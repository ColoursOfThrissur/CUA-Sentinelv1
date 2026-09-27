"""Tests for the Recursive Assembly Decomposition & Feedback Engine."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from core.assembly_spec import (
    AssemblyGraph,
    AssemblyNode,
    AttachmentSpec,
    PartParadigm,
    JoinMode,
)
from core.assembly_resolver import AssemblyResolver, Mat4
from core.assembly_verification import (
    AssemblyVerificationGate,
    JointVerificationResult,
)
from core.assembly_feedback import (
    AssemblyFeedbackEngine,
    MutationAction,
)
from db.repositories import OperationalRepository


def test_assembly_graph_schema_and_lookup():
    """Verify AssemblyGraph Pydantic model tree traversal and node lookup."""
    root = AssemblyNode(
        node_id="root_chassis",
        label="chassis",
        paradigm=PartParadigm.HARD_SURFACE,
        sub_spec={"name": "chassis", "size": [1.2, 2.4, 0.4]},
        attachment=AttachmentSpec(socket_name="origin"),
        children=[
            AssemblyNode(
                node_id="wheel_fl",
                label="front_left_wheel",
                paradigm=PartParadigm.HARD_SURFACE,
                sub_spec={"name": "wheel", "radius": 0.25},
                attachment=AttachmentSpec(
                    parent_node_id="root_chassis",
                    socket_name="chassis.wheel_fl",
                    local_offset=(-0.65, 0.8, -0.15),
                    join_mode=JoinMode.PARENT_ONLY,
                ),
            ),
            AssemblyNode(
                node_id="wheel_fr",
                label="front_right_wheel",
                paradigm=PartParadigm.HARD_SURFACE,
                sub_spec={"name": "wheel", "radius": 0.25},
                attachment=AttachmentSpec(
                    parent_node_id="root_chassis",
                    socket_name="chassis.wheel_fr",
                    local_offset=(0.65, 0.8, -0.15),
                    join_mode=JoinMode.PARENT_ONLY,
                ),
            ),
        ],
    )

    graph = AssemblyGraph(
        task_id="task_test_assembly_1",
        root=root,
        description="A stylized procedural car",
    )

    assert graph.get_node("root_chassis") is not None
    assert graph.get_node("wheel_fl") is not None
    assert graph.get_node("wheel_fr") is not None
    assert graph.get_node("non_existent") is None
    assert len(root.all_nodes()) == 3


def test_operational_repo_assembly_persistence():
    """Verify persistence of AssemblyGraph and nodes into operational.sqlite."""
    repo = OperationalRepository()

    root = AssemblyNode(
        node_id="node_a",
        label="base_pillar",
        paradigm=PartParadigm.PRIMITIVE,
        sub_spec={"type": "CYLINDER"},
        children=[
            AssemblyNode(
                node_id="node_b",
                label="top_arch",
                paradigm=PartParadigm.PRIMITIVE,
                sub_spec={"type": "BOX"},
                attachment=AttachmentSpec(
                    parent_node_id="node_a",
                    socket_name="top",
                    local_offset=(0, 0, 2.0),
                ),
            )
        ],
    )

    graph = AssemblyGraph(
        task_id="task_persist_test",
        root=root,
        description="Pillar with arch",
    )

    # Save
    repo.save_assembly_graph(graph.model_dump())

    # Update status
    updated = repo.update_assembly_node_status(
        task_id="task_persist_test",
        node_id="node_b",
        status="VERIFIED",
        retry_count=1,
    )
    assert updated is True

    # Retrieve
    loaded = repo.get_assembly_graph_dict("task_persist_test")
    assert loaded is not None
    assert loaded["task_id"] == "task_persist_test"
    assert loaded["root"]["node_id"] == "node_a"


@pytest.mark.asyncio
async def test_assembly_resolver_matrix_transforms():
    """Verify top-down transform compounding in AssemblyResolver."""
    calls = []

    async def mock_call(tool_name, args):
        calls.append((tool_name, args))
        return {"ok": True}

    resolver = AssemblyResolver(tool_gateway_or_bridge=mock_call)

    # Root at (0, 0, 1.0), child offset by (0, 2.0, 0.5)
    root = AssemblyNode(
        node_id="parent",
        label="parent_mesh",
        attachment=AttachmentSpec(local_offset=(0, 0, 1.0)),
        children=[
            AssemblyNode(
                node_id="child",
                label="child_mesh",
                attachment=AttachmentSpec(
                    parent_node_id="parent",
                    socket_name="head",
                    local_offset=(0, 2.0, 0.5),
                    join_mode=JoinMode.PARENT_ONLY,
                ),
            )
        ],
    )
    graph = AssemblyGraph(task_id="task_mat", root=root, description="test")

    res = await resolver.resolve(graph)
    assert res["ok"] is True
    assert res["nodes_placed"] == 2

    # Check child transform: world Z = 1.0 + 0.5 = 1.5, world Y = 2.0
    child_transforms = [args for (tool, args) in calls if tool == "blender:set_transform" and args["name"] == "child_mesh"]
    assert len(child_transforms) == 1
    assert child_transforms[0]["location"] == [0.0, 2.0, 1.5]

    # Verify parenting occurred
    parent_calls = [args for (tool, args) in calls if tool == "blender:parent_object"]
    assert len(parent_calls) == 1
    assert parent_calls[0]["name"] == "child_mesh"
    assert parent_calls[0]["parent_name"] == "parent_mesh"


def test_assembly_feedback_engine_mutation_and_escalation():
    """Verify closed-loop mutation and retry escalation rules."""
    root = AssemblyNode(
        node_id="chassis",
        label="car_chassis",
        children=[
            AssemblyNode(
                node_id="wheel_1",
                label="rear_wheel",
                attachment=AttachmentSpec(
                    parent_node_id="chassis",
                    socket_name="wheel_well_top",
                    local_offset=(0.8, -0.6, 0.0),
                    mating_tolerance_mm=2.0,
                ),
                max_split_depth_remaining=1,
            )
        ],
    )
    graph = AssemblyGraph(task_id="task_fb", root=root, description="car", max_retries_per_node=2)

    # 1. First failure: gap of 3.5mm (> tolerance 2.0mm)
    fail_1 = JointVerificationResult(
        node_id="wheel_1",
        parent_id="chassis",
        socket_name="wheel_well_top",
        gap_or_overlap_mm=3.5,
        passed=False,
        reason="Gap 3.50mm exceeds tolerance 2.00mm",
    )

    action_1 = AssemblyFeedbackEngine.process_joint_failure(graph, fail_1)
    assert action_1["action"] == MutationAction.RETRY_MUTATED_SPEC
    assert action_1["retry_count"] == 1
    assert action_1["offset_adjusted"] is True
    # Z was shifted downwards to close the gap
    assert action_1["new_offset"][2] < 0.0
    assert "Assembly verification failure" in action_1["diagnostic_prompt"]

    # 2. Second failure: retry count reaches 2
    action_2 = AssemblyFeedbackEngine.process_joint_failure(graph, fail_1)
    assert action_2["action"] == MutationAction.RETRY_MUTATED_SPEC
    assert action_2["retry_count"] == 2

    # 3. Third failure: exceeds max_retries (2), should trigger SPLIT_FURTHER
    action_3 = AssemblyFeedbackEngine.process_joint_failure(graph, fail_1)
    assert action_3["action"] == MutationAction.SPLIT_FURTHER
    assert action_3["split_depth_remaining"] == 0

    # 4. Fourth failure: retry count exceeded and split depth 0 -> EXTERNAL_GENERATIVE
    action_4 = AssemblyFeedbackEngine.process_joint_failure(graph, fail_1)
    assert action_4["action"] == MutationAction.EXTERNAL_GENERATIVE


# ===========================================================================
# Phase 7: Consolidated Regression Test Suite
# ===========================================================================

@pytest.mark.asyncio
async def test_regression_buried_stem_fails_verification():
    """Regression 1: Uncorrected lamp with buried stem must fail verification and report violation."""
    from unittest.mock import AsyncMock

    mock_bridge = AsyncMock()
    mock_bridge.call_internal = AsyncMock(return_value={"ok": True, "z_min": -0.17})

    verifier = AssemblyVerificationGate(mock_bridge)
    buried_node = AssemblyNode(
        node_id="stem",
        label="stem",
        sub_spec={"primitive": "cylinder", "radius": 1, "depth": 40},
    )
    graph = AssemblyGraph(schema_version="2.0", task_id="reg_1", root=buried_node)
    res = await verifier.verify(graph)

    assert res["ok"] is False
    assert "Ground plane violation" in res["error"]


@pytest.mark.asyncio
async def test_regression_orphaned_objects_after_failure_is_empty():
    """Regression 2: Mid-graph failure must roll back all partial objects, leaving zero orphaned objects."""
    from core.scene_transaction import SceneTransaction

    deleted = []
    mock_bridge = AsyncMock()
    mock_bridge.execute_tool = AsyncMock(side_effect=lambda tool, args: deleted.append(args.get("name")))

    txn = SceneTransaction(tool_executor=mock_bridge)
    with pytest.raises(ValueError):
        async with txn:
            txn.record("lamp_base")
            txn.record("lamp_stem")
            raise ValueError("Failure creating lamp_head")

    assert txn.committed is False
    assert txn.rolled_back is True
    assert deleted == ["lamp_stem", "lamp_base"]


def test_regression_missing_import_caught_by_linter():
    """Regression 3: Using math.radians without import math must be caught by CodegenLinter locally."""
    from core.codegen_linter import lint, CodegenLintError
    from core.blender_ops import render_op_script, CreateBoxParams

    broken_template = """
import bpy
import json
params = json.loads(PARAMS_JSON)
rot = params.get("rotation")
rot_rad = tuple(math.radians(r) for r in rot) if rot else (0,0,0)
bpy.ops.mesh.primitive_cube_add(rotation=rot_rad)
"""
    p = CreateBoxParams(name="box", size=[1, 1, 1], location=[0, 0, 0], rotation=[0, 90, 0])
    with pytest.raises(CodegenLintError) as exc:
        render_op_script(broken_template, p)

    assert "math" in str(exc.value)


def test_regression_no_web_search_on_3d_task():
    """Regression 4: Web search fallback must never trigger on 3D modeling tasks."""
    from agents.endpoint_agent import EndpointAgent
    from unittest.mock import MagicMock

    agent = EndpointAgent(model_manager=MagicMock(), governance=MagicMock(), config={})

    assert agent._should_use_web("create a 3d model of a desk lamp", explicit=False) is False
    assert agent._should_use_web("build a 2m cube in blender", explicit=False) is False
    assert agent._should_use_web("a cylinder resting on ground plane", explicit=False) is False


@pytest.mark.asyncio
async def test_regression_single_span_id_and_domain_success():
    """Regression 5: ToolGateway must emit a single span_id and mandatory domain_success field."""
    from core.tool_gateway import ToolGateway

    gw = ToolGateway()
    # Mock handler
    ToolGateway.register_tool_handler("test_mock_tool", lambda **kw: {"ok": True, "data": "success"})

    res = await gw.execute_tool("web_search", {"query": "test"}, caller_name="endpoint_agent")
    assert "span_id" in res
    assert res["span_id"].startswith("span_")
    assert "domain_success" in res
    assert isinstance(res["domain_success"], bool)

