"""Primitive Readback Test — Verify Blender's interpretation of our parameters.

Run this to establish ground truth for how Blender interprets each primitive type.
Compares requested parameters against actual obj.dimensions and world bounding box.
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class PrimitiveReadback:
    """Result of creating and measuring a primitive."""
    primitive_type: str
    requested: Dict[str, Any]
    actual_dimensions: Tuple[float, float, float]  # obj.dimensions
    world_bbox_min: Tuple[float, float, float]
    world_bbox_max: Tuple[float, float, float]
    origin_in_bbox: Tuple[float, float, float]  # Where origin sits relative to bbox (0-1)
    discrepancies: List[str]


# Script template for creating and measuring a primitive
_READBACK_SCRIPT = '''
import bpy
import json
import mathutils

# Clear existing test objects
for obj in list(bpy.data.objects):
    if obj.name.startswith("_readback_"):
        bpy.data.objects.remove(obj, do_unlink=True)

results = []

# === BOX ===
bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0, 0, 0))
obj = bpy.context.active_object
obj.name = "_readback_box"
# Scale to target size [0.5, 0.3, 0.8] - cube default is 2x2x2 with size=1
target_size = [0.5, 0.3, 0.8]
obj.scale = (target_size[0]/2, target_size[1]/2, target_size[2]/2)
bpy.ops.object.transform_apply(scale=True)
mw = obj.matrix_world
bbox = [mw @ mathutils.Vector(c) for c in obj.bound_box]
bbox_min = [min(c[i] for c in bbox) for i in range(3)]
bbox_max = [max(c[i] for c in bbox) for i in range(3)]
origin = list(obj.location)
results.append({
    "type": "box",
    "requested": {"size": target_size},
    "dimensions": list(obj.dimensions),
    "bbox_min": bbox_min,
    "bbox_max": bbox_max,
    "origin": origin,
})

# === CYLINDER ===
bpy.ops.mesh.primitive_cylinder_add(radius=0.15, depth=1.2, location=(3, 0, 0))
obj = bpy.context.active_object
obj.name = "_readback_cylinder"
mw = obj.matrix_world
bbox = [mw @ mathutils.Vector(c) for c in obj.bound_box]
bbox_min = [min(c[i] for c in bbox) for i in range(3)]
bbox_max = [max(c[i] for c in bbox) for i in range(3)]
origin = list(obj.location)
results.append({
    "type": "cylinder",
    "requested": {"radius": 0.15, "depth": 1.2},
    "dimensions": list(obj.dimensions),
    "bbox_min": bbox_min,
    "bbox_max": bbox_max,
    "origin": origin,
})

# === CYLINDER ROTATED 90° around Y ===
import math
bpy.ops.mesh.primitive_cylinder_add(radius=0.1, depth=0.8, location=(6, 0, 0), rotation=(0, math.radians(90), 0))
obj = bpy.context.active_object
obj.name = "_readback_cylinder_rotated"
mw = obj.matrix_world
bbox = [mw @ mathutils.Vector(c) for c in obj.bound_box]
bbox_min = [min(c[i] for c in bbox) for i in range(3)]
bbox_max = [max(c[i] for c in bbox) for i in range(3)]
origin = list(obj.location)
results.append({
    "type": "cylinder_rotated_90Y",
    "requested": {"radius": 0.1, "depth": 0.8, "rotation_deg": [0, 90, 0]},
    "dimensions": list(obj.dimensions),
    "bbox_min": bbox_min,
    "bbox_max": bbox_max,
    "origin": origin,
    "note": "After 90° Y rotation, depth should be along X, radius along Y and Z",
})

# === SPHERE ===
bpy.ops.mesh.primitive_uv_sphere_add(radius=0.25, location=(9, 0, 0))
obj = bpy.context.active_object
obj.name = "_readback_sphere"
mw = obj.matrix_world
bbox = [mw @ mathutils.Vector(c) for c in obj.bound_box]
bbox_min = [min(c[i] for c in bbox) for i in range(3)]
bbox_max = [max(c[i] for c in bbox) for i in range(3)]
origin = list(obj.location)
results.append({
    "type": "sphere",
    "requested": {"radius": 0.25},
    "dimensions": list(obj.dimensions),
    "bbox_min": bbox_min,
    "bbox_max": bbox_max,
    "origin": origin,
})

# === CONE ===
bpy.ops.mesh.primitive_cone_add(radius1=0.3, depth=0.6, location=(12, 0, 0))
obj = bpy.context.active_object
obj.name = "_readback_cone"
mw = obj.matrix_world
bbox = [mw @ mathutils.Vector(c) for c in obj.bound_box]
bbox_min = [min(c[i] for c in bbox) for i in range(3)]
bbox_max = [max(c[i] for c in bbox) for i in range(3)]
origin = list(obj.location)
results.append({
    "type": "cone",
    "requested": {"radius1": 0.3, "depth": 0.6},
    "dimensions": list(obj.dimensions),
    "bbox_min": bbox_min,
    "bbox_max": bbox_max,
    "origin": origin,
    "note": "Check if origin is at center or base",
})

res = {"ok": True, "primitives": results}
print("SENTINEL_OUTPUT_START" + json.dumps(res) + "SENTINEL_OUTPUT_END")
'''


async def run_primitive_readback(mcp_manager: Any) -> Dict[str, Any]:
    """Execute primitive readback test in Blender.
    
    Returns dict with:
        - primitives: List of readback results
        - summary: Human-readable summary of findings
        - discrepancies: List of any mismatches found
    """
    from core.blender_ops import parse_op_output
    
    result = await mcp_manager.call_locked(
        "blender", "execute_blender_code", {"code": _READBACK_SCRIPT}
    )
    
    data = parse_op_output(result.get("output", ""))
    primitives = data.get("primitives", [])
    
    summary_lines = ["=== PRIMITIVE READBACK RESULTS ===\n"]
    discrepancies = []
    
    for p in primitives:
        ptype = p["type"]
        req = p["requested"]
        dims = p["dimensions"]
        bbox_min = p["bbox_min"]
        bbox_max = p["bbox_max"]
        origin = p["origin"]
        
        # Calculate where origin sits in bbox (0=min, 1=max)
        bbox_size = [bbox_max[i] - bbox_min[i] for i in range(3)]
        origin_rel = [
            (origin[i] - bbox_min[i]) / bbox_size[i] if bbox_size[i] > 0.0001 else 0.5
            for i in range(3)
        ]
        
        summary_lines.append(f"\n{ptype.upper()}:")
        summary_lines.append(f"  Requested: {req}")
        summary_lines.append(f"  obj.dimensions: [{dims[0]:.4f}, {dims[1]:.4f}, {dims[2]:.4f}]")
        summary_lines.append(f"  World bbox: min={[round(v,4) for v in bbox_min]}, max={[round(v,4) for v in bbox_max]}")
        summary_lines.append(f"  Origin position in bbox: [{origin_rel[0]:.2f}, {origin_rel[1]:.2f}, {origin_rel[2]:.2f}]")
        
        if p.get("note"):
            summary_lines.append(f"  Note: {p['note']}")
        
        # Check for discrepancies
        if ptype == "box":
            expected = req["size"]
            for i, axis in enumerate(["X", "Y", "Z"]):
                if abs(dims[i] - expected[i]) > 0.001:
                    disc = f"BOX {axis}: expected {expected[i]}, got {dims[i]}"
                    discrepancies.append(disc)
                    summary_lines.append(f"  ⚠️ {disc}")
            # Origin should be at center (0.5, 0.5, 0.5)
            if any(abs(origin_rel[i] - 0.5) > 0.01 for i in range(3)):
                disc = f"BOX origin not centered: {origin_rel}"
                discrepancies.append(disc)
                
        elif ptype == "cylinder":
            # Dimensions should be [diameter, diameter, depth]
            expected_d = req["radius"] * 2
            expected_depth = req["depth"]
            if abs(dims[0] - expected_d) > 0.001:
                disc = f"CYLINDER X: expected diameter {expected_d}, got {dims[0]}"
                discrepancies.append(disc)
            if abs(dims[2] - expected_depth) > 0.001:
                disc = f"CYLINDER Z (depth): expected {expected_depth}, got {dims[2]}"
                discrepancies.append(disc)
                
        elif ptype == "cylinder_rotated_90Y":
            # After 90° Y rotation: depth along X, radius along Y and Z
            expected_depth = req["depth"]
            expected_d = req["radius"] * 2
            # X should now be depth, Y and Z should be diameter
            if abs(dims[0] - expected_depth) > 0.001:
                disc = f"ROTATED CYLINDER X: expected depth {expected_depth}, got {dims[0]}"
                discrepancies.append(disc)
            if abs(dims[1] - expected_d) > 0.001:
                disc = f"ROTATED CYLINDER Y: expected diameter {expected_d}, got {dims[1]}"
                discrepancies.append(disc)
                
        elif ptype == "sphere":
            expected_d = req["radius"] * 2
            for i, axis in enumerate(["X", "Y", "Z"]):
                if abs(dims[i] - expected_d) > 0.001:
                    disc = f"SPHERE {axis}: expected diameter {expected_d}, got {dims[i]}"
                    discrepancies.append(disc)
                    
        elif ptype == "cone":
            expected_d = req["radius1"] * 2
            expected_depth = req["depth"]
            if abs(dims[2] - expected_depth) > 0.001:
                disc = f"CONE Z (depth): expected {expected_depth}, got {dims[2]}"
                discrepancies.append(disc)
            # Check origin position - is it at center or base?
            summary_lines.append(f"  Origin Z in bbox: {origin_rel[2]:.2f} (0.5=center, 0=base, 1=tip)")
    
    if discrepancies:
        summary_lines.append(f"\n⚠️ DISCREPANCIES FOUND: {len(discrepancies)}")
        for d in discrepancies:
            summary_lines.append(f"  - {d}")
    else:
        summary_lines.append("\n✅ All primitives match expected dimensions")
    
    return {
        "ok": len(discrepancies) == 0,
        "primitives": primitives,
        "summary": "\n".join(summary_lines),
        "discrepancies": discrepancies,
    }


async def verify_built_object_dimensions(
    mcp_manager: Any,
    object_name: str,
    expected_spec: Dict[str, Any],
) -> Dict[str, Any]:
    """Verify a built object's dimensions match the spec.
    
    Args:
        mcp_manager: MCP manager for Blender calls
        object_name: Name of object in Blender
        expected_spec: The sub_spec dict with expected dimensions
        
    Returns:
        Dict with ok, actual, expected, discrepancies
    """
    script = f'''
import bpy
import json
import mathutils

obj = bpy.data.objects.get({repr(object_name)})
if not obj:
    res = {{"ok": False, "error": "Object not found"}}
else:
    mw = obj.matrix_world
    bbox = [mw @ mathutils.Vector(c) for c in obj.bound_box]
    bbox_min = [min(c[i] for c in bbox) for i in range(3)]
    bbox_max = [max(c[i] for c in bbox) for i in range(3)]
    res = {{
        "ok": True,
        "name": obj.name,
        "dimensions": list(obj.dimensions),
        "location": list(obj.location),
        "rotation_euler_deg": [round(r * 57.2958, 2) for r in obj.rotation_euler],
        "bbox_min": bbox_min,
        "bbox_max": bbox_max,
        "matrix_world_translation": list(mw.translation),
    }}
print("SENTINEL_OUTPUT_START" + json.dumps(res) + "SENTINEL_OUTPUT_END")
'''
    from core.blender_ops import parse_op_output
    
    result = await mcp_manager.call_locked(
        "blender", "execute_blender_code", {"code": script}
    )
    data = parse_op_output(result.get("output", ""))
    
    if not data.get("ok"):
        return data
    
    actual_dims = data["dimensions"]
    discrepancies = []
    
    prim = expected_spec.get("primitive", "box")
    
    if prim == "box":
        expected_size = expected_spec.get("size", [1, 1, 1])
        for i, axis in enumerate(["X", "Y", "Z"]):
            diff = abs(actual_dims[i] - expected_size[i])
            if diff > 0.01:  # 1cm tolerance
                discrepancies.append(
                    f"{axis}: expected {expected_size[i]:.3f}m, got {actual_dims[i]:.3f}m (diff={diff:.3f}m)"
                )
                
    elif prim == "cylinder":
        expected_r = expected_spec.get("radius", 0.5)
        expected_d = expected_spec.get("depth", 1.0)
        # Check if rotated - if so, depth might be along different axis
        rot = data.get("rotation_euler_deg", [0, 0, 0])
        
        # For unrotated cylinder: dims = [diameter, diameter, depth]
        if abs(rot[1]) < 1:  # Not rotated around Y
            if abs(actual_dims[2] - expected_d) > 0.01:
                discrepancies.append(
                    f"Depth (Z): expected {expected_d:.3f}m, got {actual_dims[2]:.3f}m"
                )
            if abs(actual_dims[0] - expected_r * 2) > 0.01:
                discrepancies.append(
                    f"Diameter (X): expected {expected_r*2:.3f}m, got {actual_dims[0]:.3f}m"
                )
        else:
            # Rotated 90° around Y: depth along X
            if abs(actual_dims[0] - expected_d) > 0.01:
                discrepancies.append(
                    f"Depth (X after rotation): expected {expected_d:.3f}m, got {actual_dims[0]:.3f}m"
                )
                
    elif prim == "sphere":
        expected_r = expected_spec.get("radius", 0.5)
        expected_d = expected_r * 2
        for i, axis in enumerate(["X", "Y", "Z"]):
            if abs(actual_dims[i] - expected_d) > 0.01:
                discrepancies.append(
                    f"{axis}: expected diameter {expected_d:.3f}m, got {actual_dims[i]:.3f}m"
                )
    
    return {
        "ok": len(discrepancies) == 0,
        "object_name": object_name,
        "expected_spec": expected_spec,
        "actual": {
            "dimensions": actual_dims,
            "location": data["location"],
            "rotation_deg": data["rotation_euler_deg"],
            "world_translation": data["matrix_world_translation"],
        },
        "discrepancies": discrepancies,
    }
