import json
import logging
from decimal import Decimal
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

from db.connections import get_state_db

logger = logging.getLogger(__name__)

# Default quote freshness window: 15 minutes (Section 7.1)
DEFAULT_QUOTE_VALIDITY_SEC = 900


def is_fact_stale(valid_until_str: Optional[str], observed_at_str: str) -> bool:
    now = datetime.now(timezone.utc)
    if valid_until_str:
        try:
            valid_dt = datetime.fromisoformat(valid_until_str.replace("Z", "+00:00"))
            return now > valid_dt
        except Exception:
            pass

    try:
        observed_dt = datetime.fromisoformat(observed_at_str.replace("Z", "+00:00"))
        age = (now - observed_dt).total_seconds()
        return age > DEFAULT_QUOTE_VALIDITY_SEC
    except Exception:
        return False


def finance_summary_view(user_id: str = "default_user") -> Dict[str, Any]:
    """
    Section 7.5: finance_summary_view
    Computes accounts, holdings, and derived portfolio values at READ time.
    Agents never read the facts table directly.
    Carries as_of = oldest input, and a STALE flag if any quote expired.
    """
    conn = get_state_db()
    try:
        # 1. Fetch active transactions
        tx_rows = conn.execute(
            """
            SELECT entity_id, attribute, value_json, observed_at
            FROM facts
            WHERE entity_type = 'TRANSACTION' AND status = 'active'
            ORDER BY observed_at ASC
            """
        ).fetchall()

        # Compute holdings from transactions (Section 7.1: holdings are DERIVED)
        holdings_qty: Dict[str, Decimal] = {}
        holdings_cost: Dict[str, Decimal] = {}
        oldest_as_of = None

        for row in tx_rows:
            obs = row["observed_at"]
            if oldest_as_of is None or obs < oldest_as_of:
                oldest_as_of = obs

            val = json.loads(row["value_json"])
            symbol = val.get("instrument_symbol", "UNKNOWN")
            qty = Decimal(str(val.get("quantity", 0)))
            price_dec = Decimal(str(val.get("price_decimal", "0.00")))

            holdings_qty[symbol] = holdings_qty.get(symbol, Decimal(0)) + qty
            cost_basis = holdings_cost.get(symbol, Decimal(0)) + (qty * price_dec)
            holdings_cost[symbol] = cost_basis

        # 2. Fetch latest active prices for instruments
        price_rows = conn.execute(
            """
            SELECT entity_id, value_json, observed_at, valid_until
            FROM facts
            WHERE entity_type = 'INSTRUMENT' AND attribute = 'last_price' AND status = 'active'
            """
        ).fetchall()

        prices: Dict[str, Decimal] = {}
        has_stale_input = False

        for row in price_rows:
            symbol = row["entity_id"]
            val = json.loads(row["value_json"])
            price = Decimal(str(val.get("amount_decimal", "0.00")))
            prices[symbol] = price

            if is_fact_stale(row["valid_until"], row["observed_at"]):
                has_stale_input = True

        # 3. Calculate derived total value and gain/loss
        total_market_value = Decimal("0.00")
        holdings_list = []

        for symbol, qty in holdings_qty.items():
            if qty > 0:
                current_price = prices.get(symbol, Decimal("0.00"))
                mkt_val = qty * current_price
                total_market_value += mkt_val

                holdings_list.append({
                    "instrument": symbol,
                    "quantity": str(qty),
                    "current_price": str(current_price),
                    "market_value": str(mkt_val),
                })

        return {
            "user_id": user_id,
            "holdings": holdings_list,
            "total_portfolio_value": str(total_market_value),
            "currency": "USD",
            "as_of": oldest_as_of or datetime.now(timezone.utc).isoformat(),
            "stale": has_stale_input,
        }
    finally:
        conn.close()


def market_view(symbols: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """
    Section 7.5: market_view
    Instruments with last price, as_of, and staleness flag.
    """
    conn = get_state_db()
    try:
        query = """
            SELECT entity_id, value_json, observed_at, valid_until, tier
            FROM facts
            WHERE entity_type = 'INSTRUMENT' AND attribute = 'last_price' AND status = 'active'
        """
        rows = conn.execute(query).fetchall()

        results = []
        for row in rows:
            sym = row["entity_id"]
            if symbols and sym not in symbols:
                continue

            val = json.loads(row["value_json"])
            stale = is_fact_stale(row["valid_until"], row["observed_at"])
            results.append({
                "symbol": sym,
                "tier": row["tier"],
                "price": val.get("amount_decimal", "0.00"),
                "currency": val.get("currency", "USD"),
                "as_of": row["observed_at"],
                "stale": stale,
                "label": f"[{row['tier']} | {'STALE' if stale else 'fresh'}] Instrument {sym} price {val.get('amount_decimal')}",
            })
        return results
    finally:
        conn.close()


def extraction_view(statement_hash: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Section 7.5: extraction_view
    Statement and document metadata plus extraction requirements.
    """
    conn = get_state_db()
    try:
        rows = conn.execute(
            """
            SELECT entity_id, value_json, observed_at, tier
            FROM facts
            WHERE entity_type = 'STATEMENT' AND status = 'active'
            """
        ).fetchall()

        results = []
        for row in rows:
            val = json.loads(row["value_json"])
            results.append({
                "statement_id": row["entity_id"],
                "tier": row["tier"],
                "file_hash": val.get("file_hash"),
                "institution": val.get("institution"),
                "period": val.get("period"),
                "imported_at": row["observed_at"],
            })
        return results
    finally:
        conn.close()
