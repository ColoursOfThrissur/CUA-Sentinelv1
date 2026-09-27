import logging
import json
import re
from typing import Optional, List, Dict, Any
from tools.memory_tool import MemoryTool
from db.connections import get_operational_db

logger = logging.getLogger(__name__)


class ReflectionEngine:
    """
    Self-Improvement Layer for CUA-Sentinel.
    Post-task reflection: Analyzes completed tasks, distills execution lessons,
    and stores them into persistent vector memory (ChromaDB + SQLite).
    Pre-task recall: Retrieves relevant procedural wisdom before LLM reasoning.
    """

    def __init__(self, memory_tool: Optional[MemoryTool] = None):
        self.memory = memory_tool or MemoryTool()

    async def reflect_on_task(
        self,
        task_id: str,
        workflow_type: str,
        prompt: str,
        result_payload: Optional[Dict[str, Any]],
        status: str = "COMPLETED",
    ) -> Optional[str]:
        """
        Analyze a finished task execution and distill actionable lessons into memory.
        """
        if not prompt or len(prompt.strip()) < 5:
            return None

        # Fetch step traces to see which tools were used
        tools_used = []
        try:
            conn = get_operational_db()
            steps = conn.execute(
                "SELECT step_type, description, status FROM task_steps WHERE task_id = ? ORDER BY step_order",
                (task_id,),
            ).fetchall()
            conn.close()
            tools_used = [s["step_type"] for s in steps if s["status"] == "COMPLETED"]
        except Exception as e:
            logger.debug(f"Could not load steps for reflection: {e}")

        # Distill capability execution lesson
        response_text = ""
        if result_payload:
            response_text = str(
                result_payload.get("response")
                or result_payload.get("answer")
                or result_payload.get("output")
                or ""
            )[:300]

        lesson_type = "SUCCESSFUL_WORKFLOW" if status == "COMPLETED" else "FAILED_WORKFLOW"
        tools_summary = ", ".join(tools_used) if tools_used else "direct reasoning"

        lesson_content = (
            f"Task Type: {workflow_type}\n"
            f"User Intent: {prompt.strip()}\n"
            f"Execution Strategy: {tools_summary}\n"
            f"Outcome: {status}\n"
            f"Key Takeaway: When handling tasks related to '{prompt[:60]}', "
            f"using {tools_summary} produced {status.lower()} outcome. "
            f"Summary: {response_text[:180]}"
        )

        try:
            doc_id = self.memory.ingest(
                source_uri=f"sentinel://reflections/{task_id}",
                domain="AI",
                raw_content=lesson_content,
                authority_level="MAINTAINER_REPO",
            )
            logger.info(f"Self-improvement lesson crystallized for task {task_id} (doc_id={doc_id})")
            return doc_id
        except Exception as err:
            logger.warning(f"Failed to crystallize reflection lesson: {err}")
            return None

    def recall_lessons(self, query: str, top_k: int = 2) -> Optional[str]:
        """
        Query persistent memory for lessons learned relevant to the query.
        Returns a formatted string block suitable for sealed prompt injection.
        """
        if not query or len(query.strip()) < 5:
            return None

        try:
            raw_xml = self.memory.retrieve(query=query, domain="AI", top_k=top_k)
            # Extract content from XML tags if present
            snippets = re.findall(r'<snippet[^>]*>(.*?)</snippet>', raw_xml, re.DOTALL)
            if not snippets:
                return None

            cleaned_lessons = []
            for s in snippets[:top_k]:
                cleaned = s.strip()
                if cleaned:
                    cleaned_lessons.append(f"• {cleaned}")

            if not cleaned_lessons:
                return None

            return "\n".join(cleaned_lessons)
        except Exception as e:
            logger.debug(f"Failed to recall past lessons: {e}")
            return None


reflection_engine = ReflectionEngine()
