"""Euler Angle Conversion — boundary module for Euler ↔ matrix conversion.

Isolated from the core 4×4 matrix logic in transforms.py so that Euler
angle concerns (gimbal lock, decomposition order) are contained in one place.

Consumers:
- transforms.py  (WorldMatrix._decompose, LocalTransform.from_matrix)
- transforms.py  re-exports _matrix_to_euler for stage4_resolver compatibility
"""

from __future__ import annotations

import math
from typing import List, Tuple


def _mat4_to_trs(
    m: List[List[float]],
) -> Tuple[List[float], List[float], List[float]]:
    """Extract Translation, Rotation (Euler XYZ radians), Scale from 4×4 matrix.

    Assumes no shear.  For sheared matrices results are approximate.

    Gimbal-lock handling:
    - Uses math.isclose(abs(r20), 1.0, abs_tol=1e-4) instead of a hard
      threshold so floating-point drift from matrix composition (e.g.
      r20 = -1.0000000000000002) is absorbed correctly.
    - r20 is clamped to [-1, 1] before math.asin to prevent domain errors.
    """
    # Translation
    position = [m[0][3], m[1][3], m[2][3]]

    # Scale = length of each rotation column
    sx = math.sqrt(m[0][0] ** 2 + m[1][0] ** 2 + m[2][0] ** 2)
    sy = math.sqrt(m[0][1] ** 2 + m[1][1] ** 2 + m[2][1] ** 2)
    sz = math.sqrt(m[0][2] ** 2 + m[1][2] ** 2 + m[2][2] ** 2)
    scale = [sx, sy, sz]

    # Normalise rotation columns
    if sx > 1e-8:
        r00, r10, r20 = m[0][0] / sx, m[1][0] / sx, m[2][0] / sx
    else:
        r00, r10, r20 = 1.0, 0.0, 0.0
    if sy > 1e-8:
        r01, r11, r21 = m[0][1] / sy, m[1][1] / sy, m[2][1] / sy
    else:
        r01, r11, r21 = 0.0, 1.0, 0.0
    if sz > 1e-8:
        r02, r12, r22 = m[0][2] / sz, m[1][2] / sz, m[2][2] / sz
    else:
        r02, r12, r22 = 0.0, 0.0, 1.0

    # Clamp r20 to [-1, 1] to guard against floating-point drift before asin
    r20_clamped = max(-1.0, min(1.0, r20))

    # Euler XYZ extraction with isclose-based gimbal-lock guard
    if not math.isclose(abs(r20_clamped), 1.0, abs_tol=1e-4):
        ry = math.asin(-r20_clamped)
        rx = math.atan2(r21, r22)
        rz = math.atan2(r10, r00)
    else:
        # Gimbal lock: ry = ±90°, rz is set to 0 (arbitrary)
        rz = 0.0
        if r20_clamped < 0:   # ry = +90°
            ry = math.pi / 2
            rx = math.atan2(r01, r02)
        else:                  # ry = -90°
            ry = -math.pi / 2
            rx = math.atan2(-r01, -r02)

    return position, [rx, ry, rz], scale


def _matrix_to_euler(m: List[List[float]]) -> List[float]:
    """Convert 3×3 rotation matrix to Euler XYZ radians.

    Pads to 4×4 and delegates to _mat4_to_trs so gimbal-lock handling
    is consistent everywhere.
    """
    m4 = [
        [m[0][0], m[0][1], m[0][2], 0.0],
        [m[1][0], m[1][1], m[1][2], 0.0],
        [m[2][0], m[2][1], m[2][2], 0.0],
        [0.0,     0.0,     0.0,     1.0],
    ]
    _, rotation, _ = _mat4_to_trs(m4)
    return rotation
