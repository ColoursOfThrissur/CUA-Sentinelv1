from typing import List, Optional
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, Field
from db.connections import get_operational_db
from core.state_manager import JSON_FIELDS, parse_json_fields
from api.websocket import broadcast_hitl_update

router = APIRouter()


class HITLDecision(BaseModel):
    approved: bool
    resolved_by: str = "user"


class BatchHITLDecision(BaseModel):
    approval_ids: Optional[List[str]] = Field(default_factory=list)
    approved: bool = True
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


@router.post("/resolve-all")
async def resolve_all_hitl(decision: BatchHITLDecision, request: Request):
    """
    1-Click batch approval / rejection for multiple or all pending HITL items.
    If approval_ids is empty or not provided, resolves ALL currently pending requests.
    """
    conn = get_operational_db()
    try:
        if decision.approval_ids:
            placeholders = ",".join("?" for _ in decision.approval_ids)
            rows = conn.execute(
                f"SELECT approval_id FROM hitl_pending WHERE status = 'PENDING' AND approval_id IN ({placeholders})",
                decision.approval_ids,
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT approval_id FROM hitl_pending WHERE status = 'PENDING'"
            ).fetchall()
        target_ids = [r["approval_id"] for r in rows]
    finally:
        conn.close()

    gov = getattr(request.app.state, "governance", None)
    resolved_count = 0
    if gov:
        for aid in target_ids:
            try:
                if gov.resolve_hitl(aid, decision.approved, decision.resolved_by):
                    resolved_count += 1
            except Exception:
                pass

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

    return {"resolved_count": resolved_count, "approved": decision.approved, "remaining": len(pending)}


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
