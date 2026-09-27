"""Tests for SceneTransaction — Phase 2 atomic rollback verification."""

import pytest
import asyncio
from unittest.mock import AsyncMock
from core.scene_transaction import SceneTransaction
from core.assembly_resolver import AssemblyResolver
from core.assembly_spec import AssemblyGraph, AssemblyNode, AttachmentSpec, JoinMode, PartParadigm


@pytest.mark.asyncio
async def test_scene_transaction_clean_commit():
    """Verify successful transaction commits without deleting objects."""
    deleted_calls = []

    async def mock_execute(tool_name, args):
        if tool_name == "blender:delete_object":
            deleted_calls.append(args.get("name"))
        return {"status": "ok", "data": {"ok": True}}

    mock_bridge = AsyncMock()
    mock_bridge.execute_tool = mock_execute

    txn = SceneTransaction(tool_executor=mock_bridge)
    async with txn:
        txn.record("part_a")
        txn.record("part_b")
        await txn.commit()

    assert txn.committed is True
    assert len(deleted_calls) == 0, "No rollback should occur on committed transaction"


@pytest.mark.asyncio
async def test_scene_transaction_atomic_rollback_on_exception():
    """Verify rollback deletes tracked objects in reverse order upon exception."""
    deleted_calls = []

    async def mock_execute(tool_name, args):
        if tool_name == "blender:delete_object":
            deleted_calls.append(args.get("name"))
        return {"status": "ok", "data": {"ok": True}}

    mock_bridge = AsyncMock()
    mock_bridge.execute_tool = mock_execute

    txn = SceneTransaction(tool_executor=mock_bridge)

    with pytest.raises(RuntimeError, match="Simulated mid-graph failure"):
        async with txn:
            txn.record("lamp_base")
            txn.record("lamp_stem")
            # Mid-graph crash (e.g. lamp_head throws NameError)
            raise RuntimeError("Simulated mid-graph failure")

    assert txn.committed is False
    assert txn.rolled_back is True
    # Reverse order: stem deleted before base
    assert deleted_calls == ["lamp_stem", "lamp_base"]


@pytest.mark.asyncio
async def test_assembly_resolver_rolls_back_on_mid_execution_error():
    """Verify AssemblyResolver automatically rolls back partial objects when a node fails."""
    deleted_calls = []
    created_calls = []

    async def mock_execute(tool_name, args):
        if tool_name == "blender:delete_object":
            deleted_calls.append(args.get("name"))
            return {"status": "ok", "data": {"ok": True}}
        if tool_name in ("blender:create_box", "blender:create_cylinder"):
            name = args.get("name")
            created_calls.append(name)
            if name == "lamp_head":
                raise RuntimeError("NameError: name 'math' is not defined")
            return {"status": "ok", "data": {"ok": True}}
        return {"status": "ok", "data": {"ok": True}}

    mock_bridge = AsyncMock()
    mock_bridge.execute_tool = mock_execute

    resolver = AssemblyResolver(mock_bridge)

    # Build 3-node graph: base -> stem -> head
    base = AssemblyNode(
        node_id="base_id",
        label="lamp_base",
        sub_spec={"primitive": "cylinder", "radius": 10.0, "depth": 2.0},
    )
    stem = AssemblyNode(
        node_id="stem_id",
        label="lamp_stem",
        sub_spec={"primitive": "cylinder", "radius": 1.0, "depth": 40.0},
        attachment=AttachmentSpec(local_offset=(0, 0, 21)),
    )
    head = AssemblyNode(
        node_id="head_id",
        label="lamp_head",
        sub_spec={"primitive": "box", "size": [25, 5, 2]},
        attachment=AttachmentSpec(local_offset=(0, 0, 21)),
    )
    stem.children.append(head)
    base.children.append(stem)

    graph = AssemblyGraph(
        schema_version="2.0",
        task_id="test_atomic_rollback",
        root=base,
    )

    res = await resolver.resolve(graph)

    assert res["ok"] is False
    assert "rolled_back" in res and res["rolled_back"] is True
    # Head threw error, so base and stem must have been rolled back
    assert "lamp_head" in created_calls
    assert "lamp_stem" in deleted_calls
    assert "lamp_base" in deleted_calls
