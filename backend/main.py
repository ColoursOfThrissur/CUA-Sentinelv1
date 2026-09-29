import os
import sys
# Guarantee backend/ directory is on sys.path regardless of execution directory
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_THIS_DIR)
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)
if _ROOT_DIR not in sys.path:
    sys.path.insert(0, _ROOT_DIR)

import asyncio
import logging
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


async def _cache_prune_loop() -> None:
    """Prune expired result_cache entries every 30 minutes."""
    while True:
        try:
            await asyncio.sleep(1800)  # wait 30 min before first prune too
            from core.result_cache import result_cache
            pruned = result_cache.prune_expired()
            if pruned > 0:
                logger.info(f"Result cache: pruned {pruned} expired entries")
        except Exception as e:
            logger.warning(f"Cache prune error: {e}")


async def _chroma_prune_loop() -> None:
    """
    Prune ChromaDB knowledge collection entries older than 90 days, every 24 hours.
    Keeps the vector store from growing unbounded and degrading semantic search quality.
    """
    CHROMA_MAX_AGE_DAYS = 90
    while True:
        try:
            await asyncio.sleep(86400)  # 24h between runs
            pruned = await asyncio.to_thread(_prune_chroma_old_entries, CHROMA_MAX_AGE_DAYS)
            if pruned > 0:
                logger.info(f"ChromaDB: pruned {pruned} entries older than {CHROMA_MAX_AGE_DAYS} days")
        except Exception as e:
            logger.warning(f"ChromaDB prune error: {e}")


def _prune_chroma_old_entries(max_age_days: int) -> int:
    """
    Deletes ChromaDB documents whose 'created_at' metadata is older than max_age_days.
    Returns the count of deleted entries.
    """
    try:
        import chromadb
        from datetime import datetime, timezone, timedelta
        cutoff_ts = (datetime.now(timezone.utc) - timedelta(days=max_age_days)).timestamp()
        client = chromadb.PersistentClient(path="data/chroma_db")
        total_pruned = 0
        for coll_name in [c.name for c in client.list_collections()]:
            coll = client.get_collection(coll_name)
            results = coll.get(include=["metadatas"])
            ids_to_delete = []
            for doc_id, meta in zip(results["ids"], results["metadatas"] or []):
                created_at = (meta or {}).get("created_at")
                if created_at:
                    try:
                        ts = float(created_at)
                        if ts < cutoff_ts:
                            ids_to_delete.append(doc_id)
                    except (ValueError, TypeError):
                        pass
            if ids_to_delete:
                coll.delete(ids=ids_to_delete)
                total_pruned += len(ids_to_delete)
        return total_pruned
    except Exception as e:
        logger.warning(f"ChromaDB prune internal error: {e}")
        return 0


EVAL_INTERVAL_SEC = 7 * 24 * 3600  # weekly


async def _eval_harness_loop() -> None:
    """
    Runs the golden eval harness on a weekly schedule.
    First run is delayed 5 minutes after startup to avoid competing with cold-start tasks.
    Results are written to the audit DB and logged.  A regression (pass_rate < 0.8) logs
    a warning so it shows up in sentinel.log and the watchdog can react.
    """
    await asyncio.sleep(300)  # 5-min startup grace period
    while True:
        try:
            logger.info("Eval harness: starting weekly golden suite run")
            import sys as _sys
            _eval_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "eval")
            if _eval_dir not in _sys.path:
                _sys.path.insert(0, _eval_dir)
            from eval.harness import GoldenEvalHarness
            harness = GoldenEvalHarness()
            report = await harness.run_suite(iterations_per_case=2)

            pass_rate = report.get("pass_rate", 0.0)
            total = report.get("total_cases", 0)
            passed = report.get("passed_cases", 0)
            run_id = report.get("run_id", "unknown")

            # Persist summary to audit DB
            try:
                from db.connections import get_audit_db
                conn = get_audit_db()
                try:
                    conn.execute("""
                        CREATE TABLE IF NOT EXISTS eval_runs (
                            run_id TEXT PRIMARY KEY,
                            pass_rate REAL,
                            total_cases INTEGER,
                            passed_cases INTEGER,
                            report_json TEXT,
                            created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
                        )
                    """)
                    conn.execute(
                        "INSERT OR REPLACE INTO eval_runs (run_id, pass_rate, total_cases, passed_cases, report_json) VALUES (?,?,?,?,?)",
                        (run_id, pass_rate, total, passed,
                         __import__("json").dumps(report, default=str)[:65535]),
                    )
                    conn.commit()
                finally:
                    conn.close()
            except Exception as db_err:
                logger.warning(f"Eval harness: could not persist report: {db_err}")

            if pass_rate < 0.8:
                logger.warning(
                    f"Eval harness REGRESSION: pass_rate={pass_rate:.0%} "
                    f"({passed}/{total} cases) — run_id={run_id}"
                )
            else:
                logger.info(
                    f"Eval harness OK: pass_rate={pass_rate:.0%} "
                    f"({passed}/{total} cases) — run_id={run_id}"
                )
        except Exception as e:
            logger.error(f"Eval harness loop error: {e}")

        await asyncio.sleep(EVAL_INTERVAL_SEC)

def _is_service_enabled(service_id: str) -> bool:
    """Check user preference for a background service. Default: disabled."""
    try:
        from db.connections import get_knowledge_db
        conn = get_knowledge_db()
        try:
            row = conn.execute(
                "SELECT pref_value FROM user_preferences WHERE pref_key = 'background_services_enabled'"
            ).fetchone()
            if row:
                cfg = __import__("json").loads(row["pref_value"])
                return bool(cfg.get(service_id, False))
        finally:
            conn.close()
    except Exception:
        pass
    return False


async def startup(app: FastAPI) -> None:
    logger.info(f"CUA-Sentinel starting. Boot ID: {BOOT_ID}")

    config = load_system_config()
    policy = load_policy_rules()
    registry = load_model_registry()

    # P0.1 Tool Registry startup validation (fail closed)
    from config.loader import validate_tool_registry
    validate_tool_registry()

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
    from agents.endpoint_agent import EndpointAgent
    from agents.researcher import ResearcherAgent
    from agents.synthesizer import SynthesizerAgent
    from agents.project_repair_agent import ProjectRepairAgent
    from agents.research_cycle_agent import ResearchCycleAgent
    from core.discord_bot import DiscordSentinelBot
    from core.scheduler_engine import SchedulerEngine
    from core.project_health_daemon import project_health_daemon
    from core.background_services import BackgroundTaskGroup
    from agents.base_agent import BaseAgent
    BaseAgent.register_default_handlers()

    # Wire unified task_queue to project_health_daemon
    project_health_daemon.task_queue = task_queue

    # Consolidated Single Source of Truth Agent Registry
    AgentRegistry.register("ENDPOINT", EndpointAgent)
    AgentRegistry.register("FINANCE", EndpointAgent)
    AgentRegistry.register("BOOKMARK", EndpointAgent)

    # Initialize MCP Manager for app connections
    from core.mcp_manager import MCPManager
    mcp_manager = MCPManager()
    mcp_manager.initialize_from_config()
    try:
        await mcp_manager.auto_connect_enabled()
    except Exception as mcp_err:
        logger.warning(f"MCP auto-connect had errors: {mcp_err}")
    scheduler.mcp_manager = mcp_manager

    # Wire MCP manager into ToolGateway for runtime tool resolution
    from core.tool_gateway import ToolGateway
    ToolGateway._active_mcp_manager = mcp_manager
    AgentRegistry.register("PROJECT_HEALTH_REPAIR", ProjectRepairAgent)
    AgentRegistry.register("RESEARCH_CYCLE", ResearchCycleAgent)
    AgentRegistry.register("CODE_REFACTOR", CodeRefactorAgent)
    AgentRegistry.register("SCAFFOLDER", CodeRefactorAgent)
    AgentRegistry.register("REFACTOR", CodeRefactorAgent)
    AgentRegistry.register("TESTER", CodeRefactorAgent)
    AgentRegistry.register("REVIEWER", CodeRefactorAgent)
    AgentRegistry.register("RESEARCHER", ResearcherAgent)
    AgentRegistry.register("RESEARCH", ResearcherAgent)
    AgentRegistry.register("SYNTHESIZER", SynthesizerAgent)
    AgentRegistry.register("CUA", CUAAgent)
    AgentRegistry.register("SECOND_BRAIN", CUAAgent)
    AgentRegistry.register("SYNTHETIC_DATA", CUAAgent)

    cron_engine = CronEngine(config, task_queue=task_queue)
    await cron_engine.start()

    # Initialize Discord 2-Way Bot Service if configured
    discord_bot = DiscordSentinelBot(task_queue=task_queue, governance=governance)
    if _is_service_enabled("discord_bot"):
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
    else:
        logger.info("Background service 'discord_bot' is disabled — skipping.")

    # Initialize SchedulerEngine for background reminders & cron jobs
    scheduler_engine = SchedulerEngine(task_queue=task_queue, discord_bot=discord_bot)
    if _is_service_enabled("scheduler_engine"):
        await scheduler_engine.start()
    else:
        logger.info("Background service 'scheduler_engine' is disabled — skipping.")

    from core.portfolio_watchdog import PortfolioWatchdog
    portfolio_watchdog = PortfolioWatchdog()
    if _is_service_enabled("portfolio_watchdog"):
        portfolio_watchdog.start_background_loop()
    else:
        logger.info("Background service 'portfolio_watchdog' is disabled — skipping.")

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
    app.state.mcp_manager = mcp_manager
    app.state.background_tasks = BackgroundTaskGroup()

    app.state.background_tasks.start("scheduler", scheduler.run())
    app.state.background_tasks.start("watchdog", watchdog.run())
    app.state.background_tasks.start("telemetry", telemetry_loop())

    # Maintenance loops: run at startup and then on schedule
    app.state.background_tasks.start("cache-prune", _cache_prune_loop())
    app.state.background_tasks.start("chroma-prune", _chroma_prune_loop())

    # Eval harness: runs once at startup (after a short delay) then weekly
    app.state.background_tasks.start("eval-harness", _eval_harness_loop())

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

    if hasattr(app.state, "mcp_manager"):
        try:
            await app.state.mcp_manager.shutdown()
        except Exception as e:
            logger.warning(f"Error shutting down MCP manager: {e}")

    if hasattr(app.state, "background_tasks"):
        await app.state.background_tasks.stop()

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
# Module-level FastAPI app instance for Uvicorn CLI discovery (e.g. uvicorn main:app)
app = create_app(lifespan)

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
