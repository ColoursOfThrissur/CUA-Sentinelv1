"""Test suite for Phase 1 procedural PBR shader material system."""

import pytest
from core.blender_pipeline.progressive_v2.materials import (
    MATERIAL_PRESETS,
    MaterialPreset,
    get_material_preset,
    get_material_for_description,
)
from core.blender_pipeline.progressive_v2.manifest import (
    MaterialSpec,
    BuildManifest,
    ManifestNode,
    NodeKind,
    NodeState,
    GeometrySpec,
)
from core.blender_pipeline.progressive_v2.executor import BlenderExecutor


def test_material_presets_procedural_properties():
    """Ensure key presets define their procedural shading configs properly."""
    wood_presets = ["wood_oak", "wood_walnut", "wood_varnished", "wood_light", "wood_dark"]
    for name in wood_presets:
        preset = get_material_preset(name)
        assert preset is not None, f"Preset {name} should exist"
        assert preset.procedural_texture == "wood"
        assert "scale" in preset.procedural_params
        assert "distortion" in preset.procedural_params

    brushed_presets = ["brushed_steel", "brushed_aluminum"]
    for name in brushed_presets:
        preset = get_material_preset(name)
        assert preset is not None
        assert preset.procedural_texture == "brushed_metal"
        assert preset.anisotropy > 0
        assert "stretch" in preset.procedural_params

    leather = get_material_preset("leather")
    assert leather is not None
    assert leather.procedural_texture == "leather"
    assert "scale" in leather.procedural_params

    marble = get_material_preset("marble_white")
    assert marble is not None
    assert marble.procedural_texture == "marble"
    assert "scale" in marble.procedural_params


def test_material_spec_serialization_roundtrip():
    """Test serialization & deserialization of procedural MaterialSpec."""
    spec = MaterialSpec.from_preset("wood_walnut")
    assert spec.procedural_texture == "wood"
    assert spec.procedural_params["scale"] == 14.0

    d = spec.to_dict()
    assert d["procedural_texture"] == "wood"
    assert d["procedural_params"]["scale"] == 14.0

    restored = MaterialSpec.from_dict(d)
    assert restored.procedural_texture == "wood"
    assert restored.procedural_params["scale"] == 14.0
    assert restored.roughness == spec.roughness
    assert restored.base_color == spec.base_color


def test_executor_generates_procedural_shader_script():
    """Verify BlenderExecutor._material_fragment outputs procedural node logic."""
    executor = BlenderExecutor(mcp_manager=None, task_id="test_task")
    spec = MaterialSpec.from_preset("wood_oak")
    script = executor._material_fragment("seat_obj", spec)

    # Validate node creation strings exist
    assert "ShaderNodeTexWave" in script
    assert "ShaderNodeBump" in script
    assert "ShaderNodeValToRGB" in script
    assert "smart_project" in script
    assert "_tex_coord.outputs['Object']" in script

    # Test leather
    leather_spec = MaterialSpec.from_preset("leather")
    leather_script = executor._material_fragment("cushion_obj", leather_spec)
    assert "ShaderNodeTexVoronoi" in leather_script
    assert "ShaderNodeBump" in leather_script

    # Test brushed metal
    metal_spec = MaterialSpec.from_preset("brushed_steel")
    metal_script = executor._material_fragment("shaft_obj", metal_spec)
    assert "ShaderNodeTexNoise" in metal_script
    assert "Anisotropic" in metal_script or "anisotropy" in metal_script.lower()
