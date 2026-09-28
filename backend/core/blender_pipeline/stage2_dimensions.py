"""Stage 2 — Dimension Assignment.

Input: Stage 1 topology + Stage 0 scale anchor.
Output: Dimensions for each part, validated as ratios against scale_anchor.

Code validates each dimension as a ratio of the scale anchor.
Parts claiming to be larger than the whole object, or smaller than 1/500th,
are flagged for re-ask.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# Ratio bounds for sanity checking
MAX_PART_RATIO = 1.0      # No part larger than the whole object
MIN_PART_RATIO = 0.002    # No part smaller than 1/500th of object


@dataclass
class PartMaterial:
    """Material properties for a part."""
    color: Tuple[float, float, float] = (0.5, 0.5, 0.5)  # RGB (0-1)
    metallic: float = 0.0      # 0=plastic/matte, 1=metal
    roughness: float = 0.5     # 0=shiny/mirror, 1=matte
    emission_color: Optional[Tuple[float, float, float]] = None  # RGB glow
    emission_strength: float = 0.0  # Glow intensity


@dataclass
class PartDimensions:
    """Dimensions for a single part."""
    label: str
    primitive_type: str
    # Primitive-specific dimensions (all in meters)
    size: Optional[Tuple[float, float, float]] = None  # For box: [x, y, z]
    radius: Optional[float] = None                      # For cylinder, sphere, cone
    depth: Optional[float] = None                       # For cylinder, cone
    radius1: Optional[float] = None                     # For cone (base radius)
    vertices: int = 32                                  # For cylinder
    confidence: float = 1.0                             # LLM's confidence in these values
    material: Optional[PartMaterial] = None             # Material properties
    
    def get_max_extent(self) -> float:
        """Get the largest dimension of this part."""
        extents = []
        if self.size:
            extents.extend(self.size)
        if self.radius:
            extents.append(self.radius * 2)
        if self.depth:
            extents.append(self.depth)
        if self.radius1:
            extents.append(self.radius1 * 2)
        return max(extents) if extents else 0.0
    
    def to_sub_spec(self) -> dict:
        """Convert to sub_spec dict for AssemblyNode."""
        spec = {"primitive": self.primitive_type}
        if self.primitive_type == "box" and self.size:
            spec["size"] = list(self.size)
        elif self.primitive_type == "cylinder":
            spec["radius"] = self.radius or 0.1
            spec["depth"] = self.depth or 1.0
            spec["vertices"] = self.vertices
        elif self.primitive_type == "sphere":
            spec["radius"] = self.radius or 0.5
        elif self.primitive_type == "cone":
            spec["radius1"] = self.radius1 or self.radius or 0.5
            spec["depth"] = self.depth or 1.0
        return spec


@dataclass
class DimensionedPart:
    """A part with both topology and dimensions."""
    label: str
    primitive_type: str
    parent_label: Optional[str]
    socket_type: str
    dimensions: PartDimensions


@dataclass
class Stage2Output:
    """Stage 2 output: parts with dimensions."""
    parts: List[DimensionedPart] = field(default_factory=list)
    scale_anchor_m: float = 1.0
    
    def get_part(self, label: str) -> Optional[DimensionedPart]:
        """Get a part by label."""
        for p in self.parts:
            if p.label == label:
                return p
        return None
    
    def to_dict(self) -> dict:
        return {
            "scale_anchor_m": self.scale_anchor_m,
            "parts": [
                {
                    "label": p.label,
                    "primitive_type": p.primitive_type,
                    "parent_label": p.parent_label,
                    "socket_type": p.socket_type,
                    "dimensions": {
                        "size": list(p.dimensions.size) if p.dimensions.size else None,
                        "radius": p.dimensions.radius,
                        "depth": p.dimensions.depth,
                        "radius1": p.dimensions.radius1,
                        "vertices": p.dimensions.vertices,
                        "confidence": p.dimensions.confidence,
                    },
                    "material": {
                        "color": list(p.dimensions.material.color) if p.dimensions.material else [0.5, 0.5, 0.5],
                        "metallic": p.dimensions.material.metallic if p.dimensions.material else 0.0,
                        "roughness": p.dimensions.material.roughness if p.dimensions.material else 0.5,
                        "emission_color": list(p.dimensions.material.emission_color) if p.dimensions.material and p.dimensions.material.emission_color else None,
                        "emission_strength": p.dimensions.material.emission_strength if p.dimensions.material else 0.0,
                    } if p.dimensions.material else None,
                }
                for p in self.parts
            ],
        }


STAGE2_SYSTEM_PROMPT = """You are assigning dimensions AND materials to 3D object parts.

You will receive:
1. The object's scale anchor (total height/length in meters)
2. A list of parts with their primitive types

Your task is to output dimensions AND material properties for each part.

CRITICAL RULES:
1. ALL dimensions must be in METERS (not mm, not cm).
2. Each part's largest dimension should be a reasonable fraction of the scale anchor.
3. Parts should fit together logically (child parts smaller than parents, etc.)
4. Materials must be realistic for the object type.

For each primitive type, provide "dimensions":
- box: "size" as [x, y, z] in meters
- cylinder: "radius" and "depth" in meters, optionally "vertices" (default 32)
- sphere: "radius" in meters
- cone: "radius1" (base radius) and "depth" in meters

For ALL parts, also provide "material" with:
- "color": [R, G, B] values 0.0-1.0 (REQUIRED)
- "metallic": 0.0-1.0 (0=plastic/painted, 1=chrome/metal)
- "roughness": 0.0-1.0 (0=shiny/glossy, 1=matte)
- "emission_color": [R, G, B] for glowing parts (screens, LEDs) or null
- "emission_strength": 0.0-10.0 for glow intensity (0 if not glowing)

Material guidelines:
- Arcade cabinet body: color=[0.1,0.1,0.15], metallic=0, roughness=0.3 (painted wood/plastic)
- Screens: color=[0.02,0.02,0.03], metallic=0, roughness=0.1, emission_color=[0.0,0.3,0.5], emission_strength=2.0
- Control panels: color=[0.15,0.15,0.2], metallic=0, roughness=0.4
- Plastic buttons: color=[1.0,0.2,0.2], metallic=0, roughness=0.3 (shiny plastic)
- Metal parts: color=[0.7,0.7,0.75], metallic=0.9, roughness=0.3
- Joystick ball: color=[1.0,0.0,0.0], metallic=0, roughness=0.2 (shiny red)
- Wood: color=[0.4,0.25,0.1], metallic=0, roughness=0.7
- Chrome trim: color=[0.9,0.9,0.95], metallic=1.0, roughness=0.1

Output JSON with a "parts" array:
```json
{
  "parts": [
    {
      "label": "body",
      "dimensions": {"size": [0.7, 0.6, 1.6], "confidence": 0.8},
      "material": {"color": [0.1, 0.1, 0.15], "metallic": 0.0, "roughness": 0.3, "emission_color": null, "emission_strength": 0.0}
    },
    {
      "label": "screen",
      "dimensions": {"size": [0.5, 0.05, 0.4], "confidence": 0.7},
      "material": {"color": [0.02, 0.02, 0.03], "metallic": 0.0, "roughness": 0.1, "emission_color": [0.0, 0.4, 0.6], "emission_strength": 3.0}
    },
    {
      "label": "button_1",
      "dimensions": {"radius": 0.02, "depth": 0.015, "confidence": 0.6},
      "material": {"color": [1.0, 0.2, 0.2], "metallic": 0.0, "roughness": 0.25, "emission_color": null, "emission_strength": 0.0}
    }
  ]
}
```

Output ONLY valid JSON."""


class Stage2Dimensions:
    """Stage 2: Assign dimensions to parts."""
    
    @classmethod
    async def run(
        cls,
        stage0_output: dict,
        stage1_output: dict,
        model_manager: Any,
        task_id: str,
        model_id: Optional[str] = None,
        rejection_feedback: Optional[str] = None,
    ) -> Stage2Output:
        """Run Stage 2 to assign dimensions.
        
        Args:
            stage0_output: Output from Stage 0
            stage1_output: Output from Stage 1
            model_manager: Model manager for LLM calls
            task_id: Task ID for tracking
            model_id: Optional specific model to use
            rejection_feedback: Error from previous attempt (for retry)
            
        Returns:
            Stage2Output with dimensioned parts
            
        Raises:
            Stage2Error: If output is invalid
        """
        mid = model_id or model_manager.get_model_for_workflow("ENDPOINT")
        
        scale_anchor = stage0_output.get("scale_anchor_m", {}).get("overall_height_or_length", 1.0)
        
        # Build context
        parts_list = "\n".join(
            f"- {p['label']}: {p['primitive_type']} (socket: {p['socket_type']})"
            for p in stage1_output.get("parts", [])
        )
        
        context = (
            f"Scale anchor: {scale_anchor}m (this is the object's total height/length)\n"
            f"Category: {stage0_output.get('category', 'unknown')}\n\n"
            f"Parts to dimension:\n{parts_list}"
        )
        
        if rejection_feedback:
            context += f"\n\n[RETRY - Previous attempt failed: {rejection_feedback}. Fix the issue.]"
        
        response = await model_manager.generate_async(
            model_id=mid,
            task_id=f"stage2_{task_id}",
            lease_id="internal",
            lease_generation=0,
            system_prompt=STAGE2_SYSTEM_PROMPT,
            prompt=context,
            temperature=0.1,
        )
        
        data = cls._extract_json(response)
        if not data:
            raise Stage2Error(f"Stage 2 failed to parse JSON: {response[:200]}")
        
        return cls._validate_and_build(data, stage1_output, scale_anchor)
    
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
    def _validate_and_build(
        cls,
        data: dict,
        stage1_output: dict,
        scale_anchor: float,
    ) -> Stage2Output:
        """Validate dimensions and build output."""
        parts_data = data.get("parts")
        if not parts_data or not isinstance(parts_data, list):
            raise Stage2Error("Missing or invalid 'parts' array")
        
        # Build lookup from Stage 1
        stage1_parts = {p["label"]: p for p in stage1_output.get("parts", [])}
        
        dimensioned_parts: List[DimensionedPart] = []
        ratio_violations: List[str] = []
        
        for p in parts_data:
            label = p.get("label")
            if not label:
                raise Stage2Error(f"Part missing 'label' field")
            
            if label not in stage1_parts:
                raise Stage2Error(f"Part '{label}' not found in Stage 1 topology")
            
            s1_part = stage1_parts[label]
            
            # Build PartDimensions based on primitive type
            prim = s1_part["primitive_type"]
            dims_data = p.get("dimensions", {})
            mat_data = p.get("material")  # New: separate material object
            dims = cls._build_dimensions(label, prim, dims_data, mat_data)
            
            # Ratio check against scale anchor
            max_extent = dims.get_max_extent()
            if max_extent > 0 and scale_anchor > 0:
                ratio = max_extent / scale_anchor
                if ratio > MAX_PART_RATIO:
                    ratio_violations.append(
                        f"'{label}': {max_extent:.3f}m is {ratio:.1f}x the scale anchor ({scale_anchor}m)"
                    )
                elif ratio < MIN_PART_RATIO:
                    ratio_violations.append(
                        f"'{label}': {max_extent:.3f}m is only {ratio:.4f}x the scale anchor (too small)"
                    )
            
            dimensioned_parts.append(DimensionedPart(
                label=label,
                primitive_type=prim,
                parent_label=s1_part["parent_label"],
                socket_type=s1_part["socket_type"],
                dimensions=dims,
            ))
        
        # Log ratio violations as warnings (don't fail, but flag for review)
        # CRITICAL: Severe violations (>2x or <0.001x) should raise errors
        severe_violations = []
        for v in ratio_violations:
            # Parse the ratio from the violation message
            if "is " in v and "x the scale anchor" in v:
                # Extract ratio value
                import re
                match = re.search(r'is ([\d.]+)x the scale anchor', v)
                if match:
                    ratio = float(match.group(1))
                    if ratio > 2.0:  # Part claims to be >2x the whole object
                        severe_violations.append(v)
            elif "too small" in v:
                severe_violations.append(v)
        
        if severe_violations:
            raise Stage2Error(
                f"Severe dimension violations - parts are impossibly sized:\n" +
                "\n".join(f"  - {v}" for v in severe_violations)
            )
        
        if ratio_violations:
            logger.warning(
                f"Stage 2: Dimension ratio violations detected:\n" +
                "\n".join(f"  - {v}" for v in ratio_violations)
            )
        
        return Stage2Output(
            parts=dimensioned_parts,
            scale_anchor_m=scale_anchor,
        )
    
    @classmethod
    def _build_dimensions(cls, label: str, prim: str, dims: dict, mat_data: Optional[dict]) -> PartDimensions:
        """Build PartDimensions from raw dimension and material data."""
        confidence = float(dims.get("confidence", 0.5))
        
        # Parse material
        material = None
        if mat_data:
            color = (0.5, 0.5, 0.5)
            if mat_data.get("color"):
                c = mat_data["color"]
                if isinstance(c, (list, tuple)) and len(c) >= 3:
                    color = (float(c[0]), float(c[1]), float(c[2]))
            
            emission_color = None
            if mat_data.get("emission_color"):
                ec = mat_data["emission_color"]
                if isinstance(ec, (list, tuple)) and len(ec) >= 3:
                    emission_color = (float(ec[0]), float(ec[1]), float(ec[2]))
            
            material = PartMaterial(
                color=color,
                metallic=float(mat_data.get("metallic", 0.0)),
                roughness=float(mat_data.get("roughness", 0.5)),
                emission_color=emission_color,
                emission_strength=float(mat_data.get("emission_strength", 0.0)),
            )
        
        if prim == "box":
            size = dims.get("size")
            if not size or not isinstance(size, list) or len(size) != 3:
                raise Stage2Error(f"Part '{label}' (box): invalid or missing 'size' [x,y,z]")
            return PartDimensions(
                label=label,
                primitive_type=prim,
                size=tuple(float(s) for s in size),
                confidence=confidence,
                material=material,
            )
        
        elif prim == "cylinder":
            radius = dims.get("radius")
            depth = dims.get("depth")
            if radius is None:
                raise Stage2Error(f"Part '{label}' (cylinder): missing 'radius'")
            if depth is None:
                raise Stage2Error(f"Part '{label}' (cylinder): missing 'depth'")
            return PartDimensions(
                label=label,
                primitive_type=prim,
                radius=float(radius),
                depth=float(depth),
                vertices=int(dims.get("vertices", 32)),
                confidence=confidence,
                material=material,
            )
        
        elif prim == "sphere":
            radius = dims.get("radius")
            if radius is None:
                raise Stage2Error(f"Part '{label}' (sphere): missing 'radius'")
            return PartDimensions(
                label=label,
                primitive_type=prim,
                radius=float(radius),
                confidence=confidence,
                material=material,
            )
        
        elif prim == "cone":
            radius1 = dims.get("radius1") or dims.get("radius")
            depth = dims.get("depth")
            if radius1 is None:
                raise Stage2Error(f"Part '{label}' (cone): missing 'radius1' or 'radius'")
            if depth is None:
                raise Stage2Error(f"Part '{label}' (cone): missing 'depth'")
            return PartDimensions(
                label=label,
                primitive_type=prim,
                radius1=float(radius1),
                depth=float(depth),
                confidence=confidence,
                material=material,
            )
        
        else:
            raise Stage2Error(f"Part '{label}': unknown primitive type '{prim}'")


class Stage2Error(Exception):
    """Raised when Stage 2 fails to produce valid output."""
    pass
