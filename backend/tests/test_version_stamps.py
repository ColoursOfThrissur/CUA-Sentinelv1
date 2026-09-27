import os
import sys
import sqlite3
import pytest

# Ensure backend root is on sys.path
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from db.connections import get_operational_db, initialize_all_databases
from config.loader import get_config_version, compute_prompt_hash, GATEWAY_VERSION
from agents.base_agent import BaseAgent
from core.model_manager import ModelManager
from core.governance import GovernanceEngine


class DummyAgent(BaseAgent):
    async def run(self, claim) -> dict:
        return {}


def test_config_version_and_prompt_hash():
    cfg_ver = get_config_version()
    assert isinstance(cfg_ver, str)
    assert len(cfg_ver) == 16

    h1 = compute_prompt_hash("System rule: do not lie.")
    h2 = compute_prompt_hash("System rule: do not lie.")
    h3 = compute_prompt_hash("System rule: different rule.")

    assert h1 == h2
    assert h1 != h3
    assert len(h1) == 16


def _create_dummy_task(task_id: str):
    conn = get_operational_db()
    try:
        conn.execute(
            """
            INSERT OR IGNORE INTO tasks (task_id, workflow_type, title, status, created_at, updated_at)
            VALUES (?, 'TEST', 'Test Task', 'RUNNING', '2026-09-19T00:00:00Z', '2026-09-19T00:00:00Z')
            """,
            (task_id,),
        )
        conn.commit()
    finally:
        conn.close()


def test_step_audit_row_has_all_version_stamps():
    initialize_all_databases()
    agent = DummyAgent(None, None, {})

    task_id = "test-version-task-1"
    _create_dummy_task(task_id)
    step_id = agent.create_step(
        task_id=task_id,
        step_order=0,
        step_type="PLANNING",
        description="Initial plan step",
        model_id="qwen2.5-coder:7b",
        prompt_hash="abcd1234efgh5678",
    )

    conn = get_operational_db()
    try:
        row = conn.execute(
            """
            SELECT step_id, model_id, prompt_hash, config_version, gateway_version
            FROM task_steps
            WHERE step_id = ?
            """,
            (step_id,),
        ).fetchone()

        assert row is not None
        # All 4 version stamps must be non-null
        assert row["model_id"] == "qwen2.5-coder:7b"
        assert row["prompt_hash"] == "abcd1234efgh5678"
        assert row["config_version"] == get_config_version()
        assert row["gateway_version"] == GATEWAY_VERSION
    finally:
        conn.close()


def test_step_default_version_stamps_are_never_null():
    initialize_all_databases()
    agent = DummyAgent(None, None, {})

    task_id = "test-version-task-2"
    _create_dummy_task(task_id)
    step_id = agent.create_step(
        task_id=task_id,
        step_order=1,
        step_type="EXECUTION",
        description="Running execution step without explicit model",
    )

    conn = get_operational_db()
    try:
        row = conn.execute(
            """
            SELECT step_id, model_id, prompt_hash, config_version, gateway_version
            FROM task_steps
            WHERE step_id = ?
            """,
            (step_id,),
        ).fetchone()

        assert row is not None
        assert row["model_id"] is not None and len(row["model_id"]) > 0
        assert row["prompt_hash"] is not None and len(row["prompt_hash"]) > 0
        assert row["config_version"] is not None and len(row["config_version"]) > 0
        assert row["gateway_version"] is not None and len(row["gateway_version"]) > 0
    finally:
        conn.close()
