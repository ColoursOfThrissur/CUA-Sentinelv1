"""Compile one typed model intent into V3's executable scene contract."""
from __future__ import annotations

import math
from typing import Dict, List

from .envelope import fit_xy
from .identity import canonical_path, slug
from .intent import IntentComponent, ModelIntent
from .layout import RelationLayout
from .scene import Geometry, Material, Modifier, Scene, ScenePart


def _positive(value: object, fallback: float) -> float:
    if value is None:
        return fallback
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid positive dimension: {value!r}") from exc
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"invalid positive dimension: {value!r}")
    return number


class IntentCompiler:
    @classmethod
    def compile(cls, intent: ModelIntent, model_id: str | None = None) -> Scene:
        if not intent.components:
            raise ValueError("V3 intent has no components")
        if sum(component.count for component in intent.components) > 400:
            raise ValueError("V3 plan exceeds the 400-part transaction limit")
        scene = Scene.create(intent.prompt, model_id)
        extent = intent.overall_extent_m or .6
        scene.overall_extent_m = intent.overall_extent_m
        scene.stats.update({"pipeline": "progressive_v3", "overall_extent_m": intent.overall_extent_m, "component_count": len(intent.components)})
        by_key: Dict[str, List[ScenePart]] = {}
        for component in intent.components:
            parts: List[ScenePart] = []
            for index in range(component.count):
                path = canonical_path(component.parent, component.key, index)
                part = ScenePart(
                    id=f"{scene.model_id}_{slug(component.key)}_{index + 1:03d}",
                    component_key=component.key, instance_index=index,
                    label=f"v3_{slug(component.key)}_{index + 1:02d}",
                    canonical_path=path,
                    geometry=cls._geometry(component, extent),
                    material=cls._material(component),
                    modifiers=cls._modifiers(component, extent),
                )
                parts.append(part)
                scene.parts.append(part)
            by_key[component.key] = parts
        RelationLayout.resolve(intent, by_key, extent)
        if scene.overall_extent_m:
            fit_xy(scene, scene.overall_extent_m)
        scene.record_event("v3_compiled", {"parts": len(scene.parts), "relations": len(intent.relations), "schema_version": scene.schema_version})
        return scene

    @classmethod
    def _geometry(cls, component: IntentComponent, extent: float) -> Geometry:
        primitive = component.primitive
        values = component.parameters
        segments = max(8, min(128, int(_positive(values.get("segments"), 32))))
        if primitive in {"box", "wedge", "plane"}:
            default = [extent * .42, extent * .3, extent * .18] if primitive != "plane" else [extent * .3, extent * .3, .002]
            raw = values.get("size")
            if raw is not None and (not isinstance(raw, list) or len(raw) != 3):
                raise ValueError(f"{component.key} requires size [x, y, z]")
            size = [_positive(value, default[i]) for i, value in enumerate(raw)] if raw is not None else default
            return Geometry(primitive, size=size, segments=segments)
        if primitive in {"cylinder", "cone", "capsule", "prism", "pyramid"}:
            radius = _positive(values.get("radius"), extent * .055)
            depth = _positive(values.get("depth"), extent * .2)
            if primitive == "capsule":
                depth = max(depth, radius * 2.1)
            return Geometry(primitive, radius=radius, radius2=_positive(values.get("radius2"), radius * .55) if primitive == "cone" else None, depth=depth, segments=segments)
        if primitive in {"sphere", "hemisphere", "circle"}:
            return Geometry(primitive, radius=_positive(values.get("radius"), extent * .07), segments=segments)
        if primitive in {"torus", "u_shape"}:
            return Geometry(primitive, major_radius=_positive(values.get("major_radius"), extent * .1), minor_radius=_positive(values.get("minor_radius"), extent * .012), segments=segments)
        raise ValueError(f"V3 primitive {primitive!r} is not implemented")

    @staticmethod
    def _material(component: IntentComponent) -> Material:
        name = component.material or "neutral painted surface"
        text = name.lower()
        colors = {
            "charcoal": [.04, .045, .055, 1.0], "black": [.015, .017, .02, 1.0],
            "white": [.82, .83, .82, 1.0], "silver": [.55, .59, .64, 1.0],
            "blue": [.025, .17, .75, 1.0], "red": [.8, .025, .02, 1.0],
            "green": [.02, .55, .12, 1.0], "yellow": [.9, .6, .025, 1.0],
            "orange": [.85, .22, .025, 1.0], "gold": [.7, .45, .08, 1.0],
        }
        color = next((value for token, value in colors.items() if token in text), [.35, .4, .45, 1.0])
        explicit = component.parameters.get("color")
        if explicit is not None:
            if not isinstance(explicit, list) or len(explicit) not in {3, 4}:
                raise ValueError(f"{component.key} color must have three or four numeric channels")
            try:
                color = [max(0.0, min(1.0, float(channel))) for channel in explicit[:3]] + [1.0]
            except (TypeError, ValueError) as exc:
                raise ValueError(f"invalid color for {component.key}") from exc
        glass = "glass" in text or "transparent" in text
        metal = any(word in text for word in ("steel", "metal", "chrome", "aluminum", "aluminium", "silver", "gold"))
        emissive = any(word in text for word in ("emissive", "led", "glowing", "neon"))
        roughness = .82 if "rubber" in text else .68 if "matte" in text else .34 if "brushed" in text else .12 if "glossy" in text or glass else .42
        return Material(name, color, metallic=.8 if metal else 0.0, roughness=roughness,
                        transmission=.8 if glass else 0.0,
                        emission_color=color[:3] if emissive else None,
                        emission_strength=2.0 if emissive else 0.0)

    @staticmethod
    def _modifiers(component: IntentComponent, extent: float) -> List[Modifier]:
        style = (component.style + " " + component.display_label).lower()
        modifiers = []
        if any(word in style for word in ("bevel", "rounded", "soft edge")):
            modifiers.append(Modifier("bevel", {"width": extent * .004, "segments": 3}))
        if any(word in style for word in ("smooth", "curved", "glossy")):
            modifiers.append(Modifier("smooth", {}))
        raw = component.parameters.get("modifiers")
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, dict) and item.get("kind") in {"bevel", "subdivision", "solidify", "smooth"}:
                    modifiers.append(Modifier(item["kind"], dict(item.get("parameters") or {})))
        return modifiers
