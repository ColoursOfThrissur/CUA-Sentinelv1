import asyncio
import logging
import sqlite3
import json
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

from db.connections import get_operational_db

logger = logging.getLogger(__name__)


def init_digest_db():
    """Initializes the daily_digests table in operational.sqlite."""
    conn = get_operational_db()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS daily_digests (
            digest_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            full_markdown TEXT NOT NULL,
            portfolio_summary TEXT,
            email_summary TEXT,
            tech_summary TEXT,
            status TEXT NOT NULL DEFAULT 'COMPLETED',
            created_at TEXT NOT NULL
        )
        """
    )
    conn.commit()


class DigestEngine:
    """
    Automated Daily Operations Digest Engine for CUA-Sentinel.
    Aggregates Portfolio Valuation & P/L %, Recent Gmail highlights,
    and Tech Radar insights into a structured executive report.
    """

    def __init__(self, model_manager=None):
        self.model_manager = model_manager
        init_digest_db()

    async def generate_digest(self) -> Dict[str, Any]:
        """
        Generates a fresh Daily Operations Digest.
        """
        digest_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        now_str = datetime.now(timezone.utc).strftime("%B %d, %Y - %H:%M UTC")

        logger.info(f"Starting Daily Operations Digest generation: {digest_id}")

        # 1. Fetch Finance & Portfolio Summary
        portfolio_text = "Portfolio Status: No assets tracked currently."
        try:
            from tools.finance_tools import FinanceTools
            ft = FinanceTools()
            pf = ft.get_portfolio()
            if pf and isinstance(pf, list) and len(pf) > 0:
                symbols = [asset.get("asset_symbol") for asset in pf if asset.get("asset_symbol")]
                total_val = 0.0
                total_invested = 0.0
                asset_lines = []

                for asset in pf:
                    sym = asset.get("asset_symbol")
                    qty = float(asset.get("quantity", 0))
                    buy_price = float(asset.get("buy_price", 0))
                    invested = qty * buy_price
                    total_invested += invested

                    quote = await ft.fetch_ticker_quote(sym)
                    cur_price = float(quote.get("price", buy_price))
                    val = qty * cur_price
                    total_val += val

                    pnl_pct = ((cur_price - buy_price) / buy_price * 100) if buy_price > 0 else 0
                    asset_lines.append(f"- **{sym}**: Qty {qty} | Price ₹{cur_price:,.2f} | P/L {pnl_pct:+.2f}%")

                overall_pnl_pct = ((total_val - total_invested) / total_invested * 100) if total_invested > 0 else 0
                portfolio_text = f"**Total Valuation**: ₹{total_val:,.2f} (P/L: {overall_pnl_pct:+.2f}%)\n" + "\n".join(asset_lines)

                # Fetch breaking news specifically for held assets
                p_news = await ft.fetch_portfolio_news()
                if p_news:
                    news_lines = [f"\n### 📰 Breaking News on Your Holdings:"]
                    for item in p_news:
                        news_lines.append(f"**{item['symbol']} ({item['name']})**: {item['news_snippet']}")
                    portfolio_text += "\n" + "\n".join(news_lines)

            await ft.close()
        except Exception as p_err:
            logger.warning(f"Error compiling portfolio summary for digest: {p_err}")

        # 2. Fetch Recent Gmail Inbox Highlights & Action Feed Items
        email_text = "Gmail Action Feed: No unread statements or bill notices."
        try:
            from core.gmail_triage import GmailTriageEngine
            gt = GmailTriageEngine()
            feed_items = gt.get_feed()
            if not feed_items:
                feed_items = gt.scan_inbox()

            if feed_items:
                lines = []
                for item in feed_items[:5]:
                    amt_str = f" | Amount: **{item['amount']}**" if item.get('amount') else ""
                    due_str = f" | Due: **{item['due_date']}**" if item.get('due_date') else ""
                    lines.append(f"- **[{item['category']}]** {item['subject']}{amt_str}{due_str}\n  *Sender:* {item['sender']}")
                email_text = "\n".join(lines)
        except Exception as e_err:
            logger.warning(f"Error fetching Gmail highlights for digest: {e_err}")

        # 3. Fetch Tech Radar & Market Highlights
        tech_text = "- **AI Developments**: Open-weights LLMs and local agentic architectures advancing rapidly.\n- **Software & Tooling**: Local VRAM efficiency and dynamic prompt registries optimizing edge inference.\n- **Hardware Radar**: Next-gen GPU architectures expanding high-bandwidth memory for local AI models."
        try:
            from tools.web_search import WebSearchTool
            ws = WebSearchTool()
            search_res = ws.search("latest AI technology news software hardware releases", max_results=3)
            if search_res and len(search_res.strip()) > 30:
                tech_text = search_res
        except Exception as t_err:
            logger.warning(f"Error compiling tech radar for digest: {t_err}")

        # 4. Synthesize Executive Daily Digest
        full_markdown = f"""# 📊 Sentinel Operations Digest — {now_str}

---

## 📈 1. Portfolio & Financial Operations
{portfolio_text}

---

## 📧 2. Gmail Inbox & Order Updates
{email_text}

---

## 🌐 3. Tech & Industry Radar
{tech_text}

---
*Generated automatically by CUA-Sentinel local Operations Engine.*
"""

        title = f"Daily Operations Digest — {now_str}"

        # Save to SQLite
        conn = get_operational_db()
        conn.execute(
            """
            INSERT INTO daily_digests (
                digest_id, title, full_markdown, portfolio_summary,
                email_summary, tech_summary, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, 'COMPLETED', ?)
            """,
            (digest_id, title, full_markdown, portfolio_text, email_text, tech_text, created_at)
        )
        conn.commit()

        logger.info(f"Daily Operations Digest completed: {digest_id}")

        return {
            "digest_id": digest_id,
            "title": title,
            "full_markdown": full_markdown,
            "portfolio_summary": portfolio_text,
            "email_summary": email_text,
            "tech_summary": tech_text,
            "created_at": created_at
        }

    def get_latest_digest(self) -> Optional[Dict[str, Any]]:
        """Retrieves the most recent digest from SQLite."""
        conn = get_operational_db()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT digest_id, title, full_markdown, portfolio_summary,
                   email_summary, tech_summary, status, created_at
            FROM daily_digests
            ORDER BY created_at DESC
            LIMIT 1
            """
        )
        r = cur.fetchone()
        if not r:
            return None
        return {
            "digest_id": r[0],
            "title": r[1],
            "full_markdown": r[2],
            "portfolio_summary": r[3],
            "email_summary": r[4],
            "tech_summary": r[5],
            "status": r[6],
            "created_at": r[7]
        }

    def list_digests(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Lists historical digests."""
        conn = get_operational_db()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT digest_id, title, created_at, status
            FROM daily_digests
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,)
        )
        rows = cur.fetchall()
        return [{"digest_id": r[0], "title": r[1], "created_at": r[2], "status": r[3]} for r in rows]
