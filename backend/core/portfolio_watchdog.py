import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

from db.connections import get_operational_db
from tools.finance_tools import FinanceTools
from core.alert_manager import AlertManager

logger = logging.getLogger(__name__)


class PortfolioWatchdog:
    """
    Automated Background Watchdog for Portfolio Holdings & Market Alerts.
    Periodically checks price shift triggers (|Δ| >= 5%) and breaking news for held stocks.
    """

    def __init__(self, alert_manager: Optional[AlertManager] = None):
        self.finance_tools = FinanceTools(alert_manager=alert_manager)
        self.alert_manager = alert_manager or AlertManager()
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._check_interval_seconds = 3600  # 1 hour

    async def run_once(self) -> Dict[str, Any]:
        """
        Executes a single watchdog scan across all Demat portfolio assets.
        """
        logger.info("Executing automated Portfolio Watchdog scan...")
        try:
            alerts = await self.finance_tools.evaluate_portfolio_alerts()
            news = await self.finance_tools.fetch_portfolio_news()
            
            timestamp = datetime.now(timezone.utc).isoformat()
            conn = get_operational_db()
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS watchdog_logs (
                    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    alerts_count INTEGER,
                    news_count INTEGER,
                    run_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "INSERT INTO watchdog_logs (alerts_count, news_count, run_at) VALUES (?, ?, ?)",
                (len(alerts), len(news), timestamp)
            )
            conn.commit()
            conn.close()

            logger.info(f"Watchdog scan complete: {len(alerts)} alerts triggered, {len(news)} news items fetched.")
            return {
                "status": "SUCCESS",
                "alerts_triggered": len(alerts),
                "news_items": len(news),
                "timestamp": timestamp
            }
        except Exception as e:
            logger.error(f"Error during Portfolio Watchdog scan: {e}")
            return {"status": "ERROR", "error": str(e)}

    async def _loop(self):
        while self._running:
            await self.run_once()
            await asyncio.sleep(self._check_interval_seconds)

    def start_background_loop(self):
        if not self._running:
            self._running = True
            self._task = asyncio.create_task(self._loop())
            logger.info("Portfolio Watchdog background loop started.")

    def stop_background_loop(self):
        if self._running:
            self._running = False
            if self._task:
                self._task.cancel()
            logger.info("Portfolio Watchdog background loop stopped.")
