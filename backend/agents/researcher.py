import json
import logging
from agents.base_agent import BaseAgent
from tools.web_search import WebSearchTool

logger = logging.getLogger(__name__)

MAX_RESEARCH_STEPS = 8


class ResearcherAgent(BaseAgent):
    """
    Asynchronous Deep Researcher.
    Takes a complex question, breaks it into a research tree,
    researches each node, compresses findings into episodic memory,
    and synthesizes a final answer.
    Uses hierarchical decomposition so VRAM stays bounded at each step.
    """

    async def run(self, claim) -> dict:
        task_id = claim.task_id
        lease_id = claim.lease_id
        lease_generation = claim.lease_generation
        payload = claim.input_payload
        model_id = self.model_manager.get_model_for_workflow("RESEARCHER")

        question = payload.get("question", "")
        if not question:
            return {"error": "No question provided"}

        # Step 0: Decompose the question into a research plan
        plan_step_id = self.create_step(task_id, 0, "DECOMPOSE", f"Break down: {question[:80]}")
        self.update_step_status(plan_step_id, "RUNNING")

        plan_prompt = f"""You are a research planner. Break this question into 3-6 specific sub-questions that together will answer it completely.

Question: {question}

Respond with only valid JSON in this format:
{{
  "sub_questions": [
    {{"id": 1, "question": "...", "why": "..."}},
    ...
  ],
  "research_strategy": "brief description of approach"
}}"""

        try:
            plan_raw = await self.model_manager.generate_async(
                model_id=model_id,
                task_id=task_id,
                lease_id=lease_id,
                lease_generation=lease_generation,
                prompt=plan_prompt,
                temperature=0.0,
                context_budget=4096,
            )
            plan = json.loads(plan_raw)
        except Exception as e:
            self.update_step_status(plan_step_id, "FAILED", {"error": str(e)})
            return {"error": f"Planning failed: {e}"}

        self.save_artifact(
            task_id,
            "PLAN",
            json.dumps(plan, indent=2),
            step_id=plan_step_id,
            metadata={"question": question},
        )
        self.update_step_status(plan_step_id, "COMPLETED", {"sub_questions": len(plan.get("sub_questions", []))})
        self.save_episodic_memory(task_id, plan_step_id, "RESEARCHER", {
            "outcome": "Research plan created",
            "key_facts": [sq["question"] for sq in plan.get("sub_questions", [])],
            "next_context": plan.get("research_strategy", ""),
            "status": "success",
        })

        # Steps 1-N: Research each sub-question
        web_tool = WebSearchTool()
        findings = []

        for i, sub_q in enumerate(plan.get("sub_questions", [])[:MAX_RESEARCH_STEPS]):
            step_id = self.create_step(task_id, i + 1, "RESEARCH_NODE", sub_q["question"])
            self.update_step_status(step_id, "RUNNING")

            # Heartbeat lease while working
            self.model_manager.__class__  # just a reference to keep linter happy
            from core.queue import TaskQueue
            # Note: heartbeat is handled by scheduler loop

            try:
                # Fetch web content
                search_results = web_tool.search(sub_q["question"], max_results=3)

                # Load only the skeleton context from previous steps.
                context_pack = self.build_context_pack(task_id)
                prior_memory = context_pack["memory_skeleton"]
                context_summary = "\n".join([
                    f"- {m['summary'].get('outcome', '')}: {m['summary'].get('next_context', '')}"
                    for m in prior_memory[-3:]
                ])

                research_prompt = f"""You are researching this specific question: {sub_q["question"]}

Context from previous research steps:
{context_summary}

Web search results:
{search_results[:3000]}

Provide a thorough answer to the specific question above based on the search results.
Be factual. Cite sources where possible. Note any contradictions found."""

                answer = await self.model_manager.generate_async(
                    model_id=model_id,
                    task_id=task_id,
                    lease_id=lease_id,
                    lease_generation=lease_generation,
                    prompt=research_prompt,
                    context_budget=claim.context_budget,
                    temperature=0.1,
                )

                self.save_artifact(
                    task_id,
                    "RAW_OUTPUT",
                    answer,
                    step_id=step_id,
                    metadata={"sub_question": sub_q["question"]},
                )

                # Compress to skeleton before moving to next step
                skeleton = self.compress_to_skeleton(
                    model_id=model_id,
                    task_id=task_id,
                    lease_id=lease_id,
                    lease_generation=lease_generation,
                    raw_output=answer,
                    step_description=sub_q["question"],
                )

                self.save_episodic_memory(task_id, step_id, "RESEARCHER", skeleton)
                self.update_step_status(step_id, "COMPLETED", skeleton)
                findings.append({"question": sub_q["question"], "finding": skeleton})

            except Exception as e:
                logger.error(f"Research step {i+1} failed: {e}")
                self.update_step_status(step_id, "FAILED", {"error": str(e)})

        # Final step: Synthesize all findings
        synth_step_id = self.create_step(task_id, len(findings) + 1, "SYNTHESIZE", "Compile final answer")
        self.update_step_status(synth_step_id, "RUNNING")

        all_findings = "\n\n".join([
            f"Q: {f['question']}\nFinding: {f['finding'].get('outcome', '')} — {f['finding'].get('next_context', '')}"
            for f in findings
        ])

        synthesis_prompt = f"""You have completed research on: {question}

Here are the findings from each sub-question:
{all_findings}

Write a comprehensive, well-structured answer to the original question.
Include key facts, cite sources where available, and note any areas of uncertainty."""

        try:
            final_answer = await self.model_manager.generate_async(
                model_id=model_id,
                task_id=task_id,
                lease_id=lease_id,
                lease_generation=lease_generation,
                prompt=synthesis_prompt,
                context_budget=claim.context_budget,
                temperature=0.2,
            )
            self.save_artifact(
                task_id,
                "FINAL_REPORT",
                final_answer,
                step_id=synth_step_id,
                metadata={"question": question, "findings_count": len(findings)},
            )
            self.update_step_status(synth_step_id, "COMPLETED", {"answer_length": len(final_answer)})
            logger.info(f"Researcher task {task_id} completed with {len(findings)} findings.")
            return {
                "question": question,
                "answer": final_answer,
                "findings_count": len(findings),
                "model_used": model_id,
            }

        except Exception as e:
            self.update_step_status(synth_step_id, "FAILED", {"error": str(e)})
            return {"error": f"Synthesis failed: {e}", "partial_findings": findings}
