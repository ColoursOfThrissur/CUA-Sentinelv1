"""Comprehensive Automated Test Suite for Milestone 0 MCP Security Hardening & Fail-Closed Governance.

Verifies:
1. Missing required governance flags in registry fail closed at load and gate.
2. deny_all: true and allowed_agents: [] unconditionally block execution; no __all__ wildcard bypass.
3. taint_deny: true hard-denies under tainted context.
4. Single-decision approval: tainted L3 tool requests and consumes exactly one approval.
5. Safe mode denial occurs before approval consumption (does not burn approval).
6. Lockfile verification: unlisted tools are hidden; schema hash mismatch disables app.
7. Direct call to mcp:blender:execute_blender_code is denied to agents.
8. Pydantic parameter validation in blender_ops rejects injection attacks, NaN, and Inf.
9. call_locked succeeds for internal tools and rejects non-internal tools with LockViolationError.
10. call_tool timeout raises MCPTimeoutError and transitions scene_state to UNKNOWN.
11. isError: true on tool invocation raises MCPToolError.
12. Subprocess environment isolation strips host secrets (JWT, tokens, credentials).
"""

import os
import sys
import uuid
import math
import json
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path
from pydantic import ValidationError

# Ensure backend directory is in sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from core.governance import GovernanceEngine, GovernanceViolation, HITLRequired
from db.connections import get_operational_db
from config.loader import (
    load_policy_rules,
    load_system_config,
    load_tool_registry,
    validate_tool_registry,
)
from core.mcp_manager import (
    MCPManager,
    MCPAppConnection,
    MCPToolDescriptor,
    MCPTimeoutError,
    MCPToolError,
    LockMismatchError,
    LockViolationError,
    compute_schema_hash,
)
from core.blender_ops import (
    CreateBoxParams,
    CreateSphereParams,
    SetTransformParams,
    GetManifestParams,
    render_op_script,
    parse_op_output,
    _CREATE_BOX_TEMPLATE,
)
from agents.base_agent import BaseAgent


@pytest.fixture
def gov_engine():
    policy = load_policy_rules()
    config = load_system_config()
    return GovernanceEngine(policy, config)


# ==============================================================================
# 1. Missing Required Governance Flags Fail Closed
# ==============================================================================
def test_registry_missing_required_flags_fail_closed(gov_engine):
    """Missing required governance flags in registry must fail closed at load and at gate."""
    # At gate check: registry_meta missing required flags
    incomplete_meta = {
        "side_effect": "read",
        "risk_level": "L0",
        "allowed_agents": ["endpoint_agent"],
        # Missing: deny_all, taint_deny, taint_safe, egress, returns_untrusted, reads_private_data
    }
    with pytest.raises(GovernanceViolation, match="missing required governance flag"):
        gov_engine.check_tool_execution_safety(
            tool_name="test_incomplete_tool",
            caller_agent="endpoint_agent",
            registry_meta=incomplete_meta,
        )

    # At registry validation: invalid registry dictionary
    bad_registry = {
        "tools": {
            "bad_tool": {
                "name": "bad_tool",
                "side_effect": "act",
                "risk_level": "L2",
            }
        }
    }
    with pytest.raises(ValueError, match="missing required flag"):
        validate_tool_registry(bad_registry)


# ==============================================================================
# 2. deny_all and allowed_agents Fail-Closed Enforcement
# ==============================================================================
def test_deny_all_and_empty_allowed_agents_blocks_execution(gov_engine):
    """deny_all: true and allowed_agents: [] strictly block execution; __all__ wildcard is rejected."""
    base_meta = {
        "side_effect": "read",
        "risk_level": "L0",
        "allowed_agents": ["endpoint_agent"],
        "deny_all": True,
        "taint_deny": False,
        "taint_safe": False,
        "egress": False,
        "returns_untrusted": False,
        "reads_private_data": False,
    }
    # deny_all: true blocks unconditionally
    with pytest.raises(GovernanceViolation, match="denied unconditionally"):
        gov_engine.check_tool_execution_safety(
            tool_name="test_denied_tool",
            caller_agent="endpoint_agent",
            registry_meta=base_meta,
        )

    # allowed_agents: [] blocks execution
    base_meta["deny_all"] = False
    base_meta["allowed_agents"] = []
    with pytest.raises(GovernanceViolation, match="NOT authorized to execute tool"):
        gov_engine.check_tool_execution_safety(
            tool_name="test_denied_tool",
            caller_agent="endpoint_agent",
            registry_meta=base_meta,
        )

    # allowed_agents: ["__all__"] does NOT grant wildcard access
    base_meta["allowed_agents"] = ["__all__"]
    with pytest.raises(GovernanceViolation, match="NOT authorized to execute tool"):
        gov_engine.check_tool_execution_safety(
            tool_name="test_denied_tool",
            caller_agent="endpoint_agent",
            registry_meta=base_meta,
        )


# ==============================================================================
# 3. taint_deny Hard-Denies Under Taint
# ==============================================================================
def test_taint_deny_hard_denies_under_taint(gov_engine):
    """taint_deny: true must hard-deny execution under tainted context with no HITL approval option."""
    meta = {
        "side_effect": "write",
        "risk_level": "L2",
        "allowed_agents": ["code_refactor_agent"],
        "deny_all": False,
        "taint_deny": True,
        "taint_safe": False,
        "egress": False,
        "returns_untrusted": False,
        "reads_private_data": False,
    }
    # Under untainted context, execution succeeds
    approved_meta = gov_engine.check_tool_execution_safety(
        tool_name="test_taint_deny_tool",
        caller_agent="code_refactor_agent",
        untrusted_present=False,
        registry_meta=meta,
    )
    assert approved_meta["risk_level"] == "L2"

    # Under tainted context, must raise GovernanceViolation (hard deny, NOT HITLRequired)
    with pytest.raises(GovernanceViolation, match="HARD DENIED under taint"):
        gov_engine.check_tool_execution_safety(
            tool_name="test_taint_deny_tool",
            caller_agent="code_refactor_agent",
            untrusted_present=True,
            registry_meta=meta,
        )


# ==============================================================================
# 4. Single-Decision Approval for Tainted L3 Tool
# ==============================================================================
def test_single_decision_approval_taint_plus_l3(gov_engine):
    """A tainted L3 tool requests a single approval mentioning both reasons and consumes it once."""
    task_id = f"test_single_dec_{uuid.uuid4().hex}"
    meta = {
        "side_effect": "act",
        "risk_level": "L3",
        "allowed_agents": ["cua_agent"],
        "deny_all": False,
        "taint_deny": False,
        "taint_safe": False,
        "egress": False,
        "returns_untrusted": False,
        "reads_private_data": False,
        "version": "1.0",
    }
    params = {"target": "render_view"}

    # 1. First call triggers HITLRequired with both taint and L3 in the reason
    with pytest.raises(HITLRequired) as exc:
        gov_engine.check_tool_execution_safety(
            tool_name="desktop_click",
            caller_agent="cua_agent",
            task_id=task_id,
            untrusted_present=True,
            taint_origins="web_search",
            params=params,
            registry_meta=meta,
        )
    approval_id = exc.value.approval_id
    assert "tainted context" in exc.value.action_description
    assert "risk level L3" in exc.value.action_description

    # 2. Approve the single HITL request
    resolved = gov_engine.resolve_hitl(approval_id, approved=True, resolved_by="admin")
    assert resolved is True

    # 3. Calling immediately consumes the approval and passes without triggering a second approval
    approved = gov_engine.check_tool_execution_safety(
        tool_name="desktop_click",
        caller_agent="cua_agent",
        task_id=task_id,
        untrusted_present=True,
        taint_origins="web_search",
        params=params,
        registry_meta=meta,
    )
    assert approved.get("risk_level") == "L3"

    # 4. Verify in DB that the record is marked USED
    conn = get_operational_db()
    try:
        row = conn.execute("SELECT status FROM hitl_pending WHERE approval_id = ?", (approval_id,)).fetchone()
        assert row["status"] == "USED"
    finally:
        conn.close()


# ==============================================================================
# 5. Safe Mode Denial Occurs Before Approval Consumption
# ==============================================================================
def test_safe_mode_denial_before_approval_consumption(gov_engine):
    """Safe Mode check executes prior to approval consumption, preserving pending/approved state."""
    task_id = f"test_sm_{uuid.uuid4().hex}"
    meta = {
        "side_effect": "act",
        "risk_level": "L3",
        "allowed_agents": ["cua_agent"],
        "deny_all": False,
        "taint_deny": False,
        "taint_safe": False,
        "egress": False,
        "returns_untrusted": False,
        "reads_private_data": False,
        "version": "1.0",
    }
    params = {"x": 50, "y": 50}

    # Generate and approve an HITL record
    with pytest.raises(HITLRequired) as exc:
        gov_engine.check_tool_execution_safety(
            tool_name="desktop_click",
            caller_agent="cua_agent",
            task_id=task_id,
            params=params,
            registry_meta=meta,
        )
    approval_id = exc.value.approval_id
    gov_engine.resolve_hitl(approval_id, approved=True, resolved_by="admin")

    # Enter Safe Mode
    gov_engine.enter_safe_mode("Emergency safe mode test")
    try:
        with pytest.raises(GovernanceViolation, match="Safe Mode"):
            gov_engine.check_tool_execution_safety(
                tool_name="desktop_click",
                caller_agent="cua_agent",
                task_id=task_id,
                params=params,
                registry_meta=meta,
            )

        # The approval MUST NOT be marked USED; safe mode denied before consumption
        conn = get_operational_db()
        try:
            row = conn.execute("SELECT status FROM hitl_pending WHERE approval_id = ?", (approval_id,)).fetchone()
            assert row["status"] == "APPROVED"
        finally:
            conn.close()
    finally:
        gov_engine.exit_safe_mode()


# ==============================================================================
# 6. Lockfile Verification & Schema Mismatch Detection
# ==============================================================================
@pytest.mark.asyncio
async def test_lockfile_hides_unlisted_tools_and_catches_schema_mismatch():
    """MCP server discovery hides unlisted tools and raises LockMismatchError on modified schemas."""
    mgr = MCPManager()
    mgr.initialize_from_config()
    conn = mgr.get_connection("blender")
    assert conn is not None

    # Mock MCP session
    mock_session = AsyncMock()

    # Tool 1: In lockfile with matching schema
    tool_locked = MagicMock()
    tool_locked.name = "execute_blender_code"
    tool_locked.description = "Server description (ignored)"
    tool_locked.input_schema = {
        "type": "object",
        "properties": {"code": {"type": "string"}},
        "required": ["code"],
    }

    # Tool 2: Not in lockfile (must be silently ignored)
    tool_unlisted = MagicMock()
    tool_unlisted.name = "unlisted_dangerous_tool"
    tool_unlisted.description = "Rogue tool"
    tool_unlisted.input_schema = {}

    mock_session.list_tools = AsyncMock(return_value=MagicMock(tools=[tool_locked, tool_unlisted]))
    conn._session = mock_session

    test_lock = {
        "apps": {
            "blender": {
                "tools": {
                    "execute_blender_code": {
                        "schema_sha256": compute_schema_hash(tool_locked.input_schema),
                        "description": "Internal execution bridge for validated Blender Python templates",
                        "internal_only": True,
                    }
                }
            }
        }
    }

    with patch.object(mgr, "load_lock", return_value=test_lock):
        await mgr._discover_tools(conn)

        discovered_names = [t.name for t in conn.discovered_tools]
        assert "execute_blender_code" in discovered_names
        assert "unlisted_dangerous_tool" not in discovered_names

        # Verify local description was used, NOT server description
        exec_tool = next(t for t in conn.discovered_tools if t.name == "execute_blender_code")
        assert exec_tool.description == "Internal execution bridge for validated Blender Python templates"

        # Test schema tampering: alter schema so hash mismatches
        tool_tampered = MagicMock()
        tool_tampered.name = "execute_blender_code"
        tool_tampered.input_schema = {
            "type": "object",
            "properties": {"code": {"type": "string"}, "extra_field": {"type": "number"}},
            "required": ["code"],
        }
        mock_session.list_tools = AsyncMock(return_value=MagicMock(tools=[tool_tampered]))

        with pytest.raises(LockMismatchError, match="schema hash mismatch"):
            await mgr._discover_tools(conn)

        assert conn.status == "error"
        assert "schema hash mismatch" in conn.error_message


# ==============================================================================
# 7. execute_blender_code Denied to Agents
# ==============================================================================
def test_execute_blender_code_denied_to_agents(gov_engine):
    """mcp:blender:execute_blender_code is internal_only, deny_all, and allowed_agents: []."""
    mgr = MCPManager()
    mgr.initialize_from_config()
    conn = mgr.get_connection("blender")
    conn.discovered_tools = [
        MCPToolDescriptor(
            name="execute_blender_code",
            description="Run Python",
            input_schema={"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"]},
            app_id="blender",
        )
    ]
    entries = mgr.get_tool_registry_entries("blender")
    assert "mcp:blender:execute_blender_code" in entries
    raw_meta = entries["mcp:blender:execute_blender_code"]

    assert raw_meta["internal_only"] is True
    assert raw_meta["deny_all"] is True
    assert raw_meta["allowed_agents"] == []

    # Calling via governance must fail closed
    with pytest.raises(GovernanceViolation, match="denied unconditionally"):
        gov_engine.check_tool_execution_safety(
            tool_name="mcp:blender:execute_blender_code",
            caller_agent="endpoint_agent",
            registry_meta=raw_meta,
        )


# ==============================================================================
# 8. Pydantic Parameter Validation in Typed Ops
# ==============================================================================
def test_pydantic_blender_params_validation():
    """Pydantic schemas enforce regex names, reject NaN/Inf, and parse structured output."""
    # 1. Valid params pass
    box = CreateBoxParams(name="my_box_01", size=[2.0, 3.0, 1.0], location=[0.0, 0.0, 1.0])
    assert box.name == "my_box_01"
    assert box.size == [2.0, 3.0, 1.0]

    # 2. Injection attempts in names are rejected
    malicious_names = [
        'x"); import os; #',
        "cube; drop database",
        "box space",
        "../../etc/passwd",
        'a"b',
        "",
        "a" * 65,  # Exceeds 64 chars
    ]
    for bad_name in malicious_names:
        with pytest.raises(ValidationError):
            CreateBoxParams(name=bad_name)

    # 3. NaN and Inf are rejected
    with pytest.raises(ValidationError):
        CreateSphereParams(name="sphere_nan", radius=float("nan"))
    with pytest.raises(ValidationError):
        CreateSphereParams(name="sphere_inf", radius=float("inf"))
    with pytest.raises(ValidationError):
        SetTransformParams(name="box_inf", location=[0.0, float("-inf"), 0.0])

    # 4. Out of bounds values are rejected
    with pytest.raises(ValidationError):
        CreateBoxParams(name="box_huge", size=[50000.0, 1.0, 1.0])  # max size is 100.0

    # 5. Template rendering safely injects JSON literal
    script = render_op_script(_CREATE_BOX_TEMPLATE, box)
    assert 'PARAMS_JSON = \'{"name":"my_box_01","size":[2.0,3.0,1.0],"location":[0.0,0.0,1.0]}\'' in script or "my_box_01" in script
    assert "bpy.ops.mesh.primitive_cube_add" in script

    # 6. Structured JSON output delimiter parsing
    raw_output = 'Preparing scene...\nSENTINEL_OUTPUT_START{"ok": true, "name": "my_box_01", "location": [0,0,1]}SENTINEL_OUTPUT_END\nDone.'
    parsed = parse_op_output(raw_output)
    assert parsed["ok"] is True
    assert parsed["name"] == "my_box_01"

    # 7. Corrupt or error output from Blender raises clean ValueError
    with pytest.raises(ValueError, match="structured Sentinel payload"):
        parse_op_output("Error: Python syntax error on line 42")

    with pytest.raises(ValueError, match="Object not found"):
        parse_op_output('SENTINEL_OUTPUT_START{"ok": false, "error": "Object not found"}SENTINEL_OUTPUT_END')


# ==============================================================================
# 9. call_locked Internal Enforcement
# ==============================================================================
@pytest.mark.asyncio
async def test_call_locked_internal_enforcement():
    """call_locked strictly requires internal_only: true in mcp_tools.lock.json."""
    mgr = MCPManager()
    mgr.initialize_from_config()

    # Attempting to call an unlocked tool via call_locked raises LockViolationError
    with pytest.raises(LockViolationError, match="not marked internal_only"):
        await mgr.call_locked("blender", "unlisted_tool", {})

    # Valid internal call to execute_blender_code delegates to call_tool
    with patch.object(mgr, "call_tool", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = {"output": "ok", "is_error": False}
        res = await mgr.call_locked("blender", "execute_blender_code", {"code": "print(1)"})
        assert res["output"] == "ok"
        mock_call.assert_awaited_once_with("blender", "execute_blender_code", {"code": "print(1)"}, timeout=60.0)


# ==============================================================================
# 10. MCP Timeout Raises MCPTimeoutError and Marks Scene UNKNOWN
# ==============================================================================
@pytest.mark.asyncio
async def test_mcp_timeout_sets_unknown_scene_state():
    """call_tool enforces timeout, raises MCPTimeoutError, and transitions scene_state to UNKNOWN."""
    mgr = MCPManager()
    mgr.initialize_from_config()
    conn = mgr.get_connection("blender")
    conn.status = "connected"
    conn.scene_state = "SYNCED"

    # Mock session call_tool that sleeps longer than timeout
    async def slow_call(name, arguments):
        await asyncio.sleep(0.5)
        return MagicMock(content=[], isError=False)

    mock_session = MagicMock()
    mock_session.call_tool = slow_call
    conn._session = mock_session

    with pytest.raises(MCPTimeoutError, match="timed out"):
        await mgr.call_tool("blender", "get_scene_info", {}, timeout=0.05)

    assert conn.scene_state == "UNKNOWN"


# ==============================================================================
# 11. MCP isError Response Raises MCPToolError
# ==============================================================================
@pytest.mark.asyncio
async def test_mcp_tool_is_error_raises_exception():
    """When MCP tool response indicates isError=True, call_tool raises MCPToolError."""
    mgr = MCPManager()
    mgr.initialize_from_config()
    conn = mgr.get_connection("blender")
    conn.status = "connected"

    mock_session = AsyncMock()
    text_block = MagicMock()
    text_block.text = "Traceback (most recent call last): NameError: name 'bpy' is not defined"
    mock_result = MagicMock()
    mock_result.isError = True
    mock_result.content = [text_block]
    mock_session.call_tool = AsyncMock(return_value=mock_result)
    conn._session = mock_session

    with pytest.raises(MCPToolError, match="failed: Traceback"):
        await mgr.call_tool("blender", "execute_blender_code", {"code": "bad_code()"})


# ==============================================================================
# 12. Subprocess Environment Isolation Strips Host Secrets
# ==============================================================================
def test_subprocess_env_isolation(monkeypatch):
    """MCPManager.filter_env strips sensitive host variables (JWT, Discord, Gmail, API keys)."""
    # Inject sensitive credentials into host os.environ
    monkeypatch.setenv("SENTINEL_JWT_SECRET", "super-secret-jwt-key-999")
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "discord-bot-secret-xyz")
    monkeypatch.setenv("GMAIL_PASSWORD", "secret-email-password")
    monkeypatch.setenv("BRAVE_API_KEY", "brave-api-key-12345")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "aws-secret-access-key")

    # Filter environment
    clean = MCPManager.filter_env({"PINNED_APP_PORT": "9000"})

    # Assert sensitive variables are completely stripped
    assert "SENTINEL_JWT_SECRET" not in clean
    assert "DISCORD_BOT_TOKEN" not in clean
    assert "GMAIL_PASSWORD" not in clean
    assert "BRAVE_API_KEY" not in clean
    assert "AWS_SECRET_ACCESS_KEY" not in clean

    # Assert safe variables and explicit app parameters are preserved
    assert clean["PINNED_APP_PORT"] == "9000"
    for allowed_key in ["SYSTEMROOT", "PATH", "TEMP", "TMP"]:
        if allowed_key in os.environ:
            assert allowed_key in clean


# ==============================================================================
# 13. Expanded 3D Modeling Toolkit Validation
# ==============================================================================
def test_expanded_3d_modeling_toolkit():
    """All expanded 3D modeling parameter models and templates render and validate safely."""
    from core.blender_ops import (
        CreateCylinderParams, CreateConeParams, CreateTorusParams,
        ApplySubdivisionParams, ApplyBooleanParams, ApplyBevelParams,
        SetSmoothShadingParams, SetMaterialParams, JoinObjectsParams,
        DeleteObjectParams, ClearSceneParams, CreateLightParams, CreateCameraParams,
        render_op_script,
        _CREATE_CYLINDER_TEMPLATE, _CREATE_CONE_TEMPLATE, _CREATE_TORUS_TEMPLATE,
        _APPLY_SUBDIVISION_TEMPLATE, _APPLY_BOOLEAN_TEMPLATE, _APPLY_BEVEL_TEMPLATE,
        _SET_SMOOTH_SHADING_TEMPLATE, _SET_MATERIAL_TEMPLATE, _JOIN_OBJECTS_TEMPLATE,
        _DELETE_OBJECT_TEMPLATE, _CLEAR_SCENE_TEMPLATE, _CREATE_LIGHT_TEMPLATE, _CREATE_CAMERA_TEMPLATE
    )

    # 1. Primitives
    cyl = CreateCylinderParams(name="cyl_01", radius=0.5, depth=3.0, location=[1.0, 2.0, 0.0])
    assert cyl.name == "cyl_01"
    assert "primitive_cylinder_add" in render_op_script(_CREATE_CYLINDER_TEMPLATE, cyl)

    cone = CreateConeParams(name="cone_01", radius1=1.5, depth=4.0, location=[0.0, 0.0, 2.0])
    assert "primitive_cone_add" in render_op_script(_CREATE_CONE_TEMPLATE, cone)

    torus = CreateTorusParams(name="wheel_tire", major_radius=1.0, minor_radius=0.3)
    assert "primitive_torus_add" in render_op_script(_CREATE_TORUS_TEMPLATE, torus)

    # 2. Modifiers
    sub = ApplySubdivisionParams(name="organic_body", levels=2)
    assert "modifier_apply" in render_op_script(_APPLY_SUBDIVISION_TEMPLATE, sub)

    bool_op = ApplyBooleanParams(name="car_body", target_name="window_cutter", operation="DIFFERENCE")
    assert "Boolean" in render_op_script(_APPLY_BOOLEAN_TEMPLATE, bool_op)

    bev = ApplyBevelParams(name="table_top", width=0.02, segments=4)
    assert "Bevel" in render_op_script(_APPLY_BEVEL_TEMPLATE, bev)

    smooth = SetSmoothShadingParams(name="organic_body", smooth=True)
    assert "shade_smooth" in render_op_script(_SET_SMOOTH_SHADING_TEMPLATE, smooth)

    # 3. Materials & Shading
    mat = SetMaterialParams(name="car_body", color=[1.0, 0.0, 0.0, 1.0], metallic=0.9, roughness=0.1)
    assert mat.color == [1.0, 0.0, 0.0, 1.0]
    assert "Principled BSDF" in render_op_script(_SET_MATERIAL_TEMPLATE, mat)

    # 4. Assembly & Scene Control
    join = JoinObjectsParams(names=["part_a", "part_b"], target_name="unified_mesh")
    assert "join()" in render_op_script(_JOIN_OBJECTS_TEMPLATE, join)

    del_op = DeleteObjectParams(name="scratch_cube")
    assert "remove" in render_op_script(_DELETE_OBJECT_TEMPLATE, del_op)

    clear = ClearSceneParams(keep_camera_and_lights=True)
    assert "clear_scene" in render_op_script(_CLEAR_SCENE_TEMPLATE, clear)

    light = CreateLightParams(name="KeyLight", type="SUN", energy=500.0, location=[5.0, -5.0, 10.0])
    assert "SUN" in render_op_script(_CREATE_LIGHT_TEMPLATE, light)

    cam = CreateCameraParams(name="StudioCam", location=[8.0, -8.0, 6.0])
    assert "create_camera" in render_op_script(_CREATE_CAMERA_TEMPLATE, cam)

    # 5. Injection rejection in new parameters
    with pytest.raises(ValidationError):
        CreateCylinderParams(name="bad;import os;")
    with pytest.raises(ValidationError):
        ApplyBooleanParams(name="ok_name", target_name="evil'quote", operation="DIFFERENCE")
    with pytest.raises(ValidationError):
        ApplyBooleanParams(name="ok_name", target_name="target", operation="INVALID_OP")
    with pytest.raises(ValidationError):
        SetMaterialParams(name="mesh", color=[2.5, 0.0, 0.0])  # > 1.0
    with pytest.raises(ValidationError):
        JoinObjectsParams(names=["only_one"])  # min_length is 2

