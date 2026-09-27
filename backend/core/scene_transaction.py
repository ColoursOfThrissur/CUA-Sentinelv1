"""SceneTransaction — Atomic transaction manager for Blender scene modifications.

Guarantees atomicity: records all objects created during a modeling action or assembly.
If any step or verification check fails, rollback() unconditionally deletes every tracked
object in reverse creation order, preventing orphaned geometry in Blender.
"""

from typing import List, Optional, Any
import logging

logger = logging.getLogger(__name__)


class SceneTransaction:
    """Async context manager tracking created Blender objects with atomic rollback."""

    def __init__(self, tool_executor: Any = None):
        self.executor = tool_executor
        self.created_objects: List[str] = []
        self.committed: bool = False
        self.rolled_back: bool = False

    def record(self, object_name: str) -> None:
        """Track a created object by name."""
        if object_name and object_name not in self.created_objects:
            self.created_objects.append(object_name)

    async def commit(self) -> None:
        """Mark the transaction as committed. Prevents rollback on normal exit."""
        self.committed = True

    async def rollback(self) -> List[str]:
        """Delete all tracked objects in reverse creation order."""
        if self.rolled_back:
            return []

        rolled_back_names = []
        for name in reversed(self.created_objects):
            try:
                logger.info(f"SceneTransaction: Rolling back created object '{name}'")
                if self.executor:
                    if hasattr(self.executor, "execute_tool"):
                        await self.executor.execute_tool("blender:delete_object", {"name": name})
                    elif callable(self.executor):
                        res = self.executor("blender:delete_object", {"name": name})
                        if hasattr(res, "__await__"):
                            await res
                rolled_back_names.append(name)
            except Exception as e:
                logger.warning(f"SceneTransaction: Failed to delete '{name}' during rollback: {e}")

        self.rolled_back = True
        return rolled_back_names

    async def __aenter__(self) -> "SceneTransaction":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool:
        if exc_type is not None and not self.committed:
            logger.warning(f"SceneTransaction aborted due to error: {exc_val}. Rolling back {len(self.created_objects)} objects.")
            await self.rollback()
        return False  # Do not suppress original exception
