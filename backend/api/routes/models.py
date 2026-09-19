from fastapi import APIRouter, Request, HTTPException
from db.connections import get_operational_db

router = APIRouter()


@router.get("/")
async def list_models():
    conn = get_operational_db()
    try:
        rows = conn.execute("SELECT * FROM models_registry ORDER BY model_name").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.get("/active")
async def get_active_model(request: Request):
    conn = get_operational_db()
    try:
        row = conn.execute(
            "SELECT model_id, model_name, ollama_tag FROM models_registry WHERE current_state IN ('READY', 'BUSY', 'IDLE') ORDER BY last_loaded_at DESC LIMIT 1"
        ).fetchone()
        if not row:
            # Fallback to enabled model from database
            row = conn.execute(
                "SELECT model_id, model_name, ollama_tag FROM models_registry WHERE is_enabled = 1 LIMIT 1"
            ).fetchone()
        if row:
            return dict(row)
        return {"model_id": "qwen3_14b_q4", "model_name": "Qwen3 14B Q4", "ollama_tag": "qwen3:14b-q4_K_M"}
    finally:
        conn.close()


@router.get("/{model_id}")
async def get_model(model_id: str):
    conn = get_operational_db()
    try:
        row = conn.execute(
            "SELECT * FROM models_registry WHERE model_id = ?", (model_id,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "Model not found")
        return dict(row)
    finally:
        conn.close()


@router.post("/{model_id}/enable")
async def enable_model(model_id: str):
    conn = get_operational_db()
    try:
        conn.execute("UPDATE models_registry SET is_enabled = 1 WHERE model_id = ?", (model_id,))
        conn.commit()
        return {"model_id": model_id, "is_enabled": True}
    finally:
        conn.close()


@router.post("/{model_id}/disable")
async def disable_model(model_id: str):
    conn = get_operational_db()
    try:
        conn.execute("UPDATE models_registry SET is_enabled = 0 WHERE model_id = ?", (model_id,))
        conn.commit()
        return {"model_id": model_id, "is_enabled": False}
    finally:
        conn.close()
