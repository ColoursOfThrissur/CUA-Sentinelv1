import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from pydantic import BaseModel

from tools.finance_tools import FinanceTools

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/finance", tags=["finance"])
finance_tools = FinanceTools()


class AssetPayload(BaseModel):
    symbol: str
    asset_type: str  # STOCK, CRYPTO, COMMODITY, FOREX
    name: str
    quantity: float
    buy_price: float
    alert_threshold_pct: float = 5.0
    notes: Optional[str] = ""


class DematImportPayload(BaseModel):
    csv_text: str


import re


def parse_text_lines(text: str) -> int:
    lines = text.strip().splitlines()
    imported_count = 0
    for line in lines:
        if not line.strip():
            continue
        # Support tabs \t (Excel copy-paste), commas ,, and semicolons ;
        if "\t" in line:
            parts = [p.strip().strip('"') for p in line.split("\t")]
        elif ";" in line:
            parts = [p.strip().strip('"') for p in line.split(";")]
        else:
            parts = [p.strip().strip('"') for p in line.split(",")]

        if len(parts) >= 2:
            raw_sym = parts[0].upper()
            if raw_sym.lower() in ["symbol", "ticker", "instrument", "name", "total", "subtotal", "particulars"]:
                continue

            clean_sym = re.sub(r'[^A-Z0-9.\-]', '', raw_sym.split()[0])
            if not clean_sym:
                continue

            try:
                qty_str = re.sub(r'[^0-9.]', '', parts[1])
                qty = float(qty_str) if qty_str else 1.0

                price_str = re.sub(r'[^0-9.]', '', parts[2]) if len(parts) > 2 else "0"
                buy_p = float(price_str) if price_str else 0.0

                name = parts[3] if len(parts) > 3 else clean_sym
                finance_tools.upsert_asset(
                    symbol=clean_sym,
                    asset_type="STOCK",
                    name=name,
                    quantity=qty,
                    buy_price=buy_p,
                    alert_threshold_pct=5.0,
                    notes="Imported via Demat Statement"
                )
                imported_count += 1
            except Exception:
                continue

    return imported_count


@router.post("/portfolio/import-file")
async def import_demat_file(file: UploadFile = File(...)) -> Dict[str, Any]:
    filename = file.filename.lower()
    contents = await file.read()

    if filename.endswith(".xlsx") or filename.endswith(".xls"):
        count = finance_tools.import_excel_holdings(contents)
        return {"status": "SUCCESS", "imported": count, "filename": file.filename}

    # Fallback to text / CSV parsing
    text = contents.decode("utf-8", errors="ignore")
    count = parse_text_lines(text)
    return {"status": "SUCCESS", "imported": count, "filename": file.filename}


@router.post("/portfolio/import-csv")
def import_demat_csv(payload: DematImportPayload) -> Dict[str, Any]:
    count = parse_text_lines(payload.csv_text)
    return {"status": "SUCCESS", "imported": count}


@router.get("/portfolio")
def get_portfolio() -> List[Dict[str, Any]]:
    return finance_tools.get_portfolio()


@router.post("/portfolio")
def upsert_asset(payload: AssetPayload) -> Dict[str, Any]:
    return finance_tools.upsert_asset(
        symbol=payload.symbol,
        asset_type=payload.asset_type,
        name=payload.name,
        quantity=payload.quantity,
        buy_price=payload.buy_price,
        alert_threshold_pct=payload.alert_threshold_pct,
        notes=payload.notes or "",
    )


@router.delete("/portfolio/clear-all")
def clear_all_portfolio() -> Dict[str, Any]:
    success = finance_tools.clear_portfolio()
    return {"status": "SUCCESS", "cleared": success}


@router.delete("/portfolio/{symbol}")
def delete_asset(symbol: str) -> Dict[str, Any]:
    success = finance_tools.delete_asset(symbol)
    return {"symbol": symbol, "deleted": success}


@router.get("/quote/{symbol}")
async def get_quote(symbol: str) -> Dict[str, Any]:
    quote = await finance_tools.fetch_ticker_quote(symbol)
    return quote


@router.post("/evaluate-alerts")
async def evaluate_alerts() -> Dict[str, Any]:
    triggered = await finance_tools.evaluate_portfolio_alerts()
    return {"status": "SUCCESS", "alerts_triggered": len(triggered), "details": triggered}
