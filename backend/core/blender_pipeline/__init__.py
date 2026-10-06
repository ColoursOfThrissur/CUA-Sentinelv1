"""Primary Blender build entry point (V2; V3 remains experimental)."""

from .progressive_v2 import HierarchyLimits, run_progressive_build

__all__ = [
    "run_progressive_build",
    "HierarchyLimits",
]
