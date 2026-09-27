"""
Database transaction utilities: bounded retries, exponential backoff,
structured failure events, and lock error detection for SQLite under concurrency.
"""

import logging
import random
import sqlite3
import time
from contextlib import contextmanager
from typing import Any, Callable, Generator, Optional

logger = logging.getLogger(__name__)


class DatabaseLockError(Exception):
    """Raised when a database write transaction fails due to lock contention after retries are exhausted."""

    def __init__(
        self,
        db_name: str,
        operation: str,
        retries_attempted: int,
        elapsed_seconds: float,
        error_details: str,
    ):
        super().__init__(
            f"Database '{db_name}' locked during '{operation}' after {retries_attempted} retries "
            f"({elapsed_seconds:.3f}s elapsed): {error_details}"
        )
        self.db_name = db_name
        self.operation = operation
        self.retries_attempted = retries_attempted
        self.elapsed_seconds = elapsed_seconds
        self.error_details = error_details

    def to_dict(self) -> dict:
        return {
            "error_type": "DatabaseLockError",
            "db_name": self.db_name,
            "operation": self.operation,
            "retries_attempted": self.retries_attempted,
            "elapsed_seconds": round(self.elapsed_seconds, 4),
            "details": self.error_details,
        }


def is_lock_error(exc: Exception) -> bool:
    """Returns True if the exception represents SQLite lock contention or busy status."""
    if isinstance(exc, sqlite3.OperationalError):
        msg = str(exc).lower()
        return "locked" in msg or "busy" in msg
    return False


@contextmanager
def execute_write_transaction(
    conn: sqlite3.Connection,
    operation_name: str = "write_transaction",
    max_retries: int = 5,
    initial_delay: float = 0.05,
    backoff_factor: float = 2.0,
    max_delay: float = 1.0,
    db_name: str = "database",
) -> Generator[sqlite3.Cursor, None, None]:
    """
    Context manager executing write operations inside an explicit transaction with bounded retries.

    If SQLite raises a lock/busy OperationalError, it retries with exponential backoff and jitter.
    If max_retries is reached, rolls back, logs a structured error event, and raises DatabaseLockError.
    """
    start_time = time.monotonic()
    last_err: Optional[Exception] = None

    for attempt in range(1, max_retries + 1):
        try:
            # Begin explicit immediate transaction for write isolation
            cursor = conn.cursor()
            cursor.execute("BEGIN IMMEDIATE")
            yield cursor
            conn.commit()
            return
        except Exception as exc:
            last_err = exc
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass

            if is_lock_error(exc):
                elapsed = time.monotonic() - start_time
                if attempt < max_retries:
                    delay = min(initial_delay * (backoff_factor ** (attempt - 1)), max_delay)
                    jitter = random.uniform(0, 0.03)
                    total_delay = delay + jitter
                    logger.warning(
                        f"Database '{db_name}' locked during '{operation_name}' "
                        f"(attempt {attempt}/{max_retries}, elapsed={elapsed:.3f}s). "
                        f"Retrying in {total_delay:.3f}s... Error: {exc}"
                    )
                    time.sleep(total_delay)
                    continue

            # Non-lock error or exhausted retries: re-raise immediately or raise DatabaseLockError
            break

    elapsed = time.monotonic() - start_time
    if last_err and is_lock_error(last_err):
        # Emit structured failure log
        logger.error(
            "DB_WRITE_TRANSACTION_FAILED",
            extra={
                "event": "DB_WRITE_TRANSACTION_FAILED",
                "db_name": db_name,
                "operation": operation_name,
                "retries_attempted": max_retries,
                "elapsed_seconds": elapsed,
                "error": str(last_err),
            },
        )
        raise DatabaseLockError(
            db_name=db_name,
            operation=operation_name,
            retries_attempted=max_retries,
            elapsed_seconds=elapsed,
            error_details=str(last_err),
        ) from last_err

    # Re-raise standard exception if not a lock error
    if last_err:
        raise last_err


def run_write_with_retry(
    conn: sqlite3.Connection,
    fn: Callable[[sqlite3.Connection], Any],
    operation_name: str = "write_function",
    max_retries: int = 5,
    initial_delay: float = 0.05,
    backoff_factor: float = 2.0,
    max_delay: float = 1.0,
    db_name: str = "database",
) -> Any:
    """Executes a custom write function with bounded retries and lock detection."""
    start_time = time.monotonic()
    last_err: Optional[Exception] = None

    for attempt in range(1, max_retries + 1):
        try:
            return fn(conn)
        except Exception as exc:
            last_err = exc
            if is_lock_error(exc):
                elapsed = time.monotonic() - start_time
                if attempt < max_retries:
                    delay = min(initial_delay * (backoff_factor ** (attempt - 1)), max_delay)
                    jitter = random.uniform(0, 0.03)
                    total_delay = delay + jitter
                    logger.warning(
                        f"Database '{db_name}' locked in callable '{operation_name}' "
                        f"(attempt {attempt}/{max_retries}, elapsed={elapsed:.3f}s). "
                        f"Retrying in {total_delay:.3f}s... Error: {exc}"
                    )
                    time.sleep(total_delay)
                    continue
            break

    elapsed = time.monotonic() - start_time
    if last_err and is_lock_error(last_err):
        logger.error(
            "DB_WRITE_TRANSACTION_FAILED",
            extra={
                "event": "DB_WRITE_TRANSACTION_FAILED",
                "db_name": db_name,
                "operation": operation_name,
                "retries_attempted": max_retries,
                "elapsed_seconds": elapsed,
                "error": str(last_err),
            },
        )
        raise DatabaseLockError(
            db_name=db_name,
            operation=operation_name,
            retries_attempted=max_retries,
            elapsed_seconds=elapsed,
            error_details=str(last_err),
        ) from last_err

    if last_err:
        raise last_err
