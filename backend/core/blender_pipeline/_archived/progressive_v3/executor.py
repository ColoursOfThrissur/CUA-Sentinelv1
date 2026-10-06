"""V3-owned atomic Blender transaction. No V2 manifest or executor adapter."""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import asdict
from typing import Any

from core.blender_ops import parse_op_output

from .scene import Scene


BLENDER_SCRIPT = r'''
import bpy, json, math, traceback
from mathutils import Vector

plan = json.loads(__V3_PLAN__)
collection_name = plan['collection']
collection = None

def mesh_object(name, vertices, faces):
    mesh = bpy.data.meshes.new(name + '_mesh')
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    return obj

def primitive(part):
    g = part['geometry']
    kind = g['primitive']
    name = part['blender_name']
    seg = max(8, min(128, int(g.get('segments') or 32)))
    radius = g.get('radius') or 0.05
    depth = g.get('depth') or 0.1
    size = g.get('size') or [0.1, 0.1, 0.1]
    if kind == 'box':
        bpy.ops.mesh.primitive_cube_add(size=1)
        obj = bpy.context.object
        obj.dimensions = size
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    elif kind == 'sphere':
        bpy.ops.mesh.primitive_uv_sphere_add(segments=seg, ring_count=max(8, seg//2), radius=radius)
        obj = bpy.context.object
    elif kind == 'hemisphere':
        rings = max(4, seg//4)
        verts = [(0, 0, radius)]
        for j in range(1, rings + 1):
            phi = math.pi*j/(2*rings)
            for i in range(seg):
                a = 2*math.pi*i/seg
                verts.append((radius*math.sin(phi)*math.cos(a), radius*math.sin(phi)*math.sin(a), radius*math.cos(phi)))
        faces = []
        for i in range(seg): faces.append((0, 1+i, 1+(i+1)%seg))
        for j in range(rings-1):
            base = 1+j*seg
            nxt = base+seg
            for i in range(seg): faces.append((base+i, nxt+i, nxt+(i+1)%seg, base+(i+1)%seg))
        faces.append(tuple(1+(rings-1)*seg+i for i in reversed(range(seg))))
        obj = mesh_object(name, verts, faces)
    elif kind == 'cylinder':
        bpy.ops.mesh.primitive_cylinder_add(vertices=seg, radius=radius, depth=depth)
        obj = bpy.context.object
    elif kind == 'cone':
        bpy.ops.mesh.primitive_cone_add(vertices=seg, radius1=radius, radius2=g.get('radius2') or 0, depth=depth)
        obj = bpy.context.object
    elif kind == 'torus':
        bpy.ops.mesh.primitive_torus_add(major_segments=seg, minor_segments=max(6, seg//4), location=(0,0,0), major_radius=g['major_radius'], minor_radius=g['minor_radius'])
        obj = bpy.context.object
    elif kind == 'plane':
        bpy.ops.mesh.primitive_cube_add(size=1)
        obj = bpy.context.object
        obj.dimensions = size
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    elif kind == 'circle':
        bpy.ops.mesh.primitive_cylinder_add(vertices=seg, radius=radius, depth=max(radius*.02, .0005))
        obj = bpy.context.object
    elif kind == 'capsule':
        bpy.ops.mesh.primitive_uv_sphere_add(segments=seg, ring_count=max(8,seg//2), radius=radius)
        obj = bpy.context.object
        for v in obj.data.vertices:
            v.co.z += math.copysign(max(0, depth/2-radius), v.co.z)
    elif kind in ('prism', 'pyramid'):
        sides = 3 if kind == 'prism' else 4
        bpy.ops.mesh.primitive_cone_add(vertices=sides, radius1=radius, radius2=radius if kind == 'prism' else 0, depth=depth)
        obj = bpy.context.object
    elif kind == 'wedge':
        x,y,z = [s/2 for s in size]
        obj = mesh_object(name, [(-x,-y,-z),(x,-y,-z),(x,y,-z),(-x,y,-z),(-x,-y,z),(-x,y,z)], [(0,3,2,1),(0,1,4),(3,5,2),(0,4,5,3),(1,2,5,4)])
    elif kind == 'u_shape':
        R = g['major_radius']; r = g['minor_radius']
        points = [(R*math.cos(math.pi*i/seg), 0, -R*math.sin(math.pi*i/seg)) for i in range(seg+1)]
        verts=[]; faces=[]; sides=8
        for p in points:
            for j in range(sides):
                a=2*math.pi*j/sides
                verts.append((p[0]+r*math.cos(a), p[1]+r*math.sin(a), p[2]))
        for i in range(seg):
            for j in range(sides):
                a=i*sides+j; b=i*sides+(j+1)%sides
                faces.append((a,b,b+sides,a+sides))
        faces.extend([tuple(reversed(range(sides))), tuple(seg*sides+j for j in range(sides))])
        obj = mesh_object(name, verts, faces)
    else:
        raise ValueError('unsupported V3 primitive: ' + kind)
    if obj.name not in collection.objects:
        for old in list(obj.users_collection): old.objects.unlink(obj)
        collection.objects.link(obj)
    obj.name = name
    if obj.name != name:
        raise ValueError('Blender object name collision: ' + name)
    return obj

def material(spec):
    mat = bpy.data.materials.new('V3_' + spec['name'][:45])
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get('Principled BSDF')
    if bsdf is None: raise RuntimeError('Principled BSDF unavailable')
    for socket, value in [('Base Color',spec['base_color']),('Metallic',spec['metallic']),('Roughness',spec['roughness'])]:
        if socket not in bsdf.inputs: raise RuntimeError('missing material socket ' + socket)
        bsdf.inputs[socket].default_value = value
    if spec['transmission']:
        if 'Transmission Weight' not in bsdf.inputs: raise RuntimeError('transmission unsupported')
        bsdf.inputs['Transmission Weight'].default_value = spec['transmission']
    if spec['emission_strength']:
        if 'Emission Color' not in bsdf.inputs or 'Emission Strength' not in bsdf.inputs: raise RuntimeError('emission unsupported')
        bsdf.inputs['Emission Color'].default_value = spec['emission_color'] + [1.0]
        bsdf.inputs['Emission Strength'].default_value = spec['emission_strength']
    return mat

def modifiers(obj, specs):
    for spec in specs:
        kind = spec['kind']; p = spec['parameters']
        if kind == 'bevel':
            m=obj.modifiers.new('V3_Bevel','BEVEL'); m.width=float(p.get('width',.002)); m.segments=int(p.get('segments',3))
        elif kind == 'solidify':
            m=obj.modifiers.new('V3_Solidify','SOLIDIFY'); m.thickness=float(p.get('thickness',.002))
        elif kind == 'subdivision':
            m=obj.modifiers.new('V3_Subdivision','SUBSURF'); m.levels=min(3,max(1,int(p.get('levels',1))))
        elif kind == 'smooth':
            for face in obj.data.polygons: face.use_smooth=True
        else: raise ValueError('unsupported V3 modifier: '+kind)

try:
    if bpy.data.collections.get(collection_name): raise RuntimeError('V3 collection already exists: '+collection_name)
    collection=bpy.data.collections.new(collection_name)
    bpy.context.scene.collection.children.link(collection)
    root=bpy.data.objects.new(collection_name+'_Root',None)
    collection.objects.link(root)
    made={}
    for part in plan['parts']:
        if bpy.data.objects.get(part['blender_name']): raise RuntimeError('object name exists: '+part['blender_name'])
        obj=primitive(part)
        obj.location=part['transform']['position']
        obj.rotation_euler=part['transform']['rotation']
        obj.scale=part['transform']['scale']
        obj.data.materials.append(material(part['material']))
        modifiers(obj,part['modifiers'])
        obj['v3_part_id']=part['id']
        obj['v3_canonical_path']=part['canonical_path']
        made[part['id']]=obj
    bpy.context.view_layer.update()
    for part in plan['parts']:
        obj=made[part['id']]
        matrix=obj.matrix_world.copy()
        obj.parent=made[part['parent_id']] if part['parent_id'] else root
        obj.matrix_world=matrix
    bpy.context.view_layer.update()
    result={'ok':True,'collection':collection_name,'objects':{p['id']:made[p['id']].name for p in plan['parts']}}
    print('SENTINEL_OUTPUT_START'+json.dumps(result)+'SENTINEL_OUTPUT_END')
except Exception as exc:
    if collection:
        for obj in list(collection.objects): bpy.data.objects.remove(obj,do_unlink=True)
        bpy.data.collections.remove(collection)
    print('SENTINEL_OUTPUT_START'+json.dumps({'ok':False,'error':str(exc),'traceback':traceback.format_exc()[-3000:]})+'SENTINEL_OUTPUT_END')
'''


class V3Executor:
    def __init__(self, mcp_manager: Any, task_id: str) -> None:
        self.mcp_manager = mcp_manager
        self.collection_name = 'Sentinel_V3_' + hashlib.sha256(task_id.encode()).hexdigest()[:8] + '_' + uuid.uuid4().hex[:8]

    def render(self, scene: Scene) -> str:
        safe_prefix = re.sub(r'[^A-Za-z0-9_]', '_', scene.model_id)[:24]
        for part in scene.parts:
            part.blender_name = f"V3_{safe_prefix}_{part.id[-30:]}"[:63]
        if len({p.blender_name for p in scene.parts}) != len(scene.parts):
            raise ValueError('V3 Blender names are not unique')
        payload = {'collection': self.collection_name, 'parts': [asdict(part) for part in scene.parts]}
        return BLENDER_SCRIPT.replace('__V3_PLAN__', repr(json.dumps(payload, allow_nan=False)))

    async def execute(self, scene: Scene) -> dict[str, Any]:
        try:
            response = await self.mcp_manager.call_locked('blender','execute_blender_code',{'code': self.render(scene)})
            payload = parse_op_output(response.get('output',''))
        except Exception:
            # The MCP connection may fail after Blender executed the code.
            # This collection is unique to this attempt, so a best-effort rollback is safe.
            try:
                await self.cleanup()
            except Exception:
                pass
            raise
        if not payload.get('ok'):
            raise RuntimeError('V3_BLENDER_TRANSACTION_FAILED: ' + str(payload.get('error') or payload))
        names = payload.get('objects') or {}
        if set(names) != {part.id for part in scene.parts}:
            await self.cleanup()
            raise RuntimeError('V3 Blender receipt did not contain every part')
        for part in scene.parts:
            if names[part.id] != part.blender_name:
                await self.cleanup()
                raise RuntimeError(f'V3 Blender renamed {part.id}')
        return payload

    async def cleanup(self) -> None:
        script = (
            'import bpy, json\n'
            f'_c=bpy.data.collections.get({self.collection_name!r})\n'
            'if _c:\n'
            '    for _o in list(_c.objects): bpy.data.objects.remove(_o,do_unlink=True)\n'
            '    bpy.data.collections.remove(_c)\n'
            "print('SENTINEL_OUTPUT_START'+json.dumps({'ok':True})+'SENTINEL_OUTPUT_END')\n"
        )
        await self.mcp_manager.call_locked('blender','execute_blender_code',{'code':script})
