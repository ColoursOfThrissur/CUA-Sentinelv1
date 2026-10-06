import json
import os
from pathlib import Path

builds_dir = Path('data/builds_v2')
# Get all dirs with llm_log but no manifest (recent failed/incomplete builds)
recent = []
for d in builds_dir.iterdir():
    if not d.is_dir():
        continue
    log = d / 'llm_log.json'
    manifest = d / 'manifest.json'
    if log.exists():
        mtime = log.stat().st_mtime
        recent.append((mtime, d, manifest.exists()))

recent.sort(reverse=True)

for mtime, d, has_manifest in recent[:5]:
    log_path = d / 'llm_log.json'
    try:
        entries = json.loads(log_path.read_text(encoding='utf-8'))
    except Exception as e:
        print('%s: error reading log: %s' % (d.name, e))
        continue

    print('%s (has_manifest=%s, entries=%d)' % (d.name, has_manifest, len(entries)))
    for entry in entries:
        resp = entry.get('response', '')
        # Check if response has nested children
        try:
            data = json.loads(resp)
            children = data.get('children', [])
            has_nested = any('children' in c for c in children)
            print('  node=%s children=%d has_nested_children=%s' % (
                entry.get('node', '?'), len(children), has_nested))
        except Exception:
            print('  node=%s response_not_json' % entry.get('node', '?'))
