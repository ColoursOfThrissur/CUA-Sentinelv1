"""Tests for the transform audit system."""

import pytest
from typing import List, Optional
from dataclasses import dataclass, field

from .audit_transforms import (
    NodeAuditResult,
    ModelAuditResult,
    TransformProvenance,
    analyze_mismatch_pattern,
    generate_audit_report,
    audit_model_transforms,
    create_provenance,
)
from .transforms import LocalTransform, NodeTransformState


# ---------------------------------------------------------------------------
# Mock Node for Testing
# ---------------------------------------------------------------------------

@dataclass
class MockAttachment:
    parent_id: Optional[str] = None
    socket_type: Optional["MockSocketType"] = None
    resolution_method: str = "test"


@dataclass
class MockSocketType:
    value: str = "TOP_CENTER"


@dataclass
class MockNode:
    node_id: str
    label: str = ""
    attachment: Optional[MockAttachment] = None
    transform_state: Optional[NodeTransformState] = None
    
    def __post_init__(self):
        if not self.label:
            self.label = self.node_id


# ---------------------------------------------------------------------------
# Pattern Analysis Tests
# ---------------------------------------------------------------------------

class TestPatternAnalysis:
    """Test mismatch pattern analysis."""
    
    def test_no_mismatches(self):
        """No mismatches should return 'none' pattern."""
        pattern, hypothesis = analyze_mismatch_pattern([])
        assert pattern == "none"
        assert "match" in hypothesis.lower()
    
    def test_rotation_only_pattern(self):
        """Rotation-only mismatches should be detected."""
        mismatches = [
            NodeAuditResult(
                node_id="n1", label="n1", depth=1,
                position_delta=0.0001,  # Position matches
                rotation_delta=15.0,    # Rotation differs
                status="DIFFER",
            ),
            NodeAuditResult(
                node_id="n2", label="n2", depth=2,
                position_delta=0.0002,
                rotation_delta=15.0,
                status="DIFFER",
            ),
        ]
        
        pattern, hypothesis = analyze_mismatch_pattern(mismatches)
        assert pattern == "rotation_only"
        assert "rotation" in hypothesis.lower()
    
    def test_position_only_pattern(self):
        """Position-only mismatches should be detected."""
        mismatches = [
            NodeAuditResult(
                node_id="n1", label="n1", depth=1,
                position_delta=0.5,    # Position differs
                rotation_delta=0.01,   # Rotation matches
                status="DIFFER",
            ),
        ]
        
        pattern, hypothesis = analyze_mismatch_pattern(mismatches)
        assert pattern == "position_only"
        assert "position" in hypothesis.lower()
    
    def test_uniform_offset_pattern(self):
        """Uniform offset should be detected."""
        mismatches = [
            NodeAuditResult(
                node_id="n1", label="n1", depth=1,
                position_delta=0.1,
                rotation_delta=5.0,
                status="DIFFER",
            ),
            NodeAuditResult(
                node_id="n2", label="n2", depth=2,
                position_delta=0.1,  # Same delta
                rotation_delta=5.0,
                status="DIFFER",
            ),
            NodeAuditResult(
                node_id="n3", label="n3", depth=3,
                position_delta=0.1,  # Same delta
                rotation_delta=5.0,
                status="DIFFER",
            ),
        ]
        
        pattern, hypothesis = analyze_mismatch_pattern(mismatches)
        assert pattern == "uniform_offset"
        assert "root" in hypothesis.lower() or "frame" in hypothesis.lower()
    
    def test_socket_only_pattern(self):
        """Socket-only mismatches should be detected."""
        mismatches = [
            NodeAuditResult(
                node_id="n1", label="n1", depth=2,
                socket_type="TOP_CENTER",
                position_delta=0.1,
                rotation_delta=5.0,
                status="DIFFER",
            ),
            NodeAuditResult(
                node_id="n2", label="n2", depth=3,
                socket_type="CORNER",
                position_delta=0.2,
                rotation_delta=3.0,
                status="DIFFER",
            ),
        ]
        
        pattern, hypothesis = analyze_mismatch_pattern(mismatches)
        assert pattern == "socket_only"
        assert "socket" in hypothesis.lower()
    
    def test_depth_cascade_pattern(self):
        """Depth cascade (error compounds with depth) should be detected."""
        mismatches = [
            NodeAuditResult(
                node_id="n1", label="n1", depth=3,
                position_delta=0.1,
                rotation_delta=5.0,
                status="DIFFER",
            ),
            NodeAuditResult(
                node_id="n2", label="n2", depth=4,
                position_delta=0.2,  # Larger
                rotation_delta=5.0,
                status="DIFFER",
            ),
            NodeAuditResult(
                node_id="n3", label="n3", depth=5,
                position_delta=0.3,  # Even larger
                rotation_delta=5.0,
                status="DIFFER",
            ),
        ]
        
        pattern, hypothesis = analyze_mismatch_pattern(mismatches)
        assert pattern == "depth_cascade"
        assert "depth" in hypothesis.lower()


# ---------------------------------------------------------------------------
# Report Generation Tests
# ---------------------------------------------------------------------------

class TestReportGeneration:
    """Test audit report generation."""
    
    def test_all_match_report(self):
        """Report for all-matching model."""
        result = ModelAuditResult(
            model_name="test_model",
            total_nodes=5,
            match_count=5,
            differ_count=0,
            error_count=0,
        )
        
        report = generate_audit_report(result)
        
        assert "test_model" in report
        assert "Total nodes:  5" in report
        assert "MATCH:        5" in report
        assert "ALL NODES MATCH" in report
    
    def test_mismatch_report(self):
        """Report with mismatches should show details."""
        result = ModelAuditResult(
            model_name="problem_model",
            total_nodes=10,
            match_count=8,
            differ_count=2,
            error_count=0,
            pattern="rotation_only",
            root_cause_hypothesis="Check rotation conventions",
            mismatches=[
                NodeAuditResult(
                    node_id="barrel",
                    label="barrel",
                    depth=4,
                    parent_id="cannon",
                    socket_type="TOP_CENTER",
                    position_delta=0.0001,
                    rotation_delta=12.5,
                    status="DIFFER",
                    legacy_world_position=[1.0, 2.0, 3.0],
                    new_world_position=[1.0, 2.0, 3.0],
                ),
            ],
        )
        
        report = generate_audit_report(result)
        
        assert "problem_model" in report
        assert "DIFFER:       2" in report
        assert "PATTERN ANALYSIS" in report
        assert "rotation_only" in report
        assert "MISMATCHES" in report
        assert "barrel" in report
        assert "depth:          4" in report
        assert "12.5" in report


# ---------------------------------------------------------------------------
# Audit Runner Tests
# ---------------------------------------------------------------------------

class TestAuditRunner:
    """Test the audit runner."""
    
    def _make_node(
        self,
        node_id: str,
        parent_id: Optional[str] = None,
        socket_type: Optional[str] = None,
        local_pos: List[float] = None,
        local_rot: List[float] = None,
    ) -> MockNode:
        """Create a mock node with transform state."""
        local_pos = local_pos or [0, 0, 0]
        local_rot = local_rot or [0, 0, 0]
        
        attachment = None
        if parent_id:
            socket = MockSocketType(value=socket_type) if socket_type else None
            attachment = MockAttachment(parent_id=parent_id, socket_type=socket)
        
        transform_state = NodeTransformState()
        transform_state.set_local_transform(LocalTransform(
            position=local_pos,
            rotation=local_rot,
        ))
        
        return MockNode(
            node_id=node_id,
            attachment=attachment,
            transform_state=transform_state,
        )
    
    def test_audit_matching_transforms(self):
        """Audit should report MATCH for matching transforms."""
        # Create simple hierarchy
        root = self._make_node("root")
        root.transform_state.compute_world(None, -1)
        
        child = self._make_node("child", parent_id="root", local_pos=[0, 0, 1])
        child.transform_state.compute_world(
            root.transform_state.world_matrix,
            root.transform_state.revision,
        )
        
        nodes = [root, child]
        
        # Legacy transforms that match
        legacy = {
            "root": {"position": [0, 0, 0], "rotation": [0, 0, 0]},
            "child": {"position": [0, 0, 1], "rotation": [0, 0, 0]},
        }
        
        result = audit_model_transforms(nodes, legacy, "test_model")
        
        assert result.total_nodes == 2
        assert result.match_count == 2
        assert result.differ_count == 0
        assert result.pattern == "none"
    
    def test_audit_mismatching_transforms(self):
        """Audit should report DIFFER for mismatching transforms."""
        root = self._make_node("root")
        root.transform_state.compute_world(None, -1)
        
        child = self._make_node("child", parent_id="root", local_pos=[0, 0, 1])
        child.transform_state.compute_world(
            root.transform_state.world_matrix,
            root.transform_state.revision,
        )
        
        nodes = [root, child]
        
        # Legacy transforms that DON'T match
        legacy = {
            "root": {"position": [0, 0, 0], "rotation": [0, 0, 0]},
            "child": {"position": [0, 0, 2], "rotation": [0, 0, 0]},  # Wrong!
        }
        
        result = audit_model_transforms(nodes, legacy, "test_model")
        
        assert result.total_nodes == 2
        assert result.match_count == 1  # root matches
        assert result.differ_count == 1  # child differs
        assert len(result.mismatches) == 1
        assert result.mismatches[0].node_id == "child"


# ---------------------------------------------------------------------------
# Provenance Tests
# ---------------------------------------------------------------------------

class TestProvenance:
    """Test transform provenance records."""
    
    def test_create_provenance_root(self):
        """Provenance for root node."""
        node = MockNode(node_id="root", label="base")
        node.transform_state = NodeTransformState()
        node.transform_state.set_local_transform(LocalTransform.identity())
        node.transform_state.compute_world(None, -1)
        
        prov = create_provenance(node, depth=0)
        
        assert prov.node_id == "root"
        assert prov.parent_id is None
        assert prov.depth == 0
        assert prov.attachment_source == "ROOT"
    
    def test_create_provenance_child(self):
        """Provenance for child node with socket attachment."""
        node = MockNode(
            node_id="turret",
            label="turret",
            attachment=MockAttachment(
                parent_id="base",
                socket_type=MockSocketType(value="TOP_CENTER"),
                resolution_method="deterministic_socket_solver",
            ),
        )
        node.transform_state = NodeTransformState()
        node.transform_state.set_local_transform(LocalTransform(position=[0, 0, 0.5]))
        node.transform_state.compute_world(None, -1)
        
        prov = create_provenance(node, depth=1)
        
        assert prov.node_id == "turret"
        assert prov.parent_id == "base"
        assert prov.depth == 1
        assert prov.attachment_source == "TOP_CENTER"
        assert prov.resolver_type == "deterministic_socket_solver"
    
    def test_provenance_format_report(self):
        """Provenance should format as readable report."""
        prov = TransformProvenance(
            node_id="barrel",
            parent_id="cannon",
            depth=4,
            attachment_source="SOCKET_ATTACHMENT",
            resolver_type="deterministic_socket_solver",
            socket_info="barrel_mount → barrel_base",
            local_transform={
                "position": [0, 0, 0.3],
                "rotation": [0, 0, 0],
                "scale": [1, 1, 1],
            },
            revision=17,
            parent_revision=12,
        )
        
        report = prov.format_report()
        
        assert "barrel" in report
        assert "cannon" in report
        assert "Depth:" in report
        assert "4" in report
        assert "barrel_mount → barrel_base" in report
        assert "Revision:" in report
        assert "17" in report
    
    def test_provenance_to_dict(self):
        """Provenance should serialize to dict."""
        prov = TransformProvenance(
            node_id="test",
            parent_id="parent",
            depth=2,
            attachment_source="TOP_CENTER",
            resolver_type="test_resolver",
            socket_info=None,
        )
        
        d = prov.to_dict()
        
        assert d["node_id"] == "test"
        assert d["parent_id"] == "parent"
        assert d["depth"] == 2
        assert d["attachment_source"] == "TOP_CENTER"
