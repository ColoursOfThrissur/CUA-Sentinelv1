"""Focused tests for frozen scene-plan transaction compilation."""

import asyncio
from types import SimpleNamespace as NS

from core.blender_pipeline.progressive_v2.node_types import NodeKind, SocketType
from core.blender_pipeline.progressive_v2.node_types import PrimitiveType
from core.blender_pipeline.progressive_v2.executor import BlenderExecutor
from core.blender_pipeline.progressive_v2.stages.stage4_resolver import BBox, Stage4Resolver
from core.blender_pipeline.progressive_v2.transaction import SceneTransactionCompiler
from core.blender_pipeline.progressive_v2.model_contract import ModelContract
from core.blender_pipeline.progressive_v2.reference_brief import ReferenceBrief, ReferenceBriefGenerator
from core.blender_pipeline.progressive_v2.stages.stage2_dimensions import Stage2Dimensions
from core.blender_pipeline.progressive_v2.constraint_planner import StructuralConstraintPlanner
from core.blender_pipeline.progressive_v2.design_fidelity import DesignFidelityValidator
from core.blender_pipeline.progressive_v2.design_audit import DesignProposalAudit
from core.blender_pipeline.progressive_v2.capabilities import validate_transaction_capabilities
from core.blender_pipeline.progressive_v2.modifiers import ModifierSpec, ModifierType
from core.blender_pipeline.progressive_v2.manifest import AttachmentSpec, BuildManifest, GeometrySpec, MaterialSpec
from core.blender_pipeline.progressive_v2.controller import BuildPhase, ProgressiveController


class _Executor:
    def __init__(self):
        self._script_buffer = []
        self.flush_calls = 0

    async def build_node(self, node, manifest, defer_modifiers=False):
        return NS(ok=True, error=None, blender_objects=[f"{node.label}_object"], bounding_box={})

    async def merge_assembly(self, node, manifest):
        children = [
            name
            for child_id in node.children_ids
            for name in manifest.nodes[child_id].blender_objects
        ]
        return NS(ok=True, error=None, blender_objects=[f"{node.label}_empty", *children], bounding_box={})

    async def flush(self, manifest):
        self.flush_calls += 1
        return True


def test_compiler_submits_one_complete_transaction():
    root = NS(
        node_id="root", label="model", kind=NodeKind.MODEL, children_ids=["part"],
        expected_child_count=1, hierarchy_depth=0, attachment=None, blender_objects=[], bounding_box=None,
    )
    part = NS(
        node_id="part", label="base", kind=NodeKind.PART, children_ids=[], expected_child_count=None,
        hierarchy_depth=1, geometry=NS(), transform_state=NS(world_matrix=NS()),
        attachment=NS(socket_type=SocketType.ROOT), parent_id="root", blender_objects=[], bounding_box=None,
    )
    manifest = NS(nodes={"root": root, "part": part}, record_event=lambda *args, **kwargs: None)
    executor = _Executor()

    receipt = asyncio.run(SceneTransactionCompiler(executor, manifest).execute())

    assert receipt.part_count == 1
    assert receipt.assembly_count == 1
    assert executor.flush_calls == 1


def test_radial_assembly_slots_are_unique_and_deterministic():
    parent = NS(node_id="hub", children_ids=["a", "b", "c", "d"])
    nodes = {"hub": parent}
    radial_nodes = []
    for index, node_id in enumerate(parent.children_ids):
        node = NS(
            node_id=node_id,
            attachment=NS(socket_type=SocketType.RADIAL, radial_count=None, radial_index=None),
            stage_outputs={},
        )
        nodes[node_id] = node
        radial_nodes.append(node)
    manifest = NS(nodes=nodes)

    for node in radial_nodes:
        Stage4Resolver._populate_assembly_radial_semantics(node, parent, manifest)

    assert [node.attachment.radial_index for node in radial_nodes] == [0, 1, 2, 3]
    assert {node.attachment.radial_count for node in radial_nodes} == {4}


def test_extended_mesh_primitives_compile_to_native_fragments():
    executor = BlenderExecutor(None, "test")
    matrix = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
    expected = {
        PrimitiveType.PLANE: "create_cube",
        PrimitiveType.CIRCLE: "primitive_circle_add",
        PrimitiveType.GRID: "create_grid",
        PrimitiveType.MONKEY: "primitive_monkey_add",
        PrimitiveType.PYRAMID: "primitive_cone_add",
        PrimitiveType.PRISM: "primitive_cone_add",
        PrimitiveType.WEDGE: "from_pydata",
        PrimitiveType.CAPSULE: "create_uvsphere",
    }
    for primitive, marker in expected.items():
        geo = NS(primitive=primitive, size=[1, 1, 1], radius=0.5, depth=1.0, segments=6)
        fragment = executor._get_primitive_fragment(primitive, "shape", geo, [0, 0, 0], matrix, "test")
        assert marker in fragment


def test_model_contract_uses_stage0_anchor_and_has_explicit_fallback():
    anchored = ModelContract.from_stage0({
        "category": "desk_fan",
        "rests_on_surface": True,
        "style_tag": "hard_surface_industrial",
        "scale_anchor_m": {"overall_height_or_length": 0.42},
    })
    fallback = ModelContract.from_stage0(None)

    assert anchored.overall_extent_m == 0.42
    assert anchored.scale_source == "stage0"
    assert fallback.overall_extent_m == 1.0
    assert fallback.scale_source == "fallback"
    assert anchored.fingerprint != fallback.fingerprint


def test_front_facing_radial_group_uses_xz_plane():
    parent = BBox(min_x=-0.02, max_x=0.02, min_y=-0.02, max_y=0.02, min_z=-0.02, max_z=0.02)
    blade = BBox(min_x=-0.06, max_x=0.06, min_y=-0.015, max_y=0.015, min_z=-0.025, max_z=0.025)
    result = Stage4Resolver._resolve_radial(parent, blade, {"radial_count": 4, "radial_index": 1, "radial_plane": "xz"}, NS())

    assert abs(result.offset[0]) < 1e-8
    assert result.offset[2] > 0
    assert result.rotation == [0.0, -1.5707963267948966, 0.0]
    assert result.offset[1] < parent.min_y


def test_front_face_clearance_pushes_guard_ahead_of_body():
    parent = BBox(min_x=-0.1, max_x=0.1, min_y=-0.02, max_y=0.02, min_z=-0.1, max_z=0.1)
    guard = BBox(min_x=-0.2, max_x=0.2, min_y=-0.008, max_y=0.008, min_z=-0.2, max_z=0.2)
    result = Stage4Resolver._resolve_front_face(parent, guard, {"front_clearance_m": 0.02}, NS())

    assert result.offset[1] == -0.048


def test_reference_brief_fallback_preserves_user_visual_intent():
    brief = ReferenceBrief.fallback("a red brushed metal desk fan", {"category": "desk_fan"})

    assert brief.category == "desk_fan"
    assert brief.palette["body"] == "red"
    assert "metallic" in brief.material_roles["body"]
    assert brief.proportion_rules


def test_reference_brief_keeps_contextual_component_design_without_claiming_exact_scale():
    fallback = ReferenceBrief.fallback("a drone with a camera", {"category": "drone"})
    brief = ReferenceBriefGenerator._validated({
        "component_profiles": {
            "camera": {
                "design_class": "compact gimbal/action camera",
                "context": "underslung on a small drone",
                "form_rules": ["small rounded rectangular housing", "forward lens barrel"],
                "scale_relation": "substantially smaller than the drone body",
                "material_role": "matte dark composite",
                "confidence": 0.72,
            }
        }
    }, fallback, [], "model")
    assert brief.component_profiles["camera"]["design_class"] == "compact gimbal/action camera"
    assert brief.scale_evidence == {}


def test_design_fidelity_expands_a_counted_assembly_and_corrects_lens_before_staging():
    manifest = BuildManifest.create("a drone with four cylindrical arms and a camera lens")
    root = manifest.get_root()
    drone = manifest.add_child_node(root.node_id, "drone_assembly", NodeKind.ASSEMBLY,
                                    attachment=AttachmentSpec(socket_type=SocketType.ROOT))
    arm = manifest.add_child_node(drone.node_id, "arm_assembly", NodeKind.ASSEMBLY,
                                  attachment=AttachmentSpec(socket_type=SocketType.ROOT))
    manifest.add_child_node(arm.node_id, "cylindrical_arm", NodeKind.PART,
                            attachment=AttachmentSpec(socket_type=SocketType.ROOT),
                            geometry=GeometrySpec(primitive=PrimitiveType.CYLINDER))
    manifest.add_child_node(drone.node_id, "camera_lens", NodeKind.PART,
                            attachment=AttachmentSpec(socket_type=SocketType.FRONT_FACE),
                            geometry=GeometrySpec(primitive=PrimitiveType.SPHERE))

    report = DesignFidelityValidator.repair_explicit_requirements(manifest)

    arm_branches = [node for node in manifest.nodes.values() if node.kind == NodeKind.ASSEMBLY and node.label.startswith("arm_assembly")]
    assert len(arm_branches) == 4
    assert {node.attachment.radial_index for node in arm_branches} == {0, 1, 2, 3}
    lens = next(node for node in manifest.nodes.values() if node.label == "camera_lens")
    assert lens.geometry.primitive == PrimitiveType.CYLINDER
    assert report["count"] == 2
    assert DesignFidelityValidator.validate(manifest) == []


def test_design_fidelity_preserves_an_explicit_spherical_lens_request():
    manifest = BuildManifest.create("suspend a smaller sphere to act as a camera lens")
    root = manifest.get_root()
    lens = manifest.add_child_node(root.node_id, "camera_lens", NodeKind.PART,
                                   attachment=AttachmentSpec(socket_type=SocketType.ROOT),
                                   geometry=GeometrySpec(primitive=PrimitiveType.SPHERE))

    report = DesignFidelityValidator.repair_explicit_requirements(manifest)

    assert lens.geometry.primitive == PrimitiveType.SPHERE
    assert report["repairs"] == []
    assert DesignFidelityValidator.validate(manifest) == []


def test_design_fidelity_preserves_explicit_circular_ring_geometry():
    manifest = BuildManifest.create("attach a flat, horizontal circular ring to act as a rotor guard")
    root = manifest.get_root()
    guard = manifest.add_child_node(root.node_id, "rotor_guard", NodeKind.PART,
                                    attachment=AttachmentSpec(socket_type=SocketType.ROOT),
                                    geometry=GeometrySpec(primitive=PrimitiveType.BOX))

    report = DesignFidelityValidator.repair_explicit_requirements(manifest)

    assert guard.geometry.primitive == PrimitiveType.TORUS
    assert any(item["mode"] == "explicit_circular_ring_to_torus" for item in report["repairs"])
    assert DesignFidelityValidator.validate(manifest) == []


def test_reference_scale_requires_two_valid_citations():
    sources = [{"title": "spec A"}, {"title": "spec B"}]
    accepted = ReferenceBriefGenerator._validated_scale_evidence({
        "overall_extent_m": 0.42, "confidence": 0.85,
        "reasoning": "matching product specifications", "source_indexes": [0, 1],
    }, sources)
    rejected = ReferenceBriefGenerator._validated_scale_evidence({
        "overall_extent_m": 0.42, "confidence": 0.99, "source_indexes": [0],
    }, sources)

    assert accepted["overall_extent_m"] == 0.42
    assert not rejected


def test_user_measurement_is_detected_before_reference_scale_can_override_it():
    assert ProgressiveController._prompt_has_explicit_measurement("a 42 cm desk fan")
    assert not ProgressiveController._prompt_has_explicit_measurement("a desk fan in red plastic")


def test_design_fidelity_rejects_missing_explicit_repeated_components():
    arm = NS(label="cylindrical_arm", kind=NodeKind.PART, geometry=NS(primitive=PrimitiveType.CYLINDER))
    manifest = NS(prompt="Build a drone with four cylindrical arms", nodes={"arm": arm})

    errors = DesignFidelityValidator.validate(manifest)

    assert "needs 4 'arm' parts, but the plan contains 1" in errors[0]


def test_design_fidelity_rejects_a_spherical_lens():
    lens = NS(label="camera_lens", kind=NodeKind.PART, geometry=NS(primitive=PrimitiveType.SPHERE))
    manifest = NS(prompt="Build a camera", nodes={"lens": lens})

    assert "cannot use a sphere" in DesignFidelityValidator.validate(manifest)[0]


def test_root_length_axis_orients_blender_z_primitive():
    node = NS(
        kind=NodeKind.PART, node_id="tube", label="tube", parent_id="",
        attachment=NS(socket_type=SocketType.ROOT),
        stage_outputs={"decomposition_hint": {"length_axis": "y"}},
    )
    _, solution = Stage4Resolver.run(node, NS(nodes={}))

    assert solution.local_transform.rotation == [-1.5707963267948966, 0.0, 0.0]


def test_repeated_radial_assembly_leaf_reuses_first_dimensions():
    first_leaf = NS(
        node_id="first_leaf", kind=NodeKind.PART,
        geometry=NS(primitive=PrimitiveType.CYLINDER),
        stage_outputs={"stage2": {"radius": 0.02, "depth": 0.36}},
    )
    first_assembly = NS(node_id="first", attachment=NS(socket_type=SocketType.RADIAL), children_ids=["first_leaf"])
    second_assembly = NS(node_id="second", attachment=NS(socket_type=SocketType.RADIAL), children_ids=[])
    candidate = NS(
        node_id="candidate", kind=NodeKind.PART, geometry=NS(primitive=PrimitiveType.CYLINDER),
        parent_id="second", stage_outputs={"decomposition_hint": {}},
    )
    grandparent = NS(children_ids=["first", "second"])
    manifest = NS(nodes={"first_leaf": first_leaf, "first": first_assembly, "second": second_assembly, "candidate": candidate, "grand": grandparent})
    first_assembly.parent_id = "grand"
    second_assembly.parent_id = "grand"

    assert Stage2Dimensions._shared_dimension_reference(candidate, manifest) == {"radius": 0.02, "depth": 0.36}


def test_radial_strut_pattern_becomes_endpoint_constraints():
    hub = NS(
        node_id="hub", kind=NodeKind.PART, children_ids=[],
        geometry=NS(primitive=PrimitiveType.CYLINDER),
        attachment=NS(socket_type=SocketType.ROOT), stage_outputs={"stage2": {"radius": .04, "depth": .2}},
    )
    nodes = {"hub": hub}
    assemblies = []
    for index in range(3):
        leaf = NS(
            node_id=f"leg{index}", kind=NodeKind.PART, children_ids=[],
            geometry=NS(primitive=PrimitiveType.CYLINDER),
            attachment=NS(socket_type=SocketType.ROOT),
            stage_outputs={"stage2": {"radius": .01, "depth": .4}, "decomposition_hint": {}},
        )
        assembly = NS(
            node_id=f"group{index}", kind=NodeKind.ASSEMBLY, children_ids=[leaf.node_id],
            attachment=NS(socket_type=SocketType.RADIAL), stage_outputs={},
        )
        nodes[assembly.node_id] = assembly
        nodes[leaf.node_id] = leaf
        assemblies.append(assembly)
    parent = NS(node_id="stand", kind=NodeKind.ASSEMBLY, children_ids=["hub", *[a.node_id for a in assemblies]])
    nodes[parent.node_id] = parent
    manifest = NS(nodes=nodes, prompt="A tripod stand with three legs angled outward and downward to the ground")

    report = StructuralConstraintPlanner.apply(manifest)

    assert report["patterns"][0]["kind"] == "radial_strut_group"
    assert report["definitions"]
    assert all(a.attachment.socket_type == SocketType.BOTTOM_CENTER for a in assemblies)
    constraint = nodes["leg1"].stage_outputs["decomposition_hint"]["endpoint_constraint"]
    assert constraint["kind"] == "radial_strut"
    resolved = Stage4Resolver._resolve_endpoint_constraint(nodes["leg1"], manifest, constraint)
    assert resolved.offset[2] < 0
    assert resolved.rotation != [0.0, 0.0, 0.0]


def test_radial_drone_branches_remain_radial_and_share_definition_by_topology():
    hub = NS(node_id="hub", kind=NodeKind.PART, children_ids=[], geometry=NS(primitive=PrimitiveType.SPHERE),
             attachment=NS(socket_type=SocketType.ROOT), stage_outputs={})
    nodes = {"hub": hub}
    branches = []
    for index in range(4):
        arm = NS(node_id=f"arm{index}", kind=NodeKind.PART, children_ids=[], dependency_ids=[],
                 geometry=NS(primitive=PrimitiveType.CYLINDER), attachment=NS(socket_type=SocketType.ROOT), stage_outputs={})
        guard = NS(node_id=f"guard{index}", kind=NodeKind.PART, children_ids=[], dependency_ids=[],
                   geometry=NS(primitive=PrimitiveType.TORUS), attachment=NS(socket_type=SocketType.TOP_CENTER), stage_outputs={})
        branch = NS(node_id=f"branch{index}", kind=NodeKind.ASSEMBLY, children_ids=[arm.node_id, guard.node_id],
                    attachment=NS(socket_type=SocketType.RADIAL), stage_outputs={})
        nodes.update({arm.node_id: arm, guard.node_id: guard, branch.node_id: branch})
        branches.append(branch)
    drone = NS(node_id="drone", kind=NodeKind.ASSEMBLY, children_ids=["hub", *[branch.node_id for branch in branches]])
    nodes[drone.node_id] = drone
    manifest = NS(nodes=nodes, prompt="a hovering drone with four arms radiating outward and a downward camera bracket")

    report = StructuralConstraintPlanner.apply(manifest)

    assert all(branch.attachment.socket_type == SocketType.RADIAL for branch in branches)
    assert {nodes[f"arm{i}"].stage_outputs["decomposition_hint"]["length_axis"] for i in range(4)} == {"x"}
    assert {nodes[f"guard{i}"].attachment.socket_type for i in range(4)} == {SocketType.RIGHT_END}
    arm_keys = {nodes[f"arm{i}"].stage_outputs["decomposition_hint"]["repeat_key"] for i in range(4)}
    guard_keys = {nodes[f"guard{i}"].stage_outputs["decomposition_hint"]["repeat_key"] for i in range(4)}
    assert len(arm_keys) == len(guard_keys) == 1 and arm_keys != guard_keys
    assert nodes["arm0"].node_id in nodes["arm1"].dependency_ids
    assert any(key.startswith("radial_repeat:") for key in report["definitions"])


def test_radial_branch_attaches_its_inboard_edge_to_the_hub_surface():
    parent = BBox(min_x=-.0583, max_x=.0583, min_y=-.0583, max_y=.0583, min_z=-.0583, max_z=.0583)
    # An arm rooted at the branch origin with a guard at its outer end is
    # intentionally asymmetric: its local inboard edge is -0.075m.
    branch = BBox(min_x=-.075, max_x=.234, min_y=-.078, max_y=.078, min_z=-.078, max_z=.078)

    resolved = Stage4Resolver._resolve_radial(parent, branch, {"radial_count": 4, "radial_index": 0}, NS())

    assert abs(resolved.offset[0] - .1333) < 1e-9


def test_design_audit_rejects_vertical_radial_spokes_and_stacked_ring_terminal():
    arm = NS(node_id="arm", label="arm", kind=NodeKind.PART, children_ids=[],
             geometry=NS(primitive=PrimitiveType.CYLINDER), attachment=NS(socket_type=SocketType.ROOT), stage_outputs={})
    ring = NS(node_id="ring", label="ring", kind=NodeKind.PART, children_ids=[],
              geometry=NS(primitive=PrimitiveType.TORUS), attachment=NS(socket_type=SocketType.TOP_CENTER), stage_outputs={})
    branch_a = NS(node_id="a", label="branch_a", kind=NodeKind.ASSEMBLY, children_ids=["arm", "ring"], attachment=NS(socket_type=SocketType.RADIAL))
    branch_b = NS(node_id="b", label="branch_b", kind=NodeKind.ASSEMBLY, children_ids=[], attachment=NS(socket_type=SocketType.RADIAL))
    parent = NS(node_id="parent", label="parent", kind=NodeKind.ASSEMBLY, children_ids=["a", "b"])
    manifest = NS(nodes={"parent": parent, "a": branch_a, "b": branch_b, "arm": arm, "ring": ring}, prompt="two arms")

    audit = DesignProposalAudit.run(manifest)

    assert not audit["passed"]
    assert any("Z-oriented" in error for error in audit["errors"])
    assert any("stacks ring" in error for error in audit["errors"])


def test_design_audit_rejects_an_inset_larger_than_a_u_shape_fork_opening():
    bracket = NS(node_id="bracket", label="bracket", kind=NodeKind.PART, children_ids=[],
                 geometry=NS(primitive=PrimitiveType.U_SHAPE, major_radius=.02, minor_radius=.005),
                 attachment=NS(socket_type=SocketType.ROOT), stage_outputs={})
    camera = NS(node_id="camera", label="camera", kind=NodeKind.ASSEMBLY, children_ids=[],
                attachment=NS(socket_type=SocketType.INSET), bounding_box={"min": [-.03, 0, 0], "max": [.03, 0, 0]})
    host = NS(node_id="host", label="host", kind=NodeKind.ASSEMBLY, children_ids=["bracket", "camera"])
    manifest = NS(nodes={"host": host, "bracket": bracket, "camera": camera}, prompt="camera in U bracket")

    audit = DesignProposalAudit.run(manifest)

    assert any("usable fork opening" in error for error in audit["errors"])


def test_design_fidelity_counts_u_shape_forks_without_requiring_duplicate_meshes():
    bracket = NS(label="u_bracket", kind=NodeKind.PART, geometry=NS(primitive=PrimitiveType.U_SHAPE))
    manifest = NS(nodes={"bracket": bracket}, prompt="a bracket with two forks")

    assert not any("two forks" in error for error in DesignFidelityValidator.validate(manifest))


def test_radial_repeat_key_replaces_decomposition_null_value():
    hub = NS(node_id="hub", kind=NodeKind.PART, children_ids=[], geometry=NS(primitive=PrimitiveType.SPHERE),
             attachment=NS(socket_type=SocketType.ROOT), stage_outputs={})
    nodes = {"hub": hub}
    branches = []
    for index in range(2):
        arm = NS(node_id=f"arm{index}", kind=NodeKind.PART, children_ids=[], dependency_ids=[],
                 geometry=NS(primitive=PrimitiveType.CYLINDER), attachment=NS(socket_type=SocketType.ROOT),
                 stage_outputs={"decomposition_hint": {"repeat_key": None}})
        guard = NS(node_id=f"guard{index}", kind=NodeKind.PART, children_ids=[], dependency_ids=[],
                   geometry=NS(primitive=PrimitiveType.TORUS), attachment=NS(socket_type=SocketType.TOP_CENTER),
                   stage_outputs={"decomposition_hint": {"repeat_key": None}})
        branch = NS(node_id=f"branch{index}", kind=NodeKind.ASSEMBLY, children_ids=[arm.node_id, guard.node_id],
                    attachment=NS(socket_type=SocketType.RADIAL), stage_outputs={})
        nodes.update({arm.node_id: arm, guard.node_id: guard, branch.node_id: branch})
        branches.append(branch)
    parent = NS(node_id="parent", kind=NodeKind.ASSEMBLY, children_ids=["hub", *[branch.node_id for branch in branches]])
    nodes[parent.node_id] = parent

    StructuralConstraintPlanner.apply(NS(nodes=nodes, prompt="a drone with two arms"))

    assert nodes["guard0"].stage_outputs["decomposition_hint"]["repeat_key"]
    assert nodes["guard0"].stage_outputs["decomposition_hint"]["repeat_key"] != nodes["arm0"].stage_outputs["decomposition_hint"]["repeat_key"]


def test_radial_fallback_reuses_same_branch_position_not_first_matching_primitive():
    collar = NS(node_id="collar", kind=NodeKind.PART, geometry=NS(primitive=PrimitiveType.TORUS),
                stage_outputs={"stage2": {"major_radius": .012}}, parent_id="first")
    guard = NS(node_id="guard", kind=NodeKind.PART, geometry=NS(primitive=PrimitiveType.TORUS),
               stage_outputs={"stage2": {"major_radius": .03}}, parent_id="first")
    first = NS(node_id="first", attachment=NS(socket_type=SocketType.RADIAL), children_ids=["collar", "guard"], parent_id="root")
    candidate = NS(node_id="candidate", kind=NodeKind.PART, geometry=NS(primitive=PrimitiveType.TORUS),
                   stage_outputs={"decomposition_hint": {}}, parent_id="second")
    second = NS(node_id="second", attachment=NS(socket_type=SocketType.RADIAL), children_ids=["other_collar", "candidate"], parent_id="root")
    other_collar = NS(node_id="other_collar", kind=NodeKind.PART, geometry=NS(primitive=PrimitiveType.TORUS), stage_outputs={}, parent_id="second")
    root = NS(children_ids=["first", "second"])
    manifest = NS(nodes={"root": root, "first": first, "second": second, "collar": collar, "guard": guard,
                         "other_collar": other_collar, "candidate": candidate})

    assert Stage2Dimensions._shared_dimension_reference(candidate, manifest) == {"major_radius": .03}


def test_inset_fit_constraint_orders_and_clamps_a_contained_sphere():
    bracket = NS(node_id="bracket", label="bracket", kind=NodeKind.PART, children_ids=[], dependency_ids=[],
                 geometry=NS(primitive=PrimitiveType.U_SHAPE, major_radius=.02, minor_radius=.005),
                 attachment=NS(socket_type=SocketType.ROOT), stage_outputs={})
    lens = NS(node_id="lens", label="lens", kind=NodeKind.PART, children_ids=[], dependency_ids=[],
              geometry=NS(primitive=PrimitiveType.SPHERE), attachment=NS(socket_type=SocketType.ROOT), stage_outputs={})
    camera = NS(node_id="camera", label="camera", kind=NodeKind.ASSEMBLY, children_ids=["lens"],
                attachment=NS(socket_type=SocketType.INSET), stage_outputs={})
    host = NS(node_id="host", label="host", kind=NodeKind.ASSEMBLY, children_ids=["bracket", "camera"])
    manifest = NS(nodes={"host": host, "bracket": bracket, "camera": camera, "lens": lens}, prompt="camera in bracket")

    report = StructuralConstraintPlanner.apply(manifest)
    output = Stage2Dimensions._apply_inset_fit_constraint(
        lens, manifest, Stage2Dimensions._from_dict({"radius": .04, "reasoning": "too large"}),
    )

    assert lens.dependency_ids == ["bracket"]
    assert lens.stage_outputs["decomposition_hint"]["inset_fit_host_node_id"] == "bracket"
    assert output.radius == .0135
    assert any(pattern["kind"] == "inset_fit_constraint" for pattern in report["patterns"])


def test_design_audit_uses_resolved_inset_geometry_not_simulation_placeholder_bbox():
    bracket = NS(node_id="bracket", label="bracket", kind=NodeKind.PART, children_ids=[],
                 geometry=NS(primitive=PrimitiveType.U_SHAPE, major_radius=.12, minor_radius=.015),
                 attachment=NS(socket_type=SocketType.ROOT), stage_outputs={"stage2": {"major_radius": .12, "minor_radius": .015}})
    lens = NS(node_id="lens", label="lens", kind=NodeKind.PART, children_ids=[],
              geometry=NS(primitive=PrimitiveType.SPHERE), attachment=NS(socket_type=SocketType.ROOT),
              stage_outputs={"stage2": {"radius": .045}}, transform_state=None)
    camera = NS(node_id="camera", label="camera", kind=NodeKind.ASSEMBLY, children_ids=["lens"],
                attachment=NS(socket_type=SocketType.INSET), bounding_box={"min": [-.5, -.5, -.5], "max": [.5, .5, .5]})
    host = NS(node_id="host", label="host", kind=NodeKind.ASSEMBLY, children_ids=["bracket", "camera"])
    manifest = NS(nodes={"host": host, "bracket": bracket, "camera": camera, "lens": lens}, prompt="camera in U bracket")

    audit = DesignProposalAudit.run(manifest)

    assert not any("usable fork opening" in error for error in audit["errors"])


def test_controller_returns_failed_when_a_post_plan_audit_fails():
    controller = ProgressiveController(model_manager=None)
    controller.manifest = BuildManifest.create("a test model")
    controller.manifest.stats["build_error"] = "SCENE_PLAN_AUDIT_FAILED: contained part does not fit"
    controller.phase = BuildPhase.FAILED

    result = controller._build_result(0.1, [controller.manifest.stats["build_error"]])

    assert not result.success
    assert result.completion_status.value == "failed"


def test_longitudinal_front_back_attachments_follow_horizontal_tube_axis():
    tube = NS(
        node_id="tube", kind=NodeKind.PART, children_ids=[],
        geometry=NS(primitive=PrimitiveType.CYLINDER), attachment=NS(socket_type=SocketType.ROOT),
        stage_outputs={"decomposition_hint": {"length_axis": "x"}},
    )
    cap = NS(
        node_id="cap", kind=NodeKind.PART, children_ids=[],
        geometry=NS(primitive=PrimitiveType.CYLINDER), attachment=NS(socket_type=SocketType.ROOT),
        stage_outputs={"decomposition_hint": {"length_axis": "z"}},
    )
    cap_assembly = NS(
        node_id="cap_group", kind=NodeKind.ASSEMBLY, children_ids=["cap"],
        attachment=NS(socket_type=SocketType.FRONT_FACE), stage_outputs={},
    )
    host = NS(node_id="host", kind=NodeKind.ASSEMBLY, children_ids=["tube", "cap_group"])
    manifest = NS(nodes={"host": host, "tube": tube, "cap_group": cap_assembly, "cap": cap}, prompt="a horizontal tube")

    report = StructuralConstraintPlanner.apply(manifest)

    assert cap_assembly.attachment.socket_type == SocketType.RIGHT_FACE
    assert cap.stage_outputs["decomposition_hint"]["length_axis"] == "x"
    assert any(p["kind"] == "longitudinal_attachments" for p in report["patterns"])


def test_transaction_modifier_fragment_covers_declared_supported_modifiers():
    executor = BlenderExecutor(None, "test")
    fragment = executor._modifiers_fragment("shape", [
        ModifierSpec(type=kind).to_dict()
        for kind in (ModifierType.SOLIDIFY, ModifierType.MIRROR, ModifierType.ARRAY,
                     ModifierType.SIMPLE_DEFORM, ModifierType.WEIGHTED_NORMAL,
                     ModifierType.SMOOTH, ModifierType.EDGE_SPLIT,
                     ModifierType.TRIANGULATE, ModifierType.DECIMATE)
    ])
    for marker in ("SOLIDIFY", "MIRROR", "ARRAY", "SIMPLE_DEFORM", "WEIGHTED_NORMAL", "SMOOTH", "EDGE_SPLIT", "TRIANGULATE", "DECIMATE"):
        assert marker in fragment


def test_transaction_material_fragment_preserves_full_principled_pbr_intent():
    executor = BlenderExecutor(None, "test")
    material = MaterialSpec(
        name="glass_detail", base_color=[0.1, 0.2, 0.3, 0.6], metallic=.2, roughness=.15,
        transmission=.9, ior=1.52, subsurface=.1, clearcoat=.3, sheen=.2,
        emission_color=[0.1, 0.2, 0.3], emission_strength=.4,
    )
    fragment = executor._material_fragment("shape", material)
    for marker in ("Transmission", "IOR", "Subsurface", "Coat", "Sheen", "Emission", "Alpha"):
        assert marker in fragment
    assert "MatPBR_" in fragment
    assert "default_value = 0.0" not in fragment.split("Specular Tint")[-1].split("Emission")[0]
    assert "(1.0, 1.0, 1.0, 1.0)" in fragment


def test_unsupported_future_geometry_is_rejected_before_transaction():
    node = NS(label="curve", geometry=NS(primitive=PrimitiveType.BEZIER_CURVE), modifiers=[], material=None)
    errors = validate_transaction_capabilities(node)
    assert errors == ["part 'curve' uses unsupported transaction primitive 'bezier_curve'"]


def test_curved_primitives_emit_smooth_shading_and_edge_split():
    executor = BlenderExecutor(None, "test")
    matrix = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]

    # Curved primitives with sharp caps must emit smooth shading AND shade_smooth_by_angle
    for prim in (PrimitiveType.CYLINDER, PrimitiveType.CONE, PrimitiveType.HEMISPHERE, PrimitiveType.U_SHAPE):
        geo = GeometrySpec(primitive=prim, radius=0.1, depth=0.3, segments=16, rings=8, major_radius=0.1, minor_radius=0.02)
        frag = executor._get_primitive_fragment(prim, f"test_{prim.value}", geo, [0, 0, 0], matrix, "test")
        assert "use_smooth" in frag, f"{prim.value} must emit use_smooth"
        assert "shade_smooth_by_angle" in frag, f"{prim.value} must emit shade_smooth_by_angle"

    # Fully curved primitives must emit smooth shading without shade_smooth_by_angle
    for prim in (PrimitiveType.SPHERE, PrimitiveType.TORUS, PrimitiveType.CAPSULE):
        geo = GeometrySpec(primitive=prim, radius=0.1, depth=0.3, segments=16, rings=8, major_radius=0.1, minor_radius=0.02)
        frag = executor._get_primitive_fragment(prim, f"test_{prim.value}", geo, [0, 0, 0], matrix, "test")
        assert "use_smooth" in frag, f"{prim.value} must emit use_smooth"
        assert "shade_smooth_by_angle" not in frag, f"{prim.value} must not emit shade_smooth_by_angle"

    # Planar primitives must remain flat
    for prim in (PrimitiveType.BOX, PrimitiveType.PLANE):
        geo = GeometrySpec(primitive=prim, size=[0.2, 0.2, 0.2])
        frag = executor._get_primitive_fragment(prim, f"test_{prim.value}", geo, [0, 0, 0], matrix, "test")
        assert "use_smooth" not in frag, f"{prim.value} must not emit use_smooth"

