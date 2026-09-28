import sqlite3, json, os

ROOT = os.path.join(os.path.dirname(__file__), '..')
au_db = os.path.join(ROOT, 'data', 'audit.sqlite')
op_db = os.path.join(ROOT, 'data', 'operational.sqlite')

con = sqlite3.connect(au_db)
con.row_factory = sqlite3.Row
task_id = '0f33fc0e-8ae9-4bda-bcda-a94914ee0434'

rows = con.execute(
    "SELECT log_sequence, action_type, decision_factors FROM audit_logs "
    "WHERE task_id=? AND action_type='MODEL_GENERATED' ORDER BY log_sequence ASC",
    (task_id,)
).fetchall()
print(f"MODEL_GENERATED events: {len(rows)}")
for r in rows:
    df = r['decision_factors']
    if df:
        try:
            obj = json.loads(df)
            print(f"\n[{r['log_sequence']}] MODEL_GENERATED")
            # Print full decision_factors
            print(json.dumps(obj, indent=2)[:4000])
        except Exception as e:
            print(f"  raw: {df[:2000]}")
con.close()

# Also check assembly_graphs for this task
print("\n\n=== ASSEMBLY GRAPHS ===")
con2 = sqlite3.connect(op_db)
con2.row_factory = sqlite3.Row
graphs = con2.execute(
    "SELECT task_id, description, status, graph_json FROM assembly_graphs WHERE task_id LIKE ? OR task_id LIKE ?",
    (f'%{task_id[:8]}%', f'decomp_%')
).fetchall()
print(f"Assembly graphs found: {len(graphs)}")
for g in graphs:
    print(f"\ntask_id={g['task_id']} status={g['status']}")
    gj = g['graph_json']
    if gj:
        try:
            obj = json.loads(gj)
            print(json.dumps(obj, indent=2)[:3000])
        except Exception:
            print(gj[:1000])
con2.close()
