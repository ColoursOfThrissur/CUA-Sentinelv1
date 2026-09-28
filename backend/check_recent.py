"""Check recent failed builds from the database."""
import sys
sys.path.insert(0, '.')

from db.repositories.operational_repo import OperationalRepository
import json

repo = OperationalRepository()

# Get recent tasks
print("=== Recent Tasks ===")
tasks = repo.list_tasks(limit=10)
for t in tasks:
    print(f"  {t['task_id'][:30]} | {t['status']} | {t.get('title', 'N/A')[:40]}")

# Get recent assembly graphs directly from DB
print("\n=== Recent Assembly Graphs ===")
conn = repo.get_connection()
try:
    cur = conn.cursor()
    cur.execute("SELECT task_id, description, status, graph_json FROM assembly_graphs ORDER BY rowid DESC LIMIT 5")
    rows = cur.fetchall()
    for row in rows:
        print(f"\nTask: {row['task_id']}")
        print(f"Status: {row['status']}")
        print(f"Description: {row['description'][:60] if row['description'] else 'N/A'}...")
        if row['graph_json']:
            graph = json.loads(row['graph_json'])
            print("Node tree:")
            def print_node(node, indent=0):
                label = node.get('label', 'unknown')
                offset = node.get('attachment', {}).get('local_offset', [0,0,0])
                shape = node.get('sub_spec', {})
                prim = shape.get('primitive', '?')
                print(f"{'  '*indent}{label}: offset={[round(o,2) for o in offset]}, {prim}")
                for child in node.get('children', []):
                    print_node(child, indent+1)
            if 'root' in graph:
                print_node(graph['root'])
finally:
    conn.close()

# Check for any spec3d_pending_builds
print("\n=== Pending 3D Builds ===")
conn = repo.get_connection()
try:
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='spec3d_pending_builds'")
    if cur.fetchone():
        cur.execute("SELECT * FROM spec3d_pending_builds ORDER BY rowid DESC LIMIT 3")
        rows = cur.fetchall()
        for row in rows:
            print(dict(row))
    else:
        print("Table spec3d_pending_builds not found")
finally:
    conn.close()
