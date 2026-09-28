import sqlite3, json, os

ROOT = os.path.join(os.path.dirname(__file__), '..')
au_db = os.path.join(ROOT, 'data', 'audit.sqlite')
op_db = os.path.join(ROOT, 'data', 'operational.sqlite')
task_id = '0f33fc0e-8ae9-4bda-bcda-a94914ee0434'

# Full MODEL_GENERATED row
con = sqlite3.connect(au_db)
con.row_factory = sqlite3.Row
rows = con.execute(
    "SELECT * FROM audit_logs WHERE task_id=? AND action_type='MODEL_GENERATED'",
    (task_id,)
).fetchall()
print(f"MODEL_GENERATED rows: {len(rows)}")
for r in rows:
    d = dict(r)
    for k, v in d.items():
        if isinstance(v, str) and len(v) > 500:
            d[k] = v[:500] + '...'
    print(json.dumps(d, indent=2, default=str))
con.close()

# Task input_payload and result_payload
con2 = sqlite3.connect(op_db)
con2.row_factory = sqlite3.Row
task = con2.execute("SELECT input_payload, result_payload FROM tasks WHERE task_id=?", (task_id,)).fetchone()
if task:
    print("\n=== INPUT PAYLOAD ===")
    try:
        ip = json.loads(task['input_payload'])
        print(json.dumps(ip, indent=2, default=str)[:2000])
    except Exception:
        print(task['input_payload'][:2000])
con2.close()

# Check if decomp task was stored
con3 = sqlite3.connect(op_db)
con3.row_factory = sqlite3.Row
decomp_tasks = con3.execute(
    "SELECT task_id, status, input_payload FROM tasks WHERE task_id LIKE 'decomp_%' ORDER BY rowid DESC LIMIT 5"
).fetchall()
print(f"\n=== DECOMP TASKS: {len(decomp_tasks)} ===")
for t in decomp_tasks:
    print(f"  {t['task_id']} status={t['status']}")
con3.close()
