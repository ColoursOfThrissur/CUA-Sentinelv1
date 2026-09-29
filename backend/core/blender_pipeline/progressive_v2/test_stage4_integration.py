"""Tests for Phase 2: Stage 4 → AttachmentSolution → transform_state integration.

Run with: pytest backend/core/blender_pipeline/progressive_v2/test_stage4_integration.py -v
"""

import math
import pytest
from .manifest import BuildManifest, ManifestNode, GeometrySpec, AttachmentSpec
from .node_types import NodeKind, SocketType, PrimitiveType
from .stages import Stage4Resolver, AttachmentSolution, ResolvedTransform
from .transforms import LocalTransform, NodeTransformState


class TestResolvedTransformBridge:
    """Test ResolvedTransform → LocalTransform conversion."""
    
    def test_to_local_transform_basic(self):
        """ResolvedTransform should convert to LocalTransform correctly."""
        rt = ResolvedTransform(
            offset=[1.0, 2.0, 3.0],
            rotation=[0.1, 0.2, 0.3],
            scale=[1.0, 1.0, 1.0],
        )
        lt = rt.to_local_transform()
        
        assert lt.position == [1.0, 2.0, 3.0]
        assert lt.rotation == [0.1, 0.2, 0.3]
        assert lt.scale == [1.0, 1.0, 1.0]
    
    def test_to_local_transform_preserves_radians(self):
        """Rotation should remain in radians (not converted)."""
        rt = ResolvedTransform(
            offset=[0, 0, 0],
            rotation=[math.pi/2, 0, 0],  # 90 degrees in radians
        )
        lt = rt.to_local_transform()
        
        assert abs(lt.rotation[0] - math.pi/2) < 1e-6


class TestAttachmentSolution:
    """Test AttachmentSolution creation and serialization."""
    
    def test_from_resolved_transform(self):
        """AttachmentSolution should be creatable from ResolvedTransform."""
        rt = ResolvedTransform(
            offset=[1.0, 0.0, 0.5],
            rotation=[0.0, 0.0, 0.0],
            resolution_method="TOP_CENTER",
        )
        
        sol = AttachmentSolution.from_resolved_transform(
            resolved=rt,
            parent_id="parent_001",
            child_id="child_001",
            socket_type=SocketType.TOP_CENTER,
        )
        
        assert sol.parent_id == "parent_001"
        assert sol.child_id == "child_001"
        assert sol.parent_socket == "TOP_CENTER"
        assert sol.source == "TOP_CENTER"
        assert sol.local_transform.position == [1.0, 0.0, 0.5]
    
    def test_to_dict_serialization(self):
        """AttachmentSolution should serialize to dict for logging."""
        sol = AttachmentSolution(
            parent_id="p1",
            child_id="c1",
            parent_socket="TOP_CENTER",
            local_transform=LocalTransform.from_position(1, 2, 3),
            source="test_resolver",
        )
        
        d = sol.to_dict()
        
        assert d["parent_id"] == "p1"
        assert d["child_id"] == "c1"
        assert d["source"] == "test_resolver"
        assert d["local_transform"]["position"] == [1, 2, 3]


class TestStage4ResolverReturnType:
    """Test that Stage4Resolver.run returns (ResolvedTransform, AttachmentSolution)."""
    
    def _create_test_manifest(self):
        """Create a minimal manifest for testing."""
        manifest = BuildManifest.create("test model")
        
        # Add MODEL root
        model = ManifestNode(
            node_id="model_001",
            label="test_model",
            kind=NodeKind.MODEL,
            parent_id=None,
            hierarchy_depth=0,
        )
        manifest.nodes[model.node_id] = model
        manifest.root_id = model.node_id
        
        # Add ASSEMBLY
        assembly = ManifestNode(
            node_id="asm_001",
            label="test_assembly",
            kind=NodeKind.ASSEMBLY,
            parent_id=model.node_id,
            hierarchy_depth=1,
            attachment=AttachmentSpec(socket_type=SocketType.ROOT),
        )
        manifest.nodes[assembly.node_id] = assembly
        model.children_ids.append(assembly.node_id)
        
        # Add ROOT PART with geometry
        root_part = ManifestNode(
            node_id="part_001",
            label="base",
            kind=NodeKind.PART,
            parent_id=assembly.node_id,
            hierarchy_depth=2,
            attachment=AttachmentSpec(socket_type=SocketType.ROOT),
            geometry=GeometrySpec(primitive=PrimitiveType.BOX, size=[1.0, 1.0, 0.5]),
        )
        root_part.stage_outputs["stage2"] = {"size_x": 1.0, "size_y": 1.0, "size_z": 0.5}
        manifest.nodes[root_part.node_id] = root_part
        assembly.children_ids.append(root_part.node_id)
        
        # Add TOP_CENTER PART
        top_part = ManifestNode(
            node_id="part_002",
            label="top_piece",
            kind=NodeKind.PART,
            parent_id=assembly.node_id,
            hierarchy_depth=2,
            attachment=AttachmentSpec(socket_type=SocketType.TOP_CENTER),
            geometry=GeometrySpec(primitive=PrimitiveType.BOX, size=[0.5, 0.5, 0.3]),
        )
        top_part.stage_outputs["stage2"] = {"size_x": 0.5, "size_y": 0.5, "size_z": 0.3}
        top_part.stage_outputs["stage3"] = {}
        manifest.nodes[top_part.node_id] = top_part
        assembly.children_ids.append(top_part.node_id)
        
        return manifest, root_part, top_part
    
    def test_run_returns_tuple(self):
        """Stage4Resolver.run should return (ResolvedTransform, AttachmentSolution)."""
        manifest, root_part, top_part = self._create_test_manifest()
        
        # Simulate root part being built (so it has bbox)
        root_part.bounding_box = {"min": [-0.5, -0.5, -0.25], "max": [0.5, 0.5, 0.25]}
        
        # Run Stage 4 on top_part
        result = Stage4Resolver.run(top_part, manifest)
        
        # Should return a tuple
        assert isinstance(result, tuple)
        assert len(result) == 2
        
        resolved, solution = result
        assert isinstance(resolved, ResolvedTransform)
        assert isinstance(solution, AttachmentSolution)
    
    def test_run_root_socket(self):
        """ROOT socket should return identity transform."""
        manifest, root_part, _ = self._create_test_manifest()
        
        resolved, solution = Stage4Resolver.run(root_part, manifest)
        
        assert resolved.resolution_method == "ROOT"
        assert resolved.offset == [0.0, 0.0, 0.0]
        assert solution.source == "ROOT"
        assert solution.local_transform.position == [0.0, 0.0, 0.0]
    
    def test_run_top_center_socket(self):
        """TOP_CENTER socket should compute correct offset."""
        manifest, root_part, top_part = self._create_test_manifest()
        
        # Simulate root part being built
        root_part.bounding_box = {"min": [-0.5, -0.5, -0.25], "max": [0.5, 0.5, 0.25]}
        
        resolved, solution = Stage4Resolver.run(top_part, manifest)
        
        # TOP_CENTER: child sits on top of parent
        # Parent max_z = 0.25, child min_z = -0.15 (half of 0.3)
        # Expected offset_z = 0.25 + 0.15 = 0.40
        assert "TOP_CENTER" in resolved.resolution_method
        assert abs(resolved.offset[2] - 0.40) < 0.01
        
        # Solution should match
        assert abs(solution.local_transform.position[2] - 0.40) < 0.01
    
    def test_legacy_run_method(self):
        """run_legacy should return only ResolvedTransform for backward compat."""
        manifest, root_part, _ = self._create_test_manifest()
        
        result = Stage4Resolver.run_legacy(root_part, manifest)
        
        assert isinstance(result, ResolvedTransform)
        assert result.resolution_method == "ROOT"


class TestTransformStateIntegration:
    """Test that AttachmentSolution integrates with NodeTransformState."""
    
    def test_solution_to_transform_state(self):
        """AttachmentSolution.local_transform should work with NodeTransformState."""
        sol = AttachmentSolution(
            parent_id="p1",
            child_id="c1",
            local_transform=LocalTransform.from_position(1, 2, 3),
            source="test",
        )
        
        state = NodeTransformState()
        state.set_local_transform(sol.local_transform)
        
        assert state.local_transform.position == [1, 2, 3]
        assert state.revision == 1  # Should have incremented
    
    def test_world_computation_from_solution(self):
        """World matrix should be computable from AttachmentSolution chain."""
        # Parent at origin
        parent_state = NodeTransformState()
        parent_state.set_local_transform(LocalTransform.from_position(10, 0, 0))
        parent_world = parent_state.compute_world(None, -1)
        
        # Child solution: offset (5, 0, 0) from parent
        child_sol = AttachmentSolution(
            parent_id="parent",
            child_id="child",
            local_transform=LocalTransform.from_position(5, 0, 0),
            source="TOP_CENTER",
        )
        
        child_state = NodeTransformState()
        child_state.set_local_transform(child_sol.local_transform)
        child_world = child_state.compute_world(parent_world, parent_state.revision)
        
        # Child should be at (15, 0, 0)
        assert abs(child_world.position[0] - 15.0) < 1e-5
