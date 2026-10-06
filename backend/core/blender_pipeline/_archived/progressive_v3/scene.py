"""V3's own serializable scene contract and public build result."""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class BuildStatus(str, Enum):
    IN_PROGRESS = "IN_PROGRESS"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


@dataclass
class Transform:
    position: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    rotation: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    scale: List[float] = field(default_factory=lambda: [1.0, 1.0, 1.0])


@dataclass
class Geometry:
    primitive: str
    size: Optional[List[float]] = None
    radius: Optional[float] = None
    radius2: Optional[float] = None
    depth: Optional[float] = None
    major_radius: Optional[float] = None
    minor_radius: Optional[float] = None
    segments: int = 32


@dataclass
class Material:
    name: str
    base_color: List[float]
    metallic: float = 0.0
    roughness: float = 0.5
    transmission: float = 0.0
    emission_color: Optional[List[float]] = None
    emission_strength: float = 0.0


@dataclass
class Modifier:
    kind: str
    parameters: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ScenePart:
    id: str
    component_key: str
    instance_index: int
    label: str
    canonical_path: str
    geometry: Geometry
    material: Material
    modifiers: List[Modifier] = field(default_factory=list)
    transform: Transform = field(default_factory=Transform)
    parent_id: Optional[str] = None
    relation: Dict[str, Any] = field(default_factory=dict)
    blender_name: Optional[str] = None
    readback_bbox: Optional[Dict[str, List[float]]] = None


@dataclass
class Scene:
    model_id: str
    prompt: str
    parts: List[ScenePart] = field(default_factory=list)
    overall_extent_m: Optional[float] = None
    status: BuildStatus = BuildStatus.IN_PROGRESS
    stats: Dict[str, Any] = field(default_factory=dict)
    events: List[Dict[str, Any]] = field(default_factory=list)
    schema_version: int = 3
    created_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

    @classmethod
    def create(cls, prompt: str, model_id: Optional[str] = None) -> "Scene":
        return cls(model_id or f"m_{uuid.uuid4().hex[:10]}", prompt)

    def get_parts(self) -> List[ScenePart]:
        return self.parts

    @property
    def nodes(self) -> Dict[str, ScenePart]:
        return {part.id: part for part in self.parts}

    def record_event(self, kind: str, details: Optional[Dict[str, Any]] = None) -> None:
        self.events.append({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "type": kind, "details": details or {}})

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data

    def save(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        tmp.replace(path)
        return path


@dataclass
class BuildResult:
    success: bool
    manifest: Scene
    completion_status: BuildStatus
    total_nodes: int = 0
    verified_nodes: int = 0
    failed_nodes: int = 0
    skipped_nodes: int = 0
    llm_calls: int = 0
    blender_ops: int = 0
    build_time_seconds: float = 0.0
    errors: List[str] = field(default_factory=list)
    blender_objects: List[str] = field(default_factory=list)
    output_file: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success, "completion_status": self.completion_status.value,
            "total_nodes": self.total_nodes, "verified_nodes": self.verified_nodes,
            "failed_nodes": self.failed_nodes, "skipped_nodes": self.skipped_nodes,
            "llm_calls": self.llm_calls, "blender_ops": self.blender_ops,
            "build_time_seconds": self.build_time_seconds, "errors": self.errors,
            "blender_objects": self.blender_objects, "output_file": self.output_file,
            "spatial_verification_failed": bool(self.manifest.stats.get("spatial_verification_failed")),
            "spatial_errors": self.manifest.stats.get("spatial_errors", []),
        }
