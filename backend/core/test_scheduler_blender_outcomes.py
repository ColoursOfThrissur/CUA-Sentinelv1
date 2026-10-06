from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.blender_pipeline.progressive_v2.controller import ProgressiveResult
from core.blender_pipeline.progressive_v2.manifest import BuildManifest, BuildOutcome, CompletionStatus
from core.queue import TaskClaimResult


def _result(status: CompletionStatus) -> dict:
    manifest = BuildManifest.create("scheduler outcome")
    outcome = BuildOutcome(status=status, defects=[{"node_id": "node-1", "gate": "quality"}])
    manifest.outcome = outcome
    manifest.completion_status = status
    return ProgressiveResult(
        success=status is CompletionStatus.SUCCESS,
        manifest=manifest,
        completion_status=status,
        errors=["node-1 failed"] if status is not CompletionStatus.SUCCESS else [],
        outcome=outcome,
    ).to_dict()


class _Queue:
    def __init__(self): self.calls = []
    def is_cancel_requested(self, _task_id): return False
    def release_task(self, *args, **kwargs): self.calls.append((args, kwargs))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (CompletionStatus.SUCCESS, "COMPLETED"),
        (CompletionStatus.COMPLETED_DEGRADED, "COMPLETED"),
        (CompletionStatus.COMMITTED_UNVERIFIED, "FAILED"),
        (CompletionStatus.PLANNED_ONLY, "FAILED"),
        (CompletionStatus.FAILED, "FAILED"),
    ],
)
async def test_scheduler_does_not_complete_non_done_blender_outcomes(monkeypatch, status, expected):
    from core.scheduler import Scheduler
    from core.router import IntentRouter
    import api.websocket

    payload = _result(status)
    class Agent:
        def __init__(self, **_kwargs): pass
        async def run(self, _claim): return payload
    monkeypatch.setattr(IntentRouter, "resolve_agent", staticmethod(lambda *_args: Agent))
    updates = []
    async def broadcast(*args): updates.append(args)
    monkeypatch.setattr(api.websocket, "broadcast_task_update", broadcast)

    queue = _Queue()
    models = SimpleNamespace(
        get_model_for_workflow=lambda _workflow: "model",
        get_current_model_id=lambda: "model",
        unload_current=lambda: None,
        load_model=lambda *_args: None,
    )
    scheduler = Scheduler(queue, models, object(), {"scheduler": {"poll_interval_sec": 1}}, None)
    claim = TaskClaimResult("task-1", "lease-1", 1, "ENDPOINT", 1, 1, {"prompt": "build"})

    await scheduler._execute_task(claim)
    assert queue.calls[0][0][2] == expected
    assert updates[0][1] == expected


@pytest.mark.asyncio
async def test_scheduler_websocket_marks_degraded_build_with_warning_payload(monkeypatch):
    from core.scheduler import Scheduler
    from core.router import IntentRouter
    import api.websocket

    class Agent:
        def __init__(self, **_kwargs): pass
        async def run(self, _claim): return _result(CompletionStatus.COMPLETED_DEGRADED)
    monkeypatch.setattr(IntentRouter, "resolve_agent", staticmethod(lambda *_args: Agent))
    updates = []
    async def broadcast(*args): updates.append(args)
    monkeypatch.setattr(api.websocket, "broadcast_task_update", broadcast)
    queue = _Queue()
    models = SimpleNamespace(get_model_for_workflow=lambda _w: "m", get_current_model_id=lambda: "m", unload_current=lambda: None, load_model=lambda *_a: None)
    scheduler = Scheduler(queue, models, object(), {"scheduler": {"poll_interval_sec": 1}}, None)
    claim = TaskClaimResult("task-warning", "lease", 1, "ENDPOINT", 1, 1, {"prompt": "build"})

    await scheduler._execute_task(claim)

    assert updates[0][1] == "COMPLETED"
    assert updates[0][2]["task_outcome"] == "done_with_warnings"
    assert "node-1 failed" in updates[0][2]["warnings"]
