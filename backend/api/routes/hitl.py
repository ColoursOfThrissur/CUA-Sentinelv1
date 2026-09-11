from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from db.connections import get_operational_db
from core.state_manager import JSON_FIELDS, parse_json_fields
from api.websocket import broadcast_hitl_update

router = APIRouter()


class HITLDecision(BaseModel):
    approved: bool
    resolved_by: str = "user"


@router.get("/pending")
async def get_pending():
    conn = get_operational_db()
    try:
        rows = conn.execute(
            "SELECT * FROM hitl_pending WHERE status = 'PENDING' ORDER BY created_at DESC"
        ).fetchall()
        return [parse_json_fields(r, JSON_FIELDS["hitl_pending"]) for r in rows]
    finally:
        conn.close()


@router.post("/{approval_id}/resolve")
async def resolve_hitl(approval_id: str, decision: HITLDecision, request: Request):
    success = request.app.state.governance.resolve_hitl(
        approval_id, decision.approved, decision.resolved_by
    )
    if not success:
        raise HTTPException(400, "Approval not found, already resolved, or expired")

    # Push updated pending list to all connected clients
    conn = get_operational_db()
    try:
        rows = conn.execute(
            "SELECT * FROM hitl_pending WHERE status = 'PENDING' ORDER BY created_at DESC"
        ).fetchall()
        pending = [parse_json_fields(r, JSON_FIELDS["hitl_pending"]) for r in rows]
    finally:
        conn.close()
    await broadcast_hitl_update(pending)

    return {"approval_id": approval_id, "approved": decision.approved}
