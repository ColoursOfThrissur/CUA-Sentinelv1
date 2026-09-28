"""Tests for assembly_spec step ordering.

Verifies that modifiers (bevel, subsurf) are applied AFTER boolean operations,
so bevels apply to the final joined mesh, not pre-boolean operands.
"""

import pytest
from core.assembly_spec import (
    AssemblyGraph,
    AssemblyNode,
    AttachmentSpec,
    JoinMode,
    graph_to_blender_steps,
)


def _make_simple_graph(with_boolean: bool = False) -> AssemblyGraph:
    """Create a simple test graph."""
    root = AssemblyNode(
        node_id="root",
        label="main_body",
        sub_spec={"primitive": "box", "size": [1.0, 1.0, 1.0]},
        children=[],
    )
    
    if with_boolean:
        child = AssemblyNode(
            node_id="child",
            label="cutter",
            sub_spec={"primitive": "cylinder", "radius": 0.2, "depth": 0.5},
            attachment=AttachmentSpec(
                parent_node_id="root",
                local_offset=(0.0, 0.0, 0.3),
                join_mode=JoinMode.BOOLEAN_DIFFERENCE,
            ),
        )
        root.children.append(child)
    
    return AssemblyGraph(
        task_id="test",
        root=root,
        rests_on_surface=True,
    )


class TestStepOrdering:
    """Test that steps are ordered correctly: geometry -> booleans -> modifiers."""
    
    def test_geometry_first_no_clear_scene(self):
        """Geometry creation should be first (no clear_scene - we use collection isolation)."""
        graph = _make_simple_graph()
        steps = graph_to_blender_steps(graph)
        
        # First step should be geometry creation, not clear_scene
        # (executor uses collection-based isolation instead)
        assert "create_" in steps[0][0], f"First step should be geometry creation, got {steps[0][0]}"
        assert not any("clear_scene" in s[0] for s in steps), "clear_scene should not be in steps"
    
    def test_geometry_before_modifiers(self):
        """Geometry creation should come before modifier application."""
        graph = _make_simple_graph()
        steps = graph_to_blender_steps(graph)
        
        step_names = [s[0] for s in steps]
        
        # Find indices
        create_idx = next(i for i, n in enumerate(step_names) if "create_box" in n)
        bevel_idx = next(i for i, n in enumerate(step_names) if "apply_bevel" in n)
        
        assert create_idx < bevel_idx, "Geometry should be created before bevel applied"
    
    def test_boolean_before_bevel(self):
        """Boolean operations should complete before bevel is applied."""
        graph = _make_simple_graph(with_boolean=True)
        steps = graph_to_blender_steps(graph)
        
        step_names = [s[0] for s in steps]
        
        # Find boolean and bevel indices
        boolean_indices = [i for i, n in enumerate(step_names) if "apply_boolean" in n]
        bevel_indices = [i for i, n in enumerate(step_names) if "apply_bevel" in n]
        
        # All booleans should come before all bevels
        if boolean_indices and bevel_indices:
            assert max(boolean_indices) < min(bevel_indices), \
                "All booleans should complete before any bevel is applied"
    
    def test_smooth_shading_in_modifier_phase(self):
        """Smooth shading should be in the modifier phase (after booleans)."""
        graph = _make_simple_graph(with_boolean=True)
        steps = graph_to_blender_steps(graph)
        
        step_names = [s[0] for s in steps]
        
        boolean_indices = [i for i, n in enumerate(step_names) if "apply_boolean" in n]
        smooth_indices = [i for i, n in enumerate(step_names) if "set_smooth_shading" in n]
        
        if boolean_indices and smooth_indices:
            assert max(boolean_indices) < min(smooth_indices), \
                "Smooth shading should come after booleans"
    
    def test_consumed_mesh_not_modified(self):
        """Meshes consumed by boolean operations should not receive modifiers."""
        graph = _make_simple_graph(with_boolean=True)
        steps = graph_to_blender_steps(graph)
        
        # The "cutter" mesh is consumed by boolean difference
        # It should not appear in any modifier steps
        modifier_ops = ["apply_bevel", "apply_subdivision", "set_smooth_shading"]
        
        for step_name, step_args in steps:
            if any(op in step_name for op in modifier_ops):
                assert step_args.get("name") != "cutter", \
                    "Consumed mesh 'cutter' should not receive modifiers"


class TestModifierIntentIntegration:
    """Test modifier intent integration with step generation."""
    
    def test_with_modifier_intents(self):
        """Steps should use modifier intents when provided."""
        from core.blender_pipeline.stage45_modifiers import ModifierIntent, BevelParams
        
        graph = _make_simple_graph()
        
        # Create custom modifier intent
        intents = {
            "main_body": ModifierIntent(
                label="main_body",
                bevel=BevelParams(width=0.05, segments=4),
                subsurf=None,
                surface_detail=None,
            )
        }
        
        steps = graph_to_blender_steps(graph, modifier_intents=intents)
        
        # Find bevel step
        bevel_step = next((s for s in steps if "apply_bevel" in s[0]), None)
        assert bevel_step is not None
        assert bevel_step[1]["width"] == 0.05
        assert bevel_step[1]["segments"] == 4
    
    def test_fallback_without_intents(self):
        """Should use style-based heuristics when no intents provided."""
        graph = _make_simple_graph()
        
        steps = graph_to_blender_steps(graph, style_tag="hard_surface_industrial")
        
        # Should still have bevel (from heuristics)
        bevel_step = next((s for s in steps if "apply_bevel" in s[0]), None)
        assert bevel_step is not None


class TestThreePhaseStructure:
    """Test the three-phase step structure."""
    
    def test_phases_are_contiguous(self):
        """Each phase should be contiguous (no interleaving)."""
        graph = _make_simple_graph(with_boolean=True)
        steps = graph_to_blender_steps(graph)
        
        # Categorize each step
        def categorize(step_name):
            if "clear_scene" in step_name or "create_" in step_name or "set_material" in step_name:
                return "geometry"
            elif "apply_boolean" in step_name or "parent_object" in step_name:
                return "boolean"
            else:
                return "modifier"
        
        categories = [categorize(s[0]) for s in steps]
        
        # Check that we don't go backwards in phases
        phase_order = {"geometry": 0, "boolean": 1, "modifier": 2}
        max_phase_seen = -1
        
        for cat in categories:
            phase = phase_order[cat]
            if phase < max_phase_seen:
                pytest.fail(f"Phase '{cat}' appeared after a later phase")
            max_phase_seen = max(max_phase_seen, phase)
