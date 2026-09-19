import os
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from jose import jwt, JWTError

ALGORITHM = "HS256"


def get_jwt_secret() -> str:
    secret = os.getenv("SENTINEL_JWT_SECRET")
    if not secret or secret == "change_me_generate_a_real_secret":
        secret = os.getenv("SENTINEL_API_TOKEN", "sentinel_internal_session_secret")
    return secret


def create_jwt_token(
    subject: str = "sentinel_user",
    expires_delta_hours: int = 720,
    extra_claims: Optional[Dict[str, Any]] = None,
) -> str:
    """Generates a signed HMAC-SHA256 JWT session token with expiration timestamp."""
    now = datetime.now(timezone.utc)
    expire = now + timedelta(hours=expires_delta_hours)
    payload = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, get_jwt_secret(), algorithm=ALGORITHM)


def verify_jwt_token(token: str) -> Optional[Dict[str, Any]]:
    """Decodes and validates a signed JWT token against the active secret."""
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None


class SentinelAuthMiddleware(BaseHTTPMiddleware):
    """
    Dual-layer authentication gate:
    1. Static master token (SENTINEL_API_TOKEN) for shortcuts, CLI & internal daemons.
    2. Signed JWT session tokens (SENTINEL_JWT_SECRET) with expiration verification.
    """

    def __init__(self, app, token_env: str = "SENTINEL_API_TOKEN"):
        super().__init__(app)
        self.token = os.getenv(token_env, "")
        self.enabled = bool(self.token and self.token != "change_me_generate_a_real_token")

    async def dispatch(self, request: Request, call_next):
        if not self.enabled:
            return await call_next(request)

        path = request.url.path
        # Health probe and auth token exchange are unauthenticated
        if path in ("/health", "/api/auth/token", "/api/auth/login"):
            return await call_next(request)

        supplied = request.headers.get("x-sentinel-token")
        if not supplied and request.headers.get("authorization", "").startswith("Bearer "):
            supplied = request.headers["authorization"].removeprefix("Bearer ").strip()

        if not supplied:
            return JSONResponse({"detail": "Missing authentication token"}, status_code=401)

        # Priority 1: Match against static master token
        if supplied == self.token:
            request.state.user = "master_token"
            return await call_next(request)

        # Priority 2: Match against signed JWT session token
        jwt_payload = verify_jwt_token(supplied)
        if jwt_payload:
            request.state.user = jwt_payload.get("sub", "authenticated_user")
            return await call_next(request)

        return JSONResponse({"detail": "Invalid or expired token"}, status_code=401)
