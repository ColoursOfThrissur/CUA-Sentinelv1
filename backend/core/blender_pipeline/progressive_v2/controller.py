"""Progressive Assembly Controller — main build loop.

This is the heart of v5: the progressive build loop that:
1. Decomposes the model recursively
2. Builds nodes bottom-up (leaves first)
3. Runs per-node stages (2, 3, 4) just before building
4. Verifies each node after building
5. Merges verified children into assemblies
6. Checkpoints at verification boundaries

Unlike v4 which batches all stages upfront, this runs stages per-node
during the build loop, enabling recursive decomposition.

Blueprint references: §31 (main loop), §11 (per-node stages).
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, TYPE_CHECKING

from .node_types import NodeKind, NodeImportance, SocketType, PrimitiveType
from .manifest import (
    BuildManifest,
    ManifestNode,
    NodeState,
    CompletionStatus,
    BuildOutcome,
    GeometrySpec,
    AttachmentSpec,
)
from .hierarchy import ContainmentTree, HierarchyLimits, TraversalOrder
from .dag import DependencyDAG, DependencyType
from .decomposer import RecursiveDecomposer, decompose_manifest
from .stages import (
    Stage2Dimensions,
    Stage3Semantics,
    Stage4Resolver,
    ResolvedTransform,
)

logger = logging.getLogger(__name__)

# Import broadcast helper (optional - graceful fallback if not available)
try:
    from ..broadcast import broadcast_blender_trace
    _HAS_BROADCAST = True
except ImportError:
    _HAS_BROADCAST = False
    async def broadcast_blender_trace(*args, **kwargs):
        pass


# ---------------------------------------------------------------------------
# Build Result
# ---------------------------------------------------------------------------

@dataclass
class ProgressiveResult:
    """Result of a progressive assembly build."""
    success: bool
    manifest: BuildManifest
    completion_status: CompletionStatus
    # Correlation identity supplied by the caller.  This is distinct from the
    # generated model_id used for durable build artifacts.
    task_id: Optional[str] = None
    
    # Statistics
    total_nodes: int = 0
    verified_nodes: int = 0
    failed_nodes: int = 0
    skipped_nodes: int = 0
    
    llm_calls: int = 0
    blender_ops: int = 0
    
    build_time_seconds: float = 0.0
    
    # Errors
    errors: List[str] = field(default_factory=list)
    
    # Output
    blender_objects: List[str] = field(default_factory=list)
    output_file: Optional[str] = None
    outcome: Optional[BuildOutcome] = None
    
    def to_dict(self) -> Dict[str, Any]:
        # Include spatial verification status from manifest stats
        spatial_failed = False
        spatial_errors_list = []
        if self.manifest and hasattr(self.manifest, 'stats'):
            spatial_failed = self.manifest.stats.get("spatial_verification_failed", False)
            spatial_errors_list = self.manifest.stats.get("spatial_errors", [])
        
        return {
            "task_id": self.task_id,
            "success": self.completion_status == CompletionStatus.SUCCESS,
            "completion_status": self.completion_status.value,
            "total_nodes": self.total_nodes,
            "verified_nodes": self.verified_nodes,
            "failed_nodes": self.failed_nodes,
            "skipped_nodes": self.skipped_nodes,
            "llm_calls": self.llm_calls,
            "blender_ops": self.blender_ops,
            "build_time_seconds": self.build_time_seconds,
            "errors": self.errors,
            "blender_objects": self.blender_objects,
            "output_file": self.output_file,
            "outcome": self.outcome.to_dict() if self.outcome else None,
            # Spatial verification status - CRITICAL for synthesis prompt branching
            "spatial_verification_failed": spatial_failed,
            "spatial_errors": spatial_errors_list,
        }


# ---------------------------------------------------------------------------
# Build Phase
# ---------------------------------------------------------------------------

class BuildPhase(str, Enum):
    """Current phase of the build."""
    INITIALIZING = "initializing"
    DECOMPOSING = "decomposing"
    STAGING = "staging"
    BUILDING = "building"
    VERIFYING = "verifying"
    MERGING = "merging"
    FINALIZING = "finalizing"
    COMPLETE = "complete"
    FAILED = "failed"


# ---------------------------------------------------------------------------
# Progressive Controller
# ---------------------------------------------------------------------------

class ProgressiveController:
    """Main controller for progressive assembly builds.
    
    Usage:
        controller = ProgressiveController(model_manager, mcp_manager)
        result = await controller.run("Build a pirate ship", task_id="ship_001")
    """
    
    def __init__(
        self,
        model_manager: Any,
        mcp_manager: Optional[Any] = None,
        limits: Optional[HierarchyLimits] = None,
        max_retries: int = 3,
        checkpoint_interval: int = 5,  # Checkpoint every N verified nodes
        use_llm_modifiers: bool = True,
        preserve_scene: bool = False,
    ):
        self.model_manager = model_manager
        self.mcp_manager = mcp_manager
        self.limits = limits or HierarchyLimits()
        self.max_retries = max_retries
        self.checkpoint_interval = checkpoint_interval
        self.use_llm_modifiers = bool(use_llm_modifiers)
        self.preserve_scene = bool(preserve_scene)
        
        # Build state
        self.manifest: Optional[BuildManifest] = None
        self.tree: Optional[ContainmentTree] = None
        self.dag: Optional[DependencyDAG] = None
        self.phase: BuildPhase = BuildPhase.INITIALIZING
        self._executor: Optional[Any] = None  # shared BlenderExecutor for buffered build
        self._attempt_ledger: Optional[Any] = None
        
        # Tracking
        self.verified_since_checkpoint = 0
        self.start_time: float = 0.0
        
        # Callbacks for progress reporting
        self.on_phase_change: Optional[Callable[[BuildPhase, str], None]] = None
        self.on_node_complete: Optional[Callable[[str, NodeState], None]] = None

        # ── Gap 2: stage pipeline (class-level _PART_STAGE_PIPELINE below) ──
        # ── Gap 5: kind dispatch map ─────────────────────────────────────────
        # Maps NodeKind → async handler(node, task_id, model_id).
        # Add LIGHT, ARMATURE, etc. by inserting one entry here.
        self._KIND_HANDLERS: Dict[NodeKind, Any] = {
            NodeKind.PART:     self._process_part,
            NodeKind.DEFINITION: self._process_part,
            NodeKind.INSTANCE: self._process_part,
            NodeKind.ASSEMBLY: self._process_assembly_compat,
            NodeKind.MODEL:    self._process_assembly_compat,
        }

    @staticmethod
    def _prompt_has_explicit_measurement(prompt: str) -> bool:
        """Whether the user, rather than research, specified a physical size."""
        return bool(re.search(
            r"\b\d+(?:\.\d+)?\s*(?:mm|millimet(?:er|re)s?|cm|centimet(?:er|re)s?|m|met(?:er|re)s?|in(?:ch(?:es)?)?|ft|feet)\b",
            prompt or "", re.IGNORECASE,
        ))

    
    # ══════════════════════════════════════════════════════════════════════
    # Main Entry Point
    # ══════════════════════════════════════════════════════════════════════
    
    async def run(
        self,
        prompt: str,
        task_id: str,
        model_id: Optional[str] = None,
        stage0_output: Optional[Dict[str, Any]] = None,
    ) -> ProgressiveResult:
        """Run a complete progressive assembly build.
        
        Args:
            prompt: Natural language description of the model
            task_id: Unique task identifier
            model_id: Optional specific LLM model to use
            stage0_output: Optional pre-computed Stage 0 output
            
        Returns:
            ProgressiveResult with build outcome and statistics
        """
        self.start_time = time.time()
        self.task_id = task_id
        errors: List[str] = []
        
        try:
            # ── Phase 1: Initialize ──────────────────────────────────────
            self._set_phase(BuildPhase.INITIALIZING, "Creating manifest")
            await broadcast_blender_trace(task_id, 0, "Object Understanding", "running")

            from .manifest import prune_old_builds
            try:
                retention_days = int(os.getenv("BLENDER_BUILD_RETENTION_DAYS", "30"))
            except ValueError:
                retention_days = 30
            prune_old_builds(retention_days=retention_days)

            self.manifest = BuildManifest.create(prompt)
            self.manifest.stats["task_id"] = task_id
            from .attempt_ledger import AttemptLedger
            self._attempt_ledger = AttemptLedger(self.manifest, preserve_failed_scene=self.preserve_scene)
            self.manifest.stats["use_llm_modifiers"] = self.use_llm_modifiers
            if self.mcp_manager is None:
                self.manifest.stats["build_error"] = "BLENDER_MCP_UNAVAILABLE"
                self.manifest.record_event("build_blocked", details={"code": "BLENDER_MCP_UNAVAILABLE"})
                self.manifest.save()
                raise RuntimeError("BLENDER_MCP_UNAVAILABLE")
            # A previous process may have died after Blender side effects but
            # before it could roll back.  Sweep only terminal, non-preserved
            # manifests; active builds are deliberately skipped.
            try:
                from .manifest import _builds_dir
                persisted = []
                for manifest_path in _builds_dir().glob("*/manifest.json"):
                    try:
                        persisted.append(BuildManifest.load(manifest_path))
                    except Exception as load_error:
                        logger.warning("Unable to inspect prior build manifest %s: %s", manifest_path, load_error)
                sweep_reports = await AttemptLedger.sweep_orphans(self.mcp_manager, persisted)
                if sweep_reports:
                    self.manifest.stats["startup_orphan_sweep"] = sweep_reports
                    self.manifest.record_event("startup_orphan_sweep", details={"reports": sweep_reports})
            except Exception as sweep_error:
                self.manifest.stats["startup_orphan_sweep_error"] = str(sweep_error)
                self.manifest.record_event("startup_orphan_sweep_failed", details={"error": str(sweep_error)})
            # A scale contract is not optional for a spatial compiler.  Older
            # callers may omit Stage 0, so run the established understanding
            # stage here rather than silently dimensioning against 1 metre.
            if stage0_output is None:
                from ..stage0_understanding import Stage0Understanding, Stage0Error
                try:
                    understanding = await Stage0Understanding.run(
                        prompt, self.model_manager, task_id, model_id,
                    )
                    stage0_output = understanding.to_dict()
                    self.manifest.record_llm_call()
                    self.manifest.record_event(
                        "stage0_generated",
                        details={"scale_anchor_m": stage0_output.get("scale_anchor_m", {})},
                    )
                except Stage0Error as exc:
                    # Keep the build usable if an external model is temporarily
                    # unavailable, but make the degraded scale explicit.
                    logger.warning("[%s] Stage 0 unavailable: %s", task_id, exc)
                    self.manifest.record_event("stage0_unavailable", details={"error": str(exc)})
            self.manifest.stage0_output = stage0_output
            from .reference_brief import ReferenceBriefGenerator
            research_enabled = os.getenv("BLENDER_REFERENCE_RESEARCH", "1").strip().lower() not in {"0", "false", "off"}
            brief = await ReferenceBriefGenerator.run(
                prompt, stage0_output, self.model_manager, task_id, model_id, use_web=research_enabled,
            )
            # A user measurement is authoritative.  Otherwise adopt researched
            # scale only when ReferenceBrief retained two independent sources;
            # generic internet results remain visual/proportional guidance.
            if brief.scale_evidence and not self._prompt_has_explicit_measurement(prompt):
                stage0_output = dict(stage0_output or {})
                anchor = dict(stage0_output.get("scale_anchor_m") or {})
                anchor.update({
                    "overall_height_or_length": brief.scale_evidence["overall_extent_m"],
                    "reasoning": brief.scale_evidence["reasoning"],
                    "confidence": brief.scale_evidence["confidence"],
                    "source": "cross_checked_web_reference",
                })
                stage0_output["scale_anchor_m"] = anchor
                self.manifest.stage0_output = stage0_output
                self.manifest.record_event("reference_scale_adopted", details=brief.scale_evidence)
            # Stable conventions also cover legacy calls that omit Stage 0.
            from .model_contract import ModelContract
            self.manifest.stats["model_contract"] = ModelContract.from_stage0(stage0_output).to_dict()
            self.manifest.stats["reference_brief"] = brief.to_dict()
            if brief.source in {"model", "web+model"}:
                self.manifest.record_llm_call()
            self.tree = ContainmentTree(self.manifest, self.limits)
            
            await broadcast_blender_trace(task_id, 0, "Object Understanding", "complete", stage0_output or {})
            logger.info(f"[{task_id}] Starting progressive build: {prompt[:50]}...")
            
            # ── Phase 2: Decompose ───────────────────────────────────────
            self._set_phase(BuildPhase.DECOMPOSING, "Recursive decomposition")
            await broadcast_blender_trace(task_id, 1, "Decomposition", "running")
            
            decomp_stats = await self._decompose(task_id, model_id)

            # Resolve direct, unambiguous prompt facts into the physical tree
            # before downstream planners assign material or structural rules.
            # For example, a repeated arm assembly becomes repeated physical
            # branches rather than a single branch with a radial transform.
            from .design_fidelity import DesignFidelityValidator
            self.manifest.stats["design_fidelity"] = DesignFidelityValidator.report(prompt)
            ownership_report = DesignFidelityValidator.normalize_decomposition_ownership(self.manifest)
            self.manifest.stats["decomposition_ownership"] = ownership_report
            repair_report = DesignFidelityValidator.repair_explicit_requirements(self.manifest)
            self.manifest.stats["design_fidelity"]["repairs"] = repair_report["repairs"]
            # Turn explicit modelling intent and containment topology into a
            # small, deterministic constraint plan before any geometry is
            # resolved.  This is deliberately independent of display labels.
            from .constraint_planner import StructuralConstraintPlanner
            constraint_report = StructuralConstraintPlanner.apply(self.manifest)
            self.manifest.stats["structural_constraints"] = constraint_report
            # SceneTransactionCompiler enforces the same contract immediately
            # before it is allowed to send anything to Blender.
            from .capabilities import SCENE_PLAN_SCHEMA_VERSION, capability_manifest
            self.manifest.stats["scene_plan_schema_version"] = SCENE_PLAN_SCHEMA_VERSION
            self.manifest.stats["transaction_capabilities"] = capability_manifest()
            if constraint_report["material_coverage"]["missing_node_ids"]:
                self.manifest.record_event(
                    "material_hints_missing",
                    details={"nodes": constraint_report["material_coverage"]["missing_node_ids"]},
                )
            
            # Log socket types for debugging
            for node in self.manifest.nodes.values():
                if node.kind == NodeKind.PART:
                    socket = node.attachment.socket_type if node.attachment else "None"
                    logger.info(f"[{task_id}] Part {node.label}: socket={socket}")
            
            await broadcast_blender_trace(task_id, 1, "Decomposition", "complete", {
                "nodes_count": decomp_stats.get("total_nodes", 0)
            })
            logger.info(
                f"[{task_id}] Decomposition complete: "
                f"{decomp_stats['total_nodes']} nodes, "
                f"max depth {decomp_stats['max_depth_reached']}"
            )
            
            # Build dependency graph
            self.dag = DependencyDAG.from_manifest(self.manifest)
            
            # ── Phase 3: Build Loop ──────────────────────────────────────
            self._set_phase(BuildPhase.BUILDING, "Progressive build loop")
            await broadcast_blender_trace(task_id, 4, "Progressive Build", "running")

            # Create ONE shared executor for the entire build — all build_node
            # and merge_assembly calls buffer into it, then flush() sends ONE
            # atomic MCP call so parenting always sees all objects in scope.
            build_mode = os.getenv("BLENDER_BUILD_MODE", "transaction").strip().lower()
            if self.mcp_manager and build_mode == "transaction":
                await self._plan_then_commit_transaction(task_id, model_id)
            else:
                if self.mcp_manager:
                    from .executor import BlenderExecutor
                    self._executor = BlenderExecutor(
                        self.mcp_manager, task_id,
                        use_llm_modifiers=self.use_llm_modifiers,
                    )
                await self._build_loop(task_id, model_id)

            await broadcast_blender_trace(task_id, 4, "Progressive Build", "complete")
            
            # ── Phase 4: Ground-plane correction ─────────────────────────
            # Do not trust the transaction receipt as proof of scene state.
            # Query Blender before ground lifting so translation cannot hide a
            # detached or malformed committed scene.
            if self._executor and self.mcp_manager:
                from .readback import SceneReadbackVerifier
                readback = await SceneReadbackVerifier(self.mcp_manager).verify(
                    self.manifest, self._executor,
                )
                self.manifest.stats["scene_readback"] = readback
                if not readback["ok"]:
                    fatal_codes = [
                        item["code"] for item in readback["findings"]
                        if item["severity"] == "error" and item["code"] in (
                            "collection_missing", "object_missing", "identity_mismatch"
                        )
                    ]
                    if fatal_codes:
                        raise RuntimeError("SCENE_READBACK_FAILED: " + ", ".join(fatal_codes[:8]))
                    error_codes = [
                        item["code"] for item in readback["findings"]
                        if item["severity"] == "error"
                    ]
                    logger.warning(
                        "[%s] Scene readback reported non-fatal defects: %s",
                        task_id, ", ".join(error_codes[:8]),
                    )
                from .scene_quality import ProductionSceneAudit
                from .scene_quality import QualityGateFailed
                real_mcp = self.mcp_manager
                _MAX_SCENE_QUALITY_RETRIES = 2
                _previous_error_count: Optional[int] = None
                for _sq_attempt in range(_MAX_SCENE_QUALITY_RETRIES + 1):
                    scene_audit = ProductionSceneAudit.run(self.manifest, readback)
                    if scene_audit["ok"]:
                        break

                    error_findings = [
                        item for item in scene_audit["findings"]
                        if item["severity"] == "error"
                    ]
                    # A repair is only acceptable when it strictly reduces
                    # error-severity defects.  This prevents churn that keeps
                    # a visually different but equally invalid attempt.
                    if _previous_error_count is not None and len(error_findings) >= _previous_error_count:
                        raise QualityGateFailed(
                            self._executor._attempt_id,
                            error_findings,
                            ["scene_readback.json", "production_scene_audit.json"],
                        )
                    _previous_error_count = len(error_findings)
                    if _sq_attempt >= _MAX_SCENE_QUALITY_RETRIES:
                        # Exhausted retries — fail the build with details
                        raise QualityGateFailed(
                            self._executor._attempt_id,
                            error_findings,
                            ["scene_readback.json", "production_scene_audit.json"],
                        )

                    # Collect failing node_ids and their specific violations
                    repair_targets = {}
                    for finding in error_findings:
                        nid = finding.get("node_id")
                        if nid and nid in self.manifest.nodes:
                            repair_targets.setdefault(nid, []).append(finding)

                    if not repair_targets:
                        # Findings without node_ids cannot be repaired
                        raise QualityGateFailed(
                            self._executor._attempt_id,
                            error_findings,
                            ["scene_readback.json", "production_scene_audit.json"],
                        )

                    logger.warning(
                        "[%s] Scene quality repair attempt %d/%d: %d nodes to fix: %s",
                        task_id, _sq_attempt + 1, _MAX_SCENE_QUALITY_RETRIES,
                        len(repair_targets),
                        ", ".join(
                            f"{self.manifest.nodes[nid].label}({','.join(f['code'] for f in findings)})"
                            for nid, findings in repair_targets.items()
                        ),
                    )
                    self.manifest.record_event(
                        "scene_quality_repair_attempt",
                        details={
                            "attempt": _sq_attempt + 1,
                            "max_attempts": _MAX_SCENE_QUALITY_RETRIES,
                            "failing_nodes": {
                                nid: [f["code"] for f in findings]
                                for nid, findings in repair_targets.items()
                            },
                        },
                    )

                    # Feed violation details back into stage_outputs so
                    # Stage 2 re-dimension can see the specific failure.
                    for nid, findings in repair_targets.items():
                        node = self.manifest.nodes[nid]
                        node.stage_outputs["scene_quality_feedback"] = [
                            {
                                "code": f["code"],
                                "expected": f.get("expected"),
                                "dimensions": f.get("dimensions"),
                                "gap_m": f.get("gap_m"),
                                "reference_node_id": f.get("reference_node_id"),
                                "reference_label": (
                                    self.manifest.nodes[f["reference_node_id"]].label
                                    if f.get("reference_node_id") and f["reference_node_id"] in self.manifest.nodes
                                    else None
                                ),
                                "node_ids": f.get("node_ids"),
                            }
                            for f in findings
                        ]
                        # Reset the node's stage2/3/4 outputs to force re-planning
                        node.stage_outputs.pop("stage2", None)
                        node.stage_outputs.pop("stage3", None)
                        node.stage_outputs.pop("stage4", None)
                        # ``ManifestNode.transform_state`` is a durable
                        # serialization invariant.  Reset its contents for
                        # Stage 4, never replace it with None: ledger state
                        # transitions persist the manifest before replanning.
                        from .transforms import NodeTransformState
                        node.transform_state = NodeTransformState()
                        node.blender_objects = []
                        node.bounding_box = None
                        node.state = NodeState.PLANNED

                    # Also un-verify ancestor assemblies so _build_loop doesn't immediately
                    # exit on is_root_resolved() before re-planning the nodes.
                    for nid in list(repair_targets.keys()):
                        for anc_id in self.manifest.get_ancestors(nid):
                            anc_node = self.manifest.nodes.get(anc_id)
                            if anc_node and anc_node.state == NodeState.VERIFIED:
                                anc_node.state = NodeState.PLANNED
                                if anc_node.transform_state:
                                    anc_node.transform_state.unfreeze()

                    # Re-run planning for the affected nodes, then recompile
                    # and re-submit the full transaction.
                    previous_executor = self._executor
                    self.mcp_manager = None
                    self._executor = None
                    try:
                        await self._build_loop(task_id, model_id)
                    finally:
                        self.mcp_manager = real_mcp

                    # Clean up superseded attempt so scene inspections and readback do not see both
                    if previous_executor and not self.preserve_scene:
                        try:
                            await previous_executor.cleanup_all()
                        except Exception as hide_err:
                            logger.warning("[%s] Failed to clean superseded attempt: %s", task_id, hide_err)

                    from .executor import BlenderExecutor
                    from .transaction import SceneTransactionCompiler
                    self._executor = BlenderExecutor(
                        real_mcp, task_id,
                        use_llm_modifiers=self.use_llm_modifiers,
                        preserve_scene=self.preserve_scene,
                    )
                    if self._attempt_ledger:
                        self._attempt_ledger.register(self._executor)
                        self._attempt_ledger.mark_committing(self._executor._attempt_id)
                    receipt = await SceneTransactionCompiler(
                        self._executor, self.manifest
                    ).execute()
                    if self._attempt_ledger:
                        self._attempt_ledger.mark_committed(self._executor._attempt_id)
                    logger.info(
                        "[%s] Repair transaction committed: %d parts, %d assemblies",
                        task_id, receipt.part_count, receipt.assembly_count,
                    )

                    # Re-run readback for the new scene
                    from .readback import SceneReadbackVerifier
                    readback = await SceneReadbackVerifier(
                        self.mcp_manager
                    ).verify(self.manifest, self._executor)
                    if not readback["ok"]:
                        codes = [
                            item["code"] for item in readback["findings"]
                            if item["severity"] == "error"
                        ]
                        raise RuntimeError(
                            "SCENE_READBACK_FAILED after repair: "
                            + ", ".join(codes[:8])
                        )
                    # Loop back to re-check scene quality

            # Ground-plane correction is allowed only after measured scene
            # state has passed identity and quality gates.
            await self._lift_to_ground_plane(task_id)

            # Re-run readback post-lift to verify coordinates match manifest
            if self._executor and self.mcp_manager:
                from .readback import SceneReadbackVerifier
                post_lift_readback = await SceneReadbackVerifier(self.mcp_manager).verify(
                    self.manifest, self._executor,
                )
                self.manifest.stats["scene_readback_post_lift"] = post_lift_readback
                if not post_lift_readback["ok"]:
                    fatal_codes = [
                        item["code"] for item in post_lift_readback["findings"]
                        if item["severity"] == "error" and item["code"] in (
                            "collection_missing", "object_missing", "identity_mismatch"
                        )
                    ]
                    if fatal_codes:
                        raise RuntimeError("SCENE_READBACK_FAILED_POST_LIFT: " + ", ".join(fatal_codes[:8]))
                    error_codes = [
                        item["code"] for item in post_lift_readback["findings"]
                        if item["severity"] == "error"
                    ]
                    logger.warning(
                        "[%s] Post-lift readback reported non-fatal defects: %s",
                        task_id, ", ".join(error_codes[:8]),
                    )
            
            # ── Phase 5: Whole-Model Verification ────────────────────────
            self._set_phase(BuildPhase.VERIFYING, "Whole-model spatial verification")
            await broadcast_blender_trace(task_id, 6, "Spatial Verification", "running")
            
            spatial_errors = await self._verify_whole_model(task_id)
            
            # CRITICAL: Spatial verification failures MUST affect completion status
            self.manifest.stats["spatial_verification_failed"] = bool(spatial_errors)
            self.manifest.stats["spatial_errors"] = spatial_errors
            if spatial_errors:
                for err in spatial_errors:
                    errors.append(err)
                    logger.warning(f"[{task_id}] Spatial issue: {err}")
            
            await broadcast_blender_trace(task_id, 6, "Spatial Verification", "complete", {
                "issues": len(spatial_errors),
                "passed": len(spatial_errors) == 0,
            })

            # Fixed views are durable evidence for human/VLM evaluation.  A
            # renderer failure is explicit but does not overwrite geometry
            # verification; deployments can disable it for throughput tests.
            render_enabled = os.getenv("BLENDER_RENDER_EVIDENCE", "1").strip().lower() not in {"0", "false", "off"}
            if render_enabled and self._executor and self.mcp_manager:
                try:
                    from .render_evidence import MultiViewEvidenceRenderer
                    await MultiViewEvidenceRenderer.render(
                        self.manifest, self._executor, self.mcp_manager,
                    )
                    self.manifest.stats["visual_review"] = {
                        "status": "awaiting_reviewer", "pass": None,
                    }
                except Exception as render_error:
                    logger.warning("[%s] Render evidence failed: %s", task_id, render_error)
                    self.manifest.stats["render_evidence"] = {
                        "ok": False, "error": str(render_error),
                    }
            
            # ── Phase 5: Finalize ────────────────────────────────────────
            self._set_phase(BuildPhase.FINALIZING, "Finalizing build")
            
            await self._keep_final_attempt()
            self.manifest.finalize(self._compute_outcome(errors))
            
        except Exception as e:
            logger.exception(f"[{task_id}] Build failed: {e}")
            errors.append(str(e))
            self._set_phase(BuildPhase.FAILED, str(e))
            if self._attempt_ledger and self.mcp_manager:
                try:
                    cleaned = await self._attempt_ledger.rollback_all()
                    if not cleaned:
                        self.manifest.stats["orphan_risk"] = True
                except Exception as cleanup_error:
                    logger.warning("[%s] Attempt rollback failed: %s", task_id, cleanup_error)
            # A plan can fail after every planning node has been verified but
            # before Blender is allowed to receive the transaction.  Persist
            # that terminal outcome explicitly; otherwise the UI reloads an
            # old scene while the manifest misleadingly remains in_progress.
            if self.manifest:
                self.manifest.stats["build_error"] = str(e)
                quality_defects = list(getattr(e, "defects", []))
                evidence_paths = list(getattr(e, "evidence_paths", []))
                self.manifest.stats["build_end_time"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                self.manifest.outcome = BuildOutcome(
                    status=CompletionStatus.FAILED,
                    verification_levels_run=["controller"],
                    levels_passed={"controller": False},
                    defects=quality_defects or [{"gate": "controller", "measured": str(e), "expected": "successful build"}],
                    attempt_id=getattr(e, "attempt_id", None),
                    evidence_paths=evidence_paths,
                )
                self.manifest.completion_status = self.manifest.outcome.status
                self.manifest.record_event("build_failed", details={"error": str(e), "phase": self.phase.value})
                self.manifest.save()
        
        # Build result
        elapsed = time.time() - self.start_time
        
        return self._build_result(elapsed, errors)

    async def _keep_final_attempt(self) -> None:
        """Commit the delivery decision through durable attempt ownership.

        The ledger has every potentially dirty executor, so cleanup never
        depends on the controller retaining an old executor reference.
        """
        if not self._attempt_ledger or not self._executor:
            return
        if not await self._attempt_ledger.keep_final(self._executor._attempt_id):
            raise RuntimeError("ATTEMPT_CLEANUP_FAILED: superseded scene could not be proven absent")
    
    async def _plan_then_commit_transaction(
        self,
        task_id: str,
        model_id: Optional[str],
    ) -> None:
        """Resolve a full model off-scene, then make one construction call."""
        real_mcp = self.mcp_manager
        self._normalize_cage_ring_plan()
        self.mcp_manager = None
        self._executor = None
        try:
            # Existing stages remain the planning engine, but their simulated
            # path ensures no partial Blender state is created.
            await self._build_loop(task_id, model_id)
        finally:
            self.mcp_manager = real_mcp

        root = self.manifest.get_root()
        if root.state != NodeState.VERIFIED:
            raise RuntimeError("SCENE_PLAN_INCOMPLETE: planning did not resolve the root model")
        failed_required = [
            node.label for node in self.manifest.nodes.values()
            if node.importance == NodeImportance.REQUIRED
            and node.state in (NodeState.FAILED, NodeState.SKIPPED)
        ]
        if failed_required:
            raise RuntimeError(
                "SCENE_PLAN_INCOMPLETE: required nodes failed: " + ", ".join(failed_required[:8])
            )

        from .design_audit import DesignProposalAudit
        normalization = DesignProposalAudit.fit_to_scale_contract(self.manifest)
        if normalization:
            self.manifest.stats["scale_normalization"] = normalization
            self.manifest.record_event("scene_plan_scale_normalized", details=normalization)
        audit = DesignProposalAudit.run(self.manifest)
        self.manifest.stats["design_proposal_audit"] = audit
        if audit["errors"]:
            self.manifest.record_event("scene_plan_audit_failed", details=audit)
            self.manifest.save()
            raise RuntimeError("SCENE_PLAN_AUDIT_FAILED: " + "; ".join(audit["errors"][:6]))
        for warning in audit["warnings"]:
            logger.warning("[%s] Scene-plan audit: %s", task_id, warning)

        from .executor import BlenderExecutor
        from .transaction import SceneTransactionCompiler

        self._set_phase(BuildPhase.BUILDING, "Committing frozen scene plan")
        self._executor = BlenderExecutor(
            real_mcp, task_id, use_llm_modifiers=self.use_llm_modifiers,
            preserve_scene=self.preserve_scene,
        )
        if self._attempt_ledger:
            self._attempt_ledger.register(self._executor)
            self._attempt_ledger.mark_committing(self._executor._attempt_id)
        receipt = await SceneTransactionCompiler(self._executor, self.manifest).execute()
        if self._attempt_ledger:
            self._attempt_ledger.mark_committed(self._executor._attempt_id)
        logger.info(
            f"[{task_id}] Scene transaction committed: {receipt.part_count} parts, "
            f"{receipt.assembly_count} assemblies, {receipt.boolean_count} booleans"
        )

    def _normalize_cage_ring_plan(self) -> None:
        """Normalize a topology-detected radial guard, without relying on labels."""
        for assembly in self.manifest.nodes.values():
            if assembly.kind != NodeKind.ASSEMBLY:
                continue
            rings = [
                self.manifest.nodes[child_id]
                for child_id in assembly.children_ids
                if child_id in self.manifest.nodes
                and self.manifest.nodes[child_id].kind == NodeKind.PART
                and self.manifest.nodes[child_id].geometry
                and self.manifest.nodes[child_id].geometry.primitive == PrimitiveType.TORUS
            ]
            if len(rings) < 2:
                continue
            parent = self.manifest.nodes.get(assembly.parent_id) if assembly.parent_id else None
            has_radial_group = bool(parent and any(
                self.manifest.nodes.get(child_id)
                and self.manifest.nodes[child_id].attachment
                and self.manifest.nodes[child_id].attachment.socket_type == SocketType.RADIAL
                for child_id in parent.children_ids
            ))
            # Multiple tori alone could be an ornament.  A guard is recognized
            # by a torus group alongside a radial moving/repeated group.
            if not has_radial_group:
                continue
            contract = self.manifest.stats.get("model_contract", {})
            extent = float(contract.get("overall_extent_m", 1.0) or 1.0)
            wire_radius = max((ring.geometry.minor_radius or 0.0) for ring in rings)
            clearance = max(extent * 0.01, wire_radius * 2.0)
            assembly.stage_outputs.setdefault("stage3", {})["front_clearance_m"] = clearance
            for ring in rings:
                if ring.attachment.socket_type == SocketType.RELATIVE_TO:
                    ring.attachment.socket_type = SocketType.ROOT
                    ring.attachment.relative_to = None
                    ring.stage_outputs.pop("stage3", None)
                if assembly.attachment and assembly.attachment.socket_type in {
                    SocketType.FRONT_FACE, SocketType.BACK_FACE,
                    SocketType.FRONT_CENTER, SocketType.BACK_CENTER,
                }:
                    ring.stage_outputs["orientation_policy"] = {
                        "local_rotation": [1.5707963267948966, 0.0, 0.0],
                        "reason": "face_mounted_radial_guard",
                    }
            self.manifest.record_event(
                "radial_guard_plan_normalized",
                node_id=assembly.node_id,
                details={"rings": [ring.node_id for ring in rings], "layout": "concentric", "clearance_m": clearance},
            )

    def _set_phase(self, phase: BuildPhase, message: str) -> None:
        """Update current phase and notify callback."""
        self.phase = phase
        logger.debug(f"Phase: {phase.value} - {message}")
        if self.on_phase_change:
            self.on_phase_change(phase, message)
    
    def _build_result(self, elapsed: float, errors: List[str]) -> ProgressiveResult:
        """Build the final result object.
        
        CRITICAL: Completion status is affected by:
        1. Node states (verified, failed, skipped)
        2. Spatial verification errors (interpenetration, floating, embedment)
        3. Any other errors accumulated during build
        
        A build with spatial errors is COMPLETED_DEGRADED, not SUCCESS.
        """
        if not self.manifest:
            return ProgressiveResult(
                success=False,
                manifest=BuildManifest.create(""),
                completion_status=CompletionStatus.FAILED,
                errors=errors,
                build_time_seconds=elapsed,
            )
        
        # Count node states
        verified = len(self.manifest.nodes_in_state(NodeState.VERIFIED))
        failed = len(self.manifest.nodes_in_state(NodeState.FAILED))
        skipped = len(self.manifest.nodes_in_state(NodeState.SKIPPED))
        
        # Collect blender objects
        blender_objects = []
        for node in self.manifest.nodes.values():
            blender_objects.extend(node.blender_objects)
        
        outcome = self.manifest.outcome or self._compute_outcome(errors)
        status = outcome.status
        
        all_errors = list(errors)
        for node in self.manifest.nodes.values():
            if node.state == NodeState.FAILED and node.error_message:
                entry = f"NODE_FAILED [{node.node_id}] {node.label}: {node.error_message}"
                if entry not in all_errors:
                    all_errors.append(entry)

        return ProgressiveResult(
            success=status == CompletionStatus.SUCCESS,
            manifest=self.manifest,
            completion_status=status,
            total_nodes=len(self.manifest.nodes),
            verified_nodes=verified,
            failed_nodes=failed,
            skipped_nodes=skipped,
            llm_calls=self.manifest.stats.get("total_llm_calls", 0),
            blender_ops=self.manifest.stats.get("total_blender_ops", 0),
            build_time_seconds=elapsed,
            errors=all_errors,
            blender_objects=blender_objects,
            outcome=outcome,
        )

    def _compute_outcome(self, errors: List[str]) -> BuildOutcome:
        """Compute the only build outcome used by persistence and API results."""
        if not self.manifest:
            return BuildOutcome(CompletionStatus.FAILED, ["controller"], {"controller": False})
        stats = self.manifest.stats
        levels: Dict[str, bool] = {}
        evidence: List[str] = []
        defects: List[Dict[str, Any]] = []
        readback = stats.get("scene_readback")
        if isinstance(readback, dict):
            levels["readback"] = readback.get("ok") is True
            evidence.append("scene_readback.json")
            defects.extend(readback.get("findings", []))
        audit = stats.get("production_scene_audit")
        if isinstance(audit, dict):
            levels["scene_quality"] = audit.get("ok") is True
            evidence.append("production_scene_audit.json")
            defects.extend(audit.get("findings", []))
        spatial_failed = bool(stats.get("spatial_verification_failed", False))
        if "spatial_verification_failed" in stats:
            levels["spatial"] = not spatial_failed
            defects.extend({"gate": "spatial", "measured": error, "expected": "no spatial errors"}
                           for error in stats.get("spatial_errors", []))

        render_enabled = os.getenv("BLENDER_RENDER_EVIDENCE", "1").strip().lower() not in {"0", "false", "off"}
        if render_enabled and ("visual_review" in stats or "render_evidence" in stats):
            render_ok = stats.get("render_evidence", {}).get("ok", True) if "render_evidence" in stats else True
            levels["render"] = render_ok
            if "render_evidence" in stats and not render_ok:
                defects.append({"gate": "render", "measured": stats["render_evidence"].get("error"), "expected": "render completed"})

        # Explicit required verification levels: all must run and pass for SUCCESS
        required_levels = ["readback", "scene_quality", "spatial"]
        all_required_passed = all(levels.get(lvl) is True for lvl in required_levels)

        if self.phase == BuildPhase.FAILED or stats.get("build_error"):
            status = CompletionStatus.FAILED
        elif self.mcp_manager is None:
            status = CompletionStatus.PLANNED_ONLY
        elif spatial_failed or (audit is not None and audit.get("ok") is not True):
            status = CompletionStatus.COMPLETED_DEGRADED
        elif readback is None:
            status = CompletionStatus.COMMITTED_UNVERIFIED
        elif readback.get("ok") is not True:
            status = CompletionStatus.COMPLETED_DEGRADED
        elif not all_required_passed:
            # Missing required verification level blocks SUCCESS
            status = CompletionStatus.COMPLETED_DEGRADED
        else:
            status = self.manifest.compute_completion_status()
            if status == CompletionStatus.IN_PROGRESS:
                # Finished build must not remain IN_PROGRESS
                status = CompletionStatus.FAILED
        return BuildOutcome(
            status=status,
            verification_levels_run=list(levels),
            levels_passed=levels,
            defects=defects,
            attempt_id=getattr(self._executor, "_attempt_id", None),
            evidence_paths=evidence,
        )
    
    # ══════════════════════════════════════════════════════════════════════
    # Whole-Model Verification
    # ══════════════════════════════════════════════════════════════════════
    
    async def _lift_to_ground_plane(self, task_id: str) -> None:
        """Translate the entire assembly so its lowest point sits at Z=0.

        Architecture:
        - The lift is a change to the ROOT node's local transform Z position.
        - After updating the root's local_transform, we call
          manifest.propagate_transforms_from(root_id) to cascade the new
          world_matrix down through every descendant via the revision/
          parent_revision mechanism.
        - This preserves every child's LOCAL relationship to its parent;
          only world positions change.
        - We MUST NOT reconstruct world_matrix directly with WorldMatrix.from_local()
          on non-root nodes — that is the same root-node mistake as Bug 1.
        """
        if not self.mcp_manager:
            # Simulated path: find global min Z from bounding boxes
            min_z = float('inf')
            for node in self.manifest.nodes.values():
                if node.kind == NodeKind.PART and node.bounding_box:
                    min_z = min(min_z, node.bounding_box["min"][2])
            if min_z == float('inf') or abs(min_z) < 0.001:
                return
            lift = -min_z
            logger.info(f"[{task_id}] Ground-plane lift (sim): {lift:.4f}m")

            # Apply lift to ROOT node's local transform Z, then propagate
            root = self.manifest.get_root()
            if root.transform_state:
                lt = root.transform_state.local_transform
                from .transforms import LocalTransform
                new_local = LocalTransform(
                    position=[lt.position[0], lt.position[1], lt.position[2] + lift],
                    rotation=list(lt.rotation),
                    scale=list(lt.scale),
                )
                root.transform_state.set_local_transform(new_local, force=root.transform_state.frozen)
                self.manifest.propagate_transforms_from(root.node_id)

            # Keep legacy fields and bounding boxes in sync
            for node in self.manifest.nodes.values():
                if node.bounding_box:
                    node.bounding_box["min"][2] += lift
                    node.bounding_box["max"][2] += lift
                if node.world_position is not None:
                    node.world_position = [
                        node.world_position[0],
                        node.world_position[1],
                        node.world_position[2] + lift,
                    ]
            return

        # Real path: ask Blender for the global min Z scoped strictly to this attempt's collection,
        # excluding boolean cutters, definitions, hidden objects, cameras, and lights.
        # Lift the root object ONCE so hierarchy carries all parts and empties together.
        root_node = self.manifest.get_root()
        root_obj_name = root_node.blender_objects[0] if root_node and root_node.blender_objects else None
        coll_name = self._executor._collection_name if self._executor else None

        script = f'''
import bpy, json
from mathutils import Vector

coll_name = {coll_name!r}
root_obj_name = {root_obj_name!r}
coll = bpy.data.collections.get(coll_name) if coll_name else None
objects_to_measure = coll.all_objects if coll else bpy.context.scene.collection.all_objects

min_z = float('inf')
depsgraph = bpy.context.evaluated_depsgraph_get()
initial_mesh_count = len(bpy.data.meshes)

for obj in objects_to_measure:
    if obj.type == 'MESH' and not obj.hide_viewport and not obj.hide_render:
        eval_obj = obj.evaluated_get(depsgraph)
        mesh = eval_obj.to_mesh()
        try:
            for v in mesh.vertices:
                wz = (obj.matrix_world @ v.co).z
                if wz < min_z:
                    min_z = wz
        finally:
            eval_obj.to_mesh_clear()

final_mesh_count = len(bpy.data.meshes)
assert initial_mesh_count == final_mesh_count, f"Mesh leak during min_z measurement: {{final_mesh_count}} != {{initial_mesh_count}}"

if min_z == float('inf') or abs(min_z) < 0.001:
    print("SENTINEL_OUTPUT_START" + json.dumps({{"ok": True, "lift": 0.0}}) + "SENTINEL_OUTPUT_END")
else:
    lift = -min_z
    # Lift ROOT object once so hierarchy preserves relative transforms
    root_obj = bpy.data.objects.get(root_obj_name) if root_obj_name else None
    if root_obj:
        root_obj.matrix_world.translation.z += lift
    else:
        # Fallback if no single root object: translate top-level unparented objects in collection
        for obj in objects_to_measure:
            if obj.parent is None:
                obj.matrix_world.translation.z += lift
    bpy.context.view_layer.update()
    print("SENTINEL_OUTPUT_START" + json.dumps({{"ok": True, "lift": lift}}) + "SENTINEL_OUTPUT_END")
'''
        try:
            result = await self.mcp_manager.call_locked(
                "blender", "execute_blender_code", {"code": script}
            )
            output = result.get("output", "")
            import json as _json
            s, e = "SENTINEL_OUTPUT_START", "SENTINEL_OUTPUT_END"
            si, ei = output.find(s), output.find(e)
            if si != -1 and ei != -1:
                data = _json.loads(output[si + len(s):ei].strip())
                lift = data.get("lift", 0.0)
                if lift:
                    logger.info(f"[{task_id}] Ground-plane lift: {lift:.4f}m")

                    # Apply lift to ROOT node's local transform Z, then propagate
                    # through the hierarchy so every descendant's world_matrix
                    # is recomputed correctly via revision/parent_revision.
                    root = self.manifest.get_root()
                    if root.transform_state:
                        lt = root.transform_state.local_transform
                        from .transforms import LocalTransform
                        new_local = LocalTransform(
                            position=[lt.position[0], lt.position[1], lt.position[2] + lift],
                            rotation=list(lt.rotation),
                            scale=list(lt.scale),
                        )
                        root.transform_state.set_local_transform(new_local, force=root.transform_state.frozen)
                        self.manifest.propagate_transforms_from(root.node_id)

                    # Keep legacy fields and bounding boxes in sync
                    for node in self.manifest.nodes.values():
                        if node.world_position is not None:
                            node.world_position = [
                                node.world_position[0],
                                node.world_position[1],
                                node.world_position[2] + lift,
                            ]
                        if node.bounding_box:
                            node.bounding_box["min"][2] += lift
                            node.bounding_box["max"][2] += lift
        except Exception as exc:
            logger.warning(f"[{task_id}] Ground-plane lift failed: {exc}")

    async def _verify_whole_model(self, task_id: str) -> List[str]:
        """Run whole-model spatial verification after build completes.
        
        Checks:
        1. Interpenetration between non-boolean parts
        2. Floating objects (parts not touching anything)
        3. Ground plane violations (parts below Z=0 when they shouldn't be)
        4. Embedment issues (parts mostly inside other parts)
        
        Returns list of error messages (empty if all checks pass).
        """
        errors = []
        
        if not self.mcp_manager:
            logger.debug(f"[{task_id}] Skipping spatial verification (no MCP)")
            return errors
        
        from .verification import SpatialVerifier, VerificationLevel
        
        # Collect all blender objects from verified PART nodes
        all_objects = []
        allowed_overlaps = set()
        allowed_disconnected = set()
        
        for node in self.manifest.nodes.values():
            if node.kind in (NodeKind.PART, NodeKind.INSTANCE) and node.state == NodeState.VERIFIED:
                all_objects.extend(node.blender_objects)
                if node.attachment and node.attachment.allow_disconnected:
                    allowed_disconnected.update(node.blender_objects)
                
                # Boolean cuts, insets, embedded parts, and declared clearance parts
                # are allowed to overlap/intersect their host/parent.
                if node.attachment and (
                    node.attachment.socket_type in (SocketType.BOOLEAN_CUT, SocketType.INSET, SocketType.EMBEDDED)
                    or node.attachment.allow_disconnected
                ):
                    if node.parent_id:
                        parent = self.manifest.nodes.get(node.parent_id)
                        if parent:
                            for node_obj in node.blender_objects:
                                for parent_obj in parent.blender_objects:
                                    allowed_overlaps.add((node_obj, parent_obj))
                                    allowed_overlaps.add((parent_obj, node_obj))
                            for sib_id in parent.children_ids:
                                sib = self.manifest.nodes.get(sib_id)
                                if sib and sib.attachment and sib.attachment.socket_type == SocketType.ROOT:
                                    for node_obj in node.blender_objects:
                                        for sib_obj in sib.blender_objects:
                                            allowed_overlaps.add((node_obj, sib_obj))
                                            allowed_overlaps.add((sib_obj, node_obj))
        
        if len(all_objects) < 2:
            logger.debug(f"[{task_id}] Skipping spatial verification (< 2 objects)")
            return errors
        
        verifier = SpatialVerifier(self.mcp_manager)
        
        # Run verification at STRICT level (interpenetration + floating check)
        result = await verifier.verify_assembly(
            objects=all_objects,
            level=VerificationLevel.STRICT,
            allowed_overlaps=allowed_overlaps,
            allowed_disconnected=allowed_disconnected,
            task_id=task_id,
        )
        
        # Collect errors and warnings
        for issue in result.issues:
            if issue.severity == "error":
                errors.append(str(issue))
            else:
                logger.warning(f"[{task_id}] Spatial warning: {issue}")
        
        errors.extend(result.errors)
        
        # Additional check: ground plane violations
        ground_errors = await self._check_ground_plane(all_objects, task_id)
        errors.extend(ground_errors)
        
        # Additional check: embedment (parts mostly inside other parts)
        embedment_errors = await self._check_embedment(all_objects, allowed_overlaps, task_id)
        errors.extend(embedment_errors)
        
        return errors
    
    async def _check_ground_plane(self, objects: List[str], task_id: str) -> List[str]:
        """Check for objects that are below the ground plane (Z < 0).
        
        Some objects (like table legs) legitimately extend below Z=0,
        but the ROOT part's bottom should typically be at or above Z=0.
        """
        errors = []
        
        if not self.mcp_manager:
            return errors
        
        # Find the ROOT part's minimum Z
        root = self.manifest.get_root()
        root_part = None
        if root:
            for cid in root.children_ids:
                child = self.manifest.nodes.get(cid)
                if child and child.kind == NodeKind.PART:
                    if child.attachment and child.attachment.socket_type == SocketType.ROOT:
                        root_part = child
                        break
                elif child and child.kind == NodeKind.ASSEMBLY:
                    # Look for ROOT part inside assembly
                    for gcid in child.children_ids:
                        gchild = self.manifest.nodes.get(gcid)
                        if gchild and gchild.kind == NodeKind.PART:
                            if gchild.attachment and gchild.attachment.socket_type == SocketType.ROOT:
                                root_part = gchild
                                break
        
        if not root_part or not root_part.blender_objects:
            return errors
        
        # Check if ROOT part's bottom is significantly below ground
        script = f'''
import bpy
import json
from mathutils import Vector

try:
    obj_name = {repr(root_part.blender_objects[0])}
    obj = bpy.data.objects.get(obj_name)

    if not obj or obj.type != 'MESH':
        result = {{"ok": True, "skipped": True}}
    else:
        # Get world-space minimum Z
        world_verts = [obj.matrix_world @ v.co for v in obj.data.vertices]
        if world_verts:
            min_z = min(v.z for v in world_verts)
            # Allow 1cm below ground for floating point tolerance
            # Return ok=True always, but include min_z for caller to evaluate
            result = {{"ok": True, "min_z": min_z, "below_ground": min_z < -0.01}}
        else:
            result = {{"ok": True, "skipped": True}}
except Exception as e:
    result = {{"ok": True, "skipped": True, "error": str(e)}}

print("SENTINEL_OUTPUT_START" + json.dumps(result) + "SENTINEL_OUTPUT_END")
'''
        try:
            result = await self.mcp_manager.call_locked(
                "blender", "execute_blender_code", {"code": script}
            )
            output = result.get("output", "")
            
            # Parse output manually to avoid parse_op_output raising on ok=false
            import json as json_mod
            start_tag = "SENTINEL_OUTPUT_START"
            end_tag = "SENTINEL_OUTPUT_END"
            start_idx = output.find(start_tag)
            end_idx = output.find(end_tag)
            
            if start_idx != -1 and end_idx != -1:
                json_str = output[start_idx + len(start_tag):end_idx].strip()
                data = json_mod.loads(json_str)
                
                if data.get("below_ground") and not data.get("skipped"):
                    min_z = data.get("min_z", 0)
                    errors.append(f"Ground plane violation: {root_part.label} extends to Z={min_z:.3f}m")
        except Exception as e:
            logger.warning(f"[{task_id}] Ground plane check failed: {e}")
        
        return errors
    
    async def _check_embedment(
        self,
        objects: List[str],
        allowed_overlaps: set,
        task_id: str,
    ) -> List[str]:
        """Check for parts that are mostly embedded inside other parts.
        
        A part is "embedded" if >50% of its volume is inside another part.
        This catches cases like a strut that's entirely inside a dish.
        """
        errors = []
        
        if not self.mcp_manager or len(objects) < 2:
            return errors
        
        # Convert allowed_overlaps to list for JSON
        allowed_list = [list(pair) for pair in allowed_overlaps]
        
        script = f'''
import bpy
import json
from mathutils import Vector
import random

try:
    objects = {repr(objects)}
    allowed = {allowed_list}
    EMBEDMENT_THRESHOLD = 0.5  # 50% of volume inside = embedded
    SAMPLE_COUNT = 50  # Number of random points to sample

    # Build set of allowed pairs
    allowed_set = set()
    for a, b in allowed:
        allowed_set.add((a, b))
        allowed_set.add((b, a))

    embedded = []

    # Seed once before the outer loop so each object gets a different
    # set of sample points, preventing systematic bias from a fixed seed
    # inside the per-object loop.
    random.seed(42)

    # For each object, check if it's mostly inside any other object
    for name_a in objects:
        obj_a = bpy.data.objects.get(name_a)
        if not obj_a or obj_a.type != 'MESH':
            continue
        
        # Get bounding box of A in world space
        bbox_a = [obj_a.matrix_world @ Vector(corner) for corner in obj_a.bound_box]
        min_a = Vector((min(v.x for v in bbox_a), min(v.y for v in bbox_a), min(v.z for v in bbox_a)))
        max_a = Vector((max(v.x for v in bbox_a), max(v.y for v in bbox_a), max(v.z for v in bbox_a)))
        
        # Sample random points inside A's bounding box.
        # Seed is set once before the outer loop (not here) so all object
        # pairs use different points, avoiding systematic bias.
        sample_points = [
            Vector((
                random.uniform(min_a.x, max_a.x),
                random.uniform(min_a.y, max_a.y),
                random.uniform(min_a.z, max_a.z),
            ))
            for _ in range(SAMPLE_COUNT)
        ]
        
        # Check each other object
        for name_b in objects:
            if name_a == name_b:
                continue
            if (name_a, name_b) in allowed_set:
                continue
            
            obj_b = bpy.data.objects.get(name_b)
            if not obj_b or obj_b.type != 'MESH':
                continue
            
            # Use closest_point_on_mesh + normal dot product.
            # Works correctly for non-convex meshes unlike the ray_cast
            # dual-direction heuristic which gives false positives for
            # hollow or toroidal geometry.
            inside_count = 0
            for p in sample_points:
                p_local = obj_b.matrix_world.inverted() @ p
                ok, loc, normal, _ = obj_b.closest_point_on_mesh(p_local)
                if ok:
                    to_point = p_local - loc
                    if to_point.dot(normal) < 0:
                        inside_count += 1
            
            ratio = inside_count / SAMPLE_COUNT
            if ratio > EMBEDMENT_THRESHOLD:
                embedded.append({{
                    "object": name_a,
                    "inside": name_b,
                    "ratio": ratio,
                }})

    result = {{"ok": True, "embedded": embedded}}
except Exception as e:
    result = {{"ok": True, "embedded": [], "error": str(e)}}

print("SENTINEL_OUTPUT_START" + json.dumps(result) + "SENTINEL_OUTPUT_END")
'''
        try:
            result = await self.mcp_manager.call_locked(
                "blender", "execute_blender_code", {"code": script}
            )
            output = result.get("output", "")
            
            # Parse output manually to avoid parse_op_output raising on ok=false
            import json as json_mod
            start_tag = "SENTINEL_OUTPUT_START"
            end_tag = "SENTINEL_OUTPUT_END"
            start_idx = output.find(start_tag)
            end_idx = output.find(end_tag)
            
            if start_idx != -1 and end_idx != -1:
                json_str = output[start_idx + len(start_tag):end_idx].strip()
                data = json_mod.loads(json_str)
                
                for item in data.get("embedded", []):
                    errors.append(
                        f"Embedment: {item['object']} is {item['ratio']*100:.0f}% inside {item['inside']}"
                    )
                
                if data.get("error"):
                    logger.debug(f"[{task_id}] Embedment check script error: {data['error']}")
        except Exception as e:
            logger.warning(f"[{task_id}] Embedment check failed: {e}")
        
        return errors

    
    # ══════════════════════════════════════════════════════════════════════
    # Decomposition
    # ══════════════════════════════════════════════════════════════════════
    
    async def _decompose(
        self,
        task_id: str,
        model_id: Optional[str],
    ) -> Dict[str, Any]:
        """Run recursive decomposition."""
        decomposer = RecursiveDecomposer(
            limits=self.limits,
            max_llm_calls=20,
        )
        
        stats = await decomposer.decompose(
            manifest=self.manifest,
            model_manager=self.model_manager,
            task_id=task_id,
            model_id=model_id,
        )
        
        return stats

    
    # ══════════════════════════════════════════════════════════════════════
    # Build Loop
    # ══════════════════════════════════════════════════════════════════════
    
    async def _build_loop(
        self,
        task_id: str,
        model_id: Optional[str],
    ) -> None:
        """Main progressive build loop.
        
        Processes nodes in dependency order:
        1. Find ready nodes (dependencies satisfied)
        2. For PART nodes: run stages 2/3/4, build, verify
        3. For ASSEMBLY nodes: check if children done, merge
        4. Checkpoint periodically
        5. Repeat until root is verified or stuck
        
        Phase 3: After Stage 4 completes for all ready nodes, propagate
        world transforms via the new system and compare with legacy.
        """
        # Log initial state of all nodes
        logger.info(f"[{task_id}] Build loop starting with {len(self.manifest.nodes)} nodes:")
        for node in self.manifest.nodes.values():
            parent = self.manifest.nodes.get(node.parent_id) if node.parent_id else None
            parent_info = f"parent={parent.label}({parent.state.value})" if parent else "ROOT"
            socket = node.attachment.socket_type.value if node.attachment else "None"
            logger.info(f"  [{node.kind.value}] {node.label}: state={node.state.value}, socket={socket}, {parent_info}")
        iteration = 0
        # Derive cap from node count: each node needs at most 5 transitions
        # (planned→ready→building→verifying→verified) plus assembly overhead.
        _per_node_budget = 5
        max_iterations = len(self.manifest.nodes) * _per_node_budget
        
        # Progress detection: snapshot of (node_id → state) to catch infinite spin
        _last_states: Dict[str, str] = {}
        _no_progress_count = 0
        _NO_PROGRESS_ABORT = 3  # Abort after this many consecutive no-progress iterations
        
        while iteration < max_iterations:
            # Recompile can add nodes; keep cap proportional.
            max_iterations = max(max_iterations, len(self.manifest.nodes) * _per_node_budget)
            iteration += 1
            
            # Check if done
            if self.manifest.is_root_resolved():
                logger.info(f"[{task_id}] Root verified - build complete!")
                self._set_phase(BuildPhase.COMPLETE, "Build complete")
                
                # FIX: Flush all buffered scripts before establishing hierarchy
                if self._executor and self._executor._script_buffer:
                    logger.info(f"[{task_id}] Flushing {len(self._executor._script_buffer)} buffered fragments before hierarchy establishment")
                    flush_ok = await self._executor.flush(self.manifest)
                    if not flush_ok:
                        logger.error(f"[{task_id}] Final flush failed before hierarchy establishment")
                
                # FIX: Establish Blender hierarchy after all assemblies are merged
                await self._establish_blender_hierarchy(task_id)
                return
            
            # Find actionable nodes
            actionable = self._find_actionable_nodes()
            
            if not actionable:
                # Log why we're stuck
                if iteration % 20 == 0:  # Log every 20 iterations
                    pending = [n for n in self.manifest.nodes.values() 
                               if n.state not in (NodeState.VERIFIED, NodeState.SKIPPED, NodeState.FAILED)]
                    if pending:
                        logger.warning(f"[{task_id}] Stuck - {len(pending)} pending nodes:")
                        for p in pending[:10]:  # Show more nodes
                            parent = self.manifest.nodes.get(p.parent_id) if p.parent_id else None
                            parent_info = f"parent={parent.label}({parent.state.value})" if parent else "no parent"
                            socket_info = f"socket={p.attachment.socket_type.value}" if p.attachment else "no socket"
                            # Check for transform state issues
                            transform_info = ""
                            if p.transform_state:
                                if p.transform_state.world_matrix is None:
                                    transform_info = " world_matrix=None"
                                if not p.transform_state.is_resolved:
                                    transform_info += " is_resolved=False"
                            # Check for missing stage data
                            stage_info = ""
                            missing_stages = []
                            for stage in ["stage2", "stage3", "stage4"]:
                                if stage not in p.stage_outputs:
                                    missing_stages.append(stage)
                            if missing_stages:
                                stage_info = f" missing_stages={missing_stages}"
                            logger.warning(
                                f"  - {p.label}: state={p.state.value}, kind={p.kind.value}, "
                                f"depth={p.hierarchy_depth}, {parent_info}, {socket_info}"
                                f"{transform_info}{stage_info}"
                            )
                
                # Check for deadlock
                if self._is_deadlocked():
                    logger.warning(f"[{task_id}] Build deadlocked - no actionable nodes")
                    break
                
                # No-progress detection: if state snapshot hasn't changed, we're spinning.
                current_states = {nid: n.state.value for nid, n in self.manifest.nodes.items()}
                if current_states == _last_states:
                    _no_progress_count += 1
                    if _no_progress_count >= _NO_PROGRESS_ABORT:
                        # Dump diagnostic before aborting
                        pending = [
                            n for n in self.manifest.nodes.values()
                            if n.state not in (NodeState.VERIFIED, NodeState.SKIPPED, NodeState.FAILED)
                        ]
                        logger.error(
                            f"[{task_id}] No-progress abort after {iteration} iterations. "
                            f"Stuck nodes ({len(pending)}): "
                            + ", ".join(f"{n.label}(state={n.state.value},kind={n.kind.value})" for n in pending[:15])
                        )
                        break
                else:
                    _no_progress_count = 0
                _last_states = current_states
                
                # All nodes processing, wait
                await asyncio.sleep(0.01)
                continue
            
            # ── Batch all ready PART nodes: stages → buffer, then ONE flush, then verify ──
            # ASSEMBLY nodes are processed one at a time (they only buffer an empty + parenting).
            part_nodes = [n for n in actionable if n.kind == NodeKind.PART]
            other_nodes = [n for n in actionable if n.kind != NodeKind.PART]

            staged = []
            if part_nodes and self._executor:
                # Phase 1: run stages 2/3/4 and buffer every ready PART.
                for node in part_nodes:
                    if await self._stage_and_buffer_part(node, task_id, model_id):
                        staged.append(node)

                # Phase 2: submit the complete currently-resolved part batch.
                # This must be in the executor branch: buffered objects do not
                # exist in Blender until this call succeeds.
                if staged and self._executor._script_buffer:
                    flush_ok = await self._executor.flush(self.manifest)
                    if not flush_ok:
                        for node in staged:
                            self._handle_failure(node, "Batch flush failed", "build")
                        staged = []
                        await asyncio.sleep(2.0)

                # Phase 3: only verify parts that have been flushed to Blender.
                for node in staged:
                    await self._verify_staged_part(node, task_id)
                    if self.on_node_complete:
                        self.on_node_complete(node.label, node.state)
            else:
                # No MCP executor: use the simulation/fallback path directly.
                for node in part_nodes:
                    handler = self._KIND_HANDLERS.get(node.kind)
                    if handler:
                        await handler(node, task_id, model_id)
                        if self.on_node_complete:
                            self.on_node_complete(node.label, node.state)

            # ASSEMBLY / MODEL nodes — buffer only, NO flush (deferred to final flush)
            for node in other_nodes:
                handler = self._KIND_HANDLERS.get(node.kind)
                if handler:
                    await handler(node, task_id, model_id)
                else:
                    self._handle_failure(
                        node,
                        f"UNSUPPORTED_CAPABILITY: no handler registered for NodeKind.{node.kind.value}",
                        "capability",
                    )
                if self.on_node_complete:
                    self.on_node_complete(node.label, node.state)

            # Checkpoint if needed
            if self.verified_since_checkpoint >= self.checkpoint_interval:
                self.manifest.checkpoint(f"auto_{iteration}")
                self.verified_since_checkpoint = 0
        
        logger.warning(f"[{task_id}] Build loop ended after {iteration} iterations")
    
    def _find_actionable_nodes(self) -> List[ManifestNode]:
        """Find nodes that can be processed now."""
        actionable = []
        
        for node in self.manifest.nodes.values():
            if self._is_actionable(node):
                actionable.append(node)
        
        # Sort by priority:
        # 1. Deepest first (leaves before parents)
        # 2. ROOT socket parts first (they define parent bbox for siblings)
        # 3. Then alphabetically for determinism
        def sort_key(n: ManifestNode) -> tuple:
            is_root_socket = (
                n.kind == NodeKind.PART and 
                n.attachment and 
                n.attachment.socket_type == SocketType.ROOT
            )
            return (-n.hierarchy_depth, 0 if is_root_socket else 1, n.label)
        
        actionable.sort(key=sort_key)
        
        return actionable
    
    def _is_actionable(self, node: ManifestNode) -> bool:
        """Check if a node can be processed now.

        Delegates ordering decisions to the DAG frontier so that
        BOOLEAN_TARGET, SIBLING_ROOT_REF, and CROSS_REFERENCE edges are
        the single source of truth for build ordering.
        """
        from .node_types import SocketType, CROSS_REFERENCE_SOCKETS

        # Already done or in progress
        if node.state in (NodeState.VERIFIED, NodeState.SKIPPED,
                          NodeState.BUILDING, NodeState.VERIFYING, NodeState.MERGING):
            return False

        # Failed and can't retry
        if node.state == NodeState.FAILED and not node.can_retry():
            return False

        if node.kind in (NodeKind.PART, NodeKind.DEFINITION, NodeKind.INSTANCE):
            # Parent must have finished decomposition
            if node.parent_id:
                parent = self.manifest.nodes.get(node.parent_id)
                if not parent:
                    return False
                if parent.state == NodeState.FAILED:
                    return False
                if parent.state == NodeState.DECOMPOSING:
                    return False
                if parent.state == NodeState.PLANNED and not parent.children_ids:
                    return False

                # Ensure parent assembly has its transform computed (lazy init).
                # If the parent's transform is still deferred (world_matrix is None
                # after the attempt), the child cannot be placed yet — block it.
                if parent.kind in (NodeKind.ASSEMBLY, NodeKind.MODEL):
                    if parent.transform_state and parent.transform_state.world_matrix is None:
                        self._ensure_assembly_transform(parent)
                    if parent.transform_state and parent.transform_state.world_matrix is None:
                        # Parent transform still unresolved (ROOT sibling not built yet).
                        # Block this child until the parent can be placed.
                        return False

            # Delegate ordering to DAG: all semantic edges (BOOLEAN_TARGET,
            # SIBLING_ROOT_REF, CROSS_REFERENCE) must be satisfied.
            if self.dag:
                blockers = self.dag.get_blocked_by(node.node_id)
                for block in blockers:
                    blocker = self.manifest.nodes.get(block.blocker_id)
                    if blocker is None:
                        # FIX: Missing blocker - this is a DAG integrity issue
                        # Log it clearly and fail the node with actionable error
                        logger.error(
                            f"[actionable] {node.label}: DAG blocker {block.blocker_id} not found in manifest. "
                            f"This indicates a DAG integrity issue or orphaned dependency."
                        )
                        self._handle_failure(
                            node,
                            f"DAG blocker {block.blocker_id} not found in manifest",
                            "dag_integrity",
                        )
                        return False
                    # Permanently failed required blocker — fail this node immediately
                    if blocker.state == NodeState.FAILED and not blocker.can_retry():
                        dep = self.dag.get_dependency(node.node_id, block.blocker_id)
                        if dep and dep.required:
                            logger.warning(
                                f"[actionable] {node.label}: required blocker "
                                f"'{blocker.label}' permanently failed — failing immediately"
                            )
                            if node.state == NodeState.RETRYING:
                                # RETRYING → FAILED is not a valid transition;
                                # exhaust retries by going straight to SKIPPED.
                                self.manifest.transition(node.node_id, NodeState.SKIPPED)
                            else:
                                self._handle_failure(
                                    node,
                                    f"Required blocker '{blocker.label}' permanently failed",
                                    "prerequisite",
                                )
                            return False
                    # FIX: Log blocker state more clearly
                    logger.debug(
                        f"[actionable] {node.label}: blocked by {blocker.label} "
                        f"(state={blocker.state.value}, kind={blocker.kind.value}, depth={blocker.hierarchy_depth})"
                    )
                    return False

            return node.state in (NodeState.PLANNED, NodeState.READY, NodeState.RETRYING)

        elif node.kind in (NodeKind.ASSEMBLY, NodeKind.MODEL):
            if not node.children_ids:
                # PLANNED with no children = decomposition never ran or failed silently.
                # Only treat as a leaf if READY (decomposer explicitly left it childless).
                return node.state == NodeState.READY

            all_done = self.manifest.all_children_done(node.node_id)
            if all_done and node.state in (NodeState.PLANNED, NodeState.READY):
                return True

            return False

        return False
    
    def _is_deadlocked(self) -> bool:
        """Check if build is deadlocked (no progress possible)."""
        # If any node is still processing, not deadlocked
        for node in self.manifest.nodes.values():
            if node.state in (NodeState.BUILDING, NodeState.VERIFYING, 
                              NodeState.MERGING, NodeState.DECOMPOSING):
                return False
        
        # If any node is actionable, not deadlocked
        if self._find_actionable_nodes():
            return False
        
        # If root is done, not deadlocked
        if self.manifest.is_root_resolved():
            return False
        
        # If any required node is still pending (not terminal), the build is
        # blocked but not necessarily deadlocked — return False so the loop
        # keeps waiting rather than terminating prematurely.
        for node in self.manifest.nodes.values():
            if node.importance == NodeImportance.REQUIRED:
                if node.state not in (NodeState.VERIFIED, NodeState.FAILED, NodeState.SKIPPED):
                    return False

        # If any ASSEMBLY/MODEL is still in a non-terminal state, it needs to
        # run _process_assembly to cascade-fail itself — not deadlocked yet.
        for node in self.manifest.nodes.values():
            if node.kind in (NodeKind.ASSEMBLY, NodeKind.MODEL):
                if node.state not in (NodeState.VERIFIED, NodeState.FAILED, NodeState.SKIPPED):
                    return False

        return True
    
    def _find_root_part_in_assembly(self, assembly: ManifestNode) -> Optional[ManifestNode]:
        """Find the ROOT part inside an assembly.
        
        Recursively searches for the ROOT part that defines the assembly's geometry.
        For nested assemblies, this may need to look inside child assemblies.
        """
        for cid in assembly.children_ids:
            child = self.manifest.nodes.get(cid)
            if not child:
                continue
            
            if child.kind == NodeKind.PART:
                child_socket = child.attachment.socket_type if child.attachment else None
                if child_socket == SocketType.ROOT:
                    return child
            elif child.kind == NodeKind.ASSEMBLY:
                # Check if this child assembly has ROOT socket
                child_socket = child.attachment.socket_type if child.attachment else None
                if child_socket == SocketType.ROOT:
                    # Recursively find ROOT part inside this assembly
                    return self._find_root_part_in_assembly(child)
        
        return None
    
    def _ensure_assembly_transform(self, assembly: ManifestNode) -> None:
        """Ensure an assembly has its local_transform and world_matrix computed.
        
        Phase 3: This is called lazily when a child part needs the parent
        assembly's world_matrix. It computes the assembly's transform chain
        up to the root.
        
        Cache validity uses the revision/parent_revision mechanism:
        - world_matrix is None  -> never computed, must compute
        - world_matrix exists but parent_revision stale -> must recompute
        - world_matrix exists and parent_revision current -> cache hit
        
        Using revision == 0 as a proxy for "not yet computed" is WRONG because
        revision tracks local_transform mutations, not world_matrix existence.
        A ROOT assembly legitimately has revision == 0 (identity, never mutated)
        and a valid world_matrix.
        
        FIX: For deep hierarchies, retry deferred assemblies when ROOT sibling becomes verified.
        """
        from .stages import Stage4Resolver
        from .transforms import LocalTransform
        
        # Determine parent revision for cache validity check
        parent_revision = -1
        if assembly.parent_id:
            parent = self.manifest.nodes.get(assembly.parent_id)
            if parent and parent.transform_state:
                parent_revision = parent.transform_state.revision
        
        # Skip if world_matrix exists AND is still valid for the current parent revision
        # AND Stage 4 has actually resolved this assembly (not just a deferred identity).
        if (assembly.transform_state and
                assembly.transform_state.world_matrix is not None and
                assembly.transform_state.is_resolved and
                assembly.transform_state.is_world_valid(parent_revision)):
            return
        
        # First, ensure parent's transform is computed (recursive)
        if assembly.parent_id:
            parent = self.manifest.nodes.get(assembly.parent_id)
            if parent and parent.kind in (NodeKind.ASSEMBLY, NodeKind.MODEL):
                self._ensure_assembly_transform(parent)
        
        # Compute this assembly's local_transform via Stage 4 only if
        # set_local_transform was never called (is_resolved=False means Stage 4
        # hasn't run for this node yet; revision==0 is NOT a safe proxy because
        # a ROOT assembly legitimately has revision==0 with a valid identity transform).
        if assembly.transform_state:
            if not assembly.transform_state.is_resolved:
                try:
                    parent_world = None
                    if assembly.parent_id:
                        p = self.manifest.nodes.get(assembly.parent_id)
                        if p and p.transform_state:
                            parent_world = p.transform_state.world_matrix
                    solution = Stage4Resolver.run_assembly(assembly, self.manifest, parent_world)
                    # Only mark resolved if Stage 4 produced a real transform.
                    # A deferred identity (source contains 'deferred_no_ref_bbox')
                    # means the ROOT sibling wasn't built yet — leave is_resolved=False
                    # so the next call retries once geometry is available.
                    _src = solution.source or ""
                    is_deferred = "deferred_no_ref_bbox" in _src or "fallback_identity" in _src
                    if not is_deferred:
                        assembly.transform_state.set_local_transform(solution.local_transform)
                        assembly.attachment.local_offset = list(solution.local_transform.position)
                        assembly.attachment.local_rotation = list(solution.local_transform.rotation)
                        logger.debug(
                            f"_ensure_assembly_transform: {assembly.label} -> "
                            f"local_pos={[round(p, 4) for p in solution.local_transform.position]}"
                        )
                    else:
                        # FIX: Check if ROOT sibling is now verified and retry
                        root_sibling = self._find_root_part_in_assembly(assembly)
                        if root_sibling and root_sibling.state == NodeState.VERIFIED:
                            logger.info(
                                f"_ensure_assembly_transform: {assembly.label} ROOT sibling {root_sibling.label} "
                                f"is now verified, retrying transform computation"
                            )
                            # Force retry by setting is_resolved=False if it was set
                            assembly.transform_state.is_resolved = False
                            # Recursive retry with updated context
                            parent_world = None
                            if assembly.parent_id:
                                p = self.manifest.nodes.get(assembly.parent_id)
                                if p and p.transform_state:
                                    parent_world = p.transform_state.world_matrix
                            solution = Stage4Resolver.run_assembly(assembly, self.manifest, parent_world)
                            _src_retry = solution.source or ""
                            is_deferred_retry = "deferred_no_ref_bbox" in _src_retry or "fallback_identity" in _src_retry
                            if not is_deferred_retry:
                                assembly.transform_state.set_local_transform(solution.local_transform)
                                assembly.attachment.local_offset = list(solution.local_transform.position)
                                assembly.attachment.local_rotation = list(solution.local_transform.rotation)
                                logger.debug(
                                    f"_ensure_assembly_transform: {assembly.label} retry succeeded -> "
                                    f"local_pos={[round(p, 4) for p in solution.local_transform.position]}"
                                )
                            else:
                                logger.warning(
                                    f"_ensure_assembly_transform: {assembly.label} retry still deferred, "
                                    f"may indicate circular dependency or missing geometry"
                                )
                        else:
                            logger.debug(
                                f"_ensure_assembly_transform: {assembly.label} deferred "
                                f"(ROOT sibling not built yet or resolver failed), will retry"
                            )
                except Exception as e:
                    logger.warning(f"_ensure_assembly_transform: {assembly.label} failed: {e}")
            
            # Propagate world transform (recomputes world_matrix from local + parent)
            self.manifest.propagate_transforms_from(assembly.node_id)

    
    # ══════════════════════════════════════════════════════════════════════
    # Part Processing
    # ══════════════════════════════════════════════════════════════════════
    
    # Pipeline of (output_key, method_name) pairs executed in order for each PART.
    # Async methods receive (node, task_id, model_id); sync methods receive (node, task_id).
    # To add a new stage (e.g. UV-unwrap after build), append:
    #   ("stage5_uv", "_run_stage5_uv")
    _PART_STAGE_PIPELINE = [
        ("stage2", "_run_stage2"),   # async: dimension resolution
        ("stage3", "_run_stage3"),   # async: semantic attachment
        ("stage4", "_run_stage4"),   # sync:  transform resolution
    ]

    async def _process_part(
        self,
        node: ManifestNode,
        task_id: str,
        model_id: Optional[str],
    ) -> None:
        """Process a PART node: pipeline stages → build → verify."""
        from .node_types import SocketType
        from .transforms import validate_local_transform

        try:
            if node.state == NodeState.PLANNED:
                self.manifest.transition(node.node_id, NodeState.READY)
            elif node.state == NodeState.RETRYING:
                self.manifest.transition(node.node_id, NodeState.READY)

            # ── Run stage pipeline ────────────────────────────────────────
            for output_key, method_name in self._PART_STAGE_PIPELINE:
                if output_key not in node.stage_outputs:
                    try:
                        method = getattr(self, method_name)
                        if asyncio.iscoroutinefunction(method):
                            await method(node, task_id, model_id)
                        else:
                            method(node, task_id)
                    except Exception as e:
                        # FIX: Catch stage failures early and fail the node with clear error
                        logger.error(
                            f"[{task_id}] Stage {output_key} failed for {node.label}: {e}"
                        )
                        self._handle_failure(
                            node,
                            f"Stage {output_key} failed: {str(e)}",
                            "stage_execution",
                        )
                        return  # Exit early - don't continue to build with invalid data
            
            # ── Phase 3: Validate local transform before hierarchy insertion ──
            if node.transform_state and node.transform_state.local_transform:
                errors = validate_local_transform(
                    node.transform_state.local_transform,
                    context=f"{node.label} Stage 4 output",
                )
                if errors:
                    for err in errors:
                        logger.warning(f"[{task_id}] Transform validation: {err}")
            
            # ── Phase 3: Propagate world transforms via new system ────────
            # This computes world_matrix for this node using hierarchy composition
            # BEFORE the legacy executor runs, so we can compare
            self.manifest.propagate_transforms_from(node.node_id)
            
            # ── Build in Blender ─────────────────────────────────────────
            self.manifest.transition(node.node_id, NodeState.BUILDING)
            
            # Check if this is a BOOLEAN_CUT node
            is_boolean_cut = (
                node.attachment and 
                node.attachment.socket_type == SocketType.BOOLEAN_CUT
            )
            
            if is_boolean_cut:
                await self._build_boolean_cut(node, task_id)
            else:
                await self._build_part(node, task_id)
            
            # ── Verify ───────────────────────────────────────────────────
            self.manifest.transition(node.node_id, NodeState.VERIFYING)
            
            if is_boolean_cut:
                # Boolean cuts don't have objects to verify - just mark as verified
                node.verification_result = {
                    "verified": True,
                    "timestamp": time.time(),
                    "type": "boolean_cut",
                }
                verified = True
                await broadcast_blender_trace(task_id, 5, f"Verified {node.label} (boolean cut)", "complete")
            else:
                verified = await self._verify_part(node, task_id)
            
            if verified:
                self.manifest.transition(node.node_id, NodeState.VERIFIED)
                self.verified_since_checkpoint += 1
                # Freeze the local transform now that the node is verified.
                # This prevents retries from silently overwriting a confirmed position.
                if node.transform_state:
                    node.transform_state.freeze()
                logger.info(f"[{task_id}] Verified: {node.label}")
            else:
                raise Exception("Verification failed")
                
        except Exception as e:
            logger.warning(f"[{task_id}] Part {node.label} failed: {e}")
            self._handle_failure(node, str(e), "build")
    
    async def _run_stage2(
        self,
        node: ManifestNode,
        task_id: str,
        model_id: Optional[str],
    ) -> None:
        """Run Stage 2 (dimensions) for a part."""
        self._set_phase(BuildPhase.STAGING, f"Stage 2: {node.label}")
        
        output = await Stage2Dimensions.run(
            node=node,
            manifest=self.manifest,
            model_manager=self.model_manager,
            task_id=task_id,
            model_id=model_id,
        )
        
        # Store output and apply to geometry
        node.stage_outputs["stage2"] = output.to_dict()
        if node.geometry:
            output.apply_to_geometry(node.geometry)
        
        await broadcast_blender_trace(task_id, 2, f"Dimensions: {node.label}", "complete")
        logger.debug(f"[{task_id}] Stage 2 complete for {node.label}: {output.to_dict()}")
    
    async def _run_stage3(
        self,
        node: ManifestNode,
        task_id: str,
        model_id: Optional[str],
    ) -> None:
        """Run Stage 3 (semantics) for a part."""
        self._set_phase(BuildPhase.STAGING, f"Stage 3: {node.label}")
        
        semantics = await Stage3Semantics.run(
            node=node,
            manifest=self.manifest,
            model_manager=self.model_manager,
            task_id=task_id,
            model_id=model_id,
        )
        
        # Store output and apply to attachment
        node.stage_outputs["stage3"] = semantics
        Stage3Semantics.apply_to_attachment(node.attachment, semantics)
        
        await broadcast_blender_trace(task_id, 3, f"Semantics: {node.label}", "complete")
        logger.debug(f"[{task_id}] Stage 3 complete for {node.label}: {semantics}")
    
    def _run_stage4(self, node: ManifestNode, task_id: str = "") -> None:
        """Run Stage 4 (transform resolution) for a part.
        
        Phase 2 Migration:
        - Stage 4 now returns (ResolvedTransform, AttachmentSolution)
        - ResolvedTransform feeds legacy executor path (attachment.local_offset/rotation)
        - AttachmentSolution feeds new transform system (transform_state.local_transform)
        - Both paths run in parallel for comparison
        
        For cross-reference sockets (RELATIVE_TO, BRIDGE, STRUT, RADIAL_BRIDGE),
        this runs pass1 first, then pass2 after collecting world positions.
        
        FIX: Validate Stage 2 data exists before running Stage 4.
        """
        from .stages import Stage4Resolver
        from .stages.stage4_resolver import BBox, AttachmentSolution
        
        self._set_phase(BuildPhase.STAGING, f"Stage 4: {node.label}")
        
        # FIX: Validate Stage 2 data exists - Stage 4 requires geometry dimensions
        if "stage2" not in node.stage_outputs:
            logger.error(
                f"[{task_id}] Stage 4 cannot run for {node.label}: "
                f"Stage 2 data missing. This indicates a pipeline error."
            )
            raise Exception(f"Stage 2 data missing for {node.label}, cannot run Stage 4")
        
        stage2_data = node.stage_outputs["stage2"]
        if not stage2_data or not isinstance(stage2_data, dict):
            logger.error(
                f"[{task_id}] Stage 4 cannot run for {node.label}: "
                f"Stage 2 data invalid: {stage2_data}"
            )
            raise Exception(f"Stage 2 data invalid for {node.label}, cannot run Stage 4")
        
        # Check if this is a cross-reference socket that needs pass2
        socket = node.attachment.socket_type if node.attachment else None
        is_cross_ref = Stage4Resolver.is_cross_reference_socket(socket) if socket else False
        
        if is_cross_ref:
            # Pass 1: Get placeholder transform
            transform, solution = Stage4Resolver.run(node, self.manifest)
            
            # Pass 2: Resolve using world matrices of built nodes.
            # Prefer transform_state.world_matrix (new path). Only fall back to
            # legacy world_position if transform_state was never populated —
            # e.g. a node built before USE_HIERARCHICAL_TRANSFORMS was enabled.
            # Do NOT mix the two sources for the same node: if world_matrix is
            # set, it is authoritative and world_position may be stale.
            from .transforms import WorldMatrix as _WM
            world_matrices = {}
            world_bboxes = {}

            for n in self.manifest.nodes.values():
                if n.transform_state and n.transform_state.world_matrix is not None:
                    # New path — authoritative
                    world_matrices[n.node_id] = n.transform_state.world_matrix
                elif n.world_position is not None and n.transform_state is None:
                    # Legacy-only node (pre-migration): build WorldMatrix from
                    # world_position. Only used when transform_state is absent
                    # entirely, not just when world_matrix hasn't been computed yet.
                    from .transforms import LocalTransform as _LT
                    world_matrices[n.node_id] = _WM.from_local(_LT(
                        position=list(n.world_position),
                        rotation=list(n.world_rotation) if n.world_rotation else [0.0, 0.0, 0.0],
                    ))
                if n.bounding_box:
                    bb = n.bounding_box
                    world_bboxes[n.node_id] = BBox(
                        min_x=bb["min"][0], max_x=bb["max"][0],
                        min_y=bb["min"][1], max_y=bb["max"][1],
                        min_z=bb["min"][2], max_z=bb["max"][2],
                    )

            # Run pass2 resolution
            transform, solution = Stage4Resolver.resolve_cross_reference(
                node, self.manifest, world_matrices, world_bboxes
            )
            logger.debug(f"Stage 4 pass2 complete for {node.label}: {transform.resolution_method}")
        else:
            # Standard resolution (single pass) - returns tuple
            transform, solution = Stage4Resolver.run(node, self.manifest)
            logger.debug(f"Stage 4 complete for {node.label}: {transform.resolution_method}")
        
        # ── Legacy path: store in attachment ──
        node.stage_outputs["stage4"] = transform.to_dict()
        node.attachment.local_offset = transform.offset
        node.attachment.local_rotation = transform.rotation
        
        # ── New path: store in transform_state ──
        # This populates the hierarchical transform system
        if node.transform_state is not None:
            node.transform_state.set_local_transform(solution.local_transform)
            logger.debug(
                f"Stage 4 transform_state for {node.label}: "
                f"pos={solution.local_transform.position}, "
                f"rot={[round(r, 3) for r in solution.local_transform.rotation]}"
            )
    
    # ══════════════════════════════════════════════════════════════════════
    # Phase 3: Shadow Transform System
    # ══════════════════════════════════════════════════════════════════════
    
    def _propagate_new_world_transform(self, node: ManifestNode, task_id: str) -> None:
        """Phase 3: Compute world_matrix via pure hierarchical transform composition.
        
        This is the NEW transform system. It computes:
            world_matrix = parent.world_matrix @ node.local_matrix
        
        No geometry lookup, no bbox, no socket resolution inside this method.
        All that complexity is handled upstream by Stage 4 (for PARTs) or
        run_assembly (for ASSEMBLYs).
        
        CRITICAL: This method should be "boring" - just matrix composition.
        """
        from .transforms import WorldMatrix, LocalTransform
        
        if node.transform_state is None:
            logger.warning(f"[{task_id}] {node.label}: No transform_state, skipping propagation")
            return
        
        # Get parent's world matrix and revision
        parent_world = None
        parent_revision = -1
        
        if node.parent_id:
            parent = self.manifest.nodes.get(node.parent_id)
            if parent and parent.transform_state and parent.transform_state.world_matrix:
                parent_world = parent.transform_state.world_matrix
                parent_revision = parent.transform_state.revision
        
        # Compute this node's world matrix via pure composition
        world = node.transform_state.compute_world(parent_world, parent_revision)
        
        logger.debug(
            f"[{task_id}] Phase 3 propagate {node.label}: "
            f"local_pos={[round(p, 4) for p in node.transform_state.local_transform.position]}, "
            f"parent_world={'found' if parent_world else 'None'}, "
            f"world_pos={[round(p, 4) for p in world.position]}"
        )
    
    async def _stage_and_buffer_part(self, node: ManifestNode, task_id: str, model_id: Optional[str]) -> bool:
        """Run stages 2/3/4 and buffer geometry for a PART node. Returns True if buffered OK.

        Does NOT flush or verify — caller batches multiple nodes then flushes once.
        BOOLEAN_CUT nodes are skipped here; they need a live target and are handled
        individually by _process_part via the sim/fallback path.
        """
        from .node_types import SocketType
        from .transforms import validate_local_transform

        is_boolean_cut = node.attachment and node.attachment.socket_type == SocketType.BOOLEAN_CUT
        if is_boolean_cut:
            # Boolean cuts need a live target — process individually via _process_part
            await self._process_part(node, task_id, model_id)
            return False  # already fully handled, don't re-verify

        try:
            if node.state == NodeState.PLANNED:
                self.manifest.transition(node.node_id, NodeState.READY)
            elif node.state == NodeState.RETRYING:
                self.manifest.transition(node.node_id, NodeState.READY)

            # Run stage pipeline
            for output_key, method_name in self._PART_STAGE_PIPELINE:
                if output_key not in node.stage_outputs:
                    try:
                        method = getattr(self, method_name)
                        if asyncio.iscoroutinefunction(method):
                            await method(node, task_id, model_id)
                        else:
                            method(node, task_id)
                    except Exception as e:
                        logger.error(f"[{task_id}] Stage {output_key} failed for {node.label}: {e}")
                        self._handle_failure(node, f"Stage {output_key} failed: {str(e)}", "stage_execution")
                        return False

            if node.transform_state and node.transform_state.local_transform:
                errs = validate_local_transform(
                    node.transform_state.local_transform,
                    context=f"{node.label} Stage 4 output",
                )
                for err in errs:
                    logger.warning(f"[{task_id}] Transform validation: {err}")

            self._propagate_new_world_transform(node, task_id)
            self.manifest.transition(node.node_id, NodeState.BUILDING)

            # Check defer_modifiers
            defer_modifiers = False
            if node.attachment and node.attachment.socket_type == SocketType.ROOT and node.parent_id:
                parent = self.manifest.nodes.get(node.parent_id)
                if parent:
                    for sib_id in parent.children_ids:
                        if sib_id == node.node_id:
                            continue
                        sib = self.manifest.nodes.get(sib_id)
                        if sib and sib.attachment and sib.attachment.socket_type == SocketType.BOOLEAN_CUT:
                            if sib.state not in (NodeState.VERIFIED, NodeState.SKIPPED, NodeState.FAILED):
                                defer_modifiers = True
                                break

            result = await self._executor.build_node(node, self.manifest, defer_modifiers=defer_modifiers)
            if not result.ok:
                self._handle_failure(node, f"Build failed: {result.error}", "build")
                return False

            node.blender_objects = result.blender_objects
            node.bounding_box = result.bounding_box
            self.manifest.record_blender_op()
            return True

        except Exception as e:
            logger.warning(f"[{task_id}] Stage/buffer failed for {node.label}: {e}")
            self._handle_failure(node, str(e), "build")
            return False

    async def _verify_staged_part(self, node: ManifestNode, task_id: str) -> None:
        """Verify a PART node that was already buffered and flushed."""
        try:
            self.manifest.transition(node.node_id, NodeState.VERIFYING)
            verified = await self._verify_part(node, task_id)
            if verified:
                self.manifest.transition(node.node_id, NodeState.VERIFIED)
                self.verified_since_checkpoint += 1
                if node.transform_state:
                    node.transform_state.freeze()
                logger.info(f"[{task_id}] Verified: {node.label}")
            else:
                self._handle_failure(node, "Verification failed", "verify")
        except Exception as e:
            logger.warning(f"[{task_id}] Verify failed for {node.label}: {e}")
            self._handle_failure(node, str(e), "verify")

    async def _build_part(self, node: ManifestNode, task_id: str) -> None:
        """Build a part in Blender via MCP (sim path / fallback only).

        In the real MCP path, _stage_and_buffer_part + batch flush + _verify_staged_part
        are used instead. This method is kept for the no-MCP simulation path and
        for BOOLEAN_CUT nodes which need a live target.
        """
        self._set_phase(BuildPhase.BUILDING, f"Building: {node.label}")
        await broadcast_blender_trace(task_id, 5, f"Building {node.label}", "running")

        if not self.mcp_manager:
            logger.debug(f"[{task_id}] Simulated build for {node.label}")
            node.blender_objects = [f"obj_{node.label}"]
            # Use geometry-based bbox so BRIDGE/STRUT pass-2 resolvers get
            # accurate extents instead of a misleading unit cube.
            from .stages.stage4_resolver import BBox
            if node.geometry and "stage2" in node.stage_outputs:
                bbox = BBox.from_geometry(node.geometry, node.stage_outputs["stage2"])
                wp = list(node.transform_state.world_matrix.position) if (
                    node.transform_state and node.transform_state.world_matrix
                ) else [0.0, 0.0, 0.0]
                node.bounding_box = {
                    "min": [wp[0] + bbox.min_x, wp[1] + bbox.min_y, wp[2] + bbox.min_z],
                    "max": [wp[0] + bbox.max_x, wp[1] + bbox.max_y, wp[2] + bbox.max_z],
                }
            else:
                node.bounding_box = {"min": [-0.5, -0.5, -0.5], "max": [0.5, 0.5, 0.5]}
            self.manifest.record_blender_op()
            return

        # Check if this ROOT part has pending BOOLEAN_CUT siblings
        defer_modifiers = False
        if node.attachment and node.attachment.socket_type == SocketType.ROOT:
            if node.parent_id:
                parent = self.manifest.nodes.get(node.parent_id)
                if parent:
                    for sib_id in parent.children_ids:
                        if sib_id == node.node_id:
                            continue
                        sib = self.manifest.nodes.get(sib_id)
                        if sib and sib.attachment:
                            if sib.attachment.socket_type == SocketType.BOOLEAN_CUT:
                                if sib.state not in (NodeState.VERIFIED, NodeState.SKIPPED, NodeState.FAILED):
                                    defer_modifiers = True
                                    logger.info(f"[{task_id}] Deferring modifiers for {node.label} (has pending BOOLEAN_CUT sibling)")
                                    break

        result = await self._executor.build_node(node, self.manifest, defer_modifiers=defer_modifiers)
        if not result.ok:
            raise Exception(f"Build failed: {result.error}")

        node.blender_objects = result.blender_objects
        node.bounding_box = result.bounding_box
        self.manifest.record_blender_op()

        # Flush immediately (used when called from _process_part directly, e.g. boolean cut path)
        if self._executor._script_buffer:
            flush_ok = await self._executor.flush(self.manifest)
            if not flush_ok:
                raise Exception(f"Flush failed for {node.label} — object may not exist in Blender")
    
    async def _build_boolean_cut(self, node: ManifestNode, task_id: str) -> None:
        """Build a boolean cut: create cutter, apply to target, delete cutter.
        
        After the cut completes, if the target had deferred modifiers, apply them now.
        """
        from .node_types import SocketType
        
        self._set_phase(BuildPhase.BUILDING, f"Boolean cut: {node.label}")
        await broadcast_blender_trace(task_id, 5, f"Boolean cut {node.label}", "running")
        
        if not self.mcp_manager:
            # No MCP - simulate
            logger.debug(f"[{task_id}] Simulated boolean cut for {node.label}")
            node.blender_objects = []
            self.manifest.record_blender_op()
            return
        
        # Find the target node (parent or sibling with ROOT socket)
        target_node = None
        if node.parent_id:
            parent = self.manifest.nodes.get(node.parent_id)
            if parent:
                # Look for ROOT sibling (the main body to cut into)
                for sib_id in parent.children_ids:
                    if sib_id == node.node_id:
                        continue
                    sib = self.manifest.nodes.get(sib_id)
                    if sib and sib.attachment:
                        if sib.attachment.socket_type == SocketType.ROOT:
                            if sib.state == NodeState.VERIFIED and sib.blender_objects:
                                target_node = sib
                                break
                
                # If no ROOT sibling, try parent itself if it has objects
                if not target_node and parent.blender_objects:
                    target_node = parent
        
        if not target_node:
            raise Exception(f"No target found for boolean cut '{node.label}'")
        
        logger.info(f"[{task_id}] Boolean cut: {node.label} -> {target_node.label}")
        
        # Execute boolean cut (live MCP call — flush must have run before booleans)
        result = await self._executor.build_boolean_cut(node, target_node, self.manifest)
        
        if not result.ok:
            raise Exception(f"Boolean cut failed: {result.error}")
        
        node.blender_objects = result.blender_objects  # Empty - cutter was deleted
        self.manifest.record_blender_op()
        
        # Check if this was the last BOOLEAN_CUT sibling
        # If so, apply deferred modifiers to the target
        if target_node.stage_outputs.get("_pending_modifiers"):
            # Check if any other BOOLEAN_CUT siblings are still pending
            has_pending_cuts = False
            if node.parent_id:
                parent = self.manifest.nodes.get(node.parent_id)
                if parent:
                    for sib_id in parent.children_ids:
                        if sib_id == node.node_id:
                            continue
                        sib = self.manifest.nodes.get(sib_id)
                        if sib and sib.attachment:
                            if sib.attachment.socket_type == SocketType.BOOLEAN_CUT:
                                if sib.state not in (NodeState.VERIFIED, NodeState.SKIPPED, NodeState.FAILED, NodeState.VERIFYING):
                                    has_pending_cuts = True
                                    break
            
            if not has_pending_cuts:
                logger.info(f"[{task_id}] Applying deferred modifiers to {target_node.label}")
                mod_result = await self._executor.apply_deferred_modifiers(target_node, self.manifest)
                if not mod_result.ok:
                    logger.warning(f"[{task_id}] Deferred modifier application failed: {mod_result.error}")
    
    async def _verify_part(self, node: ManifestNode, task_id: str) -> bool:
        """Verify a built part."""
        self._set_phase(BuildPhase.VERIFYING, f"Verifying: {node.label}")
        
        # Basic verification - check that objects were created
        if not node.blender_objects:
            return False
        
        if self.mcp_manager:
            # Use shared executor for verification (live MCP call — objects exist after flush)
            result = await self._executor.verify_node(node)
            
            if not result.ok:
                logger.warning(
                    f"[{task_id}] Verification failed for {node.label}: {result.checks_failed} "
                    f"(mesh_issues={result.mesh_issues}, dims={result.dimension_mismatches})"
                )
                return False
            
            node.verification_result = {
                "verified": True,
                "timestamp": time.time(),
                "checks_passed": result.checks_passed,
            }
            await broadcast_blender_trace(task_id, 5, f"Verified {node.label}", "complete", {
                "objects": node.blender_objects
            })
            return True
        
        # Simulated verification
        node.verification_result = {
            "verified": True,
            "timestamp": time.time(),
            "objects": node.blender_objects,
        }
        await broadcast_blender_trace(task_id, 5, f"Verified {node.label}", "complete", {
            "objects": node.blender_objects
        })
        
        return True

    
    # ══════════════════════════════════════════════════════════════════════
    # Assembly Processing
    # ══════════════════════════════════════════════════════════════════════
    
    async def _process_assembly_compat(
        self,
        node: ManifestNode,
        task_id: str,
        model_id: Optional[str],
    ) -> None:
        """Shim so ASSEMBLY/MODEL fit the uniform (node, task_id, model_id) handler signature."""
        await self._process_assembly(node, task_id)

    async def _process_assembly(
        self,
        node: ManifestNode,
        task_id: str,
    ) -> None:
        """Process an ASSEMBLY node: compute transform, then merge verified children.
        
        Phase 3: Assemblies now get local_transform computed via Stage4Resolver.run_assembly()
        so that propagation is purely hierarchical.
        """
        try:
            # ── Phase 3: Compute assembly's local_transform ──────────────
            # This must happen BEFORE children are processed so they can
            # use the assembly's world_matrix as their parent reference.
            # Only compute if set_local_transform was never called.
            # is_resolved=False means Stage 4 hasn't run yet.
            # Do NOT use revision==0 — a ROOT assembly legitimately has
            # revision==0 with a valid identity transform and must not be
            # recomputed on every retry.
            if node.transform_state and not node.transform_state.is_resolved:
                from .stages import Stage4Resolver
                from .stages.stage4_resolver import AttachmentSolution
                
                try:
                    parent_world = None
                    if node.parent_id:
                        p = self.manifest.nodes.get(node.parent_id)
                        if p and p.transform_state:
                            parent_world = p.transform_state.world_matrix
                    solution = Stage4Resolver.run_assembly(node, self.manifest, parent_world)
                    # Only commit if Stage 4 produced a real transform (not a
                    # deferred identity waiting for the ROOT sibling to be built).
                    _src = solution.source or ""
                    is_deferred = "deferred_no_ref_bbox" in _src or "fallback_identity" in _src
                    if not is_deferred:
                        node.transform_state.set_local_transform(solution.local_transform)
                        node.attachment.local_offset = list(solution.local_transform.position)
                        node.attachment.local_rotation = list(solution.local_transform.rotation)
                        logger.debug(
                            f"[{task_id}] Assembly {node.label} local_transform: "
                            f"pos={[round(p, 4) for p in solution.local_transform.position]}"
                        )
                    else:
                        raise RuntimeError(
                            f"TRANSFORM_DEFERRED_UNRESOLVED: Assembly {node.label} cannot be positioned ({_src})"
                        )
                except Exception as e:
                    logger.error(f"[{task_id}] Assembly {node.label} Stage4 failed: {e}")
                    raise
            
            # ── Propagate world transform ────────────────────────────────
            self.manifest.propagate_transforms_from(node.node_id)
            
            # Handle assemblies with no children.
            # READY + no children = decomposer explicitly left it childless (depth limit etc.) → leaf.
            # PLANNED + no children = decomposition never ran or failed silently → re-decompose.
            if not node.children_ids:
                expected = node.expected_child_count
                # FIX: Recursively search for nested children at arbitrary depth
                nested = node.stage_outputs.get("decomposition_hint", {}).get("_nested_children")
                
                # Recursive function to find nested children at any depth
                def find_nested_children(children, depth=0):
                    """Recursively search for _nested_children in assembly children.
                    
                    Will work through the entire nested structure regardless of depth,
                    handling varying sub-nest depths automatically.
                    """
                    if depth > 20:  # Generous safety limit for very deep hierarchies
                        return None
                    for child in children:
                        if child.get("kind") == "assembly":
                            if "_nested_children" in child:
                                return child["_nested_children"]
                            if "children" in child:
                                result = find_nested_children(child["children"], depth + 1)
                                if result:
                                    return result
                    return None
                
                # Also check if there are nested children in the children array (LLM nested structure)
                if not nested:
                    decomp_hint = node.stage_outputs.get("decomposition_hint", {})
                    if "children" in decomp_hint:
                        nested = find_nested_children(decomp_hint["children"])
                
                if expected or nested:
                    # FIX: Extract nested children and pass them to re-decomposition
                    # This handles assemblies that have pre-parsed children from LLM but weren't committed
                    # Also handle READY state - the node may have transitioned to READY without committing nested children
                    if node.state in (NodeState.PLANNED, NodeState.RETRYING, NodeState.READY):
                        logger.warning(
                            f"[{task_id}] Assembly {node.label} (state={node.state}) has no children but has "
                            f"expected_child_count={expected} or nested_children={len(nested) if nested else 0} — "
                            f"re-running decomposition with pre-parsed children"
                        )
                        # FIX: Transition to READY before attempting decomposition
                        # This ensures the assembly doesn't get marked as a leaf if decomposition fails
                        if node.state == NodeState.PLANNED:
                            self.manifest.transition(node.node_id, NodeState.READY)
                        
                        try:
                            from .decomposer import RecursiveDecomposer
                            decomposer = RecursiveDecomposer(limits=self.limits, max_llm_calls=5)
                            await decomposer._decompose_node(
                                node=node,
                                manifest=self.manifest,
                                tree=ContainmentTree(self.manifest, self.limits),
                                model_manager=self.model_manager,
                                task_id=task_id,
                                model_id=None,
                                stats={},
                                pre_parsed_children=nested,  # FIX: Pass nested children!
                            )
                        except Exception as _e:
                            logger.warning(f"[{task_id}] Re-decomposition of {node.label} failed: {_e}")
                            raise RuntimeError(
                                f"DECOMPOSITION_COMMIT_INCOMPLETE: assembly has an expected "
                                f"subtree (expected_child_count={expected}) but no committed children"
                            ) from _e
                        # If children were added, let the build loop pick them up next iteration.
                        # If still no children, fall through to leaf handling below.
                        if node.children_ids:
                            self.dag = DependencyDAG.from_manifest(self.manifest)
                            self.manifest.record_event(
                                "graph_recompiled",
                                node_id=node.node_id,
                                details={"node_count": len(self.manifest.nodes)},
                            )
                            return
                        # A node with an expected or supplied subtree is not a
                        # deliberate leaf.  Do not convert a depth/budget stop
                        # into a successful leaf assembly.
                        raise RuntimeError(
                            f"DECOMPOSITION_COMMIT_INCOMPLETE: assembly has an expected "
                            f"subtree (expected_child_count={expected}) but no committed children"
                        )
                    else:
                        # READY state with no children but expected = decomposer explicitly left it childless
                        logger.info(
                            f"[{task_id}] Assembly {node.label} is READY with no children "
                            f"(decomposer left it childless, expected_child_count={expected})"
                        )

                logger.info(f"[{task_id}] Assembly {node.label} has no children (leaf assembly)")
                # Must follow proper state transitions: PLANNED -> READY -> MERGING -> VERIFIED
                if node.state == NodeState.PLANNED:
                    self.manifest.transition(node.node_id, NodeState.READY)
                if node.state == NodeState.READY:
                    self.manifest.transition(node.node_id, NodeState.MERGING)
                # Now we can transition to VERIFIED
                self.manifest.transition(node.node_id, NodeState.VERIFIED)
                node.verification_result = {
                    "verified": True,
                    "timestamp": time.time(),
                    "type": "leaf_assembly",
                    "child_count": 0,
                }
                self.verified_since_checkpoint += 1
                logger.info(f"[{task_id}] Assembly verified (leaf): {node.label}")
                return
            
            # Check if all children are done
            if not self.manifest.all_children_done(node.node_id):
                logger.debug(f"[{task_id}] Assembly {node.label} waiting for children")
                return
            
            # Required/optional split: named required failures → typed error
            failed_required = self.manifest.failed_required_children(node.node_id)
            if failed_required:
                error_msg = "Required child(ren) failed: " + ", ".join(failed_required[:5])
                logger.warning(f"[{task_id}] Assembly {node.label} failing: {error_msg}")
                self.manifest.transition(
                    node.node_id,
                    NodeState.FAILED,
                    error=error_msg,
                )
                return
            # Optional failures: let the assembly proceed as degraded, just log
            for cid in node.children_ids:
                child = self.manifest.nodes.get(cid)
                if child and child.state in (NodeState.FAILED, NodeState.SKIPPED):
                    if child.importance in (NodeImportance.OPTIONAL, NodeImportance.DECORATIVE):
                        logger.info(f"[{task_id}] Assembly {node.label}: optional child '{child.label}' failed, continuing as degraded")
            
            # Transition to MERGING
            if node.state == NodeState.PLANNED:
                self.manifest.transition(node.node_id, NodeState.READY)
            self.manifest.transition(node.node_id, NodeState.MERGING)
            
            self._set_phase(BuildPhase.MERGING, f"Merging: {node.label}")
            
            # Merge children
            await self._merge_assembly(node, task_id)
            
            # Verify merge
            verified = await self._verify_assembly(node, task_id)
            
            if verified:
                self.manifest.transition(node.node_id, NodeState.VERIFIED)
                self.verified_since_checkpoint += 1
                if node.transform_state:
                    node.transform_state.freeze()
                logger.info(f"[{task_id}] Assembly verified: {node.label}")
            else:
                raise Exception("Assembly verification failed")
                
        except Exception as e:
            logger.warning(f"[{task_id}] Assembly {node.label} failed: {e}")
            self._handle_failure(node, str(e), "merge")
    
    async def _merge_assembly(self, node: ManifestNode, task_id: str) -> None:
        """Merge verified children into an assembly."""
        if self.mcp_manager:
            # Buffer the empty + parenting fragment (no flush - do it at the end)
            result = await self._executor.merge_assembly(node, self.manifest)
            
            if not result.ok:
                raise Exception(f"Merge failed: {result.error}")
            
            node.blender_objects = result.blender_objects
            node.bounding_box = result.bounding_box
            self.manifest.record_blender_op()
            
            # FIX: Don't flush here - accumulate all assembly merges and flush once at the end
            # The flush will happen after the build loop completes or after all assemblies are merged
            return
        
        # Simulated merge - collect all blender objects from children
        all_objects = []
        for cid in node.children_ids:
            child = self.manifest.nodes.get(cid)
            if child and child.state == NodeState.VERIFIED:
                all_objects.extend(child.blender_objects)
        
        node.blender_objects = all_objects
        node.bounding_box = self._compute_assembly_bbox(node)
        self.manifest.record_blender_op()
        
        logger.debug(f"[{task_id}] Merged {len(all_objects)} objects into {node.label}")
    
    async def _establish_blender_hierarchy(self, task_id: str) -> None:
        """Second pass: establish parent-child relationships between assembly Empties.
        
        This runs after all assemblies are merged to ensure parent Empties exist.
        Also validates Empty position consistency with children.
        """
        if not self.mcp_manager:
            logger.debug(f"[{task_id}] Skipping hierarchy establishment (no MCP manager)")
            return
        
        # Collect all assembly nodes that have been merged
        assemblies = []
        for node in self.manifest.nodes.values():
            if node.kind in (NodeKind.ASSEMBLY, NodeKind.MODEL) and node.state == NodeState.VERIFIED and node.blender_objects:
                assemblies.append(node)
        
        if not assemblies:
            logger.debug(f"[{task_id}] No assemblies to hierarchy")
            return
        
        # Build hierarchy script
        script = '''
import bpy
import json

parentings = []
position_warnings = []

# Process each assembly and parent it to its parent assembly
'''
        
        for node in assemblies:
            if node.parent_id:
                parent_node = self.manifest.nodes.get(node.parent_id)
                if parent_node and parent_node.kind in (NodeKind.ASSEMBLY, NodeKind.MODEL):
                    # Find this assembly's Empty
                    empty_name = None
                    for obj_name in node.blender_objects:
                        if obj_name.startswith(f"{node.label}_assembly_"):
                            empty_name = obj_name
                            break
                    
                    # Find parent's Empty
                    parent_empty_name = None
                    if parent_node.blender_objects:
                        for obj_name in parent_node.blender_objects:
                            if obj_name.startswith(f"{parent_node.label}_assembly_"):
                                parent_empty_name = obj_name
                                break
                    
                    if empty_name and parent_empty_name:
                        script += f'''
# Parent {node.label} to {parent_node.label}
empty = bpy.data.objects.get("{empty_name}")
parent_empty = bpy.data.objects.get("{parent_empty_name}")
if empty and parent_empty:
    if empty.parent != parent_empty:
        empty.parent = parent_empty
        parentings.append([str(empty.name), str(parent_empty.name)])
'''
        
        # Add validation script at the end
        script += '''
# Validate Empty positions relative to children
for obj in bpy.data.objects:
    if obj.type == 'EMPTY' and "_assembly_" in obj.name:
        # Get all children of this Empty
        children = [child for child in bpy.data.objects if child.parent == obj]
        if children:
            # Compute centroid of child world positions
            child_positions = [list(child.matrix_world.translation) for child in children]
            centroid = [sum(p[i] for p in child_positions) / len(child_positions) for i in range(3)]
            empty_pos = list(obj.matrix_world.translation)
            # Check distance
            distance = ((empty_pos[0] - centroid[0])**2 + (empty_pos[1] - centroid[1])**2 + (empty_pos[2] - centroid[2])**2)**0.5
            if distance > 0.1:  # 10cm tolerance
                position_warnings.append([str(obj.name), float(distance), empty_pos, centroid])
'''

        script += '''
result = {"ok": True, "parentings": parentings, "position_warnings": position_warnings}
print("SENTINEL_OUTPUT_START" + json.dumps(result) + "SENTINEL_OUTPUT_END")
'''
        
        # Execute the hierarchy script via MCP manager
        try:
            result = await self.mcp_manager.call_locked(
                "blender",
                "execute_blender_code",
                {"code": script},
            )
            if isinstance(result, list):
                output = "".join(getattr(item, "text", str(item)) for item in result)
            elif isinstance(result, dict):
                output = result.get("output", result.get("text", ""))
            else:
                output = str(result)
            from core.blender_ops import parse_op_output
            data = parse_op_output(output)
            if data.get("ok"):
                parentings = data.get('parentings', [])
                warnings = data.get('position_warnings', [])
                logger.info(f"[{task_id}] Established {len(parentings)} parent-child relationships in Blender")
                if warnings:
                    logger.warning(f"[{task_id}] Found {len(warnings)} assembly Empties with position inconsistencies:")
                    for w in warnings:
                        if isinstance(w, (list, tuple)) and len(w) >= 2:
                            logger.warning(f"  - {w[0]}: {float(w[1]):.3f}m from child centroid")
                        elif isinstance(w, dict):
                            logger.warning(f"  - {w.get('empty')}: {float(w.get('distance', 0.0)):.3f}m from child centroid")
            else:
                logger.warning(f"[{task_id}] Hierarchy establishment failed: {data}")
        except Exception as e:
            logger.warning(f"[{task_id}] Hierarchy establishment error: {e}")
    
    def _compute_assembly_bbox(self, node: ManifestNode) -> Optional[Dict[str, List[float]]]:
        """Compute bounding box encompassing all children."""
        min_pt = [float('inf'), float('inf'), float('inf')]
        max_pt = [float('-inf'), float('-inf'), float('-inf')]
        
        has_bbox = False
        for cid in node.children_ids:
            child = self.manifest.nodes.get(cid)
            if child and child.bounding_box:
                has_bbox = True
                cmin = child.bounding_box.get("min", [0, 0, 0])
                cmax = child.bounding_box.get("max", [0, 0, 0])
                for i in range(3):
                    min_pt[i] = min(min_pt[i], cmin[i])
                    max_pt[i] = max(max_pt[i], cmax[i])
        
        if not has_bbox:
            return None
        
        return {"min": min_pt, "max": max_pt}
    
    async def _verify_assembly(self, node: ManifestNode, task_id: str) -> bool:
        """Verify a merged assembly."""
        self._set_phase(BuildPhase.VERIFYING, f"Verifying assembly: {node.label}")
        
        # Basic verification - check that we have objects
        if not node.blender_objects:
            return False
        
        # Check that all required children are verified
        for cid in node.children_ids:
            child = self.manifest.nodes.get(cid)
            if child and child.importance == NodeImportance.REQUIRED:
                if child.state != NodeState.VERIFIED:
                    return False
        
        node.verification_result = {
            "verified": True,
            "timestamp": time.time(),
            "child_count": len(node.children_ids),
            "object_count": len(node.blender_objects),
        }
        
        return True
    
    # ══════════════════════════════════════════════════════════════════════
    # Failure Handling
    # ══════════════════════════════════════════════════════════════════════
    
    def _handle_failure(
        self,
        node: ManifestNode,
        error: str,
        stage: str,
    ) -> None:
        """Handle a node failure with retry logic."""
        # If already RETRYING, this is a re-entrant call from _is_actionable
        # (e.g. a blocker permanently failed while this node was already queued
        # for retry).  The node is already scheduled — don't re-transition.
        if node.state == NodeState.RETRYING:
            return

        # Transition to FAILED
        self.manifest.transition(
            node.node_id,
            NodeState.FAILED,
            error=error,
            error_stage=stage,
        )
        
        # Check if can retry
        if node.can_retry():
            logger.info(f"Scheduling retry for {node.label} (attempt {node.retry_count + 1})")
            self.manifest.transition(node.node_id, NodeState.RETRYING)
        else:
            # Max retries exceeded
            if node.importance == NodeImportance.REQUIRED:
                logger.error(f"Required node {node.label} failed permanently")
            else:
                # Skip optional/decorative nodes
                logger.warning(f"Skipping optional node {node.label}")
                self.manifest.transition(node.node_id, NodeState.SKIPPED)


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------

async def run_progressive_build(
    prompt: str,
    model_manager: Any,
    task_id: str,
    mcp_manager: Optional[Any] = None,
    model_id: Optional[str] = None,
    limits: Optional[HierarchyLimits] = None,
    stage0_output: Optional[Dict[str, Any]] = None,
    use_llm_modifiers: bool = True,
    preserve_scene: bool = False,
) -> ProgressiveResult:
    """Convenience function to run a progressive build.
    
    Args:
        prompt: Natural language description
        model_manager: LLM model manager
        task_id: Unique task ID
        mcp_manager: Optional MCP manager for Blender
        model_id: Optional specific model
        limits: Optional hierarchy limits
        stage0_output: Optional pre-computed Stage 0
        use_llm_modifiers: Enable LLM modifier intent
        preserve_scene: Do not rollback Blender objects on error
        
    Returns:
        ProgressiveResult
    """
    controller = ProgressiveController(
        model_manager=model_manager,
        mcp_manager=mcp_manager,
        limits=limits,
        use_llm_modifiers=use_llm_modifiers,
        preserve_scene=preserve_scene,
    )
    
    return await controller.run(
        prompt=prompt,
        task_id=task_id,
        model_id=model_id,
        stage0_output=stage0_output,
    )
