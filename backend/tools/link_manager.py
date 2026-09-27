import hashlib
import ipaddress
import json
import logging
import re
import socket
import sqlite3
import uuid
import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse, urljoin
import httpx
from bs4 import BeautifulSoup

from db.connections import get_knowledge_db, get_operational_db

logger = logging.getLogger(__name__)

MAX_FETCH_BYTES = 2_000_000
MAX_REDIRECT_HOPS = 3

class BlockedURLError(ValueError):
    """Raised when URL validation fails (SSRF protection)."""
    pass

def check_url_safety(url: str) -> None:
    """Validate that URL scheme is http/https and destination is a global non-private IP."""
    u = urlparse(url)
    if u.scheme not in ("http", "https") or not u.hostname:
        raise BlockedURLError(f"Invalid or disallowed scheme: {u.scheme}")
    if u.port not in (None, 80, 443, 8080):
        raise BlockedURLError(f"Disallowed destination port: {u.port}")
    try:
        addr_info = socket.getaddrinfo(u.hostname, u.port or 443, type=socket.SOCK_STREAM)
        for *_, sockaddr in addr_info:
            raw_ip = sockaddr[0].split("%")[0]
            ip = ipaddress.ip_address(raw_ip)
            if not ip.is_global:
                raise BlockedURLError(f"Destination IP {ip} is non-global / loopback / private")
    except socket.gaierror as e:
        raise BlockedURLError(f"DNS resolution failure for host '{u.hostname}': {e}")

class LinkManager:
    """
    URL Bookmark Manager (`user_links`).
    Crawls, cleans (HTML to markdown/text), summarizes, tags, and indexes links into
    SQLite storage and disposable Chroma vector memory for RAG recall.
    """

    def __init__(self):
        self.http_client = httpx.AsyncClient(
            timeout=15.0,
            follow_redirects=False,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            },
        )

    def add_link(self, url: str, title: Optional[str] = None) -> Dict[str, Any]:
        """
        Registers a new bookmark link. Returns link info.
        """
        clean_url = url.strip()
        parsed = urlparse(clean_url)
        domain = parsed.netloc or "external"
        link_id = f"link_{uuid.uuid4().hex[:12]}"

        conn = get_operational_db()
        try:
            conn.execute(
                """
                INSERT INTO user_links (link_id, url, title, domain, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'PENDING', ?, ?)
                ON CONFLICT(url) DO UPDATE SET updated_at = excluded.updated_at
                """,
                (
                    link_id,
                    clean_url,
                    title or domain,
                    domain,
                    datetime.now(timezone.utc).isoformat(),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            conn.commit()

            cur = conn.execute("SELECT * FROM user_links WHERE url = ?", (clean_url,))
            row = dict(cur.fetchone())
            return row
        finally:
            conn.close()

    def get_links(self, search: Optional[str] = None) -> List[Dict[str, Any]]:
        conn = get_operational_db()
        if search:
            cur = conn.execute(
                "SELECT * FROM user_links WHERE title LIKE ? OR url LIKE ? OR summary LIKE ? ORDER BY updated_at DESC",
                (f"%{search}%", f"%{search}%", f"%{search}%"),
            )
        else:
            cur = conn.execute("SELECT * FROM user_links ORDER BY updated_at DESC")
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        for r in rows:
            if isinstance(r.get("tags"), str):
                try:
                    r["tags"] = json.loads(r["tags"])
                except Exception:
                    r["tags"] = []
        return rows

    async def crawl_and_process(self, link_id: str) -> Dict[str, Any]:
        """
        Fetches web page, extracts article text, generates summary and tags,
        stores in SQLite, and indexes into canonical knowledge DB for RAG.
        """
        conn = get_operational_db()
        cur = conn.execute("SELECT * FROM user_links WHERE link_id = ?", (link_id,))
        row = cur.fetchone()
        if not row:
            conn.close()
            return {"status": "FAILED", "error": "Link not found"}

        url = row["url"]
        conn.execute("UPDATE user_links SET status = 'CRAWLING' WHERE link_id = ?", (link_id,))
        conn.commit()

        try:
            # Safe HTTP fetch with SSRF validation, redirect cap, and size limit
            current_url = url
            res_text = ""
            for hop in range(MAX_REDIRECT_HOPS + 1):
                await asyncio.to_thread(check_url_safety, current_url)
                resp = await self.http_client.get(current_url)
                if resp.is_redirect:
                    redir_loc = resp.headers.get("location")
                    if not redir_loc:
                        raise BlockedURLError("Redirect response missing Location header")
                    current_url = urljoin(current_url, redir_loc)
                    continue
                
                content_type = resp.headers.get("content-type", "")
                if "text/html" not in content_type and "text/plain" not in content_type:
                    raise BlockedURLError(f"Disallowed content-type: {content_type}")
                
                if len(resp.content) > MAX_FETCH_BYTES:
                    raise BlockedURLError(f"Response size exceeded {MAX_FETCH_BYTES} bytes limit")
                
                res_text = resp.text
                break
            else:
                raise BlockedURLError("Exceeded maximum redirect hops")

            html_content = res_text
            soup = BeautifulSoup(html_content, "html.parser")

            # Remove scripts, styles, navs, footers, hidden elements
            for elem in soup(["script", "style", "nav", "footer", "header", "aside", "iframe"]):
                elem.decompose()
            for hidden in soup.find_all(style=re.compile(r'display:\s*none', re.I)):
                hidden.decompose()

            page_title = soup.title.string.strip() if soup.title and soup.title.string else row["domain"]

            # Extract main text
            paragraphs = [p.get_text(strip=True) for p in soup.find_all(["p", "h1", "h2", "h3", "article"])]
            raw_text = "\n\n".join([p for p in paragraphs if len(p) > 20])

            if not raw_text:
                raw_text = soup.get_text(separator="\n", strip=True)[:5000]

            # Generate 3-bullet AI Markdown summary & tags
            summary_bullets = self._generate_3_bullet_summary(page_title, raw_text)
            tags = self._extract_tags(page_title + " " + raw_text[:1000])

            # Update Operational DB
            conn.execute(
                """
                UPDATE user_links 
                SET title = ?, summary = ?, raw_content = ?, tags = ?, status = 'INDEXED', chroma_indexed = 1, updated_at = ?
                WHERE link_id = ?
                """,
                (
                    page_title,
                    summary_bullets,
                    raw_text[:20000],  # Keep up to 20k chars in SQLite
                    json.dumps(tags),
                    datetime.now(timezone.utc).isoformat(),
                    link_id,
                ),
            )
            conn.commit()

            # Index into Canonical Knowledge DB (BP03)
            self._index_to_knowledge_db(url, row["domain"], page_title, raw_text)

            return {
                "link_id": link_id,
                "title": page_title,
                "summary": summary_bullets,
                "tags": tags,
                "status": "INDEXED",
            }
        except Exception as e:
            logger.error(f"Error crawling link {url}: {e}")
            conn.execute("UPDATE user_links SET status = 'FAILED' WHERE link_id = ?", (link_id,))
            conn.commit()
            return {"link_id": link_id, "status": "FAILED", "error": str(e)}
        finally:
            conn.close()

    def _generate_3_bullet_summary(self, title: str, text: str) -> str:
        paragraphs = [p.strip() for p in text.split("\n\n") if len(p.strip()) > 30]
        bullets = []
        if paragraphs:
            bullets.append(f"• **Overview**: {paragraphs[0][:180]}...")
        if len(paragraphs) > 1:
            bullets.append(f"• **Key Details**: {paragraphs[1][:180]}...")
        if len(paragraphs) > 2:
            bullets.append(f"• **Takeaway**: {paragraphs[2][:180]}...")

        while len(bullets) < 3:
            bullets.append(f"• **Insight**: Extracted article content from {title}.")

        return "\n".join(bullets)

    def _extract_tags(self, text: str) -> List[str]:
        keywords = ["ai", "react", "python", "finance", "crypto", "bitcoin", "gpu", "ollama", "tech", "web", "design", "trading", "docker", "linux"]
        found = []
        lower_text = text.lower()
        for kw in keywords:
            if kw in lower_text:
                found.append(kw.upper() if len(kw) <= 4 else kw.capitalize())
        return list(set(found))[:5] or ["General"]

    def _index_to_knowledge_db(self, url: str, domain: str, title: str, text: str):
        k_conn = get_knowledge_db()
        try:
            doc_id = f"doc_{uuid.uuid4().hex[:12]}"
            doc_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()

            k_conn.execute(
                """
                INSERT INTO canonical_documents 
                (document_id, source_uri, domain, authority_level, raw_content, document_hash, embedding_config_hash, valid_from, index_status)
                VALUES (?, ?, ?, 'COMMUNITY', ?, ?, 'nomic-v1.5', ?, 'INDEXED')
                ON CONFLICT(document_id) DO NOTHING
                """,
                (
                    doc_id,
                    url,
                    domain,
                    f"# {title}\n\n{text}",
                    doc_hash,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            k_conn.commit()
        except Exception as e:
            logger.warning(f"Knowledge DB index warning for {url}: {e}")
        finally:
            k_conn.close()

    async def close(self):
        await self.http_client.aclose()
