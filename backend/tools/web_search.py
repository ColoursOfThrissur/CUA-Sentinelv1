import logging
import html
import re
from typing import Optional, List, Dict, Any
from urllib.parse import urlparse, unquote
import feedparser
import httpx
from bs4 import BeautifulSoup

from core.scraper_sanitizer import scraper_sanitizer

logger = logging.getLogger(__name__)

ALLOWED_SCHEMES = ("http://", "https://")
REQUEST_TIMEOUT = 15
MAX_CONTENT_CHARS = 12000

COMMON_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


class WebSearchTool:
    """
    Multi-Engine Web Search and Deep Content Scraper.
    Supports DuckDuckGo POST (HTML), DuckDuckGo Lite, and Wikipedia API fallbacks.
    Air-gapped and sanitized against prompt injections before reaching LLM context.
    """

    def __init__(self):
        self._headers = COMMON_HEADERS

    NEWS_KEYWORDS = ("news", "latest", "today", "recent", "current", "update", "updates", "breaking", "happening", "this week")

    def _has_news_intent(self, query: str) -> bool:
        q_lower = query.lower()
        return any(kw in q_lower for kw in self.NEWS_KEYWORDS)

    def _search_google_news(self, query: str, max_results: int) -> List[Dict[str, str]]:
        """Real-time Google News RSS search (instant, verified, live news from today)."""
        try:
            # Clean query of filler words
            clean_term = re.sub(r'\b(what|is|the|give|me|tell|about|show|latest|news|on|for|in|today|current|recent)\b', '', query, flags=re.IGNORECASE).strip()
            clean_term = re.sub(r'\s+', ' ', clean_term).strip()
            if not clean_term or len(clean_term) < 2:
                feed_url = "https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en"
            else:
                from urllib.parse import quote_plus
                feed_url = f"https://news.google.com/rss/search?q={quote_plus(clean_term)}&hl=en-US&gl=US&ceid=US:en"

            with httpx.Client(timeout=REQUEST_TIMEOUT, follow_redirects=True) as client:
                resp = client.get(feed_url, headers=self._headers)
                if resp.status_code != 200 or not resp.text:
                    return []

            parsed = feedparser.parse(resp.text)
            results = []
            for entry in parsed.entries[:max_results]:
                title = entry.get("title", "")
                link = entry.get("link", "")
                pub_date = entry.get("published", "")
                source_title = entry.get("source", {}).get("title", "") if isinstance(entry.get("source"), dict) else ""
                summary = entry.get("summary", "")
                clean_snippet = re.sub(r'<[^>]+>', '', summary).strip() if summary else title

                domain = source_title or (urlparse(link).netloc if link else "news.google.com")
                if title:
                    results.append({
                        "title": self._sanitize_text(title),
                        "url": link,
                        "snippet": self._sanitize_text(f"{clean_snippet} [Published: {pub_date}]"),
                        "source": domain,
                        "engine": "Google-News-Live",
                    })
            return results
        except Exception as e:
            logger.debug(f"Google News RSS error: {e}")
            return []

    def search_structured(self, query: str, max_results: int = 4) -> List[Dict[str, str]]:
        """
        Executes web search and returns structured result items:
        [{"title": ..., "url": ..., "snippet": ..., "source": ..., "engine": ...}]
        Falls back across multiple search engines automatically.
        Prioritizes live news feeds for temporal queries.
        """
        clean_q = query.strip()
        if not clean_q:
            return []

        is_news = self._has_news_intent(clean_q)

        # Tier 0: For news/latest queries, query real-time live news first
        if is_news:
            news_results = self._search_google_news(clean_q, max_results)
            if news_results:
                return news_results

        # Tier 1: DuckDuckGo HTML via POST (with date filter if news)
        results = self._search_ddg_post(clean_q, max_results, date_filter="m" if is_news else None)
        if results:
            return results

        # Tier 2: DuckDuckGo Lite via POST
        logger.info(f"DDG POST returned 0 results for '{clean_q}'. Falling back to DDG Lite.")
        results = self._search_ddg_lite(clean_q, max_results)
        if results:
            return results

        # Tier 3: Wikipedia API Fallback (Disabled for news/recency queries to avoid 90s/historical articles)
        if not is_news:
            logger.info(f"DDG Lite returned 0 results for '{clean_q}'. Falling back to Wikipedia API.")
            results = self._search_wikipedia(clean_q, max_results)
            if results:
                return results

        logger.warning(f"All search engines returned 0 results for query: '{clean_q}'")
        return []

    def search(self, query: str, max_results: int = 3) -> str:
        """
        Uses multi-engine search and returns sanitized plain text of top results.
        Preserves backward compatibility with existing callers.
        """
        items = self.search_structured(query, max_results=max_results)
        if not items:
            return ""

        formatted = []
        for it in items:
            source = it.get("source") or it.get("url")
            title = it.get("title", "")
            snippet = it.get("snippet", "")
            formatted.append(f"[{source}] {title}: {snippet}")

        return self._sanitize_text("\n\n".join(formatted))

    def _search_ddg_post(self, query: str, max_results: int, date_filter: Optional[str] = None) -> List[Dict[str, str]]:
        """DuckDuckGo HTML search using POST (bypasses GET 202 bot challenge)."""
        try:
            url = "https://html.duckduckgo.com/html/"
            post_data = {"q": query}
            if date_filter:
                post_data["df"] = date_filter
            with httpx.Client(timeout=REQUEST_TIMEOUT, follow_redirects=True) as client:
                resp = client.post(url, data=post_data, headers=self._headers)
                if resp.status_code != 200 or not resp.text:
                    return []

            soup = BeautifulSoup(resp.text, "lxml")
            results = []
            bodies = soup.select(".result__body")
            for body in bodies:
                # Skip sponsored ads
                parent = body.find_parent(class_=re.compile(r"result--ad"))
                if parent:
                    continue

                title_el = body.select_one(".result__title")
                snippet_el = body.select_one(".result__snippet")
                url_el = body.select_one(".result__url")
                a_tag = title_el.find("a") if title_el else None

                raw_url = ""
                if a_tag and a_tag.get("href"):
                    raw_href = a_tag["href"]
                    # Extract target from DDG redirect url e.g. //duckduckgo.com/l/?uddg=...
                    if "uddg=" in raw_href:
                        parsed_uddg = re.search(r"uddg=([^&]+)", raw_href)
                        if parsed_uddg:
                            raw_url = unquote(parsed_uddg.group(1))
                    if not raw_url and raw_href.startswith("http"):
                        raw_url = raw_href

                title = title_el.get_text(strip=True) if title_el else ""
                snippet = snippet_el.get_text(strip=True) if snippet_el else ""
                source = url_el.get_text(strip=True) if url_el else ""

                if not raw_url and source:
                    raw_url = f"https://{source.split('/')[0]}"

                if title and snippet:
                    clean_title = self._sanitize_text(title)
                    clean_snippet = self._sanitize_text(snippet)
                    domain = urlparse(raw_url).netloc or source
                    results.append({
                        "title": clean_title,
                        "url": raw_url,
                        "snippet": clean_snippet,
                        "source": domain,
                        "engine": "DuckDuckGo-HTML",
                    })
                    if len(results) >= max_results:
                        break

            return results
        except Exception as e:
            logger.debug(f"DDG POST search error: {e}")
            return []

    def _search_ddg_lite(self, query: str, max_results: int) -> List[Dict[str, str]]:
        """DuckDuckGo Lite search fallback."""
        try:
            url = "https://lite.duckduckgo.com/lite/"
            with httpx.Client(timeout=REQUEST_TIMEOUT, follow_redirects=True) as client:
                resp = client.post(url, data={"q": query}, headers=self._headers)
                if resp.status_code != 200 or not resp.text:
                    return []

            soup = BeautifulSoup(resp.text, "lxml")
            results = []
            links = soup.select(".result-link")
            snippets = soup.select(".result-snippet")

            for i in range(min(len(links), len(snippets))):
                a_tag = links[i]
                title = a_tag.get_text(strip=True)
                raw_href = a_tag.get("href", "")
                raw_url = raw_href
                if "uddg=" in raw_href:
                    m = re.search(r"uddg=([^&]+)", raw_href)
                    if m:
                        raw_url = unquote(m.group(1))

                snippet = snippets[i].get_text(strip=True) if i < len(snippets) else ""
                domain = urlparse(raw_url).netloc or "duckduckgo.com"

                if title and snippet:
                    results.append({
                        "title": self._sanitize_text(title),
                        "url": raw_url,
                        "snippet": self._sanitize_text(snippet),
                        "source": domain,
                        "engine": "DuckDuckGo-Lite",
                    })
                    if len(results) >= max_results:
                        break

            return results
        except Exception as e:
            logger.debug(f"DDG Lite search error: {e}")
            return []

    def _search_wikipedia(self, query: str, max_results: int) -> List[Dict[str, str]]:
        """Wikipedia OpenSearch + Summary API fallback (free, instant, highly factual)."""
        wiki_headers = {
            "User-Agent": "SentinelResearch/1.0 (https://github.com/ColoursOfThrissur/CUA-Sentinelv1; contact@sentinel.local)"
        }
        try:
            api_url = "https://en.wikipedia.org/w/api.php"
            params = {
                "action": "opensearch",
                "search": query,
                "limit": max_results,
                "namespace": 0,
                "format": "json",
            }
            with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
                resp = client.get(api_url, params=params, headers=wiki_headers)
                if resp.status_code != 200:
                    return []
                data = resp.json()

            # Format: [query, [titles], [snippets], [urls]]
            if len(data) >= 4:
                titles = data[1]
                snippets = data[2]
                urls = data[3]
                results = []
                for i in range(len(titles)):
                    raw_snippet = snippets[i] if i < len(snippets) and snippets[i] else ""
                    if not raw_snippet:
                        # Fetch quick summary extract from Wikipedia REST API
                        try:
                            sum_resp = httpx.get(
                                f"https://en.wikipedia.org/api/rest_v1/page/summary/{titles[i].replace(' ', '_')}",
                                headers=wiki_headers,
                                timeout=5.0,
                            )
                            if sum_resp.status_code == 200:
                                raw_snippet = sum_resp.json().get("extract", "")
                        except Exception:
                            raw_snippet = f"Wikipedia encyclopedia entry for {titles[i]}."

                    clean_title = self._sanitize_text(titles[i])
                    clean_snippet = self._sanitize_text(raw_snippet or f"Wikipedia entry on {titles[i]}")
                    url = urls[i] if i < len(urls) else ""
                    results.append({
                        "title": clean_title,
                        "url": url,
                        "snippet": clean_snippet,
                        "source": "en.wikipedia.org",
                        "engine": "Wikipedia",
                    })
                return results
            return []
        except Exception as e:
            logger.debug(f"Wikipedia search error: {e}")
            return []

    def deep_scrape_url(self, url: str, max_chars: int = MAX_CONTENT_CHARS) -> Dict[str, Any]:
        """
        Deep Article Scraper: fetches URL, strips ads/nav/scripts, extracts main body,
        and runs both deterministic and prompt-injection sanitization.
        """
        parsed_domain = urlparse(url).netloc
        if not any(url.startswith(s) for s in ALLOWED_SCHEMES):
            return {
                "url": url,
                "domain": parsed_domain,
                "title": "",
                "error": "Invalid scheme",
                "content": "",
                "char_count": 0,
                "was_sanitized": False,
            }

        headers = dict(self._headers)
        if "wikipedia.org" in parsed_domain:
            headers["User-Agent"] = "SentinelResearch/1.0 (https://github.com/ColoursOfThrissur/CUA-Sentinelv1; contact@sentinel.local)"

        try:
            with httpx.Client(timeout=REQUEST_TIMEOUT, follow_redirects=True) as client:
                resp = client.get(url, headers=headers)
                resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "lxml")

            # Extract title
            title = soup.title.get_text(strip=True) if soup.title else ""

            # Remove noise elements
            for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form", "iframe", "noscript"]):
                tag.decompose()

            # Prefer <article> or <main> if available
            main_container = soup.find("article") or soup.find("main") or soup.body or soup
            paragraphs = [p.get_text(separator=" ", strip=True) for p in main_container.find_all(["p", "h1", "h2", "h3", "h4", "li"])]
            text = "\n\n".join(p for p in paragraphs if len(p) > 15)

            if not text:
                text = main_container.get_text(separator="\n", strip=True)

            # Air-gap sanitization pass against prompt injection
            clean_text, was_injected, _ = scraper_sanitizer.sanitize_text(text[:max_chars])
            clean_text = self._sanitize_text(clean_text)

            return {
                "url": url,
                "domain": parsed_domain,
                "title": self._sanitize_text(title),
                "content": clean_text,
                "char_count": len(clean_text),
                "was_sanitized": was_injected,
            }
        except Exception as e:
            logger.error(f"Deep scrape failed for {url}: {e}")
            return {
                "url": url,
                "domain": parsed_domain,
                "title": "",
                "error": str(e),
                "content": "",
                "char_count": 0,
                "was_sanitized": False,
            }

    def fetch_page(self, url: str) -> str:
        """Fetch and extract plain text from a single URL."""
        res = self.deep_scrape_url(url, max_chars=8000)
        return res.get("content", "")

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
        """
        if not text:
            return ""
        text = html.unescape(text)
        text = re.sub(r"<[^>]+>", "", text)
        text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
        # Strip obvious prompt injection patterns
        injection_patterns = [
            r"ignore\s+(all\s+|previous\s+|prior\s+)*instructions?",
            r"disregard\s+(all\s+|previous\s+|prior\s+)*prompts?",
            r"system\s*prompt",
            r"you\s+are\s+now\s+in",
            r"system\s+override",
            r"forget\s+(everything|all)",
        ]
        for pattern in injection_patterns:
            text = re.sub(pattern, "[REDACTED]", text, flags=re.IGNORECASE)
        return text.strip()

