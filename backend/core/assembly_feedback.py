"""Assembly Feedback & Mutation Engine.

Takes a Tier-3 JointVerificationResult failure and turns it into:
1. A deterministic parameter or transform mutation (compensating offset/scale).
2. A structured LLM re-prompt with numerical error diagnostics.
3. An escalation decision: mutate_and_retry -> split_further -> external_generative_fallback.
"""

from typing import Dict, Any, List, Optional, Tuple
import logging
from core.assembly_spec import AssemblyGraph, AssemblyNode
from core.assembly_verification import JointVerificationResult

logger = logging.getLogger(__name__)


class MutationAction:
    RETRY_MUTATED_SPEC = "retry_mutated_spec"
    SPLIT_FURTHER = "split_further"
    EXTERNAL_GENERATIVE = "external_generative"
    ABORT = "abort"


class AssemblyFeedbackEngine:
    """Computes targeted mutations and escalations for failing assembly nodes."""

    @classmethod
    def process_joint_failure(
        cls,
        graph: AssemblyGraph,
        failure: JointVerificationResult,
    ) -> Dict[str, Any]:
        """Process a single joint failure and produce a mutated spec or escalation action."""
        node = graph.get_node(failure.node_id)
        if not node:
            return {
                "action": MutationAction.ABORT,
                "reason": f"Node {failure.node_id} not found in assembly graph",
            }

        node.retry_count += 1
        logger.info(
            f"Processing joint failure for node '{node.label}' ({node.node_id}), "
            f"retry {node.retry_count}/{graph.max_retries_per_node}: {failure.reason}"
        )

        # Check retry exhaustion
        if node.retry_count > graph.max_retries_per_node:
            if node.max_split_depth_remaining > 0:
                node.status = "SPLIT"
                node.max_split_depth_remaining -= 1
                return {
                    "action": MutationAction.SPLIT_FURTHER,
                    "node_id": node.node_id,
                    "label": node.label,
                    "reason": f"Retry budget exhausted ({graph.max_retries_per_node} attempts). Decomposing node further.",
                    "split_depth_remaining": node.max_split_depth_remaining,
                }
            else:
                node.status = "FAILED"
                return {
                    "action": MutationAction.EXTERNAL_GENERATIVE,
                    "node_id": node.node_id,
                    "label": node.label,
                    "reason": "Retry budget and split depth exhausted. Escalating to external generative fallback (Hyper3D/Hunyuan3D).",
                }

        # Attempt deterministic spatial or spec mutation first
        mutated_spec, offset_adjustment = cls._attempt_deterministic_mutation(node, failure)

        # Build diagnostic LLM prompt for re-planning if deterministic mutation needs agent synthesis
        prompt = cls._build_diagnostic_prompt(node, failure)

        node.status = "BUILDING"
        if mutated_spec:
            node.sub_spec = mutated_spec

        if offset_adjustment:
            cur_off = list(node.attachment.local_offset)
            cur_off[0] += offset_adjustment[0]
            cur_off[1] += offset_adjustment[1]
            cur_off[2] += offset_adjustment[2]
            node.attachment.local_offset = (round(cur_off[0], 4), round(cur_off[1], 4), round(cur_off[2], 4))

        return {
            "action": MutationAction.RETRY_MUTATED_SPEC,
            "node_id": node.node_id,
            "label": node.label,
            "retry_count": node.retry_count,
            "offset_adjusted": offset_adjustment is not None,
            "new_offset": node.attachment.local_offset,
            "diagnostic_prompt": prompt,
            "mutated_sub_spec": node.sub_spec,
        }

    @classmethod
    def _attempt_deterministic_mutation(
        cls,
        node: AssemblyNode,
        failure: JointVerificationResult,
    ) -> Tuple[Optional[Dict[str, Any]], Optional[Tuple[float, float, float]]]:
        """Apply closed-form numerical adjustment to socket offset or part dimensions."""
        error_mm = failure.gap_or_overlap_mm
        offset_adj: Optional[Tuple[float, float, float]] = None
        mutated_spec: Optional[Dict[str, Any]] = None

        # 1. Spatial offset shift: if gap/overlap along Z or socket axis
        # Convert error from mm to meters
        shift_m = -(error_mm / 1000.0)

        # Heuristic: apply shift along Z or predominant socket axis
        socket = failure.socket_name.lower()
        if "top" in socket or "roof" in socket or "head" in socket or "deck" in socket or "bottom" in socket:
            # Vertical shift
            offset_adj = (0.0, 0.0, shift_m)
        elif "wheel" in socket or "x" in socket or "side" in socket:
            # Lateral shift
            sign = 1.0 if "right" in socket or "_r" in socket else -1.0
            offset_adj = (shift_m * sign, 0.0, 0.0)
        else:
            offset_adj = (0.0, 0.0, shift_m)

        # 2. Part dimension scaling if sibling interpenetration occurred
        if "overlap" in socket or "sibling" in socket:
            mutated_spec = dict(node.sub_spec)
            # If parts list in spec, shrink slightly (e.g. 5%)
            if "parts" in mutated_spec and isinstance(mutated_spec["parts"], list):
                for p in mutated_spec["parts"]:
                    if "size" in p and isinstance(p["size"], list):
                        p["size"] = [round(s * 0.92, 4) for s in p["size"]]
            elif "radius" in mutated_spec:
                mutated_spec["radius"] = round(float(mutated_spec["radius"]) * 0.92, 4)

        return mutated_spec, offset_adj

    @classmethod
    def _build_diagnostic_prompt(cls, node: AssemblyNode, failure: JointVerificationResult) -> str:
        """Constructs high-information context prompt for the LLM when re-planning."""
        return (
            f"Assembly verification failure on part '{node.label}' (node {node.node_id}):\n"
            f"- Socket: {failure.socket_name}\n"
            f"- Measured Gap/Overlap: {failure.gap_or_overlap_mm:+.2f} mm "
            f"({'GAP — part is too distant or small' if failure.gap_or_overlap_mm > 0 else 'OVERLAP — part penetrates parent or sibling'})\n"
            f"- Allowed Tolerance: {node.attachment.mating_tolerance_mm} mm\n"
            f"- Diagnosis: {failure.reason}\n\n"
            f"Instruction: Mutate the part dimensions or local attachment offset to resolve this {abs(failure.gap_or_overlap_mm):.2f}mm error."
        )
