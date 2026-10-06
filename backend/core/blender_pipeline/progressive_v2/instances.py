"""Instance Manager — Definition vs Placement pattern for repeated parts.

Complex models often have many identical parts (cannons on a ship, windows on
a building, rivets on machinery). Building each independently wastes time and
creates inconsistency.

The Instance pattern:
1. DEFINITION node: Built and verified once, becomes the template
2. INSTANCE nodes: Reference the definition, only need placement

Blueprint reference: §14 (Instance Definitions).

Example hierarchy:
    ship (MODEL)
    ├── hull (PART)
    ├── cannon_def (DEFINITION)  ← Built once, verified
    ├── cannon_1 (INSTANCE of cannon_def)  ← Just placed
    ├── cannon_2 (INSTANCE of cannon_def)  ← Just placed
    └── cannon_3 (INSTANCE of cannon_def)  ← Just placed
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, TYPE_CHECKING

if TYPE_CHECKING:
    from .manifest import BuildManifest, ManifestNode

logger = logging.getLogger(__name__)


@dataclass
class InstancePlacement:
    """Placement data for an instance."""
    instance_node_id: str
    definition_node_id: str
    world_position: List[float]
    world_rotation: List[float]  # degrees
    scale: List[float] = field(default_factory=lambda: [1.0, 1.0, 1.0])


@dataclass 
class InstanceResult:
    """Result of creating instances."""
    ok: bool
    definition_object: Optional[str] = None
    instance_objects: List[str] = field(default_factory=list)
    error: Optional[str] = None


class InstanceManager:
    """Manages definition/instance relationships for repeated parts.
    
    Usage:
        manager = InstanceManager(mcp_manager)
        
        # After building definition node
        await manager.register_definition(def_node, "cannon_mesh")
        
        # For each instance node
        result = await manager.create_instance(inst_node, manifest, task_id)
    """
    
    def __init__(self, mcp_manager: Any):
        self.mcp_manager = mcp_manager
        
        # Track definitions: definition_node_id -> blender_object_name
        self._definitions: Dict[str, str] = {}
        
        # Track instances: instance_node_id -> blender_object_name
        self._instances: Dict[str, str] = {}
    
    def register_definition(
        self,
        node: "ManifestNode",
        blender_object: str,
    ) -> None:
        """Register a built node as a definition template."""
        self._definitions[node.node_id] = blender_object
        logger.debug(f"Registered definition: {node.label} -> {blender_object}")
    
    def get_definition_object(self, definition_id: str) -> Optional[str]:
        """Get the Blender object name for a definition."""
        return self._definitions.get(definition_id)
    
    def is_definition_ready(self, definition_id: str) -> bool:
        """Check if a definition has been built and registered."""
        return definition_id in self._definitions
    
    async def create_instance(
        self,
        instance_node: "ManifestNode",
        manifest: "BuildManifest",
        task_id: str,
        use_linked: bool = False,
    ) -> InstanceResult:
        """Create an instance of a definition.
        
        Args:
            instance_node: The INSTANCE node to create
            manifest: Build manifest for context
            task_id: Task ID for logging
            use_linked: If True, use Blender linked duplicate (shares mesh data)
                       If False, use full copy (independent mesh)
        """
        from .node_types import NodeKind
        from core.blender_ops import parse_op_output
        
        if instance_node.kind != NodeKind.INSTANCE:
            return InstanceResult(
                ok=False,
                error=f"Node {instance_node.label} is not an INSTANCE",
            )
        
        definition_id = instance_node.instance_of
        if not definition_id:
            return InstanceResult(
                ok=False,
                error=f"Instance {instance_node.label} has no definition reference",
            )
        
        definition_object = self._definitions.get(definition_id)
        if not definition_object:
            return InstanceResult(
                ok=False,
                error=f"Definition {definition_id} not registered",
            )
        
        # Compute world transform for instance
        world_pos, world_rot, scale = self._compute_instance_transform(instance_node, manifest)
        
        # Generate unique name for instance
        gen_short = uuid.uuid4().hex[:6]
        instance_name = f"g{gen_short}_{instance_node.label}"
        
        # Create instance in Blender
        if use_linked:
            script = self._linked_duplicate_script(
                definition_object, instance_name, world_pos, world_rot, scale
            )
        else:
            script = self._full_copy_script(
                definition_object, instance_name, world_pos, world_rot, scale
            )
        
        try:
            result = await self.mcp_manager.call_locked(
                "blender", "execute_blender_code", {"code": script}
            )
            data = parse_op_output(result.get("output", ""))
            
            if not data.get("ok"):
                return InstanceResult(
                    ok=False,
                    error=data.get("error", "Instance creation failed"),
                )
            
            created_name = data.get("name", instance_name)
            self._instances[instance_node.node_id] = created_name
            
            return InstanceResult(
                ok=True,
                definition_object=definition_object,
                instance_objects=[created_name],
            )
            
        except Exception as e:
            return InstanceResult(ok=False, error=str(e))
    
    async def create_instances_batch(
        self,
        instance_nodes: List["ManifestNode"],
        manifest: "BuildManifest",
        task_id: str,
        use_linked: bool = False,
    ) -> InstanceResult:
        """Create multiple instances in a single Blender call (more efficient)."""
        from .node_types import NodeKind
        from core.blender_ops import parse_op_output
        
        if not instance_nodes:
            return InstanceResult(ok=True, instance_objects=[])
        
        # Group by definition
        by_definition: Dict[str, List["ManifestNode"]] = {}
        for node in instance_nodes:
            if node.kind != NodeKind.INSTANCE or not node.instance_of:
                continue
            def_id = node.instance_of
            if def_id not in by_definition:
                by_definition[def_id] = []
            by_definition[def_id].append(node)
        
        all_created = []
        
        for def_id, nodes in by_definition.items():
            definition_object = self._definitions.get(def_id)
            if not definition_object:
                logger.warning(f"Definition {def_id} not registered, skipping instances")
                continue
            
            # Build placement data
            placements = []
            for node in nodes:
                world_pos, world_rot, scale = self._compute_instance_transform(node, manifest)
                gen_short = uuid.uuid4().hex[:6]
                instance_name = f"g{gen_short}_{node.label}"
                placements.append({
                    "node_id": node.node_id,
                    "name": instance_name,
                    "position": world_pos,
                    "rotation": world_rot,
                    "scale": scale,
                })
            
            # Batch create
            script = self._batch_instance_script(
                definition_object, placements, use_linked
            )
            
            try:
                result = await self.mcp_manager.call_locked(
                    "blender", "execute_blender_code", {"code": script}
                )
                data = parse_op_output(result.get("output", ""))
                
                if data.get("ok"):
                    for p, created in zip(placements, data.get("created", [])):
                        self._instances[p["node_id"]] = created
                        all_created.append(created)
                        
            except Exception as e:
                logger.error(f"Batch instance creation failed: {e}")
        
        return InstanceResult(
            ok=len(all_created) > 0,
            instance_objects=all_created,
        )
    
    def _compute_instance_transform(
        self,
        node: "ManifestNode",
        manifest: "BuildManifest",
    ) -> tuple:
        """Compute world transform for an instance node using hierarchical matrix composition."""
        # Prefer transform_state.world_matrix if resolved (authoritative hierarchical composition)
        if node.transform_state and node.transform_state.world_matrix is not None:
            wm = node.transform_state.world_matrix
            return list(wm.position), list(wm.rotation), list(wm.scale)
        
        # If transform_state has local_transform and parent has world_matrix, compose them
        if node.parent_id and node.transform_state and node.transform_state.local_transform:
            parent = manifest.nodes.get(node.parent_id)
            if parent and parent.transform_state and parent.transform_state.world_matrix is not None:
                parent_wm = parent.transform_state.world_matrix
                wm = node.transform_state.compute_world(parent_wm)
                return list(wm.position), list(wm.rotation), list(wm.scale)

        local_offset = list(node.attachment.local_offset) if node.attachment else [0, 0, 0]
        local_rot = list(node.attachment.local_rotation) if node.attachment else [0, 0, 0]
        
        if not node.parent_id:
            return local_offset, local_rot, [1.0, 1.0, 1.0]
        
        parent = manifest.nodes.get(node.parent_id)
        if not parent or not parent.bounding_box:
            return local_offset, local_rot, [1.0, 1.0, 1.0]
        
        pmin = parent.bounding_box.get("min", [0, 0, 0])
        pmax = parent.bounding_box.get("max", [0, 0, 0])
        parent_center = [(pmin[i] + pmax[i]) / 2 for i in range(3)]
        world_pos = [parent_center[i] + local_offset[i] for i in range(3)]
        return world_pos, local_rot, [1.0, 1.0, 1.0]
    
    def _linked_duplicate_script(
        self,
        source: str,
        name: str,
        pos: List[float],
        rot: List[float],
        scale: Optional[List[float]] = None,
    ) -> str:
        """Script to create a linked duplicate (shares mesh data)."""
        scale_vec = scale if scale is not None else [1.0, 1.0, 1.0]
        return f'''
import bpy
import json
import math

source_name = {repr(source)}
new_name = {repr(name)}
pos = {pos}
rot_deg = {rot}
scale_vec = {scale_vec}

source = bpy.data.objects.get(source_name)
if not source:
    result = {{"ok": False, "error": f"Source '{{source_name}}' not found"}}
else:
    # Linked duplicate - shares mesh data
    new_obj = source.copy()
    new_obj.name = new_name
    # Don't copy mesh data - link to same mesh
    
    new_obj.location = tuple(pos)
    new_obj.rotation_euler = tuple(math.radians(r) for r in rot_deg)
    new_obj.scale = tuple(scale_vec)
    
    # Link to same collection as source
    for coll in source.users_collection:
        coll.objects.link(new_obj)
        break
    else:
        bpy.context.collection.objects.link(new_obj)
    
    result = {{"ok": True, "name": new_obj.name, "linked": True}}

print("SENTINEL_OUTPUT_START" + json.dumps(result) + "SENTINEL_OUTPUT_END")
'''
    
    def _full_copy_script(
        self,
        source: str,
        name: str,
        pos: List[float],
        rot: List[float],
        scale: Optional[List[float]] = None,
    ) -> str:
        """Script to create a full copy (independent mesh)."""
        scale_vec = scale if scale is not None else [1.0, 1.0, 1.0]
        return f'''
import bpy
import json
import math

source_name = {repr(source)}
new_name = {repr(name)}
pos = {pos}
rot_deg = {rot}
scale_vec = {scale_vec}

source = bpy.data.objects.get(source_name)
if not source:
    result = {{"ok": False, "error": f"Source '{{source_name}}' not found"}}
else:
    # Full copy - independent mesh data
    new_obj = source.copy()
    new_obj.name = new_name
    if source.data:
        new_obj.data = source.data.copy()
        new_obj.data.name = new_name
    
    new_obj.location = tuple(pos)
    new_obj.rotation_euler = tuple(math.radians(r) for r in rot_deg)
    new_obj.scale = tuple(scale_vec)
    
    for coll in source.users_collection:
        coll.objects.link(new_obj)
        break
    else:
        bpy.context.collection.objects.link(new_obj)
    
    result = {{"ok": True, "name": new_obj.name, "linked": False}}

print("SENTINEL_OUTPUT_START" + json.dumps(result) + "SENTINEL_OUTPUT_END")
'''
    
    def _batch_instance_script(
        self,
        source: str,
        placements: List[Dict],
        use_linked: bool,
    ) -> str:
        """Script to create multiple instances in one call."""
        return f'''
import bpy
import json
import math

source_name = {repr(source)}
placements = {placements}
use_linked = {use_linked}

source = bpy.data.objects.get(source_name)
if not source:
    result = {{"ok": False, "error": f"Source '{{source_name}}' not found"}}
else:
    created = []
    target_coll = None
    for coll in source.users_collection:
        target_coll = coll
        break
    
    for p in placements:
        new_obj = source.copy()
        new_obj.name = p["name"]
        
        if not use_linked and source.data:
            new_obj.data = source.data.copy()
            new_obj.data.name = p["name"]
        
        new_obj.location = tuple(p["position"])
        new_obj.rotation_euler = tuple(math.radians(r) for r in p["rotation"])
        if "scale" in p and p["scale"]:
            new_obj.scale = tuple(p["scale"])
        
        if target_coll:
            target_coll.objects.link(new_obj)
        else:
            bpy.context.collection.objects.link(new_obj)
        
        created.append(new_obj.name)
    
    result = {{"ok": True, "created": created, "count": len(created)}}

print("SENTINEL_OUTPUT_START" + json.dumps(result) + "SENTINEL_OUTPUT_END")
'''


def find_instance_groups(manifest: "BuildManifest") -> Dict[str, List[str]]:
    """Find groups of nodes that could share a definition.
    
    Looks for nodes with identical geometry specs that could be
    converted to definition + instances pattern.
    
    Returns:
        Dict mapping geometry_hash -> list of node_ids
    """
    from .node_types import NodeKind
    import hashlib
    import json
    
    groups: Dict[str, List[str]] = {}
    
    for node in manifest.nodes.values():
        if node.kind != NodeKind.PART:
            continue
        if not node.geometry:
            continue
        
        # Hash the geometry spec
        spec_str = json.dumps({
            "primitive": node.geometry.primitive_type.value if node.geometry.primitive_type else None,
            "dimensions": node.geometry.dimensions,
        }, sort_keys=True)
        spec_hash = hashlib.md5(spec_str.encode()).hexdigest()[:12]
        
        if spec_hash not in groups:
            groups[spec_hash] = []
        groups[spec_hash].append(node.node_id)
    
    # Only return groups with 2+ members (worth instancing)
    return {k: v for k, v in groups.items() if len(v) >= 2}
