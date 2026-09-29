"""Unit and integration tests for Phase 4 of Progressive Assembly Pipeline v5.

Tests:
1. ProgressiveNodeExecutor builds and verifies leaf primitives
2. ProgressiveNodeExecutor merges verified child objects
3. ToolGateway routes blender:build_progressive to ProgressiveAssemblyController
4. ToolGateway routes blender:build_spec with pipeline_version='v5' to v5
5. ToolGateway preserves v4 fallback when pipeline_version is not v5
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from core.blender_pipeline.progressive.node_types import NodeKind, NodeImportance
from core.blender_pipeline.progressive.manifest import (
    NodeState,
    ManifestNode,
    BuildManifest,
)
from core.blender_pipeline.progressive.node_executor import ProgressiveNodeExecutor
from core.tool_gateway import ToolGateway


@pytest.mark.asyncio
async def test_node_executor_leaf_build():
    """Verify ProgressiveNodeExecutor creates and verifies a leaf box primitive."""
    mock_mcp = AsyncMock()
    # Mock returns the name that executor generates (includes label)
    mock_mcp.call_locked = AsyncMock(
        return_value={"output": 'SENTINEL_OUTPUT_START{"ok": true, "name": "g12345678_tabletop"}SENTINEL_OUTPUT_END'}
    )

    manifest = BuildManifest.create("Table", model_id="exec_test_01")
    node = ManifestNode(
        node_id="part_top",
        label="tabletop",
        kind=NodeKind.PART,
        stage_outputs={
            "stage1": {"primitive_type": "box"},
            "stage2": {"dimensions": {"size": [1.0, 0.8, 0.05]}},
        },
    )
    manifest.add_node(node)

    executor = ProgressiveNodeExecutor(mcp_manager=mock_mcp)

    res = await executor.execute_leaf_node(node, manifest, task_id="test_leaf")

    assert res["ok"] is True
    assert len(node.blender_objects) == 1
    assert "tabletop" in node.blender_objects[0]


@pytest.mark.asyncio
async def test_node_executor_assembly_merge():
    """Verify ProgressiveNodeExecutor merges children and runs spatial verification."""
    mock_mcp = AsyncMock()
    mock_mcp.call_locked = AsyncMock(
        return_value={"output": 'SENTINEL_OUTPUT_START{"ok": true}SENTINEL_OUTPUT_END'}
    )

    manifest = BuildManifest.create("Table", model_id="merge_test_01")
    root_id = manifest.root_node_id

    c1 = ManifestNode("p1", "top", kind=NodeKind.PART, parent_id=root_id, state=NodeState.VERIFIED, blender_objects=["g_top"])
    c2 = ManifestNode("p2", "leg", kind=NodeKind.PART, parent_id=root_id, state=NodeState.VERIFIED, blender_objects=["g_leg"])
    manifest.add_node(c1)
    manifest.add_node(c2)
    manifest.get_root().children_ids = ["p1", "p2"]

    executor = ProgressiveNodeExecutor(mcp_manager=mock_mcp)

    with patch("core.assembly_verification.AssemblyVerificationGate.verify_flat_object_set", new=AsyncMock(return_value={"all_joints_verified": True})):
        res = await executor.execute_assembly_merge(manifest.get_root(), manifest, task_id="test_merge")

    assert res["ok"] is True


@pytest.mark.asyncio
async def test_tool_gateway_routing_progressive():
    """Verify ToolGateway dispatches blender:build_progressive to ProgressiveAssemblyController."""
    # Ensure handlers are registered
    ToolGateway.register_default_handlers()
    
    mock_controller_res = MagicMock(
        success=True,
        completion_status=MagicMock(value="success"),
        total_nodes=3,
        verified_nodes=3,
        failed_nodes=0,
        skipped_nodes=0,
        manifest=MagicMock(model_id="test_model_v5"),
        error=None,
    )

    with patch("core.blender_pipeline.progressive.controller.ProgressiveAssemblyController.run", new=AsyncMock(return_value=mock_controller_res)):
        handler = ToolGateway._TOOL_HANDLERS["blender:build_progressive"]
        res = await handler(description="a wooden stool", task_id="task_prog_test")

    assert res["ok"] is True
    assert res["status"] == "success"
    assert res["total_nodes"] == 3


@pytest.mark.asyncio
async def test_tool_gateway_routing_build_spec_v5():
    """Verify ToolGateway routes blender:build_spec to v5 (now the only pipeline)."""
    # Ensure handlers are registered
    ToolGateway.register_default_handlers()
    
    mock_controller_res = MagicMock(
        success=True,
        completion_status=MagicMock(value="success"),
        total_nodes=2,
        verified_nodes=2,
        failed_nodes=0,
        skipped_nodes=0,
        manifest=MagicMock(model_id="test_model_spec_v5"),
        error=None,
    )

    with patch("core.blender_pipeline.progressive.controller.ProgressiveAssemblyController.run", new=AsyncMock(return_value=mock_controller_res)):
        handler = ToolGateway._TOOL_HANDLERS["blender:build_spec"]
        # No pipeline_version needed - v5 is now the default
        res = await handler(description="a dumbbell", task_id="task_spec_v5")

    assert res["ok"] is True
    assert res["status"] == "success"
    assert res["model_id"] == "test_model_spec_v5"


@pytest.mark.asyncio
async def test_tool_gateway_routing_build_spec_always_v5():
    """Verify blender:build_spec always uses v5 progressive pipeline (v4 removed)."""
    # Ensure handlers are registered
    ToolGateway.register_default_handlers()
    
    mock_controller_res = MagicMock(
        success=True,
        completion_status=MagicMock(value="success"),
        total_nodes=1,
        verified_nodes=1,
        failed_nodes=0,
        skipped_nodes=0,
        manifest=MagicMock(model_id="test_v5_only"),
        error=None,
    )

    with patch("core.blender_pipeline.progressive.controller.ProgressiveAssemblyController.run", new=AsyncMock(return_value=mock_controller_res)):
        handler = ToolGateway._TOOL_HANDLERS["blender:build_spec"]
        # Even without any flags, should use v5
        res = await handler(description="a mug", task_id="task_v5_only")

    assert res["ok"] is True
    assert res["status"] == "success"
    # Confirms v5 was used (has model_id from progressive result)
    assert res["model_id"] == "test_v5_only"
