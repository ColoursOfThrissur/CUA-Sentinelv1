"""Decomposition Schema Validation — Fail-loud contract enforcement.

This module ensures LLM decomposition output matches the expected schema.
Silent fallbacks are FORBIDDEN — any schema mismatch raises DecompositionSchemaError.

Field name normalization handles common LLM drift (type→primitive, name→label, etc.)
but logs warnings so we can fix the prompt if drift becomes systematic.
"""

from typing import Dict, Any, List, Optional, Tuple
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class DecompositionSchemaError(Exception):
    """Raised when LLM decomposition output doesn't match expected schema."""
    pass


class SocketType(str, Enum):
    """Semantic socket types for deterministic position resolution.
    
    The LLM outputs these semantic types; the resolver computes numeric offsets.
    This moves arithmetic OUT of the LLM and INTO tested code.
    """
    # Axial attachments (along parent's primary axis)
    TOP_CENTER = "top_center"           # Child sits on top of parent
    BOTTOM_CENTER = "bottom_center"     # Child hangs below parent
    
    # Surface mounts (on parent's faces)
    FRONT_FACE = "front_face"           # -Y face of parent
    BACK_FACE = "back_face"             # +Y face of parent
    LEFT_FACE = "left_face"             # -X face of parent
    RIGHT_FACE = "right_face"           # +X face of parent
    SURFACE_MOUNT = "surface_mount"     # Generic surface (needs direction hint)
    
    # Through/intersection attachments
    THROUGH_AXIS = "through_axis"       # Child passes THROUGH parent (horizontal axis)
    INTERSECT = "intersect"             # Child intersects parent volume
    
    # End mounts (at ends of elongated parent)
    LEFT_END = "left_end"               # At -X end of horizontal parent
    RIGHT_END = "right_end"             # At +X end of horizontal parent
    TOP_END = "top_end"                 # At +Z end of vertical parent
    BOTTOM_END = "bottom_end"           # At -Z end of vertical parent
    
    # Radial/offset attachments
    RADIAL = "radial"                   # At radius from parent center
    STRUT = "strut"                     # Diagonal structural connector
    
    # Generic fallback
    JOINT = "joint"                     # Unspecified attachment


# Field name aliases: LLM drift → canonical name
FIELD_ALIASES = {
    # Shape field
    "type": "primitive",
    "prim": "primitive",
    "shape_type": "primitive",
    
    # Part label
    "name": "label",
    "part_name": "label",
    "id": "label",
    
    # Parent reference
    "parent": "parent_label",
    "parent_name": "parent_label",
    "parent_id": "parent_label",
    
    # Socket
    "socket": "socket_name",
    "socket_type": "socket_name",
    "attachment_point": "socket_name",
    
    # Offset
    "offset": "local_offset",
    "position": "local_offset",
    
    # Rotation
    "rotation": "local_rotation_euler",
    "rotation_euler": "local_rotation_euler",
    "euler": "local_rotation_euler",
}


def normalize_field_names(data: Dict[str, Any], context: str = "") -> Dict[str, Any]:
    """Normalize field names using aliases, logging any drift detected.
    
    Args:
        data: Raw dict from LLM
        context: Description for logging (e.g., "root" or "part[arm_axis]")
    
    Returns:
        Dict with canonical field names
    """
    normalized = {}
    drift_detected = []
    
    for key, value in data.items():
        canonical = FIELD_ALIASES.get(key, key)
        if canonical != key:
            drift_detected.append(f"{key}→{canonical}")
        
        # Recursively normalize nested dicts (e.g., shape, attachment)
        if isinstance(value, dict):
            value = normalize_field_names(value, f"{context}.{canonical}")
        
        normalized[canonical] = value
    
    if drift_detected:
        logger.warning(
            f"[DecompositionSchema] Field name drift in {context}: {', '.join(drift_detected)}. "
            f"Consider updating DECOMPOSITION_SYSTEM_PROMPT to prevent this."
        )
    
    return normalized


def validate_shape(shape: Dict[str, Any], part_label: str) -> Dict[str, Any]:
    """Validate and normalize a shape dict. Raises on invalid schema.
    
    Args:
        shape: Shape dict from LLM (already field-normalized)
        part_label: Part name for error messages
    
    Returns:
        Validated shape dict with 'primitive' field guaranteed
    
    Raises:
        DecompositionSchemaError: If shape is invalid or missing required fields
    """
    if not shape:
        raise DecompositionSchemaError(
            f"Part '{part_label}' has no shape definition"
        )
    
    # Ensure primitive field exists
    primitive = shape.get("primitive")
    if not primitive:
        raise DecompositionSchemaError(
            f"Part '{part_label}' shape missing 'primitive' field. "
            f"Got keys: {list(shape.keys())}. "
            f"Expected one of: box, cylinder, sphere, cone, hemisphere"
        )
    
    # Validate primitive type
    valid_primitives = {"box", "cylinder", "sphere", "cone", "hemisphere", "torus"}
    if primitive not in valid_primitives:
        raise DecompositionSchemaError(
            f"Part '{part_label}' has invalid primitive '{primitive}'. "
            f"Must be one of: {valid_primitives}"
        )
    
    # Validate required dimensions per primitive
    if primitive == "box":
        if "size" not in shape:
            raise DecompositionSchemaError(
                f"Part '{part_label}' (box) missing 'size' field"
            )
        size = shape["size"]
        if not isinstance(size, list) or len(size) != 3:
            raise DecompositionSchemaError(
                f"Part '{part_label}' (box) 'size' must be [x, y, z] list, got: {size}"
            )
    
    elif primitive == "cylinder":
        if "radius" not in shape:
            raise DecompositionSchemaError(
                f"Part '{part_label}' (cylinder) missing 'radius' field"
            )
        if "depth" not in shape:
            raise DecompositionSchemaError(
                f"Part '{part_label}' (cylinder) missing 'depth' field"
            )
    
    elif primitive == "sphere" or primitive == "hemisphere":
        if "radius" not in shape:
            raise DecompositionSchemaError(
                f"Part '{part_label}' ({primitive}) missing 'radius' field"
            )
    
    elif primitive == "cone":
        if "radius1" not in shape and "radius" not in shape:
            raise DecompositionSchemaError(
                f"Part '{part_label}' (cone) missing 'radius1' or 'radius' field"
            )
        if "depth" not in shape:
            raise DecompositionSchemaError(
                f"Part '{part_label}' (cone) missing 'depth' field"
            )
        # Normalize radius → radius1 for cones
        if "radius" in shape and "radius1" not in shape:
            shape["radius1"] = shape.pop("radius")
    
    return shape


def validate_part(part: Dict[str, Any], available_parents: set, part_index: int) -> Dict[str, Any]:
    """Validate a non-root part. Raises on invalid schema.
    
    Args:
        part: Part dict from LLM (already field-normalized)
        available_parents: Set of valid parent labels
        part_index: Index for error messages
    
    Returns:
        Validated part dict
    
    Raises:
        DecompositionSchemaError: If part is invalid
    """
    # Label is required
    label = part.get("label")
    if not label:
        raise DecompositionSchemaError(
            f"Part[{part_index}] missing 'label' field. Got keys: {list(part.keys())}"
        )
    
    # Parent label is required and must reference existing part
    parent_label = part.get("parent_label")
    if not parent_label:
        raise DecompositionSchemaError(
            f"Part '{label}' missing 'parent_label' field"
        )
    if parent_label not in available_parents:
        raise DecompositionSchemaError(
            f"Part '{label}' references unknown parent '{parent_label}'. "
            f"Available parents: {available_parents}"
        )
    
    # Shape is required
    shape = part.get("shape")
    if not shape:
        raise DecompositionSchemaError(
            f"Part '{label}' missing 'shape' field"
        )
    part["shape"] = validate_shape(normalize_field_names(shape, f"part[{label}].shape"), label)
    
    # Socket name (optional but recommended)
    if "socket_name" not in part:
        logger.warning(f"Part '{label}' missing 'socket_name', defaulting to 'joint'")
        part["socket_name"] = "joint"
    
    # Local offset (optional, defaults to [0,0,0])
    if "local_offset" not in part:
        logger.warning(f"Part '{label}' missing 'local_offset', defaulting to [0,0,0]")
        part["local_offset"] = [0, 0, 0]
    else:
        offset = part["local_offset"]
        if not isinstance(offset, list) or len(offset) != 3:
            raise DecompositionSchemaError(
                f"Part '{label}' 'local_offset' must be [x, y, z] list, got: {offset}"
            )
    
    # Local rotation (optional, defaults to [0,0,0])
    if "local_rotation_euler" not in part:
        part["local_rotation_euler"] = [0, 0, 0]
    else:
        rot = part["local_rotation_euler"]
        if not isinstance(rot, list) or len(rot) != 3:
            raise DecompositionSchemaError(
                f"Part '{label}' 'local_rotation_euler' must be [rx, ry, rz] list, got: {rot}"
            )
    
    # Join mode (optional, defaults to parent_only)
    if "join_mode" not in part:
        part["join_mode"] = "parent_only"
    
    return part


def validate_root(root: Dict[str, Any]) -> Dict[str, Any]:
    """Validate root node. Raises on invalid schema.
    
    Args:
        root: Root dict from LLM (already field-normalized)
    
    Returns:
        Validated root dict
    
    Raises:
        DecompositionSchemaError: If root is invalid
    """
    # Label (optional for root, defaults to "base")
    if "label" not in root:
        logger.warning("Root missing 'label', defaulting to 'base'")
        root["label"] = "base"
    
    label = root["label"]
    
    # Shape is required
    shape = root.get("shape")
    if not shape:
        raise DecompositionSchemaError(
            f"Root '{label}' missing 'shape' field"
        )
    root["shape"] = validate_shape(normalize_field_names(shape, f"root.shape"), label)
    
    # Attachment (optional)
    if "attachment" not in root:
        root["attachment"] = {"local_offset": [0, 0, 0]}
    else:
        att = root["attachment"]
        if "local_offset" not in att:
            att["local_offset"] = [0, 0, 0]
    
    return root


def validate_decomposition(data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate entire decomposition output. Raises on any schema violation.
    
    This is the main entry point. Call this before _build_graph_from_decomp.
    
    Args:
        data: Raw decomposition dict from LLM
    
    Returns:
        Validated and normalized decomposition dict
    
    Raises:
        DecompositionSchemaError: If any part of the schema is invalid
    """
    if not isinstance(data, dict):
        raise DecompositionSchemaError(
            f"Decomposition must be a dict, got: {type(data).__name__}"
        )
    
    # Root is required
    if "root" not in data:
        raise DecompositionSchemaError(
            "Decomposition missing 'root' field"
        )
    
    # Normalize and validate root
    data["root"] = validate_root(normalize_field_names(data["root"], "root"))
    root_label = data["root"]["label"]
    
    # Track available parent labels
    available_parents = {root_label}
    
    # Validate parts (if any)
    parts = data.get("parts", [])
    if not isinstance(parts, list):
        raise DecompositionSchemaError(
            f"'parts' must be a list, got: {type(parts).__name__}"
        )
    
    validated_parts = []
    for i, part in enumerate(parts):
        if not isinstance(part, dict):
            raise DecompositionSchemaError(
                f"Part[{i}] must be a dict, got: {type(part).__name__}"
            )
        
        # Normalize field names first
        part = normalize_field_names(part, f"part[{i}]")
        
        # Validate
        part = validate_part(part, available_parents, i)
        
        # Add this part's label to available parents for subsequent parts
        available_parents.add(part["label"])
        validated_parts.append(part)
    
    data["parts"] = validated_parts
    
    # rests_on_surface (optional, defaults to True)
    if "rests_on_surface" not in data:
        data["rests_on_surface"] = True
    
    return data


def infer_socket_type(socket_name: str, parent_label: str = "") -> SocketType:
    """Infer semantic socket type from socket_name string.
    
    Args:
        socket_name: Raw socket name from LLM
        parent_label: Optional parent part label for context
    
    Returns:
        SocketType enum value
    """
    s = socket_name.lower()
    p = parent_label.lower()
    
    # Exact matches first
    for st in SocketType:
        if st.value == s:
            return st
    
    # Check if parent is a horizontal axis/arm/axle - then left/right mean END not FACE
    parent_is_axis = any(kw in p for kw in ("axis", "arm", "axle", "bar", "rod", "beam", "crossbar"))
    
    # Keyword matching - most specific first
    if "strut" in s or "brace" in s or "support" in s:
        return SocketType.STRUT
    if "through" in s or "intersect" in s or "pass" in s or "horizontal" in s:
        return SocketType.THROUGH_AXIS
    if "left_end" in s or "left end" in s or ("left" in s and "end" in s):
        return SocketType.LEFT_END
    if "right_end" in s or "right end" in s or ("right" in s and "end" in s):
        return SocketType.RIGHT_END
    if "top_end" in s or "top end" in s:
        return SocketType.TOP_END
    if "bottom_end" in s or "bottom end" in s:
        return SocketType.BOTTOM_END
    if "top" in s and "center" in s:
        return SocketType.TOP_CENTER
    if "top" in s:
        return SocketType.TOP_CENTER
    if "bottom" in s and "center" in s:
        return SocketType.BOTTOM_CENTER
    if "bottom" in s:
        return SocketType.BOTTOM_CENTER
    if "front" in s:
        return SocketType.FRONT_FACE
    if "back" in s:
        return SocketType.BACK_FACE
    # If parent is an axis, left/right mean END
    if "left" in s:
        return SocketType.LEFT_END if parent_is_axis else SocketType.LEFT_FACE
    if "right" in s:
        return SocketType.RIGHT_END if parent_is_axis else SocketType.RIGHT_FACE
    if "surface" in s or "mount" in s:
        return SocketType.SURFACE_MOUNT
    if "radial" in s or "spoke" in s:
        return SocketType.RADIAL
    
    return SocketType.JOINT
