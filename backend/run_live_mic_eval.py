"""
run_live_mic_eval.py

Runs an end-to-end live test of the Blender Pipeline V2 on the Studio Broadcast Condenser Microphone.
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
logger = logging.getLogger("live_mic_eval")

MIC_PROMPT = (
    "Build a professional studio broadcast condenser microphone mounted on a desk stand: "
    "1. Desk Stand Assembly: "
    "A circular steel base plate: a low, wide cylinder of diameter 0.14m and height 0.015m resting flat on the ground. "
    "A vertical support riser stem: a slender cylinder of diameter 0.02m and height 0.16m centered directly on top of the base plate. "
    "2. Microphone Body Assembly (attached to the top of the support riser stem): "
    "A lower cylindrical acoustic body: a cylinder of diameter 0.048m and height 0.11m sitting vertically on the riser stem. "
    "An upper capsule mesh grille: a dome capsule of diameter 0.048m and height 0.07m attached directly on the top face of the lower body. "
    "A rotary gain knob: a small cylinder of diameter 0.012m and depth 0.008m attached to the front face of the lower acoustic body."
)

ARTIFACT_DIR = Path(r"C:\Users\derik\.gemini\antigravity\brain\1f90b81f-c78f-48cc-a929-061484d5f2c8\mic_eval")

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
    print("  LIVE STUDIO MICROPHONE PROGRESSIVE BUILD & REAL-WORLD AUDIT")
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

    task_id = f"live_mic_{int(time.time())}"
    print(f"Starting progressive build task: {task_id}")
    print(f"Prompt:\n  {MIC_PROMPT}\n")

    t0 = time.time()
    result = await run_progressive_build(
        prompt=MIC_PROMPT,
        model_manager=model_manager,
        task_id=task_id,
        mcp_manager=mcp,
        preserve_scene=True,
    )
    t1 = time.time()
    print(f"\nBuild finished in {t1 - t0:.2f}s")
    print(f"Completion Status: {result.completion_status}")
    print(f"Success: {result.success}")
    print(f"Total Nodes: {result.total_nodes}, Verified: {result.verified_nodes}, Failed: {result.failed_nodes}, Skipped: {result.skipped_nodes}")
    print(f"Errors: {result.errors}")

    manifest = result.manifest
    model_id = manifest.model_id
    build_dir = Path("backend/data/builds_v2") / model_id
    print(f"Build artifacts directory: {build_dir}")

    # Check live objects in Blender
    check_code = """
import bpy, json
objs = [{"name": o.name, "type": o.type, "loc": list(o.location), "dims": list(o.dimensions)} for o in bpy.data.objects if o.type == 'MESH']
colls = [c.name for c in bpy.data.collections]
result = {"ok": True, "mesh_count": len(objs), "meshes": objs, "collections": colls}
print("SENTINEL_OUTPUT_START" + json.dumps(result) + "SENTINEL_OUTPUT_END")
"""
    from core.blender_ops import parse_op_output
    check_res = await mcp.call_locked("blender", "execute_blender_code", {"code": check_code})
    parsed_check = parse_op_output(check_res.get("output", ""))
    print(f"\n--- LIVE BLENDER SCENE CHECK ---")
    print(f"Live Blender Mesh Objects Preserved: {parsed_check.get('mesh_count')}")
    for m in parsed_check.get("meshes", []):
        dims = [round(v, 4) for v in m.get("dims", [])]
        loc = [round(v, 4) for v in m.get("loc", [])]
        print(f"  - {m['name']}: pos={loc}, dims={dims}")

    collection_name = manifest.stats.get("build_collection") or f"SentinelBuild_{task_id}"
    for coll in parsed_check.get("collections", []):
        if "Sentinel" in coll:
            collection_name = coll
            break

    render_res = {}
    if parsed_check.get("mesh_count", 0) > 0:
        print(f"\nRendering high-res views for collection: {collection_name}...")
        render_out_dir = ARTIFACT_DIR
        try:
            render_res = await render_custom_camera_views(mcp, collection_name, render_out_dir)
            print("Render result:", render_res)
        except Exception as e:
            print(f"Custom camera rendering error: {e}")

    print("\nLive test complete!")

if __name__ == "__main__":
    asyncio.run(main())
