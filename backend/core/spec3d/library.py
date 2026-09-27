"""Curated Spec Library, Few-Shot Retrieval, and Live Blender Presentation.

v3 changes:
- Append only the MODEL collection (not all objects — staging/lights excluded).
- Safe path serialization via json.dumps (handles Windows backslashes).
- Viewport shading via window_manager.windows loop
  (bpy.context.screen is None when called via MCP socket).
- Unique suffixed names prevent Dog.001 collisions across consecutive appends.
- save_approved_spec / has_exact_match / has_category_exemplar for route selection.
"""

import os
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

SPECS_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "specs"


class SpecLibrary:
    """Curated library of approved specs used as few-shot exemplars and exact-match sources."""

    @classmethod
    def initialize_library(cls) -> None:
        """Seed the library with golden exemplars if not already present."""
        os.makedirs(SPECS_DIR / "quadruped", exist_ok=True)
        os.makedirs(SPECS_DIR / "furniture", exist_ok=True)
        os.makedirs(SPECS_DIR / "vessel", exist_ok=True)
        os.makedirs(SPECS_DIR / "vehicle", exist_ok=True)
        os.makedirs(SPECS_DIR / "tool", exist_ok=True)
        os.makedirs(SPECS_DIR / "generic", exist_ok=True)

        from .templates import ArchetypeTemplates

        seeds = [
            (SPECS_DIR / "quadruped" / "golden_retriever.json",
             lambda: ArchetypeTemplates.quadruped(name="golden_retriever",
                                                   body_length=0.85, withers_height=0.55)),
            (SPECS_DIR / "furniture" / "dining_table.json",
             lambda: ArchetypeTemplates.dining_table(name="dining_table",
                                                      length=1.6, width=0.9, height=0.75)),
            (SPECS_DIR / "vessel" / "ceramic_mug.json",
             lambda: ArchetypeTemplates.ceramic_mug(name="ceramic_mug",
                                                     height=0.10, radius=0.042)),
        ]
        for path, factory in seeds:
            if not path.exists():
                try:
                    spec = factory()
                    with open(path, "w", encoding="utf-8") as f:
                        json.dump(spec.model_dump(), f, indent=2)
                    logger.info(f"Seeded golden exemplar: {path}")
                except Exception as e:
                    logger.warning(f"Failed to seed {path}: {e}")

    # ----------------------------------------------------------------
    # Route-selection helpers (used by pipeline / planner)
    # ----------------------------------------------------------------

    @classmethod
    def has_exact_match(cls, object_name: str) -> bool:
        """Return True if an approved spec with this name exists."""
        return cls._find_approved_spec(object_name) is not None

    @classmethod
    def get_approved_spec(cls, object_name: str) -> Optional[Dict[str, Any]]:
        """Return the approved spec dict for an exact name match, or None."""
        path = cls._find_approved_spec(object_name)
        if path:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        return None

    @classmethod
    def has_category_exemplar(cls, category: str) -> bool:
        return cls.get_few_shot_exemplar(category) is not None

    @classmethod
    def get_few_shot_exemplar(cls, category: str) -> Optional[Dict[str, Any]]:
        """Return the best matching exemplar spec for a category (for LLM few-shot)."""
        # Canonical category mapping
        cat_map = {
            "dog": "quadruped", "cat": "quadruped", "animal": "quadruped",
            "creature": "quadruped", "mammal": "quadruped",
            "table": "furniture", "chair": "furniture", "desk": "furniture",
            "mug": "vessel", "cup": "vessel", "bowl": "vessel",
            "bottle": "vessel", "vase": "vessel", "glass": "vessel",
        }
        canonical = cat_map.get(category, category)
        cat_dir = SPECS_DIR / canonical

        if cat_dir.exists():
            # Prefer files that contain the category name
            files = sorted(cat_dir.glob("*.json"))
            if files:
                # Prefer approved_ prefix if present
                approved = [f for f in files if f.stem.startswith("approved_")]
                target = approved[0] if approved else files[0]
                try:
                    with open(target, "r", encoding="utf-8") as f:
                        return json.load(f)
                except Exception as e:
                    logger.warning(f"Failed to load exemplar {target}: {e}")
        return None

    @classmethod
    def save_approved_spec(
        cls,
        category: str,
        name: str,
        spec_data: Dict[str, Any],
        thumbnail_path: Optional[str] = None,
        metrics: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Persist a human-approved spec into the curated library."""
        cat_dir = SPECS_DIR / category
        os.makedirs(cat_dir, exist_ok=True)
        safe_name = "approved_" + "".join(
            c for c in name if c.isalnum() or c in ("_", "-")
        )
        file_path = cat_dir / f"{safe_name}.json"

        payload: Dict[str, Any] = {**spec_data}
        if thumbnail_path:
            payload["_thumbnail"] = thumbnail_path
        if metrics:
            payload["_metrics"] = metrics

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        logger.info(f"Saved approved 3D spec: {file_path}")
        return str(file_path)

    @classmethod
    def list_approved(cls, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all approved specs, optionally filtered by category."""
        results = []
        search_dirs = [SPECS_DIR / category] if category else [
            d for d in SPECS_DIR.iterdir() if d.is_dir()
        ]
        for d in search_dirs:
            for f in sorted(d.glob("approved_*.json")):
                try:
                    with open(f, "r", encoding="utf-8") as fh:
                        data = json.load(fh)
                    results.append({"path": str(f), "name": f.stem, "category": d.name, "spec": data})
                except Exception:
                    pass
        return results

    # ----------------------------------------------------------------
    # Internal helpers
    # ----------------------------------------------------------------

    @classmethod
    def _find_approved_spec(cls, name: str) -> Optional[Path]:
        """Search all category dirs for an approved_<name>.json file."""
        safe = "approved_" + "".join(c for c in name if c.isalnum() or c in ("_", "-"))
        for cat_dir in SPECS_DIR.iterdir():
            if not cat_dir.is_dir():
                continue
            candidate = cat_dir / f"{safe}.json"
            if candidate.exists():
                return candidate
            # Also match without prefix
            candidate2 = cat_dir / f"{name}.json"
            if candidate2.exists():
                return candidate2
        return None


# ---------------------------------------------------------------------------
# Live Blender Appender
# ---------------------------------------------------------------------------

class LiveBlenderAppender:
    """Generates clean append scripts for the live interactive Blender session."""

    @classmethod
    def generate_append_script(
        cls,
        blend_path: str,
        model_collection_name: str,
    ) -> str:
        """
        Generate a script that appends ONLY the model collection from the
        verified .blend into the live Blender session.

        Key guarantees:
        - Staging objects (lights, camera, floor) are NOT imported.
        - Viewport shading is set via window_manager.windows loop
          (bpy.context.screen is None when called via MCP socket).
        - json.dumps handles Windows backslashes safely.
        """
        # Use json.dumps for safe path embedding (handles Windows backslashes)
        safe_blend_path = json.dumps(os.path.abspath(blend_path))
        safe_coll_name = json.dumps(model_collection_name)

        return f"""
import bpy
import json

BLEND_PATH = {safe_blend_path}
MODEL_COLL_NAME = {safe_coll_name}

# 1. Append the model collection (excludes staging lights/camera)
with bpy.data.libraries.load(BLEND_PATH, link=False) as (data_from, data_to):
    if MODEL_COLL_NAME in data_from.collections:
        data_to.collections = [MODEL_COLL_NAME]
    else:
        # Fallback: append all mesh objects, skip lights/cameras
        data_to.objects = [
            o for o in data_from.objects
            if not o.startswith("Key_") and not o.startswith("Fill_")
               and not o.startswith("Camera") and not o.startswith("Sentinel_Staging")
        ]

# 2. Link appended collection to active scene (if collection path was used)
for coll in bpy.data.collections:
    if coll.name == MODEL_COLL_NAME:
        if MODEL_COLL_NAME not in bpy.context.scene.collection.children:
            bpy.context.scene.collection.children.link(coll)
        break
else:
    # Fallback: link any orphaned appended objects directly
    for obj in bpy.data.objects:
        if not obj.users_collection:
            bpy.context.scene.collection.objects.link(obj)

# 3. Switch 3D viewports to MATERIAL shading via window_manager.windows
# (bpy.context.screen is None when called via MCP socket)
try:
    wm = bpy.context.window_manager
    if wm is None:
        wm = bpy.data.window_managers[0]
    for window in wm.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                for space in area.spaces:
                    if space.type == 'VIEW_3D':
                        space.shading.type = 'MATERIAL'
except Exception as e:
    print(f"Viewport shading note: {{e}}")

# 4. Report
appended_names = [o.name for o in bpy.data.objects if MODEL_COLL_NAME in o.name or
                  any(c.name == MODEL_COLL_NAME for c in o.users_collection)]
res = {{
    "ok": True,
    "collection": MODEL_COLL_NAME,
    "blend_path": BLEND_PATH,
    "appended_objects": appended_names,
}}
print("SENTINEL_OUTPUT_START" + json.dumps(res) + "SENTINEL_OUTPUT_END")
"""
