"""DimensionResolver — self-populating, self-correcting dimension cache.

Resolution order for any unstated dimension:
1. User stated it explicitly → caller never reaches this module.
2. ACTIVE cache hit → reuse, bump times_used/last_used_at.
3. Cache miss, model confidence >= CONFIDENCE_THRESHOLD → use model value, cache it.
4. Cache miss, confidence < threshold → one bounded web_search call (max
   MAX_WEB_LOOKUPS_PER_TASK per task), cache result as 'web_verified'.
5. Fell through → use model value anyway, log as 'prior_knowledge_low_confidence'.

Every resolution is logged to audit.sqlite audit_logs, same pattern as ToolGateway.

Invalidation:
  Call invalidate(decision_key, reason) when assembly verification fails for a
  size-driven reason. Marks the entry SUSPECT so the next resolve() re-derives
  rather than silently reusing a bad value.

User correction:
  Call store_user_correction(key, new_value) to overwrite a cached entry with
  source='user_stated' and confidence=1.0 — highest priority, never re-derived.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional

from db.connections import get_audit_db, get_knowledge_db

logger = logging.getLogger(__name__)

CONFIDENCE_THRESHOLD = 0.6
MAX_WEB_LOOKUPS_PER_TASK = 2  # same discipline as search_tools loop cap


def _normalize_key(category: str, descriptor: str, dimension_name: str) -> str:
    cat  = re.sub(r"[^a-z0-9_]", "", category.lower().strip().replace(" ", "_"))
    desc = re.sub(r"[^a-z0-9_]", "", (descriptor or "").lower().strip().replace(" ", "_"))
    dim  = dimension_name.lower().strip()
    return f"{cat}|{desc}|{dim}"


@dataclass
class DimensionDecision:
    value: float
    source: str
    confidence: float
    decision_key: str
    from_cache: bool


class DimensionResolver:
    def __init__(self, web_search_fn: Optional[Callable] = None):
        # web_search_fn: async callable(query: str) -> str, injected so this
        # module doesn't import the web_search tool directly (testable, and
        # keeps the bounded-call-count enforcement at the caller's level).
        self._web_search_fn = web_search_fn

    async def resolve(
        self,
        task_id: str,
        category: str,
        descriptor: str,
        dimension_name: str,
        model_value: float,
        model_confidence: float,
        web_lookups_used_this_task: int = 0,
    ) -> DimensionDecision:
        key = _normalize_key(category, descriptor, dimension_name)

        # 1. Cache hit
        cached = self._get_active(key)
        if cached:
            self._bump_usage(key)
            self._log_audit(task_id, "DIMENSION_RESOLVED", {
                "decision_key": key, "source": "cache",
                "value": cached["value"], "confidence": cached["confidence"],
            })
            return DimensionDecision(
                value=cached["value"], source=cached["source"],
                confidence=cached["confidence"], decision_key=key, from_cache=True,
            )

        # 2. High-confidence model value
        if model_confidence >= CONFIDENCE_THRESHOLD:
            self._store(key, category, descriptor, dimension_name,
                        model_value, model_confidence, "prior_knowledge")
            self._log_audit(task_id, "DIMENSION_RESOLVED", {
                "decision_key": key, "source": "prior_knowledge",
                "value": model_value, "confidence": model_confidence,
            })
            return DimensionDecision(
                value=model_value, source="prior_knowledge",
                confidence=model_confidence, decision_key=key, from_cache=False,
            )

        # 3. Web lookup fallback
        if self._web_search_fn and web_lookups_used_this_task < MAX_WEB_LOOKUPS_PER_TASK:
            try:
                web_value = await self._web_lookup(category, descriptor, dimension_name)
                if web_value is not None:
                    self._store(key, category, descriptor, dimension_name,
                                web_value, 0.75, "web_verified")
                    self._log_audit(task_id, "DIMENSION_RESOLVED", {
                        "decision_key": key, "source": "web_verified", "value": web_value,
                    })
                    return DimensionDecision(
                        value=web_value, source="web_verified",
                        confidence=0.75, decision_key=key, from_cache=False,
                    )
            except Exception as e:
                logger.warning(f"Web dimension lookup failed for {key}: {e}")

        # 4. Low-confidence fallback — use model value but be honest about it
        self._store(key, category, descriptor, dimension_name,
                    model_value, model_confidence, "prior_knowledge_low_confidence")
        self._log_audit(task_id, "DIMENSION_RESOLVED", {
            "decision_key": key, "source": "prior_knowledge_low_confidence",
            "value": model_value, "confidence": model_confidence,
        })
        return DimensionDecision(
            value=model_value, source="prior_knowledge_low_confidence",
            confidence=model_confidence, decision_key=key, from_cache=False,
        )

    async def _web_lookup(
        self, category: str, descriptor: str, dimension_name: str
    ) -> Optional[float]:
        query = (
            f"typical {descriptor} {category} "
            f"{dimension_name.replace('_cm', '').replace('_', ' ')} cm dimensions"
        )
        result_text = await self._web_search_fn(query)
        match = re.search(r"(\d+(?:\.\d+)?)\s*cm", result_text or "")
        return float(match.group(1)) if match else None

    def invalidate(self, decision_key: str, reason: str) -> None:
        """Mark a cached entry SUSPECT so it is re-derived next time instead of
        silently reused. Called when assembly verification fails for a size-driven reason."""
        conn = get_knowledge_db()
        try:
            conn.execute(
                "UPDATE object_dimension_decisions SET status = 'SUSPECT' WHERE decision_key = ?",
                (decision_key,),
            )
            conn.commit()
            logger.warning(f"Dimension decision '{decision_key}' marked SUSPECT: {reason}")
        finally:
            conn.close()

    def store_user_correction(
        self, category: str, descriptor: str, dimension_name: str, new_value: float
    ) -> str:
        """Overwrite a cached entry with a user-stated value (confidence=1.0).
        Returns the decision_key that was updated."""
        key = _normalize_key(category, descriptor, dimension_name)
        self._store(key, category, descriptor, dimension_name, new_value, 1.0, "user_stated")
        logger.info(f"User correction stored for '{key}': {new_value}")
        return key

    # ------------------------------------------------------------------
    # Internal DB helpers
    # ------------------------------------------------------------------

    def _get_active(self, key: str) -> Optional[dict]:
        conn = get_knowledge_db()
        try:
            row = conn.execute(
                "SELECT value, confidence, source FROM object_dimension_decisions "
                "WHERE decision_key = ? AND status = 'ACTIVE'",
                (key,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def _bump_usage(self, key: str) -> None:
        conn = get_knowledge_db()
        try:
            conn.execute(
                "UPDATE object_dimension_decisions "
                "SET times_used = times_used + 1, "
                "last_used_at = strftime('%Y-%m-%dT%H:%M:%SZ','now') "
                "WHERE decision_key = ?",
                (key,),
            )
            conn.commit()
        finally:
            conn.close()

    def _store(
        self,
        key: str,
        category: str,
        descriptor: str,
        dimension_name: str,
        value: float,
        confidence: float,
        source: str,
    ) -> None:
        conn = get_knowledge_db()
        try:
            conn.execute(
                """INSERT INTO object_dimension_decisions
                   (decision_key, category, descriptor, dimension_name,
                    value, confidence, source, times_used, last_used_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 1, strftime('%Y-%m-%dT%H:%M:%SZ','now'))
                   ON CONFLICT(decision_key) DO UPDATE SET
                     value      = excluded.value,
                     confidence = excluded.confidence,
                     source     = excluded.source,
                     status     = 'ACTIVE',
                     times_used = object_dimension_decisions.times_used + 1,
                     last_used_at = strftime('%Y-%m-%dT%H:%M:%SZ','now')""",
                (key, category, descriptor, dimension_name, value, confidence, source),
            )
            conn.commit()
        finally:
            conn.close()

    def _log_audit(self, task_id: str, action_type: str, factors: dict) -> None:
        try:
            conn = get_audit_db()
            try:
                conn.execute(
                    """INSERT INTO audit_logs
                       (log_id, run_id, task_id, step_id, who_actor,
                        action_type, tool_name, decision_summary, decision_factors, created_at)
                       VALUES (?, ?, ?, 'step_0', 'dimension_resolver',
                               ?, 'dimension_resolver', ?, ?, ?)""",
                    (
                        str(uuid.uuid4()),
                        f"run_{task_id}",
                        task_id,
                        action_type,
                        json.dumps({"action": action_type}, default=str),
                        json.dumps(factors, default=str),
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
                conn.commit()
            finally:
                conn.close()
        except Exception as e:
            logger.debug(f"DimensionResolver audit log failed: {e}")
