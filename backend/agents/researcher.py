import json
import logging
import uuid
import re
from datetime import datetime, timezone
from urllib.parse import urlparse
from typing import Dict, Any, List

from agents.base_agent import BaseAgent
from tools.web_search import WebSearchTool
try:
    from db.repositories.knowledge_repo import KnowledgeRepository
except (ImportError, ModuleNotFoundError):
    from backend.db.repositories.knowledge_repo import KnowledgeRepository
from core.sealed_envelope import build_sealed_envelope

logger = logging.getLogger(__name__)

MAX_RESEARCH_STEPS = 6

OFFICIAL_SPEC_DOMAINS = {
    "w3.org", "ietf.org", "iso.org", "ecma-international.org", "unicode.org"
}

OFFICIAL_DOCS_DOMAINS = {
    "python.org", "docs.python.org", "developer.mozilla.org", "react.dev",
    "nodejs.org", "fastapi.tiangolo.com", "pydantic.dev", "docs.docker.com",
    "pytorch.org", "tensorflow.org", "huggingface.co", "microsoft.com",
    "apple.com", "google.com", "cloudflare.com", "tailscale.com"
}

PEER_REVIEWED_DOMAINS = {
    "arxiv.org", "nature.com", "ieee.org", "sciencedirect.com", "acm.org", "springer.com"
}

COMMUNITY_DOMAINS = {
    "reddit.com", "medium.com", "dev.to", "stackoverflow.com", "news.ycombinator.com",
    "x.com", "twitter.com", "quora.com", "hashnode.dev"
}


class ResearcherAgent(BaseAgent):
    """
    Production-Grade Autonomous Deep Researcher.
    - Declarative profile researcher.yaml loaded at startup.
    - Prompt assembly strictly routed through call_llm().
    - Web search strictly routed through execute_tool().
    - Untrusted web context sealed with cryptographically generated nonces.
    - Hierarchical problem decomposition into search sub-nodes.
    - Real-time step-trace telemetry broadcast over WebSockets.
    - Atomic claims extraction and persistent indexing into SQLite knowledge.db.
    """
    PROFILE_NAME = "researcher"

    def classify_source_authority(self, url: str) -> str:
        """Determines the authority tier of a source URI according to knowledge_v1 schema."""
        if not url:
            return "UNVERIFIED"
        domain = urlparse(url).netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]

        if any(domain == d or domain.endswith("." + d) for d in OFFICIAL_SPEC_DOMAINS):
            return "OFFICIAL_SPEC"
        if domain.endswith(".gov") or domain.endswith(".edu"):
            return "OFFICIAL_DOCS"
        if any(domain == d or domain.endswith("." + d) for d in OFFICIAL_DOCS_DOMAINS):
            return "OFFICIAL_DOCS"
        if domain in ("github.com", "gitlab.com"):
            return "MAINTAINER_REPO"
        if any(domain == d or domain.endswith("." + d) for d in PEER_REVIEWED_DOMAINS):
            return "PEER_REVIEWED"
        if any(domain == d or domain.endswith("." + d) for d in COMMUNITY_DOMAINS):
            return "COMMUNITY"
        return "UNVERIFIED"

    def classify_domain(self, text: str) -> str:
        """Classifies text into one of knowledge.db's CHECK constraint domains using word boundaries."""
        t = text.lower()
        patterns = {
            "UI_UX": [r"\bcss\b", r"\bui\b", r"\bux\b", r"\bdesign\b", r"\btailwind\b", r"\bfigma\b", r"\bfrontend\b", r"\bhtml\b"],
            "AI": [r"\bai\b", r"\bllm\b", r"\bmodel\b", r"\bneural\b", r"\bdeep learning\b", r"\bgpt\b", r"\btransformer\b", r"\bollama\b"],
            "FINANCE": [r"\bstock\b", r"\bmarket\b", r"\bfinance\b", r"\bprice\b", r"\bcrypto\b", r"\bbitcoin\b", r"\bdollar\b", r"\binr\b", r"\bportfolio\b"],
            "CODE": [r"\bcode\b", r"\bpython\b", r"\bjavascript\b", r"\bbug\b", r"\bgit\b", r"\bapi\b", r"\bdocker\b", r"\btest\b", r"\bfunction\b", r"\bqueue\b"],
            "PERSONAL": [r"\bpersonal\b", r"\bhealth\b", r"\bdiary\b", r"\breminder\b", r"\bemail\b", r"\bschedule\b"],
        }
        for domain, regexes in patterns.items():
            if any(re.search(p, t) for p in regexes):
                return domain
        return "OTHER"

    @classmethod
    def expand_search_terms(cls, query: str) -> list[str]:
        """Expands queries with formal technical domain terms, canonical benchmarks, and synonyms."""
        q_lower = query.lower()
        expanded = [query]
        EXPANSIONS = {
            r"\b(ui\s+mockup|ui\s+parsing|parse\s+ui|button\s+click|ui\s+grounding|bounding\s+box)\b": [
                "GUI grounding ScreenSpot WebUIBench visual localization",
                "bounding box coordinate prediction UI OmniParser",
            ],
            r"\b(vram|memory\s+usage|memory\s+requirement)\b": [
                "4-bit quantization VRAM requirements GGUF AWQ parameter memory footprint",
            ],
            r"\b(tok/s|speed|latency|tokens\s+per\s+second)\b": [
                "inference speed tokens per second RTX 3060 throughput latency benchmark",
            ],
            r"\b(qwen2\.5-vl|qwen\s*2\.5\s*vl)\b": [
                "Qwen2.5-VL visual grounding benchmark ScreenSpot bounding box 3B 7B",
            ],
            r"\b(minicpm-v|minicpm\s*v)\b": [
                "MiniCPM-V 2.6 OCR GUI grounding benchmark UI localization 8B",
            ],
            r"\b(smolvlm)\b": [
                "SmolVLM 2B visual question answering GUI bounding box localization",
            ],
        }
        for pattern, terms in EXPANSIONS.items():
            if re.search(pattern, q_lower):
                for t in terms:
                    if t not in expanded:
                        expanded.append(t)
        return expanded

    async def run(self, claim) -> dict:
        task_id = claim.task_id
        lease_id = claim.lease_id
        lease_generation = claim.lease_generation
        payload = claim.input_payload or {}
        model_id = self.model_manager.get_model_for_workflow("RESEARCHER")

        question = payload.get("question") or payload.get("prompt", "")
        depth = payload.get("depth", "deep")
        max_subnodes = 2 if depth == "quick" else 4

        if not question:
            return {"error": "No question provided"}

        domain_tag = self.classify_domain(question)
        logger.info(f"ResearcherAgent starting task {task_id} for '{question[:80]}' (Domain: {domain_tag}, Depth: {depth})")

        # Step 0: Decompose the question into a structured research plan
        plan_step_id = self.create_step(task_id, 0, "DECOMPOSE", f"Plan breakdown: {question[:80]}")
        self.update_step_status(plan_step_id, "RUNNING")
        await self.broadcast_step_trace(task_id, "DECOMPOSITION", "ResearcherAgent", "RUNNING", {"question": question})

        now_dt = datetime.now()
        current_date_str = now_dt.strftime("%A, %B %d, %Y")
        plan_system = (
            f"You are an elite technical research analyst operating in {now_dt.year} (Today: {current_date_str}).\n"
            f"Break down this research question into {max_subnodes} distinct, highly specific sub-questions with targeted search queries.\n"
            f"CRITICAL TAXONOMY RULES:\n"
            f"1. Bridge colloquial user vocabulary to formal academic and industry terminology and canonical benchmarks.\n"
            f"   (e.g., 'UI mockup parsing / button clicking' -> 'GUI grounding, ScreenSpot, WebUIBench, OmniParser, visual localization, bounding box prediction').\n"
            f"2. Ensure EVERY model, framework, or constraint named in the prompt (e.g. parameter sizes, VRAM limits, RTX 3060) is explicitly investigated.\n"
            f"3. In search queries, combine model names with canonical benchmark and architectural terms.\n"
            f"Target current {now_dt.year} developments and live sources. Do NOT focus on outdated history unless asked."
        )
        plan_task = f"""Question: {question}

Respond with only valid JSON in this exact schema:
{{
  "sub_questions": [
    {{
      "id": 1,
      "question": "Clear focused sub-question",
      "search_query": "specific search engine keywords",
      "why": "rationale for investigating this"
    }}
  ],
  "research_strategy": "brief 1-2 sentence strategy"
}}"""

        try:
            plan_raw = await self.call_llm(
                task_id=task_id,
                system_rules=plan_system,
                task_prompt=plan_task,
                model_id=model_id,
                lease_id=lease_id,
                lease_generation=lease_generation,
                temperature=0.0,
                context_budget=4096,
            )
            # Clean possible markdown code fences
            cleaned_plan_raw = re.sub(r"^```(json)?\s*|\s*```$", "", plan_raw.strip())
            plan = json.loads(cleaned_plan_raw)
        except Exception as e:
            logger.warning(f"Structured plan parsing failed: {e}. Falling back to default plan.")
            plan = {
                "sub_questions": [
                    {"id": 1, "question": question, "search_query": question, "why": "Direct inquiry"}
                ],
                "research_strategy": "Direct search inquiry",
            }

        sub_questions = plan.get("sub_questions", [])[:max_subnodes]
        self.save_artifact(
            task_id,
            "PLAN",
            json.dumps(plan, indent=2),
            step_id=plan_step_id,
            metadata={"question": question, "sub_nodes": len(sub_questions)},
        )
        self.update_step_status(plan_step_id, "COMPLETED", {"sub_questions": len(sub_questions)})
        self.save_episodic_memory(task_id, plan_step_id, "RESEARCHER", {
            "outcome": "Research plan created",
            "key_facts": [sq["question"] for sq in sub_questions],
            "next_context": plan.get("research_strategy", ""),
            "status": "success",
        })
        await self.broadcast_step_trace(task_id, "DECOMPOSITION", "ResearcherAgent", "COMPLETED", {
            "sub_questions_count": len(sub_questions),
            "strategy": plan.get("research_strategy", "")
        })

        # Steps 1-N: Execute Research on each Sub-Node
        web_tool = WebSearchTool()
        findings = []
        collected_sources = []

        for i, sub_q in enumerate(sub_questions):
            q_text = sub_q.get("question", "")
            search_q = sub_q.get("search_query") or q_text
            step_id = self.create_step(task_id, i + 1, "RESEARCH_NODE", q_text)
            self.update_step_status(step_id, "RUNNING")
            await self.broadcast_step_trace(task_id, f"NODE_{i+1}_SEARCH", "WebSearchTool", "RUNNING", {
                "sub_question": q_text,
                "search_query": search_q,
            })

            try:
                # 1. Structured Multi-Engine Search via Tool Gateway
                tool_res = await self.execute_tool("web_search", {"query": search_q, "max_results": 4}, task_id=task_id, step_id=step_id)
                raw_search_res = tool_res.get("data") or ""

                search_items = web_tool.search_structured(search_q, max_results=3)
                node_sources = []
                deep_content_snippets = []

                for item in search_items[:2]:
                    target_url = item.get("url")
                    if target_url:
                        authority = self.classify_source_authority(target_url)
                        node_sources.append({
                            "url": target_url,
                            "title": item.get("title", ""),
                            "authority": authority,
                            "snippet": item.get("snippet", ""),
                        })
                        collected_sources.append(node_sources[-1])

                        # 2. Deep Article Scrape if URL is valid
                        scraped = web_tool.deep_scrape_url(target_url, max_chars=3500)
                        if scraped.get("content"):
                            deep_content_snippets.append(
                                f"--- SOURCE: {item.get('title')} ({target_url}) [Authority: {authority}] ---\n{scraped['content'][:2500]}"
                            )

                # Supplementary Search using expanded domain & benchmark taxonomy
                if len(node_sources) < 2:
                    expanded_list = self.expand_search_terms(search_q)
                    for exp_q in expanded_list[1:]:
                        sup_items = web_tool.search_structured(exp_q, max_results=2)
                        for item in sup_items:
                            target_url = item.get("url")
                            if target_url and not any(s["url"] == target_url for s in node_sources):
                                authority = self.classify_source_authority(target_url)
                                node_sources.append({
                                    "url": target_url,
                                    "title": item.get("title", ""),
                                    "authority": authority,
                                    "snippet": item.get("snippet", ""),
                                })
                                collected_sources.append(node_sources[-1])
                                scraped = web_tool.deep_scrape_url(target_url, max_chars=3500)
                                if scraped.get("content"):
                                    deep_content_snippets.append(
                                        f"--- SOURCE: {item.get('title')} ({target_url}) [Authority: {authority}] ---\n{scraped['content'][:2500]}"
                                    )
                                if len(node_sources) >= 3:
                                    break
                        if len(node_sources) >= 3:
                            break

                search_summary = "\n\n".join([f"[{s['authority']}] {s['title']}: {s['snippet']}" for s in node_sources]) or raw_search_res
                combined_evidence = f"Search Results:\n{search_summary}\n\nDetailed Source Excerpts:\n" + ("\n\n".join(deep_content_snippets) if deep_content_snippets else "None available.")

                await self.broadcast_step_trace(task_id, f"NODE_{i+1}_ANALYSIS", "ResearcherAgent", "RUNNING", {
                    "sources_found": len(node_sources),
                    "deep_pages_scraped": len(deep_content_snippets)
                })

                # 3. Analyze Evidence with Sealed Envelope + call_llm
                evidence_envelope = build_sealed_envelope(combined_evidence[:5000], origin=f"web:{search_q}")
                node_system = "You are an elite researcher investigating this sub-question."
                node_task = (
                    f"Question: {q_text}\n\n"
                    f"Provide a clear, factual, and concise answer to the sub-question based strictly on the evidence above.\n"
                    f"Include specific facts, figures, and cite the sources where possible."
                )

                answer = await self.call_llm(
                    task_id=task_id,
                    system_rules=node_system,
                    task_prompt=node_task,
                    untrusted_blocks=[evidence_envelope],
                    model_id=model_id,
                    lease_id=lease_id,
                    lease_generation=lease_generation,
                    context_budget=claim.context_budget,
                    temperature=0.1,
                )

                self.save_artifact(
                    task_id,
                    "RAW_OUTPUT",
                    answer,
                    step_id=step_id,
                    metadata={"sub_question": q_text, "sources": [s["url"] for s in node_sources]},
                )

                skeleton = self.compress_to_skeleton(
                    model_id=model_id,
                    task_id=task_id,
                    lease_id=lease_id,
                    lease_generation=lease_generation,
                    raw_output=answer,
                    step_description=q_text,
                )

                self.save_episodic_memory(task_id, step_id, "RESEARCHER", skeleton)
                self.update_step_status(step_id, "COMPLETED", skeleton)
                findings.append({
                    "question": q_text,
                    "finding": skeleton,
                    "detailed_answer": answer,
                    "sources": node_sources,
                })
                await self.broadcast_step_trace(task_id, f"NODE_{i+1}_COMPLETE", "ResearcherAgent", "COMPLETED", {
                    "sub_question": q_text,
                    "outcome": skeleton.get("outcome", "")[:100]
                })

            except Exception as e:
                logger.error(f"Research node {i+1} failed: {e}")
                self.update_step_status(step_id, "FAILED", {"error": str(e)})
                await self.broadcast_step_trace(task_id, f"NODE_{i+1}_ERROR", "ResearcherAgent", "FAILED", {"error": str(e)})

        # Final Step: Synthesize Full Report & Extract Structured Claims
        synth_step_id = self.create_step(task_id, len(findings) + 1, "SYNTHESIZE", "Compile final research report")
        self.update_step_status(synth_step_id, "RUNNING")
        await self.broadcast_step_trace(task_id, "SYNTHESIZING_REPORT", "ResearcherAgent", "RUNNING", {
            "findings_count": len(findings)
        })

        all_findings_block = "\n\n".join([
            f"### Sub-Question: {f['question']}\n**Key Finding**: {f['finding'].get('outcome', '')}\n{f['detailed_answer']}"
            for f in findings
        ])

        unique_sources = []
        seen_urls = set()
        for s in collected_sources:
            if s.get("url") and s["url"] not in seen_urls:
                seen_urls.add(s["url"])
                unique_sources.append(s)

        sources_list_md = "\n".join([f"- [{s.get('title') or s.get('url')}]({s.get('url')}) `[{s.get('authority')}]`" for s in unique_sources]) or "- No external web sources recorded."

        synthesis_prompt = f"""You have conducted deep research on the topic: "{question}"

Here are the synthesized findings from all investigated sub-questions:
{all_findings_block}

Available Sources:
{sources_list_md}

Write an authoritative, beautifully structured research report in GitHub-flavored markdown.
Include:
1. # Executive Summary (concise 1-2 paragraph overview)
2. ## Detailed Findings (key developments, data, architecture, comparisons)
3. ## Verified Takeaways & Fact Sheet (bullet points of verified facts)
4. ## Caveats & Open Questions
5. ## References & Sources (include markdown links with source authority)

Write thoroughly and professionally with no fluff. Ground the report in current {now_dt.year} developments and live sources."""

        try:
            draft_report = await self.call_llm(
                task_id=task_id,
                system_rules=f"You are an elite research analyst operating in {now_dt.year} (Today: {current_date_str}). Write an authoritative, beautifully structured research report in GitHub-flavored markdown. Emphasize current real-world developments.",
                task_prompt=synthesis_prompt,
                model_id=model_id,
                lease_id=lease_id,
                lease_generation=lease_generation,
                context_budget=claim.context_budget,
                temperature=0.2,
            )

            # Verification & Anti-Hallucination Gate
            await self.broadcast_step_trace(task_id, "VERIFYING_REPORT", "ResearcherAgent", "RUNNING", {})
            final_report = await self._verify_and_ground_report(
                task_id=task_id,
                model_id=model_id,
                lease_id=lease_id,
                lease_generation=lease_generation,
                context_budget=claim.context_budget,
                question=question,
                draft_report=draft_report,
                findings=findings,
            )

            # Step: Extract Atomic Claims and Insert into SQLite knowledge.db (research_claims table)
            await self.broadcast_step_trace(task_id, "EXTRACTING_CLAIMS", "ResearcherAgent", "RUNNING", {})
            claims_count = self._persist_research_claims(
                task_id=task_id,
                domain=domain_tag,
                findings=findings,
                sources=unique_sources,
            )

            # Step: Persist Canonical Document into knowledge.db
            self._persist_canonical_document(
                task_id=task_id,
                question=question,
                domain=domain_tag,
                report_content=final_report,
                sources=unique_sources,
            )

            self.save_artifact(
                task_id,
                "FINAL_REPORT",
                final_report,
                step_id=synth_step_id,
                metadata={
                    "question": question,
                    "findings_count": len(findings),
                    "claims_count": claims_count,
                    "sources_count": len(unique_sources),
                    "domain": domain_tag,
                },
            )
            self.update_step_status(synth_step_id, "COMPLETED", {
                "answer_length": len(final_report),
                "claims_extracted": claims_count,
            })
            await self.broadcast_step_trace(task_id, "REPORT_COMPLETED", "ResearcherAgent", "COMPLETED", {
                "report_length": len(final_report),
                "claims_count": claims_count,
                "sources_count": len(unique_sources),
            })

            logger.info(f"Researcher task {task_id} completed: {claims_count} claims stored, {len(unique_sources)} sources.")
            return {
                "question": question,
                "domain": domain_tag,
                "answer": final_report,
                "findings_count": len(findings),
                "claims_count": claims_count,
                "sources": unique_sources,
                "model_used": model_id,
            }

        except Exception as e:
            logger.error(f"Synthesis failed: {e}")
            self.update_step_status(synth_step_id, "FAILED", {"error": str(e)})
            await self.broadcast_step_trace(task_id, "SYNTHESIS_ERROR", "ResearcherAgent", "FAILED", {"error": str(e)})
            return {"error": f"Synthesis failed: {e}", "partial_findings": findings}

    def _persist_research_claims(self, task_id: str, domain: str, findings: List[dict], sources: List[dict]) -> int:
        """
        Parses findings and extracts atomic claims into the research_claims table of knowledge.db.
        Enforces schema constraints: confidence_score BETWEEN 0.0 AND 1.0, source_authority CHECK.
        """
        count = 0
        now = datetime.now(timezone.utc).isoformat()
        primary_source = sources[0] if sources else {}
        source_url = primary_source.get("url", "https://sentinel.internal/research")
        source_auth = primary_source.get("authority", "UNVERIFIED")
        repo = KnowledgeRepository()

        try:
            for f in findings:
                finding_text = f.get("finding", {}).get("outcome") or f.get("detailed_answer", "")
                if not finding_text:
                    continue

                # Break finding into bullet points or sentences
                sentences = [s.strip() for s in re.split(r"[.\n•]+", finding_text) if len(s.strip()) > 25]
                for sentence in sentences[:3]:
                    claim_id = f"claim_{uuid.uuid4().hex[:12]}"
                    confidence = 0.90 if source_auth in ("OFFICIAL_SPEC", "OFFICIAL_DOCS", "PEER_REVIEWED") else 0.75

                    repo.save_claim(
                        task_id=task_id,
                        claim_text=sentence[:500],
                        source_uri=source_url,
                        source_authority=source_auth,
                        retrieval_timestamp=now,
                        confidence_score=confidence,
                        confidence_basis=f"Extracted by Deep Researcher from {urlparse(source_url).netloc or 'web sources'}",
                        domain=domain,
                        claim_id=claim_id,
                    )
                    count += 1
            return count
        except Exception as e:
            logger.warning(f"Error persisting research claims: {e}")
            return count

    def _persist_canonical_document(self, task_id: str, question: str, domain: str, report_content: str, sources: List[dict]) -> None:
        """
        Indexes the complete research report into canonical_documents table in knowledge.db
        for Second Brain / RAG queryability.
        """
        doc_id = f"doc_research_{uuid.uuid4().hex[:10]}"
        primary_url = sources[0].get("url") if sources else f"urn:task:{task_id}"
        primary_auth = sources[0].get("authority") if sources else "UNVERIFIED"
        repo = KnowledgeRepository()

        try:
            repo.upsert_document(
                source_uri=primary_url,
                domain=domain,
                authority_level=primary_auth,
                title=f"Research: {question[:120]}",
                raw_content=report_content,
                document_hash=str(hash(report_content)),
                embedding_config_hash="nomic-v1.5",
                document_id=doc_id,
                index_status="INDEXED",
            )
            logger.info(f"Persisted Canonical Document {doc_id} into knowledge.db for task {task_id}")
        except Exception as e:
            logger.warning(f"Error persisting canonical document: {e}")

    async def _verify_and_ground_report(
        self,
        task_id: str,
        model_id: str,
        lease_id: str,
        lease_generation: int,
        context_budget: int,
        question: str,
        draft_report: str,
        findings: list,
    ) -> str:
        """
        Anti-Hallucination & Mathematical Grounding Gate.
        Enforces:
        1. Constraint Coverage: all requested models/entities must be directly evaluated.
        2. Hardware / VRAM Mathematical Grounding:
           Formula: VRAM (GB) ≈ (Parameters in Billions * Quantization_Bits / 8) * 1.25 overhead.
           - 2B model at 4-bit ≈ 1.2 - 1.6 GB VRAM
           - 3B model at 4-bit ≈ 2.0 - 2.5 GB VRAM
           - 7B - 8B model at 4-bit ≈ 4.8 - 5.5 GB VRAM
           - RTX 3060 12GB can comfortably run 4-bit 7B/8B models with full KV cache.
           Rejects phantom models (e.g. 'Gemma 4 E4B 15GB').
        3. Anti-Dodging Rule: Rejects topic deflection (e.g. pivoting to unrequested papers like 'SparkUI-Parser' or claiming 'no data' when architectural inference is possible).
        """
        prompt = (
            f"You are a strict technical verification judge and fact checker.\n"
            f"Review this draft research report against the user's original inquiry:\n\n"
            f"Original Inquiry: {question}\n\n"
            f"Draft Research Report:\n{draft_report}\n\n"
            f"Verification Rules:\n"
            f"1. Model & Entity Coverage: Did the report directly evaluate EVERY model and constraint mentioned in the inquiry?\n"
            f"2. Mathematical VRAM Grounding: Verify that all memory numbers adhere to the physical law:\n"
            f"   VRAM ≈ (Parameters in Billions * Bits_per_weight / 8) * 1.25.\n"
            f"   - 2B model at 4-bit ≈ 1.2 - 1.6 GB VRAM\n"
            f"   - 3B model at 4-bit ≈ 2.0 - 2.5 GB VRAM\n"
            f"   - 7B - 8B model at 4-bit ≈ 4.8 - 5.5 GB VRAM\n"
            f"   Reject and eliminate any phantom/hallucinated model names (such as 'Gemma 4', 'E4B 15GB', etc.).\n"
            f"3. Anti-Dodging & Topic Deflection Ban: If the report claims 'no benchmark data is available' and pivots to summarize an unrelated paper (e.g. SparkUI-Parser) as a distraction tactic, ELIMINATE that deflection. Instead, evaluate the models' actual architectural capabilities (native dynamic resolution, visual tokens, coordinate output) on GUI grounding benchmarks like ScreenSpot and WebUIBench.\n\n"
            f"If the report passes with no hallucinations and complete coverage, return the report unchanged.\n"
            f"If any violations, phantom models, ungrounded math, or deflections are found, output the corrected, fully grounded report in markdown.\n"
            f"Do NOT output commentary, preamble, or critique meta-text. Output ONLY the finalized report markdown."
        )
        try:
            verified = await self.call_llm(
                task_id=task_id,
                system_rules="You are an uncompromising technical auditor and fact checker. Output only the validated, corrected markdown report with zero meta-commentary.",
                task_prompt=prompt,
                model_id=model_id,
                lease_id=lease_id,
                lease_generation=lease_generation,
                context_budget=context_budget,
                temperature=0.0,
            )
            if verified and len(verified.strip()) > 200 and not verified.strip().startswith("⚠️"):
                return verified.strip()
        except Exception as e:
            logger.warning(f"Verification pass error: {e}")
        return draft_report


