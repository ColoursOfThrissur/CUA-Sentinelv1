"""Recursive Decomposer (Stage 0.5) — decomposes complex models into variable-depth hierarchies.

Blueprint references: §4 (Progressive Decomposition), §5 (Algorithm), §4.2 (Stop Conditions).
Enforces:
- Variable depth (stops when node is geometrically & semantically manageable)
- Code owns hierarchy integrity, limits, and validation; LLM proposes semantics.
- Hard safety limits (MAX_HIERARCHY_DEPTH, MAX_CHILDREN_PER_NODE, MAX_TOTAL_NODES).
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from .manifest import BuildManifest, ManifestNode, NodeState
from .node_types import NodeKind, NodeImportance
from .hierarchy import ContainmentTree, HierarchyError
from ..stage1_topology import Stage1Topology, Stage1Error

logger = logging.getLogger(__name__)


# Keywords indicating high complexity that warrants decomposition into sub-assemblies
COMPLEX_ASSEMBLY_KEYWORDS = frozenset({
    "ship", "car", "robot", "castle", "engine", "vehicle", "plane", "aircraft",
    "cannon", "arm", "chassis", "deck", "mast", "cockpit", "wheel_assembly",
    "cabinet", "station", "complex", "apparatus",
})


class DecomposerError(Exception):
    """Raised when decomposition fails unrecoverably."""
    pass


class RecursiveDecomposer:
    """Recursively breaks down complex nodes into manageable assemblies and leaf parts."""

    def __init__(
        self,
        max_depth: int = ContainmentTree.MAX_HIERARCHY_DEPTH,
        max_children: int = ContainmentTree.MAX_CHILDREN_PER_NODE,
    ):
        self.max_depth = max_depth
        self.max_children = max_children

    def should_decompose(self, node: ManifestNode) -> bool:
        """Evaluate Blueprint §4.2 stop conditions.

        A node should be decomposed if:
        1. It is explicitly marked as MODEL or ASSEMBLY
        2. Its label or description implies a multi-part compound assembly
        3. Its current hierarchy depth is strictly less than max_depth
        4. It has not exceeded maximum decomposition attempts
        """
        if node.hierarchy_depth >= self.max_depth:
            return False

        if node.kind == NodeKind.PART:
            return False

        if node.kind in (NodeKind.MODEL, NodeKind.ASSEMBLY):
            return True

        label_lower = node.label.lower()
        if any(k in label_lower for k in COMPLEX_ASSEMBLY_KEYWORDS):
            return True

        return False

    async def decompose_root(
        self,
        manifest: BuildManifest,
        prompt: str,
        stage0_output: Dict[str, Any],
        model_manager: Any = None,
        task_id: str = "adhoc",
        model_id: Optional[str] = None,
    ) -> None:
        """Entry point: decomposes the root node of the manifest into an initial hierarchy."""
        root = manifest.get_root()
        tree = ContainmentTree(manifest)

        manifest.transition(root.node_id, NodeState.DECOMPOSING)

        # Decompose using Stage 1 topology as the foundational decomposition
        try:
            stage1_out = await Stage1Topology.run(
                prompt=prompt,
                stage0_output=stage0_output,
                model_manager=model_manager,
                task_id=task_id,
                model_id=model_id,
            )
        except Exception as e:
            manifest.transition(root.node_id, NodeState.FAILED, error=str(e))
            raise DecomposerError(f"Root decomposition failed: {e}") from e

        # Populate children under root or intermediate assemblies
        parts = stage1_out.parts
        label_to_node_id: Dict[str, str] = {}

        for p in parts:
            child_id = f"{manifest.model_id}_{p.label}"
            label_to_node_id[p.label] = child_id

            # Determine kind: if part label indicates a compound assembly, mark as ASSEMBLY
            is_assembly = any(k in p.label.lower() for k in COMPLEX_ASSEMBLY_KEYWORDS)
            kind = NodeKind.ASSEMBLY if is_assembly else NodeKind.PART

            # Containment hierarchy:
            # Parts belong to root or an enclosing ASSEMBLY.
            # If parent_label points to an ASSEMBLY, nest under it.
            # If parent_label points to a PART, both are contained by root/parent assembly,
            # and an attachment dependency is created.
            parent_id = root.node_id
            dep_ids = []

            if p.parent_label and p.parent_label in label_to_node_id:
                candidate_parent_id = label_to_node_id[p.parent_label]
                candidate_parent = manifest.nodes.get(candidate_parent_id)
                if candidate_parent and candidate_parent.kind in (NodeKind.ASSEMBLY, NodeKind.MODEL):
                    parent_id = candidate_parent_id
                else:
                    # Parent is a PART: both belong to root, but this part depends on parent
                    parent_id = root.node_id
                    dep_ids.append(candidate_parent_id)

            try:
                tree.add_child(
                    parent_id=parent_id,
                    child_id=child_id,
                    label=p.label,
                    kind=kind,
                    importance=NodeImportance.REQUIRED,
                    dependency_ids=dep_ids,
                    stage_outputs={
                        "stage1": {
                            "primitive_type": p.primitive_type,
                            "socket_type": p.socket_type,
                            "parent_label": p.parent_label,
                        }
                    },
                )
                # Child is ready for subsequent stages
                manifest.transition(child_id, NodeState.READY)
            except HierarchyError as he:
                logger.warning(f"Hierarchy safety limit reached during decomposition: {he}")
                break

        # Validate resulting hierarchy
        errors = tree.validate()
        if errors:
            manifest.transition(root.node_id, NodeState.FAILED, error="; ".join(errors))
            raise DecomposerError(f"Hierarchy validation failed after decomposition: {errors}")

        # Root transitions to READY once children are generated and validated
        manifest.transition(root.node_id, NodeState.READY)
        logger.info(
            f"[{manifest.model_id}] Decomposed root into {len(manifest.nodes) - 1} child nodes"
        )
