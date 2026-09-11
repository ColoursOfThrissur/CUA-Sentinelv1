"""
Execution Broker Module for CUA-Sentinel.

Central trust boundary between LLM code generation and physical filesystem execution.
Processes Normalized File Operations (FileOpPlan), canonicalizes paths, enforces security boundaries,
executes atomic writes, and registers policy-governed repairs in audit DB.
"""

import os
import re
import logging
from typing import List, Dict, Any, Optional
from core.path_security import path_security, PathSecurityViolation

logger = logging.getLogger(__name__)

class ExecutionBroker:
    def __init__(self):
        pass

    def parse_raw_llm_code_blocks(self, text: str) -> List[Dict[str, str]]:
        """
        Parses raw LLM markdown response into Normalized File Operations (FileOpPlan).
        Look for code blocks matching:
        ```tsx
        // filepath: src/components/Component.tsx
        // code content...
        ```
        or:
        ```python
        # filepath: backend/main.py
        # code content...
        ```
        """
        file_ops = []
        pattern = re.compile(
            r'```(?:\w+)?\s*(?:#|//|/\*)\s*(?:file|filepath):\s*([^\n\r]+)\n(.*?)```',
            re.DOTALL | re.IGNORECASE
        )
        matches = pattern.findall(text)
        for rel_path, code in matches:
            rel_path = rel_path.strip().strip("'\"")
            if rel_path:
                file_ops.append({
                    "rel_path": rel_path,
                    "content": code.strip()
                })
        return file_ops

    def execute_write_plan(
        self,
        project_path: str,
        file_ops: List[Dict[str, str]],
        task_id: Optional[str] = None
    ) -> List[str]:
        """
        Validates, canonicalizes, and executes a FileOpPlan within target project directory.
        """
        if not os.path.exists(project_path):
            raise FileNotFoundError(f"Target project directory does not exist: {project_path}")

        norm_root = path_security.canonicalize_path(project_path)
        written_files = []

        for op in file_ops:
            rel_path = op.get("rel_path", "")
            code_content = op.get("content", "")
            if not rel_path:
                continue

            target_full = os.path.normpath(os.path.join(norm_root, rel_path))

            try:
                # Security Gate 1: Path Canonicalization & Root Scope Check
                canonical_full = path_security.canonicalize_path(target_full, root_boundary=norm_root)

                # Security Gate 2: Write Permission Validation
                path_security.validate_write_permission(canonical_full, root_boundary=norm_root)

                # Execute File Write
                os.makedirs(os.path.dirname(canonical_full), exist_ok=True)
                with open(canonical_full, "w", encoding="utf-8") as f:
                    f.write(code_content + "\n")

                written_files.append(rel_path)
                logger.info(f"ExecutionBroker: Successfully wrote file '{rel_path}' ({len(code_content)} bytes)")

                # Security Gate 3: Policy-Governed Import Repair (e.g. CSS auto-healing)
                self._repair_missing_imports(norm_root, canonical_full, code_content, task_id)

            except PathSecurityViolation as psv:
                logger.error(f"ExecutionBroker Blocked Operation for '{rel_path}': {psv}")
            except Exception as err:
                logger.warning(f"ExecutionBroker Error writing file '{rel_path}': {err}")

        # Security Gate 4: Autonomous Dependency Auto-Installation & Env Defaults
        try:
            from core.environment_engine import environment_engine
            environment_engine.scan_and_install_dependencies(norm_root)
            environment_engine.ensure_env_defaults(norm_root)
        except Exception as env_err:
            logger.warning(f"ExecutionBroker: EnvironmentEngine auto-install warning: {env_err}")

        return written_files

    def _repair_missing_imports(self, root_path: str, full_file_path: str, code: str, task_id: Optional[str]) -> None:
        """
        Scans written code for relative CSS imports and performs policy-controlled asset repair.
        Logs operation in audit DB.
        """
        css_imports = re.findall(r"import\s+['\"](\.\/[^'\"]+\.css)['\"]", code)
        for css_rel in css_imports:
            css_full = os.path.normpath(os.path.join(os.path.dirname(full_file_path), css_rel))
            try:
                canonical_css = path_security.canonicalize_path(css_full, root_boundary=root_path)
                if not os.path.exists(canonical_css):
                    os.makedirs(os.path.dirname(canonical_css), exist_ok=True)
                    with open(canonical_css, "w", encoding="utf-8") as cf:
                        cf.write("/* Auto-generated baseline style module by CUA-Sentinel ExecutionBroker */\n")

                    logger.info(f"ExecutionBroker: Repaired missing asset import '{css_rel}' at '{canonical_css}'")

                    # Audit DB Log Registration
                    self._log_audit_repair(task_id, css_rel, canonical_css)
            except Exception as e:
                logger.warning(f"ExecutionBroker: Could not auto-repair asset import '{css_rel}': {e}")

    def _log_audit_repair(self, task_id: Optional[str], asset_rel: str, asset_full: str) -> None:
        try:
            from db.connections import get_audit_db
            conn = get_audit_db()
            conn.execute(
                """
                INSERT INTO system_audit_log (
                    audit_id, task_id, action_type, actor, details
                ) VALUES (
                    lower(hex(randomblob(16))), ?, 'MISSING_IMPORT_REPAIRED', 'ExecutionBroker', ?
                )
                """,
                (task_id or "system", f"Created baseline asset '{asset_rel}' at path '{asset_full}'")
            )
            conn.commit()
            conn.close()
        except Exception:
            pass

execution_broker = ExecutionBroker()
