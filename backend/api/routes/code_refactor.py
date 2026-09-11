"""
API Router for Autonomous Code Refactoring Engine in CUA-Sentinel.
"""

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from agents.code_refactor_agent import CodeRefactorAgent
from core.project_backup import project_backup_manager

router = APIRouter()

class ScanRequest(BaseModel):
    project_path: str

class StartRefactorRequest(BaseModel):
    project_path: str
    goal_instruction: Optional[str] = "Analyze and improve backend and frontend code quality."
    approved_features: Optional[List[str]] = []
    blueprint_content: Optional[str] = None
    blueprint_filename: Optional[str] = None

class RollbackRequest(BaseModel):
    project_path: str
    task_id: str

@router.post("/scan")
async def scan_repository(req: ScanRequest):
    """
    Scans a local project directory, builds Repository AST Map, and returns initial Code Health Score (0-100).
    """
    agent = CodeRefactorAgent(None, None, None)
    res = agent.scan_repository(req.project_path)
    if "error" in res:
        raise HTTPException(status_code=400, detail=res["error"])
    return res

@router.post("/start")
async def start_refactoring(req: StartRefactorRequest, request: Request):
    """
    Enqueues an autonomous code refactoring run in the task queue.
    """
    task_id = request.app.state.task_queue.enqueue(
        workflow_type="REFACTOR",
        title=f"Code Refactor: {req.project_path[:40]}",
        input_payload={
            "project_path": req.project_path,
            "goal_instruction": req.goal_instruction,
            "approved_features": req.approved_features,
            "blueprint_content": req.blueprint_content,
            "blueprint_filename": req.blueprint_filename,
        },
        priority=2,
        context_budget=16384,
    )
    return {"task_id": task_id, "status": "QUEUED", "project_path": req.project_path}

class CreateScratchRequest(BaseModel):
    project_name: str
    target_path: str
    tech_stack: Optional[str] = "FastAPI + React"
    ui_style: Optional[str] = "Glassmorphism"
    description: Optional[str] = ""
    blueprint_content: Optional[str] = None
    blueprint_filename: Optional[str] = None

@router.post("/create-scratch")
async def create_project_from_scratch(req: CreateScratchRequest, request: Request):
    """
    Creates a new project from scratch on target storage drive with UI/UX Pro Max design tokens,
    and enqueues an autonomous local LLM generation task to build full complex solution modules.
    """
    agent = CodeRefactorAgent(None, None, None)
    try:
        res = agent.create_project_from_scratch(
            project_name=req.project_name,
            target_path=req.target_path,
            tech_stack=req.tech_stack or "FastAPI + React",
            ui_style=req.ui_style or "Glassmorphism",
            description=req.description or "",
            blueprint_content=req.blueprint_content or "",
            blueprint_filename=req.blueprint_filename or ""
        )

        # Automatically enqueue autonomous local LLM agent task if blueprint directive or description provided
        task_id = None
        if hasattr(request.app.state, "task_queue") and request.app.state.task_queue:
            task_id = request.app.state.task_queue.enqueue(
                workflow_type="SCAFFOLDER",
                title=f"Autonomous Scaffold: {req.project_name}",
                input_payload={
                    "project_path": req.target_path,
                    "project_name": req.project_name,
                    "goal_instruction": req.description or f"Implement full architecture for {req.project_name}",
                    "blueprint_content": req.blueprint_content,
                    "blueprint_filename": req.blueprint_filename,
                },
                priority=2,
                context_budget=16384,
            )
            res["task_id"] = task_id
            res["generation_status"] = "QUEUED_FOR_LLM_SYNTHESIS"

        return res
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

class LaunchPreviewRequest(BaseModel):
    project_path: str

@router.post("/launch-preview")
async def launch_live_preview(req: LaunchPreviewRequest):
    """
    Allocates an open port, spawns background app dev server, and probes /health status.
    """
    from core.sandbox_runner import sandbox_runner
    res = sandbox_runner.launch_app_preview(req.project_path)
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error", "Launch failed"))
    return res

@router.post("/rollback")
async def rollback_changes(req: RollbackRequest):
    """
    Restores pre-refactor backup snapshot (1-click Rollback).
    """
    success = project_backup_manager.restore_snapshot(req.project_path, req.task_id)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to restore backup snapshot.")
    return {"status": "RESTORED", "message": f"Successfully rolled back changes for task {req.task_id}"}

class InstallDepsRequest(BaseModel):
    project_path: str

@router.post("/install-dependencies")
async def install_dependencies(req: InstallDepsRequest):
    """
    Scans project for missing npm/Python imports & manifest declarations, auto-installs them on demand.
    """
    from core.environment_engine import environment_engine
    try:
        res = environment_engine.scan_and_install_dependencies(req.project_path)
        return res
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
