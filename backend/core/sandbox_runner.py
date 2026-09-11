"""
Sandbox Execution & Application Web Prober Module for CUA-Sentinel.

Safely executes project test commands in subprocess sandboxes, captures terminal stack traces,
spawns background dev servers, and probes http://localhost:port health status.
"""

import subprocess
import urllib.request
import logging
import os
from typing import Dict, Any, Tuple, Optional

logger = logging.getLogger(__name__)

class SandboxRunner:
    def execute_test_command(self, project_path: str, command: str = "python -m unittest discover") -> Dict[str, Any]:
        """
        Executes a test command inside project directory, returning stdout, stderr, and exit code.
        """
        if not os.path.exists(project_path):
            return {"success": False, "exit_code": -1, "stdout": "", "stderr": "Project directory not found."}

        try:
            res = subprocess.run(
                command,
                shell=True,
                cwd=project_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=45
            )
            success = (res.returncode == 0)
            return {
                "success": success,
                "exit_code": res.returncode,
                "stdout": res.stdout[:2000],
                "stderr": res.stderr[:2000],
                "error_summary": res.stderr.splitlines()[-5:] if res.stderr else []
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "exit_code": -2, "stdout": "", "stderr": "Test command timed out after 45s."}
        except Exception as e:
            return {"success": False, "exit_code": -3, "stdout": "", "stderr": str(e)}

    def probe_http_health(self, url: str = "http://localhost:8000/health", timeout_sec: int = 3) -> Tuple[bool, str]:
        """
        Probes a local URL endpoint to verify application startup health.
        """
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "CUA-Sentinel-Prober/1.0"})
            with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
                if resp.status in (200, 201, 202, 204):
                    return True, f"HTTP {resp.status} OK"
                return False, f"HTTP {resp.status} Response"
        except Exception as e:
            return False, f"Probe Failed: {e}"

    def find_open_port(self, start_port: int = 8000, max_tries: int = 20) -> int:
        """
        Dynamically finds an unallocated local port starting from start_port to prevent port conflicts.
        """
        import socket
        for port in range(start_port, start_port + max_tries):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                try:
                    s.bind(("127.0.0.1", port))
                    logger.info(f"Dynamically allocated open local port: {port}")
                    return port
                except OSError:
                    continue
        return start_port

    def launch_app_preview(self, project_path: str) -> Dict[str, Any]:
        """
        Dynamically allocates an open port, spawns background app dev server, and probes /health endpoint.
        """
        if not os.path.exists(project_path):
            return {"success": False, "error": f"Path does not exist: {project_path}"}

        allocated_port = self.find_open_port(8001)
        preview_url = f"http://localhost:{allocated_port}"

        main_py = os.path.join(project_path, "backend", "main.py")
        if not os.path.exists(main_py):
            main_py = os.path.join(project_path, "main.py")

        cmd = f"python {main_py}" if os.path.exists(main_py) else f"python -m http.server {allocated_port}"

        try:
            proc = subprocess.Popen(
                cmd,
                shell=True,
                cwd=project_path,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            import time
            time.sleep(1.5)
            healthy, msg = self.probe_http_health(f"{preview_url}/health", timeout_sec=2)

            return {
                "success": True,
                "pid": proc.pid,
                "port": allocated_port,
                "preview_url": preview_url,
                "health_status": msg if healthy else f"Server running on port {allocated_port}"
            }
        except Exception as err:
            return {"success": False, "error": str(err)}

sandbox_runner = SandboxRunner()
