import os
import re
import json
import logging
from pathlib import Path
from typing import Optional, Tuple
from agents.base_agent import BaseAgent
from tools.desktop_tool import DesktopTool

logger = logging.getLogger(__name__)


class CUAAgent(BaseAgent):
    """
    Computer Use Agent (CUA Engine).
    Executes desktop screen captures, window inspections, and UI interaction macros.
    All mutating desktop actions (click, type, write) are governed by HITL risk checks.
    """
    PROFILE_NAME = "cua_agent"
    agent_name = "cua_agent"

    def __init__(self, model_manager, governance, config):
        super().__init__(model_manager, governance, config)
        self.desktop_tool = DesktopTool()

    def _extract_file_intent(self, prompt: str) -> Optional[Tuple[str, str]]:
        """Extracts desired filename and content for desktop file creation requests."""
        p_lower = prompt.lower()
        has_create_kw = any(kw in p_lower for kw in ("create", "write", "make", "save", "touch", "new file", "new txt", "new md"))
        has_file_kw = any(kw in p_lower for kw in ("file", "filew", "txt", "md", "text", "doc", "document"))
        if not (has_create_kw and has_file_kw):
            return None
        norm_text = re.sub(r'[\s_\-]+', '', p_lower)
        has_desktop = (
            "desktop" in p_lower
            or p_lower.startswith("/desktop")
            or "desktop" in norm_text
            or any(kw in p_lower for kw in ("desk top", "desktp", "deskop"))
        )
        if not has_desktop:
            return None

        # Look for explicit filename with .txt or .md
        fn_match = re.search(r'([A-Za-z0-9_\-]+\.(?:txt|md))', prompt, re.IGNORECASE)
        # Look for "named <name>" or "called <name>" without extension
        name_match = re.search(r'(?:named|called)\s+([A-Za-z0-9_\-]+)', prompt, re.IGNORECASE)

        desktop_dir = Path(os.environ.get("SENTINEL_DESKTOP_DIR", Path.home() / "Desktop")).resolve()

        if fn_match:
            filename = fn_match.group(1)
        elif name_match:
            base = name_match.group(1)
            ext = ".md" if (".md" in p_lower or "markdown" in p_lower) else ".txt"
            filename = f"{base}{ext}"
        else:
            base_name = "new_file.md" if (".md" in p_lower or "markdown" in p_lower) else "new_file.txt"
            filename = base_name
            if (desktop_dir / filename).exists():
                for i in range(1, 100):
                    cand = f"new_file_{i}.txt" if filename.endswith(".txt") else f"new_file_{i}.md"
                    if not (desktop_dir / cand).exists():
                        filename = cand
                        break

        # Look for explicit content
        content_match = re.search(r'(?:content|text|saying|containing|with)\s*[:=]?\s*["\']([^"\']+)["\']', prompt, re.IGNORECASE)
        if content_match:
            content = content_match.group(1)
        else:
            content = f"Created by CUA-Sentinel on Desktop.\nSource Request: {prompt}\n"

        return filename, content

    async def run(self, claim) -> dict:
        task_id = claim.task_id
        lease_id = claim.lease_id
        lease_generation = claim.lease_generation
        payload = claim.input_payload or {}
        step_id = None

        prompt = payload.get("prompt", "Capture desktop screenshot and inspect active environment")
        model_id = self.model_manager.get_model_for_workflow("ENDPOINT")

        try:
            # Step 1: Check for direct Desktop file creation intent (runs untainted before any screen capture)
            file_intent = self._extract_file_intent(prompt)
            if file_intent:
                fname, fcontent = file_intent
                step_id = self.create_step(task_id, 0, "CUA_DESKTOP_FILE_WRITE", f"Write {fname} to Desktop")
                self.update_step_status(step_id, "RUNNING")
                await self.broadcast_step_trace(task_id, "DESKTOP_FILE_WRITE", "DesktopTool", "RUNNING", {"filename": fname})

                write_res = await self.execute_tool(
                    "desktop_file_write",
                    {"filename": fname, "content": fcontent},
                    task_id=task_id,
                    step_id=step_id,
                    tool_instance=self.desktop_tool,
                )
                write_data = write_res.get("data") or {}

                if write_res.get("status") == "ok" and write_data.get("status") == "SUCCESS":
                    self.update_step_status(step_id, "COMPLETED", write_data)
                    await self.broadcast_step_trace(task_id, "DESKTOP_FILE_WRITE", "DesktopTool", "COMPLETED", write_data)

                    resp_text = (
                        f"✅ Successfully created file `{fname}` on your Desktop at `{write_data.get('path')}` "
                        f"({write_data.get('bytes_written', 0)} bytes written)."
                    )
                    return {
                        "response": resp_text,
                        "file_created": write_data,
                        "model_used": model_id,
                    }
                else:
                    err_msg = write_data.get("error") or write_res.get("reason") or "File creation failed"
                    self.update_step_status(step_id, "FAILED", {"error": err_msg})
                    await self.broadcast_step_trace(task_id, "DESKTOP_FILE_WRITE", "DesktopTool", "FAILED", {"error": err_msg})
                    return {
                        "response": f"❌ Could not create file on Desktop: {err_msg}",
                        "error": err_msg,
                        "model_used": model_id,
                    }

            # Step 2: Desktop Screen Inspection & Active Environment Capture
            step_id = self.create_step(task_id, 0, "CUA_DESKTOP_INSPECT", "Inspect active desktop environment")
            self.update_step_status(step_id, "RUNNING")
            await self.broadcast_step_trace(task_id, "DESKTOP_SCREENSHOT", "DesktopTool", "RUNNING", {"action": "capture"})

            win_res = await self.execute_tool(
                "get_active_window",
                {},
                task_id=task_id,
                step_id=step_id,
                tool_instance=self.desktop_tool,
            )
            window_info = win_res.get("data") or {"title": "Desktop", "controls": []}

            shot_res = await self.execute_tool(
                "take_screenshot",
                {"max_width": 1280, "quality": 80},
                task_id=task_id,
                step_id=step_id,
                tool_instance=self.desktop_tool,
            )
            screenshot = shot_res.get("data") or {}

            # Step 2b: Auto-cleanup old screenshots to avoid database bloat
            try:
                self.desktop_tool.cleanup_old_screenshots(keep_count=20)
            except Exception as clean_err:
                logger.debug(f"Screenshot cleanup check: {clean_err}")

            # Save compressed screenshot as an artifact
            artifact_id = self.save_artifact(
                task_id=task_id,
                artifact_type="OBSERVATION",
                content=screenshot.get("full_b64", screenshot.get("image_b64", "")),
                step_id=step_id,
                metadata={
                    "width": screenshot.get("width"),
                    "height": screenshot.get("height"),
                    "scaled_width": screenshot.get("scaled_width"),
                    "scaled_height": screenshot.get("scaled_height"),
                    "format": screenshot.get("format", "JPEG"),
                    "size_kb": screenshot.get("size_kb"),
                    "window": window_info.get("title")
                },
            )

            await self.broadcast_step_trace(
                task_id,
                "DESKTOP_INSPECTED",
                "DesktopTool",
                "COMPLETED",
                {
                    "active_window": window_info.get("title"),
                    "artifact_id": artifact_id,
                    "controls_found": len(window_info.get("controls", [])),
                    "image_size_kb": screenshot.get("size_kb")
                },
            )

            # Step 3: Format prompt with active UI controls (VRAM & Token efficient)
            controls_summary = ""
            controls = window_info.get("controls", [])
            if controls:
                ctrl_lines = [f"- '{c['text'] or c['class']}' at center ({c['center'][0]}, {c['center'][1]})" for c in controls[:10]]
                controls_summary = "\nVisible UI Controls:\n" + "\n".join(ctrl_lines)

            cua_prompt = f"""You are a Computer Use Agent (CUA) inspecting the user's desktop environment.
Active Foreground Window: {window_info.get('title')} (OS: {window_info.get('os')})
Display Resolution: {screenshot.get('width')}x{screenshot.get('height')} (Captured at {screenshot.get('scaled_width')}x{screenshot.get('scaled_height')} JPEG, size {screenshot.get('size_kb')}KB){controls_summary}

User Instruction: {prompt}

Provide a concise, clear status report of the desktop state and any actions required."""

            response = await self.model_manager.generate_async(
                model_id=model_id,
                task_id=task_id,
                lease_id=lease_id,
                lease_generation=lease_generation,
                prompt=cua_prompt,
                temperature=0.2,
                context_budget=claim.context_budget,
            )

            self.update_step_status(step_id, "COMPLETED", {"active_window": window_info.get("title")})

            return {
                "response": response,
                "active_window": window_info.get("title"),
                "screenshot_artifact_id": artifact_id,
                "controls": controls[:10],
                "model_used": model_id,
            }

        except Exception as e:
            logger.error(f"CUA Agent task {task_id} failed: {e}")
            if step_id:
                self.update_step_status(step_id, "FAILED", {"error": str(e)})
            return {"error": f"CUA execution failed: {e}"}
