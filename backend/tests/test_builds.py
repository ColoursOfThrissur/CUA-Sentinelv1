"""Re-test arcade cabinet and desk fan with fixed box sizes."""
import requests
import json

API = "http://localhost:8000"

def build(description: str) -> dict:
    print(f"\n{'='*60}")
    print(f"Building: {description}")
    print('='*60)
    r = requests.post(f"{API}/api/blender/build", json={"description": description}, timeout=120)
    result = r.json()
    print(f"Status: {'OK' if result.get('ok') else 'FAILED'}")
    if result.get('error'):
        print(f"Error: {result.get('error')}")
    if result.get('verification'):
        print(f"Verification: {json.dumps(result.get('verification'), indent=2)}")
    return result

def get_manifest() -> dict:
    r = requests.post(f"{API}/api/blender/execute", json={"code": """
import bpy
import json
from mathutils import Vector

objects = []
for obj in bpy.data.objects:
    if obj.type != 'MESH':
        continue
    world_loc = obj.matrix_world.translation
    world_aabb_min = [0, 0, 0]
    world_aabb_max = [0, 0, 0]
    if obj.data.vertices:
        world_verts = [obj.matrix_world @ v.co for v in obj.data.vertices]
        world_aabb_min = [min(v[i] for v in world_verts) for i in range(3)]
        world_aabb_max = [max(v[i] for v in world_verts) for i in range(3)]
    objects.append({
        "name": obj.name,
        "world_loc": [round(c, 3) for c in world_loc],
        "dimensions": [round(c, 3) for c in obj.dimensions],
        "aabb_min": [round(c, 3) for c in world_aabb_min],
        "aabb_max": [round(c, 3) for c in world_aabb_max],
    })
print("SENTINEL_OUTPUT_START" + json.dumps({"ok": True, "objects": objects}) + "SENTINEL_OUTPUT_END")
"""}, timeout=30)
    output = r.json().get("output", "")
    if "SENTINEL_OUTPUT_START" in output:
        return json.loads(output.split("SENTINEL_OUTPUT_START")[1].split("SENTINEL_OUTPUT_END")[0])
    return {"ok": False}

def main():
    # Test 1: Arcade Cabinet
    result = build("retro arcade cabinet with screen, control panel with joystick and buttons, and marquee sign on top")
    if result.get("ok"):
        manifest = get_manifest()
        print("\nManifest:")
        for obj in manifest.get("objects", []):
            print(f"  {obj['name']}: dims={obj['dimensions']}, z_range=[{obj['aabb_min'][2]:.2f}, {obj['aabb_max'][2]:.2f}]")
    
    # Test 2: Desk Fan
    result = build("desk fan with circular base, adjustable neck, and protective cage around spinning blades")
    if result.get("ok"):
        manifest = get_manifest()
        print("\nManifest:")
        for obj in manifest.get("objects", []):
            print(f"  {obj['name']}: dims={obj['dimensions']}, z_range=[{obj['aabb_min'][2]:.2f}, {obj['aabb_max'][2]:.2f}]")

if __name__ == "__main__":
    main()
