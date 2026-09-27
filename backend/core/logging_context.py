"""
Structured logging context: correlation IDs, task IDs, step IDs, and approval IDs.
Uses Python contextvars for safe propagation across async tasks.
"""

from contextlib import contextmanager
import contextvars
import logging
import uuid
from typing import Any, Dict, Generator, Optional

_correlation_id_var = contextvars.ContextVar("correlation_id", default="")
_task_id_var = contextvars.ContextVar("task_id", default="")
_step_id_var = contextvars.ContextVar("step_id", default="")
_approval_id_var = contextvars.ContextVar("approval_id", default="")


class StructuredCorrelationFilter(logging.Filter):
    """Logging filter that injects correlation context variables into every LogRecord."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = _correlation_id_var.get() or "-"
        record.task_id = _task_id_var.get() or "-"
        record.step_id = _step_id_var.get() or "-"
        record.approval_id = _approval_id_var.get() or "-"
        return True


def get_current_log_context() -> Dict[str, str]:
    """Returns the current structured logging context dictionary."""
    return {
        "correlation_id": _correlation_id_var.get(),
        "task_id": _task_id_var.get(),
        "step_id": _step_id_var.get(),
        "approval_id": _approval_id_var.get(),
    }


@contextmanager
def bind_log_context(
    correlation_id: Optional[str] = None,
    task_id: Optional[str] = None,
    step_id: Optional[str] = None,
    approval_id: Optional[str] = None,
) -> Generator[Dict[str, str], None, None]:
    """
    Context manager to bind correlation identifiers for the duration of a block.
    Restores previous values upon exit.
    """
    token_corr = _correlation_id_var.set(
        correlation_id or _correlation_id_var.get() or f"corr_{uuid.uuid4().hex[:10]}"
    )
    token_task = _task_id_var.set(task_id or _task_id_var.get())
    token_step = _step_id_var.set(step_id or _step_id_var.get())
    token_appr = _approval_id_var.set(approval_id or _approval_id_var.get())

    try:
        yield get_current_log_context()
    finally:
        _correlation_id_var.reset(token_corr)
        _task_id_var.reset(token_task)
        _step_id_var.reset(token_step)
        _approval_id_var.reset(token_appr)
