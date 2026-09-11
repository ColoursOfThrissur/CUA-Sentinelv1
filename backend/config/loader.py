import json
from pathlib import Path

CONFIG_DIR = Path(__file__).parent


def load_system_config() -> dict:
    return json.loads((CONFIG_DIR / "system_config.json").read_text())


def load_policy_rules() -> dict:
    return json.loads((CONFIG_DIR / "policy_rules.json").read_text())


def load_model_registry() -> dict:
    return json.loads((CONFIG_DIR / "models_registry.json").read_text())
