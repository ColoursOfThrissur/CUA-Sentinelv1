from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.blender_pipeline.progressive_v2.controller import ProgressiveResult
from core.blender_pipeline.progressive_v2.manifest import BuildManifest, BuildOutcome, CompletionStatus


def _v2_result(status: CompletionStatus) -> ProgressiveResult:
    manifest = BuildManifest.create("endpoint V2 result")
    defects = [{"node_id": "leg-1", "gate": "ground", "message": "floating leg"}]
    outcome = BuildOutcome(status=status, defects=defects)
    manifest.outcome = outcome
    manifest.completion_status = status
    return ProgressiveResult(
        success=status is CompletionStatus.SUCCESS,
        manifest=manifest,
        completion_status=status,
        errors=["leg-1 floating"] if status is not CompletionStatus.SUCCESS else [],
        outcome=outcome,
    )


def _agent(monkeypatch, result: ProgressiveResult):
    from agents.endpoint_agent import EndpointAgent
    import core.blender_pipeline.progressive_v2 as v2

    agent = object.__new__(EndpointAgent)
    agent.model_manager = SimpleNamespace(get_model_for_workflow=lambda _workflow: "test-model")
    agent.profile = {}
    agent._mcp_manager = SimpleNamespace(
        list_connected_app_ids=lambda: [],
        get_tools_for_app=lambda _app: [],
    )
    agent.create_step = lambda *_args: "step-1"
    agent.update_step_status = lambda *_args, **_kwargs: None
    agent.save_artifact = lambda *_args, **_kwargs: None
    async def trace(*_args, **_kwargs): pass
    agent.broadcast_step_trace = trace
    async def llm(**_kwargs):
        return '{"action":"call_tool","tool":"blender:build_spec","args":{}}'
    agent.call_llm = llm
    async def execute(*_args, **_kwargs):
        return {"status": "ok", "data": {}}
    agent.execute_tool = execute
    monkeypatch.setattr(v2, "run_progressive_build", lambda **_kwargs: _async_result(result))
    return agent


async def _async_result(result):
    return result


async def _raise(error):
    raise error


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "expected_done"),
    [
        (CompletionStatus.SUCCESS, True),
        (CompletionStatus.COMPLETED_DEGRADED, True),
        (CompletionStatus.COMMITTED_UNVERIFIED, False),
        (CompletionStatus.PLANNED_ONLY, False),
        (CompletionStatus.FAILED, False),
    ],
)
async def test_endpoint_flow_maps_real_v2_outcome_to_task_result(monkeypatch, status, expected_done):
    agent = _agent(monkeypatch, _v2_result(status))
    claim = SimpleNamespace(
        task_id="endpoint-v2",
        lease_id="lease",
        lease_generation=1,
        input_payload={"prompt": "build a test stool"},
        context_budget=1024,
    )

    payload = await agent.run(claim)

    assert payload["completion_status"] == status.value
    assert payload["task_outcome"] == ("done" if status is CompletionStatus.SUCCESS else "done_with_warnings" if status is CompletionStatus.COMPLETED_DEGRADED else "not_done")
    assert payload["ok"] is expected_done
    if status is CompletionStatus.COMPLETED_DEGRADED:
        assert "floating leg" in payload["response"]
    if not expected_done:
        assert "leg-1 floating" in payload["error"]


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [
    pytest.param(__import__("core.blender_pipeline.progressive_v2.scene_quality", fromlist=["QualityGateFailed"]).QualityGateFailed(
        "attempt-x", [{"node_id": "leg-1", "message": "floating leg"}], ["audit.json"]
    ), id="quality-gate"),
    pytest.param(RuntimeError("MCP bridge disconnected"), id="unexpected"),
])
async def test_endpoint_exception_path_is_fail_closed_and_preserves_defects(monkeypatch, error):
    agent = _agent(monkeypatch, _v2_result(CompletionStatus.SUCCESS))
    import core.blender_pipeline.progressive_v2 as v2
    monkeypatch.setattr(v2, "run_progressive_build", lambda **_kwargs: _raise(error))
    claim = SimpleNamespace(task_id="endpoint-error", lease_id="lease", lease_generation=1,
                            input_payload={"prompt": "build a test stool"}, context_budget=1024)

    payload = await agent.run(claim)

    assert payload["completion_status"] == "failed"
    assert payload["task_outcome"] == "not_done"
    assert payload["ok"] is False
    assert str(error) in payload["error"]
    if hasattr(error, "defects"):
        assert payload["outcome"]["defects"] == error.defects
