"""
TTL Janitor Script for CUA-Sentinel.

Decommissions zombie infrastructure, cleans old workspace runs,
prunes expired episodic memory records, and vacuums SQLite databases.
"""

import os
import time
import shutil
import logging
from typing import Dict, Any
from db.connections import get_operational_db, get_knowledge_db

logger = logging.getLogger(__name__)

class JanitorEngine:
    def __init__(self, workspace_dir: str = "data/workspaces", max_age_days: int = 7):
        self.workspace_dir = workspace_dir
        self.max_age_seconds = max_age_days * 86400

    def run_cleanup(self) -> Dict[str, Any]:
        """
        Executes complete janitorial sweep across temporary folders and databases.
        """
        summary = {
            "deleted_workspaces": 0,
            "pruned_memories": 0,
            "vacuumed_dbs": []
        }

        # 1. Clean old workspace run directories
        if os.path.exists(self.workspace_dir):
            now = time.time()
            for folder in os.listdir(self.workspace_dir):
                folder_path = os.path.join(self.workspace_dir, folder)
                if os.path.isdir(folder_path):
                    mtime = os.path.getmtime(folder_path)
                    if (now - mtime) > self.max_age_seconds:
                        try:
                            shutil.rmtree(folder_path)
                            summary["deleted_workspaces"] += 1
                            logger.info(f"Janitor pruned old workspace: {folder_path}")
                        except Exception as e:
                            logger.warning(f"Failed to delete workspace {folder_path}: {e}")

        # 2. Prune expired episodic memories
        conn_k = get_knowledge_db()
        try:
            res = conn_k.execute(
                """
                DELETE FROM episodic_memory
                WHERE expires_at IS NOT NULL AND expires_at < (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
                """
            )
            summary["pruned_memories"] = res.rowcount
            conn_k.commit()
        except Exception as e:
            logger.warning(f"Janitor failed to prune episodic memory: {e}")
        finally:
            conn_k.close()

        # 3. Vacuum SQLite WAL databases
        for db_getter, name in [(get_operational_db, "operational"), (get_knowledge_db, "knowledge")]:
            try:
                conn = db_getter()
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                conn.close()
                summary["vacuumed_dbs"].append(name)
            except Exception as e:
                logger.warning(f"Janitor failed to vacuum {name} db: {e}")

        logger.info(f"Janitor Sweep Complete: {summary}")
        return summary

janitor_engine = JanitorEngine()
