"""Instrument-centered market workspace: quote, chart, then decision context."""
from html import escape
import pandas as pd
import streamlit as st
from components import tab_kline


def _instrument_header(ctx, symbol):
    profile = ctx["profiles"][symbol]
    status = ctx["statuses"][symbol]
    raw = ctx["raw_data"][symbol]
    quote = ctx.get("quotes", {}).get(symbol)
    price = quote["price"] if quote else (raw["close"].iloc[-1] if not raw.empty else None)
    price_text = f"{price:.3f}" if price is not None else "—"
    latest = ctx["data_status"][symbol]["last_date"]
    latest_text = latest.strftime("%Y.%m.%d") if latest is not None else "暂无行情"
    target = f"{status['target_position']:.0%}" if status.get("is_ready") else "—"
    label = status.get("state_label", "等待行情")
    price_label = "行情快照" if quote else "日线收盘"
    st.markdown(
        f'<section class="instrument-head"><div class="instrument-name"><div class="eyebrow">{symbol} · 场内 ETF</div><h1>{escape(profile.name)}</h1><p>日线截至 {latest_text}</p></div>'
        f'<div class="instrument-price">{price_text}<small>{price_label} / 元</small></div>'
        f'<div class="instrument-state"><span class="eyebrow">通道状态</span><strong>{escape(label)}</strong></div>'
        f'<div class="instrument-target"><span class="eyebrow">日线目标仓位</span><strong>{target}</strong></div></section>',
        unsafe_allow_html=True,
    )
    if quote:
        timestamp = quote.get("quote_time")
        time_label = timestamp.strftime("%Y-%m-%d %H:%M:%S") if timestamp else "接口未提供时间"
        st.caption(f"快照时间：{time_label}；图表与策略使用日线。")
    if latest is not None and (pd.Timestamp(ctx["end_date"]) - latest).days > 7:
        st.warning(f"行情停留在 {latest:%Y-%m-%d}，距所选结束日期超过 7 天，请检查数据更新。")


def _decision_context(view):
    status = view["status"]
    if not status.get("is_ready"):
        st.info(status.get("message", "行情不足，暂时无法计算策略。"))
        return
    last = status.get("last_signal", {})
    recent = f"{last['date']:%Y.%m.%d}" if last.get("date") is not None else "暂无调仓"
    action = escape(last.get("action", "暂无"))
    position = f"调仓后目标仓位 {last['position_after']:.0%}" if last.get("position_after") is not None else "当前区间尚未出现调仓信号。"
    st.markdown(
        f'<div class="analysis-heading"><h2>决策参考</h2><span>按图表末日 {view["last_date"]:%Y.%m.%d} 计算</span></div>'
        f'<div class="decision-grid"><section><div class="eyebrow">01 / 当前位置</div><h3>{escape(status["state_label"])}</h3><p>{escape(status["hint"])}</p><div class="decision-foot">通道位置 <strong>{status["channel_position"]:.0%}</strong></div></section>'
        f'<section><div class="eyebrow">02 / 价格边界</div><div class="band-values"><div><small>下轨</small><strong>{status["lower_band"]:.3f}</strong></div><div><small>中轨</small><strong>{status["ma"]:.3f}</strong></div><div><small>上轨</small><strong>{status["upper_band"]:.3f}</strong></div></div><p>与当日收盘价比较，观察买入与卖出边界。</p></section>'
        f'<section><div class="eyebrow">03 / 最近调仓</div><h3>{recent} <span>{action}</span></h3><p>{position}</p><div class="decision-foot">策略信号，请结合实际持仓判断。</div></section></div>',
        unsafe_allow_html=True,
    )


def render(ctx):
    with st.container(key="instrument-switcher"):
        symbol = st.radio("选择 ETF", list(ctx["profiles"]),
                          format_func=lambda s: f"{ctx['profiles'][s].name}  /  {s}",
                          horizontal=True, key="chart_etf", label_visibility="collapsed")
    _instrument_header(ctx, symbol)
    with st.container(key="market-canvas"):
        view = tab_kline.render(ctx, symbol=symbol, title=None, compact=True)
    if view:
        _decision_context(view)
