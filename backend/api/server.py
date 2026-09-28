import logging
import os
import re
import uuid
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from api.routes import tasks, chat, models, telemetry, hitl, settings, finance, links, notifications, scheduler, digests, gmail_triage, code_refactor, projects, improvements, auth, research, apps, dependency_plans, blender
from api.websocket import router as ws_router
from config.loader import load_system_config
from api.auth import SentinelAuthMiddleware
from core.logging_context import bind_log_context
from db.connections import get_operational_db, get_audit_db, get_knowledge_db

logger = logging.getLogger(__name__)


def create_app(lifespan) -> FastAPI:
    config = load_system_config()
    configured_origins = config["api"].get("cors_origins", [])
    exact_origins = [origin for origin in configured_origins if "*" not in origin]
    wildcard_origins = [origin for origin in configured_origins if "*" in origin]

    # Starlette accepts a regular expression for the small set of dynamic origins
    # (for example, a temporary Cloudflare tunnel) while keeping known local
    # origins explicit. Do not use a global '*' origin with credentials.
    allow_origin_regex = None
    if wildcard_origins:
        allow_origin_regex = "|".join(
            "^" + re.escape(origin).replace(r"\*", ".*") + "$"
            for origin in wildcard_origins
        )

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
        allow_origins=exact_origins,
        allow_origin_regex=allow_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(SentinelAuthMiddleware)

    app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
    app.include_router(research.router, prefix="/api/research", tags=["research"])
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
    app.include_router(apps.router, prefix="/api/apps", tags=["apps"])
    app.include_router(blender.router, prefix="/api/blender", tags=["blender"])
    app.include_router(dependency_plans.router, prefix="/api/dependency-plans", tags=["dependency_plans"])
    app.include_router(ws_router)

    @app.middleware("http")
    async def correlation_middleware(request: Request, call_next):
        corr_id = request.headers.get("x-correlation-id") or f"corr_{uuid.uuid4().hex[:12]}"
        with bind_log_context(correlation_id=corr_id):
            response = await call_next(request)
            response.headers["x-correlation-id"] = corr_id
            return response

    @app.get("/health")
    @app.get("/api/health")
    async def health():
        return {"status": "ok"}

    _cached_ready_payload = None
    _cached_ready_time = 0.0
    _ready_cache_ttl = 5.0  # seconds

    @app.get("/health/ready")
    @app.get("/api/health/ready")
    async def health_ready():
        """Verifies configuration, database connectivity, and model runtime reachability (cached 5s TTL)."""
        nonlocal _cached_ready_payload, _cached_ready_time
        import time
        now = time.monotonic()
        if _cached_ready_payload is not None and (now - _cached_ready_time) < _ready_cache_ttl:
            status_code = 200 if _cached_ready_payload.get("status") == "ready" else 503
            return JSONResponse(status_code=status_code, content=_cached_ready_payload)

        config_ok = False
        try:
            cfg = load_system_config()
            config_ok = bool(cfg and "api" in cfg)
        except Exception as e:
            logger.warning(f"Health ready: config check failed: {e}")

        db_status = {}
        for db_name, getter in [
            ("operational", get_operational_db),
            ("audit", get_audit_db),
            ("knowledge", get_knowledge_db),
        ]:
            try:
                conn = getter()
                conn.execute("SELECT 1")
                conn.close()
                db_status[db_name] = "ok"
            except Exception as e:
                db_status[db_name] = f"error: {e}"

        all_dbs_ok = all(v == "ok" for v in db_status.values())

        model_runtime = "unknown"
        try:
            import urllib.request
            cfg = load_system_config()
            ollama_url = cfg.get("models", {}).get("ollama_url", "http://localhost:11434")
            req = urllib.request.Request(f"{ollama_url.rstrip('/')}/api/version", method="GET")
            with urllib.request.urlopen(req, timeout=0.8) as resp:
                if resp.status == 200:
                    model_runtime = "reachable"
        except Exception:
            model_runtime = "unreachable"

        ready = config_ok and all_dbs_ok
        status_code = 200 if ready else 503
        payload = {
            "status": "ready" if ready else "not_ready",
            "config": "ok" if config_ok else "error",
            "databases": db_status,
            "model_runtime": model_runtime,
            "version": app.version,
        }
        _cached_ready_payload = payload
        _cached_ready_time = now
        return JSONResponse(status_code=status_code, content=payload)

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
