"""Run Checkpoint 2 - Emit Values Analysis."""

import sys
sys.path.insert(0, '.')

from tests.test_transform_chain import (
    capture_emit_values, compare_emit_to_expected,
    CASE_A_NODES, CASE_A_EXPECTED,
    CASE_B_NODES, CASE_B_EXPECTED,
    CASE_C_NODES, CASE_C_EXPECTED,
)

print('='*60)
print('CHECKPOINT 2: Emit Values Analysis')
print('='*60)

for case_name, nodes, expected in [
    ('Case_A', CASE_A_NODES, CASE_A_EXPECTED),
    ('Case_B', CASE_B_NODES, CASE_B_EXPECTED),
    ('Case_C', CASE_C_NODES, CASE_C_EXPECTED),
]:
    print(f'\n{case_name}:')
    emit = capture_emit_values(nodes, case_name)
    errors, frame_type = compare_emit_to_expected(emit, expected, case_name)
    
    print(f'  Frame type detected: {frame_type}')
    print(f'  Emit values:')
    for name, vals in emit.items():
        print(f'    {name}: loc={vals["location"]}, rot={vals["rotation_deg"]}')
    
    if errors:
        print(f'  ERRORS:')
        for e in errors:
            print(f'    - {e}')
    
    print(f'  Expected world positions:')
    for exp in expected:
        print(f'    {exp.name}: {exp.position}')
