"""Authoritative capability boundary for the frozen Blender transaction.

Node/primitive enums describe the long-term scene language.  This registry
describes the smaller subset the active transaction can actually compile.
Keeping those two ideas separate prevents a declared future feature from being
silently substituted with unrelated geometry.
"""

from __future__ import annotations

from typing import Any, Dict, List, Set

from .modifiers import ModifierType
from .node_types import PrimitiveType


SCENE_PLAN_SCHEMA_VERSION = 3

SUPPORTED_PRIMITIVES: Set[PrimitiveType] = {
    PrimitiveType.BOX, PrimitiveType.SPHERE, PrimitiveType.CYLINDER,
    PrimitiveType.CONE, PrimitiveType.TORUS, PrimitiveType.PLANE,
    PrimitiveType.HEMISPHERE, PrimitiveType.U_SHAPE, PrimitiveType.WEDGE,
    PrimitiveType.PYRAMID, PrimitiveType.PRISM, PrimitiveType.CAPSULE,
}

# Lattice needs an external lattice object and is therefore deliberately not
# enabled until it has a typed companion-definition compiler.
SUPPORTED_MODIFIERS: Set[str] = {
    ModifierType.SUBDIVISION.value, ModifierType.BEVEL.value,
    ModifierType.SOLIDIFY.value, ModifierType.MIRROR.value,
    ModifierType.ARRAY.value, ModifierType.SIMPLE_DEFORM.value,
    ModifierType.WEIGHTED_NORMAL.value, ModifierType.SMOOTH.value,
    ModifierType.EDGE_SPLIT.value, ModifierType.TRIANGULATE.value,
    ModifierType.DECIMATE.value,
}


def validate_transaction_capabilities(node: Any) -> List[str]:
    """Return explicit errors for features absent from the active compiler."""
    errors: List[str] = []
    geo = getattr(node, "geometry", None)
    primitive = getattr(geo, "primitive", None)
    if primitive is not None and primitive not in SUPPORTED_PRIMITIVES:
        name = getattr(primitive, "value", str(primitive))
        errors.append(f"part '{node.label}' uses unsupported transaction primitive '{name}'")

    for modifier in getattr(node, "modifiers", []) or []:
        mod_type = modifier.get("type") if isinstance(modifier, dict) else getattr(getattr(modifier, "type", None), "value", None)
        if mod_type not in SUPPORTED_MODIFIERS:
            errors.append(f"part '{node.label}' uses unsupported transaction modifier '{mod_type}'")

    material = getattr(node, "material", None)
    if material:
        if getattr(material, "node_tree_name", None):
            errors.append(f"part '{node.label}' requests custom material node tree; use a supported material template")
        for field in ("metallic", "roughness", "transmission", "subsurface", "clearcoat", "sheen", "specular", "specular_tint", "alpha", "anisotropy"):
            value = getattr(material, field, 0.0)
            if not isinstance(value, (int, float)) or not 0.0 <= value <= 1.0:
                errors.append(f"part '{node.label}' has invalid material {field}")
        if not isinstance(getattr(material, "ior", None), (int, float)) or not 1.0 <= material.ior <= 3.0:
            errors.append(f"part '{node.label}' has invalid material ior")
        if not isinstance(getattr(material, "normal_strength", None), (int, float)) or not 0.0 <= material.normal_strength <= 10.0:
            errors.append(f"part '{node.label}' has invalid material normal_strength")
        if getattr(material, "blend_mode", "opaque") not in {"opaque", "dithered", "blended"}:
            errors.append(f"part '{node.label}' has invalid material blend_mode")
        color = getattr(material, "base_color", None)
        if not isinstance(color, list) or len(color) not in {3, 4} or not all(isinstance(v, (int, float)) and 0.0 <= v <= 1.0 for v in color):
            errors.append(f"part '{node.label}' has invalid material base_color")
        for field in ("emission_color", "subsurface_color"):
            color = getattr(material, field, None)
            if color is not None and (
                not isinstance(color, list)
                or len(color) not in {3, 4}
                or not all(isinstance(v, (int, float)) and 0.0 <= v <= 1.0 for v in color)
            ):
                errors.append(f"part '{node.label}' has invalid material {field}")
    return errors


def capability_manifest() -> Dict[str, Any]:
    """A serializable record persisted with a frozen plan for traceability."""
    return {
        "schema_version": SCENE_PLAN_SCHEMA_VERSION,
        "geometry": sorted(primitive.value for primitive in SUPPORTED_PRIMITIVES),
        "modifiers": sorted(SUPPORTED_MODIFIERS),
        "material_template": "principled_pbr_v1",
    }


def planner_primitive_vocabulary() -> str:
    """Return the exact primitive vocabulary exposed to planning prompts."""
    return ", ".join(sorted(primitive.value for primitive in SUPPORTED_PRIMITIVES))
