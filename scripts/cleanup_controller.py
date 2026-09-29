import os

path = r'c:\Users\derik\Desktop\Derik\Projects\CUA-Sentinel\backend\core\blender_pipeline\progressive_v2\controller.py'
with open(path, encoding='utf-8') as f:
    lines = f.readlines()

start = next(i for i in range(len(lines)) if '# LEGACY: Reference Discovery Methods' in lines[i]) - 1
end = next(i for i in range(len(lines)) if 'async def _build_part' in lines[i])
print(f'Removing lines {start+1} to {end} ({end-start} lines)')

new_lines = lines[:start] + lines[end:]
with open(path, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print('Done, new size:', os.path.getsize(path))
