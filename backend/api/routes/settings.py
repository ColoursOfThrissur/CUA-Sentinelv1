import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any
from db.connections import get_knowledge_db, get_operational_db

BACKGROUND_SERVICES = [
    {"id": "improvement_scout",   "label": "Code Improvement Scout",     "description": "Scans projects and generates improvement proposals"},
    {"id": "portfolio_watchdog",  "label": "Portfolio Watchdog",          "description": "Monitors stock prices and triggers alerts"},
    {"id": "project_health_daemon","label": "Project Health Daemon",     "description": "Auto-audits and repairs registered projects"},
    {"id": "gmail_triage",        "label": "Gmail Triage & Sync",         "description": "Scans and categorizes inbox emails"},
    {"id": "discord_bot",         "label": "Discord Bot",                 "description": "2-way Discord remote command integration"},
    {"id": "scheduler_engine",    "label": "Scheduler Engine",            "description": "Reminders and recurring cron jobs"},
    {"id": "eval_harness",        "label": "Weekly Eval Harness",         "description": "Runs golden evaluation suite weekly"},
    {"id": "cache_prune",         "label": "Cache & ChromaDB Pruning",    "description": "Prunes expired result cache and old vector entries"},
]

SERVICES_PREF_KEY = "background_services_enabled"

router = APIRouter()


class PreferenceUpdate(BaseModel):
    value: Any


@router.get("/preferences")
async def get_preferences():
    conn = get_knowledge_db()
    try:
        rows = conn.execute("SELECT pref_key, pref_value FROM user_preferences").fetchall()
        return {r["pref_key"]: json.loads(r["pref_value"]) for r in rows}
    finally:
        conn.close()


@router.put("/preferences/{key}")
async def update_preference(key: str, update: PreferenceUpdate):
    from datetime import datetime, timezone
    conn = get_knowledge_db()
    try:
        conn.execute(
            """
            INSERT INTO user_preferences (pref_key, pref_value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(pref_key) DO UPDATE SET pref_value = excluded.pref_value, updated_at = excluded.updated_at
            """,
            (key, json.dumps(update.value), datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        return {"key": key, "value": update.value}
    finally:
        conn.close()


@router.get("/schedules")
async def get_schedules():
    conn = get_operational_db()
    try:
        rows = conn.execute("SELECT * FROM scheduled_jobs ORDER BY workflow_type").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.post("/schedules/{job_id}/toggle")
async def toggle_schedule(job_id: str):
    from datetime import datetime, timezone
    conn = get_operational_db()
    try:
        row = conn.execute(
            "SELECT is_enabled FROM scheduled_jobs WHERE job_id = ?", (job_id,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "Schedule not found")
        new_state = 0 if row["is_enabled"] else 1
        conn.execute(
            "UPDATE scheduled_jobs SET is_enabled = ?, updated_at = ? WHERE job_id = ?",
            (new_state, datetime.now(timezone.utc).isoformat(), job_id),
        )
        conn.commit()
        return {"job_id": job_id, "is_enabled": bool(new_state)}
    finally:
        conn.close()


@router.get("/system")
async def get_system_state():
    conn = get_operational_db()
    try:
        rows = conn.execute("SELECT key, value FROM system_state").fetchall()
        return {r["key"]: r["value"] for r in rows}
    finally:
        conn.close()


@router.post("/system/safe-mode")
async def toggle_safe_mode(request: dict):
    from datetime import datetime, timezone
    enable = request.get("enable", False)
    conn = get_operational_db()
    try:
        conn.execute(
            "UPDATE system_state SET value = ?, updated_at = ? WHERE key = 'safe_mode'",
            ("true" if enable else "false", datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        return {"safe_mode": enable}
    finally:
        conn.close()


@router.post("/system/emergency-stop")
async def emergency_stop():
    from datetime import datetime, timezone
    try:
        from tools.desktop_tool import abort_desktop_actions
        abort_desktop_actions()
    except Exception:
        pass
    conn = get_operational_db()
    try:
        conn.execute(
            "UPDATE system_state SET value = 'true', updated_at = ? WHERE key = 'emergency_stop'",
            (datetime.now(timezone.utc).isoformat(),),
        )
        conn.commit()
        return {"emergency_stop": True}
    finally:
        conn.close()


@router.post("/system/emergency-stop/reset")
async def reset_emergency_stop():
    from datetime import datetime, timezone
    try:
        from tools.desktop_tool import reset_desktop_abort
        reset_desktop_abort()
    except Exception:
        pass
    conn = get_operational_db()
    try:
        conn.execute(
            "UPDATE system_state SET value = 'false', updated_at = ? WHERE key = 'emergency_stop'",
            (datetime.now(timezone.utc).isoformat(),),
        )
        conn.commit()
        return {"emergency_stop": False}
    finally:
        conn.close()


def _load_services_config(conn) -> dict:
    row = conn.execute(
        "SELECT pref_value FROM user_preferences WHERE pref_key = ?", (SERVICES_PREF_KEY,)
    ).fetchone()
    if row:
        try:
            return json.loads(row["pref_value"])
        except Exception:
            pass
    # Default: all disabled
    return {s["id"]: False for s in BACKGROUND_SERVICES}


@router.get("/background-services")
async def get_background_services():
    conn = get_knowledge_db()
    try:
        enabled_map = _load_services_config(conn)
        return [
            {**s, "enabled": enabled_map.get(s["id"], False)}
            for s in BACKGROUND_SERVICES
        ]
    finally:
        conn.close()


@router.post("/background-services/{service_id}/toggle")
async def toggle_background_service(service_id: str):
    from datetime import datetime, timezone
    if not any(s["id"] == service_id for s in BACKGROUND_SERVICES):
        raise HTTPException(404, "Unknown service")
    conn = get_knowledge_db()
    try:
        enabled_map = _load_services_config(conn)
        enabled_map[service_id] = not enabled_map.get(service_id, False)
        conn.execute(
            """
            INSERT INTO user_preferences (pref_key, pref_value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(pref_key) DO UPDATE SET pref_value = excluded.pref_value, updated_at = excluded.updated_at
            """,
            (SERVICES_PREF_KEY, json.dumps(enabled_map), datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        return {"service_id": service_id, "enabled": enabled_map[service_id]}
    finally:
        conn.close()

