"""
run_live_stool_eval.py

Runs an end-to-end live test of the Blender Pipeline V2 on a Modern Industrial Bar Stool.
Components:
- Circular footrest base ring (torus/cylinder base) or 4 angled cylindrical legs
- Footrest stretcher ring (horizontal torus/cylinder)
- Central mounting hub / top frame
- Circular seat cushion (cylinder)
"""

import asyncio
import json
import logging
import os
import shutil
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("live_stool_eval")

STOOL_PROMPT = (
    "Build a modern industrial bar stool with a circular seat cushion: "
    "1. Base Frame Assembly: "
    "A circular steel foot ring base: a horizontal torus or ring of major radius 0.22m and tube radius 0.015m resting flat on the ground. "
    "A central vertical support column: a vertical cylinder of diameter 0.06m and height 0.65m centered directly on top of the base ring. "
    "A circular footrest ring: a horizontal ring of major radius 0.18m and tube radius 0.012m mounted around the support column at height 0.25m. "
    "2. Seat Assembly (attached to the top end of the central support column): "
    "A circular wooden seat plate: a cylinder of diameter 0.34m and height 0.03m resting flat horizontally on top of the support column. "
    "An upholstered round seat cushion: a soft cylinder of diameter 0.32m and height 0.05m attached directly to the top face of the wooden seat plate."
)

ARTIFACT_DIR = Path(r"C:\Users\derik\.gemini\antigravity\brain\1f90b81f-c78f-48cc-a929-061484d5f2c8\stool_eval")

async def render_custom_camera_views(mcp, collection_name: str, output_dir: Path):
    """Render high-res multi-view cameras from Blender."""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    script = f'''
import bpy, json, math
from mathutils import Vector

coll = bpy.data.collections.get({collection_name!r})
if not coll:
    for c in bpy.data.collections:
        if "Sentinel" in c.name:
            coll = c
            break

meshes = [o for o in (coll.all_objects if coll else bpy.data.objects) if o.type == 'MESH' and not o.hide_render]
if not meshes:
    raise RuntimeError("No renderable meshes found")

corners = []
for o in meshes:
    corners.extend([o.matrix_world @ Vector(c) for c in o.bound_box])
lo = Vector((min(v.x for v in corners), min(v.y for v in corners), min(v.z for v in corners)))
hi = Vector((max(v.x for v in corners), max(v.y for v in corners), max(v.z for v in corners)))
center = (lo + hi) * 0.5
extent = max((hi - lo).length, 0.1)

cam_data = bpy.data.cameras.new("EvalCameraData")
cam = bpy.data.objects.new("EvalCamera", cam_data)
bpy.context.scene.collection.objects.link(cam)
bpy.context.scene.camera = cam
cam_data.lens = 50

# Lighting setup
key_data = bpy.data.lights.new("EvalKeyData", "AREA")
key_data.energy = 1400
key_data.shape = 'DISK'
key_data.size = max(extent * 1.5, 1.0)
key = bpy.data.objects.new("EvalKey", key_data)
bpy.context.scene.collection.objects.link(key)
key.location = center + Vector((extent, -extent, extent * 1.5))

fill_data = bpy.data.lights.new("EvalFillData", "AREA")
fill_data.energy = 600
fill_data.shape = 'DISK'
fill_data.size = max(extent * 2.0, 1.0)
fill = bpy.data.objects.new("EvalFill", fill_data)
bpy.context.scene.collection.objects.link(fill)
fill.location = center + Vector((-extent, extent, extent * 0.5))

scene = bpy.context.scene
scene.render.engine = 'BLENDER_EEVEE_NEXT'
scene.render.resolution_x = 1024
scene.render.resolution_y = 1024
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = 'PNG'
scene.render.film_transparent = False

world = scene.world or bpy.data.worlds.new("EvalWorld")
scene.world = world
world.color = (0.05, 0.05, 0.06)

views = {{
    "isometric": (center, Vector((1.0, -1.0, 0.8)).normalized(), extent * 1.35),
    "front": (center, Vector((0.0, -1.0, 0.15)).normalized(), extent * 1.35),
    "top": (center, Vector((0.001, -0.001, 1.0)).normalized(), extent * 1.35),
    "side": (center, Vector((1.0, 0.0, 0.15)).normalized(), extent * 1.35),
}}

out_paths = {{}}
base_dir = {str(output_dir).replace(chr(92), '/')!r}
for name, (tgt, direction, dist) in views.items():
    cam.location = tgt + direction * dist
    cam.rotation_euler = (tgt - cam.location).to_track_quat('-Z', 'Y').to_euler()
    p = f"{{base_dir}}/{{name}}.png"
    scene.render.filepath = p
    bpy.ops.render.render(write_still=True)
    out_paths[name] = p

bpy.data.objects.remove(cam, do_unlink=True)
bpy.data.cameras.remove(cam_data)
bpy.data.objects.remove(key, do_unlink=True)
bpy.data.lights.remove(key_data)
bpy.data.objects.remove(fill, do_unlink=True)
bpy.data.lights.remove(fill_data)

print("SENTINEL_OUTPUT_START" + json.dumps({{"ok": True, "paths": out_paths, "center": list(center), "extent": extent}}) + "SENTINEL_OUTPUT_END")
'''
    from core.blender_ops import parse_op_output
    res = await mcp.call_locked("blender", "execute_blender_code", {"code": script})
    return parse_op_output(res.get("output", ""))

async def main():
    from config.loader import load_system_config, load_model_registry
    from core.model_manager import ModelManager
    from core.mcp_manager import MCPManager
    from core.blender_pipeline.progressive_v2.controller import run_progressive_build

    print("======================================================================")
    print("  LIVE BAR STOOL PROGRESSIVE BUILD & REAL-WORLD AUDIT")
    print("======================================================================")

    mcp = MCPManager()
    mcp.initialize_from_config()
    print("Connecting to Blender MCP...")
    await mcp.connect_app("blender")
    print("Connected to Blender MCP.")

    config = load_system_config()
    registry = load_model_registry()
    model_manager = ModelManager(config, registry)
    print("ModelManager initialized.")

    task_id = f"live_stool_{int(time.time())}"
    print(f"Starting progressive build task: {task_id}")
    print(f"Prompt:\n  {STOOL_PROMPT}\n")

    t0 = time.time()
    result = await run_progressive_build(
        prompt=STOOL_PROMPT,
        model_manager=model_manager,
        task_id=task_id,
        mcp_manager=mcp,
        preserve_scene=True,
    )
    duration = time.time() - t0

    print("======================================================================")
    print(f"Build Finished in {duration:.2f}s")
    print(f"Status: {result.completion_status}")
    print(f"Success: {result.success}")
    print(f"Total Nodes: {result.total_nodes}")
    print(f"Verified Nodes: {result.verified_nodes}")
    print(f"Blender Objects: {result.blender_objects}")
    print(f"Errors: {result.errors}")
    print("======================================================================")

    # Mathematical readback from Blender
    inspect_script = '''
import bpy, json
from mathutils import Vector

meshes = [o for o in bpy.data.objects if o.type == 'MESH']
audit_data = []
for o in meshes:
    corners = [o.matrix_world @ Vector(c) for c in o.bound_box]
    min_c = [min(v[i] for v in corners) for i in range(3)]
    max_c = [max(v[i] for v in corners) for i in range(3)]
    dim = [max_c[i] - min_c[i] for i in range(3)]
    center = [o.matrix_world.translation[i] for i in range(3)]
    rot_deg = [math.degrees(a) for a in o.matrix_world.to_euler()]
    
    # Check manifoldness
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(o.data)
    non_manifold_edges = sum(1 for e in bm.edges if not e.is_manifold)
    non_manifold_verts = sum(1 for v in bm.verts if not v.is_manifold)
    bm.free()
    
    audit_data.append({
        "name": o.name,
        "center": [round(c, 4) for c in center],
        "dimensions": [round(d, 4) for d in dim],
        "rotation_deg": [round(r, 2) for r in rot_deg],
        "is_manifold": (non_manifold_edges == 0 and non_manifold_verts == 0),
        "non_manifold_edges": non_manifold_edges,
        "poly_count": len(o.data.polygons),
        "vertex_count": len(o.data.vertices),
    })

print("SENTINEL_OUTPUT_START" + json.dumps({"meshes": audit_data, "total_meshes": len(meshes)}) + "SENTINEL_OUTPUT_END")
'''
    from core.blender_ops import parse_op_output
    raw_insp = await mcp.call_locked("blender", "execute_blender_code", {"code": inspect_script})
    parsed_insp = parse_op_output(raw_insp.get("output", ""))
    
    print("\nMATHEMATICAL AUDIT DATA:")
    print(json.dumps(parsed_insp, indent=2))

    # Render multi-view camera shots
    print("\nRendering camera views...")
    render_res = await render_custom_camera_views(mcp, f"Collection_{result.model_id}", ARTIFACT_DIR)
    print("Render completed:", render_res)

    audit_path = ARTIFACT_DIR / "live_stool_audit.json"
    audit_path.write_text(json.dumps({
        "task_id": task_id,
        "model_id": result.model_id,
        "duration": duration,
        "status": str(result.completion_status),
        "success": result.success,
        "total_nodes": result.total_nodes,
        "verified_nodes": result.verified_nodes,
        "blender_objects": result.blender_objects,
        "errors": result.errors,
        "readback": parsed_insp,
    }, indent=2))
    print(f"Saved audit json to {audit_path}")

if __name__ == "__main__":
    asyncio.run(main())
