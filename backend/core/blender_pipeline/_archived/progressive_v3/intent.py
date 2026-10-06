"""The small typed contract between V3's one planning call and its compiler."""
from __future__ import annotations
import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

ALLOWED_PRIMITIVES = {"box", "sphere", "cylinder", "cone", "torus", "hemisphere", "u_shape", "capsule", "wedge", "pyramid", "prism", "plane", "circle"}
ALLOWED_RELATIONS = {"radial", "above", "below", "front", "back", "left", "right", "inside", "center", "outward"}

@dataclass(frozen=True)
class IntentRelation:
    kind: str
    subject: str
    target: Optional[str] = None
    parameters: Dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class IntentComponent:
    key: str
    display_label: str
    primitive: str
    parent: Optional[str] = None
    count: int = 1
    material: str = ""
    style: str = ""
    importance: str = "required"
    parameters: Dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class ModelIntent:
    prompt: str
    components: List[IntentComponent]
    relations: List[IntentRelation] = field(default_factory=list)
    overall_extent_m: Optional[float] = None
    confidence: float = 0.0

    @classmethod
    def from_dict(cls, prompt: str, data: Dict[str, Any]) -> "ModelIntent":
        components, seen = [], set()
        for raw in data.get("components", []):
            if not isinstance(raw, dict): continue
            key, primitive = _key(raw.get("key")), str(raw.get("primitive") or "").lower().strip()
            if not key or key in seen:
                raise ValueError(f"invalid or duplicate component key: {key!r}")
            if primitive not in ALLOWED_PRIMITIVES:
                raise ValueError(f"unsupported planned primitive {primitive!r} for {key}")
            seen.add(key)
            try:
                count = int(raw.get("count", 1))
            except (TypeError, ValueError) as exc:
                raise ValueError(f"invalid count for {key}") from exc
            if not 1 <= count <= 400:
                raise ValueError(f"count for {key} must be between 1 and 400")
            importance = str(raw.get("importance") or "required").lower()
            if importance not in {"required", "structural", "optional", "decorative"}: importance = "required"
            components.append(IntentComponent(key, str(raw.get("display_label") or key), primitive, _key(raw.get("parent")) or None, count, str(raw.get("material") or ""), str(raw.get("style") or ""), importance, dict(raw.get("parameters") or {})))
        relations = []
        for raw in data.get("relations", []):
            if not isinstance(raw, dict): continue
            kind, subject = str(raw.get("kind") or "").lower(), _key(raw.get("subject"))
            if kind in ALLOWED_RELATIONS and subject:
                relations.append(IntentRelation(kind, subject, _key(raw.get("target")) or None, dict(raw.get("parameters") or {})))
        try:
            extent = float(data.get("overall_extent_m")); extent = extent if .03 <= extent <= 100 else None
        except (TypeError, ValueError): extent = None
        stated = re.search(r"\b(\d+(?:\.\d+)?)\s*(meters?|metres?|m|centimeters?|centimetres?|cm)\b", prompt, flags=re.I)
        if stated:
            extent = float(stated.group(1)) / (100 if stated.group(2).lower().startswith(("cent", "cm")) else 1)
        try: confidence = float(data.get("confidence", 0.0) or 0.0)
        except (TypeError, ValueError): confidence = 0.0
        return cls(prompt, components, relations, extent, max(0.0, min(1.0, confidence)))

class IntentPlanner:
    """One bounded LLM call; it emits semantics, never executable Blender code."""
    SYSTEM_PROMPT = """You are a mechanical/product 3D design planner. Return ONLY JSON. Describe every visible structural and important functional component, not abstract assemblies. Use only primitives: box,sphere,cylinder,cone,torus,hemisphere,u_shape,capsule,wedge,pyramid,prism,plane,circle. Use explicit count for repeated parts. Every non-root component MUST have one relation that names its target; repeated subject/target counts map one-to-one, while a multiple subject count maps contiguous groups to each target (for example 12 blades to 4 hubs). Relations use radial,above,below,front,back,left,right,inside,center. Parameters may include size:[x,y,z], radius, depth, major_radius, minor_radius, segments. Never create a component that contains itself; do not emit Blender Python. Schema: {overall_extent_m:number,confidence:number,components:[{key,display_label,primitive,count,material,style,importance,parameters}],relations:[{kind,subject,target,parameters}]}"""
    def __init__(self, model_manager: Any, model_id: Optional[str], task_id: str) -> None:
        self.model_manager, self.model_id, self.task_id, self.calls = model_manager, model_id, task_id, 0
        self.attempts: List[Dict[str, Any]] = []
    async def plan(self, prompt: str, stage0_output: Optional[Dict[str, Any]] = None) -> ModelIntent:
        if self.model_manager is None:
            raise RuntimeError("No model manager available for V3 planning")
        model_id = self.model_id or self.model_manager.get_model_for_workflow("ENDPOINT")
        context = "\nStage-0 context (hints only): " + json.dumps(stage0_output, default=str)[:3000] if stage0_output else ""
        try:
            self.calls += 1
            response = await self.model_manager.generate_async(model_id=model_id, task_id=f"v3_plan_{self.task_id}", lease_id="internal", lease_generation=0, system_prompt=self.SYSTEM_PROMPT, prompt="Create a manufacturable, visually recognizable 3D component plan for:\n" + prompt + context, temperature=.15)
            self.attempts.append({"phase": "plan", "response": str(response)})
            intent = ModelIntent.from_dict(prompt, _json_object(response))
            if intent.components: return intent
            raise ValueError("planner returned no supported components")
        except Exception as exc:
            self.attempts.append({"phase": "plan_error", "error": str(exc)})
            raise RuntimeError(f"V3 planning failed: {exc}") from exc
    async def repair(self, prompt: str, prior: ModelIntent, audit_errors: List[str]) -> Optional[ModelIntent]:
        """Ask once for a corrected semantic plan after deterministic audit failure.

        Blender has not been touched at this point.  The request is deliberately
        constrained to placement/cardinality repair, so it cannot turn into the
        former recursive decomposition loop.
        """
        if self.model_manager is None:
            return None
        model_id = self.model_id or self.model_manager.get_model_for_workflow("ENDPOINT")
        prior_payload = {
            "overall_extent_m": prior.overall_extent_m,
            "components": [c.__dict__ for c in prior.components],
            "relations": [r.__dict__ for r in prior.relations],
        }
        repair_prompt = (
            "Repair this V3 scene intent. Keep all requested components and counts. "
            "Every repeated component must have a relation to the corresponding "
            "repeated target; use radial for equal angular slots or repeated groups. "
            "Return a complete replacement JSON object in the original schema only.\n"
            f"Original request:\n{prompt}\n"
            f"Audit errors:\n{json.dumps(audit_errors)}\n"
            f"Prior intent:\n{json.dumps(prior_payload)}"
        )
        try:
            self.calls += 1
            response = await self.model_manager.generate_async(
                model_id=model_id, task_id=f"v3_repair_{self.task_id}", lease_id="internal", lease_generation=0,
                system_prompt=self.SYSTEM_PROMPT, prompt=repair_prompt, temperature=.05,
            )
            self.attempts.append({"phase": "repair", "response": str(response)})
            repaired = ModelIntent.from_dict(prompt, _json_object(response))
            previous = {component.key: component.count for component in prior.components}
            current = {component.key: component.count for component in repaired.components}
            lost = {key: count for key, count in previous.items() if current.get(key, 0) < count}
            if lost:
                self.attempts.append({"phase": "repair_rejected", "lost_components": lost})
                return None
            return repaired if repaired.components else None
        except Exception as exc:
            self.attempts.append({"phase": "repair_error", "error": str(exc)})
            return None
def _key(value: Any) -> str: return re.sub(r"[^a-z0-9_]+", "_", str(value or "").lower()).strip("_")
def _json_object(response: Any) -> Dict[str, Any]:
    text = response if isinstance(response, str) else getattr(response, "text", None) or str(response)
    text = re.sub(r"^\s*```(?:json)?|```\s*$", "", text.strip(), flags=re.I | re.M)
    start = text.find("{")
    if start < 0: raise ValueError("planner did not return JSON")
    value, _ = json.JSONDecoder().raw_decode(text[start:])
    if not isinstance(value, dict): raise ValueError("planner root must be an object")
    return value
