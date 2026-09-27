import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from db.connections import get_audit_db, get_operational_db

logger = logging.getLogger(__name__)

TASK_TERMINAL_STATES = {"COMPLETED", "FAILED", "CANCELLED", "ARCHIVED"}

TASK_TRANSITIONS = {
    "QUEUED": {"RUNNING", "CANCEL_REQUESTED", "ARCHIVED"},
    "RUNNING": {"COMPLETED", "FAILED", "PREEMPTED", "CANCEL_REQUESTED", "QUEUED"},
    "PREEMPTED": {"QUEUED", "RUNNING", "CANCEL_REQUESTED", "FAILED"},
    "BLOCKED": {"QUEUED", "CANCEL_REQUESTED", "FAILED"},
    "CANCEL_REQUESTED": {"CANCELLED", "FAILED"},
    "COMPLETED": {"ARCHIVED"},
    "FAILED": {"ARCHIVED", "QUEUED"},
    "CANCELLED": {"ARCHIVED"},
    "ARCHIVED": set(),
}

MODEL_TRANSITIONS = {
    "UNLOADED": {"LOADING"},
    "LOADING": {"READY", "FAILED", "LOAD_TIMEOUT"},
    "READY": {"BUSY", "IDLE", "EVICTING", "UNHEALTHY"},
    "IDLE": {"BUSY", "EVICTING", "UNHEALTHY"},
    "BUSY": {"READY", "FAILED", "UNHEALTHY", "EVICTING", "UNLOADED"},
    "EVICTING": {"UNLOADED", "FAILED"},
    "FAILED": {"RECOVERING", "UNLOADED"},
    "LOAD_TIMEOUT": {"RECOVERING", "UNLOADED"},
    "UNHEALTHY": {"RECOVERING", "UNLOADED"},
    "RECOVERING": {"READY", "FAILED", "UNLOADED"},
}

JSON_FIELDS = {
    "tasks": ("requested_capabilities", "granted_capabilities", "input_payload", "result_payload"),
    "task_steps": ("input_context", "output_summary"),
    "hitl_pending": ("action_payload",),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def parse_json_fields(row: Any, fields: Iterable[str]) -> dict:
    data = dict(row)
    for field in fields:
        if data.get(field) is not None and isinstance(data[field], str):
            try:
                data[field] = json.loads(data[field])
            except json.JSONDecodeError:
                logger.warning("Invalid JSON in field %s", field)
    return data


class StateTransitionError(Exception):
    pass


class LeaseValidationError(Exception):
    pass


class StateManager:
    """
    Small transactional boundary around BP01/BP02.
    All dangerous state changes should pass through this class instead of raw SQL.
    """

    def audit(
        self,
        *,
        action_type: str,
        who_actor: str,
        task_id: str,
        run_id: Optional[str] = None,
        step_id: Optional[str] = None,
        operation_id: Optional[str] = None,
        attempt_id: Optional[str] = None,
        tool_name: Optional[str] = None,
        arguments: Optional[dict] = None,
        result: Optional[dict] = None,
        decision_summary: Optional[dict] = None,
        reconciliation_status: str = "VALIDATED",
    ) -> None:
        conn = get_audit_db()
        try:
            conn.execute(
                """
                INSERT INTO audit_logs (
                    log_id, run_id, task_id, step_id, operation_id, attempt_id,
                    who_actor, action_type, tool_name, arguments_hash, result_hash,
                    decision_summary, reconciliation_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    run_id or f"task:{task_id}",
                    task_id,
                    step_id,
                    operation_id,
                    attempt_id,
                    who_actor,
                    action_type,
                    tool_name,
                    stable_hash(arguments) if arguments is not None else None,
                    stable_hash(result) if result is not None else None,
                    json.dumps(decision_summary or {"summary": action_type}),
                    reconciliation_status,
                ),
            )
            conn.commit()
        except Exception as exc:
            logger.warning("Audit write failed: %s", exc)
        finally:
            conn.close()

    def validate_task_lease(self, conn, task_id: str, lease_id: str, lease_generation: int) -> None:
        if task_id in ("system", "file_diagnose", "internal", "direct") or lease_id == "internal":
            return
        lease = conn.execute(
            """
            SELECT lease_id, lease_generation, expires_at
            FROM task_leases
            WHERE task_id = ?
            """,
            (task_id,),
        ).fetchone()
        if not lease:
            raise LeaseValidationError(f"No active lease for task {task_id}")
        if lease["lease_id"] != lease_id or lease["lease_generation"] != lease_generation:
            raise LeaseValidationError(f"Stale lease for task {task_id}")
        expires = datetime.fromisoformat(lease["expires_at"].replace("Z", "+00:00"))
        if datetime.now(timezone.utc) > expires:
            raise LeaseValidationError(f"Expired lease for task {task_id}")

    def transition_task(
        self,
        *,
        task_id: str,
        new_status: str,
        lease_id: Optional[str] = None,
        lease_generation: Optional[int] = None,
        result_payload: Optional[dict] = None,
        error_message: Optional[str] = None,
        release_lease: bool = False,
        actor: str = "StateManager",
    ) -> bool:
        now = utc_now()
        conn = get_operational_db()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT status FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
            if not row:
                raise StateTransitionError(f"Task not found: {task_id}")
            current = row["status"]
            if new_status not in TASK_TRANSITIONS.get(current, set()):
                raise StateTransitionError(f"Invalid task transition {current} -> {new_status}")
            if lease_id is not None:
                self.validate_task_lease(conn, task_id, lease_id, int(lease_generation or 0))

            conn.execute(
                """
                UPDATE tasks
                SET status = ?, updated_at = ?, result_payload = ?, error_message = ?
                WHERE task_id = ?
                """,
                (
                    new_status,
                    now,
                    json.dumps(result_payload) if result_payload is not None else None,
                    error_message,
                    task_id,
                ),
            )
            if release_lease:
                conn.execute("DELETE FROM task_leases WHERE task_id = ?", (task_id,))
            conn.execute("COMMIT")
            self.audit(
                action_type=f"TASK_{current}_TO_{new_status}",
                who_actor=actor,
                task_id=task_id,
                result={"status": new_status},
            )
            return True
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    def transition_model(self, model_id: str, new_state: str, *, task_id: Optional[str] = None) -> bool:
        now = utc_now()
        conn = get_operational_db()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT current_state FROM models_registry WHERE model_id = ?", (model_id,)
            ).fetchone()
            if not row:
                raise StateTransitionError(f"Model not found: {model_id}")
            current = row["current_state"]
            if current == new_state:
                conn.execute("COMMIT")
                return True
            if new_state not in MODEL_TRANSITIONS.get(current, set()):
                raise StateTransitionError(f"Invalid model transition {current} -> {new_state}")
            conn.execute(
                """
                UPDATE models_registry
                SET current_state = ?, busy_task_id = ?, last_health_check_at = ?
                WHERE model_id = ?
                """,
                (new_state, task_id if new_state == "BUSY" else None, now, model_id),
            )
            conn.execute("COMMIT")
            return True
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()
