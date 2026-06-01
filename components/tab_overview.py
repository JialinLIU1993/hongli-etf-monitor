"""Tab1: 组合总览"""
import streamlit as st
import plotly.graph_objects as go


def render(ctx):
    """渲染组合总览 Tab。

    Args:
        ctx: dict containing res_1, res_2, met_1, met_2, rm_1, rm_2,
             cum_return, total_return, portfolio_cash_return, max_dd,
             weight_1, weight_2, w1, std1, w2, std2, ret_cash_1, ret_cash_2
    """
    # 组合总览卡片
    st.markdown("### 🏆 组合表现")
    c1, c2, c3, c4 = st.columns(4)

    res_1, res_2 = ctx['res_1'], ctx['res_2']
    weight_1, weight_2 = ctx['weight_1'], ctx['weight_2']
    total_return = ctx['total_return']
    portfolio_cash_return = ctx['portfolio_cash_return']
    max_dd = ctx['max_dd']

    with c1:
        st.metric(
            "组合总收益 (含闲钱增强)",
            f"{total_return:.2%}",
            delta=f"{total_return - (res_1['cumulative_market_return'].iloc[-1] - 1) * weight_1 - (res_2['cumulative_market_return'].iloc[-1] - 1) * weight_2:.2%} 超额收益",
            help="现已默认包含空仓期间场内货基/逆回购等无风险收益"
        )
    with c2:
        st.metric(
            "基准表现 (一直满仓持有)",
            f"{(res_1['cumulative_market_return'].iloc[-1] - 1) * weight_1 + (res_2['cumulative_market_return'].iloc[-1] - 1) * weight_2:.2%}",
            delta="-死拿不动",
            delta_color="off",
            help="全程满仓买入持有标的时的整体基准收益"
        )
    with c3:
        st.metric("最大回撤", f"{max_dd:.2%}")
    with c4:
        avg_pos = (res_1['position'].mean() * weight_1 + res_2['position'].mean() * weight_2)
        st.metric("平均仓位", f"{avg_pos:.0%}")

    st.markdown("---")

    # 最新信号
    signal_date_str = ctx.get('common_latest_date_str', res_1.index[-1].strftime('%Y-%m-%d'))
    st.markdown(f"### 🔔 最新操作信号（截至 {signal_date_str}）")
    col1, col2 = st.columns(2)

    def show_signal_card(res, name, symbol, params, col, ctx=None):
        last = res.iloc[-1]
        price = last['close']
        position = last['position']

        with col:
            st.markdown(f"#### {name}")
            
            lower = last['lower_band']
            upper = last['upper_band']
            ma = last['ma']
            
            signal_row_date = last.name.strftime('%Y-%m-%d') if hasattr(last.name, 'strftime') else str(last.name)
            st.caption(f"数据日期: {signal_row_date} | 代码: {symbol} | 参数: Window={params[0]}, Std={params[1]}")

            price_pct = (price - lower) / (upper - lower) * 100 if upper != lower else 50
            dist_to_buy = (price - lower) / price * 100   # 距买入点的百分比
            dist_to_sell = (upper - price) / price * 100   # 距卖出点的百分比

            if price < lower:
                signal_class = "signal-buy"
                signal_text = f"🔴 **买入信号** | 现价 ¥{price:.3f} < 下轨 ¥{lower:.3f}"
                delta = f"偏离下轨 {(price - lower) / lower * 100:.1f}%"
                action_hint = f"💡 建议买入 | 已跌破下轨，可分批建仓"
            elif price > upper:
                signal_class = "signal-sell"
                signal_text = f"🟢 **卖出信号** | 现价 ¥{price:.3f} > 上轨 ¥{upper:.3f}"
                delta = f"偏离上轨 +{(price - upper) / upper * 100:.1f}%"
                action_hint = f"💡 建议卖出 | 已突破上轨，可分批减仓"
            else:
                signal_class = "signal-hold"
                signal_text = f"⚪ **观望中** | 通道内运行"
                delta = f"通道位置 {price_pct:.0f}%"
                if dist_to_buy < dist_to_sell:
                    action_hint = f"💡 距买入点 ¥{lower:.3f} 还差 {dist_to_buy:.1f}%"
                else:
                    action_hint = f"💡 距卖出点 ¥{upper:.3f} 还差 {dist_to_sell:.1f}%"

            st.markdown(f'<div class="{signal_class}">{signal_text}<br><small>{delta}</small></div>', unsafe_allow_html=True)
            st.caption(action_hint)

            # 指标行 1: 仓位、中轨、通道宽度
            m1, m2, m3 = st.columns(3)
            m1.metric("当前仓位", f"{position:.0%}")
            m2.metric("MA中轨", f"¥{ma:.3f}")
            m3.metric("通道宽度", f"{(upper - lower) / ma * 100:.1f}%")

            # 指标行 2: 买入点、卖出点、距触发
            b1, b2, b3 = st.columns(3)
            b1.metric("📉 买入点(下轨)", f"¥{lower:.3f}", f"{-dist_to_buy:.1f}%")
            b2.metric("📈 卖出点(上轨)", f"¥{upper:.3f}", f"+{dist_to_sell:.1f}%")
            b3.metric("📍 现价", f"¥{price:.3f}")

    show_signal_card(res_1, "红利 ETF (进攻)", "510880", (ctx['w1'], ctx['std1']), col1, ctx)
    show_signal_card(res_2, "红利低波 (防守)", "512890", (ctx['w2'], ctx['std2']), col2, ctx)

    st.markdown("---")

    # 风控状态
    st.markdown("### 🛡️ 风控状态")

    rc1, rc2 = st.columns(2)

    summary_1 = ctx['rm_1'].get_trigger_summary()
    summary_2 = ctx['rm_2'].get_trigger_summary()

    with rc1:
        st.markdown("#### 510880 风控")
        total_1 = summary_1['total_count']
        if total_1 > 0:
            st.warning(f"⚠️ 共触发 **{total_1}** 次止损")
            for tp, cnt in summary_1['by_type'].items():
                st.caption(f"  {tp}: {cnt} 次")
            last = summary_1['last_trigger']
            if last:
                st.caption(f"最近触发: {last['date'].strftime('%Y-%m-%d')} — {last['detail']}")
        else:
            st.success("✅ 未触发止损")

    with rc2:
        st.markdown("#### 512890 风控")
        total_2 = summary_2['total_count']
        if total_2 > 0:
            st.warning(f"⚠️ 共触发 **{total_2}** 次止损")
            for tp, cnt in summary_2['by_type'].items():
                st.caption(f"  {tp}: {cnt} 次")
            last = summary_2['last_trigger']
            if last:
                st.caption(f"最近触发: {last['date'].strftime('%Y-%m-%d')} — {last['detail']}")
        else:
            st.success("✅ 未触发止损")

    st.markdown("---")

    # 自适应参数状态（仅在自适应模式下显示）
    if ctx.get('adaptive_enabled'):
        st.markdown("### 🧠 自适应参数状态")

        for strat, name in [(ctx['strat_1'], '510880 (红利)'), (ctx['strat_2'], '512890 (低波)')]:
            if hasattr(strat, 'get_regime_summary'):
                summary = strat.get_regime_summary()
                current = summary.get('current_regime')

                if current:
                    st.markdown(f"**{name}** — 当前: {current['label']}  "
                                f"(Window={current['window']}, Std={current['num_std']})")

                    ac1, ac2, ac3 = st.columns(3)
                    for regime_key, col in [('high', ac1), ('mid', ac2), ('low', ac3)]:
                        info = summary['by_regime'].get(regime_key)
                        if info:
                            col.metric(info['label'], f"{info['pct']:.0%}", f"{info['days']}天 / {info['segments']}段")
                        else:
                            from src.adaptive import REGIME_PARAMS
                            col.metric(REGIME_PARAMS[regime_key]['label'], "0%", "无")

                    # 参数变化时间线
                    if strat.param_log and len(strat.param_log) > 1:
                        with st.expander(f"📊 {name} 参数变化历史", expanded=False):
                            import pandas as pd
                            log_df = pd.DataFrame(strat.param_log)
                            log_df['start'] = log_df['start'].dt.strftime('%Y-%m-%d')
                            log_df['end'] = log_df['end'].dt.strftime('%Y-%m-%d')
                            log_df = log_df.rename(columns={
                                'start': '开始', 'end': '结束', 'label': '状态',
                                'window': '布林周期', 'num_std': '标准差', 'days': '天数'
                            })
                            st.dataframe(log_df[['开始', '结束', '状态', '布林周期', '标准差', '天数']],
                                         use_container_width=True, hide_index=True)

        st.markdown("---")

    # 收益曲线
    st.markdown("### 📈 收益走势对比")

    cum_return = ctx['cum_return']
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=cum_return.index, y=cum_return,
        name="组合策略",
        line=dict(color='#d97706', width=3),
        fill='tozeroy',
        fillcolor='rgba(251, 191, 36, 0.2)'
    ))
    fig.add_trace(go.Scatter(
        x=res_1.index, y=res_1['cumulative_strategy_return'],
        name="510880 策略",
        line=dict(color='#dc2626', width=2, dash='dash')
    ))
    fig.add_trace(go.Scatter(
        x=res_1.index, y=res_1['cumulative_market_return'],
        name="510880 持有",
        line=dict(color='#f87171', width=1),
        opacity=0.6
    ))
    fig.add_trace(go.Scatter(
        x=res_2.index, y=res_2['cumulative_strategy_return'],
        name="512890 策略",
        line=dict(color='#2563eb', width=2, dash='dash')
    ))
    fig.add_trace(go.Scatter(
        x=res_2.index, y=res_2['cumulative_market_return'],
        name="512890 持有",
        line=dict(color='#60a5fa', width=1),
        opacity=0.6
    ))

    fig.update_layout(
        template='plotly_white',
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        title=dict(text="组合 vs 个股策略 vs 买入持有", font=dict(color='#374151')),
        xaxis=dict(title="日期", gridcolor='#f3f4f6'),
        yaxis=dict(title="累计净值", gridcolor='#f3f4f6'),
        hovermode="x unified",
        legend=dict(
            orientation="h",
            yanchor="bottom", y=1.02,
            xanchor="right", x=1,
            bgcolor='rgba(255,255,255,0.8)'
        ),
        height=500
    )

    st.plotly_chart(fig, use_container_width=True)
