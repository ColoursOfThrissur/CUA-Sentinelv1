import sqlite3, json

conn = sqlite3.connect("data/operational.sqlite")
cur = conn.cursor()

for table in ("task_steps", "artifacts", "tasks"):
    cur.execute(f"PRAGMA table_info({table})")
    cols = [r[1] for r in cur.fetchall()]
    print(f"{table}: {cols}")

conn.close()
