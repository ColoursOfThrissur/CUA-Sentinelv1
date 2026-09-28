"""Stage 4.5 — Modifier Intent Resolution.

Position: After Stage 4 (Deterministic Resolution), before Stage 5 (Blender Execution).

Governing rule: LLM never emits numeric modifier parameters. It selects from closed
vocabularies. Code derives every numeric value from the part's real geometry.

This stage adds modifier intent to each part in the resolved graph, which is then
converted to actual Blender modifier calls during graph_to_blender_steps().
"""

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class Stage45Error(Exception):
    """Raised when Stage 4.5 fails after retries."""
    pass


# ===== CLOSED VOCABULARIES =====
# LLM must pick from these exact values, nothing else

BEVEL_STYLES = frozenset({"none", "sharp", "soft", "heavy"})
SUBSURF_INTENTS = frozenset({"rounded", "very_smooth"})
SURFACE_DETAILS = frozenset({"none", "rivets", "panel_lines", "ribbing", "studs"})
DETAIL_DENSITIES = frozenset({"sparse", "medium", "dense"})


@dataclass
class BevelParams:
    """Resolved bevel modifier parameters."""
    width: float  # in meters
    segments: int


@dataclass
class SubsurfParams:
    """Resolved subdivision surface parameters."""
    levels: int
    render_levels: int


@dataclass
class ArrayDetailParams:
    """Resolved array modifier parameters for surface details."""
    base_mesh_type: str  # rivets | panel_lines | ribbing | studs
    count: int
    spacing: float  # exact spacing in meters
    base_radius: float  # size of individual detail element


@dataclass
class ModifierIntent:
    """Resolved modifier intent for a single part."""
    label: str
    bevel: Optional[BevelParams] = None
    subsurf: Optional[SubsurfParams] = None
    surface_detail: Optional[ArrayDetailParams] = None


def resolve_bevel(bevel_style: str, part_smallest_extent_m: float) -> Optional[BevelParams]:
    """Derive bevel parameters from style and part geometry.
    
    Args:
        bevel_style: One of BEVEL_STYLES
        part_smallest_extent_m: Smallest dimension of the part (radius for cylinder/sphere,
                                min half-size axis for box)
    
    Returns:
        BevelParams or None if bevel_style is "none"
    """
    if bevel_style == "none":
        return None
    
    if bevel_style not in BEVEL_STYLES:
        logger.warning(f"Invalid bevel_style '{bevel_style}', defaulting to 'none'")
        return None
    
    width_ratio = {"sharp": 0.01, "soft": 0.03, "heavy": 0.06}[bevel_style]
    segments = {"sharp": 1, "soft": 3, "heavy": 5}[bevel_style]
    
    width_m = round(part_smallest_extent_m * width_ratio, 5)
    # Hard floor/ceiling so degenerate geometry can't produce zero or absurd bevel
    width_m = max(0.0005, min(width_m, part_smallest_extent_m * 0.15))
    
    return BevelParams(width=width_m, segments=segments)


def resolve_subsurf(needs_subsurf: bool, subsurf_intent: str) -> Optional[SubsurfParams]:
    """Derive subdivision surface parameters.
    
    Args:
        needs_subsurf: Whether subdivision is needed
        subsurf_intent: One of SUBSURF_INTENTS (only used if needs_subsurf=True)
    
    Returns:
        SubsurfParams or None
    """
    if not needs_subsurf:
        return None
    
    if subsurf_intent not in SUBSURF_INTENTS:
        logger.warning(f"Invalid subsurf_intent '{subsurf_intent}', defaulting to 'rounded'")
        subsurf_intent = "rounded"
    
    levels = {"rounded": 1, "very_smooth": 2}[subsurf_intent]
    # Cap render_levels at 3 — higher is rarely visually distinguishable
    render_levels = min(levels + 1, 3)
    
    return SubsurfParams(levels=levels, render_levels=render_levels)


def resolve_surface_detail(
    detail_type: str,
    density: str,
    part_surface_length_m: float,
    part_smallest_extent_m: float,
) -> Optional[ArrayDetailParams]:
    """Derive array modifier parameters for surface details.
    
    Args:
        detail_type: One of SURFACE_DETAILS
        density: One of DETAIL_DENSITIES
        part_surface_length_m: Length of the edge/seam this detail runs along
        part_smallest_extent_m: Smallest dimension of the part (for sizing detail elements)
    
    Returns:
        ArrayDetailParams or None
    """
    if detail_type == "none":
        return None
    
    if detail_type not in SURFACE_DETAILS:
        logger.warning(f"Invalid detail_type '{detail_type}', skipping")
        return None
    
    if density not in DETAIL_DENSITIES:
        logger.warning(f"Invalid density '{density}', defaulting to 'medium'")
        density = "medium"
    
    spacing_m = {"sparse": 0.25, "medium": 0.12, "dense": 0.06}[density]
    count = max(2, int(part_surface_length_m / spacing_m))
    
    # Re-derive exact spacing from final integer count so array fits exactly
    exact_spacing_m = part_surface_length_m / count
    
    # Base element size scales with part size
    base_radius = part_smallest_extent_m * {
        "rivets": 0.006,
        "panel_lines": 0.004,
        "ribbing": 0.004,
        "studs": 0.01,
    }[detail_type]
    
    return ArrayDetailParams(
        base_mesh_type=detail_type,
        count=count,
        spacing=exact_spacing_m,
        base_radius=base_radius,
    )


def get_part_extents(sub_spec: dict) -> tuple:
    """Extract smallest extent and surface length from part sub_spec.
    
    Returns:
        (smallest_extent_m, surface_length_m)
    """
    prim = sub_spec.get("primitive", "box")
    
    if prim == "cylinder":
        radius = float(sub_spec.get("radius", 0.5))
        depth = float(sub_spec.get("depth", 1.0))
        return (radius, depth)  # smallest = radius, surface = depth (along axis)
    
    elif prim in ("sphere", "hemisphere"):
        radius = float(sub_spec.get("radius", 0.5))
        return (radius, radius * 2)  # circumference approximation
    
    elif prim == "cone":
        radius = float(sub_spec.get("radius1", 0.5))
        depth = float(sub_spec.get("depth", 1.0))
        return (min(radius, depth / 2), depth)
    
    else:  # box
        size = sub_spec.get("size", [1.0, 1.0, 1.0])
        if isinstance(size, list) and len(size) >= 3:
            half_sizes = [s / 2.0 for s in size]
            return (min(half_sizes), max(size))
        return (0.5, 1.0)


def resolve_modifier_intent_for_part(
    label: str,
    sub_spec: dict,
    llm_intent: dict,
) -> ModifierIntent:
    """Resolve modifier intent for a single part.
    
    Args:
        label: Part label
        sub_spec: Part's sub_spec from Stage 4
        llm_intent: LLM output for this part with keys:
            - bevel_style: str (from BEVEL_STYLES)
            - needs_subsurf: bool
            - subsurf_intent: str (from SUBSURF_INTENTS, only if needs_subsurf)
            - surface_detail: str (from SURFACE_DETAILS)
            - detail_density: str (from DETAIL_DENSITIES, only if surface_detail != "none")
    
    Returns:
        ModifierIntent with resolved parameters
    """
    smallest_extent, surface_length = get_part_extents(sub_spec)
    
    bevel = resolve_bevel(
        llm_intent.get("bevel_style", "none"),
        smallest_extent,
    )
    
    subsurf = resolve_subsurf(
        llm_intent.get("needs_subsurf", False),
        llm_intent.get("subsurf_intent", "rounded"),
    )
    
    surface_detail = resolve_surface_detail(
        llm_intent.get("surface_detail", "none"),
        llm_intent.get("detail_density", "medium"),
        surface_length,
        smallest_extent,
    )
    
    return ModifierIntent(
        label=label,
        bevel=bevel,
        subsurf=subsurf,
        surface_detail=surface_detail,
    )


def infer_modifier_intent_from_style(
    label: str,
    sub_spec: dict,
    style_tag: str,
    category: str = "",
) -> ModifierIntent:
    """Infer modifier intent from style_tag without LLM call.
    
    This is the fallback/default path when Stage 4.5 LLM is not run.
    Uses heuristics based on style_tag and primitive type.
    
    Args:
        label: Part label
        sub_spec: Part's sub_spec
        style_tag: Style from Stage 0
        category: Object category from Stage 0
    
    Returns:
        ModifierIntent with inferred parameters
    """
    prim = sub_spec.get("primitive", "box")
    smallest_extent, surface_length = get_part_extents(sub_spec)
    
    is_organic = style_tag in ("organic_worn", "soft_domestic")
    is_hard_surface = style_tag in ("hard_surface_industrial", "stylized_clean")
    
    # Bevel: boxes always get bevel, cylinders get light bevel for hard surface
    bevel = None
    if prim == "box":
        bevel_style = "soft" if is_organic else "sharp"
        bevel = resolve_bevel(bevel_style, smallest_extent)
    elif prim == "cylinder" and is_hard_surface:
        bevel = resolve_bevel("sharp", smallest_extent)
    
    # Subsurf: organic spheres/hemispheres
    subsurf = None
    if prim in ("sphere", "hemisphere") and is_organic:
        subsurf = resolve_subsurf(True, "rounded")
    
    # Surface detail: only for industrial style on larger parts
    surface_detail = None
    # Skip surface details in default inference — too risky without LLM guidance
    
    return ModifierIntent(
        label=label,
        bevel=bevel,
        subsurf=subsurf,
        surface_detail=surface_detail,
    )


# ===== LLM PROMPT TEMPLATE =====

STAGE45_SYSTEM_PROMPT = """You are a 3D modeling modifier specialist. Your task is to assign visual modifiers to each part of a 3D model.

You will receive:
1. The original object description
2. Stage 0 output: Object understanding (category, style, scale anchor, functional role)
3. Stage 1 output: Part topology (what parts exist and their relationships)
4. Stage 2 output: Resolved dimensions for each part
5. Stage 3 output: Attachment semantics (how parts connect)

Use ALL this context to make informed modifier decisions.

You must select from EXACT closed vocabularies - no other values are allowed:

bevel_style: "none" | "sharp" | "soft" | "heavy"
  - none: No edge beveling
  - sharp: Minimal bevel, 1 segment (technical/mechanical look)
  - soft: Medium bevel, 3 segments (general purpose)
  - heavy: Large bevel, 5 segments (rounded/worn look)

needs_subsurf: true | false
  - true: Apply subdivision surface for smoother geometry
  - false: Keep original geometry

subsurf_intent: "rounded" | "very_smooth" (only if needs_subsurf=true)
  - rounded: 1 subdivision level
  - very_smooth: 2 subdivision levels

surface_detail: "none" | "rivets" | "panel_lines" | "ribbing" | "studs"
  - none: No surface details
  - rivets: Small cylindrical protrusions along seams (industrial, mechanical)
  - panel_lines: Recessed grooves (vehicles, armor, industrial panels)
  - ribbing: Raised ridges (structural reinforcement, organic)
  - studs: Small hemispherical bumps (toys, decorative)

detail_density: "sparse" | "medium" | "dense" (only if surface_detail != "none")
  - sparse: Few details, wide spacing
  - medium: Moderate detail count
  - dense: Many details, tight spacing

Rules:
1. NEVER output numeric values - only vocabulary terms
2. Every part MUST have all fields specified
3. Match modifiers to the object's style_tag and each part's functional role
4. Organic/worn styles → soft/heavy bevels, subdivision on curved parts
5. Industrial/mechanical → sharp bevels, rivets/panel_lines on large flat surfaces
6. Small parts (< 5% of scale anchor) → usually "none" for surface_detail
7. Parts that are boolean cutters or will be deleted → "none" for everything
8. Consider the part's primitive type: boxes benefit from bevel, spheres from subsurf"""

STAGE45_USER_TEMPLATE = """# Original Request
{description}

# Stage 0: Object Understanding
{stage0_context}

# Stage 1: Part Topology
{stage1_context}

# Stage 2: Resolved Dimensions
{stage2_context}

# Stage 3: Attachment Semantics
{stage3_context}

# Parts Summary (with computed extents)
{parts_list}

---
For each part, output a JSON array with one object per part:
```json
[
  {{
    "label": "part_name",
    "bevel_style": "sharp|soft|heavy|none",
    "needs_subsurf": true|false,
    "subsurf_intent": "rounded|very_smooth",
    "surface_detail": "none|rivets|panel_lines|ribbing|studs",
    "detail_density": "sparse|medium|dense"
  }}
]
```

Output ONLY the JSON array, no explanation."""


def _format_stage0_context(stage0_output: Optional[dict]) -> str:
    """Format Stage 0 output for LLM context."""
    if not stage0_output:
        return "(not available)"
    
    lines = []
    if stage0_output.get("category"):
        lines.append(f"Category: {stage0_output['category']}")
    if stage0_output.get("style_tag"):
        lines.append(f"Style: {stage0_output['style_tag']}")
    if stage0_output.get("functional_role"):
        lines.append(f"Functional Role: {stage0_output['functional_role']}")
    
    anchor = stage0_output.get("scale_anchor", {})
    if anchor:
        if anchor.get("reference_object"):
            lines.append(f"Scale Reference: {anchor['reference_object']}")
        if anchor.get("overall_height_or_length_m"):
            lines.append(f"Overall Size: {anchor['overall_height_or_length_m']}m")
    
    if stage0_output.get("rests_on_surface") is not None:
        lines.append(f"Rests on Surface: {stage0_output['rests_on_surface']}")
    
    return "\n".join(lines) if lines else "(minimal data)"


def _format_stage1_context(stage1_output: Optional[dict]) -> str:
    """Format Stage 1 output for LLM context."""
    if not stage1_output:
        return "(not available)"
    
    parts = stage1_output.get("parts", [])
    if not parts:
        return "(no parts defined)"
    
    lines = []
    for p in parts:
        label = p.get("label", "unknown")
        prim = p.get("primitive", "box")
        parent = p.get("parent_label", "root")
        role = p.get("functional_role", "")
        
        line = f"- {label}: {prim}"
        if parent and parent != "root":
            line += f" (parent: {parent})"
        if role:
            line += f" [{role}]"
        lines.append(line)
    
    return "\n".join(lines)


def _format_stage2_context(stage2_output: Optional[dict]) -> str:
    """Format Stage 2 output for LLM context."""
    if not stage2_output:
        return "(not available)"
    
    lines = []
    if stage2_output.get("scale_anchor_m"):
        lines.append(f"Scale Anchor: {stage2_output['scale_anchor_m']}m")
    
    dims = stage2_output.get("dimensions", {})
    for label, dim in dims.items():
        if isinstance(dim, dict):
            prim = dim.get("primitive", "box")
            if prim == "box":
                size = dim.get("size", [])
                if size:
                    lines.append(f"- {label}: box {size[0]:.3f} x {size[1]:.3f} x {size[2]:.3f}m")
            elif prim == "cylinder":
                r = dim.get("radius", 0)
                d = dim.get("depth", 0)
                lines.append(f"- {label}: cylinder r={r:.3f}m, h={d:.3f}m")
            elif prim in ("sphere", "hemisphere"):
                r = dim.get("radius", 0)
                lines.append(f"- {label}: {prim} r={r:.3f}m")
            elif prim == "cone":
                r = dim.get("radius1", 0)
                d = dim.get("depth", 0)
                lines.append(f"- {label}: cone r={r:.3f}m, h={d:.3f}m")
    
    return "\n".join(lines) if lines else "(dimensions not parsed)"


def _format_stage3_context(stage3_output: Optional[dict]) -> str:
    """Format Stage 3 output for LLM context."""
    if not stage3_output:
        return "(not available)"
    
    semantics = stage3_output.get("semantics", {})
    if not semantics:
        return "(no semantics defined)"
    
    lines = []
    for label, sem in semantics.items():
        if isinstance(sem, dict):
            socket = sem.get("socket_type", "unknown")
            join = sem.get("join_mode", "parent_only")
            line = f"- {label}: {socket}"
            if join != "parent_only":
                line += f" (join: {join})"
            lines.append(line)
    
    return "\n".join(lines) if lines else "(semantics not parsed)"


def _build_parts_list(graph: Any) -> str:
    """Build formatted parts list for LLM prompt."""
    lines = []
    for node in graph.root.all_nodes():
        prim = node.sub_spec.get("primitive", "box")
        smallest, surface = get_part_extents(node.sub_spec)
        lines.append(f"- {node.label}: {prim}, smallest_extent={smallest:.3f}m, surface_length={surface:.3f}m")
    return "\n".join(lines)


def _parse_llm_response(raw: str, expected_labels: List[str]) -> Dict[str, dict]:
    """Parse and validate LLM JSON response.
    
    Returns:
        Dict mapping label to validated intent dict
    Raises:
        Stage45Error if parsing or validation fails
    """
    # Extract JSON from response
    json_match = re.search(r'\[\s*\{.*\}\s*\]', raw, re.DOTALL)
    if not json_match:
        raise Stage45Error(f"No JSON array found in response: {raw[:200]}")
    
    try:
        items = json.loads(json_match.group())
    except json.JSONDecodeError as e:
        raise Stage45Error(f"Invalid JSON: {e}")
    
    if not isinstance(items, list):
        raise Stage45Error("Response must be a JSON array")
    
    result = {}
    errors = []
    
    for item in items:
        label = item.get("label")
        if not label:
            errors.append("Missing 'label' field")
            continue
        
        # Validate closed vocabularies
        bevel = item.get("bevel_style", "none")
        if bevel not in BEVEL_STYLES:
            errors.append(f"{label}: invalid bevel_style '{bevel}'")
            bevel = "none"
        
        needs_sub = item.get("needs_subsurf", False)
        if not isinstance(needs_sub, bool):
            needs_sub = str(needs_sub).lower() == "true"
        
        sub_intent = item.get("subsurf_intent", "rounded")
        if sub_intent not in SUBSURF_INTENTS:
            sub_intent = "rounded"
        
        detail = item.get("surface_detail", "none")
        if detail not in SURFACE_DETAILS:
            errors.append(f"{label}: invalid surface_detail '{detail}'")
            detail = "none"
        
        density = item.get("detail_density", "medium")
        if density not in DETAIL_DENSITIES:
            density = "medium"
        
        result[label] = {
            "bevel_style": bevel,
            "needs_subsurf": needs_sub,
            "subsurf_intent": sub_intent,
            "surface_detail": detail,
            "detail_density": density,
        }
    
    # Check for missing parts
    for label in expected_labels:
        if label not in result:
            logger.warning(f"Stage 4.5: LLM missed part '{label}', using defaults")
            result[label] = {
                "bevel_style": "none",
                "needs_subsurf": False,
                "subsurf_intent": "rounded",
                "surface_detail": "none",
                "detail_density": "medium",
            }
    
    if errors:
        logger.warning(f"Stage 4.5 validation warnings: {errors}")
    
    return result


class Stage45ModifierIntent:
    """Stage 4.5: Modifier Intent Resolution.
    
    Two modes:
    1. With LLM: Calls LLM to get modifier intent per part, then resolves to params
    2. Without LLM: Infers intent from style_tag heuristics (fallback)
    """
    
    @classmethod
    def run_inference(
        cls,
        graph: Any,  # AssemblyGraph
        style_tag: str,
        category: str = "",
    ) -> Dict[str, ModifierIntent]:
        """Run modifier intent inference without LLM.
        
        Args:
            graph: AssemblyGraph from Stage 4
            style_tag: Style from Stage 0
            category: Object category from Stage 0
        
        Returns:
            Dict mapping part label to ModifierIntent
        """
        intents = {}
        
        for node in graph.root.all_nodes():
            intent = infer_modifier_intent_from_style(
                label=node.label,
                sub_spec=node.sub_spec,
                style_tag=style_tag,
                category=category,
            )
            intents[node.label] = intent
        
        return intents
    
    @classmethod
    async def run_with_llm(
        cls,
        graph: Any,  # AssemblyGraph
        style_tag: str,
        category: str,
        description: str,
        model_manager: Any,
        task_id: str,
        model_id: Optional[str] = None,
        stage0_output: Optional[dict] = None,
        stage1_output: Optional[dict] = None,
        stage2_output: Optional[dict] = None,
        stage3_output: Optional[dict] = None,
    ) -> Dict[str, ModifierIntent]:
        """Run modifier intent with LLM guidance.
        
        The LLM receives full context from all prior stages to make informed
        decisions based on the object's category, style, dimensions, and
        attachment semantics - not just guessing from the description.
        
        Args:
            graph: AssemblyGraph from Stage 4
            style_tag: Style from Stage 0
            category: Object category from Stage 0
            description: Original user prompt
            model_manager: Model manager for LLM calls
            task_id: Task ID for logging
            model_id: Optional specific model to use
            stage0_output: Full Stage 0 output (object understanding)
            stage1_output: Full Stage 1 output (part topology)
            stage2_output: Full Stage 2 output (dimensions)
            stage3_output: Full Stage 3 output (attachment semantics)
        
        Returns:
            Dict mapping part label to ModifierIntent
        """
        # Build rich context from all stages
        parts_list = _build_parts_list(graph)
        
        user_prompt = STAGE45_USER_TEMPLATE.format(
            description=description,
            stage0_context=_format_stage0_context(stage0_output),
            stage1_context=_format_stage1_context(stage1_output),
            stage2_context=_format_stage2_context(stage2_output),
            stage3_context=_format_stage3_context(stage3_output),
            parts_list=parts_list,
        )
        
        # Get expected labels for validation
        expected_labels = [node.label for node in graph.root.all_nodes()]
        
        # Call LLM
        try:
            response = await model_manager.generate(
                prompt=user_prompt,
                system_prompt=STAGE45_SYSTEM_PROMPT,
                model_id=model_id,
                temperature=0.3,  # Low temp for consistent vocabulary selection
                max_tokens=2000,
            )
            
            raw_text = response.get("text", "") if isinstance(response, dict) else str(response)
            
            # Parse and validate
            llm_intents = _parse_llm_response(raw_text, expected_labels)
            
            # Resolve to ModifierIntent objects
            intents = {}
            for node in graph.root.all_nodes():
                llm_intent = llm_intents.get(node.label, {})
                intent = resolve_modifier_intent_for_part(
                    label=node.label,
                    sub_spec=node.sub_spec,
                    llm_intent=llm_intent,
                )
                intents[node.label] = intent
            
            logger.info(f"[{task_id}] Stage 4.5 LLM complete: {len(intents)} parts")
            return intents
            
        except Exception as e:
            logger.warning(f"[{task_id}] Stage 4.5 LLM failed: {e}, falling back to inference")
            return cls.run_inference(graph, style_tag, category)
