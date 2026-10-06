"""Conservative XY bounds and uniform fitting for a compiled scene."""
from __future__ import annotations

import math
from typing import Any


def xy_half_extents(node: Any) -> tuple[float, float]:
    geo = node.geometry
    kind = geo.primitive
    rotation = node.transform.rotation
    angle = rotation[2]
    if kind in {"box", "wedge", "pyramid", "prism", "plane", "grid"}:
        size = geo.size or [.01, .01, .01]
        hx, hy = size[0] / 2, size[1] / 2
        return abs(math.cos(angle)) * hx + abs(math.sin(angle)) * hy, abs(math.sin(angle)) * hx + abs(math.cos(angle)) * hy
    if kind in {"cylinder", "cone", "capsule"}:
        radius = geo.radius or 0.0
        if abs(math.sin(rotation[1])) > .7:
            axial = (geo.depth or 0.0) / 2
            return abs(math.cos(angle)) * axial + radius, abs(math.sin(angle)) * axial + radius
        return radius, radius
    if kind in {"torus", "u_shape"}:
        radius = (geo.major_radius or 0.0) + (geo.minor_radius or 0.0)
        return radius, radius
    radius = geo.radius or 0.0
    return radius, radius


def xy_bounds(manifest: Any) -> tuple[float, float, float, float]:
    bounds = [math.inf, -math.inf, math.inf, -math.inf]
    for node in manifest.get_parts():
        x, y = node.transform.position[:2]
        hx, hy = xy_half_extents(node)
        bounds[0] = min(bounds[0], x - hx)
        bounds[1] = max(bounds[1], x + hx)
        bounds[2] = min(bounds[2], y - hy)
        bounds[3] = max(bounds[3], y + hy)
    return tuple(bounds) if manifest.get_parts() else (0.0, 0.0, 0.0, 0.0)


def fit_xy(manifest: Any, extent: float) -> float:
    """Scale the entire model uniformly; never change only the positions."""
    if not extent or extent <= 0:
        return 1.0
    left, right, front, back = xy_bounds(manifest)
    footprint = max(right - left, back - front, 2 * max(abs(left), abs(right), abs(front), abs(back)))
    factor = min(1.0, extent * .98 / footprint) if footprint > 0 else 1.0
    if factor >= 1.0:
        return 1.0
    for node in manifest.get_parts():
        transform = node.transform
        transform.position = [coordinate * factor for coordinate in transform.position]
        geo = node.geometry
        if geo.size:
            geo.size = [dimension * factor for dimension in geo.size]
        for attr in ("radius", "radius2", "depth", "major_radius", "minor_radius"):
            value = getattr(geo, attr, None)
            if value is not None:
                setattr(geo, attr, value * factor)
    manifest.stats["v3_uniform_fit_scale"] = factor
    return factor
