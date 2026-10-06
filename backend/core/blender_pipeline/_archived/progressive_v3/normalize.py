"""Complete component attachment edges before numeric layout.

The planner can omit relations. A missing edge is never interpreted as an
instruction to place the component at the origin. This pass derives an edge
from an explicit parent, from the clause describing the part, or from nearby
component structure. Every inferred edge is recorded for the build trace.
"""
from __future__ import annotations

import re
from dataclasses import replace
from typing import Any

from .intent import IntentComponent, IntentRelation, ModelIntent


def _mentions(sentence: str, component: IntentComponent, *, alias: bool = False) -> bool:
    names = {component.key.replace("_", " "), component.display_label.lower().replace("_", " ")}
    # Natural instructions often shorten "rotor guard" to "guard" in the
    # next sentence. The final noun is a useful alias when unambiguous.
    tail = component.key.split("_")[-1]
    if alias and len(tail) >= 4:
        names.add(tail)
    irregular = {"foot": "feet", "tooth": "teeth"}
    if alias and tail in irregular and re.search(r"\b" + irregular[tail] + r"\b", sentence):
        return True
    for name in names:
        if name and re.search(r"\b" + re.escape(name) + r"(?:s|es)?\b", sentence):
            return True
    return False


class IntentNormalizer:
    @classmethod
    def complete(cls, intent: ModelIntent) -> tuple[ModelIntent, list[dict[str, Any]]]:
        if not intent.components:
            return intent, []
        sentences = [s.strip().lower() for s in re.split(r"[.!?]", intent.prompt) if s.strip()]
        updated_components = []
        for component in intent.components:
            clause = next((s for s in sentences if _mentions(s, component)), "")
            params = dict(component.parameters)
            if component.primitive in {"cylinder", "cone", "capsule"} and "horizontal" in clause and "orientation" not in params:
                params["orientation"] = "horizontal"
            updated_components.append(replace(component, parameters=params))
        intent = replace(intent, components=updated_components)
        components = {component.key: component for component in intent.components}
        root = intent.components[0].key
        relations = [r for r in intent.relations if r.subject in components and r.target in components and r.subject != r.target]
        corrections: list[dict[str, Any]] = []
        attached = {r.subject for r in relations}
        for ordinal, component in enumerate(intent.components):
            if component.key == root or component.key in attached:
                continue
            earlier = intent.components[:ordinal]
            target = components.get(component.parent or "") if component.parent in components else None
            clause = next((s for s in sentences if _mentions(s, component)), "")
            if not clause:
                clause = next((s for s in sentences if _mentions(s, component, alias=True)), "")
            source = "parent" if target else "prompt"
            if target is None and clause:
                matches = [candidate for candidate in earlier if _mentions(clause, candidate, alias=True)]
                if matches:
                    # A repeated part generally attaches to a repeated group
                    # of equal or divisible cardinality, e.g. 12 blades/4 hubs.
                    compatible = [c for c in matches if component.count == c.count or component.count % c.count == 0]
                    target = (compatible or matches)[-1]
            if target is None:
                source = "structure"
                if re.search(r"\b(?:front|rear|back|on top|above|under|underside|below|beneath)\b", clause):
                    target = components[root]
                else:
                    compatible = [c for c in earlier if component.count == c.count]
                    target = compatible[-1] if compatible else (earlier[-1] if earlier else components[root])
            if target.key == component.key:
                target = components[root]
            kind = cls._kind(clause, component.count, target.count)
            if target.key != root and kind in {"front", "back", "above", "below"}:
                # Spatial words can describe the target's location in the
                # sentence rather than the child (e.g. LEDs on a rear battery).
                kind = "center"
            relation = IntentRelation(kind, component.key, target.key, {})
            relations.append(relation)
            corrections.append({"subject": component.key, "target": target.key, "kind": kind, "source": source})
        return replace(intent, relations=relations), corrections

    @staticmethod
    def _kind(clause: str, subject_count: int, target_count: int) -> str:
        if re.search(r"\b(?:outer end|end of each|end of every)\b", clause):
            return "outward"
        if re.search(r"\b(?:under|underside|below|beneath|landing)\b", clause):
            return "below"
        if re.search(r"\b(?:rear|behind|back)\b", clause):
            return "back"
        if re.search(r"\b(?:front|forward)\b", clause):
            return "front"
        if re.search(r"\b(?:on top|above|atop)\b", clause):
            return "above"
        if re.search(r"\b(?:inside|within|in the center|between)\b", clause):
            return "inside"
        if subject_count > 1 and target_count == 1:
            return "radial"
        return "center"
