"""
Audit Repository: manages append-only audit logs, system lifecycle events,
HITL approvals, telemetry, evaluation runs, and dependency plans.
Stored in data/audit.sqlite with synchronous=NORMAL and WAL journal mode.
"""

import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

try:
    from ..connections import get_audit_db
    from .base import BaseRepository
except ImportError:
    from backend.db.connections import get_audit_db
    from backend.db.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class AuditRepository(BaseRepository):
    """Data access repository for audit logs, governance decisions, and system events."""

    def __init__(self, db_getter=get_audit_db):
        super().__init__(db_getter=db_getter, db_name="audit")

    # =========================================================================
    # Audit Logs (Append-Only Governance Record)
    # =========================================================================

    def append_audit_log(
        self,
        task_id: str,
        who_actor: str,
        action_type: str,
        decision_summary: Dict[str, Any],
        run_id: Optional[str] = None,
        step_id: Optional[str] = None,
        operation_id: Optional[str] = None,
        attempt_id: Optional[str] = None,
        tool_name: Optional[str] = None,
        pre_state_hash: Optional[str] = None,
        arguments_hash: Optional[str] = None,
        result_hash: Optional[str] = None,
        approval_id: Optional[str] = None,
        decision_factors: Optional[Dict[str, Any]] = None,
        policy_rule_ids: Optional[List[str]] = None,
        log_id: Optional[str] = None,
    ) -> str:
        """Appends a new immutable audit record."""
        lid = log_id or f"log_{uuid.uuid4().hex[:12]}"
        rid = run_id or f"run_{task_id[:12]}"
        now = datetime.now(timezone.utc).isoformat()

        dec_summary_json = json.dumps(decision_summary)
        dec_factors_json = json.dumps(decision_factors) if decision_factors is not None else None
        policy_rules_json = json.dumps(policy_rule_ids) if policy_rule_ids is not None else None

        with self.write_transaction("append_audit_log") as cur:
            cur.execute(
                """
                INSERT INTO audit_logs (
                    log_id, run_id, task_id, step_id, operation_id, attempt_id,
                    who_actor, action_type, tool_name, pre_state_hash,
                    arguments_hash, result_hash, approval_id, decision_summary,
                    decision_factors, policy_rule_ids, reconciliation_status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'VALIDATED', ?)
                """,
                (
                    lid,
                    rid,
                    task_id,
                    step_id,
                    operation_id,
                    attempt_id,
                    who_actor,
                    action_type,
                    tool_name,
                    pre_state_hash,
                    arguments_hash,
                    result_hash,
                    approval_id,
                    dec_summary_json,
                    dec_factors_json,
                    policy_rules_json,
                    now,
                ),
            )
        return lid

    def get_audit_logs_for_task(self, task_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Retrieves audit logs associated with a specific task."""
        conn = self.get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT * FROM audit_logs
                WHERE task_id = ?
                ORDER BY log_sequence ASC
                LIMIT ?
                """,
                (task_id, limit),
            )
            return self.rows_to_dicts(cur.fetchall())
        finally:
            conn.close()

    def list_recent_audit_logs(self, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """Lists recent audit logs across all tasks."""
        conn = self.get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT * FROM audit_logs
                ORDER BY log_sequence DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            )
            return self.rows_to_dicts(cur.fetchall())
        finally:
            conn.close()

    # =========================================================================
    # System Lifecycle Events
    # =========================================================================

    def record_system_event(
        self,
        worker_id: str,
        boot_id: str,
        event_type: str,
        component: str,
        description: Optional[str] = None,
        task_id: Optional[str] = None,
        run_id: Optional[str] = None,
        operation_id: Optional[str] = None,
        attempt_id: Optional[str] = None,
        event_id: Optional[str] = None,
    ) -> str:
        """Records a system lifecycle event (e.g. BOOT, SAFE_MODE_ENTERED, SHUTDOWN_CLEAN)."""
        eid = event_id or f"evt_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()

        with self.write_transaction("record_system_event") as cur:
            cur.execute(
                """
                INSERT INTO system_events (
                    event_id, worker_id, boot_id, event_type, component,
                    description, run_id, task_id, operation_id, attempt_id, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    eid,
                    worker_id,
                    boot_id,
                    event_type,
                    component,
                    description,
                    run_id,
                    task_id,
                    operation_id,
                    attempt_id,
                    now,
                ),
            )
        return eid

    def list_system_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Lists recent system lifecycle events."""
        conn = self.get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM system_events ORDER BY event_sequence DESC LIMIT ?",
                (limit,),
            )
            return self.rows_to_dicts(cur.fetchall())
        finally:
            conn.close()

    # =========================================================================
    # HITL Approvals
    # =========================================================================

    def record_hitl_event(
        self,
        approval_id: str,
        task_id: str,
        event_type: str,
        target_action_hash: str,
        tool_version: str,
        resource_version_hash: str,
        nonce: str,
        expires_at: str,
        actor: Optional[str] = None,
        signature: Optional[str] = None,
        event_id: Optional[str] = None,
    ) -> str:
        """Records a human-in-the-loop approval lifecycle transition."""
        eid = event_id or f"hitl_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()

        with self.write_transaction("record_hitl_event") as cur:
            cur.execute(
                """
                INSERT INTO hitl_approval_events (
                    event_id, approval_id, task_id, event_type, target_action_hash,
                    tool_version, resource_version_hash, nonce, expires_at,
                    cryptographic_signature, actor, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    eid,
                    approval_id,
                    task_id,
                    event_type,
                    target_action_hash,
                    tool_version,
                    resource_version_hash,
                    nonce,
                    expires_at,
                    signature,
                    actor,
                    now,
                ),
            )
        return eid

    # =========================================================================
    # Telemetry Events
    # =========================================================================

    def record_telemetry(
        self,
        worker_id: str,
        metric_name: str,
        metric_value: float,
        unit: str,
        task_id: Optional[str] = None,
        step_id: Optional[str] = None,
    ) -> None:
        """Records high-frequency hardware or token telemetry."""
        now = datetime.now(timezone.utc).isoformat()
        with self.write_transaction("record_telemetry") as cur:
            cur.execute(
                """
                INSERT INTO telemetry_events (
                    worker_id, task_id, step_id, metric_name, metric_value, unit, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (worker_id, task_id, step_id, metric_name, metric_value, unit, now),
            )

    # =========================================================================
    # Eval Runs
    # =========================================================================

    def record_eval_run(
        self,
        run_id: str,
        model_id: str,
        prompt_hash: str,
        config_version: str,
        gateway_version: str,
        total_cases: int,
        passed_cases: int,
        failed_cases: int,
        pass_rate: float,
        summary: Dict[str, Any],
    ) -> str:
        """Records an evaluation run summary."""
        now = datetime.now(timezone.utc).isoformat()
        summary_json = json.dumps(summary)

        with self.write_transaction("record_eval_run") as cur:
            cur.execute(
                """
                INSERT INTO eval_runs (
                    run_id, model_id, prompt_hash, config_version, gateway_version,
                    total_cases, passed_cases, failed_cases, pass_rate, summary_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    model_id,
                    prompt_hash,
                    config_version,
                    gateway_version,
                    total_cases,
                    passed_cases,
                    failed_cases,
                    pass_rate,
                    summary_json,
                    now,
                ),
            )
        return run_id
