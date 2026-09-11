import asyncio
import json
import logging
import psutil
import os
from datetime import datetime, timezone
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)
router = APIRouter()


class ConnectionManager:
    def __init__(self):
        self._connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.append(ws)
        logger.info(f"WebSocket connected. Total: {len(self._connections)}")

    def disconnect(self, ws: WebSocket) -> None:
        self._connections.remove(ws)
        logger.info(f"WebSocket disconnected. Total: {len(self._connections)}")

    async def broadcast(self, message: dict) -> None:
        dead = []
        for ws in self._connections:
            try:
                await ws.send_text(json.dumps(message))
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._connections.remove(ws)

    def has_connections(self) -> bool:
        return len(self._connections) > 0


manager = ConnectionManager()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    token = os.getenv("SENTINEL_API_TOKEN", "")
    auth_enabled = bool(token and token != "change_me_generate_a_real_token")
    supplied = websocket.query_params.get("token") or websocket.headers.get("x-sentinel-token")
    if auth_enabled and supplied != token:
        await websocket.close(code=1008)
        return

    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive, client sends pings
            data = await asyncio.wait_for(websocket.receive_text(), timeout=30)
            if data == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
    except (WebSocketDisconnect, asyncio.TimeoutError):
        manager.disconnect(websocket)


async def broadcast_hitl_update(pending: list) -> None:
    await manager.broadcast({"type": "hitl_update", "pending": pending})


async def broadcast_task_update(task_id: str, status: str, payload: dict = None) -> None:
    await manager.broadcast({
        "type": "task_update",
        "task_id": task_id,
        "status": status,
        "payload": payload or {},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


async def broadcast_telemetry(data: dict) -> None:
    await manager.broadcast({"type": "telemetry", **data})


async def telemetry_loop() -> None:
    """Background loop that samples hardware and broadcasts to all connected clients."""
    while True:
        try:
            if manager.has_connections():
                ram = psutil.virtual_memory()
                cpu = psutil.cpu_percent(interval=None)

                gpu_temp = None
                vram_used = None
                vram_total = None
                try:
                    import subprocess
                    result = subprocess.run(
                        ["nvidia-smi", "--query-gpu=temperature.gpu,memory.used,memory.total",
                         "--format=csv,noheader,nounits"],
                        capture_output=True, text=True, timeout=5,
                    )
                    if result.returncode == 0:
                        parts = result.stdout.strip().split(", ")
                        if len(parts) >= 3:
                            gpu_temp = float(parts[0])
                            vram_used = int(parts[1])
                            vram_total = int(parts[2])
                except Exception:
                    pass

                await broadcast_telemetry({
                    "ram_used_mb": ram.used // (1024 * 1024),
                    "ram_total_mb": ram.total // (1024 * 1024),
                    "ram_percent": ram.percent,
                    "cpu_percent": cpu,
                    "gpu_temp_c": gpu_temp,
                    "vram_used_mb": vram_used,
                    "vram_total_mb": vram_total,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
        except Exception as e:
            logger.error(f"Telemetry loop error: {e}")

        await asyncio.sleep(10)
