"""Connector Endpoint Geometry — Per BLENDER_GEOMETRY_CALCULATIONS.md Section 8.

RULE: For connectors (struts, rods, beams), define by endpoints, not Euler angles.

This module provides the canonical way to compute connector transforms:
1. Define start and end points in world space
2. Compute midpoint, length, and rotation quaternion
3. Never use arbitrary LLM Euler angles when endpoints are known

The rotation maps the cylinder's local +Z axis to the start→end direction.
"""

from typing import Tuple, Dict, Any, Optional
import math


class Vec3:
    """Minimal 3D vector for connector geometry (no external deps)."""
    __slots__ = ("x", "y", "z")

    def __init__(self, x: float = 0.0, y: float = 0.0, z: float = 0.0):
        self.x = float(x)
        self.y = float(y)
        self.z = float(z)

    @classmethod
    def from_tuple(cls, t: Tuple[float, float, float]) -> "Vec3":
        return cls(t[0], t[1], t[2])

    def __sub__(self, other: "Vec3") -> "Vec3":
        return Vec3(self.x - other.x, self.y - other.y, self.z - other.z)

    def __add__(self, other: "Vec3") -> "Vec3":
        return Vec3(self.x + other.x, self.y + other.y, self.z + other.z)

    def __mul__(self, scalar: float) -> "Vec3":
        return Vec3(self.x * scalar, self.y * scalar, self.z * scalar)

    def __truediv__(self, scalar: float) -> "Vec3":
        return Vec3(self.x / scalar, self.y / scalar, self.z / scalar)

    def length(self) -> float:
        return math.sqrt(self.x ** 2 + self.y ** 2 + self.z ** 2)

    def normalized(self) -> "Vec3":
        mag = self.length()
        if mag < 1e-9:
            return Vec3(0, 0, 1)
        return self / mag

    def dot(self, other: "Vec3") -> float:
        return self.x * other.x + self.y * other.y + self.z * other.z

    def cross(self, other: "Vec3") -> "Vec3":
        return Vec3(
            self.y * other.z - self.z * other.y,
            self.z * other.x - self.x * other.z,
            self.x * other.y - self.y * other.x,
        )

    def to_tuple(self) -> Tuple[float, float, float]:
        return (round(self.x, 6), round(self.y, 6), round(self.z, 6))


class Quaternion:
    """Minimal quaternion for rotation (w, x, y, z)."""
    __slots__ = ("w", "x", "y", "z")

    def __init__(self, w: float = 1.0, x: float = 0.0, y: float = 0.0, z: float = 0.0):
        self.w = float(w)
        self.x = float(x)
        self.y = float(y)
        self.z = float(z)

    @classmethod
    def from_axis_angle(cls, axis: Vec3, angle: float) -> "Quaternion":
        """Create quaternion from axis-angle representation."""
        axis = axis.normalized()
        half = angle / 2.0
        s = math.sin(half)
        return cls(math.cos(half), axis.x * s, axis.y * s, axis.z * s)

    @classmethod
    def rotation_between(cls, v_from: Vec3, v_to: Vec3) -> "Quaternion":
        """Compute quaternion that rotates v_from to v_to."""
        v_from = v_from.normalized()
        v_to = v_to.normalized()

        dot = v_from.dot(v_to)

        # Vectors are parallel (same direction)
        if dot > 0.9999:
            return cls(1, 0, 0, 0)

        # Vectors are anti-parallel (opposite direction)
        if dot < -0.9999:
            # Find orthogonal axis
            ortho = Vec3(1, 0, 0).cross(v_from)
            if ortho.length() < 0.01:
                ortho = Vec3(0, 1, 0).cross(v_from)
            return cls.from_axis_angle(ortho, math.pi)

        # General case
        axis = v_from.cross(v_to)
        s = math.sqrt((1 + dot) * 2)
        inv_s = 1 / s
        return cls(s / 2, axis.x * inv_s, axis.y * inv_s, axis.z * inv_s)

    def to_euler_xyz(self) -> Tuple[float, float, float]:
        """Convert to Euler XYZ angles in radians."""
        # Roll (X)
        sinr_cosp = 2 * (self.w * self.x + self.y * self.z)
        cosr_cosp = 1 - 2 * (self.x ** 2 + self.y ** 2)
        roll = math.atan2(sinr_cosp, cosr_cosp)

        # Pitch (Y)
        sinp = 2 * (self.w * self.y - self.z * self.x)
        if abs(sinp) >= 1:
            pitch = math.copysign(math.pi / 2, sinp)
        else:
            pitch = math.asin(sinp)

        # Yaw (Z)
        siny_cosp = 2 * (self.w * self.z + self.x * self.y)
        cosy_cosp = 1 - 2 * (self.y ** 2 + self.z ** 2)
        yaw = math.atan2(siny_cosp, cosy_cosp)

        return (round(roll, 6), round(pitch, 6), round(yaw, 6))

    def to_euler_degrees(self) -> Tuple[float, float, float]:
        """Convert to Euler XYZ angles in degrees."""
        rad = self.to_euler_xyz()
        return (
            round(math.degrees(rad[0]), 4),
            round(math.degrees(rad[1]), 4),
            round(math.degrees(rad[2]), 4),
        )


def compute_connector_transform(
    start_point: Tuple[float, float, float],
    end_point: Tuple[float, float, float],
) -> Dict[str, Any]:
    """Canonical connector orientation per BLENDER_GEOMETRY_CALCULATIONS.md.

    Maps cylinder's local +Z to the start→end direction.

    Args:
        start_point: World-space start position
        end_point: World-space end position

    Returns:
        {
            'location': (x, y, z) midpoint,
            'depth': length of connector,
            'rotation_quat': (w, x, y, z) quaternion,
            'rotation_euler_rad': (rx, ry, rz) in radians,
            'rotation_euler_deg': (rx, ry, rz) in degrees,
        }
    """
    start = Vec3.from_tuple(start_point)
    end = Vec3.from_tuple(end_point)

    direction = end - start
    length = direction.length()
    midpoint = (start + end) / 2

    # Rotation that maps (0, 0, 1) to direction
    up = Vec3(0, 0, 1)
    rotation = Quaternion.rotation_between(up, direction.normalized())

    return {
        "location": midpoint.to_tuple(),
        "depth": round(length, 6),
        "rotation_quat": (rotation.w, rotation.x, rotation.y, rotation.z),
        "rotation_euler_rad": rotation.to_euler_xyz(),
        "rotation_euler_deg": rotation.to_euler_degrees(),
    }


def compute_strut_endpoints(
    parent_center: Tuple[float, float, float],
    parent_radius: float,
    parent_half_z: float,
    child_center: Tuple[float, float, float],
    child_radius: float,
    child_half_z: float,
    strut_offset_angle_deg: float = 0.0,
) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
    """Compute strut anchor points on parent and child surfaces.

    For a strut connecting a pillar (parent) to a dish (child):
    - Start point: on parent's top surface at its outer radius
    - End point: on child's bottom surface at its outer radius

    Args:
        parent_center: Parent object centroid
        parent_radius: Parent's XY radius
        parent_half_z: Parent's half-height
        child_center: Child object centroid
        child_radius: Child's XY radius
        child_half_z: Child's half-height
        strut_offset_angle_deg: Compass angle for strut position (0=+X, 90=+Y)

    Returns:
        (start_point, end_point) in world coordinates
    """
    angle_rad = math.radians(strut_offset_angle_deg)
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)

    # Start: parent top surface at radius
    start = (
        parent_center[0] + parent_radius * cos_a,
        parent_center[1] + parent_radius * sin_a,
        parent_center[2] + parent_half_z,
    )

    # End: child bottom surface at radius
    end = (
        child_center[0] + child_radius * cos_a,
        child_center[1] + child_radius * sin_a,
        child_center[2] - child_half_z,
    )

    return (start, end)


def compute_radial_strut_transforms(
    parent_center: Tuple[float, float, float],
    parent_radius: float,
    parent_half_z: float,
    child_center: Tuple[float, float, float],
    child_radius: float,
    child_half_z: float,
    strut_count: int,
    strut_radius: float,
    start_angle_deg: float = 0.0,
) -> list:
    """Compute transforms for N evenly-spaced radial struts.

    Args:
        parent_center: Parent object centroid
        parent_radius: Parent's XY radius
        parent_half_z: Parent's half-height
        child_center: Child object centroid
        child_radius: Child's XY radius
        child_half_z: Child's half-height
        strut_count: Number of struts (e.g., 4 for quad support)
        strut_radius: Radius of each strut cylinder
        start_angle_deg: Starting compass angle

    Returns:
        List of dicts with location, depth, rotation for each strut
    """
    struts = []
    angle_step = 360.0 / strut_count

    for i in range(strut_count):
        angle = start_angle_deg + i * angle_step
        start, end = compute_strut_endpoints(
            parent_center, parent_radius, parent_half_z,
            child_center, child_radius, child_half_z,
            angle,
        )
        transform = compute_connector_transform(start, end)
        transform["strut_index"] = i
        transform["compass_angle_deg"] = angle
        transform["radius"] = strut_radius
        struts.append(transform)

    return struts


def is_connector_part(label: str, socket_name: str) -> bool:
    """Check if a part should use endpoint-based connector geometry.

    Per doc: struts, rods, beams, braces, supports, spokes, legs, arms.
    """
    keywords = (
        "strut", "brace", "support", "rod", "beam", "bar",
        "connector", "leg", "arm", "spoke", "axle", "shaft",
    )
    combined = (label + " " + socket_name).lower()
    return any(kw in combined for kw in keywords)


def resolve_connector_from_offset(
    parent_center: Tuple[float, float, float],
    parent_shape: Dict[str, Any],
    local_offset: Tuple[float, float, float],
    connector_depth: float,
) -> Dict[str, Any]:
    """Resolve connector transform from parent center and local offset.

    When the LLM provides a local_offset for a connector, we can infer
    the start and end points:
    - Start: parent surface in the direction of offset
    - End: start + offset direction * connector_depth

    This replaces the Euler angle guessing in graph_compiler.
    """
    # Get parent dimensions
    prim = parent_shape.get("primitive", "box")
    if prim in ("cylinder", "cone"):
        parent_radius = float(parent_shape.get("radius", parent_shape.get("radius1", 1.0)))
        parent_half_z = float(parent_shape.get("depth", 2.0)) / 2.0
    elif prim in ("sphere", "hemisphere"):
        parent_radius = float(parent_shape.get("radius", 1.0))
        parent_half_z = parent_radius
    else:  # box
        size = parent_shape.get("size", [2.0, 2.0, 2.0])
        parent_radius = max(float(size[0]), float(size[1])) / 2.0
        parent_half_z = float(size[2]) / 2.0

    ox, oy, oz = local_offset
    xy_mag = math.sqrt(ox ** 2 + oy ** 2)

    if xy_mag < 0.001:
        # Purely vertical connector (unusual for struts)
        if oz > 0:
            start = (parent_center[0], parent_center[1], parent_center[2] + parent_half_z)
            end = (parent_center[0], parent_center[1], start[2] + connector_depth)
        else:
            start = (parent_center[0], parent_center[1], parent_center[2] - parent_half_z)
            end = (parent_center[0], parent_center[1], start[2] - connector_depth)
    else:
        # Diagonal or horizontal connector
        # Normalize XY direction
        dir_x = ox / xy_mag
        dir_y = oy / xy_mag

        # Start point: on parent surface
        start = (
            parent_center[0] + parent_radius * dir_x,
            parent_center[1] + parent_radius * dir_y,
            parent_center[2] + oz * (parent_half_z / abs(oz)) if abs(oz) > 0.001 else parent_center[2],
        )

        # End point: offset from start in the direction of local_offset
        offset_vec = Vec3.from_tuple(local_offset).normalized()
        end_vec = Vec3.from_tuple(start) + offset_vec * connector_depth
        end = end_vec.to_tuple()

    return compute_connector_transform(start, end)
