import uuid
import json
import hashlib
import logging
import html
from datetime import datetime, timezone
from typing import Optional
import chromadb
from db.connections import get_knowledge_db

logger = logging.getLogger(__name__)

AUTHORITY_WEIGHTS = {
    "OFFICIAL_SPEC": 1.00,
    "OFFICIAL_DOCS": 0.95,
    "MAINTAINER_REPO": 0.90,
    "PEER_REVIEWED": 0.80,
    "COMMUNITY": 0.50,
    "UNVERIFIED": 0.20,
}


class MemoryTool:
    """
    Read/write to the knowledge layer.
    SQLite is the source of truth. ChromaDB is a disposable index.
    If Chroma is corrupted it can be fully rebuilt from SQLite canonical_documents.
    Retrieved content is always tagged as untrusted — never treated as instructions.
    """

    def __init__(self, chroma_path: str = "./data/chroma_db"):
        self.chroma_client = chromadb.PersistentClient(path=chroma_path)
        self._collection = None

    def _get_collection(self) -> chromadb.Collection:
        if self._collection is None:
            conn = get_knowledge_db()
            try:
                row = conn.execute(
                    "SELECT collection_name FROM active_index_pointer WHERE id = 1"
                ).fetchone()
                name = row["collection_name"] if row else "sentinel_knowledge_v1"
            finally:
                conn.close()
            self._collection = self.chroma_client.get_or_create_collection(name)
        return self._collection

    def ingest(
        self,
        source_uri: str,
        domain: str,
        raw_content: str,
        authority_level: str = "UNVERIFIED",
        supersedes_id: Optional[str] = None,
    ) -> str:
        document_id = str(uuid.uuid4())
        doc_hash = hashlib.sha256(raw_content.encode()).hexdigest()
        embedding_config_hash = hashlib.sha256(b"nomic-embed-text-v1.5_768").hexdigest()
        now = datetime.now(timezone.utc).isoformat()

        conn = get_knowledge_db()
        try:
            # Mark superseded document
            if supersedes_id:
                conn.execute(
                    "UPDATE canonical_documents SET index_status = 'SUPERSEDED', valid_until = ? WHERE document_id = ?",
                    (now, supersedes_id),
                )

            conn.execute(
                """
                INSERT INTO canonical_documents (
                    document_id, source_uri, domain, authority_level,
                    raw_content, document_hash, embedding_config_hash,
                    valid_from, supersedes_document_id, index_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING')
                """,
                (document_id, source_uri, domain, authority_level,
                 raw_content, doc_hash, embedding_config_hash, now, supersedes_id),
            )
            conn.execute(
                "UPDATE canonical_documents SET index_status = 'INDEXING' WHERE document_id = ?",
                (document_id,),
            )
            conn.commit()
        finally:
            conn.close()

        try:
            collection = self._get_collection()
            chunks = self._chunk_text(raw_content)
            for i, chunk in enumerate(chunks):
                chunk_hash = hashlib.sha256(chunk.encode()).hexdigest()
                chunk_id = hashlib.sha256(f"{doc_hash}:{i}:{chunk_hash}".encode()).hexdigest()
                collection.upsert(
                    ids=[chunk_id],
                    documents=[chunk],
                    metadatas=[{
                        "document_id": document_id,
                        "document_hash": doc_hash,
                        "chunk_hash": chunk_hash,
                        "domain": domain,
                        "authority_level": authority_level,
                        "source_uri": source_uri,
                        "chunk_index": i,
                        "ingested_at": now,
                    }],
                )

            conn = get_knowledge_db()
            try:
                conn.execute(
                "UPDATE canonical_documents SET index_status = 'INDEXED', index_error = NULL WHERE document_id = ?",
                    (document_id,),
                )
                conn.commit()
            finally:
                conn.close()

            logger.info(f"Ingested document {document_id} ({len(chunks)} chunks)")
            return document_id

        except Exception as e:
            conn = get_knowledge_db()
            try:
                conn.execute(
                    "UPDATE canonical_documents SET index_status = 'FAILED', index_error = ? WHERE document_id = ?",
                    (str(e), document_id),
                )
                conn.commit()
            finally:
                conn.close()
            raise

    def retrieve(self, query: str, domain: Optional[str] = None, top_k: int = 5) -> str:
        """
        Composite scoring: relevance + authority weight + recency.
        Returns content wrapped in untrusted context tags.
        Retrieved content NEVER authorizes tool execution.
        """
        collection = self._get_collection()
        where = {"domain": domain} if domain else None

        try:
            results = collection.query(
                query_texts=[query],
                n_results=min(top_k * 5, 50),
                where=where,
            )
        except Exception as e:
            logger.error(f"ChromaDB query failed: {e}")
            return "<untrusted_retrieved_context></untrusted_retrieved_context>"

        if not results["documents"] or not results["documents"][0]:
            return "<untrusted_retrieved_context></untrusted_retrieved_context>"

        scored = []
        conn = get_knowledge_db()
        try:
            active_docs = {
                row["document_id"]: row
                for row in conn.execute(
                    """
                    SELECT document_id, valid_from, valid_until, document_hash
                    FROM canonical_documents
                    WHERE index_status = 'INDEXED' AND valid_until IS NULL
                    """
                ).fetchall()
            }
        finally:
            conn.close()

        for doc, meta, distance in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            canonical = active_docs.get(meta.get("document_id"))
            if not canonical:
                continue
            if canonical["document_hash"] != meta.get("document_hash"):
                continue
            relevance = 1.0 - min(distance, 1.0)
            authority = AUTHORITY_WEIGHTS.get(meta.get("authority_level", "UNVERIFIED"), 0.2)
            score = min((relevance * 0.6) + (authority * 0.4), 1.0)
            scored.append((score, doc, meta))

        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[:top_k]

        parts = []
        for score, doc, meta in top:
            safe_source = html.escape(str(meta.get("source_uri", "unknown")), quote=True)
            safe_authority = html.escape(str(meta.get("authority_level", "UNVERIFIED")), quote=True)
            safe_doc = html.escape(doc, quote=True)
            parts.append(
                f"[Source: {safe_source} | "
                f"Authority: {safe_authority} | "
                f"Score: {score:.2f}]\n{safe_doc}"
            )

        content = "\n\n---\n\n".join(parts)
        return f"<untrusted_retrieved_context>\n{content}\n</untrusted_retrieved_context>"

    def rebuild_index(self) -> bool:
        """Rebuild ChromaDB from SQLite canonical_documents. Called on corruption."""
        logger.warning("Rebuilding ChromaDB index from SQLite...")
        conn = get_knowledge_db()
        try:
            rows = conn.execute(
                "SELECT * FROM canonical_documents WHERE index_status = 'INDEXED' AND valid_until IS NULL"
            ).fetchall()
        finally:
            conn.close()

        new_name = f"sentinel_knowledge_rebuild_{uuid.uuid4().hex[:8]}"
        new_collection = self.chroma_client.get_or_create_collection(new_name)

        for row in rows:
            doc_hash = hashlib.sha256(row["raw_content"].encode()).hexdigest()
            if doc_hash != row["document_hash"]:
                raise ValueError(f"Document hash mismatch during rebuild: {row['document_id']}")
            chunks = self._chunk_text(row["raw_content"])
            for i, chunk in enumerate(chunks):
                chunk_hash = hashlib.sha256(chunk.encode()).hexdigest()
                chunk_id = hashlib.sha256(f"{row['document_hash']}:{i}:{chunk_hash}".encode()).hexdigest()
                new_collection.upsert(
                    ids=[chunk_id],
                    documents=[chunk],
                    metadatas=[{
                        "document_id": row["document_id"],
                        "document_hash": row["document_hash"],
                        "chunk_hash": chunk_hash,
                        "domain": row["domain"],
                        "authority_level": row["authority_level"],
                        "source_uri": row["source_uri"],
                        "chunk_index": i,
                    }],
                )

        conn = get_knowledge_db()
        try:
            conn.execute(
                "UPDATE active_index_pointer SET collection_name = ?, activated_at = ? WHERE id = 1",
                (new_name, datetime.now(timezone.utc).isoformat()),
            )
            conn.commit()
        finally:
            conn.close()

        self._collection = new_collection
        logger.info(f"Index rebuilt into collection: {new_name}")
        return True

    def _chunk_text(self, text: str, chunk_size: int = 512, overlap: int = 64) -> list:
        words = text.split()
        chunks = []
        i = 0
        while i < len(words):
            chunk = " ".join(words[i:i + chunk_size])
            chunks.append(chunk)
            i += chunk_size - overlap
        return chunks if chunks else [text]
