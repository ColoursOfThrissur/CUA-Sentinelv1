"""
Tests for Phase 3 Persistence Hardening:
- Concurrency safety under multi-threaded writes
- Bounded retry / exponential backoff on SQLite lock contention
- Structured failure reporting with DatabaseLockError
- Pre-migration backup snapshot generation
- Architectural invariant: zero direct SQL in backend/agents/
"""

import concurrent.futures
import os
from pathlib import Path
import sqlite3
import sys
import threading
import time

backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import pytest
from backend.db.connections import (
    initialize_all_databases,
    get_operational_db,
    get_audit_db,
    get_knowledge_db,
    _backup_db_pre_migrate,
    DB_DIR,
)
from backend.db.transaction import (
    DatabaseLockError,
    execute_write_transaction,
    is_lock_error,
    run_write_with_retry,
)
from backend.db.repositories.operational_repo import OperationalRepository
from backend.db.repositories.audit_repo import AuditRepository
from backend.db.repositories.knowledge_repo import KnowledgeRepository


@pytest.fixture(autouse=True)
def setup_databases(tmp_path, monkeypatch):
    """Run tests against temporary SQLite databases."""
    op_path = tmp_path / "operational.sqlite"
    audit_path = tmp_path / "audit.sqlite"
    knowledge_path = tmp_path / "knowledge.sqlite"
    state_path = tmp_path / "state.sqlite"

    monkeypatch.setattr("backend.db.connections.OPERATIONAL_DB", op_path)
    monkeypatch.setattr("backend.db.connections.AUDIT_DB", audit_path)
    monkeypatch.setattr("backend.db.connections.KNOWLEDGE_DB", knowledge_path)
    monkeypatch.setattr("backend.db.connections.STATE_DB", state_path)
    monkeypatch.setattr("backend.db.connections.DB_DIR", tmp_path)

    initialize_all_databases()
    yield tmp_path


def test_concurrent_task_and_step_creation():
    """Verify concurrent writes from multiple threads into OperationalRepository do not corrupt or deadlock."""
    repo = OperationalRepository(db_getter=get_operational_db)
    num_threads = 10
    tasks_per_thread = 5

    def worker(worker_idx: int):
        created_ids = []
        for i in range(tasks_per_thread):
            tid = repo.create_task(
                title=f"Worker-{worker_idx}-Task-{i}",
                workflow_type="ENDPOINT",
                priority=1,
            )
            created_ids.append(tid)
            # Create steps for this task
            sid = repo.create_step(
                task_id=tid,
                step_order=0,
                step_type="INIT",
                description="Initialize task",
            )
            repo.update_step_status(step_id=sid, status="COMPLETED")
            repo.save_checkpoint(
                task_id=tid,
                step_index=0,
                state_dict={"progress": 100},
                input_hash="test_hash",
            )
        return created_ids

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(worker, idx) for idx in range(num_threads)]
        results = [f.result() for f in futures]

    all_tasks = repo.list_tasks(limit=100)
    assert len(all_tasks) == num_threads * tasks_per_thread


def test_concurrent_audit_logging():
    """Verify concurrent audit logging under contention."""
    repo = AuditRepository(db_getter=get_audit_db)
    num_threads = 8
    logs_per_thread = 10

    def audit_worker(worker_idx: int):
        for i in range(logs_per_thread):
            repo.append_audit_log(
                task_id=f"task_worker_{worker_idx}",
                who_actor=f"worker_{worker_idx}",
                action_type="EXECUTE_TOOL",
                tool_name="web_search",
                decision_summary={"allowed": True, "index": i},
            )

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(audit_worker, idx) for idx in range(num_threads)]
        for f in futures:
            f.result()

    recent_logs = repo.list_recent_audit_logs(limit=200)
    assert len(recent_logs) == num_threads * logs_per_thread


def test_concurrent_knowledge_claims_and_digests():
    """Verify concurrent writes to KnowledgeRepository."""
    repo = KnowledgeRepository(db_getter=get_knowledge_db)
    num_threads = 6

    def knowledge_worker(idx: int):
        for i in range(5):
            repo.save_claim(
                task_id=f"task_k_{idx}",
                claim_text=f"Factual claim {i} from worker {idx}",
                domain="AI",
                confidence_score=0.88,
            )
            repo.write_memory(
                task_id=f"task_k_{idx}",
                agent_type="researcher",
                summary={"key": f"value_{idx}_{i}"},
            )

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(knowledge_worker, idx) for idx in range(num_threads)]
        for f in futures:
            f.result()

    claims = repo.get_claims_for_task("task_k_0")
    assert len(claims) == 5
    memories = repo.read_memories_for_task("task_k_0")
    assert len(memories) == 5


def test_bounded_retry_succeeds_after_transient_lock(tmp_path):
    """Verify execute_write_transaction retries and succeeds when lock is temporarily held."""
    db_file = tmp_path / "test_retry.sqlite"
    conn_setup = sqlite3.connect(str(db_file), timeout=5.0)
    conn_setup.execute("PRAGMA journal_mode=WAL")
    conn_setup.execute("CREATE TABLE counter (val INTEGER)")
    conn_setup.execute("INSERT INTO counter VALUES (0)")
    conn_setup.commit()
    conn_setup.close()

    lock_released = threading.Event()
    writer_ready = threading.Event()

    def lock_holder():
        conn_holder = sqlite3.connect(str(db_file), timeout=5.0)
        conn_holder.execute("BEGIN EXCLUSIVE")
        writer_ready.set()
        # Hold lock briefly (120ms) then commit and release
        time.sleep(0.12)
        conn_holder.execute("UPDATE counter SET val = 1")
        conn_holder.commit()
        conn_holder.close()
        lock_released.set()

    t_holder = threading.Thread(target=lock_holder)
    t_holder.start()

    writer_ready.wait(timeout=2.0)

    # Now attempt a write from second connection with retry
    conn_writer = sqlite3.connect(str(db_file), timeout=0.01)
    with execute_write_transaction(
        conn=conn_writer,
        operation_name="test_transient_lock",
        max_retries=5,
        initial_delay=0.04,
        backoff_factor=1.5,
        db_name="test_retry",
    ) as cur:
        cur.execute("UPDATE counter SET val = val + 10")

    t_holder.join(timeout=2.0)
    conn_writer.close()

    # Final check: counter should be 1 + 10 = 11
    conn_verify = sqlite3.connect(str(db_file))
    val = conn_verify.execute("SELECT val FROM counter").fetchone()[0]
    conn_verify.close()
    assert val == 11


def test_retry_exhaustion_raises_database_lock_error(tmp_path):
    """Verify that permanent lock exhaustion raises DatabaseLockError with structured info."""
    db_file = tmp_path / "test_exhaust.sqlite"
    conn_setup = sqlite3.connect(str(db_file))
    conn_setup.execute("CREATE TABLE t (x INT)")
    conn_setup.commit()
    conn_setup.close()

    conn_holder = sqlite3.connect(str(db_file))
    conn_holder.execute("BEGIN EXCLUSIVE")

    conn_writer = sqlite3.connect(str(db_file), timeout=0.001)

    with pytest.raises(DatabaseLockError) as exc_info:
        with execute_write_transaction(
            conn=conn_writer,
            operation_name="exhaust_op",
            max_retries=3,
            initial_delay=0.01,
            db_name="exhaust_db",
        ) as cur:
            cur.execute("INSERT INTO t VALUES (42)")

    err = exc_info.value
    assert err.db_name == "exhaust_db"
    assert err.operation == "exhaust_op"
    assert err.retries_attempted == 3
    assert err.elapsed_seconds >= 0.01

    conn_holder.rollback()
    conn_holder.close()
    conn_writer.close()


def test_pre_migration_backup_creation(tmp_path):
    """Verify _backup_db_pre_migrate creates a timestamped backup before migrations."""
    db_file = tmp_path / "operational.sqlite"
    conn = sqlite3.connect(str(db_file))
    conn.execute("CREATE TABLE test (id INT)")
    conn.execute("INSERT INTO test VALUES (100)")
    conn.commit()
    conn.close()

    backup_path = _backup_db_pre_migrate(db_file)
    assert backup_path is not None
    assert backup_path.exists()
    assert ".sentinel_backup" in str(backup_path)
    assert "db_pre_migrate" in str(backup_path)
    assert backup_path.stat().st_size > 0


def test_architectural_rule_zero_direct_sql_in_agents():
    """Verify no agent in backend/agents/ issues direct raw SQL statements."""
    agents_dir = Path(__file__).resolve().parent.parent / "agents"
    forbidden_terms = [".execute(", ".executescript("]

    violations = []
    for py_file in agents_dir.glob("*.py"):
        code = py_file.read_text(encoding="utf-8")
        for term in forbidden_terms:
            if term in code:
                violations.append(f"{py_file.name} contains forbidden direct SQL call '{term}'")

    assert not violations, f"Architectural Invariant Violations found in agents:\n" + "\n".join(violations)
