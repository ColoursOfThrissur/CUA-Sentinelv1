# Blender Pipeline — Living Blueprint

> **Ground truth only. Every statement here is verified against actual code.**
> Separate sections for CURRENT BEHAVIOR, KNOWN DEFECTS, and OPEN DECISIONS.
> Update this file when code changes. Never document intended behavior as current.

---

## Bug Registry (canonical list)

| ID | Node | Symptom | Confirmed Root Cause | Status |
|---|---|---|---|---|
| BUG-001 | `cage_assembly` | `children_ids: []`, `blender_objects: []`, verified as `type: leaf_assembly` | Exact failure point unknown. Do not attribute until state transitions are traced from actual log data. | Open — untraced |
| BUG-002 | `motor_housing_assembly` | Placed at local Z=0.05 (inside base) instead of correct position above `vertical_rod` | `run_assembly()` TOP_CENTER restricts reference candidates to ROOT-socket siblings only. `vertical_rod` has TOP_CENTER socket so is excluded. | Open — fix contract not settled |
| BUG-003 | `cage_assembly` transform | Identity transform, `source="ASSEMBLY:FRONT_FACE:unsupported"` | `run_assembly()` had no assembly-level handler for FRONT_FACE. Fell through to `else` branch → identity + warning log. | **Fixed** — see Stage 4 change log |
| BUG-004 | All assemblies with non-center sockets | Flat output — all parts placed at/near world origin | `run_assembly()` `else` branch returned identity for any socket not in the 7 named cases. All children inherited `world_matrix` at `[0,0,0]`. | **Fixed** — see Stage 4 change log |

---

## Pipeline Entry

```
POST /api/blender  (or task queue)
        │
        ▼
  controller.py  ──  BuildManifest.create(prompt)
        │              model_id = "m_{10-hex}"
        │              root node: kind=MODEL, state=PLANNED, depth=0
        ▼
  RecursiveDecomposer.decompose()
        │
        ▼
  [Stage 2 → Stage 3 → Stage 4 per PART node]
        │
        ▼
  Executor (build geometry in Blender)
```

---

## Stage 0 — Decomposition (`decomposer.py`)

### CURRENT BEHAVIOR

#### Limits (`hierarchy.py` — `HierarchyLimits` defaults)

| Limit | Value | Note |
|---|---|---|
| `max_depth` | **16** | Intentionally higher than all other limits — depth is the last stop condition |
| `max_children` | 25 | Per node |
| `max_total_nodes` | 300 | Entire manifest |
| `max_llm_calls` | 30 | Per build (set on `RecursiveDecomposer`, not `HierarchyLimits`) |

`trace_pipeline.py` overrides these locally: `max_depth=6, max_total_nodes=60, max_children=12`.

#### Limit enforcement — exact behavior

`StopConditionEvaluator.should_decompose()` stops decomposition for a node when:
- node already has children
- node kind not in `DECOMPOSABLE_KINDS`
- `node.hierarchy_depth >= limits.max_depth`
- `limits.max_total_nodes - len(manifest.nodes) < 2`
- node geometry is a terminal primitive (SPHERE, HEMISPHERE, TORUS)
- `stage_outputs["decomposition_hint"]["is_simple"] == True` AND no `_nested_children`
- node kind is INSTANCE

`tree.can_add_child()` checks depth, children count, and total nodes before each child is added during `_decompose_node`. If it returns False, the loop breaks and remaining children are silently dropped.

#### Validation boundary

LLM output is untrusted. The decomposer operates strictly within this boundary:

**May:**
- parse JSON
- normalize nested children (`_flatten_children`)
- validate/coerce structural fields
- record `ValidationWarning`s
- reject invalid decomposition

**Must NOT:**
- infer spatial transforms
- calculate bounding boxes
- resolve semantic attachment geometry
- mutate Blender state
- commit partially validated nodes

#### Decomposition flow

```
_decompose_node(node)
    │
    ├─ StopConditionEvaluator.should_decompose()
    │       → if False: transition PLANNED→READY, return
    │
    ├─ pre_parsed_children provided?
    │       YES → _parse_pre_parsed_children()   (no LLM call)
    │       NO  → _call_llm_decompose()          (LLM call, increments counter)
    │
    ├─ _flatten_children()
    │       strips "children" key, adds "_nested_children" recursively
    │       pure normalisation — no validation, no manifest writes
    │
    ├─ _parse_child()  [per child]
    │       ├─ label missing → ValueError (child skipped)
    │       ├─ DUPLICATE label → ValueError("DUPLICATE_NODE_ID:…")
    │       │       ↳ entire decomposition returns SKIP result
    │       │         manifest NOT committed, node → FAILED
    │       │         NO auto-rename
    │       ├─ kind: "assembly"|"part" only; anything else → PART
    │       ├─ primitive: invalid → coerce to BOX + ValidationWarning
    │       └─ socket_type: _infer_socket_type()
    │               ├─ corner label patterns → CORNER (no warning)
    │               ├─ ROOT requested + already have ROOT → demote + warning
    │               ├─ index==0 + no ROOT yet → force ROOT + warning if requested≠ROOT
    │               └─ invalid enum → TOP_CENTER (silent fallback)
    │
    ├─ manifest.commit_decomposition()  [atomic]
    │       checks (in order, all-or-nothing):
    │       1. parent exists
    │       2. no candidate label collides with ANY existing manifest node
    │       3. no duplicate labels within this candidate batch
    │          NOTE: "part","part","part" fails check #3.
    │                A later decomposition of a different node could fail check #2.
    │                These are distinct failure modes.
    │       4. exactly one ROOT child
    │       5. no candidate label matches an ancestor label (cycle guard)
    │       → raises ValueError on any failure → node → FAILED
    │
    └─ recurse into ASSEMBLY children
            nested children → pre_parsed_children path (no LLM)
            no nested children → LLM path
```

`warnings: []` in the LLM log is not inconsistent with the duplicate hard-error
behaviour — duplicates are rejected before any warning is recorded.

#### Global label uniqueness — design concern (unresolved)

`commit_decomposition` check #2 enforces globally unique labels across the entire
manifest. This means two different assemblies cannot both contain a child named
`bracket` or `housing`.

The current identity model: label is used as the lookup key in
`manifest.get_node_by_label()`, which is called by Stage 3 and Stage 4 cross-
reference resolvers (`connects_to`, `relative_to`). If labels were scoped,
these resolvers would need a scoped path rather than a flat label.

**Do not change this until the full reference chain is traced.** If labels are
being used as node identity throughout Stage 3/4, this becomes a broader
migration (node_id = generated identity, label = semantic name, references use
scoped paths). Verify before touching.

---

## Stage 1 — (not yet traced)

No `stage1_topology.py` exists in `progressive_v2/stages/`. The file
`backend/core/blender_pipeline/stage1_topology.py` exists at the top level but
its relationship to the v2 pipeline is unconfirmed. Fill this section once
traced.

---

## Stage 2 — Dimensions (`stages/stage2_dimensions.py`)

### CURRENT BEHAVIOR

Assigns physical dimensions to each PART node. Called per-node. Writes
`node.stage_outputs["stage2"]` and calls `output.apply_to_geometry(node.geometry)`.

LLM call per node (temperature=0.1). Falls back to hardcoded defaults on
exception (see `trace_pipeline.py` fallback block).

`BBox.from_geometry()` in Stage 4 reads `stage_outputs["stage2"]` to compute
bounding boxes. Stage 4 raises `Stage4Error` if `stage2` is not populated.

---

## Stage 3 — Semantics (`stages/stage3_semantics.py`)

### CURRENT BEHAVIOR

Adds semantic attachment hints to a PART node's `AttachmentSpec`. Called per-node.

**Simple sockets** (ROOT, TOP_CENTER, BOTTOM_CENTER, FRONT/BACK/LEFT/RIGHT_CENTER,
LEFT/RIGHT/TOP/BOTTOM/FRONT/BACK_END, EMBEDDED, SURFACE_FOLLOW, SCATTER,
CURVE_FOLLOW, VOLUME_FILL, BONE_*, BOOLEAN_UNION, BOOLEAN_INTERSECT) return `{}`
immediately — no LLM call.

**Complex sockets** require LLM call to fill fields defined in `SOCKET_SEMANTICS`.

**Pre-seed from decomposition hint**: fields already present in
`node.stage_outputs["decomposition_hint"]` are extracted first. If all required
fields are already present, the LLM call is skipped entirely. After the LLM call,
`hint_seed` values overwrite LLM output for those fields (hint_seed wins).

**Cross-reference fields** (`connects_to`, `relative_to`) are resolved here by
label lookup. Stage 3 provides the label string; Stage 4 resolves it to a node
and computes geometry. Stage 3 does NOT compute positions.

**`connects_to` / `relative_to` cannot equal the node's own parent** — Stage 3
raises `Stage3Error` if this is detected.

`apply_to_attachment(node.attachment, semantics)` writes results to the
`AttachmentSpec` via `setattr`.

### OPEN DECISION — Stage 3 / Stage 4 reference contract

Stage 3 currently resolves `connects_to` / `relative_to` to a label string.
Stage 4 then calls `manifest.get_node_by_label()` to find the node and computes
geometry independently.

The architectural direction (not yet implemented): Stage 3 should supply an
explicit `reference_node_id` so Stage 4 receives a resolved node reference, not
a label it must re-resolve. This would eliminate Stage 4's need to independently
discover reference geometry and would make BUG-002 easier to reason about.

**Do not implement until the full Stage 3 → Stage 4 contract is traced and
agreed.**

---

## Stage 4 — Transform Resolver (`stages/stage4_resolver.py`)

### CURRENT BEHAVIOR

Pure code — no LLM calls. Deterministic transform computation.

`run()` handles PART nodes. Returns `(ResolvedTransform, AttachmentSolution)`.
`run_assembly()` handles ASSEMBLY/MODEL nodes. Returns `AttachmentSolution`.

**Coordinate convention**: Blender convention throughout.
- +Z = up
- -Y = front
- +Y = back
- +X = right
- -X = left

`BlenderAxis.get_direction()` is the single source of truth for direction→axis
mapping. Do not hardcode direction signs elsewhere.

#### Supported sockets in `run()` (PART path)

All sockets in `_get_resolver()` dispatch table are supported. Unsupported
sockets raise `Stage4Error` — there is no silent fallback in the PART path.

Cross-reference sockets (BRIDGE, STRUT, RELATIVE_TO, RADIAL_BRIDGE) use
two-pass resolution:
- Pass 1: placeholder transform stored (`_resolve_*_pass1`)
- Pass 2: `resolve_cross_reference()` called after all pass-1 world matrices
  are available. Converts desired world matrix to parent-local via
  `child_local = inverse(parent_world) @ child_world`.

#### Supported sockets in `run_assembly()` (ASSEMBLY path)

| Socket | Behavior |
|---|---|
| `ROOT` | Identity transform |
| `TOP_CENTER` | `ref_attachment_local[2] = ref_bbox.max_z` |
| `BOTTOM_CENTER` | `ref_attachment_local[2] = ref_bbox.min_z` |
| `FRONT_CENTER` | `ref_attachment_local[1] = ref_bbox.min_y` |
| `BACK_CENTER` | `ref_attachment_local[1] = ref_bbox.max_y` |
| `LEFT_CENTER` | `ref_attachment_local[0] = ref_bbox.min_x` |
| `RIGHT_CENTER` | `ref_attachment_local[0] = ref_bbox.max_x` |
| **all others** | Delegated to the PART resolver for that socket type via `_get_resolver(socket)`. The resolver's parent-local offset is lifted to world space via `parent_world.transform_point()`, then converted back to `LocalTransform` via `_world_to_parent_local()`. On resolver failure, falls back to identity with `source="ASSEMBLY:{socket}:fallback_identity"`. |

`run_assembly()` requires `parent_world` (WorldMatrix) for all non-ROOT sockets.
Raises `Stage4Error` if not provided.

#### Reference sibling selection in `run_assembly()`

For all sockets, `run_assembly()` iterates `parent_node.children_ids` looking
for siblings with `socket_type == SocketType.ROOT`. Only ROOT-socket siblings
are candidates for the reference bbox.

For `TOP_CENTER` specifically: among ROOT-socket siblings, selects the one with
the greatest `candidate_bbox.max_z`.

For all other sockets: first ROOT-socket sibling wins.

If no ROOT-socket sibling has geometry (stage2 not populated), returns identity
with `source="ASSEMBLY:{socket}:deferred_no_ref_bbox"` and `confidence="low"`.

#### BUG-002 — confirmed code path

`motor_housing_assembly` (TOP_CENTER) inside `base_assembly`. Siblings:
- `base` — socket=ROOT, box 0.4×0.6×0.1m, `max_z=0.05`
- `vertical_rod` — socket=TOP_CENTER (not ROOT), excluded from candidates

Only `base` is a ROOT-socket sibling → `ref_bbox.max_z = 0.05` →
`motor_housing_assembly` placed at local Z=0.05.

**Confirmed bug**: TOP_CENTER restricts reference candidates to ROOT-socket
siblings. Incorrect when the semantic support sibling is non-ROOT.

**Fix contract not yet settled.** Do not document a specific fix rule until
the reference-selection contract for Stage 4 is finalized.

#### BUG-003 / BUG-004 — fixed

Previously: any assembly socket not in the 7 named cases hit `else` → identity
at origin. All children inherited `world_matrix` at `[0,0,0]` → flat output.

Fix: `else` branch now delegates to `_get_resolver(socket)` (the same dispatch
table used by PART nodes). The resolver's parent-local offset is lifted to world
space via `parent_world.transform_point()`, then converted back to `LocalTransform`
via `_world_to_parent_local()`. On resolver failure, falls back to identity with
`source="ASSEMBLY:{socket}:fallback_identity"` (not `"unsupported"`).

The controller's deferred-check in `_ensure_assembly_transform` and
`_process_assembly` now treats both `"deferred_no_ref_bbox"` and
`"fallback_identity"` as deferred, so a failed resolver does not permanently
lock the assembly to identity — it retries on the next iteration.

#### `_get_parent_bbox()` — PART path bbox selection

For ASSEMBLY/MODEL parents, bbox strategy depends on socket type:

- `FRONT_FACE`, `BACK_FACE`, `LEFT_FACE`, `RIGHT_FACE`, `TOP_FACE`,
  `BOTTOM_FACE`, `FRONT_CENTER`, `BACK_CENTER`, `LEFT_CENTER`, `RIGHT_CENTER`,
  `RADIAL` → `_get_root_only_bbox()` (ROOT child's intrinsic geometry only)
- all others → `_get_root_child_bbox()` which delegates to
  `_get_assembly_aggregate_bbox()` (union of all children's transformed bboxes)

`_get_root_child_bbox()` is a thin wrapper around `_get_assembly_aggregate_bbox()`
kept for call-site compatibility.

`_get_assembly_aggregate_bbox()` transforms each child's intrinsic bbox
(Stage 2 geometry) into assembly-local space via `child.transform_state.local_transform`.
Falls back to ROOT-child-only bbox if no child has stage2 data.

---

## Executor (`controller.py` + `executor.py`)

### CURRENT BEHAVIOR

#### Build loop (`controller.py`)

```
controller._is_actionable(node)
    PART + READY + stage4 present → build geometry
    ASSEMBLY + no children → run_assembly() (leaf assembly path)
    ASSEMBLY + all children VERIFIED → merge

controller._process_assembly(node)
    no children + expected_child_count or _nested_children set
        → raises RuntimeError("DECOMPOSITION_COMMIT_INCOMPLETE") → node FAILED
    no children + PLANNED → re-decompose (max 5 LLM calls)
        → if children added: recompile DAG, record_event("graph_recompiled"), return
        → if still no children: fall through to leaf_assembly path
    no children + READY → verify as leaf_assembly (type="leaf_assembly")
    children done → merge children

_ensure_assembly_transform(node)
    lazy-computes assembly world matrix via run_assembly()
    deferred if source contains "deferred_no_ref_bbox" OR "fallback_identity"
```

`_build_loop` safety limit: `max_iterations = len(self.manifest.nodes) * 3`, updated
each iteration via `max_iterations = max(max_iterations, len(self.manifest.nodes) * 3)`
so re-decomposition that adds nodes during the loop does not cause premature exit.

Unknown `NodeKind` in `_KIND_HANDLERS`: calls `_handle_failure` with
`"UNSUPPORTED_CAPABILITY"` error — does NOT silently mark VERIFIED.

`all_children_done()` (manifest.py) requires VERIFIED or SKIPPED.
FAILED does NOT count — an assembly with a FAILED child will not merge.

#### Transform ownership contract (`executor.py`)

`USE_HIERARCHICAL_TRANSFORMS = True` is hardcoded. The executor is a **read-only
consumer** of `transform_state.world_matrix`. It must never write it.

Authoritative write path (only):
```
Stage 4 → local_transform → controller._propagate_new_world_transform()
        → NodeTransformState.compute_world() → world_matrix
```

If `transform_state.world_matrix` is `None` when `_compute_world_transform()` is
called, it raises `RuntimeError` — the node fails rather than falling back to
legacy. There is no legacy fallback path remaining.

#### Blender object placement (`executor.py`)

Each PART node is placed by passing `world_matrix` as a 4×4 matrix directly to
`obj.matrix_world = mathutils.Matrix(matrix_rows)` in the Blender script. No
Euler reconstruction. No `bpy.ops` location parameter.

Sphere is the only primitive that still uses `location=tuple(pos)` in
`primitive_uv_sphere_add` — it does not receive `matrix_rows`. This is a
minor inconsistency but does not affect hierarchy correctness.

#### Assembly merge (`executor.py` — `merge_assembly`)

Creates a Blender Empty at the ROOT child's world position. Parents all child
objects to it via:
```python
obj.parent = empty
obj.matrix_parent_inverse = empty.matrix_world.inverted()
```
Objects do not move — their world positions were already set by
`_compute_world_transform`. The parent-child tree in the Blender outliner is
real but cosmetic: all spatial positioning is done by world-space placement,
not by the parent-child chain.

---

## State Machine (`manifest.py`)

### CURRENT BEHAVIOR

```
PLANNED ──→ DECOMPOSING ──→ READY ──→ BUILDING ──→ VERIFYING ──→ VERIFIED
   │                          │                                      │
   └──────────────────────────┘                                   MERGING ──→ VERIFIED
   (PLANNED→READY direct allowed)
                              │
                           FAILED ──→ RETRYING ──→ READY
                                    └──→ SKIPPED  (terminal)

VERIFIED ──→ STALE ──→ READY
```

Valid transitions are enforced by `_VALID_TRANSITIONS` dict. Any unlisted
transition raises `ValueError`.

`MERGING` is in the diagram but NOT shown in the state machine table in the
previous blueprint version — that was a doc error. `MERGING` is a real state:
`VERIFIED → MERGING` and `MERGING → VERIFIED` are both valid.

`FAILED → RETRYING → READY` is the retry path. `transition()` increments
`node.retry_count` when transitioning to RETRYING.

### KNOWN DEFECT — no transition history

`transition()` mutates `node.state` in place. There is no record of prior
states, timestamps, or failure reasons beyond `node.error_message` and
`node.error_stage` (single values, overwritten on each failure).

This is the primary reason BUG-001 cannot be traced from the manifest alone.
The cage_assembly's state history is gone by the time the manifest is read.

### OPEN DECISION — transition history

Proposed addition to `ManifestNode`:

```python
state_history: List[Dict] = field(default_factory=list)
# Each entry: {"from": str, "to": str, "ts": str, "reason": {"code": str, "message": str} | None}
```

`transition()` would append to `state_history` before mutating `node.state`.
This is distinct from `ValidationWarning` (coercion record) and from
`error_message` (last failure string).

**Not yet implemented.** Implement as a standalone change before touching
other architecture.

---

## Persistence

| File | Location | Purpose |
|---|---|---|
| `manifest.json` | `data/builds_v2/{model_id}/` | Full build state, atomic write via `.tmp` rename |
| `llm_log.json` | `data/builds_v2/{model_id}/` | Raw LLM prompts + responses + warnings, append-only |

`prune_old_builds(keep=3)` deletes all but 3 most-recent manifests (by
`manifest.json` mtime). Directories without `manifest.json` are ignored.

**Operational risk**: pruning destroys forensic evidence for failed builds.
No pin/archive mechanism exists. If a build fails and a newer build runs,
the failed manifest may be pruned before the failure is investigated.

---

## Change Log

| Date | Change | File(s) |
|---|---|---|
| 2026-09-30 | `max_depth` raised from 8 → 16 (intentionally above other limits) | `hierarchy.py` |
| 2026-09-30 | Duplicate decomposition labels are a hard `DUPLICATE_NODE_ID` failure; no auto-rename and no manifest commit | `decomposer.py` |
| 2026-09-30 | BUG-003/BUG-004 fixed: `run_assembly()` `else` branch now delegates to `_get_resolver(socket)` instead of returning identity. Deferred-check in controller updated to also treat `"fallback_identity"` source as deferred. | `stage4_resolver.py`, `controller.py` |
| 2026-09-30 | Build loop `max_iterations` updated each iteration to account for nodes added by re-decomposition. Unknown `NodeKind` now calls `_handle_failure` instead of silently marking VERIFIED. `_process_assembly` raises `DECOMPOSITION_COMMIT_INCOMPLETE` if `expected_child_count` or `_nested_children` is set but no children were committed. DAG recompiled after successful re-decomposition. | `controller.py` |
