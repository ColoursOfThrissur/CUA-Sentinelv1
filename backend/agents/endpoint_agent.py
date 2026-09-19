import logging
import re
from datetime import datetime
from agents.base_agent import BaseAgent
from tools.web_search import WebSearchTool
from tools.finance_tools import FinanceTools
from tools.link_manager import LinkManager

logger = logging.getLogger(__name__)

WEB_HINTS = (
    "web", "internet", "search", "look up", "lookup", "latest", "current",
    "today", "news", "price", "weather", "fetch", "http://", "https://",
)

FINANCE_TICKER_MAP = {
    "nvidia": "NVDA",
    "nvda": "NVDA",
    "apple": "AAPL",
    "aapl": "AAPL",
    "tesla": "TSLA",
    "tsla": "TSLA",
    "bitcoin": "BTC-USD",
    "btc": "BTC-USD",
    "ethereum": "ETH-USD",
    "eth": "ETH-USD",
    "gold": "GC=F",
    "rupee": "INR=X",
    "inr": "INR=X",
    "microsoft": "MSFT",
    "msft": "MSFT",
    "google": "GOOGL",
    "amazon": "AMZN",
}


class EndpointAgent(BaseAgent):
    """
    Universal Endpoint — direct chat from phone or browser.
    Priority 0 fast path with intelligent auto-wiring for:
    1. Financial Ticker Quotes & Portfolio Alerts (FinanceTools)
    2. URL Bookmarking & RAG Indexing (LinkManager)
    3. Web Search Enrichment (WebSearchTool)
    """

    def __init__(self, model_manager, governance, config):
        super().__init__(model_manager, governance, config)
        self.finance_tools = FinanceTools()
        self.link_manager = LinkManager()

    def _should_use_web(self, prompt: str, explicit: bool) -> bool:
        text = prompt.lower()
        return explicit or any(hint in text for hint in WEB_HINTS)

    def _extract_ticker_symbol(self, prompt: str) -> str:
        text = prompt.lower()
        for key, symbol in FINANCE_TICKER_MAP.items():
            if key in text:
                return symbol
        # Regex search for explicit uppercase symbols like NVDA, AAPL, BTC-USD
        match = re.search(r'\b[A-Z]{2,5}(-[A-Z]{3})?\b', prompt)
        if match:
            return match.group(0)
        return ""

    async def run(self, claim) -> dict:
        task_id = claim.task_id
        lease_id = claim.lease_id
        lease_generation = claim.lease_generation
        payload = claim.input_payload

        prompt = payload.get("prompt", "")
        now_str = datetime.now().strftime("%A, %B %d, %Y (%I:%M %p)")
        base_prompt = payload.get("system_prompt") or (
            "You are CUA-Sentinel, an intelligent personal AI assistant running locally on the user's PC. "
            "Provide direct, accurate, and helpful answers to user requests. When context data is provided, use it directly without issuing unnecessary disclaimers or mentioning unrelated tools."
        )

        from core.memory_layers import memory_layers
        recent_activity = memory_layers.get_recent_autonomous_activity_summary(hours=24)
        activity_context = f"\n\n{recent_activity}" if recent_activity else ""

        system_prompt = f"{base_prompt}\nToday's Date & Time: {now_str}{activity_context}"
        use_web = bool(payload.get("use_web"))

        if not prompt:
            return {"error": "No prompt provided"}

        model_id = self.model_manager.get_model_for_workflow("ENDPOINT")
        step_id = self.create_step(task_id, 0, "DIRECT_CHAT", "Direct chat response")
        self.update_step_status(step_id, "RUNNING")

        try:
            extra_contexts = []

            # 0. Wire Prior Multi-Turn Conversation History
            history = payload.get("history", [])
            if history and isinstance(history, list):
                recent_history = history[-8:]
                history_lines = []
                for msg in recent_history:
                    role_label = "User" if msg.get("role") == "user" else "Assistant"
                    content_str = str(msg.get("content", "")).strip()
                    if content_str:
                        history_lines.append(f"{role_label}: {content_str[:500]}")
                if history_lines:
                    extra_contexts.append("[PRIOR CONVERSATION HISTORY]\n" + "\n".join(history_lines))

            # 1. Wire URL Link Auto-Bookmark & RAG Indexer
            urls = re.findall(r'https?://[^\s]+', prompt)
            if urls:
                await self.broadcast_step_trace(task_id, "INTENT_DETECTED", "LinkManager", "RUNNING", {"url": urls[0]})
                for target_url in urls[:2]:
                    link_res = self.link_manager.add_link(target_url)
                    crawled = await self.link_manager.crawl_and_process(link_res["link_id"])
                    if crawled.get("status") == "INDEXED":
                        extra_contexts.append(
                            f"[BOOKMARK INDEXED]\nURL: {target_url}\nTitle: {crawled.get('title')}\nSummary: {crawled.get('summary')}"
                        )
                        await self.broadcast_step_trace(task_id, "BOOKMARK_INDEXED", "LinkManager", "COMPLETED", {"title": crawled.get('title')})

            # 2. Wire Financial Market Quotes & Ticker Lookup
            ticker_symbol = self._extract_ticker_symbol(prompt)
            if ticker_symbol or any(k in prompt.lower() for k in ["stock", "price", "ticker", "portfolio", "crypto", "value"]):
                symbol_to_fetch = ticker_symbol or "NVDA"
                await self.broadcast_step_trace(task_id, "FETCH_MARKET_QUOTE", "FinanceTools", "RUNNING", {"symbol": symbol_to_fetch})
                quote = await self.finance_tools.fetch_ticker_quote(symbol_to_fetch)
                if quote.get("price"):
                    extra_contexts.append(
                        f"[LIVE MARKET TICKER DATA]\nSymbol: {quote['symbol']}\nName: {quote['name']}\nCurrent Price: ${quote['price']:,.2f} {quote['currency']}\n24h Change: {quote['change_24h_pct']:+.2f}%\nTimestamp: {quote['timestamp']}"
                    )
                    await self.broadcast_step_trace(task_id, "FETCH_MARKET_QUOTE", "FinanceTools", "COMPLETED", {"symbol": quote['symbol'], "price": f"${quote['price']:,.2f}"})

            # 3. Wire Web Search Enrichment if requested or detected
            web_context = ""
            if self._should_use_web(prompt, use_web):
                self.governance.check_tool_permission("web_search", task_id)
                self.update_step_status(step_id, "RUNNING", {"web_context": "fetching"})
                await self.broadcast_step_trace(task_id, "WEB_SEARCH", "WebSearchTool", "RUNNING", {"query": prompt})
                web_context = WebSearchTool().search(prompt, max_results=4)
                if web_context:
                    from core.scraper_sanitizer import scraper_sanitizer
                    clean_web_context, _, _ = scraper_sanitizer.sanitize_text(web_context)
                    extra_contexts.append(f"[WEB SEARCH CONTEXT]\n{clean_web_context}")
                    await self.broadcast_step_trace(task_id, "WEB_SEARCH", "WebSearchTool", "COMPLETED", {"results_count": 4})

            # 4. Wire Gmail Email Inbox Search Integration (via ToolRegistry capability detection)
            from core.tool_registry import ToolRegistry
            detected_caps = ToolRegistry.detect_explicit_capabilities(prompt)
            has_gmail_intent = any(c.capability_id == "GMAIL_INBOX" for c in detected_caps)

            if has_gmail_intent:
                try:
                    from core.alert_manager import AlertManager
                    from core.email_engine import EmailEngine
                    am = AlertManager()
                    e_user = am._get_setting("smtp_user")
                    e_pass = am._get_setting("smtp_app_password")
                    if e_user and e_pass:
                        await self.broadcast_step_trace(task_id, "FETCH_GMAIL_CONTEXT", "EmailEngine", "RUNNING", {"query": prompt})
                        ee = EmailEngine()
                        email_results = ee.search_emails(e_user, e_pass, prompt, max_results=5)
                        if email_results:
                            mail_blocks = [f"From: {m['sender']}\nDate: {m['date']}\nSubject: {m['subject']}\nEmail Body:\n{m['snippet']}" for m in email_results]
                            extra_contexts.append("[GMAIL INBOX SEARCH CONTEXT]\n" + "\n---\n".join(mail_blocks))
                            await self.broadcast_step_trace(task_id, "FETCH_GMAIL_CONTEXT", "EmailEngine", "COMPLETED", {"matches_found": len(email_results)})
                except Exception as mail_err:
                    logger.warning(f"Error fetching Gmail context: {mail_err}")

            # Dynamic Tool Routing for 12GB VRAM System Prompt Optimization
            tool_context = ToolRegistry.get_relevant_capabilities_prompt(prompt, max_tools=2)
            active_system_prompt = f"{system_prompt}\n\n{tool_context}"

            final_prompt = prompt
            if extra_contexts:
                combined_context = "\n\n".join(extra_contexts)
                final_prompt = f"""[CONTEXT DATA]
{combined_context}

[USER REQUEST]
{prompt}

Answer the user's request directly using any relevant context provided above."""

            response = await self.model_manager.generate_async(
                model_id=model_id,
                task_id=task_id,
                lease_id=lease_id,
                lease_generation=lease_generation,
                prompt=final_prompt,
                system_prompt=active_system_prompt,
                context_budget=claim.context_budget,
                temperature=0.7,
                keep_alive=self.model_manager.keep_alive_endpoint,
            )

            # Record Episodic Memory JSON log
            try:
                from core.memory_layers import memory_layers
                memory_layers.record_episodic_memory(
                    task_id=task_id,
                    step_id=step_id,
                    agent_type="ENDPOINT",
                    summary_payload={
                        "prompt": prompt[:200],
                        "response_snippet": str(response)[:200],
                        "context_types": [c.split('\n')[0] for c in extra_contexts]
                    }
                )
            except Exception as mem_err:
                logger.warning(f"Failed to save chat episodic memory: {mem_err}")

            self.save_artifact(
                task_id,
                "RAW_OUTPUT",
                response,
                step_id=step_id,
                metadata={"kind": "endpoint_chat", "used_web": bool(web_context), "has_market_quote": bool(ticker_symbol)},
            )
            self.update_step_status(step_id, "COMPLETED", {"response_length": len(response)})
            logger.info(f"Endpoint task {task_id} completed.")
            market_quote_payload = quote if (ticker_symbol and quote.get("price")) else None
            return {
                "response": response,
                "model_used": model_id,
                "used_web": bool(web_context),
                "market_quote": market_quote_payload,
            }

        except Exception as e:
            self.update_step_status(step_id, "FAILED", {"error": str(e)})
            logger.error(f"Endpoint task {task_id} failed: {e}")
            return {"error": str(e)}

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.finance_tools.close()
        await self.link_manager.close()
