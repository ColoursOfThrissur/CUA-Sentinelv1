import asyncio
import logging
from datetime import datetime, timezone
from tools.finance_tools import FinanceTools
from core.alert_manager import AlertManager

logger = logging.getLogger(__name__)


class CronEngine:
    """
    24/7 Autonomous Cron Scheduler Engine.
    Executes background periodic tasks without requiring human UI interaction:
    1. Financial Market Watchdog (Every 30 Minutes)
    2. Industry Synthesizer Briefing (Daily)
    3. SQLite Maintenance & DB Retention Janitor (Weekly)
    """

    def __init__(self, config: dict):
        self.config = config
        self.finance_tools = FinanceTools()
        self.alert_manager = AlertManager()
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
        last_daily_tick_date = ""

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

                # Task 2: Daily Industry Briefing (At 06:00 UTC if not run today)
                if now.hour == 6 and last_daily_tick_date != today_str:
                    logger.info("Cron: Dispatching Daily Morning Sector Briefing...")
                    await self.alert_manager.dispatch_alert(
                        title="Morning Sector Briefing",
                        message="24/7 Autonomous Industry Radar digest updated. Check Dashboard for full synthesis.",
                        severity="INFO",
                        category="DIGEST",
                    )
                    last_daily_tick_date = today_str

            except Exception as e:
                logger.error(f"Error in CronEngine loop: {e}")

            # Sleep 60 seconds between tick checks
            await asyncio.sleep(60)
