"""Dependency DAG — directed acyclic graph for build ordering.

The dependency graph is SEPARATE from the containment hierarchy:
- Containment: parent-child tree (what contains what)
- Dependency: build ordering (what must exist before what)

Default rule: children depend on parent existing (but not being VERIFIED).
Explicit dependencies can be added for cross-assembly relationships.

Key operations:
- Topological sort for build order
- Cycle detection (dependencies must be acyclic)
- Frontier computation (what's ready to build now)
- Blocked-by queries (what's blocking a node)

Blueprint references: §2.2 (dependency DAG), §9 (build frontier), §34 (cross-assembly).
"""

from __future__ import annotations

import logging
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import (
    Any,
    Callable,
    Dict,
    FrozenSet,
    Generator,
    List,
    Optional,
    Set,
    Tuple,
    TYPE_CHECKING,
)

if TYPE_CHECKING:
    from .manifest import BuildManifest, ManifestNode

from .node_types import NodeKind, is_decomposable
from .manifest import NodeState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dependency Types
# ---------------------------------------------------------------------------

class DependencyType(str, Enum):
    """Type of dependency relationship."""
    # Hierarchy — execution order
    # CHILD_MERGE: an assembly depends on each of its children being VERIFIED
    # before it can merge.  Containment (A is inside B) does NOT mean A waits
    # for B; it means B waits for A.  This is the inverse of the old
    # PARENT_EXISTS edge and fixes the circular deadlock where a child waited
    # for a parent to verify while the parent waited for the child to merge.
    CHILD_MERGE = "child_merge"          # Assembly depends on child being VERIFIED
    SIBLING_ORDER = "sibling_order"      # Earlier siblings built first

    # Explicit cross-assembly
    SOCKET_CONNECTION = "socket_connection"  # Connected via socket
    MATERIAL_SHARED = "material_shared"      # Shares material definition
    INSTANCE_OF = "instance_of"              # Instance depends on definition

    # Semantic edges (derived from socket vocabulary)
    BOOLEAN_TARGET = "boolean_target"    # BOOLEAN_CUT node depends on its cut target (ROOT sibling)
    INSET_TARGET = "inset_target"        # INSET node depends on its BOOLEAN_CUT sibling (hole must exist first)
    SIBLING_ROOT_REF = "sibling_root_ref"  # Non-ROOT sibling depends on ROOT sibling (always assembly-local, never global)
    CROSS_REFERENCE = "cross_reference"  # BRIDGE/STRUT/RELATIVE_TO/RADIAL_BRIDGE target
    MISSING_TARGET = "missing_target"    # Cross-reference target label not found in manifest
    INVALID_DEPENDENCY = "invalid_dependency"  # Dependency structurally invalid (e.g. self-bridge)

    # Build phase ordering
    PHASE_ORDER = "phase_order"          # Later phase depends on earlier


@dataclass
class Dependency:
    """A single dependency edge."""
    from_node: str          # Node that has the dependency
    to_node: str            # Node that must be ready first
    dep_type: DependencyType
    required: bool = True   # If False, dependency is soft (can skip if target fails)
    
    def __hash__(self):
        return hash((self.from_node, self.to_node, self.dep_type))
    
    def __eq__(self, other):
        if not isinstance(other, Dependency):
            return False
        return (self.from_node == other.from_node and 
                self.to_node == other.to_node and
                self.dep_type == other.dep_type)


@dataclass
class DependencyBlock:
    """Structured description of a single blocking dependency.

    Replaces the old (blocker_id, reason_str) tuple so that the controller
    and UI can inspect the exact reason without string parsing.

    Fields:
        blocker_id:    node_id of the node that is blocking progress.
        blocker_state: current NodeState of the blocking node (or None if
                       the node is absent from the manifest).
        dep_type:      the DependencyType edge that is unsatisfied.
        reason:        human-readable summary for logs / UI traces.
    """
    blocker_id: str
    blocker_state: Optional[Any]   # NodeState | None
    dep_type: DependencyType
    reason: str

    def __str__(self) -> str:
        state_str = self.blocker_state.value if self.blocker_state else "missing"
        return (
            f"BLOCKED: requires '{self.blocker_id}' "
            f"(State: {state_str}) for {self.dep_type.value}"
        )


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class DependencyError(Exception):
    """Base exception for dependency graph errors."""
    pass


class CyclicDependencyError(DependencyError):
    """Raised when adding a dependency would create a cycle."""
    def __init__(self, cycle: List[str]):
        self.cycle = cycle
        super().__init__(f"Cyclic dependency detected: {' -> '.join(cycle)}")


class MissingNodeError(DependencyError):
    """Raised when referencing a node not in the graph."""
    def __init__(self, node_id: str):
        self.node_id = node_id
        super().__init__(f"Node not found in dependency graph: {node_id}")


# ---------------------------------------------------------------------------
# DependencyDAG
# ---------------------------------------------------------------------------

class DependencyDAG:
    """Directed acyclic graph for build ordering.
    
    Maintains dependency relationships between nodes and provides:
    - Topological sort for valid build orders
    - Cycle detection when adding edges
    - Frontier computation (nodes ready to build)
    - Blocked-by queries
    
    Works alongside BuildManifest - does not duplicate node storage.
    """
    
    def __init__(self, manifest: Optional[BuildManifest] = None):
        """Initialize DAG, optionally from a manifest."""
        self.manifest = manifest
        
        # Adjacency lists
        # forward[A] = {B, C} means A depends on B and C (B, C must be done before A)
        self._forward: Dict[str, Set[str]] = defaultdict(set)
        # reverse[B] = {A} means A depends on B (A is blocked by B)
        self._reverse: Dict[str, Set[str]] = defaultdict(set)
        
        # Detailed dependency info
        self._dependencies: Dict[Tuple[str, str], Dependency] = {}
        
        # All known nodes
        self._nodes: Set[str] = set()
        
        # Build from manifest if provided
        if manifest:
            self._build_from_manifest()
    
    # ── Construction ─────────────────────────────────────────────────────
    
    def _build_from_manifest(self) -> None:
        """Build dependency graph from manifest hierarchy and explicit deps."""
        if not self.manifest:
            return
        
        # Add all nodes
        for node_id in self.manifest.nodes:
            self._nodes.add(node_id)
        
        # CHILD_MERGE edges: each assembly/model depends on its children being
        # VERIFIED before it can merge.  This is the inverse of the old
        # PARENT_EXISTS pattern and eliminates the circular deadlock where a
        # child waited for a parent to verify while the parent waited for the
        # child to merge.
        for node_id, node in self.manifest.nodes.items():
            from .node_types import NodeKind as _NK
            if node.kind in (_NK.ASSEMBLY, _NK.MODEL):
                for child_id in node.children_ids:
                    if child_id in self.manifest.nodes:
                        self.add_dependency(
                            from_node=node_id,
                            to_node=child_id,
                            dep_type=DependencyType.CHILD_MERGE,
                            required=True,
                        )

            # Instance depends on definition
            if node.instance_of and node.instance_of in self.manifest.nodes:
                self.add_dependency(
                    from_node=node_id,
                    to_node=node.instance_of,
                    dep_type=DependencyType.INSTANCE_OF,
                    required=True,
                )

            # Explicit dependencies from node
            for dep_id in node.dependency_ids:
                if dep_id in self.manifest.nodes:
                    self.add_dependency(
                        from_node=node_id,
                        to_node=dep_id,
                        dep_type=DependencyType.SOCKET_CONNECTION,
                        required=True,
                    )

            # ── Semantic edges from socket vocabulary ────────────────────
            if not node.attachment:
                continue
            from .node_types import SocketType, CROSS_REFERENCE_SOCKETS
            socket = node.attachment.socket_type
            parent = self.manifest.nodes.get(node.parent_id) if node.parent_id else None

            # BOOLEAN_TARGET: BOOLEAN_CUT depends on ROOT sibling (the body it cuts)
            if socket == SocketType.BOOLEAN_CUT and parent:
                for sib_id in parent.children_ids:
                    if sib_id == node_id:
                        continue
                    sib = self.manifest.nodes.get(sib_id)
                    if sib and sib.attachment and sib.attachment.socket_type == SocketType.ROOT:
                        self.add_dependency(
                            from_node=node_id,
                            to_node=sib_id,
                            dep_type=DependencyType.BOOLEAN_TARGET,
                            required=True,
                        )
                        break

            # INSET_TARGET: INSET depends on BOOLEAN_CUT sibling (hole must exist before panel fills it)
            elif socket == SocketType.INSET and parent:
                for sib_id in parent.children_ids:
                    if sib_id == node_id:
                        continue
                    sib = self.manifest.nodes.get(sib_id)
                    if sib and sib.attachment and sib.attachment.socket_type == SocketType.BOOLEAN_CUT:
                        self.add_dependency(
                            from_node=node_id,
                            to_node=sib_id,
                            dep_type=DependencyType.INSET_TARGET,
                            required=True,
                        )
                        break

            # SIBLING_ROOT_REF: non-ROOT siblings depend on ROOT sibling (assembly-local)
            elif socket not in (SocketType.ROOT,) and socket not in CROSS_REFERENCE_SOCKETS and parent:
                for sib_id in parent.children_ids:
                    if sib_id == node_id:
                        continue
                    sib = self.manifest.nodes.get(sib_id)
                    if sib and sib.attachment and sib.attachment.socket_type == SocketType.ROOT:
                        self.add_dependency(
                            from_node=node_id,
                            to_node=sib_id,
                            dep_type=DependencyType.SIBLING_ROOT_REF,
                            required=True,
                        )
                        break

            # CROSS_REFERENCE: BRIDGE/STRUT/RELATIVE_TO/RADIAL_BRIDGE depend on named target
            elif socket in CROSS_REFERENCE_SOCKETS:
                hint = node.stage_outputs.get("decomposition_hint", {})
                target_label = (
                    hint.get("connects_to") or hint.get("relative_to")
                    or (node.attachment.connects_to if hasattr(node.attachment, "connects_to") else None)
                    or (node.attachment.relative_to if hasattr(node.attachment, "relative_to") else None)
                )
                if target_label:
                    target = self.manifest.get_node_by_label(target_label)
                    if target and target.node_id in self.manifest.nodes:
                        self.add_dependency(
                            from_node=node_id,
                            to_node=target.node_id,
                            dep_type=DependencyType.CROSS_REFERENCE,
                            required=True,
                        )
    
    @classmethod
    def from_manifest(cls, manifest: BuildManifest) -> DependencyDAG:
        """Factory method to create DAG from manifest."""
        return cls(manifest)
    
    def rebuild(self) -> None:
        """Rebuild the graph from current manifest state."""
        self._forward.clear()
        self._reverse.clear()
        self._dependencies.clear()
        self._nodes.clear()
        self._build_from_manifest()
    
    # ── Node Management ──────────────────────────────────────────────────
    
    def add_node(self, node_id: str) -> None:
        """Add a node to the graph (no dependencies yet)."""
        self._nodes.add(node_id)
    
    def remove_node(self, node_id: str) -> None:
        """Remove a node and all its dependencies."""
        if node_id not in self._nodes:
            return
        
        # Remove forward edges from this node
        for target in list(self._forward.get(node_id, [])):
            self._reverse[target].discard(node_id)
            key = (node_id, target)
            self._dependencies.pop(key, None)
        self._forward.pop(node_id, None)
        
        # Remove reverse edges to this node
        for source in list(self._reverse.get(node_id, [])):
            self._forward[source].discard(node_id)
            key = (source, node_id)
            self._dependencies.pop(key, None)
        self._reverse.pop(node_id, None)
        
        self._nodes.discard(node_id)
    
    def has_node(self, node_id: str) -> bool:
        """Check if node exists in graph."""
        return node_id in self._nodes
    
    @property
    def node_count(self) -> int:
        """Number of nodes in graph."""
        return len(self._nodes)
    
    @property
    def edge_count(self) -> int:
        """Number of dependency edges."""
        return len(self._dependencies)
    
    # ── Dependency Management ────────────────────────────────────────────
    
    def add_dependency(
        self,
        from_node: str,
        to_node: str,
        dep_type: DependencyType = DependencyType.SOCKET_CONNECTION,
        required: bool = True,
        check_cycle: bool = True,
    ) -> None:
        """Add a dependency: from_node depends on to_node.
        
        Args:
            from_node: Node that has the dependency
            to_node: Node that must be ready first
            dep_type: Type of dependency
            required: If True, from_node cannot proceed if to_node fails
            check_cycle: If True, verify no cycle is created
        
        Raises:
            CyclicDependencyError: If this would create a cycle
        """
        if from_node == to_node:
            return  # Self-dependency is no-op
        
        # Ensure nodes exist
        self._nodes.add(from_node)
        self._nodes.add(to_node)
        
        # Check for cycle before adding
        if check_cycle and self._would_create_cycle(from_node, to_node):
            cycle = self._find_cycle_path(from_node, to_node)
            raise CyclicDependencyError(cycle)
        
        # Add edge
        self._forward[from_node].add(to_node)
        self._reverse[to_node].add(from_node)
        
        # Store detailed info
        dep = Dependency(from_node, to_node, dep_type, required)
        self._dependencies[(from_node, to_node)] = dep
    
    def remove_dependency(self, from_node: str, to_node: str) -> None:
        """Remove a dependency edge."""
        self._forward[from_node].discard(to_node)
        self._reverse[to_node].discard(from_node)
        self._dependencies.pop((from_node, to_node), None)
    
    def has_dependency(self, from_node: str, to_node: str) -> bool:
        """Check if from_node depends on to_node."""
        return to_node in self._forward.get(from_node, set())
    
    def get_dependency(self, from_node: str, to_node: str) -> Optional[Dependency]:
        """Get dependency details."""
        return self._dependencies.get((from_node, to_node))
    
    def get_dependencies(self, node_id: str) -> List[Dependency]:
        """Get all dependencies OF a node (what it depends on)."""
        return [
            self._dependencies[(node_id, target)]
            for target in self._forward.get(node_id, [])
            if (node_id, target) in self._dependencies
        ]
    
    def get_dependents(self, node_id: str) -> List[str]:
        """Get nodes that depend ON this node."""
        return list(self._reverse.get(node_id, []))
    
    def get_blockers(self, node_id: str) -> List[str]:
        """Get nodes that block this node (same as forward edges)."""
        return list(self._forward.get(node_id, []))
    
    # ── Cycle Detection ──────────────────────────────────────────────────
    
    def _would_create_cycle(self, from_node: str, to_node: str) -> bool:
        """Check if adding from_node -> to_node would create a cycle.
        
        A cycle would exist if to_node can already reach from_node.
        """
        # If to_node can reach from_node, adding from_node -> to_node creates cycle
        return self._can_reach(to_node, from_node)
    
    def _can_reach(self, start: str, target: str) -> bool:
        """Check if target is reachable from start via forward edges."""
        if start == target:
            return True
        
        visited: Set[str] = set()
        queue = deque([start])
        
        while queue:
            current = queue.popleft()
            if current in visited:
                continue
            visited.add(current)
            
            for next_node in self._forward.get(current, []):
                if next_node == target:
                    return True
                queue.append(next_node)
        
        return False
    
    def _find_cycle_path(self, from_node: str, to_node: str) -> List[str]:
        """Find the path that would form a cycle."""
        # Path from to_node back to from_node
        path = self._find_path(to_node, from_node)
        if path:
            return [from_node, to_node] + path[1:]  # from -> to -> ... -> from
        return [from_node, to_node, from_node]
    
    def _find_path(self, start: str, target: str) -> Optional[List[str]]:
        """Find a path from start to target."""
        if start == target:
            return [start]
        
        visited: Set[str] = set()
        queue = deque([(start, [start])])
        
        while queue:
            current, path = queue.popleft()
            if current in visited:
                continue
            visited.add(current)
            
            for next_node in self._forward.get(current, []):
                new_path = path + [next_node]
                if next_node == target:
                    return new_path
                queue.append((next_node, new_path))
        
        return None
    
    def detect_cycles(self) -> List[List[str]]:
        """Find all cycles in the graph. Returns list of cycle paths."""
        cycles: List[List[str]] = []
        visited: Set[str] = set()
        rec_stack: Set[str] = set()
        
        def dfs(node: str, path: List[str]) -> None:
            visited.add(node)
            rec_stack.add(node)
            path.append(node)
            
            for neighbor in self._forward.get(node, []):
                if neighbor not in visited:
                    dfs(neighbor, path)
                elif neighbor in rec_stack:
                    # Found cycle
                    cycle_start = path.index(neighbor)
                    cycle = path[cycle_start:] + [neighbor]
                    cycles.append(cycle)
            
            path.pop()
            rec_stack.remove(node)
        
        for node in self._nodes:
            if node not in visited:
                dfs(node, [])
        
        return cycles
    
    def is_acyclic(self) -> bool:
        """Check if graph has no cycles."""
        return len(self.detect_cycles()) == 0
    
    # ── Topological Sort ─────────────────────────────────────────────────
    
    def topological_sort(self) -> List[str]:
        """Return nodes in topological order (dependencies first).
        
        Raises:
            CyclicDependencyError: If graph has cycles
        """
        # Kahn's algorithm
        in_degree: Dict[str, int] = {node: 0 for node in self._nodes}
        for node in self._nodes:
            for dep in self._forward.get(node, []):
                if dep in in_degree:
                    pass  # dep is a dependency, not dependent
            for dependent in self._reverse.get(node, []):
                if dependent in in_degree:
                    in_degree[dependent] += 0  # Already counted
        
        # Count incoming edges
        for node in self._nodes:
            in_degree[node] = len(self._forward.get(node, set()))
        
        # Start with nodes that have no dependencies
        queue = deque([n for n in self._nodes if in_degree[n] == 0])
        result: List[str] = []
        
        while queue:
            node = queue.popleft()
            result.append(node)
            
            # Reduce in-degree of dependents
            for dependent in self._reverse.get(node, []):
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)
        
        if len(result) != len(self._nodes):
            # Cycle detected
            remaining = self._nodes - set(result)
            raise CyclicDependencyError(list(remaining)[:5])
        
        return result
    
    def topological_sort_grouped(self) -> List[List[str]]:
        """Return nodes grouped by level (all nodes in a level can be built in parallel).
        
        Level 0: nodes with no dependencies
        Level 1: nodes depending only on level 0
        etc.
        """
        levels: List[List[str]] = []
        remaining = set(self._nodes)
        completed: Set[str] = set()
        
        while remaining:
            # Find nodes whose dependencies are all completed
            ready = [
                n for n in remaining
                if all(dep in completed for dep in self._forward.get(n, []))
            ]
            
            if not ready:
                # Cycle detected
                raise CyclicDependencyError(list(remaining)[:5])
            
            levels.append(ready)
            completed.update(ready)
            remaining -= set(ready)
        
        return levels
    
    # ── Build Frontier ───────────────────────────────────────────────────
    
    def get_ready_nodes(
        self,
        completed: Set[str],
        failed: Optional[Set[str]] = None,
        filter_fn: Optional[Callable[[str], bool]] = None,
    ) -> List[str]:
        """Get nodes ready to build (all dependencies satisfied).
        
        Args:
            completed: Set of node IDs that are done (VERIFIED)
            failed: Set of node IDs that failed (optional)
            filter_fn: Additional filter (e.g., check node state)
        
        Returns:
            List of node IDs ready to build
        """
        failed = failed or set()
        ready = []
        
        for node_id in self._nodes:
            if node_id in completed or node_id in failed:
                continue
            
            # Check all dependencies
            deps = self._forward.get(node_id, set())
            all_satisfied = True
            
            for dep_id in deps:
                dep_info = self._dependencies.get((node_id, dep_id))
                
                if dep_id in completed:
                    continue  # Satisfied
                
                if dep_id in failed:
                    # Dependency failed
                    if dep_info and not dep_info.required:
                        continue  # Soft dependency, can proceed
                    all_satisfied = False
                    break
                
                # Dependency not yet done
                all_satisfied = False
                break
            
            if all_satisfied:
                if filter_fn is None or filter_fn(node_id):
                    ready.append(node_id)
        
        return ready
    
    def get_frontier(self) -> List[str]:
        """Get current build frontier using manifest state.
        
        A node is in the frontier if:
        1. It's in READY state
        2. All its dependencies are VERIFIED (or SKIPPED for soft deps)
        """
        if not self.manifest:
            return []
        
        completed = {
            nid for nid, node in self.manifest.nodes.items()
            if node.state == NodeState.VERIFIED
        }
        failed = {
            nid for nid, node in self.manifest.nodes.items()
            if node.state in (NodeState.FAILED, NodeState.SKIPPED)
        }
        
        def is_ready_state(node_id: str) -> bool:
            node = self.manifest.nodes.get(node_id)
            return node is not None and node.state == NodeState.READY
        
        return self.get_ready_nodes(completed, failed, is_ready_state)
    
    def get_missing_targets(self) -> List[Tuple[str, str]]:
        """Return (node_id, target_label) pairs where a cross-reference target
        label was recorded in decomposition_hint but no matching node exists.

        Used for pre-build validation: if any entry is returned the manifest
        has dangling references that Stage 4 pass-2 will fail on.
        """
        if not self.manifest:
            return []
        from .node_types import CROSS_REFERENCE_SOCKETS
        missing = []
        for node_id, node in self.manifest.nodes.items():
            if not node.attachment:
                continue
            if node.attachment.socket_type not in CROSS_REFERENCE_SOCKETS:
                continue
            hint = node.stage_outputs.get("decomposition_hint", {})
            target_label = (
                hint.get("connects_to") or hint.get("relative_to")
                or (node.attachment.connects_to if hasattr(node.attachment, "connects_to") else None)
                or (node.attachment.relative_to if hasattr(node.attachment, "relative_to") else None)
            )
            if not target_label:
                continue
            if self.manifest.get_node_by_label(target_label) is None:
                missing.append((node_id, target_label))
        return missing

    def get_blocked_by(self, node_id: str) -> List[DependencyBlock]:
        """Get structured DependencyBlock list for what's blocking a node.

        CHILD_MERGE and SIBLING_ORDER edges only require the dependency to
        be non-failed — they do NOT require VERIFIED.  All other edge types
        require VERIFIED before the dependent can proceed.

        Returns a list of DependencyBlock dataclasses instead of raw
        (id, reason) tuples so callers can inspect dep_type without parsing.
        """
        if not self.manifest:
            return [
                DependencyBlock(
                    blocker_id=dep,
                    blocker_state=None,
                    dep_type=DependencyType.SOCKET_CONNECTION,
                    reason="unknown (no manifest)",
                )
                for dep in self._forward.get(node_id, [])
            ]

        # Edge types that only need the dependency to be non-failed (not VERIFIED)
        _EXISTENCE_ONLY = {DependencyType.CHILD_MERGE, DependencyType.SIBLING_ORDER}

        blockers: List[DependencyBlock] = []
        for dep_id in self._forward.get(node_id, []):
            dep_node = self.manifest.nodes.get(dep_id)
            if not dep_node:
                blockers.append(DependencyBlock(
                    blocker_id=dep_id,
                    blocker_state=None,
                    dep_type=DependencyType.MISSING_TARGET,
                    reason="blocker node missing from manifest",
                ))
                continue

            dep_info = self._dependencies.get((node_id, dep_id))
            dep_type = dep_info.dep_type if dep_info else DependencyType.SOCKET_CONNECTION

            if dep_type in _EXISTENCE_ONLY:
                # Only block if the dependency has permanently failed
                if dep_node.state == NodeState.FAILED and dep_info and dep_info.required:
                    if not dep_node.can_retry():
                        blockers.append(DependencyBlock(
                            blocker_id=dep_id,
                            blocker_state=dep_node.state,
                            dep_type=dep_type,
                            reason=f"permanently failed: {dep_node.error_message or 'unknown'}",
                        ))
                elif dep_node.state == NodeState.SKIPPED and dep_info and dep_info.required:
                    blockers.append(DependencyBlock(
                        blocker_id=dep_id,
                        blocker_state=dep_node.state,
                        dep_type=dep_type,
                        reason="skipped (required)",
                    ))
                # Any other state (PLANNED, READY, BUILDING, VERIFIED, …) is fine
                continue

            # All other edge types require VERIFIED
            if dep_node.state == NodeState.VERIFIED:
                continue  # Not blocking

            if dep_node.state == NodeState.FAILED:
                blockers.append(DependencyBlock(
                    blocker_id=dep_id,
                    blocker_state=dep_node.state,
                    dep_type=dep_type,
                    reason=f"failed: {dep_node.error_message or 'unknown'}",
                ))
            elif dep_node.state == NodeState.SKIPPED:
                if dep_info and dep_info.required:
                    blockers.append(DependencyBlock(
                        blocker_id=dep_id,
                        blocker_state=dep_node.state,
                        dep_type=dep_type,
                        reason="skipped (required)",
                    ))
            else:
                blockers.append(DependencyBlock(
                    blocker_id=dep_id,
                    blocker_state=dep_node.state,
                    dep_type=dep_type,
                    reason=f"state: {dep_node.state.value}",
                ))

        return blockers
    
    def is_blocked(self, node_id: str) -> bool:
        """Check if a node is blocked by unmet dependencies."""
        return len(self.get_blocked_by(node_id)) > 0
    
    # ── Impact Analysis ──────────────────────────────────────────────────
    
    def get_downstream(self, node_id: str) -> Set[str]:
        """Get all nodes that transitively depend on this node."""
        downstream: Set[str] = set()
        queue = deque([node_id])
        
        while queue:
            current = queue.popleft()
            for dependent in self._reverse.get(current, []):
                if dependent not in downstream:
                    downstream.add(dependent)
                    queue.append(dependent)
        
        return downstream
    
    def get_upstream(self, node_id: str) -> Set[str]:
        """Get all nodes this node transitively depends on."""
        upstream: Set[str] = set()
        queue = deque([node_id])
        
        while queue:
            current = queue.popleft()
            for dep in self._forward.get(current, []):
                if dep not in upstream:
                    upstream.add(dep)
                    queue.append(dep)
        
        return upstream
    
    def get_impact_of_failure(self, node_id: str) -> Dict[str, Any]:
        """Analyze impact if a node fails.
        
        Returns dict with:
        - blocked_count: How many nodes would be blocked
        - blocked_required: Required nodes that would be blocked
        - blocked_optional: Optional nodes that would be blocked
        """
        downstream = self.get_downstream(node_id)
        
        if not self.manifest:
            return {
                "blocked_count": len(downstream),
                "blocked_required": list(downstream),
                "blocked_optional": [],
            }
        
        required = []
        optional = []
        
        for nid in downstream:
            node = self.manifest.nodes.get(nid)
            if node:
                from .node_types import NodeImportance
                if node.importance == NodeImportance.REQUIRED:
                    required.append(nid)
                else:
                    optional.append(nid)
        
        return {
            "blocked_count": len(downstream),
            "blocked_required": required,
            "blocked_optional": optional,
        }
    
    # ── Serialization ────────────────────────────────────────────────────
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict for persistence."""
        return {
            "nodes": list(self._nodes),
            "dependencies": [
                {
                    "from": dep.from_node,
                    "to": dep.to_node,
                    "type": dep.dep_type.value,
                    "required": dep.required,
                }
                for dep in self._dependencies.values()
            ],
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any], manifest: Optional[BuildManifest] = None) -> DependencyDAG:
        """Reconstruct from dict."""
        dag = cls(manifest=None)  # Don't auto-build
        dag.manifest = manifest
        
        for node_id in data.get("nodes", []):
            dag.add_node(node_id)
        
        for dep_data in data.get("dependencies", []):
            dag.add_dependency(
                from_node=dep_data["from"],
                to_node=dep_data["to"],
                dep_type=DependencyType(dep_data.get("type", "socket_connection")),
                required=dep_data.get("required", True),
                check_cycle=False,  # Trust serialized data
            )
        
        return dag
    
    # ── Debug ────────────────────────────────────────────────────────────
    
    def print_graph(self) -> str:
        """Return string representation of the graph."""
        lines = [f"DependencyDAG: {self.node_count} nodes, {self.edge_count} edges"]
        
        # Group by dependency count
        by_dep_count: Dict[int, List[str]] = defaultdict(list)
        for node in self._nodes:
            count = len(self._forward.get(node, []))
            by_dep_count[count].append(node)
        
        for count in sorted(by_dep_count.keys()):
            nodes = by_dep_count[count]
            lines.append(f"\n{count} dependencies:")
            for node in sorted(nodes):
                deps = self._forward.get(node, set())
                if deps:
                    dep_str = ", ".join(sorted(deps))
                    lines.append(f"  {node} <- [{dep_str}]")
                else:
                    lines.append(f"  {node} (root)")
        
        return "\n".join(lines)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get graph statistics."""
        if not self._nodes:
            return {
                "node_count": 0,
                "edge_count": 0,
                "max_in_degree": 0,
                "max_out_degree": 0,
                "avg_in_degree": 0,
                "roots": [],
                "leaves": [],
            }
        
        in_degrees = [len(self._forward.get(n, [])) for n in self._nodes]
        out_degrees = [len(self._reverse.get(n, [])) for n in self._nodes]
        
        roots = [n for n in self._nodes if len(self._forward.get(n, [])) == 0]
        leaves = [n for n in self._nodes if len(self._reverse.get(n, [])) == 0]
        
        return {
            "node_count": len(self._nodes),
            "edge_count": len(self._dependencies),
            "max_in_degree": max(in_degrees) if in_degrees else 0,
            "max_out_degree": max(out_degrees) if out_degrees else 0,
            "avg_in_degree": sum(in_degrees) / len(in_degrees) if in_degrees else 0,
            "roots": roots,
            "leaves": leaves,
        }
