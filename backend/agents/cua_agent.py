import json
import logging
from agents.base_agent import BaseAgent
from tools.desktop_tool import DesktopTool

logger = logging.getLogger(__name__)


class CUAAgent(BaseAgent):
    """
    Computer Use Agent (CUA Engine).
    Executes desktop screen captures, window inspections, and UI interaction macros.
    All mutating desktop actions (click, type) are governed by HITL risk checks.
    """

    def __init__(self, model_manager, governance, config):
        super().__init__(model_manager, governance, config)
        self.desktop_tool = DesktopTool()

    async def run(self, claim) -> dict:
        task_id = claim.task_id
        lease_id = claim.lease_id
        lease_generation = claim.lease_generation
        payload = claim.input_payload

        prompt = payload.get("prompt", "Capture desktop screenshot and inspect active environment")
        model_id = self.model_manager.get_model_for_workflow("ENDPOINT")

        step_id = self.create_step(task_id, 0, "CUA_DESKTOP_INSPECT", "Inspect active desktop environment")
        self.update_step_status(step_id, "RUNNING")
        await self.broadcast_step_trace(task_id, "DESKTOP_SCREENSHOT", "DesktopTool", "RUNNING", {"action": "capture"})

        try:
            # Step 1: Capture screen & window info
            window_info = self.desktop_tool.get_active_window()
            screenshot = self.desktop_tool.take_screenshot(max_width=1280, quality=80)

            # Step 1b: Auto-cleanup old screenshots in SQLite to avoid database bloat
            try:
                from db.connections import get_operational_db
                with get_operational_db() as db_conn:
                    self.desktop_tool.cleanup_old_screenshots(db_conn, keep_count=20)
            except Exception as clean_err:
                logger.debug(f"Screenshot cleanup check: {clean_err}")

            # Save compressed screenshot as an artifact
            artifact_id = self.save_artifact(
                task_id=task_id,
                artifact_type="SCREENSHOT",
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

            # Step 2: Format prompt with active UI controls (VRAM & Token efficient)
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
            self.update_step_status(step_id, "FAILED", {"error": str(e)})
            return {"error": f"CUA execution failed: {e}"}
