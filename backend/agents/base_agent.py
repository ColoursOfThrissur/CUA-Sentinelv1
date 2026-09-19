import uuid
import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone

from db.connections import get_operational_db
from core.model_manager import ModelManager
from core.governance import GovernanceEngine
from core.artifacts import ArtifactStore, ContextPackBuilder

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """
    All agents inherit from here.
    Provides: step management, episodic memory read/write,
    context compression, and structured JSON handoffs between steps.
    Agents decide. Workers execute. Nothing bypasses governance.
    """

    def __init__(self, model_manager: ModelManager, governance: GovernanceEngine, config: dict):
        self.model_manager = model_manager
        self.governance = governance
        self.config = config
        self.artifacts = ArtifactStore()
        self.context_packs = ContextPackBuilder()

    async def broadcast_step_trace(self, task_id: str, step_name: str, tool_name: str, status: str = "RUNNING", details: dict = None) -> None:
        """
        Broadcasts real-time step trace telemetry over WebSockets to UI clients.
        """
        try:
            from api.websocket import manager
            payload = {
                "type": "AGENT_TRACE",
                "task_id": task_id,
                "step_name": step_name,
                "tool_name": tool_name,
                "status": status,
                "details": details or {},
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            await manager.broadcast(payload)
        except Exception as e:
            logger.warning(f"Error broadcasting agent step trace: {e}")

    @abstractmethod
    async def run(self, claim) -> dict:
        """Entry point. Returns result_payload dict."""
        pass

    def create_step(self, task_id: str, step_order: int, step_type: str, description: str = None) -> str:
        step_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        conn = get_operational_db()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO task_steps (step_id, task_id, step_order, step_type, description, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 'PENDING', ?, ?)
                """,
                (step_id, task_id, step_order, step_type, description, now, now),
            )
            conn.commit()
            return step_id
        finally:
            conn.close()

    def update_step_status(self, step_id: str, status: str, output_summary: dict = None) -> None:
        VALID_STATUSES = {'PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED', 'SKIPPED'}
        if status not in VALID_STATUSES:
            logger.warning(f"update_step_status: invalid status '{status}', normalizing to COMPLETED")
            status = 'COMPLETED' if 'COMPLETED' in status.upper() else 'FAILED'

        now = datetime.now(timezone.utc).isoformat()
        conn = get_operational_db()
        try:
            conn.execute(
                """
                UPDATE task_steps SET status = ?, updated_at = ?,
                    output_summary = ?,
                    started_at = CASE WHEN ? = 'RUNNING' AND started_at IS NULL THEN ? ELSE started_at END,
                    finished_at = CASE WHEN ? IN ('COMPLETED','FAILED','CANCELLED') THEN ? ELSE finished_at END
                WHERE step_id = ?
                """,
                (
                    status, now,
                    json.dumps(output_summary) if output_summary else None,
                    status, now,
                    status, now,
                    step_id,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def save_episodic_memory(self, task_id: str, step_id: str, agent_type: str, summary: dict) -> str:
        """
        Saves a compressed JSON summary to episodic memory.
        This is what gets passed to the next step — not raw output.
        """
        from db.connections import get_knowledge_db
        memory_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        conn = get_knowledge_db()
        try:
            conn.execute(
                """
                INSERT INTO episodic_memory (memory_id, task_id, step_id, agent_type, summary_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (memory_id, task_id, step_id, agent_type, json.dumps(summary), now),
            )
            conn.commit()
            return memory_id
        finally:
            conn.close()

    def load_episodic_memory(self, task_id: str) -> list:
        """Load all episodic summaries for a task — the skeleton context."""
        from db.connections import get_knowledge_db
        conn = get_knowledge_db()
        try:
            rows = conn.execute(
                """
                SELECT agent_type, summary_json, created_at
                FROM episodic_memory WHERE task_id = ?
                ORDER BY created_at ASC
                """,
                (task_id,),
            ).fetchall()
            return [
                {"agent_type": r["agent_type"], "summary": json.loads(r["summary_json"]), "at": r["created_at"]}
                for r in rows
            ]
        finally:
            conn.close()

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
