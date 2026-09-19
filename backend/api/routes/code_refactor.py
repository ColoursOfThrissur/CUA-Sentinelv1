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

@router.post("/solution-context")
async def get_solution_context(req: ScanRequest):
    """
    Parses solution repository and returns File Responsibility Index and Solution Context Map.
    """
    from core.solution_context import solution_context_engine
    res = solution_context_engine.build_solution_map(req.project_path)
    if "error" in res:
        raise HTTPException(status_code=400, detail=res["error"])
    return res

@router.post("/dual-diagnostics")
async def run_dual_diagnostics(req: ScanRequest):
    """
    Runs simultaneous pre-flight diagnostic probes for Backend (Python/FastAPI) and Frontend (React/Vite).
    """
    from core.project_health_daemon import project_health_daemon
    return project_health_daemon.audit_dual_stack_health(req.project_path)

class AutoHealTriggerRequest(BaseModel):
    project_path: str
    error_context: str
    source: Optional[str] = "UI_MANUAL_TRIGGER"

@router.post("/auto-heal-trigger")
async def trigger_auto_heal(req: AutoHealTriggerRequest):
    """
    Triggers zero-touch auto-healing or package auto-installation for a project.
    """
    from core.project_health_daemon import project_health_daemon
    res = await project_health_daemon.trigger_autonomous_repair(req.project_path, req.error_context, source=req.source or "UI_TRIGGER")
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

        # If the scaffolder's inline env setup didn't fully complete (e.g. slow npm),
        # trigger a second pass in a background thread to guarantee node_modules + .venv
        import threading
        def _bg_env_setup(target_path: str):
            try:
                from core.environment_engine import environment_engine
                environment_engine.scan_and_install_dependencies(target_path)
            except Exception as bg_err:
                import logging
                logging.getLogger(__name__).warning(f"Background env setup notice for {target_path}: {bg_err}")

        threading.Thread(target=_bg_env_setup, args=(req.target_path,), daemon=True).start()

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

class DiagnoseFileRequest(BaseModel):
    project_path: str
    file_path: str

@router.post("/diagnose-file")
async def diagnose_file(req: DiagnoseFileRequest, request: Request):
    """
    Diagnoses syntax/TypeScript/Python errors in a specific selected file and applies 1-click AI repair.
    """
    agent = CodeRefactorAgent(
        model_manager=getattr(request.app.state, "model_manager", None),
        governance=getattr(request.app.state, "governance", None),
        config={}
    )
    res = await agent.diagnose_and_fix_file(req.project_path, req.file_path)
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error", "Diagnosis failed"))
    return res

class ClearCooloffRequest(BaseModel):
    project_id: str

@router.post("/health-daemon/run-now")
async def run_health_daemon_now(request: Request):
    """
    Triggers an immediate 24/7 Autonomous Project Health Daemon audit scan across all registered solutions.
    """
    from core.project_health_daemon import project_health_daemon
    try:
        project_health_daemon.model_manager = getattr(request.app.state, "model_manager", None)
        res = await project_health_daemon.audit_all_projects(force_run=True)
        return res
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/health-daemon/logs")
async def get_health_daemon_logs(limit: int = 50):
    """
    Retrieves recent autonomous health audit logs, findings, and auto-repair/rollback history.
    """
    from core.project_health_daemon import project_health_daemon
    try:
        logs = project_health_daemon.fetch_daemon_logs(limit=limit)
        return {"logs": logs}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/health-daemon/clear-cooloff")
async def clear_health_daemon_cooloff(req: ClearCooloffRequest):
    """
    Clears the 24-hour cool-off suppression for a project so auto-repair can be retried immediately.
    """
    from core.project_health_daemon import project_health_daemon
    success = project_health_daemon.clear_cooloff(req.project_id)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to clear project cool-off.")
    return {"status": "SUCCESS", "message": f"Cleared cool-off for project '{req.project_id}'"}


class ValidateAlignmentRequest(BaseModel):
    project_path: str
    goal_instruction: Optional[str] = ""
    auto_remediate: Optional[bool] = False


@router.post("/validate-alignment")
async def validate_solution_alignment(req: ValidateAlignmentRequest):
    """
    Validates solution semantic goal coverage, cross-layer API contract sync,
    and component mounting integrity.
    """
    from core.alignment_validator import alignment_validator
    try:
        res = alignment_validator.validate_solution(
            req.project_path,
            req.goal_instruction or "Verify project functionality",
            [],
            auto_remediate=req.auto_remediate or False
        )
        return res
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/auto-remediate-alignment")
async def remediate_solution_alignment(req: ValidateAlignmentRequest):
    """
    Auto-remediates contract drift by synthesizing missing FastAPI routes and mounting orphan components.
    """
    from core.alignment_validator import alignment_validator
    try:
        res = alignment_validator.validate_solution(
            req.project_path,
            req.goal_instruction or "Auto-remediate project contracts",
            [],
            auto_remediate=True
        )
        return res
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


