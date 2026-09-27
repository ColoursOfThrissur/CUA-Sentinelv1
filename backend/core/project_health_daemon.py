"""
Autonomous Project Health & Auto-Repair Daemon for CUA-Sentinel.

Periodically audits all registered projects for code health index regressions,
AST security vulnerabilities, and broken unit tests.
Features:
- Active Session Protection (skips projects being modified by user or running tasks)
- Cool-off Loop Suppression (max 1 auto-repair per 24 hours per project)
- Low Priority Task Queueing (priority=3, preemptible by user actions)
- 3-Stage Deterministic Verification Gate (AST parse + Security Audit + Test Probe)
- Automated Backup Snapshot Rollback if post-repair verification fails
"""

import os
import sys
import json
import uuid
import asyncio
import subprocess
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional

try:
    from db.connections import get_operational_db
    from core.projects_manager import projects_manager
    from core.project_backup import project_backup_manager
    from core.sandbox_runner import sandbox_runner
    from core.alert_manager import AlertManager
    from core.state_manager import utc_now
except ModuleNotFoundError:
    from backend.db.connections import get_operational_db
    from backend.core.projects_manager import projects_manager
    from backend.core.project_backup import project_backup_manager
    from backend.core.sandbox_runner import sandbox_runner
    from backend.core.alert_manager import AlertManager
    from backend.core.state_manager import utc_now

logger = logging.getLogger(__name__)

ACTIVE_SESSION_THRESHOLD_SEC = 600  # 10 minutes
COOLOFF_DURATION_HOURS = 24


class ProjectHealthDaemon:
    def __init__(self, alert_manager: Optional[AlertManager] = None, model_manager: Optional[Any] = None, task_queue: Optional[Any] = None):
        self.alert_manager = alert_manager or AlertManager()
        self.model_manager = model_manager
        self.task_queue = task_queue


    def _ensure_logs_table(self, conn) -> None:
        """Ensures project_health_daemon_logs table exists."""
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS project_health_daemon_logs (
                log_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                project_name TEXT NOT NULL,
                target_path TEXT NOT NULL,
                pre_health INTEGER,
                post_health INTEGER,
                vulnerabilities_count INTEGER,
                test_status TEXT,
                action_taken TEXT NOT NULL,
                details_json TEXT,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
            );
            """
        )
        conn.commit()

    def is_active_user_session(self, target_path: str) -> bool:
        """
        Checks if the project was modified recently by a user or has an active task running.
        Returns True if active (should be skipped by daemon).
        """
        norm_path = os.path.abspath(target_path)
        if not os.path.exists(norm_path):
            return False

        # 1. Check file mtime (modified within last 10 minutes)
        now_ts = datetime.now(timezone.utc).timestamp()
        try:
            for root, dirs, files in os.walk(norm_path):
                # Skip build/cache dirs
                dirs[:] = [d for d in dirs if d not in {"node_modules", ".venv", "venv", ".git", "dist", "build", "__pycache__", ".sentinel_backup"}]
                for f in files:
                    fp = os.path.join(root, f)
                    if os.path.exists(fp):
                        mtime = os.path.getmtime(fp)
                        if (now_ts - mtime) < ACTIVE_SESSION_THRESHOLD_SEC:
                            logger.info(f"Health Daemon: Active session detected for {norm_path} (file {f} modified recently).")
                            return True
        except Exception as err:
            logger.debug(f"mtime check notice: {err}")

        # 2. Check running or queued tasks in DB
        conn = get_operational_db()
        try:
            cursor = conn.execute(
                """
                SELECT task_id, status, input_payload FROM tasks
                WHERE status IN ('QUEUED', 'RUNNING')
                """
            )
            rows = cursor.fetchall()
            for r in rows:
                payload_raw = r["input_payload"] or "{}"
                if norm_path in payload_raw:
                    logger.info(f"Health Daemon: Active task {r['task_id']} running for project {norm_path}.")
                    return True
        except Exception:
            pass
        finally:
            conn.close()

        # 3. Check dirty git status (uncommitted user changes)
        if os.path.exists(os.path.join(norm_path, ".git")):
            try:
                res = subprocess.run("git status --porcelain", shell=True, cwd=norm_path, capture_output=True, text=True, timeout=5)
                if res.returncode == 0 and res.stdout.strip():
                    logger.info(f"Health Daemon: Uncommitted Git changes detected in {norm_path}.")
                    return True
            except Exception:
                pass

        return False

    def is_in_cooloff(self, project_id: str) -> bool:
        """
        Checks if project had an auto-repair attempt within the cool-off window (24 hours).
        """
        conn = get_operational_db()
        try:
            self._ensure_logs_table(conn)
            cutoff = (datetime.now(timezone.utc) - timedelta(hours=COOLOFF_DURATION_HOURS)).isoformat()
            cursor = conn.execute(
                """
                SELECT log_id, action_taken, created_at FROM project_health_daemon_logs
                WHERE project_id = ? AND action_taken IN ('AUTO_REPAIRED', 'ROLLED_BACK')
                AND created_at >= ?
                ORDER BY created_at DESC LIMIT 1
                """,
                (project_id, cutoff)
            )
            row = cursor.fetchone()
            if row:
                logger.info(f"Health Daemon: Project {project_id} in 24h cool-off (last action: {row['action_taken']} at {row['created_at']}).")
                return True
            return False
        except Exception as e:
            logger.error(f"Error checking cool-off status: {e}")
            return False
        finally:
            conn.close()

    def clear_cooloff(self, project_id: str) -> bool:
        """
        Clears cool-off status for a project to allow immediate manual auto-repair.
        """
        conn = get_operational_db()
        try:
            self._ensure_logs_table(conn)
            conn.execute(
                "DELETE FROM project_health_daemon_logs WHERE project_id = ? AND action_taken IN ('AUTO_REPAIRED', 'ROLLED_BACK')",
                (project_id,)
            )
            conn.commit()
            logger.info(f"Health Daemon: Cleared cool-off logs for project {project_id}.")
            return True
        except Exception as e:
            logger.error(f"Error clearing cool-off: {e}")
            return False
        finally:
            conn.close()

    def log_daemon_action(
        self,
        project_id: str,
        project_name: str,
        target_path: str,
        pre_health: int,
        post_health: int,
        vulnerabilities_count: int,
        test_status: str,
        action_taken: str,
        details: Dict[str, Any]
    ) -> str:
        """
        Records daemon audit outcome into operational.sqlite.
        """
        log_id = f"daemon_log_{uuid.uuid4().hex[:10]}"
        now = utc_now()
        conn = get_operational_db()
        try:
            self._ensure_logs_table(conn)
            conn.execute(
                """
                INSERT INTO project_health_daemon_logs (
                    log_id, project_id, project_name, target_path, pre_health, post_health,
                    vulnerabilities_count, test_status, action_taken, details_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    log_id, project_id, project_name, target_path, pre_health, post_health,
                    vulnerabilities_count, test_status, action_taken, json.dumps(details), now
                )
            )
            conn.commit()
            return log_id
        except Exception as e:
            logger.error(f"Failed to record daemon log: {e}")
            return ""
        finally:
            conn.close()

    def fetch_daemon_logs(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Retrieves recent daemon audit logs.
        """
        conn = get_operational_db()
        try:
            self._ensure_logs_table(conn)
            cursor = conn.execute(
                """
                SELECT * FROM project_health_daemon_logs
                ORDER BY created_at DESC LIMIT ?
                """,
                (limit,)
            )
            rows = cursor.fetchall()
            logs = []
            for r in rows:
                item = dict(r)
                if item.get("details_json"):
                    try:
                        item["details"] = json.loads(item["details_json"])
                    except Exception:
                        item["details"] = {}
                logs.append(item)
            return logs
        finally:
            conn.close()

    async def audit_single_project(self, project: Dict[str, Any], force_run: bool = False) -> Dict[str, Any]:
        """
        Audits a single project for AST health, security vulnerabilities, and unit test pass status.
        Triggers auto-repair if issues exist and project is eligible.
        """
        project_id = project.get("project_id", "")
        project_name = project.get("project_name", "Unknown")
        target_path = project.get("target_path", "")

        if not target_path or not os.path.exists(target_path):
            return {"status": "SKIPPED_NOT_FOUND", "project_name": project_name}

        # 0. Sentinel Self-Protection Guard
        norm_path = os.path.abspath(target_path)
        _sentinel_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        if os.path.normcase(norm_path) == os.path.normcase(_sentinel_root):
            logger.info(f"Health Daemon: Skipping CUA-Sentinel self-directory ({norm_path}).")
            return {"status": "SKIPPED_SENTINEL_SELF", "project_name": project_name}

        # 1. Active Session Check
        if not force_run and self.is_active_user_session(target_path):
            self.log_daemon_action(
                project_id, project_name, target_path, 100, 100, 0, "SKIPPED",
                "SKIPPED_ACTIVE_SESSION", {"reason": "Active user session or running task detected."}
            )
            return {"status": "SKIPPED_ACTIVE_SESSION", "project_name": project_name}

        # 2. Cool-off Check
        if not force_run and self.is_in_cooloff(project_id):
            self.log_daemon_action(
                project_id, project_name, target_path, 100, 100, 0, "SKIPPED",
                "SKIPPED_COOLOFF", {"reason": "Project is in 24-hour auto-repair cool-off."}
            )
            return {"status": "SKIPPED_COOLOFF", "project_name": project_name}

        # 3. Perform Health & Security Audit Scan
        # Run in a worker thread so the asyncio event loop is never blocked
        # (AST parsing + security checks can take several seconds on large projects)
        try:
            from agents.code_refactor_agent import CodeRefactorAgent
            scanner = CodeRefactorAgent(None, None, {})
            scan_res = await asyncio.wait_for(
                asyncio.to_thread(scanner.scan_repository, target_path),
                timeout=120.0,  # 2-minute cap; large projects won't stall the daemon loop
            ) or {}
        except asyncio.TimeoutError:
            logger.warning(f"Health Daemon: scan_repository timed out for '{project_name}' after 120s — skipping")
            return {"status": "SKIPPED_SCAN_TIMEOUT", "project_name": project_name}
        except Exception as scan_err:
            logger.error(f"Daemon scan error for {project_name}: {scan_err}")
            return {"status": "ERROR", "error": str(scan_err)}

        pre_health = scan_res.get("overall_health_score", 100)
        sec_audit = scan_res.get("security_assessment", {})
        vuln_count = sec_audit.get("total_vulnerabilities", 0)
        vuln_list = sec_audit.get("vulnerabilities", [])

        # 4. Probe Unit Test Execution (non-blocking)
        test_res = await sandbox_runner.execute_test_command_async(target_path)
        test_passed = test_res.get("success", False)
        test_status = "PASSED" if test_passed else ("NO_TESTS" if "No test" in test_res.get("stdout", "") or "No test" in test_res.get("stderr", "") else "FAILED")

        # 5. Evaluate Self-Healing Need
        needs_repair = (pre_health < 75) or (vuln_count > 0) or (test_status == "FAILED")

        if not needs_repair:
            # Update DB health scores
            self._update_project_db_scores(target_path, pre_health, sec_audit.get("security_score", 100))
            self.log_daemon_action(
                project_id, project_name, target_path, pre_health, pre_health, vuln_count,
                test_status, "NONE", {"scan_summary": "Project is healthy & passing tests."}
            )
            return {
                "status": "HEALTHY",
                "project_name": project_name,
                "health_score": pre_health,
                "vulnerabilities": vuln_count,
                "test_status": test_status
            }

        # 6. Self-Healing Enqueueing & Backup
        logger.info(f"Health Daemon: Self-healing triggered for '{project_name}' (Health={pre_health}, Vulns={vuln_count}, Tests={test_status})")

        # Create ephemeral snapshot backup before enqueuing repair
        task_id = f"daemon_task_{uuid.uuid4().hex[:8]}"
        backup_path = project_backup_manager.create_snapshot(target_path, task_id)

        # Enqueue via TaskQueue (priority 2) for unified scheduler execution
        queue = self.task_queue
        if not queue:
            from config.loader import load_system_config
            from core.queue import TaskQueue
            queue = TaskQueue(load_system_config())
            self.task_queue = queue

        enqueued_task_id = queue.enqueue(
            workflow_type="PROJECT_HEALTH_REPAIR",
            title=f"Auto-Repair: {project_name}",
            priority=2,
            input_payload={
                "project_id": project_id,
                "project_name": project_name,
                "target_path": target_path,
                "pre_health": pre_health,
                "pre_vuln": vuln_count,
                "test_status": test_status,
                "backup_path": backup_path,
                "backup_task_id": task_id,
            },
            description=f"Autonomous health repair for {project_name} (Health={pre_health}, Vulns={vuln_count})"
        )
        logger.info(f"Health Daemon: Enqueued auto-repair task {enqueued_task_id} (priority 2) for '{project_name}'.")

        return {
            "status": "REPAIR_ENQUEUED",
            "task_id": enqueued_task_id,
            "project_name": project_name,
            "pre_health": pre_health,
            "vulnerabilities": vuln_count,
            "test_status": test_status,
        }

    async def audit_all_projects(self, force_run: bool = False) -> Dict[str, Any]:
        """
        Runs health scan across all registered solutions.
        """
        projects = projects_manager.list_projects()
        logger.info(f"Health Daemon: Starting periodic audit across {len(projects)} registered project(s)...")

        results = []
        for proj in projects:
            res = await self.audit_single_project(proj, force_run=force_run)
            results.append(res)

        return {
            "status": "COMPLETED",
            "projects_audited": len(projects),
            "timestamp": utc_now(),
            "results": results
        }

    def _update_project_db_scores(self, target_path: str, health_score: int, security_score: int) -> None:
        """Updates created_projects table with audited scores."""
        conn = get_operational_db()
        try:
            norm_path = os.path.abspath(target_path)
            conn.execute(
                "UPDATE created_projects SET health_score = ?, security_score = ? WHERE target_path = ?",
                (health_score, security_score, norm_path)
            )
            conn.commit()
        except Exception as e:
            logger.warning(f"Failed to update project scores in DB: {e}")
        finally:
            conn.close()

    def _update_task_db_status(self, task_id: str, status: str) -> None:
        """Updates tasks table status."""
        conn = get_operational_db()
        try:
            now_iso = utc_now()
            conn.execute(
                "UPDATE tasks SET status = ?, updated_at = ? WHERE task_id = ?",
                (status, now_iso, task_id)
            )
            conn.commit()
        except Exception as e:
            logger.warning(f"Failed to update task status in DB: {e}")
        finally:
            conn.close()

    async def trigger_autonomous_repair(self, project_path: str, error_context: str, source: str = "RUNTIME_EXCEPTION") -> Dict[str, Any]:
        """
        Zero-Touch Auto-Healing Trigger:
        Inspects runtime exception / server crash error_context.
        1. If error is missing library (ModuleNotFoundError / Failed to resolve import), executes auto-install.
        2. If error is code/syntax break, enqueues background self-healing refactor task.
        """
        if not os.path.exists(project_path):
            return {"success": False, "error": f"Invalid path: {project_path}"}

        logger.info(f"Health Daemon: Zero-touch trigger received from {source} for {project_path}.")

        # Check missing library package pattern
        from core.environment_engine import environment_engine
        pkg_check = environment_engine.parse_missing_package_from_error(error_context)
        if pkg_check.get("missing"):
            pkg_name = pkg_check["package"]
            ecosystem = pkg_check["ecosystem"]
            logger.info(f"Health Daemon: Auto-repairing missing {ecosystem} package '{pkg_name}'...")
            inst_res = environment_engine.auto_install_missing_package(project_path, pkg_name, ecosystem=ecosystem)
            if inst_res.get("success"):
                await self.alert_manager.dispatch_alert(
                    title=f"Auto-Installed Missing Package: {pkg_name}",
                    message=f"Sentinel automatically installed missing {ecosystem} package '{pkg_name}' into project environment.",
                    severity="INFO",
                    category="AUTONOMY"
                )
                return {
                    "status": "AUTO_INSTALLED_PACKAGE",
                    "success": True,
                    "package": pkg_name,
                    "ecosystem": ecosystem,
                    "log": inst_res.get("log", "Installation completed successfully.")
                }
            else:
                return {
                    "status": "PACKAGE_INSTALL_FAILED",
                    "success": False,
                    "package": pkg_name,
                    "ecosystem": ecosystem,
                    "log": inst_res.get("log", "Package installation failed.")
                }

        # Otherwise enqueue background self-healing refactor task
        task_id = f"auto_heal_{uuid.uuid4().hex[:8]}"
        conn = get_operational_db()
        try:
            conn.execute(
                """
                INSERT INTO tasks (
                    task_id, workflow_type, status, title, input_payload, priority, context_budget, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    "REFACTOR",
                    "QUEUED",
                    f"Auto-Heal: {source} ({os.path.basename(project_path)})",
                    json.dumps({
                        "project_path": project_path,
                        "goal_instruction": f"Zero-Touch Auto-Repair triggered by {source}:\n{error_context[:800]}\nFix all errors while preserving project contracts.",
                        "approved_features": ["Auto-Healing Repair"],
                    }),
                    3,  # Priority 3 (Background AI task)
                    16384,
                    utc_now(),
                    utc_now()
                )
            )
            conn.commit()
            logger.info(f"Health Daemon: Enqueued zero-touch auto-healing task {task_id}.")
            return {"status": "AUTO_HEAL_QUEUED", "task_id": task_id}
        except Exception as e:
            logger.error(f"Failed to enqueue auto-heal task: {e}")
            return {"status": "ERROR", "error": str(e)}
        finally:
            conn.close()

    def audit_dual_stack_health(self, project_path: str) -> Dict[str, Any]:
        """
        Simultaneous Pre-Flight Diagnostic Runner for Backend (FastAPI/Python) and Frontend (React/Vite).
        Returns structured health status for both stacks on server startup.
        """
        backend_status = {"healthy": True, "issues": [], "syntax_ok": True}
        frontend_status = {"healthy": True, "issues": [], "package_ok": True}

        if not os.path.exists(project_path):
            return {"backend": {"healthy": False, "issues": ["Path not found"]}, "frontend": {"healthy": False, "issues": ["Path not found"]}}

        # 1. Backend Probe: Python Syntax & FastAPI main.py check
        main_py = os.path.join(project_path, "backend", "main.py")
        if not os.path.exists(main_py):
            main_py = os.path.join(project_path, "main.py")

        if os.path.exists(main_py):
            try:
                import ast
                ast.parse(open(main_py, encoding="utf-8", errors="ignore").read())
            except SyntaxError as syn_err:
                backend_status["healthy"] = False
                backend_status["syntax_ok"] = False
                backend_status["issues"].append(f"Python SyntaxError line {syn_err.lineno} in {os.path.basename(main_py)}: {syn_err.msg}")
            except Exception as py_err:
                backend_status["healthy"] = False
                backend_status["issues"].append(f"Backend read error: {py_err}")

        # 2. Frontend Probe: package.json & Vite TypeScript check
        pkg_json = os.path.join(project_path, "package.json")
        if os.path.exists(pkg_json):
            try:
                pkg_data = json.load(open(pkg_json, encoding="utf-8"))
                deps = {**pkg_data.get("dependencies", {}), **pkg_data.get("devDependencies", {})}
                if "react" in deps and "react-dom" not in deps:
                    frontend_status["healthy"] = False
                    frontend_status["package_ok"] = False
                    frontend_status["issues"].append("Missing 'react-dom' dependency in package.json")
            except Exception as pkg_err:
                frontend_status["healthy"] = False
                frontend_status["issues"].append(f"Invalid package.json: {pkg_err}")

        return {
            "project_name": os.path.basename(os.path.abspath(project_path)),
            "backend": backend_status,
            "frontend": frontend_status,
            "timestamp": utc_now()
        }


project_health_daemon = ProjectHealthDaemon()

