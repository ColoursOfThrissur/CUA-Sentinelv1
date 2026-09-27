"""Unit tests for the extracted ToolGateway service."""

import pytest
from unittest.mock import MagicMock

from core.tool_gateway import ToolGateway
from core.governance import GovernanceEngine
from config.loader import load_policy_rules, load_system_config


@pytest.fixture
def governance_engine():
    policy = load_policy_rules()
    config = load_system_config()
    return GovernanceEngine(policy, config)


@pytest.fixture
def gateway(governance_engine):
    config = {"governance": {"max_tool_calls_per_task": 3}}
    return ToolGateway(governance=governance_engine, config=config)


def test_tool_gateway_init(gateway):
    """ToolGateway initializes with expected state and zero taint."""
    assert gateway.is_tainted("task_1") is False
    assert gateway.get_taint_origins("task_1") == "untrusted tool return data"
    assert gateway.max_tool_calls_per_task == 3


def test_tool_gateway_taint_lifecycle(gateway):
    """ToolGateway tracks taint by task ID and origin tool."""
    task_id = "task_taint_extracted"
    assert gateway.is_tainted(task_id) is False

    gateway.set_tainted(task_id, origin_tool="web_search")
    assert gateway.is_tainted(task_id) is True
    assert "web_search" in gateway.get_taint_origins(task_id)

    # Different task is not tainted
    assert gateway.is_tainted("other_task") is False


@pytest.mark.asyncio
async def test_tool_gateway_denies_unknown_tool(gateway):
    """Gateway returns structured denial when tool is unknown."""
    res = await gateway.execute_tool(
        "non_existent_tool_123",
        params={},
        task_id="t1",
        caller_name="endpoint_agent",
    )
    assert res["status"] == "denied"
    assert "Unknown tool" in res["reason"]
    assert res["untrusted"] is False
    assert res["span_id"].startswith("span_")


@pytest.mark.asyncio
async def test_tool_gateway_budget_enforcement(gateway):
    """Gateway caps execution at max_tool_calls_per_task."""
    task_id = "budget_task_extracted"

    # Register mock tool for test
    ToolGateway.register_tool_handler("test_echo", lambda val: {"echo": val})

    for i in range(3):
        res = await gateway.execute_tool(
            "fetch_ticker_quote",
            {"symbol": "NVDA"},
            task_id=task_id,
            caller_name="endpoint_agent",
            tool_instance=lambda symbol: {"price": 100},
        )
        assert res["status"] == "ok"

    # 4th call exceeds budget of 3
    res_exceeded = await gateway.execute_tool(
        "fetch_ticker_quote",
        {"symbol": "NVDA"},
        task_id=task_id,
        caller_name="endpoint_agent",
        tool_instance=lambda symbol: {"price": 100},
    )
    assert res_exceeded["status"] == "denied"
    assert "Budget exceeded" in res_exceeded["reason"]


@pytest.mark.asyncio
async def test_tool_gateway_profile_boundary(gateway):
    """Gateway checks profile tools_allowed restriction."""
    restricted_profile = {
        "name": "restricted_agent",
        "tools_allowed": ["search_emails"],
    }
    # fetch_ticker_quote is not in allowed tools
    res = await gateway.execute_tool(
        "fetch_ticker_quote",
        {"symbol": "AAPL"},
        task_id="profile_task",
        caller_name="restricted_agent",
        profile=restricted_profile,
        tool_instance=lambda symbol: {"price": 150},
    )
    assert res["status"] == "denied"
    assert "PROFILE BOUNDARY DENIAL" in res["reason"] or "not permitted in agent profile" in res["reason"]
