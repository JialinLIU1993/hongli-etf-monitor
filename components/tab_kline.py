"""K-line and Bollinger band tab."""
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from src.monitoring import summarize_monitor_status


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


def _status_tone(status):
    state = status.get("state", "watch")
    return {
        "buy": ("买入触发", "#ef4444", "rgba(254, 242, 242, 0.94)"),
        "sell": ("卖出触发", "#22c55e", "rgba(240, 253, 244, 0.94)"),
        "watch": ("通道观察", "#2563eb", "rgba(239, 246, 255, 0.94)"),
    }.get(state, ("观察", "#2563eb", "rgba(239, 246, 255, 0.94)"))


def _add_monitor_annotations(fig, status, row=1, col=1):
    """Add current monitor state directly onto the K-line chart."""
    if not status.get("is_ready"):
        return

    label, color, bg = _status_tone(status)
    close = status["close"]
    date = status["date"]
    lower = status["lower_band"]
    upper = status["upper_band"]

    fig.add_hline(
        y=close,
        line_width=1,
        line_dash="dot",
        line_color=color,
        opacity=0.75,
        row=row,
        col=col,
    )
    fig.add_trace(
        go.Scatter(
            x=[date],
            y=[close],
            mode="markers",
            name="日线收盘",
            marker=dict(size=9, color=color, line=dict(width=2, color="#ffffff")),
            hovertemplate="日线收盘 %{y:.3f}<extra></extra>",
            showlegend=False,
        ),
        row=row,
        col=col,
    )

    fig.add_annotation(
        x=date,
        y=close,
        xanchor="left",
        yanchor="middle",
        showarrow=True,
        arrowhead=2,
        arrowsize=1,
        arrowwidth=1,
        arrowcolor=color,
        ax=34,
        ay=-24,
        bgcolor="rgba(255,255,255,0.92)",
        bordercolor=color,
        borderwidth=1,
        borderpad=4,
        font=dict(size=11, color="#111827"),
        text=f"收盘 {close:.3f}",
        row=row,
        col=col,
    )


def render(ctx, title="K线与布林带", compact=False, symbol=None):
    """Render K-line and Bollinger bands for the selected ETF."""
    frames = ctx['frames']
    profiles = ctx['profiles']

    if title:
        st.markdown(f"### {title}")

    etf_choice = symbol or st.radio("选择 ETF", ["510880", "512890"], horizontal=True, key="chart_etf")
    control_cols = st.columns([4, 1], vertical_alignment="bottom")
    df_kline = frames[etf_choice].copy()
    profile = profiles[etf_choice]
    status = ctx["statuses"].get(etf_choice, {})
    param_idx = 1 if etf_choice == "510880" else 2
    if df_kline.empty:
        st.info(f"{profile.name} 暂无可用行情，请调整数据区间或刷新。")
        return

    with control_cols[0]:
        range_choice = st.segmented_control(
            "显示区间",
            options=list(RANGE_OPTIONS.keys()),
            default=None if f"kline_range_{etf_choice}" in st.session_state else "近3月",
            key=f"kline_range_{etf_choice}",
        ) or "近3月"
    with control_cols[1]:
        with st.popover("图表设置"):
            chart_type = st.radio("图表类型", ["K线", "收盘线"], key="kline_type")
            has_volume = "volume" in df_kline.columns and df_kline["volume"].notna().any()
            show_volume = st.toggle("显示成交量", value=False if f"kline_volume_{etf_choice}" in st.session_state else bool(has_volume), disabled=not has_volume,
                                    key=f"kline_volume_{etf_choice}") and has_volume

    if range_choice == "自定义":
        min_date = df_kline.index.min().date()
        max_date = df_kline.index.max().date()
        default_start = _slice_recent_rows(df_kline, 66).index.min().date()
        saved_range_key = f"kline_custom_range_{etf_choice}"
        saved_range = st.session_state.get(saved_range_key, (default_start, max_date))
        saved_range = tuple(min(max(day, min_date), max_date) for day in saved_range)
        selected_range = st.date_input(
            "自定义日期范围",
            value=saved_range,
            min_value=min_date,
            max_value=max_date,
            key=f"_kline_custom_range_{etf_choice}",
        )
        st.session_state[saved_range_key] = selected_range
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
    # Historical ranges must annotate their own final day, never an off-screen latest quote.
    if status.get("date") != last_view_date:
        status = summarize_monitor_status(
            df_kline.loc[:last_view_date], symbol=etf_choice, name=profile.name,
            role=profile.role, window=ctx[f"w{param_idx}"], num_std=ctx[f"std{param_idx}"],
            first_batch_pct=ctx[f"batch{param_idx}"],
        )

    st.caption(
        f"{ctx.get('price_basis', '前复权')} · {ctx[f'w{param_idx}']} 日 / {ctx[f'std{param_idx}']} 倍标准差 · "
        f"当前显示 {_format_date(first_view_date)} 至 {_format_date(last_view_date)}，共 {len(df_view)} 个交易日"
    )
    if show_volume and ctx.get("provider") == "hithink":
        st.caption("成交量保留接口原始单位；官方 ETF 文档未注明份/手，未作单位换算。")

    fig_kline = make_subplots(
        rows=2 if show_volume else 1, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.72, 0.28] if show_volume else None
    )

    if chart_type == "K线":
        fig_kline.add_trace(go.Candlestick(
            x=df_view.index, open=df_view['open'], high=df_view['high'],
            low=df_view['low'], close=df_view['close'], name="K线",
            increasing_line_color='#be3e47', decreasing_line_color='#188568',
            increasing_fillcolor='#be3e47', decreasing_fillcolor='#188568',
        ), row=1, col=1)
    else:
        fig_kline.add_trace(go.Scatter(
            x=df_view.index, y=df_view['close'], name="收盘价",
            line=dict(color='#202938', width=2),
            hovertemplate="收盘 %{y:.3f}<extra></extra>",
        ), row=1, col=1)

    # 布林带
    fig_kline.add_trace(go.Scatter(
        x=df_view.index, y=df_view['upper_band'],
        name="上轨", line=dict(color='#6b8bc5', width=1, dash='dash')
    ), row=1, col=1)
    fig_kline.add_trace(go.Scatter(
        x=df_view.index, y=df_view['lower_band'],
        name="下轨", line=dict(color='#6b8bc5', width=1, dash='dash'),
        fill='tonexty', fillcolor='rgba(75, 113, 182, 0.055)'
    ), row=1, col=1)
    fig_kline.add_trace(go.Scatter(
        x=df_view.index, y=df_view['ma'],
        name="中轨", line=dict(color='#6b8bc5', width=1)
    ), row=1, col=1)

    # 买卖信号标记
    buys = df_view[df_view['signal'] > 0]
    sells = df_view[df_view['signal'] < 0]

    fig_kline.add_trace(go.Scatter(
        x=buys.index, y=buys['low'] * 0.99,
        mode='markers',
        name='买入',
        marker=dict(symbol='triangle-up', size=12, color='#be3e47')
    ), row=1, col=1)
    fig_kline.add_trace(go.Scatter(
        x=sells.index, y=sells['high'] * 1.01,
        mode='markers',
        name='卖出',
        marker=dict(symbol='triangle-down', size=12, color='#188568')
    ), row=1, col=1)

    if show_volume:
        colors = ['#be3e47' if df_view['close'].iloc[i] >= df_view['open'].iloc[i] else '#188568'
                  for i in range(len(df_view))]
        fig_kline.add_trace(go.Bar(
            x=df_view.index, y=df_view['volume'],
            name="成交量", marker_color=colors
        ), row=2, col=1)

    _add_monitor_annotations(fig_kline, status)

    fig_kline.update_layout(
        template='plotly_white',
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        height=440 if compact else 560,
        font=dict(family="Arial, sans-serif", color="#667085", size=11),
        uirevision=f"{etf_choice}:{range_choice}:{first_view_date}:{last_view_date}",
        xaxis_rangeslider_visible=False,
        dragmode="pan",
        hovermode="x unified",
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=0, r=50, t=34, b=15),
    )
    fig_kline.update_xaxes(
        gridcolor='#f3f4f6',
        tickformat='%m/%d', hoverformat='%Y-%m-%d',
        rangebreaks=[dict(bounds=["sat", "mon"])],
        showspikes=True,
        spikemode="across",
        spikesnap="cursor",
        spikethickness=1,
        spikecolor="#9ca3af",
    )
    fig_kline.update_yaxes(gridcolor='#eff2f6', fixedrange=False, side='right')
    fig_kline.update_yaxes(tickformat='.3f', row=1, col=1)

    st.plotly_chart(
        fig_kline, width="stretch", key=f"kline_chart_{etf_choice}",
        config={"scrollZoom": False, "displaylogo": False,
                "modeBarButtonsToRemove": ["select2d", "lasso2d", "zoom2d"]},
    )
    return {"status": status, "last_date": last_view_date, "first_date": first_view_date}
