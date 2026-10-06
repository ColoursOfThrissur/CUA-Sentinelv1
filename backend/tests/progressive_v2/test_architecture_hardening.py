"""Regression tests for the V2 executable-contract hardening."""

import asyncio
from types import SimpleNamespace as NS

import pytest

from core.blender_pipeline.progressive_v2.evaluation import BASELINE_CASES
from core.blender_pipeline.progressive_v2.executor import BlenderExecutor
from core.blender_pipeline.progressive_v2.manifest import AttachmentSpec, BuildManifest, GeometrySpec
from core.blender_pipeline.progressive_v2.node_types import NodeKind, PrimitiveType, SocketType
from core.blender_pipeline.progressive_v2.scene_ir import ExecutableScenePlan, canonical_node_path
from core.blender_pipeline.progressive_v2.transaction import SceneTransactionCompiler
from core.blender_pipeline.progressive_v2.verification import SpatialVerifier, VerificationLevel
from core.blender_pipeline.progressive_v2.controller import BuildPhase, ProgressiveController
from core.blender_pipeline.progressive_v2.manifest import CompletionStatus, NodeState
from core.blender_pipeline.progressive_v2.capabilities import SUPPORTED_PRIMITIVES


def test_attempt_collections_are_unique_even_for_same_task() -> None:
    first = BlenderExecutor(None, "same-task")
    second = BlenderExecutor(None, "same-task")
    assert first._collection_name != second._collection_name
    assert first._attempt_id != second._attempt_id


def test_unknown_primitive_has_no_box_fallback() -> None:
    executor = BlenderExecutor(None, "capability-test")
    geo = NS(size=[1, 1, 1])
    with pytest.raises(ValueError, match="Unsupported transaction primitive"):
        executor._get_primitive_fragment(
            "future_mesh", "shape", geo, [0, 0, 0],
            [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]], "collection",
        )


def test_executable_scene_plan_uses_stable_id_paths_and_records_normalization() -> None:
    manifest = BuildManifest.create("panel", "scene_ir_test")
    root = manifest.get_root()
    child = manifest.add_child_node(
        root.node_id, "display_name", NodeKind.PART,
        attachment=AttachmentSpec(socket_type=SocketType.ROOT),
        geometry=GeometrySpec.from_dict({"primitive": "plane", "size": [1, 2]}),
    )
    plan = ExecutableScenePlan.from_manifest(manifest)
    record = next(item for item in plan.objects if item.node_id == child.node_id)
    assert record.canonical_path == canonical_node_path(manifest, child.node_id)
    assert record.canonical_path.endswith(child.node_id)
    assert plan.normalization_events[0]["rule"] == "plane_xy_to_thin_panel"
    assert plan.fingerprint


def test_boolean_target_method_is_reachable_on_compiler() -> None:
    root = NS(children_ids=["target", "cut"])
    target = NS(attachment=NS(socket_type=SocketType.ROOT))
    cutter = NS(parent_id="root")
    manifest = NS(nodes={"root": root, "target": target, "cut": cutter})
    compiler = SceneTransactionCompiler(NS(), manifest)
    assert compiler._boolean_target(cutter) is target


class _FloatingVerifier(SpatialVerifier):
    async def _check_interpenetration(self, *args, **kwargs):
        return {"issues": []}

    async def _check_floating_objects(self, *args, **kwargs):
        return {"floating": ["detached"]}


def test_disconnected_component_is_error_unless_explicitly_allowed() -> None:
    verifier = _FloatingVerifier(None)
    failed = asyncio.run(verifier.verify_assembly(
        ["body", "detached"], VerificationLevel.STRICT,
    ))
    allowed = asyncio.run(verifier.verify_assembly(
        ["body", "detached"], VerificationLevel.STRICT,
        allowed_disconnected={"detached"},
    ))
    assert failed.ok is False
    assert "Floating object: detached" in failed.errors
    assert allowed.ok is True


def test_reviewed_baseline_starts_small() -> None:
    assert 8 <= len(BASELINE_CASES) <= 10
    assert len({case.case_id for case in BASELINE_CASES}) == len(BASELINE_CASES)


def test_success_requires_independent_scene_readback() -> None:
    controller = ProgressiveController(None, object())
    controller.manifest = BuildManifest.create("model", "readback_gate")
    controller.manifest.get_root().state = NodeState.VERIFIED
    controller.phase = BuildPhase.COMPLETE
    result = controller._build_result(0.1, [])
    assert result.success is False
    assert result.completion_status == CompletionStatus.COMMITTED_UNVERIFIED


def test_every_declared_primitive_has_a_transaction_compiler() -> None:
    executor = BlenderExecutor(None, "coverage")
    matrix = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
    for primitive in SUPPORTED_PRIMITIVES:
        geometry = NS(
            primitive=primitive, size=[1.0, 1.0, 0.1], radius=0.5,
            radius2=0.25, depth=1.0, segments=12, rings=8,
            major_radius=0.5, minor_radius=0.1,
        )
        fragment = executor._get_primitive_fragment(
            primitive, f"shape_{primitive.value}", geometry, [0, 0, 0], matrix, "collection",
        )
        assert "_sentinel_results" in fragment
