"""Staged Pipeline Orchestrator — Runs Stages 0-4 in sequence.

This is the main entry point for the new staged pipeline.
It replaces the single-shot GraphCompiler.compile_from_prompt() approach.

Stage Numbering:
    Orchestrator (this file):     Stages 0-4 (LLM + deterministic resolution)
    Executor (executor.py):       Stages 5-6 (Blender execution + verification)
    
    Note: The BLENDER_PIPELINE_BLUEPRINT.md refers to a "Stage 5: Targeted Feedback"
    which is NOT yet implemented. If added, it would be a retry loop within the
    orchestrator, not a new numbered stage in the executor.
"""

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional, Tuple, TypeVar

# Max retry attempts per LLM stage (Stages 0-3)
MAX_STAGE_RETRIES = 2

from core.assembly_spec import AssemblyGraph
from .broadcast import broadcast_blender_trace

from .stage0_understanding import Stage0Understanding, ObjectUnderstanding, Stage0Error
from .stage1_topology import Stage1Topology, PartTopology, Stage1Error
from .stage2_dimensions import Stage2Dimensions, Stage2Output, Stage2Error
from .stage3_semantics import Stage3Semantics, Stage3Output, Stage3Error
from .stage4_resolver import Stage4Resolver, Stage4Error

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    """Result of running the staged pipeline."""
    success: bool
    graph: Optional[AssemblyGraph] = None
    error: Optional[str] = None
    failed_stage: Optional[int] = None
    retry_count: int = 0  # Total retries across all stages
    
    # Intermediate outputs for debugging/feedback
    stage0_output: Optional[dict] = None
    stage1_output: Optional[dict] = None
    stage2_output: Optional[dict] = None
    stage3_output: Optional[dict] = None


T = TypeVar('T')


async def _run_with_retry(
    stage_fn: Callable[..., T],
    stage_num: int,
    stage_name: str,
    task_id: str,
    error_class: type,
    **kwargs,
) -> Tuple[T, int]:
    """Run a stage function with bounded retries.
    
    Returns:
        Tuple of (result, retry_count)
    Raises:
        The stage's error class if all retries exhausted
    """
    last_error = None
    for attempt in range(MAX_STAGE_RETRIES + 1):
        try:
            if attempt > 0:
                logger.info(f"[{task_id}] Stage {stage_num} retry {attempt}/{MAX_STAGE_RETRIES}")
                await broadcast_blender_trace(
                    task_id, stage_num, stage_name, "retrying",
                    {"attempt": attempt + 1, "max_attempts": MAX_STAGE_RETRIES + 1, "last_error": str(last_error)}
                )
                # Add rejection feedback to kwargs for retry
                kwargs["rejection_feedback"] = str(last_error)
            
            # Pass task_id to the stage function
            result = await stage_fn(task_id=task_id, **kwargs)
            return result, attempt
        except error_class as e:
            last_error = e
            if attempt >= MAX_STAGE_RETRIES:
                raise
        except Exception:
            # Don't retry unexpected errors
            raise
    
    # Should not reach here, but satisfy type checker
    raise last_error


class StagedPipelineOrchestrator:
    """Orchestrates the 5-stage Blender assembly pipeline.
    
    Usage:
        result = await StagedPipelineOrchestrator.run(
            prompt="A training dummy with horizontal arm",
            model_manager=model_manager,
            task_id="task_123",
        )
        if result.success:
            graph = result.graph
            # Proceed to Blender build and verification
    """
    
    @classmethod
    async def run(
        cls,
        prompt: str,
        model_manager: Any,
        task_id: Optional[str] = None,
        model_id: Optional[str] = None,
    ) -> PipelineResult:
        """Run the full staged pipeline.
        
        Args:
            prompt: User's natural language description of the object
            model_manager: Model manager for LLM calls
            task_id: Optional task ID (generated if not provided)
            model_id: Optional specific model to use for all stages
            
        Returns:
            PipelineResult with the AssemblyGraph or error details
        """
        tid = task_id or f"staged_{uuid.uuid4().hex[:8]}"
        
        result = PipelineResult(success=False)
        
        # ===== STAGE 0: Object Understanding =====
        logger.info(f"[{tid}] Stage 0: Object Understanding")
        await broadcast_blender_trace(tid, 0, "Object Understanding", "running")
        try:
            stage0, retries = await _run_with_retry(
                Stage0Understanding.run,
                stage_num=0,
                stage_name="Object Understanding",
                task_id=tid,
                error_class=Stage0Error,
                # kwargs for Stage0Understanding.run:
                prompt=prompt,
                model_manager=model_manager,
                model_id=model_id,
            )
            result.retry_count += retries
            result.stage0_output = stage0.to_dict()
            logger.info(
                f"[{tid}] Stage 0 complete: category={stage0.category}, "
                f"scale={stage0.scale_anchor.overall_height_or_length_m}m"
            )
            await broadcast_blender_trace(tid, 0, "Object Understanding", "complete", {
                "category": stage0.category, "scale_m": stage0.scale_anchor.overall_height_or_length_m
            })
        except Stage0Error as e:
            logger.error(f"[{tid}] Stage 0 failed after {MAX_STAGE_RETRIES} retries: {e}")
            await broadcast_blender_trace(tid, 0, "Object Understanding", "failed", {"error": str(e)})
            result.error = f"Stage 0 (Understanding) failed: {e}"
            result.failed_stage = 0
            return result
        except Exception as e:
            logger.exception(f"[{tid}] Stage 0 unexpected error")
            await broadcast_blender_trace(tid, 0, "Object Understanding", "failed", {"error": str(e)})
            result.error = f"Stage 0 unexpected error: {e}"
            result.failed_stage = 0
            return result
        
        # ===== STAGE 1: Part Topology =====
        logger.info(f"[{tid}] Stage 1: Part Topology")
        await broadcast_blender_trace(tid, 1, "Part Topology", "running")
        try:
            stage1, retries = await _run_with_retry(
                Stage1Topology.run,
                stage_num=1,
                stage_name="Part Topology",
                task_id=tid,
                error_class=Stage1Error,
                # kwargs for Stage1Topology.run:
                prompt=prompt,
                stage0_output=result.stage0_output,
                model_manager=model_manager,
                model_id=model_id,
            )
            result.retry_count += retries
            result.stage1_output = stage1.to_dict()
            logger.info(f"[{tid}] Stage 1 complete: {len(stage1.parts)} parts")
            await broadcast_blender_trace(tid, 1, "Part Topology", "complete", {
                "parts_count": len(stage1.parts), "parts": [p.label for p in stage1.parts]
            })
        except Stage1Error as e:
            logger.error(f"[{tid}] Stage 1 failed after {MAX_STAGE_RETRIES} retries: {e}")
            await broadcast_blender_trace(tid, 1, "Part Topology", "failed", {"error": str(e)})
            result.error = f"Stage 1 (Topology) failed: {e}"
            result.failed_stage = 1
            return result
        except Exception as e:
            logger.exception(f"[{tid}] Stage 1 unexpected error")
            await broadcast_blender_trace(tid, 1, "Part Topology", "failed", {"error": str(e)})
            result.error = f"Stage 1 unexpected error: {e}"
            result.failed_stage = 1
            return result
        
        # ===== STAGE 2: Dimension Assignment =====
        logger.info(f"[{tid}] Stage 2: Dimension Assignment")
        await broadcast_blender_trace(tid, 2, "Dimension Assignment", "running")
        try:
            stage2, retries = await _run_with_retry(
                Stage2Dimensions.run,
                stage_num=2,
                stage_name="Dimension Assignment",
                task_id=tid,
                error_class=Stage2Error,
                # kwargs for Stage2Dimensions.run:
                stage0_output=result.stage0_output,
                stage1_output=result.stage1_output,
                model_manager=model_manager,
                model_id=model_id,
            )
            result.retry_count += retries
            result.stage2_output = stage2.to_dict()
            logger.info(f"[{tid}] Stage 2 complete: dimensions assigned")
            await broadcast_blender_trace(tid, 2, "Dimension Assignment", "complete", {
                "scale_anchor_m": stage2.scale_anchor_m
            })
        except Stage2Error as e:
            logger.error(f"[{tid}] Stage 2 failed after {MAX_STAGE_RETRIES} retries: {e}")
            await broadcast_blender_trace(tid, 2, "Dimension Assignment", "failed", {"error": str(e)})
            result.error = f"Stage 2 (Dimensions) failed: {e}"
            result.failed_stage = 2
            return result
        except Exception as e:
            logger.exception(f"[{tid}] Stage 2 unexpected error")
            await broadcast_blender_trace(tid, 2, "Dimension Assignment", "failed", {"error": str(e)})
            result.error = f"Stage 2 unexpected error: {e}"
            result.failed_stage = 2
            return result
        
        # ===== STAGE 3: Attachment Semantics =====
        logger.info(f"[{tid}] Stage 3: Attachment Semantics")
        await broadcast_blender_trace(tid, 3, "Attachment Semantics", "running")
        try:
            stage3, retries = await _run_with_retry(
                Stage3Semantics.run,
                stage_num=3,
                stage_name="Attachment Semantics",
                task_id=tid,
                error_class=Stage3Error,
                # kwargs for Stage3Semantics.run:
                stage1_output=result.stage1_output,
                stage2_output=result.stage2_output,
                model_manager=model_manager,
                model_id=model_id,
            )
            result.retry_count += retries
            result.stage3_output = stage3.to_dict()
            logger.info(f"[{tid}] Stage 3 complete: semantics assigned")
            await broadcast_blender_trace(tid, 3, "Attachment Semantics", "complete")
        except Stage3Error as e:
            logger.error(f"[{tid}] Stage 3 failed after {MAX_STAGE_RETRIES} retries: {e}")
            await broadcast_blender_trace(tid, 3, "Attachment Semantics", "failed", {"error": str(e)})
            result.error = f"Stage 3 (Semantics) failed: {e}"
            result.failed_stage = 3
            return result
        except Exception as e:
            logger.exception(f"[{tid}] Stage 3 unexpected error")
            await broadcast_blender_trace(tid, 3, "Attachment Semantics", "failed", {"error": str(e)})
            result.error = f"Stage 3 unexpected error: {e}"
            result.failed_stage = 3
            return result
        
        # ===== STAGE 4: Deterministic Resolution (PURE CODE) =====
        logger.info(f"[{tid}] Stage 4: Deterministic Resolution")
        await broadcast_blender_trace(tid, 4, "Deterministic Resolution", "running")
        try:
            graph = Stage4Resolver.run(
                stage0_output=result.stage0_output,
                stage2_output=result.stage2_output,
                stage3_output=result.stage3_output,
                task_id=tid,
            )
            result.graph = graph
            result.success = True
            node_count = len(graph.root.all_nodes()) if hasattr(graph.root, 'all_nodes') else 1
            logger.info(f"[{tid}] Stage 4 complete: AssemblyGraph with {node_count} nodes")
            await broadcast_blender_trace(tid, 4, "Deterministic Resolution", "complete", {
                "nodes_count": node_count
            })
        except Stage4Error as e:
            logger.error(f"[{tid}] Stage 4 failed: {e}")
            await broadcast_blender_trace(tid, 4, "Deterministic Resolution", "failed", {"error": str(e)})
            result.error = f"Stage 4 (Resolution) failed: {e}"
            result.failed_stage = 4
            return result
        except Exception as e:
            logger.exception(f"[{tid}] Stage 4 unexpected error")
            await broadcast_blender_trace(tid, 4, "Deterministic Resolution", "failed", {"error": str(e)})
            result.error = f"Stage 4 unexpected error: {e}"
            result.failed_stage = 4
            return result
        
        return result
    
    @classmethod
    async def run_from_stage(
        cls,
        stage: int,
        prior_outputs: Dict[str, dict],
        prompt: str,
        model_manager: Any,
        task_id: str,
        model_id: Optional[str] = None,
    ) -> PipelineResult:
        """Resume pipeline from a specific stage (for targeted feedback/retry).
        
        Args:
            stage: Stage number to start from (0-4)
            prior_outputs: Dict with keys like "stage0", "stage1", etc.
            prompt: Original user prompt
            model_manager: Model manager for LLM calls
            task_id: Task ID
            model_id: Optional specific model
            
        Returns:
            PipelineResult
        """
        result = PipelineResult(success=False)
        
        # Copy prior outputs
        result.stage0_output = prior_outputs.get("stage0")
        result.stage1_output = prior_outputs.get("stage1")
        result.stage2_output = prior_outputs.get("stage2")
        result.stage3_output = prior_outputs.get("stage3")
        
        # Run from specified stage
        if stage <= 0:
            return await cls.run(prompt, model_manager, task_id, model_id)
        
        if stage <= 1 and result.stage0_output:
            try:
                stage1 = await Stage1Topology.run(
                    prompt=prompt,
                    stage0_output=result.stage0_output,
                    model_manager=model_manager,
                    task_id=task_id,
                    model_id=model_id,
                )
                result.stage1_output = stage1.to_dict()
            except Exception as e:
                result.error = f"Stage 1 failed: {e}"
                result.failed_stage = 1
                return result
        
        if stage <= 2 and result.stage0_output and result.stage1_output:
            try:
                stage2 = await Stage2Dimensions.run(
                    stage0_output=result.stage0_output,
                    stage1_output=result.stage1_output,
                    model_manager=model_manager,
                    task_id=task_id,
                    model_id=model_id,
                )
                result.stage2_output = stage2.to_dict()
            except Exception as e:
                result.error = f"Stage 2 failed: {e}"
                result.failed_stage = 2
                return result
        
        if stage <= 3 and result.stage1_output and result.stage2_output:
            try:
                stage3 = await Stage3Semantics.run(
                    stage1_output=result.stage1_output,
                    stage2_output=result.stage2_output,
                    model_manager=model_manager,
                    task_id=task_id,
                    model_id=model_id,
                )
                result.stage3_output = stage3.to_dict()
            except Exception as e:
                result.error = f"Stage 3 failed: {e}"
                result.failed_stage = 3
                return result
        
        if result.stage0_output and result.stage2_output and result.stage3_output:
            try:
                graph = Stage4Resolver.run(
                    stage0_output=result.stage0_output,
                    stage2_output=result.stage2_output,
                    stage3_output=result.stage3_output,
                    task_id=task_id,
                )
                result.graph = graph
                result.success = True
            except Exception as e:
                result.error = f"Stage 4 failed: {e}"
                result.failed_stage = 4
                return result
        
        return result
