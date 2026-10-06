"""
run_live_clock_eval.py

Runs an end-to-end live test of the Blender Pipeline V2 on a Retro Twin-Bell Alarm Clock.
Components:
- Main Housing Assembly:
  - Cylindrical clock body (cylinder resting horizontally or upright, depth 0.05m, diameter 0.12m)
  - Front glass dial cover (thin circular disc / cylinder on front face)
- Twin Bell Chime Assembly:
  - Left alarm bell dome (spherical dome or hemispherical cup atop upper left)
  - Right alarm bell dome (spherical dome or hemispherical cup atop upper right)
  - Top central carrying handle / striker (bridge / arch between bells)
- Support Feet:
  - Left angled support foot (small peg / cylinder)
  - Right angled support foot (small peg / cylinder)
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
logger = logging.getLogger("live_clock_eval")

CLOCK_PROMPT = (
    "Build a classic vintage twin-bell alarm clock: "
    "1. Main Clock Housing Assembly: "
    "A main cylindrical clock body: a drum cylinder of diameter 0.12m and depth 0.06m oriented horizontally facing forward. "
    "A recessed circular dial face: a thin cylinder of diameter 0.106m and depth 0.005m recessed into the front face of the main body. "
    "2. Twin Chime Bell Assembly (attached to the top of the main clock body): "
    "A left bell dome: a hemisphere dome of diameter 0.045m attached to the top left surface of the main clock body. "
    "A right bell dome: a hemisphere dome of diameter 0.045m attached to the top right surface of the main clock body. "
    "A center striker hammer: a small cylinder of diameter 0.012m and height 0.03m standing vertically between the two bells. "
    "3. Support Feet Assembly (attached to the bottom of the main clock body): "
    "A left peg foot: a small cylinder of diameter 0.012m and length 0.025m attached to the bottom left surface. "
    "A right peg foot: a small cylinder of diameter 0.012m and length 0.025m attached to the bottom right surface."
)

ARTIFACT_DIR = Path(r"C:\Users\derik\.gemini\antigravity\brain\1f90b81f-c78f-48cc-a929-061484d5f2c8\clock_eval")

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
key.location = center + Vector((extent * 1.2, -extent * 1.2, extent * 1.5))

fill_data = bpy.data.lights.new("EvalFillData", "AREA")
fill_data.energy = 600
fill_data.shape = 'DISK'
fill_data.size = max(extent * 2.0, 1.0)
fill = bpy.data.objects.new("EvalFill", fill_data)
bpy.context.scene.collection.objects.link(fill)
fill.location = center + Vector((-extent * 1.2, extent * 1.2, extent * 0.5))

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
    "isometric": (center, Vector((1.2, -1.2, 0.8)).normalized(), extent * 1.4),
    "front": (center, Vector((0.0, -1.0, 0.05)).normalized(), extent * 1.4),
    "top": (center, Vector((0.001, -0.001, 1.0)).normalized(), extent * 1.4),
    "side": (center, Vector((1.0, 0.0, 0.05)).normalized(), extent * 1.4),
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
    print("  LIVE RETRO TWIN-BELL ALARM CLOCK PROGRESSIVE BUILD & AUDIT")
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

    task_id = f"live_clock_{int(time.time())}"
    print(f"Starting progressive build task: {task_id}")
    print(f"Prompt:\n  {CLOCK_PROMPT}\n")

    t0 = time.time()
    result = await run_progressive_build(
        prompt=CLOCK_PROMPT,
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

    # Mathematical readback from Blender for clock objects
    inspect_script = f'''
import bpy, json, math
from mathutils import Vector
import bmesh

coll = bpy.data.collections.get("Collection_{result.model_id}")
meshes = [o for o in (coll.all_objects if coll else bpy.data.objects) if o.type == 'MESH']
audit_data = []
for o in meshes:
    corners = [o.matrix_world @ Vector(c) for c in o.bound_box]
    min_c = [min(v[i] for v in corners) for i in range(3)]
    max_c = [max(v[i] for v in corners) for i in range(3)]
    dim = [max_c[i] - min_c[i] for i in range(3)]
    center = [o.matrix_world.translation[i] for i in range(3)]
    rot_deg = [math.degrees(a) for a in o.matrix_world.to_euler()]
    
    bm = bmesh.new()
    bm.from_mesh(o.data)
    non_m_edges = sum(1 for e in bm.edges if not e.is_manifold)
    non_m_verts = sum(1 for v in bm.verts if not v.is_manifold)
    bm.free()
    
    audit_data.append({{
        "name": o.name,
        "center": [round(c, 4) for c in center],
        "dimensions": [round(d, 4) for d in dim],
        "rotation_deg": [round(r, 2) for r in rot_deg],
        "is_manifold": (non_m_edges == 0 and non_m_verts == 0),
        "non_manifold_edges": non_m_edges,
        "poly_count": len(o.data.polygons),
        "vertex_count": len(o.data.vertices),
    }})

print("===AUDIT_START===")
print(json.dumps(audit_data))
print("===AUDIT_END===")
'''
    raw_insp = await mcp.call_locked("blender", "execute_blender_code", {"code": inspect_script})
    out = raw_insp.get("output", "")
    audit_data = []
    if "===AUDIT_START===" in out:
        part = out.split("===AUDIT_START===")[1].split("===AUDIT_END===")[0].strip()
        audit_data = json.loads(part)
    
    print("\nMATHEMATICAL AUDIT DATA:")
    print(json.dumps(audit_data, indent=2))

    # Render multi-view camera shots
    print("\nRendering camera views...")
    render_res = await render_custom_camera_views(mcp, f"Collection_{result.model_id}", ARTIFACT_DIR)
    print("Render completed:", render_res)

    audit_path = ARTIFACT_DIR / "live_clock_audit.json"
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
        "readback": audit_data,
    }, indent=2))
    print(f"Saved audit json to {audit_path}")

if __name__ == "__main__":
    asyncio.run(main())
