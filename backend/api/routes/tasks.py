import json
import logging

logger = logging.getLogger(__name__)
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from typing import Optional
from db.connections import get_operational_db
from core.state_manager import JSON_FIELDS, parse_json_fields

router = APIRouter()


class CreateTaskRequest(BaseModel):
    workflow_type: str
    title: str
    input_payload: dict
    priority: int = 2
    context_budget: int = 8192
    description: Optional[str] = None


def _delete_tasks(conn, task_ids: list[str]) -> int:
    if not task_ids:
        return 0

    placeholders = ",".join("?" for _ in task_ids)

    # Unlink models_registry busy_task_id
    try:
        conn.execute(
            f"UPDATE models_registry SET busy_task_id = NULL, current_state = 'READY' WHERE busy_task_id IN ({placeholders})",
            task_ids,
        )
    except Exception as e:
        logger.warning(f"Failed to clear models_registry for task: {e}")

    # Unlink parent_task_id in child tasks
    try:
        conn.execute(
            f"UPDATE tasks SET parent_task_id = NULL WHERE parent_task_id IN ({placeholders})",
            task_ids,
        )
    except Exception as e:
        logger.warning(f"Failed to clear parent_task_id: {e}")

    # Clear operations & operation_attempts
    try:
        operation_rows = conn.execute(
            f"SELECT operation_id FROM operations WHERE task_id IN ({placeholders})",
            task_ids,
        ).fetchall()
        operation_ids = [r["operation_id"] for r in operation_rows]
        if operation_ids:
            operation_placeholders = ",".join("?" for _ in operation_ids)
            conn.execute(
                f"DELETE FROM operation_attempts WHERE operation_id IN ({operation_placeholders})",
                operation_ids,
            )
            conn.execute(
                f"DELETE FROM hitl_pending WHERE operation_id IN ({operation_placeholders})",
                operation_ids,
            )
            conn.execute(
                f"DELETE FROM operations WHERE operation_id IN ({operation_placeholders})",
                operation_ids,
            )
    except Exception as e:
        logger.warning(f"Failed to clear operations and attempts: {e}")

    # Delete hitl_pending, leases, steps
    try:
        conn.execute(f"DELETE FROM hitl_pending WHERE task_id IN ({placeholders})", task_ids)
    except Exception as e:
        logger.warning(f"Failed to delete hitl_pending: {e}")
    try:
        conn.execute(f"DELETE FROM task_leases WHERE task_id IN ({placeholders})", task_ids)
    except Exception as e:
        logger.warning(f"Failed to delete task_leases: {e}")
    try:
        conn.execute(f"DELETE FROM task_steps WHERE task_id IN ({placeholders})", task_ids)
    except Exception as e:
        logger.warning(f"Failed to delete task_steps: {e}")

    conn.execute(f"DELETE FROM tasks WHERE task_id IN ({placeholders})", task_ids)
    return len(task_ids)


@router.post("/")
async def create_task(req: CreateTaskRequest, request: Request):
    valid_types = [
        "RESEARCHER", "SYNTHESIZER", "SCAFFOLDER",
        "TESTER", "REVIEWER", "REFACTOR", "SECOND_BRAIN", "SYNTHETIC_DATA"
    ]
    if req.workflow_type not in valid_types:
        raise HTTPException(400, f"Invalid workflow_type. Must be one of: {valid_types}")

    task_id = request.app.state.task_queue.enqueue(
        workflow_type=req.workflow_type,
        title=req.title,
        input_payload=req.input_payload,
        priority=req.priority,
        context_budget=req.context_budget,
        description=req.description,
    )
    return {"task_id": task_id, "status": "QUEUED"}


@router.get("/")
async def list_tasks(status: Optional[str] = None, limit: int = 50):
    conn = get_operational_db()
    try:
        if status:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [parse_json_fields(r, JSON_FIELDS["tasks"]) for r in rows]
    finally:
        conn.close()


@router.delete("/chat-history")
async def clear_chat_history():
    conn = get_operational_db()
    try:
        rows = conn.execute(
            """
            SELECT task_id FROM tasks
            WHERE workflow_type = 'ENDPOINT'
              AND status NOT IN ('RUNNING', 'PREEMPTED')
            """
        ).fetchall()
        task_ids = [r["task_id"] for r in rows]
        deleted = _delete_tasks(conn, task_ids)
        conn.commit()
        return {"deleted": deleted}
    finally:
        conn.close()


@router.delete("/chat-history/{task_id}")
async def delete_chat_history_task(task_id: str):
    conn = get_operational_db()
    try:
        row = conn.execute(
            """
            SELECT status FROM tasks
            WHERE task_id = ? AND workflow_type = 'ENDPOINT'
            """,
            (task_id,),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Chat task not found")
        if row["status"] in ("RUNNING", "PREEMPTED"):
            raise HTTPException(400, "Running chat tasks cannot be deleted yet")

        deleted = _delete_tasks(conn, [task_id])
        conn.commit()
        return {"task_id": task_id, "deleted": deleted}
    finally:
        conn.close()


@router.get("/{task_id}")
async def get_task(task_id: str):
    conn = get_operational_db()
    try:
        task = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
        if not task:
            raise HTTPException(404, "Task not found")
        steps = conn.execute(
            "SELECT * FROM task_steps WHERE task_id = ? ORDER BY step_order", (task_id,)
        ).fetchall()
        return {
            "task": parse_json_fields(task, JSON_FIELDS["tasks"]),
            "steps": [parse_json_fields(s, JSON_FIELDS["task_steps"]) for s in steps],
        }
    finally:
        conn.close()


@router.post("/{task_id}/cancel")
async def cancel_task(task_id: str, request: Request):
    from datetime import datetime, timezone
    conn = get_operational_db()
    try:
        now = datetime.now(timezone.utc).isoformat()
        row = conn.execute("SELECT status FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Task not found")

        if row["status"] in ("CANCEL_REQUESTED", "CANCELLED", "COMPLETED", "FAILED"):
            return {"task_id": task_id, "status": row["status"]}

        conn.execute(
            """
            UPDATE tasks SET status = 'CANCEL_REQUESTED',
                cancel_requested_at = ?, cancel_requested_by = 'user'
            WHERE task_id = ? AND status IN ('QUEUED', 'RUNNING', 'PREEMPTED')
            """,
            (now, task_id),
        )
        conn.commit()
        return {"task_id": task_id, "status": "CANCEL_REQUESTED"}
    finally:
        conn.close()


@router.delete("/{task_id}")
async def delete_task(task_id: str):
    """
    Deletes/removes a task and its associated steps, operations, and leases from the queue database.
    If the task is currently RUNNING or QUEUED, cancels it first before deletion.
    """
    conn = get_operational_db()
    try:
        task = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
        if not task:
            raise HTTPException(404, "Task not found")

        status = task["status"]
        if status in ("RUNNING", "PREEMPTED", "QUEUED"):
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                "UPDATE tasks SET status = 'CANCEL_REQUESTED', cancel_requested_at = ?, cancel_requested_by = 'user' WHERE task_id = ?",
                (now, task_id),
            )
            conn.commit()

        deleted = _delete_tasks(conn, [task_id])
        conn.commit()
        return {"task_id": task_id, "deleted": deleted, "success": True}
    finally:
        conn.close()


@router.get("/{task_id}/report")
async def download_task_report(task_id: str):
    """
    Returns a downloadable Markdown research report file for a given task.
    """
    from fastapi.responses import Response
    from db.connections import get_knowledge_db
    from core.artifacts import ArtifactStore

    conn = get_operational_db()
    try:
        task = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
        if not task:
            raise HTTPException(404, "Task not found")
        task_dict = parse_json_fields(task, JSON_FIELDS["tasks"])
        result_payload = task_dict.get("result_payload") or {}
        answer = result_payload.get("answer") or result_payload.get("response") or task_dict.get("description") or ""

        k_conn = get_knowledge_db()
        artifact_row = k_conn.execute(
            "SELECT artifact_id FROM artifacts WHERE task_id = ? AND artifact_type IN ('FINAL_REPORT', 'RAW_OUTPUT') ORDER BY created_at DESC LIMIT 1",
            (task_id,),
        ).fetchone()
        k_conn.close()

        if artifact_row:
            try:
                content = ArtifactStore().read(artifact_row["artifact_id"])
            except Exception:
                content = f"# Research Report: {task_dict.get('title')}\n\n{answer}"
        else:
            content = f"# Research Report: {task_dict.get('title')}\n\nTask ID: {task_id}\nCreated At: {task_dict.get('created_at')}\n\n## Content\n\n{answer}"

        filename = f"sentinel_report_{task_id[:8]}.md"
        return Response(
            content=content,
            media_type="text/markdown",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    finally:
        conn.close()
