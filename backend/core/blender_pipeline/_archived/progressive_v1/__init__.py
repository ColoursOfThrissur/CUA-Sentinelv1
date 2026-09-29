"""Progressive Assembly Pipeline v5 — hierarchical, state-driven 3D model building.

Subpackage of blender_pipeline.  Adds recursive decomposition, persistent manifests,
dependency-aware scheduling, and progressive merge-and-verify to the existing
Stage 0-6 infrastructure.
"""

from .manifest import BuildManifest, ManifestNode, NodeState, CompletionStatus
from .node_types import NodeKind, NodeImportance
from .hierarchy import ContainmentTree
from .dependency_graph import DependencyDAG
from .frontier import BuildFrontier
from .scheduler import SmartScheduler
from .decomposer import RecursiveDecomposer
from .merger import AssemblyMerger
from .checkpoint import CheckpointManager
from .dirty_propagation import DirtyPropagator
from .controller import ProgressiveAssemblyController, ProgressiveResult
from .node_executor import ProgressiveNodeExecutor
from .instances import InstanceManager
from .relationships import RelationshipGraph, CrossAssemblyRelationship, SocketAnchor

__all__ = [
    # Core data structures
    "BuildManifest",
    "ManifestNode",
    "NodeState",
    "CompletionStatus",
    "NodeKind",
    "NodeImportance",
    # Hierarchy & DAG
    "ContainmentTree",
    "DependencyDAG",
    # Scheduling
    "BuildFrontier",
    "SmartScheduler",
    # Decomposition & Merge
    "RecursiveDecomposer",
    "AssemblyMerger",
    # Persistence
    "CheckpointManager",
    "DirtyPropagator",
    # Controller & Execution
    "ProgressiveAssemblyController",
    "ProgressiveResult",
    "ProgressiveNodeExecutor",
    # Phase 5: Instances & Relationships
    "InstanceManager",
    "RelationshipGraph",
    "CrossAssemblyRelationship",
    "SocketAnchor",
]
