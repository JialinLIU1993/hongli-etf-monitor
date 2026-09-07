"""Local investment record storage and PnL calculations."""
from __future__ import annotations

from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
import math
import os
from pathlib import Path
import tempfile
from threading import RLock
from uuid import NAMESPACE_URL, uuid4, uuid5

try:
    import fcntl
except ImportError:  # Windows still shares the in-process Streamlit lock.
    fcntl = None

import pandas as pd


RECORD_COLUMNS = ["id", "date", "symbol", "side", "price", "quantity", "fee", "note", "created_at"]
RECORDS_PATH = Path(__file__).resolve().parents[1] / "data" / "investment_records.csv"
_RECORD_LOCK = RLock()


@dataclass(frozen=True)
class RecordValidationResult:
    ok: bool
    message: str = ""


def empty_records() -> pd.DataFrame:
    """Return an empty records table with stable columns."""
    return pd.DataFrame(columns=RECORD_COLUMNS)


def normalize_records(records: pd.DataFrame) -> pd.DataFrame:
    """Normalize records without silently dropping or repairing invalid trades."""
    if records is None or records.empty:
        result = empty_records()
        if records is not None:
            result.attrs.update(records.attrs)
        return result

    normalized = records.copy()
    required = {"date", "symbol", "side", "price", "quantity"}
    missing = required - set(normalized.columns)
    if missing:
        raise ValueError(f"投资记录缺少必要字段：{', '.join(sorted(missing))}。原文件未修改。")
    for col in RECORD_COLUMNS:
        if col not in normalized.columns:
            normalized[col] = 0.0 if col == "fee" else ""

    # Keep any additional CSV columns so that saving cannot discard user data.
    extra_columns = [col for col in normalized.columns if col not in RECORD_COLUMNS]
    normalized = normalized[RECORD_COLUMNS + extra_columns]
    created_at_present = normalized["created_at"].notna() & normalized["created_at"].astype(str).str.strip().ne("")
    normalized["date"] = pd.to_datetime(normalized["date"], errors="coerce", format="mixed")
    normalized["created_at"] = pd.to_datetime(normalized["created_at"], errors="coerce", format="mixed")
    for col in ("date", "created_at"):
        if isinstance(normalized[col].dtype, pd.DatetimeTZDtype):
            normalized[col] = normalized[col].dt.tz_localize(None)
        elif not pd.api.types.is_datetime64_any_dtype(normalized[col]):
            raise ValueError("投资记录的日期时区格式不一致，请检查原文件。")
    normalized["date"] = normalized["date"].dt.normalize()
    normalized["symbol"] = normalized["symbol"].fillna("").astype(str).str.strip()
    normalized["side"] = normalized["side"].fillna("").astype(str).str.strip()
    for col in ("price", "quantity", "fee"):
        normalized[col] = pd.to_numeric(normalized[col], errors="coerce")
    normalized["note"] = normalized["note"].fillna("").astype(str)

    valid = (
        normalized["date"].notna()
        & (~created_at_present | normalized["created_at"].notna())
        & normalized["symbol"].isin(["510880", "512890"])
        & normalized["side"].isin(["buy", "sell"])
        & (normalized["price"] > 0)
        & (normalized["quantity"] > 0)
        & (normalized["fee"] >= 0)
    )
    for col in ("price", "quantity", "fee"):
        valid &= normalized[col].map(math.isfinite)
    if not valid.all():
        rows = [str(i + 2) for i, ok in enumerate(valid) if not ok]
        raise ValueError(f"投资记录第 {', '.join(rows[:10])} 行包含无效日期、ETF、方向或金额，请检查原文件；未丢弃任何记录。")
    normalized["created_at"] = normalized["created_at"].fillna(normalized["date"])
    normalized["id"] = normalized["id"].fillna("").astype(str).str.strip()
    for position in (i for i, missing_id in enumerate(normalized["id"].eq("")) if missing_id):
        # Stable IDs keep older CSV files without IDs manageable across reruns.
        identity = f"{position}:{normalized.iloc[position].to_json(date_format='iso')}"
        normalized.iloc[position, normalized.columns.get_loc("id")] = uuid5(NAMESPACE_URL, identity).hex[:12]
    if normalized["id"].duplicated().any():
        raise ValueError("投资记录存在重复 ID，请检查原文件后再保存或删除。")

    # Existing timestamps have second precision: equal timestamps retain CSV order.
    return normalized.sort_values(["date", "created_at"], kind="stable").reset_index(drop=True)


def validate_record(symbol: str, side: str, price: float, quantity: float, fee: float) -> RecordValidationResult:
    """Validate a single investment record before storing it."""
    if symbol not in {"510880", "512890"}:
        return RecordValidationResult(False, "请选择支持的 ETF。")
    if side not in {"buy", "sell"}:
        return RecordValidationResult(False, "请选择买入或卖出。")
    try:
        price, quantity, fee = float(price), float(quantity), float(fee)
    except (TypeError, ValueError, OverflowError):
        return RecordValidationResult(False, "成交价、份额和费用必须为有效数字。")
    if not all(math.isfinite(value) for value in (price, quantity, fee)):
        return RecordValidationResult(False, "成交价、份额和费用必须为有限数字。")
    if price <= 0:
        return RecordValidationResult(False, "成交价必须大于 0。")
    if quantity <= 0:
        return RecordValidationResult(False, "份额必须大于 0。")
    if fee < 0:
        return RecordValidationResult(False, "费用不能为负数。")
    return RecordValidationResult(True)


def lookup_trade_price(price_frame: pd.DataFrame, date, field: str = "close") -> dict:
    """Look up a trade-date price, falling back to the previous trading day."""
    if price_frame is None or price_frame.empty or field not in price_frame.columns:
        return {
            "price": None,
            "date": None,
            "field": field,
            "is_exact": False,
            "message": "没有可用行情",
        }

    frame = price_frame.sort_index()
    target = pd.Timestamp(date).normalize()
    eligible = frame[frame.index.normalize() <= target]
    if eligible.empty:
        return {
            "price": None,
            "date": None,
            "field": field,
            "is_exact": False,
            "message": "所选日期之前没有行情",
        }

    row = eligible.iloc[-1]
    used_date = eligible.index[-1]
    value = row[field]
    if not _valid_price(value):
        return {
            "price": None,
            "date": used_date,
            "field": field,
            "is_exact": used_date.normalize() == target,
            "message": "所选价格字段缺失或无效",
        }

    is_exact = used_date.normalize() == target
    return {
        "price": float(value),
        "date": used_date,
        "field": field,
        "is_exact": is_exact,
        "message": "匹配所选交易日" if is_exact else "所选日期非交易日，使用此前最近交易日",
    }


def load_records(path: Path = RECORDS_PATH) -> pd.DataFrame:
    """Load local investment records. Missing file is treated as no records."""
    path = Path(path).resolve()
    try:
        payload = path.read_bytes()
    except FileNotFoundError:
        result = empty_records()
        revision = None
    else:
        result = _decode_records(payload, path)
        revision = sha256(payload).hexdigest()
    result.attrs.update(_storage_path=str(path), _storage_revision=revision)
    return result


def _decode_records(payload: bytes, path: Path) -> pd.DataFrame:
    """Decode and validate a snapshot, with a recovery hint on invalid files."""
    try:
        # IDs, notes and ETF codes must not be inferred as numeric or NA values.
        return normalize_records(pd.read_csv(BytesIO(payload), dtype=str, keep_default_na=False))
    except (ValueError, pd.errors.ParserError, pd.errors.EmptyDataError, UnicodeError) as exc:
        raise ValueError(f"投资记录文件无法读取：{exc} 请检查原文件或同目录备份 {path.name}.bak；未自动覆盖。") from exc


@contextmanager
def _storage_lock(path: Path):
    """Serialize writers and protect the revision check from concurrent saves."""
    with _RECORD_LOCK:
        with path.with_suffix(path.suffix + ".lock").open("a+b") as lock_file:
            if fcntl is not None:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                if fcntl is not None:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _atomic_write(payload: bytes, path: Path) -> None:
    """Write one complete snapshot without truncating the previous file."""
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False) as temp:
            temporary_path = Path(temp.name)
            temp.write(payload)
            temp.flush()
            os.fsync(temp.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def save_records(records: pd.DataFrame, path: Path = RECORDS_PATH) -> None:
    """Atomically save valid records, refusing to overwrite a stale loaded copy."""
    path = Path(path).resolve()
    normalized = normalize_records(records)
    to_save = normalized.copy()
    if not to_save.empty:
        to_save["date"] = to_save["date"].dt.strftime("%Y-%m-%d")
        to_save["created_at"] = to_save["created_at"].dt.strftime("%Y-%m-%d %H:%M:%S.%f")
    payload = to_save.to_csv(index=False).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    with _storage_lock(path):
        try:
            current_payload = path.read_bytes()
        except FileNotFoundError:
            current_payload = None
        current_revision = sha256(current_payload).hexdigest() if current_payload is not None else None
        if records.attrs.get("_storage_path") == str(path):
            if current_revision != records.attrs.get("_storage_revision"):
                raise ValueError("投资记录已被其他页面或程序更新，请刷新页面后重试，以免覆盖新记录。")
        elif current_payload is not None:
            raise ValueError("现有投资文件不能被没有来源版本的记录覆盖，请先读取最新记录再保存。")
        if current_payload is not None:
            _decode_records(current_payload, path)
            # Back up a verified complete snapshot first. A backup failure aborts
            # the save; a later primary-file failure leaves the original intact.
            _atomic_write(current_payload, path.with_suffix(path.suffix + ".bak"))
        _atomic_write(payload, path)
    records.attrs.update(_storage_path=str(path), _storage_revision=sha256(payload).hexdigest())


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
    try:
        trade_date = pd.Timestamp(date)
        if pd.isna(trade_date):
            raise ValueError
        trade_date = trade_date.tz_localize(None).normalize()
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("请选择有效的交易日期。") from exc

    new_record = {
        "id": uuid4().hex[:12],
        "date": trade_date,
        "symbol": symbol,
        "side": side,
        "price": float(price),
        "quantity": float(quantity),
        "fee": float(fee),
        "note": note or "",
        "created_at": pd.Timestamp.now(),
    }
    normalized = normalize_records(records)
    combined = pd.DataFrame([new_record]) if normalized.empty else pd.concat([normalized, pd.DataFrame([new_record])], ignore_index=True)
    combined.attrs.update(normalized.attrs)
    return normalize_records(combined)


def delete_records(records: pd.DataFrame, ids: list[str]) -> pd.DataFrame:
    """Return records with selected IDs removed."""
    if not ids:
        return normalize_records(records)
    normalized = normalize_records(records)
    return normalized[~normalized["id"].isin(ids)].reset_index(drop=True)


def _valid_price(value) -> bool:
    try:
        return math.isfinite(float(value)) and float(value) > 0
    except (TypeError, ValueError, OverflowError):
        return False


def _current_price(symbol: str, current_prices: dict[str, float]) -> float | None:
    value = current_prices.get(symbol)
    return float(value) if _valid_price(value) else None


def calculate_investment_summary(
    records: pd.DataFrame,
    current_prices: dict[str, float] | None = None,
) -> dict:
    """Calculate FIFO realized PnL, open positions, and history summaries."""
    current_prices = current_prices or {}
    normalized = normalize_records(records)

    lots: dict[str, deque[dict]] = {"510880": deque(), "512890": deque()}
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
        while remaining_sell_qty > 0 and lots[symbol]:
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
            if lot["remaining"] <= 0:
                lots[symbol].popleft()

        if remaining_sell_qty > 0:
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
    missing_price_symbols = sorted(open_df.loc[open_df["current_price"].isna(), "symbol"].unique()) if not open_df.empty else []
    market_value = (float(open_df["market_value"].sum()) if not open_df.empty else 0.0) if not missing_price_symbols else None
    unrealized_pnl = (float(open_df["unrealized_pnl"].sum()) if not open_df.empty else 0.0) if not missing_price_symbols else None
    total_pnl = realized_pnl + unrealized_pnl if unrealized_pnl is not None else None
    capital_base = realized_cost + open_cost

    history_df = pd.DataFrame()
    if not closed_df.empty:
        history_df = closed_df.copy()
        history_df["month"] = history_df["sell_date"].dt.to_period("M").astype(str)
        history_df = history_df.groupby("month", as_index=False).agg(
            realized_pnl=("pnl", "sum"),
            proceeds=("proceeds", "sum"),
            cost=("cost", "sum"),
            trades=("sell_id", "nunique"),
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
            "total_return": (total_pnl / capital_base if capital_base else 0.0) if total_pnl is not None else None,
            "open_cost": open_cost,
            "market_value": market_value,
            "capital_base": capital_base,
            "missing_price_symbols": missing_price_symbols,
        },
    }
