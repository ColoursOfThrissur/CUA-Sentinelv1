"""Stage 4 — Deterministic Resolution (PURE CODE, no LLM).

Input: Stage 2 dimensions + Stage 3 semantics.
Output: Complete AssemblyGraph with all transforms computed.

This is the ONLY place numeric transforms are produced.
Every offset and rotation is computed from real geometry, never from LLM raw numbers.

The key invariant enforced here:
    Every axis of offset[0..2] and rotation[0..2] must be explicitly assigned.
    No axis may be left unassigned or passed through from LLM output.
"""

import math
import logging
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from core.assembly_spec import (
    AssemblyGraph,
    AssemblyNode,
    AttachmentSpec,
    JoinMode,
    PartParadigm,
    InteractionType,
)
from core.embedment_validation import (
    is_pierce_socket_type,
    compute_required_embedment,
    compute_embedment_depth,
    validate_pierce_embedment,
    PierceAxis,
)

logger = logging.getLogger(__name__)


@dataclass
class WorldPose:
    """World-space position and rotation for a node.
    
    Used to compute actual world positions for connectors (STRUT, RADIAL_BRIDGE).
    """
    position: Tuple[float, float, float]  # World XYZ
    rotation_rad: Tuple[float, float, float]  # Euler XYZ in radians
    
    @classmethod
    def identity(cls) -> "WorldPose":
        return cls((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
    
    def transform_point(self, local_point: Tuple[float, float, float]) -> Tuple[float, float, float]:
        """Transform a point from local space to world space."""
        # Apply rotation then translation
        rotated = _rotate_point(local_point, self.rotation_rad)
        return (
            rotated[0] + self.position[0],
            rotated[1] + self.position[1],
            rotated[2] + self.position[2],
        )


def _rotate_point(p: Tuple[float, float, float], euler_rad: Tuple[float, float, float]) -> Tuple[float, float, float]:
    """Rotate point by Euler XYZ angles (in radians)."""
    x, y, z = p
    rx, ry, rz = euler_rad
    
    # Rotation around X
    cos_rx, sin_rx = math.cos(rx), math.sin(rx)
    y1 = y * cos_rx - z * sin_rx
    z1 = y * sin_rx + z * cos_rx
    y, z = y1, z1
    
    # Rotation around Y
    cos_ry, sin_ry = math.cos(ry), math.sin(ry)
    x1 = x * cos_ry + z * sin_ry
    z1 = -x * sin_ry + z * cos_ry
    x, z = x1, z1
    
    # Rotation around Z
    cos_rz, sin_rz = math.cos(rz), math.sin(rz)
    x1 = x * cos_rz - y * sin_rz
    y1 = x * sin_rz + y * cos_rz
    x, y = x1, y1
    
    return (x, y, z)


# Default margin for embedment validation (in mm, matching embedment_validation.py)
DEFAULT_EMBEDMENT_MARGIN_MM = 2.0


@dataclass
class ShapeBounds:
    """Origin-relative bounds for a shape.
    
    All values are distances from the shape's local origin.
    Positive values extend in the positive axis direction.
    Negative values extend in the negative axis direction.
    
    For a centered box of size [1, 1, 2]:
        x_min=-0.5, x_max=0.5, y_min=-0.5, y_max=0.5, z_min=-1.0, z_max=1.0
    
    For a hemisphere with flat face at origin, dome pointing +Z:
        x_min=-r, x_max=r, y_min=-r, y_max=r, z_min=0, z_max=r
    """
    x_min: float
    x_max: float
    y_min: float
    y_max: float
    z_min: float
    z_max: float
    
    @property
    def half_x(self) -> float:
        """Half-extent along X (for symmetric shapes)."""
        return (self.x_max - self.x_min) / 2.0
    
    @property
    def half_y(self) -> float:
        """Half-extent along Y (for symmetric shapes)."""
        return (self.y_max - self.y_min) / 2.0
    
    @property
    def half_z(self) -> float:
        """Half-extent along Z (for symmetric shapes)."""
        return (self.z_max - self.z_min) / 2.0
    
    @property
    def center_offset(self) -> Tuple[float, float, float]:
        """Offset from origin to bounding box center."""
        return (
            (self.x_min + self.x_max) / 2.0,
            (self.y_min + self.y_max) / 2.0,
            (self.z_min + self.z_max) / 2.0,
        )
    
    @classmethod
    def from_spec(cls, spec: dict) -> "ShapeBounds":
        """Create bounds from a sub_spec dict.
        
        CRITICAL: This returns LOCAL bounds before any rotation.
        After rotation, these bounds are no longer axis-aligned!
        """
        prim = spec.get("primitive", "box")
        
        if prim == "box":
            size = spec.get("size", [1, 1, 1])
            hx, hy, hz = size[0]/2, size[1]/2, size[2]/2
            return cls(-hx, hx, -hy, hy, -hz, hz)
        
        elif prim == "cylinder":
            r = float(spec.get("radius", 0.5))
            d = float(spec.get("depth", 1.0))
            hd = d / 2.0
            # Cylinder: origin at center, axis along Z
            return cls(-r, r, -r, r, -hd, hd)
        
        elif prim == "sphere":
            r = float(spec.get("radius", 0.5))
            return cls(-r, r, -r, r, -r, r)
        
        elif prim == "hemisphere":
            r = float(spec.get("radius", 0.5))
            # Hemisphere: flat face at Z=0, dome extends to +Z
            # (This is how we create it: sphere + boolean cut below Z=0)
            return cls(-r, r, -r, r, 0.0, r)
        
        elif prim == "cone":
            r = float(spec.get("radius1", spec.get("radius", 0.5)))
            d = float(spec.get("depth", 1.0))
            hd = d / 2.0
            # Cone: Blender creates cones with origin at CENTER of bounding box
            # Base (radius1) is at -Z, tip (radius2=0) is at +Z
            # So z_min = -depth/2, z_max = +depth/2
            return cls(-r, r, -r, r, -hd, hd)
        
        else:
            # Unknown primitive, assume unit cube
            return cls(-0.5, 0.5, -0.5, 0.5, -0.5, 0.5)


@dataclass
class ResolvedTransform:
    """Fully resolved transform for a part."""
    offset: Tuple[float, float, float]      # In parent's local frame
    rotation_rad: Tuple[float, float, float]  # Euler XYZ in radians
    computed_depth: Optional[float] = None  # For connectors: actual span distance
    
    def __post_init__(self):
        """Validate that all axes are assigned (not None)."""
        for i, axis in enumerate(["X", "Y", "Z"]):
            if self.offset[i] is None:
                raise ValueError(f"Offset {axis} is None - all axes must be explicitly assigned")
            if self.rotation_rad[i] is None:
                raise ValueError(f"Rotation {axis} is None - all axes must be explicitly assigned")


class Stage4Resolver:
    """Stage 4: Compute all transforms deterministically from geometry."""
    
    @classmethod
    def run(
        cls,
        stage0_output: dict,
        stage2_output: dict,
        stage3_output: dict,
        task_id: str,
    ) -> AssemblyGraph:
        """Run Stage 4 to compute all transforms.
        
        Args:
            stage0_output: Output from Stage 0 (understanding)
            stage2_output: Output from Stage 2 (dimensions)
            stage3_output: Output from Stage 3 (semantics)
            task_id: Task ID for the graph
            
        Returns:
            Complete AssemblyGraph ready for Blender
        """
        # Build lookup tables
        dims_by_label = {p["label"]: p for p in stage2_output.get("parts", [])}
        semantics_by_label = {p["label"]: p for p in stage3_output.get("parts", [])}
        
        # Find root
        root_part = None
        for p in stage2_output.get("parts", []):
            if p["socket_type"] == "ROOT":
                root_part = p
                break
        
        if not root_part:
            raise Stage4Error("No ROOT part found")
        
        rests_on_surface = stage0_output.get("rests_on_surface", True)
        
        # Build root node
        root_dims = root_part["dimensions"]
        root_material = root_part.get("material")
        root_sub_spec = cls._build_sub_spec(root_part["primitive_type"], root_dims, root_material)
        
        # Root Z offset: if rests_on_surface, bottom face at Z=0
        if rests_on_surface:
            root_z = cls._get_half_z(root_sub_spec)
        else:
            root_z = 0.0
        
        root_node = AssemblyNode(
            node_id=f"root_{root_part['label']}_{task_id}",
            label=root_part["label"],
            paradigm=PartParadigm.PRIMITIVE,
            sub_spec=root_sub_spec,
            attachment=AttachmentSpec(
                parent_node_id=None,
                socket_name="root",
                socket_type="ROOT",
                local_offset=(0.0, 0.0, round(root_z, 6)),
                local_rotation_euler=(0.0, 0.0, 0.0),
                join_mode=JoinMode.PARENT_ONLY,
            ),
            children=[],
        )
        
        nodes_by_label: Dict[str, AssemblyNode] = {root_part["label"]: root_node}
        
        # Track parent relationships for cycle detection
        parent_chain: Dict[str, str] = {}  # child_label -> parent_label
        
        # Process children in order (parents before children guaranteed by Stage 1)
        for part in stage2_output.get("parts", []):
            if part["socket_type"] == "ROOT":
                continue
            
            label = part["label"]
            parent_label = part["parent_label"]
            socket_type = part["socket_type"]
            
            parent_node = nodes_by_label.get(parent_label)
            if not parent_node:
                raise Stage4Error(f"Parent '{parent_label}' not found for part '{label}'")
            
            # CYCLE DETECTION: Check if this would create a parent cycle
            if cls._would_create_cycle(label, parent_label, parent_chain):
                raise Stage4Error(
                    f"Parent cycle detected: '{label}' -> '{parent_label}' would create a loop"
                )
            parent_chain[label] = parent_label
            
            # Get dimensions and semantics
            dims = part["dimensions"]
            material = part.get("material")
            
            # Get semantics with proper defaults for socket types that need them
            semantics = semantics_by_label.get(label, {})
            if not semantics:
                semantics = {"label": label, "socket_type": socket_type}
            
            # Inject parent_label for world pose computation
            semantics = dict(semantics)
            semantics["_parent_label"] = parent_label
            
            # Apply default semantics for socket types that require them
            semantics = cls._apply_default_semantics(semantics, socket_type, label, nodes_by_label)
            
            # Build sub_spec
            child_sub_spec = cls._build_sub_spec(part["primitive_type"], dims, material)
            
            # Resolve transform based on socket type
            transform = cls._resolve_transform(
                socket_type=socket_type,
                parent_spec=parent_node.sub_spec,
                child_spec=child_sub_spec,
                semantics=semantics,
                dims_by_label=dims_by_label,
                nodes_by_label=nodes_by_label,
            )
            
            # For connectors (STRUT, RADIAL_BRIDGE), override depth with computed length
            if transform.computed_depth is not None and transform.computed_depth > 0:
                prim = child_sub_spec.get("primitive")
                if prim in ("cylinder", "cone"):
                    child_sub_spec["depth"] = transform.computed_depth
                    logger.info(f"Part '{label}': auto-sized depth to {transform.computed_depth:.4f}m")
            
            # Determine interaction type for verification
            interaction_type = cls._get_interaction_type(socket_type)
            
            # Determine through_axis for pierce types
            through_axis = None
            if is_pierce_socket_type(socket_type):
                pd = semantics.get("pierce_direction", "left_right")
                through_axis = {"left_right": "x", "front_back": "y", "up_down": "z"}.get(pd, "x")
            
            # Determine join_mode based on socket type
            # BOOLEAN_CUT parts are subtracted from parent
            if socket_type == "BOOLEAN_CUT":
                join_mode = JoinMode.BOOLEAN_DIFFERENCE
            else:
                join_mode = JoinMode.PARENT_ONLY
            
            child_node = AssemblyNode(
                node_id=f"node_{label}_{task_id}",
                label=label,
                paradigm=PartParadigm.PRIMITIVE,
                sub_spec=child_sub_spec,
                attachment=AttachmentSpec(
                    parent_node_id=parent_node.node_id,
                    socket_name=f"{parent_label}.{socket_type.lower()}",
                    socket_type=socket_type,
                    through_axis=through_axis,
                    local_offset=transform.offset,
                    local_rotation_euler=transform.rotation_rad,
                    join_mode=join_mode,
                    interaction_type=interaction_type,
                ),
                children=[],
            )
            
            parent_node.children.append(child_node)
            nodes_by_label[label] = child_node
        
        return AssemblyGraph(
            schema_version="2.0",
            task_id=task_id,
            root=root_node,
            description=stage0_output.get("category", "object"),
            status="PENDING",
            rests_on_surface=rests_on_surface,
        )
    
    @classmethod
    def _resolve_transform(
        cls,
        socket_type: str,
        parent_spec: dict,
        child_spec: dict,
        semantics: dict,
        dims_by_label: dict,
        nodes_by_label: dict,
    ) -> ResolvedTransform:
        """Resolve offset and rotation for a socket type.
        
        CRITICAL: Every branch must explicitly assign all 6 values (3 offset + 3 rotation).
        
        COORDINATE SYSTEM:
        - Blender uses right-handed: +X=right, +Y=forward, +Z=up
        - Cylinders are created with axis along Z (vertical by default)
        - To make a cylinder horizontal along X: rotate 90° around Y
        - To make a cylinder horizontal along Y: rotate 90° around X
        """
        # Get parent geometry (in parent's LOCAL frame, before any rotation)
        p_half_x = cls._get_half_x(parent_spec)
        p_half_y = cls._get_half_y(parent_spec)
        p_half_z = cls._get_half_z(parent_spec)
        p_radius = cls._get_radius(parent_spec)
        
        # Get child geometry (in child's LOCAL frame, before any rotation)
        c_half_x = cls._get_half_x(child_spec)
        c_half_y = cls._get_half_y(child_spec)
        c_half_z = cls._get_half_z(child_spec)
        c_radius = cls._get_radius(child_spec)
        
        # For cylinders, half_z is half the depth (length along axis)
        # After rotation, this becomes the half-extent along the new axis
        c_half_length = cls._get_half_length(child_spec)  # = depth/2 for cylinders
        p_half_length = cls._get_half_length(parent_spec)
        
        # Default: all zeros (will be overwritten per socket type)
        ox, oy, oz = 0.0, 0.0, 0.0
        rx, ry, rz = 0.0, 0.0, 0.0
        
        # ===== SOCKET TYPE DISPATCH =====
        
        if socket_type == "TOP_CENTER":
            # Child sits on top of parent, centered
            # Child's bottom touches parent's top
            ox, oy = 0.0, 0.0
            oz = p_half_z + c_half_z
            rx, ry, rz = 0.0, 0.0, 0.0
        
        elif socket_type == "BOTTOM_CENTER":
            # Child hangs below parent
            ox, oy = 0.0, 0.0
            oz = -(p_half_z + c_half_z)
            rx, ry, rz = 0.0, 0.0, 0.0
        
        elif socket_type == "THROUGH_AXIS":
            # Child (typically cylinder) passes through parent horizontally
            # The child is ROTATED to lie along the pierce axis
            pierce_dir = semantics.get("pierce_direction", "left_right")
            height_hint = semantics.get("height_hint", "center")
            
            # Child will be rotated, so after rotation:
            # - Its length (depth) will be along the pierce axis
            # - Its radius will be perpendicular
            
            if pierce_dir == "left_right":
                # Rotate child to lie along X axis
                # Rotation: 90° around Y makes Z->X
                rx, ry, rz = 0.0, math.radians(90), 0.0
                
                # After rotation, child's half_length is along X, radius along Y and Z
                # Position: centered in X, centered in Y, height_hint in Z
                ox = 0.0  # Centered through parent
                oy = 0.0
                oz = cls._compute_height_from_hint(height_hint, p_half_z, c_radius)
                
                # Validate: child radius must fit within parent's Z extent at this height
                cls._validate_pierce_embedment(p_half_z, oz, c_radius, "z")
                
            elif pierce_dir == "front_back":
                # Rotate child to lie along Y axis
                # Rotation: 90° around X makes Z->Y
                rx, ry, rz = math.radians(90), 0.0, 0.0
                
                ox = 0.0
                oy = 0.0
                oz = cls._compute_height_from_hint(height_hint, p_half_z, c_radius)
                
                cls._validate_pierce_embedment(p_half_z, oz, c_radius, "z")
                
            else:  # up_down - child stays vertical, passes through vertically
                rx, ry, rz = 0.0, 0.0, 0.0
                ox, oy = 0.0, 0.0
                oz = 0.0  # Centered vertically
        
        elif socket_type == "LEFT_END":
            # Child at "left" end of parent's length axis
            # For cylinders/cones, length is along LOCAL Z axis
            # "Left" = negative end of length axis (local -Z)
            # The parent's rotation will transform this to world space
            ox, oy = 0.0, 0.0
            oz = -(p_half_length + c_half_z)  # Offset along parent's length axis
            rx, ry, rz = 0.0, 0.0, 0.0  # Child aligns with parent
        
        elif socket_type == "RIGHT_END":
            # Child at "right" end of parent's length axis (local +Z)
            ox, oy = 0.0, 0.0
            oz = p_half_length + c_half_z
            rx, ry, rz = 0.0, 0.0, 0.0
        
        elif socket_type == "TOP_END":
            # Child at top end of VERTICAL parent
            ox, oy = 0.0, 0.0
            oz = p_half_z + c_half_z
            rx, ry, rz = 0.0, 0.0, 0.0
        
        elif socket_type == "BOTTOM_END":
            # Child at bottom end of vertical parent
            ox, oy = 0.0, 0.0
            oz = -(p_half_z + c_half_z)
            rx, ry, rz = 0.0, 0.0, 0.0
        
        elif socket_type == "FRONT_FACE":
            # Child on front face of parent (-Y for boxes, +Z end for cylinders)
            height_hint = semantics.get("height_hint", "center")
            parent_prim = parent_spec.get("primitive", "box")
            
            if parent_prim == "cylinder":
                # For cylinder: "front" = positive end of length axis
                # Cylinder length is along Z in local space
                # Place child at +Z end, touching
                ox = 0.0
                oy = 0.0
                oz = p_half_z + c_half_z
            else:
                # Box: front is -Y face
                oz = cls._compute_face_height(height_hint, p_half_z, c_half_z)
                ox = 0.0
                oy = -(p_half_y + c_half_y)
            rx, ry, rz = 0.0, 0.0, 0.0
        
        elif socket_type == "BACK_FACE":
            # Child on back face of parent (+Y for boxes, -Z end for cylinders)
            height_hint = semantics.get("height_hint", "center")
            parent_prim = parent_spec.get("primitive", "box")
            
            if parent_prim == "cylinder":
                # For cylinder: "back" = negative end of length axis
                ox = 0.0
                oy = 0.0
                oz = -(p_half_z + c_half_z)
            else:
                # Box: back is +Y face
                oz = cls._compute_face_height(height_hint, p_half_z, c_half_z)
                ox = 0.0
                oy = p_half_y + c_half_y
            rx, ry, rz = 0.0, 0.0, 0.0
        
        elif socket_type == "LEFT_FACE":
            # Child on -X face of parent
            height_hint = semantics.get("height_hint", "center")
            oz = cls._compute_face_height(height_hint, p_half_z, c_half_z)
            ox = -(p_half_x + c_half_x)
            oy = 0.0
            rx, ry, rz = 0.0, 0.0, 0.0
        
        elif socket_type == "RIGHT_FACE":
            # Child on +X face of parent
            height_hint = semantics.get("height_hint", "center")
            oz = cls._compute_face_height(height_hint, p_half_z, c_half_z)
            ox = p_half_x + c_half_x
            oy = 0.0
            rx, ry, rz = 0.0, 0.0, 0.0
        
        elif socket_type == "TOP_FACE":
            # Child on top face (same as TOP_CENTER but may have lateral offset)
            face_pos = semantics.get("face_position", "center")
            ox, oy = cls._compute_face_lateral(face_pos, p_half_x, p_half_y)
            oz = p_half_z + c_half_z
            rx, ry, rz = 0.0, 0.0, 0.0
        
        elif socket_type == "BOTTOM_FACE":
            # Child on bottom face
            face_pos = semantics.get("face_position", "center")
            ox, oy = cls._compute_face_lateral(face_pos, p_half_x, p_half_y)
            oz = -(p_half_z + c_half_z)
            rx, ry, rz = 0.0, 0.0, 0.0
        
        elif socket_type == "ARRAY_MEMBER":
            # Part of an array on a surface
            # CRITICAL: Array members are NEVER tilted - always flush to mounting face
            array_axis = semantics.get("array_axis", "x")
            array_count = semantics.get("array_count", 1)
            array_index = semantics.get("array_index", 0)
            spacing_hint = semantics.get("spacing_hint", "normal")
            
            # Compute spacing
            spacing = cls._compute_array_spacing(
                array_axis, array_count, p_half_x, p_half_y, c_half_x, c_half_y, spacing_hint
            )
            
            # FEASIBILITY CHECK: Validate array fits on parent surface
            total_span = spacing * (array_count - 1) if array_count > 1 else 0
            child_extent = c_half_x * 2 if array_axis == "x" else c_half_y * 2
            total_array_length = total_span + child_extent
            
            if array_axis == "x":
                available = p_half_x * 2
            else:
                available = p_half_y * 2
            
            if total_array_length > available * 1.1:  # 10% tolerance
                logger.warning(
                    f"Array may not fit: {array_count} items need {total_array_length:.3f}m, "
                    f"parent has {available:.3f}m on {array_axis}-axis"
                )
            
            # Center the array
            start_offset = -total_span / 2
            
            if array_axis == "x":
                ox = start_offset + array_index * spacing
                oy = 0.0
            elif array_axis == "y":
                ox = 0.0
                oy = start_offset + array_index * spacing
            else:
                ox, oy = 0.0, 0.0
            
            # Default to top face mount
            oz = p_half_z + c_half_z
            rx, ry, rz = 0.0, 0.0, 0.0  # NEVER tilted
        
        elif socket_type == "STRUT":
            # Diagonal connector between parent and connects_to
            # CRITICAL: Must use actual world positions, not just dimensions
            # CRITICAL: Strut length is computed from actual anchor distance
            connects_to = semantics.get("connects_to")
            computed_depth = None
            if not connects_to or connects_to not in nodes_by_label:
                logger.warning(f"STRUT missing valid connects_to, defaulting to diagonal")
                ox, oy, oz = p_half_x, p_half_y, p_half_z
                rx, ry, rz = 0.0, 0.0, 0.0
            else:
                target_node = nodes_by_label[connects_to]
                # Get world poses for parent and target
                parent_label = semantics.get("_parent_label", "")
                parent_node = nodes_by_label.get(parent_label)
                
                parent_world = cls._compute_world_pose(parent_node, nodes_by_label) if parent_node else WorldPose.identity()
                target_world = cls._compute_world_pose(target_node, nodes_by_label)
                
                ox, oy, oz, rx, ry, rz, computed_depth = cls._compute_strut_transform_world(
                    parent_spec, target_node.sub_spec, child_spec,
                    parent_world, target_world,
                )
            
            # Return early with computed_depth
            offset = (round(ox, 6), round(oy, 6), round(oz, 6))
            rotation = (round(rx, 6), round(ry, 6), round(rz, 6))
            return ResolvedTransform(offset=offset, rotation_rad=rotation, computed_depth=computed_depth)
        
        elif socket_type == "RADIAL":
            # Items evenly spaced around parent's circumference
            radial_count = semantics.get("radial_count", 4)
            radial_index = semantics.get("radial_index", 0)
            height_hint = semantics.get("height_hint", "center")
            
            angle = (2 * math.pi * radial_index) / radial_count
            
            # CRITICAL: Compute proper radius for boxes (not just p_radius which defaults to 0.5)
            # For boxes, use the inscribed circle radius (min of half_x, half_y)
            # For cylinders/spheres, use the actual radius
            parent_prim = parent_spec.get("primitive", "box")
            if parent_prim == "box":
                # Use the smaller of half_x, half_y as the "radius" for radial placement
                effective_radius = min(p_half_x, p_half_y)
            else:
                effective_radius = p_radius
            
            radius = effective_radius + c_half_x  # Place at parent's surface
            
            ox = radius * math.cos(angle)
            oy = radius * math.sin(angle)
            oz = cls._compute_face_height(height_hint, p_half_z, c_half_z)
            
            # Rotate to face outward
            rz = angle
            rx, ry = 0.0, 0.0
        
        elif socket_type == "RADIAL_BRIDGE":
            # Connector from parent to another part, radially arranged
            # CRITICAL: Must use actual world positions to reach target
            # CRITICAL: Bridge length is computed from actual anchor distance
            connects_to = semantics.get("connects_to")
            radial_count = semantics.get("radial_count", 4)
            radial_index = semantics.get("radial_index", 0)
            computed_depth = None
            
            if not connects_to or connects_to not in nodes_by_label:
                logger.warning(f"RADIAL_BRIDGE missing valid connects_to")
                ox, oy, oz = 0.0, 0.0, 0.0
                rx, ry, rz = 0.0, 0.0, 0.0
            else:
                target_node = nodes_by_label[connects_to]
                parent_label = semantics.get("_parent_label", "")
                parent_node = nodes_by_label.get(parent_label)
                
                parent_world = cls._compute_world_pose(parent_node, nodes_by_label) if parent_node else WorldPose.identity()
                target_world = cls._compute_world_pose(target_node, nodes_by_label)
                
                ox, oy, oz, rx, ry, rz, computed_depth = cls._compute_radial_bridge_transform_world(
                    parent_spec, target_node.sub_spec, child_spec,
                    radial_count, radial_index,
                    parent_world, target_world,
                )
            
            # Return early with computed_depth
            offset = (round(ox, 6), round(oy, 6), round(oz, 6))
            rotation = (round(rx, 6), round(ry, 6), round(rz, 6))
            return ResolvedTransform(offset=offset, rotation_rad=rotation, computed_depth=computed_depth)
        
        elif socket_type == "CORNER":
            # Child at a corner of parent's bounding box
            # corner_position: which corner (e.g., "top_front_left", "bottom_back_right")
            corner_pos = semantics.get("corner_position", "top_front_left")
            
            # Parse corner position
            is_top = "top" in corner_pos
            is_front = "front" in corner_pos
            is_left = "left" in corner_pos
            
            # Compute offset to corner
            ox = -p_half_x if is_left else p_half_x
            oy = -p_half_y if is_front else p_half_y
            oz = p_half_z if is_top else -p_half_z
            
            # Offset child so it sits at the corner (not inside)
            ox += -c_half_x if is_left else c_half_x
            oy += -c_half_y if is_front else c_half_y
            oz += c_half_z if is_top else -c_half_z
            
            rx, ry, rz = 0.0, 0.0, 0.0
        
        elif socket_type == "EDGE":
            # Child along an edge of parent's bounding box
            # edge_position: which edge (e.g., "top_front", "bottom_left", "front_left")
            edge_pos = semantics.get("edge_position", "top_front")
            edge_offset = semantics.get("edge_offset", 0.0)  # -1 to 1, position along edge
            
            # Parse edge - edges are named by the two faces they connect
            # Horizontal edges (parallel to X or Y)
            if edge_pos == "top_front":
                ox = edge_offset * p_half_x
                oy = -p_half_y - c_half_y
                oz = p_half_z + c_half_z
            elif edge_pos == "top_back":
                ox = edge_offset * p_half_x
                oy = p_half_y + c_half_y
                oz = p_half_z + c_half_z
            elif edge_pos == "top_left":
                ox = -p_half_x - c_half_x
                oy = edge_offset * p_half_y
                oz = p_half_z + c_half_z
            elif edge_pos == "top_right":
                ox = p_half_x + c_half_x
                oy = edge_offset * p_half_y
                oz = p_half_z + c_half_z
            elif edge_pos == "bottom_front":
                ox = edge_offset * p_half_x
                oy = -p_half_y - c_half_y
                oz = -(p_half_z + c_half_z)
            elif edge_pos == "bottom_back":
                ox = edge_offset * p_half_x
                oy = p_half_y + c_half_y
                oz = -(p_half_z + c_half_z)
            elif edge_pos == "bottom_left":
                ox = -p_half_x - c_half_x
                oy = edge_offset * p_half_y
                oz = -(p_half_z + c_half_z)
            elif edge_pos == "bottom_right":
                ox = p_half_x + c_half_x
                oy = edge_offset * p_half_y
                oz = -(p_half_z + c_half_z)
            # Vertical edges
            elif edge_pos == "front_left":
                ox = -p_half_x - c_half_x
                oy = -p_half_y - c_half_y
                oz = edge_offset * p_half_z
            elif edge_pos == "front_right":
                ox = p_half_x + c_half_x
                oy = -p_half_y - c_half_y
                oz = edge_offset * p_half_z
            elif edge_pos == "back_left":
                ox = -p_half_x - c_half_x
                oy = p_half_y + c_half_y
                oz = edge_offset * p_half_z
            elif edge_pos == "back_right":
                ox = p_half_x + c_half_x
                oy = p_half_y + c_half_y
                oz = edge_offset * p_half_z
            else:
                # Default to top_front
                ox = edge_offset * p_half_x
                oy = -p_half_y - c_half_y
                oz = p_half_z + c_half_z
            
            rx, ry, rz = 0.0, 0.0, 0.0
        
        elif socket_type == "INSET":
            # Child is recessed INTO parent's surface (like a button in a panel)
            # inset_face: which face to inset into
            # inset_depth: how deep to recess (0 = flush, positive = into parent)
            inset_face = semantics.get("inset_face", "top")
            inset_depth = semantics.get("inset_depth", 0.0)  # In meters
            face_pos = semantics.get("face_position", "center")
            
            # Get lateral offset
            lat_x, lat_y = cls._compute_face_lateral(face_pos, p_half_x, p_half_y)
            
            if inset_face == "top":
                ox = lat_x
                oy = lat_y
                oz = p_half_z - c_half_z - inset_depth
            elif inset_face == "bottom":
                ox = lat_x
                oy = lat_y
                oz = -(p_half_z - c_half_z - inset_depth)
            elif inset_face == "front":
                oz = cls._compute_face_height(semantics.get("height_hint", "center"), p_half_z, c_half_z)
                ox = lat_x
                oy = -(p_half_y - c_half_y - inset_depth)
            elif inset_face == "back":
                oz = cls._compute_face_height(semantics.get("height_hint", "center"), p_half_z, c_half_z)
                ox = lat_x
                oy = p_half_y - c_half_y - inset_depth
            elif inset_face == "left":
                oz = cls._compute_face_height(semantics.get("height_hint", "center"), p_half_z, c_half_z)
                ox = -(p_half_x - c_half_x - inset_depth)
                oy = lat_y
            elif inset_face == "right":
                oz = cls._compute_face_height(semantics.get("height_hint", "center"), p_half_z, c_half_z)
                ox = p_half_x - c_half_x - inset_depth
                oy = lat_y
            else:
                # Default to top
                ox = lat_x
                oy = lat_y
                oz = p_half_z - c_half_z - inset_depth
            
            rx, ry, rz = 0.0, 0.0, 0.0
        
        elif socket_type == "BOOLEAN_CUT":
            # Part is subtracted from parent (grooves, holes, cutouts)
            # Position the cutter so it overlaps with parent for boolean subtraction
            cut_face = semantics.get("cut_face", "top")
            height_hint = semantics.get("height_hint", "center")
            face_pos = semantics.get("face_position", "center")
            
            # Get lateral offset
            lat_x, lat_y = cls._compute_face_lateral(face_pos, p_half_x, p_half_y)
            
            # Position cutter so it penetrates INTO parent from the specified face
            # The cutter should overlap with parent's volume
            if cut_face == "top":
                ox = lat_x
                oy = lat_y
                # Position so cutter's bottom is inside parent, top extends above
                oz = p_half_z  # Cutter center at parent's top surface
            elif cut_face == "bottom":
                ox = lat_x
                oy = lat_y
                oz = -p_half_z
            elif cut_face == "front":
                oz = cls._compute_face_height(height_hint, p_half_z, c_half_z)
                ox = lat_x
                oy = -p_half_y
            elif cut_face == "back":
                oz = cls._compute_face_height(height_hint, p_half_z, c_half_z)
                ox = lat_x
                oy = p_half_y
            elif cut_face == "left":
                oz = cls._compute_face_height(height_hint, p_half_z, c_half_z)
                ox = -p_half_x
                oy = lat_y
            elif cut_face == "right":
                oz = cls._compute_face_height(height_hint, p_half_z, c_half_z)
                ox = p_half_x
                oy = lat_y
            else:
                # Default to top
                ox = lat_x
                oy = lat_y
                oz = p_half_z
            
            rx, ry, rz = 0.0, 0.0, 0.0
        
        else:
            # Unknown socket type - log warning and use defaults
            logger.warning(f"Unknown socket_type '{socket_type}', using zero transform")
            ox, oy, oz = 0.0, 0.0, 0.0
            rx, ry, rz = 0.0, 0.0, 0.0
        
        # Round for cleanliness
        offset = (round(ox, 6), round(oy, 6), round(oz, 6))
        rotation = (round(rx, 6), round(ry, 6), round(rz, 6))
        
        return ResolvedTransform(offset=offset, rotation_rad=rotation)
    
    # ===== GEOMETRY HELPERS =====
    
    @classmethod
    def _get_bounds(cls, spec: dict) -> ShapeBounds:
        """Get origin-relative bounds for a shape.
        
        CRITICAL: These are LOCAL bounds before rotation.
        For rotated shapes, use world-space bounding box from Blender.
        """
        return ShapeBounds.from_spec(spec)
    
    @classmethod
    def _build_sub_spec(cls, primitive_type: str, dims: dict, material: dict = None) -> dict:
        """Build sub_spec dict from dimensions and material."""
        spec = {"primitive": primitive_type}
        if primitive_type == "box":
            spec["size"] = list(dims.get("size", [1, 1, 1]))
        elif primitive_type == "cylinder":
            spec["radius"] = dims.get("radius", 0.1)
            spec["depth"] = dims.get("depth", 1.0)
            spec["vertices"] = dims.get("vertices", 32)
        elif primitive_type == "sphere":
            spec["radius"] = dims.get("radius", 0.5)
        elif primitive_type == "cone":
            spec["radius1"] = dims.get("radius1", dims.get("radius", 0.5))
            spec["depth"] = dims.get("depth", 1.0)
        
        # Add material if provided
        if material:
            spec["material"] = material
        
        return spec
    
    @classmethod
    def _get_half_z(cls, spec: dict) -> float:
        """Get half-extent along Z axis."""
        prim = spec.get("primitive", "box")
        if prim in ("cylinder", "cone"):
            return float(spec.get("depth", 1.0)) / 2.0
        elif prim in ("sphere",):
            return float(spec.get("radius", 0.5))
        else:  # box
            size = spec.get("size", [1, 1, 1])
            return float(size[2]) / 2.0
    
    @classmethod
    def _get_half_x(cls, spec: dict) -> float:
        """Get half-extent along X axis."""
        prim = spec.get("primitive", "box")
        if prim in ("cylinder", "cone", "sphere"):
            return float(spec.get("radius", spec.get("radius1", 0.5)))
        else:  # box
            size = spec.get("size", [1, 1, 1])
            return float(size[0]) / 2.0
    
    @classmethod
    def _get_half_y(cls, spec: dict) -> float:
        """Get half-extent along Y axis."""
        prim = spec.get("primitive", "box")
        if prim in ("cylinder", "cone", "sphere"):
            return float(spec.get("radius", spec.get("radius1", 0.5)))
        else:  # box
            size = spec.get("size", [1, 1, 1])
            return float(size[1]) / 2.0
    
    @classmethod
    def _get_radius(cls, spec: dict) -> float:
        """Get radius for cylindrical/spherical shapes."""
        return float(spec.get("radius", spec.get("radius1", 0.5)))
    
    @classmethod
    def _get_half_length(cls, spec: dict) -> float:
        """Get half-length along the primary axis (depth for cylinders)."""
        prim = spec.get("primitive", "box")
        if prim in ("cylinder", "cone"):
            return float(spec.get("depth", 1.0)) / 2.0
        else:
            return cls._get_half_z(spec)
    
    # ===== SEMANTIC HINT RESOLVERS =====
    
    @classmethod
    def _compute_height_from_hint(
        cls,
        hint: str,
        parent_half_z: float,
        child_radius: float,
        margin_mm: float = DEFAULT_EMBEDMENT_MARGIN_MM,
    ) -> float:
        """Compute Z offset from height_hint, clamped for embedment.
        
        Uses the shared compute_required_embedment() to ensure consistency
        with the verification gate's embedment validation.
        """
        # Convert to mm for shared function, then back to meters
        parent_half_z_mm = parent_half_z * 1000.0
        child_radius_mm = child_radius * 1000.0
        
        # Required embedment depth (in mm) from shared function
        required_mm = compute_required_embedment(child_radius_mm, margin_mm)
        
        # Max offset where embedment is still valid:
        # embedment_depth = parent_half - abs(offset)
        # We need: embedment_depth >= required
        # So: parent_half - abs(offset) >= required
        # Thus: abs(offset) <= parent_half - required
        max_offset_mm = parent_half_z_mm - required_mm
        max_z = max_offset_mm / 1000.0  # Back to meters
        
        # Clamp to ensure we don't go negative (would mean child can't fit)
        max_z = max(0.0, max_z)
        min_z = -max_z
        
        if hint == "flush_top":
            return max_z
        elif hint == "flush_bottom":
            return min_z
        elif hint == "near_top":
            return max_z * 0.7
        elif hint == "near_bottom":
            return min_z * 0.7
        else:  # center
            return 0.0
    
    @classmethod
    def _validate_pierce_embedment(
        cls,
        parent_half_extent_m: float,
        child_offset_m: float,
        child_radius_m: float,
        axis: str,
    ) -> bool:
        """Validate pierce embedment using the shared validation function.
        
        This is a thin wrapper that converts meters to mm and calls the
        shared validate_pierce_embedment() function.
        
        Raises:
            Stage4Error: If embedment validation fails (bad geometry)
            
        Returns True if embedment is valid.
        """
        # Convert to mm
        parent_half_mm = parent_half_extent_m * 1000.0
        child_offset_mm = child_offset_m * 1000.0
        child_radius_mm = child_radius_m * 1000.0
        
        # Map axis string to PierceAxis enum
        axis_enum = {
            "x": PierceAxis.X,
            "y": PierceAxis.Y, 
            "z": PierceAxis.Z,
        }.get(axis.lower(), PierceAxis.X)
        
        result = validate_pierce_embedment(
            parent_half_extent_mm=parent_half_mm,
            child_offset_along_axis_mm=child_offset_mm,
            child_radius_mm=child_radius_mm,
            axis=axis_enum,
            margin_mm=DEFAULT_EMBEDMENT_MARGIN_MM,
        )
        
        if not result.valid:
            raise Stage4Error(
                f"Embedment validation failed on {axis}-axis: {result.reason}. "
                f"Parent half={parent_half_extent_m:.4f}m, child offset={child_offset_m:.4f}m, "
                f"child radius={child_radius_m:.4f}m"
            )
        
        return True
    
    @classmethod
    def _compute_face_height(cls, hint: str, parent_half_z: float, child_half_z: float) -> float:
        """Compute Z offset for face-mounted parts."""
        if hint == "flush_top":
            return parent_half_z - child_half_z
        elif hint == "flush_bottom":
            return -parent_half_z + child_half_z
        elif hint == "near_top":
            return (parent_half_z - child_half_z) * 0.7
        elif hint == "near_bottom":
            return -(parent_half_z - child_half_z) * 0.7
        else:  # center
            return 0.0
    
    @classmethod
    def _compute_face_lateral(
        cls,
        hint: str,
        parent_half_x: float,
        parent_half_y: float,
    ) -> Tuple[float, float]:
        """Compute XY offset for face position hint."""
        if hint == "near_left":
            return (-parent_half_x * 0.5, 0.0)
        elif hint == "near_right":
            return (parent_half_x * 0.5, 0.0)
        else:  # center
            return (0.0, 0.0)
    
    @classmethod
    def _compute_array_spacing(
        cls,
        axis: str,
        count: int,
        p_half_x: float,
        p_half_y: float,
        c_half_x: float,
        c_half_y: float,
        hint: str,
    ) -> float:
        """Compute spacing between array members."""
        if count <= 1:
            return 0.0
        
        # Available span on parent
        if axis == "x":
            available = (p_half_x - c_half_x) * 2
            child_size = c_half_x * 2
        else:
            available = (p_half_y - c_half_y) * 2
            child_size = c_half_y * 2
        
        # Spacing based on hint
        if hint == "tight":
            return child_size * 1.1
        elif hint == "spread":
            return available / (count - 1) if count > 1 else 0
        else:  # normal
            return child_size * 1.5
    
    @classmethod
    def _compute_strut_transform(
        cls,
        parent_spec: dict,
        target_spec: dict,
        child_spec: dict,
    ) -> Tuple[float, float, float, float, float, float]:
        """DEPRECATED: Use _compute_strut_transform_world instead."""
        return cls._compute_strut_transform_world(
            parent_spec, target_spec, child_spec,
            WorldPose.identity(), WorldPose.identity(),
        )
    
    @classmethod
    def _compute_strut_transform_world(
        cls,
        parent_spec: dict,
        target_spec: dict,
        child_spec: dict,
        parent_world: WorldPose,
        target_world: WorldPose,
    ) -> Tuple[float, float, float, float, float, float, float]:
        """Compute transform for a STRUT connecting parent to target using world positions.
        
        The strut connects an anchor point on parent's surface to an anchor on target's surface.
        Returns (ox, oy, oz, rx, ry, rz, computed_length) in PARENT's local frame.
        
        CRITICAL: The computed_length is the actual distance between anchors.
        This should be used to override the strut's depth in sub_spec.
        """
        p_half_x = cls._get_half_x(parent_spec)
        p_half_z = cls._get_half_z(parent_spec)
        t_half_x = cls._get_half_x(target_spec)
        t_half_z = cls._get_half_z(target_spec)
        
        # Determine anchor surfaces based on relative Z positions
        parent_world_z = parent_world.position[2]
        target_world_z = target_world.position[2]
        
        if parent_world_z < target_world_z:
            # Parent BELOW target -> anchor at parent's TOP, target's BOTTOM
            parent_anchor_local = (p_half_x, 0.0, p_half_z)
            target_anchor_local = (t_half_x, 0.0, -t_half_z)
        else:
            # Parent ABOVE target -> anchor at parent's BOTTOM, target's TOP
            parent_anchor_local = (p_half_x, 0.0, -p_half_z)
            target_anchor_local = (t_half_x, 0.0, t_half_z)
        
        # Transform to world
        parent_anchor_world = parent_world.transform_point(parent_anchor_local)
        target_anchor_world = target_world.transform_point(target_anchor_local)
        
        # Compute actual distance between anchors
        dx = target_anchor_world[0] - parent_anchor_world[0]
        dy = target_anchor_world[1] - parent_anchor_world[1]
        dz = target_anchor_world[2] - parent_anchor_world[2]
        computed_length = math.sqrt(dx*dx + dy*dy + dz*dz)
        
        # Strut midpoint in world
        mid_world = (
            (parent_anchor_world[0] + target_anchor_world[0]) / 2,
            (parent_anchor_world[1] + target_anchor_world[1]) / 2,
            (parent_anchor_world[2] + target_anchor_world[2]) / 2,
        )
        
        # Convert midpoint to parent's local frame
        offset_world = (
            mid_world[0] - parent_world.position[0],
            mid_world[1] - parent_world.position[1],
            mid_world[2] - parent_world.position[2],
        )
        inv_rot = (-parent_world.rotation_rad[0], -parent_world.rotation_rad[1], -parent_world.rotation_rad[2])
        offset_local = _rotate_point(offset_world, inv_rot)
        
        # Compute rotation to align strut's Z axis with direction
        rx, ry, rz = cls._rotation_to_direction(dx, dy, dz)
        
        # Adjust rotation to be relative to parent's rotation
        rx -= parent_world.rotation_rad[0]
        ry -= parent_world.rotation_rad[1]
        rz -= parent_world.rotation_rad[2]
        
        return (
            round(offset_local[0], 6),
            round(offset_local[1], 6),
            round(offset_local[2], 6),
            round(rx, 6),
            round(ry, 6),
            round(rz, 6),
            round(computed_length, 6),
        )
    
    @classmethod
    def _compute_radial_bridge_transform(
        cls,
        parent_spec: dict,
        target_spec: dict,
        child_spec: dict,
        count: int,
        index: int,
        target_offset: Tuple[float, float, float] = (0.0, 0.0, 0.0),
    ) -> Tuple[float, float, float, float, float, float]:
        """DEPRECATED: Use _compute_radial_bridge_transform_world instead."""
        return cls._compute_radial_bridge_transform_world(
            parent_spec, target_spec, child_spec,
            count, index,
            WorldPose.identity(), WorldPose.identity(),
        )
    
    @classmethod
    def _compute_radial_bridge_transform_world(
        cls,
        parent_spec: dict,
        target_spec: dict,
        child_spec: dict,
        count: int,
        index: int,
        parent_world: WorldPose,
        target_world: WorldPose,
    ) -> Tuple[float, float, float, float, float, float, float]:
        """Compute transform for RADIAL_BRIDGE using actual world positions.
        
        The bridge connects from parent's surface to target's surface.
        Radially distributed around parent.
        
        Returns (ox, oy, oz, rx, ry, rz, computed_length).
        """
        angle = (2 * math.pi * index) / count
        
        # Get parent radius
        parent_prim = parent_spec.get("primitive", "box")
        if parent_prim == "cylinder":
            p_radius = cls._get_radius(parent_spec)
        else:
            p_radius = min(cls._get_half_x(parent_spec), cls._get_half_y(parent_spec))
        
        # Get target radius for anchor point
        target_prim = target_spec.get("primitive", "box")
        if target_prim == "cylinder":
            t_radius = cls._get_radius(target_spec)
        else:
            t_radius = min(cls._get_half_x(target_spec), cls._get_half_y(target_spec))
        
        # Anchor on parent surface (local) - at this radial angle, at parent's center Z
        parent_anchor_local = (
            p_radius * math.cos(angle),
            p_radius * math.sin(angle),
            0.0,  # Parent's center (strut originates from middle of parent)
        )
        
        # Determine which surface of target to anchor to based on relative Z positions
        # If parent is ABOVE target -> connect to target's TOP
        # If parent is BELOW target -> connect to target's BOTTOM
        t_half_z = cls._get_half_z(target_spec)
        parent_world_z = parent_world.position[2]
        target_world_z = target_world.position[2]
        
        if parent_world_z > target_world_z:
            # Parent above target -> anchor to target's TOP surface
            target_z_local = t_half_z
        else:
            # Parent below target -> anchor to target's BOTTOM surface
            target_z_local = -t_half_z
        
        target_anchor_local = (
            t_radius * math.cos(angle),
            t_radius * math.sin(angle),
            target_z_local,
        )
        
        # Transform to world
        parent_anchor_world = parent_world.transform_point(parent_anchor_local)
        target_anchor_world = target_world.transform_point(target_anchor_local)
        
        # Compute actual distance between anchors
        dx = target_anchor_world[0] - parent_anchor_world[0]
        dy = target_anchor_world[1] - parent_anchor_world[1]
        dz = target_anchor_world[2] - parent_anchor_world[2]
        computed_length = math.sqrt(dx*dx + dy*dy + dz*dz)
        
        # Bridge midpoint in world
        mid_world = (
            (parent_anchor_world[0] + target_anchor_world[0]) / 2,
            (parent_anchor_world[1] + target_anchor_world[1]) / 2,
            (parent_anchor_world[2] + target_anchor_world[2]) / 2,
        )
        
        # Convert midpoint to parent's local frame
        offset_world = (
            mid_world[0] - parent_world.position[0],
            mid_world[1] - parent_world.position[1],
            mid_world[2] - parent_world.position[2],
        )
        inv_rot = (-parent_world.rotation_rad[0], -parent_world.rotation_rad[1], -parent_world.rotation_rad[2])
        offset_local = _rotate_point(offset_world, inv_rot)
        
        # Compute tilt angle (how much the strut tilts up toward target)
        horiz_dist = math.sqrt(dx*dx + dy*dy)
        tilt_angle = math.atan2(dz, horiz_dist) if horiz_dist > 0.001 else 0.0
        
        # Rotation: 90° Y to make horizontal, then Z for radial angle, then X for tilt
        rx = -tilt_angle  # Tilt up toward target
        ry = math.radians(90)  # Horizontal, pointing outward
        rz = angle  # Rotate to correct radial position
        
        # Adjust for parent's rotation
        rx -= parent_world.rotation_rad[0]
        ry -= parent_world.rotation_rad[1]
        rz -= parent_world.rotation_rad[2]
        
        return (
            round(offset_local[0], 6),
            round(offset_local[1], 6),
            round(offset_local[2], 6),
            round(rx, 6),
            round(ry, 6),
            round(rz, 6),
            round(computed_length, 6),
        )
    
    @classmethod
    def _rotation_to_direction(cls, dx: float, dy: float, dz: float) -> Tuple[float, float, float]:
        """Compute Euler XYZ rotation to align +Z with direction vector."""
        length = math.sqrt(dx*dx + dy*dy + dz*dz)
        if length < 0.0001:
            return (0.0, 0.0, 0.0)
        
        # Normalize
        dx, dy, dz = dx/length, dy/length, dz/length
        
        # Compute angles
        # ry = rotation around Y to align XZ projection
        # rx = rotation around X to tilt up/down
        ry = math.atan2(dx, dz)
        rx = -math.asin(dy)
        rz = 0.0
        
        return (rx, ry, rz)
    
    @classmethod
    def _apply_default_semantics(
        cls,
        semantics: dict,
        socket_type: str,
        label: str,
        nodes_by_label: dict,
    ) -> dict:
        """Apply sensible defaults for socket types that require specific semantics."""
        result = dict(semantics)
        
        # THROUGH_AXIS needs pierce_direction
        if socket_type == "THROUGH_AXIS" and not result.get("pierce_direction"):
            result["pierce_direction"] = "left_right"  # Default horizontal
            logger.info(f"Part '{label}': defaulting pierce_direction to 'left_right'")
        
        # THROUGH_AXIS and face mounts benefit from height_hint
        if socket_type in ("THROUGH_AXIS", "FRONT_FACE", "BACK_FACE", "LEFT_FACE", "RIGHT_FACE", "INSET"):
            if not result.get("height_hint"):
                result["height_hint"] = "center"
        
        # RADIAL_BRIDGE needs connects_to - try to find a sibling that makes sense
        if socket_type == "RADIAL_BRIDGE" and not result.get("connects_to"):
            # Look for a part that could be the target (typically something above like a dish/platform)
            for other_label, other_node in nodes_by_label.items():
                if other_label != label and other_node.attachment.socket_type in ("TOP_CENTER", "TOP_END"):
                    result["connects_to"] = other_label
                    logger.info(f"Part '{label}': defaulting connects_to to '{other_label}'")
                    break
        
        # RADIAL and RADIAL_BRIDGE need radial_count and radial_index
        if socket_type in ("RADIAL", "RADIAL_BRIDGE"):
            if result.get("radial_count") is None:
                result["radial_count"] = 4  # Default to 4-way symmetry
            if result.get("radial_index") is None:
                result["radial_index"] = 0
        
        # ARRAY_MEMBER needs array fields
        if socket_type == "ARRAY_MEMBER":
            if not result.get("array_axis"):
                result["array_axis"] = "x"
            if result.get("array_count") is None:
                result["array_count"] = 1
            if result.get("array_index") is None:
                result["array_index"] = 0
        
        # CORNER needs corner_position
        if socket_type == "CORNER":
            if not result.get("corner_position"):
                result["corner_position"] = "top_front_left"
        
        # EDGE needs edge_position
        if socket_type == "EDGE":
            if not result.get("edge_position"):
                result["edge_position"] = "top_front"
            if result.get("edge_offset") is None:
                result["edge_offset"] = 0.0  # Center of edge
        
        # INSET needs inset_face
        if socket_type == "INSET":
            if not result.get("inset_face"):
                result["inset_face"] = "top"
            if result.get("inset_depth") is None:
                result["inset_depth"] = 0.0  # Flush by default
        
        return result

    @classmethod
    def _get_interaction_type(cls, socket_type: str) -> InteractionType:
        """Determine interaction type for verification."""
        if socket_type in ("THROUGH_AXIS", "RADIAL_BRIDGE", "STRUT"):
            return InteractionType.THROUGH
        elif socket_type in ("TOP_CENTER", "BOTTOM_CENTER", "TOP_END", "BOTTOM_END", "CORNER", "EDGE"):
            return InteractionType.TOUCH
        elif socket_type in ("INSET", "BOOLEAN_CUT"):
            return InteractionType.INSERT  # Child is inserted/embedded in parent
        else:
            return InteractionType.ATTACH
    
    @classmethod
    def _compute_world_pose(
        cls,
        node: "AssemblyNode",
        nodes_by_label: Dict[str, "AssemblyNode"],
    ) -> WorldPose:
        """Compute world-space pose for a node by walking up the parent chain.
        
        This is essential for STRUT/RADIAL_BRIDGE which need to know where
        the target actually IS in world space, not just its local offset.
        """
        # Build chain from root to node
        chain = []
        current = node
        while current:
            chain.append(current)
            parent_id = current.attachment.parent_node_id
            if not parent_id:
                break
            # Find parent by node_id
            parent = None
            for n in nodes_by_label.values():
                if n.node_id == parent_id:
                    parent = n
                    break
            current = parent
        
        # Reverse to go root -> node
        chain.reverse()
        
        # Accumulate transforms
        world_pos = [0.0, 0.0, 0.0]
        world_rot = [0.0, 0.0, 0.0]
        
        for n in chain:
            local_offset = n.attachment.local_offset or (0.0, 0.0, 0.0)
            local_rot = n.attachment.local_rotation_euler or (0.0, 0.0, 0.0)
            
            # Transform local offset by accumulated rotation
            rotated_offset = _rotate_point(local_offset, tuple(world_rot))
            
            # Add to world position
            world_pos[0] += rotated_offset[0]
            world_pos[1] += rotated_offset[1]
            world_pos[2] += rotated_offset[2]
            
            # Accumulate rotation (simplified - proper would use quaternions)
            world_rot[0] += local_rot[0]
            world_rot[1] += local_rot[1]
            world_rot[2] += local_rot[2]
        
        return WorldPose(
            position=tuple(world_pos),
            rotation_rad=tuple(world_rot),
        )


    @classmethod
    def _would_create_cycle(
        cls,
        child_label: str,
        parent_label: str,
        parent_chain: Dict[str, str],
    ) -> bool:
        """Check if adding child->parent would create a cycle.
        
        Walks up the parent chain from parent_label to see if we reach child_label.
        """
        visited = {child_label}
        current = parent_label
        
        while current:
            if current in visited:
                return True
            visited.add(current)
            current = parent_chain.get(current)
        
        return False


class Stage4Error(Exception):
    """Raised when Stage 4 fails."""
    pass
