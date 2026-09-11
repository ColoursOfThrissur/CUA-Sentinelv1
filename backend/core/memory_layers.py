"""
4-Layer Memory Management Module for CUA-Sentinel.

Provides structured access to:
1. Working Memory (Active SQLite task state & queue)
2. Episodic Memory (Strict machine-readable JSON logs in SQLite)
3. Semantic Memory (Vector DB / URL link indexing)
4. Procedural Memory (Hardcoded SQLite rules and code templates)
"""

import json
import logging
import uuid
from typing import Dict, Any, List, Optional
from db.connections import get_knowledge_db

logger = logging.getLogger(__name__)

class MemoryLayersManager:
    """
    Manages 4-Layer Memory read/write operations to keep context small and structured.
    """

    def record_episodic_memory(
        self,
        task_id: str,
        agent_type: str,
        summary_payload: Dict[str, Any],
        step_id: Optional[str] = None,
        retention_tier: str = "HOT"
    ) -> str:
        """
        Stores structured JSON event log into episodic_memory table.
        Prevents LLM text morphing bugs by enforcing JSON payloads.
        """
        memory_id = f"mem_{uuid.uuid4().hex[:8]}"
        conn = get_knowledge_db()
        try:
            conn.execute(
                """
                INSERT INTO episodic_memory (
                    memory_id, task_id, step_id, agent_type, summary_json, retention_tier
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    memory_id,
                    task_id,
                    step_id,
                    agent_type,
                    json.dumps(summary_payload),
                    retention_tier
                )
            )
            conn.commit()
            logger.info(f"Recorded Episodic Memory {memory_id} for Task {task_id}")
            return memory_id
        except Exception as e:
            logger.error(f"Failed to record episodic memory: {e}")
            return ""
        finally:
            conn.close()

    def fetch_episodic_memories(self, task_id: str) -> List[Dict[str, Any]]:
        """
        Retrieves compressed JSON episodic summaries for a given task.
        """
        conn = get_knowledge_db()
        results = []
        try:
            rows = conn.execute(
                """
                SELECT memory_id, step_id, agent_type, summary_json, created_at
                FROM episodic_memory
                WHERE task_id = ?
                ORDER BY created_at ASC
                """,
                (task_id,)
            ).fetchall()
            for r in rows:
                data = dict(r)
                if data.get("summary_json"):
                    data["summary"] = json.loads(data["summary_json"])
                results.append(data)
        except Exception as e:
            logger.error(f"Failed to fetch episodic memories: {e}")
        finally:
            conn.close()
        return results

    def get_procedural_rule(self, rule_name: str) -> Optional[Dict[str, Any]]:
        """
        Fetches an active procedural rule or project template from procedural_memory.
        """
        conn = get_knowledge_db()
        try:
            row = conn.execute(
                """
                SELECT rule_id, rule_type, rule_name, rule_content
                FROM procedural_memory
                WHERE rule_name = ? AND is_active = 1
                """,
                (rule_name,)
            ).fetchone()
            if row:
                data = dict(row)
                data["rule_content"] = json.loads(data["rule_content"])
                return data
        except Exception as e:
            logger.error(f"Failed to fetch procedural rule '{rule_name}': {e}")
        finally:
            conn.close()
        return None

    def upsert_procedural_rule(self, rule_name: str, rule_type: str, content: Dict[str, Any]) -> bool:
        """
        Inserts or updates a procedural rule/template.
        """
        conn = get_knowledge_db()
        rule_id = f"rule_{uuid.uuid4().hex[:8]}"
        try:
            conn.execute(
                """
                INSERT INTO procedural_memory (rule_id, rule_type, rule_name, rule_content, is_active)
                VALUES (?, ?, ?, ?, 1)
                ON CONFLICT(rule_name) DO UPDATE SET
                    rule_content = excluded.rule_content,
                    rule_type = excluded.rule_type,
                    updated_at = (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
                """,
                (rule_id, rule_type, rule_name, json.dumps(content))
            )
            conn.commit()
            logger.info(f"Upserted Procedural Rule: {rule_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to upsert procedural rule: {e}")
            return False
        finally:
            conn.close()

memory_layers = MemoryLayersManager()
