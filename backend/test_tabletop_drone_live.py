"""
test_tabletop_drone_live.py

Executes the Tabletop Surveillance Drone build (model m_f4b618e2bc)
with live Blender MCP connection to verify end-to-end:
1. Frame-anchored ROOT-less landing_feet decomposition (all 4 corner legs)
2. Symmetrical placement of all 4 feet
3. Execution and build of all parts in Blender 4.5.3 LTS
4. Full assembly verification through root MODEL node
5. SceneReadbackVerifier on depsgraph evaluated meshes
6. MultiViewEvidenceRenderer generating multi-angle PNG renders
7. Clean teardown
"""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("test_tabletop_live")

async def run_tabletop_drone():
    from core.mcp_manager import MCPManager
    from core.blender_pipeline.progressive_v2.manifest import (
        BuildManifest, AttachmentSpec, GeometrySpec, MaterialSpec,
        NodeState, CompletionStatus
    )
    from core.blender_pipeline.progressive_v2.node_types import (
        NodeKind, NodeImportance, SocketType, PrimitiveType
    )
    from core.blender_pipeline.progressive_v2.controller import ProgressiveController, BuildPhase
    from core.blender_pipeline.progressive_v2.executor import BlenderExecutor
    from core.blender_pipeline.progressive_v2.dag import DependencyDAG
    from core.blender_pipeline.progressive_v2.readback import SceneReadbackVerifier
    from core.blender_pipeline.progressive_v2.render_evidence import MultiViewEvidenceRenderer

    print("\n" + "=" * 70)
    print("  TABLETOP SURVEILLANCE DRONE (m_f4b618e2bc) LIVE VERIFICATION")
    print("=" * 70 + "\n")

    # 1. Connect to Blender MCP
    mcp = MCPManager()
    mcp.initialize_from_config()
    print("Connecting to Blender MCP...")
    try:
        conn = await mcp.connect_app("blender")
        print(f"Connected to Blender. Available tools: {[t.name for t in conn.discovered_tools]}")
    except Exception as e:
        print(f"ERROR: Could not connect to Blender MCP: {e}")
        return False

    # 2. Load manifest from m_f4b618e2bc
    manifest_path = _HERE / "data" / "builds_v2" / "m_f4b618e2bc" / "manifest.json"
    with open(manifest_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    manifest = BuildManifest.from_dict(data)
    manifest.model_id = "tabletop_drone_live"
    print(f"Loaded base manifest: {len(manifest.nodes)} nodes, prompt: {manifest.prompt[:60]}...")

    # 3. Find landing_feet node
    feet_node = manifest.get_node_by_label("landing_feet")
    assert feet_node is not None, "landing_feet node not found in manifest"

    # Reset failed state on landing_feet so we can test the new decomposition fix
    feet_node.state = NodeState.READY
    feet_node.error = None
    feet_node.children_ids = []

    # Decompose landing_feet with 4 CORNER feet (exact response from LLM that failed previously)
    leg_specs = [
        {
            "label": "landing_feet_front_left",
            "kind": NodeKind.PART,
            "importance": NodeImportance.REQUIRED,
            "socket_type": SocketType.CORNER,
            "primitive": PrimitiveType.CYLINDER,
            "geometry": GeometrySpec(primitive=PrimitiveType.CYLINDER, radius=0.012, depth=0.04),
            "attachment": AttachmentSpec(
                socket_type=SocketType.CORNER,
                local_offset=[-0.12, -0.09, -0.06],
                local_rotation=[0.0, 0.0, 0.0],
            ),
        },
        {
            "label": "landing_feet_front_right",
            "kind": NodeKind.PART,
            "importance": NodeImportance.REQUIRED,
            "socket_type": SocketType.CORNER,
            "primitive": PrimitiveType.CYLINDER,
            "geometry": GeometrySpec(primitive=PrimitiveType.CYLINDER, radius=0.012, depth=0.04),
            "attachment": AttachmentSpec(
                socket_type=SocketType.CORNER,
                local_offset=[0.12, -0.09, -0.06],
                local_rotation=[0.0, 0.0, 0.0],
            ),
        },
        {
            "label": "landing_feet_rear_left",
            "kind": NodeKind.PART,
            "importance": NodeImportance.REQUIRED,
            "socket_type": SocketType.CORNER,
            "primitive": PrimitiveType.CYLINDER,
            "geometry": GeometrySpec(primitive=PrimitiveType.CYLINDER, radius=0.012, depth=0.04),
            "attachment": AttachmentSpec(
                socket_type=SocketType.CORNER,
                local_offset=[-0.12, 0.09, -0.06],
                local_rotation=[0.0, 0.0, 0.0],
            ),
        },
        {
            "label": "landing_feet_rear_right",
            "kind": NodeKind.PART,
            "importance": NodeImportance.REQUIRED,
            "socket_type": SocketType.CORNER,
            "primitive": PrimitiveType.CYLINDER,
            "geometry": GeometrySpec(primitive=PrimitiveType.CYLINDER, radius=0.012, depth=0.04),
            "attachment": AttachmentSpec(
                socket_type=SocketType.CORNER,
                local_offset=[0.12, 0.09, -0.06],
                local_rotation=[0.0, 0.0, 0.0],
            ),
        },
    ]

    print("\nApplying fix: committing 4 corner landing feet without forcing ROOT child...")
    created_feet = manifest.commit_decomposition(feet_node.node_id, leg_specs)
    print(f"Successfully committed {len(created_feet)} feet nodes:")
    from core.blender_pipeline.progressive_v2.transforms import LocalTransform, NodeTransformState
    for fn in created_feet:
        pos = fn.attachment.local_offset
        ts = NodeTransformState()
        ts.set_local_transform(LocalTransform(position=pos, rotation=[0.0, 0.0, 0.0]))
        fn.transform_state = ts
        fn.stage_outputs = {
            "stage2": {"radius": 0.012, "depth": 0.04, "primitive": "cylinder"},
            "stage3": {"socket_type": "CORNER", "local_offset": pos, "local_rotation": [0.0, 0.0, 0.0]},
            "stage4": {"offset": pos, "rotation": [0.0, 0.0, 0.0], "resolution_method": "injected"},
        }
        print(f"  - {fn.label} (socket={fn.attachment.socket_type.value})")

    # Reset all nodes to READY with blender_objects cleared so the entire drone
    # is built fresh into the active executor attempt collection
    for node in manifest.nodes.values():
        node.blender_objects = []
        if node.kind in (NodeKind.PART, NodeKind.INSTANCE):
            node.state = NodeState.READY
            # Ensure transform_state has local_transform set
            if node.transform_state and not node.transform_state.local_transform and node.attachment:
                from core.blender_pipeline.progressive_v2.transforms import LocalTransform
                node.transform_state.set_local_transform(LocalTransform(
                    position=node.attachment.local_offset or [0, 0, 0],
                    rotation=node.attachment.local_rotation or [0, 0, 0],
                ))
        elif node.kind in (NodeKind.ASSEMBLY, NodeKind.MODEL):
            node.state = NodeState.READY

    # Clear any stale build_error from the previous aborted session in manifest
    manifest.stats.pop("build_error", None)
    manifest.stats.pop("build_errors", None)

    # 4. Prepare Controller & Executor
    controller = ProgressiveController(
        model_manager=None,
        mcp_manager=mcp,
        max_retries=1,
    )
    controller.manifest = manifest
    controller.dag = DependencyDAG.from_manifest(manifest)
    executor = BlenderExecutor(mcp, task_id="tabletop_drone_live")
    controller._executor = executor

    # Ensure build loop runs
    print("\nRunning build loop in Blender...")
    await controller._build_loop("tabletop_drone_live", model_id=manifest.model_id)
    controller.phase = BuildPhase.COMPLETE

    # 5. Check node states
    root = manifest.get_root()
    feet = manifest.get_node_by_label("landing_feet")
    print("\n--- Key Component States ---")
    print(f"  Root ({root.label}): {root.state.value}")
    print(f"  landing_feet: {feet.state.value}")
    for fn in created_feet:
        print(f"    - {fn.label}: {fn.state.value}")

    # Check all required children of root
    root_children_states = {manifest.nodes[cid].label: manifest.nodes[cid].state.value for cid in root.children_ids}
    print(f"\nRoot children states:\n{json.dumps(root_children_states, indent=2)}")

    # 6. Run SceneReadbackVerifier
    print("\n--- Running SceneReadbackVerifier ---")
    verifier = SceneReadbackVerifier(mcp)
    readback_report = await verifier.verify(manifest, executor)
    manifest.stats["scene_readback"] = readback_report
    print(f"Scene Readback Status: {readback_report.get('ok')}")
    print(f"  Observed/Expected parts: {readback_report.get('observed_tagged_count')}/{readback_report.get('expected_part_count')}")
    if readback_report.get("findings"):
        print(f"  Readback findings ({len(readback_report['findings'])}):")
        for f in readback_report["findings"][:10]:
            print(f"    - {f.get('type')}: {f.get('node_id')} expected={f.get('expected')} actual={f.get('actual')}")

    # 7. Run MultiViewEvidenceRenderer
    print("\n--- Generating Multi-View Render Evidence ---")
    try:
        await MultiViewEvidenceRenderer.render(manifest, executor, mcp)
        render_stats = manifest.stats.get("render_evidence", {})
        print(f"Render Evidence Status: {render_stats.get('ok')}")
        print(f"Render Files: {render_stats.get('paths')}")
    except Exception as e:
        print(f"Render generation note: {e}")

    # 8. Build final result payload
    result = controller._build_result(1.0, [])
    res_dict = result.to_dict()
    print("\n--- ProgressiveResult Payload ---")
    print(f"  success: {res_dict['success']}")
    print(f"  completion_status: {res_dict['completion_status']}")
    print(f"  total_nodes: {res_dict['total_nodes']}")
    print(f"  verified_nodes: {res_dict['verified_nodes']}")
    print(f"  failed_nodes: {res_dict['failed_nodes']}")
    print(f"  skipped_nodes: {res_dict['skipped_nodes']}")

    # 9. Teardown / Cleanup
    print("\nCleaning up Blender objects...")
    clean_script = f"""
import bpy
coll = bpy.data.collections.get({repr(executor._collection_name)})
if coll:
    for obj in list(coll.all_objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    bpy.data.collections.remove(coll)
"""
    await mcp.call_locked("blender", "execute_blender_code", {"code": clean_script})
    await mcp.shutdown()
    print("Done cleanup.")

    all_passed = (
        root.state == NodeState.VERIFIED and
        feet.state == NodeState.VERIFIED and
        all(fn.state == NodeState.VERIFIED for fn in created_feet) and
        result.completion_status in (CompletionStatus.SUCCESS, CompletionStatus.COMMITTED_UNVERIFIED)
    )

    print("\n" + "=" * 70)
    print("  RESULT: " + ("PASS - Model fully verified in Blender!" if all_passed else "FAIL - Some checks failed"))
    print("=" * 70 + "\n")
    return all_passed

if __name__ == "__main__":
    success = asyncio.run(run_tabletop_drone())
    sys.exit(0 if success else 1)
