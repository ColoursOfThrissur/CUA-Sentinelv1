"""Deterministic multi-view renders for V2 build evidence and visual review."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict


class MultiViewEvidenceRenderer:
    VIEWS = {
        "front": (0.0, -1.0, 0.25),
        "side": (1.0, 0.0, 0.25),
        "top": (0.01, -0.01, 1.0),
        "isometric": (1.0, -1.0, 0.8),
    }

    @classmethod
    async def render(cls, manifest: Any, executor: Any, mcp_manager: Any) -> Dict[str, Any]:
        from core.blender_ops import parse_op_output

        output_dir = manifest._build_dir() / "renders"
        output_dir.mkdir(parents=True, exist_ok=True)
        paths = {name: str((output_dir / f"{name}.png").resolve()) for name in cls.VIEWS}
        script = f'''
import bpy, json, math
from mathutils import Vector
_coll=bpy.data.collections.get({executor._collection_name!r})
_meshes=[o for o in (_coll.all_objects if _coll else []) if o.type=='MESH' and not o.hide_render]
if not _meshes: raise RuntimeError('No renderable meshes in build collection')
_corners=[]
for _o in _meshes:
    _corners.extend([_o.matrix_world @ Vector(c) for c in _o.bound_box])
_lo=Vector((min(v.x for v in _corners),min(v.y for v in _corners),min(v.z for v in _corners)))
_hi=Vector((max(v.x for v in _corners),max(v.y for v in _corners),max(v.z for v in _corners)))
_center=(_lo+_hi)*0.5
_extent=max((_hi-_lo).length,0.1)
_camera_data=bpy.data.cameras.new('SentinelEvidenceCameraData')
_camera=bpy.data.objects.new('SentinelEvidenceCamera',_camera_data)
bpy.context.scene.collection.objects.link(_camera); bpy.context.scene.camera=_camera
_camera_data.lens=52
_light_data=bpy.data.lights.new('SentinelEvidenceKeyData','AREA'); _light_data.energy=900; _light_data.shape='DISK'; _light_data.size=max(_extent,1.0)
_light=bpy.data.objects.new('SentinelEvidenceKey',_light_data); bpy.context.scene.collection.objects.link(_light)
_light.location=_center+Vector((_extent,-_extent,_extent*1.5))
_scene=bpy.context.scene; _scene.render.engine='BLENDER_EEVEE_NEXT'; _scene.render.resolution_x=512; _scene.render.resolution_y=512; _scene.render.resolution_percentage=100
_scene.render.image_settings.file_format='PNG'; _scene.render.film_transparent=False
_world=_scene.world or bpy.data.worlds.new('SentinelEvidenceWorld'); _scene.world=_world; _world.color=(0.035,0.035,0.035)
_views={cls.VIEWS!r}; _paths={paths!r}; _written=[]
for _name,_direction in _views.items():
    _dir=Vector(_direction).normalized(); _camera.location=_center+_dir*(_extent*1.35)
    _camera.rotation_euler=(_center-_camera.location).to_track_quat('-Z','Y').to_euler()
    _scene.render.filepath=_paths[_name]; bpy.ops.render.render(write_still=True); _written.append(_paths[_name])
bpy.data.objects.remove(_camera,do_unlink=True); bpy.data.cameras.remove(_camera_data)
bpy.data.objects.remove(_light,do_unlink=True); bpy.data.lights.remove(_light_data)
print('SENTINEL_OUTPUT_START'+json.dumps({{'ok':True,'paths':_written}})+'SENTINEL_OUTPUT_END')
'''
        result = await mcp_manager.call_locked("blender", "execute_blender_code", {"code": script})
        data = parse_op_output(result.get("output", ""))
        report = {"ok": bool(data.get("ok")), "paths": data.get("paths", []), "views": list(cls.VIEWS)}
        manifest.stats["render_evidence"] = report
        manifest.record_event("render_evidence_created", details=report)
        return report
