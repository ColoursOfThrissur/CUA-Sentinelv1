"""Blender Assembly Pipeline — Staged Architecture per BLENDER_PIPELINE_BLUEPRINT.md.

This module implements the 5-stage pipeline where:
- Stages 0-3: LLM makes semantic/creative judgments (no raw numbers)
- Stage 4: Pure code computes all numeric transforms
- Stage 5: Targeted feedback on verification failure

The key invariant: NO numeric offset or rotation value that reaches Blender
may come directly from the LLM. Every axis is either computed by code or
derived from a closed-vocabulary semantic hint.
"""

from .stage0_understanding import Stage0Understanding, ObjectUnderstanding
from .stage1_topology import Stage1Topology, PartTopology
from .stage2_dimensions import Stage2Dimensions, DimensionedPart
from .stage3_semantics import Stage3Semantics, AttachmentSemantics
from .stage4_resolver import Stage4Resolver, ShapeBounds
from .orchestrator import StagedPipelineOrchestrator
from .executor import run_staged_pipeline_and_execute, execute_assembly_graph
from .primitive_readback import run_primitive_readback, verify_built_object_dimensions

__all__ = [
    "Stage0Understanding",
    "ObjectUnderstanding",
    "Stage1Topology",
    "PartTopology",
    "Stage2Dimensions",
    "DimensionedPart",
    "Stage3Semantics",
    "AttachmentSemantics",
    "Stage4Resolver",
    "ShapeBounds",
    "StagedPipelineOrchestrator",
    "run_staged_pipeline_and_execute",
    "execute_assembly_graph",
    "run_primitive_readback",
    "verify_built_object_dimensions",
]
