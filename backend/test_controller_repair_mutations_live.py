"""Live Blender repair-attempt proof and negative-control matrix.

This is deliberately small and deterministic: it exercises the controller's
attempt-finalization boundary with two real Blender candidates, rather than
asking an LLM to reproduce a particular geometry defect.  The old candidate
stands for a failed quality-gate attempt; the new candidate stands for its
repair.  Every negative control must leave the old tag visible.
"""

from __future__ import annotations

import asyncio
from contextlib import suppress

import pytest

from core.blender_pipeline.progressive_v2.attempt_ledger import AttemptLedger, AttemptState
from core.blender_pipeline.progressive_v2.controller import ProgressiveController
from core.blender_pipeline.progressive_v2.executor import BlenderExecutor
from test_controller_executor_live import _build_manifest


async def _candidate(mcp, manifest, ledger, *, register: bool) -> BlenderExecutor:
    node = manifest.get_node_by_label("tabletop")
    parent = manifest.nodes[node.parent_id]
    node.transform_state.compute_world(parent.transform_state.world_matrix, parent.transform_state.revision)
    executor = BlenderExecutor(mcp, task_id="controller_repair_mutation_live")
    if register:
        ledger.register(executor)
        ledger.mark_committing(executor._attempt_id)
    assert (await executor.build_node(node, manifest)).ok
    assert await executor.flush(manifest)
    if register:
        ledger.mark_committed(executor._attempt_id)
    return executor


async def _cleanup(*executors: BlenderExecutor) -> None:
    for executor in executors:
        with suppress(Exception):
            await executor.cleanup_all()


async def _run_case(mcp, name: str, mutation: str | None) -> None:
    manifest = _build_manifest()
    controller = ProgressiveController(model_manager=None, mcp_manager=mcp)
    controller.manifest = manifest
    ledger = AttemptLedger(manifest)
    controller._attempt_ledger = ledger

    first = await _candidate(mcp, manifest, ledger, register=mutation != "omit_register")
    second = await _candidate(mcp, manifest, ledger, register=True)
    controller._executor = second
    original_keep = ledger.keep_final
    original_cleanup = ledger._cleanup
    original_finalize = controller._keep_final_attempt

    try:
        if mutation == "skip_cleanup":
            async def no_cleanup_keep(attempt_id):
                ledger.records[attempt_id].state = AttemptState.KEPT_FINAL
                return True
            ledger.keep_final = no_cleanup_keep
        elif mutation == "bypass_keep_final":
            async def no_finalize():
                return None
            controller._keep_final_attempt = no_finalize
        elif mutation == "skip_verify_absent":
            async def falsely_clean(record):
                # Mutation: emulate a cleanup call that declares success
                # without invoking executor.verify_attempt_absent().
                record.state = AttemptState.CLEANED
                return True
            ledger._cleanup = falsely_clean

        await controller._keep_final_attempt()
        old_absent = (await first.verify_attempt_absent())["ok"]
        delivery_present = not (await second.verify_attempt_absent())["ok"]
        baseline_ok = old_absent and delivery_present and ledger.records.get(second._attempt_id, None) and ledger.records[second._attempt_id].state is AttemptState.KEPT_FINAL
        if mutation is None:
            assert baseline_ok, (old_absent, delivery_present, ledger.records)
            print(f"LIVE_REPAIR_BASELINE_PASS {name}")
        else:
            assert not baseline_ok, f"mutation {mutation} was not detected"
            print(f"EXPECTED_MUTATION_FAILURE {name} {mutation} old_absent={old_absent} delivery_present={delivery_present}")
    finally:
        ledger.keep_final = original_keep
        ledger._cleanup = original_cleanup
        controller._keep_final_attempt = original_finalize
        await _cleanup(first, second)


async def main() -> None:
    from core.mcp_manager import MCPManager
    mcp = MCPManager()
    mcp.initialize_from_config()
    await mcp.connect_app("blender")
    try:
        await _run_case(mcp, "repair", None)
        for mutation in ("omit_register", "skip_cleanup", "bypass_keep_final", "skip_verify_absent"):
            await _run_case(mcp, "repair", mutation)
    finally:
        await mcp.shutdown()


@pytest.mark.asyncio
async def test_live_controller_repair_mutation_matrix() -> None:
    """Recorded suite form; skips visibly only when Blender is unavailable."""
    from core.mcp_manager import MCPManager
    mcp = MCPManager()
    mcp.initialize_from_config()
    try:
        await mcp.connect_app("blender")
    except Exception as exc:
        pytest.skip(f"Blender MCP unavailable: {exc}")
    try:
        await _run_case(mcp, "repair", None)
        for mutation in ("omit_register", "skip_cleanup", "bypass_keep_final", "skip_verify_absent"):
            await _run_case(mcp, "repair", mutation)
    finally:
        await mcp.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
