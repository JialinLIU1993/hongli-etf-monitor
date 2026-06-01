"""Tab4: 交易明细"""
import streamlit as st
import pandas as pd


def render(ctx):
    """渲染交易明细 Tab。"""
    st.markdown("### 📋 交易明细")

    def render_trade_table(engine, name, symbol):
        records = engine.get_trade_records()
        if not records:
            st.info(f"{name} 暂无交易记录")
            return

        trade_df = pd.DataFrame(records)
        trade_df['date'] = trade_df['date'].dt.strftime('%Y-%m-%d')

        # 格式化 PnL
        trade_df['pnl_display'] = trade_df['pnl'].apply(
            lambda x: f"{x:+.2%}" if pd.notna(x) else "—"
        )
        trade_df['holding_display'] = trade_df['holding_days'].apply(
            lambda x: f"{int(x)} 天" if pd.notna(x) else "—"
        )

        # 构建展示用 DataFrame
        display_df = trade_df[['date', 'direction', 'price', 'position_change', 'position_after', 'pnl_display', 'holding_display']].copy()
        display_df.columns = ['日期', '方向', '成交价', '仓位变动', '交易后仓位', '已实现收益', '持仓天数']
        display_df['成交价'] = display_df['成交价'].apply(lambda x: f"¥{x:.3f}")

        # 统计摘要
        sell_records = [r for r in records if r['pnl'] is not None]
        if sell_records:
            pnls = [r['pnl'] for r in sell_records]
            wins = [p for p in pnls if p > 0]
            losses = [p for p in pnls if p <= 0]

            s1, s2, s3, s4 = st.columns(4)
            s1.metric("交易次数", f"{len(sell_records)} 笔")
            s2.metric("胜率", f"{len(wins)/len(sell_records):.0%}")
            avg_win = sum(wins)/len(wins) if wins else 0
            avg_loss = abs(sum(losses)/len(losses)) if losses else 0
            s3.metric("平均盈利", f"{avg_win:+.2%}" if wins else "—")
            s4.metric("盈亏比", f"{avg_win/avg_loss:.2f}" if avg_loss > 0 else "∞")

        # 颜色标记函数
        def highlight_direction(row):
            if row['方向'] == '买入':
                return ['background-color: rgba(239, 68, 68, 0.08)'] * len(row)
            elif row['方向'] == '卖出':
                return ['background-color: rgba(34, 197, 94, 0.08)'] * len(row)
            return [''] * len(row)

        styled = display_df.style.apply(highlight_direction, axis=1)
        st.dataframe(styled, use_container_width=True, hide_index=True, height=400)

        # 导出按钮
        csv = display_df.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            f"⬇️ 导出 {symbol} 交易记录",
            csv,
            file_name=f"trades_{symbol}.csv",
            mime="text/csv"
        )

    tc1, tc2 = st.columns(2)

    with tc1:
        st.markdown("#### 🔴 510880 红利 ETF")
        render_trade_table(ctx['engine_1'], "红利 ETF", "510880")

    with tc2:
        st.markdown("#### 🔵 512890 红利低波")
        render_trade_table(ctx['engine_2'], "红利低波", "512890")
