"""Step-1 regression gates for trustworthy V2 build outcomes and evidence."""

import asyncio
import json
import os
import time

import pytest

from core.blender_pipeline.progressive_v2 import manifest as manifest_module
from core.blender_pipeline.progressive_v2.controller import BuildPhase, ProgressiveController
from core.blender_pipeline.progressive_v2.decomposer import DecompositionError, RecursiveDecomposer
from core.blender_pipeline.progressive_v2.hierarchy import HierarchyLimits
from core.blender_pipeline.progressive_v2.manifest import BuildManifest, CompletionStatus, GeometrySpec, NodeState
from core.blender_pipeline.progressive_v2.node_types import PrimitiveType


def test_degraded_result_is_not_api_success() -> None:
    controller = ProgressiveController(model_manager=None, mcp_manager=object())
    controller.manifest = BuildManifest.create("test model", "degraded_result")
    controller.manifest.get_root().state = NodeState.VERIFIED
    controller.manifest.stats["spatial_verification_failed"] = True
    controller.manifest.stats["spatial_errors"] = ["floating component"]
    controller.phase = BuildPhase.COMPLETE

    result = controller._build_result(0.1, ["floating component"])

    assert result.completion_status == CompletionStatus.COMPLETED_DEGRADED
    assert result.success is False
    assert result.to_dict()["success"] is False


def test_no_mcp_cannot_report_success() -> None:
    controller = ProgressiveController(model_manager=None, mcp_manager=None)
    controller.manifest = BuildManifest.create("test model", "no_mcp_result")
    controller.manifest.get_root().state = NodeState.VERIFIED
    controller.phase = BuildPhase.COMPLETE

    result = controller._build_result(0.1, [])

    assert result.success is False
    assert result.completion_status == CompletionStatus.PLANNED_ONLY


def test_build_retention_is_age_based_and_preserves_failures(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(manifest_module, "_DATA_ROOT", tmp_path)
    now = time.time()

    def build(name: str, status: str, age_days: int) -> None:
        directory = tmp_path / name
        directory.mkdir()
        path = directory / "manifest.json"
        path.write_text(json.dumps({"completion_status": status}), encoding="utf-8")
        stamp = now - age_days * 86400
        os.utime(path, (stamp, stamp))

    build("recent_success", "success", 2)
    build("old_success", "success", 45)
    build("old_failure", "failed", 90)

    report = manifest_module.prune_old_builds(retention_days=30, now=now)

    assert (tmp_path / "recent_success").exists()
    assert not (tmp_path / "old_success").exists()
    assert (tmp_path / "old_failure").exists()
    assert report["removed"] == ["old_success"]
    assert "old_failure" in report["preserved_failures"]


def test_decomposition_budget_exhaustion_is_explicit_and_persisted(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(manifest_module, "_DATA_ROOT", tmp_path)
    manifest = BuildManifest.create("a complex model", "budget_exhaustion")
    decomposer = RecursiveDecomposer(
        limits=HierarchyLimits(max_depth=5, max_children=20, max_total_nodes=100),
        max_llm_calls=0,
    )

    with pytest.raises(DecompositionError, match="DECOMPOSITION_BUDGET_EXHAUSTED"):
        asyncio.run(decomposer.decompose(manifest, model_manager=None, task_id="budget-test"))

    assert manifest.stats["decomposition_complete"] is False
    assert manifest.stats["decomposition_budget_exhausted"]
    assert any(event["type"] == "decomposition_budget_exhausted" for event in manifest.events)
    persisted = json.loads((tmp_path / manifest.model_id / "manifest.json").read_text(encoding="utf-8"))
    assert persisted["stats"]["decomposition_complete"] is False


def test_v3_drone_plane_shape_replays_as_explicit_thin_panel() -> None:
    # Frozen from the failed V3 drone plan: its two-value plane size used to
    # raise before repair or Blender execution.
    raw = {"primitive": "plane", "size": [0.38, 0.24], "depth": 0.005}

    geometry = GeometrySpec.from_dict(raw)

    assert geometry.primitive == PrimitiveType.PLANE
    assert geometry.size == [0.38, 0.24, 0.005]
    assert geometry.normalization_events == [{
        "field": "size",
        "rule": "plane_xy_to_thin_panel",
        "got": [0.38, 0.24],
        "normalized": [0.38, 0.24, 0.005],
    }]
