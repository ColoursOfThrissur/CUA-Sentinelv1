import asyncio
import json
import os
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from core.blender_pipeline.progressive_v2.manifest import (
    BuildManifest,
    NodeState,
    NodeKind,
    NodeImportance,
    SocketType,
    PrimitiveType,
    GeometrySpec,
    AttachmentSpec,
    CompletionStatus,
)
from core.blender_pipeline.progressive_v2.transforms import LocalTransform, NodeTransformState
from core.blender_pipeline.progressive_v2.controller import ProgressiveController, BuildPhase
from core.blender_pipeline.progressive_v2.executor import BlenderExecutor
from core.blender_pipeline.progressive_v2.dag import DependencyDAG
from core.blender_pipeline.progressive_v2.readback import SceneReadbackVerifier
from core.blender_pipeline.progressive_v2.render_evidence import MultiViewEvidenceRenderer
from core.mcp_manager import MCPManager

async def run_and_export():
    print("=" * 70)
    print("  RUNNING PIPELINE V2 & EXPORTING COMPILED BLENDER SCRIPT")
    print("=" * 70)

    # 1. Connect to live Blender MCP
    mcp = MCPManager()
    mcp.initialize_from_config()
    await mcp.connect_app("blender")
    print("Connected to Blender MCP.")

    # 2. Load manifest from saved tabletop drone run
    manifest_path = Path("data/builds_v2/m_f4b618e2bc/manifest.json")
    manifest = BuildManifest.load(manifest_path)
    print(f"Loaded base manifest: {len(manifest.nodes)} nodes")

    # 3. Apply the 4-corner assembly frame anchor fix for landing feet
    feet_node = manifest.get_node_by_label("landing_feet")
    leg_specs = [
        {
            "label": "landing_feet_front_left",
            "kind": NodeKind.PART,
            "importance": NodeImportance.REQUIRED,
            "socket_type": SocketType.CORNER,
            "primitive": PrimitiveType.CYLINDER,
            "geometry": GeometrySpec(primitive=PrimitiveType.CYLINDER, radius=0.012, depth=0.04),
            "attachment": AttachmentSpec(socket_type=SocketType.CORNER, local_offset=[-0.12, -0.09, -0.06], local_rotation=[0.0, 0.0, 0.0]),
        },
        {
            "label": "landing_feet_front_right",
            "kind": NodeKind.PART,
            "importance": NodeImportance.REQUIRED,
            "socket_type": SocketType.CORNER,
            "primitive": PrimitiveType.CYLINDER,
            "geometry": GeometrySpec(primitive=PrimitiveType.CYLINDER, radius=0.012, depth=0.04),
            "attachment": AttachmentSpec(socket_type=SocketType.CORNER, local_offset=[0.12, -0.09, -0.06], local_rotation=[0.0, 0.0, 0.0]),
        },
        {
            "label": "landing_feet_rear_left",
            "kind": NodeKind.PART,
            "importance": NodeImportance.REQUIRED,
            "socket_type": SocketType.CORNER,
            "primitive": PrimitiveType.CYLINDER,
            "geometry": GeometrySpec(primitive=PrimitiveType.CYLINDER, radius=0.012, depth=0.04),
            "attachment": AttachmentSpec(socket_type=SocketType.CORNER, local_offset=[-0.12, 0.09, -0.06], local_rotation=[0.0, 0.0, 0.0]),
        },
        {
            "label": "landing_feet_rear_right",
            "kind": NodeKind.PART,
            "importance": NodeImportance.REQUIRED,
            "socket_type": SocketType.CORNER,
            "primitive": PrimitiveType.CYLINDER,
            "geometry": GeometrySpec(primitive=PrimitiveType.CYLINDER, radius=0.012, depth=0.04),
            "attachment": AttachmentSpec(socket_type=SocketType.CORNER, local_offset=[0.12, 0.09, -0.06], local_rotation=[0.0, 0.0, 0.0]),
        },
    ]
    existing_feet = [
        manifest.get_node_by_label(spec["label"])
        for spec in leg_specs
    ]
    if all(existing_feet):
        created_feet = existing_feet
        print("Reusing the four existing landing feet from the saved manifest.")
    else:
        created_feet = manifest.commit_decomposition(feet_node.node_id, leg_specs)
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

    for node in manifest.nodes.values():
        node.blender_objects = []
        if node.kind in (NodeKind.PART, NodeKind.INSTANCE):
            node.state = NodeState.READY
            if node.transform_state and not node.transform_state.local_transform and node.attachment:
                node.transform_state.set_local_transform(LocalTransform(
                    position=node.attachment.local_offset or [0, 0, 0],
                    rotation=node.attachment.local_rotation or [0, 0, 0],
                ))
        elif node.kind in (NodeKind.ASSEMBLY, NodeKind.MODEL):
            node.state = NodeState.READY

    manifest.stats.pop("build_error", None)
    manifest.stats.pop("build_errors", None)

    # 4. Prepare Controller & Custom Hooked Executor to intercept the compiled script
    controller = ProgressiveController(model_manager=None, mcp_manager=mcp, max_retries=1)
    controller.manifest = manifest
    controller.dag = DependencyDAG.from_manifest(manifest)
    executor = BlenderExecutor(mcp, task_id="tabletop_drone_export")
    controller._executor = executor

    flushed_scripts = []
    orig_flush = executor.flush

    async def intercepted_flush(m):
        if executor._script_buffer:
            header = (
                "import bpy, bmesh, json, math, mathutils\n"
                f"_coll_name = {repr(executor._collection_name)}\n"
                "if _coll_name not in bpy.data.collections:\n"
                "    _c = bpy.data.collections.new(_coll_name)\n"
                "    bpy.context.scene.collection.children.link(_c)\n"
                "_coll = bpy.data.collections.get(_coll_name)\n"
                "def _link(obj):\n"
                "    if _coll: _coll.objects.link(obj)\n"
                "    else: bpy.context.scene.collection.objects.link(obj)\n"
                "def _unlink_all(obj):\n"
                "    for c in list(obj.users_collection): c.objects.unlink(obj)\n"
                "_sentinel_results = {}\n"
            )
            footer = (
                "\nprint('SENTINEL_OUTPUT_START' + json.dumps({'ok': True, 'results': _sentinel_results}) + 'SENTINEL_OUTPUT_END')\n"
            )
            full_script = header + "\n".join(executor._script_buffer) + footer
            flushed_scripts.append(full_script)
        return await orig_flush(m)

    executor.flush = intercepted_flush

    # 5. Run build loop
    print("Executing pipeline build loop...")
    await controller._build_loop("tabletop_drone_export", model_id=manifest.model_id)
    controller.phase = BuildPhase.COMPLETE

    # 6. Save accumulated compiled pipeline script to file
    out_dir = Path("data")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_script = out_dir / "pipeline_compiled_drone_script.py"

    full_compiled = "\n# --- PIPELINE FLUSH CHUNK ---\n".join(flushed_scripts)
    # Add standalone camera + lighting + render footer for direct headless execution
    standalone_footer = '''
# --- STANDALONE RENDER VERIFICATION FOOTER ---
import bpy, os
render_dir = r"C:\\Users\\derik\\Desktop\\Derik\\Projects\\CUA-Sentinel\\backend\\data\\renders_pipeline_compiled"
os.makedirs(render_dir, exist_ok=True)

# Add Camera & Sun if not present
cam_data = bpy.data.cameras.new("PipelineCamera")
cam_obj = bpy.data.objects.new("PipelineCamera", cam_data)
bpy.context.scene.collection.objects.link(cam_obj)
bpy.context.scene.camera = cam_obj

light_data = bpy.data.lights.new(name="PipelineSun", type='SUN')
light_data.energy = 3.5
light_obj = bpy.data.objects.new(name="PipelineSun", object_data=light_data)
bpy.context.scene.collection.objects.link(light_obj)
light_obj.rotation_euler = (0.785, 0.35, 0.785)

scene = bpy.context.scene
scene.render.resolution_x = 800
scene.render.resolution_y = 600
scene.render.film_transparent = True

views = {
    "isometric.png": ((0.5, -0.6, 0.4), (1.05, 0.0, 0.785)),
    "front.png":     ((0.0, -0.7, 0.1), (1.57, 0.0, 0.0)),
    "side.png":      ((0.7, 0.0, 0.1),  (1.57, 0.0, 1.57)),
    "top.png":       ((0.0, 0.0, 0.7),  (0.0, 0.0, 0.0)),
}

for filename, (loc, rot) in views.items():
    cam_obj.location = loc
    cam_obj.rotation_euler = rot
    scene.render.filepath = os.path.join(render_dir, filename)
    bpy.ops.render.render(write_still=True)
    print(f"Rendered: {scene.render.filepath}")

print("PIPELINE_STANDALONE_BUILD_AND_RENDER_COMPLETE")
'''
    out_script.write_text(full_compiled + "\n" + standalone_footer, encoding="utf-8")
    print(f"\nSaved complete compiled pipeline script to: {out_script.resolve()}")
    print(f"Total script length: {len(full_compiled.splitlines())} lines, {len(flushed_scripts)} batches flushed.")

    # 7. Scene Readback
    verifier = SceneReadbackVerifier(mcp)
    readback_report = await verifier.verify(manifest, executor)
    print(f"Scene Readback Status: {readback_report.get('ok')} ({readback_report.get('observed_tagged_count')}/{readback_report.get('expected_part_count')} parts)")

    await mcp.shutdown()
    print("Done pipeline run; live Blender objects were retained for review.")

if __name__ == "__main__":
    asyncio.run(run_and_export())
