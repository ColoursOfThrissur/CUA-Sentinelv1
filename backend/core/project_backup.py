"""
Project Backup & Rollback Manager for CUA-Sentinel.

Creates pre-refactor zip/folder snapshots in .sentinel_backup/
and provides 1-click Rollback Changes functionality.
"""

import os
import shutil
import time
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

EXCLUDE_DIRS = {"node_modules", ".venv", "venv", ".git", "dist", "build", "__pycache__", ".sentinel_backup"}

class ProjectBackupManager:
    def __init__(self, backup_root: str = "data/backups"):
        self.backup_root = backup_root
        os.makedirs(self.backup_root, exist_ok=True)

    def create_snapshot(self, project_path: str, task_id: str) -> Optional[str]:
        """
        Creates an ephemeral backup snapshot of project files prior to editing.
        """
        if not os.path.exists(project_path):
            logger.error(f"Project path does not exist for backup: {project_path}")
            return None

        backup_dir = os.path.join(self.backup_root, f"snapshot_{task_id}")
        os.makedirs(backup_dir, exist_ok=True)

        try:
            for root, dirs, files in os.walk(project_path):
                # Modify dirs in-place to skip excluded folders
                dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
                rel_path = os.path.relpath(root, project_path)
                target_root = os.path.join(backup_dir, rel_path) if rel_path != "." else backup_dir
                os.makedirs(target_root, exist_ok=True)

                for f in files:
                    src_file = os.path.join(root, f)
                    dst_file = os.path.join(target_root, f)
                    shutil.copy2(src_file, dst_file)

            logger.info(f"Created pre-refactor backup snapshot at: {backup_dir}")
            return backup_dir
        except Exception as e:
            logger.error(f"Failed to create backup snapshot: {e}")
            return None

    def restore_snapshot(self, project_path: str, task_id: str) -> bool:
        """
        Restores project files from backup snapshot (1-click Rollback).
        """
        backup_dir = os.path.join(self.backup_root, f"snapshot_{task_id}")
        if not os.path.exists(backup_dir):
            logger.error(f"Backup snapshot not found for task {task_id} at {backup_dir}")
            return False

        try:
            for root, dirs, files in os.walk(backup_dir):
                rel_path = os.path.relpath(root, backup_dir)
                target_root = os.path.join(project_path, rel_path) if rel_path != "." else project_path
                os.makedirs(target_root, exist_ok=True)

                for f in files:
                    src_file = os.path.join(root, f)
                    dst_file = os.path.join(target_root, f)
                    shutil.copy2(src_file, dst_file)

            logger.info(f"Successfully restored snapshot for task {task_id} to {project_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to restore snapshot: {e}")
            return False

project_backup_manager = ProjectBackupManager()
