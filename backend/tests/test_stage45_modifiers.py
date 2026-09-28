"""Tests for Stage 4.5 Modifier Intent Resolution.

These are pure code tests - no LLM or Blender required.
Tests the deterministic parameter derivation from closed vocabularies.
"""

import pytest
from core.blender_pipeline.stage45_modifiers import (
    resolve_bevel,
    resolve_subsurf,
    resolve_surface_detail,
    get_part_extents,
    infer_modifier_intent_from_style,
    BevelParams,
    SubsurfParams,
    ArrayDetailParams,
    BEVEL_STYLES,
    SUBSURF_INTENTS,
    SURFACE_DETAILS,
    DETAIL_DENSITIES,
)


class TestResolveBevel:
    """Test bevel parameter derivation."""
    
    def test_none_returns_none(self):
        result = resolve_bevel("none", 0.5)
        assert result is None
    
    def test_sharp_bevel(self):
        result = resolve_bevel("sharp", 1.0)
        assert result is not None
        assert result.width == pytest.approx(0.01, rel=0.01)  # 1% of 1.0
        assert result.segments == 1
    
    def test_soft_bevel(self):
        result = resolve_bevel("soft", 1.0)
        assert result is not None
        assert result.width == pytest.approx(0.03, rel=0.01)  # 3% of 1.0
        assert result.segments == 3
    
    def test_heavy_bevel(self):
        result = resolve_bevel("heavy", 1.0)
        assert result is not None
        assert result.width == pytest.approx(0.06, rel=0.01)  # 6% of 1.0
        assert result.segments == 5
    
    def test_bevel_scales_with_part_size(self):
        """Bevel width should scale proportionally with part size."""
        small = resolve_bevel("soft", 0.1)
        large = resolve_bevel("soft", 2.0)
        
        assert small.width < large.width
        # Ratio should be approximately 20:1
        assert large.width / small.width == pytest.approx(20.0, rel=0.5)
    
    def test_bevel_floor(self):
        """Very small parts should still get minimum bevel."""
        result = resolve_bevel("sharp", 0.001)
        assert result.width >= 0.0005  # Hard floor
    
    def test_bevel_ceiling(self):
        """Bevel shouldn't exceed 15% of part size."""
        result = resolve_bevel("heavy", 0.1)
        assert result.width <= 0.1 * 0.15
    
    def test_invalid_style_returns_none(self):
        result = resolve_bevel("invalid_style", 1.0)
        assert result is None


class TestResolveSubsurf:
    """Test subdivision surface parameter derivation."""
    
    def test_false_returns_none(self):
        result = resolve_subsurf(False, "rounded")
        assert result is None
    
    def test_rounded(self):
        result = resolve_subsurf(True, "rounded")
        assert result is not None
        assert result.levels == 1
        assert result.render_levels == 2
    
    def test_very_smooth(self):
        result = resolve_subsurf(True, "very_smooth")
        assert result is not None
        assert result.levels == 2
        assert result.render_levels == 3  # Capped at 3
    
    def test_invalid_intent_defaults_to_rounded(self):
        result = resolve_subsurf(True, "invalid")
        assert result is not None
        assert result.levels == 1


class TestResolveSurfaceDetail:
    """Test surface detail array parameter derivation."""
    
    def test_none_returns_none(self):
        result = resolve_surface_detail("none", "medium", 2.0, 0.5)
        assert result is None
    
    def test_rivets_medium(self):
        result = resolve_surface_detail("rivets", "medium", 2.0, 0.5)
        assert result is not None
        assert result.base_mesh_type == "rivets"
        assert result.count >= 2
        # 2.0m / 0.12m spacing = ~16 rivets
        assert result.count == pytest.approx(16, abs=2)
    
    def test_sparse_vs_dense(self):
        """Sparse should have fewer elements than dense."""
        sparse = resolve_surface_detail("rivets", "sparse", 2.0, 0.5)
        dense = resolve_surface_detail("rivets", "dense", 2.0, 0.5)
        
        assert sparse.count < dense.count
    
    def test_exact_spacing_fits_surface(self):
        """Spacing should be recalculated to fit surface exactly."""
        result = resolve_surface_detail("panel_lines", "medium", 1.5, 0.3)
        # count * spacing should equal surface length
        assert result.count * result.spacing == pytest.approx(1.5, rel=0.01)
    
    def test_minimum_count(self):
        """Even very short surfaces should get at least 2 elements."""
        result = resolve_surface_detail("studs", "sparse", 0.1, 0.05)
        assert result.count >= 2
    
    def test_base_radius_scales_with_part(self):
        """Detail element size should scale with part size."""
        small = resolve_surface_detail("rivets", "medium", 1.0, 0.1)
        large = resolve_surface_detail("rivets", "medium", 1.0, 1.0)
        
        assert small.base_radius < large.base_radius


class TestGetPartExtents:
    """Test part extent extraction from sub_spec."""
    
    def test_cylinder(self):
        sub_spec = {"primitive": "cylinder", "radius": 0.3, "depth": 2.0}
        smallest, surface = get_part_extents(sub_spec)
        assert smallest == 0.3  # radius
        assert surface == 2.0   # depth
    
    def test_sphere(self):
        sub_spec = {"primitive": "sphere", "radius": 0.5}
        smallest, surface = get_part_extents(sub_spec)
        assert smallest == 0.5
        assert surface == 1.0  # diameter
    
    def test_box(self):
        sub_spec = {"primitive": "box", "size": [1.0, 2.0, 3.0]}
        smallest, surface = get_part_extents(sub_spec)
        assert smallest == 0.5  # min half-size
        assert surface == 3.0   # max dimension
    
    def test_defaults(self):
        sub_spec = {"primitive": "box"}
        smallest, surface = get_part_extents(sub_spec)
        assert smallest == 0.5  # default
        assert surface == 1.0


class TestInferModifierIntent:
    """Test style-based modifier inference."""
    
    def test_box_hard_surface_gets_sharp_bevel(self):
        intent = infer_modifier_intent_from_style(
            "test_box",
            {"primitive": "box", "size": [1.0, 1.0, 1.0]},
            "hard_surface_industrial",
        )
        assert intent.bevel is not None
        assert intent.bevel.segments == 1  # sharp
        assert intent.subsurf is None
    
    def test_box_organic_gets_soft_bevel(self):
        intent = infer_modifier_intent_from_style(
            "test_box",
            {"primitive": "box", "size": [1.0, 1.0, 1.0]},
            "organic_worn",
        )
        assert intent.bevel is not None
        assert intent.bevel.segments == 3  # soft
    
    def test_sphere_organic_gets_subsurf(self):
        intent = infer_modifier_intent_from_style(
            "test_sphere",
            {"primitive": "sphere", "radius": 0.5},
            "organic_worn",
        )
        assert intent.subsurf is not None
        assert intent.subsurf.levels == 1
    
    def test_sphere_hard_surface_no_subsurf(self):
        intent = infer_modifier_intent_from_style(
            "test_sphere",
            {"primitive": "sphere", "radius": 0.5},
            "hard_surface_industrial",
        )
        assert intent.subsurf is None
    
    def test_cylinder_hard_surface_gets_bevel(self):
        intent = infer_modifier_intent_from_style(
            "test_cyl",
            {"primitive": "cylinder", "radius": 0.3, "depth": 1.0},
            "hard_surface_industrial",
        )
        assert intent.bevel is not None
    
    def test_no_surface_detail_in_inference(self):
        """Surface details should not be inferred without LLM guidance."""
        intent = infer_modifier_intent_from_style(
            "test",
            {"primitive": "box", "size": [2.0, 2.0, 2.0]},
            "hard_surface_industrial",
        )
        assert intent.surface_detail is None


class TestBevelScaleMatrix:
    """Test bevel width correctness across a range of scales.
    
    Per blueprint Section 8: test 0.1m to 20m parts.
    """
    
    @pytest.mark.parametrize("part_size", [0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0])
    def test_bevel_proportional_to_size(self, part_size):
        """Bevel should be proportional to part size within bounds."""
        result = resolve_bevel("soft", part_size)
        
        # Should be approximately 3% of part size
        expected = part_size * 0.03
        
        # But clamped to floor/ceiling
        expected = max(0.0005, min(expected, part_size * 0.15))
        
        assert result.width == pytest.approx(expected, rel=0.01)
    
    @pytest.mark.parametrize("part_size", [0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0])
    def test_bevel_never_exceeds_part(self, part_size):
        """Bevel width should never exceed 15% of part size."""
        for style in ["sharp", "soft", "heavy"]:
            result = resolve_bevel(style, part_size)
            if result:
                assert result.width <= part_size * 0.15


class TestSurfaceDetailEdgeCases:
    """Test surface detail count/spacing for edge cases."""
    
    def test_very_short_seam(self):
        """Seam shorter than one spacing unit should still get 2 elements."""
        result = resolve_surface_detail("rivets", "sparse", 0.05, 0.1)
        assert result.count == 2
        assert result.spacing == pytest.approx(0.025, rel=0.01)
    
    def test_exact_multiple_seam(self):
        """Seam that's exact multiple of spacing should fit perfectly."""
        # 1.2m seam with 0.12m spacing = exactly 10 elements
        result = resolve_surface_detail("rivets", "medium", 1.2, 0.5)
        assert result.count == 10
        assert result.count * result.spacing == pytest.approx(1.2, rel=0.001)
    
    def test_long_seam(self):
        """Long seams should get many elements."""
        result = resolve_surface_detail("panel_lines", "dense", 10.0, 1.0)
        # 10m / 0.06m = ~166 elements
        assert result.count > 100


class TestLLMResponseParsing:
    """Test LLM response parsing and validation."""
    
    def test_valid_json_array(self):
        """Valid JSON array should parse correctly."""
        from core.blender_pipeline.stage45_modifiers import _parse_llm_response
        
        raw = '''```json
[
  {"label": "main_hull", "bevel_style": "soft", "needs_subsurf": false, "subsurf_intent": "rounded", "surface_detail": "rivets", "detail_density": "medium"},
  {"label": "tower", "bevel_style": "sharp", "needs_subsurf": true, "subsurf_intent": "rounded", "surface_detail": "none", "detail_density": "medium"}
]
```'''
        result = _parse_llm_response(raw, ["main_hull", "tower"])
        
        assert "main_hull" in result
        assert "tower" in result
        assert result["main_hull"]["bevel_style"] == "soft"
        assert result["tower"]["needs_subsurf"] == True
    
    def test_missing_part_gets_defaults(self):
        """Missing parts should get default values."""
        from core.blender_pipeline.stage45_modifiers import _parse_llm_response
        
        raw = '[{"label": "hull", "bevel_style": "soft", "needs_subsurf": false, "subsurf_intent": "rounded", "surface_detail": "none", "detail_density": "medium"}]'
        result = _parse_llm_response(raw, ["hull", "missing_part"])
        
        assert "missing_part" in result
        assert result["missing_part"]["bevel_style"] == "none"
    
    def test_invalid_vocabulary_corrected(self):
        """Invalid vocabulary values should be corrected to defaults."""
        from core.blender_pipeline.stage45_modifiers import _parse_llm_response
        
        raw = '[{"label": "test", "bevel_style": "INVALID", "needs_subsurf": false, "subsurf_intent": "rounded", "surface_detail": "none", "detail_density": "medium"}]'
        result = _parse_llm_response(raw, ["test"])
        
        assert result["test"]["bevel_style"] == "none"  # Corrected to default
    
    def test_no_json_raises_error(self):
        """Response without JSON should raise Stage45Error."""
        from core.blender_pipeline.stage45_modifiers import _parse_llm_response, Stage45Error
        
        with pytest.raises(Stage45Error):
            _parse_llm_response("No JSON here, just text.", ["test"])
    
    def test_string_bool_converted(self):
        """String 'true'/'false' should be converted to bool."""
        from core.blender_pipeline.stage45_modifiers import _parse_llm_response
        
        raw = '[{"label": "test", "bevel_style": "soft", "needs_subsurf": "true", "subsurf_intent": "rounded", "surface_detail": "none", "detail_density": "medium"}]'
        result = _parse_llm_response(raw, ["test"])
        
        assert result["test"]["needs_subsurf"] == True
