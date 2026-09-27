from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

router = APIRouter()


class HistoryTurn(BaseModel):
    role: str = Field(..., pattern=r"^(user|assistant|system)$")
    content: str = Field(..., max_length=16000)


class ChatRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=8000)
    system_prompt: Optional[str] = None  # Dropped by server; client cannot override system rules
    context_budget: int = Field(8192, ge=2048, le=16384)
    use_web: bool = False
    target_app: Optional[str] = None  # Specific connected MCP app to target
    history: Optional[List[HistoryTurn]] = None


@router.post("/")
async def chat(req: ChatRequest, request: Request):
    """
    Universal Endpoint — Priority 0 direct chat.
    Enqueues at Priority 0 for immediate execution with multi-turn conversation memory.
    """
    cleaned_prompt = req.prompt.strip()
    from core.router import IntentRouter
    detected = IntentRouter.classify_intent(cleaned_prompt)
    workflow_type = "CUA" if detected == "CUA" else "ENDPOINT"

    history_payload = []
    if req.history:
        for turn in req.history:
            history_payload.append(turn.model_dump() if hasattr(turn, "model_dump") else turn.dict())

    task_id = request.app.state.task_queue.enqueue(
        workflow_type=workflow_type,
        title=f"Chat: {cleaned_prompt[:60]}",
        input_payload={
            "prompt": cleaned_prompt,
            "use_web": req.use_web,
            "target_app": req.target_app,
            "history": history_payload,
        },
        priority=0,
        context_budget=req.context_budget,
    )
    return {"task_id": task_id, "status": "QUEUED", "priority": 0}


class ApproveSpecRequest(BaseModel):
    build_id: str = Field(..., min_length=1, max_length=64)


@router.post("/approve-spec")
async def approve_spec(req: ApproveSpecRequest):
    """
    1-click approval for a pending 3D build spec to persist it to the library.
    """
    from core.spec3d.pipeline import Spec3DPipeline
    result = await Spec3DPipeline.process_save_approved(req.build_id.strip())
    return result

