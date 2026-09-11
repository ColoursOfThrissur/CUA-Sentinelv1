import uuid
import json
import hashlib
import logging
from datetime import datetime, timezone, timedelta

from db.connections import get_operational_db

logger = logging.getLogger(__name__)


class GovernanceViolation(Exception):
    pass


class HITLRequired(Exception):
    def __init__(self, approval_id: str, message: str):
        self.approval_id = approval_id
        super().__init__(message)


class GovernanceEngine:
    """
    Nothing executes without passing through here.
    Checks risk level, issues capability grants, creates HITL requests,
    and enforces retry policy based on error class — not blind retry counts.
    """

    def __init__(self, policy: dict, config: dict):
        self.policy = policy
        self.config = config
        self.tool_policies = policy["tool_policies"]
        self.retry_policy = policy["retry_policy"]
        self.risk_levels = policy["risk_levels"]
        self.safe_mode_allowed = policy["safe_mode_allowed_operations"]

    def check_tool_permission(self, tool_name: str, task_id: str, is_safe_mode: bool = False) -> dict:
        """
        Returns the tool policy if allowed.
        Raises GovernanceViolation if blocked.
        Raises HITLRequired if human approval needed.
        """
        tool_policy = self.tool_policies.get(tool_name)
        if not tool_policy:
            raise GovernanceViolation(f"Unknown tool: {tool_name}")

        if is_safe_mode and tool_name not in self.safe_mode_allowed:
            raise GovernanceViolation(f"Tool {tool_name} blocked in safe mode")

        risk_level = tool_policy["risk_level"]
        level_config = self.risk_levels[risk_level]

        if level_config.get("requires_approval"):
            approval_id = self._create_hitl_request(tool_name, task_id, tool_policy)
            raise HITLRequired(approval_id, f"Tool {tool_name} requires human approval (risk={risk_level})")

        return tool_policy

    def _create_hitl_request(self, tool_name: str, task_id: str, tool_policy: dict) -> str:
        approval_id = str(uuid.uuid4())
        timeout_sec = self.risk_levels[tool_policy["risk_level"]].get("approval_timeout_sec", 3600)
        expires_at = (datetime.now(timezone.utc) + timedelta(seconds=timeout_sec)).isoformat()
        now = datetime.now(timezone.utc).isoformat()

        action_hash = hashlib.sha256(
            json.dumps({"tool": tool_name, "task_id": task_id, "ts": now}, sort_keys=True).encode()
        ).hexdigest()

        conn = get_operational_db()
        try:
            conn.execute(
                """
                INSERT INTO hitl_pending (
                    approval_id, task_id, operation_id, risk_level,
                    action_description, action_payload, action_hash,
                    tool_version, resource_version_hash, nonce,
                    status, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?)
                """,
                (
                    approval_id, task_id, str(uuid.uuid4()),
                    int(tool_policy["risk_level"][1]),
                    f"Tool execution: {tool_name}",
                    json.dumps({"tool": tool_name}),
                    action_hash, "1.0", action_hash,
                    str(uuid.uuid4()), expires_at,
                ),
            )
            conn.commit()
            logger.info(f"HITL request created: {approval_id} for tool {tool_name}")
            return approval_id
        finally:
            conn.close()

    def resolve_hitl(self, approval_id: str, approved: bool, resolved_by: str) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        conn = get_operational_db()
        try:
            row = conn.execute(
                "SELECT status, expires_at FROM hitl_pending WHERE approval_id = ?",
                (approval_id,),
            ).fetchone()

            if not row:
                return False

            if row["status"] != "PENDING":
                return False

            expires = datetime.fromisoformat(row["expires_at"].replace("Z", "+00:00"))
            if datetime.now(timezone.utc) > expires:
                conn.execute(
                    "UPDATE hitl_pending SET status = 'EXPIRED', resolved_at = ? WHERE approval_id = ?",
                    (now, approval_id),
                )
                conn.commit()
                return False

            new_status = "APPROVED" if approved else "REJECTED"
            conn.execute(
                """
                UPDATE hitl_pending SET status = ?, resolved_at = ?, resolved_by = ?
                WHERE approval_id = ?
                """,
                (new_status, now, resolved_by, approval_id),
            )
            conn.commit()
            logger.info(f"HITL {approval_id} resolved: {new_status} by {resolved_by}")
            return True
        finally:
            conn.close()

    def get_retry_action(self, error_class: str, attempt_no: int, error_fingerprint: str, prev_fingerprint: str) -> str:
        """
        Returns what to do next: 'retry', 'pivot', 'halt', 'escalate', 'backoff'
        Decision is based on error class and fingerprint — not blind retry count.
        """
        if error_fingerprint and error_fingerprint == prev_fingerprint:
            return "pivot"

        policy = self.retry_policy.get(error_class)
        if not policy:
            return "halt"

        if attempt_no >= policy["max_retries"]:
            return "halt"

        return policy["strategy"].split("_")[0]

    def is_safe_mode(self) -> bool:
        conn = get_operational_db()
        try:
            row = conn.execute(
                "SELECT value FROM system_state WHERE key = 'safe_mode'"
            ).fetchone()
            return row and row["value"] == "true"
        finally:
            conn.close()

    def enter_safe_mode(self, reason: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        conn = get_operational_db()
        try:
            conn.execute(
                "UPDATE system_state SET value = 'true', updated_at = ? WHERE key = 'safe_mode'",
                (now,),
            )
            conn.commit()
            logger.warning(f"SAFE MODE ENTERED: {reason}")
        finally:
            conn.close()

    def exit_safe_mode(self) -> None:
        now = datetime.now(timezone.utc).isoformat()
        conn = get_operational_db()
        try:
            conn.execute(
                "UPDATE system_state SET value = 'false', updated_at = ? WHERE key = 'safe_mode'",
                (now,),
            )
            conn.commit()
            logger.info("Safe mode exited.")
        finally:
            conn.close()

    def trigger_emergency_stop(self) -> None:
        now = datetime.now(timezone.utc).isoformat()
        conn = get_operational_db()
        try:
            conn.execute(
                "UPDATE system_state SET value = 'true', updated_at = ? WHERE key = 'emergency_stop'",
                (now,),
            )
            conn.commit()
            logger.critical("EMERGENCY STOP TRIGGERED.")
        finally:
            conn.close()
