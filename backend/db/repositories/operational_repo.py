"""
Operational Repository: manages task lifecycle, task steps, checkpoints, operations, and worker nodes.
Stored in data/operational.sqlite with synchronous=FULL and WAL journal mode.
"""

import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

try:
    from ..connections import get_operational_db
    from .base import BaseRepository
except ImportError:
    from backend.db.connections import get_operational_db
    from backend.db.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class OperationalRepository(BaseRepository):
    """Data access repository for operational state (tasks, steps, checkpoints, operations)."""

    def __init__(self, db_getter=get_operational_db):
        super().__init__(db_getter=db_getter, db_name="operational")

    # =========================================================================
    # Task Lifecycle Management
    # =========================================================================

    def create_task(
        self,
        task_id: Optional[str] = None,
        workflow_type: str = "ENDPOINT",
        title: str = "Untitled Task",
        description: Optional[str] = None,
        priority: int = 2,
        context_budget: int = 8192,
        input_payload: Optional[Dict[str, Any]] = None,
        parent_task_id: Optional[str] = None,
        deadline: Optional[str] = None,
    ) -> str:
        """Creates a new queued task in the operational database."""
        tid = task_id or f"task_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()
        payload_json = json.dumps(input_payload) if input_payload is not None else None

        with self.write_transaction("create_task") as cur:
            cur.execute(
                """
                INSERT INTO tasks (
                    task_id, parent_task_id, workflow_type, title, description,
                    priority, created_at, updated_at, deadline, status,
                    context_budget, input_payload, is_tainted
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'QUEUED', ?, ?, 0)
                """,
                (
                    tid,
                    parent_task_id,
                    workflow_type,
                    title,
                    description,
                    priority,
                    now,
                    now,
                    deadline,
                    context_budget,
                    payload_json,
                ),
            )
        logger.info(f"Task created: {tid} ({workflow_type}, priority={priority})")
        return tid

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a task by task_id."""
        conn = self.get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,))
            row = cur.fetchone()
            return self.row_to_dict(row)
        finally:
            conn.close()

    def update_task_status(
        self,
        task_id: str,
        status: str,
        error_message: Optional[str] = None,
        result_payload: Optional[Any] = None,
        blocked_reason: Optional[str] = None,
    ) -> bool:
        """Updates the status and optional results or errors of a task."""
        now = datetime.now(timezone.utc).isoformat()
        res_json = (
            json.dumps(result_payload)
            if result_payload is not None and not isinstance(result_payload, str)
            else result_payload
        )

        with self.write_transaction("update_task_status") as cur:
            cur.execute(
                """
                UPDATE tasks
                SET status = ?,
                    updated_at = ?,
                    error_message = COALESCE(?, error_message),
                    result_payload = COALESCE(?, result_payload),
                    blocked_reason = COALESCE(?, blocked_reason)
                WHERE task_id = ?
                """,
                (status, now, error_message, res_json, blocked_reason, task_id),
            )
            return cur.rowcount > 0

    def list_tasks(
        self,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Lists tasks optionally filtered by status, ordered by priority and created_at."""
        conn = self.get_connection()
        try:
            cur = conn.cursor()
            if status:
                cur.execute(
                    """
                    SELECT * FROM tasks
                    WHERE status = ?
                    ORDER BY priority ASC, created_at ASC
                    LIMIT ? OFFSET ?
                    """,
                    (status, limit, offset),
                )
            else:
                cur.execute(
                    """
                    SELECT * FROM tasks
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?
                    """,
                    (limit, offset),
                )
            rows = cur.fetchall()
            return self.rows_to_dicts(rows)
        finally:
            conn.close()

    def set_task_tainted(self, task_id: str, is_tainted: bool = True) -> None:
        """Marks or unmarks a task as tainted (received untrusted data)."""
        now = datetime.now(timezone.utc).isoformat()
        with self.write_transaction("set_task_tainted") as cur:
            cur.execute(
                "UPDATE tasks SET is_tainted = ?, updated_at = ? WHERE task_id = ?",
                (1 if is_tainted else 0, now, task_id),
            )

    def is_task_tainted(self, task_id: str) -> bool:
        """Checks if a task is flagged as tainted."""
        conn = self.get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT is_tainted FROM tasks WHERE task_id = ?", (task_id,))
            row = cur.fetchone()
            return bool(row["is_tainted"]) if row and "is_tainted" in row.keys() else False
        finally:
            conn.close()

    def request_task_cancellation(self, task_id: str, requested_by: str = "user") -> bool:
        """Requests cooperative cancellation for a running or queued task."""
        now = datetime.now(timezone.utc).isoformat()
        with self.write_transaction("request_task_cancellation") as cur:
            cur.execute(
                """
                UPDATE tasks
                SET status = 'CANCEL_REQUESTED',
                    cancel_requested_at = ?,
                    cancel_requested_by = ?,
                    updated_at = ?
                WHERE task_id = ? AND status IN ('QUEUED', 'RUNNING', 'BLOCKED', 'PREEMPTED')
                """,
                (now, requested_by, now, task_id),
            )
            return cur.rowcount > 0

    def get_next_queued_task(self) -> Optional[Dict[str, Any]]:
        """Fetches the next highest-priority queued task."""
        conn = self.get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT * FROM tasks
                WHERE status = 'QUEUED'
                ORDER BY priority ASC, created_at ASC
                LIMIT 1
                """
            )
            row = cur.fetchone()
            return self.row_to_dict(row)
        finally:
            conn.close()

    # =========================================================================
    # Task Step Management
    # =========================================================================

    def create_step(
        self,
        task_id: str,
        step_order: int,
        step_type: str,
        description: Optional[str] = None,
        status: str = "PENDING",
        assigned_agent: Optional[str] = None,
        input_context: Optional[str] = None,
        step_id: Optional[str] = None,
        model_id: Optional[str] = None,
        prompt_hash: Optional[str] = None,
        config_version: Optional[str] = None,
        gateway_version: Optional[str] = None,
        profile_version: Optional[str] = None,
    ) -> str:
        """Creates a step record under a task with optional version stamps."""
        sid = step_id or f"step_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()

        with self.write_transaction("create_step") as cur:
            cur.execute(
                """
                INSERT OR REPLACE INTO task_steps (
                    step_id, task_id, step_order, step_type, description, status,
                    input_context, model_id, prompt_hash, config_version, gateway_version, profile_version,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sid,
                    task_id,
                    step_order,
                    step_type,
                    description,
                    status,
                    input_context,
                    model_id,
                    prompt_hash,
                    config_version,
                    gateway_version,
                    profile_version,
                    now,
                    now,
                ),
            )
        return sid

    def update_step_status(
        self,
        step_id: str,
        status: str,
        output_summary: Optional[Any] = None,
        error_message: Optional[str] = None,
    ) -> bool:
        """Updates the completion or failure status of a step."""
        now = datetime.now(timezone.utc).isoformat()
        summary_json = (
            json.dumps(output_summary)
            if output_summary is not None and not isinstance(output_summary, str)
            else output_summary
        )
        with self.write_transaction("update_step_status") as cur:
            cur.execute(
                """
                UPDATE task_steps
                SET status = ?,
                    output_summary = COALESCE(?, output_summary),
                    updated_at = ?,
                    started_at = CASE WHEN ? = 'RUNNING' AND started_at IS NULL THEN ? ELSE started_at END,
                    finished_at = CASE WHEN ? IN ('COMPLETED', 'FAILED', 'CANCELLED', 'SKIPPED') THEN ? ELSE finished_at END
                WHERE step_id = ?
                """,
                (status, summary_json, now, status, now, status, now, step_id),
            )
            return cur.rowcount > 0

    def list_steps_for_task(self, task_id: str) -> List[Dict[str, Any]]:
        """Lists all steps for a given task ordered by step_order."""
        conn = self.get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM task_steps WHERE task_id = ? ORDER BY step_order ASC",
                (task_id,),
            )
            return self.rows_to_dicts(cur.fetchall())
        finally:
            conn.close()

    def get_step(self, step_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a single step by step_id."""
        conn = self.get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM task_steps WHERE step_id = ?", (step_id,))
            return self.row_to_dict(cur.fetchone())
        finally:
            conn.close()

    # =========================================================================
    # Checkpoint Management
    # =========================================================================

    def save_checkpoint(
        self,
        task_id: str,
        step_index: int,
        state_dict: Dict[str, Any],
        input_hash: str,
        checkpoint_id: Optional[str] = None,
        phase: Optional[str] = None,
    ) -> str:
        """Saves a durable execution checkpoint for task resumption."""
        cid = checkpoint_id or f"chk_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()
        state_json = json.dumps(state_dict)

        with self.write_transaction("save_checkpoint") as cur:
            cur.execute(
                """
                INSERT INTO task_checkpoints (
                    checkpoint_id, task_id, step_index, phase, state_json, input_hash, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (cid, task_id, step_index, phase, state_json, input_hash, now),
            )
        return cid

    def get_latest_checkpoint(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Fetches the latest checkpoint recorded for a task."""
        conn = self.get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT * FROM task_checkpoints
                WHERE task_id = ?
                ORDER BY step_index DESC, created_at DESC
                LIMIT 1
                """,
                (task_id,),
            )
            return self.row_to_dict(cur.fetchone())
        finally:
            conn.close()

    def list_checkpoints(self, task_id: str) -> List[Dict[str, Any]]:
        """Lists all checkpoints for a task ordered by step_index."""
        conn = self.get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT * FROM task_checkpoints
                WHERE task_id = ?
                ORDER BY step_index ASC, created_at ASC
                """,
                (task_id,),
            )
            return self.rows_to_dicts(cur.fetchall())
        finally:
            conn.close()

    # =========================================================================
    # Operations
    # =========================================================================

    def create_operation(
        self,
        task_id: str,
        step_id: str,
        op_type: str,
        target_system: str,
        operation_id: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Records an operation under a task step."""
        op_id = operation_id or f"op_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()
        params_json = json.dumps(parameters) if parameters is not None else None

        with self.write_transaction("create_operation") as cur:
            cur.execute(
                """
                INSERT INTO operations (
                    operation_id, task_id, step_id, op_type, target_system,
                    parameters, status, started_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'RUNNING', ?)
                """,
                (op_id, task_id, step_id, op_type, target_system, params_json, now),
            )
        return op_id

    def update_operation_status(
        self,
        operation_id: str,
        status: str,
        result_payload: Optional[Any] = None,
        error_message: Optional[str] = None,
    ) -> bool:
        """Updates operation status and records completion timestamp."""
        now = datetime.now(timezone.utc).isoformat()
        res_json = (
            json.dumps(result_payload)
            if result_payload is not None and not isinstance(result_payload, str)
            else result_payload
        )

        with self.write_transaction("update_operation_status") as cur:
            cur.execute(
                """
                UPDATE operations
                SET status = ?,
                    result_payload = COALESCE(?, result_payload),
                    error_message = COALESCE(?, error_message),
                    completed_at = CASE WHEN ? IN ('COMPLETED', 'FAILED', 'CANCELLED') THEN ? ELSE completed_at END
                WHERE operation_id = ?
                """,
                (status, res_json, error_message, status, now, operation_id),
            )
            return cur.rowcount > 0

    # =========================================================================
    # Assembly Graph & Node Checkpoint Management
    # =========================================================================

    def _ensure_assembly_tables(self, cur: sqlite3.Cursor) -> None:
        """Create assembly tables if they do not exist."""
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS assembly_nodes (
                task_id TEXT NOT NULL,
                node_id TEXT NOT NULL,
                parent_node_id TEXT,
                label TEXT,
                status TEXT NOT NULL DEFAULT 'PENDING',
                retry_count INTEGER NOT NULL DEFAULT 0,
                paradigm TEXT NOT NULL,
                sub_spec_json TEXT,
                attachment_json TEXT,
                PRIMARY KEY (task_id, node_id)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS assembly_graphs (
                task_id TEXT PRIMARY KEY,
                description TEXT,
                status TEXT NOT NULL DEFAULT 'PENDING',
                graph_json TEXT,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
            )
            """
        )

    def save_assembly_graph(self, graph_dict: Dict[str, Any]) -> None:
        """Persists the full assembly graph and each of its constituent nodes."""
        task_id = graph_dict["task_id"]
        desc = graph_dict.get("description", "")
        status = graph_dict.get("status", "PENDING")
        graph_json = json.dumps(graph_dict)

        with self.write_transaction("save_assembly_graph") as cur:
            self._ensure_assembly_tables(cur)
            cur.execute(
                """
                INSERT OR REPLACE INTO assembly_graphs (task_id, description, status, graph_json)
                VALUES (?, ?, ?, ?)
                """,
                (task_id, desc, status, graph_json),
            )

            # Flatten and upsert all nodes
            def _upsert_node(node: Dict[str, Any], parent_id: Optional[str] = None):
                nid = node["node_id"]
                lbl = node.get("label", nid)
                st = node.get("status", "PENDING")
                retries = int(node.get("retry_count", 0))
                paradigm = node.get("paradigm", "hard_surface_spec")
                sub_spec = json.dumps(node.get("sub_spec", {}))
                att = json.dumps(node.get("attachment", {}))

                cur.execute(
                    """
                    INSERT OR REPLACE INTO assembly_nodes (
                        task_id, node_id, parent_node_id, label, status,
                        retry_count, paradigm, sub_spec_json, attachment_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (task_id, nid, parent_id, lbl, st, retries, paradigm, sub_spec, att),
                )
                for child in node.get("children", []):
                    _upsert_node(child, parent_id=nid)

            root = graph_dict.get("root")
            if root:
                _upsert_node(root, None)

    def update_assembly_node_status(
        self,
        task_id: str,
        node_id: str,
        status: str,
        retry_count: Optional[int] = None,
    ) -> bool:
        """Update node execution status and optional retry count."""
        with self.write_transaction("update_assembly_node_status") as cur:
            self._ensure_assembly_tables(cur)
            if retry_count is not None:
                cur.execute(
                    """
                    UPDATE assembly_nodes
                    SET status = ?, retry_count = ?
                    WHERE task_id = ? AND node_id = ?
                    """,
                    (status, retry_count, task_id, node_id),
                )
            else:
                cur.execute(
                    """
                    UPDATE assembly_nodes
                    SET status = ?
                    WHERE task_id = ? AND node_id = ?
                    """,
                    (status, task_id, node_id),
                )
            return cur.rowcount > 0

    def get_assembly_graph_dict(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve stored assembly graph by task_id."""
        with self.get_connection() as conn:
            cur = conn.cursor()
            try:
                self._ensure_assembly_tables(cur)
                cur.execute("SELECT graph_json FROM assembly_graphs WHERE task_id = ?", (task_id,))
                row = cur.fetchone()
                if row and row["graph_json"]:
                    return json.loads(row["graph_json"])
            except Exception as e:
                logger.warning(f"Could not load assembly graph for task {task_id}: {e}")
            return None
