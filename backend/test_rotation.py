"""Test rotation composition to verify it's working correctly."""
import math

def _euler_to_matrix(rot_rad):
    rx, ry, rz = rot_rad[0], rot_rad[1], rot_rad[2]
    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)
    return [
        [cy*cz, sx*sy*cz - cx*sz, cx*sy*cz + sx*sz],
        [cy*sz, sx*sy*sz + cx*cz, cx*sy*sz - sx*cz],
        [-sy,   sx*cy,            cx*cy           ],
    ]

def _matrix_multiply_3x3(a, b):
    return [
        [a[i][0]*b[0][j] + a[i][1]*b[1][j] + a[i][2]*b[2][j] for j in range(3)]
        for i in range(3)
    ]

def _matrix_to_euler(m):
    if abs(m[2][0]) < 0.9999:
        ry = math.asin(-m[2][0])
        rx = math.atan2(m[2][1], m[2][2])
        rz = math.atan2(m[1][0], m[0][0])
    else:
        rz = 0.0
        if m[2][0] < 0:
            ry = math.pi / 2
            rx = math.atan2(m[0][1], m[0][2])
        else:
            ry = -math.pi / 2
            rx = math.atan2(-m[0][1], -m[0][2])
    return [rx, ry, rz]

def _matrix_vector_multiply(m, v):
    return [
        m[0][0]*v[0] + m[0][1]*v[1] + m[0][2]*v[2],
        m[1][0]*v[0] + m[1][1]*v[1] + m[1][2]*v[2],
        m[2][0]*v[0] + m[2][1]*v[1] + m[2][2]*v[2],
    ]

def _compose_rotations(parent_rot, child_rot):
    prx, pry, prz = parent_rot[0], parent_rot[1], parent_rot[2]
    crx, cry, crz = child_rot[0], child_rot[1], child_rot[2]
    if abs(prx) < 0.0001 and abs(pry) < 0.0001 and abs(prz) < 0.0001:
        return list(child_rot)
    if abs(crx) < 0.0001 and abs(cry) < 0.0001 and abs(crz) < 0.0001:
        return list(parent_rot)
    parent_m = _euler_to_matrix(parent_rot)
    child_m = _euler_to_matrix(child_rot)
    composed_m = _matrix_multiply_3x3(parent_m, child_m)
    result = _matrix_to_euler(composed_m)
    return [round(result[0], 6), round(result[1], 6), round(result[2], 6)]

def _rotate_vector(v, rot_rad):
    m = _euler_to_matrix(rot_rad)
    return _matrix_vector_multiply(m, v)

print("=" * 60)
print("ROTATION COMPOSITION TEST")
print("=" * 60)

# Test 1: Parent 90Z, Child 90X
print("\nTest 1: Parent 90Z, Child 90X")
parent = [0, 0, math.pi/2]
child = [math.pi/2, 0, 0]

wrong = [parent[0] + child[0], parent[1] + child[1], parent[2] + child[2]]
print(f"  Euler addition: [{math.degrees(wrong[0]):.1f}, {math.degrees(wrong[1]):.1f}, {math.degrees(wrong[2]):.1f}]")

composed = _compose_rotations(parent, child)
print(f"  Matrix compose: [{math.degrees(composed[0]):.1f}, {math.degrees(composed[1]):.1f}, {math.degrees(composed[2]):.1f}]")

print(f"  Different? {wrong != composed}")

# Test 2: Verify with vector
print("\nTest 2: Vector rotation verification")
# If parent is 90Z, child's local X points to world Y
# If child is then 90X (around its local X = world Y), child's local Z points to world X
# So [0,0,1] in child space should become [1,0,0] in world space

# First, what does the composed rotation do to [0,0,1]?
test_vec = [0, 0, 1]
result = _rotate_vector(test_vec, composed)
print(f"  [0,0,1] with composed rotation: [{result[0]:.3f}, {result[1]:.3f}, {result[2]:.3f}]")

# What SHOULD happen:
# Parent 90Z: X->Y, Y->-X, Z->Z
# Child 90X (in parent's frame, so around world Y): Z->X, X->Z
# Combined: child's Z should point to world X
print(f"  Expected: [1, 0, 0]")

# Test 3: Simple 90Z rotation
print("\nTest 3: Simple 90Z rotation")
rot_90z = [0, 0, math.pi/2]
vec_x = [1, 0, 0]
result = _rotate_vector(vec_x, rot_90z)
print(f"  [1,0,0] rotated 90Z: [{result[0]:.3f}, {result[1]:.3f}, {result[2]:.3f}]")
print(f"  Expected: [0, 1, 0]")

# Test 4: Simple 90X rotation
print("\nTest 4: Simple 90X rotation")
rot_90x = [math.pi/2, 0, 0]
vec_z = [0, 0, 1]
result = _rotate_vector(vec_z, rot_90x)
print(f"  [0,0,1] rotated 90X: [{result[0]:.3f}, {result[1]:.3f}, {result[2]:.3f}]")
print(f"  Expected: [0, -1, 0]")

print("\n" + "=" * 60)
