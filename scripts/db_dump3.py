import sqlite3, json, sys

conn = sqlite3.connect('data/operational.sqlite')
cur = conn.cursor()
cur.execute("SELECT build_id, data_json FROM spec3d_pending_builds ORDER BY rowid DESC LIMIT 1")
row = cur.fetchone()
conn.close()

build_id, data_json = row
d = json.loads(data_json)

print(f"build_id: {build_id}")
print(f"name: {d.get('name')}")
print(f"category: {d.get('category')}")
print(f"blend_path: {d.get('blend_path')}")
print(f"schema_version: {d.get('schema_version')}")
print()

metrics = d.get('metrics', {})
print("=== METRICS ===")
print(json.dumps(metrics, indent=2))
print()

spec = d.get('spec', {})
nodes = spec.get('nodes', [])
print(f"=== SPEC NODES ({len(nodes)}) ===")
for n in nodes:
    label = n.get('label', n.get('node_id', '?'))
    socket = n.get('attachment', {}).get('socket_type', '?')
    status = n.get('build_status', n.get('status', '?'))
    world_pos = n.get('world_position', '?')
    bbox = n.get('bounding_box', '?')
    print(f"  {label}: socket={socket} status={status} world_pos={world_pos}")
    if 'shackle_right' in label.lower():
        print(f"    FULL NODE:")
        print(json.dumps(n, indent=4))

sys.stdout.flush()
