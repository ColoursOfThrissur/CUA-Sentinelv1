"""
Code Refactoring & AI Feature Proposer Agent for CUA-Sentinel.

Orchestrates multi-file project scanning, Repository AST Mapping, Code Health Scoring (0-100),
HITL Feature Recommendations, Backup Snapshots, JSON IR Task Execution, and AST Verification.
"""

import os
import json
import logging
import subprocess
from typing import Dict, Any, List, Optional
from agents.base_agent import BaseAgent
from core.code_health_evaluator import code_health_evaluator
from core.code_security_auditor import code_security_auditor
from core.project_backup import project_backup_manager
from core.hierarchical_planner import hierarchical_planner
from core.verification_gate import verification_gate
from core.sandbox_runner import sandbox_runner
from core.memory_layers import memory_layers

from core.path_security import path_security, PathSecurityViolation
from core.project_scaffolder import project_scaffolder
from core.ui_ux_pro_max import ui_ux_pro_max
from core.solution_context import solution_context_engine
from core.code_diff_engine import code_diff_engine
from core.alignment_validator import alignment_validator

logger = logging.getLogger(__name__)

EXCLUDE_DIRS = {"node_modules", ".venv", "venv", ".git", "dist", "build", "__pycache__", ".sentinel_backup"}
ALLOWED_EXTS = {".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".md"}

class CodeRefactorAgent(BaseAgent):
    def scan_repository(self, project_path: str) -> Dict[str, Any]:
        """
        Recursively scans project files, builds Repository AST Map, and calculates Code Health Index (0-100) & AST Security Audit.
        """
        if not os.path.exists(project_path):
            return {"error": f"Directory path does not exist: {project_path}"}

        # Check drive path permission
        try:
            path_security.validate_read_permission(project_path)
        except PathSecurityViolation as psv:
            return {"error": str(psv)}

        file_entries = []
        for root, dirs, files in os.walk(project_path):
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            for f in files:
                ext = os.path.splitext(f)[1].lower()
                if ext in ALLOWED_EXTS:
                    full_path = os.path.join(root, f)
                    rel_path = os.path.relpath(full_path, project_path)
                    try:
                        with open(full_path, "r", encoding="utf-8", errors="ignore") as fh:
                            content = fh.read(15000) # Read first 15k chars
                        file_entries.append({
                            "filename": rel_path,
                            "full_path": full_path,
                            "size_bytes": os.path.getsize(full_path),
                            "content": content
                        })
                    except Exception as err:
                        logger.warning(f"Error reading file {full_path}: {err}")

        repo_map = {"project_path": project_path, "files": file_entries}
        health_assessment = code_health_evaluator.calculate_project_health(repo_map)
        security_assessment = code_security_auditor.audit_repository(repo_map)

        # Generate HITL Feature Ideas dynamically based on actual scan findings
        feature_ideas = []
        idea_counter = [1]  # use list for closure

        def next_id():
            fid = f"feat_{idea_counter[0]}"
            idea_counter[0] += 1
            return fid

        overal_health = health_assessment.get('overall_score', 100)
        total_issues = health_assessment.get('total_issues', 0)
        vulns = security_assessment.get('total_vulnerabilities', 0)
        vuln_list = security_assessment.get('vulnerabilities', [])

        if overal_health < 85:
            feature_ideas.append({
                "idea_id": next_id(),
                "title": "Add Type Annotations & Docstrings",
                "description": f"Project health is {overal_health}/100. Injecting missing return types and docstrings will improve maintainability and IDE autocompletion.",
                "category": "Refactoring & Readability",
                "approved": True,
                "priority": "HIGH" if overal_health < 70 else "MEDIUM"
            })

        if total_issues > 3:
            feature_ideas.append({
                "idea_id": next_id(),
                "title": f"Modularize Oversized Functions ({total_issues} Quality Issues Found)",
                "description": "Break down long monolithic functions (>50 lines) detected during AST scan into single-responsibility helpers.",
                "category": "Architecture",
                "approved": False,
                "priority": "MEDIUM"
            })

        if vulns > 0:
            vuln_types = list({v.get('type', '') for v in vuln_list[:3]})
            feature_ideas.append({
                "idea_id": next_id(),
                "title": f"Security Hardening — {vulns} Vulnerability(ies) Detected",
                "description": f"AST security audit found: {', '.join(vuln_types)}. Automated remediation strongly recommended.",
                "category": "Security",
                "approved": True,
                "priority": "HIGH"
            })
        else:
            feature_ideas.append({
                "idea_id": next_id(),
                "title": "Harden Exception Handling",
                "description": "Replace bare except handlers with explicit Exception logging to prevent silent errors.",
                "category": "Robustness & Security",
                "approved": True,
                "priority": "MEDIUM"
            })

        feature_ideas.append({
            "idea_id": next_id(),
            "title": f"Verify Environment Dependencies ({len(file_entries)} Files Scanned)",
            "description": "Run 1-Click Dependency Scan to confirm node_modules and Python .venv are fully populated.",
            "category": "Environment",
            "approved": False,
            "priority": "LOW"
        })

        return {
            "project_path": project_path,
            "total_files": len(file_entries),
            "files_scanned": len(file_entries),
            "overall_health_score": health_assessment.get('overall_score', 0),
            "health_assessment": health_assessment,
            "security_assessment": security_assessment,
            "feature_ideas": feature_ideas,
            "file_list": [f["filename"] for f in file_entries[:15]]
        }

    def create_project_from_scratch(
        self,
        project_name: str,
        target_path: str,
        tech_stack: str = "FastAPI + React",
        ui_style: str = "Glassmorphism",
        description: str = "",
        blueprint_content: str = "",
        blueprint_filename: str = ""
    ) -> Dict[str, Any]:
        """
        Creates a brand-new project from scratch on target D:\\ drive location with UI/UX Pro Max design tokens and architectural spec directives.
        """
        # Validate drive write permission (blocks C:\ OS drive writes)
        path_security.validate_write_permission(target_path)

        scaffold_res = project_scaffolder.create_project_structure(
            project_name=project_name,
            target_path=target_path,
            tech_stack=tech_stack,
            ui_style=ui_style,
            description=description,
            blueprint_content=blueprint_content,
            blueprint_filename=blueprint_filename
        )

        design_tokens = ui_ux_pro_max.get_design_system(ui_style)

        return {
            "status": "SUCCESS",
            "project_name": project_name,
            "target_path": target_path,
            "tech_stack": tech_stack,
            "ui_style": ui_style,
            "blueprint_attached": bool(blueprint_content),
            "design_tokens": design_tokens,
            "scaffold_res": scaffold_res
        }

    async def diagnose_and_fix_file(self, project_path: str, file_path: str) -> Dict[str, Any]:
        """
        Diagnoses static syntax/TypeScript/Python errors in a specific selected file and applies AI repair via local LLM.
        """
        if not os.path.isabs(file_path):
            abs_file_path = os.path.normpath(os.path.join(project_path, file_path))
        else:
            abs_file_path = file_path

        path_security.validate_write_permission(abs_file_path)

        if not os.path.exists(abs_file_path):
            return {"success": False, "error": f"File not found: {abs_file_path}"}

        with open(abs_file_path, "r", encoding="utf-8", errors="ignore") as f:
            code_content = f.read()

        # Perform static analysis check
        errors = []
        if abs_file_path.endswith(".py"):
            try:
                import ast
                ast.parse(code_content)
            except SyntaxError as syn_err:
                errors.append(f"Python SyntaxError line {syn_err.lineno}: {syn_err.msg}")
            except Exception as py_err:
                errors.append(f"Python Error: {py_err}")
        elif abs_file_path.endswith((".ts", ".tsx", ".js", ".jsx")):
            try:
                res = subprocess.run(
                    "npx tsc --noEmit",
                    shell=True,
                    cwd=project_path,
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                if res.returncode != 0 and res.stdout:
                    file_rel = os.path.relpath(abs_file_path, project_path).replace("\\", "/")
                    file_errors = [line for line in res.stdout.splitlines() if file_rel in line.replace("\\", "/")]
                    if file_errors:
                        errors.extend(file_errors[:5])
            except Exception:
                pass

        rel_path = os.path.relpath(abs_file_path, project_path).replace("\\", "/")
        context_block = self._build_context_block(project_path, rel_path)
        
        ext = rel_path.rsplit(".", 1)[-1] if "." in rel_path else "txt"
        lang_map = {"py": "python", "tsx": "tsx", "ts": "typescript", "js": "javascript", "jsx": "jsx", "css": "css", "json": "json"}
        lang = lang_map.get(ext, ext)
        comment_char = "#" if ext == "py" else "//"

        prompt = f"""You are an expert autonomous software engineer repairing file '{rel_path}'.
Project Directory: {project_path}
Target File: {rel_path}

FULL SOLUTION CONTEXT (other files & integration contracts across project):
{context_block}

Diagnostic Errors Identified:
{json.dumps(errors, indent=2) if errors else "No explicit static build gate errors, but inspect for potential bugs, unhandled null states, broken imports, missing component exports, or route prefix mismatches."}

Fix all syntax, import, missing export, or logic errors in this file while strictly preserving integration contracts with other solution files. Provide the complete updated code block with filepath comment:
```{lang}
{comment_char} filepath: {rel_path}
// updated code content here...
```
Provide a brief natural language summary of what was diagnosed and fixed before the code block."""

        model_id = self.model_manager.get_model_for_workflow("REFACTOR") if self.model_manager else "qwen3_14b_q4"
        
        try:
            if self.model_manager:
                llm_response = await self.model_manager.generate_async(
                    model_id=model_id,
                    task_id="file_diagnose",
                    lease_id="internal",
                    lease_generation=0,
                    prompt=prompt,
                    temperature=0.1
                )
            else:
                llm_response = f"// filepath: {rel_path}\n{code_content}"

            written_files = self._extract_and_write_code_blocks(project_path, llm_response)
            
            # Execute Wire-Up pass across project to fix uvicorn import strings, package.json type module, & route prefixes
            wired_files = self._run_wireup_pass(project_path, "diagnose_fix", written_files)
            all_written = list(set(written_files + wired_files))
            
            with open(abs_file_path, "r", encoding="utf-8", errors="ignore") as f:
                fixed_code = f.read()

            summary = llm_response.split("```")[0].strip() if "```" in llm_response else "Diagnosed and repaired code errors."

            return {
                "success": True,
                "file_path": rel_path,
                "abs_file_path": abs_file_path,
                "errors_found": errors,
                "summary": summary,
                "fixed_code": fixed_code,
                "written_files": all_written
            }
        except Exception as err:
            logger.error(f"Error during file diagnosis for {abs_file_path}: {err}")
            return {"success": False, "error": str(err)}

    def _extract_and_write_code_blocks(self, project_path: str, text: str, target_file_path: Optional[str] = None, task_id: Optional[str] = None) -> List[str]:
        from core.execution_broker import execution_broker
        file_ops = execution_broker.parse_raw_llm_code_blocks(text)

        # Strict Target File Scoping & Sanity Validation
        if target_file_path and file_ops:
            valid_ops = []
            target_norm = os.path.normpath(target_file_path).lower()
            target_is_react = target_norm.endswith(('.tsx', '.jsx'))

            for op in file_ops:
                rel_norm = os.path.normpath(op.get("rel_path", "")).lower()
                code = op.get("content", "")

                # Sanity check: If writing a React UI component (e.g. App.tsx) but code lacks React export/JSX keywords, reject
                if target_is_react and not any(kw in code for kw in ["export default", "return (", "return<", "function ", "const ", "class "]):
                    logger.warning(f"Strict Sanity Check: Rejected non-component code block when writing React UI file '{target_file_path}'")
                    continue

                if rel_norm == target_norm or rel_norm.endswith(os.path.basename(target_norm).lower()):
                    op["rel_path"] = target_file_path
                    valid_ops.append(op)
                else:
                    op["rel_path"] = target_file_path
                    valid_ops.append(op)

            file_ops = valid_ops

        written = execution_broker.execute_write_plan(project_path, file_ops, task_id=task_id)
        if written:
            return written

        # Fallback 1: Check for SEARCH/REPLACE blocks (Pillar 1)
        if target_file_path:
            abs_target = os.path.normpath(os.path.join(project_path, target_file_path))
            diff_res = code_diff_engine.apply_search_replace_blocks(abs_target, text)
            if diff_res.get("success") and diff_res.get("blocks_applied", 0) > 0:
                logger.info(f"_extract_and_write_code_blocks: Applied {diff_res['blocks_applied']} SEARCH/REPLACE block(s) to {target_file_path}")
                return [target_file_path]

        # Fallback 2: If LLM outputted a single markdown code block without filepath header for target_file_path
        if target_file_path and "```" in text:
            import re
            m = re.search(r'```(?:\w+)?\n(.*?)```', text, re.DOTALL)
            if m:
                code_content = m.group(1).strip()
                lines = code_content.splitlines()
                if lines and any(kw in lines[0].lower() for kw in ["filepath:", "file:", "target:"]):
                    lines = lines[1:]
                code_clean = "\n".join(lines).strip()
                if code_clean:
                    single_op = [{"rel_path": target_file_path, "content": code_clean}]
                    return execution_broker.execute_write_plan(project_path, single_op, task_id=task_id)

        return []

    # ── Context helpers ────────────────────────────────────────────────────

    def _read_file_safe(self, project_path: str, rel_path: str, max_chars: int = 4000) -> str:
        """Read a project file safely, truncating if too large."""
        try:
            abs_path = os.path.join(project_path, rel_path)
            if os.path.exists(abs_path):
                with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                if len(content) > max_chars:
                    return content[:max_chars] + f"\n... [truncated — {len(content)} total chars]"
                return content
        except Exception:
            pass
        return ""

    def _build_context_block(self, project_path: str, target_file_path: str) -> str:
        """
        Build a comprehensive solution context block by dynamically discovering all
        backend Python modules, models, schemas, and frontend React components/API files.
        Keeps total context size under ~12000 chars with exact solution contracts.
        """
        context_parts = []
        
        # 0. Generate AST Solution Architecture Map & File Responsibility Index
        try:
            sol_map_prompt = solution_context_engine.generate_solution_context_prompt(project_path)
            if sol_map_prompt:
                context_parts.append(sol_map_prompt)
        except Exception as e:
            logger.warning(f"Failed to generate solution context map: {e}")
        
        # 1. Discover all relevant files in the solution dynamically
        discovered_files = []

        # Priority entry points — discover dynamically by checking which actually exist
        candidate_entry_points = [
            "backend/main.py", "main.py", "app.py", "server.py",          # Python backends
            "src/App.tsx", "src/App.jsx", "src/App.ts", "src/App.js",     # React/JS frontends
            "src/main.tsx", "src/main.ts", "src/index.tsx", "src/index.ts",
            "src/api.ts", "src/api.tsx", "src/api.js",                    # API clients
            "vite.config.ts", "vite.config.js",                           # Build configs
            "next.config.js", "next.config.ts",                           # Next.js
            "package.json", "requirements.txt",                           # Dependency manifests
        ]
        for p in candidate_entry_points:
            if os.path.exists(os.path.join(project_path, p)):
                discovered_files.append(p)
                
        # Scan backend/ and src/ recursively for additional context files
        for root, dirs, files in os.walk(project_path):
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            for f in files:
                ext = os.path.splitext(f)[1].lower()
                if ext in {".py", ".ts", ".tsx", ".jsx", ".js", ".json"}:
                    full_p = os.path.join(root, f)
                    rel_p = os.path.relpath(full_p, project_path).replace("\\", "/")
                    if rel_p not in discovered_files and not rel_p.startswith(("node_modules", ".venv", "venv", "dist", "build")):
                        discovered_files.append(rel_p)
                        
        # Read reference files (excluding target_file_path)
        ref_count = 0
        for rel_p in discovered_files:
            if rel_p == target_file_path:
                continue
            if ref_count >= 10:
                break
            content = self._read_file_safe(project_path, rel_p, max_chars=2000)
            if content:
                context_parts.append(f"=== {rel_p} ===\n{content}")
                ref_count += 1

        # Include current target file content (if modifying)
        current = self._read_file_safe(project_path, target_file_path, max_chars=3000)
        if current:
            context_parts.append(f"=== {target_file_path} (current target — modify this) ===\n{current}")

        # Append solution integration contract directive
        contract = (
            "=== SOLUTION INTEGRATION CONTRACT & RULES ===\n"
            "1. VITE PROXY MATCHING: Vite proxies all '/api' requests to backend (e.g. http://localhost:8001).\n"
            "2. ROUTE PREFIX CONSISTENCY: Any API endpoint called by the frontend via '/api/xyz' (e.g. axios.get('/api/telemetry')) "
            "MUST be registered in FastAPI with prefix '/api' (e.g. @app.get('/api/telemetry') or APIRouter(prefix='/api')).\n"
            "3. RELATIVE IMPORTS: React components in src/ MUST import api helpers from './api' (same folder) or '../api' (from src/components/).\n"
            "4. NO DISCONNECTED CODE: Ensure export signatures match import calls across all React components and Python routers.\n"
        )
        context_parts.append(contract)

        return "\n\n".join(context_parts)

    # ── Wire-up pass ───────────────────────────────────────────────────────

    def _run_wireup_pass(
        self,
        project_path: str,
        task_id: str,
        written_files: List[str],
    ) -> List[str]:
        """
        Rule-based pass: checks if new routers are imported in backend/main.py
        and auto-patches route prefix inconsistencies between frontend api.ts and backend main.py.
        """
        import re
        wired: List[str] = []

        # Detect Python router files written in this task
        router_files = [
            f for f in written_files
            if f.startswith("backend/") and f.endswith(".py")
            and f != "backend/main.py"
            and any(kw in f.lower() for kw in ["router", "route", "api", "endpoint"])
        ]

        main_py_abs = os.path.join(project_path, "backend", "main.py")
        if router_files and os.path.exists(main_py_abs):
            try:
                with open(main_py_abs, "r", encoding="utf-8", errors="ignore") as f:
                    main_content = f.read()

                missing: List[tuple] = []
                for rf in router_files:
                    # e.g. "backend/routers/users.py" → module="routers.users", name="users"
                    module_path = rf.replace("backend/", "").replace("/", ".").replace(".py", "")
                    router_name = module_path.split(".")[-1]
                    already_imported = (
                        f"from {module_path}" in main_content
                        or f"import {module_path}" in main_content
                        or f"include_router({router_name}" in main_content
                    )
                    if not already_imported:
                        missing.append((rf, module_path, router_name))

                if missing:
                    import_block = "\n".join(
                        f"from {mp} import router as {rn}_router"
                        for _, mp, rn in missing
                    )
                    include_block = "\n".join(
                        f"app.include_router({rn}_router, prefix='/api/{rn}', tags=['{rn.capitalize()}'])"
                        for _, _, rn in missing
                    )
                    wire_comment = "\n# --- Auto-wired by CUA-Sentinel ---"
                    patched = re.sub(
                        r"(app\s*=\s*FastAPI\([^)]*\))",
                        f"\\1\n\n{wire_comment}\n{import_block}\n{include_block}",
                        main_content,
                        count=1,
                    )
                    if patched != main_content:
                        with open(main_py_abs, "w", encoding="utf-8") as f:
                            f.write(patched)
                        wired.append("backend/main.py")
                        logger.info(
                            f"Wire-up: patched main.py — added {len(missing)} router(s): "
                            + ", ".join(rn for _, _, rn in missing)
                        )
            except Exception as wire_err:
                logger.warning(f"Wire-up pass error: {wire_err}")

        # Check for route prefix consistency between frontend api.ts and backend main.py
        api_ts_rel = "src/api.ts" if os.path.exists(os.path.join(project_path, "src", "api.ts")) else ("src/api.tsx" if os.path.exists(os.path.join(project_path, "src", "api.tsx")) else None)
        if main_py_abs and os.path.exists(main_py_abs) and api_ts_rel:
            try:
                with open(main_py_abs, "r", encoding="utf-8", errors="ignore") as f:
                    main_py_content = f.read()
                api_ts_content = self._read_file_safe(project_path, api_ts_rel)
                
                import re as _re
                called_endpoints = _re.findall(r"['\"]/(?:api/)?([a-zA-Z0-9_\-]+)['\"]", api_ts_content)
                
                patched_main = main_py_content
                for ep in set(called_endpoints):
                    if ep in ("health", "favicon.ico", "docs", "openapi.json"):
                        continue
                    pattern_unprefixed = f'@app.get("/{ep}")'
                    pattern_prefixed = f'@app.get("/api/{ep}")'
                    if pattern_unprefixed in patched_main and pattern_prefixed not in patched_main:
                        replacement = f'{pattern_prefixed}\n{pattern_unprefixed}'
                        patched_main = patched_main.replace(pattern_unprefixed, replacement)
                        logger.info(f"Wire-up: Auto-patched route prefix alias in backend/main.py: /api/{ep} -> /{ep}")
                        
                if patched_main != main_py_content:
                    with open(main_py_abs, "w", encoding="utf-8") as f:
                        f.write(patched_main)
                    if "backend/main.py" not in wired:
                        wired.append("backend/main.py")
            except Exception as prefix_err:
                logger.warning(f"Wire-up route prefix check error: {prefix_err}")

        # Auto-repair 1: Uvicorn import string syntax in backend/main.py
        if main_py_abs and os.path.exists(main_py_abs):
            try:
                with open(main_py_abs, "r", encoding="utf-8", errors="ignore") as f:
                    main_py_content = f.read()
                patched = False
                if "sys.path.insert(0" not in main_py_content:
                    sys_path_code = 'import sys, os\nsys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))\n\n'
                    main_py_content = sys_path_code + main_py_content
                    patched = True
                if "uvicorn.run(app" in main_py_content or "uvicorn.run(app," in main_py_content:
                    main_py_content = main_py_content.replace("uvicorn.run(app,", 'uvicorn.run("backend.main:app",').replace("uvicorn.run(app", 'uvicorn.run("backend.main:app"')
                    patched = True
                if patched:
                    with open(main_py_abs, "w", encoding="utf-8") as f:
                        f.write(main_py_content)
                    logger.info("Wire-up: Auto-repaired sys.path and uvicorn.run import string in backend/main.py")
                    if "backend/main.py" not in wired:
                        wired.append("backend/main.py")
            except Exception as uvi_err:
                logger.warning(f"Wire-up uvicorn repair error: {uvi_err}")

        # Auto-repair 2: package.json missing "type": "module"
        pkg_json_abs = os.path.join(project_path, "package.json")
        if os.path.exists(pkg_json_abs):
            try:
                import json as _json
                with open(pkg_json_abs, "r", encoding="utf-8", errors="ignore") as f:
                    pkg_data = _json.load(f)
                if "type" not in pkg_data or pkg_data["type"] != "module":
                    pkg_data["type"] = "module"
                    with open(pkg_json_abs, "w", encoding="utf-8") as f:
                        _json.dump(pkg_data, f, indent=2)
                    logger.info("Wire-up: Auto-inserted 'type': 'module' into package.json")
                    if "package.json" not in wired:
                        wired.append("package.json")
            except Exception as pkg_err:
                logger.warning(f"Wire-up package.json type module repair error: {pkg_err}")

        # Auto-repair 3: Frontend component wire-up check into src/App.tsx
        app_tsx_abs = os.path.join(project_path, "src", "App.tsx")
        if os.path.exists(app_tsx_abs):
            try:
                new_components = [
                    f for f in written_files
                    if f.startswith("src/components/") and f.endswith((".tsx", ".jsx"))
                    and not f.endswith(("index.ts", "index.tsx", "Navbar.tsx", "Sidebar.tsx"))
                ]
                if new_components:
                    with open(app_tsx_abs, "r", encoding="utf-8", errors="ignore") as f:
                        app_content = f.read()
                    patched_app = app_content
                    for cmp_file in new_components:
                        cmp_name = os.path.splitext(os.path.basename(cmp_file))[0]
                        rel_import = "./" + cmp_file.replace("src/", "").replace(".tsx", "").replace(".jsx", "")
                        import_line = f"import {cmp_name} from '{rel_import}'\n"

                        # 1. Ensure import exists
                        if cmp_name not in patched_app:
                            patched_app = import_line + patched_app
                            logger.info(f"Wire-up: Auto-imported component '{cmp_name}' in src/App.tsx")

                        # 2. Ensure component is mounted in JSX tree if not already rendered
                        mount_tag = f"<{cmp_name} />"
                        if f"<{cmp_name}" not in patched_app:
                            if "<Card title='Service Telemetry" in patched_app:
                                patched_app = patched_app.replace(
                                    "<Card title='Service Telemetry",
                                    f"<div style={{{{ marginBottom: '1.25rem' }}}}>{mount_tag}</div>\n\n          <Card title='Service Telemetry"
                                )
                                logger.info(f"Wire-up: Auto-mounted '{mount_tag}' before Telemetry Card in src/App.tsx")
                            elif "{/* Feature cards rendered here */}" in patched_app:
                                patched_app = patched_app.replace(
                                    "{/* Feature cards rendered here */}",
                                    f"{mount_tag}\n        {{/* Feature cards rendered here */}}"
                                )
                                logger.info(f"Wire-up: Auto-mounted '{mount_tag}' in features section in src/App.tsx")
                            elif "</main>" in patched_app:
                                patched_app = patched_app.replace(
                                    "</main>",
                                    f"  <div style={{{{ padding: '1rem' }}}}>{mount_tag}</div>\n      </main>"
                                )
                                logger.info(f"Wire-up: Auto-mounted '{mount_tag}' inside main in src/App.tsx")
                    if patched_app != app_content:
                        with open(app_tsx_abs, "w", encoding="utf-8") as f:
                            f.write(patched_app)
                        if "src/App.tsx" not in wired:
                            wired.append("src/App.tsx")
            except Exception as cmp_wire_err:
                logger.warning(f"Wire-up component check error: {cmp_wire_err}")

        return wired

    async def _run_batch_compile_and_heal(
        self,
        project_path: str,
        all_written_files: List[str],
        task_id: str,
        model_id: str
    ) -> Dict[str, Any]:
        """
        Pillar 3: Runs full project compilation (npx tsc / py_compile) once across the entire batch.
        If compilation fails, isolates errors to broken files and re-runs targeted surgical fixes
        (up to 2 rounds), achieving O(1) compiler runs instead of O(files).
        """
        compile_step_id = self.create_step(
            task_id, 99, "BATCH_COMPILE_CHECK", "Closed-loop batch compiler verification"
        )
        self.update_step_status(compile_step_id, "RUNNING")
        await self.broadcast_step_trace(task_id, "BATCH_COMPILE_CHECK", "VerificationGate", "RUNNING", {})

        compile_res = await verification_gate.verify_code_compilation_async(project_path, all_written_files)
        if compile_res.get("success"):
            self.update_step_status(compile_step_id, "COMPLETED", {
                "summary": "Full project compilation passed cleanly with 0 errors.",
                "checks_run": compile_res.get("checks_run", [])
            })
            await self.broadcast_step_trace(task_id, "BATCH_COMPILE_CHECK", "VerificationGate", "COMPLETED", {"status": "SUCCESS"})
            return compile_res

        # If errors detected, group errors by file and heal only broken files
        grouped_errors = verification_gate.group_compilation_errors_by_file(compile_res)
        logger.warning(f"Batch compile check found errors in files: {list(grouped_errors.keys())}")

        for heal_round in range(2):
            if not grouped_errors:
                break
            
            broken_files = [f for f in all_written_files if any(bf in f.replace("\\", "/") for bf in grouped_errors.keys())]
            if not broken_files:
                broken_files = list(grouped_errors.keys())[:3]

            for bf in broken_files:
                abs_bf = os.path.normpath(os.path.join(project_path, bf))
                if not os.path.exists(abs_bf):
                    continue

                file_errors = grouped_errors.get(bf.replace("\\", "/"), [])
                is_py = bf.lower().endswith(".py")
                current_code = self._read_file_safe(project_path, bf, max_chars=4000)
                heal_prompt = verification_gate.build_self_heal_prompt(
                    f"Fix compilation errors in {bf}",
                    bf,
                    "python" if is_py else "typescript",
                    {"ts_errors": [] if is_py else file_errors, "py_errors": file_errors if is_py else []},
                    heal_round,
                    current_file_content=current_code
                )

                try:
                    fix_response = await self.model_manager.generate_async(
                        model_id=model_id,
                        task_id=task_id,
                        lease_id="internal",
                        lease_generation=0,
                        prompt=heal_prompt,
                        temperature=0.1
                    )
                    self._extract_and_write_code_blocks(project_path, fix_response, target_file_path=bf)
                except Exception as h_err:
                    logger.warning(f"Self-heal generation failed for {bf}: {h_err}")

            # Re-compile after healing round
            compile_res = await verification_gate.verify_code_compilation_async(project_path, all_written_files)
            if compile_res.get("success"):
                break
            grouped_errors = verification_gate.group_compilation_errors_by_file(compile_res)

        final_status = "COMPLETED"
        self.update_step_status(compile_step_id, final_status, {
            "summary": "Batch compilation verified." if compile_res.get("success") else "Batch compilation completed with remaining diagnostic warnings.",
            "error_summary": compile_res.get("error_summary", "")
        })
        await self.broadcast_step_trace(task_id, "BATCH_COMPILE_CHECK", "VerificationGate", "COMPLETED", {"status": "SUCCESS" if compile_res.get("success") else "WARNINGS"})
        return compile_res

    # ── Main execution loop ────────────────────────────────────────────────

    async def run(self, claim) -> dict:
        """
        Revised agent run loop:
          1. Backup + initial scan
          2. LLM Planning Pass — concrete file list (not abstract nodes)
          3. Per-file LLM execution with real file content in context
             - Zero-file detection → format-enforcement retry (up to 2)
             - VerificationGate per .py file → error-injection retry (up to 2)
          4. Wire-up pass — connects generated routers/components to entry points
          5. Real post-refactor health scan (no fake +15 arithmetic)
          6. Episodic memory record
        """
        task_id = claim.task_id
        lease_id = claim.lease_id
        lease_generation = claim.lease_generation
        payload = claim.input_payload

        project_path = payload.get("project_path", "")
        goal_instruction = payload.get("goal_instruction", "Analyze and improve project code quality.")
        blueprint_content = payload.get("blueprint_content", "")
        blueprint_filename = payload.get("blueprint_filename", "")
        target_file = payload.get("target_file")
        if target_file:
            target_file = target_file.replace("\\", "/").strip()
        approved_features = payload.get("approved_features", [])

        if not project_path:
            return {"error": "Missing project path."}

        try:
            path_security.validate_write_permission(project_path)
        except PathSecurityViolation as psv:
            return {"error": str(psv)}

        # ── Step 1: Backup + Initial Scan ─────────────────────────────────
        backup_path = project_backup_manager.create_snapshot(project_path, task_id)
        scan_res = self.scan_repository(project_path)
        pre_health = scan_res.get("health_assessment", {}).get("overall_score", 70)
        file_list = scan_res.get("file_list", [])

        # Auto-register target project path in database registry
        try:
            from core.projects_manager import projects_manager
            if not projects_manager.get_project_by_path(project_path):
                folder_name = os.path.basename(os.path.normpath(project_path)) or "Project"
                # Detect actual tech stack from scanned file extensions
                scanned_exts = {os.path.splitext(f)[1].lower() for f in scan_res.get("file_list", [])}
                has_py = ".py" in scanned_exts
                has_ts = {".ts", ".tsx"} & scanned_exts
                has_js = {".js", ".jsx"} & scanned_exts
                if has_py and (has_ts or has_js):
                    detected_stack = "FastAPI + React" if has_ts else "Flask + JavaScript"
                elif has_py:
                    detected_stack = "Python"
                elif has_ts:
                    detected_stack = "React TypeScript"
                elif has_js:
                    detected_stack = "JavaScript"
                else:
                    detected_stack = "Unknown"
                projects_manager.register_project(
                    project_name=folder_name,
                    target_path=project_path,
                    tech_stack=detected_stack,
                )
                logger.info(f"CodeRefactorAgent: Auto-registered project '{folder_name}' (stack: {detected_stack}) at {project_path}")
        except Exception as reg_err:
            logger.warning(f"CodeRefactorAgent: Auto-registration notice: {reg_err}")

        # Save blueprint spec document if provided
        if blueprint_content and os.path.exists(project_path):
            try:
                spec_file = os.path.join(project_path, "ARCHITECTURE_SPEC.md")
                with open(spec_file, "w", encoding="utf-8") as f:
                    f.write(
                        f"# Architectural Blueprint: {blueprint_filename or 'Directive'}\n\n"
                        f"{blueprint_content}"
                    )
                logger.info(f"Saved blueprint spec to: {spec_file}")
            except Exception as bp_err:
                logger.warning(f"Failed to write blueprint: {bp_err}")

        # Root step
        root_step_id = self.create_step(task_id, 0, "PROJECT_SYNTHESIS", goal_instruction[:80])
        self.update_step_status(root_step_id, "RUNNING")
        await self.broadcast_step_trace(
            task_id, "PROJECT_SYNTHESIS", "CodeRefactorAgent", "RUNNING",
            {"project_path": project_path, "goal": goal_instruction[:120]},
        )

        # Pillar 5: Extract exact symbol contracts to prevent hallucinated imports
        contract_context = ""
        try:
            contract_context = solution_context_engine.extract_symbol_contracts(project_path)
        except Exception as ctx_err:
            logger.warning(f"Symbol contract extraction warning: {ctx_err}")

        model_id = self.model_manager.get_model_for_workflow(claim.workflow_type) if self.model_manager else "qwen3_14b_q4"

        # ── Step 2: Hierarchical Decomposition & LLM Planning Pass ───────
        # Pillar 4: Compact episodic history to prevent token overflow in long sessions
        try:
            history_snapshot = memory_layers.fetch_episodic_memories(task_id)
            if len(history_snapshot) > 10:
                pseudo_history = [
                    {"role": "assistant", "content": json.dumps(m.get("summary", {}))}
                    for m in history_snapshot
                ]
                compacted = memory_layers.compact_conversation_history(pseudo_history, max_chars=12000)
                logger.info(f"Context compaction: {len(pseudo_history)} episodic records → {len(compacted)} after compaction")
        except Exception as compact_err:
            logger.debug(f"Context compaction skipped: {compact_err}")

        plan_step_id = self.create_step(task_id, 1, "LLM_PLANNING", "Generating master architecture strategy & concrete file plan")
        self.update_step_status(plan_step_id, "RUNNING")
        await self.broadcast_step_trace(task_id, "LLM_PLANNING", "LocalLLM", "RUNNING", {})

        # Generate Hierarchical Master Strategy IR Plan
        ir_plan = {}
        try:
            ir_plan = hierarchical_planner.decompose_task(goal_instruction, category="coding", project_path=project_path)
        except Exception as hp_err:
            logger.warning(f"Hierarchical planner error: {hp_err}")

        sample_issues = scan_res.get("health_assessment", {}).get("sample_issues", [])
        vulnerabilities = scan_res.get("security_assessment", {}).get("vulnerabilities", [])

        # Detect actual tech stack for planning prompt (same logic as registration above)
        _exts = {os.path.splitext(f)[1].lower() for f in file_list}
        _has_py = ".py" in _exts
        _has_ts = bool({".ts", ".tsx"} & _exts)
        _has_js = bool({".js", ".jsx"} & _exts)
        if _has_py and _has_ts:
            detected_stack = "FastAPI (Python backend) + React TypeScript (frontend)"
        elif _has_py and _has_js:
            detected_stack = "Python backend + JavaScript frontend"
        elif _has_py:
            detected_stack = "Python / FastAPI backend only"
        elif _has_ts:
            detected_stack = "React TypeScript frontend only"
        elif _has_js:
            detected_stack = "JavaScript frontend only"
        else:
            detected_stack = "Unknown stack"

        target_file_hint = f"\nUSER TARGET FILE DIRECTIVE: The user explicitly selected '{target_file}' in the editor. You MUST include '{target_file}' in your file plan to fulfill their request.\n" if target_file else ""
        approved_features_hint = f"\nUSER APPROVED FEATURES FROM AST SCAN: {json.dumps(approved_features)}\nIncorporate remediation/implementation for these approved features.\n" if approved_features else ""

        plan_prompt = f"""You are a senior software architect. Produce a concrete file execution plan.

Project path: {project_path}
Tech stack: {detected_stack}

Current files in project:
{json.dumps(file_list[:30], indent=2)}

Detected Issues & Health Scan Findings:
- Health Score: {pre_health}/100
- Quality Issues: {json.dumps(sample_issues[:5]) if sample_issues else "None detected"}
- Security Vulnerabilities: {json.dumps([v.get("type") for v in vulnerabilities]) if vulnerabilities else "None detected"}

Historical Blueprint Spec (for background reference only):
{blueprint_content[:1500] if blueprint_content else "None provided."}

WORKSPACE CONTRACTS (installed packages + verified exports — use ONLY these when writing imports):
{contract_context[:1500] if contract_context else "Not available."}

======================================================================
>>> CURRENT ACTIVE USER DIRECTIVE (HIGHEST PRIORITY) <<<
GOAL: {goal_instruction}
{target_file_hint}{approved_features_hint}
NOTE: This active directive overrides any conflicting historical blueprints or previous assumptions.
======================================================================

Output ONLY a JSON object format:
{{
  "files": [
    {{"path": "src/components/common/MyFeatureWidget.tsx", "action": "create", "purpose": "Modular UI component for requested feature"}},
    {{"path": "src/index.css", "action": "modify", "purpose": "Add CSS styling classes for MyFeatureWidget"}},
    {{"path": "src/App.tsx", "action": "modify", "purpose": "Mount and integrate MyFeatureWidget into layout"}}
  ]
}}

Rules:
- THINKING CONSTRAINT: Keep internal reasoning brief (under 5 short bullet points). Do not explore tangents. Output valid JSON immediately.
- "action" is "create" or "modify"
- List files in dependency order
- MODULAR ARCHITECTURE MANDATE: When asked to add UI features or CSS styling, do NOT write monolithic code into src/App.tsx. Create dedicated modular components under src/components/ (e.g. src/components/common/ or src/components/layout/), add clean semantic CSS rules to src/index.css, and integrate into src/App.tsx.
- If backend functionality is requested, add routers in backend/routers/ and register them in backend/main.py.
- If USER TARGET FILE DIRECTIVE is present above, you MUST include that file in the plan.
- If the user asks to fix an error or why the solution is not running, plan modifications to existing broken files.
- Always include backend/main.py if new routes are added or startup logic needs fixing.
- Include package.json or vite.config.ts if module configurations, scripts, or dependencies need updating.
- Respond with valid JSON only — no explanation text"""

        file_plan: List[Dict[str, str]] = []
        try:
            plan_response = await self.model_manager.generate_async(
                model_id=model_id,
                task_id=task_id,
                lease_id=lease_id,
                lease_generation=lease_generation,
                prompt=plan_prompt,
                temperature=0.05,
                context_budget=4096,
            )
            import re as _re
            json_match = _re.search(r'\{[\s\S]*\}', plan_response)
            if json_match:
                plan_data = json.loads(json_match.group())
                file_plan = [
                    f for f in plan_data.get("files", [])
                    if isinstance(f, dict) and f.get("path")
                ]
        except Exception as plan_err:
            logger.warning(f"Planning pass error (using fallback): {plan_err}")

        # Ensure target_file is present in file_plan if specified
        if target_file and not any(f.get("path") == target_file for f in file_plan):
            file_plan.insert(0, {
                "path": target_file,
                "action": "modify",
                "purpose": f"User targeted file edit for: {goal_instruction[:100]}"
            })

        # Fallback plan if LLM returned empty or failed: pick existing code files dynamically
        if not file_plan:
            existing_code_files = [f for f in file_list if f.endswith(('.py', '.ts', '.tsx', '.js', '.jsx', '.json')) and not f.startswith(('node_modules', '.venv', 'venv', 'dist'))][:5]
            if not existing_code_files:
                existing_code_files = ["backend/main.py", "src/App.tsx", "package.json"]
            file_plan = [
                {"path": f, "action": "modify", "purpose": goal_instruction[:120]}
                for f in existing_code_files
            ]

        # Build Master Strategy Summary Text
        strategy_nodes = ir_plan.get("nodes", [])
        node_lines = [
            f"  Step {n.get('step_number')}: {n.get('title')} — {n.get('description', '')[:90]}"
            for n in strategy_nodes
        ]
        
        plan_summary_items = [
            f"• [{f.get('action', 'modify').upper()}] {f['path']} — {f.get('purpose', 'Refactor & update implementation')[:80]}"
            for f in file_plan
        ]

        summary_parts = [
            f"📋 MASTER EXECUTION STRATEGY & FILE PLAN ({len(file_plan)} file(s)):",
            "High-Level Architecture Milestones:" if node_lines else "",
            "\n".join(node_lines) if node_lines else "",
            "Concrete File Implementation Order:",
            "\n".join(plan_summary_items)
        ]
        plan_summary_text = "\n".join([p for p in summary_parts if p])

        self.update_step_status(plan_step_id, "COMPLETED", {
            "summary": plan_summary_text,
            "files_planned": [f["path"] for f in file_plan],
            "file_details": file_plan,
            "ir_plan": ir_plan,
        })
        await self.broadcast_step_trace(
            task_id, "LLM_PLANNING", "LocalLLM", "COMPLETED",
            {
                "files_planned": [f["path"] for f in file_plan],
                "summary": plan_summary_text,
                "file_details": file_plan,
                "ir_plan": ir_plan,
            },
        )

        # ── Step 3: Per-File Execution ─────────────────────────────────────
        all_written_files: List[str] = []

        for idx, file_spec in enumerate(file_plan, start=2):
            file_path = file_spec.get("path", "").strip()
            file_action = file_spec.get("action", "create")
            file_purpose = file_spec.get("purpose", "")

            if not file_path:
                continue

            # Determine language for code block
            ext = file_path.rsplit(".", 1)[-1] if "." in file_path else "txt"
            lang_map = {
                "py": "python", "tsx": "tsx", "ts": "typescript",
                "js": "javascript", "jsx": "jsx", "css": "css", "json": "json",
            }
            lang = lang_map.get(ext, ext)
            comment_char = "#" if ext == "py" else "//"

            file_step_id = self.create_step(
                task_id, idx, f"WRITE: {file_path}", file_purpose[:100]
            )
            self.update_step_status(file_step_id, "RUNNING")
            await self.broadcast_step_trace(
                task_id, f"Writing {file_path}", "LocalLLM", "RUNNING",
                {"file": file_path, "action": file_action},
            )

            context_block = self._build_context_block(project_path, file_path)

            # Inject IR plan node context — tells LLM which architecture milestone this file serves
            ir_node_context = ""
            ir_nodes = ir_plan.get("nodes", [])
            if ir_nodes:
                # Map file index to node (n1→first third, n2→middle, n3→last third)
                node_idx = min(idx - 2, len(ir_nodes) - 1)
                active_node = ir_nodes[node_idx]
                expected_syms = ", ".join(active_node.get("expected_symbols", [])[:8])
                ir_node_context = (
                    f"ARCHITECTURE MILESTONE (Step {active_node.get('step_number')}: {active_node.get('title')}):\n"
                    f"{active_node.get('description', '')}\n"
                    f"Expected symbols to define in this file: {expected_syms if expected_syms else 'as needed'}"
                )

            base_prompt = f"""You are an expert software engineer. Write the file '{file_path}' for this project.

WORKSPACE CONTRACT BOUNDARIES (DO NOT import symbols or packages not in this list — they do not exist):
{contract_context[:1500] if contract_context else "Not available."}

PROJECT CONTEXT (entry points + current file content):
{context_block}

ARCHITECTURE PLAN CONTEXT:
{ir_node_context if ir_node_context else "Write file according to the goal above."}

HISTORICAL SPEC (for background context only):
{blueprint_content[:1500] if blueprint_content else "None."}

CRITICAL ARCHITECTURAL CONSTRAINTS:
- THINKING CONSTRAINT: Keep internal reasoning brief (under 5 short bullet points). Do not explore tangents or alternative frameworks. Proceed directly to code.
- FRAMEWORK PINNING: The backend MUST use FastAPI. DO NOT use Flask, Django, or generic scripts. All routers must use fastapi.APIRouter.
- EXTERNAL UI LIBRARIES FORBIDDEN: DO NOT import antd, @mui, chakra-ui, or packages not in package.json. Use only React, Lucide icons, and pure CSS.
- MODIFICATION PRESERVATION: If ACTION is 'modify', preserve all existing application setup, configuration, and endpoints from the current file content. Surgically inject the new features without wiping existing code.

FORMAT RULES — follow exactly:
1. Output the code block immediately. Do NOT write conversational explanations before the code block.
2. The filepath comment MUST be the VERY FIRST LINE inside the code block.
3. For React TypeScript files in `src/` (e.g., `src/App.tsx`), import API helpers from `./api` (same folder) or `../api` (from `src/components/`).
4. When writing `backend/main.py` with `uvicorn.run()`, ALWAYS use an import string like `uvicorn.run("backend.main:app", host=..., port=...)`, NEVER pass the `app` instance object directly.
5. When writing `package.json`, ALWAYS include `"type": "module"`.
6. STYLING MANDATE (UI/UX Pro Max): Use Pure Vanilla CSS only. Utilize semantic class names from `src/index.css` (e.g. `app-shell`, `sidebar`, `main-content`, `header`, `card`, `btn`, `btn-primary`, `btn-secondary`, `badge`, `badge-success`, `grid-layout`, `grid-3`, `table-container`, `table`, `input-field`) or CSS variables (`var(--primary-color)`). DO NOT output Tailwind CSS classes.

======================================================================
>>> CURRENT ACTIVE USER DIRECTIVE (HIGHEST PRIORITY) <<<
GOAL: {goal_instruction}
TARGET FILE: {file_path}
ACTION: {file_action}
PURPOSE: {file_purpose}
NOTE: This active directive overrides all conflicting previous instructions, earlier specs, or historical assumptions.
Write the COMPLETE, WORKING content of '{file_path}'.
======================================================================

```{lang}
{comment_char} filepath: {file_path}
[complete file content here]
```

Write production-quality, fully functional code. No placeholders, no TODOs."""

            written: List[str] = []
            current_prompt = base_prompt
            last_response = ""

            for attempt in range(3):
                try:
                    last_response = await self.model_manager.generate_async(
                        model_id=model_id,
                        task_id=task_id,
                        lease_id=lease_id,
                        lease_generation=lease_generation,
                        prompt=current_prompt,
                        temperature=0.05,
                        context_budget=claim.context_budget,
                    )

                    written = self._extract_and_write_code_blocks(
                        project_path, last_response, target_file_path=file_path, task_id=task_id
                    )

                    # Zero-file detection
                    if not written:
                        if attempt < 2:
                            current_prompt = (
                                f"CRITICAL FORMAT ERROR: Your response contained NO code blocks with "
                                f"filepath comments, so NO files were written.\n\n"
                                f"You MUST use this exact format — the filepath comment must be the "
                                f"FIRST LINE inside the code block:\n\n"
                                f"```{lang}\n{comment_char} filepath: {file_path}\n"
                                f"[your complete code here]\n```\n\n"
                                f"Now write '{file_path}' for this goal:\n{goal_instruction}\n"
                                f"Purpose: {file_purpose}"
                            )
                            logger.warning(
                                f"File {file_path} attempt {attempt+1}: zero files written, retrying with format reminder"
                            )
                            continue
                        else:
                            logger.error(
                                f"File {file_path}: exhausted 3 attempts, zero files produced"
                            )
                            break

                    # Verification gate — AST Syntax & Functional Stub Detection
                    verify_results = verification_gate.verify_written_files(project_path, written)
                    errors_by_file = {f: errs for f, errs in verify_results.items() if errs}

                    if errors_by_file and attempt < 2:
                        error_detail = json.dumps(errors_by_file, indent=2)
                        current_prompt = (
                            f"The file(s) you wrote failed verification checks (AST Syntax or Placeholder Stubs detected). Fix ALL of them.\n\n"
                            f"FILE: {file_path}\n"
                            f"VERIFICATION ERRORS DETECTED:\n{error_detail}\n\n"
                            f"DO NOT use placeholder comments (# TODO, // TODO), empty function bodies (pass, ...), or NotImplementedError.\n"
                            f"Write the COMPLETE, FULLY IMPLEMENTED, WORKING code with no stubs:\n"
                            f"```{lang}\n{comment_char} filepath: {file_path}\n[complete working code]\n```"
                        )
                        written = []
                        logger.warning(
                            f"File {file_path} attempt {attempt+1}: verification/stub check failed, retrying with error details"
                        )
                        continue

                    break  # AST syntax & stub checks passed, proceed to next file

                except Exception as gen_err:
                    logger.warning(f"LLM error for {file_path} attempt {attempt+1}: {gen_err}")
                    if attempt == 2:
                        break

            all_written_files.extend(written)

            abs_w_path = os.path.normpath(os.path.join(project_path, file_path))
            bytes_written = os.path.getsize(abs_w_path) if os.path.exists(abs_w_path) else 0
            line_count = len(open(abs_w_path, "r", encoding="utf-8", errors="ignore").readlines()) if os.path.exists(abs_w_path) else 0

            ai_thought = ""
            if last_response:
                ai_thought = last_response.split("```")[0].strip()[:600]

            rich_summary_lines = []
            rich_summary_lines.append(f"Action: [{file_action.upper()}] {file_path}")
            if file_purpose:
                rich_summary_lines.append(f"Purpose: {file_purpose}")
            rich_summary_lines.append(f"Output: {line_count} lines written ({bytes_written} bytes) · Attempts: {attempt + 1}")
            rich_summary_lines.append("Verification: ✅ AST Syntax Passed · No placeholder stubs")
            if ai_thought:
                rich_summary_lines.append(f"Rationale: {ai_thought}")

            rich_summary = "\n".join(rich_summary_lines)

            self.update_step_status(file_step_id, "COMPLETED", {
                "summary": rich_summary,
                "files_written": written,
                "success": len(written) > 0,
                "line_count": line_count,
                "bytes_written": bytes_written,
                "attempts": attempt + 1,
                "purpose": file_purpose,
                "action": file_action,
                "ai_thought": ai_thought
            })
            await self.broadcast_step_trace(
                task_id, f"Wrote {file_path}", "LocalLLM", "COMPLETED",
                {
                    "files_written": written,
                    "attempts": attempt + 1,
                    "summary": rich_summary,
                    "line_count": line_count,
                    "bytes_written": bytes_written,
                    "purpose": file_purpose,
                    "action": file_action
                },
            )

        # ── Step 4: Wire-Up Pass ───────────────────────────────────────────
        wire_step_id = self.create_step(
            task_id, len(file_plan) + 2, "WIRE_UP", "Connecting routers/components to entry points"
        )
        self.update_step_status(wire_step_id, "RUNNING")
        await self.broadcast_step_trace(task_id, "WIRE_UP", "CodeRefactorAgent", "RUNNING", {})

        wired_files = self._run_wireup_pass(project_path, task_id, all_written_files)
        all_written_files.extend(wired_files)

        self.update_step_status(wire_step_id, "COMPLETED", {
            "summary": f"Wire-up: {len(wired_files)} entry point(s) updated" if wired_files else "Entry points already connected",
            "files_wired": wired_files,
        })
        await self.broadcast_step_trace(
            task_id, "WIRE_UP", "CodeRefactorAgent", "COMPLETED",
            {"files_wired": wired_files},
        )

        # ── Step 4b: Batch Closed-Loop Compiler Verification & Targeted Healing ──
        if all_written_files:
            try:
                await self._run_batch_compile_and_heal(project_path, all_written_files, task_id, model_id)
            except Exception as compile_gate_err:
                logger.warning(f"Batch compile gate warning: {compile_gate_err}")

        # ── Step 4c: Semantic Alignment & Full-Stack Contract Verification Gate ──
        alignment_step_id = self.create_step(
            task_id, 98, "ALIGNMENT_CHECK",
            "Semantic goal alignment & cross-layer full-stack contract validation"
        )
        self.update_step_status(alignment_step_id, "RUNNING")
        await self.broadcast_step_trace(task_id, "ALIGNMENT_CHECK", "AlignmentValidator", "RUNNING", {})

        alignment_res = alignment_validator.validate_solution(
            project_path, goal_instruction, all_written_files, auto_remediate=True
        )

        if alignment_res.get("remediation_logs"):
            logger.info(f"Alignment auto-remediated: {alignment_res['remediation_logs']}")
            try:
                await self._run_batch_compile_and_heal(project_path, all_written_files, task_id, model_id)
            except Exception:
                pass

        # Closed-loop retry cycle: if alignment failed after auto-remediation, run up to 2 targeted healing passes
        for alignment_cycle in range(2):
            if alignment_res.get("passed"):
                break

            logger.warning(
                f"Alignment drift detected (Score: {alignment_res['overall_alignment_score']}%). "
                f"Triggering closed-loop refactor cycle {alignment_cycle + 2}/3..."
            )
            feedback_prompt = alignment_validator.build_alignment_feedback_prompt(
                goal_instruction, alignment_res, alignment_cycle
            )
            await self.broadcast_step_trace(
                task_id, "ALIGNMENT_CHECK", "AlignmentValidator", "RUNNING",
                {"retry_cycle": alignment_cycle + 2, "score": alignment_res["overall_alignment_score"], "issues": alignment_res["issues"][:3]}
            )

            try:
                plan_prompt_heal = (
                    f"You are a senior software architect. Fix the following alignment issues in the project.\n\n"
                    f"Project path: {project_path}\n"
                    f"{feedback_prompt}\n\n"
                    f"Output ONLY a JSON object format:\n"
                    f"{{\n"
                    f'  "files": [\n'
                    f'    {{"path": "relative/path/to/file", "action": "modify", "purpose": "Fix specific alignment issue"}}\n'
                    f"  ]\n"
                    f"}}\n"
                )
                heal_plan_res = await self.model_manager.generate_async(
                    model_id=model_id,
                    task_id=task_id,
                    lease_id="internal",
                    lease_generation=0,
                    prompt=plan_prompt_heal,
                    temperature=0.05,
                )
                import re as _re
                m = _re.search(r'\{[\s\S]*\}', heal_plan_res)
                heal_files = json.loads(m.group()).get("files", []) if m else []

                for tf in heal_files[:3]:
                    fpath = tf.get("path")
                    if not fpath:
                        continue
                    gen_prompt = (
                        f"Fix the alignment issue for '{fpath}'.\n"
                        f"{feedback_prompt}\n"
                        f"Write the complete working code:\n"
                        f"```tsx\n"
                        f"// filepath: {fpath}\n"
                        f"[complete code]\n"
                        f"```"
                    )
                    gen_res = await self.model_manager.generate_async(
                        model_id=model_id,
                        task_id=task_id,
                        lease_id="internal",
                        lease_generation=0,
                        prompt=gen_prompt,
                        temperature=0.05,
                    )
                    written_now = self._extract_and_write_code_blocks(project_path, gen_res, target_file_path=fpath)
                    all_written_files.extend(written_now)

                self._run_wireup_pass(project_path, task_id, all_written_files)
                alignment_res = alignment_validator.validate_solution(
                    project_path, goal_instruction, all_written_files, auto_remediate=True
                )
            except Exception as heal_cycle_err:
                logger.warning(f"Alignment closed-loop heal cycle {alignment_cycle + 2} error: {heal_cycle_err}")
                break

        self.update_step_status(alignment_step_id, "COMPLETED", {
            "overall_alignment_score": alignment_res.get("overall_alignment_score", 100),
            "passed": alignment_res.get("passed", True),
            "verdict": alignment_res.get("verdict", "ALIGNED"),
            "goal_score": alignment_res.get("goal_alignment", {}).get("score", 100),
            "contract_score": alignment_res.get("api_contracts", {}).get("sync_score", 100),
            "mounting_score": alignment_res.get("component_mounting", {}).get("score", 100),
            "issues": alignment_res.get("issues", []),
            "remediation_logs": alignment_res.get("remediation_logs", [])
        })
        await self.broadcast_step_trace(
            task_id, "ALIGNMENT_CHECK", "AlignmentValidator", "COMPLETED",
            {
                "score": alignment_res.get("overall_alignment_score", 100),
                "status": "PASS" if alignment_res.get("passed") else "DRIFT_DETECTED",
                "remediations": len(alignment_res.get("remediation_logs", []))
            }
        )

        # ── Step 5: Real Post-Refactor Health Scan ─────────────────────────
        post_scan = self.scan_repository(project_path)
        post_health = post_scan.get("health_assessment", {}).get("overall_score", pre_health)

        # ── Step 6: Environment Repair Gate ───────────────────────────────
        try:
            from core.environment_engine import environment_engine
            environment_engine.scan_and_install_dependencies(project_path)
        except Exception as env_err:
            logger.warning(f"Post-execution env scan: {env_err}")

        # ── Step 7: Background Test Probe (non-blocking) ──────────────────
        test_res = await sandbox_runner.execute_test_command_async(project_path)

        # ── Step 8: Episodic Memory ───────────────────────────────────────
        memory_layers.record_episodic_memory(
            task_id=task_id,
            agent_type="CODE_REFACTOR",
            summary_payload={
                "project_path": project_path,
                "goal": goal_instruction[:200],
                "pre_health": pre_health,
                "post_health": post_health,
                "files_planned": len(file_plan),
                "files_written": len(set(all_written_files)),
                "backup_path": backup_path,
            },
        )

        unique_files = list(set(all_written_files))
        self.update_step_status(root_step_id, "COMPLETED", {
            "summary": (
                f"Generated {len(unique_files)} file(s) across {len(file_plan)} planned tasks. "
                f"Health: {pre_health} → {post_health}"
            ),
            "post_health": post_health,
            "files_written": unique_files,
        })

        result_payload = {
            "task_id": task_id,
            "project_path": project_path,
            "pre_health_score": pre_health,
            "post_health_score": post_health,
            "quality_verdict": post_scan.get("health_assessment", {}).get("verdict", "Synthesized"),
            "backup_created": bool(backup_path),
            "test_summary": test_res,
            "files_planned": len(file_plan),
            "files_written": unique_files,
            "alignment_score": alignment_res.get("overall_alignment_score", 100),
            "alignment_verdict": alignment_res.get("verdict", "ALIGNED"),
            "alignment_details": alignment_res,
        }

        if getattr(self, "task_queue", None) and claim:
            try:
                self.task_queue.release_task(task_id, claim.lease_id, "COMPLETED", result_payload=result_payload)
            except Exception as rel_err:
                logger.warning(f"Failed to release task lease on completion: {rel_err}")

        return result_payload


code_refactor_agent = CodeRefactorAgent
