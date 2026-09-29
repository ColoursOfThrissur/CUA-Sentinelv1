"""Node type enums and classifications for progressive assembly.

This module defines the vocabulary for what kinds of things can exist in a build.
Designed to support not just static geometry but also:
- Animation and rigging (armatures, bones, constraints)
- Materials with node graphs
- Geometry nodes / procedural generation
- Physics simulations
- Particle systems
- Lighting setups
- Cameras and render settings

The type system is extensible - new NodeKind values can be added without
breaking existing builds (unknown kinds fall back to safe defaults).
"""

from enum import Enum
from typing import Set, FrozenSet


class NodeKind(str, Enum):
    """What structural/functional role a node plays in the build.
    
    Geometry Types (buildable in Blender as mesh/curve/surface):
    ─────────────────────────────────────────────────────────────
    MODEL       — Root node representing the complete model/scene.
    ASSEMBLY    — Container whose children are built then merged/grouped.
    PART        — Leaf geometry node: single primitive or imported mesh.
    INSTANCE    — Placement of a DEFINITION (linked duplicate or collection instance).
    DEFINITION  — Template geometry built once, instanced N times.
    
    Connector Types (relationships between geometry):
    ─────────────────────────────────────────────────────────────
    CONNECTOR   — Physical connection between parts (bolts, welds, joints).
    CABLE       — Flexible connector (ropes, wires, chains, hoses).
    
    Rigging & Animation Types:
    ─────────────────────────────────────────────────────────────
    ARMATURE    — Skeleton/rig container (Blender Armature object).
    BONE        — Single bone within an armature.
    CONSTRAINT  — Relationship constraint (IK, copy rotation, limit, etc.).
    DRIVER      — Driven property (expression-based animation).
    ACTION      — Animation action/clip that can be applied.
    
    Material & Shading Types:
    ─────────────────────────────────────────────────────────────
    MATERIAL    — Material definition (can have complex node graph).
    SHADER_NODE — Node within a material's shader graph.
    TEXTURE     — Texture resource (image, procedural, etc.).
    
    Procedural Types:
    ─────────────────────────────────────────────────────────────
    GEO_NODES   — Geometry Nodes modifier/tree.
    GEO_NODE    — Single node within a geometry node tree.
    MODIFIER    — Non-geo-nodes modifier (subdivision, bevel, array, etc.).
    
    Physics & Simulation Types:
    ─────────────────────────────────────────────────────────────
    PHYSICS     — Physics simulation settings (rigid body, cloth, fluid).
    PARTICLE    — Particle system definition.
    FORCE_FIELD — Force field (wind, turbulence, vortex, etc.).
    
    Scene Types:
    ─────────────────────────────────────────────────────────────
    LIGHT       — Light source (point, sun, spot, area).
    CAMERA      — Camera with settings.
    EMPTY       — Empty/null object (for organization, targets, etc.).
    COLLECTION  — Blender collection for organization.
    
    Abstract Types:
    ─────────────────────────────────────────────────────────────
    GROUP       — Logical grouping (not a Blender object, just organization).
    REFERENCE   — Reference to external asset (linked .blend, imported file).
    PLACEHOLDER — Placeholder for future implementation.
    """
    # Geometry
    MODEL = "model"
    ASSEMBLY = "assembly"
    PART = "part"
    INSTANCE = "instance"
    DEFINITION = "definition"
    
    # Connectors
    CONNECTOR = "connector"
    CABLE = "cable"
    
    # Rigging & Animation
    ARMATURE = "armature"
    BONE = "bone"
    CONSTRAINT = "constraint"
    DRIVER = "driver"
    ACTION = "action"
    
    # Materials & Shading
    MATERIAL = "material"
    SHADER_NODE = "shader_node"
    TEXTURE = "texture"
    
    # Procedural
    GEO_NODES = "geo_nodes"
    GEO_NODE = "geo_node"
    MODIFIER = "modifier"
    
    # Physics & Simulation
    PHYSICS = "physics"
    PARTICLE = "particle"
    FORCE_FIELD = "force_field"
    
    # Scene
    LIGHT = "light"
    CAMERA = "camera"
    EMPTY = "empty"
    COLLECTION = "collection"
    
    # Abstract
    GROUP = "group"
    REFERENCE = "reference"
    PLACEHOLDER = "placeholder"


# Classification sets for quick type checking
GEOMETRY_KINDS: FrozenSet[NodeKind] = frozenset({
    NodeKind.MODEL,
    NodeKind.ASSEMBLY,
    NodeKind.PART,
    NodeKind.INSTANCE,
    NodeKind.DEFINITION,
    NodeKind.CONNECTOR,
    NodeKind.CABLE,
})

RIGGING_KINDS: FrozenSet[NodeKind] = frozenset({
    NodeKind.ARMATURE,
    NodeKind.BONE,
    NodeKind.CONSTRAINT,
    NodeKind.DRIVER,
    NodeKind.ACTION,
})

MATERIAL_KINDS: FrozenSet[NodeKind] = frozenset({
    NodeKind.MATERIAL,
    NodeKind.SHADER_NODE,
    NodeKind.TEXTURE,
})

PROCEDURAL_KINDS: FrozenSet[NodeKind] = frozenset({
    NodeKind.GEO_NODES,
    NodeKind.GEO_NODE,
    NodeKind.MODIFIER,
})

PHYSICS_KINDS: FrozenSet[NodeKind] = frozenset({
    NodeKind.PHYSICS,
    NodeKind.PARTICLE,
    NodeKind.FORCE_FIELD,
})

SCENE_KINDS: FrozenSet[NodeKind] = frozenset({
    NodeKind.LIGHT,
    NodeKind.CAMERA,
    NodeKind.EMPTY,
    NodeKind.COLLECTION,
})

# Kinds that can be decomposed into children
DECOMPOSABLE_KINDS: FrozenSet[NodeKind] = frozenset({
    NodeKind.MODEL,
    NodeKind.ASSEMBLY,
    NodeKind.ARMATURE,      # Can decompose into bones
    NodeKind.GEO_NODES,     # Can decompose into geo_node children
    NodeKind.MATERIAL,      # Can decompose into shader_node children
    NodeKind.GROUP,
    NodeKind.COLLECTION,
})

# Kinds that are leaf nodes (cannot have children)
LEAF_KINDS: FrozenSet[NodeKind] = frozenset({
    NodeKind.PART,
    NodeKind.INSTANCE,
    NodeKind.BONE,
    NodeKind.CONSTRAINT,
    NodeKind.DRIVER,
    NodeKind.SHADER_NODE,
    NodeKind.GEO_NODE,
    NodeKind.TEXTURE,
    NodeKind.LIGHT,
    NodeKind.CAMERA,
    NodeKind.EMPTY,
    NodeKind.FORCE_FIELD,
    NodeKind.PLACEHOLDER,
})

# Kinds that create Blender objects
BLENDER_OBJECT_KINDS: FrozenSet[NodeKind] = frozenset({
    NodeKind.PART,
    NodeKind.INSTANCE,
    NodeKind.DEFINITION,
    NodeKind.CONNECTOR,
    NodeKind.CABLE,
    NodeKind.ARMATURE,
    NodeKind.LIGHT,
    NodeKind.CAMERA,
    NodeKind.EMPTY,
    NodeKind.FORCE_FIELD,
})

# Kinds that can be instanced (built once, placed many times)
INSTANCEABLE_KINDS: FrozenSet[NodeKind] = frozenset({
    NodeKind.DEFINITION,
    NodeKind.MATERIAL,
    NodeKind.GEO_NODES,
    NodeKind.ACTION,
    NodeKind.COLLECTION,
})


class NodeImportance(str, Enum):
    """How critical a node is to its parent's success.
    
    This affects failure handling:
    - REQUIRED nodes block parent completion if they fail
    - OPTIONAL nodes cause COMPLETED_DEGRADED status if skipped
    - DECORATIVE nodes are silently skipped without affecting status
    - STRUCTURAL nodes are like REQUIRED but also affect physics/rigging
    """
    REQUIRED = "required"       # Must succeed for parent to succeed
    STRUCTURAL = "structural"   # Required AND affects physics/rigging integrity
    OPTIONAL = "optional"       # Nice to have, degraded completion if missing
    DECORATIVE = "decorative"   # Purely cosmetic, skip silently
    GENERATED = "generated"     # Auto-generated (e.g., by geo nodes), can regenerate


class BuildPhase(str, Enum):
    """What phase of the build pipeline a node belongs to.
    
    Nodes are processed in phase order:
    1. STRUCTURE  — Core geometry that defines the shape
    2. DETAIL     — Surface details, bevels, subdivisions
    3. MATERIAL   — Materials and textures
    4. RIGGING    — Armatures, bones, constraints
    5. ANIMATION  — Actions, drivers, keyframes
    6. PHYSICS    — Physics simulations, particles
    7. LIGHTING   — Lights and environment
    8. RENDER     — Cameras and render settings
    """
    STRUCTURE = "structure"
    DETAIL = "detail"
    MATERIAL = "material"
    RIGGING = "rigging"
    ANIMATION = "animation"
    PHYSICS = "physics"
    LIGHTING = "lighting"
    RENDER = "render"


# Default phase for each node kind
DEFAULT_PHASE: dict[NodeKind, BuildPhase] = {
    # Geometry → STRUCTURE
    NodeKind.MODEL: BuildPhase.STRUCTURE,
    NodeKind.ASSEMBLY: BuildPhase.STRUCTURE,
    NodeKind.PART: BuildPhase.STRUCTURE,
    NodeKind.INSTANCE: BuildPhase.STRUCTURE,
    NodeKind.DEFINITION: BuildPhase.STRUCTURE,
    NodeKind.CONNECTOR: BuildPhase.STRUCTURE,
    NodeKind.CABLE: BuildPhase.STRUCTURE,
    NodeKind.GROUP: BuildPhase.STRUCTURE,
    NodeKind.COLLECTION: BuildPhase.STRUCTURE,
    NodeKind.EMPTY: BuildPhase.STRUCTURE,
    NodeKind.REFERENCE: BuildPhase.STRUCTURE,
    NodeKind.PLACEHOLDER: BuildPhase.STRUCTURE,
    
    # Modifiers → DETAIL
    NodeKind.MODIFIER: BuildPhase.DETAIL,
    NodeKind.GEO_NODES: BuildPhase.DETAIL,
    NodeKind.GEO_NODE: BuildPhase.DETAIL,
    
    # Materials → MATERIAL
    NodeKind.MATERIAL: BuildPhase.MATERIAL,
    NodeKind.SHADER_NODE: BuildPhase.MATERIAL,
    NodeKind.TEXTURE: BuildPhase.MATERIAL,
    
    # Rigging → RIGGING
    NodeKind.ARMATURE: BuildPhase.RIGGING,
    NodeKind.BONE: BuildPhase.RIGGING,
    NodeKind.CONSTRAINT: BuildPhase.RIGGING,
    
    # Animation → ANIMATION
    NodeKind.DRIVER: BuildPhase.ANIMATION,
    NodeKind.ACTION: BuildPhase.ANIMATION,
    
    # Physics → PHYSICS
    NodeKind.PHYSICS: BuildPhase.PHYSICS,
    NodeKind.PARTICLE: BuildPhase.PHYSICS,
    NodeKind.FORCE_FIELD: BuildPhase.PHYSICS,
    
    # Lighting → LIGHTING
    NodeKind.LIGHT: BuildPhase.LIGHTING,
    
    # Render → RENDER
    NodeKind.CAMERA: BuildPhase.RENDER,
}


class PrimitiveType(str, Enum):
    """Blender primitive types that can be created.
    
    These map directly to Blender's mesh primitives and other object types.
    Used by PART nodes to specify what geometry to create.
    """
    # Mesh primitives
    BOX = "box"
    SPHERE = "sphere"
    CYLINDER = "cylinder"
    CONE = "cone"
    TORUS = "torus"
    PLANE = "plane"
    CIRCLE = "circle"
    GRID = "grid"
    MONKEY = "monkey"  # Suzanne, useful for testing
    
    # Extended mesh types
    HEMISPHERE = "hemisphere"       # Half sphere (sphere + bisect)
    U_SHAPE = "u_shape"             # Half torus (torus + bisect) — padlock shackle, handles
    CAPSULE = "capsule"             # Cylinder with hemisphere caps
    WEDGE = "wedge"                 # Triangular prism
    PYRAMID = "pyramid"             # 4-sided pyramid
    PRISM = "prism"                 # N-sided prism
    
    # Curve primitives
    BEZIER_CURVE = "bezier_curve"
    NURBS_CURVE = "nurbs_curve"
    PATH = "path"
    BEZIER_CIRCLE = "bezier_circle"
    NURBS_CIRCLE = "nurbs_circle"
    
    # Surface primitives
    NURBS_SURFACE = "nurbs_surface"
    
    # Text
    TEXT = "text"
    
    # Special
    EMPTY = "empty"
    LATTICE = "lattice"
    ARMATURE = "armature"
    
    # Imported/referenced
    IMPORTED_MESH = "imported_mesh"
    LINKED_OBJECT = "linked_object"


# Primitives that are mesh objects
MESH_PRIMITIVES: FrozenSet[PrimitiveType] = frozenset({
    PrimitiveType.BOX,
    PrimitiveType.SPHERE,
    PrimitiveType.CYLINDER,
    PrimitiveType.CONE,
    PrimitiveType.TORUS,
    PrimitiveType.PLANE,
    PrimitiveType.CIRCLE,
    PrimitiveType.GRID,
    PrimitiveType.MONKEY,
    PrimitiveType.HEMISPHERE,
    PrimitiveType.U_SHAPE,
    PrimitiveType.CAPSULE,
    PrimitiveType.WEDGE,
    PrimitiveType.PYRAMID,
    PrimitiveType.PRISM,
})

# Primitives that are curve objects
CURVE_PRIMITIVES: FrozenSet[PrimitiveType] = frozenset({
    PrimitiveType.BEZIER_CURVE,
    PrimitiveType.NURBS_CURVE,
    PrimitiveType.PATH,
    PrimitiveType.BEZIER_CIRCLE,
    PrimitiveType.NURBS_CIRCLE,
})


class SocketType(str, Enum):
    """How a child node attaches to its parent.
    
    Socket types define the geometric relationship between parent and child.
    Stage 4 Resolver uses these to compute exact transforms.
    
    Positional Sockets (relative to parent's bounding box):
    ───────────────────────────────────────────────────────
    ROOT            — No parent, this is the root/origin
    TOP_CENTER      — Centered on parent's top face
    BOTTOM_CENTER   — Centered on parent's bottom face
    FRONT_CENTER    — Centered on parent's front face (-Y)
    BACK_CENTER     — Centered on parent's back face (+Y)
    LEFT_CENTER     — Centered on parent's left face (-X)
    RIGHT_CENTER    — Centered on parent's right face (+X)
    
    Corner Sockets (8 corners of bounding box):
    ───────────────────────────────────────────────────────
    CORNER          — At a corner, requires corner_position semantic
    
    Edge Sockets (12 edges of bounding box):
    ───────────────────────────────────────────────────────
    EDGE            — Along an edge, requires edge_position semantic
    
    Face Sockets (on a face with offset):
    ───────────────────────────────────────────────────────
    TOP_FACE        — On top face with lateral offset
    BOTTOM_FACE     — On bottom face with lateral offset
    FRONT_FACE      — On front face with height offset
    BACK_FACE       — On back face with height offset
    LEFT_FACE       — On left face with height offset
    RIGHT_FACE      — On right face with height offset
    
    Axis-Aligned Sockets (for elongated parts):
    ───────────────────────────────────────────────────────
    LEFT_END        — At -X end of parent's extent
    RIGHT_END       — At +X end of parent's extent
    TOP_END         — At +Z end of parent's extent
    BOTTOM_END      — At -Z end of parent's extent
    FRONT_END       — At -Y end of parent's extent
    BACK_END        — At +Y end of parent's extent
    
    Through/Pierce Sockets (child passes through parent):
    ───────────────────────────────────────────────────────
    THROUGH_AXIS    — Child passes through parent (axles, crossbars)
    
    Array/Radial Sockets (multiple items):
    ───────────────────────────────────────────────────────
    ARRAY_MEMBER    — Part of linear array on a surface
    RADIAL          — Evenly spaced around parent's circumference
    RADIAL_BRIDGE   — Radial connector to another named part
    
    Connector Sockets (structural connections):
    ───────────────────────────────────────────────────────
    STRUT           — Diagonal connector between two parts
    BRIDGE          — Horizontal connector between two parts
    
    Boolean Sockets (subtractive):
    ───────────────────────────────────────────────────────
    BOOLEAN_CUT     — Subtracted from parent (holes, grooves, cutouts)
    BOOLEAN_UNION   — Added/merged with parent
    BOOLEAN_INTERSECT — Intersection with parent
    
    Inset/Embedded Sockets:
    ───────────────────────────────────────────────────────
    INSET           — Recessed into parent's surface
    EMBEDDED        — Fully inside parent's volume
    SURFACE_FOLLOW  — Follows parent's surface contour
    
    Rigging Sockets:
    ───────────────────────────────────────────────────────
    BONE_HEAD       — At bone's head position
    BONE_TAIL       — At bone's tail position
    BONE_ALONG      — Along bone's length (0-1 parameter)
    
    Constraint Sockets:
    ───────────────────────────────────────────────────────
    CONSTRAINED_TO  — Position/rotation constrained to target
    PARENTED_TO     — Blender parent relationship
    
    Procedural Sockets:
    ───────────────────────────────────────────────────────
    SCATTER         — Scattered on parent's surface (grass, debris)
    CURVE_FOLLOW    — Follows a curve path
    VOLUME_FILL     — Fills parent's volume
    """
    # Positional
    ROOT = "ROOT"
    TOP_CENTER = "TOP_CENTER"
    BOTTOM_CENTER = "BOTTOM_CENTER"
    FRONT_CENTER = "FRONT_CENTER"
    BACK_CENTER = "BACK_CENTER"
    LEFT_CENTER = "LEFT_CENTER"
    RIGHT_CENTER = "RIGHT_CENTER"
    
    # Corner
    CORNER = "CORNER"
    
    # Edge
    EDGE = "EDGE"
    
    # Face with offset
    TOP_FACE = "TOP_FACE"
    BOTTOM_FACE = "BOTTOM_FACE"
    FRONT_FACE = "FRONT_FACE"
    BACK_FACE = "BACK_FACE"
    LEFT_FACE = "LEFT_FACE"
    RIGHT_FACE = "RIGHT_FACE"
    
    # Axis ends
    LEFT_END = "LEFT_END"
    RIGHT_END = "RIGHT_END"
    TOP_END = "TOP_END"
    BOTTOM_END = "BOTTOM_END"
    FRONT_END = "FRONT_END"
    BACK_END = "BACK_END"
    
    # Through
    THROUGH_AXIS = "THROUGH_AXIS"
    
    # Array/Radial
    ARRAY_MEMBER = "ARRAY_MEMBER"
    RADIAL = "RADIAL"
    RADIAL_BRIDGE = "RADIAL_BRIDGE"
    
    # Connectors
    STRUT = "STRUT"
    BRIDGE = "BRIDGE"
    
    # Boolean
    BOOLEAN_CUT = "BOOLEAN_CUT"
    BOOLEAN_UNION = "BOOLEAN_UNION"
    BOOLEAN_INTERSECT = "BOOLEAN_INTERSECT"
    
    # Inset/Embedded
    INSET = "INSET"
    EMBEDDED = "EMBEDDED"
    SURFACE_FOLLOW = "SURFACE_FOLLOW"
    
    # Rigging
    BONE_HEAD = "BONE_HEAD"
    BONE_TAIL = "BONE_TAIL"
    BONE_ALONG = "BONE_ALONG"
    
    # Constraint
    CONSTRAINED_TO = "CONSTRAINED_TO"
    PARENTED_TO = "PARENTED_TO"
    
    # Procedural
    SCATTER = "SCATTER"
    CURVE_FOLLOW = "CURVE_FOLLOW"
    VOLUME_FILL = "VOLUME_FILL"
    
    # Relative positioning (closed vocabulary, no LLM-computed numbers)
    RELATIVE_TO = "RELATIVE_TO"


# Socket types that require specific semantic fields
SOCKET_REQUIRED_SEMANTICS: dict[SocketType, list[str]] = {
    SocketType.CORNER: ["corner_position"],
    SocketType.EDGE: ["edge_position"],
    SocketType.THROUGH_AXIS: ["pierce_direction"],
    SocketType.ARRAY_MEMBER: ["array_axis", "array_count", "array_index"],
    SocketType.RADIAL: ["radial_count", "radial_index"],
    SocketType.RADIAL_BRIDGE: ["connects_to", "radial_count", "radial_index"],
    SocketType.STRUT: ["connects_to"],
    SocketType.BRIDGE: ["connects_to", "position_fraction"],
    SocketType.RELATIVE_TO: ["relative_to", "direction", "gap"],
    SocketType.BOOLEAN_CUT: [],  # cut_face is optional, defaults to nearest
    SocketType.INSET: ["inset_face"],
    SocketType.BONE_ALONG: ["bone_parameter"],  # 0-1 along bone length
    SocketType.SCATTER: ["scatter_density"],
    SocketType.CURVE_FOLLOW: ["curve_target", "curve_parameter"],
}

# Socket types that involve boolean operations
BOOLEAN_SOCKETS: FrozenSet[SocketType] = frozenset({
    SocketType.BOOLEAN_CUT,
    SocketType.BOOLEAN_UNION,
    SocketType.BOOLEAN_INTERSECT,
})

# Socket types that connect to another named part (not just parent)
CONNECTOR_SOCKETS: FrozenSet[SocketType] = frozenset({
    SocketType.RADIAL_BRIDGE,
    SocketType.STRUT,
    SocketType.BRIDGE,
    SocketType.RELATIVE_TO,
    SocketType.CONSTRAINED_TO,
})

# Socket types that require cross-reference resolution (two-pass)
# These reference another named part and need that part's world position
CROSS_REFERENCE_SOCKETS: FrozenSet[SocketType] = frozenset({
    SocketType.RADIAL_BRIDGE,
    SocketType.STRUT,
    SocketType.BRIDGE,
    SocketType.RELATIVE_TO,
})


# ═══════════════════════════════════════════════════════════════════════════
# SINGLE SOURCE OF TRUTH: Blender Directional Convention
# ═══════════════════════════════════════════════════════════════════════════
# Blender uses right-handed coordinate system:
#   +X = right,  -X = left
#   +Y = back,   -Y = front  (CRITICAL: opposite of many other 3D apps)
#   +Z = up,     -Z = down
#
# ALL socket resolvers MUST use these constants, not hardcoded signs.
# ═══════════════════════════════════════════════════════════════════════════

class BlenderAxis:
    """Single source of truth for Blender's directional conventions.
    
    Every socket resolver must import and use these constants.
    DO NOT hardcode directional signs anywhere else.
    """
    # Axis indices
    X = 0
    Y = 1
    Z = 2
    
    # Direction signs (multiply by these to get correct direction)
    RIGHT = +1   # +X
    LEFT = -1    # -X
    BACK = +1    # +Y (Blender convention: +Y is BACK)
    FRONT = -1   # -Y (Blender convention: -Y is FRONT)
    UP = +1      # +Z
    DOWN = -1    # -Z
    
    @classmethod
    def get_direction(cls, direction_name: str) -> tuple[int, int]:
        """Get (axis_index, sign) for a direction name.
        
        Args:
            direction_name: One of 'left', 'right', 'front', 'back', 'above', 'below'
            
        Returns:
            Tuple of (axis_index, sign_multiplier)
            
        Raises:
            ValueError: If direction_name is not recognized
        """
        mapping = {
            "left": (cls.X, cls.LEFT),
            "right": (cls.X, cls.RIGHT),
            "front": (cls.Y, cls.FRONT),
            "back": (cls.Y, cls.BACK),
            "above": (cls.Z, cls.UP),
            "below": (cls.Z, cls.DOWN),
            # Aliases
            "up": (cls.Z, cls.UP),
            "down": (cls.Z, cls.DOWN),
            "top": (cls.Z, cls.UP),
            "bottom": (cls.Z, cls.DOWN),
            "forward": (cls.Y, cls.FRONT),
            "backward": (cls.Y, cls.BACK),
        }
        if direction_name.lower() not in mapping:
            raise ValueError(f"Unknown direction: {direction_name}. Valid: {list(mapping.keys())}")
        return mapping[direction_name.lower()]
    
    @classmethod
    def offset_for_corner(
        cls,
        is_front: bool,
        is_left: bool,
        is_bottom: bool,
        half_x: float,
        half_y: float,
        half_z: float,
        inset_factor: float = 0.8,
    ) -> tuple[float, float, float]:
        """Compute corner offset using canonical direction signs.
        
        Args:
            is_front: True if front corner (-Y in Blender)
            is_left: True if left corner (-X)
            is_bottom: True if bottom corner (-Z)
            half_x, half_y, half_z: Half-extents of parent bbox
            inset_factor: How far toward edge (0=center, 1=edge)
            
        Returns:
            (offset_x, offset_y, offset_z) tuple
        """
        # X: left = -X, right = +X
        x_sign = cls.LEFT if is_left else cls.RIGHT
        offset_x = x_sign * half_x * inset_factor
        
        # Y: front = -Y, back = +Y (Blender convention)
        y_sign = cls.FRONT if is_front else cls.BACK
        offset_y = y_sign * half_y * inset_factor
        
        # Z: bottom = -Z, top = +Z
        z_sign = cls.DOWN if is_bottom else cls.UP
        offset_z = z_sign * half_z * inset_factor
        
        return (offset_x, offset_y, offset_z)


def get_phase_for_kind(kind: NodeKind) -> BuildPhase:
    """Get the default build phase for a node kind."""
    return DEFAULT_PHASE.get(kind, BuildPhase.STRUCTURE)


def is_decomposable(kind: NodeKind) -> bool:
    """Check if a node kind can be decomposed into children."""
    return kind in DECOMPOSABLE_KINDS


def is_leaf(kind: NodeKind) -> bool:
    """Check if a node kind is always a leaf (no children)."""
    return kind in LEAF_KINDS


def creates_blender_object(kind: NodeKind) -> bool:
    """Check if a node kind creates a Blender object."""
    return kind in BLENDER_OBJECT_KINDS


def is_geometry(kind: NodeKind) -> bool:
    """Check if a node kind represents geometry."""
    return kind in GEOMETRY_KINDS


def is_instanceable(kind: NodeKind) -> bool:
    """Check if a node kind can be instanced."""
    return kind in INSTANCEABLE_KINDS
