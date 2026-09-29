"""Blender Assembly Pipeline — Progressive v2 Architecture.

This module implements the progressive assembly pipeline where:
- Stages 0-3: LLM makes semantic/creative judgments (no raw numbers)
- Stage 4: Pure code computes all numeric transforms
- Stage 5: Targeted feedback on verification failure

The key invariant: NO numeric offset or rotation value that reaches Blender
may come directly from the LLM. Every axis is either computed by code or
derived from a closed-vocabulary semantic hint.

All builds now route through progressive_v2.
"""

from .progressive_v2 import run_progressive_build, HierarchyLimits

__all__ = [
    "run_progressive_build",
    "HierarchyLimits",
]
