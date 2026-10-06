from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.blender_pipeline.progressive_v2.controller import ProgressiveResult
from core.blender_pipeline.progressive_v2.manifest import BuildManifest, BuildOutcome, CompletionStatus


def _result(status: CompletionStatus) -> ProgressiveResult:
    manifest = BuildManifest.create("consumer result")
    outcome = BuildOutcome(status=status, defects=[{"node_id": "node-1", "gate": "quality"}])
    manifest.outcome = outcome
    manifest.completion_status = status
    return ProgressiveResult(
        success=status is CompletionStatus.SUCCESS,
        manifest=manifest,
        completion_status=status,
        errors=["node-1 quality failure"] if status is not CompletionStatus.SUCCESS else [],
        outcome=outcome,
    )


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
async def test_api_route_uses_real_v2_result_outcome(monkeypatch, status, ok, task_outcome):
    from api.routes import blender
    import core.blender_pipeline.progressive_v2 as v2

    async def fake_build(**_kwargs):
        return _result(status)

    monkeypatch.setattr(v2, "run_progressive_build", fake_build)
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(model_manager=object(), mcp_manager=object())))
    payload = await blender.build_3d_object(blender.BlenderBuildRequest(description="test object"), request)

    assert payload["ok"] is ok
    assert payload["task_outcome"] == task_outcome
    assert payload["completion_status"] == status.value
    assert payload["outcome"]["status"] == status.value
    if not ok:
        assert "node-1 quality failure" in payload["error"]
