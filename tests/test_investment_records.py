"""Tests for local investment record calculations."""
import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.investment_records import (
    append_record,
    calculate_investment_summary,
    delete_records,
    empty_records,
    load_records,
    lookup_trade_price,
    normalize_records,
    save_records,
    validate_record,
)


def test_fifo_realized_pnl_with_fees():
    records = empty_records()
    records = append_record(
        records,
        date="2026-01-01",
        symbol="510880",
        side="buy",
        price=3.0,
        quantity=1000,
        fee=1.0,
    )
    records = append_record(
        records,
        date="2026-02-01",
        symbol="510880",
        side="sell",
        price=3.2,
        quantity=400,
        fee=0.8,
    )

    result = calculate_investment_summary(records, {"510880": 3.1})
    closed = result["closed_trades"]
    open_positions = result["open_positions"]

    assert len(closed) == 1
    assert closed.iloc[0]["cost"] == pytest.approx(1200.4)
    assert closed.iloc[0]["proceeds"] == pytest.approx(1279.2)
    assert closed.iloc[0]["pnl"] == pytest.approx(78.8)
    assert open_positions.iloc[0]["quantity"] == pytest.approx(600)
    assert open_positions.iloc[0]["cost_basis"] == pytest.approx(1800.6)
    assert open_positions.iloc[0]["unrealized_pnl"] == pytest.approx(59.4)


def test_fifo_uses_oldest_lot_first():
    records = empty_records()
    records = append_record(records, date="2026-01-01", symbol="510880", side="buy", price=3.0, quantity=1000)
    records = append_record(records, date="2026-01-10", symbol="510880", side="buy", price=3.5, quantity=1000)
    records = append_record(records, date="2026-02-01", symbol="510880", side="sell", price=4.0, quantity=1500)

    result = calculate_investment_summary(records, {"510880": 3.8})
    closed = result["closed_trades"]
    open_positions = result["open_positions"]

    assert len(closed) == 2
    assert closed.iloc[0]["quantity"] == pytest.approx(1000)
    assert closed.iloc[0]["buy_price"] == pytest.approx(3.0)
    assert closed.iloc[1]["quantity"] == pytest.approx(500)
    assert closed.iloc[1]["buy_price"] == pytest.approx(3.5)
    assert open_positions.iloc[0]["quantity"] == pytest.approx(500)


def test_unmatched_sell_is_reported():
    records = empty_records()
    records = append_record(records, date="2026-01-01", symbol="512890", side="sell", price=1.2, quantity=1000)

    result = calculate_investment_summary(records, {"512890": 1.1})

    assert result["closed_trades"].empty
    assert len(result["unmatched_sells"]) == 1
    assert result["unmatched_sells"].iloc[0]["quantity"] == pytest.approx(1000)


def test_history_groups_realized_pnl_by_month():
    records = empty_records()
    records = append_record(records, date="2026-01-01", symbol="510880", side="buy", price=3.0, quantity=1000)
    records = append_record(records, date="2026-03-01", symbol="510880", side="sell", price=3.2, quantity=500)
    records = append_record(records, date="2026-03-10", symbol="510880", side="sell", price=3.3, quantity=500)

    history = calculate_investment_summary(records, {"510880": 3.1})["history"]

    assert len(history) == 1
    assert history.iloc[0]["month"] == "2026-03"
    assert history.iloc[0]["realized_pnl"] == pytest.approx(250)
    assert history.iloc[0]["trades"] == 2


def test_lookup_trade_price_uses_selected_trade_date():
    dates = pd.to_datetime(["2026-05-22", "2026-05-25", "2026-06-01"])
    frame = pd.DataFrame({"close": [1.15, 1.159, 1.183]}, index=dates)

    result = lookup_trade_price(frame, "2026-05-25")

    assert result["price"] == pytest.approx(1.159)
    assert result["date"] == pd.Timestamp("2026-05-25")
    assert result["is_exact"] is True


def test_lookup_trade_price_falls_back_to_previous_trading_day():
    dates = pd.to_datetime(["2026-05-22", "2026-05-25"])
    frame = pd.DataFrame({"close": [1.15, 1.159]}, index=dates)

    result = lookup_trade_price(frame, "2026-05-24")

    assert result["price"] == pytest.approx(1.15)
    assert result["date"] == pd.Timestamp("2026-05-22")
    assert result["is_exact"] is False


def _buy(records=None, **overrides):
    values = dict(date="2026-01-01", symbol="510880", side="buy", price=3.0, quantity=1000)
    values.update(overrides)
    return append_record(empty_records() if records is None else records, **values)


@pytest.mark.parametrize("field", ["price", "quantity", "fee"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), None, "invalid"])
def test_rejects_non_finite_or_non_numeric_amounts(field, value):
    values = dict(symbol="510880", side="buy", price=3.0, quantity=1000, fee=0.0)
    values[field] = value
    assert not validate_record(**values).ok
    with pytest.raises(ValueError):
        _buy(**{field: value})


@pytest.mark.parametrize("date", [None, "not-a-date", pd.NaT])
def test_append_rejects_invalid_trade_date(date):
    with pytest.raises(ValueError, match="交易日期"):
        _buy(date=date)


def test_same_second_records_retain_insertion_order_after_round_trip(tmp_path):
    records = _buy()
    records = _buy(records, side="sell", price=4.0)
    records["created_at"] = pd.Timestamp("2026-01-01 12:00:00")
    # Random UUID lexical order used to move this sell before the buy.
    records["id"] = ["zzzzzzzzzzzz", "aaaaaaaaaaaa"]
    path = tmp_path / "records.csv"
    save_records(records, path)

    result = calculate_investment_summary(load_records(path))

    assert result["unmatched_sells"].empty
    assert result["open_positions"].empty
    assert result["summary"]["realized_pnl"] == pytest.approx(1000)


def test_monthly_trade_count_counts_sell_orders_not_fifo_lots():
    records = _buy(quantity=100)
    records = _buy(records, date="2026-01-02", quantity=200, price=3.5)
    records = _buy(records, date="2026-02-01", side="sell", quantity=300, price=4.0, fee=3)

    result = calculate_investment_summary(records)

    assert len(result["closed_trades"]) == 2
    assert result["history"].iloc[0]["trades"] == 1
    assert result["closed_trades"]["sell_fee"].sum() == pytest.approx(3)


@pytest.mark.parametrize("price", [None, float("nan"), float("inf"), -1.0, 0.0, "invalid"])
def test_missing_or_invalid_market_price_does_not_become_zero_pnl(price):
    result = calculate_investment_summary(_buy(), {"510880": price})

    for field in ("market_value", "unrealized_pnl", "total_pnl", "total_return"):
        assert result["summary"][field] is None
    assert result["summary"]["realized_pnl"] == 0.0
    assert result["summary"]["missing_price_symbols"] == ["510880"]


def test_partial_market_coverage_does_not_report_incomplete_portfolio_total():
    records = _buy()
    records = _buy(records, symbol="512890", price=1.0)

    result = calculate_investment_summary(records, {"510880": 3.1})

    assert result["summary"]["market_value"] is None
    assert result["summary"]["missing_price_symbols"] == ["512890"]
    available = result["open_positions"].query("symbol == '510880'").iloc[0]
    assert available["unrealized_pnl"] == pytest.approx(100)


def test_csv_preserves_identifier_note_and_extra_columns(tmp_path):
    path = tmp_path / "records.csv"
    records = _buy(note="NA")
    records["id"] = "000000000012"
    records["broker_reference"] = "000045"
    save_records(records, path)

    loaded = load_records(path)

    assert loaded.iloc[0]["id"] == "000000000012"
    assert loaded.iloc[0]["note"] == "NA"
    assert loaded.iloc[0]["broker_reference"] == "000045"
    assert loaded.iloc[0]["created_at"] == records.iloc[0]["created_at"].floor("us")


def test_legacy_records_without_optional_columns_have_stable_ids(tmp_path):
    path = tmp_path / "records.csv"
    path.write_text("date,symbol,side,price,quantity\n2026-01-01,510880,buy,3,1000\n", encoding="utf-8")

    first = load_records(path)
    second = load_records(path)

    assert first.iloc[0]["id"] == second.iloc[0]["id"]
    assert first.iloc[0]["fee"] == 0
    save_records(first, path)
    assert len(load_records(path)) == 1


@pytest.mark.parametrize("field,value", [("date", "invalid"), ("created_at", "invalid"), ("fee", -1), ("quantity", float("inf")), ("price", "broken")])
def test_invalid_record_cannot_silently_replace_existing_file(tmp_path, field, value):
    path = tmp_path / "records.csv"
    records = _buy()
    save_records(records, path)
    before = path.read_bytes()
    invalid = records.astype({field: "object"})
    invalid.loc[0, field] = value

    with pytest.raises(ValueError):
        save_records(invalid, path)

    assert path.read_bytes() == before


def test_invalid_csv_is_reported_without_removing_rows(tmp_path):
    path = tmp_path / "records.csv"
    payload = "date,symbol,side,price,quantity\n2026-01-01,510880,buy,3,1000\ninvalid,510880,buy,3,1000\n"
    path.write_text(payload, encoding="utf-8")

    with pytest.raises(ValueError, match="未丢弃"):
        load_records(path)

    assert path.read_text(encoding="utf-8") == payload


def test_duplicate_ids_cannot_delete_multiple_unrelated_records():
    records = _buy()
    records = _buy(records, date="2026-01-02")
    records["id"] = "duplicate"

    with pytest.raises(ValueError, match="重复 ID"):
        delete_records(records, ["duplicate"])


def test_stale_loaded_records_cannot_overwrite_another_save(tmp_path):
    path = tmp_path / "records.csv"
    first = load_records(path)
    second = load_records(path)
    first = _buy(first)
    second = _buy(second, symbol="512890")
    save_records(first, path)

    with pytest.raises(ValueError, match="更新"):
        save_records(second, path)

    loaded = load_records(path)
    assert loaded["symbol"].tolist() == ["510880"]


def test_stale_deletion_cannot_discard_new_records(tmp_path):
    path = tmp_path / "records.csv"
    save_records(_buy(), path)
    original = load_records(path)
    updated = _buy(load_records(path), date="2026-01-02")
    save_records(updated, path)
    deleted = delete_records(original, original["id"].tolist())

    with pytest.raises(ValueError, match="更新"):
        save_records(deleted, path)

    assert len(load_records(path)) == 2


def test_failed_atomic_replace_preserves_existing_csv(tmp_path, monkeypatch):
    path = tmp_path / "records.csv"
    save_records(_buy(), path)
    before = path.read_bytes()
    updated = _buy(load_records(path), date="2026-01-02")

    def fail_replace(*args):
        raise OSError("simulated disk error")

    monkeypatch.setattr("src.investment_records.os.replace", fail_replace)
    with pytest.raises(OSError, match="disk error"):
        save_records(updated, path)

    assert path.read_bytes() == before
    assert not list(tmp_path.glob("*.tmp"))


def test_oversell_fee_allocation_conserves_full_transaction_fee():
    records = _buy(quantity=100, fee=2)
    records = _buy(records, date="2026-02-01", side="sell", quantity=150, price=4, fee=3)

    result = calculate_investment_summary(records)

    assert result["closed_trades"]["buy_fee"].sum() == pytest.approx(2)
    assert result["closed_trades"]["sell_fee"].sum() == pytest.approx(2)
    assert result["unmatched_sells"]["fee_unmatched"].sum() == pytest.approx(1)


def test_empty_portfolio_still_has_zero_valuation():
    summary = calculate_investment_summary(empty_records())["summary"]

    assert summary["market_value"] == 0.0
    assert summary["total_pnl"] == 0.0
    assert summary["missing_price_symbols"] == []


def test_small_fractional_quantity_is_not_silently_dropped():
    records = _buy(quantity=1e-10)
    records = _buy(records, date="2026-01-02", side="sell", price=4, quantity=1e-10)

    result = calculate_investment_summary(records)

    assert result["open_positions"].empty
    assert result["unmatched_sells"].empty
    assert len(result["closed_trades"]) == 1
    assert result["closed_trades"].iloc[0]["quantity"] == pytest.approx(1e-10)


def test_records_without_loaded_revision_cannot_overwrite_existing_file(tmp_path):
    path = tmp_path / "records.csv"
    save_records(_buy(), path)
    before = path.read_bytes()

    with pytest.raises(ValueError, match="来源版本"):
        save_records(_buy(symbol="512890"), path)

    assert path.read_bytes() == before
    assert not path.with_suffix(".csv.bak").exists()


def test_backup_is_previous_complete_snapshot_after_each_save(tmp_path):
    path = tmp_path / "records.csv"
    backup = path.with_suffix(".csv.bak")
    first = _buy()
    save_records(first, path)
    first_bytes = path.read_bytes()
    assert not backup.exists()

    second = _buy(load_records(path), date="2026-01-02")
    save_records(second, path)
    second_bytes = path.read_bytes()
    assert backup.read_bytes() == first_bytes
    assert len(load_records(backup)) == 1

    third = _buy(load_records(path), date="2026-01-03")
    save_records(third, path)
    assert backup.read_bytes() == second_bytes
    assert len(load_records(backup)) == 2
    assert len(load_records(path)) == 3


def test_backup_write_failure_preserves_both_original_and_previous_backup(tmp_path, monkeypatch):
    path = tmp_path / "records.csv"
    backup = path.with_suffix(".csv.bak")
    save_records(_buy(), path)
    save_records(_buy(load_records(path), date="2026-01-02"), path)
    original_bytes = path.read_bytes()
    backup_bytes = backup.read_bytes()
    updated = _buy(load_records(path), date="2026-01-03")
    real_replace = os.replace

    def fail_backup(source, destination):
        if destination == backup:
            raise OSError("simulated backup failure")
        real_replace(source, destination)

    monkeypatch.setattr("src.investment_records.os.replace", fail_backup)
    with pytest.raises(OSError, match="backup failure"):
        save_records(updated, path)

    assert path.read_bytes() == original_bytes
    assert backup.read_bytes() == backup_bytes
    assert not list(tmp_path.glob("*.tmp"))


def test_primary_replace_failure_leaves_original_and_complete_backup(tmp_path, monkeypatch):
    path = tmp_path / "records.csv"
    backup = path.with_suffix(".csv.bak")
    save_records(_buy(), path)
    before = path.read_bytes()
    updated = _buy(load_records(path), date="2026-01-02")
    real_replace = os.replace

    def fail_primary(source, destination):
        if destination == path:
            raise OSError("simulated primary failure")
        real_replace(source, destination)

    monkeypatch.setattr("src.investment_records.os.replace", fail_primary)
    with pytest.raises(OSError, match="primary failure"):
        save_records(updated, path)

    assert path.read_bytes() == before
    assert backup.read_bytes() == before
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.parametrize("payload", ["", "not,a,ledger\n1,2,3\n", "date,symbol,side,price,quantity\ninvalid,510880,buy,3,100\n"])
def test_invalid_file_error_points_to_backup_without_modifying_files(tmp_path, payload):
    path = tmp_path / "records.csv"
    backup = path.with_suffix(".csv.bak")
    save_records(_buy(), path)
    backup.write_bytes(path.read_bytes())
    backup_before = backup.read_bytes()
    path.write_text(payload, encoding="utf-8")

    with pytest.raises(ValueError, match=r"records\.csv\.bak"):
        load_records(path)

    assert path.read_text(encoding="utf-8") == payload
    assert backup.read_bytes() == backup_before
