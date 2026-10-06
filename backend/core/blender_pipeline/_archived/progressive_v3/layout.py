"""Graph layout of repeated V3 parts in world-space metres."""
from __future__ import annotations

import math
from typing import Dict, List

from .intent import IntentComponent, IntentRelation, ModelIntent
from .scene import ScenePart


def _positive(value: object, fallback: float) -> float:
    if value is None:
        return fallback
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid positive placement distance: {value!r}") from exc
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"invalid positive placement distance: {value!r}")
    return number


def _half(part: ScenePart, axis: int) -> float:
    geo = part.geometry
    if geo.size:
        return geo.size[axis] / 2
    if geo.primitive in {"cylinder", "cone", "capsule", "prism", "pyramid"}:
        return (geo.depth or 0) / 2 if axis == 2 else (geo.radius or 0)
    if geo.primitive in {"torus", "u_shape"}:
        return (geo.major_radius or 0) + (geo.minor_radius or 0) if axis < 2 else (geo.minor_radius or 0)
    return geo.radius or 0


class RelationLayout:
    @classmethod
    def resolve(cls, intent: ModelIntent, by_key: Dict[str, List[ScenePart]], extent: float) -> None:
        """Place each component after its target; reject cycles and unknown edges."""
        components = {component.key: component for component in intent.components}
        relations: Dict[str, List[IntentRelation]] = {}
        for relation in intent.relations:
            relations.setdefault(relation.subject, []).append(relation)
        root = intent.components[0].key
        resolved: set[str] = set()
        visiting: set[str] = set()

        def place(key: str) -> None:
            if key in resolved:
                return
            if key in visiting:
                raise ValueError(f"attachment cycle involving {key}")
            if key not in by_key:
                raise ValueError(f"unknown component {key}")
            visiting.add(key)
            edges = relations.get(key, [])
            if key != root and not edges:
                raise ValueError(f"component {key} has no attachment relation")
            target_keys = {edge.target for edge in edges}
            if len(target_keys) > 1:
                raise ValueError(f"component {key} has multiple attachment targets: {sorted(target_keys)}")
            target_key = next(iter(target_keys)) if target_keys else None
            if target_key:
                if target_key not in by_key:
                    raise ValueError(f"component {key} targets unknown component {target_key}")
                place(target_key)
            targets = by_key.get(target_key or "", [])
            parts = by_key[key]
            component = components[key]
            for index, part in enumerate(parts):
                target_index = cls._target_index(index, len(parts), len(targets))
                target = targets[target_index] if targets else None
                anchor = target.transform.position if target else [0.0, 0.0, 0.0]
                offset = [0.0, 0.0, 0.0]
                radial_angle = None
                for edge in edges:
                    delta, angle = cls._delta(edge, index, len(parts), target_index, targets, extent)
                    offset = [offset[axis] + delta[axis] for axis in range(3)]
                    if angle is not None:
                        radial_angle = angle
                group_size = cls._group_size(len(parts), len(targets))
                if group_size > 1 and not any(edge.kind == "radial" for edge in edges):
                    slot = index % group_size
                    angle = 2 * math.pi * slot / group_size
                    spread = _positive(edges[0].parameters.get("spread_radius") if edges else None, extent * .075)
                    offset[0] += spread * math.cos(angle)
                    offset[1] += spread * math.sin(angle)
                part.transform.position = [anchor[axis] + offset[axis] for axis in range(3)]
                if radial_angle is not None:
                    part.transform.rotation[2] = radial_angle
                if component.parameters.get("orientation") == "horizontal":
                    part.transform.rotation[1] = math.pi / 2
                    if target and radial_angle is None:
                        part.transform.rotation[2] = target.transform.rotation[2]
                part.parent_id = target.id if target else None
                part.relation = {"kinds": [edge.kind for edge in edges], "target": target_key, "target_index": target_index, "slot": index % max(1, group_size)}
            visiting.remove(key)
            resolved.add(key)

        for component in intent.components:
            place(component.key)

    @staticmethod
    def _group_size(subject_count: int, target_count: int) -> int:
        if target_count and subject_count % target_count == 0:
            return max(1, subject_count // target_count)
        return subject_count

    @staticmethod
    def _target_index(index: int, subject_count: int, target_count: int) -> int:
        if target_count <= 1:
            return 0
        if subject_count == target_count:
            return index
        if subject_count > target_count and subject_count % target_count == 0:
            return index // (subject_count // target_count)
        return index % target_count

    @classmethod
    def _delta(cls, edge: IntentRelation, index: int, count: int, target_index: int, targets: List[ScenePart], extent: float) -> tuple[List[float], float | None]:
        target = targets[target_index] if targets else None
        distance = _positive(edge.parameters.get("distance"), extent * .12)
        if edge.kind == "radial":
            group_size = cls._group_size(count, len(targets))
            slot = index % group_size
            angle = 2 * math.pi * slot / group_size
            default_radius = extent * (.07 if len(targets) > 1 else .3)
            radius = _positive(edge.parameters.get("radius"), default_radius)
            if len(targets) > 1:
                enclosing = target.geometry.major_radius if target else None
                radius = min(radius, (enclosing or extent * .07) * .7)
            return [radius * math.cos(angle), radius * math.sin(angle), 0.0], angle
        if edge.kind == "outward":
            anchor = target.transform.position if target else [0.0, 0.0, 0.0]
            norm = math.hypot(anchor[0], anchor[1])
            direction = (anchor[0] / norm, anchor[1] / norm) if norm > 1e-8 else (1.0, 0.0)
            distance = _positive(edge.parameters.get("distance"), extent * .08)
            return [direction[0] * distance, direction[1] * distance, 0.0], None
        direction = {
            "above": (0, 0, 1), "below": (0, 0, -1),
            "front": (0, -1, 0), "back": (0, 1, 0),
            "left": (-1, 0, 0), "right": (1, 0, 0),
        }.get(edge.kind, (0, 0, 0))
        if target and any(direction):
            axis = next(i for i, value in enumerate(direction) if value)
            distance = _positive(edge.parameters.get("distance"), _half(target, axis) + extent * .025)
        return [distance * value for value in direction], None
