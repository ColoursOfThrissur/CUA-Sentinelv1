"""Bounded deterministic repairs applied before the V2 scene plan freezes."""

from __future__ import annotations

from typing import Any, Dict, List

from .node_types import NodeKind, PrimitiveType, SocketType


class ScenePlanRepairer:
    """Repair schema-shape defects without inventing missing design intent."""

    @classmethod
    def apply(cls, manifest: Any) -> Dict[str, Any]:
        repairs: List[Dict[str, Any]] = []
        for node in manifest.nodes.values():
            geometry = getattr(node, "geometry", None)
            if geometry and getattr(geometry, "primitive", None) == PrimitiveType.PLANE:
                size = list(geometry.size or [])
                if len(size) == 2:
                    thickness = float(geometry.depth or 0.002)
                    if thickness <= 0:
                        thickness = 0.002
                    geometry.size = [float(size[0]), float(size[1]), thickness]
                    event = {
                        "field": "size", "rule": "plane_xy_to_thin_panel",
                        "got": size, "normalized": list(geometry.size),
                    }
                    events = getattr(geometry, "normalization_events", None)
                    if events is None:
                        events = []
                        geometry.normalization_events = events
                    if event not in events:
                        events.append(event)
                    repairs.append({"node_id": node.node_id, **event})
                modifiers = list(getattr(node, "modifiers", None) or [])
                retained = []
                removed = []
                for modifier in modifiers:
                    mod_type = modifier.get("type") if isinstance(modifier, dict) else getattr(getattr(modifier, "type", None), "value", None)
                    if mod_type == "solidify":
                        removed.append(mod_type)
                    else:
                        retained.append(modifier)
                if removed:
                    node.modifiers = retained
                    repairs.append({
                        "node_id": node.node_id, "field": "modifiers",
                        "rule": "thin_panel_already_has_thickness",
                        "got": removed, "normalized": [],
                    })

            material = getattr(node, "material", None)
            if material:
                for field in (
                    "metallic", "roughness", "transmission", "subsurface",
                    "clearcoat", "sheen", "specular", "specular_tint", "alpha", "anisotropy",
                ):
                    value = getattr(material, field, None)
                    if isinstance(value, (int, float)) and not 0.0 <= value <= 1.0:
                        normalized = min(1.0, max(0.0, float(value)))
                        setattr(material, field, normalized)
                        repairs.append({
                            "node_id": node.node_id, "field": f"material.{field}",
                            "rule": "unit_interval_clamp", "got": value, "normalized": normalized,
                        })

        # Repeated placement slots are mechanical when the sibling group is
        # complete: preserve order and fill a single shared count/index set.
        for parent in manifest.nodes.values():
            for socket, count_field, index_field in (
                (SocketType.RADIAL, "radial_count", "radial_index"),
                (SocketType.RADIAL_BRIDGE, "radial_count", "radial_index"),
                (SocketType.ARRAY_MEMBER, "array_count", "array_index"),
            ):
                children = [
                    manifest.nodes[child_id] for child_id in parent.children_ids
                    if child_id in manifest.nodes
                    and manifest.nodes[child_id].attachment
                    and manifest.nodes[child_id].attachment.socket_type == socket
                ]
                if not children:
                    continue
                for index, child in enumerate(children):
                    before = [getattr(child.attachment, count_field), getattr(child.attachment, index_field)]
                    setattr(child.attachment, count_field, len(children))
                    setattr(child.attachment, index_field, index)
                    after = [len(children), index]
                    if before != after:
                        repairs.append({
                            "node_id": child.node_id, "field": socket.value,
                            "rule": "stable_sibling_slots", "got": before, "normalized": after,
                        })

        report = {"repair_count": len(repairs), "repairs": repairs}
        if repairs and hasattr(manifest, "record_event"):
            manifest.record_event("scene_plan_repaired", details=report)
        return report
