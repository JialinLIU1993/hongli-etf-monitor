"""Core monitoring dashboard."""
import pandas as pd
import streamlit as st

from components import tab_investments, tab_kline
from src.investment_records import calculate_investment_summary, load_records


def _date(value):
    if value is None:
        return "暂无"
    return value.strftime("%Y-%m-%d") if hasattr(value, "strftime") else str(value)


def _money(value):
    if value is None or pd.isna(value):
        return "—"
    return f"{value:,.2f}"


def _pct(value):
    if value is None or pd.isna(value):
        return "—"
    return f"{value:.2%}"


def _current_prices(ctx):
    prices = {}
    for symbol, status in ctx["statuses"].items():
        if status.get("is_ready"):
            prices[symbol] = status.get("close")
    return prices


def _data_latest(ctx):
    latest_dates = [
        data["last_date"]
        for data in ctx["data_status"].values()
        if data["last_date"] is not None
    ]
    return min(latest_dates) if latest_dates else None


def render(ctx):
    """Render one dashboard combining monitor, K-line and investments."""
    records = load_records()
    investment = calculate_investment_summary(records, _current_prices(ctx))
    summary = investment["summary"]
    common_latest = _data_latest(ctx)

    st.markdown("### Dashboard")
    st.caption("盯盘信息已整合进 K 线图；参数优化和信号流水收在策略工具里。")

    top = st.columns([1.15, 1, 1, 1, 1])
    top[0].metric("数据截至", _date(common_latest))
    top[1].metric("累计收益", _money(summary["total_pnl"]), _pct(summary["total_return"]), delta_color="inverse")
    top[2].metric("浮动收益", _money(summary["unrealized_pnl"]))
    top[3].metric("当前市值", _money(summary["market_value"]))
    top[4].metric("记录笔数", f"{summary['record_count']}")

    left, right = st.columns([1.35, 1.0], gap="large")
    with left:
        tab_kline.render(ctx, title="K线窗口", compact=True)
    with right:
        st.markdown("### 持仓与记录")
        tab_investments.render(ctx, show_title=False, compact=True)
