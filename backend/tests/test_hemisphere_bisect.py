"""Test hemisphere via bpy.ops.mesh.bisect."""
import requests
import json

API = "http://localhost:8000"

def test_hemisphere():
    print("=== Hemisphere via mesh.bisect Test ===\n")
    
    # Clear and test
    result = requests.post(f"{API}/api/blender/execute", json={"code": """
import bpy
import json
from mathutils import Vector

# Clear
for obj in list(bpy.data.objects):
    if obj.type == 'MESH':
        bpy.data.objects.remove(obj, do_unlink=True)

name = "test_hemi"
radius = 0.1

# Create sphere at origin
bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, radius=radius, location=(0, 0, 0))
obj = bpy.context.active_object
obj.name = name

# Enter edit mode and bisect
bpy.context.view_layer.objects.active = obj
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')

# Bisect: plane at z=0, normal pointing up, clear inner (z < 0), fill cap
bpy.ops.mesh.bisect(
    plane_co=(0, 0, 0),
    plane_no=(0, 0, 1),
    clear_inner=True,
    clear_outer=False,
    use_fill=True
)

bpy.ops.object.mode_set(mode='OBJECT')

# Move to test position
obj.location = (0.6, 0, 0.1)

# CRITICAL: Update view layer to recalculate world transforms
bpy.context.view_layer.update()

# Get world AABB
mw = obj.matrix_world
bbox = [mw @ Vector(c) for c in obj.bound_box]
bbox_min = [min(c[i] for c in bbox) for i in range(3)]
bbox_max = [max(c[i] for c in bbox) for i in range(3)]

dims = list(obj.dimensions)
res = {
    "ok": True,
    "dimensions": dims,
    "aabb_x": [round(bbox_min[0], 4), round(bbox_max[0], 4)],
    "aabb_z": [round(bbox_min[2], 4), round(bbox_max[2], 4)],
    "vertex_count": len(obj.data.vertices),
    "face_count": len(obj.data.polygons),
}
print("SENTINEL_OUTPUT_START" + json.dumps(res) + "SENTINEL_OUTPUT_END")
"""}, timeout=30)
    
    output = result.json().get("output", "")
    if "SENTINEL_OUTPUT_START" in output:
        data = json.loads(output.split("SENTINEL_OUTPUT_START")[1].split("SENTINEL_OUTPUT_END")[0])
        dims = data.get("dimensions", [])
        aabb_x = data.get("aabb_x", [])
        aabb_z = data.get("aabb_z", [])
        
        expected_xy = 0.2
        expected_z = 0.1
        
        xy_ok = abs(dims[0] - expected_xy) < 0.01 and abs(dims[1] - expected_xy) < 0.01
        z_ok = abs(dims[2] - expected_z) < 0.02  # Slightly more tolerance
        aabb_x_ok = abs(aabb_x[0] - 0.5) < 0.01 and abs(aabb_x[1] - 0.7) < 0.01
        aabb_z_ok = abs(aabb_z[0] - 0.1) < 0.01 and abs(aabb_z[1] - 0.2) < 0.02
        
        print(f"   Dimensions: {[round(d,4) for d in dims]}")
        print(f"   Expected:   [{expected_xy}, {expected_xy}, {expected_z}]")
        print(f"   XY dims:    {'PASS' if xy_ok else 'FAIL'}")
        print(f"   Z dim:      {'PASS' if z_ok else 'FAIL'}")
        print(f"   AABB X:     {aabb_x} (expected [0.5, 0.7]) {'PASS' if aabb_x_ok else 'FAIL'}")
        print(f"   AABB Z:     {aabb_z} (expected [0.1, 0.2]) {'PASS' if aabb_z_ok else 'FAIL'}")
        print(f"   Vertices:   {data.get('vertex_count')}")
        print(f"   Faces:      {data.get('face_count')}")
        
        all_pass = xy_ok and z_ok and aabb_x_ok and aabb_z_ok
        print(f"\n   Overall:    {'PASS' if all_pass else 'FAIL'}")
    else:
        print(f"   Error: {output[:500]}")

if __name__ == "__main__":
    test_hemisphere()
