import sqlite3
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

DB_DIR = Path(__file__).parent.parent.parent / "data"
DB_DIR.mkdir(exist_ok=True)

OPERATIONAL_DB = DB_DIR / "operational.sqlite"
AUDIT_DB = DB_DIR / "audit.sqlite"
KNOWLEDGE_DB = DB_DIR / "knowledge.sqlite"

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def _get_connection(db_path: Path, synchronous: str = "NORMAL") -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(f"PRAGMA synchronous={synchronous}")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def get_operational_db() -> sqlite3.Connection:
    return _get_connection(OPERATIONAL_DB, synchronous="FULL")


def get_audit_db() -> sqlite3.Connection:
    return _get_connection(AUDIT_DB, synchronous="NORMAL")


def get_knowledge_db() -> sqlite3.Connection:
    return _get_connection(KNOWLEDGE_DB, synchronous="NORMAL")


def _apply_migration(conn: sqlite3.Connection, sql_path: Path) -> None:
    sql = sql_path.read_text(encoding="utf-8")
    conn.executescript(sql)
    logger.info(f"Applied migration: {sql_path.name}")


def initialize_all_databases() -> None:
    """
    Run on startup. Applies migrations to all three databases if not already applied.
    Safe to call multiple times - uses INSERT OR IGNORE on schema_migrations.
    """
    databases = [
        (OPERATIONAL_DB, MIGRATIONS_DIR / "operational_v1.sql"),
        (OPERATIONAL_DB, MIGRATIONS_DIR / "features_v1.sql"),
        (OPERATIONAL_DB, MIGRATIONS_DIR / "projects_v1.sql"),
        (AUDIT_DB, MIGRATIONS_DIR / "audit_v1.sql"),
        (KNOWLEDGE_DB, MIGRATIONS_DIR / "knowledge_v1.sql"),
    ]

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
