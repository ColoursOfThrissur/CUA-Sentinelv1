"""Real-Model Transform Audit — Pre-Phase 4 Validation.

Runs actual models through the shadow transform pipeline and produces
comparison reports to classify mismatches before executor migration.

Usage:
    python -m audit_transforms [model_name]
    python -m audit_transforms --all
"""

import sys
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from pathlib import Path

# Handle both package and standalone imports
try:
    from .transforms import (
        LocalTransform,
        WorldMatrix,
        NodeTransformState,
        compare_positions,
        compare_rotations_matrix,
    )
    from .stages.stage4_resolver import (
        TransformComparison,
        compare_transform_systems,
        log_transform_comparison,
    )
except ImportError:
    from transforms import (
        LocalTransform,
        WorldMatrix,
        NodeTransformState,
        compare_positions,
        compare_rotations_matrix,
    )
    # For standalone, we don't need stage4_resolver imports
    TransformComparison = None
    compare_transform_systems = None
    log_transform_comparison = None

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Audit Result Types
# ---------------------------------------------------------------------------

@dataclass
class NodeAuditResult:
    """Audit result for a single node."""
    node_id: str
    label: str
    depth: int
    parent_id: Optional[str] = None
    socket_type: Optional[str] = None
    
    # Transforms
    local_position: List[float] = field(default_factory=lambda: [0, 0, 0])
    local_rotation: List[float] = field(default_factory=lambda: [0, 0, 0])
    legacy_world_position: List[float] = field(default_factory=lambda: [0, 0, 0])
    legacy_world_rotation: List[float] = field(default_factory=lambda: [0, 0, 0])
    new_world_position: List[float] = field(default_factory=lambda: [0, 0, 0])
    new_world_rotation: List[float] = field(default_factory=lambda: [0, 0, 0])
    
    # Deltas
    position_delta: float = 0.0
    rotation_delta: float = 0.0
    status: str = "PENDING"  # MATCH, DIFFER, ERROR
    
    # Diagnosis
    diagnosis: str = ""


@dataclass
class ModelAuditResult:
    """Audit result for an entire model."""
    model_name: str
    total_nodes: int = 0
    match_count: int = 0
    differ_count: int = 0
    error_count: int = 0
    
    nodes: List[NodeAuditResult] = field(default_factory=list)
    mismatches: List[NodeAuditResult] = field(default_factory=list)
    
    # Pattern analysis
    pattern: str = ""  # e.g., "depth_cascade", "rotation_only", "socket_only"
    root_cause_hypothesis: str = ""


# ---------------------------------------------------------------------------
# Pattern Analysis
# ---------------------------------------------------------------------------

def analyze_mismatch_pattern(mismatches: List[NodeAuditResult]) -> tuple[str, str]:
    """Analyze mismatch pattern to suggest root cause.
    
    Returns:
        (pattern_name, hypothesis)
    """
    if not mismatches:
        return "none", "All nodes match"
    
    # Check for rotation-only mismatches (high priority - specific pattern)
    rotation_only = all(m.position_delta < 0.001 and m.rotation_delta > 0.1 for m in mismatches)
    if rotation_only:
        return "rotation_only", "Position matches but rotation differs. Check rotation conventions or socket orientation."
    
    # Check for position-only mismatches
    position_only = all(m.position_delta > 0.001 and m.rotation_delta < 0.1 for m in mismatches)
    if position_only:
        return "position_only", "Rotation matches but position differs. Check translation or reference frame."
    
    # Check for socket-specific mismatches
    socket_mismatches = [m for m in mismatches if m.socket_type and m.socket_type != "ROOT"]
    non_socket_mismatches = [m for m in mismatches if not m.socket_type or m.socket_type == "ROOT"]
    if socket_mismatches and not non_socket_mismatches:
        return "socket_only", "Only socket attachments mismatch. Transform engine OK, check Stage 4 socket conversion."
    
    # Check for uniform offset (all nodes differ by same amount)
    if len(mismatches) > 1:
        pos_deltas = [m.position_delta for m in mismatches]
        if max(pos_deltas) - min(pos_deltas) < 0.01:
            return "uniform_offset", "All nodes differ by same amount. Check root/frame conventions."
    
    # Check for depth cascade (parent matches, children diverge increasingly)
    # This is checked last as it's the most general pattern
    depths = sorted(set(m.depth for m in mismatches))
    if len(depths) > 1:
        min_depth = min(depths)
        # Check if position delta strictly increases with depth
        by_depth = {}
        for m in mismatches:
            if m.depth not in by_depth:
                by_depth[m.depth] = []
            by_depth[m.depth].append(m.position_delta)
        
        avg_by_depth = {d: sum(deltas)/len(deltas) for d, deltas in by_depth.items()}
        if len(avg_by_depth) >= 2:
            sorted_depths = sorted(avg_by_depth.keys())
            # Require strictly increasing deltas (not just non-decreasing)
            if all(avg_by_depth[sorted_depths[i]] < avg_by_depth[sorted_depths[i+1]] - 0.01
                   for i in range(len(sorted_depths)-1)):
                return "depth_cascade", f"Error compounds from depth {min_depth}. Check local transform at that level."
    
    return "mixed", "Multiple mismatch types. Manual investigation needed."


# ---------------------------------------------------------------------------
# Report Generation
# ---------------------------------------------------------------------------

def generate_audit_report(result: ModelAuditResult) -> str:
    """Generate human-readable audit report."""
    lines = []
    lines.append("=" * 60)
    lines.append(f"MODEL: {result.model_name}")
    lines.append("=" * 60)
    lines.append("")
    
    # Summary
    lines.append("SUMMARY")
    lines.append("-" * 40)
    lines.append(f"  Total nodes:  {result.total_nodes}")
    lines.append(f"  MATCH:        {result.match_count}")
    lines.append(f"  DIFFER:       {result.differ_count}")
    lines.append(f"  ERROR:        {result.error_count}")
    lines.append("")
    
    if result.differ_count == 0 and result.error_count == 0:
        lines.append("✅ ALL NODES MATCH")
        lines.append("")
        return "\n".join(lines)
    
    # Pattern analysis
    lines.append("PATTERN ANALYSIS")
    lines.append("-" * 40)
    lines.append(f"  Pattern:     {result.pattern}")
    lines.append(f"  Hypothesis:  {result.root_cause_hypothesis}")
    lines.append("")
    
    # Mismatches detail
    if result.mismatches:
        lines.append("MISMATCHES")
        lines.append("-" * 40)
        
        for m in sorted(result.mismatches, key=lambda x: x.depth):
            lines.append("")
            lines.append(f"  {m.label} ({m.node_id})")
            lines.append(f"    depth:          {m.depth}")
            lines.append(f"    parent:         {m.parent_id or 'ROOT'}")
            lines.append(f"    socket:         {m.socket_type or 'N/A'}")
            lines.append(f"    position delta: {m.position_delta:.4f} m")
            lines.append(f"    rotation delta: {m.rotation_delta:.1f}°")
            lines.append(f"    status:         {m.status}")
            
            if m.diagnosis:
                lines.append(f"    diagnosis:      {m.diagnosis}")
            
            # Show actual values for debugging
            lines.append(f"    legacy pos:     [{', '.join(f'{v:.4f}' for v in m.legacy_world_position)}]")
            lines.append(f"    new pos:        [{', '.join(f'{v:.4f}' for v in m.new_world_position)}]")
    
    lines.append("")
    lines.append("=" * 60)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Audit Runner
# ---------------------------------------------------------------------------

def audit_model_transforms(
    nodes: List[Any],
    legacy_world_transforms: Dict[str, Dict[str, List[float]]],
    model_name: str = "unnamed",
) -> ModelAuditResult:
    """Run transform audit on a model.
    
    Args:
        nodes: List of manifest nodes with transform_state populated
        legacy_world_transforms: Dict of node_id -> {"position": [...], "rotation": [...]}
        model_name: Name for the report
        
    Returns:
        ModelAuditResult with full analysis
    """
    result = ModelAuditResult(model_name=model_name)
    result.total_nodes = len(nodes)
    
    for node in nodes:
        node_id = node.node_id
        label = getattr(node, 'label', node_id)
        
        # Get depth from hierarchy
        depth = _compute_depth(node, nodes)
        
        # Get parent info
        parent_id = None
        socket_type = None
        if hasattr(node, 'attachment') and node.attachment:
            parent_id = node.attachment.parent_id
            socket_type = node.attachment.socket_type.value if node.attachment.socket_type else None
        
        audit = NodeAuditResult(
            node_id=node_id,
            label=label,
            depth=depth,
            parent_id=parent_id,
            socket_type=socket_type,
        )
        
        # Get local transform
        if hasattr(node, 'transform_state') and node.transform_state:
            local = node.transform_state.local_transform
            audit.local_position = list(local.position)
            audit.local_rotation = list(local.rotation)
            
            # Get new world transform
            world = node.transform_state.world_matrix
            if world:
                audit.new_world_position = list(world.position)
                audit.new_world_rotation = list(world.rotation)
        
        # Get legacy world transform
        if node_id in legacy_world_transforms:
            legacy = legacy_world_transforms[node_id]
            audit.legacy_world_position = legacy.get("position", [0, 0, 0])
            audit.legacy_world_rotation = legacy.get("rotation", [0, 0, 0])
        
        # Compare
        pos_delta, pos_match = compare_positions(
            audit.legacy_world_position,
            audit.new_world_position,
            tolerance=0.001,
        )
        rot_delta, rot_match = compare_rotations_matrix(
            audit.legacy_world_rotation,
            audit.new_world_rotation,
            tolerance_deg=0.5,
        )
        
        audit.position_delta = pos_delta
        audit.rotation_delta = rot_delta
        
        if pos_match and rot_match:
            audit.status = "MATCH"
            result.match_count += 1
        else:
            audit.status = "DIFFER"
            result.differ_count += 1
            result.mismatches.append(audit)
            
            # Add diagnosis
            if not pos_match and rot_match:
                audit.diagnosis = "Position differs, rotation OK"
            elif pos_match and not rot_match:
                audit.diagnosis = "Rotation differs, position OK"
            else:
                audit.diagnosis = "Both position and rotation differ"
        
        result.nodes.append(audit)
    
    # Analyze pattern
    result.pattern, result.root_cause_hypothesis = analyze_mismatch_pattern(result.mismatches)
    
    return result


def _compute_depth(node: Any, all_nodes: List[Any]) -> int:
    """Compute depth of node in hierarchy."""
    node_map = {n.node_id: n for n in all_nodes}
    depth = 0
    current = node
    
    while hasattr(current, 'attachment') and current.attachment and current.attachment.parent_id:
        parent_id = current.attachment.parent_id
        if parent_id not in node_map:
            break
        current = node_map[parent_id]
        depth += 1
        if depth > 100:  # Safety limit
            break
    
    return depth


# ---------------------------------------------------------------------------
# Provenance Record
# ---------------------------------------------------------------------------

@dataclass
class TransformProvenance:
    """Final-transform provenance record for debugging.
    
    Answers: "Why is this object here?"
    """
    node_id: str
    parent_id: Optional[str]
    depth: int
    
    # Attachment info
    attachment_source: str  # e.g., "SOCKET_ATTACHMENT", "ROOT", "RELATIVE_TO"
    resolver_type: str      # e.g., "deterministic_socket_solver"
    socket_info: Optional[str]  # e.g., "TOP_CENTER → BOTTOM_CENTER"
    
    # Transforms
    local_transform: Dict[str, List[float]] = field(default_factory=dict)
    world_matrix: List[List[float]] = field(default_factory=list)
    
    # Revisions
    revision: int = 0
    parent_revision: int = -1
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "parent_id": self.parent_id,
            "depth": self.depth,
            "attachment_source": self.attachment_source,
            "resolver_type": self.resolver_type,
            "socket_info": self.socket_info,
            "local_transform": self.local_transform,
            "world_matrix": self.world_matrix,
            "revision": self.revision,
            "parent_revision": self.parent_revision,
        }
    
    def format_report(self) -> str:
        """Format as human-readable report."""
        lines = [
            f"{self.node_id}",
            "",
            f"Parent:",
            f"    {self.parent_id or 'ROOT'}",
            "",
            f"Depth:",
            f"    {self.depth}",
            "",
            f"Attachment:",
            f"    {self.socket_info or self.attachment_source}",
            "",
            f"Local:",
            f"    position = {self.local_transform.get('position', [])}",
            f"    rotation = {self.local_transform.get('rotation', [])}",
            f"    scale = {self.local_transform.get('scale', [1,1,1])}",
            "",
            f"World:",
            f"    matrix = [...]",  # Too verbose to show full matrix
            "",
            f"Revision:",
            f"    {self.revision}",
            "",
            f"Parent revision:",
            f"    {self.parent_revision}",
            "",
            f"Source:",
            f"    {self.resolver_type}",
        ]
        return "\n".join(lines)


def create_provenance(node: Any, depth: int) -> TransformProvenance:
    """Create provenance record for a node."""
    # Attachment info
    attachment_source = "ROOT"
    resolver_type = "identity"
    socket_info = None
    parent_id = None
    
    if hasattr(node, 'attachment') and node.attachment:
        att = node.attachment
        parent_id = att.parent_id
        attachment_source = att.socket_type.value if att.socket_type else "UNKNOWN"
        resolver_type = getattr(att, 'resolution_method', 'unknown')
        
        if hasattr(att, 'parent_socket') and hasattr(att, 'child_socket'):
            socket_info = f"{att.parent_socket} → {att.child_socket}"
    
    # Transform info
    local_dict = {}
    world_matrix = []
    revision = 0
    parent_revision = -1
    
    if hasattr(node, 'transform_state') and node.transform_state:
        ts = node.transform_state
        local_dict = {
            "position": list(ts.local_transform.position),
            "rotation": list(ts.local_transform.rotation),
            "scale": list(ts.local_transform.scale),
        }
        if ts.world_matrix:
            world_matrix = ts.world_matrix.matrix
        revision = ts.revision
        parent_revision = ts.parent_revision
    
    return TransformProvenance(
        node_id=node.node_id,
        parent_id=parent_id,
        depth=depth,
        attachment_source=attachment_source,
        resolver_type=resolver_type,
        socket_info=socket_info,
        local_transform=local_dict,
        world_matrix=world_matrix,
        revision=revision,
        parent_revision=parent_revision,
    )
