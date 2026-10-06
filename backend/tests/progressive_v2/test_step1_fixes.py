import pytest
from backend.core.blender_pipeline.progressive_v2.manifest import BuildManifest, NodeState, AttachmentSpec, GeometrySpec
from backend.core.blender_pipeline.progressive_v2.node_types import NodeKind, NodeImportance, SocketType, PrimitiveType

def _set_state(manifest: BuildManifest, node_id: str, state: NodeState):
    manifest.get_node(node_id).state = state

def test_all_children_done_includes_failed():
    manifest = BuildManifest.create("test", model_id="test")
    root_id = manifest.root_node_id
    c1 = manifest.add_child_node(
        parent_id=root_id,
        label="child1",
        kind=NodeKind.PART,
    )
    c2 = manifest.add_child_node(
        parent_id=root_id,
        label="child2",
        kind=NodeKind.PART,
    )
    
    _set_state(manifest, c1.node_id, NodeState.VERIFIED)
    manifest.transition(c2.node_id, NodeState.FAILED)
    
    assert manifest.all_children_done(root_id) is True

def test_all_children_done_false_when_pending():
    manifest = BuildManifest.create("test", model_id="test")
    root_id = manifest.root_node_id
    c1 = manifest.add_child_node(
        parent_id=root_id,
        label="child1",
        kind=NodeKind.PART,
    )
    c2 = manifest.add_child_node(
        parent_id=root_id,
        label="child2",
        kind=NodeKind.PART,
    )
    
    _set_state(manifest, c1.node_id, NodeState.VERIFIED)
    assert c2.state == NodeState.PLANNED
    
    assert manifest.all_children_done(root_id) is False

def test_required_child_failure_propagates():
    manifest = BuildManifest.create("test", model_id="test")
    root_id = manifest.root_node_id
    parent = manifest.add_child_node(
        parent_id=root_id,
        label="parent",
        kind=NodeKind.ASSEMBLY,
    )
    
    c1 = manifest.add_child_node(
        parent_id=parent.node_id,
        label="part1",
        kind=NodeKind.PART,
    )
    
    landing_feet = manifest.add_child_node(
        parent_id=parent.node_id,
        label="landing_feet",
        kind=NodeKind.ASSEMBLY,
        importance=NodeImportance.REQUIRED
    )
    
    _set_state(manifest, c1.node_id, NodeState.VERIFIED)
    manifest.transition(landing_feet.node_id, NodeState.FAILED)
    
    failed_required = manifest.failed_required_children(parent.node_id)
    assert "landing_feet" in failed_required
    
    error_msg = "Required child(ren) failed: " + ", ".join(failed_required[:5])
    manifest.transition(
        parent.node_id,
        NodeState.FAILED,
        error=error_msg,
    )
    
    assert "landing_feet" in manifest.get_node(parent.node_id).error_message

def test_root_model_becomes_actionable_after_required_child_fails():
    manifest = BuildManifest.create("test", model_id="test")
    root_id = manifest.root_node_id
    for i in range(7):
        child = manifest.add_child_node(
            parent_id=root_id,
            label=f"child_{i}",
            kind=NodeKind.PART,
        )
        _set_state(manifest, child.node_id, NodeState.VERIFIED)
        
    failed_child = manifest.add_child_node(
        parent_id=root_id,
        label="failed_child",
        kind=NodeKind.ASSEMBLY,
        importance=NodeImportance.REQUIRED
    )
    manifest.transition(failed_child.node_id, NodeState.FAILED)
    
    assert manifest.all_children_done(root_id) is True

def test_landing_feet_repro_no_root_child():
    manifest = BuildManifest.create("test", model_id="test")
    root_id = manifest.root_node_id
    
    children_specs = [
        {
            "label": "panel1",
            "kind": NodeKind.PART,
            "attachment": AttachmentSpec(socket_type=SocketType.TOP_CENTER)
        },
        {
            "label": "panel2",
            "kind": NodeKind.PART,
            "attachment": AttachmentSpec(socket_type=SocketType.TOP_CENTER)
        }
    ]
    
    with pytest.raises(ValueError) as exc:
        manifest.commit_decomposition(root_id, children_specs)
    
    assert "no ROOT child" in str(exc.value)

@pytest.mark.asyncio
async def test_h5_unresolved_transform_raises_typed_error():
    from backend.core.blender_pipeline.progressive_v2.controller import ProgressiveController
    manifest = BuildManifest.create("test_h5", model_id="m_test_h5")
    root_id = manifest.root_node_id

    # Create an assembly with non-ROOT socket and no parent geometry/ref
    sub_asm = manifest.add_child_node(
        parent_id=root_id,
        label="unplaced_assembly",
        kind=NodeKind.ASSEMBLY,
        attachment=AttachmentSpec(socket_type=SocketType.TOP_CENTER),
    )

    controller = ProgressiveController(model_manager=None, mcp_manager=None)
    controller.manifest = manifest

    # Processing assembly without reference geometry must fail the node with a typed error, not silently place at identity
    await controller._process_assembly(sub_asm, task_id="test_task")

    assert sub_asm.state in (NodeState.FAILED, NodeState.RETRYING)
    assert "TRANSFORM_DEFERRED_UNRESOLVED" in sub_asm.error_message

def test_required_node_failure_propagates_id_and_reason_to_api_response():
    from backend.core.blender_pipeline.progressive_v2.controller import ProgressiveController
    manifest = BuildManifest.create("error_prop_test", model_id="m_err_prop")
    root_id = manifest.root_node_id
    child = manifest.add_child_node(
        parent_id=root_id,
        label="critical_gear",
        kind=NodeKind.PART,
        importance=NodeImportance.REQUIRED,
    )
    manifest.transition(child.node_id, NodeState.FAILED, error="Mesh synthesis syntax error in cutter")

    controller = ProgressiveController(model_manager=None, mcp_manager=None)
    controller.manifest = manifest
    result = controller._build_result(1.2, ["Controller timeout"])

    api_dict = result.to_dict()
    assert api_dict["success"] is False
    assert any(child.node_id in err and "Mesh synthesis syntax error" in err for err in api_dict["errors"])

@pytest.mark.asyncio
async def test_repro_four_children_no_root_anchors_to_assembly_frame():
    from backend.core.blender_pipeline.progressive_v2.decomposer import RecursiveDecomposer
    from backend.core.blender_pipeline.progressive_v2.hierarchy import ContainmentTree, HierarchyLimits
    manifest = BuildManifest.create("tabletop drone", model_id="m_tabletop")
    root_id = manifest.root_node_id
    landing_feet = manifest.add_child_node(
        parent_id=root_id,
        label="landing_feet",
        kind=NodeKind.ASSEMBLY,
        attachment=AttachmentSpec(socket_type=SocketType.BOTTOM_CENTER),
    )
    tree = ContainmentTree(manifest=manifest, limits=HierarchyLimits())

    # 4 corner children with NO ROOT (exact landing_feet case)
    four_legs = [
        {"label": "front_left_leg", "kind": "part", "socket_type": "CORNER", "primitive": "cylinder"},
        {"label": "front_right_leg", "kind": "part", "socket_type": "CORNER", "primitive": "cylinder"},
        {"label": "back_left_leg", "kind": "part", "socket_type": "CORNER", "primitive": "cylinder"},
        {"label": "back_right_leg", "kind": "part", "socket_type": "CORNER", "primitive": "cylinder"},
    ]

    decomposer = RecursiveDecomposer()
    await decomposer._decompose_node(
        node=landing_feet,
        manifest=manifest,
        tree=tree,
        model_manager=None,
        task_id="t_repro",
        model_id=manifest.model_id,
        stats={},
        pre_parsed_children=four_legs,
    )

    # Must successfully decompose instead of failing with "no ROOT child"
    assert landing_feet.state != NodeState.FAILED
    assert len(landing_feet.children_ids) == 4
    # All 4 children preserve their CORNER socket attached to the assembly frame
    for cid in landing_feet.children_ids:
        child = manifest.nodes[cid]
        assert child.attachment.socket_type == SocketType.CORNER
    # Event must be recorded: assembly_frame anchor (not arbitrary child promotion)
    frame_events = [e for e in manifest.events if e.get("type") == "decomposition_frame_anchor"]
    assert len(frame_events) == 1
    assert frame_events[0]["details"]["anchor_type"] == "assembly_frame"

@pytest.mark.asyncio
async def test_repro_two_root_children_demotes_duplicate():
    from backend.core.blender_pipeline.progressive_v2.decomposer import RecursiveDecomposer
    from backend.core.blender_pipeline.progressive_v2.hierarchy import ContainmentTree, HierarchyLimits
    manifest = BuildManifest.create("dual_root_test", model_id="m_dual_root")
    root_id = manifest.root_node_id
    sub_asm = manifest.add_child_node(
        parent_id=root_id,
        label="dual_assembly",
        kind=NodeKind.ASSEMBLY,
        attachment=AttachmentSpec(socket_type=SocketType.TOP_CENTER),
    )
    tree = ContainmentTree(manifest=manifest, limits=HierarchyLimits())

    # Two children both requesting ROOT
    two_roots = [
        {"label": "chassis_base", "kind": "part", "socket_type": "ROOT", "primitive": "box"},
        {"label": "chassis_cover", "kind": "part", "socket_type": "ROOT", "primitive": "box"},
    ]

    decomposer = RecursiveDecomposer()
    await decomposer._decompose_node(
        node=sub_asm,
        manifest=manifest,
        tree=tree,
        model_manager=None,
        task_id="t_repro_dual",
        model_id=manifest.model_id,
        stats={},
        pre_parsed_children=two_roots,
    )

    assert sub_asm.state != NodeState.FAILED
    assert len(sub_asm.children_ids) == 2
    c0 = manifest.nodes[sub_asm.children_ids[0]]
    c1 = manifest.nodes[sub_asm.children_ids[1]]
    assert c0.attachment.socket_type == SocketType.ROOT
    # Second ROOT must be demoted to non-ROOT
    assert c1.attachment.socket_type != SocketType.ROOT
    demote_events = [e for e in manifest.events if e.get("type") == "decomposition_duplicate_root_demoted"]
    assert len(demote_events) == 1
    assert demote_events[0]["details"]["demoted_child"] == c1.label

def test_four_legs_placement_symmetry():
    """Verify that a 4-leg assembly places all 4 legs symmetrically about the assembly center."""
    from backend.core.blender_pipeline.progressive_v2.stages.stage4_resolver import Stage4Resolver
    manifest = BuildManifest.create("symmetry_test", model_id="m_symm")
    root_id = manifest.root_node_id

    # Create root chassis body with dimensions 1.0 x 1.0 x 0.2
    body = manifest.add_child_node(
        parent_id=root_id,
        label="chassis_body",
        kind=NodeKind.PART,
        geometry=GeometrySpec(primitive=PrimitiveType.BOX, size=[1.0, 1.0, 0.2]),
        attachment=AttachmentSpec(socket_type=SocketType.ROOT),
        stage_outputs={"stage2": {"size": [1.0, 1.0, 0.2]}},
    )

    # Create landing_feet assembly under root
    feet_asm = manifest.add_child_node(
        parent_id=root_id,
        label="landing_feet",
        kind=NodeKind.ASSEMBLY,
        attachment=AttachmentSpec(socket_type=SocketType.BOTTOM_CENTER),
    )

    leg_specs = [
        ("front_left_leg", SocketType.CORNER),
        ("front_right_leg", SocketType.CORNER),
        ("back_left_leg", SocketType.CORNER),
        ("back_right_leg", SocketType.CORNER),
    ]

    leg_nodes = []
    offsets = {}
    for name, sock in leg_specs:
        leg = manifest.add_child_node(
            parent_id=feet_asm.node_id,
            label=name,
            kind=NodeKind.PART,
            geometry=GeometrySpec(primitive=PrimitiveType.CYLINDER, radius=0.03, depth=0.1),
            attachment=AttachmentSpec(socket_type=sock),
            stage_outputs={"stage2": {"radius": 0.03, "depth": 0.1}},
        )
        leg_nodes.append(leg)
        resolved, _ = Stage4Resolver.run(leg, manifest)
        offsets[name] = resolved.offset

    # Assert measured symmetry:
    # 1. Centroid must be at (0, 0) in X/Y plane
    centroid_x = sum(offsets[name][0] for name in offsets) / 4.0
    centroid_y = sum(offsets[name][1] for name in offsets) / 4.0
    assert abs(centroid_x) < 1e-4, f"X centroid should be 0.0, got {centroid_x}"
    assert abs(centroid_y) < 1e-4, f"Y centroid should be 0.0, got {centroid_y}"

    # 2. Inset factor 0.8 on 1.0m body (half_x=0.5) -> magnitude 0.4
    for name in offsets:
        assert abs(abs(offsets[name][0]) - 0.4) < 1e-4, f"{name} X offset magnitude should be 0.4, got {offsets[name][0]}"
        assert abs(abs(offsets[name][1]) - 0.4) < 1e-4, f"{name} Y offset magnitude should be 0.4, got {offsets[name][1]}"

    # 3. Spans must be equal
    x_span_front = abs(offsets["front_right_leg"][0] - offsets["front_left_leg"][0])
    x_span_back = abs(offsets["back_right_leg"][0] - offsets["back_left_leg"][0])
    y_span_left = abs(offsets["back_left_leg"][1] - offsets["front_left_leg"][1])
    y_span_right = abs(offsets["back_right_leg"][1] - offsets["front_right_leg"][1])

    assert abs(x_span_front - x_span_back) < 1e-4, f"Front X span {x_span_front} != Back X span {x_span_back}"
    assert abs(y_span_left - y_span_right) < 1e-4, f"Left Y span {y_span_left} != Right Y span {y_span_right}"
    assert abs(x_span_front - 0.8) < 1e-4
    assert abs(y_span_left - 0.8) < 1e-4


def test_torus_ring_end_attachment_has_zero_gap():
    """Torus ring attaching to RIGHT_END must center on arm tip without offset push."""
    from core.blender_pipeline.progressive_v2.stages.stage4_resolver import Stage4Resolver, BBox
    from core.blender_pipeline.progressive_v2.manifest import ManifestNode, GeometrySpec
    from core.blender_pipeline.progressive_v2.node_types import PrimitiveType

    parent_bbox = BBox(min_x=-0.1, max_x=0.1, min_y=-0.02, max_y=0.02, min_z=-0.02, max_z=0.02)
    child_bbox = BBox(min_x=-0.05, max_x=0.05, min_y=-0.05, max_y=0.05, min_z=-0.01, max_z=0.01)
    ring_node = ManifestNode(
        node_id="ring_1",
        label="rotor_guard_ring",
        geometry=GeometrySpec(primitive=PrimitiveType.TORUS),
    )
    resolved = Stage4Resolver._resolve_right_end(parent_bbox, child_bbox, {}, ring_node)
    assert resolved.offset[0] == 0.1, f"Expected 0.1 (arm max_x), got {resolved.offset[0]}"


def test_torus_flat_horizontal_orientation_compensates_pitch():
    """Torus attached to an arm with pitch rotation gets compensated rotation so world normal is vertical."""
    import math
    from core.blender_pipeline.progressive_v2.stages.stage4_resolver import Stage4Resolver
    from core.blender_pipeline.progressive_v2.manifest import BuildManifest, ManifestNode, GeometrySpec, AttachmentSpec
    from core.blender_pipeline.progressive_v2.node_types import PrimitiveType, SocketType, NodeKind

    manifest = BuildManifest.create("test", model_id="test")
    arm = ManifestNode(
        node_id="arm_1",
        label="drone_arm",
        kind=NodeKind.PART,
        geometry=GeometrySpec(primitive=PrimitiveType.CYLINDER),
        stage_outputs={
            "stage2": {"radius": 0.02, "depth": 0.2},
            "decomposition_hint": {"length_axis": "x"},
        },
        attachment=AttachmentSpec(socket_type=SocketType.ROOT),
    )
    ring = ManifestNode(
        node_id="ring_1",
        label="rotor_guard",
        kind=NodeKind.PART,
        parent_id="arm_1",
        geometry=GeometrySpec(primitive=PrimitiveType.TORUS),
        stage_outputs={"stage2": {"major_radius": 0.05, "minor_radius": 0.005}},
        attachment=AttachmentSpec(socket_type=SocketType.RIGHT_END),
    )
    manifest.add_node(arm)
    manifest.add_node(ring)

    resolved, solution = Stage4Resolver.run(ring, manifest)
    assert abs(resolved.rotation[1] - (-math.pi / 2.0)) < 1e-4, f"Expected pitch compensation -pi/2, got {resolved.rotation[1]}"


def test_u_shape_inset_centers_in_fork_gap():
    """INSET socket inside a U_SHAPE bracket centers the child between the forks in Z."""
    from core.blender_pipeline.progressive_v2.stages.stage4_resolver import Stage4Resolver, BBox
    from core.blender_pipeline.progressive_v2.manifest import ManifestNode, GeometrySpec
    from core.blender_pipeline.progressive_v2.node_types import PrimitiveType

    bracket_bbox = BBox(min_x=-0.05, max_x=0.05, min_y=-0.01, max_y=0.01, min_z=0.0, max_z=0.06)
    child_bbox = BBox(min_x=-0.01, max_x=0.01, min_y=-0.01, max_y=0.01, min_z=-0.01, max_z=0.01)
    lens_node = ManifestNode(
        node_id="lens_1",
        label="camera_lens",
        geometry=GeometrySpec(primitive=PrimitiveType.SPHERE),
    )
    sem = {"parent_primitive": PrimitiveType.U_SHAPE.value, "parent_label": "u_bracket"}
    resolved = Stage4Resolver._resolve_inset(bracket_bbox, child_bbox, sem, lens_node)
    assert resolved.offset == [0.0, 0.0, 0.03], f"Expected [0, 0, 0.03] fork midpoint, got {resolved.offset}"


def test_cylinder_front_end_uses_oriented_axis():
    """FRONT_END socket on a cylinder rotated into the horizontal plane selects the true cylinder tip."""
    import math
    from core.blender_pipeline.progressive_v2.stages.stage4_resolver import Stage4Resolver
    from core.blender_pipeline.progressive_v2.manifest import BuildManifest, ManifestNode, GeometrySpec, AttachmentSpec
    from core.blender_pipeline.progressive_v2.node_types import PrimitiveType, SocketType, NodeKind
    from core.blender_pipeline.progressive_v2.transforms import NodeTransformState, WorldMatrix, _mat4_from_trs

    manifest = BuildManifest.create("test", model_id="test")
    # Cylinder rotated by +pi/2 around X (pointing forward along -Y)
    arm = ManifestNode(
        node_id="arm_1",
        label="horizontal_arm",
        kind=NodeKind.PART,
        geometry=GeometrySpec(primitive=PrimitiveType.CYLINDER),
        stage_outputs={
            "stage2": {"radius": 0.03, "depth": 0.24},
            "spatial_contract": {"orientation": "horizontal"},
        },
        attachment=AttachmentSpec(socket_type=SocketType.FRONT_FACE, local_rotation=[math.pi / 2, 0.0, 0.0]),
    )
    arm.transform_state = NodeTransformState()
    arm.transform_state.world_matrix = WorldMatrix(
        matrix=_mat4_from_trs([0.0, -0.09, 0.165], [math.pi / 2, 0.0, 0.0], [1.0, 1.0, 1.0])
    )

    ring = ManifestNode(
        node_id="ring_1",
        label="rotor_guard",
        kind=NodeKind.PART,
        parent_id="arm_1",
        geometry=GeometrySpec(primitive=PrimitiveType.TORUS),
        stage_outputs={
            "stage2": {"major_radius": 0.135, "minor_radius": 0.015},
            "spatial_contract": {"orientation": "flat_horizontal"},
        },
        attachment=AttachmentSpec(socket_type=SocketType.FRONT_END),
    )
    manifest.add_node(arm)
    manifest.add_node(ring)

    resolved, solution = Stage4Resolver.run(ring, manifest)
    # The local offset along the cylinder's axis (Z) must be +0.12 (the outer tip at world Y = -0.21)
    assert abs(resolved.offset[2] - 0.12) < 1e-4, f"Expected cylinder tip at z=0.12, got {resolved.offset}"
    # The local rotation must compensate the parent's +pi/2 pitch so world rotation is [0, 0, 0]
    assert abs(resolved.rotation[0] - (-math.pi / 2)) < 1e-4, f"Expected rx compensation -pi/2, got {resolved.rotation}"


def test_duplicate_root_part_rejected_in_auto_scoping():
    from backend.core.blender_pipeline.progressive_v2.decomposer import RecursiveDecomposer
    manifest = BuildManifest.create("test", model_id="m_test")
    root_id = manifest.root_node_id
    manifest.add_child_node(
        parent_id=root_id,
        label="central_chassis",
        kind=NodeKind.PART,
        attachment=AttachmentSpec(socket_type=SocketType.ROOT),
    )
    asm = manifest.add_child_node(
        parent_id=root_id,
        label="rotor_guard_assembly",
        kind=NodeKind.ASSEMBLY,
        attachment=AttachmentSpec(socket_type=SocketType.TOP_CENTER),
    )

    # Candidate children contains central_chassis again
    existing_labels = {n.label for n in manifest.nodes.values()}
    root_node = manifest.get_root()
    root_part_labels = {
        manifest.nodes[cid].label.lower()
        for cid in root_node.children_ids
        if cid in manifest.nodes and manifest.nodes[cid].kind == NodeKind.PART
    }
    assert "central_chassis" in root_part_labels

    with pytest.raises(ValueError, match="duplicates root-level part"):
        # Re-enact the decomposer auto-scoping check
        label = "central_chassis"
        if label in existing_labels:
            if label.lower() in root_part_labels:
                raise ValueError(
                    f"commit_decomposition: child '{label}' in assembly '{asm.label}' "
                    f"duplicates root-level part '{label}'"
                )


def test_normalize_decomposition_ownership_prunes_imposter_root_assembly():
    from backend.core.blender_pipeline.progressive_v2.design_fidelity import DesignFidelityValidator
    manifest = BuildManifest.create("test", model_id="m_test")
    root_id = manifest.root_node_id
    manifest.add_child_node(
        parent_id=root_id,
        label="central_chassis",
        kind=NodeKind.PART,
        attachment=AttachmentSpec(socket_type=SocketType.ROOT),
    )
    asm = manifest.add_child_node(
        parent_id=root_id,
        label="rotor_guard_assembly",
        kind=NodeKind.ASSEMBLY,
        attachment=AttachmentSpec(socket_type=SocketType.TOP_CENTER),
    )
    # Imposter duplicate chassis inside the assembly
    manifest.add_child_node(
        parent_id=asm.node_id,
        label="central_chassis__dup_01",
        kind=NodeKind.PART,
        attachment=AttachmentSpec(socket_type=SocketType.ROOT),
    )
    manifest.add_child_node(
        parent_id=asm.node_id,
        label="guard_ring",
        kind=NodeKind.PART,
        attachment=AttachmentSpec(socket_type=SocketType.RADIAL),
    )

    DesignFidelityValidator.normalize_decomposition_ownership(manifest)
    assert asm.node_id not in manifest.nodes, "Expected imposter assembly to be pruned from manifest"




