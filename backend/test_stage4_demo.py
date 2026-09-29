"""Stage 4 Resolver Demo - Show actual transform output for different socket types."""

import sys
sys.path.insert(0, ".")

from core.blender_pipeline.progressive_v2.manifest import BuildManifest, GeometrySpec, AttachmentSpec
from core.blender_pipeline.progressive_v2.node_types import NodeKind, PrimitiveType, SocketType
from core.blender_pipeline.progressive_v2.stages.stage4_resolver import Stage4Resolver, BBox
import math


def demo_top_center():
    """Demo TOP_CENTER socket resolution."""
    print("\n" + "="*60)
    print("TOP_CENTER Socket (stem on base)")
    print("="*60)
    
    manifest = BuildManifest.create(prompt="lamp", model_id="test")
    
    # Add base (parent)
    base = manifest.add_child_node(
        parent_id=manifest.root_node_id,
        label="base",
        kind=NodeKind.PART,
        geometry=GeometrySpec(primitive=PrimitiveType.CYLINDER),
        attachment=AttachmentSpec(socket_type=SocketType.ROOT),
    )
    base.stage_outputs["stage2"] = {"radius": 0.1, "depth": 0.05}  # 10cm radius, 5cm tall
    
    # Add stem (child)
    stem = manifest.add_child_node(
        parent_id=base.node_id,
        label="stem",
        kind=NodeKind.PART,
        geometry=GeometrySpec(primitive=PrimitiveType.CYLINDER),
        attachment=AttachmentSpec(socket_type=SocketType.TOP_CENTER),
    )
    stem.stage_outputs["stage2"] = {"radius": 0.015, "depth": 0.35}  # 1.5cm radius, 35cm tall
    stem.stage_outputs["stage3"] = {}  # No semantics needed
    
    resolved, solution = Stage4Resolver.run(stem, manifest)
    
    print(f"Parent (base): radius=0.1m, depth=0.05m")
    print(f"Child (stem): radius=0.015m, depth=0.35m")
    print(f"Resolved offset: {[round(x, 4) for x in resolved.offset]}")
    print(f"  Expected Z: parent.max_z + child.half_depth = 0.025 + 0.175 = 0.2")
    print(f"Resolution method: {resolved.resolution_method}")
    return resolved


def demo_corner():
    """Demo CORNER socket resolution (table leg)."""
    print("\n" + "="*60)
    print("CORNER Socket (table leg)")
    print("="*60)
    
    manifest = BuildManifest.create(prompt="table", model_id="test")
    
    # Add tabletop (parent)
    tabletop = manifest.add_child_node(
        parent_id=manifest.root_node_id,
        label="tabletop",
        kind=NodeKind.PART,
        geometry=GeometrySpec(primitive=PrimitiveType.BOX),
        attachment=AttachmentSpec(socket_type=SocketType.ROOT),
    )
    tabletop.stage_outputs["stage2"] = {"size_x": 1.2, "size_y": 0.8, "size_z": 0.03}
    
    # Add leg (child) - label determines corner position
    leg = manifest.add_child_node(
        parent_id=tabletop.node_id,
        label="leg_front_left",  # Label encodes position!
        kind=NodeKind.PART,
        geometry=GeometrySpec(primitive=PrimitiveType.CYLINDER),
        attachment=AttachmentSpec(socket_type=SocketType.CORNER),
    )
    leg.stage_outputs["stage2"] = {"radius": 0.03, "depth": 0.72}
    leg.stage_outputs["stage3"] = {"corner_position": "bottom_front_left"}
    
    resolved, solution = Stage4Resolver.run(leg, manifest)
    
    print(f"Parent (tabletop): 1.2m x 0.8m x 0.03m")
    print(f"Child (leg): radius=0.03m, depth=0.72m")
    print(f"Resolved offset: {[round(x, 4) for x in resolved.offset]}")
    print(f"  X: 80% toward left edge = -0.6 * 0.8 = {-0.6 * 0.8 * 1.2 / 1.2:.4f}")
    print(f"  Y: 80% toward front edge (Blender: -Y = front)")
    print(f"  Z: below tabletop by half leg height")
    print(f"Resolution method: {resolved.resolution_method}")
    return resolved


def demo_through_axis():
    """Demo THROUGH_AXIS socket resolution."""
    print("\n" + "="*60)
    print("THROUGH_AXIS Socket (axle through hub)")
    print("="*60)
    
    manifest = BuildManifest.create(prompt="wheel", model_id="test")
    
    hub = manifest.add_child_node(
        parent_id=manifest.root_node_id,
        label="hub",
        kind=NodeKind.PART,
        geometry=GeometrySpec(primitive=PrimitiveType.CYLINDER),
        attachment=AttachmentSpec(socket_type=SocketType.ROOT),
    )
    hub.stage_outputs["stage2"] = {"radius": 0.15, "depth": 0.1}
    
    axle = manifest.add_child_node(
        parent_id=hub.node_id,
        label="axle",
        kind=NodeKind.PART,
        geometry=GeometrySpec(primitive=PrimitiveType.CYLINDER),
        attachment=AttachmentSpec(socket_type=SocketType.THROUGH_AXIS),
    )
    axle.stage_outputs["stage2"] = {"radius": 0.02, "depth": 0.5}
    axle.stage_outputs["stage3"] = {"pierce_direction": "left_right", "height_hint": "center"}
    
    resolved, solution = Stage4Resolver.run(axle, manifest)
    
    print(f"Parent (hub): radius=0.15m, depth=0.1m")
    print(f"Child (axle): radius=0.02m, depth=0.5m")
    print(f"Resolved offset: {[round(x, 4) for x in resolved.offset]}")
    print(f"Resolved rotation: {[round(math.degrees(r), 1) for r in resolved.rotation]}°")
    print(f"  Rotation Y=90° aligns cylinder along X axis (left_right)")
    print(f"Resolution method: {resolved.resolution_method}")
    return resolved


def demo_boolean_cut():
    """Demo BOOLEAN_CUT socket resolution."""
    print("\n" + "="*60)
    print("BOOLEAN_CUT Socket (hole in panel)")
    print("="*60)
    
    manifest = BuildManifest.create(prompt="panel with hole", model_id="test")
    
    panel = manifest.add_child_node(
        parent_id=manifest.root_node_id,
        label="panel",
        kind=NodeKind.PART,
        geometry=GeometrySpec(primitive=PrimitiveType.BOX),
        attachment=AttachmentSpec(socket_type=SocketType.ROOT),
    )
    panel.stage_outputs["stage2"] = {"size_x": 0.5, "size_y": 0.5, "size_z": 0.02}
    
    cutter = manifest.add_child_node(
        parent_id=panel.node_id,
        label="hole_cutter",
        kind=NodeKind.PART,
        geometry=GeometrySpec(primitive=PrimitiveType.CYLINDER),
        attachment=AttachmentSpec(socket_type=SocketType.BOOLEAN_CUT),
    )
    cutter.stage_outputs["stage2"] = {"radius": 0.05, "depth": 0.05}
    cutter.stage_outputs["stage3"] = {"cut_face": "top"}
    
    resolved, solution = Stage4Resolver.run(cutter, manifest)
    
    print(f"Parent (panel): 0.5m x 0.5m x 0.02m")
    print(f"Child (cutter): radius=0.05m, depth=0.05m")
    print(f"Resolved offset: {[round(x, 4) for x in resolved.offset]}")
    print(f"  Z includes 2mm overshoot to avoid coplanar issues")
    print(f"Boolean op: {resolved.boolean_op}")
    print(f"Resolution method: {resolved.resolution_method}")
    return resolved


def demo_inset():
    """Demo INSET socket resolution (glass in frame)."""
    print("\n" + "="*60)
    print("INSET Socket (glass panel in frame)")
    print("="*60)
    
    manifest = BuildManifest.create(prompt="window", model_id="test")
    
    frame = manifest.add_child_node(
        parent_id=manifest.root_node_id,
        label="frame",
        kind=NodeKind.PART,
        geometry=GeometrySpec(primitive=PrimitiveType.BOX),
        attachment=AttachmentSpec(socket_type=SocketType.ROOT),
    )
    frame.stage_outputs["stage2"] = {"size_x": 0.6, "size_y": 0.02, "size_z": 0.8}
    
    glass = manifest.add_child_node(
        parent_id=frame.node_id,
        label="glass",
        kind=NodeKind.PART,
        geometry=GeometrySpec(primitive=PrimitiveType.BOX),
        attachment=AttachmentSpec(socket_type=SocketType.INSET),
    )
    glass.stage_outputs["stage2"] = {"size_x": 0.55, "size_y": 0.003, "size_z": 0.75}
    glass.stage_outputs["stage3"] = {"inset_face": "front", "inset_depth": 0.005}
    
    resolved, solution = Stage4Resolver.run(glass, manifest)
    
    print(f"Parent (frame): 0.6m x 0.02m x 0.8m")
    print(f"Child (glass): 0.55m x 0.003m x 0.75m")
    print(f"Resolved offset: {[round(x, 4) for x in resolved.offset]}")
    print(f"  Y offset: recessed 5mm from front face")
    print(f"Resolution method: {resolved.resolution_method}")
    return resolved


def demo_array_member():
    """Demo ARRAY_MEMBER socket resolution."""
    print("\n" + "="*60)
    print("ARRAY_MEMBER Socket (keyboard keys)")
    print("="*60)
    
    manifest = BuildManifest.create(prompt="keyboard", model_id="test")
    
    base = manifest.add_child_node(
        parent_id=manifest.root_node_id,
        label="keyboard_base",
        kind=NodeKind.PART,
        geometry=GeometrySpec(primitive=PrimitiveType.BOX),
        attachment=AttachmentSpec(socket_type=SocketType.ROOT),
    )
    base.stage_outputs["stage2"] = {"size_x": 0.4, "size_y": 0.15, "size_z": 0.02}
    
    # Key at index 2 of 5 (middle)
    key = manifest.add_child_node(
        parent_id=base.node_id,
        label="key_3",
        kind=NodeKind.PART,
        geometry=GeometrySpec(primitive=PrimitiveType.BOX),
        attachment=AttachmentSpec(socket_type=SocketType.ARRAY_MEMBER),
    )
    key.stage_outputs["stage2"] = {"size_x": 0.02, "size_y": 0.02, "size_z": 0.01}
    key.stage_outputs["stage3"] = {
        "array_axis": "x",
        "array_count": 5,
        "array_index": 2,  # Middle key
        "spacing_hint": "even"
    }
    
    resolved, solution = Stage4Resolver.run(key, manifest)
    
    print(f"Parent (base): 0.4m x 0.15m x 0.02m")
    print(f"Child (key): 0.02m x 0.02m x 0.01m")
    print(f"Array: index 2 of 5 along X axis")
    print(f"Resolved offset: {[round(x, 4) for x in resolved.offset]}")
    print(f"  X: index 2/5 = 0.5 -> t=0 (center)")
    print(f"  Z: on top of parent")
    print(f"Resolution method: {resolved.resolution_method}")
    return resolved


def demo_radial():
    """Demo RADIAL socket resolution."""
    print("\n" + "="*60)
    print("RADIAL Socket (spokes around hub)")
    print("="*60)
    
    manifest = BuildManifest.create(prompt="wheel", model_id="test")
    
    hub = manifest.add_child_node(
        parent_id=manifest.root_node_id,
        label="hub",
        kind=NodeKind.PART,
        geometry=GeometrySpec(primitive=PrimitiveType.CYLINDER),
        attachment=AttachmentSpec(socket_type=SocketType.ROOT),
    )
    hub.stage_outputs["stage2"] = {"radius": 0.05, "depth": 0.02}
    
    # Spoke at index 1 of 4 (90 degrees)
    spoke = manifest.add_child_node(
        parent_id=hub.node_id,
        label="spoke_1",
        kind=NodeKind.PART,
        geometry=GeometrySpec(primitive=PrimitiveType.CYLINDER),
        attachment=AttachmentSpec(socket_type=SocketType.RADIAL),
    )
    spoke.stage_outputs["stage2"] = {"radius": 0.005, "depth": 0.15}
    spoke.stage_outputs["stage3"] = {"radial_count": 4, "radial_index": 1}
    
    resolved, solution = Stage4Resolver.run(spoke, manifest)
    
    print(f"Parent (hub): radius=0.05m")
    print(f"Child (spoke): radius=0.005m, depth=0.15m")
    print(f"Radial: index 1 of 4 (90° from X axis)")
    print(f"Resolved offset: {[round(x, 4) for x in resolved.offset]}")
    print(f"  Angle: 90° -> X=0, Y=radius")
    print(f"Resolved rotation: {[round(math.degrees(r), 1) for r in resolved.rotation]}°")
    print(f"Resolution method: {resolved.resolution_method}")
    return resolved


def main():
    print("Stage 4 Resolver Demo")
    print("=" * 60)
    print("All transforms are DETERMINISTIC - no LLM calls!")
    
    demo_top_center()
    demo_corner()
    demo_through_axis()
    demo_boolean_cut()
    demo_inset()
    demo_array_member()
    demo_radial()
    
    print("\n" + "="*60)
    print("All Stage 4 demos complete!")
    print("="*60)


if __name__ == "__main__":
    main()
