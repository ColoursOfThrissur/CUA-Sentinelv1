"""Stage 3 Semantics Demo - Show actual output for different socket types."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import sys
sys.path.insert(0, ".")

from core.blender_pipeline.progressive_v2.manifest import BuildManifest, GeometrySpec, AttachmentSpec
from core.blender_pipeline.progressive_v2.node_types import NodeKind, PrimitiveType, SocketType
from core.blender_pipeline.progressive_v2.stages.stage3_semantics import Stage3Semantics, SOCKET_SEMANTICS


def create_mock_manager(response: str):
    """Create mock model manager with given response."""
    manager = MagicMock()
    manager.get_model_for_workflow = MagicMock(return_value="test-model")
    manager.generate_async = AsyncMock(return_value=response)
    return manager


async def demo_corner_socket():
    """Demo CORNER socket semantics (table leg)."""
    print("\n" + "="*60)
    print("CORNER Socket (table leg)")
    print("="*60)
    
    # LLM response for corner position
    llm_response = json.dumps({
        "corner_position": "bottom_front_left"
    })
    
    manager = create_mock_manager(llm_response)
    
    manifest = BuildManifest.create(prompt="table", model_id="test")
    
    # Add tabletop as parent
    tabletop = manifest.add_child_node(
        parent_id=manifest.root_node_id,
        label="tabletop",
        kind=NodeKind.PART,
        geometry=GeometrySpec(primitive=PrimitiveType.BOX),
        attachment=AttachmentSpec(socket_type=SocketType.ROOT),
    )
    
    # Add leg with CORNER socket
    leg = manifest.add_child_node(
        parent_id=tabletop.node_id,
        label="leg_front_left",
        kind=NodeKind.PART,
        geometry=GeometrySpec(primitive=PrimitiveType.CYLINDER),
        attachment=AttachmentSpec(socket_type=SocketType.CORNER),
    )
    
    print(f"Required fields for CORNER: {SOCKET_SEMANTICS[SocketType.CORNER]}")
    print(f"LLM response: {llm_response}")
    
    result = await Stage3Semantics.run(
        node=leg,
        manifest=manifest,
        model_manager=manager,
        task_id="test",
    )
    
    print(f"Parsed semantics: {result}")
    return result


async def demo_through_axis_socket():
    """Demo THROUGH_AXIS socket semantics (axle through wheel)."""
    print("\n" + "="*60)
    print("THROUGH_AXIS Socket (axle through hub)")
    print("="*60)
    
    llm_response = json.dumps({
        "pierce_direction": "left_right",
        "height_hint": "center"
    })
    
    manager = create_mock_manager(llm_response)
    
    manifest = BuildManifest.create(prompt="wheel", model_id="test")
    
    hub = manifest.add_child_node(
        parent_id=manifest.root_node_id,
        label="hub",
        kind=NodeKind.PART,
        geometry=GeometrySpec(primitive=PrimitiveType.CYLINDER),
        attachment=AttachmentSpec(socket_type=SocketType.ROOT),
    )
    
    axle = manifest.add_child_node(
        parent_id=hub.node_id,
        label="axle",
        kind=NodeKind.PART,
        geometry=GeometrySpec(primitive=PrimitiveType.CYLINDER),
        attachment=AttachmentSpec(socket_type=SocketType.THROUGH_AXIS),
    )
    
    print(f"Required fields for THROUGH_AXIS: {SOCKET_SEMANTICS[SocketType.THROUGH_AXIS]}")
    print(f"LLM response: {llm_response}")
    
    result = await Stage3Semantics.run(
        node=axle,
        manifest=manifest,
        model_manager=manager,
        task_id="test",
    )
    
    print(f"Parsed semantics: {result}")
    return result


async def demo_array_member_socket():
    """Demo ARRAY_MEMBER socket semantics (keyboard keys)."""
    print("\n" + "="*60)
    print("ARRAY_MEMBER Socket (keyboard key)")
    print("="*60)
    
    llm_response = json.dumps({
        "array_axis": "x",
        "array_count": 10,
        "array_index": 3,
        "spacing_hint": "tight"
    })
    
    manager = create_mock_manager(llm_response)
    
    manifest = BuildManifest.create(prompt="keyboard", model_id="test")
    
    base = manifest.add_child_node(
        parent_id=manifest.root_node_id,
        label="keyboard_base",
        kind=NodeKind.PART,
        geometry=GeometrySpec(primitive=PrimitiveType.BOX),
        attachment=AttachmentSpec(socket_type=SocketType.ROOT),
    )
    
    key = manifest.add_child_node(
        parent_id=base.node_id,
        label="key_4",
        kind=NodeKind.PART,
        geometry=GeometrySpec(primitive=PrimitiveType.BOX),
        attachment=AttachmentSpec(socket_type=SocketType.ARRAY_MEMBER),
    )
    
    print(f"Required fields for ARRAY_MEMBER: {SOCKET_SEMANTICS[SocketType.ARRAY_MEMBER]}")
    print(f"LLM response: {llm_response}")
    
    result = await Stage3Semantics.run(
        node=key,
        manifest=manifest,
        model_manager=manager,
        task_id="test",
    )
    
    print(f"Parsed semantics: {result}")
    return result


async def demo_relative_to_socket():
    """Demo RELATIVE_TO socket semantics (chair next to table)."""
    print("\n" + "="*60)
    print("RELATIVE_TO Socket (chair next to table)")
    print("="*60)
    
    llm_response = json.dumps({
        "relative_to": "table",
        "direction": "right",
        "gap": "small",
        "align": "same_level"
    })
    
    manager = create_mock_manager(llm_response)
    
    manifest = BuildManifest.create(prompt="desk setup", model_id="test")
    
    table = manifest.add_child_node(
        parent_id=manifest.root_node_id,
        label="table",
        kind=NodeKind.PART,
        geometry=GeometrySpec(primitive=PrimitiveType.BOX),
        attachment=AttachmentSpec(socket_type=SocketType.ROOT),
    )
    
    chair = manifest.add_child_node(
        parent_id=manifest.root_node_id,
        label="chair",
        kind=NodeKind.PART,
        geometry=GeometrySpec(primitive=PrimitiveType.BOX),
        attachment=AttachmentSpec(socket_type=SocketType.RELATIVE_TO),
    )
    
    print(f"Required fields for RELATIVE_TO: {SOCKET_SEMANTICS[SocketType.RELATIVE_TO]}")
    print(f"LLM response: {llm_response}")
    
    result = await Stage3Semantics.run(
        node=chair,
        manifest=manifest,
        model_manager=manager,
        task_id="test",
    )
    
    print(f"Parsed semantics: {result}")
    return result


async def demo_simple_socket_no_llm():
    """Demo simple socket that needs no LLM call."""
    print("\n" + "="*60)
    print("TOP_CENTER Socket (no LLM needed)")
    print("="*60)
    
    manager = MagicMock()
    manager.get_model_for_workflow = MagicMock(return_value="test-model")
    manager.generate_async = AsyncMock()  # Should NOT be called
    
    manifest = BuildManifest.create(prompt="lamp", model_id="test")
    
    base = manifest.add_child_node(
        parent_id=manifest.root_node_id,
        label="base",
        kind=NodeKind.PART,
        geometry=GeometrySpec(primitive=PrimitiveType.CYLINDER),
        attachment=AttachmentSpec(socket_type=SocketType.ROOT),
    )
    
    stem = manifest.add_child_node(
        parent_id=base.node_id,
        label="stem",
        kind=NodeKind.PART,
        geometry=GeometrySpec(primitive=PrimitiveType.CYLINDER),
        attachment=AttachmentSpec(socket_type=SocketType.TOP_CENTER),
    )
    
    print(f"Required fields for TOP_CENTER: {SOCKET_SEMANTICS[SocketType.TOP_CENTER]}")
    print("(Empty list = no LLM call needed)")
    
    result = await Stage3Semantics.run(
        node=stem,
        manifest=manifest,
        model_manager=manager,
        task_id="test",
    )
    
    print(f"Parsed semantics: {result}")
    print(f"LLM called: {manager.generate_async.called}")
    return result


async def demo_invalid_values_defaulted():
    """Demo invalid semantic values being defaulted."""
    print("\n" + "="*60)
    print("Edge Case: Invalid values defaulted")
    print("="*60)
    
    llm_response = json.dumps({
        "corner_position": "invalid_corner",  # Invalid!
        "extra_field": "ignored"
    })
    
    manager = create_mock_manager(llm_response)
    
    manifest = BuildManifest.create(prompt="table", model_id="test")
    
    tabletop = manifest.add_child_node(
        parent_id=manifest.root_node_id,
        label="tabletop",
        kind=NodeKind.PART,
        geometry=GeometrySpec(primitive=PrimitiveType.BOX),
        attachment=AttachmentSpec(socket_type=SocketType.ROOT),
    )
    
    leg = manifest.add_child_node(
        parent_id=tabletop.node_id,
        label="leg",
        kind=NodeKind.PART,
        geometry=GeometrySpec(primitive=PrimitiveType.CYLINDER),
        attachment=AttachmentSpec(socket_type=SocketType.CORNER),
    )
    
    print(f"LLM response (invalid): {llm_response}")
    
    result = await Stage3Semantics.run(
        node=leg,
        manifest=manifest,
        model_manager=manager,
        task_id="test",
    )
    
    print(f"Parsed semantics (defaulted): {result}")
    print(f"corner_position defaulted to: {result.get('corner_position')}")
    return result


async def main():
    print("Stage 3 Semantics Demo")
    print("=" * 60)
    
    await demo_corner_socket()
    await demo_through_axis_socket()
    await demo_array_member_socket()
    await demo_relative_to_socket()
    await demo_simple_socket_no_llm()
    await demo_invalid_values_defaulted()
    
    print("\n" + "="*60)
    print("All Stage 3 demos complete!")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())
