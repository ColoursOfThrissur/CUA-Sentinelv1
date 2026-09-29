"""Dependency DAG — build-order graph separate from containment hierarchy.

Defines what must be available (VERIFIED) before a node can be built, merged,
or verified.  The dependency graph is separate from the containment tree:
a node's dependencies may include siblings, cousins, or nodes from entirely
different branches.

The canonical example from the blueprint:
    wheel_definition → cannon_assembly → armament_assembly → ship

Blueprint references: §2.2 (dependency DAG), §34 (tree depth vs dependency depth).
"""

from __future__ import annotations

import logging
from collections import defaultdict, deque
from typing import Dict, FrozenSet, List, Optional, Set, Tuple

from .manifest import BuildManifest, ManifestNode, NodeState

logger = logging.getLogger(__name__)


class CycleError(Exception):
    """Raised when a dependency cycle is detected."""
    def __init__(self, cycle: List[str]):
        self.cycle = cycle
        super().__init__(f"Dependency cycle detected: {' → '.join(cycle)}")


class DependencyDAG:
    """Directed acyclic graph for build ordering.

    Edges are stored as ``node_id → set(depends_on_ids)``.  An edge
    ``A depends on B`` means B must be VERIFIED before A can enter the
    build frontier.

    This class is independent of the containment tree — you can have
    dependency edges between nodes at any hierarchy level.
    """

    def __init__(self):
        # Forward edges: node_id → set of node_ids it depends on
        self._deps: Dict[str, Set[str]] = defaultdict(set)
        # Reverse edges: node_id → set of node_ids that depend on it
        self._rdeps: Dict[str, Set[str]] = defaultdict(set)
        # All known node IDs
        self._all_nodes: Set[str] = set()

    # ── Construction ─────────────────────────────────────────────────────

    def add_node(self, node_id: str) -> None:
        """Register a node (with no dependencies yet)."""
        self._all_nodes.add(node_id)

    def add_dependency(self, node_id: str, depends_on: str) -> None:
        """Declare that ``node_id`` depends on ``depends_on``.

        Raises CycleError if this edge would create a cycle.
        """
        if node_id == depends_on:
            raise CycleError([node_id, depends_on])

        # Tentatively add the edge
        self._deps[node_id].add(depends_on)
        self._rdeps[depends_on].add(node_id)
        self._all_nodes.add(node_id)
        self._all_nodes.add(depends_on)

        # Check for cycles via DFS from depends_on looking for node_id
        cycle = self._find_path(depends_on, node_id)
        if cycle is not None:
            # Roll back the edge
            self._deps[node_id].discard(depends_on)
            self._rdeps[depends_on].discard(node_id)
            raise CycleError(cycle + [depends_on])

    def remove_dependency(self, node_id: str, depends_on: str) -> None:
        """Remove a dependency edge."""
        self._deps[node_id].discard(depends_on)
        self._rdeps[depends_on].discard(node_id)

    def remove_node(self, node_id: str) -> None:
        """Remove a node and all its edges."""
        # Remove forward edges
        for dep in list(self._deps.get(node_id, [])):
            self._rdeps[dep].discard(node_id)
        self._deps.pop(node_id, None)

        # Remove reverse edges
        for dependent in list(self._rdeps.get(node_id, [])):
            self._deps[dependent].discard(node_id)
        self._rdeps.pop(node_id, None)

        self._all_nodes.discard(node_id)

    # ── Bulk construction ────────────────────────────────────────────────

    @classmethod
    def from_manifest(cls, manifest: BuildManifest) -> DependencyDAG:
        """Build a DAG from the manifest's declared dependency_ids.

        Also adds implicit containment dependencies: if a node's parent is
        an ASSEMBLY, all children are implicit dependencies of the parent
        (the parent can only merge after all children are built).
        """
        dag = cls()

        for nid, node in manifest.nodes.items():
            dag.add_node(nid)

        for nid, node in manifest.nodes.items():
            # Explicit dependencies
            for dep_id in node.dependency_ids:
                if dep_id in manifest.nodes:
                    try:
                        dag.add_dependency(nid, dep_id)
                    except CycleError as e:
                        logger.warning(
                            f"Skipping dependency {nid} → {dep_id}: {e}"
                        )

            # Implicit: parent ASSEMBLY depends on all its children
            if node.parent_id and node.parent_id in manifest.nodes:
                parent = manifest.nodes[node.parent_id]
                if parent.kind.value in ("assembly", "model"):
                    try:
                        dag.add_dependency(node.parent_id, nid)
                    except CycleError:
                        pass  # Should not happen with valid hierarchy

        return dag

    # ── Queries ──────────────────────────────────────────────────────────

    def get_dependencies(self, node_id: str) -> Set[str]:
        """Return the set of node_ids that ``node_id`` directly depends on."""
        return set(self._deps.get(node_id, set()))

    def get_dependents(self, node_id: str) -> Set[str]:
        """Return the set of node_ids that directly depend on ``node_id``."""
        return set(self._rdeps.get(node_id, set()))

    def get_all_upstream(self, node_id: str) -> Set[str]:
        """Return all transitive dependencies (everything that must finish first)."""
        result: Set[str] = set()
        queue = deque(self._deps.get(node_id, set()))
        while queue:
            dep = queue.popleft()
            if dep not in result:
                result.add(dep)
                queue.extend(self._deps.get(dep, set()) - result)
        return result

    def get_ready_nodes(self, completed: Set[str]) -> List[str]:
        """Return nodes whose dependencies are all in the ``completed`` set.

        A node is "ready" if every node it depends on is in ``completed``.
        Nodes already in ``completed`` are excluded from the result.
        """
        ready: List[str] = []
        for nid in self._all_nodes:
            if nid in completed:
                continue
            deps = self._deps.get(nid, set())
            if deps <= completed:  # all deps are completed
                ready.append(nid)
        return ready

    def get_blocked_by(self, node_id: str) -> List[str]:
        """Return the list of unmet dependencies for ``node_id``."""
        return sorted(self._deps.get(node_id, set()))

    def dependency_depth(self, node_id: str) -> int:
        """Compute the longest dependency chain length ending at ``node_id``.

        Blueprint §34: This is distinct from hierarchy_depth.
        """
        memo: Dict[str, int] = {}
        return self._dep_depth_recursive(node_id, memo, set())

    def _dep_depth_recursive(
        self, node_id: str, memo: Dict[str, int], visiting: Set[str]
    ) -> int:
        if node_id in memo:
            return memo[node_id]
        if node_id in visiting:
            return 0  # cycle guard (should not happen after add_dependency check)
        visiting.add(node_id)
        deps = self._deps.get(node_id, set())
        if not deps:
            memo[node_id] = 0
        else:
            memo[node_id] = 1 + max(
                self._dep_depth_recursive(d, memo, visiting) for d in deps
            )
        visiting.discard(node_id)
        return memo[node_id]

    # ── Topological Sort ─────────────────────────────────────────────────

    def topological_sort(self) -> List[str]:
        """Return all nodes in valid build order (dependencies before dependents).

        Uses Kahn's algorithm.  Raises CycleError if the graph has cycles
        (should not happen if add_dependency checks are working).
        """
        in_degree: Dict[str, int] = {nid: 0 for nid in self._all_nodes}
        for nid, deps in self._deps.items():
            for dep in deps:
                # dep must be built before nid, so in_degree of nid increases
                # (wait, we want topo order where deps come first)
                pass
        # Recompute: in_degree counts how many nodes must come before this one
        in_degree = {nid: 0 for nid in self._all_nodes}
        for nid in self._all_nodes:
            for dep in self._deps.get(nid, set()):
                # nid depends on dep → dep blocks nid → increment nid's in-degree
                in_degree[nid] = in_degree.get(nid, 0) + 1

        queue = deque(nid for nid, deg in in_degree.items() if deg == 0)
        result: List[str] = []

        while queue:
            nid = queue.popleft()
            result.append(nid)
            # For each node that depends on nid, decrement its in-degree
            for dependent in self._rdeps.get(nid, set()):
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)

        if len(result) != len(self._all_nodes):
            # Some nodes have unresolved dependencies — cycle exists
            remaining = self._all_nodes - set(result)
            raise CycleError(sorted(remaining))

        return result

    # ── Cycle Detection ──────────────────────────────────────────────────

    def detect_cycles(self) -> List[List[str]]:
        """Find all cycles in the graph.

        Returns a list of cycles, each cycle as a list of node IDs.
        Empty list = acyclic (valid DAG).
        """
        try:
            self.topological_sort()
            return []
        except CycleError as e:
            # Return the problematic nodes (simplified — full cycle enumeration
            # is NP-hard; we return the set of nodes involved)
            return [e.cycle]

    def _find_path(self, start: str, target: str) -> Optional[List[str]]:
        """DFS to find a path from start to target.  Returns path or None."""
        visited: Set[str] = set()
        path: List[str] = []

        def dfs(current: str) -> bool:
            if current == target:
                path.append(current)
                return True
            if current in visited:
                return False
            visited.add(current)
            path.append(current)
            for dep in self._deps.get(current, set()):
                if dfs(dep):
                    return True
            path.pop()
            return False

        if dfs(start):
            return path
        return None

    # ── Debugging ────────────────────────────────────────────────────────

    def summary(self) -> Dict[str, int]:
        """Quick stats for debugging."""
        total_edges = sum(len(deps) for deps in self._deps.values())
        return {
            "nodes": len(self._all_nodes),
            "edges": total_edges,
            "max_dependency_depth": max(
                (self.dependency_depth(nid) for nid in self._all_nodes),
                default=0,
            ),
        }
