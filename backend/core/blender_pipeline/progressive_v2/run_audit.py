"""Real-Model Audit Runner — Pre-Phase 4 Validation.

Runs actual models through the shadow transform pipeline and produces
comparison reports in the format needed for mismatch classification.

Usage:
    python run_audit.py <model_name>
    python run_audit.py --all
    python run_audit.py --test-models
    
The --test-models flag runs the 5 validation models (A-E) defined in this file.
"""

import sys
import math
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from transforms import LocalTransform, WorldMatrix, NodeTransformState
from audit_transforms import (
    audit_model_transforms,
    generate_audit_report,
    create_provenance,
    TransformProvenance,
)

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Test Model Definitions (Models A-E)
# ---------------------------------------------------------------------------

@dataclass
class TestNode:
    """Simplified node for audit testing."""
    node_id: str
    label: str
    parent_id: Optional[str] = None
    socket_type: Optional[str] = None
    
    # Local transform (what Stage 4 would produce)
    local_position: List[float] = field(default_factory=lambda: [0, 0, 0])
    local_rotation: List[float] = field(default_factory=lambda: [0, 0, 0])  # radians
    
    # Simulated legacy world transform (what old executor produces)
    legacy_world_position: List[float] = field(default_factory=lambda: [0, 0, 0])
    legacy_world_rotation: List[float] = field(default_factory=lambda: [0, 0, 0])
    
    # Runtime state
    transform_state: Optional[NodeTransformState] = None
    attachment: Optional[Any] = None
    
    def __post_init__(self):
        # Create attachment mock if parent specified
        if self.parent_id:
            self.attachment = type('Attachment', (), {
                'parent_id': self.parent_id,
                'socket_type': type('SocketType', (), {'value': self.socket_type})() if self.socket_type else None,
                'resolution_method': 'test',
            })()


def build_test_hierarchy(nodes: List[TestNode]) -> List[TestNode]:
    """Build transform hierarchy and compute world matrices."""
    node_map = {n.node_id: n for n in nodes}
    
    # Initialize transform states
    for node in nodes:
        node.transform_state = NodeTransformState()
        node.transform_state.set_local_transform(LocalTransform(
            position=list(node.local_position),
            rotation=list(node.local_rotation),
        ))
    
    # Compute world matrices in dependency order
    computed = set()
    
    def compute_node(node: TestNode):
        if node.node_id in computed:
            return
        
        parent_world = None
        parent_rev = -1
        
        if node.parent_id and node.parent_id in node_map:
            parent = node_map[node.parent_id]
            if parent.node_id not in computed:
                compute_node(parent)
            parent_world = parent.transform_state.world_matrix
            parent_rev = parent.transform_state.revision
        
        node.transform_state.compute_world(parent_world, parent_rev)
        computed.add(node.node_id)
    
    for node in nodes:
        compute_node(node)
    
    return nodes


# ---------------------------------------------------------------------------
# Model A: Simple Baseline
# ---------------------------------------------------------------------------

def create_model_a() -> tuple[str, List[TestNode], Dict[str, Dict]]:
    """Model A — Simple baseline (Base → Turret → Cannon)."""
    nodes = [
        TestNode(
            node_id="base",
            label="Base",
            local_position=[0, 0, 0],
            local_rotation=[0, 0, 0],
            legacy_world_position=[0, 0, 0],
            legacy_world_rotation=[0, 0, 0],
        ),
        TestNode(
            node_id="turret",
            label="Turret",
            parent_id="base",
            socket_type="TOP_CENTER",
            local_position=[0, 0, 0.5],  # On top of base
            local_rotation=[0, 0, 0],
            legacy_world_position=[0, 0, 0.5],
            legacy_world_rotation=[0, 0, 0],
        ),
        TestNode(
            node_id="cannon",
            label="Cannon",
            parent_id="turret",
            socket_type="TOP_CENTER",
            local_position=[0, 0, 0.3],  # On top of turret
            local_rotation=[0, 0, 0],
            legacy_world_position=[0, 0, 0.8],
            legacy_world_rotation=[0, 0, 0],
        ),
    ]
    
    legacy = {
        "base": {"position": [0, 0, 0], "rotation": [0, 0, 0]},
        "turret": {"position": [0, 0, 0.5], "rotation": [0, 0, 0]},
        "cannon": {"position": [0, 0, 0.8], "rotation": [0, 0, 0]},
    }
    
    return "Model A: Simple Baseline", build_test_hierarchy(nodes), legacy


# ---------------------------------------------------------------------------
# Model B: Rotated Hierarchy
# ---------------------------------------------------------------------------

def create_model_b() -> tuple[str, List[TestNode], Dict[str, Dict]]:
    """Model B — Rotated hierarchy (rotation at every level)."""
    # Each level rotates 45° around Z
    r45 = math.radians(45)
    
    nodes = [
        TestNode(
            node_id="base",
            label="Base",
            local_position=[0, 0, 0],
            local_rotation=[0, 0, r45],  # 45° Z
            legacy_world_position=[0, 0, 0],
            legacy_world_rotation=[0, 0, r45],
        ),
        TestNode(
            node_id="turret",
            label="Turret",
            parent_id="base",
            socket_type="TOP_CENTER",
            local_position=[0, 0, 0.5],
            local_rotation=[0, 0, r45],  # Another 45° Z (total 90°)
            # After base rotation, local Z offset stays Z (rotation around Z doesn't affect Z)
            legacy_world_position=[0, 0, 0.5],
            legacy_world_rotation=[0, 0, 2*r45],  # 90°
        ),
        TestNode(
            node_id="cannon",
            label="Cannon",
            parent_id="turret",
            socket_type="TOP_CENTER",
            local_position=[0, 0, 0.3],
            local_rotation=[0, 0, r45],  # Another 45° (total 135°)
            legacy_world_position=[0, 0, 0.8],
            legacy_world_rotation=[0, 0, 3*r45],  # 135°
        ),
        TestNode(
            node_id="barrel",
            label="Barrel",
            parent_id="cannon",
            socket_type="TOP_CENTER",
            local_position=[0, 0, 0.4],
            local_rotation=[0, 0, r45],  # Another 45° (total 180°)
            legacy_world_position=[0, 0, 1.2],
            legacy_world_rotation=[0, 0, 4*r45],  # 180°
        ),
    ]
    
    legacy = {
        "base": {"position": [0, 0, 0], "rotation": [0, 0, r45]},
        "turret": {"position": [0, 0, 0.5], "rotation": [0, 0, 2*r45]},
        "cannon": {"position": [0, 0, 0.8], "rotation": [0, 0, 3*r45]},
        "barrel": {"position": [0, 0, 1.2], "rotation": [0, 0, 4*r45]},
    }
    
    return "Model B: Rotated Hierarchy", build_test_hierarchy(nodes), legacy


# ---------------------------------------------------------------------------
# Model C: Deep Hierarchy (6 levels)
# ---------------------------------------------------------------------------

def create_model_c() -> tuple[str, List[TestNode], Dict[str, Dict]]:
    """Model C — Deep hierarchy (6 levels, tests >2 level composition)."""
    nodes = [
        TestNode(
            node_id="base",
            label="Base",
            local_position=[0, 0, 0],
            legacy_world_position=[0, 0, 0],
        ),
        TestNode(
            node_id="turret",
            label="Turret",
            parent_id="base",
            socket_type="TOP_CENTER",
            local_position=[0, 0, 0.5],
            legacy_world_position=[0, 0, 0.5],
        ),
        TestNode(
            node_id="cannon",
            label="Cannon",
            parent_id="turret",
            socket_type="TOP_CENTER",
            local_position=[0, 0, 0.3],
            legacy_world_position=[0, 0, 0.8],
        ),
        TestNode(
            node_id="breech",
            label="Breech",
            parent_id="cannon",
            socket_type="TOP_CENTER",
            local_position=[0, 0, 0.2],
            legacy_world_position=[0, 0, 1.0],
        ),
        TestNode(
            node_id="barrel",
            label="Barrel",
            parent_id="breech",
            socket_type="TOP_CENTER",
            local_position=[0, 0, 0.6],
            legacy_world_position=[0, 0, 1.6],
        ),
        TestNode(
            node_id="muzzle",
            label="Muzzle",
            parent_id="barrel",
            socket_type="TOP_CENTER",
            local_position=[0, 0, 0.1],
            legacy_world_position=[0, 0, 1.7],
        ),
    ]
    
    legacy = {
        "base": {"position": [0, 0, 0], "rotation": [0, 0, 0]},
        "turret": {"position": [0, 0, 0.5], "rotation": [0, 0, 0]},
        "cannon": {"position": [0, 0, 0.8], "rotation": [0, 0, 0]},
        "breech": {"position": [0, 0, 1.0], "rotation": [0, 0, 0]},
        "barrel": {"position": [0, 0, 1.6], "rotation": [0, 0, 0]},
        "muzzle": {"position": [0, 0, 1.7], "rotation": [0, 0, 0]},
    }
    
    return "Model C: Deep Hierarchy", build_test_hierarchy(nodes), legacy


# ---------------------------------------------------------------------------
# Model D: Sockets and Branching
# ---------------------------------------------------------------------------

def create_model_d() -> tuple[str, List[TestNode], Dict[str, Dict]]:
    """Model D — Sockets and branching (RADIAL, multiple children)."""
    r90 = math.pi / 2
    
    nodes = [
        TestNode(
            node_id="base",
            label="Base",
            local_position=[0, 0, 0],
            legacy_world_position=[0, 0, 0],
        ),
        TestNode(
            node_id="turret",
            label="Turret",
            parent_id="base",
            socket_type="TOP_CENTER",
            local_position=[0, 0, 0.5],
            local_rotation=[0, 0, r90],  # 90° rotation
            legacy_world_position=[0, 0, 0.5],
            legacy_world_rotation=[0, 0, r90],
        ),
        # Counterweight - offset in local X (becomes Y after turret rotation)
        TestNode(
            node_id="counterweight",
            label="Counterweight",
            parent_id="turret",
            socket_type="RADIAL",
            local_position=[-0.4, 0, 0],  # Local -X
            legacy_world_position=[0, -0.4, 0.5],  # After 90° Z: -X → -Y
            legacy_world_rotation=[0, 0, r90],
        ),
        # Cannon - offset in local +X (becomes +Y after turret rotation)
        TestNode(
            node_id="cannon",
            label="Cannon",
            parent_id="turret",
            socket_type="TOP_CENTER",
            local_position=[0.3, 0, 0.2],  # Local +X, +Z
            legacy_world_position=[0, 0.3, 0.7],  # After 90° Z: +X → +Y
            legacy_world_rotation=[0, 0, r90],
        ),
        TestNode(
            node_id="barrel",
            label="Barrel",
            parent_id="cannon",
            socket_type="TOP_CENTER",
            local_position=[0, 0, 0.5],
            legacy_world_position=[0, 0.3, 1.2],
            legacy_world_rotation=[0, 0, r90],
        ),
        TestNode(
            node_id="muzzle",
            label="Muzzle",
            parent_id="barrel",
            socket_type="TOP_CENTER",
            local_position=[0, 0, 0.1],
            legacy_world_position=[0, 0.3, 1.3],
            legacy_world_rotation=[0, 0, r90],
        ),
    ]
    
    legacy = {
        "base": {"position": [0, 0, 0], "rotation": [0, 0, 0]},
        "turret": {"position": [0, 0, 0.5], "rotation": [0, 0, r90]},
        "counterweight": {"position": [0, -0.4, 0.5], "rotation": [0, 0, r90]},
        "cannon": {"position": [0, 0.3, 0.7], "rotation": [0, 0, r90]},
        "barrel": {"position": [0, 0.3, 1.2], "rotation": [0, 0, r90]},
        "muzzle": {"position": [0, 0.3, 1.3], "rotation": [0, 0, r90]},
    }
    
    return "Model D: Sockets and Branching", build_test_hierarchy(nodes), legacy


# ---------------------------------------------------------------------------
# Model E: Hostile Combination
# ---------------------------------------------------------------------------

def create_model_e() -> tuple[str, List[TestNode], Dict[str, Dict]]:
    """Model E — Hostile combination (rotation at multiple levels, sockets, deep)."""
    r30 = math.radians(30)
    r45 = math.radians(45)
    r60 = math.radians(60)
    
    # This is the most complex test case
    # Base rotated, turret rotated, multiple branches, deep hierarchy
    
    nodes = [
        TestNode(
            node_id="base",
            label="Base",
            local_position=[0, 0, 0],
            local_rotation=[0, 0, r30],  # 30° Z
            legacy_world_position=[0, 0, 0],
            legacy_world_rotation=[0, 0, r30],
        ),
        TestNode(
            node_id="turret",
            label="Turret",
            parent_id="base",
            socket_type="TOP_CENTER",
            local_position=[0, 0, 0.5],
            local_rotation=[0, 0, r45],  # +45° (total 75°)
            legacy_world_position=[0, 0, 0.5],
            legacy_world_rotation=[0, 0, r30 + r45],
        ),
        # Counterweight via RADIAL_BRIDGE
        TestNode(
            node_id="counterweight",
            label="Counterweight",
            parent_id="turret",
            socket_type="RADIAL_BRIDGE",
            local_position=[-0.5, 0, 0],  # Local -X
            local_rotation=[0, 0, 0],
            # After 75° Z rotation: local -X rotates to world direction
            # cos(75°) ≈ 0.259, sin(75°) ≈ 0.966
            # -X * cos(75°) = -0.129, -X * -sin(75°) = 0.483 (for Y)
            # Actually: R_z(θ) * [-0.5, 0, 0] = [-0.5*cos(θ), -0.5*sin(θ), 0]
            # = [-0.5*0.259, -0.5*0.966, 0] = [-0.129, -0.483, 0]
            legacy_world_position=[-0.5 * math.cos(r30+r45), -0.5 * math.sin(r30+r45), 0.5],
            legacy_world_rotation=[0, 0, r30 + r45],
        ),
        TestNode(
            node_id="cannon",
            label="Cannon",
            parent_id="turret",
            socket_type="TOP_CENTER",
            local_position=[0, 0, 0.3],
            local_rotation=[0, 0, r30],  # +30° (total 105°)
            legacy_world_position=[0, 0, 0.8],
            legacy_world_rotation=[0, 0, r30 + r45 + r30],
        ),
        TestNode(
            node_id="breech",
            label="Breech",
            parent_id="cannon",
            socket_type="TOP_CENTER",
            local_position=[0, 0, 0.15],
            local_rotation=[0, 0, 0],
            legacy_world_position=[0, 0, 0.95],
            legacy_world_rotation=[0, 0, r30 + r45 + r30],
        ),
        TestNode(
            node_id="barrel",
            label="Barrel",
            parent_id="breech",
            socket_type="TOP_CENTER",
            local_position=[0, 0, 0.4],
            local_rotation=[0, 0, r60],  # +60° (total 165°)
            legacy_world_position=[0, 0, 1.35],
            legacy_world_rotation=[0, 0, r30 + r45 + r30 + r60],
        ),
        TestNode(
            node_id="muzzle",
            label="Muzzle",
            parent_id="barrel",
            socket_type="TOP_CENTER",
            local_position=[0, 0, 0.1],
            local_rotation=[0, 0, 0],
            legacy_world_position=[0, 0, 1.45],
            legacy_world_rotation=[0, 0, r30 + r45 + r30 + r60],
        ),
    ]
    
    legacy = {n.node_id: {"position": n.legacy_world_position, "rotation": n.legacy_world_rotation} 
              for n in nodes}
    
    return "Model E: Hostile Combination", build_test_hierarchy(nodes), legacy


# ---------------------------------------------------------------------------
# Socket Closure Check
# ---------------------------------------------------------------------------

def check_socket_closure(nodes: List[TestNode], node_map: Dict[str, TestNode]) -> List[str]:
    """Check socket closure for all parent-child pairs."""
    results = []
    
    for node in nodes:
        if not node.parent_id or node.parent_id not in node_map:
            continue
        
        parent = node_map[node.parent_id]
        
        # Get world positions
        parent_world = parent.transform_state.world_matrix
        child_world = node.transform_state.world_matrix
        
        if not parent_world or not child_world:
            continue
        
        # For socket closure, we'd need socket positions
        # For now, just report the parent-child world positions
        parent_pos = parent_world.position
        child_pos = child_world.position
        
        # Calculate distance (simplified - actual socket closure needs socket offsets)
        dist = math.sqrt(sum((a-b)**2 for a, b in zip(parent_pos, child_pos)))
        
        results.append(f"  {parent.label} -> {node.label}: distance={dist:.3f}m")
    
    return results


# ---------------------------------------------------------------------------
# Detailed Audit Output
# ---------------------------------------------------------------------------

def run_detailed_audit(name: str, nodes: List[TestNode], legacy: Dict[str, Dict]) -> str:
    """Run audit and produce detailed output."""
    lines = []
    lines.append("")
    lines.append("=" * 70)
    lines.append(f"TRANSFORM AUDIT: {name}")
    lines.append("=" * 70)
    lines.append("")
    
    # Run the audit
    result = audit_model_transforms(nodes, legacy, name)
    
    # Summary table
    lines.append(f"{'Node':<20} {'Depth':>5} {'Status':<8} {'Pos D':>10} {'Rot D':>10}")
    lines.append("-" * 70)
    
    for node_result in sorted(result.nodes, key=lambda x: (x.depth, x.node_id)):
        status = "MATCH" if node_result.status == "MATCH" else "DIFFER"
        pos_delta = f"{node_result.position_delta:.4f}"
        rot_delta = f"{node_result.rotation_delta:.2f}deg"
        lines.append(f"{node_result.label:<20} {node_result.depth:>5} {status:<8} {pos_delta:>10} {rot_delta:>10}")
    
    lines.append("")
    lines.append(f"Total: {result.total_nodes} nodes, {result.match_count} MATCH, {result.differ_count} DIFFER")
    lines.append("")
    
    # Pattern analysis
    if result.differ_count > 0:
        lines.append("PATTERN ANALYSIS")
        lines.append("-" * 40)
        lines.append(f"  Pattern:    {result.pattern}")
        lines.append(f"  Hypothesis: {result.root_cause_hypothesis}")
        lines.append("")
        
        # Detailed mismatches
        lines.append("DETAILED MISMATCHES")
        lines.append("-" * 40)
        for m in result.mismatches:
            lines.append(f"\n  {m.label} ({m.node_id})")
            lines.append(f"    Depth:      {m.depth}")
            lines.append(f"    Parent:     {m.parent_id or 'ROOT'}")
            lines.append(f"    Socket:     {m.socket_type or 'N/A'}")
            lines.append(f"    Pos delta:  {m.position_delta:.6f} m")
            lines.append(f"    Rot delta:  {m.rotation_delta:.2f}°")
            lines.append(f"    Legacy pos: [{', '.join(f'{v:.4f}' for v in m.legacy_world_position)}]")
            lines.append(f"    New pos:    [{', '.join(f'{v:.4f}' for v in m.new_world_position)}]")
            lines.append(f"    Legacy rot: [{', '.join(f'{v:.4f}' for v in m.legacy_world_rotation)}]")
            lines.append(f"    New rot:    [{', '.join(f'{v:.4f}' for v in m.new_world_rotation)}]")
    else:
        lines.append("[OK] ALL TRANSFORMS MATCH")
    
    lines.append("")
    
    # Socket closure (simplified)
    node_map = {n.node_id: n for n in nodes}
    closure_results = check_socket_closure(nodes, node_map)
    if closure_results:
        lines.append("PARENT-CHILD DISTANCES")
        lines.append("-" * 40)
        lines.extend(closure_results)
        lines.append("")
    
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_all_test_models():
    """Run audit on all test models A-E."""
    models = [
        create_model_a,
        create_model_b,
        create_model_c,
        create_model_d,
        create_model_e,
    ]
    
    all_output = []
    all_output.append("\n" + "=" * 70)
    all_output.append("PRE-PHASE 4 TRANSFORM AUDIT — TEST MODELS A-E")
    all_output.append("=" * 70)
    
    summary = []
    
    for create_fn in models:
        name, nodes, legacy = create_fn()
        output = run_detailed_audit(name, nodes, legacy)
        all_output.append(output)
        
        # Quick summary
        result = audit_model_transforms(nodes, legacy, name)
        status = "[OK] PASS" if result.differ_count == 0 else f"[FAIL] ({result.differ_count} differ)"
        summary.append(f"  {name}: {status}")
    
    # Final summary
    all_output.append("\n" + "=" * 70)
    all_output.append("SUMMARY")
    all_output.append("=" * 70)
    all_output.extend(summary)
    all_output.append("")
    
    return "\n".join(all_output)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--test-models":
        print(run_all_test_models())
    else:
        print("Usage: python run_audit.py --test-models")
        print("")
        print("This runs the 5 validation models (A-E) through the shadow transform")
        print("pipeline and compares against expected legacy transforms.")
