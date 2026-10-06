import json
from pathlib import Path

builds_dir = Path('data/builds_v2')
recent = []
for d in builds_dir.iterdir():
    if not d.is_dir():
        continue
    log = d / 'llm_log.json'
    if log.exists():
        recent.append((log.stat().st_mtime, d))

recent.sort(reverse=True)

for mtime, d in recent[:8]:
    log_path = d / 'llm_log.json'
    has_manifest = (d / 'manifest.json').exists()
    try:
        entries = json.loads(log_path.read_text(encoding='utf-8'))
    except Exception as e:
        print('%s: error: %s' % (d.name, e))
        continue

    print('%s has_manifest=%s entries=%d' % (d.name, has_manifest, len(entries)))
    for entry in entries:
        resp = entry.get('response', '')
        node = entry.get('node', '?')
        try:
            data = json.loads(resp)
            def count_nodes(obj, depth=0):
                total = 1
                for c in obj.get('children', []):
                    total += count_nodes(c, depth+1)
                return total
            children = data.get('children', [])
            total = sum(count_nodes(c) for c in children)
            print('  node=%-40s top_children=%d total_in_tree=%d' % (node[:40], len(children), total))
        except Exception:
            print('  node=%-40s PARSE_ERROR' % node[:40])
    print()
