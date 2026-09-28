"""Stage 0 — Object Understanding & Scale Anchor.

Input: Raw user prompt.
Output: ObjectUnderstanding with category, rests_on_surface, style_tag, scale_anchor_m.

This stage grounds the entire build with a real-world scale reference.
The LLM may use web search here to find typical dimensions for the object category.
"""

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)


# Closed vocabulary for style_tag (extend here, not ad-hoc)
VALID_STYLE_TAGS = frozenset({
    "hard_surface_industrial",
    "organic_worn",
    "stylized_clean",
    "soft_domestic",
})


@dataclass
class ScaleAnchor:
    """Scale reference for the object."""
    overall_height_or_length_m: float
    reasoning: str


@dataclass
class ObjectUnderstanding:
    """Stage 0 output: semantic understanding of the object."""
    category: str
    rests_on_surface: bool
    style_tag: str
    scale_anchor: ScaleAnchor
    
    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "rests_on_surface": self.rests_on_surface,
            "style_tag": self.style_tag,
            "scale_anchor_m": {
                "overall_height_or_length": self.scale_anchor.overall_height_or_length_m,
                "reasoning": self.scale_anchor.reasoning,
            },
        }


STAGE0_SYSTEM_PROMPT = """You are analyzing a 3D object request to understand its category and real-world scale.

Your task is to output a JSON object with these fields:
- category: A short snake_case category name (e.g., "training_dummy", "arcade_cabinet", "communication_tower")
- rests_on_surface: true if the object normally sits on a surface (floor, table), false for free-floating objects (satellites, dumbbells, axles)
- style_tag: One of: "hard_surface_industrial", "organic_worn", "stylized_clean", "soft_domestic"
- scale_anchor_m: An object with:
  - overall_height_or_length: The object's primary dimension in METERS (use real-world reference)
  - reasoning: Brief explanation of how you determined the scale

CRITICAL: The scale_anchor is the GROUND TRUTH for this build. All part dimensions will be validated as ratios against this value. Be accurate.

Examples:
- "A training dummy for martial arts" → height ~1.7m (human-height target)
- "An arcade cabinet" → height ~1.8m (standard arcade machine)
- "A communication tower" → height ~7-15m (small radio mast)
- "A coffee mug" → height ~0.10m (typical mug)
- "A dumbbell" → length ~0.4m, rests_on_surface=false

Output ONLY valid JSON, no markdown, no explanation outside the JSON."""


class Stage0Understanding:
    """Stage 0: Extract object understanding and scale anchor from prompt."""
    
    @classmethod
    async def run(
        cls,
        prompt: str,
        model_manager: Any,
        task_id: str,
        model_id: Optional[str] = None,
        rejection_feedback: Optional[str] = None,
    ) -> ObjectUnderstanding:
        """Run Stage 0 to extract object understanding.
        
        Args:
            prompt: Raw user prompt describing the object
            model_manager: Model manager for LLM calls
            task_id: Task ID for tracking
            model_id: Optional specific model to use
            rejection_feedback: Error from previous attempt (for retry)
            
        Returns:
            ObjectUnderstanding with category, style, and scale anchor
            
        Raises:
            Stage0Error: If LLM output is invalid or missing required fields
        """
        mid = model_id or model_manager.get_model_for_workflow("ENDPOINT")
        
        user_prompt = prompt
        if rejection_feedback:
            user_prompt = f"{prompt}\n\n[RETRY - Previous attempt failed: {rejection_feedback}. Fix the issue.]"
        
        response = await model_manager.generate_async(
            model_id=mid,
            task_id=f"stage0_{task_id}",
            lease_id="internal",
            lease_generation=0,
            system_prompt=STAGE0_SYSTEM_PROMPT,
            prompt=user_prompt,
            temperature=0.1,
        )
        
        data = cls._extract_json(response)
        if not data:
            raise Stage0Error(f"Stage 0 failed to parse JSON from LLM response: {response[:200]}")
        
        return cls._validate_and_build(data)
    
    @classmethod
    def _extract_json(cls, text: str) -> Optional[dict]:
        """Extract JSON from LLM response."""
        try:
            # Try direct parse first
            return json.loads(text.strip())
        except json.JSONDecodeError:
            pass
        
        # Try extracting from markdown code block
        m = re.search(r'```(?:json)?\s*(\{[\s\S]*?\})\s*```', text)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass
        
        # Try finding raw JSON object
        m = re.search(r'\{[\s\S]*\}', text)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
        
        return None
    
    @classmethod
    def _validate_and_build(cls, data: dict) -> ObjectUnderstanding:
        """Validate LLM output and build ObjectUnderstanding."""
        # Category (required)
        category = data.get("category")
        if not category or not isinstance(category, str):
            raise Stage0Error("Missing or invalid 'category' field")
        
        # rests_on_surface (required, must be bool)
        rests_on_surface = data.get("rests_on_surface")
        if rests_on_surface is None:
            raise Stage0Error("Missing 'rests_on_surface' field")
        if not isinstance(rests_on_surface, bool):
            # Try to coerce string "true"/"false"
            if isinstance(rests_on_surface, str):
                rests_on_surface = rests_on_surface.lower() == "true"
            else:
                raise Stage0Error(f"'rests_on_surface' must be boolean, got: {type(rests_on_surface)}")
        
        # style_tag (required, must be from closed vocabulary)
        style_tag = data.get("style_tag", "hard_surface_industrial")
        if style_tag not in VALID_STYLE_TAGS:
            logger.warning(
                f"Stage 0: Invalid style_tag '{style_tag}', defaulting to 'hard_surface_industrial'. "
                f"Valid options: {VALID_STYLE_TAGS}"
            )
            style_tag = "hard_surface_industrial"
        
        # scale_anchor_m (required)
        scale_data = data.get("scale_anchor_m")
        if not scale_data or not isinstance(scale_data, dict):
            raise Stage0Error("Missing or invalid 'scale_anchor_m' field")
        
        height_or_length = scale_data.get("overall_height_or_length")
        if height_or_length is None:
            raise Stage0Error("Missing 'scale_anchor_m.overall_height_or_length' field")
        
        try:
            height_or_length = float(height_or_length)
        except (TypeError, ValueError):
            raise Stage0Error(f"'scale_anchor_m.overall_height_or_length' must be numeric, got: {height_or_length}")
        
        if height_or_length <= 0:
            raise Stage0Error(f"'scale_anchor_m.overall_height_or_length' must be positive, got: {height_or_length}")
        
        # Sanity check: flag suspicious scales but don't reject
        if height_or_length > 100:
            logger.warning(f"Stage 0: Scale anchor {height_or_length}m seems very large (>100m)")
        elif height_or_length < 0.01:
            logger.warning(f"Stage 0: Scale anchor {height_or_length}m seems very small (<1cm)")
        
        reasoning = scale_data.get("reasoning", "No reasoning provided")
        
        return ObjectUnderstanding(
            category=category,
            rests_on_surface=rests_on_surface,
            style_tag=style_tag,
            scale_anchor=ScaleAnchor(
                overall_height_or_length_m=height_or_length,
                reasoning=reasoning,
            ),
        )


class Stage0Error(Exception):
    """Raised when Stage 0 fails to produce valid output."""
    pass
