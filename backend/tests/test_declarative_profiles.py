import ast
import json
import uuid
import os
import sys
import pytest
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from core.profile_manager import (
    load_profile,
    validate_schema,
    run_validators,
    verify_profile_against_eval_pack,
)
from agents.base_agent import BaseAgent
from agents.researcher import ResearcherAgent
from agents.synthesizer import SynthesizerAgent
from agents.endpoint_agent import EndpointAgent
from db.connections import get_operational_db, initialize_all_databases


@pytest.fixture(autouse=True)
def setup_db():
    initialize_all_databases()


def test_profile_loading_and_attributes():
    """Verify all declarative profiles load correctly with required fields."""
    profiles = ["researcher", "synthesizer", "endpoint"]
    for p_name in profiles:
        prof = load_profile(p_name)
        assert prof["name"] in ["researcher", "synthesizer", "endpoint_agent"]
        assert "version" in prof and len(prof["version"]) > 0
        assert "description" in prof
        assert "prompt_template" in prof
        assert "model_preference" in prof
        assert isinstance(prof["tools_allowed"], list) and len(prof["tools_allowed"]) > 0
        assert "_template_content" in prof and len(prof["_template_content"]) > 0


def test_profile_fail_closed_on_unauthorized_tools(tmp_path):
    """Profile with unknown tools not in tool_registry.json must fail closed."""
    bad_yaml = tmp_path / "rogue.yaml"
    bad_yaml.write_text(
        """
name: rogue
version: "1.0.0"
description: "Rogue agent"
prompt_template: "none"
model_preference: "qwen3_14b_q4"
tools_allowed:
  - unknown_weaponized_tool
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="does not exist in tool_registry.json"):
        load_profile(str(bad_yaml))


@pytest.mark.asyncio
async def test_profile_boundary_enforcement_in_execute_tool():
    """Agents cannot call tools outside their declarative profile's tools_allowed list."""
    mock_mm = MagicMock()
    mock_gov = MagicMock()
    config = {"governance": {"max_tool_calls_per_task": 20}}

    class StrictAgent(BaseAgent):
        PROFILE_NAME = "researcher"

        async def run(self, claim):
            return {"status": "ok"}

    agent = StrictAgent(mock_mm, mock_gov, config)
    assert agent.profile is not None
    assert "web_search" in agent.profile["tools_allowed"]
    assert "desktop_click" not in agent.profile["tools_allowed"]

    # Calling tool outside profile tools_allowed must be DENIED by gateway
    res = await agent.execute_tool(
        task_id="task_test_profile",
        step_id="step_test_profile",
        name="desktop_click",
        params={"x": 100, "y": 200},
    )
    assert res["status"] == "denied"
    assert "not permitted in agent profile" in res["reason"]


def test_task_steps_persist_profile_version():
    """Verify task_steps record persists the active profile_version."""
    mock_mm = MagicMock()
    mock_gov = MagicMock()
    config = {"governance": {"max_tool_calls_per_task": 20}}

    agent = ResearcherAgent(mock_mm, mock_gov, config)
    assert agent.profile_version == "1.0.0"

    task_id = f"task_pv_{uuid.uuid4().hex[:8]}"
    conn = get_operational_db()
    try:
        conn.execute(
            "INSERT INTO tasks (task_id, title, description, status, priority, workflow_type) VALUES (?, 'Test PV', 'Test PV', 'QUEUED', 1, 'RESEARCHER')",
            (task_id,),
        )
        conn.commit()
    finally:
        conn.close()

    step_id = agent.create_step(task_id, 0, "TEST_STEP", "Testing profile version stamp")
    assert step_id is not None

    conn = get_operational_db()
    try:
        row = conn.execute(
            "SELECT profile_version, model_id, prompt_hash FROM task_steps WHERE step_id = ?",
            (step_id,),
        ).fetchone()
        assert row is not None
        assert row["profile_version"] == "1.0.0"
    finally:
        conn.close()


def test_output_schema_and_validators():
    """Verify lightweight schema and python validators execute properly."""
    schema = {
        "type": "object",
        "required": ["topic", "digest"],
        "properties": {
            "topic": {"type": "string"},
            "digest": {"type": "string"},
        },
    }

    # Valid data
    valid_data = {"topic": "AI", "digest": "Weekly roundup"}
    ok, err = validate_schema(valid_data, schema)
    assert ok is True
    assert err is None

    # Missing required field
    bad_data = {"topic": "AI"}
    ok, err = validate_schema(bad_data, schema)
    assert ok is False
    assert "Missing required property: 'digest'" in err

    # Wrong type
    wrong_type_data = {"topic": 123, "digest": "Roundup"}
    ok, err = validate_schema(wrong_type_data, schema)
    assert ok is False
    assert "Property 'topic'" in err

    # Named validators
    passed, val_errs = run_validators({"sub_questions": ["Q1"]}, ["validate_research_output"])
    assert passed is True
    assert len(val_errs) == 0

    passed, val_errs = run_validators({}, ["validate_research_output"])
    assert passed is False


def test_profile_eval_pack_verification():
    """Verify profile can be tested against its eval pack before activation."""
    prof = load_profile("researcher")
    report = verify_profile_against_eval_pack(prof)
    assert report["profile_name"] == "researcher"
    assert report["profile_version"] == "1.0.0"
    assert "pass_rate" in report
    assert report["status"] in ["PASSED", "FAILED"]


def test_ast_enforcement_llm_calls_use_call_llm():
    """
    AST Security Check:
    Verifies that LLM-dependent agents (ResearcherAgent, SynthesizerAgent, EndpointAgent)
    do not call model_manager.generate_async directly in their run() methods.
    They must use self.call_llm().
    """
    agent_files = [
        Path("backend/agents/researcher.py"),
        Path("backend/agents/synthesizer.py"),
        Path("backend/agents/endpoint_agent.py"),
    ]

    for fpath in agent_files:
        assert fpath.is_file(), f"File {fpath} does not exist"
        tree = ast.parse(fpath.read_text(encoding="utf-8"))

        # Find the run method
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
                if node.name == "run":
                    for subnode in ast.walk(node):
                        if isinstance(subnode, ast.Call):
                            # Check if calling generate_async on model_manager
                            func = subnode.func
                            if isinstance(func, ast.Attribute) and func.attr == "generate_async":
                                pytest.fail(
                                    f"VIOLATION: {fpath.name}::run() calls generate_async directly instead of self.call_llm()"
                                )
