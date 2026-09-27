"""
OpenAPI schema snapshot and frontend API client contract tests.
Verifies that:
1. OpenAPI specification generates cleanly and is saved to docs/openapi.json.
2. Every endpoint called by frontend/src/api/index.ts matches a valid route in the FastAPI application.
3. The /health/ready endpoint reports readiness without loading models.
4. Incoming correlation IDs (x-correlation-id) are echoed in response headers.
"""

from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
import re
import sys

backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import pytest
from fastapi.testclient import TestClient
from backend.api.server import create_app
from backend.db.connections import initialize_all_databases


@asynccontextmanager
async def dummy_lifespan(app):
    yield


@pytest.fixture(scope="module")
def app_and_client():
    initialize_all_databases()
    app = create_app(dummy_lifespan)
    client = TestClient(app, base_url="http://testserver")
    return app, client


def test_openapi_snapshot_generation(app_and_client):
    """Generates and verifies the OpenAPI snapshot document at docs/openapi.json."""
    app, _ = app_and_client
    schema = app.openapi()
    assert schema is not None
    assert "paths" in schema
    assert "/health" in schema["paths"]
    assert "/health/ready" in schema["paths"]
    assert "/api/tasks/" in schema["paths"] or "/api/tasks" in schema["paths"]

    docs_dir = Path(__file__).resolve().parent.parent.parent / "docs"
    docs_dir.mkdir(exist_ok=True)
    snapshot_path = docs_dir / "openapi.json"
    snapshot_path.write_text(json.dumps(schema, indent=2), encoding="utf-8")
    assert snapshot_path.exists()
    assert snapshot_path.stat().st_size > 1000


def test_health_ready_endpoint(app_and_client):
    """Verifies that /health/ready checks databases and configuration."""
    _, client = app_and_client
    resp = client.get("/health/ready")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ready"
    assert data["config"] == "ok"
    assert "databases" in data
    assert data["databases"].get("operational") == "ok"
    assert data["databases"].get("audit") == "ok"
    assert data["databases"].get("knowledge") == "ok"
    assert "model_runtime" in data


def test_correlation_id_propagation(app_and_client):
    """Verifies that x-correlation-id is propagated or generated in response headers."""
    _, client = app_and_client

    # 1. Custom correlation ID provided
    custom_corr = "corr_custom_test_12345"
    resp = client.get("/health", headers={"x-correlation-id": custom_corr})
    assert resp.status_code == 200
    assert resp.headers.get("x-correlation-id") == custom_corr

    # 2. Auto-generated correlation ID when not provided
    resp_auto = client.get("/health")
    assert resp_auto.status_code == 200
    assert resp_auto.headers.get("x-correlation-id") is not None
    assert resp_auto.headers.get("x-correlation-id").startswith("corr_")


def test_frontend_api_endpoints_covered_by_backend(app_and_client):
    """Verifies that endpoints in frontend/src/api/index.ts have matching FastAPI routes."""
    app, _ = app_and_client
    frontend_api_file = Path(__file__).resolve().parent.parent.parent / "frontend" / "src" / "api" / "index.ts"
    if not frontend_api_file.exists():
        pytest.skip("frontend/src/api/index.ts not found")

    content = frontend_api_file.read_text(encoding="utf-8")

    # Extract all api.get/post/put/delete('/path...') occurrences
    pattern = re.compile(r"api\.(get|post|put|delete)\(['`]([^'`$]+)", re.I)
    matches = pattern.findall(content)

    registered_paths = set(app.openapi()["paths"].keys())

    # Helper to check if a base route matches any registered path prefix
    for method, path in matches:
        clean_path = "/api" + path.split("?")[0].rstrip("/")
        # Check exact, with slash, or as a path prefix for parameterized routes
        matched = False
        for reg in registered_paths:
            reg_clean = reg.rstrip("/")
            if clean_path == reg_clean or reg_clean.startswith(clean_path):
                matched = True
                break
        assert matched, f"Frontend API call {method.upper()} {clean_path} has no matching registered route in backend!"
