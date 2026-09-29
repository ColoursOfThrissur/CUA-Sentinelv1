"""Persistent Build Manifest — the v5 pipeline's working memory.

Stores the complete state of a progressive assembly build: hierarchy, node states,
stage outputs, verification results, and checkpoint history.  Persisted to JSON in
``data/builds/{model_id}/manifest.json`` so builds survive backend restarts.

The manifest is the single source of truth for what has been built, what failed,
and what remains.  Every mutation goes through ``transition()`` which enforces
valid state machine edges.

Blueprint references: §6 (manifest), §7 (temp vs permanent), §8 (node states),
§17 (degraded completion), §19 (checkpointing).
"""

from __future__ import annotations

import copy
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from .node_types import NodeKind, NodeImportance

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data directory — matches existing data/specs/ pattern
# ---------------------------------------------------------------------------
_DATA_ROOT = Path(__file__).resolve().parent.parent.parent.parent / "data" / "builds"


def _builds_dir() -> Path:
    """Return (and lazily create) the root builds directory."""
    _DATA_ROOT.mkdir(parents=True, exist_ok=True)
    return _DATA_ROOT


# ---------------------------------------------------------------------------
# Node State Machine
# ---------------------------------------------------------------------------

class NodeState(str, Enum):
    """Lifecycle state of a single hierarchy node.  Blueprint §8."""
    PLANNED = "planned"
    DECOMPOSING = "decomposing"
    READY = "ready"
    BUILDING = "building"
    VERIFYING = "verifying"
    VERIFIED = "verified"
    MERGING = "merging"
    FAILED = "failed"
    RETRYING = "retrying"
    SKIPPED = "skipped"
    STALE = "stale"


# Valid state transitions.  Any edge not listed here is illegal.
_VALID_TRANSITIONS: Dict[NodeState, Set[NodeState]] = {
    NodeState.PLANNED:     {NodeState.DECOMPOSING, NodeState.READY},
    NodeState.DECOMPOSING: {NodeState.READY, NodeState.FAILED},
    NodeState.READY:       {NodeState.BUILDING, NodeState.MERGING},
    NodeState.BUILDING:    {NodeState.VERIFYING, NodeState.FAILED, NodeState.MERGING},
    NodeState.VERIFYING:   {NodeState.VERIFIED, NodeState.FAILED},
    NodeState.VERIFIED:    {NodeState.MERGING, NodeState.STALE},
    NodeState.MERGING:     {NodeState.VERIFIED, NodeState.FAILED},
    NodeState.FAILED:      {NodeState.RETRYING, NodeState.SKIPPED},
    NodeState.RETRYING:    {NodeState.READY, NodeState.SKIPPED},
    NodeState.SKIPPED:     set(),  # terminal
    NodeState.STALE:       {NodeState.READY},
}


class CompletionStatus(str, Enum):
    """Overall build outcome.  Blueprint §17."""
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    COMPLETED_DEGRADED = "completed_degraded"
    FAILED = "failed"


# ---------------------------------------------------------------------------
# ManifestNode — one entry in the hierarchy
# ---------------------------------------------------------------------------

@dataclass
class ManifestNode:
    """A single node in the build manifest.

    Carries everything needed to build, verify, retry, and merge this node,
    plus checkpoint state for crash recovery.
    """
    # Identity
    node_id: str
    label: str
    kind: NodeKind = NodeKind.PART

    # State machine
    state: NodeState = NodeState.PLANNED
    importance: NodeImportance = NodeImportance.REQUIRED

    # Hierarchy (containment tree, not dependency)
    parent_id: Optional[str] = None
    children_ids: List[str] = field(default_factory=list)

    # Dependency DAG (separate from containment)
    dependency_ids: List[str] = field(default_factory=list)

    # Instance support (§14)
    instance_of: Optional[str] = None  # definition node_id when kind == INSTANCE

    # Retry tracking
    retry_count: int = 0
    max_retries: int = 3
    error_message: Optional[str] = None

    # Hierarchy metadata
    hierarchy_depth: int = 0

    # Stage outputs (keyed by stage name, e.g. "stage0", "stage2", "stage3")
    stage_outputs: Dict[str, Any] = field(default_factory=dict)

    # Verification
    verification_result: Optional[Dict[str, Any]] = None

    # Blender objects owned by this node's current generation
    blender_objects: List[str] = field(default_factory=list)
    generation_id: Optional[str] = None

    # Assembly contract — public interface for parent consumption (§13)
    public_sockets: List[Dict[str, Any]] = field(default_factory=list)
    bounding_info: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for JSON persistence."""
        return {
            "node_id": self.node_id,
            "label": self.label,
            "kind": self.kind.value,
            "state": self.state.value,
            "importance": self.importance.value,
            "parent_id": self.parent_id,
            "children_ids": list(self.children_ids),
            "dependency_ids": list(self.dependency_ids),
            "instance_of": self.instance_of,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "error_message": self.error_message,
            "hierarchy_depth": self.hierarchy_depth,
            "stage_outputs": self.stage_outputs,
            "verification_result": self.verification_result,
            "blender_objects": list(self.blender_objects),
            "generation_id": self.generation_id,
            "public_sockets": self.public_sockets,
            "bounding_info": self.bounding_info,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> ManifestNode:
        """Deserialize from JSON."""
        return cls(
            node_id=d["node_id"],
            label=d["label"],
            kind=NodeKind(d.get("kind", "part")),
            state=NodeState(d.get("state", "planned")),
            importance=NodeImportance(d.get("importance", "required")),
            parent_id=d.get("parent_id"),
            children_ids=list(d.get("children_ids", [])),
            dependency_ids=list(d.get("dependency_ids", [])),
            instance_of=d.get("instance_of"),
            retry_count=d.get("retry_count", 0),
            max_retries=d.get("max_retries", 3),
            error_message=d.get("error_message"),
            hierarchy_depth=d.get("hierarchy_depth", 0),
            stage_outputs=d.get("stage_outputs", {}),
            verification_result=d.get("verification_result"),
            blender_objects=list(d.get("blender_objects", [])),
            generation_id=d.get("generation_id"),
            public_sockets=d.get("public_sockets", []),
            bounding_info=d.get("bounding_info"),
        )


# ---------------------------------------------------------------------------
# BuildManifest — the complete build state
# ---------------------------------------------------------------------------

class BuildManifest:
    """Persistent build state for one progressive assembly build.

    This is the v5 pipeline's single source of truth.  It is serialized to
    ``data/builds/{model_id}/manifest.json`` at every checkpoint.

    All node mutations go through ``transition()`` which enforces the state
    machine and logs the change.
    """

    def __init__(
        self,
        model_id: str,
        description: str = "",
        root_node_id: Optional[str] = None,
    ):
        self.model_id: str = model_id
        self.description: str = description
        self.root_node_id: str = root_node_id or ""
        self.nodes: Dict[str, ManifestNode] = {}
        self.completion_status: CompletionStatus = CompletionStatus.IN_PROGRESS
        self.created_at: str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self.updated_at: str = self.created_at
        self.checkpoints: List[Dict[str, Any]] = []
        self.stage0_output: Optional[Dict[str, Any]] = None  # shared model understanding

    # ── Factory ──────────────────────────────────────────────────────────

    @classmethod
    def create(cls, description: str, model_id: Optional[str] = None) -> BuildManifest:
        """Create a new manifest with a root MODEL node."""
        mid = model_id or uuid.uuid4().hex[:12]
        manifest = cls(model_id=mid, description=description)

        root_id = f"{mid}_root"
        root = ManifestNode(
            node_id=root_id,
            label=description[:60] if description else "model",
            kind=NodeKind.MODEL,
            hierarchy_depth=0,
        )
        manifest.nodes[root_id] = root
        manifest.root_node_id = root_id

        return manifest

    # ── Node access ──────────────────────────────────────────────────────

    def get_node(self, node_id: str) -> ManifestNode:
        """Get a node or raise KeyError."""
        if node_id not in self.nodes:
            raise KeyError(f"Node '{node_id}' not in manifest '{self.model_id}'")
        return self.nodes[node_id]

    def get_root(self) -> ManifestNode:
        """Return the root MODEL node."""
        return self.get_node(self.root_node_id)

    def add_node(self, node: ManifestNode) -> None:
        """Add a node to the manifest.  Raises if duplicate."""
        if node.node_id in self.nodes:
            raise ValueError(f"Duplicate node_id: {node.node_id}")
        self.nodes[node.node_id] = node
        self.updated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def remove_node(self, node_id: str) -> ManifestNode:
        """Remove a node.  Does NOT cascade to children — caller must handle that."""
        node = self.nodes.pop(node_id)
        # Remove from parent's children list
        if node.parent_id and node.parent_id in self.nodes:
            parent = self.nodes[node.parent_id]
            if node_id in parent.children_ids:
                parent.children_ids.remove(node_id)
        self.updated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        return node

    # ── State machine ────────────────────────────────────────────────────

    def transition(self, node_id: str, new_state: NodeState, error: Optional[str] = None) -> None:
        """Move a node to a new state.  Validates the transition is legal.

        Raises ValueError if the transition is not in _VALID_TRANSITIONS.
        """
        node = self.get_node(node_id)
        old_state = node.state
        allowed = _VALID_TRANSITIONS.get(old_state, set())

        if new_state not in allowed:
            raise ValueError(
                f"Illegal state transition for '{node.label}' ({node_id}): "
                f"{old_state.value} → {new_state.value}.  "
                f"Allowed: {sorted(s.value for s in allowed)}"
            )

        node.state = new_state
        if error is not None:
            node.error_message = error
        if new_state == NodeState.RETRYING:
            node.retry_count += 1

        self.updated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        logger.debug(
            f"[{self.model_id}] {node.label}: {old_state.value} → {new_state.value}"
            + (f" (error: {error})" if error else "")
        )

    # ── Queries ──────────────────────────────────────────────────────────

    def nodes_in_state(self, state: NodeState) -> List[ManifestNode]:
        """Return all nodes currently in the given state."""
        return [n for n in self.nodes.values() if n.state == state]

    def get_children(self, node_id: str) -> List[ManifestNode]:
        """Return the immediate children of a node."""
        parent = self.get_node(node_id)
        return [self.nodes[cid] for cid in parent.children_ids if cid in self.nodes]

    def get_leaves(self) -> List[ManifestNode]:
        """Return all leaf nodes (no children)."""
        return [n for n in self.nodes.values() if not n.children_ids]

    def all_verified(self, node_ids: List[str]) -> bool:
        """Check if all given nodes are VERIFIED."""
        return all(
            self.nodes[nid].state == NodeState.VERIFIED
            for nid in node_ids
            if nid in self.nodes
        )

    def is_root_resolved(self) -> bool:
        """True if the root node is VERIFIED — build is complete."""
        root = self.get_root()
        return root.state == NodeState.VERIFIED

    def compute_completion_status(self) -> CompletionStatus:
        """Evaluate overall build status from node states.

        Blueprint §17 logic:
        - All required VERIFIED → SUCCESS
        - All required VERIFIED but some optional SKIPPED → COMPLETED_DEGRADED
        - Any required SKIPPED or FAILED → FAILED
        - Otherwise → IN_PROGRESS
        """
        required_nodes = [
            n for n in self.nodes.values()
            if n.importance == NodeImportance.REQUIRED and n.kind != NodeKind.MODEL
        ]
        optional_nodes = [
            n for n in self.nodes.values()
            if n.importance in (NodeImportance.OPTIONAL, NodeImportance.DECORATIVE)
        ]

        if not required_nodes:
            # Only root exists — check root state
            root = self.get_root()
            if root.state == NodeState.VERIFIED:
                return CompletionStatus.SUCCESS
            if root.state in (NodeState.FAILED, NodeState.SKIPPED):
                return CompletionStatus.FAILED
            return CompletionStatus.IN_PROGRESS

        required_failed = any(n.state in (NodeState.FAILED, NodeState.SKIPPED) for n in required_nodes)
        required_all_done = all(n.state == NodeState.VERIFIED for n in required_nodes)
        optional_skipped = any(n.state == NodeState.SKIPPED for n in optional_nodes)

        if required_failed:
            return CompletionStatus.FAILED
        if required_all_done:
            if optional_skipped:
                return CompletionStatus.COMPLETED_DEGRADED
            return CompletionStatus.SUCCESS
        return CompletionStatus.IN_PROGRESS

    # ── Persistence ──────────────────────────────────────────────────────

    def _build_dir(self) -> Path:
        """Return (and lazily create) this build's directory."""
        d = _builds_dir() / self.model_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def to_dict(self) -> Dict[str, Any]:
        """Full serialization for JSON persistence."""
        return {
            "model_id": self.model_id,
            "description": self.description,
            "root_node_id": self.root_node_id,
            "completion_status": self.completion_status.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "stage0_output": self.stage0_output,
            "nodes": {nid: node.to_dict() for nid, node in self.nodes.items()},
            "checkpoints": self.checkpoints,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> BuildManifest:
        """Reconstruct from parsed JSON dictionary."""
        m = cls(
            model_id=d["model_id"],
            description=d.get("description", ""),
            root_node_id=d.get("root_node_id", ""),
        )
        m.completion_status = CompletionStatus(d.get("completion_status", "in_progress"))
        m.created_at = d.get("created_at", "")
        m.updated_at = d.get("updated_at", "")
        m.stage0_output = d.get("stage0_output")
        m.checkpoints = d.get("checkpoints", [])
        for nid, ndict in d.get("nodes", {}).items():
            m.nodes[nid] = ManifestNode.from_dict(ndict)
        return m

    def save(self, path: Optional[Path] = None) -> Path:
        """Persist manifest to JSON.  Uses atomic write (tmp + rename) for safety.

        Returns the path written to.
        """
        target = path or (self._build_dir() / "manifest.json")
        tmp = target.with_suffix(".tmp")
        data = json.dumps(self.to_dict(), indent=2, ensure_ascii=False)
        tmp.write_text(data, encoding="utf-8")
        tmp.replace(target)  # atomic on same filesystem
        logger.debug(f"Manifest saved: {target}")
        return target

    @classmethod
    def load(cls, path: Path) -> BuildManifest:
        """Load manifest from a JSON file."""
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls.from_dict(data)

    @classmethod
    def load_by_model_id(cls, model_id: str) -> Optional[BuildManifest]:
        """Load manifest by model_id from the standard location, or None if missing."""
        p = _builds_dir() / model_id / "manifest.json"
        if not p.exists():
            return None
        try:
            return cls.load(p)
        except Exception as e:
            logger.warning(f"Failed to load manifest for {model_id}: {e}")
            return None

    # ── Checkpointing ────────────────────────────────────────────────────

    def checkpoint(self, label: Optional[str] = None) -> None:
        """Save a checkpoint snapshot and persist to disk.

        Blueprint §19: Checkpointed at every verified leaf, sub-assembly,
        assembly, and successful merge.  The checkpoint stores the full
        manifest state so we can resume from it after a crash.
        """
        snap = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "label": label or f"checkpoint_{len(self.checkpoints)}",
            "verified_nodes": [
                n.node_id for n in self.nodes.values()
                if n.state == NodeState.VERIFIED
            ],
            "failed_nodes": [
                n.node_id for n in self.nodes.values()
                if n.state in (NodeState.FAILED, NodeState.SKIPPED)
            ],
        }
        self.checkpoints.append(snap)
        self.save()
        logger.info(
            f"[{self.model_id}] Checkpoint '{snap['label']}': "
            f"{len(snap['verified_nodes'])} verified, "
            f"{len(snap['failed_nodes'])} failed/skipped"
        )

    def delete_build_state(self) -> None:
        """Delete temporary build state after successful completion.  Blueprint §7."""
        import shutil
        build_dir = self._build_dir()
        if build_dir.exists():
            shutil.rmtree(build_dir, ignore_errors=True)
            logger.info(f"[{self.model_id}] Temporary build state deleted")
