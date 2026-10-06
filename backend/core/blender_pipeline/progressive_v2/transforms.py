"""Hierarchical Transform System — Phase 1 Data Model.

This module provides the spatial backbone for the progressive pipeline.
Every node has a coordinate frame, and transforms compose through the tree.

Key invariants:
1. local_transform is authoritative (position, rotation, scale)
2. world_matrix is derived (4x4 homogeneous matrix)
3. world_matrix = parent.world_matrix @ child.local_matrix
4. No geometry lookup is involved in transform composition
5. Revision-based cache invalidation: world_matrix valid only if parent_revision matches
6. Frozen means "local spatial contract verified" — descendants can still change
7. Scale should be [1,1,1] unless explicit architectural reason (dimensions ≠ scale)

The transform hierarchy is SEPARATE from:
- Geometry (what shape to create)
- Attachment/sockets (semantic relationship to parent)
- Bounding boxes (derived from built geometry)

Blueprint: Hierarchical Transform Frames architecture.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    pass


# ---------------------------------------------------------------------------
# Matrix Utilities
# ---------------------------------------------------------------------------

def _identity_4x4() -> List[List[float]]:
    """Return 4x4 identity matrix."""
    return [
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]


def _mat4_multiply(a: List[List[float]], b: List[List[float]]) -> List[List[float]]:
    """Multiply two 4x4 matrices: result = a @ b."""
    result = [[0.0] * 4 for _ in range(4)]
    for i in range(4):
        for j in range(4):
            result[i][j] = sum(a[i][k] * b[k][j] for k in range(4))
    return result


def _mat4_from_trs(
    position: List[float],
    rotation: List[float],
    scale: List[float],
) -> List[List[float]]:
    """Build 4x4 matrix from Translation, Rotation (Euler XYZ radians), Scale.
    
    Composition order: M = T @ R @ S
    This matches Blender's convention.
    """
    # Rotation matrix (Euler XYZ: Rz @ Ry @ Rx)
    rx, ry, rz = rotation[0], rotation[1], rotation[2]
    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)
    
    # Combined rotation: Rz @ Ry @ Rx
    r00 = cy * cz
    r01 = sx * sy * cz - cx * sz
    r02 = cx * sy * cz + sx * sz
    r10 = cy * sz
    r11 = sx * sy * sz + cx * cz
    r12 = cx * sy * sz - sx * cz
    r20 = -sy
    r21 = sx * cy
    r22 = cx * cy
    
    # Apply scale to rotation columns
    sx_scale, sy_scale, sz_scale = scale[0], scale[1], scale[2]
    
    return [
        [r00 * sx_scale, r01 * sy_scale, r02 * sz_scale, position[0]],
        [r10 * sx_scale, r11 * sy_scale, r12 * sz_scale, position[1]],
        [r20 * sx_scale, r21 * sy_scale, r22 * sz_scale, position[2]],
        [0.0, 0.0, 0.0, 1.0],
    ]


# _mat4_to_trs lives in euler_conversion.py (Euler isolation — item 4).
# Imported here so WorldMatrix._decompose and LocalTransform.from_matrix
# can call it without knowing about the boundary module.
from .euler_conversion import _mat4_to_trs  # noqa: F401  (re-used below)


def _mat4_transform_point(m: List[List[float]], p: List[float]) -> List[float]:
    """Transform a 3D point by a 4x4 matrix."""
    x = m[0][0] * p[0] + m[0][1] * p[1] + m[0][2] * p[2] + m[0][3]
    y = m[1][0] * p[0] + m[1][1] * p[1] + m[1][2] * p[2] + m[1][3]
    z = m[2][0] * p[0] + m[2][1] * p[1] + m[2][2] * p[2] + m[2][3]
    return [x, y, z]


def _mat4_transform_vector(m: List[List[float]], v: List[float]) -> List[float]:
    """Transform a 3D vector by a 4x4 matrix (ignores translation)."""
    x = m[0][0] * v[0] + m[0][1] * v[1] + m[0][2] * v[2]
    y = m[1][0] * v[0] + m[1][1] * v[1] + m[1][2] * v[2]
    z = m[2][0] * v[0] + m[2][1] * v[1] + m[2][2] * v[2]
    return [x, y, z]


def _mat4_inverse(m: List[List[float]]) -> Optional[List[List[float]]]:
    """Compute inverse of 4x4 matrix. Returns None if singular.

    Fast path: affine TRS matrix (bottom row [0,0,0,1], uniform-ish scale).
        R^-1 = R^T  (rotation is orthogonal)
        t^-1 = -R^T @ t
    Scale guard: if any column norm deviates from 1 by more than 1e-4 the
    matrix carries non-unit scale; fall through to the full cofactor path.

    Fallback: general 16-cofactor inverse for non-affine matrices.
    """
    # ── Affine fast-path ──────────────────────────────────────────────────
    # Check bottom row is [0, 0, 0, 1]
    if (abs(m[3][0]) < 1e-9 and abs(m[3][1]) < 1e-9 and
            abs(m[3][2]) < 1e-9 and abs(m[3][3] - 1.0) < 1e-9):
        # Column norms of the 3×3 rotation block
        s0 = math.sqrt(m[0][0]**2 + m[1][0]**2 + m[2][0]**2)
        s1 = math.sqrt(m[0][1]**2 + m[1][1]**2 + m[2][1]**2)
        s2 = math.sqrt(m[0][2]**2 + m[1][2]**2 + m[2][2]**2)
        if (abs(s0 - 1.0) < 1e-4 and abs(s1 - 1.0) < 1e-4 and
                abs(s2 - 1.0) < 1e-4):
            # Pure rotation + translation: inverse = R^T | -R^T·t
            tx, ty, tz = m[0][3], m[1][3], m[2][3]
            return [
                [m[0][0], m[1][0], m[2][0], -(m[0][0]*tx + m[1][0]*ty + m[2][0]*tz)],
                [m[0][1], m[1][1], m[2][1], -(m[0][1]*tx + m[1][1]*ty + m[2][1]*tz)],
                [m[0][2], m[1][2], m[2][2], -(m[0][2]*tx + m[1][2]*ty + m[2][2]*tz)],
                [0.0, 0.0, 0.0, 1.0],
            ]

    # ── General 16-cofactor fallback ──────────────────────────────────────
    a = m[0][0]; b = m[0][1]; c = m[0][2]; d = m[0][3]
    e = m[1][0]; f = m[1][1]; g = m[1][2]; h = m[1][3]
    i = m[2][0]; j = m[2][1]; k = m[2][2]; l = m[2][3]
    n = m[3][0]; o = m[3][1]; p = m[3][2]; q = m[3][3]

    kq_lp = k * q - l * p
    jq_lo = j * q - l * o
    jp_ko = j * p - k * o
    iq_ln = i * q - l * n
    ip_kn = i * p - k * n
    io_jn = i * o - j * n

    det = (a * (f * kq_lp - g * jq_lo + h * jp_ko)
         - b * (e * kq_lp - g * iq_ln + h * ip_kn)
         + c * (e * jq_lo - f * iq_ln + h * io_jn)
         - d * (e * jp_ko - f * ip_kn + g * io_jn))

    if abs(det) < 1e-12:
        return None

    inv_det = 1.0 / det

    gq_hp = g * q - h * p
    fq_ho = f * q - h * o
    fp_go = f * p - g * o
    eq_hn = e * q - h * n
    ep_gn = e * p - g * n
    eo_fn = e * o - f * n
    gl_hk = g * l - h * k
    fl_hj = f * l - h * j
    fk_gj = f * k - g * j
    el_hi = e * l - h * i
    ek_gi = e * k - g * i
    ej_fi = e * j - f * i

    return [
        [
            (f * kq_lp - g * jq_lo + h * jp_ko) * inv_det,
            -(b * kq_lp - c * jq_lo + d * jp_ko) * inv_det,
            (b * gq_hp - c * fq_ho + d * fp_go) * inv_det,
            -(b * gl_hk - c * fl_hj + d * fk_gj) * inv_det,
        ],
        [
            -(e * kq_lp - g * iq_ln + h * ip_kn) * inv_det,
            (a * kq_lp - c * iq_ln + d * ip_kn) * inv_det,
            -(a * gq_hp - c * eq_hn + d * ep_gn) * inv_det,
            (a * gl_hk - c * el_hi + d * ek_gi) * inv_det,
        ],
        [
            (e * jq_lo - f * iq_ln + h * io_jn) * inv_det,
            -(a * jq_lo - b * iq_ln + d * io_jn) * inv_det,
            (a * fq_ho - b * eq_hn + d * eo_fn) * inv_det,
            -(a * fl_hj - b * el_hi + d * ej_fi) * inv_det,
        ],
        [
            -(e * jp_ko - f * ip_kn + g * io_jn) * inv_det,
            (a * jp_ko - b * ip_kn + c * io_jn) * inv_det,
            -(a * fp_go - b * ep_gn + c * eo_fn) * inv_det,
            (a * fk_gj - b * ek_gi + c * ej_fi) * inv_det,
        ],
    ]


# ---------------------------------------------------------------------------
# LocalTransform — authoritative local-space transform
# ---------------------------------------------------------------------------

@dataclass
class LocalTransform:
    """Local transform relative to parent frame.
    
    This is the AUTHORITATIVE representation. World transforms are derived
    by composing local transforms through the hierarchy.
    
    Attributes:
        position: [x, y, z] translation in meters
        rotation: [rx, ry, rz] Euler XYZ rotation in RADIANS
        scale: [sx, sy, sz] scale factors (default [1, 1, 1])
    """
    position: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    rotation: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    scale: List[float] = field(default_factory=lambda: [1.0, 1.0, 1.0])
    
    @classmethod
    def identity(cls) -> LocalTransform:
        """Create identity transform (no translation, rotation, or scale)."""
        return cls()
    
    @classmethod
    def from_position(cls, x: float, y: float, z: float) -> LocalTransform:
        """Create transform with only translation."""
        return cls(position=[x, y, z])
    
    @classmethod
    def from_rotation_degrees(cls, rx: float, ry: float, rz: float) -> LocalTransform:
        """Create transform with only rotation (input in degrees)."""
        return cls(rotation=[
            math.radians(rx),
            math.radians(ry),
            math.radians(rz),
        ])
    
    def to_matrix(self) -> List[List[float]]:
        """Convert to 4x4 homogeneous transformation matrix."""
        return _mat4_from_trs(self.position, self.rotation, self.scale)
    
    @classmethod
    def from_matrix(cls, m: List[List[float]]) -> LocalTransform:
        """Create LocalTransform from 4x4 matrix."""
        pos, rot, scale = _mat4_to_trs(m)
        return cls(position=pos, rotation=rot, scale=scale)
    
    def rotation_degrees(self) -> List[float]:
        """Return rotation in degrees (for Blender API)."""
        return [math.degrees(r) for r in self.rotation]
    
    def to_dict(self) -> dict:
        """Serialize for JSON persistence."""
        return {
            "position": list(self.position),
            "rotation": list(self.rotation),
            "scale": list(self.scale),
        }
    
    @classmethod
    def from_dict(cls, d: dict) -> LocalTransform:
        """Deserialize from JSON."""
        return cls(
            position=list(d.get("position", [0.0, 0.0, 0.0])),
            rotation=list(d.get("rotation", [0.0, 0.0, 0.0])),
            scale=list(d.get("scale", [1.0, 1.0, 1.0])),
        )
    
    def __repr__(self) -> str:
        pos = f"[{self.position[0]:.3f}, {self.position[1]:.3f}, {self.position[2]:.3f}]"
        rot_deg = self.rotation_degrees()
        rot = f"[{rot_deg[0]:.1f}°, {rot_deg[1]:.1f}°, {rot_deg[2]:.1f}°]"
        return f"LocalTransform(pos={pos}, rot={rot})"


# ---------------------------------------------------------------------------
# WorldMatrix — derived world-space transform (cached)
# ---------------------------------------------------------------------------

@dataclass
class WorldMatrix:
    """World-space transformation matrix (derived, cached).
    
    This is the DERIVED representation, computed from the hierarchy:
        world_matrix = parent.world_matrix @ child.local_matrix
    
    The 4x4 matrix is the authoritative world representation.
    Position/rotation/scale are extracted on demand.
    """
    matrix: List[List[float]] = field(default_factory=_identity_4x4)
    
    # Cached decomposition (computed lazily)
    _position: Optional[List[float]] = field(default=None, repr=False)
    _rotation: Optional[List[float]] = field(default=None, repr=False)
    _scale: Optional[List[float]] = field(default=None, repr=False)
    
    @classmethod
    def identity(cls) -> WorldMatrix:
        """Create identity world matrix."""
        return cls()
    
    @classmethod
    def from_local(cls, local: LocalTransform) -> WorldMatrix:
        """Create world matrix from a local transform (for root nodes)."""
        return cls(matrix=local.to_matrix())
    
    @classmethod
    def compose(cls, parent: WorldMatrix, child_local: LocalTransform) -> WorldMatrix:
        """Compose parent world matrix with child local transform.
        
        This is THE core operation:
            child_world = parent_world @ child_local
        """
        child_matrix = child_local.to_matrix()
        result_matrix = _mat4_multiply(parent.matrix, child_matrix)
        return cls(matrix=result_matrix)
    
    def _decompose(self) -> None:
        """Lazily decompose matrix into position/rotation/scale."""
        if self._position is None:
            self._position, self._rotation, self._scale = _mat4_to_trs(self.matrix)
    
    @property
    def position(self) -> List[float]:
        """World position [x, y, z]."""
        self._decompose()
        return self._position
    
    @property
    def rotation(self) -> List[float]:
        """World rotation [rx, ry, rz] in radians."""
        self._decompose()
        return self._rotation
    
    @property
    def scale(self) -> List[float]:
        """World scale [sx, sy, sz]."""
        self._decompose()
        return self._scale
    
    def rotation_degrees(self) -> List[float]:
        """World rotation in degrees (for Blender API)."""
        return [math.degrees(r) for r in self.rotation]
    
    def transform_point(self, p: List[float]) -> List[float]:
        """Transform a local point to world space."""
        return _mat4_transform_point(self.matrix, p)
    
    def transform_vector(self, v: List[float]) -> List[float]:
        """Transform a local vector to world space (ignores translation)."""
        return _mat4_transform_vector(self.matrix, v)
    
    def inverse(self) -> Optional[WorldMatrix]:
        """Compute inverse matrix (world-to-local). Returns None if singular."""
        inv = _mat4_inverse(self.matrix)
        if inv is None:
            return None
        return WorldMatrix(matrix=inv)
    
    def to_dict(self) -> dict:
        """Serialize for JSON persistence."""
        return {"matrix": [list(row) for row in self.matrix]}
    
    @classmethod
    def from_dict(cls, d: dict) -> WorldMatrix:
        """Deserialize from JSON."""
        return cls(matrix=[list(row) for row in d.get("matrix", _identity_4x4())])
    
    def __repr__(self) -> str:
        pos = self.position
        rot_deg = self.rotation_degrees()
        return (
            f"WorldMatrix(pos=[{pos[0]:.3f}, {pos[1]:.3f}, {pos[2]:.3f}], "
            f"rot=[{rot_deg[0]:.1f}°, {rot_deg[1]:.1f}°, {rot_deg[2]:.1f}°])"
        )


# ---------------------------------------------------------------------------
# NodeTransformState — complete transform state for a node
# ---------------------------------------------------------------------------

@dataclass
class NodeTransformState:
    """Complete transform state for a manifest node.
    
    Revision-based cache invalidation:
    - revision: incremented when local_transform changes
    - parent_revision: the parent's revision when world_matrix was computed
    - world_matrix is valid only if parent_revision matches parent's current revision
    
    Frozen semantics:
    - Frozen means "this node's local spatial contract has been verified"
    - Frozen does NOT mean descendants cannot change
    - Parent transform change → descendants become stale (must recompute)
    - Child transform change → parent unaffected
    
    Usage:
        state = NodeTransformState()
        state.set_local_transform(LocalTransform.from_position(1, 0, 0))
        state.compute_world(parent_state)
        print(state.world_matrix.position)
    """
    # Authoritative local transform
    local_transform: LocalTransform = field(default_factory=LocalTransform)
    
    # Derived world matrix (None until computed)
    world_matrix: Optional[WorldMatrix] = None
    
    # Revision tracking for cache invalidation
    revision: int = 0  # Incremented when local_transform changes
    parent_revision: int = -1  # Parent's revision when world was computed (-1 = never)
    
    # Lock state - once frozen, LOCAL transform cannot change
    # (world_matrix may still be recomputed if ancestors change)
    frozen: bool = False

    # Set to True by set_local_transform() so callers can distinguish
    # "Stage 4 has run" from "still at default identity" without relying
    # on revision == 0 (which is also 0 for a ROOT node that legitimately
    # has an identity transform and has never been mutated).
    is_resolved: bool = False
    
    def set_local_transform(
        self,
        transform: LocalTransform,
        *,
        force: bool = False,
    ) -> None:
        """Set local transform and increment revision.
        
        Args:
            transform: New local transform
            force: If True, allow setting even if frozen (for repair)
            
        Raises:
            RuntimeError: If frozen and force=False
        """
        if self.frozen and not force:
            raise RuntimeError("Cannot modify frozen transform (use force=True for repair)")
        self.local_transform = transform
        self.revision += 1
        self.is_resolved = True
        # Invalidate cached world (will be recomputed on next access)
        self.world_matrix = None
        self.parent_revision = -1
    
    def is_world_valid(self, parent_revision: int) -> bool:
        """Check if cached world_matrix is still valid.
        
        Args:
            parent_revision: Current revision of parent node (-1 for root)
            
        Returns:
            True if world_matrix is valid and doesn't need recomputation
        """
        if self.world_matrix is None:
            return False
        return self.parent_revision == parent_revision
    
    def compute_world(
        self,
        parent_world: Optional[WorldMatrix],
        parent_revision: int = -1,
    ) -> WorldMatrix:
        """Compute and cache world matrix from parent.
        
        Args:
            parent_world: Parent's world matrix, or None for root nodes
            parent_revision: Parent's current revision (-1 for root)
            
        Returns:
            The computed world matrix
        """
        # Check if cache is valid
        if self.is_world_valid(parent_revision):
            return self.world_matrix
        
        if parent_world is None:
            # Root node: world = local
            new_world = WorldMatrix.from_local(self.local_transform)
        else:
            # Child node: world = parent @ local
            new_world = WorldMatrix.compose(parent_world, self.local_transform)
        
        self.world_matrix = new_world
        self.parent_revision = parent_revision
        return new_world
    
    def freeze(self) -> None:
        """Lock the local transform (called when node is verified).
        
        Frozen means: this node's local spatial contract has been verified
        and must not be modified unless explicitly invalidated.
        
        Note: Descendants can still change. World matrix may be recomputed
        if ancestors change (but local_transform stays fixed).
        """
        # Allow freezing even if world_matrix is None (e.g. ROOT nodes with
        # identity transform that haven't needed propagation yet). The contract
        # being frozen is the LOCAL transform, not the derived world matrix.
        self.frozen = True
    
    def unfreeze(self) -> None:
        """Unlock the local transform (for retry/repair)."""
        self.frozen = False
    
    def mark_stale(self) -> None:
        """Mark world_matrix as needing recomputation.
        
        Called when an ancestor's transform changed. Does NOT affect
        local_transform or frozen status.
        """
        self.world_matrix = None
        self.parent_revision = -1
    
    def to_dict(self) -> dict:
        """Serialize for JSON persistence."""
        d = {
            "local_transform": self.local_transform.to_dict(),
            "frozen": self.frozen,
            "is_resolved": self.is_resolved,
            "revision": self.revision,
            "parent_revision": self.parent_revision,
        }
        if self.world_matrix is not None:
            d["world_matrix"] = self.world_matrix.to_dict()
        return d
    
    @classmethod
    def from_dict(cls, d: dict) -> NodeTransformState:
        """Deserialize from JSON."""
        state = cls(
            local_transform=LocalTransform.from_dict(d.get("local_transform", {})),
            frozen=d.get("frozen", False),
            is_resolved=d.get("is_resolved", False),
            revision=d.get("revision", 0),
            parent_revision=d.get("parent_revision", -1),
        )
        if "world_matrix" in d:
            state.world_matrix = WorldMatrix.from_dict(d["world_matrix"])
        return state


# ---------------------------------------------------------------------------
# Transform Hierarchy Operations
# ---------------------------------------------------------------------------

def compute_world_transform_chain(
    node_id: str,
    get_node_transform: callable,
    get_parent_id: callable,
) -> WorldMatrix:
    """Compute world matrix by walking up the hierarchy.
    
    This is the CORE algorithm for hierarchical transforms:
        world = root.local @ child1.local @ child2.local @ ... @ node.local
    
    Uses revision-based caching: only recomputes nodes whose parent changed.
    
    Args:
        node_id: The node to compute world transform for
        get_node_transform: Callable(node_id) -> NodeTransformState
        get_parent_id: Callable(node_id) -> Optional[parent_id]
        
    Returns:
        WorldMatrix for the node
    """
    # Collect ancestor chain (node -> parent -> grandparent -> ... -> root)
    chain = []
    current_id = node_id
    while current_id is not None:
        chain.append(current_id)
        current_id = get_parent_id(current_id)
    
    # Reverse to get root -> ... -> node order
    chain.reverse()
    
    # Compose transforms from root to node, using revision caching
    parent_world = None
    parent_revision = -1  # Root has no parent
    
    for nid in chain:
        transform_state = get_node_transform(nid)
        parent_world = transform_state.compute_world(parent_world, parent_revision)
        parent_revision = transform_state.revision
    
    return parent_world


def propagate_world_transforms(
    root_id: str,
    get_node_transform: callable,
    get_children_ids: callable,
    get_parent_id: callable,
) -> None:
    """Propagate world transforms down the hierarchy from root.
    
    This is used after a parent's local transform changes to update
    all descendants' world matrices.
    
    Key behavior:
    - All descendants are marked stale FIRST, then recomputed top-down.
      This is necessary because revision-based caching only detects
      local_transform mutations (via set_local_transform), not world_matrix
      content changes caused by an ancestor's recomputation. Without the
      stale pass, a child whose parent_revision still matches its stored
      value would be treated as a cache hit even though its parent's
      world_matrix content has changed.
    - Frozen nodes: local_transform stays fixed, but world_matrix is recomputed.
    
    Args:
        root_id: The node whose subtree to update
        get_node_transform: Callable(node_id) -> NodeTransformState
        get_children_ids: Callable(node_id) -> List[child_id]
        get_parent_id: Callable(node_id) -> Optional[parent_id]
    """
    # Step 1: mark all descendants stale so compute_world is forced to
    # recompute every node regardless of cached parent_revision values.
    mark_descendants_stale(root_id, get_node_transform, get_children_ids)
    # Also mark the root itself stale so it recomputes from its parent.
    get_node_transform(root_id).mark_stale()

    def propagate(
        node_id: str,
        parent_world: Optional[WorldMatrix],
        parent_revision: int,
    ) -> None:
        transform_state = get_node_transform(node_id)
        # world_matrix is None (marked stale above), so compute_world always runs.
        world = transform_state.compute_world(parent_world, parent_revision)
        current_revision = transform_state.revision
        for child_id in get_children_ids(node_id):
            propagate(child_id, world, current_revision)

    # Get parent's world matrix if root has a parent
    parent_id = get_parent_id(root_id)
    if parent_id is not None:
        parent_state = get_node_transform(parent_id)
        parent_world = parent_state.world_matrix
        parent_revision = parent_state.revision
    else:
        parent_world = None
        parent_revision = -1

    propagate(root_id, parent_world, parent_revision)


def mark_descendants_stale(
    node_id: str,
    get_node_transform: callable,
    get_children_ids: callable,
) -> None:
    """Mark all descendants as needing world recomputation.
    
    Called when a node's local_transform changes. Does not modify
    local_transform or frozen status of any node.
    
    Args:
        node_id: The node whose descendants to mark stale
        get_node_transform: Callable(node_id) -> NodeTransformState
        get_children_ids: Callable(node_id) -> List[child_id]
    """
    for child_id in get_children_ids(node_id):
        child_state = get_node_transform(child_id)
        child_state.mark_stale()
        mark_descendants_stale(child_id, get_node_transform, get_children_ids)


# ---------------------------------------------------------------------------
# Scale Invariant Validation
# ---------------------------------------------------------------------------

def validate_unit_scale(transform: LocalTransform, tolerance: float = 1e-6) -> bool:
    """Check that scale is [1,1,1] (dimensions ≠ transform scale invariant).
    
    In this architecture, geometry dimensions determine mesh size.
    Transform scale should NOT be used to specify physical dimensions.
    
    Args:
        transform: LocalTransform to validate
        tolerance: Allowed deviation from 1.0
        
    Returns:
        True if scale is effectively [1,1,1]
    """
    return all(abs(s - 1.0) < tolerance for s in transform.scale)


def assert_unit_scale(transform: LocalTransform, context: str = "") -> None:
    """Raise if scale is not [1,1,1].
    
    Args:
        transform: LocalTransform to validate
        context: Description for error message
        
    Raises:
        ValueError: If scale is not unit
    """
    if not validate_unit_scale(transform):
        raise ValueError(
            f"Non-unit scale {transform.scale} in {context}. "
            f"Use geometry dimensions, not transform scale, for physical size."
        )


# ---------------------------------------------------------------------------
# Matrix-Based Transform Comparison (Phase 3)
# ---------------------------------------------------------------------------

def compare_positions(
    pos_a: List[float],
    pos_b: List[float],
    tolerance: float = 1e-5,
) -> Tuple[float, bool]:
    """Compare two positions.
    
    Args:
        pos_a: First position [x, y, z]
        pos_b: Second position [x, y, z]
        tolerance: Maximum allowed distance
        
    Returns:
        (distance, is_match)
    """
    dist = math.sqrt(sum((pos_a[i] - pos_b[i]) ** 2 for i in range(3)))
    return dist, dist <= tolerance


def compare_rotations_matrix(
    rot_a: List[float],
    rot_b: List[float],
    tolerance_deg: float = 0.1,
) -> Tuple[float, bool]:
    """Compare two rotations using matrix method (avoids Euler ambiguity).
    
    Computes R_delta = inverse(R_a) @ R_b and extracts the angular error.
    This is more robust than comparing Euler angles directly because:
    - [0, 0, 0] and [360, 0, 0] represent the same orientation
    - Different Euler decompositions can represent the same rotation
    
    Args:
        rot_a: First rotation [rx, ry, rz] in radians
        rot_b: Second rotation [rx, ry, rz] in radians
        tolerance_deg: Maximum allowed angular difference in degrees
        
    Returns:
        (angular_error_degrees, is_match)
    """
    # Build rotation matrices
    mat_a = _mat4_from_trs([0, 0, 0], rot_a, [1, 1, 1])
    mat_b = _mat4_from_trs([0, 0, 0], rot_b, [1, 1, 1])
    
    # Compute R_delta = inverse(R_a) @ R_b
    mat_a_inv = _mat4_inverse(mat_a)
    if mat_a_inv is None:
        # Singular matrix - fall back to Euler comparison
        max_diff = max(abs(math.degrees(rot_a[i] - rot_b[i])) for i in range(3))
        return max_diff, max_diff <= tolerance_deg
    
    mat_delta = _mat4_multiply(mat_a_inv, mat_b)
    
    # Extract angular error from R_delta
    # For a rotation matrix, trace = 1 + 2*cos(angle)
    # So angle = acos((trace - 1) / 2)
    trace = mat_delta[0][0] + mat_delta[1][1] + mat_delta[2][2]
    # Clamp to valid range for acos
    cos_angle = max(-1.0, min(1.0, (trace - 1.0) / 2.0))
    angle_rad = math.acos(cos_angle)
    angle_deg = math.degrees(angle_rad)
    
    return angle_deg, angle_deg <= tolerance_deg


def compare_world_matrices(
    mat_a: WorldMatrix,
    mat_b: WorldMatrix,
    pos_tolerance: float = 1e-5,
    rot_tolerance_deg: float = 0.1,
) -> Tuple[float, float, bool]:
    """Compare two world matrices.
    
    Args:
        mat_a: First world matrix
        mat_b: Second world matrix
        pos_tolerance: Position tolerance in meters
        rot_tolerance_deg: Rotation tolerance in degrees
        
    Returns:
        (position_delta, rotation_delta_deg, is_match)
    """
    pos_delta, pos_match = compare_positions(
        mat_a.position, mat_b.position, pos_tolerance
    )
    rot_delta, rot_match = compare_rotations_matrix(
        mat_a.rotation, mat_b.rotation, rot_tolerance_deg
    )
    return pos_delta, rot_delta, pos_match and rot_match


def validate_local_transform(transform: LocalTransform, context: str = "") -> List[str]:
    """Validate a local transform before inserting into hierarchy.
    
    Checks:
    - Position is finite
    - Rotation is finite
    - Scale is finite
    - Scale is approximately [1,1,1]
    
    Args:
        transform: LocalTransform to validate
        context: Description for error messages
        
    Returns:
        List of validation error messages (empty if valid)
    """
    errors = []
    
    # Check position finite
    if not all(math.isfinite(p) for p in transform.position):
        errors.append(f"{context}: position contains non-finite values: {transform.position}")
    
    # Check rotation finite
    if not all(math.isfinite(r) for r in transform.rotation):
        errors.append(f"{context}: rotation contains non-finite values: {transform.rotation}")
    
    # Check scale finite
    if not all(math.isfinite(s) for s in transform.scale):
        errors.append(f"{context}: scale contains non-finite values: {transform.scale}")
    
    # Check scale is unit
    if not validate_unit_scale(transform):
        errors.append(f"{context}: non-unit scale {transform.scale}")
    
    return errors


# ---------------------------------------------------------------------------
# Euler Utility (re-exported for stage4_resolver compatibility)
# ---------------------------------------------------------------------------

def _matrix_to_euler(m: List[List[float]]) -> List[float]:
    """Convert 3x3 rotation matrix to Euler XYZ radians.

    Thin wrapper around _mat4_to_trs so stage4_resolver doesn't need to
    import from executor (which no longer contains this function).
    """
    m4 = [
        [m[0][0], m[0][1], m[0][2], 0.0],
        [m[1][0], m[1][1], m[1][2], 0.0],
        [m[2][0], m[2][1], m[2][2], 0.0],
        [0.0,     0.0,     0.0,     1.0],
    ]
    _, rotation, _ = _mat4_to_trs(m4)
    return rotation
