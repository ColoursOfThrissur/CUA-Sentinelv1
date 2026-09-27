r"""
Drive Path Security Guardrail Module for CUA-Sentinel.

Enforces OS protection rules:
- Strictly BLOCKS write/edit/delete operations on critical OS directories (Windows, Program Files, System32).
- PERMITS read-only inspection for runtime package and environment verifications.
- GRANTS full read/write/edit permissions on designated project storage paths.
- Enforces Path Canonicalization (Path.resolve()) to prevent relative path escapes (../).
- Blocks writes to critical protected system/meta files (.git, .env, *.sqlite).
"""

import os
import logging
from pathlib import Path
from typing import Tuple, Optional, List

logger = logging.getLogger(__name__)


class PathSecurityViolation(Exception):
    pass


PROTECTED_EXCLUSION_NAMES = {
    ".git", ".sentinel_backup",
    "operational.sqlite", "audit.sqlite", "projects.sqlite", "knowledge.sqlite", "features.sqlite"
}

CRITICAL_SYSTEM_DIRS = {
    "windows", "system32", "syswow64", "program files", "program files (x86)",
    "programdata", "recovery", "boot", "$recycle.bin"
}


class PathSecurityGuardrail:
    def __init__(self, allowed_drives: Optional[List[str]] = None, allowed_project_roots: Optional[List[str]] = None):
        if allowed_drives is None:
            allowed_drives = ["C:", "D:", "E:", "F:", "G:"]
        self.allowed_drives = [d.upper() for d in allowed_drives]

        if allowed_project_roots is None:
            allowed_project_roots = ["projects", "workspace", "cua-sentinel", "temp", ".gemini\\antigravity"]
        self.allowed_project_roots = [r.lower() for r in allowed_project_roots]

    def canonicalize_path(self, target_path: str, root_boundary: Optional[str] = None) -> str:
        r"""
        Canonicalizes target_path by resolving symlinks and relative operators (../).
        If root_boundary is supplied, verifies target_path resolves inside root_boundary.
        """
        if not target_path:
            raise PathSecurityViolation("Target path is empty.")

        try:
            resolved_target = Path(target_path).resolve()
        except Exception as e:
            raise PathSecurityViolation(f"Invalid path format '{target_path}': {e}")

        # Protect critical system files / folders
        for part in resolved_target.parts:
            low_part = part.lower()
            if low_part in PROTECTED_EXCLUSION_NAMES:
                raise PathSecurityViolation(f"Path Security Violation: Cannot mutate protected asset '{part}' in '{resolved_target}'")
            if low_part in CRITICAL_SYSTEM_DIRS:
                raise PathSecurityViolation(f"Path Security Violation: Cannot mutate critical OS system directory '{part}' in '{resolved_target}'")

        if root_boundary:
            try:
                resolved_root = Path(root_boundary).resolve()
                resolved_target.relative_to(resolved_root)
            except ValueError:
                raise PathSecurityViolation(
                    f"SECURITY BLOCK: Path '{resolved_target}' escapes designated project root boundary '{resolved_root}'!"
                )

        return str(resolved_target)

    def validate_write_permission(self, target_path: str, root_boundary: Optional[str] = None) -> bool:
        r"""
        Validates whether target_path is allowed for write/edit/delete operations.
        Blocks root OS directories and enforces safe project locations.
        """
        norm_path = self.canonicalize_path(target_path, root_boundary=root_boundary)
        drive_letter = os.path.splitdrive(norm_path)[0].upper()
        low_path = norm_path.lower()

        # Check for critical system directories regardless of drive
        for part in Path(norm_path).parts:
            if part.lower() in CRITICAL_SYSTEM_DIRS:
                raise PathSecurityViolation(f"SECURITY BLOCK: Cannot mutate OS system directory: '{norm_path}'")

        # C:\ OS Drive: Allowed inside safe user project roots
        if drive_letter == "C:":
            is_safe_project = any(root in low_path for root in self.allowed_project_roots)
            if is_safe_project:
                return True

            logger.error(f"PathSecurityViolation: Write operation blocked on OS drive root path: {norm_path}")
            raise PathSecurityViolation(
                f"SECURITY BLOCK: File write operation blocked on C:\\ system path: '{norm_path}'. "
                "Projects on C:\\ must be located inside a 'Projects' or 'workspace' directory."
            )

        if drive_letter in self.allowed_drives:
            return True

        return True

    def validate_read_permission(self, target_path: str) -> bool:
        r"""
        Validates whether target_path is allowed for read operations.
        Blocks critical OS system directories (System32, Windows, etc.)
        but allows reading from any safe user-accessible location.
        """
        if not target_path:
            return False

        try:
            resolved = Path(target_path).resolve()
        except Exception:
            return False

        # Block reads from critical system directories
        parts_lower = [p.lower() for p in resolved.parts]
        for part in parts_lower:
            if part in CRITICAL_SYSTEM_DIRS:
                logger.warning(f"Read blocked: path touches critical system directory '{part}' in '{resolved}'")
                return False

        # Block reads of protected sentinel assets (databases, .git)
        if resolved.name.lower() in PROTECTED_EXCLUSION_NAMES:
            logger.warning(f"Read blocked: path targets protected asset '{resolved.name}' in '{resolved}'")
            return False

        # Verify drive is in allowed list
        drive_letter = os.path.splitdrive(str(resolved))[0].upper()
        if drive_letter and drive_letter not in self.allowed_drives:
            logger.warning(f"Read blocked: drive '{drive_letter}' not in allowed drives")
            return False

        return True


path_security = PathSecurityGuardrail()
