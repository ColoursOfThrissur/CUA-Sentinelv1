import re
import unicodedata
import uuid
import json
import logging
import inspect
import asyncio
import secrets
import hashlib
from abc import ABC, abstractmethod
from datetime import datetime, timezone, timedelta
from typing import Any, Callable, Optional
from db.connections import get_operational_db, get_audit_db
from core.model_manager import ModelManager
from core.governance import GovernanceEngine, GovernanceViolation, HITLRequired
from core.artifacts import ArtifactStore, ContextPackBuilder
from core.scraper_sanitizer import scraper_sanitizer
from core.sealed_envelope import build_sealed_envelope
from core.agent_runtime import AgentRuntime
from core.tool_gateway import ToolGateway
from config.loader import get_config_version, compute_prompt_hash, load_tool_registry, GATEWAY_VERSION

logger = logging.getLogger(__name__)



class BaseAgent(ABC):
    """
    All agents inherit from here.
    Provides: step management, episodic memory read/write,
    context compression, and structured JSON handoffs between steps.
    Agents decide. Workers execute. Nothing bypasses governance.
    """

    # Class-level tool handler registry owned by ToolGateway
    _TOOL_HANDLERS: dict[str, Callable] = ToolGateway._TOOL_HANDLERS

    @classmethod
    def register_tool_handler(cls, name: str, handler: Callable) -> None:
        """Register a tool handler in the gateway-owned map."""
        ToolGateway.register_tool_handler(name, handler)

    @classmethod
    def register_default_handlers(cls) -> None:
        """Register default tool handlers via ToolGateway."""
        ToolGateway.register_default_handlers()

    @classmethod
    def register_typed_blender_handlers(cls) -> None:
        """Register typed Blender ops handlers via ToolGateway."""
        ToolGateway.register_typed_blender_handlers()

    def __init__(self, model_manager: ModelManager, governance: GovernanceEngine, config: dict):
        self.model_manager = model_manager
        self.governance = governance
        self.config = config or {}
        self.artifacts = ArtifactStore()
        self.context_packs = ContextPackBuilder()
        self.runtime = AgentRuntime(model_manager=self.model_manager, config=self.config)
        self.gateway = ToolGateway(
            governance=self.governance,
            config=self.config,
            model_manager=self.model_manager,
            mcp_manager=getattr(self, "_mcp_manager", None),
        )

        # Make model_manager accessible to class-level tool handlers (e.g. build_spec planner)
        BaseAgent._active_model_manager = model_manager
        ToolGateway._active_model_manager = model_manager

        # Shared state references for backward compatibility
        self._taint_state: dict[str, bool] = self.gateway._taint_state
        self._taint_origins: dict[str, list[str]] = self.gateway._taint_origins
        self._task_prompt_hashes: dict[str, str] = self.runtime._task_prompt_hashes
        self._task_active_models: dict[str, str] = self.runtime._task_active_models
        self.allowed_urls: set[str] = self.gateway.allowed_urls
        self.tool_call_counts: dict[str, int] = self.gateway.tool_call_counts
        self.max_tool_calls_per_task: int = self.gateway.max_tool_calls_per_task
        self.log_only_gateway: bool = self.gateway.log_only_gateway

        # P3: Declarative agent profile & version stamp (Pilot Profile Section 8.1)
        self.profile: dict | None = None
        self.profile_version: str | None = None
        if hasattr(self, "PROFILE_NAME") and getattr(self, "PROFILE_NAME"):
            try:
                self.load_profile(getattr(self, "PROFILE_NAME"))
            except Exception as e:
                logger.warning(f"Could not auto-load profile '{getattr(self, 'PROFILE_NAME')}': {e}")

    def load_profile(self, name_or_path: str) -> dict:
        """Loads a declarative agent profile YAML per P3 Section 8.1."""
        from core.profile_manager import load_profile
        self.profile = load_profile(name_or_path)
        self.profile_version = str(self.profile.get("version", "1.0.0"))
        if self.profile.get("model_preference"):
            self.active_model_id = self.profile.get("model_preference")
        return self.profile

    def validate_output(self, data: Any) -> tuple[bool, list[str]]:
        """Validate output data against profile's output_schema and validators."""
        if not self.profile:
            return True, []
        from core.profile_manager import validate_schema, run_validators
        errors = []
        schema = self.profile.get("output_schema")
        if schema:
            valid, err = validate_schema(data, schema)
            if not valid:
                errors.append(f"Schema violation: {err}")
        validators = self.profile.get("validators", [])
        if validators:
            valid, val_errs = run_validators(data, validators)
            if not valid:
                errors.extend(val_errs)
        return len(errors) == 0, errors

    def get_profile_prompt_template(self) -> str:
        """Returns the loaded prompt template content from profile."""
        if self.profile:
            return self.profile.get("_template_content") or self.profile.get("prompt_template", "")
        return ""

    def is_tainted(self, task_id: str = "adhoc") -> bool:
        """Check if a task's run state is tainted. Delegates to ToolGateway."""
        return self.gateway.is_tainted(task_id)

    def __getattr__(self, name):
        # Backward compatibility for legacy tests checking `agent.is_tainted` as a boolean property
        if name == "is_tainted_legacy_bool":
            return self.is_tainted("adhoc")
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

    def set_tainted(self, task_id: str, origin_tool: str = "unknown") -> None:
        """Mark a task's run state as tainted. Delegates to ToolGateway."""
        self.gateway.set_tainted(task_id, origin_tool)

    def get_taint_origins(self, task_id: str) -> str:
        """Get a comma-separated string of tool names that caused taint. Delegates to ToolGateway."""
        return self.gateway.get_taint_origins(task_id)


    async def broadcast_step_trace(
        self,
        task_id: str,
        step_name: str,
        tool_name: str,
        status: str = "RUNNING",
        details: dict = None,
        span_id: str = None,
    ) -> None:
        """Broadcasts real-time step trace telemetry over WebSockets to UI clients."""
        await self.runtime.broadcast_step_trace(
            task_id=task_id,
            step_name=step_name,
            tool_name=tool_name,
            status=status,
            details=details,
            span_id=span_id,
        )

    @abstractmethod
    async def run(self, claim) -> dict:
        """Entry point. Returns result_payload dict."""
        raise RuntimeError(f"{type(self).__name__} must implement run()")

    def create_step(
        self,
        task_id: str,
        step_order: int,
        step_type: str,
        description: str = None,
        model_id: str = None,
        prompt_hash: str = None,
    ) -> str:
        """Creates a task step with non-null version stamps."""
        effective_model_id = model_id or getattr(self, "active_model_id", None)
        effective_prompt_hash = prompt_hash or getattr(self, "active_prompt_hash", None)
        profile_version = getattr(self, "profile_version", None)
        return self.runtime.create_step(
            task_id=task_id,
            step_order=step_order,
            step_type=step_type,
            description=description,
            model_id=effective_model_id,
            prompt_hash=effective_prompt_hash,
            profile_version=profile_version,
        )

    def update_step_status(
        self,
        step_id: str,
        status: str,
        output_summary: dict = None,
        model_id: str = None,
        prompt_hash: str = None,
    ) -> None:
        """Updates a task step status, output summary, and terminal timestamps."""
        self.runtime.update_step_status(
            step_id=step_id,
            status=status,
            output_summary=output_summary,
            model_id=model_id,
            prompt_hash=prompt_hash,
        )

    # =========================================================================
    # Checkpoint & Resume Lifecycle
    # =========================================================================

    def compute_input_hash(self, input_payload: Any) -> str:
        """Computes deterministic sha256 input hash for task resumption validation."""
        return self.runtime.compute_input_hash(input_payload)

    def write_checkpoint(
        self,
        task_id: str,
        step_index: int,
        phase: str = "EXECUTION",
        state_dict: dict = None,
        input_payload: Any = None,
    ) -> str:
        """Writes a checkpoint after each COMPLETED step."""
        return self.runtime.write_checkpoint(
            task_id=task_id,
            step_index=step_index,
            phase=phase,
            state_dict=state_dict,
            input_payload=input_payload,
        )

    def load_latest_checkpoint(
        self,
        task_id: str,
        current_input_payload: Any = None,
        max_age_seconds: int = 86400,
    ) -> Optional[dict]:
        """Loads latest valid checkpoint for continuation if fresh and matching hash."""
        return self.runtime.load_latest_checkpoint(
            task_id=task_id,
            current_input_payload=current_input_payload,
            max_age_seconds=max_age_seconds,
        )

    def should_yield(self, task_id: str) -> bool:
        """Cooperative Preemption Check."""
        return self.runtime.should_yield(task_id)

    def save_episodic_memory(self, task_id: str, step_id: str, agent_type: str, summary: dict) -> str:
        """Saves a compressed JSON summary to episodic memory."""
        return self.runtime.save_episodic_memory(
            task_id=task_id,
            step_id=step_id,
            agent_type=agent_type,
            summary=summary,
        )

    def load_episodic_memory(self, task_id: str) -> list:
        """Loads all episodic summaries for a task."""
        return self.runtime.load_episodic_memory(task_id)

    def build_context_pack(self, task_id: str) -> dict:
        return self.context_packs.build_for_task(task_id)

    def save_artifact(self, task_id: str, artifact_type: str, content: str,
                      step_id: str = None, metadata: dict = None) -> str:
        return self.artifacts.save(
            task_id=task_id,
            step_id=step_id,
            artifact_type=artifact_type,
            content=content,
            metadata=metadata,
        )

    def compress_to_skeleton(self, model_id: str, task_id: str, lease_id: str,
                              lease_generation: int, raw_output: str, step_description: str) -> dict:
        """
        Uses the sanitizer/small model to compress raw output into a structured JSON skeleton.
        This is the key mechanism that keeps VRAM usage low across multi-step tasks.
        """
        prompt = f"""You completed this step: {step_description}

Here is the raw output:
{raw_output[:4000]}

Extract a structured JSON summary with these exact keys:
- "outcome": one sentence describing what was accomplished
- "key_facts": list of critical facts, names, values, URLs that must be remembered
- "next_context": what the next step needs to know (2-3 sentences max)
- "status": "success" or "partial" or "failed"

Respond with only valid JSON."""

        compressed = self.model_manager.generate(
            model_id=model_id,
            task_id=task_id,
            lease_id=lease_id,
            lease_generation=lease_generation,
            prompt=prompt,
            temperature=0.0,
            context_budget=4096,
        )

        try:
            return json.loads(compressed)
        except json.JSONDecodeError:
            return {
                "outcome": step_description,
                "key_facts": [],
                "next_context": raw_output[:500],
                "status": "partial",
            }

    def _resolve_tool_handler(self, name: str, tool_instance: Any = None) -> Any:
        """Resolve the callable handler for a tool name. Delegates to ToolGateway."""
        return self.gateway._resolve_tool_handler(name, tool_instance)

    async def execute_tool(
        self,
        name: str,
        params: dict = None,
        task_id: str = "adhoc",
        step_id: str = None,
        tool_instance: Any = None,
    ) -> dict:
        """
        P0.1/P0.2 Single Tool Gateway:
        Centralized checkpoint through which every tool invocation runs.
        Delegates to ToolGateway service.
        """
        caller_name = getattr(self, "agent_name", self.__class__.__name__.lower())
        effective_model_id = getattr(self, "active_model_id", None)
        effective_prompt_hash = getattr(self, "active_prompt_hash", None)

        if getattr(self, "_mcp_manager", None):
            self.gateway._mcp_manager = getattr(self, "_mcp_manager", None)
            ToolGateway._active_mcp_manager = getattr(self, "_mcp_manager", None)

        return await self.gateway.execute_tool(
            name=name,
            params=params,
            task_id=task_id,
            step_id=step_id,
            tool_instance=tool_instance,
            caller_name=caller_name,
            profile=self.profile,
            profile_version=getattr(self, "profile_version", None),
            model_id=effective_model_id,
            prompt_hash=effective_prompt_hash,
        )


    async def call_llm(
        self,
        *,
        task_id: str,
        system_rules: str,
        task_prompt: str,
        facts: list[str] | None = None,
        untrusted_blocks: list[str] | None = None,
        model_id: str | None = None,
        lease_id: str | None = None,
        lease_generation: int | None = None,
        context_budget: int = 8192,
        temperature: float = 0.7,
        keep_alive: str | None = None,
    ) -> str:
        """
        Unified LLM call for ALL agents. Delegates to AgentRuntime.
        """
        def _on_untrusted(origin: str):
            self.set_tainted(task_id, origin_tool=origin)

        effective_model = model_id or getattr(self, "active_model_id", None)

        response = await self.runtime.call_llm(
            task_id=task_id,
            system_rules=system_rules,
            task_prompt=task_prompt,
            facts=facts,
            untrusted_blocks=untrusted_blocks,
            model_id=effective_model,
            lease_id=lease_id,
            lease_generation=lease_generation,
            context_budget=context_budget,
            temperature=temperature,
            keep_alive=keep_alive,
            profile=self.profile,
            on_untrusted=_on_untrusted,
        )
        self.active_prompt_hash = self.runtime._task_prompt_hashes.get(task_id)
        return response
