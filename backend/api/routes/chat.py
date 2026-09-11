from fastapi import APIRouter, Request
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

router = APIRouter()


class ChatRequest(BaseModel):
    prompt: str
    system_prompt: Optional[str] = None
    context_budget: int = 8192
    use_web: bool = False
    history: Optional[List[Dict[str, Any]]] = None


@router.post("/")
async def chat(req: ChatRequest, request: Request):
    """
    Universal Endpoint — Priority 0 direct chat.
    Bypasses the queue for immediate response with multi-turn conversation memory.
    """
    task_id = request.app.state.task_queue.enqueue(
        workflow_type="ENDPOINT",
        title=f"Chat: {req.prompt[:60]}",
        input_payload={
            "prompt": req.prompt,
            "system_prompt": req.system_prompt,
            "use_web": req.use_web,
            "history": req.history or [],
        },
        priority=0,
        context_budget=req.context_budget,
    )
    return {"task_id": task_id, "status": "QUEUED", "priority": 0}
