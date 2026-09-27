"""Two-Tier Geometric and Topological Verifier for 3D Specifications.

Tier 1: Pure Python in-memory verification on the spec object (<5ms).
         Runs before compilation to filter/rank candidates.

Tier 2: Post-headless verification that reads the metrics JSON produced
         by the headless runner and applies evaluated-mesh checks:
         - Level-feet: lowest vertex per leg within 5mm.
         - Contact via BVHTree (no bounding-box shortcuts).
         - Symmetry via KDTree — mirrored vertex within 1mm.
         - Manifold edge check.
         - Silhouette area ratios vs category priors.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union

from .schema import QuadrupedSpec, HardSurfaceSpec, VesselSpec, JointSpec, BoneSpec


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class VerificationResult:
    valid: bool
    score: float = 0.0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    repair_patches: Dict[str, Any] = field(default_factory=dict)
    metrics: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Tier 1 — pure Python
# ---------------------------------------------------------------------------

class SpecVerifier:
    """Tier 1: in-memory spec verification."""

    CATEGORY_DIMENSION_PRIORS: Dict[str, Dict[str, Tuple[float, float]]] = {
        "dining_table": {
            "height": (0.65, 0.85),
            "length": (0.80, 2.50),
            "width": (0.60, 1.40),
        },
        "coffee_table": {
            "height": (0.35, 0.55),
            "length": (0.60, 1.60),
            "width": (0.40, 1.00),
        },
        "ceramic_mug": {
            "height": (0.07, 0.15),
            "radius": (0.03, 0.07),
            "wall_thickness": (0.002, 0.01),
        },
        "quadruped": {
            "body_length": (0.30, 2.50),
            "withers_height": (0.20, 5.50),  # Allow giraffe
            "withers_to_length_ratio": (0.50, 3.50),  # Allow tall animals
        },
        "vehicle": {
            "length": (1.50, 5.50),
            "width": (0.80, 2.40),
            "height": (0.60, 2.20),
        },
    }

    # ----------------------------------------------------------------
    # Quadruped
    # ----------------------------------------------------------------

    @classmethod
    def verify_quadruped(cls, spec: QuadrupedSpec) -> VerificationResult:
        errors: List[str] = []
        warnings: List[str] = []
        repair_patches: Dict[str, Any] = {}
        metrics: Dict[str, Any] = {}
        score = 1.0

        joints_dict = {j.name: j for j in spec.joints}

        # 1. Centerline x = 0
        for j in spec.joints:
            if not j.name.endswith("_L") and not j.name.endswith("_R"):
                if abs(j.x) > 0.001:
                    errors.append(f"Centerline joint '{j.name}' must have x=0.0, got x={j.x:.4f}")
                    repair_patches[f"joints.{j.name}.x"] = 0.0
                    score -= 0.15

        # 2. Bone connectivity and non-zero length
        adjacency: Dict[str, List[str]] = {j.name: [] for j in spec.joints}
        for b in spec.bones:
            if b.parent not in joints_dict:
                errors.append(f"Bone references unknown parent joint '{b.parent}'")
                score -= 0.2
                continue
            if b.child not in joints_dict:
                errors.append(f"Bone references unknown child joint '{b.child}'")
                score -= 0.2
                continue

            pj, cj = joints_dict[b.parent], joints_dict[b.child]
            dist = math.sqrt((pj.x - cj.x) ** 2 + (pj.y - cj.y) ** 2 + (pj.z - cj.z) ** 2)
            if dist < 0.01:
                errors.append(f"Zero-length bone between '{b.parent}' and '{b.child}' (dist={dist:.4f}m)")
                score -= 0.2

            adjacency[b.parent].append(b.child)
            adjacency[b.child].append(b.parent)

        # 3. Graph connectivity (all joints reachable)
        if spec.joints:
            start = spec.joints[0].name
            visited: set = set()
            queue = [start]
            while queue:
                curr = queue.pop(0)
                if curr not in visited:
                    visited.add(curr)
                    for nbr in adjacency.get(curr, []):
                        if nbr not in visited:
                            queue.append(nbr)
            unconnected = set(joints_dict.keys()) - visited
            if unconnected:
                errors.append(f"Disconnected joints not in bone tree: {sorted(unconnected)}")
                score -= 0.3

        # 4. Level-feet (spec-level check — Tier 2 does evaluated-mesh level)
        paw_joints = [j for j in spec.joints if "paw" in j.name.lower() or "foot" in j.name.lower()]
        if paw_joints:
            paw_zs = [p.z for p in paw_joints]
            target_z = min(paw_zs)
            delta = max(paw_zs) - target_z
            metrics["paw_z_delta"] = delta
            if delta > 0.015:
                errors.append(
                    f"Unlevel paws detected: height delta {delta:.3f}m > 0.015m. Model will tilt."
                )
                score -= 0.25
                for p in paw_joints:
                    if abs(p.z - target_z) > 0.001:
                        repair_patches[f"joints.{p.name}.z"] = target_z

        # 5. Proportion priors
        if spec.body_length_m > 0:
            ratio = spec.withers_height_m / spec.body_length_m
            metrics["withers_to_length_ratio"] = ratio
            bounds = cls.CATEGORY_DIMENSION_PRIORS["quadruped"]["withers_to_length_ratio"]
            if not (bounds[0] <= ratio <= bounds[1]):
                warnings.append(
                    f"Withers-to-body-length ratio {ratio:.2f} outside prior {bounds}"
                )
                score -= 0.05

        return VerificationResult(
            valid=len(errors) == 0,
            score=max(0.0, score),
            errors=errors,
            warnings=warnings,
            repair_patches=repair_patches,
            metrics=metrics,
        )

    # ----------------------------------------------------------------
    # Hard-surface / vessel
    # ----------------------------------------------------------------

    @classmethod
    def verify_hard_surface(cls, spec: HardSurfaceSpec) -> VerificationResult:
        errors: List[str] = []
        warnings: List[str] = []
        repair_patches: Dict[str, Any] = {}
        metrics: Dict[str, Any] = {}
        score = 1.0

        parts_dict = {p.name: p for p in spec.parts}

        # 1. Relation references exist
        for rel in spec.relations:
            if rel.target_part not in parts_dict:
                errors.append(f"Relation references unknown target_part '{rel.target_part}'")
                score -= 0.2
            if rel.parent_part not in parts_dict:
                errors.append(f"Relation references unknown parent_part '{rel.parent_part}'")
                score -= 0.2

        # 2. Vessel hollow check
        spec_name = spec.name.lower()
        if spec.category == "vessel" or any(w in spec_name for w in ("mug", "cup", "bowl", "glass", "vase")):
            has_hollow = any(
                any(m.type == "SOLIDIFY" for m in p.modifiers) or p.end_fill_type == "NOTHING"
                for p in spec.parts
            )
            if not has_hollow:
                warnings.append("Vessel body lacks SOLIDIFY modifier or open cap — may produce solid mesh.")
                score -= 0.15

        # 3. Table dimension priors
        if spec.category == "furniture" and "table" in spec_name:
            prior = cls.CATEGORY_DIMENSION_PRIORS["dining_table"]
            top_part = next((p for p in spec.parts if "top" in p.name.lower()), None)
            if top_part and len(top_part.size) >= 2:
                table_len = max(top_part.size[:2])
                table_wid = min(top_part.size[:2])
                metrics["table_length"] = table_len
                metrics["table_width"] = table_wid
                if not (prior["length"][0] <= table_len <= prior["length"][1]):
                    warnings.append(
                        f"Tabletop length {table_len:.2f}m outside prior {prior['length']}"
                    )
                    score -= 0.05

        return VerificationResult(
            valid=len(errors) == 0,
            score=max(0.0, score),
            errors=errors,
            warnings=warnings,
            repair_patches=repair_patches,
            metrics=metrics,
        )

    @classmethod
    def verify_vessel(cls, spec: VesselSpec) -> VerificationResult:
        errors: List[str] = []
        warnings: List[str] = []
        score = 1.0

        if len(spec.profile) < 3:
            errors.append("VesselSpec requires at least 3 profile points for revolution.")
            score -= 0.5

        # All radii non-negative
        for i, pt in enumerate(spec.profile):
            if pt.radius < 0:
                errors.append(f"Profile point {i}: radius {pt.radius} < 0")
                score -= 0.1

        # At least one non-zero radius (not a degenerate line on the axis)
        if all(pt.radius < 0.001 for pt in spec.profile):
            errors.append("All profile radii are near zero — vessel would be invisible.")
            score -= 0.5

        return VerificationResult(
            valid=len(errors) == 0,
            score=max(0.0, score),
            errors=errors,
            warnings=warnings,
        )


# ---------------------------------------------------------------------------
# Tier 2 — evaluated-mesh checks (reads metrics JSON from headless runner)
# ---------------------------------------------------------------------------

# Category silhouette area ratio priors  {category: {plane: (min_ratio, max_ratio)}}
# ratio = filled_pixels / bounding_box_pixels
SILHOUETTE_PRIORS: Dict[str, Dict[str, Tuple[float, float]]] = {
    "quadruped": {
        "front_XZ": (0.30, 0.75),
        "side_YZ": (0.45, 0.85),
    },
    "furniture": {
        "top_XY": (0.50, 1.00),
    },
    "vessel": {
        "front_XZ": (0.35, 0.80),
        "side_YZ": (0.35, 0.80),
    },
}


class MeshVerifier:
    """Tier 2: post-headless evaluated-mesh verification."""

    @classmethod
    def verify_mesh_tier2(
        cls,
        metrics: Dict[str, Any],
        category: str = "",
    ) -> VerificationResult:
        """
        Run all Tier 2 checks on the data written to the metrics JSON by the
        headless runner / Blender verification footer.

        metrics keys expected (all optional — missing → check skipped):
            world_verts:   List[List[float]]   — all model vertices in world space
            polys:         List[List[int]]     — polygon vertex-index lists
            leg_verts:     Dict[str, List[float]] — {leg_name: [min_z, ...]}
            contact_pairs: List[Dict]          — [{part_a, part_b, verts_a, verts_b}]
            silhouettes:   Dict[str, str]      — {plane: png_path}

        Returns a VerificationResult (non-blocking: critical failures are errors,
        informational issues are warnings).
        """
        errors: List[str] = []
        warnings: List[str] = []
        metrics_out: Dict[str, Any] = {}

        # ---- a. Level-feet (evaluated mesh) ----
        leg_bottom_z = metrics.get("leg_bottom_z")  # {leg_name: z_value}
        if leg_bottom_z and isinstance(leg_bottom_z, dict) and len(leg_bottom_z) >= 2:
            z_vals = list(leg_bottom_z.values())
            delta = max(z_vals) - min(z_vals)
            metrics_out["level_feet_delta_m"] = delta
            if delta > 0.005:  # 5mm tolerance
                errors.append(
                    f"Evaluated level-feet failed: delta {delta*1000:.1f}mm > 5mm. "
                    f"Legs: {leg_bottom_z}"
                )

        # ---- b. Contact check (BVHTree — checked inside headless, results here) ----
        contact_results = metrics.get("contact_results")  # List[{pair, overlaps, min_dist_mm}]
        if contact_results:
            for cr in contact_results:
                pair = cr.get("pair", "?")
                min_dist = cr.get("min_dist_mm", 0.0)
                required = cr.get("required", False)
                if required and min_dist > 2.0:
                    errors.append(
                        f"Contact check failed for '{pair}': nearest vertex {min_dist:.1f}mm > 2mm. "
                        "Parts may be floating."
                    )

        # ---- c. Symmetry via KDTree ----
        symmetry_max_error = metrics.get("symmetry_max_error_mm")
        if symmetry_max_error is not None:
            metrics_out["symmetry_max_error_mm"] = symmetry_max_error
            if symmetry_max_error > 1.0:
                errors.append(
                    f"Symmetry check failed: max mirror mismatch {symmetry_max_error:.2f}mm > 1mm."
                )

        # ---- d. Manifold edge check ----
        non_manifold_edges = metrics.get("non_manifold_edges", 0)
        metrics_out["non_manifold_edges"] = non_manifold_edges
        if non_manifold_edges > 0:
            errors.append(
                f"Non-manifold mesh: {non_manifold_edges} edges with != 2 adjacent faces."
            )

        # ---- e. Silhouette area ratios ----
        silhouette_metrics = metrics.get("silhouette_metrics")  # {plane: ratio}
        if silhouette_metrics and category in SILHOUETTE_PRIORS:
            priors = SILHOUETTE_PRIORS[category]
            for plane, bounds in priors.items():
                ratio = silhouette_metrics.get(plane)
                if ratio is not None:
                    metrics_out[f"silhouette_ratio_{plane}"] = ratio
                    if not (bounds[0] <= ratio <= bounds[1]):
                        warnings.append(
                            f"Silhouette area ratio for {plane}: {ratio:.2f} "
                            f"outside expected {bounds} for category '{category}'."
                        )

        valid = len(errors) == 0
        score = 1.0 - (0.2 * len(errors)) - (0.05 * len(warnings))
        return VerificationResult(
            valid=valid,
            score=max(0.0, score),
            errors=errors,
            warnings=warnings,
            metrics=metrics_out,
        )
