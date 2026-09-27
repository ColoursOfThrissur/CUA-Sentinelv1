import pytest
import os
import sys
import json
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from core.mcp_manager import MCPManager, MCPToolDescriptor
from core.tool_gateway import ToolGateway
from agents.endpoint_agent import EndpointAgent
from core.queue import TaskClaimResult
from db.connections import get_audit_db


@pytest.fixture
def mcp_manager_with_tools():
    mgr = MCPManager()
    mgr.initialize_from_config()
    fs = mgr.get_connection("filesystem")
    fs.status = "connected"
    fs.discovered_tools = [
        MCPToolDescriptor(
            name="search_files",
            description="Recursively search directory trees for files matching a pattern.",
            input_schema={"type": "object", "properties": {"pattern": {"type": "string"}}},
            app_id="filesystem",
        ),
        MCPToolDescriptor(
            name="read_file",
            description="Read file contents from the local disk filesystem given a path.",
            input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
            app_id="filesystem",
        ),
    ]
    return mgr


@pytest.mark.asyncio
async def test_search_tools_via_gateway_execution(mcp_manager_with_tools):
    """Verify search_tools executes through ToolGateway and returns schemas."""
    ToolGateway._active_mcp_manager = mcp_manager_with_tools
    gateway = ToolGateway()

    result = await gateway.execute_tool(
        name="search_tools",
        params={"query": "search for files matching pattern", "limit": 2},
        task_id="task_search_gw_1",
        step_id="step_1",
        caller_name="endpoint_agent",
    )

    assert result["status"] == "ok"
    data = result["data"]
    assert data["found"] > 0
    assert "mcp:filesystem:search_files" in data["tools"]
    assert "<connected_tools>" in data["formatted_schemas"]


@pytest.mark.asyncio
async def test_search_tools_audit_logging_including_zero_match(mcp_manager_with_tools):
    """Verify both successful and zero-match searches are audited in audit.sqlite."""
    ToolGateway._active_mcp_manager = mcp_manager_with_tools
    gateway = ToolGateway()

    # 1. Search with matches
    await gateway.execute_tool(
        name="search_tools",
        params={"query": "read file contents", "limit": 1},
        task_id="task_audit_match",
        step_id="step_match",
        caller_name="endpoint_agent",
    )

    # 2. Search with zero matches
    await gateway.execute_tool(
        name="search_tools",
        params={"query": "completely unmatchable nonsense 999 xyz", "limit": 1},
        task_id="task_audit_zero",
        step_id="step_zero",
        caller_name="endpoint_agent",
    )

    # Query audit.sqlite for both task records
    conn = get_audit_db()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT task_id, decision_summary, decision_factors FROM audit_logs WHERE task_id IN (?, ?) ORDER BY log_sequence ASC",
            ("task_audit_match", "task_audit_zero"),
        )
        rows = cur.fetchall()
        assert len(rows) >= 2

        # Check matched row
        matched_row = [r for r in rows if r["task_id"] == "task_audit_match"][0]
        assert "ALLOWED" in matched_row["decision_summary"]

        # Check zero-match row
        zero_row = [r for r in rows if r["task_id"] == "task_audit_zero"][0]
        factors = json.loads(zero_row["decision_factors"]) if zero_row["decision_factors"] else {}
        assert "ALLOWED" in zero_row["decision_summary"]
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_endpoint_agent_search_tools_loop_cap(mcp_manager_with_tools):
    """Verify EndpointAgent caps search_tools to max 2 calls per task."""
    ToolGateway._active_mcp_manager = mcp_manager_with_tools

    mock_model_mgr = MagicMock()
    mock_gov = MagicMock()
    mock_gov.check_tool_execution_safety.return_value = {
        "name": "search_tools",
        "side_effect": "read",
        "risk_level": "L0",
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
    agent._mcp_manager = mcp_manager_with_tools
    agent.create_step = MagicMock(return_value="step_123")
    agent.update_step_status = MagicMock()
    agent.save_artifact = MagicMock()
    agent.broadcast_step_trace = AsyncMock()

    # Pre-populate search calls to 2 (simulating 2 calls already made in this task)
    task_id = "task_loop_test"
    agent._search_tool_call_counts[task_id] = 2

    # LLM emits a 3rd search_tools call
    async def mock_call_llm(*args, **kwargs):
        return '```json\n{"action": "call_tool", "tool": "search_tools", "args": {"query": "more files"}}\n```'

    agent.call_llm = mock_call_llm

    claim = TaskClaimResult(
        task_id=task_id,
        lease_id="lease_loop",
        lease_generation=1,
        workflow_type="ENDPOINT",
        priority=0,
        context_budget=4000,
        input_payload={"prompt": "Find something else"},
    )

    result = await agent.run(claim)

    # 3rd call should have been blocked by the ceiling
    assert "Search call limit reached" in result["response"]
    assert agent._search_tool_call_counts[task_id] == 2


@pytest.mark.asyncio
async def test_tool_discovery_mode_toggle(mcp_manager_with_tools):
    """Verify TOOL_DISCOVERY_MODE=search exposes search_tools and hides eager app dump."""
    mock_model_mgr = MagicMock()
    mock_gov = MagicMock()

    agent = EndpointAgent(
        model_manager=mock_model_mgr,
        governance=mock_gov,
        config={"governance": {"max_tool_calls_per_task": 50}},
    )
    agent._mcp_manager = mcp_manager_with_tools
    agent.create_step = MagicMock(return_value="step_123")
    agent.update_step_status = MagicMock()
    agent.save_artifact = MagicMock()
    agent.broadcast_step_trace = AsyncMock()

    captured_rules = []

    async def mock_call_llm(*args, **kwargs):
        rules = kwargs.get("system_rules", "")
        captured_rules.append(rules)
        return "Acknowledged."

    agent.call_llm = mock_call_llm

    claim = TaskClaimResult(
        task_id="task_mode_test",
        lease_id="lease_mode",
        lease_generation=1,
        workflow_type="ENDPOINT",
        priority=0,
        context_budget=4000,
        input_payload={"prompt": "search my files"},
    )

    # In search mode
    with patch.dict(os.environ, {"TOOL_DISCOVERY_MODE": "search"}):
        await agent.run(claim)
        assert len(captured_rules) > 0
        rules = captured_rules[-1]
        assert "search_tools" in rules
        # In pure search mode, filesystem tools are not dumped up-front
        assert "mcp:filesystem:read_file" not in rules

    # In hybrid mode (default)
    with patch.dict(os.environ, {"TOOL_DISCOVERY_MODE": "hybrid"}):
        await agent.run(claim)
        rules = captured_rules[-1]
        assert "search_tools" in rules
        # In hybrid mode, keyword match triggers eager injection
        assert "mcp:filesystem:search_files" in rules
