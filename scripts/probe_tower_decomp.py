"""
Probe script: send the sci-fi communication tower prompt through
DECOMPOSITION_SYSTEM_PROMPT and print exactly what the LLM returns,
what JSON is extracted, and what Blender steps graph_to_blender_steps emits.

Run from repo root:
    .venv\Scripts\python scripts\probe_tower_decomp.py
"""

import asyncio
import json
import sys
import os

# Make backend importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from core.graph_compiler import GraphCompiler, DECOMPOSITION_SYSTEM_PROMPT
from core.assembly_spec import graph_to_blender_steps

TOWER_PROMPT = (
    "Build a sci-fi communication tower. "
    "Start with a wide, flat cylindrical base (radius=15, depth=3). "
    "Place a taller, thinner hexagonal pillar (vertices=6, radius=3, depth=30) "
    "standing upright in the exact center of the base. "
    "On top of this pillar, attach a large, shallow hemisphere (radius=8) "
    "facing upwards as the main radar dish. "
    "Place a thin, pointed antenna (cone, radius1=0.3, depth=12) "
    "sticking straight up from the center of the dish. "
    "Finally, create four angled support struts (cylinder, radius=0.4, depth=9.43 each) "
    "connecting the outer rim of the dish down to the sides of the hexagonal pillar — "
    "one at +X (local_offset=[5.5,0,19], rotation=[0,-32,0]), "
    "one at -X (local_offset=[-5.5,0,19], rotation=[0,32,0]), "
    "one at +Y (local_offset=[0,5.5,19], rotation=[32,0,0]), "
    "one at -Y (local_offset=[0,-5.5,19], rotation=[-32,0,0]). "
    "Parent all struts to the pillar."
)

SEP = "=" * 70


async def main():
    # ── 1. Call Ollama directly ──────────────────────────────────────────────
    try:
        import httpx
        print(SEP)
        print("STEP 1 — Raw LLM response (Ollama /api/generate)")
        print(SEP)

        payload = {
            "model": "qwen3:14b-q4_K_M",
            "system": DECOMPOSITION_SYSTEM_PROMPT,
            "prompt": TOWER_PROMPT,
            "stream": False,
            "options": {"temperature": 0.1},
        }
        async with httpx.AsyncClient(timeout=300) as client:
            r = await client.post("http://localhost:11434/api/generate", json=payload)
            r.raise_for_status()
            raw_response = r.json().get("response", "")

        print(raw_response)

    except Exception as e:
        print(f"[ERROR] Could not reach Ollama: {e}")
        print("Make sure Ollama is running and qwen3:14b-q4_K_M is pulled.")
        return

    # ── 2. Extract JSON ──────────────────────────────────────────────────────
    print()
    print(SEP)
    print("STEP 2 — Extracted JSON (GraphCompiler._extract_json)")
    print(SEP)
    decomp = GraphCompiler._extract_json(raw_response)
    if decomp:
        print(json.dumps(decomp, indent=2))
    else:
        print("[FAILED] No valid JSON found in LLM response.")
        return

    # ── 3. Build AssemblyGraph (no DimensionResolver, no model_manager) ─────
    print()
    print(SEP)
    print("STEP 3 — AssemblyGraph nodes")
    print(SEP)
    if "root" not in decomp:
        print("[FAILED] JSON has no 'root' key.")
        return

    graph = GraphCompiler._build_graph_from_decomp(decomp, TOWER_PROMPT, "probe_001")
    print(f"rests_on_surface : {graph.rests_on_surface}")
    print(f"root label       : {graph.root.label}")
    print(f"root sub_spec    : {graph.root.sub_spec}")
    print(f"root offset      : {graph.root.attachment.local_offset}")
    print()

    def _print_tree(node, indent=0):
        rot_deg = [round(__import__('math').degrees(r), 2) for r in node.attachment.local_rotation_euler]
        print(
            "  " * indent
            + f"[{node.label}]  primitive={node.sub_spec.get('primitive')}  "
            + f"offset={[round(x,3) for x in node.attachment.local_offset]}  "
            + f"rot_deg={rot_deg}"
        )
        for child in node.children:
            _print_tree(child, indent + 1)

    _print_tree(graph.root)

    # ── 4. Blender steps ─────────────────────────────────────────────────────
    print()
    print(SEP)
    print("STEP 4 — graph_to_blender_steps output")
    print(SEP)
    steps = graph_to_blender_steps(graph)
    for i, (tool, args) in enumerate(steps, 1):
        print(f"  [{i:02d}] {tool}")
        for k, v in args.items():
            print(f"        {k}: {v}")
        print()

    # ── 5. Strut angle audit ─────────────────────────────────────────────────
    print(SEP)
    print("STEP 5 - Strut angle audit (expected rot ~+/-32 deg on X or Y)")
    print(SEP)
    strut_steps = [(t, a) for t, a in steps if "strut" in a.get("name", "").lower()]
    if not strut_steps:
        print("[WARN] No strut steps found — check label names above.")
    for tool, args in strut_steps:
        rot = args.get("rotation", [0, 0, 0])
        loc = args.get("location", [0, 0, 0])
        print(f"  {args['name']:20s}  loc={[round(x,2) for x in loc]}  rot={[round(r,2) for r in rot]}")

    print()
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
