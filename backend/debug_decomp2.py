"""
Trace _decompose_node calls by monkey-patching the decomposer.
Run from backend/ directory.
"""
import asyncio
import sys
import json
import logging

logging.basicConfig(level=logging.DEBUG, stream=sys.stdout,
                    format='%(levelname)s %(name)s: %(message)s')

sys.path.insert(0, '.')

from core.blender_pipeline.progressive_v2 import decomposer as decomp_mod
from core.blender_pipeline.progressive_v2.decomposer import RecursiveDecomposer
from core.blender_pipeline.progressive_v2.manifest import BuildManifest, NodeState
from core.blender_pipeline.progressive_v2.hierarchy import HierarchyLimits

# Patch _decompose_node to trace calls
original_decompose_node = RecursiveDecomposer._decompose_node

async def traced_decompose_node(self, node, manifest, tree, model_manager, task_id, model_id, stats, pre_parsed_children=None):
    print(f'>>> _decompose_node: {node.label} (depth={node.hierarchy_depth}, state={node.state.value}, pre_parsed={pre_parsed_children is not None})', flush=True)
    children_before = len(manifest.nodes)
    await original_decompose_node(self, node, manifest, tree, model_manager, task_id, model_id, stats, pre_parsed_children)
    children_after = len(manifest.nodes)
    print(f'<<< _decompose_node: {node.label} -> added {children_after - children_before} nodes, node.children_ids={manifest.nodes[node.node_id].children_ids}', flush=True)

RecursiveDecomposer._decompose_node = traced_decompose_node

# Patch commit_decomposition to trace calls
from core.blender_pipeline.progressive_v2.manifest import BuildManifest as BM
original_commit = BM.commit_decomposition

def traced_commit(self, parent_id, children_specs):
    parent = self.nodes[parent_id]
    labels = [s['label'] for s in children_specs]
    print(f'  commit_decomposition: parent={parent.label}, labels={labels}', flush=True)
    try:
        result = original_commit(self, parent_id, children_specs)
        print(f'  commit_decomposition: SUCCESS, created {len(result)} nodes', flush=True)
        return result
    except ValueError as e:
        print(f'  commit_decomposition: FAILED: {e}', flush=True)
        raise

BM.commit_decomposition = traced_commit

# Fake model manager that returns the saved LLM response
with open('data/builds_v2/m_8433a0439d/llm_log.json') as f:
    llm_log = json.load(f)

saved_response = llm_log[0]['response']

class FakeModelManager:
    def get_model_for_workflow(self, workflow):
        return 'fake'
    async def generate_async(self, **kwargs):
        print(f'  LLM call for: {kwargs.get("prompt", "")[:60]}', flush=True)
        return saved_response

async def main():
    manifest = BuildManifest.create('Build a multi-part desk fan. Start with a wide, flattened cylinder for the base. Attach a thin vertical rod to the exact center of the base. On top of this rod, place a thicker, horizontal cylinder to act as the motor housing. On the front circular face of the motor housing, attach a small spherical hub. Radially distribute exactly four flattened, elongated blades evenly around this hub. Twist each blade slightly on its own local lengthwise axis so they look angled to catch air. Finally, enclose the blades and hub completely inside a protective cage made of several thin, intersecting circular wireframe rings.')
    
    decomposer = RecursiveDecomposer(limits=HierarchyLimits(), max_llm_calls=20)
    stats = await decomposer.decompose(
        manifest=manifest,
        model_manager=FakeModelManager(),
        task_id='debug',
        model_id='fake',
    )
    
    print(f'\n=== RESULT: {len(manifest.nodes)} nodes ===', flush=True)
    for nid, node in manifest.nodes.items():
        print(f'  {node.label} (depth={node.hierarchy_depth}, children={len(node.children_ids)})', flush=True)

asyncio.run(main())
