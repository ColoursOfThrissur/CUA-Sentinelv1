import sqlite3, json, sys, os, re

conn = sqlite3.connect('data/operational.sqlite')
cur = conn.cursor()
cur.execute("""
    SELECT DISTINCT task_id FROM llm_traces 
    WHERE task_id LIKE '%shackle%' OR task_id LIKE '%lock_body%'
    ORDER BY rowid DESC LIMIT 20
""")
trace_tasks = [r[0] for r in cur.fetchall()]
conn.close()

# Extract UUID: stage2_<uuid>_<node_label>
# UUID pattern: 8-4-4-4-12
uuid_re = re.compile(r'([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})')
parent_ids = set()
for t in trace_tasks:
    m = uuid_re.search(t)
    if m:
        parent_ids.add(m.group(1))

print("parent task IDs:", parent_ids)

artifact_base = 'data/artifacts'
for task_id in sorted(parent_ids):
    task_dir = os.path.join(artifact_base, task_id)
    if not os.path.exists(task_dir):
        print(f"no artifact dir for {task_id}")
        continue
    files = sorted(os.listdir(task_dir))
    print(f"\n=== artifacts/{task_id} ({len(files)} files) ===")
    for f in files:
        fpath = os.path.join(task_dir, f)
        size = os.path.getsize(fpath)
        print(f"  {f} ({size} bytes)")
        if size < 15000:
            try:
                content = open(fpath, encoding='utf-8', errors='replace').read()
                print(content[:5000])
                print("---")
            except Exception as e:
                print(f"  read error: {e}")

sys.stdout.flush()
