"""Flat Pydantic schemas for declarative 3D modeling specifications.

Designed for grammar-constrained local LLM decoders (Ollama):
- Uses flat lists of typed objects with fixed keys instead of arbitrary Dict[str, ...].
- Uses Enums / Literals for categories, primitives, shapes, and relations.
- Vec3 replaces List[float] for position/offset fields (no minItems/maxItems grammar issues).
- Hex color strings replace float lists (LLM writes "#8B4513", code converts to linear float).
- VesselSpec with profile revolution for hollow organic vessels.
- Pattern field on PartSpec for repeated elements (legs, wheels, windows).
"""

from __future__ import annotations
from typing import List, Optional, Literal
from pydantic import BaseModel, Field, field_validator
import re


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def srgb_hex_to_linear(hex_color: str) -> tuple[float, float, float]:
    """Convert #RRGGBB sRGB hex string to a linear-light (r, g, b) tuple."""
    hex_color = hex_color.lstrip("#")
    r_s, g_s, b_s = (int(hex_color[i:i+2], 16) / 255.0 for i in (0, 2, 4))

    def _to_linear(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    return (_to_linear(r_s), _to_linear(g_s), _to_linear(b_s))


def srgb_hex_to_linear_rgba(hex_color: str, alpha: float = 1.0) -> tuple[float, float, float, float]:
    r, g, b = srgb_hex_to_linear(hex_color)
    return (r, g, b, alpha)


# ---------------------------------------------------------------------------
# Shared primitives
# ---------------------------------------------------------------------------

class Vec3(BaseModel):
    """Fixed-key 3D vector.  Preferred over List[float] for LLM grammar stability."""
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    def as_tuple(self) -> tuple[float, float, float]:
        return (self.x, self.y, self.z)


class MaterialSpec(BaseModel):
    name: Optional[str] = "Material"
    # Hex color string — LLM writes "#RRGGBB", compiler converts to linear float
    color: str = Field(
        default="#CCCCCC",
        pattern=r"^#[0-9a-fA-F]{6}$",
        description="sRGB hex color, e.g. '#8B4513'"
    )
    roughness: float = Field(default=0.5, ge=0.0, le=1.0)
    metallic: float = Field(default=0.0, ge=0.0, le=1.0)
    coat_weight: float = Field(default=0.0, ge=0.0, le=1.0, description="Clearcoat layer weight")

    def linear_rgba(self, alpha: float = 1.0) -> tuple[float, float, float, float]:
        return srgb_hex_to_linear_rgba(self.color, alpha)


class FinishSpec(BaseModel):
    subdiv_levels: int = Field(default=2, ge=0, le=4)
    shading: Literal["SMOOTH", "FLAT"] = Field("SMOOTH")
    ground_plane: bool = Field(default=True, description="Add subtle floor plane under model")
    studio_lighting: bool = Field(default=True, description="Add 3-point area/sun lighting")


# ---------------------------------------------------------------------------
# Quadruped (skeleton / skin-modifier path)
# ---------------------------------------------------------------------------

class JointSpec(BaseModel):
    name: str = Field(..., description="Unique joint identifier (e.g. 'pelvis', 'chest', 'knee_L')")
    x: float = Field(..., description="X coordinate in meters")
    y: float = Field(..., description="Y coordinate in meters")
    z: float = Field(..., description="Z coordinate in meters")
    rx: float = Field(..., gt=0.001, le=2.0, description="X radius / cross-section thickness in meters")
    ry: float = Field(..., gt=0.001, le=2.0, description="Y radius / cross-section thickness in meters")


class BoneSpec(BaseModel):
    parent: str = Field(..., description="Starting joint name")
    child: str = Field(..., description="Ending joint name")


class AttachmentSpec(BaseModel):
    name: str = Field(..., description="Attachment name (e.g. 'snout', 'eye_L', 'ear_L')")
    parent_joint: str = Field(..., description="Joint to anchor attachment to")
    shape: Literal["SPHERE", "CONE", "BOX", "CYLINDER"] = Field("SPHERE")
    scale: Vec3 = Field(default_factory=lambda: Vec3(x=0.05, y=0.05, z=0.05))
    offset: Vec3 = Field(default_factory=Vec3)


class QuadrupedSpec(BaseModel):
    category: Literal["quadruped"] = "quadruped"
    name: str = Field(default="quadruped_model", description="Model name")
    symmetry: Literal["x"] = "x"
    body_length_m: float = Field(..., gt=0.05, le=5.0, description="Pelvis-to-chest length in meters")
    withers_height_m: float = Field(..., gt=0.05, le=3.0, description="Ground-to-shoulder height in meters")
    joints: List[JointSpec] = Field(..., min_length=4)
    bones: List[BoneSpec] = Field(..., min_length=3)
    attachments: List[AttachmentSpec] = Field(default_factory=list)
    material: MaterialSpec = Field(default_factory=MaterialSpec)
    finish: FinishSpec = Field(default_factory=FinishSpec)

    @field_validator("joints")
    @classmethod
    def validate_centerline_joints(cls, joints: List[JointSpec]) -> List[JointSpec]:
        """Clamp centerline joints (no _L/_R suffix) to exact x = 0.0."""
        for j in joints:
            if not j.name.endswith("_L") and not j.name.endswith("_R"):
                if abs(j.x) > 0.001:
                    j.x = 0.0
        return joints


# ---------------------------------------------------------------------------
# Hard-surface (parts + relations path)
# ---------------------------------------------------------------------------

class ModifierSpec(BaseModel):
    type: Literal["SOLIDIFY", "BEVEL", "SUBSURF", "MIRROR"] = Field(...)
    thickness: Optional[float] = Field(None, gt=0.0, le=1.0, description="For SOLIDIFY")
    width: Optional[float] = Field(None, gt=0.0, le=1.0, description="For BEVEL")
    segments: Optional[int] = Field(None, ge=1, le=8, description="For BEVEL")
    levels: Optional[int] = Field(None, ge=1, le=4, description="For SUBSURF")


class PartSpec(BaseModel):
    name: str = Field(..., description="Part identifier (e.g. 'tabletop', 'leg', 'mug_body')")
    primitive: Literal["BOX", "CYLINDER", "TORUS", "PLANE", "SPHERE"] = Field(...)
    size: List[float] = Field(..., min_length=2, max_length=3, description="[dx, dy, dz] or [radius, depth]")
    # Pattern: how many instances and their arrangement
    pattern: Literal["SINGLE", "CORNERS", "GRID", "RING", "WHEEL_POSITIONS"] = Field(
        default="SINGLE",
        description="Repeat pattern for this part"
    )
    count: int = Field(default=1, ge=1, le=24, description="Number of instances for RING / GRID patterns")
    modifiers: List[ModifierSpec] = Field(default_factory=list)
    material: MaterialSpec = Field(default_factory=MaterialSpec)
    end_fill_type: Optional[Literal["NOTHING", "NGON", "TRIFAN"]] = Field("NGON")


class RelationSpec(BaseModel):
    target_part: str = Field(..., description="Part being positioned")
    parent_part: str = Field(..., description="Reference parent part")
    relation_type: Literal[
        "ON_TOP_OF",
        "ATTACH_SIDE",
        "INSET",
        "ALIGN_CENTER",
        "CORNER_LEGS",
        "WHEEL_POSITIONS",
        "RING_POSITIONS",
    ] = Field(...)
    offset: Vec3 = Field(default_factory=Vec3, description="Translation offset from resolved position")
    inset: Optional[float] = Field(0.0, ge=0.0, description="Inset margin from parent edges (for CORNER_LEGS)")


class HardSurfaceSpec(BaseModel):
    category: Literal[
        "furniture", "vehicle", "vessel", "architecture", "tool", "generic"
    ] = Field(...)
    name: str = Field(default="hardsurface_model")
    parts: List[PartSpec] = Field(..., min_length=1)
    relations: List[RelationSpec] = Field(default_factory=list)
    finish: FinishSpec = Field(default_factory=FinishSpec)


# ---------------------------------------------------------------------------
# Vessel (bmesh spin revolution path)
# ---------------------------------------------------------------------------

class ProfilePoint(BaseModel):
    """One (radius, height) sample on the profile curve revolved around Z."""
    radius: float = Field(..., ge=0.0, description="Distance from center axis in meters")
    height: float = Field(..., description="Z coordinate in meters")


class HandleSpec(BaseModel):
    """Torus handle attached to a vessel side wall."""
    major_radius: float = Field(default=0.028, gt=0.0, description="Torus ring radius")
    minor_radius: float = Field(default=0.006, gt=0.0, description="Torus tube radius")
    offset_x: float = Field(default=0.0, description="Horizontal offset from axis (embed depth < 0 = into wall)")
    offset_z: float = Field(default=0.05, description="Vertical position along vessel height")
    material: Optional[MaterialSpec] = None


class VesselSpec(BaseModel):
    """Profile-revolved hollow vessel (cup, vase, bottle, bowl).

    The profile is a list of (radius, height) points.  The compiler revolves them
    360° around the Z axis using bmesh.ops.spin, adds wall thickness via SOLIDIFY,
    caps the bottom if requested, and optionally attaches a torus handle.
    """
    category: Literal["vessel"] = "vessel"
    name: str = Field(default="vessel_model")
    profile: List[ProfilePoint] = Field(..., min_length=3, description="Cross-section profile curve")
    wall_thickness: float = Field(default=0.005, gt=0.0, le=0.05)
    bottom_closed: bool = True
    top_closed: bool = False
    steps: int = Field(default=32, ge=8, le=128, description="Revolution segments")
    handle: Optional[HandleSpec] = None
    material: MaterialSpec = Field(default_factory=MaterialSpec)
    finish: FinishSpec = Field(default_factory=FinishSpec)
