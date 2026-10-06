"""
Decomposer test - runs the full RecursiveDecomposer pipeline with a live Ollama call.
Validates: nested hierarchy, exactly-one-ROOT per assembly, blade count, cage structure.
"""

import asyncio
import sys
import os
import logging

logging.basicConfig(level=logging.WARNING, format='%(levelname)s - %(message)s')

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.blender_pipeline.progressive_v2.decomposer import RecursiveDecomposer
from core.blender_pipeline.progressive_v2.manifest import BuildManifest
from core.blender_pipeline.progressive_v2.hierarchy import HierarchyLimits
from core.blender_pipeline.progressive_v2.node_types import NodeKind, SocketType

PROMPT = (
    "Build a multi-part desk fan. Start with a wide, flattened cylinder for the base. "
    "Attach a thin vertical rod to the exact center of the base. On top of this rod, "
    "place a thicker, horizontal cylinder to act as the motor housing. On the front "
    "circular face of the motor housing, attach a small spherical hub. Radially "
    "distribute exactly four flattened, elongated blades evenly around this hub. "
    "Twist each blade slightly on its own local lengthwise axis so they look angled "
    "to catch air. Finally, enclose the blades and hub completely inside a protective "
    "cage made of several thin, intersecting circular wireframe rings."
)

MODEL_ID = "qwen3:14b-q4_K_M"
OLLAMA_URL = "http://localhost:11434"


class OllamaModelManager:
    """Minimal model manager that calls Ollama directly, matching the real interface."""

    def get_model_for_workflow(self, workflow: str) -> str:
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
        import httpx
        payload = {
            "model": model_id,
            "system": system_prompt,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature},
        }
        async with httpx.AsyncClient(timeout=180) as client:
            r = await client.post(f"{OLLAMA_URL}/api/generate", json=payload)
            r.raise_for_status()
            return r.json().get("response", "")


def print_hierarchy(manifest, node_id=None, indent=0):
    if node_id is None:
        root = manifest.get_root()
        node_id = root.node_id
    node = manifest.nodes[node_id]
    socket = node.attachment.socket_type.value if node.attachment else "?"
    kind_char = {"model": "M", "assembly": "A", "part": "P"}.get(node.kind.value, "?")
    print(f"{'  ' * indent}[{kind_char}] {node.label}  socket={socket}  depth={node.hierarchy_depth}")
    for cid in node.children_ids:
        print_hierarchy(manifest, cid, indent + 1)


def validate(manifest):
    errors = []
    warnings = []

    # 1. Every assembly must have exactly one ROOT child
    for node in manifest.nodes.values():
        if node.kind in (NodeKind.ASSEMBLY, NodeKind.MODEL) and node.children_ids:
            root_children = [
                manifest.nodes[cid] for cid in node.children_ids
                if manifest.nodes[cid].attachment
                and manifest.nodes[cid].attachment.socket_type == SocketType.ROOT
            ]
            if len(root_children) == 0:
                errors.append(f"MISSING ROOT child in '{node.label}'")
            elif len(root_children) > 1:
                errors.append(f"MULTIPLE ROOT children in '{node.label}': {[n.label for n in root_children]}")

    # 2. Depth must be > 1 (not flat)
    max_depth = max(n.hierarchy_depth for n in manifest.nodes.values())
    if max_depth < 2:
        errors.append(f"Hierarchy is flat (max_depth={max_depth}), expected >= 2")

    # 3. Exactly 4 RADIAL parts (blades)
    radial_parts = [
        n for n in manifest.nodes.values()
        if n.kind == NodeKind.PART
        and n.attachment
        and n.attachment.socket_type == SocketType.RADIAL
    ]
    if len(radial_parts) != 4:
        errors.append(f"Expected exactly 4 RADIAL blades, got {len(radial_parts)}: {[n.label for n in radial_parts]}")

    # 4. At least one torus part (cage rings)
    from core.blender_pipeline.progressive_v2.node_types import PrimitiveType
    torus_parts = [
        n for n in manifest.nodes.values()
        if n.kind == NodeKind.PART
        and n.geometry
        and n.geometry.primitive == PrimitiveType.TORUS
    ]
    if not torus_parts:
        warnings.append("No torus parts found (cage rings expected)")

    # 5. At least one sphere part (hub)
    sphere_parts = [
        n for n in manifest.nodes.values()
        if n.kind == NodeKind.PART
        and n.geometry
        and n.geometry.primitive == PrimitiveType.SPHERE
    ]
    if not sphere_parts:
        warnings.append("No sphere part found (hub expected)")

    # 6. All labels unique
    labels = [n.label for n in manifest.nodes.values()]
    dupes = [l for l in labels if labels.count(l) > 1]
    if dupes:
        errors.append(f"Duplicate labels: {list(set(dupes))}")

    return errors, warnings


async def main():
    print("=" * 70)
    print("DECOMPOSER TEST  --  live Ollama call")
    print("=" * 70)
    print(f"Prompt : {PROMPT[:80]}...")
    print(f"Model  : {MODEL_ID}")
    print()

    manifest = BuildManifest.create(PROMPT)
    model_manager = OllamaModelManager()
    limits = HierarchyLimits()
    decomposer = RecursiveDecomposer(limits=limits, max_llm_calls=20)

    print("Calling LLM (may take 30-90s)...")
    stats = await decomposer.decompose(
        manifest=manifest,
        model_manager=model_manager,
        task_id="test_fan",
        model_id=MODEL_ID,
    )

    print(f"\nLLM calls : {stats['llm_calls']}")
    print(f"Nodes     : {stats['total_nodes']}")
    print(f"Max depth : {stats['max_depth_reached']}")

    print("\n--- Hierarchy ---")
    print_hierarchy(manifest)

    print("\n--- Validation ---")
    errors, warnings = validate(manifest)

    for w in warnings:
        print(f"  WARN  {w}")
    for e in errors:
        print(f"  FAIL  {e}")

    if not errors and not warnings:
        print("  PASS  All checks passed")
    elif not errors:
        print(f"  PASS  No errors ({len(warnings)} warning(s))")
    else:
        print(f"\n  {len(errors)} error(s), {len(warnings)} warning(s)")

    print("\n--- Node table ---")
    print(f"{'label':<38} {'kind':<10} {'socket':<18} {'depth'}")
    print("-" * 72)
    for node in manifest.nodes.values():
        socket = node.attachment.socket_type.value if node.attachment else "-"
        print(f"{node.label:<38} {node.kind.value:<10} {socket:<18} {node.hierarchy_depth}")


if __name__ == "__main__":
    asyncio.run(main())
