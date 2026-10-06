"""Independent V3 contract and post-commit checks."""
from __future__ import annotations

import math
from dataclasses import asdict
from typing import Any

from .intent import ALLOWED_PRIMITIVES
from .scene import Scene


class V3Preflight:
    @staticmethod
    def run(scene: Scene) -> dict[str, Any]:
        errors: list[str] = []
        ids = {part.id for part in scene.parts}
        if not scene.parts:
            errors.append("scene contains no parts")
        if len(ids) != len(scene.parts):
            errors.append("duplicate part IDs")
        if len({part.canonical_path for part in scene.parts}) != len(scene.parts):
            errors.append("duplicate canonical paths")
        for part in scene.parts:
            geo = part.geometry
            if geo.primitive not in ALLOWED_PRIMITIVES:
                errors.append(f"unsupported primitive {geo.primitive}: {part.id}")
            numbers = part.transform.position + part.transform.rotation + part.transform.scale
            numbers += [value for value in asdict(geo).values() if isinstance(value, (float, int))]
            numbers += geo.size or []
            numbers += part.material.base_color + [part.material.metallic, part.material.roughness,
                                                   part.material.transmission, part.material.emission_strength]
            if not all(isinstance(value, (float, int)) and math.isfinite(value) for value in numbers):
                errors.append(f"non-finite geometry or transform: {part.id}")
            if geo.size and (len(geo.size) != 3 or min(geo.size) <= 0):
                errors.append(f"invalid size: {part.id}")
            if any(value is not None and value <= 0 for value in (geo.radius, geo.depth, geo.major_radius, geo.minor_radius)):
                errors.append(f"invalid radius or depth: {part.id}")
            if part.parent_id and part.parent_id not in ids:
                errors.append(f"unknown parent: {part.id}")
            if not part.material or len(part.material.base_color) != 4:
                errors.append(f"invalid material: {part.id}")
            for mod in part.modifiers:
                if mod.kind not in {"bevel", "solidify", "subdivision", "smooth"}:
                    errors.append(f"unsupported modifier {mod.kind}: {part.id}")
        return {"passed": not errors, "errors": errors, "checked_parts": len(scene.parts)}


async def verify_committed_scene(mcp_manager: Any, scene: Scene, collection_name: str) -> dict[str, Any]:
    from core.blender_ops import parse_op_output

    names = [part.blender_name for part in scene.parts]
    script = (
        "import bpy, json\n"
        f"_names = {names!r}\n_collection = bpy.data.collections.get({collection_name!r})\n"
        "_found = {}\n"
        "for _name in _names:\n"
        "    _o = bpy.data.objects.get(_name)\n"
        "    if _o and _o.type == 'MESH' and _collection and _o.name in _collection.objects:\n"
        "        _v = [_o.matrix_world @ _p.co for _p in _o.data.vertices]\n"
        "        if _v: _found[_name] = {'min': [min(p[i] for p in _v) for i in range(3)], 'max': [max(p[i] for p in _v) for i in range(3)], 'vertices': len(_v), 'part_id': _o.get('v3_part_id'), 'parent': _o.parent.name if _o.parent else None, 'location': list(_o.matrix_world.translation), 'materials': len(_o.data.materials), 'modifiers': [m.type for m in _o.modifiers]}\n"
        "print('SENTINEL_OUTPUT_START' + json.dumps({'ok': True, 'objects': _found}) + 'SENTINEL_OUTPUT_END')\n"
    )
    response = await mcp_manager.call_locked("blender", "execute_blender_code", {"code": script})
    payload = parse_op_output(response.get("output", ""))
    found = payload.get("objects", {}) if payload.get("ok") else {}
    errors = [f"missing Blender mesh: {name}" for name in names if name not in found]
    by_id = {part.id: part for part in scene.parts}
    for part in scene.parts:
        if part.blender_name in found:
            item = found[part.blender_name]
            part.readback_bbox = {key: item[key] for key in ("min", "max")}
            if item.get('part_id') != part.id:
                errors.append(f"Blender identity mismatch: {part.id}")
            parent_name = by_id[part.parent_id].blender_name if part.parent_id else collection_name + '_Root'
            if item.get('parent') != parent_name:
                errors.append(f"Blender parent mismatch: {part.id}")
            if item.get('materials', 0) < 1:
                errors.append(f"Blender material missing: {part.id}")
            if any(abs(float(item['location'][axis]) - part.transform.position[axis]) > .001 for axis in range(3)):
                errors.append(f"Blender placement mismatch: {part.id}")
            expected_mods = {'bevel': 'BEVEL', 'subdivision': 'SUBSURF', 'solidify': 'SOLIDIFY'}
            missing_mods = [mod.kind for mod in part.modifiers if mod.kind in expected_mods and expected_mods[mod.kind] not in item.get('modifiers', [])]
            if missing_mods:
                errors.append(f"Blender modifiers missing on {part.id}: {missing_mods}")
    if found and scene.overall_extent_m:
        width = max(max(box["max"][axis] for box in found.values()) - min(box["min"][axis] for box in found.values()) for axis in (0, 1))
        if width > scene.overall_extent_m + .005:
            errors.append(f"Blender width {width:.4f} exceeds {scene.overall_extent_m:.4f} m")
    return {"passed": not errors, "errors": errors, "expected_meshes": len(names), "found_meshes": len(found)}
