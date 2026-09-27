"""MCP (Model Context Protocol) Manager — connection lifecycle, tool discovery, and invocation."""

import os
import logging
import asyncio
import yaml
from dataclasses import dataclass, field
from typing import Literal, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).parent.parent / "config" / "mcp_apps.yaml"
LOCK_PATH = Path(__file__).parent.parent / "config" / "mcp_tools.lock.json"

class MCPTimeoutError(Exception):
    """Raised when an MCP tool invocation exceeds its timeout."""
    pass

class MCPToolError(Exception):
    """Raised when an MCP tool returns an error flag."""
    pass

class LockMismatchError(Exception):
    """Raised when discovered tool schema diverges from mcp_tools.lock.json."""
    pass

class LockViolationError(Exception):
    """Raised when an unapproved tool is requested via call_locked."""
    pass

def compute_schema_hash(schema: dict) -> str:
    """Compute canonical SHA-256 hash of an MCP tool inputSchema."""
    import hashlib
    import json
    return hashlib.sha256(
        json.dumps(schema or {}, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

@dataclass
class MCPToolDescriptor:
    name: str
    description: str
    input_schema: dict
    app_id: str

@dataclass 
class MCPAppConnection:
    app_id: str
    display_name: str
    icon: str
    transport: Literal["stdio", "http"]
    command: str | None = None
    args: list[str] = field(default_factory=list)
    url: str | None = None
    env: dict[str, str] = field(default_factory=dict)
    enabled: bool = False
    status: Literal["connected", "disconnected", "connecting", "error"] = "disconnected"
    error_message: str | None = None
    discovered_tools: list[MCPToolDescriptor] = field(default_factory=list)
    description: str = ""
    security: dict = field(default_factory=lambda: {"default_side_effect": "read", "default_risk_level": "L2", "returns_untrusted": True})
    scene_state: str = "IDLE"
    # Internal runtime state (not persisted)
    _session: Any = field(default=None, repr=False)
    _runner_task: Any = field(default=None, repr=False)
    _stop_event: Any = field(default=None, repr=False)
    _stderr_buffer: Any = field(default=None, repr=False)


ENV_ALLOWLIST = {
    "SYSTEMROOT", "TEMP", "TMP", "PATH", "USERPROFILE",
    "APPDATA", "LOCALAPPDATA", "PYTHONIOENCODING", "PATHEXT"
}


class MCPManager:
    """Manages all MCP app connections, tool discovery, and tool invocation."""
    
    ENV_ALLOWLIST = ENV_ALLOWLIST
    _instance: Optional["MCPManager"] = None

    @classmethod
    def get_instance(cls) -> Optional["MCPManager"]:
        return cls._instance

    @classmethod
    def filter_env(cls, extra_env: dict = None) -> dict:
        """Strip sensitive host environment variables, retaining only allowed OS variables."""
        clean = {k: os.environ[k] for k in cls.ENV_ALLOWLIST if k in os.environ}
        if extra_env:
            for k, v in extra_env.items():
                if v:
                    clean[k] = v
        return clean
    
    def __init__(self):
        self._connections: dict[str, MCPAppConnection] = {}
        self._lock = asyncio.Lock()
        self._config_path = CONFIG_PATH
        MCPManager._instance = self
    
    def load_config(self) -> dict:
        """Load app configs from mcp_apps.yaml."""
        if not self._config_path.exists():
            return {"apps": {}}
        with open(self._config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {"apps": {}}
    
    def load_lock(self) -> dict:
        """Load static tool specifications and schema hashes from mcp_tools.lock.json."""
        if not LOCK_PATH.exists():
            return {"apps": {}}
        with open(LOCK_PATH, "r", encoding="utf-8") as f:
            import json
            return json.load(f) or {"apps": {}}
    def get_locked_tool_meta(self, app_id: str, tool_name: str) -> dict | None:
        """Returns this tool's static governance metadata from mcp_tools.lock.json,
        or None if the tool has no lockfile entry (i.e. no restriction declared)."""
        lock = self.load_lock()
        return lock.get("apps", {}).get(app_id, {}).get("tools", {}).get(tool_name)
    
    def save_config(self, config: dict) -> None:
        """Persist app configs to mcp_apps.yaml."""
        with open(self._config_path, "w", encoding="utf-8") as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)
    
    def initialize_from_config(self) -> None:
        """Load all configured apps into memory (disconnected state)."""
        config = self.load_config()
        for app_id, app_cfg in config.get("apps", {}).items():
            conn = MCPAppConnection(
                app_id=app_id,
                display_name=app_cfg.get("display_name", app_id),
                icon=app_cfg.get("icon", "plug"),
                transport=app_cfg.get("transport", "stdio"),
                command=app_cfg.get("command"),
                args=app_cfg.get("args", []),
                url=app_cfg.get("url"),
                env=app_cfg.get("env", {}),
                enabled=app_cfg.get("enabled", False),
                description=app_cfg.get("description", ""),
                security=app_cfg.get("security", {}),
            )
            self._connections[app_id] = conn
    
    async def _stop_runner_task(self, conn: MCPAppConnection) -> None:
        """Signal and wait for the connection runner task to exit cleanly."""
        if conn._stop_event and not conn._stop_event.is_set():
            conn._stop_event.set()

        if conn._runner_task and not conn._runner_task.done():
            try:
                await asyncio.wait_for(asyncio.shield(conn._runner_task), timeout=5.0)
            except (asyncio.TimeoutError, Exception):
                conn._runner_task.cancel()
                try:
                    await conn._runner_task
                except (asyncio.CancelledError, Exception):
                    pass

        conn._runner_task = None
        conn._stop_event = None
        conn._session = None

    async def connect_app(self, app_id: str) -> MCPAppConnection:
        """Start an MCP server connection and discover its tools."""
        async with self._lock:
            conn = self._connections.get(app_id)
            if not conn:
                raise ValueError(f"Unknown app: {app_id}")

            if conn.status == "connected" and conn._session:
                return conn

            # Stop any previously lingering runner task
            await self._stop_runner_task(conn)

            # Pre-validate required environment variables for known servers
            if app_id == "brave_search":
                key = conn.env.get("BRAVE_API_KEY") or os.environ.get("BRAVE_API_KEY")
                if not key:
                    err = "BRAVE_API_KEY environment variable is required to connect to Brave Search. Please configure your API key."
                    conn.status = "error"
                    conn.error_message = err
                    raise ValueError(err)

            conn.status = "connecting"
            conn.error_message = None

            loop = asyncio.get_running_loop()
            ready_future = loop.create_future()

            if conn.transport == "stdio":
                runner = asyncio.create_task(self._run_stdio_session(conn, ready_future))
                conn._runner_task = runner
            elif conn.transport == "http":
                runner = asyncio.create_task(self._run_http_session(conn, ready_future))
                conn._runner_task = runner
            else:
                conn.status = "error"
                conn.error_message = f"Unknown transport: {conn.transport}"
                raise ValueError(f"Unknown transport: {conn.transport}")

            try:
                await asyncio.wait_for(ready_future, timeout=30.0)
                await self._sync_catalog_on_connect(conn)
                logger.info(f"MCP connected: {conn.display_name} ({len(conn.discovered_tools)} tools)")
                return conn
            except Exception as e:
                await self._stop_runner_task(conn)
                raise

    async def _run_stdio_session(self, conn: MCPAppConnection, ready_future: asyncio.Future) -> None:
        """Dedicated runner task for stdio MCP connections with environment isolation."""
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        import tempfile

        clean_env = self.filter_env(conn.env)

        # Check lockfile for pinned command and args
        lock = self.load_lock()
        app_lock = lock.get("apps", {}).get(conn.app_id, {})
        server_spec = app_lock.get("server", {})
        command = server_spec.get("command") or conn.command
        args = server_spec.get("args") if "args" in server_spec else conn.args

        server_params = StdioServerParameters(
            command=command,
            args=args,
            env=clean_env,
        )

        stop_event = asyncio.Event()
        conn._stop_event = stop_event

        # Use TemporaryFile which has a real OS file descriptor required by subprocess.Popen on Windows
        stderr_file = tempfile.TemporaryFile(mode="w+", encoding="utf-8")
        conn._stderr_buffer = stderr_file

        try:
            async with stdio_client(server_params, errlog=stderr_file) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    conn._session = session

                    # Discover and verify tools within the runner while session is initialized
                    await self._discover_tools(conn)
                    conn.status = "connected"
                    conn.error_message = None
                    conn.enabled = True
                    self._update_config_enabled(conn.app_id, True)

                    if not ready_future.done():
                        ready_future.set_result(True)

                    # Keep runner task alive until disconnect is signaled
                    await stop_event.wait()
        except Exception as exc:
            err_detail = ""
            try:
                stderr_file.seek(0)
                err_detail = stderr_file.read().strip()
            except Exception:
                pass
            msg = f"{exc}"
            if err_detail:
                msg = f"{msg} (stderr: {err_detail})"
            conn.status = "error"
            conn.error_message = msg
            conn._session = None
            conn.discovered_tools = []
            logger.error(f"MCP connection error for {conn.app_id}: {msg}")
            if not ready_future.done():
                ready_future.set_exception(RuntimeError(msg))
        finally:
            conn._session = None
            try:
                stderr_file.close()
            except Exception:
                pass
            conn._stderr_buffer = None
            if conn.status == "connected":
                conn.status = "disconnected"
            if not ready_future.done():
                ready_future.set_exception(RuntimeError("Connection terminated before initialization"))

    async def _run_http_session(self, conn: MCPAppConnection, ready_future: asyncio.Future) -> None:
        """Dedicated runner task for HTTP MCP connections."""
        from mcp import Client
        stop_event = asyncio.Event()
        conn._stop_event = stop_event

        try:
            client = Client(conn.url)
            async with client as session:
                conn._session = session
                await self._discover_tools(conn)
                conn.status = "connected"
                conn.error_message = None
                conn.enabled = True
                self._update_config_enabled(conn.app_id, True)

                if not ready_future.done():
                    ready_future.set_result(True)

                await stop_event.wait()
        except Exception as exc:
            conn.status = "error"
            conn.error_message = str(exc)
            conn._session = None
            conn.discovered_tools = []
            logger.error(f"MCP HTTP connection error for {conn.app_id}: {exc}")
            if not ready_future.done():
                ready_future.set_exception(exc)
        finally:
            conn._session = None
            if conn.status == "connected":
                conn.status = "disconnected"
            if not ready_future.done():
                ready_future.set_exception(RuntimeError("HTTP connection terminated"))

    async def _discover_tools(self, conn: MCPAppConnection) -> None:
        """Discover tools and strictly verify against mcp_tools.lock.json."""
        if not conn._session:
            raise RuntimeError(f"No active session for {conn.app_id}")

        result = await conn._session.list_tools()
        conn.discovered_tools = []

        lock = self.load_lock()
        app_lock = lock.get("apps", {}).get(conn.app_id, {})
        locked_tools = app_lock.get("tools", {})

        for tool in result.tools:
            t_name = tool.name
            schema = tool.input_schema if hasattr(tool, "input_schema") else (tool.inputSchema if hasattr(tool, "inputSchema") else {})

            # Rule 1: If lock exists for this app, any unlisted tool is skipped (invisible)
            if locked_tools and t_name not in locked_tools:
                logger.debug(f"MCP tool '{conn.app_id}:{t_name}' not listed in lockfile; skipping.")
                continue

            # Rule 2: If tool is locked, canonical schema hash must match
            if locked_tools:
                locked_meta = locked_tools[t_name]
                expected_hash = locked_meta.get("schema_sha256")
                actual_hash = compute_schema_hash(schema)
                if expected_hash and actual_hash != expected_hash:
                    err = (
                        f"SECURITY ALERT: MCP tool schema hash mismatch for '{conn.app_id}:{t_name}'. "
                        f"Expected {expected_hash}, got {actual_hash}. Disabling app."
                    )
                    logger.critical(err)
                    conn.status = "error"
                    conn.error_message = err
                    conn.discovered_tools = []
                    self._update_config_enabled(conn.app_id, False)
                    raise LockMismatchError(err)

                # Rule 3: Use local locked description, never third-party server string
                desc = locked_meta.get("description", tool.description or "")
            else:
                desc = tool.description or ""

            descriptor = MCPToolDescriptor(
                name=t_name,
                description=desc,
                input_schema=schema,
                app_id=conn.app_id,
            )
            conn.discovered_tools.append(descriptor)

    async def disconnect_app(self, app_id: str) -> None:
        """Stop an MCP server connection."""
        async with self._lock:
            conn = self._connections.get(app_id)
            if not conn:
                return

            try:
                await self._stop_runner_task(conn)
                conn.discovered_tools = []
                conn.status = "disconnected"
                conn.error_message = None

                self._update_config_enabled(app_id, False)
                conn.enabled = False
                await self._sync_catalog_on_disconnect(app_id)

                logger.info(f"MCP disconnected: {conn.display_name}")
            except Exception as e:
                logger.error(f"Error disconnecting {app_id}: {e}")

    async def call_tool(self, app_id: str, tool_name: str, arguments: dict, timeout: float = 60.0) -> dict:
        """Invoke an MCP tool with enforced timeout and structured error handling."""
        conn = self._connections.get(app_id)
        if not conn or conn.status != "connected" or not conn._session:
            raise RuntimeError(f"App '{app_id}' is not connected")

        try:
            result = await asyncio.wait_for(
                conn._session.call_tool(name=tool_name, arguments=arguments),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            conn.scene_state = "UNKNOWN"
            logger.error(f"MCP tool '{app_id}:{tool_name}' timed out after {timeout}s. Scene state marked UNKNOWN.")
            raise MCPTimeoutError(f"MCP tool '{app_id}:{tool_name}' timed out after {timeout}s")

        # Check if MCP server returned an error flag
        is_error = getattr(result, "isError", False)
        content_parts = []
        for block in getattr(result, "content", []):
            if hasattr(block, "text"):
                content_parts.append(block.text)
            elif hasattr(block, "data"):
                content_parts.append(f"[binary data: {getattr(block, 'mimeType', 'unknown')}]")

        output_str = "\n".join(content_parts)
        if is_error:
            logger.error(f"MCP tool '{app_id}:{tool_name}' returned error: {output_str}")
            raise MCPToolError(f"MCP tool '{app_id}:{tool_name}' failed: {output_str}")

        return {
            "output": output_str,
            "is_error": False,
        }

    async def call_locked(self, app_id: str, tool_name: str, arguments: dict, timeout: float = 60.0) -> dict:
        """Internal execution bridge for validated typed ops. Requires internal_only: true in lockfile."""
        lock = self.load_lock()
        app_lock = lock.get("apps", {}).get(app_id, {})
        locked_tool = app_lock.get("tools", {}).get(tool_name)
        if not locked_tool or not locked_tool.get("internal_only"):
            raise LockViolationError(f"Tool '{app_id}:{tool_name}' is not marked internal_only in mcp_tools.lock.json.")

        return await self.call_tool(app_id, tool_name, arguments, timeout=timeout)
    
    async def test_connection(self, app_id: str) -> dict:
        """Test an app connection: connect, discover tools, disconnect. Returns status."""
        import time
        start = time.monotonic()
        was_connected = False
        conn = self.get_connection(app_id)
        if conn and conn.status == "connected":
            was_connected = True

        try:
            if not was_connected:
                await self.connect_app(app_id)

            conn = self.get_connection(app_id)
            tool_count = len(conn.discovered_tools) if conn else 0
            tool_names = [t.name for t in conn.discovered_tools] if conn else []
            latency_ms = int((time.monotonic() - start) * 1000)

            if not was_connected:
                await self.disconnect_app(app_id)

            return {"ok": True, "latency_ms": latency_ms, "tools_count": tool_count, "tool_names": tool_names}
        except Exception as e:
            if not was_connected:
                try:
                    await self.disconnect_app(app_id)
                except Exception:
                    pass
            latency_ms = int((time.monotonic() - start) * 1000)
            return {"ok": False, "latency_ms": latency_ms, "error": str(e)}

    
    def list_connections(self) -> list[dict]:
        """List all configured apps with their current status."""
        result = []
        for app_id, conn in self._connections.items():
            result.append({
                "app_id": conn.app_id,
                "display_name": conn.display_name,
                "icon": conn.icon,
                "transport": conn.transport,
                "status": conn.status,
                "enabled": conn.enabled,
                "description": conn.description,
                "error_message": conn.error_message,
                "tools_count": len(conn.discovered_tools),
                "tools": [{"name": t.name, "description": t.description, "input_schema": t.input_schema} for t in conn.discovered_tools],
                "security": conn.security,
            })
        return result
    
    def get_connection(self, app_id: str) -> MCPAppConnection | None:
        return self._connections.get(app_id)
    
    def list_connected_app_names(self) -> list[str]:
        """Get display names of currently connected apps (for intent routing)."""
        return [conn.display_name.lower() for conn in self._connections.values() if conn.status == "connected"]
    
    def list_connected_app_ids(self) -> list[str]:
        """Get app IDs of currently connected apps."""
        return [app_id for app_id, conn in self._connections.items() if conn.status == "connected"]
    
    def get_tools_for_app(self, app_id: str) -> list[MCPToolDescriptor]:
        """Get discovered tools for a specific app."""
        conn = self._connections.get(app_id)
        return conn.discovered_tools if conn else []
    
    def get_tool_registry_entries(self, app_id: str) -> dict:
        """Generate tool_registry-compatible entries for an app's discovered MCP tools.
        Enforces complete REQUIRED_GOVERNANCE_FLAGS, pulling from lockfile when available."""
        conn = self._connections.get(app_id)
        if not conn:
            return {}

        lock = self.load_lock()
        app_lock = lock.get("apps", {}).get(app_id, {})
        locked_tools = app_lock.get("tools", {})

        entries = {}
        security = conn.security or {}
        for tool in conn.discovered_tools:
            tool_key = f"mcp:{app_id}:{tool.name}"
            locked_meta = locked_tools.get(tool.name, {})

            is_auto_approve = bool(security.get("auto_approve"))
            entries[tool_key] = {
                "name": tool_key,
                "side_effect": locked_meta.get("side_effect", security.get("default_side_effect", "act")),
                "risk_level": "L0" if is_auto_approve else (locked_meta.get("risk_level") or security.get("default_risk_level", "L3")),
                "returns_untrusted": locked_meta.get("returns_untrusted", security.get("returns_untrusted", True)),
                "reads_private_data": locked_meta.get("reads_private_data", False),
                "deny_all": locked_meta.get("deny_all", False),
                "taint_deny": locked_meta.get("taint_deny", False),
                "taint_safe": True if is_auto_approve else locked_meta.get("taint_safe", bool(security.get("taint_safe"))),
                "egress": locked_meta.get("egress", False),
                "internal_only": locked_meta.get("internal_only", False),
                "timeout_seconds": locked_meta.get("timeout_seconds", 60),
                "cost": 3,
                "allowed_agents": locked_meta.get("allowed_agents", ["endpoint_agent", "cua_agent"]),
                "auto_approve": is_auto_approve,
                "_mcp": True,
                "_app_id": app_id,
                "_mcp_tool_name": tool.name,
            }
        return entries
    
    def add_custom_app(self, app_id: str, config_data: dict) -> None:
        """Add a new custom MCP app configuration."""
        conn = MCPAppConnection(
            app_id=app_id,
            display_name=config_data.get("display_name", app_id),
            icon=config_data.get("icon", "plug"),
            transport=config_data.get("transport", "stdio"),
            command=config_data.get("command"),
            args=config_data.get("args", []),
            url=config_data.get("url"),
            env=config_data.get("env", {}),
            description=config_data.get("description", ""),
            security=config_data.get("security", {"default_side_effect": "read", "default_risk_level": "L2", "returns_untrusted": True}),
        )
        self._connections[app_id] = conn
        
        # Persist to YAML
        full_config = self.load_config()
        full_config.setdefault("apps", {})[app_id] = config_data
        self.save_config(full_config)
    
    def remove_app(self, app_id: str) -> None:
        """Remove an app configuration."""
        if app_id in self._connections:
            del self._connections[app_id]
        
        full_config = self.load_config()
        if app_id in full_config.get("apps", {}):
            del full_config["apps"][app_id]
            self.save_config(full_config)
    
    def update_app_config(self, app_id: str, updates: dict) -> None:
        """Update an existing app's configuration."""
        conn = self._connections.get(app_id)
        if not conn:
            raise ValueError(f"Unknown app: {app_id}")
        
        # Update in-memory
        for key in ["display_name", "icon", "transport", "command", "args", "url", "env", "description", "security"]:
            if key in updates:
                setattr(conn, key, updates[key])
        
        # Persist to YAML
        full_config = self.load_config()
        app_cfg = full_config.get("apps", {}).get(app_id, {})
        app_cfg.update(updates)
        full_config.setdefault("apps", {})[app_id] = app_cfg
        self.save_config(full_config)
    
    def _update_config_enabled(self, app_id: str, enabled: bool) -> None:
        """Update the enabled state in the YAML config."""
        try:
            full_config = self.load_config()
            if app_id in full_config.get("apps", {}):
                full_config["apps"][app_id]["enabled"] = enabled
                self.save_config(full_config)
        except Exception as e:
            logger.warning(f"Could not persist enabled state for {app_id}: {e}")

    async def _sync_catalog_on_connect(self, conn: MCPAppConnection) -> None:
        """Upsert discovered tools into knowledge.sqlite mcp_tool_catalog and check for drift."""
        from db.connections import get_knowledge_db, get_audit_db
        from db.transaction import execute_write_transaction
        import hashlib, json, uuid

        try:
            k_conn = get_knowledge_db()
            drift_events = []
            try:
                with execute_write_transaction(k_conn, operation_name="sync_mcp_catalog_connect", db_name="knowledge") as cur:
                    for t in conn.discovered_tools:
                        tool_key = f"mcp:{conn.app_id}:{t.name}"
                        # Combined hash covering BOTH description and schema to catch stealth description tampering
                        spec_payload = {
                            "description": t.description or "",
                            "schema": t.input_schema or {},
                        }
                        spec_sha = hashlib.sha256(json.dumps(spec_payload, sort_keys=True).encode("utf-8")).hexdigest()

                        cur.execute("SELECT spec_sha256 FROM mcp_tool_catalog WHERE tool_key = ?", (tool_key,))
                        row = cur.fetchone()
                        if row and row["spec_sha256"] != spec_sha:
                            logger.warning(
                                f"SCHEMA_DRIFT_DETECTED: Tool '{tool_key}' spec hash changed from {row['spec_sha256'][:10]} to {spec_sha[:10]}"
                            )
                            drift_events.append({
                                "app_id": conn.app_id,
                                "tool_key": tool_key,
                                "old_hash": row["spec_sha256"],
                                "new_hash": spec_sha,
                            })

                        cur.execute(
                            """
                            INSERT OR REPLACE INTO mcp_tool_catalog (
                                tool_key, app_id, tool_name, description, input_schema,
                                spec_sha256, is_active, last_discovered_at
                            ) VALUES (?, ?, ?, ?, ?, ?, 1, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
                            """,
                            (
                                tool_key,
                                conn.app_id,
                                t.name,
                                t.description or "",
                                json.dumps(t.input_schema or {}),
                                spec_sha,
                            ),
                        )
            finally:
                k_conn.close()

            # Record schema drift events to audit.sqlite
            if drift_events:
                try:
                    a_conn = get_audit_db()
                    try:
                        with execute_write_transaction(a_conn, operation_name="log_schema_drift", db_name="audit") as cur:
                            for drift in drift_events:
                                cur.execute(
                                    """
                                    INSERT INTO audit_logs (
                                        log_id, run_id, task_id, who_actor, action_type, tool_name,
                                        decision_summary, decision_factors
                                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                                    """,
                                    (
                                        f"drift_{uuid.uuid4().hex[:12]}",
                                        "system_mcp",
                                        f"connect_{conn.app_id}",
                                        "mcp_manager",
                                        "SCHEMA_DRIFT_DETECTED",
                                        drift["tool_key"],
                                        json.dumps({"status": "DRIFT_RECORDED", "reason": "Spec hash mismatch on connect"}),
                                        json.dumps(drift),
                                    ),
                                )
                    finally:
                        a_conn.close()
                except Exception as audit_err:
                    logger.warning(f"Could not record schema drift audit event: {audit_err}")

            # Invalidate ToolGateway cache so search_tools reflects fresh schemas immediately
            from core.tool_gateway import ToolGateway
            ToolGateway._tool_search_index = None

        except Exception as e:
            logger.warning(f"Failed to sync mcp_tool_catalog for {conn.app_id}: {e}")

    async def _sync_catalog_on_disconnect(self, app_id: str) -> None:
        """Mark tools in knowledge.sqlite as inactive on app disconnect."""
        from db.connections import get_knowledge_db
        from db.transaction import execute_write_transaction

        try:
            k_conn = get_knowledge_db()
            try:
                with execute_write_transaction(k_conn, operation_name="sync_mcp_catalog_disconnect", db_name="knowledge") as cur:
                    cur.execute("UPDATE mcp_tool_catalog SET is_active = 0 WHERE app_id = ?", (app_id,))
            finally:
                k_conn.close()

            # Invalidate ToolGateway cache
            from core.tool_gateway import ToolGateway
            ToolGateway._tool_search_index = None
        except Exception as e:
            logger.warning(f"Failed to mark mcp_tool_catalog inactive for {app_id}: {e}")
    
    async def shutdown(self) -> None:
        """Disconnect all MCP servers gracefully."""
        for app_id in list(self._connections.keys()):
            if self._connections[app_id].status == "connected":
                try:
                    await self.disconnect_app(app_id)
                except Exception as e:
                    logger.warning(f"Error disconnecting {app_id} during shutdown: {e}")
    
    async def auto_connect_enabled(self) -> None:
        """Connect all apps that have enabled=true in config."""
        for app_id, conn in self._connections.items():
            if conn.enabled:
                try:
                    await self.connect_app(app_id)
                except Exception as e:
                    logger.warning(f"Auto-connect failed for {app_id}: {e}")
