import sqlite3, json, sys

def dump_db(path):
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in cur.fetchall()]
    for t in tables:
        cur.execute(f"SELECT count(*) FROM {t}")
        count = cur.fetchone()[0]
        if count == 0:
            continue
        print(f"\n=== {path} :: {t} ({count} rows) ===")
        cur.execute(f"PRAGMA table_info({t})")
        cols = [c[1] for c in cur.fetchall()]
        print("cols:", cols)
        cur.execute(f"SELECT * FROM {t} ORDER BY rowid DESC LIMIT 5")
        for r in cur.fetchall():
            print(r)
    conn.close()

for db in ["data/operational.sqlite", "data/audit.sqlite", "data/knowledge.sqlite", "data/state.sqlite"]:
    try:
        dump_db(db)
    except Exception as e:
        print(f"ERROR {db}: {e}")

sys.stdout.flush()
