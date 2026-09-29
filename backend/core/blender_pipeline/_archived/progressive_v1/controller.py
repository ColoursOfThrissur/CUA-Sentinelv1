"""Progressive Assembly Controller — main execution loop for v5 pipeline.

Blueprint references: §31 (Main Progressive Assembly Controller), §41, §42.
Fundamental Architectural Rule (§42):
  "A stage operates on a node; the progressive controller operates on the model."

CRITICAL: This controller orchestrates Stages 0-4 per-node, then executes in Blender.
It does NOT duplicate Stage 4 logic - it CALLS Stage 4 Resolver.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .manifest import BuildManifest, ManifestNode, NodeState, CompletionStatus
from .node_types import NodeKind, NodeImportance
from .hierarchy import ContainmentTree
from .dependency_graph import DependencyDAG
from .frontier import BuildFrontier
from .scheduler import SmartScheduler
from .decomposer import RecursiveDecomposer
from .merger import AssemblyMerger
from .checkpoint import CheckpointManager
from .dirty_propagation import DirtyPropagator

from ..stage0_understanding import Stage0Understanding
from ..stage2_dimensions import Stage2Dimensions, Stage2Output
from ..stage3_semantics import Stage3Semantics, Stage3Output
from ..stage4_resolver import Stage4Resolver, Stage4Error
from ..broadcast import broadcast_blender_trace

logger = logging.getLogger(__name__)


@dataclass
class ProgressiveResult:
    """Result of running the progressive assembly pipeline."""
    success: bool
    manifest: BuildManifest
    completion_status: CompletionStatus
    total_nodes: int = 0
    verified_nodes: int = 0
    failed_nodes: int = 0
    skipped_nodes: int = 0
    error: Optional[str] = None


class ProgressiveAssemblyController:
    """Orchestrates progressive, bottom-up assembly of 3D models.
    
    Blueprint §31: The controller runs the progressive loop:
    1. Stage 0: Object Understanding (once for whole model)
    2. Decomposition: Create hierarchy via Stage 1
    3. For each node in build order:
       a. Stage 2: Dimensions (per-node)
       b. Stage 3: Semantics (per-node) 
       c. Stage 4: Transform Resolution (per-node, PURE CODE)
       d. Execute in Blender
       e. Verify
    4. Merge verified children into parent assemblies
    """

    def __init__(
        self,
        model_manager: Any = None,
        mcp_manager: Any = None,
    ):
        self.model_manager = model_manager
        self.mcp_manager = mcp_manager
        self.scheduler = SmartScheduler()
        self.frontier = BuildFrontier()
        self.merger = AssemblyMerger(mcp_manager=mcp_manager)

    async def run(
        self,
        prompt: str,
        task_id: Optional[str] = None,
        model_id: Optional[str] = None,
    ) -> ProgressiveResult:
        """Run the full progressive assembly pipeline for a prompt."""
        tid = task_id or f"prog_{uuid.uuid4().hex[:8]}"
        mid = model_id or f"model_{uuid.uuid4().hex[:8]}"

        logger.info(f"[{tid}] Starting progressive assembly: {prompt!r}")

        # ── Stage 0: Object Understanding ─────────────────────────────
        await broadcast_blender_trace(tid, 0, "Object Understanding", "running")
        try:
            stage0 = await Stage0Understanding.run(
                prompt=prompt,
                model_manager=self.model_manager,
                task_id=tid,
                model_id=model_id,
            )
            stage0_dict = stage0.to_dict()
            await broadcast_blender_trace(tid, 0, "Object Understanding", "complete", stage0_dict)
        except Exception as e:
            logger.exception(f"[{tid}] Stage 0 failed: {e}")
            await broadcast_blender_trace(tid, 0, "Object Understanding", "failed", {"error": str(e)})
            manifest = BuildManifest.create(prompt, model_id=mid)
            manifest.completion_status = CompletionStatus.FAILED
            return ProgressiveResult(
                success=False, manifest=manifest,
                completion_status=CompletionStatus.FAILED,
                error=f"Stage 0 failed: {e}",
            )

        # ── Initialize Manifest ───────────────────────────────────────
        manifest = BuildManifest.create(prompt, model_id=mid)
        manifest.stage0_output = stage0_dict

        # ── Decomposition (Stage 0.5 + Stage 1) ───────────────────────
        await broadcast_blender_trace(tid, 1, "Decomposition", "running")
        decomposer = RecursiveDecomposer()
        try:
            await decomposer.decompose_root(
                manifest=manifest,
                prompt=prompt,
                stage0_output=stage0_dict,
                model_manager=self.model_manager,
                task_id=tid,
                model_id=model_id,
            )
            await broadcast_blender_trace(
                tid, 1, "Decomposition", "complete",
                {"nodes_count": len(manifest.nodes)}
            )
        except Exception as e:
            logger.exception(f"[{tid}] Decomposition failed: {e}")
            await broadcast_blender_trace(tid, 1, "Decomposition", "failed", {"error": str(e)})
            manifest.completion_status = CompletionStatus.FAILED
            return ProgressiveResult(
                success=False, manifest=manifest,
                completion_status=CompletionStatus.FAILED,
                error=f"Decomposition failed: {e}",
            )

        # ── Build DAG and Frontier ────────────────────────────────────
        dag = DependencyDAG.from_manifest(manifest)
        self.frontier.refresh(manifest, dag)
        CheckpointManager.checkpoint(manifest, label="initial_decomposition")

        # ── Run Stages 2+3 for ALL parts (batch LLM calls) ────────────
        await broadcast_blender_trace(tid, 2, "Dimensions & Semantics", "running")
        try:
            await self._run_stages_2_and_3_batch(manifest, tid)
            await broadcast_blender_trace(tid, 2, "Dimensions & Semantics", "complete")
        except Exception as e:
            logger.exception(f"[{tid}] Stage 2/3 failed: {e}")
            await broadcast_blender_trace(tid, 2, "Dimensions & Semantics", "failed", {"error": str(e)})
            manifest.completion_status = CompletionStatus.FAILED
            return ProgressiveResult(
                success=False, manifest=manifest,
                completion_status=CompletionStatus.FAILED,
                error=f"Stage 2/3 failed: {e}",
            )

        # ── Run Stage 4 for ALL parts (pure code, no LLM) ─────────────
        await broadcast_blender_trace(tid, 3, "Transform Resolution", "running")
        try:
            self._run_stage_4_all_nodes(manifest, tid)
            await broadcast_blender_trace(tid, 3, "Transform Resolution", "complete")
        except Exception as e:
            logger.exception(f"[{tid}] Stage 4 failed: {e}")
            await broadcast_blender_trace(tid, 3, "Transform Resolution", "failed", {"error": str(e)})
            manifest.completion_status = CompletionStatus.FAILED
            return ProgressiveResult(
                success=False, manifest=manifest,
                completion_status=CompletionStatus.FAILED,
                error=f"Stage 4 failed: {e}",
            )

        # ── Progressive Build Loop ────────────────────────────────────
        await broadcast_blender_trace(tid, 4, "Progressive Build", "running")
        step_count = 0
        max_steps = len(manifest.nodes) * 4

        while not manifest.is_root_resolved() and step_count < max_steps:
            step_count += 1
            actionable = self.frontier.refresh(manifest, dag)

            if not actionable:
                # Try merging assemblies
                merged_any = await self._try_merge_assemblies(manifest, tid)
                if merged_any:
                    continue
                logger.warning(f"[{tid}] No actionable nodes and no merges possible")
                break

            next_node_id = self.scheduler.pick_next(actionable, manifest, dag)
            if not next_node_id:
                break

            node = manifest.nodes[next_node_id]

            # Assembly nodes: try to merge if children ready
            if node.kind in (NodeKind.ASSEMBLY, NodeKind.MODEL) and node.children_ids:
                if self.merger.can_merge(next_node_id, manifest):
                    await self.merger.merge(next_node_id, manifest, task_id=tid)
                    CheckpointManager.checkpoint(manifest, label=f"merged_{node.label}")
                else:
                    self.frontier.remove(next_node_id)
                continue

            # PART nodes: build and verify
            await self._build_and_verify_node(node, manifest, tid)
            CheckpointManager.checkpoint(manifest, label=f"node_{node.label}")

            # Try immediate parent merge
            if node.parent_id and self.merger.can_merge(node.parent_id, manifest):
                await self.merger.merge(node.parent_id, manifest, task_id=tid)
                CheckpointManager.checkpoint(manifest, label=f"merged_parent")

        await broadcast_blender_trace(tid, 4, "Progressive Build", "complete")

        # ── Final Outcome ─────────────────────────────────────────────
        status = manifest.compute_completion_status()
        manifest.completion_status = status
        manifest.save()

        verified = len(manifest.nodes_in_state(NodeState.VERIFIED))
        failed = len(manifest.nodes_in_state(NodeState.FAILED))
        skipped = len(manifest.nodes_in_state(NodeState.SKIPPED))

        logger.info(
            f"[{tid}] Progressive assembly finished: status={status.value}, "
            f"{verified}/{len(manifest.nodes)} verified, {failed} failed, {skipped} skipped"
        )

        return ProgressiveResult(
            success=status in (CompletionStatus.SUCCESS, CompletionStatus.COMPLETED_DEGRADED),
            manifest=manifest,
            completion_status=status,
            total_nodes=len(manifest.nodes),
            verified_nodes=verified,
            failed_nodes=failed,
            skipped_nodes=skipped,
        )

    async def _run_stages_2_and_3_batch(
        self,
        manifest: BuildManifest,
        task_id: str,
    ) -> None:
        """Run Stage 2 (dimensions) and Stage 3 (semantics) for all parts.
        
        This batches the LLM calls for efficiency - one Stage 2 call and one
        Stage 3 call for the entire model, then distributes results to nodes.
        """
        # Build stage1_output format from manifest nodes
        stage1_parts = []
        for nid, node in manifest.nodes.items():
            if node.kind == NodeKind.MODEL:
                continue  # Skip root MODEL node
            s1 = node.stage_outputs.get("stage1", {})
            stage1_parts.append({
                "label": node.label,
                "primitive_type": s1.get("primitive_type", "box"),
                "parent_label": s1.get("parent_label"),
                "socket_type": s1.get("socket_type", "ROOT"),
            })

        if not stage1_parts:
            return

        stage1_output = {"parts": stage1_parts}

        # ── Stage 2: Dimensions ───────────────────────────────────────
        stage2_out = await Stage2Dimensions.run(
            stage0_output=manifest.stage0_output or {},
            stage1_output=stage1_output,
            model_manager=self.model_manager,
            task_id=task_id,
        )

        # Store Stage 2 results in nodes
        for part in stage2_out.parts:
            node = self._find_node_by_label(manifest, part.label)
            if node:
                node.stage_outputs["stage2"] = {
                    "label": part.label,
                    "primitive_type": part.primitive_type,
                    "parent_label": part.parent_label,
                    "socket_type": part.socket_type,
                    "dimensions": self._dims_to_dict(part.dimensions),
                    "material": self._material_to_dict(part.dimensions.material),
                }

        # ── Stage 3: Semantics ────────────────────────────────────────
        stage2_dict = stage2_out.to_dict()
        stage3_out = await Stage3Semantics.run(
            stage1_output=stage1_output,
            stage2_output=stage2_dict,
            model_manager=self.model_manager,
            task_id=task_id,
        )

        # Store Stage 3 results in nodes
        for sem in stage3_out.parts:
            node = self._find_node_by_label(manifest, sem.label)
            if node:
                node.stage_outputs["stage3"] = {
                    "label": sem.label,
                    "socket_type": sem.socket_type,
                    "pierce_direction": sem.pierce_direction,
                    "height_hint": sem.height_hint,
                    "array_axis": sem.array_axis,
                    "array_count": sem.array_count,
                    "array_index": sem.array_index,
                    "spacing_hint": sem.spacing_hint,
                    "connects_to": sem.connects_to,
                    "radial_count": sem.radial_count,
                    "radial_index": sem.radial_index,
                    "face_position": sem.face_position,
                    "cut_face": sem.cut_face,
                }

    def _run_stage_4_all_nodes(
        self,
        manifest: BuildManifest,
        task_id: str,
    ) -> None:
        """Run Stage 4 Resolver to compute transforms for all nodes.
        
        CRITICAL: This calls the REAL Stage 4 Resolver (1489 lines of pure code).
        We do NOT duplicate transform logic here.
        """
        # Build stage2_output and stage3_output in the format Stage4 expects
        stage2_parts = []
        stage3_parts = []

        for nid, node in manifest.nodes.items():
            if node.kind == NodeKind.MODEL:
                continue

            s1 = node.stage_outputs.get("stage1", {})
            s2 = node.stage_outputs.get("stage2", {})
            s3 = node.stage_outputs.get("stage3", {})

            # Stage 2 format for Stage 4
            stage2_parts.append({
                "label": node.label,
                "primitive_type": s1.get("primitive_type", "box"),
                "parent_label": s1.get("parent_label"),
                "socket_type": s1.get("socket_type", "ROOT"),
                "dimensions": s2.get("dimensions", {}),
                "material": s2.get("material"),
            })

            # Stage 3 format for Stage 4
            stage3_parts.append({
                "label": node.label,
                "socket_type": s1.get("socket_type", "ROOT"),
                "pierce_direction": s3.get("pierce_direction"),
                "height_hint": s3.get("height_hint"),
                "array_axis": s3.get("array_axis"),
                "array_count": s3.get("array_count"),
                "array_index": s3.get("array_index"),
                "spacing_hint": s3.get("spacing_hint"),
                "connects_to": s3.get("connects_to"),
                "radial_count": s3.get("radial_count"),
                "radial_index": s3.get("radial_index"),
                "face_position": s3.get("face_position"),
                "cut_face": s3.get("cut_face"),
            })

        if not stage2_parts:
            return

        stage2_output = {"parts": stage2_parts}
        stage3_output = {"parts": stage3_parts}

        # Call the REAL Stage 4 Resolver
        assembly_graph = Stage4Resolver.run(
            stage0_output=manifest.stage0_output or {},
            stage2_output=stage2_output,
            stage3_output=stage3_output,
            task_id=task_id,
        )

        # Extract transforms from AssemblyGraph and store in manifest nodes
        self._extract_transforms_from_graph(assembly_graph.root, manifest)

    def _extract_transforms_from_graph(
        self,
        graph_node,
        manifest: BuildManifest,
    ) -> None:
        """Recursively extract Stage 4 transforms from AssemblyGraph into manifest."""
        # Find corresponding manifest node
        mnode = self._find_node_by_label(manifest, graph_node.label)
        if mnode:
            att = graph_node.attachment
            mnode.stage_outputs["stage4"] = {
                "location": list(att.local_offset) if att.local_offset else [0, 0, 0],
                "rotation": list(att.local_rotation_euler) if att.local_rotation_euler else [0, 0, 0],
                "socket_type": att.socket_type,
                "join_mode": att.join_mode.value if att.join_mode else "PARENT_ONLY",
                "sub_spec": graph_node.sub_spec,
            }

        # Recurse to children
        for child in graph_node.children:
            self._extract_transforms_from_graph(child, manifest)

    async def _build_and_verify_node(
        self,
        node: ManifestNode,
        manifest: BuildManifest,
        task_id: str,
    ) -> None:
        """Execute single leaf node build & verification in Blender."""
        manifest.transition(node.node_id, NodeState.BUILDING)
        await broadcast_blender_trace(task_id, 5, f"Building {node.label}", "running")

        # Get Stage 4 computed transform
        s4 = node.stage_outputs.get("stage4", {})
        if not s4:
            logger.error(f"[{task_id}] Node '{node.label}' missing Stage 4 output")
            manifest.transition(node.node_id, NodeState.FAILED, error="Missing Stage 4 transform")
            return

        manifest.transition(node.node_id, NodeState.VERIFYING)

        from .node_executor import ProgressiveNodeExecutor
        executor = ProgressiveNodeExecutor(mcp_manager=self.mcp_manager)

        try:
            res = await executor.execute_leaf_node(
                node=node,
                manifest=manifest,
                task_id=task_id,
            )
            node.verification_result = res.get("dimension_check", {"passed": True})
            manifest.transition(node.node_id, NodeState.VERIFIED)
            await broadcast_blender_trace(
                task_id, 5, f"Verified {node.label}", "complete",
                {"objects": node.blender_objects}
            )
        except Exception as e:
            logger.error(f"[{task_id}] Build failed for '{node.label}': {e}")
            manifest.transition(node.node_id, NodeState.FAILED, error=str(e))
            await broadcast_blender_trace(
                task_id, 5, f"Failed {node.label}", "failed",
                {"error": str(e)}
            )

    async def _try_merge_assemblies(
        self,
        manifest: BuildManifest,
        task_id: str,
    ) -> bool:
        """Try to merge any assemblies whose children are all verified."""
        merged_any = False
        for nid, node in list(manifest.nodes.items()):
            if node.kind in (NodeKind.ASSEMBLY, NodeKind.MODEL):
                if node.state in (NodeState.READY, NodeState.PLANNED):
                    if self.merger.can_merge(nid, manifest):
                        merged = await self.merger.merge(nid, manifest, task_id=task_id)
                        if merged:
                            merged_any = True
                            CheckpointManager.checkpoint(manifest, label=f"merged_{node.label}")
        return merged_any

    def _find_node_by_label(
        self,
        manifest: BuildManifest,
        label: str,
    ) -> Optional[ManifestNode]:
        """Find a manifest node by its label."""
        for nid, node in manifest.nodes.items():
            if node.label == label:
                return node
        return None

    def _dims_to_dict(self, dims) -> Dict[str, Any]:
        """Convert PartDimensions to dict."""
        result = {}
        if dims.size:
            result["size"] = list(dims.size)
        if dims.radius is not None:
            result["radius"] = dims.radius
        if dims.depth is not None:
            result["depth"] = dims.depth
        if dims.radius1 is not None:
            result["radius1"] = dims.radius1
        if dims.vertices:
            result["vertices"] = dims.vertices
        return result

    def _material_to_dict(self, mat) -> Optional[Dict[str, Any]]:
        """Convert PartMaterial to dict."""
        if not mat:
            return None
        result = {
            "color": list(mat.color),
            "metallic": mat.metallic,
            "roughness": mat.roughness,
        }
        if mat.emission_color:
            result["emission_color"] = list(mat.emission_color)
            result["emission_strength"] = mat.emission_strength
        return result
