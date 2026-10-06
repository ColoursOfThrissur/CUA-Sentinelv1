import json
from pathlib import Path

manifest_path = Path("data/builds_v2/m_f4b618e2bc/manifest.json")
with open(manifest_path, "r", encoding="utf-8") as f:
    data = json.load(f)

nodes = data.get("nodes", {})

target_labels = ["status_dome", "arm_front", "arm_assembly_root", "propeller_blade_front_1", "propeller_blade_front_2", "chassis_base"]

for nid, n in nodes.items():
    lbl = n.get("label", "")
    if any(t in lbl for t in ["status_dome", "arm_front", "blade_front", "propeller_blade"]):
        print("=" * 80)
        print(f"NODE: {lbl} (id={nid}, kind={n.get('kind')}, importance={n.get('importance')})")
        print(f"  Parent: {n.get('parent_id')}")
        print(f"  Geometry: {n.get('geometry')}")
        print(f"  Attachment: {n.get('attachment')}")
        print(f"  Material: {n.get('material')}")
        print(f"  Stage Outputs:")
        for sname, sdata in n.get("stage_outputs", {}).items():
            print(f"    {sname}: {json.dumps(sdata)}")
        ts = n.get("transform_state", {})
        print(f"  Transform State:")
        print(f"    local_transform: {ts.get('local_transform')}")
        print(f"    world_matrix: {ts.get('world_matrix')}")
        print(f"    provenance: {ts.get('provenance')}")
