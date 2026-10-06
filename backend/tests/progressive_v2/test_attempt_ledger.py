from __future__ import annotations

import pytest

from core.blender_pipeline.progressive_v2.attempt_ledger import AttemptLedger, AttemptState
from core.blender_pipeline.progressive_v2.manifest import BuildManifest, CompletionStatus


class FakeExecutor:
    def __init__(self, attempt_id: str):
        self._attempt_id = attempt_id
        self._collection_name = f"attempt_{attempt_id}"
        self.cleaned = 0
        self.absent_checks = 0

    async def cleanup_all(self):
        self.cleaned += 1

    async def verify_attempt_absent(self):
        self.absent_checks += 1
        return {"ok": True, "remaining": []}


class RemainingArtifactsExecutor(FakeExecutor):
    async def verify_attempt_absent(self):
        self.absent_checks += 1
        return {"ok": False, "remaining": [{"kind": "objects", "name": "tagged-leftover"}]}


class UnreachableExecutor(FakeExecutor):
    async def cleanup_all(self):
        raise ConnectionError("Blender MCP bridge disconnected")


@pytest.mark.asyncio
async def test_terminal_failure_rolls_back_every_possibly_dirty_attempt(tmp_path):
    manifest = BuildManifest.create("ledger")
    manifest._build_dir = lambda: tmp_path
    ledger = AttemptLedger(manifest)
    first, second = FakeExecutor("first"), FakeExecutor("second")

    ledger.register(first)
    ledger.mark_committing(first._attempt_id)
    ledger.mark_committed(first._attempt_id)
    ledger.register(second)
    ledger.mark_committing(second._attempt_id)

    await ledger.rollback_all()

    assert first.cleaned == second.cleaned == 1
    assert first.absent_checks == second.absent_checks == 1
    assert {record.state for record in ledger.records.values()} == {AttemptState.CLEANED}


@pytest.mark.asyncio
async def test_success_keeps_only_final_attempt_and_cleans_superseded(tmp_path):
    manifest = BuildManifest.create("ledger")
    manifest._build_dir = lambda: tmp_path
    ledger = AttemptLedger(manifest)
    old, keeper = FakeExecutor("old"), FakeExecutor("keeper")
    for executor in (old, keeper):
        ledger.register(executor)
        ledger.mark_committing(executor._attempt_id)
        ledger.mark_committed(executor._attempt_id)

    await ledger.keep_final(keeper._attempt_id)

    assert old.cleaned == 1
    assert keeper.cleaned == 0
    assert ledger.records[old._attempt_id].state == AttemptState.CLEANED
    assert ledger.records[keeper._attempt_id].state == AttemptState.KEPT_FINAL


def test_ledger_is_recovered_from_persisted_manifest_after_restart(tmp_path):
    manifest = BuildManifest.create("durable ledger")
    manifest._build_dir = lambda: tmp_path
    executor = FakeExecutor("durable")
    ledger = AttemptLedger(manifest)
    ledger.register(executor)
    ledger.mark_committing(executor._attempt_id)
    manifest_path = manifest.save()

    restarted_manifest = BuildManifest.load(manifest_path)
    recovered = AttemptLedger.from_manifest(restarted_manifest)

    assert recovered.records["durable"].state is AttemptState.COMMITTING
    assert recovered.records["durable"].executor is None


@pytest.mark.asyncio
async def test_cleanup_is_failed_when_separate_absence_proof_finds_remnants(tmp_path):
    manifest = BuildManifest.create("absence proof")
    manifest._build_dir = lambda: tmp_path
    executor = RemainingArtifactsExecutor("remaining")
    ledger = AttemptLedger(manifest)
    ledger.register(executor)
    ledger.mark_committing(executor._attempt_id)

    assert await ledger.rollback_all() is False
    assert ledger.records[executor._attempt_id].state is AttemptState.CLEANUP_FAILED


@pytest.mark.asyncio
async def test_cleanup_unreachable_records_cleanup_failed(tmp_path):
    manifest = BuildManifest.create("connection lost")
    manifest._build_dir = lambda: tmp_path
    executor = UnreachableExecutor("offline")
    ledger = AttemptLedger(manifest)
    ledger.register(executor)
    ledger.mark_committing(executor._attempt_id)

    assert await ledger.rollback_all() is False
    assert ledger.records[executor._attempt_id].state is AttemptState.CLEANUP_FAILED
    assert manifest.events[-1]["type"] == "attempt_cleanup_failed"


def test_startup_sweep_skips_active_and_preserved_attempts():
    active = BuildManifest.create("active")
    active.completion_status = CompletionStatus.IN_PROGRESS
    active.stats["attempt_ledger"] = [{"attempt_id": "active", "collection": "active-coll", "state": "committing"}]
    dead = BuildManifest.create("dead")
    dead.completion_status = CompletionStatus.FAILED
    dead.stats["attempt_ledger"] = [
        {"attempt_id": "orphan", "collection": "orphan-coll", "state": "cleanup_failed"},
        {"attempt_id": "debug", "collection": "debug-coll", "state": "preserved"},
        {"attempt_id": "final", "collection": "final-coll", "state": "kept_final"},
    ]

    assert AttemptLedger.sweep_candidates([active, dead]) == [
        {"attempt_id": "orphan", "collection": "orphan-coll"}
    ]
