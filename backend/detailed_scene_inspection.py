import bpy
import bmesh
import json
import os

def analyze_current_scene(output_path):
    report = {
        "object_count": len(bpy.data.objects),
        "mesh_count": len(bpy.data.meshes),
        "material_count": len(bpy.data.materials),
        "objects": []
    }
    
    for obj in bpy.data.objects:
        if obj.type != 'MESH':
            continue
        info = {
            "name": obj.name,
            "location": [round(c, 4) for c in obj.location],
            "dimensions": [round(c, 4) for c in obj.dimensions],
            "parent": obj.parent.name if obj.parent else None,
            "materials": [m.name for m in obj.data.materials if m],
            "modifiers": [m.type for m in obj.modifiers],
            "verts": len(obj.data.vertices),
            "faces": len(obj.data.polygons),
        }
        report["objects"].append(info)
        
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"Wrote inspection report to {output_path} ({len(report['objects'])} mesh objects)")

if __name__ == "__main__":
    import sys
    out = sys.argv[-1] if len(sys.argv) > 1 and sys.argv[-1].endswith(".json") else "scene_report.json"
    analyze_current_scene(out)
