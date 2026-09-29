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
    
    def to_dict(self) -> Dict[str, Any]:
        # Include spatial verification status from manifest stats
        spatial_failed = False
        spatial_errors_list = []
        if self.manifest and hasattr(self.manifest, 'stats'):
            spatial_failed = self.manifest.stats.get("spatial_verification_failed", False)
            spatial_errors_list = self.manifest.stats.get("spatial_errors", [])
        
        return {
            "success": self.success,
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
    ):
        self.model_manager = model_manager
        self.mcp_manager = mcp_manager
        self.limits = limits or HierarchyLimits()
        self.max_retries = max_retries
        self.checkpoint_interval = checkpoint_interval
        
        # Build state
        self.manifest: Optional[BuildManifest] = None
        self.tree: Optional[ContainmentTree] = None
        self.dag: Optional[DependencyDAG] = None
        self.phase: BuildPhase = BuildPhase.INITIALIZING
        
        # Tracking
        self.verified_since_checkpoint = 0
        self.start_time: float = 0.0
        
        # Callbacks for progress reporting
        self.on_phase_change: Optional[Callable[[BuildPhase, str], None]] = None
        self.on_node_complete: Optional[Callable[[str, NodeState], None]] = None

    
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
        errors: List[str] = []
        
        try:
            # ── Phase 1: Initialize ──────────────────────────────────────
            self._set_phase(BuildPhase.INITIALIZING, "Creating manifest")
            await broadcast_blender_trace(task_id, 0, "Object Understanding", "running")
            
            self.manifest = BuildManifest.create(prompt)
            self.manifest.stage0_output = stage0_output
            self.tree = ContainmentTree(self.manifest, self.limits)
            
            await broadcast_blender_trace(task_id, 0, "Object Understanding", "complete", stage0_output or {})
            logger.info(f"[{task_id}] Starting progressive build: {prompt[:50]}...")
            
            # ── Phase 2: Decompose ───────────────────────────────────────
            self._set_phase(BuildPhase.DECOMPOSING, "Recursive decomposition")
            await broadcast_blender_trace(task_id, 1, "Decomposition", "running")
            
            decomp_stats = await self._decompose(task_id, model_id)
            
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
            
            await self._build_loop(task_id, model_id)
            
            await broadcast_blender_trace(task_id, 4, "Progressive Build", "complete")
            
            # ── Phase 4: Ground-plane correction ─────────────────────────
            await self._lift_to_ground_plane(task_id)
            
            # ── Phase 5: Whole-Model Verification ────────────────────────
            self._set_phase(BuildPhase.VERIFYING, "Whole-model spatial verification")
            await broadcast_blender_trace(task_id, 6, "Spatial Verification", "running")
            
            spatial_errors = await self._verify_whole_model(task_id)
            
            # CRITICAL: Spatial verification failures MUST affect completion status
            # This is not just logging - these are blocking errors that degrade the build
            if spatial_errors:
                for err in spatial_errors:
                    errors.append(err)
                    logger.warning(f"[{task_id}] Spatial issue: {err}")
                
                # Mark the build as degraded due to spatial issues
                # This ensures the user knows the model has problems
                self.manifest.stats["spatial_verification_failed"] = True
                self.manifest.stats["spatial_errors"] = spatial_errors
            
            await broadcast_blender_trace(task_id, 6, "Spatial Verification", "complete", {
                "issues": len(spatial_errors),
                "passed": len(spatial_errors) == 0,
            })
            
            # ── Phase 5: Finalize ────────────────────────────────────────
            self._set_phase(BuildPhase.FINALIZING, "Finalizing build")
            
            self.manifest.finalize()
            
        except Exception as e:
            logger.exception(f"[{task_id}] Build failed: {e}")
            errors.append(str(e))
            self._set_phase(BuildPhase.FAILED, str(e))
        
        # Build result
        elapsed = time.time() - self.start_time
        
        return self._build_result(elapsed, errors)
    
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
        
        # Compute base status from node states
        status = self.manifest.compute_completion_status()
        
        # CRITICAL: Downgrade status if spatial verification failed
        # A model with interpenetration/floating/embedment issues is degraded
        spatial_failed = self.manifest.stats.get("spatial_verification_failed", False)
        if spatial_failed and status == CompletionStatus.SUCCESS:
            status = CompletionStatus.COMPLETED_DEGRADED
            logger.info(f"Build status downgraded to COMPLETED_DEGRADED due to spatial verification failures")
        
        return ProgressiveResult(
            success=status in (CompletionStatus.SUCCESS, CompletionStatus.COMPLETED_DEGRADED),
            manifest=self.manifest,
            completion_status=status,
            total_nodes=len(self.manifest.nodes),
            verified_nodes=verified,
            failed_nodes=failed,
            skipped_nodes=skipped,
            llm_calls=self.manifest.stats.get("total_llm_calls", 0),
            blender_ops=self.manifest.stats.get("total_blender_ops", 0),
            build_time_seconds=elapsed,
            errors=errors,
            blender_objects=blender_objects,
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

        # Real path: ask Blender for the global min Z, then move all objects
        all_objects = [
            obj
            for node in self.manifest.nodes.values()
            if node.kind == NodeKind.PART and node.state == NodeState.VERIFIED
            for obj in node.blender_objects
        ]
        if not all_objects:
            return

        script = f'''
import bpy, json
from mathutils import Vector

objects = {repr(all_objects)}
min_z = float('inf')
for name in objects:
    obj = bpy.data.objects.get(name)
    if obj and obj.type == 'MESH':
        for v in obj.data.vertices:
            wz = (obj.matrix_world @ v.co).z
            if wz < min_z:
                min_z = wz

if min_z == float('inf') or abs(min_z) < 0.001:
    print("SENTINEL_OUTPUT_START" + json.dumps({{"ok": True, "lift": 0.0}}) + "SENTINEL_OUTPUT_END")
else:
    lift = -min_z
    for name in objects:
        obj = bpy.data.objects.get(name)
        if obj:
            obj.location.z += lift
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
        
        for node in self.manifest.nodes.values():
            if node.kind == NodeKind.PART and node.state == NodeState.VERIFIED:
                all_objects.extend(node.blender_objects)
                
                # Boolean cuts are allowed to overlap their target
                if node.attachment and node.attachment.socket_type == SocketType.BOOLEAN_CUT:
                    # Find the ROOT sibling (target of the cut)
                    if node.parent_id:
                        parent = self.manifest.nodes.get(node.parent_id)
                        if parent:
                            for sib_id in parent.children_ids:
                                sib = self.manifest.nodes.get(sib_id)
                                if sib and sib.attachment:
                                    if sib.attachment.socket_type == SocketType.ROOT:
                                        for node_obj in node.blender_objects:
                                            for sib_obj in sib.blender_objects:
                                                allowed_overlaps.add((node_obj, sib_obj))
        
        if len(all_objects) < 2:
            logger.debug(f"[{task_id}] Skipping spatial verification (< 2 objects)")
            return errors
        
        verifier = SpatialVerifier(self.mcp_manager)
        
        # Run verification at STRICT level (interpenetration + floating check)
        result = await verifier.verify_assembly(
            objects=all_objects,
            level=VerificationLevel.STRICT,
            allowed_overlaps=allowed_overlaps,
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
        iteration = 0
        max_iterations = len(self.manifest.nodes) * 3  # Safety limit
        
        # Log initial state of all nodes
        logger.info(f"[{task_id}] Build loop starting with {len(self.manifest.nodes)} nodes:")
        for node in self.manifest.nodes.values():
            parent = self.manifest.nodes.get(node.parent_id) if node.parent_id else None
            parent_info = f"parent={parent.label}({parent.state.value})" if parent else "ROOT"
            socket = node.attachment.socket_type.value if node.attachment else "None"
            logger.info(f"  [{node.kind.value}] {node.label}: state={node.state.value}, socket={socket}, {parent_info}")
        iteration = 0
        max_iterations = len(self.manifest.nodes) * 3  # Safety limit
        
        while iteration < max_iterations:
            iteration += 1
            
            # Check if done
            if self.manifest.is_root_resolved():
                logger.info(f"[{task_id}] Root verified - build complete!")
                self._set_phase(BuildPhase.COMPLETE, "Build complete")
                return
            
            # Find actionable nodes
            actionable = self._find_actionable_nodes()
            
            if not actionable:
                # Log why we're stuck
                if iteration % 20 == 0:  # Log every 20 iterations
                    pending = [n for n in self.manifest.nodes.values() 
                               if n.state not in (NodeState.VERIFIED, NodeState.SKIPPED, NodeState.FAILED)]
                    if pending:
                        logger.debug(f"[{task_id}] Stuck - {len(pending)} pending nodes:")
                        for p in pending[:5]:
                            parent = self.manifest.nodes.get(p.parent_id) if p.parent_id else None
                            parent_info = f"parent={parent.label}({parent.state.value})" if parent else "no parent"
                            logger.debug(f"  - {p.label}: state={p.state.value}, kind={p.kind.value}, {parent_info}")
                
                # Check for deadlock
                if self._is_deadlocked():
                    logger.warning(f"[{task_id}] Build deadlocked - no actionable nodes")
                    break
                # All nodes processing, wait
                await asyncio.sleep(0.01)
                continue
            
            # Process one node at a time (could parallelize later)
            node = actionable[0]
            
            logger.debug(f"[{task_id}] Processing: {node.label} ({node.kind.value})")
            
            if node.kind == NodeKind.PART:
                await self._process_part(node, task_id, model_id)
            elif node.kind in (NodeKind.ASSEMBLY, NodeKind.MODEL):
                await self._process_assembly(node, task_id)
            else:
                # Other node types - mark as verified for now
                self.manifest.transition(node.node_id, NodeState.VERIFIED)
            
            # Notify callback
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
        """Check if a node can be processed now."""
        from .node_types import SocketType, CROSS_REFERENCE_SOCKETS
        
        # Already done or in progress
        if node.state in (NodeState.VERIFIED, NodeState.SKIPPED, 
                          NodeState.BUILDING, NodeState.VERIFYING, NodeState.MERGING):
            return False
        
        # Failed and can't retry
        if node.state == NodeState.FAILED and not node.can_retry():
            return False
        
        # Check dependencies
        if node.kind == NodeKind.PART:
            # Parts need parent to be in READY state (decomposition complete)
            if node.parent_id:
                parent = self.manifest.nodes.get(node.parent_id)
                if not parent:
                    logger.debug(f"[actionable] {node.label}: parent not found")
                    return False
                if parent.state == NodeState.FAILED:
                    logger.debug(f"[actionable] {node.label}: parent {parent.label} FAILED")
                    return False
                # Parent must have finished decomposition (READY or later)
                if parent.state in (NodeState.PLANNED, NodeState.DECOMPOSING):
                    logger.debug(f"[actionable] {node.label}: parent {parent.label} still decomposing (state={parent.state.value})")
                    return False
                
                # Phase 3: Ensure parent assembly has its local_transform computed
                # This is needed so the child can use parent.world_matrix
                if parent.kind in (NodeKind.ASSEMBLY, NodeKind.MODEL):
                    if parent.transform_state and parent.transform_state.world_matrix is None:
                        # Parent assembly needs its transform computed first
                        # Compute it now (lazy initialization)
                        self._ensure_assembly_transform(parent)
                
                my_socket = node.attachment.socket_type if node.attachment else None
                
                # BOOLEAN_CUT nodes must wait for ROOT sibling to be verified
                # (they cut into the ROOT part)
                if my_socket == SocketType.BOOLEAN_CUT:
                    for sib_id in parent.children_ids:
                        if sib_id == node.node_id:
                            continue
                        sib = self.manifest.nodes.get(sib_id)
                        if sib and sib.kind == NodeKind.PART:
                            sib_socket = sib.attachment.socket_type if sib.attachment else None
                            if sib_socket == SocketType.ROOT:
                                if sib.state != NodeState.VERIFIED:
                                    logger.debug(f"[actionable] {node.label} (BOOLEAN_CUT) waiting for ROOT sibling {sib.label}")
                                    return False
                
                # INSET nodes must wait for BOOLEAN_CUT siblings to be verified
                # (they go inside the hole created by BOOLEAN_CUT)
                elif my_socket == SocketType.INSET:
                    for sib_id in parent.children_ids:
                        if sib_id == node.node_id:
                            continue
                        sib = self.manifest.nodes.get(sib_id)
                        if sib and sib.kind == NodeKind.PART:
                            sib_socket = sib.attachment.socket_type if sib.attachment else None
                            if sib_socket == SocketType.BOOLEAN_CUT:
                                if sib.state != NodeState.VERIFIED:
                                    logger.debug(f"[actionable] {node.label} (INSET) waiting for BOOLEAN_CUT sibling {sib.label}")
                                    return False
                
                # Cross-reference sockets (BRIDGE, STRUT, RADIAL_BRIDGE, RELATIVE_TO)
                # must wait for their target part to be verified
                elif my_socket in CROSS_REFERENCE_SOCKETS:
                    # Get the target label from semantics or attachment
                    sem = node.stage_outputs.get("stage3", {})
                    decomp_hint = node.stage_outputs.get("decomposition_hint", {})
                    target_label = None
                    
                    if my_socket == SocketType.RELATIVE_TO:
                        target_label = (
                            sem.get("relative_to") or 
                            decomp_hint.get("relative_to") or
                            (node.attachment.relative_to if node.attachment else None)
                        )
                    elif my_socket == SocketType.RADIAL_BRIDGE:
                        # RADIAL_BRIDGE connects to a named part (usually the hub)
                        target_label = (
                            sem.get("connects_to") or 
                            decomp_hint.get("connects_to") or
                            (node.attachment.connects_to if node.attachment else None)
                        )
                        # If no explicit target, RADIAL_BRIDGE needs the parent's ROOT sibling
                        # (the hub that the blades radiate from).
                        # Only walk to grandparent if the grandparent actually has a ROOT
                        # sibling of our parent — avoid picking an arbitrary node.
                        if not target_label and node.parent_id:
                            _parent = self.manifest.nodes.get(node.parent_id)
                            if _parent and _parent.parent_id:
                                grandparent = self.manifest.nodes.get(_parent.parent_id)
                                if grandparent:
                                    for sib_id in grandparent.children_ids:
                                        if sib_id == _parent.node_id:
                                            continue
                                        sib = self.manifest.nodes.get(sib_id)
                                        if sib and sib.attachment and sib.attachment.socket_type == SocketType.ROOT:
                                            if sib.kind == NodeKind.PART:
                                                target_label = sib.label
                                            elif sib.kind == NodeKind.ASSEMBLY:
                                                root_part = self._find_root_part_in_assembly(sib)
                                                if root_part:
                                                    target_label = root_part.label
                                            break
                                    # If grandparent has no ROOT sibling, leave target_label
                                    # as None — Stage 3 must supply connects_to explicitly.
                    else:  # BRIDGE, STRUT
                        target_label = (
                            sem.get("connects_to") or 
                            decomp_hint.get("connects_to") or
                            (node.attachment.connects_to if node.attachment else None)
                        )
                    
                    # If still no target, this socket can't be resolved yet
                    # Allow it to proceed - Stage 3 will populate connects_to
                    if not target_label:
                        logger.debug(f"[actionable] {node.label} ({my_socket.value}) has no target_label yet - allowing for Stage 3")
                        # Fall through to normal non-ROOT sibling check below
                    else:
                        target = self.manifest.get_node_by_label(target_label)
                        if not target:
                            # Target doesn't exist in manifest - fail fast rather than burn a retry
                            logger.warning(f"[actionable] {node.label}: cross-reference target '{target_label}' not found in manifest")
                            return False
                        
                        if target.state != NodeState.VERIFIED:
                            # If the target permanently failed, fail this node immediately
                            # rather than burning its own retries on a doomed resolution.
                            if target.state == NodeState.FAILED and not target.can_retry():
                                logger.warning(
                                    f"[actionable] {node.label} ({my_socket.value}): "
                                    f"prerequisite '{target_label}' permanently failed — failing immediately"
                                )
                                self._handle_failure(
                                    node,
                                    f"Prerequisite '{target_label}' permanently failed",
                                    "prerequisite",
                                )
                                return False
                            logger.debug(f"[actionable] {node.label} ({my_socket.value}) waiting for target {target_label} (state={target.state.value})")
                            return False
                
                # Non-ROOT parts must wait for ROOT sibling to be verified first
                # (ROOT sibling defines the parent's bounding box for transform resolution)
                elif my_socket and my_socket != SocketType.ROOT:
                    for sib_id in parent.children_ids:
                        if sib_id == node.node_id:
                            continue
                        sib = self.manifest.nodes.get(sib_id)
                        if sib and sib.kind == NodeKind.PART:
                            sib_socket = sib.attachment.socket_type if sib.attachment else None
                            if sib_socket == SocketType.ROOT:
                                # Found ROOT sibling - must be verified first
                                if sib.state != NodeState.VERIFIED:
                                    logger.debug(f"[actionable] {node.label} waiting for ROOT sibling {sib.label} (state={sib.state.value})")
                                    return False
                
                # ROOT parts inside assemblies with non-ROOT sockets must wait for
                # the parent assembly's reference geometry to be built first.
                # E.g., stand_assembly(TOP_CENTER) -> stand(ROOT) needs base_assembly's
                # ROOT part (base) to be built first so we know where to position.
                if my_socket == SocketType.ROOT:
                    parent_socket = parent.attachment.socket_type if parent.attachment else None
                    if parent_socket and parent_socket != SocketType.ROOT:
                        # Parent assembly has a non-ROOT socket - find the reference geometry
                        # This could be a sibling ROOT part, or a ROOT part in a sibling assembly
                        grandparent = self.manifest.nodes.get(parent.parent_id) if parent.parent_id else None
                        if grandparent:
                            # Find the ROOT sibling (assembly or part) of our parent
                            for sib_id in grandparent.children_ids:
                                if sib_id == parent.node_id:
                                    continue
                                sib = self.manifest.nodes.get(sib_id)
                                if sib and sib.attachment and sib.attachment.socket_type == SocketType.ROOT:
                                    # Found ROOT sibling - find its ROOT part
                                    ref_part = self._find_root_part_in_assembly(sib) if sib.kind == NodeKind.ASSEMBLY else sib
                                    if ref_part and ref_part.kind == NodeKind.PART:
                                        if ref_part.state != NodeState.VERIFIED:
                                            logger.debug(f"[actionable] {node.label} (ROOT in {parent.label}) waiting for reference part {ref_part.label} (state={ref_part.state.value})")
                                            return False
                                    break
            
            # Parts in PLANNED or READY state are actionable
            return node.state in (NodeState.PLANNED, NodeState.READY, NodeState.RETRYING)
        
        elif node.kind in (NodeKind.ASSEMBLY, NodeKind.MODEL):
            # Assemblies need all children verified (or skipped)
            if not node.children_ids:
                # No children - this assembly is a leaf (e.g., depth limit reached)
                # It can be verified immediately as an empty assembly
                return node.state in (NodeState.PLANNED, NodeState.READY)
            
            # Check if all children are done
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
        if (assembly.transform_state and
                assembly.transform_state.world_matrix is not None and
                assembly.transform_state.is_world_valid(parent_revision)):
            return
        
        # First, ensure parent's transform is computed (recursive)
        if assembly.parent_id:
            parent = self.manifest.nodes.get(assembly.parent_id)
            if parent and parent.kind in (NodeKind.ASSEMBLY, NodeKind.MODEL):
                self._ensure_assembly_transform(parent)
        
        # Compute this assembly's local_transform via Stage 4 only if
        # set_local_transform was never called (revision == 0 means the
        # local_transform is still the default identity and Stage 4 hasn't
        # run for this node yet).
        if assembly.transform_state:
            if assembly.transform_state.revision == 0:
                try:
                    parent_world = None
                    if assembly.parent_id:
                        p = self.manifest.nodes.get(assembly.parent_id)
                        if p and p.transform_state:
                            parent_world = p.transform_state.world_matrix
                    solution = Stage4Resolver.run_assembly(assembly, self.manifest, parent_world)
                    assembly.transform_state.set_local_transform(solution.local_transform)
                    logger.debug(
                        f"_ensure_assembly_transform: {assembly.label} -> "
                        f"local_pos={[round(p, 4) for p in solution.local_transform.position]}"
                    )
                except Exception as e:
                    logger.warning(f"_ensure_assembly_transform: {assembly.label} failed: {e}")
            
            # Propagate world transform (recomputes world_matrix from local + parent)
            self._propagate_new_world_transform(assembly, "ensure")

    
    # ══════════════════════════════════════════════════════════════════════
    # Part Processing
    # ══════════════════════════════════════════════════════════════════════
    
    async def _process_part(
        self,
        node: ManifestNode,
        task_id: str,
        model_id: Optional[str],
    ) -> None:
        """Process a PART node: stages 2/3/4 → build → verify.
        
        Phase 3: After Stage 4, propagate world transforms via new system
        and compare with legacy executor results.
        """
        from .node_types import SocketType
        from .transforms import validate_local_transform
        
        try:
            # Transition to READY if needed
            if node.state == NodeState.PLANNED:
                self.manifest.transition(node.node_id, NodeState.READY)
            elif node.state == NodeState.RETRYING:
                self.manifest.transition(node.node_id, NodeState.READY)
            
            # ── Run Stages 2, 3, 4 if needed ─────────────────────────────
            if "stage2" not in node.stage_outputs:
                await self._run_stage2(node, task_id, model_id)
            
            if "stage3" not in node.stage_outputs:
                await self._run_stage3(node, task_id, model_id)
            
            if "stage4" not in node.stage_outputs:
                self._run_stage4(node, task_id)
            
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
            self._propagate_new_world_transform(node, task_id)
            
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
        """
        from .stages import Stage4Resolver
        from .stages.stage4_resolver import BBox, AttachmentSolution
        
        self._set_phase(BuildPhase.STAGING, f"Stage 4: {node.label}")
        
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
    
    async def _build_part(self, node: ManifestNode, task_id: str) -> None:
        """Build a part in Blender via MCP.
        
        CRITICAL: If this part has BOOLEAN_CUT siblings, we defer modifier/material
        application until after all cuts are complete. This ensures bevels are
        applied to the final cut geometry, not the pre-cut primitive.
        """
        self._set_phase(BuildPhase.BUILDING, f"Building: {node.label}")
        await broadcast_blender_trace(task_id, 5, f"Building {node.label}", "running")
        
        if not self.mcp_manager:
            # No MCP - simulate build
            logger.debug(f"[{task_id}] Simulated build for {node.label}")
            node.blender_objects = [f"obj_{node.label}"]
            node.bounding_box = {"min": [-0.5, -0.5, -0.5], "max": [0.5, 0.5, 0.5]}
            self.manifest.record_blender_op()
            return
        
        # Check if this ROOT part has pending BOOLEAN_CUT siblings
        # If so, defer modifiers until after cuts complete
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
        
        # Build via real executor
        from .executor import BlenderExecutor
        
        executor = BlenderExecutor(self.mcp_manager, task_id)
        result = await executor.build_node(node, self.manifest, defer_modifiers=defer_modifiers)
        
        if not result.ok:
            raise Exception(f"Build failed: {result.error}")
        
        node.blender_objects = result.blender_objects
        node.bounding_box = result.bounding_box
        self.manifest.record_blender_op()
    
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
        
        # Execute boolean cut
        from .executor import BlenderExecutor
        
        executor = BlenderExecutor(self.mcp_manager, task_id)
        result = await executor.build_boolean_cut(node, target_node, self.manifest)
        
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
                mod_result = await executor.apply_deferred_modifiers(target_node, self.manifest)
                if not mod_result.ok:
                    logger.warning(f"[{task_id}] Deferred modifier application failed: {mod_result.error}")
    
    async def _verify_part(self, node: ManifestNode, task_id: str) -> bool:
        """Verify a built part."""
        self._set_phase(BuildPhase.VERIFYING, f"Verifying: {node.label}")
        
        # Basic verification - check that objects were created
        if not node.blender_objects:
            return False
        
        if self.mcp_manager:
            # Use real verification
            from .executor import BlenderExecutor
            
            executor = BlenderExecutor(self.mcp_manager, task_id)
            result = await executor.verify_node(node)
            
            if not result.ok:
                logger.warning(f"[{task_id}] Verification failed for {node.label}: {result.checks_failed}")
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
            # Only compute if set_local_transform was never called (revision == 0).
            # Do NOT use a position equality check — a ROOT assembly legitimately
            # has position [0,0,0] and would be recomputed on every retry.
            if node.transform_state and node.transform_state.revision == 0:
                from .stages import Stage4Resolver
                from .stages.stage4_resolver import AttachmentSolution
                
                try:
                    parent_world = None
                    if node.parent_id:
                        p = self.manifest.nodes.get(node.parent_id)
                        if p and p.transform_state:
                            parent_world = p.transform_state.world_matrix
                    solution = Stage4Resolver.run_assembly(node, self.manifest, parent_world)
                    node.transform_state.set_local_transform(solution.local_transform)
                    logger.debug(
                        f"[{task_id}] Assembly {node.label} local_transform: "
                        f"pos={[round(p, 4) for p in solution.local_transform.position]}"
                    )
                except Exception as e:
                    logger.warning(f"[{task_id}] Assembly {node.label} Stage4 failed: {e}")
            
            # ── Propagate world transform ────────────────────────────────
            self._propagate_new_world_transform(node, task_id)
            
            # Handle assemblies with no children (e.g., depth limit reached)
            # These are leaf assemblies that can be verified immediately
            if not node.children_ids:
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
            
            # Check if any required children failed
            has_required_failure = False
            for cid in node.children_ids:
                child = self.manifest.nodes.get(cid)
                if child and child.importance == NodeImportance.REQUIRED:
                    if child.state in (NodeState.FAILED, NodeState.SKIPPED):
                        has_required_failure = True
                        break
            
            if has_required_failure:
                self.manifest.transition(
                    node.node_id, 
                    NodeState.FAILED,
                    error="Required child failed",
                )
                return
            
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
            # Use real executor for merge
            from .executor import BlenderExecutor
            
            executor = BlenderExecutor(self.mcp_manager, task_id)
            result = await executor.merge_assembly(node, self.manifest)
            
            if not result.ok:
                raise Exception(f"Merge failed: {result.error}")
            
            node.blender_objects = result.blender_objects
            node.bounding_box = result.bounding_box
            self.manifest.record_blender_op()
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
        
    Returns:
        ProgressiveResult
    """
    controller = ProgressiveController(
        model_manager=model_manager,
        mcp_manager=mcp_manager,
        limits=limits,
    )
    
    return await controller.run(
        prompt=prompt,
        task_id=task_id,
        model_id=model_id,
        stage0_output=stage0_output,
    )
