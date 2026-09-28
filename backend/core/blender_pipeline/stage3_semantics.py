"""Stage 3 — Attachment Semantics.

Input: Stage 1 topology + Stage 2 dimensions.
Output: Semantic attachment hints per socket_type (height_hint, pierce_direction, etc.)

CRITICAL: Still NO raw offset/rotation numbers. Only semantic hints from closed vocabularies.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# Closed vocabularies for semantic hints
VALID_HEIGHT_HINTS = frozenset({
    "near_top",
    "center",
    "near_bottom",
    "flush_top",
    "flush_bottom",
})

VALID_PIERCE_DIRECTIONS = frozenset({
    "left_right",   # X axis
    "front_back",   # Y axis
    "up_down",      # Z axis (rare for THROUGH_AXIS)
})

VALID_FACE_POSITIONS = frozenset({
    "center",
    "near_top",
    "near_bottom",
    "near_left",
    "near_right",
})


@dataclass
class AttachmentSemantics:
    """Semantic attachment hints for a single part."""
    label: str
    socket_type: str
    
    # For THROUGH_AXIS
    pierce_direction: Optional[str] = None  # left_right, front_back, up_down
    height_hint: Optional[str] = None       # near_top, center, near_bottom
    
    # For ARRAY_MEMBER
    array_axis: Optional[str] = None        # x, y, z
    array_count: Optional[int] = None
    array_index: Optional[int] = None
    spacing_hint: Optional[str] = None      # tight, normal, spread
    
    # For STRUT / RADIAL_BRIDGE
    connects_to: Optional[str] = None       # Label of the other endpoint
    radial_count: Optional[int] = None      # For RADIAL/RADIAL_BRIDGE
    radial_index: Optional[int] = None
    
    # For face mounts
    face_position: Optional[str] = None     # center, near_top, near_bottom, etc.
    
    # For BOOLEAN_CUT
    cut_face: Optional[str] = None          # Which face to cut into: top, front, etc.


@dataclass
class Stage3Output:
    """Stage 3 output: parts with attachment semantics."""
    parts: List[AttachmentSemantics] = field(default_factory=list)
    
    def get_semantics(self, label: str) -> Optional[AttachmentSemantics]:
        """Get semantics for a part by label."""
        for p in self.parts:
            if p.label == label:
                return p
        return None
    
    def to_dict(self) -> dict:
        return {
            "parts": [
                {
                    "label": p.label,
                    "socket_type": p.socket_type,
                    "pierce_direction": p.pierce_direction,
                    "height_hint": p.height_hint,
                    "array_axis": p.array_axis,
                    "array_count": p.array_count,
                    "array_index": p.array_index,
                    "spacing_hint": p.spacing_hint,
                    "connects_to": p.connects_to,
                    "radial_count": p.radial_count,
                    "radial_index": p.radial_index,
                    "face_position": p.face_position,
                    "cut_face": p.cut_face,
                }
                for p in self.parts
            ],
        }


# Socket types that need specific semantic fields
SOCKET_REQUIRED_FIELDS = {
    "THROUGH_AXIS": ["pierce_direction"],
    "STRUT": ["connects_to"],
    "RADIAL_BRIDGE": ["connects_to", "radial_count", "radial_index"],
    "RADIAL": ["radial_count", "radial_index"],
    "ARRAY_MEMBER": ["array_count", "array_index"],
    "BOOLEAN_CUT": [],  # cut_face is optional, defaults to TOP_FACE
}


STAGE3_SYSTEM_PROMPT = """You are specifying how 3D parts attach to each other using semantic hints.

You will receive parts with their socket types. For each part, provide the semantic hints that socket type requires.

CRITICAL: NO NUMBERS for positions or rotations. Only semantic hints from these vocabularies:

For THROUGH_AXIS (part passes through parent):
- pierce_direction: "left_right" (X), "front_back" (Y), or "up_down" (Z)
- height_hint: "near_top", "center", "near_bottom", "flush_top", "flush_bottom"

For STRUT (diagonal connector):
- connects_to: label of the part this strut connects to (other than parent)

For RADIAL_BRIDGE (radial connector to another part):
- connects_to: label of the target part
- radial_count: total number of radial items (e.g., 4 for 4 struts)
- radial_index: this item's index (0 to count-1)

For RADIAL (items around parent's circumference):
- radial_count: total number of items
- radial_index: this item's index (0 to count-1)

For ARRAY_MEMBER (items in a line on a surface):
- array_axis: "x", "y", or "z"
- array_count: total items in array
- array_index: this item's index (0 to count-1)
- spacing_hint: "tight", "normal", "spread" (optional)

For face mounts (FRONT_FACE, etc.):
- height_hint: vertical position on the face
- face_position: "center", "near_left", "near_right" (optional)

For BOOLEAN_CUT (part subtracted from parent):
- cut_face: which face to cut into - "top", "front", "back", "left", "right", "bottom"
- height_hint: where along the face (optional, defaults to "center")
- face_position: lateral position on the face (optional, defaults to "center")

For simple sockets (TOP_CENTER, LEFT_END, etc.):
- Usually no extra fields needed, but height_hint can refine position

Output JSON with a "parts" array. Include ONLY the fields relevant to each socket type.

Example:
```json
{
  "parts": [
    {"label": "post", "socket_type": "ROOT"},
    {"label": "arm_axis", "socket_type": "THROUGH_AXIS", "pierce_direction": "left_right", "height_hint": "near_top"},
    {"label": "strike_shield", "socket_type": "LEFT_END"},
    {"label": "counterweight", "socket_type": "RIGHT_END"},
    {"label": "groove", "socket_type": "BOOLEAN_CUT", "cut_face": "front", "height_hint": "center"},
    {"label": "strut_1", "socket_type": "RADIAL_BRIDGE", "connects_to": "base_plate", "radial_count": 4, "radial_index": 0},
    {"label": "strut_2", "socket_type": "RADIAL_BRIDGE", "connects_to": "base_plate", "radial_count": 4, "radial_index": 1}
  ]
}
```

Output ONLY valid JSON."""


class Stage3Semantics:
    """Stage 3: Assign attachment semantics to parts."""
    
    @classmethod
    async def run(
        cls,
        stage1_output: dict,
        stage2_output: dict,
        model_manager: Any,
        task_id: str,
        model_id: Optional[str] = None,
        rejection_feedback: Optional[str] = None,
    ) -> Stage3Output:
        """Run Stage 3 to assign attachment semantics.
        
        Args:
            stage1_output: Output from Stage 1 (topology)
            stage2_output: Output from Stage 2 (dimensions)
            model_manager: Model manager for LLM calls
            task_id: Task ID for tracking
            model_id: Optional specific model to use
            rejection_feedback: Error from previous attempt (for retry)
            
        Returns:
            Stage3Output with attachment semantics
            
        Raises:
            Stage3Error: If output is invalid
        """
        mid = model_id or model_manager.get_model_for_workflow("ENDPOINT")
        
        # Build context showing parts with their socket types and dimensions
        parts_info = []
        for p in stage2_output.get("parts", []):
            dims = p.get("dimensions", {})
            dim_str = ""
            if dims.get("size"):
                dim_str = f"size={dims['size']}"
            elif dims.get("radius") and dims.get("depth"):
                dim_str = f"r={dims['radius']}, d={dims['depth']}"
            elif dims.get("radius"):
                dim_str = f"r={dims['radius']}"
            
            parts_info.append(
                f"- {p['label']}: {p['primitive_type']}, socket={p['socket_type']}, "
                f"parent={p.get('parent_label', 'none')}, {dim_str}"
            )
        
        context = (
            f"Parts with their socket types:\n" +
            "\n".join(parts_info) +
            "\n\nProvide semantic attachment hints for each part."
        )
        
        if rejection_feedback:
            context += f"\n\n[RETRY - Previous attempt failed: {rejection_feedback}. Fix the issue.]"
        
        response = await model_manager.generate_async(
            model_id=mid,
            task_id=f"stage3_{task_id}",
            lease_id="internal",
            lease_generation=0,
            system_prompt=STAGE3_SYSTEM_PROMPT,
            prompt=context,
            temperature=0.1,
        )
        
        data = cls._extract_json(response)
        if not data:
            raise Stage3Error(f"Stage 3 failed to parse JSON: {response[:200]}")
        
        return cls._validate_and_build(data, stage1_output)
    
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
    def _validate_and_build(cls, data: dict, stage1_output: dict) -> Stage3Output:
        """Validate semantics and build output."""
        parts_data = data.get("parts")
        if not parts_data or not isinstance(parts_data, list):
            raise Stage3Error("Missing or invalid 'parts' array")
        
        # Build lookup from Stage 1
        stage1_parts = {p["label"]: p for p in stage1_output.get("parts", [])}
        all_labels = set(stage1_parts.keys())
        
        semantics_list: List[AttachmentSemantics] = []
        processed_labels: set = set()
        
        for p in parts_data:
            label = p.get("label")
            if not label:
                raise Stage3Error("Part missing 'label' field")
            
            if label not in stage1_parts:
                raise Stage3Error(f"Part '{label}' not found in Stage 1 topology")
            
            processed_labels.add(label)
            socket_type = p.get("socket_type", stage1_parts[label]["socket_type"])
            
            # Validate required fields for this socket type
            # CRITICAL: Missing required fields = Stage3Error (not warning)
            required = SOCKET_REQUIRED_FIELDS.get(socket_type, [])
            missing = [f for f in required if p.get(f) is None]
            if missing:
                raise Stage3Error(
                    f"Part '{label}' ({socket_type}) missing REQUIRED fields: {missing}. "
                    f"These fields are mandatory for this socket type."
                )
            
            # Validate array/radial counts are valid
            if p.get("radial_count") is not None:
                rc = int(p["radial_count"])
                if rc < 1:
                    raise Stage3Error(f"Part '{label}': radial_count must be >= 1, got {rc}")
            if p.get("radial_index") is not None:
                ri = int(p["radial_index"])
                rc = int(p.get("radial_count", 1))
                if ri < 0 or ri >= rc:
                    raise Stage3Error(f"Part '{label}': radial_index {ri} out of range [0, {rc})")
            if p.get("array_count") is not None:
                ac = int(p["array_count"])
                if ac < 1:
                    raise Stage3Error(f"Part '{label}': array_count must be >= 1, got {ac}")
            if p.get("array_index") is not None:
                ai = int(p["array_index"])
                ac = int(p.get("array_count", 1))
                if ai < 0 or ai >= ac:
                    raise Stage3Error(f"Part '{label}': array_index {ai} out of range [0, {ac})")
            
            # Validate semantic values against closed vocabularies
            semantics = AttachmentSemantics(label=label, socket_type=socket_type)
            
            # pierce_direction
            if p.get("pierce_direction"):
                pd = p["pierce_direction"].lower()
                if pd not in VALID_PIERCE_DIRECTIONS:
                    logger.warning(f"Part '{label}': invalid pierce_direction '{pd}'")
                else:
                    semantics.pierce_direction = pd
            
            # height_hint
            if p.get("height_hint"):
                hh = p["height_hint"].lower()
                if hh not in VALID_HEIGHT_HINTS:
                    logger.warning(f"Part '{label}': invalid height_hint '{hh}'")
                else:
                    semantics.height_hint = hh
            
            # connects_to (must reference valid label)
            if p.get("connects_to"):
                ct = p["connects_to"]
                if ct not in all_labels:
                    raise Stage3Error(
                        f"Part '{label}': connects_to '{ct}' not found in parts list"
                    )
                semantics.connects_to = ct
            
            # Array fields
            if p.get("array_axis"):
                semantics.array_axis = p["array_axis"].lower()
            if p.get("array_count") is not None:
                semantics.array_count = int(p["array_count"])
            if p.get("array_index") is not None:
                semantics.array_index = int(p["array_index"])
            if p.get("spacing_hint"):
                semantics.spacing_hint = p["spacing_hint"].lower()
            
            # Radial fields
            if p.get("radial_count") is not None:
                semantics.radial_count = int(p["radial_count"])
            if p.get("radial_index") is not None:
                semantics.radial_index = int(p["radial_index"])
            
            # Face position
            if p.get("face_position"):
                fp = p["face_position"].lower()
                if fp not in VALID_FACE_POSITIONS:
                    logger.warning(f"Part '{label}': invalid face_position '{fp}'")
                else:
                    semantics.face_position = fp
            
            # cut_face for BOOLEAN_CUT
            if p.get("cut_face"):
                cf = p["cut_face"].lower()
                valid_cut_faces = {"top", "bottom", "front", "back", "left", "right"}
                if cf not in valid_cut_faces:
                    logger.warning(f"Part '{label}': invalid cut_face '{cf}', defaulting to 'top'")
                    cf = "top"
                semantics.cut_face = cf
            
            semantics_list.append(semantics)
        
        # CRITICAL: Add any parts that LLM missed with default semantics
        missing_labels = all_labels - processed_labels
        for label in missing_labels:
            s1_part = stage1_parts[label]
            socket_type = s1_part["socket_type"]
            logger.warning(f"Stage 3: LLM missed part '{label}', adding with default semantics")
            semantics_list.append(AttachmentSemantics(label=label, socket_type=socket_type))
        
        return Stage3Output(parts=semantics_list)


class Stage3Error(Exception):
    """Raised when Stage 3 fails to produce valid output."""
    pass
