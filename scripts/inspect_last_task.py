import sqlite3, json

conn = sqlite3.connect("data/operational.sqlite")
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# Most recent task
cur.execute("SELECT task_id, created_at, status, input_payload, result_payload, error_message FROM tasks ORDER BY created_at DESC LIMIT 1")
task = dict(cur.fetchone())
tid = task["task_id"]
print("=== TASK ===")
print(f"  id     : {tid}")
print(f"  status : {task['status']}")
print(f"  created: {task['created_at']}")
try:
    payload = json.loads(task["input_payload"] or "{}")
    print(f"  prompt : {str(payload.get('prompt',''))[:200]}")
except Exception:
    pass
if task["error_message"]:
    print(f"  error  : {task['error_message'][:300]}")
try:
    result = json.loads(task["result_payload"] or "{}")
    resp = result.get("response", "")
    print(f"  result : {str(resp)[:400]}")
except Exception:
    pass

# Steps
print("\n=== STEPS ===")
cur.execute("""
    SELECT step_order, step_type, description, status, output_summary, created_at
    FROM task_steps WHERE task_id=? ORDER BY step_order ASC
""", (tid,))
for row in cur.fetchall():
    print(f"  [{row['status']:12s}] #{row['step_order']} {row['step_type']} — {row['description']}")
    if row["output_summary"]:
        try:
            s = json.loads(row["output_summary"])
            print(f"             out: {json.dumps(s)[:300]}")
        except Exception:
            print(f"             out: {str(row['output_summary'])[:300]}")

# Audit log for this task
print("\n=== AUDIT (system_events) ===")
try:
    cur.execute("""
        SELECT event_type, created_at, payload
        FROM system_events WHERE task_id=? ORDER BY created_at ASC
    """, (tid,))
    for row in cur.fetchall():
        try:
            p = json.loads(row["payload"] or "{}")
        except Exception:
            p = {}
        print(f"  [{row['event_type']}] {row['created_at']}")
        if p:
            print(f"    {json.dumps(p)[:300]}")
except Exception as e:
    print(f"  (no system_events or wrong db: {e})")

conn.close()
