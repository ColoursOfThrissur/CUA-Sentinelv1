"""Production quality gates evaluated from measured Blender state."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional

from .node_types import NodeKind


class QualityGateFailed(RuntimeError):
    """Typed, evidence-bearing terminal quality-gate failure."""

    def __init__(self, attempt_id: str, defects: List[Dict[str, Any]], evidence_paths: List[str]) -> None:
        self.attempt_id = attempt_id
        self.defects = defects
        self.evidence_paths = evidence_paths
        super().__init__(
            f"QUALITY_GATE_FAILED attempt={attempt_id}: "
            + ", ".join(str(item.get("code", item.get("gate", "unknown"))) for item in defects[:8])
        )


class ProductionSceneAudit:
    """Audit Blender readback against generic manifest contracts."""

    CONTACT_TOLERANCE_M = 0.005
    ORIENTATION_RATIO = 1.25

    @classmethod
    def run(cls, manifest: Any, readback: Dict[str, Any]) -> Dict[str, Any]:
        objects = [item for item in readback.get("objects", []) if item.get("node_id")]
        by_node = {item["node_id"]: item for item in objects}
        findings: List[Dict[str, Any]] = []
        cls._check_declared_orientations(manifest, by_node, findings)
        cls._check_connectivity(manifest, objects, by_node, findings)
        errors = [item for item in findings if item["severity"] == "error"]
        report = {
            "ok": not errors,
            "schema_version": 1,
            "objects_checked": len(objects),
            "findings": findings,
        }
        manifest.stats["production_scene_audit"] = report
        manifest.record_event(
            "production_scene_audit_passed" if report["ok"] else "production_scene_audit_failed",
            details={"objects_checked": len(objects), "findings": findings},
        )
        if hasattr(manifest, "_build_dir"):
            cls._save(report, manifest._build_dir() / "production_scene_audit.json")
        return report

    @classmethod
    def _check_declared_orientations(
        cls, manifest: Any, by_node: Dict[str, Dict[str, Any]], findings: List[Dict[str, Any]],
    ) -> None:
        for node_id, actual in by_node.items():
            node = manifest.nodes.get(node_id)
            if not node:
                continue
            contract = (getattr(node, "stage_outputs", {}) or {}).get("spatial_contract", {})
            orientation = str(contract.get("orientation", "")).lower()
            dimensions = [float(value) for value in (actual.get("dimensions") or [])]
            if len(dimensions) != 3 or orientation not in {"horizontal", "flat_horizontal", "vertical"}:
                continue
            xy_long = max(dimensions[0], dimensions[1])
            z_size = dimensions[2]
            failed = (
                orientation in {"horizontal", "flat_horizontal"}
                and z_size > xy_long / cls.ORIENTATION_RATIO
            ) or (
                orientation == "vertical"
                and z_size * cls.ORIENTATION_RATIO < xy_long
            )
            if failed:
                findings.append(cls._finding(
                    "error", "orientation_contract_failed", node_id,
                    expected=orientation, dimensions=dimensions,
                ))

    @classmethod
    def _check_connectivity(
        cls,
        manifest: Any,
        objects: List[Dict[str, Any]],
        by_node: Dict[str, Dict[str, Any]],
        findings: List[Dict[str, Any]],
    ) -> None:
        eligible = []
        for item in objects:
            node = manifest.nodes.get(item["node_id"])
            if not node or not item.get("world_bounds"):
                continue
            if node.attachment and node.attachment.allow_disconnected:
                continue
            eligible.append(item)
        if len(eligible) < 2:
            return

        graph = {item["node_id"]: set() for item in eligible}
        for index, left in enumerate(eligible):
            for right in eligible[index + 1:]:
                if cls._aabb_gap(left["world_bounds"], right["world_bounds"]) <= cls.CONTACT_TOLERANCE_M:
                    graph[left["node_id"]].add(right["node_id"])
                    graph[right["node_id"]].add(left["node_id"])

        components: List[List[str]] = []
        remaining = set(graph)
        while remaining:
            seed = remaining.pop()
            component = {seed}
            stack = [seed]
            while stack:
                current = stack.pop()
                for neighbour in graph[current]:
                    if neighbour not in component:
                        component.add(neighbour)
                        remaining.discard(neighbour)
                        stack.append(neighbour)
            components.append(sorted(component))
        components.sort(key=len, reverse=True)
        for component in components[1:]:
            findings.append(cls._finding(
                "error", "disconnected_component", component[0],
                node_ids=component, size=len(component),
            ))

        for node_id, actual in by_node.items():
            node = manifest.nodes.get(node_id)
            attachment = getattr(node, "attachment", None) if node else None
            if not attachment or attachment.allow_disconnected or not actual.get("world_bounds"):
                continue
            reference_id = attachment.reference_node_id
            if not reference_id and attachment.connects_to:
                reference_id = cls._resolve_label_reference(manifest, node, attachment.connects_to)
            if not reference_id and attachment.relative_to:
                reference_id = cls._resolve_label_reference(manifest, node, attachment.relative_to)
            reference = by_node.get(reference_id) if reference_id else None
            if reference and reference.get("world_bounds"):
                gap = cls._aabb_gap(actual["world_bounds"], reference["world_bounds"])
                if gap > cls.CONTACT_TOLERANCE_M:
                    findings.append(cls._finding(
                        "error", "declared_attachment_gap", node_id,
                        reference_node_id=reference_id, gap_m=gap,
                    ))

    @staticmethod
    def _resolve_label_reference(manifest: Any, node: Any, label: str) -> Optional[str]:
        target = str(label).strip().lower()
        candidates = [
            other for other in manifest.nodes.values()
            if other.kind in (NodeKind.PART, NodeKind.INSTANCE)
            and str(other.label).strip().lower() == target
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda other: (
            0 if other.parent_id == node.parent_id else 1,
            abs(int(getattr(other, "hierarchy_depth", 0)) - int(getattr(node, "hierarchy_depth", 0))),
            other.node_id,
        ))
        return candidates[0].node_id

    @staticmethod
    def _aabb_gap(left: Dict[str, List[float]], right: Dict[str, List[float]]) -> float:
        squared = 0.0
        for axis in range(3):
            if left["max"][axis] < right["min"][axis]:
                delta = right["min"][axis] - left["max"][axis]
            elif right["max"][axis] < left["min"][axis]:
                delta = left["min"][axis] - right["max"][axis]
            else:
                delta = 0.0
            squared += delta * delta
        return math.sqrt(squared)

    @staticmethod
    def _finding(severity: str, code: str, node_id: str, **details: Any) -> Dict[str, Any]:
        return {"severity": severity, "code": code, "node_id": node_id, **details}

    @staticmethod
    def _save(report: Dict[str, Any], path: Path) -> None:
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        temporary.replace(path)
