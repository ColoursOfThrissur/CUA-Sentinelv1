"""Unit tests for Phase 2 of Progressive Assembly Pipeline v5.

Tests:
1. BuildFrontier refresh, actionable candidate filtering, and removal
2. SmartScheduler prioritization, blocking unblocking scoring, and retry backoff
3. RecursiveDecomposer stop conditions and hierarchy formation
"""

import pytest
from unittest.mock import AsyncMock, patch

from core.blender_pipeline.progressive.node_types import NodeKind, NodeImportance
from core.blender_pipeline.progressive.manifest import (
    NodeState,
    ManifestNode,
    BuildManifest,
)
from core.blender_pipeline.progressive.dependency_graph import DependencyDAG
from core.blender_pipeline.progressive.frontier import BuildFrontier
from core.blender_pipeline.progressive.scheduler import SmartScheduler
from core.blender_pipeline.progressive.decomposer import RecursiveDecomposer
from core.blender_pipeline.stage1_topology import PartTopology, PartNode


def test_frontier_actionable_filtering():
    """Verify that only READY nodes with VERIFIED dependencies enter frontier."""
    manifest = BuildManifest.create("Cannon Model", model_id="cannon_01")
    root_id = manifest.root_node_id

    # Create 3 nodes: base, barrel (depends on base), wheel (independent)
    base = ManifestNode("base", "base", kind=NodeKind.PART, parent_id=root_id, state=NodeState.READY)
    barrel = ManifestNode("barrel", "barrel", kind=NodeKind.PART, parent_id=root_id, state=NodeState.READY)
    wheel = ManifestNode("wheel", "wheel", kind=NodeKind.PART, parent_id=root_id, state=NodeState.READY)

    manifest.add_node(base)
    manifest.add_node(barrel)
    manifest.add_node(wheel)

    dag = DependencyDAG()
    dag.add_node("base")
    dag.add_node("barrel")
    dag.add_node("wheel")
    dag.add_dependency("barrel", "base")  # barrel depends on base

    frontier = BuildFrontier()
    actionable = frontier.refresh(manifest, dag)

    # Base and wheel should be actionable. Barrel is blocked by base.
    assert "base" in actionable
    assert "wheel" in actionable
    assert "barrel" not in actionable

    # Verify base
    manifest.transition("base", NodeState.BUILDING)
    manifest.transition("base", NodeState.VERIFYING)
    manifest.transition("base", NodeState.VERIFIED)

    # Refresh frontier: now barrel should become actionable
    actionable_after = frontier.refresh(manifest, dag)
    assert "barrel" in actionable_after
    assert "base" not in actionable_after


def test_smart_scheduler_prioritization():
    """Verify scheduler scores foundational and blocking nodes higher."""
    manifest = BuildManifest.create("Assembly", model_id="sched_test")
    dag = DependencyDAG()
    scheduler = SmartScheduler()

    # Node A unblocks 2 dependents. Node B unblocks 0 dependents.
    node_a = ManifestNode("A", "Node A", kind=NodeKind.PART, state=NodeState.READY)
    node_b = ManifestNode("B", "Node B", kind=NodeKind.PART, state=NodeState.READY)
    node_c = ManifestNode("C", "Node C", kind=NodeKind.PART, state=NodeState.READY)
    node_d = ManifestNode("D", "Node D", kind=NodeKind.PART, state=NodeState.READY)

    manifest.add_node(node_a)
    manifest.add_node(node_b)
    manifest.add_node(node_c)
    manifest.add_node(node_d)

    dag.add_dependency("C", "A")
    dag.add_dependency("D", "A")

    score_a = scheduler.score_node("A", manifest, dag)
    score_b = scheduler.score_node("B", manifest, dag)

    assert score_a > score_b

    # Picking next from ["A", "B"] should choose "A"
    best = scheduler.pick_next(["B", "A"], manifest, dag)
    assert best == "A"


def test_smart_scheduler_retry_backoff():
    """Verify that repeated failures reduce node priority."""
    manifest = BuildManifest.create("Retry Test", model_id="retry_test")
    dag = DependencyDAG()
    scheduler = SmartScheduler()

    n1 = ManifestNode("n1", "Part 1", kind=NodeKind.PART, state=NodeState.READY, retry_count=0)
    n2 = ManifestNode("n2", "Part 2", kind=NodeKind.PART, state=NodeState.READY, retry_count=3)

    manifest.add_node(n1)
    manifest.add_node(n2)

    score1 = scheduler.score_node("n1", manifest, dag)
    score2 = scheduler.score_node("n2", manifest, dag)

    assert score1 > score2


@pytest.mark.asyncio
async def test_recursive_decomposer_root():
    """Verify that RecursiveDecomposer splits root into child nodes."""
    manifest = BuildManifest.create("Desk Lamp", model_id="lamp_01")
    decomposer = RecursiveDecomposer()

    # Mock Stage1Topology response
    mock_stage1 = PartTopology(
        parts=[
            PartNode(label="base", primitive_type="cylinder", parent_label=None, socket_type="ROOT"),
            PartNode(label="pole", primitive_type="cylinder", parent_label="base", socket_type="TOP_CENTER"),
            PartNode(label="shade", primitive_type="cone", parent_label="pole", socket_type="TOP_CENTER"),
        ]
    )

    with patch("core.blender_pipeline.stage1_topology.Stage1Topology.run", new=AsyncMock(return_value=mock_stage1)):
        await decomposer.decompose_root(
            manifest=manifest,
            prompt="A minimalist desk lamp",
            stage0_output={"category": "furniture", "scale_anchor": {"overall_height_or_length_m": 0.5}},
        )

    # Root should have transitioned to READY
    assert manifest.get_root().state == NodeState.READY
    # Manifest should have 4 nodes total (root + 3 parts)
    assert len(manifest.nodes) == 4
    assert f"lamp_01_base" in manifest.nodes
    assert f"lamp_01_pole" in manifest.nodes
    assert f"lamp_01_shade" in manifest.nodes
