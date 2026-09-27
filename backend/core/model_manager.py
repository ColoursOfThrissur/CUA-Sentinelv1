import logging
import httpx
import psutil
from datetime import datetime, timezone
from typing import Optional

from db.connections import get_operational_db
from core.state_manager import LeaseValidationError, StateManager, StateTransitionError

logger = logging.getLogger(__name__)


class ModelAdmissionError(Exception):
    pass


class ModelLeaseError(Exception):
    pass


class ModelInferenceError(Exception):
    pass


class ModelManager:
    """
    Controls which model is loaded in Ollama at any given time.
    Ollama executes. BP01 (operational.sqlite) decides and records state.
    One model in VRAM at a time — enforced here, not by Ollama config alone.
    """

    # Class-level lock: only one load/evict can proceed at a time across all instances.
    # This prevents TOCTOU races where two concurrent requests both check VRAM, both
    # see "enough space", and then both try to load — crashing the second one.
    _vram_lock: "asyncio.Lock | None" = None

    @classmethod
    def _get_vram_lock(cls):
        import asyncio
        if cls._vram_lock is None:
            cls._vram_lock = asyncio.Lock()
        return cls._vram_lock

    def __init__(self, config: dict, registry: dict):
        self.ollama_url = config["ollama"]["base_url"]
        self.keep_alive_bg = config["ollama"]["keep_alive_background"]
        self.keep_alive_endpoint = config["ollama"]["keep_alive_endpoint"]
        self.default_top_p = float(config.get("ollama", {}).get("default_top_p", 0.9))
        self.default_repeat_penalty = float(config.get("ollama", {}).get("default_repeat_penalty", 1.1))
        self.limits = registry["hardware_limits"]
        self.models_by_id = {m["model_id"]: m for m in registry["models"]}
        self.routing = registry["model_routing"]
        self._current_model_id: Optional[str] = None
        self.state = StateManager()
        self._sync_registry_to_db()

    def _sync_registry_to_db(self) -> None:
        """Upsert models from JSON registry into BP01 on startup."""
        import json
        conn = get_operational_db()
        try:
            for m in self.models_by_id.values():
                conn.execute(
                    """
                    INSERT INTO models_registry (
                        model_id, model_name, ollama_tag, version, quantization,
                        context_limit_max, vram_mb_estimate, ram_mb_estimate,
                        num_layers, num_kv_heads, head_dim, capabilities, is_enabled
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(model_id) DO UPDATE SET
                        model_name = excluded.model_name,
                        ollama_tag = excluded.ollama_tag,
                        version = excluded.version,
                        quantization = excluded.quantization,
                        context_limit_max = excluded.context_limit_max,
                        vram_mb_estimate = excluded.vram_mb_estimate,
                        ram_mb_estimate = excluded.ram_mb_estimate,
                        num_layers = excluded.num_layers,
                        num_kv_heads = excluded.num_kv_heads,
                        head_dim = excluded.head_dim,
                        capabilities = excluded.capabilities,
                        is_enabled = excluded.is_enabled
                    """,
                    (
                        m["model_id"], m["model_name"], m["ollama_tag"],
                        m["version"], m["quantization"], m["context_limit_max"],
                        m["vram_mb_estimate"], m["ram_mb_estimate"],
                        m["num_layers"], m["num_kv_heads"], m["head_dim"],
                        json.dumps(m["capabilities"]), 1 if m["is_enabled"] else 0,
                    ),
                )
            conn.commit()
        finally:
            conn.close()

    def _kv_cache_mb(self, model_id: str, context_budget: int) -> int:
        """
        Deterministic KV cache calculation based on tensor geometry.
        KV_bytes = 2 * num_layers * num_kv_heads * head_dim * context_budget * bytes_per_element
        For q8_0: bytes_per_element = 1
        """
        m = self.models_by_id[model_id]
        kv_bytes = 2 * m["num_layers"] * m["num_kv_heads"] * m["head_dim"] * context_budget * 1
        return kv_bytes // (1024 * 1024)

    def evaluate_admission(self, model_id: str, context_budget: int) -> bool:
        if model_id not in self.models_by_id:
            raise ModelAdmissionError(f"Unknown model: {model_id}")

        m = self.models_by_id[model_id]
        kv_mb = self._kv_cache_mb(model_id, context_budget)

        vram_required = m["vram_mb_estimate"] + kv_mb + self.limits["runtime_vram_overhead_mb"]
        vram_ceiling = self.limits["max_vram_mb"] - self.limits["os_vram_reserve_mb"]
        if vram_required > vram_ceiling:
            raise ModelAdmissionError(
                f"VRAM admission failed: need {vram_required}MB, ceiling {vram_ceiling}MB"
            )



        return True

    def get_model_for_workflow(self, workflow_type: str) -> str:
        model_id = self.routing.get(workflow_type)
        if not model_id:
            # Fallback to default ENDPOINT model if unknown workflow type
            model_id = self.routing.get("ENDPOINT", "qwen3_14b_q4")
            logger.info(f"Unmapped workflow '{workflow_type}', falling back to model '{model_id}'")
        return model_id

    def load_model(self, model_id: str, context_budget: int) -> bool:
        # If another model is currently loaded in VRAM, evict it first to free GPU VRAM
        if self._current_model_id and self._current_model_id != model_id:
            logger.info(f"ModelManager: Evicting loaded model '{self._current_model_id}' before loading '{model_id}'")
            self.unload_current()

        try:
            # VRAM admission check is inside the lock so two concurrent callers can't
            # both see "enough VRAM" simultaneously and double-load.
            self.evaluate_admission(model_id, context_budget)
        except ModelAdmissionError as mae:
            # Fallback to 9B model if VRAM/geometry check failed
            fallback_id = "qwen3_5_9b" if model_id != "qwen3_5_9b" else "phi3_latest"
            logger.warning(f"Admission failed for {model_id} ({mae}). Retrying with fallback: {fallback_id}")
            model_id = fallback_id

        conn = get_operational_db()
        try:
            # Concurrent load lock — only one LOADING transition allowed
            result = conn.execute(
                """
                UPDATE models_registry SET current_state = 'LOADING', last_loaded_at = ?
                WHERE model_id = ? AND current_state = 'UNLOADED'
                """,
                (datetime.now(timezone.utc).isoformat(), model_id),
            )
            conn.commit()

            if result.rowcount == 0:
                state = conn.execute(
                    "SELECT current_state FROM models_registry WHERE model_id = ?", (model_id,)
                ).fetchone()
                current = state["current_state"] if state else "UNKNOWN"
                if current in ("READY", "IDLE", "BUSY"):
                    logger.info(f"Model {model_id} already loaded (state={current})")
                    self._current_model_id = model_id
                    return True
                # Force reset if stuck in LOADING
                conn.execute(
                    "UPDATE models_registry SET current_state = 'READY' WHERE model_id = ?", (model_id,)
                )
                conn.commit()
                self._current_model_id = model_id
                return True
        finally:
            conn.close()

        m = self.models_by_id[model_id]
        try:
            with httpx.Client(timeout=60) as client:
                resp = client.post(
                    f"{self.ollama_url}/api/generate",
                    json={"model": m["ollama_tag"], "prompt": "", "keep_alive": self.keep_alive_bg},
                )
                resp.raise_for_status()

            self._set_model_state(model_id, "READY")
            self.state.audit(
                action_type="MODEL_LOADED",
                who_actor="ModelManager",
                task_id="system",
                result={"model_id": model_id, "ollama_tag": m["ollama_tag"]},
            )
            self._current_model_id = model_id
            logger.info(f"Loaded model {model_id} ({m['ollama_tag']})")
            return True

        except Exception as e:
            self._set_model_state(model_id, "FAILED")
            logger.error(f"Failed to load model {model_id}: {e}")
            if model_id != "qwen3_5_9b" and "qwen3_5_9b" in self.models_by_id:
                logger.warning(f"Attempting fallback to 'qwen3_5_9b' after load failure for '{model_id}'")
                return self.load_model("qwen3_5_9b", context_budget)
            self._current_model_id = model_id
            return False

    def generate(
        self,
        model_id: str,
        task_id: str,
        lease_id: str,
        lease_generation: int,
        prompt: str,
        system_prompt: str = None,
        context_budget: int = 8192,
        temperature: float = 0.0,
        keep_alive: str = None,
    ) -> str:
        conn = get_operational_db()
        try:
            conn.execute("BEGIN IMMEDIATE")

            self.state.validate_task_lease(conn, task_id, lease_id, lease_generation)

            model_row = conn.execute(
                "SELECT current_state, busy_task_id, model_lease_generation FROM models_registry WHERE model_id = ?",
                (model_id,),
            ).fetchone()

            # Auto-recover stale model leases if busy_task_id is no longer running
            if model_row and model_row["current_state"] == "BUSY" and model_row["busy_task_id"] != task_id:
                t_row = conn.execute("SELECT status FROM tasks WHERE task_id = ?", (model_row["busy_task_id"],)).fetchone()
                if not t_row or t_row["status"] not in ("RUNNING", "CLAIMED"):
                    conn.execute("UPDATE models_registry SET current_state = 'READY', busy_task_id = NULL WHERE model_id = ?", (model_id,))
                    model_row = conn.execute(
                        "SELECT current_state, busy_task_id, model_lease_generation FROM models_registry WHERE model_id = ?",
                        (model_id,),
                    ).fetchone()

            is_valid_state = model_row and (
                model_row["current_state"] in ("READY", "IDLE") or
                (model_row["current_state"] == "BUSY" and model_row["busy_task_id"] == task_id)
            )

            # If target model is UNLOADED, attempt to auto-load it
            if not is_valid_state and (not model_row or model_row["current_state"] == "UNLOADED"):
                logger.info(f"Model '{model_id}' is UNLOADED; attempting auto-load...")
                conn.execute("COMMIT")  # Commit immediate transaction before load_model call
                loaded = self.load_model(model_id, context_budget)
                conn = get_operational_db()
                conn.execute("BEGIN IMMEDIATE")
                if loaded:
                    model_row = conn.execute(
                        "SELECT current_state, busy_task_id, model_lease_generation FROM models_registry WHERE model_id = ?",
                        (model_id,),
                    ).fetchone()

            is_valid_state = model_row and (
                model_row["current_state"] in ("READY", "IDLE") or
                (model_row["current_state"] == "BUSY" and model_row["busy_task_id"] == task_id)
            )

            if not is_valid_state:
                # Fallback check 1: check self._current_model_id
                if self._current_model_id and self._current_model_id in self.models_by_id:
                    alt_row = conn.execute(
                        "SELECT current_state, busy_task_id, model_lease_generation FROM models_registry WHERE model_id = ?",
                        (self._current_model_id,),
                    ).fetchone()
                    if alt_row and (alt_row["current_state"] in ("READY", "IDLE") or (alt_row["current_state"] == "BUSY" and alt_row["busy_task_id"] == task_id)):
                        logger.info(f"Model '{model_id}' not ready; falling back to loaded model '{self._current_model_id}'")
                        model_id = self._current_model_id
                        model_row = alt_row

            is_valid_state = model_row and (
                model_row["current_state"] in ("READY", "IDLE") or
                (model_row["current_state"] == "BUSY" and model_row["busy_task_id"] == task_id)
            )

            if not is_valid_state:
                # Fallback check 2: check any ready model in database
                ready_row = conn.execute(
                    "SELECT model_id, current_state, busy_task_id, model_lease_generation FROM models_registry WHERE current_state IN ('READY', 'IDLE') LIMIT 1"
                ).fetchone()
                if ready_row:
                    logger.info(f"Model '{model_id}' not ready; falling back to available ready model '{ready_row['model_id']}'")
                    model_id = ready_row["model_id"]
                    model_row = ready_row

            is_valid_state = model_row and (
                model_row["current_state"] in ("READY", "IDLE") or
                (model_row["current_state"] == "BUSY" and model_row["busy_task_id"] == task_id)
            )

            if not is_valid_state:
                conn.execute("ROLLBACK")
                raise ModelLeaseError(f"Model {model_id} not ready (state={model_row['current_state'] if model_row else 'MISSING'})")

            t_exists = conn.execute("SELECT 1 FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
            busy_tid = task_id if t_exists else None

            conn.execute(
                """
                UPDATE models_registry
                SET current_state = 'BUSY', busy_task_id = ?
                WHERE model_id = ?
                  AND model_lease_generation = ?
                """,
                (busy_tid, model_id, model_row["model_lease_generation"]),
            )
            conn.execute("COMMIT")
        except (ModelLeaseError, LeaseValidationError) as e:
            raise ModelLeaseError(str(e)) from e
        except Exception as e:
            conn.execute("ROLLBACK")
            raise ModelLeaseError(f"Inference fence failed: {e}") from e
        finally:
            conn.close()

        m = self.models_by_id[model_id]
        context_budget = min(context_budget, m.get("context_limit_max", 8192))
        messages = []
        effective_system_prompt = system_prompt
        effective_user_prompt = prompt

        # If system_prompt was not explicitly supplied, extract [SYSTEM RULES] if present
        if not effective_system_prompt and prompt.startswith("[SYSTEM RULES]\n"):
            parts = prompt.split("\n\n[TASK]\n", 1)
            if len(parts) == 2:
                effective_system_prompt = parts[0].replace("[SYSTEM RULES]\n", "").strip()
                effective_user_prompt = "[TASK]\n" + parts[1]

        if effective_system_prompt:
            messages.append({"role": "system", "content": effective_system_prompt})
        messages.append({"role": "user", "content": effective_user_prompt})

        try:
            with httpx.Client(timeout=300) as client:
                resp = client.post(
                    f"{self.ollama_url}/api/chat",
                    json={
                        "model": m["ollama_tag"],
                        "messages": messages,
                        "stream": False,
                        "options": {
                            "temperature": temperature,
                            "num_ctx": context_budget,
                            "top_p": getattr(self, "default_top_p", 0.9),
                            "repeat_penalty": getattr(self, "default_repeat_penalty", 1.1),
                        },
                        "think": False,
                        "keep_alive": keep_alive or self.keep_alive_bg,
                    },
                )
                resp.raise_for_status()
                result = resp.json()
                content = result["message"]["content"]
                # Strip any think blocks that slip through
                import re
                content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
                self.state.audit(
                    action_type="MODEL_GENERATED",
                    who_actor="ModelManager",
                    task_id=task_id,
                    result={
                        "model_id": model_id,
                        "tokens_in_est": len(prompt.split()),
                        "tokens_out_est": len(content.split()),
                    },
                )
                return content
        except Exception as e:
            logger.error(f"Inference error for model {model_id}: {e}")
            raise ModelInferenceError(
                f"Could not connect to Ollama backend at `{self.ollama_url}` ({e}). "
                f"Please ensure Ollama is running and model `{m['ollama_tag']}` is loaded."
            ) from e
        finally:
            self._set_model_state(model_id, "READY", clear_busy=True)

    async def generate_async(
        self,
        model_id: str,
        task_id: str,
        lease_id: str,
        lease_generation: int,
        prompt: str,
        system_prompt: str = None,
        context_budget: int = 8192,
        temperature: float = 0.0,
        keep_alive: str = None,
    ) -> str:
        """
        Non-blocking async wrapper around generate().
        Acquires the class-level VRAM lock before the load step so concurrent
        callers cannot double-load and race on VRAM admission.
        """
        import asyncio
        # Ensure the model is loaded under the VRAM lock before entering inference
        async with self._get_vram_lock():
            if self._current_model_id != model_id:
                await asyncio.to_thread(self.load_model, model_id, context_budget)

        return await asyncio.to_thread(
            self.generate,
            model_id,
            task_id,
            lease_id,
            lease_generation,
            prompt,
            system_prompt,
            context_budget,
            temperature,
            keep_alive,
        )

    def unload_current(self) -> None:
        if not self._current_model_id:
            return
        model_id = self._current_model_id
        m = self.models_by_id.get(model_id)
        if not m:
            return
        try:
            self._set_model_state(model_id, "EVICTING")
            with httpx.Client(timeout=30) as client:
                client.post(
                    f"{self.ollama_url}/api/generate",
                    json={"model": m["ollama_tag"], "prompt": "", "keep_alive": "0"},
                )
            self._set_model_state(model_id, "UNLOADED")
            self._current_model_id = None
            logger.info(f"Unloaded model {model_id}")
        except Exception as e:
            logger.error(f"Failed to unload model {model_id}: {e}")

    def release_task_lease(self, task_id: str) -> None:
        """
        Explicitly clears any model leases held by task_id in models_registry.
        Ensures preemption immediately marks the model as READY so high-priority
        tasks never deadlock on a busy model lock.
        """
        conn = get_operational_db()
        try:
            res = conn.execute(
                "UPDATE models_registry SET current_state = 'READY', busy_task_id = NULL WHERE busy_task_id = ?",
                (task_id,),
            )
            conn.commit()
            if res.rowcount > 0:
                logger.info(f"ModelManager: Released busy model lease for preempted/cancelled task {task_id}")
        except Exception as e:
            logger.error(f"Error releasing model lease for {task_id}: {e}")
        finally:
            conn.close()

    def _set_model_state(self, model_id: str, state: str, clear_busy: bool = False) -> None:
        allowed = {
            "UNLOADED": {"LOADING"},
            "LOADING": {"READY", "FAILED", "LOAD_TIMEOUT"},
            "READY": {"BUSY", "IDLE", "EVICTING", "UNHEALTHY"},
            "IDLE": {"BUSY", "EVICTING", "UNHEALTHY"},
            "BUSY": {"READY", "FAILED", "UNHEALTHY"},
            "EVICTING": {"UNLOADED", "FAILED"},
            "FAILED": {"RECOVERING", "UNLOADED"},
            "LOAD_TIMEOUT": {"RECOVERING", "UNLOADED"},
            "UNHEALTHY": {"RECOVERING", "UNLOADED"},
            "RECOVERING": {"READY", "FAILED", "UNLOADED"},
        }
        conn = get_operational_db()
        try:
            row = conn.execute(
                "SELECT current_state FROM models_registry WHERE model_id = ?",
                (model_id,),
            ).fetchone()
            if row and row["current_state"] == state:
                if clear_busy:
                    conn.execute(
                        "UPDATE models_registry SET busy_task_id = NULL WHERE model_id = ?",
                        (model_id,),
                    )
                    conn.commit()
                return
            if row and state not in allowed.get(row["current_state"], set()):
                raise StateTransitionError(
                    f"Invalid model transition {row['current_state']} -> {state}"
                )
            if clear_busy:
                conn.execute(
                    "UPDATE models_registry SET current_state = ?, busy_task_id = NULL WHERE model_id = ?",
                    (state, model_id),
                )
            else:
                conn.execute(
                    "UPDATE models_registry SET current_state = ? WHERE model_id = ?",
                    (state, model_id),
                )
            conn.commit()
        finally:
            conn.close()

    def get_current_model_id(self) -> Optional[str]:
        return self._current_model_id
