"""Tests for local investment record calculations."""
import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.investment_records import append_record, calculate_investment_summary, empty_records


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
