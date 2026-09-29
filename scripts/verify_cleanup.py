import sys, ast, os
sys.stdout.reconfigure(encoding='utf-8')
files = {
    'stage4_resolver.py': r'c:\Users\derik\Desktop\Derik\Projects\CUA-Sentinel\backend\core\blender_pipeline\progressive_v2\stages\stage4_resolver.py',
    'controller.py': r'c:\Users\derik\Desktop\Derik\Projects\CUA-Sentinel\backend\core\blender_pipeline\progressive_v2\controller.py',
    'executor.py': r'c:\Users\derik\Desktop\Derik\Projects\CUA-Sentinel\backend\core\blender_pipeline\progressive_v2\executor.py',
}
dead_markers = [
    'run_legacy','_resolve_relative_to_pass2\n','_resolve_bridge_pass2\n',
    '_resolve_strut_pass2\n','_resolve_radial_bridge_pass2\n',
    'TransformComparison','compare_transform_systems','log_transform_comparison',
    'SocketClosureResult','verify_socket_closure','verify_all_socket_closures',
    'legacy_positions','legacy_rotations','_find_reference_world_matrix',
    '_compute_assembly_world_matrix','_find_reference_for_root_child',
    '_compare_transform_systems','_compute_world_transform_legacy',
    '_get_reference_node_for_parent','_get_parent_world_rotation',
    '_get_parent_world_position','_get_reference_bbox','_bottom_face_offset',
]
for name, path in files.items():
    src = open(path, encoding='utf-8').read()
    try:
        ast.parse(src)
        parse_status = 'PARSE OK'
    except SyntaxError as e:
        parse_status = f'SYNTAX ERROR: {e}'
    hits = [m.strip() for m in dead_markers if m in src]
    lines = src.count('\n')
    print(f'{name}: {parse_status}, {lines} lines, dead markers: {hits if hits else "none"}')
