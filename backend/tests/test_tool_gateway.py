import os
import sys
import asyncio
import json
import pytest
from unittest.mock import MagicMock

# Ensure backend root is on sys.path
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from config.loader import load_tool_registry, validate_tool_registry, load_policy_rules, load_system_config
from core.governance import GovernanceEngine
from agents.base_agent import BaseAgent



class ConcreteTestAgent(BaseAgent):
    """Test concrete implementation of BaseAgent."""
    agent_name = "test_agent"

    async def run(self, claim) -> dict:
        return {"status": "ok"}


@pytest.fixture
def test_agent():
    gov = GovernanceEngine(load_policy_rules(), load_system_config())
    agent = ConcreteTestAgent(MagicMock(), gov, {"governance": {"max_tool_calls_per_task": 3}})
    agent.agent_name = "endpoint_agent"
    return agent


def test_registry_validation_startup():
    """Fail closed: tool registry must validate on startup."""
    reg = load_tool_registry()
    assert validate_tool_registry(reg) is True

    # Bad registry missing field fails closed
    bad_reg = {"tools": {"bad_tool": {"name": "bad_tool", "risk_level": "INVALID"}}}
    with pytest.raises(ValueError):
        validate_tool_registry(bad_reg)


@pytest.mark.asyncio
async def test_gateway_denies_unknown_tool(test_agent):
    """Gateway returns structured denial for unlisted tool without raising."""
    res = await test_agent.execute_tool("unknown_dangerous_tool", {})
    assert res["status"] == "denied"
    assert "Unknown tool" in res["reason"]
    assert res["untrusted"] is False
    assert res["span_id"].startswith("span_")


@pytest.mark.asyncio
async def test_gateway_denies_unauthorized_agent(test_agent):
    """Gateway denies tool execution if caller agent is not in allowed_agents."""
    test_agent.agent_name = "unauthorized_rogue_agent"
    res = await test_agent.execute_tool("fetch_ticker_quote", {"symbol": "NVDA"})
    assert res["status"] == "denied"
    assert "NOT authorized" in res["reason"]


@pytest.mark.asyncio
async def test_gateway_taint_blocks_act_and_write(test_agent):
    """
    Taint tracking (Change 1 / Step 3):
    When an untrusted tool returns data, agent is marked tainted,
    and subsequent act or write tools are blocked under S1.
    """
    task_id = "task_taint_test"
    test_agent.gateway._taint_state[task_id] = False
    assert test_agent.is_tainted(task_id) is False

    # Execute a tool that returns untrusted data (e.g., mock fetch_ticker_quote)
    mock_quote = {"symbol": "AAPL", "price": 150.0}
    res_quote = await test_agent.execute_tool(
        "fetch_ticker_quote",
        {"symbol": "AAPL"},
        task_id=task_id,
        tool_instance=lambda symbol: mock_quote,
    )
    assert res_quote["status"] == "ok"
    assert res_quote["untrusted"] is True
    assert test_agent.is_tainted(task_id) is True

    # Now attempt an 'act' tool (e.g. desktop_click)
    test_agent.agent_name = "cua_agent"
    res_act = await test_agent.execute_tool(
        "desktop_click",
        {"x": 100, "y": 200},
        task_id=task_id,
        tool_instance=lambda x, y: {"clicked": True},
    )
    assert res_act["status"] == "denied"
    assert "TAINT GATE (S1)" in res_act["reason"] or "TAINT VIOLATION" in res_act["reason"]


@pytest.mark.asyncio
async def test_gateway_emergency_stop_denial(test_agent):
    """Gateway evaluates Emergency Stop at call time from DB."""
    test_agent.governance.trigger_emergency_stop()
    try:
        res = await test_agent.execute_tool(
            "fetch_ticker_quote",
            {"symbol": "NVDA"},
            tool_instance=lambda symbol: {},
        )
        assert res["status"] == "denied"
        assert "Emergency Stop is ACTIVE" in res["reason"]
    finally:
        test_agent.governance.reset_emergency_stop()


@pytest.mark.asyncio
async def test_gateway_safe_mode_denial(test_agent):
    """Safe mode blocks act/write tools through the gateway at call time."""
    test_agent.agent_name = "code_refactor_agent"
    test_agent.governance.enter_safe_mode("Test safe mode")
    try:
        res = await test_agent.execute_tool(
            "file_write",
            {"relative_path": "test.txt", "content": "hello"},
            task_id="task_safe_mode_test",
            tool_instance=lambda relative_path, content: None,
        )
        assert res["status"] == "denied"
        assert "Safe Mode" in res["reason"]
    finally:
        test_agent.governance.exit_safe_mode()


@pytest.mark.asyncio
async def test_gateway_per_task_budget_cap(test_agent):
    """Gateway enforces maximum tool call limit per task."""
    test_agent.agent_name = "endpoint_agent"
    task_id = "task_budget_test"

    for i in range(3):
        res = await test_agent.execute_tool(
            "fetch_ticker_quote",
            {"symbol": "NVDA"},
            task_id=task_id,
            tool_instance=lambda symbol: {"price": 100},
        )
        assert res["status"] == "ok"

    # 4th call exceeds max_tool_calls_per_task = 3
    res_overflow = await test_agent.execute_tool(
        "fetch_ticker_quote",
        {"symbol": "NVDA"},
        task_id=task_id,
        tool_instance=lambda symbol: {"price": 100},
    )
    assert res_overflow["status"] == "denied"
    assert "Budget exceeded" in res_overflow["reason"]


@pytest.mark.asyncio
async def test_gateway_masked_audit_and_version_stamps(test_agent):
    """Gateway records audit span with masked inputs and version stamps."""
    from db.connections import get_audit_db

    task_id = "task_audit_mask_test"
    sensitive_params = {
        "email_user": "secret_user@example.com",
        "search_term": "invoice 4532-1122-3344-5566",
        "app_password": "supersecretpassword123",
    }

    res = await test_agent.execute_tool(
        "search_emails",
        sensitive_params,
        task_id=task_id,
        tool_instance=lambda **kwargs: [{"snippet": "card 1234-5678-9012-3456 payment"}],
    )
    assert res["status"] == "ok"

    conn = get_audit_db()
    try:
        row = conn.execute(
            "SELECT * FROM audit_logs WHERE task_id = ? ORDER BY created_at DESC LIMIT 1",
            (task_id,),
        ).fetchone()
        assert row is not None
        assert row["tool_name"] == "search_emails"
        factors = json.loads(row["decision_factors"])
        assert factors["gateway_version"] == "1.0.0"
        assert len(factors["config_version"]) == 16
        # Check input masking: email masked, password masked, card number masked
        assert factors["input"]["app_password"] == "***MASKED***"
        assert "secret_user@example.com" not in str(factors["input"])
        assert "s***r@example.com" in str(factors["input"]) or "***" in str(factors["input"]["email_user"])
        assert "4532-1122-3344-5566" not in str(factors["input"])
    finally:
        conn.close()
