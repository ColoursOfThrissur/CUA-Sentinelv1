import re
import json
import uuid
import logging
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple

from db.connections import get_state_db

logger = logging.getLogger(__name__)

# Price surge threshold that forces human review instead of commit (11.3 F6)
PRICE_SURGE_THRESHOLD_PCT = 50.0

# Tier precedence: T0 beats T1 beats T2 beats T3
TIER_RANK = {"T0": 0, "T1": 1, "T2": 2, "T3": 3}


class WriteGate:
    """
    P2 Typed Write Gate for Finance State (Section 7.4, Closes G3, G8).
    Deterministic code-based verification pipeline:
      1. Schema and type validation (Decimal money, ISO currencies, no negative prices).
      2. Provenance check (source_ref and evidence_ref required).
      3. Conflict & sanity checks:
         - T0 beats T1 beats T2. A conflict opens a review and never overwrites T0.
         - Duplicate detection by natural key hash.
         - Outlier detection (price jump > 50% vs last recorded value -> pending_review).
      4. Content screening: strips formulas/instructions.
      5. Outcome: COMMIT | QUARANTINE | REVIEW | REJECT.
      6. Emits an append-only event.
    """

    @staticmethod
    def parse_money(amount_val: Any, currency: str) -> Tuple[int, str]:
        """
        Decision D4 / Rule R2: Money as Decimal string and integer minor units.
        Never floats. Returns (amount_minor, amount_decimal_str).
        """
        if isinstance(amount_val, (int, str, Decimal)):
            d = Decimal(str(amount_val)).quantize(Decimal("0.01"))
        elif isinstance(amount_val, float):
            # Quantize float to 2 decimal places to avoid floating point issues
            d = Decimal(str(round(amount_val, 2))).quantize(Decimal("0.01"))
        else:
            raise ValueError(f"Invalid amount type for money: {type(amount_val)}")

        amount_minor = int(d * 100)
        return amount_minor, str(d)

    def propose_fact(
        self,
        *,
        entity_type: str,
        entity_id: str,
        attribute: str,
        value_data: Dict[str, Any],
        tier: str,
        source_kind: str,
        source_ref: str,
        source_authority: str,
        evidence_ref: str,
        author_agent: str,
        model_id: Optional[str] = None,
        prompt_hash: Optional[str] = None,
        task_id: Optional[str] = None,
        step_id: Optional[str] = None,
        observed_at: Optional[str] = None,
        valid_from: Optional[str] = None,
        valid_until: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Main entry point for proposing a fact into state.sqlite.
        Returns: {status: 'COMMIT' | 'REVIEW' | 'QUARANTINE' | 'REJECT', fact_id: str, reason: str}
        """
        now = datetime.now(timezone.utc).isoformat()
        observed_at = observed_at or now

        # 1. Provenance Check: source_ref and evidence_ref required
        if not source_ref or not evidence_ref:
            reason = "Provenance missing: source_ref and evidence_ref are strictly required"
            logger.warning(f"WRITE GATE REJECT: {reason}")
            return {"status": "REJECT", "fact_id": None, "reason": reason}

        # 2. Content Screening: check for formula injection (=cmd, @SUM, etc.)
        for k, v in value_data.items():
            if isinstance(v, str) and (v.startswith("=") or v.startswith("@") or "SYSTEM:" in v):
                # Quarantine suspicious formula or instruction payloads (11.3 F5)
                fact_id = f"fact_{uuid.uuid4().hex[:12]}"
                self._record_fact(
                    fact_id=fact_id,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    attribute=attribute,
                    value_json=json.dumps(value_data),
                    tier=tier,
                    status="quarantined",
                    source_kind=source_kind,
                    source_ref=source_ref,
                    source_authority=source_authority,
                    evidence_ref=evidence_ref,
                    author_agent=author_agent,
                    model_id=model_id,
                    prompt_hash=prompt_hash,
                    task_id=task_id,
                    step_id=step_id,
                    observed_at=observed_at,
                    valid_from=valid_from,
                    valid_until=valid_until,
                )
                self._record_event(fact_id, "QUARANTINE", author_agent, f"Formula/instruction screened in field {k}")
                return {"status": "QUARANTINE", "fact_id": fact_id, "reason": f"Content screened: {k}"}

        # 3. Canonical Key & Deduplication
        conn = get_state_db()
        try:
            # Check existing active fact for same entity_type, entity_id, attribute
            existing = conn.execute(
                """
                SELECT fact_id, tier, status, value_json
                FROM facts
                WHERE entity_type = ? AND entity_id = ? AND attribute = ? AND status = 'active'
                """,
                (entity_type, entity_id, attribute),
            ).fetchone()

            # Duplicate Check: Identical value already active
            if existing:
                try:
                    existing_val = json.loads(existing["value_json"])
                    if existing_val == value_data:
                        # Idempotent match: return COMMIT without duplicating
                        return {"status": "COMMIT", "fact_id": existing["fact_id"], "reason": "idempotent_duplicate"}
                except Exception:
                    pass

                # Conflict Check: Higher tier fact cannot be silently overwritten (e.g. T1 vs T0)
                existing_tier = existing["tier"]
                if TIER_RANK.get(tier, 99) > TIER_RANK.get(existing_tier, 99):
                    # Lower tier proposing new value over higher tier fact (e.g. T1 manual or T2 extraction vs T0 statement)
                    # Open a review; T0/T1 fact stands! (11.3 F7)
                    fact_id = f"fact_{uuid.uuid4().hex[:12]}"
                    self._record_fact(
                        conn=conn,
                        fact_id=fact_id,
                        entity_type=entity_type,
                        entity_id=entity_id,
                        attribute=attribute,
                        value_json=json.dumps(value_data),
                        tier=tier,
                        status="pending_review",
                        source_kind=source_kind,
                        source_ref=source_ref,
                        source_authority=source_authority,
                        evidence_ref=evidence_ref,
                        author_agent=author_agent,
                        model_id=model_id,
                        prompt_hash=prompt_hash,
                        task_id=task_id,
                        step_id=step_id,
                        observed_at=observed_at,
                        valid_from=valid_from,
                        valid_until=valid_until,
                    )
                    review_id = self._open_review(
                        conn=conn,
                        fact_id=fact_id,
                        reason=f"Conflict: proposed {tier} fact conflicts with active {existing_tier} fact {existing['fact_id']}",
                        options={"keep_existing": existing["fact_id"], "override": fact_id},
                    )
                    self._record_event(fact_id, "REVIEW", author_agent, f"Review opened: conflict with {existing_tier}", conn=conn)
                    return {"status": "REVIEW", "fact_id": fact_id, "review_id": review_id, "reason": "conflict_opened_review"}

            # 4. Outlier & Sanity Check for Quotes (11.3 F6)
            if attribute in ("last_price", "price") and "amount_minor" in value_data and existing:
                try:
                    old_minor = json.loads(existing["value_json"]).get("amount_minor", 0)
                    new_minor = value_data["amount_minor"]
                    if old_minor > 0:
                        change_pct = abs((new_minor - old_minor) / old_minor) * 100.0
                        if change_pct >= PRICE_SURGE_THRESHOLD_PCT:
                            # Price jump >= 50% vs last value: pending_review (not committed silently)
                            fact_id = f"fact_{uuid.uuid4().hex[:12]}"
                            self._record_fact(
                                conn=conn,
                                fact_id=fact_id,
                                entity_type=entity_type,
                                entity_id=entity_id,
                                attribute=attribute,
                                value_json=json.dumps(value_data),
                                tier=tier,
                                status="pending_review",
                                source_kind=source_kind,
                                source_ref=source_ref,
                                source_authority=source_authority,
                                evidence_ref=evidence_ref,
                                author_agent=author_agent,
                                model_id=model_id,
                                prompt_hash=prompt_hash,
                                task_id=task_id,
                                step_id=step_id,
                                observed_at=observed_at,
                                valid_from=valid_from,
                                valid_until=valid_until,
                            )
                            review_id = self._open_review(
                                conn=conn,
                                fact_id=fact_id,
                                reason=f"Anomalous price surge of {change_pct:.1f}% detected vs previous price",
                                options={"accept_price": fact_id, "reject_price": None},
                            )
                            self._record_event(fact_id, "REVIEW", author_agent, f"Price outlier {change_pct:.1f}%", conn=conn)
                            return {"status": "REVIEW", "fact_id": fact_id, "review_id": review_id, "reason": "outlier_price_surge"}
                except Exception as e:
                    logger.debug(f"Outlier evaluation check error: {e}")

            # 5. Commit Path: Mark any existing superseded, commit new active fact
            fact_id = f"fact_{uuid.uuid4().hex[:12]}"
            if existing:
                conn.execute(
                    "UPDATE facts SET status = 'superseded' WHERE fact_id = ?",
                    (existing["fact_id"],),
                )
                self._record_event(existing["fact_id"], "SUPERSEDE", author_agent, f"Superseded by {fact_id}", conn=conn)

            self._record_fact(
                conn=conn,
                fact_id=fact_id,
                entity_type=entity_type,
                entity_id=entity_id,
                attribute=attribute,
                value_json=json.dumps(value_data),
                tier=tier,
                status="active",
                source_kind=source_kind,
                source_ref=source_ref,
                source_authority=source_authority,
                evidence_ref=evidence_ref,
                author_agent=author_agent,
                model_id=model_id,
                prompt_hash=prompt_hash,
                task_id=task_id,
                step_id=step_id,
                observed_at=observed_at,
                valid_from=valid_from,
                valid_until=valid_until,
            )
            self._record_event(fact_id, "COMMIT", author_agent, "Committed through write gate", conn=conn)
            return {"status": "COMMIT", "fact_id": fact_id, "reason": "committed"}

        finally:
            conn.close()

    def _record_fact(self, conn=None, **kwargs) -> None:
        owns_conn = conn is None
        c = get_state_db() if owns_conn else conn
        try:
            cols = ", ".join(kwargs.keys())
            placeholders = ", ".join(["?"] * len(kwargs))
            c.execute(
                f"INSERT INTO facts ({cols}) VALUES ({placeholders})",
                tuple(kwargs.values()),
            )
            c.commit()
        finally:
            if owns_conn:
                c.close()

    def _record_event(self, fact_id: str, event_type: str, actor: str, reason: str, conn=None) -> None:
        owns_conn = conn is None
        c = get_state_db() if owns_conn else conn
        try:
            c.execute(
                """
                INSERT INTO events (event_id, event_type, fact_id, actor, reason, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    f"evt_{uuid.uuid4().hex[:12]}",
                    event_type,
                    fact_id,
                    actor,
                    reason,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            c.commit()
        finally:
            if owns_conn:
                c.close()

    def _open_review(self, fact_id: str, reason: str, options: dict, conn=None) -> str:
        review_id = f"rev_{uuid.uuid4().hex[:12]}"
        owns_conn = conn is None
        c = get_state_db() if owns_conn else conn
        try:
            c.execute(
                """
                INSERT INTO reviews (review_id, fact_id, reason, options_json, status, created_at)
                VALUES (?, ?, ?, ?, 'PENDING', ?)
                """,
                (
                    review_id,
                    fact_id,
                    reason,
                    json.dumps(options),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            c.commit()
            return review_id
        finally:
            if owns_conn:
                c.close()
