"""Recursive Decomposer — breaks complex objects into variable-depth hierarchies.

This is the CRITICAL module that makes v5 different from v4:
- v4: Single-pass flat decomposition (all parts at depth 1)
- v5: Recursive decomposition with smart stop conditions

The decomposer asks the LLM to break down a node into children, then
evaluates each child to decide if it needs further decomposition.

Stop conditions (Blueprint §4.2):
A. Geometric manageability - single primitive or simple compound
B. Semantic cohesion - parts that move/function together
C. Independent verifiability - can be verified in isolation
D. Interface clarity - clear attachment points
E. Complexity budget - within limits
F. Depth limit - not too deep

Blueprint references: §4 (decomposition), §5 (stop conditions).
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from .manifest import BuildManifest, ManifestNode

from .node_types import (
    NodeKind,
    NodeImportance,
    SocketType,
    PrimitiveType,
    is_decomposable,
    DECOMPOSABLE_KINDS,
)
from .manifest import (
    NodeState,
    GeometrySpec,
    AttachmentSpec,
    ManifestNode,
)
from .hierarchy import ContainmentTree, HierarchyLimits

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Maximum parts from a single decomposition call
MAX_CHILDREN_PER_DECOMPOSITION = 12

# Complexity thresholds
SIMPLE_OBJECT_THRESHOLD = 3      # Objects with <= 3 parts don't need sub-assemblies
COMPLEX_ASSEMBLY_THRESHOLD = 8   # Assemblies with > 8 parts should be split

# Primitives that are always leaf nodes (never decompose further)
TERMINAL_PRIMITIVES = frozenset({
    PrimitiveType.SPHERE,
    PrimitiveType.HEMISPHERE,
    PrimitiveType.TORUS,
})


# ---------------------------------------------------------------------------
# Decomposition Result
# ---------------------------------------------------------------------------

class DecompositionDecision(str, Enum):
    """Decision about whether to decompose a node."""
    DECOMPOSE = "decompose"           # Break into children
    LEAF = "leaf"                     # Keep as-is (terminal)
    SKIP = "skip"                     # Skip (already decomposed or invalid)


@dataclass
class DecomposedChild:
    """A child produced by decomposition."""
    label: str
    kind: NodeKind
    primitive: Optional[PrimitiveType] = None
    socket_type: SocketType = SocketType.ROOT
    importance: NodeImportance = NodeImportance.REQUIRED
    
    # Semantic hints for Stage 3/4
    semantic_hints: Dict[str, Any] = field(default_factory=dict)
    
    # Whether this child should be further decomposed
    needs_decomposition: bool = False
    decomposition_reason: str = ""


@dataclass
class DecompositionResult:
    """Result of decomposing a single node."""
    node_id: str
    decision: DecompositionDecision
    children: List[DecomposedChild] = field(default_factory=list)
    error: Optional[str] = None
    llm_response: Optional[str] = None
    warnings: List[ValidationWarning] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return self.error is None and self.decision != DecompositionDecision.SKIP


# ---------------------------------------------------------------------------
# Decomposition Error
# ---------------------------------------------------------------------------

class DecompositionError(Exception):
    """Raised when decomposition fails."""
    pass


@dataclass
class ValidationWarning:
    """Structured record of a non-fatal LLM output coercion.

    Emitted whenever _parse_child silently overrides an invalid value
    rather than rejecting the child outright.  Collected in
    DecompositionResult.warnings so callers and telemetry can track
    LLM hallucination rates without any effect on geometry state.
    """
    node_label: str
    field: str          # e.g. "primitive"
    requested: str      # raw value from LLM
    coerced_to: str     # value actually used
    reason: str         # human-readable explanation


# ---------------------------------------------------------------------------
# Stop Condition Evaluator
# ---------------------------------------------------------------------------

class StopConditionEvaluator:
    """Evaluates whether a node should be decomposed further.
    
    Implements Blueprint §4.2 stop conditions.
    """
    
    def __init__(self, limits: HierarchyLimits):
        self.limits = limits
    
    def should_decompose(
        self,
        node: ManifestNode,
        manifest: BuildManifest,
        tree: ContainmentTree,
    ) -> Tuple[bool, str]:
        """Determine if a node should be decomposed.
        
        Returns (should_decompose, reason).
        
        FIX: Add logging for deep hierarchies to track why decomposition stops.
        """
        # A. Already has children - BUT if we have pre-parsed children, we should still process them
        # This check is now handled by the caller passing pre_parsed_children
        if node.children_ids:
            logger.debug(f"Decomposition skip: {node.label} already has {len(node.children_ids)} children")
            return False, "Already has children"
        
        # B. Not a decomposable kind
        if node.kind not in DECOMPOSABLE_KINDS:
            logger.debug(f"Decomposition skip: {node.label} kind {node.kind.value} not decomposable")
            return False, f"Kind {node.kind.value} is not decomposable"
        
        # C. At depth limit
        if node.hierarchy_depth >= self.limits.max_depth:
            logger.warning(
                f"Decomposition skip: {node.label} at depth limit ({node.hierarchy_depth}/{self.limits.max_depth})"
            )
            return False, f"At depth limit ({self.limits.max_depth})"
        
        # D. Would exceed total nodes
        remaining_capacity = self.limits.max_total_nodes - len(manifest.nodes)
        if remaining_capacity < 2:
            logger.warning(
                f"Decomposition skip: {node.label} near total nodes limit ({remaining_capacity} remaining)"
            )
            return False, "Near total nodes limit"
        
        # E. Terminal primitive (for PART nodes that somehow got here)
        if node.geometry and node.geometry.primitive in TERMINAL_PRIMITIVES:
            logger.debug(f"Decomposition skip: {node.label} is terminal primitive {node.geometry.primitive.value}")
            return False, f"Terminal primitive ({node.geometry.primitive.value})"
        
        # F. Check stage outputs for complexity hints
        # IMPORTANT: Don't stop decomposition if we have pre-parsed children
        # The "is_simple" flag from LLM is about whether the object ITSELF is simple,
        # not whether it has children that need to be added
        if "decomposition_hint" in node.stage_outputs:
            hint = node.stage_outputs["decomposition_hint"]
            # Only stop if marked simple AND no nested children
            if hint.get("is_simple", False) and not hint.get("_nested_children"):
                logger.debug(f"Decomposition skip: {node.label} marked as simple by LLM")
                return False, "Marked as simple by LLM"
            elif hint.get("_nested_children"):
                logger.info(f"Decomposition: {node.label} has {len(hint.get('_nested_children', []))} nested children to process")
        
        # G. Instance nodes are never decomposed (use definition)
        if node.kind == NodeKind.INSTANCE:
            logger.debug(f"Decomposition skip: {node.label} is INSTANCE node")
            return False, "Instance nodes use definition's structure"
        
        # Default: yes, decompose
        logger.debug(f"Decomposition approved: {node.label} at depth {node.hierarchy_depth}")
        return True, "Decomposition recommended"
    
    def evaluate_child_complexity(
        self,
        child: DecomposedChild,
        parent_depth: int,
    ) -> Tuple[bool, str]:
        """Evaluate if a decomposed child needs further decomposition.
        
        Returns (needs_decomposition, reason).
        """
        # PART nodes are terminal
        if child.kind == NodeKind.PART:
            return False, "PART nodes are terminal"
        
        # ASSEMBLY nodes may need decomposition
        if child.kind == NodeKind.ASSEMBLY:
            # Check semantic hints
            hints = child.semantic_hints
            
            # If LLM said it's complex
            if hints.get("is_complex", False):
                return True, "Marked as complex"
            
            # If it has sub-components mentioned
            if hints.get("has_subcomponents", False):
                return True, "Has sub-components"
            
            # If estimated part count is high
            estimated_parts = hints.get("estimated_parts", 0)
            if estimated_parts > SIMPLE_OBJECT_THRESHOLD:
                return True, f"Estimated {estimated_parts} parts"
            
            # Default for assemblies at shallow depth: decompose
            if parent_depth < 2:
                return True, "Shallow assembly, decompose for detail"
            
            return False, "Simple assembly"
        
        # MODEL nodes always decompose
        if child.kind == NodeKind.MODEL:
            return True, "MODEL nodes always decompose"
        
        return False, "Unknown kind"


# ---------------------------------------------------------------------------
# LLM Prompts for Decomposition
# ---------------------------------------------------------------------------

DECOMPOSITION_SYSTEM_PROMPT = """You are decomposing a 3D object into its component parts for Blender primitives.

Your task is to break down the given object into SIMPLE, MINIMAL components. Output a JSON object with:
- "children": Array of components this object breaks down into
- "is_simple": Boolean - true if this is a simple object

Each child in the "children" array has:
- "label": Unique snake_case name (e.g., "tabletop", "leg", "seat")
- "kind": Either "assembly" (has sub-parts) or "part" (single primitive)
- "primitive": For "part" kind only - one of: "box", "cylinder", "cone", "sphere", "hemisphere", "torus", "u_shape", "plane", "wedge", "pyramid", "prism", "capsule"
- "socket_type": How this attaches to parent (see SOCKET VOCABULARY below)
- "attach_to": Optional label of the exact sibling or part this attaches to.
- "attach_anchor": Optional named anchor on attach_to, such as "top_center".
- "importance": "required", "optional", or "decorative"
- "is_complex": Boolean - true if this assembly needs further decomposition
- "has_subcomponents": Boolean - true if this has parts that stack on it
- "estimated_parts": Number - usually 1 for parts
- "material_hint": Material description (see MATERIAL VOCABULARY below)
- "style_hint": Surface style (see STYLE VOCABULARY below)
- "length_axis": For elongated primitives, the axis of their long dimension: "x", "y", or "z"
- "repeat_key": Shared key for interchangeable repeated components
- "structural_role": Optional physical role: "support", "strut", "guard",
  "spoke", "frame", "housing", "trim", or "fastener".
- "endpoint_intent": For a long support/brace, use "between_anchors" rather
  than leaving it as a detached ROOT primitive.  The deterministic planner
  chooses exact endpoints; do not provide numeric coordinates.
- "allow_disconnected": Optional boolean. Use true only when a visible air
  gap is intentional, such as a suspended element or hinge clearance.

For connector sockets (BRIDGE, STRUT, RADIAL_BRIDGE, RELATIVE_TO), include additional fields as specified below.

MATERIAL VOCABULARY (use these terms in material_hint):
- Metals: "polished steel", "brushed steel", "brushed aluminum", "chrome", "copper", "brass", "gold", "iron", "rusty metal"
- Plastics: "glossy plastic", "matte plastic", "black plastic", "white plastic", "rubber", "silicone"
- Wood: "light wood", "dark wood", "oak wood", "walnut wood", "painted white wood", "varnished wood"
- Glass: "clear glass", "frosted glass", "tinted glass", "acrylic"
- Fabric: "cotton fabric", "velvet", "leather", "black leather"
- Stone: "concrete", "marble", "granite"
- Ceramic: "white ceramic", "glazed ceramic", "porcelain"
- Emissive: "led white", "led red", "led green", "led blue", "screen"
- Car paint: "car paint red", "car paint black", "metallic car paint"

STYLE VOCABULARY (use these terms in style_hint):
- "smooth" - basic smooth surface (subdivision modifier)
- "beveled" or "beveled edges" - rounded edges (bevel modifier)
- "sharp" or "hard surface" - crisp edges (edge split modifier)
- "organic" - soft organic shapes (subdivision + smooth)
- "mechanical" or "hard surface mechanical" - precise mechanical look (bevel + weighted normal)
- "panel" or "paneled" - panel lines (solidify modifier)
- "game ready" - optimized for games (triangulate + decimate)

ARTISTIC DIRECTION (apply to every build):
- Choose materials that feel authentic and specific — not just "metal" but "brushed brass", "aged copper", "polished chrome"
- Vary surface styles across parts of the same object — a lamp might have a "smooth" shade, "mechanical" base, and "beveled" arm
- For organic objects (fruit, animals, plants) use "organic" style with subsurface-appropriate materials
- For industrial/mechanical objects mix "hard surface mechanical" with "beveled" accents
- For furniture prefer "smooth beveled" on main surfaces and "smooth" on legs/supports
- Emit a "style_hint" that is SPECIFIC — e.g. "smooth beveled" not just "smooth"
- When the prompt mentions a finish (matte, glossy, brushed, aged, worn) reflect it in material_hint

CRITICAL RULES:
1. KEEP IT SIMPLE - a table is just: tabletop (box) + 4 legs (cylinders). That's it.
2. NO decorative sub-parts like "edge bands", "braces", "connectors", "plates" unless explicitly requested
3. Use "part" kind for everything that can be a single primitive
4. Use "assembly" for things that have OTHER PARTS STACKED ON THEM
5. NEVER invent numeric positions or distances - use socket types with closed vocabulary fields
6. ALWAYS include material_hint and style_hint for EVERY part
7. For elongated primitives (cylinder, cone, capsule, prism, box), include
   "length_axis": "x" | "y" | "z" when their long direction matters. Blender
   primitives default to Z, so "horizontal" must be emitted as x or y.
8. For repeated interchangeable components, include the same "repeat_key" on
   every occurrence. Repeated components must have identical geometry/material.
9. Long legs, braces, rails, handles, and cables must declare their physical
   structural_role and endpoint_intent when their two ends attach to things.
10. Sibling labels must be unique. Names may recur in different assemblies;
    stable hierarchy IDs provide global identity.
11. Create assemblies only for meaningful reusable or multi-part
    subassemblies. A leaf part may attach directly to its parent assembly.
12. RADIAL DISTRIBUTION: Multi-rotor arms, struts, propeller guards, and legs extending outward from a central body MUST use "RADIAL" socket_type (with radial_count and radial_index: 0..N-1) around the circumference. NEVER use "ARRAY_MEMBER" along Z for arms or rotors (that stacks them vertically inside each other).

STACKED OBJECTS:
For stacked objects, use nested assemblies only for actual multi-part levels:
- A level with several dependent parts may become its own assembly
- The bottom part of that level is the ROOT of that assembly
- Parts that attach to it are siblings inside that same assembly
- This nesting continues upward: if the top of level-1 has more parts, those form level-2 assembly
- Leaf parts at different heights may be siblings with different sockets

Generic example pattern:
WRONG: main_assembly { bottom_part, middle_part, top_part, attached_part } — all flat siblings
CORRECT: main_assembly { bottom_part(ROOT), middle_assembly(TOP_CENTER) { middle_part(ROOT), top_assembly(TOP_CENTER) { top_part(ROOT), attached_assembly(FRONT_FACE) { attached_part(ROOT) } } } }

ASSEMBLY ECONOMY RULE:
- Do not create a one-child wrapper merely because a part uses a non-ROOT socket.
- Create an assembly only when it owns multiple parts or is a meaningful reusable unit.

STACKED ASSEMBLY GUIDANCE:
When objects stack vertically (bottom → middle → top), each level MUST be nested inside the previous level.
- Nest levels only when each level is itself a multi-part unit.
- Otherwise attach leaf parts directly with semantic sockets.

WRONG: level1_assembly(depth 1), level2_assembly(depth 1), level3_assembly(depth 1)
CORRECT: level1_assembly(depth 1) { level2_assembly(depth 2) { level3_assembly(depth 3) } }

SOCKET TYPE VOCABULARY:
- ROOT: The first/main part of this level (only ONE per assembly)
- TOP_CENTER, BOTTOM_CENTER: Stacked above/below parent
- LEFT_CENTER, RIGHT_CENTER, FRONT_CENTER, BACK_CENTER: Adjacent to parent on that side
- FRONT_FACE, BACK_FACE, LEFT_FACE, RIGHT_FACE, TOP_FACE, BOTTOM_FACE: Mounted flush on a face
- LEFT_END, RIGHT_END, TOP_END, BOTTOM_END: At the end of an elongated parent
- THROUGH_AXIS: Passes through the parent (axles, crossbars) - requires pierce_direction, height_hint
- ARRAY_MEMBER: One of a repeated row/cluster on a face - requires array_axis, array_count, array_index
- RADIAL: Evenly spaced around parent's circumference - requires radial_count, radial_index
- RADIAL_BRIDGE: Connects parent's circumference to another named part - requires connects_to, radial_count, radial_index
- STRUT: A single diagonal connector to another named part - requires connects_to
- BRIDGE: A horizontal connector between parent and another named part - requires connects_to, position_fraction ("start"|"quarter"|"middle"|"three_quarter"|"end")
- RELATIVE_TO: Positioned next to another named part - requires relative_to, direction ("left"|"right"|"front"|"back"|"above"|"below"), gap ("touching"|"small"|"medium"|"large")
- CORNER: At a corner of parent (use label like leg_front_left to specify which)
- BOOLEAN_CUT: Cuts a hole in the parent (for windows, holes, cutouts) - the cutter shape is subtracted from parent
- INSET: Recessed into parent surface (for glass panels, screens, inlays that fill a hole) - use AFTER a BOOLEAN_CUT sibling

GLASS INSETS AND CUTOUTS:
For a glass panel inset into a tabletop or frame:
1. Use BOOLEAN_CUT for the hole shape (e.g., "glass_cutout" with primitive "box")
2. Use INSET for the glass panel that fills the hole (e.g., "glass_panel" with primitive "box")
The INSET part will be positioned inside the hole created by BOOLEAN_CUT.

NEVER invent a numeric position. If a relationship doesn't fit one of the sockets above, pick the closest one and let its semantic fields describe the relationship.

Example for a generic stacked object (base → pole → head with radial parts + enclosure):
```json
{
  "is_simple": false,
  "children": [
    {
      "label": "base_assembly",
      "kind": "assembly",
      "socket_type": "ROOT",
      "importance": "required",
      "is_complex": true,
      "has_subcomponents": true,
      "children": [
        {"label": "base_part", "kind": "part", "primitive": "cylinder", "socket_type": "ROOT", "importance": "required", "material_hint": "black plastic", "style_hint": "smooth beveled"},
        {
          "label": "pole_assembly",
          "kind": "assembly",
          "socket_type": "TOP_CENTER",
          "importance": "required",
          "is_complex": true,
          "has_subcomponents": true,
          "children": [
            {"label": "pole_part", "kind": "part", "primitive": "cylinder", "socket_type": "ROOT", "importance": "required", "material_hint": "chrome", "style_hint": "smooth"},
            {
              "label": "head_assembly",
              "kind": "assembly",
              "socket_type": "TOP_CENTER",
              "importance": "required",
              "is_complex": true,
              "children": [
                {"label": "head_body", "kind": "part", "primitive": "cylinder", "socket_type": "ROOT", "importance": "required", "material_hint": "white plastic", "style_hint": "smooth"},
                {"label": "front_hub", "kind": "part", "primitive": "sphere", "socket_type": "FRONT_FACE", "importance": "required", "material_hint": "white plastic", "style_hint": "smooth"},
                {"label": "radial_part_1", "kind": "part", "primitive": "box", "socket_type": "RADIAL", "radial_count": 4, "radial_index": 0, "importance": "required", "material_hint": "white plastic", "style_hint": "smooth"},
                {"label": "radial_part_2", "kind": "part", "primitive": "box", "socket_type": "RADIAL", "radial_count": 4, "radial_index": 1, "importance": "required", "material_hint": "white plastic", "style_hint": "smooth"},
                {"label": "radial_part_3", "kind": "part", "primitive": "box", "socket_type": "RADIAL", "radial_count": 4, "radial_index": 2, "importance": "required", "material_hint": "white plastic", "style_hint": "smooth"},
                {"label": "radial_part_4", "kind": "part", "primitive": "box", "socket_type": "RADIAL", "radial_count": 4, "radial_index": 3, "importance": "required", "material_hint": "white plastic", "style_hint": "smooth"},
                {
                  "label": "enclosure_assembly",
                  "kind": "assembly",
                  "socket_type": "FRONT_FACE",
                  "importance": "required",
                  "is_complex": true,
                  "children": [
                    {"label": "enclosure_ring_1", "kind": "part", "primitive": "torus", "socket_type": "ROOT", "importance": "required", "material_hint": "chrome", "style_hint": "smooth"},
                    {"label": "enclosure_ring_2", "kind": "part", "primitive": "torus", "socket_type": "RELATIVE_TO", "relative_to": "enclosure_ring_1", "direction": "front", "gap": "small", "importance": "required", "material_hint": "chrome", "style_hint": "smooth"}
                  ]
                }
              ]
            }
          ]
        }
      ]
    }
  ]
}
```

Example for "simple wooden table with 4 legs":
```json
{
  "is_simple": true,
  "children": [
    {"label": "tabletop", "kind": "part", "primitive": "box", "socket_type": "ROOT", "importance": "required", "material_hint": "dark wood", "style_hint": "smooth beveled"},
    {"label": "leg_front_left", "kind": "part", "primitive": "cylinder", "socket_type": "CORNER", "importance": "required", "material_hint": "dark wood", "style_hint": "smooth"},
    {"label": "leg_front_right", "kind": "part", "primitive": "cylinder", "socket_type": "CORNER", "importance": "required", "material_hint": "dark wood", "style_hint": "smooth"},
    {"label": "leg_back_left", "kind": "part", "primitive": "cylinder", "socket_type": "CORNER", "importance": "required", "material_hint": "dark wood", "style_hint": "smooth"},
    {"label": "leg_back_right", "kind": "part", "primitive": "cylinder", "socket_type": "CORNER", "importance": "required", "material_hint": "dark wood", "style_hint": "smooth"}
  ]
}
```

Example for "coffee table with glass inset":
```json
{
  "is_simple": true,
  "children": [
    {"label": "tabletop_frame", "kind": "part", "primitive": "box", "socket_type": "ROOT", "importance": "required", "material_hint": "dark wood", "style_hint": "smooth beveled"},
    {"label": "glass_cutout", "kind": "part", "primitive": "box", "socket_type": "BOOLEAN_CUT", "importance": "required", "material_hint": "none", "style_hint": "sharp"},
    {"label": "glass_panel", "kind": "part", "primitive": "box", "socket_type": "INSET", "importance": "required", "material_hint": "clear glass", "style_hint": "smooth"},
    {"label": "leg_front_left", "kind": "part", "primitive": "cylinder", "socket_type": "CORNER", "importance": "required", "material_hint": "brushed steel", "style_hint": "smooth"},
    {"label": "leg_front_right", "kind": "part", "primitive": "cylinder", "socket_type": "CORNER", "importance": "required", "material_hint": "brushed steel", "style_hint": "smooth"},
    {"label": "leg_back_left", "kind": "part", "primitive": "cylinder", "socket_type": "CORNER", "importance": "required", "material_hint": "brushed steel", "style_hint": "smooth"},
    {"label": "leg_back_right", "kind": "part", "primitive": "cylinder", "socket_type": "CORNER", "importance": "required", "material_hint": "brushed steel", "style_hint": "smooth"}
  ]
}
```

Example for "step ladder with 2 rails and 3 rungs":
```json
{
  "is_simple": true,
  "children": [
    {"label": "left_rail", "kind": "part", "primitive": "box", "socket_type": "ROOT", "importance": "required", "material_hint": "light wood", "style_hint": "smooth"},
    {"label": "right_rail", "kind": "part", "primitive": "box", "socket_type": "RELATIVE_TO", "relative_to": "left_rail", "direction": "right", "gap": "medium", "importance": "required", "material_hint": "light wood", "style_hint": "smooth"},
    {"label": "rung_bottom", "kind": "part", "primitive": "box", "socket_type": "BRIDGE", "connects_to": "right_rail", "position_fraction": "quarter", "importance": "required", "material_hint": "light wood", "style_hint": "smooth"},
    {"label": "rung_middle", "kind": "part", "primitive": "box", "socket_type": "BRIDGE", "connects_to": "right_rail", "position_fraction": "middle", "importance": "required", "material_hint": "light wood", "style_hint": "smooth"},
    {"label": "rung_top", "kind": "part", "primitive": "box", "socket_type": "BRIDGE", "connects_to": "right_rail", "position_fraction": "three_quarter", "importance": "required", "material_hint": "light wood", "style_hint": "smooth"}
  ]
}
```

PRIMITIVE SELECTION GUIDE:
- Fan blades (individual blade): "box" (flat, angled) or "cylinder" (disc/impeller) — NEVER "torus"
- Rings, donuts, gaskets, O-rings: "torus"
- Round housings, balls: "sphere"
- Poles, stands, legs: "cylinder"
- Flat surfaces, boxes: "box"
- Pointed things: "cone"
- U-shaped bent tubes (padlock shackle, handle, hook, bail): "u_shape" — ONE single part, never split into legs
- Half-dome, bowl: "hemisphere"

Output ONLY valid JSON, no markdown, no explanation."""

# Capability declarations, validation and execution must not drift.  The
# static examples above teach form choice; this appended line is the
# authoritative executable vocabulary.
from .capabilities import planner_primitive_vocabulary
DECOMPOSITION_SYSTEM_PROMPT += (
    "\nACTIVE EXECUTABLE PRIMITIVES (authoritative): "
    + planner_primitive_vocabulary()
)


ASSEMBLY_DECOMPOSITION_PROMPT = """You are decomposing the assembly "{assembly_label}" into its parts.

Full object being built: {parent_context}
Current depth: {depth} (max: {max_depth})
Remaining node budget: {remaining_nodes}
Max children this call: {max_children}

STRUCTURAL RULES (same as root decomposition — apply them here too):
1. Exactly ONE child must have socket_type "ROOT" — it is the reference geometry for this assembly.
2. Every other child must have a non-ROOT socket type from the vocabulary below.
3. If depth is near max ({max_depth}), use "part" kind only — no more assemblies.
4. NEVER invent numeric positions. Use socket vocabulary exclusively.
   The ROOT child must be a physical "part", never an "assembly" wrapper.
   Every emitted assembly must directly contain a physical part; never emit a
   same-named group inside itself (for example landing_feet_group -> landing_feet_group).
5. ALWAYS include material_hint and style_hint on every part.
6. ALL labels must be unique across the entire model — prefix with the assembly name if needed.
7. RADIAL DISTRIBUTION: Multi-rotor arms, struts, propeller guards, and legs MUST use "RADIAL" socket_type (with radial_count and radial_index: 0..N-1) so they fan out horizontally around the center. NEVER use "ARRAY_MEMBER" along Z for arms or rotors (that stacks them vertically like logs inside the body).

SOCKET VOCABULARY (pick the closest fit):
- ROOT: reference geometry for this assembly (exactly one)
- TOP_CENTER / BOTTOM_CENTER: stacked above/below ROOT
- FRONT_FACE / BACK_FACE / LEFT_FACE / RIGHT_FACE / TOP_FACE / BOTTOM_FACE: flush on a face
- FRONT_CENTER / BACK_CENTER / LEFT_CENTER / RIGHT_CENTER: adjacent to ROOT on that side
- RADIAL: evenly around circumference — requires radial_count, radial_index
- CORNER: at a corner of ROOT (label must contain front_left/front_right/back_left/back_right)
- BRIDGE: horizontal span to another named part — requires connects_to, position_fraction
- RELATIVE_TO: next to another named part — requires relative_to, direction, gap
- BOOLEAN_CUT: subtracts from ROOT geometry
- INSET: fills a BOOLEAN_CUT hole

NESTING RULE: create an assembly only for a real subassembly with a physical
ROOT part. Do not create organisational or pass-through wrapper assemblies.

Output ONLY valid JSON with a "children" array and "is_simple" boolean. No markdown, no explanation."""


# ---------------------------------------------------------------------------
# Recursive Decomposer
# ---------------------------------------------------------------------------

class RecursiveDecomposer:
    """Recursively decomposes complex objects into variable-depth hierarchies.
    
    This is the core of v5's progressive assembly approach:
    1. Start with root MODEL node
    2. Ask LLM to decompose into children
    3. For each child marked as complex, recursively decompose
    4. Stop when hitting limits or simple parts
    
    Unlike v4 which does single-pass flat decomposition, this creates
    proper hierarchies like:
        ship
        ├── hull_assembly
        │   ├── hull_body (part)
        │   ├── bow (part)
        │   └── stern (part)
        ├── mast_assembly
        │   ├── mast_pole (part)
        │   └── sail (part)
        └── deck_assembly
            ├── deck_floor (part)
            └── railing (part)
    """
    
    def __init__(
        self,
        limits: Optional[HierarchyLimits] = None,
        max_llm_calls: int = 30,
    ):
        self.limits = limits or HierarchyLimits()
        self.max_llm_calls = max_llm_calls
        self.llm_call_count = 0
        self.stop_evaluator = StopConditionEvaluator(self.limits)
    
    async def decompose(
        self,
        manifest: BuildManifest,
        model_manager: Any,
        task_id: str,
        model_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Recursively decompose the manifest's root node.
        
        Mutates manifest in-place, adding hierarchy.
        
        Returns dict with statistics about the decomposition.
        """
        self.llm_call_count = 0
        tree = ContainmentTree(manifest, self.limits)
        
        stats = {
            "llm_calls": 0,
            "nodes_created": 0,
            "max_depth_reached": 0,
            "decomposition_stopped_reasons": [],
        }
        
        # Start with root
        root = manifest.get_root()
        
        # Decompose recursively
        await self._decompose_node(
            node=root,
            manifest=manifest,
            tree=tree,
            model_manager=model_manager,
            task_id=task_id,
            model_id=model_id,
            stats=stats,
        )
        
        stats["llm_calls"] = self.llm_call_count
        stats["total_nodes"] = len(manifest.nodes)
        stats["max_depth_reached"] = tree.max_depth

        exhausted = [
            item for item in stats.get("decomposition_stopped_reasons", [])
            if item.get("reason") == "LLM call budget exhausted"
        ]
        stats["decomposition_complete"] = not exhausted
        stats["decomposition_budget_exhausted"] = exhausted
        manifest.stats.update(stats)
        if exhausted:
            manifest.record_event(
                "decomposition_budget_exhausted",
                details={"nodes": exhausted, "max_llm_calls": self.max_llm_calls},
            )
            manifest.save()
            labels = ", ".join(str(item.get("node")) for item in exhausted[:8])
            raise DecompositionError(
                f"DECOMPOSITION_BUDGET_EXHAUSTED: unresolved nodes: {labels}"
            )
        manifest.save()
        
        return stats
    
    async def _decompose_node(
        self,
        node: ManifestNode,
        manifest: BuildManifest,
        tree: ContainmentTree,
        model_manager: Any,
        task_id: str,
        model_id: Optional[str],
        stats: Dict[str, Any],
        pre_parsed_children: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """Decompose a single node and recursively decompose children.
        
        Args:
            pre_parsed_children: If provided, use these instead of calling LLM.
                                This handles nested children from a single LLM response.
        """
        # Check if we should decompose
        should, reason = self.stop_evaluator.should_decompose(node, manifest, tree)
        
        if not should:
            logger.info(f"Decomposition stopped for {node.label}: {reason}")
            # Re-decomposition callers may supply an empty stats mapping.
            # Record the stop reason without turning a legitimate budget stop
            # into a KeyError that hides the real outcome.
            stats.setdefault("decomposition_stopped_reasons", []).append({
                "node": node.label,
                "reason": reason,
            })
            # Still transition to READY so children can be built
            if node.state == NodeState.PLANNED:
                manifest.transition(node.node_id, NodeState.READY)
            return
        
        # If we have pre-parsed children, use them directly (no LLM call needed)
        if pre_parsed_children is not None:
            result = self._parse_pre_parsed_children(node, pre_parsed_children)
            # Transition to DECOMPOSING
            if node.state == NodeState.PLANNED:
                manifest.transition(node.node_id, NodeState.DECOMPOSING)
        else:
            # Check LLM call budget
            if self.llm_call_count >= self.max_llm_calls:
                stats.setdefault("decomposition_stopped_reasons", []).append({
                    "node": node.label,
                    "reason": "LLM call budget exhausted",
                })
                # Still transition to READY
                if node.state == NodeState.PLANNED:
                    manifest.transition(node.node_id, NodeState.READY)
                return
            
            # Transition to DECOMPOSING state
            if node.state == NodeState.PLANNED:
                manifest.transition(node.node_id, NodeState.DECOMPOSING)
            
            # Call LLM to decompose
            result = await self._call_llm_decompose(
                node=node,
                manifest=manifest,
                tree=tree,
                model_manager=model_manager,
                task_id=task_id,
                model_id=model_id,
            )
        
        if not result.success:
            logger.warning(f"Decomposition failed for {node.label}: {result.error}")
            manifest.transition(node.node_id, NodeState.FAILED, error=result.error)
            return
        
        # Build the candidate spec list first — no manifest writes yet.
        # Reject recursive assembly wrappers before duplicate-label scoping.
        # Without this, ``feet_assembly -> feet_assembly`` becomes an
        # unbounded renamed wrapper chain and later a DAG cycle.
        def canonical_assembly_label(value: str) -> str:
            value = re.sub(r"(?:[_-]?\d+)+$", "", value.lower())
            return re.sub(r"(?:[_-]?assembly)+$", "", value).strip("_-")

        ancestor_labels = {canonical_assembly_label(node.label)}
        for ancestor_id in manifest.get_ancestors(node.node_id):
            ancestor = manifest.nodes.get(ancestor_id)
            if ancestor:
                ancestor_labels.add(canonical_assembly_label(ancestor.label))
        retained_children = []
        discarded = []
        for child in result.children:
            if child.kind == NodeKind.ASSEMBLY and canonical_assembly_label(child.label) in ancestor_labels:
                discarded.append(child.label)
            else:
                retained_children.append(child)
        if discarded:
            logger.warning("Discarding recursive assembly wrapper(s) under %s: %s", node.label, ", ".join(discarded))
            manifest.record_event("decomposition_recursive_wrappers_discarded", node_id=node.node_id, details={"labels": discarded})
            result.children = retained_children
        if not result.children:
            manifest.transition(node.node_id, NodeState.FAILED, error="DECOMPOSITION_RECURSIVE_WRAPPER_ONLY")
            return

        # Record warnings such as duplicate root demotion to manifest events
        for warn in result.warnings:
            if "DUPLICATE_ROOT" in warn.reason:
                manifest.record_event(
                    "decomposition_duplicate_root_demoted",
                    node_id=node.node_id,
                    details={
                        "parent": node.label,
                        "demoted_child": warn.node_label,
                        "demoted_socket": warn.coerced_to,
                    },
                )

        # Ensure anchor exists: either exactly one ROOT child exists,
        # OR all children are anchored to assembly frame (CORNER, RADIAL, ARRAY_MEMBER)
        _FRAME_RELATIVE_SOCKETS = {
            SocketType.CORNER,
            SocketType.RADIAL,
            SocketType.ARRAY_MEMBER,
            SocketType.RADIAL_BRIDGE,
        }
        root_children = [c for c in result.children if c.socket_type == SocketType.ROOT]
        all_frame_anchored = (
            len(result.children) > 0
            and all(c.socket_type in _FRAME_RELATIVE_SOCKETS for c in result.children)
        )
        if len(root_children) == 0:
            if all_frame_anchored:
                logger.info(
                    "ASSEMBLY_FRAME_ANCHOR: all %d children under '%s' attach to assembly frame directly (%s). No child forced to ROOT.",
                    len(result.children), node.label, ", ".join(c.socket_type.value for c in result.children[:4])
                )
                manifest.record_event(
                    "decomposition_frame_anchor",
                    node_id=node.node_id,
                    details={
                        "parent": node.label,
                        "anchor_type": "assembly_frame",
                        "child_count": len(result.children),
                    },
                )
            elif result.children:
                # Fallback: promote child 0 to ROOT only when not frame-anchored
                promoted = result.children[0]
                orig_socket = promoted.socket_type
                promoted.socket_type = SocketType.ROOT
                logger.info(
                    "ANCHOR_TO_ASSEMBLY_ORIGIN: no ROOT child in decomposition for '%s'. "
                    "Promoted '%s' (was %s) to ROOT anchor at assembly origin.",
                    node.label, promoted.label, orig_socket.value,
                )
                manifest.record_event(
                    "decomposition_anchor_fallback",
                    node_id=node.node_id,
                    details={
                        "parent": node.label,
                        "promoted_child": promoted.label,
                        "original_socket": orig_socket.value,
                        "reason": "ANCHOR_TO_ASSEMBLY_ORIGIN",
                    },
                )
        elif len(root_children) > 1:
            # Multiple ROOT variant: keep first, demote subsequent ones
            for extra_root in root_children[1:]:
                demoted_socket = SocketType.BOTTOM_CENTER
                extra_root.socket_type = demoted_socket
                logger.warning(
                    "DUPLICATE_ROOT: multiple ROOT children in decomposition for '%s'. "
                    "Demoted '%s' from ROOT to %s.",
                    node.label, extra_root.label, demoted_socket.value,
                )
                manifest.record_event(
                    "decomposition_duplicate_root_demoted",
                    node_id=node.node_id,
                    details={
                        "parent": node.label,
                        "demoted_child": extra_root.label,
                        "demoted_socket": demoted_socket.value,
                    },
                )

        can_add, limit_reason = tree.can_add_children(node.node_id, len(result.children))
        if not can_add:
            error = (
                f"DECOMPOSITION_CAPACITY_EXCEEDED: cannot commit "
                f"{len(result.children)} children for '{node.label}': {limit_reason}"
            )
            manifest.record_event(
                "decomposition_rejected", node_id=node.node_id,
                details={"reason": error, "requested_child_count": len(result.children)},
            )
            manifest.transition(node.node_id, NodeState.FAILED, error=error)
            return

        node.expected_child_count = len(result.children)
        manifest.record_event(
            "decomposition_validated", node_id=node.node_id,
            details={"expected_child_count": node.expected_child_count},
        )
        
        # FIX: Auto-scope duplicate labels with parent assembly name to prevent global conflicts
        # This handles cases where the LLM generates the same child labels for different assemblies
        # (e.g., left_arm_assembly and right_arm_assembly both having "upper_arm")
        existing_labels = {n.label for n in manifest.nodes.values()}
        children_specs = []
        parent_path = str(getattr(node, "custom_props", {}).get("canonical_path") or node.label)
        for child_index, child_spec in enumerate(result.children, start=1):
            label = child_spec.label
            display_label = label
            canonical_path = f"{parent_path}/{display_label}[{child_index}]"
            # If label already exists in manifest, scope it with parent assembly name
            # EXCEPT do not auto-scope if it duplicates a root-level PART
            root_node = manifest.get_root()
            root_part_labels = {
                manifest.nodes[cid].label.lower()
                for cid in root_node.children_ids
                if cid in manifest.nodes and manifest.nodes[cid].kind == NodeKind.PART
            } if root_node else set()

            if label in existing_labels:
                if label.lower() in root_part_labels and child_spec.socket_type == SocketType.ROOT:
                    raise ValueError(
                        f"commit_decomposition: child '{label}' in assembly '{node.label}' "
                        f"duplicates root-level part '{label}'"
                    )
                # Keep the artist-facing label separately and make only the
                # machine/Blender identifier unique from its immediate parent
                # identity.  This mirrors DCC namespace/path practice instead
                # of repeatedly prepending display names.
                scoped_label = f"{label}__{node.node_id[-8:]}_{child_index:02d}"
                logger.warning(
                    f"Auto-scoping duplicate label: '{label}' → '{scoped_label}' "
                    f"(parent: {node.label}, existing_labels: {sorted(existing_labels)[:5]}...)"
                )
                label = scoped_label
                # Update the child_spec label
                child_spec = DecomposedChild(
                    label=label,
                    kind=child_spec.kind,
                    primitive=child_spec.primitive,
                    socket_type=child_spec.socket_type,
                    importance=child_spec.importance,
                    semantic_hints=child_spec.semantic_hints,
                    needs_decomposition=child_spec.needs_decomposition,
                    decomposition_reason=child_spec.decomposition_reason,
                )
            
            children_specs.append({
                "label": label,
                "kind": child_spec.kind,
                "importance": child_spec.importance,
                "attachment": AttachmentSpec(socket_type=child_spec.socket_type),
                "geometry": GeometrySpec(primitive=child_spec.primitive) if child_spec.primitive else None,
                "stage_outputs": {
                    "decomposition_hint": child_spec.semantic_hints,
                    "identity": {"display_label": display_label, "canonical_path": canonical_path},
                },
                "custom_props": {"display_label": display_label, "canonical_path": canonical_path},
                "_child_spec": child_spec,  # carried through for decompose bookkeeping
            })
            if child_spec.semantic_hints.get("allow_disconnected"):
                children_specs[-1]["attachment"].allow_disconnected = True

        # Atomic commit — if validation fails the manifest is untouched.
        try:
            created_nodes = manifest.commit_decomposition(node.node_id, children_specs)
        except ValueError as exc:
            logger.warning(
                f"commit_decomposition rejected for '{node.label}': {exc}"
            )
            manifest.record_event(
                "decomposition_commit_failed", node_id=node.node_id,
                details={"reason": str(exc), "expected_child_count": node.expected_child_count},
            )
            manifest.transition(node.node_id, NodeState.FAILED, error=str(exc))
            return

        if len(created_nodes) != node.expected_child_count:
            error = (
                f"DECOMPOSITION_COMMIT_INCOMPLETE: expected "
                f"{node.expected_child_count}, committed {len(created_nodes)}"
            )
            manifest.record_event("decomposition_commit_failed", node_id=node.node_id,
                                  details={"reason": error})
            manifest.transition(node.node_id, NodeState.FAILED, error=error)
            return

        # Build children_to_decompose from the committed nodes.
        children_to_decompose: List[Tuple[ManifestNode, Optional[List[Dict[str, Any]]]]] = []
        for child_node, spec in zip(created_nodes, children_specs):
            child_spec = spec["_child_spec"]
            stats["nodes_created"] = stats.get("nodes_created", 0) + 1

            attach_to = child_spec.semantic_hints.get("attach_to")
            if attach_to:
                target = manifest.get_node_by_label(attach_to)
                if target is None:
                    error = (
                        f"UNKNOWN_ATTACHMENT_TARGET: '{child_spec.label}' "
                        f"references '{attach_to}'"
                    )
                    manifest.record_event(
                        "attachment_reference_rejected", node_id=child_node.node_id,
                        details={"reason": error},
                    )
                    manifest.transition(child_node.node_id, NodeState.FAILED, error=error)
                else:
                    child_node.attachment.reference_node_id = target.node_id
                    child_node.attachment.reference_anchor = child_spec.semantic_hints.get("attach_anchor")
                    manifest.record_event(
                        "attachment_reference_resolved", node_id=child_node.node_id,
                        details={"reference_node_id": target.node_id,
                                 "reference_anchor": child_node.attachment.reference_anchor},
                    )

            nested_children = child_spec.semantic_hints.get("_nested_children")

            logger.debug(
                f"Child {child_spec.label}: kind={child_spec.kind.value}, "
                f"nested_children={bool(nested_children)}"
            )

            if child_spec.kind == NodeKind.ASSEMBLY:
                if nested_children:
                    logger.info(
                        f"Assembly {child_spec.label} has "
                        f"{len(nested_children)} pre-parsed children"
                    )
                    children_to_decompose.append((child_node, nested_children))
                else:
                    logger.info(
                        f"Assembly {child_spec.label} needs LLM decomposition "
                        f"(no nested children)"
                    )
                    children_to_decompose.append((child_node, None))
            elif child_spec.needs_decomposition:
                children_to_decompose.append((child_node, nested_children))

        # Transition node to READY (decomposition complete)
        manifest.transition(node.node_id, NodeState.READY)
        
        # Recursively decompose children that need it
        for child_node, nested in children_to_decompose:
            logger.info(f"Recursively decomposing {child_node.label} (depth={child_node.hierarchy_depth}, nested={bool(nested)})")
            await self._decompose_node(
                node=child_node,
                manifest=manifest,
                tree=tree,
                model_manager=model_manager,
                task_id=task_id,
                model_id=model_id,
                stats=stats,
                pre_parsed_children=nested,
            )
    
    def _parse_pre_parsed_children(
        self,
        node: ManifestNode,
        children_data: List[Dict[str, Any]],
    ) -> DecompositionResult:
        """Parse pre-parsed children (from nested LLM response)."""
        children: List[DecomposedChild] = []
        labels_seen: Set[str] = set()
        has_root = False
        warnings: List[ValidationWarning] = []
        
        # Flatten in case there's more nesting
        flat_children = self._flatten_children(children_data)
        
        for i, child_data in enumerate(flat_children):
            if len(children) >= self.limits.max_children:
                return DecompositionResult(
                    node_id=node.node_id,
                    decision=DecompositionDecision.SKIP,
                    error=(f"DECOMPOSITION_CHILD_LIMIT: response has more than "
                           f"{self.limits.max_children} children for '{node.label}'"),
                )
            
            try:
                child, warn = self._parse_child(child_data, i, labels_seen, node.hierarchy_depth, has_root)
                children.append(child)
                labels_seen.add(child.label)
                if warn:
                    warnings.append(warn)
                if child.socket_type == SocketType.ROOT:
                    has_root = True
            except ValueError as e:
                err = str(e)
                if "DUPLICATE_NODE_ID" in err:
                    return DecompositionResult(
                        node_id=node.node_id,
                        decision=DecompositionDecision.SKIP,
                        error=err,
                    )
                logger.warning(f"Skipping invalid pre-parsed child {i}: {e}")
                continue
        
        if not children:
            return DecompositionResult(
                node_id=node.node_id,
                decision=DecompositionDecision.SKIP,
                error="No valid children in pre-parsed data",
            )
        
        return DecompositionResult(
            node_id=node.node_id,
            decision=DecompositionDecision.DECOMPOSE,
            children=children,
            warnings=warnings,
        )
    
    async def _call_llm_decompose(
        self,
        node: ManifestNode,
        manifest: BuildManifest,
        tree: ContainmentTree,
        model_manager: Any,
        task_id: str,
        model_id: Optional[str],
    ) -> DecompositionResult:
        """Call LLM to decompose a node into children."""
        self.llm_call_count += 1
        manifest.record_llm_call()
        
        mid = model_id or model_manager.get_model_for_workflow("ENDPOINT")
        
        # Build context
        if node.kind == NodeKind.MODEL:
            # Root decomposition — reflect structural cues from the prompt back
            # so the LLM doesn't have to re-infer them from a generic instruction.
            import re as _re
            p = manifest.prompt

            # Extract explicit counts ("four blades", "3 rings", "2 rails", etc.)
            count_hints = _re.findall(
                r'(\b(?:one|two|three|four|five|six|seven|eight|\d+)\b[^,.;]{0,40})',
                p, _re.IGNORECASE
            )
            count_note = (
                f"Explicit counts mentioned: {'; '.join(count_hints[:6])}.\n"
                if count_hints else ""
            )

            # Detect vertical stacking signal words
            stacking_words = [w for w in
                ["base", "stand", "pole", "rod", "stem", "column", "neck",
                 "top", "head", "housing", "mount", "tower", "pedestal"]
                if w in p.lower()]
            stacking_note = (
                f"Stacking cues detected ({', '.join(stacking_words[:6])}) — "
                f"use nested assemblies, one level per vertical transition.\n"
                if len(stacking_words) >= 2 else ""
            )

            # Detect enclosure / cage signal
            enclosure_note = (
                "An enclosure/cage is mentioned — model it as a child assembly "
                "with torus rings as parts.\n"
                if any(w in p.lower() for w in ["cage", "enclosure", "guard", "grille", "cover"])
                else ""
            )
            reference = manifest.stats.get("reference_brief", {})
            reference_note = ""
            if reference:
                reference_note = (
                    "Visual reference contract (honor it unless the user conflicts):\n"
                    f"- Shape: {reference.get('shape_rules', [])}\n"
                    f"- Proportions: {reference.get('proportion_rules', [])}\n"
                    f"- Material roles: {reference.get('material_roles', {})}\n"
                    f"- Contextual component profiles: {reference.get('component_profiles', {})}\n"
                )

            user_prompt = (
                f"ROOT PASS — decompose this object into its immediate, high-level structural hierarchy:\n"
                f"{p}\n\n"
                f"{count_note}"
                f"{stacking_note}"
                f"{enclosure_note}"
                f"{reference_note}"
                f"RULES:\n"
                f"- This is a staged plan. Emit only the ROOT object's immediate children (normally 1–8 structural assemblies/parts).\n"
                f"- Do NOT put a children array inside any child in this ROOT response; each complex assembly is decomposed in its own later call.\n"
                f"- Mark every child assembly is_complex: true so it will receive that later decomposition call.\n"
                f"- Preserve named systems and count intent, but do not expand a repeated system into every physical instance at this pass.\n"
                f"- Set is_simple: false.\n"
                f"- Use the exact JSON contract from the system prompt: top-level is_simple and children; each child needs label, kind, socket_type, material_hint, and style_hint.\n"
                f"- Do not use alternate keys such as name or assemblies."
            )
            system_prompt = DECOMPOSITION_SYSTEM_PROMPT
        else:
            # Assembly decomposition - provide context
            parent_context = self._build_parent_context(node, manifest)
            remaining = self.limits.max_total_nodes - len(manifest.nodes)
            
            user_prompt = ASSEMBLY_DECOMPOSITION_PROMPT.format(
                parent_context=parent_context,
                assembly_label=node.label,
                depth=node.hierarchy_depth,
                max_depth=self.limits.max_depth,
                remaining_nodes=remaining,
                max_children=self.limits.max_children,
            )
            system_prompt = DECOMPOSITION_SYSTEM_PROMPT
        
        try:
            response = await model_manager.generate_async(
                model_id=mid,
                task_id=f"decompose_{task_id}_{node.label}",
                lease_id="internal",
                lease_generation=0,
                system_prompt=system_prompt,
                prompt=user_prompt,
                temperature=0.4,
            )

            result = self._parse_decomposition_response(
                response=response,
                node=node,
                manifest=manifest,
            )
            manifest.append_llm_log(
                node_label=node.label,
                prompt=user_prompt,
                response=response,
                warnings=result.warnings,
            )
            # Semantic retry: a surprisingly common model failure is to emit
            # the requested assembly itself as its sole child.  That is not a
            # decomposition; auto-renaming it creates an infinite wrapper
            # chain.  Ask once for the physical children at this level.
            def canonical_assembly_label(value: str) -> str:
                value = re.sub(r"(?:[_-]?\d+)+$", "", value.lower())
                return re.sub(r"(?:[_-]?assembly)+$", "", value).strip("_-")

            if (
                result.success and result.children
                and all(child.kind == NodeKind.ASSEMBLY and canonical_assembly_label(child.label) == canonical_assembly_label(node.label)
                        for child in result.children)
            ):
                wrapper_retry_prompt = (
                    user_prompt
                    + f"\n\nCRITICAL CORRECTION: Do not emit '{node.label}' (or any spelling of it) as a child. "
                    "It is already the current assembly. Return its direct physical children only: "
                    "one ROOT physical part plus any attached part/assembly children."
                )
                response_retry = await model_manager.generate_async(
                    model_id=mid, task_id=f"decompose_{task_id}_{node.label}_wrapper_retry",
                    lease_id="internal", lease_generation=0, system_prompt=system_prompt,
                    prompt=wrapper_retry_prompt, temperature=0.0,
                )
                self.llm_call_count += 1
                manifest.record_llm_call()
                wrapper_result = self._parse_decomposition_response(response_retry, node, manifest)
                manifest.append_llm_log(
                    node_label=f"{node.label}:wrapper_retry", prompt=wrapper_retry_prompt,
                    response=response_retry, warnings=wrapper_result.warnings,
                )
                if wrapper_result.success:
                    result = wrapper_result

            # Structured retry for ROOT invariant violation:
            # If an assembly decomposition has no ROOT part AND the children are not
            # an assembly-frame relative set (like corner legs or radial parts),
            # re-prompt with the exact rule before any fallback.
            if result.success and result.children:
                root_count = sum(1 for c in result.children if c.socket_type == SocketType.ROOT)
                _FRAME_RELATIVE_SOCKETS = {
                    SocketType.CORNER,
                    SocketType.RADIAL,
                    SocketType.ARRAY_MEMBER,
                    SocketType.RADIAL_BRIDGE,
                }
                frame_anchored = all(c.socket_type in _FRAME_RELATIVE_SOCKETS for c in result.children)
                if (root_count == 0 and not frame_anchored) or (root_count > 1):
                    rule_retry_prompt = (
                        user_prompt
                        + f"\n\nRULE VIOLATION: An assembly must have exactly one ROOT component that serves as the reference frame/anchor, OR use frame-relative sockets (CORNER, RADIAL, ARRAY_MEMBER) for all children. "
                        f"Your response had {root_count} ROOT parts. Return the children again with exactly one physical part designated with socket_type: 'ROOT'."
                    )
                    response_retry = await model_manager.generate_async(
                        model_id=mid, task_id=f"decompose_{task_id}_{node.label}_root_rule_retry",
                        lease_id="internal", lease_generation=0, system_prompt=system_prompt,
                        prompt=rule_retry_prompt, temperature=0.0,
                    )
                    self.llm_call_count += 1
                    manifest.record_llm_call()
                    rule_result = self._parse_decomposition_response(response_retry, node, manifest)
                    manifest.append_llm_log(
                        node_label=f"{node.label}:root_rule_retry", prompt=rule_retry_prompt,
                        response=response_retry, warnings=rule_result.warnings,
                    )
                    if rule_result.success:
                        result = rule_result

            # Structured retry for duplicate root part:
            # If an assembly emits a child whose canonical label matches an existing root part,
            # (e.g. central_chassis declared again inside rotor_guard_assembly), prompt to fix it.
            root_node = manifest.get_root()
            root_part_labels = {
                canonical_assembly_label(manifest.nodes[cid].label)
                for cid in root_node.children_ids
                if cid in manifest.nodes and manifest.nodes[cid].kind == NodeKind.PART
            } if root_node else set()

            if result.success and result.children and root_part_labels:
                conflicting = [
                    c.label for c in result.children
                    if canonical_assembly_label(c.label) in root_part_labels
                ]
                if conflicting:
                    dup_retry_prompt = (
                        user_prompt
                        + f"\n\nRULE VIOLATION: Do not re-emit root-level parts ({', '.join(conflicting)}) inside '{node.label}'. "
                        f"Those parts already exist at the model root level. Provide only the parts that belong to '{node.label}', "
                        f"with one of them designated as socket_type: 'ROOT'."
                    )
                    response_retry = await model_manager.generate_async(
                        model_id=mid, task_id=f"decompose_{task_id}_{node.label}_dup_root_retry",
                        lease_id="internal", lease_generation=0, system_prompt=system_prompt,
                        prompt=dup_retry_prompt, temperature=0.0,
                    )
                    self.llm_call_count += 1
                    manifest.record_llm_call()
                    dup_result = self._parse_decomposition_response(response_retry, node, manifest)
                    manifest.append_llm_log(
                        node_label=f"{node.label}:dup_root_retry", prompt=dup_retry_prompt,
                        response=response_retry, warnings=dup_result.warnings,
                    )
                    if dup_result.success:
                        result = dup_result

            # A large nested hierarchy is occasionally semantically complete
            # but contains one malformed string/token.  Do not turn that
            # transport-format error into a root build failure: retry once
            # with the same task context and a JSON-only correction request.
            # We intentionally do not attempt a lossy regex "repair" of a
            # scene specification, because that could change geometry intent.
            if result.error and result.error.startswith("Failed to parse JSON"):
                retry_prompt = (
                    user_prompt
                    + "\n\nYour previous response could not be parsed as JSON. "
                    "Return the complete hierarchy again as ONE strictly valid JSON object. "
                    "Use double-quoted keys and strings; do not include markdown or prose."
                )
                response_retry = await model_manager.generate_async(
                    model_id=mid,
                    task_id=f"decompose_{task_id}_{node.label}_json_retry",
                    lease_id="internal",
                    lease_generation=0,
                    system_prompt=(
                        DECOMPOSITION_SYSTEM_PROMPT
                        + "\n\nRETRY CONTRACT: Return only one syntactically valid JSON object "
                        "using exactly the is_simple/children schema above. Never use name/assemblies "
                        "or any alternate schema. No markdown, comments, or prose."
                    ),
                    prompt=retry_prompt,
                    temperature=0.0,
                )
                self.llm_call_count += 1
                manifest.record_llm_call()
                retry_result = self._parse_decomposition_response(
                    response=response_retry,
                    node=node,
                    manifest=manifest,
                )
                manifest.append_llm_log(
                    node_label=f"{node.label}:json_retry",
                    prompt=retry_prompt,
                    response=response_retry,
                    warnings=retry_result.warnings,
                )
                if retry_result.success:
                    return retry_result
            return result
            
        except Exception as e:
            logger.error(f"LLM call failed for {node.label}: {e}")
            return DecompositionResult(
                node_id=node.node_id,
                decision=DecompositionDecision.SKIP,
                error=str(e),
            )
    
    def _build_parent_context(self, node: ManifestNode, manifest: BuildManifest) -> str:
        """Build context string describing the parent hierarchy."""
        ancestors = manifest.get_ancestors(node.node_id)
        path_labels = []
        if ancestors:
            for aid in reversed(ancestors):
                ancestor = manifest.nodes.get(aid)
                if ancestor:
                    path_labels.append(ancestor.label)
        path_labels.append(node.label)
        
        ctx = f"{manifest.prompt} > {' > '.join(path_labels)}"
        existing_parts = [
            n.label
            for n in manifest.nodes.values()
            if n.kind == NodeKind.PART and n.node_id != node.node_id
        ]
        if existing_parts:
            ctx += f"\nNote: The following parts are ALREADY modeled in the assembly ({', '.join(existing_parts[:8])}). DO NOT re-emit or duplicate these inside {node.label}."
        return ctx
    
    def _parse_decomposition_response(
        self,
        response: str,
        node: ManifestNode,
        manifest: BuildManifest,
    ) -> DecompositionResult:
        """Parse LLM response into DecompositionResult."""
        # Extract JSON
        data = self._extract_json(response)
        if not data:
            return DecompositionResult(
                node_id=node.node_id,
                decision=DecompositionDecision.SKIP,
                error=f"Failed to parse JSON from response: {response[:200]}",
                llm_response=response,
            )
        
        # Check if simple
        is_simple = data.get("is_simple", False)
        
        # Parse children
        children_data = data.get("children", [])
        if not children_data:
            return DecompositionResult(
                node_id=node.node_id,
                decision=DecompositionDecision.SKIP,
                error="No children in response",
                llm_response=response,
            )
        
        # Unpack single-child self-wrapper: if the response wrapped its children in a
        # redundant same-named assembly container (e.g. rotor_guard_assembly -> rotor_guard_assembly -> [guards]),
        # unwrap it immediately.
        def canonical_label(value: str) -> str:
            value = re.sub(r"(?:[_-]?\d+)+$", "", str(value).lower())
            return re.sub(r"(?:[_-]?assembly)+$", "", value).strip("_-")

        if len(children_data) == 1 and isinstance(children_data[0], dict) and children_data[0].get("children"):
            wrapper_label = str(children_data[0].get("label", ""))
            if canonical_label(wrapper_label) == canonical_label(node.label):
                logger.info(
                    f"Unwrapping redundant same-named assembly container '{wrapper_label}' for '{node.label}'"
                )
                children_data = children_data[0]["children"]

        # Flatten nested children - recursively extract all children
        flat_children = self._flatten_children(children_data)
        
        children: List[DecomposedChild] = []
        labels_seen: Set[str] = set()
        has_root = False
        warnings: List[ValidationWarning] = []
        
        for i, child_data in enumerate(flat_children):
            if len(children) >= MAX_CHILDREN_PER_DECOMPOSITION:
                # Reject if the truncated child is ROOT — losing the ROOT child
                # makes the assembly unbuildable (no geometry anchor).
                remaining_socket = child_data.get("socket_type", "").upper()
                if remaining_socket == "ROOT" or (not has_root and i == 0):
                    return DecompositionResult(
                        node_id=node.node_id,
                        decision=DecompositionDecision.SKIP,
                        error=(
                            f"Budget limit ({MAX_CHILDREN_PER_DECOMPOSITION}) reached before "
                            f"ROOT child '{child_data.get('label', '?')}' was added — "
                            f"assembly would be unbuildable. Retry with fewer children."
                        ),
                        llm_response=response,
                    )
                logger.warning(f"Truncating children at {MAX_CHILDREN_PER_DECOMPOSITION}")
                break
            
            try:
                child, warn = self._parse_child(child_data, i, labels_seen, node.hierarchy_depth, has_root)
                children.append(child)
                labels_seen.add(child.label)
                if warn:
                    warnings.append(warn)
                if child.socket_type == SocketType.ROOT:
                    has_root = True
            except ValueError as e:
                err = str(e)
                if "DUPLICATE_NODE_ID" in err:
                    return DecompositionResult(
                        node_id=node.node_id,
                        decision=DecompositionDecision.SKIP,
                        error=err,
                        llm_response=response,
                    )
                logger.warning(f"Skipping invalid child {i}: {e}")
                continue
        
        if not children:
            return DecompositionResult(
                node_id=node.node_id,
                decision=DecompositionDecision.SKIP,
                error="No valid children parsed",
                llm_response=response,
            )
        
        return DecompositionResult(
            node_id=node.node_id,
            decision=DecompositionDecision.DECOMPOSE,
            children=children,
            llm_response=response,
            warnings=warnings,
        )
    
    def _flatten_children(self, children_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Normalize a nested children list into a flat list with preserved hierarchy.

        Each output dict is a shallow copy of the input dict (no "children" key)
        with an added "_nested_children" key whose value is the *already-normalized*
        result of recursively calling this method on the original nested children.

        This means every level of the tree is represented identically:
            {"label": "stand_assembly", ..., "_nested_children": [
                {"label": "stand", ...},
                {"label": "head_assembly", ..., "_nested_children": [
                    {"label": "motor_housing", ...},
                ]},
            ]}

        Contract: pure normalization only — no manifest mutation, no validation,
        no budget enforcement, no enum decisions.
        """
        result = []

        for child in children_data:
            # Build a clean copy that never carries the raw "children" key forward.
            child_copy = {k: v for k, v in child.items() if k != "children"}

            raw_nested = child.get("children", [])
            if raw_nested:
                # Recurse so depth-N nesting is normalized the same way as depth-1.
                child_copy["is_complex"] = True
                child_copy["has_subcomponents"] = True
                child_copy["_nested_children"] = self._flatten_children(raw_nested)

            result.append(child_copy)

        return result
    
    def _parse_child(
        self,
        data: Dict[str, Any],
        index: int,
        labels_seen: Set[str],
        parent_depth: int,
        has_root_already: bool = False,
    ) -> DecomposedChild:
        """Parse a single child from LLM response."""
        # Label (required)
        label = data.get("label")
        if not label or not isinstance(label, str):
            raise ValueError(f"Child {index}: missing or invalid label")
        
        # Duplicate label is a hard error — silent rename hides model output problems
        # and makes later semantic references (connects_to, relative_to) ambiguous.
        if label in labels_seen:
            raise ValueError(
                f"DUPLICATE_NODE_ID: label '{label}' appears more than once in "
                f"this decomposition response (occurrence at index {index}). "
                f"Retry decomposition — do not auto-rename."
            )
        
        # Kind (required)
        kind_str = data.get("kind", "part").lower()
        if kind_str == "assembly":
            kind = NodeKind.ASSEMBLY
        elif kind_str == "part":
            kind = NodeKind.PART
        else:
            raise ValueError(f"UNSUPPORTED_NODE_KIND: '{kind_str}' for '{label}'")
        
        # Primitive (for parts) - ALWAYS set for PART nodes
        primitive = None
        primitive_warning: Optional[ValidationWarning] = None
        if kind == NodeKind.PART:
            prim_str = data.get("primitive", "").lower()
            if not prim_str:
                raise ValueError(f"MISSING_PRIMITIVE: part '{label}' must declare a primitive")
            try:
                primitive = PrimitiveType(prim_str)
            except ValueError:
                raise ValueError(
                    f"UNSUPPORTED_PRIMITIVE: '{prim_str}' for '{label}'; "
                    "the decomposition must choose an executable capability"
                )
        
        # Socket type - infer from label and enforce single ROOT
        socket_str = data.get("socket_type", "").upper()
        socket_type, socket_warning = self._infer_socket_type(label, socket_str, index, has_root_already)
        if socket_warning:
            logger.warning(
                "ValidationWarning: node='%s' field='socket_type' "
                "requested='%s' coerced_to='%s' reason='%s'",
                label, socket_warning.requested, socket_warning.coerced_to, socket_warning.reason,
            )
        logger.debug(f"Socket for {label}: requested={socket_str}, inferred={socket_type.value}, has_root={has_root_already}")
        
        # Importance
        imp_str = data.get("importance", "required").lower()
        if imp_str == "optional":
            importance = NodeImportance.OPTIONAL
        elif imp_str == "decorative":
            importance = NodeImportance.DECORATIVE
        else:
            importance = NodeImportance.REQUIRED
        
        # Semantic hints
        semantic_hints = {
            "is_complex": data.get("is_complex", False),
            "has_subcomponents": data.get("has_subcomponents", False),
            "estimated_parts": data.get("estimated_parts", 1),
            "is_simple": data.get("is_simple", kind == NodeKind.PART),
            "material_hint": data.get("material_hint", ""),
            "style_hint": data.get("style_hint", ""),
            # Connector socket fields (closed vocabulary, no LLM-computed numbers)
            "connects_to": data.get("connects_to"),
            "position_fraction": data.get("position_fraction"),
            "relative_to": data.get("relative_to"),
            "direction": data.get("direction"),
            "gap": data.get("gap"),
            "radial_count": data.get("radial_count"),
            "radial_index": data.get("radial_index"),
            "attach_to": data.get("attach_to"),
            "attach_anchor": data.get("attach_anchor"),
            "length_axis": data.get("length_axis"),
            "allow_disconnected": bool(
                data.get("allow_disconnected", False)
                or "suspend" in label.lower()
                or "suspend" in json.dumps(data).lower()
                or "clearance" in json.dumps(data).lower()
            ),
            "repeat_key": data.get("repeat_key"),
            "structural_role": data.get("structural_role"),
            "endpoint_intent": data.get("endpoint_intent"),
        }
        
        # Preserve nested children for recursive decomposition
        if "_nested_children" in data:
            semantic_hints["_nested_children"] = data["_nested_children"]
        
        # Evaluate if needs decomposition
        needs_decomp, reason = self.stop_evaluator.evaluate_child_complexity(
            DecomposedChild(
                label=label,
                kind=kind,
                primitive=primitive,
                socket_type=socket_type,
                importance=importance,
                semantic_hints=semantic_hints,
            ),
            parent_depth,
        )
        
        return DecomposedChild(
            label=label,
            kind=kind,
            primitive=primitive,
            socket_type=socket_type,
            importance=importance,
            semantic_hints=semantic_hints,
            needs_decomposition=needs_decomp,
            decomposition_reason=reason,
        ), primitive_warning or socket_warning
    
    def _infer_socket_type(
        self,
        label: str,
        requested: str,
        index: int,
        has_root_already: bool,
    ) -> Tuple[SocketType, Optional[ValidationWarning]]:
        """Infer socket type from label, enforcing single ROOT per assembly.
        
        Returns (socket_type, warning) where warning is non-None when the
        requested value was coerced (e.g. TOP_CENTER -> ROOT for first child).
        """
        label_lower = label.lower()
        
        # 1. If caller/LLM explicitly supplied a socket, validate and use it
        if requested:
            try:
                parsed = SocketType(requested.upper())
                if parsed == SocketType.ROOT and has_root_already:
                    # Demote duplicate root
                    if "leg" in label_lower or "foot" in label_lower:
                        demoted = SocketType.CORNER
                    elif "top" in label_lower:
                        demoted = SocketType.TOP_CENTER
                    elif "bottom" in label_lower or "base" in label_lower:
                        demoted = SocketType.BOTTOM_CENTER
                    elif "left" in label_lower:
                        demoted = SocketType.LEFT_CENTER
                    elif "right" in label_lower:
                        demoted = SocketType.RIGHT_CENTER
                    elif "front" in label_lower:
                        demoted = SocketType.FRONT_CENTER
                    elif "back" in label_lower or "rear" in label_lower:
                        demoted = SocketType.BACK_CENTER
                    else:
                        demoted = SocketType.BOTTOM_CENTER
                    return demoted, ValidationWarning(
                        node_label=label,
                        field="socket_type",
                        requested="ROOT",
                        coerced_to=demoted.value,
                        reason="DUPLICATE_ROOT: assembly already has a ROOT child",
                    )
                return parsed, None
            except ValueError:
                pass

        # 2. Only infer from label pattern when requested socket is missing
        corner_patterns = [
            ("front_left", SocketType.CORNER),
            ("front_right", SocketType.CORNER),
            ("back_left", SocketType.CORNER),
            ("back_right", SocketType.CORNER),
            ("rear_left", SocketType.CORNER),
            ("rear_right", SocketType.CORNER),
            ("fl_", SocketType.CORNER),
            ("fr_", SocketType.CORNER),
            ("bl_", SocketType.CORNER),
            ("br_", SocketType.CORNER),
        ]
        for pattern, socket in corner_patterns:
            if pattern in label_lower:
                return socket, None

        # Default: first child is ROOT when no ROOT exists yet and not corner-pattern
        if index == 0 and not has_root_already:
            return SocketType.ROOT, None

        return SocketType.TOP_CENTER, None
    
    def _extract_json(self, text: str) -> Optional[Dict[str, Any]]:
        """Extract JSON from LLM response."""
        # Try direct parse
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError:
            pass

        # Some model backends end a response exactly at the token boundary.  A
        # complete scene tree can therefore be missing only its final `}` or
        # `]`.  Recover *only* that mechanically provable case: the response
        # must end outside a string and all outstanding delimiters must be
        # closable in LIFO order.  We deliberately do not repair commas,
        # quotes, field values, or arbitrary malformed JSON because those can
        # change design intent.
        completed = self._complete_trailing_json_delimiters(text.strip())
        if completed:
            try:
                obj = json.loads(completed)
                if isinstance(obj, dict):
                    logger.info("Recovered JSON response with trailing structural delimiters")
                    return obj
            except json.JSONDecodeError:
                pass
        
        # Try markdown code block
        m = re.search(r'```(?:json)?\s*(\{[\s\S]*?\})\s*```', text)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass
        
        # Find the first '{' and use raw_decode to consume exactly one JSON object,
        # stopping at the matching '}' rather than greedily taking the last '}'.
        start = text.find('{')
        if start != -1:
            try:
                obj, _ = json.JSONDecoder().raw_decode(text, start)
                if isinstance(obj, dict):
                    return obj
            except json.JSONDecodeError:
                pass
        
        return None

    @staticmethod
    def _complete_trailing_json_delimiters(text: str) -> Optional[str]:
        """Return a safely closed JSON object when only final delimiters are absent."""
        if not text.startswith("{"):
            return None

        stack: List[str] = []
        in_string = False
        escaped = False
        pairs = {"{": "}", "[": "]"}

        for char in text:
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char in pairs:
                stack.append(pairs[char])
            elif char in ("}", "]"):
                if not stack or char != stack[-1]:
                    return None
                stack.pop()

        if in_string or not stack:
            return None
        return text + "".join(reversed(stack))


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------

async def decompose_manifest(
    manifest: BuildManifest,
    model_manager: Any,
    task_id: str,
    model_id: Optional[str] = None,
    limits: Optional[HierarchyLimits] = None,
) -> Dict[str, Any]:
    """Convenience function to decompose a manifest.
    
    Returns statistics dict.
    """
    decomposer = RecursiveDecomposer(limits=limits)
    return await decomposer.decompose(
        manifest=manifest,
        model_manager=model_manager,
        task_id=task_id,
        model_id=model_id,
    )
