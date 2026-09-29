"""Relationship Graph — cross-assembly socket connections.

Blueprint reference: §35 (Cross-Assembly Relationships).
- Socket connections between separate assemblies after both are VERIFIED
- Connector geometry computed deterministically from anchor world positions
- E.g., mast ↔ railing rigging, wheel ↔ axle connections
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .manifest import BuildManifest, ManifestNode, NodeState
from .node_types import NodeKind

logger = logging.getLogger(__name__)


@dataclass
class SocketAnchor:
    """A socket attachment point on a node."""
    node_id: str
    socket_type: str  # e.g., "top_center", "side_left", "custom"
    world_position: Optional[List[float]] = None  # Resolved after build
    local_offset: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])


@dataclass 
class CrossAssemblyRelationship:
    """A connection between two nodes in different assembly branches."""
    relationship_id: str
    source_anchor: SocketAnchor
    target_anchor: SocketAnchor
    connector_type: str = "none"  # "none", "rod", "cable", "beam"
    connector_object: Optional[str] = None  # Blender object name if created
    verified: bool = False


class RelationshipGraph:
    """Manages cross-assembly socket connections."""

    def __init__(self, mcp_manager: Optional[Any] = None):
        self.mcp_manager = mcp_manager
        self.relationships: Dict[str, CrossAssemblyRelationship] = {}

    def add_relationship(
        self,
        source_node_id: str,
        source_socket: str,
        target_node_id: str,
        target_socket: str,
        connector_type: str = "none",
    ) -> str:
        """Register a cross-assembly relationship."""
        rel_id = f"rel_{source_node_id}_{target_node_id}"
        
        self.relationships[rel_id] = CrossAssemblyRelationship(
            relationship_id=rel_id,
            source_anchor=SocketAnchor(node_id=source_node_id, socket_type=source_socket),
            target_anchor=SocketAnchor(node_id=target_node_id, socket_type=target_socket),
            connector_type=connector_type,
        )
        
        logger.debug(f"Added relationship: {source_node_id}:{source_socket} -> {target_node_id}:{target_socket}")
        return rel_id

    def get_pending_relationships(self, manifest: BuildManifest) -> List[CrossAssemblyRelationship]:
        """Get relationships where both endpoints are VERIFIED but relationship not yet resolved."""
        pending = []
        for rel in self.relationships.values():
            if rel.verified:
                continue
            
            source = manifest.nodes.get(rel.source_anchor.node_id)
            target = manifest.nodes.get(rel.target_anchor.node_id)
            
            if source and target:
                if source.state == NodeState.VERIFIED and target.state == NodeState.VERIFIED:
                    pending.append(rel)
        
        return pending

    async def resolve_relationship(
        self,
        rel: CrossAssemblyRelationship,
        manifest: BuildManifest,
        task_id: str = "adhoc",
    ) -> Dict[str, Any]:
        """Resolve socket positions and optionally create connector geometry."""
        source = manifest.nodes.get(rel.source_anchor.node_id)
        target = manifest.nodes.get(rel.target_anchor.node_id)
        
        if not source or not target:
            return {"ok": False, "error": "Source or target node not found"}
        
        if not source.blender_objects or not target.blender_objects:
            return {"ok": False, "error": "Nodes have no Blender objects"}
        
        # Resolve world positions of sockets
        source_pos = await self._get_socket_world_position(
            source.blender_objects[0],
            rel.source_anchor.socket_type,
            task_id,
        )
        target_pos = await self._get_socket_world_position(
            target.blender_objects[0],
            rel.target_anchor.socket_type,
            task_id,
        )
        
        if not source_pos or not target_pos:
            return {"ok": False, "error": "Could not resolve socket positions"}
        
        rel.source_anchor.world_position = source_pos
        rel.target_anchor.world_position = target_pos
        
        # Create connector geometry if needed
        if rel.connector_type != "none":
            connector_result = await self._create_connector(
                rel, source_pos, target_pos, task_id
            )
            if connector_result.get("ok"):
                rel.connector_object = connector_result.get("name")
        
        rel.verified = True
        logger.info(f"[{task_id}] Resolved relationship {rel.relationship_id}")
        
        return {
            "ok": True,
            "source_position": source_pos,
            "target_position": target_pos,
            "connector": rel.connector_object,
        }

    async def _get_socket_world_position(
        self,
        obj_name: str,
        socket_type: str,
        task_id: str,
    ) -> Optional[List[float]]:
        """Get world position of a socket on an object."""
        if not self.mcp_manager:
            # Mock: return origin
            return [0.0, 0.0, 0.0]
        
        from core.blender_ops import parse_op_output
        
        script = f'''
import bpy
import json
from mathutils import Vector

obj = bpy.data.objects.get({repr(obj_name)})
if not obj:
    res = {{"ok": False, "error": "not_found"}}
else:
    # Get bounding box in world space
    bbox = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    
    min_co = [min(v[i] for v in bbox) for i in range(3)]
    max_co = [max(v[i] for v in bbox) for i in range(3)]
    center = [(min_co[i] + max_co[i]) / 2 for i in range(3)]
    
    socket_type = {repr(socket_type)}
    
    # Compute socket position based on type
    if socket_type == "top_center":
        pos = [center[0], center[1], max_co[2]]
    elif socket_type == "bottom_center":
        pos = [center[0], center[1], min_co[2]]
    elif socket_type == "front_center":
        pos = [center[0], max_co[1], center[2]]
    elif socket_type == "back_center":
        pos = [center[0], min_co[1], center[2]]
    elif socket_type == "left_center":
        pos = [min_co[0], center[1], center[2]]
    elif socket_type == "right_center":
        pos = [max_co[0], center[1], center[2]]
    else:
        pos = center  # Default to center
    
    res = {{"ok": True, "position": [round(p, 4) for p in pos]}}

print("SENTINEL_OUTPUT_START" + json.dumps(res) + "SENTINEL_OUTPUT_END")
'''
        try:
            result = await self.mcp_manager.call_locked(
                "blender", "execute_blender_code", {"code": script}
            )
            data = parse_op_output(result.get("output", ""))
            return data.get("position") if data.get("ok") else None
        except Exception as e:
            logger.warning(f"[{task_id}] Socket position query failed: {e}")
            return None

    async def _create_connector(
        self,
        rel: CrossAssemblyRelationship,
        source_pos: List[float],
        target_pos: List[float],
        task_id: str,
    ) -> Dict[str, Any]:
        """Create connector geometry between two points."""
        if not self.mcp_manager:
            return {"ok": True, "name": f"connector_{rel.relationship_id}", "mock": True}
        
        from core.blender_ops import parse_op_output
        import math
        
        # Calculate midpoint and length
        mid = [(source_pos[i] + target_pos[i]) / 2 for i in range(3)]
        dx = target_pos[0] - source_pos[0]
        dy = target_pos[1] - source_pos[1]
        dz = target_pos[2] - source_pos[2]
        length = math.sqrt(dx*dx + dy*dy + dz*dz)
        
        connector_name = f"connector_{rel.relationship_id}"
        
        if rel.connector_type == "rod":
            # Create cylinder between points
            script = f'''
import bpy
import json
import math
from mathutils import Vector

# Create cylinder
bpy.ops.mesh.primitive_cylinder_add(
    radius=0.01,
    depth={length},
    location={mid}
)
obj = bpy.context.active_object
obj.name = {repr(connector_name)}

# Orient to point from source to target
direction = Vector({target_pos}) - Vector({source_pos})
obj.rotation_euler = direction.to_track_quat('Z', 'Y').to_euler()

res = {{"ok": True, "name": obj.name}}
print("SENTINEL_OUTPUT_START" + json.dumps(res) + "SENTINEL_OUTPUT_END")
'''
        elif rel.connector_type == "cable":
            # Create thin cylinder (cable)
            script = f'''
import bpy
import json
from mathutils import Vector

bpy.ops.mesh.primitive_cylinder_add(
    radius=0.005,
    depth={length},
    location={mid}
)
obj = bpy.context.active_object
obj.name = {repr(connector_name)}

direction = Vector({target_pos}) - Vector({source_pos})
obj.rotation_euler = direction.to_track_quat('Z', 'Y').to_euler()

res = {{"ok": True, "name": obj.name}}
print("SENTINEL_OUTPUT_START" + json.dumps(res) + "SENTINEL_OUTPUT_END")
'''
        else:
            # Default: create edge/line (beam)
            script = f'''
import bpy
import json
import bmesh

mesh = bpy.data.meshes.new({repr(connector_name)})
obj = bpy.data.objects.new({repr(connector_name)}, mesh)
bpy.context.collection.objects.link(obj)

bm = bmesh.new()
v1 = bm.verts.new({source_pos})
v2 = bm.verts.new({target_pos})
bm.edges.new((v1, v2))
bm.to_mesh(mesh)
bm.free()

res = {{"ok": True, "name": obj.name}}
print("SENTINEL_OUTPUT_START" + json.dumps(res) + "SENTINEL_OUTPUT_END")
'''
        
        try:
            result = await self.mcp_manager.call_locked(
                "blender", "execute_blender_code", {"code": script}
            )
            return parse_op_output(result.get("output", ""))
        except Exception as e:
            logger.error(f"[{task_id}] Connector creation failed: {e}")
            return {"ok": False, "error": str(e)}

    def get_relationships_for_node(self, node_id: str) -> List[CrossAssemblyRelationship]:
        """Get all relationships involving a specific node."""
        return [
            rel for rel in self.relationships.values()
            if rel.source_anchor.node_id == node_id or rel.target_anchor.node_id == node_id
        ]

    def to_dict(self) -> Dict[str, Any]:
        """Serialize relationships for checkpoint."""
        return {
            rel_id: {
                "source_node": rel.source_anchor.node_id,
                "source_socket": rel.source_anchor.socket_type,
                "target_node": rel.target_anchor.node_id,
                "target_socket": rel.target_anchor.socket_type,
                "connector_type": rel.connector_type,
                "connector_object": rel.connector_object,
                "verified": rel.verified,
            }
            for rel_id, rel in self.relationships.items()
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any], mcp_manager: Any = None) -> "RelationshipGraph":
        """Restore from checkpoint."""
        graph = cls(mcp_manager=mcp_manager)
        for rel_id, rel_data in data.items():
            graph.relationships[rel_id] = CrossAssemblyRelationship(
                relationship_id=rel_id,
                source_anchor=SocketAnchor(
                    node_id=rel_data["source_node"],
                    socket_type=rel_data["source_socket"],
                ),
                target_anchor=SocketAnchor(
                    node_id=rel_data["target_node"],
                    socket_type=rel_data["target_socket"],
                ),
                connector_type=rel_data.get("connector_type", "none"),
                connector_object=rel_data.get("connector_object"),
                verified=rel_data.get("verified", False),
            )
        return graph
