"""Unit tests for analytical embedment validation.

These tests validate the closed-form pierce embedment checks without any Blender dependency.
They form part of Section 8's synthetic test matrix for Stage 4.
"""

import pytest
from core.embedment_validation import (
    compute_embedment_depth,
    compute_required_embedment,
    validate_pierce_embedment,
    validate_pierce_from_specs,
    is_pierce_socket_type,
    extract_pierce_axis_from_socket,
    PierceAxis,
)


class TestEmbedmentDepthCalculation:
    """Test the core embedment depth formula."""
    
    def test_centered_child_full_embedment(self):
        """Child at center of parent has embedment = parent half-extent."""
        depth = compute_embedment_depth(
            parent_half_extent_mm=50.0,
            child_offset_along_axis_mm=0.0,
        )
        assert depth == 50.0
    
    def test_edge_child_zero_embedment(self):
        """Child at parent edge has zero embedment."""
        depth = compute_embedment_depth(
            parent_half_extent_mm=50.0,
            child_offset_along_axis_mm=50.0,
        )
        assert depth == 0.0
    
    def test_outside_child_negative_embedment(self):
        """Child outside parent has negative embedment."""
        depth = compute_embedment_depth(
            parent_half_extent_mm=50.0,
            child_offset_along_axis_mm=60.0,
        )
        assert depth == -10.0
    
    def test_negative_offset_same_as_positive(self):
        """Offset direction doesn't matter - uses absolute value."""
        depth_pos = compute_embedment_depth(50.0, 20.0)
        depth_neg = compute_embedment_depth(50.0, -20.0)
        assert depth_pos == depth_neg == 30.0


class TestRequiredEmbedment:
    """Test minimum required embedment calculation."""
    
    def test_default_margin(self):
        """Default margin is 2mm."""
        required = compute_required_embedment(child_radius_mm=20.0)
        assert required == 22.0  # 20 + 2
    
    def test_custom_margin(self):
        """Custom margin is respected."""
        required = compute_required_embedment(child_radius_mm=20.0, margin_mm=5.0)
        assert required == 25.0  # 20 + 5
    
    def test_zero_margin(self):
        """Zero margin means just the radius."""
        required = compute_required_embedment(child_radius_mm=15.0, margin_mm=0.0)
        assert required == 15.0


class TestValidatePierceEmbedment:
    """Test the main validation function."""
    
    def test_well_embedded_passes(self):
        """Arm centered in post passes validation."""
        # Post: 50mm radius cylinder (100mm diameter)
        # Arm: 20mm radius, centered (offset=0)
        # Embedment: 50mm, Required: 22mm -> PASS
        result = validate_pierce_embedment(
            parent_half_extent_mm=50.0,
            child_offset_along_axis_mm=0.0,
            child_radius_mm=20.0,
            axis=PierceAxis.X,
        )
        assert result.valid is True
        assert result.embedment_depth_mm == 50.0
        assert result.required_depth_mm == 22.0
    
    def test_edge_grazing_fails(self):
        """Arm barely touching edge fails validation."""
        # Post: 50mm half-extent
        # Arm: 20mm radius, offset 45mm from center
        # Embedment: 5mm, Required: 22mm -> FAIL
        result = validate_pierce_embedment(
            parent_half_extent_mm=50.0,
            child_offset_along_axis_mm=45.0,
            child_radius_mm=20.0,
            axis=PierceAxis.X,
        )
        assert result.valid is False
        assert result.embedment_depth_mm == 5.0
        assert "Insufficient embedment" in result.reason
    
    def test_exactly_at_threshold_passes(self):
        """Embedment exactly at required depth passes."""
        # Required: 20 + 2 = 22mm
        # Set offset so embedment = 22mm exactly
        result = validate_pierce_embedment(
            parent_half_extent_mm=50.0,
            child_offset_along_axis_mm=28.0,  # 50 - 28 = 22
            child_radius_mm=20.0,
            axis=PierceAxis.Z,
        )
        assert result.valid is True
        assert result.embedment_depth_mm == 22.0
    
    def test_just_below_threshold_fails(self):
        """Embedment just below required depth fails."""
        result = validate_pierce_embedment(
            parent_half_extent_mm=50.0,
            child_offset_along_axis_mm=29.0,  # 50 - 29 = 21 < 22
            child_radius_mm=20.0,
            axis=PierceAxis.Z,
        )
        assert result.valid is False
        assert result.embedment_depth_mm == 21.0


class TestTrainingDummyCase:
    """Regression test for the training dummy arm-through-post case."""
    
    def test_training_dummy_correct_embedment(self):
        """Training dummy with arm properly centered in post."""
        # Post: 25mm radius, so half-extent = 25mm
        # Arm: 20mm radius, centered (offset=0)
        # Embedment: 25mm, Required: 22mm -> PASS
        result = validate_pierce_embedment(
            parent_half_extent_mm=25.0,
            child_offset_along_axis_mm=0.0,
            child_radius_mm=20.0,
            axis=PierceAxis.X,
        )
        assert result.valid is True
        assert result.embedment_depth_mm == 25.0
    
    def test_training_dummy_flush_with_edge_fails(self):
        """Training dummy with arm flush to post edge (the old bug)."""
        # Post: 25mm radius
        # Arm: 20mm radius, offset so arm edge aligns with post edge
        # If arm center is at offset = 25 - 20 = 5mm from post edge
        # Actually if arm is "flush", its center is at post_radius - arm_radius from center
        # Wait, let's think about this more carefully:
        # - Post radius = 25mm, so post surface is at X = ±25mm from center
        # - Arm radius = 20mm
        # - If arm is "flush with edge", arm's far surface touches post's surface
        # - Arm center would be at X = 25 - 20 = 5mm? No...
        # - Actually "flush with edge" means arm barely inside:
        #   arm center at X = 25 - 20 = 5mm means arm surface at X = 5 + 20 = 25mm (touching edge)
        # - Embedment = 25 - 5 = 20mm, Required = 22mm -> FAIL (barely)
        
        # Let's use a clearer case: arm center at X = 10mm
        # Embedment = 25 - 10 = 15mm, Required = 22mm -> FAIL
        result = validate_pierce_embedment(
            parent_half_extent_mm=25.0,
            child_offset_along_axis_mm=10.0,
            child_radius_mm=20.0,
            axis=PierceAxis.X,
        )
        assert result.valid is False
        assert result.embedment_depth_mm == 15.0
        assert result.required_depth_mm == 22.0


class TestSocketTypeDetection:
    """Test socket type classification."""
    
    @pytest.mark.parametrize("socket_type", [
        "through_axis",
        "through_x",
        "through_y", 
        "through_z",
        "THROUGH_AXIS",
        "through-axis",
        "radial_bridge",
        "strut",
        "strut_diagonal",
    ])
    def test_pierce_types_detected(self, socket_type):
        """All pierce socket types are correctly identified."""
        assert is_pierce_socket_type(socket_type) is True
    
    @pytest.mark.parametrize("socket_type", [
        "top_center",
        "front_face",
        "bottom",
        "side_left",
        "root",
        "",
        None,
    ])
    def test_non_pierce_types_not_detected(self, socket_type):
        """Non-pierce socket types return False."""
        assert is_pierce_socket_type(socket_type) is False


class TestAxisExtraction:
    """Test pierce axis inference from socket names."""
    
    def test_explicit_x_axis(self):
        assert extract_pierce_axis_from_socket("through_x") == PierceAxis.X
        assert extract_pierce_axis_from_socket("lateral_pierce") == PierceAxis.X
    
    def test_explicit_y_axis(self):
        assert extract_pierce_axis_from_socket("through_y") == PierceAxis.Y
        assert extract_pierce_axis_from_socket("forward_strut") == PierceAxis.Y
    
    def test_explicit_z_axis(self):
        assert extract_pierce_axis_from_socket("through_z") == PierceAxis.Z
        assert extract_pierce_axis_from_socket("vertical_post") == PierceAxis.Z
    
    def test_ambiguous_returns_none(self):
        assert extract_pierce_axis_from_socket("through_axis") is None
        assert extract_pierce_axis_from_socket("strut") is None


class TestHighLevelValidation:
    """Test the convenience wrapper with full specs."""
    
    def test_box_parent_cylinder_child(self):
        """Cylinder passing through a box."""
        # Box: 100x100x100mm
        # Cylinder: 15mm radius, passing through center along X
        result = validate_pierce_from_specs(
            parent_dimensions_mm=(100.0, 100.0, 100.0),
            child_radius_mm=15.0,
            child_offset_mm=(0.0, 0.0, 50.0),  # Centered in X/Y, at Z=50
            socket_type="through_axis",
            through_axis_hint="x",
        )
        # Parent half-extent along X = 50mm
        # Child offset along X = 0mm
        # Embedment = 50mm, Required = 17mm -> PASS
        assert result.valid is True
        assert result.axis == PierceAxis.X
    
    def test_cylinder_parent_cylinder_child(self):
        """Cylinder passing through another cylinder (training dummy case)."""
        # Post: 25mm radius cylinder, 200mm tall -> dims = (50, 50, 200)
        # Arm: 20mm radius, centered
        result = validate_pierce_from_specs(
            parent_dimensions_mm=(50.0, 50.0, 200.0),  # diameter, diameter, height
            child_radius_mm=20.0,
            child_offset_mm=(0.0, 0.0, 100.0),  # Centered at Z=100 (middle of post)
            socket_type="through_axis",
            through_axis_hint="x",
        )
        # Parent half-extent along X = 25mm
        # Child offset along X = 0mm
        # Embedment = 25mm, Required = 22mm -> PASS
        assert result.valid is True
        assert result.embedment_depth_mm == 25.0
