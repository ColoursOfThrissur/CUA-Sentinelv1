"""Live Blender proof that controller finalization cleans a superseded attempt.

This intentionally builds two independently tagged candidates in the same
Blender session, then calls the controller's finalization boundary.  It proves
the ledger—not a stale controller executor pointer—owns old-attempt cleanup.
"""

from __future__ import annotations

import asyncio

from core.blender_pipeline.progressive_v2.attempt_ledger import AttemptLedger, AttemptState
from core.blender_pipeline.progressive_v2.controller import ProgressiveController
from core.blender_pipeline.progressive_v2.executor import BlenderExecutor
from test_controller_executor_live import _build_manifest


async def main() -> None:
    from core.mcp_manager import MCPManager

    mcp = MCPManager()
    mcp.initialize_from_config()
    await mcp.connect_app("blender")
    manifest = _build_manifest()
    controller = ProgressiveController(model_manager=None, mcp_manager=mcp)
    controller.manifest = manifest
    controller._attempt_ledger = AttemptLedger(manifest)
    node = manifest.get_node_by_label("tabletop")
    assert node is not None
    parent = manifest.nodes[node.parent_id]
    node.transform_state.compute_world(parent.transform_state.world_matrix, parent.transform_state.revision)

    first = BlenderExecutor(mcp, task_id="controller_attempt_ownership")
    controller._attempt_ledger.register(first)
    controller._attempt_ledger.mark_committing(first._attempt_id)
    assert (await first.build_node(node, manifest)).ok
    assert await first.flush(manifest)
    controller._attempt_ledger.mark_committed(first._attempt_id)

    second = BlenderExecutor(mcp, task_id="controller_attempt_ownership")
    controller._attempt_ledger.register(second)
    controller._attempt_ledger.mark_committing(second._attempt_id)
    assert (await second.build_node(node, manifest)).ok
    assert await second.flush(manifest)
    controller._attempt_ledger.mark_committed(second._attempt_id)

    # The controller has only the delivery executor; it must still clean the
    # first one through its ledger-owned record.
    controller._executor = second
    await controller._keep_final_attempt()

    assert controller._attempt_ledger.records[first._attempt_id].state is AttemptState.CLEANED
    assert controller._attempt_ledger.records[second._attempt_id].state is AttemptState.KEPT_FINAL
    assert (await first.verify_attempt_absent())["ok"] is True
    assert (await second.verify_attempt_absent())["ok"] is False
    await second.cleanup_all()
    assert (await second.verify_attempt_absent())["ok"] is True
    print("LIVE_CONTROLLER_ATTEMPT_OWNERSHIP_PASS")
    await mcp.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
