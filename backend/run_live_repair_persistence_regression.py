"""Exercise the real controller repair path with one deterministic gate failure."""

from __future__ import annotations

import asyncio
import os


async def main() -> None:
    # Keep this regression focused on repair persistence rather than web/render
    # latency; Blender commit and readback remain live.
    os.environ["BLENDER_REFERENCE_RESEARCH"] = "0"
    os.environ["BLENDER_RENDER_EVIDENCE"] = "0"

    from core.blender_pipeline.progressive_v2.controller import ProgressiveController
    from core.blender_pipeline.progressive_v2.scene_quality import ProductionSceneAudit
    from core.blender_pipeline.progressive_v2.node_types import NodeKind
    from core.mcp_manager import MCPManager
    from core.blender_pipeline.progressive_v2.trace_pipeline import _OllamaManager

    mcp = MCPManager()
    mcp.initialize_from_config()
    await mcp.connect_app("blender")
    original_run = ProductionSceneAudit.run
    calls = 0

    def injected_run(cls, manifest, readback):
        nonlocal calls
        calls += 1
        if calls == 1:
            target = next(node for node in manifest.nodes.values() if node.kind is NodeKind.PART)
            return {
                "ok": False,
                "findings": [{
                    "severity": "error", "code": "injected_repair_probe",
                    "node_id": target.node_id, "message": "deterministic retry probe",
                }],
            }
        return {"ok": True, "findings": []}

    ProductionSceneAudit.run = classmethod(injected_run)
    try:
        controller = ProgressiveController(
            model_manager=_OllamaManager(), mcp_manager=mcp,
            max_retries=1,
        )
        result = await controller.run(
            "Build a simple tabletop stool with a square seat and four straight legs.",
            task_id="live_repair_persistence_regression",
            model_id="qwen3:14b-q4_K_M",
            stage0_output={
                "category": "furniture", "rests_on_surface": True,
                "style_tag": "plain", "scale_anchor_m": {"overall_height_or_length": 0.45},
            },
        )
        events = [event["type"] for event in result.manifest.events]
        assert "scene_quality_repair_attempt" in events, events
        assert result.manifest.stats.get("attempt_ledger"), "ledger was not persisted"
        assert result.completion_status.value != "in_progress"
        print("LIVE_REPAIR_PERSISTENCE_PASS", result.completion_status.value, result.manifest.model_id)
    finally:
        ProductionSceneAudit.run = original_run
        await mcp.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
