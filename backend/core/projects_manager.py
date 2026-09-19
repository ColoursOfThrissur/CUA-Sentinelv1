"""
Projects Registry & Live App Process Manager for CUA-Sentinel.

Provides database persistence for created/scaffolded/refactored projects, dynamic server process execution,
real-time stdout/stderr log streaming, zip archiving, and safe disk deletion.
"""

import os
import re
import shutil
import uuid
import zipfile
import subprocess
import threading
import collections
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path
import time

ANSI_ESCAPE_REGEX = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

def clean_terminal_log_line(line: str) -> str:
    """Strips ANSI escape codes and fixes UTF-8/CP1252 character encoding glitches."""
    if not line:
        return ""
    clean = ANSI_ESCAPE_REGEX.sub("", line)
    clean = clean.replace("âžœ", "➜").replace("âœ", "✓").replace("â€", "—")
    return clean.rstrip()


def kill_process_tree(pid: int) -> None:
    """Forcefully kills a process and all its child processes across Windows & Linux/macOS."""
    if not pid or pid <= 0:
        return
    try:
        if os.name == 'nt':
            subprocess.run(f"taskkill /F /T /PID {pid}", shell=True, capture_output=True, timeout=5)
        else:
            import signal
            os.killpg(os.getpgid(pid), signal.SIGKILL)
    except Exception as e:
        logger.debug(f"Failed to kill process tree for PID {pid}: {e}")


def kill_process_on_port(port: int) -> None:
    """Scans netstat for any process listening on target port and forces termination on Windows."""
    if not port or port <= 0:
        return
    try:
        if os.name == 'nt':
            cmd = f'netstat -aon | findstr LISTENING | findstr :{port}'
            res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=5)
            if res.stdout:
                for line in res.stdout.strip().splitlines():
                    parts = line.split()
                    if parts and len(parts) >= 5:
                        local_addr = parts[1]
                        pid_str = parts[-1]
                        if local_addr.endswith(f":{port}") and pid_str.isdigit():
                            pid = int(pid_str)
                            if pid > 0 and pid != os.getpid():
                                logger.info(f"Port Netstat Scavenger: Killing PID {pid} occupying port {port}")
                                kill_process_tree(pid)
    except Exception as e:
        logger.debug(f"kill_process_on_port error for port {port}: {e}")


def _ensure_columns(conn) -> None:
    """Ensures backend_port and frontend_port columns exist in created_projects table."""
    try:
        cursor = conn.execute("PRAGMA table_info(created_projects)")
        columns = [row[1] for row in cursor.fetchall()]
        if "backend_port" not in columns:
            conn.execute("ALTER TABLE created_projects ADD COLUMN backend_port INTEGER")
        if "frontend_port" not in columns:
            conn.execute("ALTER TABLE created_projects ADD COLUMN frontend_port INTEGER")
        conn.commit()
    except Exception as e:
        logger.warning(f"Error ensuring DB columns in created_projects: {e}")



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
        self._active_processes: Dict[str, List[subprocess.Popen]] = collections.defaultdict(list)
        self._project_logs: Dict[str, collections.deque] = collections.defaultdict(lambda: collections.deque(maxlen=MAX_LOG_LINES))
        self._log_threads: Dict[str, List[threading.Thread]] = collections.defaultdict(list)

    def _allocate_assigned_ports(self, conn) -> tuple:
        """Allocates next available collision-free backend_port (8001+) and frontend_port (5174+)."""
        try:
            cursor = conn.execute("SELECT MAX(backend_port), MAX(frontend_port) FROM created_projects")
            row = cursor.fetchone()
            max_backend = row[0] if row and row[0] else 8000
            max_frontend = row[1] if row and row[1] else 5173

            backend_port = max(max_backend + 1, 8001)
            frontend_port = max(max_frontend + 1, 5174)

            backend_port = sandbox_runner.find_open_port(backend_port)
            frontend_port = sandbox_runner.find_open_port(frontend_port)

            if frontend_port == backend_port:
                frontend_port = sandbox_runner.find_open_port(backend_port + 1)

            return backend_port, frontend_port
        except Exception as e:
            logger.warning(f"Failed to allocate dynamic ports: {e}")
            return 8001, 5174

    def register_project(
        self,
        project_name: str,
        target_path: str,
        tech_stack: str,
        ui_style: str = "Glassmorphism",
        blueprint_filename: Optional[str] = None,
        health_score: int = 100,
        security_score: int = 100,
        backend_port: Optional[int] = None,
        frontend_port: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Registers a created/scaffolded/refactored solution in the persistent database with assigned ports.
        """
        norm_path = os.path.abspath(target_path)

        # ── Sentinel Self-Protection Guard ────────────────────────────────────────
        _sentinel_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        if os.path.normcase(norm_path) == os.path.normcase(_sentinel_root):
            logger.warning(
                "Sentinel Self-Protection: Blocked attempt to register the CUA-Sentinel "
                "installation directory as a managed project. Registration skipped."
            )
            return {
                "project_id": "sentinel_self",
                "project_name": project_name,
                "target_path": norm_path,
                "tech_stack": tech_stack,
                "status": "PROTECTED",
                "_sentinel_protected": True,
            }
        # ─────────────────────────────────────────────────────────────────────────

        project_id = f"proj_{uuid.uuid4().hex[:10]}"

        conn = get_operational_db()
        try:
            _ensure_columns(conn)

            if not backend_port or not frontend_port:
                alloc_b, alloc_f = self._allocate_assigned_ports(conn)
                backend_port = backend_port or alloc_b
                frontend_port = frontend_port or alloc_f

            # Check if path already registered
            cursor = conn.execute("SELECT * FROM created_projects WHERE target_path = ?", (norm_path,))
            existing = cursor.fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE created_projects
                    SET project_name = ?, tech_stack = ?, ui_style = ?, blueprint_filename = ?,
                        health_score = ?, security_score = ?, backend_port = ?, frontend_port = ?
                    WHERE target_path = ?
                    """,
                    (project_name, tech_stack, ui_style, blueprint_filename, health_score, security_score, backend_port, frontend_port, norm_path)
                )
                conn.commit()
                return self.get_project_by_path(norm_path)

            conn.execute(
                """
                INSERT INTO created_projects (
                    project_id, project_name, target_path, tech_stack, ui_style,
                    blueprint_filename, health_score, security_score, status,
                    backend_port, frontend_port
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'STOPPED', ?, ?)
                """,
                (project_id, project_name, norm_path, tech_stack, ui_style, blueprint_filename, health_score, security_score, backend_port, frontend_port)
            )
            conn.commit()
            logger.info(f"Registered project '{project_name}' ({project_id}) at path: {norm_path} (Backend: {backend_port}, Frontend: {frontend_port})")
            return self.get_project(project_id)
        finally:
            conn.close()

    def get_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        conn = get_operational_db()
        try:
            _ensure_columns(conn)
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
            _ensure_columns(conn)
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
        Automatically performs a disk sweep on project roots (e.g. G:\\Projects, D:\\Projects) to discover unregistered projects.
        """
        # Disk auto-discovery sweep
        search_roots = ["G:\\Projects", "D:\\Projects", "C:\\Projects"]
        for root_dir in search_roots:
            if os.path.exists(root_dir):
                try:
                    for entry in os.listdir(root_dir):
                        full_entry = os.path.join(root_dir, entry)
                        if os.path.isdir(full_entry) and not entry.startswith(('.', '$')):
                            has_pkg = os.path.exists(os.path.join(full_entry, "package.json"))
                            has_main = os.path.exists(os.path.join(full_entry, "backend", "main.py"))
                            has_html = os.path.exists(os.path.join(full_entry, "index.html"))
                            if has_pkg or has_main or has_html:
                                conn_disc = get_operational_db()
                                try:
                                    _ensure_columns(conn_disc)
                                    norm_p = os.path.abspath(full_entry)
                                    cur = conn_disc.execute("SELECT 1 FROM created_projects WHERE target_path = ?", (norm_p,))
                                    if not cur.fetchone():
                                        self.register_project(
                                            project_name=entry,
                                            target_path=norm_p,
                                            tech_stack="FastAPI + React",
                                        )
                                        logger.info(f"ProjectsManager: Auto-discovered and registered project on disk: {norm_p}")
                                finally:
                                    conn_disc.close()
                except Exception as disc_err:
                    logger.debug(f"Disk discovery error on {root_dir}: {disc_err}")

        conn = get_operational_db()
        try:
            _ensure_columns(conn)
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
            procs = self._active_processes.get(p_id, [])
            running_procs = [p for p in procs if p.poll() is None]
            if running_procs:
                p_dict["status"] = "RUNNING"
                p_dict["active_pid"] = running_procs[0].pid
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
        Starts background dev servers (backend & frontend) for the project with terminal log streaming.
        """
        project = self.get_project(project_id)
        if not project:
            return {"success": False, "error": f"Project '{project_id}' not found."}

        target_path = project["target_path"]
        if not os.path.exists(target_path):
            return {"success": False, "error": f"Project directory does not exist: {target_path}"}

        # Check if already running
        existing_procs = [p for p in self._active_processes.get(project_id, []) if p.poll() is None]
        if existing_procs:
            active_port = project.get("active_port") or project.get("frontend_port") or project.get("backend_port") or 8001
            return {
                "success": True,
                "project_id": project_id,
                "status": "RUNNING",
                "port": active_port,
                "pid": existing_procs[0].pid,
                "preview_url": f"http://localhost:{active_port}",
                "message": "Server is already running."
            }

        # Get or allocate ports
        backend_port = project.get("backend_port") or 8001
        frontend_port = project.get("frontend_port") or 5174

        # Netstat Scavenger: Ensure ports are completely freed before launching!
        kill_process_on_port(backend_port)
        kill_process_on_port(frontend_port)

        # Pre-flight environment check & dependency auto-install
        try:
            from core.environment_engine import environment_engine
            environment_engine.scan_and_install_dependencies(target_path)
            environment_engine.ensure_env_defaults(target_path)
        except Exception as env_err:
            logger.warning(f"Pre-flight environment check warning for {project_id}: {env_err}")

        # Setup persistent server log file
        log_file_path = os.path.join(target_path, "sentinel_server.log")
        try:
            with open(log_file_path, "a", encoding="utf-8") as f:
                f.write(f"\n--- SERVER LAUNCH AT {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
        except Exception:
            pass

        package_json = os.path.join(target_path, "package.json")
        node_modules = os.path.join(target_path, "node_modules")
        backend_main = os.path.join(target_path, "backend", "main.py")
        root_main = os.path.join(target_path, "main.py")
        py_exec = environment_engine.get_python_venv_executables(target_path)["python"]

        spawned_procs: List[subprocess.Popen] = []
        commands_run: List[str] = []
        primary_port = frontend_port if os.path.exists(package_json) else backend_port

        creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0

        # 1. Spawn FastAPI Backend if backend/main.py or main.py exists
        if os.path.exists(backend_main):
            b_cmd = f'"{py_exec}" "{backend_main}"'
        elif os.path.exists(root_main):
            b_cmd = f'"{py_exec}" "{root_main}"'
        else:
            b_cmd = None

        if b_cmd:
            logger.info(f"Launching FastAPI Backend for {project_id} on port {backend_port}: {b_cmd}")
            try:
                b_proc = subprocess.Popen(
                    b_cmd,
                    shell=True,
                    cwd=target_path,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                    creationflags=creation_flags
                )
                spawned_procs.append(b_proc)
                commands_run.append(b_cmd)
                self._start_log_streamer(project_id, b_proc, "BACKEND", log_file_path)
            except Exception as e:
                logger.error(f"Failed to spawn backend for {project_id}: {e}")

        # 2. Spawn React/Vite Frontend if package.json exists
        if os.path.exists(package_json) and os.path.exists(node_modules):
            f_cmd = f"npx vite --port {frontend_port} --host"
            logger.info(f"Launching Vite Frontend for {project_id} on port {frontend_port}: {f_cmd}")
            try:
                f_proc = subprocess.Popen(
                    f_cmd,
                    shell=True,
                    cwd=target_path,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                    creationflags=creation_flags
                )
                spawned_procs.append(f_proc)
                commands_run.append(f_cmd)
                self._start_log_streamer(project_id, f_proc, "FRONTEND", log_file_path)
            except Exception as e:
                logger.error(f"Failed to spawn frontend for {project_id}: {e}")
        elif not spawned_procs:
            # Fallback static server
            s_cmd = f'"{py_exec}" -m http.server {primary_port}'
            logger.info(f"Launching Static HTTP server for {project_id} on port {primary_port}: {s_cmd}")
            try:
                s_proc = subprocess.Popen(
                    s_cmd,
                    shell=True,
                    cwd=target_path,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1
                )
                spawned_procs.append(s_proc)
                commands_run.append(s_cmd)
                self._start_log_streamer(project_id, s_proc, "STATIC", log_file_path)
            except Exception as e:
                logger.error(f"Failed to spawn static server for {project_id}: {e}")

        if not spawned_procs:
            return {"success": False, "error": "No processes could be spawned."}

        self._active_processes[project_id] = spawned_procs
        main_pid = spawned_procs[0].pid
        self._update_db_status(project_id, "RUNNING", primary_port, main_pid)

        # Quick startup health diagnostic check (wait 1.5s to see if process immediately crashes)
        time.sleep(1.5)
        crashed = [p for p in spawned_procs if p.poll() is not None and p.poll() != 0]
        if crashed:
            startup_logs = self.get_project_logs(project_id, tail=20)
            err_msg = "Server crashed immediately after launch:\n" + "\n".join(startup_logs)
            logger.error(f"Startup crash detected for {project_id}: {err_msg}")
            return {
                "success": False,
                "error": err_msg,
                "project_id": project_id,
                "startup_logs": startup_logs
            }

        preview_url = f"http://localhost:{primary_port}"
        return {
            "success": True,
            "project_id": project_id,
            "status": "RUNNING",
            "port": primary_port,
            "backend_port": backend_port,
            "frontend_port": frontend_port,
            "pid": main_pid,
            "preview_url": preview_url,
            "commands": commands_run
        }

    def _start_log_streamer(self, project_id: str, proc: subprocess.Popen, prefix: str, log_file_path: str) -> None:
        def stream_output(pipe, tag: str):
            try:
                for line in iter(pipe.readline, ''):
                    if not line:
                        break
                    sanitized = clean_terminal_log_line(line)
                    if sanitized:
                        clean_line = f"[{prefix}:{tag}] {sanitized}"
                        self._project_logs[project_id].append(clean_line)
                        try:
                            with open(log_file_path, "a", encoding="utf-8") as f:
                                f.write(clean_line + "\n")
                        except Exception:
                            pass
            except Exception:
                pass
            finally:
                try:
                    pipe.close()
                except Exception:
                    pass

        t_out = threading.Thread(target=stream_output, args=(proc.stdout, "STDOUT"), daemon=True)
        t_err = threading.Thread(target=stream_output, args=(proc.stderr, "STDERR"), daemon=True)
        t_out.start()
        t_err.start()
        self._log_threads[project_id].extend([t_out, t_err])

    def stop_project_server(self, project_id: str) -> Dict[str, Any]:
        """
        Stops all running application server processes for project and scavenges ports.
        """
        project = self.get_project(project_id)
        b_port = project.get("backend_port") if project else None
        f_port = project.get("frontend_port") if project else None
        a_port = project.get("active_port") if project else None

        procs = self._active_processes.pop(project_id, [])
        for proc in procs:
            if proc.poll() is None:
                kill_process_tree(proc.pid)

        # Force scavenge ports
        for port in (b_port, f_port, a_port):
            if port:
                kill_process_on_port(port)

        self._update_db_status(project_id, "STOPPED", None, None)
        return {
            "success": True,
            "project_id": project_id,
            "status": "STOPPED",
            "message": "Server stopped successfully and ports freed."
        }

    def get_project_logs(self, project_id: str, tail: int = 100) -> List[str]:
        """
        Returns recent log lines for the given project with ANSI escape codes stripped.
        """
        logs = list(self._project_logs.get(project_id, []))
        if not logs:
            project = self.get_project(project_id)
            if project and project.get("target_path"):
                log_file = os.path.join(project["target_path"], "sentinel_server.log")
                if os.path.exists(log_file):
                    try:
                        with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                            file_lines = f.readlines()
                            logs = [clean_terminal_log_line(line) for line in file_lines]
                    except Exception:
                        pass
        raw_tail = logs[-tail:] if tail > 0 else logs
        return [clean_terminal_log_line(line) for line in raw_tail]



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

        # ── Sentinel Self-Protection Guard ────────────────────────────────────────
        # Never allow deletion/purge of the CUA-Sentinel installation directory.
        target_path_check = os.path.abspath(project.get("target_path", ""))
        _sentinel_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        if os.path.normcase(target_path_check) == os.path.normcase(_sentinel_root):
            logger.error(
                "Sentinel Self-Protection: BLOCKED attempt to delete CUA-Sentinel itself "
                f"(project_id={project_id}). This operation is permanently forbidden."
            )
            return {
                "success": False,
                "error": "SENTINEL_PROTECTED: Cannot delete or purge the CUA-Sentinel installation directory. "
                         "This project is protected from accidental deletion."
            }
        # ─────────────────────────────────────────────────────────────────────────

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
