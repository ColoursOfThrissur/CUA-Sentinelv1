import sqlite3, json, os

ROOT = os.path.join(os.path.dirname(__file__), '..')
op_db = os.path.join(ROOT, 'data', 'operational.sqlite')
au_db = os.path.join(ROOT, 'data', 'audit.sqlite')

def dump(db_path, label):
    try:
        con = sqlite3.connect(db_path)
        con.row_factory = sqlite3.Row
        tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        print(f"\n=== {label} TABLES: {tables} ===")
        for t in tables:
            try:
                rows = con.execute(f"SELECT * FROM {t} ORDER BY rowid DESC LIMIT 5").fetchall()
                if rows:
                    print(f"\n-- {t} (last 5) --")
                    for r in rows:
                        d = dict(r)
                        for k, v in d.items():
                            if isinstance(v, str) and len(v) > 400:
                                d[k] = v[:400] + '...'
                        print(json.dumps(d, default=str))
            except Exception as te:
                print(f"  skip {t}: {te}")
        con.close()
    except Exception as e:
        print(f"ERROR reading {label}: {e}")

dump(op_db, "OPERATIONAL")
dump(au_db, "AUDIT")
