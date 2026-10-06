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
import inspect
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from .manifest import BuildManifest, ManifestNode

logger = logging.getLogger(__name__)

import json as _json

_PAYLOAD_SENTINEL = "___BLENDER_PAYLOAD___"

def _build_script(template: str, payload: dict) -> str:
    """Build a Blender script from a static template and a JSON payload.
    
    All runtime values must be in payload. The template may reference them
    via payload["key"]. The sentinel _PAYLOAD_SENTINEL is replaced with the
    serialized payload. No runtime value is ever directly interpolated.
    """
    serialized = _json.dumps(payload, ensure_ascii=False)
    return template.replace(_PAYLOAD_SENTINEL, repr(serialized))

_BOX_TEMPLATE = '''
import bpy
import bmesh
import json
import mathutils

payload = json.loads(___BLENDER_PAYLOAD___)
name = payload["name"]
size = payload["size"]
matrix_rows = payload["matrix_rows"]
coll_name = payload["collection"]

if name in bpy.data.objects:
    result = {"ok": False, "error": f"Object '{name}' already exists"}
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
    obj.matrix_world = mathutils.Matrix(matrix_rows)
    
    coll = bpy.data.collections.get(coll_name)
    if coll:
        coll.objects.link(obj)
    else:
        bpy.context.collection.objects.link(obj)
    
    result = {"ok": True, "name": obj.name, "location": list(obj.location)}

print("SENTINEL_OUTPUT_START" + json.dumps(result) + "SENTINEL_OUTPUT_END")
'''


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BUILD_COLLECTION_PREFIX = "Sentinel_Build"
DEFAULT_DIMENSION_TOLERANCE_M = 0.01  # 1cm
DEFAULT_GAP_TOLERANCE_M = 0.002  # 2mm
BOOLEAN_OVERSHOOT_M = 0.002  # 2mm — cutter extends past target surface to avoid coplanar faces


class FaultPoint(str, Enum):
    BEFORE_FIRST_FLUSH = "before_first_flush"
    DURING_CLEANUP = "during_cleanup"
    CONNECTION_LOST = "connection_lost"

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

    BUFFERED MODE (default):
        build_node() and merge_assembly() accumulate script fragments into
        self._script_buffer instead of sending individual MCP calls.  Call
        flush() once after the entire build loop completes to send everything
        as ONE atomic Blender script.  This is the fix for the flat-hierarchy
        bug: parenting only works reliably when all objects exist in the same
        Python execution context.

        After flush() the executor queries Blender for every buffered object's
        world position and bbox, then back-fills node.blender_objects /
        node.bounding_box on all pending nodes.

        Operations that MUST remain as live calls (they need objects to already
        exist in Blender):
          - _get_bounding_box()        (boolean depth, post-flush verification)
          - _apply_boolean()           (needs both objects live)
          - verify_node() and helpers  (post-flush queries)
          - cleanup_all()              (teardown)
          - apply_deferred_modifiers() (post-boolean, objects already live)

    Usage:
        executor = BlenderExecutor(mcp_manager, task_id)
        result = await executor.build_node(node, manifest)   # buffers
        ...                                                   # more build_node / merge_assembly
        await executor.flush(manifest)                        # ONE MCP call
        verified = await executor.verify_node(node)          # live query
    """

    def __init__(
        self,
        mcp_manager: Any,
        task_id: str = "",
        dimension_tolerance: float = DEFAULT_DIMENSION_TOLERANCE_M,
        gap_tolerance: float = DEFAULT_GAP_TOLERANCE_M,
        use_llm_modifiers: bool = True,
        preserve_scene: bool = False,
        fault_injector: Optional[Any] = None,
    ):
        self.mcp_manager = mcp_manager
        self.task_id = task_id
        self.dimension_tolerance = dimension_tolerance
        self.gap_tolerance = gap_tolerance
        self.use_llm_modifiers = bool(use_llm_modifiers)
        self.preserve_scene = bool(preserve_scene)
        self.fault_injector = fault_injector

        import hashlib
        task_hash = hashlib.sha256(task_id.encode()).hexdigest()[:12] if task_id else "default"
        # A task may be retried while an older attempt is still visible.  The
        # attempt suffix prevents Blender name reuse from binding a new plan to
        # stale objects and makes rollback precisely scoped.
        self._attempt_id = uuid.uuid4().hex[:10]
        self._collection_name = f"{BUILD_COLLECTION_PREFIX}_{task_hash}_{self._attempt_id}"
        self._collection_created = False

        # Track created objects for cleanup
        self._created_objects: List[str] = []

        # ── Buffered-build state ──────────────────────────────────────────
        # Each entry is a self-contained block of Blender Python (no imports,
        # no SENTINEL print — those are added by flush()).
        self._script_buffer: List[str] = []
        # Maps obj_name -> ManifestNode so flush() can back-fill results.
        self._pending_nodes: Dict[str, "ManifestNode"] = {}
        # Tracks which nodes are waiting for bbox after flush.
        self._pending_bbox_nodes: List["ManifestNode"] = []
    
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
        
        # Scale the cutter geometry up slightly so it cleanly punches through
        # the target without leaving coplanar faces or paper-thin walls.
        # We do this by temporarily inflating the geometry spec before creating
        # the primitive, then restoring it.
        CUTTER_SCALE = 1.02  # 2% larger on all axes
        geo = cutter_node.geometry
        _orig_size = list(geo.size) if geo.size else None
        _orig_radius = geo.radius
        _orig_radius2 = geo.radius2
        _orig_depth = geo.depth
        _orig_major = geo.major_radius
        _orig_minor = geo.minor_radius
        if geo.size:
            geo.size = [s * CUTTER_SCALE for s in geo.size]
        if geo.radius is not None:
            geo.radius = geo.radius * CUTTER_SCALE
        if geo.radius2 is not None:
            geo.radius2 = geo.radius2 * CUTTER_SCALE
        if geo.depth is not None:
            # Depth must pierce fully through the target — use target's bbox
            # thickness along the cut axis plus overshoot on both sides.
            target_bbox = await self._get_bounding_box(target_obj_name)
            if target_bbox:
                target_thickness = max(
                    target_bbox["max"][0] - target_bbox["min"][0],
                    target_bbox["max"][1] - target_bbox["min"][1],
                    target_bbox["max"][2] - target_bbox["min"][2],
                )
                geo.depth = target_thickness + BOOLEAN_OVERSHOOT_M * 4
            else:
                geo.depth = geo.depth * CUTTER_SCALE
        if geo.major_radius is not None:
            geo.major_radius = geo.major_radius * CUTTER_SCALE
        
        try:
            # Compute cutter position (centered on target, or use attachment offset)
            cutter_pos, matrix_rows = self._compute_world_transform(cutter_node, manifest)
            
            # Create cutter geometry
            create_result = await self._create_primitive(
                node=cutter_node,
                obj_name=cutter_name,
                world_pos=cutter_pos,
                matrix_rows=matrix_rows,
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
            
            # Restore original geometry spec (cutter inflation is temporary)
            if _orig_size is not None:
                geo.size = _orig_size
            geo.radius = _orig_radius
            geo.radius2 = _orig_radius2
            geo.depth = _orig_depth
            geo.major_radius = _orig_major
            geo.minor_radius = _orig_minor

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
            # Restore geometry spec even on failure
            if geo.size is not None and _orig_size is not None:
                geo.size = _orig_size
            geo.radius = _orig_radius
            geo.radius2 = _orig_radius2
            geo.depth = _orig_depth
            geo.major_radius = _orig_major
            geo.minor_radius = _orig_minor
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
        """Buffer a node's geometry creation for atomic flush later.

        Does NOT send any MCP call.  The script fragment is appended to
        self._script_buffer.  Call flush(manifest) after the build loop
        to send everything in one shot.

        Bounding box is estimated from the geometry spec (no Blender query
        needed) and stored on the node immediately so Stage 4 cross-reference
        sockets can use it.  flush() overwrites it with the real Blender bbox.
        """
        from .node_types import NodeKind, PrimitiveType
        from .materials import get_material_for_description, get_material_preset
        from .modifiers import get_modifiers_for_style
        from .manifest import MaterialSpec

        if not node.geometry:
            return ExecutionResult(
                ok=False, node_id=node.node_id, error="Node has no geometry spec"
            )

        obj_name = f"{node.label}_{uuid.uuid4().hex[:6]}"

        try:
            world_pos, matrix_rows = self._compute_world_transform(node, manifest)

            # ── Buffer the primitive creation fragment ───────────────────────────
            prim_fragment = self._get_primitive_fragment(
                node.geometry.primitive, obj_name, node.geometry,
                world_pos, matrix_rows, self._collection_name,
            )
            self._script_buffer.append(prim_fragment)
            from .scene_ir import canonical_node_path
            self._script_buffer.append(self._identity_fragment(
                obj_name,
                node.node_id,
                canonical_node_path(manifest, node.node_id),
                [m.to_dict() if hasattr(m, "to_dict") else m for m in (node.modifiers or [])],
            ))
            self._created_objects.append(obj_name)
            self._pending_nodes[obj_name] = node

            if not defer_modifiers:
                # ── Buffer modifiers ───────────────────────────────────────────────
                modifiers = node.modifiers
                if (
                    not modifiers and self.use_llm_modifiers
                    and not node.stage_outputs.get("_modifiers_resolved")
                ):
                    decomp_hint = node.stage_outputs.get("decomposition_hint", {})
                    style_hint = decomp_hint.get("style_hint", "")
                    if style_hint:
                        modifiers = get_modifiers_for_style(style_hint)
                if modifiers:
                    mod_dicts = [m.to_dict() if hasattr(m, "to_dict") else m for m in modifiers]
                    self._script_buffer.append(self._modifiers_fragment(obj_name, mod_dicts))

                # ── Buffer mesh cleanup ───────────────────────────────────────────
                self._script_buffer.append(self._cleanup_fragment(obj_name))

                # ── Buffer material ───────────────────────────────────────────────
                material = node.material
                if not material:
                    decomp_hint = node.stage_outputs.get("decomposition_hint", {})
                    material_hint = decomp_hint.get("material_hint", "")
                    if material_hint:
                        preset = get_material_for_description(material_hint)
                        if preset:
                            material = MaterialSpec.from_preset(preset.name)
                    if not material:
                        preset = get_material_for_description(node.label)
                        if preset:
                            material = MaterialSpec.from_preset(preset.name)
                if material:
                    self._script_buffer.append(self._material_fragment(obj_name, material))
            else:
                node.stage_outputs["_pending_modifiers"] = True

            # Estimate bbox from geometry spec (no Blender call needed yet).
            # flush() will overwrite with the real measured bbox.
            bbox = self._estimate_bbox(node.geometry, world_pos)

            node.world_position = world_pos
            node.world_rotation = (
                list(node.transform_state.world_matrix.rotation)
                if node.transform_state and node.transform_state.world_matrix
                else [0.0, 0.0, 0.0]
            )
            self._pending_bbox_nodes.append(node)

            return ExecutionResult(
                ok=True,
                node_id=node.node_id,
                blender_objects=[obj_name],
                generation_id=self._collection_name,
                bounding_box=bbox,
                steps_executed=1,
            )

        except Exception as e:
            logger.exception(f"[{self.task_id}] Buffer failed for {node.label}: {e}")
            return ExecutionResult(
                ok=False, node_id=node.node_id, error=str(e), rolled_back=True
            )

    async def build_instance(
        self,
        node: "ManifestNode",
        definition_node: "ManifestNode",
        manifest: "BuildManifest",
    ) -> ExecutionResult:
        """Buffer a linked mesh instance with its own stable transform/identity."""
        if not definition_node.blender_objects:
            return ExecutionResult(False, node.node_id, error="Definition has no Blender object")
        source_name = definition_node.blender_objects[0]
        obj_name = f"{node.label}_{uuid.uuid4().hex[:6]}"
        try:
            _, matrix_rows = self._compute_world_transform(node, manifest)
            self._script_buffer.append(
                f"_src=bpy.data.objects.get({source_name!r})\n"
                f"if not _src: raise RuntimeError('Instance definition object missing: {source_name}')\n"
                f"_obj=_src.copy(); _obj.data=_src.data; _obj.name={obj_name!r}\n"
                f"_obj.matrix_world=mathutils.Matrix({matrix_rows!r}); _obj.hide_render=False; _obj.hide_viewport=False; _link(_obj)\n"
                f"_sentinel_results[{obj_name!r}]=list(_obj.matrix_world.translation)\n"
            )
            from .scene_ir import canonical_node_path
            self._script_buffer.append(self._identity_fragment(
                obj_name, node.node_id, canonical_node_path(manifest, node.node_id), [],
            ))
            self._created_objects.append(obj_name)
            self._pending_nodes[obj_name] = node
            self._pending_bbox_nodes.append(node)
            world_position = list(node.transform_state.world_matrix.position)
            bbox = self._estimate_bbox(definition_node.geometry, world_position)
            return ExecutionResult(
                True, node.node_id, blender_objects=[obj_name],
                generation_id=self._collection_name, bounding_box=bbox, steps_executed=1,
            )
        except Exception as exc:
            return ExecutionResult(False, node.node_id, error=str(exc), rolled_back=True)

    # ──────────────────────────────────────────────────────────────────────
    # Flush — send the entire buffered build as ONE atomic MCP call
    # ──────────────────────────────────────────────────────────────────────

    async def flush(self, manifest: "BuildManifest") -> bool:
        """Send all buffered fragments as one atomic Blender script.

        Returns True if the script executed without error.
        Back-fills node.bounding_box for every pending node using a
        post-flush bbox query.
        """
        from core.blender_ops import parse_op_output

        if not self._script_buffer:
            logger.debug(f"[{self.task_id}] flush(): buffer empty, nothing to send")
            return True

        await self._inject_fault(FaultPoint.BEFORE_FIRST_FLUSH)

        # ── Assemble the full script ─────────────────────────────────────────────
        header = (
            "import bpy, bmesh, json, math, mathutils\n"
            f"_coll_name = {repr(self._collection_name)}\n"
            "if _coll_name not in bpy.data.collections:\n"
            "    _c = bpy.data.collections.new(_coll_name)\n"
            "    bpy.context.scene.collection.children.link(_c)\n"
            "_coll = bpy.data.collections.get(_coll_name)\n"
            f"if _coll: _coll['sentinel_build_id'] = {self._collection_name!r}\n"
            f"if _coll: _coll['sentinel_attempt_id'] = {self._attempt_id!r}\n"
            "def _link(obj):\n"
            "    if _coll: _coll.objects.link(obj)\n"
            "    else: bpy.context.scene.collection.objects.link(obj)\n"
            "def _unlink_all(obj):\n"
            "    for c in list(obj.users_collection): c.objects.unlink(obj)\n"
            "_sentinel_results = {}\n"
        )

        footer = (
            "\nprint('SENTINEL_OUTPUT_START' + json.dumps({'ok': True, 'results': _sentinel_results}) + 'SENTINEL_OUTPUT_END')\n"
        )

        full_script = header + "\n".join(self._script_buffer) + footer

        logger.info(
            f"[{self.task_id}] flush(): sending {len(self._script_buffer)} fragments, "
            f"{len(self._created_objects)} objects in ONE MCP call"
        )

        try:
            result = await self.mcp_manager.call_locked(
                "blender", "execute_blender_code", {"code": full_script}
            )
            data = parse_op_output(result.get("output", ""))
        except Exception as e:
            logger.error(f"[{self.task_id}] flush() MCP call failed: {e}")
            # A transaction can have created some objects before Blender raised.
            # Remove only this task's collection before reporting failure.
            if not self.preserve_scene:
                await self.cleanup_all()
            self._script_buffer.clear()
            self._pending_bbox_nodes.clear()
            self._pending_nodes.clear()
            self._created_objects.clear()
            return False

        if not data.get("ok"):
            logger.error(f"[{self.task_id}] flush() script error: {data}")
            if not self.preserve_scene:
                await self.cleanup_all()
            self._script_buffer.clear()
            self._pending_bbox_nodes.clear()
            self._pending_nodes.clear()
            self._created_objects.clear()
            return False

        self._collection_created = True
        self._script_buffer.clear()

        # ── Back-fill real bboxes for all pending nodes ──────────────────────────
        if self._pending_bbox_nodes:
            obj_names = [
                n.blender_objects[0]
                for n in self._pending_bbox_nodes
                if n.blender_objects
            ]
            if obj_names:
                bbox_script = (
                    "import bpy, json\n"
                    f"_names = {repr(obj_names)}\n"
                    "_bboxes = {}\n"
                    "for _n in _names:\n"
                    "    _o = bpy.data.objects.get(_n)\n"
                    "    if _o and _o.type == 'MESH':\n"
                    "        _verts = [_o.matrix_world @ v.co for v in _o.data.vertices]\n"
                    "        if _verts:\n"
                    "            _bboxes[_n] = {'min': [min(v[i] for v in _verts) for i in range(3)],\n"
                    "                           'max': [max(v[i] for v in _verts) for i in range(3)]}\n"
                    "print('SENTINEL_OUTPUT_START' + json.dumps({'ok': True, 'bboxes': _bboxes}) + 'SENTINEL_OUTPUT_END')\n"
                )
                try:
                    bbox_result = await self.mcp_manager.call_locked(
                        "blender", "execute_blender_code", {"code": bbox_script}
                    )
                    bbox_data = parse_op_output(bbox_result.get("output", ""))
                    bboxes = bbox_data.get("bboxes", {})
                    for node in self._pending_bbox_nodes:
                        if node.blender_objects:
                            bb = bboxes.get(node.blender_objects[0])
                            if bb:
                                node.bounding_box = bb
                except Exception as e:
                    logger.warning(f"[{self.task_id}] flush() bbox back-fill failed: {e}")

        self._pending_bbox_nodes.clear()
        self._pending_nodes.clear()
        logger.info(f"[{self.task_id}] flush(): complete")
        return True


    
    def _compute_world_transform(
        self,
        node: "ManifestNode",
        manifest: "BuildManifest",
    ) -> Tuple[List[float], List[List[float]]]:
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
                    # Serialize the full 4x4 matrix as rows — no Euler anywhere.
                    # repr() round-trips Python floats exactly (unlike str()).
                    matrix_rows = [list(row) for row in world_matrix.matrix]
                    world_pos = list(world_matrix.position)
                    
                    logger.info(
                        f"[{self.task_id}] {node.label} using hierarchical transform: "
                        f"pos={[round(p, 4) for p in world_pos]}"
                    )
                    
                    return world_pos, matrix_rows
            
            # Fallback: transform_state not populated — this is a bug
            raise RuntimeError(
                f"{node.label} has no transform_state.world_matrix. "
                f"Stage 4 must populate world_matrix before executor runs."
            )
        
        raise RuntimeError(f"{node.label} has no transform_state")
    
    # Dispatch table: PrimitiveType -> callable(self, obj_name, geo, world_pos, matrix_rows, collection_name) -> str
    # Add new primitives here without touching _create_primitive.
    def _get_primitive_script(self, prim: Any, obj_name: str, geo: Any, world_pos: List[float], matrix_rows: List[List[float]], collection_name: str) -> str:
        from .node_types import PrimitiveType
        dispatch = {
            PrimitiveType.BOX:        lambda: self._box_script(obj_name, geo.size or [1, 1, 1], world_pos, matrix_rows, collection_name),
            PrimitiveType.CYLINDER:   lambda: self._cylinder_script(obj_name, geo.radius or 0.5, geo.depth or 1.0, geo.segments or 32, world_pos, matrix_rows, collection_name),
            PrimitiveType.SPHERE:     lambda: self._sphere_script(obj_name, geo.radius or 0.5, world_pos, matrix_rows, collection_name),
            PrimitiveType.CONE:       lambda: self._cone_script(obj_name, geo.radius or 0.5, geo.depth or 1.0, world_pos, matrix_rows, collection_name, radius2=getattr(geo, "radius2", 0.0) or 0.0),
            PrimitiveType.HEMISPHERE: lambda: self._hemisphere_script(obj_name, geo.radius or 0.5, world_pos, matrix_rows, collection_name),
            PrimitiveType.CAPSULE:    lambda: self._capsule_script(obj_name, geo.radius or 0.5, geo.depth or 1.0, world_pos, matrix_rows, collection_name),
            PrimitiveType.TORUS:      lambda: self._torus_script(obj_name, geo.major_radius or 1.0, geo.minor_radius or 0.25, world_pos, matrix_rows, collection_name),
            PrimitiveType.U_SHAPE:    lambda: self._u_shape_script(obj_name, geo.major_radius or 0.5, geo.minor_radius or 0.05, world_pos, matrix_rows, collection_name),
        }
        builder = dispatch.get(prim)
        if builder:
            return builder()
        raise ValueError(f"Unsupported primitive for live executor: {getattr(prim, 'value', prim)}")

    def _get_primitive_fragment(
        self,
        prim: Any,
        obj_name: str,
        geo: Any,
        world_pos: List[float],
        matrix_rows: List[List[float]],
        collection_name: str,
    ) -> str:
        """Return a script fragment (no imports, no SENTINEL print) for buffered mode.

        Uses _link/_unlink_all and mathutils injected by flush() header.
        Records the object world position in _sentinel_results.
        """
        from .node_types import PrimitiveType
        name = repr(obj_name)
        mr   = repr(matrix_rows)

        if prim == PrimitiveType.BOX:
            s = geo.size or [1, 1, 1]
            return (
                f"if {name} not in bpy.data.objects:\n"
                f"    _mesh = bpy.data.meshes.new({name})\n"
                f"    _bm = bmesh.new()\n"
                f"    bmesh.ops.create_cube(_bm, size=1.0)\n"
                f"    for _v in _bm.verts: _v.co.x*={s[0]}; _v.co.y*={s[1]}; _v.co.z*={s[2]}\n"
                f"    _bm.to_mesh(_mesh); _bm.free()\n"
                f"    _obj = bpy.data.objects.new({name}, _mesh)\n"
                f"    _obj.matrix_world = mathutils.Matrix({mr})\n"
                f"    _link(_obj)\n"
                f"    _sentinel_results[{name}] = list(_obj.matrix_world.translation)\n"
            )
        elif prim == PrimitiveType.CYLINDER:
            r, d, seg = geo.radius or 0.5, geo.depth or 1.0, geo.segments or 32
            return (
                f"if {name} not in bpy.data.objects:\n"
                f"    bpy.ops.mesh.primitive_cylinder_add(radius={r}, depth={d}, vertices={seg})\n"
                f"    _obj = bpy.context.active_object\n"
                f"    _obj.name = {name}; _obj.data.name = {name}\n"
                f"    _obj.data.polygons.foreach_set('use_smooth', [True] * len(_obj.data.polygons))\n"
                f"    try:\n"
                f"        bpy.context.view_layer.objects.active = _obj\n"
                f"        bpy.ops.object.shade_smooth_by_angle(angle=0.523599)\n"
                f"    except Exception:\n"
                f"        pass\n"
                f"    _obj.matrix_world = mathutils.Matrix({mr})\n"
                f"    _unlink_all(_obj); _link(_obj)\n"
                f"    _sentinel_results[{name}] = list(_obj.matrix_world.translation)\n"
            )
        elif prim == PrimitiveType.SPHERE:
            r = geo.radius or 0.5
            seg = geo.segments or 32
            rings = geo.rings or 16
            return (
                f"if {name} not in bpy.data.objects:\n"
                f"    bpy.ops.mesh.primitive_uv_sphere_add(segments={seg}, ring_count={rings}, radius={r})\n"
                f"    _obj = bpy.context.active_object\n"
                f"    _obj.name = {name}; _obj.data.name = {name}\n"
                f"    _obj.data.polygons.foreach_set('use_smooth', [True] * len(_obj.data.polygons))\n"
                f"    _obj.matrix_world = mathutils.Matrix({mr})\n"
                f"    _unlink_all(_obj); _link(_obj)\n"
                f"    _sentinel_results[{name}] = list(_obj.matrix_world.translation)\n"
            )
        elif prim == PrimitiveType.CONE:
            r1 = geo.radius if geo.radius is not None else 0.5
            r2 = getattr(geo, "radius2", None)
            if r2 is None:
                r2 = 0.0
            d = geo.depth if geo.depth is not None else 1.0
            seg = geo.segments or 32
            return (
                f"if {name} not in bpy.data.objects:\n"
                f"    bpy.ops.mesh.primitive_cone_add(vertices={seg}, radius1={r1}, radius2={r2}, depth={d})\n"
                f"    _obj = bpy.context.active_object\n"
                f"    _obj.name = {name}; _obj.data.name = {name}\n"
                f"    _obj.data.polygons.foreach_set('use_smooth', [True] * len(_obj.data.polygons))\n"
                f"    try:\n"
                f"        bpy.context.view_layer.objects.active = _obj\n"
                f"        bpy.ops.object.shade_smooth_by_angle(angle=0.523599)\n"
                f"    except Exception:\n"
                f"        pass\n"
                f"    _obj.matrix_world = mathutils.Matrix({mr})\n"
                f"    _unlink_all(_obj); _link(_obj)\n"
                f"    _sentinel_results[{name}] = list(_obj.matrix_world.translation)\n"
            )
        elif prim == PrimitiveType.HEMISPHERE:
            r = geo.radius or 0.5
            seg = geo.segments or 32
            rings = geo.rings or 16
            return (
                f"if {name} not in bpy.data.objects:\n"
                f"    bpy.ops.mesh.primitive_uv_sphere_add(segments={seg}, ring_count={rings}, radius={r})\n"
                f"    _obj = bpy.context.active_object\n"
                f"    _obj.name = {name}; _obj.data.name = {name}\n"
                f"    _bm2 = bmesh.new(); _bm2.from_mesh(_obj.data)\n"
                f"    _geom2 = _bm2.verts[:]+_bm2.edges[:]+_bm2.faces[:]\n"
                f"    bmesh.ops.bisect_plane(_bm2,geom=_geom2,plane_co=(0,0,0),plane_no=(0,0,1),clear_inner=True,clear_outer=False)\n"
                f"    bmesh.ops.remove_doubles(_bm2,verts=_bm2.verts,dist=0.0001)\n"
                f"    _bnd=[e for e in _bm2.edges if len(e.link_faces)==1]\n"
                f"    if _bnd: bmesh.ops.edgeloop_fill(_bm2,edges=_bnd)\n"
                f"    _mz2 = min(v.co.z for v in _bm2.verts)\n"
                f"    if abs(_mz2) > 1e-6: bmesh.ops.translate(_bm2, vec=mathutils.Vector((0,0,-_mz2)), verts=_bm2.verts)\n"
                f"    _bm2.to_mesh(_obj.data); _bm2.free(); _obj.data.update()\n"
                f"    _obj.data.polygons.foreach_set('use_smooth', [True] * len(_obj.data.polygons))\n"
                f"    try:\n"
                f"        bpy.context.view_layer.objects.active = _obj\n"
                f"        bpy.ops.object.shade_smooth_by_angle(angle=0.523599)\n"
                f"    except Exception:\n"
                f"        pass\n"
                f"    _obj.matrix_world = mathutils.Matrix({mr})\n"
                f"    _unlink_all(_obj); _link(_obj)\n"
                f"    _sentinel_results[{name}] = list(_obj.matrix_world.translation)\n"
            )
        elif prim == PrimitiveType.CAPSULE:
            radius, depth, seg = geo.radius or 0.5, geo.depth or 1.0, geo.segments or 32
            cylinder_depth = max(0.0, depth - 2.0 * radius)
            return (
                f"if {name} not in bpy.data.objects:\n"
                f"    _caps = []\n"
                f"    if {cylinder_depth} > 0:\n"
                f"        _bm_c = bmesh.new(); bmesh.ops.create_cone(_bm_c, cap_ends=False, segments={seg}, radius1={radius}, radius2={radius}, depth={cylinder_depth})\n"
                f"        _m_c = bpy.data.meshes.new('caps_c'); _bm_c.to_mesh(_m_c); _bm_c.free()\n"
                f"        _o_c = bpy.data.objects.new('caps_c', _m_c); bpy.context.scene.collection.objects.link(_o_c); _caps.append(_o_c)\n"
                f"    _bm_t = bmesh.new(); bmesh.ops.create_uvsphere(_bm_t, u_segments={seg}, v_segments=max(8, {seg}//2), radius={radius})\n"
                f"    bmesh.ops.bisect_plane(_bm_t, geom=_bm_t.verts[:]+_bm_t.edges[:]+_bm_t.faces[:], plane_co=(0,0,0), plane_no=(0,0,1), clear_inner=True, clear_outer=False)\n"
                f"    bmesh.ops.translate(_bm_t, vec=(0,0,{cylinder_depth}/2), verts=_bm_t.verts)\n"
                f"    _m_t = bpy.data.meshes.new('caps_t'); _bm_t.to_mesh(_m_t); _bm_t.free()\n"
                f"    _o_t = bpy.data.objects.new('caps_t', _m_t); bpy.context.scene.collection.objects.link(_o_t); _caps.append(_o_t)\n"
                f"    _bm_b = bmesh.new(); bmesh.ops.create_uvsphere(_bm_b, u_segments={seg}, v_segments=max(8, {seg}//2), radius={radius})\n"
                f"    bmesh.ops.bisect_plane(_bm_b, geom=_bm_b.verts[:]+_bm_b.edges[:]+_bm_b.faces[:], plane_co=(0,0,0), plane_no=(0,0,-1), clear_inner=True, clear_outer=False)\n"
                f"    bmesh.ops.translate(_bm_b, vec=(0,0,-{cylinder_depth}/2), verts=_bm_b.verts)\n"
                f"    _m_b = bpy.data.meshes.new('caps_b'); _bm_b.to_mesh(_m_b); _bm_b.free()\n"
                f"    _o_b = bpy.data.objects.new('caps_b', _m_b); bpy.context.scene.collection.objects.link(_o_b); _caps.append(_o_b)\n"
                f"    bpy.ops.object.select_all(action='DESELECT')\n"
                f"    for _p in _caps: _p.select_set(True)\n"
                f"    bpy.context.view_layer.objects.active = _caps[0]; bpy.ops.object.join(); _obj = bpy.context.active_object\n"
                f"    _merge_d = max(1e-6, min(0.0005, {radius} * 0.01))\n"
                f"    _bm_f = bmesh.new(); _bm_f.from_mesh(_obj.data); bmesh.ops.remove_doubles(_bm_f, verts=_bm_f.verts, dist=_merge_d); _bm_f.to_mesh(_obj.data); _bm_f.free()\n"
                f"    _obj.data.polygons.foreach_set('use_smooth', [True] * len(_obj.data.polygons))\n"
                f"    _obj.name = {name}; _obj.data.name = {name}; _obj.matrix_world = mathutils.Matrix({mr}); _unlink_all(_obj); _link(_obj)\n"
                f"    _sentinel_results[{name}] = list(_obj.matrix_world.translation)\n"
            )
        elif prim == PrimitiveType.TORUS:
            maj, mn = geo.major_radius or 1.0, geo.minor_radius or 0.25
            maj_seg = geo.segments or 32
            min_seg = geo.rings or 16
            return (
                f"if {name} not in bpy.data.objects:\n"
                f"    bpy.ops.mesh.primitive_torus_add(major_radius={maj}, minor_radius={mn}, major_segments={maj_seg}, minor_segments={min_seg})\n"
                f"    _obj = bpy.context.active_object\n"
                f"    _obj.name = {name}; _obj.data.name = {name}\n"
                f"    _obj.data.polygons.foreach_set('use_smooth', [True] * len(_obj.data.polygons))\n"
                f"    _obj.matrix_world = mathutils.Matrix({mr})\n"
                f"    _unlink_all(_obj); _link(_obj)\n"
                f"    _sentinel_results[{name}] = list(_obj.matrix_world.translation)\n"
            )
        elif prim == PrimitiveType.U_SHAPE:
            maj, mn = geo.major_radius or 0.5, geo.minor_radius or 0.05
            return (
                f"if {name} not in bpy.data.objects:\n"
                f"    bpy.ops.mesh.primitive_torus_add(major_radius={maj},minor_radius={mn},major_segments=48,minor_segments=16,location=(0,0,0),rotation=(0,0,0))\n"
                f"    _obj = bpy.context.active_object\n"
                f"    _obj.name = {name}; _obj.data.name = {name}\n"
                f"    _bm3=bmesh.new(); _bm3.from_mesh(_obj.data)\n"
                f"    _g3=_bm3.verts[:]+_bm3.edges[:]+_bm3.faces[:]\n"
                f"    bmesh.ops.bisect_plane(_bm3,geom=_g3,plane_co=(0,0,0),plane_no=(1,0,0),clear_inner=True,clear_outer=False)\n"
                f"    bmesh.ops.remove_doubles(_bm3,verts=_bm3.verts,dist=0.0001)\n"
                f"    _bnd3=[e for e in _bm3.edges if len(e.link_faces)==1]\n"
                f"    if _bnd3: bmesh.ops.edgeloop_fill(_bm3,edges=_bnd3)\n"
                f"    _rz=mathutils.Matrix.Rotation(1.5707963267948966,4,'Z'); _rx=mathutils.Matrix.Rotation(1.5707963267948966,4,'X')\n"
                f"    bmesh.ops.transform(_bm3,matrix=_rx@_rz,verts=_bm3.verts)\n"
                f"    _mz3=min(v.co.z for v in _bm3.verts)\n"
                f"    bmesh.ops.translate(_bm3,vec=mathutils.Vector((0,0,-_mz3)),verts=_bm3.verts)\n"
                f"    _bm3.to_mesh(_obj.data); _bm3.free(); _obj.data.update()\n"
                f"    _obj.data.polygons.foreach_set('use_smooth', [True] * len(_obj.data.polygons))\n"
                f"    try:\n"
                f"        bpy.context.view_layer.objects.active = _obj\n"
                f"        bpy.ops.object.shade_smooth_by_angle(angle=0.523599)\n"
                f"    except Exception:\n"
                f"        pass\n"
                f"    _obj.matrix_world = mathutils.Matrix({mr})\n"
                f"    _unlink_all(_obj); _link(_obj)\n"
                f"    _sentinel_results[{name}] = list(_obj.matrix_world.translation)\n"
            )
        elif prim == PrimitiveType.PLANE:
            # A planning plane is an explicit thin panel, not a zero-thickness
            # surface.  GeometrySpec normalizes [x, y] to [x, y, thickness].
            size = geo.size or [1.0, 1.0, 0.002]
            return (
                f"if {name} not in bpy.data.objects:\n"
                f"    _mesh = bpy.data.meshes.new({name})\n"
                f"    _bm = bmesh.new(); bmesh.ops.create_cube(_bm, size=1.0)\n"
                f"    for _v in _bm.verts: _v.co.x*={size[0]}; _v.co.y*={size[1]}; _v.co.z*={size[2]}\n"
                f"    _bm.to_mesh(_mesh); _bm.free()\n"
                f"    _obj=bpy.data.objects.new({name},_mesh); _obj.matrix_world=mathutils.Matrix({mr}); _link(_obj)\n"
                f"    _sentinel_results[{name}]=list(_obj.matrix_world.translation)\n"
            )
        elif prim == PrimitiveType.CIRCLE:
            radius, seg = geo.radius or 0.5, geo.segments or 32
            return self._operator_fragment(name, mr, f"bpy.ops.mesh.primitive_circle_add(vertices={seg}, radius={radius}, fill_type='NGON')")
        elif prim == PrimitiveType.GRID:
            size = geo.size or [1.0, 1.0, 0.0]
            seg = max(2, geo.segments or 10)
            return (
                f"if {name} not in bpy.data.objects:\n"
                f"    _mesh=bpy.data.meshes.new({name}); _bm=bmesh.new()\n"
                f"    bmesh.ops.create_grid(_bm, x_segments={seg}, y_segments={seg}, size=0.5)\n"
                f"    for _v in _bm.verts: _v.co.x*={size[0]}; _v.co.y*={size[1]}\n"
                f"    _bm.to_mesh(_mesh); _bm.free()\n"
                f"    _obj=bpy.data.objects.new({name},_mesh); _obj.matrix_world=mathutils.Matrix({mr}); _link(_obj)\n"
                f"    _sentinel_results[{name}]=list(_obj.matrix_world.translation)\n"
            )
        elif prim == PrimitiveType.MONKEY:
            return self._operator_fragment(name, mr, "bpy.ops.mesh.primitive_monkey_add()")
        elif prim in (PrimitiveType.PYRAMID, PrimitiveType.PRISM):
            radius, depth = geo.radius or 0.5, geo.depth or 1.0
            vertices = 4 if prim == PrimitiveType.PYRAMID else max(3, geo.segments or 6)
            top_radius = 0.0 if prim == PrimitiveType.PYRAMID else radius
            return self._operator_fragment(name, mr, f"bpy.ops.mesh.primitive_cone_add(vertices={vertices}, radius1={radius}, radius2={top_radius}, depth={depth})")
        elif prim == PrimitiveType.WEDGE:
            size = geo.size or [1.0, 1.0, 1.0]
            verts = [[-size[0]/2,-size[1]/2,-size[2]/2],[size[0]/2,-size[1]/2,-size[2]/2],[size[0]/2,size[1]/2,-size[2]/2],[-size[0]/2,size[1]/2,-size[2]/2],[-size[0]/2,-size[1]/2,size[2]/2],[-size[0]/2,size[1]/2,size[2]/2]]
            faces = [[0,1,2,3],[0,4,5,3],[0,1,4],[1,2,5,4],[2,3,5]]
            return (
                f"if {name} not in bpy.data.objects:\n"
                f"    _mesh=bpy.data.meshes.new({name}); _mesh.from_pydata({verts!r},[],{faces!r}); _mesh.update()\n"
                f"    _obj=bpy.data.objects.new({name},_mesh); _obj.matrix_world=mathutils.Matrix({mr}); _link(_obj)\n"
                f"    _sentinel_results[{name}]=list(_obj.matrix_world.translation)\n"
            )
        raise ValueError(f"Unsupported transaction primitive: {getattr(prim, 'value', prim)}")

    @staticmethod
    def _operator_fragment(name: str, matrix_rows: str, operator: str) -> str:
        """Wrap a native Blender primitive operator for buffered execution."""
        return (
            f"if {name} not in bpy.data.objects:\n"
            f"    {operator}\n"
            f"    _obj=bpy.context.active_object; _obj.name={name}; _obj.data.name={name}\n"
            f"    _obj.matrix_world=mathutils.Matrix({matrix_rows}); _unlink_all(_obj); _link(_obj)\n"
            f"    _sentinel_results[{name}]=list(_obj.matrix_world.translation)\n"
        )

    def _modifiers_fragment(self, obj_name: str, mod_list: List[Dict]) -> str:
        """Compile every modifier supported by the active transaction registry.

        This intentionally fails the transaction for a Blender-side modifier
        error.  Silently skipping a declared modifier produces a scene whose
        appearance no longer matches its frozen plan.
        """
        return (
            f"_mod_obj = bpy.data.objects.get({repr(obj_name)})\n"
            f"if _mod_obj:\n"
            f"    for _ms in {repr(mod_list)}:\n"
            f"            _mt = _ms.get('type','')\n"
            f"            if _mt == 'bevel':\n"
            f"                _m = _mod_obj.modifiers.new('Sentinel_bevel','BEVEL')\n"
            f"                _dims = [d for d in (_mod_obj.dimensions.x, _mod_obj.dimensions.y, _mod_obj.dimensions.z) if d > 0.0001]\n"
            f"                _min_d = min(_dims) if _dims else 0.1\n"
            f"                _m.width = min(_ms.get('bevel_width',0.02), max(0.0005, _min_d * 0.25))\n"
            f"                _m.segments = _ms.get('bevel_segments',3)\n"
            f"                _m.use_clamp_overlap = True\n"
            f"            elif _mt == 'subdivision':\n"
            f"                _m = _mod_obj.modifiers.new('Sentinel_sub','SUBSURF')\n"
            f"                _m.levels = _ms.get('subdivision_levels',2)\n"
            f"                _m.render_levels = _ms.get('subdivision_render_levels',2)\n"
            f"            elif _mt == 'solidify':\n"
            f"                _m = _mod_obj.modifiers.new('Sentinel_solidify','SOLIDIFY'); _m.thickness = _ms.get('solidify_thickness',0.01); _m.offset = _ms.get('solidify_offset',-1.0)\n"
            f"            elif _mt == 'mirror':\n"
            f"                _m = _mod_obj.modifiers.new('Sentinel_mirror','MIRROR'); _ax = _ms.get('mirror_axis',[True,False,False]); _m.use_axis[0] = bool(_ax[0]) if len(_ax)>0 else True; _m.use_axis[1] = bool(_ax[1]) if len(_ax)>1 else False; _m.use_axis[2] = bool(_ax[2]) if len(_ax)>2 else False\n"
            f"            elif _mt == 'array':\n"
            f"                _m = _mod_obj.modifiers.new('Sentinel_array','ARRAY'); _m.count = _ms.get('array_count',2); _m.use_relative_offset = _ms.get('array_use_relative_offset',True); _of = _ms.get('array_offset',[1,0,0]); _m.relative_offset_displace[0] = float(_of[0]) if len(_of)>0 else 1.0; _m.relative_offset_displace[1] = float(_of[1]) if len(_of)>1 else 0.0; _m.relative_offset_displace[2] = float(_of[2]) if len(_of)>2 else 0.0\n"
            f"            elif _mt == 'simple_deform':\n"
            f"                _m = _mod_obj.modifiers.new('Sentinel_deform','SIMPLE_DEFORM'); _m.deform_method = _ms.get('deform_method','BEND'); _m.angle = _ms.get('deform_angle',0.0); _m.factor = _ms.get('deform_factor',0.0); _m.deform_axis = _ms.get('deform_axis','X')\n"
            f"            elif _mt == 'weighted_normal':\n"
            f"                _m = _mod_obj.modifiers.new('Sentinel_weighted_normal','WEIGHTED_NORMAL'); _m.weight = _ms.get('weighted_normal_weight',50); _m.keep_sharp = _ms.get('weighted_normal_keep_sharp',True)\n"
            f"            elif _mt == 'smooth':\n"
            f"                _m = _mod_obj.modifiers.new('Sentinel_smooth','SMOOTH'); _m.factor = _ms.get('smooth_factor',0.5); _m.iterations = _ms.get('smooth_iterations',1)\n"
            f"            elif _mt == 'edge_split':\n"
            f"                _m = _mod_obj.modifiers.new('Sentinel_edge_split','EDGE_SPLIT'); _m.split_angle = math.radians(_ms.get('edge_split_angle',30.0))\n"
            f"            elif _mt == 'triangulate':\n"
            f"                _m = _mod_obj.modifiers.new('Sentinel_triangulate','TRIANGULATE')\n"
            f"            elif _mt == 'decimate':\n"
            f"                _m = _mod_obj.modifiers.new('Sentinel_decimate','DECIMATE'); _m.ratio = _ms.get('decimate_ratio',0.5); _m.decimate_type = _ms.get('decimate_type','COLLAPSE')\n"
            f"            else:\n"
            f"                raise RuntimeError('Unsupported transaction modifier: ' + str(_mt))\n"
            f"            if _ms.get('apply', False):\n"
            f"                bpy.context.view_layer.objects.active = _mod_obj; bpy.ops.object.modifier_apply(modifier=_m.name)\n"
        )

    def _cleanup_fragment(self, obj_name: str) -> str:
        """Fragment that removes doubles and recalculates normals."""
        return (
            f"_cl_obj = bpy.data.objects.get({repr(obj_name)})\n"
            f"if _cl_obj and _cl_obj.type == 'MESH':\n"
            f"    _cl_bm = bmesh.new(); _cl_bm.from_mesh(_cl_obj.data)\n"
            f"    bmesh.ops.remove_doubles(_cl_bm, verts=_cl_bm.verts, dist=0.0001)\n"
            f"    bmesh.ops.recalc_face_normals(_cl_bm, faces=_cl_bm.faces)\n"
            f"    _cl_bm.to_mesh(_cl_obj.data); _cl_bm.free()\n"
        )

    def _identity_fragment(
        self,
        obj_name: str,
        node_id: str,
        canonical_path: str,
        modifiers: List[Dict[str, Any]],
    ) -> str:
        """Attach stable plan identity and declared operations to an object."""
        return (
            f"_id_obj = bpy.data.objects.get({obj_name!r})\n"
            f"if not _id_obj: raise RuntimeError('Created object missing before identity tagging: {obj_name}')\n"
            f"_id_obj['sentinel_build_id'] = {self._collection_name!r}\n"
            f"_id_obj['sentinel_attempt_id'] = {self._attempt_id!r}\n"
            f"_id_obj['sentinel_node_id'] = {node_id!r}\n"
            f"_id_obj['sentinel_canonical_path'] = {canonical_path!r}\n"
            f"_id_obj['sentinel_declared_modifiers'] = json.dumps({modifiers!r}, sort_keys=True)\n"
            f"if getattr(_id_obj, 'data', None) is not None:\n"
            f"    _id_obj.data['sentinel_build_id'] = {self._collection_name!r}\n"
            f"    _id_obj.data['sentinel_attempt_id'] = {self._attempt_id!r}\n"
        )

    def _material_fragment(self, obj_name: str, material: Any) -> str:
        """Fragment that creates and assigns the full supported Principled PBR spec."""
        import hashlib
        import json
        def rgba(value: Any) -> Optional[List[float]]:
            """Normalize optional RGB/RGBA plan values for Blender colour sockets."""
            if not isinstance(value, (list, tuple)) or len(value) not in {3, 4}:
                return None
            normalized = [float(component) for component in value]
            return normalized + [1.0] if len(normalized) == 3 else normalized

        def linear_rgba(value: Any) -> Optional[List[float]]:
            normalized = rgba(value)
            if normalized is None:
                return None
            def channel(component: float) -> float:
                return component / 12.92 if component <= 0.04045 else ((component + 0.055) / 1.055) ** 2.4
            return [channel(component) for component in normalized[:3]] + [normalized[3]]

        color = linear_rgba(material.base_color) or linear_rgba([0.8, 0.8, 0.8, 1.0])
        def _get_val(attr: str, default: float) -> float:
            val = getattr(material, attr, None)
            return default if val is None else float(val)

        metallic  = _get_val("metallic", 0.0)
        roughness = _get_val("roughness", 0.5)
        emission_color = linear_rgba(getattr(material, "emission_color", None))
        emission_strength = _get_val("emission_strength", 0.0)
        transmission = _get_val("transmission", 0.0)
        ior = _get_val("ior", 1.45)
        subsurface = _get_val("subsurface", 0.0)
        subsurface_color = linear_rgba(getattr(material, "subsurface_color", None))
        subsurface_radius = list(getattr(material, "subsurface_radius", [1.0, 0.2, 0.1]))
        clearcoat = _get_val("clearcoat", 0.0)
        clearcoat_roughness = _get_val("clearcoat_roughness", 0.03)
        sheen = _get_val("sheen", 0.0)
        specular = _get_val("specular", 0.5)
        specular_tint = _get_val("specular_tint", 0.0)
        anisotropy = _get_val("anisotropy", 0.0)
        normal_strength = _get_val("normal_strength", 1.0)
        # Blender 4.x changed Specular Tint from a scalar to an RGBA socket.
        # Preserve the legacy scalar's meaning by blending neutral white toward
        # the base colour, rather than assigning a float to a vector property.
        specular_tint_color = tuple(
            (1.0 - specular_tint) + specular_tint * component
            for component in color[:3]
        ) + (1.0,)
        alpha = getattr(material, "alpha", 1.0)
        procedural_texture = getattr(material, "procedural_texture", None)
        procedural_params = getattr(material, "procedural_params", {}) or {}
        blend_mode = getattr(material, "blend_mode", "opaque")
        material_payload = {
            "base_color": color, "metallic": metallic, "roughness": roughness,
            "emission_color": emission_color, "emission_strength": emission_strength,
            "transmission": transmission, "ior": ior, "subsurface": subsurface,
            "subsurface_color": subsurface_color, "subsurface_radius": subsurface_radius,
            "clearcoat": clearcoat, "clearcoat_roughness": clearcoat_roughness,
            "sheen": sheen, "specular": specular, "specular_tint": specular_tint,
            "anisotropy": anisotropy, "normal_strength": normal_strength,
            "alpha": alpha, "blend_mode": blend_mode,
            "procedural_texture": procedural_texture, "procedural_params": procedural_params,
        }
        material_hash = hashlib.sha256(json.dumps(material_payload, sort_keys=True).encode("utf-8")).hexdigest()[:12]
        mat_name = f"MatPBR_{material_hash}_{self._attempt_id}"
        aniso_lines = (
            f"        if 'Anisotropic IOR Level' in _bsdf.inputs: _bsdf.inputs['Anisotropic IOR Level'].default_value = {anisotropy}\n"
            f"        elif 'Anisotropic' in _bsdf.inputs: _bsdf.inputs['Anisotropic'].default_value = {anisotropy}\n"
        ) if anisotropy > 0 else ""

        procedural_code = ""
        if procedural_texture == "wood":
            scale = procedural_params.get("scale", 16.0)
            distortion = procedural_params.get("distortion", 3.8)
            detail = procedural_params.get("detail", 3.0)
            strength = procedural_params.get("strength", 0.12)
            procedural_code = f"""
        # Procedural Wood Texture Node Graph
        _tex_coord = _mat.node_tree.nodes.new('ShaderNodeTexCoord')
        _mapping = _mat.node_tree.nodes.new('ShaderNodeMapping')
        _wave = _mat.node_tree.nodes.new('ShaderNodeTexWave')
        _ramp = _mat.node_tree.nodes.new('ShaderNodeValToRGB')
        _bump = _mat.node_tree.nodes.new('ShaderNodeBump')
        _wave.wave_type = 'RINGS'
        if 'Scale' in _wave.inputs: _wave.inputs['Scale'].default_value = {scale}
        if 'Distortion' in _wave.inputs: _wave.inputs['Distortion'].default_value = {distortion}
        if 'Detail' in _wave.inputs: _wave.inputs['Detail'].default_value = {detail}
        _c0 = tuple([max(0.0, c * 0.7) for c in {tuple(color)}[:3]] + [1.0])
        _c1 = tuple([min(1.0, c * 1.3) for c in {tuple(color)}[:3]] + [1.0])
        _ramp.color_ramp.elements[0].position = 0.35
        _ramp.color_ramp.elements[0].color = _c0
        _ramp.color_ramp.elements[1].position = 0.65
        _ramp.color_ramp.elements[1].color = _c1
        _bump.inputs['Strength'].default_value = {strength}
        _mat.node_tree.links.new(_tex_coord.outputs['Object'], _mapping.inputs['Vector'])
        _mat.node_tree.links.new(_mapping.outputs['Vector'], _wave.inputs['Vector'])
        _mat.node_tree.links.new(_wave.outputs['Color'], _ramp.inputs['Fac'])
        _mat.node_tree.links.new(_ramp.outputs['Color'], _bsdf.inputs['Base Color'])
        _mat.node_tree.links.new(_wave.outputs['Fac'], _bump.inputs['Height'])
        _mat.node_tree.links.new(_bump.outputs['Normal'], _bsdf.inputs['Normal'])
"""
        elif procedural_texture == "brushed_metal":
            scale = procedural_params.get("scale", 35.0)
            stretch = procedural_params.get("stretch", 60.0)
            strength = procedural_params.get("strength", 0.04)
            procedural_code = f"""
        # Procedural Brushed Metal Node Graph
        _tex_coord = _mat.node_tree.nodes.new('ShaderNodeTexCoord')
        _mapping = _mat.node_tree.nodes.new('ShaderNodeMapping')
        _noise = _mat.node_tree.nodes.new('ShaderNodeTexNoise')
        _bump = _mat.node_tree.nodes.new('ShaderNodeBump')
        _mapping.inputs['Scale'].default_value = ({stretch}, 1.0, 1.0)
        _noise.inputs['Scale'].default_value = {scale}
        _noise.inputs['Detail'].default_value = 4.0
        _bump.inputs['Strength'].default_value = {strength}
        _mat.node_tree.links.new(_tex_coord.outputs['Object'], _mapping.inputs['Vector'])
        _mat.node_tree.links.new(_mapping.outputs['Vector'], _noise.inputs['Vector'])
        _mat.node_tree.links.new(_noise.outputs['Fac'], _bump.inputs['Height'])
        _mat.node_tree.links.new(_bump.outputs['Normal'], _bsdf.inputs['Normal'])
"""
        elif procedural_texture == "leather":
            scale = procedural_params.get("scale", 120.0)
            strength = procedural_params.get("strength", 0.12)
            procedural_code = f"""
        # Procedural Leather Voronoi Node Graph
        _tex_coord = _mat.node_tree.nodes.new('ShaderNodeTexCoord')
        _voronoi = _mat.node_tree.nodes.new('ShaderNodeTexVoronoi')
        _bump = _mat.node_tree.nodes.new('ShaderNodeBump')
        _voronoi.feature = 'F1'
        _voronoi.inputs['Scale'].default_value = {scale}
        _bump.inputs['Strength'].default_value = {strength}
        _mat.node_tree.links.new(_tex_coord.outputs['Object'], _voronoi.inputs['Vector'])
        _mat.node_tree.links.new(_voronoi.outputs['Distance'], _bump.inputs['Height'])
        _mat.node_tree.links.new(_bump.outputs['Normal'], _bsdf.inputs['Normal'])
"""
        elif procedural_texture == "marble":
            scale = procedural_params.get("scale", 5.0)
            distortion = procedural_params.get("distortion", 8.0)
            strength = procedural_params.get("strength", 0.08)
            procedural_code = f"""
        # Procedural Marble Veins Node Graph
        _tex_coord = _mat.node_tree.nodes.new('ShaderNodeTexCoord')
        _wave = _mat.node_tree.nodes.new('ShaderNodeTexWave')
        _ramp = _mat.node_tree.nodes.new('ShaderNodeValToRGB')
        _bump = _mat.node_tree.nodes.new('ShaderNodeBump')
        _wave.wave_type = 'BANDS'
        if 'Scale' in _wave.inputs: _wave.inputs['Scale'].default_value = {scale}
        if 'Distortion' in _wave.inputs: _wave.inputs['Distortion'].default_value = {distortion}
        if 'Detail' in _wave.inputs: _wave.inputs['Detail'].default_value = 4.0
        _ramp.color_ramp.elements[0].position = 0.45
        _ramp.color_ramp.elements[0].color = (0.7, 0.7, 0.72, 1.0)
        _ramp.color_ramp.elements[1].position = 0.55
        _ramp.color_ramp.elements[1].color = {tuple(color)}
        _bump.inputs['Strength'].default_value = {strength}
        _mat.node_tree.links.new(_tex_coord.outputs['Object'], _wave.inputs['Vector'])
        _mat.node_tree.links.new(_wave.outputs['Color'], _ramp.inputs['Fac'])
        _mat.node_tree.links.new(_ramp.outputs['Color'], _bsdf.inputs['Base Color'])
        _mat.node_tree.links.new(_wave.outputs['Fac'], _bump.inputs['Height'])
        _mat.node_tree.links.new(_bump.outputs['Normal'], _bsdf.inputs['Normal'])
"""
        elif procedural_texture == "noise":
            scale = procedural_params.get("scale", 30.0)
            detail = procedural_params.get("detail", 4.0)
            strength = procedural_params.get("strength", 0.15)
            procedural_code = f"""
        # Procedural Noise / Surface Roughness Bump
        _tex_coord = _mat.node_tree.nodes.new('ShaderNodeTexCoord')
        _noise = _mat.node_tree.nodes.new('ShaderNodeTexNoise')
        _bump = _mat.node_tree.nodes.new('ShaderNodeBump')
        _noise.inputs['Scale'].default_value = {scale}
        _noise.inputs['Detail'].default_value = {detail}
        _bump.inputs['Strength'].default_value = {strength}
        _mat.node_tree.links.new(_tex_coord.outputs['Object'], _noise.inputs['Vector'])
        _mat.node_tree.links.new(_noise.outputs['Fac'], _bump.inputs['Height'])
        _mat.node_tree.links.new(_bump.outputs['Normal'], _bsdf.inputs['Normal'])
"""

        return (
            f"_mat_obj = bpy.data.objects.get({repr(obj_name)})\n"
            f"if _mat_obj:\n"
            f"    _mat = bpy.data.materials.get({repr(mat_name)}) or bpy.data.materials.new({repr(mat_name)})\n"
            f"    _mat.use_nodes = True\n"
            f"    _mat['sentinel_build_id'] = {self._collection_name!r}\n"
            f"    _bsdf = next((n for n in _mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'), None)\n"
            f"    if _bsdf:\n"
            f"        if 'Base Color' in _bsdf.inputs: _bsdf.inputs['Base Color'].default_value = {tuple(color)}\n"
            f"        if 'Metallic'   in _bsdf.inputs: _bsdf.inputs['Metallic'].default_value   = {metallic}\n"
            f"        if 'Roughness'  in _bsdf.inputs: _bsdf.inputs['Roughness'].default_value  = {roughness}\n"
            f"        if 'IOR' in _bsdf.inputs: _bsdf.inputs['IOR'].default_value = {ior}\n"
            f"        if 'Alpha' in _bsdf.inputs: _bsdf.inputs['Alpha'].default_value = {alpha}\n"
            f"        if 'Transmission Weight' in _bsdf.inputs: _bsdf.inputs['Transmission Weight'].default_value = {transmission}\n"
            f"        elif 'Transmission' in _bsdf.inputs: _bsdf.inputs['Transmission'].default_value = {transmission}\n"
            f"        if 'Subsurface Weight' in _bsdf.inputs: _bsdf.inputs['Subsurface Weight'].default_value = {subsurface}\n"
            f"        elif 'Subsurface' in _bsdf.inputs: _bsdf.inputs['Subsurface'].default_value = {subsurface}\n"
            f"        if 'Subsurface Tint' in _bsdf.inputs and {repr(subsurface_color)}: _bsdf.inputs['Subsurface Tint'].default_value = tuple({repr(subsurface_color)})\n"
            f"        if 'Subsurface Radius' in _bsdf.inputs: _bsdf.inputs['Subsurface Radius'].default_value = {tuple(subsurface_radius)}\n"
            f"        if 'Coat Weight' in _bsdf.inputs: _bsdf.inputs['Coat Weight'].default_value = {clearcoat}\n"
            f"        elif 'Clearcoat' in _bsdf.inputs: _bsdf.inputs['Clearcoat'].default_value = {clearcoat}\n"
            f"        if 'Coat Roughness' in _bsdf.inputs: _bsdf.inputs['Coat Roughness'].default_value = {clearcoat_roughness}\n"
            f"        elif 'Clearcoat Roughness' in _bsdf.inputs: _bsdf.inputs['Clearcoat Roughness'].default_value = {clearcoat_roughness}\n"
            f"        if 'Sheen Weight' in _bsdf.inputs: _bsdf.inputs['Sheen Weight'].default_value = {sheen}\n"
            f"        elif 'Sheen' in _bsdf.inputs: _bsdf.inputs['Sheen'].default_value = {sheen}\n"
            f"        if 'Specular IOR Level' in _bsdf.inputs: _bsdf.inputs['Specular IOR Level'].default_value = {specular}\n"
            f"        elif 'Specular' in _bsdf.inputs: _bsdf.inputs['Specular'].default_value = {specular}\n"
            f"        if 'Specular Tint' in _bsdf.inputs: _bsdf.inputs['Specular Tint'].default_value = {specular_tint_color}\n"
            f"{aniso_lines}"
            f"        if {repr(emission_color)} and {emission_strength} > 0:\n"
            f"            _em = tuple({repr(emission_color)})\n"
            f"            if 'Emission Color' in _bsdf.inputs: _bsdf.inputs['Emission Color'].default_value = _em\n"
            f"            elif 'Emission' in _bsdf.inputs: _bsdf.inputs['Emission'].default_value = _em\n"
            f"            if 'Emission Strength' in _bsdf.inputs: _bsdf.inputs['Emission Strength'].default_value = {emission_strength}\n"
            f"{procedural_code}"
            f"    _mat['sentinel_normal_strength'] = {normal_strength}\n"
            f"    _mat['sentinel_blend_mode'] = {blend_mode!r}\n"
            f"    if hasattr(_mat, 'surface_render_method') and {blend_mode!r} != 'opaque': _mat.surface_render_method = 'DITHERED' if {blend_mode!r} == 'dithered' else 'BLENDED'\n"
            f"    elif hasattr(_mat, 'surface_render_method') and ({transmission} > 0 or {alpha} < 1): _mat.surface_render_method = 'DITHERED'\n"
            f"    if _mat_obj.data and hasattr(_mat_obj.data,'materials'):\n"
            f"        if not _mat_obj.data.materials: _mat_obj.data.materials.append(_mat)\n"
            f"        else: _mat_obj.data.materials[0] = _mat\n"
            f"        _mat_obj.active_material = _mat\n"
            f"        try:\n"
            f"            if len(_mat_obj.data.uv_layers) == 0:\n"
            f"                bpy.context.view_layer.objects.active = _mat_obj\n"
            f"                bpy.ops.object.mode_set(mode='EDIT')\n"
            f"                bpy.ops.mesh.select_all(action='SELECT')\n"
            f"                bpy.ops.uv.smart_project(angle_limit=66.0, island_margin=0.02)\n"
            f"                bpy.ops.object.mode_set(mode='OBJECT')\n"
            f"        except Exception:\n"
            f"            pass\n"
        )

    def _estimate_bbox(
        self, geo: Any, world_pos: List[float]
    ) -> Optional[Dict[str, List[float]]]:
        """Estimate bbox from geometry spec without querying Blender.

        Used during buffered build so Stage 4 cross-reference sockets have
        something to work with.  flush() overwrites with the real bbox.
        """
        from .node_types import PrimitiveType
        p = world_pos
        prim = geo.primitive
        try:
            if prim == PrimitiveType.BOX:
                s = geo.size or [1, 1, 1]
                return {
                    "min": [p[0]-s[0]/2, p[1]-s[1]/2, p[2]-s[2]/2],
                    "max": [p[0]+s[0]/2, p[1]+s[1]/2, p[2]+s[2]/2],
                }
            elif prim in (PrimitiveType.CYLINDER, PrimitiveType.CONE, PrimitiveType.CAPSULE, PrimitiveType.PYRAMID, PrimitiveType.PRISM):
                r = geo.radius or 0.5
                d = geo.depth  or 1.0
                return {
                    "min": [p[0]-r, p[1]-r, p[2]-d/2],
                    "max": [p[0]+r, p[1]+r, p[2]+d/2],
                }
            elif prim in (PrimitiveType.SPHERE, PrimitiveType.HEMISPHERE):
                r = geo.radius or 0.5
                return {
                    "min": [p[0]-r, p[1]-r, p[2]-r],
                    "max": [p[0]+r, p[1]+r, p[2]+r],
                }
            elif prim == PrimitiveType.TORUS:
                r = (geo.major_radius or 1.0) + (geo.minor_radius or 0.25)
                return {
                    "min": [p[0]-r, p[1]-r, p[2]-r],
                    "max": [p[0]+r, p[1]+r, p[2]+r],
                }
            elif prim in (PrimitiveType.PLANE, PrimitiveType.GRID, PrimitiveType.WEDGE):
                s = geo.size or [1.0, 1.0, 0.0]
                if prim == PrimitiveType.WEDGE:
                    z = s[2] / 2
                else:
                    z = 0.0
                return {
                    "min": [p[0]-s[0]/2, p[1]-s[1]/2, p[2]-z],
                    "max": [p[0]+s[0]/2, p[1]+s[1]/2, p[2]+z],
                }
            elif prim == PrimitiveType.CIRCLE:
                r = geo.radius or 0.5
                return {"min": [p[0]-r, p[1]-r, p[2]], "max": [p[0]+r, p[1]+r, p[2]]}
        except Exception:
            pass
        return None

    def _compute_assembly_bbox_from_children(
        self, node: "ManifestNode", manifest: "BuildManifest"
    ) -> Optional[Dict[str, List[float]]]:
        """Compute assembly bbox from children's existing bboxes (Python-side)."""
        mn = [float("inf")] * 3
        mx = [float("-inf")] * 3
        found = False
        for cid in node.children_ids:
            child = manifest.nodes.get(cid)
            if child and child.bounding_box:
                found = True
                for i in range(3):
                    mn[i] = min(mn[i], child.bounding_box["min"][i])
                    mx[i] = max(mx[i], child.bounding_box["max"][i])
        return {"min": mn, "max": mx} if found else None

    async def _create_primitive(
        self,
        node: "ManifestNode",
        obj_name: str,
        world_pos: List[float],
        matrix_rows: List[List[float]],
        collection_name: str,
    ) -> Dict[str, Any]:
        """Create a primitive mesh in Blender (used by build_boolean_cut only)."""
        from .node_types import PrimitiveType
        from core.blender_ops import parse_op_output

        if not node.geometry:
            return {"ok": False, "error": "No geometry spec"}

        script = self._get_primitive_script(
            node.geometry.primitive, obj_name, node.geometry, world_pos, matrix_rows, collection_name
        )

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
        matrix_rows: List[List[float]],
        collection: str,
    ) -> str:
        """Generate script to create a box."""
        return _build_script(_BOX_TEMPLATE, {
            "name": name,
            "size": size,
            "matrix_rows": matrix_rows,
            "collection": collection,
        })

    
    def _cylinder_script(
        self,
        name: str,
        radius: float,
        depth: float,
        vertices: int,
        pos: List[float],
        matrix_rows: List[List[float]],
        collection: str,
    ) -> str:
        """Generate script to create a cylinder."""
        return f'''
import bpy
import json

name = {repr(name)}
radius = {radius}
depth = {depth}
vertices = {vertices}
matrix_rows = {repr(matrix_rows)}
coll_name = {repr(collection)}

if name in bpy.data.objects:
    result = {{"ok": False, "error": f"Object '{{name}}' already exists"}}
else:
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth)
    obj = bpy.context.active_object
    obj.name = name
    obj.data.name = name
    import mathutils
    obj.matrix_world = mathutils.Matrix(matrix_rows)
    
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
        matrix_rows: List[List[float]],
        collection: str,
    ) -> str:
        """Generate script to create a sphere."""
        return f'''
import bpy
import json

name = {repr(name)}
radius = {radius}
matrix_rows = {repr(matrix_rows)}
coll_name = {repr(collection)}

if name in bpy.data.objects:
    result = {{"ok": False, "error": f"Object '{{name}}' already exists"}}
else:
    bpy.ops.mesh.primitive_uv_sphere_add(radius=radius, location=(0, 0, 0))
    obj = bpy.context.active_object
    obj.name = name
    obj.data.name = name
    import mathutils
    obj.matrix_world = mathutils.Matrix(matrix_rows)
    
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
        matrix_rows: List[List[float]],
        collection: str,
        radius2: float = 0.0,
    ) -> str:
        """Generate script to create a cone."""
        return f'''
import bpy
import json

name = {repr(name)}
radius = {radius}
radius2 = {radius2}
depth = {depth}
matrix_rows = {repr(matrix_rows)}
coll_name = {repr(collection)}

if name in bpy.data.objects:
    result = {{"ok": False, "error": f"Object '{{name}}' already exists"}}
else:
    bpy.ops.mesh.primitive_cone_add(radius1=radius, radius2=radius2, depth=depth)
    obj = bpy.context.active_object
    obj.name = name
    obj.data.name = name
    import mathutils
    obj.matrix_world = mathutils.Matrix(matrix_rows)
    
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
        matrix_rows: List[List[float]],
        collection: str,
    ) -> str:
        """Generate script to create a hemisphere via bisect."""
        return f'''
import bpy
import bmesh
import json

name = {repr(name)}
radius = {radius}
matrix_rows = {repr(matrix_rows)}
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
    
    import mathutils
    obj.matrix_world = mathutils.Matrix(matrix_rows)
    
    coll = bpy.data.collections.get(coll_name)
    if coll:
        for c in obj.users_collection:
            c.objects.unlink(obj)
        coll.objects.link(obj)
    
    result = {{"ok": True, "name": obj.name, "location": list(obj.location)}}

print("SENTINEL_OUTPUT_START" + json.dumps(result) + "SENTINEL_OUTPUT_END")
'''

    def _capsule_script(
        self,
        name: str,
        radius: float,
        depth: float,
        pos: List[float],
        matrix_rows: List[List[float]],
        collection: str,
    ) -> str:
        """Generate a closed capsule with a total cap-to-cap ``depth``."""
        cylinder_depth = max(0.0, depth - 2.0 * radius)
        return f'''
import bpy
import json
import mathutils

name = {repr(name)}
radius = {radius}
cylinder_depth = {cylinder_depth}
matrix_rows = {repr(matrix_rows)}
coll_name = {repr(collection)}

if name in bpy.data.objects:
    result = {{"ok": False, "error": f"Object '{{name}}' already exists"}}
else:
    pieces = []
    if cylinder_depth > 0:
        bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=radius, depth=cylinder_depth)
        pieces.append(bpy.context.active_object)
    bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, radius=radius, location=(0,0,cylinder_depth/2))
    pieces.append(bpy.context.active_object)
    bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, radius=radius, location=(0,0,-cylinder_depth/2))
    pieces.append(bpy.context.active_object)
    bpy.ops.object.select_all(action='DESELECT')
    for piece in pieces: piece.select_set(True)
    bpy.context.view_layer.objects.active = pieces[0]
    bpy.ops.object.join()
    obj = bpy.context.active_object
    obj.name = name
    obj.data.name = name
    obj.matrix_world = mathutils.Matrix(matrix_rows)
    coll = bpy.data.collections.get(coll_name)
    if coll:
        for c in list(obj.users_collection): c.objects.unlink(obj)
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
        matrix_rows: List[List[float]],
        collection: str,
    ) -> str:
        """Generate script to create a torus."""
        return f'''
import bpy
import json

name = {repr(name)}
major = {major}
minor = {minor}
matrix_rows = {repr(matrix_rows)}
coll_name = {repr(collection)}

if name in bpy.data.objects:
    result = {{"ok": False, "error": f"Object '{{name}}' already exists"}}
else:
    bpy.ops.mesh.primitive_torus_add(major_radius=major, minor_radius=minor)
    obj = bpy.context.active_object
    obj.name = name
    obj.data.name = name
    import mathutils
    obj.matrix_world = mathutils.Matrix(matrix_rows)
    
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
        matrix_rows: List[List[float]],
        collection: str,
    ) -> str:
        """Generate script to create a U-shape (half torus) via bisect.
        
        Used for padlock shackles, handles, hooks — any bent tube.
        Arch faces UP (+Z), legs point DOWN (-Z).
        Local origin is at the bottom of the legs (Z=0), so TOP_CENTER
        socket places the leg bottoms flush with the parent's top face.
        major_radius = radius of the U arc centre-line
        minor_radius = tube cross-section radius
        """
        return f'''
import bpy
import bmesh
import json
import math
from mathutils import Vector

name = {repr(name)}
major = {major}
minor = {minor}
matrix_rows = {repr(matrix_rows)}
coll_name = {repr(collection)}

if name in bpy.data.objects:
    result = {{"ok": False, "error": f"Object '{{name}}' already exists"}}
else:
    # Build torus at origin, lying flat in XY plane (default Blender orientation)
    bpy.ops.mesh.primitive_torus_add(
        major_radius=major, minor_radius=minor,
        major_segments=48, minor_segments=16,
        location=(0, 0, 0), rotation=(0, 0, 0)
    )
    obj = bpy.context.active_object
    obj.name = name
    obj.data.name = name
    
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    
    # Step 1: bisect on X-plane — keep only X >= 0 half.
    # This gives a C-shape lying in the XZ plane (arch on +X side).
    geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
    bmesh.ops.bisect_plane(
        bm, geom=geom,
        plane_co=(0, 0, 0), plane_no=(1, 0, 0),
        clear_inner=True, clear_outer=False
    )
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.0001)
    boundary = [e for e in bm.edges if len(e.link_faces) == 1]
    if boundary:
        bmesh.ops.edgeloop_fill(bm, edges=boundary)
    
    # Step 2: rotate 90 deg around Z so the arch faces +Y,
    # then 90 deg around X so the arch faces +Z (up) and legs point -Z (down).
    import mathutils
    rot_z90 = mathutils.Matrix.Rotation(math.pi / 2, 4, 'Z')
    rot_x90 = mathutils.Matrix.Rotation(math.pi / 2, 4, 'X')
    mat = rot_x90 @ rot_z90
    bmesh.ops.transform(bm, matrix=mat, verts=bm.verts)
    
    # Step 3: translate so the bottom of the legs sits at Z = 0.
    # After the rotation the legs point down; find the minimum Z and shift up.
    min_z = min(v.co.z for v in bm.verts)
    bmesh.ops.translate(bm, vec=Vector((0, 0, -min_z)), verts=bm.verts)
    
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()
    
    # Apply world matrix directly from Stage 4 — no Euler reconstruction.
    obj.matrix_world = mathutils.Matrix(matrix_rows)
    
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
        alpha = getattr(material, 'alpha', 1.0)
        if alpha is None:
            alpha = 1.0
        
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
alpha = {alpha}
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
            # Alpha for viewport transparency
            if "Alpha" in bsdf.inputs:
                bsdf.inputs["Alpha"].default_value = alpha
            # Blender 4.x: use HASHED for transmission (BLEND breaks it)
            mat.blend_method = 'HASHED'
            try:
                mat.shadow_method = 'HASHED'
            except AttributeError:
                pass  # Blender 4.2+ removed shadow_method
        
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
        should_apply = mod_spec.get("apply", False)
        mod_name = mod_spec.get("name") or f"Sentinel_{{mod_type}}"
        
        try:
            if mod_type == "subdivision":
                mod = obj.modifiers.new(name=mod_name, type='SUBSURF')
                mod.levels = mod_spec.get("subdivision_levels", 2)
                mod.render_levels = mod_spec.get("subdivision_render_levels", 2)
                mod.subdivision_type = mod_spec.get("subdivision_type", "CATMULL_CLARK")
                
            elif mod_type == "bevel":
                mod = obj.modifiers.new(name=mod_name, type='BEVEL')
                dims = [d for d in (obj.dimensions.x, obj.dimensions.y, obj.dimensions.z) if d > 0.0001]
                min_dim = min(dims) if dims else 0.1
                requested_width = mod_spec.get("bevel_width", 0.02)
                mod.width = min(requested_width, max(0.0005, min_dim * 0.25))
                mod.segments = mod_spec.get("bevel_segments", 3)
                mod.limit_method = mod_spec.get("bevel_limit_method", "ANGLE")
                mod.angle_limit = math.radians(mod_spec.get("bevel_angle_limit", 30.0))
                mod.profile = mod_spec.get("bevel_profile", 0.5)
                mod.use_clamp_overlap = True
                
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
    created = True
else:
    coll = bpy.data.collections[coll_name]
    created = False
coll['sentinel_build_id'] = {self._collection_name!r}
coll['sentinel_attempt_id'] = {self._attempt_id!r}
result = {{"ok": True, "created": created, "name": coll_name}}

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

obj = bpy.data.objects.get({repr(obj_name)})
if not obj or obj.type != 'MESH':
    result = {{"ok": False, "error": "not_mesh"}}
else:
    # Use obj.dimensions (local-space extents) so that rotated objects
    # are measured against their own axes, not the world AABB.
    # World AABB grows for any non-axis-aligned rotation (e.g. RADIAL
    # blades at 90°/270°), causing false dimension mismatches.
    d = obj.dimensions
    result = {{"ok": True, "scaled_size": [d.x, d.y, d.z]}}

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
    
    degen = sum(1 for f in bm.faces if f.calc_area() < 1e-12)
    if degen > 0:
        issues.append(f"{{degen}} degenerate faces")
    
    non_manifold = sum(1 for e in bm.edges if not e.is_manifold)
    if non_manifold > 0:
        issues.append(f"{{non_manifold}} non-manifold edges")
    
    bm.free()
    err_msg = "; ".join(issues) if issues else None
    result = {{"ok": len(issues) == 0, "error": err_msg, "issues": issues}}

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
        """Buffer an assembly empty + parenting for atomic flush later.

        Does NOT send any MCP call.  The empty creation and all child
        parenting are appended to self._script_buffer so they execute in
        the same Python context as the mesh creation fragments.
        """
        from .node_types import NodeKind, SocketType
        from core.blender_ops import parse_op_output

        empty_name = f"{node.label}_assembly_{uuid.uuid4().hex[:6]}"

        child_objects: List[str] = []
        for cid in node.children_ids:
            child = manifest.nodes.get(cid)
            if child and child.blender_objects:
                # An assembly's first object is its Empty.  Parent that Empty,
                # not every descendant mesh, so nested assemblies keep their
                # own hierarchy instead of being flattened by the next merge.
                if child.kind in (NodeKind.ASSEMBLY, NodeKind.MODEL):
                    child_objects.append(child.blender_objects[0])
                else:
                    child_objects.extend(child.blender_objects)

        if not child_objects:
            return ExecutionResult(
                ok=False, node_id=node.node_id, error="No child objects to merge"
            )

        # Parent assembly label so the fragment can find the parent empty
        from .node_types import NodeKind as _NK
        parent_assembly_label: Optional[str] = None
        if node.parent_id:
            parent_node = manifest.nodes.get(node.parent_id)
            if parent_node and parent_node.kind in (_NK.ASSEMBLY, _NK.MODEL):
                parent_assembly_label = parent_node.label

        assembly_matrix_rows = (
            list(node.transform_state.world_matrix.matrix)
            if node.transform_state and node.transform_state.world_matrix
            else None
        )

        # ── Build the fragment ─────────────────────────────────────────────────
        # Uses _link/_unlink_all helpers defined in flush() header.
        fragment_lines = [
            f"# ── assembly: {node.label} ──",
            f"_e = bpy.data.objects.new({repr(empty_name)}, None)",
            f"_e.empty_display_type = 'PLAIN_AXES'",
            f"_e.empty_display_size = 0.5",
        ]

        if assembly_matrix_rows:
            fragment_lines.append(
                f"_e.matrix_world = mathutils.Matrix({repr(assembly_matrix_rows)})"
            )

        fragment_lines += [
            "_unlink_all(_e) if _e.users_collection else None",
            "_link(_e)",
        ]

        # Parent this empty to its parent assembly empty (already buffered above
        # because bottom-up order means child assemblies merge before parents).
        if parent_assembly_label:
            fragment_lines += [
                f"_pe = next((o for o in bpy.data.objects if o.name.startswith({repr(parent_assembly_label + '_assembly_')}) and o.type == 'EMPTY'), None)",
                "if _pe:",
                "    _world = _e.matrix_world.copy()",
                "    _e.parent = _pe",
                "    _e.matrix_parent_inverse = _pe.matrix_world.inverted()",
                "    _e.matrix_world = _world",
            ]

        # Parent all child objects to this empty
        fragment_lines += [
            f"for _cn in {repr(child_objects)}:",
            "    _co = bpy.data.objects.get(_cn)",
            "    if _co:",
            "        _world = _co.matrix_world.copy()",
            "        _co.parent = _e",
            "        _co.matrix_parent_inverse = _e.matrix_world.inverted()",
            "        _co.matrix_world = _world",
            f"_sentinel_results[{repr(empty_name)}] = list(_e.matrix_world.translation)",
        ]

        self._script_buffer.append("\n".join(fragment_lines))
        self._created_objects.append(empty_name)

        # Compute assembly bbox from children's estimated bboxes (Python-side)
        bbox = self._compute_assembly_bbox_from_children(node, manifest)

        return ExecutionResult(
            ok=True,
            node_id=node.node_id,
            blender_objects=[empty_name] + child_objects,
            generation_id=self._collection_name,
            bounding_box=bbox,
            steps_executed=1,
        )

    
    async def cleanup_all(self) -> None:
        """Clean up all created objects and the collection."""
        from core.blender_ops import parse_op_output
        await self._inject_fault(FaultPoint.DURING_CLEANUP)
        
        script = f'''
import bpy
import json

objects = {repr(self._created_objects)}
coll_name = {repr(self._collection_name)}
removed = []

coll = bpy.data.collections.get(coll_name)
if coll:
    for obj in list(coll.objects):
        obj_name = obj.name
        data = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        removed.append(obj_name)
        if data and getattr(data, 'users', 1) == 0:
            if isinstance(data, bpy.types.Mesh): bpy.data.meshes.remove(data)
            elif isinstance(data, bpy.types.Curve): bpy.data.curves.remove(data)
    bpy.data.collections.remove(coll)

# Also remove attempt-tagged objects that were created before collection link.
for obj in list(bpy.data.objects):
    if obj.get('sentinel_build_id') == coll_name:
        obj_name = obj.name
        data = obj.data
        removed.append(obj_name)
        bpy.data.objects.remove(obj, do_unlink=True)
        if data and getattr(data, 'users', 1) == 0:
            if isinstance(data, bpy.types.Mesh): bpy.data.meshes.remove(data)
            elif isinstance(data, bpy.types.Curve): bpy.data.curves.remove(data)

# A material may be shared by a newer attempt.  Keep it while it has users;
# once unreferenced, any Sentinel-owned material is safe to collect even if
# its owner was an earlier superseded attempt.
for mat in list(bpy.data.materials):
    if mat.get('sentinel_build_id') and mat.users == 0:
        bpy.data.materials.remove(mat)

result = {{"ok": True, "removed": removed}}
print("SENTINEL_OUTPUT_START" + json.dumps(result) + "SENTINEL_OUTPUT_END")
'''
        try:
            result = await self.mcp_manager.call_locked(
                "blender", "execute_blender_code", {"code": script}
            )
            data = parse_op_output(result.get("output", ""))
            if not data.get("ok"):
                raise RuntimeError(str(data.get("error", "Blender cleanup returned no success receipt")))
        except Exception as e:
            logger.warning(f"Cleanup failed: {e}")
            raise
        
        self._created_objects.clear()
        self._collection_created = False

    async def _inject_fault(self, point: FaultPoint) -> None:
        """Invoke a constructor-supplied test hook; never read runtime flags."""
        if self.fault_injector is None:
            return
        result = self.fault_injector(point, self)
        if inspect.isawaitable(result):
            await result

    async def verify_attempt_absent(self) -> Dict[str, Any]:
        """Independently prove no datablock still carries this attempt tag."""
        script = f'''
import bpy, json
_tag={self._collection_name!r}
_remaining=[]
for _kind,_items in (
    ('objects', bpy.data.objects), ('meshes', bpy.data.meshes),
    ('materials', bpy.data.materials), ('collections', bpy.data.collections),
    ('curves', bpy.data.curves), ('images', bpy.data.images), ('lights', bpy.data.lights),
):
    for _item in _items:
        if _item.get('sentinel_build_id') == _tag or (_kind == 'collections' and _item.name == _tag):
            _remaining.append({{'kind': _kind, 'name': _item.name}})
print('SENTINEL_OUTPUT_START'+json.dumps({{'ok': not _remaining, 'remaining': _remaining}})+'SENTINEL_OUTPUT_END')
'''
        result = await self.mcp_manager.call_locked("blender", "execute_blender_code", {"code": script})
        # ``ok: false`` is an expected verification result (tagged remnants
        # exist), not a Blender transport failure.  Do not route this through
        # parse_op_output, which deliberately raises on false operational
        # receipts and would hide the evidence from the ledger.
        output = str(result.get("output", ""))
        start = output.find("SENTINEL_OUTPUT_START")
        end = output.find("SENTINEL_OUTPUT_END", start)
        if start < 0 or end < 0:
            raise RuntimeError("attempt absence verification returned no Sentinel payload")
        payload = output[start + len("SENTINEL_OUTPUT_START"):end]
        try:
            parsed = _json.loads(payload)
        except (TypeError, ValueError) as exc:
            raise RuntimeError("attempt absence verification returned invalid JSON") from exc
        if not isinstance(parsed, dict) or "ok" not in parsed:
            raise RuntimeError("attempt absence verification returned malformed receipt")
        return parsed


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
