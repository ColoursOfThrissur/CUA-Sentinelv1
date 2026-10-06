"""Blender-state readback for committed V2 scene transactions."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .node_types import NodeKind, PrimitiveType, SocketType
from .scene_ir import canonical_node_path


class SceneReadbackVerifier:
    """Verify Blender state independently from the compiler receipt."""

    def __init__(self, mcp_manager: Any, dimension_relative_tolerance: float = 0.15) -> None:
        self.mcp_manager = mcp_manager
        self.dimension_relative_tolerance = dimension_relative_tolerance

    @staticmethod
    def _parse_output(raw_stdout: str) -> Dict[str, Any]:
        """Extract and parse structured Sentinel JSON from Blender stdout."""
        if not raw_stdout:
            return {"ok": False, "objects": []}
        start_tag = "SENTINEL_OUTPUT_START"
        end_tag = "SENTINEL_OUTPUT_END"
        start_idx = raw_stdout.find(start_tag)
        end_idx = raw_stdout.find(end_tag)
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            json_str = raw_stdout[start_idx + len(start_tag):end_idx].strip()
            try:
                return json.loads(json_str)
            except Exception:
                pass
        return {"ok": False, "objects": []}

    async def verify(self, manifest: Any, executor: Any) -> Dict[str, Any]:

        script = f'''
import bpy, json
_collection_name = {executor._collection_name!r}
_collection = bpy.data.collections.get(_collection_name)
_objects = []
if _collection:
    for _obj in _collection.all_objects:
        _materials = []
        _pbr = {{}}
        if getattr(_obj, 'data', None) and hasattr(_obj.data, 'materials'):
            _materials = [m.name for m in _obj.data.materials if m]
            if _obj.data.materials and _obj.data.materials[0] and _obj.data.materials[0].use_nodes:
                _bsdf=next((n for n in _obj.data.materials[0].node_tree.nodes if n.type=='BSDF_PRINCIPLED'),None)
                if _bsdf:
                    for _key,_aliases in {{'base_color':['Base Color'],'metallic':['Metallic'],'roughness':['Roughness'],'transmission':['Transmission Weight','Transmission'],'alpha':['Alpha']}}.items():
                        _socket=next((_bsdf.inputs.get(a) for a in _aliases if _bsdf.inputs.get(a)),None)
                        if _socket:
                            _value=_socket.default_value
                            _pbr[_key]=list(_value) if hasattr(_value,'__len__') else float(_value)
        _eval_obj = _obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
        _bound_box = getattr(_eval_obj, 'bound_box', None)
        _world_corners = [_obj.matrix_world @ __import__('mathutils').Vector(corner) for corner in _bound_box] if _bound_box else []
        _world_bounds = {{
            'min': [min(point[axis] for point in _world_corners) for axis in range(3)],
            'max': [max(point[axis] for point in _world_corners) for axis in range(3)],
        }} if _world_corners else None
        _world_dimensions = [
            _world_bounds['max'][axis] - _world_bounds['min'][axis]
            for axis in range(3)
        ] if _world_bounds else list(_eval_obj.dimensions)
        _volume = None
        _is_manifold = None
        if _obj.type == 'MESH':
            _m_eval = _eval_obj.to_mesh()
            try:
                _bm = __import__('bmesh').new()
                _bm.from_mesh(_m_eval)
                _bm.transform(_obj.matrix_world)
                _volume = abs(float(_bm.calc_volume()))
                _is_manifold = bool(all(len(e.link_faces) == 2 for e in _bm.edges))
                if not _is_manifold and getattr(_obj, 'data', None):
                    _bm_base = __import__('bmesh').new()
                    _bm_base.from_mesh(_obj.data)
                    _is_manifold = bool(all(len(e.link_faces) == 2 for e in _bm_base.edges))
                    _bm_base.free()
                _bm.free()
            finally:
                _eval_obj.to_mesh_clear()
        _objects.append({{
            'name': _obj.name,
            'type': _obj.type,
            'node_id': _obj.get('sentinel_node_id'),
            'canonical_path': _obj.get('sentinel_canonical_path'),
            'build_id': _obj.get('sentinel_build_id'),
            'dimensions': _world_dimensions,
            'local_dimensions': list(_eval_obj.dimensions),
            'volume': _volume,
            'is_manifold': _is_manifold,
            'location': list(_obj.matrix_world.translation),
            'world_matrix': [list(row) for row in _obj.matrix_world],
            'world_bounds': _world_bounds,
            'materials': _materials,
            'pbr': _pbr,
            'parent': _obj.parent.name if _obj.parent else None,
            'declared_modifiers': _obj.get('sentinel_declared_modifiers', '[]'),
        }})
print('SENTINEL_OUTPUT_START' + json.dumps({{'ok': bool(_collection), 'collection': _collection_name, 'objects': _objects}}) + 'SENTINEL_OUTPUT_END')
'''
        result = await self.mcp_manager.call_locked(
            "blender", "execute_blender_code", {"code": script}
        )
        observed = self._parse_output(result.get("output", ""))
        findings: List[Dict[str, Any]] = []
        by_node = {
            item.get("node_id"): item
            for item in observed.get("objects", [])
            if item.get("node_id")
        }
        if not observed.get("ok"):
            findings.append(self._finding("error", "collection_missing", executor._collection_name))

        # fit_to_scale_contract applies a uniform factor to the root transform
        # which propagates into every object's local scale before Blender
        # receives it.  Expected dimensions must be scaled by the same factor.
        scale_norm = (getattr(manifest, "stats", {}) or {}).get("scale_normalization") or {}
        scale_factor: float = float(scale_norm.get("uniform_factor", 1.0))

        expected_parts = [
            node for node in manifest.nodes.values()
            if node.kind in (NodeKind.PART, NodeKind.INSTANCE)
            and not (node.attachment and node.attachment.socket_type in (
                SocketType.BOOLEAN_CUT, SocketType.BOOLEAN_UNION, SocketType.BOOLEAN_INTERSECT
            ))
        ]
        for node in expected_parts:
            actual = by_node.get(node.node_id)
            if actual is None:
                findings.append(self._finding("error", "object_missing", node.node_id))
                continue
            expected_path = canonical_node_path(manifest, node.node_id)
            if actual.get("canonical_path") != expected_path:
                findings.append(self._finding(
                    "error", "identity_mismatch", node.node_id,
                    expected=expected_path, actual=actual.get("canonical_path"),
                ))
            # Use local_dimensions (object-space, pre-parent-scale) so that a
            # uniform scale on the assembly empty does not cause false mismatches.
            dimensions = actual.get("local_dimensions") or actual.get("dimensions") or []
            raw_dims = self._expected_dimensions(node.geometry)
            expected_dimensions = (
                [d * scale_factor for d in raw_dims] if raw_dims and scale_factor != 1.0 else raw_dims
            )
            bool_op = self._boolean_operation_for_node(node, manifest)
            is_unmodified = self._is_unmodified_for_tolerance(node, manifest)
            if expected_dimensions is None:
                findings.append(self._finding(
                    "error", "missing_geometry_dimensions", node.node_id,
                    primitive=getattr(getattr(node, "geometry", None), "primitive", None),
                ))
            else:
                dims_match = self._verify_dimensions_for_op(
                    expected_dimensions, dimensions, bool_op, tight=is_unmodified
                )
                if not dims_match:
                    findings.append(self._finding(
                        "error", "dimension_mismatch", node.node_id,
                        expected=expected_dimensions, actual=dimensions,
                        boolean_operation=bool_op,
                        note="local_dimensions (pre-parent-scale)",
                    ))

            # Manifold mesh verification for closed solids only
            prim = getattr(getattr(node, "geometry", None), "primitive", None)
            is_closed_solid = prim not in {
                PrimitiveType.PLANE, PrimitiveType.CIRCLE, PrimitiveType.GRID, PrimitiveType.MONKEY
            }
            if is_closed_solid and actual.get("is_manifold") is False:
                findings.append(self._finding(
                    "error", "non_manifold_mesh", node.node_id,
                    name=actual.get("name"),
                ))

            if node.material is not None and not actual.get("materials"):
                findings.append(self._finding("error", "material_missing", node.node_id))
            elif node.material is not None:
                pbr = actual.get("pbr") or {}
                for field in ("metallic", "roughness", "transmission", "alpha"):
                    got = pbr.get(field)
                    want = float(getattr(node.material, field))
                    if not isinstance(got, (int, float)) or abs(float(got) - want) > 0.025:
                        findings.append(self._finding(
                            "error", "material_value_mismatch", node.node_id,
                            field=field, expected=want, actual=got,
                        ))
                expected_color = self._linear_color(node.material.base_color)
                actual_color = pbr.get("base_color")
                if not isinstance(actual_color, list) or len(actual_color) < 3 or any(
                    abs(float(actual_color[index]) - expected_color[index]) > 0.025
                    for index in range(3)
                ):
                    findings.append(self._finding(
                        "error", "material_color_mismatch", node.node_id,
                        expected=expected_color, actual=actual_color,
                    ))

        duplicate_ids = sorted({
            node_id for node_id in by_node
            if sum(1 for item in observed.get("objects", []) if item.get("node_id") == node_id) > 1
        })
        for node_id in duplicate_ids:
            findings.append(self._finding("error", "duplicate_node_identity", node_id))

        errors = [item for item in findings if item["severity"] == "error"]
        report = {
            "ok": not errors,
            "collection": executor._collection_name,
            "expected_part_count": len(expected_parts),
            "observed_tagged_count": len(by_node),
            "findings": findings,
            "objects": observed.get("objects", []),
        }
        manifest.stats["scene_readback"] = report
        manifest.record_event("scene_readback_verified" if report["ok"] else "scene_readback_failed", details={
            "collection": executor._collection_name,
            "expected_part_count": len(expected_parts),
            "observed_tagged_count": len(by_node),
            "findings": findings,
        })
        if hasattr(manifest, "_build_dir"):
            self._save(report, manifest._build_dir() / "scene_readback.json")
        return report

    @classmethod
    def _boolean_operation_for_node(cls, node: Any, manifest: Any) -> Optional[str]:
        """Resolve the boolean operation targeting this node, if any.

        Checks the frozen scene_plan IR first, then node modifiers,
        then assembly ROOT sibling cutters.
        Returns 'difference', 'union', 'intersect', or None.
        """
        # 1. Source of truth: scene_plan IR stored in manifest stats
        plan = manifest.stats.get("scene_plan", {})
        for b_op in plan.get("boolean_operations", []):
            if b_op.get("target_node_id") == node.node_id:
                return b_op.get("operation")

        # 2. Modifiers on node itself
        for mod in (getattr(node, "modifiers", None) or []):
            m_type = mod.get("type") if isinstance(mod, dict) else getattr(mod, "type", "")
            if str(m_type).upper() == "BOOLEAN":
                return str(mod.get("operation") if isinstance(mod, dict) else getattr(mod, "operation", "difference")).lower()

        # 3. Check if this is the target ROOT sibling of cutters in the assembly
        if getattr(getattr(node, "attachment", None), "socket_type", None) == SocketType.ROOT:
            parent = manifest.nodes.get(node.parent_id) if getattr(node, "parent_id", None) else None
            if parent:
                for child_id in parent.children_ids:
                    if child_id != node.node_id:
                        sib = manifest.nodes.get(child_id)
                        st = getattr(getattr(sib, "attachment", None), "socket_type", None)
                        if st == SocketType.BOOLEAN_CUT:
                            return "difference"
                        elif st == SocketType.BOOLEAN_UNION:
                            return "union"
                        elif st == SocketType.BOOLEAN_INTERSECT:
                            return "intersect"
        return None

    @classmethod
    def _is_cut_target(cls, node: Any, manifest: Any) -> bool:
        """Backward-compatible helper for difference/cut targets."""
        op = cls._boolean_operation_for_node(node, manifest)
        return op == "difference"

    @classmethod
    def _is_unmodified_for_tolerance(cls, node: Any, manifest: Any) -> bool:
        """Bounds-preserving modifiers (BEVEL, WEIGHTED_NORMAL, etc.) do NOT disqualify
        a part from tight tolerance. Only modifiers altering extents trigger loose tolerance.
        """
        bool_op = cls._boolean_operation_for_node(node, manifest)
        _EXTENT_ALTERING_MODIFIERS = {
            "SOLIDIFY", "ARRAY", "MIRROR", "SUBSURF", "SUBDIVISION", "BOOLEAN",
            "DISPLACE", "SCREW", "CURVE", "LATTICE", "SHRINKWRAP", "CAST",
            "SMOOTH", "CORRECTIVE_SMOOTH", "LAPLACIANSMOOTH", "DECIMATE", "SIMPLE_DEFORM",
        }
        node_mods = getattr(node, "modifiers", None) or []
        has_extent_mod = any(
            str(m.get("type") if isinstance(m, dict) else getattr(m, "type", "")).upper() in _EXTENT_ALTERING_MODIFIERS
            for m in node_mods
        )
        return bool_op is None and not has_extent_mod

    def _verify_dimensions_for_op(
        self, expected: List[float], actual: List[float], op: Optional[str], tight: bool = False
    ) -> bool:
        """Verify dimensions according to the specific boolean operation."""
        if op == "difference":
            return self._boolean_dimensions_match(expected, actual)
        elif op == "union":
            # Union expands or maintains bounds: each axis >= want - tolerance
            if len(actual) != 3 or any(not isinstance(value, (int, float)) or value <= 0 for value in actual):
                return False
            return all(
                float(got) >= float(want) * (1.0 - self.dimension_relative_tolerance) - 0.002
                for want, got in zip(expected, actual)
            )
        elif op == "intersect":
            # Intersect shrinks bounds: each axis <= want + tolerance
            if len(actual) != 3 or any(not isinstance(value, (int, float)) or value <= 0 for value in actual):
                return False
            return all(
                float(got) <= float(want) * (1.0 + self.dimension_relative_tolerance) + 0.002
                for want, got in zip(expected, actual)
            )
        else:
            return self._dimensions_match(expected, actual, tight=tight)

    def _dimensions_match(
        self, expected: List[float], actual: List[float], tight: bool = False
    ) -> bool:
        """Strict oriented comparison: preserves axis alignment without sorting.

        Scale-aware tolerance:
        - Relative tolerance: 2% when tight (unmodified parts), 15% when loose.
        - Dynamic floor: scales proportionally to the feature size for small parts
          (min 0.3mm to respect float/mesh limits, capped at 1.0mm tight / 2.0mm loose),
          ensuring sub-centimeter features don't drown in a fixed floor while large
          features are guarded tightly against axis flips and permutations.
        """
        if len(actual) != 3 or any(not isinstance(value, (int, float)) or value < 0 for value in actual):
            return False
        tol_rel = 0.02 if tight else self.dimension_relative_tolerance
        max_floor = 0.001 if tight else 0.002
        min_floor = 0.0003 if tight else 0.0005
        return all(
            abs(float(want) - float(got)) <= max(
                min(max_floor, max(min_floor, abs(float(want)) * 0.20)),
                abs(float(want)) * tol_rel,
            )
            for want, got in zip(expected, actual)
        )

    def _boolean_dimensions_match(self, expected: List[float], actual: List[float]) -> bool:
        """Check that boolean-cut object bounds lie within base bounds + tolerance and volume change is plausible."""
        if len(actual) != 3 or any(not isinstance(value, (int, float)) or value <= 0 for value in actual):
            return False
        # Each axis must not exceed expected bounds plus tolerance
        within_bounds = all(
            float(got) <= float(want) * (1.0 + self.dimension_relative_tolerance) + 0.002
            and float(got) >= float(want) * 0.05
            for want, got in zip(expected, actual)
        )
        if not within_bounds:
            return False
        # Plausible volume verification: cut volume must not exceed initial bounding volume
        expected_vol = float(expected[0]) * float(expected[1]) * float(expected[2])
        actual_vol = float(actual[0]) * float(actual[1]) * float(actual[2])
        if expected_vol > 0:
            vol_ratio = actual_vol / expected_vol
            # A difference cut must not increase volume beyond upper tolerance bound
            if vol_ratio > (1.0 + self.dimension_relative_tolerance) ** 3:
                return False
        return True

    @staticmethod
    def _polygon_xy_bounds(radius: float, segments: int) -> Tuple[float, float, float, float]:
        """Calculate exact object-space (min_x, max_x, min_y, max_y) for Blender's primitive circle-based meshes."""
        n = max(3, int(segments))
        angles = [math.pi / 2.0 + 2.0 * math.pi * i / n for i in range(n)]
        xs = [radius * math.cos(a) for a in angles]
        ys = [radius * math.sin(a) for a in angles]
        return min(xs), max(xs), min(ys), max(ys)

    @staticmethod
    def _torus_xy_bounds(outer_radius: float, segments: int) -> Tuple[float, float, float, float]:
        """Calculate exact object-space (min_x, max_x, min_y, max_y) for Blender's primitive torus mesh."""
        n = max(3, int(segments))
        angles = [2.0 * math.pi * i / n for i in range(n)]
        xs = [outer_radius * math.cos(a) for a in angles]
        ys = [outer_radius * math.sin(a) for a in angles]
        return min(xs), max(xs), min(ys), max(ys)

    @classmethod
    def _expected_dimensions(cls, geometry: Any) -> Optional[List[float]]:
        primitive = geometry.primitive
        if primitive in {PrimitiveType.BOX, PrimitiveType.PLANE, PrimitiveType.WEDGE}:
            return list(geometry.size or [])
        if primitive == PrimitiveType.GRID:
            s = list(geometry.size or [1.0, 1.0])
            return [s[0], s[1], 0.0]
        if primitive == PrimitiveType.CYLINDER:
            min_x, max_x, min_y, max_y = cls._polygon_xy_bounds(geometry.radius or 0.0, geometry.segments or 32)
            return [max_x - min_x, max_y - min_y, geometry.depth]
        if primitive == PrimitiveType.CONE:
            r1 = geometry.radius if geometry.radius is not None else 0.0
            r2 = getattr(geometry, "radius2", None) or 0.0
            r_max = max(r1, r2)
            min_x, max_x, min_y, max_y = cls._polygon_xy_bounds(r_max, geometry.segments or 32)
            return [max_x - min_x, max_y - min_y, geometry.depth]
        if primitive == PrimitiveType.PYRAMID:
            min_x, max_x, min_y, max_y = cls._polygon_xy_bounds(geometry.radius or 0.0, 4)
            return [max_x - min_x, max_y - min_y, geometry.depth]
        if primitive == PrimitiveType.PRISM:
            min_x, max_x, min_y, max_y = cls._polygon_xy_bounds(geometry.radius or 0.0, geometry.segments or 6)
            return [max_x - min_x, max_y - min_y, geometry.depth]
        if primitive == PrimitiveType.SPHERE:
            min_x, max_x, min_y, max_y = cls._polygon_xy_bounds(geometry.radius or 0.0, geometry.segments or 32)
            return [max_x - min_x, max_y - min_y, 2 * geometry.radius]
        if primitive == PrimitiveType.HEMISPHERE:
            min_x, max_x, min_y, max_y = cls._polygon_xy_bounds(geometry.radius or 0.0, geometry.segments or 32)
            return [max_x - min_x, max_y - min_y, geometry.radius]
        if primitive == PrimitiveType.CAPSULE:
            min_x, max_x, min_y, max_y = cls._polygon_xy_bounds(geometry.radius or 0.0, geometry.segments or 32)
            return [max_x - min_x, max_y - min_y, geometry.depth]
        if primitive == PrimitiveType.TORUS:
            outer = (geometry.major_radius or 0.5) + (geometry.minor_radius or 0.1)
            min_x, max_x, min_y, max_y = cls._torus_xy_bounds(outer, geometry.segments or 32)
            return [max_x - min_x, max_y - min_y, 2 * (geometry.minor_radius or 0.1)]
        if primitive == PrimitiveType.U_SHAPE:
            outer = geometry.major_radius + geometry.minor_radius
            return [2 * outer, 2 * geometry.minor_radius, outer]
        if primitive == PrimitiveType.CIRCLE:
            min_x, max_x, min_y, max_y = cls._polygon_xy_bounds(geometry.radius or 0.0, geometry.segments or 32)
            return [max_x - min_x, max_y - min_y, 0.0]
        if primitive == PrimitiveType.MONKEY:
            return [2.73438, 1.70312, 1.96876]
        return None

    @staticmethod
    def _finding(severity: str, code: str, node_id: str, **details: Any) -> Dict[str, Any]:
        return {"severity": severity, "code": code, "node_id": node_id, **details}

    @staticmethod
    def _linear_color(color: List[float]) -> List[float]:
        def channel(component: float) -> float:
            return component / 12.92 if component <= 0.04045 else ((component + 0.055) / 1.055) ** 2.4
        return [channel(float(component)) for component in color[:3]]

    @staticmethod
    def _save(report: Dict[str, Any], path: Path) -> None:
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        temporary.replace(path)


def _expected_dimensions(geometry: Any) -> Optional[List[float]]:
    """Module-level helper resolving expected bounding dimensions for geometry spec."""
    return SceneReadbackVerifier._expected_dimensions(geometry)


def _expected_local_bounds(geometry: Any) -> Tuple[List[float], List[float]]:
    """Module-level helper resolving expected local origin-relative min and max bounds."""
    from .stages.stage4_resolver import BBox
    bbox = BBox.from_geometry(geometry, {})
    return [bbox.min_x, bbox.min_y, bbox.min_z], [bbox.max_x, bbox.max_y, bbox.max_z]

