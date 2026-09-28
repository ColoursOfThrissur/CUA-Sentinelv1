"""Standalone Blender Transform Chain Test.

Copy and paste this entire script into Blender's Python console or Text Editor.
It will build the test cases and print readback results.

This tests the parenting behavior directly in Blender without MCP.
"""

import bpy
import json
import math
from mathutils import Vector, Matrix

# =============================================================================
# TEST CASE DEFINITIONS
# =============================================================================

CASE_A = {
    "name": "Case_A",
    "nodes": [
        {"name": "base", "prim": "cylinder", "radius": 0.5, "depth": 0.2,
         "parent": None, "offset": (0, 0, 0.1), "rot_deg": (0, 0, 0)},
        {"name": "arm", "prim": "cylinder", "radius": 0.05, "depth": 1.0,
         "parent": "base", "offset": (0, 0, 0.4), "rot_deg": (0, 90, 0)},
        {"name": "disc", "prim": "cylinder", "radius": 0.15, "depth": 0.02,
         "parent": "arm", "offset": (0, 0, 0.51), "rot_deg": (0, 0, 0)},
    ],
    "expected": {
        "base": {"pos": (0, 0, 0.1), "axis_z": (0, 0, 1)},
        "arm": {"pos": (0, 0, 0.5), "axis_z": (1, 0, 0)},
        "disc": {"pos": (0.51, 0, 0.5), "axis_z": (1, 0, 0)},
    }
}

CASE_B = {
    "name": "Case_B",
    "nodes": [
        {"name": "base", "prim": "cylinder", "radius": 0.5, "depth": 0.2,
         "parent": None, "offset": (0, 0, 0.1), "rot_deg": (0, 0, 0)},
        {"name": "arm_b", "prim": "cylinder", "radius": 0.05, "depth": 1.0,
         "parent": "base", "offset": (0, 0, 0.4), "rot_deg": (90, 0, 90)},
        {"name": "cap", "prim": "sphere", "radius": 0.10, "depth": 0,
         "parent": "arm_b", "offset": (0, 0, 0.6), "rot_deg": (0, 0, 0)},
    ],
    "expected": {
        "base": {"pos": (0, 0, 0.1), "axis_z": (0, 0, 1)},
        "arm_b": {"pos": (0, 0, 0.5), "axis_z": (1, 0, 0)},
        "cap": {"pos": (0.6, 0, 0.5), "axis_z": (1, 0, 0)},
    }
}

CASE_C = {
    "name": "Case_C",
    "nodes": [
        {"name": "base", "prim": "cylinder", "radius": 0.5, "depth": 0.2,
         "parent": None, "offset": (0, 0, 0.1), "rot_deg": (0, 0, 0)},
        {"name": "link1", "prim": "cylinder", "radius": 0.05, "depth": 1.0,
         "parent": "base", "offset": (0, 0, 0.4), "rot_deg": (90, 0, 0)},
        {"name": "link2", "prim": "cylinder", "radius": 0.05, "depth": 0.5,
         "parent": "link1", "offset": (0, 0, 0.75), "rot_deg": (0, 90, 0)},
        {"name": "tip", "prim": "sphere", "radius": 0.05, "depth": 0,
         "parent": "link2", "offset": (0, 0, 0.30), "rot_deg": (0, 0, 0)},
    ],
    "expected": {
        "base": {"pos": (0, 0, 0.1), "axis_z": (0, 0, 1)},
        "link1": {"pos": (0, 0, 0.5), "axis_z": (0, -1, 0)},
        "link2": {"pos": (0, -0.75, 0.5), "axis_z": (1, 0, 0)},
        "tip": {"pos": (0.3, -0.75, 0.5), "axis_z": (1, 0, 0)},
    }
}

# =============================================================================
# ORACLE MATH (same as test_transform_chain.py)
# =============================================================================

def rx(deg):
    r = math.radians(deg)
    c, s = math.cos(r), math.sin(r)
    return [[1, 0, 0], [0, c, -s], [0, s, c]]

def ry(deg):
    r = math.radians(deg)
    c, s = math.cos(r), math.sin(r)
    return [[c, 0, s], [0, 1, 0], [-s, 0, c]]

def rz(deg):
    r = math.radians(deg)
    c, s = math.cos(r), math.sin(r)
    return [[c, -s, 0], [s, c, 0], [0, 0, 1]]

def mat_mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]

def mat_vec(m, v):
    return (m[0][0]*v[0] + m[0][1]*v[1] + m[0][2]*v[2],
            m[1][0]*v[0] + m[1][1]*v[1] + m[1][2]*v[2],
            m[2][0]*v[0] + m[2][1]*v[1] + m[2][2]*v[2])

def euler_to_matrix(deg):
    return mat_mul(rz(deg[2]), mat_mul(ry(deg[1]), rx(deg[0])))

def vec_add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])

# =============================================================================
# BUILD AND TEST
# =============================================================================

def clear_scene():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()

def create_primitive(node):
    if node["prim"] == "cylinder":
        bpy.ops.mesh.primitive_cylinder_add(radius=node["radius"], depth=node["depth"], location=(0,0,0))
    elif node["prim"] == "sphere":
        bpy.ops.mesh.primitive_uv_sphere_add(radius=node["radius"], location=(0,0,0))
    obj = bpy.context.active_object
    obj.name = node["name"]
    return obj

def compute_world_transforms(nodes):
    """Compute expected world transforms using oracle math."""
    results = {}
    for node in nodes:
        if node["parent"] is None:
            world_pos = node["offset"]
            world_rot = euler_to_matrix(node["rot_deg"])
        else:
            parent = results[node["parent"]]
            rotated_offset = mat_vec(parent["rot"], node["offset"])
            world_pos = vec_add(parent["pos"], rotated_offset)
            local_rot = euler_to_matrix(node["rot_deg"])
            world_rot = mat_mul(parent["rot"], local_rot)
        results[node["name"]] = {"pos": world_pos, "rot": world_rot}
    return results

def build_case_with_world_coords(case):
    """Build using WORLD coordinates (what pipeline emits) + parenting with keep_transform."""
    clear_scene()
    print(f"\n{'='*60}")
    print(f"Building {case['name']} with WORLD coordinates + parenting")
    print(f"{'='*60}")
    
    # Compute world transforms
    world_xforms = compute_world_transforms(case["nodes"])
    
    objects = {}
    for node in case["nodes"]:
        # Create primitive at origin
        obj = create_primitive(node)
        objects[node["name"]] = obj
        
        # Set WORLD position and rotation
        wx = world_xforms[node["name"]]
        obj.location = wx["pos"]
        
        # Convert rotation matrix to Euler
        rot_mat = Matrix([wx["rot"][0], wx["rot"][1], wx["rot"][2]]).transposed()
        obj.rotation_euler = rot_mat.to_euler('XYZ')
        
        print(f"  {node['name']}: world_pos={tuple(round(v,4) for v in wx['pos'])}")
    
    # Update scene
    bpy.context.view_layer.update()
    
    # Now parent with keep_transform=True
    print("\nParenting with keep_transform=True:")
    for node in case["nodes"]:
        if node["parent"]:
            child = objects[node["name"]]
            parent = objects[node["parent"]]
            
            # This is what the pipeline does:
            child.parent = parent
            child.matrix_parent_inverse = parent.matrix_world.inverted()
            
            print(f"  {node['name']} -> {node['parent']}")
            print(f"    parent_inverse_is_identity: {child.matrix_parent_inverse == Matrix.Identity(4)}")
    
    bpy.context.view_layer.update()
    return objects

def readback_transforms(objects, expected):
    """Read back transforms and compare to expected."""
    print("\nReadback results:")
    errors = []
    tol = 0.01
    
    for name, obj in objects.items():
        bpy.context.view_layer.update()
        mw = obj.matrix_world
        pos = tuple(mw.translation)
        rot = mw.to_3x3()
        axis_z = tuple(rot.col[2])
        
        exp = expected.get(name, {})
        exp_pos = exp.get("pos", (0,0,0))
        exp_z = exp.get("axis_z", (0,0,1))
        
        pos_ok = all(abs(pos[i] - exp_pos[i]) < tol for i in range(3))
        z_ok = all(abs(axis_z[i] - exp_z[i]) < tol for i in range(3))
        
        status = "OK" if (pos_ok and z_ok) else "FAIL"
        print(f"  {name}: {status}")
        print(f"    position: {tuple(round(v,4) for v in pos)} (expected {exp_pos})")
        print(f"    axis_z:   {tuple(round(v,4) for v in axis_z)} (expected {exp_z})")
        
        if obj.parent:
            print(f"    parent: {obj.parent.name}")
            print(f"    parent_inverse_is_identity: {obj.matrix_parent_inverse == Matrix.Identity(4)}")
        
        if not pos_ok:
            errors.append(f"{name} position mismatch")
        if not z_ok:
            errors.append(f"{name} axis_z mismatch")
    
    return errors

def run_all_tests():
    """Run all test cases."""
    print("\n" + "="*60)
    print("BLENDER TRANSFORM CHAIN TEST")
    print("="*60)
    
    all_errors = []
    
    for case in [CASE_A, CASE_B, CASE_C]:
        objects = build_case_with_world_coords(case)
        errors = readback_transforms(objects, case["expected"])
        if errors:
            all_errors.extend([f"{case['name']}: {e}" for e in errors])
    
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    if all_errors:
        print("FAILURES:")
        for e in all_errors:
            print(f"  - {e}")
    else:
        print("ALL TESTS PASSED")
    
    return len(all_errors) == 0

# Run the tests
if __name__ == "__main__":
    run_all_tests()
