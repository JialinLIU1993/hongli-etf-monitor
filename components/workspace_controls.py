"""Global navigation and on-demand workspace controls."""
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from src.config import BOLLINGER_510880, BOLLINGER_512890
from src.data_sources import PROVIDER_LABELS, PRICE_BASIS_LABELS, get_hithink_api_key, resolve_provider


def _configured_api_key():
    api_key = get_hithink_api_key()
    if api_key:
        return api_key
    try:
        return str(st.secrets.get("HITHINK_FINANCE_API_KEY", "")).strip()
    except (FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
        return ""


def percent_slider(label, min_pct, max_pct, default_pct, step_pct=1, *, key=None, help=None):
    """Render an integer-percent slider and return a 0-1 float."""
    value_pct = st.slider(
        label,
        min_value=min_pct,
        max_value=max_pct,
        value=default_pct,
        step=step_pct,
        format="%d%%",
        key=key,
        help=help,
    )
    return value_pct / 100


def percent_slider_float(label, min_pct, max_pct, default_pct, step_pct=0.5, *, key=None, help=None):
    """Render a float-percent slider and return a 0-1 float."""
    value_pct = st.slider(
        label,
        min_value=min_pct,
        max_value=max_pct,
        value=default_pct,
        step=step_pct,
        format="%.1f%%",
        key=key,
        help=help,
    )
    return value_pct / 100


def _connection():
    try:
        default_provider = resolve_provider()
    except ValueError:
        default_provider = "akshare"
        st.warning("环境中的行情来源无效，请重新选择。")
    provider = st.selectbox("行情来源", list(PROVIDER_LABELS),
                            index=list(PROVIDER_LABELS).index(default_provider),
                            format_func=PROVIDER_LABELS.get, key="data_provider")
    api_key = ""
    st.caption(f"价格口径：{PRICE_BASIS_LABELS[provider]}")
    if provider == "hithink":
        configured_key = _configured_api_key()
        with st.expander("同花顺 API 设置", expanded=not bool(configured_key)):
            api_key = st.text_input(
                "API Key", type="password", key="hithink_api_key_input",
                help="仅用于本次页面会话；不会写入代码、行情缓存或投资记录。",
            ).strip() or configured_key
            if configured_key:
                st.caption("已读取环境或私密配置中的 Key；上方输入可临时覆盖。")
            if not api_key:
                st.info("请填写 API Key 后加载同花顺行情。也可先切换到 AkShare。")
            st.link_button("申请 API Key", "https://fuyao.aicubes.cn/admin/")
        st.caption("ETF 接口不提供复权选项，策略结果可能与前复权行情不同。")

    return provider, api_key


def _date_range():
    date_preset = st.radio(
        "快捷选择",
        ["近1年", "近3年", "近5年", "全部", "自定义"],
        horizontal=True,
        label_visibility="collapsed",
    )

    now = datetime.now(ZoneInfo("Asia/Shanghai")).date()
    if date_preset == "近1年":
        start_date = (pd.Timestamp(now) - pd.DateOffset(years=1)).date()
    elif date_preset == "近3年":
        start_date = (pd.Timestamp(now) - pd.DateOffset(years=3)).date()
    elif date_preset == "近5年":
        start_date = (pd.Timestamp(now) - pd.DateOffset(years=5)).date()
    elif date_preset == "全部":
        start_date = datetime(2015, 1, 1).date()
    else:
        start_date = st.date_input("开始日期", value=datetime(2020, 1, 1), max_value=now)

    end_date = st.date_input("结束日期", value=now, max_value=now)
    if start_date > end_date:
        st.error("开始日期不能晚于结束日期，请调整数据区间。")
        st.stop()

    return start_date, end_date


def _strategy():
    st.caption("调整参数后，图表和信号会同步计算。")

    st.markdown("**510880 红利 ETF**")
    w1 = st.number_input(
        "510880 布林周期",
        value=BOLLINGER_510880["window"],
        min_value=5,
        max_value=250,
        step=1,
        key="w1",
    )
    std1 = st.number_input(
        "510880 标准差倍数",
        value=float(BOLLINGER_510880["num_std"]),
        min_value=0.5,
        max_value=5.0,
        step=0.1,
        key="std1",
    )
    batch1 = percent_slider(
        "510880 首批仓位",
        10,
        100,
        int(BOLLINGER_510880["first_batch_pct"] * 100),
        10,
        key="b1_pct",
    )

    st.markdown("**512890 红利低波**")
    w2 = st.number_input(
        "512890 布林周期",
        value=BOLLINGER_512890["window"],
        min_value=5,
        max_value=250,
        step=1,
        key="w2",
    )
    std2 = st.number_input(
        "512890 标准差倍数",
        value=float(BOLLINGER_512890["num_std"]),
        min_value=0.5,
        max_value=5.0,
        step=0.1,
        key="std2",
    )
    batch2 = percent_slider(
        "512890 首批仓位",
        10,
        100,
        int(BOLLINGER_512890["first_batch_pct"] * 100),
        10,
        key="b2_pct",
    )

    scale_threshold = percent_slider_float(
        "深度触发阈值",
        0.5,
        5.0,
        2.0,
        0.5,
        key="scale_threshold_pct",
        help="跌破下轨超过该比例时满仓，突破上轨超过该比例时清仓。",
    )

    pyramid_enabled = st.checkbox(
        "金字塔加仓",
        value=False,
        help="跌破下轨后按深度分三档逐步加仓，替代简单分批。",
    )
    if pyramid_enabled:
        pyr_l1 = percent_slider_float("第1档深度", 0.5, 3.0, 1.0, 0.5, key="pyr_l1_pct")
        pyr_l2 = percent_slider_float("第2档深度", 1.0, 5.0, 2.0, 0.5, key="pyr_l2_pct")
        pyr_l3 = percent_slider_float("第3档深度", 2.0, 8.0, 3.0, 0.5, key="pyr_l3_pct")
        pyramid_levels = [pyr_l1, pyr_l2, pyr_l3]
        pyramid_sizes = [0.3, 0.3, 0.4]
        if not pyr_l1 < pyr_l2 < pyr_l3:
            st.error("金字塔深度必须满足：第1档 < 第2档 < 第3档。")
            st.stop()
    else:
        pyramid_levels = []
        pyramid_sizes = []

    return {
        "w1": int(w1),
        "std1": float(std1),
        "batch1": batch1,
        "w2": int(w2),
        "std2": float(std2),
        "batch2": batch2,
        "scale_threshold": scale_threshold,
        "pyramid_levels": pyramid_levels,
        "pyramid_sizes": pyramid_sizes,
    }


def render_controls():
    """The shell owns global choices; pages only receive validated settings."""
    st.markdown('<header class="appbar"><div class="wordmark"><span class="wordmark-icon">双</span>红利双雄<span class="wordmark-sub">投资工作台</span></div><span class="market-label">沪深 ETF · 日线策略</span></header>', unsafe_allow_html=True)
    with st.container(key="workspace-toolbar"):
        navigation, actions = st.columns([1, 1.15], vertical_alignment="center")
        with navigation:
            page = st.segmented_control("页面", ["行情总览", "持仓记录", "信号复盘", "参数研究"],
                                        default="行情总览", key="workspace_nav", label_visibility="collapsed") or "行情总览"
        with actions:
            with st.container(horizontal=True, horizontal_alignment="right", vertical_alignment="center", gap="small"):
                with st.popover("行情连接"):
                    provider, api_key = _connection()
                with st.popover("数据范围"):
                    start_date, end_date = _date_range()
                with st.popover("策略参数"):
                    settings = _strategy()
                force_update = st.button("刷新行情数据", key="workspace_refresh", icon=":material/refresh:", help="重新获取行情，常规页面操作复用 5 分钟内的缓存。")
    return dict(settings, page=page, provider=provider, api_key=api_key,
                start_date=start_date, end_date=end_date, force_update=force_update)
