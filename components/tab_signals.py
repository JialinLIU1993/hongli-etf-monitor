"""Signal history tab."""
import pandas as pd
import streamlit as st


def _signal_rows(frame, symbol, name):
    if frame.empty:
        return pd.DataFrame()
    rows = frame[frame["signal"].fillna(0) != 0].copy()
    if rows.empty:
        return pd.DataFrame()

    rows = rows.reset_index(names="date")
    rows["代码"] = symbol
    rows["名称"] = name
    rows["来源"] = frame.attrs.get("provider", "akshare")
    rows["价格口径"] = frame.attrs.get("price_basis", "前复权")
    rows["日期"] = rows["date"].dt.strftime("%Y-%m-%d")
    rows["方向"] = rows["signal"].apply(lambda v: "加仓" if v > 0 else "减仓")
    rows["仓位变化"] = rows["signal"].apply(lambda v: f"{v:+.0%}")
    rows["目标仓位"] = rows["position"].apply(lambda v: f"{v:.0%}")
    rows["收盘价"] = rows["close"].apply(lambda v: f"{v:.3f}")
    rows["下轨"] = rows["lower_band"].apply(lambda v: f"{v:.3f}")
    rows["上轨"] = rows["upper_band"].apply(lambda v: f"{v:.3f}")
    return rows[["日期", "代码", "名称", "方向", "仓位变化", "目标仓位", "收盘价", "下轨", "上轨", "来源", "价格口径"]]


def render(ctx):
    """Render recent Bollinger signal history."""
    st.markdown("### 调仓信号")
    st.caption("策略生成的目标仓位变化；实际成交请在持仓记录中管理。")

    frames = []
    for symbol in ["510880", "512890"]:
        profile = ctx["profiles"][symbol]
        frames.append(_signal_rows(ctx["frames"][symbol], symbol, profile.name))

    signal_df = pd.concat([df for df in frames if not df.empty], ignore_index=True) if any(
        not df.empty for df in frames
    ) else pd.DataFrame()

    if signal_df.empty:
        st.info("当前区间内暂未出现调仓信号。")
        return

    metrics = st.columns(3)
    metrics[0].metric("调仓信号", len(signal_df))
    metrics[1].metric("加仓次数", int((signal_df["方向"] == "加仓").sum()))
    metrics[2].metric("减仓次数", int((signal_df["方向"] == "减仓").sum()))
    left, right = st.columns(2)
    with left:
        direction = st.segmented_control("筛选方向", ["全部", "加仓", "减仓"],
                                         default=None if "signal_filter_direction" in st.session_state else "全部", key="signal_filter_direction")
    with right:
        symbol = st.segmented_control("筛选 ETF", ["全部", "510880", "512890"],
                                      default=None if "signal_filter_symbol" in st.session_state else "全部", key="signal_filter_symbol")

    filtered = signal_df.copy()
    if direction and direction != "全部":
        filtered = filtered[filtered["方向"] == direction]
    if symbol and symbol != "全部":
        filtered = filtered[filtered["代码"] == symbol]

    filtered = filtered.sort_values("日期", ascending=False)
    st.caption(f"共 {len(filtered)} 条调仓信号，覆盖所选完整数据区间。")
    st.dataframe(filtered, width="stretch", hide_index=True, height=min(560, 38 + 35 * len(filtered)))

    csv = filtered.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "导出信号流水",
        csv,
        file_name="bollinger_watch_signals.csv",
        mime="text/csv",
        width="stretch",
    )
