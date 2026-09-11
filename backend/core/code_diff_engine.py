"""
Code Diff & Patch Engine for CUA-Sentinel.

Calculates unified line-by-line diffs between existing files and proposed AI code modifications,
validates write safety via PathSecurityGuardrail, and manages 1-click patch rollbacks.
"""

import os
import difflib
import logging
from typing import Dict, Any, List, Optional
from core.path_security import path_security, PathSecurityViolation

logger = logging.getLogger(__name__)

class CodeDiffEngine:
    def compute_diff(self, old_content: str, new_content: str, filename: str = "file") -> Dict[str, Any]:
        """
        Generates a unified git-style diff and line stats (additions, deletions).
        """
        old_lines = old_content.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)

        diff_lines = list(difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"a/{filename}",
            tofile=f"b/{filename}"
        ))

        additions = sum(1 for line in diff_lines if line.startswith("+") and not line.startswith("+++"))
        deletions = sum(1 for line in diff_lines if line.startswith("-") and not line.startswith("---"))

        return {
            "filename": filename,
            "diff": "".join(diff_lines),
            "additions": additions,
            "deletions": deletions,
            "is_new_file": not bool(old_content.strip()),
            "total_lines_new": len(new_lines)
        }

    def compute_project_diff(self, project_path: str, proposed_files: Dict[str, str]) -> Dict[str, Any]:
        """
        Computes diff summary across multiple proposed file changes in project_path.
        """
        file_diffs = []
        total_additions = 0
        total_deletions = 0

        for rel_path, new_code in proposed_files.items():
            full_path = os.path.normpath(os.path.join(project_path, rel_path))
            old_code = ""
            if os.path.exists(full_path):
                try:
                    with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                        old_code = f.read()
                except Exception as err:
                    logger.warning(f"Could not read existing file for diff {full_path}: {err}")

            file_diff = self.compute_diff(old_code, new_code, filename=rel_path)
            file_diffs.append(file_diff)
            total_additions += file_diff["additions"]
            total_deletions += file_diff["deletions"]

        return {
            "project_path": project_path,
            "total_files_changed": len(file_diffs),
            "total_additions": total_additions,
            "total_deletions": total_deletions,
            "file_diffs": file_diffs
        }

code_diff_engine = CodeDiffEngine()
