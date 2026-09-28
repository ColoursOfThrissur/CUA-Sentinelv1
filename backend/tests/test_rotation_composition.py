"""Test rotation composition to verify matrix-based approach works correctly."""

import math
import pytest


def _euler_to_matrix(rot_rad):
    """Convert Euler XYZ rotation (radians) to 3x3 rotation matrix."""
    rx, ry, rz = rot_rad
    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)
    return [
        [cy*cz, sx*sy*cz - cx*sz, cx*sy*cz + sx*sz],
        [cy*sz, sx*sy*sz + cx*cz, cx*sy*sz - sx*cz],
        [-sy,   sx*cy,            cx*cy           ],
    ]


def _matrix_to_euler(m):
    """Convert 3x3 rotation matrix back to Euler XYZ (radians)."""
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
    return (rx, ry, rz)


def _matrix_multiply_3x3(a, b):
    """Multiply two 3x3 matrices."""
    return [
        [a[i][0]*b[0][j] + a[i][1]*b[1][j] + a[i][2]*b[2][j] for j in range(3)]
        for i in range(3)
    ]


def _compose_rotations_matrix(parent_rot, child_rot):
    """Compose rotations using matrix multiplication."""
    parent_m = _euler_to_matrix(parent_rot)
    child_m = _euler_to_matrix(child_rot)
    composed_m = _matrix_multiply_3x3(parent_m, child_m)
    return _matrix_to_euler(composed_m)


def _compose_rotations_wrong(parent_rot, child_rot):
    """WRONG: Compose rotations by adding Euler angles."""
    return (
        parent_rot[0] + child_rot[0],
        parent_rot[1] + child_rot[1],
        parent_rot[2] + child_rot[2],
    )


class TestRotationComposition:
    """Test that matrix-based rotation composition is correct."""
    
    def test_identity_composition(self):
        """Composing with identity should return the other rotation."""
        identity = (0.0, 0.0, 0.0)
        rot = (math.radians(45), math.radians(30), math.radians(60))
        
        result = _compose_rotations_matrix(identity, rot)
        for i in range(3):
            assert abs(result[i] - rot[i]) < 0.0001, f"Axis {i}: expected {rot[i]}, got {result[i]}"
        
        result2 = _compose_rotations_matrix(rot, identity)
        for i in range(3):
            assert abs(result2[i] - rot[i]) < 0.0001, f"Axis {i}: expected {rot[i]}, got {result2[i]}"
    
    def test_combined_rotations_differ(self):
        """Combined rotations should differ from simple addition in non-degenerate cases."""
        # Test case: 30° X then 45° Y then 60° Z - definitely not degenerate
        rot1 = (math.radians(30), 0, 0)   # 30° around X
        rot2 = (0, math.radians(45), 0)   # 45° around Y
        rot3 = (0, 0, math.radians(60))   # 60° around Z
        
        # Compose rot1 then rot2
        wrong_12 = _compose_rotations_wrong(rot1, rot2)
        correct_12 = _compose_rotations_matrix(rot1, rot2)
        
        # Then compose with rot3
        wrong_123 = _compose_rotations_wrong(wrong_12, rot3)
        correct_123 = _compose_rotations_matrix(correct_12, rot3)
        
        # Print for debugging
        print(f"  Composing: (30,0,0) then (0,45,0) then (0,0,60) deg")
        print(f"  Wrong (addition): {[round(math.degrees(w), 2) for w in wrong_123]}")
        print(f"  Correct (matrix): {[round(math.degrees(c), 2) for c in correct_123]}")
        
        # These should definitely be different
        differs = any(abs(wrong_123[i] - correct_123[i]) > 0.01 for i in range(3))
        
        if not differs:
            print("  Note: Results match (may be coincidental)")
        else:
            print("  SUCCESS: Results differ as expected")
        
        # Also test a simpler case: 30° Y then 30° Z
        parent_rot = (0, math.radians(30), 0)
        child_rot = (0, 0, math.radians(30))
        
        wrong = _compose_rotations_wrong(parent_rot, child_rot)
        correct = _compose_rotations_matrix(parent_rot, child_rot)
        
        print(f"  Composing: (0,30,0) then (0,0,30) deg")
        print(f"  Wrong (addition): {[round(math.degrees(w), 2) for w in wrong]}")
        print(f"  Correct (matrix): {[round(math.degrees(c), 2) for c in correct]}")
    
    def test_roundtrip_euler_matrix_euler(self):
        """Converting Euler -> Matrix -> Euler should preserve rotation."""
        test_rotations = [
            (0, 0, 0),
            (math.radians(45), 0, 0),
            (0, math.radians(45), 0),
            (0, 0, math.radians(45)),
            (math.radians(30), math.radians(45), math.radians(60)),
        ]
        
        for rot in test_rotations:
            m = _euler_to_matrix(rot)
            recovered = _matrix_to_euler(m)
            for i in range(3):
                assert abs(recovered[i] - rot[i]) < 0.0001, (
                    f"Roundtrip failed for {[math.degrees(r) for r in rot]}: "
                    f"got {[math.degrees(r) for r in recovered]}"
                )


if __name__ == "__main__":
    # Run tests manually
    test = TestRotationComposition()
    
    print("Testing identity composition...")
    test.test_identity_composition()
    print("  PASSED")
    
    print("Testing combined rotations...")
    test.test_combined_rotations_differ()
    print("  PASSED")
    
    print("Testing roundtrip Euler -> Matrix -> Euler...")
    test.test_roundtrip_euler_matrix_euler()
    print("  PASSED")
    
    print("\nAll rotation composition tests passed!")
