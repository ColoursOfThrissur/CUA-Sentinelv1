import base64
import io
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import concurrent.futures
import threading

logger = logging.getLogger(__name__)

NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.\-]{0,80}$")
RESERVED_DOS_NAMES = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}
ALLOWED_EXTENSIONS = {".txt", ".md"}
MAX_FILE_BYTES = 100_000
ALLOWED_APPS = {
    "notepad": "notepad.exe",
    "notepad.exe": "notepad.exe",
    "explorer": "explorer.exe",
    "explorer.exe": "explorer.exe",
}

try:
    from PIL import ImageGrab, Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    import pyautogui
    pyautogui.FAILSAFE = True
    PYAUTOGUI_AVAILABLE = True
except Exception:
    PYAUTOGUI_AVAILABLE = False

# Single-worker pool serializes all physical mouse and keyboard actions
ACT_POOL = concurrent.futures.ThreadPoolExecutor(max_workers=1)
DESKTOP_LOCK = threading.Lock()
DESKTOP_ABORT_EVENT = threading.Event()

def abort_desktop_actions() -> None:
    """Triggered by Emergency Stop to halt running typing actions between chunks."""
    DESKTOP_ABORT_EVENT.set()

def reset_desktop_abort() -> None:
    """Reset abort flag when Emergency Stop is lifted."""
    DESKTOP_ABORT_EVENT.clear()



class DesktopTool:
    """
    Computer Use Agent (CUA) Desktop Automation Tool (BP05 Adapter).
    Handles compressed screen capture, desktop UI element inspection, screenshot cleanup, mouse clicks, and key presses.
    Optimized for local 12GB VRAM + single-model Ollama execution.
    """

    def take_screenshot(self, max_width: int = 1280, quality: int = 80) -> Dict[str, Any]:
        """
        Captures desktop screenshot, resizes to max_width, compresses to JPEG for zero-bloat storage.
        """
        if PIL_AVAILABLE:
            try:
                img = ImageGrab.grab()
                orig_width, orig_height = img.width, img.height

                # Downscale for VRAM / storage efficiency if larger than max_width
                if orig_width > max_width:
                    scale = max_width / float(orig_width)
                    new_height = int(float(orig_height) * scale)
                    img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)

                buffer = io.BytesIO()
                # Convert RGBA to RGB for JPEG compression
                if img.mode != "RGB":
                    img = img.convert("RGB")
                img.save(buffer, format="JPEG", quality=quality, optimize=True)
                b64_str = base64.b64encode(buffer.getvalue()).decode("utf-8")

                return {
                    "status": "SUCCESS",
                    "width": orig_width,
                    "height": orig_height,
                    "scaled_width": img.width,
                    "scaled_height": img.height,
                    "format": "JPEG",
                    "size_kb": round(len(b64_str) * 0.75 / 1024, 2),
                    "image_b64": b64_str[:100] + "...[compressed]",
                    "full_b64": b64_str,
                }
            except Exception as e:
                logger.error(f"Error grabbing screen with PIL: {e}")
                return {
                    "status": "FAILED",
                    "error": f"Failed to capture screen: {e}",
                    "note": "Screen capture threw an exception",
                }

        return {
            "status": "FAILED",
            "error": "PIL/Pillow library not available",
            "note": "Install Pillow package to enable desktop screenshot capture",
        }

    def get_active_window(self) -> Dict[str, Any]:
        """
        Retrieves active window title and inspects child UI controls (buttons, text inputs, handles).
        """
        title = "Desktop Environment"
        controls = []
        if sys.platform == "win32":
            try:
                import win32gui
                hwnd = win32gui.GetForegroundWindow()
                title = win32gui.GetWindowText(hwnd) or "Windows Desktop"

                # Enumerate child windows/controls to locate clickable elements without Vision model overhead
                def enum_child_callback(child_hwnd, extra):
                    if win32gui.IsWindowVisible(child_hwnd):
                        c_title = win32gui.GetWindowText(child_hwnd).strip()
                        c_class = win32gui.GetClassName(child_hwnd)
                        rect = win32gui.GetWindowRect(child_hwnd)
                        left, top, right, bottom = rect
                        w = right - left
                        h = bottom - top
                        if (c_title or c_class in ["Button", "Edit", "Static", "ToolbarWindow32"]) and w > 10 and h > 10:
                            cx = left + w // 2
                            cy = top + h // 2
                            controls.append({
                                "text": c_title,
                                "class": c_class,
                                "bounds": [left, top, right, bottom],
                                "center": [cx, cy]
                            })
                    return True

                win32gui.EnumChildWindows(hwnd, enum_child_callback, None)
            except Exception as e:
                logger.debug(f"win32gui control enumeration notice: {e}")

        return {"title": title, "os": sys.platform, "controls": controls[:15]}

    def cleanup_old_screenshots(self, db_conn=None, keep_count: int = 20) -> int:
        """
        Prunes old screenshot artifacts in SQLite database to prevent storage accumulation.
        Retains only the latest `keep_count` screenshot artifacts.
        """
        own_conn = False
        if db_conn is None:
            from db.connections import get_operational_db
            db_conn = get_operational_db()
            own_conn = True

        try:
            cursor = db_conn.cursor()
            # Select IDs of screenshot artifacts beyond keep_count
            cursor.execute("""
                DELETE FROM artifacts 
                WHERE artifact_type = 'SCREENSHOT' 
                AND artifact_id NOT IN (
                    SELECT artifact_id FROM artifacts 
                    WHERE artifact_type = 'SCREENSHOT' 
                    ORDER BY created_at DESC 
                    LIMIT ?
                )
            """, (keep_count,))
            deleted_count = cursor.rowcount
            db_conn.commit()
            if deleted_count > 0:
                logger.info(f"Pruned {deleted_count} old screenshot artifacts from database.")
            return deleted_count
        except Exception as e:
            logger.error(f"Error cleaning up screenshot artifacts: {e}")
            return 0
        finally:
            if own_conn and db_conn:
                db_conn.close()

    def get_active_process_name(self) -> str:
        """
        Returns lowercased executable name of the active foreground window process.
        Uses win32process and psutil to avoid spoofable window title checks.
        """
        if sys.platform != "win32":
            return ""
        try:
            import win32gui
            import win32process
            import psutil
            hwnd = win32gui.GetForegroundWindow()
            if not hwnd:
                return ""
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if pid <= 0:
                return ""
            proc = psutil.Process(pid)
            try:
                exe_name = Path(proc.exe()).name.lower()
            except Exception:
                exe_name = proc.name().lower()
            return exe_name
        except Exception as e:
            logger.debug(f"Failed to inspect active process: {e}")
            return ""

    def click_coordinate(self, x: int, y: int) -> Dict[str, Any]:
        """
        Executes mouse click at (x, y) coordinates.
        Requires L3 HITL Governance check before execution.
        Restricted to allowed processes (notepad.exe, explorer.exe).
        """
        if DESKTOP_ABORT_EVENT.is_set():
            return {"status": "ABORTED", "action": "CLICK", "x": x, "y": y, "error": "Desktop action aborted by emergency stop"}

        # Reject invalid coordinates before inspecting or interacting with the
        # active application. This makes the validation deterministic and avoids
        # any desktop-side work for malformed requests.
        if PYAUTOGUI_AVAILABLE:
            try:
                screen_w, screen_h = pyautogui.size()
            except Exception as e:
                logger.error(f"PyAutoGUI screen-size error: {e}")
                return {"status": "FAILED", "action": "CLICK", "x": x, "y": y, "error": str(e)}
            if x < 0 or y < 0 or x >= screen_w or y >= screen_h:
                return {
                    "status": "FAILED",
                    "action": "CLICK",
                    "x": x,
                    "y": y,
                    "error": f"Coordinates ({x}, {y}) out of screen bounds ({screen_w}x{screen_h})",
                }

        if sys.platform == "win32":
            active_proc = self.get_active_process_name()
            if active_proc and active_proc not in ("notepad.exe", "explorer.exe"):
                return {
                    "status": "FAILED",
                    "action": "CLICK",
                    "x": x,
                    "y": y,
                    "error": f"Target process '{active_proc}' is not allowed for clicks (only notepad.exe and explorer.exe permitted)"
                }

        if PYAUTOGUI_AVAILABLE:
            try:
                with DESKTOP_LOCK:
                    pyautogui.click(x=x, y=y)
                return {"status": "SUCCESS", "action": "CLICK", "x": x, "y": y}
            except Exception as e:
                logger.error(f"PyAutoGUI click error: {e}")
                return {"status": "FAILED", "action": "CLICK", "x": x, "y": y, "error": str(e)}

        return {
            "status": "FAILED",
            "action": "CLICK",
            "x": x,
            "y": y,
            "error": "PyAutoGUI library not available",
            "note": "Install pyautogui package to enable desktop interaction",
        }

    def type_text(self, text: str) -> Dict[str, Any]:
        """
        Types keyboard text sequence in chunks with abort checks.
        Raw input text is scrubbed from return output to prevent secret leakage.
        Restricted to allowed typing processes (notepad.exe).
        """
        if DESKTOP_ABORT_EVENT.is_set():
            return {"status": "ABORTED", "action": "TYPE", "chars_typed": 0, "error": "Desktop action aborted by emergency stop"}

        if sys.platform == "win32":
            active_proc = self.get_active_process_name()
            if active_proc and active_proc != "notepad.exe":
                return {
                    "status": "FAILED",
                    "action": "TYPE",
                    "chars_typed": 0,
                    "error": f"Target process '{active_proc}' is not allowed for typing (only notepad.exe permitted)"
                }

        capped_text = str(text)[:500]
        if PYAUTOGUI_AVAILABLE:
            try:
                chunk_size = 20
                typed_count = 0
                with DESKTOP_LOCK:
                    for i in range(0, len(capped_text), chunk_size):
                        if DESKTOP_ABORT_EVENT.is_set():
                            return {
                                "status": "ABORTED",
                                "action": "TYPE",
                                "chars_typed": typed_count,
                                "error": "Desktop action aborted by emergency stop",
                            }
                        chunk = capped_text[i : i + chunk_size]
                        pyautogui.write(chunk, interval=0.05)
                        typed_count += len(chunk)

                return {"status": "SUCCESS", "action": "TYPE", "chars_typed": typed_count}
            except Exception as e:
                logger.error(f"PyAutoGUI type error: {e}")
                return {"status": "FAILED", "action": "TYPE", "chars_typed": 0, "error": str(e)}

        return {
            "status": "FAILED",
            "action": "TYPE",
            "chars_typed": 0,
            "error": "PyAutoGUI library not available",
            "note": "Install pyautogui package to enable desktop interaction",
        }

    def app_launch(self, app_name: str) -> Dict[str, Any]:
        """
        Launches an approved application executable.
        Requires L3 HITL Governance check before execution.
        Enforces strict binary allowlist without shell execution.
        """
        if DESKTOP_ABORT_EVENT.is_set():
            return {"status": "ABORTED", "action": "APP_LAUNCH", "app": app_name, "error": "Desktop action aborted by emergency stop"}

        cleaned_name = (app_name or "").strip().lower()
        if cleaned_name not in ALLOWED_APPS:
            return {
                "status": "FAILED",
                "action": "APP_LAUNCH",
                "app": app_name,
                "error": f"Application '{app_name}' is not in the allowed list: {list(ALLOWED_APPS.keys())}"
            }

        exe_to_launch = ALLOWED_APPS[cleaned_name]
        try:
            import subprocess
            subprocess.Popen([exe_to_launch], shell=False)
            return {"status": "SUCCESS", "action": "APP_LAUNCH", "app": exe_to_launch}
        except Exception as e:
            logger.error(f"Failed to launch app '{app_name}': {e}")
            return {"status": "FAILED", "action": "APP_LAUNCH", "app": app_name, "error": str(e)}

    def desktop_file_write(self, filename: str, content: str = "", overwrite: bool = False) -> Dict[str, Any]:
        """
        Direct, validated Desktop file creator.
        Safely writes text or markdown files to the user's Desktop directory with
        strict path-traversal, DOS reserved names, extension, and size checks.
        """
        if DESKTOP_ABORT_EVENT.is_set():
            return {"status": "ABORTED", "action": "FILE_WRITE", "error": "Desktop action aborted by emergency stop"}

        if not filename or not isinstance(filename, str):
            return {"status": "FAILED", "action": "FILE_WRITE", "error": "Filename is required and must be a string"}

        clean_filename = filename.strip()
        if not NAME_RE.match(clean_filename):
            return {
                "status": "FAILED",
                "action": "FILE_WRITE",
                "error": f"Filename '{clean_filename}' contains invalid characters or exceeds 80 characters"
            }

        desktop_dir = Path(os.environ.get("SENTINEL_DESKTOP_DIR", Path.home() / "Desktop")).resolve()
        target_path = (desktop_dir / clean_filename).resolve()

        # Symlink / Junction / Path traversal escape check
        if target_path.parent != desktop_dir:
            return {
                "status": "FAILED",
                "action": "FILE_WRITE",
                "error": "Path traversal detected: target is outside Desktop directory"
            }

        # Extension allowlist
        if target_path.suffix.lower() not in ALLOWED_EXTENSIONS:
            return {
                "status": "FAILED",
                "action": "FILE_WRITE",
                "error": f"Extension '{target_path.suffix}' not allowed (must be .txt or .md)"
            }

        # DOS reserved device names check
        base_stem = target_path.stem.lower()
        if base_stem in RESERVED_DOS_NAMES:
            return {
                "status": "FAILED",
                "action": "FILE_WRITE",
                "error": f"Filename '{clean_filename}' uses a reserved DOS device name ({base_stem})"
            }

        # Max size check (100 KB)
        content_bytes = (content or "").encode("utf-8")
        if len(content_bytes) > MAX_FILE_BYTES:
            return {
                "status": "FAILED",
                "action": "FILE_WRITE",
                "error": f"Content size ({len(content_bytes)} bytes) exceeds maximum limit of {MAX_FILE_BYTES} bytes"
            }

        # Write mode: exclusive ('x') by default, or overwrite ('w') if requested
        mode = "w" if overwrite else "x"
        try:
            desktop_dir.mkdir(parents=True, exist_ok=True)
            with open(target_path, mode, encoding="utf-8", newline="") as f:
                f.write(content or "")
            logger.info(f"Successfully wrote desktop file: {target_path} ({len(content_bytes)} bytes)")
            return {
                "status": "SUCCESS",
                "action": "FILE_WRITE",
                "filename": clean_filename,
                "path": str(target_path),
                "bytes_written": len(content_bytes)
            }
        except FileExistsError:
            return {
                "status": "FAILED",
                "action": "FILE_WRITE",
                "error": f"File '{clean_filename}' already exists on Desktop."
            }
        except Exception as e:
            logger.error(f"Failed writing desktop file: {e}")
            return {
                "status": "FAILED",
                "action": "FILE_WRITE",
                "error": str(e)
            }

    # Aliases matching registry tool names
    desktop_click = click_coordinate
    desktop_type = type_text

    _session_read_files: set = set()

    def desktop_file_read(self, filename: str) -> Dict[str, Any]:
        """
        Read a desktop file safely and track it in session memory.
        Enforces read-before-write invariants.
        """
        if not filename or not isinstance(filename, str):
            return {"status": "FAILED", "action": "FILE_READ", "error": "Filename is required"}

        clean_filename = filename.strip()
        desktop_dir = Path(os.environ.get("SENTINEL_DESKTOP_DIR", Path.home() / "Desktop")).resolve()
        target_path = (desktop_dir / clean_filename).resolve()

        if target_path.parent != desktop_dir:
            return {"status": "FAILED", "action": "FILE_READ", "error": "Path traversal detected"}

        if not target_path.exists():
            return {"status": "FAILED", "action": "FILE_READ", "error": f"File '{clean_filename}' does not exist"}

        try:
            content = target_path.read_text(encoding="utf-8")
            DesktopTool._session_read_files.add(str(target_path))
            try:
                from core.code_diff_engine import code_diff_engine
                code_diff_engine.record_file_read(str(target_path))
            except Exception:
                pass
            return {
                "status": "SUCCESS",
                "action": "FILE_READ",
                "filename": clean_filename,
                "content": content,
                "bytes": len(content.encode("utf-8")),
            }
        except Exception as e:
            return {"status": "FAILED", "action": "FILE_READ", "error": str(e)}

    def surgical_edit_file(
        self,
        filename: str,
        old_string: str,
        new_string: str,
        require_read: bool = True,
    ) -> Dict[str, Any]:
        """
        Claude Code-style surgical string replacement.
        Guarantees:
        1. Target file must have been read prior to editing (if require_read=True).
        2. old_string must appear EXACTLY ONCE in target file.
        3. Automatic syntax validation (ast.parse for .py, json.loads for .json) with rollback.
        """
        if DESKTOP_ABORT_EVENT.is_set():
            return {"status": "ABORTED", "action": "SURGICAL_EDIT", "error": "Action aborted by emergency stop"}

        if not filename or not isinstance(filename, str):
            return {"status": "FAILED", "action": "SURGICAL_EDIT", "error": "Filename is required"}

        clean_filename = filename.strip()
        desktop_dir = Path(os.environ.get("SENTINEL_DESKTOP_DIR", Path.home() / "Desktop")).resolve()
        target_path = (desktop_dir / clean_filename).resolve()

        if target_path.parent != desktop_dir:
            return {"status": "FAILED", "action": "SURGICAL_EDIT", "error": "Path traversal detected"}

        if not target_path.exists():
            return {"status": "FAILED", "action": "SURGICAL_EDIT", "error": f"File '{clean_filename}' does not exist"}

        # Invariant 1: Read-Before-Write
        from core.code_diff_engine import code_diff_engine
        is_read = (str(target_path) in DesktopTool._session_read_files) or code_diff_engine.is_file_read(str(target_path))
        if require_read and not is_read:
            return {
                "status": "FAILED",
                "action": "SURGICAL_EDIT",
                "error": f"Read-before-write invariant violated: '{clean_filename}' must be read before editing.",
            }

        try:
            original_content = target_path.read_text(encoding="utf-8")
        except Exception as e:
            return {"status": "FAILED", "action": "SURGICAL_EDIT", "error": f"Could not read file: {e}"}

        # Invariant 2: Uniqueness of old_string
        occurrences = original_content.count(old_string)
        if occurrences == 0:
            return {
                "status": "FAILED",
                "action": "SURGICAL_EDIT",
                "error": "old_string not found in file. Ensure exact whitespace and line match.",
            }
        if occurrences > 1:
            return {
                "status": "FAILED",
                "action": "SURGICAL_EDIT",
                "error": f"old_string is ambiguous: found {occurrences} occurrences. Provide more surrounding context lines.",
            }

        new_content = original_content.replace(old_string, new_string, 1)

        # Invariant 3: Syntax Verification with Automatic Rollback
        ext = target_path.suffix.lower()
        if ext == ".py":
            import ast
            try:
                ast.parse(new_content)
            except SyntaxError as syn_err:
                return {
                    "status": "SYNTAX_ERROR",
                    "action": "SURGICAL_EDIT",
                    "error": f"Python SyntaxError on line {syn_err.lineno}: {syn_err.msg}",
                    "reverted": True,
                }
        elif ext == ".json":
            import json
            try:
                json.loads(new_content)
            except Exception as j_err:
                return {
                    "status": "SYNTAX_ERROR",
                    "action": "SURGICAL_EDIT",
                    "error": f"JSON syntax error: {j_err}",
                    "reverted": True,
                }

        try:
            target_path.write_text(new_content, encoding="utf-8")
            return {
                "status": "SUCCESS",
                "action": "SURGICAL_EDIT",
                "filename": clean_filename,
                "path": str(target_path),
                "bytes_written": len(new_content.encode("utf-8")),
            }
        except Exception as e:
            return {"status": "FAILED", "action": "SURGICAL_EDIT", "error": f"Failed writing edit: {e}"}


