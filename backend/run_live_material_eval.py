"""
run_live_material_eval.py

Live end-to-end evaluation script to test Phase 1 Advanced Procedural PBR materials in Blender:
- Rich wood grain procedural shading (oak/walnut) on seat
- Genuine leather grain Voronoi bump shading on upholstered cushion
- Brushed steel / brushed aluminum anisotropic streaks on metal column and base ring
- Mathematical shader node tree readback & high-resolution multi-view renders
"""

import asyncio
import json
import logging
import math
import os
import shutil
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("live_material_eval")

MATERIAL_PROMPT = (
    "Build a luxury designer bar stool with rich realistic PBR materials: "
    "1. Base Frame Assembly: "
    "A circular brushed steel foot ring base: a horizontal torus or ring of major radius 0.22m and tube radius 0.015m resting flat on the ground with brushed steel metallic finish. "
    "A central vertical support column: a vertical cylinder of diameter 0.06m and height 0.65m centered directly on top of the base ring with brushed steel finish. "
    "A circular brushed steel footrest ring: a horizontal ring of major radius 0.18m and tube radius 0.012m mounted around the support column at height 0.25m. "
    "2. Seat Assembly (attached to the top end of the central support column): "
    "A circular solid oak wooden seat plate: a cylinder of diameter 0.34m and height 0.03m resting flat horizontally on top of the support column with rich oak wood grain finish. "
    "An upholstered black leather seat cushion: a soft cylinder of diameter 0.32m and height 0.05m attached directly to the top face of the wooden seat plate with fine leather grain texture."
)

ARTIFACT_DIR = Path(r"C:\Users\derik\Desktop\Derik\Projects\CUA-Sentinel\backend\artifacts\material_eval")
BRAIN_ARTIFACT_DIR = Path(r"C:\Users\derik\.gemini\antigravity\brain\1f90b81f-c78f-48cc-a929-061484d5f2c8\material_eval")


async def render_material_views(mcp, collection_name: str, output_dirs: list):
    """Render high-res camera views and save to artifact destinations."""
    for d in output_dirs:
        d.mkdir(parents=True, exist_ok=True)
    
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

cam_data = bpy.data.cameras.new("EvalMatCamData")
cam = bpy.data.objects.new("EvalMatCam", cam_data)
bpy.context.scene.collection.objects.link(cam)
bpy.context.scene.camera = cam
cam_data.lens = 50

# Studio 3-point lighting setup to highlight material textures & reflections
key_data = bpy.data.lights.new("EvalKeyData", "AREA")
key_data.energy = 1800
key_data.shape = 'DISK'
key_data.size = max(extent * 1.5, 1.2)
key = bpy.data.objects.new("EvalKey", key_data)
bpy.context.scene.collection.objects.link(key)
key.location = center + Vector((extent * 1.2, -extent * 1.2, extent * 1.5))

fill_data = bpy.data.lights.new("EvalFillData", "AREA")
fill_data.energy = 800
fill_data.shape = 'DISK'
fill_data.size = max(extent * 2.0, 1.5)
fill = bpy.data.objects.new("EvalFill", fill_data)
bpy.context.scene.collection.objects.link(fill)
fill.location = center + Vector((-extent * 1.2, extent * 1.0, extent * 0.8))

rim_data = bpy.data.lights.new("EvalRimData", "AREA")
rim_data.energy = 1200
rim_data.shape = 'DISK'
rim_data.size = max(extent * 1.2, 1.0)
rim = bpy.data.objects.new("EvalRim", rim_data)
bpy.context.scene.collection.objects.link(rim)
rim.location = center + Vector((0.0, extent * 1.5, extent * 1.2))

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
    "isometric": (center, Vector((1.0, -1.0, 0.8)).normalized(), extent * 1.35),
    "front": (center, Vector((0.0, -1.0, 0.15)).normalized(), extent * 1.35),
    "seat_closeup": (Vector((center.x, center.y, hi.z - 0.05)), Vector((0.8, -0.8, 0.6)).normalized(), 0.55),
    "side": (center, Vector((1.0, 0.0, 0.15)).normalized(), extent * 1.35),
}}

out_paths = {{}}
primary_dir = {str(output_dirs[0]).replace(chr(92), '/')!r}
for name, (tgt, direction, dist) in views.items():
    cam.location = tgt + direction * dist
    cam.rotation_euler = (tgt - cam.location).to_track_quat('-Z', 'Y').to_euler()
    p = f"{{primary_dir}}/{{name}}.png"
    scene.render.filepath = p
    bpy.ops.render.render(write_still=True)
    out_paths[name] = p

bpy.data.objects.remove(cam, do_unlink=True)
bpy.data.cameras.remove(cam_data)
bpy.data.objects.remove(key, do_unlink=True)
bpy.data.lights.remove(key_data)
bpy.data.objects.remove(fill, do_unlink=True)
bpy.data.lights.remove(fill_data)
bpy.data.objects.remove(rim, do_unlink=True)
bpy.data.lights.remove(rim_data)

print("SENTINEL_OUTPUT_START" + json.dumps({{"ok": True, "paths": out_paths, "center": list(center), "extent": extent}}) + "SENTINEL_OUTPUT_END")
'''
    from core.blender_ops import parse_op_output
    res = await mcp.call_locked("blender", "execute_blender_code", {"code": script})
    parsed = parse_op_output(res.get("output", ""))
    
    # Copy generated renders to secondary directories
    if len(output_dirs) > 1:
        for p in output_dirs[0].glob("*.png"):
            for d in output_dirs[1:]:
                shutil.copy2(p, d / p.name)
                
    return parsed


async def inspect_material_shader_trees(mcp):
    """Authoritative shader node readback from Blender."""
    script = '''
import bpy, json

mat_audit = []
for mat in bpy.data.materials:
    if not mat.use_nodes or not mat.node_tree:
        continue
    nodes_info = []
    for n in mat.node_tree.nodes:
        nodes_info.append({
            "name": n.name,
            "type": n.type,
            "inputs": [sock.name for sock in n.inputs if sock.is_linked or (hasattr(sock, 'default_value') and sock.name in ['Base Color', 'Metallic', 'Roughness', 'Scale', 'Detail', 'Distortion', 'Strength'])],
        })
    links_info = []
    for link in mat.node_tree.links:
        links_info.append({
            "from_node": link.from_node.name,
            "from_socket": link.from_socket.name,
            "to_node": link.to_node.name,
            "to_socket": link.to_socket.name,
        })
    mat_audit.append({
        "material_name": mat.name,
        "node_count": len(mat.node_tree.nodes),
        "nodes": nodes_info,
        "links": links_info,
    })

mesh_mat_map = []
for obj in bpy.data.objects:
    if obj.type == 'MESH':
        mats = [slot.material.name for slot in obj.material_slots if slot.material]
        mesh_mat_map.append({
            "object_name": obj.name,
            "materials": mats,
            "uv_layers": [uv.name for uv in obj.data.uv_layers],
        })

print("SENTINEL_OUTPUT_START" + json.dumps({"ok": True, "materials": mat_audit, "mesh_assignments": mesh_mat_map}) + "SENTINEL_OUTPUT_END")
'''
    from core.blender_ops import parse_op_output
    raw = await mcp.call_locked("blender", "execute_blender_code", {"code": script})
    return parse_op_output(raw.get("output", ""))


async def inspect_geometry_and_manifold(mcp):
    """Mathematical mesh readback."""
    script = '''
import bpy, json, math
from mathutils import Vector
import bmesh

meshes = [o for o in bpy.data.objects if o.type == 'MESH']
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

print("SENTINEL_OUTPUT_START" + json.dumps({"ok": True, "meshes": audit_data, "total_meshes": len(meshes)}) + "SENTINEL_OUTPUT_END")
'''
    from core.blender_ops import parse_op_output
    raw = await mcp.call_locked("blender", "execute_blender_code", {"code": script})
    return parse_op_output(raw.get("output", ""))


async def main():
    from config.loader import load_system_config, load_model_registry
    from core.model_manager import ModelManager
    from core.mcp_manager import MCPManager
    from core.blender_pipeline.progressive_v2.controller import run_progressive_build

    print("======================================================================")
    print("  PHASE 1: LIVE ADVANCED MATERIAL & PROCEDURAL PBR BUILD EVALUATION")
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

    task_id = f"live_mat_eval_{int(time.time())}"
    print(f"Starting progressive build task: {task_id}")
    print(f"Prompt:\n  {MATERIAL_PROMPT}\n")

    t0 = time.time()
    result = await run_progressive_build(
        prompt=MATERIAL_PROMPT,
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

    # Mathematical mesh readback
    print("\nReading geometric and manifold properties from Blender...")
    geom_readback = await inspect_geometry_and_manifold(mcp)
    print(json.dumps(geom_readback, indent=2))

    # Shader & Material node readback
    print("\nReading shader node graphs and material assignments from Blender...")
    shader_readback = await inspect_material_shader_trees(mcp)
    print(json.dumps(shader_readback, indent=2))

    # Render multi-view camera shots
    print("\nRendering high-res camera views...")
    model_id = result.manifest.model_id if result.manifest else "model"
    render_res = await render_material_views(
        mcp, f"Collection_{model_id}", [ARTIFACT_DIR, BRAIN_ARTIFACT_DIR]
    )
    print("Render completed:", render_res)

    audit_payload = {
        "task_id": task_id,
        "model_id": model_id,
        "duration": duration,
        "status": str(result.completion_status),
        "success": result.success,
        "total_nodes": result.total_nodes,
        "verified_nodes": result.verified_nodes,
        "blender_objects": result.blender_objects,
        "errors": result.errors,
        "geometry_readback": geom_readback,
        "shader_readback": shader_readback,
    }

    for target_dir in [ARTIFACT_DIR, BRAIN_ARTIFACT_DIR]:
        p = target_dir / "live_material_audit.json"
        p.write_text(json.dumps(audit_payload, indent=2))
        print(f"Saved audit json to {p}")


if __name__ == "__main__":
    asyncio.run(main())
