"""
AST & Functional Stub Verification Gate Module for CUA-Sentinel.

Executes non-AI deterministic code checking using Python AST parsing and regex heuristics
to catch syntax errors, symbol mismatches, and placeholder stubs (e.g. pass, TODOs, NotImplementedError).
"""

import ast
import re
import os
import logging
from typing import Dict, Any, List, Tuple

logger = logging.getLogger(__name__)

STUB_COMMENTS_REGEX = re.compile(
    r'(?://|#|/\*)\s*(?:TODO|FIXME|HACK|IMPLEMENT ME|PLACEHOLDER|TBD)\b',
    re.IGNORECASE
)

class VerificationGate:
    def __init__(self, max_retries: int = 5):
        self.max_retries = max_retries
        self.retry_counts: Dict[str, int] = {}

    def _is_python_node_stub(self, node: ast.AST) -> bool:
        """
        Checks if a function node body consists ONLY of a placeholder stub:
        - pass statement
        - ... (Ellipsis)
        - raise NotImplementedError
        - docstring/bare string with no executable statements
        """
        if not hasattr(node, "body") or not node.body:
            return True

        non_stub_statements = []
        for stmt in node.body:
            if isinstance(stmt, ast.Pass):
                continue
            if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
                # Bare string / docstring / Ellipsis (...)
                continue
            if isinstance(stmt, ast.Raise):
                if isinstance(stmt.exc, ast.Call) and isinstance(stmt.exc.func, ast.Name) and stmt.exc.func.id == "NotImplementedError":
                    continue
                if isinstance(stmt.exc, ast.Name) and stmt.exc.id == "NotImplementedError":
                    continue
            non_stub_statements.append(stmt)

        return len(non_stub_statements) == 0

    def verify_python_code(self, code_snippet: str, expected_symbols: List[str] = None) -> Tuple[bool, List[str]]:
        """
        Parses Python code snippet via AST and checks for syntax errors, case-sensitive symbols,
        and empty functional stubs (pass, ..., raise NotImplementedError).
        Returns (is_valid, error_messages).
        """
        errors = []
        if not code_snippet or not code_snippet.strip():
            return False, ["Code snippet is empty."]

        # 1. Check AST Syntax Validity
        try:
            tree = ast.parse(code_snippet)
        except SyntaxError as se:
            logger.warning(f"AST SyntaxError detected: {se}")
            return False, [f"AST SyntaxError at line {se.lineno}: {se.msg}"]

        # 2. Check for Placeholder Stubs in Functions
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if self._is_python_node_stub(node):
                    errors.append(
                        f"Stub Implementation Error: Function '{node.name}' at line {node.lineno} body is an unfulfilled placeholder stub (contains only pass / ... / NotImplementedError). Complete implementation is required."
                    )

        # 3. Check for TODO/FIXME Placeholder Comments
        if STUB_COMMENTS_REGEX.search(code_snippet):
            errors.append("Placeholder Comment Error: Code contains unfulfilled TODO/FIXME comments.")

        # 4. Extract defined symbols & check expected symbols
        defined_symbols = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                defined_symbols.add(node.name)
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        defined_symbols.add(target.id)

        if expected_symbols:
            for expected in expected_symbols:
                if expected not in defined_symbols:
                    case_mismatches = [s for s in defined_symbols if s.lower() == expected.lower()]
                    if case_mismatches:
                        errors.append(
                            f"Symbol Case Morphing Error: Expected '{expected}', but found '{case_mismatches[0]}'. Case must match exactly."
                        )
                    else:
                        errors.append(f"Missing Required Symbol: Expected '{expected}' was not defined in generated code.")

        is_valid = len(errors) == 0
        return is_valid, errors

    def verify_js_ts_code(self, code_snippet: str) -> Tuple[bool, List[str]]:
        """
        Checks JS/TS code for TODO/FIXME placeholders and throw new Error("Not implemented") stubs.
        """
        errors = []
        if not code_snippet or not code_snippet.strip():
            return False, ["JS/TS code snippet is empty."]

        if STUB_COMMENTS_REGEX.search(code_snippet):
            errors.append("Placeholder Comment Error in JS/TS: Code contains unfulfilled TODO/FIXME comments.")

        if re.search(r'throw\s+new\s+Error\s*\(\s*["\'](?:Not\s+implemented|TODO|Placeholder)["\']\s*\)', code_snippet, re.I):
            errors.append("Stub Implementation Error in JS/TS: Code contains 'throw new Error(\"Not implemented\")' stub.")

        if re.search(r'return\s*\(?\s*<div[^>]*>\s*(?:TODO|LLM generation in progress)[^<]*</div>', code_snippet, re.I):
            errors.append("Stub Component Error in React: Component returns a placeholder 'TODO' HTML block.")

        return len(errors) == 0, errors

    def evaluate_tapered_retry(self, task_id: str) -> Dict[str, Any]:
        current_retries = self.retry_counts.get(task_id, 0) + 1
        self.retry_counts[task_id] = current_retries

        if current_retries in (1, 2):
            return {
                "action": "retry_standard",
                "attempt": current_retries,
                "prompt_injection": None
            }
        elif current_retries in (3, 4):
            return {
                "action": "retry_tapered",
                "attempt": current_retries,
                "prompt_injection": "ATTENTION: Previous attempts failed verification or contained placeholder stubs. Write a complete, production-ready implementation with no stubs."
            }
        else:
            return {
                "action": "hard_halt",
                "attempt": current_retries,
                "prompt_injection": "FATAL: Maximum retry limit (5) reached. Task halted gracefully."
            }

    def reset_retry(self, task_id: str):
        if task_id in self.retry_counts:
            del self.retry_counts[task_id]

    # ------------------------------------------------------------------
    # Pillar 3: Closed-Loop Compiler Verification
    # ------------------------------------------------------------------

    def verify_code_compilation(
        self, project_path: str, modified_files: List[str] = None
    ) -> Dict[str, Any]:
        """
        Runs the real compiler (tsc / py_compile / ast.parse) on the project
        and returns structured results with parsed error locations.
        """
        import subprocess

        ts_errors: List[Dict[str, Any]] = []
        py_errors: List[Dict[str, Any]] = []
        compiler_stderr: str = ""
        checks_run: List[str] = []

        # ── Detect project types ──────────────────────────────────────
        has_ts = (
            os.path.isfile(os.path.join(project_path, "package.json"))
            and (
                os.path.isfile(os.path.join(project_path, "tsconfig.json"))
                or os.path.isdir(os.path.join(project_path, "src"))
            )
        )

        py_files_modified: List[str] = []
        if modified_files:
            py_files_modified = [f for f in modified_files if f.endswith(".py")]
        has_py = bool(py_files_modified)

        # If modified_files not provided, scan project root for any .py files
        if not modified_files:
            SKIP_DIRS = {"node_modules", ".venv", "dist", "build", "__pycache__"}
            for root, dirs, files in os.walk(project_path):
                dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
                if any(f.endswith(".py") for f in files):
                    has_py = True
                    break

        # ── TypeScript / React check ──────────────────────────────────
        has_node_modules = os.path.isdir(os.path.join(project_path, "node_modules"))
        if has_ts and has_node_modules:
            checks_run.append("typescript")
            try:
                proc = subprocess.run(
                    "npx tsc --noEmit",
                    shell=True,
                    cwd=project_path,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                compiler_stderr = proc.stderr or ""
                if proc.returncode != 0:
                    # Parse lines like: src/foo.ts(12,5): error TS2345: ...
                    ts_error_re = re.compile(
                        r"^(?P<file>.+?)\((?P<line>\d+),(?P<col>\d+)\):\s+error\s+"
                        r"(?P<code>TS\d+):\s+(?P<message>.+)$"
                    )
                    output = proc.stdout or ""
                    for raw_line in output.splitlines():
                        m = ts_error_re.match(raw_line.strip())
                        if m:
                            ts_errors.append(
                                {
                                    "file": m.group("file"),
                                    "line": int(m.group("line")),
                                    "col": int(m.group("col")),
                                    "code": m.group("code"),
                                    "message": m.group("message"),
                                }
                            )
                    # If tsc produced no parseable errors but still failed,
                    # add a generic entry so callers know something went wrong.
                    if not ts_errors and (proc.stdout or compiler_stderr):
                        ts_errors.append(
                            {
                                "file": project_path,
                                "line": 0,
                                "col": 0,
                                "code": "TS0000",
                                "message": (proc.stdout or compiler_stderr).strip()[:500],
                            }
                        )
            except subprocess.TimeoutExpired:
                ts_errors.append(
                    {
                        "file": project_path,
                        "line": 0,
                        "col": 0,
                        "code": "TS_TIMEOUT",
                        "message": "tsc --noEmit timed out after 60 seconds.",
                    }
                )
            except Exception as exc:
                logger.warning(f"TypeScript compilation check failed: {exc}")
                ts_errors.append(
                    {
                        "file": project_path,
                        "line": 0,
                        "col": 0,
                        "code": "TS_ERROR",
                        "message": str(exc),
                    }
                )

        # ── Python check ──────────────────────────────────────────────
        if has_py:
            checks_run.append("python")

            if py_files_modified:
                # Run py_compile on each explicitly modified .py file
                import py_compile
                for rel_or_abs in py_files_modified:
                    abs_path = (
                        rel_or_abs
                        if os.path.isabs(rel_or_abs)
                        else os.path.join(project_path, rel_or_abs)
                    )
                    if not os.path.isfile(abs_path):
                        continue
                    try:
                        py_compile.compile(abs_path, doraise=True)
                    except py_compile.PyCompileError as pce:
                        line_match = re.search(r"line (\d+)", str(pce))
                        lineno = int(line_match.group(1)) if line_match else 0
                        py_errors.append(
                            {
                                "file": abs_path,
                                "line": lineno,
                                "message": str(pce),
                            }
                        )
            else:
                # Walk the project and ast.parse all .py files
                SKIP_DIRS = {"node_modules", ".venv", "dist", "build", "__pycache__"}
                for root, dirs, files in os.walk(project_path):
                    dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
                    for fname in files:
                        if not fname.endswith(".py"):
                            continue
                        abs_path = os.path.join(root, fname)
                        try:
                            with open(abs_path, "r", encoding="utf-8", errors="ignore") as fh:
                                source = fh.read()
                            ast.parse(source)
                        except SyntaxError as se:
                            py_errors.append(
                                {
                                    "file": abs_path,
                                    "line": se.lineno or 0,
                                    "message": f"{se.msg} (col {se.offset})",
                                }
                            )
                        except Exception as exc:
                            py_errors.append(
                                {
                                    "file": abs_path,
                                    "line": 0,
                                    "message": str(exc),
                                }
                            )

        # ── Build human-readable summary ──────────────────────────────
        all_error_lines: List[str] = []
        for e in ts_errors:
            all_error_lines.append(
                f"  [{e['code']}] {e['file']}:{e['line']}:{e['col']} — {e['message']}"
            )
        for e in py_errors:
            all_error_lines.append(
                f"  [SyntaxError] {e['file']}:{e['line']} — {e['message']}"
            )

        error_summary = "\n".join(all_error_lines) if all_error_lines else "0 compilation errors"
        success = len(ts_errors) == 0 and len(py_errors) == 0

        logger.info(
            f"Compilation check done — success={success}, "
            f"ts_errors={len(ts_errors)}, py_errors={len(py_errors)}"
        )

        return {
            "success": success,
            "project_path": project_path,
            "ts_errors": ts_errors,
            "py_errors": py_errors,
            "error_summary": error_summary,
            "compiler_stderr": compiler_stderr,
            "checks_run": checks_run,
        }

    async def verify_code_compilation_async(
        self, project_path: str, modified_files: List[str] = None
    ) -> Dict[str, Any]:
        """
        Non-blocking async wrapper around verify_code_compilation.
        Runs tsc / py_compile in a worker thread so the main asyncio event loop is never frozen.
        """
        import asyncio
        return await asyncio.to_thread(self.verify_code_compilation, project_path, modified_files)

    def group_compilation_errors_by_file(
        self, compile_result: Dict[str, Any]
    ) -> Dict[str, List[dict]]:
        """
        Groups compiler errors by normalized relative file path.
        Returns: { 'src/App.tsx': [ { 'line': 12, 'code': 'TS2304', 'message': ... }, ... ] }
        """
        grouped: Dict[str, List[dict]] = {}
        project_path = compile_result.get("project_path", "")

        for err in compile_result.get("ts_errors", []):
            fpath = err.get("file", "")
            if project_path and os.path.isabs(fpath):
                try:
                    fpath = os.path.relpath(fpath, project_path)
                except ValueError:
                    pass
            fpath = fpath.replace("\\", "/")
            grouped.setdefault(fpath, []).append(err)

        for err in compile_result.get("py_errors", []):
            fpath = err.get("file", "")
            if project_path and os.path.isabs(fpath):
                try:
                    fpath = os.path.relpath(fpath, project_path)
                except ValueError:
                    pass
            fpath = fpath.replace("\\", "/")
            grouped.setdefault(fpath, []).append(err)

        return grouped

    def build_self_heal_prompt(
        self,
        original_prompt: str,
        file_path: str,
        lang: str,
        compilation_result: Dict[str, Any],
        attempt: int,
        current_file_content: str = "",
    ) -> str:
        """
        Builds a self-healing retry prompt that feeds compiler errors back into
        the LLM so it can surgically fix the broken file on the next attempt.
        """
        ts_errors: List[Dict[str, Any]] = compilation_result.get("ts_errors", [])
        py_errors: List[Dict[str, Any]] = compilation_result.get("py_errors", [])

        # ── Filter errors relevant to this specific file ──────────────
        norm_target = os.path.normpath(file_path).lower()

        def _matches_file(err_file: str) -> bool:
            return os.path.normpath(err_file).lower() == norm_target

        relevant_ts = [e for e in ts_errors if _matches_file(e.get("file", ""))]
        relevant_py = [e for e in py_errors if _matches_file(e.get("file", ""))]

        # Fallback: use all errors if none are tied to this specific file
        if not relevant_ts and not relevant_py:
            relevant_ts = ts_errors
            relevant_py = py_errors

        # ── Format error lines ────────────────────────────────────────
        formatted_errors: List[str] = []
        for e in relevant_ts:
            code_str = e.get("code", "TS_ERROR")
            formatted_errors.append(f"  Line {e.get('line', 0)}: [{code_str}] {e.get('message', '')}")
        for e in relevant_py:
            formatted_errors.append(f"  Line {e.get('line', 0)}: [SyntaxError] {e.get('message', '')}")

        if not formatted_errors:
            formatted_errors.append("  (no specific errors — review full file logic)")

        error_block = "\n".join(formatted_errors)

        content_block = ""
        if current_file_content:
            content_block = f"CURRENT BROKEN FILE CONTENT TO FIX:\n```{lang}\n{current_file_content[:5000]}\n```\n\n"

        prompt = (
            f"COMPILER SELF-HEALING (Attempt {attempt + 1}/3): "
            f"Previous code for '{file_path}' introduced compilation errors.\n\n"
            f"Compiler Errors:\n{error_block}\n\n"
            f"{content_block}"
            f"Fix ALL the errors above. Output the COMPLETE corrected file content "
            f"with the filepath comment as first line:\n"
            f"```{lang}\n"
            f"// filepath: {file_path}\n"
            f"[corrected complete file content]\n"
            f"```\n\n"
            f"Do NOT repeat errors. Fix them surgically. DO NOT use LucideIcon as a value (in lucide-react, import icons as named components, e.g. import {{ User, Mail }} from 'lucide-react')."
        )

        return prompt

    def verify_written_files(self, project_path: str, written_rel_paths: list) -> dict:
        """
        Reads each written file from disk and runs multi-language AST & stub verification.
        Returns {rel_path: [error_strings]} — empty list means file is valid.
        """
        results = {}
        for rel_path in written_rel_paths:
            abs_path = os.path.join(project_path, rel_path) if not os.path.isabs(rel_path) else rel_path
            rel_key = rel_path

            if not os.path.exists(abs_path):
                results[rel_key] = [f"File not found on disk after write: {abs_path}"]
                continue

            try:
                with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
                    code = f.read()

                if rel_path.endswith(".py"):
                    _, errors = self.verify_python_code(code)
                elif rel_path.endswith((".ts", ".tsx", ".js", ".jsx")):
                    _, errors = self.verify_js_ts_code(code)
                else:
                    errors = []

                results[rel_key] = errors
            except Exception as e:
                results[rel_key] = [f"Could not read/verify file: {e}"]

        return results

verification_gate = VerificationGate()
