import os
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
try:
    from jose import jwt, JWTError
except ImportError:
    import jwt
    from jwt.exceptions import PyJWTError as JWTError

ALGORITHM = "HS256"


def get_jwt_secret() -> str:
    secret = os.getenv("SENTINEL_JWT_SECRET")
    if not secret or secret == "change_me_generate_a_real_secret":
        secret = os.getenv("SENTINEL_API_TOKEN", "sentinel_internal_session_secret")
    return secret


def _get_token_version() -> int:
    """
    Read the current token version from operational DB.
    All JWTs must carry a matching 'ver' claim; a mismatch invalidates the token.
    Incrementing this (via /api/auth/revoke-all) instantly revokes every issued JWT.
    Returns 1 on any DB error (safe default).
    """
    try:
        from db.connections import get_operational_db
        conn = get_operational_db()
        try:
            row = conn.execute(
                "SELECT value FROM system_state WHERE key = 'jwt_token_version'"
            ).fetchone()
            return int(row["value"]) if row else 1
        finally:
            conn.close()
    except Exception:
        return 1


def create_jwt_token(
    subject: str = "sentinel_user",
    expires_delta_hours: int = 720,
    extra_claims: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Generates a signed HMAC-SHA256 JWT session token with expiration timestamp.
    Embeds the current token version so revoke-all immediately invalidates it.
    """
    now = datetime.now(timezone.utc)
    expire = now + timedelta(hours=expires_delta_hours)
    payload = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "ver": _get_token_version(),  # revocation version stamp
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, get_jwt_secret(), algorithm=ALGORITHM)


def verify_jwt_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Decodes and validates a signed JWT token.
    Rejects tokens whose 'ver' claim doesn't match the current DB version.
    """
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=[ALGORITHM])
        # Version check — mismatch means all tokens were revoked
        token_ver = payload.get("ver", 1)
        current_ver = _get_token_version()
        if token_ver != current_ver:
            return None
        return payload
    except JWTError:
        return None


def revoke_all_tokens() -> bool:
    """
    Increment the token version in the DB.
    Every existing JWT immediately becomes invalid on next request.
    """
    try:
        from db.connections import get_operational_db
        conn = get_operational_db()
        try:
            # Upsert and increment
            conn.execute("""
                INSERT INTO system_state (key, value, updated_at)
                VALUES ('jwt_token_version', '2', datetime('now'))
                ON CONFLICT(key) DO UPDATE SET
                    value = CAST(CAST(value AS INTEGER) + 1 AS TEXT),
                    updated_at = datetime('now')
            """)
            conn.commit()
            return True
        finally:
            conn.close()
    except Exception:
        return False


class SentinelAuthMiddleware(BaseHTTPMiddleware):
    """
    Dual-layer authentication gate:
    1. Static master token (SENTINEL_API_TOKEN) for shortcuts, CLI & internal daemons.
    2. Signed JWT session tokens (SENTINEL_JWT_SECRET) with expiration + version check.
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

        # WebSocket upgrades pass token as query param — handled in the WS handler itself
        if request.headers.get("upgrade", "").lower() == "websocket":
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

        # Priority 2: Match against signed JWT session token (includes version check)
        jwt_payload = verify_jwt_token(supplied)
        if jwt_payload:
            request.state.user = jwt_payload.get("sub", "authenticated_user")
            return await call_next(request)

        return JSONResponse({"detail": "Invalid or expired token"}, status_code=401)
