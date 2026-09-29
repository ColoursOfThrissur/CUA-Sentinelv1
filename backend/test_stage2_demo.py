"""Demo script to show Stage 2 (Dimensions) output."""
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

from core.blender_pipeline.progressive_v2.stages.stage2_dimensions import Stage2Dimensions
from core.blender_pipeline.progressive_v2.manifest import BuildManifest, GeometrySpec, AttachmentSpec
from core.blender_pipeline.progressive_v2.node_types import NodeKind, PrimitiveType, SocketType


async def main():
    print("=" * 60)
    print("STAGE 2: DIMENSIONS - MOCKUP LLM TESTS")
    print("=" * 60)
    
    # Setup mock model manager
    mock_mgr = MagicMock()
    mock_mgr.get_model_for_workflow = MagicMock(return_value='test-model')
    mock_mgr.generate_async = AsyncMock()
    
    # =========================================================================
    # TEST 1: Cylinder (lamp stem)
    # =========================================================================
    print("\n--- TEST 1: Cylinder (lamp stem) ---")
    print("LLM Input (simulated):")
    cylinder_response = {
        "radius": 0.015,
        "depth": 0.35,
        "reasoning": "Lamp stem is thin cylinder, 3cm diameter, 35cm tall"
    }
    print(json.dumps(cylinder_response, indent=2))
    
    mock_mgr.generate_async.return_value = json.dumps(cylinder_response)
    
    manifest = BuildManifest.create(prompt='desk lamp', model_id='test1')
    manifest.stage0_output = {
        "scale_anchor_m": {"overall_height_or_length": 0.5, "reasoning": "50cm lamp"}
    }
    
    stem = manifest.add_child_node(
        parent_id=manifest.root_node_id,
        label="stem",
        kind=NodeKind.PART,
        geometry=GeometrySpec(primitive=PrimitiveType.CYLINDER),
        attachment=AttachmentSpec(socket_type=SocketType.TOP_CENTER),
    )
    
    result = await Stage2Dimensions.run(
        node=stem,
        manifest=manifest,
        model_manager=mock_mgr,
        task_id="test",
    )
    
    print("\nStage 2 Output:")
    print(f"  radius: {result.radius} m ({result.radius * 100:.1f} cm)")
    print(f"  depth:  {result.depth} m ({result.depth * 100:.1f} cm)")
    print(f"  reasoning: {result.reasoning}")
    
    # =========================================================================
    # TEST 2: Box (tabletop)
    # =========================================================================
    print("\n--- TEST 2: Box (tabletop) ---")
    print("LLM Input (simulated):")
    box_response = {
        "size_x": 0.8,
        "size_y": 0.5,
        "size_z": 0.02,
        "reasoning": "Tabletop is 80cm x 50cm, 2cm thick"
    }
    print(json.dumps(box_response, indent=2))
    
    mock_mgr.generate_async.return_value = json.dumps(box_response)
    
    manifest2 = BuildManifest.create(prompt='table', model_id='test2')
    manifest2.stage0_output = {"scale_anchor_m": {"overall_height_or_length": 0.75}}
    
    tabletop = manifest2.add_child_node(
        parent_id=manifest2.root_node_id,
        label="tabletop",
        kind=NodeKind.PART,
        geometry=GeometrySpec(primitive=PrimitiveType.BOX),
        attachment=AttachmentSpec(socket_type=SocketType.ROOT),
    )
    
    result2 = await Stage2Dimensions.run(
        node=tabletop,
        manifest=manifest2,
        model_manager=mock_mgr,
        task_id="test",
    )
    
    print("\nStage 2 Output:")
    print(f"  size_x: {result2.size_x} m ({result2.size_x * 100:.1f} cm)")
    print(f"  size_y: {result2.size_y} m ({result2.size_y * 100:.1f} cm)")
    print(f"  size_z: {result2.size_z} m ({result2.size_z * 100:.2f} cm)")
    print(f"  reasoning: {result2.reasoning}")
    
    # =========================================================================
    # TEST 3: Torus (fan blade - the problematic case!)
    # =========================================================================
    print("\n--- TEST 3: Torus (fan blade) ---")
    print("LLM Input (simulated):")
    torus_response = {
        "major_radius": 0.12,
        "minor_radius": 0.015,
        "reasoning": "Fan blade ring, 24cm outer diameter, 3cm tube thickness"
    }
    print(json.dumps(torus_response, indent=2))
    
    mock_mgr.generate_async.return_value = json.dumps(torus_response)
    
    manifest3 = BuildManifest.create(prompt='desk fan', model_id='test3')
    manifest3.stage0_output = {"scale_anchor_m": {"overall_height_or_length": 0.4}}
    
    fan_blade = manifest3.add_child_node(
        parent_id=manifest3.root_node_id,
        label="fan_blade",
        kind=NodeKind.PART,
        geometry=GeometrySpec(primitive=PrimitiveType.TORUS),
        attachment=AttachmentSpec(socket_type=SocketType.FRONT_CENTER),
    )
    
    result3 = await Stage2Dimensions.run(
        node=fan_blade,
        manifest=manifest3,
        model_manager=mock_mgr,
        task_id="test",
    )
    
    print("\nStage 2 Output:")
    print(f"  major_radius: {result3.major_radius} m ({result3.major_radius * 100:.1f} cm)")
    print(f"  minor_radius: {result3.minor_radius} m ({result3.minor_radius * 100:.1f} cm)")
    print(f"  reasoning: {result3.reasoning}")
    
    # =========================================================================
    # TEST 4: Edge Case - Missing fields (should use defaults)
    # =========================================================================
    print("\n--- TEST 4: Edge Case - Missing fields ---")
    print("LLM Input (simulated - missing size_y and size_z):")
    missing_response = {
        "size_x": 0.3,
        "reasoning": "Only width specified"
    }
    print(json.dumps(missing_response, indent=2))
    
    mock_mgr.generate_async.return_value = json.dumps(missing_response)
    
    manifest4 = BuildManifest.create(prompt='cube', model_id='test4')
    manifest4.stage0_output = {"scale_anchor_m": {"overall_height_or_length": 1.0}}
    
    cube = manifest4.add_child_node(
        parent_id=manifest4.root_node_id,
        label="cube",
        kind=NodeKind.PART,
        geometry=GeometrySpec(primitive=PrimitiveType.BOX),
        attachment=AttachmentSpec(socket_type=SocketType.ROOT),
    )
    
    result4 = await Stage2Dimensions.run(
        node=cube,
        manifest=manifest4,
        model_manager=mock_mgr,
        task_id="test",
    )
    
    print("\nStage 2 Output (missing fields defaulted to size_x):")
    print(f"  size_x: {result4.size_x} m")
    print(f"  size_y: {result4.size_y} m (defaulted)")
    print(f"  size_z: {result4.size_z} m (defaulted)")
    
    # =========================================================================
    # TEST 5: Edge Case - Negative values (should use positive defaults)
    # =========================================================================
    print("\n--- TEST 5: Edge Case - Negative/zero values ---")
    print("LLM Input (simulated - invalid values):")
    bad_response = {
        "radius": -0.5,
        "depth": 0,
        "reasoning": "Bad dimensions from confused LLM"
    }
    print(json.dumps(bad_response, indent=2))
    
    mock_mgr.generate_async.return_value = json.dumps(bad_response)
    
    manifest5 = BuildManifest.create(prompt='cylinder', model_id='test5')
    manifest5.stage0_output = {"scale_anchor_m": {"overall_height_or_length": 1.0}}
    
    cyl = manifest5.add_child_node(
        parent_id=manifest5.root_node_id,
        label="cyl",
        kind=NodeKind.PART,
        geometry=GeometrySpec(primitive=PrimitiveType.CYLINDER),
        attachment=AttachmentSpec(socket_type=SocketType.ROOT),
    )
    
    result5 = await Stage2Dimensions.run(
        node=cyl,
        manifest=manifest5,
        model_manager=mock_mgr,
        task_id="test",
    )
    
    print("\nStage 2 Output (invalid values replaced with defaults):")
    print(f"  radius: {result5.radius} m (was -0.5, defaulted to 0.1)")
    print(f"  depth:  {result5.depth} m (was 0, defaulted to 0.2)")
    
    print("\n" + "=" * 60)
    print("ALL STAGE 2 TESTS COMPLETE")
    print("=" * 60)


if __name__ == '__main__':
    asyncio.run(main())
