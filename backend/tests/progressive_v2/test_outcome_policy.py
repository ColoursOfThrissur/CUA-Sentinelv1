from __future__ import annotations

import pytest

from core.blender_pipeline.progressive_v2.manifest import CompletionStatus
from core.blender_pipeline.progressive_v2.outcome_policy import TaskDisposition, task_disposition


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (CompletionStatus.SUCCESS, TaskDisposition.DONE),
        (CompletionStatus.COMPLETED_DEGRADED, TaskDisposition.DONE_WITH_WARNINGS),
        (CompletionStatus.COMMITTED_UNVERIFIED, TaskDisposition.NOT_DONE),
        (CompletionStatus.PLANNED_ONLY, TaskDisposition.NOT_DONE),
        (CompletionStatus.FAILED, TaskDisposition.NOT_DONE),
        ("future_status", TaskDisposition.NOT_DONE),
        (None, TaskDisposition.NOT_DONE),
    ],
)
def test_task_disposition_is_fail_closed(status, expected):
    assert task_disposition(status) is expected
