import asyncio
import logging
import os
import signal
import sys
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from db.connections import initialize_all_databases, get_operational_db
from core.model_manager import ModelManager
from core.queue import TaskQueue
from core.scheduler import Scheduler
from core.watchdog import Watchdog
from core.governance import GovernanceEngine
from api.server import create_app
from api.websocket import telemetry_loop
from config.loader import load_system_config, load_policy_rules, load_model_registry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("sentinel.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("sentinel.main")

BOOT_ID = str(uuid.uuid4())


async def startup(app: FastAPI) -> None:
    logger.info(f"CUA-Sentinel starting. Boot ID: {BOOT_ID}")

    config = load_system_config()
    policy = load_policy_rules()
    registry = load_model_registry()

    initialize_all_databases()

    conn = get_operational_db()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO worker_nodes (worker_id, os_type, last_seen_boot_id, status) VALUES (?, ?, ?, 'ONLINE')",
            (config["system"]["worker_id"], config["system"]["os_type"], BOOT_ID),
        )
        conn.execute(
            "UPDATE system_state SET value = ?, updated_at = ? WHERE key = 'current_boot_id'",
            (BOOT_ID, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    finally:
        conn.close()

    model_manager = ModelManager(config, registry)
    task_queue = TaskQueue(config)
    recovered_count = task_queue.recover_interrupted_tasks()
    if recovered_count > 0:
        logger.info(f"Startup task recovery: requeued {recovered_count} interrupted task(s).")
    governance = GovernanceEngine(policy, config)
    scheduler = Scheduler(task_queue, model_manager, governance, config)

    # Pre-load default ENDPOINT model so first chat has no cold-start delay
    try:
        default_model = registry["model_routing"]["ENDPOINT"]
        model_manager.load_model(default_model, 8192)
        logger.info(f"Pre-loaded default model: {default_model}")
    except Exception as e:
        logger.warning(f"Could not pre-load default model: {e}")
    watchdog = Watchdog(config, scheduler, model_manager)

    from core.cron_engine import CronEngine
    from core.router import AgentRegistry
    from agents.cua_agent import CUAAgent
    from agents.code_refactor_agent import CodeRefactorAgent
    from core.discord_bot import DiscordSentinelBot
    from core.scheduler_engine import SchedulerEngine
    AgentRegistry.register("CUA", CUAAgent)
    AgentRegistry.register("CODE_REFACTOR", CodeRefactorAgent)
    AgentRegistry.register("SCAFFOLDER", CodeRefactorAgent)
    AgentRegistry.register("REFACTOR", CodeRefactorAgent)
    AgentRegistry.register("TESTER", CodeRefactorAgent)
    AgentRegistry.register("REVIEWER", CodeRefactorAgent)
    AgentRegistry.register("ENDPOINT", CUAAgent)
    AgentRegistry.register("RESEARCHER", CUAAgent)
    AgentRegistry.register("SYNTHESIZER", CUAAgent)
    AgentRegistry.register("SECOND_BRAIN", CUAAgent)
    AgentRegistry.register("SYNTHETIC_DATA", CUAAgent)

    cron_engine = CronEngine(config)
    await cron_engine.start()

    # Initialize Discord 2-Way Bot Service if configured
    discord_bot = DiscordSentinelBot(task_queue=task_queue, governance=governance)
    try:
        from core.alert_manager import AlertManager
        am = AlertManager()
        token = am._get_setting("discord_bot_token")
        allowed_uid = am._get_setting("discord_allowed_user_id")
        channel_id = am._get_setting("discord_channel_id")
        if token:
            discord_bot.start_bot(token, allowed_uid, channel_id)
    except Exception as d_err:
        logger.warning(f"Could not initialize Discord Bot: {d_err}")

    # Initialize SchedulerEngine for background reminders & cron jobs
    scheduler_engine = SchedulerEngine(task_queue=task_queue, discord_bot=discord_bot)
    await scheduler_engine.start()

    from core.portfolio_watchdog import PortfolioWatchdog
    portfolio_watchdog = PortfolioWatchdog()
    portfolio_watchdog.start_background_loop()

    app.state.config = config
    app.state.policy = policy
    app.state.registry = registry
    app.state.boot_id = BOOT_ID
    app.state.model_manager = model_manager
    app.state.task_queue = task_queue
    app.state.governance = governance
    app.state.scheduler = scheduler
    app.state.watchdog = watchdog
    app.state.cron_engine = cron_engine
    app.state.discord_bot = discord_bot
    app.state.scheduler_engine = scheduler_engine
    app.state.portfolio_watchdog = portfolio_watchdog

    asyncio.create_task(scheduler.run())
    asyncio.create_task(watchdog.run())
    asyncio.create_task(telemetry_loop())

    logger.info("CUA-Sentinel fully started.")


async def shutdown(app: FastAPI) -> None:
    logger.info("CUA-Sentinel shutting down cleanly...")

    if hasattr(app.state, "portfolio_watchdog"):
        app.state.portfolio_watchdog.stop_background_loop()

    if hasattr(app.state, "scheduler_engine"):
        await app.state.scheduler_engine.stop()

    if hasattr(app.state, "scheduler"):
        await app.state.scheduler.stop()

    if hasattr(app.state, "watchdog"):
        await app.state.watchdog.stop()

    if hasattr(app.state, "cron_engine"):
        await app.state.cron_engine.stop()

    if hasattr(app.state, "model_manager"):
        app.state.model_manager.unload_current()

    conn = get_operational_db()
    try:
        conn.execute(
            "UPDATE worker_nodes SET status = 'OFFLINE' WHERE worker_id = ?",
            (app.state.config["system"]["worker_id"],),
        )
        conn.commit()
    finally:
        conn.close()

    logger.info("CUA-Sentinel shutdown complete.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await startup(app)
    yield
    await shutdown(app)


def main():
    config = load_system_config()
    app = create_app(lifespan)

    # Optional SSL support: prefer environment variables, fallback to config
    ssl_cert = os.environ.get("SENTINEL_SSL_CERT") or config["api"].get("ssl_certfile")
    ssl_key = os.environ.get("SENTINEL_SSL_KEY") or config["api"].get("ssl_keyfile")

    uvicorn_kwargs = dict(app=app, host=config["api"]["host"], port=config["api"]["port"], log_level="info")
    # Only enable SSL if both files exist on disk
    if ssl_cert and ssl_key:
        if os.path.exists(ssl_cert) and os.path.exists(ssl_key):
            uvicorn_kwargs["ssl_certfile"] = ssl_cert
            uvicorn_kwargs["ssl_keyfile"] = ssl_key
            logger.info("Starting with SSL: cert=%s key=%s", ssl_cert, ssl_key)
        else:
            logger.warning(
                "SSL cert/key specified but file(s) not found. Serving HTTP instead. cert=%s key=%s",
                ssl_cert,
                ssl_key,
            )

    uvicorn.run(**uvicorn_kwargs)


if __name__ == "__main__":
    main()
