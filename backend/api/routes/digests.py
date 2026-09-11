from fastapi import APIRouter, HTTPException, Request
from typing import Optional, List, Dict, Any

router = APIRouter()


@router.get("/latest")
async def get_latest_digest(request: Request):
    """
    Retrieves the most recent Daily Operations Digest.
    """
    from core.digest_engine import DigestEngine
    engine = DigestEngine()
    digest = engine.get_latest_digest()
    if not digest:
        return {"digest": None, "message": "No digests generated yet. Click 'Generate New Digest' to create one."}
    return {"digest": digest}


@router.post("/generate")
async def generate_digest(request: Request):
    """
    Triggers an on-demand Daily Operations Digest generation.
    """
    from core.digest_engine import DigestEngine
    engine = DigestEngine()
    digest = await engine.generate_digest()
    return {"status": "SUCCESS", "digest": digest}


@router.get("/history")
async def list_digests(request: Request, limit: int = 10):
    """
    Lists historical daily digests.
    """
    from core.digest_engine import DigestEngine
    engine = DigestEngine()
    return {"digests": engine.list_digests(limit=limit)}
