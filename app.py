"""Application shell: controls → shared data context → focused workspace."""
import logging
import streamlit as st
from components import tab_dashboard, tab_investments, tab_signals, tab_optimize
from components.workspace_controls import render_controls
from components.workspace_context import build_context
from components.styles import CUSTOM_CSS
from src.data_sources import PROVIDER_LABELS

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
st.set_page_config(page_title="红利双雄 · 投资工作台", page_icon="◈", layout="wide", initial_sidebar_state="collapsed")
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
cfg = render_controls()

# Keep view preferences when navigating to a workspace without those widgets.
for state_key in list(st.session_state):
    if state_key.startswith(("kline_", "opt_", "signal_filter_")) or state_key == "chart_etf":
        st.session_state[state_key] = st.session_state[state_key]
with st.spinner("正在准备行情…"):
    ctx, warnings = build_context(cfg)
for warning in warnings:
    st.warning(warning)

page = cfg["page"]
if page == "行情总览":
    tab_dashboard.render(ctx)
else:
    descriptions = {
        "持仓记录": ("我的持仓", "从成交记录查看资产与收益"),
        "信号复盘": ("调仓复盘", "还原信号发生时的价格与仓位"),
        "参数研究": ("策略实验", "在历史行情中比较参数表现"),
    }
    title, description = descriptions[page]
    st.markdown(f'<div class="workspace-title"><h1>{title}</h1><p>{description}</p></div>', unsafe_allow_html=True)
    if page == "持仓记录":
        tab_investments.render(ctx, show_title=False, compact=True)
    elif page == "信号复盘":
        tab_signals.render(ctx)
    else:
        tab_optimize.render(ctx)
st.caption(f"行情来源：{PROVIDER_LABELS[ctx['provider']]} · {ctx['price_basis']} · 数据范围 {ctx['start_date']:%Y.%m.%d} — {ctx['end_date']:%Y.%m.%d}")
st.markdown('<footer class="workspace-footer"><span>红利双雄 / 投资工作台</span><span>策略目标不等于实际持仓 · 信号仅供参考</span></footer>', unsafe_allow_html=True)
