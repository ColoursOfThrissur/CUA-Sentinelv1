import hashlib
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest

BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from core.dependency_plans import (
    DependencyChangeExecutor,
    DependencyPlanBuilder,
    DependencyPlanRepository,
    hash_file,
    is_pinned_spec,
    validate_package_name,
    validate_requested_spec,
)
from core.path_security import PathSecurityViolation
from db.connections import get_audit_db, get_operational_db, initialize_all_databases


@pytest.fixture(autouse=True)
def initialize_db():
    initialize_all_databases()


@pytest.fixture
def temp_project(tmp_path):
    project_dir = tmp_path / "sample_project"
    project_dir.mkdir()
    req_file = project_dir / "requirements.txt"
    req_file.write_text("fastapi==0.110.0\n", encoding="utf-8")
    package_json = project_dir / "package.json"
    package_json.write_text('{"name": "test-pkg", "dependencies": {}}\n', encoding="utf-8")
    return project_dir


def test_dependency_plan_persists_immutable_approval_inputs():
    repository = DependencyPlanRepository()
    token = uuid4().hex
    plan = repository.create(
        project_path=f"C:/projects/{token}",
        ecosystem="pip",
        package_name="requests",
        requested_spec="requests==2.32.3",
        reason="Missing import in backend/client.py",
        evidence=[{"source": "backend/client.py", "import": "requests"}],
        manifest_path=f"C:/projects/{token}/requirements.txt",
        manifest_before_hash="manifest-before",
        command=["python", "-m", "pip", "install", "requests==2.32.3"],
    )

    try:
        restored = repository.get(plan.plan_id)
        assert restored == plan
        assert restored.status == "PLANNED"
        assert restored.command == ["python", "-m", "pip", "install", "requests==2.32.3"]
        assert restored.plan_hash == DependencyPlanRepository.compute_plan_hash(
            project_path=plan.project_path,
            ecosystem=plan.ecosystem,
            package_name=plan.package_name,
            requested_spec=plan.requested_spec,
            manifest_path=plan.manifest_path,
            lockfile_path=plan.lockfile_path,
            manifest_before_hash=plan.manifest_before_hash,
            lockfile_before_hash=plan.lockfile_before_hash,
            command=plan.command,
        )
    finally:
        conn = get_operational_db()
        try:
            conn.execute("DELETE FROM dependency_change_plans WHERE plan_id = ?", (plan.plan_id,))
            conn.commit()
        finally:
            conn.close()


def test_dependency_plan_rejects_invalid_ecosystem_and_command():
    repository = DependencyPlanRepository()
    common = {
        "project_path": "C:/projects/example",
        "package_name": "requests",
        "requested_spec": "requests==2.32.3",
        "reason": "test",
        "manifest_path": "C:/projects/example/requirements.txt",
    }

    with pytest.raises(ValueError, match="Unsupported"):
        repository.create(ecosystem="cargo", command=["cargo", "add", "requests"], **common)

    with pytest.raises(ValueError, match="Command"):
        repository.create(ecosystem="pip", command=["python", ""], **common)


def test_package_name_injection_prevention():
    # Pip injection attempts
    malicious_pip = [
        "; rm -rf /",
        "requests && calc.exe",
        "requests | whoami",
        "`id`",
        "$(whoami)",
        "requests\nmalicious",
        "-e git+https://evil.com/repo.git",
        "--extra-index-url http://evil.com",
        "../../etc/passwd",
        "foo/bar",
        "foo\\bar",
        "requests>2.0",  # Spec character inside package_name
    ]
    for bad_pkg in malicious_pip:
        with pytest.raises(ValueError):
            validate_package_name(bad_pkg, "pip")

    # Safe pip names
    assert validate_package_name("requests", "pip") == "requests"
    assert validate_package_name("pytest-cov", "pip") == "pytest-cov"
    assert validate_package_name("scikit_learn", "pip") == "scikit_learn"
    assert validate_package_name("PyYAML", "pip") == "PyYAML"

    # npm injection attempts
    malicious_npm = [
        "express; calc",
        "-g express",
        "../../malicious",
        "@scope/pkg/extra",
        "@scope\\pkg",
        "Express",  # Scoped / standard npm names disallow uppercase
    ]
    for bad_pkg in malicious_npm:
        with pytest.raises(ValueError):
            validate_package_name(bad_pkg, "npm")

    # Safe npm names
    assert validate_package_name("express", "npm") == "express"
    assert validate_package_name("@types/node", "npm") == "@types/node"
    assert validate_package_name("lodash-es", "npm") == "lodash-es"


def test_requested_spec_validation_and_pinning():
    # Pip specs
    assert is_pinned_spec("requests==2.32.3", "pip") is True
    assert is_pinned_spec("requests>=2.0.0", "pip") is False
    assert is_pinned_spec("requests", "pip") is False
    assert is_pinned_spec("requests==2.*", "pip") is False

    assert validate_requested_spec("requests", "requests==2.32.3", "pip") == "requests==2.32.3"
    assert validate_requested_spec("requests", "requests", "pip") == "requests"

    # Spec that doesn't match package name
    with pytest.raises(ValueError, match="does not match package name"):
        validate_requested_spec("requests", "flask==2.0.0", "pip")

    # Spec containing injection
    with pytest.raises(ValueError):
        validate_requested_spec("requests", "requests==2.32.3; reboot", "pip")

    # npm specs
    assert is_pinned_spec("lodash@4.17.21", "npm") is True
    assert is_pinned_spec("@types/node@20.11.0", "npm") is True
    assert is_pinned_spec("lodash@^4.17.21", "npm") is False
    assert is_pinned_spec("lodash@~4.17.21", "npm") is False
    assert is_pinned_spec("lodash@latest", "npm") is False
    assert is_pinned_spec("lodash", "npm") is False

    assert validate_requested_spec("lodash", "lodash@4.17.21", "npm") == "lodash@4.17.21"
    assert validate_requested_spec("@types/node", "@types/node@20.11.0", "npm") == "@types/node@20.11.0"


def test_plan_builder_enforces_boundaries_and_hashes(temp_project):
    builder = DependencyPlanBuilder()
    req_file = temp_project / "requirements.txt"

    # Valid plan creation inside project
    plan = builder.create_plan(
        project_path=str(temp_project),
        ecosystem="pip",
        package_name="httpx",
        requested_spec="httpx==0.27.0",
        reason="Async HTTP client required",
        manifest_path=str(req_file),
    )

    try:
        assert plan.status == "PLANNED"
        assert plan.is_pinned is True
        assert plan.package_name == "httpx"
        assert plan.requested_spec == "httpx==0.27.0"
        assert plan.manifest_before_hash == hash_file(str(req_file))
        assert plan.command == [sys.executable, "-m", "pip", "install", "httpx==0.27.0"]

        # Manifest outside project root rejected
        with pytest.raises(PathSecurityViolation):
            builder.create_plan(
                project_path=str(temp_project),
                ecosystem="pip",
                package_name="httpx",
                requested_spec="httpx==0.27.0",
                reason="Escape attempt",
                manifest_path=str(temp_project.parent / "other_requirements.txt"),
            )
    finally:
        conn = get_operational_db()
        try:
            conn.execute("DELETE FROM dependency_change_plans WHERE plan_id = ?", (plan.plan_id,))
            conn.commit()
        finally:
            conn.close()


def test_approval_lifecycle_and_single_use_execution(temp_project):
    repository = DependencyPlanRepository()
    builder = DependencyPlanBuilder(repository)
    req_file = temp_project / "requirements.txt"

    plan = builder.create_plan(
        project_path=str(temp_project),
        ecosystem="pip",
        package_name="pydantic",
        requested_spec="pydantic==2.8.2",
        reason="Data validation",
        manifest_path=str(req_file),
    )

    try:
        # Step 1: Request approval (PLANNED -> AWAITING_APPROVAL)
        plan_awaiting = repository.request_approval(plan.plan_id)
        assert plan_awaiting.status == "AWAITING_APPROVAL"

        # Step 2: Tampered hash rejected
        with pytest.raises(ValueError, match="hash mismatch"):
            repository.approve(plan.plan_id, expected_plan_hash="fake_hash_12345")

        # Step 3: Legitimate approval (AWAITING_APPROVAL -> APPROVED)
        plan_approved = repository.approve(plan.plan_id, expected_plan_hash=plan.plan_hash)
        assert plan_approved.status == "APPROVED"
        assert plan_approved.approved_at is not None

        # Cannot approve an already approved plan
        with pytest.raises(ValueError, match="status"):
            repository.approve(plan.plan_id, expected_plan_hash=plan.plan_hash)

        # Step 4: Single-use execution (APPROVED -> EXECUTING)
        plan_executing = repository.mark_executing(plan.plan_id, expected_plan_hash=plan.plan_hash)
        assert plan_executing.status == "EXECUTING"

        # Once executing, cannot execute again (single-use semantics!)
        with pytest.raises(ValueError, match="APPROVED"):
            repository.mark_executing(plan.plan_id, expected_plan_hash=plan.plan_hash)

        # Step 5: Mark completion (EXECUTING -> SUCCEEDED)
        result_payload = {"installed_version": "2.8.2", "duration_ms": 120}
        plan_succeeded = repository.mark_completed(plan.plan_id, success=True, result_payload=result_payload)
        assert plan_succeeded.status == "SUCCEEDED"
        assert plan_succeeded.result == result_payload
        assert plan_succeeded.executed_at is not None

        # Step 6: Verify audit trail was logged
        audit_conn = get_audit_db()
        try:
            audit_rows = audit_conn.execute(
                "SELECT action_type FROM audit_logs WHERE arguments_hash = ? ORDER BY log_sequence ASC",
                (plan.plan_hash,),
            ).fetchall()
            actions = [r["action_type"] for r in audit_rows]
            assert "DEPENDENCY_PLAN_CREATED" in actions
            assert "DEPENDENCY_PLAN_AWAITING_APPROVAL" in actions
            assert "DEPENDENCY_PLAN_APPROVED" in actions
            assert "DEPENDENCY_PLAN_EXECUTING" in actions
            assert "DEPENDENCY_PLAN_SUCCEEDED" in actions
        finally:
            audit_conn.close()

    finally:
        conn = get_operational_db()
        try:
            conn.execute("DELETE FROM dependency_change_plans WHERE plan_id = ?", (plan.plan_id,))
            conn.commit()
        finally:
            conn.close()


def test_unpinned_dependency_requires_explicit_confirmation(temp_project):
    repository = DependencyPlanRepository()
    builder = DependencyPlanBuilder(repository)
    req_file = temp_project / "requirements.txt"

    # Unpinned pip plan: "requests>=2.25.0"
    plan = builder.create_plan(
        project_path=str(temp_project),
        ecosystem="pip",
        package_name="requests",
        requested_spec="requests>=2.25.0",
        reason="Client library",
        manifest_path=str(req_file),
    )

    try:
        assert plan.is_pinned is False

        # Attempt to approve without allow_unpinned -> Rejected!
        with pytest.raises(ValueError, match="unpinned"):
            repository.approve(plan.plan_id, expected_plan_hash=plan.plan_hash, allow_unpinned=False)

        # Explicit confirmation allows approval
        approved = repository.approve(plan.plan_id, expected_plan_hash=plan.plan_hash, allow_unpinned=True)
        assert approved.status == "APPROVED"

    finally:
        conn = get_operational_db()
        try:
            conn.execute("DELETE FROM dependency_change_plans WHERE plan_id = ?", (plan.plan_id,))
            conn.commit()
        finally:
            conn.close()


def test_stale_manifest_hash_invalidates_plan(temp_project):
    repository = DependencyPlanRepository()
    builder = DependencyPlanBuilder(repository)
    req_file = temp_project / "requirements.txt"

    plan = builder.create_plan(
        project_path=str(temp_project),
        ecosystem="pip",
        package_name="rich",
        requested_spec="rich==13.7.1",
        reason="Terminal formatting",
        manifest_path=str(req_file),
    )

    try:
        # Mutate the manifest on disk after plan was generated
        req_file.write_text("fastapi==0.110.0\n# concurrent change\n", encoding="utf-8")

        # Approval must detect stale hash and reject with failure
        with pytest.raises(ValueError, match="stale hash"):
            repository.approve(plan.plan_id, expected_plan_hash=plan.plan_hash)

        reloaded = repository.get(plan.plan_id)
        assert reloaded.status == "FAILED"
        assert "stale hash" in str(reloaded.result)

    finally:
        conn = get_operational_db()
        try:
            conn.execute("DELETE FROM dependency_change_plans WHERE plan_id = ?", (plan.plan_id,))
            conn.commit()
        finally:
            conn.close()


def test_expired_plans_cannot_be_approved_and_are_culled(temp_project):
    repository = DependencyPlanRepository()
    builder = DependencyPlanBuilder(repository)
    req_file = temp_project / "requirements.txt"

    # Create plan 1 with 1-minute TTL to test approval failure
    plan1 = builder.create_plan(
        project_path=str(temp_project),
        ecosystem="pip",
        package_name="wheel",
        requested_spec="wheel==0.43.0",
        reason="Build dependency",
        manifest_path=str(req_file),
        ttl_minutes=1,
    )

    # Create plan 2 to test expire_stale_plans batch culling
    plan2 = builder.create_plan(
        project_path=str(temp_project),
        ecosystem="pip",
        package_name="setuptools",
        requested_spec="setuptools==69.0.0",
        reason="Build tools",
        manifest_path=str(req_file),
        ttl_minutes=1,
    )

    try:
        # Artificially expire both plans in the database
        past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        conn = get_operational_db()
        try:
            conn.execute("UPDATE dependency_change_plans SET expires_at = ? WHERE plan_id IN (?, ?)", (past, plan1.plan_id, plan2.plan_id))
            conn.commit()
        finally:
            conn.close()

        # Approval fails due to expiry on plan1 (and marks it EXPIRED)
        with pytest.raises(ValueError, match="expired"):
            repository.approve(plan1.plan_id, expected_plan_hash=plan1.plan_hash)

        reloaded1 = repository.get(plan1.plan_id)
        assert reloaded1.status == "EXPIRED"

        # expire_stale_plans culls remaining un-approved expired plan2
        culled = repository.expire_stale_plans()
        assert culled >= 1

        reloaded2 = repository.get(plan2.plan_id)
        assert reloaded2.status == "EXPIRED"

    finally:
        conn = get_operational_db()
        try:
            conn.execute("DELETE FROM dependency_change_plans WHERE plan_id IN (?, ?)", (plan1.plan_id, plan2.plan_id))
            conn.commit()
        finally:
            conn.close()


def test_plan_rejection_lifecycle(temp_project):
    repository = DependencyPlanRepository()
    builder = DependencyPlanBuilder(repository)
    req_file = temp_project / "requirements.txt"

    plan = builder.create_plan(
        project_path=str(temp_project),
        ecosystem="pip",
        package_name="click",
        requested_spec="click==8.1.7",
        reason="CLI support",
        manifest_path=str(req_file),
    )

    try:
        rejected = repository.reject(plan.plan_id, reason="Not approved by policy")
        assert rejected.status == "REJECTED"
        assert rejected.result == {"reject_reason": "Not approved by policy"}

        # Cannot approve or execute a rejected plan
        with pytest.raises(ValueError):
            repository.approve(plan.plan_id, expected_plan_hash=plan.plan_hash)
        with pytest.raises(ValueError):
            repository.mark_executing(plan.plan_id, expected_plan_hash=plan.plan_hash)

    finally:
        conn = get_operational_db()
        try:
            conn.execute("DELETE FROM dependency_change_plans WHERE plan_id = ?", (plan.plan_id,))
            conn.commit()
        finally:
            conn.close()


def test_executor_successful_execution_and_backup(temp_project):
    repository = DependencyPlanRepository()
    builder = DependencyPlanBuilder(repository)
    req_file = temp_project / "requirements.txt"

    plan = builder.create_plan(
        project_path=str(temp_project),
        ecosystem="pip",
        package_name="black",
        requested_spec="black==24.4.2",
        reason="Code formatting",
        manifest_path=str(req_file),
    )

    try:
        # Must approve plan first
        repository.approve(plan.plan_id, expected_plan_hash=plan.plan_hash)

        # Mock process runner that simulates pip install success and updates requirements.txt
        recorded_calls = []

        class FakeProcessResult:
            returncode = 0
            stdout = "Successfully installed black-24.4.2"
            stderr = ""

        def fake_runner(cmd, cwd, capture_output, text, timeout, shell):
            recorded_calls.append({
                "cmd": cmd,
                "cwd": cwd,
                "shell": shell,
            })
            # Simulate file change
            with open(req_file, "a", encoding="utf-8") as f:
                f.write("black==24.4.2\n")
            return FakeProcessResult()

        executor = DependencyChangeExecutor(repository=repository, process_runner=fake_runner)
        result = executor.execute_plan(plan.plan_id, expected_plan_hash=plan.plan_hash)

        # Invariants: shell must be False, command must be array
        assert len(recorded_calls) == 1
        assert recorded_calls[0]["shell"] is False
        assert recorded_calls[0]["cmd"] == [sys.executable, "-m", "pip", "install", "black==24.4.2"]
        assert recorded_calls[0]["cwd"] == str(temp_project)

        # Execution result assertions
        assert result["success"] is True
        assert result["returncode"] == 0
        assert "Successfully installed" in result["stdout"]

        # Backup assertion
        backup_file = os.path.join(result["backup_dir"], "requirements.txt")
        assert os.path.isfile(backup_file)
        with open(backup_file, "r", encoding="utf-8") as f:
            backup_content = f.read()
        assert "fastapi==0.110.0" in backup_content
        assert "black" not in backup_content  # Pre-execution backup

        # Database state assertion
        completed_plan = repository.get(plan.plan_id)
        assert completed_plan.status == "SUCCEEDED"
        assert completed_plan.result["success"] is True
        assert completed_plan.executed_at is not None

    finally:
        conn = get_operational_db()
        try:
            conn.execute("DELETE FROM dependency_change_plans WHERE plan_id = ?", (plan.plan_id,))
            conn.commit()
        finally:
            conn.close()


def test_executor_failure_and_rollback(temp_project):
    repository = DependencyPlanRepository()
    builder = DependencyPlanBuilder(repository)
    req_file = temp_project / "requirements.txt"
    original_content = req_file.read_text(encoding="utf-8")

    plan = builder.create_plan(
        project_path=str(temp_project),
        ecosystem="pip",
        package_name="flake8",
        requested_spec="flake8==7.0.0",
        reason="Linter",
        manifest_path=str(req_file),
    )

    try:
        repository.approve(plan.plan_id, expected_plan_hash=plan.plan_hash)

        class FakeProcessFailure:
            returncode = 1
            stdout = ""
            stderr = "ERROR: Could not find a version that satisfies the requirement"

        def fake_failing_runner(cmd, cwd, capture_output, text, timeout, shell):
            # Simulate corrupt partial write before failure
            with open(req_file, "w", encoding="utf-8") as f:
                f.write("corrupted content during failed install\n")
            return FakeProcessFailure()

        executor = DependencyChangeExecutor(repository=repository, process_runner=fake_failing_runner)
        result = executor.execute_plan(plan.plan_id, expected_plan_hash=plan.plan_hash)

        assert result["success"] is False
        assert result["returncode"] == 1
        assert "Could not find a version" in result["stderr"]

        failed_plan = repository.get(plan.plan_id)
        assert failed_plan.status == "FAILED"

        # Explicit rollback request restores the pre-execution backup
        rollback_res = executor.rollback_plan(plan.plan_id, actor="operator")
        assert rollback_res["success"] is True
        assert str(req_file) in rollback_res["restored_files"]
        assert req_file.read_text(encoding="utf-8") == original_content

        # Verify rollback logged in audit trail
        audit_conn = get_audit_db()
        try:
            row = audit_conn.execute(
                "SELECT * FROM audit_logs WHERE arguments_hash = ? AND action_type = 'DEPENDENCY_PLAN_ROLLBACK'",
                (plan.plan_hash,),
            ).fetchone()
            assert row is not None
        finally:
            audit_conn.close()

    finally:
        conn = get_operational_db()
        try:
            conn.execute("DELETE FROM dependency_change_plans WHERE plan_id = ?", (plan.plan_id,))
            conn.commit()
        finally:
            conn.close()


def test_executor_rejects_unapproved_plan(temp_project):
    repository = DependencyPlanRepository()
    builder = DependencyPlanBuilder(repository)
    req_file = temp_project / "requirements.txt"

    plan = builder.create_plan(
        project_path=str(temp_project),
        ecosystem="pip",
        package_name="isort",
        requested_spec="isort==5.13.2",
        reason="Import sorter",
        manifest_path=str(req_file),
    )

    try:
        executor = DependencyChangeExecutor(repository=repository)
        # Attempt execution while in PLANNED status -> Must be rejected!
        with pytest.raises(ValueError, match="APPROVED"):
            executor.execute_plan(plan.plan_id, expected_plan_hash=plan.plan_hash)

        # Transition to AWAITING_APPROVAL -> Still must be rejected!
        repository.request_approval(plan.plan_id)
        with pytest.raises(ValueError, match="APPROVED"):
            executor.execute_plan(plan.plan_id, expected_plan_hash=plan.plan_hash)

    finally:
        conn = get_operational_db()
        try:
            conn.execute("DELETE FROM dependency_change_plans WHERE plan_id = ?", (plan.plan_id,))
            conn.commit()
        finally:
            conn.close()

