import json
from pathlib import Path

manifest_path = Path("data/builds_v2/m_f4b618e2bc/manifest.json")
with open(manifest_path, "r", encoding="utf-8") as f:
    d = json.load(f)

targets = ["status_dome", "status_dome__sembly_1_02", "arm_front", "chassis_base", "propeller_blade_front_1"]

for nid, n in d.get("nodes", {}).items():
    lbl = n.get("label", "")
    if lbl in targets:
        print("=" * 70)
        print(f"NODE: {lbl} (id: {nid})")
        print(f"  Parent: {n.get('parent_id')}")
        parent_node = d.get("nodes", {}).get(n.get("parent_id"), {})
        print(f"  Parent Label: {parent_node.get('label')} (geom: {parent_node.get('geometry')})")
        print(f"  Geometry: {n.get('geometry')}")
        print(f"  Attachment: {n.get('attachment')}")
        print(f"  Stage Outputs: {json.dumps(n.get('stage_outputs'), indent=2)}")
        print(f"  Transform State: {json.dumps(n.get('transform_state'), indent=2)}")
