import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.gmail_triage import GmailTriageEngine

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/gmail-triage", tags=["gmail-triage"])
triage_engine = GmailTriageEngine()


@router.get("/feed")
def get_action_feed(category: Optional[str] = None) -> List[Dict[str, Any]]:
    return triage_engine.get_feed(category=category)


@router.post("/scan")
def trigger_scan() -> Dict[str, Any]:
    items = triage_engine.scan_inbox()
    return {"status": "SUCCESS", "scanned_items": len(items), "details": items}
