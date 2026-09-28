import sqlite3, json, os

ROOT = os.path.join(os.path.dirname(__file__), '..')
au_db = os.path.join(ROOT, 'data', 'audit.sqlite')

con = sqlite3.connect(au_db)
con.row_factory = sqlite3.Row

task_id = '0f33fc0e-8ae9-4bda-bcda-a94914ee0434'
rows = con.execute(
    "SELECT log_sequence, action_type, tool_name, decision_factors FROM audit_logs "
    "WHERE task_id=? ORDER BY log_sequence ASC",
    (task_id,)
).fetchall()

print(f"Total audit rows for task: {len(rows)}\n")
for r in rows:
    df = r['decision_factors']
    if df:
        try:
            df_obj = json.loads(df)
            inp = df_obj.get('input', {})
            out = df_obj.get('output', {})
            print(f"[{r['log_sequence']}] {r['action_type']} | {r['tool_name']}")
            print(f"  INPUT:  {json.dumps(inp)}")
            print(f"  OUTPUT: {json.dumps(out)}")
        except Exception:
            print(f"[{r['log_sequence']}] {r['action_type']} | {r['tool_name']} | raw: {df[:200]}")
    else:
        print(f"[{r['log_sequence']}] {r['action_type']} | {r['tool_name']}")

con.close()
