import sqlite3, json, sys

conn = sqlite3.connect('data/operational.sqlite')
cur = conn.cursor()
cur.execute("SELECT build_id, expires_at, data_json FROM spec3d_pending_builds ORDER BY rowid DESC")
rows = cur.fetchall()
conn.close()

for build_id, expires, data_json in rows:
    d = json.loads(data_json)
    name = d.get('name', '')
    spec = d.get('spec', {})
    parts = spec.get('parts', [])
    # Check if any part label contains 'shackle' or 'lock'
    part_labels = []
    if isinstance(parts, list):
        for p in parts:
            if isinstance(p, dict):
                part_labels.append(p.get('label') or p.get('name') or str(list(p.keys())[:3]))
    elif isinstance(parts, dict):
        part_labels = list(parts.keys())
    
    is_padlock = 'lock' in name.lower() or 'shackle' in name.lower() or any('shackle' in l.lower() or 'lock' in l.lower() for l in part_labels)
    print(f"build_id={build_id} name={name} expires={expires} parts={part_labels[:5]} padlock={is_padlock}")

sys.stdout.flush()
