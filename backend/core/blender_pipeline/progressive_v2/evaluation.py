"""Small end-to-end V2 regression baseline and durable eval records."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional


@dataclass(frozen=True)
class EvalCase:
    case_id: str
    prompt: str
    minimum_parts: int
    required_terms: List[str]


BASELINE_CASES: List[EvalCase] = [
    EvalCase("drone_radial", "Build a 0.45 m tabletop surveillance drone with four identical radial arms, torus rotor guards, three blades per rotor, a U camera bracket, lens, battery, LEDs, and four landing feet.", 30, ["arm", "guard", "blade", "camera", "foot"]),
    EvalCase("desk_fan", "Build a detailed 0.35 m desk fan with a stable base, vertical neck, motor housing, five blades, front and rear wire guards, controls, and connected power cable.", 18, ["base", "blade", "guard", "motor"]),
    EvalCase("office_chair", "Build an ergonomic office chair with five caster legs, wheels, gas lift, seat, backrest, two armrests and visible support brackets.", 18, ["seat", "back", "arm", "wheel"]),
    EvalCase("camera", "Build a mirrorless camera with beveled body, grip, interchangeable lens barrel and glass, top dials, shutter button, rear screen, viewfinder and strap lugs.", 14, ["body", "lens", "screen", "viewfinder"]),
    EvalCase("robot_arm", "Build a tabletop six-axis industrial robot arm with bolted base, six connected joints, tapered links, cable covers, wrist and two-finger gripper.", 18, ["base", "joint", "link", "gripper"]),
    EvalCase("lantern", "Build a retro camping lantern with fuel base, control knob, glass chamber, mantle, protective cage, ventilated cap and carry handle.", 14, ["base", "glass", "cage", "handle"]),
    EvalCase("arcade", "Build a detailed tabletop arcade cabinet with beveled shell, inset screen, control deck, joystick, six buttons, speaker grille and rear access panel.", 16, ["cabinet", "screen", "joystick", "button"]),
    EvalCase("bicycle", "Build a simplified but connected bicycle with two wheels and tires, frame triangle, fork, handlebars, saddle, crank, pedals and chain guard.", 20, ["wheel", "frame", "fork", "pedal"]),
    EvalCase("greenhouse", "Build a small architectural greenhouse with foundation, pitched frame, transparent wall and roof panels, hinged door, shelves and planters.", 18, ["frame", "panel", "door", "shelf"]),
    EvalCase("creature", "Build a stylized quadruped robot creature with torso, head, four articulated legs, feet, tail, ears and two emissive eyes; keep bilateral symmetry.", 20, ["torso", "head", "leg", "foot", "eye"]),
]


class V2EvaluationHarness:
    """Run reviewed prompts and retain machine-readable evidence per case."""

    def __init__(self, output_root: Path, visual_reviewer: Optional[Callable[[Any, EvalCase], Awaitable[Dict[str, Any]]]] = None) -> None:
        self.output_root = Path(output_root)
        self.visual_reviewer = visual_reviewer

    async def run(
        self,
        build: Callable[..., Awaitable[Any]],
        *,
        model_manager: Any,
        mcp_manager: Any,
        model_id: Optional[str] = None,
        cases: Optional[List[EvalCase]] = None,
    ) -> Dict[str, Any]:
        run_id = time.strftime("%Y%m%d_%H%M%S", time.gmtime())
        run_dir = self.output_root / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        records: List[Dict[str, Any]] = []
        for case in cases or BASELINE_CASES:
            result = await build(
                prompt=case.prompt,
                model_manager=model_manager,
                mcp_manager=mcp_manager,
                model_id=model_id,
                task_id=f"eval_{run_id}_{case.case_id}",
            )
            record = self.evaluate_result(case, result)
            if self.visual_reviewer is not None and result.success:
                record["visual_review"] = await self.visual_reviewer(result, case)
            else:
                record["visual_review"] = {"status": "not_configured", "pass": None}
            records.append(record)
            self._write(run_dir / f"{case.case_id}.json", record)
        summary = {
            "run_id": run_id,
            "case_count": len(records),
            "passed": sum(1 for item in records if item["pass"]),
            "failed": sum(1 for item in records if not item["pass"]),
            "records": records,
        }
        self._write(run_dir / "summary.json", summary)
        return summary

    @staticmethod
    def evaluate_result(case: EvalCase, result: Any) -> Dict[str, Any]:
        manifest = result.manifest
        parts = [node for node in manifest.nodes.values() if getattr(getattr(node, "kind", None), "value", "") == "part"]
        labels = " ".join(node.label.lower() for node in parts)
        missing_terms = [term for term in case.required_terms if term not in labels]
        readback = manifest.stats.get("scene_readback", {})
        gates = {
            "api_success": bool(result.success),
            "minimum_parts": len(parts) >= case.minimum_parts,
            "required_terms": not missing_terms,
            "readback_verified": readback.get("ok") is True,
            "not_degraded": result.completion_status.value == "success",
        }
        return {
            "case_id": case.case_id,
            "prompt": case.prompt,
            "pass": all(gates.values()),
            "gates": gates,
            "part_count": len(parts),
            "missing_terms": missing_terms,
            "completion_status": result.completion_status.value,
            "errors": list(result.errors),
            "model_id": manifest.model_id,
        }

    @staticmethod
    def _write(path: Path, payload: Dict[str, Any]) -> None:
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        temporary.replace(path)
