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
        
        return cls._parse_response(response, node)
    
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
        lines.append("")
        
        # This part
        lines.append(f"Part to dimension: {node.label}")
        lines.append(f"Primitive type: {node.geometry.primitive.value}")
        lines.append(f"Socket type: {node.attachment.socket_type.value}")
        
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
        
        return "\n".join(lines)
    
    @classmethod
    def _parse_response(cls, response: str, node: ManifestNode) -> DimensionsOutput:
        """Parse LLM response into DimensionsOutput."""
        data = cls._extract_json(response)
        if not data:
            raise Stage2Error(f"Failed to parse JSON from response: {response[:200]}")
        
        primitive = node.geometry.primitive
        output = DimensionsOutput(reasoning=data.get("reasoning", ""))
        
        # Parse based on primitive type
        if primitive == PrimitiveType.BOX:
            output.size_x = cls._get_positive_float(data, "size_x", 0.1)
            output.size_y = cls._get_positive_float(data, "size_y", output.size_x)
            output.size_z = cls._get_positive_float(data, "size_z", output.size_x)
            
        elif primitive in (PrimitiveType.CYLINDER, PrimitiveType.HEMISPHERE):
            output.radius = cls._get_positive_float(data, "radius", 0.1)
            if primitive == PrimitiveType.CYLINDER:
                output.depth = cls._get_positive_float(data, "depth", 0.2)
                
        elif primitive == PrimitiveType.CONE:
            output.radius = cls._get_positive_float(data, "radius", 0.1)
            output.radius2 = cls._get_float(data, "radius2", 0.0)  # Can be 0 for pointed
            output.depth = cls._get_positive_float(data, "depth", 0.2)
            
        elif primitive == PrimitiveType.SPHERE:
            output.radius = cls._get_positive_float(data, "radius", 0.1)
            
        elif primitive == PrimitiveType.TORUS:
            output.major_radius = cls._get_positive_float(data, "major_radius", 0.1)
            output.minor_radius = cls._get_positive_float(data, "minor_radius", 0.02)
        
        return output
    
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
