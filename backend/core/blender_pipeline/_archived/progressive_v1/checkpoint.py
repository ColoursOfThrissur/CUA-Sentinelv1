"""Checkpoint Manager — handles saving, listing, and restoring manifest snapshots.

Blueprint references: §19 (Checkpointing).
After every meaningful boundary:
- verified leaf
- verified sub-assembly
- verified assembly
- successful merge
the manifest is checkpointed so that if the process crashes, we can resume from the frontier.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .manifest import BuildManifest, _builds_dir

logger = logging.getLogger(__name__)


class CheckpointManager:
    """Manages snapshot history and restoration for a BuildManifest."""

    @classmethod
    def checkpoint(cls, manifest: BuildManifest, label: Optional[str] = None) -> Dict[str, Any]:
        """Record and persist a checkpoint for the manifest."""
        manifest.checkpoint(label=label)
        last_snap = manifest.checkpoints[-1]
        return last_snap

    @classmethod
    def list_checkpoints(cls, model_id: str) -> List[Dict[str, Any]]:
        """List all checkpoint records saved for a model build."""
        manifest = BuildManifest.load_by_model_id(model_id)
        if manifest is None:
            return []
        return manifest.checkpoints

    @classmethod
    def restore_latest(cls, model_id: str) -> Optional[BuildManifest]:
        """Restore the latest manifest state for model_id."""
        manifest = BuildManifest.load_by_model_id(model_id)
        if manifest is None:
            logger.warning(f"No checkpoint found for model_id '{model_id}'")
            return None
        logger.info(
            f"Restored manifest '{model_id}' with {len(manifest.nodes)} nodes "
            f"and {len(manifest.checkpoints)} checkpoints"
        )
        return manifest
