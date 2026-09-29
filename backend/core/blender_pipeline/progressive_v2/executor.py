"""Progressive Pipeline Executor — bridges progressive controller to Blender MCP.

Converts ManifestNode geometry specs into Blender operations and executes them.

CRITICAL INVARIANTS:
1. Each node builds into its own generation-scoped collection
2. Verification failure = node failure (triggers retry logic)
3. Partial builds are rolled back on failure
4. User scene is never destroyed - we use isolated collections

Blueprint references: §11 (per-node execution), §12 (merge), §21 (verification).
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from .manifest import BuildManifest, ManifestNode

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BUILD_COLLECTION_PREFIX = "Sentinel_Build"
DEFAULT_DIMENSION_TOLERANCE_M = 0.01  # 1cm
DEFAULT_GAP_TOLERANCE_M = 0.002  # 2mm

# Phase 4 feature flag: use hierarchical transform system
# Set to True to use node.transform_state.world_matrix instead of legacy computation
USE_HIERARCHICAL_TRANSFORMS = True

# ---------------------------------------------------------------------------
# Transform Ownership Contract
# ---------------------------------------------------------------------------
# transform_state.world_matrix has ONE authoritative write path:
#
#   Stage 4 -> local_transform -> controller._propagate_new_world_transform()
#           -> NodeTransformState.compute_world() -> world_matrix
#
# The executor is a READ-ONLY consumer of world_matrix.
# It may write legacy node.world_position / node.world_rotation for
# backward-compatibility, but MUST NEVER write transform_state.world_matrix.
#
# Allowed writers:                              Status
#   NodeTransformState.compute_world()          OK
#   controller._propagate_new_world_transform() OK  (calls compute_world)
#   controller._ensure_assembly_transform()     OK  (calls compute_world)
#   manifest.propagate_transforms_from()        OK  (calls compute_world)
#   NodeTransformState.set_local_transform()    OK  (invalidates, not writes)
#
# Forbidden writers:
#   BlenderExecutor.build_node()                FORBIDDEN
#   BlenderExecutor.build_boolean_cut()         FORBIDDEN
#   _lift_to_ground_plane() direct reconstruct  FORBIDDEN
#   Stage 4 / semantic resolvers                FORBIDDEN


# ---------------------------------------------------------------------------
# Execution Result
# ---------------------------------------------------------------------------

@dataclass
class ExecutionResult:
    """Result of executing a single node in Blender."""
    ok: bool
    node_id: str
    blender_objects: List[str] = field(default_factory=list)
    generation_id: Optional[str] = None
    bounding_box: Optional[Dict[str, List[float]]] = None
    error: Optional[str] = None
    steps_executed: int = 0
    rolled_back: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "node_id": self.node_id,
            "blender_objects": self.blender_objects,
            "generation_id": self.generation_id,
            "bounding_box": self.bounding_box,
            "error": self.error,
            "steps_executed": self.steps_executed,
            "rolled_back": self.rolled_back,
        }


@dataclass
class VerificationResult:
    """Result of verifying a built node."""
    ok: bool
    node_id: str
    checks_passed: List[str] = field(default_factory=list)
    checks_failed: List[str] = field(default_factory=list)
    dimension_mismatches: List[Dict] = field(default_factory=list)
    mesh_issues: List[Dict] = field(default_factory=list)
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Blender Executor
# ---------------------------------------------------------------------------

class BlenderExecutor:
    """Executes progressive pipeline nodes in Blender via MCP.
    
    Usage:
        executor = BlenderExecutor(mcp_manager, task_id)
        result = await executor.build_node(node, manifest)
        if result.ok:
            verified = await executor.verify_node(node)
    """
    
    def __init__(
        self,
        mcp_manager: Any,
        task_id: str = "",
        dimension_tolerance: float = DEFAULT_DIMENSION_TOLERANCE_M,
        gap_tolerance: float = DEFAULT_GAP_TOLERANCE_M,
    ):
        self.mcp_manager = mcp_manager
        self.task_id = task_id
        self.dimension_tolerance = dimension_tolerance
        self.gap_tolerance = gap_tolerance
        
        # Single collection for entire build - use hash to avoid collision
        # while keeping name reasonably short
        import hashlib
        task_hash = hashlib.sha256(task_id.encode()).hexdigest()[:12] if task_id else "default"
        self._collection_name = f"{BUILD_COLLECTION_PREFIX}_{task_hash}"
        self._collection_created = False
        
        # Track created objects for cleanup
        self._created_objects: List[str] = []
    
    # ══════════════════════════════════════════════════════════════════════
    # Node Building
    # ══════════════════════════════════════════════════════════════════════
    
    async def apply_deferred_modifiers(
        self,
        node: "ManifestNode",
        manifest: "BuildManifest",
    ) -> ExecutionResult:
        """Apply modifiers and materials that were deferred during build.
        
        Called after all BOOLEAN_CUT siblings have been processed.
        This ensures bevels are applied to the final cut geometry.
        """
        from .materials import get_material_for_description
        from .modifiers import get_modifiers_for_style
        from .manifest import MaterialSpec
        
        if not node.blender_objects:
            return ExecutionResult(
                ok=False,
                node_id=node.node_id,
                error="No blender objects to apply modifiers to",
            )
        
        obj_name = node.blender_objects[0]
        steps = 0
        
        try:
            # Infer modifiers from style_hint if not explicitly set
            modifiers = node.modifiers
            if not modifiers:
                decomp_hint = node.stage_outputs.get("decomposition_hint", {})
                style_hint = decomp_hint.get("style_hint", "")
                if style_hint:
                    modifiers = get_modifiers_for_style(style_hint)
                    logger.info(f"[{self.task_id}] Deferred modifiers for {node.label} from '{style_hint}': {[m.type.value for m in modifiers]}")
            
            # Apply modifiers
            if modifiers:
                mod_dicts = [m.to_dict() if hasattr(m, 'to_dict') else m for m in modifiers]
                mod_result = await self._apply_modifiers(obj_name, mod_dicts)
                if not mod_result.get("ok"):
                    logger.warning(f"[{self.task_id}] Modifier application failed for {node.label}: {mod_result.get('errors', [])}")
                steps += 1
            
            # Mesh cleanup
            cleanup_result = await self._cleanup_mesh(obj_name)
            if not cleanup_result.get("ok") and not cleanup_result.get("skipped"):
                logger.warning(f"[{self.task_id}] Mesh cleanup failed for {node.label}: {cleanup_result.get('error')}")
            steps += 1
            
            # Infer material from material_hint if not explicitly set
            material = node.material
            if not material:
                decomp_hint = node.stage_outputs.get("decomposition_hint", {})
                material_hint = decomp_hint.get("material_hint", "")
                if material_hint:
                    preset = get_material_for_description(material_hint)
                    if preset:
                        material = MaterialSpec.from_preset(preset.name)
                        logger.info(f"[{self.task_id}] Deferred material for {node.label} from '{material_hint}': {preset.name}")
            
            # Apply material
            if material:
                mat_result = await self._apply_material_full(obj_name, material)
                if not mat_result.get("ok"):
                    logger.warning(f"[{self.task_id}] Material application failed for {node.label}: {mat_result.get('error')}")
                steps += 1
            
            # Update bounding box (may have changed after modifiers)
            bbox = await self._get_bounding_box(obj_name)
            node.bounding_box = bbox
            
            # Clear the pending flag
            node.stage_outputs.pop("_pending_modifiers", None)
            
            return ExecutionResult(
                ok=True,
                node_id=node.node_id,
                blender_objects=node.blender_objects,
                generation_id=self._collection_name,
                bounding_box=bbox,
                steps_executed=steps,
            )
            
        except Exception as e:
            logger.exception(f"[{self.task_id}] Deferred modifier application failed for {node.label}: {e}")
            return ExecutionResult(
                ok=False,
                node_id=node.node_id,
                error=str(e),
            )

    async def build_boolean_cut(
        self,
        cutter_node: "ManifestNode",
        target_node: "ManifestNode",
        manifest: "BuildManifest",
    ) -> ExecutionResult:
        """Build a boolean cut: create cutter geometry, apply to target, delete cutter.
        
        Args:
            cutter_node: The node with BOOLEAN_CUT socket (defines the hole shape)
            target_node: The node to cut into (must already be built)
            manifest: Build manifest
            
        Returns:
            ExecutionResult with success/failure
        """
        from .node_types import NodeKind, PrimitiveType
        
        # Ensure collection exists
        if not self._collection_created:
            coll_result = await self._create_collection(self._collection_name)
            if not coll_result.get("ok"):
                return ExecutionResult(
                    ok=False,
                    node_id=cutter_node.node_id,
                    error=f"Failed to create collection: {coll_result.get('error')}",
                )
            self._collection_created = True
        
        # Target must have blender objects
        if not target_node.blender_objects:
            return ExecutionResult(
                ok=False,
                node_id=cutter_node.node_id,
                error=f"Target node '{target_node.label}' has no blender objects",
            )
        
        target_obj_name = target_node.blender_objects[0]
        cutter_name = f"{cutter_node.label}_cutter_{uuid.uuid4().hex[:6]}"
        
        try:
            # Compute cutter position (centered on target, or use attachment offset)
            cutter_pos, cutter_rot, _ = self._compute_world_transform(cutter_node, manifest)
            
            # Create cutter geometry
            create_result = await self._create_primitive(
                node=cutter_node,
                obj_name=cutter_name,
                world_pos=cutter_pos,
                world_rot=cutter_rot,
                collection_name=self._collection_name,
            )
            
            if not create_result.get("ok"):
                return ExecutionResult(
                    ok=False,
                    node_id=cutter_node.node_id,
                    error=f"Failed to create cutter: {create_result.get('error')}",
                )
            
            # Apply boolean difference
            bool_result = await self._apply_boolean(
                target_name=target_obj_name,
                cutter_name=cutter_name,
                operation="DIFFERENCE",
                delete_cutter=True,
            )
            
            if not bool_result.get("ok"):
                # Try to clean up cutter
                await self._remove_object(cutter_name)
                return ExecutionResult(
                    ok=False,
                    node_id=cutter_node.node_id,
                    error=f"Boolean operation failed: {bool_result.get('error')}",
                )
            
            # Update target's bounding box (it may have changed)
            new_bbox = await self._get_bounding_box(target_obj_name)
            if new_bbox:
                target_node.bounding_box = new_bbox
            
            # Boolean cut node doesn't create persistent objects (cutter is deleted)
            # but we mark it as successful
            return ExecutionResult(
                ok=True,
                node_id=cutter_node.node_id,
                blender_objects=[],  # Cutter was deleted
                generation_id=self._collection_name,
                bounding_box=None,
                steps_executed=2,  # create + boolean
            )
            
        except Exception as e:
            logger.exception(f"[{self.task_id}] Boolean cut failed for {cutter_node.label}: {e}")
            await self._remove_object(cutter_name)
            return ExecutionResult(
                ok=False,
                node_id=cutter_node.node_id,
                error=str(e),
                rolled_back=True,
            )

    async def build_node(
        self,
        node: "ManifestNode",
        manifest: "BuildManifest",
        defer_modifiers: bool = False,
    ) -> ExecutionResult:
        """Build a single node in Blender.
        
        Creates geometry based on node.geometry spec, applies transform
        from node.attachment, and tracks created objects.
        
        Args:
            node: The node to build
            manifest: Build manifest
            defer_modifiers: If True, skip modifier/material application.
                            Used when this node has pending BOOLEAN_CUT siblings.
        """
        from .node_types import NodeKind, PrimitiveType
        from .materials import get_material_for_description, get_material_preset
        from .modifiers import get_modifiers_for_style
        from .manifest import MaterialSpec
        
        # Ensure collection exists (once per build)
        if not self._collection_created:
            coll_result = await self._create_collection(self._collection_name)
            if not coll_result.get("ok"):
                return ExecutionResult(
                    ok=False,
                    node_id=node.node_id,
                    error=f"Failed to create collection: {coll_result.get('error')}",
                )
            self._collection_created = True
        
        # Generate unique object name
        obj_name = f"{node.label}_{uuid.uuid4().hex[:6]}"
        
        try:
            # Build geometry based on primitive type
            if not node.geometry:
                return ExecutionResult(
                    ok=False,
                    node_id=node.node_id,
                    error="Node has no geometry spec",
                )
            
            # Compute world transform (returns pos, rot_deg, rot_rad)
            world_pos, world_rot, world_rot_rad = self._compute_world_transform(node, manifest)
            
            # Create primitive
            create_result = await self._create_primitive(
                node=node,
                obj_name=obj_name,
                world_pos=world_pos,
                world_rot=world_rot,
                collection_name=self._collection_name,
            )
            
            if not create_result.get("ok"):
                return ExecutionResult(
                    ok=False,
                    node_id=node.node_id,
                    error=f"Failed to create primitive: {create_result.get('error')}",
                )
            
            self._created_objects.append(obj_name)
            
            # Defer modifiers/materials if requested (for boolean cut ordering)
            if defer_modifiers:
                # Store pending modifiers/materials for later application
                node.stage_outputs["_pending_modifiers"] = True
                
                # Get bounding box
                bbox = await self._get_bounding_box(obj_name)
                
                # Store legacy world transform for backward-compatibility.
                # INVARIANT: executor MUST NOT write transform_state.world_matrix.
                # The controller already computed it via hierarchy composition
                # before calling build_node(); writing here would stomp that value.
                node.world_position = world_pos
                node.world_rotation = world_rot_rad
                
                return ExecutionResult(
                    ok=True,
                    node_id=node.node_id,
                    blender_objects=[obj_name],
                    generation_id=self._collection_name,
                    bounding_box=bbox,
                    steps_executed=1,
                )
            
            # Infer modifiers from style_hint if not explicitly set
            modifiers = node.modifiers
            if not modifiers:
                decomp_hint = node.stage_outputs.get("decomposition_hint", {})
                style_hint = decomp_hint.get("style_hint", "")
                logger.info(f"[{self.task_id}] {node.label} decomp_hint: {decomp_hint}")
                if style_hint:
                    modifiers = get_modifiers_for_style(style_hint)
                    logger.info(f"[{self.task_id}] Inferred modifiers for {node.label} from '{style_hint}': {[m.type.value for m in modifiers]}")
            
            # Apply modifiers if specified
            if modifiers:
                mod_dicts = [m.to_dict() if hasattr(m, 'to_dict') else m for m in modifiers]
                mod_result = await self._apply_modifiers(obj_name, mod_dicts)
                if not mod_result.get("ok"):
                    mod_errors = mod_result.get("errors", [])
                    logger.warning(f"[{self.task_id}] Modifier application failed for {node.label}: {mod_errors}")
                    # Don't fail the build for modifier issues, but log them
            
            # Mesh cleanup (remove doubles, recalculate normals)
            cleanup_result = await self._cleanup_mesh(obj_name)
            if not cleanup_result.get("ok") and not cleanup_result.get("skipped"):
                logger.warning(f"[{self.task_id}] Mesh cleanup failed for {node.label}: {cleanup_result.get('error')}")
            
            # Infer material from material_hint if not explicitly set
            material = node.material
            if not material:
                decomp_hint = node.stage_outputs.get("decomposition_hint", {})
                material_hint = decomp_hint.get("material_hint", "")
                if material_hint:
                    preset = get_material_for_description(material_hint)
                    if preset:
                        material = MaterialSpec.from_preset(preset.name)
                        logger.info(f"[{self.task_id}] Inferred material for {node.label} from '{material_hint}': {preset.name}")
                else:
                    logger.info(f"[{self.task_id}] No material_hint for {node.label}, using default")
                    # Apply a default material based on node label
                    preset = get_material_for_description(node.label)
                    if preset:
                        material = MaterialSpec.from_preset(preset.name)
                        logger.info(f"[{self.task_id}] Inferred material for {node.label} from label: {preset.name}")
            
            # Apply material if specified
            if material:
                mat_result = await self._apply_material_full(obj_name, material)
                if not mat_result.get("ok"):
                    logger.warning(f"[{self.task_id}] Material application failed for {node.label}: {mat_result.get('error')}")
            
            # Get bounding box
            bbox = await self._get_bounding_box(obj_name)
            
            # Store legacy world transform for backward-compatibility.
            # INVARIANT: executor MUST NOT write transform_state.world_matrix.
            # The controller already computed it via hierarchy composition
            # before calling build_node(); writing here would stomp that value.
            node.world_position = world_pos
            node.world_rotation = world_rot_rad  # Store in radians
            
            return ExecutionResult(
                ok=True,
                node_id=node.node_id,
                blender_objects=[obj_name],
                generation_id=self._collection_name,
                bounding_box=bbox,
                steps_executed=1,
            )
            
        except Exception as e:
            logger.exception(f"[{self.task_id}] Build failed for {node.label}: {e}")
            # Try to remove the failed object
            await self._remove_object(obj_name)
            return ExecutionResult(
                ok=False,
                node_id=node.node_id,
                error=str(e),
                rolled_back=True,
            )

    
    def _compute_world_transform(
        self,
        node: "ManifestNode",
        manifest: "BuildManifest",
    ) -> Tuple[List[float], List[float], List[float]]:
        """Compute world position and rotation for a node.
        
        PHASE 4: If USE_HIERARCHICAL_TRANSFORMS is True, reads directly from
        node.transform_state.world_matrix (computed by the transform system).
        
        LEGACY: Uses proper matrix composition for rotations.
        - World rotation = composed parent rotations (NOT Euler addition)
        - Local offset is rotated by parent's world rotation before adding
        
        Returns (position, rotation_degrees, rotation_radians).
        """
        from .node_types import SocketType, NodeKind
        import math
        
        # ══════════════════════════════════════════════════════════════════
        # PHASE 4: New hierarchical transform path
        # ══════════════════════════════════════════════════════════════════
        if USE_HIERARCHICAL_TRANSFORMS:
            if hasattr(node, 'transform_state') and node.transform_state is not None:
                world_matrix = node.transform_state.world_matrix
                if world_matrix is not None:
                    # Read directly from pre-computed world matrix
                    world_pos = list(world_matrix.position)
                    world_rot_rad = list(world_matrix.rotation)
                    world_rot_deg = [math.degrees(r) for r in world_rot_rad]
                    
                    logger.info(
                        f"[{self.task_id}] {node.label} using hierarchical transform: "
                        f"pos={[round(p, 4) for p in world_pos]}, "
                        f"rot_deg={[round(r, 2) for r in world_rot_deg]}"
                    )
                    
                    return world_pos, world_rot_deg, world_rot_rad
            
            # Fallback: transform_state not populated — this is a bug
            raise RuntimeError(
                f"{node.label} has no transform_state.world_matrix. "
                f"Stage 4 must populate world_matrix before executor runs."
            )
        
        raise RuntimeError(f"{node.label} has no transform_state")
    
    async def _create_primitive(
        self,
        node: "ManifestNode",
        obj_name: str,
        world_pos: List[float],
        world_rot: List[float],
        collection_name: str,
    ) -> Dict[str, Any]:
        """Create a primitive mesh in Blender."""
        from .node_types import PrimitiveType
        from core.blender_ops import parse_op_output
        
        if not node.geometry:
            return {"ok": False, "error": "No geometry spec"}
        
        prim = node.geometry.primitive
        geo = node.geometry
        
        # Build creation script based on primitive type
        if prim == PrimitiveType.BOX:
            size = geo.size or [1, 1, 1]
            script = self._box_script(obj_name, size, world_pos, world_rot, collection_name)
        elif prim == PrimitiveType.CYLINDER:
            radius = geo.radius or 0.5
            depth = geo.depth or 1.0
            vertices = geo.segments or 32
            script = self._cylinder_script(obj_name, radius, depth, vertices, world_pos, world_rot, collection_name)
        elif prim == PrimitiveType.SPHERE:
            radius = geo.radius or 0.5
            script = self._sphere_script(obj_name, radius, world_pos, collection_name)
        elif prim == PrimitiveType.CONE:
            radius = geo.radius or 0.5
            depth = geo.depth or 1.0
            script = self._cone_script(obj_name, radius, depth, world_pos, world_rot, collection_name)
        elif prim == PrimitiveType.HEMISPHERE:
            radius = geo.radius or 0.5
            script = self._hemisphere_script(obj_name, radius, world_pos, world_rot, collection_name)
        elif prim == PrimitiveType.TORUS:
            major = geo.major_radius or 1.0
            minor = geo.minor_radius or 0.25
            script = self._torus_script(obj_name, major, minor, world_pos, world_rot, collection_name)
        elif prim == PrimitiveType.U_SHAPE:
            major = geo.major_radius or 0.5
            minor = geo.minor_radius or 0.05
            script = self._u_shape_script(obj_name, major, minor, world_pos, world_rot, collection_name)
        else:
            # Default to box
            size = geo.size or [1, 1, 1]
            script = self._box_script(obj_name, size, world_pos, world_rot, collection_name)
        
        try:
            result = await self.mcp_manager.call_locked(
                "blender", "execute_blender_code", {"code": script}
            )
            return parse_op_output(result.get("output", ""))
        except Exception as e:
            return {"ok": False, "error": str(e)}

    
    # ══════════════════════════════════════════════════════════════════════
    # Blender Script Templates
    # ══════════════════════════════════════════════════════════════════════
    
    def _box_script(
        self,
        name: str,
        size: List[float],
        pos: List[float],
        rot: List[float],
        collection: str,
    ) -> str:
        """Generate script to create a box."""
        return f'''
import bpy
import bmesh
import json
import math

name = {repr(name)}
size = {size}
pos = {pos}
rot_deg = {rot}
coll_name = {repr(collection)}

if name in bpy.data.objects:
    result = {{"ok": False, "error": f"Object '{{name}}' already exists"}}
else:
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co.x *= size[0]
        v.co.y *= size[1]
        v.co.z *= size[2]
    bm.to_mesh(mesh)
    bm.free()
    
    obj = bpy.data.objects.new(name, mesh)
    obj.location = tuple(pos)
    obj.rotation_euler = tuple(math.radians(r) for r in rot_deg)
    
    coll = bpy.data.collections.get(coll_name)
    if coll:
        coll.objects.link(obj)
    else:
        bpy.context.collection.objects.link(obj)
    
    result = {{"ok": True, "name": obj.name, "location": list(obj.location)}}

print("SENTINEL_OUTPUT_START" + json.dumps(result) + "SENTINEL_OUTPUT_END")
'''
    
    def _cylinder_script(
        self,
        name: str,
        radius: float,
        depth: float,
        vertices: int,
        pos: List[float],
        rot: List[float],
        collection: str,
    ) -> str:
        """Generate script to create a cylinder."""
        return f'''
import bpy
import json
import math

name = {repr(name)}
radius = {radius}
depth = {depth}
vertices = {vertices}
pos = {pos}
rot_deg = {rot}
coll_name = {repr(collection)}

if name in bpy.data.objects:
    result = {{"ok": False, "error": f"Object '{{name}}' already exists"}}
else:
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=vertices, radius=radius, depth=depth,
        location=tuple(pos),
        rotation=tuple(math.radians(r) for r in rot_deg)
    )
    obj = bpy.context.active_object
    obj.name = name
    obj.data.name = name
    
    # Move to collection
    coll = bpy.data.collections.get(coll_name)
    if coll:
        for c in obj.users_collection:
            c.objects.unlink(obj)
        coll.objects.link(obj)
    
    result = {{"ok": True, "name": obj.name, "location": list(obj.location)}}

print("SENTINEL_OUTPUT_START" + json.dumps(result) + "SENTINEL_OUTPUT_END")
'''
    
    def _sphere_script(
        self,
        name: str,
        radius: float,
        pos: List[float],
        collection: str,
    ) -> str:
        """Generate script to create a sphere."""
        return f'''
import bpy
import json

name = {repr(name)}
radius = {radius}
pos = {pos}
coll_name = {repr(collection)}

if name in bpy.data.objects:
    result = {{"ok": False, "error": f"Object '{{name}}' already exists"}}
else:
    bpy.ops.mesh.primitive_uv_sphere_add(radius=radius, location=tuple(pos))
    obj = bpy.context.active_object
    obj.name = name
    obj.data.name = name
    
    coll = bpy.data.collections.get(coll_name)
    if coll:
        for c in obj.users_collection:
            c.objects.unlink(obj)
        coll.objects.link(obj)
    
    result = {{"ok": True, "name": obj.name, "location": list(obj.location)}}

print("SENTINEL_OUTPUT_START" + json.dumps(result) + "SENTINEL_OUTPUT_END")
'''
    
    def _cone_script(
        self,
        name: str,
        radius: float,
        depth: float,
        pos: List[float],
        rot: List[float],
        collection: str,
    ) -> str:
        """Generate script to create a cone."""
        return f'''
import bpy
import json
import math

name = {repr(name)}
radius = {radius}
depth = {depth}
pos = {pos}
rot_deg = {rot}
coll_name = {repr(collection)}

if name in bpy.data.objects:
    result = {{"ok": False, "error": f"Object '{{name}}' already exists"}}
else:
    bpy.ops.mesh.primitive_cone_add(
        radius1=radius, depth=depth,
        location=tuple(pos),
        rotation=tuple(math.radians(r) for r in rot_deg)
    )
    obj = bpy.context.active_object
    obj.name = name
    obj.data.name = name
    
    coll = bpy.data.collections.get(coll_name)
    if coll:
        for c in obj.users_collection:
            c.objects.unlink(obj)
        coll.objects.link(obj)
    
    result = {{"ok": True, "name": obj.name, "location": list(obj.location)}}

print("SENTINEL_OUTPUT_START" + json.dumps(result) + "SENTINEL_OUTPUT_END")
'''
    
    def _hemisphere_script(
        self,
        name: str,
        radius: float,
        pos: List[float],
        rot: List[float],
        collection: str,
    ) -> str:
        """Generate script to create a hemisphere via bisect."""
        return f'''
import bpy
import bmesh
import json
import math

name = {repr(name)}
radius = {radius}
pos = {pos}
rot_deg = {rot}
coll_name = {repr(collection)}

if name in bpy.data.objects:
    result = {{"ok": False, "error": f"Object '{{name}}' already exists"}}
else:
    bpy.ops.mesh.primitive_uv_sphere_add(radius=radius, location=(0, 0, 0))
    obj = bpy.context.active_object
    obj.name = name
    obj.data.name = name
    
    # Bisect to create hemisphere
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
    bmesh.ops.bisect_plane(
        bm, geom=geom,
        plane_co=(0, 0, 0), plane_no=(0, 0, 1),
        clear_inner=True, clear_outer=False
    )
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.0001)
    boundary = [e for e in bm.edges if len(e.link_faces) == 1]
    if boundary:
        bmesh.ops.edgeloop_fill(bm, edges=boundary)
    bm.to_mesh(obj.data)
    bm.free()
    
    obj.location = tuple(pos)
    obj.rotation_euler = tuple(math.radians(r) for r in rot_deg)
    
    coll = bpy.data.collections.get(coll_name)
    if coll:
        for c in obj.users_collection:
            c.objects.unlink(obj)
        coll.objects.link(obj)
    
    result = {{"ok": True, "name": obj.name, "location": list(obj.location)}}

print("SENTINEL_OUTPUT_START" + json.dumps(result) + "SENTINEL_OUTPUT_END")
'''
    
    def _torus_script(
        self,
        name: str,
        major: float,
        minor: float,
        pos: List[float],
        rot: List[float],
        collection: str,
    ) -> str:
        """Generate script to create a torus."""
        return f'''
import bpy
import json
import math

name = {repr(name)}
major = {major}
minor = {minor}
pos = {pos}
rot_deg = {rot}
coll_name = {repr(collection)}

if name in bpy.data.objects:
    result = {{"ok": False, "error": f"Object '{{name}}' already exists"}}
else:
    bpy.ops.mesh.primitive_torus_add(
        major_radius=major, minor_radius=minor,
        location=tuple(pos),
        rotation=tuple(math.radians(r) for r in rot_deg)
    )
    obj = bpy.context.active_object
    obj.name = name
    obj.data.name = name
    
    coll = bpy.data.collections.get(coll_name)
    if coll:
        for c in obj.users_collection:
            c.objects.unlink(obj)
        coll.objects.link(obj)
    
    result = {{"ok": True, "name": obj.name, "location": list(obj.location)}}

print("SENTINEL_OUTPUT_START" + json.dumps(result) + "SENTINEL_OUTPUT_END")
'''

    def _u_shape_script(
        self,
        name: str,
        major: float,
        minor: float,
        pos: List[float],
        rot: List[float],
        collection: str,
    ) -> str:
        """Generate script to create a U-shape (half torus) via bisect.
        
        Used for padlock shackles, handles, hooks — any bent tube.
        The open end faces -Y (front), legs point downward (-Z).
        major_radius = radius of the U arc center-line
        minor_radius = tube thickness
        """
        return f'''
import bpy
import bmesh
import json
import math

name = {repr(name)}
major = {major}
minor = {minor}
pos = {pos}
rot_deg = {rot}
coll_name = {repr(collection)}

if name in bpy.data.objects:
    result = {{"ok": False, "error": f"Object '{{name}}' already exists"}}
else:
    bpy.ops.mesh.primitive_torus_add(
        major_radius=major, minor_radius=minor,
        major_segments=48, minor_segments=16,
        location=(0, 0, 0), rotation=(0, 0, 0)
    )
    obj = bpy.context.active_object
    obj.name = name
    obj.data.name = name
    
    # Bisect: keep only the half where Y >= 0 (back half = U shape opening toward -Y)
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
    bmesh.ops.bisect_plane(
        bm, geom=geom,
        plane_co=(0, 0, 0), plane_no=(0, 1, 0),
        clear_inner=True, clear_outer=False
    )
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.0001)
    # Cap the open ends
    boundary = [e for e in bm.edges if len(e.link_faces) == 1]
    if boundary:
        bmesh.ops.edgeloop_fill(bm, edges=boundary)
    bm.to_mesh(obj.data)
    bm.free()
    
    obj.location = tuple(pos)
    obj.rotation_euler = tuple(math.radians(r) for r in rot_deg)
    
    coll = bpy.data.collections.get(coll_name)
    if coll:
        for c in obj.users_collection:
            c.objects.unlink(obj)
        coll.objects.link(obj)
    
    result = {{"ok": True, "name": obj.name, "location": list(obj.location)}}

print("SENTINEL_OUTPUT_START" + json.dumps(result) + "SENTINEL_OUTPUT_END")
'''

    # ══════════════════════════════════════════════════════════════════════
    # Helper Operations
    # ══════════════════════════════════════════════════════════════════════
    
    async def _apply_boolean(
        self,
        target_name: str,
        cutter_name: str,
        operation: str = "DIFFERENCE",
        delete_cutter: bool = True,
    ) -> Dict[str, Any]:
        """Apply boolean operation between two objects.
        
        Args:
            target_name: Object to modify
            cutter_name: Object to use as cutter
            operation: DIFFERENCE, UNION, or INTERSECT
            delete_cutter: Whether to delete cutter after operation
        """
        from core.blender_ops import parse_op_output
        
        script = f'''
import bpy
import json

target_name = {repr(target_name)}
cutter_name = {repr(cutter_name)}
operation = {repr(operation)}
delete_cutter = {delete_cutter}

target = bpy.data.objects.get(target_name)
cutter = bpy.data.objects.get(cutter_name)

if not target:
    result = {{"ok": False, "error": f"Target '{{target_name}}' not found"}}
elif not cutter:
    result = {{"ok": False, "error": f"Cutter '{{cutter_name}}' not found"}}
else:
    # Add boolean modifier
    mod = target.modifiers.new(name="Boolean", type='BOOLEAN')
    mod.operation = operation
    mod.object = cutter
    
    # Apply modifier
    bpy.context.view_layer.objects.active = target
    try:
        bpy.ops.object.modifier_apply(modifier=mod.name)
        applied = True
    except Exception as e:
        applied = False
        error_msg = str(e)
    
    if applied:
        if delete_cutter:
            bpy.data.objects.remove(cutter, do_unlink=True)
        result = {{"ok": True, "target": target_name, "operation": operation, "cutter_deleted": delete_cutter}}
    else:
        # Remove failed modifier
        if mod.name in target.modifiers:
            target.modifiers.remove(mod)
        result = {{"ok": False, "error": f"Failed to apply boolean: {{error_msg}}"}}

print("SENTINEL_OUTPUT_START" + json.dumps(result) + "SENTINEL_OUTPUT_END")
'''
        try:
            result = await self.mcp_manager.call_locked(
                "blender", "execute_blender_code", {"code": script}
            )
            return parse_op_output(result.get("output", ""))
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def _apply_material(
        self,
        obj_name: str,
        material: Any,  # MaterialSpec
    ) -> Dict[str, Any]:
        """Apply basic material to an object (legacy method)."""
        return await self._apply_material_full(obj_name, material)
    
    async def _apply_material_full(
        self,
        obj_name: str,
        material: Any,  # MaterialSpec
    ) -> Dict[str, Any]:
        """Apply full PBR material to an object.
        
        Supports:
        - Base color, metallic, roughness
        - Emission
        - Transmission (glass)
        - Subsurface scattering
        - Clearcoat
        - Sheen
        """
        from core.blender_ops import parse_op_output
        
        # Extract material properties
        color = list(material.base_color) if material.base_color else [0.8, 0.8, 0.8, 1.0]
        if len(color) == 3:
            color.append(1.0)
        
        metallic = getattr(material, 'metallic', 0.0) or 0.0
        roughness = getattr(material, 'roughness', 0.5) or 0.5
        
        # Emission
        emission_color = getattr(material, 'emission_color', None)
        emission_strength = getattr(material, 'emission_strength', 0.0) or 0.0
        
        # Transmission
        transmission = getattr(material, 'transmission', 0.0) or 0.0
        ior = getattr(material, 'ior', 1.45) or 1.45
        
        # Subsurface
        subsurface = getattr(material, 'subsurface', 0.0) or 0.0
        
        # Clearcoat
        clearcoat = getattr(material, 'clearcoat', 0.0) or 0.0
        clearcoat_roughness = getattr(material, 'clearcoat_roughness', 0.03) or 0.03
        
        # Sheen
        sheen = getattr(material, 'sheen', 0.0) or 0.0
        
        # Specular
        specular = getattr(material, 'specular', 0.5) or 0.5
        
        script = f'''
import bpy
import json

obj_name = {repr(obj_name)}
color = {color}
metallic = {metallic}
roughness = {roughness}
emission_color = {emission_color if emission_color else 'None'}
emission_strength = {emission_strength}
transmission = {transmission}
ior = {ior}
subsurface = {subsurface}
clearcoat = {clearcoat}
clearcoat_roughness = {clearcoat_roughness}
sheen = {sheen}
specular = {specular}

obj = bpy.data.objects.get(obj_name)
if not obj:
    result = {{"ok": False, "error": f"Object '{{obj_name}}' not found"}}
else:
    mat_name = f"Mat_{{obj.name}}"
    mat = bpy.data.materials.get(mat_name) or bpy.data.materials.new(name=mat_name)
    mat.use_nodes = True
    
    # Find Principled BSDF
    bsdf = None
    for node in mat.node_tree.nodes:
        if node.type == 'BSDF_PRINCIPLED':
            bsdf = node
            break
    
    if bsdf:
        # Base PBR
        if "Base Color" in bsdf.inputs:
            bsdf.inputs["Base Color"].default_value = tuple(color)
        if "Metallic" in bsdf.inputs:
            bsdf.inputs["Metallic"].default_value = metallic
        if "Roughness" in bsdf.inputs:
            bsdf.inputs["Roughness"].default_value = roughness
        if "Specular IOR Level" in bsdf.inputs:
            bsdf.inputs["Specular IOR Level"].default_value = specular
        elif "Specular" in bsdf.inputs:
            bsdf.inputs["Specular"].default_value = specular
        
        # Emission
        if emission_color and emission_strength > 0:
            if "Emission Color" in bsdf.inputs:
                bsdf.inputs["Emission Color"].default_value = tuple(emission_color) + (1.0,) if len(emission_color) == 3 else tuple(emission_color)
            elif "Emission" in bsdf.inputs:
                bsdf.inputs["Emission"].default_value = tuple(emission_color) + (1.0,) if len(emission_color) == 3 else tuple(emission_color)
            if "Emission Strength" in bsdf.inputs:
                bsdf.inputs["Emission Strength"].default_value = emission_strength
        
        # Transmission (glass)
        if transmission > 0:
            if "Transmission" in bsdf.inputs:
                bsdf.inputs["Transmission"].default_value = transmission
            if "IOR" in bsdf.inputs:
                bsdf.inputs["IOR"].default_value = ior
            # Make material use alpha blend for glass
            mat.blend_method = 'BLEND'
            # shadow_method was removed in Blender 4.0+, use try/except
            try:
                mat.shadow_method = 'HASHED'
            except AttributeError:
                pass  # Blender 4.0+ doesn't have shadow_method
        
        # Subsurface
        if subsurface > 0:
            if "Subsurface Weight" in bsdf.inputs:
                bsdf.inputs["Subsurface Weight"].default_value = subsurface
            elif "Subsurface" in bsdf.inputs:
                bsdf.inputs["Subsurface"].default_value = subsurface
        
        # Clearcoat
        if clearcoat > 0:
            if "Coat Weight" in bsdf.inputs:
                bsdf.inputs["Coat Weight"].default_value = clearcoat
            elif "Clearcoat" in bsdf.inputs:
                bsdf.inputs["Clearcoat"].default_value = clearcoat
            if "Coat Roughness" in bsdf.inputs:
                bsdf.inputs["Coat Roughness"].default_value = clearcoat_roughness
            elif "Clearcoat Roughness" in bsdf.inputs:
                bsdf.inputs["Clearcoat Roughness"].default_value = clearcoat_roughness
        
        # Sheen
        if sheen > 0:
            if "Sheen Weight" in bsdf.inputs:
                bsdf.inputs["Sheen Weight"].default_value = sheen
            elif "Sheen" in bsdf.inputs:
                bsdf.inputs["Sheen"].default_value = sheen
    
    # Assign material to object
    if obj.data and hasattr(obj.data, "materials"):
        if len(obj.data.materials) == 0:
            obj.data.materials.append(mat)
        else:
            obj.data.materials[0] = mat
    
    result = {{"ok": True, "material": mat.name}}

print("SENTINEL_OUTPUT_START" + json.dumps(result) + "SENTINEL_OUTPUT_END")
'''
        try:
            result = await self.mcp_manager.call_locked(
                "blender", "execute_blender_code", {"code": script}
            )
            return parse_op_output(result.get("output", ""))
        except Exception as e:
            return {"ok": False, "error": str(e)}
    
    async def _apply_modifiers(
        self,
        obj_name: str,
        modifiers: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Apply a list of modifiers to an object.
        
        Modifiers are applied in order. Each modifier dict should have:
        - type: ModifierType value (string)
        - apply: bool (whether to apply destructively)
        - type-specific parameters
        """
        from core.blender_ops import parse_op_output
        
        # Convert modifier specs to serializable format
        mod_list = []
        for mod in modifiers:
            if hasattr(mod, 'to_dict'):
                mod_list.append(mod.to_dict())
            elif isinstance(mod, dict):
                mod_list.append(mod)
        
        script = f'''
import bpy
import json
import math

obj_name = {repr(obj_name)}
modifiers = {repr(mod_list)}

obj = bpy.data.objects.get(obj_name)
if not obj:
    result = {{"ok": False, "error": f"Object '{{obj_name}}' not found"}}
else:
    applied = []
    errors = []
    
    for mod_spec in modifiers:
        mod_type = mod_spec.get("type", "")
        should_apply = mod_spec.get("apply", True)
        mod_name = mod_spec.get("name") or f"Sentinel_{{mod_type}}"
        
        try:
            if mod_type == "subdivision":
                mod = obj.modifiers.new(name=mod_name, type='SUBSURF')
                mod.levels = mod_spec.get("subdivision_levels", 2)
                mod.render_levels = mod_spec.get("subdivision_render_levels", 2)
                mod.subdivision_type = mod_spec.get("subdivision_type", "CATMULL_CLARK")
                
            elif mod_type == "bevel":
                mod = obj.modifiers.new(name=mod_name, type='BEVEL')
                mod.width = mod_spec.get("bevel_width", 0.02)
                mod.segments = mod_spec.get("bevel_segments", 3)
                mod.limit_method = mod_spec.get("bevel_limit_method", "ANGLE")
                mod.angle_limit = math.radians(mod_spec.get("bevel_angle_limit", 30.0))
                mod.profile = mod_spec.get("bevel_profile", 0.5)
                
            elif mod_type == "solidify":
                mod = obj.modifiers.new(name=mod_name, type='SOLIDIFY')
                mod.thickness = mod_spec.get("solidify_thickness", 0.01)
                mod.offset = mod_spec.get("solidify_offset", -1.0)
                mod.use_even_offset = mod_spec.get("solidify_even_thickness", True)
                
            elif mod_type == "mirror":
                mod = obj.modifiers.new(name=mod_name, type='MIRROR')
                axis = mod_spec.get("mirror_axis", [True, False, False])
                mod.use_axis[0] = axis[0] if len(axis) > 0 else True
                mod.use_axis[1] = axis[1] if len(axis) > 1 else False
                mod.use_axis[2] = axis[2] if len(axis) > 2 else False
                mod.use_mirror_merge = mod_spec.get("mirror_merge", True)
                mod.merge_threshold = mod_spec.get("mirror_merge_threshold", 0.001)
                
            elif mod_type == "array":
                mod = obj.modifiers.new(name=mod_name, type='ARRAY')
                mod.count = mod_spec.get("array_count", 2)
                mod.use_relative_offset = mod_spec.get("array_use_relative_offset", True)
                offset = mod_spec.get("array_offset", [1.0, 0.0, 0.0])
                mod.relative_offset_displace[0] = offset[0] if len(offset) > 0 else 1.0
                mod.relative_offset_displace[1] = offset[1] if len(offset) > 1 else 0.0
                mod.relative_offset_displace[2] = offset[2] if len(offset) > 2 else 0.0
                
            elif mod_type == "weighted_normal":
                mod = obj.modifiers.new(name=mod_name, type='WEIGHTED_NORMAL')
                mod.weight = mod_spec.get("weighted_normal_weight", 50)
                mod.keep_sharp = mod_spec.get("weighted_normal_keep_sharp", True)
                
            elif mod_type == "smooth":
                mod = obj.modifiers.new(name=mod_name, type='SMOOTH')
                mod.factor = mod_spec.get("smooth_factor", 0.5)
                mod.iterations = mod_spec.get("smooth_iterations", 1)
                
            elif mod_type == "edge_split":
                mod = obj.modifiers.new(name=mod_name, type='EDGE_SPLIT')
                mod.split_angle = math.radians(mod_spec.get("edge_split_angle", 30.0))
                
            elif mod_type == "triangulate":
                mod = obj.modifiers.new(name=mod_name, type='TRIANGULATE')
                
            elif mod_type == "decimate":
                mod = obj.modifiers.new(name=mod_name, type='DECIMATE')
                mod.ratio = mod_spec.get("decimate_ratio", 0.5)
                mod.decimate_type = mod_spec.get("decimate_type", "COLLAPSE")
                
            elif mod_type == "simple_deform":
                mod = obj.modifiers.new(name=mod_name, type='SIMPLE_DEFORM')
                mod.deform_method = mod_spec.get("deform_method", "BEND")
                mod.angle = mod_spec.get("deform_angle", 0.0)
                mod.factor = mod_spec.get("deform_factor", 0.0)
                mod.deform_axis = mod_spec.get("deform_axis", "X")
            else:
                errors.append(f"Unknown modifier type: {{mod_type}}")
                continue
            
            # Apply modifier if requested
            if should_apply:
                bpy.context.view_layer.objects.active = obj
                try:
                    bpy.ops.object.modifier_apply(modifier=mod.name)
                    applied.append(mod_name)
                except Exception as e:
                    errors.append(f"Failed to apply {{mod_name}}: {{str(e)}}")
            else:
                applied.append(f"{{mod_name}} (live)")
                
        except Exception as e:
            errors.append(f"Failed to create {{mod_type}}: {{str(e)}}")
    
    result = {{
        "ok": len(errors) == 0,
        "applied": applied,
        "errors": errors,
    }}

print("SENTINEL_OUTPUT_START" + json.dumps(result) + "SENTINEL_OUTPUT_END")
'''
        try:
            result = await self.mcp_manager.call_locked(
                "blender", "execute_blender_code", {"code": script}
            )
            return parse_op_output(result.get("output", ""))
        except Exception as e:
            return {"ok": False, "error": str(e)}
    
    async def _cleanup_mesh(
        self,
        obj_name: str,
        remove_doubles: bool = True,
        recalc_normals: bool = True,
        merge_distance: float = 0.0001,
    ) -> Dict[str, Any]:
        """Clean up mesh geometry.
        
        Operations:
        1. Remove doubles (merge by distance)
        2. Recalculate normals (make consistent)
        3. Remove loose vertices/edges
        """
        from core.blender_ops import parse_op_output
        
        script = f'''
import bpy
import bmesh
import json

obj_name = {repr(obj_name)}
remove_doubles = {remove_doubles}
recalc_normals = {recalc_normals}
merge_distance = {merge_distance}

obj = bpy.data.objects.get(obj_name)
if not obj or obj.type != 'MESH':
    result = {{"ok": True, "skipped": True, "reason": "not_mesh"}}
else:
    stats = {{}}
    
    # Work with bmesh for cleanup
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    
    # Remove doubles
    if remove_doubles:
        before_verts = len(bm.verts)
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=merge_distance)
        after_verts = len(bm.verts)
        stats["doubles_removed"] = before_verts - after_verts
    
    # Recalculate normals
    if recalc_normals:
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        stats["normals_recalculated"] = True
    
    # Remove loose geometry
    loose_verts = [v for v in bm.verts if not v.link_edges]
    loose_edges = [e for e in bm.edges if not e.link_faces]
    
    if loose_verts:
        bmesh.ops.delete(bm, geom=loose_verts, context='VERTS')
        stats["loose_verts_removed"] = len(loose_verts)
    
    if loose_edges:
        bmesh.ops.delete(bm, geom=loose_edges, context='EDGES')
        stats["loose_edges_removed"] = len(loose_edges)
    
    # Write back to mesh
    bm.to_mesh(obj.data)
    bm.free()
    
    # Update mesh
    obj.data.update()
    
    result = {{"ok": True, "stats": stats}}

print("SENTINEL_OUTPUT_START" + json.dumps(result) + "SENTINEL_OUTPUT_END")
'''
        try:
            result = await self.mcp_manager.call_locked(
                "blender", "execute_blender_code", {"code": script}
            )
            return parse_op_output(result.get("output", ""))
        except Exception as e:
            return {"ok": False, "error": str(e)}
    
    async def _remove_object(self, obj_name: str) -> Dict[str, Any]:
        """Remove a single object from Blender."""
        from core.blender_ops import parse_op_output
        
        script = f'''
import bpy
import json

obj = bpy.data.objects.get({repr(obj_name)})
if obj:
    bpy.data.objects.remove(obj, do_unlink=True)
    result = {{"ok": True, "removed": True}}
else:
    result = {{"ok": True, "removed": False}}

print("SENTINEL_OUTPUT_START" + json.dumps(result) + "SENTINEL_OUTPUT_END")
'''
        try:
            result = await self.mcp_manager.call_locked(
                "blender", "execute_blender_code", {"code": script}
            )
            return parse_op_output(result.get("output", ""))
        except Exception as e:
            return {"ok": False, "error": str(e)}
    
    async def _create_collection(self, collection_name: str) -> Dict[str, Any]:
        """Create a collection for this generation."""
        from core.blender_ops import parse_op_output
        
        script = f'''
import bpy
import json

coll_name = {repr(collection_name)}

if coll_name not in bpy.data.collections:
    coll = bpy.data.collections.new(coll_name)
    bpy.context.scene.collection.children.link(coll)
    result = {{"ok": True, "created": True, "name": coll_name}}
else:
    result = {{"ok": True, "created": False, "name": coll_name}}

print("SENTINEL_OUTPUT_START" + json.dumps(result) + "SENTINEL_OUTPUT_END")
'''
        try:
            result = await self.mcp_manager.call_locked(
                "blender", "execute_blender_code", {"code": script}
            )
            return parse_op_output(result.get("output", ""))
        except Exception as e:
            return {"ok": False, "error": str(e)}
    
    async def _get_bounding_box(self, obj_name: str) -> Optional[Dict[str, List[float]]]:
        """Get world-space bounding box of an object."""
        from core.blender_ops import parse_op_output
        
        script = f'''
import bpy
import json
from mathutils import Vector

obj = bpy.data.objects.get({repr(obj_name)})
if not obj or obj.type != 'MESH':
    result = {{"ok": False, "error": "not_found"}}
else:
    world_verts = [obj.matrix_world @ Vector(v.co) for v in obj.data.vertices]
    if world_verts:
        bbox_min = [min(v[i] for v in world_verts) for i in range(3)]
        bbox_max = [max(v[i] for v in world_verts) for i in range(3)]
        result = {{"ok": True, "min": bbox_min, "max": bbox_max}}
    else:
        result = {{"ok": False, "error": "no_vertices"}}

print("SENTINEL_OUTPUT_START" + json.dumps(result) + "SENTINEL_OUTPUT_END")
'''
        try:
            result = await self.mcp_manager.call_locked(
                "blender", "execute_blender_code", {"code": script}
            )
            data = parse_op_output(result.get("output", ""))
            if data.get("ok"):
                return {"min": data["min"], "max": data["max"]}
            return None
        except Exception:
            return None

    
    # ══════════════════════════════════════════════════════════════════════
    # Verification
    # ══════════════════════════════════════════════════════════════════════
    
    async def verify_node(
        self,
        node: "ManifestNode",
    ) -> VerificationResult:
        """Verify a built node meets its spec.
        
        Checks:
        1. Object exists in Blender
        2. Dimensions match spec (within tolerance)
        3. Mesh is valid (no degenerate faces)
        """
        checks_passed = []
        checks_failed = []
        dimension_mismatches = []
        mesh_issues = []
        
        if not node.blender_objects:
            return VerificationResult(
                ok=False,
                node_id=node.node_id,
                error="No blender objects to verify",
            )
        
        obj_name = node.blender_objects[0]
        
        # Check 1: Object exists
        exists = await self._check_object_exists(obj_name)
        if exists:
            checks_passed.append("object_exists")
        else:
            checks_failed.append("object_exists")
            return VerificationResult(
                ok=False,
                node_id=node.node_id,
                checks_passed=checks_passed,
                checks_failed=checks_failed,
                error=f"Object {obj_name} not found in Blender",
            )
        
        # Check 2: Dimensions match
        if node.geometry:
            dim_result = await self._verify_dimensions(obj_name, node)
            if dim_result["ok"]:
                checks_passed.append("dimensions")
            else:
                checks_failed.append("dimensions")
                dimension_mismatches = dim_result.get("mismatches", [])
        
        # Check 3: Mesh validity
        mesh_result = await self._verify_mesh(obj_name)
        if mesh_result["ok"]:
            checks_passed.append("mesh_valid")
        else:
            checks_failed.append("mesh_valid")
            mesh_issues = mesh_result.get("issues", [])
        
        # Overall result
        ok = len(checks_failed) == 0
        
        return VerificationResult(
            ok=ok,
            node_id=node.node_id,
            checks_passed=checks_passed,
            checks_failed=checks_failed,
            dimension_mismatches=dimension_mismatches,
            mesh_issues=mesh_issues,
        )
    
    async def _check_object_exists(self, obj_name: str) -> bool:
        """Check if object exists in Blender."""
        from core.blender_ops import parse_op_output
        
        script = f'''
import bpy
import json
result = {{"ok": {repr(obj_name)} in bpy.data.objects}}
print("SENTINEL_OUTPUT_START" + json.dumps(result) + "SENTINEL_OUTPUT_END")
'''
        try:
            result = await self.mcp_manager.call_locked(
                "blender", "execute_blender_code", {"code": script}
            )
            data = parse_op_output(result.get("output", ""))
            return data.get("ok", False)
        except Exception:
            return False
    
    async def _verify_dimensions(
        self,
        obj_name: str,
        node: "ManifestNode",
    ) -> Dict[str, Any]:
        """Verify object dimensions match spec."""
        from core.blender_ops import parse_op_output
        from .node_types import PrimitiveType
        
        script = f'''
import bpy
import json
from mathutils import Vector

obj = bpy.data.objects.get({repr(obj_name)})
if not obj or obj.type != 'MESH':
    result = {{"ok": False, "error": "not_mesh"}}
else:
    # Use world-space vertices so rotated objects measure correctly.
    # Local-space extents are wrong for any non-identity rotation because
    # the local X/Y/Z axes don't align with the world axes after rotation.
    world_verts = [obj.matrix_world @ v.co for v in obj.data.vertices]
    if not world_verts:
        result = {{"ok": False, "error": "no_vertices"}}
    else:
        world_min = [min(v[i] for v in world_verts) for i in range(3)]
        world_max = [max(v[i] for v in world_verts) for i in range(3)]
        world_size = [world_max[i] - world_min[i] for i in range(3)]
        result = {{"ok": True, "scaled_size": world_size}}

print("SENTINEL_OUTPUT_START" + json.dumps(result) + "SENTINEL_OUTPUT_END")
'''
        try:
            result = await self.mcp_manager.call_locked(
                "blender", "execute_blender_code", {"code": script}
            )
            data = parse_op_output(result.get("output", ""))
            
            if not data.get("ok"):
                return {"ok": False, "error": data.get("error")}
            
            actual_size = data["scaled_size"]
            mismatches = []
            
            # Compare against spec
            if node.geometry:
                geo = node.geometry
                prim = geo.primitive
                
                if prim == PrimitiveType.BOX:
                    expected = geo.size or [1, 1, 1]
                    for i, axis in enumerate(["X", "Y", "Z"]):
                        diff = abs(actual_size[i] - expected[i])
                        if diff > self.dimension_tolerance:
                            mismatches.append({
                                "axis": axis,
                                "expected": expected[i],
                                "actual": round(actual_size[i], 4),
                                "diff": round(diff, 4),
                            })
                
                elif prim == PrimitiveType.CYLINDER:
                    expected_d = (geo.radius or 0.5) * 2
                    expected_h = geo.depth or 1.0
                    
                    if abs(actual_size[0] - expected_d) > self.dimension_tolerance:
                        mismatches.append({
                            "axis": "diameter",
                            "expected": expected_d,
                            "actual": round(actual_size[0], 4),
                        })
                    if abs(actual_size[2] - expected_h) > self.dimension_tolerance:
                        mismatches.append({
                            "axis": "height",
                            "expected": expected_h,
                            "actual": round(actual_size[2], 4),
                        })
            
            return {"ok": len(mismatches) == 0, "mismatches": mismatches}
            
        except Exception as e:
            return {"ok": False, "error": str(e)}
    
    async def _verify_mesh(self, obj_name: str) -> Dict[str, Any]:
        """Verify mesh is valid (no degenerate geometry)."""
        from core.blender_ops import parse_op_output
        
        script = f'''
import bpy
import bmesh
import json

obj = bpy.data.objects.get({repr(obj_name)})
if not obj or obj.type != 'MESH':
    result = {{"ok": True, "skipped": True}}
else:
    issues = []
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    
    degen = sum(1 for f in bm.faces if f.calc_area() < 1e-8)
    if degen > 0:
        issues.append(f"{{degen}} degenerate faces")
    
    non_manifold = sum(1 for e in bm.edges if not e.is_manifold)
    if non_manifold > 0:
        issues.append(f"{{non_manifold}} non-manifold edges")
    
    bm.free()
    result = {{"ok": len(issues) == 0, "issues": issues}}

print("SENTINEL_OUTPUT_START" + json.dumps(result) + "SENTINEL_OUTPUT_END")
'''
        try:
            result = await self.mcp_manager.call_locked(
                "blender", "execute_blender_code", {"code": script}
            )
            return parse_op_output(result.get("output", ""))
        except Exception as e:
            return {"ok": False, "error": str(e), "issues": [str(e)]}

    
    # ══════════════════════════════════════════════════════════════════════
    # Assembly Operations
    # ══════════════════════════════════════════════════════════════════════
    
    async def merge_assembly(
        self,
        node: "ManifestNode",
        manifest: "BuildManifest",
    ) -> ExecutionResult:
        """Merge verified children into an assembly.
        
        Creates a parent empty and parents all child objects to it.
        """
        from core.blender_ops import parse_op_output
        
        empty_name = f"{node.label}_assembly_{uuid.uuid4().hex[:6]}"
        
        # Collect child object names
        child_objects = []
        for cid in node.children_ids:
            child = manifest.nodes.get(cid)
            if child and child.blender_objects:
                child_objects.extend(child.blender_objects)
        
        if not child_objects:
            return ExecutionResult(
                ok=False,
                node_id=node.node_id,
                error="No child objects to merge",
            )
        
        # Find the ROOT child's first blender object to use as the assembly origin.
        # This keeps parent.world_position aligned with what Stage 4 uses as the
        # assembly's coordinate frame origin.
        from .node_types import SocketType
        root_child_name = ""
        for cid in node.children_ids:
            child = manifest.nodes.get(cid)
            if child and child.blender_objects:
                if child.attachment and child.attachment.socket_type == SocketType.ROOT:
                    root_child_name = child.blender_objects[0]
                    break
        
        # Create empty at the ROOT child's position so that parent.world_position
        # (the empty's location) matches what Stage 4 uses as the assembly origin.
        # Using the average of all child positions would offset it from the ROOT
        # child, causing downstream Stage 4 resolvers to compute wrong offsets.
        script = f'''
import bpy
import json
from mathutils import Vector

empty_name = {repr(empty_name)}
child_names = {repr(child_objects)}
root_child_name = {repr(root_child_name)}

# Prefer ROOT child position as the assembly origin; fall back to first child.
origin_obj = bpy.data.objects.get(root_child_name) if root_child_name else None
if not origin_obj:
    origin_obj = next((bpy.data.objects.get(n) for n in child_names if bpy.data.objects.get(n)), None)

if not origin_obj:
    result = {{"ok": False, "error": "No child objects found"}}
else:
    origin = origin_obj.location.copy()
    
    empty = bpy.data.objects.new(empty_name, None)
    empty.empty_display_type = \'PLAIN_AXES\'
    empty.empty_display_size = 0.5
    empty.location = origin
    bpy.context.collection.objects.link(empty)
    
    # Parent children
    parented = []
    for name in child_names:
        obj = bpy.data.objects.get(name)
        if obj:
            obj.parent = empty
            obj.matrix_parent_inverse = empty.matrix_world.inverted()
            parented.append(name)
    
    # Compute assembly bounding box from world vertices
    all_verts = []
    for name in child_names:
        obj = bpy.data.objects.get(name)
        if obj and obj.type == \'MESH\':
            for v in obj.data.vertices:
                all_verts.append(obj.matrix_world @ v.co)
    
    if all_verts:
        bbox_min = [min(v[i] for v in all_verts) for i in range(3)]
        bbox_max = [max(v[i] for v in all_verts) for i in range(3)]
    else:
        bbox_min = bbox_max = [0, 0, 0]
    
    result = {{
        "ok": True,
        "empty": empty_name,
        "parented": parented,
        "bbox_min": bbox_min,
        "bbox_max": bbox_max,
    }}

print("SENTINEL_OUTPUT_START" + json.dumps(result) + "SENTINEL_OUTPUT_END")
'''
        try:
            result = await self.mcp_manager.call_locked(
                "blender", "execute_blender_code", {"code": script}
            )
            data = parse_op_output(result.get("output", ""))
            
            if not data.get("ok"):
                return ExecutionResult(
                    ok=False,
                    node_id=node.node_id,
                    error=data.get("error", "Merge failed"),
                )
            
            return ExecutionResult(
                ok=True,
                node_id=node.node_id,
                blender_objects=[empty_name] + child_objects,
                generation_id=self._collection_name,
                bounding_box={
                    "min": data.get("bbox_min", [0, 0, 0]),
                    "max": data.get("bbox_max", [0, 0, 0]),
                },
                steps_executed=1,
            )
            
        except Exception as e:
            return ExecutionResult(
                ok=False,
                node_id=node.node_id,
                error=str(e),
            )
    
    async def cleanup_all(self) -> None:
        """Clean up all created objects and the collection."""
        from core.blender_ops import parse_op_output
        
        script = f'''
import bpy
import json

objects = {repr(self._created_objects)}
coll_name = {repr(self._collection_name)}
removed = []

for obj_name in objects:
    obj = bpy.data.objects.get(obj_name)
    if obj:
        bpy.data.objects.remove(obj, do_unlink=True)
        removed.append(obj_name)

coll = bpy.data.collections.get(coll_name)
if coll:
    bpy.data.collections.remove(coll)

result = {{"ok": True, "removed": removed}}
print("SENTINEL_OUTPUT_START" + json.dumps(result) + "SENTINEL_OUTPUT_END")
'''
        try:
            await self.mcp_manager.call_locked(
                "blender", "execute_blender_code", {"code": script}
            )
        except Exception as e:
            logger.warning(f"Cleanup failed: {e}")
        
        self._created_objects.clear()
        self._collection_created = False


# ---------------------------------------------------------------------------
# Convenience Functions
# ---------------------------------------------------------------------------

async def build_and_verify_node(
    node: "ManifestNode",
    manifest: "BuildManifest",
    mcp_manager: Any,
    task_id: str,
) -> Tuple[ExecutionResult, Optional[VerificationResult]]:
    """Build a node and verify it in one call.
    
    Returns (execution_result, verification_result).
    verification_result is None if build failed.
    """
    executor = BlenderExecutor(mcp_manager, task_id)
    
    exec_result = await executor.build_node(node, manifest)
    if not exec_result.ok:
        return exec_result, None
    
    # Update node with build results
    node.blender_objects = exec_result.blender_objects
    node.bounding_box = exec_result.bounding_box
    
    verify_result = await executor.verify_node(node)
    
    return exec_result, verify_result
