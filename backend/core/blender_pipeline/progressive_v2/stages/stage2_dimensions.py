"""Stage 2 — Dimensions Assignment (Per-Node).

Assigns real-world dimensions in meters to a single PART node.
Uses the scale anchor from Stage 0 and parent context.

Unlike v4 which batches all parts, this runs per-node during build loop,
allowing dimensions to be informed by already-built siblings.

Blueprint references: §11 (per-node stages).
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..manifest import BuildManifest, ManifestNode

from ..node_types import NodeKind, PrimitiveType, SocketType

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Stage 2 Output
# ---------------------------------------------------------------------------

@dataclass
class DimensionsOutput:
    """Output from Stage 2 for a single part."""
    # Primary dimensions based on primitive type
    size_x: Optional[float] = None  # For box
    size_y: Optional[float] = None  # For box
    size_z: Optional[float] = None  # For box
    radius: Optional[float] = None  # For sphere, cylinder, cone
    radius2: Optional[float] = None # For cone (top radius)
    depth: Optional[float] = None   # For cylinder, cone
    major_radius: Optional[float] = None  # For torus
    minor_radius: Optional[float] = None  # For torus
    
    # Reasoning from LLM
    reasoning: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        d = {"reasoning": self.reasoning}
        if self.size_x is not None: d["size_x"] = self.size_x
        if self.size_y is not None: d["size_y"] = self.size_y
        if self.size_z is not None: d["size_z"] = self.size_z
        if self.radius is not None: d["radius"] = self.radius
        if self.radius2 is not None: d["radius2"] = self.radius2
        if self.depth is not None: d["depth"] = self.depth
        if self.major_radius is not None: d["major_radius"] = self.major_radius
        if self.minor_radius is not None: d["minor_radius"] = self.minor_radius
        return d
    
    def apply_to_geometry(self, geometry) -> None:
        """Apply dimensions to a GeometrySpec."""
        if self.size_x is not None:
            geometry.size = [self.size_x, self.size_y or self.size_x, self.size_z or self.size_x]
        if self.radius is not None:
            geometry.radius = self.radius
        if self.radius2 is not None:
            geometry.radius2 = self.radius2
        if self.depth is not None:
            geometry.depth = self.depth
        if self.major_radius is not None:
            geometry.major_radius = self.major_radius
        if self.minor_radius is not None:
            geometry.minor_radius = self.minor_radius


class Stage2Error(Exception):
    """Raised when Stage 2 fails."""
    pass


# ---------------------------------------------------------------------------
# LLM Prompt
# ---------------------------------------------------------------------------

STAGE2_SYSTEM_PROMPT = """You are assigning real-world dimensions to a 3D model part.

Given:
- The part's label and primitive type
- The overall model's scale anchor (total height/length in meters)
- Parent and sibling context

Output a JSON object with dimensions in METERS. Use the primitive-appropriate fields:

For "box": {"size_x": float, "size_y": float, "size_z": float, "reasoning": "..."}
For "cylinder": {"radius": float, "depth": float, "reasoning": "..."}
For "cone": {"radius": float, "radius2": float, "depth": float, "reasoning": "..."}
  - radius is bottom, radius2 is top (0 for pointed cone)
For "sphere": {"radius": float, "reasoning": "..."}
For "hemisphere": {"radius": float, "reasoning": "..."}
For "torus": {"major_radius": float, "minor_radius": float, "reasoning": "..."}
For "capsule": {"radius": float, "depth": float, "reasoning": "..."}
  - depth is total end-to-end length including both hemispherical caps and must be at least twice radius.
For "u_shape": {"major_radius": float, "minor_radius": float, "reasoning": "..."}
  - major_radius: arc centre-line radius (e.g. 0.025 for a padlock shackle)
  - minor_radius: tube cross-section radius (e.g. 0.005 for a padlock shackle)
  - A padlock shackle on a ~0.06m body: major_radius≈0.018, minor_radius≈0.005

For "plane", "grid", or "wedge": {"size_x": float, "size_y": float, "size_z": float, "reasoning": "..."}
  - A plane is a physical thin panel; size_z is its positive thickness.
For "circle": {"radius": float, "reasoning": "..."}
For "pyramid" or "prism": {"radius": float, "depth": float, "reasoning": "..."}

CRITICAL RULES:
1. All dimensions in METERS (not cm, not mm)
2. Dimensions must be PROPORTIONAL to the scale anchor
3. Parts should fit together logically (child smaller than parent attachment area)
4. Consider real-world proportions for the object type

Example for a table leg (scale anchor: 0.75m table height):
```json
{"radius": 0.03, "depth": 0.72, "reasoning": "Table leg is slightly shorter than table height, typical leg diameter 6cm"}
```

Output ONLY valid JSON, no markdown, no explanation outside JSON."""


# ---------------------------------------------------------------------------
# Stage 2 Implementation
# ---------------------------------------------------------------------------

class Stage2Dimensions:
    """Stage 2: Assign dimensions to a single PART node."""
    
    @classmethod
    async def run(
        cls,
        node: ManifestNode,
        manifest: BuildManifest,
        model_manager: Any,
        task_id: str,
        model_id: Optional[str] = None,
    ) -> DimensionsOutput:
        """Run Stage 2 for a single node.
        
        Args:
            node: The PART node to dimension
            manifest: Build manifest (for context)
            model_manager: LLM model manager
            task_id: Task ID for tracking
            model_id: Optional specific model
            
        Returns:
            DimensionsOutput with dimensions in meters
            
        Raises:
            Stage2Error: If dimensioning fails
        """
        if node.kind != NodeKind.PART:
            raise Stage2Error(f"Stage 2 only runs on PART nodes, got {node.kind.value}")
        
        if not node.geometry:
            raise Stage2Error(f"Node {node.label} has no geometry spec")

        shared = cls._shared_dimension_reference(node, manifest)
        if shared is not None:
            # Repeated geometry is a definition, not several independent LLM
            # guesses.  This preserves symmetry for blades, legs, bolts, etc.
            return cls._apply_orientation_aspect_guard(
                node, manifest,
                cls._apply_inset_fit_constraint(
                    node, manifest,
                    cls._from_dict(shared, reasoning="shared repeated-component definition"),
                ),
            )
        
        mid = model_id or model_manager.get_model_for_workflow("ENDPOINT")
        
        # Build context
        context = cls._build_context(node, manifest)
        
        response = await model_manager.generate_async(
            model_id=mid,
            task_id=f"stage2_{task_id}_{node.label}",
            lease_id="internal",
            lease_generation=0,
            system_prompt=STAGE2_SYSTEM_PROMPT,
            prompt=context,
            temperature=0.1,
        )
        
        manifest.record_llm_call()
        manifest.append_llm_log(node.label, context, response)
        
        result = cls._parse_response(response, node)
        if result is None:
            # Retry once with a minimal prompt that forces JSON output with matching schema
            prim = node.geometry.primitive
            if prim in (PrimitiveType.BOX, PrimitiveType.PLANE, PrimitiveType.GRID, PrimitiveType.WEDGE):
                ex = '{"size_x": 0.1, "size_y": 0.1, "size_z": 0.1, "reasoning": "estimate"}'
            elif prim in (PrimitiveType.CYLINDER, PrimitiveType.CAPSULE, PrimitiveType.HEMISPHERE, PrimitiveType.PRISM, PrimitiveType.PYRAMID):
                ex = '{"radius": 0.05, "depth": 0.15, "reasoning": "estimate"}'
            elif prim == PrimitiveType.CONE:
                ex = '{"radius": 0.05, "radius2": 0.0, "depth": 0.15, "reasoning": "estimate"}'
            elif prim in (PrimitiveType.SPHERE, PrimitiveType.CIRCLE):
                ex = '{"radius": 0.05, "reasoning": "estimate"}'
            elif prim in (PrimitiveType.TORUS, PrimitiveType.U_SHAPE):
                ex = '{"major_radius": 0.1, "minor_radius": 0.02, "reasoning": "estimate"}'
            else:
                ex = '{"size_x": 0.1, "size_y": 0.1, "size_z": 0.1, "reasoning": "estimate"}'

            retry_prompt = (
                f"Output ONLY a JSON object with dimensions in meters for a "
                f"{prim.value} part named '{node.label}'. "
                f"No explanation. Example: {ex}"
            )
            response2 = await model_manager.generate_async(
                model_id=mid,
                task_id=f"stage2_{task_id}_{node.label}_retry",
                lease_id="internal",
                lease_generation=0,
                system_prompt="Respond with ONLY a valid JSON object. No markdown, no explanation outside JSON.",
                prompt=retry_prompt,
                temperature=0.0,
            )
            manifest.record_llm_call()
            manifest.append_llm_log(node.label, retry_prompt, response2)
            result = cls._parse_response(response2, node)
        
        if result is None:
            raise Stage2Error(
                f"DIMENSION_PLAN_INVALID: '{node.label}' returned no valid "
                f"{node.geometry.primitive.value} dimensions after repair"
            )
        
        return cls._apply_orientation_aspect_guard(
            node, manifest,
            cls._apply_inset_fit_constraint(node, manifest, result),
        )

    @classmethod
    def _from_dict(cls, data: Dict[str, Any], reasoning: str = "") -> DimensionsOutput:
        return DimensionsOutput(
            size_x=data.get("size_x"), size_y=data.get("size_y"), size_z=data.get("size_z"),
            radius=data.get("radius"), radius2=data.get("radius2"), depth=data.get("depth"),
            major_radius=data.get("major_radius"), minor_radius=data.get("minor_radius"),
            reasoning=reasoning or data.get("reasoning", ""),
        )

    @classmethod
    def _shared_dimension_reference(cls, node: ManifestNode, manifest: BuildManifest) -> Optional[Dict[str, Any]]:
        """Find an already dimensioned equivalent from topology or repeat_key."""
        hint = node.stage_outputs.get("decomposition_hint", {})
        repeat_key = hint.get("repeat_key")
        candidates = []
        if repeat_key:
            candidates = [
                other for other in manifest.nodes.values()
                if other.node_id != node.node_id
                and other.kind == NodeKind.PART and other.geometry
                and other.geometry.primitive == node.geometry.primitive
                and other.stage_outputs.get("decomposition_hint", {}).get("repeat_key") == repeat_key
            ]
        else:
            # Equivalent leaves in sibling radial assemblies are a structural
            # repeated group, even if an older LLM omitted repeat_key.
            parent = manifest.nodes.get(node.parent_id) if node.parent_id else None
            grandparent = manifest.nodes.get(parent.parent_id) if parent and parent.parent_id else None
            if parent and grandparent and parent.attachment and parent.attachment.socket_type == SocketType.RADIAL:
                try:
                    path_index = parent.children_ids.index(node.node_id)
                except ValueError:
                    path_index = None
                for sibling_id in grandparent.children_ids:
                    sibling = manifest.nodes.get(sibling_id)
                    if not sibling or sibling.node_id == parent.node_id or not sibling.attachment:
                        continue
                    if sibling.attachment.socket_type != SocketType.RADIAL:
                        continue
                    # Sibling branch position is the stable topology identity.
                    # Matching only primitive type can copy the first torus
                    # (for example, a collar) onto a later torus (a guard).
                    if path_index is not None and path_index < len(sibling.children_ids):
                        other = manifest.nodes.get(sibling.children_ids[path_index])
                        if other and other.kind == NodeKind.PART and other.geometry and other.geometry.primitive == node.geometry.primitive:
                            candidates.append(other)
                    elif path_index is None:
                        # Legacy/incomplete trees occasionally omit the
                        # candidate from its parent's child list.  Primitive
                        # fallback is safe only when it is unambiguous.
                        matches = [
                            manifest.nodes.get(child_id) for child_id in sibling.children_ids
                            if manifest.nodes.get(child_id) and manifest.nodes[child_id].kind == NodeKind.PART
                            and manifest.nodes[child_id].geometry
                            and manifest.nodes[child_id].geometry.primitive == node.geometry.primitive
                        ]
                        if len(matches) == 1:
                            candidates.append(matches[0])
        for other in candidates:
            stage2 = other.stage_outputs.get("stage2")
            if isinstance(stage2, dict):
                return stage2
        return None
    
    @classmethod
    def _build_context(cls, node: ManifestNode, manifest: BuildManifest) -> str:
        """Build context string for LLM."""
        lines = []
        
        # Scale anchor
        stage0 = manifest.stage0_output or {}
        scale = stage0.get("scale_anchor_m", {})
        scale_value = scale.get("overall_height_or_length", 1.0)
        lines.append(f"Model: {manifest.prompt}")
        lines.append(f"Scale anchor: {scale_value}m ({scale.get('reasoning', 'overall size')})")
        contract = manifest.stats.get("model_contract", {})
        if contract:
            lines.append(
                "Global model contract: use metres; Z is up and -Y is front; "
                f"all parts together must fit a coherent {contract.get('overall_extent_m', scale_value)}m overall envelope. "
                "Dimension this part as a proportion of that one shared envelope, not in isolation."
            )
        reference = manifest.stats.get("reference_brief", {})
        if reference:
            lines.append(f"Reference shape/proportion rules: {reference.get('shape_rules', [])}; {reference.get('proportion_rules', [])}")
            profiles = reference.get("component_profiles", {})
            if profiles:
                lines.append(f"Contextual component design profiles: {profiles}. Use these only when they match this part's role/label; preserve the shared scale anchor.")
            scale_evidence = reference.get("scale_evidence") or {}
            if scale_evidence:
                lines.append(
                    "Cross-checked reference scale: "
                    f"{scale_evidence.get('overall_extent_m')}m "
                    f"({scale_evidence.get('reasoning', 'external specification')}). "
                    "Keep all dimensions consistent with this shared anchor."
                )
        lines.append("")
        
        # This part
        lines.append(f"Part to dimension: {node.label}")
        lines.append(f"Primitive type: {node.geometry.primitive.value}")
        lines.append(f"Socket type: {node.attachment.socket_type.value}")
        hint = node.stage_outputs.get("decomposition_hint", {}) or {}
        host_id = hint.get("inset_fit_host_node_id")
        host = manifest.nodes.get(host_id) if host_id else None
        if host and host.geometry:
            major = float(host.geometry.major_radius or 0.0)
            minor = float(host.geometry.minor_radius or 0.0)
            opening = 2.0 * (major - minor)
            if opening > 0:
                lines.append(
                    f"Physical fit constraint: this component is inside U-shaped host '{host.label}'. "
                    f"Its X-axis width must be no more than {opening * 0.90:.5g}m, leaving fork clearance."
                )
        
        # Parent context
        if node.parent_id:
            parent = manifest.nodes.get(node.parent_id)
            if parent:
                lines.append(f"\nParent: {parent.label} ({parent.kind.value})")
                if parent.geometry and "stage2" in parent.stage_outputs:
                    parent_dims = parent.stage_outputs["stage2"]
                    lines.append(f"Parent dimensions: {parent_dims}")
        
        # Sibling context (all siblings, dimensioned ones include their dims)
        if node.parent_id:
            parent = manifest.nodes.get(node.parent_id)
            if parent:
                all_sibs = []
                for sib_id in parent.children_ids:
                    if sib_id != node.node_id:
                        sib = manifest.nodes.get(sib_id)
                        if sib:
                            prim = sib.geometry.primitive.value if sib.geometry else "?"
                            if "stage2" in sib.stage_outputs:
                                all_sibs.append(f"  - {sib.label} ({prim}): {sib.stage_outputs['stage2']}")
                            else:
                                all_sibs.append(f"  - {sib.label} ({prim}): not yet dimensioned")
                if all_sibs:
                    lines.append(f"\nSiblings in same assembly:")
                    lines.extend(all_sibs)
        
        lines.append(f"\nProvide dimensions for {node.label} in meters.")
        
        # Repair feedback if this is a retry/re-dimension attempt
        feedback = node.stage_outputs.get("scene_quality_feedback")
        if feedback:
            lines.append("\nPREVIOUS BUILD QUALITY DEFECTS TO FIX:")
            for item in feedback:
                lines.append(f"  - Gate failure: {item.get('code')}")
                if item.get("expected"):
                    lines.append(f"    Expected orientation/aspect: {item.get('expected')}")
                if item.get("dimensions"):
                    lines.append(f"    Measured problematic dimensions: {item.get('dimensions')}")
                if item.get("gap_m"):
                    ref = item.get("reference_label") or item.get("reference_node_id") or "host"
                    lines.append(f"    Attachment gap: {float(item.get('gap_m')):.4f}m away from declared host '{ref}'")
                    lines.append(f"    Enlarge span or depth along connection axis so it bridges contact with '{ref}'.")
                if item.get("node_ids"):
                    lines.append(f"    Component was disconnected/floating from main body (members: {item.get('node_ids')[:5]}).")
            lines.append("Adjust dimensions to strictly satisfy these physical constraints.")
        
        return "\n".join(lines)

    @classmethod
    def _apply_inset_fit_constraint(
        cls, node: ManifestNode, manifest: BuildManifest, result: DimensionsOutput,
    ) -> DimensionsOutput:
        """Clamp the lateral size of an inset part to a resolved U-host opening.

        The LLM receives this constraint in its context, but this deterministic
        guard makes the physical containment invariant reliable even if the
        model ignores it.  It applies only when the planner identified the
        exact U_SHAPE/INSET topology.
        """
        hint = node.stage_outputs.get("decomposition_hint", {}) or {}
        host_id = hint.get("inset_fit_host_node_id")
        host = manifest.nodes.get(host_id) if host_id else None
        if not host or not host.geometry or host.geometry.primitive != PrimitiveType.U_SHAPE:
            return result
        major = float(host.geometry.major_radius or 0.0)
        minor = float(host.geometry.minor_radius or 0.0)
        max_width = 2.0 * (major - minor) * 0.90
        if max_width <= 0:
            return result

        changed = False
        if result.radius is not None and result.radius * 2.0 > max_width:
            result.radius = max_width / 2.0
            changed = True
        if result.size_x is not None and result.size_x > max_width:
            result.size_x = max_width
            changed = True
        if changed:
            suffix = f"clamped to {max_width:.5g}m U-bracket fork opening"
            result.reasoning = f"{result.reasoning}; {suffix}" if result.reasoning else suffix
            logger.info("Stage 2 inset-fit constraint: %s", suffix)
        return result
    
    @classmethod
    def _apply_orientation_aspect_guard(
        cls, node: 'ManifestNode', manifest: 'BuildManifest', result: DimensionsOutput,
    ) -> DimensionsOutput:
        """Ensure elongated primitives meet the scene-quality orientation ratio.

        ProductionSceneAudit enforces  max(dim_x, dim_y) / dim_z >= 1.25
        for horizontal/flat_horizontal orientations (and the inverse for
        vertical).  If the LLM proposes dimensions that would fail this
        gate, deterministically clamp the *length* axis up (or *cross-section*
        down) so the ratio is at least 1.5 — leaving headroom above the 1.25
        hard minimum.

        This guard runs after the LLM response is parsed and after any
        inset-fit clamping, so it is the last deterministic adjustment.
        """
        SAFE_RATIO = 1.5  # headroom above the 1.25 hard gate
        contract = (node.stage_outputs or {}).get("spatial_contract", {})
        orientation = str(contract.get("orientation", "")).lower()
        if orientation not in {"horizontal", "flat_horizontal", "vertical"}:
            return result

        prim = node.geometry.primitive if node.geometry else None
        # Only elongated primitives have a length vs cross-section distinction.
        _ELONGATED = {
            PrimitiveType.CYLINDER, PrimitiveType.CONE,
            PrimitiveType.CAPSULE, PrimitiveType.PRISM,
        }
        if prim not in _ELONGATED:
            return result

        depth = result.depth  # length axis
        radius = result.radius  # cross-section half-width
        if depth is None or radius is None or depth <= 0 or radius <= 0:
            return result

        diameter = 2.0 * radius
        if orientation == "horizontal":
            # After rotation the length axis maps to XY, cross-section to Z.
            # Required: depth / diameter >= SAFE_RATIO
            if depth < diameter * SAFE_RATIO:
                old_depth = depth
                result.depth = diameter * SAFE_RATIO
                suffix = (
                    f"orientation guard: depth clamped {old_depth:.5g} -> "
                    f"{result.depth:.5g}m (ratio {old_depth/diameter:.2f} < "
                    f"{SAFE_RATIO}; orientation={orientation})"
                )
                result.reasoning = f"{result.reasoning}; {suffix}" if result.reasoning else suffix
                logger.info("Stage 2 %s", suffix)
        elif orientation == "vertical":
            # Vertical: length axis stays on Z, cross-section on XY.
            # Required: depth / diameter >= SAFE_RATIO  (audit checks z > xy*ratio)
            if depth < diameter * SAFE_RATIO:
                old_depth = depth
                result.depth = diameter * SAFE_RATIO
                suffix = (
                    f"orientation guard: depth clamped {old_depth:.5g} -> "
                    f"{result.depth:.5g}m (ratio {old_depth/diameter:.2f} < "
                    f"{SAFE_RATIO}; orientation={orientation})"
                )
                result.reasoning = f"{result.reasoning}; {suffix}" if result.reasoning else suffix
                logger.info("Stage 2 %s", suffix)

        return result
    
    @classmethod
    def _default_output(cls, node: ManifestNode, manifest: Optional[BuildManifest] = None) -> DimensionsOutput:
        """Conservative geometric defaults keyed by primitive type and scale anchor."""
        prim = node.geometry.primitive
        scale = 1.0
        if manifest:
            stage0 = manifest.stage0_output or {}
            anchor = stage0.get("scale_anchor_m", {})
            scale = float(anchor.get("overall_height_or_length", 1.0) or 1.0)
            contract = manifest.stats.get("model_contract", {})
            if contract and "overall_extent_m" in contract:
                scale = float(contract["overall_extent_m"] or scale)

        if prim == PrimitiveType.TORUS:
            return DimensionsOutput(major_radius=0.15 * scale, minor_radius=0.01 * scale, reasoning="scale-anchored default")
        if prim == PrimitiveType.U_SHAPE:
            return DimensionsOutput(major_radius=0.05 * scale, minor_radius=0.005 * scale, reasoning="scale-anchored default")
        if prim in (PrimitiveType.CYLINDER, PrimitiveType.CAPSULE, PrimitiveType.HEMISPHERE):
            out = DimensionsOutput(radius=0.05 * scale, reasoning="scale-anchored default")
            if prim in (PrimitiveType.CYLINDER, PrimitiveType.CAPSULE):
                out.depth = 0.1 * scale
            return out
        if prim == PrimitiveType.CONE:
            return DimensionsOutput(radius=0.05 * scale, radius2=0.0, depth=0.1 * scale, reasoning="scale-anchored default")
        if prim == PrimitiveType.SPHERE:
            return DimensionsOutput(radius=0.05 * scale, reasoning="scale-anchored default")
        return DimensionsOutput(size_x=0.1 * scale, size_y=0.1 * scale, size_z=0.1 * scale, reasoning="scale-anchored default")

    @classmethod
    def _parse_response(cls, response: str, node: ManifestNode) -> "Optional[DimensionsOutput]":
        """Parse LLM response into DimensionsOutput, or return None on failure."""
        data = cls._extract_json(response)
        if not data:
            return None
        
        primitive = node.geometry.primitive
        output = DimensionsOutput(reasoning=data.get("reasoning", ""))
        
        # Parse based on primitive type
        if primitive in (PrimitiveType.BOX, PrimitiveType.PLANE, PrimitiveType.GRID, PrimitiveType.WEDGE):
            output.size_x = cls._required_positive_float(data, "size_x")
            output.size_y = cls._required_positive_float(data, "size_y")
            output.size_z = cls._required_positive_float(data, "size_z")
            if None in (output.size_x, output.size_y, output.size_z):
                return None
            
        elif primitive in (PrimitiveType.CYLINDER, PrimitiveType.CAPSULE, PrimitiveType.HEMISPHERE):
            output.radius = cls._required_positive_float(data, "radius")
            if output.radius is None:
                # Fallback: check if diameter was provided
                diam = cls._required_positive_float(data, "diameter")
                if diam is not None:
                    output.radius = diam * 0.5
                elif "size_x" in data and "size_y" in data:
                    # Bounding box fallback: radius is half of average horizontal extent
                    sx = cls._required_positive_float(data, "size_x")
                    sy = cls._required_positive_float(data, "size_y")
                    if sx is not None and sy is not None:
                        output.radius = (sx + sy) * 0.25
            if output.radius is None:
                return None
            if primitive in (PrimitiveType.CYLINDER, PrimitiveType.CAPSULE):
                minimum_depth = output.radius * 2 if primitive == PrimitiveType.CAPSULE else 0.0
                depth = cls._required_positive_float(data, "depth")
                if depth is None:
                    depth = cls._required_positive_float(data, "height")
                if depth is None:
                    depth = cls._required_positive_float(data, "length")
                if depth is None and "size_z" in data:
                    depth = cls._required_positive_float(data, "size_z")
                if depth is None:
                    return None
                output.depth = max(minimum_depth, depth)
                
        elif primitive == PrimitiveType.CONE:
            output.radius = cls._required_positive_float(data, "radius")
            output.radius2 = cls._get_float(data, "radius2", 0.0)  # Can be 0 for pointed
            output.depth = cls._required_positive_float(data, "depth")
            if output.radius is None or output.depth is None or output.radius2 < 0:
                return None
            
        elif primitive == PrimitiveType.SPHERE:
            output.radius = cls._required_positive_float(data, "radius")
            if output.radius is None:
                return None

        elif primitive == PrimitiveType.CIRCLE:
            output.radius = cls._required_positive_float(data, "radius")
            if output.radius is None:
                return None

        elif primitive in (PrimitiveType.PYRAMID, PrimitiveType.PRISM):
            output.radius = cls._required_positive_float(data, "radius")
            output.depth = cls._required_positive_float(data, "depth")
            if output.radius is None or output.depth is None:
                return None
            
        elif primitive in (PrimitiveType.TORUS, PrimitiveType.U_SHAPE):
            output.major_radius = cls._required_positive_float(data, "major_radius")
            output.minor_radius = cls._required_positive_float(data, "minor_radius")
            if output.major_radius is None or output.minor_radius is None:
                return None
        
        return output

    @staticmethod
    def _required_positive_float(data: dict, key: str) -> Optional[float]:
        value = data.get(key)
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None
    
    @classmethod
    def _get_positive_float(cls, data: dict, key: str, default: float) -> float:
        """Get a positive float from data, with default."""
        val = data.get(key)
        if val is None:
            return default
        try:
            f = float(val)
            return f if f > 0 else default
        except (TypeError, ValueError):
            return default
    
    @classmethod
    def _get_float(cls, data: dict, key: str, default: float) -> float:
        """Get a float from data (can be 0 or negative), with default."""
        val = data.get(key)
        if val is None:
            return default
        try:
            return float(val)
        except (TypeError, ValueError):
            return default
    
    @classmethod
    def _extract_json(cls, text: str) -> Optional[Dict[str, Any]]:
        """Extract JSON from LLM response."""
        try:
            return json.loads(text.strip())
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
