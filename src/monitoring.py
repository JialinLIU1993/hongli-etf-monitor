"""ETF Bollinger-band monitoring helpers."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .strategies import BollingerBandsStrategy


@dataclass(frozen=True)
class EtfProfile:
    symbol: str
    name: str
    role: str
    window: int
    num_std: float
    first_batch_pct: float


ETF_PROFILES = {
    "510880": EtfProfile(
        symbol="510880",
        name="红利 ETF",
        role="进攻端",
        window=40,
        num_std=2.1,
        first_batch_pct=0.9,
    ),
    "512890": EtfProfile(
        symbol="512890",
        name="红利低波",
        role="防守端",
        window=50,
        num_std=2.1,
        first_batch_pct=1.0,
    ),
}


def build_bollinger_strategy(
    window: int,
    num_std: float,
    first_batch_pct: float,
    scale_threshold: float = 0.02,
    pyramid_levels: list[float] | None = None,
    pyramid_sizes: list[float] | None = None,
) -> BollingerBandsStrategy:
    """Create the preserved Bollinger strategy used for daily monitoring."""
    return BollingerBandsStrategy(
        window=window,
        num_std=num_std,
        staged=True,
        scale_threshold=scale_threshold,
        first_batch_pct=first_batch_pct,
        pyramid_levels=pyramid_levels or [],
        pyramid_sizes=pyramid_sizes or [],
    )


def calculate_monitor_frame(
    df: pd.DataFrame,
    *,
    window: int,
    num_std: float,
    first_batch_pct: float,
    scale_threshold: float = 0.02,
    pyramid_levels: list[float] | None = None,
    pyramid_sizes: list[float] | None = None,
) -> pd.DataFrame:
    """Return price data with Bollinger bands, target position and action signal."""
    strategy = build_bollinger_strategy(
        window=window,
        num_std=num_std,
        first_batch_pct=first_batch_pct,
        scale_threshold=scale_threshold,
        pyramid_levels=pyramid_levels,
        pyramid_sizes=pyramid_sizes,
    )
    return strategy.generate_signals(df.copy())


def _format_signal(signal: float) -> tuple[str, str]:
    if signal > 0:
        return "加仓", f"+{signal:.0%}"
    if signal < 0:
        return "减仓", f"{signal:.0%}"
    return "无调仓", "0%"


def summarize_monitor_status(
    frame: pd.DataFrame,
    *,
    symbol: str,
    name: str,
    role: str,
    window: int,
    num_std: float,
    first_batch_pct: float,
) -> dict:
    """Summarize the latest actionable monitoring state for one ETF."""
    if frame.empty:
        return {
            "symbol": symbol,
            "name": name,
            "role": role,
            "is_ready": False,
            "message": "无可用数据",
        }

    usable = frame.dropna(subset=["ma", "upper_band", "lower_band"])
    if usable.empty:
        return {
            "symbol": symbol,
            "name": name,
            "role": role,
            "is_ready": False,
            "message": f"数据不足，至少需要 {window} 个交易日计算布林带",
        }

    latest = usable.iloc[-1]
    close = float(latest["close"])
    upper = float(latest["upper_band"])
    lower = float(latest["lower_band"])
    ma = float(latest["ma"])
    position = float(latest["position"])
    signal = float(latest["signal"]) if pd.notna(latest["signal"]) else 0.0
    band_range = upper - lower
    channel_position = ((close - lower) / band_range) if band_range else 0.5
    band_width = (band_range / ma) if ma else 0.0
    dist_to_lower = (close - lower) / close if close else 0.0
    dist_to_upper = (upper - close) / close if close else 0.0

    if close <= lower:
        state = "buy"
        state_label = "触发买入/加仓"
        priority = 1
        hint = "价格已跌破下轨，按保留的布林带分批规则检查买入或加仓。"
    elif close >= upper:
        state = "sell"
        state_label = "触发卖出/减仓"
        priority = 2
        hint = "价格已突破上轨，按保留的布林带分批规则检查止盈或减仓。"
    else:
        state = "watch"
        state_label = "通道内观察"
        priority = 3
        if dist_to_lower < dist_to_upper:
            hint = f"更接近下轨，距买入触发价约 {dist_to_lower:.2%}。"
        else:
            hint = f"更接近上轨，距卖出触发价约 {dist_to_upper:.2%}。"

    signal_rows = usable[usable["signal"].fillna(0) != 0]
    if signal_rows.empty:
        last_signal = {
            "date": None,
            "action": "暂无",
            "position_after": None,
            "change": None,
        }
    else:
        row = signal_rows.iloc[-1]
        action, change = _format_signal(float(row["signal"]))
        last_signal = {
            "date": row.name,
            "action": action,
            "position_after": float(row["position"]),
            "change": change,
        }

    action, signal_change = _format_signal(signal)

    return {
        "symbol": symbol,
        "name": name,
        "role": role,
        "is_ready": True,
        "date": latest.name,
        "close": close,
        "open": float(latest["open"]) if "open" in latest else None,
        "high": float(latest["high"]) if "high" in latest else None,
        "low": float(latest["low"]) if "low" in latest else None,
        "volume": float(latest["volume"]) if "volume" in latest else None,
        "ma": ma,
        "upper_band": upper,
        "lower_band": lower,
        "channel_position": channel_position,
        "band_width": band_width,
        "dist_to_lower": dist_to_lower,
        "dist_to_upper": dist_to_upper,
        "target_position": position,
        "signal": signal,
        "signal_action": action,
        "signal_change": signal_change,
        "state": state,
        "state_label": state_label,
        "priority": priority,
        "hint": hint,
        "window": window,
        "num_std": num_std,
        "first_batch_pct": first_batch_pct,
        "last_signal": last_signal,
    }


def summarize_data_status(df: pd.DataFrame, symbol: str) -> dict:
    """Summarize local/API data coverage for display."""
    if df.empty:
        return {
            "symbol": symbol,
            "rows": 0,
            "first_date": None,
            "last_date": None,
            "first_date_str": "无",
            "last_date_str": "无",
        }

    first_date = df.index.min()
    last_date = df.index.max()
    return {
        "symbol": symbol,
        "rows": len(df),
        "first_date": first_date,
        "last_date": last_date,
        "first_date_str": first_date.strftime("%Y-%m-%d"),
        "last_date_str": last_date.strftime("%Y-%m-%d"),
    }
