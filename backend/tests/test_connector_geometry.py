"""Tests for connector_geometry module — endpoint-based connector transforms."""

import pytest
import math
from core.connector_geometry import (
    Vec3,
    Quaternion,
    compute_connector_transform,
    compute_strut_endpoints,
    compute_radial_strut_transforms,
    is_connector_part,
    resolve_connector_from_offset,
)


class TestVec3:
    def test_basic_operations(self):
        v1 = Vec3(1, 2, 3)
        v2 = Vec3(4, 5, 6)
        
        # Subtraction
        diff = v2 - v1
        assert diff.x == 3
        assert diff.y == 3
        assert diff.z == 3
        
        # Addition
        sum_v = v1 + v2
        assert sum_v.x == 5
        assert sum_v.y == 7
        assert sum_v.z == 9
        
        # Scalar multiplication
        scaled = v1 * 2
        assert scaled.x == 2
        assert scaled.y == 4
        assert scaled.z == 6

    def test_length_and_normalize(self):
        v = Vec3(3, 4, 0)
        assert v.length() == 5.0
        
        n = v.normalized()
        assert abs(n.length() - 1.0) < 1e-6
        assert abs(n.x - 0.6) < 1e-6
        assert abs(n.y - 0.8) < 1e-6

    def test_dot_product(self):
        v1 = Vec3(1, 0, 0)
        v2 = Vec3(0, 1, 0)
        assert v1.dot(v2) == 0  # Perpendicular
        
        v3 = Vec3(1, 0, 0)
        assert v1.dot(v3) == 1  # Parallel

    def test_cross_product(self):
        x = Vec3(1, 0, 0)
        y = Vec3(0, 1, 0)
        z = x.cross(y)
        assert abs(z.x) < 1e-6
        assert abs(z.y) < 1e-6
        assert abs(z.z - 1.0) < 1e-6


class TestQuaternion:
    def test_identity(self):
        q = Quaternion(1, 0, 0, 0)
        euler = q.to_euler_xyz()
        assert all(abs(e) < 1e-6 for e in euler)

    def test_rotation_between_same_vector(self):
        v = Vec3(0, 0, 1)
        q = Quaternion.rotation_between(v, v)
        # Should be identity
        assert abs(q.w - 1.0) < 1e-6

    def test_rotation_between_opposite_vectors(self):
        v1 = Vec3(0, 0, 1)
        v2 = Vec3(0, 0, -1)
        q = Quaternion.rotation_between(v1, v2)
        # Should be 180 degree rotation
        euler = q.to_euler_xyz()
        # One of the angles should be ~pi
        assert any(abs(abs(e) - math.pi) < 0.1 for e in euler)

    def test_rotation_90_degrees(self):
        # Rotate from +Z to +X
        v1 = Vec3(0, 0, 1)
        v2 = Vec3(1, 0, 0)
        q = Quaternion.rotation_between(v1, v2)
        euler_deg = q.to_euler_degrees()
        # Should have ~90 degree Y rotation
        assert abs(euler_deg[1] - (-90)) < 5 or abs(euler_deg[1] - 90) < 5


class TestComputeConnectorTransform:
    def test_vertical_connector(self):
        """Vertical connector from (0,0,0) to (0,0,10)."""
        result = compute_connector_transform((0, 0, 0), (0, 0, 10))
        
        assert result["depth"] == 10.0
        assert result["location"] == (0, 0, 5)  # Midpoint
        # Rotation should be identity (already pointing +Z)
        euler = result["rotation_euler_rad"]
        assert all(abs(e) < 0.1 for e in euler)

    def test_horizontal_connector_x(self):
        """Horizontal connector along X axis."""
        result = compute_connector_transform((0, 0, 5), (10, 0, 5))
        
        assert result["depth"] == 10.0
        assert result["location"] == (5, 0, 5)
        # Should have ~90 degree Y rotation
        euler_deg = result["rotation_euler_deg"]
        assert abs(abs(euler_deg[1]) - 90) < 5

    def test_diagonal_connector(self):
        """Diagonal connector at 45 degrees."""
        result = compute_connector_transform((0, 0, 0), (10, 0, 10))
        
        expected_length = math.sqrt(200)  # ~14.14
        assert abs(result["depth"] - expected_length) < 0.01
        assert result["location"] == (5, 0, 5)
        # Should have ~45 degree tilt
        euler_deg = result["rotation_euler_deg"]
        assert abs(abs(euler_deg[1]) - 45) < 5


class TestComputeStrutEndpoints:
    def test_basic_strut(self):
        """Strut from pillar top to dish bottom."""
        start, end = compute_strut_endpoints(
            parent_center=(0, 0, 10),  # Pillar at Z=10
            parent_radius=2.0,
            parent_half_z=5.0,
            child_center=(0, 0, 25),   # Dish at Z=25
            child_radius=8.0,
            child_half_z=4.0,
            strut_offset_angle_deg=0,
        )
        
        # Start should be at pillar top surface, at radius
        assert start[0] == 2.0  # parent_radius * cos(0)
        assert start[1] == 0.0
        assert start[2] == 15.0  # parent_center_z + parent_half_z
        
        # End should be at dish bottom surface, at radius
        assert end[0] == 8.0  # child_radius * cos(0)
        assert end[1] == 0.0
        assert end[2] == 21.0  # child_center_z - child_half_z

    def test_strut_at_90_degrees(self):
        """Strut at 90 degree compass angle (+Y direction)."""
        start, end = compute_strut_endpoints(
            parent_center=(0, 0, 0),
            parent_radius=1.0,
            parent_half_z=1.0,
            child_center=(0, 0, 5),
            child_radius=2.0,
            child_half_z=1.0,
            strut_offset_angle_deg=90,
        )
        
        # At 90 degrees, X should be ~0, Y should be radius
        assert abs(start[0]) < 0.01
        assert abs(start[1] - 1.0) < 0.01
        assert abs(end[0]) < 0.01
        assert abs(end[1] - 2.0) < 0.01


class TestComputeRadialStrutTransforms:
    def test_four_struts(self):
        """Four evenly spaced struts."""
        struts = compute_radial_strut_transforms(
            parent_center=(0, 0, 0),
            parent_radius=2.0,
            parent_half_z=1.0,
            child_center=(0, 0, 10),
            child_radius=4.0,
            child_half_z=2.0,
            strut_count=4,
            strut_radius=0.1,
            start_angle_deg=0,
        )
        
        assert len(struts) == 4
        
        # Check compass angles
        assert struts[0]["compass_angle_deg"] == 0
        assert struts[1]["compass_angle_deg"] == 90
        assert struts[2]["compass_angle_deg"] == 180
        assert struts[3]["compass_angle_deg"] == 270
        
        # All should have same depth
        depths = [s["depth"] for s in struts]
        assert all(abs(d - depths[0]) < 0.01 for d in depths)


class TestIsConnectorPart:
    def test_strut_keywords(self):
        assert is_connector_part("support_strut_1", "dish.mount") is True
        assert is_connector_part("brace_arm", "hub.connector") is True
        assert is_connector_part("leg_01", "body.leg_socket") is True
        assert is_connector_part("spoke", "wheel.hub") is True

    def test_non_connector_parts(self):
        assert is_connector_part("body", "root") is False
        assert is_connector_part("dish", "pillar.top") is False
        assert is_connector_part("base_plate", "ground") is False


class TestResolveConnectorFromOffset:
    def test_diagonal_offset(self):
        """Connector with diagonal offset should get proper transform."""
        result = resolve_connector_from_offset(
            parent_center=(0, 0, 5),
            parent_shape={"primitive": "cylinder", "radius": 2.0, "depth": 4.0},
            local_offset=(6, 0, -8),
            connector_depth=10.0,
        )
        
        assert "location" in result
        assert "depth" in result
        assert "rotation_euler_rad" in result
        
        # Depth should match
        assert result["depth"] == 10.0

    def test_vertical_offset(self):
        """Purely vertical connector."""
        result = resolve_connector_from_offset(
            parent_center=(0, 0, 0),
            parent_shape={"primitive": "cylinder", "radius": 1.0, "depth": 2.0},
            local_offset=(0, 0, 5),
            connector_depth=4.0,
        )
        
        # Should be vertical, minimal rotation
        euler = result["rotation_euler_rad"]
        assert all(abs(e) < 0.1 for e in euler)
