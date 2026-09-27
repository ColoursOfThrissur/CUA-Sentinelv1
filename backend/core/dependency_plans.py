"""Persistence boundary for reviewable dependency-change plans.

This module does not run package managers. It only records immutable plan data
and controlled lifecycle state for a later approved executor.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional

from db.connections import get_operational_db
from core.path_security import path_security, PathSecurityViolation

logger = logging.getLogger(__name__)


VALID_ECOSYSTEMS = {"pip", "npm"}
VALID_STATUSES = {
    "PLANNED", "AWAITING_APPROVAL", "APPROVED", "EXECUTING",
    "SUCCEEDED", "FAILED", "REJECTED", "EXPIRED",
}

# PEP 508 PyPI package name regex: starts/ends with alphanumeric, can contain . - _
PIP_PACKAGE_REGEX = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?$")

# npm package name regex: optional @scope/ prefix, lowercase alphanumeric, -, _, .
NPM_PACKAGE_REGEX = re.compile(r"^(?:@[a-z0-9_.-]+/)?[a-z0-9_.-]+$")

# Disallowed characters that could lead to command or path injection
PACKAGE_FORBIDDEN_CHARS = set(";&|`$()<>\\\"'\r\n\t\0")
SPEC_FORBIDDEN_CHARS = set(";&|`$()\\\"'\r\n\t\0")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def hash_file(file_path: Optional[str]) -> Optional[str]:
    """Computes SHA256 hex digest of a file if it exists, otherwise None."""
    if not file_path or not os.path.isfile(file_path):
        return None
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def validate_package_name(package_name: str, ecosystem: str) -> str:
    """Validates that a package name is safe and conforms to ecosystem naming rules."""
    if not package_name or not isinstance(package_name, str):
        raise ValueError("Package name must be a non-empty string")

    pkg = package_name.strip()
    if not pkg:
        raise ValueError("Package name cannot be whitespace")

    if any(c in PACKAGE_FORBIDDEN_CHARS or c.isspace() for c in pkg):
        raise ValueError(f"Package name contains forbidden characters: {pkg!r}")

    if pkg.startswith("-"):
        raise ValueError(f"Package name cannot start with a hyphen (flag injection risk): {pkg!r}")

    if ".." in pkg:
        raise ValueError(f"Package name cannot contain directory traversal: {pkg!r}")

    if ecosystem == "pip":
        if "/" in pkg or "\\" in pkg:
            raise ValueError(f"Pip package name cannot contain path separators: {pkg!r}")
        if not PIP_PACKAGE_REGEX.match(pkg):
            raise ValueError(f"Invalid pip package name (must conform to PEP 508): {pkg!r}")
        return pkg

    elif ecosystem == "npm":
        if "\\" in pkg:
            raise ValueError(f"npm package name cannot contain backslashes: {pkg!r}")
        if "/" in pkg:
            # Must be a valid scoped package @scope/package
            if not pkg.startswith("@") or pkg.count("/") != 1:
                raise ValueError(f"Invalid scoped npm package name: {pkg!r}")
        if not NPM_PACKAGE_REGEX.match(pkg):
            raise ValueError(f"Invalid npm package name: {pkg!r}")
        return pkg

    else:
        raise ValueError(f"Unsupported dependency ecosystem: {ecosystem}")


def validate_requested_spec(package_name: str, requested_spec: str, ecosystem: str) -> str:
    """Validates that a requested version specifier is safe and references the package."""
    if not requested_spec or not isinstance(requested_spec, str):
        raise ValueError("Requested spec must be a non-empty string")

    spec = requested_spec.strip()
    if not spec:
        raise ValueError("Requested spec cannot be whitespace")

    if any(c in SPEC_FORBIDDEN_CHARS or c == "\n" or c == "\r" or c == "\0" for c in spec):
        raise ValueError(f"Requested spec contains forbidden characters: {spec!r}")

    if spec.startswith("-"):
        raise ValueError(f"Requested spec cannot start with a hyphen: {spec!r}")

    pkg = validate_package_name(package_name, ecosystem)

    if ecosystem == "pip":
        # Spec must either equal package name, or start with package_name followed by version constraint
        if spec.lower() == pkg.lower():
            return spec
        if not spec.lower().startswith(pkg.lower()):
            raise ValueError(f"Pip spec '{spec}' does not match package name '{pkg}'")
        constraint = spec[len(pkg):].strip()
        # Allowed constraint characters: <, >, =, !, ~, ,, ., +, -, and alphanumeric
        if not re.match(r"^(?:[<>=!~]+[A-Za-z0-9._+-]+)(?:,\s*[<>=!~]+[A-Za-z0-9._+-]+)*$", constraint):
            raise ValueError(f"Invalid pip version constraint in spec: {spec!r}")
        return spec

    elif ecosystem == "npm":
        # Spec can equal package name, or package_name@version_constraint
        if spec == pkg:
            return spec
        if not spec.startswith(pkg + "@"):
            raise ValueError(f"npm spec '{spec}' must match '{pkg}' or '{pkg}@<version>'")
        version_part = spec[len(pkg) + 1:].strip()
        if not re.match(r"^[0-9a-zA-Z^~.*><=\s|-]+$", version_part):
            raise ValueError(f"Invalid npm version constraint in spec: {spec!r}")
        return spec

    else:
        raise ValueError(f"Unsupported dependency ecosystem: {ecosystem}")


def is_pinned_spec(requested_spec: str, ecosystem: str) -> bool:
    """Returns True if the specifier binds to an exact, immutable package version."""
    spec = requested_spec.strip()
    if ecosystem == "pip":
        if "==" not in spec:
            return False
        # If there are commas (multiple clauses) or wildcards, it's not pinned
        if "," in spec or "*" in spec:
            return False
        parts = spec.split("==", 1)
        if len(parts) != 2:
            return False
        version = parts[1].strip()
        # Version must be non-empty and conform to exact release version (e.g. 2.32.3)
        return bool(re.match(r"^\d+(?:\.\d+)*(?:[a-zA-Z0-9._+-]+)?$", version))

    elif ecosystem == "npm":
        if "@" not in spec:
            return False
        # Scoped packages like @types/node@20.0.0 have two @ symbols
        version = spec.rsplit("@", 1)[1].strip()
        # Non-pinned if range operators or tags are used
        if any(c in version for c in ("^", "~", ">", "<", "*", "x", "X")) or version in ("latest", "next"):
            return False
        return bool(re.match(r"^\d+\.\d+\.\d+(?:-[a-zA-Z0-9._+-]+)?$", version))

    return False


def _record_audit_event(
    *,
    action_type: str,
    actor: str,
    plan_id: str,
    plan_hash: str,
    decision_summary: dict[str, Any],
    decision_factors: Optional[dict[str, Any]] = None,
    task_id: Optional[str] = None,
) -> None:
    """Appends a structured governance event to the audit database."""
    try:
        from db.connections import get_audit_db
        conn = get_audit_db()
        try:
            log_id = str(uuid.uuid4())
            run_id = f"dep_plan_{plan_id[:8]}"
            t_id = task_id or f"task_{plan_id[:8]}"
            conn.execute(
                """
                INSERT INTO audit_logs (
                    log_id, run_id, task_id, who_actor, action_type,
                    arguments_hash, decision_summary, decision_factors,
                    reconciliation_status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'VALIDATED', ?)
                """,
                (
                    log_id,
                    run_id,
                    t_id,
                    actor,
                    action_type,
                    plan_hash,
                    _canonical_json(decision_summary),
                    _canonical_json(decision_factors) if decision_factors else None,
                    _utc_now(),
                ),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        logger.warning(f"Failed to record audit log for plan {plan_id}: {e}")


@dataclass(frozen=True)
class DependencyChangePlan:
    plan_id: str
    project_path: str
    ecosystem: str
    package_name: str
    requested_spec: str
    reason: str
    evidence: list[dict[str, Any]]
    manifest_path: str
    lockfile_path: Optional[str]
    manifest_before_hash: Optional[str]
    lockfile_before_hash: Optional[str]
    command: list[str]
    plan_hash: str
    status: str
    created_at: str
    expires_at: str
    approved_at: Optional[str] = None
    executed_at: Optional[str] = None
    result: Optional[dict[str, Any]] = None

    @property
    def is_pinned(self) -> bool:
        return is_pinned_spec(self.requested_spec, self.ecosystem)


class DependencyPlanRepository:
    """Stores immutable dependency plans and manages their lifecycle transitions."""

    @staticmethod
    def compute_plan_hash(
        *,
        project_path: str,
        ecosystem: str,
        package_name: str,
        requested_spec: str,
        manifest_path: str,
        lockfile_path: Optional[str],
        manifest_before_hash: Optional[str],
        lockfile_before_hash: Optional[str],
        command: Iterable[str],
    ) -> str:
        payload = {
            "project_path": project_path,
            "ecosystem": ecosystem,
            "package_name": package_name,
            "requested_spec": requested_spec,
            "manifest_path": manifest_path,
            "lockfile_path": lockfile_path,
            "manifest_before_hash": manifest_before_hash,
            "lockfile_before_hash": lockfile_before_hash,
            "command": list(command),
        }
        return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()

    def create(
        self,
        *,
        project_path: str,
        ecosystem: str,
        package_name: str,
        requested_spec: str,
        reason: str,
        evidence: Optional[list[dict[str, Any]]] = None,
        manifest_path: str,
        lockfile_path: Optional[str] = None,
        manifest_before_hash: Optional[str] = None,
        lockfile_before_hash: Optional[str] = None,
        command: list[str],
        ttl_minutes: int = 15,
        task_id: Optional[str] = None,
        actor: str = "system",
    ) -> DependencyChangePlan:
        if ecosystem not in VALID_ECOSYSTEMS:
            raise ValueError(f"Unsupported dependency ecosystem: {ecosystem}")

        clean_package_name = validate_package_name(package_name, ecosystem)
        clean_requested_spec = validate_requested_spec(clean_package_name, requested_spec, ecosystem)

        if not reason:
            raise ValueError("Reason is required")
        if not command or any(not isinstance(token, str) or not token for token in command):
            raise ValueError("Command must be a non-empty list of non-empty argument tokens")
        if ttl_minutes <= 0:
            raise ValueError("Plan TTL must be positive")

        now = datetime.now(timezone.utc)
        command_tokens = list(command)
        plan_hash = self.compute_plan_hash(
            project_path=project_path,
            ecosystem=ecosystem,
            package_name=clean_package_name,
            requested_spec=clean_requested_spec,
            manifest_path=manifest_path,
            lockfile_path=lockfile_path,
            manifest_before_hash=manifest_before_hash,
            lockfile_before_hash=lockfile_before_hash,
            command=command_tokens,
        )
        plan = DependencyChangePlan(
            plan_id=str(uuid.uuid4()),
            project_path=project_path,
            ecosystem=ecosystem,
            package_name=clean_package_name,
            requested_spec=clean_requested_spec,
            reason=reason,
            evidence=evidence or [],
            manifest_path=manifest_path,
            lockfile_path=lockfile_path,
            manifest_before_hash=manifest_before_hash,
            lockfile_before_hash=lockfile_before_hash,
            command=command_tokens,
            plan_hash=plan_hash,
            status="PLANNED",
            created_at=now.isoformat(),
            expires_at=(now + timedelta(minutes=ttl_minutes)).isoformat(),
        )

        conn = get_operational_db()
        try:
            conn.execute(
                """
                INSERT INTO dependency_change_plans (
                    plan_id, project_path, ecosystem, package_name, requested_spec,
                    reason, evidence_json, manifest_path, lockfile_path,
                    manifest_before_hash, lockfile_before_hash, command_json,
                    plan_hash, status, created_at, expires_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    plan.plan_id, plan.project_path, plan.ecosystem, plan.package_name,
                    plan.requested_spec, plan.reason, _canonical_json(plan.evidence),
                    plan.manifest_path, plan.lockfile_path, plan.manifest_before_hash,
                    plan.lockfile_before_hash, _canonical_json(plan.command), plan.plan_hash,
                    plan.status, plan.created_at, plan.expires_at, plan.created_at,
                ),
            )
            conn.commit()
        finally:
            conn.close()

        _record_audit_event(
            action_type="DEPENDENCY_PLAN_CREATED",
            actor=actor,
            plan_id=plan.plan_id,
            plan_hash=plan.plan_hash,
            decision_summary={
                "action": "plan_created",
                "package": plan.package_name,
                "spec": plan.requested_spec,
                "ecosystem": plan.ecosystem,
                "is_pinned": plan.is_pinned,
            },
            task_id=task_id,
        )

        return plan

    def get(self, plan_id: str) -> Optional[DependencyChangePlan]:
        conn = get_operational_db()
        try:
            row = conn.execute(
                "SELECT * FROM dependency_change_plans WHERE plan_id = ?", (plan_id,)
            ).fetchone()
            return self._to_plan(row) if row else None
        finally:
            conn.close()

    def list_by_status(self, status: Optional[str] = None) -> list[DependencyChangePlan]:
        if status is not None and status not in VALID_STATUSES:
            raise ValueError(f"Unsupported dependency plan status: {status}")
        conn = get_operational_db()
        try:
            if status is None:
                rows = conn.execute(
                    "SELECT * FROM dependency_change_plans ORDER BY created_at DESC"
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM dependency_change_plans WHERE status = ? ORDER BY created_at DESC", (status,)
                ).fetchall()
            return [self._to_plan(row) for row in rows]
        finally:
            conn.close()

    def request_approval(self, plan_id: str, actor: str = "agent") -> DependencyChangePlan:
        """Transitions a plan from PLANNED to AWAITING_APPROVAL."""
        plan = self.get(plan_id)
        if not plan:
            raise KeyError(f"Dependency plan not found: {plan_id}")

        if plan.status != "PLANNED":
            raise ValueError(f"Cannot request approval for plan in status: {plan.status}")

        now = _utc_now()
        if plan.expires_at <= now:
            self._update_status(plan_id, "EXPIRED")
            raise ValueError("Dependency plan has expired")

        self._update_status(plan_id, "AWAITING_APPROVAL")
        _record_audit_event(
            action_type="DEPENDENCY_PLAN_AWAITING_APPROVAL",
            actor=actor,
            plan_id=plan.plan_id,
            plan_hash=plan.plan_hash,
            decision_summary={"action": "awaiting_approval", "plan_id": plan_id},
        )
        return self.get(plan_id)

    def approve(
        self,
        plan_id: str,
        expected_plan_hash: str,
        allow_unpinned: bool = False,
        actor: str = "user",
    ) -> DependencyChangePlan:
        """Validates plan hash, manifest disk state, and unpinned confirmation before approving."""
        plan = self.get(plan_id)
        if not plan:
            raise KeyError(f"Dependency plan not found: {plan_id}")

        if plan.status not in ("PLANNED", "AWAITING_APPROVAL"):
            raise ValueError(f"Plan cannot be approved from status: {plan.status}")

        now = _utc_now()
        if plan.expires_at <= now:
            self._update_status(plan_id, "EXPIRED")
            raise ValueError("Dependency plan has expired")

        if plan.plan_hash != expected_plan_hash:
            raise ValueError("Plan hash mismatch: plan definition has been tampered with or modified")

        if not plan.is_pinned and not allow_unpinned:
            raise ValueError("Plan specifies unpinned dependency; explicit allow_unpinned confirmation required")

        # Concurrency guard: verify manifest on disk has not changed since plan creation
        if plan.manifest_path and os.path.exists(plan.manifest_path):
            current_manifest_hash = hash_file(plan.manifest_path)
            if plan.manifest_before_hash and current_manifest_hash != plan.manifest_before_hash:
                self._update_status(plan_id, "FAILED", result={"error": "Manifest changed on disk (stale hash)"})
                raise ValueError("Manifest has changed on disk since plan creation (stale hash)")

        # Concurrency guard: verify lockfile on disk has not changed if tracked
        if plan.lockfile_path and os.path.exists(plan.lockfile_path):
            current_lockfile_hash = hash_file(plan.lockfile_path)
            if plan.lockfile_before_hash and current_lockfile_hash != plan.lockfile_before_hash:
                self._update_status(plan_id, "FAILED", result={"error": "Lockfile changed on disk (stale hash)"})
                raise ValueError("Lockfile has changed on disk since plan creation (stale hash)")

        conn = get_operational_db()
        try:
            conn.execute(
                """
                UPDATE dependency_change_plans
                SET status = 'APPROVED', approved_at = ?, updated_at = ?
                WHERE plan_id = ? AND status IN ('PLANNED', 'AWAITING_APPROVAL')
                """,
                (now, now, plan_id),
            )
            conn.commit()
        finally:
            conn.close()

        _record_audit_event(
            action_type="DEPENDENCY_PLAN_APPROVED",
            actor=actor,
            plan_id=plan.plan_id,
            plan_hash=plan.plan_hash,
            decision_summary={
                "action": "approved",
                "allow_unpinned": allow_unpinned,
                "actor": actor,
            },
        )
        return self.get(plan_id)

    def reject(self, plan_id: str, reason: str = "", actor: str = "user") -> DependencyChangePlan:
        """Marks an unexecuted plan as REJECTED with an optional reason."""
        plan = self.get(plan_id)
        if not plan:
            raise KeyError(f"Dependency plan not found: {plan_id}")

        if plan.status in ("SUCCEEDED", "FAILED", "REJECTED", "EXPIRED", "EXECUTING"):
            raise ValueError(f"Cannot reject plan in terminal or running status: {plan.status}")

        result_payload = {"reject_reason": reason} if reason else None
        self._update_status(plan_id, "REJECTED", result=result_payload)

        _record_audit_event(
            action_type="DEPENDENCY_PLAN_REJECTED",
            actor=actor,
            plan_id=plan.plan_id,
            plan_hash=plan.plan_hash,
            decision_summary={"action": "rejected", "reason": reason, "actor": actor},
        )
        return self.get(plan_id)

    def mark_executing(self, plan_id: str, expected_plan_hash: str, actor: str = "executor") -> DependencyChangePlan:
        """Atomically consumes an approval and transitions the plan to EXECUTING."""
        plan = self.get(plan_id)
        if not plan:
            raise KeyError(f"Dependency plan not found: {plan_id}")

        if plan.status != "APPROVED":
            raise ValueError(f"Plan must be in APPROVED status to execute, got: {plan.status}")

        now = _utc_now()
        if plan.expires_at <= now:
            self._update_status(plan_id, "EXPIRED")
            raise ValueError("Dependency plan has expired")

        if plan.plan_hash != expected_plan_hash:
            raise ValueError("Plan hash mismatch during execution handoff")

        conn = get_operational_db()
        try:
            cursor = conn.execute(
                """
                UPDATE dependency_change_plans
                SET status = 'EXECUTING', updated_at = ?
                WHERE plan_id = ? AND status = 'APPROVED' AND plan_hash = ? AND expires_at > ?
                """,
                (now, plan_id, expected_plan_hash, now),
            )
            conn.commit()
            if cursor.rowcount == 0:
                raise ValueError("Could not mark plan as EXECUTING (concurrent transition or expired)")
        finally:
            conn.close()

        _record_audit_event(
            action_type="DEPENDENCY_PLAN_EXECUTING",
            actor=actor,
            plan_id=plan.plan_id,
            plan_hash=plan.plan_hash,
            decision_summary={"action": "executing", "actor": actor},
        )
        return self.get(plan_id)

    def mark_completed(
        self,
        plan_id: str,
        success: bool,
        result_payload: Optional[dict[str, Any]] = None,
        actor: str = "executor",
    ) -> DependencyChangePlan:
        """Transitions an EXECUTING plan to SUCCEEDED or FAILED."""
        plan = self.get(plan_id)
        if not plan:
            raise KeyError(f"Dependency plan not found: {plan_id}")

        if plan.status != "EXECUTING":
            raise ValueError(f"Plan must be in EXECUTING status to complete, got: {plan.status}")

        new_status = "SUCCEEDED" if success else "FAILED"
        now = _utc_now()

        conn = get_operational_db()
        try:
            conn.execute(
                """
                UPDATE dependency_change_plans
                SET status = ?, executed_at = ?, result_json = ?, updated_at = ?
                WHERE plan_id = ? AND status = 'EXECUTING'
                """,
                (new_status, now, _canonical_json(result_payload or {}), now, plan_id),
            )
            conn.commit()
        finally:
            conn.close()

        _record_audit_event(
            action_type=f"DEPENDENCY_PLAN_{new_status}",
            actor=actor,
            plan_id=plan.plan_id,
            plan_hash=plan.plan_hash,
            decision_summary={"action": new_status.lower(), "success": success, "actor": actor},
            decision_factors=result_payload,
        )
        return self.get(plan_id)

    def expire_stale_plans(self) -> int:
        """Transitions any active non-terminal plans past their expires_at to EXPIRED."""
        now = _utc_now()
        conn = get_operational_db()
        try:
            cursor = conn.execute(
                """
                UPDATE dependency_change_plans
                SET status = 'EXPIRED', updated_at = ?
                WHERE status IN ('PLANNED', 'AWAITING_APPROVAL', 'APPROVED') AND expires_at <= ?
                """,
                (now, now),
            )
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()

    def _update_status(
        self,
        plan_id: str,
        new_status: str,
        result: Optional[dict[str, Any]] = None,
    ) -> None:
        now = _utc_now()
        conn = get_operational_db()
        try:
            if result is not None:
                conn.execute(
                    """
                    UPDATE dependency_change_plans
                    SET status = ?, result_json = ?, updated_at = ?
                    WHERE plan_id = ?
                    """,
                    (new_status, _canonical_json(result), now, plan_id),
                )
            else:
                conn.execute(
                    "UPDATE dependency_change_plans SET status = ?, updated_at = ? WHERE plan_id = ?",
                    (new_status, now, plan_id),
                )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _to_plan(row: Any) -> DependencyChangePlan:
        return DependencyChangePlan(
            plan_id=row["plan_id"], project_path=row["project_path"], ecosystem=row["ecosystem"],
            package_name=row["package_name"], requested_spec=row["requested_spec"],
            reason=row["reason"], evidence=json.loads(row["evidence_json"]),
            manifest_path=row["manifest_path"], lockfile_path=row["lockfile_path"],
            manifest_before_hash=row["manifest_before_hash"], lockfile_before_hash=row["lockfile_before_hash"],
            command=json.loads(row["command_json"]), plan_hash=row["plan_hash"], status=row["status"],
            created_at=row["created_at"], expires_at=row["expires_at"], approved_at=row["approved_at"],
            executed_at=row["executed_at"], result=json.loads(row["result_json"]) if row["result_json"] else None,
        )


dependency_plan_repository = DependencyPlanRepository()


class DependencyPlanBuilder:
    """Validates parameters, hashes file boundaries, and creates reviewable DependencyChangePlans."""

    def __init__(self, repository: Optional[DependencyPlanRepository] = None):
        self.repository = repository or dependency_plan_repository

    def create_plan(
        self,
        *,
        project_path: str,
        ecosystem: str,
        package_name: str,
        requested_spec: str,
        reason: str,
        manifest_path: str,
        evidence: Optional[list[dict[str, Any]]] = None,
        lockfile_path: Optional[str] = None,
        python_exe: Optional[str] = None,
        ttl_minutes: int = 15,
        task_id: Optional[str] = None,
        actor: str = "environment_engine",
    ) -> DependencyChangePlan:
        canonical_project = path_security.canonicalize_path(project_path)
        canonical_manifest = path_security.canonicalize_path(manifest_path, root_boundary=canonical_project)

        canonical_lockfile: Optional[str] = None
        if lockfile_path:
            canonical_lockfile = path_security.canonicalize_path(lockfile_path, root_boundary=canonical_project)

        clean_package = validate_package_name(package_name, ecosystem)
        clean_spec = validate_requested_spec(clean_package, requested_spec, ecosystem)

        manifest_before_hash = hash_file(canonical_manifest)
        lockfile_before_hash = hash_file(canonical_lockfile) if canonical_lockfile else None

        if ecosystem == "pip":
            py = python_exe or sys.executable
            command = [py, "-m", "pip", "install", clean_spec]
        elif ecosystem == "npm":
            command = ["npm", "install", clean_spec]
        else:
            raise ValueError(f"Unsupported dependency ecosystem: {ecosystem}")

        return self.repository.create(
            project_path=canonical_project,
            ecosystem=ecosystem,
            package_name=clean_package,
            requested_spec=clean_spec,
            reason=reason,
            evidence=evidence or [],
            manifest_path=canonical_manifest,
            lockfile_path=canonical_lockfile,
            manifest_before_hash=manifest_before_hash,
            lockfile_before_hash=lockfile_before_hash,
            command=command,
            ttl_minutes=ttl_minutes,
            task_id=task_id,
            actor=actor,
        )


dependency_plan_builder = DependencyPlanBuilder()


class DependencyChangeExecutor:
    """Sole authorized executor for dependency installations in CUA-Sentinel."""

    def __init__(
        self,
        repository: Optional[DependencyPlanRepository] = None,
        process_runner: Optional[Any] = None,
    ):
        self.repository = repository or dependency_plan_repository
        self._process_runner = process_runner or subprocess.run

    def execute_plan(
        self,
        plan_id: str,
        expected_plan_hash: str,
        actor: str = "dependency_executor",
    ) -> dict[str, Any]:
        """
        Executes an approved, unexpired plan after single-use consumption and backup capture.
        Enforces tokenized command array with shell=False.
        """
        plan = self.repository.get(plan_id)
        if not plan:
            raise KeyError(f"Dependency plan not found: {plan_id}")

        # Transition to EXECUTING (ensures single-use and validates APPROVED status & hash)
        self.repository.mark_executing(plan_id, expected_plan_hash, actor=actor)

        # 1. Create backups of manifest and lockfile before command execution
        backup_dir = os.path.join(plan.project_path, ".sentinel_backup", "deps", plan.plan_id)
        os.makedirs(backup_dir, exist_ok=True)

        backup_manifest_path = None
        if plan.manifest_path and os.path.exists(plan.manifest_path):
            backup_manifest_path = os.path.join(backup_dir, os.path.basename(plan.manifest_path))
            shutil.copy2(plan.manifest_path, backup_manifest_path)

        backup_lockfile_path = None
        if plan.lockfile_path and os.path.exists(plan.lockfile_path):
            backup_lockfile_path = os.path.join(backup_dir, os.path.basename(plan.lockfile_path))
            shutil.copy2(plan.lockfile_path, backup_lockfile_path)

        # 2. Execute approved tokenized command (strictly shell=False)
        try:
            res = self._process_runner(
                plan.command,
                cwd=plan.project_path,
                capture_output=True,
                text=True,
                timeout=180,
                shell=False,
            )
            success = (getattr(res, "returncode", 0) == 0)
            manifest_after_hash = hash_file(plan.manifest_path)
            lockfile_after_hash = hash_file(plan.lockfile_path)

            result_payload = {
                "success": success,
                "returncode": getattr(res, "returncode", 0),
                "manifest_after_hash": manifest_after_hash,
                "lockfile_after_hash": lockfile_after_hash,
                "backup_dir": backup_dir,
                "stdout": getattr(res, "stdout", "")[-2000:],
                "stderr": getattr(res, "stderr", "")[-2000:],
            }
            self.repository.mark_completed(plan_id, success=success, result_payload=result_payload, actor=actor)
            return result_payload

        except Exception as err:
            result_payload = {
                "success": False,
                "returncode": -1,
                "error": str(err),
                "backup_dir": backup_dir,
            }
            self.repository.mark_completed(plan_id, success=False, result_payload=result_payload, actor=actor)
            return result_payload

    def rollback_plan(self, plan_id: str, actor: str = "user") -> dict[str, Any]:
        """Restores backed-up manifest and lockfile if an installation failed or needs reverting."""
        plan = self.repository.get(plan_id)
        if not plan:
            raise KeyError(f"Dependency plan not found: {plan_id}")

        backup_dir = os.path.join(plan.project_path, ".sentinel_backup", "deps", plan.plan_id)
        if not os.path.exists(backup_dir):
            raise FileNotFoundError(f"No backup directory found for plan {plan_id}")

        restored_files = []
        if plan.manifest_path:
            backup_manifest = os.path.join(backup_dir, os.path.basename(plan.manifest_path))
            if os.path.exists(backup_manifest):
                shutil.copy2(backup_manifest, plan.manifest_path)
                restored_files.append(plan.manifest_path)

        if plan.lockfile_path:
            backup_lockfile = os.path.join(backup_dir, os.path.basename(plan.lockfile_path))
            if os.path.exists(backup_lockfile):
                shutil.copy2(backup_lockfile, plan.lockfile_path)
                restored_files.append(plan.lockfile_path)

        _record_audit_event(
            action_type="DEPENDENCY_PLAN_ROLLBACK",
            actor=actor,
            plan_id=plan.plan_id,
            plan_hash=plan.plan_hash,
            decision_summary={"action": "rollback", "restored_files": restored_files, "actor": actor},
        )
        return {"success": True, "restored_files": restored_files}


dependency_change_executor = DependencyChangeExecutor()

