"""
Base Repository: foundation for all SQLite repositories in CUA-Sentinel.
Provides connection pooling, row serialization, and retry-backed transactions.
"""

import sqlite3
from typing import Any, Callable, Dict, Generator, List, Optional
from contextlib import contextmanager

try:
    from ..transaction import DatabaseLockError, execute_write_transaction, run_write_with_retry
except ImportError:
    from backend.db.transaction import DatabaseLockError, execute_write_transaction, run_write_with_retry


class BaseRepository:
    """Base class for data access repositories managing SQLite persistence."""

    def __init__(self, db_getter: Callable[[], sqlite3.Connection], db_name: str = "sqlite"):
        self._db_getter = db_getter
        self.db_name = db_name

    def get_connection(self) -> sqlite3.Connection:
        """Obtain a fresh connection with standard pragmas (WAL, busy_timeout=30s, foreign keys)."""
        return self._db_getter()

    @contextmanager
    def write_transaction(
        self,
        operation_name: str = "write_transaction",
        max_retries: int = 5,
        initial_delay: float = 0.05,
    ) -> Generator[sqlite3.Cursor, None, None]:
        """Provides an isolated transaction with bounded retry/backoff on lock contention."""
        conn = self.get_connection()
        try:
            with execute_write_transaction(
                conn=conn,
                operation_name=operation_name,
                max_retries=max_retries,
                initial_delay=initial_delay,
                db_name=self.db_name,
            ) as cursor:
                yield cursor
        finally:
            conn.close()

    @staticmethod
    def row_to_dict(row: Optional[sqlite3.Row]) -> Optional[Dict[str, Any]]:
        """Converts an sqlite3.Row to a standard Python dictionary."""
        if row is None:
            return None
        return dict(row)

    @staticmethod
    def rows_to_dicts(rows: List[sqlite3.Row]) -> List[Dict[str, Any]]:
        """Converts a list of sqlite3.Row objects to standard Python dictionaries."""
        return [dict(r) for r in rows]
