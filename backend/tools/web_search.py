import logging
import html
import re
import feedparser
import httpx
from bs4 import BeautifulSoup
from typing import Optional

logger = logging.getLogger(__name__)

ALLOWED_SCHEMES = ("http://", "https://")
REQUEST_TIMEOUT = 20
MAX_CONTENT_CHARS = 8000


class WebSearchTool:
    """
    Fetches web content and RSS feeds.
    Raw content is NEVER passed directly to a privileged LLM.
    All output must go through the sanitizer model first.
    Tool-to-tool air gap enforced — this tool returns text only,
    never triggers another tool directly.
    """

    def search(self, query: str, max_results: int = 3) -> str:
        """
        Uses DuckDuckGo HTML search (no API key needed).
        Returns sanitized plain text of top results.
        """
        try:
            url = f"https://html.duckduckgo.com/html/?q={query.replace(' ', '+')}"
            with httpx.Client(timeout=REQUEST_TIMEOUT, follow_redirects=True) as client:
                resp = client.get(url, headers={"User-Agent": "Mozilla/5.0"})
                resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "lxml")
            results = []
            for result in soup.select(".result__body")[:max_results]:
                title_el = result.select_one(".result__title")
                snippet_el = result.select_one(".result__snippet")
                url_el = result.select_one(".result__url")
                title = title_el.get_text(strip=True) if title_el else ""
                snippet = snippet_el.get_text(strip=True) if snippet_el else ""
                source = url_el.get_text(strip=True) if url_el else ""
                results.append(f"[{source}] {title}: {snippet}")

            return self._sanitize_text("\n\n".join(results))

        except Exception as e:
            logger.error(f"Web search failed for '{query}': {e}")
            return ""

    def fetch_page(self, url: str) -> str:
        """Fetch and extract plain text from a single URL."""
        if not any(url.startswith(s) for s in ALLOWED_SCHEMES):
            logger.warning(f"Blocked non-HTTP URL: {url}")
            return ""
        try:
            with httpx.Client(timeout=REQUEST_TIMEOUT, follow_redirects=True) as client:
                resp = client.get(url, headers={"User-Agent": "Mozilla/5.0"})
                resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")
            for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                tag.decompose()
            text = soup.get_text(separator="\n", strip=True)
            return self._sanitize_text(text[:MAX_CONTENT_CHARS])
        except Exception as e:
            logger.error(f"Failed to fetch {url}: {e}")
            return ""

    def fetch_feeds(self, feed_urls: list) -> str:
        """Parse RSS/Atom feeds and return combined plain text entries."""
        all_entries = []
        for url in feed_urls:
            if not any(url.startswith(s) for s in ALLOWED_SCHEMES):
                continue
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries[:5]:
                    title = getattr(entry, "title", "")
                    summary = getattr(entry, "summary", "")
                    link = getattr(entry, "link", "")
                    clean = self._sanitize_text(f"{title}. {summary}")
                    all_entries.append(f"[{link}] {clean}")
            except Exception as e:
                logger.error(f"Failed to parse feed {url}: {e}")

        return "\n\n".join(all_entries)[:MAX_CONTENT_CHARS]

    def _sanitize_text(self, text: str) -> str:
        """
        Deterministic sanitization pass before any LLM sees the content.
        Strips HTML entities, control characters, and obvious injection patterns.
        The LLM sanitizer model is a second advisory pass on top of this.
        """
        text = html.unescape(text)
        text = re.sub(r"<[^>]+>", "", text)
        text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
        # Strip obvious prompt injection patterns
        injection_patterns = [
            r"ignore\s+(previous|all|prior)\s+instructions?",
            r"system\s*prompt",
            r"you\s+are\s+now",
            r"disregard\s+(all|previous)",
            r"forget\s+(everything|all)",
        ]
        for pattern in injection_patterns:
            text = re.sub(pattern, "[REDACTED]", text, flags=re.IGNORECASE)
        return text.strip()
