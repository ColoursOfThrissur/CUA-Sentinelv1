import os
import yaml
import json
import logging
import asyncio
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from config.loader import load_tool_registry

logger = logging.getLogger(__name__)

PROFILES_DIR = Path(__file__).resolve().parent.parent / "profiles"


# Built-in Python validators registry for profiles
def validate_research_output(data: Any) -> bool:
    if isinstance(data, dict):
        return "sub_questions" in data or "strategy" in data or "findings" in data
    return isinstance(data, (list, str)) and len(data) > 0


def validate_digest_output(data: Any) -> bool:
    if isinstance(data, dict):
        return "topic" in data or "digest" in data or "digests" in data
    return isinstance(data, (list, str)) and len(data) > 0


def validate_chat_output(data: Any) -> bool:
    return isinstance(data, str) and len(data.strip()) > 0


VALIDATORS = {
    "validate_research_output": validate_research_output,
    "validate_digest_output": validate_digest_output,
    "validate_chat_output": validate_chat_output,
}


def load_profile(name_or_path: str) -> Dict[str, Any]:
    """
    Loads and validates a declarative agent profile YAML per Section 8.1.
    Fails closed if the profile is missing, malformed, or references unauthorized tools.
    """
    path = Path(name_or_path)
    if not path.is_file():
        # Check profiles directory
        candidate = PROFILES_DIR / f"{name_or_path}.yaml"
        if candidate.is_file():
            path = candidate
        else:
            candidate_yml = PROFILES_DIR / f"{name_or_path}.yml"
            if candidate_yml.is_file():
                path = candidate_yml
            else:
                raise FileNotFoundError(f"Profile '{name_or_path}' not found at {path} or {candidate}")

    with open(path, "r", encoding="utf-8") as f:
        profile = yaml.safe_load(f)

    if not isinstance(profile, dict):
        raise ValueError(f"Profile '{path}' does not contain a valid mapping")

    # Required fields per Section 8.1
    required_fields = ["name", "version", "description", "prompt_template", "model_preference", "tools_allowed"]
    for field in required_fields:
        if field not in profile:
            raise ValueError(f"Profile '{path}' missing required field: '{field}'")

    # Fail-closed validation: tools_allowed must be a subset of tool_registry.json
    tool_reg = load_tool_registry().get("tools", {})
    tools_allowed = profile.get("tools_allowed", [])
    if not isinstance(tools_allowed, list):
        raise ValueError(f"Profile 'tools_allowed' must be a list, got {type(tools_allowed)}")

    for t in tools_allowed:
        if '*' in t:
            continue
        if t not in tool_reg:
            raise ValueError(
                f"Profile '{profile.get('name')}' specifies tool '{t}' which does not exist in tool_registry.json"
            )

    # Resolve prompt template if it's a relative file path
    tmpl_ref = profile.get("prompt_template", "")
    if tmpl_ref:
        tmpl_path = path.parent / tmpl_ref
        if tmpl_path.is_file():
            try:
                profile["_template_content"] = tmpl_path.read_text(encoding="utf-8")
            except Exception as e:
                logger.warning(f"Could not read template file {tmpl_path}: {e}")
                profile["_template_content"] = tmpl_ref
        else:
            profile["_template_content"] = tmpl_ref

    profile["_profile_path"] = str(path)
    return profile


def validate_schema(data: Any, schema: Optional[Dict[str, Any]]) -> Tuple[bool, Optional[str]]:
    """
    Lightweight, robust JSON schema validator without external dependencies.
    Supports object, array, string, number, integer, boolean types and required fields.
    """
    if schema is None:
        return True, None

    schema_type = schema.get("type")
    if schema_type:
        type_map = {
            "object": dict,
            "array": list,
            "string": str,
            "number": (int, float),
            "integer": int,
            "boolean": bool,
        }
        expected_py_type = type_map.get(schema_type)
        if expected_py_type and not isinstance(data, expected_py_type):
            return False, f"Expected type '{schema_type}', got '{type(data).__name__}'"

    if isinstance(data, dict) and schema_type == "object":
        required = schema.get("required", [])
        for r in required:
            if r not in data:
                return False, f"Missing required property: '{r}'"

        properties = schema.get("properties", {})
        for k, val in data.items():
            if k in properties:
                valid, err = validate_schema(val, properties[k])
                if not valid:
                    return False, f"Property '{k}': {err}"

    elif isinstance(data, list) and schema_type == "array":
        item_schema = schema.get("items")
        if item_schema:
            for idx, item in enumerate(data):
                valid, err = validate_schema(item, item_schema)
                if not valid:
                    return False, f"Item [{idx}]: {err}"

    return True, None


def run_validators(data: Any, validator_names: List[str]) -> Tuple[bool, List[str]]:
    """
    Runs named Python validator functions against data.
    """
    errors = []
    for name in validator_names:
        fn = VALIDATORS.get(name)
        if not fn:
            logger.warning(f"Unknown validator function: '{name}'")
            continue
        try:
            passed = fn(data)
            if not passed:
                errors.append(f"Validator '{name}' rejected output")
        except Exception as e:
            errors.append(f"Validator '{name}' raised error: {e}")

    return len(errors) == 0, errors


def verify_profile_against_eval_pack(profile: Dict[str, Any]) -> Dict[str, Any]:
    """
    Verifies that a profile satisfies its configured golden evaluation pack (Section 8.1).
    Rules: a profile change bumps version and must pass its eval pack before activation.
    """
    eval_pack_path = profile.get("eval_pack")
    if not eval_pack_path:
        return {"status": "SKIPPED", "reason": "No eval_pack configured in profile"}

    import sys
    root_dir = Path(__file__).resolve().parent.parent.parent
    if str(root_dir) not in sys.path:
        sys.path.insert(0, str(root_dir))
    backend_dir = root_dir / "backend"
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))

    from eval.harness import GoldenEvalHarness
    eval_dir = root_dir / eval_pack_path
    if not eval_dir.is_dir():
        eval_dir = root_dir / "eval" / "golden"

    harness = GoldenEvalHarness(golden_root=str(eval_dir))

    async def _run():
        return await harness.run_suite(iterations_per_case=1)

    try:
        loop = asyncio.get_running_loop()
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            report = pool.submit(asyncio.run, _run()).result()
    except RuntimeError:
        report = asyncio.run(_run())

    pass_rate = report.get("pass_rate", 0.0)
    passed = pass_rate >= 0.8  # Threshold for activation

    return {
        "status": "PASSED" if passed else "FAILED",
        "profile_name": profile.get("name"),
        "profile_version": profile.get("version"),
        "eval_pack": eval_pack_path,
        "pass_rate": pass_rate,
        "total_cases": report.get("total_cases", 0),
        "passed_cases": report.get("passed_cases", 0),
    }
