# Blender Assembly Pipeline — Architecture Blueprint v4

**Status:** IMPLEMENTED AND VERIFIED  
**Last Updated:** January 2025  
**Test Coverage:** 59 pipeline tests passing

**Audience:** An implementing coding assistant with no memory of prior discussion.  
**Purpose:** This document describes the IMPLEMENTED staged pipeline architecture.
The LLM makes only semantic/creative judgments; code owns 100% of numeric geometry.

---

## 0. The Core Invariant

> **No numeric offset or rotation value that reaches Blender may come directly from the
> LLM. Every axis of every transform is either (a) computed by deterministic code from
> real part geometry, or (b) derived from a closed-vocabulary semantic hint the LLM
> chose from a fixed list. There is no path (c): "LLM's raw number, trusted as-is."**

---

## 1. File Structure

```
backend/core/blender_pipeline/
├── orchestrator.py          # Runs Stages 0-4, returns PipelineResult
├── executor.py              # Runs Stages 4.5-6, executes in Blender
├── stage0_understanding.py  # Object category, scale, style
├── stage1_topology.py       # Part tree structure (no numbers)
├── stage2_dimensions.py     # Sizes in meters
├── stage3_semantics.py      # Attachment hints (height_hint, etc.)
├── stage4_resolver.py       # PURE CODE: computes all transforms
├── stage45_modifiers.py     # Bevel/subsurf intent
└── broadcast.py             # WebSocket trace events

backend/core/
├── assembly_spec.py         # AssemblyGraph, AssemblyNode, graph_to_blender_steps()
├── assembly_verification.py # Spatial verification gate
└── blender_ops.py           # Blender operation templates (Pydantic models)
```

---

## 2. Pipeline Overview (IMPLEMENTED)

```
User Prompt
     │
     ▼
┌─────────────────────────────────────────────────────────┐
│ ORCHESTRATOR (orchestrator.py) — Stages 0-4             │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  Stage 0 — Object Understanding (LLM)                   │
│    Output: category, rests_on_surface, style_tag,       │
│            scale_anchor_m                               │
│    File: stage0_understanding.py                        │
│                                                         │
│  Stage 1 — Part Topology (LLM)                          │
│    Output: parts[] with label, primitive_type,          │
│            parent_label, socket_type                    │
│    CRITICAL: NO NUMBERS ALLOWED                         │
│    File: stage1_topology.py                             │
│                                                         │
│  Stage 2 — Dimension Assignment (LLM + validation)      │
│    Output: size/radius/depth per part in meters         │
│    Code validates against scale_anchor                  │
│    File: stage2_dimensions.py                           │
│                                                         │
│  Stage 3 — Attachment Semantics (LLM)                   │
│    Output: height_hint, pierce_direction, connects_to,  │
│            cut_face, radial_count, radial_index, etc.   │
│    STILL NO RAW OFFSET/ROTATION NUMBERS                 │
│    File: stage3_semantics.py                            │
│                                                         │
│  Stage 4 — Deterministic Resolution (PURE CODE)         │
│    Output: AssemblyGraph with computed transforms       │
│    Every offset + rotation from real geometry           │
│    File: stage4_resolver.py                             │
│                                                         │
│  Returns: PipelineResult with AssemblyGraph             │
└─────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────┐
│ EXECUTOR (executor.py) — Stages 4.5-6                   │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  Stage 4.5 — Modifier Intent (LLM or inference)         │
│    Output: bevel, subsurf, surface_detail per part      │
│    File: stage45_modifiers.py                           │
│                                                         │
│  Stage 5 — Blender Execution                            │
│    - graph_to_blender_steps() generates tool calls      │
│    - Three phases: Geometry → Boolean → Modifiers       │
│    - Collection-based isolation (no clear_scene)        │
│    - Transactional: rollback on any failure             │
│    File: executor.py + assembly_spec.py                 │
│                                                         │
│  Stage 6 — Verification                                 │
│    - _run_verification(): spatial/interpenetration      │
│    - _verify_dimensions_match_spec(): LOCAL mesh check  │
│    - _verify_connectors_reach_targets(): STRUT/BRIDGE   │
│    - _verify_boolean_postconditions(): mesh validity    │
│    FAIL = rollback + PipelineStatus.VERIFICATION_FAILED │
│    File: executor.py + assembly_verification.py         │
│                                                         │
└─────────────────────────────────────────────────────────┘
     │
  PASS │ FAIL
     │    └── Rollback generation, purge orphans
     ▼
  SUCCESS (PipelineStatus.SUCCESS)
```

---

## 3. Stage Specifications

### 3.0 Stage 0 — Object Understanding

**Input:** Raw user prompt  
**LLM outputs:**
```json
{
  "category": "weapon",
  "rests_on_surface": true,
  "style_tag": "hard_surface_industrial",
  "scale_anchor_m": {
    "overall_height_or_length": 1.2,
    "reasoning": "broadsword, typical length ~1.2m"
  }
}
```

**style_tag vocabulary:** `hard_surface_industrial | organic_worn | stylized_clean | soft_domestic`

---

### 3.1 Stage 1 — Part Topology

**Input:** Prompt + Stage 0 output  
**LLM outputs:** Parts array with NO NUMBERS
```json
{
  "parts": [
    {"label": "blade", "primitive_type": "box", "parent_label": null, "socket_type": "ROOT"},
    {"label": "groove", "primitive_type": "box", "parent_label": "blade", "socket_type": "BOOLEAN_CUT"},
    {"label": "guard", "primitive_type": "box", "parent_label": "blade", "socket_type": "BOTTOM_CENTER"},
    {"label": "handle", "primitive_type": "cylinder", "parent_label": "guard", "socket_type": "BOTTOM_CENTER"}
  ]
}
```

**primitive_type vocabulary:** `box | cylinder | cone | sphere`  
(Note: `hemisphere` is created via bisect, not a separate primitive)

**socket_type vocabulary:**
```
ROOT
TOP_CENTER | BOTTOM_CENTER
THROUGH_AXIS
LEFT_END | RIGHT_END | TOP_END | BOTTOM_END
FRONT_FACE | BACK_FACE | LEFT_FACE | RIGHT_FACE | TOP_FACE | BOTTOM_FACE
ARRAY_MEMBER
STRUT
RADIAL
RADIAL_BRIDGE
CORNER
EDGE
INSET
BOOLEAN_CUT    ← NEW: Part subtracted from parent (grooves, holes, cutouts)
```

---

### 3.2 Stage 2 — Dimension Assignment

**Input:** Stage 0 + Stage 1 output  
**LLM outputs:** Dimensions per part in meters
```json
{
  "parts": [
    {"label": "blade", "primitive_type": "box", "dimensions": {"size": [0.08, 0.02, 1.0]}},
    {"label": "groove", "primitive_type": "box", "dimensions": {"size": [0.02, 0.005, 0.7]}},
    {"label": "guard", "primitive_type": "box", "dimensions": {"size": [0.25, 0.03, 0.04]}},
    {"label": "handle", "primitive_type": "cylinder", "dimensions": {"radius": 0.02, "depth": 0.15}}
  ]
}
```

**Code validates:** Ratio against scale_anchor, rejects severe mismatches.

---

### 3.3 Stage 3 — Attachment Semantics

**Input:** Stage 1 + Stage 2 output  
**LLM outputs:** Semantic hints per socket_type (NO raw numbers)
```json
{
  "parts": [
    {"label": "blade", "socket_type": "ROOT"},
    {"label": "groove", "socket_type": "BOOLEAN_CUT", "cut_face": "front", "height_hint": "center"},
    {"label": "guard", "socket_type": "BOTTOM_CENTER"},
    {"label": "handle", "socket_type": "BOTTOM_CENTER"}
  ]
}
```

**Required fields by socket_type:**
| socket_type | Required Fields |
|-------------|-----------------|
| THROUGH_AXIS | pierce_direction |
| STRUT | connects_to |
| RADIAL_BRIDGE | connects_to, radial_count, radial_index |
| RADIAL | radial_count, radial_index |
| ARRAY_MEMBER | array_count, array_index |
| BOOLEAN_CUT | (cut_face optional, defaults to "top") |

---

### 3.4 Stage 4 — Deterministic Resolution (PURE CODE)

**Input:** Stage 0 + Stage 2 + Stage 3 output  
**Output:** Complete AssemblyGraph with all transforms computed

**Key invariant:**
```python
def _resolve_transform(socket_type, parent_spec, child_spec, semantics) -> ResolvedTransform:
    """
    MUST assign every one of offset[0..2] and rotation[0..2] explicitly.
    MUST NOT read any raw numeric field from LLM output.
    Every branch must leave no axis unassigned.
    """
```

**JoinMode enum:**
- `FUSE` — Boolean union
- `PARENT_ONLY` — Stays separate, parented
- `BOOLEAN_DIFFERENCE` — Subtracted from parent (for BOOLEAN_CUT)

---

### 3.5 Stage 4.5 — Modifier Intent

**Input:** AssemblyGraph + style_tag  
**Output:** ModifierIntent per part
```python
@dataclass
class ModifierIntent:
    label: str
    bevel: Optional[BevelParams]      # width, segments
    subsurf: Optional[SubsurfParams]  # levels
    surface_detail: Optional[ArrayDetailParams]
```

Can run via LLM or inference (heuristics based on style_tag).

---

### 3.6 Stage 5 — Blender Execution

**graph_to_blender_steps()** generates three phases:

1. **Geometry Phase:** `create_box`, `create_cylinder`, `set_material`
2. **Boolean Phase:** `apply_boolean`, `parent_object`
3. **Modifier Phase:** `set_smooth_shading`, `apply_bevel`, `apply_subdivision`

**Critical:** Modifiers apply AFTER booleans, so bevels apply to final joined mesh.

**Collection-based isolation:**
- Each build gets a unique generation collection (e.g., `sentinel_gen_task123_a1b2c3d4`)
- Object names are prefixed with generation ID (e.g., `ga1b2c3_blade`) to avoid collisions
- No `clear_scene` — user's existing scene preserved
- Lights and cameras link to generation collection, not scene.collection
- On failure: rollback deletes generation + **targeted** orphan cleanup (only orphans created by this build)

---

### 3.7 Stage 6 — Verification

Four verification checks:

1. **_run_verification()** — Spatial/interpenetration via AssemblyVerificationGate
2. **_verify_dimensions_match_spec()** — LOCAL mesh bounds (not world AABB)
3. **_verify_connectors_reach_targets()** — STRUT/RADIAL_BRIDGE length check
4. **_verify_boolean_postconditions()** — Mesh validity (no degenerate faces)

**CRITICAL:** Verification failure = pipeline failure (ok=False), never ok=True with warnings.

**Retry on verification failure:**
- Up to `MAX_VERIFICATION_RETRIES` (default: 1) retries from the **appropriate stage**:
  - Dimension mismatch → retry from **Stage 2** (Dimensions)
  - Spatial/interpenetration → retry from **Stage 3** (Semantics)
  - Connector issues → retry from **Stage 3** (Semantics)
  - Mesh issues (degenerate faces) → **not retryable** (geometry problem)
- Each retry uses a new generation prefix to avoid name collisions
- Verification error is passed as feedback to the retried stage
- Rollback occurs before each retry attempt

**PipelineStatus enum:**
- `SUCCESS` — Build and verification passed
- `BUILD_FAILED` — Stage 0-5 failed (LLM error, execution error)
- `VERIFICATION_FAILED` — Stage 6 checks failed (spatial, dimension, mesh issues)
- `VERIFICATION_UNAVAILABLE` — Verification could not run (exception in verifier). **Fail closed**: treated as failure, not success with warning.
- `ROLLBACK_COMPLETE` — Internal state after rollback (not returned to user)

---

## 4. Socket Type Resolver Rules (Stage 4)

| socket_type | Offset Computation | Rotation |
|-------------|-------------------|----------|
| TOP_CENTER | (0, 0, p_half_z + c_half_z) | Inherit parent |
| BOTTOM_CENTER | (0, 0, -(p_half_z + c_half_z)) | Inherit parent |
| THROUGH_AXIS | X/Y=0, Z from height_hint clamped | From pierce_direction |
| LEFT_END | (0, 0, -(p_half_length + c_half_z)) | Inherit parent |
| RIGHT_END | (0, 0, p_half_length + c_half_z) | Inherit parent |
| FRONT_FACE | (0, -(p_half_y + c_half_y), height_hint) | Flush to face |
| RADIAL | R*cos(θ), R*sin(θ), height_hint | Face outward (rz=θ) |
| RADIAL_BRIDGE | Midpoint of anchors, auto-sized depth | Quaternion to direction |
| STRUT | Midpoint of anchors, auto-sized depth | Quaternion to direction |
| BOOLEAN_CUT | Positioned to penetrate from cut_face | (0, 0, 0) |
| INSET | Recessed into parent surface | Flush |
| CORNER | At parent's corner + child offset | (0, 0, 0) |
| EDGE | Along parent's edge | (0, 0, 0) |
| ARRAY_MEMBER | Spaced along axis, NEVER tilted | Flush to face |

**RADIAL on boxes:** Uses `min(half_x, half_y)` as effective radius.

**Bounds-based socket offsets (asymmetric shapes):**
For primitives with asymmetric bounds (e.g., hemisphere where z_min=0, z_max=radius),
the resolver uses actual mesh bounds rather than symmetric half-extents:
- `BOTTOM_CENTER` on hemisphere: offset = (0, 0, 0) since z_min is already at 0
- `TOP_CENTER` on hemisphere: offset = (0, 0, radius) since z_max = radius

This is computed in Stage 4 using the primitive's known geometry, not measured from Blender.

---

## 5. Blender Conventions

- **Units:** 1 Blender unit = 1 meter
- **Rotation order:** Euler XYZ (Rz · Ry · Rx)
- **Internal storage:** Radians (convert to degrees only at I/O boundary)
- **Cylinder/cone axis:** Local +Z is depth/length axis
- **Verification:** Uses LOCAL mesh bounds (circumradius for cylinders/spheres), not world AABB

---

## 6. Key Implementation Details

### 6.1 Rotation Composition
Euler angles do NOT compose by addition. Use matrix multiplication:
```python
def _compose_rotations(parent_rot, child_rot) -> Tuple[float, float, float]:
    parent_m = _euler_to_matrix(parent_rot)
    child_m = _euler_to_matrix(child_rot)
    composed_m = _matrix_multiply_3x3(parent_m, child_m)
    return _matrix_to_euler(composed_m)
```

### 6.2 World Pose Computation
For STRUT/RADIAL_BRIDGE, must compute actual world positions:
```python
def _compute_world_pose(node, nodes_by_label) -> WorldPose:
    # Walk parent chain, accumulate transforms
    # Returns world position + rotation
```

### 6.3 Connector Auto-Sizing
STRUT and RADIAL_BRIDGE compute their depth from actual anchor distance:
```python
computed_length = sqrt(dx² + dy² + dz²)
child_sub_spec["depth"] = computed_length  # Override LLM's guess
```

### 6.4 Boolean Operations
BOOLEAN_CUT socket type sets `join_mode = JoinMode.BOOLEAN_DIFFERENCE`:
- Stage 4 sets the join_mode
- graph_to_blender_steps() emits `apply_boolean(operation="DIFFERENCE")`
- Target (cutter) is deleted after boolean

---

## 7. Test Coverage

**59 tests in test_stage4_resolver.py covering:**
- TOP_CENTER, BOTTOM_CENTER on various primitives
- THROUGH_AXIS with all pierce_directions
- LEFT_END, RIGHT_END with rotation inheritance
- Face mounts (FRONT_FACE, etc.) with height_hint
- ARRAY_MEMBER spacing and no-tilt invariant
- RADIAL_BRIDGE distinct rotations per index
- CORNER, EDGE, INSET positioning
- RADIAL on boxes (uses min half-extent)
- Parent cycle detection
- Array feasibility warnings
- Embedment validation

---

## 8. API Entry Point

```
POST /api/blender/build
{
  "description": "fantasy broadsword with central groove",
  "use_llm_modifiers": false
}
```

Calls `run_staged_pipeline_and_execute()` which:
1. Runs orchestrator (Stages 0-4)
2. Runs executor (Stages 4.5-6)
3. Returns success/failure with generation_id

---

## 9. Debugging

WebSocket traces broadcast to frontend at each stage:
```python
await broadcast_blender_trace(task_id, stage_num, stage_name, status, data)
```

Trace includes:
- Stage number and name
- Status: running/complete/failed/retrying
- Stage-specific data (parts count, errors, etc.)
