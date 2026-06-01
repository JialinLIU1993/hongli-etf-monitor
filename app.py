"""红利双雄 ETF 盯盘看板."""
import logging

import pandas as pd
import streamlit as st

from components import tab_kline, tab_monitor, tab_optimize, tab_signals
from components.sidebar import render_sidebar
from components.styles import CUSTOM_CSS
from src.data_loader import fetch_etf_data
from src.monitoring import (
    ETF_PROFILES,
    calculate_monitor_frame,
    summarize_data_status,
    summarize_monitor_status,
)


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")


st.set_page_config(
    page_title="红利双雄 ETF 盯盘",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

st.markdown(
    """
    <div style="padding: 0.75rem 0 1rem 0;">
        <h1 style="font-size: 2.35rem; margin-bottom: 0.35rem;">红利双雄 ETF 盯盘</h1>
        <p style="color: #4b5563; font-size: 1.05rem; margin: 0;">
            510880 红利 ETF + 512890 红利低波 | AkShare 日线 | 布林带触发价与目标仓位
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

cfg = render_sidebar()


@st.cache_data(show_spinner=False)
def load_data(symbol, start, end, force=False):
    """Load ETF data using the original AkShare-backed data source."""
    start_str = start.strftime("%Y%m%d") if hasattr(start, "strftime") else start
    end_str = end.strftime("%Y%m%d") if hasattr(end, "strftime") else end
    return fetch_etf_data(symbol, start_date=start_str, end_date=end_str, force_update=force)


with st.spinner("正在加载两只 ETF 的盯盘数据..."):
    raw_data = {
        symbol: load_data(symbol, cfg["start_date"], cfg["end_date"], cfg["force_update"])
        for symbol in ["510880", "512890"]
    }

if any(df.empty for df in raw_data.values()):
    st.error("数据加载失败，请检查网络连接或本地缓存后重试。")
    st.stop()

frames = {}
statuses = {}
data_status = {}

for idx, symbol in enumerate(["510880", "512890"], start=1):
    profile = ETF_PROFILES[symbol]
    window = cfg[f"w{idx}"]
    num_std = cfg[f"std{idx}"]
    first_batch_pct = cfg[f"batch{idx}"]
    frame = calculate_monitor_frame(
        raw_data[symbol],
        window=window,
        num_std=num_std,
        first_batch_pct=first_batch_pct,
        scale_threshold=cfg["scale_threshold"],
        pyramid_levels=cfg["pyramid_levels"],
        pyramid_sizes=cfg["pyramid_sizes"],
    )
    frames[symbol] = frame
    data_status[symbol] = summarize_data_status(raw_data[symbol], symbol)
    statuses[symbol] = summarize_monitor_status(
        frame,
        symbol=symbol,
        name=profile.name,
        role=profile.role,
        window=window,
        num_std=num_std,
        first_batch_pct=first_batch_pct,
    )


ctx = {
    "profiles": ETF_PROFILES,
    "raw_data": raw_data,
    "frames": frames,
    "statuses": statuses,
    "data_status": data_status,
    "start_date": cfg["start_date"],
    "end_date": cfg["end_date"],
    "w1": cfg["w1"],
    "std1": cfg["std1"],
    "batch1": cfg["batch1"],
    "w2": cfg["w2"],
    "std2": cfg["std2"],
    "batch2": cfg["batch2"],
    "scale_threshold": cfg["scale_threshold"],
}

tab1, tab2, tab3, tab4 = st.tabs(["盯盘总览", "K线图表", "信号流水", "参数优化"])

with tab1:
    tab_monitor.render(ctx)
with tab2:
    tab_kline.render(ctx)
with tab3:
    tab_signals.render(ctx)
with tab4:
    tab_optimize.render(ctx)

st.markdown("---")
st.markdown(
    """
    <div style="text-align: center; color: #6b7280; font-size: 0.85rem;">
        红利双雄 ETF 盯盘 | 数据来源: AkShare | 布林带信号仅供参考，投资需谨慎
    </div>
    """,
    unsafe_allow_html=True,
)
