"""Tests for CodegenLinter — Phase 3 static pre-flight check verification."""

import pytest
from core.codegen_linter import lint, CodegenLintError
from core.blender_ops import CreateBoxParams, render_op_script


def test_codegen_linter_catches_missing_math_import():
    """Verify that using math.radians without import math is caught locally pre-flight."""
    broken_template = """
import bpy
import json

params = json.loads(PARAMS_JSON)
rot = params.get("rotation")
# Intentionally missing import math!
rot_rad = tuple(math.radians(r) for r in rot) if rot else (0, 0, 0)
bpy.ops.mesh.primitive_cube_add(location=(0,0,0), rotation=rot_rad)
"""
    p = CreateBoxParams(name="test_box", size=[1, 1, 1], location=[0, 0, 0], rotation=[0, 90, 0])

    with pytest.raises(CodegenLintError) as exc_info:
        render_op_script(broken_template, p)

    err_msg = str(exc_info.value)
    assert "math" in err_msg, f"Expected 'math' to be reported as missing name, got: {err_msg}"


def test_codegen_linter_passes_valid_template():
    """Verify that a valid template with all required imports passes cleanly."""
    valid_template = """
import bpy
import json
import math

params = json.loads(PARAMS_JSON)
rot = params.get("rotation")
rot_rad = tuple(math.radians(r) for r in rot) if rot else (0, 0, 0)
bpy.ops.mesh.primitive_cube_add(location=(0,0,0), rotation=rot_rad)
"""
    p = CreateBoxParams(name="test_box", size=[1, 1, 1], location=[0, 0, 0], rotation=[0, 90, 0])
    script = render_op_script(valid_template, p)
    assert "PARAMS_JSON" in script
    assert "primitive_cube_add" in script
