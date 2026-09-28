"""Tests for Stage 2 dimension validation."""

import pytest


class TestStage2DimensionValidation:
    """Test that Stage 2 rejects severe dimension violations."""
    
    def test_severe_ratio_violation_raises_error(self):
        """Part claiming to be >2x the scale anchor should raise Stage2Error."""
        from core.blender_pipeline.stage2_dimensions import Stage2Dimensions, Stage2Error
        
        # Stage 1 output with one part
        stage1_output = {
            "parts": [
                {"label": "body", "primitive_type": "box", "parent_label": None, "socket_type": "ROOT"},
            ]
        }
        
        # LLM output claiming body is 3x the scale anchor (scale_anchor=1m, body=3m)
        data = {
            "parts": [
                {
                    "label": "body",
                    "dimensions": {"size": [3.0, 3.0, 3.0], "confidence": 0.8},
                }
            ]
        }
        
        scale_anchor = 1.0  # 1 meter
        
        with pytest.raises(Stage2Error) as exc_info:
            Stage2Dimensions._validate_and_build(data, stage1_output, scale_anchor)
        
        assert "Severe dimension violations" in str(exc_info.value)
    
    def test_moderate_ratio_violation_warns_but_passes(self):
        """Part at 1.5x scale anchor should warn but not fail."""
        from core.blender_pipeline.stage2_dimensions import Stage2Dimensions
        
        stage1_output = {
            "parts": [
                {"label": "body", "primitive_type": "box", "parent_label": None, "socket_type": "ROOT"},
            ]
        }
        
        # 1.5x is > MAX_PART_RATIO (1.0) but < 2.0 threshold
        data = {
            "parts": [
                {
                    "label": "body",
                    "dimensions": {"size": [1.5, 1.5, 1.5], "confidence": 0.8},
                }
            ]
        }
        
        scale_anchor = 1.0
        
        # Should not raise - just warn
        result = Stage2Dimensions._validate_and_build(data, stage1_output, scale_anchor)
        assert len(result.parts) == 1
    
    def test_valid_dimensions_pass(self):
        """Parts with valid dimensions should pass without error."""
        from core.blender_pipeline.stage2_dimensions import Stage2Dimensions
        
        stage1_output = {
            "parts": [
                {"label": "body", "primitive_type": "box", "parent_label": None, "socket_type": "ROOT"},
                {"label": "head", "primitive_type": "sphere", "parent_label": "body", "socket_type": "TOP_CENTER"},
            ]
        }
        
        data = {
            "parts": [
                {
                    "label": "body",
                    "dimensions": {"size": [0.5, 0.5, 1.0], "confidence": 0.8},
                },
                {
                    "label": "head",
                    "dimensions": {"radius": 0.2, "confidence": 0.7},
                }
            ]
        }
        
        scale_anchor = 1.5  # 1.5 meters
        
        result = Stage2Dimensions._validate_and_build(data, stage1_output, scale_anchor)
        assert len(result.parts) == 2
        assert result.parts[0].label == "body"
        assert result.parts[1].label == "head"


class TestBooleanPostconditionVerification:
    """Test that boolean postcondition verification function exists."""
    
    def test_verify_boolean_postconditions_function_exists(self):
        """The _verify_boolean_postconditions function should exist."""
        from core.blender_pipeline.executor import _verify_boolean_postconditions
        import inspect
        
        assert callable(_verify_boolean_postconditions)
        assert inspect.iscoroutinefunction(_verify_boolean_postconditions)
    
    def test_mesh_check_included_in_verification_flow(self):
        """mesh_check should be included in the verification result."""
        import inspect
        from core.blender_pipeline import executor
        
        source = inspect.getsource(executor.run_staged_pipeline_and_execute)
        
        # Check that mesh_check is called
        assert "_verify_boolean_postconditions" in source
        assert "mesh_check" in source


class TestEvaluatedDepsgraph:
    """Test that dimension verification uses evaluated depsgraph."""
    
    def test_dimension_verification_uses_evaluated_mesh(self):
        """Dimension verification script should use evaluated_depsgraph_get."""
        import inspect
        from core.blender_pipeline import executor
        
        source = inspect.getsource(executor._verify_dimensions_match_spec)
        
        # Check that evaluated depsgraph is used
        assert "evaluated_depsgraph_get" in source
        assert "evaluated_get" in source
        assert "to_mesh" in source
