"""Tests for Stage 0 — Object Understanding & Scale Anchor."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from core.blender_pipeline.stage0_understanding import (
    Stage0Understanding,
    ObjectUnderstanding,
    ScaleAnchor,
    Stage0Error,
    VALID_STYLE_TAGS,
)


class TestStage0Understanding:
    """Tests for Stage 0 validation and parsing."""
    
    def test_valid_output_parsing(self):
        """Test parsing a valid LLM response."""
        data = {
            "category": "training_dummy",
            "rests_on_surface": True,
            "style_tag": "hard_surface_industrial",
            "scale_anchor_m": {
                "overall_height_or_length": 1.7,
                "reasoning": "Human-height martial arts target"
            }
        }
        
        result = Stage0Understanding._validate_and_build(data)
        
        assert result.category == "training_dummy"
        assert result.rests_on_surface is True
        assert result.style_tag == "hard_surface_industrial"
        assert result.scale_anchor.overall_height_or_length_m == 1.7
        assert "martial arts" in result.scale_anchor.reasoning
    
    def test_missing_category_raises(self):
        """Test that missing category raises Stage0Error."""
        data = {
            "rests_on_surface": True,
            "style_tag": "hard_surface_industrial",
            "scale_anchor_m": {"overall_height_or_length": 1.0}
        }
        
        with pytest.raises(Stage0Error, match="category"):
            Stage0Understanding._validate_and_build(data)
    
    def test_missing_rests_on_surface_raises(self):
        """Test that missing rests_on_surface raises Stage0Error."""
        data = {
            "category": "test",
            "style_tag": "hard_surface_industrial",
            "scale_anchor_m": {"overall_height_or_length": 1.0}
        }
        
        with pytest.raises(Stage0Error, match="rests_on_surface"):
            Stage0Understanding._validate_and_build(data)
    
    def test_string_rests_on_surface_coerced(self):
        """Test that string 'true'/'false' is coerced to bool."""
        data = {
            "category": "test",
            "rests_on_surface": "true",
            "style_tag": "hard_surface_industrial",
            "scale_anchor_m": {"overall_height_or_length": 1.0, "reasoning": "test"}
        }
        
        result = Stage0Understanding._validate_and_build(data)
        assert result.rests_on_surface is True
        
        data["rests_on_surface"] = "false"
        result = Stage0Understanding._validate_and_build(data)
        assert result.rests_on_surface is False
    
    def test_invalid_style_tag_defaults(self):
        """Test that invalid style_tag defaults to hard_surface_industrial."""
        data = {
            "category": "test",
            "rests_on_surface": True,
            "style_tag": "invalid_style",
            "scale_anchor_m": {"overall_height_or_length": 1.0, "reasoning": "test"}
        }
        
        result = Stage0Understanding._validate_and_build(data)
        assert result.style_tag == "hard_surface_industrial"
    
    def test_missing_scale_anchor_raises(self):
        """Test that missing scale_anchor_m raises Stage0Error."""
        data = {
            "category": "test",
            "rests_on_surface": True,
            "style_tag": "hard_surface_industrial",
        }
        
        with pytest.raises(Stage0Error, match="scale_anchor_m"):
            Stage0Understanding._validate_and_build(data)
    
    def test_missing_scale_value_raises(self):
        """Test that missing overall_height_or_length raises Stage0Error."""
        data = {
            "category": "test",
            "rests_on_surface": True,
            "style_tag": "hard_surface_industrial",
            "scale_anchor_m": {"reasoning": "test"}
        }
        
        with pytest.raises(Stage0Error, match="overall_height_or_length"):
            Stage0Understanding._validate_and_build(data)
    
    def test_negative_scale_raises(self):
        """Test that negative scale value raises Stage0Error."""
        data = {
            "category": "test",
            "rests_on_surface": True,
            "style_tag": "hard_surface_industrial",
            "scale_anchor_m": {"overall_height_or_length": -1.0}
        }
        
        with pytest.raises(Stage0Error, match="positive"):
            Stage0Understanding._validate_and_build(data)
    
    def test_zero_scale_raises(self):
        """Test that zero scale value raises Stage0Error."""
        data = {
            "category": "test",
            "rests_on_surface": True,
            "style_tag": "hard_surface_industrial",
            "scale_anchor_m": {"overall_height_or_length": 0}
        }
        
        with pytest.raises(Stage0Error, match="positive"):
            Stage0Understanding._validate_and_build(data)
    
    def test_to_dict_roundtrip(self):
        """Test that to_dict produces valid output."""
        understanding = ObjectUnderstanding(
            category="arcade_cabinet",
            rests_on_surface=True,
            style_tag="stylized_clean",
            scale_anchor=ScaleAnchor(
                overall_height_or_length_m=1.8,
                reasoning="Standard arcade machine height"
            )
        )
        
        d = understanding.to_dict()
        
        assert d["category"] == "arcade_cabinet"
        assert d["rests_on_surface"] is True
        assert d["style_tag"] == "stylized_clean"
        assert d["scale_anchor_m"]["overall_height_or_length"] == 1.8
    
    def test_json_extraction_direct(self):
        """Test JSON extraction from clean JSON."""
        text = '{"category": "test", "rests_on_surface": true}'
        result = Stage0Understanding._extract_json(text)
        assert result["category"] == "test"
    
    def test_json_extraction_markdown(self):
        """Test JSON extraction from markdown code block."""
        text = '''Here's the analysis:
```json
{"category": "test", "rests_on_surface": true}
```
'''
        result = Stage0Understanding._extract_json(text)
        assert result["category"] == "test"
    
    def test_json_extraction_embedded(self):
        """Test JSON extraction from text with embedded JSON."""
        text = 'The object is {"category": "test", "rests_on_surface": true} as shown.'
        result = Stage0Understanding._extract_json(text)
        assert result["category"] == "test"
    
    def test_valid_style_tags_complete(self):
        """Test that all valid style tags are recognized."""
        expected = {
            "hard_surface_industrial",
            "organic_worn",
            "stylized_clean",
            "soft_domestic",
        }
        assert VALID_STYLE_TAGS == expected


class TestStage0Integration:
    """Integration tests for Stage 0 with mocked model_manager."""
    
    @pytest.mark.asyncio
    async def test_run_with_valid_response(self):
        """Test full run with a valid LLM response."""
        mock_manager = MagicMock()
        mock_manager.get_model_for_workflow.return_value = "test_model"
        mock_manager.generate_async = AsyncMock(return_value='''
{
    "category": "communication_tower",
    "rests_on_surface": true,
    "style_tag": "hard_surface_industrial",
    "scale_anchor_m": {
        "overall_height_or_length": 7.5,
        "reasoning": "Small radio mast"
    }
}
''')
        
        result = await Stage0Understanding.run(
            prompt="A sci-fi communication tower",
            model_manager=mock_manager,
            task_id="test_123",
        )
        
        assert result.category == "communication_tower"
        assert result.scale_anchor.overall_height_or_length_m == 7.5
        mock_manager.generate_async.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_run_with_invalid_response_raises(self):
        """Test that invalid LLM response raises Stage0Error."""
        mock_manager = MagicMock()
        mock_manager.get_model_for_workflow.return_value = "test_model"
        mock_manager.generate_async = AsyncMock(return_value="This is not JSON")
        
        with pytest.raises(Stage0Error, match="parse JSON"):
            await Stage0Understanding.run(
                prompt="test",
                model_manager=mock_manager,
                task_id="test_123",
            )


class TestStage0RealWorldCases:
    """Test cases based on real-world objects from the blueprint."""
    
    def test_training_dummy(self):
        """Test training dummy scale anchor."""
        data = {
            "category": "training_dummy",
            "rests_on_surface": True,
            "style_tag": "hard_surface_industrial",
            "scale_anchor_m": {
                "overall_height_or_length": 1.7,
                "reasoning": "Human-height martial arts target"
            }
        }
        result = Stage0Understanding._validate_and_build(data)
        assert 1.5 <= result.scale_anchor.overall_height_or_length_m <= 2.0
    
    def test_arcade_cabinet(self):
        """Test arcade cabinet scale anchor."""
        data = {
            "category": "arcade_cabinet",
            "rests_on_surface": True,
            "style_tag": "stylized_clean",
            "scale_anchor_m": {
                "overall_height_or_length": 1.8,
                "reasoning": "Standard arcade machine"
            }
        }
        result = Stage0Understanding._validate_and_build(data)
        assert 1.6 <= result.scale_anchor.overall_height_or_length_m <= 2.0
    
    def test_dumbbell_free_floating(self):
        """Test dumbbell as free-floating object."""
        data = {
            "category": "dumbbell",
            "rests_on_surface": False,
            "style_tag": "hard_surface_industrial",
            "scale_anchor_m": {
                "overall_height_or_length": 0.4,
                "reasoning": "Standard dumbbell length"
            }
        }
        result = Stage0Understanding._validate_and_build(data)
        assert result.rests_on_surface is False
    
    def test_coffee_mug(self):
        """Test coffee mug scale anchor."""
        data = {
            "category": "coffee_mug",
            "rests_on_surface": True,
            "style_tag": "soft_domestic",
            "scale_anchor_m": {
                "overall_height_or_length": 0.10,
                "reasoning": "Typical coffee mug height"
            }
        }
        result = Stage0Understanding._validate_and_build(data)
        assert 0.08 <= result.scale_anchor.overall_height_or_length_m <= 0.15
