"""Investment record tab."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.investment_records import (
    RECORDS_PATH,
    append_record,
    calculate_investment_summary,
    delete_records,
    load_records,
    save_records,
)


SIDE_LABELS = {"buy": "买入", "sell": "卖出"}
SIDE_VALUES = {"买入": "buy", "卖出": "sell"}


def _money(value):
    if value is None or pd.isna(value):
        return "—"
    return f"{value:,.2f}"


def _pct(value):
    if value is None or pd.isna(value):
        return "—"
    return f"{value:.2%}"


def _date(value):
    if value is None or pd.isna(value):
        return "—"
    return pd.Timestamp(value).strftime("%Y-%m-%d")


def _format_records(records):
    if records.empty:
        return pd.DataFrame()
    display = records.copy()
    display["日期"] = display["date"].dt.strftime("%Y-%m-%d")
    display["ETF"] = display["symbol"]
    display["方向"] = display["side"].map(SIDE_LABELS)
    display["成交价"] = display["price"].map(lambda v: f"{v:.3f}")
    display["份额"] = display["quantity"].map(lambda v: f"{v:,.0f}")
    display["费用"] = display["fee"].map(_money)
    display["成交金额"] = (display["price"] * display["quantity"]).map(_money)
    display["备注"] = display["note"]
    display["记录ID"] = display["id"]
    return display[["日期", "ETF", "方向", "成交价", "份额", "费用", "成交金额", "备注", "记录ID"]]


def _format_open_positions(open_df):
    if open_df.empty:
        return pd.DataFrame()
    display = open_df.copy()
    display["买入日期"] = display["buy_date"].map(_date)
    display["ETF"] = display["symbol"]
    display["剩余份额"] = display["quantity"].map(lambda v: f"{v:,.0f}")
    display["买入价"] = display["buy_price"].map(lambda v: f"{v:.3f}")
    display["成本"] = display["cost_basis"].map(_money)
    display["现价"] = display["current_price"].map(lambda v: "—" if pd.isna(v) else f"{v:.3f}")
    display["市值"] = display["market_value"].map(_money)
    display["浮动收益"] = display["unrealized_pnl"].map(_money)
    display["收益率"] = display["return_pct"].map(_pct)
    return display[["ETF", "买入日期", "剩余份额", "买入价", "成本", "现价", "市值", "浮动收益", "收益率"]]


def _format_closed_trades(closed_df):
    if closed_df.empty:
        return pd.DataFrame()
    display = closed_df.copy()
    display["ETF"] = display["symbol"]
    display["买入日期"] = display["buy_date"].map(_date)
    display["卖出日期"] = display["sell_date"].map(_date)
    display["份额"] = display["quantity"].map(lambda v: f"{v:,.0f}")
    display["买入价"] = display["buy_price"].map(lambda v: f"{v:.3f}")
    display["卖出价"] = display["sell_price"].map(lambda v: f"{v:.3f}")
    display["成本"] = display["cost"].map(_money)
    display["卖出收入"] = display["proceeds"].map(_money)
    display["已实现收益"] = display["pnl"].map(_money)
    display["收益率"] = display["return_pct"].map(_pct)
    display["持仓天数"] = display["holding_days"].map(lambda v: f"{int(v)}")
    return display[[
        "ETF", "买入日期", "卖出日期", "份额", "买入价", "卖出价",
        "成本", "卖出收入", "已实现收益", "收益率", "持仓天数",
    ]]


def _format_history(history_df):
    if history_df.empty:
        return pd.DataFrame()
    display = history_df.copy()
    display["月份"] = display["month"]
    display["已实现收益"] = display["realized_pnl"].map(_money)
    display["成本"] = display["cost"].map(_money)
    display["卖出收入"] = display["proceeds"].map(_money)
    display["收益率"] = display["return_pct"].map(_pct)
    display["交易批次"] = display["trades"].map(lambda v: f"{int(v)}")
    return display[["月份", "已实现收益", "收益率", "成本", "卖出收入", "交易批次"]]


def _render_summary(summary):
    cols = st.columns(5)
    cols[0].metric("累计收益", _money(summary["total_pnl"]), _pct(summary["total_return"]))
    cols[1].metric("已实现收益", _money(summary["realized_pnl"]), _pct(summary["realized_return"]))
    cols[2].metric("浮动收益", _money(summary["unrealized_pnl"]))
    cols[3].metric("当前市值", _money(summary["market_value"]))
    cols[4].metric("投入成本口径", _money(summary["capital_base"]))


def _render_history_chart(history_df):
    if history_df.empty:
        return
    colors = ["#ef4444" if v >= 0 else "#22c55e" for v in history_df["realized_pnl"]]
    fig = go.Figure(go.Bar(
        x=history_df["month"],
        y=history_df["realized_pnl"],
        marker_color=colors,
        name="已实现收益",
    ))
    fig.update_layout(
        template="plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=320,
        margin=dict(l=20, r=20, t=30, b=30),
        xaxis_title="月份",
        yaxis_title="收益",
    )
    st.plotly_chart(fig, width="stretch", config={"displaylogo": False})


def _current_prices_from_ctx(ctx):
    prices = {}
    for symbol, status in ctx["statuses"].items():
        if status.get("is_ready"):
            prices[symbol] = status.get("close")
    return prices


def render(ctx):
    """Render investment records and calculated return history."""
    st.markdown("### 投资记录")
    st.caption(f"记录保存在本机 `{RECORDS_PATH}`，该文件已被忽略，不会上传到公开仓库。")

    records = load_records()

    with st.form("investment_record_form", clear_on_submit=True):
        st.markdown("#### 新增买入/卖出")
        c1, c2, c3, c4 = st.columns([1.1, 1.1, 1.1, 1.2])
        trade_date = c1.date_input("日期", value=pd.Timestamp.today())
        symbol = c2.selectbox("ETF", ["510880", "512890"], format_func=lambda s: f"{s} {ctx['profiles'][s].name}")
        side_label = c3.segmented_control("方向", ["买入", "卖出"], default="买入")
        quantity = c4.number_input("份额", min_value=1, value=1000, step=100)

        c5, c6, c7 = st.columns([1.1, 1.1, 2.2])
        default_price = float(ctx["statuses"].get(symbol, {}).get("close") or 1.0)
        price = c5.number_input("成交价", min_value=0.001, value=round(default_price, 3), step=0.001, format="%.3f")
        fee = c6.number_input("佣金/费用", min_value=0.0, value=0.0, step=0.01, format="%.2f")
        note = c7.text_input("备注", placeholder="可选")

        submitted = st.form_submit_button("保存记录")
        if submitted:
            try:
                records = append_record(
                    records,
                    date=trade_date,
                    symbol=symbol,
                    side=SIDE_VALUES[side_label],
                    price=price,
                    quantity=quantity,
                    fee=fee,
                    note=note,
                )
                save_records(records)
                st.success("投资记录已保存。")
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))

    analysis = calculate_investment_summary(records, _current_prices_from_ctx(ctx))

    st.markdown("---")
    _render_summary(analysis["summary"])

    if not analysis["unmatched_sells"].empty:
        st.warning("存在卖出份额超过已记录持仓的记录，相关部分未计入收益。请检查交易流水。")
        warn_df = analysis["unmatched_sells"].copy()
        warn_df["date"] = warn_df["date"].dt.strftime("%Y-%m-%d")
        st.dataframe(warn_df, width="stretch", hide_index=True)

    st.markdown("#### 当前持仓")
    open_display = _format_open_positions(analysis["open_positions"])
    if open_display.empty:
        st.info("暂无未卖出的持仓。")
    else:
        st.dataframe(open_display, width="stretch", hide_index=True)

    st.markdown("#### 历史收益")
    _render_history_chart(analysis["history"])
    history_display = _format_history(analysis["history"])
    if history_display.empty:
        st.info("暂无已实现收益，卖出记录会在这里形成历史收益。")
    else:
        st.dataframe(history_display.sort_values("月份", ascending=False), width="stretch", hide_index=True)

    with st.expander("已实现交易明细", expanded=False):
        closed_display = _format_closed_trades(analysis["closed_trades"])
        if closed_display.empty:
            st.info("暂无已配对的卖出交易。")
        else:
            st.dataframe(closed_display.sort_values("卖出日期", ascending=False), width="stretch", hide_index=True)

    with st.expander("原始流水与删除", expanded=False):
        record_display = _format_records(analysis["records"])
        if record_display.empty:
            st.info("暂无投资记录。")
        else:
            st.dataframe(record_display.sort_values("日期", ascending=False), width="stretch", hide_index=True)
            labels = {
                row["记录ID"]: f"{row['日期']} {row['ETF']} {row['方向']} {row['份额']}份 @ {row['成交价']}"
                for _, row in record_display.iterrows()
            }
            selected_ids = st.multiselect(
                "选择要删除的记录",
                options=list(labels.keys()),
                format_func=lambda value: labels[value],
            )
            if st.button("删除选中记录", type="secondary", disabled=not selected_ids):
                save_records(delete_records(records, selected_ids))
                st.success("已删除选中记录。")
                st.rerun()

            csv = record_display.to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                "导出投资流水",
                csv,
                file_name="investment_records.csv",
                mime="text/csv",
                width="stretch",
            )
