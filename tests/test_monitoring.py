"""Tests for ETF monitoring helpers."""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.monitoring import calculate_monitor_frame, summarize_monitor_status


def _make_df(prices):
    dates = pd.bdate_range("2024-01-01", periods=len(prices))
    return pd.DataFrame(
        {
            "open": prices,
            "high": [p * 1.01 for p in prices],
            "low": [p * 0.99 for p in prices],
            "close": prices,
            "volume": [1000000] * len(prices),
        },
        index=dates,
    )


def test_monitor_frame_keeps_bollinger_columns():
    df = _make_df([1.0] * 30 + [0.95, 0.92, 0.90, 0.88, 0.86])

    frame = calculate_monitor_frame(df, window=20, num_std=2.1, first_batch_pct=0.9)

    for col in ["ma", "upper_band", "lower_band", "signal", "position"]:
        assert col in frame.columns


def test_summary_marks_unready_when_data_short():
    df = _make_df([1.0] * 5)
    frame = calculate_monitor_frame(df, window=20, num_std=2.1, first_batch_pct=0.9)

    status = summarize_monitor_status(
        frame,
        symbol="510880",
        name="红利 ETF",
        role="进攻端",
        window=20,
        num_std=2.1,
        first_batch_pct=0.9,
    )

    assert status["is_ready"] is False
    assert "至少需要 20 个交易日" in status["message"]


def test_summary_contains_action_fields_when_ready():
    df = _make_df([1.0] * 40 + [0.98, 0.95, 0.92, 0.90, 0.88])
    frame = calculate_monitor_frame(df, window=20, num_std=2.1, first_batch_pct=0.9)

    status = summarize_monitor_status(
        frame,
        symbol="510880",
        name="红利 ETF",
        role="进攻端",
        window=20,
        num_std=2.1,
        first_batch_pct=0.9,
    )

    assert status["is_ready"] is True
    assert status["state"] in {"buy", "sell", "watch"}
    assert 0.0 <= status["target_position"] <= 1.0
    assert "last_signal" in status
