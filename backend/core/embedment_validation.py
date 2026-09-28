"""Analytical embedment validation for pierce-type socket connections.

Provides closed-form validation for THROUGH_AXIS, RADIAL_BRIDGE, and STRUT socket types
where BVH vertex sampling is structurally blind (child passes through parent with no
vertices inside the target volume).

This module is intentionally pure functions with no Blender/MCP dependencies so it can be:
1. Called by Stage 4's resolve_transform for immediate pre-build validation
2. Called by AssemblyVerificationGate as a pre-check before BVH fallback
3. Unit tested directly without any Blender instance
"""

from dataclasses import dataclass
from typing import Tuple, Optional, Literal
from enum import Enum


class PierceAxis(Enum):
    """Axis along which a child pierces through a parent."""
    X = "x"
    Y = "y"
    Z = "z"


@dataclass(frozen=True)
class EmbedmentResult:
    """Result of analytical embedment validation."""
    valid: bool
    embedment_depth_mm: float
    required_depth_mm: float
    margin_mm: float
    axis: PierceAxis
    reason: str = ""


# Socket types that require analytical embedment validation
PIERCE_SOCKET_TYPES = frozenset({
    "through_axis",
    "through_x", "through_y", "through_z",
    "radial_bridge",
    "strut", "strut_diagonal",
})


def is_pierce_socket_type(socket_type: str) -> bool:
    """Check if a socket type requires analytical embedment validation."""
    if not socket_type:
        return False
    normalized = socket_type.lower().replace("-", "_").replace(" ", "_")
    # Check exact match or prefix match for variants
    if normalized in PIERCE_SOCKET_TYPES:
        return True
    # Handle variants like "through_axis_x" or "strut_to_rim"
    for prefix in ("through_", "radial_bridge", "strut"):
        if normalized.startswith(prefix):
            return True
    return False


def compute_embedment_depth(
    parent_half_extent_mm: float,
    child_offset_along_axis_mm: float,
) -> float:
    """Compute how deeply a child is embedded into a parent along the pierce axis.
    
    For a child centered at offset O along the pierce axis, passing through a parent
    whose solid extent runs from -H to +H (half_extent = H):
    
    - If child is at center (offset=0), embedment = H (fully centered)
    - If child is at edge (offset=H), embedment = 0 (just touching edge)
    - If child is outside (offset>H), embedment < 0 (not embedded)
    
    Args:
        parent_half_extent_mm: Half the parent's dimension along pierce axis (in mm)
        child_offset_along_axis_mm: Child's centerline offset from parent center (in mm)
    
    Returns:
        Embedment depth in mm (positive = inside, negative = outside)
    """
    return parent_half_extent_mm - abs(child_offset_along_axis_mm)


def compute_required_embedment(
    child_radius_mm: float,
    margin_mm: float = 2.0,
) -> float:
    """Compute minimum required embedment depth for a pierce connection.
    
    The child must be embedded at least its own radius plus a margin to ensure
    solid contact, not just edge-grazing.
    
    Args:
        child_radius_mm: Radius of the piercing child (cylinder radius)
        margin_mm: Additional safety margin (default 2mm)
    
    Returns:
        Minimum required embedment depth in mm
    """
    return child_radius_mm + margin_mm


def validate_pierce_embedment(
    parent_half_extent_mm: float,
    child_offset_along_axis_mm: float,
    child_radius_mm: float,
    axis: PierceAxis,
    margin_mm: float = 2.0,
) -> EmbedmentResult:
    """Validate that a pierce-type connection has sufficient embedment depth.
    
    This is the primary validation function called by both Stage 4 and the
    verification gate.
    
    Args:
        parent_half_extent_mm: Half the parent's dimension along pierce axis
        child_offset_along_axis_mm: Child's centerline offset from parent center
        child_radius_mm: Radius of the piercing child cylinder
        axis: Which axis the child pierces through
        margin_mm: Safety margin beyond child radius (default 2mm)
    
    Returns:
        EmbedmentResult with validation status and diagnostic info
    """
    actual_depth = compute_embedment_depth(parent_half_extent_mm, child_offset_along_axis_mm)
    required_depth = compute_required_embedment(child_radius_mm, margin_mm)
    
    valid = actual_depth >= required_depth
    
    if valid:
        reason = f"Embedment {actual_depth:.1f}mm >= required {required_depth:.1f}mm"
    else:
        shortfall = required_depth - actual_depth
        reason = (
            f"Insufficient embedment: {actual_depth:.1f}mm < required {required_depth:.1f}mm "
            f"(shortfall {shortfall:.1f}mm). Child radius={child_radius_mm:.1f}mm, "
            f"margin={margin_mm:.1f}mm, parent half-extent={parent_half_extent_mm:.1f}mm"
        )
    
    return EmbedmentResult(
        valid=valid,
        embedment_depth_mm=actual_depth,
        required_depth_mm=required_depth,
        margin_mm=margin_mm,
        axis=axis,
        reason=reason,
    )


def extract_pierce_axis_from_socket(socket_type: str) -> Optional[PierceAxis]:
    """Infer the pierce axis from socket type name.
    
    Returns None if axis cannot be determined (caller should use through_axis hint
    from the attachment spec or default based on geometry).
    """
    normalized = socket_type.lower()
    if "_x" in normalized or "lateral" in normalized:
        return PierceAxis.X
    if "_y" in normalized or "forward" in normalized:
        return PierceAxis.Y
    if "_z" in normalized or "vertical" in normalized:
        return PierceAxis.Z
    return None


def validate_pierce_from_specs(
    parent_dimensions_mm: Tuple[float, float, float],
    child_radius_mm: float,
    child_offset_mm: Tuple[float, float, float],
    socket_type: str,
    through_axis_hint: Optional[str] = None,
    margin_mm: float = 2.0,
) -> EmbedmentResult:
    """High-level validation from part specs - convenience wrapper.
    
    Determines pierce axis from socket_type or hint, extracts relevant dimensions,
    and runs validation.
    
    Args:
        parent_dimensions_mm: Parent (width, depth, height) or (dx, dy, dz) in mm
        child_radius_mm: Radius of piercing cylinder
        child_offset_mm: Child offset (x, y, z) from parent center in mm
        socket_type: Socket type string (e.g., "through_axis", "strut")
        through_axis_hint: Optional explicit axis hint ("x", "y", "z")
        margin_mm: Safety margin
    
    Returns:
        EmbedmentResult with validation status
    """
    # Determine pierce axis
    axis = None
    if through_axis_hint:
        axis = PierceAxis(through_axis_hint.lower())
    else:
        axis = extract_pierce_axis_from_socket(socket_type)
    
    if axis is None:
        # Default: assume Z for vertical struts, X for horizontal through
        if "strut" in socket_type.lower():
            axis = PierceAxis.Z
        else:
            axis = PierceAxis.X
    
    # Extract relevant dimension and offset component
    if axis == PierceAxis.X:
        parent_half = parent_dimensions_mm[0] / 2.0
        child_offset = child_offset_mm[0]
    elif axis == PierceAxis.Y:
        parent_half = parent_dimensions_mm[1] / 2.0
        child_offset = child_offset_mm[1]
    else:  # Z
        parent_half = parent_dimensions_mm[2] / 2.0
        child_offset = child_offset_mm[2]
    
    return validate_pierce_embedment(
        parent_half_extent_mm=parent_half,
        child_offset_along_axis_mm=child_offset,
        child_radius_mm=child_radius_mm,
        axis=axis,
        margin_mm=margin_mm,
    )
