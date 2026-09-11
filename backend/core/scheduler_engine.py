import asyncio
import logging
import sqlite3
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional

from db.connections import get_operational_db

logger = logging.getLogger(__name__)


def init_scheduler_db():
    """Initializes the scheduled_jobs table in operational.sqlite with auto-migration."""
    conn = get_operational_db()
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(scheduled_jobs)")
    cols = [c[1] for c in cur.fetchall()]

    if cols and "name" not in cols:
        logger.info("Migrating legacy scheduled_jobs table schema...")
        conn.execute("DROP TABLE scheduled_jobs")
        conn.commit()

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS scheduled_jobs (
            job_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            schedule_type TEXT NOT NULL, -- 'TIMER' or 'CRON'
            cron_expr TEXT,
            run_at TEXT,
            workflow_type TEXT NOT NULL DEFAULT 'ENDPOINT',
            input_payload TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDING', -- 'PENDING', 'RUNNING', 'COMPLETED', 'CANCELLED'
            last_run_at TEXT,
            next_run_at TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.commit()


class SchedulerEngine:
    """
    Background Scheduler Engine for CUA-Sentinel.
    Persists recurring cron tasks and one-shot reminders in SQLite,
    executes due jobs via TaskQueue, and dispatches alerts to Discord and UI.
    """

    def __init__(self, task_queue=None, discord_bot=None):
        self.task_queue = task_queue
        self.discord_bot = discord_bot
        self._running = False
        self._loop_task = None
        init_scheduler_db()

    def set_dependencies(self, task_queue, discord_bot=None):
        self.task_queue = task_queue
        self.discord_bot = discord_bot

    def parse_time_offset(self, time_str: str) -> Optional[datetime]:
        """
        Parses relative time strings like '10s', '15m', '2h', '1d' into a UTC target datetime.
        """
        time_str = time_str.strip().lower()
        now = datetime.now(timezone.utc)

        try:
            if time_str.endswith('s'):
                seconds = int(time_str[:-1])
                return now + timedelta(seconds=seconds)
            elif time_str.endswith('m'):
                minutes = int(time_str[:-1])
                return now + timedelta(minutes=minutes)
            elif time_str.endswith('h'):
                hours = int(time_str[:-1])
                return now + timedelta(hours=hours)
            elif time_str.endswith('d'):
                days = int(time_str[:-1])
                return now + timedelta(days=days)
            else:
                # Try parsing as ISO format timestamp
                return datetime.fromisoformat(time_str).replace(tzinfo=timezone.utc)
        except Exception as e:
            logger.warning(f"Failed to parse time string '{time_str}': {e}")
            return None

    def add_reminder(self, name: str, time_str: str, prompt: str, workflow_type: str = "ENDPOINT") -> Optional[Dict[str, Any]]:
        """
        Schedules a one-shot reminder job.
        """
        import uuid
        target_time = self.parse_time_offset(time_str)
        if not target_time:
            return None

        job_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        run_at = target_time.isoformat()

        payload = {
            "prompt": prompt,
            "system_prompt": f"Reminder Alert: {name}",
        }

        conn = get_operational_db()
        conn.execute(
            """
            INSERT INTO scheduled_jobs (
                job_id, name, schedule_type, run_at, workflow_type,
                input_payload, status, next_run_at, created_at
            ) VALUES (?, ?, 'TIMER', ?, ?, ?, 'PENDING', ?, ?)
            """,
            (job_id, name, run_at, workflow_type, json.dumps(payload), run_at, created_at)
        )
        conn.commit()

        return {
            "job_id": job_id,
            "name": name,
            "run_at": run_at,
            "status": "PENDING",
            "prompt": prompt
        }

    def list_jobs(self) -> List[Dict[str, Any]]:
        """
        Lists all scheduled jobs from SQLite.
        """
        conn = get_operational_db()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT job_id, name, schedule_type, cron_expr, run_at,
                   workflow_type, input_payload, status, last_run_at, next_run_at, created_at
            FROM scheduled_jobs
            ORDER BY created_at DESC
            """
        )
        rows = cur.fetchall()
        jobs = []
        for r in rows:
            payload = json.loads(r[6]) if r[6] else {}
            jobs.append({
                "job_id": r[0],
                "name": r[1],
                "schedule_type": r[2],
                "cron_expr": r[3],
                "run_at": r[4],
                "workflow_type": r[5],
                "prompt": payload.get("prompt", ""),
                "status": r[7],
                "last_run_at": r[8],
                "next_run_at": r[9],
                "created_at": r[10]
            })
        return jobs

    def cancel_job(self, job_id: str) -> bool:
        """
        Cancels a scheduled job.
        """
        conn = get_operational_db()
        cur = conn.cursor()
        cur.execute("UPDATE scheduled_jobs SET status = 'CANCELLED' WHERE job_id = ?", (job_id,))
        conn.commit()
        return cur.rowcount > 0

    async def start(self):
        """Starts the async background check loop."""
        if self._running:
            return
        self._running = True
        self._loop_task = asyncio.create_task(self._scheduler_loop())
        logger.info("SchedulerEngine background loop started.")

    async def stop(self):
        """Stops the background loop cleanly."""
        self._running = False
        if self._loop_task:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass
        logger.info("SchedulerEngine background loop stopped.")

    async def _scheduler_loop(self):
        """Periodically checks SQLite for due jobs every 5 seconds."""
        while self._running:
            try:
                await self._check_due_jobs()
            except Exception as e:
                logger.error(f"Error in SchedulerEngine loop: {e}")
            await asyncio.sleep(5)

    async def _check_due_jobs(self):
        now_iso = datetime.now(timezone.utc).isoformat()
        conn = get_operational_db()
        cur = conn.cursor()

        # Find due jobs
        cur.execute(
            """
            SELECT job_id, name, schedule_type, workflow_type, input_payload
            FROM scheduled_jobs
            WHERE status = 'PENDING' AND (run_at <= ? OR next_run_at <= ?)
            """,
            (now_iso, now_iso)
        )
        due_jobs = cur.fetchall()

        for j in due_jobs:
            job_id, name, sched_type, wf_type, payload_str = j
            logger.info(f"Executing due scheduled job: {job_id} ({name})")

            # Update status to RUNNING
            conn.execute(
                "UPDATE scheduled_jobs SET status = 'RUNNING', last_run_at = ? WHERE job_id = ?",
                (now_iso, job_id)
            )
            conn.commit()

            payload = json.loads(payload_str) if payload_str else {}

            # Execute via TaskQueue if present
            if self.task_queue:
                t_id = self.task_queue.enqueue(
                    workflow_type=wf_type,
                    title=f"Scheduled Job: {name}",
                    input_payload=payload,
                    priority=0
                )
                logger.info(f"Enqueued task {t_id} for scheduled job {job_id}")

            # Notify Discord Bot if configured
            if self.discord_bot and hasattr(self.discord_bot, "broadcast_notification"):
                try:
                    msg = f"⏰ **Reminder Triggered**: **{name}**\nPrompt: {payload.get('prompt')}"
                    await self.discord_bot.broadcast_notification(msg)
                except Exception as d_err:
                    logger.warning(f"Could not dispatch Discord reminder: {d_err}")

            # Update final job state to COMPLETED for one-shot timers
            conn.execute(
                "UPDATE scheduled_jobs SET status = 'COMPLETED' WHERE job_id = ?",
                (job_id,)
            )
            conn.commit()
