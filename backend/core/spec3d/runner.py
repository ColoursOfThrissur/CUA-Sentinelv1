"""Headless Blender Runner for 3D Verification.

Executes compiled scripts in a headless Blender instance (blender -b),
saving verified .blend files and exchanging measurements via JSON files.

v3 changes:
- --factory-startup added: disables all user addons and preferences.
- 60s timeout (up from 35s).
- Explicit process.kill() + await process.wait() on timeout.
- Software silhouette projection: numpy triangle projection onto 3 ortho planes,
  rasterised to 256x256 PNG via Pillow, saved alongside metrics JSON.
  Falls back gracefully if numpy/Pillow not available.
"""

import os
import sys
import json
import asyncio
import tempfile
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)

DEFAULT_BLENDER_PATH = os.environ.get(
    "BLENDER_EXECUTABLE_PATH",
    r"C:\Program Files\Blender Foundation\Blender 4.5\blender.exe",
)

# Silhouette raster size (pixels)
SILHOUETTE_SIZE = 256


# ---------------------------------------------------------------------------
# Software silhouette generation (pure Python, runs in THIS process after
# the headless build returns the .blend — no GPU or Workbench needed).
# ---------------------------------------------------------------------------

def _generate_silhouettes(metrics: Dict[str, Any], blend_path: str, out_dir: str) -> Dict[str, str]:
    """
    Load mesh data from the metrics dict (world-space vertex list + poly indices)
    and rasterise binary silhouette images for 3 ortho planes.

    Returns a dict of {plane: png_path} or {} if unavailable.
    """
    try:
        import numpy as np
        from PIL import Image, ImageDraw
    except ImportError:
        logger.debug("numpy/Pillow not available — skipping silhouette generation")
        return {}

    world_verts = metrics.get("world_verts")  # List of [x, y, z]
    polys = metrics.get("polys")              # List of [i0, i1, i2, ...]

    if not world_verts or not polys:
        return {}

    try:
        verts = np.array(world_verts, dtype=np.float32)  # (N, 3)
    except Exception:
        return {}

    def _rasterise(axis0: int, axis1: int, label: str) -> Optional[str]:
        """Project triangles onto the plane defined by axis0, axis1 and rasterise."""
        try:
            pts = verts[:, [axis0, axis1]]
            mn, mx = pts.min(axis=0), pts.max(axis=0)
            span = mx - mn
            if span.min() < 1e-6:
                return None

            scale = (SILHOUETTE_SIZE - 4) / span
            offset = -mn * scale + 2

            img = Image.new("L", (SILHOUETTE_SIZE, SILHOUETTE_SIZE), 0)
            draw = ImageDraw.Draw(img)

            for poly in polys:
                if len(poly) < 3:
                    continue
                # Fan-triangulate
                for i in range(1, len(poly) - 1):
                    tri_idx = [poly[0], poly[i], poly[i + 1]]
                    coords = []
                    for idx in tri_idx:
                        if idx >= len(pts):
                            break
                        px = int(pts[idx, 0] * scale[0] + offset[0])
                        py = int(SILHOUETTE_SIZE - (pts[idx, 1] * scale[1] + offset[1]))
                        coords.append((px, py))
                    if len(coords) == 3:
                        draw.polygon(coords, fill=255)

            png_path = os.path.join(out_dir, f"silhouette_{label}.png")
            img.save(png_path)
            return png_path
        except Exception as e:
            logger.debug(f"Silhouette rasterisation failed for {label}: {e}")
            return None

    paths: Dict[str, str] = {}
    for ax0, ax1, lbl in ((1, 2, "front_XZ"), (0, 2, "side_YZ"), (0, 1, "top_XY")):
        p = _rasterise(ax0, ax1, lbl)
        if p:
            paths[lbl] = p

    return paths


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

class HeadlessBlenderRunner:

    def __init__(self, blender_bin: Optional[str] = None):
        self.blender_bin = blender_bin or DEFAULT_BLENDER_PATH
        if not Path(self.blender_bin).is_file():
            import shutil
            which = shutil.which("blender")
            if which:
                self.blender_bin = which

    async def build_and_verify(
        self,
        script_code: str,
        timeout_seconds: int = 60,
    ) -> Tuple[bool, Dict[str, Any], str]:
        """
        Execute the compiled script in headless Blender.

        Returns:
            (success, metrics_dict, blend_file_path)
        """
        if not Path(self.blender_bin).is_file():
            err = f"Blender executable not found at: {self.blender_bin}"
            logger.error(err)
            return False, {"error": err}, ""

        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as sf:
            script_path = sf.name
            sf.write(script_code)

        temp_dir = tempfile.gettempdir()
        uid = f"{os.getpid()}_{id(script_code)}"
        blend_path = os.path.join(temp_dir, f"sentinel_verified_{uid}.blend")
        metrics_path = os.path.join(temp_dir, f"sentinel_metrics_{uid}.json")

        cmd = [
            self.blender_bin,
            "-b",
            "--factory-startup",
            "--python-exit-code", "1",
            "--python", script_path,
            "--",
            "--out-blend", blend_path,
            "--out-json", metrics_path,
        ]

        logger.info(f"Running headless Blender build (timeout={timeout_seconds}s): {self.blender_bin}")
        process = None

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout_seconds,
                )
            except asyncio.TimeoutError:
                logger.error(f"Headless Blender timed out after {timeout_seconds}s — killing process")
                try:
                    process.kill()
                    await process.wait()
                except Exception:
                    pass
                return False, {"error": f"Build timed out after {timeout_seconds}s"}, ""

            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")

            if process.returncode != 0:
                logger.error(f"Blender exit code {process.returncode}: {stderr[-300:]}")
                return False, {
                    "error": f"Blender exit code {process.returncode}",
                    "stderr": stderr[-800:],
                }, ""

            # Read metrics JSON
            metrics: Dict[str, Any] = {}
            if os.path.isfile(metrics_path):
                with open(metrics_path, "r", encoding="utf-8") as f:
                    metrics = json.load(f)
            else:
                # Try parsing SENTINEL_OUTPUT_START marker from stdout
                tag_s = "SENTINEL_OUTPUT_START"
                tag_e = "SENTINEL_OUTPUT_END"
                if tag_s in stdout:
                    try:
                        raw = stdout[stdout.index(tag_s) + len(tag_s): stdout.index(tag_e)]
                        metrics = json.loads(raw)
                    except Exception:
                        metrics = {"ok": True, "note": "parsed from stdout"}

            if not os.path.isfile(blend_path):
                return False, {"error": "Blender did not output a .blend file", "stderr": stderr[-400:]}, ""

            # Software silhouette projection
            sil_dir = os.path.join(temp_dir, f"sentinel_silhouettes_{uid}")
            os.makedirs(sil_dir, exist_ok=True)
            silhouette_paths = _generate_silhouettes(metrics, blend_path, sil_dir)
            if silhouette_paths:
                metrics["silhouettes"] = silhouette_paths

            return True, metrics, blend_path

        except Exception as e:
            logger.error(f"Failed to execute headless Blender: {repr(e)}")
            if process:
                try:
                    process.kill()
                    await process.wait()
                except Exception:
                    pass
            # Sync fallback: asyncio.create_subprocess_exec can silently fail on some
            # Windows configurations (e.g. ProactorEventLoop not fully initialised).
            # Try subprocess.run as a last resort so we at least get stderr output.
            try:
                import subprocess
                logger.info("Retrying headless Blender build via subprocess.run fallback")
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout_seconds,
                )
                if result.returncode == 0:
                    metrics: Dict[str, Any] = {}
                    if os.path.isfile(metrics_path):
                        with open(metrics_path, "r", encoding="utf-8") as f:
                            metrics = json.load(f)
                    if os.path.isfile(blend_path):
                        return True, metrics, blend_path
                    return False, {"error": "Blender did not output a .blend file", "stderr": result.stderr[-400:]}, ""
                logger.error(f"Blender subprocess fallback exit {result.returncode}: {result.stderr[-300:]}")
                return False, {"error": f"Blender exit code {result.returncode}", "stderr": result.stderr[-800:]}, ""
            except subprocess.TimeoutExpired:
                return False, {"error": f"Build timed out after {timeout_seconds}s (sync fallback)"}, ""
            except Exception as e2:
                logger.error(f"Blender subprocess fallback also failed: {repr(e2)}")
                return False, {"error": f"Headless Blender failed: {repr(e)} / fallback: {repr(e2)}"}, ""

        finally:
            if os.path.exists(script_path):
                try:
                    os.remove(script_path)
                except Exception:
                    pass
            if os.path.exists(metrics_path):
                try:
                    os.remove(metrics_path)
                except Exception:
                    pass
