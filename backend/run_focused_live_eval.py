"""
run_focused_live_eval.py

Runs an end-to-end live test in Blender 4.5.3 LTS via MCP for the focused drone mechanism:
- Central mounting block
- Horizontal cylindrical arm with a flat, horizontal circular ring rotor guard attached at its end
- Downward-facing U-bracket with a spherical camera lens suspended between the forks

Verifies:
1. Complete scene cleanup before build.
2. Progressive build execution with preserve_scene=True.
3. Mathematical readback of parts, bounds, orientations, and scene quality audit.
4. Multi-angle and close-up camera renders with calibrated lighting.
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
logger = logging.getLogger("focused_live_eval")

PROMPT = (
    "Build a drone mechanism: A central mounting block. "
    "Extending horizontally from the block is a cylindrical arm with a flat, horizontal circular ring rotor guard attached at its end. "
    "Underneath the block, attach a downward-facing U-bracket with a spherical camera lens suspended inside it resting perfectly between the forks of the U."
)

ARTIFACT_DIR = Path(r"C:\Users\derik\.gemini\antigravity\brain\1f90b81f-c78f-48cc-a929-061484d5f2c8\focused_eval")
ROOT_ARTIFACT_DIR = Path(r"C:\Users\derik\.gemini\antigravity\brain\1f90b81f-c78f-48cc-a929-061484d5f2c8")

async def clean_blender_scene(mcp):
    """Ensure Blender scene has no leftover objects or collections."""
    clean_script = '''
import bpy, json
for obj in list(bpy.data.objects):
    bpy.data.objects.remove(obj, do_unlink=True)
for col in list(bpy.data.collections):
    bpy.data.collections.remove(col)
for mesh in list(bpy.data.meshes):
    bpy.data.meshes.remove(mesh)
for mat in list(bpy.data.materials):
    bpy.data.materials.remove(mat)
print("SENTINEL_OUTPUT_START" + json.dumps({"ok": True, "remaining": len(bpy.data.objects)}) + "SENTINEL_OUTPUT_END")
'''
    from core.blender_ops import parse_op_output
    res = await mcp.call_locked("blender", "execute_blender_code", {"code": clean_script})
    logger.info(f"Clean scene result: {res.get('output', '')}")

async def render_custom_camera_views(mcp, collection_name: str, output_dir: Path):
    """Render multi-view and targeted close-ups with studio-quality calibrated lighting."""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    script = f'''
import bpy, json, math
from mathutils import Vector

coll = bpy.data.collections.get({collection_name!r})
if not coll:
    for c in bpy.data.collections:
        if "SentinelBuild" in c.name:
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

# Find specific parts for closeups
lens_obj = None
arm_obj = None
bracket_obj = None
guard_obj = None

for o in meshes:
    name_lower = o.name.lower()
    if "lens" in name_lower or "camera" in name_lower:
        lens_obj = o
    elif "bracket" in name_lower or "fork" in name_lower or "u_shape" in name_lower:
        bracket_obj = o
    elif "guard" in name_lower or "ring" in name_lower or "torus" in name_lower:
        guard_obj = o
    elif "arm" in name_lower:
        arm_obj = o

cam_data = bpy.data.cameras.new("FocusedEvalCamData")
cam = bpy.data.objects.new("FocusedEvalCam", cam_data)
bpy.context.scene.collection.objects.link(cam)
bpy.context.scene.camera = cam
cam_data.lens = 55

# Studio Calibrated Lighting (Soft Key + Rim/Fill)
key_data = bpy.data.lights.new("EvalKeyData", "AREA")
key_data.energy = 120.0
key_data.shape = 'DISK'
key_data.size = max(extent * 1.5, 0.8)
key = bpy.data.objects.new("EvalKey", key_data)
bpy.context.scene.collection.objects.link(key)
key.location = center + Vector((extent * 0.9, -extent * 1.1, extent * 1.2))

fill_data = bpy.data.lights.new("EvalFillData", "AREA")
fill_data.energy = 40.0
fill_data.size = max(extent * 2.0, 1.0)
fill = bpy.data.objects.new("EvalFill", fill_data)
bpy.context.scene.collection.objects.link(fill)
fill.location = center + Vector((-extent * 1.0, extent * 0.9, extent * 0.6))

scene = bpy.context.scene
scene.render.engine = 'BLENDER_EEVEE_NEXT'
scene.render.resolution_x = 1024
scene.render.resolution_y = 1024
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = 'PNG'
scene.render.film_transparent = False

world = scene.world or bpy.data.worlds.new("EvalWorld")
scene.world = world
world.color = (0.04, 0.04, 0.05)

views = {{
    "isometric": (center, Vector((1.0, -1.0, 0.8)).normalized(), extent * 1.4),
    "front": (center, Vector((0.0, -1.0, 0.15)).normalized(), extent * 1.35),
    "top": (center, Vector((0.001, -0.001, 1.0)).normalized(), extent * 1.35),
    "side": (center, Vector((1.0, 0.0, 0.2)).normalized(), extent * 1.35),
    "bottom_up": (center, Vector((0.3, -0.8, -0.7)).normalized(), extent * 1.25),
}}

target_bracket_lens = lens_obj or bracket_obj
if target_bracket_lens:
    t_center = target_bracket_lens.matrix_world.translation
    t_extent = max(target_bracket_lens.dimensions.length, 0.06)
    views["closeup_lens_bracket"] = (t_center, Vector((0.4, -0.9, -0.2)).normalized(), t_extent * 3.2)

target_arm_guard = guard_obj or arm_obj
if target_arm_guard:
    ag_center = target_arm_guard.matrix_world.translation
    ag_extent = max(target_arm_guard.dimensions.length, 0.06)
    views["closeup_arm_guard"] = (ag_center, Vector((0.7, -0.7, 0.5)).normalized(), ag_extent * 2.8)

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

print("SENTINEL_OUTPUT_START" + json.dumps({{"ok": True, "paths": out_paths}}) + "SENTINEL_OUTPUT_END")
'''
    from core.blender_ops import parse_op_output
    res = await mcp.call_locked("blender", "execute_blender_code", {"code": script})
    return parse_op_output(res.get("output", ""))

async def query_live_scene_details(mcp, collection_name: str):
    """Query live Blender mesh objects with exact transforms, bounds, and materials."""
    script = f'''
import bpy, json
from mathutils import Vector

coll = bpy.data.collections.get({collection_name!r})
if not coll:
    for c in bpy.data.collections:
        if "SentinelBuild" in c.name:
            coll = c
            break

objects = coll.all_objects if coll else bpy.data.objects
parts = []
for obj in objects:
    if obj.type != 'MESH':
        continue
    mat_names = [slot.material.name for slot in obj.material_slots if slot.material]
    corners = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    min_pt = [min(v[i] for v in corners) for i in range(3)]
    max_pt = [max(v[i] for v in corners) for i in range(3)]
    parts.append({{
        "name": obj.name,
        "location": [round(c, 5) for c in obj.location],
        "rotation_euler": [round(c, 5) for c in obj.rotation_euler],
        "dimensions": [round(c, 5) for c in obj.dimensions],
        "world_bounds": {{
            "min": [round(c, 5) for c in min_pt],
            "max": [round(c, 5) for c in max_pt],
            "center": [round((min_pt[i] + max_pt[i]) / 2, 5) for i in range(3)],
        }},
        "materials": mat_names,
    }})

print("SENTINEL_OUTPUT_START" + json.dumps({{"ok": True, "parts": parts, "collection": coll.name if coll else None}}) + "SENTINEL_OUTPUT_END")
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
    print("  FOCUSED LIVE TEST: ARM + GUARD RING & U-BRACKET + SUSPENDED LENS")
    print("======================================================================")

    # 1. Connect to MCP
    mcp = MCPManager()
    mcp.initialize_from_config()
    print("Connecting to Blender MCP...")
    await mcp.connect_app("blender")
    print("Connected to Blender MCP.")

    # 2. Clean scene
    print("Cleaning existing Blender scene...")
    await clean_blender_scene(mcp)

    # 3. ModelManager
    config = load_system_config()
    registry = load_model_registry()
    model_manager = ModelManager(config, registry)

    task_id = f"focused_drone_{int(time.time())}"
    print(f"Starting focused progressive build task: {task_id}")
    print(f"Prompt:\n  {PROMPT}\n")

    t0 = time.time()
    result = await run_progressive_build(
        prompt=PROMPT,
        model_manager=model_manager,
        task_id=task_id,
        mcp_manager=mcp,
        preserve_scene=True,
    )
    t1 = time.time()

    print(f"\nBuild finished in {t1 - t0:.2f}s")
    print(f"Completion Status: {result.completion_status}")
    print(f"Success: {result.success}")
    print(f"Total Nodes: {result.total_nodes}, Verified: {result.verified_nodes}, Failed: {result.failed_nodes}")
    print(f"Errors: {result.errors}")

    manifest = result.manifest
    collection_name = manifest.collection_name if hasattr(manifest, "collection_name") else f"SentinelBuild_{task_id}"

    # 4. Query live scene details
    print("\nQuerying live scene geometry and transforms from Blender...")
    live_details = await query_live_scene_details(mcp, collection_name)
    parts = live_details.get("parts", [])
    print(f"Found {len(parts)} mesh objects in live Blender scene:")
    for p in parts:
        print(f" - {p['name']}: dims={p['dimensions']}, pos={p['location']}, rot={p['rotation_euler']}, mats={p['materials']}")

    # 5. Render custom camera views
    print(f"\nRendering high-res multi-view cameras to {ARTIFACT_DIR}...")
    render_result = await render_custom_camera_views(mcp, collection_name, ARTIFACT_DIR)
    print("Render result:", render_result)

    # Copy to root artifacts folder for markdown embeds
    if render_result.get("ok"):
        for name, path_str in render_result.get("paths", {}).items():
            src = Path(path_str)
            if src.exists():
                dest = ROOT_ARTIFACT_DIR / f"focused_{name}.png"
                shutil.copy2(src, dest)
                print(f"Copied render: {dest.name}")

    # Output scene quality audit from manifest stats
    print("\n--- Production Scene Audit Stats ---")
    audit_stats = manifest.stats.get("production_scene_audit", {})
    print(json.dumps(audit_stats, indent=2))

    return {
        "result": result.to_dict(),
        "live_parts": parts,
        "audit_stats": audit_stats,
        "renders": render_result,
    }

if __name__ == "__main__":
    out = asyncio.run(main())
