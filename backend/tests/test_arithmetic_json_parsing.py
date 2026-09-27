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


def test_dumbbell_arithmetic_with_negatives_and_parentheses():
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
