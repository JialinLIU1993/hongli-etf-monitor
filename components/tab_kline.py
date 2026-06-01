"""K-line and Bollinger band tab."""
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots


RANGE_OPTIONS = {
    "近1月": 22,
    "近2月": 44,
    "近3月": 66,
    "近6月": 120,
    "近1年": 242,
    "全部": None,
    "自定义": "custom",
}


def _slice_recent_rows(df, rows):
    """Return the most recent rows while keeping rolling indicators precomputed."""
    if rows is None or rows == "custom" or len(df) <= rows:
        return df.copy()
    return df.tail(rows).copy()


def _format_date(value):
    return value.strftime("%Y-%m-%d") if hasattr(value, "strftime") else str(value)


def render(ctx, title="K线与布林带", compact=False):
    """Render K-line and Bollinger bands for the selected ETF."""
    frames = ctx['frames']
    profiles = ctx['profiles']

    if title:
        st.markdown(f"### {title}")

    control_cols = st.columns([1.1, 2.4, 1.5])
    with control_cols[0]:
        etf_choice = st.radio("选择 ETF", ["510880", "512890"], horizontal=True)
    df_kline = frames[etf_choice].copy()
    profile = profiles[etf_choice]
    param_idx = 1 if etf_choice == "510880" else 2

    with control_cols[1]:
        range_choice = st.segmented_control(
            "显示区间",
            options=list(RANGE_OPTIONS.keys()),
            default="近3月",
            key=f"kline_range_{etf_choice}",
        )
    with control_cols[2]:
        show_volume = st.toggle("显示成交量", value=True, key=f"kline_volume_{etf_choice}")

    if range_choice == "自定义":
        min_date = df_kline.index.min().date()
        max_date = df_kline.index.max().date()
        default_start = _slice_recent_rows(df_kline, 66).index.min().date()
        selected_range = st.date_input(
            "自定义日期范围",
            value=(default_start, max_date),
            min_value=min_date,
            max_value=max_date,
            key=f"kline_custom_range_{etf_choice}",
        )
        if isinstance(selected_range, tuple) and len(selected_range) == 2:
            start_date, end_date = selected_range
            df_view = df_kline.loc[pd.Timestamp(start_date):pd.Timestamp(end_date)].copy()
        else:
            df_view = _slice_recent_rows(df_kline, 66)
    else:
        df_view = _slice_recent_rows(df_kline, RANGE_OPTIONS[range_choice])

    if df_view.empty:
        st.warning("当前选择区间内没有可展示数据。")
        return

    first_view_date = df_view.index.min()
    last_view_date = df_view.index.max()

    st.caption(
        f"{profile.name} | 布林带参数: Window={ctx[f'w{param_idx}']}, "
        f"Std={ctx[f'std{param_idx}']} | "
        f"当前显示 {_format_date(first_view_date)} 至 {_format_date(last_view_date)}，共 {len(df_view)} 个交易日"
    )

    fig_kline = make_subplots(
        rows=2 if show_volume else 1, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.72, 0.28] if show_volume else None
    )

    # 蜡烛图
    fig_kline.add_trace(go.Candlestick(
        x=df_view.index,
        open=df_view['open'],
        high=df_view['high'],
        low=df_view['low'],
        close=df_view['close'],
        name="K线",
        increasing_line_color='#ef4444',
        decreasing_line_color='#22c55e'
    ), row=1, col=1)

    # 布林带
    fig_kline.add_trace(go.Scatter(
        x=df_view.index, y=df_view['upper_band'],
        name="上轨", line=dict(color='#f59e0b', width=1, dash='dash')
    ), row=1, col=1)
    fig_kline.add_trace(go.Scatter(
        x=df_view.index, y=df_view['ma'],
        name="中轨", line=dict(color='#f59e0b', width=1)
    ), row=1, col=1)
    fig_kline.add_trace(go.Scatter(
        x=df_view.index, y=df_view['lower_band'],
        name="下轨", line=dict(color='#f59e0b', width=1, dash='dash'),
        fill='tonexty', fillcolor='rgba(251, 191, 36, 0.1)'
    ), row=1, col=1)

    # 买卖信号标记
    buys = df_view[df_view['signal'] > 0]
    sells = df_view[df_view['signal'] < 0]

    fig_kline.add_trace(go.Scatter(
        x=buys.index, y=buys['low'] * 0.99,
        mode='markers',
        name='买入',
        marker=dict(symbol='triangle-up', size=12, color='#ef4444')
    ), row=1, col=1)
    fig_kline.add_trace(go.Scatter(
        x=sells.index, y=sells['high'] * 1.01,
        mode='markers',
        name='卖出',
        marker=dict(symbol='triangle-down', size=12, color='#22c55e')
    ), row=1, col=1)

    if show_volume:
        colors = ['#ef4444' if df_view['close'].iloc[i] >= df_view['open'].iloc[i] else '#22c55e'
                  for i in range(len(df_view))]
        fig_kline.add_trace(go.Bar(
            x=df_view.index, y=df_view['volume'],
            name="成交量", marker_color=colors
        ), row=2, col=1)

    fig_kline.update_layout(
        template='plotly_white',
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        height=460 if compact else 620,
        xaxis_rangeslider_visible=False,
        dragmode="pan",
        hovermode="x unified",
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=20, r=20, t=64, b=20),
    )
    fig_kline.update_xaxes(
        gridcolor='#f3f4f6',
        rangebreaks=[dict(bounds=["sat", "mon"])],
        showspikes=True,
        spikemode="across",
        spikesnap="cursor",
        spikethickness=1,
        spikecolor="#9ca3af",
    )
    fig_kline.update_yaxes(gridcolor='#f3f4f6', fixedrange=False)

    st.plotly_chart(
        fig_kline,
        width="stretch",
        config={
            "scrollZoom": False,
            "displaylogo": False,
            "modeBarButtonsToRemove": ["select2d", "lasso2d", "zoom2d"],
        },
    )
