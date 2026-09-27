"""FastAPI route handlers for governing dependency-change plans."""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from core.dependency_plans import (
    dependency_change_executor,
    dependency_plan_repository,
    DependencyChangePlan,
)

logger = logging.getLogger(__name__)

router = APIRouter()


class ApprovePlanRequest(BaseModel):
    plan_hash: str = Field(..., description="Hash of the immutable plan payload")
    allow_unpinned: bool = Field(False, description="Explicit confirmation for unpinned version constraints")


class ExecutePlanRequest(BaseModel):
    plan_hash: str = Field(..., description="Hash of the immutable plan payload")


class RejectPlanRequest(BaseModel):
    reason: str = Field("", description="Optional rejection reason")


@router.get("")
async def list_dependency_plans(status: Optional[str] = Query(None, description="Filter by plan status")):
    """Lists dependency change plans, optionally filtered by status."""
    try:
        plans = dependency_plan_repository.list_by_status(status)
        return [
            {
                "plan_id": p.plan_id,
                "project_path": p.project_path,
                "ecosystem": p.ecosystem,
                "package_name": p.package_name,
                "requested_spec": p.requested_spec,
                "reason": p.reason,
                "evidence": p.evidence,
                "manifest_path": p.manifest_path,
                "lockfile_path": p.lockfile_path,
                "command": p.command,
                "plan_hash": p.plan_hash,
                "status": p.status,
                "is_pinned": p.is_pinned,
                "created_at": p.created_at,
                "expires_at": p.expires_at,
                "approved_at": p.approved_at,
                "executed_at": p.executed_at,
                "result": p.result,
            }
            for p in plans
        ]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error listing dependency plans: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{plan_id}")
async def get_dependency_plan(plan_id: str):
    """Retrieves a single dependency change plan by ID."""
    plan = dependency_plan_repository.get(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail=f"Dependency plan not found: {plan_id}")
    return {
        "plan_id": plan.plan_id,
        "project_path": plan.project_path,
        "ecosystem": plan.ecosystem,
        "package_name": plan.package_name,
        "requested_spec": plan.requested_spec,
        "reason": plan.reason,
        "evidence": plan.evidence,
        "manifest_path": plan.manifest_path,
        "lockfile_path": plan.lockfile_path,
        "command": plan.command,
        "plan_hash": plan.plan_hash,
        "status": plan.status,
        "is_pinned": plan.is_pinned,
        "created_at": plan.created_at,
        "expires_at": plan.expires_at,
        "approved_at": plan.approved_at,
        "executed_at": plan.executed_at,
        "result": plan.result,
    }


@router.post("/{plan_id}/approve")
async def approve_dependency_plan(plan_id: str, req: ApprovePlanRequest):
    """Creates a one-time approval for a plan after verifying plan hash and concurrency guard."""
    try:
        plan = dependency_plan_repository.approve(
            plan_id=plan_id,
            expected_plan_hash=req.plan_hash,
            allow_unpinned=req.allow_unpinned,
            actor="user",
        )
        return {"status": plan.status, "approved_at": plan.approved_at, "plan_id": plan.plan_id}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error approving dependency plan {plan_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{plan_id}/execute")
async def execute_dependency_plan(plan_id: str, req: ExecutePlanRequest):
    """Executes an approved, unexpired plan via the dedicated DependencyChangeExecutor."""
    try:
        res = dependency_change_executor.execute_plan(
            plan_id=plan_id,
            expected_plan_hash=req.plan_hash,
            actor="user",
        )
        return res
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error executing dependency plan {plan_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{plan_id}/reject")
async def reject_dependency_plan(plan_id: str, req: RejectPlanRequest):
    """Rejects an unexecuted plan with an optional reason."""
    try:
        plan = dependency_plan_repository.reject(
            plan_id=plan_id,
            reason=req.reason,
            actor="user",
        )
        return {"status": plan.status, "plan_id": plan.plan_id}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error rejecting dependency plan {plan_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{plan_id}/rollback")
async def rollback_dependency_plan(plan_id: str):
    """Restores pre-execution manifest backups for a plan."""
    try:
        res = dependency_change_executor.rollback_plan(plan_id=plan_id, actor="user")
        return res
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error rolling back dependency plan {plan_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
