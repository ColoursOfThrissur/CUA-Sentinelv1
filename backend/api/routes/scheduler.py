from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

router = APIRouter()


class ScheduleRequest(BaseModel):
    name: str
    time_offset: str  # e.g., '10s', '15m', '1h', '1d'
    prompt: str
    workflow_type: Optional[str] = "ENDPOINT"


@router.get("/jobs")
async def list_scheduled_jobs(request: Request):
    """
    Lists all scheduled jobs and reminders.
    """
    scheduler = getattr(request.app.state, "scheduler_engine", None)
    if not scheduler:
        raise HTTPException(status_code=500, detail="SchedulerEngine is not initialized")
    return {"jobs": scheduler.list_jobs()}


@router.post("/jobs")
async def create_scheduled_job(req: ScheduleRequest, request: Request):
    """
    Schedules a new reminder or timer job.
    """
    scheduler = getattr(request.app.state, "scheduler_engine", None)
    if not scheduler:
        raise HTTPException(status_code=500, detail="SchedulerEngine is not initialized")

    job = scheduler.add_reminder(
        name=req.name,
        time_str=req.time_offset,
        prompt=req.prompt,
        workflow_type=req.workflow_type or "ENDPOINT"
    )

    if not job:
        raise HTTPException(status_code=400, detail="Invalid time_offset format. Use e.g. '30s', '15m', '2h', '1d'")

    return {"status": "SCHEDULED", "job": job}


@router.delete("/jobs/{job_id}")
async def cancel_scheduled_job(job_id: str, request: Request):
    """
    Cancels an existing scheduled job.
    """
    scheduler = getattr(request.app.state, "scheduler_engine", None)
    if not scheduler:
        raise HTTPException(status_code=500, detail="SchedulerEngine is not initialized")

    success = scheduler.cancel_job(job_id)
    if not success:
        raise HTTPException(status_code=404, detail="Job not found or already cancelled")

    return {"status": "CANCELLED", "job_id": job_id}
