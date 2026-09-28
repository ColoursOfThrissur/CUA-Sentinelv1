import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple
from agents.base_agent import BaseAgent
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
    PROFILE_NAME = "endpoint"

    def __init__(self, model_manager, governance, config):
        super().__init__(model_manager, governance, config)
        self.finance_tools = FinanceTools()
        self.link_manager = LinkManager()
        self._search_tool_call_counts: Dict[str, int] = {}

    def _should_use_web(self, prompt: str, explicit: bool) -> bool:
        text = prompt.lower()
        # Strictly guard against web search triggering on 3D modeling instructions
        blender_3d_keywords = (
            "blender", "create_box", "create_cylinder", "create_sphere", "create_cone",
            "create_torus", "3d model", "build_spec", "primitive", "mesh",
            "subdivision", "cylinder", "sphere", "ground plane",
        )
        if any(kw in text for kw in blender_3d_keywords):
            return False
        return explicit or any(hint in text for hint in WEB_HINTS)

    def _extract_ticker_symbol(self, prompt: str) -> str:
        text = prompt.lower()
        has_finance_intent = any(
            w in text for w in (
                "stock", "price", "share", "quote", "ticker", "market", "crypto",
                "dividend", "invest", "trading", "worth", "valuation", "pe ratio"
            )
        )

        # Check explicit dollar sign tickers e.g. $AAPL, $NVDA, $BTC-USD
        dollar_match = re.search(r'\$([A-Z]{1,5}(-[A-Z]{3})?)\b', prompt)
        if dollar_match:
            return dollar_match.group(1)

        # Check explicit mapped keywords
        for key, symbol in FINANCE_TICKER_MAP.items():
            if re.search(rf'\b{re.escape(key)}\b', text):
                if has_finance_intent or key in ("bitcoin", "btc", "ethereum", "eth", "solana", "sol", "gold", "silver", "crude oil", "nifty", "sensex"):
                    return symbol

        # Only check all-caps tickers if explicit financial intent exists
        if has_finance_intent:
            match = re.search(r'\b[A-Z]{2,5}(-[A-Z]{3})?\b', prompt)
            if match:
                symbol = match.group(0)
                # Avoid common technical/general all-caps words
                if symbol not in ("AI", "UI", "UX", "API", "REST", "JSON", "HTML", "CSS", "UV", "MCP", "URL", "CUA", "LLM", "SQL", "POST", "GET"):
                    return symbol

    def _extract_file_update_intent(self, prompt: str, history: list) -> Optional[Tuple[str, str]]:
        """
        Detects requests to paste, insert, or write content into an existing desktop file
        (e.g., 'in the new txt file u created above can u paste the todays gmail first 10 messages').
        Returns (target_filename, content_intent_type) where content_intent_type is 'GMAIL', 'WEB', or 'TEXT'.
        """
        p_lower = prompt.lower()
        has_action = any(kw in p_lower for kw in ("paste", "insert", "append", "put", "write", "add", "save", "copy", "dump"))
        has_file_kw = any(kw in p_lower for kw in ("file", "txt", "md", "document"))
        has_in_or_to = any(kw in p_lower for kw in ("in ", "into ", "to "))

        if not (has_action and (has_file_kw or has_in_or_to)):
            return None

        desktop_dir = Path(os.environ.get("SENTINEL_DESKTOP_DIR", Path.home() / "Desktop")).resolve()
        target_filename = None

        # 1. Explicit filename in prompt (e.g. notes.txt or new_file.txt)
        fn_match = re.search(r'([A-Za-z0-9_\-]+\.(?:txt|md))', prompt, re.IGNORECASE)
        if fn_match:
            target_filename = fn_match.group(1)

        # 2. Check history for referenced file
        if not target_filename and history:
            for msg in reversed(history):
                content = str(msg.get("content", ""))
                hist_match = re.search(r'`([A-Za-z0-9_\-]+\.(?:txt|md))`', content, re.IGNORECASE)
                if hist_match:
                    target_filename = hist_match.group(1)
                    break
                hist_match2 = re.search(r'\b([A-Za-z0-9_\-]+\.(?:txt|md))\b', content, re.IGNORECASE)
                if hist_match2:
                    target_filename = hist_match2.group(1)
                    break

        # 3. Check existing files on Desktop created recently
        if not target_filename:
            candidates = ["new_file.txt", "new_txt_file.txt", "new_file.md"]
            for cand_name in candidates:
                if (desktop_dir / cand_name).exists():
                    target_filename = cand_name
                    break

        # 4. Fallback if prompt specifically refers to "file created above" or "new txt file"
        if not target_filename:
            if any(w in p_lower for w in ("above", "created", "new txt", "new file")):
                target_filename = "new_file.txt"
            else:
                return None

        # Determine content intent type
        if any(w in p_lower for w in ("gmail", "email", "inbox", "mail", "messages")):
            content_type = "GMAIL"
        elif any(w in p_lower for w in ("news", "web", "weather", "search")):
            content_type = "WEB"
        else:
            content_type = "TEXT"

        return target_filename, content_type


    async def run(self, claim) -> dict:
        task_id = claim.task_id
        lease_id = claim.lease_id
        lease_generation = claim.lease_generation
        payload = claim.input_payload

        prompt = payload.get("prompt", "")
        now_dt = datetime.now()
        current_date_str = now_dt.strftime("%A, %B %d, %Y")
        system_prompt = (
            f"<role>\n"
            f"You are CUA-Sentinel, an intelligent personal AI assistant and deterministic operations engine running locally on the user's PC.\n"
            f"Today's real-world date is {current_date_str}. The current year is {now_dt.year}.\n"
            f"</role>\n\n"
            f"<invariants>\n"
            f"1. When answering requests about current events, latest updates, or news, strictly anchor your response in {now_dt.year} using the fresh context provided. Never treat historical 1990s or old background info as current news.\n"
            f"2. Provide direct, accurate, and helpful answers to user requests. When context data is provided, use it directly without issuing unnecessary disclaimers or mentioning unrelated tools.\n"
            f"3. Never hallucinate 3D model geometry or tool execution outcomes; execute tools to observe real state.\n"
            f"</invariants>"
        )
        use_web = bool(payload.get("use_web"))

        if not prompt:
            return {"error": "No prompt provided"}

        model_id = self.model_manager.get_model_for_workflow("ENDPOINT")
        step_id = self.create_step(task_id, 0, "DIRECT_CHAT", "Direct chat response")
        self.update_step_status(step_id, "RUNNING")

        try:
            # Check for direct Desktop file creation request
            from agents.cua_agent import CUAAgent
            cua_file_intent = CUAAgent._extract_file_intent(self, prompt)
            if cua_file_intent:
                fname, fcontent = cua_file_intent
                await self.broadcast_step_trace(task_id, "DESKTOP_FILE_WRITE", "DesktopTool", "RUNNING", {"filename": fname})
                write_res = await self.execute_tool(
                    "desktop_file_write",
                    {"filename": fname, "content": fcontent},
                    task_id=task_id,
                    step_id=step_id,
                )
                write_data = write_res.get("data") or {}
                if write_res.get("status") == "ok" and write_data.get("status") == "SUCCESS":
                    await self.broadcast_step_trace(task_id, "DESKTOP_FILE_WRITE", "DesktopTool", "COMPLETED", write_data)
                    response = f"✅ Successfully created file `{fname}` on your Desktop at `{write_data.get('path')}` ({write_data.get('bytes_written', 0)} bytes written)."
                    self.save_artifact(
                        task_id,
                        "RAW_OUTPUT",
                        response,
                        step_id=step_id,
                        metadata={"file_created": write_data},
                    )
                    self.update_step_status(step_id, "COMPLETED", {"response_length": len(response)})
                    return {
                        "response": response,
                        "file_created": write_data,
                        "model_used": model_id,
                    }

            # Check for direct 3D build approval request
            approve_match = re.search(r"\b(?:save\s+as\s+approved|approve(?:\s+build|\s+spec|\s+model)?)\s+([a-f0-90-9]{4,16})\b", prompt, re.IGNORECASE)
            if approve_match:
                b_id = approve_match.group(1).lower()
                from core.spec3d.pipeline import Spec3DPipeline
                appr_res = await Spec3DPipeline.process_save_approved(b_id)
                if appr_res.get("ok"):
                    msg = (
                        f"✅ **3D Model Approved & Saved to Library!**\n\n"
                        f"- **Model**: `{appr_res.get('name')}`\n"
                        f"- **Category**: `{appr_res.get('category')}`\n"
                        f"- **Library File**: `{appr_res.get('saved_to')}`\n\n"
                        f"Future requests for this object will use this approved spec directly with zero latency."
                    )
                else:
                    msg = f"⚠️ Could not approve build `{b_id}`: {appr_res.get('error')}"
                self.save_artifact(task_id, "RAW_OUTPUT", msg, step_id=step_id)
                self.update_step_status(step_id, "COMPLETED")
                return {"response": msg, "model_used": model_id, "approved_build_id": b_id}

            # Check for direct Desktop file update / paste request (e.g. paste Gmail messages into created file)
            history = payload.get("history", [])
            file_update_intent = self._extract_file_update_intent(prompt, history)
            if file_update_intent:
                target_file, content_type = file_update_intent
                if content_type == "GMAIL":
                    from core.alert_manager import AlertManager
                    am = AlertManager()
                    e_user = am._get_setting("smtp_user")
                    e_pass = am._get_setting("smtp_app_password")
                    if not (e_user and e_pass):
                        response = f"⚠️ Cannot paste Gmail messages into `{target_file}`: Gmail SMTP / IMAP credentials are not configured in Settings."
                        self.save_artifact(task_id, "RAW_OUTPUT", response, step_id=step_id)
                        self.update_step_status(step_id, "COMPLETED", {"error": "no_credentials"})
                        return {"response": response, "model_used": model_id}

                    await self.broadcast_step_trace(task_id, "FETCH_GMAIL", "EmailEngine", "RUNNING", {"max_emails": 10})
                    gateway_mail = await self.execute_tool(
                        "fetch_recent_emails",
                        {"email_user": e_user, "app_password": e_pass, "max_emails": 10},
                        task_id=task_id,
                        step_id=step_id,
                    )
                    email_results = gateway_mail.get("data") or []
                    if not email_results:
                        gateway_mail = await self.execute_tool(
                            "search_emails",
                            {"email_user": e_user, "app_password": e_pass, "query": "", "search_term": "", "max_results": 10},
                            task_id=task_id,
                            step_id=step_id,
                        )
                        email_results = gateway_mail.get("data") or []

                    if not email_results:
                        response = f"⚠️ Connected to Gmail for `{e_user}`, but found no messages in the inbox to paste into `{target_file}`."
                        self.save_artifact(task_id, "RAW_OUTPUT", response, step_id=step_id)
                        self.update_step_status(step_id, "COMPLETED")
                        return {"response": response, "model_used": model_id}

                    export_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    file_lines = [
                        "=" * 60,
                        f"CUA-Sentinel: Gmail Inbox Export ({len(email_results)} Recent Messages)",
                        f"Account: {e_user}",
                        f"Exported At: {export_time}",
                        "=" * 60,
                        ""
                    ]
                    for idx, em in enumerate(email_results, start=1):
                        file_lines.append(f"[{idx}] Subject: {em.get('subject', 'No Subject')}")
                        file_lines.append(f"    From: {em.get('sender', 'Unknown')}")
                        file_lines.append(f"    Date: {em.get('date', '')}")
                        file_lines.append("    Snippet:")
                        snippet_text = em.get('snippet', '').strip()
                        file_lines.append(f"    {snippet_text}")
                        file_lines.append("-" * 60)

                    file_content = "\n".join(file_lines)

                    await self.broadcast_step_trace(task_id, "DESKTOP_FILE_WRITE", "DesktopTool", "RUNNING", {"filename": target_file, "overwrite": True})
                    write_res = await self.execute_tool(
                        "desktop_file_write",
                        {"filename": target_file, "content": file_content, "overwrite": True},
                        task_id=task_id,
                        step_id=step_id,
                    )
                    write_data = write_res.get("data") or {}
                    if write_res.get("status") == "ok" and write_data.get("status") == "SUCCESS":
                        await self.broadcast_step_trace(task_id, "DESKTOP_FILE_WRITE", "DesktopTool", "COMPLETED", write_data)
                        preview_items = []
                        for idx, em in enumerate(email_results[:10], start=1):
                            preview_items.append(f"{idx}. **{em.get('subject', 'No Subject')}**\n   - From: `{em.get('sender', 'Unknown')}`\n   - Date: {em.get('date', '')}")
                        preview_str = "\n".join(preview_items)
                        response = (
                            f"✅ Successfully pasted your **first {len(email_results)} Gmail messages** into `{target_file}` on your Desktop at `{write_data.get('path')}` ({write_data.get('bytes_written', 0)} bytes written).\n\n"
                            f"### 📬 Exported Messages:\n{preview_str}\n\n"
                            f"*(Full email details and snippets have been saved to `{target_file}` on your Desktop)*"
                        )
                        self.save_artifact(
                            task_id,
                            "RAW_OUTPUT",
                            response,
                            step_id=step_id,
                            metadata={"file_updated": write_data, "emails_count": len(email_results)},
                        )
                        self.update_step_status(step_id, "COMPLETED", {"response_length": len(response)})
                        return {
                            "response": response,
                            "file_updated": write_data,
                            "emails_count": len(email_results),
                            "model_used": model_id,
                        }

            facts_list = []
            extra_contexts = []

            # 0. Always load Financial Portfolio View when specified in profile (Turn 1 and subsequent turns)
            if self.profile and self.profile.get("view"):
                view_name = self.profile.get("view")
                try:
                    import core.finance_views as fv
                    if hasattr(fv, view_name):
                        view_fn = getattr(fv, view_name)
                        view_output = view_fn()
                        if isinstance(view_output, str) and view_output.strip():
                            facts_list.append(f"[FACTS | T1 Financial Portfolio View (Fresh)]\n{view_output}")
                        else:
                            facts_list.append("[FACTS | T1 Financial Portfolio View] Finance data unavailable or empty.")
                except Exception as e:
                    logger.warning(f"Could not load view '{view_name}': {e}")
                    facts_list.append("[FACTS | T1 Financial Portfolio View] Finance data unavailable due to read error.")

            # 0b. Background Autonomous Activity Digest (Tier 2 facts, never placed in system rules)
            try:
                from core.memory_layers import memory_layers
                recent_activity = memory_layers.get_recent_autonomous_activity_summary(hours=24)
                if recent_activity:
                    facts_list.append(f"[FACTS | T2 Autonomous Activity Digest (Past 24h)]\n{recent_activity}")
            except Exception as act_err:
                logger.debug(f"Could not load activity digest: {act_err}")

            # 0c. Prior Multi-Turn Conversation History
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
                    facts_list.append("[PRIOR CONVERSATION HISTORY]\n" + "\n".join(history_lines))

            # 0d. Recalled Capability Lessons (Self-Improvement Layer)
            try:
                from core.reflection import reflection_engine
                recalled_wisdom = reflection_engine.recall_lessons(prompt, top_k=2)
                if recalled_wisdom:
                    facts_list.append(f"[RECALLED CAPABILITY LESSONS]\n{recalled_wisdom}")
            except Exception as ref_err:
                logger.debug(f"Could not recall capability lessons: {ref_err}")

            # 1. Wire Financial Market Quotes & Ticker Lookup ONLY if symbol extracted
            ticker_symbol = self._extract_ticker_symbol(prompt)
            if ticker_symbol:
                symbol_to_fetch = ticker_symbol
                await self.broadcast_step_trace(task_id, "FETCH_MARKET_QUOTE", "FinanceTools", "RUNNING", {"symbol": symbol_to_fetch})
                gateway_quote = await self.execute_tool(
                    "fetch_ticker_quote",
                    {"symbol": symbol_to_fetch},
                    task_id=task_id,
                    step_id=step_id,
                    tool_instance=self.finance_tools,
                )
                quote = gateway_quote.get("data") or {}
                price_val = quote.get("price")
                if price_val is not None:
                    try:
                        price_str = f"${float(price_val):,.2f}"
                    except (ValueError, TypeError):
                        price_str = str(price_val)
                    change_pct = quote.get("change_24h_pct")
                    change_str = f"{float(change_pct):+.2f}%" if isinstance(change_pct, (int, float)) else "N/A"
                    extra_contexts.append(
                        f"[LIVE MARKET TICKER DATA]\nSymbol: {quote.get('symbol', symbol_to_fetch)}\nName: {quote.get('name', symbol_to_fetch)}\nCurrent Price: {price_str} {quote.get('currency', 'USD')}\n24h Change: {change_str}\nTimestamp: {quote.get('timestamp', '')}"
                    )
                    await self.broadcast_step_trace(task_id, "FETCH_MARKET_QUOTE", "FinanceTools", "COMPLETED", {"symbol": quote.get('symbol', symbol_to_fetch), "price": price_str})

            # 2. Wire Web Search Enrichment if requested or detected
            web_context = ""
            if self._should_use_web(prompt, use_web):
                self.update_step_status(step_id, "RUNNING", {"web_context": "fetching"})
                await self.broadcast_step_trace(task_id, "WEB_SEARCH", "WebSearchTool", "RUNNING", {"query": prompt})
                gateway_search = await self.execute_tool(
                    "web_search",
                    {"query": prompt, "max_results": 4},
                    task_id=task_id,
                    step_id=step_id,
                )
                web_context = gateway_search.get("data") or ""
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
                    am = AlertManager()
                    e_user = am._get_setting("smtp_user")
                    e_pass = am._get_setting("smtp_app_password")
                    if e_user and e_pass:
                        await self.broadcast_step_trace(task_id, "FETCH_GMAIL_CONTEXT", "EmailEngine", "RUNNING", {"query": prompt})
                        is_recent = any(w in prompt.lower() for w in ("recent", "first", "today", "inbox", "last", "latest", "unread"))
                        if is_recent:
                            gateway_mail = await self.execute_tool(
                                "fetch_recent_emails",
                                {"email_user": e_user, "app_password": e_pass, "max_emails": 10},
                                task_id=task_id,
                                step_id=step_id,
                            )
                            email_results = gateway_mail.get("data") or []
                            if not email_results:
                                gateway_mail = await self.execute_tool(
                                    "search_emails",
                                    {"email_user": e_user, "app_password": e_pass, "query": prompt, "search_term": prompt, "max_results": 10},
                                    task_id=task_id,
                                    step_id=step_id,
                                )
                                email_results = gateway_mail.get("data") or []
                        else:
                            gateway_mail = await self.execute_tool(
                                "search_emails",
                                {"email_user": e_user, "app_password": e_pass, "query": prompt, "search_term": prompt, "max_results": 10},
                                task_id=task_id,
                                step_id=step_id,
                            )
                            email_results = gateway_mail.get("data") or []
                            if not email_results:
                                gateway_mail = await self.execute_tool(
                                    "fetch_recent_emails",
                                    {"email_user": e_user, "app_password": e_pass, "max_emails": 10},
                                    task_id=task_id,
                                    step_id=step_id,
                                )
                                email_results = gateway_mail.get("data") or []

                        if email_results:
                            mail_blocks = [f"From: {m['sender']}\nDate: {m['date']}\nSubject: {m['subject']}\nEmail Body:\n{m['snippet']}" for m in email_results]
                            extra_contexts.append("[GMAIL INBOX SEARCH CONTEXT]\n" + "\n---\n".join(mail_blocks))
                            facts_list.append(f"[FACTS | GMAIL INBOX ({len(email_results)} messages)]\n" + "\n---\n".join(mail_blocks))
                            await self.broadcast_step_trace(task_id, "FETCH_GMAIL_CONTEXT", "EmailEngine", "COMPLETED", {"matches_found": len(email_results)})
                except Exception as mail_err:
                    logger.warning(f"Error fetching Gmail context: {mail_err}")

            # Dynamic Tool Routing for 12GB VRAM System Prompt Optimization
            tool_context = ToolRegistry.get_relevant_capabilities_prompt(prompt, max_tools=2)
            active_system_prompt = f"{system_prompt}\n\n{tool_context}"

            # MCP Connected Applications Tool Injection
            # MCP Connected Applications Tool Injection with Intent Routing & Compact Formatting
            mcp_mgr = getattr(self, "_mcp_manager", None)
            target_app = payload.get("target_app")
            mcp_tool_lines = []
            if mcp_mgr:
                connected_ids = mcp_mgr.list_connected_app_ids()
                discovery_mode = os.getenv("TOOL_DISCOVERY_MODE", "hybrid").lower()

                # In search or hybrid mode, expose search_tools discovery meta-tool
                if connected_ids and discovery_mode in ("search", "hybrid"):
                    mcp_tool_lines.append(
                        "- `search_tools`: Dynamic Tool Retrieval. Search all connected MCP servers (filesystem, github, postgres, slack, etc.) for specialized tools by intent query (args: query: str, limit: int opt). Call this whenever you need capabilities not surfaced below."
                    )

                # Determine relevant apps based on explicit target, discovery mode, or prompt keywords
                if target_app and target_app in connected_ids:
                    app_ids = [target_app]
                elif discovery_mode == "search":
                    # In pure search mode, do not inject keyword-matched apps up-front (progressive disclosure)
                    prompt_lower = prompt.lower()
                    app_ids = ["blender"] if ("blender" in connected_ids and any(k in prompt_lower for k in ("3d", "mesh", "blender", "model"))) else []
                else:
                    # Hybrid or keyword mode: evaluate keyword routing
                    prompt_lower = prompt.lower()
                    recent_history_text = " ".join(
                        str(m.get("content", "")) for m in (payload.get("history") or [])[-4:]
                    ).lower()
                    full_context_text = f"{prompt_lower} {recent_history_text}"

                    matched_apps = []
                    app_keywords = {
                        "blender": ["blender", "3d", "sphere", "spheres", "cube", "cubes", "cylinder", "cylinders", "cone", "cones", "torus", "mesh", "meshes", "bpy", "render", "viewport", "vertex", "vertices", "material", "primitive", "extrude", "bevel", "subdivision", "subsurf", "boolean", "mcp:blender:", "model", "modeling", "dog", "cat", "car", "character", "animal", "cup", "mug", "table", "chair", "robot", "vehicle", "house", "tree", "arcade", "cabinet", "machine", "kiosk", "vending"],
                        "filesystem": ["file", "files", "directory", "directories", "folder", "folders", "path", "desktop", "read_file", "write_file", "list_dir", "mcp:filesystem:"],
                        "github": ["github", "repo", "repository", "issue", "issues", "pull request", "pr", "commit", "branch", "fork", "mcp:github:"],
                        "postgres": ["postgres", "postgresql", "sql", "table", "schema", "query", "database", "mcp:postgres:"],
                        "slack": ["slack", "channel", "slack message", "mcp:slack:"],
                    }

                    for aid in connected_ids:
                        kw_list = app_keywords.get(aid, [aid])
                        if any(kw in full_context_text for kw in kw_list):
                            matched_apps.append(aid)

                    app_ids = matched_apps

                allowed_profile_tools = set(self.profile.get("tools_allowed", [])) if self.profile else set()
                if app_ids:
                    for aid in app_ids:
                        if aid == "blender":
                            # Only expose build_spec - all 3D generation goes through staged pipeline
                            mcp_tool_lines.append("- `blender:build_spec`: Build ANY 3D object from natural language. Describe what you want (e.g. 'a communication tower with radar dish and support struts', 'a training dummy', 'an arcade cabinet'). The pipeline handles all geometry, positioning, and materials automatically. (args: description: str)")
                            mcp_tool_lines.append("- `blender:get_manifest`: List all objects currently in the Blender scene (args: none)")

                        app_tools = mcp_mgr.get_tools_for_app(aid)
                        # Prioritize key execution and creation tools
                        def _tool_priority(t):
                            tname = t.name.lower()
                            if "execute" in tname or "code" in tname or "run" in tname:
                                return 0
                            if "create" in tname or "add" in tname:
                                return 1
                            if "read" in tname or "get" in tname or "list" in tname:
                                return 2
                            return 3

                        sorted_tools = sorted(app_tools, key=_tool_priority)
                        # Filter to only tools explicitly permitted in agent profile
                        for t in sorted_tools[:15]:
                            if t.name == "execute_blender_code":
                                continue  # internal locked execution, use typed operations
                            tool_fullname = f"mcp:{aid}:{t.name}"
                            
                            def _profile_allows(name, allowed):
                                if name in allowed:
                                    return True
                                for pattern in allowed:
                                    if '*' in pattern:
                                        if name.startswith(pattern.replace('*', '')):
                                            return True
                                return False

                            if not _profile_allows(tool_fullname, allowed_profile_tools) and not _profile_allows(aid, allowed_profile_tools):
                                continue

                            props = t.input_schema.get("properties", {}) if isinstance(t.input_schema, dict) else {}
                            req = t.input_schema.get("required", []) if isinstance(t.input_schema, dict) else []
                            params_desc = []
                            for k, v in list(props.items())[:5]:
                                ptype = v.get("type", "any") if isinstance(v, dict) else "any"
                                is_req = "req" if k in req else "opt"
                                params_desc.append(f"{k}: {ptype} ({is_req})")
                            params_str = ", ".join(params_desc) if params_desc else "none"
                            desc = (t.description or "").split("\n")[0].strip()
                            if len(desc) > 100:
                                desc = desc[:97] + "..."
                            mcp_tool_lines.append(f"- `{tool_fullname}`: {desc} (args: {params_str})")

            if mcp_tool_lines:
                mcp_block = (
                    "\n\n<connected_tools>\n"
                    "You have direct execution access to the following connected application tools:\n"
                    + "\n".join(mcp_tool_lines)
                    + "\n</connected_tools>\n\n"
                    "<action_guidance>\n"
                    "- When the user asks you to create, model, build, or manipulate 3D objects, DO NOT provide generic text or outside software recommendations.\n"
                    "- NEVER respond to a build/create request with 'blender:get_manifest'. get_manifest is read-only inspection. It does not build anything.\n"
                    "- For organic animals/creatures, characters, figurines, complete objects/furniture/vessels, OR complex multi-part assemblies (arcade machines, vending machines, ATMs, kiosks, control panels, etc.) with no explicit dimensions, USE 'blender:build_spec' as the primary tool. The pipeline plans, verifies geometry, generates PBR materials, smooths shading, configures studio lighting, and loads the model into Blender automatically.\n"
                    "- CRITICAL: 'blender:build_spec' is an ALL-IN-ONE pipeline that builds the ENTIRE object from a SINGLE description. Pass the COMPLETE user request as the description argument. DO NOT split the object into multiple build_spec calls. DO NOT follow build_spec with primitive tools. ONE build_spec call = ONE complete object.\n"
                    "- Use primitive composition tools ('blender:create_box', 'blender:create_cylinder', 'blender:set_material', etc.) when: (a) the user provides exact numeric dimensions, (b) 'blender:build_spec' previously failed or returned an error, or (c) the user explicitly asks for step-by-step primitive construction. In these cases, generate a full multi-step plan with all primitives, booleans, materials, and camera/light.\n"
                    "\n"
                    "PLANNING A COMPLEX MODEL (primitive composition)\n"
                    "- Before writing any tool calls, mentally decompose the object into named parts. Identify: (1) the structural base/body, (2) secondary components that attach to it, (3) detail parts (handles, knobs, caps, feet), (4) any hollow cavities or cutouts.\n"
                    "- Establish a single consistent unit scale for the whole model (e.g. 1 unit = 1 cm). All parts must use the same scale.\n"
                    "- Build order: create structural/base parts first, then attach secondary parts, then apply booleans (DIFFERENCE/UNION), then apply materials, then smooth shading, then camera and light last.\n"
                    "- Boolean operations require BOTH target objects to already exist in the scene. Always create the cutter/inner object before calling apply_boolean.\n"
                    "- Use clear, descriptive names for every object (e.g. 'body', 'lid', 'handle_left', 'leg_front_left'). Boolean cutters should be named with a '_cutter' suffix so they are identifiable before deletion.\n"
                    "- For a fresh build, start with 'blender:clear_scene' (keep_camera_and_lights: false) to avoid leftover objects from previous builds.\n"
                    "\n"
                    "SPATIAL POSITIONING\n"
                    "- Every primitive's origin is at its geometric center. Always compute positions from center, not from edges or faces.\n"
                    "- Stacking (vertical): B_center_z = A_center_z + A_half + B_half, where half = depth/2 for cylinders/boxes, radius for spheres.\n"
                    "- Side-by-side (horizontal): B_center_x = A_center_x ± (A_half + B_half). Same principle applies on Y-axis.\n"
                    "- Chain rule: each successive part's center = previous_center ± previous_half + current_half. Apply repeatedly for multi-part chains.\n"
                    "- Sphere half-extent = radius in all directions. Box half-extent = size/2 per axis. Cone base is at center_z - depth/2, tip at center_z + depth/2.\n"
                    "- Torus center is its geometric center; major_radius is the ring radius, minor_radius is the tube thickness. Torus lies flat (XY plane) by default.\n"
                    "- Always pre-compute all positions as plain evaluated numbers before writing JSON. NEVER write arithmetic expressions inside JSON values.\n"
                    "\n"
                    "SYMMETRY\n"
                    "- For mirrored pairs (left/right legs, handles, wheels, ears), compute one side's center then negate the relevant axis for the other: right_x = +offset, left_x = -offset.\n"
                    "- For radially symmetric parts (e.g. 4 legs of a table), place them at ±offset on both X and Y axes.\n"
                    "\n"
                    "HOLLOW OBJECTS\n"
                    "- To hollow any vessel: create outer primitive, then create inner primitive (the cavity), then apply boolean DIFFERENCE on the outer using the inner as target.\n"
                    "- inner_radius = outer_radius - wall_thickness.\n"
                    "- Flat-bottomed open vessel (cup, pot, vase): inner_depth = outer_depth - wall_thickness. inner_center_z = outer_center_z + wall_thickness/2. inner cutter top = outer_center_z + inner_depth/2 = outer_top - wall_thickness/2 (flush with inner wall, NOT past the rim). To guarantee the boolean cuts cleanly through the open face, extend the cutter 0.1 past the outer rim: inner_depth += 0.1, inner_center_z += 0.05.\n"
                    "- Fully closed vessel: inner_depth = outer_depth - 2*wall_thickness. inner_center_z = outer_center_z.\n"
                    "- Example (outer_r=5, outer_depth=20, wall=0.3, outer_center_z=0): inner_r=4.7, inner_depth=19.8, inner_center_z=0.2. (inner_depth = 20-0.3+0.1=19.8, inner_center_z = 0+0.3/2+0.05=0.2)\n"
                    "- NEVER place inner_center_z = outer_center_z for a flat-bottomed vessel.\n"
                    "- Set delete_target: true in apply_boolean to remove the cutter after the operation.\n"
                    "\n"
                    "ROD / SHAFT / INSERT INSIDE A VESSEL\n"
                    "- Any part that slides inside a cavity must have radius < cavity_inner_radius. Use clearance = 0.2 unless specified: insert_radius = inner_cavity_radius - 0.2.\n"
                    "- 'N units above the bottom': part_center_z = (vessel_center_z - vessel_depth/2) + N + part_depth/2.\n"
                    "- Example (vessel_center_z=0, vessel_depth=20, N=5, plate_depth=0.2): plate_center_z = (0-10)+5+0.1 = -4.9.\n"
                    "- Rod flush with vessel top: rod_center_z = vessel_center_z + vessel_depth/2 - rod_depth/2.\n"
                    "- Example (vessel_center_z=0, vessel_depth=20, rod_depth=22): rod_center_z = 0+10-11 = -1.\n"
                    "- Plate at rod bottom tip: plate_center_z = rod_center_z - rod_depth/2 + plate_depth/2.\n"
                    "- Applies to: press plungers, pistons, syringes, pestles, stoppers, caps that fit inside a tube.\n"
                    "\n"
                    "ORIENTATION\n"
                    "- Cylinders are vertical (Z-axis) by default. Leave rotation [0,0,0] for upright columns, rods, tubes, legs, bottles.\n"
                    "- Horizontal along X-axis (bar, axle, handle, rolling pin): rotation [0,90,0].\n"
                    "- Horizontal along Y-axis: rotation [90,0,0].\n"
                    "- Cones point upward by default (tip at +Z). To make a downward-pointing cone (funnel, spike): rotation [180,0,0].\n"
                    "- Torus lies flat (XY plane) by default. To stand it upright like a wheel: rotation [90,0,0].\n"
                    "\n"
                    "SHAPING & DETAIL\n"
                    "- Use 'blender:apply_bevel' on sharp-edged parts to add realistic edge rounding (width = 5-10% of the part's smallest dimension, segments=2-3).\n"
                    "- Use 'blender:apply_subdivision' (levels 1-2) on any part that should appear smooth or organic rather than faceted.\n"
                    "- Use 'blender:set_smooth_shading' after subdivision to eliminate visible polygon edges.\n"
                    "- Use 'blender:apply_boolean' UNION to fuse two parts into one solid mesh when they should appear seamless.\n"
                    "- Use 'blender:join_objects' to merge finished parts into a single object for export or simplicity.\n"
                    "\n"
                    "MATERIALS\n"
                    "- Call 'blender:set_material' for every mesh. Identify the real-world material of each part, then set PBR values accordingly.\n"
                    "- metallic=1.0 for all metals; metallic=0 for all non-metals.\n"
                    "- roughness by surface finish: mirror/polished=0.0-0.05, glossy=0.1, brushed=0.3-0.4, bare industrial=0.3, painted=0.15-0.2, matte=0.6-0.7, rough/cast=0.7-0.9, rubber=0.9.\n"
                    "- color: match the real-world appearance of the part. Use neutral grey [0.5,0.5,0.5,1] only when the object has no defined color. For user-specified colors, convert the color name to an approximate [r,g,b,1] value.\n"
                    "- Transparent/glass parts: color=[0.8,0.95,1.0,alpha], metallic=0, roughness=0.0. Alpha must be ≤0.2 for visible transparency. Frosted glass: roughness=0.15, alpha=0.4.\n"
                    "- Emissive parts (screens, LEDs, neon): add emission_color=[r,g,b] to set_material.\n"
                    "\n"
                    "CAMERA & LIGHTING\n"
                    "- Every build plan MUST end with 'blender:create_light' and 'blender:create_camera', unless the scene already has them.\n"
                    "- Camera distance = 3x the object's largest dimension. Place at roughly equal X and -Y offset, elevated 30-45 degrees above horizon for a 3/4 view.\n"
                    "- Camera rotation for a 3/4 view: rotation=[65, 0, 45]. Do NOT use rotation=[0,90,0] (top-down). Do NOT use rotation=[90,0,0] (flat front view).\n"
                    "- For small objects (< 10 units): POINT light, energy 200-500. Medium (10-50 units): POINT or SUN, energy 500-2000. Large/architectural: SUN light.\n"
                    "- Place the light above and to one side, not directly overhead, to create shadow and depth.\n"
                    "\n"
                    "- To execute a single tool:\n"
                    "```json\n"
                    '{"action": "call_tool", "tool": "<tool_name>", "args": { ... }}\n'
                    "```\n"
                    "- To execute a multi-step plan:\n"
                    "```json\n"
                    '{"action": "plan", "steps": [{"tool": "<tool_name>", "args": { ... }}, ...]}\n'
                    "```\n"
                    "</action_guidance>"
                )
                max_rules_allowed = int(claim.context_budget * 3.8) - len(prompt) - 1000
                if len(active_system_prompt) + len(mcp_block) <= max_rules_allowed:
                    active_system_prompt += mcp_block
                else:
                    logger.warning(
                        f"[task={task_id}] MCP tool block exceeds safe context budget "
                        f"({len(active_system_prompt) + len(mcp_block)} > {max_rules_allowed}); "
                        f"using concise tool injection."
                    )
                    # Degraded fallback: still name the highest-value tools by name,
                    # even without full schemas, so the model isn't left guessing
                    # tool names from scratch. Losing schemas is acceptable; losing
                    # every tool name is not — that's what caused a 3D build request
                    # to silently fall back to a bare read-only manifest check.
                    concise_lines = []
                    if "blender" in connected_ids:
                        concise_lines.append(
                            '- `blender:build_spec`: build ANY 3D object from a natural-language '
                            'description (args: description: str). Use this for ANY create/build/model request.'
                        )
                        concise_lines.append(
                            '- `blender:get_manifest`: read-only, lists existing scene objects. '
                            'Do NOT use this to fulfill a build/create request.'
                        )
                    active_system_prompt += (
                        "\n\n[CONNECTED APPLICATION TOOLS — CONCISE MODE]\n"
                        "Connected apps available: " + ", ".join(connected_ids) + ".\n"
                        + ("\n".join(concise_lines) + "\n" if concise_lines else "")
                        + "To execute an application tool, respond with: "
                        '{"action": "call_tool", "tool": "<tool_name>", "args": { ... }}\n'
                    )

            # P0.2: Wrap all untrusted context in sealed envelopes
            from core.sealed_envelope import build_sealed_envelope
            untrusted_blocks = []
            trusted_facts = list(facts_list)

            for ctx in extra_contexts:
                # Market ticker data is untrusted (from external API)
                if ctx.startswith("[LIVE MARKET TICKER DATA]"):
                    untrusted_blocks.append(
                        build_sealed_envelope(ctx, origin="api:yahoo-finance")
                    )
                # Web search context is untrusted
                elif ctx.startswith("[WEB SEARCH CONTEXT]"):
                    untrusted_blocks.append(
                        build_sealed_envelope(ctx, origin="web:search-results")
                    )
                # Gmail context is untrusted
                elif ctx.startswith("[GMAIL INBOX"):
                    untrusted_blocks.append(
                        build_sealed_envelope(ctx, origin="email:gmail-inbox")
                    )
                else:
                    # Default: treat unknown context as untrusted
                    untrusted_blocks.append(
                        build_sealed_envelope(ctx, origin="unknown")
                    )

            # JSON extraction helpers — defined here so they are available for both
            # the prompt pre-scan below AND the response parsing after call_llm.
            def _try_parse_tool_json(json_str: str) -> Optional[dict]:
                if not json_str:
                    return None
                try:
                    return json.loads(json_str)
                except Exception:
                    pass

                # Sanitize arithmetic expressions inside JSON arrays or property values:
                # e.g. [-15 - (12/2), 0, 0] or [15 + (12/2) + (5/2), 0, 0] or 15 + 2/2
                try:
                    import ast

                    def _eval_ast_node(node):
                        if isinstance(node, ast.Expression):
                            return _eval_ast_node(node.body)
                        elif isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
                            return float(node.value)
                        elif isinstance(node, ast.UnaryOp):
                            operand = _eval_ast_node(node.operand)
                            if isinstance(node.op, ast.USub):
                                return -operand
                            elif isinstance(node.op, ast.UAdd):
                                return +operand
                            raise ValueError("Unsupported unary operator")
                        elif isinstance(node, ast.BinOp):
                            left = _eval_ast_node(node.left)
                            right = _eval_ast_node(node.right)
                            if isinstance(node.op, ast.Add):
                                return left + right
                            elif isinstance(node.op, ast.Sub):
                                return left - right
                            elif isinstance(node.op, ast.Mult):
                                return left * right
                            elif isinstance(node.op, ast.Div):
                                if right == 0:
                                    raise ZeroDivisionError("division by zero")
                                return left / right
                            raise ValueError("Unsupported binary operator")
                        raise ValueError(f"Disallowed AST node: {type(node)}")

                    def _safe_eval_math(expr_str: str) -> float:
                        if not re.match(r"^[\s0-9\.\+\-\*\/\(\)]+$", expr_str):
                            raise ValueError(f"Unsafe expression: {expr_str}")
                        tree = ast.parse(expr_str, mode='eval')
                        return float(_eval_ast_node(tree))

                    def _replace_math(match):
                        prefix = match.group(1)
                        expr = match.group(2).strip()
                        suffix = match.group(3)
                        if re.match(r'^-?\d+(?:\.\d+)?$', expr) or expr in ('true', 'false', 'null', '""'):
                            return match.group(0)
                        try:
                            val = _safe_eval_math(expr)
                            return f"{prefix} {round(val, 4)}{suffix}"
                        except Exception:
                            return match.group(0)

                    pattern = r'([\[,:]\s*)([\s0-9\.\+\-\*\/\(\)]*[\+\-\*\/][\s0-9\.\+\-\*\/\(\)]*?)(\s*[,\]\}])'
                    cleaned = json_str
                    for _ in range(5):
                        prev = cleaned
                        cleaned = re.sub(pattern, _replace_math, cleaned)
                        if cleaned == prev:
                            break

                    return json.loads(cleaned)
                except Exception:
                    pass
                return None

            def _extract_outer_json_object(text: str) -> Optional[str]:
                for trigger in ('"action": "plan"', '"action":"plan"', '"action": "call_tool"', '"action":"call_tool"', '"steps":', '"actions":'):
                    idx = text.find(trigger)
                    if idx != -1:
                        start = text.rfind('{', 0, idx)
                        if start == -1:
                            start = idx
                        depth = 0
                        in_string = False
                        escape = False
                        for i in range(start, len(text)):
                            char = text[i]
                            if escape:
                                escape = False
                                continue
                            if char == '\\':
                                escape = True
                                continue
                            if char == '"':
                                in_string = not in_string
                                continue
                            if not in_string:
                                if char == '{':
                                    depth += 1
                                elif char == '}':
                                    depth -= 1
                                    if depth == 0:
                                        return text[start:i+1]
                return None

            # Short-circuit: if the prompt itself contains a ready-to-execute plan
            # (user pasted a JSON plan directly into chat), extract and run it immediately
            # without burning an LLM turn. This handles the case where the UI renders
            # the plan JSON and the user re-submits it.
            _prompt_plan_steps: list = []
            _prompt_json_raw = _extract_outer_json_object(prompt)
            if _prompt_json_raw:
                _prompt_obj = _try_parse_tool_json(_prompt_json_raw)
                if _prompt_obj and (_prompt_obj.get("steps") or _prompt_obj.get("actions")):
                    for _s in (_prompt_obj.get("steps") or _prompt_obj.get("actions") or []):
                        if isinstance(_s, dict) and _s.get("tool"):
                            _prompt_plan_steps.append((_s["tool"], _s.get("args") or {}))

            # P0.2: Use call_llm for fixed-order prompt assembly
            try:
                response = await self.call_llm(
                    task_id=task_id,
                    system_rules=active_system_prompt,
                    task_prompt=f"{prompt}\n\nAnswer the user's request directly using any relevant context provided above.",
                    facts=trusted_facts if trusted_facts else None,
                    untrusted_blocks=untrusted_blocks if untrusted_blocks else None,
                    model_id=model_id,
                    lease_id=lease_id,
                    lease_generation=lease_generation,
                    context_budget=claim.context_budget,
                    temperature=0.7,
                )
            except Exception as e:
                logger.error(f"EndpointAgent LLM generation failed: {e}")
                return {
                    "response": f"⚠️ **AI Service Offline or Busy**\n\nCould not generate response ({e}). Please ensure Ollama is running (`ollama serve`).",
                    "model_used": model_id,
                }

            # Extract executable steps from LLM response
            steps_to_execute = []

            # 1. Check for batch/plan action: {"action": "plan", "steps": [...]} in markdown code blocks
            plan_match = re.search(r'```(?:json)?\s*(\{[\s\S]*?"(?:steps|actions)"\s*:\s*\[[\s\S]*?\][\s\S]*?\})\s*```', response)
            if plan_match:
                plan_obj = _try_parse_tool_json(plan_match.group(1))
                if plan_obj:
                    for s in (plan_obj.get("steps") or plan_obj.get("actions") or []):
                        if isinstance(s, dict) and s.get("tool"):
                            steps_to_execute.append((s.get("tool"), s.get("args") or {}))

            # 2. Check for single or multiple call_tool blocks in markdown code blocks
            if not steps_to_execute:
                for m in re.finditer(r'```(?:json)?\s*(\{[\s\S]*?"action"\s*:\s*"call_tool"[\s\S]*?\})\s*```', response):
                    single_obj = _try_parse_tool_json(m.group(1))
                    if single_obj and single_obj.get("tool"):
                        steps_to_execute.append((single_obj.get("tool"), single_obj.get("args") or {}))

            # 3. Check for bare JSON blocks anywhere in response with balanced bracket parsing
            if not steps_to_execute:
                raw_extracted = _extract_outer_json_object(response)
                if raw_extracted:
                    obj = _try_parse_tool_json(raw_extracted)
                    if obj:
                        if obj.get("steps") or obj.get("actions"):
                            for s in (obj.get("steps") or obj.get("actions") or []):
                                if isinstance(s, dict) and s.get("tool"):
                                    steps_to_execute.append((s.get("tool"), s.get("args") or {}))
                        elif obj.get("tool"):
                            steps_to_execute.append((obj.get("tool"), obj.get("args") or {}))

            # 4. If the LLM produced nothing executable but the prompt itself contained
            # a valid plan (user pasted JSON directly), use that as the execution plan.
            if not steps_to_execute and _prompt_plan_steps:
                steps_to_execute = _prompt_plan_steps
                logger.info(f"[task={task_id}] Executing plan extracted directly from prompt ({len(steps_to_execute)} steps)")

            # Route multi-part primitive composition through staged pipeline.
            # When LLM emits primitives instead of build_spec, re-route through
            # our new staged pipeline which has correct socket resolution.
            _is_primitive_plan = (
                steps_to_execute
                and any(t.startswith("blender:create_") for t, _ in steps_to_execute)
                and not any(t == "blender:build_spec" for t, _ in steps_to_execute)
            )
            if _is_primitive_plan:
                try:
                    from core.blender_pipeline.executor import run_staged_pipeline_and_execute
                    mcp_mgr = getattr(self, "_mcp_manager", None)
                    logger.info(f"[task={task_id}] Re-routing primitive plan through staged pipeline")
                    _staged_result = await run_staged_pipeline_and_execute(
                        description=prompt,
                        mcp_manager=mcp_mgr,
                        model_manager=self.model_manager,
                        task_id=task_id,
                    )
                    if _staged_result.get("ok"):
                        # Staged pipeline executed successfully - clear steps_to_execute
                        # so we don't double-execute, and record the result
                        executed_tool_results.append(("blender:build_spec", {"data": _staged_result}))
                        executed_summaries.append(
                            f"✅ `blender:build_spec`: Built {_staged_result.get('parts_count', '?')} parts, "
                            f"status={_staged_result.get('status', 'OK')}"
                        )
                        steps_to_execute = []  # Clear - already executed via staged pipeline
                        logger.info(
                            f"[task={task_id}] Staged pipeline succeeded: "
                            f"{_staged_result.get('executed_steps')} steps executed"
                        )
                    else:
                        logger.warning(
                            f"[task={task_id}] Staged pipeline failed: {_staged_result.get('error')}, "
                            f"falling back to direct primitive execution"
                        )
                        # Fall through to execute primitives directly
                except Exception as _sp_err:
                    logger.warning(
                        f"[task={task_id}] Staged pipeline error ({_sp_err}), "
                        f"falling back to direct primitive execution"
                    )

            # Execute extracted steps
            if steps_to_execute:
                allowed_tools = set(self.profile.get("tools_allowed", [])) if self.profile else set()
                executed_summaries = []
                executed_tool_results = []
                total_steps = len(steps_to_execute)
                for step_idx, (tool_to_call, call_args) in enumerate(steps_to_execute, start=1):
                    import uuid as _uuid
                    step_span_id = f"span_{_uuid.uuid4().hex[:12]}"
                    part_name = call_args.get("name", "")
                    step_label = f"STEP_{step_idx}_OF_{total_steps}" + (f"_{part_name}" if part_name else "")
                    try:
                        # Short-circuit: if this is a raw mcp:app:tool call, check the
                    # lockfile's allowed_agents before even attempting execution.
                        if tool_to_call.startswith("mcp:"):
                            _parts = tool_to_call.split(":", 2)
                            if len(_parts) == 3:
                                _app_id, _tool_name = _parts[1], _parts[2]
                                _locked_meta = mcp_mgr.get_locked_tool_meta(_app_id, _tool_name) if mcp_mgr else None
                                if _locked_meta:
                                    _lock_allowed = _locked_meta.get("allowed_agents")
                                    if isinstance(_lock_allowed, list) and "endpoint_agent" not in _lock_allowed:
                                        executed_summaries.append(
                                            f"⚠️ `{tool_to_call}` is restricted to {_lock_allowed} and not available to this agent."
                                        )
                                        continue

                        is_allowed = (
                            tool_to_call in allowed_tools
                            or any(tool_to_call.startswith(f"mcp:{p}") for p in allowed_tools)
                            or any(tool_to_call.startswith(f"{p}:") for p in allowed_tools)
                            or (tool_to_call.startswith("blender:") and "blender" in allowed_tools)
                            or (tool_to_call.startswith("mcp:blender:") and "blender" in allowed_tools)
                            or any('*' in p and tool_to_call.startswith(p.replace('*', '')) for p in allowed_tools)
                        )
                        if is_allowed:
                            # Enforce hard loop ceiling for search_tools (max 2 calls per task)
                            if tool_to_call == "search_tools":
                                current_searches = self._search_tool_call_counts.get(task_id, 0)
                                if current_searches >= 2:
                                    logger.warning(f"Task {task_id} exceeded search_tools ceiling (max 2 per task). Blocking call.")
                                    executed_summaries.append("⚠️ `search_tools`: Search call limit reached (max 2 per task).")
                                    continue
                                self._search_tool_call_counts[task_id] = current_searches + 1

                            await self.broadcast_step_trace(task_id, step_label, tool_to_call, "RUNNING", call_args, span_id=step_span_id)
                            tool_res = await self.execute_tool(tool_to_call, call_args, task_id=task_id, step_id=step_id)
                            await self.broadcast_step_trace(task_id, step_label, tool_to_call, tool_res.get("status", "ok").upper(), tool_res, span_id=step_span_id)
                            executed_tool_results.append((tool_to_call, tool_res))
                            res_data = tool_res.get("data")
                            if tool_res.get("status") == "ok":
                                if isinstance(res_data, dict):
                                    if res_data.get("ok") is False:
                                        err_msg = res_data.get("error") or res_data.get("reason") or "Operation failed"
                                        executed_summaries.append(f"⚠️ `{tool_to_call}` failed: {err_msg}")
                                    elif "formatted_schemas" in res_data and "found" in res_data:
                                        found_n = res_data.get("found", 0)
                                        found_tools = ", ".join(res_data.get("tools", [])) or "none"
                                        executed_summaries.append(f"✅ `search_tools`: Found {found_n} tool(s): {found_tools}")
                                    elif "output" in res_data:
                                        out_preview = str(res_data["output"]).strip().replace("\n", " ")[:80]
                                        executed_summaries.append(f"✅ `{tool_to_call}`: {out_preview}")
                                    else:
                                        executed_summaries.append(f"✅ `{tool_to_call}`: {res_data.get('action', res_data.get('status', 'OK'))} {res_data.get('model_name', res_data.get('name', ''))}")
                                else:
                                    executed_summaries.append(f"✅ `{tool_to_call}`: {str(res_data)[:80]}")
                            else:
                                executed_summaries.append(f"⚠️ `{tool_to_call}` note: {tool_res.get('reason')}")
                        else:
                            logger.warning(f"Agent profile '{self.profile.get('name') if self.profile else 'unknown'}' blocked tool '{tool_to_call}'")
                            executed_summaries.append(f"🚫 `{tool_to_call}` not permitted by active profile")
                    except Exception as call_err:
                        logger.warning(f"Failed to execute step {tool_to_call}: {call_err}")
                        executed_summaries.append(f"❌ `{tool_to_call}` error: {call_err}")

                # Mandatory post-plan spatial verification — structurally unavoidable,
                # runs after every primitive plan regardless of how the plan was produced.
                if any(t.startswith("blender:") for t, _ in steps_to_execute):
                    try:
                        from core.assembly_verification import AssemblyVerificationGate
                        from core.scene_transaction import SceneTransaction
                        mcp_bridge = getattr(self, "_mcp_manager", None)
                        if mcp_bridge is not None:
                            verifier = AssemblyVerificationGate(blender_bridge=mcp_bridge)
                            # Collect every object name touched by this plan.
                            # Boolean cutter names (suffixed _cutter or used as target_name
                            # in apply_boolean steps) are excluded from interpenetration checks
                            # because their overlap is intentional.
                            _boolean_targets = [
                                a.get("target_name")
                                for t, a in steps_to_execute
                                if t == "blender:apply_boolean" and a.get("target_name")
                            ]
                            _touched_names = [
                                a.get("name")
                                for t, a in steps_to_execute
                                if a.get("name") and t not in (
                                    "blender:delete_object",
                                    "blender:clear_scene",
                                    "blender:create_light",
                                    "blender:create_camera",
                                )
                            ]
                        # Detect whether the object is free-floating/symmetric (no ground plane).
                            # Primary source: rests_on_surface field on the AssemblyGraph, set by
                            # the LLM reasoning about the object's physical nature at decomposition
                            # time — not from prompt phrasing.
                            # Fallback for primitive-composition plans (no graph): check whether
                            # every create_ step has a horizontal rotation (all axes along X/Y),
                            # which is the structural signature of a dumbbell/axle/ring.
                            _origin_centered = False
                            # Check if any executed tool returned a graph with rests_on_surface=False
                            for _t, _r in executed_tool_results:
                                _d = _r.get("data") or {}
                                if isinstance(_d.get("rests_on_surface"), bool):
                                    _origin_centered = not _d["rests_on_surface"]
                                    break
                            # Primitive-composition fallback: all non-boolean cylinders are horizontal
                            if not _origin_centered:
                                _create_steps = [
                                    a for t, a in steps_to_execute
                                    if t == "blender:create_cylinder"
                                ]
                                if _create_steps and all(
                                    abs(float((a.get("rotation") or [0, 0, 0])[1])) >= 85
                                    for a in _create_steps
                                ):
                                    _origin_centered = True
                            v_res = await verifier.verify_flat_object_set(
                                object_names=_touched_names,
                                task_id=task_id,
                                boolean_targets=_boolean_targets,
                                origin_centered=_origin_centered,
                            )
                            if not v_res.get("ok"):
                                logger.warning(
                                    f"[task={task_id}] Post-plan verification failed: {v_res.get('error')}. "
                                    f"Initiating rollback of {len(_touched_names)} objects."
                                )
                                txn = SceneTransaction(tool_executor=self)
                                await txn.rollback()
                                self.update_step_status(step_id, "FAILED", {"verification_error": v_res.get("error")})
                                return {
                                    "response": (
                                        f"\u26a0\ufe0f **Spatial Verification Failed** \u2014 build rolled back.\n\n"
                                        f"{v_res.get('error')}\n\n"
                                        "The scene has been restored to its previous state. "
                                        "Please revise the geometry and try again."
                                    ),
                                    "model_used": model_id,
                                    "verification_failed": True,
                                    "verification": v_res,
                                }
                    except Exception as _vfy_err:
                        logger.warning(f"[task={task_id}] Post-plan verification skipped: {_vfy_err}")

                # Progressive Disclosure Follow-Up Turn:
                # If search_tools discovered schemas, give LLM a follow-up turn with surfaced schemas
                discovered_searches = [
                    (t_name, t_res) for t_name, t_res in executed_tool_results
                    if t_name == "search_tools"
                    and isinstance(t_res.get("data"), dict)
                    and t_res["data"].get("found", 0) > 0
                ]
                if discovered_searches:
                    disc_data = discovered_searches[0][1]["data"]
                    disc_schemas = disc_data.get("formatted_schemas", "")
                    disc_prompt = (
                        f"The user originally requested: {prompt}\n\n"
                        f"You searched for tools and surfaced these capabilities:\n"
                        f"{disc_schemas}\n\n"
                        "Instructions: Now call the appropriate tool using JSON block or answer the user directly."
                    )
                    try:
                        second_turn = await self.call_llm(
                            task_id=task_id,
                            system_rules=active_system_prompt + "\n\n" + disc_schemas,
                            task_prompt=disc_prompt,
                            model_id=model_id,
                            lease_id=lease_id,
                            lease_generation=lease_generation,
                            context_budget=claim.context_budget,
                            temperature=0.2,
                        )
                        if second_turn and not second_turn.strip().startswith("⚠️"):
                            response = second_turn
                            for block in re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", second_turn, re.DOTALL):
                                try:
                                    parsed = json.loads(block)
                                    if parsed.get("action") == "call_tool" and parsed.get("tool"):
                                        st_tool = parsed["tool"]
                                        st_args = parsed.get("args") or {}
                                        if st_tool != "search_tools":
                                            st_res = await self.execute_tool(st_tool, st_args, task_id=task_id, step_id=step_id)
                                            executed_tool_results.append((st_tool, st_res))
                                            st_data = st_res.get("data")
                                            if st_res.get("status") == "ok":
                                                if isinstance(st_data, dict) and "output" in st_data:
                                                    executed_summaries.append(f"✅ `{st_tool}`: {str(st_data['output']).strip()[:80]}")
                                                else:
                                                    executed_summaries.append(f"✅ `{st_tool}`: OK")
                                            else:
                                                executed_summaries.append(f"⚠️ `{st_tool}` note: {st_res.get('reason')}")
                                except Exception:
                                    pass
                    except Exception as disc_err:
                        logger.warning(f"Tool search follow-up turn error: {disc_err}")

                # Grounded Observation Synthesis (Claude Code QueryEngine pattern)
                # Feed real observations back into LLM so it reflects actual tool outcomes
                _blender_primitive_tools = {
                    "blender:create_cylinder", "blender:create_box", "blender:create_sphere",
                    "blender:create_cone", "blender:create_torus", "blender:apply_boolean",
                    "blender:set_material", "blender:create_light", "blender:create_camera",
                    "blender:clear_scene", "blender:apply_subdivision", "blender:apply_bevel",
                    "blender:set_smooth_shading", "blender:join_objects",
                }
                has_substantive_result = any(
                    (
                        isinstance(r.get("data"), dict)
                        and (
                            "build_id" in r["data"]
                            or "total_polys" in r["data"]
                            or "poly_count" in r["data"]
                            or (r["data"].get("ok") is True and t in _blender_primitive_tools)
                        )
                    )
                    for t, r in executed_tool_results
                )
                if has_substantive_result:
                    obs_payloads = []
                    for t_name, t_res in executed_tool_results:
                        d = t_res.get("data")
                        if isinstance(d, dict):
                            obs_payloads.append(f"Action: `{t_name}`\nResult: {json.dumps(d, indent=2)}")
                        else:
                            obs_payloads.append(f"Action: `{t_name}`\nResult: {d or t_res.get('reason')}")

                    # Determine if this is a build_spec result or primitive composition
                    _is_build_spec = any(
                        isinstance(r.get("data"), dict) and "build_id" in r["data"]
                        for _, r in executed_tool_results
                    )
                    if _is_build_spec:
                        _synth_instructions = (
                            "Write a clear, confident response confirming the 3D model was built and loaded. "
                            "Mention the model name, polygon count, and quality verification status. "
                            "End your response with exactly one line in this format: 'build_id: <the_actual_build_id_value>'. "
                            "Do NOT output raw JSON blocks. Do NOT write 'save as approved' in your response."
                        )
                    else:
                        _synth_instructions = (
                            "Write a clear, confident response summarising what was built in Blender. "
                            "List each object created (name, type, location) based strictly on the observations above. "
                            "Do NOT fabricate polygon counts or build IDs that are not in the observations. "
                            "Do NOT output raw JSON blocks."
                        )
                    synth_task = (
                        f"The user originally requested: {prompt}\n\n"
                        f"The system executed the required tools with these real observations:\n"
                        + "\n---\n".join(obs_payloads)
                        + f"\n\nInstructions: {_synth_instructions}"
                    )
                    # Honesty note: surface any resolver-estimated dimensions to the user
                    estimated_dims = []
                    for t_name, t_res in executed_tool_results:
                        d = t_res.get("data") or {}
                        for part_key, sources in (d.get("_dimension_sources") or {}).items():
                            if isinstance(sources, dict):
                                for dim_name, src in sources.items():
                                    if src not in ("user_stated", "cache"):
                                        estimated_dims.append(f"{part_key}.{dim_name}")
                            elif isinstance(sources, str) and sources not in ("user_stated", "cache"):
                                estimated_dims.append(part_key)
                    if estimated_dims:
                        synth_task += (
                            f"\n\nNote: the following dimensions were not specified by the user and were "
                            f"estimated from prior knowledge: {', '.join(estimated_dims)}. "
                            "Mention this briefly at the end of your response."
                        )
                    try:
                        grounded_text = await self.call_llm(
                            task_id=task_id,
                            system_rules="You are CUA-Sentinel. Provide a concise, professional confirmation of the executed 3D action based strictly on the observation data provided.",
                            task_prompt=synth_task,
                            model_id=model_id,
                            lease_id=lease_id,
                            lease_generation=lease_generation,
                            context_budget=claim.context_budget,
                            temperature=0.2,
                        )
                        if grounded_text and not grounded_text.strip().startswith("⚠️"):
                            response = grounded_text
                        elif executed_summaries:
                            response += "\n\n**Actions Executed:**\n" + "\n".join(f"- {s}" for s in executed_summaries)
                    except Exception as synth_err:
                        logger.warning(f"Synthesis turn error: {synth_err}")
                        if executed_summaries:
                            response += "\n\n**Actions Executed:**\n" + "\n".join(f"- {s}" for s in executed_summaries)
                elif executed_summaries:
                    response += "\n\n**Actions Executed in Blender / Connected App:**\n" + "\n".join(f"- {s}" for s in executed_summaries)

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
