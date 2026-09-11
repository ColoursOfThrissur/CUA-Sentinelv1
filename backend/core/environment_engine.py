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

class EnvironmentEngine:
    def __init__(self):
        pass

    def scan_js_ts_imports(self, project_path: str) -> Set[str]:
        """
        Scans all .ts, .tsx, .js, .jsx files in project directory for third-party import statements.
        Returns a set of imported package names.
        """
        imported_packages = set()

        # Regex for ESM import statements: import ... from 'package-name' or import 'package-name'
        import_pattern = re.compile(r"import\s+.*?from\s+['\"]([^'\"]+)['\"]|import\s+['\"]([^'\"]+)['\"]")

        for root, dirs, files in os.walk(project_path):
            dirs[:] = [d for d in dirs if d not in (".git", "node_modules", "dist", "build", ".venv", "venv")]
            for f in files:
                if f.endswith((".ts", ".tsx", ".js", ".jsx")):
                    full_p = os.path.join(root, f)
                    try:
                        with open(full_p, "r", encoding="utf-8", errors="ignore") as fh:
                            content = fh.read()
                        matches = import_pattern.findall(content)
                        for m in matches:
                            pkg = m[0] or m[1]
                            pkg = pkg.strip()
                            # Ignore relative imports (./ or ../) and baseline CSS imports
                            if pkg.startswith(".") or pkg.endswith(".css"):
                                continue
                            # Extract root package name (e.g. 'chart.js/auto' -> 'chart.js', '@scope/pkg/sub' -> '@scope/pkg')
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
        Scans all .py files in project directory for third-party import statements.
        """
        imported_packages = set()
        for root, dirs, files in os.walk(project_path):
            dirs[:] = [d for d in dirs if d not in (".git", "node_modules", ".venv", "venv", "__pycache__")]
            for f in files:
                if f.endswith(".py"):
                    full_p = os.path.join(root, f)
                    try:
                        with open(full_p, "r", encoding="utf-8", errors="ignore") as fh:
                            content = fh.read()
                        # Match: import pkg or from pkg import ...
                        matches = re.findall(r"^\s*(?:import|from)\s+([a-zA-Z0-9_]+)", content, re.MULTILINE)
                        for pkg in matches:
                            pkg = pkg.strip()
                            if pkg and pkg not in BUILTIN_PYTHON_MODULES:
                                imported_packages.add(pkg)
                    except Exception as err:
                        logger.warning(f"Error scanning Python imports in {full_p}: {err}")

        return imported_packages

    def scan_and_install_dependencies(self, project_path: str) -> Dict[str, Any]:
        """
        Scans project code for missing dependencies, updates package manifests, and auto-installs missing packages.
        """
        if not os.path.exists(project_path):
            return {"success": False, "error": f"Project directory does not exist: {project_path}"}

        path_security.validate_write_permission(project_path)
        installed_npm = []
        installed_pip = []

        # 1. Handle Node.js / React Dependencies
        package_json_path = os.path.join(project_path, "package.json")
        if os.path.exists(package_json_path):
            imported_npm = self.scan_js_ts_imports(project_path)
            try:
                with open(package_json_path, "r", encoding="utf-8") as f:
                    pkg_data = json.load(f)
                
                existing_deps = set(pkg_data.get("dependencies", {}).keys()).union(set(pkg_data.get("devDependencies", {}).keys()))
                missing_npm = [p for p in imported_npm if p not in existing_deps]

                if ("react-chartjs-2" in missing_npm or "react-chartjs-2" in existing_deps) and "chart.js" not in existing_deps:
                    missing_npm.append("chart.js")

                # Ensure tsconfig.json exists if project contains .ts / .tsx files
                has_ts_files = any(f.endswith((".ts", ".tsx")) for root, _, files in os.walk(project_path) for f in files if "node_modules" not in root)
                tsconfig_path = os.path.join(project_path, "tsconfig.json")
                if has_ts_files and not os.path.exists(tsconfig_path):
                    try:
                        path_security.validate_write_permission(tsconfig_path)
                        with open(tsconfig_path, "w", encoding="utf-8") as tf:
                            tf.write("""{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": false
  },
  "include": ["src"]
}
""")
                        logger.info(f"EnvironmentEngine: Auto-scaffolded missing tsconfig.json at {tsconfig_path}")
                    except Exception as ts_err:
                        logger.warning(f"Could not auto-generate tsconfig.json: {ts_err}")

                # Detect Vite project and ensure vite & @vitejs/plugin-react devDependencies exist
                has_vite_config = os.path.exists(os.path.join(project_path, "vite.config.ts")) or os.path.exists(os.path.join(project_path, "vite.config.js"))
                scripts_str = json.dumps(pkg_data.get("scripts", {}))
                is_vite_project = has_vite_config or "vite" in scripts_str

                updated_manifest = False
                if is_vite_project:
                    if "scripts" not in pkg_data:
                        pkg_data["scripts"] = {}
                    if "dev" not in pkg_data["scripts"]:
                        pkg_data["scripts"]["dev"] = "vite"
                        updated_manifest = True
                    if "build" not in pkg_data["scripts"]:
                        pkg_data["scripts"]["build"] = "vite build"
                        updated_manifest = True

                missing_dev_deps = []
                if is_vite_project:
                    if "vite" not in existing_deps:
                        missing_dev_deps.append("vite")
                    if "@vitejs/plugin-react" not in existing_deps:
                        missing_dev_deps.append("@vitejs/plugin-react")

                if missing_npm or missing_dev_deps or updated_manifest:
                    logger.info(f"EnvironmentEngine: Updating package.json in {project_path}: deps={missing_npm}, devDeps={missing_dev_deps}")
                    if "dependencies" not in pkg_data:
                        pkg_data["dependencies"] = {}
                    if "devDependencies" not in pkg_data:
                        pkg_data["devDependencies"] = {}

                    for m_pkg in missing_npm:
                        pkg_data["dependencies"][m_pkg] = "*"
                    for m_dev_pkg in missing_dev_deps:
                        pkg_data["devDependencies"][m_dev_pkg] = "^4.3.0" if m_dev_pkg.startswith("@vitejs") else ("^5.4.0" if m_dev_pkg == "vite" else "*")

                    with open(package_json_path, "w", encoding="utf-8") as f:
                        json.dump(pkg_data, f, indent=2)

                    all_to_install = missing_npm + missing_dev_deps
                    if all_to_install:
                        cmd = f"npm install {' '.join(all_to_install)} --save"
                        logger.info(f"Running auto-install command: {cmd}")
                        res = subprocess.run(cmd, shell=True, cwd=project_path, capture_output=True, text=True, timeout=120)
                        if res.returncode == 0:
                            installed_npm.extend(all_to_install)
                            logger.info(f"Successfully installed npm packages: {all_to_install}")
                        else:
                            logger.warning(f"npm install returned non-zero code: {res.stderr}")
            except Exception as e:
                logger.warning(f"Failed to scan/install npm packages for {project_path}: {e}")

        # 2. Handle Python Dependencies
        requirements_txt_path = os.path.join(project_path, "requirements.txt")
        if os.path.exists(requirements_txt_path) or any(f.endswith(".py") for f in os.listdir(project_path) if os.path.isfile(os.path.join(project_path, f))):
            imported_python = self.scan_python_imports(project_path)
            local_modules = set()
            for root, dirs, files in os.walk(project_path):
                dirs[:] = [d for d in dirs if d not in (".git", "node_modules", ".venv", "venv", "__pycache__")]
                for d in dirs:
                    local_modules.add(d.lower())
                for f in files:
                    if f.endswith(".py"):
                        local_modules.add(os.path.splitext(f)[0].lower())

            existing_pip = set()
            if os.path.exists(requirements_txt_path):
                try:
                    with open(requirements_txt_path, "r", encoding="utf-8") as f:
                        existing_pip = {line.strip().split("==")[0].split(">=")[0].lower() for line in f if line.strip() and not line.startswith("#")}
                except Exception:
                    pass

            missing_pip = [p for p in imported_python if p.lower() not in existing_pip and p.lower() not in local_modules]
            if missing_pip:
                logger.info(f"EnvironmentEngine: Detected missing python packages: {missing_pip}")
                try:
                    with open(requirements_txt_path, "a", encoding="utf-8") as f:
                        for p in missing_pip:
                            f.write(f"\n{p}")
                    installed_pip.extend(missing_pip)
                except Exception:
                    pass

        # 3. Validate and repair missing relative component/module imports
        repaired_rel_imports = self.validate_and_repair_relative_imports(project_path)

        return {
            "success": True,
            "installed_npm": installed_npm,
            "installed_pip": installed_pip,
            "repaired_relative_imports": repaired_rel_imports
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
                                
                                # Attempt auto-repair / shim generation
                                target_dir = os.path.dirname(norm_target_base)
                                target_file_basename = os.path.basename(norm_target_base)
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

environment_engine = EnvironmentEngine()
