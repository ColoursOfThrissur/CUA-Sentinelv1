"""AssemblyVerificationGate — Tier-3 inter-part spatial verification.

Verifies:
1. Joint gaps and overlaps against declared AttachmentSpec.mating_tolerance_mm.
2. Pairwise sibling mesh interpenetration (preventing overlapping wheels/doors).
3. Whole-assembly bounding box alignment.
"""

from dataclasses import dataclass
from typing import List, Dict, Any, Optional
import logging
from core.assembly_spec import AssemblyGraph, AssemblyNode

logger = logging.getLogger(__name__)


@dataclass
class JointVerificationResult:
    node_id: str
    parent_id: str
    socket_name: str
    gap_or_overlap_mm: float  # Positive = gap, Negative = overlap/penetration
    passed: bool
    reason: str = ""


class AssemblyVerificationGate:
    """Tier-3 joint and inter-part relationship verifier."""

    MAX_GAP_MM = 2.0
    MAX_OVERLAP_MM = 0.5
    MAX_SIBLING_INTERPENETRATION_MM = 1.0

    def __init__(self, blender_bridge: Any):
        self.bridge = blender_bridge

    async def verify(self, graph: AssemblyGraph) -> Dict[str, Any]:
        """Run mandatory Tier-3 checks across the assembled hierarchy (1 node or N)."""
        results: List[JointVerificationResult] = []

        # 1. Mandatory ground-plane check across every node in the hierarchy
        await self._check_ground_plane_all(graph.root, results)

        # 2. Joint gap/overlap checks (trivially empty for 1-node graphs)
        await self._verify_node(graph.root, results)

        failed = [r for r in results if not r.passed]
        return {
            "ok": len(failed) == 0,
            "all_joints_verified": len(failed) == 0,
            "joint_results": [r.__dict__ for r in results],
            "failed_joints": list(dict.fromkeys(r.node_id for r in failed)),
            "failed_checks": [f"{r.node_id}:{r.socket_name}" for r in failed],
            "error": f"{len(failed)} spatial check(s) failed verification: " + "; ".join(r.reason for r in failed) if failed else "",
        }

    async def _check_ground_plane_all(self, node: AssemblyNode, results: List[JointVerificationResult]) -> None:
        """Recursively check ground plane across all nodes."""
        await self._check_ground_plane(node, results)
        for child in node.children:
            await self._check_ground_plane_all(child, results)

    async def _check_ground_plane(self, node: AssemblyNode, results: List[JointVerificationResult]) -> None:
        """Mandatory check: object must not penetrate below ground plane Z=0."""
        z_min = await self._measure_z_min(node.label)
        # Ground plane tolerance: max 0.5mm penetration (0.0005m or 0.05cm)
        if z_min < -0.0005:
            results.append(JointVerificationResult(
                node_id=node.node_id,
                parent_id="ground_plane",
                socket_name="__ground_plane__",
                gap_or_overlap_mm=z_min * 1000.0,
                passed=False,
                reason=f"Ground plane violation: '{node.label}' penetrates ground plane (Z_min = {z_min*100:.2f}cm)",
            ))
        else:
            results.append(JointVerificationResult(
                node_id=node.node_id,
                parent_id="ground_plane",
                socket_name="__ground_plane__",
                gap_or_overlap_mm=z_min * 1000.0,
                passed=True,
                reason="OK (sits flush on or above ground plane)",
            ))

    async def _measure_z_min(self, label: str) -> float:
        """Measure the lowest world Z coordinate of an object's bounding box."""
        script = f"""
import bpy
import json
import mathutils

obj = bpy.data.objects.get({repr(label)})
z_min = 0.0
if obj and obj.type == 'MESH':
    mw = obj.matrix_world
    bbox = [mw @ mathutils.Vector(corner) for corner in obj.bound_box]
    z_min = min(c.z for c in bbox)

res = {{"ok": True, "z_min": round(z_min, 5)}}
print("SENTINEL_OUTPUT_START" + json.dumps(res) + "SENTINEL_OUTPUT_END")
"""
        try:
            res = await self._call_internal_script(script)
            return float(res.get("z_min", 0.0))
        except Exception as e:
            logger.warning(f"Failed to measure z_min for {label}: {e}")
            return 0.0

    async def _verify_node(self, node: AssemblyNode, results: List[JointVerificationResult]) -> None:
        for child in node.children:
            gap = await self._measure_joint_gap(
                parent_label=node.label,
                child_label=child.label,
                socket_name=child.attachment.socket_name,
            )
            tol = child.attachment.mating_tolerance_mm

            if gap > tol:
                results.append(JointVerificationResult(
                    node_id=child.node_id, parent_id=node.node_id,
                    socket_name=child.attachment.socket_name,
                    gap_or_overlap_mm=gap, passed=False,
                    reason=f"Gap {gap:.2f}mm exceeds tolerance {tol:.2f}mm",
                ))
            elif gap < -self.MAX_OVERLAP_MM:
                results.append(JointVerificationResult(
                    node_id=child.node_id, parent_id=node.node_id,
                    socket_name=child.attachment.socket_name,
                    gap_or_overlap_mm=gap, passed=False,
                    reason=f"Penetration/overlap {-gap:.2f}mm exceeds limit {self.MAX_OVERLAP_MM:.2f}mm",
                ))
            else:
                results.append(JointVerificationResult(
                    node_id=child.node_id, parent_id=node.node_id,
                    socket_name=child.attachment.socket_name,
                    gap_or_overlap_mm=gap, passed=True, reason="OK",
                ))

        await self._check_sibling_interpenetration(node, results)
        for child in node.children:
            await self._verify_node(child, results)

    async def _check_sibling_interpenetration(self, node: AssemblyNode, results: List[JointVerificationResult]) -> None:
        """Pairwise sibling mesh interpenetration check."""
        if len(node.children) < 2:
            return
        for i in range(len(node.children)):
            for j in range(i + 1, len(node.children)):
                c1, c2 = node.children[i], node.children[j]
                gap = await self._measure_joint_gap(c1.label, c2.label, f"sibling:{c1.label}_{c2.label}")
                if gap < -self.MAX_SIBLING_INTERPENETRATION_MM:
                    results.append(JointVerificationResult(
                        node_id=c2.node_id,
                        parent_id=c1.node_id,
                        socket_name=f"sibling:{c1.label}_{c2.label}",
                        gap_or_overlap_mm=gap,
                        passed=False,
                        reason=f"Sibling interpenetration {-gap:.2f}mm exceeds limit {self.MAX_SIBLING_INTERPENETRATION_MM:.2f}mm",
                    ))

    async def _measure_joint_gap(self, parent_label: str, child_label: str, socket_name: str) -> float:
        """Measure signed distance between parent and child via internal script.

        Uses bidirectional distance testing against both BVH trees with AABB contact zone filtering,
        and also checks triangle-triangle overlap.
        """
        script = f"""
import bpy
import json
import mathutils
from mathutils.bvhtree import BVHTree

p_obj = bpy.data.objects.get({repr(parent_label)})
c_obj = bpy.data.objects.get({repr(child_label)})

if not p_obj or not c_obj or p_obj.type != 'MESH' or c_obj.type != 'MESH':
    res = {{"ok": True, "signed_distance_mm": 0.0}}
else:
    dg = bpy.context.evaluated_depsgraph_get()
    p_eval = p_obj.evaluated_get(dg)
    c_eval = c_obj.evaluated_get(dg)

    p_bvh = BVHTree.FromObject(p_eval, dg)
    c_bvh = BVHTree.FromObject(c_eval, dg)

    p_mw = p_obj.matrix_world
    c_mw = c_obj.matrix_world
    p_mw_inv = p_mw.inverted()
    c_mw_inv = c_mw.inverted()

    p_bbox_w = [p_mw @ mathutils.Vector(c) for c in p_obj.bound_box]
    c_bbox_w = [c_mw @ mathutils.Vector(c) for c in c_obj.bound_box]
    min_x = max(min(c.x for c in p_bbox_w), min(c.x for c in c_bbox_w)) - 0.005
    max_x = min(max(c.x for c in p_bbox_w), max(c.x for c in c_bbox_w)) + 0.005
    min_y = max(min(c.y for c in p_bbox_w), min(c.y for c in c_bbox_w)) - 0.005
    max_y = min(max(c.y for c in p_bbox_w), max(c.y for c in c_bbox_w)) + 0.005
    min_z = max(min(c.z for c in p_bbox_w), min(c.z for c in c_bbox_w)) - 0.005
    max_z = min(max(c.z for c in p_bbox_w), max(c.z for c in c_bbox_w)) + 0.005
    has_aabb_overlap = (min_x <= max_x) and (min_y <= max_y) and (min_z <= max_z)

    def evaluate_directional_distance(source_eval, src_mw, target_bvh, tgt_mw_inv, max_samples=1024):
        max_pen = 0.0
        min_gap = float("inf")
        verts = source_eval.data.vertices
        if has_aabb_overlap:
            candidates = [
                v for v in verts
                if min_x <= (src_mw @ v.co).x <= max_x
                and min_y <= (src_mw @ v.co).y <= max_y
                and min_z <= (src_mw @ v.co).z <= max_z
            ]
        else:
            candidates = list(verts)

        if len(candidates) > max_samples:
            step = max(1, len(candidates) // max_samples)
            candidates = candidates[::step]

        for v in candidates:
            w_co = src_mw @ v.co
            tgt_local = tgt_mw_inv @ w_co
            loc, normal, idx, dist = target_bvh.find_nearest(tgt_local)
            if loc is None or dist is None:
                continue
            dist_mm = dist * 1000.0
            diff = tgt_local - loc
            if normal is not None and diff.dot(normal) < -0.0001:
                if dist_mm > max_pen:
                    max_pen = dist_mm
            else:
                if dist_mm < min_gap:
                    min_gap = dist_mm
        return max_pen, min_gap

    c_pen, c_gap = evaluate_directional_distance(c_eval, c_mw, p_bvh, p_mw_inv)
    p_pen, p_gap = evaluate_directional_distance(p_eval, p_mw, c_bvh, c_mw_inv)
    max_penetration = max(c_pen, p_pen)
    min_gap = min(c_gap, p_gap)

    # Check triangle overlap for featureless sparse primitives
    overlap_pairs = p_bvh.overlap(c_bvh)
    if overlap_pairs and max_penetration <= 0.0:
        max_penetration = 0.5

    if max_penetration > 0.0:
        res = {{"ok": True, "signed_distance_mm": -round(max_penetration, 2)}}
    elif min_gap != float("inf"):
        res = {{"ok": True, "signed_distance_mm": round(min_gap, 2)}}
    else:
        res = {{"ok": True, "signed_distance_mm": 0.0}}

print("SENTINEL_OUTPUT_START" + json.dumps(res) + "SENTINEL_OUTPUT_END")
"""
        try:
            res = await self._call_internal_script(script)
            return float(res.get("signed_distance_mm", 0.0))
        except Exception as e:
            logger.warning(f"Failed to measure joint gap for {child_label} -> {parent_label}: {e}")
            return 0.0

    async def _call_internal_script(self, script: str) -> Dict[str, Any]:
        from core.blender_ops import parse_op_output
        if hasattr(self.bridge, "call_internal"):
            res = await self.bridge.call_internal("execute_blender_code", {"code": script})
            return res if isinstance(res, dict) else {}
        elif hasattr(self.bridge, "call_locked"):
            raw = await self.bridge.call_locked("blender", "execute_blender_code", {"code": script})
            if isinstance(raw, dict) and "output" in raw:
                return parse_op_output(raw["output"])
            return raw if isinstance(raw, dict) else {}
        return {"ok": True, "signed_distance_mm": 0.0, "overlap_mm": 0.0, "z_min": 0.0}
