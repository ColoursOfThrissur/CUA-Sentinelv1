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
print()

metrics = d.get('metrics', {})
print("=== METRICS ===")
# Print everything except large arrays
def safe_print(obj, indent=0):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, (dict, list)) and len(str(v)) > 200:
                print(" " * indent + f"{k}: [truncated, len={len(v) if isinstance(v, list) else len(str(v))}]")
            else:
                print(" " * indent + f"{k}: {v}")
    else:
        print(" " * indent + str(obj))

safe_print(metrics)
print()

spec = d.get('spec', {})
print("=== SPEC TOP-LEVEL KEYS ===")
for k, v in spec.items():
    if isinstance(v, list):
        print(f"  {k}: list[{len(v)}]")
    elif isinstance(v, dict):
        print(f"  {k}: dict keys={list(v.keys())[:10]}")
    else:
        print(f"  {k}: {v}")

# Look for node-level data
for k in ['objects', 'nodes', 'parts', 'assembly', 'build_nodes', 'node_results']:
    if k in spec:
        print(f"\n=== spec['{k}'] ===")
        items = spec[k]
        if isinstance(items, list):
            for item in items[:20]:
                if isinstance(item, dict):
                    label = item.get('label') or item.get('name') or item.get('node_id') or '?'
                    status = item.get('build_status') or item.get('status') or '?'
                    socket = item.get('socket_type') or (item.get('attachment') or {}).get('socket_type') or '?'
                    print(f"  {label}: status={status} socket={socket}")
        elif isinstance(items, dict):
            for label, item in list(items.items())[:20]:
                status = item.get('build_status') or item.get('status') or '?' if isinstance(item, dict) else '?'
                print(f"  {label}: {status}")

sys.stdout.flush()
