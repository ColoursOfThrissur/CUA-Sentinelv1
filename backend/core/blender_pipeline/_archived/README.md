# Archived Blender Pipeline Code

The active runtime is `core.blender_pipeline.progressive_v2` only.

- `legacy_stages/` contains the former batch Stage 1–4.5 implementation.
- `legacy_v4/` contains the former staged orchestrator and executor.
- `progressive_v1/` is retained for historical/debug reference.

`stage0_understanding.py` remains outside this archive because the active v2
controller uses it to establish the model-scale contract when callers do not
provide Stage 0 output.

These modules are not exported by `core.blender_pipeline` and must not be
used for new builds. They remain version-controlled so they can be inspected
or recovered without affecting the live transaction pipeline.
