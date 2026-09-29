"""Containment Hierarchy — tree structure with safety limits and validation.

This module provides:
- ContainmentTree: Wrapper around BuildManifest for hierarchy operations
- Safety limits: MAX_DEPTH, MAX_CHILDREN, MAX_TOTAL_NODES
- Validation: Cycle detection, orphan detection, depth consistency
- Traversal: BFS, DFS, level-order, bottom-up for build ordering

The hierarchy is the CONTAINMENT relationship (parent-child tree).
This is separate from the DEPENDENCY graph (build ordering).

Blueprint references: §2.1 (containment), §3 (hierarchy), §4.3 (limits).
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import (
    Any,
    Callable,
    Dict,
    Generator,
    Iterator,
    List,
    Optional,
    Set,
    Tuple,
    TYPE_CHECKING,
)

if TYPE_CHECKING:
    from .manifest import BuildManifest, ManifestNode

from .node_types import NodeKind, is_decomposable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Safety Limits — Blueprint §4.3
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class HierarchyLimits:
    """Configurable safety limits for hierarchy construction.
    
    These prevent runaway decomposition and ensure builds complete
    in reasonable time/memory.
    """
    max_depth: int = 8              # Maximum hierarchy depth (root = 0)
    max_children: int = 25          # Maximum children per node
    max_total_nodes: int = 300      # Maximum nodes in entire manifest
    max_decomposition_attempts: int = 3  # Retries per node decomposition
    
    # Complexity thresholds for decomposition decisions
    min_parts_for_assembly: int = 2     # Don't create assembly for < 2 parts
    max_parts_per_assembly: int = 15    # Split if > 15 parts
    
    def validate(self) -> List[str]:
        """Return list of validation errors (empty if valid)."""
        errors = []
        if self.max_depth < 1:
            errors.append("max_depth must be >= 1")
        if self.max_children < 1:
            errors.append("max_children must be >= 1")
        if self.max_total_nodes < 2:
            errors.append("max_total_nodes must be >= 2")
        if self.min_parts_for_assembly < 1:
            errors.append("min_parts_for_assembly must be >= 1")
        return errors


# Default limits - can be overridden per-build
DEFAULT_LIMITS = HierarchyLimits()


# ---------------------------------------------------------------------------
# Validation Errors
# ---------------------------------------------------------------------------

class HierarchyError(Exception):
    """Base exception for hierarchy violations."""
    pass


class DepthLimitError(HierarchyError):
    """Raised when hierarchy depth would exceed limit."""
    def __init__(self, node_label: str, current_depth: int, max_depth: int):
        self.node_label = node_label
        self.current_depth = current_depth
        self.max_depth = max_depth
        super().__init__(
            f"Cannot add children to '{node_label}' at depth {current_depth}: "
            f"would exceed max_depth={max_depth}"
        )


class ChildLimitError(HierarchyError):
    """Raised when a node would have too many children."""
    def __init__(self, node_label: str, current_count: int, max_children: int):
        self.node_label = node_label
        self.current_count = current_count
        self.max_children = max_children
        super().__init__(
            f"Cannot add more children to '{node_label}': "
            f"already has {current_count}, max={max_children}"
        )


class TotalNodesLimitError(HierarchyError):
    """Raised when total node count would exceed limit."""
    def __init__(self, current_count: int, max_total: int, adding: int = 1):
        self.current_count = current_count
        self.max_total = max_total
        self.adding = adding
        super().__init__(
            f"Cannot add {adding} node(s): "
            f"already have {current_count}, max={max_total}"
        )


class CycleDetectedError(HierarchyError):
    """Raised when a cycle is detected in the hierarchy."""
    def __init__(self, cycle_path: List[str]):
        self.cycle_path = cycle_path
        super().__init__(f"Cycle detected in hierarchy: {' -> '.join(cycle_path)}")


class OrphanNodeError(HierarchyError):
    """Raised when a node has no path to root."""
    def __init__(self, node_id: str, node_label: str):
        self.node_id = node_id
        self.node_label = node_label
        super().__init__(f"Orphan node detected: '{node_label}' ({node_id})")


# ---------------------------------------------------------------------------
# Traversal Order
# ---------------------------------------------------------------------------

class TraversalOrder(str, Enum):
    """Order for tree traversal."""
    DEPTH_FIRST_PRE = "dfs_pre"     # Parent before children
    DEPTH_FIRST_POST = "dfs_post"   # Children before parent (bottom-up)
    BREADTH_FIRST = "bfs"           # Level by level
    LEAVES_FIRST = "leaves_first"   # All leaves, then their parents, etc.


# ---------------------------------------------------------------------------
# ContainmentTree — hierarchy operations wrapper
# ---------------------------------------------------------------------------

class ContainmentTree:
    """Wrapper around BuildManifest for hierarchy operations.
    
    Provides:
    - Safety limit enforcement
    - Validation (cycles, orphans, depth consistency)
    - Traversal utilities (BFS, DFS, bottom-up)
    - Decomposition helpers
    
    Does NOT duplicate manifest storage - operates on the manifest directly.
    """
    
    def __init__(
        self,
        manifest: BuildManifest,
        limits: Optional[HierarchyLimits] = None,
    ):
        self.manifest = manifest
        self.limits = limits or DEFAULT_LIMITS
        
        # Validate limits
        limit_errors = self.limits.validate()
        if limit_errors:
            raise ValueError(f"Invalid limits: {limit_errors}")
    
    # ── Properties ───────────────────────────────────────────────────────
    
    @property
    def root_id(self) -> str:
        """Return root node ID."""
        return self.manifest.root_node_id
    
    @property
    def root(self) -> ManifestNode:
        """Return root node."""
        return self.manifest.get_root()
    
    @property
    def node_count(self) -> int:
        """Return total number of nodes."""
        return len(self.manifest.nodes)
    
    @property
    def max_depth(self) -> int:
        """Return maximum depth in current hierarchy."""
        if not self.manifest.nodes:
            return 0
        return max(n.hierarchy_depth for n in self.manifest.nodes.values())
    
    # ── Limit Checks ─────────────────────────────────────────────────────
    
    def can_add_child(self, parent_id: str) -> Tuple[bool, Optional[str]]:
        """Check if a child can be added to parent. Returns (ok, reason)."""
        parent = self.manifest.get_node(parent_id)
        
        # Check total nodes
        if self.node_count >= self.limits.max_total_nodes:
            return False, f"Total nodes limit reached ({self.limits.max_total_nodes})"
        
        # Check depth
        if parent.hierarchy_depth >= self.limits.max_depth:
            return False, f"Depth limit reached ({self.limits.max_depth})"
        
        # Check children count
        if len(parent.children_ids) >= self.limits.max_children:
            return False, f"Children limit reached ({self.limits.max_children})"
        
        return True, None
    
    def can_add_children(self, parent_id: str, count: int) -> Tuple[bool, Optional[str]]:
        """Check if multiple children can be added. Returns (ok, reason)."""
        parent = self.manifest.get_node(parent_id)
        
        # Check total nodes
        if self.node_count + count > self.limits.max_total_nodes:
            return False, (
                f"Would exceed total nodes limit: "
                f"{self.node_count} + {count} > {self.limits.max_total_nodes}"
            )
        
        # Check depth
        if parent.hierarchy_depth >= self.limits.max_depth:
            return False, f"Depth limit reached ({self.limits.max_depth})"
        
        # Check children count
        new_count = len(parent.children_ids) + count
        if new_count > self.limits.max_children:
            return False, (
                f"Would exceed children limit: "
                f"{len(parent.children_ids)} + {count} > {self.limits.max_children}"
            )
        
        return True, None
    
    def enforce_add_child(self, parent_id: str) -> None:
        """Raise appropriate error if child cannot be added."""
        parent = self.manifest.get_node(parent_id)
        
        if self.node_count >= self.limits.max_total_nodes:
            raise TotalNodesLimitError(self.node_count, self.limits.max_total_nodes)
        
        if parent.hierarchy_depth >= self.limits.max_depth:
            raise DepthLimitError(
                parent.label, parent.hierarchy_depth, self.limits.max_depth
            )
        
        if len(parent.children_ids) >= self.limits.max_children:
            raise ChildLimitError(
                parent.label, len(parent.children_ids), self.limits.max_children
            )
    
    # ── Validation ───────────────────────────────────────────────────────
    
    def validate(self) -> List[str]:
        """Run all validation checks. Returns list of errors (empty if valid)."""
        errors = []
        errors.extend(self._check_cycles())
        errors.extend(self._check_orphans())
        errors.extend(self._check_depth_consistency())
        errors.extend(self._check_parent_child_consistency())
        return errors
    
    def _check_cycles(self) -> List[str]:
        """Detect cycles in parent-child relationships."""
        errors = []
        
        for node_id, node in self.manifest.nodes.items():
            visited: Set[str] = set()
            current = node_id
            path: List[str] = []
            
            while current is not None:
                if current in visited:
                    # Found cycle
                    cycle_start = path.index(current) if current in path else 0
                    cycle = path[cycle_start:] + [current]
                    errors.append(f"Cycle detected: {' -> '.join(cycle)}")
                    break
                
                visited.add(current)
                path.append(current)
                
                current_node = self.manifest.nodes.get(current)
                if current_node is None:
                    break
                current = current_node.parent_id
        
        return errors
    
    def _check_orphans(self) -> List[str]:
        """Find nodes that have no path to root."""
        errors = []
        root_id = self.manifest.root_node_id
        
        # BFS from root to find all reachable nodes
        reachable: Set[str] = set()
        queue = deque([root_id])
        
        while queue:
            nid = queue.popleft()
            if nid in reachable:
                continue
            reachable.add(nid)
            
            node = self.manifest.nodes.get(nid)
            if node:
                queue.extend(node.children_ids)
        
        # Check for unreachable nodes
        for node_id, node in self.manifest.nodes.items():
            if node_id not in reachable:
                errors.append(f"Orphan node: '{node.label}' ({node_id})")
        
        return errors
    
    def _check_depth_consistency(self) -> List[str]:
        """Verify hierarchy_depth values are consistent with tree structure."""
        errors = []
        
        for node_id, node in self.manifest.nodes.items():
            if node.parent_id is None:
                # Root should be depth 0
                if node.hierarchy_depth != 0:
                    errors.append(
                        f"Root node '{node.label}' has depth {node.hierarchy_depth}, expected 0"
                    )
            else:
                parent = self.manifest.nodes.get(node.parent_id)
                if parent:
                    expected = parent.hierarchy_depth + 1
                    if node.hierarchy_depth != expected:
                        errors.append(
                            f"Node '{node.label}' has depth {node.hierarchy_depth}, "
                            f"expected {expected} (parent '{parent.label}' is at {parent.hierarchy_depth})"
                        )
        
        return errors
    
    def _check_parent_child_consistency(self) -> List[str]:
        """Verify parent_id and children_ids are consistent."""
        errors = []
        
        for node_id, node in self.manifest.nodes.items():
            # Check that parent lists this node as child
            if node.parent_id:
                parent = self.manifest.nodes.get(node.parent_id)
                if parent and node_id not in parent.children_ids:
                    errors.append(
                        f"Node '{node.label}' has parent '{parent.label}' "
                        f"but is not in parent's children_ids"
                    )
            
            # Check that all children list this node as parent
            for child_id in node.children_ids:
                child = self.manifest.nodes.get(child_id)
                if child and child.parent_id != node_id:
                    errors.append(
                        f"Node '{node.label}' lists '{child.label}' as child "
                        f"but child's parent_id is '{child.parent_id}'"
                    )
        
        return errors
    
    # ── Traversal ────────────────────────────────────────────────────────
    
    def traverse(
        self,
        order: TraversalOrder = TraversalOrder.DEPTH_FIRST_PRE,
        start_id: Optional[str] = None,
        filter_fn: Optional[Callable[[ManifestNode], bool]] = None,
    ) -> Generator[ManifestNode, None, None]:
        """Traverse the tree in specified order.
        
        Args:
            order: Traversal order (DFS pre/post, BFS, leaves-first)
            start_id: Starting node (default: root)
            filter_fn: Optional filter - only yield nodes where filter returns True
        
        Yields:
            ManifestNode objects in traversal order
        """
        start = start_id or self.root_id
        
        if order == TraversalOrder.DEPTH_FIRST_PRE:
            yield from self._dfs_pre(start, filter_fn)
        elif order == TraversalOrder.DEPTH_FIRST_POST:
            yield from self._dfs_post(start, filter_fn)
        elif order == TraversalOrder.BREADTH_FIRST:
            yield from self._bfs(start, filter_fn)
        elif order == TraversalOrder.LEAVES_FIRST:
            yield from self._leaves_first(start, filter_fn)
    
    def _dfs_pre(
        self,
        node_id: str,
        filter_fn: Optional[Callable[[ManifestNode], bool]],
    ) -> Generator[ManifestNode, None, None]:
        """Depth-first pre-order: parent before children."""
        node = self.manifest.nodes.get(node_id)
        if not node:
            return
        
        if filter_fn is None or filter_fn(node):
            yield node
        
        for child_id in node.children_ids:
            yield from self._dfs_pre(child_id, filter_fn)
    
    def _dfs_post(
        self,
        node_id: str,
        filter_fn: Optional[Callable[[ManifestNode], bool]],
    ) -> Generator[ManifestNode, None, None]:
        """Depth-first post-order: children before parent (bottom-up)."""
        node = self.manifest.nodes.get(node_id)
        if not node:
            return
        
        for child_id in node.children_ids:
            yield from self._dfs_post(child_id, filter_fn)
        
        if filter_fn is None or filter_fn(node):
            yield node
    
    def _bfs(
        self,
        start_id: str,
        filter_fn: Optional[Callable[[ManifestNode], bool]],
    ) -> Generator[ManifestNode, None, None]:
        """Breadth-first: level by level."""
        queue = deque([start_id])
        visited: Set[str] = set()
        
        while queue:
            node_id = queue.popleft()
            if node_id in visited:
                continue
            visited.add(node_id)
            
            node = self.manifest.nodes.get(node_id)
            if not node:
                continue
            
            if filter_fn is None or filter_fn(node):
                yield node
            
            queue.extend(node.children_ids)
    
    def _leaves_first(
        self,
        start_id: str,
        filter_fn: Optional[Callable[[ManifestNode], bool]],
    ) -> Generator[ManifestNode, None, None]:
        """Leaves first, then their parents, etc. (bottom-up by level)."""
        # Group nodes by depth
        by_depth: Dict[int, List[ManifestNode]] = {}
        
        for node in self._dfs_pre(start_id, None):
            depth = node.hierarchy_depth
            if depth not in by_depth:
                by_depth[depth] = []
            by_depth[depth].append(node)
        
        # Yield from deepest to shallowest
        for depth in sorted(by_depth.keys(), reverse=True):
            for node in by_depth[depth]:
                if filter_fn is None or filter_fn(node):
                    yield node
    
    def get_level(self, depth: int) -> List[ManifestNode]:
        """Get all nodes at a specific depth."""
        return [
            n for n in self.manifest.nodes.values()
            if n.hierarchy_depth == depth
        ]
    
    def get_leaves(self) -> List[ManifestNode]:
        """Get all leaf nodes (no children)."""
        return [n for n in self.manifest.nodes.values() if not n.children_ids]
    
    def get_internal_nodes(self) -> List[ManifestNode]:
        """Get all non-leaf nodes."""
        return [n for n in self.manifest.nodes.values() if n.children_ids]
    
    # ── Decomposition Helpers ────────────────────────────────────────────
    
    def get_decomposable_nodes(self) -> List[ManifestNode]:
        """Get nodes that can and should be decomposed.
        
        A node is decomposable if:
        1. Its kind is decomposable (MODEL, ASSEMBLY)
        2. It has no children yet (is a leaf)
        3. It's not at max depth
        """
        result = []
        for node in self.manifest.nodes.values():
            if not is_decomposable(node.kind):
                continue
            if node.children_ids:  # Already has children
                continue
            if node.hierarchy_depth >= self.limits.max_depth:
                continue
            result.append(node)
        return result
    
    def should_decompose(self, node_id: str) -> Tuple[bool, str]:
        """Determine if a node should be decomposed further.
        
        Returns (should_decompose, reason).
        
        Blueprint §4.2 stop conditions:
        A. Geometric manageability - single primitive or simple compound
        B. Semantic cohesion - parts that move/function together
        C. Independent verifiability - can be verified in isolation
        D. Interface clarity - clear attachment points
        E. Complexity budget - within limits
        F. Depth limit - not too deep
        """
        node = self.manifest.get_node(node_id)
        
        # Not decomposable kind
        if not is_decomposable(node.kind):
            return False, f"Kind {node.kind.value} is not decomposable"
        
        # Already has children
        if node.children_ids:
            return False, "Already decomposed"
        
        # At depth limit
        if node.hierarchy_depth >= self.limits.max_depth:
            return False, f"At depth limit ({self.limits.max_depth})"
        
        # Would exceed total nodes (need at least 2 children for meaningful decomposition)
        if self.node_count + self.limits.min_parts_for_assembly > self.limits.max_total_nodes:
            return False, "Would exceed total nodes limit"
        
        # Check if node has stage outputs suggesting it's simple enough
        stage_outputs = node.stage_outputs
        if "stage1" in stage_outputs:
            topology = stage_outputs["stage1"]
            # If Stage 1 already ran and produced few parts, don't decompose further
            if isinstance(topology, dict):
                parts = topology.get("parts", [])
                if len(parts) <= 1:
                    return False, "Single part - no decomposition needed"
        
        # Default: yes, decompose
        return True, "Decomposition recommended"
    
    def estimate_complexity(self, node_id: str) -> int:
        """Estimate complexity score for a node (higher = more complex).
        
        Used by scheduler to prioritize simpler nodes first.
        """
        node = self.manifest.get_node(node_id)
        score = 0
        
        # Base complexity by kind
        kind_scores = {
            NodeKind.MODEL: 10,
            NodeKind.ASSEMBLY: 5,
            NodeKind.PART: 1,
            NodeKind.INSTANCE: 0,  # Instances are cheap
            NodeKind.CONNECTOR: 2,
            NodeKind.CABLE: 3,
        }
        score += kind_scores.get(node.kind, 1)
        
        # Depth penalty (deeper = more context needed)
        score += node.hierarchy_depth
        
        # Children count (more children = more complex merge)
        score += len(node.children_ids) * 2
        
        # Retry penalty
        score += node.retry_count * 3
        
        return score
    
    # ── Path Operations ──────────────────────────────────────────────────
    
    def get_path_to_root(self, node_id: str) -> List[str]:
        """Get node IDs from node up to root (inclusive)."""
        path = []
        current = node_id
        visited: Set[str] = set()
        
        while current:
            if current in visited:
                logger.warning(f"Cycle detected in path to root from {node_id}")
                break
            visited.add(current)
            path.append(current)
            
            node = self.manifest.nodes.get(current)
            if not node:
                break
            current = node.parent_id
        
        return path
    
    def get_path_from_root(self, node_id: str) -> List[str]:
        """Get node IDs from root down to node (inclusive)."""
        return list(reversed(self.get_path_to_root(node_id)))
    
    def get_common_ancestor(self, node_id_a: str, node_id_b: str) -> Optional[str]:
        """Find the lowest common ancestor of two nodes."""
        path_a = set(self.get_path_to_root(node_id_a))
        
        for ancestor in self.get_path_to_root(node_id_b):
            if ancestor in path_a:
                return ancestor
        
        return None
    
    def get_siblings(self, node_id: str) -> List[ManifestNode]:
        """Get sibling nodes (same parent, excluding self)."""
        node = self.manifest.get_node(node_id)
        if not node.parent_id:
            return []
        
        parent = self.manifest.get_node(node.parent_id)
        return [
            self.manifest.nodes[cid]
            for cid in parent.children_ids
            if cid != node_id and cid in self.manifest.nodes
        ]
    
    # ── Subtree Operations ───────────────────────────────────────────────
    
    def get_subtree_size(self, node_id: str) -> int:
        """Count total nodes in subtree (including the node itself)."""
        count = 1
        node = self.manifest.nodes.get(node_id)
        if node:
            for child_id in node.children_ids:
                count += self.get_subtree_size(child_id)
        return count
    
    def get_subtree_depth(self, node_id: str) -> int:
        """Get maximum depth of subtree relative to node."""
        node = self.manifest.nodes.get(node_id)
        if not node or not node.children_ids:
            return 0
        
        max_child_depth = 0
        for child_id in node.children_ids:
            child_depth = self.get_subtree_depth(child_id)
            max_child_depth = max(max_child_depth, child_depth)
        
        return max_child_depth + 1
    
    def get_subtree_nodes(self, node_id: str) -> List[ManifestNode]:
        """Get all nodes in subtree (including the node itself)."""
        return list(self.traverse(
            order=TraversalOrder.DEPTH_FIRST_PRE,
            start_id=node_id,
        ))
    
    # ── Statistics ───────────────────────────────────────────────────────
    
    def get_stats(self) -> Dict[str, Any]:
        """Get hierarchy statistics."""
        nodes = list(self.manifest.nodes.values())
        
        if not nodes:
            return {
                "total_nodes": 0,
                "max_depth": 0,
                "avg_depth": 0,
                "leaf_count": 0,
                "internal_count": 0,
                "avg_children": 0,
                "max_children": 0,
            }
        
        depths = [n.hierarchy_depth for n in nodes]
        children_counts = [len(n.children_ids) for n in nodes]
        leaves = [n for n in nodes if not n.children_ids]
        internals = [n for n in nodes if n.children_ids]
        
        return {
            "total_nodes": len(nodes),
            "max_depth": max(depths),
            "avg_depth": sum(depths) / len(depths),
            "leaf_count": len(leaves),
            "internal_count": len(internals),
            "avg_children": sum(children_counts) / len(nodes) if nodes else 0,
            "max_children": max(children_counts) if children_counts else 0,
            "by_depth": {d: len([n for n in nodes if n.hierarchy_depth == d]) for d in range(max(depths) + 1)},
            "by_kind": {k.value: len([n for n in nodes if n.kind == k]) for k in NodeKind if any(n.kind == k for n in nodes)},
        }
    
    def print_stats(self) -> str:
        """Return formatted statistics string."""
        stats = self.get_stats()
        lines = [
            f"Hierarchy Statistics:",
            f"  Total nodes: {stats['total_nodes']}",
            f"  Max depth: {stats['max_depth']}",
            f"  Avg depth: {stats['avg_depth']:.1f}",
            f"  Leaves: {stats['leaf_count']}",
            f"  Internal: {stats['internal_count']}",
            f"  Avg children: {stats['avg_children']:.1f}",
            f"  Max children: {stats['max_children']}",
        ]
        
        if stats.get("by_depth"):
            lines.append("  By depth:")
            for d, count in sorted(stats["by_depth"].items()):
                lines.append(f"    {d}: {count}")
        
        if stats.get("by_kind"):
            lines.append("  By kind:")
            for k, count in sorted(stats["by_kind"].items()):
                lines.append(f"    {k}: {count}")
        
        return "\n".join(lines)
