"""Phase 3 Tests — Shadow Transform System Validation.

Tests for the shadow world-transform pipeline that runs in parallel
with the legacy executor for comparison.

Key tests:
1. Matrix-based rotation comparison (avoids Euler ambiguity)
2. Transform comparison with hierarchy metadata
3. Socket closure tests
4. Local transform validation
"""

import math
import pytest
from typing import List, Dict, Optional

from .transforms import (
    LocalTransform,
    WorldMatrix,
    NodeTransformState,
    compare_positions,
    compare_rotations_matrix,
    compare_world_matrices,
    validate_local_transform,
    _mat4_from_trs,
)
from .stages.stage4_resolver import (
    TransformComparison,
    SocketClosureResult,
    verify_socket_closure,
    log_transform_comparison,
)


# ---------------------------------------------------------------------------
# Matrix-Based Rotation Comparison Tests
# ---------------------------------------------------------------------------

class TestMatrixRotationComparison:
    """Test matrix-based rotation comparison (avoids Euler ambiguity)."""
    
    def test_identical_rotations_match(self):
        """Identical rotations should match."""
        rot = [0.5, 0.3, 0.1]
        delta, match = compare_rotations_matrix(rot, rot, tolerance_deg=0.1)
        assert match
        assert delta < 0.01
    
    def test_zero_rotations_match(self):
        """Zero rotations should match."""
        rot_a = [0.0, 0.0, 0.0]
        rot_b = [0.0, 0.0, 0.0]
        delta, match = compare_rotations_matrix(rot_a, rot_b, tolerance_deg=0.1)
        assert match
        assert delta < 0.01
    
    def test_equivalent_euler_representations_match(self):
        """Different Euler representations of same rotation should match.
        
        [0, 0, 0] and [2π, 0, 0] represent the same orientation.
        """
        rot_a = [0.0, 0.0, 0.0]
        rot_b = [2 * math.pi, 0.0, 0.0]  # 360° around X
        delta, match = compare_rotations_matrix(rot_a, rot_b, tolerance_deg=1.0)
        assert match, f"Expected match, got delta={delta}°"
    
    def test_small_rotation_difference_within_tolerance(self):
        """Small rotation difference within tolerance should match."""
        rot_a = [0.0, 0.0, 0.0]
        rot_b = [math.radians(0.05), 0.0, 0.0]  # 0.05° difference
        delta, match = compare_rotations_matrix(rot_a, rot_b, tolerance_deg=0.1)
        assert match
        assert delta < 0.1
    
    def test_large_rotation_difference_fails(self):
        """Large rotation difference should not match."""
        rot_a = [0.0, 0.0, 0.0]
        rot_b = [math.radians(45), 0.0, 0.0]  # 45° difference
        delta, match = compare_rotations_matrix(rot_a, rot_b, tolerance_deg=0.1)
        assert not match
        assert delta > 40  # Should be ~45°
    
    def test_90_degree_rotation_detected(self):
        """90° rotation should be detected as different from identity."""
        rot_a = [0.0, 0.0, 0.0]
        rot_b = [math.pi / 2, 0.0, 0.0]  # 90° around X
        delta, match = compare_rotations_matrix(rot_a, rot_b, tolerance_deg=0.1)
        assert not match
        assert abs(delta - 90) < 1  # Should be ~90°
    
    def test_combined_rotation_comparison(self):
        """Combined XYZ rotation comparison."""
        rot_a = [math.radians(30), math.radians(45), math.radians(60)]
        rot_b = [math.radians(30.05), math.radians(45.05), math.radians(60.05)]
        delta, match = compare_rotations_matrix(rot_a, rot_b, tolerance_deg=0.5)
        assert match, f"Expected match for small difference, got delta={delta}°"


class TestPositionComparison:
    """Test position comparison."""
    
    def test_identical_positions_match(self):
        """Identical positions should match."""
        pos = [1.0, 2.0, 3.0]
        delta, match = compare_positions(pos, pos, tolerance=1e-5)
        assert match
        assert delta < 1e-6
    
    def test_small_difference_within_tolerance(self):
        """Small position difference within tolerance should match."""
        pos_a = [1.0, 2.0, 3.0]
        pos_b = [1.000001, 2.000001, 3.000001]
        delta, match = compare_positions(pos_a, pos_b, tolerance=1e-4)
        assert match
    
    def test_large_difference_fails(self):
        """Large position difference should not match."""
        pos_a = [0.0, 0.0, 0.0]
        pos_b = [1.0, 0.0, 0.0]
        delta, match = compare_positions(pos_a, pos_b, tolerance=1e-5)
        assert not match
        assert abs(delta - 1.0) < 0.001


class TestWorldMatrixComparison:
    """Test full world matrix comparison."""
    
    def test_identical_matrices_match(self):
        """Identical world matrices should match."""
        local = LocalTransform(
            position=[1.0, 2.0, 3.0],
            rotation=[0.5, 0.3, 0.1],
        )
        mat_a = WorldMatrix.from_local(local)
        mat_b = WorldMatrix.from_local(local)
        
        pos_delta, rot_delta, match = compare_world_matrices(mat_a, mat_b)
        assert match
        assert pos_delta < 1e-6
        assert rot_delta < 0.01
    
    def test_different_positions_detected(self):
        """Different positions should be detected."""
        mat_a = WorldMatrix.from_local(LocalTransform(position=[0, 0, 0]))
        mat_b = WorldMatrix.from_local(LocalTransform(position=[1, 0, 0]))
        
        pos_delta, rot_delta, match = compare_world_matrices(mat_a, mat_b)
        assert not match
        assert pos_delta > 0.9
    
    def test_different_rotations_detected(self):
        """Different rotations should be detected."""
        mat_a = WorldMatrix.from_local(LocalTransform(rotation=[0, 0, 0]))
        mat_b = WorldMatrix.from_local(LocalTransform(rotation=[math.pi/2, 0, 0]))
        
        pos_delta, rot_delta, match = compare_world_matrices(mat_a, mat_b)
        assert not match
        assert rot_delta > 80  # ~90°


# ---------------------------------------------------------------------------
# Transform Comparison Tests
# ---------------------------------------------------------------------------

class TestTransformComparison:
    """Test TransformComparison dataclass."""
    
    def test_compute_deltas_match(self):
        """Matching transforms should have MATCH status."""
        comp = TransformComparison(
            node_id="test_node",
            node_label="test",
            depth=1,
            legacy_position=[1.0, 2.0, 3.0],
            legacy_rotation=[0.1, 0.2, 0.3],
            new_position=[1.0, 2.0, 3.0],
            new_rotation=[0.1, 0.2, 0.3],
        )
        comp.compute_deltas()
        
        assert comp.status == "MATCH"
        assert comp.position_delta < 1e-5
        assert comp.rotation_delta < 0.1
    
    def test_compute_deltas_differ(self):
        """Different transforms should have DIFFER status."""
        comp = TransformComparison(
            node_id="test_node",
            node_label="test",
            depth=1,
            legacy_position=[0.0, 0.0, 0.0],
            legacy_rotation=[0.0, 0.0, 0.0],
            new_position=[1.0, 0.0, 0.0],
            new_rotation=[0.0, 0.0, 0.0],
        )
        comp.compute_deltas()
        
        assert comp.status == "DIFFER"
        assert comp.position_delta > 0.9
    
    def test_hierarchy_metadata_preserved(self):
        """Hierarchy metadata should be preserved in comparison."""
        comp = TransformComparison(
            node_id="child_node",
            node_label="child",
            depth=3,
            parent_id="parent_node",
            socket_type="TOP_CENTER",
            local_position=[0.0, 0.0, 0.5],
            local_rotation=[0.0, 0.0, 0.0],
        )
        
        assert comp.parent_id == "parent_node"
        assert comp.socket_type == "TOP_CENTER"
        assert comp.depth == 3
        assert comp.local_position == [0.0, 0.0, 0.5]
    
    def test_to_dict_includes_all_fields(self):
        """to_dict should include all fields."""
        comp = TransformComparison(
            node_id="test",
            node_label="test_label",
            depth=2,
            parent_id="parent",
            socket_type="CORNER",
            local_position=[1, 2, 3],
            local_rotation=[0.1, 0.2, 0.3],
            legacy_position=[1, 2, 3],
            legacy_rotation=[0.1, 0.2, 0.3],
            new_position=[1, 2, 3],
            new_rotation=[0.1, 0.2, 0.3],
        )
        comp.compute_deltas()
        
        d = comp.to_dict()
        assert "node_id" in d
        assert "parent_id" in d
        assert "socket_type" in d
        assert "local_position" in d
        assert "position_delta" in d
        assert "rotation_delta" in d
        assert "status" in d


class TestLogTransformComparison:
    """Test log_transform_comparison formatting."""
    
    def test_generates_table_format(self):
        """Should generate table format output."""
        comparisons = [
            TransformComparison(
                node_id="node1",
                node_label="base",
                depth=1,
                parent_id="root",
                socket_type="ROOT",
                legacy_position=[0, 0, 0],
                legacy_rotation=[0, 0, 0],
                new_position=[0, 0, 0],
                new_rotation=[0, 0, 0],
            ),
            TransformComparison(
                node_id="node2",
                node_label="turret",
                depth=2,
                parent_id="node1",
                socket_type="TOP_CENTER",
                legacy_position=[0, 0, 1],
                legacy_rotation=[0, 0, 0],
                new_position=[0, 0, 1],
                new_rotation=[0, 0, 0],
            ),
        ]
        for c in comparisons:
            c.compute_deltas()
        
        output = log_transform_comparison(comparisons)
        
        assert "TRANSFORM COMPARISON" in output
        assert "Node" in output
        assert "Parent" in output
        assert "Depth" in output
        assert "MATCH" in output
        assert "SUMMARY" in output
    
    def test_shows_detailed_differences(self):
        """Should show detailed breakdown for DIFFER nodes."""
        comparisons = [
            TransformComparison(
                node_id="node1",
                node_label="problem_node",
                depth=1,
                legacy_position=[0, 0, 0],
                legacy_rotation=[0, 0, 0],
                new_position=[1, 0, 0],  # Different!
                new_rotation=[0, 0, 0],
            ),
        ]
        comparisons[0].compute_deltas()
        
        output = log_transform_comparison(comparisons)
        
        assert "DIFFER" in output
        assert "DETAILED DIFFERENCES" in output
        assert "problem_node" in output


# ---------------------------------------------------------------------------
# Local Transform Validation Tests
# ---------------------------------------------------------------------------

class TestLocalTransformValidation:
    """Test local transform validation before hierarchy insertion."""
    
    def test_valid_transform_passes(self):
        """Valid transform should pass validation."""
        transform = LocalTransform(
            position=[1.0, 2.0, 3.0],
            rotation=[0.1, 0.2, 0.3],
            scale=[1.0, 1.0, 1.0],
        )
        errors = validate_local_transform(transform, "test")
        assert len(errors) == 0
    
    def test_non_finite_position_fails(self):
        """Non-finite position should fail validation."""
        transform = LocalTransform(
            position=[float('inf'), 0.0, 0.0],
            rotation=[0.0, 0.0, 0.0],
            scale=[1.0, 1.0, 1.0],
        )
        errors = validate_local_transform(transform, "test")
        assert len(errors) > 0
        assert "non-finite" in errors[0].lower()
    
    def test_nan_rotation_fails(self):
        """NaN rotation should fail validation."""
        transform = LocalTransform(
            position=[0.0, 0.0, 0.0],
            rotation=[float('nan'), 0.0, 0.0],
            scale=[1.0, 1.0, 1.0],
        )
        errors = validate_local_transform(transform, "test")
        assert len(errors) > 0
    
    def test_non_unit_scale_fails(self):
        """Non-unit scale should fail validation."""
        transform = LocalTransform(
            position=[0.0, 0.0, 0.0],
            rotation=[0.0, 0.0, 0.0],
            scale=[2.0, 1.0, 1.0],  # Non-unit!
        )
        errors = validate_local_transform(transform, "test")
        assert len(errors) > 0
        assert "scale" in errors[0].lower()
    
    def test_context_included_in_error(self):
        """Context should be included in error message."""
        transform = LocalTransform(
            position=[float('inf'), 0.0, 0.0],
        )
        errors = validate_local_transform(transform, "my_node Stage 4")
        assert len(errors) > 0
        assert "my_node" in errors[0]


# ---------------------------------------------------------------------------
# Socket Closure Tests
# ---------------------------------------------------------------------------

class TestSocketClosure:
    """Test socket closure verification."""
    
    def _make_node_with_transform(
        self,
        node_id: str,
        label: str,
        local_pos: List[float],
        local_rot: List[float],
        parent_world: Optional[WorldMatrix] = None,
    ):
        """Helper to create a mock node with transform state."""
        class MockNode:
            pass
        
        node = MockNode()
        node.node_id = node_id
        node.label = label
        node.transform_state = NodeTransformState()
        node.transform_state.set_local_transform(LocalTransform(
            position=local_pos,
            rotation=local_rot,
        ))
        
        # Compute world matrix
        parent_rev = parent_world.position[0] if parent_world else -1  # Dummy revision
        node.transform_state.compute_world(parent_world, int(parent_rev))
        
        return node
    
    def test_socket_closure_passes_for_correct_attachment(self):
        """Socket closure should pass for correctly attached parts."""
        # Parent at origin
        parent = self._make_node_with_transform(
            "parent", "base",
            local_pos=[0, 0, 0],
            local_rot=[0, 0, 0],
        )
        
        # Child on top of parent (socket at Z=0.5 on parent, Z=-0.5 on child)
        child = self._make_node_with_transform(
            "child", "turret",
            local_pos=[0, 0, 1.0],  # Offset to put child's bottom at parent's top
            local_rot=[0, 0, 0],
            parent_world=parent.transform_state.world_matrix,
        )
        
        # Parent socket at top (Z=0.5), child socket at bottom (Z=-0.5)
        result = verify_socket_closure(
            parent_node=parent,
            child_node=child,
            parent_socket_local=[0, 0, 0.5],
            child_socket_local=[0, 0, -0.5],
            tolerance=1e-4,
        )
        
        assert result.is_closed, f"Expected closed, got distance={result.socket_distance}"
    
    def test_socket_closure_fails_for_misaligned_attachment(self):
        """Socket closure should fail for misaligned parts."""
        parent = self._make_node_with_transform(
            "parent", "base",
            local_pos=[0, 0, 0],
            local_rot=[0, 0, 0],
        )
        
        # Child offset incorrectly
        child = self._make_node_with_transform(
            "child", "turret",
            local_pos=[0, 0, 2.0],  # Too far!
            local_rot=[0, 0, 0],
            parent_world=parent.transform_state.world_matrix,
        )
        
        result = verify_socket_closure(
            parent_node=parent,
            child_node=child,
            parent_socket_local=[0, 0, 0.5],
            child_socket_local=[0, 0, -0.5],
            tolerance=1e-4,
        )
        
        assert not result.is_closed
        assert result.socket_distance > 0.5
    
    def test_socket_closure_with_rotated_parent(self):
        """Socket closure should work with rotated parent."""
        # Parent rotated 90° around Y
        parent = self._make_node_with_transform(
            "parent", "base",
            local_pos=[0, 0, 0],
            local_rot=[0, math.pi/2, 0],  # 90° Y rotation
        )
        
        # Child attached to parent's "top" (which is now +X due to rotation)
        # After 90° Y rotation: local +Z becomes world +X
        child = self._make_node_with_transform(
            "child", "turret",
            local_pos=[0, 0, 1.0],  # Local offset along Z
            local_rot=[0, 0, 0],
            parent_world=parent.transform_state.world_matrix,
        )
        
        # Parent socket at local Z=0.5 (world X=0.5 after rotation)
        # Child socket at local Z=-0.5
        result = verify_socket_closure(
            parent_node=parent,
            child_node=child,
            parent_socket_local=[0, 0, 0.5],
            child_socket_local=[0, 0, -0.5],
            tolerance=1e-4,
        )
        
        assert result.is_closed, f"Expected closed with rotated parent, got distance={result.socket_distance}"
    
    def test_socket_closure_result_contains_metadata(self):
        """SocketClosureResult should contain all metadata."""
        parent = self._make_node_with_transform(
            "parent_id", "parent_label",
            local_pos=[0, 0, 0],
            local_rot=[0, 0, 0],
        )
        child = self._make_node_with_transform(
            "child_id", "child_label",
            local_pos=[0, 0, 1.0],
            local_rot=[0, 0, 0],
            parent_world=parent.transform_state.world_matrix,
        )
        
        result = verify_socket_closure(
            parent_node=parent,
            child_node=child,
            parent_socket_local=[0, 0, 0.5],
            child_socket_local=[0, 0, -0.5],
        )
        
        assert result.parent_id == "parent_id"
        assert result.child_id == "child_id"
        assert result.parent_label == "parent_label"
        assert result.child_label == "child_label"
        assert len(result.parent_socket_world) == 3
        assert len(result.child_socket_world) == 3


# ---------------------------------------------------------------------------
# Integration: Shadow System Matches Legacy
# ---------------------------------------------------------------------------

class TestShadowSystemIntegration:
    """Test that shadow transform system can match legacy results."""
    
    def test_simple_hierarchy_matches(self):
        """Simple 2-level hierarchy should produce matching results."""
        # Simulate what Stage 4 produces
        root_local = LocalTransform.identity()
        child_local = LocalTransform(position=[0, 0, 1.0])
        
        # New system computation
        root_state = NodeTransformState()
        root_state.set_local_transform(root_local)
        root_world = root_state.compute_world(None, -1)
        
        child_state = NodeTransformState()
        child_state.set_local_transform(child_local)
        child_world = child_state.compute_world(root_world, root_state.revision)
        
        # Expected legacy result (simple addition for no rotation)
        legacy_pos = [0, 0, 1.0]
        legacy_rot = [0, 0, 0]
        
        # Compare
        pos_delta, pos_match = compare_positions(legacy_pos, child_world.position)
        rot_delta, rot_match = compare_rotations_matrix(legacy_rot, child_world.rotation)
        
        assert pos_match, f"Position mismatch: {legacy_pos} vs {child_world.position}"
        assert rot_match, f"Rotation mismatch: {legacy_rot} vs {child_world.rotation}"
    
    def test_rotated_hierarchy_matches(self):
        """Hierarchy with rotation should produce correct results."""
        # Parent rotated 90° around Z
        parent_local = LocalTransform(rotation=[0, 0, math.pi/2])
        # Child offset in local X (becomes world Y after parent rotation)
        child_local = LocalTransform(position=[1.0, 0, 0])
        
        # New system computation
        parent_state = NodeTransformState()
        parent_state.set_local_transform(parent_local)
        parent_world = parent_state.compute_world(None, -1)
        
        child_state = NodeTransformState()
        child_state.set_local_transform(child_local)
        child_world = child_state.compute_world(parent_world, parent_state.revision)
        
        # Expected: child at world (0, 1, 0) due to 90° Z rotation
        # Local X [1,0,0] rotated 90° around Z becomes [0,1,0]
        expected_pos = [0, 1, 0]
        
        pos_delta, pos_match = compare_positions(expected_pos, child_world.position, tolerance=1e-4)
        assert pos_match, f"Position mismatch: expected {expected_pos}, got {child_world.position}"
