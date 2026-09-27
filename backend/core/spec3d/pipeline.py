"""Declarative 3D Spec Execution Pipeline — v3.

Three-route architecture:
  Route 1 — Library hit:    Exact approved spec → compile directly.
  Route 2 — LLM planned:   Category/generic → SpecPlanner.plan_best_of_n()
                             → Tier 1 verify + repair → compile → Tier 2 verify.
  Route 3 — Decline:        Planner confidence < 0.3 → return error.

Approval step:
  Returns build_id in response.  User later sends "save as approved" + build_id
  to persist spec + thumbnail to library.

model_manager access:
  Passed from base_agent.py (not a singleton).

Pending builds:
  Persisted to operational.sqlite with 24h TTL so they survive backend restarts.
"""

import os
import json
import logging
import time
from typing import Any, Dict, Optional, Union

from .schema import QuadrupedSpec, HardSurfaceSpec, VesselSpec
from .templates import ArchetypeTemplates
from .verifier import SpecVerifier, MeshVerifier
from .compiler import SpecCompiler
from .runner import HeadlessBlenderRunner
from .library import SpecLibrary, LiveBlenderAppender
from .planner import SpecPlanner, infer_category

logger = logging.getLogger(__name__)

SCHEMA_VERSION = "3.0"
PENDING_BUILD_TTL_HOURS = 24


# ---------------------------------------------------------------------------
# Pending build persistence helpers
# ---------------------------------------------------------------------------

def _save_pending_build(build_id: str, entry: Dict[str, Any]) -> None:
    """Persist a pending build to operational.sqlite."""
    try:
        from db.connections import get_operational_db
        db = get_operational_db()
        _ensure_pending_builds_table(db)
        expires_at = time.time() + PENDING_BUILD_TTL_HOURS * 3600
        db.execute(
            """INSERT OR REPLACE INTO spec3d_pending_builds
               (build_id, data_json, expires_at) VALUES (?, ?, ?)""",
            (build_id, json.dumps(entry), expires_at),
        )
        db.commit()
    except Exception as e:
        logger.warning(f"Could not persist pending build {build_id}: {e}")
        # Fall back to in-memory
        _pending_builds_memory[build_id] = entry


def _load_pending_build(build_id: str) -> Optional[Dict[str, Any]]:
    """Load a pending build from DB, respecting TTL. Falls back to in-memory."""
    try:
        from db.connections import get_operational_db
        db = get_operational_db()
        _ensure_pending_builds_table(db)
        row = db.execute(
            "SELECT data_json, expires_at FROM spec3d_pending_builds WHERE build_id = ?",
            (build_id,),
        ).fetchone()
        if row:
            data_json, expires_at = row
            if time.time() < expires_at:
                return json.loads(data_json)
            # Expired — clean up
            db.execute("DELETE FROM spec3d_pending_builds WHERE build_id = ?", (build_id,))
            db.commit()
    except Exception as e:
        logger.warning(f"DB pending build lookup failed: {e}")
    # In-memory fallback
    return _pending_builds_memory.get(build_id)


def _delete_pending_build(build_id: str) -> None:
    try:
        from db.connections import get_operational_db
        db = get_operational_db()
        db.execute("DELETE FROM spec3d_pending_builds WHERE build_id = ?", (build_id,))
        db.commit()
    except Exception:
        pass
    _pending_builds_memory.pop(build_id, None)


def _ensure_pending_builds_table(db) -> None:
    """Create the table if it doesn't exist yet (lazy migration)."""
    db.execute("""
        CREATE TABLE IF NOT EXISTS spec3d_pending_builds (
            build_id TEXT PRIMARY KEY,
            data_json TEXT NOT NULL,
            expires_at REAL NOT NULL
        )
    """)
    db.commit()


# In-memory fallback (used when DB is unavailable)
_pending_builds_memory: Dict[str, Dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

class Spec3DPipeline:

    @classmethod
    async def process_build_spec(
        cls,
        args: Dict[str, Any],
        mcp_manager: Any,
        model_manager: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Full Spec3D v3 pipeline.

        args:
          description (str)   — natural language object description (primary)
          category    (str)   — optional category hint
          spec        (dict)  — optional pre-formed spec dict (bypasses planner)
          params      (dict)  — legacy knob params (still accepted for backward compat)
        """
        description = args.get("description") or args.get("params", {}).get("name", "")
        category_hint = args.get("category", "").lower()
        spec_data = args.get("spec")
        params = args.get("params") or {}

        # ----------------------------------------------------------------
        # STAGE 0: Route Selection
        # ----------------------------------------------------------------
        spec_obj: Optional[Union[QuadrupedSpec, HardSurfaceSpec, VesselSpec]] = None
        route_used = "unknown"

        # Sub-route A: pre-formed spec dict passed directly
        if spec_data:
            try:
                cat = spec_data.get("category", "").lower()
                if cat == "quadruped":
                    spec_obj = QuadrupedSpec(**spec_data)
                elif cat == "vessel":
                    spec_obj = VesselSpec(**spec_data)
                else:
                    spec_obj = HardSurfaceSpec(**spec_data)
                route_used = "direct_spec"
            except Exception as e:
                return {"ok": False, "error": f"Invalid spec dict: {e}"}

        # Sub-route B: exact library match
        if spec_obj is None and description:
            if SpecLibrary.has_exact_match(description):
                spec_dict = SpecLibrary.get_approved_spec(description)
                try:
                    cat = spec_dict.get("category", "")
                    if cat == "quadruped":
                        spec_obj = QuadrupedSpec(**spec_dict)
                    elif cat == "vessel":
                        spec_obj = VesselSpec(**spec_dict)
                    else:
                        spec_obj = HardSurfaceSpec(**spec_dict)
                    route_used = "library_exact"
                    logger.info(f"Library exact match for '{description}'")
                except Exception:
                    spec_obj = None  # fall through to planner

        # Sub-route C: LLM planner (with or without exemplar)
        if spec_obj is None:
            if model_manager is None:
                # Graceful degradation — fall back to archetype template
                logger.warning("model_manager not available; falling back to archetype template")
                spec_obj = cls._template_fallback(category_hint, params, description)
                if spec_obj is None:
                    return {
                        "ok": False,
                        "error": (
                            f"model_manager is required for LLM planning and no template "
                            f"matches '{description}'. Provide a spec dict directly or enable model_manager."
                        ),
                    }
                route_used = "template_fallback"
            else:
                category = infer_category(description, category_hint)
                exemplar = SpecLibrary.get_few_shot_exemplar(category)

                spec_obj, confidence = await SpecPlanner.plan_best_of_n(
                    prompt=description,
                    category_hint=category_hint,
                    model_manager=model_manager,
                    exemplar=exemplar,
                    n=3,
                )

                if spec_obj is None or confidence < 0.3:
                    fallback_spec = cls._template_fallback(category_hint, params, description)
                    if fallback_spec is not None:
                        logger.warning(
                            f"LLM planner returned low confidence ({confidence:.2f}) for '{description}'. "
                            f"Gracefully falling back to archetype template."
                        )
                        spec_obj = fallback_spec
                        route_used = f"archetype_fallback (confidence={confidence:.2f})"
                    else:
                        return {
                            "ok": False,
                            "error": (
                                f"LLM planner returned low-confidence spec for '{description}' "
                                f"(confidence={confidence:.2f}). "
                                "Try providing more detail, e.g. 'a tall ceramic wine glass with thin stem'."
                            ),
                            "confidence": confidence,
                        }
                else:
                    route_used = f"llm_planned (confidence={confidence:.2f})"
                    logger.info(f"LLM planned spec for '{description}': {route_used}")

        if spec_obj is None:
            return {"ok": False, "error": f"Could not construct spec for '{description}'"}

        # ----------------------------------------------------------------
        # STAGE 1+2: Tier 1 Verification + Deterministic Repair
        # ----------------------------------------------------------------
        tier1_result = cls._tier1_verify(spec_obj)

        if not tier1_result.valid:
            logger.warning(f"Tier 1 failed ({len(tier1_result.errors)} errors) — applying repairs")

            # Apply deterministic repair patches
            if tier1_result.repair_patches and isinstance(spec_obj, QuadrupedSpec):
                for k, val in tier1_result.repair_patches.items():
                    if k.startswith("joints."):
                        parts = k.split(".")
                        jname, axis = parts[1], parts[2]
                        for j in spec_obj.joints:
                            if j.name == jname:
                                setattr(j, axis, val)
                tier1_result = cls._tier1_verify(spec_obj)

            # If still failing and model_manager is available, ask LLM to patch
            if not tier1_result.valid and model_manager and route_used.startswith("llm"):
                spec_obj, repaired = await SpecPlanner.repair_spec(
                    spec_obj, tier1_result.errors, model_manager
                )
                tier1_result = cls._tier1_verify(spec_obj)
                if not tier1_result.valid:
                    logger.warning(
                        f"Spec still has Tier 1 errors after repair — proceeding with warnings: "
                        f"{tier1_result.errors}"
                    )

        # ----------------------------------------------------------------
        # STAGE 3: Compile
        # ----------------------------------------------------------------
        script = SpecCompiler.compile_to_script(spec_obj)

        # ----------------------------------------------------------------
        # STAGE 4: Headless Build + Tier 2 Verification
        # ----------------------------------------------------------------
        runner = HeadlessBlenderRunner()
        success, metrics, blend_path = await runner.build_and_verify(script, timeout_seconds=60)

        if not success or not blend_path:
            return {
                "ok": False,
                "error": f"Headless Blender build failed: {metrics.get('error', 'unknown')}",
                "stderr": metrics.get("stderr", ""),
                "tier1_score": round(tier1_result.score, 2),
            }

        # Tier 2 mesh verification
        tier2_result = MeshVerifier.verify_mesh_tier2(metrics, category=spec_obj.category)
        if not tier2_result.valid:
            logger.warning(
                f"Tier 2 mesh check flagged issues (informational): {tier2_result.errors}"
            )

        # ----------------------------------------------------------------
        # STAGE 5: Live Append (model collection only)
        # ----------------------------------------------------------------
        model_coll_name = metrics.get("model_collection", f"Sentinel_{spec_obj.name}")
        append_script = LiveBlenderAppender.generate_append_script(
            blend_path=blend_path,
            model_collection_name=model_coll_name,
        )

        append_res: Dict[str, Any] = {}
        try:
            live_raw = await mcp_manager.call_locked(
                "blender", "execute_blender_code", {"code": append_script}
            )
            from core.blender_ops import parse_op_output
            raw_str = live_raw.get("output", "") if isinstance(live_raw, dict) else str(live_raw)
            append_res = parse_op_output(raw_str)
        except Exception as e:
            logger.warning(f"Live append skipped (Blender not connected?): {e}")
            append_res = {"note": str(e)}

        # ----------------------------------------------------------------
        # STAGE 6: Register for Approval (persisted to DB)
        # ----------------------------------------------------------------
        import hashlib
        build_id = hashlib.md5(
            f"{spec_obj.name}_{time.time()}".encode()
        ).hexdigest()[:10]

        pending_entry = {
            "spec": spec_obj.model_dump(),
            "category": spec_obj.category,
            "name": spec_obj.name,
            "metrics": metrics,
            "blend_path": blend_path,
            "schema_version": SCHEMA_VERSION,
        }
        _save_pending_build(build_id, pending_entry)

        # Surface Tier 2 issues in a user-readable quality message
        mesh_quality = "ok"
        mesh_quality_detail = None
        if not tier2_result.valid:
            mesh_quality = "warning"
            mesh_quality_detail = "; ".join(tier2_result.errors[:3])
        elif tier2_result.warnings:
            mesh_quality = "info"
            mesh_quality_detail = tier2_result.warnings[0]

        return {
            "ok": True,
            "status": "VERIFIED_AND_LOADED",
            "model_name": spec_obj.name,
            "category": spec_obj.category,
            "route": route_used,
            "poly_count": metrics.get("total_polys", 0),
            "object_count": metrics.get("object_count", 1),
            "tier1_score": round(tier1_result.score, 2),
            "mesh_quality": mesh_quality,
            "mesh_quality_detail": mesh_quality_detail,
            "live_status": append_res,
            "build_id": build_id,
            "hint": f"To save this to the library, say: save as approved {build_id}",
        }

    @classmethod
    async def process_save_approved(
        cls,
        build_id: str,
    ) -> Dict[str, Any]:
        """Persist a pending build to the spec library as an approved exemplar."""
        entry = _load_pending_build(build_id)
        if not entry:
            return {
                "ok": False,
                "error": (
                    f"No pending build with id '{build_id}'. "
                    "Builds are kept for 24 hours and survive backend restarts. "
                    "If it's been longer than 24h, you'll need to rebuild."
                ),
            }

        spec_data = {**entry["spec"], "_schema_version": SCHEMA_VERSION}
        path = SpecLibrary.save_approved_spec(
            category=entry["category"],
            name=entry["name"],
            spec_data=spec_data,
            metrics=entry.get("metrics"),
        )

        _delete_pending_build(build_id)

        return {
            "ok": True,
            "status": "APPROVED",
            "saved_to": path,
            "name": entry["name"],
            "category": entry["category"],
            "message": (
                f"Spec for '{entry['name']}' saved to library (schema v{SCHEMA_VERSION}). "
                "Future builds with the same name will use this approved spec directly."
            ),
        }

    # ----------------------------------------------------------------
    # Helpers
    # ----------------------------------------------------------------

    @staticmethod
    def _tier1_verify(spec):
        if isinstance(spec, QuadrupedSpec):
            return SpecVerifier.verify_quadruped(spec)
        elif isinstance(spec, VesselSpec):
            return SpecVerifier.verify_vessel(spec)
        else:
            return SpecVerifier.verify_hard_surface(spec)

    @staticmethod
    def _template_fallback(category_hint: str, params: dict, description: str):
        """Return an archetype template spec when planner is unavailable or low-confidence."""
        cat = (category_hint or infer_category(description)).lower()
        desc = (description or "").lower()
        name = params.get("name") or description or "model"

        if cat in ("quadruped", "dog", "cat", "animal", "creature", "wolf", "horse", "bear", "fox", "lion", "tiger", "cow", "deer", "elephant", "giraffe", "mammal") or any(w in desc for w in ("dog", "cat", "penguin", "animal", "creature", "quadruped")):
            return ArchetypeTemplates.quadruped(
                name=name,
                body_length=float(params.get("body_length", 0.85)),
                withers_height=float(params.get("withers_height", 0.55)),
            )

        if cat in ("mug", "ceramic_mug", "cup", "vessel", "glass", "wine_glass", "wineglass", "vase", "bottle", "bowl", "jug", "pitcher") or any(w in desc for w in ("mug", "cup", "vessel", "glass", "vase", "bottle", "bowl")):
            if "wine" in desc or "glass" in desc:
                return ArchetypeTemplates.wine_glass(name=name)
            elif "vase" in desc:
                return ArchetypeTemplates.ceramic_vase(name=name)
            else:
                return ArchetypeTemplates.ceramic_mug(
                    name=name,
                    height=float(params.get("height", 0.10)),
                    radius=float(params.get("radius", 0.042)),
                )

        if cat in ("table", "dining_table", "furniture", "chair", "shelf", "bookshelf", "vehicle", "car", "truck", "generic", "tool") or any(w in desc for w in ("table", "chair", "desk", "shelf", "bookshelf", "car", "vehicle", "lamp")):
            if "chair" in desc:
                return ArchetypeTemplates.dining_chair(name=name)
            elif "shelf" in desc or "bookshelf" in desc:
                return ArchetypeTemplates.bookshelf(name=name)
            elif "car" in desc or "vehicle" in desc or "truck" in desc:
                return ArchetypeTemplates.simple_car(name=name)
            elif "lamp" in desc:
                return ArchetypeTemplates.floor_lamp(name=name)
            else:
                return ArchetypeTemplates.dining_table(
                    name=name,
                    length=float(params.get("length", 1.6)),
                    width=float(params.get("width", 0.9)),
                    height=float(params.get("height", 0.75)),
                )

        # Default fallback to ceramic mug or dining table
        return ArchetypeTemplates.ceramic_mug(name=name)
