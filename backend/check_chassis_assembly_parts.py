import json

manifest = json.load(open("data/builds_v2/m_f4b618e2bc/manifest.json", encoding="utf-8"))
bounds = json.load(open("data/measured_bounds.json", encoding="utf-8"))

nodes = manifest["nodes"]
chassis_asm = next(n for n in nodes.values() if n.get("label") == "chassis_assembly")
print("=" * 70)
print("CHASSIS_ASSEMBLY (id:", chassis_asm["node_id"], ")")
print("Children IDs:", chassis_asm["children_ids"])

print("\n--- Children of chassis_assembly in Manifest ---")
for cid in chassis_asm["children_ids"]:
    child = nodes.get(cid)
    if not child:
        print(f"Child ID {cid} NOT in nodes")
        continue
    lbl = child.get("label")
    geom = child.get("geometry")
    attach = child.get("attachment")
    stages = child.get("stage_outputs", {})
    s4 = stages.get("stage4", {})
    print(f"\nPart: {lbl} (kind={child.get('kind')}, id={cid})")
    print(f"  Geometry: {geom}")
    print(f"  Attachment: {attach}")
    print(f"  Stage 4: {s4}")
    
    # Find matching object in measured bounds
    matching_objs = [k for k in bounds.keys() if lbl in k]
    for mk in matching_objs:
        mb = bounds[mk]["world_bounds"]
        print(f"  Measured Blender World Bounds ({mk}):")
        print(f"    X: [{mb['min'][0]}, {mb['max'][0]}]")
        print(f"    Y: [{mb['min'][1]}, {mb['max'][1]}]")
        print(f"    Z: [{mb['min'][2]}, {mb['max'][2]}]  (span_z={mb['span_z']})")

print("\n" + "=" * 70)
print("STATUS DOME DECLARATION & RESOLVER INPUT")
dome_node = next(n for n in nodes.values() if n.get("label") == "status_dome")
print("Status Dome Node:", dome_node["node_id"])
print("  Parent ID:", dome_node.get("parent_id"))
parent_node = nodes.get(dome_node.get("parent_id"))
print(f"  Parent Node: {parent_node.get('label')} (kind={parent_node.get('kind')})")
print("  Attachment Spec:", dome_node.get("attachment"))
print("  Stage 4 Output:", dome_node.get("stage_outputs", {}).get("stage4"))
print("=" * 70)
