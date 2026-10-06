"""Deterministic checks that keep a scene plan faithful to stated design intent.

Reference research is useful for artistic direction, but prose alone cannot
guarantee that a generated hierarchy contains the parts the user asked for.
This module deliberately validates only high-confidence, user-stated facts:
explicit component counts and a small set of physically unambiguous forms.
It is a gate, not a catalogue of product-specific rules.
"""

from __future__ import annotations

import copy
import logging
import re
from dataclasses import asdict, dataclass
from typing import Any, Dict, List

from .node_types import NodeKind, PrimitiveType, SocketType
from .manifest import NodeState

logger = logging.getLogger(__name__)


_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}


# Semantic role groups for deduplication. When comparing assembly subtrees,
# tokens are first mapped to their canonical functional role so that
# different naming conventions ("cylinder" vs "arm", "ring" vs "guard")
# are recognized as covering the same design intent.
_ROLE_SYNONYMS: Dict[str, str] = {
    # Structural extensions
    "arm": "arm", "strut": "arm", "boom": "arm", "cylinder": "arm",
    "rod": "arm", "bar": "arm", "beam": "arm", "spar": "arm",
    # Protective rings/guards
    "guard": "guard", "ring": "guard", "cage": "guard",
    "bumper": "guard", "protector": "guard", "shield": "guard",
    # Rotor/propulsion
    "rotor": "rotor", "propeller": "rotor", "blade": "rotor",
    "impeller": "rotor", "fan": "rotor", "vane": "rotor",
    # Suspension / brackets
    "bracket": "bracket", "mount": "bracket", "fork": "bracket",
    "yoke": "bracket", "cradle": "bracket", "hanger": "bracket",
    # Optical / sensor
    "lens": "lens", "camera": "lens", "sensor": "lens",
    "optic": "lens", "eye": "lens",
    # Body / chassis
    "chassis": "chassis", "body": "chassis", "hull": "chassis",
    "frame": "chassis", "fuselage": "chassis",
    # Lighting
    "led": "led", "light": "led", "indicator": "led",
    "lamp": "led", "diode": "led",
    # Landing gear
    "foot": "foot", "leg": "foot", "pad": "foot",
    "skid": "foot", "gear": "foot", "stand": "foot",
}


def _to_roles(tokens: set) -> frozenset:
    """Map raw label tokens to canonical functional roles.

    Tokens not in the synonym table are kept as-is so that truly novel
    parts are still compared by their original names.
    """
    return frozenset(_ROLE_SYNONYMS.get(tok, tok) for tok in tokens)


@dataclass(frozen=True)
class ComponentCountRequirement:
    component: str
    count: int
    phrase: str


class DesignFidelityValidator:
    """Validate the frozen hierarchy against direct, real-world design intent."""

    @classmethod
    def requirements_from_prompt(cls, prompt: str) -> List[ComponentCountRequirement]:
        """Extract only explicit plural component counts, never inferred counts."""
        requirements: List[ComponentCountRequirement] = []
        # The final plural word is the component: "four cylindrical arms" -> arm.
        pattern = re.compile(
            r"(?<![\w.])(" + "|".join(_NUMBER_WORDS) + r"|\d{1,2})\s+(?:[a-z][a-z_-]*\s+){0,3}([a-z][a-z_-]*s)\b",
            re.IGNORECASE,
        )
        for match in pattern.finditer(prompt or ""):
            raw_count, plural = match.groups()
            count = _NUMBER_WORDS.get(raw_count.lower(), int(raw_count) if raw_count.isdigit() else 0)
            component = cls._singular(plural.lower())
            # Avoid treating dimensions such as "three metres" as components.
            if component in {"meter", "metre", "centimeter", "centimetre", "millimeter", "millimetre", "inch"}:
                continue
            requirements.append(ComponentCountRequirement(component, count, match.group(0)))
        # A repeated phrase should be enforced once, at its highest explicit count.
        merged: Dict[str, ComponentCountRequirement] = {}
        for requirement in requirements:
            previous = merged.get(requirement.component)
            if previous is None or requirement.count > previous.count:
                merged[requirement.component] = requirement
        return list(merged.values())

    @classmethod
    def validate(cls, manifest: Any) -> List[str]:
        errors: List[str] = []
        requirements = cls.requirements_from_prompt(getattr(manifest, "prompt", ""))
        leaves = [node for node in manifest.nodes.values() if getattr(node, "kind", None) == NodeKind.PART]
        labels = [cls._tokens(getattr(node, "label", "")) for node in leaves]
        for requirement in requirements:
            actual = sum(cls._component_matches(requirement.component, tokens) for tokens in labels)
            actual += cls._implicit_component_count(requirement.component, leaves)
            if actual < requirement.count:
                errors.append(
                    f"design requirement '{requirement.phrase}' needs {requirement.count} "
                    f"'{requirement.component}' parts, but the plan contains {actual}"
                )

        # These names often have a narrow physical meaning, unless the user
        # explicitly requested a stylized or ball-like interpretation.  User
        # shape language always takes precedence over semantic heuristics.
        for node in leaves:
            tokens = cls._tokens(getattr(node, "label", ""))
            primitive = getattr(getattr(node, "geometry", None), "primitive", None)
            if "lens" in tokens and primitive == PrimitiveType.SPHERE and not cls._prompt_requests_spherical_lens(getattr(manifest, "prompt", "")):
                errors.append(f"design requirement: lens '{node.label}' cannot use a sphere; use a shallow cylinder, cone, or torus")
            if "blade" in tokens and primitive == PrimitiveType.TORUS:
                errors.append(f"design requirement: blade '{node.label}' cannot use a torus; use a flat box or an impeller cylinder")
            if cls._prompt_requires_circular_ring(getattr(manifest, "prompt", "")) and {"ring", "guard"} & tokens and primitive not in {PrimitiveType.TORUS, PrimitiveType.CIRCLE}:
                errors.append(f"design requirement: circular ring '{node.label}' cannot use {getattr(primitive, 'value', primitive)}; use a torus or circle")
        return errors

    @staticmethod
    def _implicit_component_count(component: str, leaves: List[Any]) -> int:
        """Count physical features represented by one semantic primitive.

        A U-shaped solid has two physical forks even though modelling it as a
        single continuous mesh is the correct topology.  Count that geometric
        feature rather than demanding redundant, separately named meshes.
        """
        feature_counts = {
            "fork": {PrimitiveType.U_SHAPE: 2},
            "prong": {PrimitiveType.U_SHAPE: 2},
            "tine": {PrimitiveType.U_SHAPE: 2},
        }
        by_primitive = feature_counts.get(component, {})
        return sum(
            by_primitive.get(getattr(getattr(node, "geometry", None), "primitive", None), 0)
            for node in leaves
        )

    @classmethod
    def repair_explicit_requirements(cls, manifest: Any) -> Dict[str, Any]:
        """Apply only lossless repairs implied directly by the user's prompt.

        The decomposer sometimes represents a repeated *assembly* as one radial
        child.  A radial transform places that one branch once; it is not an
        instancer.  For a direct count such as ``four arms``, clone the complete
        representative subtree before any geometry stages run so four physical
        branches are planned and committed.  This is intentionally limited to
        one clear representative and retains validation for ambiguous cases.
        """
        repaired: List[Dict[str, Any]] = []
        for requirement in cls.requirements_from_prompt(getattr(manifest, "prompt", "")):
            leaves = [node for node in manifest.nodes.values() if getattr(node, "kind", None) == NodeKind.PART]
            actual = sum(
                cls._component_matches(requirement.component, cls._tokens(getattr(node, "label", "")))
                for node in leaves
            )
            missing = requirement.count - actual
            if missing <= 0:
                continue
            source = cls._representative_subtree(manifest, requirement.component)
            if source is None or not source.parent_id:
                continue
            subtree_size = len(cls._subtree_ids(manifest, source.node_id))
            if len(manifest.nodes) + subtree_size * missing > 96:
                continue

            parent = manifest.nodes.get(source.parent_id)
            if parent is None:
                continue
            repeat_key = f"explicit_{requirement.component}_group"
            cls._set_repeat_key(source, repeat_key)
            clones = []
            for index in range(1, missing + 1):
                clone = cls._clone_subtree(manifest, source, parent.node_id, index + 1)
                cls._set_repeat_key(clone, repeat_key)
                clones.append(clone)
            members = [source] + clones
            if source.kind == NodeKind.PART and requirement.count == 2 and source.attachment.socket_type in {
                SocketType.FRONT_FACE, SocketType.BACK_FACE,
                SocketType.TOP_FACE, SocketType.BOTTOM_FACE,
            }:
                source.attachment.face_position = "near_left"
                clones[0].attachment.face_position = "near_right"
            elif source.kind == NodeKind.PART:
                for index, member in enumerate(members):
                    member.attachment.socket_type = SocketType.ARRAY_MEMBER
                    member.attachment.array_axis = "x"
                    member.attachment.array_count = requirement.count
                    member.attachment.array_index = index
                    member.attachment.spacing_hint = "tight"
            else:
                for index, member in enumerate(members):
                    cls._make_radial(member, requirement.count, index)
            if parent.expected_child_count is not None:
                parent.expected_child_count += missing
            repaired.append({
                "requirement": requirement.phrase,
                "source": source.label,
                "copies_added": missing,
                "mode": (
                    "paired_face_expansion" if source.kind == NodeKind.PART and requirement.count == 2
                    else "linear_part_expansion" if source.kind == NodeKind.PART
                    else "radial_subtree_expansion"
                ),
            })

        # A prompt-level circular-ring requirement is an explicit geometric
        # contract, so correct a decomposer fallback (commonly a flat box)
        # before Stage 2 chooses primitive-specific dimensions.
        if cls._prompt_requires_circular_ring(getattr(manifest, "prompt", "")):
            for node in manifest.nodes.values():
                if (
                    getattr(node, "kind", None) == NodeKind.PART
                    and {"ring", "guard"} & cls._tokens(getattr(node, "label", ""))
                    and getattr(getattr(node, "geometry", None), "primitive", None) not in {PrimitiveType.TORUS, PrimitiveType.CIRCLE}
                ):
                    node.geometry.primitive = PrimitiveType.TORUS
                    repaired.append({"part": node.label, "mode": "explicit_circular_ring_to_torus"})

        # A lens is commonly a rotational optical element.  Correct it before
        # Stage 2 only when the prompt did not explicitly request a sphere;
        # otherwise the user's stylized form is the contract.
        for node in manifest.nodes.values():
            if (
                getattr(node, "kind", None) == NodeKind.PART
                and "lens" in cls._tokens(getattr(node, "label", ""))
                and getattr(getattr(node, "geometry", None), "primitive", None) == PrimitiveType.SPHERE
                and not cls._prompt_requests_spherical_lens(getattr(manifest, "prompt", ""))
            ):
                node.geometry.primitive = PrimitiveType.CYLINDER
                repaired.append({"part": node.label, "mode": "lens_sphere_to_cylinder"})

        prompt_text = getattr(manifest, "prompt", "").lower()
        # Reparent guard/ring to arm end if weakly flattened under central body
        if "attached at its end" in prompt_text or "end of each arm" in prompt_text or "end of the arm" in prompt_text:
            arms = [n for n in manifest.nodes.values() if getattr(n, "kind", None) == NodeKind.PART and "arm" in cls._tokens(getattr(n, "label", ""))]
            guards = [n for n in manifest.nodes.values() if getattr(n, "kind", None) == NodeKind.PART and ({"guard", "ring"} & cls._tokens(getattr(n, "label", "")))]
            if len(arms) == 1 and len(guards) == 1:
                arm = arms[0]
                guard = guards[0]
                if guard.parent_id != arm.node_id:
                    old_parent = manifest.nodes.get(guard.parent_id)
                    if old_parent and guard.node_id in getattr(old_parent, "children_ids", []):
                        old_parent.children_ids.remove(guard.node_id)
                    guard.parent_id = arm.node_id
                    if guard.node_id not in arm.children_ids:
                        arm.children_ids.append(guard.node_id)
                    arm_socket = arm.attachment.socket_type if arm.attachment else None
                    if arm_socket in (SocketType.FRONT_FACE, SocketType.FRONT_CENTER):
                        guard.attachment.socket_type = SocketType.FRONT_END
                    elif arm_socket in (SocketType.LEFT_FACE, SocketType.LEFT_CENTER):
                        guard.attachment.socket_type = SocketType.LEFT_END
                    elif arm_socket in (SocketType.RIGHT_FACE, SocketType.RIGHT_CENTER):
                        guard.attachment.socket_type = SocketType.RIGHT_END
                    elif arm_socket in (SocketType.BACK_FACE, SocketType.BACK_CENTER):
                        guard.attachment.socket_type = SocketType.BACK_END
                    else:
                        guard.attachment.socket_type = SocketType.RIGHT_END
                    repaired.append({"part": guard.label, "mode": "reparent_guard_to_arm_end"})

        # Reparent lens to bracket interior if weakly flattened
        if "inside" in prompt_text or "between the forks" in prompt_text or "suspended" in prompt_text:
            brackets = [n for n in manifest.nodes.values() if getattr(n, "kind", None) == NodeKind.PART and ({"bracket", "fork"} & cls._tokens(getattr(n, "label", "")))]
            lenses = [n for n in manifest.nodes.values() if getattr(n, "kind", None) == NodeKind.PART and ({"lens", "camera"} & cls._tokens(getattr(n, "label", "")))]
            if len(brackets) == 1 and len(lenses) == 1:
                bracket = brackets[0]
                lens = lenses[0]
                if lens.parent_id != bracket.node_id:
                    old_parent = manifest.nodes.get(lens.parent_id)
                    if old_parent and lens.node_id in getattr(old_parent, "children_ids", []):
                        old_parent.children_ids.remove(lens.node_id)
                    lens.parent_id = bracket.node_id
                    if lens.node_id not in bracket.children_ids:
                        bracket.children_ids.append(lens.node_id)
                    lens.attachment.socket_type = SocketType.INSET
                    lens.attachment.allow_disconnected = True
        # Reparent orphaned root-level control/detail parts that explicitly mention
        # being attached to another part or assembly (e.g. "attached to the front face of the lower acoustic body")
        root_id = getattr(manifest, "root_node_id", None) or getattr(manifest, "root_id", None)
        root_nodes = [
            n for n in manifest.nodes.values()
            if (getattr(n, "parent_id", None) == root_id or getattr(n, "parent_id", None) is None)
            and getattr(n, "kind", None) == NodeKind.PART
            and getattr(getattr(n, "attachment", None), "socket_type", None) in {
                SocketType.FRONT_FACE, SocketType.BACK_FACE,
                SocketType.LEFT_FACE, SocketType.RIGHT_FACE,
                SocketType.FRONT_CENTER, SocketType.BACK_CENTER,
                SocketType.INSET,
            }
        ]
        if root_nodes:
            clauses = [c.strip() for c in re.split(r"[.;\n]+", prompt_text) if c.strip()]
            for orphan in root_nodes:
                orphan_tokens = cls._tokens(orphan.label)
                # Find prompt clauses mentioning this orphan
                evidence_clauses = [c for c in clauses if orphan_tokens & cls._tokens(c)]
                for c in evidence_clauses:
                    if "attached to" in c or "mounted on" in c or "on the" in c:
                        # Find other potential host nodes mentioned in this clause
                        best_candidate = None
                        best_score = 0
                        for other in manifest.nodes.values():
                            if other.node_id in (root_id, orphan.node_id):
                                continue
                            if other.parent_id == orphan.node_id:
                                continue
                            other_tokens = cls._tokens(other.label)
                            overlap = len(other_tokens & cls._tokens(c))
                            if overlap > best_score:
                                best_score = overlap
                                best_candidate = other
                        if best_candidate and best_score >= 1:
                            # Reparent orphan to best_candidate
                            old_parent = manifest.nodes.get(orphan.parent_id)
                            if old_parent and orphan.node_id in getattr(old_parent, "children_ids", []):
                                old_parent.children_ids.remove(orphan.node_id)
                            orphan.parent_id = best_candidate.node_id
                            if orphan.node_id not in best_candidate.children_ids:
                                best_candidate.children_ids.append(orphan.node_id)
                            repaired.append({
                                "part": orphan.label,
                                "mode": f"reparent_orphan_to_{best_candidate.label}",
                            })
                            break

        if repaired:
            manifest.record_event("design_fidelity_repaired", details={"repairs": repaired})
        return {"repairs": repaired, "count": len(repaired)}

    @classmethod
    def normalize_decomposition_ownership(cls, manifest: Any) -> Dict[str, Any]:
        """Remove conservative root-level duplicates owned by a primary assembly.

        Some model responses emit both a complete main assembly and selected
        details again as root siblings.  Prefer the largest ROOT assembly only
        when it already contains the same display identity or the semantic
        stem of another root assembly.  Repeated parts inside separate peer
        assemblies are untouched.
        """
        root = manifest.get_root()
        children = [manifest.nodes[cid] for cid in root.children_ids if cid in manifest.nodes]
        assemblies = [
            child for child in children
            if child.kind == NodeKind.ASSEMBLY
            and child.attachment
            and child.attachment.socket_type == SocketType.ROOT
        ]
        if not assemblies:
            # Case B: When root's ROOT child is a PART (e.g. central chassis),
            # check peer assemblies under root. If one assembly's component tokens
            # are a complete subset of another assembly's components, or if two assemblies
            # duplicate the same subsystem (e.g. u-bracket + camera lens), prune the redundant one.
            all_assemblies = [child for child in children if child.kind == NodeKind.ASSEMBLY]
            ignored = {"part", "assembly", "group", "module", "system", "shape", "base", "holder", "object"}
            asm_tokens = {}
            for a in all_assemblies:
                desc = [manifest.nodes[d] for d in cls._subtree_ids(manifest, a.node_id)[1:] if d in manifest.nodes]
                toks = set().union(*(cls._tokens(d.label) for d in desc)) - ignored
                asm_tokens[a.node_id] = toks

            remove_ids = []
            # If root has a physical ROOT part (e.g. central_chassis), any assembly
            # under root that re-creates an imposter duplicate of this ROOT part
            # must be pruned.
            root_root_part = next(
                (c for c in children if c.kind == NodeKind.PART and c.attachment and c.attachment.socket_type == SocketType.ROOT),
                None
            )
            if root_root_part:
                root_stem = root_root_part.label.split("_")[0]
                for a in all_assemblies:
                    desc = [manifest.nodes[d] for d in cls._subtree_ids(manifest, a.node_id)[1:] if d in manifest.nodes]
                    for d in desc:
                        if d.kind == NodeKind.PART and d.attachment and d.attachment.socket_type == SocketType.ROOT:
                            d_stem = d.label.split("__")[0].split("_")[0]
                            if d_stem == root_stem:
                                logger.warning(
                                    f"Pruning assembly '{a.label}': re-created root part duplicate '{d.label}'"
                                )
                                remove_ids.append(a.node_id)
                                break

            for a in all_assemblies:
                if a.node_id in remove_ids:
                    continue
                a_stem = a.label.split("_")[0]
                for b in all_assemblies:
                    if a.node_id == b.node_id or b.node_id in remove_ids:
                        continue
                    b_stem = b.label.split("_")[0]
                    if a_stem == b_stem:
                        continue
                    toks_a = asm_tokens[a.node_id]
                    toks_b = asm_tokens[b.node_id]
                    if not toks_b:
                        continue
                    # Compare both raw tokens AND functional roles.
                    # Two assemblies are duplicates if either their raw tokens
                    # overlap or their functional roles overlap.
                    roles_a = _to_roles(toks_a)
                    roles_b = _to_roles(toks_b)
                    is_raw_subset = toks_b.issubset(toks_a) and len(toks_a) > len(toks_b)
                    is_role_subset = roles_b.issubset(roles_a) and len(roles_a) > len(roles_b)
                    # High role overlap (>=50% of the smaller set) signals
                    # the same subsystem expressed with different vocabulary.
                    role_overlap = roles_a & roles_b
                    min_roles = min(len(roles_a), len(roles_b))
                    high_role_overlap = (
                        min_roles > 0
                        and len(role_overlap) >= max(2, min_roles * 0.5)
                    )
                    if is_raw_subset or is_role_subset or high_role_overlap:
                        # Keep the larger assembly, prune the smaller one
                        size_a = len(DesignFidelityValidator._subtree_ids(manifest, a.node_id))
                        size_b = len(DesignFidelityValidator._subtree_ids(manifest, b.node_id))
                        if size_b <= size_a:
                            remove_ids.append(b.node_id)
                        else:
                            remove_ids.append(a.node_id)
                    elif len(toks_a & toks_b) >= 2 and ("bracket" in (toks_a & toks_b) or "lens" in (toks_a & toks_b)):
                        sock_a = a.attachment.socket_type.value if a.attachment else ""
                        sock_b = b.attachment.socket_type.value if b.attachment else ""
                        if sock_a == "BOTTOM_CENTER" and sock_b != "BOTTOM_CENTER":
                            remove_ids.append(b.node_id)
                        elif sock_b == "BOTTOM_CENTER" and sock_a != "BOTTOM_CENTER":
                            remove_ids.append(a.node_id)

            removed = []
            for node_id in remove_ids:
                if node_id not in manifest.nodes:
                    continue
                removed.extend(cls._subtree_ids(manifest, node_id))
                root.children_ids = [child_id for child_id in root.children_ids if child_id != node_id]
                for subtree_id in cls._subtree_ids(manifest, node_id):
                    manifest.nodes.pop(subtree_id, None)
            if removed:
                manifest.record_event(
                    "decomposition_ownership_normalized",
                    details={"removed_nodes": removed, "primary": None},
                )
            return {"removed": removed, "primary": None}
        primary = max(assemblies, key=lambda item: len(cls._subtree_ids(manifest, item.node_id)))
        primary_descendants = [
            manifest.nodes[node_id] for node_id in cls._subtree_ids(manifest, primary.node_id)[1:]
        ]
        descendant_displays = {
            str((node.custom_props or {}).get("display_label") or node.label).lower()
            for node in primary_descendants
        }
        descendant_tokens = set().union(*(cls._tokens(label) for label in descendant_displays)) if descendant_displays else set()
        ignored = {"assembly", "group", "module", "system", "base", "top", "head", "mount", "holder", "shape", "part", "object"}
        remove_ids: List[str] = []
        for child in children:
            if child.node_id == primary.node_id:
                continue
            display = str((child.custom_props or {}).get("display_label") or child.label).lower()
            if child.kind == NodeKind.PART and display in descendant_displays:
                remove_ids.append(child.node_id)
                continue
            if child.kind == NodeKind.ASSEMBLY:
                child_desc = [manifest.nodes[d] for d in cls._subtree_ids(manifest, child.node_id)[1:] if d in manifest.nodes]
                child_tokens = set().union(*(cls._tokens(d.label) for d in child_desc)) - ignored if child_desc else set()
                core = (cls._tokens(display) - ignored) | child_tokens
                # Only prune if there are non-empty core tokens AND significant role overlap
                # (e.g. true duplicates, not different subsystems sharing a word like 'base')
                if core and descendant_tokens:
                    roles_child = _to_roles(core)
                    roles_primary = _to_roles(descendant_tokens - ignored)
                    role_overlap = roles_child & roles_primary
                    min_roles = min(len(roles_child), len(roles_primary))
                    # Prune only if strong functional duplicate (>=50% role overlap and at least 2 roles)
                    if min_roles > 0 and len(role_overlap) >= max(2, min_roles * 0.5):
                        remove_ids.append(child.node_id)

        removed = []
        for node_id in remove_ids:
            if node_id not in manifest.nodes:
                continue
            removed.extend(cls._subtree_ids(manifest, node_id))
            root.children_ids = [child_id for child_id in root.children_ids if child_id != node_id]
            for subtree_id in cls._subtree_ids(manifest, node_id):
                manifest.nodes.pop(subtree_id, None)
        if removed:
            manifest.record_event(
                "decomposition_ownership_normalized",
                node_id=primary.node_id,
                details={"primary": primary.node_id, "removed_node_ids": removed},
            )
        return {"removed": removed, "primary": primary.node_id}

    @classmethod
    def _representative_subtree(cls, manifest: Any, component: str) -> Any:
        """Find the smallest assembly branch containing exactly one component."""
        candidates = []
        for node in manifest.nodes.values():
            if getattr(node, "kind", None) != NodeKind.ASSEMBLY or not node.parent_id:
                continue
            descendant_leaves = [manifest.nodes[node_id] for node_id in cls._subtree_ids(manifest, node.node_id)
                                 if manifest.nodes[node_id].kind == NodeKind.PART]
            matches = sum(cls._component_matches(component, cls._tokens(leaf.label)) for leaf in descendant_leaves)
            if matches == 1 and cls._component_matches(component, cls._tokens(node.label)):
                candidates.append(node)
        if candidates:
            return min(candidates, key=lambda node: len(cls._subtree_ids(manifest, node.node_id)))
        for node in manifest.nodes.values():
            if getattr(node, "kind", None) == NodeKind.PART and cls._component_matches(component, cls._tokens(node.label)):
                return node
        # Last resort for a semantically named component represented only by
        # a nested leaf.  This is intentionally after exact leaf matching so
        # a missing LED cannot clone an entire chassis merely because the LED
        # happens to live inside it.
        for node in manifest.nodes.values():
            if getattr(node, "kind", None) != NodeKind.ASSEMBLY or not node.parent_id:
                continue
            descendant_leaves = [manifest.nodes[node_id] for node_id in cls._subtree_ids(manifest, node.node_id)
                                 if manifest.nodes[node_id].kind == NodeKind.PART]
            if sum(cls._component_matches(component, cls._tokens(leaf.label)) for leaf in descendant_leaves) == 1:
                candidates.append(node)
        if candidates:
            return min(candidates, key=lambda node: len(cls._subtree_ids(manifest, node.node_id)))
        return None

    @staticmethod
    def _subtree_ids(manifest: Any, node_id: str) -> List[str]:
        node = manifest.nodes[node_id]
        result = [node_id]
        for child_id in node.children_ids:
            result.extend(DesignFidelityValidator._subtree_ids(manifest, child_id))
        return result

    @staticmethod
    def _set_repeat_key(node: Any, repeat_key: str) -> None:
        node.stage_outputs.setdefault("decomposition_hint", {})["repeat_key"] = repeat_key

    @staticmethod
    def _make_radial(node: Any, count: int, index: int) -> None:
        node.attachment.socket_type = SocketType.RADIAL
        node.attachment.radial_count = count
        node.attachment.radial_index = index

    @classmethod
    def _clone_subtree(cls, manifest: Any, source: Any, parent_id: str, ordinal: int) -> Any:
        """Clone an unbuilt subtree with fresh identity and no Blender state."""
        existing_labels = {node.label for node in manifest.nodes.values()}
        base = f"{source.label}_{ordinal}"
        label = base
        suffix = 2
        while label in existing_labels:
            label = f"{base}_{suffix}"
            suffix += 1
        clone = manifest.add_child_node(
            parent_id=parent_id, label=label, kind=source.kind,
            importance=source.importance, dependency_ids=[],
            attachment=copy.deepcopy(source.attachment),
            geometry=copy.deepcopy(source.geometry), material=copy.deepcopy(source.material),
            stage_outputs=copy.deepcopy(source.stage_outputs),
        )
        clone.expected_child_count = source.expected_child_count
        clone.modifiers = copy.deepcopy(source.modifiers)
        clone.constraints = copy.deepcopy(source.constraints)
        clone.custom_props = copy.deepcopy(source.custom_props)
        if clone.kind in (NodeKind.ASSEMBLY, NodeKind.MODEL) and getattr(source, "state", None) in (NodeState.READY, NodeState.VERIFIED):
            clone.state = NodeState.READY
        for child_id in source.children_ids:
            cls._clone_subtree(manifest, manifest.nodes[child_id], clone.node_id, ordinal)
        return clone

    @classmethod
    def report(cls, prompt: str) -> Dict[str, Any]:
        """Persist the parsed requirements for traceability and debugging."""
        return {"schema_version": 1, "explicit_component_counts": [asdict(item) for item in cls.requirements_from_prompt(prompt)]}

    @staticmethod
    def _tokens(label: str) -> set[str]:
        return {DesignFidelityValidator._singular(token) for token in re.findall(r"[a-z]+", label.lower())}

    @staticmethod
    def _component_matches(component: str, tokens: set[str]) -> bool:
        aliases = {
            "blade": {"blade", "propeller", "vane"},
            "led": {"led", "indicator", "diode"},
            "guard": {"guard", "ring", "cage"},
            "foot": {"foot", "pad"},
        }
        return bool(tokens & aliases.get(component, {component}))

    @staticmethod
    def _singular(word: str) -> str:
        # These common component nouns end in ``s`` while already singular.
        if word in {"lens", "chassis", "glass", "harness"}:
            return word
        if word.endswith("ies") and len(word) > 3:
            return word[:-3] + "y"
        if word.endswith("ses") and len(word) > 3:
            return word[:-2]
        return word[:-1] if word.endswith("s") and len(word) > 1 else word

    @staticmethod
    def _prompt_requests_spherical_lens(prompt: str) -> bool:
        """Recognize an explicit sphere/lens relationship without label assumptions."""
        text = (prompt or "").lower()
        return bool(re.search(r"\b(?:sphere|spherical|ball)\b.{0,80}\blens\b|\blens\b.{0,80}\b(?:sphere|spherical|ball)\b", text))

    @staticmethod
    def _prompt_requires_circular_ring(prompt: str) -> bool:
        text = (prompt or "").lower()
        return bool(re.search(r"\b(?:flat\s*,?\s*horizontal\s*)?(?:circular|round)\s+ring\b|\bring\b.{0,50}\b(?:circular|round)\b", text))
