import os
import sys
import json
import pytest
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Ensure backend on sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from core.write_gate import WriteGate
from core.finance_views import finance_summary_view, market_view, extraction_view
from db.connections import get_state_db, initialize_all_databases


@pytest.fixture
def gate():
    initialize_all_databases()
    # Clean state tables before test run
    conn = get_state_db()
    conn.execute("DELETE FROM reviews")
    conn.execute("DELETE FROM events")
    conn.execute("DELETE FROM facts")
    conn.execute("DELETE FROM entities")
    conn.commit()
    conn.close()
    return WriteGate()


def test_statement_import_idempotent(gate):
    """
    Acceptance test (Section 7.7):
    Importing the same statement twice creates no duplicate facts.
    """
    file_hash = "sha256_statement_file_12345"
    tx_val = {
        "statement_ref": file_hash,
        "instrument_symbol": "AAPL",
        "date": "2026-09-01",
        "kind": "BUY",
        "quantity": 10,
        "price_decimal": "150.00",
        "amount_minor": 150000,
        "currency": "USD",
    }

    # First import -> COMMIT
    res1 = gate.propose_fact(
        entity_type="TRANSACTION",
        entity_id="tx_statement_001",
        attribute="trade",
        value_data=tx_val,
        tier="T0",
        source_kind="file",
        source_ref=file_hash,
        source_authority="OFFICIAL_STATEMENT",
        evidence_ref="artifact://stmt_pdf_1",
        author_agent="statement_parser",
    )
    assert res1["status"] == "COMMIT"
    assert res1["fact_id"] is not None

    # Re-importing identical statement payload -> COMMIT idempotent (no duplicate rows)
    res2 = gate.propose_fact(
        entity_type="TRANSACTION",
        entity_id="tx_statement_001",
        attribute="trade",
        value_data=tx_val,
        tier="T0",
        source_kind="file",
        source_ref=file_hash,
        source_authority="OFFICIAL_STATEMENT",
        evidence_ref="artifact://stmt_pdf_1",
        author_agent="statement_parser",
    )
    assert res2["status"] == "COMMIT"
    assert res2["fact_id"] == res1["fact_id"]  # Identical fact id!

    # Verify only 1 fact row exists
    conn = get_state_db()
    cnt = conn.execute("SELECT COUNT(*) FROM facts WHERE entity_id = 'tx_statement_001'").fetchone()[0]
    conn.close()
    assert cnt == 1


def test_manual_entry_conflict_opens_review(gate):
    """
    Acceptance test (Section 7.7):
    A manual entry that conflicts with an imported statement opens a review
    and does NOT overwrite the T0 fact.
    """
    # 1. Statement fact (T0) established
    res_t0 = gate.propose_fact(
        entity_type="ACCOUNT",
        entity_id="acc_9821",
        attribute="closing_balance",
        value_data={"amount_minor": 234000, "amount_decimal": "2340.00", "currency": "USD"},
        tier="T0",
        source_kind="file",
        source_ref="file_statement_september",
        source_authority="BANK_STATEMENT",
        evidence_ref="artifact://stmt_sept",
        author_agent="statement_parser",
    )
    assert res_t0["status"] == "COMMIT"

    # 2. Conflicting manual user entry (T1) proposing different balance
    res_t1 = gate.propose_fact(
        entity_type="ACCOUNT",
        entity_id="acc_9821",
        attribute="closing_balance",
        value_data={"amount_minor": 5000000, "amount_decimal": "50000.00", "currency": "USD"},
        tier="T1",
        source_kind="user",
        source_ref="user_1",
        source_authority="USER_MANUAL",
        evidence_ref="user_prompt_input",
        author_agent="endpoint_agent",
    )

    # Must open review and NOT commit/overwrite T0
    assert res_t1["status"] == "REVIEW"
    assert "conflict" in res_t1["reason"]

    # Verify T0 fact remains ACTIVE in facts table
    conn = get_state_db()
    active_row = conn.execute(
        "SELECT fact_id, tier, status FROM facts WHERE entity_id = 'acc_9821' AND status = 'active'"
    ).fetchone()
    review_row = conn.execute("SELECT * FROM reviews WHERE fact_id = ?", (res_t1["fact_id"],)).fetchone()
    conn.close()

    assert active_row["tier"] == "T0"
    assert active_row["fact_id"] == res_t0["fact_id"]
    assert review_row is not None


def test_absurd_quote_outlier_quarantined(gate):
    """
    Acceptance test (Section 7.7):
    A web quote 10x off the last value is held for review, not committed silently.
    """
    # 1. Normal price: $118.50
    gate.propose_fact(
        entity_type="INSTRUMENT",
        entity_id="NVDA",
        attribute="last_price",
        value_data={"amount_minor": 11850, "amount_decimal": "118.50", "currency": "USD"},
        tier="T2",
        source_kind="web",
        source_ref="api:yahoo",
        source_authority="MARKET_API",
        evidence_ref="http://api.market/nvda",
        author_agent="finance_tools",
    )

    # 2. Absurd surge quote: $1180.50 (10x / 900% jump)
    res_surge = gate.propose_fact(
        entity_type="INSTRUMENT",
        entity_id="NVDA",
        attribute="last_price",
        value_data={"amount_minor": 118050, "amount_decimal": "1180.50", "currency": "USD"},
        tier="T2",
        source_kind="web",
        source_ref="web:fake_quote",
        source_authority="COMMUNITY_WEB",
        evidence_ref="http://malicious.example/quote",
        author_agent="finance_tools",
    )

    assert res_surge["status"] == "REVIEW"
    assert "outlier_price_surge" in res_surge["reason"]


def test_stale_quote_flagged_in_view(gate):
    """
    Acceptance test (Section 7.7):
    A stale quote is presented with a STALE flag in views, never as current.
    """
    # Insert quote with expired validity window (observed 2 hours ago)
    stale_time = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    gate.propose_fact(
        entity_type="INSTRUMENT",
        entity_id="AAPL",
        attribute="last_price",
        value_data={"amount_minor": 22050, "amount_decimal": "220.50", "currency": "USD"},
        tier="T2",
        source_kind="web",
        source_ref="api:market",
        source_authority="FINANCE_API",
        evidence_ref="api_response_aapl",
        author_agent="finance_tools",
        observed_at=stale_time,
        valid_until=(datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
    )

    m_view = market_view(symbols=["AAPL"])
    assert len(m_view) == 1
    assert m_view[0]["stale"] is True
    assert "STALE" in m_view[0]["label"]


def test_derived_holdings_computed_at_read_time(gate):
    """
    Acceptance test (Section 7.7):
    Holdings and portfolio values are computed at READ time from transactions.
    """
    # 1. Buy 10 shares of MSFT @ $300
    gate.propose_fact(
        entity_type="TRANSACTION",
        entity_id="tx_01",
        attribute="trade",
        value_data={"instrument_symbol": "MSFT", "quantity": 10, "price_decimal": "300.00"},
        tier="T0",
        source_kind="file",
        source_ref="stmt_1",
        source_authority="STATEMENT",
        evidence_ref="stmt_ref_1",
        author_agent="parser",
    )

    # 2. Buy another 5 shares of MSFT @ $320
    gate.propose_fact(
        entity_type="TRANSACTION",
        entity_id="tx_02",
        attribute="trade",
        value_data={"instrument_symbol": "MSFT", "quantity": 5, "price_decimal": "320.00"},
        tier="T0",
        source_kind="file",
        source_ref="stmt_1",
        source_authority="STATEMENT",
        evidence_ref="stmt_ref_1",
        author_agent="parser",
    )

    # 3. Market price for MSFT is $350
    gate.propose_fact(
        entity_type="INSTRUMENT",
        entity_id="MSFT",
        attribute="last_price",
        value_data={"amount_minor": 35000, "amount_decimal": "350.00", "currency": "USD"},
        tier="T2",
        source_kind="web",
        source_ref="market_feed",
        source_authority="FEED",
        evidence_ref="feed_1",
        author_agent="finance_tools",
    )

    # View computes derived holdings: total 15 shares, portfolio market value = 15 * 350 = $5,250.00
    summary = finance_summary_view()
    assert len(summary["holdings"]) == 1
    msft_holding = summary["holdings"][0]
    assert msft_holding["instrument"] == "MSFT"
    assert msft_holding["quantity"] == "15"
    assert msft_holding["market_value"] == "5250.00"
    assert summary["total_portfolio_value"] == "5250.00"


def test_no_direct_facts_table_access_by_agents():
    """
    Acceptance test (Section 7.7):
    Enforced by AST test: no agent code in backend/agents reads the facts table directly.
    """
    import ast
    agents_dir = backend_dir / "agents"
    for py_file in agents_dir.glob("*.py"):
        code = py_file.read_text(encoding="utf-8")
        assert "SELECT" not in code or "FROM facts" not in code, (
            f"VIOLATION: Agent file {py_file.name} queries 'facts' table directly! Agents must use views."
        )
        assert "get_state_db" not in code, (
            f"VIOLATION: Agent file {py_file.name} accesses get_state_db() directly!"
        )
