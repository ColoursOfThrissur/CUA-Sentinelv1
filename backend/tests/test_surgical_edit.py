import os
import sys
import pytest
from pathlib import Path

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
repo_root = os.path.dirname(backend_dir)
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from tools.desktop_tool import DesktopTool


@pytest.fixture
def temp_desktop(tmp_path, monkeypatch):
    monkeypatch.setenv("SENTINEL_DESKTOP_DIR", str(tmp_path))
    DesktopTool._session_read_files.clear()
    return tmp_path


def test_surgical_edit_read_before_write_enforced(temp_desktop):
    target = temp_desktop / "test_file.txt"
    target.write_text("Hello World\nLine 2\n", encoding="utf-8")

    tool = DesktopTool()
    # Attempting to edit without reading first should fail
    res = tool.surgical_edit_file("test_file.txt", "World", "Sentinel", require_read=True)
    assert res["status"] == "FAILED"
    assert "invariant violated" in res["error"]


def test_surgical_edit_success_after_read(temp_desktop):
    target = temp_desktop / "test_file.txt"
    target.write_text("def hello():\n    print('Hello World')\n", encoding="utf-8")

    tool = DesktopTool()
    read_res = tool.desktop_file_read("test_file.txt")
    assert read_res["status"] == "SUCCESS"
    assert "Hello World" in read_res["content"]

    edit_res = tool.surgical_edit_file("test_file.txt", "Hello World", "Hello Sentinel")
    assert edit_res["status"] == "SUCCESS"
    assert target.read_text(encoding="utf-8") == "def hello():\n    print('Hello Sentinel')\n"


def test_surgical_edit_rejects_ambiguous_match(temp_desktop):
    target = temp_desktop / "ambig.txt"
    target.write_text("foo bar foo\n", encoding="utf-8")

    tool = DesktopTool()
    tool.desktop_file_read("ambig.txt")
    res = tool.surgical_edit_file("ambig.txt", "foo", "baz")
    assert res["status"] == "FAILED"
    assert "ambiguous" in res["error"]


def test_surgical_edit_rejects_missing_string(temp_desktop):
    target = temp_desktop / "missing.txt"
    target.write_text("alpha beta gamma\n", encoding="utf-8")

    tool = DesktopTool()
    tool.desktop_file_read("missing.txt")
    res = tool.surgical_edit_file("missing.txt", "delta", "epsilon")
    assert res["status"] == "FAILED"
    assert "not found" in res["error"]


def test_surgical_edit_python_syntax_error_rollback(temp_desktop):
    target = temp_desktop / "script.py"
    original_code = "def valid():\n    return 42\n"
    target.write_text(original_code, encoding="utf-8")

    tool = DesktopTool()
    tool.desktop_file_read("script.py")

    # Introduce invalid python syntax
    bad_edit = tool.surgical_edit_file("script.py", "return 42", "return )(")
    assert bad_edit["status"] == "SYNTAX_ERROR"
    assert bad_edit["reverted"] is True
    # Verify file was NOT modified on disk
    assert target.read_text(encoding="utf-8") == original_code


def test_surgical_edit_json_syntax_error_rollback(temp_desktop):
    target = temp_desktop / "config.json"
    original_json = '{"key": "value"}'
    target.write_text(original_json, encoding="utf-8")

    tool = DesktopTool()
    tool.desktop_file_read("config.json")

    bad_json = tool.surgical_edit_file("config.json", '"value"', '{"unclosed')
    assert bad_json["status"] == "SYNTAX_ERROR"
    assert bad_json["reverted"] is True
    assert target.read_text(encoding="utf-8") == original_json


# ---------------------------------------------------------------------------
# CodeDiffEngine & ProjectWriteService Surgical Edit Tests (Claude Code Harness)
# ---------------------------------------------------------------------------
from core.code_diff_engine import CodeDiffEngine, code_diff_engine
from core.project_write_service import ProjectWriteService


def test_code_diff_engine_read_before_write_enforced(tmp_path):
    target = tmp_path / "module.py"
    target.write_text("def run():\n    return True\n", encoding="utf-8")

    CodeDiffEngine.clear_session_reads()
    engine = CodeDiffEngine()

    block = """<<<<<<< SEARCH
    return True
=======
    return False
>>>>>>> REPLACE"""

    res = engine.apply_search_replace_blocks(str(target), block, require_read=True)
    assert res["success"] is False
    assert "Read-before-write invariant violated" in res["error"]
    assert target.read_text(encoding="utf-8") == "def run():\n    return True\n"


def test_code_diff_engine_unique_exact_match_success(tmp_path):
    target = tmp_path / "service.py"
    original = "def compute():\n    x = 10\n    return x * 2\n"
    target.write_text(original, encoding="utf-8")

    CodeDiffEngine.clear_session_reads()
    CodeDiffEngine.record_file_read(str(target))
    engine = CodeDiffEngine()

    block = """<<<<<<< SEARCH
    x = 10
    return x * 2
=======
    x = 25
    return x * 4
>>>>>>> REPLACE"""

    res = engine.apply_search_replace_blocks(str(target), block, require_read=True)
    assert res["success"] is True
    assert res["blocks_applied"] == 1
    assert target.read_text(encoding="utf-8") == "def compute():\n    x = 25\n    return x * 4\n"


def test_code_diff_engine_rejects_ambiguous_search_block(tmp_path):
    target = tmp_path / "dups.py"
    original = "def a():\n    return 42\n\ndef b():\n    return 42\n"
    target.write_text(original, encoding="utf-8")

    CodeDiffEngine.clear_session_reads()
    CodeDiffEngine.record_file_read(str(target))
    engine = CodeDiffEngine()

    # Ambiguous block matching both functions
    block = """<<<<<<< SEARCH
    return 42
=======
    return 99
>>>>>>> REPLACE"""

    res = engine.apply_search_replace_blocks(str(target), block, require_read=True)
    assert res["success"] is False
    assert "ambiguous" in res["error"].lower()
    assert "found 2 exact occurrences" in res["error"].lower()
    # Disk remains completely untouched
    assert target.read_text(encoding="utf-8") == original


def test_code_diff_engine_rejects_missing_search_block(tmp_path):
    target = tmp_path / "target.py"
    original = "def existing():\n    pass\n"
    target.write_text(original, encoding="utf-8")

    CodeDiffEngine.clear_session_reads()
    CodeDiffEngine.record_file_read(str(target))
    engine = CodeDiffEngine()

    block = """<<<<<<< SEARCH
def nonexistent():
    return None
=======
def replaced():
    return 1
>>>>>>> REPLACE"""

    res = engine.apply_search_replace_blocks(str(target), block, require_read=True)
    assert res["success"] is False
    assert "not found in file" in res["error"].lower()
    assert target.read_text(encoding="utf-8") == original


def test_code_diff_engine_atomic_all_or_nothing(tmp_path):
    target = tmp_path / "multi.py"
    original = "def one():\n    return 1\n\ndef two():\n    return 2\n"
    target.write_text(original, encoding="utf-8")

    CodeDiffEngine.clear_session_reads()
    CodeDiffEngine.record_file_read(str(target))
    engine = CodeDiffEngine()

    # Block 1 is valid, but Block 2 does not exist
    multi_block = """<<<<<<< SEARCH
def one():
    return 1
=======
def one():
    return 100
>>>>>>> REPLACE
<<<<<<< SEARCH
def three():
    return 3
=======
def three():
    return 300
>>>>>>> REPLACE"""

    res = engine.apply_search_replace_blocks(str(target), multi_block, require_read=True)
    assert res["success"] is False
    assert "not found in file" in res["error"].lower()
    # CRITICAL: Block 1 must NOT be partially written to disk
    assert target.read_text(encoding="utf-8") == original


def test_code_diff_engine_syntax_error_aborts_write(tmp_path):
    target = tmp_path / "valid.py"
    original = "def compute():\n    return 10\n"
    target.write_text(original, encoding="utf-8")

    CodeDiffEngine.clear_session_reads()
    CodeDiffEngine.record_file_read(str(target))
    engine = CodeDiffEngine()

    # Introduce invalid python syntax
    bad_syntax_block = """<<<<<<< SEARCH
def compute():
    return 10
=======
def compute():
    return ))broken syntax((
>>>>>>> REPLACE"""

    res = engine.apply_search_replace_blocks(str(target), bad_syntax_block, require_read=True)
    assert res["success"] is False
    assert "SYNTAX_ERROR" in res["error"]
    assert res.get("reverted") is True
    # Disk remains unaltered
    assert target.read_text(encoding="utf-8") == original


def test_code_diff_engine_crlf_lf_resilience(tmp_path):
    target = tmp_path / "windows_file.py"
    # Write file with Windows CRLF line endings
    original = "def first():\r\n    return 1\r\n\r\ndef second():\r\n    return 2\r\n"
    with open(str(target), "wb") as f:
        f.write(original.encode("utf-8"))

    CodeDiffEngine.clear_session_reads()
    CodeDiffEngine.record_file_read(str(target))
    engine = CodeDiffEngine()

    # Search block with LF line endings
    block_lf = "<<<<<<< SEARCH\ndef first():\n    return 1\n=======\ndef first():\n    return 10\n>>>>>>> REPLACE"

    res = engine.apply_search_replace_blocks(str(target), block_lf, require_read=True)
    assert res["success"] is True
    assert res["blocks_applied"] == 1
    content = target.read_text(encoding="utf-8")
    assert "return 10" in content


def test_project_write_service_apply_surgical_edit(tmp_path, monkeypatch):
    # Set workspace root
    proj_dir = tmp_path / "workspace"
    proj_dir.mkdir()
    target = proj_dir / "app.py"
    target.write_text("def start():\n    print('start')\n", encoding="utf-8")

    monkeypatch.setenv("SENTINEL_WORKSPACE_ROOT", str(proj_dir))
    from core.path_security import path_security
    path_security._cached_drives = [str(tmp_path).lower()]

    service = ProjectWriteService()
    CodeDiffEngine.record_file_read(str(target))

    block = """<<<<<<< SEARCH
def start():
    print('start')
=======
def start():
    print('running')
>>>>>>> REPLACE"""

    res = service.apply_surgical_edit(str(proj_dir), "app.py", block, require_read=True)
    assert res["success"] is True
    assert target.read_text(encoding="utf-8") == "def start():\n    print('running')\n"


def test_code_refactor_agent_extract_and_write_prioritizes_search_replace(tmp_path, monkeypatch):
    proj_dir = tmp_path / "proj"
    proj_dir.mkdir()
    target = proj_dir / "calc.py"
    target.write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")

    monkeypatch.setenv("SENTINEL_WORKSPACE_ROOT", str(proj_dir))
    from core.path_security import path_security
    path_security._cached_drives = [str(tmp_path).lower()]

    from agents.code_refactor_agent import CodeRefactorAgent
    from unittest.mock import MagicMock
    agent = CodeRefactorAgent(MagicMock(), MagicMock(), {})

    llm_output = """Here is the surgical fix:
<<<<<<< SEARCH
def add(a, b):
    return a - b
=======
def add(a, b):
    return a + b
>>>>>>> REPLACE
"""
    CodeDiffEngine.record_file_read(str(target))
    written = agent._extract_and_write_code_blocks(str(proj_dir), llm_output, target_file_path="calc.py")
    assert written == ["calc.py"]
    assert target.read_text(encoding="utf-8") == "def add(a, b):\n    return a + b\n"


