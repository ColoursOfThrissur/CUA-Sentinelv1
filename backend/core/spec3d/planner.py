"""LLM Spec Planner — Stage 1 of the Spec3D v3 pipeline.

Calls the local Ollama 14B model to generate a full JSON spec for any
described 3D object.  Templates are never the production path here — they
are loaded as few-shot exemplars only.

Route selection (called by pipeline.py):
  1. Library exact match  → return approved spec directly.
  2. Category exemplar exists → plan_spec() with that exemplar as few-shot.
  3. No match at all      → plan_spec() with schema only.
  4. Confidence < 0.3     → decline and return error.

Best-of-N:
  Generate N candidates at temperature=0.6.
  Score each via Tier 1 verifier.
  Return highest-scoring candidate.

Repair loop:
  Deterministic repairs first (snap centerline, clamp knobs, rescale).
  Only remaining errors → LLM field-level JSON patch (max 3 rounds).
"""

from __future__ import annotations

import httpx
import json
import logging
import math
import re
from typing import Any, Dict, List, Optional, Tuple, Union

from pydantic import ValidationError

from .schema import (
    QuadrupedSpec,
    HardSurfaceSpec,
    VesselSpec,
    JointSpec,
)
from .verifier import SpecVerifier, VerificationResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Category → spec class mapping
# ---------------------------------------------------------------------------

QUADRUPED_CATEGORIES = {"quadruped", "dog", "cat", "wolf", "horse", "bear", "fox",
                         "lion", "tiger", "cow", "deer", "elephant", "giraffe",
                         "animal", "creature", "mammal"}

VESSEL_CATEGORIES = {"vessel", "cup", "mug", "vase", "bottle", "bowl", "glass",
                     "wineglass", "wine_glass", "jug", "pitcher"}

HARD_SURFACE_CATEGORIES = {
    "furniture", "table", "chair", "desk", "shelf", "bookshelf", "bench",
    "vehicle", "car", "truck", "forklift", "bus",
    "tool", "hammer", "wrench",
    "architecture", "building", "house",
    "generic",
}


def infer_category(prompt: str, hint: str = "") -> str:
    """Return the canonical category for a free-text object description."""
    combined = f"{hint} {prompt}".lower()
    for cat in QUADRUPED_CATEGORIES:
        if cat in combined:
            return "quadruped"
    for cat in VESSEL_CATEGORIES:
        if cat in combined:
            return "vessel"
    return "generic"


def _spec_class_for_category(category: str):
    if category == "quadruped":
        return QuadrupedSpec
    if category == "vessel":
        return VesselSpec
    return HardSurfaceSpec


# ---------------------------------------------------------------------------
# Scoring (weighted penalty — more detail within reason scores higher)
# ---------------------------------------------------------------------------

def score_spec(
    spec: Union[QuadrupedSpec, HardSurfaceSpec, VesselSpec],
    v_result: VerificationResult,
) -> float:
    """Return a numeric score; higher is better.  v_result.score is the base."""
    base = v_result.score  # 0.0–1.0 from Tier 1

    # Bonus: richer detail
    bonus = 0.0
    if isinstance(spec, QuadrupedSpec):
        # More joints (up to 22) and attachments are rewarded
        bonus += min(len(spec.joints) / 22.0, 1.0) * 0.05
        bonus += min(len(spec.attachments) / 3.0, 1.0) * 0.02
    elif isinstance(spec, HardSurfaceSpec):
        bonus += min(len(spec.parts) / 8.0, 1.0) * 0.04
    elif isinstance(spec, VesselSpec):
        bonus += min(len(spec.profile) / 12.0, 1.0) * 0.04

    return base + bonus


# ---------------------------------------------------------------------------
# Deterministic pre-repair
# ---------------------------------------------------------------------------

def apply_deterministic_repairs(
    spec: Union[QuadrupedSpec, HardSurfaceSpec, VesselSpec],
    errors: List[str],
) -> Union[QuadrupedSpec, HardSurfaceSpec, VesselSpec]:
    """Snap obvious out-of-range values without using the LLM."""
    if isinstance(spec, QuadrupedSpec):
        # Snap centerline x → 0.0
        for j in spec.joints:
            if not j.name.endswith("_L") and not j.name.endswith("_R"):
                j.x = 0.0
        # Clamp rx/ry within schema bounds
        for j in spec.joints:
            j.rx = max(0.002, min(j.rx, 2.0))
            j.ry = max(0.002, min(j.ry, 2.0))
        # Clamp body dimensions
        spec.body_length_m = max(0.05, min(spec.body_length_m, 5.0))
        spec.withers_height_m = max(0.05, min(spec.withers_height_m, 3.0))

    elif isinstance(spec, VesselSpec):
        # Clamp wall thickness
        spec.wall_thickness = max(0.001, min(spec.wall_thickness, 0.05))
        # Ensure profile radius values are non-negative
        for pt in spec.profile:
            pt.radius = max(0.0, pt.radius)
        # Ensure minimum 3 profile points (schema requires min_length=3)
        if len(spec.profile) == 2:
            from .schema import ProfilePoint
            bot, top = spec.profile[0], spec.profile[1]
            mid_r = (bot.radius + top.radius) / 2.0
            mid_h = (bot.height + top.height) / 2.0
            spec.profile.insert(1, ProfilePoint(radius=mid_r, height=mid_h))
        elif len(spec.profile) < 2:
            from .schema import ProfilePoint
            h = 0.1
            r = 0.04
            spec.profile = [
                ProfilePoint(radius=r * 0.8, height=0.0),
                ProfilePoint(radius=r, height=h * 0.5),
                ProfilePoint(radius=r * 0.9, height=h),
            ]

    elif isinstance(spec, HardSurfaceSpec):
        # Clamp modifier values
        for part in spec.parts:
            for mod in part.modifiers:
                if mod.thickness is not None:
                    mod.thickness = max(0.001, min(mod.thickness, 1.0))
                if mod.width is not None:
                    mod.width = max(0.001, min(mod.width, 1.0))

    return spec


# ---------------------------------------------------------------------------
# SpecPlanner
# ---------------------------------------------------------------------------

class SpecPlanner:
    """Plan, score, and repair 3D specs using the local Ollama LLM."""

    # ----------------------------------------------------------------
    # Public API
    # ----------------------------------------------------------------

    @classmethod
    async def plan_spec(
        cls,
        prompt: str,
        category_hint: str,
        model_manager: Any,
        exemplar: Optional[Dict[str, Any]] = None,
        temperature: float = 0.4,
    ) -> Tuple[Optional[Union[QuadrupedSpec, HardSurfaceSpec, VesselSpec]], float]:
        """
        Ask the LLM to generate one spec for `prompt`.

        Returns (spec_obj, confidence) or (None, 0.0) on unrecoverable failure.
        """
        category = infer_category(prompt, category_hint)
        spec_cls = _spec_class_for_category(category)
        system_prompt = cls._build_system_prompt(category, spec_cls, exemplar)
        user_message = f"Generate a complete JSON spec for: {prompt}"

        raw = await cls._call_llm(system_prompt, user_message, model_manager, temperature)
        if not raw:
            return None, 0.0

        return cls._parse_and_score(raw, spec_cls)

    @classmethod
    async def plan_best_of_n(
        cls,
        prompt: str,
        category_hint: str,
        model_manager: Any,
        exemplar: Optional[Dict[str, Any]] = None,
        n: int = 3,
    ) -> Tuple[Optional[Union[QuadrupedSpec, HardSurfaceSpec, VesselSpec]], float]:
        """
        Generate N candidates and return the highest-scoring one.

        Uses temperature=0.6 for diversity.
        """
        category = infer_category(prompt, category_hint)
        spec_cls = _spec_class_for_category(category)
        system_prompt = cls._build_system_prompt(category, spec_cls, exemplar)
        user_message = f"Generate a complete JSON spec for: {prompt}"

        candidates: List[Tuple[Union[QuadrupedSpec, HardSurfaceSpec, VesselSpec], float]] = []

        for i in range(n):
            raw = await cls._call_llm(system_prompt, user_message, model_manager, temperature=0.6)
            if not raw:
                continue
            spec_obj, score = cls._parse_and_score(raw, spec_cls)
            if spec_obj is not None:
                logger.info(f"Candidate {i+1}/{n}: score={score:.3f}")
                candidates.append((spec_obj, score))

        if not candidates:
            return None, 0.0

        # Sort descending by score
        candidates.sort(key=lambda x: x[1], reverse=True)
        best_spec, best_score = candidates[0]
        logger.info(f"Best-of-{n} winner: score={best_score:.3f}")
        return best_spec, best_score

    @classmethod
    async def repair_spec(
        cls,
        spec: Union[QuadrupedSpec, HardSurfaceSpec, VesselSpec],
        errors: List[str],
        model_manager: Any,
        max_rounds: int = 3,
    ) -> Tuple[Union[QuadrupedSpec, HardSurfaceSpec, VesselSpec], bool]:
        """
        Repair a spec that failed Tier 1 verification.

        1. Apply deterministic repairs first.
        2. Re-verify; if still failing, send remaining errors to LLM for field-level patch.
        3. Repeat up to max_rounds.

        Returns (repaired_spec, success).
        """
        # Step 1: deterministic
        spec = apply_deterministic_repairs(spec, errors)

        for round_num in range(max_rounds):
            if isinstance(spec, QuadrupedSpec):
                v_result = SpecVerifier.verify_quadruped(spec)
            elif isinstance(spec, VesselSpec):
                # VesselSpec Tier1 is simple — just re-validate the model
                try:
                    spec = type(spec)(**spec.model_dump())
                    v_result = VerificationResult(valid=True, score=0.9)
                except Exception as e:
                    v_result = VerificationResult(valid=False, score=0.0, errors=[str(e)])
            else:
                v_result = SpecVerifier.verify_hard_surface(spec)

            if v_result.valid:
                logger.info(f"Spec repaired in round {round_num + 1}")
                return spec, True

            remaining_errors = v_result.errors
            if not remaining_errors:
                return spec, True

            # Step 2: LLM field-level patch
            logger.info(f"Repair round {round_num + 1}: {len(remaining_errors)} errors remain, asking LLM")
            patch = await cls._ask_for_patch(spec, remaining_errors, model_manager)
            if not patch:
                continue

            spec_dict = spec.model_dump()
            cls._apply_json_patch(spec_dict, patch)
            try:
                spec = type(spec)(**spec_dict)
            except ValidationError as e:
                logger.warning(f"Patch produced invalid spec: {e}")
                continue

        # Final check
        return spec, v_result.valid if v_result else False

    # ----------------------------------------------------------------
    # Prompt construction
    # ----------------------------------------------------------------

    @classmethod
    def _build_system_prompt(
        cls,
        category: str,
        spec_cls,
        exemplar: Optional[Dict[str, Any]],
    ) -> str:
        schema_json = json.dumps(spec_cls.model_json_schema(), indent=2)

        dimension_hints = cls._dimension_hints(category)

        exemplar_section = ""
        if exemplar:
            exemplar_section = f"""
## Few-Shot Exemplar
Study this approved spec to learn the schema vocabulary and typical proportions:
```json
{json.dumps(exemplar, indent=2)}
```
"""

        rules = cls._category_rules(category)

        return f"""You are a precise 3D modelling spec generator.
Output a single JSON object that strictly conforms to the schema below.
Do NOT include any text outside the JSON object.

## JSON Schema
```json
{schema_json}
```

{exemplar_section}
## Dimensional Reference
{dimension_hints}

## Authoring Rules
{rules}
"""

    @classmethod
    def _dimension_hints(cls, category: str) -> str:
        hints = {
            "quadruped": (
                "Dog: body_length_m 0.50–0.90, withers_height_m 0.40–0.65. "
                "Giraffe: body_length_m 1.80–2.40, withers_height_m 4.5–5.5 (scale all joints accordingly). "
                "Joint rx/ry should be proportional to body scale — e.g. 0.06–0.14 for torso, 0.03–0.06 for limbs."
            ),
            "vessel": (
                "Coffee mug: height 0.09–0.12, max radius 0.040–0.055. "
                "Wine glass: height 0.18–0.24, max bowl radius 0.040–0.055, stem radius 0.008–0.012. "
                "Vase: height 0.15–0.40, max radius 0.05–0.15. "
                "wall_thickness 0.003–0.007 for ceramics, 0.002–0.004 for glass."
            ),
            "furniture": (
                "Dining table: length 1.2–2.0m, width 0.75–1.2m, height 0.72–0.78m. "
                "Chair: seat height 0.43–0.48m, seat width 0.44–0.52m, back height 0.85–1.05m total. "
                "Bookshelf: height 1.5–2.0m, width 0.6–1.0m, depth 0.25–0.35m."
            ),
            "vehicle": (
                "Sedan: length 4.0–4.8m, width 1.7–1.9m, height 1.4–1.5m. "
                "Forklift: length 2.5–3.5m, width 1.0–1.3m, height 2.0–2.5m. "
                "Wheel radius 0.20–0.35m for cars, 0.40–0.60m for trucks."
            ),
            "generic": (
                "Use real-world proportions.  Aim for units of meters. "
                "Prefer physically plausible dimensions over arbitrary values."
            ),
        }
        return hints.get(category, hints["generic"])

    @classmethod
    def _category_rules(cls, category: str) -> str:
        base = (
            "- Output ONLY a valid JSON object. No markdown fences, no commentary.\n"
            "- All color fields must be #RRGGBB hex strings (e.g. \"#8B4513\").\n"
            "- All offsets and positions use {\"x\": ..., \"y\": ..., \"z\": ...} objects, not lists.\n"
        )
        if category == "quadruped":
            return base + (
                "- symmetry is always \"x\". Define only LEFT-side joints (_L suffix); "
                "  the compiler mirrors them to the right automatically.\n"
                "- Centerline joints (pelvis, chest, waist, neck, head, snout, nose, tail_*) must have x = 0.0 exactly.\n"
                "- All paw/foot joints must have the same z value (level feet).\n"
                "- Every joint must be connected by at least one bone. No floating joints.\n"
                "- Include at least 15 joints and 14 bones for a realistic quadruped.\n"
                "- branch_smoothing is set by the compiler; you do not need to include it.\n"
            )
        if category == "vessel":
            return base + (
                "- profile is a list of {\"radius\": ..., \"height\": ...} points from bottom to top.\n"
                "- Start with a small base radius and end at the rim — vary the curve for realism.\n"
                "- bottom_closed should be true for cups/mugs/vases; false for a ring or open torus.\n"
                "- For a wine glass, include a narrow stem (radius ~0.009) between bowl and base.\n"
            )
        if category in ("furniture", "vehicle", "tool", "architecture", "generic"):
            return base + (
                "- Use pattern: \"CORNERS\" for table legs, \"WHEEL_POSITIONS\" for car wheels.\n"
                "- relation_type \"ON_TOP_OF\" places the target on top of the parent's bounding box.\n"
                "- relation_type \"INSET\" embeds the target inside the parent by the inset distance.\n"
                "- All offset vectors use x/y/z keys.\n"
            )
        return base

    # ----------------------------------------------------------------
    # LLM call
    # ----------------------------------------------------------------

    @classmethod
    async def _call_llm(
        cls,
        system_prompt: str,
        user_message: str,
        model_manager: Any,
        temperature: float,
    ) -> Optional[str]:
        """Call model_manager or local Ollama directly and return raw text."""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        # 1. If model_manager has a mock generate_async that accepts messages (e.g. unit tests)
        if hasattr(model_manager, "generate_async"):
            try:
                result = await model_manager.generate_async(
                    messages=messages,
                    temperature=temperature,
                    max_tokens=4096,
                )
                if isinstance(result, dict):
                    return result.get("content") or result.get("text") or str(result)
                if result is not None:
                    return str(result)
            except TypeError:
                pass  # Incompatible signature (e.g. real ModelManager), fall through to Ollama call
            except Exception as e:
                logger.warning(f"model_manager.generate_async call failed: {e}")

        # 2. Determine Ollama endpoint and model tag
        ollama_url = getattr(model_manager, "ollama_url", "http://localhost:11434")
        model_tag = "qwen2.5-coder:14b"
        if hasattr(model_manager, "_current_model_id") and model_manager._current_model_id:
            curr = getattr(model_manager, "models_by_id", {}).get(model_manager._current_model_id)
            if curr and curr.get("ollama_tag"):
                model_tag = curr["ollama_tag"]
        elif hasattr(model_manager, "models_by_id") and isinstance(model_manager.models_by_id, dict):
            for preferred in ["qwen2_5_coder_14b", "qwen3_14b_q4", "qwen3_5_9b"]:
                m = model_manager.models_by_id.get(preferred)
                if m and m.get("ollama_tag"):
                    model_tag = m["ollama_tag"]
                    break

        # 3. Call Ollama via async HTTP
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(
                    f"{ollama_url}/api/chat",
                    json={
                        "model": model_tag,
                        "messages": messages,
                        "stream": False,
                        "options": {
                            "temperature": temperature,
                            "num_predict": 4096,
                        },
                        "think": False,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                content = data.get("message", {}).get("content", "")
                content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
                return content
        except Exception as e:
            logger.error(f"SpecPlanner Ollama call failed for {model_tag}: {e}")
            if model_tag != "qwen3:14b-q4_K_M":
                try:
                    async with httpx.AsyncClient(timeout=120.0) as client:
                        resp = await client.post(
                            f"{ollama_url}/api/chat",
                            json={
                                "model": "qwen3:14b-q4_K_M",
                                "messages": messages,
                                "stream": False,
                                "options": {
                                    "temperature": temperature,
                                    "num_predict": 4096,
                                },
                                "think": False,
                            },
                        )
                        resp.raise_for_status()
                        data = resp.json()
                        content = data.get("message", {}).get("content", "")
                        return re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
                except Exception as e2:
                    logger.error(f"SpecPlanner Ollama fallback call failed: {e2}")
            return None

    # ----------------------------------------------------------------
    # Parse + score
    # ----------------------------------------------------------------

    @classmethod
    def _parse_and_score(
        cls,
        raw: str,
        spec_cls,
    ) -> Tuple[Optional[Union[QuadrupedSpec, HardSurfaceSpec, VesselSpec]], float]:
        """Extract JSON from LLM output and validate against spec_cls."""
        json_str = cls._extract_json(raw)
        if not json_str:
            logger.warning("LLM output contained no parseable JSON object")
            return None, 0.0

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.warning(f"JSON parse error: {e}")
            return None, 0.0

        try:
            spec_obj = spec_cls(**data)
        except ValidationError as e:
            logger.warning(f"Pydantic validation failed: {e}")
            # Attempt partial recovery via deterministic repair
            try:
                partial = spec_cls.model_construct(**data)
                partial = apply_deterministic_repairs(partial, [])
                spec_obj = spec_cls(**partial.__dict__)
            except Exception:
                return None, 0.0

        # Tier 1 score
        if isinstance(spec_obj, QuadrupedSpec):
            v_result = SpecVerifier.verify_quadruped(spec_obj)
        elif isinstance(spec_obj, VesselSpec):
            v_result = VerificationResult(valid=True, score=0.85)
        else:
            v_result = SpecVerifier.verify_hard_surface(spec_obj)

        final_score = score_spec(spec_obj, v_result)
        return spec_obj, final_score

    @staticmethod
    def _extract_json(text: str) -> Optional[str]:
        """Extract the first top-level JSON object from LLM output."""
        # Try markdown code fences first
        fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if fence:
            return fence.group(1)
        # Try bare JSON object
        start = text.find("{")
        if start == -1:
            return None
        depth = 0
        for i, ch in enumerate(text[start:], start=start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start:i+1]
        return None

    # ----------------------------------------------------------------
    # Patch helpers
    # ----------------------------------------------------------------

    @classmethod
    async def _ask_for_patch(
        cls,
        spec: Union[QuadrupedSpec, HardSurfaceSpec, VesselSpec],
        errors: List[str],
        model_manager: Any,
    ) -> Optional[Dict[str, Any]]:
        """Ask LLM to return a minimal JSON patch dict fixing the listed errors."""
        error_block = "\n".join(f"- {e}" for e in errors)
        current_json = json.dumps(spec.model_dump(), indent=2)
        system = (
            "You are a JSON patch generator. Given a 3D spec JSON and a list of errors, "
            "output ONLY a flat JSON object whose keys are dot-separated field paths "
            "(e.g. {\"joints.pelvis.x\": 0.0, \"body_length_m\": 0.85}). "
            "No explanation, no markdown fences."
        )
        user = (
            f"Current spec:\n{current_json}\n\n"
            f"Errors to fix:\n{error_block}\n\n"
            "Return the minimal patch JSON:"
        )
        raw = await cls._call_llm(system, user, model_manager, temperature=0.1)
        if not raw:
            return None
        json_str = SpecPlanner._extract_json(raw)
        if not json_str:
            return None
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _apply_json_patch(spec_dict: Dict[str, Any], patch: Dict[str, Any]) -> None:
        """Apply a flat dot-path patch to a nested dict in-place."""
        for path, value in patch.items():
            keys = path.split(".")
            node = spec_dict
            for key in keys[:-1]:
                if isinstance(node, dict) and key in node:
                    node = node[key]
                elif isinstance(node, list):
                    try:
                        node = node[int(key)]
                    except (ValueError, IndexError):
                        break
                else:
                    break
            else:
                last = keys[-1]
                if isinstance(node, dict):
                    node[last] = value
                elif isinstance(node, list):
                    try:
                        node[int(last)] = value
                    except (ValueError, IndexError):
                        pass
