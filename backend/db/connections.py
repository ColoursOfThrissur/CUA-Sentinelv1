import logging
from datetime import datetime, timezone
from pathlib import Path
import shutil
import sqlite3
from typing import Optional

logger = logging.getLogger(__name__)

DB_DIR = Path(__file__).parent.parent.parent / "data"
DB_DIR.mkdir(exist_ok=True)

OPERATIONAL_DB = DB_DIR / "operational.sqlite"
AUDIT_DB = DB_DIR / "audit.sqlite"
KNOWLEDGE_DB = DB_DIR / "knowledge.sqlite"
STATE_DB = DB_DIR / "state.sqlite"

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def _get_connection(db_path: Path, synchronous: str = "NORMAL") -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), check_same_thread=False, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(f"PRAGMA synchronous={synchronous}")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def get_operational_db() -> sqlite3.Connection:
    return _get_connection(OPERATIONAL_DB, synchronous="FULL")


def get_audit_db() -> sqlite3.Connection:
    return _get_connection(AUDIT_DB, synchronous="NORMAL")


def get_knowledge_db() -> sqlite3.Connection:
    return _get_connection(KNOWLEDGE_DB, synchronous="NORMAL")


def get_state_db() -> sqlite3.Connection:
    return _get_connection(STATE_DB, synchronous="NORMAL")


def _backup_db_pre_migrate(db_path: Path) -> Optional[Path]:
    """Creates a pre-migration timestamped snapshot of the SQLite database if it exists and is non-empty."""
    if not db_path.exists() or db_path.stat().st_size == 0:
        return None
    backup_dir = DB_DIR / ".sentinel_backup" / "db_pre_migrate"
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    target_path = backup_dir / f"{db_path.stem}_{timestamp}.sqlite"
    try:
        shutil.copy2(db_path, target_path)
        logger.info(f"Created pre-migration backup for {db_path.name} at {target_path}")
        return target_path
    except Exception as e:
        logger.warning(f"Failed to create pre-migration backup for {db_path.name}: {e}")
        return None


def _apply_migration(conn: sqlite3.Connection, sql_path: Path) -> None:
    # Ensure schema_migrations table exists with migration_name tracking
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
        )
        """
    )
    cur = conn.execute("PRAGMA table_info(schema_migrations)")
    cols = {row["name"] for row in cur.fetchall()}
    if "migration_name" not in cols:
        try:
            conn.execute("ALTER TABLE schema_migrations ADD COLUMN migration_name TEXT")
        except Exception:
            pass

    cur = conn.execute("SELECT 1 FROM schema_migrations WHERE migration_name = ?", (sql_path.name,))
    if cur.fetchone():
        logger.debug(f"Migration {sql_path.name} already applied, skipping.")
        return

    sql = sql_path.read_text(encoding="utf-8")
    conn.executescript(sql)
    conn.execute(
        "INSERT OR IGNORE INTO schema_migrations (version, migration_name) VALUES ((SELECT COALESCE(MAX(version), 0) + 1 FROM schema_migrations), ?)",
        (sql_path.name,),
    )
    logger.info(f"Applied migration: {sql_path.name}")


def initialize_all_databases() -> None:
    """
    Run on startup. Backs up existing databases before applying migrations.
    Safe to call multiple times - verifies schema_migrations.
    """
    databases = [
        (OPERATIONAL_DB, MIGRATIONS_DIR / "operational_v1.sql"),
        (OPERATIONAL_DB, MIGRATIONS_DIR / "features_v1.sql"),
        (OPERATIONAL_DB, MIGRATIONS_DIR / "projects_v1.sql"),
        (OPERATIONAL_DB, MIGRATIONS_DIR / "improvements_v1.sql"),
        (AUDIT_DB, MIGRATIONS_DIR / "audit_v1.sql"),
        (KNOWLEDGE_DB, MIGRATIONS_DIR / "knowledge_v1.sql"),
        (KNOWLEDGE_DB, MIGRATIONS_DIR / "mcp_catalog_v1.sql"),
    ]

    # Pre-migration backup snapshot for each unique DB
    backed_up_paths = set()
    for db_path, _ in databases:
        if db_path not in backed_up_paths:
            _backup_db_pre_migrate(db_path)
            backed_up_paths.add(db_path)

    for db_path, migration_path in databases:
        conn = _get_connection(db_path)
        try:
            _apply_migration(conn, migration_path)
            conn.commit()
            logger.info(f"Database ready: {db_path.name}")
        except Exception as e:
            logger.error(f"Failed to initialize {db_path.name}: {e}")
            raise
        finally:
            conn.close()

    # P0.3: Ensure version stamp columns exist on task_steps
    op_conn = get_operational_db()
    try:
        cur = op_conn.execute("PRAGMA table_info(task_steps)")
        cols = {row["name"] for row in cur.fetchall()}
        for col in ["model_id", "prompt_hash", "config_version", "gateway_version", "profile_version"]:
            if col not in cols:
                op_conn.execute(f"ALTER TABLE task_steps ADD COLUMN {col} TEXT")
                logger.info(f"Added version column '{col}' to task_steps")

        # P0.2: Ensure is_tainted column exists on tasks (taint persistence for resume)
        cur_tasks = op_conn.execute("PRAGMA table_info(tasks)")
        task_cols = {row["name"] for row in cur_tasks.fetchall()}
        if "is_tainted" not in task_cols:
            op_conn.execute("ALTER TABLE tasks ADD COLUMN is_tainted INTEGER DEFAULT 0")
            logger.info("Added taint column 'is_tainted' to tasks")

        # P0.4: Ensure task_checkpoints table exists (Pilot Profile Section 5.4)
        op_conn.execute(
            """
            CREATE TABLE IF NOT EXISTS task_checkpoints (
                checkpoint_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                step_index INTEGER NOT NULL,
                phase TEXT,
                state_json TEXT NOT NULL,
                input_hash TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
                FOREIGN KEY(task_id) REFERENCES tasks(task_id)
            )
            """
        )
        op_conn.execute("CREATE INDEX IF NOT EXISTS idx_checkpoints_task_step ON task_checkpoints(task_id, step_index DESC)")

        # P4: Result Cache & Playbook Hints (Pilot Profile Section 8.2, Decision D5)
        op_conn.execute(
            """
            CREATE TABLE IF NOT EXISTS result_cache (
                cache_key TEXT PRIMARY KEY,
                input_hash TEXT NOT NULL,
                profile_version TEXT NOT NULL,
                prompt_hash TEXT NOT NULL,
                model_id TEXT NOT NULL,
                ontology_version TEXT NOT NULL,
                result_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                hit_count INTEGER DEFAULT 0
            )
            """
        )
        op_conn.execute("CREATE INDEX IF NOT EXISTS idx_cache_expires ON result_cache(expires_at)")

        op_conn.execute(
            """
            CREATE TABLE IF NOT EXISTS playbook_hints (
                hint_id TEXT PRIMARY KEY,
                domain TEXT NOT NULL,
                agent_name TEXT NOT NULL,
                hint_text TEXT NOT NULL,
                provenance TEXT NOT NULL,
                status TEXT NOT NULL,
                approved_by TEXT,
                valid_from TEXT NOT NULL,
                valid_until TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        op_conn.execute("CREATE INDEX IF NOT EXISTS idx_hints_agent_domain ON playbook_hints(agent_name, domain, status)")

        op_conn.commit()
    except Exception as e:
        logger.warning(f"Version/taint/checkpoint column check: {e}")
    finally:
        op_conn.close()

    # P1: Golden Evaluation Tables in audit_db
    audit_conn = get_audit_db()
    try:
        audit_conn.execute(
            """
            CREATE TABLE IF NOT EXISTS eval_runs (
                run_id TEXT PRIMARY KEY,
                model_id TEXT NOT NULL,
                prompt_hash TEXT NOT NULL,
                config_version TEXT NOT NULL,
                gateway_version TEXT NOT NULL,
                total_cases INTEGER NOT NULL,
                passed_cases INTEGER NOT NULL,
                failed_cases INTEGER NOT NULL,
                pass_rate REAL NOT NULL,
                summary_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
            )
            """
        )
        audit_conn.execute(
            """
            CREATE TABLE IF NOT EXISTS eval_case_results (
                result_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                case_id TEXT NOT NULL,
                tag TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('PASS', 'FAIL', 'ERROR')),
                runs_count INTEGER NOT NULL,
                pass_count INTEGER NOT NULL,
                details_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
                FOREIGN KEY(run_id) REFERENCES eval_runs(run_id)
            )
            """
        )
        audit_conn.commit()
    except Exception as e:
        logger.warning(f"Failed to create eval tables in audit_db: {e}")
    finally:
        audit_conn.close()

    # P2: Typed Finance State Database (state.sqlite, Decision D1, Section 7.2)
    state_conn = get_state_db()
    try:
        # 1. Facts table
        state_conn.execute(
            """
            CREATE TABLE IF NOT EXISTS facts (
                fact_id TEXT PRIMARY KEY,
                entity_type TEXT NOT NULL CHECK(entity_type IN (
                    'STATEMENT', 'ACCOUNT', 'INSTRUMENT', 'TRANSACTION', 'HOLDING', 'FOREXRATE'
                )),
                entity_id TEXT NOT NULL,
                attribute TEXT NOT NULL,
                value_json TEXT NOT NULL,
                tier TEXT NOT NULL CHECK(tier IN ('T0', 'T1', 'T2', 'T3')),
                status TEXT NOT NULL CHECK(status IN (
                    'active', 'superseded', 'quarantined', 'rejected', 'pending_review'
                )),
                source_kind TEXT NOT NULL CHECK(source_kind IN ('file', 'user', 'web', 'derived', 'agent')),
                source_ref TEXT NOT NULL,
                source_authority TEXT NOT NULL,
                evidence_ref TEXT NOT NULL,
                author_agent TEXT NOT NULL,
                model_id TEXT,
                prompt_hash TEXT,
                task_id TEXT,
                step_id TEXT,
                observed_at TEXT NOT NULL,
                recorded_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
                valid_from TEXT,
                valid_until TEXT,
                confidence REAL DEFAULT 1.0,
                supersedes_fact_id TEXT,
                ontology_version TEXT DEFAULT '1.0'
            )
            """
        )
        state_conn.execute("CREATE INDEX IF NOT EXISTS idx_facts_entity ON facts(entity_type, entity_id, attribute)")
        state_conn.execute("CREATE INDEX IF NOT EXISTS idx_facts_status ON facts(status)")

        # 2. Entities table
        state_conn.execute(
            """
            CREATE TABLE IF NOT EXISTS entities (
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                canonical_key TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
                PRIMARY KEY (entity_type, entity_id),
                UNIQUE(canonical_key)
            )
            """
        )

        # 3. Events table (append-only state audit)
        state_conn.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                event_id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL CHECK(event_type IN (
                    'COMMIT', 'QUARANTINE', 'REVIEW', 'REJECT', 'SUPERSEDE'
                )),
                fact_id TEXT NOT NULL,
                actor TEXT NOT NULL,
                reason TEXT NOT NULL,
                timestamp TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
            )
            """
        )

        # 4. Reviews table (pending human decisions)
        state_conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reviews (
                review_id TEXT PRIMARY KEY,
                fact_id TEXT NOT NULL,
                reason TEXT NOT NULL,
                options_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'PENDING' CHECK(status IN ('PENDING', 'RESOLVED', 'DISMISSED')),
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
                resolved_at TEXT,
                FOREIGN KEY(fact_id) REFERENCES facts(fact_id)
            )
            """
        )
        state_conn.commit()
    except Exception as e:
        logger.warning(f"Failed to initialize state.sqlite tables: {e}")
    finally:
        state_conn.close()
