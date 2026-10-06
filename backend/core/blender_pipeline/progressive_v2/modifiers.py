"""Modifier specifications and presets for progressive assembly.

Defines the modifier types, their parameters, and semantic presets
that can be applied to geometry after creation.

Modifier order matters:
1. Mirror (if symmetric)
2. Array (if repeated)
3. Subdivision Surface (smoothing)
4. Bevel (edge rounding)
5. Solidify (thickness)
6. Weighted Normal (shading fix)

Blueprint references: §6 (modifiers in manifest).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ModifierType(str, Enum):
    """Blender modifier types we support."""
    # Geometry modifiers
    SUBDIVISION = "subdivision"
    BEVEL = "bevel"
    SOLIDIFY = "solidify"
    MIRROR = "mirror"
    ARRAY = "array"
    
    # Deformation modifiers
    SIMPLE_DEFORM = "simple_deform"
    LATTICE = "lattice"
    
    # Normals/Shading
    WEIGHTED_NORMAL = "weighted_normal"
    SMOOTH = "smooth"
    
    # Special
    EDGE_SPLIT = "edge_split"
    TRIANGULATE = "triangulate"
    DECIMATE = "decimate"


@dataclass
class ModifierSpec:
    """Specification for a single modifier.
    
    Each modifier type has its own set of parameters.
    """
    type: ModifierType
    
    # Common
    name: Optional[str] = None  # Auto-generated if not provided
    apply: bool = False  # Keep live (non-destructive) by default, apply only on export
    
    # Subdivision Surface
    subdivision_levels: int = 2
    subdivision_render_levels: int = 2
    subdivision_type: str = "CATMULL_CLARK"  # or "SIMPLE"
    
    # Bevel
    bevel_width: float = 0.02  # meters
    bevel_segments: int = 3
    bevel_limit_method: str = "ANGLE"  # ANGLE, WEIGHT, VGROUP
    bevel_angle_limit: float = 30.0  # degrees
    bevel_profile: float = 0.5  # 0-1, 0.5 = round
    
    # Solidify
    solidify_thickness: float = 0.01  # meters
    solidify_offset: float = -1.0  # -1 = inward, 1 = outward
    solidify_even_thickness: bool = True
    
    # Mirror
    mirror_axis: List[bool] = field(default_factory=lambda: [True, False, False])  # X, Y, Z
    mirror_merge: bool = True
    mirror_merge_threshold: float = 0.001
    
    # Array
    array_count: int = 2
    array_offset: List[float] = field(default_factory=lambda: [1.0, 0.0, 0.0])
    array_use_relative_offset: bool = True
    
    # Simple Deform
    deform_method: str = "BEND"  # TWIST, BEND, TAPER, STRETCH
    deform_angle: float = 0.0  # radians
    deform_factor: float = 0.0
    deform_axis: str = "X"
    
    # Weighted Normal
    weighted_normal_weight: int = 50
    weighted_normal_keep_sharp: bool = True
    
    # Smooth
    smooth_factor: float = 0.5
    smooth_iterations: int = 1
    
    # Edge Split
    edge_split_angle: float = 30.0  # degrees
    
    # Decimate
    decimate_ratio: float = 0.5
    decimate_type: str = "COLLAPSE"  # COLLAPSE, UNSUBDIV, DISSOLVE
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize for JSON."""
        return {
            "type": self.type.value,
            "name": self.name,
            "apply": self.apply,
            "subdivision_levels": self.subdivision_levels,
            "subdivision_render_levels": self.subdivision_render_levels,
            "subdivision_type": self.subdivision_type,
            "bevel_width": self.bevel_width,
            "bevel_segments": self.bevel_segments,
            "bevel_limit_method": self.bevel_limit_method,
            "bevel_angle_limit": self.bevel_angle_limit,
            "bevel_profile": self.bevel_profile,
            "solidify_thickness": self.solidify_thickness,
            "solidify_offset": self.solidify_offset,
            "solidify_even_thickness": self.solidify_even_thickness,
            "mirror_axis": self.mirror_axis,
            "mirror_merge": self.mirror_merge,
            "mirror_merge_threshold": self.mirror_merge_threshold,
            "array_count": self.array_count,
            "array_offset": self.array_offset,
            "array_use_relative_offset": self.array_use_relative_offset,
            "deform_method": self.deform_method,
            "deform_angle": self.deform_angle,
            "deform_factor": self.deform_factor,
            "deform_axis": self.deform_axis,
            "weighted_normal_weight": self.weighted_normal_weight,
            "weighted_normal_keep_sharp": self.weighted_normal_keep_sharp,
            "smooth_factor": self.smooth_factor,
            "smooth_iterations": self.smooth_iterations,
            "edge_split_angle": self.edge_split_angle,
            "decimate_ratio": self.decimate_ratio,
            "decimate_type": self.decimate_type,
        }
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> ModifierSpec:
        """Deserialize from JSON."""
        return cls(
            type=ModifierType(d.get("type", "bevel")),
            name=d.get("name"),
            apply=d.get("apply", False),
            subdivision_levels=d.get("subdivision_levels", 2),
            subdivision_render_levels=d.get("subdivision_render_levels", 2),
            subdivision_type=d.get("subdivision_type", "CATMULL_CLARK"),
            bevel_width=d.get("bevel_width", 0.02),
            bevel_segments=d.get("bevel_segments", 3),
            bevel_limit_method=d.get("bevel_limit_method", "ANGLE"),
            bevel_angle_limit=d.get("bevel_angle_limit", 30.0),
            bevel_profile=d.get("bevel_profile", 0.5),
            solidify_thickness=d.get("solidify_thickness", 0.01),
            solidify_offset=d.get("solidify_offset", -1.0),
            solidify_even_thickness=d.get("solidify_even_thickness", True),
            mirror_axis=d.get("mirror_axis", [True, False, False]),
            mirror_merge=d.get("mirror_merge", True),
            mirror_merge_threshold=d.get("mirror_merge_threshold", 0.001),
            array_count=d.get("array_count", 2),
            array_offset=d.get("array_offset", [1.0, 0.0, 0.0]),
            array_use_relative_offset=d.get("array_use_relative_offset", True),
            deform_method=d.get("deform_method", "BEND"),
            deform_angle=d.get("deform_angle", 0.0),
            deform_factor=d.get("deform_factor", 0.0),
            deform_axis=d.get("deform_axis", "X"),
            weighted_normal_weight=d.get("weighted_normal_weight", 50),
            weighted_normal_keep_sharp=d.get("weighted_normal_keep_sharp", True),
            smooth_factor=d.get("smooth_factor", 0.5),
            smooth_iterations=d.get("smooth_iterations", 1),
            edge_split_angle=d.get("edge_split_angle", 30.0),
            decimate_ratio=d.get("decimate_ratio", 0.5),
            decimate_type=d.get("decimate_type", "COLLAPSE"),
        )


# ---------------------------------------------------------------------------
# Modifier Presets — semantic names for common modifier combinations
# ---------------------------------------------------------------------------

def get_modifier_preset(preset_name: str) -> List[ModifierSpec]:
    """Get a list of modifiers for a semantic preset.
    
    Presets:
    - "smooth": Subdivision for organic smoothing
    - "smooth_light": Light subdivision (1 level)
    - "beveled": Bevel edges for hard-surface look
    - "beveled_heavy": More pronounced bevel
    - "rounded": Bevel + subdivision for smooth rounded edges
    - "sharp": Edge split for sharp shading
    - "panel": Solidify for thin panels
    - "thick_panel": Thicker solidify
    - "game_ready": Triangulate + weighted normals
    - "organic": Smooth + subdivision for organic shapes
    """
    presets = {
        "smooth": [
            ModifierSpec(
                type=ModifierType.SUBDIVISION,
                subdivision_levels=2,
                subdivision_type="CATMULL_CLARK",
            ),
        ],
        
        "smooth_light": [
            ModifierSpec(
                type=ModifierType.SUBDIVISION,
                subdivision_levels=1,
                subdivision_type="CATMULL_CLARK",
            ),
        ],
        
        "beveled": [
            ModifierSpec(
                type=ModifierType.BEVEL,
                bevel_width=0.003,
                bevel_segments=3,
                bevel_angle_limit=30.0,
            ),
        ],
        
        "beveled_heavy": [
            ModifierSpec(
                type=ModifierType.BEVEL,
                bevel_width=0.006,
                bevel_segments=4,
                bevel_angle_limit=30.0,
            ),
        ],
        
        "rounded": [
            ModifierSpec(
                type=ModifierType.BEVEL,
                bevel_width=0.004,
                bevel_segments=3,
                bevel_angle_limit=30.0,
            ),
            ModifierSpec(
                type=ModifierType.SUBDIVISION,
                subdivision_levels=1,
                subdivision_type="CATMULL_CLARK",
            ),
        ],
        
        "sharp": [
            ModifierSpec(
                type=ModifierType.EDGE_SPLIT,
                edge_split_angle=30.0,
            ),
        ],
        
        "panel": [
            ModifierSpec(
                type=ModifierType.SOLIDIFY,
                solidify_thickness=0.005,
                solidify_offset=-1.0,
            ),
        ],
        
        "thick_panel": [
            ModifierSpec(
                type=ModifierType.SOLIDIFY,
                solidify_thickness=0.02,
                solidify_offset=-1.0,
            ),
        ],
        
        "game_ready": [
            ModifierSpec(
                type=ModifierType.TRIANGULATE,
                apply=False,
            ),
            ModifierSpec(
                type=ModifierType.WEIGHTED_NORMAL,
                weighted_normal_weight=50,
                weighted_normal_keep_sharp=True,
            ),
        ],
        
        "organic": [
            ModifierSpec(
                type=ModifierType.SMOOTH,
                smooth_factor=0.5,
                smooth_iterations=2,
            ),
            ModifierSpec(
                type=ModifierType.SUBDIVISION,
                subdivision_levels=2,
                subdivision_type="CATMULL_CLARK",
            ),
        ],
        
        "low_poly": [
            ModifierSpec(
                type=ModifierType.DECIMATE,
                decimate_ratio=0.5,
                decimate_type="COLLAPSE",
            ),
        ],
    }
    
    return presets.get(preset_name, [])


def get_modifiers_for_style(style_hint: str) -> List[ModifierSpec]:
    """Infer modifiers from a style description.
    
    Maps semantic descriptions to modifier presets:
    - "smooth", "organic", "soft" → smooth preset
    - "hard surface", "mechanical", "industrial" → beveled preset
    - "rounded", "soft edges" → rounded preset
    - "sharp", "angular", "faceted" → sharp preset
    - "thin", "panel", "plate" → panel preset
    """
    style_lower = style_hint.lower()
    
    if any(w in style_lower for w in ["organic", "soft", "natural", "curved"]):
        return get_modifier_preset("smooth")
    
    if any(w in style_lower for w in ["smooth"]):
        return get_modifier_preset("rounded")
    
    if any(w in style_lower for w in ["rounded", "soft edge", "smooth edge"]):
        return get_modifier_preset("rounded")
    
    if any(w in style_lower for w in ["hard surface", "mechanical", "industrial", "metal", "machine"]):
        return get_modifier_preset("beveled")
    
    if any(w in style_lower for w in ["sharp", "angular", "faceted", "low poly"]):
        return get_modifier_preset("sharp")
    
    if any(w in style_lower for w in ["thin", "panel", "plate", "sheet"]):
        return get_modifier_preset("panel")
    
    if any(w in style_lower for w in ["game", "realtime", "optimized"]):
        return get_modifier_preset("game_ready")
    
    # Default: light bevel for most objects
    return get_modifier_preset("beveled")


def ensure_manifest_modifiers(manifest: Any, *, enabled: bool = True) -> Dict[str, Any]:
    """Resolve style-driven modifiers before the executable plan freezes."""
    from .node_types import NodeKind

    assigned: List[str] = []
    explicit: List[str] = []
    disabled: List[str] = []
    for node in manifest.nodes.values():
        if node.kind not in (NodeKind.PART, NodeKind.DEFINITION):
            continue
        stage_outputs = getattr(node, "stage_outputs", None)
        if stage_outputs is None:
            stage_outputs = {}
            node.stage_outputs = stage_outputs
        stage_outputs["_modifiers_resolved"] = True
        if getattr(node, "modifiers", None):
            explicit.append(node.node_id)
            continue
        if not enabled:
            disabled.append(node.node_id)
            continue
        style = str(stage_outputs.get("decomposition_hint", {}).get("style_hint", ""))
        node.modifiers = get_modifiers_for_style(style) if style else []
        if node.modifiers:
            assigned.append(node.node_id)
    report = {
        "enabled": enabled, "assigned_node_ids": assigned,
        "explicit_node_ids": explicit, "disabled_node_ids": disabled,
    }
    if hasattr(manifest, "record_event"):
        manifest.record_event("modifiers_resolved", details=report)
    return report
