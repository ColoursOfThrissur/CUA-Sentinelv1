"""V3 design and spatial checks on the compiled scene contract."""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from typing import Any, Dict, List, Tuple

from .envelope import xy_bounds
from .scene import Scene


class SceneAudit:
    @staticmethod
    def run(scene: Scene) -> Dict[str, Any]:
        errors: List[str] = []
        warnings: List[str] = []
        ids = {part.id for part in scene.parts}
        paths = [part.canonical_path for part in scene.parts]
        if len(ids) != len(scene.parts):
            errors.append("duplicate part identity")
        if len(set(paths)) != len(paths):
            errors.append("duplicate canonical path")
        positions: Dict[Tuple[float, float, float], List[Any]] = defaultdict(list)
        for part in scene.parts:
            if not part.geometry or not part.material:
                errors.append(f"incomplete geometry or material: {part.label}")
            if part.parent_id and part.parent_id not in ids:
                errors.append(f"missing parent for {part.label}: {part.parent_id}")
            if not all(math.isfinite(value) for value in part.transform.position + part.transform.rotation):
                errors.append(f"non-finite transform: {part.label}")
                continue
            positions[tuple(round(value, 5) for value in part.transform.position)].append(part)
        for position, nodes in positions.items():
            counts = Counter(part.component_key for part in nodes)
            if any(count > 1 for count in counts.values()):
                errors.append(f"repeated parts share placement {position}: {', '.join(part.label for part in nodes)}")
            elif len(nodes) > 2 and any(not set(part.relation.get("kinds", [])) & {"center", "inside"} for part in nodes):
                errors.append(f"independent parts share placement {position}: {', '.join(part.label for part in nodes)}")
        by_id = {part.id: part for part in scene.parts}
        for part in scene.parts:
            seen = {part.id}
            parent_id = part.parent_id
            while parent_id:
                if parent_id in seen:
                    errors.append(f"attachment cycle involving {part.label}")
                    break
                seen.add(parent_id)
                parent_id = by_id[parent_id].parent_id if parent_id in by_id else None
        bounds = xy_bounds(scene)
        extent = scene.overall_extent_m
        if extent:
            width = max(bounds[1] - bounds[0], bounds[3] - bounds[2])
            if width > extent + .002:
                errors.append(f"geometry exceeds declared {extent:.3f} m width: {width:.3f} m")
        return {"passed": not errors, "errors": errors[:16], "warnings": warnings,
                "checked_parts": len(scene.parts), "unique_slots": len(positions), "xy_bounds": bounds}
