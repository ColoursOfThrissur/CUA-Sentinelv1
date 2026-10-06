"""Versioned executable scene contract for the V2 Blender compiler.

The manifest remains the mutable planning workspace.  ``ExecutableScenePlan``
is the immutable boundary between planning and Blender execution, and is saved
as run evidence before any scene mutation occurs.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .capabilities import SCENE_PLAN_SCHEMA_VERSION, capability_manifest
from .node_types import NodeKind, SocketType


def canonical_node_path(manifest: Any, node_id: str) -> str:
    """Return an identity path made only from stable hierarchy IDs."""
    parts: List[str] = []
    seen = set()
    current = manifest.nodes.get(node_id)
    while current is not None and current.node_id not in seen:
        seen.add(current.node_id)
        parts.append(current.node_id)
        parent_id = getattr(current, "parent_id", None)
        current = manifest.nodes.get(parent_id) if parent_id else None
    return "/" + "/".join(reversed(parts))


def _serialized(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if isinstance(value, dict):
        return {str(key): _serialized(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialized(item) for item in value]
    if hasattr(value, "value"):
        return value.value
    if hasattr(value, "__dict__"):
        return {key: _serialized(item) for key, item in vars(value).items()}
    return value


@dataclass(frozen=True)
class SceneObjectPlan:
    node_id: str
    canonical_path: str
    kind: str
    label: str
    parent_id: Optional[str]
    children_ids: List[str]
    geometry: Optional[Dict[str, Any]]
    material: Optional[Dict[str, Any]]
    modifiers: List[Dict[str, Any]]
    attachment: Optional[Dict[str, Any]]
    transform: Optional[Dict[str, Any]]
    instance_of: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "canonical_path": self.canonical_path,
            "kind": self.kind,
            "label": self.label,
            "parent_id": self.parent_id,
            "children_ids": list(self.children_ids),
            "geometry": self.geometry,
            "material": self.material,
            "modifiers": list(self.modifiers),
            "attachment": self.attachment,
            "transform": self.transform,
            "instance_of": self.instance_of,
        }


@dataclass(frozen=True)
class ExecutableScenePlan:
    schema_version: int
    model_id: str
    prompt: str
    contract: Dict[str, Any]
    capabilities: Dict[str, Any]
    objects: List[SceneObjectPlan]
    boolean_operations: List[Dict[str, str]] = field(default_factory=list)
    normalization_events: List[Dict[str, Any]] = field(default_factory=list)
    fingerprint: str = ""

    @classmethod
    def from_manifest(cls, manifest: Any) -> "ExecutableScenePlan":
        objects: List[SceneObjectPlan] = []
        normalizations: List[Dict[str, Any]] = []
        booleans: List[Dict[str, str]] = []
        for node_id in sorted(manifest.nodes):
            node = manifest.nodes[node_id]
            geometry = _serialized(getattr(node, "geometry", None))
            if geometry:
                for event in geometry.get("normalization_events", []):
                    normalizations.append({"node_id": node_id, **event})
            attachment = _serialized(getattr(node, "attachment", None))
            if attachment:
                st = attachment.get("socket_type")
                if st in (SocketType.BOOLEAN_CUT.value, SocketType.BOOLEAN_UNION.value, SocketType.BOOLEAN_INTERSECT.value):
                    target_id = None
                    parent = manifest.nodes.get(node.parent_id) if node.parent_id else None
                    if parent:
                        for child_id in parent.children_ids:
                            cand = manifest.nodes.get(child_id)
                            if cand and cand.attachment and cand.attachment.socket_type == SocketType.ROOT:
                                target_id = cand.node_id
                                break
                    op_map = {
                        SocketType.BOOLEAN_CUT.value: "difference",
                        SocketType.BOOLEAN_UNION.value: "union",
                        SocketType.BOOLEAN_INTERSECT.value: "intersect",
                    }
                    booleans.append({
                        "operation": op_map[st],
                        "cutter_node_id": node_id,
                        "target_node_id": target_id,
                    })
            modifiers = [
                _serialized(item) for item in (getattr(node, "modifiers", None) or [])
            ]
            objects.append(SceneObjectPlan(
                node_id=node_id,
                canonical_path=canonical_node_path(manifest, node_id),
                kind=getattr(getattr(node, "kind", None), "value", str(getattr(node, "kind", ""))),
                label=getattr(node, "label", ""),
                parent_id=getattr(node, "parent_id", None),
                children_ids=list(getattr(node, "children_ids", [])),
                geometry=geometry,
                material=_serialized(getattr(node, "material", None)),
                modifiers=modifiers,
                attachment=attachment,
                transform=_serialized(getattr(node, "transform_state", None)),
                instance_of=getattr(node, "instance_of", None),
            ))
        base = cls(
            schema_version=SCENE_PLAN_SCHEMA_VERSION,
            model_id=str(getattr(manifest, "model_id", "unknown")),
            prompt=str(getattr(manifest, "prompt", "")),
            contract=dict(getattr(manifest, "stats", {}).get("model_contract", {})),
            capabilities=capability_manifest(),
            objects=objects,
            boolean_operations=booleans,
            normalization_events=normalizations,
        )
        payload = base.to_dict(include_fingerprint=False)
        fingerprint = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        ).hexdigest()
        return cls(**{**base.__dict__, "fingerprint": fingerprint})

    def to_dict(self, *, include_fingerprint: bool = True) -> Dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "model_id": self.model_id,
            "prompt": self.prompt,
            "contract": self.contract,
            "capabilities": self.capabilities,
            "objects": [item.to_dict() for item in self.objects],
            "boolean_operations": list(self.boolean_operations),
            "normalization_events": list(self.normalization_events),
        }
        if include_fingerprint:
            payload["fingerprint"] = self.fingerprint
        return payload

    def save(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        temporary.replace(path)
        return path
