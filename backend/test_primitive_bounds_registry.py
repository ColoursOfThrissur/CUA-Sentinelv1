"""test_primitive_bounds_registry.py

Runs inside Blender headless:
  & "C:\Program Files\Blender Foundation\Blender 4.5\blender.exe" -b --python test_primitive_bounds_registry.py

Tests every registered primitive by comparing Blender's measured local bounds
to the registry convention in stage4_resolver.py.
"""

import math
import sys
from pathlib import Path

# Add backend to sys.path
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

try:
    import bpy
    import bmesh
    import mathutils
except ImportError:
    print("Must run inside Blender.")
    sys.exit(1)

from core.blender_pipeline.progressive_v2.node_types import PrimitiveType
from core.blender_pipeline.progressive_v2.stages.stage4_resolver import Stage4Resolver, BBox


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for col in list(bpy.data.collections):
        bpy.data.collections.remove(col)
    for mesh in list(bpy.data.meshes):
        bpy.data.meshes.remove(mesh)


def measure_obj_local_bounds(obj):
    # Measured directly on mesh vertices in local object space
    coords = [v.co for v in obj.data.vertices]
    if not coords:
        return (0, 0, 0, 0, 0, 0)
    min_x = min(c.x for c in coords)
    max_x = max(c.x for c in coords)
    min_y = min(c.y for c in coords)
    max_y = max(c.y for c in coords)
    min_z = min(c.z for c in coords)
    max_z = max(c.z for c in coords)
    return (round(min_x, 5), round(max_x, 5), round(min_y, 5), round(max_y, 5), round(min_z, 5), round(max_z, 5))


def create_capsule(params):
    radius, depth = params["radius"], params["depth"]
    cylinder_depth = max(0.0, depth - 2.0 * radius)
    pieces = []
    if cylinder_depth:
        bpy.ops.mesh.primitive_cylinder_add(radius=radius, depth=cylinder_depth)
        pieces.append(bpy.context.active_object)
    for z_pos in (cylinder_depth / 2, -cylinder_depth / 2):
        bpy.ops.mesh.primitive_uv_sphere_add(radius=radius, location=(0, 0, z_pos))
        pieces.append(bpy.context.active_object)
    bpy.ops.object.select_all(action="DESELECT")
    for piece in pieces:
        piece.select_set(True)
    bpy.context.view_layer.objects.active = pieces[0]
    bpy.ops.object.join()


def create_wedge(params):
    x, y, z = params["size"]
    vertices = [
        [-x/2, -y/2, -z/2], [x/2, -y/2, -z/2],
        [x/2, y/2, -z/2], [-x/2, y/2, -z/2],
        [-x/2, -y/2, z/2], [-x/2, y/2, z/2],
    ]
    faces = [[0,1,2,3], [0,4,5,3], [0,1,4], [1,2,5,4], [2,3,5]]
    mesh = bpy.data.meshes.new("Test_wedge")
    mesh.from_pydata(vertices, [], faces)
    obj = bpy.data.objects.new("Test_wedge", mesh)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj


def create_grid(params):
    mesh = bpy.data.meshes.new("Test_grid")
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=10, y_segments=10, size=0.5)
    for vertex in bm.verts:
        vertex.co.x *= params["size"][0]
        vertex.co.y *= params["size"][1]
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new("Test_grid", mesh)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj


def run_primitive_bounds_test():
    reset_scene()
    print("=" * 80)
    print("PRIMITIVE LOCAL-BOUNDS CONVENTION TEST (BLENDER 4.5.3 LTS)")
    print("=" * 80)
    
    test_cases = [
        # (PrimitiveType, params dict, creation_fn)
        (
            PrimitiveType.BOX,
            {"size": [0.30, 0.20, 0.10]},
            lambda p: bpy.ops.mesh.primitive_cube_add(size=1.0) or (setattr(bpy.context.active_object, 'scale', (p['size'][0], p['size'][1], p['size'][2])) or bpy.ops.object.transform_apply(scale=True))
        ),
        (
            PrimitiveType.SPHERE,
            {"radius": 0.25},
            lambda p: bpy.ops.mesh.primitive_uv_sphere_add(radius=p['radius'])
        ),
        (
            PrimitiveType.CYLINDER,
            {"radius": 0.15, "depth": 0.40},
            lambda p: bpy.ops.mesh.primitive_cylinder_add(radius=p['radius'], depth=p['depth'])
        ),
        (
            PrimitiveType.CONE,
            {"radius": 0.15, "radius2": 0.0, "depth": 0.40},
            lambda p: bpy.ops.mesh.primitive_cone_add(radius1=p['radius'], radius2=p.get('radius2', 0.0), depth=p['depth'])
        ),
        (
            PrimitiveType.TORUS,
            {"major_radius": 0.30, "minor_radius": 0.05},
            lambda p: bpy.ops.mesh.primitive_torus_add(major_radius=p['major_radius'], minor_radius=p['minor_radius'])
        ),
        (
            PrimitiveType.PLANE,
            {"size": [0.50, 0.40, 0.005]},
            lambda p: (
                mesh := bpy.data.meshes.new("Test_plane"),
                bm := bmesh.new(),
                bmesh.ops.create_cube(bm, size=1.0),
                [setattr(v.co, 'x', v.co.x * p['size'][0]) or setattr(v.co, 'y', v.co.y * p['size'][1]) or setattr(v.co, 'z', v.co.z * p['size'][2]) for v in bm.verts],
                bm.to_mesh(mesh), bm.free(),
                obj := bpy.data.objects.new("Test_plane", mesh),
                bpy.context.scene.collection.objects.link(obj),
                setattr(bpy.context.view_layer.objects, 'active', obj)
            )
        ),
        (
            PrimitiveType.HEMISPHERE,
            {"radius": 0.20},
            lambda p: (
                bpy.ops.mesh.primitive_uv_sphere_add(radius=p['radius']),
                (bm := bmesh.new(), bm.from_mesh(bpy.context.active_object.data),
                 bmesh.ops.bisect_plane(bm, geom=bm.verts[:]+bm.edges[:]+bm.faces[:], plane_co=(0,0,0), plane_no=(0,0,1), clear_inner=True, clear_outer=False),
                 bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.0001),
                 bmesh.ops.edgeloop_fill(bm, edges=[e for e in bm.edges if len(e.link_faces)==1]),
                 bm.to_mesh(bpy.context.active_object.data), bm.free())
            )
        ),
        (
            PrimitiveType.U_SHAPE,
            {"major_radius": 0.20, "minor_radius": 0.04},
            lambda p: (
                bpy.ops.mesh.primitive_torus_add(major_radius=p['major_radius'], minor_radius=p['minor_radius'], major_segments=48, minor_segments=16),
                (bm := bmesh.new(), bm.from_mesh(bpy.context.active_object.data),
                 bmesh.ops.bisect_plane(bm, geom=bm.verts[:]+bm.edges[:]+bm.faces[:], plane_co=(0,0,0), plane_no=(1,0,0), clear_inner=True, clear_outer=False),
                 bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.0001),
                 bmesh.ops.edgeloop_fill(bm, edges=[e for e in bm.edges if len(e.link_faces)==1]),
                 rz := mathutils.Matrix.Rotation(math.pi/2, 4, 'Z'), rx := mathutils.Matrix.Rotation(math.pi/2, 4, 'X'),
                 bmesh.ops.transform(bm, matrix=rx@rz, verts=bm.verts),
                 mz := min(v.co.z for v in bm.verts),
                 bmesh.ops.translate(bm, vec=mathutils.Vector((0, 0, -mz)), verts=bm.verts),
                 bm.to_mesh(bpy.context.active_object.data), bm.free(),
                 bpy.context.active_object.data.update())
            )
        ),
        (
            PrimitiveType.CAPSULE,
            {"radius": 0.08, "depth": 0.40},
            create_capsule,
        ),
        (
            PrimitiveType.CIRCLE,
            {"radius": 0.20},
            lambda p: bpy.ops.mesh.primitive_circle_add(vertices=32, radius=p["radius"], fill_type="NGON"),
        ),
        (
            PrimitiveType.GRID,
            {"size": [0.50, 0.30, 0.0]},
            create_grid,
        ),
        (
            PrimitiveType.PYRAMID,
            {"radius": 0.20, "depth": 0.40},
            lambda p: bpy.ops.mesh.primitive_cone_add(vertices=4, radius1=p["radius"], radius2=0.0, depth=p["depth"]),
        ),
        (
            PrimitiveType.PRISM,
            {"radius": 0.20, "depth": 0.40, "segments": 6},
            lambda p: bpy.ops.mesh.primitive_cone_add(vertices=p["segments"], radius1=p["radius"], radius2=p["radius"], depth=p["depth"]),
        ),
        (
            PrimitiveType.WEDGE,
            {"size": [0.50, 0.30, 0.20]},
            create_wedge,
        ),
        (
            PrimitiveType.MONKEY,
            {},
            lambda p: bpy.ops.mesh.primitive_monkey_add(),
        ),
    ]
    
    results = []
    tol = 0.001  # 1mm tolerance
    
    for prim_type, params, creator in test_cases:
        reset_scene()
        creator(params)
        obj = bpy.context.active_object
        obj.name = f"Test_{prim_type.value}"
        
        # 1. Measure in Blender
        mx_min, mx_max, my_min, my_max, mz_min, mz_max = measure_obj_local_bounds(obj)
        measured_bbox = BBox(min_x=mx_min, max_x=mx_max, min_y=my_min, max_y=my_max, min_z=mz_min, max_z=mz_max)
        
        # 2. Get Stage4 registry bbox
        from core.blender_pipeline.progressive_v2.manifest import GeometrySpec
        geo = GeometrySpec(primitive=prim_type, **params)
        registry_bbox = BBox.from_geometry(geo, params)
        
        measured = [mx_min, mx_max, my_min, my_max, mz_min, mz_max]
        registered = [
            registry_bbox.min_x, registry_bbox.max_x,
            registry_bbox.min_y, registry_bbox.max_y,
            registry_bbox.min_z, registry_bbox.max_z,
        ]
        differences = [abs(actual - expected) for actual, expected in zip(measured, registered)]
        passed = all(difference <= tol for difference in differences)

        status = "PASS" if passed else "FAIL_MISMATCH"
        print(
            f"[{status:13s}] {prim_type.value:12s} | "
            f"Measured XYZ: {measured} | Registry XYZ: {[round(v, 5) for v in registered]} | "
            f"Max diff: {max(differences):.5f}"
        )
        results.append({
            "primitive": prim_type.value,
            "measured_bounds": measured,
            "registry_bounds": registered,
            "differences": differences,
            "pass": passed,
        })
        
    print("=" * 80)
    failed = [r for r in results if not r["pass"]]
    if failed:
        print(f"FAILED: {len(failed)} primitives had registry bounds mismatch with Blender!")
    else:
        print("ALL PRIMITIVE BOUNDS MATCHED REGISTRY ACCURATELY!")
    print("=" * 80)
    return len(failed) == 0

if __name__ == "__main__":
    success = run_primitive_bounds_test()
    sys.exit(0 if success else 1)
