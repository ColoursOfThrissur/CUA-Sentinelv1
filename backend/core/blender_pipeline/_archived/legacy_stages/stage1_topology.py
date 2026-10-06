"""Stage 1 — Part Topology.

Input: User prompt + Stage 0 output.
Output: Part tree with labels, primitive types, parent references, socket types.

CRITICAL: NO numeric field is permitted in this stage's output.
If any number appears, reject and re-ask.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, List, Optional

logger = logging.getLogger(__name__)


# Closed vocabulary for primitive_type (must match blender_ops.py tools)
VALID_PRIMITIVES = frozenset({
    "box",
    "cylinder",
    "cone",
    "sphere",
    "hemisphere",  # Created via sphere + bisect
    "torus",       # Ring/donut shape
})

# Closed vocabulary for socket_type
VALID_SOCKET_TYPES = frozenset({
    "ROOT",
    "TOP_CENTER",
    "BOTTOM_CENTER",
    "THROUGH_AXIS",
    "LEFT_END",
    "RIGHT_END",
    "TOP_END",
    "BOTTOM_END",
    "FRONT_FACE",
    "BACK_FACE",
    "LEFT_FACE",
    "RIGHT_FACE",
    "TOP_FACE",
    "BOTTOM_FACE",
    "ARRAY_MEMBER",
    "STRUT",
    "RADIAL",
    "RADIAL_BRIDGE",
    "BOOLEAN_CUT",  # Part is subtracted from parent (grooves, holes, cutouts)
})


@dataclass
class PartNode:
    """A single part in the topology tree (no dimensions yet)."""
    label: str
    primitive_type: str
    parent_label: Optional[str]  # None only for root
    socket_type: str


@dataclass
class PartTopology:
    """Stage 1 output: the part tree structure."""
    parts: List[PartNode] = field(default_factory=list)
    
    def get_root(self) -> Optional[PartNode]:
        """Get the root part (socket_type=ROOT)."""
        for p in self.parts:
            if p.socket_type == "ROOT":
                return p
        return None
    
    def get_children(self, parent_label: str) -> List[PartNode]:
        """Get all parts that have the given parent."""
        return [p for p in self.parts if p.parent_label == parent_label]
    
    def to_dict(self) -> dict:
        return {
            "parts": [
                {
                    "label": p.label,
                    "primitive_type": p.primitive_type,
                    "parent_label": p.parent_label,
                    "socket_type": p.socket_type,
                }
                for p in self.parts
            ]
        }


STAGE1_SYSTEM_PROMPT = """You are decomposing a 3D object into its component parts.

Your task is to output a JSON object with a "parts" array. Each part has:
- label: A unique snake_case name for the part (e.g., "base", "post", "arm_axis")
- primitive_type: One of: "box", "cylinder", "cone", "sphere" (ONLY these 4)
- parent_label: The label of the part this attaches to (null for the root part)
- socket_type: How this part attaches to its parent

CRITICAL RULES:
1. NO NUMBERS ANYWHERE. No dimensions, no offsets, no rotations. Pure structure only.
2. Exactly ONE part must have socket_type="ROOT" and parent_label=null.
3. Every other part must reference an existing part as parent_label.
4. No cycles allowed - the parts form a tree.
5. You can ONLY use these 6 primitives. Choose based on the GEOMETRY, not the name:
   - "box": Any shape with flat faces and straight edges (panels, blocks, wedges, slabs, beams, frames, screens, shelves, steps, ramps - rotation handles angles)
   - "cylinder": Any round shape with consistent cross-section (pillars, tubes, rods, discs, buttons, wheels, rings, pipes, poles, handles, knobs)
   - "cone": Any shape that tapers to a point or narrows (spikes, funnels, horns, tips, nozzles, pointed tops)
   - "sphere": Any fully rounded shape (balls, orbs, eyes, round knobs)
   - "hemisphere": Half-sphere / dome shape (radar dishes, domes, bowl shapes, rounded caps)
   - "torus": Ring/donut shape (rings, tires, donuts, circular handles, life preservers)

Valid socket_type values:
- ROOT: The base/ground part (only one allowed)
- TOP_CENTER: Stacks on top of parent, centered
- BOTTOM_CENTER: Hangs below parent, centered
- THROUGH_AXIS: Passes horizontally through parent (axles, crossbars)
- LEFT_END / RIGHT_END: At ends of a horizontal parent
- TOP_END / BOTTOM_END: At ends of a vertical parent
- FRONT_FACE / BACK_FACE / LEFT_FACE / RIGHT_FACE: On parent's faces
- TOP_FACE / BOTTOM_FACE: On parent's top/bottom faces
- ARRAY_MEMBER: Part of an array on a surface (buttons, knobs in a row)
- STRUT: Diagonal structural connector between two specific parts
- RADIAL: Items evenly spaced around ONE parent's circumference (decorative fins, spokes)
- RADIAL_BRIDGE: Diagonal connectors from parent to ANOTHER named part (support struts)
- BOOLEAN_CUT: Part is SUBTRACTED from parent (grooves, channels, holes, cutouts, slots, recesses)

**CRITICAL: BOOLEAN_CUT for subtractive features**
Use BOOLEAN_CUT when the prompt describes:
- Grooves, channels, or slots cut INTO a surface
- Holes or cutouts through a part
- Recessed areas or indentations
- Any feature described as "carved", "cut", "engraved", "inset", or "recessed"
- Decorative channels or blood grooves on blades
- Panel lines or seams that are recessed (not raised)

WRONG: "blade with a groove" → groove as FRONT_FACE (creates overlapping geometry)
RIGHT: "blade with a groove" → groove as BOOLEAN_CUT (subtracts from blade)

**CRITICAL: RADIAL vs RADIAL_BRIDGE distinction**
- Use RADIAL when items sit around ONE part only (e.g., "fins around the rocket body")
- Use RADIAL_BRIDGE when the prompt says parts "connect", "bridge", "support", or "span" 
  between TWO different named parts (e.g., "struts connecting the pillar to the dish")

WRONG: "struts connecting pillar to dish" → RADIAL (loses the dish connection entirely)
RIGHT: "struts connecting pillar to dish" → RADIAL_BRIDGE (struts will span from pillar to dish)

Example for "training dummy with horizontal arm":
```json
{
  "parts": [
    {"label": "post", "primitive_type": "cylinder", "parent_label": null, "socket_type": "ROOT"},
    {"label": "arm_axis", "primitive_type": "cylinder", "parent_label": "post", "socket_type": "THROUGH_AXIS"},
    {"label": "strike_shield", "primitive_type": "cylinder", "parent_label": "arm_axis", "socket_type": "LEFT_END"},
    {"label": "counterweight", "primitive_type": "sphere", "parent_label": "arm_axis", "socket_type": "RIGHT_END"}
  ]
}
```

Example for "sword blade with central groove":
```json
{
  "parts": [
    {"label": "blade", "primitive_type": "box", "parent_label": null, "socket_type": "ROOT"},
    {"label": "groove", "primitive_type": "box", "parent_label": "blade", "socket_type": "BOOLEAN_CUT"},
    {"label": "guard", "primitive_type": "box", "parent_label": "blade", "socket_type": "BOTTOM_CENTER"},
    {"label": "handle", "primitive_type": "cylinder", "parent_label": "guard", "socket_type": "BOTTOM_CENTER"}
  ]
}
```
Note: The groove uses BOOLEAN_CUT because it's carved INTO the blade, not sitting on top.

Example for "tower with struts connecting pillar to dish":
```json
{
  "parts": [
    {"label": "base", "primitive_type": "cylinder", "parent_label": null, "socket_type": "ROOT"},
    {"label": "pillar", "primitive_type": "cylinder", "parent_label": "base", "socket_type": "TOP_CENTER"},
    {"label": "dish", "primitive_type": "sphere", "parent_label": "pillar", "socket_type": "TOP_CENTER"},
    {"label": "strut_1", "primitive_type": "cylinder", "parent_label": "pillar", "socket_type": "RADIAL_BRIDGE"},
    {"label": "strut_2", "primitive_type": "cylinder", "parent_label": "pillar", "socket_type": "RADIAL_BRIDGE"},
    {"label": "strut_3", "primitive_type": "cylinder", "parent_label": "pillar", "socket_type": "RADIAL_BRIDGE"},
    {"label": "strut_4", "primitive_type": "cylinder", "parent_label": "pillar", "socket_type": "RADIAL_BRIDGE"}
  ]
}
```
Note: The struts use RADIAL_BRIDGE because they "connect pillar to dish" - Stage 3 will specify connects_to="dish".

Output ONLY valid JSON, no markdown, no explanation."""


class Stage1Topology:
    """Stage 1: Extract part topology from prompt."""
    
    @classmethod
    async def run(
        cls,
        prompt: str,
        stage0_output: dict,
        model_manager: Any,
        task_id: str,
        model_id: Optional[str] = None,
        rejection_feedback: Optional[str] = None,
    ) -> PartTopology:
        """Run Stage 1 to extract part topology.
        
        Args:
            prompt: Original user prompt
            stage0_output: Output from Stage 0 (for context)
            model_manager: Model manager for LLM calls
            task_id: Task ID for tracking
            model_id: Optional specific model to use
            rejection_feedback: Error from previous attempt (for retry)
            
        Returns:
            PartTopology with the part tree structure
            
        Raises:
            Stage1Error: If output is invalid
        """
        mid = model_id or model_manager.get_model_for_workflow("ENDPOINT")
        
        # Build context from Stage 0
        context = (
            f"Object category: {stage0_output.get('category', 'unknown')}\n"
            f"Rests on surface: {stage0_output.get('rests_on_surface', True)}\n"
            f"Scale: {stage0_output.get('scale_anchor_m', {}).get('overall_height_or_length', 'unknown')}m\n"
            f"\nUser request: {prompt}"
        )
        
        if rejection_feedback:
            context += f"\n\n[RETRY - Previous attempt failed: {rejection_feedback}. Fix the issue.]"
        
        response = await model_manager.generate_async(
            model_id=mid,
            task_id=f"stage1_{task_id}",
            lease_id="internal",
            lease_generation=0,
            system_prompt=STAGE1_SYSTEM_PROMPT,
            prompt=context,
            temperature=0.1,
        )
        
        data = cls._extract_json(response)
        if not data:
            raise Stage1Error(f"Stage 1 failed to parse JSON: {response[:200]}")
        
        return cls._validate_and_build(data)
    
    @classmethod
    def _extract_json(cls, text: str) -> Optional[dict]:
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
    
    @classmethod
    def _validate_and_build(cls, data: dict) -> PartTopology:
        """Validate and build PartTopology from LLM output."""
        parts_data = data.get("parts")
        if not parts_data or not isinstance(parts_data, list):
            raise Stage1Error("Missing or invalid 'parts' array")
        
        if len(parts_data) == 0:
            raise Stage1Error("'parts' array is empty")
        
        parts: List[PartNode] = []
        labels_seen: set = set()
        root_count = 0
        
        for i, p in enumerate(parts_data):
            # Check for numeric fields (FORBIDDEN in Stage 1)
            cls._check_no_numbers(p, f"parts[{i}]")
            
            # Label (required, unique)
            label = p.get("label")
            if not label or not isinstance(label, str):
                raise Stage1Error(f"parts[{i}]: missing or invalid 'label'")
            if label in labels_seen:
                raise Stage1Error(f"parts[{i}]: duplicate label '{label}'")
            labels_seen.add(label)
            
            # primitive_type (required, from closed vocabulary)
            prim = p.get("primitive_type")
            if not prim:
                raise Stage1Error(f"parts[{i}] '{label}': missing 'primitive_type'")
            if prim not in VALID_PRIMITIVES:
                raise Stage1Error(
                    f"parts[{i}] '{label}': invalid primitive_type '{prim}'. "
                    f"Must be one of: {VALID_PRIMITIVES}"
                )
            
            # socket_type (required, from closed vocabulary)
            socket = p.get("socket_type")
            if not socket:
                raise Stage1Error(f"parts[{i}] '{label}': missing 'socket_type'")
            socket = socket.upper()  # Normalize to uppercase
            if socket not in VALID_SOCKET_TYPES:
                raise Stage1Error(
                    f"parts[{i}] '{label}': invalid socket_type '{socket}'. "
                    f"Must be one of: {VALID_SOCKET_TYPES}"
                )
            
            # parent_label
            parent = p.get("parent_label")
            
            # ROOT validation
            if socket == "ROOT":
                root_count += 1
                if parent is not None:
                    raise Stage1Error(f"parts[{i}] '{label}': ROOT part must have parent_label=null")
            else:
                if parent is None:
                    raise Stage1Error(f"parts[{i}] '{label}': non-ROOT part must have parent_label")
                if parent not in labels_seen:
                    raise Stage1Error(
                        f"parts[{i}] '{label}': parent_label '{parent}' not found. "
                        f"Parts must be ordered so parents come before children."
                    )
            
            parts.append(PartNode(
                label=label,
                primitive_type=prim,
                parent_label=parent,
                socket_type=socket,
            ))
        
        # Exactly one ROOT
        if root_count == 0:
            raise Stage1Error("No ROOT part found. Exactly one part must have socket_type='ROOT'")
        if root_count > 1:
            raise Stage1Error(f"Multiple ROOT parts found ({root_count}). Exactly one allowed.")
        
        return PartTopology(parts=parts)
    
    @classmethod
    def _check_no_numbers(cls, obj: Any, path: str) -> None:
        """Recursively check that no numeric values exist in the object."""
        if isinstance(obj, (int, float)):
            raise Stage1Error(
                f"{path}: numeric value {obj} found. "
                "Stage 1 output must contain NO numbers - only structure."
            )
        elif isinstance(obj, dict):
            for k, v in obj.items():
                # Skip checking the value of known string fields
                if k in ("label", "primitive_type", "parent_label", "socket_type"):
                    continue
                cls._check_no_numbers(v, f"{path}.{k}")
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                cls._check_no_numbers(item, f"{path}[{i}]")


class Stage1Error(Exception):
    """Raised when Stage 1 fails to produce valid output."""
    pass
