"""Per-node LLM stages for progressive assembly.

Unlike v4 which runs stages in batch on all parts upfront,
v5 runs stages per-node during the build loop. This enables:
- Recursive decomposition (new nodes get stages as created)
- Context from already-built siblings/parents
- Incremental progress with checkpointing

Stages:
- Stage 2 (Dimensions): Assigns meters to each part based on scale anchor
- Stage 3 (Semantics): Adds attachment hints (corner_position, edge_offset, etc.)
- Stage 4 (Resolver): Computes exact transforms from parent geometry + semantics

Blueprint references: §11 (per-node stages), §31 (build loop).
"""

from .stage2_dimensions import Stage2Dimensions, Stage2Error
from .stage3_semantics import Stage3Semantics, Stage3Error
from .stage4_resolver import (
    Stage4Resolver,
    Stage4Error,
    ResolvedTransform,
    AttachmentSolution,
)

__all__ = [
    "Stage2Dimensions",
    "Stage2Error",
    "Stage3Semantics",
    "Stage3Error",
    "Stage4Resolver",
    "Stage4Error",
    "ResolvedTransform",
    "AttachmentSolution",
]
