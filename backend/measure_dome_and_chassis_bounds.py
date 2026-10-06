import bpy
import json

# Run in Blender with data/pipeline_compiled_drone_script.py loaded

def measure_bounds():
    report = {}
    for obj in bpy.data.objects:
        if obj.type != 'MESH':
            continue
        # Calculate world-space bounding box
        bbox_corners = [obj.matrix_world @ mathutils.Vector(corner) for corner in obj.bound_box]
        min_x = min(c.x for c in bbox_corners)
        max_x = max(c.x for c in bbox_corners)
        min_y = min(c.y for c in bbox_corners)
        max_y = max(c.y for c in bbox_corners)
        min_z = min(c.z for c in bbox_corners)
        max_z = max(c.z for c in bbox_corners)
        
        # Local bounding box
        l_min_x = min(c[0] for c in obj.bound_box)
        l_max_x = max(c[0] for c in obj.bound_box)
        l_min_y = min(c[1] for c in obj.bound_box)
        l_max_y = max(c[1] for c in obj.bound_box)
        l_min_z = min(c[2] for c in obj.bound_box)
        l_max_z = max(c[2] for c in obj.bound_box)
        
        report[obj.name] = {
            "world_bounds": {
                "min": [round(min_x, 5), round(min_y, 5), round(min_z, 5)],
                "max": [round(max_x, 5), round(max_y, 5), round(max_z, 5)],
                "center_z": round((min_z + max_z) / 2, 5),
                "span_z": round(max_z - min_z, 5),
            },
            "local_bounds": {
                "min_z": round(l_min_z, 5),
                "max_z": round(l_max_z, 5),
            },
            "matrix_world_translation": [round(c, 5) for c in obj.matrix_world.translation],
            "parent": obj.parent.name if obj.parent else None,
        }
    
    with open("data/measured_bounds.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print("Measured bounds written to data/measured_bounds.json")

if __name__ == "__main__":
    import mathutils
    measure_bounds()
