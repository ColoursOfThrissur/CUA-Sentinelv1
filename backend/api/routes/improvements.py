import json
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Request, HTTPException
from db.connections import get_operational_db

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("")
@router.get("/")
def list_improvements(status: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Returns improvement proposals drafted by ImprovementScout.
    Filter by status ('PENDING', 'APPROVED', 'REJECTED', 'APPLIED').
    """
    conn = get_operational_db()
    try:
        if status and status.upper() != "ALL":
            cur = conn.execute(
                "SELECT * FROM improvement_proposals WHERE status = ? ORDER BY created_at DESC LIMIT 100",
                (status.upper(),)
            )
        else:
            cur = conn.execute("SELECT * FROM improvement_proposals ORDER BY created_at DESC LIMIT 100")
        rows = [dict(r) for r in cur.fetchall()]
        for r in rows:
            if isinstance(r.get("affected_files"), str):
                try:
                    r["affected_files"] = json.loads(r["affected_files"])
                except Exception:
                    r["affected_files"] = [r["affected_files"]]
        return rows
    finally:
        conn.close()


@router.post("/{proposal_id}/approve")
def approve_improvement(proposal_id: str, request: Request) -> Dict[str, Any]:
    """
    Human-in-the-loop approval: Approving an ImprovementScout proposal
    converts it into a standard priority=2 CODE_REFACTOR task in TaskQueue.
    """
    conn = get_operational_db()
    try:
        cur = conn.execute("SELECT * FROM improvement_proposals WHERE proposal_id = ?", (proposal_id,))
        proposal = cur.fetchone()
        if not proposal:
            raise HTTPException(status_code=404, detail="Improvement proposal not found")

        proposal_dict = dict(proposal)
        if proposal_dict["status"] == "APPROVED":
            return {"status": "ALREADY_APPROVED", "proposal_id": proposal_id}

        # Fetch project target_path
        proj_cur = conn.execute(
            "SELECT target_path FROM created_projects WHERE project_id = ?",
            (proposal_dict["project_id"],)
        )
        proj = proj_cur.fetchone()
        target_path = proj["target_path"] if proj else None

        now_iso = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE improvement_proposals SET status = 'APPROVED', reviewed_at = ? WHERE proposal_id = ?",
            (now_iso, proposal_id),
        )
        conn.commit()

        # Enqueue as CODE_REFACTOR task
        queue = getattr(request.app.state, "task_queue", None)
        enqueued_task_id = None
        if queue and target_path:
            goal_instruction = (
                f"Apply Approved Improvement Proposal: {proposal_dict['title']}\n\n"
                f"Rationale:\n{proposal_dict['rationale']}\n\n"
                f"Suggested Changes:\n{proposal_dict.get('suggested_changes', 'Implement architectural and safety improvements.')}"
            )
            enqueued_task_id = queue.enqueue(
                workflow_type="CODE_REFACTOR",
                title=f"Improvement: {proposal_dict['title']}",
                priority=2,
                input_payload={
                    "project_path": target_path,
                    "goal_instruction": goal_instruction,
                    "proposal_id": proposal_id,
                },
                description=f"Automated refactor for approved proposal {proposal_id}"
            )

        logger.info(f"Improvement proposal {proposal_id} approved. Enqueued task: {enqueued_task_id}")
        return {
            "status": "APPROVED",
            "proposal_id": proposal_id,
            "enqueued_task_id": enqueued_task_id,
        }
    finally:
        conn.close()


@router.post("/{proposal_id}/reject")
def reject_improvement(proposal_id: str) -> Dict[str, Any]:
    """
    Rejects an improvement proposal, removing it from pending queues.
    """
    conn = get_operational_db()
    try:
        now_iso = datetime.now(timezone.utc).isoformat()
        res = conn.execute(
            "UPDATE improvement_proposals SET status = 'REJECTED', reviewed_at = ? WHERE proposal_id = ?",
            (now_iso, proposal_id),
        )
        conn.commit()
        if res.rowcount == 0:
            raise HTTPException(status_code=404, detail="Improvement proposal not found")
        logger.info(f"Improvement proposal {proposal_id} marked REJECTED.")
        return {"status": "REJECTED", "proposal_id": proposal_id}
    finally:
        conn.close()
