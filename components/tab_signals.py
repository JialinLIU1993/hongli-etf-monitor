"""Signal history tab."""
import pandas as pd
import streamlit as st


def _signal_rows(frame, symbol, name):
    rows = frame[frame["signal"].fillna(0) != 0].copy()
    if rows.empty:
        return pd.DataFrame()

    rows = rows.tail(80).reset_index(names="date")
    rows["代码"] = symbol
    rows["名称"] = name
    rows["日期"] = rows["date"].dt.strftime("%Y-%m-%d")
    rows["方向"] = rows["signal"].apply(lambda v: "加仓" if v > 0 else "减仓")
    rows["仓位变化"] = rows["signal"].apply(lambda v: f"{v:+.0%}")
    rows["目标仓位"] = rows["position"].apply(lambda v: f"{v:.0%}")
    rows["收盘价"] = rows["close"].apply(lambda v: f"{v:.3f}")
    rows["下轨"] = rows["lower_band"].apply(lambda v: f"{v:.3f}")
    rows["上轨"] = rows["upper_band"].apply(lambda v: f"{v:.3f}")
    return rows[["日期", "代码", "名称", "方向", "仓位变化", "目标仓位", "收盘价", "下轨", "上轨"]]


def render(ctx):
    """Render recent Bollinger signal history."""
    st.markdown("### 布林带信号流水")
    st.caption("这里展示盯盘规则生成的目标仓位变化，不再展示完整资金曲线回测交易账本。")

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

    direction = st.segmented_control(
        "筛选方向",
        options=["全部", "加仓", "减仓"],
        default="全部",
    )
    symbol = st.segmented_control(
        "筛选 ETF",
        options=["全部", "510880", "512890"],
        default="全部",
    )

    filtered = signal_df.copy()
    if direction != "全部":
        filtered = filtered[filtered["方向"] == direction]
    if symbol != "全部":
        filtered = filtered[filtered["代码"] == symbol]

    st.dataframe(filtered.sort_values("日期", ascending=False), width="stretch", hide_index=True)

    csv = filtered.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "导出信号流水",
        csv,
        file_name="bollinger_watch_signals.csv",
        mime="text/csv",
        width="stretch",
    )
