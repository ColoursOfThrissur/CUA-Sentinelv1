import os, ast

path = r'c:\Users\derik\Desktop\Derik\Projects\CUA-Sentinel\backend\core\blender_pipeline\progressive_v2\executor.py'
with open(path, encoding='utf-8') as f:
    lines = f.readlines()

start = next(i for i in range(len(lines)) if 'def _compute_world_transform_legacy(' in lines[i])
end = next(i for i in range(len(lines)) if 'async def _create_primitive(' in lines[i])
print(f'Removing lines {start+1} to {end} ({end-start} lines)')

new_lines = lines[:start] + lines[end:]
with open(path, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

with open(path, encoding='utf-8') as f:
    src = f.read()
ast.parse(src)
print('PARSE OK, new size:', os.path.getsize(path))
