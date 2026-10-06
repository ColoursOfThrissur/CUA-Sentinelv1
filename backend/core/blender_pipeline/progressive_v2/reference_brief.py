"""Bounded visual-reference research for a modelling plan.

This deliberately turns web/model knowledge into a small structured contract.
Raw search text is never forwarded to the geometry stages.
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


REFERENCE_SYSTEM_PROMPT = """You are preparing a safe visual reference brief for a 3D modeller.
Return ONLY JSON with: shape_rules (array of concise strings), palette (object mapping material role to color name),
material_roles (object mapping role to concise PBR intent), proportion_rules (array of concise ratio/placement rules),
component_profiles (object), research_confidence (0..1), and scale_evidence (object or null).

component_profiles maps a user-mentioned component whose design depends on its
host/context (for example a camera mounted on a drone) to an object with
design_class, context, form_rules (array), scale_relation, material_role, and
confidence. Infer a plausible generic class from the complete user request
("drone camera" may be an action/gimbal camera); do not claim a make/model or
exact dimensions unless supplied evidence names it. Keep it to four entries.

scale_evidence may contain overall_extent_m (number), confidence (0..1), reasoning (short string),
and source_indexes (array of zero-based source indexes). Set it only when the supplied evidence explicitly
supports the named object and at least two independent sources agree. Never derive measurements from a
generic category, and never invent a brand, number, or source. Respect user instructions over references."""


@dataclass(frozen=True)
class ReferenceBrief:
    category: str
    shape_rules: List[str] = field(default_factory=list)
    palette: Dict[str, str] = field(default_factory=dict)
    material_roles: Dict[str, str] = field(default_factory=dict)
    proportion_rules: List[str] = field(default_factory=list)
    component_profiles: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    sources: List[Dict[str, str]] = field(default_factory=list)
    research_confidence: float = 0.0
    source: str = "fallback"
    scale_evidence: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def fallback(cls, prompt: str, stage0: Optional[Dict[str, Any]]) -> "ReferenceBrief":
        text = prompt.lower()
        category = str((stage0 or {}).get("category") or "unspecified")
        palette = {"body": "neutral gray"}
        if any(c in text for c in ("red", "blue", "green", "black", "white", "yellow")):
            palette["body"] = next(c for c in ("red", "blue", "green", "black", "white", "yellow") if c in text)
        material = "matte ABS plastic; metallic 0.0; roughness 0.45"
        if "metal" in text or "steel" in text or "aluminum" in text:
            material = "brushed metal; metallic 0.8; roughness 0.3"
        return cls(
            category=category,
            shape_rules=["Use a clean, readable silhouette and avoid unnecessary micro-detail."],
            palette=palette,
            material_roles={"body": material},
            proportion_rules=["All component dimensions must remain proportions of the single model-scale anchor."],
            source="fallback",
        )


class ReferenceBriefGenerator:
    """Research once, synthesize once, then pass only a validated brief onward."""

    @classmethod
    async def run(
        cls, prompt: str, stage0: Optional[Dict[str, Any]], model_manager: Any,
        task_id: str, model_id: Optional[str] = None, use_web: bool = True,
    ) -> ReferenceBrief:
        fallback = ReferenceBrief.fallback(prompt, stage0)
        sources: List[Dict[str, str]] = []
        if use_web:
            try:
                from tools.web_search import WebSearchTool
                category = fallback.category.replace("_", " ")
                def is_high_confidence_target(item: Any) -> bool:
                    if not isinstance(item, dict) or not isinstance(item.get("name"), str):
                        return False
                    try:
                        return float(item.get("confidence", 0) or 0) >= 0.85
                    except (TypeError, ValueError):
                        return False

                targets = [item for item in (stage0 or {}).get("reference_targets", [])
                           if is_high_confidence_target(item)]
                if not targets:
                    target = str((stage0 or {}).get("reference_target") or "").strip()
                    try:
                        target_confidence = float((stage0 or {}).get("reference_target_confidence") or 0.0)
                    except (TypeError, ValueError):
                        target_confidence = 0.0
                    if target and target_confidence >= 0.85:
                        targets = [{"name": target, "scope": "model", "context": "primary object", "confidence": target_confidence}]

                # Research only supplied identities.  Otherwise use one
                # composition query for visual guidance; generic web results
                # are deliberately ineligible to override the scale contract.
                queries = (
                    [f"{item['name']} dimensions specifications materials colours {item.get('context', '')}" for item in targets[:3]]
                    if targets else
                    [f"{category if category != 'unspecified' else prompt} product design materials colors proportions"]
                )
                raw = []
                for query in queries:
                    raw.extend(await asyncio.to_thread(WebSearchTool().search_structured, query, 3))
                from core.scraper_sanitizer import scraper_sanitizer
                seen_urls = set()
                for item in raw[:6]:
                    if not item.get("title"):
                        continue
                    url = str(item.get("url", ""))[:500]
                    if not url or url in seen_urls:
                        continue
                    seen_urls.add(url)
                    excerpt, _, _ = scraper_sanitizer.sanitize_text(str(item.get("snippet", ""))[:500])
                    sources.append({
                        "title": str(item.get("title", ""))[:180],
                        "url": url,
                        "source": str(item.get("source", ""))[:100],
                        "excerpt": excerpt[:500],
                    })
            except Exception:
                # Research is enrichment, never a build dependency.
                sources = []

        evidence = "\n".join(
            f"- {s['title']} ({s['source']}): {s.get('excerpt', '')}" for s in sources
        ) or "No external references available."
        try:
            mid = model_id or model_manager.get_model_for_workflow("ENDPOINT")
            response = await model_manager.generate_async(
                model_id=mid, task_id=f"reference_{task_id}", lease_id="internal", lease_generation=0,
                system_prompt=REFERENCE_SYSTEM_PROMPT,
                prompt=(f"User request: {prompt}\nStage 0: {json.dumps(stage0 or {}, default=str)}\n"
                        f"Sanitized search titles only:\n{evidence}"), temperature=0.1,
            )
            data = cls._extract_json(response)
            return cls._validated(data, fallback, sources, "web+model" if sources else "model")
        except Exception:
            return fallback

    @staticmethod
    def _extract_json(text: str) -> Dict[str, Any]:
        match = re.search(r"\{[\s\S]*\}", text or "")
        return json.loads(match.group(0)) if match else {}

    @classmethod
    def _validated(cls, data: Dict[str, Any], fallback: ReferenceBrief, sources: List[Dict[str, str]], source: str) -> ReferenceBrief:
        def strings(value: Any, limit: int) -> List[str]:
            return [str(v)[:240] for v in value if isinstance(v, str)][:limit] if isinstance(value, list) else []
        def mapping(value: Any, limit: int) -> Dict[str, str]:
            if not isinstance(value, dict):
                return {}
            return {str(k)[:60]: str(v)[:180] for k, v in list(value.items())[:limit]}
        try:
            confidence = min(1.0, max(0.0, float(data.get("research_confidence", 0.0))))
        except (TypeError, ValueError):
            confidence = 0.0
        scale_evidence = cls._validated_scale_evidence(data.get("scale_evidence"), sources)
        return ReferenceBrief(
            category=fallback.category,
            shape_rules=strings(data.get("shape_rules"), 8) or fallback.shape_rules,
            palette=mapping(data.get("palette"), 8) or fallback.palette,
            material_roles=mapping(data.get("material_roles"), 8) or fallback.material_roles,
            proportion_rules=strings(data.get("proportion_rules"), 8) or fallback.proportion_rules,
            component_profiles=cls._component_profiles(data.get("component_profiles")),
            sources=sources,
            research_confidence=confidence,
            source=source,
            scale_evidence=scale_evidence,
        )

    @staticmethod
    def _component_profiles(value: Any) -> Dict[str, Dict[str, Any]]:
        """Keep contextual component intent compact, typed, and prompt-safe."""
        if not isinstance(value, dict):
            return {}
        profiles: Dict[str, Dict[str, Any]] = {}
        for raw_name, raw_profile in list(value.items())[:4]:
            if not isinstance(raw_name, str) or not isinstance(raw_profile, dict):
                continue
            name = raw_name.strip().lower()[:60]
            design_class = raw_profile.get("design_class")
            if not name or not isinstance(design_class, str) or not design_class.strip():
                continue
            try:
                confidence = min(1.0, max(0.0, float(raw_profile.get("confidence", 0.0))))
            except (TypeError, ValueError):
                confidence = 0.0
            form_rules = raw_profile.get("form_rules")
            profiles[name] = {
                "design_class": design_class.strip()[:100],
                "context": str(raw_profile.get("context") or "")[:180],
                "form_rules": [str(rule)[:180] for rule in form_rules[:5]] if isinstance(form_rules, list) else [],
                "scale_relation": str(raw_profile.get("scale_relation") or "")[:180],
                "material_role": str(raw_profile.get("material_role") or "")[:120],
                "confidence": confidence,
            }
        return profiles

    @staticmethod
    def _validated_scale_evidence(value: Any, sources: List[Dict[str, str]]) -> Dict[str, Any]:
        """Accept scale only with two cited, in-range external sources.

        This is intentionally conservative: it prevents an LLM from turning a
        generic visual reference into a false exact measurement.
        """
        if not isinstance(value, dict):
            return {}
        try:
            extent = float(value.get("overall_extent_m"))
            confidence = float(value.get("confidence"))
        except (TypeError, ValueError):
            return {}
        indexes = value.get("source_indexes")
        if (
            not 0.001 <= extent <= 10000
            or confidence < 0.8
            or not isinstance(indexes, list)
            or len(set(indexes)) < 2
            or not all(isinstance(index, int) and 0 <= index < len(sources) for index in indexes)
        ):
            return {}
        return {
            "overall_extent_m": extent,
            "confidence": min(1.0, confidence),
            "reasoning": str(value.get("reasoning") or "cross-checked external product references")[:240],
            "source_indexes": sorted(set(indexes)),
        }
