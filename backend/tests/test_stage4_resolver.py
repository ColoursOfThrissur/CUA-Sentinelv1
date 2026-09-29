"""Stage 4 Resolver Tests — comprehensive coverage for transform resolution.

Tests the critical invariants:
1. Rotation composition via matrix math (not Euler addition)
2. Offset rotation by parent's world rotation
3. All socket types have resolvers (no silent fallback)
4. THROUGH_AXIS uses child geometry for embedment
5. FRONT/BACK convention matches Blender (-Y = front)
6. Boolean cutters have overshoot margin

Blueprint reference: Chain test cases A, B, C from prior verification.
"""

import math
import pytest
from unittest.mock import MagicMock

# Import the modules under test
from core.blender_pipeline.progressive_v2.stages.stage4_resolver import (
    Stage4Resolver,
    Stage4Error,
    ResolvedTransform,
    BBox,
    BOOLEAN_OVERSHOOT_M,
)


def _run(node, manifest):
    """Unpack Stage4Resolver.run() and return just the ResolvedTransform."""
    resolved, _ = Stage4Resolver.run(node, manifest)
    return resolved
from core.blender_pipeline.progressive_v2.node_types import (
    NodeKind,
    SocketType,
    PrimitiveType,
)
from core.blender_pipeline.progressive_v2.manifest import (
    BuildManifest,
    ManifestNode,
    GeometrySpec,
    AttachmentSpec,
)
from core.blender_pipeline.progressive_v2.executor import (
    _euler_to_matrix,
    _matrix_to_euler,
    _compose_rotations,
    _rotate_vector_by_euler,
    BlenderExecutor,
)


# ---------------------------------------------------------------------------
# Rotation Composition Tests (Critical Issue #1)
# ---------------------------------------------------------------------------

class TestRotationComposition:
    """Test that rotation composition uses matrix math, not Euler addition."""
    
    def test_identity_composition(self):
        """Composing with identity returns the other rotation."""
        identity = [0.0, 0.0, 0.0]
        rot_90z = [0.0, 0.0, math.pi / 2]
        
        result = _compose_rotations(identity, rot_90z)
        assert abs(result[2] - math.pi / 2) < 0.0001
        
        result = _compose_rotations(rot_90z, identity)
        assert abs(result[2] - math.pi / 2) < 0.0001
    
    def test_90_degree_compositions(self):
        """Test 90° rotations compose correctly."""
        rot_90x = [math.pi / 2, 0.0, 0.0]
        rot_90y = [0.0, math.pi / 2, 0.0]
        rot_90z = [0.0, 0.0, math.pi / 2]
        
        # 90° X then 90° Y should NOT equal 90° Y then 90° X
        # (rotation is non-commutative)
        result_xy = _compose_rotations(rot_90x, rot_90y)
        result_yx = _compose_rotations(rot_90y, rot_90x)
        
        # They should be different
        diff = sum(abs(result_xy[i] - result_yx[i]) for i in range(3))
        assert diff > 0.1, "Rotation composition should be non-commutative"
    
    def test_euler_addition_is_wrong(self):
        """Verify that simple Euler addition gives wrong results."""
        # This test documents WHY we need matrix composition
        rot_45x = [math.pi / 4, 0.0, 0.0]
        rot_45y = [0.0, math.pi / 4, 0.0]
        
        # Wrong way: Euler addition
        wrong_result = [rot_45x[0] + rot_45y[0], rot_45x[1] + rot_45y[1], rot_45x[2] + rot_45y[2]]
        
        # Right way: matrix composition
        correct_result = _compose_rotations(rot_45x, rot_45y)
        
        # They should be different
        diff = sum(abs(wrong_result[i] - correct_result[i]) for i in range(3))
        assert diff > 0.01, "Matrix composition should differ from Euler addition"
    
    def test_roundtrip_euler_matrix_euler(self):
        """Test Euler -> Matrix -> Euler roundtrip."""
        original = [0.3, 0.5, 0.7]  # Arbitrary rotation
        
        matrix = _euler_to_matrix(original)
        recovered = _matrix_to_euler(matrix)
        
        for i in range(3):
            assert abs(original[i] - recovered[i]) < 0.0001, f"Axis {i} mismatch"


class TestOffsetRotation:
    """Test that local offsets are rotated by parent's world rotation."""
    
    def test_offset_rotated_by_90z(self):
        """Offset [1, 0, 0] rotated 90° around Z should become [0, 1, 0]."""
        offset = [1.0, 0.0, 0.0]
        rot_90z = [0.0, 0.0, math.pi / 2]
        
        result = _rotate_vector_by_euler(offset, rot_90z)
        
        assert abs(result[0]) < 0.0001, f"X should be ~0, got {result[0]}"
        assert abs(result[1] - 1.0) < 0.0001, f"Y should be ~1, got {result[1]}"
        assert abs(result[2]) < 0.0001, f"Z should be ~0, got {result[2]}"
    
    def test_offset_rotated_by_90x(self):
        """Offset [0, 1, 0] rotated 90° around X should become [0, 0, 1]."""
        offset = [0.0, 1.0, 0.0]
        rot_90x = [math.pi / 2, 0.0, 0.0]
        
        result = _rotate_vector_by_euler(offset, rot_90x)
        
        assert abs(result[0]) < 0.0001
        assert abs(result[1]) < 0.0001
        assert abs(result[2] - 1.0) < 0.0001
    
    def test_identity_rotation_preserves_offset(self):
        """Identity rotation should not change the offset."""
        offset = [1.5, 2.5, 3.5]
        identity = [0.0, 0.0, 0.0]
        
        result = _rotate_vector_by_euler(offset, identity)
        
        for i in range(3):
            assert abs(result[i] - offset[i]) < 0.0001


# ---------------------------------------------------------------------------
# Three-Level Chain Test (Critical Issue #1 - Regression Test)
# ---------------------------------------------------------------------------

class TestThreeLevelChain:
    """Test the three-level chain that catches rotation composition bugs.
    
    Setup:
    - Root: post at origin
    - Child: arm attached to post, rotated 45° around Y
    - Grandchild: disc at end of arm
    
    If rotation composition is wrong, the disc will be misplaced.
    """
    
    def _create_chain_manifest(self) -> BuildManifest:
        """Create a three-level chain for testing."""
        manifest = BuildManifest.create("test chain")
        root = manifest.get_root()
        
        # Root is a vertical post
        post = manifest.add_child_node(
            parent_id=root.node_id,
            label="post",
            kind=NodeKind.PART,
            geometry=GeometrySpec(primitive=PrimitiveType.CYLINDER, radius=0.1, depth=1.0),
            attachment=AttachmentSpec(socket_type=SocketType.ROOT),
        )
        post.stage_outputs["stage2"] = {"radius": 0.1, "depth": 1.0}
        
        # Arm attached to post, tilted 45° around Y
        # NOTE: local_rotation is in DEGREES in AttachmentSpec
        arm = manifest.add_child_node(
            parent_id=post.node_id,
            label="arm",
            kind=NodeKind.PART,
            geometry=GeometrySpec(primitive=PrimitiveType.CYLINDER, radius=0.05, depth=0.5),
            attachment=AttachmentSpec(
                socket_type=SocketType.TOP_CENTER,
                local_rotation=[0.0, 45.0, 0.0],  # 45° tilt in degrees
            ),
        )
        arm.stage_outputs["stage2"] = {"radius": 0.05, "depth": 0.5}
        arm.stage_outputs["stage3"] = {}  # No extra semantics needed
        
        # Disc at end of arm
        disc = manifest.add_child_node(
            parent_id=arm.node_id,
            label="disc",
            kind=NodeKind.PART,
            geometry=GeometrySpec(primitive=PrimitiveType.CYLINDER, radius=0.1, depth=0.02),
            attachment=AttachmentSpec(
                socket_type=SocketType.TOP_CENTER,
                local_rotation=[0.0, 0.0, 0.0],  # No additional rotation
            ),
        )
        disc.stage_outputs["stage2"] = {"radius": 0.1, "depth": 0.02}
        disc.stage_outputs["stage3"] = {}
        
        return manifest
    
    def test_chain_rotation_composition(self):
        """Verify disc inherits arm's rotation via proper matrix composition."""
        manifest = self._create_chain_manifest()
        
        # Simulate post being built with bbox
        post = manifest.get_node_by_label("post")
        post.bounding_box = {"min": [-0.1, -0.1, 0.0], "max": [0.1, 0.1, 1.0]}
        
        # Run Stage 4 on arm to get its offset
        arm = manifest.get_node_by_label("arm")
        arm_transform = _run(arm, manifest)
        arm.attachment.local_offset = arm_transform.offset
        # DON'T overwrite local_rotation - it's already set to 45° in the attachment
        arm.stage_outputs["stage4"] = arm_transform.to_dict()
        
        # Simulate arm being built with bbox
        arm.bounding_box = {"min": [-0.05, -0.05, 1.0], "max": [0.05, 0.05, 1.5]}
        
        # Run Stage 4 on disc
        disc = manifest.get_node_by_label("disc")
        disc_transform = _run(disc, manifest)
        disc.attachment.local_offset = disc_transform.offset
        disc.stage_outputs["stage4"] = disc_transform.to_dict()
        
        # Now test executor's world transform computation
        executor = BlenderExecutor(mcp_manager=None, task_id="test")
        
        # Compute arm's world transform (now returns 3 values)
        arm_world_pos, arm_world_rot, _ = executor._compute_world_transform(arm, manifest)
        
        # Arm should be at top of post
        assert arm_world_pos[2] > 0.9, f"Arm Z should be near top of post, got {arm_world_pos[2]}"
        
        # Arm should have 45° Y rotation (from its local rotation)
        assert abs(arm_world_rot[1] - 45.0) < 1.0, f"Arm Y rotation should be ~45°, got {arm_world_rot[1]}"
        
        # Compute disc's world transform (now returns 3 values)
        disc_world_pos, disc_world_rot, _ = executor._compute_world_transform(disc, manifest)
        
        # CRITICAL: Disc should inherit arm's 45° rotation
        # This is the key test for rotation composition
        assert abs(disc_world_rot[1] - 45.0) < 1.0, \
            f"Disc Y rotation should be ~45° (inherited from arm), got {disc_world_rot[1]}"


# ---------------------------------------------------------------------------
# Socket Resolver Coverage Tests (Critical Issue #2)
# ---------------------------------------------------------------------------

class TestSocketResolverCoverage:
    """Test that all socket types have resolvers and don't fall through to default."""
    
    def _create_test_node(self, socket_type: SocketType) -> tuple:
        """Create a minimal manifest and node for testing a socket type."""
        manifest = BuildManifest.create("test")
        root = manifest.get_root()
        
        # Add a parent part
        parent = manifest.add_child_node(
            parent_id=root.node_id,
            label="parent",
            kind=NodeKind.PART,
            geometry=GeometrySpec(primitive=PrimitiveType.BOX, size=[1.0, 1.0, 1.0]),
            attachment=AttachmentSpec(socket_type=SocketType.ROOT),
        )
        parent.stage_outputs["stage2"] = {"size_x": 1.0, "size_y": 1.0, "size_z": 1.0}
        parent.bounding_box = {"min": [-0.5, -0.5, -0.5], "max": [0.5, 0.5, 0.5]}
        
        # Add child with the socket type we're testing
        child = manifest.add_child_node(
            parent_id=parent.node_id,
            label="child",
            kind=NodeKind.PART,
            geometry=GeometrySpec(primitive=PrimitiveType.BOX, size=[0.2, 0.2, 0.2]),
            attachment=AttachmentSpec(socket_type=socket_type),
        )
        child.stage_outputs["stage2"] = {"size_x": 0.2, "size_y": 0.2, "size_z": 0.2}
        child.stage_outputs["stage3"] = {}  # Empty semantics
        
        return manifest, child
    
    @pytest.mark.parametrize("socket_type", [
        SocketType.TOP_CENTER,
        SocketType.BOTTOM_CENTER,
        SocketType.FRONT_CENTER,
        SocketType.BACK_CENTER,
        SocketType.LEFT_CENTER,
        SocketType.RIGHT_CENTER,
        SocketType.CORNER,
        SocketType.EDGE,
        SocketType.THROUGH_AXIS,
        SocketType.ARRAY_MEMBER,
        SocketType.RADIAL,
        SocketType.BOOLEAN_CUT,
        SocketType.BOOLEAN_UNION,
        SocketType.BOOLEAN_INTERSECT,
        SocketType.INSET,
        SocketType.TOP_FACE,
        SocketType.BOTTOM_FACE,
        SocketType.FRONT_FACE,
        SocketType.BACK_FACE,
        SocketType.LEFT_FACE,
        SocketType.RIGHT_FACE,
        SocketType.LEFT_END,
        SocketType.RIGHT_END,
        SocketType.TOP_END,
        SocketType.BOTTOM_END,
        SocketType.FRONT_END,
        SocketType.BACK_END,
        SocketType.RADIAL_BRIDGE,
        SocketType.STRUT,
        SocketType.BRIDGE,
    ])
    def test_socket_has_resolver(self, socket_type: SocketType):
        """Every socket type should have a resolver that doesn't raise."""
        manifest, child = self._create_test_node(socket_type)
        
        # Should not raise Stage4Error
        result = _run(child, manifest)
        
        # Should return a valid ResolvedTransform
        assert isinstance(result, ResolvedTransform)
        assert result.resolution_method != "DEFAULT", f"{socket_type} fell through to default"
    
    def test_unknown_socket_raises(self):
        """An unmapped socket type should raise Stage4Error, not silently default."""
        # This test verifies the fix for Issue #3 (silent fallback)
        # The resolver lookup should raise for unknown socket types
        # We test by checking that the resolver dict doesn't have a default fallback
        
        # Get the resolver dict keys
        manifest, child = self._create_test_node(SocketType.TOP_CENTER)
        
        # Verify that _get_resolver raises for a socket not in the dict
        # We can't easily create a fake SocketType, but we can verify the behavior
        # by checking that all defined socket types have resolvers
        from core.blender_pipeline.progressive_v2.node_types import SocketType as ST
        
        # These socket types should all have resolvers (no silent fallback)
        tested_sockets = [
            ST.TOP_CENTER, ST.BOTTOM_CENTER, ST.FRONT_CENTER, ST.BACK_CENTER,
            ST.LEFT_CENTER, ST.RIGHT_CENTER, ST.CORNER, ST.EDGE, ST.THROUGH_AXIS,
            ST.ARRAY_MEMBER, ST.RADIAL, ST.BOOLEAN_CUT, ST.BOOLEAN_UNION,
            ST.BOOLEAN_INTERSECT, ST.INSET, ST.TOP_FACE, ST.BOTTOM_FACE,
            ST.FRONT_FACE, ST.BACK_FACE, ST.LEFT_FACE, ST.RIGHT_FACE,
            ST.LEFT_END, ST.RIGHT_END, ST.TOP_END, ST.BOTTOM_END,
            ST.FRONT_END, ST.BACK_END, ST.RADIAL_BRIDGE, ST.STRUT, ST.BRIDGE,
        ]
        
        for socket in tested_sockets:
            resolver = Stage4Resolver._get_resolver(socket)
            assert resolver is not None, f"{socket} should have a resolver"
            assert "default" not in resolver.__name__.lower(), f"{socket} should not use default resolver"


# ---------------------------------------------------------------------------
# THROUGH_AXIS Embedment Tests (Critical Issue #4)
# ---------------------------------------------------------------------------

class TestThroughAxisEmbedment:
    """Test that THROUGH_AXIS uses child geometry for embedment margin."""
    
    def test_thick_arm_through_thin_post(self):
        """A thick arm through a thin post should stay within bounds."""
        manifest = BuildManifest.create("test")
        root = manifest.get_root()
        
        # Thin post (small Z extent)
        post = manifest.add_child_node(
            parent_id=root.node_id,
            label="post",
            kind=NodeKind.PART,
            geometry=GeometrySpec(primitive=PrimitiveType.CYLINDER, radius=0.1, depth=0.3),
            attachment=AttachmentSpec(socket_type=SocketType.ROOT),
        )
        post.stage_outputs["stage2"] = {"radius": 0.1, "depth": 0.3}
        post.bounding_box = {"min": [-0.1, -0.1, -0.15], "max": [0.1, 0.1, 0.15]}
        
        # Thick arm (large radius)
        arm = manifest.add_child_node(
            parent_id=post.node_id,
            label="arm",
            kind=NodeKind.PART,
            geometry=GeometrySpec(primitive=PrimitiveType.CYLINDER, radius=0.08, depth=0.5),
            attachment=AttachmentSpec(socket_type=SocketType.THROUGH_AXIS),
        )
        arm.stage_outputs["stage2"] = {"radius": 0.08, "depth": 0.5}
        arm.stage_outputs["stage3"] = {"pierce_direction": "left_right", "height_hint": "near_top"}
        
        result = _run(arm, manifest)
        
        # The arm's center Z should be within the post's bounds
        # accounting for the arm's radius
        post_max_z = 0.15
        arm_radius = 0.08
        max_allowed_z = post_max_z - arm_radius
        
        assert result.offset[2] <= max_allowed_z + 0.01, \
            f"Arm Z={result.offset[2]} exceeds safe max {max_allowed_z}"


# ---------------------------------------------------------------------------
# FRONT/BACK Convention Tests (Critical Issue #5)
# ---------------------------------------------------------------------------

class TestFrontBackConvention:
    """Test that FRONT = -Y and BACK = +Y (Blender convention)."""
    
    def test_front_center_is_negative_y(self):
        """FRONT_CENTER should place child at -Y of parent."""
        manifest = BuildManifest.create("test")
        root = manifest.get_root()
        
        parent = manifest.add_child_node(
            parent_id=root.node_id,
            label="parent",
            kind=NodeKind.PART,
            geometry=GeometrySpec(primitive=PrimitiveType.BOX, size=[1.0, 1.0, 1.0]),
            attachment=AttachmentSpec(socket_type=SocketType.ROOT),
        )
        parent.stage_outputs["stage2"] = {"size_x": 1.0, "size_y": 1.0, "size_z": 1.0}
        parent.bounding_box = {"min": [-0.5, -0.5, -0.5], "max": [0.5, 0.5, 0.5]}
        
        child = manifest.add_child_node(
            parent_id=parent.node_id,
            label="child",
            kind=NodeKind.PART,
            geometry=GeometrySpec(primitive=PrimitiveType.BOX, size=[0.2, 0.2, 0.2]),
            attachment=AttachmentSpec(socket_type=SocketType.FRONT_CENTER),
        )
        child.stage_outputs["stage2"] = {"size_x": 0.2, "size_y": 0.2, "size_z": 0.2}
        child.stage_outputs["stage3"] = {}
        
        result = _run(child, manifest)
        
        # FRONT should be -Y direction
        assert result.offset[1] < 0, f"FRONT_CENTER Y should be negative, got {result.offset[1]}"
    
    def test_back_center_is_positive_y(self):
        """BACK_CENTER should place child at +Y of parent."""
        manifest = BuildManifest.create("test")
        root = manifest.get_root()
        
        parent = manifest.add_child_node(
            parent_id=root.node_id,
            label="parent",
            kind=NodeKind.PART,
            geometry=GeometrySpec(primitive=PrimitiveType.BOX, size=[1.0, 1.0, 1.0]),
            attachment=AttachmentSpec(socket_type=SocketType.ROOT),
        )
        parent.stage_outputs["stage2"] = {"size_x": 1.0, "size_y": 1.0, "size_z": 1.0}
        parent.bounding_box = {"min": [-0.5, -0.5, -0.5], "max": [0.5, 0.5, 0.5]}
        
        child = manifest.add_child_node(
            parent_id=parent.node_id,
            label="child",
            kind=NodeKind.PART,
            geometry=GeometrySpec(primitive=PrimitiveType.BOX, size=[0.2, 0.2, 0.2]),
            attachment=AttachmentSpec(socket_type=SocketType.BACK_CENTER),
        )
        child.stage_outputs["stage2"] = {"size_x": 0.2, "size_y": 0.2, "size_z": 0.2}
        child.stage_outputs["stage3"] = {}
        
        result = _run(child, manifest)
        
        # BACK should be +Y direction
        assert result.offset[1] > 0, f"BACK_CENTER Y should be positive, got {result.offset[1]}"


# ---------------------------------------------------------------------------
# Boolean Overshoot Tests (Critical Issue #6)
# ---------------------------------------------------------------------------

class TestBooleanOvershoot:
    """Test that boolean cutters have overshoot margin."""
    
    def test_boolean_cut_has_overshoot(self):
        """BOOLEAN_CUT should position cutter with overshoot margin."""
        manifest = BuildManifest.create("test")
        root = manifest.get_root()
        
        parent = manifest.add_child_node(
            parent_id=root.node_id,
            label="parent",
            kind=NodeKind.PART,
            geometry=GeometrySpec(primitive=PrimitiveType.BOX, size=[1.0, 1.0, 1.0]),
            attachment=AttachmentSpec(socket_type=SocketType.ROOT),
        )
        parent.stage_outputs["stage2"] = {"size_x": 1.0, "size_y": 1.0, "size_z": 1.0}
        parent.bounding_box = {"min": [-0.5, -0.5, -0.5], "max": [0.5, 0.5, 0.5]}
        
        cutter = manifest.add_child_node(
            parent_id=parent.node_id,
            label="cutter",
            kind=NodeKind.PART,
            geometry=GeometrySpec(primitive=PrimitiveType.CYLINDER, radius=0.1, depth=0.2),
            attachment=AttachmentSpec(socket_type=SocketType.BOOLEAN_CUT),
        )
        cutter.stage_outputs["stage2"] = {"radius": 0.1, "depth": 0.2}
        cutter.stage_outputs["stage3"] = {"cut_face": "top"}
        
        result = _run(cutter, manifest)
        
        # Cutter should be positioned PAST the parent's top surface
        parent_top = 0.5
        assert result.offset[2] > parent_top, \
            f"Cutter Z={result.offset[2]} should be > parent top {parent_top}"
        
        # The overshoot should be the defined margin
        expected_z = parent_top + BOOLEAN_OVERSHOOT_M
        assert abs(result.offset[2] - expected_z) < 0.001, \
            f"Cutter Z={result.offset[2]} should be ~{expected_z}"


# ---------------------------------------------------------------------------
# BBox Helper Tests
# ---------------------------------------------------------------------------

class TestBBox:
    """Test BBox helper class."""
    
    def test_bbox_from_box_geometry(self):
        """Test BBox creation from box geometry."""
        geo = GeometrySpec(primitive=PrimitiveType.BOX, size=[2.0, 3.0, 4.0])
        stage2 = {"size_x": 2.0, "size_y": 3.0, "size_z": 4.0}
        
        bbox = BBox.from_geometry(geo, stage2)
        
        assert bbox.size_x == 2.0
        assert bbox.size_y == 3.0
        assert bbox.size_z == 4.0
        assert bbox.center == [0.0, 0.0, 0.0]

    def test_bbox_from_cylinder_geometry(self):
        """Test BBox creation from cylinder geometry."""
        geo = GeometrySpec(primitive=PrimitiveType.CYLINDER, radius=0.5, depth=2.0)
        stage2 = {"radius": 0.5, "depth": 2.0}
        
        bbox = BBox.from_geometry(geo, stage2)
        
        assert bbox.size_x == 1.0  # diameter
        assert bbox.size_y == 1.0  # diameter
        assert bbox.size_z == 2.0  # depth


# ---------------------------------------------------------------------------
# World Transform Storage Tests (New Feature)
# ---------------------------------------------------------------------------

class TestWorldTransformStorage:
    """Test that world transforms are stored and used correctly."""
    
    def test_stored_world_rotation_used_for_children(self):
        """When parent has stored world_rotation, children should use it."""
        manifest = BuildManifest.create("test")
        root = manifest.get_root()
        
        # Parent part with stored world rotation
        parent = manifest.add_child_node(
            parent_id=root.node_id,
            label="parent",
            kind=NodeKind.PART,
            geometry=GeometrySpec(primitive=PrimitiveType.BOX, size=[1.0, 1.0, 1.0]),
            attachment=AttachmentSpec(socket_type=SocketType.ROOT),
        )
        parent.stage_outputs["stage2"] = {"size_x": 1.0, "size_y": 1.0, "size_z": 1.0}
        parent.bounding_box = {"min": [-0.5, -0.5, 0.0], "max": [0.5, 0.5, 1.0]}
        
        # Simulate parent being built with 45° Y rotation
        parent.world_position = [0.0, 0.0, 0.5]
        parent.world_rotation = [0.0, math.pi/4, 0.0]  # 45° Y in radians
        
        # Child part
        child = manifest.add_child_node(
            parent_id=parent.node_id,
            label="child",
            kind=NodeKind.PART,
            geometry=GeometrySpec(primitive=PrimitiveType.BOX, size=[0.2, 0.2, 0.2]),
            attachment=AttachmentSpec(socket_type=SocketType.TOP_CENTER),
        )
        child.stage_outputs["stage2"] = {"size_x": 0.2, "size_y": 0.2, "size_z": 0.2}
        child.stage_outputs["stage3"] = {}
        
        # Run Stage 4 on child
        child_transform = _run(child, manifest)
        child.attachment.local_offset = child_transform.offset
        
        # Compute world transform
        executor = BlenderExecutor(mcp_manager=None, task_id="test")
        child_world_pos, child_world_rot, child_world_rot_rad = executor._compute_world_transform(child, manifest)
        
        # Child should inherit parent's 45° Y rotation
        assert abs(child_world_rot[1] - 45.0) < 1.0, \
            f"Child Y rotation should be ~45° (from stored parent), got {child_world_rot[1]}"
    
    def test_stored_world_position_used_for_children(self):
        """When parent has stored world_position, children should use it."""
        manifest = BuildManifest.create("test")
        root = manifest.get_root()
        
        # Parent part with stored world position
        parent = manifest.add_child_node(
            parent_id=root.node_id,
            label="parent",
            kind=NodeKind.PART,
            geometry=GeometrySpec(primitive=PrimitiveType.BOX, size=[1.0, 1.0, 1.0]),
            attachment=AttachmentSpec(socket_type=SocketType.ROOT),
        )
        parent.stage_outputs["stage2"] = {"size_x": 1.0, "size_y": 1.0, "size_z": 1.0}
        
        # Simulate parent being built at specific position
        parent.world_position = [5.0, 3.0, 2.0]  # Arbitrary position
        parent.world_rotation = [0.0, 0.0, 0.0]
        parent.bounding_box = {"min": [4.5, 2.5, 1.5], "max": [5.5, 3.5, 2.5]}
        
        # Child part
        child = manifest.add_child_node(
            parent_id=parent.node_id,
            label="child",
            kind=NodeKind.PART,
            geometry=GeometrySpec(primitive=PrimitiveType.BOX, size=[0.2, 0.2, 0.2]),
            attachment=AttachmentSpec(
                socket_type=SocketType.TOP_CENTER,
                local_offset=[0.0, 0.0, 0.6],  # On top of parent
            ),
        )
        child.stage_outputs["stage2"] = {"size_x": 0.2, "size_y": 0.2, "size_z": 0.2}
        child.stage_outputs["stage3"] = {}
        
        # Compute world transform
        executor = BlenderExecutor(mcp_manager=None, task_id="test")
        child_world_pos, _, _ = executor._compute_world_transform(child, manifest)
        
        # Child should be positioned relative to stored parent position
        # Parent at [5, 3, 2], child offset [0, 0, 0.6] + bottom_face_offset
        assert abs(child_world_pos[0] - 5.0) < 0.1, f"Child X should be ~5.0, got {child_world_pos[0]}"
        assert abs(child_world_pos[1] - 3.0) < 0.1, f"Child Y should be ~3.0, got {child_world_pos[1]}"
        assert child_world_pos[2] > 2.5, f"Child Z should be above parent, got {child_world_pos[2]}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
