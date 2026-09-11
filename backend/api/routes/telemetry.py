from fastapi import APIRouter
from db.connections import get_audit_db

router = APIRouter()


@router.get("/hardware")
async def hardware_snapshot():
    import psutil
    ram = psutil.virtual_memory()
    cpu = psutil.cpu_percent(interval=0.1)
    gpu_temp, vram_used, vram_total = None, None, None
    try:
        import subprocess
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=temperature.gpu,memory.used,memory.total",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0:
            parts = r.stdout.strip().split(", ")
            if len(parts) >= 3:
                gpu_temp = float(parts[0])
                vram_used = int(parts[1])
                vram_total = int(parts[2])
    except Exception:
        pass
    return {
        "ram_used_mb": ram.used // (1024 * 1024),
        "ram_total_mb": ram.total // (1024 * 1024),
        "ram_percent": ram.percent,
        "cpu_percent": cpu,
        "gpu_temp_c": gpu_temp,
        "vram_used_mb": vram_used,
        "vram_total_mb": vram_total,
    }


@router.get("/history")
async def telemetry_history(hours: int = 24):
    conn = get_audit_db()
    try:
        rows = conn.execute(
            """
            SELECT bucket_hour, gpu_temp_avg, gpu_temp_max,
                   vram_avg_mb, vram_max_mb, ram_avg_mb, tokens_in_total, tokens_out_total
            FROM telemetry_hourly
            ORDER BY bucket_hour DESC LIMIT ?
            """,
            (hours,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
