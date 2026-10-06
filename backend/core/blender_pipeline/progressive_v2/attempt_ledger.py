"""Durable ownership and cleanup for every Blender commit attempt."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from enum import Enum
from typing import Any, Dict, Iterable, Optional


class AttemptState(str, Enum):
    PLANNED = "planned"
    COMMITTING = "committing"  # May have Blender side effects.
    COMMITTED = "committed"
    SUPERSEDED = "superseded"
    KEPT_FINAL = "kept_final"
    PRESERVED = "preserved"
    CLEANED = "cleaned"
    CLEANUP_FAILED = "cleanup_failed"


@dataclass
class AttemptRecord:
    attempt_id: str
    collection_name: str
    executor: Any
    state: AttemptState = AttemptState.PLANNED

    def evidence(self) -> Dict[str, str]:
        return {"attempt_id": self.attempt_id, "collection": self.collection_name, "state": self.state.value}


class AttemptLedger:
    """Tracks potentially dirty attempts independently of controller pointers."""

    def __init__(self, manifest: Any, preserve_failed_scene: bool = False) -> None:
        self.manifest = manifest
        self.preserve_failed_scene = preserve_failed_scene
        self.records: Dict[str, AttemptRecord] = {}

    def register(self, executor: Any) -> AttemptRecord:
        record = AttemptRecord(executor._attempt_id, executor._collection_name, executor)
        self.records[record.attempt_id] = record
        self._persist("attempt_registered", record)
        return record

    @classmethod
    def from_manifest(
        cls, manifest: Any, executors: Optional[Dict[str, Any]] = None,
        preserve_failed_scene: bool = False,
    ) -> "AttemptLedger":
        """Recover durable ownership records after a process restart.

        Executor handles are intentionally not persisted.  A caller that has
        reconnected to Blender may supply them by attempt id; until then, the
        recovered records still provide evidence and prevent false success.
        """
        ledger = cls(manifest, preserve_failed_scene=preserve_failed_scene)
        for raw in (manifest.stats.get("attempt_ledger", []) or []):
            try:
                attempt_id = str(raw["attempt_id"])
                state = AttemptState(raw["state"])
                ledger.records[attempt_id] = AttemptRecord(
                    attempt_id=attempt_id,
                    collection_name=str(raw["collection"]),
                    executor=(executors or {}).get(attempt_id),
                    state=state,
                )
            except (KeyError, TypeError, ValueError):
                continue
        return ledger

    def mark_committing(self, attempt_id: str) -> None:
        self._transition(attempt_id, AttemptState.COMMITTING, "attempt_committing")

    def mark_committed(self, attempt_id: str) -> None:
        self._transition(attempt_id, AttemptState.COMMITTED, "attempt_committed")

    async def keep_final(self, attempt_id: str) -> bool:
        for candidate_id, record in self.records.items():
            if candidate_id == attempt_id:
                continue
            if record.state not in {AttemptState.CLEANED, AttemptState.PRESERVED}:
                record.state = AttemptState.SUPERSEDED
                self._persist("attempt_superseded", record)
                if not await self._cleanup(record):
                    return False
        self._transition(attempt_id, AttemptState.KEPT_FINAL, "attempt_kept_final")
        return True

    async def rollback_all(self) -> bool:
        ok = True
        for record in self.records.values():
            if record.state in {AttemptState.CLEANED, AttemptState.PRESERVED, AttemptState.KEPT_FINAL}:
                continue
            if self.preserve_failed_scene:
                record.state = AttemptState.PRESERVED
                self._persist("attempt_preserved", record)
                continue
            ok = await self._cleanup(record) and ok
        return ok

    @staticmethod
    def sweep_candidates(manifests: Iterable[Any]) -> list[Dict[str, str]]:
        """Return abandoned tagged attempts without touching active builds.

        The caller supplies manifests so process ownership is explicit and the
        policy remains independent of filesystem layout.  A build still marked
        in-progress is always considered active; kept and debug-preserved
        attempts are never sweep candidates.
        """
        candidates: list[Dict[str, str]] = []
        for manifest in manifests:
            status = getattr(getattr(manifest, "completion_status", None), "value", None)
            if status == "in_progress":
                continue
            for raw in (getattr(manifest, "stats", {}).get("attempt_ledger", []) or []):
                try:
                    state = AttemptState(raw["state"])
                    if state in {AttemptState.KEPT_FINAL, AttemptState.PRESERVED, AttemptState.CLEANED}:
                        continue
                    candidates.append({
                        "attempt_id": str(raw["attempt_id"]),
                        "collection": str(raw["collection"]),
                    })
                except (KeyError, TypeError, ValueError):
                    continue
        return candidates

    @staticmethod
    async def sweep_orphans(mcp_manager: Any, manifests: Iterable[Any]) -> list[Dict[str, Any]]:
        """Remove tagged abandoned attempts from a prior dead build session."""
        reports: list[Dict[str, Any]] = []
        for candidate in AttemptLedger.sweep_candidates(manifests):
            collection = candidate["collection"]
            script = f'''
import bpy, json
_tag = {collection!r}
_removed = []
_coll = bpy.data.collections.get(_tag)
if _coll:
    for _obj in list(_coll.objects):
        _data = _obj.data
        _removed.append(_obj.name)
        bpy.data.objects.remove(_obj, do_unlink=True)
        if _data and getattr(_data, 'users', 0) == 0:
            if isinstance(_data, bpy.types.Mesh): bpy.data.meshes.remove(_data)
            elif isinstance(_data, bpy.types.Curve): bpy.data.curves.remove(_data)
    bpy.data.collections.remove(_coll)
for _obj in list(bpy.data.objects):
    if _obj.get('sentinel_build_id') == _tag:
        _data = _obj.data
        _removed.append(_obj.name)
        bpy.data.objects.remove(_obj, do_unlink=True)
        if _data and getattr(_data, 'users', 0) == 0:
            if isinstance(_data, bpy.types.Mesh): bpy.data.meshes.remove(_data)
            elif isinstance(_data, bpy.types.Curve): bpy.data.curves.remove(_data)
for _mat in list(bpy.data.materials):
    if _mat.get('sentinel_build_id') == _tag and _mat.users == 0:
        bpy.data.materials.remove(_mat)
print('SENTINEL_OUTPUT_START' + json.dumps({{'ok': True, 'removed': _removed}}) + 'SENTINEL_OUTPUT_END')
'''
            try:
                from core.blender_ops import parse_op_output
                result = await mcp_manager.call_locked("blender", "execute_blender_code", {"code": script})
                reports.append({**candidate, **parse_op_output(result.get("output", ""))})
            except Exception as exc:
                reports.append({**candidate, "ok": False, "error": str(exc)})
        return reports

    async def _cleanup(self, record: AttemptRecord) -> bool:
        try:
            if record.executor is None:
                raise RuntimeError("attempt executor unavailable after restart")
            await record.executor.cleanup_all()
            report = await record.executor.verify_attempt_absent()
            if not report.get("ok"):
                raise RuntimeError(f"tagged artifacts remain: {report.get('remaining', [])}")
        except Exception as exc:
            record.state = AttemptState.CLEANUP_FAILED
            self._persist("attempt_cleanup_failed", record, error=str(exc))
            return False
        record.state = AttemptState.CLEANED
        self._persist("attempt_cleaned", record)
        return True

    def _transition(self, attempt_id: str, state: AttemptState, event: str) -> None:
        record = self.records[attempt_id]
        record.state = state
        self._persist(event, record)

    def _persist(self, event: str, record: AttemptRecord, **details: Any) -> None:
        payload = {"attempt": record.evidence(), **details}
        self.manifest.record_event(event, details=payload)
        self.manifest.stats["attempt_ledger"] = [item.evidence() for item in self.records.values()]
        self.manifest.save()
