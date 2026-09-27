"""Small, dependency-free contracts for the FastAPI application boundary."""

import sys
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

from fastapi.testclient import TestClient


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from api.server import create_app
from config.loader import load_system_config
from core.queue import TaskQueue
from db.connections import get_knowledge_db, get_operational_db


def _client(monkeypatch) -> TestClient:
    # These checks validate the public app contract, not a configured deployment.
    monkeypatch.delenv("SENTINEL_API_TOKEN", raising=False)
    monkeypatch.delenv("SENTINEL_JWT_SECRET", raising=False)
    return TestClient(create_app(None))


def test_health_contract(monkeypatch):
    response = _client(monkeypatch).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_configured_local_origin_is_allowed(monkeypatch):
    response = _client(monkeypatch).options(
        "/api/tasks/",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_unconfigured_origin_is_not_allowed(monkeypatch):
    response = _client(monkeypatch).options(
        "/api/tasks/",
        headers={
            "Origin": "https://untrusted.example",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_auth_contract_blocks_protected_routes_without_a_token(monkeypatch):
    monkeypatch.setenv("SENTINEL_API_TOKEN", "contract-test-token")
    client = TestClient(create_app(None))

    assert client.get("/health").status_code == 200
    assert client.get("/api/tasks/").status_code == 401
    authenticated = client.get("/api/tasks/", headers={"x-sentinel-token": "contract-test-token"})
    assert authenticated.status_code == 200
    assert isinstance(authenticated.json(), list)


def test_task_creation_contract_returns_queued_identifier(monkeypatch):
    monkeypatch.delenv("SENTINEL_API_TOKEN", raising=False)
    app = create_app(None)
    app.state.task_queue = MagicMock()
    app.state.task_queue.enqueue.return_value = "task-contract-001"
    client = TestClient(app)

    response = client.post(
        "/api/tasks/",
        json={
            "workflow_type": "RESEARCHER",
            "title": "Contract task",
            "input_payload": {"question": "What changed?"},
        },
    )

    assert response.status_code == 200
    assert response.json() == {"task_id": "task-contract-001", "status": "QUEUED"}
    app.state.task_queue.enqueue.assert_called_once()


def test_task_cancellation_contract_is_persisted_and_idempotent(monkeypatch):
    monkeypatch.delenv("SENTINEL_API_TOKEN", raising=False)
    title = f"Cancellation contract {uuid4()}"
    task_id = TaskQueue(load_system_config()).enqueue(
        workflow_type="RESEARCHER",
        title=title,
        input_payload={"question": "cancel me"},
    )

    try:
        client = TestClient(create_app(None))
        first = client.post(f"/api/tasks/{task_id}/cancel")
        second = client.post(f"/api/tasks/{task_id}/cancel")
        detail = client.get(f"/api/tasks/{task_id}")

        assert first.status_code == 200
        assert first.json() == {"task_id": task_id, "status": "CANCEL_REQUESTED"}
        assert second.status_code == 200
        assert second.json() == {"task_id": task_id, "status": "CANCEL_REQUESTED"}
        assert detail.status_code == 200
        assert detail.json()["task"]["status"] == "CANCEL_REQUESTED"
    finally:
        conn = get_operational_db()
        try:
            conn.execute("DELETE FROM tasks WHERE task_id = ?", (task_id,))
            conn.commit()
        finally:
            conn.close()

        knowledge = get_knowledge_db()
        try:
            knowledge.execute("DELETE FROM task_graph_nodes WHERE task_id = ?", (task_id,))
            knowledge.commit()
        finally:
            knowledge.close()


def test_dependency_plans_api_contracts(monkeypatch, tmp_path):
    from core.dependency_plans import dependency_plan_builder, dependency_plan_repository

    monkeypatch.delenv("SENTINEL_API_TOKEN", raising=False)
    client = TestClient(create_app(None))

    req_file = tmp_path / "requirements.txt"
    req_file.write_text("fastapi==0.110.0\n", encoding="utf-8")

    plan = dependency_plan_builder.create_plan(
        project_path=str(tmp_path),
        ecosystem="pip",
        package_name="uvicorn",
        requested_spec="uvicorn==0.29.0",
        reason="ASGI server contract test",
        manifest_path=str(req_file),
    )

    try:
        # 1. GET /api/dependency-plans
        list_res = client.get("/api/dependency-plans")
        assert list_res.status_code == 200
        plan_ids = [p["plan_id"] for p in list_res.json()]
        assert plan.plan_id in plan_ids

        # 2. GET /api/dependency-plans/{plan_id}
        get_res = client.get(f"/api/dependency-plans/{plan.plan_id}")
        assert get_res.status_code == 200
        assert get_res.json()["plan_id"] == plan.plan_id
        assert get_res.json()["status"] == "PLANNED"

        # 3. POST /api/dependency-plans/{plan_id}/approve
        appr_res = client.post(
            f"/api/dependency-plans/{plan.plan_id}/approve",
            json={"plan_hash": plan.plan_hash, "allow_unpinned": False},
        )
        assert appr_res.status_code == 200
        assert appr_res.json()["status"] == "APPROVED"

        # 4. Verified plan status updated in database
        updated = dependency_plan_repository.get(plan.plan_id)
        assert updated.status == "APPROVED"

    finally:
        conn = get_operational_db()
        try:
            conn.execute("DELETE FROM dependency_change_plans WHERE plan_id = ?", (plan.plan_id,))
            conn.commit()
        finally:
            conn.close()

