from __future__ import annotations

from core.blender_pipeline.progressive_v2.manifest import AttachmentSpec, BuildManifest, GeometrySpec
from core.blender_pipeline.progressive_v2.node_types import NodeKind, PrimitiveType, SocketType
from core.blender_pipeline.progressive_v2.scene_quality import ProductionSceneAudit
from core.blender_pipeline.progressive_v2.constraint_planner import StructuralConstraintPlanner
from core.blender_pipeline.progressive_v2.design_fidelity import DesignFidelityValidator


def _manifest():
    manifest = BuildManifest.create("a generic assembly with a horizontal member")
    root = manifest.get_root()
    base = manifest.add_child_node(
        root.node_id, "base", NodeKind.PART,
        geometry=GeometrySpec(primitive=PrimitiveType.BOX, size=[1, 1, 1]),
        attachment=AttachmentSpec(socket_type=SocketType.ROOT),
    )
    member = manifest.add_child_node(
        root.node_id, "member", NodeKind.PART,
        geometry=GeometrySpec(primitive=PrimitiveType.CYLINDER, radius=.1, depth=.5),
        attachment=AttachmentSpec(socket_type=SocketType.RIGHT_FACE, reference_node_id=base.node_id),
    )
    member.stage_outputs["spatial_contract"] = {"orientation": "horizontal"}
    return manifest, base.node_id, member.node_id


def _item(node_id, minimum, maximum, dimensions):
    return {
        "node_id": node_id,
        "world_bounds": {"min": minimum, "max": maximum},
        "dimensions": dimensions,
    }


def test_scene_audit_accepts_connected_declared_orientation(tmp_path):
    manifest, base_id, member_id = _manifest()
    manifest.builds_dir = tmp_path
    readback = {"objects": [
        _item(base_id, [-.5, -.5, -.5], [.5, .5, .5], [1, 1, 1]),
        _item(member_id, [.5, -.1, -.1], [1.0, .1, .1], [.5, .2, .2]),
    ]}
    assert ProductionSceneAudit.run(manifest, readback)["ok"] is True


def test_scene_audit_rejects_disconnected_component(tmp_path):
    manifest, base_id, member_id = _manifest()
    manifest.builds_dir = tmp_path
    readback = {"objects": [
        _item(base_id, [-.5, -.5, -.5], [.5, .5, .5], [1, 1, 1]),
        _item(member_id, [2.0, -.1, -.1], [2.5, .1, .1], [.5, .2, .2]),
    ]}
    report = ProductionSceneAudit.run(manifest, readback)
    assert report["ok"] is False
    assert {finding["code"] for finding in report["findings"]} == {
        "disconnected_component", "declared_attachment_gap",
    }


def test_scene_audit_rejects_vertical_geometry_declared_horizontal(tmp_path):
    manifest, base_id, member_id = _manifest()
    manifest.builds_dir = tmp_path
    readback = {"objects": [
        _item(base_id, [-.5, -.5, -.5], [.5, .5, .5], [1, 1, 1]),
        _item(member_id, [.4, -.1, -.1], [.6, .1, .4], [.2, .2, .5]),
    ]}
    report = ProductionSceneAudit.run(manifest, readback)
    assert report["ok"] is False
    assert "orientation_contract_failed" in {
        finding["code"] for finding in report["findings"]
    }


def test_declared_disconnection_is_explicit_exception(tmp_path):
    manifest, base_id, member_id = _manifest()
    manifest.builds_dir = tmp_path
    manifest.nodes[member_id].attachment.allow_disconnected = True
    readback = {"objects": [
        _item(base_id, [-.5, -.5, -.5], [.5, .5, .5], [1, 1, 1]),
        _item(member_id, [2.0, -.1, -.1], [2.5, .1, .1], [.5, .2, .2]),
    ]}
    assert ProductionSceneAudit.run(manifest, readback)["ok"] is True


def test_controller_runs_readback_and_quality_before_ground_lift():
    from core.blender_pipeline.progressive_v2 import controller as controller_mod
    source = __import__("pathlib").Path(controller_mod.__file__).read_text(encoding="utf-8")
    readback = source.index("SceneReadbackVerifier(self.mcp_manager).verify")
    quality = source.index("ProductionSceneAudit.run")
    lift = source.index("await self._lift_to_ground_plane(task_id)")
    assert readback < quality < lift


def test_flat_annular_group_propagates_orientation_without_model_names():
    manifest = BuildManifest.create(
        "make a flat horizontal torus enclosure with three tapered members inside"
    )
    root = manifest.get_root()
    group = manifest.add_child_node(root.node_id, "rotating_group", NodeKind.ASSEMBLY)
    ring = manifest.add_child_node(
        group.node_id, "annular_enclosure", NodeKind.PART,
        geometry=GeometrySpec(primitive=PrimitiveType.TORUS, major_radius=.2, minor_radius=.02),
    )
    hub = manifest.add_child_node(
        group.node_id, "central_member", NodeKind.PART,
        geometry=GeometrySpec(primitive=PrimitiveType.CYLINDER, radius=.03, depth=.02),
        attachment=AttachmentSpec(socket_type=SocketType.FRONT_FACE),
    )
    members = [
        manifest.add_child_node(
            group.node_id, f"tapered_member_{index}", NodeKind.PART,
            geometry=GeometrySpec(primitive=PrimitiveType.CONE, radius=.02, depth=.12),
            attachment=AttachmentSpec(socket_type=SocketType.TOP_CENTER),
        )
        for index in range(3)
    ]
    StructuralConstraintPlanner.apply(manifest)
    assert ring.stage_outputs["spatial_contract"]["orientation"] == "flat_horizontal"
    assert all(
        member.stage_outputs["spatial_contract"]["orientation"] == "flat_horizontal"
        and member.stage_outputs["decomposition_hint"]["length_axis"] == "x"
        for member in members
    )
    assert all(member.attachment.socket_type == SocketType.BRIDGE for member in members)
    assert all(member.attachment.connects_to == hub.label for member in members)


def test_component_count_uses_physical_synonyms():
    manifest = BuildManifest.create("add three tapered blades")
    root = manifest.get_root()
    for index in range(3):
        manifest.add_child_node(
            root.node_id, f"propeller_{index}", NodeKind.PART,
            geometry=GeometrySpec(primitive=PrimitiveType.CONE, radius=.01, depth=.1),
        )
    assert DesignFidelityValidator.validate(manifest) == []


def test_root_duplicate_ownership_prefers_complete_primary_assembly():
    manifest = BuildManifest.create("generic machine")
    root = manifest.get_root()
    primary = manifest.add_child_node(
        root.node_id, "body_assembly", NodeKind.ASSEMBLY,
        attachment=AttachmentSpec(socket_type=SocketType.ROOT),
    )
    manifest.add_child_node(
        primary.node_id, "sensor", NodeKind.PART,
        geometry=GeometrySpec(primitive=PrimitiveType.CYLINDER, radius=.1, depth=.1),
        custom_props={"display_label": "sensor"},
    )
    duplicate = manifest.add_child_node(
        root.node_id, "sensor_duplicate", NodeKind.PART,
        geometry=GeometrySpec(primitive=PrimitiveType.CYLINDER, radius=.1, depth=.1),
        custom_props={"display_label": "sensor"},
    )
    report = DesignFidelityValidator.normalize_decomposition_ownership(manifest)
    assert duplicate.node_id in report["removed"]
    assert duplicate.node_id not in manifest.nodes


def test_missing_leaf_count_clones_leaf_not_container():
    manifest = BuildManifest.create("add two red indicator LEDs")
    root = manifest.get_root()
    body = manifest.add_child_node(root.node_id, "body_assembly", NodeKind.ASSEMBLY)
    manifest.add_child_node(
        body.node_id, "led_1", NodeKind.PART,
        geometry=GeometrySpec(primitive=PrimitiveType.SPHERE, radius=.01),
        attachment=AttachmentSpec(socket_type=SocketType.FRONT_FACE),
    )
    before = len(manifest.nodes)
    report = DesignFidelityValidator.repair_explicit_requirements(manifest)
    assert len(manifest.nodes) == before + 1
    assert report["repairs"][0]["mode"] == "paired_face_expansion"
    leds = [node for node in manifest.nodes.values() if node.kind == NodeKind.PART and "led" in node.label]
    assert {node.attachment.face_position for node in leds} == {"near_left", "near_right"}


def test_readback_boolean_cut_scoped_to_target_only():
    """Negative control: has_cuts must loosen dimensions ONLY on the cut target, not sibling parts."""
    from core.blender_pipeline.progressive_v2.readback import SceneReadbackVerifier
    manifest = BuildManifest.create("box with cutter and an uncut sibling")
    root = manifest.get_root()
    assembly = manifest.add_child_node(root.node_id, "asm", NodeKind.ASSEMBLY)
    target = manifest.add_child_node(
        assembly.node_id, "chassis", NodeKind.PART,
        geometry=GeometrySpec(primitive=PrimitiveType.BOX, size=[1.0, 1.0, 1.0]),
        attachment=AttachmentSpec(socket_type=SocketType.ROOT),
    )
    cutter = manifest.add_child_node(
        assembly.node_id, "slot_cutter", NodeKind.PART,
        geometry=GeometrySpec(primitive=PrimitiveType.BOX, size=[0.2, 0.2, 0.5]),
        attachment=AttachmentSpec(socket_type=SocketType.BOOLEAN_CUT),
    )
    uncut_sibling = manifest.add_child_node(
        assembly.node_id, "uncut_bracket", NodeKind.PART,
        geometry=GeometrySpec(primitive=PrimitiveType.BOX, size=[0.5, 0.5, 0.5]),
        attachment=AttachmentSpec(socket_type=SocketType.TOP_CENTER),
    )
    
    verifier = SceneReadbackVerifier(mcp_manager=None)
    
    # 1. Target (has cut) should allow smaller dimensions (cut reduces volume/extent)
    assert verifier._is_cut_target(target, manifest) is True
    # 2. Uncut sibling must NOT be considered a cut target
    assert verifier._is_cut_target(uncut_sibling, manifest) is False


def test_readback_oriented_dimensions_reject_permuted_axes():
    """Negative control: unsorted dimension check rejects a part whose axes are permuted (e.g. vertical blade declared horizontal)."""
    from core.blender_pipeline.progressive_v2.readback import SceneReadbackVerifier
    verifier = SceneReadbackVerifier(mcp_manager=None)
    
    # Expected: [length=0.4, width=0.04, thickness=0.01] (e.g. flat horizontal blade along X)
    expected = [0.4, 0.04, 0.01]
    
    # Matching actual
    matching_actual = [0.4, 0.04, 0.01]
    assert verifier._dimensions_match(expected, matching_actual) is True
    
    # Permuted actual: [0.01, 0.04, 0.4] (standing upright along Z)
    # The old sorted check accepted this because sorted([0.01, 0.04, 0.4]) == sorted([0.4, 0.04, 0.01])!
    # Strict oriented check MUST reject this.
    permuted_actual = [0.01, 0.04, 0.4]
    assert verifier._dimensions_match(expected, permuted_actual) is False

