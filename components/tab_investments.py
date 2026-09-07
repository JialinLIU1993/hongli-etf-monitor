"""Investment record tab."""
import math

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.investment_records import (
    append_record,
    calculate_investment_summary,
    delete_records,
    lookup_trade_price,
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
    cols[0].metric("累计收益", _money(summary["total_pnl"]), _pct(summary["total_return"]), delta_color="inverse")
    cols[1].metric("已实现收益", _money(summary["realized_pnl"]), _pct(summary["realized_return"]), delta_color="inverse")
    cols[2].metric("浮动收益", _money(summary["unrealized_pnl"]))
    cols[3].metric("当前市值", _money(summary["market_value"]))
    cols[4].metric("投入成本", _money(summary["capital_base"]))


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
    for symbol, frame in ctx.get("raw_data", {}).items():
        if frame is not None and not frame.empty and "close" in frame:
            value = frame["close"].iloc[-1]
            if pd.notna(value) and math.isfinite(float(value)) and float(value) > 0:
                prices[symbol] = float(value)
    return prices


def _default_trade_price(ctx, symbol, trade_date):
    lookup = lookup_trade_price(ctx["raw_data"].get(symbol), trade_date, field="close")
    if lookup["price"] is not None:
        return round(lookup["price"], 3), lookup

    status_price = _current_prices_from_ctx(ctx).get(symbol)
    if status_price is not None:
        lookup["message"] = "未找到所选日期行情，临时使用最新参考收盘价，实际成交价请核对"
        return round(float(status_price), 3), lookup
    lookup["message"] = "暂无有效行情，请按交割单填写实际成交价"
    return None, lookup


def _render_record_form(ctx, records):
    """Render the add-record form and persist submitted data."""
    with st.container(border=False):
        st.caption("按交割单填写实际成交信息。")
        c1, c2, c3, c4 = st.columns([1.1, 1.1, 1.1, 1.2])
        trade_date = c1.date_input("日期", value=pd.Timestamp.today(), key="investment_trade_date")
        symbol = c2.selectbox(
            "ETF",
            ["510880", "512890"],
            format_func=lambda s: f"{s} {ctx['profiles'][s].name}",
            key="investment_symbol",
        )
        side_label = c3.segmented_control("方向", ["买入", "卖出"], default="买入", key="investment_side")
        quantity = c4.number_input("份额", min_value=1, value=1000, step=100, key="investment_quantity")

        c5, c6, c7 = st.columns([1.1, 1.1, 2.2])
        default_price, price_lookup = _default_trade_price(ctx, symbol, trade_date)
        price_basis = ctx.get("price_basis", "前复权")
        price_key = f"investment_price_{ctx.get('provider', 'akshare')}_{symbol}_{pd.Timestamp(trade_date).strftime('%Y%m%d')}"
        price = c5.number_input(
            "成交价",
            min_value=0.001,
            value=default_price,
            step=0.001,
            format="%.3f",
            key=price_key,
            help=f"默认带出所选 ETF 在所选日期的参考收盘价（{price_basis}）；请按交割单核对实际成交价。",
            placeholder="填写实际成交价",
        )
        fee = c6.number_input("佣金/费用", min_value=0.0, value=0.0, step=0.01, format="%.2f", key="investment_fee")
        note = c7.text_input("备注", placeholder="可选", key="investment_note")

        if price_lookup["price"] is not None:
            lookup_date = _date(price_lookup["date"])
            st.caption(f"{price_lookup['message']}: {lookup_date} 参考收盘价 {price_lookup['price']:.3f}（{price_basis}），实际成交价请核对。")
        else:
            st.caption(price_lookup["message"])

        submitted = st.button("保存记录", type="primary", key="investment_save_record", disabled=side_label not in SIDE_VALUES or price is None)
        if submitted:
            try:
                updated_records = append_record(
                    records,
                    date=trade_date,
                    symbol=symbol,
                    side=SIDE_VALUES[side_label],
                    price=price,
                    quantity=quantity,
                    fee=fee,
                    note=note,
                )
                save_records(updated_records)
                st.success("投资记录已保存。")
                st.rerun()
            except (ValueError, OSError) as exc:
                st.error(f"投资记录未保存：{exc}")
    return records


def _render_raw_records(records, analysis):
    """Render raw record management."""
    with st.container(border=False):
        st.caption("导出全部流水，或选择需要移除的记录。")
        record_display = _format_records(analysis["records"])
        if record_display.empty:
            st.info("暂无投资记录。")
        else:
            st.dataframe(record_display.drop(columns=["记录ID"]).sort_values("日期", ascending=False), width="stretch", hide_index=True)
            labels = {
                row["记录ID"]: f"{row['日期']} {row['ETF']} {row['方向']} {row['份额']}份 @ {row['成交价']}"
                for _, row in record_display.iterrows()
            }
            selected_ids = st.multiselect(
                "选择要删除的记录",
                options=list(labels.keys()),
                format_func=lambda value: labels[value],
                key="investment_delete_ids",
            )
            if st.button("删除选中记录", type="secondary", disabled=not selected_ids, key="investment_delete_records"):
                try:
                    save_records(delete_records(records, selected_ids))
                    st.success("已删除选中记录。")
                    st.rerun()
                except (ValueError, OSError) as exc:
                    st.error(f"记录未删除：{exc}")

            export_display = record_display.copy()
            # Treat a note as text when opened in spreadsheet software.
            export_display["备注"] = export_display["备注"].map(
                lambda value: "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value
            )
            csv = export_display.to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                "导出投资流水",
                csv,
                file_name="investment_records.csv",
                mime="text/csv",
                width="stretch",
            )


def render(ctx, show_title=True, compact=False, records=None, analysis=None, show_summary=True):
    """A separate portfolio workspace with an explicit record-entry action."""
    if show_title:
        st.markdown("### 持仓记录")
    try:
        if records is None:
            records = load_records()
        if analysis is None:
            analysis = calculate_investment_summary(records, _current_prices_from_ctx(ctx))
    except (ValueError, OSError) as exc:
        st.error(f"无法读取投资记录：{exc}")
        return

    summary = analysis["summary"]
    dates = [frame.index.max() for frame in ctx["raw_data"].values() if not frame.empty]
    valuation_date = min(dates).strftime("%Y.%m.%d") if dates else "暂无行情"
    st.caption(f"仅保存在本机 · 估值数据截至 {valuation_date} · {ctx.get('price_basis', '前复权')}")
    if summary.get("missing_price_symbols"):
        st.warning(f"{'、'.join(summary['missing_price_symbols'])} 缺少有效行情，当前市值、浮动收益和累计收益暂不计算；已实现收益仍可查看。")
    if records.empty:
        st.markdown('<div class="empty-state"><strong>从第一笔交易开始</strong><p>添加实际买入或卖出记录，即可查看持仓、市值和收益。</p></div>', unsafe_allow_html=True)
    elif show_summary:
        _render_summary(summary)

    with st.expander("新增交易记录", expanded=False):
        _render_record_form(ctx, records)

    if records.empty:
        return
    if not analysis["unmatched_sells"].empty:
        st.warning("存在卖出份额超过已记录持仓的记录，相关部分未计入收益。请检查交易流水。")
    view = st.segmented_control("记录视图", ["当前持仓", "收益记录", "交易流水"],
                                default="当前持仓", key="investment_view") or "当前持仓"
    if view == "当前持仓":
        display = _format_open_positions(analysis["open_positions"])
        if display.empty:
            st.info("当前没有未卖出的持仓，可在收益记录中查看已完成交易。")
        else:
            st.dataframe(display, width="stretch", hide_index=True)
    elif view == "收益记录":
        _render_history_chart(analysis["history"])
        history = _format_history(analysis["history"])
        if history.empty:
            st.info("卖出交易完成配对后，将在这里显示已实现收益。")
        else:
            st.dataframe(history.sort_values("月份", ascending=False), width="stretch", hide_index=True)
        with st.expander("已实现交易明细"):
            closed = _format_closed_trades(analysis["closed_trades"])
            if not closed.empty:
                st.dataframe(closed.sort_values("卖出日期", ascending=False), width="stretch", hide_index=True)
            else:
                st.caption("暂无已配对的卖出交易。")
    else:
        _render_raw_records(records, analysis)
