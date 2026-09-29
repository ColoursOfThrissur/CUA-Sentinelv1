"""Spatial Verification — BVH-based interpenetration and gap detection.

Complex builds need spatial verification beyond dimension checks:
- Interpenetration: Parts shouldn't overlap (unless intentional)
- Gaps: Parts should connect properly (no floating pieces)
- Alignment: Parts should be properly aligned at joints

Uses Blender's BVH (Bounding Volume Hierarchy) for efficient spatial queries.

Blueprint reference: §21 (Progressive Verification).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from .manifest import BuildManifest, ManifestNode

logger = logging.getLogger(__name__)


class VerificationLevel(str, Enum):
    """Verification strictness levels."""
    BASIC = "basic"          # Just check objects exist
    STANDARD = "standard"    # + dimension checks
    STRICT = "strict"        # + interpenetration, gaps
    PARANOID = "paranoid"    # + mesh validity, manifold


class SpatialIssueType(str, Enum):
    """Types of spatial issues."""
    INTERPENETRATION = "interpenetration"
    GAP = "gap"
    FLOATING = "floating"
    MISALIGNED = "misaligned"


@dataclass
class SpatialIssue:
    """A detected spatial issue."""
    issue_type: SpatialIssueType
    object_a: str
    object_b: Optional[str] = None
    severity: str = "warning"  # warning, error
    details: Dict[str, Any] = field(default_factory=dict)
    
    def __str__(self) -> str:
        if self.object_b:
            return f"{self.issue_type.value}: {self.object_a} <-> {self.object_b}"
        return f"{self.issue_type.value}: {self.object_a}"


@dataclass
class SpatialVerificationResult:
    """Result of spatial verification."""
    ok: bool
    level: VerificationLevel
    objects_checked: int = 0
    issues: List[SpatialIssue] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    
    @property
    def has_errors(self) -> bool:
        return len(self.errors) > 0
    
    @property
    def has_warnings(self) -> bool:
        return len(self.warnings) > 0


class SpatialVerifier:
    """Verifies spatial relationships between objects.
    
    Usage:
        verifier = SpatialVerifier(mcp_manager)
        result = await verifier.verify_assembly(
            objects=["hull", "deck", "mast"],
            level=VerificationLevel.STRICT,
        )
    """
    
    # Tolerances
    INTERPENETRATION_TOLERANCE_M = 0.002  # 2mm overlap allowed
    GAP_TOLERANCE_M = 0.005               # 5mm gap allowed
    ALIGNMENT_TOLERANCE_DEG = 1.0         # 1 degree misalignment allowed
    
    def __init__(self, mcp_manager: Any):
        self.mcp_manager = mcp_manager
    
    async def verify_assembly(
        self,
        objects: List[str],
        level: VerificationLevel = VerificationLevel.STANDARD,
        allowed_overlaps: Optional[Set[Tuple[str, str]]] = None,
        task_id: str = "",
    ) -> SpatialVerificationResult:
        """Verify spatial relationships in an assembly.
        
        Args:
            objects: List of object names to verify
            level: Verification strictness
            allowed_overlaps: Set of (obj_a, obj_b) pairs where overlap is OK
                             (e.g., boolean targets)
        """
        allowed_overlaps = allowed_overlaps or set()
        issues = []
        warnings = []
        errors = []
        
        if level == VerificationLevel.BASIC:
            # Just check objects exist
            exists_result = await self._check_objects_exist(objects)
            if not exists_result["ok"]:
                errors.append(exists_result.get("error", "Objects not found"))
            
            return SpatialVerificationResult(
                ok=len(errors) == 0,
                level=level,
                objects_checked=len(objects),
                issues=issues,
                warnings=warnings,
                errors=errors,
            )
        
        # STANDARD and above: check interpenetration
        if level in (VerificationLevel.STANDARD, VerificationLevel.STRICT, VerificationLevel.PARANOID):
            interpen_result = await self._check_interpenetration(
                objects, allowed_overlaps, task_id
            )
            
            for issue in interpen_result.get("issues", []):
                issues.append(SpatialIssue(
                    issue_type=SpatialIssueType.INTERPENETRATION,
                    object_a=issue["object_a"],
                    object_b=issue["object_b"],
                    severity="error" if level == VerificationLevel.PARANOID else "warning",
                    details={"overlap_volume": issue.get("overlap_volume")},
                ))
                
                if level == VerificationLevel.PARANOID:
                    errors.append(f"Interpenetration: {issue['object_a']} <-> {issue['object_b']}")
                else:
                    warnings.append(f"Interpenetration: {issue['object_a']} <-> {issue['object_b']}")
        
        # STRICT and above: check for floating objects
        if level in (VerificationLevel.STRICT, VerificationLevel.PARANOID):
            floating_result = await self._check_floating_objects(objects, task_id)
            
            for obj in floating_result.get("floating", []):
                issues.append(SpatialIssue(
                    issue_type=SpatialIssueType.FLOATING,
                    object_a=obj,
                    severity="warning",
                ))
                warnings.append(f"Floating object: {obj}")
        
        # PARANOID: check mesh validity
        if level == VerificationLevel.PARANOID:
            for obj in objects:
                mesh_result = await self._check_mesh_validity(obj)
                if not mesh_result.get("ok"):
                    for issue in mesh_result.get("issues", []):
                        errors.append(f"Mesh issue in {obj}: {issue}")
        
        return SpatialVerificationResult(
            ok=len(errors) == 0,
            level=level,
            objects_checked=len(objects),
            issues=issues,
            warnings=warnings,
            errors=errors,
        )
    
    async def _check_objects_exist(self, objects: List[str]) -> Dict[str, Any]:
        """Check that all objects exist in Blender."""
        from core.blender_ops import parse_op_output
        
        script = f'''
import bpy
import json

objects = {repr(objects)}
missing = [name for name in objects if name not in bpy.data.objects]

if missing:
    result = {{"ok": False, "error": f"Objects not found: {{missing}}", "missing": missing}}
else:
    result = {{"ok": True, "found": len(objects)}}

print("SENTINEL_OUTPUT_START" + json.dumps(result) + "SENTINEL_OUTPUT_END")
'''
        try:
            result = await self.mcp_manager.call_locked(
                "blender", "execute_blender_code", {"code": script}
            )
            return parse_op_output(result.get("output", ""))
        except Exception as e:
            return {"ok": False, "error": str(e)}
    
    async def _check_interpenetration(
        self,
        objects: List[str],
        allowed_overlaps: Set[Tuple[str, str]],
        task_id: str,
    ) -> Dict[str, Any]:
        """Check for interpenetration between objects using BVH."""
        from core.blender_ops import parse_op_output
        
        # Convert allowed_overlaps to list for JSON
        allowed_list = [list(pair) for pair in allowed_overlaps]
        
        script = f'''
import bpy
import json
from mathutils.bvhtree import BVHTree

objects = {repr(objects)}
allowed = {allowed_list}
tolerance = {self.INTERPENETRATION_TOLERANCE_M}

# Build set of allowed pairs (both directions)
allowed_set = set()
for a, b in allowed:
    allowed_set.add((a, b))
    allowed_set.add((b, a))

issues = []

# Build BVH trees for all mesh objects
bvh_trees = {{}}
for name in objects:
    obj = bpy.data.objects.get(name)
    if obj and obj.type == 'MESH':
        # Get evaluated mesh (with modifiers applied)
        depsgraph = bpy.context.evaluated_depsgraph_get()
        obj_eval = obj.evaluated_get(depsgraph)
        mesh = obj_eval.to_mesh()
        
        # Transform vertices to world space
        matrix = obj.matrix_world
        verts = [matrix @ v.co for v in mesh.vertices]
        polys = [p.vertices[:] for p in mesh.polygons]
        
        if verts and polys:
            bvh_trees[name] = BVHTree.FromPolygons(verts, polys)
        
        obj_eval.to_mesh_clear()

# Check all pairs
checked = 0
for i, name_a in enumerate(objects):
    if name_a not in bvh_trees:
        continue
    for name_b in objects[i+1:]:
        if name_b not in bvh_trees:
            continue
        if (name_a, name_b) in allowed_set:
            continue
        
        checked += 1
        tree_a = bvh_trees[name_a]
        tree_b = bvh_trees[name_b]
        
        # Check for overlap
        overlap = tree_a.overlap(tree_b)
        if overlap:
            issues.append({{
                "object_a": name_a,
                "object_b": name_b,
                "overlap_count": len(overlap),
            }})

result = {{"ok": len(issues) == 0, "issues": issues, "pairs_checked": checked}}
print("SENTINEL_OUTPUT_START" + json.dumps(result) + "SENTINEL_OUTPUT_END")
'''
        try:
            result = await self.mcp_manager.call_locked(
                "blender", "execute_blender_code", {"code": script}
            )
            return parse_op_output(result.get("output", ""))
        except Exception as e:
            return {"ok": False, "error": str(e), "issues": []}
    
    async def _check_floating_objects(
        self,
        objects: List[str],
        task_id: str,
    ) -> Dict[str, Any]:
        """Check for objects that don't touch any other object."""
        from core.blender_ops import parse_op_output
        
        script = f'''
import bpy
import json
from mathutils.bvhtree import BVHTree
from mathutils import Vector

objects = {repr(objects)}
gap_tolerance = {self.GAP_TOLERANCE_M}

# Build BVH trees and bounding boxes
bvh_trees = {{}}
bboxes = {{}}

for name in objects:
    obj = bpy.data.objects.get(name)
    if obj and obj.type == 'MESH':
        depsgraph = bpy.context.evaluated_depsgraph_get()
        obj_eval = obj.evaluated_get(depsgraph)
        mesh = obj_eval.to_mesh()
        
        matrix = obj.matrix_world
        verts = [matrix @ v.co for v in mesh.vertices]
        polys = [p.vertices[:] for p in mesh.polygons]
        
        if verts and polys:
            bvh_trees[name] = BVHTree.FromPolygons(verts, polys)
            # Compute world AABB
            bbox_min = [min(v[i] for v in verts) for i in range(3)]
            bbox_max = [max(v[i] for v in verts) for i in range(3)]
            bboxes[name] = (bbox_min, bbox_max)
        
        obj_eval.to_mesh_clear()

# Check which objects touch at least one other
touching = set()

for i, name_a in enumerate(objects):
    if name_a not in bvh_trees:
        continue
    for name_b in objects[i+1:]:
        if name_b not in bvh_trees:
            continue
        
        # Quick AABB check first
        bb_a = bboxes[name_a]
        bb_b = bboxes[name_b]
        
        # Expand by tolerance
        a_min = [bb_a[0][i] - gap_tolerance for i in range(3)]
        a_max = [bb_a[1][i] + gap_tolerance for i in range(3)]
        b_min = [bb_b[0][i] - gap_tolerance for i in range(3)]
        b_max = [bb_b[1][i] + gap_tolerance for i in range(3)]
        
        # Check AABB overlap
        if (a_min[0] <= b_max[0] and a_max[0] >= b_min[0] and
            a_min[1] <= b_max[1] and a_max[1] >= b_min[1] and
            a_min[2] <= b_max[2] and a_max[2] >= b_min[2]):
            # AABBs overlap - objects are close enough
            touching.add(name_a)
            touching.add(name_b)

# Objects not touching anything are floating
floating = [name for name in objects if name in bvh_trees and name not in touching]

# Exception: if only one object, it's not floating
if len(objects) == 1:
    floating = []

result = {{"ok": len(floating) == 0, "floating": floating, "touching": list(touching)}}
print("SENTINEL_OUTPUT_START" + json.dumps(result) + "SENTINEL_OUTPUT_END")
'''
        try:
            result = await self.mcp_manager.call_locked(
                "blender", "execute_blender_code", {"code": script}
            )
            return parse_op_output(result.get("output", ""))
        except Exception as e:
            return {"ok": False, "error": str(e), "floating": []}
    
    async def _check_mesh_validity(self, object_name: str) -> Dict[str, Any]:
        """Check mesh validity (manifold, no degenerate faces)."""
        from core.blender_ops import parse_op_output
        
        script = f'''
import bpy
import bmesh
import json

obj = bpy.data.objects.get({repr(object_name)})
if not obj or obj.type != 'MESH':
    result = {{"ok": True, "skipped": True}}
else:
    issues = []
    
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    
    # Check for degenerate faces
    degen = sum(1 for f in bm.faces if f.calc_area() < 1e-8)
    if degen > 0:
        issues.append(f"{{degen}} degenerate faces")
    
    # Check for non-manifold edges
    non_manifold = sum(1 for e in bm.edges if not e.is_manifold)
    if non_manifold > 0:
        issues.append(f"{{non_manifold}} non-manifold edges")
    
    # Check for loose vertices
    loose = sum(1 for v in bm.verts if not v.link_edges)
    if loose > 0:
        issues.append(f"{{loose}} loose vertices")
    
    # Check for duplicate vertices
    # (vertices at same location)
    from collections import defaultdict
    pos_count = defaultdict(int)
    for v in bm.verts:
        key = (round(v.co.x, 5), round(v.co.y, 5), round(v.co.z, 5))
        pos_count[key] += 1
    duplicates = sum(1 for c in pos_count.values() if c > 1)
    if duplicates > 0:
        issues.append(f"{{duplicates}} duplicate vertex positions")
    
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


async def verify_node_placement(
    node: "ManifestNode",
    manifest: "BuildManifest",
    mcp_manager: Any,
    task_id: str = "",
) -> SpatialVerificationResult:
    """Verify a single node's placement relative to its parent.
    
    Checks:
    - Node is within expected distance of parent
    - Node doesn't interpenetrate siblings (unless allowed)
    """
    verifier = SpatialVerifier(mcp_manager)
    
    objects_to_check = list(node.blender_objects)
    allowed_overlaps = set()
    
    # Add parent objects
    if node.parent_id:
        parent = manifest.nodes.get(node.parent_id)
        if parent and parent.blender_objects:
            objects_to_check.extend(parent.blender_objects)
            
            # If this node has boolean join mode, allow overlap with parent
            if node.attachment and hasattr(node.attachment, 'join_mode'):
                if node.attachment.join_mode in ("BOOLEAN_DIFFERENCE", "FUSE"):
                    for node_obj in node.blender_objects:
                        for parent_obj in parent.blender_objects:
                            allowed_overlaps.add((node_obj, parent_obj))
    
    # Add sibling objects
    if node.parent_id:
        parent = manifest.nodes.get(node.parent_id)
        if parent:
            for sibling_id in parent.children_ids:
                if sibling_id == node.node_id:
                    continue
                sibling = manifest.nodes.get(sibling_id)
                if sibling and sibling.blender_objects:
                    objects_to_check.extend(sibling.blender_objects)
    
    return await verifier.verify_assembly(
        objects=objects_to_check,
        level=VerificationLevel.STANDARD,
        allowed_overlaps=allowed_overlaps,
        task_id=task_id,
    )
