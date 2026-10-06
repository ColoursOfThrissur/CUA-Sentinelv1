"""Material presets and specifications for progressive assembly.

Defines PBR material presets that map semantic descriptions to
Principled BSDF shader values.

Material properties:
- base_color: RGBA [0-1]
- metallic: 0 (dielectric) to 1 (metal)
- roughness: 0 (mirror) to 1 (diffuse)
- emission_color: RGB [0-1]
- emission_strength: 0+ (watts)
- transmission: 0 (opaque) to 1 (glass)
- ior: Index of refraction (1.45 for glass)
- alpha: 0 (transparent) to 1 (opaque)
- subsurface: 0-1 for SSS effect
- subsurface_color: RGB for SSS

Blueprint references: §6 (materials in manifest).
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Dict, List, Optional


@dataclass
class MaterialPreset:
    """A named material preset with full PBR properties."""
    name: str
    
    # Base PBR
    base_color: List[float] = field(default_factory=lambda: [0.8, 0.8, 0.8, 1.0])
    metallic: float = 0.0
    roughness: float = 0.5
    
    # Emission
    emission_color: Optional[List[float]] = None
    emission_strength: float = 0.0
    
    # Transmission (glass)
    transmission: float = 0.0
    ior: float = 1.45
    
    # Alpha
    alpha: float = 1.0
    
    # Subsurface scattering
    subsurface: float = 0.0
    subsurface_color: Optional[List[float]] = None
    
    # Specular
    specular: float = 0.5
    specular_tint: float = 0.0
    
    # Clearcoat (for car paint, etc.)
    clearcoat: float = 0.0
    clearcoat_roughness: float = 0.03
    
    # Sheen (for fabric)
    sheen: float = 0.0
    sheen_tint: float = 0.5

    # Anisotropy (for brushed metal)
    anisotropy: float = 0.0
    anisotropy_rotation: float = 0.0

    # Procedural Shader Texture (Wood grain, brushed metal, leather grain, marble vein, concrete noise, etc.)
    procedural_texture: Optional[str] = None  # "wood", "brushed_metal", "leather", "marble", "noise", "hammered"
    procedural_params: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize for JSON."""
        d = {
            "name": self.name,
            "base_color": self.base_color,
            "metallic": self.metallic,
            "roughness": self.roughness,
            "transmission": self.transmission,
            "ior": self.ior,
            "alpha": self.alpha,
            "subsurface": self.subsurface,
            "specular": self.specular,
            "specular_tint": self.specular_tint,
            "clearcoat": self.clearcoat,
            "clearcoat_roughness": self.clearcoat_roughness,
            "sheen": self.sheen,
            "sheen_tint": self.sheen_tint,
            "anisotropy": self.anisotropy,
            "anisotropy_rotation": self.anisotropy_rotation,
        }
        if self.procedural_texture:
            d["procedural_texture"] = self.procedural_texture
            d["procedural_params"] = self.procedural_params
        if self.emission_color:
            d["emission_color"] = self.emission_color
            d["emission_strength"] = self.emission_strength
        if self.subsurface_color:
            d["subsurface_color"] = self.subsurface_color
        return d


# ---------------------------------------------------------------------------
# Material Preset Library
# ---------------------------------------------------------------------------

MATERIAL_PRESETS: Dict[str, MaterialPreset] = {
    # ── Metals ────────────────────────────────────────────────────────────
    "polished_steel": MaterialPreset(
        name="polished_steel",
        base_color=[0.7, 0.7, 0.72, 1.0],
        metallic=1.0,
        roughness=0.1,
    ),
    "brushed_steel": MaterialPreset(
        name="brushed_steel",
        base_color=[0.65, 0.65, 0.67, 1.0],
        metallic=1.0,
        roughness=0.35,
        anisotropy=0.8,
        procedural_texture="brushed_metal",
        procedural_params={"scale": 35.0, "stretch": 60.0, "strength": 0.04},
    ),
    "brushed_aluminum": MaterialPreset(
        name="brushed_aluminum",
        base_color=[0.85, 0.85, 0.87, 1.0],
        metallic=1.0,
        roughness=0.3,
        anisotropy=0.75,
        procedural_texture="brushed_metal",
        procedural_params={"scale": 40.0, "stretch": 70.0, "strength": 0.035},
    ),
    "polished_aluminum": MaterialPreset(
        name="polished_aluminum",
        base_color=[0.9, 0.9, 0.92, 1.0],
        metallic=1.0,
        roughness=0.05,
    ),
    "copper": MaterialPreset(
        name="copper",
        base_color=[0.95, 0.64, 0.54, 1.0],
        metallic=1.0,
        roughness=0.25,
    ),
    "brass": MaterialPreset(
        name="brass",
        base_color=[0.88, 0.73, 0.35, 1.0],
        metallic=1.0,
        roughness=0.3,
    ),
    "gold": MaterialPreset(
        name="gold",
        base_color=[1.0, 0.84, 0.0, 1.0],
        metallic=1.0,
        roughness=0.2,
    ),
    "chrome": MaterialPreset(
        name="chrome",
        base_color=[0.95, 0.95, 0.95, 1.0],
        metallic=1.0,
        roughness=0.02,
    ),
    "iron": MaterialPreset(
        name="iron",
        base_color=[0.4, 0.4, 0.42, 1.0],
        metallic=1.0,
        roughness=0.5,
    ),
    "rusty_metal": MaterialPreset(
        name="rusty_metal",
        base_color=[0.5, 0.3, 0.2, 1.0],
        metallic=0.6,
        roughness=0.8,
    ),
    
    # ── Plastics ──────────────────────────────────────────────────────────
    "glossy_plastic": MaterialPreset(
        name="glossy_plastic",
        base_color=[0.8, 0.8, 0.8, 1.0],
        metallic=0.0,
        roughness=0.15,
        specular=0.5,
    ),
    "matte_plastic": MaterialPreset(
        name="matte_plastic",
        base_color=[0.7, 0.7, 0.7, 1.0],
        metallic=0.0,
        roughness=0.6,
    ),
    "glossy_plastic_black": MaterialPreset(
        name="glossy_plastic_black",
        base_color=[0.02, 0.02, 0.02, 1.0],
        metallic=0.0,
        roughness=0.1,
    ),
    "glossy_plastic_white": MaterialPreset(
        name="glossy_plastic_white",
        base_color=[0.95, 0.95, 0.95, 1.0],
        metallic=0.0,
        roughness=0.15,
    ),
    "rubber": MaterialPreset(
        name="rubber",
        base_color=[0.15, 0.15, 0.15, 1.0],
        metallic=0.0,
        roughness=0.9,
    ),
    "rubber_red": MaterialPreset(
        name="rubber_red",
        base_color=[0.6, 0.1, 0.1, 1.0],
        metallic=0.0,
        roughness=0.85,
    ),
    "silicone": MaterialPreset(
        name="silicone",
        base_color=[0.8, 0.8, 0.82, 1.0],
        metallic=0.0,
        roughness=0.4,
        subsurface=0.1,
    ),
    
    # ── Wood ──────────────────────────────────────────────────────────────
    "wood_light": MaterialPreset(
        name="wood_light",
        base_color=[0.76, 0.6, 0.42, 1.0],
        metallic=0.0,
        roughness=0.6,
        procedural_texture="wood",
        procedural_params={"scale": 18.0, "distortion": 3.5, "detail": 3.0, "strength": 0.12},
    ),
    "wood_dark": MaterialPreset(
        name="wood_dark",
        base_color=[0.35, 0.22, 0.12, 1.0],
        metallic=0.0,
        roughness=0.55,
        procedural_texture="wood",
        procedural_params={"scale": 16.0, "distortion": 4.0, "detail": 3.0, "strength": 0.14},
    ),
    "wood_oak": MaterialPreset(
        name="wood_oak",
        base_color=[0.65, 0.45, 0.25, 1.0],
        metallic=0.0,
        roughness=0.5,
        procedural_texture="wood",
        procedural_params={"scale": 15.0, "distortion": 3.8, "detail": 3.0, "strength": 0.15},
    ),
    "wood_walnut": MaterialPreset(
        name="wood_walnut",
        base_color=[0.4, 0.28, 0.18, 1.0],
        metallic=0.0,
        roughness=0.45,
        procedural_texture="wood",
        procedural_params={"scale": 14.0, "distortion": 4.2, "detail": 3.2, "strength": 0.15},
    ),
    "wood_painted_white": MaterialPreset(
        name="wood_painted_white",
        base_color=[0.92, 0.9, 0.88, 1.0],
        metallic=0.0,
        roughness=0.4,
        procedural_texture="wood",
        procedural_params={"scale": 20.0, "distortion": 2.5, "detail": 2.0, "strength": 0.05},
    ),
    "wood_varnished": MaterialPreset(
        name="wood_varnished",
        base_color=[0.55, 0.35, 0.2, 1.0],
        metallic=0.0,
        roughness=0.2,
        clearcoat=0.3,
        procedural_texture="wood",
        procedural_params={"scale": 15.0, "distortion": 3.5, "detail": 3.0, "strength": 0.08},
    ),
    
    # ── Glass & Transparent ───────────────────────────────────────────────
    "glass_clear": MaterialPreset(
        name="glass_clear",
        base_color=[0.8, 0.95, 1.0, 0.05],
        metallic=0.0,
        roughness=0.0,
        transmission=1.0,
        ior=1.45,
        alpha=0.05,
    ),
    "glass_frosted": MaterialPreset(
        name="glass_frosted",
        base_color=[0.9, 0.92, 0.95, 0.15],
        metallic=0.0,
        roughness=0.25,
        transmission=0.9,
        ior=1.45,
        alpha=0.15,
    ),
    "glass_tinted": MaterialPreset(
        name="glass_tinted",
        base_color=[0.15, 0.25, 0.3, 0.1],
        metallic=0.0,
        roughness=0.0,
        transmission=0.85,
        ior=1.45,
        alpha=0.1,
    ),
    "acrylic": MaterialPreset(
        name="acrylic",
        base_color=[0.95, 0.97, 1.0, 0.08],
        metallic=0.0,
        roughness=0.05,
        transmission=0.95,
        ior=1.49,
        alpha=0.08,
    ),
    
    # ── Fabric ────────────────────────────────────────────────────────────
    "fabric_cotton": MaterialPreset(
        name="fabric_cotton",
        base_color=[0.85, 0.82, 0.78, 1.0],
        metallic=0.0,
        roughness=0.9,
        sheen=0.3,
    ),
    "fabric_velvet": MaterialPreset(
        name="fabric_velvet",
        base_color=[0.3, 0.1, 0.15, 1.0],
        metallic=0.0,
        roughness=0.95,
        sheen=0.8,
        sheen_tint=0.5,
    ),
    "leather": MaterialPreset(
        name="leather",
        base_color=[0.35, 0.2, 0.12, 1.0],
        metallic=0.0,
        roughness=0.6,
        specular=0.3,
        procedural_texture="leather",
        procedural_params={"scale": 120.0, "strength": 0.12},
    ),
    "leather_black": MaterialPreset(
        name="leather_black",
        base_color=[0.05, 0.05, 0.05, 1.0],
        metallic=0.0,
        roughness=0.55,
        specular=0.35,
        procedural_texture="leather",
        procedural_params={"scale": 130.0, "strength": 0.12},
    ),
    
    # ── Stone & Concrete ──────────────────────────────────────────────────
    "concrete": MaterialPreset(
        name="concrete",
        base_color=[0.55, 0.53, 0.5, 1.0],
        metallic=0.0,
        roughness=0.85,
        procedural_texture="noise",
        procedural_params={"scale": 30.0, "detail": 4.0, "roughness": 0.7, "strength": 0.18},
    ),
    "marble_white": MaterialPreset(
        name="marble_white",
        base_color=[0.95, 0.93, 0.9, 1.0],
        metallic=0.0,
        roughness=0.2,
        subsurface=0.05,
        procedural_texture="marble",
        procedural_params={"scale": 5.0, "distortion": 8.0, "detail": 3.0, "strength": 0.08},
    ),
    "granite": MaterialPreset(
        name="granite",
        base_color=[0.4, 0.38, 0.35, 1.0],
        metallic=0.0,
        roughness=0.4,
        procedural_texture="noise",
        procedural_params={"scale": 45.0, "detail": 5.0, "roughness": 0.8, "strength": 0.15},
    ),
    
    # ── Ceramic & Porcelain ───────────────────────────────────────────────
    "ceramic_white": MaterialPreset(
        name="ceramic_white",
        base_color=[0.95, 0.95, 0.93, 1.0],
        metallic=0.0,
        roughness=0.15,
        subsurface=0.02,
    ),
    "ceramic_glazed": MaterialPreset(
        name="ceramic_glazed",
        base_color=[0.9, 0.88, 0.85, 1.0],
        metallic=0.0,
        roughness=0.05,
        clearcoat=0.5,
    ),
    "porcelain": MaterialPreset(
        name="porcelain",
        base_color=[0.98, 0.97, 0.95, 1.0],
        metallic=0.0,
        roughness=0.1,
        subsurface=0.03,
    ),
    
    # ── Emissive ──────────────────────────────────────────────────────────
    "led_white": MaterialPreset(
        name="led_white",
        base_color=[1.0, 1.0, 1.0, 1.0],
        metallic=0.0,
        roughness=0.5,
        emission_color=[1.0, 1.0, 1.0],
        emission_strength=5.0,
    ),
    "led_red": MaterialPreset(
        name="led_red",
        base_color=[1.0, 0.1, 0.1, 1.0],
        metallic=0.0,
        roughness=0.5,
        emission_color=[1.0, 0.1, 0.1],
        emission_strength=3.0,
    ),
    "led_green": MaterialPreset(
        name="led_green",
        base_color=[0.1, 1.0, 0.1, 1.0],
        metallic=0.0,
        roughness=0.5,
        emission_color=[0.1, 1.0, 0.1],
        emission_strength=3.0,
    ),
    "led_blue": MaterialPreset(
        name="led_blue",
        base_color=[0.1, 0.3, 1.0, 1.0],
        metallic=0.0,
        roughness=0.5,
        emission_color=[0.1, 0.3, 1.0],
        emission_strength=3.0,
    ),
    "screen": MaterialPreset(
        name="screen",
        base_color=[0.1, 0.15, 0.2, 1.0],
        metallic=0.0,
        roughness=0.1,
        emission_color=[0.3, 0.5, 0.8],
        emission_strength=2.0,
    ),
    
    # ── Car Paint ─────────────────────────────────────────────────────────
    "car_paint_red": MaterialPreset(
        name="car_paint_red",
        base_color=[0.7, 0.05, 0.05, 1.0],
        metallic=0.0,
        roughness=0.2,
        clearcoat=1.0,
        clearcoat_roughness=0.03,
    ),
    "car_paint_black": MaterialPreset(
        name="car_paint_black",
        base_color=[0.02, 0.02, 0.02, 1.0],
        metallic=0.0,
        roughness=0.15,
        clearcoat=1.0,
        clearcoat_roughness=0.02,
    ),
    "car_paint_white": MaterialPreset(
        name="car_paint_white",
        base_color=[0.95, 0.95, 0.95, 1.0],
        metallic=0.0,
        roughness=0.2,
        clearcoat=0.8,
        clearcoat_roughness=0.03,
    ),
    "car_paint_metallic": MaterialPreset(
        name="car_paint_metallic",
        base_color=[0.4, 0.42, 0.45, 1.0],
        metallic=0.3,
        roughness=0.25,
        clearcoat=1.0,
        clearcoat_roughness=0.02,
    ),
    
    # ── Default/Fallback ──────────────────────────────────────────────────
    "default": MaterialPreset(
        name="default",
        base_color=[0.8, 0.8, 0.8, 1.0],
        metallic=0.0,
        roughness=0.5,
    ),
    "default_dark": MaterialPreset(
        name="default_dark",
        base_color=[0.2, 0.2, 0.2, 1.0],
        metallic=0.0,
        roughness=0.5,
    ),
}


def get_material_preset(preset_name: str) -> Optional[MaterialPreset]:
    """Get a material preset by name."""
    return MATERIAL_PRESETS.get(preset_name)


def get_material_for_description(description: str) -> MaterialPreset:
    """Infer material preset from a semantic description.
    
    Maps descriptions like "shiny metal", "wooden", "plastic" to presets.
    """
    desc_lower = description.lower()
    words = set(re.findall(r"[a-z]+", desc_lower))

    # An LED is a functional material role.  Resolve it before incidental
    # words such as "metal" in nearby prompt context, while keeping glass
    # components glass unless they explicitly say LED.
    if {"led", "leds", "glow"} & words:
        if "red" in words:
            return MATERIAL_PRESETS["led_red"]
        if "green" in words:
            return MATERIAL_PRESETS["led_green"]
        if "blue" in words:
            return MATERIAL_PRESETS["led_blue"]
        return MATERIAL_PRESETS["led_white"]
    
    # Metals
    if "chrome" in desc_lower or "mirror" in desc_lower:
        return MATERIAL_PRESETS["chrome"]
    if "gold" in desc_lower:
        return MATERIAL_PRESETS["gold"]
    if "copper" in desc_lower:
        return MATERIAL_PRESETS["copper"]
    if "brass" in desc_lower:
        return MATERIAL_PRESETS["brass"]
    if "rust" in desc_lower:
        return MATERIAL_PRESETS["rusty_metal"]
    if "iron" in desc_lower or "cast iron" in desc_lower:
        return MATERIAL_PRESETS["iron"]
    if "aluminum" in desc_lower or "aluminium" in desc_lower:
        if "brush" in desc_lower:
            return MATERIAL_PRESETS["brushed_aluminum"]
        return MATERIAL_PRESETS["polished_aluminum"]
    if "steel" in desc_lower or "stainless" in desc_lower:
        if "brush" in desc_lower:
            return MATERIAL_PRESETS["brushed_steel"]
        return MATERIAL_PRESETS["polished_steel"]
    if "metal" in desc_lower:
        if "shiny" in desc_lower or "polished" in desc_lower:
            return MATERIAL_PRESETS["polished_steel"]
        return MATERIAL_PRESETS["brushed_steel"]
    
    # Plastics
    if "rubber" in desc_lower:
        if "red" in desc_lower:
            return MATERIAL_PRESETS["rubber_red"]
        return MATERIAL_PRESETS["rubber"]
    if "silicone" in desc_lower:
        return MATERIAL_PRESETS["silicone"]
    if "plastic" in desc_lower:
        if "black" in desc_lower:
            return MATERIAL_PRESETS["glossy_plastic_black"]
        if "white" in desc_lower:
            return MATERIAL_PRESETS["glossy_plastic_white"]
        if "matte" in desc_lower:
            return MATERIAL_PRESETS["matte_plastic"]
        return MATERIAL_PRESETS["glossy_plastic"]
    
    # Wood
    if "wood" in desc_lower or "wooden" in desc_lower:
        if "dark" in desc_lower or "walnut" in desc_lower:
            return MATERIAL_PRESETS["wood_walnut"]
        if "oak" in desc_lower:
            return MATERIAL_PRESETS["wood_oak"]
        if "paint" in desc_lower or "white" in desc_lower:
            return MATERIAL_PRESETS["wood_painted_white"]
        if "varnish" in desc_lower or "lacquer" in desc_lower:
            return MATERIAL_PRESETS["wood_varnished"]
        if "light" in desc_lower or "pine" in desc_lower:
            return MATERIAL_PRESETS["wood_light"]
        return MATERIAL_PRESETS["wood_oak"]
    
    # Glass
    if "glass" in desc_lower:
        if "frost" in desc_lower:
            return MATERIAL_PRESETS["glass_frosted"]
        if "tint" in desc_lower or "dark" in desc_lower:
            return MATERIAL_PRESETS["glass_tinted"]
        return MATERIAL_PRESETS["glass_clear"]
    if "acrylic" in desc_lower or "plexiglass" in desc_lower:
        return MATERIAL_PRESETS["acrylic"]
    
    # Fabric
    if "velvet" in desc_lower:
        return MATERIAL_PRESETS["fabric_velvet"]
    if "leather" in desc_lower:
        if "black" in desc_lower:
            return MATERIAL_PRESETS["leather_black"]
        return MATERIAL_PRESETS["leather"]
    if "fabric" in desc_lower or "cloth" in desc_lower or "cotton" in desc_lower:
        return MATERIAL_PRESETS["fabric_cotton"]
    
    # Stone
    if "concrete" in desc_lower or "cement" in desc_lower:
        return MATERIAL_PRESETS["concrete"]
    if "marble" in desc_lower:
        return MATERIAL_PRESETS["marble_white"]
    if "granite" in desc_lower or "stone" in desc_lower:
        return MATERIAL_PRESETS["granite"]
    
    # Ceramic
    if "ceramic" in desc_lower:
        if "glaze" in desc_lower:
            return MATERIAL_PRESETS["ceramic_glazed"]
        return MATERIAL_PRESETS["ceramic_white"]
    if "porcelain" in desc_lower:
        return MATERIAL_PRESETS["porcelain"]
    
    # Emissive
    if "screen" in desc_lower or "display" in desc_lower:
        return MATERIAL_PRESETS["screen"]
    
    # Car paint
    if "car paint" in desc_lower or "automotive" in desc_lower:
        if "red" in desc_lower:
            return MATERIAL_PRESETS["car_paint_red"]
        if "black" in desc_lower:
            return MATERIAL_PRESETS["car_paint_black"]
        if "white" in desc_lower:
            return MATERIAL_PRESETS["car_paint_white"]
        return MATERIAL_PRESETS["car_paint_metallic"]
    
    # Color-based fallbacks
    # A finish alone is still meaningful intent (for example glossy
    # propeller blades).  Do not fall through to a generic rough surface.
    if "glossy" in desc_lower:
        return MATERIAL_PRESETS["glossy_plastic"]
    if "matte" in desc_lower:
        return MATERIAL_PRESETS["matte_plastic"]
    if "black" in desc_lower:
        return MATERIAL_PRESETS["glossy_plastic_black"]
    if "white" in desc_lower:
        return MATERIAL_PRESETS["glossy_plastic_white"]
    
    # Default
    return MATERIAL_PRESETS["default"]


def list_preset_names() -> List[str]:
    """Return list of all available preset names."""
    return list(MATERIAL_PRESETS.keys())


def ensure_manifest_materials(manifest: Any) -> Dict[str, Any]:
    """Resolve a concrete PBR material for every physical part before freeze.

    Material inference previously happened inside the executor, after the plan
    fingerprint was created.  That made material intent invisible to audits
    and impossible to verify by readback.  This deterministic pass makes it a
    declared part of the executable scene contract.
    """
    from .manifest import MaterialSpec
    from .node_types import NodeKind

    assigned: List[str] = []
    existing: List[str] = []
    for node in manifest.nodes.values():
        if node.kind not in (NodeKind.PART, NodeKind.DEFINITION):
            continue
        if getattr(node, "material", None) is not None:
            existing.append(node.node_id)
            continue
        hints = getattr(node, "stage_outputs", {}).get("decomposition_hint", {})
        description = str(hints.get("material_hint") or node.label)
        preset = get_material_for_description(description)
        node.material = MaterialSpec.from_preset(preset.name)
        assigned.append(node.node_id)
    report = {"assigned_node_ids": assigned, "existing_node_ids": existing, "complete": True}
    if hasattr(manifest, "record_event"):
        manifest.record_event("materials_resolved", details=report)
    return report
