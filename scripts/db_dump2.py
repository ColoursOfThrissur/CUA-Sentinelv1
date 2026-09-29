import sqlite3, json, sys

conn = sqlite3.connect('data/operational.sqlite')
cur = conn.cursor()

print("=== spec3d_pending_builds ===")
cur.execute("SELECT build_id, expires_at, data_json FROM spec3d_pending_builds ORDER BY rowid DESC")
rows = cur.fetchall()
print(f"count: {len(rows)}")
for r in rows:
    try:
        d = json.loads(r[2])
        print(f"  build_id={r[0]} expires={r[1]}")
        print(f"  keys={list(d.keys())}")
        print(f"  status={d.get('status')} task_id={d.get('task_id')} node={d.get('node_label') or d.get('label')}")
        print()
    except Exception as e:
        print(f"  {r[0]}: parse error {e}: {r[2][:200]}")

print("=== llm_traces (last 10, padlock related) ===")
cur.execute("PRAGMA table_info(llm_traces)")
cols = [c[1] for c in cur.fetchall()]
print("cols:", cols)
cur.execute("SELECT * FROM llm_traces ORDER BY rowid DESC LIMIT 10")
for r in cur.fetchall():
    row = dict(zip(cols, r))
    print(f"  trace_id={row.get('trace_id')} task_id={row.get('task_id')} model={row.get('model_id')} status={row.get('status')}")
    prompt = str(row.get('prompt_text') or row.get('prompt') or '')[:100]
    print(f"  prompt[:100]={prompt}")
    print()

conn.close()
sys.stdout.flush()
