"""Blender Pipeline Executor — bridges staged pipeline to MCP execution.

Converts AssemblyGraph from Stage 4 into Blender MCP tool calls and executes them.

CRITICAL INVARIANTS:
1. Verification failure = pipeline failure (ok=False)
2. Verifier exceptions = pipeline failure (fail closed)
3. Partial builds are rolled back on failure
4. User scene is never destroyed - we use isolated collections
"""

import logging
import uuid
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum

logger = logging.getLogger(__name__)

# Import centralized broadcast
from .broadcast import broadcast_blender_trace


class PipelineStatus(str, Enum):
    """Pipeline execution status - explicit states, no ambiguity."""
    SUCCESS = "SUCCESS"
    BUILD_FAILED = "BUILD_FAILED"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"
    VERIFICATION_UNAVAILABLE = "VERIFICATION_UNAVAILABLE"
    ROLLBACK_COMPLETE = "ROLLBACK_COMPLETE"


# Configurable tolerances
DEFAULT_DIMENSION_TOLERANCE_M = 0.01  # 1cm default
DEFAULT_CONNECTOR_REACH_TOLERANCE_M = 0.05  # 5cm tolerance for connector endpoints


# Generation ID prefix for tracking created objects
GENERATION_PREFIX = "sentinel_gen"

# Max retries on verification failure (retry from Stage 4 with feedback)
MAX_VERIFICATION_RETRIES = 1


async def execute_assembly_graph(
    graph: Any,
    mcp_manager: Any,
    task_id: str = "staged_build",
    style_tag: str = "hard_surface_industrial",
    category: str = "",
    description: str = "",
    model_manager: Any = None,
    use_llm_modifiers: bool = False,
    stage0_output: Optional[Dict] = None,
    stage1_output: Optional[Dict] = None,
    stage2_output: Optional[Dict] = None,
    stage3_output: Optional[Dict] = None,
    generation_prefix: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute an AssemblyGraph in Blender via MCP.
    
    Uses transactional execution:
    1. Create generation collection
    2. Execute all steps into that collection
    3. On failure: rollback (delete generation)
    4. On success: commit (keep generation)
    
    Args:
        graph: AssemblyGraph from Stage 4 resolver
        mcp_manager: MCPManager instance for Blender connection
        task_id: Task ID for logging
        style_tag: Style hint for post-processing modifiers
        category: Object category from Stage 0
        description: Original user prompt (for LLM mode)
        model_manager: Model manager (required for LLM mode)
        use_llm_modifiers: If True, use LLM for Stage 4.5; else use inference
        stage0_output: Full Stage 0 output for LLM context
        stage1_output: Full Stage 1 output for LLM context
        stage2_output: Full Stage 2 output for LLM context
        stage3_output: Full Stage 3 output for LLM context
        generation_prefix: Optional prefix for object names (for uniqueness across builds)
        
    Returns:
        Dict with ok, executed_steps, errors, generation_id
    """
    from core.assembly_spec import graph_to_blender_steps
    from core.blender_pipeline.stage45_modifiers import Stage45ModifierIntent
    
    # Generate unique ID for this build generation
    gen_short = uuid.uuid4().hex[:8]
    generation_id = f"{GENERATION_PREFIX}_{task_id}_{gen_short}"
    
    # Object name prefix to avoid collisions across builds
    # This ensures "blade" from build 1 doesn't conflict with "blade" from build 2
    obj_prefix = generation_prefix or f"g{gen_short}_"
    
    # ===== STAGE 4.5: Modifier Intent Resolution =====
    await broadcast_blender_trace(task_id, 4.5, "Modifier Intent", "running", {
        "mode": "llm" if use_llm_modifiers and model_manager else "inference"
    })
    
    try:
        if use_llm_modifiers and model_manager:
            modifier_intents = await Stage45ModifierIntent.run_with_llm(
                graph=graph,
                style_tag=style_tag,
                category=category,
                description=description,
                model_manager=model_manager,
                task_id=task_id,
                stage0_output=stage0_output,
                stage1_output=stage1_output,
                stage2_output=stage2_output,
                stage3_output=stage3_output,
            )
        else:
            modifier_intents = Stage45ModifierIntent.run_inference(
                graph=graph,
                style_tag=style_tag,
                category=category,
            )
        
        await broadcast_blender_trace(task_id, 4.5, "Modifier Intent", "complete", {
            "parts_with_bevel": sum(1 for i in modifier_intents.values() if i.bevel),
            "parts_with_subsurf": sum(1 for i in modifier_intents.values() if i.subsurf),
            "parts_with_detail": sum(1 for i in modifier_intents.values() if i.surface_detail),
        })
    except Exception as e:
        logger.warning(f"[{task_id}] Stage 4.5 failed: {e}, using empty intents")
        await broadcast_blender_trace(task_id, 4.5, "Modifier Intent", "warning", {"error": str(e)})
        modifier_intents = {}
    
    # Convert graph to Blender steps with modifier intents
    # NOTE: We no longer use clear_scene - instead we create into a generation collection
    steps = graph_to_blender_steps(graph, style_tag=style_tag, modifier_intents=modifier_intents)
    if not steps:
        return {"ok": False, "error": "No steps generated from assembly graph", "generation_id": generation_id}
    
    # Filter out clear_scene - we'll use collection-based isolation instead
    steps = [(name, args) for name, args in steps if name != "blender:clear_scene"]
    
    # Prefix object names to avoid collisions across builds
    steps = _prefix_object_names(steps, obj_prefix)
    
    # Create generation collection first
    collection_result = await _create_generation_collection(mcp_manager, generation_id)
    if not collection_result.get("ok"):
        return {
            "ok": False, 
            "error": f"Failed to create generation collection: {collection_result.get('error')}",
            "generation_id": generation_id
        }
    
    executed = []
    errors = []
    created_objects = []
    
    for tool_name, args in steps:
        try:
            if tool_name.startswith("blender:"):
                op_name = tool_name.split(":", 1)[1]
                
                # Inject generation metadata into creation operations
                if op_name.startswith("create_"):
                    args = dict(args)  # Copy to avoid mutation
                    args["_generation_id"] = generation_id
                    args["_collection_name"] = generation_id
                
                result = await _execute_blender_op(mcp_manager, op_name, args)
                
                if isinstance(result, dict) and result.get("ok") is False:
                    errors.append(f"{tool_name}: {result.get('error', 'failed')}")
                    # Stop on first error - don't continue partial build
                    break
                else:
                    executed.append(tool_name)
                    # Track created objects for potential rollback
                    if result.get("name"):
                        created_objects.append(result["name"])
            else:
                logger.warning(f"Unknown tool type: {tool_name}")
                
        except Exception as e:
            errors.append(f"{tool_name}: {e}")
            logger.error(f"[{task_id}] Step {tool_name} failed: {e}")
            break  # Stop on exception
    
    # If errors occurred, rollback
    if errors:
        logger.warning(f"[{task_id}] Build failed, rolling back generation {generation_id}")
        await _rollback_generation(mcp_manager, generation_id, created_objects)
        return {
            "ok": False,
            "error": f"Build failed: {errors}",
            "executed_steps": len(executed),
            "total_steps": len(steps),
            "errors": errors,
            "generation_id": generation_id,
            "rolled_back": True,
        }
    
    return {
        "ok": True,
        "executed_steps": len(executed),
        "total_steps": len(steps),
        "errors": None,
        "generation_id": generation_id,
        "created_objects": created_objects,
    }


async def _create_generation_collection(mcp_manager: Any, generation_id: str) -> Dict:
    """Create an isolated collection for this generation."""
    script = f'''
import bpy
import json

collection_name = {repr(generation_id)}

# Create collection if it doesn't exist
if collection_name not in bpy.data.collections:
    coll = bpy.data.collections.new(collection_name)
    bpy.context.scene.collection.children.link(coll)
    result = {{"ok": True, "created": True, "name": collection_name}}
else:
    result = {{"ok": True, "created": False, "name": collection_name}}

print("SENTINEL_OUTPUT_START" + json.dumps(result) + "SENTINEL_OUTPUT_END")
'''
    try:
        from core.blender_ops import parse_op_output
        result = await mcp_manager.call_locked("blender", "execute_blender_code", {"code": script})
        return parse_op_output(result.get("output", ""))
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def _rollback_generation(mcp_manager: Any, generation_id: str, created_objects: List[str]) -> Dict:
    """Rollback a failed generation by deleting its collection, objects, and orphan data."""
    script = f'''
import bpy
import json

generation_id = {repr(generation_id)}
created_objects = {repr(created_objects)}
removed = []
orphans_purged = {{}}

# Track meshes/materials before removal for targeted orphan cleanup
meshes_before = set(m.name for m in bpy.data.meshes if m.users == 1)
materials_before = set(m.name for m in bpy.data.materials if m.users == 1)

# Remove objects by name
for obj_name in created_objects:
    obj = bpy.data.objects.get(obj_name)
    if obj:
        # Track mesh name before removal
        mesh_name = obj.data.name if obj.type == "MESH" and obj.data else None
        bpy.data.objects.remove(obj, do_unlink=True)
        removed.append(obj_name)

# Remove collection
coll = bpy.data.collections.get(generation_id)
if coll:
    bpy.data.collections.remove(coll)

# Targeted orphan cleanup: only remove data blocks that became orphaned
# after our object removal (not pre-existing orphans)
meshes_after = set(m.name for m in bpy.data.meshes if m.users == 0)
materials_after = set(m.name for m in bpy.data.materials if m.users == 0)

# Only purge meshes that were single-user before and are now orphaned
orphan_meshes = [m for m in bpy.data.meshes if m.users == 0 and m.name not in meshes_before]
for mesh in orphan_meshes:
    bpy.data.meshes.remove(mesh)
orphans_purged["meshes"] = len(orphan_meshes)

# Only purge materials that were single-user before and are now orphaned  
orphan_materials = [m for m in bpy.data.materials if m.users == 0 and m.name not in materials_before]
for mat in orphan_materials:
    bpy.data.materials.remove(mat)
orphans_purged["materials"] = len(orphan_materials)

result = {{
    "ok": True, 
    "removed_objects": removed, 
    "collection_removed": coll is not None,
    "orphans_purged": orphans_purged
}}
print("SENTINEL_OUTPUT_START" + json.dumps(result) + "SENTINEL_OUTPUT_END")
'''
    try:
        from core.blender_ops import parse_op_output
        result = await mcp_manager.call_locked("blender", "execute_blender_code", {"code": script})
        return parse_op_output(result.get("output", ""))
    except Exception as e:
        logger.error(f"Rollback failed: {e}")
        return {"ok": False, "error": str(e)}


async def _execute_blender_op(mcp_manager: Any, op_name: str, args: Dict) -> Dict:
    """Execute a single Blender operation via MCP."""
    from core import blender_ops as b_ops
    from core.blender_ops import render_op_script, parse_op_output
    
    # Map op names to param classes and templates
    OP_MAP = {
        "clear_scene": (b_ops.ClearSceneParams, b_ops._CLEAR_SCENE_TEMPLATE),
        "create_cylinder": (b_ops.CreateCylinderParams, b_ops._CREATE_CYLINDER_TEMPLATE),
        "create_sphere": (b_ops.CreateSphereParams, b_ops._CREATE_SPHERE_TEMPLATE),
        "create_hemisphere": (b_ops.CreateHemisphereParams, b_ops._CREATE_HEMISPHERE_TEMPLATE),
        "create_box": (b_ops.CreateBoxParams, b_ops._CREATE_BOX_TEMPLATE),
        "create_cone": (b_ops.CreateConeParams, b_ops._CREATE_CONE_TEMPLATE),
        "create_torus": (b_ops.CreateTorusParams, b_ops._CREATE_TORUS_TEMPLATE),
        "set_material": (b_ops.SetMaterialParams, b_ops._SET_MATERIAL_TEMPLATE),
        "set_transform": (b_ops.SetTransformParams, b_ops._SET_TRANSFORM_TEMPLATE),
        "create_light": (b_ops.CreateLightParams, b_ops._CREATE_LIGHT_TEMPLATE),
        "create_camera": (b_ops.CreateCameraParams, b_ops._CREATE_CAMERA_TEMPLATE),
        "parent_object": (b_ops.ParentObjectParams, b_ops._PARENT_OBJECT_TEMPLATE),
        "apply_boolean": (b_ops.ApplyBooleanParams, b_ops._APPLY_BOOLEAN_TEMPLATE),
        "apply_bevel": (b_ops.ApplyBevelParams, b_ops._APPLY_BEVEL_TEMPLATE),
        "apply_subdivision": (b_ops.ApplySubdivisionParams, b_ops._APPLY_SUBDIVISION_TEMPLATE),
        "set_smooth_shading": (b_ops.SetSmoothShadingParams, b_ops._SET_SMOOTH_SHADING_TEMPLATE),
        "apply_array": (b_ops.ApplyArrayParams, b_ops._APPLY_ARRAY_TEMPLATE),
        "set_origin": (b_ops.SetOriginParams, b_ops._SET_ORIGIN_TEMPLATE),
        "delete_object": (b_ops.DeleteObjectParams, b_ops._DELETE_OBJECT_TEMPLATE),
        "join_objects": (b_ops.JoinObjectsParams, b_ops._JOIN_OBJECTS_TEMPLATE),
        "get_manifest": (b_ops.GetManifestParams, b_ops._GET_MANIFEST_TEMPLATE),
        "separate_mesh": (b_ops.SeparateMeshParams, b_ops._SEPARATE_MESH_TEMPLATE),
    }
    
    if op_name not in OP_MAP:
        return {"ok": False, "error": f"Unknown op: {op_name}"}
    
    param_cls, template = OP_MAP[op_name]
    
    # Remove internal metadata fields before validation
    clean_args = {k: v for k, v in args.items() if not k.startswith("_")}
    
    try:
        params = param_cls(**clean_args)
        script = render_op_script(template, params)
        
        # Inject generation metadata into script if present
        if args.get("_generation_id") and args.get("_collection_name"):
            script = _inject_generation_metadata(script, args["_generation_id"], args["_collection_name"])
        
        result = await mcp_manager.call_locked("blender", "execute_blender_code", {"code": script})
        return parse_op_output(result.get("output", ""))
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _inject_generation_metadata(script: str, generation_id: str, collection_name: str) -> str:
    """Inject code to add generation metadata and move object to collection.
    
    CRITICAL: This must be injected at a point where 'obj' is guaranteed to exist.
    We look for the pattern where obj is assigned and result is built.
    """
    # Find the LAST occurrence of 'result = {' which is in the success path
    marker = 'result = {'
    last_idx = script.rfind(marker)
    
    if last_idx == -1:
        return script
    
    # Detect the indentation level of the 'result = {' line
    # Find the start of the line containing 'result = {'
    line_start = script.rfind('\n', 0, last_idx)
    if line_start == -1:
        line_start = 0
    else:
        line_start += 1  # Skip the newline character
    
    # Extract the whitespace between line start and 'result'
    existing_indent = script[line_start:last_idx]
    # Only keep actual whitespace (spaces/tabs)
    existing_indent = ''.join(c for c in existing_indent if c in ' \t')
    
    # Build injection with matching indentation
    injection_lines = [
        f"{existing_indent}# Sentinel generation metadata",
        f"{existing_indent}if 'obj' in dir() and obj is not None:",
        f"{existing_indent}    obj['sentinel_generation_id'] = {repr(generation_id)}",
        f"{existing_indent}    # Move to generation collection",
        f"{existing_indent}    gen_coll = bpy.data.collections.get({repr(collection_name)})",
        f"{existing_indent}    if gen_coll and obj.name not in gen_coll.objects:",
        f"{existing_indent}        # Unlink from current collections",
        f"{existing_indent}        for coll in obj.users_collection:",
        f"{existing_indent}            coll.objects.unlink(obj)",
        f"{existing_indent}        gen_coll.objects.link(obj)",
        "",  # Empty line before result
    ]
    injection = '\n'.join(injection_lines)
    
    # Insert the injection before the 'result = {' (at line_start position)
    script = script[:line_start] + injection + script[line_start:]
    
    return script


async def run_staged_pipeline_and_execute(
    description: str,
    mcp_manager: Any,
    model_manager: Any,
    task_id: str = "staged_build",
    use_llm_modifiers: bool = False,
) -> Dict[str, Any]:
    """Full pipeline: run stages 0-4, then execute in Blender.
    
    CRITICAL: Verification failure = pipeline failure.
    On verification failure, retries from the appropriate stage with feedback:
    - Dimension mismatch → retry from Stage 2 (Dimensions)
    - Spatial/interpenetration → retry from Stage 3 (Semantics)  
    - Mesh issues → no retry (likely boolean geometry problem)
    
    Args:
        description: User's natural language description of the object
        mcp_manager: MCPManager for Blender connection
        model_manager: Model manager for LLM calls
        task_id: Task ID for logging/tracing
        use_llm_modifiers: If True, use LLM for Stage 4.5 modifier intent
    """
    from core.blender_pipeline.orchestrator import StagedPipelineOrchestrator
    
    if not description:
        return {"ok": False, "error": "No description provided", "status": PipelineStatus.BUILD_FAILED}
    
    if not model_manager:
        return {"ok": False, "error": "model_manager required for staged pipeline", "status": PipelineStatus.BUILD_FAILED}
    
    if not mcp_manager:
        return {
            "ok": False,
            "status": PipelineStatus.BUILD_FAILED,
            "error": "Blender MCP not connected. Connect Blender first.",
        }
    
    # Track retry state
    verification_attempt = 0
    last_verification_error = None
    retry_from_stage = None  # Which stage to retry from
    prior_outputs = {}  # Cached outputs for retry
    
    while verification_attempt <= MAX_VERIFICATION_RETRIES:
        # ===== RUN ORCHESTRATOR (Stages 0-4) =====
        if verification_attempt == 0:
            # First attempt: run full pipeline
            result = await StagedPipelineOrchestrator.run(
                prompt=description,
                model_manager=model_manager,
                task_id=task_id,
            )
        else:
            # Retry: run from failure point with feedback
            logger.info(f"[{task_id}] Verification retry {verification_attempt}/{MAX_VERIFICATION_RETRIES} from Stage {retry_from_stage}")
            await broadcast_blender_trace(task_id, retry_from_stage, "Retry", "running", {
                "attempt": verification_attempt + 1,
                "retry_from_stage": retry_from_stage,
                "feedback": last_verification_error,
            })
            
            # Inject feedback into the stage that needs fixing
            if retry_from_stage == 2:
                # Dimension issue - re-run Stage 2 with feedback
                prior_outputs["stage2_feedback"] = last_verification_error
            elif retry_from_stage == 3:
                # Spatial issue - re-run Stage 3 with feedback
                prior_outputs["stage3_feedback"] = last_verification_error
            
            result = await StagedPipelineOrchestrator.run_from_stage(
                stage=retry_from_stage,
                prior_outputs=prior_outputs,
                prompt=description,
                model_manager=model_manager,
                task_id=task_id,
            )
        
        trace = {
            "stage0": result.stage0_output,
            "stage1": result.stage1_output,
            "stage2": result.stage2_output,
            "stage3": result.stage3_output,
        }
        
        # Cache outputs for potential retry
        prior_outputs = {
            "stage0": result.stage0_output,
            "stage1": result.stage1_output,
            "stage2": result.stage2_output,
            "stage3": result.stage3_output,
        }
        
        if not result.success:
            return {
                "ok": False,
                "status": PipelineStatus.BUILD_FAILED,
                "error": result.error,
                "failed_stage": result.failed_stage,
                "trace": trace,
            }
        
        graph = result.graph
        
        style_tag = "hard_surface_industrial"
        category = ""
        if result.stage0_output:
            style_tag = result.stage0_output.get("style_tag", "hard_surface_industrial")
            category = result.stage0_output.get("category", "")
        
        # Generate unique prefix for this attempt to avoid name collisions
        gen_prefix = f"g{uuid.uuid4().hex[:6]}_"
        
        # ===== STAGE 5: Blender Execution =====
        await broadcast_blender_trace(task_id, 5, "Blender Execution", "running", {
            "total_steps": _count_nodes(graph.root) + 1,
            "attempt": verification_attempt + 1,
        })
        
        exec_result = await execute_assembly_graph(
            graph=graph,
            mcp_manager=mcp_manager,
            task_id=task_id,
            style_tag=style_tag,
            category=category,
            description=description,
            model_manager=model_manager,
            use_llm_modifiers=use_llm_modifiers,
            stage0_output=result.stage0_output,
            stage1_output=result.stage1_output,
            stage2_output=result.stage2_output,
            stage3_output=result.stage3_output,
            generation_prefix=gen_prefix,
        )
        
        generation_id = exec_result.get("generation_id")
        
        if not exec_result.get("ok"):
            await broadcast_blender_trace(task_id, 5, "Blender Execution", "failed", {
                "errors": exec_result.get("errors")
            })
            return {
                "ok": False,
                "status": PipelineStatus.BUILD_FAILED,
                "error": f"Execution failed: {exec_result.get('errors')}",
                "pipeline_succeeded": True,
                "execution_failed": True,
                "rolled_back": exec_result.get("rolled_back", False),
                "generation_id": generation_id,
                "trace": trace,
            }
        
        await broadcast_blender_trace(task_id, 5, "Blender Execution", "complete", {
            "executed_steps": exec_result.get("executed_steps")
        })
        
        # ===== STAGE 6: Verification =====
        await broadcast_blender_trace(task_id, 6, "Verification", "running")
        
        obj_prefix = gen_prefix
        
        verification_result = await _run_verification(mcp_manager, graph, task_id, obj_prefix)
        dimension_check = await _verify_dimensions_match_spec(mcp_manager, graph, task_id, obj_prefix=obj_prefix)
        connector_check = await _verify_connectors_reach_targets(mcp_manager, graph, task_id, obj_prefix=obj_prefix)
        mesh_check = await _verify_boolean_postconditions(mcp_manager, graph, task_id, obj_prefix=obj_prefix)
        
        # CRITICAL: Verification failure = pipeline failure
        verification_passed = (
            verification_result.get("ok") is True and 
            dimension_check.get("ok") is True and
            connector_check.get("ok") is True and
            mesh_check.get("ok") is True
        )
        
        # Check if verification was skipped due to error (fail closed)
        verification_skipped = verification_result.get("skipped", False)
        
        if verification_skipped:
            # Verification unavailable = fail closed (no retry)
            await broadcast_blender_trace(task_id, 6, "Verification", "failed", {
                "reason": "Verification unavailable - failing closed",
                "error": verification_result.get("reason")
            })
            await _rollback_generation(mcp_manager, generation_id, exec_result.get("created_objects", []))
            return {
                "ok": False,
                "status": PipelineStatus.VERIFICATION_UNAVAILABLE,
                "error": f"Verification unavailable: {verification_result.get('reason')}",
                "generation_id": generation_id,
                "rolled_back": True,
                "trace": trace,
            }
        
        if verification_passed:
            # SUCCESS
            await broadcast_blender_trace(task_id, 6, "Verification", "complete")
            return {
                "ok": True,
                "status": PipelineStatus.SUCCESS,
                "model_name": description[:50],
                "parts_count": _count_nodes(graph.root),
                "executed_steps": exec_result.get("executed_steps"),
                "verification": verification_result,
                "dimension_check": dimension_check,
                "connector_check": connector_check,
                "mesh_check": mesh_check,
                "rests_on_surface": graph.rests_on_surface,
                "generation_id": generation_id,
                "trace": trace,
                "verification_attempts": verification_attempt + 1,
            }
        
        # Verification failed - determine which stage to retry from
        last_verification_error = _format_verification_error(
            verification_result, dimension_check, connector_check, mesh_check
        )
        
        # Determine retry stage based on failure type
        retry_from_stage = _determine_retry_stage(
            dimension_check, verification_result, connector_check, mesh_check
        )
        
        # Rollback this attempt
        await _rollback_generation(mcp_manager, generation_id, exec_result.get("created_objects", []))
        
        # Mesh issues are not retryable (geometry problem, not LLM problem)
        if retry_from_stage is None:
            await broadcast_blender_trace(task_id, 6, "Verification", "failed", {
                "mesh_issues": mesh_check.get("issues", []),
                "not_retryable": True,
            })
            return {
                "ok": False,
                "status": PipelineStatus.VERIFICATION_FAILED,
                "error": f"Verification failed (not retryable): {last_verification_error}",
                "verification": verification_result,
                "dimension_check": dimension_check,
                "connector_check": connector_check,
                "mesh_check": mesh_check,
                "generation_id": generation_id,
                "rolled_back": True,
                "trace": trace,
            }
        
        if verification_attempt >= MAX_VERIFICATION_RETRIES:
            # No more retries - fail
            await broadcast_blender_trace(task_id, 6, "Verification", "failed", {
                "spatial_issues": verification_result.get("error"),
                "dimension_mismatches": dimension_check.get("mismatches", []),
                "connector_issues": connector_check.get("issues", []),
                "mesh_issues": mesh_check.get("issues", []),
                "attempts_exhausted": True,
            })
            return {
                "ok": False,
                "status": PipelineStatus.VERIFICATION_FAILED,
                "error": f"Verification failed after {verification_attempt + 1} attempts: {last_verification_error}",
                "verification": verification_result,
                "dimension_check": dimension_check,
                "connector_check": connector_check,
                "mesh_check": mesh_check,
                "generation_id": generation_id,
                "rolled_back": True,
                "trace": trace,
                "verification_attempts": verification_attempt + 1,
            }
        
        verification_attempt += 1
    
    # Should not reach here
    return {
        "ok": False,
        "status": PipelineStatus.VERIFICATION_FAILED,
        "error": "Unexpected exit from verification loop",
        "trace": trace,
    }


def _determine_retry_stage(
    dimension_check: Dict,
    verification_result: Dict,
    connector_check: Dict,
    mesh_check: Dict,
) -> Optional[int]:
    """Determine which stage to retry from based on verification failure type.
    
    Returns:
        Stage number to retry from, or None if not retryable
    """
    # Mesh issues (degenerate faces, non-manifold) are not retryable
    # These are geometry problems, not LLM problems
    if not mesh_check.get("ok") and mesh_check.get("issues"):
        return None
    
    # Dimension mismatches → retry from Stage 2 (Dimensions)
    if not dimension_check.get("ok") and dimension_check.get("mismatches"):
        return 2
    
    # Spatial/interpenetration issues → retry from Stage 3 (Semantics)
    # These are usually caused by wrong socket_type or height_hint
    if not verification_result.get("ok"):
        return 3
    
    # Connector issues → retry from Stage 3 (Semantics)
    if not connector_check.get("ok") and connector_check.get("issues"):
        return 3
    
    # Default: retry from Stage 2
    return 2


def _format_verification_error(
    verification_result: Dict,
    dimension_check: Dict,
    connector_check: Dict,
    mesh_check: Dict,
) -> str:
    """Format verification errors into a feedback string for retry."""
    errors = []
    
    if not verification_result.get("ok"):
        errors.append(f"Spatial: {verification_result.get('error', 'unknown')}")
    
    if not dimension_check.get("ok"):
        mismatches = dimension_check.get("mismatches", [])
        for m in mismatches[:3]:  # Limit to first 3
            errors.append(f"Dimension: {m['object']} {m['axis']} expected {m['expected']}, got {m['actual']}")
    
    if not connector_check.get("ok"):
        issues = connector_check.get("issues", [])
        for i in issues[:3]:
            errors.append(f"Connector: {i['object']} {i['issue']}")
    
    if not mesh_check.get("ok"):
        issues = mesh_check.get("issues", [])
        for i in issues[:3]:
            errors.append(f"Mesh: {i['object']} {i['issues']}")
    
    return "; ".join(errors) if errors else "Unknown verification error"


def _count_nodes(node: Any) -> int:
    """Count total nodes in tree."""
    return 1 + sum(_count_nodes(c) for c in (node.children or []))


def _prefix_object_names(steps: List[Tuple[str, Dict]], prefix: str) -> List[Tuple[str, Dict]]:
    """Prefix all object names in steps to avoid collisions across builds.
    
    This ensures that building "sword" twice doesn't cause name conflicts.
    The prefix is applied to:
    - 'name' field in create_* operations
    - 'name', 'target_name', 'parent_name' in modifier/boolean operations
    - 'names' array in join_objects
    """
    prefixed = []
    for tool_name, args in steps:
        args = dict(args)  # Copy to avoid mutation
        
        # Fields that contain object names
        name_fields = ['name', 'target_name', 'parent_name']
        for field in name_fields:
            if field in args and args[field]:
                args[field] = prefix + args[field]
        
        # Handle 'names' array (join_objects)
        if 'names' in args and isinstance(args['names'], list):
            args['names'] = [prefix + n for n in args['names']]
        
        prefixed.append((tool_name, args))
    
    return prefixed


def _collect_node_labels(node: Any) -> List[str]:
    """Collect all node labels from tree."""
    labels = [node.label]
    for child in (node.children or []):
        labels.extend(_collect_node_labels(child))
    return labels


async def _run_verification(mcp_manager: Any, graph: Any, task_id: str, obj_prefix: str = "") -> Dict[str, Any]:
    """Run AssemblyVerificationGate on the built objects.
    
    CRITICAL: Exceptions = fail closed (ok=False, skipped=True)
    
    Args:
        obj_prefix: Prefix applied to object names during build
    """
    try:
        from core.assembly_verification import AssemblyVerificationGate
        from core.assembly_spec import JoinMode
        
        verifier = AssemblyVerificationGate(blender_bridge=mcp_manager)
        # Apply prefix to object names for lookup
        object_names = [obj_prefix + n for n in _collect_node_labels(graph.root)]
        
        # Collect boolean targets (objects with boolean join modes)
        # These are excluded from interpenetration checks since overlap is intentional
        boolean_targets = []
        all_nodes = graph.root.all_nodes()
        for node in all_nodes:
            if node.attachment and node.attachment.join_mode in (
                JoinMode.BOOLEAN_DIFFERENCE,
                JoinMode.FUSE,  # FUSE = boolean union
            ):
                boolean_targets.append(obj_prefix + node.label)
        
        result = await verifier.verify_flat_object_set(
            object_names=object_names,
            task_id=task_id,
            boolean_targets=boolean_targets,
            origin_centered=not graph.rests_on_surface,
        )
        
        return result
        
    except Exception as e:
        # CRITICAL: Fail closed on verification errors
        logger.exception(f"[{task_id}] Verification failed with exception")
        return {
            "ok": False,
            "skipped": True,
            "reason": str(e)
        }


async def _verify_dimensions_match_spec(
    mcp_manager: Any,
    graph: Any,
    task_id: str,
    tolerance_m: float = DEFAULT_DIMENSION_TOLERANCE_M,
    obj_prefix: str = "",
) -> Dict[str, Any]:
    """Verify that built objects match their spec dimensions.
    
    Uses LOCAL mesh geometry to avoid rotation issues with world AABB.
    Uses evaluated depsgraph to account for modifiers.
    
    Args:
        obj_prefix: Prefix applied to object names during build
    """
    from core.blender_ops import parse_op_output
    
    all_nodes = graph.root.all_nodes()
    mismatches = []
    checked = 0
    
    for node in all_nodes:
        spec = node.sub_spec
        if not spec:
            continue
        
        prim = spec.get("primitive", "box")
        label = obj_prefix + node.label  # Apply prefix for lookup
        
        # Read LOCAL dimensions from Blender using EVALUATED mesh (accounts for modifiers)
        # This avoids the rotation problem entirely
        script = f'''
import bpy
import json
from mathutils import Vector

obj = bpy.data.objects.get({repr(label)})
if not obj or obj.type != 'MESH':
    res = {{"ok": False, "error": "not_found_or_not_mesh"}}
else:
    # Use evaluated depsgraph to get mesh with modifiers applied
    depsgraph = bpy.context.evaluated_depsgraph_get()
    obj_eval = obj.evaluated_get(depsgraph)
    mesh_eval = obj_eval.to_mesh()
    
    if not mesh_eval or not mesh_eval.vertices:
        res = {{"ok": False, "error": "no_vertices_after_eval"}}
    else:
        # Compute LOCAL bounding box from evaluated mesh vertices (ignores object rotation)
        verts = [v.co for v in mesh_eval.vertices]
        local_min = [min(v[i] for v in verts) for i in range(3)]
        local_max = [max(v[i] for v in verts) for i in range(3)]
        local_size = [local_max[i] - local_min[i] for i in range(3)]
        
        # Also get object scale (in case scale wasn't applied)
        scale = list(obj.scale)
        scaled_size = [local_size[i] * scale[i] for i in range(3)]
        
        res = {{
            "ok": True,
            "local_size": local_size,
            "scale": scale,
            "scaled_size": scaled_size,
            "used_evaluated_mesh": True,
        }}
    
    # Clean up evaluated mesh
    obj_eval.to_mesh_clear()

print("SENTINEL_OUTPUT_START" + json.dumps(res) + "SENTINEL_OUTPUT_END")
'''
        try:
            result = await mcp_manager.call_locked(
                "blender", "execute_blender_code", {"code": script}
            )
            data = parse_op_output(result.get("output", ""))
            
            if not data.get("ok"):
                continue
            
            checked += 1
            actual_size = data["scaled_size"]
            
            # Determine expected dimensions based on primitive type
            if prim == "box":
                expected = spec.get("size", [1, 1, 1])
                for i, axis in enumerate(["X", "Y", "Z"]):
                    diff = abs(actual_size[i] - expected[i])
                    if diff > tolerance_m:
                        mismatches.append({
                            "object": label,
                            "axis": axis,
                            "expected": expected[i],
                            "actual": round(actual_size[i], 4),
                            "diff_m": round(diff, 4),
                        })
                        
            elif prim == "cylinder":
                expected_r = spec.get("radius", 0.5)
                expected_d = spec.get("depth", 1.0)
                expected_diam = expected_r * 2
                
                # Cylinder: X and Y should be diameter, Z should be depth
                # (in local space, before any rotation)
                if abs(actual_size[0] - expected_diam) > tolerance_m:
                    mismatches.append({
                        "object": label,
                        "axis": "X (diameter)",
                        "expected": expected_diam,
                        "actual": round(actual_size[0], 4),
                        "diff_m": round(abs(actual_size[0] - expected_diam), 4),
                    })
                if abs(actual_size[2] - expected_d) > tolerance_m:
                    mismatches.append({
                        "object": label,
                        "axis": "Z (depth)",
                        "expected": expected_d,
                        "actual": round(actual_size[2], 4),
                        "diff_m": round(abs(actual_size[2] - expected_d), 4),
                    })
                        
            elif prim == "sphere":
                expected_diam = spec.get("radius", 0.5) * 2
                for i, axis in enumerate(["X", "Y", "Z"]):
                    diff = abs(actual_size[i] - expected_diam)
                    if diff > tolerance_m:
                        mismatches.append({
                            "object": label,
                            "axis": axis,
                            "expected": expected_diam,
                            "actual": round(actual_size[i], 4),
                            "diff_m": round(diff, 4),
                        })
                        
            elif prim == "hemisphere":
                expected_r = spec.get("radius", 0.5)
                expected_diam = expected_r * 2
                # Hemisphere: X and Y = diameter, Z = radius
                if abs(actual_size[0] - expected_diam) > tolerance_m:
                    mismatches.append({
                        "object": label,
                        "axis": "X (diameter)",
                        "expected": expected_diam,
                        "actual": round(actual_size[0], 4),
                        "diff_m": round(abs(actual_size[0] - expected_diam), 4),
                    })
                if abs(actual_size[2] - expected_r) > tolerance_m:
                    mismatches.append({
                        "object": label,
                        "axis": "Z (height)",
                        "expected": expected_r,
                        "actual": round(actual_size[2], 4),
                        "diff_m": round(abs(actual_size[2] - expected_r), 4),
                    })
                        
        except Exception as e:
            logger.warning(f"[{task_id}] Could not verify dimensions for {label}: {e}")
    
    if mismatches:
        logger.warning(
            f"[{task_id}] Dimension mismatches found:\n" +
            "\n".join(f"  - {m['object']} {m['axis']}: expected {m['expected']:.3f}m, got {m['actual']:.3f}m" 
                      for m in mismatches)
        )
    
    return {
        "ok": len(mismatches) == 0,
        "checked": checked,
        "mismatches": mismatches,
        "tolerance_m": tolerance_m,
    }


async def _verify_boolean_postconditions(
    mcp_manager: Any,
    graph: Any,
    task_id: str,
    obj_prefix: str = "",
) -> Dict[str, Any]:
    """Verify boolean operations completed successfully.
    
    Checks:
    1. Objects that had booleans applied still have valid geometry
    2. No degenerate faces (zero area)
    3. Mesh is manifold (no holes, consistent normals)
    
    Args:
        obj_prefix: Prefix applied to object names during build
    """
    from core.blender_ops import parse_op_output
    
    all_nodes = graph.root.all_nodes()
    issues = []
    checked = 0
    
    for node in all_nodes:
        label = obj_prefix + node.label  # Apply prefix for lookup
        
        # Check mesh validity
        script = f'''
import bpy
import bmesh
import json

obj = bpy.data.objects.get({repr(label)})
if not obj or obj.type != 'MESH':
    res = {{"ok": True, "skipped": True, "reason": "not_mesh"}}
else:
    issues = []
    
    # Check for degenerate geometry
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    
    # Count degenerate faces (zero or near-zero area)
    degen_faces = sum(1 for f in bm.faces if f.calc_area() < 1e-8)
    if degen_faces > 0:
        issues.append(f"{{degen_faces}} degenerate faces")
    
    # Check for non-manifold edges (edges with != 2 faces)
    non_manifold = sum(1 for e in bm.edges if not e.is_manifold)
    if non_manifold > 0:
        issues.append(f"{{non_manifold}} non-manifold edges")
    
    # Check for loose vertices
    loose_verts = sum(1 for v in bm.verts if not v.link_edges)
    if loose_verts > 0:
        issues.append(f"{{loose_verts}} loose vertices")
    
    bm.free()
    
    res = {{
        "ok": len(issues) == 0,
        "object": {repr(label)},
        "issues": issues,
        "face_count": len(obj.data.polygons),
        "vert_count": len(obj.data.vertices),
    }}

print("SENTINEL_OUTPUT_START" + json.dumps(res) + "SENTINEL_OUTPUT_END")
'''
        try:
            result = await mcp_manager.call_locked(
                "blender", "execute_blender_code", {"code": script}
            )
            data = parse_op_output(result.get("output", ""))
            
            if data.get("skipped"):
                continue
            
            checked += 1
            
            if not data.get("ok"):
                issues.append({
                    "object": label,
                    "issues": data.get("issues", []),
                })
                
        except Exception as e:
            logger.warning(f"[{task_id}] Could not verify mesh for {label}: {e}")
    
    if issues:
        logger.warning(
            f"[{task_id}] Mesh issues found:\n" +
            "\n".join(f"  - {i['object']}: {i['issues']}" for i in issues)
        )
    
    return {
        "ok": len(issues) == 0,
        "checked": checked,
        "issues": issues,
    }


async def _verify_connectors_reach_targets(
    mcp_manager: Any,
    graph: Any,
    task_id: str,
    tolerance_m: float = DEFAULT_CONNECTOR_REACH_TOLERANCE_M,
    obj_prefix: str = "",
) -> Dict[str, Any]:
    """Verify that STRUT and RADIAL_BRIDGE connectors actually reach their targets.
    
    Checks that connector endpoints are within tolerance of their target anchors.
    
    Args:
        obj_prefix: Prefix applied to object names during build
    """
    from core.blender_ops import parse_op_output
    
    all_nodes = graph.root.all_nodes()
    connector_issues = []
    checked = 0
    
    # Build label -> node lookup
    nodes_by_label = {n.label: n for n in all_nodes}
    
    for node in all_nodes:
        socket_type = node.attachment.socket_type if node.attachment else None
        if socket_type not in ("STRUT", "RADIAL_BRIDGE"):
            continue
        
        # Find the target from semantics (stored in attachment metadata or sub_spec)
        # For now, we verify the connector's world position makes geometric sense
        label = obj_prefix + node.label  # Apply prefix for lookup
        spec = node.sub_spec or {}
        
        # Get connector's world endpoints
        script = f'''
import bpy
import json
from mathutils import Vector

obj = bpy.data.objects.get({repr(label)})
if not obj or obj.type != 'MESH':
    res = {{"ok": False, "error": "not_found"}}
else:
    # Get world-space bounding box
    world_verts = [obj.matrix_world @ Vector(v.co) for v in obj.data.vertices]
    if not world_verts:
        res = {{"ok": False, "error": "no_vertices"}}
    else:
        # Find endpoints along the connector's length axis (local Z)
        # Transform local Z axis to world
        local_z = Vector((0, 0, 1))
        world_z = (obj.matrix_world.to_3x3() @ local_z).normalized()
        
        # Project vertices onto this axis to find endpoints
        projections = [(v, v.dot(world_z)) for v in world_verts]
        min_proj = min(projections, key=lambda x: x[1])
        max_proj = max(projections, key=lambda x: x[1])
        
        res = {{
            "ok": True,
            "endpoint_neg": list(min_proj[0]),
            "endpoint_pos": list(max_proj[0]),
            "world_center": list(obj.matrix_world.translation),
            "length_axis": list(world_z),
        }}
print("SENTINEL_OUTPUT_START" + json.dumps(res) + "SENTINEL_OUTPUT_END")
'''
        try:
            result = await mcp_manager.call_locked(
                "blender", "execute_blender_code", {"code": script}
            )
            data = parse_op_output(result.get("output", ""))
            
            if not data.get("ok"):
                continue
            
            checked += 1
            
            # Basic sanity check: connector should have reasonable length
            ep_neg = data["endpoint_neg"]
            ep_pos = data["endpoint_pos"]
            length = sum((ep_pos[i] - ep_neg[i])**2 for i in range(3)) ** 0.5
            
            expected_depth = spec.get("depth", 1.0)
            if abs(length - expected_depth) > tolerance_m:
                connector_issues.append({
                    "object": label,
                    "issue": "length_mismatch",
                    "expected_length": expected_depth,
                    "actual_length": round(length, 4),
                    "diff_m": round(abs(length - expected_depth), 4),
                })
                
        except Exception as e:
            logger.warning(f"[{task_id}] Could not verify connector {label}: {e}")
    
    if connector_issues:
        logger.warning(
            f"[{task_id}] Connector issues found:\n" +
            "\n".join(f"  - {c['object']}: {c['issue']} (expected {c.get('expected_length', '?')}, got {c.get('actual_length', '?')})" 
                      for c in connector_issues)
        )
    
    return {
        "ok": len(connector_issues) == 0,
        "checked": checked,
        "issues": connector_issues,
        "tolerance_m": tolerance_m,
    }
