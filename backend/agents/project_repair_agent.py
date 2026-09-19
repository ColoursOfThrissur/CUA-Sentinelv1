import json
import logging
import os
from typing import Dict, Any

from agents.base_agent import BaseAgent
from agents.code_refactor_agent import CodeRefactorAgent
from core.queue import TaskClaimResult
from core.project_backup import project_backup_manager
from core.code_health_evaluator import code_health_evaluator
from core.sandbox_runner import sandbox_runner
from core.alert_manager import AlertManager
from core.project_health_daemon import project_health_daemon

logger = logging.getLogger(__name__)


class ProjectRepairAgent(BaseAgent):
    """
    Autonomous Project Repair Agent.
    Runs inside the unified TaskQueue (priority 2) instead of CronEngine's coroutine.
    Executes CodeRefactorAgent repair, evaluates health & test status asynchronously,
    and rolls back to snapshot if health degrades or tests fail.
    """

    def __init__(self, model_manager, governance, config):
        super().__init__(model_manager, governance, config)
        self.alert_manager = AlertManager()

    async def run(self, claim: TaskClaimResult) -> Dict[str, Any]:
        task_id = claim.task_id
        payload = claim.input_payload or {}

        project_id = payload.get("project_id", "")
        project_name = payload.get("project_name", "Unknown Project")
        target_path = payload.get("target_path", "")
        pre_health = payload.get("pre_health", 70)
        pre_vuln = payload.get("pre_vuln", 0)
        test_status = payload.get("test_status", "UNKNOWN")
        backup_path = payload.get("backup_path")
        backup_task_id = payload.get("backup_task_id", task_id)

        step_id = self.create_step(task_id, 0, "HEALTH_REPAIR", f"Autonomous repair for {project_name}")
        self.update_step_status(step_id, "RUNNING")

        goal_instruction = payload.get("goal_instruction") or (
            f"Autonomous Auto-Repair for '{project_name}'.\n"
            f"Findings:\n"
            f"- Code Health Index: {pre_health}/100\n"
            f"- Vulnerabilities: {pre_vuln}\n"
            f"- Test Suite Status: {test_status}\n\n"
            f"Objective: Fix security risks, resolve AST quality issues, and ensure all tests pass cleanly."
        )

        try:
            # 1. Run refactoring through CodeRefactorAgent
            refactor_agent = CodeRefactorAgent(self.model_manager, self.governance, self.config)
            refactor_claim = TaskClaimResult(
                task_id=task_id,
                lease_id=claim.lease_id,
                lease_generation=claim.lease_generation,
                workflow_type="CODE_REFACTOR",
                priority=claim.priority,
                context_budget=claim.context_budget,
                input_payload={
                    "project_path": target_path,
                    "goal_instruction": goal_instruction,
                },
            )

            repair_res = await refactor_agent.run(refactor_claim)
            written_files = repair_res.get("files_written", [])

            # 2. Post-Repair Verification Gate (non-blocking)
            post_scan = refactor_agent.scan_repository(target_path)
            post_health = post_scan.get("overall_health_score", 0)
            post_vuln = post_scan.get("security_assessment", {}).get("total_vulnerabilities", 0)

            post_test_res = await sandbox_runner.execute_test_command_async(target_path)
            post_test_passed = post_test_res.get("success", False)

            verification_passed = (
                (post_health >= pre_health)
                and (post_vuln <= pre_vuln)
                and (not (test_status == "FAILED" and not post_test_passed))
                and (len(written_files) > 0)
            )

            if not verification_passed:
                logger.warning(
                    f"ProjectRepairAgent: Post-repair verification failed for '{project_name}' "
                    f"(health: {pre_health} -> {post_health}, vulns: {pre_vuln} -> {post_vuln}, tests passed: {post_test_passed}). "
                    f"Rolling back to snapshot {backup_task_id}..."
                )
                if backup_path:
                    project_backup_manager.restore_snapshot(target_path, backup_task_id)

                project_health_daemon.log_daemon_action(
                    project_id, project_name, target_path, pre_health, post_health, pre_vuln,
                    "FAILED", "ROLLED_BACK", {
                        "reason": "Post-repair verification failed health threshold or tests.",
                        "written_files": written_files,
                        "backup_restored": bool(backup_path),
                    }
                )

                await self.alert_manager.dispatch_alert(
                    title=f"Auto-Repair Rolled Back: {project_name}",
                    message=f"Autonomous repair for '{project_name}' failed post-verification tests. Restored snapshot cleanly.",
                    severity="WARNING",
                    category="AUTONOMY",
                )

                self.update_step_status(
                    step_id, "FAILED",
                    error="Verification checks failed. Snapshot restored."
                )

                return {
                    "status": "ROLLED_BACK",
                    "project_name": project_name,
                    "pre_health": pre_health,
                    "post_health": post_health,
                    "reason": "Verification failed",
                }

            # 3. Verification Succeeded
            sec_score = post_scan.get("security_assessment", {}).get("security_score", 100)
            project_health_daemon._update_project_db_scores(target_path, post_health, sec_score)

            project_health_daemon.log_daemon_action(
                project_id, project_name, target_path, pre_health, post_health, post_vuln,
                "PASSED" if post_test_passed else "NO_TESTS", "AUTO_REPAIRED", {
                    "files_updated": len(written_files),
                    "pre_health": pre_health,
                    "post_health": post_health,
                }
            )

            await self.alert_manager.dispatch_alert(
                title=f"Project Auto-Repaired: {project_name}",
                message=f"Successfully repaired '{project_name}'! Health: {pre_health} → {post_health}. {len(written_files)} file(s) updated.",
                severity="INFO",
                category="AUTONOMY",
            )

            self.update_step_status(
                step_id, "COMPLETED",
                result_payload={"files_updated": len(written_files), "post_health": post_health}
            )

            return {
                "status": "AUTO_REPAIRED",
                "project_name": project_name,
                "pre_health": pre_health,
                "post_health": post_health,
                "files_updated": len(written_files),
            }

        except Exception as err:
            logger.error(f"ProjectRepairAgent: Error during repair for {project_name}: {err}")
            if backup_path:
                project_backup_manager.restore_snapshot(target_path, backup_task_id)
            self.update_step_status(step_id, "FAILED", error=str(err))
            return {"status": "ERROR", "error": str(err)}
