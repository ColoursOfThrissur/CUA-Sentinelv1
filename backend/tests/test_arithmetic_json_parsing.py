import json
import re
from typing import Optional


def extract_outer_json_object(text: str) -> Optional[str]:
    """Finds the JSON object containing action: plan or call_tool with balanced bracket counting."""
    for trigger in ('"action": "plan"', '"action":"plan"', '"action": "call_tool"', '"action":"call_tool"', '"steps":', '"actions":'):
        idx = text.find(trigger)
        if idx != -1:
            start = text.rfind('{', 0, idx)
            if start == -1:
                start = idx
            depth = 0
            in_string = False
            escape = False
            for i in range(start, len(text)):
                char = text[i]
                if escape:
                    escape = False
                    continue
                if char == '\\':
                    escape = True
                    continue
                if char == '"':
                    in_string = not in_string
                    continue
                if not in_string:
                    if char == '{':
                        depth += 1
                    elif char == '}':
                        depth -= 1
                        if depth == 0:
                            return text[start:i+1]
    return None


def test_arithmetic_json_expression_cleaning():
    resp = """A multi-part modern desk lamp. The base is a flat cylinder exactly 20 cm in diameter and 2 cm in height, resting on the ground plane. A vertical stem, formed by a cylinder 2 cm in diameter and 40 cm in height, sits exactly in the top center of the base. At the very top of the stem is the lamp head: a rectangular prism measuring 25 cm in length, 5 cm in width, and 2 cm in thickness. The lamp head is rotated 90 degrees so it extends horizontally.
{"action": "plan", "steps": [
  {"tool": "blender:create_cylinder", "args": {"name": "base", "radius": 10, "depth": 2, "location": [0, 0, 1], "rotation": [0, 0, 0]}},
  {"tool": "blender:create_cylinder", "args": {"name": "stem", "radius": 1, "depth": 40, "location": [0, 0, 2 + 2/2], "rotation": [0, 0, 0]}},
  {"tool": "blender:create_box", "args": {"name": "lamp_head", "size": [25, 5, 2], "location": [0, 0, 40 + 2/2], "rotation": [0, 90, 0]}}
]}"""

    def _eval_sub(match):
        try:
            val = eval(match.group(0), {"__builtins__": {}}, {})
            return str(round(float(val), 4))
        except Exception:
            return match.group(0)

    raw_json = extract_outer_json_object(resp)
    assert raw_json is not None

    cleaned = re.sub(
        r'(?<=[,\[\s])\d+(?:\.\d+)?\s*[\+\-\*\/]\s*\d+(?:\.\d+)?(?:\s*[\+\-\*\/]\s*\d+(?:\.\d+)?)?',
        _eval_sub,
        raw_json,
    )
    parsed = json.loads(cleaned)
    assert len(parsed["steps"]) == 3
    assert parsed["steps"][1]["args"]["location"] == [0, 0, 3.0]
    assert parsed["steps"][2]["args"]["location"] == [0, 0, 41.0]


def test_resolver_skips_rotated_cylinders():
    """Resolver must not apply Z-axis position formulas to cylinders with non-zero rotation.
    A horizontal stem (rotation=[0,90,0]) must pass through unchanged.
    This is the exact failure mode that caused the desk lamp stem to be placed at z=-18.
    """
    from core.primitive_geometry_resolver import resolve_blender_plan

    steps = [
        ("blender:create_cylinder", {"name": "base", "radius": 10, "depth": 2, "location": [0, 0, 1]}),
        ("blender:create_cylinder", {"name": "stem", "radius": 1, "depth": 40,
                                      "location": [0, 0, -18], "rotation": [0, 90, 0]}),
    ]
    result = resolve_blender_plan(steps)

    # stem has rotation=[0,90,0] — resolver must not touch its location
    stem_args = next(a for t, a in result if a.get("name") == "stem")
    assert stem_args["location"] == [0, 0, -18], (
        f"Resolver must not modify a rotated cylinder's location, got {stem_args['location']}"
    )


def test_resolver_skips_flush_top_when_no_inner_cavity():
    """Flush-top rod formula must only fire when there is an inner cavity.
    A stem sitting on top of a base (no hollow cavity) must not be repositioned
    by the flush-top formula, even if its depth > base depth and radius < base radius.
    """
    from core.primitive_geometry_resolver import resolve_blender_plan

    # Lamp plan: base (r=10, d=2) and upright stem (r=1, d=40) — no inner cavity
    steps = [
        ("blender:create_cylinder", {"name": "base", "radius": 10, "depth": 2, "location": [0, 0, 1]}),
        ("blender:create_cylinder", {"name": "stem", "radius": 1, "depth": 40, "location": [0, 0, 22]}),
    ]
    result = resolve_blender_plan(steps)

    stem_args = next(a for t, a in result if a.get("name") == "stem")
    # No inner cavity exists, so flush-top formula must not fire
    assert stem_args["location"][2] == 22, (
        f"Resolver must not apply flush-top formula without an inner cavity, got z={stem_args['location'][2]}"
    )


def test_resolver_still_corrects_rod_inside_vessel():
    """Flush-top formula must still fire for a rod that is genuinely inside a hollow vessel.
    Carafe (r=5, d=20) with inner cavity (r=4.7, d=19.7) and a plunger rod (r=0.25, d=22).
    Rod is inside the cavity (r=0.25 < inner_r=4.7), so flush-top correction applies.
    """
    from core.primitive_geometry_resolver import resolve_blender_plan

    steps = [
        ("blender:create_cylinder", {"name": "carafe", "radius": 5, "depth": 20, "location": [0, 0, 0]}),
        ("blender:create_cylinder", {"name": "carafe_inner", "radius": 4.7, "depth": 19.7, "location": [0, 0, 0]}),
        # Rod placed at wrong z=10 (LLM error) — should be corrected to 0+10-11=-1
        ("blender:create_cylinder", {"name": "rod", "radius": 0.25, "depth": 22, "location": [0, 0, 10]}),
    ]
    result = resolve_blender_plan(steps)

    rod_args = next(a for t, a in result if a.get("name") == "rod")
    # correct_z = outer_center_z + outer_depth/2 - rod_depth/2 = 0 + 10 - 11 = -1
    assert abs(rod_args["location"][2] - (-1.0)) < 0.01, (
        f"Rod inside vessel should be corrected to z=-1, got z={rod_args['location'][2]}"
    )



    """Sibling test: same arithmetic-in-JSON structure as the dumbbell test,
    using a completely different object category (teapot with lateral spout offset).
    Verifies the cleaner is not pattern-matched to dumbbell/symmetric shapes."""
    import ast

    prompt = """{"action": "plan", "steps": [
  {"tool": "blender:create_sphere", "args": {"name": "body", "radius": 6, "location": [0, 0, 6]}},
  {"tool": "blender:create_cylinder", "args": {"name": "spout", "radius": 0.8, "depth": 7, "location": [6 + (7/2), 0, 7], "rotation": [0, 90, 0]}},
  {"tool": "blender:create_torus", "args": {"name": "handle", "major_radius": 3, "minor_radius": 0.5, "location": [-(6 + 3), 0, 6]}}
]}"""

    def _safe_eval_math(expr_str: str) -> float:
        if not re.match(r"^[\s0-9\.\+\-\*\/\(\)]+$", expr_str):
            raise ValueError(f"Unsafe expression: {expr_str}")
        tree = ast.parse(expr_str, mode='eval')
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant,
                                     ast.Add, ast.Sub, ast.Mult, ast.Div, ast.USub, ast.UAdd)):
                raise ValueError("Disallowed AST node")
        return float(eval(compile(tree, filename="<math>", mode="eval"), {"__builtins__": {}}, {}))

    def _replace_math(match):
        prefix = match.group(1)
        expr = match.group(2).strip()
        suffix = match.group(3)
        if re.match(r'^-?\d+(?:\.\d+)?$', expr) or expr in ('true', 'false', 'null', '""'):
            return match.group(0)
        try:
            val = _safe_eval_math(expr)
            return f"{prefix} {round(val, 4)}{suffix}"
        except Exception:
            return match.group(0)

    raw_json = extract_outer_json_object(prompt)
    assert raw_json is not None

    pattern = r'([\[,:]\s*)([\s0-9\.\+\-\*\/\(\)]*[\+\-\*\/][\s0-9\.\+\-\*\/\(\)]*?)(\s*[,\]\}])'
    cleaned = raw_json
    for _ in range(5):
        prev = cleaned
        cleaned = re.sub(pattern, _replace_math, cleaned)
        if cleaned == prev:
            break

    parsed = json.loads(cleaned)
    assert len(parsed["steps"]) == 3
    # spout: 6 + 7/2 = 9.5
    assert parsed["steps"][1]["args"]["location"][0] == 9.5
    # handle: -(6 + 3) = -9.0
    assert parsed["steps"][2]["args"]["location"][0] == -9.0

    """Verify that plans with negative coordinates and parentheses like [-15 - (12/2), 0, 0] parse cleanly."""
    prompt = """A heavy adjustable dumbbell centered at the origin, aligned along the X-axis.
{"action": "plan", "steps": [
  {"tool": "blender:create_cylinder", "args": {"name": "grip", "radius": 1.5, "depth": 15, "location": [0, 0, 0], "rotation": [0, 0, 0]}},
  {"tool": "blender:create_box", "args": {"name": "left_weight_plate", "size": [12, 12, 4], "location": [-15 - (12/2), 0, 0], "rotation": [0, 0, 0]}},
  {"tool": "blender:create_box", "args": {"name": "right_weight_plate", "size": [12, 12, 4], "location": [15 + (12/2), 0, 0], "rotation": [0, 0, 0]}},
  {"tool": "blender:create_cylinder", "args": {"name": "left_locking-collar", "radius": 2.5, "depth": 2, "location": [-15 - (12/2) - (5/2), 0, 0], "rotation": [0, 0, 0]}},
  {"tool": "blender:create_cylinder", "args": {"name": "right_locking-collar", "radius": 2.5, "depth": 2, "location": [15 + (12/2) + (5/2), 0, 0], "rotation": [0, 0, 0]}}
]}"""
    import ast

    def _safe_eval_math(expr_str: str) -> float:
        if not re.match(r"^[\s0-9\.\+\-\*\/\(\)]+$", expr_str):
            raise ValueError(f"Unsafe expression: {expr_str}")
        tree = ast.parse(expr_str, mode='eval')
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.USub, ast.UAdd)):
                raise ValueError("Disallowed AST node")
        return float(eval(compile(tree, filename="<math>", mode="eval"), {"__builtins__": {}}, {}))

    def _replace_math(match):
        prefix = match.group(1)
        expr = match.group(2).strip()
        suffix = match.group(3)
        if re.match(r'^-?\d+(?:\.\d+)?$', expr) or expr in ('true', 'false', 'null', '""'):
            return match.group(0)
        try:
            val = _safe_eval_math(expr)
            return f"{prefix} {round(val, 4)}{suffix}"
        except Exception:
            return match.group(0)

    raw_json = extract_outer_json_object(prompt)
    assert raw_json is not None

    pattern = r'([\[,:]\s*)([\s0-9\.\+\-\*\/\(\)]*[\+\-\*\/][\s0-9\.\+\-\*\/\(\)]*?)(\s*[,\]\}])'
    cleaned = raw_json
    for _ in range(5):
        prev = cleaned
        cleaned = re.sub(pattern, _replace_math, cleaned)
        if cleaned == prev:
            break

    parsed = json.loads(cleaned)
    assert len(parsed["steps"]) == 5
    assert parsed["steps"][1]["args"]["location"] == [-21.0, 0, 0]
    assert parsed["steps"][2]["args"]["location"] == [21.0, 0, 0]
    assert parsed["steps"][3]["args"]["location"] == [-23.5, 0, 0]
    assert parsed["steps"][4]["args"]["location"] == [23.5, 0, 0]
