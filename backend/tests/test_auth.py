import os
import sys
import pytest
from datetime import datetime, timezone, timedelta

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from api.auth import create_jwt_token, verify_jwt_token, get_jwt_secret, SentinelAuthMiddleware
from fastapi import FastAPI, Request
from starlette.responses import JSONResponse
from starlette.testclient import TestClient


def test_jwt_generation_and_verification():
    """Verify that create_jwt_token generates a verifiable token."""
    token = create_jwt_token(subject="user_admin", expires_delta_hours=2)
    assert isinstance(token, str)
    assert len(token) > 20

    payload = verify_jwt_token(token)
    assert payload is not None
    assert payload["sub"] == "user_admin"
    assert "exp" in payload
    assert "iat" in payload


def test_jwt_tampered_token_rejected():
    """Verify that an altered token fails verification."""
    token = create_jwt_token(subject="user_admin", expires_delta_hours=2)
    tampered = token[:-4] + "abcd"
    assert verify_jwt_token(tampered) is None


def test_jwt_expired_token_rejected():
    """Verify that an expired token fails verification."""
    # Negative expiry
    token = create_jwt_token(subject="user_admin", expires_delta_hours=-1)
    assert verify_jwt_token(token) is None


def test_auth_middleware_dual_mode():
    """Verify middleware accepts both static master token and signed JWT token."""
    os.environ["SENTINEL_API_TOKEN"] = "master_test_token_123"
    os.environ["SENTINEL_JWT_SECRET"] = "jwt_secret_xyz"

    app = FastAPI()
    app.add_middleware(SentinelAuthMiddleware)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/protected")
    def protected(request: Request):
        return {"user": getattr(request.state, "user", "unknown")}

    client = TestClient(app)

    # 1. Health probe needs no auth
    r_health = client.get("/health")
    assert r_health.status_code == 200

    # 2. Protected endpoint without token returns 401
    r_no_auth = client.get("/api/protected")
    assert r_no_auth.status_code == 401

    # 3. Protected endpoint with invalid token returns 401
    r_bad_auth = client.get("/api/protected", headers={"x-sentinel-token": "wrong_token"})
    assert r_bad_auth.status_code == 401

    # 4. Protected endpoint with static master token passes
    r_static = client.get("/api/protected", headers={"x-sentinel-token": "master_test_token_123"})
    assert r_static.status_code == 200
    assert r_static.json()["user"] == "master_token"

    # 5. Protected endpoint with Bearer authorization header master token passes
    r_bearer_static = client.get("/api/protected", headers={"authorization": "Bearer master_test_token_123"})
    assert r_bearer_static.status_code == 200

    # 6. Protected endpoint with valid signed JWT passes
    jwt_tok = create_jwt_token(subject="alice_dev", expires_delta_hours=1)
    r_jwt = client.get("/api/protected", headers={"authorization": f"Bearer {jwt_tok}"})
    assert r_jwt.status_code == 200
    assert r_jwt.json()["user"] == "alice_dev"
