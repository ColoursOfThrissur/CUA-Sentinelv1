import sqlite3, json

conn = sqlite3.connect("data/audit.sqlite")
conn.row_factory = sqlite3.Row
cur = conn.cursor()

tid = "c0469ec9-ea3e-4cd6-b8c3-55eaf0cafdd9"

cur.execute("""
    SELECT log_sequence, action_type, tool_name, decision_factors, created_at
    FROM audit_logs WHERE task_id=? ORDER BY log_sequence ASC
""", (tid,))

rows = cur.fetchall()
print(f"Total audit entries: {len(rows)}\n")

for row in rows:
    print(f"[{row['log_sequence']}] {row['action_type']} | tool={row['tool_name']} | {row['created_at']}")
    if row["decision_factors"]:
        try:
            df = json.loads(row["decision_factors"])
            inp = df.get("input", {})
            out = df.get("output", {})
            if inp:
                print(f"  INPUT : {json.dumps(inp)[:300]}")
            if out:
                print(f"  OUTPUT: {json.dumps(out)[:200]}")
        except Exception:
            print(f"  {str(row['decision_factors'])[:300]}")
    print()

conn.close()
