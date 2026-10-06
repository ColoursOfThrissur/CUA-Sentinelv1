import pytest
from backend.core.blender_pipeline.progressive_v2.manifest import BuildManifest, AttachmentSpec, GeometrySpec
from backend.core.blender_pipeline.progressive_v2.node_types import NodeKind, SocketType, PrimitiveType
from backend.core.blender_pipeline.progressive_v2.scene_ir import ExecutableScenePlan
from backend.core.blender_pipeline.progressive_v2.transaction import SceneTransactionCompiler
from backend.core.blender_pipeline.progressive_v2.instances import InstanceManager
from backend.core.blender_pipeline.progressive_v2.readback import SceneReadbackVerifier
from backend.core.blender_pipeline.progressive_v2.transforms import LocalTransform

def test_scene_ir_supports_all_boolean_operations():
    manifest = BuildManifest.create("boolean operations test", model_id="m_bool_ops")
    root_id = manifest.root_node_id

    # Add a base part
    base = manifest.add_child_node(
        parent_id=root_id,
        label="base_body",
        kind=NodeKind.PART,
        geometry=GeometrySpec(primitive=PrimitiveType.BOX, size=[1.0, 1.0, 1.0]),
        attachment=AttachmentSpec(socket_type=SocketType.ROOT),
    )

    # Add a cut part
    cut = manifest.add_child_node(
        parent_id=root_id,
        label="cutter",
        kind=NodeKind.PART,
        geometry=GeometrySpec(primitive=PrimitiveType.CYLINDER, radius=0.2, depth=1.2),
        attachment=AttachmentSpec(socket_type=SocketType.BOOLEAN_CUT),
    )

    # Add a union part
    union = manifest.add_child_node(
        parent_id=root_id,
        label="merger",
        kind=NodeKind.PART,
        geometry=GeometrySpec(primitive=PrimitiveType.SPHERE, radius=0.3),
        attachment=AttachmentSpec(socket_type=SocketType.BOOLEAN_UNION),
    )

    # Add an intersect part
    intersect = manifest.add_child_node(
        parent_id=root_id,
        label="intersecter",
        kind=NodeKind.PART,
        geometry=GeometrySpec(primitive=PrimitiveType.BOX, size=[0.5, 0.5, 0.5]),
        attachment=AttachmentSpec(socket_type=SocketType.BOOLEAN_INTERSECT),
    )

    plan = ExecutableScenePlan.from_manifest(manifest)
    bool_ops = {item["cutter_node_id"]: item["operation"] for item in plan.boolean_operations}

    assert bool_ops[cut.node_id] == "difference"
    assert bool_ops[union.node_id] == "union"
    assert bool_ops[intersect.node_id] == "intersect"

def test_boolean_fragment_is_non_destructive():
    frag = SceneTransactionCompiler._boolean_fragment("target_obj", "cutter_obj", operation="UNION")
    # Must NOT contain modifier_apply or remove
    assert "bpy.ops.object.modifier_apply" not in frag
    assert "bpy.data.objects.remove" not in frag
    # Must hide cutter in viewport and render
    assert "_cutter.hide_viewport = True" in frag
    assert "_cutter.hide_render = True" in frag
    assert "_boolean.operation = 'UNION'" in frag

def test_readback_boolean_dimensions_match_within_base_bounds():
    verifier = SceneReadbackVerifier(mcp_manager=None, dimension_relative_tolerance=0.12)
    base_dims = [1.0, 1.0, 1.0]

    # Part cut down to smaller dimension should pass
    smaller_dims = [0.8, 0.9, 1.0]
    assert verifier._boolean_dimensions_match(base_dims, smaller_dims) is True

    # Part slightly exceeding base bounds within tolerance should pass
    slight_excess = [1.05, 1.0, 1.0]
    assert verifier._boolean_dimensions_match(base_dims, slight_excess) is True

    # Part significantly exceeding base bounds should FAIL
    too_large = [1.5, 1.0, 1.0]
    assert verifier._boolean_dimensions_match(base_dims, too_large) is False

    # Part collapsed near zero should FAIL
    collapsed = [0.01, 0.01, 0.01]
    assert verifier._boolean_dimensions_match(base_dims, collapsed) is False

def test_instances_apply_scale_and_matrix_composition():
    manifest = BuildManifest.create("instance scale test", model_id="m_inst_scale")
    root_id = manifest.root_node_id

    # Create instance node with scale in transform_state
    inst_node = manifest.add_child_node(
        parent_id=root_id,
        label="scaled_instance",
        kind=NodeKind.INSTANCE,
    )
    inst_node.transform_state.set_local_transform(
        LocalTransform(position=[1.0, 2.0, 3.0], rotation=[0.0, 0.0, 0.0], scale=[2.0, 0.5, 1.5])
    )
    manifest.propagate_transforms_from(inst_node.node_id)

    manager = InstanceManager(mcp_manager=None)
    pos, rot, scale = manager._compute_instance_transform(inst_node, manifest)

    assert scale == [2.0, 0.5, 1.5]
    assert pos == [1.0, 2.0, 3.0]

    # Verify script output includes scale
    script = manager._linked_duplicate_script("def_obj", "inst_obj", pos, rot, scale)
    assert "new_obj.scale = tuple(scale_vec)" in script
    assert "scale_vec = [2.0, 0.5, 1.5]" in script
