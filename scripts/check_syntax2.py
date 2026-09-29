import ast, sys
files = [
    'backend/core/blender_pipeline/progressive_v2/node_types.py',
    'backend/core/blender_pipeline/progressive_v2/executor.py',
    'backend/core/blender_pipeline/progressive_v2/decomposer.py',
]
for f in files:
    try:
        ast.parse(open(f, encoding='utf-8').read())
        print(f'OK: {f}')
    except SyntaxError as e:
        print(f'FAIL: {f} line {e.lineno}: {e.msg}')
sys.stdout.flush()
