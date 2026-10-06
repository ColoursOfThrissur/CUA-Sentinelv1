"""Stage 3 — Semantic Attachment Hints (Per-Node).

Adds semantic hints to a PART node's attachment spec:
- corner_position for CORNER sockets
- edge_position, edge_offset for EDGE sockets
- pierce_direction, height_hint for THROUGH_AXIS
- array_axis, spacing_hint for ARRAY_MEMBER
- connects_to for STRUT, BRIDGE, RADIAL_BRIDGE
- face_position for face mounts
- etc.

These hints are used by Stage 4 to compute exact transforms.

Blueprint references: §11 (per-node stages), §3 (semantics).
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..manifest import BuildManifest, ManifestNode

from ..node_types import NodeKind, SocketType

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Socket-specific semantic fields
# ---------------------------------------------------------------------------

# Which semantic fields each socket type requires
SOCKET_SEMANTICS = {
    SocketType.ROOT: [],
    SocketType.TOP_CENTER: [],
    SocketType.BOTTOM_CENTER: [],
    SocketType.FRONT_CENTER: [],
    SocketType.BACK_CENTER: [],
    SocketType.LEFT_CENTER: [],
    SocketType.RIGHT_CENTER: [],
    
    SocketType.CORNER: ["corner_position"],
    SocketType.EDGE: ["edge_position", "edge_offset"],
    
    SocketType.THROUGH_AXIS: ["pierce_direction", "height_hint"],
    
    SocketType.ARRAY_MEMBER: ["array_axis", "array_count", "array_index", "spacing_hint"],
    SocketType.RADIAL: ["radial_count", "radial_index"],
    SocketType.RADIAL_BRIDGE: ["radial_count", "radial_index", "connects_to"],
    
    SocketType.STRUT: ["connects_to"],
    SocketType.BRIDGE: ["connects_to", "position_fraction"],
    
    # RELATIVE_TO: closed vocabulary, no LLM-computed numbers
    SocketType.RELATIVE_TO: ["relative_to", "direction", "gap", "align", "position_along"],
    
    SocketType.TOP_FACE: ["face_position"],
    SocketType.BOTTOM_FACE: ["face_position"],
    SocketType.FRONT_FACE: ["face_position"],
    SocketType.BACK_FACE: ["face_position"],
    SocketType.LEFT_FACE: ["face_position"],
    SocketType.RIGHT_FACE: ["face_position"],
    
    SocketType.BOOLEAN_CUT: ["cut_face"],
    SocketType.BOOLEAN_UNION: [],
    SocketType.BOOLEAN_INTERSECT: [],
    
    SocketType.INSET: ["inset_face", "inset_depth"],
    
    # End sockets - no extra semantics
    SocketType.LEFT_END: [],
    SocketType.RIGHT_END: [],
    SocketType.TOP_END: [],
    SocketType.BOTTOM_END: [],
    SocketType.FRONT_END: [],
    SocketType.BACK_END: [],
    
    # Advanced sockets
    SocketType.EMBEDDED: [],
    SocketType.SURFACE_FOLLOW: [],
    SocketType.SCATTER: ["array_count"],
    SocketType.CURVE_FOLLOW: [],
    SocketType.VOLUME_FILL: [],
    
    # Rigging sockets
    SocketType.BONE_HEAD: [],
    SocketType.BONE_TAIL: [],
    SocketType.BONE_ALONG: [],
    SocketType.CONSTRAINED_TO: ["connects_to"],
    SocketType.PARENTED_TO: ["connects_to"],
}

# Valid values for semantic fields
VALID_CORNER_POSITIONS = frozenset({
    "top_front_left", "top_front_right", "top_back_left", "top_back_right",
    "bottom_front_left", "bottom_front_right", "bottom_back_left", "bottom_back_right",
})

VALID_EDGE_POSITIONS = frozenset({
    "top_front", "top_back", "top_left", "top_right",
    "bottom_front", "bottom_back", "bottom_left", "bottom_right",
    "front_left", "front_right", "back_left", "back_right",
})

VALID_PIERCE_DIRECTIONS = frozenset({
    "front_back", "left_right", "up_down",
})

VALID_HEIGHT_HINTS = frozenset({
    "near_top", "center", "near_bottom", "top_third", "bottom_third",
})

VALID_ARRAY_AXES = frozenset({"x", "y", "z"})

VALID_SPACING_HINTS = frozenset({"tight", "normal", "spread", "even"})

VALID_FACE_POSITIONS = frozenset({
    "center", "near_left", "near_right", "near_front", "near_back",
    "near_top", "near_bottom", "offset_left", "offset_right",
})

VALID_DIRECTIONS = frozenset({"left", "right", "front", "back", "above", "below"})

VALID_GAPS = frozenset({"touching", "small", "medium", "large"})

VALID_ALIGNS = frozenset({"same_position", "same_level"})

VALID_POSITION_ALONG = frozenset({"start", "quarter", "middle", "halfway", "three_quarter", "end"})

VALID_POSITION_FRACTIONS = frozenset({"start", "quarter", "middle", "three_quarter", "end"})

VALID_CUT_FACES = frozenset({
    "top", "bottom", "front", "back", "left", "right", "center",
})


class Stage3Error(Exception):
    """Raised when Stage 3 fails."""
    pass


# ---------------------------------------------------------------------------
# LLM Prompt
# ---------------------------------------------------------------------------

STAGE3_SYSTEM_PROMPT = """You are adding semantic attachment hints to a 3D model part.

Given a part with its socket type, provide the semantic hints needed to compute its exact position.

Output a JSON object with the required fields for the socket type:

CORNER socket: {"corner_position": "bottom_front_left"}
  Valid: top_front_left, top_front_right, top_back_left, top_back_right,
         bottom_front_left, bottom_front_right, bottom_back_left, bottom_back_right

EDGE socket: {"edge_position": "top_front", "edge_offset": 0.0}
  edge_position: top_front, top_back, top_left, top_right, bottom_front, etc.
  edge_offset: -1.0 to 1.0 (position along edge, 0 = center)

THROUGH_AXIS socket: {"pierce_direction": "left_right", "height_hint": "center"}
  pierce_direction: front_back, left_right, up_down
  height_hint: near_top, center, near_bottom, top_third, bottom_third

ARRAY_MEMBER socket: {"array_axis": "x", "array_count": 4, "array_index": 0, "spacing_hint": "even"}
  array_axis: x, y, or z
  spacing_hint: tight, normal, spread, even

RADIAL socket: {"radial_count": 4, "radial_index": 0}
RADIAL_BRIDGE socket: {"radial_count": 4, "radial_index": 0, "connects_to": "other_part_label"}

STRUT socket: {"connects_to": "target_part_label"}

BRIDGE socket: {"connects_to": "target_part_label", "position_fraction": "middle"}
  position_fraction: start, quarter, middle, three_quarter, end
  (Determines height along the overlapping Z span of parent and target)

RELATIVE_TO socket: {"relative_to": "other_part_label", "direction": "right", "gap": "small", "align": "same_position", "position_along": "middle"}
  direction: left, right, front, back, above, below
  gap: touching, small, medium, large
  align: same_position (copy all other axes), same_level (copy only Z)
  position_along: start, quarter, middle, three_quarter, end (used when direction is above/below/along a vertical part, e.g. a shelf on a leg)

FACE sockets (TOP_FACE, FRONT_FACE, etc.): {"face_position": "center"}
  Valid: center, near_left, near_right, near_front, near_back, offset_left, offset_right

BOOLEAN_CUT socket: {"cut_face": "top"}
  Valid: top, bottom, front, back, left, right, center

INSET socket: {"inset_face": "top", "inset_depth": 0.005}
  inset_face: top, bottom, front, back, left, right (which face the inset is recessed from)
  inset_depth: recess depth in meters (default 0.005 = 5mm)

For simple sockets (ROOT, TOP_CENTER, BOTTOM_CENTER, etc.), output: {}

NEVER output numeric coordinates or distances. All positioning is done through
closed vocabulary fields that the resolver converts to exact positions.

Output ONLY valid JSON, no markdown."""


# ---------------------------------------------------------------------------
# Stage 3 Implementation
# ---------------------------------------------------------------------------

class Stage3Semantics:
    """Stage 3: Add semantic hints to a single PART node's attachment."""
    
    @classmethod
    async def run(
        cls,
        node: ManifestNode,
        manifest: BuildManifest,
        model_manager: Any,
        task_id: str,
        model_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Run Stage 3 for a single node.
        
        Args:
            node: The PART node to add semantics to
            manifest: Build manifest (for context)
            model_manager: LLM model manager
            task_id: Task ID for tracking
            model_id: Optional specific model
            
        Returns:
            Dict of semantic hints
            
        Raises:
            Stage3Error: If semantics extraction fails
        """
        if node.kind != NodeKind.PART:
            raise Stage3Error(f"Stage 3 only runs on PART nodes, got {node.kind.value}")
        
        socket_type = node.attachment.socket_type
        required_fields = SOCKET_SEMANTICS.get(socket_type, [])
        
        # Simple sockets don't need LLM call
        if not required_fields:
            return {}

        # Pre-seed from decomposition hint — these values were set by the LLM
        # during decomposition and must be preserved exactly. If all required
        # fields are already present in the hint, skip the LLM call entirely.
        hint = node.stage_outputs.get("decomposition_hint", {})
        hint_seed = {}
        for f in required_fields:
            if f in hint and hint[f] is not None:
                hint_seed[f] = hint[f]

        if set(hint_seed.keys()) >= set(required_fields):
            # All fields already known from decomposition — validate and return
            parent_label = manifest.nodes[node.parent_id].label if (node.parent_id and node.parent_id in manifest.nodes) else None
            result = cls._parse_and_validate(
                json.dumps(hint_seed), node, required_fields, parent_label=parent_label
            )
            return cls._enforce_repeated_sibling_slots(node, manifest, result, socket_type)

        mid = model_id or model_manager.get_model_for_workflow("ENDPOINT")
        
        # Build context, injecting any already-known hint values so the LLM
        # only needs to fill in the missing fields.
        context = cls._build_context(node, manifest, required_fields, hint_seed=hint_seed)
        
        response = await model_manager.generate_async(
            model_id=mid,
            task_id=f"stage3_{task_id}_{node.label}",
            lease_id="internal",
            lease_generation=0,
            system_prompt=STAGE3_SYSTEM_PROMPT,
            prompt=context,
            temperature=0.1,
        )
        
        manifest.record_llm_call()
        manifest.append_llm_log(node.label, context, response)
        
        parent_label = manifest.nodes[node.parent_id].label if (node.parent_id and node.parent_id in manifest.nodes) else None
        result = cls._parse_and_validate(response, node, required_fields, parent_label=parent_label)
        # Merge: hint_seed wins for fields the LLM might have corrupted
        for k, v in hint_seed.items():
            result[k] = v
        return cls._enforce_repeated_sibling_slots(node, manifest, result, socket_type)

    @classmethod
    def _enforce_repeated_sibling_slots(
        cls, node: ManifestNode, manifest: BuildManifest, result: Dict[str, Any], socket_type: SocketType,
    ) -> Dict[str, Any]:
        """Derive repeated placement slots from tree order, never LLM output."""
        if socket_type in (SocketType.RADIAL, SocketType.RADIAL_BRIDGE, SocketType.ARRAY_MEMBER):
            parent = manifest.nodes.get(node.parent_id) if node.parent_id else None
            if parent:
                peers = [
                    manifest.nodes[child_id]
                    for child_id in parent.children_ids
                    if child_id in manifest.nodes
                    and manifest.nodes[child_id].attachment
                    and manifest.nodes[child_id].attachment.socket_type == socket_type
                ]
                if peers:
                    index = peers.index(node)
                    if socket_type == SocketType.ARRAY_MEMBER:
                        result["array_count"] = len(peers)
                        result["array_index"] = index
                    else:
                        result["radial_count"] = len(peers)
                        result["radial_index"] = index
        return result
    
    @classmethod
    def _build_context(
        cls,
        node: ManifestNode,
        manifest: BuildManifest,
        required_fields: List[str],
        hint_seed: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Build context string for LLM."""
        lines = []
        
        lines.append(f"Model: {manifest.prompt}")
        lines.append(f"Part: {node.label}")
        lines.append(f"Socket type: {node.attachment.socket_type.value}")
        lines.append(f"Required fields: {required_fields}")
        
        # Parent context
        if node.parent_id:
            parent = manifest.nodes.get(node.parent_id)
            if parent:
                lines.append(f"\nParent: {parent.label}")
                if parent.geometry:
                    lines.append(f"Parent primitive: {parent.geometry.primitive.value}")
        
        # All siblings context (always show — critical for BRIDGE/STRUT connects_to selection)
        if node.parent_id:
            parent = manifest.nodes.get(node.parent_id)
            if parent:
                all_sibs = []
                for sib_id in parent.children_ids:
                    sib = manifest.nodes.get(sib_id)
                    if sib and sib.node_id != node.node_id:
                        prim = sib.geometry.primitive.value if sib.geometry else sib.kind.value
                        all_sibs.append(f"  - {sib.label} ({prim}, socket={sib.attachment.socket_type.value})")
                if all_sibs:
                    lines.append(f"\nAll siblings in same assembly:")
                    lines.extend(all_sibs)

        # Sibling context for arrays/radials
        if node.attachment.socket_type in (SocketType.ARRAY_MEMBER, SocketType.RADIAL, SocketType.RADIAL_BRIDGE):
            if node.parent_id:
                parent = manifest.nodes.get(node.parent_id)
                if parent:
                    same_socket_siblings = []
                    for sib_id in parent.children_ids:
                        sib = manifest.nodes.get(sib_id)
                        if sib and sib.attachment.socket_type == node.attachment.socket_type:
                            same_socket_siblings.append(sib.label)
                    if same_socket_siblings:
                        lines.append(f"\nSiblings with same socket: {same_socket_siblings}")
                        lines.append(f"This part's index in array: {same_socket_siblings.index(node.label) if node.label in same_socket_siblings else 0}")
        
        # Exclude own parent from suggestion lists — connecting to your own parent
        # produces a zero-length span for BRIDGE/STRUT/RADIAL_BRIDGE and is always wrong.
        parent_label = manifest.nodes[node.parent_id].label if (node.parent_id and node.parent_id in manifest.nodes) else None
        if "relative_to" in required_fields:
            available_refs = cls._relevant_reference_targets(
                node, manifest, parent_label, max_shown=20
            )
            if available_refs["truncated"]:
                logger.info(
                    "Stage3 [%s]: reference target list truncated to %d/%d "
                    "(filtered by assembly proximity)",
                    node.label, len(available_refs["shown"]), available_refs["total"],
                )
            note = (
                f" (showing {len(available_refs['shown'])} of {available_refs['total']} "
                f"by proximity; others exist but are in distant assemblies)"
                if available_refs["truncated"] else ""
            )
            lines.append(f"\nAvailable reference parts{note}: {available_refs['shown']}")
        
        # For connects_to, list available targets
        if "connects_to" in required_fields:
            available_targets = cls._relevant_reference_targets(
                node, manifest, parent_label, max_shown=20
            )
            if available_targets["truncated"]:
                logger.info(
                    "Stage3 [%s]: connection target list truncated to %d/%d "
                    "(filtered by assembly proximity)",
                    node.label, len(available_targets["shown"]), available_targets["total"],
                )
            note = (
                f" (showing {len(available_targets['shown'])} of {available_targets['total']} "
                f"by proximity; others exist but are in distant assemblies)"
                if available_targets["truncated"] else ""
            )
            lines.append(f"\nAvailable connection targets{note}: {available_targets['shown']}")
        
        lines.append(f"\nProvide semantic hints for {node.label}.")
        
        # Tell the LLM which fields are already known so it only fills in the rest
        if hint_seed:
            lines.append(f"Already known (do NOT change): {hint_seed}")
        
        return "\n".join(lines)
    
    @classmethod
    def _relevant_reference_targets(
        cls,
        node: "ManifestNode",
        manifest: "BuildManifest",
        parent_label: Optional[str],
        max_shown: int = 20,
    ) -> Dict[str, Any]:
        """Return a relevance-ordered list of candidate reference targets.

        Priority order:
        1. Siblings in the same assembly (most likely targets)
        2. Parts in sibling assemblies of the same parent
        3. Parts in uncle assemblies (grandparent's other children)
        4. Everything else (distant)

        When the total exceeds max_shown, items are dropped from the bottom
        of the priority list and the truncation is logged by the caller.
        """
        from ..node_types import NodeKind as _NK

        # Build ancestor set for filtering
        def get_ancestor_ids(n_id: str) -> List[str]:
            ids = []
            cur = manifest.nodes.get(n_id)
            while cur and cur.parent_id:
                ids.append(cur.parent_id)
                cur = manifest.nodes.get(cur.parent_id)
            return ids

        node_ancestors = get_ancestor_ids(node.node_id)
        parent_id = node.parent_id
        grandparent_id = (
            manifest.nodes[parent_id].parent_id
            if parent_id and parent_id in manifest.nodes
            else None
        )

        tier1, tier2, tier3, tier4 = [], [], [], []

        for n in manifest.nodes.values():
            if n.node_id == node.node_id:
                continue
            if n.label == parent_label:
                continue
            if n.kind != _NK.PART:
                continue
            lbl = n.label
            if n.parent_id == parent_id:
                tier1.append(lbl)  # Same assembly sibling
            elif (
                grandparent_id
                and n.parent_id
                and manifest.nodes.get(n.parent_id, None) is not None
                and manifest.nodes[n.parent_id].parent_id == grandparent_id
            ):
                tier2.append(lbl)  # Sibling assembly's child
            elif grandparent_id and n.parent_id in node_ancestors:
                tier3.append(lbl)  # Uncle assembly
            else:
                tier4.append(lbl)  # Distant

        ordered = tier1 + tier2 + tier3 + tier4
        total = len(ordered)
        shown = ordered[:max_shown]
        return {"shown": shown, "total": total, "truncated": total > max_shown}

    @classmethod
    def _parse_and_validate(
        cls,
        response: str,
        node: ManifestNode,
        required_fields: List[str],
        parent_label: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Parse and validate LLM response."""
        data = cls._extract_json(response)
        if data is None:
            # Empty response is OK for simple sockets
            if not required_fields:
                return {}
            raise Stage3Error(f"Failed to parse JSON: {response[:200]}")
        
        result = {}
        
        # Validate and extract each required field
        for field in required_fields:
            value = data.get(field)
            
            if field == "corner_position":
                if value and value in VALID_CORNER_POSITIONS:
                    result["corner_position"] = value
                else:
                    result["corner_position"] = "bottom_front_left"  # Default
                    
            elif field == "edge_position":
                if value and value in VALID_EDGE_POSITIONS:
                    result["edge_position"] = value
                else:
                    result["edge_position"] = "top_front"  # Default
                    
            elif field == "edge_offset":
                result["edge_offset"] = cls._clamp(cls._to_float(value, 0.0), -1.0, 1.0)
                
            elif field == "pierce_direction":
                if value and value in VALID_PIERCE_DIRECTIONS:
                    result["pierce_direction"] = value
                else:
                    result["pierce_direction"] = "left_right"  # Default
                    
            elif field == "height_hint":
                if value and value in VALID_HEIGHT_HINTS:
                    result["height_hint"] = value
                else:
                    result["height_hint"] = "center"  # Default
                    
            elif field == "array_axis":
                if value and value.lower() in VALID_ARRAY_AXES:
                    result["array_axis"] = value.lower()
                else:
                    result["array_axis"] = "x"  # Default
                    
            elif field == "array_count":
                result["array_count"] = max(1, cls._to_int(value, 1))
                
            elif field == "array_index":
                result["array_index"] = max(0, cls._to_int(value, 0))
                
            elif field == "spacing_hint":
                if value and value in VALID_SPACING_HINTS:
                    result["spacing_hint"] = value
                else:
                    result["spacing_hint"] = "even"  # Default
                    
            elif field == "radial_count":
                result["radial_count"] = max(1, cls._to_int(value, 4))
                
            elif field == "radial_index":
                result["radial_index"] = max(0, cls._to_int(value, 0))
                
            elif field == "connects_to":
                if value and isinstance(value, str):
                    if value == parent_label:
                        raise Stage3Error(
                            f"{node.label}: connects_to cannot equal parent '{parent_label}' — "
                            f"BRIDGE/STRUT/RADIAL_BRIDGE require a target different from the parent"
                        )
                    result["connects_to"] = value
                # No default - will be handled by Stage 4
                
            elif field == "face_position":
                if value and value in VALID_FACE_POSITIONS:
                    result["face_position"] = value
                else:
                    result["face_position"] = "center"  # Default
                    
            elif field == "cut_face":
                if value and value in VALID_CUT_FACES:
                    result["cut_face"] = value
                else:
                    result["cut_face"] = "center"  # Default
                    
            elif field == "inset_face":
                if value and value in VALID_CUT_FACES:
                    result["inset_face"] = value
                else:
                    result["inset_face"] = "front"  # Default
                    
            elif field == "inset_depth":
                result["inset_depth"] = max(0.001, cls._to_float(value, 0.01))
            
            elif field == "position_fraction":
                if value and value in VALID_POSITION_FRACTIONS:
                    result["position_fraction"] = value
                else:
                    result["position_fraction"] = "middle"  # Default
            
            elif field == "relative_to":
                if value and isinstance(value, str):
                    if value == parent_label:
                        raise Stage3Error(
                            f"{node.label}: relative_to cannot equal parent '{parent_label}' — "
                            f"use a sibling or other part as the reference"
                        )
                    result["relative_to"] = value
                # No default - will be validated by Stage 4
            
            elif field == "direction":
                if value and value in VALID_DIRECTIONS:
                    result["direction"] = value
                else:
                    result["direction"] = "right"  # Default
            
            elif field == "gap":
                if value and value in VALID_GAPS:
                    result["gap"] = value
                else:
                    result["gap"] = "small"  # Default
            
            elif field == "align":
                if value and value in VALID_ALIGNS:
                    result["align"] = value
                else:
                    result["align"] = "same_position"  # Default
            
            elif field == "position_along":
                if value and value in VALID_POSITION_ALONG:
                    result["position_along"] = value
                else:
                    result["position_along"] = "middle"  # Default
        
        return result
    
    @classmethod
    def _to_float(cls, value: Any, default: float) -> float:
        """Convert value to float with default."""
        if value is None:
            return default
        try:
            return float(value)
        except (TypeError, ValueError):
            return default
    
    @classmethod
    def _to_int(cls, value: Any, default: int) -> int:
        """Convert value to int with default."""
        if value is None:
            return default
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
    
    @classmethod
    def _clamp(cls, value: float, min_val: float, max_val: float) -> float:
        """Clamp value to range."""
        return max(min_val, min(max_val, value))
    
    @classmethod
    def _extract_json(cls, text: str) -> Optional[Dict[str, Any]]:
        """Extract JSON from LLM response."""
        text = text.strip()
        
        # Empty or {} is valid
        if text == "{}" or text == "":
            return {}
        
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        
        m = re.search(r'```(?:json)?\s*(\{[\s\S]*?\})\s*```', text)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass
        
        m = re.search(r'\{[\s\S]*\}', text)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
        
        return None
    
    @classmethod
    def apply_to_attachment(cls, attachment, semantics: Dict[str, Any]) -> None:
        """Apply semantic hints to an AttachmentSpec."""
        for key, value in semantics.items():
            if hasattr(attachment, key):
                setattr(attachment, key, value)
