"""
Projects Registry & Live App Process Manager for CUA-Sentinel.

Provides database persistence for created/scaffolded/refactored projects, dynamic server process execution,
real-time stdout/stderr log streaming, zip archiving, and safe disk deletion.
"""

import os
import shutil
import uuid
import zipfile
import subprocess
import threading
import collections
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path

try:
    from db.connections import get_operational_db
    from core.path_security import path_security, PathSecurityViolation
    from core.sandbox_runner import sandbox_runner
except ModuleNotFoundError:
    from backend.db.connections import get_operational_db
    from backend.core.path_security import path_security, PathSecurityViolation
    from backend.core.sandbox_runner import sandbox_runner

logger = logging.getLogger(__name__)

# Max log lines per running project process
MAX_LOG_LINES = 500

class ProjectsManager:
    def __init__(self):
        self._active_processes: Dict[str, subprocess.Popen] = {}
        self._project_logs: Dict[str, collections.deque] = collections.defaultdict(lambda: collections.deque(maxlen=MAX_LOG_LINES))
        self._log_threads: Dict[str, List[threading.Thread]] = collections.defaultdict(list)

    def register_project(
        self,
        project_name: str,
        target_path: str,
        tech_stack: str,
        ui_style: str = "Glassmorphism",
        blueprint_filename: Optional[str] = None,
        health_score: int = 100,
        security_score: int = 100
    ) -> Dict[str, Any]:
        """
        Registers a created/scaffolded/refactored solution in the persistent database.
        """
        norm_path = os.path.abspath(target_path)
        project_id = f"proj_{uuid.uuid4().hex[:10]}"

        conn = get_operational_db()
        try:
            # Check if path already registered
            cursor = conn.execute("SELECT * FROM created_projects WHERE target_path = ?", (norm_path,))
            existing = cursor.fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE created_projects
                    SET project_name = ?, tech_stack = ?, ui_style = ?, blueprint_filename = ?,
                        health_score = ?, security_score = ?
                    WHERE target_path = ?
                    """,
                    (project_name, tech_stack, ui_style, blueprint_filename, health_score, security_score, norm_path)
                )
                conn.commit()
                return self.get_project_by_path(norm_path)

            conn.execute(
                """
                INSERT INTO created_projects (
                    project_id, project_name, target_path, tech_stack, ui_style,
                    blueprint_filename, health_score, security_score, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'STOPPED')
                """,
                (project_id, project_name, norm_path, tech_stack, ui_style, blueprint_filename, health_score, security_score)
            )
            conn.commit()
            logger.info(f"Registered project '{project_name}' ({project_id}) at path: {norm_path}")
            return self.get_project(project_id)
        finally:
            conn.close()

    def get_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        conn = get_operational_db()
        try:
            cursor = conn.execute("SELECT * FROM created_projects WHERE project_id = ?", (project_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._enrich_project_dict(dict(row))
        finally:
            conn.close()

    def get_project_by_path(self, target_path: str) -> Optional[Dict[str, Any]]:
        norm_path = os.path.abspath(target_path)
        conn = get_operational_db()
        try:
            cursor = conn.execute("SELECT * FROM created_projects WHERE target_path = ?", (norm_path,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._enrich_project_dict(dict(row))
        finally:
            conn.close()

    def list_projects(self) -> List[Dict[str, Any]]:
        """
        Lists all registered projects enriched with live status, disk size, and file counts.
        """
        conn = get_operational_db()
        try:
            cursor = conn.execute("SELECT * FROM created_projects ORDER BY created_at DESC")
            rows = cursor.fetchall()
            projects = []
            for row in rows:
                p_dict = dict(row)
                projects.append(self._enrich_project_dict(p_dict))
            return projects
        finally:
            conn.close()

    def _enrich_project_dict(self, p_dict: Dict[str, Any]) -> Dict[str, Any]:
        p_id = p_dict.get("project_id", "")
        t_path = p_dict.get("target_path", "")
        path_exists = os.path.exists(t_path) if t_path else False

        p_dict["path_exists"] = path_exists
        p_dict["file_count"] = 0
        p_dict["disk_size_mb"] = 0.0

        if path_exists:
            total_bytes = 0
            file_cnt = 0
            try:
                for root, dirs, files in os.walk(t_path):
                    dirs[:] = [d for d in dirs if d not in ('.git', 'node_modules', 'venv', '__pycache__', '.pytest_cache')]
                    file_cnt += len(files)
                    for f in files:
                        try:
                            fp = os.path.join(root, f)
                            if os.path.isfile(fp):
                                total_bytes += os.path.getsize(fp)
                        except Exception:
                            pass
            except Exception:
                pass
            p_dict["file_count"] = file_cnt
            p_dict["disk_size_mb"] = round(total_bytes / (1024 * 1024), 2)

        try:
            proc = self._active_processes.get(p_id)
            if proc and proc.poll() is None:
                p_dict["status"] = "RUNNING"
                p_dict["active_pid"] = proc.pid
            else:
                if p_id in self._active_processes:
                    del self._active_processes[p_id]
                if p_dict.get("status") == "RUNNING":
                    p_dict["status"] = "STOPPED"
                    p_dict["active_port"] = None
                    p_dict["active_pid"] = None
                    self._update_db_status(p_id, "STOPPED", None, None)
        except Exception:
            pass

        return p_dict

    def _update_db_status(self, project_id: str, status: str, port: Optional[int], pid: Optional[int]) -> None:
        conn = get_operational_db()
        try:
            conn.execute(
                "UPDATE created_projects SET status = ?, active_port = ?, active_pid = ? WHERE project_id = ?",
                (status, port, pid, project_id)
            )
            conn.commit()
        finally:
            conn.close()

    def start_project_server(self, project_id: str) -> Dict[str, Any]:
        """
        Starts background dev server for the given project, returning host URL and port.
        """
        project = self.get_project(project_id)
        if not project:
            return {"success": False, "error": f"Project '{project_id}' not found."}

        target_path = project["target_path"]
        if not os.path.exists(target_path):
            return {"success": False, "error": f"Project directory does not exist: {target_path}"}

        # If process already running, return running info
        proc = self._active_processes.get(project_id)
        if proc and proc.poll() is None:
            port = project.get("active_port") or 8001
            return {
                "success": True,
                "project_id": project_id,
                "status": "RUNNING",
                "port": port,
                "pid": proc.pid,
                "preview_url": f"http://localhost:{port}",
                "message": "Server is already running."
            }

        allocated_port = sandbox_runner.find_open_port(8001)
        preview_url = f"http://localhost:{allocated_port}"

        # Pre-flight environment check & dependency auto-install
        try:
            from core.environment_engine import environment_engine
            environment_engine.scan_and_install_dependencies(target_path)
            environment_engine.ensure_env_defaults(target_path)
        except Exception as env_err:
            logger.warning(f"Pre-flight environment check warning for {project_id}: {env_err}")

        # Determine start command
        package_json = os.path.join(target_path, "package.json")
        index_html = os.path.join(target_path, "index.html")
        backend_main = os.path.join(target_path, "backend", "main.py")
        root_main = os.path.join(target_path, "main.py")
        node_modules = os.path.join(target_path, "node_modules")

        if os.path.exists(package_json) and os.path.exists(node_modules):
            cmd = f"npx vite --port {allocated_port} --host"
        elif os.path.exists(index_html):
            cmd = f"python -m http.server {allocated_port}"
        elif os.path.exists(backend_main):
            cmd = f'python -c "import sys, uvicorn; sys.path.insert(0, \'.\'); from backend.main import app; uvicorn.run(app, host=\'0.0.0.0\', port={allocated_port})"'
        elif os.path.exists(root_main):
            cmd = f'python -c "import sys, uvicorn; sys.path.insert(0, \'.\'); from main import app; uvicorn.run(app, host=\'0.0.0.0\', port={allocated_port})"'
        else:
            cmd = f"python -m http.server {allocated_port}"

        logger.info(f"Launching app server for {project_id} on port {allocated_port}: {cmd}")

        try:
            new_proc = subprocess.Popen(
                cmd,
                shell=True,
                cwd=target_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1
            )
            self._active_processes[project_id] = new_proc
            self._update_db_status(project_id, "RUNNING", allocated_port, new_proc.pid)

            # Start stdout and stderr log capture threads
            self._start_log_streamer(project_id, new_proc)

            return {
                "success": True,
                "project_id": project_id,
                "status": "RUNNING",
                "port": allocated_port,
                "pid": new_proc.pid,
                "preview_url": preview_url,
                "command": cmd
            }
        except Exception as e:
            logger.error(f"Failed to start server for {project_id}: {e}")
            return {"success": False, "error": str(e)}

    def _start_log_streamer(self, project_id: str, proc: subprocess.Popen) -> None:
        def stream_output(pipe, prefix: str):
            try:
                for line in iter(pipe.readline, ''):
                    if not line:
                        break
                    clean_line = f"[{prefix}] {line.rstrip()}"
                    self._project_logs[project_id].append(clean_line)
            except Exception:
                pass
            finally:
                pipe.close()

        t_out = threading.Thread(target=stream_output, args=(proc.stdout, "STDOUT"), daemon=True)
        t_err = threading.Thread(target=stream_output, args=(proc.stderr, "STDERR"), daemon=True)
        t_out.start()
        t_err.start()
        self._log_threads[project_id] = [t_out, t_err]

    def stop_project_server(self, project_id: str) -> Dict[str, Any]:
        """
        Stops a running application server process.
        """
        proc = self._active_processes.get(project_id)
        if proc:
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
            self._active_processes.pop(project_id, None)

        self._update_db_status(project_id, "STOPPED", None, None)
        return {
            "success": True,
            "project_id": project_id,
            "status": "STOPPED",
            "message": "Server stopped successfully."
        }

    def get_project_logs(self, project_id: str, tail: int = 100) -> List[str]:
        """
        Returns recent log lines for the given project.
        """
        logs = list(self._project_logs.get(project_id, []))
        return logs[-tail:] if tail > 0 else logs

    def export_project_zip(self, project_id: str, export_dir: Optional[str] = None) -> Dict[str, Any]:
        """
        Bundles project files into a .zip archive, saving it to export_dir or data/exports.
        """
        project = self.get_project(project_id)
        if not project:
            return {"success": False, "error": f"Project '{project_id}' not found."}

        target_path = project["target_path"]
        if not os.path.exists(target_path):
            return {"success": False, "error": f"Path does not exist: {target_path}"}

        out_dir = Path(export_dir) if export_dir else Path(__file__).parent.parent.parent / "data" / "exports"
        out_dir.mkdir(parents=True, exist_ok=True)

        zip_filename = f"{project['project_name'].replace(' ', '_')}_{project_id}.zip"
        zip_path = out_dir / zip_filename

        try:
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                for root, dirs, files in os.walk(target_path):
                    dirs[:] = [d for d in dirs if d not in ('.git', 'node_modules', 'venv', '__pycache__', '.pytest_cache')]
                    for f in files:
                        abs_file = os.path.join(root, f)
                        rel_file = os.path.relpath(abs_file, target_path)
                        zf.write(abs_file, rel_file)

            return {
                "success": True,
                "project_id": project_id,
                "zip_path": str(zip_path),
                "zip_filename": zip_filename,
                "size_mb": round(os.path.getsize(zip_path) / (1024 * 1024), 2)
            }
        except Exception as e:
            logger.error(f"Failed to export zip for project {project_id}: {e}")
            return {"success": False, "error": str(e)}

    def delete_project(self, project_id: str, purge_files: bool = False) -> Dict[str, Any]:
        """
        Unregisters project and optionally purges files from storage drive (D:\\, G:\\). OS drive C:\\ is strictly protected!
        """
        project = self.get_project(project_id)
        if not project:
            return {"success": False, "error": f"Project '{project_id}' not found."}

        # Stop server if running
        self.stop_project_server(project_id)

        target_path = project["target_path"]
        purged = False

        if purge_files and os.path.exists(target_path):
            # Guardrail check against OS drive deletion
            try:
                path_security.validate_write_permission(target_path)
                shutil.rmtree(target_path, ignore_errors=True)
                purged = True
                logger.info(f"Purged project files from disk for {project_id} at {target_path}")
            except PathSecurityViolation as sec_err:
                logger.warning(f"File purge blocked by path security: {sec_err}")
                return {"success": False, "error": str(sec_err)}

        conn = get_operational_db()
        try:
            conn.execute("DELETE FROM created_projects WHERE project_id = ?", (project_id,))
            conn.commit()
        finally:
            conn.close()

        return {
            "success": True,
            "project_id": project_id,
            "purged_files": purged,
            "message": f"Project '{project['project_name']}' deleted successfully."
        }

    def repair_project_environment(self, project_id: str, repair_type: str = "all") -> Dict[str, Any]:
        """
        1-Click Environment & Dependency Repair: Cleans node_modules, re-scans AST imports, and auto-installs missing packages.
        """
        project = self.get_project(project_id)
        if not project:
            return {"success": False, "error": f"Project '{project_id}' not found."}

        target_path = project["target_path"]
        from core.environment_engine import environment_engine
        res = environment_engine.repair_environment(target_path, repair_type=repair_type)
        res["project_id"] = project_id
        res["project_name"] = project["project_name"]
        return res

    def get_project_file_tree(self, project_id: str) -> Dict[str, Any]:
        """
        Recursively scans target project path and builds a hierarchical JSON file tree structure.
        """
        project = self.get_project(project_id)
        if not project:
            return {"success": False, "error": f"Project '{project_id}' not found."}

        target_path = project["target_path"]
        if not os.path.exists(target_path):
            return {"success": False, "error": f"Directory path does not exist: {target_path}"}

        path_security.validate_read_permission(target_path)

        def build_node(dir_path: str, rel_prefix: str = "") -> List[Dict[str, Any]]:
            items = []
            try:
                entries = sorted(os.listdir(dir_path))
            except Exception:
                return items

            for entry in entries:
                if entry in ('.git', 'node_modules', 'dist', 'build', '.venv', 'venv', '__pycache__', '.pytest_cache', '.sentinel_backup'):
                    continue
                
                full_entry_path = os.path.join(dir_path, entry)
                rel_path = os.path.join(rel_prefix, entry).replace("\\", "/")
                is_dir = os.path.isdir(full_entry_path)

                node = {
                    "name": entry,
                    "path": rel_path,
                    "type": "directory" if is_dir else "file",
                    "size_bytes": 0 if is_dir else os.path.getsize(full_entry_path)
                }

                if is_dir:
                    node["children"] = build_node(full_entry_path, rel_path)

                items.append(node)
            return items

        file_tree = build_node(target_path)
        return {
            "success": True,
            "project_id": project_id,
            "project_name": project["project_name"],
            "target_path": target_path,
            "tree": file_tree
        }

    def read_project_file(self, project_id: str, relative_path: str) -> Dict[str, Any]:
        """
        Reads and returns content of a single file within project workspace.
        """
        project = self.get_project(project_id)
        if not project:
            return {"success": False, "error": f"Project '{project_id}' not found."}

        target_path = project["target_path"]
        full_file_path = os.path.normpath(os.path.join(target_path, relative_path))

        # Enforce canonical path containment security check
        path_security.canonicalize_path(full_file_path, root_boundary=target_path)

        if not os.path.exists(full_file_path) or not os.path.isfile(full_file_path):
            return {"success": False, "error": f"File does not exist: {relative_path}"}

        try:
            with open(full_file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            ext = os.path.splitext(relative_path)[1].lower()
            return {
                "success": True,
                "project_id": project_id,
                "relative_path": relative_path.replace("\\", "/"),
                "full_path": full_file_path,
                "content": content,
                "extension": ext,
                "size_bytes": len(content)
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def write_project_file(self, project_id: str, relative_path: str, content: str) -> Dict[str, Any]:
        """
        Writes/edits a single file within project workspace with drive write permission security enforcement.
        """
        project = self.get_project(project_id)
        if not project:
            return {"success": False, "error": f"Project '{project_id}' not found."}

        target_path = project["target_path"]
        full_file_path = os.path.normpath(os.path.join(target_path, relative_path))

        path_security.validate_write_permission(full_file_path, root_boundary=target_path)

        try:
            os.makedirs(os.path.dirname(full_file_path), exist_ok=True)
            with open(full_file_path, "w", encoding="utf-8") as f:
                f.write(content)

            # Trigger post-write environment scan to maintain dependency integrity
            from core.environment_engine import environment_engine
            environment_engine.scan_and_install_dependencies(target_path)

            return {
                "success": True,
                "project_id": project_id,
                "relative_path": relative_path.replace("\\", "/"),
                "bytes_written": len(content)
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

projects_manager = ProjectsManager()
