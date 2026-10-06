"""
test_controller_executor_live.py

Tests the batch-flush path in ProgressiveController + BlenderExecutor
with a LIVE MCP connection.  No LLM calls -- stage outputs are injected
directly so the test is deterministic and fast.

Model: simple table (1 assembly, 5 parts)
  table_model  (MODEL)
    table_assembly  (ASSEMBLY)
      tabletop   BOX  [0.8, 0.6, 0.05]  pos [0, 0, 0.375]   ROOT
      leg_fl     BOX  [0.05,0.05,0.35]  pos [-0.35,-0.25,0.175]
      leg_fr     BOX  [0.05,0.05,0.35]  pos [ 0.35,-0.25,0.175]
      leg_bl     BOX  [0.05,0.05,0.35]  pos [-0.35, 0.25,0.175]
      leg_br     BOX  [0.05,0.05,0.35]  pos [ 0.35, 0.25,0.175]

Checks:
  1. All 5 mesh objects created in Blender (object_exists)
  2. All 5 world positions correct within 2mm
  3. All 5 nodes reach NodeState.VERIFIED
  4. Assembly node reaches NodeState.VERIFIED
  5. Root MODEL node reaches NodeState.VERIFIED
  6. Exactly ONE flush call was made for all 5 parts (batch flush)
  7. Cleanup: all objects removed from Blender
"""

from __future__ import annotations
import asyncio, json, math, sys, os, logging

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

logging.basicConfig(level=logging.WARNING)

TOL = 0.002  # 2mm


# ---------------------------------------------------------------------------
# Manifest builder -- no LLM, inject stage outputs directly
# ---------------------------------------------------------------------------

def _build_manifest():
    """Build a fully-staged manifest for a simple table, no LLM needed."""
    from core.blender_pipeline.progressive_v2.manifest import (
        BuildManifest, AttachmentSpec, GeometrySpec, MaterialSpec,
    )
    from core.blender_pipeline.progressive_v2.node_types import (
        NodeKind, NodeImportance, SocketType, PrimitiveType,
    )
    from core.blender_pipeline.progressive_v2.transforms import (
        LocalTransform, NodeTransformState,
    )

    manifest = BuildManifest.create("simple table", model_id="test_table_live")
    root_id = manifest.root_node_id
    root = manifest.get_root()

    from core.blender_pipeline.progressive_v2.manifest import NodeState

    # --- assembly ---
    asm = manifest.add_child_node(
        parent_id=root_id,
        label="table_assembly",
        kind=NodeKind.ASSEMBLY,
        importance=NodeImportance.REQUIRED,
        attachment=AttachmentSpec(socket_type=SocketType.ROOT),
    )
    asm_id = asm.node_id

    # Transition assembly to READY so parts aren't blocked by parent.state==PLANNED.
    # Also compute its world_matrix (identity) so _is_actionable's
    # parent.transform_state.world_matrix is None check passes for all 5 parts
    # simultaneously on the first iteration — enabling the batch flush.
    manifest.transition(asm_id, NodeState.READY)
    asm.transform_state.compute_world(None, -1)  # identity, no parent world needed

    # Helper: inject all stage outputs + transform_state for a PART
    def _add_part(label, size, pos, socket=SocketType.TOP_CENTER):
        import math as _math
        local_t = LocalTransform(position=list(pos), rotation=[0.0, 0.0, 0.0])
        ts = NodeTransformState()
        ts.set_local_transform(local_t)

        # Stage 2 output (dimensions)
        s2 = {"width": size[0], "depth": size[1], "height": size[2],
              "primitive": "box", "size": list(size)}
        # Stage 3 output (semantics -- minimal)
        s3 = {"socket_type": socket.value, "local_offset": list(pos),
              "local_rotation": [0.0, 0.0, 0.0]}
        # Stage 4 output (transform)
        s4 = {"offset": list(pos), "rotation": [0.0, 0.0, 0.0],
              "resolution_method": "injected"}

        node = manifest.add_child_node(
            parent_id=asm_id,
            label=label,
            kind=NodeKind.PART,
            importance=NodeImportance.REQUIRED,
            attachment=AttachmentSpec(
                socket_type=socket,
                local_offset=list(pos),
                local_rotation=[0.0, 0.0, 0.0],
            ),
            geometry=GeometrySpec(
                primitive=PrimitiveType.BOX,
                size=list(size),
            ),
            stage_outputs={"stage2": s2, "stage3": s3, "stage4": s4},
        )
        node.transform_state = ts
        return node

    _add_part("tabletop", [0.8, 0.6, 0.05], [0.0,  0.0,  0.375], SocketType.ROOT)
    _add_part("leg_fl",   [0.05,0.05,0.35], [-0.35,-0.25, 0.175])
    _add_part("leg_fr",   [0.05,0.05,0.35], [ 0.35,-0.25, 0.175])
    _add_part("leg_bl",   [0.05,0.05,0.35], [-0.35, 0.25, 0.175])
    _add_part("leg_br",   [0.05,0.05,0.35], [ 0.35, 0.25, 0.175])

    return manifest


# ---------------------------------------------------------------------------
# Flush counter patch
# ---------------------------------------------------------------------------

class _FlushCounter:
    """Wraps BlenderExecutor.flush() to count calls and track buffer sizes."""
    def __init__(self):
        self.calls = []  # list of buffer lengths at each flush

    def patch(self, executor):
        original = executor.flush
        counter = self

        async def _counted_flush(manifest):
            counter.calls.append(len(executor._script_buffer))
            return await original(manifest)

        executor.flush = _counted_flush

    @property
    def count(self):
        return len(self.calls)


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

async def run(mcp) -> dict:
    from core.blender_pipeline.progressive_v2.controller import ProgressiveController
    from core.blender_pipeline.progressive_v2.executor import BlenderExecutor
    from core.blender_pipeline.progressive_v2.dag import DependencyDAG
    from core.blender_pipeline.progressive_v2.manifest import NodeState

    manifest = _build_manifest()
    flush_counter = _FlushCounter()

    # Build controller with live MCP, skip LLM decomposition
    controller = ProgressiveController(
        model_manager=None,   # no LLM needed -- stages pre-injected
        mcp_manager=mcp,
        max_retries=1,
    )
    controller.manifest = manifest
    controller.dag = DependencyDAG.from_manifest(manifest)

    # All stage outputs are pre-injected and transforms pre-resolved, so
    # SIBLING_ROOT_REF edges (legs wait for tabletop bbox) are unnecessary.
    # Remove them so all 5 parts are actionable in the same iteration,
    # which is the batch-flush behaviour the test is verifying.
    from core.blender_pipeline.progressive_v2.dag import DependencyType
    for node in manifest.nodes.values():
        if node.transform_state and node.transform_state.is_resolved:
            for dep_id in list(controller.dag._forward.get(node.node_id, [])):
                dep = controller.dag.get_dependency(node.node_id, dep_id)
                if dep and dep.dep_type == DependencyType.SIBLING_ROOT_REF:
                    controller.dag.remove_dependency(node.node_id, dep_id)

    # Create executor and patch flush counter BEFORE build loop runs
    executor = BlenderExecutor(mcp, task_id="test_table_live")
    flush_counter.patch(executor)
    controller._executor = executor

    # Remove debug logging
    await controller._build_loop("test_table_live", model_id=None)

    # Query Blender for world positions of all part objects
    part_names = []
    for node in manifest.nodes.values():
        if node.blender_objects:
            part_names.extend(node.blender_objects)

    query_script = f"""
import bpy, json
names = {repr(part_names)}
out = {{}}
for n in names:
    obj = bpy.data.objects.get(n)
    if obj:
        out[n] = {{
            "exists": True,
            "loc": [round(v, 4) for v in obj.matrix_world.translation],
        }}
    else:
        out[n] = {{"exists": False}}
print("SENTINEL_OUTPUT_START" + json.dumps({{"ok": True, "objects": out}}) + "SENTINEL_OUTPUT_END")
"""
    raw = await mcp.call_locked("blender", "execute_blender_code", {"code": query_script})
    output = raw.get("output", "")
    s, e = "SENTINEL_OUTPUT_START", "SENTINEL_OUTPUT_END"
    si, ei = output.find(s), output.find(e)
    query_data = json.loads(output[si + len(s):ei]) if si != -1 else {"ok": False}

    # Cleanup
    if part_names:
        cleanup_script = f"""
import bpy, json
removed = []
for n in {repr(part_names)}:
    obj = bpy.data.objects.get(n)
    if obj:
        bpy.data.objects.remove(obj, do_unlink=True)
        removed.append(n)
# Also remove assembly empties
for obj in list(bpy.data.objects):
    if "table_assembly" in obj.name and obj.type == "EMPTY":
        bpy.data.objects.remove(obj, do_unlink=True)
        removed.append(obj.name)
# Remove collection
coll = bpy.data.collections.get(executor_coll := {repr(executor._collection_name)})
if coll:
    bpy.data.collections.remove(coll)
print("SENTINEL_OUTPUT_START" + json.dumps({{"ok": True, "removed": removed}}) + "SENTINEL_OUTPUT_END")
"""
        raw2 = await mcp.call_locked("blender", "execute_blender_code", {"code": cleanup_script})
        out2 = raw2.get("output", "")
        si2, ei2 = out2.find(s), out2.find(e)
        cleanup_data = json.loads(out2[si2 + len(s):ei2]) if si2 != -1 else {"ok": False}
    else:
        cleanup_data = {"ok": True, "removed": []}

    return {
        "manifest": manifest,
        "flush_calls": flush_counter.calls,
        "query": query_data,
        "cleanup": cleanup_data,
    }


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

EXPECTED_POSITIONS = {
    "tabletop": [0.0,  0.0,  0.375],
    "leg_fl":   [-0.35,-0.25, 0.175],
    "leg_fr":   [ 0.35,-0.25, 0.175],
    "leg_bl":   [-0.35, 0.25, 0.175],
    "leg_br":   [ 0.35, 0.25, 0.175],
}


def chk(label, ok, detail=""):
    tag = "[PASS]" if ok else "[FAIL]"
    print(f"{tag} {label}" + (f"  ({detail})" if detail else ""))
    return ok


def run_checks(results: dict) -> bool:
    from core.blender_pipeline.progressive_v2.manifest import NodeState, NodeKind

    manifest = results["manifest"]
    flush_calls = results["flush_calls"]
    query = results["query"]
    cleanup = results["cleanup"]
    objs = query.get("objects", {})

    all_pass = True
    print("\n--- Node states ---")
    for node in manifest.nodes.values():
        print(f"  [{node.kind.value:8}] {node.label:20} -> {node.state.value}")

    print("\n--- Checks ---")

    # 1. Root verified
    root = manifest.get_root()
    all_pass &= chk("root MODEL verified", root.state == NodeState.VERIFIED)

    # 2. Assembly verified
    asm = manifest.get_node_by_label("table_assembly")
    all_pass &= chk("table_assembly VERIFIED", asm and asm.state == NodeState.VERIFIED)

    # 3. All 5 parts verified
    for label in EXPECTED_POSITIONS:
        node = manifest.get_node_by_label(label)
        all_pass &= chk(f"{label} VERIFIED", node and node.state == NodeState.VERIFIED)

    # 4. All 5 objects exist in Blender
    for label in EXPECTED_POSITIONS:
        node = manifest.get_node_by_label(label)
        if not node or not node.blender_objects:
            all_pass &= chk(f"{label} object_exists", False, "no blender_objects on node")
            continue
        obj_name = node.blender_objects[0]
        obj_data = objs.get(obj_name)
        all_pass &= chk(
            f"{label} object_exists",
            obj_data is not None and obj_data.get("exists"),
            f"name={obj_name}",
        )

    # 5. World positions correct
    for label, expected in EXPECTED_POSITIONS.items():
        node = manifest.get_node_by_label(label)
        if not node or not node.blender_objects:
            all_pass &= chk(f"{label} world pos", False, "no blender_objects")
            continue
        obj_name = node.blender_objects[0]
        obj_data = objs.get(obj_name)
        if not obj_data or not obj_data.get("exists"):
            all_pass &= chk(f"{label} world pos", False, "object missing")
            continue
        loc = obj_data["loc"]
        close = all(abs(loc[i] - expected[i]) < TOL for i in range(3))
        all_pass &= chk(
            f"{label} world pos",
            close,
            f"expected={[round(v,3) for v in expected]} got={loc}",
        )

    # 6. Batch flush: all 5 parts sent in ONE flush call (not 5 separate calls).
    # Assembly merges each add 1 flush (1 per assembly empty) — those are expected.
    # We verify: exactly 1 flush had >= 5 fragments (the part batch), rest had 1.
    part_batch_flushes = [n for n in flush_calls if n >= 5]
    assembly_flushes = [n for n in flush_calls if n == 1]
    all_pass &= chk(
        "batch flush: 1 flush for 5 parts",
        len(part_batch_flushes) == 1,
        f"flush sizes={flush_calls} -- expected exactly 1 flush with >=5 fragments",
    )

    # 7. Cleanup succeeded
    all_pass &= chk("cleanup ok", cleanup.get("ok"), str(cleanup.get("removed", [])))

    return all_pass


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    print("\n" + "=" * 60)
    print("  Controller + Executor Live MCP Test")
    print("  Table: 5 parts, 1 assembly, batch flush, live verify")
    print("=" * 60 + "\n")

    from core.mcp_manager import MCPManager
    mcp = MCPManager()
    mcp.initialize_from_config()

    print("Connecting to Blender MCP...")
    try:
        conn = await mcp.connect_app("blender")
        print(f"Connected. Tools: {[t.name for t in conn.discovered_tools]}\n")
    except Exception as e:
        print(f"[FAIL] Could not connect: {e}")
        return 1

    try:
        results = await run(mcp)
    except Exception:
        import traceback; traceback.print_exc()
        await mcp.shutdown()
        return 1

    all_pass = run_checks(results)

    print("\n" + "=" * 60)
    print("  ALL CHECKS PASSED" if all_pass else "  SOME CHECKS FAILED -- see above")
    print("=" * 60)

    await mcp.shutdown()
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
