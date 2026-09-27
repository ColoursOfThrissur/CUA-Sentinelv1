"""Hierarchical Assembly Graph Specification for recursive 3D model decomposition.

Enables multi-part models (e.g. vehicles, articulated figures, architectural complexes)
to be decomposed into a tree of manageable nodes, each authored independently in a local
coordinate frame, verified, and joined through declared spatial sockets.
"""

from __future__ import annotations
from enum import Enum
from typing import Optional, List, Dict, Any, Tuple
from pydantic import BaseModel, Field


class PartParadigm(str, Enum):
    QUADRUPED = "quadruped_spec"
    VESSEL = "vessel_spec"
    HARD_SURFACE = "hard_surface_spec"
    PRIMITIVE = "typed_primitive"
    EXTERNAL_GENERATIVE = "external_generative"  # Hyper3D / Hunyuan3D fallback leaf


class JoinMode(str, Enum):
    FUSE = "fuse"                # boolean union, becomes one continuous mesh
    PARENT_ONLY = "parent_only"  # stays separate object, parented (rig/pose ready)
    PARENT_ATTACH = "parent_only" # canonical alias
    BOOLEAN_UNION = "fuse"       # canonical alias
    BOOLEAN_DIFFERENCE = "boolean_difference"


class AttachmentSpec(BaseModel):
    parent_node_id: Optional[str] = None      # null only for root node
    socket_name: str = "root"                 # e.g. "chassis.wheel_front_left"
    local_offset: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    local_rotation_euler: Tuple[float, float, float] = (0.0, 0.0, 0.0)  # in radians
    mating_tolerance_mm: float = 2.0          # max acceptable gap/overlap at joint in mm
    join_mode: JoinMode = JoinMode.PARENT_ONLY


class AssemblyNode(BaseModel):
    node_id: str                              # stable UUID or key, used as checkpoint key
    label: str                                # human-readable label, e.g. "front_left_wheel"
    paradigm: PartParadigm = PartParadigm.HARD_SURFACE
    sub_spec: Dict[str, Any] = Field(default_factory=dict)  # payload for paradigm compiler
    attachment: AttachmentSpec = Field(default_factory=AttachmentSpec)
    confidence_threshold: float = 0.4         # below this, this node re-splits or retries
    max_split_depth_remaining: int = 3        # decremented on each further decomposition
    retry_count: int = 0
    status: str = "PENDING"                   # PENDING | BUILDING | VERIFIED | FAILED | SPLIT
    children: List[AssemblyNode] = Field(default_factory=list)

    def find_node(self, target_id: str) -> Optional[AssemblyNode]:
        if self.node_id == target_id:
            return self
        for child in self.children:
            found = child.find_node(target_id)
            if found:
                return found
        return None

    def all_nodes(self) -> List[AssemblyNode]:
        nodes = [self]
        for child in self.children:
            nodes.extend(child.all_nodes())
        return nodes


AssemblyNode.model_rebuild()


class AssemblyGraph(BaseModel):
    schema_version: str = "2.0"               # Schema version for contract stability
    task_id: str
    root: AssemblyNode
    description: str = ""                     # original user prompt, for context
    max_retries_per_node: int = 3
    created_at: str = ""
    status: str = "PENDING"                   # PENDING | RESOLVING | ASSEMBLED | FAILED

    def get_node(self, node_id: str) -> Optional[AssemblyNode]:
        return self.root.find_node(node_id)
