"""Unit tests for Phase 5 of Progressive Assembly Pipeline v5.

Tests:
1. InstanceManager detects instance candidates from similar labels
2. InstanceManager creates definition nodes and links instances
3. InstanceManager builds instance from verified definition
4. RelationshipGraph adds and retrieves relationships
5. RelationshipGraph resolves pending relationships when both endpoints verified
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from core.blender_pipeline.progressive.node_types import NodeKind, NodeImportance
from core.blender_pipeline.progressive.manifest import (
    NodeState,
    ManifestNode,
    BuildManifest,
)
from core.blender_pipeline.progressive.instances import InstanceManager
from core.blender_pipeline.progressive.relationships import (
    RelationshipGraph,
    CrossAssemblyRelationship,
    SocketAnchor,
)


def test_instance_candidate_detection():
    """InstanceManager detects nodes with similar labels as instance candidates."""
    manifest = BuildManifest.create("Table with 4 legs", model_id="inst_test_01")
    
    # Add 4 legs with numbered suffixes
    for i in range(1, 5):
        leg = ManifestNode(
            node_id=f"leg_{i}",
            label=f"leg_{i}",
            kind=NodeKind.PART,
            parent_id=manifest.root_node_id,
        )
        manifest.add_node(leg)
    
    # Add unique parts
    top = ManifestNode("top", "tabletop", kind=NodeKind.PART, parent_id=manifest.root_node_id)
    manifest.add_node(top)
    
    mgr = InstanceManager()
    candidates = mgr.detect_instance_candidates(manifest)
    
    # Should detect "leg" as having 4 candidates
    assert "leg" in candidates
    assert len(candidates["leg"]) == 4
    # "tabletop" should not be a candidate (only 1 instance)
    assert "tabletop" not in candidates


def test_instance_definition_creation():
    """InstanceManager creates definition node and links instances."""
    manifest = BuildManifest.create("Chair", model_id="inst_test_02")
    
    leg_ids = []
    for i in range(1, 5):
        leg = ManifestNode(
            node_id=f"leg_{i}",
            label=f"leg_{i}",
            kind=NodeKind.PART,
            parent_id=manifest.root_node_id,
            stage_outputs={"stage1": {"primitive_type": "cylinder"}},
        )
        manifest.add_node(leg)
        leg_ids.append(f"leg_{i}")
    
    mgr = InstanceManager()
    def_id = mgr.create_definition_node(manifest, "leg", leg_ids)
    
    assert def_id is not None
    assert def_id in manifest.nodes
    
    # Definition should exist
    definition = manifest.nodes[def_id]
    assert definition.kind == NodeKind.DEFINITION
    assert "leg" in definition.label
    
    # All legs should now be instances
    for leg_id in leg_ids:
        leg = manifest.nodes[leg_id]
        assert leg.kind == NodeKind.INSTANCE
        assert leg.instance_of == def_id


@pytest.mark.asyncio
async def test_instance_build_from_definition():
    """InstanceManager builds instance by copying verified definition geometry."""
    manifest = BuildManifest.create("Stool", model_id="inst_test_03")
    
    # Create verified definition
    definition = ManifestNode(
        node_id="def_leg",
        label="leg_definition",
        kind=NodeKind.DEFINITION,
        state=NodeState.VERIFIED,
        blender_objects=["g_def_leg"],
    )
    manifest.add_node(definition)
    
    # Create instance referencing definition
    instance = ManifestNode(
        node_id="leg_1",
        label="leg_1",
        kind=NodeKind.INSTANCE,
        instance_of="def_leg",
        stage_outputs={"stage4": {"location": [0.2, 0.2, 0], "rotation": [0, 0, 0]}},
    )
    manifest.add_node(instance)
    
    # Mock MCP
    mock_mcp = AsyncMock()
    mock_mcp.call_locked = AsyncMock(
        return_value={"output": 'SENTINEL_OUTPUT_START{"ok": true, "name": "inst_leg_1"}SENTINEL_OUTPUT_END'}
    )
    
    mgr = InstanceManager(mcp_manager=mock_mcp)
    result = await mgr.build_instance_from_definition(instance, manifest, task_id="test")
    
    assert result["ok"] is True
    assert len(instance.blender_objects) == 1


def test_relationship_graph_add_and_retrieve():
    """RelationshipGraph adds relationships and retrieves by node."""
    graph = RelationshipGraph()
    
    rel_id = graph.add_relationship(
        source_node_id="mast",
        source_socket="top_center",
        target_node_id="sail",
        target_socket="bottom_center",
        connector_type="cable",
    )
    
    assert rel_id in graph.relationships
    rel = graph.relationships[rel_id]
    assert rel.source_anchor.node_id == "mast"
    assert rel.target_anchor.node_id == "sail"
    assert rel.connector_type == "cable"
    
    # Retrieve by node
    mast_rels = graph.get_relationships_for_node("mast")
    assert len(mast_rels) == 1
    assert mast_rels[0].relationship_id == rel_id


def test_relationship_pending_detection():
    """RelationshipGraph identifies pending relationships when both endpoints verified."""
    manifest = BuildManifest.create("Ship", model_id="rel_test_01")
    
    mast = ManifestNode("mast", "mast", kind=NodeKind.PART, state=NodeState.VERIFIED, blender_objects=["g_mast"])
    sail = ManifestNode("sail", "sail", kind=NodeKind.PART, state=NodeState.VERIFIED, blender_objects=["g_sail"])
    hull = ManifestNode("hull", "hull", kind=NodeKind.PART, state=NodeState.BUILDING)  # Not verified
    
    manifest.add_node(mast)
    manifest.add_node(sail)
    manifest.add_node(hull)
    
    graph = RelationshipGraph()
    graph.add_relationship("mast", "top_center", "sail", "bottom_center")
    graph.add_relationship("hull", "top_center", "mast", "bottom_center")  # hull not verified
    
    pending = graph.get_pending_relationships(manifest)
    
    # Only mast-sail should be pending (both verified)
    assert len(pending) == 1
    assert pending[0].source_anchor.node_id == "mast"


@pytest.mark.asyncio
async def test_relationship_resolution():
    """RelationshipGraph resolves socket positions and creates connector."""
    manifest = BuildManifest.create("Bridge", model_id="rel_test_02")
    
    tower1 = ManifestNode("tower1", "tower_1", kind=NodeKind.PART, state=NodeState.VERIFIED, blender_objects=["g_tower1"])
    tower2 = ManifestNode("tower2", "tower_2", kind=NodeKind.PART, state=NodeState.VERIFIED, blender_objects=["g_tower2"])
    manifest.add_node(tower1)
    manifest.add_node(tower2)
    
    mock_mcp = AsyncMock()
    # Mock socket position queries and connector creation
    mock_mcp.call_locked = AsyncMock(
        side_effect=[
            {"output": 'SENTINEL_OUTPUT_START{"ok": true, "position": [0, 0, 1]}SENTINEL_OUTPUT_END'},
            {"output": 'SENTINEL_OUTPUT_START{"ok": true, "position": [2, 0, 1]}SENTINEL_OUTPUT_END'},
            {"output": 'SENTINEL_OUTPUT_START{"ok": true, "name": "connector_rel_tower1_tower2"}SENTINEL_OUTPUT_END'},
        ]
    )
    
    graph = RelationshipGraph(mcp_manager=mock_mcp)
    rel_id = graph.add_relationship("tower1", "top_center", "tower2", "top_center", connector_type="cable")
    
    rel = graph.relationships[rel_id]
    result = await graph.resolve_relationship(rel, manifest, task_id="test")
    
    assert result["ok"] is True
    assert rel.verified is True
    assert rel.source_anchor.world_position == [0, 0, 1]
    assert rel.target_anchor.world_position == [2, 0, 1]


def test_relationship_serialization():
    """RelationshipGraph serializes and deserializes for checkpointing."""
    graph = RelationshipGraph()
    graph.add_relationship("a", "top_center", "b", "bottom_center", connector_type="rod")
    graph.relationships["rel_a_b"].verified = True
    graph.relationships["rel_a_b"].connector_object = "connector_a_b"
    
    data = graph.to_dict()
    
    restored = RelationshipGraph.from_dict(data)
    
    assert "rel_a_b" in restored.relationships
    rel = restored.relationships["rel_a_b"]
    assert rel.source_anchor.node_id == "a"
    assert rel.target_anchor.node_id == "b"
    assert rel.connector_type == "rod"
    assert rel.verified is True
    assert rel.connector_object == "connector_a_b"
