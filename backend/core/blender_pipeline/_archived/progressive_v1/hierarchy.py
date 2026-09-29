"""Containment Tree — variable-depth hierarchy for progressive assembly.

Manages the parent-child containment relationships between nodes.
Enforces safety limits (max depth, max children, max total nodes) while
allowing different branches to reach different depths.

Blueprint references: §2.1 (containment hierarchy), §3 (hierarchy levels),
§4.3 (hard safety limits).
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Set

from .node_types import NodeKind
from .manifest import BuildManifest, ManifestNode, NodeState

logger = logging.getLogger(__name__)


class HierarchyError(Exception):
    """Raised when a hierarchy operation violates structural constraints."""
    pass


class ContainmentTree:
    """Variable-depth containment hierarchy with safety limits.

    This class does NOT own the nodes — they live in BuildManifest.nodes.
    ContainmentTree provides structural operations and validation on top
    of the manifest's flat node dictionary.

    Blueprint §4.3 hard safety limits:
        MAX_HIERARCHY_DEPTH        — No branch deeper than 6 levels
        MAX_CHILDREN_PER_NODE      — No node has more than 12 children
        MAX_TOTAL_NODES            — Build cannot exceed 100 nodes total
        MAX_DECOMPOSITION_ATTEMPTS — A node cannot be re-decomposed more than 3 times
    """

    MAX_HIERARCHY_DEPTH: int = 6
    MAX_CHILDREN_PER_NODE: int = 12
    MAX_TOTAL_NODES: int = 100
    MAX_DECOMPOSITION_ATTEMPTS: int = 3

    def __init__(self, manifest: BuildManifest):
        self._manifest = manifest

    # ── Mutation ─────────────────────────────────────────────────────────

    def add_child(
        self,
        parent_id: str,
        child_id: str,
        label: str,
        kind: NodeKind = NodeKind.PART,
        **node_kwargs,
    ) -> ManifestNode:
        """Add a child node under parent_id.

        Creates the ManifestNode, links it to the parent, and adds it to
        the manifest.  Enforces safety limits before mutating anything.

        Returns the newly created ManifestNode.

        Raises:
            HierarchyError: If a safety limit would be violated.
            KeyError: If parent_id is not in the manifest.
        """
        parent = self._manifest.get_node(parent_id)

        # ── Safety checks ────────────────────────────────────────────
        if len(parent.children_ids) >= self.MAX_CHILDREN_PER_NODE:
            raise HierarchyError(
                f"Cannot add child to '{parent.label}' ({parent_id}): "
                f"already has {len(parent.children_ids)} children "
                f"(limit: {self.MAX_CHILDREN_PER_NODE})"
            )

        child_depth = parent.hierarchy_depth + 1
        if child_depth > self.MAX_HIERARCHY_DEPTH:
            raise HierarchyError(
                f"Cannot add child at depth {child_depth}: "
                f"exceeds MAX_HIERARCHY_DEPTH={self.MAX_HIERARCHY_DEPTH}"
            )

        if len(self._manifest.nodes) >= self.MAX_TOTAL_NODES:
            raise HierarchyError(
                f"Cannot add node: total nodes ({len(self._manifest.nodes)}) "
                f"would exceed MAX_TOTAL_NODES={self.MAX_TOTAL_NODES}"
            )

        if child_id in self._manifest.nodes:
            raise HierarchyError(f"Node '{child_id}' already exists in manifest")

        # ── Create and link ──────────────────────────────────────────
        child = ManifestNode(
            node_id=child_id,
            label=label,
            kind=kind,
            parent_id=parent_id,
            hierarchy_depth=child_depth,
            **node_kwargs,
        )
        self._manifest.add_node(child)
        parent.children_ids.append(child_id)

        logger.debug(
            f"[{self._manifest.model_id}] Added {kind.value} '{label}' "
            f"under '{parent.label}' (depth={child_depth})"
        )
        return child

    def remove_subtree(self, node_id: str) -> List[str]:
        """Remove a node and all its descendants from the manifest.

        Returns a list of all removed node IDs (for cleanup purposes,
        e.g. deleting Blender objects owned by removed nodes).

        Does NOT remove the root node.

        Raises:
            HierarchyError: If trying to remove the root node.
        """
        if node_id == self._manifest.root_node_id:
            raise HierarchyError("Cannot remove the root node")

        removed: List[str] = []
        self._collect_subtree_ids(node_id, removed)

        # Remove in reverse depth order (leaves first)
        for nid in reversed(removed):
            self._manifest.remove_node(nid)

        return removed

    def _collect_subtree_ids(self, node_id: str, result: List[str]) -> None:
        """Recursively collect all node IDs in a subtree (node + descendants)."""
        if node_id not in self._manifest.nodes:
            return
        node = self._manifest.nodes[node_id]
        # Children first (depth-first)
        for cid in list(node.children_ids):
            self._collect_subtree_ids(cid, result)
        result.append(node_id)

    # ── Queries ──────────────────────────────────────────────────────────

    def get_ancestors(self, node_id: str) -> List[str]:
        """Return ancestor node IDs from immediate parent up to (but not including) root.

        Returns empty list if node_id is the root.
        """
        ancestors: List[str] = []
        current_id = node_id
        visited: Set[str] = set()

        while True:
            if current_id in visited:
                # Cycle protection (should never happen with valid data)
                logger.warning(f"Cycle detected in hierarchy at node {current_id}")
                break
            visited.add(current_id)

            node = self._manifest.nodes.get(current_id)
            if node is None or node.parent_id is None:
                break
            ancestors.append(node.parent_id)
            current_id = node.parent_id

        return ancestors

    def get_siblings(self, node_id: str) -> List[ManifestNode]:
        """Return sibling nodes (same parent, excluding self)."""
        node = self._manifest.get_node(node_id)
        if node.parent_id is None:
            return []
        parent = self._manifest.get_node(node.parent_id)
        return [
            self._manifest.nodes[cid]
            for cid in parent.children_ids
            if cid != node_id and cid in self._manifest.nodes
        ]

    def get_leaves(self) -> List[ManifestNode]:
        """Return all leaf nodes (nodes with no children)."""
        return self._manifest.get_leaves()

    def get_depth(self, node_id: str) -> int:
        """Return the depth of a node in the containment tree."""
        return self._manifest.get_node(node_id).hierarchy_depth

    def max_depth(self) -> int:
        """Return the maximum depth across all nodes."""
        if not self._manifest.nodes:
            return 0
        return max(n.hierarchy_depth for n in self._manifest.nodes.values())

    # ── Validation ───────────────────────────────────────────────────────

    def validate(self) -> List[str]:
        """Validate the entire hierarchy structure.

        Returns a list of error strings (empty = valid).

        Checks:
        1. Every node's parent_id points to a valid node
        2. Every parent's children_ids includes this node
        3. No cycles
        4. Depth values are consistent
        5. Safety limits are not exceeded
        6. Root exists and has no parent
        """
        errors: List[str] = []

        # Root checks
        if self._manifest.root_node_id not in self._manifest.nodes:
            errors.append(f"Root node '{self._manifest.root_node_id}' missing from nodes")
            return errors  # Can't continue without root

        root = self._manifest.get_root()
        if root.parent_id is not None:
            errors.append(f"Root node has parent_id={root.parent_id} (should be None)")

        # Per-node checks
        visited: Set[str] = set()
        for nid, node in self._manifest.nodes.items():
            # Parent linkage
            if node.parent_id is not None:
                if node.parent_id not in self._manifest.nodes:
                    errors.append(
                        f"Node '{node.label}' ({nid}) has parent_id='{node.parent_id}' "
                        f"which does not exist"
                    )
                else:
                    parent = self._manifest.nodes[node.parent_id]
                    if nid not in parent.children_ids:
                        errors.append(
                            f"Node '{node.label}' ({nid}) claims parent "
                            f"'{parent.label}' ({node.parent_id}) but is not in "
                            f"parent's children_ids"
                        )

            # Children linkage
            for cid in node.children_ids:
                if cid not in self._manifest.nodes:
                    errors.append(
                        f"Node '{node.label}' ({nid}) lists child '{cid}' "
                        f"which does not exist"
                    )

            # Depth consistency
            if node.parent_id is not None and node.parent_id in self._manifest.nodes:
                expected_depth = self._manifest.nodes[node.parent_id].hierarchy_depth + 1
                if node.hierarchy_depth != expected_depth:
                    errors.append(
                        f"Node '{node.label}' ({nid}) has depth={node.hierarchy_depth} "
                        f"but expected {expected_depth} (parent depth + 1)"
                    )

            # Depth limit
            if node.hierarchy_depth > self.MAX_HIERARCHY_DEPTH:
                errors.append(
                    f"Node '{node.label}' ({nid}) at depth {node.hierarchy_depth} "
                    f"exceeds MAX_HIERARCHY_DEPTH={self.MAX_HIERARCHY_DEPTH}"
                )

            # Children count limit
            if len(node.children_ids) > self.MAX_CHILDREN_PER_NODE:
                errors.append(
                    f"Node '{node.label}' ({nid}) has {len(node.children_ids)} children "
                    f"(limit: {self.MAX_CHILDREN_PER_NODE})"
                )

        # Total node count
        if len(self._manifest.nodes) > self.MAX_TOTAL_NODES:
            errors.append(
                f"Total nodes ({len(self._manifest.nodes)}) exceeds "
                f"MAX_TOTAL_NODES={self.MAX_TOTAL_NODES}"
            )

        # Cycle detection (walk from root, check reachability)
        reachable: Set[str] = set()
        self._walk_reachable(self._manifest.root_node_id, reachable)
        unreachable = set(self._manifest.nodes.keys()) - reachable
        if unreachable:
            errors.append(
                f"Nodes not reachable from root: {sorted(unreachable)}"
            )

        return errors

    def _walk_reachable(self, node_id: str, visited: Set[str]) -> None:
        """BFS/DFS walk marking reachable nodes."""
        if node_id in visited or node_id not in self._manifest.nodes:
            return
        visited.add(node_id)
        node = self._manifest.nodes[node_id]
        for cid in node.children_ids:
            self._walk_reachable(cid, visited)
