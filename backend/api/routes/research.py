import json
import logging
import os
import sqlite3
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from db.connections import get_operational_db, get_knowledge_db

logger = logging.getLogger(__name__)

router = APIRouter()


class ResearchStartRequest(BaseModel):
    question: str
    depth: Optional[str] = "deep"  # "quick" | "deep"


@router.post("/start")
@router.post("/start/")
async def start_research(body: ResearchStartRequest, request: Request):
    clean_q = body.question.strip()
    if not clean_q:
        raise HTTPException(status_code=400, detail="Research question cannot be empty")

    task_queue = getattr(request.app.state, "task_queue", None)
    if not task_queue:
        raise HTTPException(status_code=500, detail="Task queue is not initialized")

    task_id = task_queue.enqueue(
        workflow_type="RESEARCHER",
        title=f"Research: {clean_q[:60]}",
        input_payload={
            "question": clean_q,
            "depth": body.depth if body.depth in ("quick", "deep") else "deep",
        },
        priority=1,
    )

    logger.info(f"Enqueued Research task {task_id} for: {clean_q[:60]}")
    return {
        "status": "QUEUED",
        "task_id": task_id,
        "question": clean_q,
        "depth": body.depth,
    }


@router.get("/reports")
@router.get("/reports/")
async def list_research_reports(limit: int = Query(20, ge=1, le=100)):
    conn = get_operational_db()
    reports = []
    try:
        cur = conn.execute(
            """
            SELECT task_id, status, input_payload, created_at, updated_at, error_message
            FROM tasks
            WHERE workflow_type = 'RESEARCHER'
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = cur.fetchall()
        for r in rows:
            row_dict = dict(r)
            payload = {}
            if row_dict.get("input_payload"):
                try:
                    payload = json.loads(row_dict["input_payload"])
                except Exception:
                    payload = {}
            reports.append({
                "task_id": row_dict["task_id"],
                "question": payload.get("question", "Unknown Research Question"),
                "depth": payload.get("depth", "deep"),
                "status": row_dict["status"],
                "created_at": row_dict["created_at"],
                "completed_at": row_dict.get("updated_at") if row_dict.get("status") in ("COMPLETED", "FAILED") else None,
                "error": row_dict.get("error_message"),
            })
    finally:
        conn.close()

    return {"reports": reports, "count": len(reports)}


@router.get("/reports/{task_id}")
async def get_research_report(task_id: str):
    op_conn = get_operational_db()
    task = None
    try:
        cur = op_conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,))
        row = cur.fetchone()
        if row:
            task = dict(row)
            if task.get("input_payload"):
                try:
                    task["input_payload"] = json.loads(task["input_payload"])
                except Exception:
                    pass
    finally:
        op_conn.close()

    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    k_conn = get_knowledge_db()
    report_content = ""
    claims = []
    try:
        cur = k_conn.execute(
            """
            SELECT artifact_id, artifact_type, storage_path, metadata_json
            FROM artifacts
            WHERE task_id = ? AND artifact_type = 'FINAL_REPORT'
            ORDER BY created_at DESC LIMIT 1
            """,
            (task_id,),
        )
        art_row = cur.fetchone()
        if art_row:
            art = dict(art_row)
            path = art.get("storage_path")
            if path and os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    report_content = f.read()

        cur_claims = k_conn.execute(
            """
            SELECT claim_id, claim_text, source_uri, source_authority,
                   confidence_score, confidence_basis, retrieval_timestamp, domain
            FROM research_claims
            WHERE task_id = ?
            ORDER BY confidence_score DESC
            """,
            (task_id,),
        )
        claims = [dict(c) for c in cur_claims.fetchall()]
    finally:
        k_conn.close()

    return {
        "task_id": task_id,
        "question": task.get("input_payload", {}).get("question", ""),
        "status": task.get("status"),
        "created_at": task.get("created_at"),
        "completed_at": task.get("updated_at") if task.get("status") in ("COMPLETED", "FAILED") else None,
        "report_markdown": report_content,
        "claims": claims,
        "claims_count": len(claims),
    }


@router.get("/claims")
@router.get("/claims/")
async def list_research_claims(
    domain: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    conn = get_knowledge_db()
    claims = []
    try:
        query = "SELECT * FROM research_claims WHERE 1=1"
        params = []

        if domain:
            query += " AND domain = ?"
            params.append(domain)

        if search:
            query += " AND (claim_text LIKE ? OR source_uri LIKE ?)"
            params.append(f"%{search}%")
            params.append(f"%{search}%")

        query += " ORDER BY retrieval_timestamp DESC LIMIT ?"
        params.append(limit)

        cur = conn.execute(query, tuple(params))
        claims = [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()

    return {"claims": claims, "count": len(claims)}
