"""Trace the actual transform chain."""
import math

# Simulate arm_axis with rotation [90, 0, 0] (horizontal along Y)
# Child at LEFT_END should end up at world -Y (since local -Z becomes world -Y after 90° X rotation)

def rotate_vector(v, rot_rad):
    """Rotate vector by Euler XYZ."""
    rx, ry, rz = rot_rad
    x, y, z = v
    
    # Apply Rx
    cx, sx = math.cos(rx), math.sin(rx)
    y1 = cx * y - sx * z
    z1 = sx * y + cx * z
    
    # Apply Ry  
    cy, sy = math.cos(ry), math.sin(ry)
    x2 = cy * x + sy * z1
    z2 = -sy * x + cy * z1
    
    # Apply Rz
    cz, sz = math.cos(rz), math.sin(rz)
    x3 = cz * x2 - sz * y1
    y3 = sz * x2 + cz * y1
    
    return (round(x3, 4), round(y3, 4), round(z2, 4))

# Parent: arm_axis at world [0, 0, 1.1] with rotation [90°, 0, 0]
parent_world_pos = (0, 0, 1.1)
parent_rot_deg = [90, 0, 0]  # This is WRONG - should be [0, 90, 0] for left-right
parent_rot_rad = tuple(math.radians(r) for r in parent_rot_deg)

# Child: strike_shield with local offset [0, 0, -0.16] (LEFT_END in parent's local frame)
child_local_offset = (0, 0, -0.16)

# Transform to world
rotated_offset = rotate_vector(child_local_offset, parent_rot_rad)
child_world_pos = tuple(round(p + o, 4) for p, o in zip(parent_world_pos, rotated_offset))

print("=== With rotation [90, 0, 0] (horizontal along Y) ===")
print(f"Parent world pos: {parent_world_pos}")
print(f"Parent rotation (deg): {parent_rot_deg}")
print(f"Child local offset: {child_local_offset}")
print(f"Rotated offset: {rotated_offset}")
print(f"Child world pos: {child_world_pos}")
print()

# Now with CORRECT rotation [0, 90, 0] (horizontal along X)
parent_rot_deg2 = [0, 90, 0]
parent_rot_rad2 = tuple(math.radians(r) for r in parent_rot_deg2)

rotated_offset2 = rotate_vector(child_local_offset, parent_rot_rad2)
child_world_pos2 = tuple(round(p + o, 4) for p, o in zip(parent_world_pos, rotated_offset2))

print("=== With rotation [0, 90, 0] (horizontal along X) ===")
print(f"Parent world pos: {parent_world_pos}")
print(f"Parent rotation (deg): {parent_rot_deg2}")
print(f"Child local offset: {child_local_offset}")
print(f"Rotated offset: {rotated_offset2}")
print(f"Child world pos: {child_world_pos2}")
print()

print("=== CONCLUSION ===")
print("With [90,0,0]: local -Z becomes world -Y → child at (0, 0.16, 1.1) - FRONT/BACK")
print("With [0,90,0]: local -Z becomes world -X → child at (-0.16, 0, 1.1) - LEFT/RIGHT ✓")
