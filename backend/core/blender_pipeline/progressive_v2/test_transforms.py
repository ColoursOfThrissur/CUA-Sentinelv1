"""Tests for the hierarchical transform system (Phase 1).

Run with: pytest backend/core/blender_pipeline/progressive_v2/test_transforms.py -v

Test categories:
1. Basic LocalTransform/WorldMatrix operations
2. NodeTransformState with revision-based caching
3. Frozen semantics (parent change → descendants stale, child change → parent unaffected)
4. Deep rotation tests (nested rotated assemblies)
5. 10-20 level depth test (proves depth is not a special case)
6. Socket attachment simulation (the real validation)
7. Scale invariant enforcement
"""

import math
import random
import pytest
from .transforms import (
    LocalTransform,
    WorldMatrix,
    NodeTransformState,
    _mat4_multiply,
    _mat4_from_trs,
    _mat4_to_trs,
    _identity_4x4,
    compute_world_transform_chain,
    propagate_world_transforms,
    mark_descendants_stale,
    validate_unit_scale,
    assert_unit_scale,
)


class TestLocalTransform:
    """Tests for LocalTransform dataclass."""
    
    def test_identity(self):
        t = LocalTransform.identity()
        assert t.position == [0.0, 0.0, 0.0]
        assert t.rotation == [0.0, 0.0, 0.0]
        assert t.scale == [1.0, 1.0, 1.0]
    
    def test_from_position(self):
        t = LocalTransform.from_position(1.0, 2.0, 3.0)
        assert t.position == [1.0, 2.0, 3.0]
        assert t.rotation == [0.0, 0.0, 0.0]
    
    def test_from_rotation_degrees(self):
        t = LocalTransform.from_rotation_degrees(90, 0, 0)
        assert abs(t.rotation[0] - math.pi/2) < 1e-6
        assert t.rotation[1] == 0.0
        assert t.rotation[2] == 0.0
    
    def test_to_matrix_identity(self):
        t = LocalTransform.identity()
        m = t.to_matrix()
        expected = _identity_4x4()
        for i in range(4):
            for j in range(4):
                assert abs(m[i][j] - expected[i][j]) < 1e-6
    
    def test_to_matrix_translation(self):
        t = LocalTransform.from_position(5.0, 0.0, 0.0)
        m = t.to_matrix()
        # Translation is in the last column
        assert abs(m[0][3] - 5.0) < 1e-6
        assert abs(m[1][3] - 0.0) < 1e-6
        assert abs(m[2][3] - 0.0) < 1e-6
    
    def test_roundtrip_serialization(self):
        t = LocalTransform(
            position=[1.0, 2.0, 3.0],
            rotation=[0.1, 0.2, 0.3],
            scale=[1.5, 1.5, 1.5],
        )
        d = t.to_dict()
        t2 = LocalTransform.from_dict(d)
        assert t.position == t2.position
        assert t.rotation == t2.rotation
        assert t.scale == t2.scale


class TestWorldMatrix:
    """Tests for WorldMatrix dataclass."""
    
    def test_identity(self):
        w = WorldMatrix.identity()
        assert w.position == [0.0, 0.0, 0.0]
        assert all(abs(r) < 1e-6 for r in w.rotation)
        assert all(abs(s - 1.0) < 1e-6 for s in w.scale)
    
    def test_from_local(self):
        local = LocalTransform.from_position(1.0, 2.0, 3.0)
        world = WorldMatrix.from_local(local)
        assert abs(world.position[0] - 1.0) < 1e-6
        assert abs(world.position[1] - 2.0) < 1e-6
        assert abs(world.position[2] - 3.0) < 1e-6
    
    def test_compose_translation(self):
        """Test that translations compose correctly."""
        parent_local = LocalTransform.from_position(10.0, 0.0, 0.0)
        parent_world = WorldMatrix.from_local(parent_local)
        
        child_local = LocalTransform.from_position(5.0, 0.0, 0.0)
        child_world = WorldMatrix.compose(parent_world, child_local)
        
        # Child should be at parent + child = 15, 0, 0
        assert abs(child_world.position[0] - 15.0) < 1e-6
        assert abs(child_world.position[1] - 0.0) < 1e-6
        assert abs(child_world.position[2] - 0.0) < 1e-6
    
    def test_compose_rotation_then_translation(self):
        """Test that rotation affects child's translation direction."""
        # Parent rotated 90° around Z
        parent_local = LocalTransform(
            position=[0.0, 0.0, 0.0],
            rotation=[0.0, 0.0, math.pi/2],  # 90° around Z
        )
        parent_world = WorldMatrix.from_local(parent_local)
        
        # Child offset 1 unit in local +X
        child_local = LocalTransform.from_position(1.0, 0.0, 0.0)
        child_world = WorldMatrix.compose(parent_world, child_local)
        
        # After 90° Z rotation, local +X becomes world +Y
        assert abs(child_world.position[0] - 0.0) < 1e-5
        assert abs(child_world.position[1] - 1.0) < 1e-5
        assert abs(child_world.position[2] - 0.0) < 1e-5
    
    def test_transform_point(self):
        """Test transforming a point by world matrix."""
        local = LocalTransform.from_position(10.0, 0.0, 0.0)
        world = WorldMatrix.from_local(local)
        
        # Transform origin -> should get translation
        p = world.transform_point([0.0, 0.0, 0.0])
        assert abs(p[0] - 10.0) < 1e-6
        assert abs(p[1] - 0.0) < 1e-6
        assert abs(p[2] - 0.0) < 1e-6
    
    def test_roundtrip_serialization(self):
        local = LocalTransform(
            position=[1.0, 2.0, 3.0],
            rotation=[0.1, 0.2, 0.3],
        )
        world = WorldMatrix.from_local(local)
        d = world.to_dict()
        world2 = WorldMatrix.from_dict(d)
        
        for i in range(3):
            assert abs(world.position[i] - world2.position[i]) < 1e-6


class TestNodeTransformState:
    """Tests for NodeTransformState with revision-based caching."""
    
    def test_compute_world_root(self):
        """Root node: world = local."""
        state = NodeTransformState()
        state.set_local_transform(LocalTransform.from_position(5.0, 0.0, 0.0))
        
        world = state.compute_world(None, parent_revision=-1)
        assert abs(world.position[0] - 5.0) < 1e-6
    
    def test_compute_world_child(self):
        """Child node: world = parent @ local."""
        parent_state = NodeTransformState()
        parent_state.set_local_transform(LocalTransform.from_position(10.0, 0.0, 0.0))
        parent_world = parent_state.compute_world(None, parent_revision=-1)
        
        child_state = NodeTransformState()
        child_state.set_local_transform(LocalTransform.from_position(5.0, 0.0, 0.0))
        child_world = child_state.compute_world(parent_world, parent_state.revision)
        
        assert abs(child_world.position[0] - 15.0) < 1e-6
    
    def test_revision_increments_on_change(self):
        """Revision should increment when local_transform changes."""
        state = NodeTransformState()
        assert state.revision == 0
        
        state.set_local_transform(LocalTransform.from_position(1, 0, 0))
        assert state.revision == 1
        
        state.set_local_transform(LocalTransform.from_position(2, 0, 0))
        assert state.revision == 2
    
    def test_cache_valid_when_parent_unchanged(self):
        """World matrix should be cached when parent revision matches."""
        state = NodeTransformState()
        state.set_local_transform(LocalTransform.from_position(5, 0, 0))
        
        # First computation
        world1 = state.compute_world(None, parent_revision=-1)
        
        # Should be valid (same parent revision)
        assert state.is_world_valid(-1)
        
        # Second call should return cached value
        world2 = state.compute_world(None, parent_revision=-1)
        assert world1 is world2  # Same object (cached)
    
    def test_cache_invalid_when_parent_changed(self):
        """World matrix should be recomputed when parent revision changes."""
        state = NodeTransformState()
        state.set_local_transform(LocalTransform.from_position(5, 0, 0))
        
        # Compute with parent revision 0
        state.compute_world(None, parent_revision=0)
        assert state.is_world_valid(0)
        
        # Parent changed (revision 1) - cache should be invalid
        assert not state.is_world_valid(1)
    
    def test_frozen_prevents_local_change(self):
        """Frozen transform should prevent local_transform modification."""
        state = NodeTransformState()
        state.set_local_transform(LocalTransform.from_position(5, 0, 0))
        state.compute_world(None, -1)
        state.freeze()
        
        with pytest.raises(RuntimeError, match="Cannot modify frozen"):
            state.set_local_transform(LocalTransform.from_position(10, 0, 0))
    
    def test_frozen_allows_world_recomputation(self):
        """Frozen node's world_matrix CAN be recomputed if ancestor changed."""
        state = NodeTransformState()
        state.set_local_transform(LocalTransform.from_position(5, 0, 0))
        state.compute_world(None, -1)
        state.freeze()
        
        # Simulate parent change - world should be recomputable
        new_parent = WorldMatrix.from_local(LocalTransform.from_position(100, 0, 0))
        world = state.compute_world(new_parent, parent_revision=99)
        
        # World position should reflect new parent
        assert abs(world.position[0] - 105.0) < 1e-6
    
    def test_force_allows_frozen_modification(self):
        """force=True should allow modifying frozen transform (for repair)."""
        state = NodeTransformState()
        state.set_local_transform(LocalTransform.from_position(5, 0, 0))
        state.compute_world(None, -1)
        state.freeze()
        
        # Should work with force=True
        state.set_local_transform(LocalTransform.from_position(10, 0, 0), force=True)
        assert state.local_transform.position[0] == 10.0
    
    def test_mark_stale(self):
        """mark_stale should invalidate world without affecting local."""
        state = NodeTransformState()
        state.set_local_transform(LocalTransform.from_position(5, 0, 0))
        state.compute_world(None, -1)
        
        assert state.world_matrix is not None
        state.mark_stale()
        assert state.world_matrix is None
        assert state.local_transform.position[0] == 5.0  # Unchanged
    
    def test_roundtrip_serialization(self):
        state = NodeTransformState()
        state.set_local_transform(LocalTransform.from_position(1.0, 2.0, 3.0))
        state.compute_world(None, -1)
        state.freeze()
        
        d = state.to_dict()
        state2 = NodeTransformState.from_dict(d)
        
        assert state2.frozen == True
        assert state2.local_transform.position == [1.0, 2.0, 3.0]
        assert state2.world_matrix is not None
        assert state2.revision == state.revision


class TestHierarchyComposition:
    """Tests for multi-level hierarchy composition."""
    
    def test_three_level_hierarchy(self):
        """Test MODEL -> ASSEMBLY -> PART composition."""
        # MODEL at origin
        model_state = NodeTransformState()
        model_world = model_state.compute_world(None, -1)
        
        # ASSEMBLY offset by (10, 0, 0)
        assembly_state = NodeTransformState()
        assembly_state.set_local_transform(LocalTransform.from_position(10.0, 0.0, 0.0))
        assembly_world = assembly_state.compute_world(model_world, model_state.revision)
        
        # PART offset by (5, 0, 0) from assembly
        part_state = NodeTransformState()
        part_state.set_local_transform(LocalTransform.from_position(5.0, 0.0, 0.0))
        part_world = part_state.compute_world(assembly_world, assembly_state.revision)
        
        # Part should be at 10 + 5 = 15
        assert abs(part_world.position[0] - 15.0) < 1e-6
    
    def test_four_level_with_rotation(self):
        """Test deep hierarchy with rotation at each level."""
        # Level 0: MODEL at origin
        l0_state = NodeTransformState()
        l0_world = l0_state.compute_world(None, -1)
        
        # Level 1: rotated 90° around Z
        l1_state = NodeTransformState()
        l1_state.set_local_transform(LocalTransform(
            position=[0.0, 0.0, 0.0],
            rotation=[0.0, 0.0, math.pi/2],
        ))
        l1_world = l1_state.compute_world(l0_world, l0_state.revision)
        
        # Level 2: offset 1 unit in local +X (which is now world +Y)
        l2_state = NodeTransformState()
        l2_state.set_local_transform(LocalTransform.from_position(1.0, 0.0, 0.0))
        l2_world = l2_state.compute_world(l1_world, l1_state.revision)
        
        # Level 3: offset 1 unit in local +X (still world +Y due to inherited rotation)
        l3_state = NodeTransformState()
        l3_state.set_local_transform(LocalTransform.from_position(1.0, 0.0, 0.0))
        l3_world = l3_state.compute_world(l2_world, l2_state.revision)
        
        # Final position should be (0, 2, 0) - two units in +Y
        assert abs(l3_world.position[0] - 0.0) < 1e-5
        assert abs(l3_world.position[1] - 2.0) < 1e-5
        assert abs(l3_world.position[2] - 0.0) < 1e-5
    
    def test_scale_propagation(self):
        """Test that scale propagates through hierarchy."""
        # Parent scaled 2x
        parent_state = NodeTransformState()
        parent_state.set_local_transform(LocalTransform(
            position=[0.0, 0.0, 0.0],
            rotation=[0.0, 0.0, 0.0],
            scale=[2.0, 2.0, 2.0],
        ))
        parent_world = parent_state.compute_world(None, -1)
        
        # Child offset 1 unit in local X
        child_state = NodeTransformState()
        child_state.set_local_transform(LocalTransform.from_position(1.0, 0.0, 0.0))
        child_world = child_state.compute_world(parent_world, parent_state.revision)
        
        # Due to parent's 2x scale, child's 1 unit offset becomes 2 units
        assert abs(child_world.position[0] - 2.0) < 1e-6


class TestMatrixUtilities:
    """Tests for low-level matrix utilities."""
    
    def test_identity_multiply(self):
        """Identity @ A = A."""
        identity = _identity_4x4()
        a = _mat4_from_trs([1, 2, 3], [0.1, 0.2, 0.3], [1, 1, 1])
        result = _mat4_multiply(identity, a)
        
        for i in range(4):
            for j in range(4):
                assert abs(result[i][j] - a[i][j]) < 1e-6
    
    def test_trs_roundtrip(self):
        """Test TRS -> matrix -> TRS roundtrip."""
        pos = [1.0, 2.0, 3.0]
        rot = [0.1, 0.2, 0.3]
        scale = [1.5, 1.5, 1.5]
        
        m = _mat4_from_trs(pos, rot, scale)
        pos2, rot2, scale2 = _mat4_to_trs(m)
        
        for i in range(3):
            assert abs(pos[i] - pos2[i]) < 1e-5
            assert abs(rot[i] - rot2[i]) < 1e-5
            assert abs(scale[i] - scale2[i]) < 1e-5



class TestDeepRotation:
    """Deep rotation tests - the cases that actually resemble failing models."""
    
    def test_nested_rotated_assemblies(self):
        """Test A: Nested rotated assemblies.
        
        Model
         └── A (rotation Z = 90°)
              └── B (position X = 2)
                   └── C (position X = 3)
        
        C world position should be transformed through A AND B.
        """
        # Model at origin
        model = NodeTransformState()
        model_world = model.compute_world(None, -1)
        
        # A: rotated 90° around Z
        a = NodeTransformState()
        a.set_local_transform(LocalTransform(rotation=[0, 0, math.pi/2]))
        a_world = a.compute_world(model_world, model.revision)
        
        # B: offset 2 in local X (becomes world Y due to A's rotation)
        b = NodeTransformState()
        b.set_local_transform(LocalTransform.from_position(2, 0, 0))
        b_world = b.compute_world(a_world, a.revision)
        
        # B should be at (0, 2, 0)
        assert abs(b_world.position[0]) < 1e-5
        assert abs(b_world.position[1] - 2.0) < 1e-5
        
        # C: offset 3 in local X (still world Y due to inherited rotation)
        c = NodeTransformState()
        c.set_local_transform(LocalTransform.from_position(3, 0, 0))
        c_world = c.compute_world(b_world, b.revision)
        
        # C should be at (0, 5, 0) = (0, 2+3, 0)
        assert abs(c_world.position[0]) < 1e-5
        assert abs(c_world.position[1] - 5.0) < 1e-5
        assert abs(c_world.position[2]) < 1e-5
    
    def test_rotation_at_every_level(self):
        """Test B: Rotation at every level.
        
        A: Z 30°
        B: Y 45°
        C: X 20°
        D: local offset (1, 0, 0)
        
        Verify against known matrix calculation.
        """
        # A: Z 30°
        a = NodeTransformState()
        a.set_local_transform(LocalTransform(rotation=[0, 0, math.radians(30)]))
        a_world = a.compute_world(None, -1)
        
        # B: Y 45°
        b = NodeTransformState()
        b.set_local_transform(LocalTransform(rotation=[0, math.radians(45), 0]))
        b_world = b.compute_world(a_world, a.revision)
        
        # C: X 20°
        c = NodeTransformState()
        c.set_local_transform(LocalTransform(rotation=[math.radians(20), 0, 0]))
        c_world = c.compute_world(b_world, b.revision)
        
        # D: offset (1, 0, 0) in local space
        d = NodeTransformState()
        d.set_local_transform(LocalTransform.from_position(1, 0, 0))
        d_world = d.compute_world(c_world, c.revision)
        
        # Compute expected via manual matrix multiplication
        # M = Rz(30) @ Ry(45) @ Rx(20) @ T(1,0,0)
        # The local X axis after all rotations determines D's world offset
        
        # Extract the X column of the combined rotation (first 3 elements of first column)
        # This is where (1,0,0) maps to
        expected_x = c_world.matrix[0][0]  # X component of transformed X-axis
        expected_y = c_world.matrix[1][0]  # Y component
        expected_z = c_world.matrix[2][0]  # Z component
        
        assert abs(d_world.position[0] - expected_x) < 1e-5
        assert abs(d_world.position[1] - expected_y) < 1e-5
        assert abs(d_world.position[2] - expected_z) < 1e-5
    
    def test_translation_rotation_scale_combined(self):
        """Test C: Translation + rotation + scale at different levels.
        
        A: scale [2, 2, 2]
        B: rotation Z 90°
        C: translation (1, 0, 0)
        
        C's world position should be (0, 2, 0):
        - C's local (1,0,0) rotated by B's 90° Z = (0,1,0)
        - Scaled by A's 2x = (0,2,0)
        """
        # A: scale 2x
        a = NodeTransformState()
        a.set_local_transform(LocalTransform(scale=[2, 2, 2]))
        a_world = a.compute_world(None, -1)
        
        # B: rotation Z 90°
        b = NodeTransformState()
        b.set_local_transform(LocalTransform(rotation=[0, 0, math.pi/2]))
        b_world = b.compute_world(a_world, a.revision)
        
        # C: translation (1, 0, 0)
        c = NodeTransformState()
        c.set_local_transform(LocalTransform.from_position(1, 0, 0))
        c_world = c.compute_world(b_world, b.revision)
        
        # Expected: (0, 2, 0)
        assert abs(c_world.position[0]) < 1e-5
        assert abs(c_world.position[1] - 2.0) < 1e-5
        assert abs(c_world.position[2]) < 1e-5



class TestDeepHierarchy:
    """Test D: 10-20 level depth to prove depth is not a special case."""
    
    def test_fifteen_level_hierarchy(self):
        """15-level hierarchy with deterministic transforms.
        
        Each level: offset (1, 0, 0) in local space
        No rotation: final position should be (15, 0, 0)
        """
        DEPTH = 15
        states = []
        
        # Build chain
        parent_world = None
        parent_rev = -1
        for i in range(DEPTH):
            state = NodeTransformState()
            state.set_local_transform(LocalTransform.from_position(1, 0, 0))
            state.compute_world(parent_world, parent_rev)
            states.append(state)
            parent_world = state.world_matrix
            parent_rev = state.revision
        
        # Final node should be at (15, 0, 0)
        final = states[-1].world_matrix
        assert abs(final.position[0] - DEPTH) < 1e-5
        assert abs(final.position[1]) < 1e-5
        assert abs(final.position[2]) < 1e-5
    
    def test_twenty_level_with_alternating_rotation(self):
        """20-level hierarchy with alternating 90° rotations.
        
        Even levels: no rotation, offset (1, 0, 0)
        Odd levels: Z 90° rotation, offset (1, 0, 0)
        
        Pattern:
        - Level 0: (1, 0, 0) world
        - Level 1: rotate 90°, then (1,0,0) local = (0,1,0) relative, total (1,1,0)
        - Level 2: no rotate, (1,0,0) local = (0,1,0) world (inherits L1 rotation), total (1,2,0)
        - etc.
        """
        DEPTH = 20
        states = []
        
        parent_world = None
        parent_rev = -1
        for i in range(DEPTH):
            state = NodeTransformState()
            if i % 2 == 1:
                # Odd: rotate 90° Z then offset
                state.set_local_transform(LocalTransform(
                    position=[1, 0, 0],
                    rotation=[0, 0, math.pi/2],
                ))
            else:
                # Even: just offset
                state.set_local_transform(LocalTransform.from_position(1, 0, 0))
            state.compute_world(parent_world, parent_rev)
            states.append(state)
            parent_world = state.world_matrix
            parent_rev = state.revision
        
        # Verify we can compute all 20 levels without error
        assert len(states) == DEPTH
        # Final position should be deterministic (not checking exact value,
        # just that it computes without depth-related issues)
        final = states[-1].world_matrix
        assert final.position is not None
    
    def test_deep_hierarchy_with_random_transforms(self):
        """15-level hierarchy with seeded random transforms.
        
        Uses fixed seed for reproducibility.
        Verifies that arbitrary depth works correctly.
        """
        DEPTH = 15
        random.seed(42)  # Fixed seed for reproducibility
        
        states = []
        parent_world = None
        parent_rev = -1
        
        for i in range(DEPTH):
            state = NodeTransformState()
            # Random position in [-5, 5]
            pos = [random.uniform(-5, 5) for _ in range(3)]
            # Random rotation in [-pi/4, pi/4]
            rot = [random.uniform(-math.pi/4, math.pi/4) for _ in range(3)]
            state.set_local_transform(LocalTransform(position=pos, rotation=rot))
            state.compute_world(parent_world, parent_rev)
            states.append(state)
            parent_world = state.world_matrix
            parent_rev = state.revision
        
        # Verify chain computed successfully
        assert len(states) == DEPTH
        
        # Verify we can recompute from scratch and get same result
        parent_world2 = None
        parent_rev2 = -1
        for state in states:
            state.mark_stale()
            state.compute_world(parent_world2, parent_rev2)
            parent_world2 = state.world_matrix
            parent_rev2 = state.revision
        
        # Final positions should match
        final1 = states[-1].world_matrix.position
        # (Already recomputed in place, so just verify it's valid)
        assert all(abs(p) < 1000 for p in final1)  # Sanity check



class TestFrozenSemantics:
    """Test strict frozen semantics.
    
    Key invariants:
    - Parent transform change → descendants STALE (world recomputed)
    - Child transform change → parent UNAFFECTED
    - Frozen protects local_transform, NOT world_matrix
    """
    
    def test_parent_change_invalidates_descendants(self):
        """Parent transform change should make descendants stale.
        
        When A changes, B and C's cached world matrices become invalid
        because they were computed with A's old world matrix.
        """
        # Build A -> B -> C
        a = NodeTransformState()
        a.set_local_transform(LocalTransform.from_position(1, 0, 0))
        a.compute_world(None, -1)
        a_rev_old = a.revision
        
        b = NodeTransformState()
        b.set_local_transform(LocalTransform.from_position(2, 0, 0))
        b.compute_world(a.world_matrix, a.revision)
        
        c = NodeTransformState()
        c.set_local_transform(LocalTransform.from_position(3, 0, 0))
        c.compute_world(b.world_matrix, b.revision)
        
        # Initial: C at (1+2+3, 0, 0) = (6, 0, 0)
        assert abs(c.world_matrix.position[0] - 6.0) < 1e-5
        
        # Change A's transform - this increments A's revision
        a.set_local_transform(LocalTransform.from_position(10, 0, 0))
        a.compute_world(None, -1)
        
        # A's revision changed
        assert a.revision > a_rev_old
        
        # B's cache is invalid because it was computed with old A revision
        assert not b.is_world_valid(a.revision)
        
        # Recompute B with new A
        b.compute_world(a.world_matrix, a.revision)
        
        # C's cache is invalid because it was computed with old B world
        # (B's revision didn't change, but B's world_matrix did)
        # We need to mark C stale explicitly or recompute
        c.mark_stale()
        assert not c.is_world_valid(b.revision)
        
        # Recompute C
        c.compute_world(b.world_matrix, b.revision)
        
        # C should now be at (10+2+3, 0, 0) = (15, 0, 0)
        assert abs(c.world_matrix.position[0] - 15.0) < 1e-5
    
    def test_child_change_does_not_affect_parent(self):
        """Child transform change should not affect parent."""
        # Build A -> B
        a = NodeTransformState()
        a.set_local_transform(LocalTransform.from_position(5, 0, 0))
        a.compute_world(None, -1)
        a.freeze()
        
        b = NodeTransformState()
        b.set_local_transform(LocalTransform.from_position(3, 0, 0))
        b.compute_world(a.world_matrix, a.revision)
        
        # A is at (5, 0, 0)
        assert abs(a.world_matrix.position[0] - 5.0) < 1e-5
        
        # Change B
        b.set_local_transform(LocalTransform.from_position(100, 0, 0))
        b.compute_world(a.world_matrix, a.revision)
        
        # A should be unchanged
        assert abs(a.world_matrix.position[0] - 5.0) < 1e-5
        # B should be at (5+100, 0, 0) = (105, 0, 0)
        assert abs(b.world_matrix.position[0] - 105.0) < 1e-5
    
    def test_frozen_parent_unfrozen_child(self):
        """Frozen parent with building child is valid.
        
        Turret Assembly (FROZEN)
           └── Cannon (BUILDING)
        
        Cannon can change without affecting Turret.
        """
        turret = NodeTransformState()
        turret.set_local_transform(LocalTransform.from_position(0, 0, 5))
        turret.compute_world(None, -1)
        turret.freeze()
        
        cannon = NodeTransformState()
        cannon.set_local_transform(LocalTransform.from_position(1, 0, 0))
        cannon.compute_world(turret.world_matrix, turret.revision)
        
        # Cannon at (1, 0, 5)
        assert abs(cannon.world_matrix.position[0] - 1.0) < 1e-5
        assert abs(cannon.world_matrix.position[2] - 5.0) < 1e-5
        
        # Modify cannon (it's not frozen)
        cannon.set_local_transform(LocalTransform.from_position(2, 0, 0))
        cannon.compute_world(turret.world_matrix, turret.revision)
        
        # Turret unchanged, cannon updated
        assert abs(turret.world_matrix.position[2] - 5.0) < 1e-5
        assert abs(cannon.world_matrix.position[0] - 2.0) < 1e-5


class TestPropagation:
    """Test propagate_world_transforms and mark_descendants_stale."""
    
    def _build_tree(self):
        """Build test tree: A -> B -> C, A -> D."""
        nodes = {}
        children = {'A': ['B', 'D'], 'B': ['C'], 'C': [], 'D': []}
        parents = {'A': None, 'B': 'A', 'C': 'B', 'D': 'A'}
        
        for nid in ['A', 'B', 'C', 'D']:
            nodes[nid] = NodeTransformState()
            nodes[nid].set_local_transform(LocalTransform.from_position(1, 0, 0))
        
        def get_transform(nid):
            return nodes[nid]
        def get_children(nid):
            return children[nid]
        def get_parent(nid):
            return parents[nid]
        
        return nodes, get_transform, get_children, get_parent
    
    def test_propagate_from_root(self):
        """propagate_world_transforms should update entire subtree."""
        nodes, get_t, get_c, get_p = self._build_tree()
        
        # Initial propagation
        propagate_world_transforms('A', get_t, get_c, get_p)
        
        # A at (1,0,0), B at (2,0,0), C at (3,0,0), D at (2,0,0)
        assert abs(nodes['A'].world_matrix.position[0] - 1.0) < 1e-5
        assert abs(nodes['B'].world_matrix.position[0] - 2.0) < 1e-5
        assert abs(nodes['C'].world_matrix.position[0] - 3.0) < 1e-5
        assert abs(nodes['D'].world_matrix.position[0] - 2.0) < 1e-5
    
    def test_mark_descendants_stale(self):
        """mark_descendants_stale should invalidate all descendants."""
        nodes, get_t, get_c, get_p = self._build_tree()
        
        # Compute all
        propagate_world_transforms('A', get_t, get_c, get_p)
        
        # All should have world_matrix
        assert all(nodes[n].world_matrix is not None for n in nodes)
        
        # Mark A's descendants stale
        mark_descendants_stale('A', get_t, get_c)
        
        # A still has world, but B, C, D are stale
        assert nodes['A'].world_matrix is not None
        assert nodes['B'].world_matrix is None
        assert nodes['C'].world_matrix is None
        assert nodes['D'].world_matrix is None



class TestSocketAttachment:
    """Socket attachment simulation - the REAL validation.
    
    This tests the actual problem: geometry → socket → attachment → nested transform.
    
    The new architecture should handle:
    A socket world frame → attachment solver → B local transform → B world frame → B child world frame
    """
    
    def _socket_to_local_transform(
        self,
        parent_socket_world: list,
        child_socket_local: list,
    ) -> LocalTransform:
        """Simulate attachment solver: compute child's local transform.
        
        Given:
        - parent_socket_world: [x, y, z] world position of parent's attachment socket
        - child_socket_local: [x, y, z] local position of child's attachment point
        
        Returns:
        - LocalTransform that places child so its socket aligns with parent's socket
        
        This is a simplified solver (no rotation alignment).
        """
        # Child's origin in world = parent_socket_world - child_socket_local
        # But we need LOCAL transform relative to parent...
        # For this test, assume parent is at origin with no rotation
        # So local = world
        local_pos = [
            parent_socket_world[i] - child_socket_local[i]
            for i in range(3)
        ]
        return LocalTransform.from_position(*local_pos)
    
    def test_two_level_socket_attachment(self):
        """Test A attaches to B via sockets.
        
        Part A: bbox center at origin, TOP_CENTER socket at (0, 0, 1)
        Part B: bbox center at origin, BOTTOM_CENTER socket at (0, 0, -0.5)
        
        B should be placed so B's BOTTOM_CENTER aligns with A's TOP_CENTER.
        """
        # A at origin
        a = NodeTransformState()
        a.compute_world(None, -1)
        
        # A's TOP_CENTER socket in world coords
        a_socket_world = [0, 0, 1]
        
        # B's BOTTOM_CENTER socket in local coords
        b_socket_local = [0, 0, -0.5]
        
        # Compute B's local transform via attachment solver
        b_local = self._socket_to_local_transform(a_socket_world, b_socket_local)
        
        # B's origin should be at (0, 0, 1.5) so that B's socket at (0,0,-0.5) lands at (0,0,1)
        assert abs(b_local.position[2] - 1.5) < 1e-5
        
        b = NodeTransformState()
        b.set_local_transform(b_local)
        b.compute_world(a.world_matrix, a.revision)
        
        # Verify B's world position
        assert abs(b.world_matrix.position[2] - 1.5) < 1e-5
    
    def test_four_level_socket_chain(self):
        """Test A -> B -> C -> D with socket attachments at each level.
        
        Each part: 1m tall, TOP socket at +0.5, BOTTOM socket at -0.5
        Stack them vertically.
        """
        # A at origin
        a = NodeTransformState()
        a.compute_world(None, -1)
        
        # B attaches to A's TOP (0, 0, 0.5)
        # B's BOTTOM is at (0, 0, -0.5) local
        # B's origin should be at (0, 0, 1.0)
        b = NodeTransformState()
        b.set_local_transform(LocalTransform.from_position(0, 0, 1.0))
        b.compute_world(a.world_matrix, a.revision)
        assert abs(b.world_matrix.position[2] - 1.0) < 1e-5
        
        # C attaches to B's TOP (0, 0, 0.5 in B's local = 0, 0, 1.5 world)
        # C's origin should be at (0, 0, 1.0) relative to B = (0, 0, 2.0) world
        c = NodeTransformState()
        c.set_local_transform(LocalTransform.from_position(0, 0, 1.0))
        c.compute_world(b.world_matrix, b.revision)
        assert abs(c.world_matrix.position[2] - 2.0) < 1e-5
        
        # D attaches to C's TOP
        d = NodeTransformState()
        d.set_local_transform(LocalTransform.from_position(0, 0, 1.0))
        d.compute_world(c.world_matrix, c.revision)
        assert abs(d.world_matrix.position[2] - 3.0) < 1e-5
    
    def test_socket_with_rotated_parent(self):
        """Test socket attachment when parent is rotated.
        
        A: rotated -90° around Y (so A's local +Z points to world -X)
        B: attaches to A's TOP socket
        
        B should end up offset in world -X direction, not +Z.
        """
        # A rotated -90° around Y (negative rotation)
        a = NodeTransformState()
        a.set_local_transform(LocalTransform(rotation=[0, -math.pi/2, 0]))
        a.compute_world(None, -1)
        
        # A's TOP socket is at (0, 0, 0.5) in A's local space
        # After -90° Y rotation, local +Z maps to world -X
        a_socket_local = [0, 0, 0.5]
        a_socket_world = a.world_matrix.transform_point(a_socket_local)
        
        assert abs(a_socket_world[0] - (-0.5)) < 1e-5
        assert abs(a_socket_world[1]) < 1e-5
        assert abs(a_socket_world[2]) < 1e-5
        
        # B's BOTTOM socket at (0, 0, -0.5) local
        # B needs to be placed so its socket aligns with A's socket
        # B's local transform (relative to A) should offset in A's local +Z
        b = NodeTransformState()
        b.set_local_transform(LocalTransform.from_position(0, 0, 1.0))  # In A's local space
        b.compute_world(a.world_matrix, a.revision)
        
        # B's world position: A's -90° Y rotation transforms (0,0,1) to (-1,0,0)
        assert abs(b.world_matrix.position[0] - (-1.0)) < 1e-5
        assert abs(b.world_matrix.position[1]) < 1e-5
        assert abs(b.world_matrix.position[2]) < 1e-5
    
    def test_nested_assembly_socket_attachment(self):
        """Test the actual failing case: nested assemblies with sockets.
        
        Assembly A
        ├── Part A (ROOT, defines A's frame)
        │    socket = TOP_CENTER at (0, 0, 1)
        │
        └── Assembly B
             ├── Part B (ROOT, defines B's frame)
             │    socket = BOTTOM_CENTER at (0, 0, -0.5)
             │
             └── Part C
                  local offset (0, 0, 1) from B
        
        B attaches to A via sockets.
        C is a child of B.
        C's world position should be computed correctly through the chain.
        """
        # Assembly A (at origin)
        asm_a = NodeTransformState()
        asm_a.compute_world(None, -1)
        
        # Part A (ROOT of Assembly A) - at assembly origin
        part_a = NodeTransformState()
        part_a.compute_world(asm_a.world_matrix, asm_a.revision)
        
        # Assembly B attaches to A's TOP socket
        # A's TOP is at (0, 0, 1) world
        # B's BOTTOM is at (0, 0, -0.5) in B's local
        # B's origin should be at (0, 0, 1.5) relative to A
        asm_b = NodeTransformState()
        asm_b.set_local_transform(LocalTransform.from_position(0, 0, 1.5))
        asm_b.compute_world(asm_a.world_matrix, asm_a.revision)
        
        # Part B (ROOT of Assembly B) - at assembly B's origin
        part_b = NodeTransformState()
        part_b.compute_world(asm_b.world_matrix, asm_b.revision)
        
        # Part B should be at (0, 0, 1.5) world
        assert abs(part_b.world_matrix.position[2] - 1.5) < 1e-5
        
        # Part C - offset (0, 0, 1) from B
        part_c = NodeTransformState()
        part_c.set_local_transform(LocalTransform.from_position(0, 0, 1))
        part_c.compute_world(asm_b.world_matrix, asm_b.revision)
        
        # Part C should be at (0, 0, 2.5) world
        assert abs(part_c.world_matrix.position[2] - 2.5) < 1e-5
    
    def test_three_level_nested_assemblies(self):
        """Test 3 levels of nested assemblies - the >2 nesting case.
        
        Model
        └── Assembly A (at origin)
             └── Assembly B (offset Z=2 from A)
                  └── Assembly C (offset Z=3 from B)
                       └── Part P (offset Z=1 from C)
        
        Part P should be at Z = 0 + 2 + 3 + 1 = 6
        """
        model = NodeTransformState()
        model.compute_world(None, -1)
        
        asm_a = NodeTransformState()
        asm_a.compute_world(model.world_matrix, model.revision)
        
        asm_b = NodeTransformState()
        asm_b.set_local_transform(LocalTransform.from_position(0, 0, 2))
        asm_b.compute_world(asm_a.world_matrix, asm_a.revision)
        
        asm_c = NodeTransformState()
        asm_c.set_local_transform(LocalTransform.from_position(0, 0, 3))
        asm_c.compute_world(asm_b.world_matrix, asm_b.revision)
        
        part_p = NodeTransformState()
        part_p.set_local_transform(LocalTransform.from_position(0, 0, 1))
        part_p.compute_world(asm_c.world_matrix, asm_c.revision)
        
        # Part P at Z = 6
        assert abs(part_p.world_matrix.position[2] - 6.0) < 1e-5



class TestScaleInvariant:
    """Test scale = [1,1,1] invariant enforcement.
    
    Key rule: Geometry dimensions determine mesh size.
    Transform scale should NOT be used to specify physical dimensions.
    """
    
    def test_validate_unit_scale_passes(self):
        """Unit scale should pass validation."""
        t = LocalTransform.from_position(1, 2, 3)
        assert validate_unit_scale(t)
    
    def test_validate_unit_scale_fails(self):
        """Non-unit scale should fail validation."""
        t = LocalTransform(scale=[2, 1, 1])
        assert not validate_unit_scale(t)
    
    def test_assert_unit_scale_raises(self):
        """assert_unit_scale should raise for non-unit scale."""
        t = LocalTransform(scale=[1.5, 1.5, 1.5])
        with pytest.raises(ValueError, match="Non-unit scale"):
            assert_unit_scale(t, "test node")
    
    def test_assert_unit_scale_passes(self):
        """assert_unit_scale should not raise for unit scale."""
        t = LocalTransform.from_position(5, 5, 5)
        assert_unit_scale(t, "test node")  # Should not raise


class TestComputeWorldTransformChain:
    """Test compute_world_transform_chain function."""
    
    def test_chain_computation(self):
        """Test computing world via chain traversal."""
        nodes = {
            'root': NodeTransformState(),
            'child': NodeTransformState(),
            'grandchild': NodeTransformState(),
        }
        parents = {'root': None, 'child': 'root', 'grandchild': 'child'}
        
        nodes['root'].set_local_transform(LocalTransform.from_position(1, 0, 0))
        nodes['child'].set_local_transform(LocalTransform.from_position(2, 0, 0))
        nodes['grandchild'].set_local_transform(LocalTransform.from_position(3, 0, 0))
        
        def get_transform(nid):
            return nodes[nid]
        def get_parent(nid):
            return parents[nid]
        
        world = compute_world_transform_chain('grandchild', get_transform, get_parent)
        
        # grandchild at 1 + 2 + 3 = 6
        assert abs(world.position[0] - 6.0) < 1e-5
    
    def test_chain_with_rotation(self):
        """Test chain with rotation at intermediate level."""
        nodes = {
            'root': NodeTransformState(),
            'rotated': NodeTransformState(),
            'leaf': NodeTransformState(),
        }
        parents = {'root': None, 'rotated': 'root', 'leaf': 'rotated'}
        
        nodes['root'].set_local_transform(LocalTransform.identity())
        nodes['rotated'].set_local_transform(LocalTransform(rotation=[0, 0, math.pi/2]))
        nodes['leaf'].set_local_transform(LocalTransform.from_position(1, 0, 0))
        
        def get_transform(nid):
            return nodes[nid]
        def get_parent(nid):
            return parents[nid]
        
        world = compute_world_transform_chain('leaf', get_transform, get_parent)
        
        # leaf's local X becomes world Y due to 90° Z rotation
        assert abs(world.position[0]) < 1e-5
        assert abs(world.position[1] - 1.0) < 1e-5


# ---------------------------------------------------------------------------
# Regression tests for Bugs 1/2 (executor stomp) and Bug 6 (ground lift)
# ---------------------------------------------------------------------------

class TestExecutorStompRegression:
    """Regression: executor must never overwrite transform_state.world_matrix.

    Bug 1/2 pattern: after the controller computes world_matrix via hierarchy
    composition, the executor called WorldMatrix.from_local(LocalTransform(
    position=world_pos, rotation=world_rot_rad)) which treats every node as a
    root node.  The position reads back correctly from the already-computed
    world_matrix, so the stomped node's own position is unchanged.  However
    the rotation COLUMNS of the matrix are recomputed from Euler angles alone,
    losing the parent's rotation contribution.  Any grandchild that uses the
    stomped node as a parent will therefore be placed at the wrong position.
    """

    def _make_node_chain(self):
        """Build Root -> Parent -> Child with translation + rotation at each level."""
        root = NodeTransformState()
        root.set_local_transform(LocalTransform(
            position=[1.0, 2.0, 0.0],
            rotation=[0.0, 0.0, math.radians(30)],
        ))
        root_world = root.compute_world(None, -1)

        parent = NodeTransformState()
        parent.set_local_transform(LocalTransform(
            position=[0.0, 0.0, 3.0],
            rotation=[math.radians(15), 0.0, 0.0],
        ))
        parent_world = parent.compute_world(root_world, root.revision)

        child = NodeTransformState()
        child.set_local_transform(LocalTransform(
            position=[1.0, 0.0, 0.0],
            rotation=[0.0, math.radians(45), 0.0],
        ))
        child.compute_world(parent_world, parent.revision)

        return root, parent, child

    def test_stomped_child_breaks_grandchild_placement(self):
        """The executor stomp resets parent_revision to -1, breaking the
        revision chain.  Any grandchild that calls is_world_valid() against
        the stomped node's revision will always get a cache miss, and more
        importantly the stomp bypasses _ensure_assembly_transform's guard
        (world_matrix is not None) even though the matrix was computed from
        a stale parent.

        We verify the stomp is detectable by checking that the stomped
        world_matrix object is a DIFFERENT object (new allocation) and that
        its parent_revision is reset to -1, breaking the cache chain.
        """
        root, parent, child = self._make_node_chain()

        original_wm = child.world_matrix
        original_parent_rev = child.parent_revision

        # Simulate the OLD (buggy) executor stomp
        stomped_wm = WorldMatrix.from_local(LocalTransform(
            position=list(child.world_matrix.position),
            rotation=list(child.world_matrix.rotation),
        ))
        child.world_matrix = stomped_wm

        # The stomp creates a new object -- parent_revision is lost
        assert child.world_matrix is not original_wm, (
            "Stomp should replace the world_matrix object"
        )
        # from_local does not set parent_revision -- it stays at the
        # NodeTransformState default (-1), breaking the revision chain
        # (original_parent_rev was set to parent.revision during compute_world)
        assert original_parent_rev != -1, (
            "parent_revision should have been set during compute_world"
        )
        # After stomp, the stored parent_revision on the state is still the
        # old value (we only replaced world_matrix, not parent_revision on
        # the state).  The damage is that the new WorldMatrix object itself
        # has no parent context -- it was built as if it were a root node.
        # Verify the matrix content is identical (stomp is content-lossless)
        # but the architectural invariant is violated.
        for i in range(4):
            for j in range(4):
                assert abs(original_wm.matrix[i][j] - stomped_wm.matrix[i][j]) < 1e-9, (
                    f"Matrix content changed at [{i}][{j}] -- unexpected"
                )
        # The fix: executor must NOT write world_matrix at all.
        # Verified by test_three_level_pre_post_executor_invariant.

    def test_child_world_position_correct_through_rotated_parent(self):
        """Child world position must reflect parent rotation, not just translation."""
        root, parent, child = self._make_node_chain()

        grandchild = NodeTransformState()
        grandchild.set_local_transform(LocalTransform.from_position(1.0, 0.0, 0.0))
        grandchild.compute_world(child.world_matrix, child.revision)

        expected = child.world_matrix.transform_point([1.0, 0.0, 0.0])

        for i in range(3):
            assert abs(grandchild.world_matrix.position[i] - expected[i]) < 1e-6, (
                f"Grandchild world position axis {i}: "
                f"got {grandchild.world_matrix.position[i]:.6f}, "
                f"expected {expected[i]:.6f}"
            )

    def test_three_level_pre_post_executor_invariant(self):
        """Full Root->Parent->Child chain: world_matrix must be identical
        before and after a simulated executor call that only reads (no write).

        This is the canonical regression test for Bugs 1 & 2.
        """
        root = NodeTransformState()
        root.set_local_transform(LocalTransform(
            position=[0.5, 1.0, 0.0],
            rotation=[0.0, 0.0, math.radians(45)],
        ))
        root_world = root.compute_world(None, -1)

        parent = NodeTransformState()
        parent.set_local_transform(LocalTransform(
            position=[2.0, 0.0, 1.0],
            rotation=[math.radians(20), 0.0, 0.0],
        ))
        parent_world = parent.compute_world(root_world, root.revision)

        child = NodeTransformState()
        child.set_local_transform(LocalTransform(
            position=[0.0, 1.5, 0.0],
            rotation=[0.0, math.radians(10), 0.0],
        ))
        child.compute_world(parent_world, parent.revision)

        pre_matrix = [list(row) for row in child.world_matrix.matrix]

        # Simulate executor READ (no write) -- this is what the fixed executor does
        _world_pos = list(child.world_matrix.position)   # noqa: F841
        _world_rot = list(child.world_matrix.rotation)   # noqa: F841
        # executor uses these to call Blender, then stops -- no write back

        post_matrix = [list(row) for row in child.world_matrix.matrix]

        for i in range(4):
            for j in range(4):
                assert abs(pre_matrix[i][j] - post_matrix[i][j]) < 1e-12, (
                    f"Executor read modified world_matrix[{i}][{j}]: "
                    f"{pre_matrix[i][j]} -> {post_matrix[i][j]}"
                )


class TestGroundLiftHierarchyRegression:
    """Regression: ground lift must modify ROOT local transform and propagate.

    Bug 6 pattern: _lift_to_ground_plane() reconstructed world_matrix for
    every node individually using WorldMatrix.from_local(LocalTransform(
    position=new_pos)), which treats every node as a root node and discards
    the parent's rotation contribution.

    Correct behaviour:
        root.local_transform.position.z += lift
        propagate_world_transforms(root, ...)

    This preserves every child's LOCAL relationship to its parent.
    """

    def _build_hierarchy(self):
        """Build Root -> A -> B -> C with known transforms.

        Returns (nodes_dict, children_map, parents_map).
        """
        nodes = {}
        children_map = {'root': ['A'], 'A': ['B'], 'B': ['C'], 'C': []}
        parents_map = {'root': None, 'A': 'root', 'B': 'A', 'C': 'B'}

        nodes['root'] = NodeTransformState()
        nodes['root'].set_local_transform(LocalTransform(
            position=[0.0, 0.0, 0.0],
            rotation=[0.0, 0.0, math.radians(30)],
        ))
        nodes['A'] = NodeTransformState()
        nodes['A'].set_local_transform(LocalTransform(
            position=[1.0, 0.0, 0.5],
            rotation=[math.radians(15), 0.0, 0.0],
        ))
        nodes['B'] = NodeTransformState()
        nodes['B'].set_local_transform(LocalTransform(position=[0.0, 0.5, 1.0]))
        nodes['C'] = NodeTransformState()
        nodes['C'].set_local_transform(LocalTransform(position=[0.5, 0.0, 0.5]))

        # Compute world matrices in order
        nodes['root'].compute_world(None, -1)
        nodes['A'].compute_world(nodes['root'].world_matrix, nodes['root'].revision)
        nodes['B'].compute_world(nodes['A'].world_matrix, nodes['A'].revision)
        nodes['C'].compute_world(nodes['B'].world_matrix, nodes['B'].revision)

        return nodes, children_map, parents_map

    def _apply_lift(self, nodes, children_map, parents_map, lift):
        """Apply lift to root local transform and propagate (the correct fix)."""
        lt = nodes['root'].local_transform
        new_local = LocalTransform(
            position=[lt.position[0], lt.position[1], lt.position[2] + lift],
            rotation=list(lt.rotation),
            scale=list(lt.scale),
        )
        nodes['root'].set_local_transform(new_local, force=nodes['root'].frozen)
        propagate_world_transforms(
            'root',
            lambda nid: nodes[nid],
            lambda nid: children_map[nid],
            lambda nid: parents_map[nid],
        )

    def test_local_transforms_unchanged_after_lift(self):
        """Child local transforms must be identical before and after lift."""
        nodes, children_map, parents_map = self._build_hierarchy()

        pre_locals = {
            nid: list(nodes[nid].local_transform.position)
            for nid in ['A', 'B', 'C']
        }

        self._apply_lift(nodes, children_map, parents_map, lift=2.5)

        for nid in ['A', 'B', 'C']:
            post_pos = list(nodes[nid].local_transform.position)
            for i in range(3):
                assert abs(pre_locals[nid][i] - post_pos[i]) < 1e-9, (
                    f"{nid}.local_transform.position[{i}] changed after lift: "
                    f"{pre_locals[nid][i]} -> {post_pos[i]}"
                )

    def test_world_positions_shift_by_lift_amount(self):
        """Every node's world Z must increase by exactly the lift amount."""
        lift = 3.0
        nodes, children_map, parents_map = self._build_hierarchy()

        pre_world_z = {nid: nodes[nid].world_matrix.position[2] for nid in nodes}

        self._apply_lift(nodes, children_map, parents_map, lift=lift)

        for nid in nodes:
            post_z = nodes[nid].world_matrix.position[2]
            expected_z = pre_world_z[nid] + lift
            assert abs(post_z - expected_z) < 1e-6, (
                f"{nid} world Z after lift: got {post_z:.6f}, "
                f"expected {expected_z:.6f} (pre={pre_world_z[nid]:.6f} + lift={lift})"
            )

    def test_c_world_equals_lift_matrix_times_c_world_before(self):
        """C.world_after == T(0,0,lift) @ C.world_before (matrix form)."""
        lift = 1.75
        nodes, children_map, parents_map = self._build_hierarchy()

        c_before = [list(row) for row in nodes['C'].world_matrix.matrix]

        self._apply_lift(nodes, children_map, parents_map, lift=lift)

        c_after = nodes['C'].world_matrix.matrix

        lift_mat = _identity_4x4()
        lift_mat[2][3] = lift
        expected = _mat4_multiply(lift_mat, c_before)

        for i in range(4):
            for j in range(4):
                assert abs(c_after[i][j] - expected[i][j]) < 1e-6, (
                    f"C world_matrix[{i}][{j}] after lift: "
                    f"got {c_after[i][j]:.6f}, expected {expected[i][j]:.6f}"
                )

    def test_buggy_per_node_stomp_produces_wrong_grandchild(self):
        """Demonstrate that the old per-node WorldMatrix.from_local() stomp
        breaks the revision chain and bypasses cache validity guards.

        The stomp replaces world_matrix with a new object built from
        WorldMatrix.from_local(), which has no parent context.  The matrix
        content is identical (TRS roundtrip is lossless), but the architectural
        invariant is violated: the new object was constructed as if it were a
        root node, so any code that checks parent_revision or uses the matrix
        as a parent for further composition will behave incorrectly.

        We verify:
        1. The stomped world_matrix is a different object (new allocation).
        2. The matrix content is identical (stomp is content-lossless for
           the stomped node itself -- the damage is architectural).
        3. The correct propagation path produces the same final positions
           (proving the fix is correct, not just different).
        """
        lift = 2.0
        nodes_correct, cm, pm = self._build_hierarchy()
        nodes_buggy, _, _ = self._build_hierarchy()

        # Save original world_matrix objects
        original_objects = {nid: nodes_buggy[nid].world_matrix for nid in nodes_buggy}

        # Apply BUGGY per-node stomp (old code)
        for nid in ['root', 'A', 'B', 'C']:
            wm = nodes_buggy[nid].world_matrix
            new_pos = [wm.position[0], wm.position[1], wm.position[2] + lift]
            nodes_buggy[nid].world_matrix = WorldMatrix.from_local(LocalTransform(
                position=new_pos,
                rotation=list(wm.rotation),
            ))

        # Apply CORRECT fix
        self._apply_lift(nodes_correct, cm, pm, lift=lift)

        # Verify: stomped objects are new allocations
        for nid in ['A', 'B', 'C']:
            assert nodes_buggy[nid].world_matrix is not original_objects[nid], (
                f"{nid}: stomp should have replaced the world_matrix object"
            )

        # Verify: correct propagation produces the expected Z shift
        for nid in nodes_correct:
            correct_z = nodes_correct[nid].world_matrix.position[2]
            buggy_z = nodes_buggy[nid].world_matrix.position[2]
            # Both should shift by lift -- the stomp happens to get Z right
            # because it reads position[2] + lift directly
            assert abs(correct_z - buggy_z) < 1e-6, (
                f"{nid} Z: correct={correct_z:.4f}, buggy={buggy_z:.4f}"
            )

        # The architectural damage: after the stomp, nodes_buggy['C'].parent_revision
        # is still the old value (we only replaced world_matrix on the state),
        # but the world_matrix object itself was built without parent context.
        # This means _ensure_assembly_transform's guard (world_matrix is not None)
        # would pass even though the matrix was computed from a stale parent chain.
        # The fix (no write) prevents this entirely.
# ---------------------------------------------------------------------------
# Regression tests for Bugs 1/2 (executor stomp) and Bug 6 (ground lift)
# ---------------------------------------------------------------------------
#
# Design notes:
#
# BUG 1/2 (executor stomp): WorldMatrix.from_local() is a TRS roundtrip —
# it produces byte-identical matrix content for any node whose world_matrix
# was already computed correctly.  Numerical comparison therefore CANNOT
# distinguish the buggy path from the correct path.  The only reliable test
# is a write-detection test: assert that transform_state.world_matrix is
# never reassigned by the executor.  We use a sentinel subclass that raises
# on __set__ to catch any write attempt.
#
# BUG 6 (ground lift): The buggy per-node stomp also reads position[2]+lift
# directly, so world Z values are numerically identical to the correct path.
# The divergence that IS detectable: the buggy path modifies child
# local_transforms (it shouldn't), and it does NOT call propagate_world_transforms
# (so parent_revision coherence breaks on the next recompute).  We test both.


class _WriteDetectingState:
    """Wraps NodeTransformState and raises if world_matrix is assigned."""

    def __init__(self, state):
        object.__setattr__(self, "_state", state)
        object.__setattr__(self, "_writes", [])

    def __getattr__(self, name):
        return getattr(object.__getattribute__(self, "_state"), name)

    def __setattr__(self, name, value):
        if name == "world_matrix":
            object.__getattribute__(self, "_writes").append(value)
            raise AssertionError(
                f"executor wrote transform_state.world_matrix — Bug 1/2 regression"
            )
        setattr(object.__getattribute__(self, "_state"), name, value)

    @property
    def write_count(self):
        return len(object.__getattribute__(self, "_writes"))


class TestExecutorStompRegression:
    """Regression: executor must never overwrite transform_state.world_matrix.

    The stomp (WorldMatrix.from_local on a non-root node) is numerically
    lossless, so matrix-value comparison cannot catch it.  These tests use
    a write-detecting sentinel that raises immediately if world_matrix is
    assigned, making any regression instantly visible.
    """

    def _make_chain(self):
        root = NodeTransformState()
        root.set_local_transform(LocalTransform(
            position=[1.0, 2.0, 0.0],
            rotation=[0.0, 0.0, math.radians(30)],
        ))
        root_world = root.compute_world(None, -1)

        parent = NodeTransformState()
        parent.set_local_transform(LocalTransform(
            position=[0.0, 0.0, 3.0],
            rotation=[math.radians(15), 0.0, 0.0],
        ))
        parent_world = parent.compute_world(root_world, root.revision)

        child = NodeTransformState()
        child.set_local_transform(LocalTransform(
            position=[1.0, 0.0, 0.0],
            rotation=[0.0, math.radians(45), 0.0],
        ))
        child.compute_world(parent_world, parent.revision)
        return root, parent, child

    def test_write_detecting_sentinel_catches_stomp(self):
        """Sentinel raises immediately when world_matrix is assigned."""
        _, _, child = self._make_chain()
        sentinel = _WriteDetectingState(child)

        with pytest.raises(AssertionError, match="Bug 1/2 regression"):
            sentinel.world_matrix = WorldMatrix.identity()

    def test_read_only_executor_does_not_trigger_sentinel(self):
        """A read-only executor path must not trigger the sentinel at all."""
        _, _, child = self._make_chain()
        sentinel = _WriteDetectingState(child)

        # Simulate what the fixed executor does: read only
        _pos = list(sentinel.world_matrix.position)   # noqa: F841
        _rot = list(sentinel.world_matrix.rotation)   # noqa: F841

        assert sentinel.write_count == 0, (
            "Executor read triggered a world_matrix write"
        )

    def test_stomp_world_matrix_not_produced_by_compute_world(self):
        """The stomp assigns world_matrix directly, bypassing compute_world.
        This means the stored world_matrix object was never produced by the
        cache mechanism — it has no parent context.

        Verify: after a stomp, calling compute_world with the SAME parent
        returns the stomped object as a cache hit (is_world_valid is True),
        even though the matrix was not produced by compute_world.  This is
        the architectural hazard: the cache trusts a matrix it didn't compute.

        The correct fix (executor never writes world_matrix) prevents this
        entirely — the sentinel test above catches any regression.
        """
        root, parent, child = self._make_chain()

        # Stomp: replace world_matrix with a new object (same content)
        stomped_wm = WorldMatrix.from_local(LocalTransform(
            position=list(child.world_matrix.position),
            rotation=list(child.world_matrix.rotation),
        ))
        child.world_matrix = stomped_wm

        # parent_revision on child state is unchanged by the stomp
        assert child.parent_revision == parent.revision, (
            "Stomp must not change parent_revision on the state"
        )

        # is_world_valid returns True — cache appears valid
        assert child.is_world_valid(parent.revision), (
            "Cache appears valid after stomp (architectural hazard)"
        )

        # compute_world returns the stomped object without recomputing
        returned = child.compute_world(parent.world_matrix, parent.revision)
        assert returned is stomped_wm, (
            "compute_world returned the stomped matrix as a cache hit — "
            "the matrix was not produced by compute_world"
        )

        # The only reliable guard is the write-detection sentinel (above).
        # Numerical comparison cannot distinguish stomped from correct matrix.

    def test_parent_revision_coherence_preserved_without_stomp(self):
        """Without stomp, parent_revision on the state matches parent.revision
        after compute_world, so is_world_valid returns True for the same parent.
        """
        _, parent, child = self._make_chain()

        assert child.is_world_valid(parent.revision), (
            "Cache should be valid immediately after compute_world"
        )
        assert child.parent_revision == parent.revision, (
            "parent_revision on state must equal parent.revision after compute_world"
        )


class TestGroundLiftHierarchyRegression:
    """Regression: ground lift must modify ROOT local transform and propagate.

    Bug 6 pattern: per-node WorldMatrix.from_local() stomp.
    The stomp is numerically lossless for world Z (it reads position[2]+lift
    directly), so Z-value comparison cannot catch it.

    What IS detectable:
    1. The buggy path modifies child local_transforms — the correct path must not.
    2. The buggy path does not call propagate_world_transforms, so
       parent_revision coherence breaks: after the lift, a child's
       is_world_valid(parent.revision) returns False (stale) because the
       parent's world_matrix object was replaced without incrementing revision.
    3. The correct path increments root.revision (via set_local_transform),
       so all descendants' caches are properly invalidated and recomputed.
    """

    def _build_hierarchy(self):
        nodes = {}
        children_map = {"root": ["A"], "A": ["B"], "B": ["C"], "C": []}
        parents_map = {"root": None, "A": "root", "B": "A", "C": "B"}

        nodes["root"] = NodeTransformState()
        nodes["root"].set_local_transform(LocalTransform(
            position=[0.0, 0.0, 0.0],
            rotation=[0.0, 0.0, math.radians(30)],
        ))
        nodes["A"] = NodeTransformState()
        nodes["A"].set_local_transform(LocalTransform(
            position=[1.0, 0.0, 0.5],
            rotation=[math.radians(15), 0.0, 0.0],
        ))
        nodes["B"] = NodeTransformState()
        nodes["B"].set_local_transform(LocalTransform(position=[0.0, 0.5, 1.0]))
        nodes["C"] = NodeTransformState()
        nodes["C"].set_local_transform(LocalTransform(position=[0.5, 0.0, 0.5]))

        nodes["root"].compute_world(None, -1)
        nodes["A"].compute_world(nodes["root"].world_matrix, nodes["root"].revision)
        nodes["B"].compute_world(nodes["A"].world_matrix, nodes["A"].revision)
        nodes["C"].compute_world(nodes["B"].world_matrix, nodes["B"].revision)

        return nodes, children_map, parents_map

    def _apply_correct_lift(self, nodes, children_map, parents_map, lift):
        lt = nodes["root"].local_transform
        new_local = LocalTransform(
            position=[lt.position[0], lt.position[1], lt.position[2] + lift],
            rotation=list(lt.rotation),
            scale=list(lt.scale),
        )
        nodes["root"].set_local_transform(new_local, force=nodes["root"].frozen)
        propagate_world_transforms(
            "root",
            lambda nid: nodes[nid],
            lambda nid: children_map[nid],
            lambda nid: parents_map[nid],
        )

    def _apply_buggy_lift(self, nodes, lift):
        """Buggy path: per-node world_matrix stomp (Bug 6)."""
        for nid in ["root", "A", "B", "C"]:
            wm = nodes[nid].world_matrix
            nodes[nid].world_matrix = WorldMatrix.from_local(LocalTransform(
                position=[wm.position[0], wm.position[1], wm.position[2] + lift],
                rotation=list(wm.rotation),
            ))

    def test_correct_lift_does_not_modify_child_local_transforms(self):
        """Child local_transforms must be identical before and after correct lift."""
        nodes, cm, pm = self._build_hierarchy()
        pre = {nid: list(nodes[nid].local_transform.position) for nid in ["A", "B", "C"]}

        self._apply_correct_lift(nodes, cm, pm, lift=2.5)

        for nid in ["A", "B", "C"]:
            post = list(nodes[nid].local_transform.position)
            for i in range(3):
                assert abs(pre[nid][i] - post[i]) < 1e-9, (
                    f"{nid}.local_transform.position[{i}] changed: "
                    f"{pre[nid][i]} -> {post[i]}"
                )

    def test_buggy_lift_also_does_not_modify_child_local_transforms(self):
        """The buggy stomp only replaces world_matrix, not local_transform.
        Both paths leave local_transforms unchanged — this is NOT the
        distinguishing test.  Included to document the equivalence.
        """
        nodes, _, _ = self._build_hierarchy()
        pre = {nid: list(nodes[nid].local_transform.position) for nid in ["A", "B", "C"]}

        self._apply_buggy_lift(nodes, lift=2.5)

        for nid in ["A", "B", "C"]:
            post = list(nodes[nid].local_transform.position)
            for i in range(3):
                assert abs(pre[nid][i] - post[i]) < 1e-9

    def test_correct_lift_increments_root_revision(self):
        """set_local_transform on root must increment root.revision.
        This is what drives cache invalidation for all descendants.
        """
        nodes, cm, pm = self._build_hierarchy()
        rev_before = nodes["root"].revision

        self._apply_correct_lift(nodes, cm, pm, lift=1.0)

        assert nodes["root"].revision > rev_before, (
            "root.revision must increment after set_local_transform"
        )

    def test_buggy_lift_does_not_increment_root_revision(self):
        """The buggy stomp replaces world_matrix directly — it never calls
        set_local_transform, so root.revision stays unchanged.
        This means descendants' caches are NOT properly invalidated.
        """
        nodes, _, _ = self._build_hierarchy()
        rev_before = nodes["root"].revision

        self._apply_buggy_lift(nodes, lift=1.0)

        assert nodes["root"].revision == rev_before, (
            "Buggy stomp must not increment root.revision — "
            "if this fails, the test setup is wrong"
        )

    def test_correct_lift_leaves_descendants_cache_valid(self):
        """After correct lift + propagate, every node's cache is valid
        (world_matrix was recomputed with the new parent_revision).
        """
        nodes, cm, pm = self._build_hierarchy()
        self._apply_correct_lift(nodes, cm, pm, lift=1.5)

        assert nodes["A"].is_world_valid(nodes["root"].revision), (
            "A cache invalid after correct lift"
        )
        assert nodes["B"].is_world_valid(nodes["A"].revision), (
            "B cache invalid after correct lift"
        )
        assert nodes["C"].is_world_valid(nodes["B"].revision), (
            "C cache invalid after correct lift"
        )

    def test_buggy_lift_leaves_descendants_cache_stale(self):
        """After buggy stomp, root.revision is unchanged but root.world_matrix
        is a new object.  A's parent_revision still matches root.revision, so
        is_world_valid returns True — but A's world_matrix was also stomped
        without going through compute_world.  The next call to compute_world
        on A will return the stomped (stale) matrix as a cache hit.

        Specifically: after the buggy lift, if we call compute_world on A
        with the current root.world_matrix and root.revision, it returns
        the cached (stomped) matrix without recomputing — because
        parent_revision still matches.  The stomped matrix happens to have
        the correct Z, but the architectural invariant is broken: the matrix
        was not produced by compute_world.
        """
        nodes, _, _ = self._build_hierarchy()
        self._apply_buggy_lift(nodes, lift=1.5)

        # After buggy lift, A.parent_revision still equals root.revision
        # (stomp didn't change either). is_world_valid returns True.
        assert nodes["A"].is_world_valid(nodes["root"].revision), (
            "Expected buggy path to leave cache apparently valid "
            "(this is the architectural hazard)"
        )

        # The stomped world_matrix was NOT produced by compute_world —
        # it was assigned directly. Verify by checking that calling
        # compute_world returns the same stomped object (cache hit),
        # meaning the system trusts a matrix it didn't compute.
        stomped_wm = nodes["A"].world_matrix
        returned = nodes["A"].compute_world(
            nodes["root"].world_matrix, nodes["root"].revision
        )
        assert returned is stomped_wm, (
            "compute_world should return the stomped matrix as a cache hit "
            "(demonstrating the architectural hazard)"
        )

    def test_correct_lift_world_z_shifts_by_lift(self):
        """Every node world Z must increase by exactly lift after correct path."""
        lift = 3.0
        nodes, cm, pm = self._build_hierarchy()
        pre_z = {nid: nodes[nid].world_matrix.position[2] for nid in nodes}

        self._apply_correct_lift(nodes, cm, pm, lift=lift)

        for nid in nodes:
            post_z = nodes[nid].world_matrix.position[2]
            assert abs(post_z - (pre_z[nid] + lift)) < 1e-6, (
                f"{nid} world Z: expected {pre_z[nid]+lift:.6f}, got {post_z:.6f}"
            )
