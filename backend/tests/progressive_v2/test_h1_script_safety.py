import pytest
import ast
import json
from core.blender_pipeline.progressive_v2.executor import _build_script, _PAYLOAD_SENTINEL, _BOX_TEMPLATE

def is_valid_python(code: str) -> bool:
    try:
        ast.parse(code)
        return True
    except SyntaxError:
        return False

def test_payload_sentinel_not_corrupted():
    payload = {"name": _PAYLOAD_SENTINEL, "size": [1, 2, 3], "matrix_rows": [], "collection": "coll"}
    script = _build_script(_BOX_TEMPLATE, payload)
    assert is_valid_python(script)
    assert script.count(_PAYLOAD_SENTINEL) == 1

def test_hostile_object_name_single_quote():
    payload = {"name": "evil'name", "size": [1, 2, 3], "matrix_rows": [], "collection": "coll"}
    script = _build_script(_BOX_TEMPLATE, payload)
    assert is_valid_python(script)

def test_hostile_object_name_triple_quote():
    payload = {"name": "'''triple'''", "size": [1, 2, 3], "matrix_rows": [], "collection": "coll"}
    script = _build_script(_BOX_TEMPLATE, payload)
    assert is_valid_python(script)

def test_hostile_object_name_backslash():
    payload = {"name": "C:\\path\\to", "size": [1, 2, 3], "matrix_rows": [], "collection": "coll"}
    script = _build_script(_BOX_TEMPLATE, payload)
    assert is_valid_python(script)

def test_hostile_object_name_newline():
    payload = {"name": "line1\nline2", "size": [1, 2, 3], "matrix_rows": [], "collection": "coll"}
    script = _build_script(_BOX_TEMPLATE, payload)
    assert is_valid_python(script)

def test_hostile_object_name_emoji():
    payload = {"name": "🛸part", "size": [1, 2, 3], "matrix_rows": [], "collection": "coll"}
    script = _build_script(_BOX_TEMPLATE, payload)
    assert is_valid_python(script)

def test_hostile_object_name_null_byte():
    payload = {"name": "null\x00byte", "size": [1, 2, 3], "matrix_rows": [], "collection": "coll"}
    script = _build_script(_BOX_TEMPLATE, payload)
    assert is_valid_python(script)

def test_hostile_object_name_non_latin():
    payload = {"name": "部品_001", "size": [1, 2, 3], "matrix_rows": [], "collection": "coll"}
    script = _build_script(_BOX_TEMPLATE, payload)
    assert is_valid_python(script)
