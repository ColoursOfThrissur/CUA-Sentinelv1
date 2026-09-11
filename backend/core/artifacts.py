import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from db.connections import DB_DIR, get_knowledge_db


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ArtifactStore:
    """
    Stores large step outputs on disk and indexes their metadata in knowledge.sqlite.
    This is the bridge between hierarchical task work and small context windows.
    """

    def __init__(self, root: Optional[Path] = None):
        self.root = root or (DB_DIR / "artifacts")
        self.root.mkdir(parents=True, exist_ok=True)

    def save(
        self,
        *,
        task_id: str,
        artifact_type: str,
        content: str,
        step_id: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> str:
        artifact_id = str(uuid.uuid4())
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        task_dir = self.root / task_id
        task_dir.mkdir(parents=True, exist_ok=True)
        path = task_dir / f"{artifact_id}.txt"
        path.write_text(content, encoding="utf-8")

        conn = get_knowledge_db()
        try:
            conn.execute(
                """
                INSERT INTO artifacts (
                    artifact_id, task_id, step_id, artifact_type, storage_path,
                    content_hash, size_bytes, metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    artifact_id,
                    task_id,
                    step_id,
                    artifact_type,
                    str(path),
                    digest,
                    len(content.encode("utf-8")),
                    json.dumps(metadata or {}),
                    _now(),
                ),
            )
            conn.commit()
        finally:
            conn.close()
        return artifact_id

    def read(self, artifact_id: str) -> str:
        conn = get_knowledge_db()
        try:
            row = conn.execute(
                "SELECT storage_path, content_hash FROM artifacts WHERE artifact_id = ?",
                (artifact_id,),
            ).fetchone()
        finally:
            conn.close()
        if not row:
            raise FileNotFoundError(f"Artifact not found: {artifact_id}")
        content = Path(row["storage_path"]).read_text(encoding="utf-8")
        actual = hashlib.sha256(content.encode("utf-8")).hexdigest()
        if actual != row["content_hash"]:
            raise ValueError(f"Artifact hash mismatch: {artifact_id}")
        return content


class ContextPackBuilder:
    """Builds compact, structured context packs for the next model call."""

    def build_for_task(self, task_id: str, *, max_memories: int = 6, max_artifacts: int = 8) -> dict[str, Any]:
        conn = get_knowledge_db()
        try:
            memories = conn.execute(
                """
                SELECT memory_id, step_id, agent_type, summary_json, created_at
                FROM episodic_memory
                WHERE task_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (task_id, max_memories),
            ).fetchall()
            artifacts = conn.execute(
                """
                SELECT artifact_id, step_id, artifact_type, content_hash, size_bytes, metadata_json, created_at
                FROM artifacts
                WHERE task_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (task_id, max_artifacts),
            ).fetchall()
        finally:
            conn.close()

        return {
            "task_id": task_id,
            "built_at": _now(),
            "memory_skeleton": [
                {
                    "memory_id": row["memory_id"],
                    "step_id": row["step_id"],
                    "agent_type": row["agent_type"],
                    "summary": json.loads(row["summary_json"]),
                    "created_at": row["created_at"],
                }
                for row in reversed(memories)
            ],
            "artifacts": [
                {
                    "artifact_id": row["artifact_id"],
                    "step_id": row["step_id"],
                    "artifact_type": row["artifact_type"],
                    "content_hash": row["content_hash"],
                    "size_bytes": row["size_bytes"],
                    "metadata": json.loads(row["metadata_json"] or "{}"),
                    "created_at": row["created_at"],
                }
                for row in artifacts
            ],
        }
