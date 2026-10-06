"""Blender build route using the primary V2 model pipeline."""

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List

router = APIRouter()


class BlenderBuildRequest(BaseModel):
    description: str = Field(..., min_length=3, max_length=2000)
    use_llm_modifiers: bool = Field(default=True, description="Use LLM for modifier intent")


class DimensionVerifyRequest(BaseModel):
    object_name: str = Field(..., description="Name of object in Blender to verify")
    expected_primitive: str = Field(..., description="Expected primitive type")
    expected_size: Optional[List[float]] = Field(None, description="Expected size [x,y,z] for box")
    expected_radius: Optional[float] = Field(None, description="Expected radius for cylinder/sphere")
    expected_depth: Optional[float] = Field(None, description="Expected depth for cylinder/cone")


@router.post("/build")
async def build_3d_object(req: BlenderBuildRequest, request: Request):
    """Plan, compile, and verify a 3D object in Blender with V2."""
    from core.blender_pipeline.progressive_v2 import HierarchyLimits, run_progressive_build
    
    # Get managers from app state
    model_manager = getattr(request.app.state, "model_manager", None)
    mcp_manager = getattr(request.app.state, "mcp_manager", None)
    
    if not model_manager:
        raise HTTPException(status_code=503, detail="Model manager not initialized")
    
    # Generate task ID
    import uuid
    task_id = f"blender_build_{uuid.uuid4().hex[:8]}"
    
    # V3 remains experimental until it can match V2 on complex model fidelity.
    import logging
    logging.getLogger(__name__).info("[task=%s] /api/blender/build routed to V2", task_id)
    result = await run_progressive_build(
        prompt=req.description,
        model_manager=model_manager,
        task_id=task_id,
        mcp_manager=mcp_manager,
        limits=HierarchyLimits(max_depth=60, max_children=200, max_total_nodes=2000),
        use_llm_modifiers=req.use_llm_modifiers,
    )
    
    # Result serialization is the API contract.  It carries the same
    # controller-computed BuildOutcome persisted in manifest.json.
    payload = result.to_dict()
    from core.blender_pipeline.progressive_v2.outcome_policy import TaskDisposition, task_disposition
    disposition = task_disposition(result.completion_status)
    payload.update({
        "ok": disposition is not TaskDisposition.NOT_DONE,
        "task_id": task_id,
        "pipeline": result.manifest.stats.get("pipeline", "unknown"),
        "task_outcome": disposition.value,
    })
    if disposition is TaskDisposition.NOT_DONE:
        payload["error"] = "; ".join(result.errors) if result.errors else "Build failed"
    return payload


@router.get("/primitive-readback")
async def primitive_readback_test(request: Request):
    """Run primitive readback test to verify Blender's interpretation of parameters.
    
    Creates one of each primitive type with known parameters and reads back
    the actual dimensions and bounding boxes. Use this to establish ground truth.
    """
    from core.blender_pipeline.primitive_readback import run_primitive_readback
    
    mcp_manager = getattr(request.app.state, "mcp_manager", None)
    if not mcp_manager:
        raise HTTPException(status_code=503, detail="Blender MCP not connected")
    
    result = await run_primitive_readback(mcp_manager)
    return result


@router.post("/verify-dimensions")
async def verify_object_dimensions(req: DimensionVerifyRequest, request: Request):
    """Verify a built object's dimensions match expected spec.
    
    Reads the actual dimensions from Blender and compares against expected values.
    """
    from core.blender_pipeline.primitive_readback import verify_built_object_dimensions
    
    mcp_manager = getattr(request.app.state, "mcp_manager", None)
    if not mcp_manager:
        raise HTTPException(status_code=503, detail="Blender MCP not connected")
    
    # Build expected spec from request
    expected_spec = {"primitive": req.expected_primitive}
    if req.expected_size:
        expected_spec["size"] = req.expected_size
    if req.expected_radius is not None:
        expected_spec["radius"] = req.expected_radius
    if req.expected_depth is not None:
        expected_spec["depth"] = req.expected_depth
    
    result = await verify_built_object_dimensions(
        mcp_manager=mcp_manager,
        object_name=req.object_name,
        expected_spec=expected_spec,
    )
    return result


class ExecuteCodeRequest(BaseModel):
    code: str = Field(..., description="Blender Python code to execute")


@router.post("/execute")
async def execute_blender_code(req: ExecuteCodeRequest, request: Request):
    """Execute raw Blender Python code via MCP.
    
    For testing and debugging only.
    """
    mcp_manager = getattr(request.app.state, "mcp_manager", None)
    if not mcp_manager:
        raise HTTPException(status_code=503, detail="Blender MCP not connected")
    
    conn = mcp_manager.get_connection("blender")
    if not conn or conn.status != "connected":
        raise HTTPException(status_code=503, detail="Blender not connected")
    
    try:
        result = await mcp_manager.call_tool("blender", "execute_blender_code", {"code": req.code})
        return {"ok": True, "output": result.get("output", "")}
    except Exception as e:
        return {"ok": False, "error": str(e)}
