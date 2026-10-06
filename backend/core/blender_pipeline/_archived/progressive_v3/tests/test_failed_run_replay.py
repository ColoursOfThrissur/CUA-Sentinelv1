"""Regression for the October 4 drone build that collapsed repeated parts."""
from core.blender_pipeline.progressive_v3.audit import SceneAudit
from core.blender_pipeline.progressive_v3.compiler import IntentCompiler
from core.blender_pipeline.progressive_v3.executor import V3Executor
from core.blender_pipeline.progressive_v3.intent import ModelIntent
from core.blender_pipeline.progressive_v3.normalize import IntentNormalizer
from core.blender_pipeline.progressive_v3.verifier import V3Preflight
import pytest


def test_missing_relations_do_not_collapse_drone_parts() -> None:
    prompt = (
        "Build a 0.45 meter drone chassis. Attach four identical horizontal cylindrical arms "
        "radially to the chassis. At the outer end of every arm attach a rotor guard. "
        "Put a hub in every guard and three blades around each hub. "
        "On the rear add a battery module with two indicator LEDs. "
        "Add four landing feet below the chassis."
    )
    data = {
        "overall_extent_m": .45,
        "components": [
            {"key": "chassis", "primitive": "box", "parameters": {"size": [.22, .16, .07]}},
            {"key": "arm", "primitive": "cylinder", "count": 4},
            {"key": "rotor_guard", "primitive": "torus", "count": 4},
            {"key": "rotor_hub", "primitive": "sphere", "count": 4},
            {"key": "propeller_blade", "primitive": "cone", "count": 12},
            {"key": "battery_module", "primitive": "box"},
            {"key": "led_indicator", "primitive": "sphere", "count": 2},
            {"key": "landing_foot", "primitive": "cylinder", "count": 4},
        ],
        "relations": [
            {"kind": "radial", "subject": "arm", "target": "chassis", "parameters": {"radius": .153}},
            {"kind": "center", "subject": "rotor_hub", "target": "rotor_guard"},
            {"kind": "radial", "subject": "propeller_blade", "target": "rotor_hub", "parameters": {"radius": .153}},
            {"kind": "below", "subject": "landing_foot", "target": "chassis"},
        ],
    }
    intent, inferred = IntentNormalizer.complete(ModelIntent.from_dict(prompt, data))
    assert {item["subject"] for item in inferred} >= {"rotor_guard", "battery_module", "led_indicator"}
    manifest = IntentCompiler.compile(intent, "v3_regression_drone")
    assert len(manifest.get_parts()) == 32
    assert V3Preflight.run(manifest)["passed"]
    assert SceneAudit.run(manifest)["passed"]
    script = V3Executor(None, "v3_regression_task").render(manifest)
    compile(script, "<v3-blender-transaction>", "exec")

    def slots(key: str) -> set[tuple[float, float, float]]:
        return {
            tuple(round(v, 5) for v in node.transform.position)
            for node in manifest.get_parts()
            if node.component_key == key
        }

    assert len(slots("rotor_guard")) == 4
    assert len(slots("propeller_blade")) == 12
    assert len(slots("landing_foot")) == 4


def test_planner_cannot_silently_drop_unsupported_parts() -> None:
    with pytest.raises(ValueError, match="unsupported planned primitive"):
        ModelIntent.from_dict("a model", {"components": [
            {"key": "body", "primitive": "box"},
            {"key": "crucial_surface", "primitive": "nurbs"},
        ]})


def test_planner_cannot_silently_reduce_part_count() -> None:
    intent = ModelIntent.from_dict("a model", {"components": [
        {"key": "rivets", "primitive": "sphere", "count": 40},
    ]})
    assert intent.components[0].count == 40
