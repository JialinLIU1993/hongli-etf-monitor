"""Local investment record storage and PnL calculations."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import pandas as pd


RECORD_COLUMNS = ["id", "date", "symbol", "side", "price", "quantity", "fee", "note", "created_at"]
RECORDS_PATH = Path("data/investment_records.csv")


@dataclass(frozen=True)
class RecordValidationResult:
    ok: bool
    message: str = ""


def empty_records() -> pd.DataFrame:
    """Return an empty records table with stable columns."""
    return pd.DataFrame(columns=RECORD_COLUMNS)


def normalize_records(records: pd.DataFrame) -> pd.DataFrame:
    """Normalize types and ordering for records loaded from CSV or UI edits."""
    if records is None or records.empty:
        return empty_records()

    normalized = records.copy()
    for col in RECORD_COLUMNS:
        if col not in normalized.columns:
            normalized[col] = ""

    normalized = normalized[RECORD_COLUMNS]
    normalized["date"] = pd.to_datetime(normalized["date"], errors="coerce")
    normalized["created_at"] = pd.to_datetime(normalized["created_at"], errors="coerce")
    normalized["symbol"] = normalized["symbol"].astype(str)
    normalized["side"] = normalized["side"].astype(str)
    normalized["price"] = pd.to_numeric(normalized["price"], errors="coerce").fillna(0.0)
    normalized["quantity"] = pd.to_numeric(normalized["quantity"], errors="coerce").fillna(0.0)
    normalized["fee"] = pd.to_numeric(normalized["fee"], errors="coerce").fillna(0.0)
    normalized["note"] = normalized["note"].fillna("").astype(str)

    normalized = normalized.dropna(subset=["date"])
    normalized = normalized[normalized["symbol"].isin(["510880", "512890"])]
    normalized = normalized[normalized["side"].isin(["buy", "sell"])]
    normalized = normalized[(normalized["price"] > 0) & (normalized["quantity"] > 0)]
    normalized["created_at"] = normalized["created_at"].fillna(normalized["date"])

    return normalized.sort_values(["date", "created_at", "id"]).reset_index(drop=True)


def validate_record(symbol: str, side: str, price: float, quantity: float, fee: float) -> RecordValidationResult:
    """Validate a single investment record before storing it."""
    if symbol not in {"510880", "512890"}:
        return RecordValidationResult(False, "请选择支持的 ETF。")
    if side not in {"buy", "sell"}:
        return RecordValidationResult(False, "请选择买入或卖出。")
    if price <= 0:
        return RecordValidationResult(False, "成交价必须大于 0。")
    if quantity <= 0:
        return RecordValidationResult(False, "份额必须大于 0。")
    if fee < 0:
        return RecordValidationResult(False, "费用不能为负数。")
    return RecordValidationResult(True)


def load_records(path: Path = RECORDS_PATH) -> pd.DataFrame:
    """Load local investment records. Missing file is treated as no records."""
    if not path.exists():
        return empty_records()
    return normalize_records(pd.read_csv(path))


def save_records(records: pd.DataFrame, path: Path = RECORDS_PATH) -> None:
    """Persist records to CSV."""
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = normalize_records(records)
    to_save = normalized.copy()
    if not to_save.empty:
        to_save["date"] = to_save["date"].dt.strftime("%Y-%m-%d")
        to_save["created_at"] = to_save["created_at"].dt.strftime("%Y-%m-%d %H:%M:%S")
    to_save.to_csv(path, index=False)


def append_record(
    records: pd.DataFrame,
    *,
    date,
    symbol: str,
    side: str,
    price: float,
    quantity: float,
    fee: float = 0.0,
    note: str = "",
) -> pd.DataFrame:
    """Return records plus one validated record."""
    validation = validate_record(symbol, side, price, quantity, fee)
    if not validation.ok:
        raise ValueError(validation.message)

    new_record = {
        "id": uuid4().hex[:12],
        "date": pd.Timestamp(date).normalize(),
        "symbol": symbol,
        "side": side,
        "price": float(price),
        "quantity": float(quantity),
        "fee": float(fee),
        "note": note or "",
        "created_at": pd.Timestamp.now().floor("s"),
    }
    normalized = normalize_records(records)
    if normalized.empty:
        return normalize_records(pd.DataFrame([new_record]))
    return normalize_records(pd.concat([normalized, pd.DataFrame([new_record])], ignore_index=True))


def delete_records(records: pd.DataFrame, ids: list[str]) -> pd.DataFrame:
    """Return records with selected IDs removed."""
    if not ids:
        return normalize_records(records)
    normalized = normalize_records(records)
    return normalized[~normalized["id"].isin(ids)].reset_index(drop=True)


def _current_price(symbol: str, current_prices: dict[str, float]) -> float | None:
    value = current_prices.get(symbol)
    if value is None or pd.isna(value):
        return None
    return float(value)


def calculate_investment_summary(
    records: pd.DataFrame,
    current_prices: dict[str, float] | None = None,
) -> dict:
    """Calculate FIFO realized PnL, open positions, and history summaries."""
    current_prices = current_prices or {}
    normalized = normalize_records(records)

    lots: dict[str, list[dict]] = {"510880": [], "512890": []}
    closed_rows = []
    unmatched_rows = []

    for row in normalized.itertuples(index=False):
        symbol = row.symbol
        quantity = float(row.quantity)
        price = float(row.price)
        fee = float(row.fee)

        if row.side == "buy":
            lots[symbol].append({
                "buy_id": row.id,
                "buy_date": row.date,
                "price": price,
                "remaining": quantity,
                "fee_remaining": fee,
                "initial_quantity": quantity,
            })
            continue

        remaining_sell_qty = quantity
        sell_fee_remaining = fee
        while remaining_sell_qty > 1e-9 and lots[symbol]:
            lot = lots[symbol][0]
            matched_qty = min(remaining_sell_qty, lot["remaining"])
            buy_fee = lot["fee_remaining"] * (matched_qty / lot["remaining"]) if lot["remaining"] else 0.0
            sell_fee = sell_fee_remaining * (matched_qty / remaining_sell_qty) if remaining_sell_qty else 0.0
            cost = lot["price"] * matched_qty + buy_fee
            proceeds = price * matched_qty - sell_fee
            pnl = proceeds - cost
            closed_rows.append({
                "symbol": symbol,
                "buy_date": lot["buy_date"],
                "sell_date": row.date,
                "quantity": matched_qty,
                "buy_price": lot["price"],
                "sell_price": price,
                "buy_fee": buy_fee,
                "sell_fee": sell_fee,
                "cost": cost,
                "proceeds": proceeds,
                "pnl": pnl,
                "return_pct": pnl / cost if cost else 0.0,
                "holding_days": (row.date - lot["buy_date"]).days,
                "sell_id": row.id,
            })

            lot["remaining"] -= matched_qty
            lot["fee_remaining"] -= buy_fee
            remaining_sell_qty -= matched_qty
            sell_fee_remaining -= sell_fee
            if lot["remaining"] <= 1e-9:
                lots[symbol].pop(0)

        if remaining_sell_qty > 1e-9:
            unmatched_rows.append({
                "date": row.date,
                "symbol": symbol,
                "quantity": remaining_sell_qty,
                "price": price,
                "fee_unmatched": sell_fee_remaining,
                "message": "卖出份额超过已记录持仓，未能完全配对。",
            })

    open_rows = []
    for symbol, symbol_lots in lots.items():
        price_now = _current_price(symbol, current_prices)
        for lot in symbol_lots:
            quantity = lot["remaining"]
            cost_basis = lot["price"] * quantity + lot["fee_remaining"]
            market_value = quantity * price_now if price_now is not None else None
            unrealized = market_value - cost_basis if market_value is not None else None
            open_rows.append({
                "symbol": symbol,
                "buy_date": lot["buy_date"],
                "quantity": quantity,
                "buy_price": lot["price"],
                "cost_basis": cost_basis,
                "current_price": price_now,
                "market_value": market_value,
                "unrealized_pnl": unrealized,
                "return_pct": unrealized / cost_basis if cost_basis and unrealized is not None else None,
            })

    closed_df = pd.DataFrame(closed_rows)
    open_df = pd.DataFrame(open_rows)
    unmatched_df = pd.DataFrame(unmatched_rows)

    realized_pnl = float(closed_df["pnl"].sum()) if not closed_df.empty else 0.0
    realized_cost = float(closed_df["cost"].sum()) if not closed_df.empty else 0.0
    open_cost = float(open_df["cost_basis"].sum()) if not open_df.empty else 0.0
    market_value = float(open_df["market_value"].dropna().sum()) if not open_df.empty else 0.0
    unrealized_pnl = float(open_df["unrealized_pnl"].dropna().sum()) if not open_df.empty else 0.0
    total_pnl = realized_pnl + unrealized_pnl
    capital_base = realized_cost + open_cost

    history_df = pd.DataFrame()
    if not closed_df.empty:
        history_df = closed_df.copy()
        history_df["month"] = history_df["sell_date"].dt.to_period("M").astype(str)
        history_df = history_df.groupby("month", as_index=False).agg(
            realized_pnl=("pnl", "sum"),
            proceeds=("proceeds", "sum"),
            cost=("cost", "sum"),
            trades=("sell_id", "count"),
        )
        history_df["return_pct"] = history_df["realized_pnl"] / history_df["cost"].replace(0, pd.NA)
        history_df["return_pct"] = history_df["return_pct"].fillna(0.0)

    return {
        "records": normalized,
        "closed_trades": closed_df,
        "open_positions": open_df,
        "unmatched_sells": unmatched_df,
        "history": history_df,
        "summary": {
            "record_count": len(normalized),
            "buy_count": int((normalized["side"] == "buy").sum()) if not normalized.empty else 0,
            "sell_count": int((normalized["side"] == "sell").sum()) if not normalized.empty else 0,
            "realized_pnl": realized_pnl,
            "unrealized_pnl": unrealized_pnl,
            "total_pnl": total_pnl,
            "realized_return": realized_pnl / realized_cost if realized_cost else 0.0,
            "total_return": total_pnl / capital_base if capital_base else 0.0,
            "open_cost": open_cost,
            "market_value": market_value,
            "capital_base": capital_base,
        },
    }
