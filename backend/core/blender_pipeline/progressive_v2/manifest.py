"""Build Manifest — persistent state for progressive assembly builds.

The manifest is the single source of truth for:
- What nodes exist in the hierarchy
- What state each node is in
- What stage outputs have been computed
- What Blender objects have been created
- Checkpoint history for crash recovery

All node mutations go through transition() which enforces valid state machine edges.
Persisted to JSON in data/builds_v2/{model_id}/manifest.json.

Blueprint references: §6 (manifest), §7 (temp vs permanent), §8 (node states),
§17 (degraded completion), §19 (checkpointing).
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Callable

from .node_types import (
    NodeKind,
    NodeImportance,
    BuildPhase,
    SocketType,
    PrimitiveType,
    is_decomposable,
    is_leaf,
    get_phase_for_kind,
)
from .transforms import LocalTransform, WorldMatrix, NodeTransformState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data directory
# ---------------------------------------------------------------------------
_DATA_ROOT = Path(__file__).resolve().parent.parent.parent.parent / "data" / "builds_v2"


def _builds_dir() -> Path:
    """Return (and lazily create) the root builds directory."""
    _DATA_ROOT.mkdir(parents=True, exist_ok=True)
    return _DATA_ROOT


# ---------------------------------------------------------------------------
# Node State Machine — Blueprint §8
# ---------------------------------------------------------------------------

class NodeState(str, Enum):
    """Lifecycle state of a node.
    
    States and their meanings:
    - PLANNED: Initial state, node exists but not yet processed
    - DECOMPOSING: Being broken into children (ASSEMBLY/MODEL only)
    - READY: Ready for next action (build for PART, merge for ASSEMBLY)
    - BUILDING: Geometry being created in Blender
    - VERIFYING: Verification in progress
    - VERIFIED: Successfully built and verified
    - MERGING: Children being merged into assembly
    - FAILED: Build or verification failed
    - RETRYING: Scheduled for retry after failure
    - SKIPPED: Skipped (optional node that failed too many times)
    - STALE: Needs rebuild due to dependency change
    """
    PLANNED = "planned"
    DECOMPOSING = "decomposing"
    READY = "ready"
    BUILDING = "building"
    VERIFYING = "verifying"
    VERIFIED = "verified"
    MERGING = "merging"
    FAILED = "failed"
    RETRYING = "retrying"
    SKIPPED = "skipped"
    STALE = "stale"


# Valid state transitions - any edge not listed is illegal
_VALID_TRANSITIONS: Dict[NodeState, Set[NodeState]] = {
    NodeState.PLANNED:     {NodeState.DECOMPOSING, NodeState.READY, NodeState.FAILED},
    NodeState.DECOMPOSING: {NodeState.READY, NodeState.FAILED},
    NodeState.READY:       {NodeState.BUILDING, NodeState.MERGING, NodeState.DECOMPOSING, NodeState.FAILED},
    NodeState.BUILDING:    {NodeState.VERIFYING, NodeState.FAILED},
    NodeState.VERIFYING:   {NodeState.VERIFIED, NodeState.FAILED},
    NodeState.VERIFIED:    {NodeState.MERGING, NodeState.STALE},
    NodeState.MERGING:     {NodeState.VERIFIED, NodeState.FAILED},
    NodeState.FAILED:      {NodeState.RETRYING, NodeState.SKIPPED},
    NodeState.RETRYING:    {NodeState.READY, NodeState.SKIPPED},
    NodeState.SKIPPED:     set(),  # Terminal
    NodeState.STALE:       {NodeState.READY},
}


class CompletionStatus(str, Enum):
    """Overall build outcome. Blueprint §17."""
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    COMPLETED_DEGRADED = "completed_degraded"
    FAILED = "failed"


# ---------------------------------------------------------------------------
# Geometry Specification — what to build
# ---------------------------------------------------------------------------

@dataclass
class GeometrySpec:
    """Specification for creating geometry in Blender.
    
    This captures everything needed to create a primitive or import a mesh.
    Used by PART nodes.
    """
    primitive: PrimitiveType = PrimitiveType.BOX
    
    # Dimensions (primitive-specific)
    size: Optional[List[float]] = None          # [x, y, z] for box
    radius: Optional[float] = None              # For sphere, cylinder, cone
    radius2: Optional[float] = None             # For cone (top radius)
    depth: Optional[float] = None               # For cylinder, cone
    segments: int = 32                          # Subdivision segments
    rings: int = 16                             # For sphere, torus
    major_radius: Optional[float] = None        # For torus
    minor_radius: Optional[float] = None        # For torus
    
    # For imported/referenced geometry
    source_path: Optional[str] = None
    source_object: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        d = {"primitive": self.primitive.value}
        if self.size: d["size"] = self.size
        if self.radius is not None: d["radius"] = self.radius
        if self.radius2 is not None: d["radius2"] = self.radius2
        if self.depth is not None: d["depth"] = self.depth
        if self.segments != 32: d["segments"] = self.segments
        if self.rings != 16: d["rings"] = self.rings
        if self.major_radius is not None: d["major_radius"] = self.major_radius
        if self.minor_radius is not None: d["minor_radius"] = self.minor_radius
        if self.source_path: d["source_path"] = self.source_path
        if self.source_object: d["source_object"] = self.source_object
        return d
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> GeometrySpec:
        return cls(
            primitive=PrimitiveType(d.get("primitive", "box")),
            size=d.get("size"),
            radius=d.get("radius"),
            radius2=d.get("radius2"),
            depth=d.get("depth"),
            segments=d.get("segments", 32),
            rings=d.get("rings", 16),
            major_radius=d.get("major_radius"),
            minor_radius=d.get("minor_radius"),
            source_path=d.get("source_path"),
            source_object=d.get("source_object"),
        )


# ---------------------------------------------------------------------------
# Material Specification
# ---------------------------------------------------------------------------

@dataclass
class MaterialSpec:
    """Material specification for a node.
    
    Supports both simple color-based materials, preset names,
    and full PBR properties.
    """
    name: Optional[str] = None
    
    # Preset name (if set, overrides individual properties)
    preset: Optional[str] = None
    
    # Simple PBR properties
    base_color: List[float] = field(default_factory=lambda: [0.8, 0.8, 0.8, 1.0])
    metallic: float = 0.0
    roughness: float = 0.5
    
    # Emission
    emission_color: Optional[List[float]] = None
    emission_strength: float = 0.0
    
    # Transmission (glass)
    transmission: float = 0.0
    ior: float = 1.45
    
    # Subsurface
    subsurface: float = 0.0
    subsurface_color: Optional[List[float]] = None
    
    # Clearcoat
    clearcoat: float = 0.0
    clearcoat_roughness: float = 0.03
    
    # Sheen (fabric)
    sheen: float = 0.0
    sheen_tint: float = 0.5
    
    # Specular
    specular: float = 0.5
    
    # Advanced
    use_nodes: bool = True
    node_tree_name: Optional[str] = None  # Reference to shared node tree
    
    def to_dict(self) -> Dict[str, Any]:
        d = {
            "base_color": self.base_color,
            "metallic": self.metallic,
            "roughness": self.roughness,
            "transmission": self.transmission,
            "ior": self.ior,
            "subsurface": self.subsurface,
            "clearcoat": self.clearcoat,
            "clearcoat_roughness": self.clearcoat_roughness,
            "sheen": self.sheen,
            "sheen_tint": self.sheen_tint,
            "specular": self.specular,
        }
        if self.name: d["name"] = self.name
        if self.preset: d["preset"] = self.preset
        if self.emission_color: 
            d["emission_color"] = self.emission_color
            d["emission_strength"] = self.emission_strength
        if self.subsurface_color:
            d["subsurface_color"] = self.subsurface_color
        if self.node_tree_name: d["node_tree_name"] = self.node_tree_name
        return d
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> MaterialSpec:
        return cls(
            name=d.get("name"),
            preset=d.get("preset"),
            base_color=d.get("base_color", [0.8, 0.8, 0.8, 1.0]),
            metallic=d.get("metallic", 0.0),
            roughness=d.get("roughness", 0.5),
            emission_color=d.get("emission_color"),
            emission_strength=d.get("emission_strength", 0.0),
            transmission=d.get("transmission", 0.0),
            ior=d.get("ior", 1.45),
            subsurface=d.get("subsurface", 0.0),
            subsurface_color=d.get("subsurface_color"),
            clearcoat=d.get("clearcoat", 0.0),
            clearcoat_roughness=d.get("clearcoat_roughness", 0.03),
            sheen=d.get("sheen", 0.0),
            sheen_tint=d.get("sheen_tint", 0.5),
            specular=d.get("specular", 0.5),
            node_tree_name=d.get("node_tree_name"),
        )
    
    @classmethod
    def from_preset(cls, preset_name: str) -> MaterialSpec:
        """Create MaterialSpec from a preset name."""
        from .materials import get_material_preset
        preset = get_material_preset(preset_name)
        if not preset:
            return cls(preset=preset_name)  # Store name, resolve later
        return cls(
            name=preset.name,
            preset=preset_name,
            base_color=preset.base_color,
            metallic=preset.metallic,
            roughness=preset.roughness,
            emission_color=preset.emission_color,
            emission_strength=preset.emission_strength,
            transmission=preset.transmission,
            ior=preset.ior,
            subsurface=preset.subsurface,
            subsurface_color=preset.subsurface_color,
            clearcoat=preset.clearcoat,
            clearcoat_roughness=preset.clearcoat_roughness,
            sheen=preset.sheen,
            sheen_tint=preset.sheen_tint,
            specular=preset.specular,
        )


# ---------------------------------------------------------------------------
# Attachment Specification — how child connects to parent
# ---------------------------------------------------------------------------

@dataclass
class AttachmentSpec:
    """How a node attaches to its parent.
    
    Combines socket type with semantic hints that Stage 4 uses
    to compute exact transforms.
    """
    socket_type: SocketType = SocketType.ROOT
    
    # Computed transform (filled by Stage 4)
    local_offset: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    local_rotation: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    
    # Semantic hints (filled by Stage 3, used by Stage 4)
    # For CORNER
    corner_position: Optional[str] = None  # e.g., "bottom_front_left"
    
    # For EDGE
    edge_position: Optional[str] = None    # e.g., "top_front"
    edge_offset: float = 0.0               # -1 to 1 along edge
    
    # For THROUGH_AXIS
    pierce_direction: Optional[str] = None  # "left_right", "front_back", "up_down"
    height_hint: Optional[str] = None       # "near_top", "center", "near_bottom"
    
    # For ARRAY_MEMBER
    array_axis: Optional[str] = None        # "x", "y", "z"
    array_count: Optional[int] = None
    array_index: Optional[int] = None
    spacing_hint: Optional[str] = None      # "tight", "normal", "spread"
    
    # For RADIAL, RADIAL_BRIDGE
    radial_count: Optional[int] = None
    radial_index: Optional[int] = None
    
    # For STRUT, BRIDGE, RADIAL_BRIDGE
    connects_to: Optional[str] = None       # Label of target part
    
    # For BRIDGE
    position_fraction: Optional[str] = None  # "start", "quarter", "middle", "three_quarter", "end"
    
    # For RELATIVE_TO (closed vocabulary - no LLM-computed numbers)
    relative_to: Optional[str] = None        # Label of reference part
    direction: Optional[str] = None          # "left", "right", "front", "back", "above", "below"
    gap: Optional[str] = None                # "touching", "small", "medium", "large"
    align: Optional[str] = None              # "same_position", "same_level"
    
    # For face mounts
    face_position: Optional[str] = None     # "center", "near_left", etc.
    
    # For BOOLEAN_CUT
    cut_face: Optional[str] = None          # "top", "front", etc.
    
    # For INSET
    inset_face: Optional[str] = None
    inset_depth: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        d = {
            "socket_type": self.socket_type.value,
            "local_offset": self.local_offset,
            "local_rotation": self.local_rotation,
        }
        # Only include non-None semantic hints
        for attr in ["corner_position", "edge_position", "pierce_direction", 
                     "height_hint", "array_axis", "spacing_hint", "connects_to",
                     "face_position", "cut_face", "inset_face", "position_fraction",
                     "relative_to", "direction", "gap", "align"]:
            val = getattr(self, attr)
            if val is not None:
                d[attr] = val
        for attr in ["edge_offset", "inset_depth"]:
            val = getattr(self, attr)
            if val != 0.0:
                d[attr] = val
        for attr in ["array_count", "array_index", "radial_count", "radial_index"]:
            val = getattr(self, attr)
            if val is not None:
                d[attr] = val
        return d
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> AttachmentSpec:
        return cls(
            socket_type=SocketType(d.get("socket_type", "ROOT")),
            local_offset=d.get("local_offset", [0.0, 0.0, 0.0]),
            local_rotation=d.get("local_rotation", [0.0, 0.0, 0.0]),
            corner_position=d.get("corner_position"),
            edge_position=d.get("edge_position"),
            edge_offset=d.get("edge_offset", 0.0),
            pierce_direction=d.get("pierce_direction"),
            height_hint=d.get("height_hint"),
            array_axis=d.get("array_axis"),
            array_count=d.get("array_count"),
            array_index=d.get("array_index"),
            spacing_hint=d.get("spacing_hint"),
            radial_count=d.get("radial_count"),
            radial_index=d.get("radial_index"),
            connects_to=d.get("connects_to"),
            position_fraction=d.get("position_fraction"),
            relative_to=d.get("relative_to"),
            direction=d.get("direction"),
            gap=d.get("gap"),
            align=d.get("align"),
            face_position=d.get("face_position"),
            cut_face=d.get("cut_face"),
            inset_face=d.get("inset_face"),
            inset_depth=d.get("inset_depth", 0.0),
        )


# ---------------------------------------------------------------------------
# ManifestNode — a single node in the build hierarchy
# ---------------------------------------------------------------------------

@dataclass
class ManifestNode:
    """A single node in the build hierarchy.
    
    Contains everything needed to build, verify, retry, and merge this node.
    Supports geometry, materials, rigging, animation - the full Blender feature set.
    """
    # Identity
    node_id: str
    label: str
    kind: NodeKind = NodeKind.PART
    
    # State machine
    state: NodeState = NodeState.PLANNED
    importance: NodeImportance = NodeImportance.REQUIRED
    phase: BuildPhase = BuildPhase.STRUCTURE
    
    # Containment hierarchy (parent-child tree)
    parent_id: Optional[str] = None
    children_ids: List[str] = field(default_factory=list)
    
    # Dependency graph (separate from containment - for build ordering)
    dependency_ids: List[str] = field(default_factory=list)
    
    # Instance support (§14)
    instance_of: Optional[str] = None  # Points to DEFINITION node_id
    instance_index: Optional[int] = None  # Which instance (0, 1, 2, ...)
    
    # Retry tracking
    retry_count: int = 0
    max_retries: int = 3
    error_message: Optional[str] = None
    error_stage: Optional[str] = None  # Which stage failed
    
    # Hierarchy metadata
    hierarchy_depth: int = 0
    
    # Geometry specification (for PART nodes)
    geometry: Optional[GeometrySpec] = None
    
    # Material specification
    material: Optional[MaterialSpec] = None
    
    # Attachment to parent
    attachment: AttachmentSpec = field(default_factory=AttachmentSpec)
    
    # Stage outputs (keyed by stage: "stage0", "stage1", "stage2", "stage3", "stage4")
    stage_outputs: Dict[str, Any] = field(default_factory=dict)
    
    # Verification result from last build attempt
    verification_result: Optional[Dict[str, Any]] = None
    
    # Blender objects created for this node
    blender_objects: List[str] = field(default_factory=list)
    generation_id: Optional[str] = None
    
    # Bounding box after build (world space)
    bounding_box: Optional[Dict[str, List[float]]] = None  # {"min": [x,y,z], "max": [x,y,z]}
    
    # World transform after build (set by executor, used by children)
    # LEGACY: These fields are kept for backward compatibility during migration
    world_position: Optional[List[float]] = None  # [x, y, z] in world coords
    world_rotation: Optional[List[float]] = None  # [rx, ry, rz] in radians
    
    # NEW: Hierarchical transform system (Phase 1)
    # local_transform is authoritative, world_matrix is derived
    # See transforms.py for the full transform hierarchy architecture
    transform_state: NodeTransformState = field(default_factory=NodeTransformState)
    
    # For ASSEMBLY nodes: public interface for parent consumption (§13)
    public_sockets: List[Dict[str, Any]] = field(default_factory=list)
    
    # Modifiers to apply after geometry creation
    modifiers: List[Dict[str, Any]] = field(default_factory=list)
    
    # Constraints (for rigging)
    constraints: List[Dict[str, Any]] = field(default_factory=list)
    
    # Animation data
    animation_data: Optional[Dict[str, Any]] = None
    
    # Physics settings
    physics_settings: Optional[Dict[str, Any]] = None
    
    # Custom properties (extensible metadata)
    custom_props: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Set default phase based on kind if not specified."""
        if self.phase == BuildPhase.STRUCTURE:
            self.phase = get_phase_for_kind(self.kind)
    
    def is_leaf(self) -> bool:
        """True if this node has no children."""
        return len(self.children_ids) == 0
    
    def is_buildable(self) -> bool:
        """True if this is a node that creates Blender geometry."""
        return self.kind in (NodeKind.PART, NodeKind.CONNECTOR, NodeKind.CABLE,
                            NodeKind.LIGHT, NodeKind.CAMERA, NodeKind.EMPTY)
    
    def is_decomposable(self) -> bool:
        """True if this node can be decomposed into children."""
        return is_decomposable(self.kind) and self.is_leaf()
    
    def needs_decomposition(self) -> bool:
        """True if this is an ASSEMBLY/MODEL that hasn't been decomposed yet."""
        return self.kind in (NodeKind.MODEL, NodeKind.ASSEMBLY) and self.is_leaf()
    
    def needs_stages(self) -> bool:
        """True if this PART node needs Stage 2/3/4 before building."""
        return self.kind == NodeKind.PART and "stage4" not in self.stage_outputs
    
    def can_retry(self) -> bool:
        """True if this node can be retried."""
        return self.state == NodeState.FAILED and self.retry_count < self.max_retries
    
    def get_world_transform(self) -> Dict[str, List[float]]:
        """Get world-space transform (computed during build)."""
        return {
            "location": self.attachment.local_offset,
            "rotation": self.attachment.local_rotation,
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize for JSON persistence."""
        d = {
            "node_id": self.node_id,
            "label": self.label,
            "kind": self.kind.value,
            "state": self.state.value,
            "importance": self.importance.value,
            "phase": self.phase.value,
            "parent_id": self.parent_id,
            "children_ids": list(self.children_ids),
            "dependency_ids": list(self.dependency_ids),
            "hierarchy_depth": self.hierarchy_depth,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "blender_objects": list(self.blender_objects),
            "stage_outputs": self.stage_outputs,
            "attachment": self.attachment.to_dict(),
        }
        
        # Optional fields - only include if set
        if self.instance_of: d["instance_of"] = self.instance_of
        if self.instance_index is not None: d["instance_index"] = self.instance_index
        if self.error_message: d["error_message"] = self.error_message
        if self.error_stage: d["error_stage"] = self.error_stage
        if self.geometry: d["geometry"] = self.geometry.to_dict()
        if self.material: d["material"] = self.material.to_dict()
        if self.verification_result: d["verification_result"] = self.verification_result
        if self.generation_id: d["generation_id"] = self.generation_id
        if self.bounding_box: d["bounding_box"] = self.bounding_box
        if self.world_position: d["world_position"] = self.world_position
        if self.world_rotation: d["world_rotation"] = self.world_rotation
        # NEW: Serialize transform state
        d["transform_state"] = self.transform_state.to_dict()
        if self.public_sockets: d["public_sockets"] = self.public_sockets
        if self.modifiers: d["modifiers"] = self.modifiers
        if self.constraints: d["constraints"] = self.constraints
        if self.animation_data: d["animation_data"] = self.animation_data
        if self.physics_settings: d["physics_settings"] = self.physics_settings
        if self.custom_props: d["custom_props"] = self.custom_props
        
        return d
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> ManifestNode:
        """Deserialize from JSON."""
        node = cls(
            node_id=d["node_id"],
            label=d["label"],
            kind=NodeKind(d.get("kind", "part")),
            state=NodeState(d.get("state", "planned")),
            importance=NodeImportance(d.get("importance", "required")),
            phase=BuildPhase(d.get("phase", "structure")),
            parent_id=d.get("parent_id"),
            children_ids=list(d.get("children_ids", [])),
            dependency_ids=list(d.get("dependency_ids", [])),
            instance_of=d.get("instance_of"),
            instance_index=d.get("instance_index"),
            retry_count=d.get("retry_count", 0),
            max_retries=d.get("max_retries", 3),
            error_message=d.get("error_message"),
            error_stage=d.get("error_stage"),
            hierarchy_depth=d.get("hierarchy_depth", 0),
            stage_outputs=dict(d.get("stage_outputs", {})),
            verification_result=d.get("verification_result"),
            blender_objects=list(d.get("blender_objects", [])),
            generation_id=d.get("generation_id"),
            bounding_box=d.get("bounding_box"),
            world_position=d.get("world_position"),
            world_rotation=d.get("world_rotation"),
            transform_state=NodeTransformState.from_dict(d.get("transform_state", {})),
            public_sockets=list(d.get("public_sockets", [])),
            modifiers=list(d.get("modifiers", [])),
            constraints=list(d.get("constraints", [])),
            animation_data=d.get("animation_data"),
            physics_settings=d.get("physics_settings"),
            custom_props=dict(d.get("custom_props", {})),
        )
        
        # Deserialize nested specs
        if d.get("geometry"):
            node.geometry = GeometrySpec.from_dict(d["geometry"])
        if d.get("material"):
            node.material = MaterialSpec.from_dict(d["material"])
        if d.get("attachment"):
            node.attachment = AttachmentSpec.from_dict(d["attachment"])
        
        return node


# ---------------------------------------------------------------------------
# BuildManifest — the complete build state
# ---------------------------------------------------------------------------

class BuildManifest:
    """Persistent build state for one progressive assembly build.
    
    This is the v5 pipeline's single source of truth. Serialized to
    data/builds_v2/{model_id}/manifest.json at every checkpoint.
    
    All node mutations go through transition() which enforces the state
    machine and logs the change.
    """
    
    def __init__(
        self,
        model_id: str,
        description: str = "",
        root_node_id: Optional[str] = None,
    ):
        self.model_id: str = model_id
        self.description: str = description
        self.root_node_id: str = root_node_id or ""
        self.nodes: Dict[str, ManifestNode] = {}
        self.completion_status: CompletionStatus = CompletionStatus.IN_PROGRESS
        self.created_at: str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self.updated_at: str = self.created_at
        self.checkpoints: List[Dict[str, Any]] = []
        
        # Original prompt
        self.prompt: str = ""
        
        # Shared context from Stage 0
        self.stage0_output: Optional[Dict[str, Any]] = None
        
        # Definition registry for instance reuse
        self.definitions: Dict[str, str] = {}  # label -> definition_node_id
        
        # Material library (shared materials)
        self.materials: Dict[str, MaterialSpec] = {}
        
        # Build statistics
        self.stats: Dict[str, Any] = {
            "total_llm_calls": 0,
            "total_blender_ops": 0,
            "build_start_time": None,
            "build_end_time": None,
        }
    
    # ── Factory ──────────────────────────────────────────────────────────
    
    @classmethod
    def create(cls, prompt: str, model_id: Optional[str] = None) -> BuildManifest:
        """Create a new manifest with a root MODEL node."""
        mid = model_id or f"m_{uuid.uuid4().hex[:10]}"
        manifest = cls(model_id=mid, description=prompt[:100])
        manifest.prompt = prompt
        manifest.stats["build_start_time"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        
        # Create root MODEL node
        root_id = f"{mid}_root"
        # Create a clean label from prompt
        label_base = prompt[:40].lower()
        label_clean = "".join(c if c.isalnum() or c == "_" else "_" for c in label_base)
        label_clean = "_".join(filter(None, label_clean.split("_")))  # Remove empty parts
        root_label = label_clean or "model"
        
        root = ManifestNode(
            node_id=root_id,
            label=root_label,
            kind=NodeKind.MODEL,
            hierarchy_depth=0,
        )
        manifest.nodes[root_id] = root
        manifest.root_node_id = root_id
        
        return manifest
    
    # ── Node Access ──────────────────────────────────────────────────────
    
    def get_node(self, node_id: str) -> ManifestNode:
        """Get a node or raise KeyError."""
        if node_id not in self.nodes:
            raise KeyError(f"Node '{node_id}' not in manifest '{self.model_id}'")
        return self.nodes[node_id]
    
    def get_root(self) -> ManifestNode:
        """Return the root MODEL node."""
        return self.get_node(self.root_node_id)
    
    def get_node_by_label(self, label: str) -> Optional[ManifestNode]:
        """Find a node by its label (returns first match or None)."""
        for node in self.nodes.values():
            if node.label == label:
                return node
        return None
    
    def has_node(self, node_id: str) -> bool:
        """Check if a node exists."""
        return node_id in self.nodes
    
    def add_node(self, node: ManifestNode) -> None:
        """Add a node to the manifest. Raises if duplicate."""
        if node.node_id in self.nodes:
            raise ValueError(f"Duplicate node_id: {node.node_id}")
        self.nodes[node.node_id] = node
        self._touch()
    
    def remove_node(self, node_id: str) -> ManifestNode:
        """Remove a node. Does NOT cascade to children."""
        node = self.nodes.pop(node_id)
        if node.parent_id and node.parent_id in self.nodes:
            parent = self.nodes[node.parent_id]
            if node_id in parent.children_ids:
                parent.children_ids.remove(node_id)
        self._touch()
        return node
    
    # ── State Machine ────────────────────────────────────────────────────
    
    def transition(
        self,
        node_id: str,
        new_state: NodeState,
        error: Optional[str] = None,
        error_stage: Optional[str] = None,
    ) -> None:
        """Move a node to a new state. Validates the transition is legal."""
        node = self.get_node(node_id)
        old_state = node.state
        allowed = _VALID_TRANSITIONS.get(old_state, set())
        
        if new_state not in allowed:
            raise ValueError(
                f"Illegal state transition for '{node.label}' ({node_id}): "
                f"{old_state.value} → {new_state.value}. "
                f"Allowed: {sorted(s.value for s in allowed)}"
            )
        
        node.state = new_state
        if error is not None:
            node.error_message = error
        if error_stage is not None:
            node.error_stage = error_stage
        if new_state == NodeState.RETRYING:
            node.retry_count += 1
        
        self._touch()
        logger.debug(
            f"[{self.model_id}] {node.label}: {old_state.value} → {new_state.value}"
            + (f" (error: {error})" if error else "")
        )
    
    def can_retry(self, node_id: str) -> bool:
        """Check if a node can be retried."""
        node = self.get_node(node_id)
        return node.can_retry()
    
    # ── Queries ──────────────────────────────────────────────────────────
    
    def nodes_in_state(self, state: NodeState) -> List[ManifestNode]:
        """Return all nodes in the given state."""
        return [n for n in self.nodes.values() if n.state == state]
    
    def nodes_of_kind(self, kind: NodeKind) -> List[ManifestNode]:
        """Return all nodes of the given kind."""
        return [n for n in self.nodes.values() if n.kind == kind]
    
    def nodes_in_phase(self, phase: BuildPhase) -> List[ManifestNode]:
        """Return all nodes in the given build phase."""
        return [n for n in self.nodes.values() if n.phase == phase]
    
    def get_children(self, node_id: str) -> List[ManifestNode]:
        """Return immediate children of a node."""
        parent = self.get_node(node_id)
        return [self.nodes[cid] for cid in parent.children_ids if cid in self.nodes]
    
    def get_descendants(self, node_id: str) -> List[ManifestNode]:
        """Return all descendants of a node (recursive)."""
        result = []
        for child in self.get_children(node_id):
            result.append(child)
            result.extend(self.get_descendants(child.node_id))
        return result
    
    def get_ancestors(self, node_id: str) -> List[str]:
        """Return ancestor node IDs from parent up to root."""
        ancestors: List[str] = []
        current_id = node_id
        visited: Set[str] = set()
        
        while True:
            if current_id in visited:
                logger.warning(f"Cycle detected at {current_id}")
                break
            visited.add(current_id)
            
            node = self.nodes.get(current_id)
            if node is None or node.parent_id is None:
                break
            ancestors.append(node.parent_id)
            current_id = node.parent_id
        
        return ancestors
    
    def get_leaves(self) -> List[ManifestNode]:
        """Return all leaf nodes (no children)."""
        return [n for n in self.nodes.values() if n.is_leaf()]
    
    def get_parts(self) -> List[ManifestNode]:
        """Return all PART nodes."""
        return self.nodes_of_kind(NodeKind.PART)
    
    def get_assemblies(self) -> List[ManifestNode]:
        """Return all ASSEMBLY nodes."""
        return self.nodes_of_kind(NodeKind.ASSEMBLY)
    
    def get_undecomposed_assemblies(self) -> List[ManifestNode]:
        """Return ASSEMBLY/MODEL nodes that need decomposition."""
        return [
            n for n in self.nodes.values()
            if n.kind in (NodeKind.MODEL, NodeKind.ASSEMBLY)
            and n.is_leaf()
            and n.state in (NodeState.PLANNED, NodeState.READY)
        ]
    
    def get_buildable_parts(self) -> List[ManifestNode]:
        """Return PART nodes ready to be built."""
        return [
            n for n in self.nodes.values()
            if n.kind == NodeKind.PART
            and n.state == NodeState.READY
            and "stage4" in n.stage_outputs
        ]
    
    def get_mergeable_assemblies(self) -> List[ManifestNode]:
        """Return ASSEMBLY nodes whose children are all verified."""
        result = []
        for n in self.nodes.values():
            if n.kind in (NodeKind.MODEL, NodeKind.ASSEMBLY):
                if n.children_ids and self.all_children_verified(n.node_id):
                    if n.state in (NodeState.READY, NodeState.PLANNED):
                        result.append(n)
        return result
    
    def all_children_verified(self, node_id: str) -> bool:
        """Check if all children are VERIFIED."""
        node = self.get_node(node_id)
        if not node.children_ids:
            return False
        return all(
            self.nodes[cid].state == NodeState.VERIFIED
            for cid in node.children_ids
            if cid in self.nodes
        )
    
    def all_children_done(self, node_id: str) -> bool:
        """Check if all children are in terminal state (VERIFIED or SKIPPED)."""
        node = self.get_node(node_id)
        if not node.children_ids:
            return False
        return all(
            self.nodes[cid].state in (NodeState.VERIFIED, NodeState.SKIPPED)
            for cid in node.children_ids
            if cid in self.nodes
        )
    
    def is_root_resolved(self) -> bool:
        """True if root is VERIFIED - build complete."""
        return self.get_root().state == NodeState.VERIFIED
    
    def compute_completion_status(self) -> CompletionStatus:
        """Evaluate overall build status. Blueprint §17."""
        required = [
            n for n in self.nodes.values()
            if n.importance == NodeImportance.REQUIRED and n.kind != NodeKind.MODEL
        ]
        optional = [
            n for n in self.nodes.values()
            if n.importance in (NodeImportance.OPTIONAL, NodeImportance.DECORATIVE)
        ]
        
        if not required:
            root = self.get_root()
            if root.state == NodeState.VERIFIED:
                return CompletionStatus.SUCCESS
            if root.state in (NodeState.FAILED, NodeState.SKIPPED):
                return CompletionStatus.FAILED
            return CompletionStatus.IN_PROGRESS
        
        required_failed = any(n.state in (NodeState.FAILED, NodeState.SKIPPED) for n in required)
        required_done = all(n.state == NodeState.VERIFIED for n in required)
        optional_skipped = any(n.state == NodeState.SKIPPED for n in optional)
        
        if required_failed:
            return CompletionStatus.FAILED
        if required_done:
            return CompletionStatus.COMPLETED_DEGRADED if optional_skipped else CompletionStatus.SUCCESS
        return CompletionStatus.IN_PROGRESS

    
    # ── Hierarchy Helpers ────────────────────────────────────────────────
    
    def add_child_node(
        self,
        parent_id: str,
        label: str,
        kind: NodeKind,
        importance: NodeImportance = NodeImportance.REQUIRED,
        dependency_ids: Optional[List[str]] = None,
        attachment: Optional[AttachmentSpec] = None,
        geometry: Optional[GeometrySpec] = None,
        material: Optional[MaterialSpec] = None,
        stage_outputs: Optional[Dict[str, Any]] = None,
    ) -> ManifestNode:
        """Create and add a child node under parent_id.
        
        This is the primary way to build the hierarchy during decomposition.
        Returns the created node.
        """
        parent = self.get_node(parent_id)
        
        # Generate unique node_id
        child_id = f"{self.model_id}_{label}_{len(self.nodes)}"
        if child_id in self.nodes:
            child_id = f"{child_id}_{uuid.uuid4().hex[:4]}"
        
        child = ManifestNode(
            node_id=child_id,
            label=label,
            kind=kind,
            importance=importance,
            parent_id=parent_id,
            hierarchy_depth=parent.hierarchy_depth + 1,
            dependency_ids=list(dependency_ids or []),
            attachment=attachment or AttachmentSpec(),
            geometry=geometry,
            material=material,
            stage_outputs=dict(stage_outputs or {}),
        )
        
        self.nodes[child_id] = child
        parent.children_ids.append(child_id)
        self._touch()
        
        logger.debug(
            f"[{self.model_id}] Added {kind.value} '{label}' "
            f"under '{parent.label}' (depth={child.hierarchy_depth})"
        )
        return child
    
    def remove_subtree(self, node_id: str) -> List[str]:
        """Remove a node and all descendants. Returns removed IDs."""
        if node_id == self.root_node_id:
            raise ValueError("Cannot remove root node")
        
        removed: List[str] = []
        self._collect_subtree(node_id, removed)
        
        for nid in reversed(removed):
            self.remove_node(nid)
        
        return removed
    
    def _collect_subtree(self, node_id: str, result: List[str]) -> None:
        """Recursively collect all node IDs in a subtree."""
        if node_id not in self.nodes:
            return
        node = self.nodes[node_id]
        for cid in list(node.children_ids):
            self._collect_subtree(cid, result)
        result.append(node_id)
    
    def reparent_node(self, node_id: str, new_parent_id: str) -> None:
        """Move a node to a new parent."""
        node = self.get_node(node_id)
        new_parent = self.get_node(new_parent_id)
        
        # Remove from old parent
        if node.parent_id and node.parent_id in self.nodes:
            old_parent = self.nodes[node.parent_id]
            if node_id in old_parent.children_ids:
                old_parent.children_ids.remove(node_id)
        
        # Add to new parent
        node.parent_id = new_parent_id
        node.hierarchy_depth = new_parent.hierarchy_depth + 1
        new_parent.children_ids.append(node_id)
        
        # Update depths of descendants
        self._update_descendant_depths(node_id)
        self._touch()
    
    def _update_descendant_depths(self, node_id: str) -> None:
        """Recursively update hierarchy_depth for all descendants."""
        node = self.nodes[node_id]
        for cid in node.children_ids:
            if cid in self.nodes:
                child = self.nodes[cid]
                child.hierarchy_depth = node.hierarchy_depth + 1
                self._update_descendant_depths(cid)
    
    # ── Definition/Instance Support ──────────────────────────────────────
    
    def register_definition(self, label: str, node_id: str) -> None:
        """Register a node as a reusable definition."""
        self.definitions[label] = node_id
        node = self.get_node(node_id)
        node.kind = NodeKind.DEFINITION
        self._touch()
    
    def create_instance(
        self,
        definition_label: str,
        parent_id: str,
        instance_label: str,
        attachment: AttachmentSpec,
    ) -> ManifestNode:
        """Create an instance of a registered definition."""
        if definition_label not in self.definitions:
            raise ValueError(f"No definition registered for '{definition_label}'")
        
        def_node_id = self.definitions[definition_label]
        def_node = self.get_node(def_node_id)
        
        # Count existing instances
        instance_count = sum(
            1 for n in self.nodes.values()
            if n.instance_of == def_node_id
        )
        
        instance = self.add_child_node(
            parent_id=parent_id,
            label=instance_label,
            kind=NodeKind.INSTANCE,
            importance=def_node.importance,
            attachment=attachment,
        )
        instance.instance_of = def_node_id
        instance.instance_index = instance_count
        
        # Copy geometry spec reference (instances share definition's geometry)
        instance.geometry = def_node.geometry
        instance.material = def_node.material
        
        return instance
    
    # ── Material Library ─────────────────────────────────────────────────
    
    def add_material(self, name: str, spec: MaterialSpec) -> None:
        """Add a material to the shared library."""
        spec.name = name
        self.materials[name] = spec
        self._touch()
    
    def get_material(self, name: str) -> Optional[MaterialSpec]:
        """Get a material from the library."""
        return self.materials.get(name)
    
    # ── Persistence ──────────────────────────────────────────────────────
    
    def _touch(self) -> None:
        """Update the updated_at timestamp."""
        self.updated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    
    def _build_dir(self) -> Path:
        """Return (and lazily create) this build's directory."""
        d = _builds_dir() / self.model_id
        d.mkdir(parents=True, exist_ok=True)
        return d
    
    def to_dict(self) -> Dict[str, Any]:
        """Full serialization for JSON persistence."""
        return {
            "model_id": self.model_id,
            "description": self.description,
            "prompt": self.prompt,
            "root_node_id": self.root_node_id,
            "completion_status": self.completion_status.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "stage0_output": self.stage0_output,
            "nodes": {nid: node.to_dict() for nid, node in self.nodes.items()},
            "definitions": self.definitions,
            "materials": {k: v.to_dict() for k, v in self.materials.items()},
            "checkpoints": self.checkpoints,
            "stats": self.stats,
        }
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> BuildManifest:
        """Reconstruct from parsed JSON."""
        m = cls(
            model_id=d["model_id"],
            description=d.get("description", ""),
            root_node_id=d.get("root_node_id", ""),
        )
        m.prompt = d.get("prompt", "")
        m.completion_status = CompletionStatus(d.get("completion_status", "in_progress"))
        m.created_at = d.get("created_at", "")
        m.updated_at = d.get("updated_at", "")
        m.stage0_output = d.get("stage0_output")
        m.checkpoints = list(d.get("checkpoints", []))
        m.definitions = dict(d.get("definitions", {}))
        m.stats = dict(d.get("stats", {}))
        
        for nid, ndict in d.get("nodes", {}).items():
            m.nodes[nid] = ManifestNode.from_dict(ndict)
        
        for name, mdict in d.get("materials", {}).items():
            m.materials[name] = MaterialSpec.from_dict(mdict)
        
        return m
    
    def save(self, path: Optional[Path] = None) -> Path:
        """Persist manifest to JSON. Uses atomic write."""
        target = path or (self._build_dir() / "manifest.json")
        tmp = target.with_suffix(".tmp")
        data = json.dumps(self.to_dict(), indent=2, ensure_ascii=False)
        tmp.write_text(data, encoding="utf-8")
        tmp.replace(target)
        logger.debug(f"Manifest saved: {target}")
        return target
    
    @classmethod
    def load(cls, path: Path) -> BuildManifest:
        """Load manifest from JSON file."""
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls.from_dict(data)
    
    @classmethod
    def load_by_model_id(cls, model_id: str) -> Optional[BuildManifest]:
        """Load manifest by model_id, or None if not found."""
        p = _builds_dir() / model_id / "manifest.json"
        if not p.exists():
            return None
        try:
            return cls.load(p)
        except Exception as e:
            logger.warning(f"Failed to load manifest {model_id}: {e}")
            return None
    
    # ── Checkpointing ────────────────────────────────────────────────────
    
    def checkpoint(self, label: Optional[str] = None) -> None:
        """Save a checkpoint and persist to disk. Blueprint §19."""
        snap = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "label": label or f"checkpoint_{len(self.checkpoints)}",
            "verified_count": len(self.nodes_in_state(NodeState.VERIFIED)),
            "failed_count": len(self.nodes_in_state(NodeState.FAILED)),
            "total_nodes": len(self.nodes),
        }
        self.checkpoints.append(snap)
        self.save()
        logger.info(
            f"[{self.model_id}] Checkpoint '{snap['label']}': "
            f"{snap['verified_count']}/{snap['total_nodes']} verified"
        )
    
    def delete_build_state(self) -> None:
        """Delete temporary build state after completion. Blueprint §7."""
        import shutil
        build_dir = self._build_dir()
        if build_dir.exists():
            shutil.rmtree(build_dir, ignore_errors=True)
            logger.info(f"[{self.model_id}] Build state deleted")
    
    # ── Statistics ───────────────────────────────────────────────────────
    
    def record_llm_call(self) -> None:
        """Increment LLM call counter."""
        self.stats["total_llm_calls"] = self.stats.get("total_llm_calls", 0) + 1
    
    def record_blender_op(self) -> None:
        """Increment Blender operation counter."""
        self.stats["total_blender_ops"] = self.stats.get("total_blender_ops", 0) + 1
    
    def finalize(self) -> None:
        """Mark build as complete and record end time."""
        self.stats["build_end_time"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self.completion_status = self.compute_completion_status()
        self.save()
    
    # ── Debug ────────────────────────────────────────────────────────────
    
    # ── Transform Hierarchy (Phase 1) ────────────────────────────────────
    
    def compute_node_world_transform(self, node_id: str) -> WorldMatrix:
        """Compute world transform for a node by walking up the hierarchy.
        
        This is the NEW transform system. It composes transforms through
        the tree without any geometry lookup:
            world = parent.world @ node.local
        
        Args:
            node_id: The node to compute world transform for
            
        Returns:
            WorldMatrix for the node
        """
        from .transforms import compute_world_transform_chain
        
        def get_transform(nid: str) -> NodeTransformState:
            return self.nodes[nid].transform_state
        
        def get_parent(nid: str) -> Optional[str]:
            return self.nodes[nid].parent_id
        
        return compute_world_transform_chain(node_id, get_transform, get_parent)
    
    def propagate_transforms_from(self, node_id: str) -> None:
        """Propagate world transforms down from a node to all descendants.
        
        Call this after changing a node's local_transform to update
        all children's world_matrix values.
        
        Args:
            node_id: The node whose subtree to update
        """
        from .transforms import propagate_world_transforms
        
        def get_transform(nid: str) -> NodeTransformState:
            return self.nodes[nid].transform_state
        
        def get_children(nid: str) -> List[str]:
            return self.nodes[nid].children_ids
        
        def get_parent(nid: str) -> Optional[str]:
            return self.nodes[nid].parent_id

        propagate_world_transforms(node_id, get_transform, get_children, get_parent)
    
    def freeze_node_transform(self, node_id: str) -> None:
        """Lock a node's transform (called when node is verified).
        
        Once frozen, the transform cannot change. This ensures verified
        nodes maintain their spatial position.
        """
        node = self.get_node(node_id)
        if node.transform_state.world_matrix is None:
            # Compute world transform first
            self.compute_node_world_transform(node_id)
        node.transform_state.freeze()
    
    def compare_transform_systems(self, node_id: str) -> Dict[str, Any]:
        """Compare old and new transform systems for debugging.
        
        Returns a dict with both systems' world positions for comparison.
        Use this during migration to verify the new system matches the old.
        """
        node = self.get_node(node_id)
        
        # Old system
        old_pos = node.world_position
        old_rot = node.world_rotation
        
        # New system
        world = self.compute_node_world_transform(node_id)
        new_pos = world.position
        new_rot = world.rotation
        
        # Compute difference
        diff_pos = None
        if old_pos and new_pos:
            diff_pos = [abs(old_pos[i] - new_pos[i]) for i in range(3)]
        
        return {
            "node_id": node_id,
            "label": node.label,
            "old_position": old_pos,
            "new_position": new_pos,
            "position_diff": diff_pos,
            "old_rotation": old_rot,
            "new_rotation": new_rot,
            "match": diff_pos is None or all(d < 0.001 for d in diff_pos),
        }
    
    
    def print_hierarchy(self, node_id: Optional[str] = None, indent: int = 0) -> str:
        """Return string representation of hierarchy for debugging."""
        if node_id is None:
            node_id = self.root_node_id
        
        node = self.nodes.get(node_id)
        if not node:
            return ""
        
        prefix = "  " * indent
        icons = {
            NodeState.PLANNED: "[ ]", NodeState.DECOMPOSING: "[~]",
            NodeState.READY: "[.]", NodeState.BUILDING: "[B]",
            NodeState.VERIFYING: "[?]", NodeState.VERIFIED: "[*]",
            NodeState.MERGING: "[M]", NodeState.FAILED: "[X]",
            NodeState.RETRYING: "[R]", NodeState.SKIPPED: "[-]",
            NodeState.STALE: "[!]",
        }
        icon = icons.get(node.state, "[?]")
        kind_tag = node.kind.value[0].upper()
        
        line = f"{prefix}{icon} [{kind_tag}] {node.label}"
        if node.kind == NodeKind.INSTANCE:
            line += f" (→{node.instance_of})"
        line += "\n"
        
        for cid in node.children_ids:
            line += self.print_hierarchy(cid, indent + 1)
        
        return line
    
    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of the build state."""
        by_state = {}
        for state in NodeState:
            count = len(self.nodes_in_state(state))
            if count > 0:
                by_state[state.value] = count
        
        by_kind = {}
        for kind in NodeKind:
            count = len(self.nodes_of_kind(kind))
            if count > 0:
                by_kind[kind.value] = count
        
        return {
            "model_id": self.model_id,
            "total_nodes": len(self.nodes),
            "completion_status": self.completion_status.value,
            "by_state": by_state,
            "by_kind": by_kind,
            "checkpoints": len(self.checkpoints),
            "stats": self.stats,
        }
