"""Primitive Geometry Resolver for CUA-Sentinel.

Intercepts a list of (tool, args) steps produced by the LLM and corrects
positions/dimensions for Blender primitive composition plans before any
tool is executed.

Rules applied:
- Hollow vessel inner cavity: inner_center_z = outer_center_z + wall/2,
  inner_depth = outer_depth - wall, inner_radius = outer_radius - wall.
- Parts positioned 'N units above the bottom' of a vessel:
  part_center_z = vessel_bottom_z + N + part_depth/2.
- Rod flush with vessel top (only when rod is INSIDE the vessel cavity):
  rod_center_z = vessel_center_z + vessel_depth/2 - rod_depth/2.

Corrections are never applied to cylinders with non-zero rotation — all
Z-axis formulas assume an upright (Z-aligned) cylinder.

Only corrects values that are detectably wrong. Passes through anything
it cannot confidently resolve.
"""

from __future__ import annotations
import logging
from typing import List, Tuple, Any, Dict, Optional

logger = logging.getLogger(__name__)


# ── helpers ──────────────────────────────────────────────────────────────────

def _loc(args: Dict[str, Any]) -> Tuple[float, float, float]:
    loc = args.get("location", [0, 0, 0])
    if isinstance(loc, (list, tuple)) and len(loc) >= 3:
        return (float(loc[0]), float(loc[1]), float(loc[2]))
    return (0.0, 0.0, 0.0)


def _is_upright(args: Dict[str, Any]) -> bool:
    """Return True only if the cylinder has no rotation (or explicitly [0,0,0]).
    All Z-axis position formulas assume an upright cylinder; applying them to a
    rotated cylinder produces nonsense coordinates.
    """
    rot = args.get("rotation")
    if rot is None:
        return True
    if isinstance(rot, (list, tuple)) and len(rot) >= 3:
        return all(abs(float(r)) < 0.01 for r in rot)
    return True


def _is_inside_vessel(cyl_r: float, outer_r: float, inner_r: Optional[float]) -> bool:
    """Return True if the cylinder's radius fits inside the vessel cavity.
    A stem sitting ON TOP of a base has radius < outer_r but is not inside it.
    A plunger rod inside a carafe has radius < inner_r (the cavity radius).
    If there is no inner cavity, nothing can be 'inside' the vessel.
    """
    if inner_r is None:
        return False
    return cyl_r < inner_r


def _find_outer_vessel(
    cylinders: Dict[str, Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Return the cylinder with the largest radius — assumed to be the outer vessel."""
    if not cylinders:
        return None
    return max(cylinders.values(), key=lambda c: float(c.get("radius", 0)))


def _find_inner_cavity(
    cylinders: Dict[str, Dict[str, Any]],
    outer_name: str,
    outer_r: float,
    outer_depth: float,
) -> Optional[Dict[str, Any]]:
    """Return the cylinder that looks like the inner cavity cutter."""
    candidates = []
    for name, cyl in cylinders.items():
        if name == outer_name:
            continue
        r = float(cyl.get("radius", 0))
        d = float(cyl.get("depth", 0))
        # Inner cavity: radius slightly less than outer, depth close to outer
        if 0 < (outer_r - r) < outer_r * 0.3 and abs(d - outer_depth) < outer_depth * 0.2:
            candidates.append(cyl)
        # Or explicitly named inner/cutter
        elif "inner" in name.lower() or "cutter" in name.lower():
            candidates.append(cyl)
    if not candidates:
        return None
    # Pick the one with radius closest to outer_r
    return max(candidates, key=lambda c: float(c.get("radius", 0)))


# ── main resolver ─────────────────────────────────────────────────────────────

def resolve_blender_plan(
    steps: List[Tuple[str, Dict[str, Any]]],
) -> List[Tuple[str, Dict[str, Any]]]:
    """
    Given a list of (tool_name, args) steps, return a corrected copy.
    Only modifies blender:create_cylinder location/depth/radius values.
    All other tools are passed through unchanged.
    """
    # Index cylinders by name so we can cross-reference
    cylinders: Dict[str, Dict[str, Any]] = {}
    for tool, args in steps:
        if tool == "blender:create_cylinder" and "name" in args:
            cylinders[args["name"]] = args

    # Detect outer vessel: largest radius cylinder
    outer = _find_outer_vessel(cylinders)
    if outer is None:
        return steps  # no vessel pattern detected, pass through unchanged

    outer_name = outer["name"]
    outer_r = float(outer.get("radius", 0))
    outer_depth = float(outer.get("depth", 0))
    outer_loc = _loc(outer)
    outer_center_z = outer_loc[2]
    outer_bottom_z = outer_center_z - outer_depth / 2

    # Detect inner cavity: cylinder whose name contains 'inner' or 'cutter',
    # or whose radius is slightly smaller than outer and depth close to outer
    inner = _find_inner_cavity(cylinders, outer_name, outer_r, outer_depth)

    corrected: Dict[str, Dict[str, Any]] = {}

    if inner is not None:
        inner_name = inner["name"]
        inner_r = float(inner.get("radius", outer_r))
        inner_depth = float(inner.get("depth", outer_depth))

        # Infer wall thickness from radius difference if plausible
        wall = outer_r - inner_r
        if wall <= 0 or wall > outer_r * 0.5:
            # Radius difference is implausible — don't touch
            pass
        else:
            correct_inner_depth = outer_depth - wall
            correct_inner_center_z = outer_center_z + wall / 2

            if abs(inner_depth - correct_inner_depth) > 0.01 or \
               abs(_loc(inner)[2] - correct_inner_center_z) > 0.01:
                fixed = dict(inner)
                fixed["depth"] = round(correct_inner_depth, 4)
                loc = list(_loc(inner))
                loc[2] = round(correct_inner_center_z, 4)
                fixed["location"] = loc
                corrected[inner_name] = fixed
                logger.info(
                    f"PrimitiveGeometryResolver: corrected '{inner_name}' "
                    f"depth {inner_depth}->{fixed['depth']}, "
                    f"center_z {_loc(inner)[2]}->{loc[2]}"
                )

    # Correct all other cylinders that are not the outer vessel or inner cavity
    inner_name = inner["name"] if inner else None
    inner_r_val: Optional[float] = float(inner.get("radius", 0)) if inner else None

    for name, cyl in cylinders.items():
        if name == outer_name or name == inner_name:
            continue

        # Never apply Z-axis position formulas to a rotated cylinder.
        # All formulas below assume the cylinder is upright (Z-axis aligned).
        # A rotated cylinder's bounding box is completely different and the
        # formulas would produce wrong coordinates.
        if not _is_upright(cyl):
            continue

        cyl_r = float(cyl.get("radius", 0))
        cyl_depth = float(cyl.get("depth", 0))
        cyl_loc = _loc(cyl)
        cyl_center_z = cyl_loc[2]

        # Detect rod/plunger flush with vessel top: must be INSIDE the vessel
        # (radius fits within the inner cavity), not merely smaller than the outer.
        # Checked BEFORE the N-above-bottom heuristic because a rod inside a vessel
        # with positive z would otherwise incorrectly trigger the N-above-bottom branch.
        if cyl_depth > outer_depth and _is_inside_vessel(cyl_r, outer_r, inner_r_val):
            correct_z = round(outer_center_z + outer_depth / 2 - cyl_depth / 2, 4)
            if abs(correct_z - cyl_center_z) > 0.05:
                fixed = dict(cyl)
                loc = list(cyl_loc)
                loc[2] = correct_z
                fixed["location"] = loc
                corrected[name] = fixed
                logger.info(
                    f"PrimitiveGeometryResolver: corrected rod '{name}' "
                    f"center_z {cyl_center_z}->{correct_z} (flush-top inside vessel)"
                )

        # Detect if this looks like a part positioned 'N above the bottom'
        # Heuristic: center_z is positive but should be negative for a
        # vessel centered at origin with bottom at outer_bottom_z < 0.
        # Only applies to parts NOT inside the vessel cavity.
        elif outer_center_z == 0 and outer_bottom_z < 0 and cyl_center_z > 0 and not _is_inside_vessel(cyl_r, outer_r, inner_r_val):
            # The LLM treated z as distance-from-bottom instead of world z
            N = cyl_center_z
            correct_z = round(outer_bottom_z + N + cyl_depth / 2, 4)
            if abs(correct_z - cyl_center_z) > 0.05:
                fixed = dict(cyl)
                loc = list(cyl_loc)
                loc[2] = correct_z
                fixed["location"] = loc
                corrected[name] = fixed
                logger.info(
                    f"PrimitiveGeometryResolver: corrected '{name}' "
                    f"center_z {cyl_center_z}->{correct_z} "
                    f"(N={N} above bottom_z={outer_bottom_z})"
                )

    if not corrected:
        return steps

    # Rebuild steps with corrections applied
    result = []
    for tool, args in steps:
        if tool == "blender:create_cylinder" and args.get("name") in corrected:
            result.append((tool, corrected[args["name"]]))
        else:
            result.append((tool, args))
    return result
