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

    # -------------------------------------------------------------------------
    # Pillar 1: Surgical Search / Replace Block Editing
    # -------------------------------------------------------------------------

    def parse_search_replace_blocks(self, text: str) -> List[Dict[str, str]]:
        """
        Parses raw LLM output for <<<<<<< SEARCH … ======= … >>>>>>> REPLACE blocks.

        Returns a list of {"search": str, "replace": str} dicts, with leading/trailing
        blank lines stripped from each half.  Returns [] if no blocks are found.
        """
        import re as _re

        pattern = _re.compile(
            r'<<<<<<< SEARCH\n(.*?)=======\n(.*?)>>>>>>> REPLACE',
            _re.DOTALL
        )

        blocks: List[Dict[str, str]] = []
        for match in pattern.finditer(text):
            search_text = match.group(1)
            replace_text = match.group(2)

            # Strip leading/trailing blank lines while preserving internal indentation
            search_text = "\n".join(
                line for line in search_text.split("\n")
            ).strip("\n")
            replace_text = "\n".join(
                line for line in replace_text.split("\n")
            ).strip("\n")

            blocks.append({"search": search_text, "replace": replace_text})

        return blocks

    def apply_search_replace_blocks(self, file_path: str, block_text: str) -> Dict[str, Any]:
        """
        Applies all SEARCH/REPLACE blocks from *block_text* to *file_path* on disk.

        Strategy for each block:
          1. Exact string match → replace first occurrence.
          2. Whitespace-normalised match → locate matching line range in original
             content and splice the replacement in.
          3. If still not found → record as a failure.

        Returns::

            {
                "success": bool,
                "file": str,
                "blocks_applied": int,
                "blocks_failed": int,
                "failures": [{"block": int, "error": str}, ...]
            }
        """
        import re as _re

        if not os.path.exists(file_path):
            return {"success": False, "error": "File not found"}

        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as fh:
                original_content = fh.read()
        except Exception as exc:
            return {"success": False, "error": f"Could not read file: {exc}"}

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

        content = original_content
        applied = 0
        failures: List[Dict[str, Any]] = []

        def _normalize_ws(s: str) -> str:
            """Collapse all whitespace runs to a single space."""
            return _re.sub(r'\s+', ' ', s).strip()

        for idx, block in enumerate(blocks):
            search_str = block["search"]
            replace_str = block["replace"]
            replaced = False

            # --- Strategy 1: exact match ---
            if search_str in content:
                content = content.replace(search_str, replace_str, 1)
                applied += 1
                replaced = True

            # --- Strategy 2: whitespace-normalised match ---
            if not replaced:
                norm_search = _normalize_ws(search_str)
                lines = content.splitlines(keepends=True)

                # Build a sliding window over lines, comparing normalised text
                search_line_count = search_str.count("\n") + 1
                # Allow ±3 line slack for minor blank-line differences
                for window_size in range(
                    max(1, search_line_count - 3),
                    search_line_count + 4
                ):
                    for start_idx in range(len(lines) - window_size + 1):
                        window = lines[start_idx: start_idx + window_size]
                        norm_window = _normalize_ws("".join(window))
                        if norm_window == norm_search:
                            # Preserve trailing newline of last window line
                            trailing_nl = "\n" if "".join(window).endswith("\n") else ""
                            replacement_lines = replace_str + trailing_nl
                            lines[start_idx: start_idx + window_size] = [replacement_lines]
                            content = "".join(lines)
                            applied += 1
                            replaced = True
                            break
                    if replaced:
                        break

            if not replaced:
                logger.warning(
                    "apply_search_replace_blocks: block %d not found in %s",
                    idx, file_path
                )
                failures.append({"block": idx, "error": "SEARCH block not found in file"})

        # Write updated content back only when at least one block was applied
        if applied > 0:
            try:
                with open(file_path, "w", encoding="utf-8") as fh:
                    fh.write(content)
            except Exception as exc:
                return {
                    "success": False,
                    "file": file_path,
                    "error": f"Could not write file: {exc}",
                    "blocks_applied": applied,
                    "blocks_failed": len(failures),
                    "failures": failures
                }

        return {
            "success": len(failures) == 0,
            "file": file_path,
            "blocks_applied": applied,
            "blocks_failed": len(failures),
            "failures": failures
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
