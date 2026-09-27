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

    # ------------------------------------------------------------------
    # Pillar 4: Context Compactor
    # ------------------------------------------------------------------

    def compact_conversation_history(
        self, history: List[Dict[str, Any]], max_chars: int = 16000
    ) -> List[Dict[str, Any]]:
        """
        Prevents context overflow for long coding sessions by compacting older
        messages while preserving the last 4 messages AND message[0] intact.

        Strategy:
        - If total chars <= max_chars, return unchanged.
        - Always pin message[0] (the original user goal — never drop it).
        - Compact messages from index 1 to len-4:
            * user messages > 500 chars → truncate to 300 + ellipsis
            * assistant messages with tool_calls → replace with 1-line summary
            * assistant messages > 800 chars → truncate to 500 + ellipsis
            * tool / tool_result messages → replace with compact placeholder
        - Prepend a synthetic system notice after message[0].
        """
        if not history:
            return history

        total_chars = sum(len(msg.get("content", "")) for msg in history)
        if total_chars <= max_chars:
            return history

        keep_tail = 4
        if len(history) <= keep_tail + 1:
            # Only the pinned first message + tail window; nothing to compact.
            return history

        # Always pin message[0] (original user goal)
        pinned_first = history[0]
        # Compactable: index 1 to len-keep_tail-1
        compactable = list(history[1: len(history) - keep_tail])
        tail = list(history[len(history) - keep_tail:])

        compacted: List[Dict[str, Any]] = []
        for msg in compactable:
            role = msg.get("role", "")
            content = msg.get("content", "")
            tool_calls = msg.get("tool_calls", [])
            new_msg = dict(msg)

            if role == "user":
                if len(content) > 500:
                    new_msg["content"] = content[:300] + f" ... [compacted — {len(content)} chars]"

            elif role == "assistant":
                if tool_calls:
                    names = ", ".join(tc.get("name", "unknown") for tc in tool_calls[:5])
                    new_msg["content"] = f"[Tool calls: {names} — compacted]"
                elif len(content) > 800:
                    new_msg["content"] = content[:500] + " ... [compacted]"

            elif role in ("tool", "tool_result", "function"):
                if content:
                    new_msg["content"] = f"[Tool result compacted — {len(content)} chars]"

            compacted.append(new_msg)

        compaction_notice: Dict[str, Any] = {
            "role": "system",
            "content": (
                "[Context Compacted] Earlier conversation has been summarized "
                "to stay within token limits. The original request (above) and "
                "recent messages (below) are complete."
            ),
        }

        # Layout: pinned_first | compaction_notice | compacted middle | tail
        result = [pinned_first, compaction_notice] + compacted + tail

        logger.info(
            f"Context compacted: {total_chars} chars → "
            f"{sum(len(m.get('content', '')) for m in result)} chars "
            f"({len(history)} msgs → {len(result)} msgs, message[0] preserved)"
        )
        return result

    async def async_record_episodic_memory(
        self,
        task_id: str,
        agent_type: str,
        summary_payload: Dict[str, Any],
        step_id: str = None,
        retention_tier: str = "HOT",
    ) -> None:
        """
        Fire-and-forget episodic memory write.
        Does NOT block the caller's response path — safe to use in async request handlers.
        SQLite write is fast (<5ms); ChromaDB embedding is offloaded to a thread.
        """
        import asyncio
        asyncio.create_task(
            asyncio.to_thread(
                self.record_episodic_memory,
                task_id, agent_type, summary_payload, step_id, retention_tier,
            )
        )

    def get_recent_autonomous_activity_summary(self, hours: int = 24) -> str:
        """
        Gathers recent background autonomous actions from project_health_daemon_logs
        and improvement_proposals (past 24h) and formats a short digest for LLM system prompt context.
        """
        from datetime import datetime, timezone, timedelta
        from db.connections import get_operational_db

        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        lines = []

        conn = get_operational_db()
        try:
            # 1. Health Daemon Actions
            cur = conn.execute(
                """
                SELECT project_name, action_taken, pre_health, post_health, created_at
                FROM project_health_daemon_logs
                WHERE created_at >= ?
                ORDER BY created_at DESC LIMIT 5
                """,
                (cutoff,)
            )
            for r in cur.fetchall():
                pname = r["project_name"]
                action = r["action_taken"]
                if action == "AUTO_REPAIRED":
                    lines.append(f"• Health Auto-Repair: Repaired '{pname}', health improved from {r['pre_health']} to {r['post_health']}.")
                elif action == "ROLLED_BACK":
                    lines.append(f"• Health Daemon: Auto-repair for '{pname}' failed verification and was safely rolled back to snapshot.")

            # 2. Improvement Proposals
            cur_p = conn.execute(
                """
                SELECT project_name, title, status, risk_level, created_at
                FROM improvement_proposals
                WHERE created_at >= ?
                ORDER BY created_at DESC LIMIT 5
                """,
                (cutoff,)
            )
            for r in cur_p.fetchall():
                lines.append(f"• Improvement Scout: Drafted '{r['title']}' for {r['project_name']} (Status: {r['status']}, Risk: {r['risk_level']}).")

        except Exception as e:
            logger.debug(f"Error querying recent autonomous activity: {e}")
        finally:
            conn.close()

        if not lines:
            return ""

        return "[RECENT AUTONOMOUS BACKGROUND ACTIVITY (Past 24 Hours)]\n" + "\n".join(lines)

memory_layers = MemoryLayersManager()
