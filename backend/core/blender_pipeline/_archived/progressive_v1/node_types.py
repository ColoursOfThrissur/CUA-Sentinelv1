"""Node type classification for the progressive assembly hierarchy.

Every node in the containment tree is one of these kinds.  The LLM proposes
semantic structure; code validates the kind assignment.
"""

from enum import Enum


class NodeKind(str, Enum):
    """What structural role a node plays in the model hierarchy.

    MODEL      — The single root node representing the complete model.
    ASSEMBLY   — An interior node whose children are built and merged.
    PART       — A leaf node: a single buildable primitive or small mesh.
    INSTANCE   — A placement of a shared definition (built once, placed N times).
    DEFINITION — A template node built once, referenced by INSTANCE nodes.
    RELATIONSHIP — A cross-assembly connection (e.g. rope, rigging, cable).
    """
    MODEL = "model"
    ASSEMBLY = "assembly"
    PART = "part"
    INSTANCE = "instance"
    DEFINITION = "definition"
    RELATIONSHIP = "relationship"


class NodeImportance(str, Enum):
    """Semantic classification of how critical a node is to the parent assembly.

    REQUIRED   — Parent cannot succeed if this node fails.
    OPTIONAL   — Parent reports COMPLETED_DEGRADED if this node is skipped.
    DECORATIVE — Purely cosmetic; skip silently if problematic.
    """
    REQUIRED = "required"
    OPTIONAL = "optional"
    DECORATIVE = "decorative"
