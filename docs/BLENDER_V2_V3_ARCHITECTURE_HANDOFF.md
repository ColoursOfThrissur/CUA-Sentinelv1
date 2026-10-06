# Blender V2/V3 architecture handoff

Code-grounded snapshot: 2026-10-05. Scope: natural-language **model creation** through the backend. V2 is the only active runtime. V3 is archived. V2 should still not be described as a proven arbitrary-complex-scene generator until live visual baselines pass.

## 1. Entry points and routing

```text
Chat/task -> endpoint_agent.py ---------+
Tool call -> tool_gateway.py -----------+--> progressive_v2.run_progressive_build
POST /api/blender/build -> routes/blender.py -+                |
core.blender_pipeline package export ---------+                +--> Blender MCP execute_blender_code

Archived V3 source --> _archived/progressive_v3 (no runtime caller)
```

- `backend/agents/endpoint_agent.py`: prepares/extracts conversational tool steps. A `blender:build_spec`, a multi-step Blender plan, or a primitive plan is rerouted to a **single build using the original whole prompt**. It suppresses the extracted individual steps after the pipeline returns. This is not a direct per-primitive construction in the normal multi-part path. It converts the result into tool result/summary and carries a build error into task reporting.
- `backend/core/tool_gateway.py`: both `blender:build_spec` and `blender:build_progressive` handlers call V2. It obtains a model manager and MCP manager, passes the description, and returns status/counts/object names/errors. Other direct Blender tools in this file are separate from the model-building pipeline.
- `backend/api/routes/blender.py`: `POST /api/blender/build` calls V2 directly; the request field is `description` (3–2000 characters). `use_llm_modifiers` is passed into V2 and controls style-inferred modifiers while preserving explicit modifiers. The route returns a JSON `ok: false` body on build failure; the code shown does not set a distinct HTTP failure status. Other routes in this file (for example primitive readback) are separate diagnostics.
- `backend/core/blender_pipeline/__init__.py`: exports V2's `run_progressive_build` and `HierarchyLimits`.
- `backend/api/server.py` mounts the build route under `/api/blender`. `backend/core/mcp_manager.py` owns the MCP connection; `call_locked` checks `backend/config/mcp_tools.lock.json` for an `internal_only` tool before calling `execute_blender_code`. `backend/config/mcp_apps.yaml` configures the Blender app connection. The generated Blender Python is executed on the Blender side of that MCP boundary, not in the FastAPI process. `backend/core/blender_ops.py:parse_op_output` extracts the Sentinel JSON returned by that script.
- The lockfile specifies `uvx blender-mcp` as the server and marks `execute_blender_code` internal-only; the checked-in `mcp_apps.yaml` entry has `enabled: false`. Runtime activation/connection is therefore an environmental prerequisite and should be inspected separately from pipeline planning. This handoff does not claim the MCP server or Blender add-on is currently connected.
- `backend/core/blender_pipeline/broadcast.py` emits non-fatal websocket `AGENT_TRACE` progress events for V2 stages. These UI events are progress telemetry, not verification evidence.
- `backend/core/blender_pipeline/primitive_readback.py` supports a separate primitive-interpretation diagnostic; it is not an automatic visual QA stage of either full-model build. `backend/core/blender_pipeline/_archived/` contains older pipelines/stages and is not the current model-creation route. `backend/core/spec3d/` is a separate approval/save workflow, not a hidden stage of V2/V3 creation.
- All three active call sites pass `HierarchyLimits(max_depth=60, max_children=200, max_total_nodes=2000)`. These are safety ceilings, not evidence that a 2000-node design is practical or visually correct.
- `BLENDER_BUILD_MODE` selects V2's execution branch; default is `transaction`. `BLENDER_REFERENCE_RESEARCH` defaults to enabled and can disable V2's web-reference attempt. `BLENDER_PIPELINE_MODE` is read **inside V3's direct runner only**; it does not switch the current normal routes back to V3.

## 2. V2: end-to-end default transaction path

```text
prompt
  -> Stage 0 understanding + optional researched reference brief
  -> persistent BuildManifest (MODEL root, containment tree)
  -> recursive LLM decomposition (MODEL/ASSEMBLY/PART nodes)
  -> explicit-requirement repair + structural constraints + dependency DAG
  -> off-scene build loop: Stage 2 dimensions -> Stage 3 semantics -> Stage 4 transforms
  -> root/required-node check -> scale fit -> design audit
  -> frozen transaction validation -> geometry/material/modifier/boolean/hierarchy script
  -> Blender MCP transaction -> ground lift -> spatial verification
  -> manifest completion status + API/task result
```

1. **Initialize and scale.** `ProgressiveController.run` creates a `BuildManifest`, currently calls `prune_old_builds(keep=3)`, and constructs a root `MODEL` node. Unless a caller supplied `stage0_output`, `Stage0Understanding.run` asks the model for category, style, ground-contact intent, and a physical scale anchor. A Stage 0 failure is logged and the pipeline can continue with degraded scale evidence. `ReferenceBriefGenerator.run` can search the web and ask the model once for shape, material, palette, proportion, and contextual component hints. Generic search results cannot override user-specified scale; research scale adoption requires the code's cross-checked evidence rules. `ModelContract.from_stage0` records the shared scale convention.
2. **Decompose.** `RecursiveDecomposer.decompose` expands the root/assemblies into nested assemblies and leaf parts. It uses LLM responses, parsing/coercion, stop conditions, tree limits, expected-child contracts, and a maximum of 20 decomposition LLM calls from this controller call. It may reuse nested children already supplied by an earlier response. `ContainmentTree` enforces depth, child count, cycles, orphan checks, and traversal. `BuildManifest` stores node identities, parent/child links, states, sockets, geometry hints, and stage output.
3. **Post-decomposition constraints.** `DesignFidelityValidator` extracts some explicit count/form requirements from the prompt, can clone a representative subtree for missing counted repetitions, and validates them again before submission. `StructuralConstraintPlanner` annotates supported topology-plus-prompt patterns (including radial struts, repeated definitions, spatial contracts, longitudinal attachments, inset fit, material/finishing intent). `DependencyDAG.from_manifest` orders work separately from the containment tree; containment answers “belongs to,” dependencies answer “must be resolved first.” `capabilities.py` declares the subset the transaction compiler actually accepts.
4. **Off-scene planning loop (default).** `_plan_then_commit_transaction` temporarily sets `mcp_manager=None` and runs `_build_loop`; the loop's “verified” states here are **planning/simulation states**, not proof of Blender objects. Actionable `PART` nodes pass through Stage 2 dimensions, Stage 3 socket semantics, Stage 4 deterministic transform resolution and transform propagation. `ASSEMBLY`/`MODEL` nodes resolve their local transform and become resolved after children; the loop checkpoints periodically. Root resolution and required-node failures are checked before commit. An empty or deadlocked root is rejected, not submitted.
5. **Pre-commit fit/audit.** `DesignProposalAudit.fit_to_scale_contract` applies a uniform root-scale correction from resolved part bounds; `DesignProposalAudit.run` checks explicit requirements, selected orientation/relationship contracts, radial ring-at-end patterns, U-fork inset clearance, and model envelope. Its warnings are not errors. This audit is deterministic and finite in scope; it does not inspect a rendered image or certify artistic quality.
6. **Freeze/compile/submit.** `SceneTransactionCompiler.validate` checks structural constraints, prompt fidelity, geometry, supported primitives/modifiers/material values, world transforms, repeated slot collapse, and expected assembly children. It freezes a plan fingerprint, buffers all part fragments with `BlenderExecutor`, adds boolean cuts, then adds assembly/root objects and parenting. `BlenderExecutor.flush` sends the buffered script through `mcp_manager.call_locked("blender", "execute_blender_code", ...)` and parses the Sentinel JSON response. Its flush may make a further bounding-box readback call. A failed transaction raises `ScenePlanError`/build failure. The default path is *one construction submission*, not one Blender call per part.
7. **Post-commit.** `_lift_to_ground_plane` adjusts the root to bring the low point to Z=0 when applicable. `_verify_whole_model` uses `SpatialVerifier` plus ground-plane and embedment checks for interpenetration/floating/invalid placement. Errors are recorded as spatial failure; warnings need not fail. `manifest.finalize()` persists the outcome. `_build_result` returns counts, LLM/Blender operation statistics, object names, errors, and a status. Importantly, V2 sets `success=True` for both `SUCCESS` and `COMPLETED_DEGRADED`; a consumer must inspect `completion_status` and spatial errors, not just `success`.

### V2 alternate execution path

If `BLENDER_BUILD_MODE` is not `transaction` (or an MCP manager is absent), `ProgressiveController.run` calls `_build_loop` directly. With MCP, it stages ready part batches, flushes them, verifies flushed parts, handles assemblies, checkpoints, and may retry failures. Without MCP it follows a simulation/fallback path; it must not be described as a completed physical Blender build. This is a distinct path from the default frozen transaction, with different timing and failure exposure. The no-MCP behavior deserves separate integration tests before use as a production success signal.

### V2 files: roles and activation

| File | Role in the current V2 implementation |
|---|---|
| `controller.py` | Orchestrator, default/alternate mode selection, build loop, stage calls, assembly handling, ground lift, whole-model verification, result. Active. |
| `manifest.py` | `BuildManifest`, `ManifestNode`, `GeometrySpec`, `MaterialSpec`, `AttachmentSpec`, state machine, persistence, checkpoints, LLM logs. Active. Persists under `backend/data/builds_v2/{model_id}/`; initialization prunes older build directories beyond three. |
| `node_types.py` | Node, socket, primitive and phase enums. **Vocabulary is wider than runtime support**; animation/rigging/physics/geometry-node enum values are not active creation handlers. |
| `hierarchy.py` | Containment tree and limits/validation. Active. |
| `decomposer.py` | Recursive LLM decomposition, response parsing, nested children, stop conditions, naming/placement hints. Active. |
| `dag.py` | Dependency graph, readiness/blockers/cycle handling. Active. |
| `stage0_understanding.py` (parent folder) | LLM object/scale understanding before decomposition. Active unless caller supplies Stage 0. |
| `reference_brief.py` | Optional bounded search plus LLM reference synthesis; returns typed shape/material/proportion/context hints. Active, with fallback. |
| `model_contract.py` | Shared world-scale contract from Stage 0. Active. |
| `design_fidelity.py` | Selected explicit prompt counts and shape rules; repairs/validates repeated parts. Active. Not a general natural-language completeness proof. |
| `constraint_planner.py` | Converts selected structural/spatial patterns into solver hints and fills some material/finishing intent. Active. |
| `stages/stage2_dimensions.py` | Per-part dimensions in metres; LLM call unless a repeated definition can reuse prior dimensions; retry/default fallback and inset-fit constraint. Active. |
| `stages/stage3_semantics.py` | Socket-specific semantic fields; skips LLM if hints suffice, otherwise calls LLM; repeated radial/array slots derived from sibling order. Active. |
| `stages/stage4_resolver.py` | Deterministic placement and orientation from sockets, bounds, semantics and cross-references; also assembly transforms. Active. No LLM at this stage. |
| `transforms.py` | Local/world matrices, composition, revision/freeze/staleness, propagation and validation. Active. |
| `euler_conversion.py` | Matrix-to-TRS/Euler utility imported by `transforms.py`; not a separate planning stage. |
| `design_audit.py` | Final pre-commit design/spatial proposal checks and scale fit. Active in transaction mode. |
| `capabilities.py` | Executable transaction allowlist and validation: 15 supported mesh primitive enum entries, 11 modifier types, Principled material template. Active. Custom arbitrary node trees and many declared future features are rejected. |
| `transaction.py` | Frozen plan validation/compilation; buffers parts, boolean cutters and assembly hierarchy, flushes construction. Active in default transaction mode. |
| `executor.py` | Blender Python fragment generator and MCP caller, materials/modifiers/primitive handlers, object/bbox verification and cleanup methods. Active. Contains alternate per-operation methods as well as buffered transaction methods. |
| `materials.py` | PBR preset catalog and phrase-to-preset selection used by planning/executor. Active helper, not proof of photorealism. |
| `modifiers.py` | Typed modifier specs/presets/style mapping consumed by constraints/executor. Active helper. |
| `verification.py` | MCP-backed object, intersection, floating and mesh checks; used by controller's whole-model verification. Active. |
| `booleans.py` | Separate `BooleanManager` utility. Present, but the default frozen transaction uses `transaction.py`'s boolean fragment rather than this manager. |
| `instances.py` | Linked/collection instance utility and group finder. Present; do not infer that the normal MODEL/ASSEMBLY/PART controller dispatch executes `INSTANCE` nodes. |
| `audit_transforms.py` | Diagnostic transform/provenance report utility; not a mandatory controller phase. |
| `run_audit.py`, `trace_pipeline.py` | Diagnostic/replay entry points, not called by normal builds. |
| `test_transaction_compiler.py` | Unit/regression tests, not a production stage. |
| `stages/__init__.py`, `__init__.py` | Exports, not independent processing stages. |

`executor.py` calls its combined script submission “atomic,” but Blender can execute earlier statements before a later statement raises. The executor attempts scoped collection cleanup on failure; do not equate one MCP call with a database-style atomic commit. The manifest persistence and Blender scene state are separate systems.

## 3. V3: end-to-end experimental direct-call path

```text
prompt -> one IntentPlanner LLM response -> ModelIntent
       -> IntentNormalizer (infer missing attachments)
       -> IntentCompiler (expand counts, basic geometry/material/modifier choices)
       -> RelationLayout + uniform XY fit -> Scene
       -> V3Preflight + SceneAudit -> optional one LLM plan repair on audit failure
       -> V3Executor one Blender transaction -> readback verification
       -> SUCCESS or rollback/FAILED
```

1. `V3Controller.run` starts an empty V3 `Scene` and calls `IntentPlanner.plan`. Unlike V2, it does **not** run `Stage0Understanding` or `ReferenceBriefGenerator` itself. It merely includes a caller-supplied `stage0_output` as hints in the prompt. The normal entry points currently do not call V3.
2. `IntentPlanner` asks for one JSON intent: components, primitive, count, material/style/parameters, relations, overall extent, confidence. `ModelIntent.from_dict` normalizes keys, checks primitives and counts, filters unrecognized relation kinds, and lets a dimension explicitly stated in the user prompt override the planner extent. This is a compact plan, not a multi-stage decomposition or true product specification.
3. `IntentNormalizer.complete` infers missing component relations from explicit parent keys, prompt clauses and earlier components; it also infers horizontal orientation for some elongated primitives. These are heuristics and can attach a part to the wrong host. Inferred relations are recorded.
4. `IntentCompiler.compile` expands each component count into physical `ScenePart` instances (at most 400 total); assigns geometry dimensions/defaults, basic keyword-based material properties and selected modifiers; calls `RelationLayout.resolve`; and uniformly shrinks XY positions/geometry if necessary to meet a declared extent. `RelationLayout` maps repeated subjects to repeated targets, gives radial slots, resolves relative offsets and parent IDs, and rejects unknown/cyclic attachments. It does **not** solve contact/clearance constraints as deeply as V2 Stage 4.
5. `V3Preflight` checks finite numeric values, primitive/modifier support, sizes, identities and parent references. `SceneAudit` checks duplicate identity/path, parent cycles, coincident repeated slots and declared XY span. If these checks return errors, controller allows one `IntentPlanner.repair` response and recompiles. **Exceptions during intent parsing or compilation do not enter this repair loop.**
6. `V3Executor` serializes the V3 `Scene` into a generated Blender Python script, creates one per-attempt collection, builds meshes/materials/modifiers, sets parent links and emits a Sentinel receipt. A Blender-side exception removes that collection. `verify_committed_scene` makes a separate MCP call to check expected meshes, part IDs, parent names, positions, material presence, modifiers and XY span. Readback failure triggers scoped rollback and `FAILED`.
7. `Scene.save` writes a V3 manifest under `backend/data/builds_v3/{model_id}/manifest.json`; `BuildResult` reports status/counts/errors. No image render, silhouette comparison, prompt-to-image evaluation or full artistic review is performed. V3's available primitives are 13 types; active modifiers are bevel, subdivision, solidify and smooth shading. It has no active boolean, curve, rigging, animation, geometry-node, physics or scene-lighting pipeline.

### V3 files: roles and activation

| File | Role |
|---|---|
| `controller.py` | Direct V3 orchestrator, audit/repair, commit/readback/rollback, persistence/result. Not called by normal routes. Its own direct runner has an optional `BLENDER_PIPELINE_MODE=v2_legacy` branch. |
| `intent.py` | Intent dataclasses, allowed primitive/relation vocabulary, JSON parsing, initial and repair LLM calls. |
| `normalize.py` | Heuristic missing-relation and orientation completion. |
| `compiler.py` | Intent-to-Scene expansion and basic geometry/material/modifier assignment. |
| `identity.py` | Slugs and canonical part paths. |
| `layout.py` | Repeated-instance mapping, graph-order placement, relative transforms/parents. |
| `envelope.py` | Approximate XY bounds and uniform fit to declared width. |
| `scene.py` | V3 typed `Scene`, `ScenePart`, geometry/material/modifier/transform, status/result and JSON persistence. Independent of V2 manifest. |
| `verifier.py` | Contract preflight and independent Blender readback checks. |
| `audit.py` | Pre-commit duplicate/cycle/collapse/envelope checks. |
| `executor.py` | V3-owned Blender Python transaction, primitive construction, node-based material, four modifier types, hierarchy and scoped cleanup. Uses common `core.blender_ops.parse_op_output`, not V2 executor. |
| `trace.py` | Adds phase events to the V3 scene. |
| `__init__.py` | Experimental package exports. |
| `tests/test_failed_run_replay.py`, `tests/test_controller_contract.py`, `tests/blender_smoke.py` | Replay/mock-controller/headless-Blender checks. Not evidence that a complex model looks correct. |

## 4. Important observed failure and honest capability boundary

The newest recorded V3 drone manifest at `backend/data/builds_v3/m_7feec5d62e/manifest.json` has `status=FAILED`, zero parts and only a failure event: `top_panel requires size [x, y, z]`. The planner supplied a two-element `size` for a plane, and `IntentCompiler._geometry` raised **before Blender was called**. The controller's repair is only reached after compilation and audit, so it could not repair this error. The raw plan also used cones for propeller blades, a questionable form choice. This is evidence of a design-planning weakness as well as a schema mismatch; passing the code smoke tests is not a substitute for a visually faithful model.

V2's broader active geometry/modifier/boolean and spatial-contract machinery makes it the safer current default for complex hard-surface models, but it is not an arbitrary-model or scene generator either. V2's NodeKind enums and agent-facing tool descriptions mention cameras, lights, animation, rigging, materials with node graphs, etc.; the active controller only dispatches `PART`, `ASSEMBLY` and `MODEL`, and the transaction capability allowlist is narrower than those declarations. Neither route currently creates a complete authored scene with camera/lighting/render based on the natural-language build prompt, nor verifies visual fidelity from a rendered image.

Some comments/docstrings still call V3 “primary” or V2 “v5”; current routing imports, not those labels, determine what runs. Similarly, a numeric node count is not a fidelity metric: root/assembly nodes are included in V2 counts, while V3 counts physical `ScenePart` records.

Task/queue completion and **build** completion are separate concepts. For a build failure, inspect the pipeline result (`completion_status`, errors, manifest event), the endpoint's `build_status`/error, and the Blender scene; a generic task or websocket “complete” line alone is not proof that model creation succeeded.

## 5. Guidance for the next model/reviewer

- Treat this document as a map, then inspect the named functions and the latest manifests/traces. Do not infer feature support from an enum, an API description or a successful unit test.
- Keep **prompt requirements**, **typed plan**, **resolved transforms**, **Blender receipt**, **readback**, and **rendered visual result** as separate evidence. “N/N verified” can mean resolved planning nodes in V2's off-scene pass; final success must be tied to an actual committed and visually inspected scene.
- Compare both pipelines on a fixed suite (the drone plus unrelated mechanical, furniture, organic and multi-object scene prompts) using the same model and Blender build, with explicit scoring for missing parts, topology/form, dimensions, contact/clearance, symmetry, materials, visual silhouette and latency/calls. Record the prompt, raw plan, manifest, Blender object inventory and renders per run.
- Do not reactivate V3 solely because its executor works. First prove capability parity or a clearly bounded domain, handle parse/compile errors through a safe repair loop, and demonstrate better visual results than V2 on the agreed suite.
- Preserve the dirty working tree: many V2/archival files already contain user work. This document made no runtime code changes.
