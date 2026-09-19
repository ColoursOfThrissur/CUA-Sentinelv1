import asyncio
import logging
from datetime import datetime, timezone
from tools.finance_tools import FinanceTools
from core.alert_manager import AlertManager
from core.gmail_triage import GmailTriageEngine

logger = logging.getLogger(__name__)


class CronEngine:
    """
    24/7 Autonomous Cron Scheduler Engine.
    Executes background periodic tasks following the strict non-blocking rule:
    - Calls cheap, LLM-free work directly (finance alerts, Gmail triage)
    - Enqueues heavy agent work via task_queue.enqueue(...) and returns immediately.
      Never instantiates an agent and calls .run() itself.
    """

    def __init__(self, config: dict, task_queue=None):
        self.config = config
        self.task_queue = task_queue
        self.finance_tools = FinanceTools()
        self.alert_manager = AlertManager()
        self.gmail_triage = GmailTriageEngine(self.alert_manager)
        self._running = False
        self._task: asyncio.Task = None

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._cron_loop())
        logger.info("24/7 Autonomous Cron Engine started.")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
        await self.finance_tools.close()
        await self.alert_manager.close()
        logger.info("24/7 Autonomous Cron Engine stopped.")

    async def _cron_loop(self) -> None:
        # Wait 15 seconds after system startup before first cron tick
        await asyncio.sleep(15)
        last_finance_tick = 0
        last_gmail_tick = 0
        last_health_daemon_tick = 0
        last_daily_tick_date = ""
        last_research_tick_date = ""

        while self._running:
            try:
                now = datetime.now(timezone.utc)
                now_timestamp = now.timestamp()
                today_str = now.strftime("%Y-%m-%d")

                # Task 1: Financial Market Watchdog (Every 30 mins / 1800 sec)
                if now_timestamp - last_finance_tick >= 1800:
                    logger.info("Cron: Running Financial Market Watchdog check...")
                    alerts = await self.finance_tools.evaluate_portfolio_alerts()
                    if alerts:
                        logger.info(f"Cron: Dispatched {len(alerts)} price shift alerts.")
                    last_finance_tick = now_timestamp

                # Task 2: Smart Gmail Inbox Triage (Every 20 mins / 1200 sec, LLM-free regex/IMAP)
                if now_timestamp - last_gmail_tick >= 1200:
                    logger.info("Cron: Running Smart Gmail Inbox Triage...")
                    try:
                        await asyncio.to_thread(self.gmail_triage.scan_inbox)
                    except Exception as gm_err:
                        logger.error(f"Cron: Gmail triage error: {gm_err}")
                    last_gmail_tick = now_timestamp

                # Task 3: Autonomous Project Health Audit (Every 2 Hours / 7200 sec)
                if now_timestamp - last_health_daemon_tick >= 7200:
                    logger.info("Cron: Running 24/7 Autonomous Project Health Daemon audit...")
                    try:
                        from core.project_health_daemon import project_health_daemon
                        if self.task_queue:
                            project_health_daemon.task_queue = self.task_queue
                        await project_health_daemon.audit_all_projects(force_run=False)
                    except Exception as hd_err:
                        logger.error(f"Cron: Error running Project Health Daemon audit: {hd_err}")
                    last_health_daemon_tick = now_timestamp

                # Task 4: Daily Industry Briefing (At 06:00 UTC if not run today)
                if now.hour == 6 and last_daily_tick_date != today_str:
                    logger.info("Cron: Dispatching Daily Morning Sector Briefing...")
                    await self.alert_manager.dispatch_alert(
                        title="Morning Sector Briefing",
                        message="24/7 Autonomous Industry Radar digest updated. Check Dashboard for full synthesis.",
                        severity="INFO",
                        category="DIGEST",
                    )
                    last_daily_tick_date = today_str

                # Task 5: Daily Off-Hours ImprovementScout Research Cycle (At 03:00 UTC)
                if now.hour == 3 and last_research_tick_date != today_str:
                    logger.info("Cron: Enqueuing Daily ImprovementScout Research Cycles...")
                    try:
                        from core.projects_manager import projects_manager
                        projects = projects_manager.list_projects()
                        for p in projects:
                            if self.task_queue:
                                self.task_queue.enqueue(
                                    workflow_type="RESEARCH_CYCLE",
                                    title=f"Improvement Scout: {p.get('project_name')}",
                                    priority=3,
                                    input_payload={
                                        "project_id": p.get("project_id"),
                                        "project_name": p.get("project_name"),
                                        "target_path": p.get("target_path"),
                                    },
                                    description=f"Autonomous research cycle for {p.get('project_name')}",
                                )
                        last_research_tick_date = today_str
                    except Exception as scout_err:
                        logger.error(f"Cron: Error enqueuing ImprovementScout cycle: {scout_err}")

            except Exception as e:
                logger.error(f"Error in CronEngine loop: {e}")

            # Sleep 60 seconds between tick checks
            await asyncio.sleep(60)

