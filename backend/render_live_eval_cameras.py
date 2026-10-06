import asyncio
import json
import logging
from pathlib import Path
from core.mcp_manager import MCPManager
from core.blender_ops import parse_op_output

ARTIFACT_DIR = Path(r"C:\Users\derik\.gemini\antigravity\brain\1f90b81f-c78f-48cc-a929-061484d5f2c8\live_eval")

async def render():
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    mcp = MCPManager()
    mcp.initialize_from_config()
    await mcp.connect_app("blender")

    base_dir_str = str(ARTIFACT_DIR.resolve()).replace("\\", "/")

    script = f'''
import bpy, json, math
from mathutils import Vector

meshes = [o for o in bpy.data.objects if o.type == 'MESH' and not o.hide_render]
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
for o in meshes:
    name_lower = o.name.lower()
    if "lens" in name_lower or "camera" in name_lower:
        lens_obj = o
    elif "bracket" in name_lower:
        if not lens_obj:
            lens_obj = o
    elif "arm" in name_lower:
        arm_obj = o

cam_data = bpy.data.cameras.new("EvalCameraData")
cam = bpy.data.objects.new("EvalCamera", cam_data)
bpy.context.scene.collection.objects.link(cam)
bpy.context.scene.camera = cam
cam_data.lens = 50

# Lighting
key_data = bpy.data.lights.new("EvalKeyData", "AREA")
key_data.energy = 1200
key_data.shape = 'DISK'
key_data.size = max(extent * 1.5, 1.0)
key = bpy.data.objects.new("EvalKey", key_data)
bpy.context.scene.collection.objects.link(key)
key.location = center + Vector((extent, -extent, extent * 1.5))

fill_data = bpy.data.lights.new("EvalFillData", "AREA")
fill_data.energy = 500
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
    "front": (center, Vector((0.0, -1.0, 0.2)).normalized(), extent * 1.35),
    "top": (center, Vector((0.001, -0.001, 1.0)).normalized(), extent * 1.35),
    "side": (center, Vector((1.0, 0.0, 0.2)).normalized(), extent * 1.35),
    "bottom_up": (center, Vector((0.5, -0.8, -0.7)).normalized(), extent * 1.2),
}}

if lens_obj:
    lens_center = lens_obj.matrix_world.translation
    lens_extent = max(lens_obj.dimensions.length, 0.05)
    views["closeup_lens"] = (lens_center, Vector((0.6, -0.8, -0.3)).normalized(), lens_extent * 3.5)

if arm_obj:
    arm_center = arm_obj.matrix_world.translation
    arm_extent = max(arm_obj.dimensions.length, 0.05)
    views["closeup_arm_guard"] = (arm_center, Vector((0.8, -0.8, 0.6)).normalized(), arm_extent * 2.8)

out_paths = {{}}
base_dir = {repr(base_dir_str)}
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

print("SENTINEL_OUTPUT_START" + json.dumps({{"ok": True, "paths": out_paths, "extent": extent, "center": list(center)}}) + "SENTINEL_OUTPUT_END")
'''
    res = await mcp.call_locked("blender", "execute_blender_code", {"code": script})
    parsed = parse_op_output(res.get("output", ""))
    print("Render completed successfully:")
    print(json.dumps(parsed, indent=2))
    await mcp.shutdown()

if __name__ == "__main__":
    asyncio.run(render())
