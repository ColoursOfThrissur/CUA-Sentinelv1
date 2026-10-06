import sqlite3, json, os, sys

ROOT = os.path.join(os.path.dirname(__file__), '..')
op_db = os.path.join(ROOT, 'data', 'operational.sqlite')
au_db = os.path.join(ROOT, 'data', 'audit.sqlite')

tid = 'a02e0d7a-fb80-425e-809d-de753f9ca9ad'

op = sqlite3.connect(op_db)
op.row_factory = sqlite3.Row

# Full result payload
task = dict(op.execute('SELECT input_payload, result_payload FROM tasks WHERE task_id=?', (tid,)).fetchone())
print('=== RESULT PAYLOAD ===')
try:
    res = json.loads(task['result_payload'])
    print(res.get('response', '')[:1000])
except Exception as e:
    print(task['result_payload'][:1000])

# All LLM traces for this task (by UUID prefix)
print('\n=== LLM TRACES (all stages) ===')
rows = op.execute(
    "SELECT trace_id, task_id, response, error FROM llm_traces WHERE task_id LIKE ? ORDER BY trace_id ASC",
    (f'%{tid[:8]}%',)
).fetchall()
print(f'Total traces: {len(rows)}')
for r in rows:
    d = dict(r)
    print(f'\n  [{d["trace_id"]}] {d["task_id"]}')
    resp = d['response'] or ''
    print(f'    {resp[:400]}')
    if d['error']:
        print(f'    ERROR: {d["error"]}')

op.close()

# Audit log sequence for this task
print('\n=== AUDIT LOG SEQUENCE ===')
au = sqlite3.connect(au_db)
au.row_factory = sqlite3.Row
rows = au.execute(
    "SELECT log_sequence, task_id, action_type, decision_factors FROM audit_logs WHERE task_id LIKE ? ORDER BY log_sequence ASC",
    (f'%{tid[:8]}%',)
).fetchall()
print(f'Total audit entries: {len(rows)}')
for r in rows:
    df = r['decision_factors']
    print(f'  [{r["log_sequence"]}] {r["task_id"][:70]} | {r["action_type"]}')
    if df and df not in ('null', None, ''):
        print(f'    factors: {df[:400]}')
au.close()

# Also check the artifact
print('\n=== ARTIFACT ===')
art_dir = os.path.join(ROOT, 'data', 'artifacts', tid)
if os.path.exists(art_dir):
    for f in os.listdir(art_dir):
        fpath = os.path.join(art_dir, f)
        print(f'  {f} ({os.path.getsize(fpath)} bytes)')
        try:
            content = open(fpath, encoding='utf-8', errors='replace').read()
            print(content[:2000])
        except Exception as e:
            print(f'  read error: {e}')
else:
    print('  no artifact dir')
