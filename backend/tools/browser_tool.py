import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse
import httpx
from bs4 import BeautifulSoup

from db.connections import get_operational_db, get_knowledge_db

logger = logging.getLogger(__name__)


class DeepBrowserEngine:
    """
    Multi-Step Deep Autonomous Web Surfer & Research Engine.
    Executes depth-controlled crawling, dynamic text extraction, HTML-to-markdown conversion,
    and structured storage in SQLite / Knowledge RAG DB.
    """

    def __init__(self):
        self.http_client = httpx.AsyncClient(
            timeout=15.0,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
            },
        )

    def create_session(self, query: str, max_depth: int = 2) -> str:
        session_id = f"crawl_{uuid.uuid4().hex[:12]}"
        conn = get_operational_db()
        conn.execute(
            "INSERT INTO web_crawl_sessions (session_id, query, current_depth, max_depth, status) VALUES (?, ?, 0, ?, 'RUNNING')",
            (session_id, query, max_depth),
        )
        conn.commit()
        conn.close()
        return session_id

    async def fetch_and_clean_page(self, url: str) -> Dict[str, Any]:
        """
        Fetches web page, extracts article text, converts to clean markdown-like text,
        and extracts outbound links.
        """
        try:
            res = await self.http_client.get(url)
            html_text = res.text
            soup = BeautifulSoup(html_text, "html.parser")

            # Readability style decomposition
            for tag in soup(["script", "style", "header", "footer", "nav", "aside", "svg", "form", "iframe"]):
                tag.decompose()

            title = soup.title.string.strip() if soup.title and soup.title.string else url

            # Extract main content elements (p, h1-h6, li, code, pre)
            content_nodes = soup.find_all(["h1", "h2", "h3", "h4", "p", "li", "pre", "code"])
            markdown_lines = []
            for node in content_nodes:
                text = node.get_text(" ", strip=True)
                if not text or len(text) < 15:
                    continue
                if node.name in ["h1", "h2", "h3"]:
                    markdown_lines.append(f"\n### {text}\n")
                elif node.name == "li":
                    markdown_lines.append(f"- {text}")
                elif node.name in ["pre", "code"]:
                    markdown_lines.append(f"```\n{text}\n```")
                else:
                    markdown_lines.append(text)

            cleaned_markdown = "\n\n".join(markdown_lines[:150])  # Cap at ~150 blocks

            # Extract outbound URLs
            outbound_links = []
            for a in soup.find_all("a", href=True):
                href = urljoin(url, a["href"])
                if href.startswith("http") and not any(ext in href for ext in [".png", ".jpg", ".pdf", ".zip", ".css"]):
                    outbound_links.append(href)

            return {
                "url": url,
                "title": title,
                "markdown": cleaned_markdown,
                "outbound_links": list(set(outbound_links))[:10],
                "success": True,
            }
        except Exception as e:
            logger.error(f"Error fetching page {url}: {e}")
            return {"url": url, "title": url, "markdown": "", "outbound_links": [], "success": False, "error": str(e)}

    async def execute_crawl_session(self, session_id: str, seed_urls: List[str]) -> Dict[str, Any]:
        """
        Executes a multi-depth crawl session across seed URLs.
        Stores extracted research facts and indexed documents into SQLite.
        """
        conn = get_operational_db()
        cur = conn.execute("SELECT * FROM web_crawl_sessions WHERE session_id = ?", (session_id,))
        session = cur.fetchone()
        if not session:
            conn.close()
            return {"error": "Session not found"}

        max_depth = session["max_depth"]
        query = session["query"]

        crawled_results = []
        queue = [(url, 0) for url in seed_urls[:3]]
        visited = set()

        while queue:
            current_url, depth = queue.pop(0)
            if current_url in visited or depth > max_depth:
                continue

            visited.add(current_url)
            page_data = await self.fetch_and_clean_page(current_url)

            if page_data["success"] and page_data["markdown"]:
                crawled_results.append({
                    "url": current_url,
                    "title": page_data["title"],
                    "depth": depth,
                    "snippet": page_data["markdown"][:400],
                })

                # Index to Canonical Knowledge DB for RAG recall
                self._save_to_knowledge_db(current_url, page_data["title"], page_data["markdown"])

                # Enqueue sub-links if depth < max_depth
                if depth < max_depth:
                    for sub_link in page_data["outbound_links"][:3]:
                        if sub_link not in visited:
                            queue.append((sub_link, depth + 1))

        # Update Session status in Operational DB
        conn.execute(
            "UPDATE web_crawl_sessions SET current_depth = ?, status = 'COMPLETED', extracted_facts = ? WHERE session_id = ?",
            (max_depth, json.dumps(crawled_results), session_id),
        )
        conn.commit()
        conn.close()

        return {
            "session_id": session_id,
            "query": query,
            "pages_crawled": len(crawled_results),
            "results": crawled_results,
        }

    def _save_to_knowledge_db(self, url: str, title: str, content: str):
        try:
            k_conn = get_knowledge_db()
            domain = urlparse(url).netloc
            doc_id = f"doc_{uuid.uuid4().hex[:12]}"
            k_conn.execute(
                """
                INSERT INTO canonical_documents 
                (document_id, source_uri, domain, authority_level, raw_content, document_hash, embedding_config_hash, valid_from, index_status)
                VALUES (?, ?, ?, 'COMMUNITY', ?, ?, 'nomic-v1.5', ?, 'INDEXED')
                """,
                (
                    doc_id,
                    url,
                    domain,
                    f"# {title}\n\n{content}",
                    str(hash(content)),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            k_conn.commit()
            k_conn.close()
        except Exception as e:
            logger.warning(f"Failed saving web crawl doc to knowledge DB: {e}")

    async def close(self):
        await self.http_client.aclose()
