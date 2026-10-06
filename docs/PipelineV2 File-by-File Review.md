# PipelineV2 file-by-file review

## 0. Scope and honesty

- Reviewed: the uploaded zip (49 files, \~24k lines). `py_compile` passes on all files. **Nothing else was executed, and no code was changed.**
- **The zip has no tests**, so I cannot confirm any claim that tests exist or pass.
- **Missing from the zip:** `stage0_understanding.py`, `core/blender_ops.py` (`parse_op_output`), `tool_gateway`, `scheduler`, `endpoint_agent`, the API route, the websocket and the frontend. Integration with these cannot be reviewed from this upload.
- Depth: **R** = read the relevant code, **G** = grep and targeted reads only, **N** = not opened (earlier-list items for these remain unverified).

## 1. Claims from earlier reports that this code contradicts

| Earlier claim | What the code shows |
| --- | --- |
| "7 defect gates pass; `perform_ground_lift_safe` / `compute_build_status` exist" | **Neither function exists in production.** The controller still calls `_lift_to_ground_plane`, and `ProductionSceneAudit` has only coarse connectivity and orientation-label checks. The gate tests used local helpers. |
| "Repair loop feeds violations to Stage 2" | `scene_quality_feedback` is written by the controller and **read by no stage**. A repair is a blind re-roll of the same prompt. |
| "`verify_attempt_absent` proves no tagged mesh/curve/image/light remains" | Only objects, collections and materials are tagged (`sentinel_build_id`). **Meshes, curves, images and lights are never tagged**, so the check cannot see them. |
| "Evaluated-mesh readback via depsgraph" | `world_bounds` and `dimensions` in the readback script come from `_obj.bound_box` (the **unevaluated** mesh). Only `local_dimensions` uses the evaluated object. Connectivity and ground checks use the stale bounds. |
| "Booleans non-destructive" | True in the transaction path (`_boolean_fragment`). The older `_apply_boolean` (`modifier_apply`) still exists in the executor. Check no path reaches it. |
| "No heuristic ROOT" | Partly. All-CORNER/RADIAL/ARRAY/RADIAL_BRIDGE sets now anchor to the assembly frame. **Mixed sets still promote child 0 to ROOT**, and duplicate ROOTs are demoted to `BOTTOM_CENTER`. |
| "H1 fixed with static templates" | `_build_script` is used **twice** in the executor. Flush header, cleanup, readback, ledger sweep, bbox backfill, render evidence, lift, boolean fragment and 15+ other scripts still interpolate values with `repr()`/f-strings. Safer than raw interpolation, but not the JSON-payload pattern, and untested for most. |

## 2. Confirmed defects (highest value first)

1. **`_compute_outcome` has no required-levels list.** SUCCESS needs only: Blender connected, readback ok, node states ok. If the audit or spatial verification never ran (stats key absent), the level is simply missing and does not block. Render evidence is not a level at all. `compute_completion_status()` can also return `IN_PROGRESS` for a finished build.
2. **Spatial failures become `COMPLETED_DEGRADED`**, and the policy maps that to `done_with_warnings`. Floating and interpenetration are warnings unless the level is PARANOID. A model with floating parts can be reported as done.
3. **Ground lift (`_lift_to_ground_plane`, real path):** (a) min Z is taken from unevaluated vertices of all verified PART/INSTANCE objects, **including hidden boolean cutters** whose overshoot pushes the model up; (b) it adds to each part's `location.z` in parent-local space, which is wrong if any parent has rotation or scale (the pipeline applies a uniform root scale); (c) assembly empties and manifest transforms are not updated.
4. **Repair loop:** old attempt stays visible while the new one is committed (cleanup only at `keep_final`), so renders and any scene-wide check can see both. Failing-node choice for `disconnected_component` is `component[0]` (alphabetically first node), not the cause. Initial and post-repair readback failures raise bare `RuntimeError`, not `QualityGateFailed`.
5. **Readback loosens itself:** `has_cuts` skips the strict dimension check for **every sibling** of any cutter; `_boolean_dimensions_match` accepts anything between 5% and 115% per axis (no volume check despite the docstring); `_dimensions_match` **sorts** dimensions so orientation is invisible (a vertical blade equals a flat one); 15% relative tolerance everywhere; missing `geometry.size` silently skips the check; emission, IOR and clearcoat are never read back.
6. **Destructive modifiers by default:** `apply: True` in `ModifierSpec`, `from_dict` default, executor `.get('apply', True)` (two places), and an explicit `apply=True` in `modifiers.py`.
7. **Auto-bevel on every BOX** (`constraint_planner`, `min(size)*0.08`, destructive) regardless of style.
8. **`_resolve_corner` infers placement from label text** ("left", "right", "front", "back", "rear", "top", "upper") and **defaults silently to front-left**: four corner parts with unrecognized labels stack in one corner. Fixed 0.8 inset. About 96 other label/substring dispatch hits across stage 2/3/4, materials, modifiers, decomposer, constraint planner and design fidelity.
9. **Single 6k-line MCP call.** `flush` sends the whole transaction in one `execute_blender_code`, with no in-script try/except, no chunking, and no timeout strategy. Large models (300 nodes) risk the MCP socket timeout and a frozen Blender.
10. **No clean-scene check.** The attempt collection is linked straight into the live scene. Nothing detects a default cube or foreign objects, and `ProductionSceneAudit` ignores objects without `node_id`.
11. **Sweep cannot reclaim crashed builds:** `sweep_candidates` skips manifests with status `in_progress`, and a crashed build stays `in_progress` forever. Needs a heartbeat or lease.
12. **`status_literal_guard` is trivial:** four hard-coded files, three literal strings; misses lowercase literals, `.success`, `!=`, `in (...)`.
13. **`render_evidence`** creates a camera and light in the scene collection (untagged, not removed), overwrites `scene.camera`, measures with unevaluated bounds, does not hide a superseded attempt, and sets no world or background.
14. **Hidden cutter in renders:** the cutter has `hide_viewport` and `hide_render` set. Confirm in an actual render (not only depsgraph readback) that the cut survives.
15. **`scene_ir`:** `boolean_operations` records only `cutter_node_id` (no target). `_serialized` falls back to `vars(value)` and `default=str` in the fingerprint, which can embed memory addresses and make fingerprints nondeterministic.
16. **Ledger:** `_persist` rewrites the whole manifest on every transition; no locking (`records` mutated from async code); `sweep_orphans` builds its script by interpolation and does not check images/lights/curves data.

## 3. File-by-file: what to change

| File | Depth | Verdict | Change |
| --- | --- | --- | --- |
| `attempt_ledger.py` | R | Good design, gaps | Tag meshes/curves/images/lights at creation (or snapshot datablock counts before and after) so `verify_attempt_absent` is real. Add a build lease/heartbeat so crashed builds are sweepable. Static-template sweep script. Guard concurrent builds with a lock. |
| `outcome_policy.py` | R | Correct, fail-closed | Add `IN_PROGRESS` to an explicit `NOT_DONE` list; test an unmapped future status. Decide whether spatial-failure degraded maps to done (see defect 2). |
| `status_literal_guard.py` | R | Weak | Replace with an AST scan for comparisons on status/completion fields across the backend; fail on any literal outside `outcome_policy`. |
| `scene_quality.py` | R | Not the 7 gates | Relative contact tolerance; penetration and attachment gap against the declared host; clearance joints as edges; stray-object detection; role-duplicate and requirement checks; oriented bounds; use `reference_node_id`, drop label lookup; consistent defect schema (`gate`, `node_id`, `measured`, `expected`, `severity`). |
| `scene_ir.py` | R | Good boundary | Add boolean target ids; deterministic serialization (no `default=str`, no `vars()`); schema version for each field group; consider Pydantic here first. |
| `capabilities.py` | R | Fine | Add Blender-version table (Principled sockets); make vocabulary generate planner prompts and emitters; add `emission_*`, `ior`, `coat` fields. |
| `repair.py` | R | Fine | Move the 0.002 thin-panel depth to config; allow repairs to emit typed events; radial slots assume one group per parent. |
| `transaction.py` | R | Good, needs chunking | Chunk the transaction (with rollback covering all chunks); compile in a scratch collection then link; payload-based fragments; validate cutters have a target before build; cutter target = ROOT sibling only (document or generalise). |
| `executor.py` | R/G | Largest risk | Default `apply` False; delete or gate `_apply_boolean`/`build_boolean_cut`; JSON-payload templates everywhere; tag meshes; scene cleanliness check at start; boolean solver and manifold checks; evaluated bounds in bbox backfill; chunked flush with timeouts. |
| `controller.py` | R/G | Heavy, needs split | Required-levels outcome; typed readback failures; ledger-owned repair with superseded attempt hidden during repair; real repair feedback consumption; replace `_lift_to_ground_plane` with the safe version (exclude cutters/hidden, world-space, after audit). Split the 2.9k-line file (phases into modules). |
| `manifest.py` | R/G | Good outcome plumbing | Single status writer only; version `stats` keys; Pydantic or schema-driven serialization later; `compute_completion_status` must not return `IN_PROGRESS` on finished builds. |
| `readback.py` | R | Needs rewrite of checks | Evaluated bounds; keep strict dimension check per part; real volume check for cut parts; oriented (unsorted) comparison against declared axes; read back emission/IOR/coat; tolerance by modifier class; typed failure; JSON-payload script. |
| `decomposer.py` | G | Partial | Remove child-0 promotion and `BOTTOM_CENTER` demotion; use structured re-prompt then typed failure; explicit placement fields for repeated children; cap exhaustion = incomplete-plan result. |
| `stages/stage4_resolver.py` | R (corner) | Label dispatch | Resolve corners/arrays from structured fields (signs, array spec); fail typed when missing; verify primitive local bounds against registry (hemisphere min 0.00041 vs 0); contact coordinate minus child's min along axis. |
| `stages/stage3_semantics.py` | G | OK | Verify the prompt states the hidden-target count; relevance order tests. |
| `stages/stage2_dimensions.py` | G | Fragile | Fallback dimensions must use the scale anchor; remove hard-coded multipliers; consume `scene_quality_feedback`. |
| `constraint_planner.py` | G | Wrong default | Bevel only by style field (realistic); `apply=False`; replace keyword tokenizer with Stage 0 structured fields. |
| `instances.py` | G | Improved | Now uses `world_matrix`. Add rotated-parent and nested-instance tests; verify scale reaches all three emit paths. |
| `verification.py` | G | Severity wrong | Interpenetration and floating are errors unless declared; avoid O(N²) (AABB broad phase first); evaluated mesh. |
| `render_evidence.py` | G | Leaky | Tag camera/light and remove them; restore `scene.camera`; hide other attempts; evaluated bounds; set world. |
| `materials.py`, `modifiers.py` | G/N | Hardcoded presets | External config; polymorphic modifier specs; `apply` default False; version-safe sockets. |
| `booleans.py` | N | Unreviewed | Check for destructive `modifier_apply` and cutter scale-restore; unify with `_boolean_fragment` or delete. |
| `design_audit.py`, `design_fidelity.py`, `hierarchy.py` | G/N | Unreviewed | Leaf-corner envelope for rotated parts; plural regex; limits (25 children / 300 nodes) configurable with explicit incomplete-plan reporting. |
| `reference_brief.py` | G | Fragile | Greedy `{...}` regex; use structured output and a schema. |
| `dag.py`, `transforms.py`, `euler_conversion.py`, `node_types.py`, `model_contract.py` | N | Unreviewed | Keep deferred items deferred; check `transforms.py` unit-scale assert, per-edge BFS in `dag.py`. |
| `evaluation.py`, `audit_transforms.py`, `run_audit.py`, `trace_pipeline.py` | N | Tools | Make `evaluation.py` the baseline harness (real Blender cases, metrics); keep the others dev-only. |
| `__init__.py` | N | Unreviewed | Check exports match the module list; remove stale names. |
| `stages/__pycache__/` | - | Remove from zip | Commit `.gitignore`. Files include both 3.11 and 3.12 bytecode. |

## 4. Integration fixes (needed before further feature work)

1. One outcome function with an explicit required-levels list: `inventory`, `dimensions`, `materials`, `attachments/contacts`, `scene_quality`, `spatial`, `render`. Missing level = not passed. SUCCESS only if all required levels ran and passed.
2. One defect schema shared by readback, audit, spatial and the API.
3. Ledger owns every attempt. Hide a superseded attempt during repair, and verify absence for meshes, curves, images and lights (tag at creation).
4. Typed errors throughout (`QualityGateFailed`, `ReadbackFailed`, `TransformFailure`); no bare `RuntimeError` after commit.
5. Replace the lift with a measured, world-space, post-audit version that ignores hidden objects, and update manifest transforms.
6. Feed repair feedback into Stage 2/3/4 prompts, and choose targets from the finding's causal node (the part and its declared host), not `component[0]`.
7. Consumers (not in this zip): confirm all use `outcome_policy`, and add the AST guard.

## 5. Order of work

1. Outcome levels and defect schema (small, high-value).
2. Tag datablocks, clean-scene check, ledger-owned repair with hidden superseded attempt.
3. Readback rewrite (evaluated bounds, strict dims, volume check) with negative controls.
4. Safe ground lift and verification severity.
5. `apply` default False plus auto-bevel by style.
6. Structured corner/array placement (remove label inference and child-0 promotion).
7. Production gate rewrite; feedback consumption in Stage 2.
8. Chunked, JSON-payload scripts; scratch-collection commit.
9. Baseline eval (8-10 prompts, real Blender, 5 runs each).
10. Then materials upgrades, geometry capabilities, renders critic.

Each step: failing test first, raw output, mutation check, and the status table at the top of every report.