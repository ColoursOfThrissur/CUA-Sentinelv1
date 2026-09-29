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
    
    @property
    def success(self) -> bool:
        return self.error is None and self.decision != DecompositionDecision.SKIP


# ---------------------------------------------------------------------------
# Decomposition Error
# ---------------------------------------------------------------------------

class DecompositionError(Exception):
    """Raised when decomposition fails."""
    pass


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
        """
        # A. Already has children - BUT if we have pre-parsed children, we should still process them
        # This check is now handled by the caller passing pre_parsed_children
        if node.children_ids:
            return False, "Already has children"
        
        # B. Not a decomposable kind
        if node.kind not in DECOMPOSABLE_KINDS:
            return False, f"Kind {node.kind.value} is not decomposable"
        
        # C. At depth limit
        if node.hierarchy_depth >= self.limits.max_depth:
            return False, f"At depth limit ({self.limits.max_depth})"
        
        # D. Would exceed total nodes
        remaining_capacity = self.limits.max_total_nodes - len(manifest.nodes)
        if remaining_capacity < 2:
            return False, "Near total nodes limit"
        
        # E. Terminal primitive (for PART nodes that somehow got here)
        if node.geometry and node.geometry.primitive in TERMINAL_PRIMITIVES:
            return False, f"Terminal primitive ({node.geometry.primitive.value})"
        
        # F. Check stage outputs for complexity hints
        # IMPORTANT: Don't stop decomposition if we have pre-parsed children
        # The "is_simple" flag from LLM is about whether the object ITSELF is simple,
        # not whether it has children that need to be added
        if "decomposition_hint" in node.stage_outputs:
            hint = node.stage_outputs["decomposition_hint"]
            # Only stop if marked simple AND no nested children
            if hint.get("is_simple", False) and not hint.get("_nested_children"):
                return False, "Marked as simple by LLM"
        
        # G. Instance nodes are never decomposed (use definition)
        if node.kind == NodeKind.INSTANCE:
            return False, "Instance nodes use definition's structure"
        
        # Default: yes, decompose
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
- "primitive": For "part" kind only - one of: "box", "cylinder", "cone", "sphere", "hemisphere", "torus", "u_shape"
- "socket_type": How this attaches to parent (see SOCKET VOCABULARY below)
- "importance": "required", "optional", or "decorative"
- "is_complex": Boolean - true if this assembly needs further decomposition
- "has_subcomponents": Boolean - true if this has parts that stack on it
- "estimated_parts": Number - usually 1 for parts
- "material_hint": Material description (see MATERIAL VOCABULARY below)
- "style_hint": Surface style (see STYLE VOCABULARY below)

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

CRITICAL RULES:
1. KEEP IT SIMPLE - a table is just: tabletop (box) + 4 legs (cylinders). That's it.
2. NO decorative sub-parts like "edge bands", "braces", "connectors", "plates" unless explicitly requested
3. Use "part" kind for everything that can be a single primitive
4. Use "assembly" for things that have OTHER PARTS STACKED ON THEM
5. NEVER invent numeric positions or distances - use socket types with closed vocabulary fields
6. ALWAYS include material_hint and style_hint for EVERY part

STACKED OBJECTS (CRITICAL):
For objects where parts stack vertically (lamp, fan, trophy, etc.), use ASSEMBLIES:
- The BOTTOM part is the ROOT of an assembly
- Parts that sit ON TOP of it are children of that assembly
- This creates proper parent-child stacking

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

Example for "desk fan with base, stand, motor housing, fan blades":
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
      "estimated_parts": 4,
      "children": [
        {"label": "base", "kind": "part", "primitive": "cylinder", "socket_type": "ROOT", "importance": "required", "material_hint": "black plastic", "style_hint": "smooth"},
        {
          "label": "stand_assembly",
          "kind": "assembly",
          "socket_type": "TOP_CENTER",
          "importance": "required",
          "is_complex": true,
          "has_subcomponents": true,
          "children": [
            {"label": "stand", "kind": "part", "primitive": "cylinder", "socket_type": "ROOT", "importance": "required", "material_hint": "chrome", "style_hint": "smooth"},
            {
              "label": "head_assembly",
              "kind": "assembly",
              "socket_type": "TOP_CENTER",
              "importance": "required",
              "is_complex": true,
              "children": [
                {"label": "motor_housing", "kind": "part", "primitive": "sphere", "socket_type": "ROOT", "importance": "required", "material_hint": "white plastic", "style_hint": "smooth"},
                {"label": "fan_blades", "kind": "part", "primitive": "torus", "socket_type": "FRONT_CENTER", "importance": "required", "material_hint": "white plastic", "style_hint": "smooth"}
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
- Flat circular things (fan blades, disc): "torus" or "cylinder" (flat)
- Round housings, balls: "sphere"
- Poles, stands, legs: "cylinder"
- Flat surfaces, boxes: "box"
- Pointed things: "cone"
- U-shaped bent tubes (padlock shackle, handle, hook, bail): "u_shape" — ONE single part, never split into legs
- Half-dome, bowl: "hemisphere"

Output ONLY valid JSON, no markdown, no explanation."""


ASSEMBLY_DECOMPOSITION_PROMPT = """You are decomposing an ASSEMBLY into its parts.

This assembly is part of a larger object. Break it down into the primitives and sub-assemblies it contains.

Context:
- Parent object: {parent_context}
- This assembly: {assembly_label}
- Current depth: {depth} (max: {max_depth})
- Remaining node budget: {remaining_nodes}

Your task: Decompose "{assembly_label}" into its components.

CRITICAL: 
- If depth is near max, prefer "part" over "assembly" to avoid hitting limits
- Keep total children under {max_children}
- Focus on STRUCTURAL components, not decorative details at deep levels

Output JSON with "children" array and "is_simple" boolean."""


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
            stats["decomposition_stopped_reasons"].append({
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
                stats["decomposition_stopped_reasons"].append({
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
        
        # Add children to manifest
        children_to_decompose: List[Tuple[ManifestNode, Optional[List[Dict[str, Any]]]]] = []
        
        for child_spec in result.children:
            # Check limits before adding
            can_add, limit_reason = tree.can_add_child(node.node_id)
            if not can_add:
                logger.warning(f"Cannot add child {child_spec.label}: {limit_reason}")
                break
            
            # Create child node
            child_node = manifest.add_child_node(
                parent_id=node.node_id,
                label=child_spec.label,
                kind=child_spec.kind,
                importance=child_spec.importance,
                attachment=AttachmentSpec(socket_type=child_spec.socket_type),
                geometry=GeometrySpec(primitive=child_spec.primitive) if child_spec.primitive else None,
            )
            
            # Store semantic hints for later stages
            child_node.stage_outputs["decomposition_hint"] = child_spec.semantic_hints
            
            stats["nodes_created"] = stats.get("nodes_created", 0) + 1
            
            # Check if child needs further decomposition
            # Get nested children if they were pre-parsed from LLM response
            nested_children = child_spec.semantic_hints.get("_nested_children")
            
            logger.debug(f"Child {child_spec.label}: kind={child_spec.kind.value}, nested_children={bool(nested_children)}")
            
            # Assemblies ALWAYS need decomposition if they don't have nested children
            # (they need at least one PART child to be buildable)
            if child_spec.kind == NodeKind.ASSEMBLY:
                if nested_children:
                    logger.info(f"Assembly {child_spec.label} has {len(nested_children)} pre-parsed children")
                    children_to_decompose.append((child_node, nested_children))
                else:
                    logger.info(f"Assembly {child_spec.label} needs LLM decomposition (no nested children)")
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
        
        # Flatten in case there's more nesting
        flat_children = self._flatten_children(children_data)
        
        for i, child_data in enumerate(flat_children):
            if len(children) >= MAX_CHILDREN_PER_DECOMPOSITION:
                break
            
            try:
                child = self._parse_child(child_data, i, labels_seen, node.hierarchy_depth, has_root)
                children.append(child)
                labels_seen.add(child.label)
                if child.socket_type == SocketType.ROOT:
                    has_root = True
            except ValueError as e:
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
            # Root decomposition - use original prompt
            user_prompt = f"Decompose this object: {manifest.prompt}"
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
                temperature=0.2,
            )
            
            return self._parse_decomposition_response(
                response=response,
                node=node,
                manifest=manifest,
            )
            
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
        if not ancestors:
            return manifest.prompt
        
        path_labels = []
        for aid in reversed(ancestors):
            ancestor = manifest.nodes.get(aid)
            if ancestor:
                path_labels.append(ancestor.label)
        path_labels.append(node.label)
        
        return f"{manifest.prompt} > {' > '.join(path_labels)}"
    
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
        
        children: List[DecomposedChild] = []
        labels_seen: Set[str] = set()
        has_root = False
        
        # Flatten nested children - recursively extract all children
        flat_children = self._flatten_children(children_data)
        
        for i, child_data in enumerate(flat_children):
            if len(children) >= MAX_CHILDREN_PER_DECOMPOSITION:
                logger.warning(f"Truncating children at {MAX_CHILDREN_PER_DECOMPOSITION}")
                break
            
            try:
                child = self._parse_child(child_data, i, labels_seen, node.hierarchy_depth, has_root)
                children.append(child)
                labels_seen.add(child.label)
                if child.socket_type == SocketType.ROOT:
                    has_root = True
            except ValueError as e:
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
        )
    
    def _flatten_children(self, children_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Flatten nested children arrays into a single list.
        
        The LLM may return nested structures like:
        {
          "children": [
            {"label": "base_assembly", "kind": "assembly", "children": [
              {"label": "base", "kind": "part"},
              {"label": "stand_assembly", "kind": "assembly", "children": [...]}
            ]}
          ]
        }
        
        We flatten this to process all nodes, but preserve the nesting info
        so the recursive decomposer can rebuild the hierarchy.
        """
        result = []
        
        for child in children_data:
            # Add this child (without its nested children)
            child_copy = {k: v for k, v in child.items() if k != "children"}
            
            # If it has nested children, mark it as needing decomposition
            nested = child.get("children", [])
            if nested:
                child_copy["is_complex"] = True
                child_copy["has_subcomponents"] = True
                child_copy["_nested_children"] = nested  # Store for later
            
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
        
        # Ensure unique
        if label in labels_seen:
            label = f"{label}_{index}"
        
        # Kind (required)
        kind_str = data.get("kind", "part").lower()
        if kind_str == "assembly":
            kind = NodeKind.ASSEMBLY
        elif kind_str == "part":
            kind = NodeKind.PART
        else:
            kind = NodeKind.PART  # Default to part
        
        # Primitive (for parts) - ALWAYS set for PART nodes
        primitive = None
        if kind == NodeKind.PART:
            prim_str = data.get("primitive", "").lower() or "box"
            try:
                primitive = PrimitiveType(prim_str)
            except ValueError:
                primitive = PrimitiveType.BOX  # Default to box for invalid/missing
        
        # Socket type - infer from label and enforce single ROOT
        socket_str = data.get("socket_type", "").upper()
        socket_type = self._infer_socket_type(label, socket_str, index, has_root_already)
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
        )
    
    def _infer_socket_type(
        self,
        label: str,
        requested: str,
        index: int,
        has_root_already: bool,
    ) -> SocketType:
        """Infer socket type from label, enforcing single ROOT per assembly."""
        label_lower = label.lower()
        
        # Pattern matching for corner positions (legs, feet, etc.)
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
        
        # Check if label implies a corner position
        for pattern, socket in corner_patterns:
            if pattern in label_lower:
                return socket
        
        # If LLM requested ROOT but we already have one, demote to appropriate socket
        if requested == "ROOT":
            if has_root_already:
                # Already have a ROOT - infer from label or default to BOTTOM_CENTER
                if "leg" in label_lower or "foot" in label_lower:
                    return SocketType.CORNER
                elif "top" in label_lower:
                    return SocketType.TOP_CENTER
                elif "bottom" in label_lower or "base" in label_lower:
                    return SocketType.BOTTOM_CENTER
                elif "left" in label_lower:
                    return SocketType.LEFT_CENTER
                elif "right" in label_lower:
                    return SocketType.RIGHT_CENTER
                elif "front" in label_lower:
                    return SocketType.FRONT_CENTER
                elif "back" in label_lower or "rear" in label_lower:
                    return SocketType.BACK_CENTER
                else:
                    return SocketType.BOTTOM_CENTER
            else:
                return SocketType.ROOT
        
        # Try to parse the requested socket type
        if requested:
            try:
                return SocketType(requested)
            except ValueError:
                pass
        
        # Default: first child is ROOT, others are TOP_CENTER
        if index == 0 and not has_root_already:
            return SocketType.ROOT
        return SocketType.TOP_CENTER
    
    def _extract_json(self, text: str) -> Optional[Dict[str, Any]]:
        """Extract JSON from LLM response."""
        # Try direct parse
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError:
            pass
        
        # Try markdown code block
        m = re.search(r'```(?:json)?\s*(\{[\s\S]*?\})\s*```', text)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass
        
        # Try finding raw JSON
        m = re.search(r'\{[\s\S]*\}', text)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
        
        return None


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
