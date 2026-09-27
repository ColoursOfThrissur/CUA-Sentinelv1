"""Project Write Service for CUA-Sentinel.

Handles file-plan parsing from LLM outputs, path canonicalization,
security boundary verification, atomic writes with rollback capability,
post-write verification, and policy-governed asset repairs.
"""

from __future__ import annotations

import logging
import os
import re
import uuid
from typing import Any, Dict, List, Optional

from core.path_security import PathSecurityViolation, path_security

logger = logging.getLogger(__name__)


class ProjectWriteService:
    """Service providing safe, validated, and verifiable file mutations."""

    def parse_file_plan(self, text: str) -> List[Dict[str, str]]:
        """Parses raw LLM markdown response into Normalized File Operations (FileOpPlan)."""
        file_ops = []
        pattern = re.compile(
            r'```(?:\w+)?\s*(?:#|//|/\*)\s*(?:file|filepath):\s*([^\n\r]+)\n(.*?)```',
            re.DOTALL | re.IGNORECASE,
        )
        matches = pattern.findall(text)
        for rel_path, code in matches:
            rel_path = rel_path.strip().strip("'\"")
            if rel_path:
                file_ops.append({
                    "rel_path": rel_path,
                    "content": code.strip(),
                })
        return file_ops

    # Backward-compatible alias for execution broker callers
    parse_raw_llm_code_blocks = parse_file_plan

    def verify_written_files(self, project_path: str, rel_paths: List[str]) -> List[str]:
        """Verifies that written files physically exist and are accessible on disk."""
        verified = []
        for rel in rel_paths:
            full = os.path.normpath(os.path.join(project_path, rel))
            if os.path.exists(full) and os.path.isfile(full):
                verified.append(rel)
            else:
                logger.warning(f"ProjectWriteService: File verification failed for '{rel}' at '{full}'")
        return verified

    def rollback_file_plan(self, project_path: str, backup_records: List[Dict[str, Any]]) -> bool:
        """Rolls back executed file operations using recorded pre-write backups."""
        all_ok = True
        for rec in reversed(backup_records):
            full_path = rec["full_path"]
            try:
                if rec["existed"]:
                    # Restore original content
                    os.makedirs(os.path.dirname(full_path), exist_ok=True)
                    with open(full_path, "w", encoding="utf-8") as f:
                        f.write(rec["original_content"])
                    logger.info(f"ProjectWriteService: Rolled back existing file '{rec['rel_path']}'")
                else:
                    # Remove newly created file
                    if os.path.exists(full_path):
                        os.remove(full_path)
                    logger.info(f"ProjectWriteService: Removed newly created file '{rec['rel_path']}' during rollback")
            except Exception as rb_err:
                logger.error(f"ProjectWriteService: Rollback failed for '{rec['rel_path']}': {rb_err}")
                all_ok = False
        return all_ok

    def execute_write_plan(
        self,
        project_path: str,
        file_ops: List[Dict[str, str]],
        task_id: Optional[str] = None,
        enable_rollback: bool = True,
    ) -> List[str]:
        """
        Validates, canonicalizes, and executes a FileOpPlan within target project directory.
        Maintains pre-write backups for atomic rollback if an unexpected failure occurs.
        """
        if not os.path.exists(project_path):
            raise FileNotFoundError(f"Target project directory does not exist: {project_path}")

        norm_root = path_security.canonicalize_path(project_path)
        written_files: List[str] = []
        backup_records: List[Dict[str, Any]] = []

        try:
            for op in file_ops:
                rel_path = op.get("rel_path", "")
                code_content = op.get("content", "")
                if not rel_path:
                    continue

                target_full = os.path.normpath(os.path.join(norm_root, rel_path))

                # Security Gate 1: Path Canonicalization & Root Scope Check
                canonical_full = path_security.canonicalize_path(target_full, root_boundary=norm_root)

                # Security Gate 2: Write Permission Validation
                path_security.validate_write_permission(canonical_full, root_boundary=norm_root)

                # Pre-write Snapshot for Rollback
                if enable_rollback:
                    if os.path.exists(canonical_full):
                        try:
                            with open(canonical_full, "r", encoding="utf-8", errors="ignore") as f:
                                orig = f.read()
                            backup_records.append({
                                "rel_path": rel_path,
                                "full_path": canonical_full,
                                "existed": True,
                                "original_content": orig,
                            })
                        except Exception:
                            backup_records.append({
                                "rel_path": rel_path,
                                "full_path": canonical_full,
                                "existed": True,
                                "original_content": "",
                            })
                    else:
                        backup_records.append({
                            "rel_path": rel_path,
                            "full_path": canonical_full,
                            "existed": False,
                            "original_content": None,
                        })

                # Execute File Write
                os.makedirs(os.path.dirname(canonical_full), exist_ok=True)
                with open(canonical_full, "w", encoding="utf-8") as f:
                    f.write(code_content + "\n")

                written_files.append(rel_path)
                logger.info(f"ProjectWriteService: Successfully wrote file '{rel_path}' ({len(code_content)} bytes)")

                # Security Gate 3: Policy-Governed Import Repair (e.g. CSS auto-healing)
                self._repair_missing_imports(norm_root, canonical_full, code_content, task_id)

        except PathSecurityViolation as psv:
            logger.error(f"ProjectWriteService Blocked Operation: {psv}")
            if enable_rollback and backup_records:
                logger.warning("ProjectWriteService: Rolling back partial writes due to security violation")
                self.rollback_file_plan(norm_root, backup_records)
                return []
            raise
        except Exception as err:
            logger.error(f"ProjectWriteService Error writing files: {err}")
            if enable_rollback and backup_records:
                logger.warning("ProjectWriteService: Rolling back partial writes due to execution error")
                self.rollback_file_plan(norm_root, backup_records)
                return []
            raise

        # Post-write Verification
        verified = self.verify_written_files(norm_root, written_files)
        if len(verified) != len(written_files):
            logger.warning(
                f"ProjectWriteService: Verification discrepancy: {len(verified)}/{len(written_files)} files confirmed on disk."
            )

        # Autonomous Dependency Planning & Env Defaults (No direct installation)
        try:
            from core.environment_engine import environment_engine
            environment_engine.scan_missing_dependencies(norm_root)
            environment_engine.ensure_env_defaults(norm_root)
        except Exception as env_err:
            logger.warning(f"ProjectWriteService: Dependency scan warning: {env_err}")

        return written_files

    def _repair_missing_imports(self, root_path: str, full_file_path: str, code: str, task_id: Optional[str]) -> None:
        """Scans written code for relative CSS imports and creates baseline style modules."""
        css_imports = re.findall(r"import\s+['\"](\.\/[^'\"]+\.css)['\"]", code)
        for css_rel in css_imports:
            css_full = os.path.normpath(os.path.join(os.path.dirname(full_file_path), css_rel))
            try:
                canonical_css = path_security.canonicalize_path(css_full, root_boundary=root_path)
                if not os.path.exists(canonical_css):
                    os.makedirs(os.path.dirname(canonical_css), exist_ok=True)
                    with open(canonical_css, "w", encoding="utf-8") as cf:
                        cf.write("/* Auto-generated baseline style module by CUA-Sentinel */\n")

                    logger.info(f"ProjectWriteService: Repaired missing asset import '{css_rel}' at '{canonical_css}'")
                    self._log_audit_repair(task_id, css_rel, canonical_css)
            except Exception as e:
                logger.warning(f"ProjectWriteService: Could not auto-repair asset import '{css_rel}': {e}")

    def _log_audit_repair(self, task_id: Optional[str], asset_rel: str, asset_full: str) -> None:
        try:
            from db.connections import get_audit_db
            conn = get_audit_db()
            conn.execute(
                """
                INSERT INTO system_audit_log (
                    audit_id, task_id, action_type, actor, details
                ) VALUES (
                    lower(hex(randomblob(16))), ?, 'MISSING_IMPORT_REPAIRED', 'ProjectWriteService', ?
                )
                """,
                (task_id or "system", f"Created baseline asset '{asset_rel}' at path '{asset_full}'"),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"Failed to log audit repair for {asset_rel}: {e}")

    def apply_surgical_edit(
        self,
        project_path: str,
        rel_path: str,
        block_text: str,
        task_id: Optional[str] = None,
        require_read: bool = True,
    ) -> Dict[str, Any]:
        """
        Validates path boundary, applies surgical SEARCH/REPLACE blocks with strict uniqueness,
        read-before-write validation, atomic rollback, and syntax verification.
        """
        if not os.path.exists(project_path):
            raise FileNotFoundError(f"Target project directory does not exist: {project_path}")

        norm_root = path_security.canonicalize_path(project_path)
        target_full = os.path.normpath(os.path.join(norm_root, rel_path))
        canonical_full = path_security.canonicalize_path(target_full, root_boundary=norm_root)
        path_security.validate_write_permission(canonical_full, root_boundary=norm_root)

        if not os.path.exists(canonical_full):
            return {
                "success": False,
                "file": rel_path,
                "error": f"Target file does not exist for surgical edit: '{rel_path}'",
                "blocks_applied": 0,
                "blocks_failed": 0,
                "failures": [],
            }

        from core.code_diff_engine import code_diff_engine
        res = code_diff_engine.apply_search_replace_blocks(canonical_full, block_text, require_read=require_read)

        if res.get("success"):
            logger.info(f"ProjectWriteService: Applied {res.get('blocks_applied', 0)} surgical block(s) to '{rel_path}'")
            try:
                from core.environment_engine import environment_engine
                environment_engine.scan_missing_dependencies(norm_root)
                environment_engine.ensure_env_defaults(norm_root)
            except Exception as env_err:
                logger.warning(f"ProjectWriteService: Dependency scan warning: {env_err}")

        return res


project_write_service = ProjectWriteService()
