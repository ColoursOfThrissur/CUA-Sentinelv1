"""Diagnose dome hemisphere - run via API."""

DIAGNOSTIC_CODE = '''
import bpy
import json

bpy.context.view_layer.update()
dg = bpy.context.evaluated_depsgraph_get()

results = {}
for obj in bpy.data.objects:
    if obj.type == 'MESH':
        eval_obj = obj.evaluated_get(dg)
        eval_mesh = eval_obj.data
        corners = [obj.matrix_world @ v.co for v in eval_mesh.vertices]
        if corners:
            bbox = {
                'x': [round(min(c.x for c in corners), 4), round(max(c.x for c in corners), 4)],
                'y': [round(min(c.y for c in corners), 4), round(max(c.y for c in corners), 4)],
                'z': [round(min(c.z for c in corners), 4), round(max(c.z for c in corners), 4)],
            }
        else:
            bbox = None
        results[obj.name] = {
            'vertex_count': len(eval_mesh.vertices),
            'modifiers': [m.type for m in obj.modifiers],
            'eval_bbox': bbox,
            'orig_bbox': {
                'x': [round(min(c[0] for c in obj.bound_box), 4), round(max(c[0] for c in obj.bound_box), 4)],
                'y': [round(min(c[1] for c in obj.bound_box), 4), round(max(c[1] for c in obj.bound_box), 4)],
                'z': [round(min(c[2] for c in obj.bound_box), 4), round(max(c[2] for c in obj.bound_box), 4)],
            }
        }

res = {'ok': True, 'objects': results, 'object_names': list(bpy.data.objects.keys())}
print("SENTINEL_OUTPUT_START" + json.dumps(res) + "SENTINEL_OUTPUT_END")
'''

import asyncio
import aiohttp
import json

async def main():
    async with aiohttp.ClientSession() as session:
        async with session.post(
            "http://localhost:8000/api/blender/execute",
            json={"code": DIAGNOSTIC_CODE}
        ) as resp:
            result = await resp.json()
            print(json.dumps(result, indent=2))

if __name__ == "__main__":
    asyncio.run(main())
