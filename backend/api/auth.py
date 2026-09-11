import os
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


class SentinelAuthMiddleware(BaseHTTPMiddleware):
    """
    Simple shared-token gate for personal LAN/tunnel use.
    Auth is disabled only when SENTINEL_API_TOKEN is unset or left as the example value.
    """

    def __init__(self, app, token_env: str = "SENTINEL_API_TOKEN"):
        super().__init__(app)
        self.token = os.getenv(token_env, "")
        self.enabled = bool(self.token and self.token != "change_me_generate_a_real_token")

    async def dispatch(self, request: Request, call_next):
        if not self.enabled:
            return await call_next(request)

        path = request.url.path
        if path == "/health":
            return await call_next(request)

        supplied = request.headers.get("x-sentinel-token")
        if not supplied and request.headers.get("authorization", "").startswith("Bearer "):
            supplied = request.headers["authorization"].removeprefix("Bearer ").strip()

        if supplied != self.token:
            return JSONResponse({"detail": "Unauthorized"}, status_code=401)

        return await call_next(request)
