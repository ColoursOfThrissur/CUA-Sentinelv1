# Blender V3 runtime (archived 2026-10-05)

V3 is no longer an active or importable runtime. Its source is retained under
`backend/core/blender_pipeline/_archived/progressive_v3` only for historical
comparison. Its plane-schema failure is now a V2 regression test, and its
useful scene-contract, identity, repair, readback and audit ideas were ported
to V2. All production build entry points route to V2.

1. `IntentPlanner` makes one bounded LLM request for a typed component/relation plan. One repair request is allowed after a failed deterministic audit. Planner responses and inferred relations are persisted in the V3 scene trace.
2. `IntentNormalizer` fills missing attachment edges. `IntentCompiler` creates a V3 `Scene` with stable part identities, geometry, materials, modifiers, transforms, and parent links. No V2 manifest is created.
3. `V3Preflight` checks the executable contract; `SceneAudit` checks identity, cycles, repeated placement collapse, and the XY envelope. Failure stops before Blender mutation.
4. `V3Executor` submits one scoped Blender transaction. It creates meshes, node-based PBR materials, modifiers, and hierarchy inside a per-attempt collection. A Blender-side exception removes that collection.
5. An independent MCP call reads objects back and checks identity, hierarchy, material presence, modifier presence, position, and width. Failed readback triggers scoped rollback. Only then is the result `SUCCESS`.

Current limits: V3 supports 13 primitive types and four modifier kinds. It does not yet implement arbitrary mesh topology, curves, booleans, sculpting, rigging, animation, or geometry nodes. The planner and layout are still approximate for complex organic/industrial models; structural verification is not the same as visual quality validation. There is no claim of support for every possible 3D model.

Historical tests remain under the archived directory and are not a production runtime gate.
