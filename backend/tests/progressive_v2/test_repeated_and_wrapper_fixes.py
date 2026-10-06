from __future__ import annotations

import math
import pytest
from core.blender_pipeline.progressive_v2.manifest import (
    AttachmentSpec,
    BuildManifest,
    GeometrySpec,
    ManifestNode,
)
from core.blender_pipeline.progressive_v2.node_types import (
    NodeKind,
    PrimitiveType,
    SocketType,
)
from core.blender_pipeline.progressive_v2.repair import ScenePlanRepairer
from core.blender_pipeline.progressive_v2.transaction import SceneTransactionCompiler
from core.blender_pipeline.progressive_v2.stages.stage4_resolver import BBox, Stage4Resolver
from core.blender_pipeline.progressive_v2.decomposer import RecursiveDecomposer


def test_single_array_member_repaired_and_validated():
    """A single ARRAY_MEMBER child must receive array_count=1, array_index=0 and pass validation."""
    manifest = BuildManifest.create("test assembly with single array member")
    root = manifest.get_root()
    manifest.add_child_node(
        root.node_id,
        "base_part",
        NodeKind.PART,
        geometry=GeometrySpec(primitive=PrimitiveType.BOX, size=[1, 1, 1]),
        attachment=AttachmentSpec(socket_type=SocketType.ROOT),
    )
    array_child = manifest.add_child_node(
        root.node_id,
        "array_child",
        NodeKind.PART,
        geometry=GeometrySpec(primitive=PrimitiveType.CYLINDER, radius=0.1, depth=0.5),
        attachment=AttachmentSpec(socket_type=SocketType.ARRAY_MEMBER),
    )

    # Before repair, slots are None
    assert array_child.attachment.array_index is None
    assert array_child.attachment.array_count is None

    # Apply repair
    report = ScenePlanRepairer.apply(manifest)
    assert report["repair_count"] >= 1
    assert array_child.attachment.array_index == 0
    assert array_child.attachment.array_count == 1

    # Transaction validation must pass without errors
    compiler = SceneTransactionCompiler(None, manifest)
    errors = compiler._repeated_slot_errors()
    assert errors == []


def test_single_radial_assembly_receives_stable_slots():
    """An assembly with a single RADIAL socket receives radial_count=1, radial_index=0."""
    manifest = BuildManifest.create("test model with radial assembly")
    root = manifest.get_root()
    chassis = manifest.add_child_node(
        root.node_id,
        "chassis",
        NodeKind.PART,
        geometry=GeometrySpec(primitive=PrimitiveType.SPHERE, radius=0.5),
        attachment=AttachmentSpec(socket_type=SocketType.ROOT),
    )
    arm_asm = manifest.add_child_node(
        root.node_id,
        "arm_assembly",
        NodeKind.ASSEMBLY,
        attachment=AttachmentSpec(socket_type=SocketType.RADIAL),
    )

    report = ScenePlanRepairer.apply(manifest)
    assert arm_asm.attachment.radial_index == 0
    assert arm_asm.attachment.radial_count == 1

    compiler = SceneTransactionCompiler(None, manifest)
    assert compiler._repeated_slot_errors() == []


def test_redundant_same_named_wrapper_unwrapped():
    """When decomposer response wraps children in a same-named container, unwrap it directly."""
    decomposer = RecursiveDecomposer()
    manifest = BuildManifest.create("drone with rotor guards")
    root = manifest.get_root()
    guard_asm = manifest.add_child_node(
        root.node_id,
        "rotor_guard_assembly",
        NodeKind.ASSEMBLY,
        attachment=AttachmentSpec(socket_type=SocketType.ROOT),
    )

    # Simulating LLM returning a redundant wrapper
    llm_response = '''{
      "is_simple": false,
      "children": [
        {
          "label": "rotor_guard_assembly",
          "kind": "assembly",
          "socket_type": "ROOT",
          "children": [
            {"label": "guard_ring_1", "kind": "part", "primitive": "torus", "socket_type": "RADIAL", "radial_count": 4, "radial_index": 0},
            {"label": "guard_ring_2", "kind": "part", "primitive": "torus", "socket_type": "RADIAL", "radial_count": 4, "radial_index": 1}
          ]
        }
      ]
    }'''

    res = decomposer._parse_decomposition_response(llm_response, guard_asm, manifest)
    assert res.success is True
    assert len(res.children) == 2
    assert res.children[0].label == "guard_ring_1"
    assert res.children[1].label == "guard_ring_2"
    assert res.children[0].primitive == PrimitiveType.TORUS


def test_radial_elongated_cylinder_oriented_horizontally():
    """An elongated cylinder placed radially in XY plane must be pitched 90 deg into the horizontal plane."""
    parent = BBox(min_x=-0.1, max_x=0.1, min_y=-0.1, max_y=0.1, min_z=-0.1, max_z=0.1)
    # Cylinder depth 0.2m, radius 0.02m (depth along Z)
    arm_child = BBox(min_x=-0.02, max_x=0.02, min_y=-0.02, max_y=0.02, min_z=-0.1, max_z=0.1)
    node = ManifestNode(
        node_id="arm_1",
        label="arm_1",
        kind=NodeKind.PART,
        geometry=GeometrySpec(primitive=PrimitiveType.CYLINDER, radius=0.02, depth=0.2),
        attachment=AttachmentSpec(socket_type=SocketType.RADIAL),
    )

    resolved = Stage4Resolver._resolve_radial(
        parent, arm_child, {"radial_count": 4, "radial_index": 0, "radial_plane": "xy"}, node
    )

    # Rotation should have pitch ~1.5708 (90 deg) so local Z lies in XY plane
    assert abs(resolved.rotation[1] - math.pi / 2) < 1e-5
    # Radius extends outward from parent surface (0.1m) + half cylinder depth (0.1m) = 0.2m
    assert abs(resolved.offset[0] - 0.2) < 1e-5
    assert abs(resolved.offset[1]) < 1e-5
    assert abs(resolved.offset[2]) < 1e-5
