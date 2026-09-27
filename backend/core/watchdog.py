import asyncio
import logging
from datetime import datetime, timezone
from collections import defaultdict

from core.queue import TaskQueue
from core.model_manager import ModelManager

logger = logging.getLogger(__name__)


class Watchdog:
    """
    Runs independently of the scheduler.
    Monitors lease expiry, component health, and triggers safe mode
    when failure thresholds are breached.
    Uses circuit breakers to prevent infinite restart loops.
    """

    def __init__(self, config: dict, scheduler, model_manager: ModelManager):
        self.config = config["watchdog"]
        self.scheduler = scheduler
        self.model_manager = model_manager
        self._stop_event = asyncio.Event()
        self._restart_counts: dict = defaultdict(list)
        self._max_restarts = self.config["component_restart_max"]
        self._restart_window = self.config["component_restart_window_sec"]
        self._cooldown = self.config["circuit_breaker_cooldown_sec"]

    async def run(self) -> None:
        logger.info("Watchdog started.")
        while not self._stop_event.is_set():
            try:
                await self._check_leases()
                await self._check_ollama_health()
                await self._check_safe_mode_conditions()
                await self._check_preemption()
            except Exception as e:
                logger.error(f"Watchdog error: {e}")

            await asyncio.sleep(self.config["heartbeat_check_interval_sec"])

        logger.info("Watchdog stopped.")

    async def _check_preemption(self) -> None:
        claim = self.scheduler._current_claim
        if not claim or claim.priority <= 0:
            return

        # Generalized preemption: if any waiting task has strictly higher priority (lower int)
        target_priority = claim.priority - 1
        if self.scheduler.queue.has_waiting_task_at_or_above_priority(target_priority):
            logger.info(
                f"Watchdog: Preemption condition met. Task {claim.task_id} (priority {claim.priority}) "
                f"preempting for incoming task with priority <= {target_priority}."
            )
            self.scheduler.request_preemption()

    async def _check_leases(self) -> None:
        expired = self.scheduler.queue.expire_stale_leases()
        if expired > 0:
            logger.warning(f"Watchdog recovered {expired} stale lease(s)")

    async def _check_ollama_health(self) -> None:
        import httpx
        ollama_url = self.model_manager.ollama_url
        try:
            with httpx.Client(timeout=5) as client:
                resp = client.get(f"{ollama_url}/api/tags")
                resp.raise_for_status()
        except Exception as e:
            logger.error(f"Ollama health check failed: {e}")
            self._record_failure("ollama")
            if self._should_trigger_safe_mode("ollama"):
                self.scheduler.governance.enter_safe_mode("Repeated Ollama health check failures")

    async def _check_safe_mode_conditions(self) -> None:
        import psutil
        ram = psutil.virtual_memory()
        ram_used_pct = ram.percent
        watchdog_cfg = self.config.get("watchdog", {}) if isinstance(self.config, dict) else {}
        threshold = watchdog_cfg.get("ram_critical_pct", 98.5)
        if ram_used_pct > threshold and ram.available < 250 * 1024 * 1024:
            logger.warning(f"RAM pressure critical: {ram_used_pct:.1f}% used ({ram.available / (1024*1024):.0f}MB available)")
            self.scheduler.governance.enter_safe_mode(f"Excessive RAM pressure: {ram_used_pct:.1f}%")
        elif ram_used_pct < (threshold - 2.0) and self.scheduler.governance.is_safe_mode():
            logger.info(f"RAM pressure normalized: {ram_used_pct:.1f}% used. Auto-recovering from Safe Mode.")
            self.scheduler.governance.exit_safe_mode()


    def _record_failure(self, component: str) -> None:
        now = datetime.now(timezone.utc).timestamp()
        self._restart_counts[component].append(now)
        window_start = now - self._restart_window
        self._restart_counts[component] = [
            t for t in self._restart_counts[component] if t > window_start
        ]

    def _should_trigger_safe_mode(self, component: str) -> bool:
        return len(self._restart_counts[component]) >= self._max_restarts

    async def stop(self) -> None:
        self._stop_event.set()
