"""Stage 4 — Transform Resolution (Per-Node, Deterministic).

Computes exact local transforms (offset, rotation) for a PART node
based on parent geometry and semantic hints from Stage 3.

This is PURE CODE - no LLM calls. The transform is computed deterministically
from parent bounding box + socket type + semantic hints.

Core invariant: NO LLM-generated numbers in transforms.

Phase 2 Migration:
- Stage 4 now produces AttachmentSolution with local_transform
- local_transform is written to node.transform_state
- Legacy path (ResolvedTransform → attachment.local_offset) remains for comparison
- Executor uses legacy path; new transform system runs in parallel for validation

Blueprint references: §11 (per-node stages), §4 (deterministic resolution).
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from ..manifest import BuildManifest, ManifestNode

from ..node_types import NodeKind, PrimitiveType, SocketType, CROSS_REFERENCE_SOCKETS, BlenderAxis
from ..transforms import (
    _matrix_to_euler,
    LocalTransform,
    WorldMatrix,
    validate_unit_scale,
    _mat4_multiply,
    _mat4_from_trs,
    _mat4_transform_vector,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Transform Output
# ---------------------------------------------------------------------------

@dataclass
class ResolvedTransform:
    """Resolved transform for a part (LEGACY - kept for comparison).
    
    This is the old representation. Phase 2 adds AttachmentSolution which
    produces LocalTransform for the new hierarchical transform system.
    """
    # Local offset from parent origin (meters)
    offset: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    
    # Local rotation (Euler XYZ in radians)
    rotation: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    
    # Scale (usually 1,1,1)
    scale: List[float] = field(default_factory=lambda: [1.0, 1.0, 1.0])
    
    # For boolean operations
    is_boolean: bool = False
    boolean_op: str = ""  # "difference", "union", "intersect"
    
    # Debug info
    resolution_method: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "offset": self.offset,
            "rotation": self.rotation,
            "scale": self.scale,
            "is_boolean": self.is_boolean,
            "boolean_op": self.boolean_op,
            "resolution_method": self.resolution_method,
        }
    
    def to_local_transform(self) -> LocalTransform:
        """Convert to new LocalTransform representation.
        
        This bridges the legacy ResolvedTransform to the new transform system.
        """
        return LocalTransform(
            position=list(self.offset),
            rotation=list(self.rotation),  # Already in radians
            scale=list(self.scale),
        )


# ---------------------------------------------------------------------------
# AttachmentSolution — Phase 2 intermediate representation
# ---------------------------------------------------------------------------

@dataclass
class AttachmentSolution:
    """Attachment solution produced by Stage 4 resolver.
    
    This is the NEW authoritative output of Stage 4. It contains:
    - The computed local_transform (position, rotation, scale relative to parent)
    - Metadata about how the attachment was computed (for debugging)
    
    The local_transform is written to node.transform_state.local_transform.
    The transform system then computes world_matrix via hierarchy composition.
    
    Key separation:
    - Stage 4 determines: "How should this node be attached relative to its parent?"
    - Transform system determines: "Where does that node end up in world space?"
    
    Stage 4 should NOT compute world positions directly.
    """
    # Node identifiers
    parent_id: str
    child_id: str
    
    # Socket information (for debugging/tracing)
    parent_socket: Optional[str] = None  # e.g., "TOP_CENTER"
    child_socket: Optional[str] = None   # e.g., "BOTTOM_CENTER"
    
    # The computed local transform (AUTHORITATIVE)
    local_transform: LocalTransform = field(default_factory=LocalTransform)
    
    # How this solution was computed
    source: str = ""  # e.g., "deterministic_socket_solver", "CORNER:bottom_front_left"
    
    # Confidence/quality indicator (optional)
    confidence: Optional[str] = None  # e.g., "high", "medium", "low"
    
    # Boolean operation info (if applicable)
    is_boolean: bool = False
    boolean_op: str = ""  # "difference", "union", "intersect"
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize for logging/debugging."""
        return {
            "parent_id": self.parent_id,
            "child_id": self.child_id,
            "parent_socket": self.parent_socket,
            "child_socket": self.child_socket,
            "local_transform": self.local_transform.to_dict(),
            "source": self.source,
            "confidence": self.confidence,
            "is_boolean": self.is_boolean,
            "boolean_op": self.boolean_op,
        }
    
    @classmethod
    def from_resolved_transform(
        cls,
        resolved: ResolvedTransform,
        parent_id: str,
        child_id: str,
        socket_type: Optional[SocketType] = None,
    ) -> AttachmentSolution:
        """Create AttachmentSolution from legacy ResolvedTransform.
        
        This bridges the existing resolvers to the new system.
        """
        return cls(
            parent_id=parent_id,
            child_id=child_id,
            parent_socket=socket_type.value if socket_type else None,
            local_transform=resolved.to_local_transform(),
            source=resolved.resolution_method,
            is_boolean=resolved.is_boolean,
            boolean_op=resolved.boolean_op,
        )


class Stage4Error(Exception):
    """Raised when Stage 4 fails."""
    pass


# Boolean cutter overshoot margin to avoid coplanar issues
BOOLEAN_OVERSHOOT_M = 0.002  # 2mm

# Gap ratios for RELATIVE_TO socket (proportional to reference part size)
GAP_RATIO = {"touching": 0.0, "small": 0.15, "medium": 0.4, "large": 0.9}

# Position fraction for RELATIVE_TO "along" positioning
# When direction is along an axis (e.g., "below" for Z), this determines
# where along the reference part to position (0=bottom, 0.5=middle, 1=top)
POSITION_ALONG = {
    "start": 0.0,
    "quarter": 0.25,
    "middle": 0.5,
    "halfway": 0.5,
    "three_quarter": 0.75,
    "end": 1.0,
}

# Direction to axis mapping - delegates to BlenderAxis single source of truth
# DO NOT hardcode direction signs here - use BlenderAxis.get_direction()
def _get_direction_axis(direction: str) -> tuple[int, int]:
    """Get (axis_index, sign) for a direction name.
    
    Wrapper around BlenderAxis.get_direction() for backward compatibility.
    """
    return BlenderAxis.get_direction(direction)

# Position fraction mapping for BRIDGE socket
POSITION_FRACTION = {
    "start": 0.0,
    "quarter": 0.25,
    "middle": 0.5,
    "three_quarter": 0.75,
    "end": 1.0,
}


# ---------------------------------------------------------------------------
# Bounding Box Helper
# ---------------------------------------------------------------------------

@dataclass
class BBox:
    """Axis-aligned bounding box."""
    min_x: float = 0.0
    max_x: float = 0.0
    min_y: float = 0.0
    max_y: float = 0.0
    min_z: float = 0.0
    max_z: float = 0.0
    
    @property
    def size_x(self) -> float:
        return self.max_x - self.min_x
    
    @property
    def size_y(self) -> float:
        return self.max_y - self.min_y
    
    @property
    def size_z(self) -> float:
        return self.max_z - self.min_z
    
    def size(self, axis: int) -> float:
        """Get size along axis (0=X, 1=Y, 2=Z)."""
        if axis == 0:
            return self.size_x
        elif axis == 1:
            return self.size_y
        else:
            return self.size_z
    
    def radius_toward(self, ux: float, uy: float) -> float:
        """Get bbox extent in horizontal direction (ux, uy).
        
        For computing anchor points on surfaces facing a direction.
        """
        # Project onto direction and take half-extent
        # For axis-aligned bbox, this is max of projections onto each axis
        return abs(ux) * (self.size_x / 2) + abs(uy) * (self.size_y / 2)
    
    @property
    def center(self) -> List[float]:
        return [
            (self.min_x + self.max_x) / 2,
            (self.min_y + self.max_y) / 2,
            (self.min_z + self.max_z) / 2,
        ]
    
    @staticmethod
    def _polygon_xy_bounds(radius: float, segments: int) -> Tuple[float, float, float, float]:
        """Calculate exact object-space (min_x, max_x, min_y, max_y) for Blender's primitive circle-based meshes."""
        n = max(3, int(segments))
        angles = [math.pi / 2.0 + 2.0 * math.pi * i / n for i in range(n)]
        xs = [radius * math.cos(a) for a in angles]
        ys = [radius * math.sin(a) for a in angles]
        return min(xs), max(xs), min(ys), max(ys)

    @staticmethod
    def _torus_xy_bounds(outer_radius: float, segments: int) -> Tuple[float, float, float, float]:
        """Calculate exact object-space (min_x, max_x, min_y, max_y) for Blender's primitive torus mesh."""
        n = max(3, int(segments))
        angles = [2.0 * math.pi * i / n for i in range(n)]
        xs = [outer_radius * math.cos(a) for a in angles]
        ys = [outer_radius * math.sin(a) for a in angles]
        return min(xs), max(xs), min(ys), max(ys)

    @classmethod
    def from_geometry(cls, geometry, stage2: Dict[str, Any]) -> BBox:
        """Create bounding box from geometry spec and Stage 2 dimensions."""
        prim = geometry.primitive
        
        if prim == PrimitiveType.BOX:
            size = stage2.get("size") or getattr(geometry, "size", None) or [1.0, 1.0, 1.0]
            sx = stage2.get("size_x", size[0] if len(size) > 0 else 1.0)
            sy = stage2.get("size_y", size[1] if len(size) > 1 else 1.0)
            sz = stage2.get("size_z", size[2] if len(size) > 2 else 1.0)
            return cls(
                min_x=-sx/2, max_x=sx/2,
                min_y=-sy/2, max_y=sy/2,
                min_z=-sz/2, max_z=sz/2,
            )
        
        elif prim in (
            PrimitiveType.CYLINDER, PrimitiveType.CONE, PrimitiveType.CAPSULE,
            PrimitiveType.PYRAMID,
        ):
            r = stage2.get("radius", getattr(geometry, "radius", None) or 0.5)
            d = stage2.get("depth", getattr(geometry, "depth", None) or 1.0)
            if prim == PrimitiveType.CONE:
                r2 = stage2.get("radius2") if stage2.get("radius2") is not None else (getattr(geometry, "radius2", 0.0) or 0.0)
                r = max(r, r2)
            seg = 4 if prim == PrimitiveType.PYRAMID else int(stage2.get("segments", getattr(geometry, "segments", 32) or 32))
            min_x, max_x, min_y, max_y = cls._polygon_xy_bounds(r, seg)
            return cls(
                min_x=min_x, max_x=max_x,
                min_y=min_y, max_y=max_y,
                min_z=-d/2, max_z=d/2,
            )

        elif prim == PrimitiveType.PRISM:
            radius = stage2.get("radius", getattr(geometry, "radius", None) or 0.5)
            depth = stage2.get("depth", getattr(geometry, "depth", None) or 1.0)
            segments = max(3, int(stage2.get("segments", getattr(geometry, "segments", 6) or 6)))
            min_x, max_x, min_y, max_y = cls._polygon_xy_bounds(radius, segments)
            return cls(
                min_x=min_x, max_x=max_x,
                min_y=min_y, max_y=max_y,
                min_z=-depth/2, max_z=depth/2,
            )
        
        elif prim in (PrimitiveType.SPHERE, PrimitiveType.HEMISPHERE):
            r = stage2.get("radius", getattr(geometry, "radius", None) or 0.5)
            seg = int(stage2.get("segments", getattr(geometry, "segments", 32) or 32))
            min_x, max_x, min_y, max_y = cls._polygon_xy_bounds(r, seg)
            if prim == PrimitiveType.HEMISPHERE:
                return cls(
                    min_x=min_x, max_x=max_x,
                    min_y=min_y, max_y=max_y,
                    min_z=0.0, max_z=r,
                )
            return cls(
                min_x=min_x, max_x=max_x,
                min_y=min_y, max_y=max_y,
                min_z=-r, max_z=r,
            )
        
        elif prim == PrimitiveType.TORUS:
            major = stage2.get("major_radius", getattr(geometry, "major_radius", None) or 0.5)
            minor = stage2.get("minor_radius", getattr(geometry, "minor_radius", None) or 0.1)
            outer = major + minor
            seg = int(stage2.get("segments", getattr(geometry, "segments", 32) or 32))
            min_x, max_x, min_y, max_y = cls._torus_xy_bounds(outer, seg)
            return cls(
                min_x=min_x, max_x=max_x,
                min_y=min_y, max_y=max_y,
                min_z=-minor, max_z=minor,
            )

        elif prim == PrimitiveType.U_SHAPE:
            major = stage2.get("major_radius", getattr(geometry, "major_radius", None) or 0.5)
            minor = stage2.get("minor_radius", getattr(geometry, "minor_radius", None) or 0.1)
            outer = major + minor
            # U_SHAPE: arch up, legs down, local origin at leg bottoms (Z=0).
            # Height = major_radius (arch top) + minor_radius (tube radius) above origin.
            # Horizontal extent = same as full torus outer radius.
            height = major + minor  # top of arch above leg bottoms
            return cls(
                min_x=-outer, max_x=outer,
                min_y=-minor, max_y=minor,
                min_z=0.0, max_z=height,
            )
        
        elif prim == PrimitiveType.GRID:
            size = stage2.get("size") or getattr(geometry, "size", None) or [1.0, 1.0, 0.0]
            sx = size[0] if len(size) > 0 else 1.0
            sy = size[1] if len(size) > 1 else 1.0
            return cls(
                min_x=-sx/2, max_x=sx/2,
                min_y=-sy/2, max_y=sy/2,
                min_z=0.0, max_z=0.0,
            )

        elif prim == PrimitiveType.PLANE:
            size = stage2.get("size") or getattr(geometry, "size", None) or [1.0, 1.0, 0.002]
            sx = size[0] if len(size) > 0 else 1.0
            sy = size[1] if len(size) > 1 else 1.0
            sz = size[2] if len(size) > 2 else 0.002
            return cls(
                min_x=-sx/2, max_x=sx/2,
                min_y=-sy/2, max_y=sy/2,
                min_z=-sz/2, max_z=sz/2,
            )

        elif prim == PrimitiveType.WEDGE:
            size = stage2.get("size") or getattr(geometry, "size", None) or [1.0, 1.0, 1.0]
            return cls(
                min_x=-size[0]/2, max_x=size[0]/2,
                min_y=-size[1]/2, max_y=size[1]/2,
                min_z=-size[2]/2, max_z=size[2]/2,
            )

        elif prim == PrimitiveType.CIRCLE:
            radius = stage2.get("radius", getattr(geometry, "radius", None) or 0.5)
            return cls(
                min_x=-radius, max_x=radius,
                min_y=-radius, max_y=radius,
                min_z=0.0, max_z=0.0,
            )

        elif prim == PrimitiveType.MONKEY:
            # Blender's built-in Suzanne mesh has a stable local-space extent.
            return cls(
                min_x=-1.36719, max_x=1.36719,
                min_y=-0.85156, max_y=0.85156,
                min_z=-0.98438, max_z=0.98438,
            )

        # Default unit cube
        return cls(min_x=-0.5, max_x=0.5, min_y=-0.5, max_y=0.5, min_z=-0.5, max_z=0.5)


# ---------------------------------------------------------------------------
# Stage 4 Resolver
# ---------------------------------------------------------------------------

class Stage4Resolver:
    """Stage 4: Compute exact transforms from parent geometry + semantics.
    
    This is PURE CODE - no LLM calls. Transforms are computed deterministically.
    
    Phase 2 Migration:
    - run() now returns (ResolvedTransform, AttachmentSolution)
    - ResolvedTransform feeds legacy executor path
    - AttachmentSolution feeds new transform system
    - Both paths run in parallel for comparison
    
    Phase 3 Extension:
    - run_assembly() computes local_transform for ASSEMBLY/MODEL nodes
    - This ensures assemblies participate in the hierarchical transform system
    - Propagation becomes purely: world = parent.world @ child.local
    
    Phase 3.5 Invariant:
    - Every AttachmentSolution.local_transform MUST be expressed in the
      coordinate frame of node.parent_id
    - Cross-reference resolvers compute desired WORLD matrix, then convert
      to parent-local via: child_local = inverse(parent_world) @ child_world
    - No world-position subtraction, Euler subtraction, or ROOT-sibling
      substitution is allowed in the new path
    """
    
    @classmethod
    def run(
        cls,
        node: ManifestNode,
        manifest: BuildManifest,
    ) -> Tuple[ResolvedTransform, AttachmentSolution]:
        """Resolve transform for a single PART node.
        
        Args:
            node: The PART node to resolve
            manifest: Build manifest (for parent context)
            
        Returns:
            Tuple of (ResolvedTransform, AttachmentSolution)
            - ResolvedTransform: Legacy format for executor
            - AttachmentSolution: New format for transform system
            
        Raises:
            Stage4Error: If resolution fails
        """
        if node.kind != NodeKind.PART:
            raise Stage4Error(f"Stage 4 only runs on PART nodes, got {node.kind.value}")
        
        socket = node.attachment.socket_type
        parent_id = node.parent_id or ""
        
        # ROOT socket - no transform needed
        if socket == SocketType.ROOT:
            endpoint = node.stage_outputs.get("decomposition_hint", {}).get("endpoint_constraint")
            if endpoint:
                resolved = cls._resolve_endpoint_constraint(node, manifest, endpoint)
                solution = AttachmentSolution(
                    parent_id=parent_id,
                    child_id=node.node_id,
                    parent_socket="ROOT",
                    local_transform=resolved.to_local_transform(),
                    source=resolved.resolution_method,
                )
                return resolved, solution
            # ROOT geometry can still carry an explicit orientation policy.
            # Blender creates a torus in XY; a front-facing guard needs XZ.
            policy = node.stage_outputs.get("orientation_policy", {})
            root_rotation = list(policy.get("local_rotation", [0.0, 0.0, 0.0]))
            if root_rotation == [0.0, 0.0, 0.0]:
                axis = node.stage_outputs.get("decomposition_hint", {}).get("length_axis")
                axis_rotation = {
                    "x": [0.0, math.pi / 2, 0.0],
                    "y": [-math.pi / 2, 0.0, 0.0],
                    "z": [0.0, 0.0, 0.0],
                }
                if axis in axis_rotation:
                    root_rotation = axis_rotation[axis]
            resolved = ResolvedTransform(rotation=root_rotation, resolution_method="ROOT")
            solution = AttachmentSolution(
                parent_id=parent_id,
                child_id=node.node_id,
                parent_socket="ROOT",
                local_transform=LocalTransform(position=[0.0, 0.0, 0.0], rotation=root_rotation),
                source="ROOT",
            )
            return resolved, solution

        # Get parent geometry
        parent = manifest.nodes.get(node.parent_id) if node.parent_id else None
        if not parent:
            raise Stage4Error(f"Node {node.label} has no parent")
        
        parent_bbox = cls._get_parent_bbox(parent, manifest, node)
        child_bbox = cls._get_child_bbox(node)
        
        # Get semantic hints
        semantics = dict(node.stage_outputs.get("stage3", {}))
        if socket == SocketType.RADIAL:
            semantics.setdefault("radial_plane", cls._infer_radial_plane(node, manifest))
        
        # Inject parent and reference context into semantics for resolvers
        if parent:
            if parent.geometry:
                semantics["parent_primitive"] = parent.geometry.primitive.value
            semantics["parent_label"] = parent.label
            if parent.kind in (NodeKind.ASSEMBLY, NodeKind.MODEL):
                for sib_id in parent.children_ids:
                    if sib_id != node.node_id:
                        sib = manifest.nodes.get(sib_id)
                        if sib and sib.attachment and sib.attachment.socket_type == SocketType.ROOT:
                            if sib.geometry:
                                semantics["parent_primitive"] = sib.geometry.primitive.value
                            semantics["parent_label"] = sib.label
                            break

        # Resolve based on socket type (legacy path)
        resolver = cls._get_resolver(socket)
        resolved = resolver(parent_bbox, child_bbox, semantics, node)
        _END_SOCKETS = {
            SocketType.FRONT_END, SocketType.BACK_END,
            SocketType.LEFT_END, SocketType.RIGHT_END,
            SocketType.TOP_END, SocketType.BOTTOM_END,
        }
        if socket in _END_SOCKETS and parent and parent.geometry:
            prim = parent.geometry.primitive
            stage2 = parent.stage_outputs.get("stage2", {})
            if prim in {PrimitiveType.CYLINDER, PrimitiveType.CONE, PrimitiveType.CAPSULE, PrimitiveType.PRISM}:
                d = float(stage2.get("depth", 1.0))
                p1 = [0.0, 0.0, -d / 2.0]
                p2 = [0.0, 0.0, +d / 2.0]
                parent_rot = [0.0, 0.0, 0.0]
                if hasattr(parent, "transform_state") and parent.transform_state and parent.transform_state.world_matrix:
                    parent_rot = list(parent.transform_state.world_matrix.rotation)
                elif getattr(parent, "attachment", None) and getattr(parent.attachment, "rotation", None):
                    parent_rot = list(parent.attachment.rotation)
                elif "stage4" in getattr(parent, "stage_outputs", {}) and "rotation" in parent.stage_outputs["stage4"]:
                    parent_rot = list(parent.stage_outputs["stage4"]["rotation"])
                
                rot_mat = _mat4_from_trs([0.0, 0.0, 0.0], parent_rot, [1.0, 1.0, 1.0])
                v1 = _mat4_transform_vector(rot_mat, p1)
                v2 = _mat4_transform_vector(rot_mat, p2)
                
                if socket == SocketType.FRONT_END:
                    chosen = p1 if v1[1] < v2[1] else p2
                elif socket == SocketType.BACK_END:
                    chosen = p1 if v1[1] > v2[1] else p2
                elif socket == SocketType.LEFT_END:
                    chosen = p1 if v1[0] < v2[0] else p2
                elif socket == SocketType.RIGHT_END:
                    chosen = p1 if v1[0] > v2[0] else p2
                elif socket == SocketType.TOP_END:
                    chosen = p1 if v1[2] > v2[2] else p2
                elif socket == SocketType.BOTTOM_END:
                    chosen = p1 if v1[2] < v2[2] else p2
                else:
                    chosen = p2
                
                resolved.offset = list(chosen)
                resolved.resolution_method = f"{socket.value}:oriented_cylinder_end"

        contract_orientation = str(
            node.stage_outputs.get("spatial_contract", {}).get("orientation", "")
        ).lower()
        hint_axis = node.stage_outputs.get("decomposition_hint", {}).get("length_axis")
        is_horizontal_contract = (
            contract_orientation == "horizontal"
            or hint_axis in ("x", "y")
        )
        if (
            is_horizontal_contract
            and node.geometry
            and node.geometry.primitive in {
                PrimitiveType.CYLINDER, PrimitiveType.CONE,
                PrimitiveType.CAPSULE, PrimitiveType.PRISM,
            }
        ):
            # Axis-based primitives are Z-long in Blender.  Preserve the
            # resolver's in-plane heading while rotating the long axis into
            # the declared XY plane.
            if socket in (SocketType.FRONT_FACE, SocketType.BACK_FACE, SocketType.FRONT_CENTER, SocketType.BACK_CENTER) or hint_axis == "y":
                resolved.rotation = [math.pi / 2.0, 0.0, resolved.rotation[2]]
            else:
                resolved.rotation = [0.0, math.pi / 2.0, resolved.rotation[2]]
        elif (
            (node.geometry and node.geometry.primitive in {PrimitiveType.TORUS, PrimitiveType.CIRCLE})
            or contract_orientation == "flat_horizontal"
        ):
            # Torus/circle primitives have normal along local Z (flat horizontal in local frame).
            # If parent has pitch/roll (e.g. cylindrical arm pointing along X or Y),
            # compensate child's local rotation so its normal remains vertical in world space.
            yaw = resolved.rotation[2] if len(resolved.rotation) > 2 else 0.0
            desired_child_world = cls._build_world_matrix([0.0, 0.0, 0.0], [0.0, 0.0, yaw])
            parent_world = None
            if hasattr(parent, "transform_state") and parent.transform_state and parent.transform_state.world_matrix:
                parent_world = parent.transform_state.world_matrix
            elif getattr(parent, "attachment", None) and getattr(parent.attachment, "rotation", None):
                parent_world = cls._build_world_matrix([0.0, 0.0, 0.0], list(parent.attachment.rotation))
            elif "stage4" in getattr(parent, "stage_outputs", {}) and "rotation" in parent.stage_outputs["stage4"]:
                parent_world = cls._build_world_matrix([0.0, 0.0, 0.0], list(parent.stage_outputs["stage4"]["rotation"]))
            else:
                # Fallback to decomposition hint length_axis if available (e.g. unit tests where Stage 4 hasn't run on parent)
                parent_axis = parent.stage_outputs.get("decomposition_hint", {}).get("length_axis")
                if parent_axis == "x":
                    parent_world = cls._build_world_matrix([0.0, 0.0, 0.0], [0.0, math.pi / 2.0, 0.0])
                elif parent_axis == "y":
                    parent_world = cls._build_world_matrix([0.0, 0.0, 0.0], [math.pi / 2.0, 0.0, 0.0])
            
            if parent_world:
                local_tf = cls._world_to_parent_local(parent_world, desired_child_world)
                resolved.rotation = list(local_tf.rotation)

        # FIX: Add logging for PART node position computation
        logger.info(
            f"Stage4 PART: {node.label} socket={socket.value} "
            f"offset={resolved.offset} rotation={resolved.rotation} "
            f"parent_bbox=({parent_bbox.min_x:.3f},{parent_bbox.max_x:.3f}) "
            f"child_bbox=({child_bbox.min_x:.3f},{child_bbox.max_x:.3f})"
        )
        
        # Create AttachmentSolution from resolved transform (bridge)
        solution = AttachmentSolution.from_resolved_transform(
            resolved=resolved,
            parent_id=parent_id,
            child_id=node.node_id,
            socket_type=socket,
        )
        
        # Validate scale invariant (dimensions ≠ transform scale)
        if not validate_unit_scale(solution.local_transform):
            logger.warning(
                f"Non-unit scale in {node.label}: {solution.local_transform.scale}. "
                f"Use geometry dimensions, not transform scale."
            )
        
        return resolved, solution

    @classmethod
    def _resolve_endpoint_constraint(
        cls, node: ManifestNode, manifest: BuildManifest, constraint: Dict[str, Any]
    ) -> ResolvedTransform:
        """Resolve an elongated primitive between deterministic attachment endpoints."""
        if constraint.get("kind") != "radial_strut":
            raise Stage4Error(f"Unsupported endpoint constraint on {node.label}")
        if not node.geometry or node.geometry.primitive not in {PrimitiveType.CYLINDER, PrimitiveType.CONE}:
            raise Stage4Error("radial_strut requires a cylinder or cone")
        stage2 = node.stage_outputs.get("stage2", {})
        length = float(stage2.get("depth") or 0.0)
        if length <= 0:
            raise Stage4Error("radial_strut requires positive Stage 2 depth")
        hub = manifest.nodes.get(constraint.get("hub_node_id"))
        if not hub or not hub.geometry or "stage2" not in hub.stage_outputs:
            raise Stage4Error("radial_strut hub geometry is unavailable")
        # Accessing the hub geometry here is intentional validation: the
        # assembly must have an actual anchor, not merely a descriptive name.
        BBox.from_geometry(hub.geometry, hub.stage_outputs["stage2"])
        index = int(constraint.get("radial_index", 0))
        count = max(1, int(constraint.get("radial_count", 1)))
        angle = (2.0 * math.pi * index) / count
        spread = min(length * float(constraint.get("spread_ratio", 0.62)), length * 0.92)
        drop = math.sqrt(max(0.0, length * length - spread * spread))
        # The radial child assembly has been placed at the hub bottom by the
        # structural planner, so these endpoints are in its local frame.
        end = [spread * math.cos(angle), spread * math.sin(angle), -drop]
        center = [component * 0.5 for component in end]
        # Rotate local +Z onto the endpoint vector.  A cylinder is radially
        # symmetric, so its roll is immaterial.
        yaw = math.atan2(end[1], end[0])
        pitch = math.acos(max(-1.0, min(1.0, end[2] / length)))
        return ResolvedTransform(
            offset=center,
            rotation=[0.0, pitch, yaw],
            resolution_method=f"ENDPOINT:radial_strut:{index}/{count}",
        )
    
    @classmethod
    def run_assembly(
        cls,
        node: ManifestNode,
        manifest: BuildManifest,
        parent_world: Optional[WorldMatrix] = None,
    ) -> AttachmentSolution:
        """Resolve local_transform for an ASSEMBLY or MODEL node.
        
        Phase 3.5: Computes assembly's local_transform relative to node.parent_id.
        
        The assembly's transform is computed by:
        1. Finding the semantic attachment reference (ROOT sibling's geometry)
        2. Computing the desired assembly WORLD position from that reference
        3. Converting to parent-local via: local = inverse(parent_world) @ child_world
        
        This ensures the local_transform is genuinely relative to the hierarchy
        parent, not to the ROOT sibling geometry.
        
        Args:
            node: The ASSEMBLY or MODEL node to resolve
            manifest: Build manifest (for parent/sibling context)
            parent_world: Parent's world matrix (required for non-ROOT sockets)
            
        Returns:
            AttachmentSolution with computed local_transform
            
        Raises:
            Stage4Error: If resolution fails
        """
        if node.kind not in (NodeKind.ASSEMBLY, NodeKind.MODEL):
            raise Stage4Error(f"run_assembly only handles ASSEMBLY/MODEL, got {node.kind.value}")
        
        socket = node.attachment.socket_type if node.attachment else SocketType.ROOT
        parent_id = node.parent_id or ""
        
        # ROOT socket - identity transform (assembly origin = parent origin)
        if socket == SocketType.ROOT:
            return AttachmentSolution(
                parent_id=parent_id,
                child_id=node.node_id,
                parent_socket="ROOT",
                local_transform=LocalTransform.identity(),
                source="ASSEMBLY:ROOT",
            )
        
        # Non-ROOT assembly requires parent world matrix for proper conversion.
        # If not yet available (parent not resolved), defer like the no-ref-bbox path
        # so _ensure_assembly_transform retries rather than silently placing at origin.
        if parent_world is None:
            logger.debug(
                f"Assembly {node.label}: non-ROOT socket ({socket.value}) but parent_world not yet available — deferring"
            )
            return AttachmentSolution(
                parent_id=parent_id,
                child_id=node.node_id,
                parent_socket=socket.value,
                local_transform=LocalTransform.identity(),
                source=f"ASSEMBLY:{socket.value}:deferred_no_ref_bbox",
                confidence="low",
            )
        
        if not node.parent_id:
            raise Stage4Error(f"Assembly {node.label} has non-ROOT socket but no parent")
        
        parent_node = manifest.nodes.get(node.parent_id)
        if not parent_node:
            raise Stage4Error(f"Assembly {node.label}'s parent not found")

        # Assemblies do not pass through Stage 3 individually, so repeated
        # groups (RADIAL, RADIAL_BRIDGE, ARRAY_MEMBER) must derive deterministic
        # indices from their sibling order.
        if socket in (SocketType.RADIAL, SocketType.RADIAL_BRIDGE, SocketType.ARRAY_MEMBER):
            cls._populate_assembly_repeated_semantics(node, parent_node, manifest, socket)
        
        # Find the reference sibling for attachment.
        # For TOP_CENTER: use the sibling with the highest max_z (the tallest part,
        # e.g. the vertical rod, not the base). For all other sockets: use the
        # first ROOT-socket sibling as before.
        ref_bbox = None
        ref_sibling = None
        explicit_reference_id = getattr(node.attachment, "reference_node_id", None)
        if explicit_reference_id:
            ref_sibling = manifest.nodes.get(explicit_reference_id)
            if ref_sibling is None:
                raise Stage4Error(
                    f"Assembly {node.label} references missing node id {explicit_reference_id}"
                )
            ref_bbox = (
                cls._get_root_child_bbox(ref_sibling, manifest)
                if ref_sibling.kind == NodeKind.ASSEMBLY else None
            )
            if ref_bbox is None and ref_sibling.kind == NodeKind.PART:
                if ref_sibling.geometry and "stage2" in ref_sibling.stage_outputs:
                    ref_bbox = BBox.from_geometry(
                        ref_sibling.geometry, ref_sibling.stage_outputs["stage2"]
                    )
        else:
            # Compatibility fallback for legacy plans.  New plans should emit
            # attach_to so placement is independent of sibling order and ROOT
            # status.
            for sibling_id in parent_node.children_ids:
                if sibling_id == node.node_id:
                    continue
                sibling = manifest.nodes.get(sibling_id)
                if not sibling or not sibling.attachment:
                    continue
                if sibling.attachment.socket_type == SocketType.ROOT:
                    candidate_bbox = cls._get_root_child_bbox(sibling, manifest) if sibling.kind == NodeKind.ASSEMBLY else None
                    if candidate_bbox is None and sibling.kind == NodeKind.PART:
                        if sibling.geometry and "stage2" in sibling.stage_outputs:
                            candidate_bbox = BBox.from_geometry(sibling.geometry, sibling.stage_outputs["stage2"])
                    if candidate_bbox is None:
                        continue
                    if socket == SocketType.TOP_CENTER:
                        if ref_bbox is None or candidate_bbox.max_z > ref_bbox.max_z:
                            ref_bbox = candidate_bbox
                            ref_sibling = sibling
                    elif ref_sibling is None:
                        ref_bbox = candidate_bbox
                        ref_sibling = sibling
        
        if ref_bbox is None:
            # No reference geometry available yet — the ROOT sibling hasn't been
            # built. Return identity so the assembly sits at the parent origin;
            # _ensure_assembly_transform will recompute once geometry is ready
            # (revision-gated, not the false-positive identity check).
            logger.warning(
                f"Assembly {node.label}: no reference bbox found — ROOT sibling not built yet. "
                f"Returning identity; will recompute when geometry is available."
            )
            return AttachmentSolution(
                parent_id=parent_id,
                child_id=node.node_id,
                parent_socket=socket.value,
                local_transform=LocalTransform.identity(),
                source=f"ASSEMBLY:{socket.value}:deferred_no_ref_bbox",
                confidence="low",
            )
        
        # Compute the attachment point on the reference sibling's surface.
        # ref_attachment_local is expressed in the parent's coordinate frame
        # (the ROOT sibling has identity transform relative to its parent, so
        # its local space IS the parent's local space).
        #
        # Invariant (Phase C): the assembly origin is determined solely by its
        # parent attachment point. The ROOT child inside this assembly receives
        # a non-identity local transform if it needs to sit offset from the
        # assembly origin — we do NOT shift the assembly origin to accommodate
        # child geometry extents here.
        ref_attachment_local = [0.0, 0.0, 0.0]

        # The assembly origin is not automatically the contact point of its
        # ROOT mesh.  Use its evaluated local aggregate so a horizontal tube
        # placed on a pedestal rests *above* it instead of intersecting it.
        child_contact_bbox = cls._get_assembly_aggregate_bbox(node, manifest) or cls._get_root_child_bbox(node, manifest)

        if socket == SocketType.TOP_CENTER:
            ref_attachment_local[2] = ref_bbox.max_z - (child_contact_bbox.min_z if child_contact_bbox else 0.0)
            logger.info(f"Stage4 TOP_CENTER: {node.label} ref_bbox.max_z={ref_bbox.max_z} ref_attachment={ref_attachment_local}")
        elif socket == SocketType.BOTTOM_CENTER:
            ref_attachment_local[2] = ref_bbox.min_z - (child_contact_bbox.max_z if child_contact_bbox else 0.0)
        elif socket == SocketType.FRONT_CENTER:
            ref_attachment_local[1] = ref_bbox.min_y
            logger.info(f"Stage4 FRONT_CENTER: {node.label} ref_bbox.min_y={ref_bbox.min_y} ref_attachment={ref_attachment_local}")
        elif socket == SocketType.BACK_CENTER:
            ref_attachment_local[1] = ref_bbox.max_y
        elif socket == SocketType.LEFT_CENTER:
            ref_attachment_local[0] = ref_bbox.min_x
        elif socket == SocketType.RIGHT_CENTER:
            ref_attachment_local[0] = ref_bbox.max_x
        else:
            # Delegate to the PART resolver for this socket type — it already
            # handles every socket in the dispatch table.  We compute the
            # local_transform in the parent's coordinate frame by:
            #   1. Getting the parent bbox (same logic as PART nodes)
            #   2. Running the PART resolver to get a local offset
            #   3. Converting that offset to a world position via parent_world
            #   4. Converting back to parent-local via matrix inversion
            # This is identical to what PART nodes do; assemblies just need the
            # extra world→local round-trip because run_assembly() works in world
            # space while the PART resolvers work in parent-local space directly.
            try:
                resolver = cls._get_resolver(socket)
                parent_node = manifest.nodes.get(node.parent_id)
                if parent_node is None:
                    raise Stage4Error(f"Assembly {node.label}: parent node not found")
                parent_bbox = cls._get_parent_bbox(parent_node, manifest, node)
                # Assemblies must contribute their real footprint.  The old
                # generic 0.2m cube made a blade subassembly and its cage
                # receive the same front-depth, even when their meshes had
                # very different thicknesses.
                child_bbox = cls._get_assembly_aggregate_bbox(node, manifest) or cls._get_child_bbox(node)
                semantics = dict(node.stage_outputs.get("stage3", {}))
                if socket == SocketType.RADIAL:
                    semantics.setdefault("radial_plane", cls._infer_radial_plane(node, manifest))
                resolved = resolver(parent_bbox, child_bbox, semantics, node)
                # resolved.offset is in parent-local space — lift to world then
                # convert back so the caller gets a proper LocalTransform.
                desired_world_pos = parent_world.transform_point(resolved.offset)
                desired_world_rot = [
                    list(parent_world.rotation)[i] + resolved.rotation[i]
                    for i in range(3)
                ]
                child_world = cls._build_world_matrix(desired_world_pos, desired_world_rot)
                local_transform = cls._world_to_parent_local(parent_world, child_world)
                logger.info(
                    f"ASSEMBLY Stage4 (delegated {socket.value}): {node.label} -> "
                    f"local={[round(p, 4) for p in local_transform.position]}"
                )
                return AttachmentSolution(
                    parent_id=parent_id,
                    child_id=node.node_id,
                    parent_socket=socket.value,
                    local_transform=local_transform,
                    source=f"ASSEMBLY:delegated:{socket.value}",
                )
            except Exception as _e:
                logger.error(
                    f"Assembly {node.label}: delegated resolver for {socket.value} failed: {_e}"
                )
                raise Stage4Error(
                    f"Assembly {node.label}: delegated resolver for {socket.value} failed: {_e}"
                ) from _e

        # Step 1: desired world position = parent_world @ ref_attachment_local
        desired_world_pos = parent_world.transform_point(ref_attachment_local)
        desired_world_rot = list(parent_world.rotation)  # inherit parent orientation
        
        # Step 2: build desired child world matrix
        child_world = cls._build_world_matrix(desired_world_pos, desired_world_rot)
        
        # Step 3: convert to parent-local via proper matrix inversion
        #   child_local = inverse(parent_world) @ child_world
        local_transform = cls._world_to_parent_local(parent_world, child_world)
        
        logger.info(
            f"ASSEMBLY Stage4 (v4): {node.label} ({socket.value}) -> "
            f"ref_bbox=[{ref_bbox.size_x:.3f}x{ref_bbox.size_y:.3f}x{ref_bbox.size_z:.3f}], "
            f"ref_local={[round(o, 4) for o in ref_attachment_local]}, "
            f"desired_world={[round(p, 4) for p in desired_world_pos]}, "
            f"local={[round(p, 4) for p in local_transform.position]}"
        )
        
        return AttachmentSolution(
            parent_id=parent_id,
            child_id=node.node_id,
            parent_socket=socket.value,
            local_transform=local_transform,
            source=f"ASSEMBLY:v4:{socket.value}",
        )
    
    @classmethod
    def _find_root_part_in_assembly(cls, assembly: ManifestNode, manifest: BuildManifest) -> Optional[ManifestNode]:
        """Find the ROOT PART inside an assembly (recursive)."""
        for cid in assembly.children_ids:
            child = manifest.nodes.get(cid)
            if not child:
                continue
            if child.kind == NodeKind.PART:
                if child.attachment and child.attachment.socket_type == SocketType.ROOT:
                    return child
            elif child.kind == NodeKind.ASSEMBLY:
                if child.attachment and child.attachment.socket_type == SocketType.ROOT:
                    return cls._find_root_part_in_assembly(child, manifest)
        return None
    
    @classmethod
    def _get_parent_bbox(cls, parent: ManifestNode, manifest: BuildManifest, node: ManifestNode) -> BBox:
        """Get parent's bounding box for computing child offsets.
        
        CRITICAL: For ASSEMBLY/MODEL parents, we need to find the ROOT child's
        bounding box, since that's the actual geometry that siblings attach to.
        The ASSEMBLY itself is just a logical container with no geometry.
        
        SPECIAL CASE: For CORNER sockets (like table legs), the legs are children
        of leg_assembly, but they need to be positioned relative to the TABLETOP,
        not the leg_assembly. We find the sibling ROOT assembly's geometry.
        
        SPECIAL CASE: For INSET sockets (like glass panels), they fill a hole
        in the ROOT sibling, so we use the ROOT sibling's bbox.
        """
        # Special handling for CORNER sockets - find the reference surface
        if node.attachment and node.attachment.socket_type == SocketType.CORNER:
            ref_bbox = cls._find_corner_reference_bbox(parent, manifest)
            if ref_bbox:
                return ref_bbox
        
        # Special handling for INSET sockets - find the ROOT sibling (the part with the hole)
        if node.attachment and node.attachment.socket_type == SocketType.INSET:
            root_bbox = cls._find_root_sibling_bbox(parent, manifest, node)
            if root_bbox:
                return root_bbox
        
        # For ASSEMBLY/MODEL parents, choose bbox strategy based on socket type.
        # Face sockets (FRONT_FACE, FRONT_CENTER, etc.) and RADIAL attach to a
        # specific surface of the ROOT part, not the whole aggregate. Using the
        # aggregate bbox here causes huge offsets because blades/cage extend far
        # beyond the motor housing in -Y. Use ROOT-only bbox for these sockets.
        if parent.kind in (NodeKind.ASSEMBLY, NodeKind.MODEL):
            socket = node.attachment.socket_type if node.attachment else None
            _SURFACE_SOCKETS = {
                SocketType.FRONT_FACE, SocketType.BACK_FACE,
                SocketType.LEFT_FACE, SocketType.RIGHT_FACE,
                SocketType.TOP_FACE, SocketType.BOTTOM_FACE,
                SocketType.FRONT_CENTER, SocketType.BACK_CENTER,
                SocketType.LEFT_CENTER, SocketType.RIGHT_CENTER,
                SocketType.TOP_CENTER, SocketType.BOTTOM_CENTER,
                SocketType.RADIAL,
            }
            if socket in _SURFACE_SOCKETS:
                # Use only the ROOT child's intrinsic geometry, not the aggregate
                root_bbox = cls._get_root_only_bbox(parent, manifest)
                if root_bbox:
                    return root_bbox
            else:
                root_bbox = cls._get_root_child_bbox(parent, manifest)
                if root_bbox:
                    return root_bbox

            # If parent assembly has no ROOT child of its own, resolve against
            # the reference surface (e.g. chassis/tabletop) from the parent's host
            frame_bbox = cls._find_corner_reference_bbox(parent, manifest)
            if frame_bbox:
                return frame_bbox
        
        # Compute from geometry + stage2 (for PART parents) - already local space
        if parent.geometry and "stage2" in parent.stage_outputs:
            return BBox.from_geometry(parent.geometry, parent.stage_outputs["stage2"])
        
        # No geometry available — raise rather than silently returning a wrong bbox.
        # _world_bbox_to_local is unreliable when world_position is absent (new
        # transform path) and produces incorrect offsets when it is present but
        # stale. Callers must ensure stage2 outputs are populated before Stage 4.
        raise Stage4Error(
            f"No geometry available for parent '{parent.label}' "
            f"(kind={parent.kind.value}). Ensure Stage 2 has run and "
            f"stage_outputs['stage2'] is populated before Stage 4."
        )
    
    @classmethod
    def _find_root_sibling_bbox(cls, parent: ManifestNode, manifest: BuildManifest, node: ManifestNode) -> Optional[BBox]:
        """Find the ROOT sibling's bbox for INSET positioning."""
        if not parent.children_ids:
            return None
        
        for sib_id in parent.children_ids:
            if sib_id == node.node_id:
                continue
            sib = manifest.nodes.get(sib_id)
            if sib and sib.attachment and sib.attachment.socket_type == SocketType.ROOT:
                if sib.geometry and "stage2" in sib.stage_outputs:
                    logger.info(f"INSET reference: using ROOT sibling {sib.label}'s geometry")
                    return BBox.from_geometry(sib.geometry, sib.stage_outputs["stage2"])
                if sib.bounding_box:
                    logger.info(f"INSET reference: using ROOT sibling {sib.label}'s bbox (converted to local)")
                    if sib.transform_state and sib.transform_state.world_matrix is not None:
                        world_pos = list(sib.transform_state.world_matrix.position)
                    else:
                        world_pos = sib.world_position
                    return cls._world_bbox_to_local(sib.bounding_box, world_pos)
        
        return None
    
    @classmethod
    def _find_corner_reference_bbox(cls, parent: ManifestNode, manifest: BuildManifest) -> Optional[BBox]:
        """Find the reference surface bbox for CORNER socket positioning."""
        if parent.kind == NodeKind.ASSEMBLY and parent.parent_id:
            grandparent = manifest.nodes.get(parent.parent_id)
            if grandparent and grandparent.kind in (NodeKind.MODEL, NodeKind.ASSEMBLY):
                for sibling_id in grandparent.children_ids:
                    sibling = manifest.nodes.get(sibling_id)
                    if sibling and sibling.attachment and sibling.attachment.socket_type == SocketType.ROOT:
                        if sibling.kind == NodeKind.ASSEMBLY:
                            root_bbox = cls._get_root_child_bbox(sibling, manifest)
                            if root_bbox:
                                logger.info(f"CORNER reference: using {sibling.label}'s ROOT child bbox [{root_bbox.size_x:.3f}x{root_bbox.size_y:.3f}x{root_bbox.size_z:.3f}]")
                                return root_bbox
                        elif sibling.kind == NodeKind.PART:
                            if sibling.geometry and "stage2" in sibling.stage_outputs:
                                return BBox.from_geometry(sibling.geometry, sibling.stage_outputs["stage2"])
                            if sibling.bounding_box:
                                if sibling.transform_state and sibling.transform_state.world_matrix is not None:
                                    world_pos = list(sibling.transform_state.world_matrix.position)
                                else:
                                    world_pos = sibling.world_position
                                return cls._world_bbox_to_local(sibling.bounding_box, world_pos)
        
        return None
    
    @classmethod
    def _get_assembly_aggregate_bbox(cls, assembly: ManifestNode, manifest: BuildManifest) -> Optional[BBox]:
        """Compute aggregate BBox for an assembly by unioning all children's local bboxes.

        Each child's intrinsic bbox (from Stage 2 geometry, in child-local space) is
        transformed into assembly-local space via the child's local_transform, then
        all eight corners are unioned to produce the assembly's true physical footprint.

        Invariant: result is expressed in assembly-local coordinates.
        Falls back to ROOT-child-only bbox when no child has stage2 data.
        """
        if not assembly.children_ids:
            return None

        all_corners: List[List[float]] = []

        for cid in assembly.children_ids:
            child = manifest.nodes.get(cid)
            if not child or not child.geometry or "stage2" not in child.stage_outputs:
                continue
            child_bbox = BBox.from_geometry(child.geometry, child.stage_outputs["stage2"])
            # Get child's local transform relative to assembly
            if child.transform_state and child.transform_state.is_resolved:
                child_local_mat = child.transform_state.local_transform.to_matrix()
            else:
                # Child not yet resolved — treat as identity (at assembly origin)
                from ..transforms import _identity_4x4
                child_local_mat = _identity_4x4()
            # Transform all 8 corners of child bbox into assembly-local space
            for cx in (child_bbox.min_x, child_bbox.max_x):
                for cy in (child_bbox.min_y, child_bbox.max_y):
                    for cz in (child_bbox.min_z, child_bbox.max_z):
                        from ..transforms import _mat4_transform_point
                        pt = _mat4_transform_point(child_local_mat, [cx, cy, cz])
                        all_corners.append(pt)

        if not all_corners:
            # No stage2 data available — fall back to ROOT child only
            for cid in assembly.children_ids:
                child = manifest.nodes.get(cid)
                if child and child.attachment and child.attachment.socket_type == SocketType.ROOT:
                    if child.geometry and "stage2" in child.stage_outputs:
                        return BBox.from_geometry(child.geometry, child.stage_outputs["stage2"])
            return None

        xs = [p[0] for p in all_corners]
        ys = [p[1] for p in all_corners]
        zs = [p[2] for p in all_corners]
        return BBox(
            min_x=min(xs), max_x=max(xs),
            min_y=min(ys), max_y=max(ys),
            min_z=min(zs), max_z=max(zs),
        )

    @classmethod
    def _get_root_only_bbox(cls, assembly: ManifestNode, manifest: BuildManifest) -> Optional[BBox]:
        """Return the intrinsic bbox of the ROOT-socket child only (no aggregate).

        Used for face/radial sockets where the child attaches to a specific
        surface of the ROOT part, not the whole assembly footprint.
        """
        for cid in assembly.children_ids:
            child = manifest.nodes.get(cid)
            if not child or not child.attachment:
                continue
            if child.attachment.socket_type == SocketType.ROOT:
                if child.kind == NodeKind.PART and child.geometry and "stage2" in child.stage_outputs:
                    return BBox.from_geometry(child.geometry, child.stage_outputs["stage2"])
                if child.kind == NodeKind.ASSEMBLY:
                    return cls._get_root_only_bbox(child, manifest)
        return None

    @classmethod
    def _get_root_child_bbox(cls, assembly: ManifestNode, manifest: BuildManifest) -> Optional[BBox]:
        """Kept for call sites that have not yet migrated to _get_assembly_aggregate_bbox."""
        return cls._get_assembly_aggregate_bbox(assembly, manifest)
    
    @classmethod
    def _world_bbox_to_local(cls, bbox: Dict[str, List[float]], world_pos: Optional[List[float]]) -> BBox:
        """Convert world-space bounding box to local space.
        
        Blender returns bbox in world coordinates. For Stage 4 offset calculations,
        we need local coordinates (relative to object origin).
        
        IMPORTANT: Callers must prefer BBox.from_geometry() (Stage 2 data) over
        this method whenever stage2 outputs are available. This method is only
        used as a fallback when only a Blender-derived world bbox is available.
        
        world_pos must be the node's actual world position. Callers should source
        this from transform_state.world_matrix.position (authoritative) rather
        than the legacy node.world_position field, which may be stale or absent
        for nodes built via the new hierarchical transform path.
        """
        if world_pos is None:
            # Cannot safely convert — the node was built via the new transform path
            # and world_position was never written. Return the bbox as-is (world space)
            # and log a warning so callers know the result may be offset.
            logger.warning(
                "_world_bbox_to_local: world_pos is None — bbox is in world space but "
                "will be treated as local. Prefer BBox.from_geometry() for accuracy."
            )
            world_pos = [0.0, 0.0, 0.0]
        
        return BBox(
            min_x=bbox["min"][0] - world_pos[0],
            max_x=bbox["max"][0] - world_pos[0],
            min_y=bbox["min"][1] - world_pos[1],
            max_y=bbox["max"][1] - world_pos[1],
            min_z=bbox["min"][2] - world_pos[2],
            max_z=bbox["max"][2] - world_pos[2],
        )
    
    @classmethod
    def _get_child_bbox(cls, node: ManifestNode) -> BBox:
        """Get child's bounding box from its geometry."""
        if node.geometry and "stage2" in node.stage_outputs:
            return BBox.from_geometry(node.geometry, node.stage_outputs["stage2"])
        return BBox(min_x=-0.1, max_x=0.1, min_y=-0.1, max_y=0.1, min_z=-0.1, max_z=0.1)
    
    @classmethod
    def _get_resolver(cls, socket: SocketType):
        """Get the resolver function for a socket type."""
        resolvers = {
            SocketType.ROOT: cls._resolve_root,
            SocketType.TOP_CENTER: cls._resolve_top_center,
            SocketType.BOTTOM_CENTER: cls._resolve_bottom_center,
            SocketType.FRONT_CENTER: cls._resolve_front_center,
            SocketType.BACK_CENTER: cls._resolve_back_center,
            SocketType.LEFT_CENTER: cls._resolve_left_center,
            SocketType.RIGHT_CENTER: cls._resolve_right_center,
            SocketType.CORNER: cls._resolve_corner,
            SocketType.EDGE: cls._resolve_edge,
            SocketType.THROUGH_AXIS: cls._resolve_through_axis,
            SocketType.ARRAY_MEMBER: cls._resolve_array_member,
            SocketType.RADIAL: cls._resolve_radial,
            SocketType.BOOLEAN_CUT: cls._resolve_boolean_cut,
            SocketType.BOOLEAN_UNION: cls._resolve_boolean_union,
            SocketType.BOOLEAN_INTERSECT: cls._resolve_boolean_intersect,
            SocketType.INSET: cls._resolve_inset,
            # Face sockets
            SocketType.TOP_FACE: cls._resolve_top_face,
            SocketType.BOTTOM_FACE: cls._resolve_bottom_face,
            SocketType.FRONT_FACE: cls._resolve_front_face,
            SocketType.BACK_FACE: cls._resolve_back_face,
            SocketType.LEFT_FACE: cls._resolve_left_face,
            SocketType.RIGHT_FACE: cls._resolve_right_face,
            # End sockets
            SocketType.LEFT_END: cls._resolve_left_end,
            SocketType.RIGHT_END: cls._resolve_right_end,
            SocketType.TOP_END: cls._resolve_top_end,
            SocketType.BOTTOM_END: cls._resolve_bottom_end,
            SocketType.FRONT_END: cls._resolve_front_end,
            SocketType.BACK_END: cls._resolve_back_end,
            # Connector sockets (pass-1 placeholders, real resolution in pass-2)
            SocketType.RADIAL_BRIDGE: cls._resolve_radial_bridge_pass1,
            SocketType.STRUT: cls._resolve_strut_pass1,
            SocketType.BRIDGE: cls._resolve_bridge_pass1,
            SocketType.RELATIVE_TO: cls._resolve_relative_to_pass1,
        }
        resolver = resolvers.get(socket)
        if resolver is None:
            raise Stage4Error(
                f"No resolver for socket type {socket.value}. "
                f"This socket type must be added to Stage4Resolver._get_resolver() before use."
            )
        return resolver
    
    @classmethod
    def is_cross_reference_socket(cls, socket: SocketType) -> bool:
        """Check if socket type requires cross-reference resolution (pass 2)."""
        return socket in CROSS_REFERENCE_SOCKETS
    
    # ── Socket Resolvers ─────────────────────────────────────────────────
    
    @classmethod
    def _resolve_root(cls, parent: BBox, child: BBox, sem: Dict, node: ManifestNode) -> ResolvedTransform:
        """ROOT: No offset, at origin."""
        return ResolvedTransform(resolution_method="ROOT")
    
    @classmethod
    def _resolve_top_center(cls, parent: BBox, child: BBox, sem: Dict, node: ManifestNode) -> ResolvedTransform:
        """TOP_CENTER: On top of parent (+Z), centered or symmetrically offset if bilateral."""
        offset_z = parent.max_z - child.min_z
        offset_x = 0.0
        offset_y = 0.0
        label = node.label.lower()
        if "left" in label:
            offset_x = parent.min_x * 0.5
        elif "right" in label:
            offset_x = parent.max_x * 0.5
        if "front" in label:
            offset_y = parent.min_y * 0.5
        elif "back" in label or "rear" in label:
            offset_y = parent.max_y * 0.5
        return ResolvedTransform(
            offset=[offset_x, offset_y, offset_z],
            resolution_method="TOP_CENTER" if (offset_x == 0.0 and offset_y == 0.0) else f"TOP_CENTER:bilateral_offset=[{offset_x:.3f},{offset_y:.3f}]",
        )
    
    @classmethod
    def _resolve_bottom_center(cls, parent: BBox, child: BBox, sem: Dict, node: ManifestNode) -> ResolvedTransform:
        """BOTTOM_CENTER: Below parent (-Z), centered or symmetrically offset if bilateral."""
        offset_z = parent.min_z - child.max_z
        offset_x = 0.0
        offset_y = 0.0
        label = node.label.lower()
        if "left" in label:
            offset_x = parent.min_x * 0.5
        elif "right" in label:
            offset_x = parent.max_x * 0.5
        if "front" in label:
            offset_y = parent.min_y * 0.5
        elif "back" in label or "rear" in label:
            offset_y = parent.max_y * 0.5
        return ResolvedTransform(
            offset=[offset_x, offset_y, offset_z],
            resolution_method="BOTTOM_CENTER" if (offset_x == 0.0 and offset_y == 0.0) else f"BOTTOM_CENTER:bilateral_offset=[{offset_x:.3f},{offset_y:.3f}]",
        )
    
    @classmethod
    def _resolve_front_center(cls, parent: BBox, child: BBox, sem: Dict, node: ManifestNode) -> ResolvedTransform:
        """FRONT_CENTER: In front of parent (-Y in Blender convention), centered.
        
        Note: Blender convention is -Y = front, +Y = back.
        """
        offset_y = parent.min_y - child.max_y
        return ResolvedTransform(
            offset=[0.0, offset_y, 0.0],
            resolution_method="FRONT_CENTER",
        )
    
    @classmethod
    def _resolve_back_center(cls, parent: BBox, child: BBox, sem: Dict, node: ManifestNode) -> ResolvedTransform:
        """BACK_CENTER: Behind parent (+Y in Blender convention), centered.
        
        Note: Blender convention is -Y = front, +Y = back.
        """
        offset_y = parent.max_y - child.min_y
        return ResolvedTransform(
            offset=[0.0, offset_y, 0.0],
            resolution_method="BACK_CENTER",
        )
    
    @classmethod
    def _resolve_left_center(cls, parent: BBox, child: BBox, sem: Dict, node: ManifestNode) -> ResolvedTransform:
        """LEFT_CENTER: Left of parent (-X), centered."""
        offset_x = parent.min_x - child.max_x
        return ResolvedTransform(
            offset=[offset_x, 0.0, 0.0],
            resolution_method="LEFT_CENTER",
        )
    
    @classmethod
    def _resolve_right_center(cls, parent: BBox, child: BBox, sem: Dict, node: ManifestNode) -> ResolvedTransform:
        """RIGHT_CENTER: Right of parent (+X), centered."""
        offset_x = parent.max_x - child.min_x
        return ResolvedTransform(
            offset=[offset_x, 0.0, 0.0],
            resolution_method="RIGHT_CENTER",
        )
    
    @classmethod
    def _resolve_corner(
        cls, 
        parent: BBox, 
        child: BBox, 
        sem: Dict, 
        node: ManifestNode,
        manifest: Optional[BuildManifest] = None,
    ) -> ResolvedTransform:
        """CORNER: At a corner of parent.
        
        For bottom corners: child hangs DOWN from parent (e.g., table legs)
        For top corners: child sits ON TOP of parent corner
        
        ALWAYS uses node label to determine corner (leg_front_left, leg_back_right, etc.)
        This is more reliable than LLM-generated semantic hints.
        
        CRITICAL: Uses BlenderAxis single source of truth for directional signs.
        DO NOT hardcode +Y/-Y assumptions here.
        """
        label = node.label.lower()
        
        # Determine left/right from label
        if "left" in label:
            is_left = True
        elif "right" in label:
            is_left = False
        else:
            is_left = True  # default
        
        # Determine front/back from label
        if "back" in label or "rear" in label:
            is_front = False
        elif "front" in label:
            is_front = True
        else:
            is_front = True  # default
        
        # Determine top/bottom (legs are usually bottom)
        if "top" in label or "upper" in label:
            is_bottom = False
        else:
            is_bottom = True  # default for legs
        
        # Use the provided parent bbox (which should already be the reference geometry)
        ref_bbox = parent
        
        # Inset factor (80% toward edge)
        inset_factor = 0.8
        
        # Use BlenderAxis single source of truth for corner offsets
        # This ensures consistency with DIRECTION_AXIS and all other resolvers
        offset_x, offset_y, _ = BlenderAxis.offset_for_corner(
            is_front=is_front,
            is_left=is_left,
            is_bottom=is_bottom,
            half_x=ref_bbox.size_x / 2,
            half_y=ref_bbox.size_y / 2,
            half_z=ref_bbox.size_z / 2,
            inset_factor=inset_factor,
        )
        
        # Z position - legs hang below the reference surface, tops sit above
        if is_bottom:
            offset_z = ref_bbox.min_z - (child.size_z / 2)
        else:
            offset_z = ref_bbox.max_z + (child.size_z / 2)
        
        pos_str = f"{'bottom' if is_bottom else 'top'}_{'front' if is_front else 'back'}_{'left' if is_left else 'right'}"
        
        logger.info(f"CORNER: {node.label} -> is_front={is_front}, is_left={is_left}, ref_bbox=[{ref_bbox.size_x:.3f}x{ref_bbox.size_y:.3f}x{ref_bbox.size_z:.3f}] -> {pos_str} @ [{offset_x:.3f}, {offset_y:.3f}, {offset_z:.3f}]")
        
        return ResolvedTransform(
            offset=[offset_x, offset_y, offset_z],
            resolution_method=f"CORNER:{pos_str}",
        )
    
    @classmethod
    def _resolve_edge(cls, parent: BBox, child: BBox, sem: Dict, node: ManifestNode) -> ResolvedTransform:
        """EDGE: Along an edge of parent, or connecting between parallel parts.
        
        For ladder rungs, shelf boards, etc. - uses label to determine Z position.
        """
        label = node.label.lower()
        
        # Check if this is a rung/step/board that should be positioned by height
        is_horizontal_connector = any(word in label for word in ["rung", "step", "board", "shelf", "crossbar"])
        
        if is_horizontal_connector:
            # Position based on label (bottom, middle, top, or numbered)
            if "bottom" in label or "lower" in label or "_1" in label:
                z_factor = 0.2  # 20% up from bottom
            elif "top" in label or "upper" in label or "_3" in label:
                z_factor = 0.8  # 80% up from bottom
            elif "middle" in label or "mid" in label or "_2" in label:
                z_factor = 0.5  # 50% (middle)
            else:
                z_factor = 0.5  # default to middle
            
            # Z position along parent height
            offset_z = parent.min_z + z_factor * parent.size_z
            
            # X centered, Y centered
            offset = [0.0, 0.0, offset_z]
            
            logger.info(f"EDGE (horizontal connector): {node.label} -> z_factor={z_factor} @ Z={offset_z:.3f}")
            
            return ResolvedTransform(
                offset=offset,
                resolution_method=f"EDGE:horizontal:{z_factor}",
            )
        
        # Standard edge positioning using semantic hints
        pos = sem.get("edge_position", "top_front")
        edge_offset = sem.get("edge_offset", 0.0)  # -1 to 1
        
        offset = [0.0, 0.0, 0.0]
        
        # Determine which edge
        if "top" in pos:
            offset[2] = parent.max_z
        elif "bottom" in pos:
            offset[2] = parent.min_z
        else:
            offset[2] = (parent.min_z + parent.max_z) / 2
        
        # FIXED: front = -Y (min_y), back = +Y (max_y) - uses BlenderAxis convention
        if "front" in pos:
            offset[1] = parent.min_y  # -Y = front
        elif "back" in pos:
            offset[1] = parent.max_y  # +Y = back
        else:
            offset[1] = (parent.min_y + parent.max_y) / 2
        
        if "left" in pos:
            offset[0] = parent.min_x
        elif "right" in pos:
            offset[0] = parent.max_x
        else:
            offset[0] = (parent.min_x + parent.max_x) / 2
        
        # Apply edge_offset along the edge
        if "top" in pos or "bottom" in pos:
            if "front" in pos or "back" in pos:
                offset[0] += edge_offset * (parent.size_x / 2)
            else:
                offset[1] += edge_offset * (parent.size_y / 2)
        else:
            offset[2] += edge_offset * (parent.size_z / 2)
        
        return ResolvedTransform(
            offset=offset,
            resolution_method=f"EDGE:{pos}:{edge_offset}",
        )
    
    @classmethod
    def _resolve_through_axis(cls, parent: BBox, child: BBox, sem: Dict, node: ManifestNode) -> ResolvedTransform:
        """THROUGH_AXIS: Passes through parent.
        
        Uses child geometry to compute embedment margin so thick parts
        don't poke through thin parents.
        """
        direction = sem.get("pierce_direction", "left_right")
        height = sem.get("height_hint", "center")
        
        offset = [0.0, 0.0, 0.0]
        rotation = [0.0, 0.0, 0.0]
        
        # Compute child radius for embedment margin
        # For cylinders piercing, the radius determines how much clearance we need
        child_radius = max(child.size_x, child.size_y) / 2
        
        # Height position with child-aware margin
        # Ensure the piercing part stays within parent bounds
        if height == "near_top":
            # Position near top but ensure child radius fits
            max_z = parent.max_z - child_radius
            offset[2] = max(parent.center[2], max_z * 0.85)
        elif height == "near_bottom":
            min_z = parent.min_z + child_radius
            offset[2] = min(parent.center[2], min_z + parent.size_z * 0.15)
        elif height == "top_third":
            offset[2] = parent.min_z + parent.size_z * 0.67
        elif height == "bottom_third":
            offset[2] = parent.min_z + parent.size_z * 0.33
        # else center = 0
        
        # Rotation based on pierce direction
        if direction == "front_back":
            rotation[0] = math.pi / 2  # Rotate to point along Y
        elif direction == "up_down":
            pass  # Default orientation (along Z)
        else:  # left_right is default (along X)
            rotation[1] = math.pi / 2  # Rotate to point along X
        
        return ResolvedTransform(
            offset=offset,
            rotation=rotation,
            resolution_method=f"THROUGH_AXIS:{direction}:{height}",
        )
    
    @classmethod
    def _resolve_array_member(cls, parent: BBox, child: BBox, sem: Dict, node: ManifestNode) -> ResolvedTransform:
        """ARRAY_MEMBER: Part of an array on parent surface."""
        axis = sem.get("array_axis", "x")
        count = sem.get("array_count", 1)
        index = sem.get("array_index", 0)
        spacing = sem.get("spacing_hint", "even")
        
        offset = [0.0, 0.0, 0.0]
        
        # Compute position along axis
        if count <= 1:
            t = 0.0
        else:
            t = index / (count - 1) if count > 1 else 0.0
            t = t * 2 - 1  # Map to -1..1
        
        # Apply spacing
        if spacing == "tight":
            t *= 0.6
        elif spacing == "spread":
            t *= 0.95
        elif spacing == "normal":
            t *= 0.8
        # "even" uses full range
        
        # Position along axis
        if axis == "x":
            offset[0] = t * (parent.size_x / 2)
            offset[2] = parent.max_z  # On top by default
        elif axis == "y":
            offset[1] = t * (parent.size_y / 2)
            offset[2] = parent.max_z
        else:  # z
            offset[2] = t * (parent.size_z / 2)
        
        return ResolvedTransform(
            offset=offset,
            resolution_method=f"ARRAY:{axis}:{index}/{count}",
        )
    
    @classmethod
    def _resolve_radial(cls, parent: BBox, child: BBox, sem: Dict, node: ManifestNode) -> ResolvedTransform:
        """RADIAL: Arrange in the declared (or structurally inferred) plane."""
        count = sem.get("radial_count", 4)
        index = sem.get("radial_index", 0)
        
        # Angle for this index
        angle = (2 * math.pi * index) / count
        
        plane = sem.get("radial_plane", "xy").lower()
        # A radial assembly's origin is not necessarily its geometric centre.
        # For an arm + terminal guard, the arm often runs from local X=0 to
        # +X while its root mesh extends slightly into -X.  Centre-to-centre
        # placement leaves a visible gap from the hub.  Attach the inward-most
        # local X edge to the parent surface instead; symmetric children retain
        # the former half-width behaviour because ``-min_x == size_x / 2``.
        inboard_extent = max(0.0, -child.min_x)
        if plane == "xz":
            # Front-facing (-Y) rotor/guard: rotate about Y and distribute
            # around the XZ plane.
            radius = max(parent.size_x, parent.size_z) / 2 + inboard_extent
            offset = [
                radius * math.cos(angle),
                # Put the rotor immediately in front of its reference body;
                # its thickness must not cut through the housing centreline.
                parent.min_y - child.size_y / 2,
                parent.center[2] + radius * math.sin(angle),
            ]
            rotation = [0.0, -angle, 0.0]
        else:
            # XY remains the default for top-down circular arrangements.
            primitive = getattr(getattr(node, "geometry", None), "primitive", None)
            prim_val = getattr(primitive, "value", str(primitive)).lower() if primitive else ""
            is_elongated_z = (
                prim_val in {"cylinder", "cone", "capsule"}
                and child.size_z > 1.25 * max(child.size_x, child.size_y)
            )
            if is_elongated_z:
                radius = max(parent.size_x, parent.size_y) / 2 + child.size_z / 2
                offset = [radius * math.cos(angle), radius * math.sin(angle), parent.center[2]]
                rotation = [0.0, math.pi / 2, angle]
            else:
                radius = max(parent.size_x, parent.size_y) / 2 + inboard_extent
                offset = [radius * math.cos(angle), radius * math.sin(angle), parent.center[2]]
                rotation = [0.0, 0.0, angle]
        
        return ResolvedTransform(
            offset=offset,
            rotation=rotation,
            resolution_method=f"RADIAL:{plane}:{index}/{count}",
        )

    @classmethod
    def _infer_radial_plane(cls, node: ManifestNode, manifest: BuildManifest) -> str:
        """Use XZ for front-facing rotor groups; retain XY for explicit top-down layouts."""
        parent = manifest.nodes.get(node.parent_id) if node.parent_id else None
        if parent and parent.attachment and parent.attachment.socket_type in {
            SocketType.FRONT_FACE, SocketType.BACK_FACE,
            SocketType.FRONT_CENTER, SocketType.BACK_CENTER,
        }:
            return "xz"
        if parent:
            # A head/body may be TOP_CENTER-mounted while its hub/enclosure is
            # front-mounted.  Its radial blade siblings must still use that
            # same front plane.
            for sibling_id in parent.children_ids:
                sibling = manifest.nodes.get(sibling_id)
                if sibling and sibling.attachment and sibling.attachment.socket_type in {
                    SocketType.FRONT_FACE, SocketType.BACK_FACE,
                    SocketType.FRONT_CENTER, SocketType.BACK_CENTER,
                }:
                    return "xz"
        return "xy"

    @classmethod
    def _populate_assembly_repeated_semantics(
        cls,
        node: ManifestNode,
        parent: ManifestNode,
        manifest: BuildManifest,
        socket: SocketType,
    ) -> None:
        """Assign stable repeated slots to sibling assemblies.

        The LLM may omit these fields for ASSEMBLY nodes because Stage 3 runs
        on parts.  Deriving them from containment order is deterministic and
        guarantees a unique 0..N-1 slot for each repeated sibling.
        """
        siblings = [
            manifest.nodes[child_id]
            for child_id in parent.children_ids
            if child_id in manifest.nodes
            and manifest.nodes[child_id].attachment
            and manifest.nodes[child_id].attachment.socket_type == socket
        ]
        if not siblings:
            return
        semantics = node.stage_outputs.setdefault("stage3", {})
        index = siblings.index(node)
        count = len(siblings)
        if socket in (SocketType.RADIAL, SocketType.RADIAL_BRIDGE):
            semantics["radial_count"] = count
            semantics["radial_index"] = index
            node.attachment.radial_count = count
            node.attachment.radial_index = index
        elif socket == SocketType.ARRAY_MEMBER:
            semantics["array_count"] = count
            semantics["array_index"] = index
            node.attachment.array_count = count
            node.attachment.array_index = index

    @classmethod
    def _populate_assembly_radial_semantics(
        cls,
        node: ManifestNode,
        parent: ManifestNode,
        manifest: BuildManifest,
    ) -> None:
        cls._populate_assembly_repeated_semantics(node, parent, manifest, SocketType.RADIAL)
    
    @classmethod
    def _resolve_boolean_cut(cls, parent: BBox, child: BBox, sem: Dict, node: ManifestNode) -> ResolvedTransform:
        """BOOLEAN_CUT: Subtracted from parent.
        
        Cutter is centered on the target face and positioned so it fully
        pierces through the parent. The cutter geometry is oversized by
        BOOLEAN_OVERSHOOT_M on each side to avoid coplanar face artifacts.
        """
        cut_face = sem.get("cut_face", "top")
        
        # Cutter is centered at the parent's geometric center so it spans the
        # full thickness. build_boolean_cut() oversizes depth by BOOLEAN_OVERSHOOT_M
        # on both sides, so no additional offset is needed here.
        # Lateral offsets (e.g. left/right hole positions) come from Stage 3
        # semantic hints via the x_offset / y_offset fields.
        offset = [0.0, 0.0, 0.0]
        
        # Apply any lateral offset specified by Stage 3 (closed vocabulary, meters)
        offset[0] += sem.get("x_offset", 0.0)
        offset[1] += sem.get("y_offset", 0.0)
        offset[2] += sem.get("z_offset", 0.0)
        
        return ResolvedTransform(
            offset=offset,
            is_boolean=True,
            boolean_op="difference",
            resolution_method=f"BOOLEAN_CUT:{cut_face}",
        )
    
    @classmethod
    def _resolve_boolean_union(cls, parent: BBox, child: BBox, sem: Dict, node: ManifestNode) -> ResolvedTransform:
        """BOOLEAN_UNION: Merged with parent."""
        # Union typically uses same positioning as the socket it would otherwise use
        # Default to centered on parent
        return ResolvedTransform(
            offset=[0.0, 0.0, 0.0],
            is_boolean=True,
            boolean_op="union",
            resolution_method="BOOLEAN_UNION",
        )
    
    @classmethod
    def _resolve_boolean_intersect(cls, parent: BBox, child: BBox, sem: Dict, node: ManifestNode) -> ResolvedTransform:
        """BOOLEAN_INTERSECT: Intersection with parent."""
        return ResolvedTransform(
            offset=[0.0, 0.0, 0.0],
            is_boolean=True,
            boolean_op="intersect",
            resolution_method="BOOLEAN_INTERSECT",
        )
    
    @classmethod
    def _resolve_inset(cls, parent: BBox, child: BBox, sem: Dict, node: ManifestNode) -> ResolvedTransform:
        """INSET: Recessed into parent surface or cavity.
        
        For glass panels, screens, or suspended elements inside brackets/cavities.
        If parent or host is a U-bracket, centers inside the fork gap.
        """
        parent_prim = sem.get("parent_primitive", "")
        parent_lbl = sem.get("parent_label", "").lower()
        if (
            parent_prim == PrimitiveType.U_SHAPE.value
            or "bracket" in parent_lbl
            or "u_shape" in parent_lbl
            or "fork" in parent_lbl
        ):
            # Inside the fork gap: centered horizontally, midpoint between arch and leg tips
            offset_z = (parent.min_z + parent.max_z) / 2.0
            return ResolvedTransform(
                offset=[0.0, 0.0, offset_z],
                resolution_method="INSET:u_bracket_fork_gap",
            )

        face = sem.get("inset_face", "top")
        depth = sem.get("inset_depth", 0.005)  # 5mm default recess
        
        offset = [0.0, 0.0, 0.0]
        
        # Position centered in parent, recessed from the specified face
        if face == "top":
            # Glass sits slightly below top surface
            offset[2] = parent.max_z - depth - child.size_z / 2
        elif face == "bottom":
            offset[2] = parent.min_z + depth + child.size_z / 2
        elif face == "front":
            offset[1] = parent.min_y + depth + child.size_y / 2
        elif face == "back":
            offset[1] = parent.max_y - depth - child.size_y / 2
        elif face == "left":
            offset[0] = parent.min_x + depth + child.size_x / 2
        elif face == "right":
            offset[0] = parent.max_x - depth - child.size_x / 2
        else:
            # Default: centered, slightly below top
            offset[2] = parent.max_z - depth - child.size_z / 2
        
        return ResolvedTransform(
            offset=offset,
            resolution_method=f"INSET:{face}:{depth}",
        )
    
    # ── Face Resolvers ───────────────────────────────────────────────────
    
    @classmethod
    def _resolve_top_face(cls, parent: BBox, child: BBox, sem: Dict, node: ManifestNode) -> ResolvedTransform:
        """TOP_FACE: On top face with position offset."""
        pos = sem.get("face_position", "center")
        offset = [0.0, 0.0, parent.max_z + child.size_z / 2]
        offset = cls._apply_face_position(offset, pos, parent, "xy")
        return ResolvedTransform(offset=offset, resolution_method=f"TOP_FACE:{pos}")
    
    @classmethod
    def _resolve_bottom_face(cls, parent: BBox, child: BBox, sem: Dict, node: ManifestNode) -> ResolvedTransform:
        """BOTTOM_FACE: On bottom face with position offset."""
        pos = sem.get("face_position", "center")
        offset = [0.0, 0.0, parent.min_z - child.size_z / 2]
        offset = cls._apply_face_position(offset, pos, parent, "xy")
        return ResolvedTransform(offset=offset, resolution_method=f"BOTTOM_FACE:{pos}")
    
    @classmethod
    def _resolve_front_face(cls, parent: BBox, child: BBox, sem: Dict, node: ManifestNode) -> ResolvedTransform:
        """FRONT_FACE: On front face (-Y in Blender) with position offset."""
        pos = sem.get("face_position", "center")
        try:
            clearance = max(0.0, float(sem.get("front_clearance_m", 0.0)))
        except (TypeError, ValueError):
            clearance = 0.0
        offset = [0.0, parent.min_y - child.size_y / 2 - clearance, 0.0]
        offset = cls._apply_face_position(offset, pos, parent, "xz")
        return ResolvedTransform(offset=offset, resolution_method=f"FRONT_FACE:{pos}:clearance={clearance}")
    
    @classmethod
    def _resolve_back_face(cls, parent: BBox, child: BBox, sem: Dict, node: ManifestNode) -> ResolvedTransform:
        """BACK_FACE: On back face (+Y in Blender) with position offset."""
        pos = sem.get("face_position", "center")
        offset = [0.0, parent.max_y + child.size_y / 2, 0.0]
        offset = cls._apply_face_position(offset, pos, parent, "xz")
        return ResolvedTransform(offset=offset, resolution_method=f"BACK_FACE:{pos}")
    
    @classmethod
    def _resolve_left_face(cls, parent: BBox, child: BBox, sem: Dict, node: ManifestNode) -> ResolvedTransform:
        """LEFT_FACE: On left face (-X) with position offset."""
        pos = sem.get("face_position", "center")
        offset = [parent.min_x - child.size_x / 2, 0.0, 0.0]
        offset = cls._apply_face_position(offset, pos, parent, "yz")
        return ResolvedTransform(offset=offset, resolution_method=f"LEFT_FACE:{pos}")
    
    @classmethod
    def _resolve_right_face(cls, parent: BBox, child: BBox, sem: Dict, node: ManifestNode) -> ResolvedTransform:
        """RIGHT_FACE: On right face (+X) with position offset."""
        pos = sem.get("face_position", "center")
        offset = [parent.max_x + child.size_x / 2, 0.0, 0.0]
        offset = cls._apply_face_position(offset, pos, parent, "yz")
        return ResolvedTransform(offset=offset, resolution_method=f"RIGHT_FACE:{pos}")
    
    @classmethod
    def _apply_face_position(cls, offset: List[float], pos: str, parent: BBox, plane: str) -> List[float]:
        """Apply face_position offset within a plane.
        
        Uses BlenderAxis convention: -Y = front, +Y = back.
        """
        offset = list(offset)
        
        if plane == "xy":
            if "left" in pos:
                offset[0] = parent.min_x * 0.5
            elif "right" in pos:
                offset[0] = parent.max_x * 0.5
            # FIXED: front = -Y (min_y), back = +Y (max_y)
            if "front" in pos:
                offset[1] = parent.min_y * 0.5
            elif "back" in pos:
                offset[1] = parent.max_y * 0.5
                
        elif plane == "xz":
            if "left" in pos:
                offset[0] = parent.min_x * 0.5
            elif "right" in pos:
                offset[0] = parent.max_x * 0.5
            if "top" in pos:
                offset[2] = parent.max_z * 0.5
            elif "bottom" in pos:
                offset[2] = parent.min_z * 0.5
                
        elif plane == "yz":
            # FIXED: front = -Y (min_y), back = +Y (max_y)
            if "front" in pos:
                offset[1] = parent.min_y * 0.5
            elif "back" in pos:
                offset[1] = parent.max_y * 0.5
            if "top" in pos:
                offset[2] = parent.max_z * 0.5
            elif "bottom" in pos:
                offset[2] = parent.min_z * 0.5
        
        return offset
    
    # ── End Sockets ──────────────────────────────────────────────────────
    
    @classmethod
    def _resolve_left_end(cls, parent: BBox, child: BBox, sem: Dict, node: ManifestNode) -> ResolvedTransform:
        """LEFT_END: At -X end of parent's extent."""
        is_ring = node.geometry and node.geometry.primitive in (PrimitiveType.TORUS, PrimitiveType.CIRCLE)
        offset_x = parent.min_x if is_ring else parent.min_x - child.size_x / 2
        return ResolvedTransform(
            offset=[offset_x, 0.0, 0.0],
            resolution_method="LEFT_END",
        )
    
    @classmethod
    def _resolve_right_end(cls, parent: BBox, child: BBox, sem: Dict, node: ManifestNode) -> ResolvedTransform:
        """RIGHT_END: At +X end of parent's extent."""
        is_ring = node.geometry and node.geometry.primitive in (PrimitiveType.TORUS, PrimitiveType.CIRCLE)
        offset_x = parent.max_x if is_ring else parent.max_x + child.size_x / 2
        return ResolvedTransform(
            offset=[offset_x, 0.0, 0.0],
            resolution_method="RIGHT_END",
        )
    
    @classmethod
    def _resolve_top_end(cls, parent: BBox, child: BBox, sem: Dict, node: ManifestNode) -> ResolvedTransform:
        """TOP_END: At +Z end of parent's extent."""
        is_ring = node.geometry and node.geometry.primitive in (PrimitiveType.TORUS, PrimitiveType.CIRCLE)
        offset_z = parent.max_z if is_ring else parent.max_z + child.size_z / 2
        return ResolvedTransform(
            offset=[0.0, 0.0, offset_z],
            resolution_method="TOP_END",
        )
    
    @classmethod
    def _resolve_bottom_end(cls, parent: BBox, child: BBox, sem: Dict, node: ManifestNode) -> ResolvedTransform:
        """BOTTOM_END: At -Z end of parent's extent."""
        is_ring = node.geometry and node.geometry.primitive in (PrimitiveType.TORUS, PrimitiveType.CIRCLE)
        offset_z = parent.min_z if is_ring else parent.min_z - child.size_z / 2
        return ResolvedTransform(
            offset=[0.0, 0.0, offset_z],
            resolution_method="BOTTOM_END",
        )
    
    @classmethod
    def _resolve_front_end(cls, parent: BBox, child: BBox, sem: Dict, node: ManifestNode) -> ResolvedTransform:
        """FRONT_END: At -Y end of parent's extent (front in Blender)."""
        is_ring = node.geometry and node.geometry.primitive in (PrimitiveType.TORUS, PrimitiveType.CIRCLE)
        offset_y = parent.min_y if is_ring else parent.min_y - child.size_y / 2
        return ResolvedTransform(
            offset=[0.0, offset_y, 0.0],
            resolution_method="FRONT_END",
        )
    
    @classmethod
    def _resolve_back_end(cls, parent: BBox, child: BBox, sem: Dict, node: ManifestNode) -> ResolvedTransform:
        """BACK_END: At +Y end of parent's extent (back in Blender)."""
        is_ring = node.geometry and node.geometry.primitive in (PrimitiveType.TORUS, PrimitiveType.CIRCLE)
        offset_y = parent.max_y if is_ring else parent.max_y + child.size_y / 2
        return ResolvedTransform(
            offset=[0.0, offset_y, 0.0],
            resolution_method="BACK_END",
        )
    
    # ── Connector Sockets (Pass 1 - Placeholders) ────────────────────────
    # These return placeholder transforms. Real resolution happens in pass 2
    # after all world positions are computed.
    
    @classmethod
    def _resolve_radial_bridge_pass1(cls, parent: BBox, child: BBox, sem: Dict, node: ManifestNode) -> ResolvedTransform:
        """RADIAL_BRIDGE pass 1: Placeholder, real resolution in pass 2.
        
        connects_to is required for pass 2 but Stage 3 may not have populated it
        yet on the first pass. We emit a placeholder and let pass 2 hard-fail if
        it's still missing — this avoids burning retries on a Stage 3 LLM race.
        """
        connects_to = sem.get("connects_to") or getattr(node.attachment, "connects_to", None)
        count = sem.get("radial_count", 4)
        index = sem.get("radial_index", 0)
        
        if not connects_to:
            # Don't raise here — Stage 3 may populate connects_to before pass 2 runs.
            # Log a warning so it's visible; pass 2 will raise if still missing.
            logger.warning(
                f"RADIAL_BRIDGE (pass1): {node.label} has no 'connects_to' yet — "
                f"pass 2 will fail if Stage 3 doesn't populate it."
            )
            connects_to = "__unknown__"
        
        logger.info(f"RADIAL_BRIDGE (pass1): {node.label} -> connects_to={connects_to}, index={index}/{count}")
        
        # Placeholder - will be replaced in pass 2
        return ResolvedTransform(
            offset=[0.0, 0.0, 0.0],
            resolution_method=f"RADIAL_BRIDGE:pass1:{connects_to}:{index}/{count}",
        )
    
    @classmethod
    def _resolve_strut_pass1(cls, parent: BBox, child: BBox, sem: Dict, node: ManifestNode) -> ResolvedTransform:
        """STRUT pass 1: Placeholder, real resolution in pass 2."""
        connects_to = sem.get("connects_to") or getattr(node.attachment, "connects_to", None)
        if not connects_to:
            logger.warning(
                f"STRUT (pass1): {node.label} has no 'connects_to' yet — "
                f"pass 2 will fail if Stage 3 doesn't populate it."
            )
            connects_to = "__unknown__"
        
        logger.info(f"STRUT (pass1): {node.label} -> connects_to={connects_to}")
        
        return ResolvedTransform(
            offset=[0.0, 0.0, 0.0],
            resolution_method=f"STRUT:pass1:{connects_to}",
        )
    
    @classmethod
    def _resolve_bridge_pass1(cls, parent: BBox, child: BBox, sem: Dict, node: ManifestNode) -> ResolvedTransform:
        """BRIDGE pass 1: Placeholder, real resolution in pass 2."""
        connects_to = sem.get("connects_to") or getattr(node.attachment, "connects_to", None)
        if not connects_to:
            logger.warning(
                f"BRIDGE (pass1): {node.label} has no 'connects_to' yet — "
                f"pass 2 will fail if Stage 3 doesn't populate it."
            )
            connects_to = "__unknown__"
        
        position_fraction = sem.get("position_fraction", "middle")
        
        logger.info(f"BRIDGE (pass1): {node.label} -> connects_to={connects_to}, fraction={position_fraction}")
        
        return ResolvedTransform(
            offset=[0.0, 0.0, 0.0],
            resolution_method=f"BRIDGE:pass1:{connects_to}:{position_fraction}",
        )
    
    @classmethod
    def _resolve_relative_to_pass1(cls, parent: BBox, child: BBox, sem: Dict, node: ManifestNode) -> ResolvedTransform:
        """RELATIVE_TO pass 1: Placeholder, real resolution in pass 2.
        
        RELATIVE_TO uses closed vocabulary - no LLM-computed numbers:
        - relative_to: label of reference part
        - direction: left|right|front|back|above|below|along (along = same axis, different position)
        - gap: touching|small|medium|large
        - align: same_position|same_level
        - position_along: start|quarter|middle|halfway|three_quarter|end (for 'along' direction)
        """
        relative_to = sem.get("relative_to") or getattr(node.attachment, "relative_to", None)
        if not relative_to:
            logger.warning(
                f"RELATIVE_TO (pass1): {node.label} has no 'relative_to' yet — "
                f"pass 2 will fail if Stage 3 doesn't populate it."
            )
            relative_to = "__unknown__"
        
        direction = sem.get("direction") or getattr(node.attachment, "direction", None) or "right"
        gap = sem.get("gap") or getattr(node.attachment, "gap", None) or "small"
        align = sem.get("align") or getattr(node.attachment, "align", None) or "same_position"
        position_along = sem.get("position_along") or getattr(node.attachment, "position_along", None) or "middle"
        
        logger.info(f"RELATIVE_TO (pass1): {node.label} -> relative_to={relative_to}, direction={direction}, gap={gap}, align={align}, position_along={position_along}")
        
        return ResolvedTransform(
            offset=[0.0, 0.0, 0.0],
            resolution_method=f"RELATIVE_TO:pass1:{relative_to}:{direction}:{gap}:{align}:{position_along}",
        )
    
    # ── Pass 2 Cross-Reference Resolvers ─────────────────────────────────
    # These are called after world positions are computed for all pass-1 nodes.
    # 
    # Phase 3.5 Architecture:
    # - Cross-reference resolvers receive world_matrices (Dict[str, WorldMatrix])
    # - They compute a desired child WORLD matrix from semantic relationships
    # - They convert to parent-local via _world_to_parent_local()
    # - NO world-position subtraction is allowed
    
    @classmethod
    def _world_to_parent_local(
        cls,
        parent_world: WorldMatrix,
        child_world: WorldMatrix,
    ) -> LocalTransform:
        """Convert desired child world transform to parent-local transform.
        
        This is THE correct formula for hierarchical transforms:
            child_local = inverse(parent_world) @ child_world
        
        Phase 3.5: This is the ONLY valid way to compute a parent-local
        transform from world-space information. Do NOT use:
            child_world_pos - parent_world_pos  (WRONG)
        
        Args:
            parent_world: Parent's world matrix
            child_world: Desired child world matrix
            
        Returns:
            LocalTransform relative to parent's coordinate frame
            
        Raises:
            Stage4Error: If parent world matrix is singular
        """
        parent_inv = parent_world.inverse()
        if parent_inv is None:
            raise Stage4Error("Singular parent world matrix - cannot compute inverse")
        child_local_matrix = _mat4_multiply(parent_inv.matrix, child_world.matrix)
        return LocalTransform.from_matrix(child_local_matrix)
    
    @classmethod
    def _build_world_matrix(
        cls,
        position: List[float],
        rotation: List[float],
    ) -> WorldMatrix:
        """Build a WorldMatrix from position and rotation.
        
        Helper for cross-reference resolvers to construct desired world matrices.
        
        Args:
            position: World position [x, y, z]
            rotation: World rotation [rx, ry, rz] in radians
            
        Returns:
            WorldMatrix representing the desired world transform
        """
        matrix = _mat4_from_trs(position, rotation, [1.0, 1.0, 1.0])
        return WorldMatrix(matrix=matrix)
    
    @classmethod
    def resolve_cross_reference(
        cls,
        node: ManifestNode,
        manifest: BuildManifest,
        world_matrices: Dict[str, WorldMatrix],
        world_bboxes: Dict[str, BBox],
    ) -> Tuple[ResolvedTransform, AttachmentSolution]:
        """Pass 2: Resolve cross-reference sockets using world matrices.
        
        Phase 3.5: Now accepts world_matrices instead of world_positions.
        Returns both legacy ResolvedTransform and new AttachmentSolution.
        
        The AttachmentSolution.local_transform is computed via proper matrix
        conversion: child_local = inverse(parent_world) @ child_world
        
        Args:
            node: Node with cross-reference socket
            manifest: Build manifest
            world_matrices: Dict of node_id -> WorldMatrix (from new transform system)
            world_bboxes: Dict of node_id -> BBox (local-space bounding boxes)
            
        Returns:
            Tuple of (ResolvedTransform, AttachmentSolution)
            
        Raises:
            Stage4Error: If required world matrices are not available
        """
        socket = node.attachment.socket_type
        sem = node.stage_outputs.get("stage3", {})
        parent_id = node.parent_id or ""
        
        # Validate parent world matrix is available
        if parent_id and parent_id not in world_matrices:
            raise Stage4Error(
                f"{node.label}: Parent '{parent_id}' world matrix not available. "
                f"Cross-reference resolution requires parent world matrix."
            )
        
        if socket == SocketType.RELATIVE_TO:
            return cls._resolve_relative_to_pass2_v2(node, manifest, world_matrices, world_bboxes, sem)
        elif socket == SocketType.BRIDGE:
            return cls._resolve_bridge_pass2_v2(node, manifest, world_matrices, world_bboxes, sem)
        elif socket == SocketType.STRUT:
            return cls._resolve_strut_pass2_v2(node, manifest, world_matrices, world_bboxes, sem)
        elif socket == SocketType.RADIAL_BRIDGE:
            return cls._resolve_radial_bridge_pass2_v2(node, manifest, world_matrices, world_bboxes, sem)
        else:
            raise Stage4Error(f"{node.label}: Unknown cross-reference socket {socket.value}")
    
    # ── Helper Methods ───────────────────────────────────────────────────
    
    @classmethod
    def _compute_anchor_points(
        cls,
        a_world: WorldMatrix,
        a_bbox: BBox,
        b_world: WorldMatrix,
        b_bbox: BBox,
        fraction: float,
    ) -> Tuple[List[float], List[float]]:
        """Compute nearest-facing surface points on A and B.

        Phase D invariant: spatial intersection math is exclusively local.
        The target world point is transformed into each part's local coordinate
        frame via inverse(world_matrix) before the AABB surface intersection is
        computed, then the result is transformed back to world space.
        This eliminates rotational clipping bugs where a world-space direction
        vector was applied directly to a local-space bbox.

        fraction determines height along overlapping Z span.
        """
        from ..transforms import _mat4_transform_point

        a_pos = list(a_world.position)
        b_pos = list(b_world.position)

        # ── Z span ────────────────────────────────────────────────────────
        # Transform the 8 bbox corners of each part to world space to obtain
        # true world-space Z bounds, properly respecting rotation/scale.
        def _world_z_extents(wm: WorldMatrix, bbox: BBox) -> Tuple[float, float]:
            corners = [
                wm.transform_point([x, y, z])
                for x in (bbox.min_x, bbox.max_x)
                for y in (bbox.min_y, bbox.max_y)
                for z in (bbox.min_z, bbox.max_z)
            ]
            zs = [c[2] for c in corners]
            return min(zs), max(zs)

        a_min_z, a_max_z = _world_z_extents(a_world, a_bbox)
        b_min_z, b_max_z = _world_z_extents(b_world, b_bbox)
        z_lo = max(a_min_z, b_min_z)
        z_hi = min(a_max_z, b_max_z)
        if z_hi < z_lo:
            mid_z = ((a_min_z + a_max_z) / 2.0 + (b_min_z + b_max_z) / 2.0) / 2.0
            z_lo = z_hi = mid_z
        z = z_lo + fraction * (z_hi - z_lo)

        # ── Anchor on A: transform B's world position into A-local space ──
        a_inv = a_world.inverse()
        if a_inv is not None:
            b_in_a_local = _mat4_transform_point(a_inv.matrix, b_pos)
            # Intersect ray from A-local origin toward b_in_a_local against A's AABB
            dx, dy = b_in_a_local[0], b_in_a_local[1]
            horiz = math.hypot(dx, dy) or 1.0
            ux_a, uy_a = dx / horiz, dy / horiz
            surface_x_a = ux_a * (a_bbox.size_x / 2)
            surface_y_a = uy_a * (a_bbox.size_y / 2)
            anchor_a_local = [surface_x_a, surface_y_a, 0.0]
            anchor_a = a_world.transform_point(anchor_a_local)
            anchor_a[2] = z
        else:
            # Singular matrix — fall back to world-centre
            anchor_a = [a_pos[0], a_pos[1], z]

        # ── Anchor on B: transform A's world position into B-local space ──
        b_inv = b_world.inverse()
        if b_inv is not None:
            a_in_b_local = _mat4_transform_point(b_inv.matrix, a_pos)
            dx, dy = a_in_b_local[0], a_in_b_local[1]
            horiz = math.hypot(dx, dy) or 1.0
            ux_b, uy_b = dx / horiz, dy / horiz
            # a_in_b_local already points from B-local origin toward A —
            # the facing surface on B is in that same direction.
            surface_x_b = ux_b * (b_bbox.size_x / 2)
            surface_y_b = uy_b * (b_bbox.size_y / 2)
            anchor_b_local = [surface_x_b, surface_y_b, 0.0]
            anchor_b = b_world.transform_point(anchor_b_local)
            anchor_b[2] = z
        else:
            anchor_b = [b_pos[0], b_pos[1], z]

        return anchor_a, anchor_b
    
    @classmethod
    def _rotation_to_direction(cls, direction: List[float], length: float) -> List[float]:
        """Compute Euler rotation to align local Z-axis with direction vector.
        
        Builds a rotation matrix whose third column (local Z) is the normalized
        direction, then converts to Euler XYZ. Uses stable cross-product basis
        construction to avoid gimbal issues.
        
        This replaces the broken pitch/yaw/roll formula that couldn't actually
        reorient the Z-axis (rotating around Z leaves Z unchanged).
        """
        if length < 1e-6:
            return [0.0, 0.0, 0.0]
        
        # Normalize direction -> this becomes our new Z-axis
        dz_x, dz_y, dz_z = direction[0] / length, direction[1] / length, direction[2] / length
        new_z = [dz_x, dz_y, dz_z]
        
        # Choose a reference "up" vector that's not parallel to direction
        # Use world Z unless direction is nearly vertical, then use world X
        if abs(dz_z) < 0.99:
            ref_up = [0.0, 0.0, 1.0]
        else:
            ref_up = [1.0, 0.0, 0.0]
        
        # new_x = ref_up × new_z (perpendicular to both)
        new_x = [
            ref_up[1] * new_z[2] - ref_up[2] * new_z[1],
            ref_up[2] * new_z[0] - ref_up[0] * new_z[2],
            ref_up[0] * new_z[1] - ref_up[1] * new_z[0],
        ]
        # Normalize new_x
        x_len = math.sqrt(new_x[0]**2 + new_x[1]**2 + new_x[2]**2)
        if x_len < 1e-6:
            # Fallback: direction is exactly along ref_up, use different reference
            ref_up = [0.0, 1.0, 0.0]
            new_x = [
                ref_up[1] * new_z[2] - ref_up[2] * new_z[1],
                ref_up[2] * new_z[0] - ref_up[0] * new_z[2],
                ref_up[0] * new_z[1] - ref_up[1] * new_z[0],
            ]
            x_len = math.sqrt(new_x[0]**2 + new_x[1]**2 + new_x[2]**2)
        
        new_x = [new_x[0] / x_len, new_x[1] / x_len, new_x[2] / x_len]
        
        # new_y = new_z × new_x (completes right-handed basis)
        new_y = [
            new_z[1] * new_x[2] - new_z[2] * new_x[1],
            new_z[2] * new_x[0] - new_z[0] * new_x[2],
            new_z[0] * new_x[1] - new_z[1] * new_x[0],
        ]
        
        # Build rotation matrix: columns are new_x, new_y, new_z
        # But _matrix_to_euler expects row-major, so we transpose
        rot_matrix = [
            [new_x[0], new_y[0], new_z[0]],
            [new_x[1], new_y[1], new_z[1]],
            [new_x[2], new_y[2], new_z[2]],
        ]
        
        # Convert to Euler using the existing verified function
        return _matrix_to_euler(rot_matrix)
    
    # ── Phase 3.5: New Cross-Reference Resolvers (Matrix-Based) ──────────
    # These use proper matrix conversion: child_local = inverse(parent_world) @ child_world
    # NO world-position subtraction is allowed.
    
    @classmethod
    def _resolve_relative_to_pass2_v2(
        cls,
        node: ManifestNode,
        manifest: BuildManifest,
        world_matrices: Dict[str, WorldMatrix],
        world_bboxes: Dict[str, BBox],
        sem: Dict,
    ) -> Tuple[ResolvedTransform, AttachmentSolution]:
        """RELATIVE_TO pass 2 (Phase 3.5): Position relative to another named part.
        
        Computes desired child WORLD matrix, then converts to parent-local
        via proper matrix inversion. No world-position subtraction.
        
        Args:
            node: Node with RELATIVE_TO socket
            manifest: Build manifest
            world_matrices: Dict of node_id -> WorldMatrix
            world_bboxes: Dict of node_id -> BBox (local-space)
            sem: Stage 3 semantic hints
            
        Returns:
            Tuple of (ResolvedTransform, AttachmentSolution)
        """
        relative_to = sem.get("relative_to") or getattr(node.attachment, "relative_to", None)
        direction = sem.get("direction") or getattr(node.attachment, "direction", None) or "right"
        gap = sem.get("gap") or getattr(node.attachment, "gap", None) or "small"
        align = sem.get("align") or getattr(node.attachment, "align", None) or "same_position"
        position_along = sem.get("position_along") or getattr(node.attachment, "position_along", None) or "middle"
        
        if not relative_to or relative_to == "__unknown__":
            raise Stage4Error(f"{node.label}: RELATIVE_TO requires 'relative_to' — Stage 3 did not populate it")
        
        # Find reference part
        ref = manifest.get_node_by_label(relative_to)
        if ref is None:
            raise Stage4Error(f"{node.label}: RELATIVE_TO target '{relative_to}' not found in manifest")
        if ref.node_id not in world_matrices:
            raise Stage4Error(
                f"{node.label}: RELATIVE_TO target '{relative_to}' world matrix not available. "
                f"Ensure target is resolved before this node."
            )
        
        ref_world = world_matrices[ref.node_id]
        ref_bbox = world_bboxes.get(ref.node_id) or cls._get_child_bbox(ref)
        child_bbox = cls._get_child_bbox(node)
        
        # Get parent world matrix
        parent_id = node.parent_id or ""
        if parent_id not in world_matrices:
            raise Stage4Error(f"{node.label}: Parent world matrix not available")
        parent_world = world_matrices[parent_id]
        
        # Detect shelf-on-leg pattern
        node_label = node.label.lower()
        ref_label = relative_to.lower()
        is_shelf_on_leg = (
            ("shelf" in node_label or "board" in node_label or "platform" in node_label) and
            ("leg" in ref_label or "post" in ref_label or "support" in ref_label)
        )
        if not is_shelf_on_leg:
            ref_is_vertical = ref_bbox.size_z > ref_bbox.size_x and ref_bbox.size_z > ref_bbox.size_y
            child_is_horizontal = child_bbox.size_z < child_bbox.size_x or child_bbox.size_z < child_bbox.size_y
            is_shelf_on_leg = ref_is_vertical and child_is_horizontal and direction in ("below", "above", "along")
        
        is_bracket_interior = (
            ("bracket" in ref_label or "u_shape" in ref_label or (ref.geometry and ref.geometry.primitive == PrimitiveType.U_SHAPE))
            and ("lens" in node_label or "camera" in node_label or direction in ("inside", "between", "center", "below"))
        )

        # Compute desired child WORLD position
        ref_world_pos = ref_world.position
        
        if is_bracket_interior:
            # Position child centered horizontally, and midway in Z between bracket min_z and max_z
            bracket_z_mid = ref_world_pos[2] + (ref_bbox.min_z + ref_bbox.max_z) / 2.0
            child_world_pos = [ref_world_pos[0], ref_world_pos[1], bracket_z_mid]
            child_world_rot = [0.0, 0.0, 0.0]
        elif is_shelf_on_leg:
            # Position shelf at a specific Z height along the leg's span
            fraction = POSITION_ALONG.get(position_along, 0.5)
            leg_z_min = ref_world_pos[2] + ref_bbox.min_z
            leg_z_max = ref_world_pos[2] + ref_bbox.max_z
            shelf_z = leg_z_min + fraction * (leg_z_max - leg_z_min)
            child_world_pos = [0.0, 0.0, shelf_z]
            child_world_rot = [0.0, 0.0, 0.0]
        else:
            # Standard RELATIVE_TO: position adjacent to reference part
            try:
                axis, sign = _get_direction_axis(direction)
            except ValueError:
                raise Stage4Error(f"{node.label}: Invalid direction '{direction}'")
            
            if gap not in GAP_RATIO:
                gap = "small"
            ref_extent = ref_bbox.size(axis)
            child_extent = child_bbox.size(axis)
            gap_dist = GAP_RATIO[gap] * ref_extent
            
            child_world_pos = list(ref_world_pos)
            child_world_pos[axis] = ref_world_pos[axis] + sign * (ref_extent / 2 + child_extent / 2 + gap_dist)
            
            if align == "same_position":
                for i in range(3):
                    if i != axis:
                        child_world_pos[i] = ref_world_pos[i]
            elif align == "same_level":
                if axis != 2:
                    child_world_pos[2] = ref_world_pos[2]
            
            child_world_rot = [0.0, 0.0, 0.0]
        
        # Build desired child world matrix
        child_world = cls._build_world_matrix(child_world_pos, child_world_rot)
        
        # Convert to parent-local using proper matrix inversion
        local_transform = cls._world_to_parent_local(parent_world, child_world)
        
        logger.info(
            f"RELATIVE_TO (pass2 v2): {node.label} -> ref={relative_to}, "
            f"child_world={[round(p, 4) for p in child_world_pos]}, "
            f"local={[round(p, 4) for p in local_transform.position]}"
        )
        
        # Create legacy ResolvedTransform for comparison
        resolved = ResolvedTransform(
            offset=list(local_transform.position),
            rotation=list(local_transform.rotation),
            resolution_method=f"RELATIVE_TO:{relative_to}:{direction}:{gap}:{align}:{position_along}",
        )
        
        solution = AttachmentSolution(
            parent_id=parent_id,
            child_id=node.node_id,
            parent_socket="RELATIVE_TO",
            local_transform=local_transform,
            source=f"RELATIVE_TO:v2:{relative_to}:{direction}:{gap}",
        )
        
        return resolved, solution
    
    @classmethod
    def _resolve_bridge_pass2_v2(
        cls,
        node: ManifestNode,
        manifest: BuildManifest,
        world_matrices: Dict[str, WorldMatrix],
        world_bboxes: Dict[str, BBox],
        sem: Dict,
    ) -> Tuple[ResolvedTransform, AttachmentSolution]:
        """BRIDGE pass 2 (Phase 3.5): Connector between parent and target.

        Special cases handled:
        A. ASSEMBLY/MODEL parent — no geometry, use ROOT sibling as from-anchor.
        B. Coaxial (zero horizontal separation) — parts stacked vertically;
           place bridge beside the target laterally.
        C. Same-height parts (no Z overlap) — use center-to-center midpoint Z.
        D. Bridge is a cylinder (radius-based) — depth auto-sized to span length.
        E. Target not yet in world_matrices — raise with clear message.
        F. connects_to resolves to the node's own parent — raise to prevent
           zero-length self-bridge.
        """
        connects_to = sem.get("connects_to") or getattr(node.attachment, "connects_to", None)
        position_fraction_str = (
            sem.get("position_fraction")
            or getattr(node.attachment, "position_fraction", None)
            or "middle"
        )

        if not connects_to or connects_to == "__unknown__":
            raise Stage4Error(
                f"{node.label}: BRIDGE requires 'connects_to' — Stage 3 did not populate it"
            )

        # ── Resolve target ────────────────────────────────────────────────
        target = manifest.get_node_by_label(connects_to)
        if target is None:
            raise Stage4Error(f"{node.label}: BRIDGE target '{connects_to}' not found")
        if target.node_id not in world_matrices:
            raise Stage4Error(
                f"{node.label}: BRIDGE target '{connects_to}' world matrix not available"
            )

        # ── Resolve parent ────────────────────────────────────────────────
        parent = manifest.nodes.get(node.parent_id)
        if parent is None or parent.node_id not in world_matrices:
            raise Stage4Error(f"{node.label}: BRIDGE parent world matrix not available")

        # Special case F: connects_to == own parent → self-bridge, always zero-length
        if target.node_id == parent.node_id:
            raise Stage4Error(
                f"{node.label}: BRIDGE connects_to '{connects_to}' is the node's own parent — "
                f"choose a sibling or unrelated part as the target"
            )

        manifest_parent_world = world_matrices[parent.node_id]
        target_world = world_matrices[target.node_id]
        target_bbox = world_bboxes.get(target.node_id) or cls._get_child_bbox(target)

        spatial_contract = node.stage_outputs.get("spatial_contract", {}) or {}
        if spatial_contract.get("relation") == "coplanar_member":
            count = max(1, int(spatial_contract.get("member_count", 1)))
            index = int(spatial_contract.get("member_index", 0)) % count
            angle = 2.0 * math.pi * index / count
            child_bbox = cls._get_child_bbox(node)
            child_length = max(child_bbox.size_x, child_bbox.size_y, child_bbox.size_z)
            hub_radius = max(target_bbox.size_x, target_bbox.size_y) / 2.0
            enclosure = manifest.nodes.get(spatial_contract.get("enclosure_node_id"))
            enclosure_radius = 0.0
            if enclosure and enclosure.geometry:
                enclosure_radius = max(
                    0.0,
                    float(getattr(enclosure.geometry, "major_radius", 0.0) or 0.0)
                    - float(getattr(enclosure.geometry, "minor_radius", 0.0) or 0.0),
                )
            radial_distance = hub_radius + child_length * 0.45
            if enclosure_radius:
                radial_distance = min(radial_distance, enclosure_radius * 0.72)
            direction = [math.cos(angle), math.sin(angle), 0.0]
            midpoint = [
                target_world.position[0] + direction[0] * radial_distance,
                target_world.position[1] + direction[1] * radial_distance,
                target_world.position[2],
            ]
            # Blender's cone/cylinder long axis is local Z.  Aim it radially
            # in the declared plane; no bridge auto-resizing is performed.
            world_rotation = cls._rotation_to_direction(direction, 1.0)
            child_world = cls._build_world_matrix(midpoint, world_rotation)
            local_transform = cls._world_to_parent_local(manifest_parent_world, child_world)
            resolved = ResolvedTransform(
                offset=list(local_transform.position),
                rotation=list(local_transform.rotation),
                resolution_method=f"COPLANAR_MEMBER:{index}/{count}",
            )
            return resolved, AttachmentSolution(
                parent_id=node.parent_id or "",
                child_id=node.node_id,
                parent_socket="BRIDGE",
                local_transform=local_transform,
                source=f"COPLANAR_MEMBER:{index}/{count}",
            )

        # ── Special case A: ASSEMBLY/MODEL parent — find from-sibling ────
        # The assembly origin is at the ROOT child's position, not at world-origin.
        # Use the ROOT sibling (or any non-target sibling) as the from-anchor so
        # the bridge spans from real geometry rather than from the assembly origin.
        from_world = manifest_parent_world
        from_bbox = world_bboxes.get(parent.node_id) or cls._get_child_bbox(parent)

        if parent.kind in (NodeKind.ASSEMBLY, NodeKind.MODEL):
            from_sibling = None
            fallback_sibling = None
            for sib_id in parent.children_ids:
                if sib_id == node.node_id:
                    continue
                sib = manifest.nodes.get(sib_id)
                if not sib or sib.node_id not in world_matrices:
                    continue
                if sib.node_id == target.node_id:
                    continue  # skip the target itself as from-anchor
                sib_socket = sib.attachment.socket_type if sib.attachment else None
                if sib_socket == SocketType.ROOT:
                    from_sibling = sib
                    break
                if fallback_sibling is None:
                    fallback_sibling = sib
            from_sibling = from_sibling or fallback_sibling
            if from_sibling is not None:
                from_world = world_matrices[from_sibling.node_id]
                from_bbox = world_bboxes.get(from_sibling.node_id) or cls._get_child_bbox(from_sibling)

        fraction = POSITION_FRACTION.get(position_fraction_str, 0.5)

        # ── Compute anchor points ─────────────────────────────────────────
        anchor_a, anchor_b = cls._compute_anchor_points(
            from_world, from_bbox,
            target_world, target_bbox,
            fraction,
        )

        midpoint = [(anchor_a[i] + anchor_b[i]) / 2 for i in range(3)]
        direction = [anchor_b[i] - anchor_a[i] for i in range(3)]
        length = math.sqrt(sum(d * d for d in direction))

        # ── Special case B: coaxial (zero horizontal separation) ──────────
        # Happens when the bridge part sits directly above/below its target
        # (e.g. a shackle leg bridging to the lock body directly below it).
        # Strategy: offset laterally by the target's half-width so the bridge
        # runs beside the target rather than through it.
        if length < 1e-6:
            target_local_bbox = cls._get_child_bbox(target)
            lateral = (target_local_bbox.size_x / 2) or 0.01
            target_top_z = target_world.position[2] + target_local_bbox.max_z
            from_pos = [
                from_world.position[0] + lateral,
                from_world.position[1],
                from_world.position[2],
            ]
            to_pos = [
                target_world.position[0] + lateral,
                target_world.position[1],
                target_top_z,
            ]
            anchor_a, anchor_b = from_pos, to_pos
            midpoint = [(anchor_a[i] + anchor_b[i]) / 2 for i in range(3)]
            direction = [anchor_b[i] - anchor_a[i] for i in range(3)]
            length = math.sqrt(sum(d * d for d in direction))
            if length < 1e-6:
                raise Stage4Error(f"{node.label}: Zero-length bridge even after coaxial fallback")
            logger.info(
                f"BRIDGE (pass2 v2): {node.label} coaxial fallback — "
                f"lateral={lateral:.4f}m, target_top_z={target_top_z:.4f}m, length={length:.4f}m"
            )

        # ── Special case C: no Z overlap — already handled by _compute_anchor_points
        # (it uses center-to-center midpoint Z when z_hi < z_lo)

        # ── Compute rotation and world matrix ─────────────────────────────
        if (
            node.geometry
            and node.geometry.primitive in (PrimitiveType.TORUS, PrimitiveType.CIRCLE)
            and (position_fraction_str in ("end", "start") or fraction >= 0.99)
        ):
            if fraction >= 0.5:
                # When connecting to an arm/radial member at the outer "end",
                # anchor_b points toward anchor_a (the inner hub/assembly center).
                # Compute the true outer tip along the outward ray away from from_world.
                target_pos = list(target_world.position)
                from_pos = list(from_world.position)
                outward = [target_pos[i] - from_pos[i] for i in range(3)]
                out_len = math.sqrt(sum(x * x for x in outward))
                if out_len > 1e-6:
                    out_dir = [x / out_len for x in outward]
                    far_pos = [target_pos[i] + out_dir[i] * 10.0 for i in range(3)]
                    target_inv = target_world.inverse()
                    if target_inv is not None:
                        from ..transforms import _mat4_transform_point
                        local_target = _mat4_transform_point(target_inv.matrix, far_pos)
                        d_len = math.sqrt(sum(x * x for x in local_target))
                        if d_len > 1e-6:
                            u = [x / d_len for x in local_target]
                            half = [target_bbox.size_x / 2.0, target_bbox.size_y / 2.0, target_bbox.size_z / 2.0]
                            t_candidates = [half[i] / abs(u[i]) for i in range(3) if abs(u[i]) > 1e-6]
                            if t_candidates:
                                t_hit = min(t_candidates)
                                midpoint = target_world.transform_point([u[i] * t_hit for i in range(3)])
                            else:
                                midpoint = anchor_b
                        else:
                            midpoint = anchor_b
                    else:
                        midpoint = anchor_b
                else:
                    midpoint = anchor_b
            else:
                midpoint = anchor_a
            world_rotation = [0.0, 0.0, 0.0]
            child_world = cls._build_world_matrix(midpoint, world_rotation)
        else:
            world_rotation = cls._rotation_to_direction(direction, length)
            child_world = cls._build_world_matrix(midpoint, world_rotation)

        # ── Special case D: auto-size depth to span length ────────────────
        # Always write the computed length back so the executor creates a
        # cylinder/box whose depth exactly spans the gap.
        if "stage2" in node.stage_outputs:
            node.stage_outputs["stage2"]["depth"] = round(length, 6)

        # ── Convert to parent-local ───────────────────────────────────────
        # Always use manifest_parent_world (the node's actual hierarchy parent),
        # NOT from_world which may have been replaced by a sibling above.
        local_transform = cls._world_to_parent_local(manifest_parent_world, child_world)

        logger.info(
            f"BRIDGE (pass2 v2): {node.label} -> {connects_to}, length={length:.3f}, "
            f"world_pos={[round(p, 4) for p in midpoint]}, "
            f"local_pos={[round(p, 4) for p in local_transform.position]}"
        )

        resolved = ResolvedTransform(
            offset=list(local_transform.position),
            rotation=list(local_transform.rotation),
            resolution_method=f"BRIDGE:{connects_to}:{position_fraction_str}",
        )
        solution = AttachmentSolution(
            parent_id=node.parent_id or "",
            child_id=node.node_id,
            parent_socket="BRIDGE",
            local_transform=local_transform,
            source=f"BRIDGE:v2:{connects_to}:{position_fraction_str}",
        )
        return resolved, solution
    
    @classmethod
    def _resolve_strut_pass2_v2(
        cls,
        node: ManifestNode,
        manifest: BuildManifest,
        world_matrices: Dict[str, WorldMatrix],
        world_bboxes: Dict[str, BBox],
        sem: Dict,
    ) -> Tuple[ResolvedTransform, AttachmentSolution]:
        """STRUT pass 2 (Phase 3.5): Diagonal connector between parent and target.
        
        Computes desired child WORLD matrix, then converts to parent-local.
        """
        connects_to = sem.get("connects_to") or getattr(node.attachment, "connects_to", None)
        
        if not connects_to or connects_to == "__unknown__":
            raise Stage4Error(f"{node.label}: STRUT requires 'connects_to' — Stage 3 did not populate it")
        
        target = manifest.get_node_by_label(connects_to)
        if target is None:
            raise Stage4Error(f"{node.label}: STRUT target '{connects_to}' not found")
        if target.node_id not in world_matrices:
            raise Stage4Error(
                f"{node.label}: STRUT target '{connects_to}' world matrix not available"
            )
        
        parent = manifest.nodes.get(node.parent_id)
        if parent is None or parent.node_id not in world_matrices:
            raise Stage4Error(f"{node.label}: STRUT parent world matrix not available")
        
        parent_world = world_matrices[parent.node_id]
        target_world = world_matrices[target.node_id]
        parent_bbox = world_bboxes.get(parent.node_id) or cls._get_child_bbox(parent)
        target_bbox = world_bboxes.get(target.node_id) or cls._get_child_bbox(target)

        # Guard: connects_to == own parent is always zero-length
        if target.node_id == parent.node_id:
            raise Stage4Error(
                f"{node.label}: STRUT connects_to '{connects_to}' is the node's own parent"
            )

        # Special case: ASSEMBLY/MODEL parent — use ROOT sibling as from-anchor
        if parent.kind in (NodeKind.ASSEMBLY, NodeKind.MODEL):
            from_sibling = None
            fallback_sibling = None
            for sib_id in parent.children_ids:
                if sib_id == node.node_id:
                    continue
                sib = manifest.nodes.get(sib_id)
                if not sib or sib.node_id not in world_matrices:
                    continue
                if sib.node_id == target.node_id:
                    continue
                sib_socket = sib.attachment.socket_type if sib.attachment else None
                if sib_socket == SocketType.ROOT:
                    from_sibling = sib
                    break
                if fallback_sibling is None:
                    fallback_sibling = sib
            from_sibling = from_sibling or fallback_sibling
            if from_sibling is not None:
                parent_world = world_matrices[from_sibling.node_id]
                parent_bbox = world_bboxes.get(from_sibling.node_id) or cls._get_child_bbox(from_sibling)

        # Strut uses closest anchor points
        anchor_a, anchor_b = cls._compute_anchor_points(
            parent_world, parent_bbox,
            target_world, target_bbox,
            0.5
        )
        
        midpoint = [(anchor_a[i] + anchor_b[i]) / 2 for i in range(3)]
        direction = [anchor_b[i] - anchor_a[i] for i in range(3)]
        length = math.sqrt(sum(d * d for d in direction))
        if length < 1e-6:
            # Coaxial fallback: offset laterally like BRIDGE
            target_local_bbox = cls._get_child_bbox(target)
            lateral = (target_local_bbox.size_x / 2) or 0.01
            anchor_a = [parent_world.position[0] + lateral, parent_world.position[1], parent_world.position[2]]
            anchor_b = [target_world.position[0] + lateral, target_world.position[1], target_world.position[2]]
            midpoint = [(anchor_a[i] + anchor_b[i]) / 2 for i in range(3)]
            direction = [anchor_b[i] - anchor_a[i] for i in range(3)]
            length = math.sqrt(sum(d * d for d in direction))
            if length < 1e-6:
                raise Stage4Error(f"{node.label}: Zero-length strut")
        
        world_rotation = cls._rotation_to_direction(direction, length)
        
        # Build desired child world matrix
        child_world = cls._build_world_matrix(midpoint, world_rotation)
        
        # Convert to parent-local
        local_transform = cls._world_to_parent_local(parent_world, child_world)
        
        # Auto-size depth to span length
        if "stage2" in node.stage_outputs:
            node.stage_outputs["stage2"]["depth"] = round(length, 6)
        
        logger.info(
            f"STRUT (pass2 v2): {node.label} -> {connects_to}, length={length:.3f}, "
            f"local_pos={[round(p, 4) for p in local_transform.position]}"
        )
        
        resolved = ResolvedTransform(
            offset=list(local_transform.position),
            rotation=list(local_transform.rotation),
            resolution_method=f"STRUT:{connects_to}",
        )
        
        solution = AttachmentSolution(
            parent_id=node.parent_id or "",
            child_id=node.node_id,
            parent_socket="STRUT",
            local_transform=local_transform,
            source=f"STRUT:v2:{connects_to}",
        )
        
        return resolved, solution
    
    @classmethod
    def _resolve_radial_bridge_pass2_v2(
        cls,
        node: ManifestNode,
        manifest: BuildManifest,
        world_matrices: Dict[str, WorldMatrix],
        world_bboxes: Dict[str, BBox],
        sem: Dict,
    ) -> Tuple[ResolvedTransform, AttachmentSolution]:
        """RADIAL_BRIDGE pass 2 (Phase 3.5): Radial connector from parent to target.
        
        Computes desired child WORLD matrix, then converts to parent-local.
        """
        connects_to = sem.get("connects_to") or getattr(node.attachment, "connects_to", None)
        count = sem.get("radial_count") or getattr(node.attachment, "radial_count", None) or 4
        index = sem.get("radial_index") or getattr(node.attachment, "radial_index", None) or 0
        
        if not connects_to or connects_to == "__unknown__":
            raise Stage4Error(f"{node.label}: RADIAL_BRIDGE requires 'connects_to' — Stage 3 did not populate it")
        
        target = manifest.get_node_by_label(connects_to)
        if target is None:
            raise Stage4Error(f"{node.label}: RADIAL_BRIDGE target '{connects_to}' not found")
        if target.node_id not in world_matrices:
            raise Stage4Error(
                f"{node.label}: RADIAL_BRIDGE target '{connects_to}' world matrix not available"
            )
        
        parent = manifest.nodes.get(node.parent_id)
        if parent is None or parent.node_id not in world_matrices:
            raise Stage4Error(f"{node.label}: RADIAL_BRIDGE parent world matrix not available")
        
        parent_world = world_matrices[parent.node_id]
        target_world = world_matrices[target.node_id]
        parent_bbox = world_bboxes.get(parent.node_id) or cls._get_child_bbox(parent)
        target_bbox = world_bboxes.get(target.node_id) or cls._get_child_bbox(target)
        
        # Compute radial angle for this index
        angle = (2 * math.pi * index) / count
        
        # Anchor A: point on parent's circumference at this angle
        radius = max(parent_bbox.size_x, parent_bbox.size_y) / 2
        parent_pos = parent_world.position
        anchor_a = [
            parent_pos[0] + radius * math.cos(angle),
            parent_pos[1] + radius * math.sin(angle),
            parent_pos[2],
        ]
        
        # Anchor B: nearest point on target
        target_pos = target_world.position
        dx = target_pos[0] - anchor_a[0]
        dy = target_pos[1] - anchor_a[1]
        horiz_len = math.hypot(dx, dy) or 1.0
        ux, uy = dx / horiz_len, dy / horiz_len
        
        anchor_b = [
            target_pos[0] - ux * target_bbox.radius_toward(-ux, -uy),
            target_pos[1] - uy * target_bbox.radius_toward(-ux, -uy),
            target_pos[2] + target_bbox.min_z,
        ]
        
        midpoint = [(anchor_a[i] + anchor_b[i]) / 2 for i in range(3)]
        direction = [anchor_b[i] - anchor_a[i] for i in range(3)]
        length = math.sqrt(sum(d * d for d in direction))
        if length < 1e-6:
            # Coaxial fallback: offset vertically
            target_local_bbox = cls._get_child_bbox(target)
            anchor_b[2] = target_pos[2] + target_local_bbox.max_z
            midpoint = [(anchor_a[i] + anchor_b[i]) / 2 for i in range(3)]
            direction = [anchor_b[i] - anchor_a[i] for i in range(3)]
            length = math.sqrt(sum(d * d for d in direction))
            if length < 1e-6:
                raise Stage4Error(f"{node.label}: Zero-length radial bridge (index {index})")
        
        world_rotation = cls._rotation_to_direction(direction, length)
        
        # Build desired child world matrix
        child_world = cls._build_world_matrix(midpoint, world_rotation)
        
        # Convert to parent-local
        local_transform = cls._world_to_parent_local(parent_world, child_world)
        
        if "stage2" in node.stage_outputs:
            node.stage_outputs["stage2"]["depth"] = round(length, 6)
        
        logger.info(
            f"RADIAL_BRIDGE (pass2 v2): {node.label} -> {connects_to}, "
            f"index={index}/{count}, angle={math.degrees(angle):.1f}°, "
            f"local_pos={[round(p, 4) for p in local_transform.position]}"
        )
        
        resolved = ResolvedTransform(
            offset=list(local_transform.position),
            rotation=list(local_transform.rotation),
            resolution_method=f"RADIAL_BRIDGE:{connects_to}:{index}/{count}",
        )
        
        solution = AttachmentSolution(
            parent_id=node.parent_id or "",
            child_id=node.node_id,
            parent_socket="RADIAL_BRIDGE",
            local_transform=local_transform,
            source=f"RADIAL_BRIDGE:v2:{connects_to}:{index}/{count}",
        )
        
        return resolved, solution
