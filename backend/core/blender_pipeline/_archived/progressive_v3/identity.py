"""V3 identity helpers: display labels are never machine identity."""
from __future__ import annotations
import re
def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", value.lower()).strip("_") or "node"
def canonical_path(parent: str | None, key: str, index: int = 0) -> str:
    return f"{slug(parent) if parent else 'root'}/{slug(key)}[{index}]"
