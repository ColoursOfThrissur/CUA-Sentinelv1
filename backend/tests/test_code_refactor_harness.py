import os
import sys
import json
import pytest
from unittest.mock import MagicMock, AsyncMock

# Ensure backend root is on sys.path
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from agents.code_refactor_agent import CodeRefactorAgent
from core.governance import GovernanceEngine
from core.queue import TaskClaimResult
from core.code_diff_engine import CodeDiffEngine
from core.path_security import path_security
from db.connections import initialize_all_databases, get_operational_db


def create_test_task(task_id: str, title: str = "Refactor Test"):
    conn = get_operational_db()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO tasks (task_id, workflow_type, title, status) VALUES (?, 'coding', ?, 'RUNNING')",
            (task_id, title),
        )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture(autouse=True)
def setup_databases_and_paths(tmp_path, monkeypatch):
    """Ensure databases and allowed workspace paths are initialized for tests."""
    initialize_all_databases()
    # Configure path security to allow writes in tmp_path
    monkeypatch.setenv("SENTINEL_WORKSPACE_ROOT", str(tmp_path))
    path_security._cached_drives = [str(tmp_path).lower()]
    CodeDiffEngine.clear_session_reads()
    return tmp_path



@pytest.mark.asyncio
async def test_code_refactor_harness_end_to_end_surgical_edit(tmp_path):
    """
    Track 1 Harness: End-to-end execution of CodeRefactorAgent.run()
    using surgical SEARCH/REPLACE blocks.
    """
    proj_dir = tmp_path / "sample_project"
    proj_dir.mkdir()
    
    calc_py = proj_dir / "calculator.py"
    initial_code = (
        "def compute_total(price, tax_rate):\n"
        "    # Missing calculation logic\n"
        "    return 0\n"
        "\n"
        "def helper():\n"
        "    return 'leave this untouched'\n"
    )
    calc_py.write_text(initial_code, encoding="utf-8")

    # Mock ModelManager
    model_mgr = MagicMock()
    
    # 1st call: Planning prompt -> return JSON file_plan targeting calculator.py
    plan_json = json.dumps({
        "files": [
            {"path": "calculator.py", "action": "modify", "purpose": "Fix compute_total calculation"}
        ]
    })
    
    # 2nd call: Surgical edit prompt -> return SEARCH/REPLACE block
    surgical_diff = (
        "Here is the surgical fix:\n"
        "<<<<<<< SEARCH\n"
        "def compute_total(price, tax_rate):\n"
        "    # Missing calculation logic\n"
        "    return 0\n"
        "=======\n"
        "def compute_total(price, tax_rate):\n"
        "    return price + (price * tax_rate)\n"
        ">>>>>>> REPLACE\n"
    )
    
    model_mgr.generate_async = AsyncMock(side_effect=[plan_json, surgical_diff])
    model_mgr.get_model_for_workflow = MagicMock(return_value="qwen3_14b_q4")

    gov = MagicMock()
    agent = CodeRefactorAgent(model_mgr, gov, {})

    create_test_task("task_refactor_harness_01")
    claim = TaskClaimResult(
        task_id="task_refactor_harness_01",
        lease_id="lease_01",
        lease_generation=1,
        workflow_type="coding",
        priority=1,
        context_budget=4096,
        input_payload={
            "project_path": str(proj_dir),
            "goal_instruction": "Fix compute_total to calculate price with tax",
            "target_file": "calculator.py",
        },
    )

    result = await agent.run(claim)

    assert "error" not in result, f"Agent run failed: {result.get('error')}"
    assert result.get("task_id") == "task_refactor_harness_01"
    assert "calculator.py" in result.get("files_written", [])
    assert result.get("backup_created") is True
    assert result.get("post_health_score") is not None

    # Verify calculator.py on disk
    updated_code = calc_py.read_text(encoding="utf-8")
    assert "return price + (price * tax_rate)" in updated_code
    # Crucial invariant: other functions must remain untouched
    assert "def helper():\n    return 'leave this untouched'" in updated_code

    # Verify backup snapshot was created and 1-click rollback works
    from core.project_backup import project_backup_manager
    snapshot_path = os.path.join(project_backup_manager.backup_root, "snapshot_task_refactor_harness_01")
    assert os.path.exists(snapshot_path)
    
    # Test 1-click rollback
    restored = project_backup_manager.restore_snapshot(str(proj_dir), "task_refactor_harness_01")
    assert restored is True
    assert calc_py.read_text(encoding="utf-8") == initial_code


@pytest.mark.asyncio
async def test_code_refactor_harness_zero_file_format_retry(tmp_path):
    """
    Track 1 Harness: When LLM outputs conversational noise on attempt 1,
    agent must detect zero files written, retry with format enforcement,
    and succeed on attempt 2.
    """
    proj_dir = tmp_path / "retry_project"
    proj_dir.mkdir()
    
    module_py = proj_dir / "service.py"
    initial_code = "def get_status():\n    return 'offline'\n"
    module_py.write_text(initial_code, encoding="utf-8")

    model_mgr = MagicMock()
    
    plan_json = json.dumps({
        "files": [
            {"path": "service.py", "action": "modify", "purpose": "Set status to online"}
        ]
    })
    
    # Attempt 1 returns conversational text with no code fence or search/replace
    attempt_1_noise = "I think you should change offline to online in service.py."
    # Attempt 2 returns valid search/replace block
    attempt_2_valid = (
        "<<<<<<< SEARCH\n"
        "def get_status():\n"
        "    return 'offline'\n"
        "=======\n"
        "def get_status():\n"
        "    return 'online'\n"
        ">>>>>>> REPLACE\n"
    )

    model_mgr.generate_async = AsyncMock(side_effect=[plan_json, attempt_1_noise, attempt_2_valid])
    model_mgr.get_model_for_workflow = MagicMock(return_value="qwen3_14b_q4")

    gov = MagicMock()
    agent = CodeRefactorAgent(model_mgr, gov, {})

    create_test_task("task_refactor_harness_retry")
    claim = TaskClaimResult(
        task_id="task_refactor_harness_retry",
        lease_id="lease_retry",
        lease_generation=1,
        workflow_type="coding",
        priority=1,
        context_budget=4096,
        input_payload={
            "project_path": str(proj_dir),
            "goal_instruction": "Set status to online",
            "target_file": "service.py",
        },
    )

    result = await agent.run(claim)

    assert "error" not in result
    assert "service.py" in result.get("files_written", [])
    assert module_py.read_text(encoding="utf-8") == "def get_status():\n    return 'online'\n"
    # Ensure model was called 3 times (1 plan + 2 file attempts)
    assert model_mgr.generate_async.call_count == 3


@pytest.mark.asyncio
async def test_code_refactor_harness_syntax_error_recovery(tmp_path):
    """
    Track 1 Harness: When LLM outputs invalid Python syntax,
    VerificationGate rejects the write, forces a self-healing retry,
    and successfully commits the corrected code on attempt 2.
    """
    proj_dir = tmp_path / "syntax_project"
    proj_dir.mkdir()
    
    main_py = proj_dir / "app.py"
    initial_code = "def run():\n    return 1\n"
    main_py.write_text(initial_code, encoding="utf-8")

    model_mgr = MagicMock()
    
    plan_json = json.dumps({
        "files": [
            {"path": "app.py", "action": "modify", "purpose": "Update return value"}
        ]
    })
    
    # Attempt 1: Malformed python code block that triggers AST SyntaxError
    attempt_1_bad_syntax = (
        "```python\n"
        "# filepath: app.py\n"
        "def run():\n"
        "    return )((invalid syntax\n"
        "```"
    )
    
    # Attempt 2: Clean working code
    attempt_2_clean = (
        "```python\n"
        "# filepath: app.py\n"
        "def run():\n"
        "    return 42\n"
        "```"
    )

    model_mgr.generate_async = AsyncMock(side_effect=[plan_json, attempt_1_bad_syntax, attempt_2_clean])
    model_mgr.get_model_for_workflow = MagicMock(return_value="qwen3_14b_q4")

    gov = MagicMock()
    agent = CodeRefactorAgent(model_mgr, gov, {})

    create_test_task("task_refactor_harness_syntax")
    claim = TaskClaimResult(
        task_id="task_refactor_harness_syntax",
        lease_id="lease_syntax",
        lease_generation=1,
        workflow_type="coding",
        priority=1,
        context_budget=4096,
        input_payload={
            "project_path": str(proj_dir),
            "goal_instruction": "Update return value to 42",
            "target_file": "app.py",
        },
    )

    result = await agent.run(claim)

    assert "error" not in result
    assert "app.py" in result.get("files_written", [])
    assert main_py.read_text(encoding="utf-8").strip() == "def run():\n    return 42"
    # Ensure retry occurred
    assert model_mgr.generate_async.call_count == 3


def test_code_refactor_wire_up_pass_auto_repairs(tmp_path):
    """
    Track 1 Harness: Verifies _run_wireup_pass automatically repairs
    package.json missing type: module and wires routes into main.py.
    """
    proj_dir = tmp_path / "wire_project"
    proj_dir.mkdir()
    
    backend_dir = proj_dir / "backend"
    backend_dir.mkdir()
    
    main_py = backend_dir / "main.py"
    main_py.write_text(
        "from fastapi import FastAPI\n"
        "app = FastAPI()\n"
        "\n"
        "if __name__ == '__main__':\n"
        "    import uvicorn\n"
        "    uvicorn.run(app, host='0.0.0.0', port=8000)\n",
        encoding="utf-8"
    )

    pkg_json = proj_dir / "package.json"
    pkg_json.write_text(json.dumps({"name": "test-app", "version": "1.0.0"}, indent=2), encoding="utf-8")

    agent = CodeRefactorAgent(MagicMock(), MagicMock(), {})
    wired = agent._run_wireup_pass(str(proj_dir), [], ["backend/main.py", "package.json"])

    # Check package.json was repaired with type: module
    with open(pkg_json, "r", encoding="utf-8") as f:
        pkg_data = json.load(f)
    assert pkg_data.get("type") == "module"

    # Check uvicorn string import repair
    main_content = main_py.read_text(encoding="utf-8")
    assert 'uvicorn.run("backend.main:app"' in main_content
    assert "sys.path.insert(0" in main_content


@pytest.mark.asyncio
async def test_code_refactor_harness_rejects_ambiguous_search_block_and_heals(tmp_path):
    """
    Track 1 Harness: SEARCH blocks matching 2+ locations must be strictly
    rejected to prevent silent corruption, keeping disk untouched until
    unique surrounding context is provided.
    """
    proj_dir = tmp_path / "ambig_project"
    proj_dir.mkdir()

    target_py = proj_dir / "handlers.py"
    initial_content = (
        "def handle_get():\n"
        "    return 42\n"
        "\n"
        "def handle_post():\n"
        "    return 42\n"
    )
    target_py.write_text(initial_content, encoding="utf-8")

    model_mgr = MagicMock()
    plan_json = json.dumps({
        "files": [
            {"path": "handlers.py", "action": "modify", "purpose": "Update handle_get only"}
        ]
    })

    # Attempt 1: Ambiguous block matching both functions — must be REJECTED
    attempt_1_ambig = (
        "<<<<<<< SEARCH\n"
        "    return 42\n"
        "=======\n"
        "    return 100\n"
        ">>>>>>> REPLACE\n"
    )

    # Attempt 2: Unique block with surrounding function signature context
    attempt_2_unique = (
        "<<<<<<< SEARCH\n"
        "def handle_get():\n"
        "    return 42\n"
        "=======\n"
        "def handle_get():\n"
        "    return 100\n"
        ">>>>>>> REPLACE\n"
    )

    model_mgr.generate_async = AsyncMock(side_effect=[plan_json, attempt_1_ambig, attempt_2_unique])
    model_mgr.get_model_for_workflow = MagicMock(return_value="qwen3_14b_q4")

    gov = MagicMock()
    agent = CodeRefactorAgent(model_mgr, gov, {})

    create_test_task("task_refactor_harness_ambig")
    claim = TaskClaimResult(
        task_id="task_refactor_harness_ambig",
        lease_id="lease_ambig",
        lease_generation=1,
        workflow_type="coding",
        priority=1,
        context_budget=4096,
        input_payload={
            "project_path": str(proj_dir),
            "goal_instruction": "Update handle_get to return 100",
            "target_file": "handlers.py",
        },
    )

    result = await agent.run(claim)

    assert "error" not in result
    assert "handlers.py" in result.get("files_written", [])

    final_content = target_py.read_text(encoding="utf-8")
    # Verify handle_get was updated
    assert "def handle_get():\n    return 100" in final_content
    # Crucial: handle_post must retain return 42 (no silent double replacement or corruption!)
    assert "def handle_post():\n    return 42" in final_content
    assert model_mgr.generate_async.call_count == 3


@pytest.mark.asyncio
async def test_code_refactor_harness_attempt_ceiling_exhaustion(tmp_path):
    """
    Track 1 Harness: Verifies retry ceiling terminates cleanly at 3 attempts
    when model repeatedly produces invalid output, marking the file step FAILED
    without entering an unbounded loop.
    """
    proj_dir = tmp_path / "exhaust_project"
    proj_dir.mkdir()

    calc_py = proj_dir / "calc.py"
    initial_code = "def calc():\n    return 1\n"
    calc_py.write_text(initial_code, encoding="utf-8")

    model_mgr = MagicMock()
    plan_json = json.dumps({
        "files": [
            {"path": "calc.py", "action": "modify", "purpose": "Cannot be completed"}
        ]
    })

    # Model returns noise on attempt 1, 2, and 3
    noise = "I am unable to output search replace blocks."
    model_mgr.generate_async = AsyncMock(side_effect=[plan_json, noise, noise, noise])
    model_mgr.get_model_for_workflow = MagicMock(return_value="qwen3_14b_q4")

    gov = MagicMock()
    agent = CodeRefactorAgent(model_mgr, gov, {})

    create_test_task("task_refactor_harness_exhaust")
    claim = TaskClaimResult(
        task_id="task_refactor_harness_exhaust",
        lease_id="lease_exhaust",
        lease_generation=1,
        workflow_type="coding",
        priority=1,
        context_budget=4096,
        input_payload={
            "project_path": str(proj_dir),
            "goal_instruction": "Trigger attempt exhaustion",
            "target_file": "calc.py",
        },
    )

    result = await agent.run(claim)

    # Agent finishes gracefully
    assert "error" not in result
    # Zero files written
    assert result.get("files_written", []) == []
    # Original file on disk remains pristine
    assert calc_py.read_text(encoding="utf-8") == initial_code
    # Exactly 4 calls: 1 plan + exactly 3 file attempts (strictly capped, no unbounded recursion)
    assert model_mgr.generate_async.call_count == 4

