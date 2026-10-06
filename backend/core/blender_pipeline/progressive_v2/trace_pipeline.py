"""
Pipeline trace - runs each stage in order, prints real LLM input/output.

Usage:
    cd backend
    python -m core.blender_pipeline.progressive_v2.trace_pipeline

Requires Ollama running with a model available.
Edit PROMPT and MODEL_ID below before running.
"""

import asyncio
import json
import sys
import os
import logging

# -- Config -------------------------------------------------------------------
# Test case with desk fan to test hierarchy fix
PROMPT   = "Build a multi-part desk fan. Start with a wide, flattened cylinder for the base. Attach a thin vertical rod to the exact center of the base. On top of this rod, place a thicker, horizontal cylinder to act as the motor housing. On the front circular face of the motor housing, attach a small spherical hub. Radially distribute exactly four flattened, elongated blades evenly around this hub. Twist each blade slightly on its own local lengthwise axis so they look angled to catch air. Finally, enclose the blades and hub completely inside a protective cage made of several thin, intersecting circular wireframe rings."
MODEL_ID = "qwen3:14b-q4_K_M"
OLLAMA_URL = "http://localhost:11434"
# -----------------------------------------------------------------------------

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)


# -- Minimal model_manager shim -----------------------------------------------
import httpx

class _OllamaManager:
    """Thin shim - calls Ollama /api/generate directly."""

    def get_model_for_workflow(self, _workflow: str) -> str:
        return MODEL_ID

    async def generate_async(
        self,
        model_id: str,
        task_id: str,
        lease_id: str,
        lease_generation: int,
        system_prompt: str,
        prompt: str,
        temperature: float = 0.4,
    ) -> str:
        payload = {
            "model": model_id,
            "prompt": f"{system_prompt}\n\n{prompt}",
            "stream": False,
            "options": {"temperature": temperature},
        }
        async with httpx.AsyncClient(timeout=300) as client:
            r = await client.post(f"{OLLAMA_URL}/api/generate", json=payload)
            r.raise_for_status()
            return r.json()["response"]


# -- Helpers ------------------------------------------------------------------

def _sep(title: str) -> None:
    print(f"\n{'='*70}")
    print(f"  {title}")
    print('='*70)

def _print_hierarchy(manifest) -> None:
    print(manifest.print_hierarchy())

def _print_nodes_table(manifest) -> None:
    print(f"{'label':<35} {'kind':<10} {'socket':<18} {'state':<12} depth")
    print("-"*85)
    for node in manifest.nodes.values():
        socket = node.attachment.socket_type.value if node.attachment else "-"
        print(f"{node.label:<35} {node.kind.value:<10} {socket:<18} {node.state.value:<12} {node.hierarchy_depth}")

def _print_dag_edges(dag, manifest) -> None:
    from .dag import DependencyType
    counts = {}
    for dep in dag._dependencies.values():
        counts[dep.dep_type.value] = counts.get(dep.dep_type.value, 0) + 1

    print(f"Total edges: {dag.edge_count}")
    for dtype, cnt in sorted(counts.items()):
        print(f"  {dtype:<25} {cnt}")

    print("\nEdge list (from -> to  [type]):")
    for dep in sorted(dag._dependencies.values(), key=lambda d: d.dep_type.value):
        from_node = manifest.nodes.get(dep.from_node)
        to_node   = manifest.nodes.get(dep.to_node)
        fn = from_node.label if from_node else dep.from_node[:12]
        tn = to_node.label   if to_node   else dep.to_node[:12]
        print(f"  {fn:<30} ->  {tn:<30}  [{dep.dep_type.value}]")


# -- Stage runners ------------------------------------------------------------

async def run_step1_decompose(manifest, model_manager):
    """Step 1 - Decomposer: LLM call -> hierarchy."""
    from .decomposer import RecursiveDecomposer
    from .hierarchy import HierarchyLimits

    limits = HierarchyLimits(max_depth=60, max_total_nodes=2000, max_children=200)
    decomposer = RecursiveDecomposer(limits=limits, max_llm_calls=30)

    _sep("STEP 1 - DECOMPOSER")
    print(f"Prompt : {PROMPT}")
    print(f"Model  : {MODEL_ID}\n")
    print("Calling LLM... (this may take 30-90s)")

    # Patch generate_async to print raw LLM response
    _orig_generate = model_manager.generate_async
    _call_count = [0]
    async def _traced_generate(*args, **kwargs):
        result = await _orig_generate(*args, **kwargs)
        _call_count[0] += 1
        print(f"\n--- RAW LLM RESPONSE (call {_call_count[0]}) ---")
        print(result[:3000])
        if len(result) > 3000:
            print(f"... [{len(result)-3000} more chars truncated]")
        print("--- END RAW RESPONSE ---\n")
        return result
    model_manager.generate_async = _traced_generate

    stats = await decomposer.decompose(
        manifest=manifest,
        model_manager=model_manager,
        task_id="trace",
        model_id=MODEL_ID,
    )
    model_manager.generate_async = _orig_generate

    print(f"\nLLM calls made : {stats['llm_calls']}")
    print(f"Nodes created  : {stats['nodes_created']}")
    print(f"Max depth      : {stats['max_depth_reached']}")
    if stats.get("decomposition_stopped_reasons"):
        print(f"Stop reasons   : {stats['decomposition_stopped_reasons']}")

    print("\n--- Hierarchy ---")
    _print_hierarchy(manifest)

    print("\n--- Node table ---")
    _print_nodes_table(manifest)

    return stats


async def run_step2_dag(manifest):
    """Step 2 - DAG: build dependency graph from manifest."""
    from .dag import DependencyDAG

    _sep("STEP 2 - DEPENDENCY DAG")
    dag = DependencyDAG.from_manifest(manifest)

    _print_dag_edges(dag, manifest)

    missing = dag.get_missing_targets()
    if missing:
        print(f"\nWARN: MISSING cross-reference targets ({len(missing)}):")
        for node_id, label in missing:
            node = manifest.nodes.get(node_id)
            print(f"  {node.label if node else node_id} -> '{label}' NOT FOUND in manifest")
    else:
        print("\nOK: All cross-reference targets resolved.")

    return dag


async def run_step3_stage2(manifest, model_manager, dag):
    """Step 3 - Stage 2 (dimensions) for every PART node."""
    from .stages import Stage2Dimensions
    from .node_types import NodeKind
    from .manifest import NodeState

    _sep("STEP 3 - STAGE 2: DIMENSIONS")

    parts = [n for n in manifest.nodes.values() if n.kind == NodeKind.PART]
    print(f"Running Stage 2 for {len(parts)} PART nodes...\n")

    for node in parts:
        if node.state == NodeState.PLANNED:
            manifest.transition(node.node_id, NodeState.READY)

        try:
            output = await Stage2Dimensions.run(
                node=node,
                manifest=manifest,
                model_manager=model_manager,
                task_id="trace",
                model_id=MODEL_ID,
            )
        except Exception as e:
            print(f"  {node.label:<35} *** Stage2Error: {e} -- using fallback dims")
            from .stages.stage2_dimensions import DimensionsOutput
            from .node_types import PrimitiveType
            output = DimensionsOutput(reasoning=f"fallback: {e}")
            prim = node.geometry.primitive if node.geometry else None
            if prim == PrimitiveType.TORUS:
                output.major_radius, output.minor_radius = 0.18, 0.01
            elif prim == PrimitiveType.CYLINDER:
                output.radius, output.depth = 0.05, 0.1
            elif prim == PrimitiveType.SPHERE:
                output.radius = 0.05
            else:
                output.size_x = output.size_y = output.size_z = 0.1

        node.stage_outputs["stage2"] = output.to_dict()
        if node.geometry:
            output.apply_to_geometry(node.geometry)

        dims = {k: v for k, v in output.to_dict().items() if k != "reasoning"}
        print(f"  {node.label:<35} {dims}")

    print("\nDone.")


async def run_step4_stage3(manifest, model_manager):
    """Step 4 - Stage 3 (semantics) for every PART node."""
    from .stages import Stage3Semantics
    from .node_types import NodeKind

    _sep("STEP 4 - STAGE 3: SEMANTICS")

    parts = [n for n in manifest.nodes.values() if n.kind == NodeKind.PART]
    print(f"Running Stage 3 for {len(parts)} PART nodes...\n")

    for node in parts:
        semantics = await Stage3Semantics.run(
            node=node,
            manifest=manifest,
            model_manager=model_manager,
            task_id="trace",
            model_id=MODEL_ID,
        )
        node.stage_outputs["stage3"] = semantics
        Stage3Semantics.apply_to_attachment(node.attachment, semantics)

        socket = node.attachment.socket_type.value
        if semantics:
            print(f"  {node.label:<35} socket={socket:<18} hints={semantics}")
        else:
            print(f"  {node.label:<35} socket={socket:<18} (no hints needed)")

    print("\nDone.")


def run_step5_stage4(manifest, dag):
    """Step 5 - Stage 4 (transforms) for every PART node."""
    from .stages import Stage4Resolver
    from .stages.stage4_resolver import BBox, AttachmentSolution
    from .transforms import WorldMatrix, LocalTransform
    from .node_types import NodeKind
    from .manifest import NodeState

    _sep("STEP 5 - STAGE 4: TRANSFORMS")

    parts = [n for n in manifest.nodes.values() if n.kind == NodeKind.PART]
    print(f"Running Stage 4 for {len(parts)} PART nodes...\n")

    errors = []

    for node in parts:
        socket = node.attachment.socket_type if node.attachment else None
        is_cross = Stage4Resolver.is_cross_reference_socket(socket) if socket else False

        try:
            if is_cross:
                transform, solution = Stage4Resolver.run(node, manifest)
                node.stage_outputs["stage4"] = transform.to_dict()
                node.attachment.local_offset   = transform.offset
                node.attachment.local_rotation = transform.rotation
                if node.transform_state:
                    node.transform_state.set_local_transform(solution.local_transform)

                world_matrices = {}
                world_bboxes   = {}
                for n in manifest.nodes.values():
                    if n.transform_state and n.transform_state.world_matrix is not None:
                        world_matrices[n.node_id] = n.transform_state.world_matrix
                    if n.bounding_box:
                        bb = n.bounding_box
                        world_bboxes[n.node_id] = BBox(
                            min_x=bb["min"][0], max_x=bb["max"][0],
                            min_y=bb["min"][1], max_y=bb["max"][1],
                            min_z=bb["min"][2], max_z=bb["max"][2],
                        )

                transform, solution = Stage4Resolver.resolve_cross_reference(
                    node, manifest, world_matrices, world_bboxes
                )
                method = f"pass2:{transform.resolution_method}"
            else:
                transform, solution = Stage4Resolver.run(node, manifest)
                method = transform.resolution_method

            node.stage_outputs["stage4"] = transform.to_dict()
            node.attachment.local_offset   = transform.offset
            node.attachment.local_rotation = transform.rotation
            if node.transform_state:
                node.transform_state.set_local_transform(solution.local_transform)

            pos = [round(x, 4) for x in transform.offset]
            rot = [round(x, 4) for x in transform.rotation]
            print(f"  {node.label:<35} method={method:<35} pos={pos}  rot={rot}")

        except Exception as e:
            errors.append((node.label, str(e)))
            print(f"  {node.label:<35} *** ERROR: {e}")

    if errors:
        print(f"\nWARN: {len(errors)} Stage 4 errors:")
        for label, err in errors:
            print(f"  {label}: {err}")
    else:
        print("\nOK: All Stage 4 transforms resolved.")

    return errors


# -- Main ---------------------------------------------------------------------

async def main():
    from .manifest import BuildManifest

    model_manager = _OllamaManager()
    manifest = BuildManifest.create(PROMPT)

    await run_step1_decompose(manifest, model_manager)
    dag = await run_step2_dag(manifest)
    await run_step3_stage2(manifest, model_manager, dag)
    await run_step4_stage3(manifest, model_manager)
    stage4_errors = run_step5_stage4(manifest, dag)

    _sep("SUMMARY")
    _print_nodes_table(manifest)
    print(f"\nStage 4 errors: {len(stage4_errors)}")
    print(f"Total LLM calls: {manifest.stats.get('total_llm_calls', 0)}")


if __name__ == "__main__":
    asyncio.run(main())
