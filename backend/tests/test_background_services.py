import asyncio
import os
import sys

import pytest


BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from core.background_services import BackgroundTaskGroup


@pytest.mark.asyncio
async def test_background_task_group_tracks_and_cancels_tasks():
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def worker():
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    group = BackgroundTaskGroup()
    group.start("worker", worker())
    await started.wait()

    assert group.names == ("worker",)

    await group.stop()

    assert cancelled.is_set()
    assert group.names == ()


@pytest.mark.asyncio
async def test_background_task_group_rejects_duplicate_names():
    group = BackgroundTaskGroup()

    async def worker():
        await asyncio.Event().wait()

    group.start("worker", worker())
    with pytest.raises(ValueError, match="already running"):
        group.start("worker", worker())

    await group.stop()


@pytest.mark.asyncio
async def test_managed_service_lifecycle_and_safe_mode():
    from core.background_services import ManagedCoroutineService, ServiceManager

    loop_active = asyncio.Event()
    stop_event = asyncio.Event()

    async def sample_loop():
        loop_active.set()
        await stop_event.wait()

    svc = ManagedCoroutineService("test_telemetry", sample_loop)
    manager = ServiceManager()
    manager.register(svc)

    await manager.start_all()
    await loop_active.wait()

    assert svc.is_running
    assert svc.is_healthy()
    status = svc.get_status()
    assert status["name"] == "test_telemetry"
    assert status["is_running"] is True

    # Safe mode toggle
    manager.on_safe_mode(True)
    assert svc.in_safe_mode is True

    # Stop all
    stop_event.set()
    await manager.stop_all()
    assert not svc.is_running

