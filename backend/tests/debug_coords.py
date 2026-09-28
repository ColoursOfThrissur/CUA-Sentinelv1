"""Debug parent-child coordinate flow."""
import requests
import json

API = "http://localhost:8000"

def build_and_trace(description: str):
    """Build an object and trace the coordinate flow."""
    print(f"\n{'='*60}")
    print(f"Building: {description}")
    print('='*60)
    
    r = requests.post(f"{API}/api/blender/build", json={"description": description}, timeout=120)
    result = r.json()
    
    if not result.get("ok"):
        print(f"FAILED: {result.get('error')}")
        return
    
    trace = result.get("trace", {})
    
    # Stage 0
    s0 = trace.get("stage0", {})
    print(f"\n--- Stage 0: Understanding ---")
    print(f"  Category: {s0.get('category')}")
    print(f"  Scale: {s0.get('scale_anchor_m', {}).get('overall_height_or_length')}m")
    
    # Stage 1
    s1 = trace.get("stage1", {})
    print(f"\n--- Stage 1: Topology ---")
    for p in s1.get("parts", []):
        print(f"  {p['label']}: {p['primitive_type']}, parent={p['parent_label']}, socket={p['socket_type']}")
    
    # Stage 2
    s2 = trace.get("stage2", {})
    print(f"\n--- Stage 2: Dimensions ---")
    for p in s2.get("parts", []):
        dims = p.get("dimensions", {})
        if "size" in dims:
            print(f"  {p['label']}: size={dims['size']}")
        elif "radius" in dims:
            print(f"  {p['label']}: r={dims.get('radius')}, d={dims.get('depth')}")
    
    # Stage 3
    s3 = trace.get("stage3", {})
    print(f"\n--- Stage 3: Semantics ---")
    for p in s3.get("parts", []):
        sem = {k: v for k, v in p.items() if k not in ("label", "socket_type")}
        if sem:
            print(f"  {p['label']}: {sem}")
    
    # Get manifest from Blender
    print(f"\n--- Blender Manifest ---")
    r = requests.post(f"{API}/api/blender/execute", json={"code": """
import bpy
import json
from mathutils import Vector
import math

objects = []
for obj in bpy.data.objects:
    if obj.type != 'MESH':
        continue
    mw = obj.matrix_world
    world_loc = mw.translation
    bbox = [mw @ Vector(c) for c in obj.bound_box]
    bbox_min = [min(c[i] for c in bbox) for i in range(3)]
    bbox_max = [max(c[i] for c in bbox) for i in range(3)]
    
    # Get parent info
    parent_info = None
    if obj.parent:
        parent_info = {
            "name": obj.parent.name,
            "world_loc": [round(c, 4) for c in obj.parent.matrix_world.translation],
            "rotation_deg": [round(math.degrees(r), 1) for r in obj.parent.rotation_euler],
        }
    
    objects.append({
        "name": obj.name,
        "world_loc": [round(c, 4) for c in world_loc],
        "local_loc": [round(c, 4) for c in obj.location],
        "rotation_deg": [round(math.degrees(r), 1) for r in obj.rotation_euler],
        "dims": [round(c, 4) for c in obj.dimensions],
        "x_range": [round(bbox_min[0], 4), round(bbox_max[0], 4)],
        "z_range": [round(bbox_min[2], 4), round(bbox_max[2], 4)],
        "parent": parent_info,
    })
print("SENTINEL_OUTPUT_START" + json.dumps({"ok": True, "objects": objects}) + "SENTINEL_OUTPUT_END")
"""}, timeout=30)
    
    output = r.json().get("output", "")
    if "SENTINEL_OUTPUT_START" in output:
        data = json.loads(output.split("SENTINEL_OUTPUT_START")[1].split("SENTINEL_OUTPUT_END")[0])
        for obj in data.get("objects", []):
            print(f"  {obj['name']}:")
            print(f"    world_loc={obj['world_loc']}, local_loc={obj['local_loc']}")
            print(f"    rotation={obj['rotation_deg']}, dims={obj['dims']}")
            print(f"    x_range={obj['x_range']}, z_range={obj['z_range']}")
            if obj['parent']:
                print(f"    parent: {obj['parent']['name']} at {obj['parent']['world_loc']}, rot={obj['parent']['rotation_deg']}")

if __name__ == "__main__":
    # Test 1: Simple vertical stack (should work)
    # build_and_trace("a simple lamp with circular base and vertical post")
    
    # Test 2: Horizontal arm (tests THROUGH_AXIS)
    # build_and_trace("training dummy with vertical post and horizontal arm through the middle")
    
    # Test 3: Arm with end attachments (tests LEFT_END/RIGHT_END)
    build_and_trace("training dummy with vertical post, horizontal arm through middle, shield on left end of arm, weight on right end")
