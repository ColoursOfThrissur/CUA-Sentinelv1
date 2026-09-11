import asyncio
import logging
from typing import Optional

from core.queue import TaskQueue, TaskClaimResult
from core.model_manager import ModelManager, ModelAdmissionError
from core.governance import GovernanceEngine

logger = logging.getLogger(__name__)

WORKER_CAPABILITIES = [
    "file_read", "file_write", "web_search",
    "git_read", "git_commit", "memory_read", "memory_write",
]


class Scheduler:
    """
    Main execution loop. Polls BP01 for work, loads the right model,
    dispatches to the correct agent, handles preemption.
    One task runs at a time. No parallelism.
    """

    def __init__(
        self,
        task_queue: TaskQueue,
        model_manager: ModelManager,
        governance: GovernanceEngine,
        config: dict,
    ):
        self.queue = task_queue
        self.model_manager = model_manager
        self.governance = governance
        self.poll_interval = config["scheduler"]["poll_interval_sec"]
        self._running = False
        self._current_claim: Optional[TaskClaimResult] = None
        self._stop_event = asyncio.Event()

    async def run(self) -> None:
        self._running = True
        logger.info("Scheduler started.")

        while not self._stop_event.is_set():
            try:
                await self._tick()
            except Exception as e:
                logger.error(f"Scheduler tick error: {e}")

            await asyncio.sleep(self.poll_interval)

        logger.info("Scheduler stopped.")

    async def _tick(self) -> None:
        from db.connections import get_operational_db

        conn = get_operational_db()
        try:
            safe_mode = conn.execute(
                "SELECT value FROM system_state WHERE key = 'safe_mode'"
            ).fetchone()
            emergency = conn.execute(
                "SELECT value FROM system_state WHERE key = 'emergency_stop'"
            ).fetchone()
        finally:
            conn.close()

        if emergency and emergency["value"] == "true":
            logger.warning("Emergency stop active. Scheduler paused.")
            return

        if safe_mode and safe_mode["value"] == "true":
            # In safe mode only ENDPOINT tasks run
            claim = self.queue.claim_next_task(WORKER_CAPABILITIES, allowed_workflows=["ENDPOINT"])
        else:
            claim = self.queue.claim_next_task(WORKER_CAPABILITIES)

        if not claim:
            return

        self._current_claim = claim
        await self._execute_task(claim)
        self._current_claim = None

    async def _execute_task(self, claim: TaskClaimResult) -> None:
        from agents.researcher import ResearcherAgent
        from agents.synthesizer import SynthesizerAgent
        from agents.endpoint_agent import EndpointAgent
        from core.router import AgentRegistry, IntentRouter
        from api.websocket import broadcast_task_update

        # Ensure core agent capabilities are registered
        AgentRegistry.register("ENDPOINT", EndpointAgent)
        AgentRegistry.register("RESEARCHER", ResearcherAgent)
        AgentRegistry.register("RESEARCH", ResearcherAgent)
        AgentRegistry.register("SYNTHESIZER", SynthesizerAgent)
        AgentRegistry.register("FINANCE", EndpointAgent)
        AgentRegistry.register("BOOKMARK", EndpointAgent)

        logger.info(f"Executing task {claim.task_id} type={claim.workflow_type}")

        try:
            model_id = self.model_manager.get_model_for_workflow(claim.workflow_type)

            if self.model_manager.get_current_model_id() != model_id:
                self.model_manager.unload_current()
                self.model_manager.load_model(model_id, claim.context_budget)

            prompt = claim.input_payload.get("prompt", "")
            agent_cls = IntentRouter.resolve_agent(prompt, claim.workflow_type)

            agent = agent_cls(
                model_manager=self.model_manager,
                governance=self.governance,
                config=self.model_manager.__dict__,
            )

            result = await agent.run(claim)
            self.queue.release_task(claim.task_id, claim.lease_id, "COMPLETED", result_payload=result)
            await broadcast_task_update(claim.task_id, "COMPLETED", result)

        except ModelAdmissionError as e:
            logger.error(f"Model admission failed for task {claim.task_id}: {e}")
            self.queue.release_task(claim.task_id, claim.lease_id, "FAILED", error=str(e))
            await broadcast_task_update(claim.task_id, "FAILED")

        except Exception as e:
            logger.error(f"Task {claim.task_id} failed: {e}")
            self.queue.release_task(claim.task_id, claim.lease_id, "FAILED", error=str(e))
            await broadcast_task_update(claim.task_id, "FAILED")

    def request_preemption(self) -> bool:
        """Called by watchdog when a P0 task arrives and a lower priority task is running."""
        if not self._current_claim:
            return False
        if self._current_claim.priority == 0:
            return False
        return self.queue.preempt_task(self._current_claim.task_id, self._current_claim.lease_id)

    async def stop(self) -> None:
        self._stop_event.set()
        self._running = False
