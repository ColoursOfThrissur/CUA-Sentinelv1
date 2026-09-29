"""Comprehensive Mock Tests for Progressive Pipeline Stages.

Tests each stage with mocked LLM responses to identify issues in:
- Decomposition (Stage 1)
- Dimensions (Stage 2)
- Semantics (Stage 3)
- Transform Resolution (Stage 4)
- Position/Rotation computation
- Material/Modifier inference

Run with: pytest tests/test_pipeline_stages_mock.py -v
"""

import pytest
import json
import math
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, Any, List

# Import pipeline components
from core.blender_pipeline.progressive_v2.manifest import (
    BuildManifest,
    ManifestNode,
    GeometrySpec,
    AttachmentSpec,
    NodeState,
)
from core.blender_pipeline.progressive_v2.node_types import (
    NodeKind,
    NodeImportance,
    SocketType,
    PrimitiveType,
)
from core.blender_pipeline.progressive_v2.decomposer import (
    RecursiveDecomposer,
    DecomposedChild,
    DecompositionResult,
)
from core.blender_pipeline.progressive_v2.stages.stage2_dimensions import (
    Stage2Dimensions,
    DimensionsOutput,
)
from core.blender_pipeline.progressive_v2.stages.stage3_semantics import (
    Stage3Semantics,
    SOCKET_SEMANTICS,
)
from core.blender_pipeline.progressive_v2.stages.stage4_resolver import (
    Stage4Resolver,
    ResolvedTransform,
    BBox,
)


def _run(node, manifest):
    """Unpack Stage4Resolver.run() tuple and return just the ResolvedTransform."""
    resolved, _ = Stage4Resolver.run(node, manifest)
    return resolved


# ============================================================================
# Mock Model Manager
# ============================================================================

class MockModelManager:
    """Mock model manager that returns predefined LLM responses."""
    
    def __init__(self):
        self.responses: Dict[str, str] = {}
        self.call_log: List[Dict] = []
    
    def set_response(self, key: str, response: str):
        """Set response for a specific call pattern."""
        self.responses[key] = response
    
    def get_model_for_workflow(self, workflow: str) -> str:
        return "mock_model"
    
    async def generate_async(
        self,
        model_id: str,
        task_id: str,
        lease_id: str,
        lease_generation: int,
        system_prompt: str,
        prompt: str,
        temperature: float = 0.1,
    ) -> str:
        """Return mocked response based on task_id pattern."""
        self.call_log.append({
            "task_id": task_id,
            "prompt": prompt,
            "system_prompt": system_prompt[:100],
        })
        
        # Find matching response
        for key, response in self.responses.items():
            if key in task_id or key in prompt:
                return response
        
        # Default empty response
        return "{}"


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def mock_model_manager():
    return MockModelManager()


@pytest.fixture
def simple_manifest():
    """Create a simple manifest for testing."""
    return BuildManifest.create("simple wooden table")


@pytest.fixture
def ladder_manifest():
    """Create manifest for step ladder (from logs)."""
    return BuildManifest.create("simple wooden step ladder")


# ============================================================================
# PART 1: Decomposition Tests
# ============================================================================

class TestDecomposerLLMParsing:
    """Test decomposer's handling of various LLM responses."""
    
    @pytest.mark.asyncio
    async def test_simple_flat_decomposition(self, mock_model_manager):
        """Test flat decomposition like table with legs."""
        llm_response = json.dumps({
            "is_simple": True,
            "children": [
                {"label": "tabletop", "kind": "part", "primitive": "box", 
                 "socket_type": "ROOT", "importance": "required",
                 "material_hint": "dark wood", "style_hint": "smooth"},
                {"label": "leg_front_left", "kind": "part", "primitive": "cylinder",
                 "socket_type": "CORNER", "importance": "required",
                 "material_hint": "dark wood", "style_hint": "smooth"},
                {"label": "leg_front_right", "kind": "part", "primitive": "cylinder",
                 "socket_type": "CORNER", "importance": "required",
                 "material_hint": "dark wood", "style_hint": "smooth"},
            ]
        })
        
        mock_model_manager.set_response("decompose", llm_response)
        
        manifest = BuildManifest.create("wooden table")
        decomposer = RecursiveDecomposer()
        
        stats = await decomposer.decompose(
            manifest=manifest,
            model_manager=mock_model_manager,
            task_id="test_table",
        )
        
        # Verify structure
        assert stats["total_nodes"] == 4  # root + 3 parts
        assert stats["llm_calls"] == 1
        
        # Verify parts created correctly
        parts = manifest.get_parts()
        assert len(parts) == 3
        
        labels = {p.label for p in parts}
        assert "tabletop" in labels
        assert "leg_front_left" in labels
    
    @pytest.mark.asyncio
    async def test_nested_assembly_decomposition(self, mock_model_manager):
        """Test nested assembly like desk fan."""
        llm_response = json.dumps({
            "is_simple": False,
            "children": [
                {
                    "label": "base_assembly",
                    "kind": "assembly",
                    "socket_type": "ROOT",
                    "is_complex": True,
                    "children": [
                        {"label": "base", "kind": "part", "primitive": "cylinder",
                         "socket_type": "ROOT", "material_hint": "black plastic"},
                        {"label": "stand", "kind": "part", "primitive": "cylinder",
                         "socket_type": "TOP_CENTER", "material_hint": "chrome"},
                    ]
                }
            ]
        })
        
        mock_model_manager.set_response("decompose", llm_response)
        
        manifest = BuildManifest.create("desk fan")
        decomposer = RecursiveDecomposer()
        
        stats = await decomposer.decompose(
            manifest=manifest,
            model_manager=mock_model_manager,
            task_id="test_fan",
        )
        
        # Should have: root MODEL + base_assembly + base + stand
        assert stats["total_nodes"] >= 3
        
        # Verify hierarchy
        assemblies = manifest.get_assemblies()
        assert len(assemblies) >= 1
    
    @pytest.mark.asyncio
    async def test_custom_socket_with_position_hint(self, mock_model_manager):
        """Test CUSTOM socket parsing (ladder rungs)."""
        llm_response = json.dumps({
            "is_simple": True,
            "children": [
                {"label": "left_rail", "kind": "part", "primitive": "box",
                 "socket_type": "ROOT", "material_hint": "light wood"},
                {"label": "right_rail", "kind": "part", "primitive": "box",
                 "socket_type": "CUSTOM", "material_hint": "light wood",
                 "position_hint": "parallel to left_rail, 0.4m to the right"},
                {"label": "rung_bottom", "kind": "part", "primitive": "box",
                 "socket_type": "CUSTOM", "material_hint": "light wood",
                 "position_hint": "horizontal bar at 0.2m height"},
            ]
        })
        
        mock_model_manager.set_response("decompose", llm_response)
        
        manifest = BuildManifest.create("step ladder")
        decomposer = RecursiveDecomposer()
        
        await decomposer.decompose(
            manifest=manifest,
            model_manager=mock_model_manager,
            task_id="test_ladder",
        )
        
        # Verify CUSTOM sockets have position_hint stored
        right_rail = manifest.get_node_by_label("right_rail")
        assert right_rail is not None
        assert right_rail.attachment.socket_type == SocketType.CUSTOM
        
        decomp_hint = right_rail.stage_outputs.get("decomposition_hint", {})
        assert "position_hint" in decomp_hint
        assert "0.4m" in decomp_hint["position_hint"]
    
    @pytest.mark.asyncio
    async def test_malformed_json_recovery(self, mock_model_manager):
        """Test recovery from malformed LLM JSON."""
        # JSON with markdown wrapper
        llm_response = """```json
{
    "is_simple": true,
    "children": [
        {"label": "base", "kind": "part", "primitive": "box"}
    ]
}
```"""
        
        mock_model_manager.set_response("decompose", llm_response)
        
        manifest = BuildManifest.create("simple box")
        decomposer = RecursiveDecomposer()
        
        stats = await decomposer.decompose(
            manifest=manifest,
            model_manager=mock_model_manager,
            task_id="test_malformed",
        )
        
        # Should still parse successfully
        assert stats["total_nodes"] >= 2
    
    @pytest.mark.asyncio
    async def test_missing_primitive_defaults_to_box(self, mock_model_manager):
        """Test that missing primitive defaults to box."""
        llm_response = json.dumps({
            "is_simple": True,
            "children": [
                {"label": "my_part", "kind": "part", "socket_type": "ROOT"}
                # No primitive specified
            ]
        })
        
        mock_model_manager.set_response("decompose", llm_response)
        
        manifest = BuildManifest.create("thing")
        decomposer = RecursiveDecomposer()
        
        await decomposer.decompose(
            manifest=manifest,
            model_manager=mock_model_manager,
            task_id="test_default",
        )
        
        # Get the PART node (not the MODEL root)
        parts = manifest.get_parts()
        assert len(parts) == 1
        my_part = parts[0]
        assert my_part.label == "my_part"
        assert my_part.geometry is not None
        assert my_part.geometry.primitive == PrimitiveType.BOX
    
    @pytest.mark.asyncio
    async def test_invalid_socket_type_defaults(self, mock_model_manager):
        """Test that invalid socket type defaults correctly."""
        llm_response = json.dumps({
            "is_simple": True,
            "children": [
                {"label": "base", "kind": "part", "primitive": "box",
                 "socket_type": "INVALID_SOCKET"},
                {"label": "top", "kind": "part", "primitive": "box",
                 "socket_type": "ALSO_INVALID"},
            ]
        })
        
        mock_model_manager.set_response("decompose", llm_response)
        
        manifest = BuildManifest.create("test")
        decomposer = RecursiveDecomposer()
        
        await decomposer.decompose(
            manifest=manifest,
            model_manager=mock_model_manager,
            task_id="test_invalid_socket",
        )
        
        # First should default to ROOT, second to TOP_CENTER
        base = manifest.get_node_by_label("base")
        top = manifest.get_node_by_label("top")
        
        # Invalid sockets should fall back to defaults
        assert base is not None
        assert top is not None


# ============================================================================
# PART 2: Stage 2 Dimensions Tests
# ============================================================================

class TestStage2Dimensions:
    """Test dimension assignment from LLM responses."""
    
    @pytest.mark.asyncio
    async def test_box_dimensions(self, mock_model_manager):
        """Test box dimension parsing."""
        llm_response = json.dumps({
            "size_x": 1.0,
            "size_y": 0.6,
            "size_z": 0.05,
            "reasoning": "Standard tabletop dimensions"
        })
        
        mock_model_manager.set_response("stage2", llm_response)
        
        manifest = BuildManifest.create("table")
        manifest.stage0_output = {
            "scale_anchor_m": {"overall_height_or_length": 0.75}
        }
        
        # Create a part node
        node = manifest.add_child_node(
            parent_id=manifest.root_node_id,
            label="tabletop",
            kind=NodeKind.PART,
            geometry=GeometrySpec(primitive=PrimitiveType.BOX),
        )
        
        result = await Stage2Dimensions.run(
            node=node,
            manifest=manifest,
            model_manager=mock_model_manager,
            task_id="test_dims",
        )
        
        assert result.size_x == 1.0
        assert result.size_y == 0.6
        assert result.size_z == 0.05
    
    @pytest.mark.asyncio
    async def test_cylinder_dimensions(self, mock_model_manager):
        """Test cylinder dimension parsing."""
        llm_response = json.dumps({
            "radius": 0.03,
            "depth": 0.72,
            "reasoning": "Table leg"
        })
        
        mock_model_manager.set_response("stage2", llm_response)
        
        manifest = BuildManifest.create("table")
        manifest.stage0_output = {
            "scale_anchor_m": {"overall_height_or_length": 0.75}
        }
        
        node = manifest.add_child_node(
            parent_id=manifest.root_node_id,
            label="leg",
            kind=NodeKind.PART,
            geometry=GeometrySpec(primitive=PrimitiveType.CYLINDER),
        )
        
        result = await Stage2Dimensions.run(
            node=node,
            manifest=manifest,
            model_manager=mock_model_manager,
            task_id="test_cyl",
        )
        
        assert result.radius == 0.03
        assert result.depth == 0.72
    
    @pytest.mark.asyncio
    async def test_negative_dimensions_rejected(self, mock_model_manager):
        """Test that negative dimensions use defaults."""
        llm_response = json.dumps({
            "size_x": -1.0,
            "size_y": 0.5,
            "size_z": 0.0,  # Zero should also use default
            "reasoning": "Bad dimensions"
        })
        
        mock_model_manager.set_response("stage2", llm_response)
        
        manifest = BuildManifest.create("test")
        manifest.stage0_output = {"scale_anchor_m": {"overall_height_or_length": 1.0}}
        
        node = manifest.add_child_node(
            parent_id=manifest.root_node_id,
            label="box",
            kind=NodeKind.PART,
            geometry=GeometrySpec(primitive=PrimitiveType.BOX),
        )
        
        result = await Stage2Dimensions.run(
            node=node,
            manifest=manifest,
            model_manager=mock_model_manager,
            task_id="test_neg",
        )
        
        # Negative/zero should use default (0.1)
        assert result.size_x == 0.1
        assert result.size_y == 0.5
        assert result.size_z == 0.1
    
    @pytest.mark.asyncio
    async def test_torus_dimensions(self, mock_model_manager):
        """Test torus dimension parsing."""
        llm_response = json.dumps({
            "major_radius": 0.5,
            "minor_radius": 0.1,
            "reasoning": "Donut shape"
        })
        
        mock_model_manager.set_response("stage2", llm_response)
        
        manifest = BuildManifest.create("torus")
        manifest.stage0_output = {"scale_anchor_m": {"overall_height_or_length": 1.0}}
        
        node = manifest.add_child_node(
            parent_id=manifest.root_node_id,
            label="ring",
            kind=NodeKind.PART,
            geometry=GeometrySpec(primitive=PrimitiveType.TORUS),
        )
        
        result = await Stage2Dimensions.run(
            node=node,
            manifest=manifest,
            model_manager=mock_model_manager,
            task_id="test_torus",
        )
        
        assert result.major_radius == 0.5
        assert result.minor_radius == 0.1



# ============================================================================
# PART 3: Stage 3 Semantics Tests
# ============================================================================

class TestStage3Semantics:
    """Test semantic hint extraction from LLM responses."""
    
    @pytest.mark.asyncio
    async def test_corner_semantics(self, mock_model_manager):
        """Test CORNER socket semantic parsing."""
        llm_response = json.dumps({
            "corner_position": "bottom_front_left"
        })
        
        mock_model_manager.set_response("stage3", llm_response)
        
        manifest = BuildManifest.create("table")
        
        # Create parent with geometry
        parent = manifest.add_child_node(
            parent_id=manifest.root_node_id,
            label="tabletop",
            kind=NodeKind.PART,
            geometry=GeometrySpec(primitive=PrimitiveType.BOX),
        )
        parent.stage_outputs["stage2"] = {"size_x": 1.0, "size_y": 0.6, "size_z": 0.05}
        
        # Create leg with CORNER socket
        leg = manifest.add_child_node(
            parent_id=parent.node_id,
            label="leg_front_left",
            kind=NodeKind.PART,
            geometry=GeometrySpec(primitive=PrimitiveType.CYLINDER),
            attachment=AttachmentSpec(socket_type=SocketType.CORNER),
        )
        
        result = await Stage3Semantics.run(
            node=leg,
            manifest=manifest,
            model_manager=mock_model_manager,
            task_id="test_corner",
        )
        
        assert result["corner_position"] == "bottom_front_left"
    
    @pytest.mark.asyncio
    async def test_custom_offset_parsing(self, mock_model_manager):
        """Test CUSTOM socket offset parsing (critical for ladders)."""
        llm_response = json.dumps({
            "custom_offset": [0.4, 0.0, 0.0]
        })
        
        mock_model_manager.set_response("stage3", llm_response)
        
        manifest = BuildManifest.create("ladder")
        
        parent = manifest.add_child_node(
            parent_id=manifest.root_node_id,
            label="left_rail",
            kind=NodeKind.PART,
            geometry=GeometrySpec(primitive=PrimitiveType.BOX),
        )
        parent.stage_outputs["stage2"] = {"size_x": 0.05, "size_y": 0.05, "size_z": 1.5}
        
        right_rail = manifest.add_child_node(
            parent_id=manifest.root_node_id,
            label="right_rail",
            kind=NodeKind.PART,
            geometry=GeometrySpec(primitive=PrimitiveType.BOX),
            attachment=AttachmentSpec(socket_type=SocketType.CUSTOM),
        )
        right_rail.stage_outputs["decomposition_hint"] = {
            "position_hint": "parallel to left_rail, 0.4m to the right"
        }
        
        result = await Stage3Semantics.run(
            node=right_rail,
            manifest=manifest,
            model_manager=mock_model_manager,
            task_id="test_custom",
        )
        
        assert "custom_offset" in result
        assert result["custom_offset"] == [0.4, 0.0, 0.0]
    
    @pytest.mark.asyncio
    async def test_custom_offset_z_height(self, mock_model_manager):
        """Test CUSTOM socket with Z offset (ladder rungs)."""
        llm_response = json.dumps({
            "custom_offset": [0.0, 0.0, 0.2]
        })
        
        mock_model_manager.set_response("stage3", llm_response)
        
        manifest = BuildManifest.create("ladder")
        
        parent = manifest.add_child_node(
            parent_id=manifest.root_node_id,
            label="left_rail",
            kind=NodeKind.PART,
            geometry=GeometrySpec(primitive=PrimitiveType.BOX),
        )
        
        rung = manifest.add_child_node(
            parent_id=manifest.root_node_id,
            label="rung_bottom",
            kind=NodeKind.PART,
            geometry=GeometrySpec(primitive=PrimitiveType.BOX),
            attachment=AttachmentSpec(socket_type=SocketType.CUSTOM),
        )
        rung.stage_outputs["decomposition_hint"] = {
            "position_hint": "horizontal bar at 0.2m height"
        }
        
        result = await Stage3Semantics.run(
            node=rung,
            manifest=manifest,
            model_manager=mock_model_manager,
            task_id="test_rung",
        )
        
        assert result["custom_offset"][2] == 0.2
    
    @pytest.mark.asyncio
    async def test_through_axis_semantics(self, mock_model_manager):
        """Test THROUGH_AXIS semantic parsing."""
        llm_response = json.dumps({
            "pierce_direction": "left_right",
            "height_hint": "near_top"
        })
        
        mock_model_manager.set_response("stage3", llm_response)
        
        manifest = BuildManifest.create("training dummy")
        
        post = manifest.add_child_node(
            parent_id=manifest.root_node_id,
            label="post",
            kind=NodeKind.PART,
            geometry=GeometrySpec(primitive=PrimitiveType.CYLINDER),
        )
        post.stage_outputs["stage2"] = {"radius": 0.05, "depth": 1.7}
        
        arm = manifest.add_child_node(
            parent_id=post.node_id,
            label="arm",
            kind=NodeKind.PART,
            geometry=GeometrySpec(primitive=PrimitiveType.CYLINDER),
            attachment=AttachmentSpec(socket_type=SocketType.THROUGH_AXIS),
        )
        
        result = await Stage3Semantics.run(
            node=arm,
            manifest=manifest,
            model_manager=mock_model_manager,
            task_id="test_through",
        )
        
        assert result["pierce_direction"] == "left_right"
        assert result["height_hint"] == "near_top"
    
    @pytest.mark.asyncio
    async def test_array_member_semantics(self, mock_model_manager):
        """Test ARRAY_MEMBER semantic parsing."""
        llm_response = json.dumps({
            "array_axis": "x",
            "array_count": 4,
            "array_index": 0,
            "spacing_hint": "even"
        })
        
        mock_model_manager.set_response("stage3", llm_response)
        
        manifest = BuildManifest.create("button panel")
        
        panel = manifest.add_child_node(
            parent_id=manifest.root_node_id,
            label="panel",
            kind=NodeKind.PART,
            geometry=GeometrySpec(primitive=PrimitiveType.BOX),
        )
        
        button = manifest.add_child_node(
            parent_id=panel.node_id,
            label="button_1",
            kind=NodeKind.PART,
            geometry=GeometrySpec(primitive=PrimitiveType.CYLINDER),
            attachment=AttachmentSpec(socket_type=SocketType.ARRAY_MEMBER),
        )
        
        result = await Stage3Semantics.run(
            node=button,
            manifest=manifest,
            model_manager=mock_model_manager,
            task_id="test_array",
        )
        
        assert result["array_axis"] == "x"
        assert result["array_count"] == 4
        assert result["array_index"] == 0
        assert result["spacing_hint"] == "even"
    
    @pytest.mark.asyncio
    async def test_invalid_corner_position_defaults(self, mock_model_manager):
        """Test that invalid corner position uses default."""
        llm_response = json.dumps({
            "corner_position": "invalid_corner_name"
        })
        
        mock_model_manager.set_response("stage3", llm_response)
        
        manifest = BuildManifest.create("table")
        
        parent = manifest.add_child_node(
            parent_id=manifest.root_node_id,
            label="top",
            kind=NodeKind.PART,
            geometry=GeometrySpec(primitive=PrimitiveType.BOX),
        )
        
        leg = manifest.add_child_node(
            parent_id=parent.node_id,
            label="leg",
            kind=NodeKind.PART,
            geometry=GeometrySpec(primitive=PrimitiveType.CYLINDER),
            attachment=AttachmentSpec(socket_type=SocketType.CORNER),
        )
        
        result = await Stage3Semantics.run(
            node=leg,
            manifest=manifest,
            model_manager=mock_model_manager,
            task_id="test_invalid",
        )
        
        # Should default to bottom_front_left
        assert result["corner_position"] == "bottom_front_left"
    
    @pytest.mark.asyncio
    async def test_boolean_cut_semantics(self, mock_model_manager):
        """Test BOOLEAN_CUT semantic parsing."""
        llm_response = json.dumps({
            "cut_face": "top"
        })
        
        mock_model_manager.set_response("stage3", llm_response)
        
        manifest = BuildManifest.create("box with hole")
        
        box = manifest.add_child_node(
            parent_id=manifest.root_node_id,
            label="box",
            kind=NodeKind.PART,
            geometry=GeometrySpec(primitive=PrimitiveType.BOX),
        )
        
        hole = manifest.add_child_node(
            parent_id=box.node_id,
            label="hole",
            kind=NodeKind.PART,
            geometry=GeometrySpec(primitive=PrimitiveType.CYLINDER),
            attachment=AttachmentSpec(socket_type=SocketType.BOOLEAN_CUT),
        )
        
        result = await Stage3Semantics.run(
            node=hole,
            manifest=manifest,
            model_manager=mock_model_manager,
            task_id="test_bool",
        )
        
        assert result["cut_face"] == "top"
    
    @pytest.mark.asyncio
    async def test_simple_socket_returns_empty(self, mock_model_manager):
        """Test that simple sockets (ROOT, TOP_CENTER) return empty dict."""
        manifest = BuildManifest.create("test")
        
        parent = manifest.add_child_node(
            parent_id=manifest.root_node_id,
            label="base",
            kind=NodeKind.PART,
            geometry=GeometrySpec(primitive=PrimitiveType.BOX),
        )
        
        top = manifest.add_child_node(
            parent_id=parent.node_id,
            label="top",
            kind=NodeKind.PART,
            geometry=GeometrySpec(primitive=PrimitiveType.BOX),
            attachment=AttachmentSpec(socket_type=SocketType.TOP_CENTER),
        )
        
        # TOP_CENTER has no required semantics, should return {} without LLM call
        result = await Stage3Semantics.run(
            node=top,
            manifest=manifest,
            model_manager=mock_model_manager,
            task_id="test_simple",
        )
        
        assert result == {}
        # No LLM call should have been made
        assert len(mock_model_manager.call_log) == 0



# ============================================================================
# PART 4: Stage 4 Transform Resolution Tests
# ============================================================================

class TestStage4Resolver:
    """Test deterministic transform resolution."""
    
    def _make_node_with_stage2(
        self,
        manifest: BuildManifest,
        parent_id: str,
        label: str,
        primitive: PrimitiveType,
        socket: SocketType,
        stage2: Dict[str, Any],
        stage3: Dict[str, Any] = None,
    ) -> ManifestNode:
        """Helper to create node with stage outputs."""
        node = manifest.add_child_node(
            parent_id=parent_id,
            label=label,
            kind=NodeKind.PART,
            geometry=GeometrySpec(primitive=primitive),
            attachment=AttachmentSpec(socket_type=socket),
        )
        node.stage_outputs["stage2"] = stage2
        if stage3:
            node.stage_outputs["stage3"] = stage3
        return node
    
    def test_root_socket_zero_offset(self):
        """ROOT socket should have zero offset."""
        manifest = BuildManifest.create("test")
        
        node = self._make_node_with_stage2(
            manifest, manifest.root_node_id,
            "base", PrimitiveType.BOX, SocketType.ROOT,
            {"size_x": 1.0, "size_y": 1.0, "size_z": 0.5}
        )
        
        transform = _run(node, manifest)
        
        assert transform.offset == [0.0, 0.0, 0.0]
        assert transform.rotation == [0.0, 0.0, 0.0]
    
    def test_top_center_stacking(self):
        """TOP_CENTER should stack on parent's top face."""
        manifest = BuildManifest.create("test")
        
        # Parent box: 1x1x0.5
        parent = self._make_node_with_stage2(
            manifest, manifest.root_node_id,
            "base", PrimitiveType.BOX, SocketType.ROOT,
            {"size_x": 1.0, "size_y": 1.0, "size_z": 0.5}
        )
        parent.bounding_box = {
            "min": [-0.5, -0.5, -0.25],
            "max": [0.5, 0.5, 0.25]
        }
        
        # Child box: 0.5x0.5x0.2
        child = self._make_node_with_stage2(
            manifest, parent.node_id,
            "top", PrimitiveType.BOX, SocketType.TOP_CENTER,
            {"size_x": 0.5, "size_y": 0.5, "size_z": 0.2}
        )
        
        transform = _run(child, manifest)
        
        # Parent top = 0.25, child half_z = 0.1
        # Expected Z = 0.25 + 0.1 = 0.35
        assert transform.offset[0] == 0.0  # X centered
        assert transform.offset[1] == 0.0  # Y centered
        assert abs(transform.offset[2] - 0.35) < 0.001
    
    def test_bottom_center_hanging(self):
        """BOTTOM_CENTER should hang below parent."""
        manifest = BuildManifest.create("test")
        
        parent = self._make_node_with_stage2(
            manifest, manifest.root_node_id,
            "body", PrimitiveType.BOX, SocketType.ROOT,
            {"size_x": 1.0, "size_y": 1.0, "size_z": 0.5}
        )
        parent.bounding_box = {
            "min": [-0.5, -0.5, -0.25],
            "max": [0.5, 0.5, 0.25]
        }
        
        child = self._make_node_with_stage2(
            manifest, parent.node_id,
            "leg", PrimitiveType.CYLINDER, SocketType.BOTTOM_CENTER,
            {"radius": 0.05, "depth": 0.7}
        )
        
        transform = _run(child, manifest)
        
        # Parent bottom = -0.25, child half_z = 0.35
        # Expected Z = -0.25 - 0.35 = -0.6
        assert abs(transform.offset[2] - (-0.6)) < 0.001
    
    def test_corner_socket_label_based(self):
        """CORNER socket should use label to determine position."""
        manifest = BuildManifest.create("table")
        
        # Tabletop
        tabletop = self._make_node_with_stage2(
            manifest, manifest.root_node_id,
            "tabletop", PrimitiveType.BOX, SocketType.ROOT,
            {"size_x": 1.0, "size_y": 0.6, "size_z": 0.05}
        )
        tabletop.bounding_box = {
            "min": [-0.5, -0.3, -0.025],
            "max": [0.5, 0.3, 0.025]
        }
        
        # Front left leg
        leg_fl = self._make_node_with_stage2(
            manifest, tabletop.node_id,
            "leg_front_left", PrimitiveType.CYLINDER, SocketType.CORNER,
            {"radius": 0.03, "depth": 0.7},
            stage3={"corner_position": "bottom_front_left"}
        )
        
        transform = _run(leg_fl, manifest)
        
        # Should be at negative X (left), positive Y (front), negative Z (bottom)
        assert transform.offset[0] < 0, f"Left leg should have negative X, got {transform.offset[0]}"
        assert transform.offset[1] > 0, f"Front leg should have positive Y, got {transform.offset[1]}"
        assert transform.offset[2] < 0, f"Bottom leg should have negative Z, got {transform.offset[2]}"
    
    def test_corner_socket_back_right(self):
        """CORNER socket back_right position."""
        manifest = BuildManifest.create("table")
        
        tabletop = self._make_node_with_stage2(
            manifest, manifest.root_node_id,
            "tabletop", PrimitiveType.BOX, SocketType.ROOT,
            {"size_x": 1.0, "size_y": 0.6, "size_z": 0.05}
        )
        tabletop.bounding_box = {
            "min": [-0.5, -0.3, -0.025],
            "max": [0.5, 0.3, 0.025]
        }
        
        leg_br = self._make_node_with_stage2(
            manifest, tabletop.node_id,
            "leg_back_right", PrimitiveType.CYLINDER, SocketType.CORNER,
            {"radius": 0.03, "depth": 0.7},
            stage3={"corner_position": "bottom_back_right"}
        )
        
        transform = _run(leg_br, manifest)
        
        # Should be at positive X (right), negative Y (back), negative Z (bottom)
        assert transform.offset[0] > 0, f"Right leg should have positive X"
        assert transform.offset[1] < 0, f"Back leg should have negative Y"
        assert transform.offset[2] < 0, f"Bottom leg should have negative Z"
    
    def test_custom_socket_uses_offset(self):
        """CUSTOM socket should use custom_offset from Stage 3."""
        manifest = BuildManifest.create("ladder")
        
        left_rail = self._make_node_with_stage2(
            manifest, manifest.root_node_id,
            "left_rail", PrimitiveType.BOX, SocketType.ROOT,
            {"size_x": 0.05, "size_y": 0.05, "size_z": 1.5}
        )
        left_rail.bounding_box = {
            "min": [-0.025, -0.025, -0.75],
            "max": [0.025, 0.025, 0.75]
        }
        
        right_rail = self._make_node_with_stage2(
            manifest, manifest.root_node_id,
            "right_rail", PrimitiveType.BOX, SocketType.CUSTOM,
            {"size_x": 0.05, "size_y": 0.05, "size_z": 1.5},
            stage3={"custom_offset": [0.4, 0.0, 0.0]}
        )
        
        transform = _run(right_rail, manifest)
        
        assert transform.offset[0] == 0.4
        assert transform.offset[1] == 0.0
        assert transform.offset[2] == 0.0
    
    def test_custom_socket_z_offset_for_rungs(self):
        """CUSTOM socket Z offset for ladder rungs."""
        manifest = BuildManifest.create("ladder")
        
        rail = self._make_node_with_stage2(
            manifest, manifest.root_node_id,
            "rail", PrimitiveType.BOX, SocketType.ROOT,
            {"size_x": 0.05, "size_y": 0.05, "size_z": 1.5}
        )
        
        rung = self._make_node_with_stage2(
            manifest, manifest.root_node_id,
            "rung_bottom", PrimitiveType.BOX, SocketType.CUSTOM,
            {"size_x": 0.4, "size_y": 0.03, "size_z": 0.03},
            stage3={"custom_offset": [0.0, 0.0, 0.2]}
        )
        
        transform = _run(rung, manifest)
        
        assert transform.offset[2] == 0.2
    
    def test_through_axis_rotation_left_right(self):
        """THROUGH_AXIS left_right should rotate 90° around Y."""
        manifest = BuildManifest.create("dummy")
        
        post = self._make_node_with_stage2(
            manifest, manifest.root_node_id,
            "post", PrimitiveType.CYLINDER, SocketType.ROOT,
            {"radius": 0.05, "depth": 1.7}
        )
        post.bounding_box = {
            "min": [-0.05, -0.05, -0.85],
            "max": [0.05, 0.05, 0.85]
        }
        
        arm = self._make_node_with_stage2(
            manifest, post.node_id,
            "arm", PrimitiveType.CYLINDER, SocketType.THROUGH_AXIS,
            {"radius": 0.02, "depth": 0.5},
            stage3={"pierce_direction": "left_right", "height_hint": "center"}
        )
        
        transform = _run(arm, manifest)
        
        # left_right should rotate 90° around Y
        assert abs(transform.rotation[1] - math.pi/2) < 0.01
    
    def test_through_axis_rotation_front_back(self):
        """THROUGH_AXIS front_back should rotate 90° around X."""
        manifest = BuildManifest.create("dummy")
        
        post = self._make_node_with_stage2(
            manifest, manifest.root_node_id,
            "post", PrimitiveType.CYLINDER, SocketType.ROOT,
            {"radius": 0.05, "depth": 1.0}
        )
        post.bounding_box = {
            "min": [-0.05, -0.05, -0.5],
            "max": [0.05, 0.05, 0.5]
        }
        
        arm = self._make_node_with_stage2(
            manifest, post.node_id,
            "arm", PrimitiveType.CYLINDER, SocketType.THROUGH_AXIS,
            {"radius": 0.02, "depth": 0.4},
            stage3={"pierce_direction": "front_back", "height_hint": "center"}
        )
        
        transform = _run(arm, manifest)
        
        # front_back should rotate 90° around X
        assert abs(transform.rotation[0] - math.pi/2) < 0.01
    
    def test_boolean_cut_transform(self):
        """BOOLEAN_CUT should position cutter correctly."""
        manifest = BuildManifest.create("box with hole")
        
        box = self._make_node_with_stage2(
            manifest, manifest.root_node_id,
            "box", PrimitiveType.BOX, SocketType.ROOT,
            {"size_x": 1.0, "size_y": 1.0, "size_z": 0.5}
        )
        box.bounding_box = {
            "min": [-0.5, -0.5, -0.25],
            "max": [0.5, 0.5, 0.25]
        }
        
        hole = self._make_node_with_stage2(
            manifest, box.node_id,
            "hole", PrimitiveType.CYLINDER, SocketType.BOOLEAN_CUT,
            {"radius": 0.1, "depth": 0.6},
            stage3={"cut_face": "top"}
        )
        
        transform = _run(hole, manifest)
        
        assert transform.is_boolean
        assert transform.boolean_op == "difference"
        # Cut from top should position cutter near top
        assert transform.offset[2] > 0
    
    def test_front_center_offset(self):
        """FRONT_CENTER should offset in -Y direction (Blender convention: -Y = front)."""
        manifest = BuildManifest.create("test")
        
        body = self._make_node_with_stage2(
            manifest, manifest.root_node_id,
            "body", PrimitiveType.BOX, SocketType.ROOT,
            {"size_x": 1.0, "size_y": 0.5, "size_z": 0.5}
        )
        body.bounding_box = {
            "min": [-0.5, -0.25, -0.25],
            "max": [0.5, 0.25, 0.25]
        }
        
        front = self._make_node_with_stage2(
            manifest, body.node_id,
            "front_panel", PrimitiveType.BOX, SocketType.FRONT_CENTER,
            {"size_x": 0.3, "size_y": 0.05, "size_z": 0.3}
        )
        
        transform = _run(front, manifest)
        
        # Front is -Y direction in Blender convention
        assert transform.offset[1] < 0, f"FRONT_CENTER should be -Y, got {transform.offset[1]}"
        assert transform.offset[0] == 0.0  # Centered X
    
    def test_radial_socket_positions(self):
        """RADIAL socket should position items in a circle."""
        manifest = BuildManifest.create("wheel")
        
        hub = self._make_node_with_stage2(
            manifest, manifest.root_node_id,
            "hub", PrimitiveType.CYLINDER, SocketType.ROOT,
            {"radius": 0.1, "depth": 0.05}
        )
        hub.bounding_box = {
            "min": [-0.1, -0.1, -0.025],
            "max": [0.1, 0.1, 0.025]
        }
        
        # First spoke at index 0 (angle 0)
        spoke0 = self._make_node_with_stage2(
            manifest, hub.node_id,
            "spoke_0", PrimitiveType.CYLINDER, SocketType.RADIAL,
            {"radius": 0.01, "depth": 0.2},
            stage3={"radial_count": 4, "radial_index": 0}
        )
        
        transform0 = _run(spoke0, manifest)
        
        # At index 0, should be along +X axis
        assert transform0.offset[0] > 0
        assert abs(transform0.offset[1]) < 0.01
        
        # Second spoke at index 1 (angle 90°)
        spoke1 = self._make_node_with_stage2(
            manifest, hub.node_id,
            "spoke_1", PrimitiveType.CYLINDER, SocketType.RADIAL,
            {"radius": 0.01, "depth": 0.2},
            stage3={"radial_count": 4, "radial_index": 1}
        )
        
        transform1 = _run(spoke1, manifest)
        
        # At index 1, should be along +Y axis
        assert abs(transform1.offset[0]) < 0.01
        assert transform1.offset[1] > 0



# ============================================================================
# PART 5: Full Pipeline Integration Tests
# ============================================================================

class TestFullPipelineIntegration:
    """Test complete pipeline flow with mocked LLM responses."""
    
    @pytest.mark.asyncio
    async def test_ladder_full_pipeline(self, mock_model_manager):
        """Test complete ladder build matching the logs."""
        # Decomposition response
        decomp_response = json.dumps({
            "is_simple": True,
            "children": [
                {"label": "left_rail", "kind": "part", "primitive": "box",
                 "socket_type": "ROOT", "material_hint": "light wood", "style_hint": "smooth"},
                {"label": "right_rail", "kind": "part", "primitive": "box",
                 "socket_type": "CUSTOM", "material_hint": "light wood", "style_hint": "smooth",
                 "position_hint": "parallel to left_rail, 0.4m to the right"},
                {"label": "step_bottom", "kind": "part", "primitive": "box",
                 "socket_type": "CUSTOM", "material_hint": "light wood", "style_hint": "smooth",
                 "position_hint": "horizontal bar at 0.2m height"},
                {"label": "step_middle", "kind": "part", "primitive": "box",
                 "socket_type": "CUSTOM", "material_hint": "light wood", "style_hint": "smooth",
                 "position_hint": "horizontal bar at 0.5m height"},
                {"label": "step_top", "kind": "part", "primitive": "box",
                 "socket_type": "CUSTOM", "material_hint": "light wood", "style_hint": "smooth",
                 "position_hint": "horizontal bar at 0.8m height"},
            ]
        })
        mock_model_manager.set_response("decompose", decomp_response)
        
        # Stage 2 responses for each part
        mock_model_manager.set_response("left_rail", json.dumps({
            "size_x": 0.05, "size_y": 0.05, "size_z": 1.2,
            "reasoning": "Ladder rail"
        }))
        mock_model_manager.set_response("right_rail", json.dumps({
            "size_x": 0.05, "size_y": 0.05, "size_z": 1.2,
            "reasoning": "Ladder rail"
        }))
        mock_model_manager.set_response("step_", json.dumps({
            "size_x": 0.35, "size_y": 0.03, "size_z": 0.03,
            "reasoning": "Ladder step"
        }))
        
        # Stage 3 responses for CUSTOM sockets
        mock_model_manager.set_response("right_rail", json.dumps({
            "custom_offset": [0.4, 0.0, 0.0]
        }))
        mock_model_manager.set_response("step_bottom", json.dumps({
            "custom_offset": [0.0, 0.0, 0.2]
        }))
        mock_model_manager.set_response("step_middle", json.dumps({
            "custom_offset": [0.0, 0.0, 0.5]
        }))
        mock_model_manager.set_response("step_top", json.dumps({
            "custom_offset": [0.0, 0.0, 0.8]
        }))
        
        # Run decomposition
        manifest = BuildManifest.create("simple wooden step ladder")
        decomposer = RecursiveDecomposer()
        
        stats = await decomposer.decompose(
            manifest=manifest,
            model_manager=mock_model_manager,
            task_id="ladder_test",
        )
        
        # Verify decomposition
        assert stats["total_nodes"] == 6  # root + 5 parts
        
        parts = manifest.get_parts()
        assert len(parts) == 5
        
        # Verify socket types
        left_rail = manifest.get_node_by_label("left_rail")
        right_rail = manifest.get_node_by_label("right_rail")
        step_bottom = manifest.get_node_by_label("step_bottom")
        
        assert left_rail.attachment.socket_type == SocketType.ROOT
        assert right_rail.attachment.socket_type == SocketType.CUSTOM
        assert step_bottom.attachment.socket_type == SocketType.CUSTOM
        
        # Verify position hints stored
        assert "position_hint" in right_rail.stage_outputs.get("decomposition_hint", {})
    
    @pytest.mark.asyncio
    async def test_table_full_pipeline(self, mock_model_manager):
        """Test complete table build with corner legs."""
        decomp_response = json.dumps({
            "is_simple": True,
            "children": [
                {"label": "tabletop", "kind": "part", "primitive": "box",
                 "socket_type": "ROOT", "material_hint": "dark wood", "style_hint": "beveled"},
                {"label": "leg_front_left", "kind": "part", "primitive": "cylinder",
                 "socket_type": "CORNER", "material_hint": "dark wood"},
                {"label": "leg_front_right", "kind": "part", "primitive": "cylinder",
                 "socket_type": "CORNER", "material_hint": "dark wood"},
                {"label": "leg_back_left", "kind": "part", "primitive": "cylinder",
                 "socket_type": "CORNER", "material_hint": "dark wood"},
                {"label": "leg_back_right", "kind": "part", "primitive": "cylinder",
                 "socket_type": "CORNER", "material_hint": "dark wood"},
            ]
        })
        mock_model_manager.set_response("decompose", decomp_response)
        
        manifest = BuildManifest.create("wooden table")
        decomposer = RecursiveDecomposer()
        
        await decomposer.decompose(
            manifest=manifest,
            model_manager=mock_model_manager,
            task_id="table_test",
        )
        
        # Verify all legs have CORNER socket
        legs = [n for n in manifest.get_parts() if "leg" in n.label]
        assert len(legs) == 4
        
        for leg in legs:
            assert leg.attachment.socket_type == SocketType.CORNER
    
    @pytest.mark.asyncio
    async def test_nested_fan_assembly(self, mock_model_manager):
        """Test nested assembly like desk fan."""
        decomp_response = json.dumps({
            "is_simple": False,
            "children": [
                {
                    "label": "base_assembly",
                    "kind": "assembly",
                    "socket_type": "ROOT",
                    "is_complex": True,
                    "has_subcomponents": True,
                    "children": [
                        {"label": "base", "kind": "part", "primitive": "cylinder",
                         "socket_type": "ROOT", "material_hint": "black plastic"},
                        {
                            "label": "stand_assembly",
                            "kind": "assembly",
                            "socket_type": "TOP_CENTER",
                            "is_complex": True,
                            "children": [
                                {"label": "stand", "kind": "part", "primitive": "cylinder",
                                 "socket_type": "ROOT", "material_hint": "chrome"},
                                {"label": "head", "kind": "part", "primitive": "sphere",
                                 "socket_type": "TOP_CENTER", "material_hint": "white plastic"},
                            ]
                        }
                    ]
                }
            ]
        })
        mock_model_manager.set_response("decompose", decomp_response)
        
        manifest = BuildManifest.create("desk fan")
        decomposer = RecursiveDecomposer()
        
        stats = await decomposer.decompose(
            manifest=manifest,
            model_manager=mock_model_manager,
            task_id="fan_test",
        )
        
        # Should have nested structure
        assemblies = manifest.get_assemblies()
        parts = manifest.get_parts()
        
        assert len(assemblies) >= 2  # base_assembly, stand_assembly
        assert len(parts) >= 3  # base, stand, head
        
        # Verify hierarchy depth
        head = manifest.get_node_by_label("head")
        if head:
            assert head.hierarchy_depth >= 2


# ============================================================================
# PART 6: Edge Cases and Error Handling
# ============================================================================

class TestEdgeCases:
    """Test edge cases and error handling."""
    
    @pytest.mark.asyncio
    async def test_empty_children_array(self, mock_model_manager):
        """Test handling of empty children array."""
        llm_response = json.dumps({
            "is_simple": True,
            "children": []
        })
        
        mock_model_manager.set_response("decompose", llm_response)
        
        manifest = BuildManifest.create("empty")
        decomposer = RecursiveDecomposer()
        
        stats = await decomposer.decompose(
            manifest=manifest,
            model_manager=mock_model_manager,
            task_id="test_empty",
        )
        
        # Should handle gracefully - root stays as is
        assert stats["total_nodes"] == 1
    
    @pytest.mark.asyncio
    async def test_duplicate_labels_handled(self, mock_model_manager):
        """Test that duplicate labels get unique suffixes."""
        llm_response = json.dumps({
            "is_simple": True,
            "children": [
                {"label": "part", "kind": "part", "primitive": "box", "socket_type": "ROOT"},
                {"label": "part", "kind": "part", "primitive": "box", "socket_type": "TOP_CENTER"},
                {"label": "part", "kind": "part", "primitive": "box", "socket_type": "TOP_CENTER"},
            ]
        })
        
        mock_model_manager.set_response("decompose", llm_response)
        
        manifest = BuildManifest.create("duplicates")
        decomposer = RecursiveDecomposer()
        
        await decomposer.decompose(
            manifest=manifest,
            model_manager=mock_model_manager,
            task_id="test_dup",
        )
        
        # All parts should have unique labels
        parts = manifest.get_parts()
        labels = [p.label for p in parts]
        assert len(labels) == len(set(labels)), f"Duplicate labels found: {labels}"
    
    @pytest.mark.asyncio
    async def test_very_deep_nesting_limit(self, mock_model_manager):
        """Test that depth limit is respected."""
        # Create deeply nested response
        def make_nested(depth: int) -> dict:
            if depth == 0:
                return {"label": f"leaf_{depth}", "kind": "part", "primitive": "box", "socket_type": "ROOT"}
            return {
                "label": f"assembly_{depth}",
                "kind": "assembly",
                "socket_type": "ROOT" if depth == 5 else "TOP_CENTER",
                "is_complex": True,
                "children": [make_nested(depth - 1)]
            }
        
        llm_response = json.dumps({
            "is_simple": False,
            "children": [make_nested(10)]  # Very deep
        })
        
        mock_model_manager.set_response("decompose", llm_response)
        
        manifest = BuildManifest.create("deep")
        decomposer = RecursiveDecomposer(max_llm_calls=5)  # Limit calls
        
        stats = await decomposer.decompose(
            manifest=manifest,
            model_manager=mock_model_manager,
            task_id="test_deep",
        )
        
        # Should stop at some point due to limits
        assert stats["llm_calls"] <= 5
    
    def test_bbox_from_geometry_box(self):
        """Test BBox creation from box geometry."""
        geo = GeometrySpec(primitive=PrimitiveType.BOX)
        stage2 = {"size_x": 2.0, "size_y": 1.0, "size_z": 0.5}
        
        bbox = BBox.from_geometry(geo, stage2)
        
        assert bbox.size_x == 2.0
        assert bbox.size_y == 1.0
        assert bbox.size_z == 0.5
        assert bbox.min_x == -1.0
        assert bbox.max_x == 1.0
    
    def test_bbox_from_geometry_cylinder(self):
        """Test BBox creation from cylinder geometry."""
        geo = GeometrySpec(primitive=PrimitiveType.CYLINDER)
        stage2 = {"radius": 0.5, "depth": 2.0}
        
        bbox = BBox.from_geometry(geo, stage2)
        
        assert bbox.size_x == 1.0  # diameter
        assert bbox.size_y == 1.0  # diameter
        assert bbox.size_z == 2.0  # depth
    
    def test_bbox_from_geometry_sphere(self):
        """Test BBox creation from sphere geometry."""
        geo = GeometrySpec(primitive=PrimitiveType.SPHERE)
        stage2 = {"radius": 0.3}
        
        bbox = BBox.from_geometry(geo, stage2)
        
        assert bbox.size_x == 0.6
        assert bbox.size_y == 0.6
        assert bbox.size_z == 0.6
    
    def test_bbox_from_geometry_torus(self):
        """Test BBox creation from torus geometry."""
        geo = GeometrySpec(primitive=PrimitiveType.TORUS)
        stage2 = {"major_radius": 0.5, "minor_radius": 0.1}
        
        bbox = BBox.from_geometry(geo, stage2)
        
        # Outer extent = major + minor = 0.6
        assert bbox.max_x == 0.6
        assert bbox.max_y == 0.6
        assert bbox.max_z == 0.1  # minor radius
    
    @pytest.mark.asyncio
    async def test_stage3_with_missing_parent(self, mock_model_manager):
        """Test Stage 3 handles missing parent gracefully."""
        manifest = BuildManifest.create("test")
        
        # Create orphan node (no valid parent)
        node = ManifestNode(
            node_id="orphan",
            label="orphan",
            kind=NodeKind.PART,
            parent_id="nonexistent",
            geometry=GeometrySpec(primitive=PrimitiveType.BOX),
            attachment=AttachmentSpec(socket_type=SocketType.CORNER),
        )
        manifest.nodes[node.node_id] = node
        
        mock_model_manager.set_response("stage3", json.dumps({
            "corner_position": "bottom_front_left"
        }))
        
        # Should not crash
        result = await Stage3Semantics.run(
            node=node,
            manifest=manifest,
            model_manager=mock_model_manager,
            task_id="test_orphan",
        )
        
        assert "corner_position" in result


# ============================================================================
# PART 7: Material and Modifier Inference Tests
# ============================================================================

class TestMaterialModifierInference:
    """Test material and modifier inference from hints."""
    
    def test_material_hint_parsing(self):
        """Test that material hints are stored correctly."""
        manifest = BuildManifest.create("test")
        
        node = manifest.add_child_node(
            parent_id=manifest.root_node_id,
            label="part",
            kind=NodeKind.PART,
            geometry=GeometrySpec(primitive=PrimitiveType.BOX),
        )
        node.stage_outputs["decomposition_hint"] = {
            "material_hint": "polished steel",
            "style_hint": "hard surface mechanical"
        }
        
        hint = node.stage_outputs["decomposition_hint"]
        assert hint["material_hint"] == "polished steel"
        assert hint["style_hint"] == "hard surface mechanical"
    
    def test_style_hint_variations(self):
        """Test various style hint values."""
        valid_styles = [
            "smooth",
            "beveled",
            "sharp",
            "organic",
            "mechanical",
            "panel",
            "game ready",
        ]
        
        for style in valid_styles:
            manifest = BuildManifest.create("test")
            node = manifest.add_child_node(
                parent_id=manifest.root_node_id,
                label=f"part_{style}",
                kind=NodeKind.PART,
                geometry=GeometrySpec(primitive=PrimitiveType.BOX),
            )
            node.stage_outputs["decomposition_hint"] = {"style_hint": style}
            
            # Should store without error
            assert node.stage_outputs["decomposition_hint"]["style_hint"] == style


# ============================================================================
# Run Tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
