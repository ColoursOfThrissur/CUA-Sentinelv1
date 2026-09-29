"""Smart Scheduler — prioritizes and selects the next node from the build frontier.

Blueprint references: §10 (Smart Scheduler), §33 (Jigsaw Principle).
Optimizes for: maximum verified structural progress per build action.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from .manifest import BuildManifest, NodeState
from .node_types import NodeKind, NodeImportance
from .dependency_graph import DependencyDAG

logger = logging.getLogger(__name__)


class SmartScheduler:
    """Scores candidate nodes on the frontier and picks the highest-priority piece."""

    def score_node(
        self,
        node_id: str,
        manifest: BuildManifest,
        dag: DependencyDAG,
    ) -> float:
        """Compute an execution priority score for a frontier node.

        Higher score = build sooner.
        Factors:
          + Blocking count (how many other nodes depend on this node) * 3.0
          + Structural foundation (leaf PART nodes or definitions) * 2.0
          + Required vs Optional (+2.0 for REQUIRED)
          - Retry penalty (-1.0 per prior attempt to avoid starvation/thrashing)
          + Sibling completion bonus (if siblings are already verified, close out assembly)
        """
        if node_id not in manifest.nodes:
            return -1000.0

        node = manifest.nodes[node_id]
        score = 0.0

        # 1. How many nodes does this unblock?
        dependents = dag.get_dependents(node_id)
        score += len(dependents) * 3.0

        # 2. Importance
        if node.importance == NodeImportance.REQUIRED:
            score += 2.0
        elif node.importance == NodeImportance.DECORATIVE:
            score -= 1.0

        # 3. Structural role: shared definition or foundational part
        if node.kind == NodeKind.PART:
            score += 1.5
        elif node.kind == NodeKind.ASSEMBLY:
            score += 0.5

        # 4. Sibling progress: if other siblings under the same parent are verified,
        # prioritize completing the cluster so the parent can merge.
        if node.parent_id and node.parent_id in manifest.nodes:
            parent = manifest.nodes[node.parent_id]
            verified_siblings = 0
            for cid in parent.children_ids:
                if cid != node_id and cid in manifest.nodes:
                    if manifest.nodes[cid].state == NodeState.VERIFIED:
                        verified_siblings += 1
            score += verified_siblings * 1.5

        # 5. Penalize repeated failures (backoff)
        score -= node.retry_count * 1.0

        # 6. Deeper nodes (bottom-up jigsaw) slightly favored
        score += node.hierarchy_depth * 0.5

        return score

    def pick_next(
        self,
        frontier: List[str],
        manifest: BuildManifest,
        dag: DependencyDAG,
    ) -> Optional[str]:
        """Select the highest-priority node from the candidate frontier."""
        if not frontier:
            return None

        best_node: Optional[str] = None
        best_score = float("-inf")

        for nid in frontier:
            score = self.score_node(nid, manifest, dag)
            if score > best_score:
                best_score = score
                best_node = nid

        logger.debug(f"SmartScheduler selected '{best_node}' with score {best_score:.2f}")
        return best_node
