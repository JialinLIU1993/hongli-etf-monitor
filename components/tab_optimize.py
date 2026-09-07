"""Parameter search using the dashboard's data and strategy settings."""
from hashlib import sha256
import json

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.optimize import optimize_bollinger
from src.data_sources import PROVIDER_LABELS

METRIC_LABELS = {
    "Total Return": "总收益率",
    "Sharpe Ratio": "夏普比率",
    "Max Drawdown": "最大回撤",
}


def optimization_signature(df, symbol, grid_mode, settings):
    """Identify both prices and parameters so old results cannot be mislabelled."""
    digest = sha256(pd.util.hash_pandas_object(df, index=True).values.tobytes())
    digest.update(json.dumps([symbol, grid_mode, settings], sort_keys=True).encode())
    return digest.hexdigest()


@st.cache_data(show_spinner=False, max_entries=12)
def run_optimization(df, grid_mode, settings):
    step = 10 if grid_mode == "粗略 (快)" else 5
    std_tick_step = 3 if grid_mode == "粗略 (快)" else 1
    windows = sorted(set(range(10, 95, step)) | {settings["window"]})
    windows = [window for window in windows if window <= len(df)]
    if not windows:
        return pd.DataFrame()
    num_stds = sorted(set(np.arange(15, 36, std_tick_step) / 10) | {round(settings["num_std"], 1)})
    results = optimize_bollinger(
        df, windows=windows, num_stds=num_stds,
        first_batch_pct=settings["first_batch_pct"], scale_threshold=settings["scale_threshold"],
        pyramid_levels=settings["pyramid_levels"], pyramid_sizes=settings["pyramid_sizes"],
    )
    return results.rename(columns={"window": "Window", "num_std": "StdDev"})


def render(ctx):
    st.markdown("### 布林带参数搜索")
    st.caption("选择标的和比较目标，运行一次即可切换查看各项表现。首批仓位等规则沿用当前策略设置。")
    columns = st.columns(3)
    with columns[0]:
        symbol = st.radio("选择 ETF", list(ctx["profiles"]), horizontal=True, key="opt_etf")
    with columns[1]:
        metric = st.selectbox("优化目标", list(METRIC_LABELS), format_func=METRIC_LABELS.get, key="opt_metric")
    with columns[2]:
        grid_mode = st.selectbox("网格精度", ["粗略 (快)", "精细 (慢)"], key="opt_grid")

    df = ctx["raw_data"][symbol]
    if df.empty or len(df) < 10:
        st.info("当前区间有效行情不足 10 个交易日，请扩大数据区间后再优化。")
        return
    idx = 1 if symbol == "510880" else 2
    settings = {
        "provider": ctx.get("provider", "akshare"),
        "price_basis": ctx.get("price_basis", "前复权"),
        "window": ctx[f"w{idx}"], "num_std": round(ctx[f"std{idx}"], 1),
        "first_batch_pct": ctx[f"batch{idx}"], "scale_threshold": ctx["scale_threshold"],
        "pyramid_levels": ctx.get("pyramid_levels", []), "pyramid_sizes": ctx.get("pyramid_sizes", []),
    }
    signature = optimization_signature(df, symbol, grid_mode, settings)
    if st.button("开始优化", key="run_opt", type="primary"):
        with st.spinner(f"正在计算 {symbol} 的参数组合…"):
            results = run_optimization(df, grid_mode, settings)
        st.session_state["optimization_result"] = {"signature": signature, "results": results}

    saved = st.session_state.get("optimization_result")
    if saved is None:
        st.info("点击“开始优化”运行搜索。完成后可直接切换优化目标查看同一批结果。")
        return
    if saved["signature"] != signature:
        st.info("行情、ETF 或策略参数已变化，请点击“开始优化”更新结果。")
        return
    results = saved["results"]
    if results.empty:
        st.warning("当前数据没有可计算的参数组合。")
        return

    st.caption(
        f"{settings['price_basis']} · {df.index.min():%Y-%m-%d} 至 {df.index.max():%Y-%m-%d} · {len(df)} 个交易日 · "
        f"{len(results)} 组参数 · 首批仓位 {settings['first_batch_pct']:.0%}。"
        "结果为所选历史区间内回测，未进行样本外验证；回撤越接近 0 越小。"
    )
    percent_metric = metric in {"Total Return", "Max Drawdown"}
    best = results.loc[results[metric].idxmax()]
    best_columns = st.columns(3)
    best_columns[0].metric("区间内最优周期", int(best["Window"]))
    best_columns[1].metric("区间内最优标准差", f"{best['StdDev']:.1f}")
    best_columns[2].metric(METRIC_LABELS[metric], f"{best[metric]:.2%}" if percent_metric else f"{best[metric]:.2f}")

    pivot = results.pivot(index="StdDev", columns="Window", values=metric).sort_index()
    text_values = [[f"{value:.1%}" if percent_metric else f"{value:.2f}" for value in row]
                   for row in pivot.values]
    fig = go.Figure(go.Heatmap(
        z=pivot.values, x=pivot.columns.tolist(), y=pivot.index.tolist(), text=text_values,
        texttemplate="%{text}" if len(results) <= 100 else None, textfont=dict(size=10),
        colorscale="Blues",
        colorbar=dict(title=METRIC_LABELS[metric], tickformat=".0%" if percent_metric else ".1f"),
        hovertemplate="周期=%{x}<br>标准差=%{y}<br>" + METRIC_LABELS[metric] + "=%{text}<extra></extra>",
    ))
    if settings["window"] in pivot.columns and settings["num_std"] in pivot.index:
        fig.add_trace(go.Scatter(
            x=[settings["window"]], y=[settings["num_std"]], mode="markers",
            marker=dict(symbol="star", size=17, color="#111827", line=dict(width=2, color="white")),
            name="当前参数",
        ))
    fig.update_layout(
        template="plotly_white", paper_bgcolor="rgba(0,0,0,0)",
        xaxis_title="布林周期", yaxis_title="标准差倍数", height=500,
        margin=dict(l=20, r=20, t=35, b=30),
    )
    st.plotly_chart(fig, width="stretch", key="optimization_heatmap")
    with st.expander("前 10 组参数"):
        top = results.nlargest(10, metric).copy()
        for column in ("Total Return", "Max Drawdown"):
            top[column] = top[column].map(lambda value: f"{value:.2%}")
        top["Sharpe Ratio"] = top["Sharpe Ratio"].map(lambda value: f"{value:.2f}")
        st.dataframe(top, width="stretch", hide_index=True)
    export = results.assign(
        代码=symbol, 行情来源=PROVIDER_LABELS[settings["provider"]], 价格口径=settings["price_basis"],
        数据开始=df.index.min().strftime("%Y-%m-%d"), 数据结束=df.index.max().strftime("%Y-%m-%d"),
    )
    st.download_button("导出全部优化结果", export.to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"{symbol}_{settings['provider']}_bollinger_optimization.csv",
                       mime="text/csv", width="stretch")
