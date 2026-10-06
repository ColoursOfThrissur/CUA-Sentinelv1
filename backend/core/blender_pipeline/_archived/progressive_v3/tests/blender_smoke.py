"""Run with Blender's bundled Python: blender -b --python blender_smoke.py."""
import ast
import json
from pathlib import Path

source = (Path(__file__).parents[1] / 'executor.py').read_text(encoding='utf-8')
tree = ast.parse(source)
script = next(ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == 'BLENDER_SCRIPT' for target in node.targets))

material = dict(name='smoke metal', base_color=[.3,.4,.5,1], metallic=.7, roughness=.3,
                transmission=0, emission_color=None, emission_strength=0)
primitives = ['box','sphere','cylinder','cone','torus','hemisphere','u_shape',
              'capsule','wedge','pyramid','prism','plane','circle']
parts = []
for index, kind in enumerate(primitives):
    geometry = dict(primitive=kind, size=[.15,.1,.05], radius=.05, radius2=.025,
                    depth=.12, major_radius=.09, minor_radius=.008, segments=16)
    variant = dict(material)
    if kind == 'sphere':
        variant.update(name='smoke glass', transmission=.7, metallic=0)
    if kind == 'circle':
        variant.update(name='smoke LED', emission_color=[.1,.2,1], emission_strength=2)
    mods = [{'kind':'bevel','parameters':{'width':.001,'segments':2}}] if kind == 'box' else []
    if kind == 'cylinder': mods = [{'kind':'smooth','parameters':{}}, {'kind':'subdivision','parameters':{'levels':1}}]
    if kind == 'plane': mods = [{'kind':'solidify','parameters':{'thickness':.001}}]
    parts.append(dict(id=f'p{index}', canonical_path=f'root/{kind}[0]', blender_name=f'V3_smoke_{kind}',
                      geometry=geometry, material=variant, modifiers=mods,
                      transform={'position':[index*.25,0,0], 'rotation':[0,0,0], 'scale':[1,1,1]},
                      parent_id='p0' if index else None))
payload = json.dumps({'collection':'Sentinel_V3_Smoke','parts':parts})
exec(compile(script.replace('__V3_PLAN__', repr(payload)), '<V3 Blender transaction>', 'exec'))
import bpy
assert len([obj for obj in bpy.data.collections['Sentinel_V3_Smoke'].objects if obj.type == 'MESH']) == len(primitives)
assert bpy.data.objects['V3_smoke_sphere'].parent.name == 'V3_smoke_box'
for part in parts:
    obj = bpy.data.objects[part['blender_name']]
    assert obj['v3_part_id'] == part['id']
    assert len(obj.data.materials) == 1
    assert abs(obj.matrix_world.translation.x - part['transform']['position'][0]) < 1e-6
assert bpy.data.objects['V3_smoke_box'].modifiers[0].type == 'BEVEL'
assert [mod.type for mod in bpy.data.objects['V3_smoke_cylinder'].modifiers] == ['SUBSURF']
assert bpy.data.objects['V3_smoke_plane'].modifiers[0].type == 'SOLIDIFY'
bad = dict(parts[0])
bad['id'] = 'bad'
bad['blender_name'] = 'V3_smoke_bad'
bad['geometry'] = dict(bad['geometry'], primitive='nonexistent')
failed = json.dumps({'collection':'Sentinel_V3_FailedSmoke','parts':[bad]})
exec(compile(script.replace('__V3_PLAN__', repr(failed)), '<V3 rollback transaction>', 'exec'))
assert bpy.data.collections.get('Sentinel_V3_FailedSmoke') is None
assert bpy.data.objects.get('V3_smoke_bad') is None
print('V3_SMOKE_PASSED', len(primitives))
