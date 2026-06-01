"""Monitoring dashboard tab."""
import pandas as pd
import streamlit as st


def _fmt_date(value):
    if value is None:
        return "暂无"
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d")
    return str(value)


def _fmt_price(value):
    return "—" if value is None else f"{value:.3f}"


def _state_class(state):
    return {
        "buy": "signal-buy",
        "sell": "signal-sell",
        "watch": "signal-hold",
    }.get(state, "signal-hold")


def _render_status_card(status):
    state = status.get("state", "watch")
    cls = _state_class(state)

    st.markdown(f"#### {status['symbol']} {status['name']}")
    st.caption(
        f"{status['role']} | 数据日期 {_fmt_date(status.get('date'))} | "
        f"Window={status.get('window')} Std={status.get('num_std')} "
        f"首批={status.get('first_batch_pct', 0):.0%}"
    )

    if not status.get("is_ready"):
        st.warning(status.get("message", "状态不可用"))
        return

    st.markdown(
        f"""
        <div class="{cls}">
            <strong>{status['state_label']}</strong><br>
            <small>{status['hint']}</small>
        </div>
        """,
        unsafe_allow_html=True,
    )

    top = st.columns(4)
    top[0].metric("最新价", _fmt_price(status["close"]))
    top[1].metric("目标仓位", f"{status['target_position']:.0%}", status["signal_change"])
    top[2].metric("下轨买点", _fmt_price(status["lower_band"]), f"{status['dist_to_lower']:.2%}")
    top[3].metric("上轨卖点", _fmt_price(status["upper_band"]), f"{status['dist_to_upper']:.2%}")

    bottom = st.columns(4)
    bottom[0].metric("中轨", _fmt_price(status["ma"]))
    bottom[1].metric("通道位置", f"{status['channel_position']:.0%}")
    bottom[2].metric("通道宽度", f"{status['band_width']:.2%}")
    bottom[3].metric("今日信号", status["signal_action"])

    last_signal = status["last_signal"]
    if last_signal["date"] is None:
        st.caption("最近调仓信号: 暂无")
    else:
        st.caption(
            f"最近调仓信号: {_fmt_date(last_signal['date'])} "
            f"{last_signal['action']} {last_signal['change']}，"
            f"调仓后目标仓位 {last_signal['position_after']:.0%}"
        )


def render(ctx):
    """Render the main two-ETF monitoring view."""
    statuses = ctx["statuses"]
    data_status = ctx["data_status"]
    requested_end_date = pd.Timestamp(ctx["end_date"]).normalize()
    latest_dates = [s["last_date"] for s in data_status.values() if s["last_date"] is not None]
    common_latest = min(latest_dates) if latest_dates else None

    st.markdown("### 双 ETF 盯盘")

    m1, m2, m3 = st.columns(3)
    m1.metric("共同最新交易日", _fmt_date(common_latest))
    m2.metric("510880 数据", data_status["510880"]["last_date_str"], f"{data_status['510880']['rows']} 条")
    m3.metric("512890 数据", data_status["512890"]["last_date_str"], f"{data_status['512890']['rows']} 条")

    if common_latest is not None and common_latest.normalize() < requested_end_date:
        st.warning(
            f"你选择的结束日期是 {requested_end_date.strftime('%Y-%m-%d')}，"
            f"当前两只 ETF 共同可用数据截至 {_fmt_date(common_latest)}。"
            "这通常来自非交易日、接口尚未更新，或本次使用了本地缓存。"
        )

    st.caption(
        f"数据来源: AkShare fund_etf_hist_em，前复权日线。请求区间 "
        f"{pd.Timestamp(ctx['start_date']).strftime('%Y-%m-%d')} 至 "
        f"{requested_end_date.strftime('%Y-%m-%d')}。"
    )

    st.markdown("---")

    col1, col2 = st.columns(2)
    with col1:
        _render_status_card(statuses["510880"])
    with col2:
        _render_status_card(statuses["512890"])

    st.markdown("---")
    st.markdown("### 盯盘清单")

    rows = []
    for symbol in ["510880", "512890"]:
        s = statuses[symbol]
        if not s.get("is_ready"):
            rows.append({
                "代码": symbol,
                "名称": s["name"],
                "状态": s.get("message", "不可用"),
                "最新价": "—",
                "下轨": "—",
                "上轨": "—",
                "目标仓位": "—",
                "距下轨": "—",
                "距上轨": "—",
                "最近信号": "—",
            })
            continue

        last_signal = s["last_signal"]
        rows.append({
            "代码": symbol,
            "名称": s["name"],
            "状态": s["state_label"],
            "最新价": f"{s['close']:.3f}",
            "下轨": f"{s['lower_band']:.3f}",
            "上轨": f"{s['upper_band']:.3f}",
            "目标仓位": f"{s['target_position']:.0%}",
            "距下轨": f"{s['dist_to_lower']:.2%}",
            "距上轨": f"{s['dist_to_upper']:.2%}",
            "最近信号": (
                "暂无"
                if last_signal["date"] is None
                else f"{_fmt_date(last_signal['date'])} {last_signal['action']}"
            ),
        })

    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
