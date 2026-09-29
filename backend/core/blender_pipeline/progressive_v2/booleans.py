"""Boolean Operations Manager — CSG operations for complex geometry.

Complex builds need boolean operations:
- DIFFERENCE: Cut holes (portholes, slots, windows)
- UNION: Merge parts into single mesh
- INTERSECT: Keep only overlapping region

CRITICAL: Boolean operations must complete BEFORE modifiers are applied.
The build order is: Create geometry → Booleans → Modifiers → Verify

Blueprint reference: §12 (Assembly Merge with booleans).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .manifest import BuildManifest, ManifestNode

logger = logging.getLogger(__name__)


class BooleanOperation(str, Enum):
    """Boolean operation types."""
    DIFFERENCE = "DIFFERENCE"  # A - B (cut B from A)
    UNION = "UNION"            # A + B (merge)
    INTERSECT = "INTERSECT"    # A ∩ B (keep overlap)


@dataclass
class BooleanSpec:
    """Specification for a boolean operation."""
    target_object: str      # Object to modify (receives the boolean)
    tool_object: str        # Object used as tool (cutter/merger)
    operation: BooleanOperation
    delete_tool: bool = True  # Delete tool object after operation
    
    # Advanced options
    solver: str = "FAST"    # FAST or EXACT
    use_self: bool = False  # Allow self-intersection


@dataclass
class BooleanResult:
    """Result of a boolean operation."""
    ok: bool
    target_object: str
    operation: BooleanOperation
    poly_count_before: int = 0
    poly_count_after: int = 0
    geometry_changed: bool = False
    error: Optional[str] = None


class BooleanManager:
    """Manages boolean operations between objects.
    
    Usage:
        manager = BooleanManager(mcp_manager)
        
        # Cut a hole
        result = await manager.apply_boolean(BooleanSpec(
            target_object="hull",
            tool_object="porthole_cutter",
            operation=BooleanOperation.DIFFERENCE,
        ))
        
        # Merge parts
        result = await manager.apply_boolean(BooleanSpec(
            target_object="body",
            tool_object="attachment",
            operation=BooleanOperation.UNION,
        ))
    """
    
    def __init__(self, mcp_manager: Any):
        self.mcp_manager = mcp_manager
    
    async def apply_boolean(
        self,
        spec: BooleanSpec,
        task_id: str = "",
    ) -> BooleanResult:
        """Apply a single boolean operation."""
        from core.blender_ops import parse_op_output
        
        script = f'''
import bpy
import json

target_name = {repr(spec.target_object)}
tool_name = {repr(spec.tool_object)}
operation = {repr(spec.operation.value)}
delete_tool = {spec.delete_tool}
solver = {repr(spec.solver)}

target = bpy.data.objects.get(target_name)
tool = bpy.data.objects.get(tool_name)

if not target:
    result = {{"ok": False, "error": f"Target '{{target_name}}' not found"}}
elif not tool:
    result = {{"ok": False, "error": f"Tool '{{tool_name}}' not found"}}
elif target_name == tool_name:
    result = {{"ok": False, "error": "Cannot boolean object with itself"}}
elif target.type != 'MESH' or tool.type != 'MESH':
    result = {{"ok": False, "error": "Both objects must be meshes"}}
else:
    # Record pre-boolean state
    pre_poly = len(target.data.polygons)
    pre_vert = len(target.data.vertices)
    
    # Apply boolean
    bpy.ops.object.select_all(action='DESELECT')
    target.select_set(True)
    bpy.context.view_layer.objects.active = target
    
    mod = target.modifiers.new(name="Boolean", type='BOOLEAN')
    mod.operation = operation
    mod.object = tool
    mod.solver = solver
    
    try:
        bpy.ops.object.modifier_apply(modifier=mod.name)
        
        # Check if geometry changed
        post_poly = len(target.data.polygons)
        post_vert = len(target.data.vertices)
        changed = (post_poly != pre_poly or post_vert != pre_vert)
        
        if delete_tool:
            bpy.data.objects.remove(tool, do_unlink=True)
        
        if not changed:
            result = {{
                "ok": False,
                "error": f"Boolean {{operation}} had no effect (objects may not intersect)",
                "poly_before": pre_poly,
                "poly_after": post_poly,
                "changed": False,
            }}
        else:
            result = {{
                "ok": True,
                "poly_before": pre_poly,
                "poly_after": post_poly,
                "changed": True,
            }}
    except Exception as e:
        result = {{"ok": False, "error": str(e)}}

print("SENTINEL_OUTPUT_START" + json.dumps(result) + "SENTINEL_OUTPUT_END")
'''
        try:
            result = await self.mcp_manager.call_locked(
                "blender", "execute_blender_code", {"code": script}
            )
            data = parse_op_output(result.get("output", ""))
            
            return BooleanResult(
                ok=data.get("ok", False),
                target_object=spec.target_object,
                operation=spec.operation,
                poly_count_before=data.get("poly_before", 0),
                poly_count_after=data.get("poly_after", 0),
                geometry_changed=data.get("changed", False),
                error=data.get("error"),
            )
            
        except Exception as e:
            return BooleanResult(
                ok=False,
                target_object=spec.target_object,
                operation=spec.operation,
                error=str(e),
            )
    
    async def apply_boolean_chain(
        self,
        target_object: str,
        tools: List[tuple],  # List of (tool_name, operation)
        task_id: str = "",
    ) -> List[BooleanResult]:
        """Apply multiple boolean operations to one target.
        
        More efficient than individual calls for complex parts.
        
        Args:
            target_object: Object to modify
            tools: List of (tool_object_name, BooleanOperation) tuples
        """
        results = []
        
        for tool_name, operation in tools:
            spec = BooleanSpec(
                target_object=target_object,
                tool_object=tool_name,
                operation=operation,
            )
            result = await self.apply_boolean(spec, task_id)
            results.append(result)
            
            # Stop on first failure
            if not result.ok:
                break
        
        return results
    
    async def create_cutter(
        self,
        name: str,
        primitive: str,
        dimensions: Dict[str, Any],
        position: List[float],
        rotation: List[float] = None,
        task_id: str = "",
    ) -> Dict[str, Any]:
        """Create a cutter object for boolean operations.
        
        Cutters are temporary objects used to cut holes, then deleted.
        """
        from core.blender_ops import parse_op_output
        
        rotation = rotation or [0, 0, 0]
        
        if primitive == "cylinder":
            radius = dimensions.get("radius", 0.1)
            depth = dimensions.get("depth", 0.5)
            script = f'''
import bpy
import json
import math

bpy.ops.mesh.primitive_cylinder_add(
    radius={radius}, depth={depth},
    location=tuple({position}),
    rotation=tuple(math.radians(r) for r in {rotation})
)
obj = bpy.context.active_object
obj.name = {repr(name)}
obj.data.name = {repr(name)}
result = {{"ok": True, "name": obj.name}}
print("SENTINEL_OUTPUT_START" + json.dumps(result) + "SENTINEL_OUTPUT_END")
'''
        elif primitive == "box":
            size = dimensions.get("size", [0.1, 0.1, 0.1])
            script = f'''
import bpy
import bmesh
import json
import math

mesh = bpy.data.meshes.new({repr(name)})
bm = bmesh.new()
bmesh.ops.create_cube(bm, size=1.0)
size = {size}
for v in bm.verts:
    v.co.x *= size[0]
    v.co.y *= size[1]
    v.co.z *= size[2]
bm.to_mesh(mesh)
bm.free()

obj = bpy.data.objects.new({repr(name)}, mesh)
obj.location = tuple({position})
obj.rotation_euler = tuple(math.radians(r) for r in {rotation})
bpy.context.collection.objects.link(obj)
result = {{"ok": True, "name": obj.name}}
print("SENTINEL_OUTPUT_START" + json.dumps(result) + "SENTINEL_OUTPUT_END")
'''
        elif primitive == "sphere":
            radius = dimensions.get("radius", 0.1)
            script = f'''
import bpy
import json

bpy.ops.mesh.primitive_uv_sphere_add(
    radius={radius},
    location=tuple({position})
)
obj = bpy.context.active_object
obj.name = {repr(name)}
obj.data.name = {repr(name)}
result = {{"ok": True, "name": obj.name}}
print("SENTINEL_OUTPUT_START" + json.dumps(result) + "SENTINEL_OUTPUT_END")
'''
        else:
            return {"ok": False, "error": f"Unknown primitive: {primitive}"}
        
        try:
            result = await self.mcp_manager.call_locked(
                "blender", "execute_blender_code", {"code": script}
            )
            return parse_op_output(result.get("output", ""))
        except Exception as e:
            return {"ok": False, "error": str(e)}
    
    async def cut_holes(
        self,
        target_object: str,
        holes: List[Dict[str, Any]],
        task_id: str = "",
    ) -> List[BooleanResult]:
        """Cut multiple holes in an object.
        
        Convenience method for common pattern of cutting circular holes.
        
        Args:
            target_object: Object to cut holes in
            holes: List of hole specs, each with:
                - position: [x, y, z]
                - radius: float
                - depth: float
                - rotation: [rx, ry, rz] (optional)
        """
        results = []
        
        for i, hole in enumerate(holes):
            # Create cutter
            cutter_name = f"_cutter_{target_object}_{i}"
            cutter_result = await self.create_cutter(
                name=cutter_name,
                primitive="cylinder",
                dimensions={
                    "radius": hole.get("radius", 0.1),
                    "depth": hole.get("depth", 0.5),
                },
                position=hole.get("position", [0, 0, 0]),
                rotation=hole.get("rotation"),
                task_id=task_id,
            )
            
            if not cutter_result.get("ok"):
                results.append(BooleanResult(
                    ok=False,
                    target_object=target_object,
                    operation=BooleanOperation.DIFFERENCE,
                    error=f"Failed to create cutter: {cutter_result.get('error')}",
                ))
                continue
            
            # Apply boolean
            result = await self.apply_boolean(
                BooleanSpec(
                    target_object=target_object,
                    tool_object=cutter_name,
                    operation=BooleanOperation.DIFFERENCE,
                    delete_tool=True,
                ),
                task_id=task_id,
            )
            results.append(result)
        
        return results


def get_boolean_specs_from_node(
    node: "ManifestNode",
    manifest: "BuildManifest",
) -> List[BooleanSpec]:
    """Extract boolean operations needed for a node from its attachment spec.
    
    Looks at node.attachment.join_mode to determine if booleans are needed.
    """
    from .node_types import NodeKind
    
    specs = []
    
    if not node.attachment:
        return specs
    
    join_mode = node.attachment.join_mode if hasattr(node.attachment, 'join_mode') else None
    
    if join_mode == "BOOLEAN_DIFFERENCE":
        # This node should be subtracted from parent
        if node.parent_id:
            parent = manifest.nodes.get(node.parent_id)
            if parent and parent.blender_objects:
                for node_obj in node.blender_objects:
                    specs.append(BooleanSpec(
                        target_object=parent.blender_objects[0],
                        tool_object=node_obj,
                        operation=BooleanOperation.DIFFERENCE,
                    ))
    
    elif join_mode == "FUSE" or join_mode == "BOOLEAN_UNION":
        # This node should be merged with parent
        if node.parent_id:
            parent = manifest.nodes.get(node.parent_id)
            if parent and parent.blender_objects:
                for node_obj in node.blender_objects:
                    specs.append(BooleanSpec(
                        target_object=parent.blender_objects[0],
                        tool_object=node_obj,
                        operation=BooleanOperation.UNION,
                    ))
    
    return specs
