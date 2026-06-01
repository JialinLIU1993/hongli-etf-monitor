"""Sidebar controls for the ETF monitoring app."""
from datetime import datetime

import streamlit as st

from src.config import BOLLINGER_510880, BOLLINGER_512890


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


def render_sidebar():
    """Render monitoring settings and return them as a dictionary."""
    with st.sidebar:
        st.markdown("### 盯盘设置")

        st.markdown("**数据区间**")
        date_preset = st.radio(
            "快捷选择",
            ["近1年", "近3年", "近5年", "全部", "自定义"],
            horizontal=True,
            label_visibility="collapsed",
        )

        now = datetime.now()
        if date_preset == "近1年":
            start_date = datetime(now.year - 1, now.month, now.day)
        elif date_preset == "近3年":
            start_date = datetime(now.year - 3, now.month, now.day)
        elif date_preset == "近5年":
            start_date = datetime(now.year - 5, now.month, now.day)
        elif date_preset == "全部":
            start_date = datetime(2015, 1, 1)
        else:
            start_date = st.date_input("开始日期", value=datetime(2020, 1, 1))

        end_date = st.date_input("结束日期", value=now)

        st.divider()

        force_update = False
        if st.button("刷新 AkShare 数据", width="stretch"):
            st.cache_data.clear()
            force_update = True

        st.divider()

        with st.expander("布林带参数", expanded=True):
            st.caption("保留原项目的数据源、默认布林带参数和分批仓位规则。")

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
            else:
                pyramid_levels = []
                pyramid_sizes = []

    return {
        "start_date": start_date,
        "end_date": end_date,
        "force_update": force_update,
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
