"""Demo script to show actual decomposition output."""
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

from core.blender_pipeline.progressive_v2.decomposer import RecursiveDecomposer
from core.blender_pipeline.progressive_v2.manifest import BuildManifest
from core.blender_pipeline.progressive_v2.hierarchy import HierarchyLimits


async def main():
    # Setup mock model manager
    mock_mgr = MagicMock()
    mock_mgr.get_model_for_workflow = MagicMock(return_value='test-model')
    mock_mgr.generate_async = AsyncMock()
    
    # Simulated LLM response - nested desk lamp hierarchy
    llm_response = json.dumps({
        'is_simple': False,
        'children': [
            {
                'label': 'base_assembly',
                'kind': 'assembly',
                'socket_type': 'ROOT',
                'children': [
                    {'label': 'base', 'kind': 'part', 'primitive': 'cylinder', 'socket_type': 'ROOT'},
                    {
                        'label': 'stem_assembly',
                        'kind': 'assembly',
                        'socket_type': 'TOP_CENTER',
                        'children': [
                            {'label': 'stem', 'kind': 'part', 'primitive': 'cylinder', 'socket_type': 'ROOT'},
                            {'label': 'shade', 'kind': 'part', 'primitive': 'cone', 'socket_type': 'TOP_CENTER'}
                        ]
                    }
                ]
            }
        ]
    })
    
    mock_mgr.generate_async.return_value = llm_response
    
    # Create manifest and run decomposition
    manifest = BuildManifest.create(prompt='desk lamp', model_id='test')
    decomposer = RecursiveDecomposer(limits=HierarchyLimits())
    
    stats = await decomposer.decompose(
        manifest=manifest,
        model_manager=mock_mgr,
        task_id='test',
    )
    
    # Print results
    print('=== DECOMPOSITION STATS ===')
    print(f'Total nodes: {stats["total_nodes"]}')
    print(f'LLM calls: {stats["llm_calls"]}')
    print(f'Max depth: {stats["max_depth_reached"]}')
    print()
    print('=== HIERARCHY ===')
    print(manifest.print_hierarchy())
    print()
    print('=== NODE DETAILS ===')
    for nid, node in manifest.nodes.items():
        prim = node.geometry.primitive.value if node.geometry else 'N/A'
        socket = node.attachment.socket_type.value if node.attachment else 'N/A'
        print(f'{node.label:20} kind={node.kind.value:10} depth={node.hierarchy_depth} prim={prim:10} socket={socket}')


if __name__ == '__main__':
    asyncio.run(main())
