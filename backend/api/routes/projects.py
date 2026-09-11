"""
API Router for Projects Registry & Live App Manager Hub in CUA-Sentinel.
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

try:
    from core.projects_manager import projects_manager
except ModuleNotFoundError:
    from backend.core.projects_manager import projects_manager

router = APIRouter()

class RegisterProjectRequest(BaseModel):
    project_name: str
    target_path: str
    tech_stack: str
    ui_style: Optional[str] = "Glassmorphism"
    blueprint_filename: Optional[str] = None
    health_score: Optional[int] = 100
    security_score: Optional[int] = 100

class ExportZipRequest(BaseModel):
    export_dir: Optional[str] = None

@router.get("/list")
async def list_projects():
    """
    Returns all registered solutions with live status, file count, and disk size.
    """
    return {"projects": projects_manager.list_projects()}

@router.post("/register")
async def register_project(req: RegisterProjectRequest):
    """
    Registers a new or existing project into the solution hub database.
    """
    try:
        project = projects_manager.register_project(
            project_name=req.project_name,
            target_path=req.target_path,
            tech_stack=req.tech_stack,
            ui_style=req.ui_style or "Glassmorphism",
            blueprint_filename=req.blueprint_filename,
            health_score=req.health_score or 100,
            security_score=req.security_score or 100
        )
        return {"success": True, "project": project}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/{project_id}")
async def get_project(project_id: str):
    """
    Gets details for a single registered project.
    """
    project = projects_manager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found.")
    return project

@router.post("/{project_id}/start-server")
async def start_server(project_id: str):
    """
    Starts background dev server for the given project on an allocated port.
    """
    res = projects_manager.start_project_server(project_id)
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error", "Failed to start server"))
    return res

@router.post("/{project_id}/stop-server")
async def stop_server(project_id: str):
    """
    Stops running server process for the given project.
    """
    res = projects_manager.stop_project_server(project_id)
    return res

@router.get("/{project_id}/logs")
async def get_logs(project_id: str, tail: int = Query(default=100, ge=1, le=500)):
    """
    Returns recent stdout/stderr terminal output logs for the given project.
    """
    logs = projects_manager.get_project_logs(project_id, tail=tail)
    return {"project_id": project_id, "logs": logs, "count": len(logs)}

@router.post("/{project_id}/export-zip")
async def export_zip(project_id: str, req: Optional[ExportZipRequest] = None):
    """
    Bundles project files into a downloadable zip archive.
    """
    export_dir = req.export_dir if req else None
    res = projects_manager.export_project_zip(project_id, export_dir=export_dir)
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error", "Failed to export zip"))
    return res

from fastapi import Request
import os

@router.post("/{project_id}/fulfill-spec")
async def fulfill_spec(project_id: str, request: Request):
    """
    Enqueues an autonomous local LLM agent task to read ARCHITECTURE_SPEC.md and fulfill/synthesize the solution.
    """
    project = projects_manager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found.")

    target_path = project["target_path"]
    spec_path = os.path.join(target_path, "ARCHITECTURE_SPEC.md")
    spec_content = ""
    if os.path.exists(spec_path):
        try:
            with open(spec_path, "r", encoding="utf-8") as f:
                spec_content = f.read()
        except Exception:
            pass

    task_id = None
    if hasattr(request.app.state, "task_queue") and request.app.state.task_queue:
        task_id = request.app.state.task_queue.enqueue(
            workflow_type="SCAFFOLDER",
            title=f"Fulfill Spec: {project['project_name']}",
            input_payload={
                "project_path": target_path,
                "project_name": project["project_name"],
                "goal_instruction": f"Synthesize and fulfill full application architecture for {project['project_name']} based on ARCHITECTURE_SPEC.md",
                "blueprint_content": spec_content,
                "blueprint_filename": "ARCHITECTURE_SPEC.md" if spec_content else None,
            },
            priority=2,
            context_budget=16384,
        )

    return {
        "success": True,
        "project_id": project_id,
        "task_id": task_id,
        "message": f"Autonomous AI Agent task enqueued ({task_id}) to fulfill specification for '{project['project_name']}'!"
    }

@router.delete("/{project_id}")
async def delete_project(project_id: str, purge_files: bool = Query(default=False)):
    """
    Unregisters project and optionally purges files on non-OS storage drives (D:\\, G:\\).
    """
    res = projects_manager.delete_project(project_id, purge_files=purge_files)
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error", "Failed to delete project"))
    return res

@router.post("/{project_id}/repair-env")
async def repair_environment(project_id: str, repair_type: str = Query(default="all")):
    """
    Triggers 1-click environment repair (npm clean install, AST import scan, auto-install missing packages).
    """
    res = projects_manager.repair_project_environment(project_id, repair_type=repair_type)
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error", "Environment repair failed"))
    return res

@router.get("/{project_id}/tree")
async def get_project_tree(project_id: str):
    """
    Returns hierarchical file tree structure for project workspace.
    """
    res = projects_manager.get_project_file_tree(project_id)
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error", "Failed to load file tree"))
    return res

@router.get("/{project_id}/file")
async def read_project_file(project_id: str, relative_path: str = Query(...)):
    """
    Reads content of a single file in project workspace.
    """
    res = projects_manager.read_project_file(project_id, relative_path)
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error", "Failed to read file"))
    return res

class WriteFileRequest(BaseModel):
    relative_path: str
    content: str

@router.post("/{project_id}/file")
async def write_project_file(project_id: str, req: WriteFileRequest):
    """
    Writes/edits a single file in project workspace.
    """
    res = projects_manager.write_project_file(project_id, req.relative_path, req.content)
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error", "Failed to write file"))
    return res

class InContextPromptRequest(BaseModel):
    prompt: str
    target_file: Optional[str] = None

@router.post("/{project_id}/prompt")
async def handle_in_context_prompt(project_id: str, req: InContextPromptRequest, request: Request):
    """
    Enqueues an in-context AI task to modify project code based on user prompt.
    """
    project = projects_manager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found.")

    target_path = project["target_path"]
    task_id = None
    if hasattr(request.app.state, "task_queue") and request.app.state.task_queue:
        task_id = request.app.state.task_queue.enqueue(
            workflow_type="REFACTOR",
            title=f"In-Context Edit: {project['project_name']}",
            input_payload={
                "project_path": target_path,
                "project_name": project["project_name"],
                "goal_instruction": req.prompt,
                "target_file": req.target_file
            },
            priority=2,
            context_budget=16384,
        )

    return {
        "success": True,
        "project_id": project_id,
        "task_id": task_id,
        "message": f"In-context AI Developer task enqueued ({task_id}) for '{project['project_name']}'!"
    }
