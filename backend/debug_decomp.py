import json

with open('data/builds_v2/m_8433a0439d/manifest.json') as f:
    d = json.load(f)

mha = d['nodes']['m_8433a0439d_motor_housing_assembly_5']
nested = mha['stage_outputs']['decomposition_hint']['_nested_children']
existing = set(n['label'] for n in d['nodes'].values())
new_labels = [c['label'] for c in nested]
collisions = [l for l in new_labels if l in existing]
root_count = sum(1 for c in nested if c.get('socket_type') == 'ROOT')

print('nested=%d root=%d' % (len(nested), root_count))
print('existing:', sorted(existing))
print('new_labels:', new_labels)
print('collisions:', collisions)

# Simulate _flatten_children
def flatten_children(children_data):
    result = []
    for child in children_data:
        child_copy = {k: v for k, v in child.items() if k != 'children'}
        raw_nested = child.get('children', [])
        if raw_nested:
            child_copy['is_complex'] = True
            child_copy['has_subcomponents'] = True
            child_copy['_nested_children'] = flatten_children(raw_nested)
        result.append(child_copy)
    return result

flat = flatten_children(nested)
print('flat count:', len(flat))
for c in flat:
    print('  label=%s socket=%s has_nested=%s' % (c['label'], c.get('socket_type'), '_nested_children' in c))
