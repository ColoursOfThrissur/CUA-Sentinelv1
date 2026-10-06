"""The global, deterministic constraints shared by every modelling stage."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any, Dict


@dataclass(frozen=True)
class ModelContract:
    """A single source of truth for units, axes, and model-scale anchor."""

    overall_extent_m: float = 1.0
    units: str = "m"
    up_axis: str = "Z"
    front_axis: str = "-Y"
    category: str = "unspecified"
    style_tag: str = "unspecified"
    rests_on_surface: bool = False
    scale_source: str = "fallback"

    @classmethod
    def from_stage0(cls, stage0: Dict[str, Any] | None) -> "ModelContract":
        data = stage0 or {}
        anchor = data.get("scale_anchor_m") or {}
        try:
            extent = float(anchor.get("overall_height_or_length"))
        except (TypeError, ValueError):
            extent = 1.0
        if not 0.001 <= extent <= 10000:
            extent = 1.0
        return cls(
            overall_extent_m=extent,
            category=str(data.get("category") or "unspecified"),
            style_tag=str(data.get("style_tag") or "unspecified"),
            rests_on_surface=bool(data.get("rests_on_surface", False)),
            scale_source="stage0" if anchor.get("overall_height_or_length") is not None else "fallback",
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @property
    def fingerprint(self) -> str:
        payload = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
