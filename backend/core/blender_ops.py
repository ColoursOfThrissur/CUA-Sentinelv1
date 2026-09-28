"""Typed operations layer for Blender MCP integration.

Enforces:
1. Strict Pydantic parameter schemas (regex names, bounds, rejects nan/inf).
2. Pure template-based bpy script rendering (never raw agent code).
3. Structured JSON-only return data (sanitized numerical manifest).
4. Raw code execution strictly blocked from direct agent access.
"""

import re
import json
import logging
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, field_validator, model_validator
import math

logger = logging.getLogger(__name__)

NAME_REGEX = re.compile(r"^[A-Za-z0-9_.-]{1,63}\Z")  # \Z prevents trailing newline, 63 = Blender max


def _validate_finite_float(v: float, min_val: float = -10000.0, max_val: float = 10000.0) -> float:
    if not isinstance(v, (int, float)) or math.isnan(v) or math.isinf(v):
        raise ValueError(f"Value must be a finite number, got {v}")
    if v < min_val or v > max_val:
        raise ValueError(f"Value {v} out of allowed range [{min_val}, {max_val}]")
    return float(v)


class CreateBoxParams(BaseModel):
    name: str = Field(..., description="Unique alphanumeric object name")
    size: List[float] = Field(default=[1.0, 1.0, 1.0], description="[X, Y, Z] dimensions in meters")
    location: List[float] = Field(default=[0.0, 0.0, 0.0], description="[X, Y, Z] center location in meters")
    rotation: Optional[List[float]] = Field(default=None, description="[X, Y, Z] rotation in degrees")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not NAME_REGEX.match(v):
            raise ValueError(f"Invalid object name '{v}'. Must match pattern ^[A-Za-z0-9_.-]{{1,64}}$")
        return v

    @field_validator("size", mode="before")
    @classmethod
    def validate_size(cls, v: Any) -> List[float]:
        if isinstance(v, (int, float)):
            v = [float(v), float(v), float(v)]
        if not isinstance(v, (list, tuple)) or len(v) != 3:
            raise ValueError("Size must have exactly 3 elements [x, y, z] or a scalar")
        return [_validate_finite_float(x, 0.001, 1000.0) for x in v]

    @field_validator("location")
    @classmethod
    def validate_location(cls, v: List[float]) -> List[float]:
        if len(v) != 3:
            raise ValueError("Location must have exactly 3 elements [x, y, z]")
        return [_validate_finite_float(x, -10000.0, 10000.0) for x in v]

    @field_validator("rotation")
    @classmethod
    def validate_rotation(cls, v: Optional[List[float]]) -> Optional[List[float]]:
        if v is not None:
            if len(v) != 3:
                raise ValueError("Rotation must have exactly 3 elements [x, y, z]")
            return [_validate_finite_float(x, -3600.0, 3600.0) for x in v]
        return None


class CreateSphereParams(BaseModel):
    name: str = Field(..., description="Unique alphanumeric object name")
    radius: float = Field(default=1.0, description="Sphere radius in meters")
    location: List[float] = Field(default=[0.0, 0.0, 0.0], description="[X, Y, Z] center location in meters")
    rotation: Optional[List[float]] = Field(default=None, description="[X, Y, Z] rotation in degrees")
    segments: int = Field(default=32, ge=3, le=256, description="Longitude segments (3-256)")
    rings: int = Field(default=16, ge=2, le=256, description="Latitude rings (2-256)")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not NAME_REGEX.match(v):
            raise ValueError(f"Invalid object name '{v}'. Must match pattern ^[A-Za-z0-9_.-]{{1,63}}$")
        return v

    @field_validator("radius")
    @classmethod
    def validate_radius(cls, v: float) -> float:
        return _validate_finite_float(v, 0.001, 1000.0)

    @field_validator("location")
    @classmethod
    def validate_location(cls, v: List[float]) -> List[float]:
        if len(v) != 3:
            raise ValueError("Location must have exactly 3 elements [x, y, z]")
        return [_validate_finite_float(x, -10000.0, 10000.0) for x in v]

    @field_validator("rotation")
    @classmethod
    def validate_rotation(cls, v: Optional[List[float]]) -> Optional[List[float]]:
        if v is not None:
            if len(v) != 3:
                raise ValueError("Rotation must have exactly 3 elements [x, y, z]")
            return [_validate_finite_float(x, -3600.0, 3600.0) for x in v]
        return None


class CreateCylinderParams(BaseModel):
    name: str = Field(..., description="Unique alphanumeric object name")
    radius: float = Field(default=1.0, description="Cylinder radius in meters")
    depth: float = Field(default=2.0, description="Cylinder depth/height in meters")
    location: List[float] = Field(default=[0.0, 0.0, 0.0], description="[X, Y, Z] center location in meters")
    rotation: Optional[List[float]] = Field(None, description="[X, Y, Z] rotation in degrees")
    vertices: int = Field(default=32, description="Circumference segments: e.g. 6 for hexagonal prism, 32 for cylinder")

    @field_validator("vertices")
    @classmethod
    def validate_vertices(cls, v: int) -> int:
        if v < 3 or v > 256:
            raise ValueError(f"Vertices must be between 3 and 256, got {v}")
        return int(v)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not NAME_REGEX.match(v):
            raise ValueError(f"Invalid object name '{v}'. Must match pattern ^[A-Za-z0-9_.-]{{1,64}}$")
        return v

    @field_validator("radius")
    @classmethod
    def validate_radius(cls, v: float) -> float:
        return _validate_finite_float(v, 0.001, 1000.0)

    @field_validator("depth")
    @classmethod
    def validate_depth(cls, v: float) -> float:
        return _validate_finite_float(v, 0.001, 1000.0)

    @field_validator("location")
    @classmethod
    def validate_location(cls, v: List[float]) -> List[float]:
        if len(v) != 3:
            raise ValueError("Location must have exactly 3 elements [x, y, z]")
        return [_validate_finite_float(x, -10000.0, 10000.0) for x in v]

    @field_validator("rotation")
    @classmethod
    def validate_rotation(cls, v: Optional[List[float]]) -> Optional[List[float]]:
        if v is not None:
            if len(v) != 3:
                raise ValueError("Rotation must have exactly 3 elements [x, y, z]")
            return [_validate_finite_float(x, -3600.0, 3600.0) for x in v]
        return None


class CreateConeParams(BaseModel):
    name: str = Field(..., description="Unique alphanumeric object name")
    radius1: float = Field(default=1.0, description="Base radius in meters")
    depth: float = Field(default=2.0, description="Cone height in meters")
    location: List[float] = Field(default=[0.0, 0.0, 0.0], description="[X, Y, Z] center location in meters")
    rotation: Optional[List[float]] = Field(None, description="[X, Y, Z] rotation in degrees")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not NAME_REGEX.match(v):
            raise ValueError(f"Invalid object name '{v}'. Must match pattern ^[A-Za-z0-9_.-]{{1,64}}$")
        return v

    @field_validator("radius1")
    @classmethod
    def validate_radius(cls, v: float) -> float:
        return _validate_finite_float(v, 0.001, 1000.0)

    @field_validator("depth")
    @classmethod
    def validate_depth(cls, v: float) -> float:
        return _validate_finite_float(v, 0.001, 1000.0)

    @field_validator("location")
    @classmethod
    def validate_location(cls, v: List[float]) -> List[float]:
        if len(v) != 3:
            raise ValueError("Location must have exactly 3 elements [x, y, z]")
        return [_validate_finite_float(x, -10000.0, 10000.0) for x in v]

    @field_validator("rotation")
    @classmethod
    def validate_rotation(cls, v: Optional[List[float]]) -> Optional[List[float]]:
        if v is not None:
            if len(v) != 3:
                raise ValueError("Rotation must have exactly 3 elements [x, y, z]")
            return [_validate_finite_float(x, -3600.0, 3600.0) for x in v]
        return None


class CreateHemisphereParams(BaseModel):
    """Hemisphere via bisect_plane - cleaner than boolean cutter."""
    name: str = Field(..., description="Unique alphanumeric object name")
    radius: float = Field(default=1.0, description="Hemisphere radius in meters")
    location: List[float] = Field(default=[0.0, 0.0, 0.0], description="[X, Y, Z] center location in meters")
    rotation: Optional[List[float]] = Field(default=None, description="[X, Y, Z] rotation in degrees")
    segments: int = Field(default=32, ge=3, le=256, description="Longitude segments (3-256)")
    rings: int = Field(default=16, ge=2, le=256, description="Latitude rings (2-256)")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not NAME_REGEX.match(v):
            raise ValueError(f"Invalid object name '{v}'. Must match pattern ^[A-Za-z0-9_.-]{{1,63}}$")
        return v

    @field_validator("radius")
    @classmethod
    def validate_radius(cls, v: float) -> float:
        return _validate_finite_float(v, 0.001, 1000.0)

    @field_validator("location")
    @classmethod
    def validate_location(cls, v: List[float]) -> List[float]:
        if len(v) != 3:
            raise ValueError("Location must have exactly 3 elements [x, y, z]")
        return [_validate_finite_float(x, -10000.0, 10000.0) for x in v]

    @field_validator("rotation")
    @classmethod
    def validate_rotation(cls, v: Optional[List[float]]) -> Optional[List[float]]:
        if v is not None:
            if len(v) != 3:
                raise ValueError("Rotation must have exactly 3 elements [x, y, z]")
            return [_validate_finite_float(x, -3600.0, 3600.0) for x in v]
        return None


class CreateTorusParams(BaseModel):
    name: str = Field(..., description="Unique alphanumeric object name")
    major_radius: float = Field(default=1.0, description="Major/outer ring radius in meters")
    minor_radius: float = Field(default=0.25, description="Minor/tube cross-section radius in meters")
    location: List[float] = Field(default=[0.0, 0.0, 0.0], description="[X, Y, Z] center location in meters")
    rotation: Optional[List[float]] = Field(None, description="[X, Y, Z] rotation in degrees")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not NAME_REGEX.match(v):
            raise ValueError(f"Invalid object name '{v}'. Must match pattern ^[A-Za-z0-9_.-]{{1,63}}$")
        return v

    @field_validator("major_radius")
    @classmethod
    def validate_major(cls, v: float) -> float:
        return _validate_finite_float(v, 0.001, 1000.0)

    @field_validator("minor_radius")
    @classmethod
    def validate_minor(cls, v: float) -> float:
        return _validate_finite_float(v, 0.001, 1000.0)
    
    @model_validator(mode='after')
    def check_radii(self):
        if self.minor_radius >= self.major_radius:
            raise ValueError(f"minor_radius ({self.minor_radius}) must be less than major_radius ({self.major_radius})")
        return self

    @field_validator("location")
    @classmethod
    def validate_location(cls, v: List[float]) -> List[float]:
        if len(v) != 3:
            raise ValueError("Location must have exactly 3 elements [x, y, z]")
        return [_validate_finite_float(x, -10000.0, 10000.0) for x in v]

    @field_validator("rotation")
    @classmethod
    def validate_rotation(cls, v: Optional[List[float]]) -> Optional[List[float]]:
        if v is not None:
            if len(v) != 3:
                raise ValueError("Rotation must have exactly 3 elements [x, y, z]")
            return [_validate_finite_float(x, -3600.0, 3600.0) for x in v]
        return None


class ApplySubdivisionParams(BaseModel):
    name: str = Field(..., description="Target object name")
    levels: int = Field(default=2, ge=1, le=4, description="Subdivision surface smoothness level (1-4)")
    render_levels: Optional[int] = Field(default=2, ge=1, le=4, description="Render subdivision level")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not NAME_REGEX.match(v):
            raise ValueError(f"Invalid object name '{v}'. Must match pattern ^[A-Za-z0-9_.-]{{1,64}}$")
        return v


class ApplyBooleanParams(BaseModel):
    name: str = Field(..., description="Base object name")
    target_name: str = Field(..., description="Target cutter or union object name")
    operation: str = Field(default="DIFFERENCE", description="'DIFFERENCE' (cut hole), 'UNION' (merge), or 'INTERSECT'")
    delete_target: bool = Field(default=True, description="Whether to delete target tool object after applying boolean")

    @field_validator("name", "target_name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not NAME_REGEX.match(v):
            raise ValueError(f"Invalid object name '{v}'. Must match pattern ^[A-Za-z0-9_.-]{{1,64}}$")
        return v

    @field_validator("operation")
    @classmethod
    def validate_operation(cls, v: str) -> str:
        v_upper = v.upper().strip()
        if v_upper not in ("DIFFERENCE", "UNION", "INTERSECT"):
            raise ValueError(f"Operation must be 'DIFFERENCE', 'UNION', or 'INTERSECT', got '{v}'")
        return v_upper


class ApplyBevelParams(BaseModel):
    name: str = Field(..., description="Target object name")
    width: float = Field(default=0.05, ge=0.0001, le=100.0, description="Bevel edge width in meters")
    segments: int = Field(default=3, ge=1, le=16, description="Bevel segments count")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not NAME_REGEX.match(v):
            raise ValueError(f"Invalid object name '{v}'. Must match pattern ^[A-Za-z0-9_.-]{{1,64}}$")
        return v


class SetSmoothShadingParams(BaseModel):
    name: str = Field(..., description="Target object name")
    smooth: bool = Field(default=True, description="True for smooth shading, False for flat faceted shading")
    angle: float = Field(default=30.0, ge=0.0, le=180.0, description="Auto-smooth angle in degrees (edges sharper than this stay sharp)")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not NAME_REGEX.match(v):
            raise ValueError(f"Invalid object name '{v}'. Must match pattern ^[A-Za-z0-9_.-]{{1,63}}$")
        return v


class SetMaterialParams(BaseModel):
    name: str = Field(..., description="Target object name")
    color: List[float] = Field(default=[0.8, 0.8, 0.8, 1.0], description="[R, G, B] or [R, G, B, A] normalized color (0.0 to 1.0)")
    metallic: float = Field(default=0.0, ge=0.0, le=1.0, description="Metallic slider (0.0=dielectric, 1.0=metal)")
    roughness: float = Field(default=0.5, ge=0.0, le=1.0, description="Roughness slider (0.0=mirror, 1.0=matte)")
    emission_color: Optional[List[float]] = Field(None, description="[R, G, B] emission glow color")
    emission_strength: Optional[float] = Field(None, ge=0.0, le=1000.0, description="Emission glow strength (defaults to 1.0 if emission_color set)")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not NAME_REGEX.match(v):
            raise ValueError(f"Invalid object name '{v}'. Must match pattern ^[A-Za-z0-9_.-]{{1,63}}$")
        return v

    @field_validator("color", mode="before")
    @classmethod
    def validate_color(cls, v: Any) -> List[float]:
        if not isinstance(v, (list, tuple)) or len(v) not in (3, 4):
            raise ValueError("Color must be a list of 3 or 4 floats [R, G, B] or [R, G, B, A] in range 0.0-1.0")
        floats = [_validate_finite_float(x, 0.0, 1.0) for x in v]
        if len(floats) == 3:
            floats.append(1.0)
        return floats

    @field_validator("emission_color", mode="before")
    @classmethod
    def validate_emission_color(cls, v: Any) -> Optional[List[float]]:
        if v is None:
            return None
        if not isinstance(v, (list, tuple)) or len(v) not in (3, 4):
            raise ValueError("emission_color must be a list of 3 or 4 floats [R, G, B] or [R, G, B, A]")
        return [_validate_finite_float(x, 0.0, 1.0) for x in v[:4]]


class JoinObjectsParams(BaseModel):
    names: List[str] = Field(..., min_length=2, description="List of at least 2 object names to join")
    target_name: Optional[str] = Field(None, description="Optional name for the joined resulting object")

    @field_validator("names")
    @classmethod
    def validate_names(cls, v: List[str]) -> List[str]:
        for n in v:
            if not NAME_REGEX.match(n):
                raise ValueError(f"Invalid object name '{n}'. Must match pattern ^[A-Za-z0-9_.-]{{1,64}}$")
        return v


class DeleteObjectParams(BaseModel):
    name: str = Field(..., description="Name of object to delete")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not NAME_REGEX.match(v):
            raise ValueError(f"Invalid object name '{v}'. Must match pattern ^[A-Za-z0-9_.-]{{1,64}}$")
        return v


class ClearSceneParams(BaseModel):
    keep_camera_and_lights: bool = Field(default=True, description="Whether to preserve existing camera and light objects")


class CreateLightParams(BaseModel):
    name: str = Field(default="Sun", description="Light object name")
    type: str = Field(default="POINT", description="'POINT', 'SUN', 'SPOT', or 'AREA'")
    energy: Optional[float] = Field(default=None, description="Light power (Watts for POINT/SPOT/AREA, W/m² for SUN). Defaults: SUN=5, others=1000")
    location: List[float] = Field(default=[4.0, -4.0, 6.0], description="[X, Y, Z] location")
    color: Optional[List[float]] = Field(None, description="[R, G, B] color (0.0 to 1.0)")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not NAME_REGEX.match(v):
            raise ValueError(f"Invalid object name '{v}'. Must match pattern ^[A-Za-z0-9_.-]{{1,63}}$")
        return v

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        v_upper = v.upper().strip()
        if v_upper not in ("POINT", "SUN", "SPOT", "AREA"):
            raise ValueError(f"Light type must be 'POINT', 'SUN', 'SPOT', or 'AREA', got '{v}'")
        return v_upper

    @field_validator("location")
    @classmethod
    def validate_location(cls, v: List[float]) -> List[float]:
        if len(v) != 3:
            raise ValueError("Location must have exactly 3 elements [x, y, z]")
        return [_validate_finite_float(x, -10000.0, 10000.0) for x in v]
    
    @field_validator("energy")
    @classmethod
    def validate_energy(cls, v: Optional[float]) -> Optional[float]:
        if v is not None:
            return _validate_finite_float(v, 0.0, 100000.0)
        return None


class CreateCameraParams(BaseModel):
    name: str = Field(default="Camera", description="Camera object name")
    location: List[float] = Field(default=[7.0, -7.0, 5.0], description="[X, Y, Z] location")
    rotation: List[float] = Field(default=[60.0, 0.0, 45.0], description="[X, Y, Z] rotation in degrees")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not NAME_REGEX.match(v):
            raise ValueError(f"Invalid object name '{v}'. Must match pattern ^[A-Za-z0-9_.-]{{1,64}}$")
        return v

    @field_validator("location")
    @classmethod
    def validate_location(cls, v: List[float]) -> List[float]:
        if len(v) != 3:
            raise ValueError("Location must have exactly 3 elements [x, y, z]")
        return [_validate_finite_float(x, -10000.0, 10000.0) for x in v]

    @field_validator("rotation")
    @classmethod
    def validate_rotation(cls, v: List[float]) -> List[float]:
        if len(v) != 3:
            raise ValueError("Rotation must have exactly 3 elements [x, y, z]")
        return [_validate_finite_float(x, -3600.0, 3600.0) for x in v]


class SetTransformParams(BaseModel):
    name: str = Field(..., description="Target object name")
    location: Optional[List[float]] = Field(None, description="[X, Y, Z] location in meters")
    rotation_euler: Optional[List[float]] = Field(None, description="[X, Y, Z] rotation in degrees")
    rotation: Optional[List[float]] = Field(None, description="Alias for rotation_euler")
    scale: Optional[Any] = Field(None, description="[X, Y, Z] scale multipliers")

    def __init__(self, **data):
        if "rotation" in data and "rotation_euler" not in data:
            data["rotation_euler"] = data.pop("rotation")
        super().__init__(**data)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not NAME_REGEX.match(v):
            raise ValueError(f"Invalid object name '{v}'. Must match pattern ^[A-Za-z0-9_.-]{{1,64}}$")
        return v

    @field_validator("location")
    @classmethod
    def validate_location(cls, v: Optional[List[float]]) -> Optional[List[float]]:
        if v is not None:
            if len(v) != 3:
                raise ValueError("Location must have exactly 3 elements [x, y, z]")
            return [_validate_finite_float(x, -10000.0, 10000.0) for x in v]
        return None

    @field_validator("rotation_euler")
    @classmethod
    def validate_rotation(cls, v: Optional[List[float]]) -> Optional[List[float]]:
        if v is not None:
            if len(v) != 3:
                raise ValueError("Rotation must have exactly 3 elements [x, y, z]")
            return [_validate_finite_float(x, -3600.0, 3600.0) for x in v]
        return None

    @field_validator("scale", mode="before")
    @classmethod
    def validate_scale(cls, v: Any) -> Optional[List[float]]:
        if v is not None:
            if isinstance(v, (int, float)):
                v = [float(v), float(v), float(v)]
            if not isinstance(v, (list, tuple)) or len(v) != 3:
                raise ValueError("Scale must have exactly 3 elements [x, y, z] or scalar")
            return [_validate_finite_float(x, 0.001, 1000.0) for x in v]
        return None


class GetManifestParams(BaseModel):
    prefix: Optional[str] = Field(None, description="Optional object name prefix filter")


class ParentObjectParams(BaseModel):
    name: str = Field(..., description="Child object name")
    parent_name: str = Field(..., description="Parent object name")
    keep_transform: bool = Field(default=True, description="Maintain child's world transform upon parenting")

    @field_validator("name", "parent_name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not NAME_REGEX.match(v):
            raise ValueError(f"Invalid object name '{v}'. Must match pattern ^[A-Za-z0-9_.-]{{1,64}}$")
        return v


class SetOriginParams(BaseModel):
    name: str = Field(..., description="Target object name")
    origin_mode: str = Field(
        default="GEOMETRY_ORIGIN",
        description="Origin placement mode: GEOMETRY_ORIGIN | ORIGIN_GEOMETRY | CURSOR | BOUNDS_CENTER"
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not NAME_REGEX.match(v):
            raise ValueError(f"Invalid object name '{v}'. Must match pattern ^[A-Za-z0-9_.-]{{1,64}}$")
        return v


class SeparateMeshParams(BaseModel):
    name: str = Field(..., description="Mesh object name to separate")
    mode: str = Field(default="LOOSE", description="Separation mode: SELECTED | LOOSE | MATERIAL")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not NAME_REGEX.match(v):
            raise ValueError(f"Invalid object name '{v}'. Must match pattern ^[A-Za-z0-9_.-]{{1,64}}$")
        return v


class ApplyArrayParams(BaseModel):
    """Array modifier for repeating geometry (rivets, panel lines, etc.)."""
    name: str = Field(..., description="Target object name to apply array to")
    count: int = Field(default=2, ge=1, le=1000, description="Number of array copies")
    offset: List[float] = Field(default=[1.0, 0.0, 0.0], description="[X, Y, Z] relative offset between copies")
    use_relative_offset: bool = Field(default=True, description="Use relative (object-size-based) offset")
    use_constant_offset: bool = Field(default=False, description="Use constant (absolute) offset")
    constant_offset: Optional[List[float]] = Field(None, description="[X, Y, Z] constant offset in meters")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not NAME_REGEX.match(v):
            raise ValueError(f"Invalid object name '{v}'. Must match pattern ^[A-Za-z0-9_.-]{{1,64}}$")
        return v

    @field_validator("offset")
    @classmethod
    def validate_offset(cls, v: List[float]) -> List[float]:
        if len(v) != 3:
            raise ValueError("Offset must have exactly 3 elements [x, y, z]")
        return [_validate_finite_float(x, -1000.0, 1000.0) for x in v]

    @field_validator("constant_offset")
    @classmethod
    def validate_constant_offset(cls, v: Optional[List[float]]) -> Optional[List[float]]:
        if v is not None:
            if len(v) != 3:
                raise ValueError("Constant offset must have exactly 3 elements [x, y, z]")
            return [_validate_finite_float(x, -1000.0, 1000.0) for x in v]
        return None


# Static reviewed bpy templates
_CREATE_BOX_TEMPLATE = """
import bpy
import json
import math
import bmesh

params = json.loads(PARAMS_JSON)
name = params["name"]
size = params["size"]
loc = params["location"]
rot = params.get("rotation")
rot_rad = tuple(math.radians(r) for r in rot) if rot else (0.0, 0.0, 0.0)

# Reject duplicate names
if name in bpy.data.objects:
    result = {"ok": False, "error": f"Object '{name}' already exists. Use unique names."}
    print("SENTINEL_OUTPUT_START" + json.dumps(result) + "SENTINEL_OUTPUT_END")
else:
    # bmesh cube with exact vertex positions (no scale needed)
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co.x *= size[0]
        v.co.y *= size[1]
        v.co.z *= size[2]
    bm.to_mesh(mesh)
    bm.free()

    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.location = tuple(loc)
    obj.rotation_euler = rot_rad

    # Verify LOCAL mesh dimensions (not world AABB which is affected by rotation)
    verts = [v.co for v in obj.data.vertices]
    local_min = [min(v[i] for v in verts) for i in range(3)]
    local_max = [max(v[i] for v in verts) for i in range(3)]
    local_size = [local_max[i] - local_min[i] for i in range(3)]
    
    tol = 0.01
    size_ok = all(abs(local_size[i] - size[i]) < size[i] * tol + 0.001 for i in range(3))
    
    result = {
        "ok": size_ok,
        "action": "create_box",
        "name": obj.name,
        "requested_size": size,
        "local_size": [round(c, 4) for c in local_size],
        "location": [round(c, 4) for c in obj.location],
        "rotation": [round(math.degrees(c), 2) for c in obj.rotation_euler]
    }
    if not size_ok:
        result["error"] = f"Dimension mismatch: requested {size}, got local_size {[round(c,4) for c in local_size]}"
    print("SENTINEL_OUTPUT_START" + json.dumps(result) + "SENTINEL_OUTPUT_END")
"""

_CREATE_SPHERE_TEMPLATE = """
import bpy
import json
import math

params = json.loads(PARAMS_JSON)
name = params["name"]
radius = params["radius"]
loc = params["location"]
rot = params.get("rotation")
rot_rad = tuple(math.radians(r) for r in rot) if rot else (0.0, 0.0, 0.0)
segments = params.get("segments", 32)
rings = params.get("rings", 16)

if name in bpy.data.objects:
    result = {"ok": False, "error": f"Object '{name}' already exists. Use unique names."}
    print("SENTINEL_OUTPUT_START" + json.dumps(result) + "SENTINEL_OUTPUT_END")
else:
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segments, ring_count=rings, radius=radius, location=tuple(loc), rotation=rot_rad, align='WORLD')
    obj = bpy.context.active_object
    obj.name = name
    obj.data.name = name
    
    # Verify using max vertex distance from center (circumradius)
    # Works for any segment count, unlike bbox which varies with tessellation
    verts = [v.co for v in obj.data.vertices]
    circumradius = max(v.length for v in verts)
    
    tol = 0.01
    size_ok = abs(circumradius - radius) < radius * tol + 0.001

    result = {
        "ok": size_ok,
        "action": "create_sphere",
        "name": obj.name,
        "radius": radius,
        "location": [round(c, 4) for c in obj.location],
        "rotation": [round(math.degrees(c), 2) for c in obj.rotation_euler],
        "circumradius": round(circumradius, 4)
    }
    if not size_ok:
        result["error"] = f"Radius mismatch: expected {radius}, got circumradius={round(circumradius,4)}"
    print("SENTINEL_OUTPUT_START" + json.dumps(result) + "SENTINEL_OUTPUT_END")
"""

_CREATE_HEMISPHERE_TEMPLATE = """
import bpy
import bmesh
import json
import math
from mathutils import Vector

params = json.loads(PARAMS_JSON)
name = params["name"]
radius = params["radius"]
loc = params["location"]
rot = params.get("rotation")
rot_rad = tuple(math.radians(r) for r in rot) if rot else (0.0, 0.0, 0.0)
segments = params.get("segments") or 32
rings = params.get("rings") or 16

if name in bpy.data.objects:
    result = {"ok": False, "error": f"Object '{name}' already exists. Use unique names."}
    print("SENTINEL_OUTPUT_START" + json.dumps(result) + "SENTINEL_OUTPUT_END")
else:
    # Create sphere and record vertex count BEFORE bisect
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segments, ring_count=rings, radius=radius, location=(0, 0, 0), align='WORLD')
    obj = bpy.context.active_object
    obj.name = name
    obj.data.name = name
    full_sphere_vert_count = len(obj.data.vertices)
    
    # Use bmesh for cleaner bisect with remove_doubles
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    
    # Bisect at z=0, keep upper half (z >= 0)
    geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
    result_geom = bmesh.ops.bisect_plane(
        bm, geom=geom,
        plane_co=(0, 0, 0),
        plane_no=(0, 0, 1),
        clear_inner=True,
        clear_outer=False,
        dist=0.0001  # Small dist to avoid edge-on issues
    )
    
    # Remove doubles at cut edge
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.0001)
    
    # Fill the cut edge to cap the hemisphere
    # Find boundary edges (edges with only one face)
    boundary_edges = [e for e in bm.edges if len(e.link_faces) == 1]
    if boundary_edges:
        bmesh.ops.edgeloop_fill(bm, edges=boundary_edges)
    
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()
    
    obj.location = tuple(loc)
    obj.rotation_euler = rot_rad
    
    # Verify the cut actually happened:
    # 1. circumradius ~ radius (XY extent)
    # 2. z_max ~ radius (dome height)
    # 3. z_min ~ 0 (flat face at z=0, proves cut happened)
    # 4. vertex count < full sphere (proves geometry was removed)
    verts = [v.co for v in obj.data.vertices]
    circumradius = max(math.hypot(v.x, v.y) for v in verts) if verts else 0
    z_max = max(v.z for v in verts) if verts else 0
    z_min = min(v.z for v in verts) if verts else -radius
    hemi_vert_count = len(obj.data.vertices)
    
    tol = 0.05
    radius_ok = abs(circumradius - radius) < radius * tol + 0.001
    height_ok = abs(z_max - radius) < radius * tol + 0.001
    cut_ok = abs(z_min) < radius * 0.02 + 0.001  # Flat face at z~0
    count_ok = hemi_vert_count < full_sphere_vert_count  # Geometry was removed
    size_ok = radius_ok and height_ok and cut_ok and count_ok

    result = {
        "ok": size_ok,
        "action": "create_hemisphere",
        "name": obj.name,
        "radius": radius,
        "location": [round(c, 4) for c in obj.location],
        "rotation": [round(math.degrees(c), 2) for c in obj.rotation_euler],
        "circumradius": round(circumradius, 4),
        "z_max": round(z_max, 4),
        "z_min": round(z_min, 4),
        "vert_count_before": full_sphere_vert_count,
        "vert_count_after": hemi_vert_count
    }
    if not size_ok:
        errors = []
        if not radius_ok:
            errors.append(f"circumradius {round(circumradius,4)} != {radius}")
        if not height_ok:
            errors.append(f"z_max {round(z_max,4)} != {radius}")
        if not cut_ok:
            errors.append(f"z_min {round(z_min,4)} != 0 (cut failed)")
        if not count_ok:
            errors.append(f"vert count {hemi_vert_count} >= {full_sphere_vert_count} (no geometry removed)")
        result["error"] = "Hemisphere verification failed: " + "; ".join(errors)
    print("SENTINEL_OUTPUT_START" + json.dumps(result) + "SENTINEL_OUTPUT_END")
"""

_FIND_OBJECT_HELPER = '''
def _find_blender_object(target_name, strict=True):
    """Find object by name. strict=True uses exact match only (for pipeline)."""
    import bpy
    import re
    if not target_name:
        return None if strict else (bpy.context.active_object or (bpy.data.objects[0] if bpy.data.objects else None))
    # 1. Exact match (always tried first)
    if target_name in bpy.data.objects:
        return bpy.data.objects[target_name]
    # For pipeline operations, fail on exact miss
    if strict:
        return None
    # Fuzzy fallbacks only for user-driven edits
    t_low = str(target_name).lower().strip()
    for o in bpy.data.objects:
        if o.name.lower() == t_low:
            return o
    for o in bpy.data.objects:
        if t_low in o.name.lower() or o.name.lower() in t_low:
            return o
    return None
'''

_SET_TRANSFORM_TEMPLATE = _FIND_OBJECT_HELPER + """
import bpy
import math
import json

params = json.loads(PARAMS_JSON)
name = params["name"]
obj = _find_blender_object(name)

if not obj:
    result = {"ok": False, "error": f"Object '{name}' not found in scene."}
else:
    if params.get("location"):
        obj.location = tuple(params["location"])
    if params.get("rotation_euler"):
        obj.rotation_euler = tuple(math.radians(r) for r in params["rotation_euler"])
    if params.get("scale"):
        obj.scale = tuple(params["scale"])
    
    result = {
        "ok": True,
        "action": "set_transform",
        "name": obj.name,
        "location": [round(c, 4) for c in obj.location],
        "rotation_euler": [round(math.degrees(c), 2) for c in obj.rotation_euler],
        "scale": [round(c, 4) for c in obj.scale],
        "dimensions": [round(c, 4) for c in obj.dimensions]
    }

print("SENTINEL_OUTPUT_START" + json.dumps(result) + "SENTINEL_OUTPUT_END")
"""

_GET_MANIFEST_TEMPLATE = """
import bpy
import re
import json
import math
from mathutils import Vector

params = json.loads(PARAMS_JSON)
prefix = params.get("prefix")
SAFE_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,63}$")

objects = []
for obj in bpy.data.objects:
    clean_name = re.sub(r"[^A-Za-z0-9_.-]", "_", obj.name)[:63]
    if prefix and not clean_name.startswith(prefix):
        continue
    
    poly_count = 0
    world_aabb_min = [0, 0, 0]
    world_aabb_max = [0, 0, 0]
    if obj.type == 'MESH' and obj.data:
        poly_count = len(obj.data.polygons)
        # Compute world AABB from mesh vertices
        if obj.data.vertices:
            world_verts = [obj.matrix_world @ v.co for v in obj.data.vertices]
            world_aabb_min = [min(v[i] for v in world_verts) for i in range(3)]
            world_aabb_max = [max(v[i] for v in world_verts) for i in range(3)]
    
    # Use world transform, not local
    world_loc = obj.matrix_world.translation
    # Extract rotation from matrix (as Euler XYZ)
    world_rot = obj.matrix_world.to_euler('XYZ')
        
    objects.append({
        "name": clean_name,
        "type": obj.type,
        "location": [round(c, 4) for c in world_loc],
        "rotation": [round(math.degrees(c), 2) for c in world_rot],
        "dimensions": [round(c, 4) for c in obj.dimensions],
        "world_aabb_min": [round(c, 4) for c in world_aabb_min],
        "world_aabb_max": [round(c, 4) for c in world_aabb_max],
        "poly_count": poly_count,
        "visible": not obj.hide_viewport,
        "parent": obj.parent.name if obj.parent else None
    })

result = {
    "ok": True,
    "object_count": len(objects),
    "objects": objects
}
print("SENTINEL_OUTPUT_START" + json.dumps(result) + "SENTINEL_OUTPUT_END")
"""

_CREATE_CYLINDER_TEMPLATE = """
import bpy
import json
import math

params = json.loads(PARAMS_JSON)
name = params["name"]
radius = params["radius"]
depth = params["depth"]
loc = params["location"]
rot = params.get("rotation") or [0, 0, 0]
rot_rad = tuple(math.radians(r) for r in rot)
vertices = int(params.get("vertices", 32))

if name in bpy.data.objects:
    result = {"ok": False, "error": f"Object '{name}' already exists. Use unique names."}
    print("SENTINEL_OUTPUT_START" + json.dumps(result) + "SENTINEL_OUTPUT_END")
else:
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=tuple(loc), rotation=rot_rad, align='WORLD')
    obj = bpy.context.active_object
    obj.name = name
    obj.data.name = name
    
    # Verify using circumradius (max XY distance from center) and Z extent
    # This works for any vertex count (hexagonal, octagonal, etc.)
    verts = [v.co for v in obj.data.vertices]
    circumradius = max(math.hypot(v.x, v.y) for v in verts)
    z_min = min(v.z for v in verts)
    z_max = max(v.z for v in verts)
    z_extent = z_max - z_min
    
    tol = 0.01
    radius_ok = abs(circumradius - radius) < radius * tol + 0.001
    depth_ok = abs(z_extent - depth) < depth * tol + 0.001
    size_ok = radius_ok and depth_ok

    result = {
        "ok": size_ok,
        "action": "create_cylinder",
        "name": obj.name,
        "radius": radius,
        "depth": depth,
        "location": [round(c, 4) for c in obj.location],
        "circumradius": round(circumradius, 4),
        "z_extent": round(z_extent, 4),
        "rotation": [round(math.degrees(c), 2) for c in obj.rotation_euler]
    }
    if not size_ok:
        result["error"] = f"Dimension mismatch: expected radius={radius}, depth={depth}, got circumradius={round(circumradius,4)}, z_extent={round(z_extent,4)}"
    print("SENTINEL_OUTPUT_START" + json.dumps(result) + "SENTINEL_OUTPUT_END")
"""

_CREATE_CONE_TEMPLATE = """
import bpy
import json
import math

params = json.loads(PARAMS_JSON)
name = params["name"]
radius1 = params["radius1"]
depth = params["depth"]
loc = params["location"]
rot = params.get("rotation") or [0, 0, 0]
rot_rad = tuple(math.radians(r) for r in rot)

if name in bpy.data.objects:
    result = {"ok": False, "error": f"Object '{name}' already exists. Use unique names."}
    print("SENTINEL_OUTPUT_START" + json.dumps(result) + "SENTINEL_OUTPUT_END")
else:
    # Note: Blender cone origin is at center of base-to-tip, not at base
    bpy.ops.mesh.primitive_cone_add(radius1=radius1, depth=depth, location=tuple(loc), rotation=rot_rad, align='WORLD')
    obj = bpy.context.active_object
    obj.name = name
    obj.data.name = name
    
    # Verify using circumradius and Z extent
    verts = [v.co for v in obj.data.vertices]
    circumradius = max(math.hypot(v.x, v.y) for v in verts)
    z_min = min(v.z for v in verts)
    z_max = max(v.z for v in verts)
    z_extent = z_max - z_min
    
    tol = 0.01
    radius_ok = abs(circumradius - radius1) < radius1 * tol + 0.001
    depth_ok = abs(z_extent - depth) < depth * tol + 0.001
    size_ok = radius_ok and depth_ok

    result = {
        "ok": size_ok,
        "action": "create_cone",
        "name": obj.name,
        "radius1": radius1,
        "depth": depth,
        "location": [round(c, 4) for c in obj.location],
        "circumradius": round(circumradius, 4),
        "z_extent": round(z_extent, 4),
        "rotation": [round(math.degrees(c), 2) for c in obj.rotation_euler]
    }
    if not size_ok:
        result["error"] = f"Dimension mismatch: expected radius1={radius1}, depth={depth}, got circumradius={round(circumradius,4)}, z_extent={round(z_extent,4)}"
    print("SENTINEL_OUTPUT_START" + json.dumps(result) + "SENTINEL_OUTPUT_END")
"""

_CREATE_TORUS_TEMPLATE = """
import bpy
import json
import math

params = json.loads(PARAMS_JSON)
name = params["name"]
major_radius = params["major_radius"]
minor_radius = params["minor_radius"]
loc = params["location"]
rot = params.get("rotation") or [0, 0, 0]
rot_rad = tuple(math.radians(r) for r in rot)

if name in bpy.data.objects:
    result = {"ok": False, "error": f"Object '{name}' already exists. Use unique names."}
else:
    bpy.ops.mesh.primitive_torus_add(major_radius=major_radius, minor_radius=minor_radius, location=tuple(loc), rotation=rot_rad, align='WORLD')
    obj = bpy.context.active_object
    obj.name = name
    obj.data.name = name
    
    result = {
        "ok": True,
        "action": "create_torus",
        "name": obj.name,
        "major_radius": major_radius,
        "minor_radius": minor_radius,
        "location": [round(c, 4) for c in obj.location],
        "dimensions": [round(c, 4) for c in obj.dimensions]
    }
print("SENTINEL_OUTPUT_START" + json.dumps(result) + "SENTINEL_OUTPUT_END")
"""

_APPLY_SUBDIVISION_TEMPLATE = _FIND_OBJECT_HELPER + """
import bpy
import json

params = json.loads(PARAMS_JSON)
name = params["name"]
levels = params.get("levels") or 2
render_levels = params.get("render_levels") or levels

obj = _find_blender_object(name)
if not obj:
    result = {"ok": False, "error": f"Object '{name}' not found."}
else:
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    mod = obj.modifiers.new(name="Subsurf", type='SUBSURF')
    mod.levels = levels
    mod.render_levels = render_levels
    bpy.ops.object.modifier_apply(modifier=mod.name)
    result = {
        "ok": True,
        "action": "apply_subdivision",
        "name": obj.name,
        "levels": levels,
        "poly_count": len(obj.data.polygons) if obj.type == 'MESH' and obj.data else 0
    }
print("SENTINEL_OUTPUT_START" + json.dumps(result) + "SENTINEL_OUTPUT_END")
"""

_APPLY_BOOLEAN_TEMPLATE = _FIND_OBJECT_HELPER + """
import bpy
import json

params = json.loads(PARAMS_JSON)
name = params["name"]
target_name = params["target_name"]
op = params.get("operation", "DIFFERENCE").upper()
delete_target = params.get("delete_target", True)

obj = _find_blender_object(name)
target_obj = _find_blender_object(target_name)

if not obj:
    result = {"ok": False, "error": f"Base object '{name}' not found."}
elif not target_obj:
    result = {"ok": False, "error": f"Target object '{target_name}' not found."}
elif name == target_name:
    result = {"ok": False, "error": "Cannot boolean an object with itself."}
elif obj.type != 'MESH' or target_obj.type != 'MESH':
    result = {"ok": False, "error": "Boolean requires both objects to be meshes."}
else:
    # Record pre-boolean state for verification
    pre_poly_count = len(obj.data.polygons)
    pre_vert_count = len(obj.data.vertices)
    
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    mod = obj.modifiers.new(name="Boolean", type='BOOLEAN')
    mod.operation = op
    mod.object = target_obj
    bpy.ops.object.modifier_apply(modifier=mod.name)
    
    # Verify boolean actually modified geometry
    post_poly_count = len(obj.data.polygons)
    post_vert_count = len(obj.data.vertices)
    geometry_changed = (post_poly_count != pre_poly_count or post_vert_count != pre_vert_count)
    
    if delete_target:
        bpy.data.objects.remove(target_obj, do_unlink=True)
    
    # Warn if boolean had no effect (silent failure detection)
    if not geometry_changed:
        result = {
            "ok": False,
            "error": f"Boolean {op} had no effect on geometry (pre: {pre_poly_count} polys, post: {post_poly_count} polys). Objects may not intersect.",
            "action": "apply_boolean",
            "name": obj.name,
            "target_name": target_name,
            "operation": op,
            "pre_poly_count": pre_poly_count,
            "post_poly_count": post_poly_count,
        }
    else:
        result = {
            "ok": True,
            "action": "apply_boolean",
            "name": obj.name,
            "target_name": target_name,
            "operation": op,
            "poly_count": post_poly_count,
            "geometry_changed": True,
        }
print("SENTINEL_OUTPUT_START" + json.dumps(result) + "SENTINEL_OUTPUT_END")
"""

_APPLY_BEVEL_TEMPLATE = _FIND_OBJECT_HELPER + """
import bpy
import json

params = json.loads(PARAMS_JSON)
name = params["name"]
width = params.get("width") or 0.05
segments = params.get("segments") or 3

obj = _find_blender_object(name)
if not obj:
    result = {"ok": False, "error": f"Object '{name}' not found."}
else:
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    mod = obj.modifiers.new(name="Bevel", type='BEVEL')
    mod.width = width
    mod.segments = segments
    bpy.ops.object.modifier_apply(modifier=mod.name)
    result = {
        "ok": True,
        "action": "apply_bevel",
        "name": obj.name,
        "width": width,
        "segments": segments,
        "poly_count": len(obj.data.polygons) if obj.type == 'MESH' and obj.data else 0
    }
print("SENTINEL_OUTPUT_START" + json.dumps(result) + "SENTINEL_OUTPUT_END")
"""

_SET_SMOOTH_SHADING_TEMPLATE = _FIND_OBJECT_HELPER + """
import bpy
import json
import math

params = json.loads(PARAMS_JSON)
name = params["name"]
smooth = params.get("smooth", True)
angle = params.get("angle") or 30.0

obj = _find_blender_object(name)
if not obj:
    result = {"ok": False, "error": f"Object '{name}' not found."}
else:
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    if smooth:
        # Use shade_smooth_by_angle if available (Blender 4.1+)
        try:
            bpy.ops.object.shade_smooth_by_angle(angle=math.radians(angle))
        except AttributeError:
            bpy.ops.object.shade_smooth()
            if hasattr(obj.data, 'use_auto_smooth'):
                obj.data.use_auto_smooth = True
                obj.data.auto_smooth_angle = math.radians(angle)
    else:
        bpy.ops.object.shade_flat()
    result = {
        "ok": True,
        "action": "set_smooth_shading",
        "name": obj.name,
        "smooth": smooth,
        "angle": angle
    }
print("SENTINEL_OUTPUT_START" + json.dumps(result) + "SENTINEL_OUTPUT_END")
"""

_SET_MATERIAL_TEMPLATE = _FIND_OBJECT_HELPER + """
import bpy
import json

params = json.loads(PARAMS_JSON)
name = params["name"]
color = params.get("color") or [0.8, 0.8, 0.8, 1.0]
if len(color) == 3:
    color = list(color) + [1.0]
metallic = params.get("metallic") if params.get("metallic") is not None else 0.0
roughness = params.get("roughness") if params.get("roughness") is not None else 0.5
emission_color = params.get("emission_color")
# Default emission_strength to 1.0 when emission_color is provided (Blender 4+ defaults to 0)
emission_strength = params.get("emission_strength")
if emission_strength is None and emission_color:
    emission_strength = 1.0

obj = _find_blender_object(name)
if not obj:
    result = {"ok": False, "error": f"Object '{name}' not found."}
else:
    mat_name = f"Mat_{obj.name}"
    mat = bpy.data.materials.get(mat_name)
    if not mat:
        mat = bpy.data.materials.new(name=mat_name)
    mat.use_nodes = True
    # Find BSDF by type, not by name (more robust)
    bsdf = None
    for node in mat.node_tree.nodes:
        if node.type == 'BSDF_PRINCIPLED':
            bsdf = node
            break
    if not bsdf:
        result = {"ok": False, "error": "Material has no Principled BSDF node."}
    else:
        if "Base Color" in bsdf.inputs:
            bsdf.inputs["Base Color"].default_value = tuple(color)
        if "Metallic" in bsdf.inputs:
            bsdf.inputs["Metallic"].default_value = float(metallic)
        if "Roughness" in bsdf.inputs:
            bsdf.inputs["Roughness"].default_value = float(roughness)
        if emission_color and "Emission Color" in bsdf.inputs:
            e_col = list(emission_color[:3]) + [1.0]
            bsdf.inputs["Emission Color"].default_value = tuple(e_col)
            if "Emission Strength" in bsdf.inputs and emission_strength is not None:
                bsdf.inputs["Emission Strength"].default_value = float(emission_strength)
        
        if obj.data and hasattr(obj.data, "materials"):
            if len(obj.data.materials) == 0:
                obj.data.materials.append(mat)
            else:
                obj.data.materials[0] = mat
        
        result = {
            "ok": True,
            "action": "set_material",
            "name": obj.name,
            "material_name": mat.name,
            "base_color": color,
            "metallic": metallic,
            "roughness": roughness
        }
print("SENTINEL_OUTPUT_START" + json.dumps(result) + "SENTINEL_OUTPUT_END")
"""

_JOIN_OBJECTS_TEMPLATE = _FIND_OBJECT_HELPER + """
import bpy
import json

params = json.loads(PARAMS_JSON)
names = params["names"]
target_name = params.get("target_name") or names[0]

objs = [_find_blender_object(n) for n in names if _find_blender_object(n)]
if len(objs) < 2:
    result = {"ok": False, "error": f"Need at least 2 valid mesh objects to join, found {len(objs)}."}
else:
    bpy.ops.object.select_all(action='DESELECT')
    primary = objs[0]
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = primary
    bpy.ops.object.join()
    primary.name = target_name
    result = {
        "ok": True,
        "action": "join_objects",
        "name": primary.name,
        "poly_count": len(primary.data.polygons) if primary.type == 'MESH' and primary.data else 0
    }
print("SENTINEL_OUTPUT_START" + json.dumps(result) + "SENTINEL_OUTPUT_END")
"""

_DELETE_OBJECT_TEMPLATE = _FIND_OBJECT_HELPER + """
import bpy
import json

params = json.loads(PARAMS_JSON)
name = params["name"]
obj = _find_blender_object(name)
if not obj:
    result = {"ok": False, "error": f"Object '{name}' not found."}
else:
    del_name = obj.name
    bpy.data.objects.remove(obj, do_unlink=True)
    result = {"ok": True, "action": "delete_object", "name": del_name}
print("SENTINEL_OUTPUT_START" + json.dumps(result) + "SENTINEL_OUTPUT_END")
"""

_CLEAR_SCENE_TEMPLATE = """
import bpy
import json

params = json.loads(PARAMS_JSON)
keep_cam_light = params.get("keep_camera_and_lights", True)

removed = []
for obj in list(bpy.data.objects):
    if keep_cam_light and obj.type in ('CAMERA', 'LIGHT'):
        continue
    removed.append(obj.name)
    bpy.data.objects.remove(obj, do_unlink=True)

# Purge orphan data blocks (meshes, materials, etc.)
bpy.ops.outliner.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)

result = {
    "ok": True,
    "action": "clear_scene",
    "removed_count": len(removed),
    "removed_objects": removed[:20],
    "orphans_purged": True
}
print("SENTINEL_OUTPUT_START" + json.dumps(result) + "SENTINEL_OUTPUT_END")
"""

_CREATE_LIGHT_TEMPLATE = """
import bpy
import json

params = json.loads(PARAMS_JSON)
name = params["name"]
ltype = params.get("type", "POINT").upper()
energy = params.get("energy")
loc = params.get("location") or [4.0, -4.0, 6.0]
color = params.get("color") or [1.0, 1.0, 1.0]
collection_name = params.get("_collection_name")  # Generation collection if provided

# Per-type energy defaults (SUN uses W/m², others use Watts)
if energy is None:
    energy = 5.0 if ltype == "SUN" else 1000.0

if name in bpy.data.objects:
    result = {"ok": False, "error": f"Object '{name}' already exists. Use unique names."}
else:
    light_data = bpy.data.lights.new(name=name, type=ltype)
    light_data.energy = energy
    if color:
        light_data.color = tuple(color[:3])
    light_obj = bpy.data.objects.new(name=name, object_data=light_data)
    
    # Link to generation collection if specified, else scene collection
    target_coll = bpy.data.collections.get(collection_name) if collection_name else None
    if target_coll:
        target_coll.objects.link(light_obj)
    else:
        bpy.context.scene.collection.objects.link(light_obj)
    light_obj.location = tuple(loc)
    
    result = {
        "ok": True,
        "action": "create_light",
        "name": light_obj.name,
        "type": ltype,
        "energy": energy,
        "location": [round(c, 4) for c in light_obj.location]
    }
print("SENTINEL_OUTPUT_START" + json.dumps(result) + "SENTINEL_OUTPUT_END")
"""

_CREATE_CAMERA_TEMPLATE = """
import bpy
import json
import math

params = json.loads(PARAMS_JSON)
name = params["name"]
loc = params.get("location") or [7.0, -7.0, 5.0]
rot = params.get("rotation") or [60.0, 0.0, 45.0]
rot_rad = tuple(math.radians(r) for r in rot)
collection_name = params.get("_collection_name")  # Generation collection if provided

if name in bpy.data.objects:
    result = {"ok": False, "error": f"Object '{name}' already exists. Use unique names."}
else:
    cam_data = bpy.data.cameras.new(name=name)
    cam_obj = bpy.data.objects.new(name=name, object_data=cam_data)
    
    # Link to generation collection if specified, else scene collection
    target_coll = bpy.data.collections.get(collection_name) if collection_name else None
    if target_coll:
        target_coll.objects.link(cam_obj)
    else:
        bpy.context.scene.collection.objects.link(cam_obj)
    cam_obj.location = tuple(loc)
    cam_obj.rotation_mode = 'XYZ'
    cam_obj.rotation_euler = rot_rad
    
    if not bpy.context.scene.camera:
        bpy.context.scene.camera = cam_obj
    
    result = {
        "ok": True,
        "action": "create_camera",
        "name": cam_obj.name,
        "location": [round(c, 4) for c in cam_obj.location],
        "rotation": [round(math.degrees(c), 2) for c in cam_obj.rotation_euler]
    }
print("SENTINEL_OUTPUT_START" + json.dumps(result) + "SENTINEL_OUTPUT_END")
"""

_PARENT_OBJECT_TEMPLATE = _FIND_OBJECT_HELPER + """
import bpy
import json

params = json.loads(PARAMS_JSON)
name = params["name"]
parent_name = params["parent_name"]
keep_transform = params.get("keep_transform", True)

obj = _find_blender_object(name)
parent_obj = _find_blender_object(parent_name)

if not obj:
    result = {"ok": False, "error": f"Child object '{name}' not found."}
elif not parent_obj:
    result = {"ok": False, "error": f"Parent object '{parent_name}' not found."}
else:
    # Update view layer to ensure matrix_world is current
    bpy.context.view_layer.update()
    obj.parent = parent_obj
    if keep_transform:
        obj.matrix_parent_inverse = parent_obj.matrix_world.inverted()
    result = {
        "ok": True,
        "action": "parent_object",
        "name": obj.name,
        "parent_name": parent_obj.name,
        "keep_transform": keep_transform
    }
print("SENTINEL_OUTPUT_START" + json.dumps(result) + "SENTINEL_OUTPUT_END")
"""

_SET_ORIGIN_TEMPLATE = _FIND_OBJECT_HELPER + """
import bpy
import json

params = json.loads(PARAMS_JSON)
name = params["name"]
origin_mode = params.get("origin_mode") or "GEOMETRY_ORIGIN"

valid_modes = {"GEOMETRY_ORIGIN", "ORIGIN_GEOMETRY", "CURSOR", "BOUNDS_CENTER"}
if origin_mode not in valid_modes:
    result = {"ok": False, "error": f"Unknown origin_mode '{origin_mode}'. Valid: {valid_modes}"}
    print("SENTINEL_OUTPUT_START" + json.dumps(result) + "SENTINEL_OUTPUT_END")
else:
    mode_map = {
        "GEOMETRY_ORIGIN": "GEOMETRY_ORIGIN",
        "ORIGIN_GEOMETRY": "ORIGIN_GEOMETRY",
        "CURSOR": "ORIGIN_CURSOR",
        "BOUNDS_CENTER": "ORIGIN_GEOMETRY"
    }
    op_type = mode_map[origin_mode]
    
    obj = _find_blender_object(name)
    if not obj:
        result = {"ok": False, "error": f"Object '{name}' not found."}
    else:
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        if origin_mode == "BOUNDS_CENTER":
            bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='BOUNDS')
        else:
            bpy.ops.object.origin_set(type=op_type)
        result = {
            "ok": True,
            "action": "set_origin",
            "name": obj.name,
            "origin_mode": origin_mode,
            "location": [round(c, 4) for c in obj.location]
        }
    print("SENTINEL_OUTPUT_START" + json.dumps(result) + "SENTINEL_OUTPUT_END")
"""

_SEPARATE_MESH_TEMPLATE = _FIND_OBJECT_HELPER + """
import bpy
import json

params = json.loads(PARAMS_JSON)
name = params["name"]
mode = params.get("mode") or "LOOSE"

valid_modes = {"SELECTED", "LOOSE", "MATERIAL"}
if mode not in valid_modes:
    result = {"ok": False, "error": f"Unknown mode '{mode}'. Valid: {valid_modes}"}
    print("SENTINEL_OUTPUT_START" + json.dumps(result) + "SENTINEL_OUTPUT_END")
else:
    obj = _find_blender_object(name)
    if not obj or obj.type != 'MESH':
        result = {"ok": False, "error": f"Mesh object '{name}' not found."}
    else:
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        before_objs = set(bpy.data.objects.keys())
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.separate(type=mode)
        bpy.ops.object.mode_set(mode='OBJECT')
        after_objs = set(bpy.data.objects.keys())
        created = list(after_objs - before_objs)
        result = {
            "ok": True,
            "action": "separate_mesh",
            "name": obj.name,
            "mode": mode,
            "created_objects": created
        }
    print("SENTINEL_OUTPUT_START" + json.dumps(result) + "SENTINEL_OUTPUT_END")
"""

_APPLY_ARRAY_TEMPLATE = _FIND_OBJECT_HELPER + """
import bpy
import json

params = json.loads(PARAMS_JSON)
name = params["name"]
count = params.get("count") or 2
offset = params.get("offset") or [1.0, 0.0, 0.0]
use_relative = params.get("use_relative_offset", True)
use_constant = params.get("use_constant_offset", False)
constant_offset = params.get("constant_offset")

obj = _find_blender_object(name)
if not obj:
    result = {"ok": False, "error": f"Object '{name}' not found."}
else:
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    mod = obj.modifiers.new(name="Array", type='ARRAY')
    mod.count = count
    mod.use_relative_offset = use_relative
    mod.use_constant_offset = use_constant
    if use_relative:
        mod.relative_offset_displace = tuple(offset)
    if use_constant and constant_offset:
        mod.constant_offset_displace = tuple(constant_offset)
    bpy.ops.object.modifier_apply(modifier=mod.name)
    result = {
        "ok": True,
        "action": "apply_array",
        "name": obj.name,
        "count": count,
        "poly_count": len(obj.data.polygons) if obj.type == 'MESH' and obj.data else 0
    }
print("SENTINEL_OUTPUT_START" + json.dumps(result) + "SENTINEL_OUTPUT_END")
"""


def render_op_script(template: str, params: BaseModel) -> str:
    """Safely inject validated parameters as a JSON string literal with pre-flight linting."""
    from core.codegen_linter import lint, CodegenLintError

    params_json = json.dumps(params.model_dump())
    script = f"PARAMS_JSON = {params_json!r}\n" + template

    missing = lint(script, allowed_globals={"PARAMS_JSON", "_find_blender_object"})
    if missing:
        raise CodegenLintError(missing, script)

    return script


def parse_op_output(raw_stdout: str) -> Dict[str, Any]:
    """Extract and validate Sentinel structured JSON from Blender execution output."""
    if not raw_stdout:
        raise ValueError("Blender returned empty output.")
    
    # Locate delimiter
    start_tag = "SENTINEL_OUTPUT_START"
    end_tag = "SENTINEL_OUTPUT_END"
    
    start_idx = raw_stdout.find(start_tag)
    end_idx = raw_stdout.find(end_tag)
    
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        json_str = raw_stdout[start_idx + len(start_tag):end_idx].strip()
        try:
            data = json.loads(json_str)
            if not data.get("ok", False):
                raise ValueError(data.get("error", "Unknown operation failure in Blender"))
            return data
        except json.JSONDecodeError as err:
            raise ValueError(f"Corrupt JSON payload from Blender: {err}")
    
    # Show both head and tail for tracebacks
    head = raw_stdout[:200]
    tail = raw_stdout[-500:] if len(raw_stdout) > 500 else ""
    raise ValueError(f"Blender output did not contain structured Sentinel payload.\nHead: {head}\nTail: {tail}")
