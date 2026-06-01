"""Tab2: 个股分析"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go


def render(ctx):
    """渲染个股分析 Tab。"""
    res_1, res_2 = ctx['res_1'], ctx['res_2']
    met_1, met_2 = ctx['met_1'], ctx['met_2']
    ret_cash_1, ret_cash_2 = ctx['ret_cash_1'], ctx['ret_cash_2']
    portfolio_equity = ctx['portfolio_equity']

    # 详细指标对比
    st.markdown("### 📊 详细指标对比")

    def _fmt_pf(v):
        return "∞" if v == float('inf') else f"{v:.2f}"

    metrics_data = {
        "指标": [
            "📈 纯策略收益", "📈 年化收益", "📈 含理财收益",
            "📉 最大回撤", "📉 年化波动率",
            "⚖️ 夏普比率", "⚖️ 索提诺比率", "⚖️ 卡尔玛比率",
            "🎯 胜率", "🎯 盈亏比", "🎯 平均盈利", "🎯 平均亏损",
            "🔢 交易次数", "🔢 最大连胜/连亏", "🔢 平均持仓天数"
        ],
        "510880 (红利)": [
            f"{met_1['Total Return']:.2%}",
            f"{met_1['Annualized Return']:.2%}",
            f"{ret_cash_1:.2%}",
            f"{met_1['Max Drawdown']:.2%}",
            f"{met_1['Volatility']:.2%}",
            f"{met_1['Sharpe Ratio']:.2f}",
            f"{met_1['Sortino Ratio']:.2f}",
            f"{met_1['Calmar Ratio']:.2f}",
            f"{met_1['Win Rate']:.0%}",
            _fmt_pf(met_1['Profit Factor']),
            f"{met_1['Avg Win']:.2%}",
            f"{met_1['Avg Loss']:.2%}",
            met_1['Transaction Count'],
            f"{met_1['Max Consecutive Wins']} / {met_1['Max Consecutive Losses']}",
            f"{met_1['Avg Holding Days']:.0f}天",
        ],
        "512890 (低波)": [
            f"{met_2['Total Return']:.2%}",
            f"{met_2['Annualized Return']:.2%}",
            f"{ret_cash_2:.2%}",
            f"{met_2['Max Drawdown']:.2%}",
            f"{met_2['Volatility']:.2%}",
            f"{met_2['Sharpe Ratio']:.2f}",
            f"{met_2['Sortino Ratio']:.2f}",
            f"{met_2['Calmar Ratio']:.2f}",
            f"{met_2['Win Rate']:.0%}",
            _fmt_pf(met_2['Profit Factor']),
            f"{met_2['Avg Win']:.2%}",
            f"{met_2['Avg Loss']:.2%}",
            met_2['Transaction Count'],
            f"{met_2['Max Consecutive Wins']} / {met_2['Max Consecutive Losses']}",
            f"{met_2['Avg Holding Days']:.0f}天",
        ]
    }

    metrics_df = pd.DataFrame(metrics_data)
    st.dataframe(metrics_df, use_container_width=True, hide_index=True)

    # 回撤分析
    st.markdown("### 📉 回撤分析")

    drawdown_1 = (res_1['equity'] - res_1['equity'].cummax()) / res_1['equity'].cummax()
    drawdown_2 = (res_2['equity'] - res_2['equity'].cummax()) / res_2['equity'].cummax()
    drawdown_portfolio = (portfolio_equity - portfolio_equity.cummax()) / portfolio_equity.cummax()

    fig_dd = go.Figure()
    fig_dd.add_trace(go.Scatter(
        x=drawdown_portfolio.index, y=drawdown_portfolio * 100,
        name="组合", fill='tozeroy',
        line=dict(color='#d97706'),
        fillcolor='rgba(251, 191, 36, 0.2)'
    ))
    fig_dd.add_trace(go.Scatter(
        x=drawdown_1.index, y=drawdown_1 * 100,
        name="510880", line=dict(color='#ef4444', width=1)
    ))
    fig_dd.add_trace(go.Scatter(
        x=drawdown_2.index, y=drawdown_2 * 100,
        name="512890", line=dict(color='#3b82f6', width=1)
    ))

    fig_dd.update_layout(
        template='plotly_white',
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        title=dict(text="回撤曲线", font=dict(color='#374151')),
        xaxis=dict(title="日期", gridcolor='#f3f4f6'),
        yaxis=dict(title="回撤 (%)", gridcolor='#f3f4f6'),
        height=350,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )

    st.plotly_chart(fig_dd, use_container_width=True)
