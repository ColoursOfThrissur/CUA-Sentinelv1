"""Dirty Propagation — marks dependent nodes and parent assemblies STALE when a node changes.

Blueprint references: §20 (Dirty Propagation).
If a previously verified component changes:
- Dependents in DependencyDAG become STALE
- Ancestors in ContainmentTree become STALE
- Unrelated branches remain CLEAN
"""

from __future__ import annotations

import logging
from typing import List, Set

from .manifest import BuildManifest, NodeState
from .dependency_graph import DependencyDAG

logger = logging.getLogger(__name__)


class DirtyPropagator:
    """Propagates STALE state to all upstream dependents and parent assemblies."""

    @classmethod
    def propagate(
        cls,
        changed_node_id: str,
        manifest: BuildManifest,
        dag: DependencyDAG,
    ) -> List[str]:
        """Mark changed_node_id and all its dependents / parent assemblies as STALE.

        Returns:
            List of node IDs that were marked STALE.
        """
        stale_nodes: Set[str] = set()

        # 1. Collect all downstream dependents from DAG
        dependents = dag.get_dependents(changed_node_id)
        queue = list(dependents)

        while queue:
            nid = queue.pop(0)
            if nid not in stale_nodes:
                stale_nodes.add(nid)
                for dep in dag.get_dependents(nid):
                    if dep not in stale_nodes:
                        queue.append(dep)

        # 2. Collect all ancestor assemblies from containment tree
        curr_id = changed_node_id
        while curr_id and curr_id in manifest.nodes:
            parent_id = manifest.nodes[curr_id].parent_id
            if parent_id and parent_id in manifest.nodes:
                stale_nodes.add(parent_id)
                curr_id = parent_id
            else:
                break

        # 3. Transition verified or building nodes to STALE (if not already failed or skipped)
        transitioned: List[str] = []
        for nid in sorted(stale_nodes):
            if nid in manifest.nodes:
                node = manifest.nodes[nid]
                if node.state in (NodeState.VERIFIED, NodeState.BUILDING, NodeState.VERIFYING):
                    manifest.nodes[nid].state = NodeState.STALE
                    transitioned.append(nid)
                    logger.debug(f"DirtyPropagator marked '{nid}' STALE due to change in '{changed_node_id}'")

        return transitioned
