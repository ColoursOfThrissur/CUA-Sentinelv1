"""One-shot recovery for a build that crashed before it could persist failure."""

from __future__ import annotations

import asyncio
from pathlib import Path

from core.blender_pipeline.progressive_v2.attempt_ledger import AttemptLedger
from core.blender_pipeline.progressive_v2.manifest import BuildManifest, BuildOutcome, CompletionStatus


async def main() -> None:
    path = Path("data/builds_v2/m_aa0869f04d/manifest.json")
    manifest = BuildManifest.load(path)
    if manifest.completion_status is CompletionStatus.IN_PROGRESS:
        manifest.outcome = BuildOutcome(
            status=CompletionStatus.FAILED,
            verification_levels_run=["controller"],
            levels_passed={"controller": False},
            defects=[{
                "gate": "persistence",
                "measured": "transform_state was None during attempt ledger persistence",
                "expected": "serializable NodeTransformState",
            }],
            evidence_paths=[str(path)],
        )
        manifest.completion_status = CompletionStatus.FAILED
        manifest.stats["build_error"] = "TRANSFORM_STATE_PERSISTENCE_FAILURE"
        manifest.record_event("build_recovered_as_failed", details={"reason": manifest.stats["build_error"]})
        manifest.save(path)

    from core.mcp_manager import MCPManager
    mcp = MCPManager()
    mcp.initialize_from_config()
    await mcp.connect_app("blender")
    try:
        report = await AttemptLedger.sweep_orphans(mcp, [manifest])
        manifest.stats["recovery_sweep"] = report
        manifest.record_event("recovery_sweep", details={"report": report})
        manifest.save(path)
        print("RECOVERY_SWEEP", report)
    finally:
        await mcp.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
