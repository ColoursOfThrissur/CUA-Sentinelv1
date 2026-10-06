"""Real LLM test for the staged Blender pipeline.

Run from backend directory:
    python scripts/test_staged_pipeline.py "a training dummy for martial arts"

This bypasses the old GraphCompiler and tests the new staged pipeline directly.
"""

import asyncio
import sys
import json
import logging
from pathlib import Path

# Fix Windows console encoding
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.blender_pipeline import StagedPipelineOrchestrator
from core.assembly_spec import graph_to_blender_steps

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


async def test_staged_pipeline(prompt: str, execute_in_blender: bool = False):
    """Test the staged pipeline with a real LLM.
    
    Args:
        prompt: Object description
        execute_in_blender: If True, also execute the build in Blender via MCP
    """
    print("\n" + "=" * 70)
    print("STAGED PIPELINE TEST - Real LLM")
    print("=" * 70)
    print(f"Prompt: {prompt}")
    print("=" * 70 + "\n")
    
    # Load config and initialize model manager properly
    from config.loader import load_system_config, load_model_registry
    from core.model_manager import ModelManager
    
    config = load_system_config()
    registry = load_model_registry()
    model_manager = ModelManager(config, registry)
    
    # Run the staged pipeline
    print("[1/5] Running staged pipeline...\n")
    
    result = await StagedPipelineOrchestrator.run(
        prompt=prompt,
        model_manager=model_manager,
        task_id="test_staged",
    )
    
    # Report results for each stage
    print("\n" + "-" * 70)
    print("STAGE OUTPUTS")
    print("-" * 70)
    
    if result.stage0_output:
        print("\n[Stage 0 - Understanding]")
        print(f"  Category: {result.stage0_output.get('category')}")
        print(f"  Rests on surface: {result.stage0_output.get('rests_on_surface')}")
        print(f"  Style: {result.stage0_output.get('style_tag')}")
        scale = result.stage0_output.get('scale_anchor_m', {})
        print(f"  Scale anchor: {scale.get('overall_height_or_length')}m")
        print(f"  Scale reasoning: {scale.get('reasoning', 'N/A')[:80]}...")
    
    if result.stage1_output:
        print("\n[Stage 1 - Topology]")
        parts = result.stage1_output.get('parts', [])
        print(f"  Parts ({len(parts)}):")
        for p in parts:
            parent = p.get('parent_label') or 'ROOT'
            print(f"    - {p['label']}: {p['primitive_type']} -> {p['socket_type']} (parent: {parent})")
    
    if result.stage2_output:
        print("\n[Stage 2 - Dimensions]")
        parts = result.stage2_output.get('parts', [])
        for p in parts:
            dims = p.get('dimensions', {})
            if dims.get('size'):
                dim_str = f"size={dims['size']}"
            elif dims.get('radius') and dims.get('depth'):
                dim_str = f"r={dims['radius']:.3f}m, d={dims['depth']:.3f}m"
            elif dims.get('radius'):
                dim_str = f"r={dims['radius']:.3f}m"
            else:
                dim_str = str(dims)
            print(f"    - {p['label']}: {dim_str}")
    
    if result.stage3_output:
        print("\n[Stage 3 - Semantics]")
        parts = result.stage3_output.get('parts', [])
        for p in parts:
            extras = []
            if p.get('pierce_direction'):
                extras.append(f"pierce={p['pierce_direction']}")
            if p.get('height_hint'):
                extras.append(f"height={p['height_hint']}")
            if p.get('connects_to'):
                extras.append(f"connects_to={p['connects_to']}")
            if p.get('radial_count'):
                extras.append(f"radial={p['radial_index']}/{p['radial_count']}")
            extra_str = f" ({', '.join(extras)})" if extras else ""
            print(f"    - {p['label']}: {p['socket_type']}{extra_str}")
    
    print("\n" + "-" * 70)
    
    if not result.success:
        print(f"\n[FAILED] PIPELINE FAILED at Stage {result.failed_stage}")
        print(f"   Error: {result.error}")
        return None
    
    print("\n[OK] PIPELINE SUCCEEDED")
    
    # Show the generated graph
    graph = result.graph
    print(f"\n[Stage 4 - AssemblyGraph]")
    print(f"  Task ID: {graph.task_id}")
    print(f"  Rests on surface: {graph.rests_on_surface}")
    print(f"  Total nodes: {len(graph.root.all_nodes())}")
    
    print("\n  Node tree:")
    def print_node(node, indent=0):
        offset = node.attachment.local_offset
        rot = node.attachment.local_rotation_euler
        rot_deg = tuple(round(r * 57.2958, 1) for r in rot)
        print(f"{'  ' * indent}  - {node.label}: offset={offset}, rot_deg={rot_deg}")
        for child in node.children:
            print_node(child, indent + 1)
    
    print_node(graph.root)
    
    # Convert to Blender steps
    print("\n[Blender Steps]")
    steps = graph_to_blender_steps(graph)
    print(f"  Total steps: {len(steps)}")
    for i, (tool, args) in enumerate(steps[:10]):  # Show first 10
        args_short = {k: v for k, v in args.items() if k != 'code'}
        print(f"    {i+1}. {tool}: {args_short}")
    if len(steps) > 10:
        print(f"    ... and {len(steps) - 10} more steps")
    
    # Optionally execute in Blender
    if execute_in_blender:
        print("\n" + "-" * 70)
        print("EXECUTING IN BLENDER")
        print("-" * 70)
        
        try:
            from core.mcp_manager import MCPManager
            from core.blender_pipeline.executor import execute_assembly_graph
            
            mcp = MCPManager()
            mcp.initialize_from_config()
            
            # Use the new executor
            exec_result = await execute_assembly_graph(graph, mcp, task_id="test_staged")
            
            if exec_result.get("ok"):
                print(f"\n[OK] BUILD COMPLETE")
                print(f"  Executed: {exec_result.get('executed_steps')}/{exec_result.get('total_steps')} steps")
                if exec_result.get("verification"):
                    v = exec_result["verification"]
                    if v.get("ok"):
                        print(f"  Verification: PASSED")
                    else:
                        print(f"  Verification: FAILED - {v.get('error')}")
            else:
                print(f"\n[FAILED] Execution failed")
                print(f"  Errors: {exec_result.get('errors')}")
            
        except Exception as e:
            print(f"\n[FAILED] Blender execution failed: {e}")
            import traceback
            traceback.print_exc()
    
    return graph


async def main():
    # Default test prompts
    test_prompts = {
        "dummy": "a training dummy for martial arts with a horizontal arm passing through the post, a strike shield on the left end and a counterweight ball on the right",
        "arcade": "an arcade cabinet with a screen, control panel with joystick and three buttons",
        "tower": "a communication tower with a central pillar, radar dish on top, and four support struts connecting the pillar to the dish",
        "mug": "a coffee mug with a handle",
    }
    
    # Parse args
    if len(sys.argv) < 2:
        print("Usage: python test_staged_pipeline.py <prompt or shortcut>")
        print("\nShortcuts:")
        for k, v in test_prompts.items():
            print(f"  {k}: {v[:60]}...")
        print("\nOptions:")
        print("  --build    Also execute in Blender via MCP")
        sys.exit(1)
    
    prompt = sys.argv[1]
    execute = "--build" in sys.argv
    
    # Check for shortcut
    if prompt in test_prompts:
        prompt = test_prompts[prompt]
    
    await test_staged_pipeline(prompt, execute_in_blender=execute)


if __name__ == "__main__":
    asyncio.run(main())
