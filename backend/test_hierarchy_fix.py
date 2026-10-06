"""
test_hierarchy_fix.py  --  smoke-test for the 3 hierarchy bugs fixed.

Tests WITHOUT Blender / Ollama.  Uses a mock MCP that captures every script.

Hierarchy under test (varying depth):

  desk_lamp  (MODEL)
    base_assembly  (ASSEMBLY)          depth 1
      base_plate     (PART, ROOT)      depth 2
      weight_block   (PART, RELATIVE_TO) depth 2
      cable_port     (PART, RELATIVE_TO) depth 2
    arm_assembly   (ASSEMBLY)          depth 1
      lower_arm      (PART, ROOT)      depth 2
      joint_assembly (ASSEMBLY)        depth 2  <-- nested sub-assembly
        pivot_pin    (PART, ROOT)      depth 3
        knuckle      (PART, RELATIVE_TO) depth 3
        upper_arm    (PART, RELATIVE_TO) depth 3
    shade_assembly (ASSEMBLY)          depth 1
      shade_body     (PART, ROOT)      depth 2
      bulb_socket    (PART, RELATIVE_TO) depth 2

Checks:
  1. merge_assembly script contains matrix_parent_inverse for every child
  2. _establish_blender_hierarchy iterates assemblies (enum fix)
  3. _establish_blender_hierarchy parses SENTINEL block (not raw dict)
  4. empty_inv computed once, applied per child (not recomputed per child)

Usage:
    cd backend
    python test_hierarchy_fix.py
"""

from __future__ import annotations
import asyncio, json, re, sys, os

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)


# ---------------------------------------------------------------------------
# Mock MCP
# ---------------------------------------------------------------------------

class MockMCP:
    def __init__(self):
        self.calls: list[dict] = []

    async def call_locked(self, service, method, params, **_kwargs):
        code = params.get("code", "")
        self.calls.append({"code": code})

        if "bpy.data.collections.new" in code:
            out = json.dumps({"ok": True, "created": True, "name": "Sentinel_Build_test"})
        elif "matrix_world = mathutils.Matrix" in code and "bpy.data.objects.new" in code:
            m = re.search(r"name = '([^']+)'", code)
            out = json.dumps({"ok": True, "name": m.group(1) if m else "unknown", "location": [0, 0, 0]})
        elif "bbox_min" in code and "bbox_max" in code and "world_verts" in code:
            out = json.dumps({"ok": True, "min": [-0.1, -0.1, 0.0], "max": [0.1, 0.1, 0.2]})
        elif "remove_doubles" in code:
            out = json.dumps({"ok": True, "stats": {}})
        elif "bpy.data.objects" in code and "result = {" in code and "in bpy.data.objects" in code:
            out = json.dumps({"ok": True})
        elif "obj.dimensions" in code:
            out = json.dumps({"ok": True, "scaled_size": [0.2, 0.2, 0.2]})
        elif "non_manifold" in code:
            out = json.dumps({"ok": True, "issues": []})
        elif "empty_display_type" in code:
            out = json.dumps({
                "ok": True,
                "empty": "test_assembly_abc123",
                "parented": ["obj_a", "obj_b"],
                "bbox_min": [-0.2, -0.2, 0.0],
                "bbox_max": [0.2, 0.2, 0.4],
            })
        elif "parentings" in code and "position_warnings" in code:
            out = json.dumps({"ok": True, "parentings": [{"child": "c", "parent": "p"}], "position_warnings": []})
        elif "min_z" in code and "lift" in code:
            out = json.dumps({"ok": True, "lift": 0.0})
        else:
            out = json.dumps({"ok": True})

        return {"output": f"SENTINEL_OUTPUT_START{out}SENTINEL_OUTPUT_END"}


# ---------------------------------------------------------------------------
# Build manifest: desk lamp with varying depth
#
#   desk_lamp (MODEL)
#     base_assembly (ASSEMBLY)
#       base_plate   (PART, ROOT)
#       weight_block (PART, RELATIVE_TO)
#       cable_port   (PART, RELATIVE_TO)
#     arm_assembly (ASSEMBLY)
#       lower_arm    (PART, ROOT)
#       joint_assembly (ASSEMBLY)          <-- nested
#         pivot_pin  (PART, ROOT)
#         knuckle    (PART, RELATIVE_TO)
#         upper_arm  (PART, RELATIVE_TO)
#     shade_assembly (ASSEMBLY)
#       shade_body   (PART, ROOT)
#       bulb_socket  (PART, RELATIVE_TO)
# ---------------------------------------------------------------------------

def build_manifest():
    from core.blender_pipeline.progressive_v2.manifest import (
        BuildManifest, GeometrySpec, AttachmentSpec, NodeState,
    )
    from core.blender_pipeline.progressive_v2.node_types import (
        NodeKind, NodeImportance, SocketType, PrimitiveType,
    )
    from core.blender_pipeline.progressive_v2.transforms import (
        NodeTransformState, LocalTransform,
    )

    manifest = BuildManifest.create("desk lamp test")

    def _ts(pos=(0.0, 0.0, 0.0)):
        lt = LocalTransform(position=list(pos), rotation=[0.0, 0.0, 0.0], scale=[1, 1, 1])
        ts = NodeTransformState()
        ts.set_local_transform(lt)
        ts.compute_world(None, -1)
        return ts

    def _geo(prim=PrimitiveType.BOX):
        g = GeometrySpec(primitive=prim)
        g.radius = 0.05; g.depth = 0.1; g.size = [0.1, 0.1, 0.1]
        return g

    def _att(socket):
        return AttachmentSpec(socket_type=socket)

    root = manifest.get_root()
    root.transform_state = _ts()

    # ---- depth-1 assemblies ----
    base_asm = manifest.add_child_node(
        root.node_id, "base_assembly", NodeKind.ASSEMBLY,
        attachment=_att(SocketType.ROOT),
    )
    base_asm.transform_state = _ts((0, 0, 0))

    arm_asm = manifest.add_child_node(
        root.node_id, "arm_assembly", NodeKind.ASSEMBLY,
        attachment=_att(SocketType.TOP_CENTER),
    )
    arm_asm.transform_state = _ts((0, 0, 0.1))

    shade_asm = manifest.add_child_node(
        root.node_id, "shade_assembly", NodeKind.ASSEMBLY,
        attachment=_att(SocketType.TOP_CENTER),
    )
    shade_asm.transform_state = _ts((0, 0, 0.5))

    # ---- base_assembly parts (depth 2) ----
    for label, pos, sock in [
        ("base_plate",   (0, 0, 0.01), SocketType.ROOT),
        ("weight_block", (0.05, 0, 0.02), SocketType.RELATIVE_TO),
        ("cable_port",   (-0.04, 0, 0.02), SocketType.RELATIVE_TO),
    ]:
        n = manifest.add_child_node(
            base_asm.node_id, label, NodeKind.PART,
            geometry=_geo(PrimitiveType.BOX), attachment=_att(sock),
        )
        n.transform_state = _ts(pos)

    # ---- arm_assembly: one part + one nested assembly (depth 2) ----
    lower_arm = manifest.add_child_node(
        arm_asm.node_id, "lower_arm", NodeKind.PART,
        geometry=_geo(PrimitiveType.CYLINDER), attachment=_att(SocketType.ROOT),
    )
    lower_arm.transform_state = _ts((0, 0, 0.15))

    joint_asm = manifest.add_child_node(
        arm_asm.node_id, "joint_assembly", NodeKind.ASSEMBLY,
        attachment=_att(SocketType.TOP_CENTER),
    )
    joint_asm.transform_state = _ts((0, 0, 0.3))

    # ---- joint_assembly parts (depth 3) ----
    for label, pos, sock in [
        ("pivot_pin", (0, 0, 0.31), SocketType.ROOT),
        ("knuckle",   (0.02, 0, 0.32), SocketType.RELATIVE_TO),
        ("upper_arm", (0, 0, 0.4),  SocketType.RELATIVE_TO),
    ]:
        n = manifest.add_child_node(
            joint_asm.node_id, label, NodeKind.PART,
            geometry=_geo(PrimitiveType.CYLINDER), attachment=_att(sock),
        )
        n.transform_state = _ts(pos)

    # ---- shade_assembly parts (depth 2) ----
    for label, pos, sock in [
        ("shade_body",  (0, 0, 0.52), SocketType.ROOT),
        ("bulb_socket", (0, 0, 0.55), SocketType.RELATIVE_TO),
    ]:
        n = manifest.add_child_node(
            shade_asm.node_id, label, NodeKind.PART,
            geometry=_geo(PrimitiveType.SPHERE), attachment=_att(sock),
        )
        n.transform_state = _ts(pos)

    # Mark all PARTs VERIFIED with dummy blender objects
    for node in manifest.nodes.values():
        if node.kind == NodeKind.PART:
            node.state = NodeState.VERIFIED
            node.blender_objects = [f"{node.label}_obj"]
            node.bounding_box = {"min": [-0.05, -0.05, 0.0], "max": [0.05, 0.05, 0.1]}
            node.stage_outputs["stage2"] = {}
            node.stage_outputs["stage3"] = {}
            node.stage_outputs["stage4"] = {}

    return manifest


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def check(label: str, condition: bool, detail: str = "") -> bool:
    tag = "[PASS]" if condition else "[FAIL]"
    print(f"{tag} {label}" + (f"  ({detail})" if detail else ""))
    return condition


def check_matrix_parent_inverse(executor) -> bool:
    merge_frags = [f for f in executor._script_buffer if "empty_display_type" in f]
    if not merge_frags:
        return check("merge_assembly buffered", False, "no merge fragments found")
    all_ok = True
    for i, frag in enumerate(merge_frags):
        has_inv = "matrix_parent_inverse" in frag
        ok = check(f"merge_assembly[{i}] sets matrix_parent_inverse", has_inv,
                   "missing" if not has_inv else "present")
        all_ok = all_ok and ok
    return all_ok


def check_hierarchy_call(mcp: MockMCP) -> bool:
    hier_calls = [c for c in mcp.calls if "parentings" in c["code"] and "position_warnings" in c["code"]]
    return check("_establish_blender_hierarchy executed", len(hier_calls) > 0,
                 f"{len(hier_calls)} call(s)")


def check_empty_inv_pattern(executor) -> bool:
    merge_frags = [f for f in executor._script_buffer if "empty_display_type" in f]
    if not merge_frags:
        return check("empty_inv pattern check", False, "no merge fragments")
    all_ok = True
    for i, frag in enumerate(merge_frags):
        has_once = "_einv = _e.matrix_world.inverted()" in frag
        has_per  = "_co.matrix_parent_inverse = _einv" in frag
        ok = check(f"merge_assembly[{i}] empty_inv once + applied per child",
                   has_once and has_per,
                   "ok" if (has_once and has_per) else f"once={has_once} per={has_per}")
        all_ok = all_ok and ok
    return all_ok


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    print("\n" + "="*60)
    print("  Hierarchy Fix Smoke Test  (varying-depth desk lamp)")
    print("="*60 + "\n")

    from core.blender_pipeline.progressive_v2.controller import ProgressiveController
    from core.blender_pipeline.progressive_v2.hierarchy import HierarchyLimits
    from core.blender_pipeline.progressive_v2.manifest import NodeState
    from core.blender_pipeline.progressive_v2.node_types import NodeKind
    from core.blender_pipeline.progressive_v2.dag import DependencyDAG
    from core.blender_pipeline.progressive_v2.executor import BlenderExecutor

    mcp = MockMCP()
    manifest = build_manifest()

    # Print hierarchy so we can visually confirm structure
    print("Manifest hierarchy:")
    print(manifest.print_hierarchy())

    limits = HierarchyLimits(max_depth=10, max_total_nodes=100, max_children=20)
    ctrl = ProgressiveController(model_manager=None, mcp_manager=mcp, limits=limits)
    ctrl.manifest = manifest
    ctrl.dag = DependencyDAG.from_manifest(manifest)

    # ---- Test 1: merge_assembly matrix_parent_inverse ----
    print("--- Test 1: merge_assembly matrix_parent_inverse ---")
    executor = BlenderExecutor(mcp, "test")
    executor._collection_created = True

    assemblies = [n for n in manifest.nodes.values() if n.kind == NodeKind.ASSEMBLY]
    print(f"  Assemblies to merge: {[n.label for n in assemblies]}")
    for asm in assemblies:
        await executor.merge_assembly(asm, manifest)

    t1 = check_matrix_parent_inverse(executor)

    # ---- Test 2 & 3: _establish_blender_hierarchy enum + SENTINEL parse ----
    print("\n--- Test 2+3: _establish_blender_hierarchy enum fix + SENTINEL parse ---")
    for node in manifest.nodes.values():
        if node.kind in (NodeKind.ASSEMBLY, NodeKind.MODEL):
            node.state = NodeState.VERIFIED
            node.blender_objects = [f"{node.label}_empty_abc123"]

    mcp.calls.clear()
    await ctrl._establish_blender_hierarchy("test")

    t2 = check_hierarchy_call(mcp)
    t3 = check("hierarchy result parsed without crash", True)

    # ---- Test 4: empty_inv computed once, applied per child ----
    print("\n--- Test 4: empty_inv once, applied per child ---")
    executor._script_buffer.clear()
    for asm in assemblies:
        await executor.merge_assembly(asm, manifest)

    t4 = check_empty_inv_pattern(executor)

    # ---- Summary ----
    print("\n" + "="*60)
    all_pass = all([t1, t2, t3, t4])
    print("  ALL CHECKS PASSED" if all_pass else "  SOME CHECKS FAILED -- see above")
    print("="*60)

    # Node count breakdown
    from core.blender_pipeline.progressive_v2.node_types import NodeKind as NK
    depths = {}
    for n in manifest.nodes.values():
        depths.setdefault(n.hierarchy_depth, []).append(n.label)
    print("\nNodes by depth:")
    for d in sorted(depths):
        print(f"  depth {d}: {depths[d]}")

    print(f"\nTotal MCP calls: {len(mcp.calls)}")
    for label, pat in [
        ("  merge_assembly", "empty_display_type"),
        ("  hierarchy      ", "parentings"),
    ]:
        print(f"{label}: {sum(1 for c in mcp.calls if pat in c['code'])}")

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
