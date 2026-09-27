import pytest
import os
import sys
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from core.mcp_manager import MCPManager, MCPToolDescriptor, MCPAppConnection
from agents.base_agent import BaseAgent


@pytest.fixture
def mcp_manager():
    mgr = MCPManager()
    mgr.initialize_from_config()
    return mgr


def test_mcp_manager_initialize_from_config(mcp_manager):
    apps = mcp_manager.list_connections()
    assert len(apps) > 0
    app_ids = [a["app_id"] for a in apps]
    assert "blender" in app_ids
    assert "filesystem" in app_ids
    
    blender = mcp_manager.get_connection("blender")
    assert blender is not None
    assert blender.display_name == "Blender 3D"
    assert blender.transport == "stdio"
    assert blender.security["default_risk_level"] in ("L0", "L1", "L2", "L3")


def test_mcp_tool_registry_entries(mcp_manager):
    blender = mcp_manager.get_connection("blender")
    blender.discovered_tools = [
        MCPToolDescriptor(
            name="execute_blender_code",
            description="Run Python in Blender",
            input_schema={"type": "object", "properties": {"code": {"type": "string"}}},
            app_id="blender",
        )
    ]
    
    entries = mcp_manager.get_tool_registry_entries("blender")
    assert "mcp:blender:execute_blender_code" in entries
    entry = entries["mcp:blender:execute_blender_code"]
    assert entry["_mcp"] is True
    assert entry["_app_id"] == "blender"
    assert entry["side_effect"] == "act"
    assert entry["risk_level"] == "L3"
    assert entry["allowed_agents"] == []
    assert entry["deny_all"] is True


@pytest.mark.asyncio
async def test_base_agent_executes_mcp_tool_via_gateway(mcp_manager):
    from agents.endpoint_agent import EndpointAgent
    mock_model_mgr = MagicMock()
    mock_gov = MagicMock()
    mock_gov.check_tool_execution_safety.return_value = True
    
    agent = EndpointAgent(
        model_manager=mock_model_mgr,
        governance=mock_gov,
        config={"governance": {"max_tool_calls_per_task": 50}},
    )
    agent._mcp_manager = mcp_manager
    # Explicitly permit tool in agent profile for test
    if agent.profile and "tools_allowed" in agent.profile:
        agent.profile["tools_allowed"].append("mcp:blender:create_cube")
    
    # Add dummy tool to blender
    blender = mcp_manager.get_connection("blender")
    blender.status = "connected"
    blender.discovered_tools = [
        MCPToolDescriptor(
            name="create_cube",
            description="Create a 3D cube",
            input_schema={"type": "object", "properties": {"size": {"type": "number"}}},
            app_id="blender",
        )
    ]
    
    # Mock call_tool on mcp_manager
    mcp_manager.call_tool = AsyncMock(return_value={"output": "Cube created at (0,0,0)", "is_error": False})
    
    result = await agent.execute_tool(
        "mcp:blender:create_cube",
        params={"size": 2.0},
        task_id="task_mcp_test",
        step_id="step_1",
    )
    
    assert result["status"] == "ok"
    assert result["data"]["output"] == "Cube created at (0,0,0)"
    mcp_manager.call_tool.assert_awaited_once_with("blender", "create_cube", {"size": 2.0})


@pytest.mark.asyncio
async def test_mcp_apps_api_endpoints():
    from fastapi.testclient import TestClient
    from api.server import create_app
    
    app = create_app(None)
    client = TestClient(app)
    
    # Test GET /api/apps (bypass auth for test or pass sentinel token)
    response = client.get("/api/apps", headers={"x-sentinel-token": os.environ.get("SENTINEL_API_TOKEN", "sentinel-local-dev-token")})
    assert response.status_code == 200
    data = response.json()
    assert "apps" in data
    assert any(a["app_id"] == "blender" for a in data["apps"])


def test_governance_rejects_unauthorized_agent_and_all_wildcards():
    from core.governance import GovernanceEngine, GovernanceViolation
    from config.loader import load_policy_rules, load_system_config

    policy = load_policy_rules()
    config = load_system_config()
    gov = GovernanceEngine(policy, config)

    mcp_tool_meta = {
        "name": "mcp:blender:execute_blender_code",
        "side_effect": "act",
        "risk_level": "L2",
        "allowed_agents": ["__all__"],
        "deny_all": False,
        "taint_deny": False,
        "taint_safe": False,
        "egress": False,
        "returns_untrusted": False,
        "reads_private_data": False,
        "_mcp": True,
    }

    # __all__ does NOT permit arbitrary callers: must fail closed
    with pytest.raises(GovernanceViolation, match="NOT authorized to execute tool"):
        gov.check_tool_execution_safety(
            tool_name="mcp:blender:execute_blender_code",
            caller_agent="endpoint_agent",
            untrusted_present=False,
            registry_meta=mcp_tool_meta,
        )

    # When caller_agent is explicitly in allowed_agents, it succeeds
    mcp_tool_meta["allowed_agents"] = ["endpoint_agent"]
    meta = gov.check_tool_execution_safety(
        tool_name="mcp:blender:execute_blender_code",
        caller_agent="endpoint_agent",
        untrusted_present=False,
        registry_meta=mcp_tool_meta,
    )
    assert meta["risk_level"] == "L2"


@pytest.mark.asyncio
async def test_brave_search_missing_key_clean_error(mcp_manager):
    """Connecting to Brave Search without BRAVE_API_KEY must raise clean ValueError without AnyIO crash."""
    with pytest.raises(ValueError, match="BRAVE_API_KEY"):
        await mcp_manager.connect_app("brave_search")
    conn = mcp_manager.get_connection("brave_search")
    assert conn.status == "error"
    assert "BRAVE_API_KEY" in conn.error_message


