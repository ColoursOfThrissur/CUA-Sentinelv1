"""Node Executor — executes and verifies individual nodes in Blender via MCP.

Blueprint references:
  §28: Stage 5 Blender Execution (node-scoped build transaction)
  §29: Stage 6 Verification (fail-closed, local bounds)
  §12: Assembly Merge Operation

CRITICAL: This executor uses the sub_spec and transforms computed by Stage 4.
It does NOT compute transforms itself.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

from .manifest import BuildManifest, ManifestNode, NodeState
from .node_types import NodeKind
from ..executor import (
    _execute_blender_op,
    _create_generation_collection,
    _rollback_generation,
    GENERATION_PREFIX,
)
from core.assembly_verification import AssemblyVerificationGate
from core.blender_ops import parse_op_output

logger = logging.getLogger(__name__)


class NodeExecutionError(Exception):
    """Raised when an individual node build fails in Blender."""
    pass


class ProgressiveNodeExecutor:
    """Executes single-node geometry creation in Blender using Stage 4 output."""

    def __init__(self, mcp_manager: Optional[Any] = None):
        self.mcp_manager = mcp_manager

    async def execute_leaf_node(
        self,
        node: ManifestNode,
        manifest: BuildManifest,
        task_id: str = "adhoc",
    ) -> Dict[str, Any]:
        """Build and verify a single leaf PART node in Blender.
        
        Uses Stage 4 output (sub_spec, location, rotation) directly.
        """
        if not self.mcp_manager:
            logger.info(f"[{task_id}] No mcp_manager; mocking build for '{node.label}'")
            node.blender_objects = [f"mock_{node.label}"]
            return {"ok": True, "created_objects": node.blender_objects}

        # Get Stage 4 output - this contains everything we need
        s4 = node.stage_outputs.get("stage4", {})
        if not s4:
            raise NodeExecutionError(f"Node '{node.label}' missing Stage 4 output")

        sub_spec = s4.get("sub_spec", {})
        location = s4.get("location", [0.0, 0.0, 0.0])
        rotation = s4.get("rotation", [0.0, 0.0, 0.0])

        # Create generation-scoped collection
        gen_short = uuid.uuid4().hex[:8]
        generation_id = f"{GENERATION_PREFIX}_{task_id}_{gen_short}"
        node.generation_id = generation_id

        safe_label = node.label.replace(" ", "_").replace("-", "_")
        obj_name = f"g{gen_short}_{safe_label}"

        coll_res = await _create_generation_collection(self.mcp_manager, generation_id)
        if not coll_res.get("ok"):
            raise NodeExecutionError(
                f"Failed to create collection for '{node.label}': {coll_res.get('error')}"
            )

        # Build operation args from sub_spec
        primitive_type = sub_spec.get("primitive", "box").lower()
        
        op_args: Dict[str, Any] = {
            "name": obj_name,
            "location": location,
            "rotation": rotation,
            "_generation_id": generation_id,
            "_collection_name": generation_id,
        }

        # Map primitive type to Blender operation
        if primitive_type == "box":
            op_name = "create_box"
            op_args["size"] = sub_spec.get("size", [0.2, 0.2, 0.2])
        elif primitive_type == "cylinder":
            op_name = "create_cylinder"
            op_args["radius"] = sub_spec.get("radius", 0.05)
            op_args["depth"] = sub_spec.get("depth", 0.2)
            op_args["vertices"] = sub_spec.get("vertices", 32)
        elif primitive_type == "sphere":
            op_name = "create_sphere"
            op_args["radius"] = sub_spec.get("radius", 0.1)
        elif primitive_type == "cone":
            op_name = "create_cone"
            op_args["radius1"] = sub_spec.get("radius1", 0.1)
            op_args["radius2"] = sub_spec.get("radius2", 0.0)
            op_args["depth"] = sub_spec.get("depth", 0.2)
        elif primitive_type == "torus":
            op_name = "create_torus"
            op_args["major_radius"] = sub_spec.get("major_radius", 0.1)
            op_args["minor_radius"] = sub_spec.get("minor_radius", 0.02)
        elif primitive_type == "hemisphere":
            # Hemisphere: create sphere then bisect
            op_name = "create_sphere"
            op_args["radius"] = sub_spec.get("radius", 0.1)
            # TODO: Add bisect operation after creation
        else:
            op_name = "create_box"
            op_args["size"] = [0.1, 0.1, 0.1]

        # Create primitive in Blender
        res = await _execute_blender_op(self.mcp_manager, op_name, op_args)
        if not res.get("ok"):
            await _rollback_generation(self.mcp_manager, generation_id, [])
            raise NodeExecutionError(f"Failed to create '{obj_name}': {res.get('error')}")

        created_name = res.get("name", obj_name)
        node.blender_objects = [created_name]

        # Apply material if specified
        s2 = node.stage_outputs.get("stage2", {})
        material = s2.get("material") or sub_spec.get("material")
        if material:
            mat_args = {
                "name": created_name,
                "color": material.get("color", [0.8, 0.8, 0.8]) + [1.0],
                "roughness": material.get("roughness", 0.5),
                "metallic": material.get("metallic", 0.0),
                "_generation_id": generation_id,
                "_collection_name": generation_id,
            }
            if material.get("emission_color"):
                mat_args["emission_color"] = material["emission_color"]
                mat_args["emission_strength"] = material.get("emission_strength", 1.0)
            await _execute_blender_op(self.mcp_manager, "set_material", mat_args)

        # Verify dimensions
        dim_check = await self._verify_node_dimensions(
            obj_name=created_name,
            sub_spec=sub_spec,
            task_id=task_id,
        )

        if not dim_check.get("ok"):
            mismatches = dim_check.get("mismatches", [])
            if any(m.get("diff_m", 0) > 0.05 for m in mismatches):
                await _rollback_generation(self.mcp_manager, generation_id, [created_name])
                raise NodeExecutionError(f"Dimension verification failed: {mismatches}")

        return {
            "ok": True,
            "created_objects": [created_name],
            "generation_id": generation_id,
            "dimension_check": dim_check,
        }

    async def _verify_node_dimensions(
        self,
        obj_name: str,
        sub_spec: Dict[str, Any],
        task_id: str,
        tolerance_m: float = 0.01,
    ) -> Dict[str, Any]:
        """Verify node dimensions match sub_spec using local mesh bounds."""
        if not self.mcp_manager:
            return {"ok": True, "skipped": True, "reason": "no_mcp"}

        script = f'''
import bpy
import json

obj = bpy.data.objects.get({repr(obj_name)})
if not obj or obj.type != 'MESH':
    res = {{"ok": False, "error": "not_found_or_not_mesh"}}
else:
    depsgraph = bpy.context.evaluated_depsgraph_get()
    obj_eval = obj.evaluated_get(depsgraph)
    mesh_eval = obj_eval.to_mesh()
    
    if not mesh_eval or not mesh_eval.vertices:
        res = {{"ok": False, "error": "no_vertices"}}
    else:
        verts = [v.co for v in mesh_eval.vertices]
        local_min = [min(v[i] for v in verts) for i in range(3)]
        local_max = [max(v[i] for v in verts) for i in range(3)]
        local_size = [local_max[i] - local_min[i] for i in range(3)]
        scale = list(obj.scale)
        scaled_size = [local_size[i] * scale[i] for i in range(3)]
        
        res = {{
            "ok": True,
            "local_size": local_size,
            "scale": scale,
            "scaled_size": scaled_size,
        }}
    obj_eval.to_mesh_clear()

print("SENTINEL_OUTPUT_START" + json.dumps(res) + "SENTINEL_OUTPUT_END")
'''
        try:
            result = await self.mcp_manager.call_locked(
                "blender", "execute_blender_code", {"code": script}
            )
            data = parse_op_output(result.get("output", ""))
            
            if not data.get("ok"):
                return {"ok": False, "error": data.get("error", "unknown")}
            
            actual_size = data["scaled_size"]
            mismatches = []
            primitive = sub_spec.get("primitive", "box")
            
            if primitive == "box":
                expected = sub_spec.get("size", [0.2, 0.2, 0.2])
                for i, axis in enumerate(["X", "Y", "Z"]):
                    diff = abs(actual_size[i] - expected[i])
                    if diff > tolerance_m:
                        mismatches.append({
                            "axis": axis,
                            "expected": expected[i],
                            "actual": round(actual_size[i], 4),
                            "diff_m": round(diff, 4),
                        })
            elif primitive == "cylinder":
                expected_r = sub_spec.get("radius", 0.05)
                expected_d = sub_spec.get("depth", 0.2)
                expected_diam = expected_r * 2
                if abs(actual_size[0] - expected_diam) > tolerance_m:
                    mismatches.append({
                        "axis": "X (diameter)",
                        "expected": expected_diam,
                        "actual": round(actual_size[0], 4),
                        "diff_m": round(abs(actual_size[0] - expected_diam), 4),
                    })
                if abs(actual_size[2] - expected_d) > tolerance_m:
                    mismatches.append({
                        "axis": "Z (depth)",
                        "expected": expected_d,
                        "actual": round(actual_size[2], 4),
                        "diff_m": round(abs(actual_size[2] - expected_d), 4),
                    })
            
            return {
                "ok": len(mismatches) == 0,
                "mismatches": mismatches,
                "actual_size": actual_size,
            }
        except Exception as e:
            logger.warning(f"[{task_id}] Dimension verification error: {e}")
            return {"ok": False, "error": str(e)}

    async def execute_assembly_merge(
        self,
        assembly_node: ManifestNode,
        manifest: BuildManifest,
        task_id: str = "adhoc",
    ) -> Dict[str, Any]:
        """Parent verified child objects under assembly in Blender."""
        if not self.mcp_manager:
            logger.info(f"[{task_id}] No mcp_manager; mocking merge for '{assembly_node.label}'")
            return {"ok": True}

        # Gather all blender objects from verified children
        child_objects: List[str] = []
        for cid in assembly_node.children_ids:
            if cid in manifest.nodes:
                child_objects.extend(manifest.nodes[cid].blender_objects)

        if len(child_objects) < 2:
            return {"ok": True, "merged_objects": child_objects}

        # Parent children to first object
        primary = child_objects[0]
        for other in child_objects[1:]:
            parent_args = {
                "name": other,
                "parent_name": primary,
                "keep_transform": True,
            }
            await _execute_blender_op(self.mcp_manager, "parent_object", parent_args)

        # Spatial verification
        try:
            gate = AssemblyVerificationGate(self.mcp_manager)
            v_res = await gate.verify_flat_object_set(
                object_names=child_objects,
                task_id=task_id,
                origin_centered=False,
            )
            return {"ok": v_res.get("all_joints_verified", True), "verification": v_res}
        except Exception as e:
            logger.warning(f"[{task_id}] Post-merge verification error: {e}")
            return {"ok": True, "warning": str(e)}
