"""Combined signal and optimization tools."""
import streamlit as st

from components import tab_optimize, tab_signals


def render(ctx):
    """Render secondary strategy tools in one place."""
    st.markdown("### 策略工具")
    st.caption("信号流水用于复盘触发过程；参数优化用于研究布林带窗口和标准差。")

    tool = st.segmented_control(
        "工具",
        options=["信号流水", "参数优化"],
        default="信号流水",
    )

    st.markdown("---")
    if tool == "信号流水":
        tab_signals.render(ctx)
    else:
        tab_optimize.render(ctx)
