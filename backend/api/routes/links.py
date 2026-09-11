import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel

from tools.link_manager import LinkManager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/links", tags=["links"])
link_manager = LinkManager()


class LinkPayload(BaseModel):
    url: str
    title: Optional[str] = None


@router.get("/")
def list_links(search: Optional[str] = None) -> List[Dict[str, Any]]:
    return link_manager.get_links(search=search)


@router.post("/")
async def add_link(payload: LinkPayload, background_tasks: BackgroundTasks) -> Dict[str, Any]:
    link = link_manager.add_link(url=payload.url, title=payload.title)
    # Trigger crawling & RAG indexing in background
    background_tasks.add_task(link_manager.crawl_and_process, link["link_id"])
    return {"status": "QUEUED_FOR_CRAWL", "link": link}


@router.post("/{link_id}/crawl")
async def crawl_link(link_id: str) -> Dict[str, Any]:
    res = await link_manager.crawl_and_process(link_id)
    if res.get("status") == "FAILED":
        raise HTTPException(status_code=400, detail=res.get("error", "Crawl failed"))
    return res
