"""Debug hemisphere cutter - don't delete it."""
import sys
import asyncio
import json
import aiohttp
sys.path.insert(0, '.')

from core import blender_ops as b_ops

async def main():
    async with aiohttp.ClientSession() as session:
        # Clear scene
        code = b_ops.render_op_script(b_ops._CLEAR_SCENE_TEMPLATE, 
            b_ops.ClearSceneParams(keep_camera_and_lights=False))
        await session.post("http://localhost:8000/api/blender/execute", json={"code": code})
        
        # Create sphere at (0.5, 0, 0.5)
        code = b_ops.render_op_script(b_ops._CREATE_SPHERE_TEMPLATE,
            b_ops.CreateSphereParams(name="dome", radius=0.2, location=[0.5, 0.0, 0.5]))
        await session.post("http://localhost:8000/api/blender/execute", json={"code": code})
        
        # Create cutter box - exact parameters from pipeline
        code = b_ops.render_op_script(b_ops._CREATE_BOX_TEMPLATE,
            b_ops.CreateBoxParams(
                name="cutter", 
                size=[0.5, 0.5, 0.5],
                location=[0.3, 0.0, 0.5],
            ))
        result = await session.post("http://localhost:8000/api/blender/execute", json={"code": code})
        print("Cutter created:", (await result.json()).get("output", "")[:300])
        
        # Read back cutter bounds
        readback_code = '''
import bpy
import json
from mathutils import Vector

bpy.context.view_layer.update()
results = {}
for name in ["dome", "cutter"]:
    obj = bpy.data.objects.get(name)
    if obj:
        mw = obj.matrix_world
        corners = [mw @ Vector(c) for c in obj.bound_box]
        results[name] = {
            "position": [round(v, 4) for v in mw.translation],
            "dimensions": [round(v, 4) for v in obj.dimensions],
            "world_bbox": {
                "x": [round(min(c.x for c in corners), 4), round(max(c.x for c in corners), 4)],
                "y": [round(min(c.y for c in corners), 4), round(max(c.y for c in corners), 4)],
                "z": [round(min(c.z for c in corners), 4), round(max(c.z for c in corners), 4)],
            }
        }
print("SENTINEL_OUTPUT_START" + json.dumps({"ok": True, "objects": results}) + "SENTINEL_OUTPUT_END")
'''
        result = await session.post("http://localhost:8000/api/blender/execute", json={"code": readback_code})
        data = await result.json()
        output = data["output"]
        json_str = output.split("SENTINEL_OUTPUT_START")[1].split("SENTINEL_OUTPUT_END")[0]
        print("\nReadback:")
        print(json.dumps(json.loads(json_str), indent=2))

if __name__ == "__main__":
    asyncio.run(main())
