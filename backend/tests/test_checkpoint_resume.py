import os
import sys
import asyncio
import json
import pytest
from unittest.mock import MagicMock, AsyncMock

# Ensure backend root is on sys.path
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from agents.base_agent import BaseAgent
from core.governance import GovernanceEngine
from config.loader import load_policy_rules, load_system_config
from core.queue import TaskQueue, TaskClaimResult
from core.scheduler import Scheduler
from core.model_manager import ModelManager
from db.connections import get_operational_db, initialize_all_databases


class CheckpointWorkflowAgent(BaseAgent):
    agent_name = "test_checkpoint_agent"

    async def run(self, claim: TaskClaimResult) -> dict:
        task_id = claim.task_id
        payload = claim.input_payload or {}
        
        # P0.4: Check for previous checkpoint
        chk = self.load_latest_checkpoint(task_id, current_input_payload=payload)
        start_step = chk["next_step_index"] if chk else 0
        state = chk["state"] if chk else {"processed_items": []}

        # Multi-step pipeline simulation: Steps 0, 1, 2
        for step_idx in range(start_step, 3):
            # Check cooperative yield signal at step boundary
            if self.should_yield(task_id):
                return {"status": "yielded", "at_step": step_idx, "state": state}

            step_id = self.create_step(task_id, step_idx, f"STEP_{step_idx}", f"Processing step {step_idx}")
            self.update_step_status(step_id, "RUNNING")

            # Perform side-effect (write tool) in step 1
            if step_idx == 1:
                await self.execute_tool(
                    "file_write",
                    {"file_path": "output.txt", "data": "payload"},
                    task_id=task_id,
                    step_id=step_id,
                    tool_instance=lambda **kw: {"written": True},
                )

            # Update state
            state["processed_items"].append(f"item_{step_idx}")
            
            # Mark step complete and write checkpoint
            self.update_step_status(step_id, "COMPLETED", {"step": step_idx})
            self.write_checkpoint(
                task_id=task_id,
                step_index=step_idx,
                phase="PROCESSING",
                state_dict=state,
                input_payload=payload,
            )

        return {"status": "completed", "final_state": state}


@pytest.fixture
def agent():
    initialize_all_databases()
    gov = GovernanceEngine(load_policy_rules(), load_system_config())
    mm = MagicMock()
    return CheckpointWorkflowAgent(mm, gov, {"governance": {"max_tool_calls_per_task": 10}})


def test_checkpoint_written_on_step_complete(agent):
    """P0.4: Checkpoint is persisted to task_checkpoints table after step completion."""
    task_id = "test_chk_write"
    payload = {"query": "sample"}

    # Ensure task exists in DB
    conn = get_operational_db()
    conn.execute("INSERT OR REPLACE INTO tasks (task_id, workflow_type, title, status) VALUES (?, 'ENDPOINT', 'Test', 'RUNNING')", (task_id,))
    conn.commit()
    conn.close()

    chk_id = agent.write_checkpoint(
        task_id=task_id,
        step_index=0,
        phase="SETUP",
        state_dict={"count": 42},
        input_payload=payload,
    )
    assert chk_id.startswith("chk_")

    conn = get_operational_db()
    row = conn.execute("SELECT * FROM task_checkpoints WHERE checkpoint_id = ?", (chk_id,)).fetchone()
    conn.close()

    assert row is not None
    assert row["task_id"] == task_id
    assert row["step_index"] == 0
    assert row["phase"] == "SETUP"
    state = json.loads(row["state_json"])
    assert state["count"] == 42


def test_resume_continues_from_step_k(agent):
    """P0.4: When interrupted mid-task, agent resumes at step k+1 instead of step 0."""
    task_id = "test_resume_step_k"
    payload = {"doc_id": "123"}

    conn = get_operational_db()
    conn.execute("INSERT OR REPLACE INTO tasks (task_id, workflow_type, title, status) VALUES (?, 'ENDPOINT', 'Resume', 'RUNNING')", (task_id,))
    conn.commit()
    conn.close()

    # Step 0 completed and checkpointed
    agent.write_checkpoint(task_id, step_index=0, phase="P1", state_dict={"done": [0]}, input_payload=payload)
    # Step 1 completed and checkpointed
    agent.write_checkpoint(task_id, step_index=1, phase="P2", state_dict={"done": [0, 1]}, input_payload=payload)

    # Resume check
    chk = agent.load_latest_checkpoint(task_id, current_input_payload=payload)
    assert chk is not None
    assert chk["step_index"] == 1
    assert chk["next_step_index"] == 2
    assert chk["state"]["done"] == [0, 1]


@pytest.mark.asyncio
async def test_idempotency_prevents_duplicate_side_effects(agent):
    """P0.4: Steps with side effects do not execute twice when replayed."""
    task_id = "test_idempotency"
    step_id = "step_idemp_1"

    # Setup task and step in DB
    conn = get_operational_db()
    conn.execute("DELETE FROM operations WHERE task_id = ?", (task_id,))
    conn.execute("INSERT OR REPLACE INTO tasks (task_id, workflow_type, title, status) VALUES (?, 'ENDPOINT', 'Idemp', 'RUNNING')", (task_id,))
    conn.execute("INSERT OR REPLACE INTO task_steps (step_id, task_id, step_order, step_type, description, status) VALUES (?, ?, 1, 'WRITE', 'write', 'RUNNING')", (step_id, task_id))
    conn.commit()
    conn.close()

    agent.agent_name = "code_refactor_agent"
    execution_counter = {"count": 0}

    def mock_write(file_path, content):
        execution_counter["count"] += 1
        return {"bytes_written": 100}

    # 1. First execution: should execute
    res1 = await agent.execute_tool(
        "file_write",
        {"file_path": "data.txt", "content": "hello"},
        task_id=task_id,
        step_id=step_id,
        tool_instance=mock_write,
    )
    assert res1["status"] == "ok"
    assert execution_counter["count"] == 1

    # 2. Replayed execution with identical parameters: should detect idempotency and skip execution
    res2 = await agent.execute_tool(
        "file_write",
        {"file_path": "data.txt", "content": "hello"},
        task_id=task_id,
        step_id=step_id,
        tool_instance=mock_write,
    )
    assert res2["status"] == "ok"
    assert res2["reason"] == "idempotent_replay"
    assert res2["data"]["idempotent_replay"] is True
    # Ensure tool handler was not invoked a second time
    assert execution_counter["count"] == 1


def test_stale_checkpoint_or_hash_mismatch_restarts(agent):
    """P0.4: Checkpoint is ignored and execution restarts at step 0 if input payload changed."""
    task_id = "test_hash_mismatch"
    initial_payload = {"version": "v1"}

    conn = get_operational_db()
    conn.execute("INSERT OR REPLACE INTO tasks (task_id, workflow_type, title, status) VALUES (?, 'ENDPOINT', 'Mismatch', 'RUNNING')", (task_id,))
    conn.commit()
    conn.close()

    agent.write_checkpoint(task_id, step_index=2, state_dict={"foo": "bar"}, input_payload=initial_payload)

    # Re-claim with altered input payload
    modified_payload = {"version": "v2_updated"}
    chk = agent.load_latest_checkpoint(task_id, current_input_payload=modified_payload)
    # Checkpoint must be rejected
    assert chk is None


def test_cooperative_preemption_at_step_boundary(agent):
    """P0.4: Cooperative preemption signal is detected via should_yield."""
    task_id = "test_coop_preempt"

    conn = get_operational_db()
    conn.execute("INSERT OR REPLACE INTO tasks (task_id, workflow_type, title, status) VALUES (?, 'ENDPOINT', 'Coop', 'RUNNING')", (task_id,))
    conn.commit()
    conn.close()

    assert agent.should_yield(task_id) is False

    # Mark PREEMPTED
    conn = get_operational_db()
    conn.execute("UPDATE tasks SET status = 'PREEMPTED' WHERE task_id = ?", (task_id,))
    conn.commit()
    conn.close()

    assert agent.should_yield(task_id) is True


@pytest.mark.asyncio
async def test_agent_killed_mid_task_resumes_without_repeating_side_effect(agent):
    """
    Acceptance test (Section 5.4):
    Simulate agent being killed mid-task during multi-step execution.
    On re-claim it continues at step k, not step 0, and does not repeat a side-effecting step.
    """
    task_id = "test_kill_and_resume"
    payload = {"job": "multi_step_processing"}

    conn = get_operational_db()
    conn.execute("DELETE FROM operations WHERE task_id = ?", (task_id,))
    conn.execute("INSERT OR REPLACE INTO tasks (task_id, workflow_type, title, status) VALUES (?, 'ENDPOINT', 'KillResume', 'RUNNING')", (task_id,))
    conn.commit()
    conn.close()

    agent.agent_name = "code_refactor_agent"
    claim = TaskClaimResult(
        task_id=task_id,
        lease_id="lease_1",
        lease_generation=1,
        workflow_type="ENDPOINT",
        input_payload=payload,
        context_budget=4096,
        priority=1,
    )

    # 1. Run step 0 and complete
    step0_id = agent.create_step(task_id, 0, "STEP_0", "Step 0 init")
    agent.update_step_status(step0_id, "COMPLETED", {"processed": 0})
    agent.write_checkpoint(task_id, 0, "INIT", {"items": [0]}, input_payload=payload)

    # 2. Run step 1: executes side-effect tool file_write
    step1_id = agent.create_step(task_id, 1, "STEP_1", "Step 1 write")
    side_effect_counter = {"executions": 0}

    def mock_side_effect(file_path, data):
        side_effect_counter["executions"] += 1
        return {"written": True}

    res_write = await agent.execute_tool(
        "file_write",
        {"file_path": "audit_record.txt", "data": "state_update"},
        task_id=task_id,
        step_id=step1_id,
        tool_instance=mock_side_effect,
    )
    assert res_write["status"] == "ok"
    assert side_effect_counter["executions"] == 1

    agent.update_step_status(step1_id, "COMPLETED", {"processed": 1})
    agent.write_checkpoint(task_id, 1, "MUTATED", {"items": [0, 1]}, input_payload=payload)

    # 3. SIMULATE AGENT CRASH / KILL HERE
    # A fresh agent instance claims the task and continues
    gov = GovernanceEngine(load_policy_rules(), load_system_config())
    fresh_agent = CheckpointWorkflowAgent(MagicMock(), gov, {"governance": {"max_tool_calls_per_task": 10}})
    fresh_agent.agent_name = "code_refactor_agent"

    # Re-claim check
    resumed_chk = fresh_agent.load_latest_checkpoint(task_id, current_input_payload=payload)
    assert resumed_chk is not None
    assert resumed_chk["step_index"] == 1
    assert resumed_chk["next_step_index"] == 2  # Continues from step 2, not step 0!

    # 4. If step 1's side-effecting tool is re-invoked with the exact same step_id, idempotency skips execution
    replayed_res = await fresh_agent.execute_tool(
        "file_write",
        {"file_path": "audit_record.txt", "data": "state_update"},
        task_id=task_id,
        step_id=step1_id,
        tool_instance=mock_side_effect,
    )
    assert replayed_res["status"] == "ok"
    assert replayed_res["reason"] == "idempotent_replay"
    assert side_effect_counter["executions"] == 1  # Did NOT repeat side-effect!


def test_watchdog_preserves_checkpoints_on_lease_expiry(agent):
    """
    Acceptance test (Section 5.4):
    When watchdog expires a stale lease and re-queues the task, checkpoints are preserved.
    """
    config = load_system_config()
    queue = TaskQueue(config)

    # Clean existing tasks in DB to ensure deterministic claim
    conn = get_operational_db()
    conn.execute("UPDATE system_state SET value = '0' WHERE key = 'safe_mode'")
    conn.execute("DELETE FROM hitl_pending")
    conn.execute("DELETE FROM operation_attempts")
    conn.execute("DELETE FROM operations")
    conn.execute("DELETE FROM task_steps")
    conn.execute("DELETE FROM task_checkpoints")
    conn.execute("DELETE FROM task_leases")
    conn.execute("DELETE FROM tasks")
    conn.commit()
    conn.close()

    payload = {"task": "watchdog_preservation"}

    # Enqueue task
    tid = queue.enqueue(workflow_type="ENDPOINT", title="Watchdog Task", input_payload=payload, priority=1)
    claim = queue.claim_next_task(["reasoning", "coding"], allowed_workflows=["ENDPOINT"])
    assert claim is not None
    assert claim.task_id == tid

    # Agent records checkpoint at step 0
    agent.write_checkpoint(tid, step_index=0, phase="WORK", state_dict={"count": 10}, input_payload=payload)

    # Manually expire the lease in task_leases
    conn = get_operational_db()
    conn.execute("UPDATE task_leases SET expires_at = '2020-01-01T00:00:00Z' WHERE task_id = ?", (tid,))
    conn.commit()
    conn.close()

    # Run expire_stale_leases
    expired_count = queue.expire_stale_leases()
    assert expired_count == 1

    # Verify task is back in QUEUED status
    conn = get_operational_db()
    task_row = conn.execute("SELECT status FROM tasks WHERE task_id = ?", (tid,)).fetchone()
    assert task_row["status"] == "QUEUED"

    # Verify checkpoint is still intact!
    chk = agent.load_latest_checkpoint(tid, current_input_payload=payload)
    assert chk is not None
    assert chk["step_index"] == 0
    assert chk["next_step_index"] == 1
    assert chk["state"]["count"] == 10

    # Teardown test task
    conn.execute("DELETE FROM task_checkpoints WHERE task_id = ?", (tid,))
    conn.execute("DELETE FROM task_leases WHERE task_id = ?", (tid,))
    conn.execute("DELETE FROM tasks WHERE task_id = ?", (tid,))
    conn.commit()
    conn.close()
