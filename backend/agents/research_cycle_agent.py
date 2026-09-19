import logging
from typing import Dict, Any
from agents.base_agent import BaseAgent
from core.queue import TaskClaimResult
from core.improvement_scout import improvement_scout

logger = logging.getLogger(__name__)


class ResearchCycleAgent(BaseAgent):
    """
    Handles RESEARCH_CYCLE tasks (priority 3).
    Executes ImprovementScout research cycles, analyzing repository packages
    and drafting structured proposals for human-in-the-loop review.
    """

    async def run(self, claim: TaskClaimResult) -> Dict[str, Any]:
        task_id = claim.task_id
        payload = claim.input_payload or {}
        project_id = payload.get("project_id", "")
        project_name = payload.get("project_name", "Unknown Project")
        target_path = payload.get("target_path", "")

        step_id = self.create_step(task_id, 0, "RESEARCH_CYCLE", f"ImprovementScout cycle for {project_name}")
        self.update_step_status(step_id, "RUNNING")

        try:
            proposals = await improvement_scout.run_research_cycle(project_id, project_name, target_path)
            self.update_step_status(step_id, "COMPLETED", {
                "proposals_count": len(proposals),
                "proposals": proposals,
            })
            return {
                "status": "SUCCESS",
                "project_name": project_name,
                "proposals_created": len(proposals),
            }
        except Exception as e:
            logger.error(f"ResearchCycleAgent error for {project_name}: {e}")
            self.update_step_status(step_id, "FAILED", error=str(e))
            return {"status": "ERROR", "error": str(e)}
