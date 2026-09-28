import sqlite3, json

for db_path in ("data/operational.sqlite", "data/audit.sqlite"):
    print(f"\n=== {db_path} tables ===")
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in cur.fetchall()]
        print(f"  tables: {tables}")

        # Look for anything with task_id column
        tid = "c0469ec9-ea3e-4cd6-b8c3-55eaf0cafdd9"
        for t in tables:
            cur.execute(f"PRAGMA table_info({t})")
            cols = [r[1] for r in cur.fetchall()]
            if "task_id" in cols:
                cur.execute(f"SELECT * FROM {t} WHERE task_id=? ORDER BY rowid DESC LIMIT 5", (tid,))
                rows = cur.fetchall()
                if rows:
                    print(f"\n  [{t}] — {len(rows)} rows for this task:")
                    for row in rows:
                        d = dict(row)
                        # truncate long fields
                        for k, v in d.items():
                            if isinstance(v, str) and len(v) > 300:
                                d[k] = v[:300] + "..."
                        print(f"    {json.dumps(d)}")
        conn.close()
    except Exception as e:
        print(f"  error: {e}")
