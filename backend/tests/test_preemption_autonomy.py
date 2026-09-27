import asyncio
import os
import sys
import uuid
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config.loader import load_system_config
from core.queue import TaskQueue
from core.verification_gate import verification_gate
from core.improvement_scout import improvement_scout
from core.memory_layers import memory_layers
from db.connections import get_operational_db


def test_queue_priority_peek():
    config = load_system_config()
    queue = TaskQueue(config)

    # Clean test tasks
    conn = get_operational_db()
    conn.execute("DELETE FROM hitl_pending")
    conn.execute("DELETE FROM operation_attempts")
    conn.execute("DELETE FROM operations")
    conn.execute("DELETE FROM task_steps")
    conn.execute("DELETE FROM task_checkpoints")
    conn.execute("DELETE FROM task_leases")
    conn.execute("DELETE FROM tasks")
    conn.commit()
    conn.close()

    assert not queue.has_waiting_task_at_or_above_priority(0)

    # Enqueue priority 2 task
    p2_id = queue.enqueue(
        workflow_type="TEST_P2",
        title="Test P2 Task",
        input_payload={},
        priority=2,
    )
    assert not queue.has_waiting_task_at_or_above_priority(1)
    assert queue.has_waiting_task_at_or_above_priority(2)

    # Enqueue priority 0 task
    p0_id = queue.enqueue(
        workflow_type="TEST_P0",
        title="Test P0 Chat Task",
        input_payload={},
        priority=0,
    )
    assert queue.has_waiting_task_at_or_above_priority(0)
    assert queue.has_waiting_task_at_or_above_priority(1)

    # Cleanup
    conn = get_operational_db()
    conn.execute("DELETE FROM tasks WHERE task_id IN (?, ?)", (p2_id, p0_id))
    conn.commit()
    conn.close()
    print("test_queue_priority_peek passed!")


def test_group_compilation_errors():
    mock_compile_result = {
        "success": False,
        "project_path": "c:/test_proj",
        "ts_errors": [
            {"file": "c:/test_proj/src/App.tsx", "line": 10, "col": 5, "code": "TS2304", "message": "Cannot find name 'X'"},
            {"file": "c:/test_proj/src/App.tsx", "line": 20, "col": 1, "code": "TS2304", "message": "Cannot find name 'Y'"},
            {"file": "c:/test_proj/src/api.ts", "line": 5, "col": 8, "code": "TS2307", "message": "Cannot find module 'foo'"},
        ],
        "py_errors": [
            {"file": "c:/test_proj/backend/main.py", "line": 15, "message": "invalid syntax"}
        ]
    }

    grouped = verification_gate.group_compilation_errors_by_file(mock_compile_result)
    assert "src/App.tsx" in grouped
    assert len(grouped["src/App.tsx"]) == 2
    assert "src/api.ts" in grouped
    assert len(grouped["src/api.ts"]) == 1
    assert "backend/main.py" in grouped
    assert len(grouped["backend/main.py"]) == 1
    print("test_group_compilation_errors passed!")


def test_improvement_scout_queries():
    queries = improvement_scout.build_research_queries(os.path.abspath("."))
    assert len(queries) > 0, "Scout must generate at least one research query"
    # Each query should be a non-empty string
    for q in queries:
        assert isinstance(q, str) and len(q.strip()) > 0, f"Query must be a non-empty string, got: {q!r}"
    print(f"test_improvement_scout_queries passed! ({len(queries)} queries generated)")


def test_memory_layers_activity_summary():
    from datetime import datetime, timezone
    conn = get_operational_db()
    test_log_id = f"test_log_{uuid.uuid4().hex[:8]}"
    try:
        conn.execute(
            """
            INSERT INTO project_health_daemon_logs (
                log_id, project_id, project_name, target_path, pre_health, post_health, action_taken, created_at
            ) VALUES (?, 'proj_test', 'TestProject', 'C:/test', 80, 100, 'AUTO_REPAIRED', ?)
            """,
            (test_log_id, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    finally:
        conn.close()

    try:
        summary = memory_layers.get_recent_autonomous_activity_summary(24)
        # Summary should contain actual content, not just be an empty string
        assert isinstance(summary, str)
        assert len(summary) > 0, "Activity summary must not be empty"
    finally:
        conn = get_operational_db()
        conn.execute("DELETE FROM project_health_daemon_logs WHERE log_id = ?", (test_log_id,))
        conn.commit()
        conn.close()

    print("test_memory_layers_activity_summary passed!")


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_scheduler_preemption_and_model_release():
    config = load_system_config()
    from config.loader import load_model_registry, load_policy_rules
    from core.model_manager import ModelManager
    from core.governance import GovernanceEngine
    from core.scheduler import Scheduler
    from core.queue import TaskClaimResult

    registry = load_model_registry()
    policy = load_policy_rules()
    queue = TaskQueue(config)
    model_mgr = ModelManager(config, registry)
    gov = GovernanceEngine(policy, config)
    scheduler = Scheduler(queue, model_mgr, gov, config)

    conn = get_operational_db()
    conn.execute("DELETE FROM hitl_pending")
    conn.execute("DELETE FROM operation_attempts")
    conn.execute("DELETE FROM operations")
    conn.execute("DELETE FROM task_steps")
    conn.execute("DELETE FROM task_checkpoints")
    conn.execute("DELETE FROM task_leases")
    conn.execute("DELETE FROM tasks")
    conn.commit()
    conn.close()

    # 1. Simulate running a P2 claim
    p2_tid = queue.enqueue(workflow_type="ENDPOINT", title="P2 Worker", input_payload={}, priority=2)
    claim = queue.claim_next_task(["reasoning", "coding", "chat"], allowed_workflows=["ENDPOINT"])
    assert claim is not None
    assert claim.task_id == p2_tid
    scheduler._current_claim = claim

    # Simulate an active asyncio task running
    async def long_running_task():
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            model_mgr.release_task_lease(claim.task_id)
            raise

    task = asyncio.create_task(long_running_task())
    scheduler._current_exec_task = task

    # 2. Trigger preemption
    preempted = scheduler.request_preemption()
    assert preempted is True

    # Allow cancellation to propagate
    await asyncio.sleep(0.05)
    assert task.cancelled() or task.done()

    # Verify task state in SQLite is PREEMPTED
    conn = get_operational_db()
    row = conn.execute("SELECT status FROM tasks WHERE task_id = ?", (claim.task_id,)).fetchone()
    assert row["status"] == "PREEMPTED"

    # Cleanup
    conn.execute("DELETE FROM task_leases WHERE task_id = ?", (claim.task_id,))
    conn.execute("DELETE FROM task_steps WHERE task_id = ?", (claim.task_id,))
    conn.execute("DELETE FROM tasks WHERE task_id = ?", (claim.task_id,))
    conn.commit()
    conn.close()
    print("test_scheduler_preemption_and_model_release passed!")


if __name__ == "__main__":
    test_queue_priority_peek()
    test_group_compilation_errors()
    test_improvement_scout_queries()
    test_memory_layers_activity_summary()
    asyncio.run(test_scheduler_preemption_and_model_release())
    print("ALL TESTS PASSED SUCCESSFULLY!")
