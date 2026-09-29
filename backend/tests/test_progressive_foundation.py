"""Unit tests for Phase 1 of Progressive Assembly Pipeline v5.

Tests:
1. NodeState transitions and legal/illegal edges
2. ManifestNode serialization and deserialization
3. BuildManifest creation, node addition/removal, queries, and completion status
4. BuildManifest atomic save/load and checkpointing
5. ContainmentTree hierarchy constraints (depth, max children, total nodes, cycles)
6. DependencyDAG topological sorting, dependency depth, ready-node filtering, and cycle detection
"""

import os
import pytest
from pathlib import Path

from core.blender_pipeline.progressive.node_types import NodeKind, NodeImportance
from core.blender_pipeline.progressive.manifest import (
    NodeState,
    CompletionStatus,
    ManifestNode,
    BuildManifest,
)
from core.blender_pipeline.progressive.hierarchy import ContainmentTree, HierarchyError
from core.blender_pipeline.progressive.dependency_graph import DependencyDAG, CycleError


def test_node_state_transitions():
    """Verify valid state transitions and rejection of invalid edges."""
    manifest = BuildManifest.create("Test model", model_id="test_model_001")
    root_id = manifest.root_node_id

    # Root starts in PLANNED
    assert manifest.get_node(root_id).state == NodeState.PLANNED

    # PLANNED -> READY is valid
    manifest.transition(root_id, NodeState.READY)
    assert manifest.get_node(root_id).state == NodeState.READY

    # READY -> BUILDING is valid
    manifest.transition(root_id, NodeState.BUILDING)
    assert manifest.get_node(root_id).state == NodeState.BUILDING

    # BUILDING -> PLANNED is illegal
    with pytest.raises(ValueError, match="Illegal state transition"):
        manifest.transition(root_id, NodeState.PLANNED)

    # BUILDING -> VERIFYING is valid
    manifest.transition(root_id, NodeState.VERIFYING)
    # VERIFYING -> VERIFIED is valid
    manifest.transition(root_id, NodeState.VERIFIED)
    assert manifest.get_node(root_id).state == NodeState.VERIFIED


def test_manifest_node_serialization():
    """Verify round-trip serialization of ManifestNode."""
    node = ManifestNode(
        node_id="part_1",
        label="wheel_front_left",
        kind=NodeKind.PART,
        state=NodeState.READY,
        importance=NodeImportance.REQUIRED,
        parent_id="assembly_1",
        children_ids=["child_a", "child_b"],
        dependency_ids=["dep_1"],
        instance_of="wheel_def",
        retry_count=1,
        max_retries=3,
        error_message=None,
        hierarchy_depth=2,
        stage_outputs={"stage2": {"radius": 0.3}},
        verification_result={"passed": True},
        blender_objects=["gen_wheel_mesh"],
        generation_id="gen_12345",
        public_sockets=[{"name": "axle_socket"}],
        bounding_info={"radius": 0.3},
    )

    data = node.to_dict()
    reconstructed = ManifestNode.from_dict(data)

    assert reconstructed.node_id == "part_1"
    assert reconstructed.label == "wheel_front_left"
    assert reconstructed.kind == NodeKind.PART
    assert reconstructed.state == NodeState.READY
    assert reconstructed.importance == NodeImportance.REQUIRED
    assert reconstructed.children_ids == ["child_a", "child_b"]
    assert reconstructed.stage_outputs == {"stage2": {"radius": 0.3}}
    assert reconstructed.blender_objects == ["gen_wheel_mesh"]


def test_manifest_completion_status():
    """Verify completion status computation (SUCCESS, COMPLETED_DEGRADED, FAILED)."""
    manifest = BuildManifest.create("Car model", model_id="test_car")
    root_id = manifest.root_node_id

    # Add 1 required part and 1 optional part
    p_req = ManifestNode(
        node_id="req_engine",
        label="engine",
        kind=NodeKind.PART,
        parent_id=root_id,
        importance=NodeImportance.REQUIRED,
    )
    p_opt = ManifestNode(
        node_id="opt_spoiler",
        label="spoiler",
        kind=NodeKind.PART,
        parent_id=root_id,
        importance=NodeImportance.OPTIONAL,
    )
    manifest.add_node(p_req)
    manifest.add_node(p_opt)
    manifest.get_root().children_ids.extend(["req_engine", "opt_spoiler"])

    # Initially in progress
    assert manifest.compute_completion_status() == CompletionStatus.IN_PROGRESS

    # When required part is verified, and optional part is skipped -> COMPLETED_DEGRADED
    manifest.nodes["req_engine"].state = NodeState.VERIFIED
    manifest.nodes["opt_spoiler"].state = NodeState.SKIPPED
    assert manifest.compute_completion_status() == CompletionStatus.COMPLETED_DEGRADED

    # When optional part is also verified -> SUCCESS
    manifest.nodes["opt_spoiler"].state = NodeState.VERIFIED
    assert manifest.compute_completion_status() == CompletionStatus.SUCCESS

    # When required part fails -> FAILED
    manifest.nodes["req_engine"].state = NodeState.FAILED
    assert manifest.compute_completion_status() == CompletionStatus.FAILED


def test_manifest_persistence_and_checkpoints(tmp_path):
    """Verify save, load, and checkpointing functionality."""
    manifest = BuildManifest.create("Pirate ship", model_id="ship_01")
    manifest.stage0_output = {"category": "vehicle", "scale_anchor_m": 25.0}
    
    # Save checkpoint
    file_path = tmp_path / "manifest.json"
    manifest.save(file_path)
    assert file_path.exists()

    loaded = BuildManifest.load(file_path)
    assert loaded.model_id == "ship_01"
    assert loaded.description == "Pirate ship"
    assert loaded.stage0_output["category"] == "vehicle"

    # Add checkpoint
    manifest.checkpoint(label="checkpoint_hull_verified")
    assert len(manifest.checkpoints) == 1
    assert manifest.checkpoints[0]["label"] == "checkpoint_hull_verified"


def test_containment_tree_operations():
    """Verify ContainmentTree child addition, safety limits, and subtree removal."""
    manifest = BuildManifest.create("Robot", model_id="robot_01")
    tree = ContainmentTree(manifest)
    root_id = manifest.root_node_id

    # Add assembly
    torso = tree.add_child(root_id, "torso", "Torso Assembly", kind=NodeKind.ASSEMBLY)
    assert torso.hierarchy_depth == 1
    assert torso.node_id in manifest.get_root().children_ids

    # Add leaf under torso
    chest = tree.add_child("torso", "chest_panel", "Chest Panel", kind=NodeKind.PART)
    assert chest.hierarchy_depth == 2

    # Verify ancestors and leaves
    assert tree.get_ancestors("chest_panel") == ["torso", root_id]
    leaves = [n.node_id for n in tree.get_leaves()]
    assert "chest_panel" in leaves
    assert "torso" not in leaves

    # Validation should pass
    errors = tree.validate()
    assert errors == []

    # Remove subtree
    removed = tree.remove_subtree("torso")
    assert "torso" in removed
    assert "chest_panel" in removed
    assert "torso" not in manifest.nodes
    assert "chest_panel" not in manifest.nodes
    assert manifest.get_root().children_ids == []


def test_containment_tree_safety_limits():
    """Verify maximum depth and children limit enforcement."""
    manifest = BuildManifest.create("Deep model", model_id="deep_01")
    tree = ContainmentTree(manifest)

    # Exceed max children
    parent_id = manifest.root_node_id
    for i in range(ContainmentTree.MAX_CHILDREN_PER_NODE):
        tree.add_child(parent_id, f"child_{i}", f"Child {i}")

    with pytest.raises(HierarchyError, match="already has .* children"):
        tree.add_child(parent_id, "overflow_child", "Overflow Child")


def test_dependency_dag_topological_sort():
    """Verify topological sort and build frontier readiness."""
    dag = DependencyDAG()
    
    # cannon -> armament -> deck -> ship
    dag.add_node("ship")
    dag.add_node("deck")
    dag.add_node("armament")
    dag.add_node("cannon")

    dag.add_dependency("deck", "armament")
    dag.add_dependency("ship", "deck")
    dag.add_dependency("armament", "cannon")

    order = dag.topological_sort()
    assert order == ["cannon", "armament", "deck", "ship"]

    # Test ready nodes
    ready = dag.get_ready_nodes(completed=set())
    assert ready == ["cannon"]

    ready_after_cannon = dag.get_ready_nodes(completed={"cannon"})
    assert ready_after_cannon == ["armament"]

    # Test dependency depth
    assert dag.dependency_depth("cannon") == 0
    assert dag.dependency_depth("armament") == 1
    assert dag.dependency_depth("ship") == 3


def test_dependency_dag_cycle_detection():
    """Verify that cycles raise CycleError."""
    dag = DependencyDAG()
    dag.add_dependency("A", "B")
    dag.add_dependency("B", "C")

    # Adding C -> A should raise CycleError
    with pytest.raises(CycleError, match="Dependency cycle detected"):
        dag.add_dependency("C", "A")
