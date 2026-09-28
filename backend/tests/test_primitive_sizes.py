"""Quick primitive size verification test via /execute endpoint."""
import requests
import json

API = "http://localhost:8000"

def run_blender(code: str) -> dict:
    r = requests.post(f"{API}/api/blender/execute", json={"code": code}, timeout=30)
    return r.json()

def test_primitives():
    print("=== Primitive Size Verification ===\n")
    
    # Clear scene
    run_blender("""
import bpy
for obj in list(bpy.data.objects):
    if obj.type == 'MESH':
        bpy.data.objects.remove(obj, do_unlink=True)
bpy.ops.outliner.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)
print("SENTINEL_OUTPUT_START" + '{"ok":true}' + "SENTINEL_OUTPUT_END")
""")
    
    # Test box with bmesh (our fixed approach)
    print("1. Box [1, 2, 3] via bmesh:")
    result = run_blender("""
import bpy
import bmesh
import json

mesh = bpy.data.meshes.new("test_box")
bm = bmesh.new()
bmesh.ops.create_cube(bm, size=1.0)
for v in bm.verts:
    v.co.x *= 1.0
    v.co.y *= 2.0
    v.co.z *= 3.0
bm.to_mesh(mesh)
bm.free()

obj = bpy.data.objects.new("test_box", mesh)
bpy.context.collection.objects.link(obj)

dims = list(obj.dimensions)
print("SENTINEL_OUTPUT_START" + json.dumps({"ok": True, "dimensions": dims}) + "SENTINEL_OUTPUT_END")
""")
    output = result.get("output", "")
    if "SENTINEL_OUTPUT_START" in output:
        data = json.loads(output.split("SENTINEL_OUTPUT_START")[1].split("SENTINEL_OUTPUT_END")[0])
        dims = data.get("dimensions", [])
        expected = [1.0, 2.0, 3.0]
        ok = all(abs(dims[i] - expected[i]) < 0.01 for i in range(3))
        status = "PASS" if ok else "FAIL"
        print(f"   Expected: {expected}")
        print(f"   Got:      {[round(d,4) for d in dims]}")
        print(f"   Status:   {status}\n")
    else:
        print(f"   Error: {output[:200]}\n")
    
    # Test cylinder
    print("2. Cylinder radius=0.5, depth=2:")
    result = run_blender("""
import bpy
import json

bpy.ops.mesh.primitive_cylinder_add(radius=0.5, depth=2.0, location=(3, 0, 0))
obj = bpy.context.active_object
obj.name = "test_cyl"

dims = list(obj.dimensions)
print("SENTINEL_OUTPUT_START" + json.dumps({"ok": True, "dimensions": dims}) + "SENTINEL_OUTPUT_END")
""")
    output = result.get("output", "")
    if "SENTINEL_OUTPUT_START" in output:
        data = json.loads(output.split("SENTINEL_OUTPUT_START")[1].split("SENTINEL_OUTPUT_END")[0])
        dims = data.get("dimensions", [])
        expected = [1.0, 1.0, 2.0]
        ok = all(abs(dims[i] - expected[i]) < 0.01 for i in range(3))
        status = "PASS" if ok else "FAIL"
        print(f"   Expected: {expected}")
        print(f"   Got:      {[round(d,4) for d in dims]}")
        print(f"   Status:   {status}\n")
    else:
        print(f"   Error: {output[:200]}\n")
    
    # Test sphere
    print("3. Sphere radius=0.5:")
    result = run_blender("""
import bpy
import json

bpy.ops.mesh.primitive_uv_sphere_add(radius=0.5, location=(6, 0, 0))
obj = bpy.context.active_object
obj.name = "test_sphere"

dims = list(obj.dimensions)
print("SENTINEL_OUTPUT_START" + json.dumps({"ok": True, "dimensions": dims}) + "SENTINEL_OUTPUT_END")
""")
    output = result.get("output", "")
    if "SENTINEL_OUTPUT_START" in output:
        data = json.loads(output.split("SENTINEL_OUTPUT_START")[1].split("SENTINEL_OUTPUT_END")[0])
        dims = data.get("dimensions", [])
        expected = [1.0, 1.0, 1.0]
        ok = all(abs(dims[i] - expected[i]) < 0.01 for i in range(3))
        status = "PASS" if ok else "FAIL"
        print(f"   Expected: {expected}")
        print(f"   Got:      {[round(d,4) for d in dims]}")
        print(f"   Status:   {status}\n")
    else:
        print(f"   Error: {output[:200]}\n")
    
    # Test the OLD buggy box approach to confirm the bug
    print("4. Box [1, 2, 3] via OLD buggy scale/2 approach:")
    result = run_blender("""
import bpy
import json

size = [1.0, 2.0, 3.0]
bpy.ops.mesh.primitive_cube_add(size=1.0, location=(10, 0, 0))
obj = bpy.context.active_object
obj.name = "test_box_old"
# OLD BUGGY CODE: divides by 2
obj.scale = (size[0] / 2.0, size[1] / 2.0, size[2] / 2.0)
bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

dims = list(obj.dimensions)
print("SENTINEL_OUTPUT_START" + json.dumps({"ok": True, "dimensions": dims}) + "SENTINEL_OUTPUT_END")
""")
    output = result.get("output", "")
    if "SENTINEL_OUTPUT_START" in output:
        data = json.loads(output.split("SENTINEL_OUTPUT_START")[1].split("SENTINEL_OUTPUT_END")[0])
        dims = data.get("dimensions", [])
        expected = [0.5, 1.0, 1.5]  # Half of requested!
        ok = all(abs(dims[i] - expected[i]) < 0.01 for i in range(3))
        status = "CONFIRMS BUG" if ok else "UNEXPECTED"
        print(f"   Expected (buggy): {expected}")
        print(f"   Got:              {[round(d,4) for d in dims]}")
        print(f"   Status:           {status}\n")
    else:
        print(f"   Error: {output[:200]}\n")

if __name__ == "__main__":
    test_primitives()
