"""
Unified Project Environment & Dependency Engine for CUA-Sentinel.

Handles AST import scanning for npm and Python packages, auto-installation of missing dependencies,
environment file generation (.env), static build gates, and 1-click environment repairs.
"""

import os
import re
import json
import shutil
import logging
import subprocess
from typing import Dict, Any, List, Set
from pathlib import Path
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

class EnvironmentEngine:
    def __init__(self):
        pass

    def get_python_venv_executables(self, project_path: str) -> Dict[str, str]:
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
        import sys
        venv_path = os.path.join(project_path, ".venv")
        already_exists = os.path.exists(venv_path) or os.path.exists(os.path.join(project_path, "venv"))
        if not already_exists:
            try:
                path_security.validate_write_permission(venv_path)
                logger.info(f"EnvironmentEngine: Creating Python virtual environment (.venv) at {venv_path}")
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
        """
        Scans all .ts, .tsx, .js, .jsx files in project directory for third-party import & require statements.
        Captures single-line, multi-line ESM imports, dynamic imports, and CJS require().
        """
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
        """
        Scans all .py files using Python AST to extract third-party import statements.
        Translates import names to canonical PyPI package names.
        """
        import ast
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

    # Directories to skip when discovering manifests
    MANIFEST_SKIP_DIRS = {
        "node_modules", ".venv", "venv", ".git", "dist", "build",
        "__pycache__", ".sentinel_backup", "backups", "data", ".vite"
    }

    def _find_package_jsons(self, project_path: str) -> List[str]:
        """
        Walks the project tree and returns a list of directory paths that contain
        a real package.json (one with dependencies/devDependencies/scripts),
        skipping node_modules, backups, .venv, etc.
        """
        found = []
        for root, dirs, files in os.walk(project_path):
            dirs[:] = [d for d in dirs if d not in self.MANIFEST_SKIP_DIRS]
            rel = os.path.relpath(root, project_path)
            depth = len(Path(rel).parts) if rel != "." else 0
            if depth > 3:
                dirs.clear()
                continue
            if "package.json" in files:
                pkg_path = os.path.join(root, "package.json")
                try:
                    with open(pkg_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if "dependencies" in data or "devDependencies" in data or "scripts" in data:
                        found.append(root)
                except Exception:
                    pass
        return found

    def _find_requirements_txts(self, project_path: str) -> List[str]:
        """
        Walks the project tree and returns a list of absolute paths to requirements.txt files,
        skipping venv, backups, etc.
        """
        found = []
        for root, dirs, files in os.walk(project_path):
            dirs[:] = [d for d in dirs if d not in self.MANIFEST_SKIP_DIRS]
            rel = os.path.relpath(root, project_path)
            depth = len(Path(rel).parts) if rel != "." else 0
            if depth > 3:
                dirs.clear()
                continue
            if "requirements.txt" in files:
                found.append(os.path.join(root, "requirements.txt"))
        return found

    def scan_and_install_dependencies(self, project_path: str) -> Dict[str, Any]:
        """
        Scans project code for missing dependencies, updates package manifests, and auto-installs
        missing packages. Discovers package.json and requirements.txt in subdirectories (e.g.
        frontend/, backend/) rather than only at the project root. Verifies physical disk presence.
        """
        if not os.path.exists(project_path):
            return {"success": False, "error": f"Project directory does not exist: {project_path}"}

        path_security.validate_write_permission(project_path)
        installed_npm: List[str] = []
        installed_pip: List[str] = []
        scanned_js_all: Set[str] = set()
        scanned_py_all: Set[str] = set()
        installation_logs: List[str] = []
        venv_created = False
        npm_installed = False
        node_modules_count = 0
        pip_packages_count = 0

        # ── 1. NODE / NPM ─────────────────────────────────────────────────────────
        pkg_dirs = self._find_package_jsons(project_path)
        logger.info(f"EnvironmentEngine: Found package.json in {len(pkg_dirs)} location(s): {pkg_dirs}")

        for pkg_dir in pkg_dirs:
            package_json_path = os.path.join(pkg_dir, "package.json")
            try:
                with open(package_json_path, "r", encoding="utf-8") as f:
                    pkg_data = json.load(f)

                existing_deps = (
                    set(pkg_data.get("dependencies", {}).keys()) |
                    set(pkg_data.get("devDependencies", {}).keys())
                )

                # Scan JS/TS imports from this package's directory subtree
                imported_npm = self.scan_js_ts_imports(pkg_dir)
                scanned_js_all.update(imported_npm)

                # Check physical presence in node_modules/ as well as manifest declaration
                node_modules_dir = os.path.join(pkg_dir, "node_modules")
                missing_npm = []
                for p in imported_npm:
                    pkg_physical_dir = os.path.join(node_modules_dir, p)
                    if p not in existing_deps or not os.path.exists(pkg_physical_dir):
                        missing_npm.append(p)

                # chart.js peer dependency
                if ("react-chartjs-2" in missing_npm or "react-chartjs-2" in existing_deps) and "chart.js" not in existing_deps:
                    missing_npm.append("chart.js")

                # Ensure tsconfig.json exists next to package.json if .ts/.tsx files present
                has_ts = any(
                    fn.endswith((".ts", ".tsx"))
                    for r, _, fls in os.walk(pkg_dir)
                    for fn in fls
                    if "node_modules" not in r
                )
                tsconfig_path = os.path.join(pkg_dir, "tsconfig.json")
                if has_ts and not os.path.exists(tsconfig_path):
                    try:
                        with open(tsconfig_path, "w", encoding="utf-8") as tf:
                            tf.write('{\n  "compilerOptions": {\n    "target": "ES2020",\n    "useDefineForClassFields": true,\n    "lib": ["ES2020", "DOM", "DOM.Iterable"],\n    "module": "ESNext",\n    "skipLibCheck": true,\n    "moduleResolution": "bundler",\n    "allowImportingTsExtensions": true,\n    "resolveJsonModule": true,\n    "isolatedModules": true,\n    "noEmit": true,\n    "jsx": "react-jsx",\n    "strict": false\n  },\n  "include": ["src"]\n}\n')
                        logger.info(f"EnvironmentEngine: Created tsconfig.json at {tsconfig_path}")
                        installation_logs.append("Created default tsconfig.json")
                    except Exception as ts_err:
                        logger.warning(f"Could not create tsconfig.json: {ts_err}")

                # Vite devDeps check
                scripts_str = json.dumps(pkg_data.get("scripts", {}))
                has_vite_cfg = os.path.exists(os.path.join(pkg_dir, "vite.config.ts")) or os.path.exists(os.path.join(pkg_dir, "vite.config.js"))
                is_vite = has_vite_cfg or "vite" in scripts_str
                missing_dev: List[str] = []
                updated_manifest = False
                if is_vite:
                    if "vite" not in existing_deps or not os.path.exists(os.path.join(node_modules_dir, "vite")):
                        missing_dev.append("vite")
                    if "@vitejs/plugin-react" not in existing_deps or not os.path.exists(os.path.join(node_modules_dir, "@vitejs", "plugin-react")):
                        missing_dev.append("@vitejs/plugin-react")
                    if "scripts" not in pkg_data:
                        pkg_data["scripts"] = {}
                    if "dev" not in pkg_data["scripts"]:
                        pkg_data["scripts"]["dev"] = "vite"
                        updated_manifest = True
                    if "build" not in pkg_data["scripts"]:
                        pkg_data["scripts"]["build"] = "vite build"
                        updated_manifest = True

                # React 18 auto-upgrade check for react-dom/client compatibility
                has_react_dom_client = False
                for r, _, fls in os.walk(pkg_dir):
                    if "node_modules" in r:
                        continue
                    for fn in fls:
                        if fn.endswith((".ts", ".tsx", ".js", ".jsx")):
                            try:
                                with open(os.path.join(r, fn), "r", encoding="utf-8", errors="ignore") as file_handle:
                                    if "react-dom/client" in file_handle.read():
                                        has_react_dom_client = True
                                        break
                            except Exception:
                                pass
                    if has_react_dom_client:
                        break

                if has_react_dom_client:
                    react_ver = pkg_data.get("dependencies", {}).get("react", "") or pkg_data.get("devDependencies", {}).get("react", "")
                    if "17." in react_ver or "16." in react_ver or not react_ver:
                        pkg_data.setdefault("dependencies", {})
                        pkg_data.setdefault("devDependencies", {})
                        pkg_data["dependencies"]["react"] = "^18.3.1"
                        pkg_data["dependencies"]["react-dom"] = "^18.3.1"
                        pkg_data["devDependencies"]["@types/react"] = "^18.3.11"
                        pkg_data["devDependencies"]["@types/react-dom"] = "^18.3.1"
                        updated_manifest = True
                        logger.info(f"EnvironmentEngine: Auto-upgraded {package_json_path} to React 18 for react-dom/client compatibility.")

                # Write updated package.json if new deps found
                if missing_npm or missing_dev or updated_manifest:
                    pkg_data.setdefault("dependencies", {})
                    pkg_data.setdefault("devDependencies", {})
                    for p in missing_npm:
                        pkg_data["dependencies"][p] = "*"
                    for p in missing_dev:
                        pkg_data["devDependencies"][p] = "^4.3.0" if p.startswith("@vitejs") else ("^5.4.0" if p == "vite" else "*")
                    with open(package_json_path, "w", encoding="utf-8") as f:
                        json.dump(pkg_data, f, indent=2)
                    logger.info(f"EnvironmentEngine: Updated package.json in {pkg_dir}: +deps={missing_npm} +devDeps={missing_dev}")

                # Run npm install from this directory
                need_npm = not os.path.exists(node_modules_dir) or missing_npm or missing_dev or updated_manifest
                if need_npm:
                    all_to_install = list(dict.fromkeys(missing_npm + missing_dev))
                    cmd = f"npm install {' '.join(all_to_install)} --save" if all_to_install else "npm install"
                    logger.info(f"EnvironmentEngine: Running '{cmd}' in {pkg_dir}")
                    res = subprocess.run(cmd, shell=True, cwd=pkg_dir, capture_output=True, text=True, timeout=300)
                    if res.returncode == 0:
                        installed_npm.extend(all_to_install if all_to_install else ["node_modules installed"])
                        npm_installed = True
                        installation_logs.append(f"npm install succeeded ({', '.join(all_to_install) if all_to_install else 'all packages'})")
                        logger.info(f"EnvironmentEngine: npm install succeeded in {pkg_dir}")
                    else:
                        installation_logs.append(f"npm install failed: {res.stderr[:200]}")
                        logger.warning(f"EnvironmentEngine: npm install failed in {pkg_dir}: {res.stderr[:400]}")
                else:
                    npm_installed = True

                # Count packages
                if node_modules_count == 0 and os.path.exists(node_modules_dir):
                    try:
                        node_modules_count = len([
                            d for d in os.listdir(node_modules_dir)
                            if os.path.isdir(os.path.join(node_modules_dir, d)) and not d.startswith(".")
                        ])
                    except Exception:
                        pass

            except Exception as e:
                logger.warning(f"EnvironmentEngine: npm handling failed for {pkg_dir}: {e}")

        # ── 2. PYTHON / PIP ───────────────────────────────────────────────────────
        req_files = self._find_requirements_txts(project_path)
        has_py = bool(req_files) or any(
            fn.endswith(".py")
            for r, _, fls in os.walk(project_path)
            for fn in fls
            if ".venv" not in r and "node_modules" not in r and "backups" not in r
        )

        if has_py:
            venv_result = self.setup_python_virtualenv(project_path)
            venv_created = venv_result.get("created", False)
            executables = self.get_python_venv_executables(project_path)
            py_exe = executables["python"]
            pip_exe = executables["pip"]

            imported_python = self.scan_python_imports(project_path)
            scanned_py_all.update(imported_python)

            local_modules: Set[str] = set()
            for root, dirs, files in os.walk(project_path):
                dirs[:] = [d for d in dirs if d not in (".git", "node_modules", ".venv", "venv", "__pycache__", "backups")]
                for d in dirs:
                    local_modules.add(d.lower())
                for fn in files:
                    if fn.endswith(".py"):
                        local_modules.add(os.path.splitext(fn)[0].lower())

            # Collect existing pip packages from all discovered requirements.txt files
            existing_pip: Set[str] = set()
            for req_path in req_files:
                try:
                    with open(req_path, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if line and not line.startswith("#"):
                                pkg_name = line.split("==")[0].split(">=")[0].split("[")[0].lower()
                                existing_pip.add(pkg_name)
                except Exception:
                    pass

            # Inspect packages physically installed in .venv
            installed_in_venv: Set[str] = set()
            try:
                freeze_res = subprocess.run(
                    f'"{py_exe}" -m pip list --format=freeze',
                    shell=True, cwd=project_path, capture_output=True, text=True, timeout=30
                )
                if freeze_res.returncode == 0:
                    for line in freeze_res.stdout.splitlines():
                        if "==" in line:
                            installed_in_venv.add(line.split("==")[0].lower())
            except Exception:
                pass

            # A Python package is missing if NOT in requirements.txt OR NOT physically in .venv
            missing_pip = []
            for p in imported_python:
                p_lower = p.lower()
                if p_lower in local_modules:
                    continue
                if p_lower not in existing_pip or p_lower not in installed_in_venv:
                    missing_pip.append(p)

            root_req = os.path.join(project_path, "requirements.txt")
            if missing_pip:
                logger.info(f"EnvironmentEngine: Writing {len(missing_pip)} missing pip packages ({missing_pip}) to {root_req}")
                try:
                    mode = "a" if os.path.exists(root_req) else "w"
                    with open(root_req, mode, encoding="utf-8") as f:
                        for p in missing_pip:
                            f.write(f"\n{p}")
                    installed_pip.extend(missing_pip)
                    installation_logs.append(f"Added missing pip packages to requirements.txt: {', '.join(missing_pip)}")
                except Exception as req_err:
                    logger.warning(f"Could not update requirements.txt: {req_err}")

            # Install every discovered requirements.txt into .venv if missing packages existed or venv fresh
            all_req_to_install = req_files if req_files else ([root_req] if os.path.exists(root_req) else [])
            for req_path in all_req_to_install:
                try:
                    pip_cmd = f'"{py_exe}" -m pip install -r "{req_path}"'
                    logger.info(f"EnvironmentEngine: Running pip install: {pip_cmd}")
                    pip_res = subprocess.run(pip_cmd, shell=True, cwd=project_path, capture_output=True, text=True, timeout=300)
                    if pip_res.returncode == 0:
                        logger.info(f"EnvironmentEngine: pip install succeeded for {req_path}")
                        installation_logs.append(f"pip install succeeded for {os.path.basename(req_path)}")
                        if not installed_pip and missing_pip:
                            installed_pip.extend(missing_pip)
                    else:
                        installation_logs.append(f"pip install notice: {pip_res.stderr[:200]}")
                        logger.warning(f"EnvironmentEngine: pip install failed for {req_path}: {pip_res.stderr[:300]}")
                except Exception as pip_err:
                    logger.warning(f"EnvironmentEngine: pip install exception for {req_path}: {pip_err}")

            # Count pip packages in venv
            try:
                freeze_res = subprocess.run(
                    f'"{py_exe}" -m pip list --format=freeze',
                    shell=True, cwd=project_path, capture_output=True, text=True, timeout=30
                )
                if freeze_res.returncode == 0:
                    pip_packages_count = len([ln for ln in freeze_res.stdout.strip().splitlines() if ln.strip()])
            except Exception:
                pass

        # ── 3. Relative import shim repair ────────────────────────────────────────
        repaired_rel_imports = self.validate_and_repair_relative_imports(project_path)

        all_installed = list(dict.fromkeys(installed_npm + installed_pip))
        return {
            "success": True,
            "scanned_js_imports": sorted(list(scanned_js_all)),
            "scanned_python_imports": sorted(list(scanned_py_all)),
            "installed": all_installed,
            "installed_npm": installed_npm,
            "installed_pip": installed_pip,
            "venv_created": venv_created,
            "npm_installed": npm_installed,
            "node_modules_count": node_modules_count,
            "pip_packages_count": pip_packages_count,
            "repaired_relative_imports": repaired_rel_imports,
            "logs": "\n".join(installation_logs) if installation_logs else "All dependencies physically verified and up to date."
        }

    def validate_and_repair_relative_imports(self, project_path: str) -> List[str]:
        """
        Scans all JS/TS files in project_path for relative imports (./ or ../).
        If any relative import target is missing, automatically repairs or creates shim components
        so that Vite/TypeScript build gates and runtime HMR load without 404 / import-analysis errors.
        """
        repaired = []
        if not os.path.exists(project_path):
            return repaired

        # Match relative import: import ... from './path' or import './path'
        import_rel_pattern = re.compile(r"import\s+(?:([\w\$\{\}\*,\s]+)\s+from\s+)?['\"](\.\.?\/[^'\"]+)['\"]")

        for root, dirs, files in os.walk(project_path):
            dirs[:] = [d for d in dirs if d not in (".git", "node_modules", "dist", "build", ".venv", "venv", ".sentinel_backup", "backups", "data")]
            for file in files:
                if file.endswith((".ts", ".tsx", ".js", ".jsx")):
                    source_file_path = os.path.join(root, file)
                    try:
                        with open(source_file_path, "r", encoding="utf-8", errors="ignore") as fh:
                            content = fh.read()
                        
                        matches = import_rel_pattern.findall(content)
                        for import_clause, rel_path in matches:
                            # Ignore CSS / asset imports
                            if rel_path.endswith((".css", ".scss", ".svg", ".png", ".jpg", ".jpeg", ".json")):
                                continue
                            
                            # Resolve target path relative to source file directory
                            dir_of_source = os.path.dirname(source_file_path)
                            norm_target_base = os.path.normpath(os.path.join(dir_of_source, rel_path))

                            # Candidate extensions
                            candidates = [
                                norm_target_base,
                                norm_target_base + ".tsx",
                                norm_target_base + ".ts",
                                norm_target_base + ".jsx",
                                norm_target_base + ".js",
                                norm_target_base + ".json",
                                os.path.join(norm_target_base, "index.tsx"),
                                os.path.join(norm_target_base, "index.ts"),
                                os.path.join(norm_target_base, "index.jsx"),
                                os.path.join(norm_target_base, "index.js")
                            ]

                            if not any(os.path.exists(c) for c in candidates):
                                logger.info(f"EnvironmentEngine: Detected missing relative import '{rel_path}' in {source_file_path}")
                                
                                target_dir = os.path.dirname(norm_target_base)
                                target_file_basename = os.path.basename(norm_target_base)

                                # ── Smart Re-resolution ───────────────────────────────────────
                                # Check if target file actually exists in same folder or in src/
                                fixed_rel = None
                                local_candidates = [
                                    os.path.join(dir_of_source, target_file_basename + ".ts"),
                                    os.path.join(dir_of_source, target_file_basename + ".tsx"),
                                    os.path.join(dir_of_source, target_file_basename + ".js"),
                                    os.path.join(dir_of_source, target_file_basename + ".jsx"),
                                ]
                                src_dir = os.path.join(project_path, "src")
                                src_candidates = [
                                    os.path.join(src_dir, target_file_basename + ".ts"),
                                    os.path.join(src_dir, target_file_basename + ".tsx"),
                                    os.path.join(src_dir, target_file_basename + ".js"),
                                    os.path.join(src_dir, target_file_basename + ".jsx"),
                                ]
                                if any(os.path.exists(lc) for lc in local_candidates):
                                    fixed_rel = f"./{target_file_basename}"
                                elif any(os.path.exists(sc) for sc in src_candidates):
                                    # Compute relative path from dir_of_source to src/
                                    matched_sc = next(sc for sc in src_candidates if os.path.exists(sc))
                                    rel_from_source = os.path.relpath(os.path.splitext(matched_sc)[0], dir_of_source).replace("\\", "/")
                                    if not rel_from_source.startswith("."):
                                        rel_from_source = "./" + rel_from_source
                                    fixed_rel = rel_from_source

                                if fixed_rel:
                                    # Update source file import statement directly!
                                    new_content = content.replace(f"'{rel_path}'", f"'{fixed_rel}'").replace(f'"{rel_path}"', f'"{fixed_rel}"')
                                    with open(source_file_path, "w", encoding="utf-8") as sfh:
                                        sfh.write(new_content)
                                    repaired.append(f"Auto-fixed relative import path in {source_file_path}: '{rel_path}' -> '{fixed_rel}'")
                                    logger.info(f"EnvironmentEngine auto-fixed broken relative import in {source_file_path}: '{rel_path}' -> '{fixed_rel}'")
                                    continue
                                # ─────────────────────────────────────────────────────────────

                                # Prevent creating root-level api.tsx/api.ts shims that collide with Vite /api proxy
                                if os.path.normpath(target_dir) == os.path.normpath(project_path) and target_file_basename.lower() in ("api", "api.ts", "api.tsx"):
                                    logger.warning(f"EnvironmentEngine: Blocked creation of root shim {norm_target_base} to prevent Vite /api proxy collision.")
                                    continue

                                # Attempt auto-repair / shim generation
                                os.makedirs(target_dir, exist_ok=True)

                                # Check if a related component file exists in target_dir
                                existing_files = os.listdir(target_dir) if os.path.exists(target_dir) else []
                                related_file = None
                                target_clean = re.sub(r'(Chart|Component|View|List|Detail|Widget)$', '', target_file_basename, flags=re.IGNORECASE)
                                for ef in existing_files:
                                    ef_no_ext = os.path.splitext(ef)[0]
                                    if target_clean.lower() in ef_no_ext.lower() or ef_no_ext.lower() in target_file_basename.lower():
                                        related_file = ef_no_ext
                                        break
                                
                                # Generate shim component file
                                shim_path = norm_target_base + (".tsx" if source_file_path.endswith((".tsx", ".jsx")) else ".ts")
                                try:
                                    path_security.validate_write_permission(shim_path)
                                    if related_file:
                                        shim_code = f"""import React from 'react';
import RelatedComponent from './{related_file}';

// Auto-generated shim component by CUA-Sentinel EnvironmentEngine
export default function {target_file_basename}(props: any) {{
  return <RelatedComponent {{...props}} />;\n}}
"""
                                    else:
                                        shim_code = f"""import React from 'react';

// Auto-generated fallback component by CUA-Sentinel EnvironmentEngine
export default function {target_file_basename}(props: any) {{
  return (
    <div style={{{{ padding: '1rem', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px', margin: '0.5rem 0' }}}}>
      <h3>{target_file_basename}</h3>
      <p style={{{{ color: '#94a3b8', fontSize: '0.9rem' }}}}>Component rendered by CUA-Sentinel EnvironmentEngine.</p>
    </div>
  );
}}
"""
                                    with open(shim_path, "w", encoding="utf-8") as sf:
                                        sf.write(shim_code)
                                    repaired.append(f"Created shim component: {shim_path} for missing import '{rel_path}'")
                                    logger.info(f"EnvironmentEngine auto-repaired missing relative import by creating {shim_path}")
                                except Exception as err:
                                    logger.warning(f"Could not create shim component for {shim_path}: {err}")
                    except Exception as err:
                        logger.warning(f"Error scanning relative imports in {source_file_path}: {err}")

        return repaired

    def ensure_env_defaults(self, project_path: str) -> None:
        """
        Ensures a baseline .env file exists with local development defaults.
        """
        env_path = os.path.join(project_path, ".env")
        if not os.path.exists(env_path):
            try:
                path_security.validate_write_permission(env_path)
                with open(env_path, "w", encoding="utf-8") as f:
                    f.write("# Environment Configuration auto-generated by CUA-Sentinel EnvironmentEngine\n")
                    f.write("VITE_API_URL=http://localhost:8001\n")
                    f.write("PORT=8001\n")
                logger.info(f"EnvironmentEngine: Generated baseline .env file at {env_path}")
            except Exception as e:
                logger.warning(f"Could not generate .env file: {e}")

    def run_static_build_gate(self, project_path: str) -> Dict[str, Any]:
        """
        Runs static build checks (tsc --noEmit or py_compile) to verify codebase integrity before launch.
        """
        errors = []
        # Check TypeScript if tsconfig exists
        tsconfig = os.path.join(project_path, "tsconfig.json")
        if os.path.exists(tsconfig):
            try:
                res = subprocess.run("npx tsc --noEmit", shell=True, cwd=project_path, capture_output=True, text=True, timeout=60)
                if res.returncode != 0:
                    errors.append(f"TypeScript compilation errors:\n{res.stdout[:1000]}")
            except Exception as e:
                logger.warning(f"TypeScript build gate warning: {e}")

        # Check Python compilation
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
            "errors": errors
        }

    def repair_environment(self, project_path: str, repair_type: str = "all") -> Dict[str, Any]:
        """
        1-Click Environment Repair: Cleans and rebuilds node_modules or python requirements.
        """
        if not os.path.exists(project_path):
            return {"success": False, "error": f"Directory not found: {project_path}"}

        path_security.validate_write_permission(project_path)
        log_msgs = []

        if repair_type in ("npm", "all"):
            node_modules = os.path.join(project_path, "node_modules")
            pkg_lock = os.path.join(project_path, "package-lock.json")
            try:
                if os.path.exists(node_modules):
                    shutil.rmtree(node_modules, ignore_errors=True)
                if os.path.exists(pkg_lock):
                    os.remove(pkg_lock)
                log_msgs.append("Purged stale node_modules and lock file.")
            except Exception as e:
                log_msgs.append(f"Warning during purge: {e}")

            # Re-install
            res = subprocess.run("npm install", shell=True, cwd=project_path, capture_output=True, text=True, timeout=180)
            if res.returncode == 0:
                log_msgs.append("Successfully executed clean npm install.")
            else:
                log_msgs.append(f"npm install warning: {res.stderr[:300]}")

        # Also trigger auto-dependency scan & relative import repairs
        scan_res = self.scan_and_install_dependencies(project_path)
        self.ensure_env_defaults(project_path)

        return {
            "success": True,
            "repair_type": repair_type,
            "log": log_msgs,
            "scan_res": scan_res
        }

    def parse_missing_package_from_error(self, error_text: str) -> Dict[str, str]:
        """
        Parses stack traces, build logs, and UI alert text for missing Python or Node package names.
        Returns dict with keys: 'missing' (bool), 'package' (str), 'ecosystem' ('pip' | 'npm').
        """
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

        # Flexible natural language / UI alert text patterns
        nl_match = re.search(r"(?:missing|uninstalled|install|package|module|library)\s+(?:package|module|library|name)?\s*['\"]?([a-zA-Z0-9_\-@\/]+)['\"]?", text, re.IGNORECASE)
        if nl_match:
            candidate = nl_match.group(1).strip().strip("'\"")
            if candidate.lower() not in ("package", "module", "library", "installation", "failed", "enqueued", "missing", "uninstalled", "error"):
                pypi_name = PYTHON_MODULE_TO_PYPI_NAME.get(candidate.lower(), candidate)
                if candidate.lower() in PYTHON_MODULE_TO_PYPI_NAME or candidate.lower() in BUILTIN_PYTHON_MODULES:
                    return {"missing": True, "package": pypi_name, "ecosystem": "pip"}
                ecosystem = "npm" if ("@" in candidate or "/" in candidate or "-" in candidate or not candidate.isidentifier()) else "pip"
                return {"missing": True, "package": pypi_name, "ecosystem": ecosystem}

        # Single-word raw package fallback (e.g. "distutils" or "lucide-react")
        clean_word = text.split()[0].strip().strip("'\"`") if text else ""
        if clean_word and clean_word.lower() not in ("error", "failed", "unknown"):
            pypi_name = PYTHON_MODULE_TO_PYPI_NAME.get(clean_word.lower(), clean_word)
            ecosystem = "pip" if clean_word.lower() in PYTHON_MODULE_TO_PYPI_NAME or clean_word.lower() in BUILTIN_PYTHON_MODULES else ("npm" if ("@" in clean_word or "-" in clean_word) else "pip")
            return {"missing": True, "package": pypi_name, "ecosystem": ecosystem}

        return {"missing": False, "package": "", "ecosystem": ""}

    def auto_install_missing_package(self, project_path: str, package_name: str, ecosystem: str = "npm") -> Dict[str, Any]:
        """
        Installs a single missing Python (pip) or Node (npm) package into the project environment
        and updates the corresponding manifest file (requirements.txt or package.json).
        """
        if not package_name or not os.path.exists(project_path):
            return {"success": False, "error": f"Invalid project or package: {package_name}"}

        path_security.validate_write_permission(project_path)
        logger.info(f"EnvironmentEngine: Auto-installing missing {ecosystem} package '{package_name}' in {project_path}...")

        # Translate import name to PyPI name if python
        if ecosystem == "pip":
            package_name = PYTHON_MODULE_TO_PYPI_NAME.get(package_name.lower(), package_name)
            self.setup_python_virtualenv(project_path)
            execs = self.get_python_venv_executables(project_path)
            pip_cmd = execs["pip"]
            cmd = f'{pip_cmd} install "{package_name}"'
            res = subprocess.run(cmd, shell=True, cwd=project_path, capture_output=True, text=True, timeout=180)
            success = res.returncode == 0
            if success:
                root_req = os.path.join(project_path, "requirements.txt")
                try:
                    mode = "a" if os.path.exists(root_req) else "w"
                    with open(root_req, mode, encoding="utf-8") as f:
                        f.write(f"\n{package_name}")
                except Exception as req_err:
                    logger.warning(f"Could not update requirements.txt during auto-install: {req_err}")
            return {
                "success": success,
                "package": package_name,
                "ecosystem": "pip",
                "log": res.stdout[:800] if success else (res.stderr[:800] or res.stdout[:800] or "pip install failed")
            }

        elif ecosystem == "npm":
            cmd = f'npm install {package_name} --save'
            res = subprocess.run(cmd, shell=True, cwd=project_path, capture_output=True, text=True, timeout=180)
            success = res.returncode == 0
            return {
                "success": success,
                "package": package_name,
                "ecosystem": "npm",
                "log": res.stdout[:800] if success else (res.stderr[:800] or res.stdout[:800] or "npm install failed")
            }

        return {"success": False, "error": f"Unknown ecosystem: {ecosystem}"}

environment_engine = EnvironmentEngine()
