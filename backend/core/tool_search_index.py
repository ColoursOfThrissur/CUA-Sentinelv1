"""
Dynamic Tool Search & Progressive Disclosure Index for CUA-Sentinel.

Provides BM25-based semantic retrieval, domain synonym expansion, multi-surface
defanging (anti-prompt injection), query precision gating, and strict context token budgeting.
"""

import math
import re
import unicodedata
import logging
from typing import Dict, List, Any, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# Zero-width, directional override, and invisible unicode characters
ZERO_WIDTH_CHARS = re.compile(
    r"[\u200B-\u200D\uFEFF\u2060\u200E\u200F\u202A-\u202E\u00AD]"
)

# Toxic prompt-injection patterns to defang at index time
DEFANG_PATTERNS = [
    (r"<system\b[^>]*>.*?</system>", "[DEFANGED_SYSTEM_BLOCK]"),
    (r"</?system\b[^>]*>", "[DEFANGED_SYSTEM_TAG]"),
    (r"</?action_guidance\b[^>]*>", "[DEFANGED_ACTION_GUIDANCE]"),
    (r"</?connected_tools\b[^>]*>", "[DEFANGED_CONNECTED_TOOLS]"),
    (r"\[/?SYSTEM\]", "[DEFANGED_SYSTEM_TAG]"),
    (r"(?i)\badmin\s+(?:override|mode)\b", "[DEFANGED_ADMIN_OVERRIDE]"),
    (r"(?i)ignore\s+(?:all\s+)?previous\s+instructions", "[DEFANGED_INJECTION_ATTEMPT]"),
    (r"(?i)disregard\s+(?:all\s+)?prior\s+prompts", "[DEFANGED_INJECTION_ATTEMPT]"),
    (r"(?i)format\s+c:", "[DEFANGED_DESTRUCTIVE_COMMAND]"),
    (r"(?i)rm\s+-rf", "[DEFANGED_DESTRUCTIVE_COMMAND]"),
    (r"(?i)delete\s+all\s+files", "[DEFANGED_DESTRUCTIVE_COMMAND]"),
    (r"(?i)drop\s+table", "[DEFANGED_DESTRUCTIVE_COMMAND]"),
    (r"```json\s*\{\s*\"action\":\s*\"[^\"]+\"\s*\}\s*```", "[DEFANGED_JSON_BLOCK]"),
]

# Domain synonym dictionary with lower weighting to preserve precision
DOMAIN_SYNONYMS: Dict[str, List[Tuple[str, float]]] = {
    "merge": [("pull_request", 0.6), ("pr", 0.5)],
    "pr": [("pull_request", 0.7), ("github", 0.3)],
    "commit": [("commits", 0.5), ("git", 0.3)],
    "commits": [("commit", 0.5), ("git", 0.3)],
    "pull": [("pull_request", 0.4)],
    "issue": [("issues", 0.6), ("github", 0.3)],
    "issues": [("issue", 0.6), ("github", 0.3)],
    "folder": [("directory", 0.6), ("path", 0.4), ("filesystem", 0.3)],
    "folders": [("directory", 0.6), ("path", 0.4)],
    "directory": [("folder", 0.5), ("path", 0.4)],
    "directories": [("folder", 0.5), ("path", 0.4)],
    "dir": [("directory", 0.6), ("folder", 0.5)],
    "file": [("files", 0.5), ("filesystem", 0.3)],
    "files": [("file", 0.5), ("filesystem", 0.3)],
    "query": [("sql", 0.5), ("postgres", 0.4), ("database", 0.4)],
    "database": [("postgres", 0.6), ("table", 0.4), ("sql", 0.4)],
    "db": [("database", 0.6), ("postgres", 0.5), ("table", 0.4)],
    "sql": [("query", 0.5), ("postgres", 0.5), ("database", 0.4)],
    "picture": [("render", 0.5), ("image", 0.5), ("scene", 0.3)],
    "photo": [("render", 0.5), ("image", 0.5)],
    "image": [("render", 0.5), ("picture", 0.4)],
    "mesh": [("blender", 0.5), ("3d", 0.4), ("cylinder", 0.3)],
    "3d": [("blender", 0.5), ("mesh", 0.4)],
    "message": [("slack", 0.5), ("send_message", 0.5)],
    "alert": [("notification", 0.5), ("message", 0.4), ("slack", 0.4)],
    "notification": [("slack", 0.5), ("message", 0.4)],
    "post": [("send_message", 0.4), ("slack", 0.4)],
}

STOP_WORDS = {
    "a", "an", "the", "and", "or", "in", "on", "at", "to", "for", "with",
    "is", "are", "was", "were", "be", "been", "being", "have", "has", "had",
    "do", "does", "did", "can", "could", "should", "would", "my", "your",
    "our", "their", "this", "that", "these", "those", "all", "any", "some",
    "of", "from", "by", "as", "into", "through", "during", "before", "after",
    "above", "below", "between", "under", "again", "further", "then", "once",
    "i", "me", "you", "he", "she", "it", "we", "they", "what", "which",
    "who", "whom", "whose", "why", "how", "where", "when", "fully", "am"
}


class ToolSanitizer:
    """Multi-surface sanitizer and defanger for tool names, descriptions, and schemas."""

    @classmethod
    def normalize_unicode(cls, text: str) -> str:
        """Collapse unicode homoglyphs via NFKC and strip invisible/zero-width chars."""
        if not text or not isinstance(text, str):
            return ""
        normalized = unicodedata.normalize("NFKC", text)
        stripped = ZERO_WIDTH_CHARS.sub("", normalized)
        return stripped

    @classmethod
    def defang_instructions(cls, text: str) -> str:
        """Neutralize malicious injection instructions and tags."""
        if not text:
            return ""
        clean = text
        for pattern, replacement in DEFANG_PATTERNS:
            clean = re.sub(pattern, replacement, clean, flags=re.IGNORECASE | re.DOTALL)
        return clean

    @classmethod
    def sanitize_name(cls, name: str) -> str:
        """Sanitize tool name to strict safe identifier characters, stripping tags completely."""
        if not name:
            return "unnamed_tool"
        norm = cls.normalize_unicode(name)
        # First strip any XML/HTML tags directly
        stripped_tags = re.sub(r"<[^>]+>", "", norm)
        # Apply defanging to remaining text
        defanged = cls.defang_instructions(stripped_tags)
        # Allow only alphanumeric, underscores, hyphens, and colons
        safe_name = re.sub(r"[^a-zA-Z0-9_\-:]", "", defanged)
        return safe_name or "unnamed_tool"

    @classmethod
    def sanitize_text(cls, text: str) -> str:
        """Sanitize description or parameter text."""
        if not text:
            return ""
        norm = cls.normalize_unicode(text)
        return cls.defang_instructions(norm)


class ToolSearchIndex:
    """
    BM25 Tool Retrieval Engine with weighted multi-field scoring,
    precision co-occurrence gating, defanging, and hard token budget formatting.
    """

    MIN_SCORE_THRESHOLD: float = 1.35

    def __init__(self, mcp_manager: Optional[Any] = None):
        self.mcp_manager = mcp_manager
        self.sanitizer = ToolSanitizer()
        self.tools: List[Dict[str, Any]] = []
        self.doc_lengths: List[float] = []
        self.avg_doc_len: float = 0.0
        self.doc_term_freqs: List[Dict[str, float]] = []
        self.doc_freqs: Dict[str, int] = {}
        self.doc_names: List[Set[str]] = []
        self.total_docs: int = 0

    def tokenize(self, text: str) -> List[str]:
        """Normalize, strip punctuation, and tokenize string into terms."""
        clean = self.sanitizer.normalize_unicode(text).lower()
        words = re.findall(r"[a-z0-9_]+", clean)
        tokens = []
        for w in words:
            subparts = w.split("_")
            for sp in subparts:
                if sp and len(sp) > 1 and sp not in STOP_WORDS:
                    tokens.append(sp)
            if len(subparts) > 1 and w not in STOP_WORDS:
                tokens.append(w)
        return tokens

    def get_content_tokens(self, text: str) -> List[str]:
        """Extract clean content tokens (excluding stop words) for precision gating."""
        clean = self.sanitizer.normalize_unicode(text).lower()
        words = re.findall(r"[a-z0-9_]+", clean)
        return [w for w in words if len(w) > 1 and w not in STOP_WORDS]

    def build_index(self, tools: Optional[List[Dict[str, Any]]] = None) -> None:
        """Build BM25 term frequency tables from tool list or active MCPManager connections."""
        self.tools = []
        self.doc_lengths = []
        self.doc_term_freqs = []
        self.doc_freqs = {}
        self.doc_names = []

        raw_tools = tools
        if raw_tools is None and self.mcp_manager:
            raw_tools = []
            for app_id in self.mcp_manager.list_connected_app_ids():
                conn_tools = self.mcp_manager.get_tools_for_app(app_id)
                for t in conn_tools:
                    raw_tools.append({
                        "app_id": app_id,
                        "name": t.name,
                        "description": t.description,
                        "input_schema": t.input_schema,
                    })

        raw_tools = raw_tools or []
        if not raw_tools:
            # Cold-boot read-through: Load active tools from knowledge.sqlite catalog
            try:
                from db.connections import get_knowledge_db
                import json
                k_conn = get_knowledge_db()
                try:
                    cur = k_conn.execute(
                        "SELECT app_id, tool_name, description, input_schema FROM mcp_tool_catalog WHERE is_active = 1"
                    )
                    rows = cur.fetchall()
                    if rows:
                        raw_tools = []
                        for r in rows:
                            try:
                                schema = json.loads(r["input_schema"]) if r["input_schema"] else {}
                            except Exception:
                                schema = {}
                            raw_tools.append({
                                "app_id": r["app_id"],
                                "name": r["tool_name"],
                                "description": r["description"] or "",
                                "input_schema": schema,
                            })
                finally:
                    k_conn.close()
            except Exception as e:
                logger.debug(f"Could not load cold-boot tools from knowledge.sqlite: {e}")

        for raw in raw_tools:
            app_id = self.sanitizer.sanitize_name(raw.get("app_id", ""))
            name = self.sanitizer.sanitize_name(raw.get("name", ""))
            desc = self.sanitizer.sanitize_text(raw.get("description", ""))
            schema = raw.get("input_schema") or {}

            sanitized_props = {}
            prop_terms = []
            if isinstance(schema, dict) and "properties" in schema:
                for pk, pv in schema.get("properties", {}).items():
                    safe_pk = self.sanitizer.sanitize_name(pk)
                    if isinstance(pv, dict):
                        safe_pdesc = self.sanitizer.sanitize_text(pv.get("description", ""))
                        safe_ptype = pv.get("type", "string")
                        sanitized_props[safe_pk] = {
                            "type": safe_ptype,
                            "description": safe_pdesc,
                        }
                        prop_terms.extend(self.tokenize(f"{safe_pk} {safe_pdesc}"))
                    else:
                        sanitized_props[safe_pk] = {"type": "any", "description": ""}

            tool_key = f"mcp:{app_id}:{name}" if app_id else name

            name_tokens = self.tokenize(name)
            app_tokens = self.tokenize(app_id)
            desc_tokens = self.tokenize(desc)

            # Build term frequency with field weights
            tf: Dict[str, float] = {}
            for t in name_tokens:
                tf[t] = tf.get(t, 0.0) + 3.0
            for t in app_tokens:
                tf[t] = tf.get(t, 0.0) + 2.0
            for t in desc_tokens:
                tf[t] = tf.get(t, 0.0) + 1.0
            for t in prop_terms:
                tf[t] = tf.get(t, 0.0) + 0.8

            doc_len = sum(tf.values())

            self.tools.append({
                "key": tool_key,
                "app_id": app_id,
                "name": name,
                "description": desc,
                "properties": sanitized_props,
                "required": schema.get("required", []) if isinstance(schema, dict) else [],
            })
            self.doc_term_freqs.append(tf)
            self.doc_lengths.append(doc_len)
            self.doc_names.append(set(name_tokens + app_tokens))

            for term in tf.keys():
                self.doc_freqs[term] = self.doc_freqs.get(term, 0) + 1

        self.total_docs = len(self.tools)
        self.avg_doc_len = (sum(self.doc_lengths) / self.total_docs) if self.total_docs > 0 else 0.0

    def search(
        self,
        query: str,
        limit: int = 3,
        max_tokens: int = 800,
    ) -> Dict[str, Any]:
        """
        Search indexed tools matching query.
        Returns matching tool schemas with hard token cap.
        """
        if self.total_docs == 0:
            return {
                "found": 0,
                "tools": [],
                "formatted_schemas": "",
                "message": "No connected application tools are currently indexed.",
                "audit_meta": {"query": query, "returned_count": 0, "status": "NO_TOOLS_INDEXED"},
            }

        safe_query = self.sanitizer.sanitize_text(query)
        base_tokens = self.tokenize(safe_query)
        content_tokens = self.get_content_tokens(safe_query)

        if not base_tokens:
            return {
                "found": 0,
                "tools": [],
                "formatted_schemas": "",
                "message": "No matching tools found for query. Proceed with standard response.",
                "audit_meta": {"query": query, "returned_count": 0, "status": "NO_MATCH"},
            }

        # Expand query terms with weighted synonyms
        query_terms: Dict[str, float] = {}
        for t in base_tokens:
            query_terms[t] = query_terms.get(t, 0.0) + 1.0
            if t in DOMAIN_SYNONYMS:
                for syn, syn_weight in DOMAIN_SYNONYMS[t]:
                    query_terms[syn] = query_terms.get(syn, 0.0) + syn_weight

        k1 = 1.2
        b = 0.75

        scores: List[Tuple[float, int]] = []
        for idx, (doc_tf, doc_len, doc_name_terms) in enumerate(
            zip(self.doc_term_freqs, self.doc_lengths, self.doc_names)
        ):
            # Precision Gating: Count distinct matched base content tokens
            matched_base_terms = set()
            for ct in content_tokens:
                if ct in doc_tf:
                    matched_base_terms.add(ct)
                elif ct in DOMAIN_SYNONYMS:
                    for syn, _ in DOMAIN_SYNONYMS[ct]:
                        if syn in doc_tf:
                            matched_base_terms.add(ct)
                            break

            # If query has >= 3 content tokens, require co-occurrence of at least 2 terms
            # to reject false positives like "review my resume" or "committed to deadline"
            if len(content_tokens) >= 3 and len(matched_base_terms) < 2:
                continue

            # If query has 1-2 content tokens, require at least 1 match in tool name or app_id
            if len(content_tokens) < 3 and not (matched_base_terms & doc_name_terms):
                continue

            score = 0.0
            for term, q_weight in query_terms.items():
                if term in doc_tf:
                    f = doc_tf[term]
                    df = self.doc_freqs.get(term, 0)
                    # Smoothed Lucene-style IDF with baseline +1.0 for small corpora
                    idf = math.log(1.0 + (self.total_docs - df + 0.5) / (df + 0.5)) + 1.0
                    term_score = idf * (f * (k1 + 1.0)) / (f + k1 * (1.0 - b + b * (doc_len / (self.avg_doc_len or 1.0))))
                    score += term_score * q_weight

            if score >= self.MIN_SCORE_THRESHOLD:
                scores.append((score, idx))

        scores.sort(key=lambda x: x[0], reverse=True)
        top_matches = scores[:limit]

        if not top_matches:
            return {
                "found": 0,
                "tools": [],
                "formatted_schemas": "",
                "message": "No matching tools found for query. Proceed with standard response without invoking tools.",
                "audit_meta": {"query": query, "returned_count": 0, "status": "NO_MATCH"},
            }

        selected_tools = [self.tools[idx] for _, idx in top_matches]
        tool_keys = [t["key"] for t in selected_tools]

        # Format schemas compactly with hard token/character budget
        max_chars = int(max_tokens * 3.8)
        formatted_blocks = []
        current_len = 0

        header = "<connected_tools>\n"
        footer = "\n</connected_tools>"
        current_len += len(header) + len(footer)

        for t in selected_tools:
            t_key = t["key"]
            t_desc = t["description"][:120].strip()
            props = t["properties"]
            req = t["required"]

            params_desc = []
            for pk, pv in list(props.items())[:6]:
                ptype = pv.get("type", "string")
                is_req = "req" if pk in req else "opt"
                pdesc = pv.get("description", "").strip()[:60]
                if pdesc:
                    params_desc.append(f"{pk}: {ptype} ({is_req}) — {pdesc}")
                else:
                    params_desc.append(f"{pk}: {ptype} ({is_req})")

            params_str = "; ".join(params_desc) if params_desc else "none"
            line = f"- `{t_key}`: {t_desc}\n  Arguments: {params_str}"

            if current_len + len(line) + 2 <= max_chars:
                formatted_blocks.append(line)
                current_len += len(line) + 2
            else:
                compact_line = f"- `{t_key}`: {t_desc}"
                if current_len + len(compact_line) + 2 <= max_chars:
                    formatted_blocks.append(compact_line)
                    current_len += len(compact_line) + 2
                break

        formatted_schemas = header + "\n".join(formatted_blocks) + footer

        return {
            "found": len(selected_tools),
            "tools": tool_keys,
            "formatted_schemas": formatted_schemas,
            "results": selected_tools,
            "audit_meta": {
                "query": query,
                "returned_count": len(selected_tools),
                "returned_tools": tool_keys,
                "status": "MATCHED",
            },
        }
