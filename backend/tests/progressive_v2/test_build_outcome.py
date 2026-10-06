from __future__ import annotations

import json

from core.blender_pipeline.progressive_v2.controller import ProgressiveController
from core.blender_pipeline.progressive_v2.manifest import BuildManifest, CompletionStatus, NodeState


def test_spatial_failure_has_one_persisted_and_returned_outcome(tmp_path):
    """A spatial failure must not be recomputed to SUCCESS during finalization."""
    controller = ProgressiveController(model_manager=None, mcp_manager="mcp")
    manifest = BuildManifest.create("outcome parity")
    manifest._build_dir = lambda: tmp_path
    manifest.get_root().state = NodeState.VERIFIED
    manifest.stats["spatial_verification_failed"] = True
    manifest.stats["spatial_errors"] = ["measured penetration"]
    controller.manifest = manifest

    outcome = controller._compute_outcome(errors=[])
    assert outcome.status == CompletionStatus.COMPLETED_DEGRADED

    manifest.finalize(outcome)
    persisted = json.loads((manifest._build_dir() / "manifest.json").read_text(encoding="utf-8"))
    result = controller._build_result(0.0, [])

    assert persisted["outcome"] == result.to_dict()["outcome"]
    assert persisted["completion_status"] == result.completion_status.value


def test_manifest_save_survives_legacy_missing_transform_state(tmp_path):
    """Persistence must record the failure instead of crashing mid-cleanup."""
    manifest = BuildManifest.create("legacy transform rescue")
    manifest._build_dir = lambda: tmp_path
    manifest.get_root().transform_state = None

    path = manifest.save()
    persisted = json.loads(path.read_text(encoding="utf-8"))

    assert isinstance(persisted["nodes"][manifest.root_node_id]["transform_state"], dict)
