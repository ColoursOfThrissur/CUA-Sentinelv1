"""Centralized broadcast helper for Blender pipeline stages.

Single source of truth for AGENT_TRACE broadcasts — prevents duplicate
broadcasts from orchestrator.py and executor.py defining their own versions.
"""

import datetime
import logging

logger = logging.getLogger(__name__)

_ws_manager = None
_HAS_BROADCAST = False

try:
    from api.websocket import manager as ws_manager
    _ws_manager = ws_manager
    _HAS_BROADCAST = True
except ImportError:
    pass


async def broadcast_blender_trace(
    task_id: str,
    stage: int,
    stage_name: str,
    status: str,
    data: dict = None,
) -> None:
    """Broadcast blender pipeline stage progress as AGENT_TRACE.
    
    Args:
        task_id: Task identifier
        stage: Stage number (0-6)
        stage_name: Human-readable stage name
        status: running | complete | failed | retrying | warning
        data: Optional additional details
    """
    if not _HAS_BROADCAST or not _ws_manager:
        return
    
    try:
        await _ws_manager.broadcast({
            "type": "AGENT_TRACE",
            "task_id": task_id,
            "step_name": f"Stage {stage}: {stage_name}",
            "tool_name": "blender:build_spec",
            "status": status,
            "details": {"stage": stage, "stage_name": stage_name, **(data or {})},
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        })
    except Exception as e:
        logger.debug(f"Broadcast failed (non-fatal): {e}")
