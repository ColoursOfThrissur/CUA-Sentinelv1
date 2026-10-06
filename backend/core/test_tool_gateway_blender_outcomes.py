from __future__ import annotations

import pytest

from core.blender_pipeline.progressive_v2.controller import ProgressiveResult
from core.blender_pipeline.progressive_v2.manifest import BuildManifest, BuildOutcome, CompletionStatus


def _result(status: CompletionStatus) -> ProgressiveResult:
    manifest = BuildManifest.create("gateway outcome")
    outcome = BuildOutcome(status=status)
    manifest.outcome = outcome
    manifest.completion_status = status
    return ProgressiveResult(status is CompletionStatus.SUCCESS, manifest, status, outcome=outcome)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "ok", "task_outcome"),
    [
        (CompletionStatus.SUCCESS, True, "done"),
        (CompletionStatus.COMPLETED_DEGRADED, True, "done_with_warnings"),
        (CompletionStatus.COMMITTED_UNVERIFIED, False, "not_done"),
        (CompletionStatus.PLANNED_ONLY, False, "not_done"),
        (CompletionStatus.FAILED, False, "not_done"),
    ],
)
async def test_gateway_handler_maps_real_v2_result(monkeypatch, status, ok, task_outcome):
    from core.tool_gateway import ToolGateway
    import core.blender_pipeline.progressive_v2 as v2

    async def fake_build(**_kwargs): return _result(status)
    monkeypatch.setattr(v2, "run_progressive_build", fake_build)
    ToolGateway._TOOL_HANDLERS.clear()
    ToolGateway._active_model_manager = object()
    ToolGateway._active_mcp_manager = object()
    ToolGateway.register_default_handlers()
    payload = await ToolGateway._TOOL_HANDLERS["blender:build_progressive"](description="test")

    assert payload["ok"] is ok
    assert payload["task_outcome"] == task_outcome
    assert payload["completion_status"] == status.value
