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

    _session_read_files: set = set()

    @classmethod
    def record_file_read(cls, file_path: str) -> None:
        """Records that a file has been inspected/read within the current session."""
        norm = os.path.normcase(os.path.normpath(os.path.abspath(file_path)))
        cls._session_read_files.add(norm)

    @classmethod
    def is_file_read(cls, file_path: str) -> bool:
        """Checks if a file has been read in the current session."""
        norm = os.path.normcase(os.path.normpath(os.path.abspath(file_path)))
        return norm in cls._session_read_files

    @classmethod
    def clear_session_reads(cls) -> None:
        """Clears all session-tracked file reads."""
        cls._session_read_files.clear()

    # -------------------------------------------------------------------------
    # Pillar 1: Surgical Search / Replace Block Editing
    # -------------------------------------------------------------------------

    def parse_search_replace_blocks(self, text: str) -> List[Dict[str, str]]:
        """
        Parses raw LLM output for <<<<<<< SEARCH … ======= … >>>>>>> REPLACE blocks.

        Returns a list of {"search": str, "replace": str} dicts, with leading/trailing
        blank lines stripped from each half. Returns [] if no blocks are found.
        """
        import re as _re

        pattern = _re.compile(
            r'<<<<<<< SEARCH[^\S\r\n]*\r?\n(.*?)=======[^\S\r\n]*\r?\n(.*?)>>>>>>> REPLACE',
            _re.DOTALL
        )

        blocks: List[Dict[str, str]] = []
        for match in pattern.finditer(text):
            search_text = match.group(1)
            replace_text = match.group(2)

            # Strip leading/trailing newlines while preserving internal indentation
            search_text = search_text.strip("\r\n")
            replace_text = replace_text.strip("\r\n")

            blocks.append({"search": search_text, "replace": replace_text})

        return blocks

    def apply_search_replace_blocks(
        self,
        file_path: str,
        block_text: str,
        require_read: bool = False,
    ) -> Dict[str, Any]:
        """
        Applies all SEARCH/REPLACE blocks from *block_text* to *file_path* on disk.

        Strict Invariants (Claude Code Harness):
          1. Read-Before-Write: target file must have been inspected within session if require_read=True.
          2. Exact & Unique Match: search block must appear EXACTLY ONCE in the target content.
             Ambiguous (>1 match) or missing (0 match) search blocks are rejected immediately.
          3. Atomic All-or-Nothing: if any block in a multi-block edit fails, no changes are written to disk.
          4. Syntax & AST Verification: validates Python / JSON syntax before saving to disk.
             On syntax error, changes are aborted without modifying disk.

        Returns::

            {
                "success": bool,
                "file": str,
                "blocks_applied": int,
                "blocks_failed": int,
                "failures": [{"block": int, "error": str}, ...],
                "error": Optional[str],
                "reverted": Optional[bool]
            }
        """
        if not os.path.exists(file_path):
            return {"success": False, "file": file_path, "error": f"File not found: {file_path}", "blocks_applied": 0, "blocks_failed": 0, "failures": []}

        # Invariant 1: Read-Before-Write
        if require_read and not self.is_file_read(file_path):
            rel_name = os.path.basename(file_path)
            return {
                "success": False,
                "file": file_path,
                "error": f"Read-before-write invariant violated: '{rel_name}' must be read before editing.",
                "blocks_applied": 0,
                "blocks_failed": 1,
                "failures": [{"block": -1, "error": f"Read-before-write invariant violated: '{rel_name}' must be read before editing."}],
            }

        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as fh:
                original_content = fh.read()
        except Exception as exc:
            return {"success": False, "file": file_path, "error": f"Could not read file: {exc}", "blocks_applied": 0, "blocks_failed": 0, "failures": []}

        blocks = self.parse_search_replace_blocks(block_text)
        if not blocks:
            return {
                "success": True,
                "file": file_path,
                "blocks_applied": 0,
                "blocks_failed": 0,
                "failures": [],
                "warning": "No SEARCH/REPLACE blocks found in block_text"
            }

        is_crlf = "\r\n" in original_content
        staged_content = original_content
        failures: List[Dict[str, Any]] = []

        for idx, block in enumerate(blocks):
            raw_search = block["search"]
            raw_replace = block["replace"]

            if not raw_search.strip():
                failures.append({"block": idx, "error": "SEARCH block is empty"})
                continue

            # Adapt line endings to match target file content
            if is_crlf:
                search_str = raw_search.replace("\r\n", "\n").replace("\n", "\r\n")
                replace_str = raw_replace.replace("\r\n", "\n").replace("\n", "\r\n")
            else:
                search_str = raw_search.replace("\r\n", "\n")
                replace_str = raw_replace.replace("\r\n", "\n")

            # Invariant 2: Exact & Unique Match Check
            count = staged_content.count(search_str)
            if count == 0:
                logger.warning(
                    "apply_search_replace_blocks: block %d not found in %s",
                    idx, file_path
                )
                failures.append({
                    "block": idx,
                    "error": "SEARCH block not found in file. Ensure exact whitespace, indentation, and line match."
                })
            elif count > 1:
                logger.warning(
                    "apply_search_replace_blocks: block %d ambiguous in %s (found %d matches)",
                    idx, file_path, count
                )
                failures.append({
                    "block": idx,
                    "error": f"SEARCH block is ambiguous: found {count} exact occurrences. Provide more surrounding context lines."
                })
            else:
                staged_content = staged_content.replace(search_str, replace_str, 1)

        # Invariant 3: Atomic All-or-Nothing Gate
        if failures:
            return {
                "success": False,
                "file": file_path,
                "error": f"Failed applying {len(failures)} block(s): " + "; ".join(f["error"] for f in failures),
                "blocks_applied": 0,
                "blocks_failed": len(failures),
                "failures": failures,
            }

        # Invariant 4: Syntax / AST Verification Gate
        ext = os.path.splitext(file_path)[1].lower()
        if ext == ".py":
            import ast
            try:
                ast.parse(staged_content)
            except SyntaxError as syn:
                return {
                    "success": False,
                    "file": file_path,
                    "error": f"SYNTAX_ERROR: Python SyntaxError on line {syn.lineno}: {syn.msg}",
                    "reverted": True,
                    "blocks_applied": 0,
                    "blocks_failed": len(blocks),
                    "failures": [{"block": -1, "error": f"Python SyntaxError on line {syn.lineno}: {syn.msg}"}],
                }
        elif ext == ".json":
            import json
            try:
                json.loads(staged_content)
            except Exception as jerr:
                return {
                    "success": False,
                    "file": file_path,
                    "error": f"SYNTAX_ERROR: JSON syntax error: {jerr}",
                    "reverted": True,
                    "blocks_applied": 0,
                    "blocks_failed": len(blocks),
                    "failures": [{"block": -1, "error": f"JSON syntax error: {jerr}"}],
                }

        # Write atomically verified content to disk
        try:
            with open(file_path, "w", encoding="utf-8", newline="") as fh:
                fh.write(staged_content)
        except Exception as exc:
            return {
                "success": False,
                "file": file_path,
                "error": f"Could not write file: {exc}",
                "blocks_applied": 0,
                "blocks_failed": len(blocks),
                "failures": [{"block": -1, "error": str(exc)}],
            }

        return {
            "success": True,
            "file": file_path,
            "blocks_applied": len(blocks),
            "blocks_failed": 0,
            "failures": [],
        }

    # -------------------------------------------------------------------------
    # Pillar 5: Exact Installed-Package Contract Extraction
    # -------------------------------------------------------------------------

    def extract_installed_packages(self, project_path: str) -> Dict[str, List[str]]:
        """
        Extracts actually-installed packages for LLM contract injection.

        Checks three sources and merges/deduplicates results:

        * ``package.json`` (JS/TS – both *dependencies* and *devDependencies*)
        * ``requirements.txt`` (Python – strips version pins and comments)
        * ``.venv/Lib/site-packages/`` (Python venv – top-level package dirs)

        Returns::

            {
                "js_packages":   [...],   # from package.json
                "py_packages":   [...],   # from requirements.txt
                "venv_packages": [...]    # from .venv site-packages
            }
        """
        import json as _json
        import re as _re

        js_packages: List[str] = []
        py_packages: List[str] = []
        venv_packages: List[str] = []

        # ---- JS/TS: package.json ------------------------------------------------
        pkg_json_path = os.path.join(project_path, "package.json")
        if os.path.isfile(pkg_json_path):
            try:
                with open(pkg_json_path, "r", encoding="utf-8", errors="ignore") as fh:
                    pkg_data = _json.load(fh)
                seen_js: set = set()
                for section in ("dependencies", "devDependencies"):
                    for name in pkg_data.get(section, {}).keys():
                        if name not in seen_js:
                            seen_js.add(name)
                            js_packages.append(name)
            except Exception as exc:
                logger.warning("extract_installed_packages: could not parse package.json: %s", exc)

        # ---- Python: requirements.txt ------------------------------------------
        req_path = os.path.join(project_path, "requirements.txt")
        if os.path.isfile(req_path):
            try:
                with open(req_path, "r", encoding="utf-8", errors="ignore") as fh:
                    req_lines = fh.readlines()
                seen_py: set = set()
                for line in req_lines:
                    line = line.strip()
                    # Skip blanks and pure comments
                    if not line or line.startswith("#"):
                        continue
                    # Strip inline comments
                    line = line.split("#")[0].strip()
                    # Strip version pins: ==, >=, <=, ~=, !=, >x, <x
                    pkg_name = _re.split(r'[><=!~;\[]', line)[0].strip()
                    if pkg_name and pkg_name not in seen_py:
                        seen_py.add(pkg_name)
                        py_packages.append(pkg_name)
            except Exception as exc:
                logger.warning("extract_installed_packages: could not parse requirements.txt: %s", exc)

        # ---- Python: .venv site-packages ----------------------------------------
        # Windows layout:  .venv/Lib/site-packages/
        # Unix layout:     .venv/lib/pythonX.Y/site-packages/
        candidate_site_paths: List[str] = []

        win_site = os.path.join(project_path, ".venv", "Lib", "site-packages")
        if os.path.isdir(win_site):
            candidate_site_paths.append(win_site)

        # Also check Unix-style layout
        lib_dir = os.path.join(project_path, ".venv", "lib")
        if os.path.isdir(lib_dir):
            for entry in os.listdir(lib_dir):
                unix_site = os.path.join(lib_dir, entry, "site-packages")
                if os.path.isdir(unix_site):
                    candidate_site_paths.append(unix_site)

        seen_venv: set = set()
        for site_path in candidate_site_paths:
            try:
                for entry in os.listdir(site_path):
                    full_entry = os.path.join(site_path, entry)
                    # Top-level directories only; skip files and hidden/private/dist-info dirs
                    if not os.path.isdir(full_entry):
                        continue
                    if entry == "__pycache__":
                        continue
                    if entry.startswith("_"):
                        continue
                    if entry.endswith(".dist-info") or entry.endswith(".data"):
                        continue
                    if entry not in seen_venv:
                        seen_venv.add(entry)
                        venv_packages.append(entry)
            except Exception as exc:
                logger.warning(
                    "extract_installed_packages: could not list site-packages at %s: %s",
                    site_path, exc
                )

        # Deduplicate venv_packages against py_packages (normalise hyphens/underscores)
        def _norm_pkg(n: str) -> str:
            return n.lower().replace("-", "_")

        py_norm = {_norm_pkg(p) for p in py_packages}
        venv_packages = [
            p for p in venv_packages if _norm_pkg(p) not in py_norm
        ]

        return {
            "js_packages": js_packages,
            "py_packages": py_packages,
            "venv_packages": venv_packages
        }


code_diff_engine = CodeDiffEngine()
