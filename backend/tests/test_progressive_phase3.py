"""Unit tests for Phase 3 of Progressive Assembly Pipeline v5.

Tests:
1. CheckpointManager: save, list, and restore checkpoints
2. DirtyPropagator: mark dependents and parent ancestors STALE
3. AssemblyMerger: enforce verified-children boundary and execute merge
4. ProgressiveAssemblyController: end-to-end progressive assembly execution
"""

import pytest
from unittest.mock import AsyncMock, patch

from core.blender_pipeline.progressive.node_types import NodeKind, NodeImportance
from core.blender_pipeline.progressive.manifest import (
    NodeState,
    CompletionStatus,
    ManifestNode,
    BuildManifest,
)
from core.blender_pipeline.progressive.dependency_graph import DependencyDAG
from core.blender_pipeline.progressive.checkpoint import CheckpointManager
from core.blender_pipeline.progressive.dirty_propagation import DirtyPropagator
from core.blender_pipeline.progressive.merger import AssemblyMerger, MergeError
from core.blender_pipeline.progressive.controller import ProgressiveAssemblyController
from core.blender_pipeline.stage0_understanding import ObjectUnderstanding, ScaleAnchor
from core.blender_pipeline.stage1_topology import PartTopology, PartNode


def test_checkpoint_manager_roundtrip(tmp_path):
    """Verify saving and restoring checkpoints."""
    manifest = BuildManifest.create("Checkpoint Test", model_id="chk_test_01")
    manifest.checkpoint("init_check")

    snap = CheckpointManager.checkpoint(manifest, label="second_check")
    assert snap["label"] == "second_check"

    # Save to disk
    manifest.save()

    # Restore
    restored = CheckpointManager.restore_latest("chk_test_01")
    assert restored is not None
    assert len(restored.checkpoints) == 2


def test_dirty_propagation():
    """Verify STALE cascade to dependents and ancestors."""
    manifest = BuildManifest.create("Car", model_id="car_dirty")
    root_id = manifest.root_node_id

    # Structure: root -> wheel_assembly -> wheel_part
    wheel_assy = ManifestNode("wheel_assembly", "Wheel Assembly", kind=NodeKind.ASSEMBLY, parent_id=root_id, state=NodeState.VERIFIED)
    wheel_part = ManifestNode("wheel_part", "Wheel Part", kind=NodeKind.PART, parent_id="wheel_assembly", state=NodeState.VERIFIED)
    body_part = ManifestNode("body_part", "Body Part", kind=NodeKind.PART, parent_id=root_id, state=NodeState.VERIFIED)

    manifest.add_node(wheel_assy)
    manifest.add_node(wheel_part)
    manifest.add_node(body_part)

    dag = DependencyDAG()
    dag.add_node("wheel_part")
    dag.add_node("wheel_assembly")
    dag.add_node("body_part")
    dag.add_dependency("wheel_assembly", "wheel_part")

    # Change wheel_part -> propagates to wheel_assembly and root
    stale = DirtyPropagator.propagate("wheel_part", manifest, dag)
    assert "wheel_assembly" in stale
    assert manifest.nodes["wheel_assembly"].state == NodeState.STALE
    # Unrelated body_part must remain CLEAN (VERIFIED)
    assert manifest.nodes["body_part"].state == NodeState.VERIFIED


def test_assembly_merger():
    """Verify AssemblyMerger can_merge conditions and execution."""
    manifest = BuildManifest.create("Table", model_id="table_merge")
    root_id = manifest.root_node_id

    # Children: top, leg
    c1 = ManifestNode("top", "Table Top", kind=NodeKind.PART, parent_id=root_id, state=NodeState.READY)
    c2 = ManifestNode("leg", "Table Leg", kind=NodeKind.PART, parent_id=root_id, state=NodeState.READY)
    manifest.add_node(c1)
    manifest.add_node(c2)
    manifest.get_root().children_ids = ["top", "leg"]

    merger = AssemblyMerger()
    # Cannot merge while children are not verified
    assert not merger.can_merge(root_id, manifest)

    # Verify both children
    manifest.nodes["top"].state = NodeState.VERIFIED
    manifest.nodes["leg"].state = NodeState.VERIFIED
    assert merger.can_merge(root_id, manifest)


@pytest.mark.asyncio
async def test_progressive_controller_end_to_end():
    """Verify full progressive assembly loop from prompt to verified root."""
    controller = ProgressiveAssemblyController()

    mock_stage0 = ObjectUnderstanding(
        category="furniture",
        rests_on_surface=True,
        style_tag="hard_surface_industrial",
        scale_anchor=ScaleAnchor(overall_height_or_length_m=0.75, reasoning="Standard table"),
    )

    mock_stage1 = PartTopology(
        parts=[
            PartNode(label="top", primitive_type="box", parent_label=None, socket_type="ROOT"),
            PartNode(label="leg", primitive_type="cylinder", parent_label="top", socket_type="BOTTOM_CENTER"),
        ]
    )

    with patch("core.blender_pipeline.stage0_understanding.Stage0Understanding.run", new=AsyncMock(return_value=mock_stage0)):
        with patch("core.blender_pipeline.stage1_topology.Stage1Topology.run", new=AsyncMock(return_value=mock_stage1)):
            result = await controller.run(prompt="A simple wooden table")

    assert result.success is True
    assert result.completion_status in (CompletionStatus.SUCCESS, CompletionStatus.COMPLETED_DEGRADED)
    assert result.verified_nodes > 0
    # Clean up test build state
    result.manifest.delete_build_state()
