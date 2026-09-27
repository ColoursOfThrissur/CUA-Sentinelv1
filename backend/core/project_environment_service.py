"""Project Environment Service for CUA-Sentinel.

Handles Python virtualenv discovery and creation, AST import scanning
for Node/TypeScript and Python packages, immutable DependencyChangePlan
generation, environment defaults (.env), and static build verification gates.
"""

from __future__ import annotations

import ast
import json
import logging
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from core.path_security import path_security

logger = logging.getLogger(__name__)

# Standard Built-in Node / React packages that do not require npm install
BUILTIN_NODE_MODULES = {
    "react", "react-dom", "react-dom/client", "react/jsx-runtime",
    "fs", "path", "os", "http", "https", "util", "stream", "crypto", "events", "buffer", "url"
}

# Standard Python Built-in modules that do not require pip install
BUILTIN_PYTHON_MODULES = {
    "os", "sys", "json", "time", "datetime", "math", "random", "re", "typing",
    "asyncio", "logging", "pathlib", "sqlite3", "subprocess", "threading", "collections",
    "uuid", "functools", "itertools", "shutil", "zipfile", "traceback", "inspect", "hashlib"
}

# Mapping of Python import names to actual PyPI package names
PYTHON_MODULE_TO_PYPI_NAME = {
    "pil": "Pillow",
    "cv2": "opencv-python",
    "sklearn": "scikit-learn",
    "yaml": "PyYAML",
    "bs4": "beautifulsoup4",
    "dotenv": "python-dotenv",
    "jose": "python-jose[cryptography]",
    "multipart": "python-multipart",
    "fitz": "PyMuPDF",
    "serial": "pyserial",
    "dateutil": "python-dateutil",
    "win32api": "pywin32",
    "win32con": "pywin32",
    "win32com": "pywin32",
    "websocket": "websocket-client",
    "jwt": "PyJWT",
    "psycopg2": "psycopg2-binary",
    "crypto": "pycryptodome",
    "docx": "python-docx",
    "pptx": "python-pptx",
    "openpyxl": "openpyxl",
    "wx": "wxPython",
    "skimage": "scikit-image",
    "pg": "psycopg2-binary",
    "mysql": "mysql-connector-python",
    "distutils": "setuptools"
}

MANIFEST_SKIP_DIRS = {
    "node_modules", ".venv", "venv", ".git", "dist", "build",
    "__pycache__", ".sentinel_backup", "backups", "data", ".vite"
}


class ProjectEnvironmentService:
    """Service providing environment inspection, dependency planning, and build verification."""

    def get_python_venv_executables(self, project_path: str) -> Dict[str, str]:
        """Resolves active python and pip executables for project (.venv or system fallback)."""
        import sys
        venv_dirs = [".venv", "venv"]
        for v_dir in venv_dirs:
            v_path = os.path.join(project_path, v_dir)
            if os.path.exists(v_path):
                if os.name == "nt":
                    py_exe = os.path.join(v_path, "Scripts", "python.exe")
                    pip_exe = os.path.join(v_path, "Scripts", "pip.exe")
                else:
                    py_exe = os.path.join(v_path, "bin", "python")
                    pip_exe = os.path.join(v_path, "bin", "pip")
                if os.path.exists(py_exe):
                    return {"python": py_exe, "pip": pip_exe if os.path.exists(pip_exe) else f'"{py_exe}" -m pip'}
        return {"python": sys.executable, "pip": f'"{sys.executable}" -m pip'}

    def setup_python_virtualenv(self, project_path: str) -> dict:
        """Sets up a virtual environment in project_path/.venv if not already present."""
        import sys
        venv_path = os.path.join(project_path, ".venv")
        already_exists = os.path.exists(venv_path) or os.path.exists(os.path.join(project_path, "venv"))
        if not already_exists:
            try:
                path_security.validate_write_permission(venv_path)
                logger.info(f"ProjectEnvironmentService: Creating .venv at {venv_path}")
                res = subprocess.run([sys.executable, "-m", "venv", ".venv"], cwd=project_path, capture_output=True, text=True, timeout=60)
                if res.returncode == 0:
                    logger.info(f"Successfully created .venv at {venv_path}")
                    return {"venv_path": venv_path, "created": True}
                else:
                    logger.warning(f"Failed to create .venv: {res.stderr}")
                    return {"venv_path": venv_path, "created": False, "error": res.stderr[:200]}
            except Exception as err:
                logger.warning(f"Could not create Python virtual environment: {err}")
                return {"venv_path": venv_path, "created": False, "error": str(err)}
        return {"venv_path": venv_path, "created": False, "already_existed": True}

    def scan_js_ts_imports(self, project_path: str) -> Set[str]:
        """Scans .ts, .tsx, .js, .jsx files in project for third-party npm package imports."""
        imported_packages = set()
        import_pattern = re.compile(r"(?:from|import|require)\s*\(?\s*['\"]([^'\"]+)['\"]")

        for root, dirs, files in os.walk(project_path):
            dirs[:] = [d for d in dirs if d not in (".git", "node_modules", "dist", "build", ".venv", "venv", "__pycache__")]
            for f in files:
                if f.endswith((".ts", ".tsx", ".js", ".jsx")):
                    full_p = os.path.join(root, f)
                    try:
                        with open(full_p, "r", encoding="utf-8", errors="ignore") as fh:
                            content = fh.read()
                        matches = import_pattern.findall(content)
                        for pkg in matches:
                            pkg = pkg.strip()
                            if pkg.startswith(".") or pkg.startswith("@src") or pkg.endswith(".css") or pkg.endswith(".scss"):
                                continue
                            parts = pkg.split("/")
                            if pkg.startswith("@") and len(parts) >= 2:
                                root_pkg = f"{parts[0]}/{parts[1]}"
                            else:
                                root_pkg = parts[0]
                            
                            if root_pkg and root_pkg not in BUILTIN_NODE_MODULES:
                                imported_packages.add(root_pkg)
                    except Exception as err:
                        logger.warning(f"Error scanning imports in {full_p}: {err}")

        return imported_packages

    def scan_python_imports(self, project_path: str) -> Set[str]:
        """Scans Python files using AST to extract third-party import statements."""
        imported_packages = set()
        for root, dirs, files in os.walk(project_path):
            dirs[:] = [d for d in dirs if d not in (".git", "node_modules", ".venv", "venv", "__pycache__", "backups")]
            for f in files:
                if f.endswith(".py"):
                    full_p = os.path.join(root, f)
                    try:
                        with open(full_p, "r", encoding="utf-8", errors="ignore") as fh:
                            content = fh.read()
                        tree = ast.parse(content)
                        for node in ast.walk(tree):
                            if isinstance(node, ast.Import):
                                for alias in node.names:
                                    mod_name = alias.name.split(".")[0]
                                    if mod_name:
                                        pypi_name = PYTHON_MODULE_TO_PYPI_NAME.get(mod_name.lower(), mod_name)
                                        if pypi_name.lower() not in BUILTIN_PYTHON_MODULES:
                                            imported_packages.add(pypi_name)
                            elif isinstance(node, ast.ImportFrom):
                                if node.module:
                                    mod_name = node.module.split(".")[0]
                                    if mod_name:
                                        pypi_name = PYTHON_MODULE_TO_PYPI_NAME.get(mod_name.lower(), mod_name)
                                        if pypi_name.lower() not in BUILTIN_PYTHON_MODULES:
                                            imported_packages.add(pypi_name)
                    except Exception as err:
                        logger.warning(f"Error scanning Python AST imports in {full_p}: {err}")

        return imported_packages

    def _find_package_jsons(self, project_path: str) -> List[str]:
        """Finds all directories containing package.json excluding build and virtualenv artifacts."""
        package_dirs: List[str] = []
        for root, dirs, files in os.walk(project_path):
            dirs[:] = [d for d in dirs if d not in MANIFEST_SKIP_DIRS]
            if "package.json" in files:
                package_dirs.append(root)
        return package_dirs

    def _find_requirements_txts(self, project_path: str) -> List[str]:
        """Finds all requirements.txt files excluding build and virtualenv artifacts."""
        req_files: List[str] = []
        for root, dirs, files in os.walk(project_path):
            dirs[:] = [d for d in dirs if d not in MANIFEST_SKIP_DIRS]
            if "requirements.txt" in files:
                req_files.append(os.path.join(root, "requirements.txt"))
        return req_files

    def scan_missing_dependencies(self, project_path: str) -> List[Any]:
        """
        Scans project code for missing npm and Python dependencies.
        Produces reviewable DependencyChangePlan objects without executing subprocesses.
        """
        from core.dependency_plans import dependency_plan_builder
        plans = []
        if not os.path.exists(project_path):
            return plans

        # 1. Discover missing npm packages
        pkg_dirs = self._find_package_jsons(project_path)
        for pkg_dir in pkg_dirs:
            package_json_path = os.path.join(pkg_dir, "package.json")
            try:
                with open(package_json_path, "r", encoding="utf-8") as f:
                    pkg_data = json.load(f)
                existing_deps = (
                    set(pkg_data.get("dependencies", {}).keys()) |
                    set(pkg_data.get("devDependencies", {}).keys())
                )
                imported_npm = self.scan_js_ts_imports(pkg_dir)
                node_modules_dir = os.path.join(pkg_dir, "node_modules")
                missing_npm = [
                    p for p in imported_npm
                    if p not in existing_deps or not os.path.exists(os.path.join(node_modules_dir, p))
                ]
                for pkg_name in missing_npm:
                    try:
                        plan = dependency_plan_builder.create_plan(
                            project_path=project_path,
                            ecosystem="npm",
                            package_name=pkg_name,
                            requested_spec=pkg_name,
                            reason=f"Detected import of '{pkg_name}' missing from {package_json_path}",
                            manifest_path=package_json_path,
                            evidence=[{"source": "scan_js_ts_imports", "manifest": package_json_path}],
                        )
                        plans.append(plan)
                    except Exception as plan_err:
                        logger.warning(f"Could not build dependency plan for npm pkg '{pkg_name}': {plan_err}")
            except Exception as e:
                logger.warning(f"Error scanning package.json at {package_json_path}: {e}")

        # 2. Discover missing Python packages
        req_files = self._find_requirements_txts(project_path)
        imported_py = self.scan_python_imports(project_path)
        for req_path in req_files:
            try:
                with open(req_path, "r", encoding="utf-8") as f:
                    existing_lines = f.read().splitlines()
                existing_pip = set()
                for line in existing_lines:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        pkg = re.split(r"[=><~!]", line)[0].strip()
                        if pkg:
                            existing_pip.add(pkg.lower())

                missing_pip = [p for p in imported_py if p.lower() not in existing_pip]
                for pkg_name in missing_pip:
                    try:
                        plan = dependency_plan_builder.create_plan(
                            project_path=project_path,
                            ecosystem="pip",
                            package_name=pkg_name,
                            requested_spec=pkg_name,
                            reason=f"Detected Python AST import of '{pkg_name}' missing from {req_path}",
                            manifest_path=req_path,
                            evidence=[{"source": "scan_python_imports", "manifest": req_path}],
                        )
                        plans.append(plan)
                    except Exception as plan_err:
                        logger.warning(f"Could not build dependency plan for pip pkg '{pkg_name}': {plan_err}")
            except Exception as e:
                logger.warning(f"Error scanning requirements.txt at {req_path}: {e}")

        return plans

    def ensure_env_defaults(self, project_path: str) -> None:
        """Ensures a baseline .env file exists with local development defaults."""
        env_path = os.path.join(project_path, ".env")
        if not os.path.exists(env_path):
            try:
                path_security.validate_write_permission(env_path)
                with open(env_path, "w", encoding="utf-8") as f:
                    f.write("# Environment Configuration auto-generated by CUA-Sentinel\n")
                    f.write("VITE_API_URL=http://localhost:8001\n")
                    f.write("PORT=8001\n")
                logger.info(f"ProjectEnvironmentService: Generated baseline .env file at {env_path}")
            except Exception as e:
                logger.warning(f"Could not generate .env file: {e}")

    def run_static_build_gate(self, project_path: str) -> Dict[str, Any]:
        """Runs static build checks (tsc --noEmit or py_compile) to verify codebase integrity."""
        errors = []
        tsconfig = os.path.join(project_path, "tsconfig.json")
        if os.path.exists(tsconfig):
            try:
                res = subprocess.run("npx tsc --noEmit", shell=True, cwd=project_path, capture_output=True, text=True, timeout=60)
                if res.returncode != 0:
                    errors.append(f"TypeScript compilation errors:\n{res.stdout[:1000]}")
            except Exception as e:
                logger.warning(f"TypeScript build gate warning: {e}")

        for root, dirs, files in os.walk(project_path):
            dirs[:] = [d for d in dirs if d not in (".git", "node_modules", ".venv", "venv")]
            for f in files:
                if f.endswith(".py"):
                    full_p = os.path.join(root, f)
                    try:
                        import py_compile
                        py_compile.compile(full_p, doraise=True)
                    except Exception as py_err:
                        errors.append(f"Python syntax error in {f}: {py_err}")

        return {
            "success": len(errors) == 0,
            "errors": errors,
        }

    def parse_missing_package_from_error(self, error_text: str) -> Dict[str, str]:
        """Parses stack traces, build logs, and UI alert text for missing Python or Node package names."""
        if not error_text:
            return {"missing": False, "package": "", "ecosystem": ""}

        text = error_text.strip()

        # Python: ModuleNotFoundError: No module named 'xyz'
        py_match = re.search(r"ModuleNotFoundError:\s*No module named ['\"]?([a-zA-Z0-9_\-\.]+)", text, re.IGNORECASE)
        if py_match:
            mod_name = py_match.group(1).split(".")[0]
            pypi_name = PYTHON_MODULE_TO_PYPI_NAME.get(mod_name.lower(), mod_name)
            return {"missing": True, "package": pypi_name, "ecosystem": "pip"}

        # Python: ImportError: cannot import name ... from 'xyz' / No module named 'xyz'
        py_imp_match = re.search(r"ImportError:.*(?:from|named)\s+['\"]?([a-zA-Z0-9_\-\.]+)", text, re.IGNORECASE)
        if py_imp_match:
            mod_name = py_imp_match.group(1).split(".")[0]
            pypi_name = PYTHON_MODULE_TO_PYPI_NAME.get(mod_name.lower(), mod_name)
            return {"missing": True, "package": pypi_name, "ecosystem": "pip"}

        # Node/Vite: Failed to resolve import "xyz" from "..."
        npm_match = re.search(r"Failed to resolve import [\"']([^\"']+)[\"']", text, re.IGNORECASE)
        if npm_match:
            pkg_name = npm_match.group(1)
            if not pkg_name.startswith((".", "/", "@src")):
                parts = pkg_name.split("/")
                base_pkg = "/".join(parts[:2]) if pkg_name.startswith("@") and len(parts) >= 2 else parts[0]
                return {"missing": True, "package": base_pkg, "ecosystem": "npm"}

        # Node: Cannot find module 'xyz'
        npm_mod_match = re.search(r"Cannot find module [\"']([^\"']+)[\"']", text, re.IGNORECASE)
        if npm_mod_match:
            pkg_name = npm_mod_match.group(1)
            if not pkg_name.startswith((".", "/")):
                base_pkg = "/".join(pkg_name.split("/")[:2]) if pkg_name.startswith("@") else pkg_name.split("/")[0]
                return {"missing": True, "package": base_pkg, "ecosystem": "npm"}

        return {"missing": False, "package": "", "ecosystem": ""}


project_environment_service = ProjectEnvironmentService()
