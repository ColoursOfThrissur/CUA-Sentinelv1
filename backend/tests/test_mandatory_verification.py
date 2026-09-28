"""Tests for AssemblyVerificationGate — Phase 4 mandatory verification tests."""

import pytest
from unittest.mock import AsyncMock
from core.assembly_verification import AssemblyVerificationGate
from core.assembly_spec import AssemblyGraph, AssemblyNode, AttachmentSpec, PartParadigm


@pytest.mark.asyncio
async def test_single_node_ground_plane_passes():
    """Verify that a 1-node cube sitting flush at Z >= 0 passes verification."""
    mock_bridge = AsyncMock()
    # z_min is 0.0 (sitting flush on ground)
    mock_bridge.call_internal = AsyncMock(return_value={"ok": True, "z_min": 0.0})

    verifier = AssemblyVerificationGate(mock_bridge)

    cube = AssemblyNode(
        node_id="cube_1",
        label="cube",
        paradigm=PartParadigm.PRIMITIVE,
        sub_spec={"primitive": "box", "size": [2, 2, 2]},
        attachment=AttachmentSpec(local_offset=(0, 0, 1.0)),
    )
    graph = AssemblyGraph(schema_version="2.0", task_id="t1", root=cube)

    res = await verifier.verify(graph)
    assert res["ok"] is True
    assert res["all_joints_verified"] is True
    assert len(res["failed_joints"]) == 0


@pytest.mark.asyncio
async def test_buried_stem_fails_ground_plane_verification():
    """Verify that an object penetrating below ground (e.g. stem with Z_min = -0.17m) FAILS verification."""
    mock_bridge = AsyncMock()
    # z_min is -0.17 (penetrating 17cm below Z=0)
    mock_bridge.call_internal = AsyncMock(return_value={"ok": True, "z_min": -0.17})

    verifier = AssemblyVerificationGate(mock_bridge)

    buried_stem = AssemblyNode(
        node_id="stem_faulty",
        label="stem",
        paradigm=PartParadigm.PRIMITIVE,
        sub_spec={"primitive": "cylinder", "radius": 1, "depth": 40},
        attachment=AttachmentSpec(local_offset=(0, 0, 3.0)),  # faulty uncentered offset
    )
    graph = AssemblyGraph(schema_version="2.0", task_id="t2", root=buried_stem)

    res = await verifier.verify(graph)
    assert res["ok"] is False, "Buried object must fail verification"
    assert "stem_faulty" in res["failed_joints"]
    assert "Ground plane violation" in res["error"]


@pytest.mark.asyncio
async def test_full_pipeline_buried_stem_rolls_back_and_fails():
    """Phase 4 key gate: Feed uncorrected lamp coordinates with buried stem into full AssemblyResolver.
    Assert it FAILS spatial verification and triggers automatic scene rollback,
    instead of wrongly reporting VERIFIED_AND_LOADED.
    """
    from core.assembly_resolver import AssemblyResolver

    deleted_objects = []
    internal_calls = []

    async def mock_execute(tool_name, args):
        if tool_name == "blender:delete_object":
            deleted_objects.append(args.get("name"))
        return {"status": "ok", "data": {"ok": True}}

    async def mock_internal(op, kwargs):
        code = kwargs.get("code", "")
        internal_calls.append(code)
        
        # Track safe deletes from SceneTransaction rollback
        if "bpy.data.objects.remove" in code and "sentinel_generation_id" in code:
            # Extract object name from the script params
            import re
            match = re.search(r'"name":\s*"([^"]+)"', code)
            if match:
                deleted_objects.append(match.group(1))
            return {"ok": True, "deleted": True}
        
        if "z_min" in code:
            if "lamp_base" in code:
                return {"ok": True, "z_min": 0.0}
            if "lamp_stem" in code:
                # Uncorrected stem penetrates down to -17cm (-0.17m)
                return {"ok": True, "z_min": -0.17}
        return {"ok": True, "signed_distance_mm": 0.0}

    mock_bridge = AsyncMock()
    mock_bridge.execute_tool = mock_execute
    mock_bridge.call_internal = mock_internal

    # Create uncorrected lamp where stem is placed at [0, 0, 3] instead of [0, 0, 22]
    # base is 2cm high resting on ground Z=0..2 (centroid Z=1)
    base = AssemblyNode(
        node_id="base_1",
        label="lamp_base",
        sub_spec={"primitive": "cylinder", "radius": 10, "depth": 2},
        attachment=AttachmentSpec(local_offset=(0, 0, 1.0)),
    )
    # stem is 40cm high, uncorrected offset places it through the base
    stem = AssemblyNode(
        node_id="stem_1",
        label="lamp_stem",
        sub_spec={"primitive": "cylinder", "radius": 1, "depth": 40},
        attachment=AttachmentSpec(local_offset=(0, 0, 2.0)),
    )
    base.children.append(stem)

    graph = AssemblyGraph(schema_version="2.0", task_id="test_lamp_failure", root=base)

    resolver = AssemblyResolver(mock_bridge)
    result = await resolver.resolve(graph)

    # Must NOT report VERIFIED_AND_LOADED!
    assert result["ok"] is False, "Uncorrected buried stem must fail resolution"
    assert result.get("rolled_back") is True, "Scene must be rolled back on spatial failure"
    # Check that rollback was attempted (either via delete_object or internal script)
    assert len(deleted_objects) > 0 or any("remove" in c for c in internal_calls), \
        "Rollback must attempt to delete objects"
    assert graph.status == "FAILED"


@pytest.mark.asyncio
async def test_failed_joints_deduped_and_namespaced_in_failed_checks():
    """Verify that multiple failed checks on the same node produce deduplicated failed_joints
    and namespaced entries in failed_checks with reserved __ground_plane__ prefix."""
    mock_bridge = AsyncMock()

    async def mock_internal(op, kwargs):
        code = kwargs.get("code", "")
        if "z_min" in code:
            # Fails ground plane check (penetrates 10cm)
            return {"ok": True, "z_min": -0.10}
        # Fails joint gap check (15mm gap)
        return {"ok": True, "signed_distance_mm": 15.0}

    mock_bridge.call_internal = mock_internal
    verifier = AssemblyVerificationGate(mock_bridge)

    base = AssemblyNode(
        node_id="base_node",
        label="base",
        sub_spec={"primitive": "box", "size": [2, 2, 2]},
        attachment=AttachmentSpec(local_offset=(0, 0, 1.0)),
    )
    stem = AssemblyNode(
        node_id="stem_node",
        label="stem",
        sub_spec={"primitive": "cylinder", "radius": 1, "depth": 10},
        attachment=AttachmentSpec(socket_name="base.socket", local_offset=(0, 0, 5.0), mating_tolerance_mm=2.0),
    )
    base.children.append(stem)
    graph = AssemblyGraph(schema_version="2.0", task_id="t_dedup", root=base)

    res = await verifier.verify(graph)
    assert res["ok"] is False

    # Assert node_id appears exactly once in failed_joints (deduplicated)
    assert res["failed_joints"].count("stem_node") == 1, "failed_joints must contain stem_node exactly once"

    # Assert failures are explicitly namespaced in failed_checks
    assert "stem_node:__ground_plane__" in res["failed_checks"], "Must namespace ground plane failure with reserved __ground_plane__"
    assert "stem_node:base.socket" in res["failed_checks"], "Must namespace joint failure with socket name"


@pytest.mark.asyncio
async def test_bidirectional_penetration_script_generation():
    """Verify that _measure_joint_gap generates code testing BOTH parent and child BVH trees symmetrically."""
    captured_scripts = []

    async def mock_internal(op, kwargs):
        captured_scripts.append(kwargs.get("code", ""))
        return {"ok": True, "signed_distance_mm": 0.0}

    mock_bridge = AsyncMock()
    mock_bridge.call_internal = mock_internal
    verifier = AssemblyVerificationGate(mock_bridge)

    gap = await verifier._measure_joint_gap(parent_label="parent_lip", child_label="child_socket", socket_name="lip_joint")
    assert gap == 0.0
    assert len(captured_scripts) == 1

    script = captured_scripts[0]
    # Symmetrical verification asserts:
    assert "p_bvh = BVHTree.FromObject(p_eval, dg)" in script, "Must build parent BVH"
    assert "c_bvh = BVHTree.FromObject(c_eval, dg)" in script, "Must build child BVH"
    assert "c_pen, c_gap = evaluate_directional_distance(c_eval, c_mw, p_bvh, p_mw_inv)" in script, "Must test child against parent"
    assert "p_pen, p_gap = evaluate_directional_distance(p_eval, p_mw, c_bvh, c_mw_inv)" in script, "Must test parent against child"
    assert "max_penetration = max(c_pen, p_pen)" in script, "Must take worst-case penetration symmetrically"


@pytest.mark.asyncio
async def test_aabb_contact_filtering_in_joint_script():
    """Verify that _measure_joint_gap generates AABB early-exit and uniform stride downsampling."""
    captured_scripts = []

    async def mock_internal(op, kwargs):
        captured_scripts.append(kwargs.get("code", ""))
        # Return skipped=True to simulate no AABB overlap
        return {"ok": True, "skipped": True, "reason": "no_aabb_overlap"}

    mock_bridge = AsyncMock()
    mock_bridge.call_internal = mock_internal
    verifier = AssemblyVerificationGate(mock_bridge)

    result = await verifier._measure_joint_gap(parent_label="p_mesh", child_label="c_mesh", socket_name="socket")
    script = captured_scripts[0]

    # Verify AABB overlap computation exists
    assert "has_aabb_overlap = (min_x <= max_x) and (min_y <= max_y) and (min_z <= max_z)" in script, "Must compute 3D AABB overlap"
    # Verify early-exit for non-overlapping AABBs (the fix)
    assert "if not has_aabb_overlap:" in script, "Must early-exit when no AABB overlap"
    assert '"skipped": True' in script, "Must return skipped=True for non-overlapping AABBs"
    assert '"reason": "no_aabb_overlap"' in script, "Must include reason for skip"
    # Verify uniform stride sampling still present for overlapping case
    assert "candidates = candidates[::step]" in script, "Must uniform-stride sample across contact candidates"
    assert "[:128]" not in script, "Arbitrary 128 head-slice must be eliminated"
    # Verify the function returns None for skipped case
    assert result is None, "Must return None when AABB check is skipped"
