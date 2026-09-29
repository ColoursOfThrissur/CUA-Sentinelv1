"""Tool Gateway Module for CUA-Sentinel.

Single secure checkpoint through which every tool invocation runs.
Encapsulates tool registration, profile permissions, budget caps,
governance rules, audit logging, taint tracking, and idempotent execution.
"""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from pydantic import BaseModel, Field

class GatewayResponseEnvelope(BaseModel):
    """Canonical sealed response envelope structurally guaranteeing domain_success across ALL exits."""
    status: str
    domain_success: bool = Field(..., description="Mandatory boolean indicating domain-level operational success")
    reason: str = ""
    data: Any = None
    untrusted: bool = False
    origin: str
    span_id: str

from config.loader import (
    GATEWAY_VERSION,
    compute_prompt_hash,
    get_config_version,
    load_tool_registry,
)
from core.governance import GovernanceEngine, GovernanceViolation, HITLRequired
from core.scraper_sanitizer import scraper_sanitizer
from db.connections import get_audit_db, get_operational_db
try:
    from db.transaction import execute_write_transaction
except ImportError:
    from backend.db.transaction import execute_write_transaction

logger = logging.getLogger(__name__)


class ToolGateway:
    """Centralized enforcement gateway for all tool invocations."""

    # Gateway owns the name -> handler map
    _TOOL_HANDLERS: dict[str, Callable] = {}
    _active_mcp_manager: Any = None
    _active_model_manager: Any = None

    @staticmethod
    def _seal_envelope(
        status: str,
        domain_success: bool,
        origin: str,
        span_id: str,
        reason: str = "",
        data: Any = None,
        untrusted: bool = False,
    ) -> dict[str, Any]:
        """Structurally guarantees valid envelope schema via Pydantic validation."""
        env = GatewayResponseEnvelope(
            status=status,
            domain_success=domain_success,
            reason=reason,
            data=data,
            untrusted=untrusted,
            origin=origin,
            span_id=span_id,
        )
        return env.model_dump()

    @classmethod
    def register_tool_handler(cls, name: str, handler: Callable) -> None:
        """Register a tool handler in the gateway-owned map."""
        cls._TOOL_HANDLERS[name] = handler

    @classmethod
    def register_default_handlers(cls) -> None:
        """Register default tool handlers at startup. Lazy imports to avoid circular deps."""
        if cls._TOOL_HANDLERS:
            return  # Already registered

        handler_defs = {
            "web_search": ("tools.web_search", "WebSearchTool", "search"),
            "crawl_and_process": ("tools.link_manager", "LinkManager", "crawl_and_process"),
            "fetch_ticker_quote": ("tools.finance_tools", "FinanceTools", "fetch_ticker_quote"),
            "search_emails": ("core.email_engine", "EmailEngine", "search_emails"),
            "fetch_recent_emails": ("core.email_engine", "EmailEngine", "fetch_recent_emails"),
            "take_screenshot": ("tools.desktop_tool", "DesktopTool", "take_screenshot"),
            "get_active_window": ("tools.desktop_tool", "DesktopTool", "get_active_window"),
            "desktop_click": ("tools.desktop_tool", "DesktopTool", "click_coordinate"),
            "desktop_type": ("tools.desktop_tool", "DesktopTool", "type_text"),
            "app_launch": ("tools.desktop_tool", "DesktopTool", "app_launch"),
            "desktop_file_write": ("tools.desktop_tool", "DesktopTool", "desktop_file_write"),
            "fetch_rss": ("tools.web_search", "WebSearchTool", "fetch_feeds"),
        }
        for tool_name, (module_path, class_name, method_name) in handler_defs.items():
            try:
                import importlib
                mod = importlib.import_module(module_path)
                tool_cls = getattr(mod, class_name)
                instance = tool_cls()
                cls._TOOL_HANDLERS[tool_name] = getattr(instance, method_name)
                logger.debug(f"Registered handler: {tool_name} -> {module_path}.{class_name}.{method_name}")
            except Exception as e:
                logger.warning(f"Could not register handler for '{tool_name}': {e}")

        # Register typed Blender operations
        cls.register_typed_blender_handlers()

    @classmethod
    def register_typed_blender_handlers(cls) -> None:
        """Register typed Blender ops handlers (Pydantic verified, template rendered)."""
        from core import blender_ops as b_ops
        from core.mcp_manager import MCPManager

        def _make_handler(param_cls, template):
            async def _handler(**kwargs):
                from core.blender_ops import render_op_script, parse_op_output
                mcp_mgr = cls._active_mcp_manager or MCPManager.get_instance() or MCPManager()
                p = param_cls(**kwargs)
                script = render_op_script(template, p)
                res = await mcp_mgr.call_locked("blender", "execute_blender_code", {"code": script})
                return parse_op_output(res["output"])
            return _handler

        ops_map = {
            "blender:create_box": (b_ops.CreateBoxParams, b_ops._CREATE_BOX_TEMPLATE),
            "blender:create_sphere": (b_ops.CreateSphereParams, b_ops._CREATE_SPHERE_TEMPLATE),
            "blender:create_cylinder": (b_ops.CreateCylinderParams, b_ops._CREATE_CYLINDER_TEMPLATE),
            "blender:create_cone": (b_ops.CreateConeParams, b_ops._CREATE_CONE_TEMPLATE),
            "blender:create_torus": (b_ops.CreateTorusParams, b_ops._CREATE_TORUS_TEMPLATE),
            "blender:apply_subdivision": (b_ops.ApplySubdivisionParams, b_ops._APPLY_SUBDIVISION_TEMPLATE),
            "blender:apply_boolean": (b_ops.ApplyBooleanParams, b_ops._APPLY_BOOLEAN_TEMPLATE),
            "blender:apply_bevel": (b_ops.ApplyBevelParams, b_ops._APPLY_BEVEL_TEMPLATE),
            "blender:apply_array": (b_ops.ApplyArrayParams, b_ops._APPLY_ARRAY_TEMPLATE),
            "blender:set_smooth_shading": (b_ops.SetSmoothShadingParams, b_ops._SET_SMOOTH_SHADING_TEMPLATE),
            "blender:set_material": (b_ops.SetMaterialParams, b_ops._SET_MATERIAL_TEMPLATE),
            "blender:join_objects": (b_ops.JoinObjectsParams, b_ops._JOIN_OBJECTS_TEMPLATE),
            "blender:delete_object": (b_ops.DeleteObjectParams, b_ops._DELETE_OBJECT_TEMPLATE),
            "blender:clear_scene": (b_ops.ClearSceneParams, b_ops._CLEAR_SCENE_TEMPLATE),
            "blender:create_light": (b_ops.CreateLightParams, b_ops._CREATE_LIGHT_TEMPLATE),
            "blender:create_camera": (b_ops.CreateCameraParams, b_ops._CREATE_CAMERA_TEMPLATE),
            "blender:set_transform": (b_ops.SetTransformParams, b_ops._SET_TRANSFORM_TEMPLATE),
            "blender:get_manifest": (b_ops.GetManifestParams, b_ops._GET_MANIFEST_TEMPLATE),
            "blender:parent_object": (b_ops.ParentObjectParams, b_ops._PARENT_OBJECT_TEMPLATE),
            "blender:set_origin": (b_ops.SetOriginParams, b_ops._SET_ORIGIN_TEMPLATE),
            "blender:separate_mesh": (b_ops.SeparateMeshParams, b_ops._SEPARATE_MESH_TEMPLATE),
        }

        for tool_name, (param_cls, template) in ops_map.items():
            cls._TOOL_HANDLERS[tool_name] = _make_handler(param_cls, template)

        async def _build_progressive_handler(**kwargs):
            """v5 Progressive Pipeline (progressive_v2) - the ONLY build path."""
            from core.blender_pipeline.progressive_v2 import run_progressive_build, HierarchyLimits
            from core.model_manager import ModelManager
            
            mcp_mgr = cls._active_mcp_manager or MCPManager.get_instance() or MCPManager()
            mdl_mgr = cls._active_model_manager
            
            # Fallback: create model_manager if not set (lazy init)
            if mdl_mgr is None:
                from config.loader import load_system_config, load_model_registry
                config = load_system_config()
                registry = load_model_registry()
                mdl_mgr = ModelManager(config, registry)
                cls._active_model_manager = mdl_mgr
            
            description = kwargs.get("description") or kwargs.get("params", {}).get("name", "")
            task_id = kwargs.get("task_id", "progressive_build")
            
            res = await run_progressive_build(
                prompt=description,
                model_manager=mdl_mgr,
                task_id=task_id,
                mcp_manager=mcp_mgr,
                limits=HierarchyLimits(max_depth=3, max_children=10, max_total_nodes=30),
            )
            return {
                "ok": res.success,
                "status": res.completion_status.value,
                "total_nodes": res.total_nodes,
                "verified_nodes": res.verified_nodes,
                "failed_nodes": res.failed_nodes,
                "skipped_nodes": res.skipped_nodes,
                "blender_objects": res.blender_objects,
                "build_time_seconds": round(res.build_time_seconds, 2),
                "errors": res.errors,
            }

        async def _build_spec_handler(**kwargs):
            """v5 Progressive Pipeline is now the default and only pipeline."""
            return await _build_progressive_handler(**kwargs)

        async def _save_approved_handler(**kwargs):
            from core.spec3d.pipeline import Spec3DPipeline
            build_id = kwargs.get("build_id") or kwargs.get("id") or ""
            return await Spec3DPipeline.process_save_approved(build_id)

        async def _search_tools_handler(**kwargs):
            from core.tool_search_index import ToolSearchIndex
            query = kwargs.get("query") or ""
            limit = int(kwargs.get("limit", 3))
            max_tokens = int(kwargs.get("max_tokens", 800))

            mcp_mgr = cls._active_mcp_manager
            idx = getattr(cls, "_tool_search_index", None)
            if idx is None:
                idx = ToolSearchIndex(mcp_manager=mcp_mgr)
                cls._tool_search_index = idx
            else:
                idx.mcp_manager = mcp_mgr

            idx.build_index()
            return idx.search(query=query, limit=limit, max_tokens=max_tokens)

        cls._TOOL_HANDLERS["blender:build_spec"] = _build_spec_handler
        cls._TOOL_HANDLERS["blender:build_progressive"] = _build_progressive_handler
        cls._TOOL_HANDLERS["blender:save_approved"] = _save_approved_handler
        cls._TOOL_HANDLERS["search_tools"] = _search_tools_handler

    def __init__(
        self,
        governance: Optional[GovernanceEngine] = None,
        config: Optional[dict] = None,
        model_manager: Any = None,
        mcp_manager: Any = None,
    ):
        self.governance = governance
        self.config = config or {}
        self.model_manager = model_manager
        self._mcp_manager = mcp_manager

        if model_manager:
            ToolGateway._active_model_manager = model_manager
        if mcp_manager:
            ToolGateway._active_mcp_manager = mcp_manager

        self._taint_state: dict[str, bool] = {}
        self._taint_origins: dict[str, list[str]] = {}
        self.allowed_urls: set[str] = set()
        self.tool_call_counts: dict[str, int] = {}
        self.max_tool_calls_per_task: int = self.config.get("governance", {}).get("max_tool_calls_per_task", 50)
        self.log_only_gateway: bool = self.config.get("governance", {}).get("gateway_log_only", False)

    def is_tainted(self, task_id: str = "adhoc") -> bool:
        """Check if a task's run state is tainted. Checks in-memory cache first, then DB."""
        if task_id in self._taint_state:
            return self._taint_state[task_id]
        try:
            import sys
            base_agent_mod = sys.modules.get("agents.base_agent")
            db_getter = getattr(base_agent_mod, "get_operational_db", get_operational_db) if base_agent_mod else get_operational_db
            conn = db_getter()
            try:
                row = conn.execute(
                    "SELECT is_tainted FROM tasks WHERE task_id = ?", (task_id,)
                ).fetchone()
                if row and row["is_tainted"]:
                    self._taint_state[task_id] = True
                    return True
            finally:
                conn.close()
        except Exception as e:
            logger.critical(f"Database error reading task taint status for {task_id}: {e}. Failing closed to TAINTED.")
            return True
        return False

    def set_tainted(self, task_id: str, origin_tool: str = "unknown") -> None:
        """Mark a task's run state as tainted. Persists to DB for resume."""
        self._taint_state[task_id] = True
        if task_id not in self._taint_origins:
            self._taint_origins[task_id] = []
        if origin_tool not in self._taint_origins[task_id]:
            self._taint_origins[task_id].append(origin_tool)

        try:
            import sys
            base_agent_mod = sys.modules.get("agents.base_agent")
            db_getter = getattr(base_agent_mod, "get_operational_db", get_operational_db) if base_agent_mod else get_operational_db
            conn = db_getter()
            try:
                conn.execute(
                    "UPDATE tasks SET is_tainted = 1 WHERE task_id = ?", (task_id,)
                )
                conn.commit()
            finally:
                conn.close()
        except Exception as e:
            logger.debug(f"Could not persist taint for task {task_id}: {e}")

    def get_taint_origins(self, task_id: str) -> str:
        """Get a comma-separated string of tool names that caused taint."""
        origins = self._taint_origins.get(task_id, [])
        return ", ".join(origins) if origins else "untrusted tool return data"

    def _resolve_tool_handler(self, name: str, tool_instance: Any = None) -> Optional[Callable]:
        """Resolve callable handler for tool name (MCP bridge -> class map -> test override)."""
        if name.startswith("mcp:"):
            mcp_mgr = getattr(self, "_mcp_manager", None) or ToolGateway._active_mcp_manager
            if mcp_mgr:
                parts = name.split(":", 2)
                if len(parts) == 3:
                    app_id, tool_name = parts[1], parts[2]
                    async def _mcp_bridge(**kwargs):
                        return await mcp_mgr.call_tool(app_id, tool_name, kwargs)
                    return _mcp_bridge
            return None

        if not self._TOOL_HANDLERS:
            self.register_default_handlers()

        if name in self._TOOL_HANDLERS:
            return self._TOOL_HANDLERS[name]

        if tool_instance is not None:
            if callable(tool_instance):
                return tool_instance
            if hasattr(tool_instance, name) and callable(getattr(tool_instance, name)):
                return getattr(tool_instance, name)

        return None

    async def execute_tool(
        self,
        name: str,
        params: Optional[dict] = None,
        task_id: str = "adhoc",
        step_id: Optional[str] = None,
        tool_instance: Any = None,
        caller_name: Optional[str] = None,
        profile: Optional[dict] = None,
        profile_version: Optional[str] = None,
        model_id: Optional[str] = None,
        prompt_hash: Optional[str] = None,
    ) -> dict:
        """
        P0.1/P0.2 Single Tool Gateway:
        Centralized checkpoint through which every tool invocation runs.
        """
        params = params or {}
        span_id = f"span_{uuid.uuid4().hex[:12]}"

        config_ver = get_config_version()
        effective_model_id = model_id or (
            self.model_manager.get_model_for_workflow("ENDPOINT") if self.model_manager else "local-default"
        )
        effective_prompt_hash = prompt_hash or compute_prompt_hash(name)

        # 1. Registry Lookup (static tools + MCP runtime tools)
        registry = load_tool_registry().get("tools", {})
        tool_meta = registry.get(name)

        # 1a. MCP Tool Resolution
        _mcp_app_id = None
        if not tool_meta and name.startswith("mcp:"):
            try:
                parts = name.split(":", 2)
                if len(parts) == 3:
                    _mcp_app_id = parts[1]
                    mcp_mgr = getattr(self, "_mcp_manager", None) or ToolGateway._active_mcp_manager
                    if mcp_mgr:
                        mcp_entries = mcp_mgr.get_tool_registry_entries(_mcp_app_id)
                        tool_meta = mcp_entries.get(name)
            except Exception as mcp_err:
                logger.warning(f"MCP tool resolution failed for '{name}': {mcp_err}")

        # 1b. Honor App-level Auto-Approve / Trust App configuration
        _app_id = name.split(":", 2)[1] if name.startswith("mcp:") else (name.split(":", 1)[0] if ":" in name else None)
        if _app_id:
            mcp_mgr = getattr(self, "_mcp_manager", None) or ToolGateway._active_mcp_manager
            if mcp_mgr:
                conn = mcp_mgr.get_connection(_app_id)
                if conn and conn.security and conn.security.get("auto_approve"):
                    tool_meta = dict(tool_meta) if tool_meta else {}
                    tool_meta["auto_approve"] = True
                    tool_meta["risk_level"] = "L0"
                    tool_meta["taint_safe"] = True

        effective_caller = caller_name or "unknown_agent"
        if effective_caller.endswith("agent") and "_" not in effective_caller:
            effective_caller = f"{effective_caller[:-5]}_agent" if effective_caller.endswith("agent") else effective_caller

        # Task-keyed taint state
        task_tainted = self.is_tainted(task_id)
        taint_origins_str = self.get_taint_origins(task_id)

        def _log_audit_decision(decision: str, reason: str, result_data: Any = None):
            try:
                masked_in = scraper_sanitizer.mask(params)
                masked_out = scraper_sanitizer.mask(result_data) if result_data is not None else None
                conn = get_audit_db()
                try:
                    with execute_write_transaction(conn, operation_name="tool_gateway_audit_log", db_name="audit") as cur:
                        cur.execute(
                            """
                            INSERT INTO audit_logs (
                                log_id, run_id, task_id, step_id, who_actor, action_type, tool_name,
                                decision_summary, decision_factors, created_at
                            ) VALUES (?, ?, ?, ?, ?, 'TOOL_GATEWAY_DECISION', ?, ?, ?, ?)
                            """,
                            (
                                span_id,
                                f"run_{task_id}",
                                task_id,
                                step_id or "step_0",
                                effective_caller,
                                name,
                                json.dumps({"decision": decision, "reason": reason}, default=str),
                                json.dumps({
                                    "tool": name,
                                    "side_effect": tool_meta.get("side_effect") if tool_meta else "unknown",
                                    "risk_level": tool_meta.get("risk_level") if tool_meta else "unknown",
                                    "tainted": task_tainted,
                                    "taint_origins": taint_origins_str,
                                    "input": masked_in,
                                    "output": masked_out,
                                    "config_version": config_ver,
                                    "model_id": str(effective_model_id),
                                    "prompt_hash": str(effective_prompt_hash),
                                    "gateway_version": GATEWAY_VERSION,
                                    "profile_version": profile_version,
                                }, default=str),
                                datetime.now(timezone.utc).isoformat(),
                            ),
                        )
                finally:
                    conn.close()
            except Exception as audit_err:
                logger.warning(f"Failed to record tool gateway audit log: {audit_err}")

        if not tool_meta:
            reason = f"Unknown tool: '{name}' is not registered in tool_registry.json"
            logger.warning(f"GATEWAY DENIAL: {reason}")
            _log_audit_decision("DENIED", reason)
            return self._seal_envelope(
                status="denied",
                domain_success=False,
                reason=reason,
                origin=f"gateway:{name}",
                span_id=span_id,
            )

        # 1b. Profile Boundary Check
        if profile and "tools_allowed" in profile:
            allowed_by_profile = profile.get("tools_allowed", [])
            
            def _matches_profile(name, allowed_by_profile):
                if name in allowed_by_profile:
                    return True
                # Check wildcard patterns like 'mcp:*' or 'mcp:filesystem:*'
                for pattern in allowed_by_profile:
                    if '*' in pattern:
                        prefix = pattern.replace('*', '')
                        if name.startswith(prefix):
                            return True
                return False

            if not _matches_profile(name, allowed_by_profile):
                reason = f"Tool '{name}' denied: not permitted in agent profile '{profile.get('name')}'"
                logger.warning(f"PROFILE BOUNDARY DENIAL: {reason}")
                _log_audit_decision("DENIED", reason)
                return self._seal_envelope(
                    status="denied",
                    domain_success=False,
                    reason=reason,
                    origin=f"gateway:{name}",
                    span_id=span_id,
                )

        # 2. Budget Check
        current_calls = self.tool_call_counts.get(task_id, 0)
        if current_calls >= self.max_tool_calls_per_task:
            reason = f"Budget exceeded: task {task_id} reached maximum tool call limit ({self.max_tool_calls_per_task})"
            logger.warning(f"GATEWAY DENIAL: {reason}")
            _log_audit_decision("DENIED", reason)
            return self._seal_envelope(
                status="denied",
                domain_success=False,
                reason=reason,
                origin=f"gateway:{name}",
                span_id=span_id,
            )
        self.tool_call_counts[task_id] = current_calls + 1

        # 3. Governance Policy, Call-Time Emergency Stop/Safe Mode, & Taint Check
        if self.governance:
            try:
                self.governance.check_tool_execution_safety(
                    tool_name=name,
                    caller_agent=effective_caller,
                    task_id=task_id,
                    untrusted_present=task_tainted,
                    registry_meta=tool_meta,
                    taint_origins=taint_origins_str,
                    params=params,
                    read_private=tool_meta.get("reads_private_data", False),
                )
            except (GovernanceViolation, HITLRequired) as gv:
                reason = str(gv)
                logger.warning(f"GATEWAY DENIAL [{effective_caller} -> {name}]: {reason}")
                _log_audit_decision("DENIED", reason)
                if self.log_only_gateway:
                    logger.info(f"LOG-ONLY GATEWAY: allowing tool '{name}' despite denial: {reason}")
                else:
                    return self._seal_envelope(
                        status="denied",
                        domain_success=False,
                        reason=reason,
                        origin=f"gateway:{name}",
                        span_id=span_id,
                    )
            except Exception as ex:
                reason = f"Unexpected governance evaluation error: {ex}"
                logger.error(f"GATEWAY ERROR: {reason}")
                _log_audit_decision("ERROR", reason)
                return self._seal_envelope(
                    status="error",
                    domain_success=False,
                    reason=reason,
                    origin=f"gateway:{name}",
                    span_id=span_id,
                )

        # 4. Tool Execution Dispatch
        side_effect = tool_meta.get("side_effect", "read")
        timeout_sec = tool_meta.get("timeout_seconds", 30)
        effective_timeout = None if side_effect == "act" or timeout_sec <= 0 else timeout_sec

        try:
            # Idempotency Key for Side-Effecting Tools (write/act)
            idempotency_key = None
            if side_effect in ("write", "act") and step_id:
                params_hash = hashlib.sha256(json.dumps(params, sort_keys=True, default=str).encode()).hexdigest()[:12]
                idempotency_key = f"{task_id}_{step_id}_{name}_{params_hash}"

                try:
                    conn = get_operational_db()
                    try:
                        cached_op = conn.execute(
                            "SELECT current_state, recovery_strategy FROM operations WHERE operation_id = ?",
                            (idempotency_key,),
                        ).fetchone()
                        if cached_op and cached_op["current_state"] == "SUCCEEDED":
                            logger.info(f"Idempotent replay detected for tool '{name}' (key={idempotency_key}). Skipping side effect.")
                            _log_audit_decision("ALLOWED", f"Idempotent replay: skipped duplicate execution ({idempotency_key})", {"replayed": True})
                            return self._seal_envelope(
                                status="ok",
                                domain_success=True,
                                reason="idempotent_replay",
                                data={"idempotent_replay": True, "key": idempotency_key},
                                untrusted=tool_meta.get("returns_untrusted", False),
                                origin=f"{name}:{effective_caller}",
                                span_id=span_id,
                            )
                    finally:
                        conn.close()
                except Exception as idemp_err:
                    logger.debug(f"Idempotency lookup error: {idemp_err}")

            result_data = None
            handler = self._resolve_tool_handler(name, tool_instance)

            if handler is None:
                reason = f"No execution handler bound for registered tool '{name}'"
                logger.error(reason)
                _log_audit_decision("ERROR", reason)
                return self._seal_envelope(
                    status="error",
                    domain_success=False,
                    reason=reason,
                    origin=f"gateway:{name}",
                    span_id=span_id,
                )

            call_params = dict(params)
            # Pass task_id to handler so pipelines can use it for tracing
            call_params["task_id"] = task_id
            if name == "fetch_rss":
                if "feed_urls" not in call_params and "urls" in call_params:
                    call_params = {"feed_urls": call_params["urls"]}
                elif "feed_urls" not in call_params:
                    call_params = {"feed_urls": []}

            # Taint Tracking: Task-keyed taint set BEFORE dispatch
            returns_untrusted = tool_meta.get("returns_untrusted", False)
            if returns_untrusted:
                self.set_tainted(task_id, origin_tool=name)
                logger.info(f"RUN STATE TAINTED: tool '{name}' marked untrusted before execution for task {task_id}.")

            if inspect.iscoroutinefunction(handler):
                if effective_timeout:
                    result_data = await asyncio.wait_for(handler(**call_params), timeout=effective_timeout)
                else:
                    result_data = await handler(**call_params)
            else:
                if effective_timeout:
                    loop = asyncio.get_running_loop()
                    result_data = await asyncio.wait_for(
                        loop.run_in_executor(None, lambda: handler(**call_params)),
                        timeout=effective_timeout,
                    )
                else:
                    result_data = handler(**call_params)

            # Record side-effecting operation as SUCCEEDED for idempotency
            if idempotency_key and step_id:
                try:
                    conn = get_operational_db()
                    try:
                        conn.execute(
                            """
                            INSERT OR REPLACE INTO operations (
                                operation_id, task_id, step_id, tool_name,
                                target_resource_canonical, recovery_strategy, current_state, updated_at
                            ) VALUES (?, ?, ?, ?, ?, 'IDEMPOTENT_RETRY', 'SUCCEEDED', ?)
                            """,
                            (
                                idempotency_key,
                                task_id,
                                step_id,
                                name,
                                f"tool://{name}",
                                datetime.now(timezone.utc).isoformat(),
                            ),
                        )
                        conn.commit()
                    finally:
                        conn.close()
                except Exception as op_rec_err:
                    logger.debug(f"Could not record operation success: {op_rec_err}")

            # Record permitted URLs returned by tools
            if result_data:
                try:
                    found_urls = re.findall(r'https?://[^\s<>"\')]+', str(result_data))
                    if found_urls:
                        self.allowed_urls.update(found_urls)
                except Exception:
                    pass

            domain_success = True
            if isinstance(result_data, dict):
                if result_data.get("ok") is False or "error" in result_data:
                    domain_success = False
                elif tool_meta.get("domain_success_path") == "data.ok":
                    domain_success = bool(result_data.get("ok", True))

            _log_audit_decision("ALLOWED", "Execution successful", result_data)

            return self._seal_envelope(
                status="ok",
                domain_success=domain_success,
                reason="",
                data=result_data,
                untrusted=returns_untrusted,
                origin=f"{name}:{effective_caller}",
                span_id=span_id,
            )

        except asyncio.TimeoutError:
            reason = f"Tool '{name}' timed out after {effective_timeout}s"
            logger.warning(reason)
            _log_audit_decision("TIMEOUT", reason)
            return self._seal_envelope(
                status="error",
                domain_success=False,
                reason=reason,
                origin=f"gateway:{name}",
                span_id=span_id,
            )
        except Exception as e:
            reason = f"Tool '{name}' failed with error: {str(e)}"
            logger.error(reason)
            _log_audit_decision("ERROR", reason)
            return self._seal_envelope(
                status="error",
                domain_success=False,
                reason=reason,
                origin=f"gateway:{name}",
                span_id=span_id,
            )
