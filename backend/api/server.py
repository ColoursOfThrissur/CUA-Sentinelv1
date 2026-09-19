import logging
import re
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

import sys

def _middleware_smart_iter(self):
    try:
        frame = sys._getframe(1)
        code = frame.f_code.co_code
        lasti = frame.f_lasti
        oparg = code[lasti + 1] if lasti < len(code) - 1 else 3
        if oparg == 2:
            return iter((self.cls, self.kwargs))
    except Exception:
        pass
    return iter((self.cls, self.args, self.kwargs))

Middleware.__iter__ = _middleware_smart_iter

from api.routes import tasks, chat, models, telemetry, hitl, settings, finance, links, notifications, scheduler, digests, gmail_triage, code_refactor, projects, improvements
from api.websocket import router as ws_router
from config.loader import load_system_config
from api.auth import SentinelAuthMiddleware

logger = logging.getLogger(__name__)


def create_app(lifespan) -> FastAPI:
    config = load_system_config()

    # Disable automatic redirecting for trailing slashes to avoid 307 responses
    app = FastAPI(
        title="CUA-Sentinel",
        description="Personal 24/7 AI backend",
        version="1.0.0",
        lifespan=lifespan,
        redirect_slashes=True,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(SentinelAuthMiddleware)

    app.include_router(tasks.router, prefix="/api/tasks", tags=["tasks"])
    app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
    app.include_router(models.router, prefix="/api/models", tags=["models"])
    app.include_router(telemetry.router, prefix="/api/telemetry", tags=["telemetry"])
    app.include_router(hitl.router, prefix="/api/hitl", tags=["hitl"])
    app.include_router(settings.router, prefix="/api/settings", tags=["settings"])
    app.include_router(finance.router)
    app.include_router(links.router)
    app.include_router(notifications.router)
    app.include_router(scheduler.router, prefix="/api/scheduler", tags=["scheduler"])
    app.include_router(digests.router, prefix="/api/digests", tags=["digests"])
    app.include_router(gmail_triage.router)
    app.include_router(code_refactor.router, prefix="/api/code-refactor", tags=["code_refactor"])
    app.include_router(projects.router, prefix="/api/projects", tags=["projects"])
    app.include_router(improvements.router, prefix="/api/improvements", tags=["improvements"])
    app.include_router(ws_router)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    # Serve built frontend static assets
    dist = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist"))
    if os.path.isdir(dist):
        app.mount("/assets", StaticFiles(directory=os.path.join(dist, "assets")), name="assets")

        # Serve other static files (sw.js, manifest, icons etc)
        @app.get("/{full_path:path}", include_in_schema=False)
        async def spa_fallback(full_path: str):
            # Try to serve exact file first
            file_path = os.path.join(dist, full_path)
            if os.path.isfile(file_path):
                return FileResponse(file_path)
            # Fall back to index.html for SPA routing
            return FileResponse(os.path.join(dist, "index.html"))

    return app
