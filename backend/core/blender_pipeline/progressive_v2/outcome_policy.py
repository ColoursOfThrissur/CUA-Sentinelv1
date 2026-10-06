"""Fail-closed mapping from V2 build outcomes to task completion semantics."""

from __future__ import annotations

from enum import Enum
from typing import Any

from .manifest import CompletionStatus


class TaskDisposition(str, Enum):
    DONE = "done"
    DONE_WITH_WARNINGS = "done_with_warnings"
    NOT_DONE = "not_done"


def task_disposition(status: Any) -> TaskDisposition:
    """Map only known V2 statuses; absent or future values are not success."""
    try:
        normalized = status if isinstance(status, CompletionStatus) else CompletionStatus(str(status))
    except (TypeError, ValueError):
        return TaskDisposition.NOT_DONE
    if normalized is CompletionStatus.SUCCESS:
        return TaskDisposition.DONE
    if normalized is CompletionStatus.COMPLETED_DEGRADED:
        return TaskDisposition.DONE_WITH_WARNINGS
    return TaskDisposition.NOT_DONE
