"""Debug script for transform propagation with various test cases."""
import sys
sys.path.insert(0, '.')

from core.blender_pipeline.progressive_v2.manifest import BuildManifest, GeometrySpec, AttachmentSpec
from core.blender_pipeline.progressive_v2.node_types import NodeKind, PrimitiveType, SocketType
from core.blender_pipeline.progressive_v2.transforms import LocalTransform, WorldMatrix, NodeTransformState
from core.blender_pipeline.progressive_v2.controller import ProgressiveController
from core.blender_pipeline.progressive_v2.stages.stage4_resolver import Stage4Resolver
from unittest.mock import MagicMock


def test_case_1_desk_lamp():
    """
    Test Case 1: Desk Lamp (original test)
    
    Structure:
      lamp (MODEL)
      └── base_assembly (ASSEMBLY, ROOT)
          ├── base (PART, ROOT) - cylinder, radius=0.1, depth=0.05
          └── stem_assembly (ASSEMBLY, TOP_CENTER)
              └── stem (PART, ROOT) - cylinder, radius=0.015, depth=0.35
    
    Expected:
      - base at Z=0 (center)
      - stem at Z = base.max_z + stem.half_depth = 0.025 + 0.175 = 0.2
    """
    print("\n" + "="*60)
    print("TEST CASE 1: Desk Lamp")
    print("="*60)
    
    manifest = BuildManifest.create('desk lamp')
    
    # Create base_assembly
    base_assembly = manifest.add_child_node(
        parent_id=manifest.root_node_id,
        label='base_assembly',
        kind=NodeKind.ASSEMBLY,
        attachment=AttachmentSpec(socket_type=SocketType.ROOT),
    )
    
    # Create base (ROOT of base_assembly)
    base = manifest.add_child_node(
        parent_id=base_assembly.node_id,
        label='base',
        kind=NodeKind.PART,
        geometry=GeometrySpec(primitive=PrimitiveType.CYLINDER),
        attachment=AttachmentSpec(socket_type=SocketType.ROOT),
    )
    base.stage_outputs['stage2'] = {'radius': 0.1, 'depth': 0.05}  # 5cm tall
    base.stage_outputs['stage3'] = {}
    base.attachment.local_offset = [0.0, 0.0, 0.0]
    base.attachment.local_rotation = [0.0, 0.0, 0.0]
    base.transform_state = NodeTransformState()
    base.transform_state.set_local_transform(LocalTransform.identity())
    base.world_position = [0.0, 0.0, 0.0]
    base.world_rotation = [0.0, 0.0, 0.0]
    base.transform_state.world_matrix = WorldMatrix.from_local(
        LocalTransform(position=[0.0, 0.0, 0.0], rotation=[0.0, 0.0, 0.0])
    )
    base.bounding_box = {'min': [-0.1, -0.1, -0.025], 'max': [0.1, 0.1, 0.025]}
    
    # Create stem_assembly (TOP_CENTER of base_assembly)
    stem_assembly = manifest.add_child_node(
        parent_id=base_assembly.node_id,
        label='stem_assembly',
        kind=NodeKind.ASSEMBLY,
        attachment=AttachmentSpec(socket_type=SocketType.TOP_CENTER),
    )
    
    # Create stem (ROOT of stem_assembly)
    stem = manifest.add_child_node(
        parent_id=stem_assembly.node_id,
        label='stem',
        kind=NodeKind.PART,
        geometry=GeometrySpec(primitive=PrimitiveType.CYLINDER),
        attachment=AttachmentSpec(socket_type=SocketType.ROOT),
    )
    stem.stage_outputs['stage2'] = {'radius': 0.015, 'depth': 0.35}  # 35cm tall
    stem.stage_outputs['stage3'] = {}
    
    # Run Stage 4 for stem
    resolved, solution = Stage4Resolver.run(stem, manifest)
    stem.attachment.local_offset = resolved.offset
    stem.attachment.local_rotation = resolved.rotation
    stem.transform_state = NodeTransformState()
    stem.transform_state.set_local_transform(solution.local_transform)
    
    # Test propagation
    controller = ProgressiveController(model_manager=MagicMock(), mcp_manager=None)
    controller.manifest = manifest
    controller._propagate_new_world_transform(stem, 'test')
    
    world_pos = stem.transform_state.world_matrix.position
    expected_z = 0.2  # base.max_z (0.025) + stem.half_depth (0.175)
    
    print(f"Base: center at Z=0, bbox Z: [-0.025, 0.025]")
    print(f"Stem: half_depth=0.175")
    print(f"Expected stem Z: {expected_z}")
    print(f"Actual stem Z: {world_pos[2]:.6f}")
    print(f"PASS: {abs(world_pos[2] - expected_z) < 0.001}")
    
    return abs(world_pos[2] - expected_z) < 0.001


def test_case_2_tall_tower():
    """
    Test Case 2: Tall Tower with different dimensions
    
    Structure:
      tower (MODEL)
      └── tower_assembly (ASSEMBLY, ROOT)
          ├── foundation (PART, ROOT) - box 2x2x0.5m
          └── column_assembly (ASSEMBLY, TOP_CENTER)
              └── column (PART, ROOT) - cylinder radius=0.3, depth=3.0m
    
    Expected:
      - foundation at Z=0 (center)
      - column at Z = foundation.max_z + column.half_depth = 0.25 + 1.5 = 1.75
    """
    print("\n" + "="*60)
    print("TEST CASE 2: Tall Tower")
    print("="*60)
    
    manifest = BuildManifest.create('tall tower')
    
    tower_assembly = manifest.add_child_node(
        parent_id=manifest.root_node_id,
        label='tower_assembly',
        kind=NodeKind.ASSEMBLY,
        attachment=AttachmentSpec(socket_type=SocketType.ROOT),
    )
    
    foundation = manifest.add_child_node(
        parent_id=tower_assembly.node_id,
        label='foundation',
        kind=NodeKind.PART,
        geometry=GeometrySpec(primitive=PrimitiveType.BOX),
        attachment=AttachmentSpec(socket_type=SocketType.ROOT),
    )
    foundation.stage_outputs['stage2'] = {'size_x': 2.0, 'size_y': 2.0, 'size_z': 0.5}
    foundation.stage_outputs['stage3'] = {}
    foundation.attachment.local_offset = [0.0, 0.0, 0.0]
    foundation.attachment.local_rotation = [0.0, 0.0, 0.0]
    foundation.transform_state = NodeTransformState()
    foundation.transform_state.set_local_transform(LocalTransform.identity())
    foundation.world_position = [0.0, 0.0, 0.0]
    foundation.world_rotation = [0.0, 0.0, 0.0]
    foundation.transform_state.world_matrix = WorldMatrix.from_local(
        LocalTransform(position=[0.0, 0.0, 0.0])
    )
    foundation.bounding_box = {'min': [-1.0, -1.0, -0.25], 'max': [1.0, 1.0, 0.25]}
    
    column_assembly = manifest.add_child_node(
        parent_id=tower_assembly.node_id,
        label='column_assembly',
        kind=NodeKind.ASSEMBLY,
        attachment=AttachmentSpec(socket_type=SocketType.TOP_CENTER),
    )
    
    column = manifest.add_child_node(
        parent_id=column_assembly.node_id,
        label='column',
        kind=NodeKind.PART,
        geometry=GeometrySpec(primitive=PrimitiveType.CYLINDER),
        attachment=AttachmentSpec(socket_type=SocketType.ROOT),
    )
    column.stage_outputs['stage2'] = {'radius': 0.3, 'depth': 3.0}
    column.stage_outputs['stage3'] = {}
    
    resolved, solution = Stage4Resolver.run(column, manifest)
    column.attachment.local_offset = resolved.offset
    column.attachment.local_rotation = resolved.rotation
    column.transform_state = NodeTransformState()
    column.transform_state.set_local_transform(solution.local_transform)
    
    controller = ProgressiveController(model_manager=MagicMock(), mcp_manager=None)
    controller.manifest = manifest
    controller._propagate_new_world_transform(column, 'test')
    
    world_pos = column.transform_state.world_matrix.position
    expected_z = 1.75  # foundation.max_z (0.25) + column.half_depth (1.5)
    
    print(f"Foundation: center at Z=0, bbox Z: [-0.25, 0.25]")
    print(f"Column: half_depth=1.5")
    print(f"Expected column Z: {expected_z}")
    print(f"Actual column Z: {world_pos[2]:.6f}")
    print(f"PASS: {abs(world_pos[2] - expected_z) < 0.001}")
    
    return abs(world_pos[2] - expected_z) < 0.001


def test_case_3_three_level_stack():
    """
    Test Case 3: Three-level stack
    
    Structure:
      stack (MODEL)
      └── stack_assembly (ASSEMBLY, ROOT)
          ├── bottom (PART, ROOT) - box 1x1x0.2m
          └── middle_assembly (ASSEMBLY, TOP_CENTER)
              ├── middle (PART, ROOT) - box 0.8x0.8x0.3m
              └── top_assembly (ASSEMBLY, TOP_CENTER)
                  └── top (PART, ROOT) - box 0.6x0.6x0.1m
    
    Expected:
      - bottom at Z=0
      - middle at Z = bottom.max_z + middle.half_z = 0.1 + 0.15 = 0.25
      - top at Z = middle.world_z + middle.half_z + top.half_z = 0.25 + 0.15 + 0.05 = 0.45
    """
    print("\n" + "="*60)
    print("TEST CASE 3: Three-Level Stack")
    print("="*60)
    
    manifest = BuildManifest.create('three level stack')
    
    stack_assembly = manifest.add_child_node(
        parent_id=manifest.root_node_id,
        label='stack_assembly',
        kind=NodeKind.ASSEMBLY,
        attachment=AttachmentSpec(socket_type=SocketType.ROOT),
    )
    
    # Bottom layer
    bottom = manifest.add_child_node(
        parent_id=stack_assembly.node_id,
        label='bottom',
        kind=NodeKind.PART,
        geometry=GeometrySpec(primitive=PrimitiveType.BOX),
        attachment=AttachmentSpec(socket_type=SocketType.ROOT),
    )
    bottom.stage_outputs['stage2'] = {'size_x': 1.0, 'size_y': 1.0, 'size_z': 0.2}
    bottom.stage_outputs['stage3'] = {}
    bottom.attachment.local_offset = [0.0, 0.0, 0.0]
    bottom.attachment.local_rotation = [0.0, 0.0, 0.0]
    bottom.transform_state = NodeTransformState()
    bottom.transform_state.set_local_transform(LocalTransform.identity())
    bottom.world_position = [0.0, 0.0, 0.0]
    bottom.world_rotation = [0.0, 0.0, 0.0]
    bottom.transform_state.world_matrix = WorldMatrix.from_local(
        LocalTransform(position=[0.0, 0.0, 0.0])
    )
    bottom.bounding_box = {'min': [-0.5, -0.5, -0.1], 'max': [0.5, 0.5, 0.1]}
    
    # Middle assembly
    middle_assembly = manifest.add_child_node(
        parent_id=stack_assembly.node_id,
        label='middle_assembly',
        kind=NodeKind.ASSEMBLY,
        attachment=AttachmentSpec(socket_type=SocketType.TOP_CENTER),
    )
    
    middle = manifest.add_child_node(
        parent_id=middle_assembly.node_id,
        label='middle',
        kind=NodeKind.PART,
        geometry=GeometrySpec(primitive=PrimitiveType.BOX),
        attachment=AttachmentSpec(socket_type=SocketType.ROOT),
    )
    middle.stage_outputs['stage2'] = {'size_x': 0.8, 'size_y': 0.8, 'size_z': 0.3}
    middle.stage_outputs['stage3'] = {}
    
    resolved, solution = Stage4Resolver.run(middle, manifest)
    middle.attachment.local_offset = resolved.offset
    middle.attachment.local_rotation = resolved.rotation
    middle.transform_state = NodeTransformState()
    middle.transform_state.set_local_transform(solution.local_transform)
    
    controller = ProgressiveController(model_manager=MagicMock(), mcp_manager=None)
    controller.manifest = manifest
    controller._propagate_new_world_transform(middle, 'test')
    
    # Simulate middle being built
    middle.world_position = list(middle.transform_state.world_matrix.position)
    middle.world_rotation = list(middle.transform_state.world_matrix.rotation)
    middle.bounding_box = {
        'min': [middle.world_position[0] - 0.4, middle.world_position[1] - 0.4, middle.world_position[2] - 0.15],
        'max': [middle.world_position[0] + 0.4, middle.world_position[1] + 0.4, middle.world_position[2] + 0.15]
    }
    
    middle_z = middle.transform_state.world_matrix.position[2]
    expected_middle_z = 0.25  # bottom.max_z (0.1) + middle.half_z (0.15)
    
    print(f"Bottom: center at Z=0, bbox Z: [-0.1, 0.1]")
    print(f"Middle: half_z=0.15")
    print(f"Expected middle Z: {expected_middle_z}")
    print(f"Actual middle Z: {middle_z:.6f}")
    print(f"Middle PASS: {abs(middle_z - expected_middle_z) < 0.001}")
    
    # Top assembly
    top_assembly = manifest.add_child_node(
        parent_id=middle_assembly.node_id,
        label='top_assembly',
        kind=NodeKind.ASSEMBLY,
        attachment=AttachmentSpec(socket_type=SocketType.TOP_CENTER),
    )
    
    top = manifest.add_child_node(
        parent_id=top_assembly.node_id,
        label='top',
        kind=NodeKind.PART,
        geometry=GeometrySpec(primitive=PrimitiveType.BOX),
        attachment=AttachmentSpec(socket_type=SocketType.ROOT),
    )
    top.stage_outputs['stage2'] = {'size_x': 0.6, 'size_y': 0.6, 'size_z': 0.1}
    top.stage_outputs['stage3'] = {}
    
    resolved, solution = Stage4Resolver.run(top, manifest)
    top.attachment.local_offset = resolved.offset
    top.attachment.local_rotation = resolved.rotation
    top.transform_state = NodeTransformState()
    top.transform_state.set_local_transform(solution.local_transform)
    
    controller._propagate_new_world_transform(top, 'test')
    
    top_z = top.transform_state.world_matrix.position[2]
    expected_top_z = 0.45  # middle.world_z (0.25) + middle.half_z (0.15) + top.half_z (0.05)
    
    print(f"Top: half_z=0.05")
    print(f"Expected top Z: {expected_top_z}")
    print(f"Actual top Z: {top_z:.6f}")
    print(f"Top PASS: {abs(top_z - expected_top_z) < 0.001}")
    
    return abs(middle_z - expected_middle_z) < 0.001 and abs(top_z - expected_top_z) < 0.001


def test_case_4_offset_base():
    """
    Test Case 4: Base at non-origin position
    
    Structure:
      model (MODEL)
      └── assembly (ASSEMBLY, ROOT)
          ├── base (PART, ROOT) - at position [1.0, 2.0, 0.5]
          └── child_assembly (ASSEMBLY, TOP_CENTER)
              └── child (PART, ROOT)
    
    Expected:
      - base at [1.0, 2.0, 0.5]
      - child at [1.0, 2.0, base.world_z + base.half_z + child.half_z]
    """
    print("\n" + "="*60)
    print("TEST CASE 4: Offset Base Position")
    print("="*60)
    
    manifest = BuildManifest.create('offset model')
    
    assembly = manifest.add_child_node(
        parent_id=manifest.root_node_id,
        label='assembly',
        kind=NodeKind.ASSEMBLY,
        attachment=AttachmentSpec(socket_type=SocketType.ROOT),
    )
    
    base = manifest.add_child_node(
        parent_id=assembly.node_id,
        label='base',
        kind=NodeKind.PART,
        geometry=GeometrySpec(primitive=PrimitiveType.BOX),
        attachment=AttachmentSpec(socket_type=SocketType.ROOT),
    )
    base.stage_outputs['stage2'] = {'size_x': 1.0, 'size_y': 1.0, 'size_z': 0.4}
    base.stage_outputs['stage3'] = {}
    base.attachment.local_offset = [1.0, 2.0, 0.5]  # Non-origin position
    base.attachment.local_rotation = [0.0, 0.0, 0.0]
    base.transform_state = NodeTransformState()
    base.transform_state.set_local_transform(LocalTransform(position=[1.0, 2.0, 0.5]))
    base.world_position = [1.0, 2.0, 0.5]
    base.world_rotation = [0.0, 0.0, 0.0]
    base.transform_state.world_matrix = WorldMatrix.from_local(
        LocalTransform(position=[1.0, 2.0, 0.5])
    )
    base.bounding_box = {'min': [0.5, 1.5, 0.3], 'max': [1.5, 2.5, 0.7]}
    
    child_assembly = manifest.add_child_node(
        parent_id=assembly.node_id,
        label='child_assembly',
        kind=NodeKind.ASSEMBLY,
        attachment=AttachmentSpec(socket_type=SocketType.TOP_CENTER),
    )
    
    child = manifest.add_child_node(
        parent_id=child_assembly.node_id,
        label='child',
        kind=NodeKind.PART,
        geometry=GeometrySpec(primitive=PrimitiveType.BOX),
        attachment=AttachmentSpec(socket_type=SocketType.ROOT),
    )
    child.stage_outputs['stage2'] = {'size_x': 0.5, 'size_y': 0.5, 'size_z': 0.2}
    child.stage_outputs['stage3'] = {}
    
    resolved, solution = Stage4Resolver.run(child, manifest)
    child.attachment.local_offset = resolved.offset
    child.attachment.local_rotation = resolved.rotation
    child.transform_state = NodeTransformState()
    child.transform_state.set_local_transform(solution.local_transform)
    
    controller = ProgressiveController(model_manager=MagicMock(), mcp_manager=None)
    controller.manifest = manifest
    controller._propagate_new_world_transform(child, 'test')
    
    world_pos = child.transform_state.world_matrix.position
    expected_x = 1.0
    expected_y = 2.0
    expected_z = 0.5 + 0.2 + 0.1  # base.world_z + base.half_z + child.half_z = 0.8
    
    print(f"Base: at [1.0, 2.0, 0.5], half_z=0.2")
    print(f"Child: half_z=0.1")
    print(f"Expected child pos: [{expected_x}, {expected_y}, {expected_z}]")
    print(f"Actual child pos: [{world_pos[0]:.6f}, {world_pos[1]:.6f}, {world_pos[2]:.6f}]")
    
    pass_x = abs(world_pos[0] - expected_x) < 0.001
    pass_y = abs(world_pos[1] - expected_y) < 0.001
    pass_z = abs(world_pos[2] - expected_z) < 0.001
    
    print(f"PASS: X={pass_x}, Y={pass_y}, Z={pass_z}")
    
    return pass_x and pass_y and pass_z


def test_case_5_horizontal_stack():
    """
    Test Case 5: Horizontal stacking (FRONT_CENTER)
    
    Structure:
      model (MODEL)
      └── assembly (ASSEMBLY, ROOT)
          ├── body (PART, ROOT) - box 1x0.5x0.3m
          └── front_assembly (ASSEMBLY, FRONT_CENTER)
              └── nose (PART, ROOT) - cone radius=0.1, depth=0.2m
    
    Expected:
      - body at [0, 0, 0]
      - nose at [0, body.min_y - nose.half_depth, 0] = [0, -0.25 - 0.1, 0] = [0, -0.35, 0]
    """
    print("\n" + "="*60)
    print("TEST CASE 5: Horizontal Stack (FRONT_CENTER)")
    print("="*60)
    
    manifest = BuildManifest.create('car')
    
    assembly = manifest.add_child_node(
        parent_id=manifest.root_node_id,
        label='car_assembly',
        kind=NodeKind.ASSEMBLY,
        attachment=AttachmentSpec(socket_type=SocketType.ROOT),
    )
    
    body = manifest.add_child_node(
        parent_id=assembly.node_id,
        label='body',
        kind=NodeKind.PART,
        geometry=GeometrySpec(primitive=PrimitiveType.BOX),
        attachment=AttachmentSpec(socket_type=SocketType.ROOT),
    )
    body.stage_outputs['stage2'] = {'size_x': 1.0, 'size_y': 0.5, 'size_z': 0.3}
    body.stage_outputs['stage3'] = {}
    body.attachment.local_offset = [0.0, 0.0, 0.0]
    body.attachment.local_rotation = [0.0, 0.0, 0.0]
    body.transform_state = NodeTransformState()
    body.transform_state.set_local_transform(LocalTransform.identity())
    body.world_position = [0.0, 0.0, 0.0]
    body.world_rotation = [0.0, 0.0, 0.0]
    body.transform_state.world_matrix = WorldMatrix.from_local(
        LocalTransform(position=[0.0, 0.0, 0.0])
    )
    body.bounding_box = {'min': [-0.5, -0.25, -0.15], 'max': [0.5, 0.25, 0.15]}
    
    front_assembly = manifest.add_child_node(
        parent_id=assembly.node_id,
        label='front_assembly',
        kind=NodeKind.ASSEMBLY,
        attachment=AttachmentSpec(socket_type=SocketType.FRONT_CENTER),
    )
    
    nose = manifest.add_child_node(
        parent_id=front_assembly.node_id,
        label='nose',
        kind=NodeKind.PART,
        geometry=GeometrySpec(primitive=PrimitiveType.CONE),
        attachment=AttachmentSpec(socket_type=SocketType.ROOT),
    )
    nose.stage_outputs['stage2'] = {'radius': 0.1, 'depth': 0.2}
    nose.stage_outputs['stage3'] = {}
    
    resolved, solution = Stage4Resolver.run(nose, manifest)
    nose.attachment.local_offset = resolved.offset
    nose.attachment.local_rotation = resolved.rotation
    nose.transform_state = NodeTransformState()
    nose.transform_state.set_local_transform(solution.local_transform)
    
    controller = ProgressiveController(model_manager=MagicMock(), mcp_manager=None)
    controller.manifest = manifest
    controller._propagate_new_world_transform(nose, 'test')
    
    world_pos = nose.transform_state.world_matrix.position
    expected_x = 0.0
    expected_y = -0.35  # body.min_y (-0.25) - nose.half_depth (0.1)
    expected_z = 0.0
    
    print(f"Body: at [0, 0, 0], bbox Y: [-0.25, 0.25]")
    print(f"Nose: half_depth=0.1")
    print(f"Expected nose pos: [{expected_x}, {expected_y}, {expected_z}]")
    print(f"Actual nose pos: [{world_pos[0]:.6f}, {world_pos[1]:.6f}, {world_pos[2]:.6f}]")
    
    pass_x = abs(world_pos[0] - expected_x) < 0.001
    pass_y = abs(world_pos[1] - expected_y) < 0.001
    pass_z = abs(world_pos[2] - expected_z) < 0.001
    
    print(f"PASS: X={pass_x}, Y={pass_y}, Z={pass_z}")
    
    return pass_x and pass_y and pass_z


if __name__ == '__main__':
    results = []
    
    results.append(('Desk Lamp', test_case_1_desk_lamp()))
    results.append(('Tall Tower', test_case_2_tall_tower()))
    results.append(('Three-Level Stack', test_case_3_three_level_stack()))
    results.append(('Offset Base', test_case_4_offset_base()))
    results.append(('Horizontal Stack', test_case_5_horizontal_stack()))
    
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    
    all_pass = True
    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"{name}: {status}")
        if not passed:
            all_pass = False
    
    print("\n" + ("ALL TESTS PASSED!" if all_pass else "SOME TESTS FAILED!"))
