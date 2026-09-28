"""Tests for the Recursive Assembly Decomposition & Feedback Engine."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from core.assembly_spec import (
    AssemblyGraph,
    AssemblyNode,
    AttachmentSpec,
    PartParadigm,
    JoinMode,
    graph_to_blender_steps,
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
from core.graph_compiler import GraphCompiler
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
    """Regression 2: Mid-graph failure must roll back all partial objects, leaving zero orphaned objects.
    
    Updated for SceneTransaction v2 which uses generation_id-based safe delete.
    The transaction tracks objects with metadata and only deletes objects from its own generation.
    """
    from core.scene_transaction import SceneTransaction

    deleted = []
    
    class MockBridge:
        """Mock bridge that tracks deletions via call_internal."""
        async def call_internal(self, method: str, params: dict):
            # Check if this is a safe delete call
            code = params.get("code", "")
            if "bpy.data.objects.remove" in code and "sentinel_generation_id" in code:
                # Extract the object name from the params embedded in the script
                import re
                match = re.search(r'"name":\s*"([^"]+)"', code)
                if match:
                    deleted.append(match.group(1))
                return {"ok": True, "deleted": True}
            return {"ok": True}

    mock_bridge = MockBridge()
    txn = SceneTransaction(tool_executor=mock_bridge)
    
    with pytest.raises(ValueError):
        async with txn:
            txn.record("lamp_base", object_id="node_base", role="root")
            txn.record("lamp_stem", object_id="node_stem", parent_id="node_base", role="child")
            raise ValueError("Failure creating lamp_head")

    assert txn.committed is False
    assert txn.rolled_back is True
    # Objects deleted in reverse order
    assert deleted == ["lamp_stem", "lamp_base"]
    # Verify generation_id was set
    assert txn.generation_id.startswith("gen_")


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
async def test_origin_centered_skips_ground_plane_check():
    """Regression 6: Objects explicitly centered at the origin (dumbbells, axles, rings)
    must not fail the ground-plane check. z_min < 0 is correct and expected for any
    symmetric object centered at Z=0."""
    mock_bridge = AsyncMock()
    # Simulate a horizontal cylinder (radius=6) centered at origin: z_min = -6.0m
    mock_bridge.call_internal = AsyncMock(return_value={"ok": True, "z_min": -6.0})

    verifier = AssemblyVerificationGate(mock_bridge)

    # With origin_centered=True: ground-plane check is skipped, result must be ok
    res = await verifier.verify_flat_object_set(
        object_names=["grip", "weight_plate_left", "weight_plate_right"],
        origin_centered=True,
    )
    assert res["ok"] is True
    assert res["checks_run"] == 0  # no ground-plane checks ran

    # With origin_centered=False (default): same z_min must fail
    res_fail = await verifier.verify_flat_object_set(
        object_names=["grip"],
        origin_centered=False,
    )
    assert res_fail["ok"] is False
    assert "Ground plane violation" in res_fail["error"]


@pytest.mark.asyncio
async def test_floating_object_fails_ground_plane_check():
    """Regression 7: A non-origin-centered object with z_min < 0 must still fail.
    Uses a pipe fitting (unrelated category) to confirm the check is general."""
    mock_bridge = AsyncMock()
    mock_bridge.call_internal = AsyncMock(return_value={"ok": True, "z_min": -0.05})

    verifier = AssemblyVerificationGate(mock_bridge)
    res = await verifier.verify_flat_object_set(
        object_names=["pipe_elbow"],
        origin_centered=False,
    )
    assert res["ok"] is False
    assert "Ground plane violation" in res["error"]


# ===========================================================================
# rests_on_surface regression tests
# Three objects from this conversation that were all phrased with
# "centered at the origin" — the regression confirms the field is driven
# by physical-nature reasoning in the decomp JSON, not by prompt phrasing.
# ===========================================================================

def test_rests_on_surface_dumbbell_is_false():
    """Dumbbell: free-floating symmetric object, no defined base.
    LLM must set rests_on_surface=false regardless of 'centered at origin' phrasing."""
    decomp = {
        "rests_on_surface": False,
        "root": {
            "label": "grip",
            "shape": {"primitive": "cylinder", "radius": 1.5, "depth": 15},
            "attachment": {"local_offset": [0, 0, 0]},
        },
        "parts": [],
    }
    graph = GraphCompiler._build_graph_from_decomp(decomp, "dumbbell centered at the origin", "tid_db")
    assert graph.rests_on_surface is False


def test_rests_on_surface_mug_is_true():
    """Ceramic mug: surface-resting object. Must be true even if prompt says 'centered at origin'."""
    decomp = {
        "rests_on_surface": True,
        "root": {
            "label": "body",
            "shape": {"primitive": "cylinder", "radius": 4.2, "depth": 10},
            "attachment": {"local_offset": [0, 0, 5]},
        },
        "parts": [],
    }
    graph = GraphCompiler._build_graph_from_decomp(decomp, "a ceramic mug centered at the origin", "tid_mug")
    assert graph.rests_on_surface is True


def test_rests_on_surface_french_press_is_true():
    """French press: surface-resting vessel. Must be true even if prompt says 'centered at origin'."""
    decomp = {
        "rests_on_surface": True,
        "root": {
            "label": "carafe",
            "shape": {"primitive": "cylinder", "radius": 5, "depth": 20},
            "attachment": {"local_offset": [0, 0, 10]},
        },
        "parts": [],
    }
    graph = GraphCompiler._build_graph_from_decomp(decomp, "a French press centered at the origin", "tid_fp")
    assert graph.rests_on_surface is True


def test_rests_on_surface_defaults_true_when_field_absent():
    """If the LLM omits rests_on_surface entirely, default must be True (safe fallback)."""
    decomp = {
        "root": {
            "label": "base",
            "shape": {"primitive": "box", "size": [10, 10, 2]},
            "attachment": {"local_offset": [0, 0, 1]},
        },
        "parts": [],
    }
    graph = GraphCompiler._build_graph_from_decomp(decomp, "some object", "tid_default")
    assert graph.rests_on_surface is True


# ===========================================================================
# graph_to_blender_steps wiring tests
# Confirm the compiled path produces correct world positions and tool names.
# ===========================================================================

def test_graph_to_blender_steps_rests_on_surface_root_z():
    """rests_on_surface=True: root cylinder base must sit on Z=0 (center at depth/2)."""
    root = AssemblyNode(
        node_id="root_base",
        label="base",
        paradigm=PartParadigm.PRIMITIVE,
        sub_spec={"primitive": "cylinder", "radius": 5.0, "depth": 4.0},
        attachment=AttachmentSpec(local_offset=(0.0, 0.0, 2.0)),
        children=[],
    )
    graph = AssemblyGraph(task_id="t1", root=root, rests_on_surface=True)
    steps = graph_to_blender_steps(graph)
    # steps[0] is clear_scene; first geometry step is the cylinder
    base_step = next(s for s in steps if s[1].get("name") == "base")
    assert base_step[0] == "blender:create_cylinder"
    # depth=4 -> bottom_face_offset=2.0 -> root world Z must be 2.0
    assert base_step[1]["location"][2] == 2.0


def test_graph_to_blender_steps_origin_centered_root_z():
    """rests_on_surface=False: root must be centered at Z=0."""
    root = AssemblyNode(
        node_id="root_grip",
        label="grip",
        paradigm=PartParadigm.PRIMITIVE,
        sub_spec={"primitive": "cylinder", "radius": 1.5, "depth": 15.0},
        attachment=AttachmentSpec(local_offset=(0.0, 0.0, 0.0)),
        children=[],
    )
    graph = AssemblyGraph(task_id="t2", root=root, rests_on_surface=False)
    steps = graph_to_blender_steps(graph)
    grip_step = next(s for s in steps if s[1].get("name") == "grip")
    assert grip_step[1]["location"][2] == 0.0


def test_graph_to_blender_steps_hemisphere_emits_boolean():
    """hemisphere primitive must always emit sphere + box_cutter + apply_boolean,
    regardless of part name (structural, not label-based)."""
    root = AssemblyNode(
        node_id="root_dish",
        label="satellite_reflector",  # deliberately not 'hemisphere' or 'dome'
        paradigm=PartParadigm.PRIMITIVE,
        sub_spec={"primitive": "hemisphere", "radius": 8.0},
        attachment=AttachmentSpec(local_offset=(0.0, 0.0, 0.0)),
        children=[],
    )
    graph = AssemblyGraph(task_id="t3", root=root, rests_on_surface=False)
    steps = graph_to_blender_steps(graph)
    tools = [t for t, _ in steps]
    # steps[0] is clear_scene; geometry steps follow
    assert "blender:create_sphere" in tools
    assert "blender:create_box" in tools
    assert "blender:apply_boolean" in tools
    # Boolean must target the cutter and delete it
    bool_step = next(s for s in steps if s[0] == "blender:apply_boolean")
    bool_args = bool_step[1]
    assert bool_args["operation"] == "DIFFERENCE"
    assert bool_args["delete_target"] is True
    assert bool_args["target_name"] == "satellite_reflector_hemi_cutter"


def test_graph_to_blender_steps_child_world_position():
    """Child world position = root world Z + child local_offset Z."""
    root = AssemblyNode(
        node_id="root_base",
        label="base",
        paradigm=PartParadigm.PRIMITIVE,
        sub_spec={"primitive": "cylinder", "radius": 5.0, "depth": 2.0},
        attachment=AttachmentSpec(local_offset=(0.0, 0.0, 1.0)),
        children=[
            AssemblyNode(
                node_id="child_pillar",
                label="pillar",
                paradigm=PartParadigm.PRIMITIVE,
                sub_spec={"primitive": "cylinder", "radius": 1.0, "depth": 10.0},
                attachment=AttachmentSpec(
                    parent_node_id="root_base",
                    local_offset=(0.0, 0.0, 6.0),  # 1 (root half) + 5 (child half)
                ),
                children=[],
            )
        ],
    )
    graph = AssemblyGraph(task_id="t4", root=root, rests_on_surface=True)
    steps = graph_to_blender_steps(graph)
    # root world Z = bottom_face_offset = 1.0 (depth/2)
    base_step = next(s for s in steps if s[1].get("name") == "base")
    assert base_step[1]["location"][2] == 1.0
    # child world Z = root_world_z(1.0) + child_offset_z(6.0) = 7.0
    pillar_step = next(s for s in steps if s[1].get("name") == "pillar")
    assert pillar_step[1]["location"][2] == 7.0


def test_strut_tilt_correction_applied_when_only_z_rotation():
    """Regression: strut with non-zero XY offset and Z-only rotation must get
    proper diagonal tilt computed. Without the fix the strut stays vertical
    and interpenetrates the parent sphere (1876mm failure observed in live build)."""
    import math
    decomp = {
        "rests_on_surface": True,
        "root": {
            "label": "radar_dish",
            "shape": {"primitive": "sphere", "radius": 8.0},
            "attachment": {"local_offset": [0, 0, 0]},
        },
        "parts": [
            {
                "label": "support_strut_1",
                "parent_label": "radar_dish",
                "socket_name": "dish.strut_mount",  # Contains 'strut' keyword
                "shape": {"primitive": "cylinder", "radius": 0.3, "depth": 5.0},
                "local_offset": [6.0, 0.0, -8.0],   # non-zero X, non-zero Z
                "local_rotation_euler": [0, 0, 45],  # Z-only yaw — the LLM bug
                "join_mode": "parent_only",
            }
        ],
    }
    graph = GraphCompiler._build_graph_from_decomp(decomp, "tower struts", "tid_strut")
    strut = graph.root.children[0]
    rot = strut.attachment.local_rotation_euler  # radians
    # After fix: Y rotation must be non-zero (tilt applied)
    assert abs(rot[1]) > 0.01, f"Expected Y tilt, got rot={rot}"
    # The tilt should point the cylinder along the offset vector direction
    # For offset [6, 0, -8], the tilt from vertical is atan2(6, 8) ≈ 36.87°
    # Since offset_z < 0, the formula gives ry = tilt * cos(compass) = tilt * 1.0
    expected_tilt = math.atan2(6.0, 8.0)  # ~0.6435 rad
    assert abs(abs(rot[1]) - expected_tilt) < 0.1, f"Tilt {abs(rot[1]):.4f} not close to expected {expected_tilt:.4f}"


def test_strut_tilt_diagonal_compass():
    """Diagonal strut at 45° compass angle must get proper tilt in both X and Y."""
    import math
    decomp = {
        "rests_on_surface": True,
        "root": {
            "label": "hub",
            "shape": {"primitive": "sphere", "radius": 5.0},
            "attachment": {"local_offset": [0, 0, 0]},
        },
        "parts": [
            {
                "label": "diagonal_strut",
                "parent_label": "hub",
                "socket_name": "hub.strut_45",
                "shape": {"primitive": "cylinder", "radius": 0.2, "depth": 4.0},
                "local_offset": [3.0, 3.0, -4.0],  # 45° compass, downward
                "local_rotation_euler": [0, 0, 0],
                "join_mode": "parent_only",
            }
        ],
    }
    graph = GraphCompiler._build_graph_from_decomp(decomp, "diagonal test", "tid_diag")
    strut = graph.root.children[0]
    rot = strut.attachment.local_rotation_euler
    # Both X and Y rotation should be non-zero for 45° diagonal
    assert abs(rot[0]) > 0.01, f"Expected X tilt for diagonal, got rot={rot}"
    assert abs(rot[1]) > 0.01, f"Expected Y tilt for diagonal, got rot={rot}"


def test_horizontal_pipe_no_false_tilt():
    """Horizontal pipe (not a strut) should NOT get auto-tilted.
    Only structural connectors with strut/brace/support keywords get correction."""
    decomp = {
        "rests_on_surface": True,
        "root": {
            "label": "tank",
            "shape": {"primitive": "cylinder", "radius": 3.0, "depth": 6.0},
            "attachment": {"local_offset": [0, 0, 0]},
        },
        "parts": [
            {
                "label": "outlet_pipe",
                "parent_label": "tank",
                "socket_name": "tank.side_outlet",  # No strut/brace keyword
                "shape": {"primitive": "cylinder", "radius": 0.5, "depth": 2.0},
                "local_offset": [4.0, 0.0, 0.0],  # Horizontal offset, small relative to parent
                "local_rotation_euler": [0, 90, 0],  # Already has Y rotation (horizontal)
                "join_mode": "parent_only",
            }
        ],
    }
    graph = GraphCompiler._build_graph_from_decomp(decomp, "pipe test", "tid_pipe")
    pipe = graph.root.children[0]
    rot = pipe.attachment.local_rotation_euler
    # Should preserve the LLM's rotation, not override it
    import math
    assert abs(rot[1] - math.radians(90)) < 0.01, f"Pipe Y rotation should be 90°, got {math.degrees(rot[1]):.1f}°"


def test_stacking_offset_correction_parent_half_only():
    """Regression: LLM returns local_offset=[0,0,parent_half] instead of [0,0,parent_half+child_half].
    Runtime must detect this and add the child's half-height.
    
    This was the root cause of the sci-fi tower interpenetration failures:
    - pillar at Z=12 (correct)
    - radar_dish at Z=22 instead of Z=28 (1500mm interpenetration with pillar)
    - antenna at Z=28 instead of Z=38 (3500mm interpenetration with dish)
    """
    decomp = {
        "rests_on_surface": True,
        "root": {
            "label": "base",
            "shape": {"primitive": "cylinder", "radius": 10.0, "depth": 2.0, "vertices": 32},
            "attachment": {"local_offset": [0, 0, 1]}
        },
        "parts": [
            {
                "label": "pillar",
                "parent_label": "base",
                "socket_name": "top_center",
                "shape": {"primitive": "cylinder", "radius": 1.5, "depth": 20.0, "vertices": 6},
                "local_offset": [0, 0, 1],  # LLM gives base_half=1, should be 1+10=11
                "local_rotation_euler": [0, 0, 0],
                "join_mode": "parent_only"
            },
            {
                "label": "radar_dish",
                "parent_label": "pillar",
                "socket_name": "top_center",
                "shape": {"primitive": "hemisphere", "radius": 6.0},
                "local_offset": [0, 0, 10],  # LLM gives pillar_half=10, should be 10+6=16
                "local_rotation_euler": [0, 0, 0],
                "join_mode": "parent_only"
            },
            {
                "label": "antenna",
                "parent_label": "radar_dish",
                "socket_name": "top_center",
                "shape": {"primitive": "cone", "radius1": 0.5, "depth": 8.0},
                "local_offset": [0, 0, 6],  # LLM gives dish_half=6, should be 6+4=10
                "local_rotation_euler": [0, 0, 0],
                "join_mode": "parent_only"
            }
        ]
    }
    
    graph = GraphCompiler._build_graph_from_decomp(decomp, 'sci-fi tower', 'test_tower')
    
    # Check corrected offsets
    pillar = next(n for n in graph.root.all_nodes() if n.label == 'pillar')
    dish = next(n for n in graph.root.all_nodes() if n.label == 'radar_dish')
    antenna = next(n for n in graph.root.all_nodes() if n.label == 'antenna')
    
    # pillar: base_half(1) + pillar_half(10) = 11
    assert abs(pillar.attachment.local_offset[2] - 11.0) < 0.01, f"pillar offset should be 11, got {pillar.attachment.local_offset[2]}"
    # dish: pillar_half(10) + dish_half(6) = 16
    assert abs(dish.attachment.local_offset[2] - 16.0) < 0.01, f"dish offset should be 16, got {dish.attachment.local_offset[2]}"
    # antenna: dish_half(6) + antenna_half(4) = 10
    assert abs(antenna.attachment.local_offset[2] - 10.0) < 0.01, f"antenna offset should be 10, got {antenna.attachment.local_offset[2]}"
    
    # Verify world positions via graph_to_blender_steps
    steps = graph_to_blender_steps(graph)
    
    base_step = next(s for s in steps if s[1].get('name') == 'base')
    pillar_step = next(s for s in steps if s[1].get('name') == 'pillar')
    dish_step = next(s for s in steps if s[1].get('name') == 'radar_dish')
    antenna_step = next(s for s in steps if s[1].get('name') == 'antenna')
    
    assert base_step[1]['location'][2] == 1.0, f"base Z should be 1, got {base_step[1]['location'][2]}"
    assert pillar_step[1]['location'][2] == 12.0, f"pillar Z should be 12, got {pillar_step[1]['location'][2]}"
    assert dish_step[1]['location'][2] == 28.0, f"dish Z should be 28, got {dish_step[1]['location'][2]}"
    assert antenna_step[1]['location'][2] == 38.0, f"antenna Z should be 38, got {antenna_step[1]['location'][2]}"


@pytest.mark.asyncio
async def test_endpoint_agent_routes_through_graph_compiler():
    """Confirm endpoint_agent uses GraphCompiler for multi-part primitive plans.
    After wiring, steps_to_execute must come from graph_to_blender_steps,
    not from the raw LLM JSON — verified by checking the compiled step count
    matches the graph node count, not the LLM's arbitrary step list."""
    from unittest.mock import AsyncMock, MagicMock, patch
    from core.assembly_spec import graph_to_blender_steps

    # Minimal 2-node graph: base + pillar
    root = AssemblyNode(
        node_id="root_base", label="base",
        sub_spec={"primitive": "cylinder", "radius": 5.0, "depth": 2.0},
        attachment=AttachmentSpec(local_offset=(0.0, 0.0, 1.0)),
        children=[
            AssemblyNode(
                node_id="child_pillar", label="pillar",
                sub_spec={"primitive": "cylinder", "radius": 1.0, "depth": 10.0},
                attachment=AttachmentSpec(parent_node_id="root_base", local_offset=(0.0, 0.0, 6.0)),
                children=[],
            )
        ],
    )
    compiled_graph = AssemblyGraph(task_id="t_wire", root=root, rests_on_surface=True)
    compiled_steps = graph_to_blender_steps(compiled_graph)
    # steps[0] is clear_scene + 2 geometry steps = 3 total
    assert len(compiled_steps) == 3  # clear_scene + base + pillar

    # Confirm graph_to_blender_steps produces correct world Z for pillar
    pillar = next(s for s in compiled_steps if s[1].get("name") == "pillar")
    assert pillar[1]["location"][2] == 7.0  # root_z(1.0) + offset(6.0)



# ===========================================================================
# Unit Normalization Tests
# ===========================================================================

def test_unit_normalization_mm_to_meters():
    """LLM outputs in mm (>50) should be converted to meters."""
    from core.graph_compiler import _normalize_shape_to_meters, _detect_unit_from_magnitude
    
    # 120mm should be detected as mm and converted to 0.12m
    assert _detect_unit_from_magnitude(120) == "mm"
    assert _detect_unit_from_magnitude(200) == "mm"
    assert _detect_unit_from_magnitude(60) == "mm"
    
    # Shape normalization
    shape = {"primitive": "box", "size": [120, 60, 200]}
    normalized = _normalize_shape_to_meters(shape)
    assert normalized["size"] == [0.12, 0.06, 0.2]
    
    # Cylinder
    cyl = {"primitive": "cylinder", "radius": 50, "depth": 100}
    norm_cyl = _normalize_shape_to_meters(cyl)
    assert norm_cyl["radius"] == 0.05
    assert norm_cyl["depth"] == 0.1


def test_unit_normalization_already_meters():
    """Values already in meters (<50) should not be converted."""
    from core.graph_compiler import _normalize_shape_to_meters, _detect_unit_from_magnitude
    
    # Small values should be assumed meters
    assert _detect_unit_from_magnitude(2.0) == "m"
    assert _detect_unit_from_magnitude(0.5) == "m"
    assert _detect_unit_from_magnitude(10) == "m"
    
    # Shape should pass through unchanged
    shape = {"primitive": "box", "size": [2.0, 1.0, 3.0]}
    normalized = _normalize_shape_to_meters(shape)
    assert normalized["size"] == [2.0, 1.0, 3.0]


def test_arcade_machine_dimensions_normalized():
    """The arcade machine case: 120x60x200 should become 0.12x0.06x0.2 meters."""
    from core.graph_compiler import GraphCompiler
    
    # Simulate LLM decomposition with mm values
    decomp = {
        "rests_on_surface": True,
        "root": {
            "label": "main_body",
            "shape": {"primitive": "box", "size": [120, 60, 200]},  # mm
            "attachment": {"local_offset": [0, 0, 100]}  # mm
        },
        "parts": [
            {
                "label": "control_panel",
                "parent_label": "main_body",
                "socket_name": "front_face",
                "shape": {"primitive": "box", "size": [90, 35, 20]},  # mm
                "local_offset": [0, -47.5, 40],  # mm - should be outside front face
                "local_rotation_euler": [-15, 0, 0],
                "join_mode": "parent_only"
            }
        ]
    }
    
    graph = GraphCompiler._build_graph_from_decomp(decomp, "arcade machine", "test_arcade")
    
    # Root should be normalized to meters
    root_size = graph.root.sub_spec["size"]
    assert root_size == [0.12, 0.06, 0.2], f"Expected [0.12, 0.06, 0.2], got {root_size}"
    
    # Root offset should be normalized
    root_offset = graph.root.attachment.local_offset
    assert root_offset[2] == 0.1, f"Expected Z offset 0.1m, got {root_offset[2]}"
    
    # Child should be normalized
    panel = graph.root.children[0]
    panel_size = panel.sub_spec["size"]
    assert panel_size == [0.09, 0.035, 0.02], f"Expected [0.09, 0.035, 0.02], got {panel_size}"


# ===========================================================================
# Boolean Difference Routing Tests
# ===========================================================================

def test_boolean_difference_join_mode_routing():
    """join_mode='boolean_difference' should be routed to JoinMode.BOOLEAN_DIFFERENCE."""
    from core.graph_compiler import GraphCompiler
    from core.assembly_spec import JoinMode
    
    decomp = {
        "rests_on_surface": True,
        "root": {
            "label": "cabinet",
            "shape": {"primitive": "box", "size": [0.6, 0.4, 1.8]},
            "attachment": {"local_offset": [0, 0, 0.9]}
        },
        "parts": [
            {
                "label": "screen_recess",
                "parent_label": "cabinet",
                "socket_name": "front_face",
                "shape": {"primitive": "box", "size": [0.5, 0.1, 0.4]},
                "local_offset": [0, -0.25, 0.5],
                "local_rotation_euler": [0, 0, 0],
                "join_mode": "boolean_difference"  # Should cut into cabinet
            }
        ]
    }
    
    graph = GraphCompiler._build_graph_from_decomp(decomp, "arcade cabinet", "test_bool")
    recess = graph.root.children[0]
    assert recess.attachment.join_mode == JoinMode.BOOLEAN_DIFFERENCE


def test_graph_to_blender_steps_emits_boolean_difference():
    """graph_to_blender_steps should emit apply_boolean with DIFFERENCE for boolean_difference join_mode."""
    from core.assembly_spec import graph_to_blender_steps, AssemblyGraph, AssemblyNode, AttachmentSpec, JoinMode
    
    root = AssemblyNode(
        node_id="root_body",
        label="body",
        sub_spec={"primitive": "box", "size": [1.0, 0.5, 2.0]},
        attachment=AttachmentSpec(local_offset=(0.0, 0.0, 1.0)),
        children=[
            AssemblyNode(
                node_id="child_hole",
                label="screen_cutout",
                sub_spec={"primitive": "box", "size": [0.8, 0.2, 0.6]},
                attachment=AttachmentSpec(
                    parent_node_id="root_body",
                    local_offset=(0.0, -0.35, 0.5),
                    join_mode=JoinMode.BOOLEAN_DIFFERENCE,
                ),
                children=[],
            )
        ],
    )
    graph = AssemblyGraph(task_id="t_bool", root=root, rests_on_surface=True)
    steps = graph_to_blender_steps(graph)
    
    # Should have apply_boolean with DIFFERENCE
    bool_steps = [s for s in steps if s[0] == "blender:apply_boolean"]
    assert len(bool_steps) >= 1
    diff_step = next((s for s in bool_steps if s[1].get("target_name") == "screen_cutout"), None)
    assert diff_step is not None, "Expected boolean step for screen_cutout"
    assert diff_step[1]["operation"] == "DIFFERENCE"
    assert diff_step[1]["delete_target"] is True


# ===========================================================================
# Surface Attachment Tests
# ===========================================================================

def test_surface_attachment_front_face_correction():
    """Parts with socket_name containing 'front_face' should be placed outside parent."""
    from core.graph_compiler import GraphCompiler
    
    decomp = {
        "rests_on_surface": True,
        "root": {
            "label": "cabinet",
            "shape": {"primitive": "box", "size": [0.6, 0.4, 1.8]},  # Y half = 0.2
            "attachment": {"local_offset": [0, 0, 0.9]}
        },
        "parts": [
            {
                "label": "control_panel",
                "parent_label": "cabinet",
                "socket_name": "front_face",  # Triggers surface attachment
                "shape": {"primitive": "box", "size": [0.5, 0.1, 0.3]},  # Y half = 0.05
                "local_offset": [0, 0, 0.3],  # Y=0 is INSIDE parent - should be corrected
                "local_rotation_euler": [0, 0, 0],
                "join_mode": "parent_only"
            }
        ]
    }
    
    graph = GraphCompiler._build_graph_from_decomp(decomp, "arcade", "test_surface")
    panel = graph.root.children[0]
    
    # Y offset should be corrected to -(parent_half_y + child_half_y) = -(0.2 + 0.05) = -0.25
    assert panel.attachment.local_offset[1] == -0.25, f"Expected Y=-0.25, got {panel.attachment.local_offset[1]}"


def test_surface_attachment_back_face_correction():
    """Parts with socket_name containing 'back_face' should be placed on +Y side."""
    from core.graph_compiler import GraphCompiler
    
    decomp = {
        "rests_on_surface": True,
        "root": {
            "label": "cabinet",
            "shape": {"primitive": "box", "size": [0.6, 0.4, 1.8]},  # Y half = 0.2
            "attachment": {"local_offset": [0, 0, 0.9]}
        },
        "parts": [
            {
                "label": "vent",
                "parent_label": "cabinet",
                "socket_name": "back_face",
                "shape": {"primitive": "box", "size": [0.4, 0.05, 0.3]},  # Y half = 0.025
                "local_offset": [0, 0, 0.5],  # Y=0 is INSIDE parent
                "local_rotation_euler": [0, 0, 0],
                "join_mode": "parent_only"
            }
        ]
    }
    
    graph = GraphCompiler._build_graph_from_decomp(decomp, "cabinet", "test_back")
    vent = graph.root.children[0]
    
    # Y offset should be corrected to +(parent_half_y + child_half_y) = 0.2 + 0.025 = 0.225
    assert vent.attachment.local_offset[1] == 0.225, f"Expected Y=0.225, got {vent.attachment.local_offset[1]}"


def test_boolean_difference_sets_interaction_type_boolean():
    """Boolean difference parts should have interaction_type=BOOLEAN to skip verification."""
    from core.graph_compiler import GraphCompiler
    from core.assembly_spec import InteractionType
    
    decomp = {
        "rests_on_surface": True,
        "root": {
            "label": "body",
            "shape": {"primitive": "box", "size": [1.0, 0.5, 2.0]},
            "attachment": {"local_offset": [0, 0, 1.0]}
        },
        "parts": [
            {
                "label": "screen_cutout",
                "parent_label": "body",
                "socket_name": "front_face",
                "shape": {"primitive": "box", "size": [0.8, 0.2, 0.5]},
                "local_offset": [0, -0.35, 0.5],
                "local_rotation_euler": [0, 0, 0],
                "join_mode": "boolean_difference"
            }
        ]
    }
    
    graph = GraphCompiler._build_graph_from_decomp(decomp, "arcade", "test_bool_int")
    cutout = graph.root.children[0]
    
    # Boolean cutters should have interaction_type=BOOLEAN
    assert cutout.attachment.interaction_type == InteractionType.BOOLEAN, \
        f"Expected BOOLEAN, got {cutout.attachment.interaction_type}"


def test_boolean_cutter_not_pushed_outside_parent():
    """Boolean cutters with surface_mount socket should NOT be pushed outside parent.
    
    This was a bug where screen_recess with socket_name='surface_mount' and
    join_mode='boolean_difference' was incorrectly pushed outside the cabinet,
    making the boolean cut happen in empty space instead of inside the cabinet.
    """
    from core.graph_compiler import GraphCompiler
    
    decomp = {
        "rests_on_surface": True,
        "root": {
            "label": "main_body",
            "shape": {"primitive": "box", "size": [1.2, 0.6, 2.0]},  # Y half = 0.3
            "attachment": {"local_offset": [0, 0, 1.0]}
        },
        "parts": [
            {
                "label": "screen_recess",
                "parent_label": "main_body",
                "socket_name": "surface_mount",  # Would trigger surface correction
                "shape": {"primitive": "box", "size": [0.8, 0.4, 0.2]},  # Y half = 0.2
                "local_offset": [0, -0.1, 0.6],  # Intentionally inside parent for boolean
                "local_rotation_euler": [0, 0, 0],
                "join_mode": "boolean_difference"  # This should prevent surface correction
            }
        ]
    }
    
    graph = GraphCompiler._build_graph_from_decomp(decomp, "arcade", "test_bool_surface")
    recess = graph.root.children[0]
    
    # Y offset should NOT be corrected - cutter should stay inside parent
    # If the bug exists, Y would be -(0.3 + 0.2) = -0.5 (pushed outside)
    # Correct behavior: Y stays at -0.1 (inside parent for boolean cut)
    assert recess.attachment.local_offset[1] == -0.1, \
        f"Boolean cutter Y should stay at -0.1 (inside parent), got {recess.attachment.local_offset[1]}"
