"""Build Frontier — tracks currently actionable nodes in the progressive build.

A node enters the frontier only when:
  1. The node is in READY state
  2. All required dependencies (in DependencyDAG) are in VERIFIED state
  3. Parent context is valid (parent node exists and is not FAILED/SKIPPED)

Blueprint references: §9 (Build Frontier).
"""

from __future__ import annotations

import logging
from typing import List, Optional, Set

from .manifest import BuildManifest, NodeState
from .dependency_graph import DependencyDAG

logger = logging.getLogger(__name__)


class BuildFrontier:
    """Maintains and updates the set of currently actionable nodes."""

    def __init__(self):
        self._actionable: Set[str] = set()

    @property
    def actionable_nodes(self) -> List[str]:
        """Return the sorted list of current frontier node IDs."""
        return sorted(self._actionable)

    def refresh(self, manifest: BuildManifest, dag: DependencyDAG) -> List[str]:
        """Recompute the frontier from current manifest state and dependency graph.

        Returns:
            List of node IDs currently actionable.
        """
        # Collect verified node IDs
        verified_ids = {
            nid for nid, node in manifest.nodes.items()
            if node.state == NodeState.VERIFIED
        }

        # Query DAG for nodes whose dependencies are satisfied
        ready_by_dag = set(dag.get_ready_nodes(completed=verified_ids))

        new_frontier: Set[str] = set()

        for nid in ready_by_dag:
            if nid not in manifest.nodes:
                continue
            node = manifest.nodes[nid]

            # Only READY nodes can enter the actionable frontier
            if node.state != NodeState.READY:
                continue

            # Check parent context: if parent exists, it must not be FAILED or SKIPPED
            if node.parent_id and node.parent_id in manifest.nodes:
                parent = manifest.nodes[node.parent_id]
                if parent.state in (NodeState.FAILED, NodeState.SKIPPED):
                    continue

            new_frontier.add(nid)

        self._actionable = new_frontier
        return sorted(self._actionable)

    def remove(self, node_id: str) -> None:
        """Remove a node from the frontier once it is picked for execution."""
        self._actionable.discard(node_id)

    def is_empty(self) -> bool:
        """Check if there are no actionable nodes."""
        return len(self._actionable) == 0
