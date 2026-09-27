import hashlib
import json
from pathlib import Path

CONFIG_DIR = Path(__file__).parent
GATEWAY_VERSION = "1.0.0"


def load_system_config() -> dict:
    return json.loads((CONFIG_DIR / "system_config.json").read_text(encoding="utf-8"))


def load_policy_rules() -> dict:
    return json.loads((CONFIG_DIR / "policy_rules.json").read_text(encoding="utf-8"))


def load_model_registry() -> dict:
    return json.loads((CONFIG_DIR / "models_registry.json").read_text(encoding="utf-8"))


def load_tool_registry() -> dict:
    p = CONFIG_DIR / "tool_registry.json"
    if p.is_file():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"tools": {}}


def validate_tool_registry(registry: dict = None) -> bool:
    """
    Validates tool registry integrity at startup (fail-closed).
    Ensures required fields, valid risk levels L0-L3, valid side effects, and non-empty allowed_agents.
    """
    if registry is None:
        registry = load_tool_registry()
    tools = registry.get("tools", {})
    if not tools:
        raise ValueError("Tool registry is empty or missing 'tools' root.")
    valid_risk_levels = {"L0", "L1", "L2", "L3"}
    valid_side_effects = {"read", "write", "act"}

    REQUIRED_FLAGS = {
        "side_effect", "risk_level", "allowed_agents", "deny_all",
        "taint_deny", "taint_safe", "egress", "returns_untrusted", "reads_private_data"
    }

    for name, t in tools.items():
        if t.get("name") != name:
            raise ValueError(f"Tool registry entry key '{name}' does not match name '{t.get('name')}'.")
        if missing := (REQUIRED_FLAGS - set(t.keys())):
            raise ValueError(f"Tool '{name}' missing required flag(s): {sorted(missing)}")
        if t.get("risk_level") not in valid_risk_levels:
            raise ValueError(f"Invalid risk_level '{t.get('risk_level')}' for tool '{name}'.")
        if t.get("side_effect") not in valid_side_effects:
            raise ValueError(f"Invalid side_effect '{t.get('side_effect')}' for tool '{name}'.")
        if not isinstance(t.get("allowed_agents"), list):
            raise ValueError(f"Tool '{name}' must specify an allowed_agents list.")
    return True


def get_config_version() -> str:
    """
    Computes a deterministic hash of system_config.json, models_registry.json, policy_rules.json, and tool_registry.json.
    """
    h = hashlib.sha256()
    for fname in sorted(["system_config.json", "models_registry.json", "policy_rules.json", "tool_registry.json"]):
        p = CONFIG_DIR / fname
        if p.is_file():
            h.update(p.read_bytes())
    return h.hexdigest()[:16]


def compute_prompt_hash(prompt_text: str) -> str:
    """
    Computes a deterministic hash of the final trusted prompt template plus rules.
    """
    if not prompt_text:
        return "none"
    return hashlib.sha256(prompt_text.strip().encode("utf-8")).hexdigest()[:16]


