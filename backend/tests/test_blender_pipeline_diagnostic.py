"""Blender pipeline diagnostic tests.

These tests PRINT what the pipeline actually computes so you can see
what's happening, not just whether it passed.

Run with: pytest tests/test_blender_pipeline_diagnostic.py -v -s

The -s flag is critical — it shows the print() output.
"""

import math
import pytest

from core.blender_pipeline.progressive_v2.manifest import (
    BuildManifest, GeometrySpec, AttachmentSpec,
)
from core.blender_pipeline.progressive_v2.node_types import (
    NodeKind, SocketType, PrimitiveType,
)
from core.blender_pipeline.progressive_v2.stages.stage4_resolver import (
    Stage4Resolver, BBox,
)
from core.blender_pipeline.progressive_v2.executor import (
    BlenderExecutor, _compose_rotations, _rotate_vector_by_euler,
)


def _add_part(manifest, parent_id, label, prim, socket, stage2, stage3=None, bbox=None):
    node = manifest.add_child_node(
        parent_id=parent_id,
        label=label,
        kind=NodeKind.PART,
        geometry=GeometrySpec(primitive=prim),
        attachment=AttachmentSpec(socket_type=socket),
    )
    node.stage_outputs["stage2"] = stage2
    if stage3:
        node.stage_outputs["stage3"] = stage3
    if bbox:
        node.bounding_box = bbox
    return node


def _run(node, manifest):
    """Unpack Stage4Resolver.run() tuple and return just the ResolvedTransform."""
    resolved, _ = Stage4Resolver.run(node, manifest)
    return resolved


# ---------------------------------------------------------------------------
# Diagnostic: table with 4 corner legs
# ---------------------------------------------------------------------------

class TestTableDiagnostic:
    """Shows exactly where each leg ends up. Run with -s to see output."""

    def test_table_leg_positions(self):
        manifest = BuildManifest.create("wooden table")

        tabletop = _add_part(
            manifest, manifest.root_node_id,
            "tabletop", PrimitiveType.BOX, SocketType.ROOT,
            {"size_x": 1.2, "size_y": 0.7, "size_z": 0.04},
            bbox={"min": [-0.6, -0.35, -0.02], "max": [0.6, 0.35, 0.02]},
        )

        corners = [
            ("leg_front_left",  "bottom_front_left"),
            ("leg_front_right", "bottom_front_right"),
            ("leg_back_left",   "bottom_back_left"),
            ("leg_back_right",  "bottom_back_right"),
        ]

        print("\n--- Table leg positions ---")
        print(f"Tabletop: 1.2m x 0.7m x 0.04m, bbox min={tabletop.bounding_box['min']}")

        for label, corner_pos in corners:
            leg = _add_part(
                manifest, tabletop.node_id,
                label, PrimitiveType.CYLINDER, SocketType.CORNER,
                {"radius": 0.03, "depth": 0.72},
                stage3={"corner_position": corner_pos},
            )
            t = _run(leg, manifest)
            print(
                f"  {label:20s} corner={corner_pos:25s} "
                f"offset=[{t.offset[0]:+.3f}, {t.offset[1]:+.3f}, {t.offset[2]:+.3f}]"
            )

            assert abs(t.offset[0]) > 0.3, \
                f"{label}: X={t.offset[0]:.3f} too small — leg not at corner"
            assert abs(t.offset[1]) > 0.1, \
                f"{label}: Y={t.offset[1]:.3f} too small — leg not at corner"
            assert t.offset[2] < 0, \
                f"{label}: Z={t.offset[2]:.3f} should be negative (leg hangs below tabletop)"

        print("--- All legs at correct corners ---\n")


# ---------------------------------------------------------------------------
# Diagnostic: rotation inheritance chain
# ---------------------------------------------------------------------------

class TestRotationChainDiagnostic:
    """Shows exactly how rotation propagates through a 3-level chain."""

    def test_rotation_chain_values(self):
        """Post, arm (45° tilt), disc — shows actual world rotations."""
        manifest = BuildManifest.create("rotation chain")

        _add_part(
            manifest, manifest.root_node_id,
            "post", PrimitiveType.CYLINDER, SocketType.ROOT,
            {"radius": 0.05, "depth": 1.0},
            bbox={"min": [-0.05, -0.05, 0.0], "max": [0.05, 0.05, 1.0]},
        )

        arm = _add_part(
            manifest, manifest.get_node_by_label("post").node_id,
            "arm", PrimitiveType.CYLINDER, SocketType.TOP_CENTER,
            {"radius": 0.03, "depth": 0.4},
            stage3={},
        )
        arm_t = _run(arm, manifest)
        arm.attachment.local_offset = arm_t.offset
        arm.attachment.local_rotation = [0.0, 45.0, 0.0]  # 45° tilt
        arm.stage_outputs["stage4"] = arm_t.to_dict()
        arm.bounding_box = {
            "min": [-0.03, -0.03, arm_t.offset[2] - 0.2],
            "max": [0.03, 0.03, arm_t.offset[2] + 0.2],
        }
        arm.world_position = arm_t.offset
        arm.world_rotation = [0.0, math.radians(45.0), 0.0]

        disc = _add_part(
            manifest, arm.node_id,
            "disc", PrimitiveType.CYLINDER, SocketType.TOP_CENTER,
            {"radius": 0.08, "depth": 0.02},
            stage3={},
        )
        disc_t = _run(disc, manifest)
        disc.attachment.local_offset = disc_t.offset

        executor = BlenderExecutor(mcp_manager=None, task_id="diag")
        arm_pos, arm_rot_deg, _ = executor._compute_world_transform(arm, manifest)
        disc_pos, disc_rot_deg, _ = executor._compute_world_transform(disc, manifest)

        print("\n--- Rotation chain ---")
        print(f"  post:  pos=[0,0,0]  rot=[0,0,0]")
        print(f"  arm:   pos=[{arm_pos[0]:+.3f}, {arm_pos[1]:+.3f}, {arm_pos[2]:+.3f}]  "
              f"rot=[{arm_rot_deg[0]:.1f}, {arm_rot_deg[1]:.1f}, {arm_rot_deg[2]:.1f}]°")
        print(f"  disc:  pos=[{disc_pos[0]:+.3f}, {disc_pos[1]:+.3f}, {disc_pos[2]:+.3f}]  "
              f"rot=[{disc_rot_deg[0]:.1f}, {disc_rot_deg[1]:.1f}, {disc_rot_deg[2]:.1f}]°")
        print(f"  Expected: disc inherits arm's 45° Y rotation")

        assert abs(arm_rot_deg[1] - 45.0) < 1.0, \
            f"Arm Y rotation should be 45°, got {arm_rot_deg[1]:.1f}°"
        assert abs(disc_rot_deg[1] - 45.0) < 1.0, \
            f"Disc should inherit arm's 45° Y rotation, got {disc_rot_deg[1]:.1f}°\n" \
            f"  Rotation composition is broken — disc not inheriting parent rotation"
        print("--- Rotation inheritance correct ---\n")


# ---------------------------------------------------------------------------
# Diagnostic: THROUGH_AXIS arm on a post
# ---------------------------------------------------------------------------

class TestThroughAxisDiagnostic:
    """Shows where a THROUGH_AXIS arm ends up on a post."""

    def test_through_axis_position(self):
        manifest = BuildManifest.create("training dummy")

        _add_part(
            manifest, manifest.root_node_id,
            "post", PrimitiveType.CYLINDER, SocketType.ROOT,
            {"radius": 0.05, "depth": 1.7},
            bbox={"min": [-0.05, -0.05, -0.85], "max": [0.05, 0.05, 0.85]},
        )

        arm = _add_part(
            manifest, manifest.get_node_by_label("post").node_id,
            "arm", PrimitiveType.CYLINDER, SocketType.THROUGH_AXIS,
            {"radius": 0.025, "depth": 0.6},
            stage3={"pierce_direction": "left_right", "height_hint": "near_top"},
        )

        t = _run(arm, manifest)

        print("\n--- THROUGH_AXIS arm ---")
        print(f"  Post: radius=0.05m, depth=1.7m, bbox Z=[-0.85, 0.85]")
        print(f"  Arm:  radius=0.025m, depth=0.6m, pierce=left_right, height=near_top")
        print(f"  Resolved: offset=[{t.offset[0]:+.3f}, {t.offset[1]:+.3f}, {t.offset[2]:+.3f}]")
        print(f"            rotation=[{math.degrees(t.rotation[0]):.1f}, "
              f"{math.degrees(t.rotation[1]):.1f}, "
              f"{math.degrees(t.rotation[2]):.1f}]°")
        print(f"  Expected: ~90° Y rotation (left_right = horizontal), Z near top of post")

        assert abs(t.rotation[1] - math.pi / 2) < 0.05, \
            f"left_right should give ~90° Y rotation, got {math.degrees(t.rotation[1]):.1f}°"
        assert t.offset[2] > 0.3, \
            f"near_top hint: arm Z={t.offset[2]:.3f} should be in upper half of post"
        assert t.offset[2] < 0.85, \
            f"Arm Z={t.offset[2]:.3f} exceeds post top 0.85"

        print("--- THROUGH_AXIS correct ---\n")


# ---------------------------------------------------------------------------
# Diagnostic: ARRAY_MEMBER socket (ladder rungs)
# ---------------------------------------------------------------------------

class TestCustomSocketDiagnostic:
    """Shows that ARRAY_MEMBER socket spaces rungs evenly along the rail."""

    def test_ladder_rung_positions(self):
        manifest = BuildManifest.create("step ladder")

        rail = _add_part(
            manifest, manifest.root_node_id,
            "left_rail", PrimitiveType.BOX, SocketType.ROOT,
            {"size_x": 0.05, "size_y": 0.05, "size_z": 1.2},
            bbox={"min": [-0.025, -0.025, -0.6], "max": [0.025, 0.025, 0.6]},
        )

        # 3 rungs evenly spaced along Z axis: index 0, 1, 2 of 3
        rung_specs = [
            ("rung_bottom", 0),
            ("rung_middle", 1),
            ("rung_top",    2),
        ]

        print("\n--- Ladder rung positions (ARRAY_MEMBER socket) ---")
        results = []
        for label, idx in rung_specs:
            rung = _add_part(
                manifest, rail.node_id,
                label, PrimitiveType.BOX, SocketType.ARRAY_MEMBER,
                {"size_x": 0.35, "size_y": 0.03, "size_z": 0.03},
                stage3={"array_axis": "z", "array_count": 3, "array_index": idx},
            )
            t = _run(rung, manifest)
            print(
                f"  {label:15s} index={idx}  "
                f"got=[{t.offset[0]:+.3f}, {t.offset[1]:+.3f}, {t.offset[2]:+.3f}]"
            )
            results.append((label, idx, t.offset[2]))

        # Rungs must be ordered bottom < middle < top
        assert results[0][2] < results[1][2] < results[2][2], (
            f"Rungs not ordered bottom < middle < top: "
            f"Z values = {[r[2] for r in results]}"
        )
        # All rungs must stay within rail Z bounds [-0.6, 0.6]
        for label, _, z in results:
            assert -0.6 <= z <= 0.6, f"{label}: Z={z:.3f} outside rail bounds [-0.6, 0.6]"

        print("--- ARRAY_MEMBER rung ordering correct ---\n")
