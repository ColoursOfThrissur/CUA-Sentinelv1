"""SceneTransaction — Atomic transaction manager for Blender scene modifications.

Guarantees atomicity: records all objects created during a modeling action or assembly.
If any step or verification check fails, rollback() unconditionally deletes every tracked
object in reverse creation order, preventing orphaned geometry in Blender.

Per BLENDER_GEOMETRY_CALCULATIONS.md Section 14:
- Every transaction has a unique generation_id
- All created objects are tagged with sentinel_generation_id
- Rollback only removes objects from THIS generation (never user objects)
- Commit marks objects as permanent
"""

from typing import List, Dict, Optional, Any
import logging
import uuid

logger = logging.getLogger(__name__)


def generate_generation_id() -> str:
    """Generate unique generation ID for this transaction."""
    return f"gen_{uuid.uuid4().hex[:12]}"


# Template to set Blender custom properties on created objects
_SET_METADATA_TEMPLATE = '''
import bpy
import json
params = json.loads(PARAMS_JSON)
obj = bpy.data.objects.get(params["name"])
if obj:
    obj["sentinel_object_id"] = params.get("object_id", params["name"])
    obj["sentinel_generation_id"] = params["generation_id"]
    if params.get("parent_id"):
        obj["sentinel_parent_id"] = params["parent_id"]
    if params.get("role"):
        obj["sentinel_role"] = params["role"]
    result = {"ok": True, "name": obj.name}
else:
    result = {"ok": False, "error": f"Object '{params['name']}' not found"}
print("SENTINEL_OUTPUT_START" + json.dumps(result) + "SENTINEL_OUTPUT_END")
'''

# Template to mark object as committed
_COMMIT_OBJECT_TEMPLATE = '''
import bpy
import json
params = json.loads(PARAMS_JSON)
obj = bpy.data.objects.get(params["name"])
if obj:
    obj["sentinel_committed"] = True
    result = {"ok": True}
else:
    result = {"ok": False}
print("SENTINEL_OUTPUT_START" + json.dumps(result) + "SENTINEL_OUTPUT_END")
'''

# Template to delete only if generation_id matches (safe rollback)
_SAFE_DELETE_TEMPLATE = '''
import bpy
import json
params = json.loads(PARAMS_JSON)
obj = bpy.data.objects.get(params["name"])
if obj:
    obj_gen = obj.get("sentinel_generation_id", "")
    if obj_gen == params["generation_id"]:
        bpy.data.objects.remove(obj, do_unlink=True)
        result = {"ok": True, "deleted": True}
    else:
        result = {"ok": True, "deleted": False, "reason": "generation_id mismatch"}
else:
    result = {"ok": True, "deleted": False, "reason": "not found"}
print("SENTINEL_OUTPUT_START" + json.dumps(result) + "SENTINEL_OUTPUT_END")
'''


class SceneTransaction:
    """Async context manager tracking created Blender objects with atomic rollback.
    
    Features:
    - Unique generation_id per transaction
    - Tags all created objects with sentinel_generation_id
    - Safe rollback only removes objects from this generation
    - Commit marks objects as permanent
    """

    def __init__(self, tool_executor: Any = None, generation_id: Optional[str] = None):
        self.executor = tool_executor
        self.generation_id = generation_id or generate_generation_id()
        self.created_objects: List[Dict[str, Any]] = []  # [{name, object_id, parent_id, role}]
        self.committed: bool = False
        self.rolled_back: bool = False

    def record(
        self,
        object_name: str,
        object_id: Optional[str] = None,
        parent_id: Optional[str] = None,
        role: Optional[str] = None,
    ) -> None:
        """Track a created object with metadata."""
        if not object_name:
            return
        if any(o["name"] == object_name for o in self.created_objects):
            return
        self.created_objects.append({
            "name": object_name,
            "object_id": object_id or object_name,
            "parent_id": parent_id,
            "role": role,
        })

    async def tag_object_metadata(self, obj_info: Dict[str, Any]) -> bool:
        """Set sentinel custom properties on a Blender object."""
        if not self.executor:
            return False
        try:
            params = {
                "name": obj_info["name"],
                "object_id": obj_info.get("object_id", obj_info["name"]),
                "generation_id": self.generation_id,
                "parent_id": obj_info.get("parent_id"),
                "role": obj_info.get("role"),
            }
            await self._execute_internal_script(_SET_METADATA_TEMPLATE, params)
            return True
        except Exception as e:
            logger.warning(f"Failed to tag metadata for '{obj_info['name']}': {e}")
            return False

    async def commit(self) -> None:
        """Mark the transaction as committed and tag all objects as permanent."""
        self.committed = True
        for obj_info in self.created_objects:
            try:
                await self._execute_internal_script(
                    _COMMIT_OBJECT_TEMPLATE,
                    {"name": obj_info["name"]}
                )
            except Exception as e:
                logger.warning(f"Failed to mark '{obj_info['name']}' as committed: {e}")

    async def rollback(self) -> List[str]:
        """Delete only objects from this generation in reverse creation order."""
        if self.rolled_back:
            return []

        rolled_back_names = []
        for obj_info in reversed(self.created_objects):
            name = obj_info["name"]
            try:
                logger.info(f"SceneTransaction[{self.generation_id}]: Rolling back '{name}'")
                # Use safe delete that checks generation_id
                result = await self._execute_internal_script(
                    _SAFE_DELETE_TEMPLATE,
                    {"name": name, "generation_id": self.generation_id}
                )
                if result and result.get("deleted"):
                    rolled_back_names.append(name)
                elif result:
                    logger.debug(f"Skipped '{name}': {result.get('reason')}")
            except Exception as e:
                # Fallback to regular delete if internal script fails
                logger.warning(f"Safe delete failed for '{name}': {e}, trying regular delete")
                try:
                    await self._call_tool("blender:delete_object", {"name": name})
                    rolled_back_names.append(name)
                except Exception as e2:
                    logger.warning(f"Failed to delete '{name}' during rollback: {e2}")

        self.rolled_back = True
        return rolled_back_names

    async def _execute_internal_script(self, template: str, params: dict) -> Optional[dict]:
        """Execute an internal Blender script via MCP."""
        import json
        script = f"PARAMS_JSON = {json.dumps(params)!r}\n" + template
        
        if hasattr(self.executor, "call_internal"):
            return await self.executor.call_internal("execute_blender_code", {"code": script})
        elif hasattr(self.executor, "call_locked"):
            from core.blender_ops import parse_op_output
            raw = await self.executor.call_locked("blender", "execute_blender_code", {"code": script})
            if isinstance(raw, dict) and "output" in raw:
                return parse_op_output(raw["output"])
            return raw if isinstance(raw, dict) else None
        return None

    async def _call_tool(self, tool_name: str, args: dict) -> Any:
        """Call a Blender tool via the executor."""
        if hasattr(self.executor, "execute_tool"):
            return await self.executor.execute_tool(tool_name, args)
        elif callable(self.executor):
            res = self.executor(tool_name, args)
            if hasattr(res, "__await__"):
                return await res
            return res
        return None

    async def __aenter__(self) -> "SceneTransaction":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool:
        if exc_type is not None and not self.committed:
            logger.warning(
                f"SceneTransaction[{self.generation_id}] aborted: {exc_val}. "
                f"Rolling back {len(self.created_objects)} objects."
            )
            await self.rollback()
        return False  # Do not suppress original exception
