"""Progressive Assembly Pipeline v2 — Clean implementation following blueprint exactly.

This module implements the v5 progressive hierarchical assembly pipeline:
- Recursive decomposition of complex objects into variable-depth hierarchies
- Per-node stage execution (not batched)
- Bottom-up verified assembly with merge operations
- Instance reuse for repeated parts
- Support for materials, rigging, animation, physics

Blueprint references: docs/BLENDER_Pipeline_newBP.md

Imports are added as modules are implemented.
"""

# Node types
from .node_types import (
    NodeKind,
    NodeImportance,
    BuildPhase,
    PrimitiveType,
    SocketType,
    # Classification sets
    GEOMETRY_KINDS,
    RIGGING_KINDS,
    MATERIAL_KINDS,
    PROCEDURAL_KINDS,
    PHYSICS_KINDS,
    SCENE_KINDS,
    DECOMPOSABLE_KINDS,
    LEAF_KINDS,
    BLENDER_OBJECT_KINDS,
    INSTANCEABLE_KINDS,
    MESH_PRIMITIVES,
    CURVE_PRIMITIVES,
    BOOLEAN_SOCKETS,
    CONNECTOR_SOCKETS,
    SOCKET_REQUIRED_SEMANTICS,
    # Helper functions
    get_phase_for_kind,
    is_decomposable,
    is_leaf,
    creates_blender_object,
    is_geometry,
    is_instanceable,
)

# Manifest
from .manifest import (
    BuildManifest,
    ManifestNode,
    NodeState,
    CompletionStatus,
    GeometrySpec,
    MaterialSpec,
    AttachmentSpec,
)

# Hierarchy
from .hierarchy import (
    HierarchyLimits,
    HierarchyError,
    DepthLimitError,
    ChildLimitError,
    TotalNodesLimitError,
    CycleDetectedError,
    OrphanNodeError,
    TraversalOrder,
    ContainmentTree,
    DEFAULT_LIMITS,
)

# Dependency DAG
from .dag import (
    DependencyType,
    Dependency,
    DependencyError,
    CyclicDependencyError,
    MissingNodeError,
    DependencyDAG,
)

# Decomposer
from .decomposer import (
    DecompositionDecision,
    DecomposedChild,
    DecompositionResult,
    DecompositionError,
    StopConditionEvaluator,
    RecursiveDecomposer,
    decompose_manifest,
)

# Stages
from .stages import (
    Stage2Dimensions,
    Stage2Error,
    Stage3Semantics,
    Stage3Error,
    Stage4Resolver,
    Stage4Error,
    ResolvedTransform,
)

# Controller
from .controller import (
    ProgressiveController,
    ProgressiveResult,
    run_progressive_build,
)

# Executor
from .executor import (
    BlenderExecutor,
    ExecutionResult,
    VerificationResult,
    build_and_verify_node,
)

# Instances
from .instances import (
    InstanceManager,
    InstancePlacement,
    InstanceResult,
    find_instance_groups,
)

# Modifiers
from .modifiers import (
    ModifierType,
    ModifierSpec,
    get_modifier_preset,
    get_modifiers_for_style,
)

# Materials
from .materials import (
    MaterialPreset,
    MATERIAL_PRESETS,
    get_material_preset,
    get_material_for_description,
    list_preset_names,
)

# Booleans
from .booleans import (
    BooleanManager,
    BooleanOperation,
    BooleanSpec,
    BooleanResult,
    get_boolean_specs_from_node,
)

# Spatial Verification
from .verification import (
    SpatialVerifier,
    VerificationLevel,
    SpatialIssueType,
    SpatialIssue,
    SpatialVerificationResult,
    verify_node_placement,
)

__all__ = [
    # Enums
    "NodeKind",
    "NodeImportance", 
    "BuildPhase",
    "PrimitiveType",
    "SocketType",
    "NodeState",
    "CompletionStatus",
    # Specs
    "GeometrySpec",
    "MaterialSpec",
    "AttachmentSpec",
    # Manifest
    "BuildManifest",
    "ManifestNode",
    # Sets
    "GEOMETRY_KINDS",
    "RIGGING_KINDS",
    "MATERIAL_KINDS",
    "PROCEDURAL_KINDS",
    "PHYSICS_KINDS",
    "SCENE_KINDS",
    "DECOMPOSABLE_KINDS",
    "LEAF_KINDS",
    "BLENDER_OBJECT_KINDS",
    "INSTANCEABLE_KINDS",
    "MESH_PRIMITIVES",
    "CURVE_PRIMITIVES",
    "BOOLEAN_SOCKETS",
    "CONNECTOR_SOCKETS",
    "SOCKET_REQUIRED_SEMANTICS",
    # Functions
    "get_phase_for_kind",
    "is_decomposable",
    "is_leaf",
    "creates_blender_object",
    "is_geometry",
    "is_instanceable",
    # Hierarchy
    "HierarchyLimits",
    "HierarchyError",
    "DepthLimitError",
    "ChildLimitError",
    "TotalNodesLimitError",
    "CycleDetectedError",
    "OrphanNodeError",
    "TraversalOrder",
    "ContainmentTree",
    "DEFAULT_LIMITS",
    # DAG
    "DependencyType",
    "Dependency",
    "DependencyError",
    "CyclicDependencyError",
    "MissingNodeError",
    "DependencyDAG",
    # Decomposer
    "DecompositionDecision",
    "DecomposedChild",
    "DecompositionResult",
    "DecompositionError",
    "StopConditionEvaluator",
    "RecursiveDecomposer",
    "decompose_manifest",
    # Stages
    "Stage2Dimensions",
    "Stage2Error",
    "Stage3Semantics",
    "Stage3Error",
    "Stage4Resolver",
    "Stage4Error",
    "ResolvedTransform",
    # Controller
    "ProgressiveController",
    "ProgressiveResult",
    "run_progressive_build",
    # Executor
    "BlenderExecutor",
    "ExecutionResult",
    "VerificationResult",
    "build_and_verify_node",
    # Instances
    "InstanceManager",
    "InstancePlacement",
    "InstanceResult",
    "find_instance_groups",
    # Modifiers
    "ModifierType",
    "ModifierSpec",
    "get_modifier_preset",
    "get_modifiers_for_style",
    # Materials
    "MaterialPreset",
    "MATERIAL_PRESETS",
    "get_material_preset",
    "get_material_for_description",
    "list_preset_names",
    # Booleans
    "BooleanManager",
    "BooleanOperation",
    "BooleanSpec",
    "BooleanResult",
    "get_boolean_specs_from_node",
    # Spatial Verification
    "SpatialVerifier",
    "VerificationLevel",
    "SpatialIssueType",
    "SpatialIssue",
    "SpatialVerificationResult",
    "verify_node_placement",
]
