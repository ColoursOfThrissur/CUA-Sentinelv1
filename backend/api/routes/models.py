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
