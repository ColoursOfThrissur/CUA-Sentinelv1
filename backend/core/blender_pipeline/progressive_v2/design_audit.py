"""Pre-commit audit for a proposed static scene plan.

This is deliberately deterministic and evidence-based: it reports what the
plan contains, rather than asking another model to invent a different design.
"""

from __future__ import annotations

from typing import Any, Dict, List

from .design_fidelity import DesignFidelityValidator
from .node_types import NodeKind, PrimitiveType, SocketType
from .stages.stage4_resolver import Stage4Resolver
from .transforms import _mat4_transform_point


class DesignProposalAudit:
    """Find missing, implausible, or envelope-breaking plan details pre-commit."""

    @classmethod
    def run(cls, manifest: Any) -> Dict[str, Any]:
        errors = list(DesignFidelityValidator.validate(manifest))
        warnings: List[str] = []
        checks: List[str] = ["explicit_requirements", "radial_branch_orientation", "model_envelope"]

        # Verify the typed prompt contract after the deterministic stages have
        # resolved it.  This is intentionally geometry-agnostic so it applies
        # equally to furniture, machinery, characters, and scene props.
        for node in manifest.nodes.values():
            contract = (getattr(node, "stage_outputs", {}) or {}).get("spatial_contract", {}) or {}
            relation = contract.get("relation")
            orientation = contract.get("orientation")
            attachment = getattr(node, "attachment", None)
            socket = getattr(attachment, "socket_type", None)
            if relation in {"recessed", "inside_host"} and socket != SocketType.INSET:
                errors.append(f"spatial contract '{relation}' was not resolved for '{node.label}'")
            if relation == "radial_group" and socket != SocketType.RADIAL:
                errors.append(f"spatial contract 'radial_group' was not resolved for '{node.label}'")
            if orientation and getattr(node, "geometry", None):
                axis = ((getattr(node, "stage_outputs", {}) or {}).get("decomposition_hint", {}) or {}).get("length_axis")
                if orientation == "horizontal" and axis not in {"x", "y"}:
                    errors.append(f"spatial contract 'horizontal' has no horizontal axis for '{node.label}'")
                if orientation == "vertical" and axis != "z":
                    errors.append(f"spatial contract 'vertical' has no vertical axis for '{node.label}'")

        for parent in manifest.nodes.values():
            children = [manifest.nodes[cid] for cid in parent.children_ids if cid in manifest.nodes]
            radial = [child for child in children if child.kind == NodeKind.ASSEMBLY and child.attachment
                      and child.attachment.socket_type == SocketType.RADIAL]
            if len(radial) >= 2:
                for branch in radial:
                    direct = [manifest.nodes[cid] for cid in branch.children_ids if cid in manifest.nodes]
                    root = next((child for child in direct if child.kind == NodeKind.PART and child.attachment.socket_type == SocketType.ROOT), None)
                    terminal = next((child for child in direct if child.kind == NodeKind.PART and child.attachment.socket_type == SocketType.TOP_CENTER
                                     and child.geometry and child.geometry.primitive in {PrimitiveType.TORUS, PrimitiveType.CIRCLE}), None)
                    if root and root.geometry and root.geometry.primitive in {
                        PrimitiveType.CYLINDER, PrimitiveType.CONE, PrimitiveType.CAPSULE, PrimitiveType.PRISM,
                    }:
                        axis = (root.stage_outputs.get("decomposition_hint", {}) or {}).get("length_axis")
                        if axis not in {"x", "y"}:
                            errors.append(f"radial branch '{branch.label}' has a Z-oriented elongated root '{root.label}'")
                    if terminal:
                        errors.append(f"radial branch '{branch.label}' stacks ring '{terminal.label}' above its root instead of attaching it at the branch end")

            # A U-shaped root explicitly defines a fork opening.  An INSET
            # child must fit between those forks; testing only global overlap
            # misses the common case where it passes through both sides.
            u_root = next((child for child in children if child.kind == NodeKind.PART and child.geometry
                           and child.geometry.primitive == PrimitiveType.U_SHAPE
                           and child.attachment.socket_type == SocketType.ROOT), None)
            inset_children = [child for child in children if child.kind == NodeKind.ASSEMBLY and child.attachment
                              and child.attachment.socket_type == SocketType.INSET]
            if u_root and inset_children:
                major = float(getattr(u_root.geometry, "major_radius", 0.0) or 0.0)
                minor = float(getattr(u_root.geometry, "minor_radius", 0.0) or 0.0)
                opening = max(0.0, 2.0 * (major - minor))
                for inset in inset_children:
                    if opening <= 0:
                        continue
                    # Planning intentionally runs off-scene.  Its legacy
                    # simulated executor used to attach a placeholder 1m box
                    # to every node, so an assembly's cached bounding_box is
                    # not evidence of its real geometry.  Rebuild the local
                    # aggregate from resolved Stage 2 geometry and transforms.
                    resolved_bbox = Stage4Resolver._get_assembly_aggregate_bbox(inset, manifest)
                    if resolved_bbox is not None:
                        width = resolved_bbox.size_x
                    else:
                        inset_bbox = getattr(inset, "bounding_box", None)
                        if not inset_bbox:
                            continue
                        width = float(inset_bbox["max"][0]) - float(inset_bbox["min"][0])
                    if width > opening * 1.02:
                        errors.append(
                            f"inset assembly '{inset.label}' is {width:.3g}m wide but U-shaped host "
                            f"'{u_root.label}' has only {opening:.3g}m usable fork opening"
                        )

        contract = (getattr(manifest, "stats", {}) or {}).get("model_contract", {})
        # Reconstruct part bounds from resolved geometry rather than trusting
        # a simulated executor placeholder.  This keeps off-scene transaction
        # planning numerically equivalent to the scene that will be committed.
        leaf_boxes = []
        for node in manifest.nodes.values():
            if getattr(node, "kind", None) != NodeKind.PART:
                continue
            stage2 = (getattr(node, "stage_outputs", {}) or {}).get("stage2")
            if not getattr(node, "geometry", None) or not isinstance(stage2, dict):
                cached = getattr(node, "bounding_box", None)
                if cached:
                    leaf_boxes.append(cached)
                continue
            local_bbox = Stage4Resolver._get_child_bbox(node)
            matrix = None
            state = getattr(node, "transform_state", None)
            if state and getattr(state, "world_matrix", None):
                matrix = state.world_matrix.matrix
            if matrix is None:
                matrix = [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0],
                          [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]]
            corners = [
                _mat4_transform_point(matrix, [x, y, z])
                for x in (local_bbox.min_x, local_bbox.max_x)
                for y in (local_bbox.min_y, local_bbox.max_y)
                for z in (local_bbox.min_z, local_bbox.max_z)
            ]
            leaf_boxes.append({
                "min": [min(corner[i] for corner in corners) for i in range(3)],
                "max": [max(corner[i] for corner in corners) for i in range(3)],
            })
        try:
            anchor = float(contract.get("overall_extent_m"))
        except (TypeError, ValueError):
            anchor = 0.0
        if leaf_boxes and anchor > 0:
            low = [min(float(box["min"][i]) for box in leaf_boxes) for i in range(3)]
            high = [max(float(box["max"][i]) for box in leaf_boxes) for i in range(3)]
            extents = [high[i] - low[i] for i in range(3)]
            maximum = max(extents)
            if maximum > anchor * 1.25:
                warnings.append(
                    f"proposed model span {maximum:.3g}m exceeds its {anchor:.3g}m scale anchor by more than 25%"
                )

        return {"schema_version": 1, "checks": checks, "errors": errors, "warnings": warnings,
                "passed": not errors, "needs_scale_review": bool(warnings)}

    @classmethod
    def fit_to_scale_contract(cls, manifest: Any) -> Dict[str, Any]:
        """Uniformly fit a frozen scene plan to its requested overall extent.

        Scaling at the model root preserves every local relationship and is
        safe for arbitrary geometry, nested assemblies, and future modifiers.
        It is a last deterministic guard after independent per-part estimates.
        """
        contract = (getattr(manifest, "stats", {}) or {}).get("model_contract", {})
        try:
            anchor = float(contract.get("overall_extent_m"))
        except (TypeError, ValueError):
            return {}
        if anchor <= 0:
            return {}
        boxes = cls._resolved_leaf_boxes(manifest)
        if not boxes:
            return {}
        low = [min(float(box["min"][i]) for box in boxes) for i in range(3)]
        high = [max(float(box["max"][i]) for box in boxes) for i in range(3)]
        span = max(high[i] - low[i] for i in range(3))
        if span <= anchor * 1.001:
            return {}
        root = manifest.get_root()
        if not getattr(root, "transform_state", None) or not root.transform_state.local_transform:
            return {}
        from .transforms import LocalTransform
        factor = anchor / span
        local = root.transform_state.local_transform
        root.transform_state.set_local_transform(LocalTransform(
            position=list(local.position), rotation=list(local.rotation),
            scale=[value * factor for value in local.scale],
        ), force=root.transform_state.frozen)
        manifest.propagate_transforms_from(root.node_id)
        return {"original_span_m": span, "target_extent_m": anchor, "uniform_factor": factor}

    @classmethod
    def _resolved_leaf_boxes(cls, manifest: Any) -> List[Dict[str, List[float]]]:
        """Return geometry-derived world boxes, avoiding simulator placeholders."""
        boxes: List[Dict[str, List[float]]] = []
        for node in manifest.nodes.values():
            if getattr(node, "kind", None) != NodeKind.PART:
                continue
            stage2 = (getattr(node, "stage_outputs", {}) or {}).get("stage2")
            if not getattr(node, "geometry", None) or not isinstance(stage2, dict):
                continue
            local_bbox = Stage4Resolver._get_child_bbox(node)
            state = getattr(node, "transform_state", None)
            matrix = getattr(getattr(state, "world_matrix", None), "matrix", None)
            if matrix is None:
                matrix = [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]]
            corners = [_mat4_transform_point(matrix, [x, y, z])
                       for x in (local_bbox.min_x, local_bbox.max_x)
                       for y in (local_bbox.min_y, local_bbox.max_y)
                       for z in (local_bbox.min_z, local_bbox.max_z)]
            boxes.append({"min": [min(p[i] for p in corners) for i in range(3)],
                          "max": [max(p[i] for p in corners) for i in range(3)]})
        return boxes
