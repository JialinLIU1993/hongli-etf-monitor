"""Tab5: 参数优化热力图"""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

from src.data_loader import fetch_etf_data
from src.strategies import BollingerBandsStrategy
from src.backtest import BacktestEngine


def render(ctx):
    """渲染参数优化热力图 Tab。"""
    st.markdown("### 🔬 布林带参数优化热力图")
    st.caption("通过网格搜索找到 Window × StdDev 的最优组合")

    opt_col1, opt_col2, opt_col3 = st.columns(3)
    with opt_col1:
        opt_etf = st.radio("选择 ETF", ["510880", "512890"], horizontal=True, key="opt_etf")
    with opt_col2:
        opt_metric = st.selectbox("优化目标", ["Total Return", "Sharpe Ratio", "Max Drawdown"], key="opt_metric")
    with opt_col3:
        opt_grid = st.selectbox("网格精度", ["粗略 (快)", "精细 (慢)"], key="opt_grid")

    metric_labels = {
        "Total Return": "总收益率",
        "Sharpe Ratio": "夏普比率",
        "Max Drawdown": "最大回撤"
    }

    @st.cache_data(show_spinner=False)
    def run_optimization(symbol, start, end, grid_mode):
        """Cached grid search optimization."""
        start_str = start.strftime("%Y%m%d") if hasattr(start, 'strftime') else start
        end_str = end.strftime("%Y%m%d") if hasattr(end, 'strftime') else end
        df = fetch_etf_data(symbol, start_date=start_str, end_date=end_str)
        if df.empty:
            return pd.DataFrame()

        if grid_mode == "粗略 (快)":
            windows = range(10, 95, 10)
            num_stds = np.arange(1.5, 3.6, 0.3)
        else:
            windows = range(10, 95, 5)
            num_stds = np.arange(1.5, 3.6, 0.1)

        results = []
        for window in windows:
            for num_std in num_stds:
                strategy = BollingerBandsStrategy(
                    window=window, num_std=num_std, staged=True, first_batch_pct=1.0
                )
                engine = BacktestEngine(strategy, df.copy(), initial_capital=100000, commission=0.0003)
                engine.run()
                metrics = engine.calculate_metrics()
                results.append({
                    'Window': window,
                    'StdDev': round(num_std, 1),
                    'Total Return': metrics.get('Total Return', 0),
                    'Sharpe Ratio': metrics.get('Sharpe Ratio', 0),
                    'Max Drawdown': metrics.get('Max Drawdown', 0),
                })
        return pd.DataFrame(results)

    if st.button("🚀 开始优化", width="stretch", key="run_opt"):
        st.session_state['opt_running'] = True

    if st.session_state.get('opt_running', False):
        with st.spinner(f"⚙️ 正在对 {opt_etf} 进行 {opt_grid} 网格搜索..."):
            opt_results = run_optimization(opt_etf, ctx['start_date'], ctx['end_date'], opt_grid)

        if opt_results.empty:
            st.error("❌ 优化失败，未获取到数据")
        else:
            # Pivot for heatmap
            pivot = opt_results.pivot(index='StdDev', columns='Window', values=opt_metric)
            pivot = pivot.sort_index(ascending=False)

            if opt_metric in ['Total Return', 'Max Drawdown']:
                text_vals = [[f"{v:.1%}" for v in row] for row in pivot.values]
            else:
                text_vals = [[f"{v:.2f}" for v in row] for row in pivot.values]

            colorscale = 'RdYlGn' if opt_metric == 'Max Drawdown' else 'YlOrRd'

            fig_heat = go.Figure(data=go.Heatmap(
                z=pivot.values,
                x=[str(c) for c in pivot.columns],
                y=[str(r) for r in pivot.index],
                text=text_vals,
                texttemplate='%{text}',
                textfont=dict(size=10),
                colorscale=colorscale,
                colorbar=dict(title=metric_labels[opt_metric]),
                hovertemplate='Window=%{x}<br>StdDev=%{y}<br>' + metric_labels[opt_metric] + '=%{text}<extra></extra>'
            ))

            # Mark current parameters
            current_w = ctx['w1'] if opt_etf == "510880" else ctx['w2']
            current_std = ctx['std1'] if opt_etf == "510880" else ctx['std2']

            fig_heat.add_trace(go.Scatter(
                x=[str(current_w)],
                y=[str(current_std)],
                mode='markers',
                marker=dict(symbol='star', size=20, color='#000000', line=dict(width=2, color='white')),
                name=f'当前参数 ({current_w}, {current_std})',
                showlegend=True
            ))

            fig_heat.update_layout(
                template='plotly_white',
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                title=dict(
                    text=f"{opt_etf} 参数优化热力图 — {metric_labels[opt_metric]}",
                    font=dict(color='#374151')
                ),
                xaxis=dict(title='Window (布林周期)', type='category'),
                yaxis=dict(title='StdDev (标准差倍数)', type='category'),
                height=500,
            )

            st.plotly_chart(fig_heat, width="stretch")

            # Best parameters
            best_row = opt_results.loc[opt_results[opt_metric].idxmax()]

            st.markdown("---")

            b1, b2, b3 = st.columns(3)
            b1.metric("🏆 最优 Window", int(best_row['Window']))
            b2.metric("🏆 最优 StdDev", f"{best_row['StdDev']:.1f}")
            if opt_metric in ['Total Return', 'Max Drawdown']:
                b3.metric(f"🏆 {metric_labels[opt_metric]}", f"{best_row[opt_metric]:.2%}")
            else:
                b3.metric(f"🏆 {metric_labels[opt_metric]}", f"{best_row[opt_metric]:.2f}")

            # Top 10 table
            with st.expander("📊 Top 10 参数组合", expanded=False):
                top10 = opt_results.nlargest(10, opt_metric)
                top10_display = top10.copy()
                top10_display['Total Return'] = top10_display['Total Return'].apply(lambda x: f"{x:.2%}")
                top10_display['Max Drawdown'] = top10_display['Max Drawdown'].apply(lambda x: f"{x:.2%}")
                top10_display['Sharpe Ratio'] = top10_display['Sharpe Ratio'].apply(lambda x: f"{x:.2f}")
                st.dataframe(top10_display, width="stretch", hide_index=True)
    else:
        st.info("👆 点击上方按钮开始参数优化。粗略模式约需 30秒，精细模式约需 2-3 分钟。")
