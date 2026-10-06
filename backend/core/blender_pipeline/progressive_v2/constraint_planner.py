"""Deterministic structural constraints inferred from an approved scene tree.

This module is intentionally conservative: it only recognises a pattern when
both the containment topology *and* the user's requested physical behaviour
agree.  It does not use part labels as geometric truth.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from .node_types import NodeKind, PrimitiveType, SocketType


class StructuralConstraintPlanner:
    """Annotate a manifest with constraints consumed by Stage 4.

    The first supported pattern is a radial set of endpoint-connected struts:
    tripods, stands, braces, and similar structures.  It replaces the unsafe
    interpretation of a radial ROOT cylinder as several detached vertical
    cylinders.
    """

    @classmethod
    def apply(cls, manifest: Any) -> Dict[str, Any]:
        report: Dict[str, Any] = {"schema_version": 1, "patterns": [], "definitions": {}, "material_coverage": {}}
        prompt = (getattr(manifest, "prompt", "") or "").lower()
        cls._apply_prompt_spatial_contracts(manifest, report)
        # Endpoint struts are for load-bearing, ground-contact structures.
        # Do not infer that intent from a generic "outward" arm plus an
        # unrelated "downward" detail (for example, a drone camera bracket).
        # Such a shortcut converts a correctly declared radial group into a
        # vertical stack and destroys the intended orbit.
        support_noun = any(token in prompt for token in (
            "tripod", "legs", "leg ", "stand", "pedestal", "ground support",
        ))
        ground_contact = any(token in prompt for token in (
            "ground", "floor", "resting", "stands on", "stable base",
        ))
        wants_splayed_support = support_noun and ground_contact and any(token in prompt for token in (
            "splay", "outward", "angled", "angle outward", "brace", "legs",
        ))

        for parent in manifest.nodes.values():
            children = [manifest.nodes[cid] for cid in parent.children_ids if cid in manifest.nodes]
            roots = [n for n in children if n.kind == NodeKind.PART and n.attachment.socket_type == SocketType.ROOT]
            radial_assemblies = [
                n for n in children
                if n.kind == NodeKind.ASSEMBLY and n.attachment.socket_type == SocketType.RADIAL
            ]
            if not wants_splayed_support or len(roots) != 1 or len(radial_assemblies) < 3:
                continue
            leaves = [cls._single_elongated_leaf(a, manifest) for a in radial_assemblies]
            if any(leaf is None for leaf in leaves):
                continue

            # The root is the hub.  Every radial assembly is anchored at its
            # lower face, then its leaf is aimed from that point to a radial
            # ground point.  This works for any count, not just tripods.
            hub = roots[0]
            count = len(radial_assemblies)
            definition_key = "radial_strut:" + ":".join(sorted(
                leaf.geometry.primitive.value for leaf in leaves if leaf and leaf.geometry
            ))
            report["definitions"][definition_key] = {
                "count": count,
                "canonical_node_id": leaves[0].node_id,
                "members": [leaf.node_id for leaf in leaves],
            }
            for index, (assembly, leaf) in enumerate(zip(radial_assemblies, leaves)):
                # The radial assembly is a placement group, not a physical
                # orbit around the hub.  The endpoint solver owns its spread.
                assembly.attachment.socket_type = SocketType.BOTTOM_CENTER
                assembly.stage_outputs.setdefault("structural_pattern", {})
                assembly.stage_outputs["structural_pattern"].update({
                    "kind": "radial_strut_group", "index": index, "count": count,
                    "hub_node_id": hub.node_id,
                })
                hint = leaf.stage_outputs.setdefault("decomposition_hint", {})
                hint["endpoint_constraint"] = {
                    "kind": "radial_strut",
                    "hub_node_id": hub.node_id,
                    "radial_index": index,
                    "radial_count": count,
                    # A stable proportion: broad enough for a real support,
                    # short enough to remain a leg rather than a flat spoke.
                    "spread_ratio": 0.62,
                }
                hint.setdefault("repeat_key", definition_key)
            report["patterns"].append({
                "kind": "radial_strut_group", "parent_id": parent.node_id,
                "hub_node_id": hub.node_id, "count": count,
            })
        cls._apply_radial_repeat_definitions(manifest, report)
        cls._apply_explicit_sibling_repeat_definitions(manifest, report)
        cls._apply_longitudinal_attachments(manifest, report)
        cls._apply_inset_fit_dependencies(manifest, report)
        cls._assign_materials_and_finishing(manifest, report)
        parts = [node for node in manifest.nodes.values() if node.kind == NodeKind.PART]
        hinted = [
            node for node in parts
            if ((getattr(node, "stage_outputs", {}) or {}).get("decomposition_hint", {}) or {}).get("material_hint")
            or getattr(node, "material", None)
        ]
        report["material_coverage"] = {
            "part_count": len(parts), "specified_part_count": len(hinted),
            "missing_node_ids": [node.node_id for node in parts if node not in hinted],
        }
        return report

    @classmethod
    def _apply_prompt_spatial_contracts(cls, manifest: Any, report: Dict[str, Any]) -> None:
        """Compile direct spatial language into closed, solver-ready constraints.

        This is deliberately relation-driven rather than category-driven: it
        works for any named elongated part, nested enclosure, recessed detail,
        or repeated radial assembly.
        """
        prompt = str(getattr(manifest, "prompt", "") or "")
        clauses = [c.strip() for c in re.split(r"[.;\n]+", prompt.lower()) if c.strip()]
        changed: List[Dict[str, Any]] = []
        for node in manifest.nodes.values():
            label = str(getattr(node, "label", getattr(node, "node_id", "")))
            tokens = set(re.findall(r"[a-z]+", label.lower()))
            evidence = " ".join(c for c in clauses if tokens & set(re.findall(r"[a-z]+", c)))
            # To determine orientation evidence without bleeding clauses that merely
            # reference this part (e.g. "attached to the lower arm"), prioritize
            # clauses where the part's full label tokens appear, and check direct modifiers.
            label_lower = label.lower().replace("_", " ")
            has_explicit_vertical = any(
                re.search(rf"\bvertical\b.*\b{re.escape(tok)}\b", c) or re.search(rf"\b{re.escape(tok)}\b.*\bvertical\b", c)
                for tok in ([label_lower] if len(label_lower.split()) > 1 else [label_lower])
                for c in clauses
            ) or (f"vertical {label_lower}" in prompt.lower())
            has_explicit_horizontal = any(
                re.search(rf"\bhorizontal\b.*\b{re.escape(tok)}\b", c) or re.search(rf"\b{re.escape(tok)}\b.*\bhorizontal\b", c)
                for tok in ([label_lower] if len(label_lower.split()) > 1 else [label_lower])
                for c in clauses
            ) or (f"horizontal {label_lower}" in prompt.lower())

            outputs = getattr(node, "stage_outputs", None)
            if not isinstance(outputs, dict):
                outputs = {}
                node.stage_outputs = outputs
            hint = outputs.setdefault("decomposition_hint", {})
            if node.kind == NodeKind.PART and node.geometry:
                if (
                    node.geometry.primitive in {PrimitiveType.TORUS, PrimitiveType.CIRCLE}
                    and ("horizontal" in evidence or "flat" in evidence or "ring" in evidence or "guard" in evidence)
                ):
                    outputs.setdefault("spatial_contract", {})["orientation"] = "flat_horizontal"
                    changed.append({"node": node.node_id, "relation": "flat_horizontal"})
                
                # Check orientation contracts: give explicit label-level modifiers priority
                is_vert = has_explicit_vertical or ("vertical" in evidence and not has_explicit_horizontal and "horizontal" not in evidence)
                is_horiz = has_explicit_horizontal or ("horizontal" in evidence and not has_explicit_vertical and "vertical" not in evidence)
                if not is_vert and not is_horiz:
                    if "vertical" in evidence and "horizontal" in evidence:
                        # Ambiguous clause evidence: check which appears closest to the label
                        best_clause = next((c for c in clauses if label_lower in c), evidence)
                        is_vert = "vertical" in best_clause and "horizontal" not in best_clause
                        is_horiz = "horizontal" in best_clause and "vertical" not in best_clause

                is_flat_disc = (
                    node.geometry.primitive == PrimitiveType.CYLINDER
                    and (
                        "flat" in evidence or "plate" in evidence or "disc" in evidence
                        or "disk" in evidence or "cushion" in evidence or "seat" in evidence
                        or "flat horizontally" in evidence or "flat horizontal" in evidence
                    )
                )
                if is_flat_disc and is_horiz:
                    outputs.setdefault("spatial_contract", {})["orientation"] = "flat_horizontal"
                    changed.append({"node": node.node_id, "relation": "flat_horizontal"})
                elif is_horiz and node.geometry.primitive in {
                    PrimitiveType.CYLINDER, PrimitiveType.CONE, PrimitiveType.CAPSULE, PrimitiveType.PRISM,
                }:
                    socket = node.attachment.socket_type if node.attachment else None
                    if socket in (
                        SocketType.FRONT_FACE, SocketType.BACK_FACE,
                        SocketType.FRONT_CENTER, SocketType.BACK_CENTER,
                    ):
                        hint["length_axis"] = "y"
                    elif socket in (
                        SocketType.LEFT_FACE, SocketType.RIGHT_FACE,
                        SocketType.LEFT_CENTER, SocketType.RIGHT_CENTER,
                    ):
                        hint["length_axis"] = "x"
                    else:
                        hint["length_axis"] = "x"
                    outputs.setdefault("spatial_contract", {})["orientation"] = "horizontal"
                    changed.append({"node": node.node_id, "relation": "horizontal"})
                elif is_vert and node.geometry.primitive in {
                    PrimitiveType.CYLINDER, PrimitiveType.CONE, PrimitiveType.CAPSULE, PrimitiveType.PRISM,
                }:
                    hint["length_axis"] = "z"
                    outputs.setdefault("spatial_contract", {})["orientation"] = "vertical"
                    changed.append({"node": node.node_id, "relation": "vertical"})
                if "recessed" in evidence and node.attachment and node.attachment.socket_type != SocketType.ROOT:
                    node.attachment.socket_type = SocketType.INSET
                    outputs.setdefault("stage3", {})["inset_face"] = "front" if "front" in evidence else "top"
                    outputs["stage3"]["inset_depth"] = 0.002
                    outputs.setdefault("spatial_contract", {})["relation"] = "recessed"
                    changed.append({"node": node.node_id, "relation": "recessed"})

        # A flat annular enclosure plus multiple tapered members is a generic
        # coplanar rotating group (fan, rotor, impeller, dial pointer group).
        # Propagate the declared plane to its members from topology; do not
        # depend on names such as "blade" or on a specific model category.
        for assembly in manifest.nodes.values():
            if assembly.kind != NodeKind.ASSEMBLY:
                continue
            children = [manifest.nodes[c] for c in assembly.children_ids if c in manifest.nodes]
            planar_hosts = [
                child for child in children
                if child.kind == NodeKind.PART
                and child.geometry
                and child.geometry.primitive == PrimitiveType.TORUS
                and child.stage_outputs.get("spatial_contract", {}).get("orientation") == "flat_horizontal"
            ]
            tapered_members = [
                child for child in children
                if child.kind == NodeKind.PART
                and child.geometry
                and child.geometry.primitive in {PrimitiveType.CONE, PrimitiveType.WEDGE, PrimitiveType.PRISM}
            ]
            if not planar_hosts or len(tapered_members) < 2:
                continue
            referenced_labels = [
                member.attachment.connects_to for member in tapered_members
                if member.attachment and member.attachment.connects_to
            ]
            hub = None
            if referenced_labels:
                hub = next((child for child in children if child.label == referenced_labels[0]), None)
            if hub is None:
                hub = next((
                    child for child in children
                    if child.kind == NodeKind.PART and child.geometry
                    and child.geometry.primitive in {PrimitiveType.CYLINDER, PrimitiveType.SPHERE}
                    and child not in tapered_members
                    and child.attachment.socket_type != SocketType.ROOT
                ), None)
            if hub is None:
                continue
            for index, member in enumerate(tapered_members):
                member.attachment.socket_type = SocketType.BRIDGE
                member.attachment.connects_to = hub.label
                contract = member.stage_outputs.setdefault("spatial_contract", {})
                contract.update({
                    "orientation": "flat_horizontal",
                    "relation": "coplanar_member",
                    "member_index": index,
                    "member_count": len(tapered_members),
                    "plane": "xy",
                    "host_node_id": hub.node_id,
                    "enclosure_node_id": planar_hosts[0].node_id,
                })
                member.stage_outputs.setdefault("decomposition_hint", {})["length_axis"] = "x"
            changed.append({
                "parent": assembly.node_id,
                "relation": "coplanar_enclosed_group",
                "members": [member.node_id for member in tapered_members],
                "host": planar_hosts[0].node_id,
                "hub": hub.node_id,
            })

        # A U-shaped root defines an opening.  A sibling mentioned as inside,
        # between its forks, or suspended is an inset relationship, not a cap
        # stacked on top of the U.  This uses topology plus prompt evidence.
        for assembly in manifest.nodes.values():
            if assembly.kind != NodeKind.ASSEMBLY:
                continue
            children = [manifest.nodes[c] for c in assembly.children_ids if c in manifest.nodes]
            has_u = any(c.kind == NodeKind.PART and c.geometry and c.geometry.primitive == PrimitiveType.U_SHAPE
                        and c.attachment and c.attachment.socket_type == SocketType.ROOT for c in children)
            if not has_u:
                continue
            for child in children:
                if child.kind != NodeKind.ASSEMBLY or not child.attachment:
                    continue
                words = set(re.findall(r"[a-z]+", str(getattr(child, "label", child.node_id)).lower()))
                evidence = " ".join(c for c in clauses if words & set(re.findall(r"[a-z]+", c)))
                if any(term in evidence for term in ("inside", "between", "suspend")):
                    child.attachment.socket_type = SocketType.INSET
                    child_outputs = getattr(child, "stage_outputs", None)
                    if not isinstance(child_outputs, dict):
                        child_outputs = {}
                        child.stage_outputs = child_outputs
                    child_outputs.setdefault("stage3", {}).update({"inset_face": "bottom", "inset_depth": 0.0})
                    child_outputs.setdefault("spatial_contract", {})["relation"] = "inside_host"
                    changed.append({"node": child.node_id, "relation": "inside_host"})

        # Repeated siblings described as radiating are a polar group even if
        # the LLM emitted front/right/back/left sockets.  Convert their parent
        # placement only; the existing radial solver owns the exact angles.
        for parent in manifest.nodes.values():
            siblings = [manifest.nodes[c] for c in parent.children_ids if c in manifest.nodes and manifest.nodes[c].kind == NodeKind.ASSEMBLY]
            groups: Dict[str, List[Any]] = {}
            for child in siblings:
                stem = re.sub(r"(?:[_-]?\d+)+$", "", str(getattr(child, "label", child.node_id)).lower().replace("_assembly", ""))
                groups.setdefault(stem, []).append(child)
            for members in groups.values():
                if len(members) < 3:
                    continue
                words = set(re.findall(r"[a-z]+", str(getattr(members[0], "label", members[0].node_id)).lower()))
                evidence = " ".join(c for c in clauses if words & set(re.findall(r"[a-z]+", c)))
                if "radiat" not in evidence and "radial" not in evidence:
                    continue
                for index, member in enumerate(members):
                    member.attachment.socket_type = SocketType.RADIAL
                    member.attachment.radial_count = len(members)
                    member.attachment.radial_index = index
                    member.stage_outputs.setdefault("spatial_contract", {})["relation"] = "radial_group"
                changed.append({"parent": parent.node_id, "relation": "radial_group", "count": len(members)})
        if changed:
            report["patterns"].extend({"kind": "prompt_spatial_contract", **item} for item in changed)

    @classmethod
    def _apply_radial_repeat_definitions(cls, manifest: Any, report: Dict[str, Any]) -> None:
        """Make equivalent physical leaves in radial assembly branches one definition.

        Matching is by containment path and primitive, never display label.  A
        radial assembly represents repeated physical construction, so its arm,
        guard, fastener, etc. must not receive independent LLM dimension
        guesses merely because they have separate node IDs.
        """
        for parent in manifest.nodes.values():
            radial = [
                manifest.nodes[child_id] for child_id in parent.children_ids
                if child_id in manifest.nodes
                and manifest.nodes[child_id].kind == NodeKind.ASSEMBLY
                and manifest.nodes[child_id].attachment
                and manifest.nodes[child_id].attachment.socket_type == SocketType.RADIAL
            ]
            if len(radial) < 2:
                continue
            cls._orient_radial_branches(radial, manifest, report)
            by_path: Dict[tuple, List[Any]] = {}
            for assembly in radial:
                for path, leaf in cls._part_paths(assembly, manifest):
                    if leaf.geometry:
                        by_path.setdefault((path, leaf.geometry.primitive.value), []).append(leaf)
            for (path, primitive), members in by_path.items():
                if len(members) != len(radial):
                    continue
                key = f"radial_repeat:{parent.node_id}:{'.'.join(map(str, path))}:{primitive}"
                canonical = members[0]
                for member in members:
                    hint = member.stage_outputs.setdefault("decomposition_hint", {})
                    # Decomposition schemas often include repeat_key=None.
                    # ``setdefault`` preserves that null value and forces the
                    # old primitive-only fallback, which can confuse two
                    # distinct tori (a collar and a rotor guard).  A detected
                    # containment-path definition is authoritative here.
                    if not hint.get("repeat_key"):
                        hint["repeat_key"] = key
                    if member is not canonical and canonical.node_id not in member.dependency_ids:
                        member.dependency_ids.append(canonical.node_id)
                report["definitions"].setdefault(key, {
                    "count": len(members), "canonical_node_id": canonical.node_id,
                    "members": [member.node_id for member in members],
                })

    @classmethod
    def _orient_radial_branches(cls, branches: List[Any], manifest: Any, report: Dict[str, Any]) -> None:
        """Give radial branch roots an outward axis and terminal attachments.

        Blender primitives are Z-long by default.  A repeated radial branch
        whose root is an elongated mesh is a spoke/arm unless a higher-level
        endpoint constraint says otherwise.  Its local X axis is radial, and
        the enclosing assembly supplies the per-branch Z rotation.  A direct
        torus/circle child previously described as TOP_CENTER is therefore an
        endpoint fitting, not a vertically stacked cap.
        """
        roots: List[Any] = []
        terminals: List[Any] = []
        for branch in branches:
            direct = [manifest.nodes[cid] for cid in branch.children_ids if cid in manifest.nodes]
            root = next((child for child in direct if child.kind == NodeKind.PART
                         and child.attachment.socket_type == SocketType.ROOT
                         and child.geometry and child.geometry.primitive in {
                             PrimitiveType.CYLINDER, PrimitiveType.CONE, PrimitiveType.CAPSULE,
                             PrimitiveType.PRISM, PrimitiveType.BOX,
                         }), None)
            terminal = next((child for child in direct if child.kind == NodeKind.PART
                             and child.attachment.socket_type == SocketType.TOP_CENTER
                             and child.geometry and child.geometry.primitive in {
                                 PrimitiveType.TORUS, PrimitiveType.CIRCLE,
                             }), None)
            if root is None or terminal is None:
                return
            roots.append(root)
            terminals.append(terminal)
        for root, terminal in zip(roots, terminals):
            root.stage_outputs.setdefault("decomposition_hint", {})["length_axis"] = "x"
            terminal.attachment.socket_type = SocketType.RIGHT_END
        report["patterns"].append({
            "kind": "radial_outward_branch_orientation",
            "members": [root.node_id for root in roots],
            "terminal_members": [terminal.node_id for terminal in terminals],
        })

    @classmethod
    def _apply_explicit_sibling_repeat_definitions(cls, manifest: Any, report: Dict[str, Any]) -> None:
        """Share definitions for prompt-declared identical sibling assemblies.

        A symmetric set can be attached to front/right/back/left faces rather
        than represented as a RADIAL group.  Its definition identity is still
        containment-path plus primitive, while the enclosing assembly owns the
        placement.  This deliberately activates only for explicit symmetry
        language, never merely because two labels look alike.
        """
        prompt = (getattr(manifest, "prompt", "") or "").lower()
        if not any(word in prompt for word in ("identical", "symmetric", "symmetrical", "same size")):
            return
        for parent in manifest.nodes.values():
            groups: Dict[str, List[Any]] = {}
            for child_id in parent.children_ids:
                child = manifest.nodes.get(child_id)
                if child and child.kind == NodeKind.ASSEMBLY:
                    stem = __import__("re").sub(r"(?:[_\s-]?\d+)+$", "", child.label.lower())
                    groups.setdefault(stem, []).append(child)
            for stem, siblings in groups.items():
                if len(siblings) < 2:
                    continue
                by_path: Dict[tuple, List[Any]] = {}
                for sibling in siblings:
                    for path, leaf in cls._part_paths(sibling, manifest):
                        if leaf.geometry:
                            by_path.setdefault((path, leaf.geometry.primitive.value), []).append(leaf)
                for (path, primitive), members in by_path.items():
                    if len(members) != len(siblings):
                        continue
                    key = f"sibling_repeat:{parent.node_id}:{stem}:{'.'.join(map(str, path))}:{primitive}"
                    canonical = members[0]
                    for member in members:
                        hint = member.stage_outputs.setdefault("decomposition_hint", {})
                        if not hint.get("repeat_key"):
                            hint["repeat_key"] = key
                        if member is not canonical and canonical.node_id not in member.dependency_ids:
                            member.dependency_ids.append(canonical.node_id)
                    report["definitions"][key] = {
                        "count": len(members), "canonical_node_id": canonical.node_id,
                        "members": [member.node_id for member in members],
                    }
                report["patterns"].append({
                    "kind": "explicit_sibling_repeat", "parent_id": parent.node_id,
                    "label_stem": stem, "count": len(siblings),
                })

    @classmethod
    def _part_paths(cls, assembly: Any, manifest: Any, path: tuple = ()) -> List[tuple]:
        """Return ``(containment_path, part)`` for descendants in stable order."""
        result: List[tuple] = []
        for index, child_id in enumerate(assembly.children_ids):
            child = manifest.nodes.get(child_id)
            if child is None:
                continue
            child_path = path + (index,)
            if child.kind == NodeKind.PART:
                result.append((child_path, child))
            elif child.kind == NodeKind.ASSEMBLY:
                result.extend(cls._part_paths(child, manifest, child_path))
        return result

    @classmethod
    def _apply_longitudinal_attachments(cls, manifest: Any, report: Dict[str, Any]) -> None:
        """Make front/back attachments follow an elongated host's real axis.

        ``front`` in user language normally means the optical/mechanical end
        of a tube, not necessarily global -Y.  This preserves world axes for
        broad bodies while making cap-like child assemblies physically coaxial
        with a declared horizontal host.
        """
        for assembly in manifest.nodes.values():
            if assembly.kind != NodeKind.ASSEMBLY:
                continue
            roots = [
                manifest.nodes[cid] for cid in assembly.children_ids
                if cid in manifest.nodes
                and manifest.nodes[cid].kind == NodeKind.PART
                and manifest.nodes[cid].attachment.socket_type == SocketType.ROOT
                and manifest.nodes[cid].geometry
                and manifest.nodes[cid].geometry.primitive in {PrimitiveType.CYLINDER, PrimitiveType.CONE}
            ]
            if len(roots) != 1:
                continue
            axis = (roots[0].stage_outputs.get("decomposition_hint", {}) or {}).get("length_axis")
            if axis not in {"x", "y"}:
                continue
            changed = []
            for child_id in assembly.children_ids:
                child = manifest.nodes.get(child_id)
                if not child or child.kind != NodeKind.ASSEMBLY or not child.attachment:
                    continue
                socket = child.attachment.socket_type
                if axis == "x" and socket in {SocketType.FRONT_FACE, SocketType.FRONT_CENTER, SocketType.BACK_FACE, SocketType.BACK_CENTER}:
                    is_front = socket in {SocketType.FRONT_FACE, SocketType.FRONT_CENTER}
                    child.attachment.socket_type = SocketType.RIGHT_FACE if is_front else SocketType.LEFT_FACE
                    for desc_id in child.children_ids:
                        desc = manifest.nodes.get(desc_id)
                        if desc and desc.kind == NodeKind.PART:
                            desc.stage_outputs.setdefault("decomposition_hint", {})["length_axis"] = "x"
                    changed.append(child.node_id)
                elif axis == "y":
                    # Global front/back already match a Y-aligned tube, but
                    # ensure the cap itself inherits the tube's long axis.
                    for desc_id in child.children_ids:
                        desc = manifest.nodes.get(desc_id)
                        if desc and desc.kind == NodeKind.PART:
                            desc.stage_outputs.setdefault("decomposition_hint", {})["length_axis"] = "y"
                    changed.append(child.node_id)
            if changed:
                report["patterns"].append({
                    "kind": "longitudinal_attachments", "host_node_id": roots[0].node_id,
                    "axis": axis, "members": changed,
                })

    @classmethod
    def _apply_inset_fit_dependencies(cls, manifest: Any, report: Dict[str, Any]) -> None:
        """Make an inset component wait for, and fit within, its physical host.

        A U-shaped bracket's opening is defined by its resolved tube radii.
        The contained component therefore cannot be dimensioned independently
        or it may pass through the two forks.  This is topology-driven: a
        ROOT U_SHAPE and a sibling INSET assembly are sufficient; labels and
        object-specific names are not consulted.
        """
        for assembly in manifest.nodes.values():
            if assembly.kind != NodeKind.ASSEMBLY:
                continue
            children = [manifest.nodes[cid] for cid in assembly.children_ids if cid in manifest.nodes]
            host = next((child for child in children if child.kind == NodeKind.PART and child.geometry
                         and child.geometry.primitive == PrimitiveType.U_SHAPE and child.attachment
                         and child.attachment.socket_type == SocketType.ROOT), None)
            inset_groups = [child for child in children if child.kind == NodeKind.ASSEMBLY and child.attachment
                            and child.attachment.socket_type == SocketType.INSET]
            if host is None or not inset_groups:
                continue
            members: List[str] = []
            for inset in inset_groups:
                for _path, part in cls._part_paths(inset, manifest):
                    hint = part.stage_outputs.setdefault("decomposition_hint", {})
                    hint["inset_fit_host_node_id"] = host.node_id
                    if host.node_id not in part.dependency_ids:
                        part.dependency_ids.append(host.node_id)
                    members.append(part.node_id)
            if members:
                report["patterns"].append({
                    "kind": "inset_fit_constraint", "host_node_id": host.node_id,
                    "members": members,
                })

    @classmethod
    def _assign_materials_and_finishing(cls, manifest: Any, report: Dict[str, Any]) -> None:
        """Turn semantic material intent into concrete PBR and safe finishing specs."""
        from .manifest import MaterialSpec
        from .materials import get_material_for_description
        from .modifiers import ModifierSpec, ModifierType

        assigned: List[str] = []
        finished: List[str] = []
        for node in manifest.nodes.values():
            if node.kind != NodeKind.PART or not node.geometry:
                continue
            if not hasattr(node, "material"):
                node.material = None
            if not hasattr(node, "modifiers"):
                node.modifiers = []
            hint = (node.stage_outputs.get("decomposition_hint", {}) or {}).get("material_hint", "")
            # The user's wording is the authority.  An LLM-produced hint is
            # useful enrichment, but must not turn "two red LEDs" into blue
            # ones or silently discard a specified chassis colour.  The
            # extractor is deliberately lexical and applies to any labelled
            # component; it does not contain product/category templates.
            description = cls._material_intent_for_node(manifest, node, str(hint))
            node.stage_outputs.setdefault("material_intent", {})["resolved_description"] = description
            if node.material is None:
                node.material = cls._material_spec_from_intent(description, get_material_for_description, MaterialSpec)
                add_material = getattr(manifest, "add_material", None)
                if callable(add_material):
                    add_material(node.material.name or "intent_material", node.material)
                assigned.append(node.node_id)
            existing = {
                modifier.get("type") if isinstance(modifier, dict)
                else getattr(getattr(modifier, "type", None), "value", getattr(modifier, "type", None))
                for modifier in node.modifiers
            }
            stage0 = getattr(manifest, "stage0_output", None) or {}
            style_tag = str(stage0.get("style_tag", "")).lower()
            prompt_text = str(getattr(manifest, "prompt", "")).lower()
            wants_bevel = any(kw in style_tag or kw in prompt_text for kw in ["rounded", "bevel", "realistic", "chamfer", "smooth"])
            if node.geometry.primitive == PrimitiveType.BOX and "bevel" not in existing and wants_bevel:
                sizes = getattr(node.geometry, "size", None) or []
                positive = [float(size) for size in sizes if isinstance(size, (int, float)) and size > 0]
                width = min(positive) * 0.08 if positive else 0.002
                node.modifiers.append(ModifierSpec(
                    type=ModifierType.BEVEL, bevel_width=max(0.0005, width), bevel_segments=2, apply=False,
                ).to_dict())
                finished.append(node.node_id)
            elif node.geometry.primitive in {PrimitiveType.SPHERE, PrimitiveType.HEMISPHERE, PrimitiveType.TORUS, PrimitiveType.U_SHAPE} and "smooth" not in existing:
                node.modifiers.append(ModifierSpec(type=ModifierType.SMOOTH, apply=False).to_dict())
                finished.append(node.node_id)
        report["material_assignment"] = {"assigned_node_ids": assigned, "finished_node_ids": finished}

    @staticmethod
    def _material_intent_for_node(manifest: Any, node: Any, llm_hint: str) -> str:
        """Collect prompt-local material evidence for one part.

        Matching a component's label tokens against complete user clauses is
        robust to arbitrary asset categories while avoiding an unsafe attempt
        to understand all prose.  The original clause is placed before the
        model hint so explicit colours and finishes deterministically win.
        """
        prompt = str(getattr(manifest, "prompt", "") or "")
        singular = lambda token: re.sub(r"(?<!s)s$", "", re.sub(r"ies$", "y", token.lower()))
        tokens = {
            singular(token)
            for token in re.findall(r"[a-zA-Z]+", str(getattr(node, "label", "")))
            if len(token) >= 3
        }
        # Commas commonly separate compact material-role lists.  Treating the
        # entire list as one description lets another component's "metal" or
        # "black" override this part's own colour.
        clauses = re.split(r"[.;:!?,]+", prompt)
        matched: List[str] = []
        for clause in clauses:
            clause_tokens = {
                singular(token)
                for token in re.findall(r"[a-zA-Z]+", clause)
            }
            if tokens & clause_tokens:
                matched.append(clause.strip())

        # Reference briefs are supplementary, but they add useful role-level
        # finish language when the user used a compact prompt.
        brief = (getattr(manifest, "stats", {}) or {}).get("reference_brief", {}) or {}
        role_text: List[str] = []
        for collection_name in ("palette", "material_roles"):
            collection = brief.get(collection_name, {}) if isinstance(brief, dict) else {}
            if not isinstance(collection, dict):
                continue
            for role, value in collection.items():
                role_tokens = set(re.findall(r"[a-zA-Z]+", str(role).lower()))
                if tokens & role_tokens:
                    role_text.append(str(value))
        return " ".join([*matched, *role_text, llm_hint, str(getattr(node, "label", ""))]).strip()

    @staticmethod
    def _material_spec_from_intent(description: str, resolver: Any, material_spec_type: Any) -> Any:
        """Build a PBR spec while retaining explicit colour and finish intent."""
        preset = resolver(description)
        spec = material_spec_type.from_preset(preset.name)
        text = description.lower()
        colors = {
            "charcoal": [0.055, 0.06, 0.07, 1.0], "black": [0.02, 0.02, 0.025, 1.0],
            "white": [0.92, 0.92, 0.92, 1.0], "red": [0.85, 0.035, 0.025, 1.0],
            "blue": [0.04, 0.20, 0.9, 1.0], "green": [0.03, 0.65, 0.12, 1.0],
            "yellow": [0.95, 0.72, 0.03, 1.0], "orange": [0.95, 0.25, 0.03, 1.0],
        }
        words = set(re.findall(r"[a-z]+", text))
        color_name = next((name for name in colors if name in words), None)
        if color_name:
            rgba = colors[color_name]
            # Preserve transparency for glass while tinting its transmitted
            # colour; opaque surfaces receive the requested base colour.
            spec.base_color = list(rgba[:3]) + [spec.alpha if spec.transmission else 1.0]
            if spec.emission_color is not None:
                spec.emission_color = list(rgba[:3])
        if "matte" in text:
            spec.roughness = max(spec.roughness, 0.58)
        if "glossy" in text or "polished" in text:
            spec.roughness = min(spec.roughness, 0.18)
        if "painted" in text and ("metal" in text or "steel" in text or "aluminum" in text):
            # Paint is a dielectric coating; retain only a restrained metallic
            # contribution rather than rendering every painted body as steel.
            spec.metallic = min(spec.metallic, 0.25)
        intent_name = "intent_" + re.sub(r"[^a-z0-9]+", "_", f"{color_name or 'neutral'}_{preset.name}").strip("_")
        spec.name = intent_name
        spec.preset = None
        return spec

    @classmethod
    def validate(cls, manifest: Any) -> List[str]:
        """Return plan errors before Blender is allowed to mutate a scene."""
        errors: List[str] = []
        repeated: Dict[str, List[Any]] = {}
        for node in manifest.nodes.values():
            outputs = getattr(node, "stage_outputs", {}) or {}
            hint = outputs.get("decomposition_hint", {})
            endpoint = hint.get("endpoint_constraint")
            if endpoint:
                if endpoint.get("kind") != "radial_strut":
                    errors.append(f"{node.label}: unknown endpoint constraint")
                if not node.geometry or node.geometry.primitive not in {PrimitiveType.CYLINDER, PrimitiveType.CONE}:
                    errors.append(f"{node.label}: endpoint constraint needs an elongated primitive")
                depth = (outputs.get("stage2") or {}).get("depth")
                if not isinstance(depth, (int, float)) or depth <= 0:
                    errors.append(f"{node.label}: endpoint constraint has no positive length")
                hub = manifest.nodes.get(endpoint.get("hub_node_id"))
                if not hub or not hub.geometry:
                    errors.append(f"{node.label}: endpoint constraint has no geometric hub")
            key = hint.get("repeat_key")
            if key and node.kind == NodeKind.PART:
                repeated.setdefault(str(key), []).append(node)

        # A repeat key is a component-definition contract.  Dimensions and
        # primitive must match before its members can safely become linked
        # instances in a later executor capability.
        for key, members in repeated.items():
            if len(members) < 2:
                continue
            canonical = members[0]
            signature = cls._component_signature(canonical)
            for member in members[1:]:
                if cls._component_signature(member) != signature:
                    errors.append(f"repeat_key '{key}' has non-identical component definitions")
                    break
        return errors

    @staticmethod
    def _component_signature(node: Any) -> tuple:
        geometry = node.geometry.to_dict() if hasattr(node.geometry, "to_dict") else vars(node.geometry)
        stage2 = (getattr(node, "stage_outputs", {}) or {}).get("stage2", {})
        return (
            getattr(getattr(node.geometry, "primitive", None), "value", None),
            tuple(sorted((k, v) for k, v in stage2.items() if k != "reasoning")),
            str(((getattr(node, "stage_outputs", {}) or {}).get("decomposition_hint", {}) or {}).get("material_hint", "")),
            tuple(sorted((k, str(v)) for k, v in geometry.items() if k != "primitive")),
        )

    @staticmethod
    def _single_elongated_leaf(assembly: Any, manifest: Any) -> Optional[Any]:
        """Return exactly one cylinder/cone descendant, otherwise no match."""
        matches: List[Any] = []
        stack = list(assembly.children_ids)
        while stack:
            node = manifest.nodes.get(stack.pop())
            if not node:
                continue
            if node.kind == NodeKind.PART and node.geometry and node.geometry.primitive in {
                PrimitiveType.CYLINDER, PrimitiveType.CONE,
            }:
                matches.append(node)
            stack.extend(node.children_ids)
        return matches[0] if len(matches) == 1 else None
