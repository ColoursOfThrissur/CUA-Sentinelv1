"""
Solution Context Engine for CUA-Sentinel.

Parses project repositories to build a Solution Architecture Map & File Responsibility Index.
Helps LLM agents (like Qwen 3.5 9B) understand:
- What every file in the solution does
- Key exported symbols, components, and functions
- Inter-file dependencies and contracts
"""

import os
import ast
import re
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

EXCLUDE_DIRS = {
    "node_modules", ".git", ".venv", "venv", "__pycache__", "dist",
    "build", ".next", ".cache", "coverage", "backups", "snapshots"
}

ALLOWED_EXTS = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".sql", ".css", ".html", ".md"
}

class SolutionContextEngine:
    def analyze_python_file(self, content: str, rel_path: str) -> Dict[str, Any]:
        """Extracts AST docstrings, classes, functions, and imports from Python code."""
        purpose = ""
        exports = []
        imports = []
        try:
            tree = ast.parse(content)
            purpose = ast.get_docstring(tree) or ""
            for node in ast.iter_child_nodes(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    exports.append(f"def {node.name}()")
                elif isinstance(node, ast.ClassDef):
                    exports.append(f"class {node.name}")
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imports.append(node.module)
        except Exception:
            pass

        if not purpose:
            if "router" in rel_path.lower():
                purpose = f"API router module defining HTTP endpoints for {os.path.basename(rel_path)}."
            elif "agent" in rel_path.lower():
                purpose = f"AI agent workflow module for executing {os.path.basename(rel_path)} tasks."
            elif "core" in rel_path.lower() or "engine" in rel_path.lower():
                purpose = f"Core system engine module providing service utilities for {os.path.basename(rel_path)}."
            elif "main" in rel_path.lower() or "server" in rel_path.lower():
                purpose = "Application entrypoint configuring FastAPI server, CORS, and route registration."
            else:
                purpose = f"Python module providing backend logic for {rel_path}."

        return {
            "purpose": purpose.strip().split("\n")[0][:150],
            "exports": exports[:12],
            "imports": list(set(imports))[:10]
        }

    def analyze_js_ts_file(self, content: str, rel_path: str) -> Dict[str, Any]:
        """Extracts exports, components, and imports from JS/TS code using regex."""
        exports = []
        imports = []

        # Find exported functions, classes, components, interfaces
        exp_matches = re.findall(
            r'export\s+(?:default\s+)?(?:function|class|const|let|var|type|interface)\s+([A-Za-z0-9_]+)',
            content
        )
        exports.extend(exp_matches)

        # Find imports
        imp_matches = re.findall(r'from\s+[\'"]([^\'"]+)[\'"]', content)
        imports.extend([imp for imp in imp_matches if not imp.startswith('.')])

        # Infer purpose
        purpose = ""
        top_comment = re.search(r'^\s*/\*\*?([\s\S]*?)\*/', content)
        if top_comment:
            clean_comment = re.sub(r'[\/\*]', '', top_comment.group(1)).strip()
            purpose = clean_comment.split("\n")[0][:150]

        if not purpose:
            base_name = os.path.basename(rel_path)
            if "page" in rel_path.lower() or "view" in rel_path.lower():
                purpose = f"Frontend view/page component for {base_name} UI layout."
            elif "component" in rel_path.lower():
                purpose = f"Reusable UI component: {base_name}."
            elif "api" in rel_path.lower() or "service" in rel_path.lower():
                purpose = f"API client service module for backend HTTP requests."
            elif "main" in rel_path.lower() or "index" in rel_path.lower():
                purpose = "Frontend root entrypoint rendering DOM tree & application providers."
            else:
                purpose = f"JavaScript/TypeScript module implementing {base_name} logic."

        return {
            "purpose": purpose[:150],
            "exports": exports[:12],
            "imports": list(set(imports))[:10]
        }

    def analyze_file(self, full_path: str, rel_path: str) -> Dict[str, Any]:
        """Analyzes a single solution file and returns its responsibility map."""
        ext = os.path.splitext(rel_path)[1].lower()
        size = os.path.getsize(full_path)

        try:
            with open(full_path, "r", encoding="utf-8", errors="ignore") as fh:
                content = fh.read(15000)
        except Exception:
            content = ""

        if ext == ".py":
            analysis = self.analyze_python_file(content, rel_path)
            category = "Backend Python Module"
        elif ext in (".ts", ".tsx", ".js", ".jsx"):
            analysis = self.analyze_js_ts_file(content, rel_path)
            category = "Frontend JS/TS Component" if ext in (".tsx", ".jsx") else "JS/TS Logic Module"
        elif ext == ".json":
            analysis = {
                "purpose": f"JSON configuration file ({os.path.basename(rel_path)})",
                "exports": [],
                "imports": []
            }
            category = "Configuration"
        elif ext == ".sql":
            analysis = {
                "purpose": f"Database SQL schema/migration definition ({os.path.basename(rel_path)})",
                "exports": [],
                "imports": []
            }
            category = "Database Schema"
        elif ext == ".css":
            analysis = {
                "purpose": f"Stylesheets and design tokens for {os.path.basename(rel_path)} UI",
                "exports": [],
                "imports": []
            }
            category = "Styling"
        else:
            analysis = {
                "purpose": f"Document / Asset file ({rel_path})",
                "exports": [],
                "imports": []
            }
            category = "Resource"

        return {
            "rel_path": rel_path.replace("\\", "/"),
            "category": category,
            "size_bytes": size,
            "purpose": analysis["purpose"],
            "exports": analysis["exports"],
            "imports": analysis["imports"]
        }

    def build_solution_map(self, project_path: str) -> Dict[str, Any]:
        """Scans project repository and returns structured Solution Context Map."""
        if not os.path.exists(project_path):
            return {"error": f"Path does not exist: {project_path}"}

        file_maps = []
        category_counts = {}

        for root, dirs, files in os.walk(project_path):
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            for f in files:
                ext = os.path.splitext(f)[1].lower()
                if ext in ALLOWED_EXTS:
                    full_path = os.path.join(root, f)
                    rel_path = os.path.relpath(full_path, project_path)
                    fmap = self.analyze_file(full_path, rel_path)
                    file_maps.append(fmap)
                    cat = fmap["category"]
                    category_counts[cat] = category_counts.get(cat, 0) + 1

        return {
            "project_name": os.path.basename(os.path.abspath(project_path)),
            "project_path": project_path.replace("\\", "/"),
            "total_files": len(file_maps),
            "category_counts": category_counts,
            "files": file_maps
        }

    def generate_solution_context_prompt(self, project_path: str) -> str:
        """Generates a compact, structured Markdown context snippet for LLM prompts."""
        sol_map = self.build_solution_map(project_path)
        if "error" in sol_map:
            return ""

        lines = [
            f"### 🗺️ SOLUTION ARCHITECTURE & FILE RESPONSIBILITY INDEX ({sol_map['project_name']})",
            f"Total Files Scanned: {sol_map['total_files']} | Categories: {', '.join(f'{k}: {v}' for k, v in sol_map['category_counts'].items())}",
            "",
            "| File Path | Category | Purpose & Responsibility | Primary Exports / Symbols |",
            "| --- | --- | --- | --- |"
        ]

        for f in sol_map["files"]:
            exp_str = ", ".join(f["exports"][:4]) if f["exports"] else "—"
            purpose = f["purpose"].replace("|", "/")
            lines.append(f"| `{f['rel_path']}` | {f['category']} | {purpose} | `{exp_str}` |")

        lines.append("")
        lines.append("CRITICAL INSTRUCTION: When modifying or adding code, respect the designated file responsibilities above and maintain exact function/component contracts across dependent files.")
        return "\n".join(lines)


    # -------------------------------------------------------------------------
    # Pillar 5: Exact Symbol & Contract Context Injection
    # -------------------------------------------------------------------------

    def extract_symbol_contracts(self, project_path: str) -> str:
        """
        Builds a compact string for LLM prompt injection that states exactly what
        symbols/exports exist and what packages are installed.

        This prevents the LLM from hallucinating imports or inventing symbols that
        don't exist in the workspace.

        The returned string follows this format::

            ### PROJECT CONTRACT BOUNDARIES
            Installed JS packages: react, react-dom, ...
            Installed Python packages: fastapi, uvicorn, ...

            Exported TypeScript Symbols:
            - src/App.tsx: App, default
            ...

            Exported Python Symbols:
            - backend/main.py: app, create_app
            ...

            CRITICAL: DO NOT import symbols or packages not listed above.

        A local import is used to avoid circular-import issues at module load time.
        """
        # Local import to avoid circular dependencies
        from core.code_diff_engine import code_diff_engine as _cde  # noqa: PLC0415

        # ---- 1. Installed packages -------------------------------------------
        pkg_info = _cde.extract_installed_packages(project_path)
        js_pkgs: List[str] = pkg_info.get("js_packages", [])
        py_pkgs: List[str] = pkg_info.get("py_packages", [])
        venv_pkgs: List[str] = pkg_info.get("venv_packages", [])

        # Merge py_packages + venv_packages for display
        all_py = list(dict.fromkeys(py_pkgs + venv_pkgs))  # deduplicated, order-preserved

        # ---- 2. Walk the project for source files ----------------------------
        WALK_EXCLUDE = {"node_modules", ".venv", "venv", "dist", "build", "__pycache__", ".git", ".next"}
        SOURCE_EXTS = {".ts", ".tsx", ".js", ".jsx", ".py"}

        ts_symbol_map: Dict[str, List[str]] = {}   # rel_path -> [symbol, ...]
        py_symbol_map: Dict[str, List[str]] = {}   # rel_path -> [symbol, ...]

        for root, dirs, files in os.walk(project_path):
            dirs[:] = [d for d in dirs if d not in WALK_EXCLUDE]
            for fname in files:
                ext = os.path.splitext(fname)[1].lower()
                if ext not in SOURCE_EXTS:
                    continue
                full_path = os.path.join(root, fname)
                rel_path = os.path.relpath(full_path, project_path).replace("\\", "/")

                try:
                    with open(full_path, "r", encoding="utf-8", errors="ignore") as fh:
                        content = fh.read(30_000)   # cap to avoid huge files
                except Exception:
                    continue

                if ext in (".ts", ".tsx", ".js", ".jsx"):
                    symbols: List[str] = []

                    # export (default)? (function|class|const|...) Name
                    for m in re.finditer(
                        r'export\s+(default\s+)?(function|class|const|let|var|type|interface|enum)\s+(\w+)',
                        content
                    ):
                        sym = m.group(3)
                        if sym not in symbols:
                            symbols.append(sym)
                        # If there's a 'default' keyword, also record "default"
                        if m.group(1):
                            if "default" not in symbols:
                                symbols.append("default")

                    # export default (anonymous / expression)
                    if re.search(r'\bexport\s+default\b', content) and "default" not in symbols:
                        symbols.append("default")

                    # export { Name1, Name2 as Alias, ... }
                    for m in re.finditer(r'export\s*\{([^}]+)\}', content):
                        for part in m.group(1).split(","):
                            # Handle "X as Y" → take Y (the exported name)
                            parts = part.strip().split()
                            export_name = parts[-1] if parts else ""
                            export_name = export_name.strip()
                            if export_name and re.match(r'^\w+$', export_name) and export_name not in symbols:
                                symbols.append(export_name)

                    if symbols:
                        ts_symbol_map[rel_path] = symbols

                elif ext == ".py":
                    py_syms: List[str] = []
                    try:
                        tree = ast.parse(content)
                        # Collect __all__ if present
                        all_list: List[str] = []
                        for node in ast.iter_child_nodes(tree):
                            if (
                                isinstance(node, ast.Assign)
                                and len(node.targets) == 1
                                and isinstance(node.targets[0], ast.Name)
                                and node.targets[0].id == "__all__"
                                and isinstance(node.value, (ast.List, ast.Tuple))
                            ):
                                for elt in node.value.elts:
                                    if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                        all_list.append(elt.value)

                        if all_list:
                            py_syms = all_list
                        else:
                            # Collect top-level defs, classes, and public assignments
                            for node in ast.iter_child_nodes(tree):
                                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                                    if not node.name.startswith("_"):
                                        py_syms.append(node.name)
                                elif isinstance(node, ast.ClassDef):
                                    if not node.name.startswith("_"):
                                        py_syms.append(node.name)
                                elif isinstance(node, ast.Assign):
                                    for t in node.targets:
                                        if isinstance(t, ast.Name) and not t.id.startswith("_"):
                                            py_syms.append(t.id)
                                elif isinstance(node, (ast.AnnAssign,)):
                                    if (
                                        isinstance(node.target, ast.Name)
                                        and not node.target.id.startswith("_")
                                    ):
                                        py_syms.append(node.target.id)

                    except Exception:
                        pass  # unparseable – skip silently

                    if py_syms:
                        py_symbol_map[rel_path] = list(dict.fromkeys(py_syms))  # deduplicate

        # ---- 3. Format the contract string -----------------------------------
        lines_out: List[str] = [
            "### PROJECT CONTRACT BOUNDARIES",
        ]

        js_line = ", ".join(js_pkgs) if js_pkgs else "(none)"
        lines_out.append(f"Installed JS packages: {js_line}")

        py_line = ", ".join(all_py) if all_py else "(none)"
        lines_out.append(f"Installed Python packages: {py_line}")
        lines_out.append("")

        if ts_symbol_map:
            lines_out.append("Exported TypeScript Symbols:")
            for rel, syms in sorted(ts_symbol_map.items()):
                lines_out.append(f"- {rel}: {', '.join(syms)}")
        else:
            lines_out.append("Exported TypeScript Symbols: (none found)")

        lines_out.append("")

        if py_symbol_map:
            lines_out.append("Exported Python Symbols:")
            for rel, syms in sorted(py_symbol_map.items()):
                lines_out.append(f"- {rel}: {', '.join(syms)}")
        else:
            lines_out.append("Exported Python Symbols: (none found)")

        lines_out.append("")
        lines_out.append(
            "CRITICAL: DO NOT import symbols or packages not listed above. "
            "They do not exist in this workspace."
        )

        return "\n".join(lines_out)


# Singleton instance
solution_context_engine = SolutionContextEngine()
