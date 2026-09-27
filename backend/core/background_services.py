"""Lifecycle management for application-owned background coroutines and managed services."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections.abc import Coroutine
from datetime import datetime, timezone
import logging
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class BackgroundTaskGroup:
    """Tracks named application tasks and cancels them during shutdown."""

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task[Any]] = {}

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self._tasks)

    def start(self, name: str, coroutine: Coroutine[Any, Any, Any]) -> asyncio.Task[Any]:
        if name in self._tasks:
            coroutine.close()
            raise ValueError(f"Background task '{name}' is already running")

        task = asyncio.create_task(coroutine, name=f"sentinel:{name}")
        self._tasks[name] = task
        task.add_done_callback(lambda finished: self._record_completion(name, finished))
        return task

    def _record_completion(self, name: str, task: asyncio.Task[Any]) -> None:
        if self._tasks.get(name) is task:
            self._tasks.pop(name, None)

        if task.cancelled():
            logger.info("Background task stopped: %s", name)
            return

        try:
            error = task.exception()
        except asyncio.CancelledError:
            return

        if error is not None:
            logger.exception("Background task failed: %s", name, exc_info=error)
        else:
            logger.warning("Background task exited unexpectedly: %s", name)

    async def stop(self) -> None:
        tasks = tuple(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()


class ManagedService(ABC):
    """Base interface for managed background services with health, lifecycle, and safe-mode hooks."""

    def __init__(self, name: str):
        self.name = name
        self.started_at: Optional[str] = None
        self.last_heartbeat: Optional[str] = None
        self.is_running: bool = False
        self.in_safe_mode: bool = False
        self.last_error: Optional[str] = None

    async def start(self) -> None:
        """Starts the service background activity."""
        self.is_running = True
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.last_heartbeat = self.started_at

    async def stop(self) -> None:
        """Stops the service gracefully."""
        self.is_running = False

    def is_healthy(self) -> bool:
        """Returns True if the service is operating normally."""
        return self.is_running and self.last_error is None

    def on_safe_mode(self, enabled: bool) -> None:
        """Invoked when safe mode is toggled by Watchdog or User."""
        self.in_safe_mode = enabled
        logger.info(f"Service '{self.name}' notified of safe-mode: {enabled}")

    def get_status(self) -> Dict[str, Any]:
        """Returns a snapshot of service state and health."""
        return {
            "name": self.name,
            "is_running": self.is_running,
            "is_healthy": self.is_healthy(),
            "in_safe_mode": self.in_safe_mode,
            "started_at": self.started_at,
            "last_heartbeat": self.last_heartbeat,
            "last_error": self.last_error,
        }


class ManagedCoroutineService(ManagedService):
    """Adapts an async background loop function into a ManagedService."""

    def __init__(self, name: str, coroutine_fn: Callable[[], Coroutine[Any, Any, Any]]):
        super().__init__(name=name)
        self._coroutine_fn = coroutine_fn
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        if self.is_running:
            return
        self.is_running = True
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.last_heartbeat = self.started_at
        self.last_error = None

        async def _wrapper():
            try:
                await self._coroutine_fn()
            except asyncio.CancelledError:
                pass
            except Exception as e:
                self.last_error = str(e)
                logger.error(f"Managed service '{self.name}' crashed: {e}")
            finally:
                self.is_running = False

        self._task = asyncio.create_task(_wrapper(), name=f"managed:{self.name}")

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self.is_running = False


class ServiceManager:
    """Central registry and lifecycle manager for all Sentinel background services."""

    def __init__(self):
        self._services: Dict[str, ManagedService] = {}

    def register(self, service: ManagedService) -> None:
        """Registers a managed service."""
        self._services[service.name] = service

    def get(self, name: str) -> Optional[ManagedService]:
        return self._services.get(name)

    async def start_all(self) -> None:
        for name, service in self._services.items():
            try:
                await service.start()
                logger.info(f"Started managed service: {name}")
            except Exception as e:
                logger.error(f"Failed to start service '{name}': {e}")

    async def stop_all(self) -> None:
        for name, service in reversed(list(self._services.items())):
            try:
                await service.stop()
                logger.info(f"Stopped managed service: {name}")
            except Exception as e:
                logger.error(f"Error stopping service '{name}': {e}")

    def on_safe_mode(self, enabled: bool) -> None:
        for service in self._services.values():
            try:
                service.on_safe_mode(enabled)
            except Exception as e:
                logger.error(f"Error notifying service '{service.name}' of safe-mode: {e}")

    def get_health_summary(self) -> Dict[str, Any]:
        return {
            "all_healthy": all(s.is_healthy() for s in self._services.values()),
            "services": {name: s.get_status() for name, s in self._services.items()},
        }


service_manager = ServiceManager()
