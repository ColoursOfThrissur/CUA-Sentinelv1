import pytest
import os
import sys
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from core.mcp_manager import MCPManager, MCPToolDescriptor
from core.tool_gateway import ToolGateway
from agents.endpoint_agent import EndpointAgent
from core.queue import TaskClaimResult


@pytest.fixture
def mcp_manager():
    mgr = MCPManager()
    mgr.initialize_from_config()
    return mgr


def test_mcp_non_blender_app_registry_entries(mcp_manager):
    """Verify non-blender apps default allowed_agents to endpoint_agent and cua_agent."""
    fs = mcp_manager.get_connection("filesystem")
    assert fs is not None
    fs.discovered_tools = [
        MCPToolDescriptor(
            name="read_file",
            description="Read a file from disk",
            input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
            app_id="filesystem",
        ),
        MCPToolDescriptor(
            name="list_directory",
            description="List directory contents",
            input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
            app_id="filesystem",
        ),
    ]

    entries = mcp_manager.get_tool_registry_entries("filesystem")
    assert "mcp:filesystem:read_file" in entries
    assert "mcp:filesystem:list_directory" in entries

    read_entry = entries["mcp:filesystem:read_file"]
    assert read_entry["_mcp"] is True
    assert read_entry["_app_id"] == "filesystem"
    assert "endpoint_agent" in read_entry["allowed_agents"]
    assert "cua_agent" in read_entry["allowed_agents"]


@pytest.mark.asyncio
async def test_endpoint_agent_wildcard_mcp_tool_execution(mcp_manager):
    """Verify EndpointAgent executes dynamic mcp:* tools without explicit tool registration."""
    # Setup mock filesystem connection
    fs = mcp_manager.get_connection("filesystem")
    fs.status = "connected"
    fs.discovered_tools = [
        MCPToolDescriptor(
            name="list_directory",
            description="List directory contents",
            input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
            app_id="filesystem",
        )
    ]
    mcp_manager.call_tool = AsyncMock(
        return_value={"output": "file1.txt\nfile2.txt", "is_error": False}
    )

    # Initialize ToolGateway with active manager
    ToolGateway._active_mcp_manager = mcp_manager

    mock_model_mgr = MagicMock()
    mock_gov = MagicMock()
    # Mock governance to approve execution safely
    mock_gov.check_tool_execution_safety.return_value = {
        "name": "mcp:filesystem:list_directory",
        "side_effect": "read",
        "risk_level": "L1",
        "allowed_agents": ["endpoint_agent"],
        "deny_all": False,
        "taint_deny": False,
        "taint_safe": False,
        "egress": False,
        "returns_untrusted": False,
        "reads_private_data": False,
    }

    agent = EndpointAgent(
        model_manager=mock_model_mgr,
        governance=mock_gov,
        config={"governance": {"max_tool_calls_per_task": 50}},
    )
    agent._mcp_manager = mcp_manager

    # endpoint.yaml profile has 'mcp:*'
    assert "mcp:*" in agent.profile.get("tools_allowed", [])

    # Execute tool directly through execute_tool
    result = await agent.execute_tool(
        "mcp:filesystem:list_directory",
        params={"path": "C:/Users/derik/Desktop"},
        task_id="task_e2e_test",
        step_id="step_e2e_1",
    )

    assert result["status"] == "ok"
    assert result["data"]["output"] == "file1.txt\nfile2.txt"
    mcp_manager.call_tool.assert_awaited_once_with(
        "filesystem", "list_directory", {"path": "C:/Users/derik/Desktop"}
    )


@pytest.mark.asyncio
async def test_endpoint_agent_prompt_includes_mcp_tools(mcp_manager):
    """Verify prompt builder injects connected MCP tools into LLM prompt during agent.run()."""
    fs = mcp_manager.get_connection("filesystem")
    fs.status = "connected"
    fs.discovered_tools = [
        MCPToolDescriptor(
            name="search_files",
            description="Recursively search for files matching a pattern",
            input_schema={"type": "object", "properties": {"pattern": {"type": "string"}}},
            app_id="filesystem",
        )
    ]

    mock_model_mgr = MagicMock()
    mock_gov = MagicMock()

    agent = EndpointAgent(
        model_manager=mock_model_mgr,
        governance=mock_gov,
        config={"governance": {"max_tool_calls_per_task": 50}},
    )
    agent._mcp_manager = mcp_manager
    agent.create_step = MagicMock(return_value="step_123")
    agent.update_step_status = MagicMock()
    agent.save_artifact = MagicMock()
    agent.broadcast_step_trace = AsyncMock()

    captured_system_rules = []

    async def mock_call_llm(*args, **kwargs):
        rules = kwargs.get("system_rules", "")
        captured_system_rules.append(rules)
        return "I can search files for you."

    agent.call_llm = mock_call_llm

    claim = TaskClaimResult(
        task_id="task_prompt_test",
        lease_id="lease_1",
        lease_generation=1,
        workflow_type="ENDPOINT",
        priority=0,
        context_budget=4000,
        input_payload={"prompt": "Can you search for pdf files in my desktop folder?"},
    )

    await agent.run(claim)

    assert len(captured_system_rules) > 0
    sys_rules = captured_system_rules[0]
    assert "mcp:filesystem:search_files" in sys_rules
    assert "Recursively search for files matching a pattern" in sys_rules


@pytest.mark.asyncio
async def test_endpoint_agent_e2e_llm_calls_mcp_tool(mcp_manager):
    """Verify LLM response emitting call_tool for MCP tool triggers ToolGateway and mcp_manager.call_tool."""
    fs = mcp_manager.get_connection("filesystem")
    fs.status = "connected"
    fs.discovered_tools = [
        MCPToolDescriptor(
            name="read_file",
            description="Read file contents from disk",
            input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
            app_id="filesystem",
        )
    ]
    mcp_manager.call_tool = AsyncMock(
        return_value={"output": "SECRET_KEY=12345", "is_error": False}
    )
    ToolGateway._active_mcp_manager = mcp_manager

    mock_model_mgr = MagicMock()
    mock_gov = MagicMock()
    mock_gov.check_tool_execution_safety.return_value = {
        "name": "mcp:filesystem:read_file",
        "side_effect": "read",
        "risk_level": "L1",
        "allowed_agents": ["endpoint_agent"],
        "deny_all": False,
        "taint_deny": False,
        "taint_safe": False,
        "egress": False,
        "returns_untrusted": False,
        "reads_private_data": False,
    }

    agent = EndpointAgent(
        model_manager=mock_model_mgr,
        governance=mock_gov,
        config={"governance": {"max_tool_calls_per_task": 50}},
    )
    agent._mcp_manager = mcp_manager
    agent.create_step = MagicMock(return_value="step_123")
    agent.update_step_status = MagicMock()
    agent.save_artifact = MagicMock()
    agent.broadcast_step_trace = AsyncMock()

    # LLM emits JSON calling mcp:filesystem:read_file
    async def mock_call_llm(*args, **kwargs):
        return '```json\n{"action": "call_tool", "tool": "mcp:filesystem:read_file", "args": {"path": "C:/Users/derik/Desktop/notes.txt"}}\n```'

    agent.call_llm = mock_call_llm

    claim = TaskClaimResult(
        task_id="task_e2e_llm_test",
        lease_id="lease_2",
        lease_generation=1,
        workflow_type="ENDPOINT",
        priority=0,
        context_budget=4000,
        input_payload={"prompt": "Read the file notes.txt on my desktop"},
    )

    result = await agent.run(claim)

    # Tool execution should succeed
    assert "error" not in result
    assert "response" in result
    assert "mcp:filesystem:read_file" in result["response"]
    assert "SECRET_KEY=12345" in result["response"]
    mcp_manager.call_tool.assert_awaited_once_with(
        "filesystem", "read_file", {"path": "C:/Users/derik/Desktop/notes.txt"}
    )


