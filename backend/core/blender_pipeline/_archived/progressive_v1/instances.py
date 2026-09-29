"""Instance Manager — handles definition vs placement for repeated geometry.

Blueprint reference: §14 (Instance Definitions).
- Build definition geometry once, create N placements via mesh copy
- Instance nodes have `instance_of` pointing to definition `node_id`
- Definition is built and verified once; instances only need placement verification
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .manifest import BuildManifest, ManifestNode, NodeState
from .node_types import NodeKind

logger = logging.getLogger(__name__)


class InstanceManager:
    """Manages instance definitions and placements for repeated geometry."""

    def __init__(self, mcp_manager: Optional[Any] = None):
        self.mcp_manager = mcp_manager

    def detect_instance_candidates(self, manifest: BuildManifest) -> Dict[str, List[str]]:
        """Find nodes that could share a definition (same label pattern, same parent type).
        
        Returns: {definition_label: [node_ids that could be instances]}
        """
        candidates: Dict[str, List[str]] = {}
        
        for node_id, node in manifest.nodes.items():
            if node.kind != NodeKind.PART:
                continue
            
            # Normalize label to find duplicates (e.g., "leg_1", "leg_2" -> "leg")
            base_label = self._normalize_label(node.label)
            if base_label not in candidates:
                candidates[base_label] = []
            candidates[base_label].append(node_id)
        
        # Only return groups with 2+ potential instances
        return {k: v for k, v in candidates.items() if len(v) >= 2}

    def _normalize_label(self, label: str) -> str:
        """Strip numeric suffixes to find base label."""
        import re
        # Remove trailing _N, _NN, -N, -NN patterns
        return re.sub(r'[_-]?\d+$', '', label.lower().strip())

    def create_definition_node(
        self,
        manifest: BuildManifest,
        base_label: str,
        instance_node_ids: List[str],
    ) -> Optional[str]:
        """Create a definition node that instances will reference.
        
        Returns the definition node_id, or None if creation failed.
        """
        if not instance_node_ids:
            return None
        
        # Use first instance as the template for the definition
        template_node = manifest.nodes.get(instance_node_ids[0])
        if not template_node:
            return None
        
        definition_id = f"{manifest.model_id}_def_{base_label}"
        
        # Check if definition already exists
        if definition_id in manifest.nodes:
            return definition_id
        
        definition_node = ManifestNode(
            node_id=definition_id,
            label=f"{base_label}_definition",
            kind=NodeKind.DEFINITION,
            state=NodeState.PLANNED,
            parent_id=template_node.parent_id,
            stage_outputs=dict(template_node.stage_outputs),
        )
        manifest.add_node(definition_node)
        
        # Mark instance nodes as instances of this definition
        for inst_id in instance_node_ids:
            if inst_id in manifest.nodes:
                manifest.nodes[inst_id].instance_of = definition_id
                manifest.nodes[inst_id].kind = NodeKind.INSTANCE
        
        logger.info(f"Created definition '{definition_id}' with {len(instance_node_ids)} instances")
        return definition_id

    async def build_instance_from_definition(
        self,
        instance_node: ManifestNode,
        manifest: BuildManifest,
        task_id: str = "adhoc",
    ) -> Dict[str, Any]:
        """Create an instance by copying the definition's geometry.
        
        The definition must already be VERIFIED with blender_objects populated.
        """
        if not instance_node.instance_of:
            return {"ok": False, "error": "Node is not an instance"}
        
        definition = manifest.nodes.get(instance_node.instance_of)
        if not definition:
            return {"ok": False, "error": f"Definition '{instance_node.instance_of}' not found"}
        
        if definition.state != NodeState.VERIFIED:
            return {"ok": False, "error": f"Definition not verified (state={definition.state})"}
        
        if not definition.blender_objects:
            return {"ok": False, "error": "Definition has no Blender objects"}
        
        if not self.mcp_manager:
            # Mock mode
            instance_node.blender_objects = [f"inst_{instance_node.label}"]
            return {"ok": True, "mock": True}
        
        # Copy definition geometry with new transform
        source_obj = definition.blender_objects[0]
        instance_name = f"inst_{instance_node.node_id}"
        
        # Get instance-specific transform from stage4
        location = instance_node.stage_outputs.get("stage4", {}).get("location", [0, 0, 0])
        rotation = instance_node.stage_outputs.get("stage4", {}).get("rotation", [0, 0, 0])
        
        from core.blender_ops import parse_op_output
        
        script = f'''
import bpy
import json

src = bpy.data.objects.get({repr(source_obj)})
if not src:
    res = {{"ok": False, "error": "source_not_found"}}
else:
    # Duplicate object
    new_obj = src.copy()
    new_obj.data = src.data.copy()
    new_obj.name = {repr(instance_name)}
    
    # Apply instance transform
    new_obj.location = {location}
    new_obj.rotation_euler = {rotation}
    
    # Link to same collection as source
    for coll in src.users_collection:
        coll.objects.link(new_obj)
        break
    
    res = {{"ok": True, "name": new_obj.name}}

print("SENTINEL_OUTPUT_START" + json.dumps(res) + "SENTINEL_OUTPUT_END")
'''
        try:
            result = await self.mcp_manager.call_locked(
                "blender", "execute_blender_code", {"code": script}
            )
            data = parse_op_output(result.get("output", ""))
            
            if data.get("ok"):
                instance_node.blender_objects = [data.get("name", instance_name)]
            
            return data
        except Exception as e:
            logger.error(f"[{task_id}] Instance creation failed: {e}")
            return {"ok": False, "error": str(e)}

    def is_instance(self, node: ManifestNode) -> bool:
        """Check if a node is an instance (has instance_of set)."""
        return bool(node.instance_of)

    def get_definition(self, node: ManifestNode, manifest: BuildManifest) -> Optional[ManifestNode]:
        """Get the definition node for an instance."""
        if not node.instance_of:
            return None
        return manifest.nodes.get(node.instance_of)
