"""Comprehensive security boundary tests for auto_approve / Trust App governance enforcement."""

import pytest
from unittest.mock import AsyncMock
from core.governance import GovernanceEngine, GovernanceViolation, HITLRequired
from core.tool_gateway import ToolGateway
from core.model_manager import ModelManager
from core.mcp_manager import MCPManager
from config.loader import load_policy_rules, load_system_config, load_model_registry


@pytest.fixture
def governance():
    policy = load_policy_rules()
    config = load_system_config()
    return GovernanceEngine(policy, config)


def test_auto_approve_bypasses_hitl_for_l3_tool(governance):
    """auto_approve: True must bypass HITL gating for an otherwise-L3 tool."""
    meta = {
        "name": "dangerous_action",
        "side_effect": "act",
        "risk_level": "L3",
        "allowed_agents": ["endpoint_agent"],
        "deny_all": False,
        "taint_deny": False,
        "taint_safe": True,
        "egress": False,
        "returns_untrusted": False,
        "reads_private_data": False,
        "auto_approve": True,
    }
    # Calling check_tool_execution_safety must succeed without raising HITLRequired
    result = governance.check_tool_execution_safety(
        tool_name="dangerous_action",
        caller_agent="endpoint_agent",
        task_id="task_auto_app",
        registry_meta=meta,
    )
    assert result == meta, "auto_approve tool must return metadata directly without HITL"


def test_auto_approve_does_not_bypass_deny_all(governance):
    """deny_all=True must take precedence and reject even if auto_approve is True."""
    meta = {
        "name": "banned_tool",
        "side_effect": "act",
        "risk_level": "L0",
        "allowed_agents": ["endpoint_agent"],
        "deny_all": True,
        "taint_deny": False,
        "taint_safe": True,
        "egress": False,
        "returns_untrusted": False,
        "reads_private_data": False,
        "auto_approve": True,
    }
    with pytest.raises(GovernanceViolation, match="denied unconditionally"):
        governance.check_tool_execution_safety(
            tool_name="banned_tool",
            caller_agent="endpoint_agent",
            registry_meta=meta,
        )


def test_auto_approve_does_not_bypass_taint_deny(governance):
    """taint_deny=True under untrusted context must reject even if auto_approve is True."""
    meta = {
        "name": "taint_sensitive_tool",
        "side_effect": "act",
        "risk_level": "L0",
        "allowed_agents": ["endpoint_agent"],
        "deny_all": False,
        "taint_deny": True,
        "taint_safe": False,
        "egress": False,
        "returns_untrusted": False,
        "reads_private_data": False,
        "auto_approve": True,
    }
    with pytest.raises(GovernanceViolation, match="TAINT VIOLATION"):
        governance.check_tool_execution_safety(
            tool_name="taint_sensitive_tool",
            caller_agent="endpoint_agent",
            untrusted_present=True,
            registry_meta=meta,
        )


def test_auto_approve_does_not_bypass_emergency_stop(governance):
    """Emergency stop must immediately block execution even if auto_approve is True."""
    meta = {
        "name": "some_tool",
        "side_effect": "act",
        "risk_level": "L0",
        "allowed_agents": ["endpoint_agent"],
        "deny_all": False,
        "taint_deny": False,
        "taint_safe": True,
        "egress": False,
        "returns_untrusted": False,
        "reads_private_data": False,
        "auto_approve": True,
    }
    governance.trigger_emergency_stop()
    try:
        with pytest.raises(GovernanceViolation, match="Emergency Stop is ACTIVE"):
            governance.check_tool_execution_safety(
                tool_name="some_tool",
                caller_agent="endpoint_agent",
                registry_meta=meta,
            )
    finally:
        governance.reset_emergency_stop()


def test_auto_approve_does_not_bypass_allowed_agents(governance):
    """allowed_agents restrictions must hold even if auto_approve is True."""
    meta = {
        "name": "internal_blender_scene_info",
        "side_effect": "read",
        "risk_level": "L0",
        "allowed_agents": ["blender_agent"],  # Locked to blender_agent only
        "deny_all": False,
        "taint_deny": False,
        "taint_safe": True,
        "egress": False,
        "returns_untrusted": False,
        "reads_private_data": False,
        "auto_approve": True,
    }
    # Calling as endpoint_agent MUST be rejected
    with pytest.raises(GovernanceViolation, match="NOT authorized to execute tool"):
        governance.check_tool_execution_safety(
            tool_name="internal_blender_scene_info",
            caller_agent="endpoint_agent",
            registry_meta=meta,
        )


@pytest.mark.asyncio
async def test_gateway_get_scene_info_blocked_for_endpoint_agent_even_if_blender_trusted():
    """Verify that ToolGateway enforces allowed_agents: ['blender_agent'] on get_scene_info
    even when Blender app is trusted with auto_approve."""
    policy = load_policy_rules()
    config = load_system_config()
    registry = load_model_registry()
    gov = GovernanceEngine(policy, config)
    mm = ModelManager(config, registry)
    mcp = MCPManager()
    mcp.initialize_from_config()
    conn = mcp.get_connection("blender")
    from core.mcp_manager import MCPToolDescriptor
    conn.discovered_tools = [MCPToolDescriptor(name="get_scene_info", description="", input_schema={}, app_id="blender")]
    conn.status = "connected"
    ToolGateway._active_mcp_manager = mcp
    gw = ToolGateway(model_manager=mm, governance=gov)

    res = await gw.execute_tool(
        "mcp:blender:get_scene_info",
        {},
        task_id="task_audit",
        caller_name="endpoint_agent",
    )
    assert res["status"] == "denied"
    assert "NOT authorized" in res["reason"]
    assert "blender_agent" in res["reason"]
