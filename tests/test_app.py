"""Offline end-to-end UI regressions; never read or write personal records."""
from datetime import date, datetime
from pathlib import Path
from unittest.mock import Mock

import numpy as np
import pandas as pd
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from src.investment_records import load_records, save_records

APP = Path(__file__).resolve().parents[1] / "app.py"


@pytest.fixture
def app_data(monkeypatch, tmp_path):
    st.cache_data.clear()
    monkeypatch.setattr("streamlit.elements.lib.policies._shown_default_value_warning", False)
    monkeypatch.delenv("ETF_DATA_PROVIDER", raising=False)
    monkeypatch.delenv("HITHINK_FINANCE_API_KEY", raising=False)
    monkeypatch.setattr("components.workspace_controls._configured_api_key", lambda: "")
    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 9, 7, 9, tzinfo=tz)

    monkeypatch.setattr("components.workspace_controls.datetime", FixedDateTime)
    dates = pd.bdate_range("2025-01-01", "2026-09-07")
    prices = 1.2 + np.sin(np.arange(len(dates)) / 7) * .15
    frame = pd.DataFrame({"open": prices, "close": prices, "high": prices + .02,
                          "low": prices - .02, "volume": 100000}, index=dates)

    def fetch(symbol, start_date, end_date, **kwargs):
        return frame.loc[pd.Timestamp(start_date):pd.Timestamp(end_date)].copy()

    mock = Mock(side_effect=fetch)
    monkeypatch.setattr("src.data_loader.fetch_etf_data", mock)
    records_path = tmp_path / "investment_records.csv"
    monkeypatch.setattr("components.tab_investments.load_records", lambda: load_records(records_path))
    monkeypatch.setattr("components.tab_investments.save_records", lambda records: save_records(records, records_path))
    yield mock
    st.cache_data.clear()


def widget(app, kind, label):
    return next(item for item in app.get(kind) if item.proto.label == label)


def assert_healthy(app):
    assert not app.exception, [item.message for item in app.exception]
    assert not any("Session State API" in item.value for item in app.warning)


def test_dashboard_reuses_prices_on_widget_changes(app_data):
    app = AppTest.from_file(APP, default_timeout=15).run()
    assert_healthy(app)
    assert app_data.call_count == 2
    widget(app, "radio", "选择 ETF").set_value("512890").run()
    assert_healthy(app)
    assert app_data.call_count == 2
    widget(app, "button_group", "显示区间").set_value("全部").run()
    assert_healthy(app)
    widget(app, "button", "刷新行情数据").click().run()
    assert_healthy(app)
    assert app_data.call_count == 4
    widget(app, "radio", "选择 ETF").set_value("510880").run()
    assert_healthy(app)
    assert app_data.call_count == 4


@pytest.mark.parametrize("failed_symbols", [{"510880"}, {"510880", "512890"}])
def test_partial_and_total_outages_keep_dashboard_available(app_data, failed_symbols):
    fetch = app_data.side_effect
    app_data.side_effect = lambda symbol, **kwargs: pd.DataFrame() if symbol in failed_symbols else fetch(symbol, **kwargs)
    app = AppTest.from_file(APP, default_timeout=15).run()
    assert_healthy(app)
    assert any("暂无可用行情" in item.value for item in app.warning)
    widget(app, "button_group", "页面").set_value("持仓记录").run()
    assert_healthy(app)
    assert any(item.label == "保存记录" for item in app.button)


def test_bad_date_range_is_explained_before_fetch(app_data):
    app = AppTest.from_file(APP, default_timeout=15).run()
    widget(app, "radio", "快捷选择").set_value("自定义").run()
    before = app_data.call_count
    widget(app, "date_input", "开始日期").set_value(date(2026, 1, 1))
    widget(app, "date_input", "结束日期").set_value(date(2025, 1, 1)).run()
    assert_healthy(app)
    assert any("开始日期不能晚于结束日期" in item.value for item in app.error)
    assert app_data.call_count == before


def test_optimization_only_runs_on_click_and_expires_on_settings_change(app_data, monkeypatch):
    from components import tab_optimize

    run = Mock(return_value=pd.DataFrame({
        "Window": [40, 50], "StdDev": [2.1, 2.1], "Total Return": [.1, .12],
        "Sharpe Ratio": [1.1, 1.2], "Max Drawdown": [-.08, -.06],
    }))
    monkeypatch.setattr(tab_optimize, "run_optimization", run)
    app = AppTest.from_file(APP, default_timeout=15).run()
    widget(app, "button_group", "页面").set_value("参数研究").run()
    assert_healthy(app)
    assert run.call_count == 0
    widget(app, "button", "开始优化").click().run()
    assert_healthy(app)
    assert run.call_count == 1
    widget(app, "selectbox", "优化目标").set_value("Max Drawdown").run()
    assert_healthy(app)
    assert run.call_count == 1
    widget(app, "number_input", "510880 布林周期").set_value(45).run()
    assert_healthy(app)
    assert run.call_count == 1
    assert any("请点击“开始优化”更新结果" in item.value for item in app.info)
    assert app_data.call_count == 2


def test_history_chart_uses_visible_final_date(app_data):
    import json

    app = AppTest.from_file(APP, default_timeout=15).run()
    widget(app, "button_group", "显示区间").set_value("自定义").run()
    widget(app, "date_input", "自定义日期范围").set_value((date(2026, 1, 5), date(2026, 2, 27))).run()
    assert_healthy(app)
    chart = json.loads(app.get("plotly_chart")[0].proto.spec)
    annotations = chart["layout"]["annotations"]
    assert annotations[-1]["x"].startswith("2026-02-27")
    assert "2026-02-27" in chart["layout"]["uirevision"]
    assert any("按图表末日 2026.02.27 计算" in item.value for item in app.markdown)
    widget(app, "button_group", "页面").set_value("持仓记录").run()
    widget(app, "button_group", "页面").set_value("行情总览").run()
    assert_healthy(app)
    chart = json.loads(app.get("plotly_chart")[0].proto.spec)
    assert chart["layout"]["annotations"][-1]["x"].startswith("2026-02-27")


def test_grid_deduplicates_floating_point_slider_values():
    from components.tab_optimize import run_optimization

    frame = pd.DataFrame({"close": np.linspace(1., 1.1, 20)}, index=pd.bdate_range("2024-01-01", periods=20))
    settings = {"window": 10, "num_std": 2.1 + .1 + .1 + .1, "first_batch_pct": .9,
                "scale_threshold": .02, "pyramid_levels": [], "pyramid_sizes": []}
    result = run_optimization.__wrapped__(frame, "粗略 (快)", settings)
    assert not result.duplicated(["Window", "StdDev"]).any()
    assert not result.pivot(index="StdDev", columns="Window", values="Total Return").empty


def test_hithink_source_without_key_has_setup_instructions(app_data, monkeypatch):
    from src.hithink_api import HithinkClient

    monkeypatch.setattr(HithinkClient, "fetch_etf_snapshot", lambda *args: pytest.fail("Missing key must not request snapshots"))
    app = AppTest.from_file(APP, default_timeout=15).run()
    widget(app, "selectbox", "行情来源").set_value("hithink").run()
    assert_healthy(app)
    key_input = widget(app, "text_input", "API Key")
    assert key_input.proto.type == key_input.proto.PASSWORD
    assert any("请填写 API Key" in item.value for item in app.info)
    assert any("接口原始口径" in item.value for item in app.caption)
    assert all(call.kwargs["provider"] == "hithink" for call in app_data.call_args_list[-2:])


def test_switching_provider_partitions_data_and_optimization(app_data, monkeypatch):
    from io import BytesIO
    from components import tab_optimize

    run = Mock(return_value=pd.DataFrame({"Window": [40], "StdDev": [2.1],
               "Total Return": [.1], "Sharpe Ratio": [1.], "Max Drawdown": [-.03]}))
    monkeypatch.setattr(tab_optimize, "run_optimization", run)
    download = Mock(return_value=False)
    monkeypatch.setattr(st, "download_button", download)
    app = AppTest.from_file(APP, default_timeout=15).run()
    widget(app, "button_group", "页面").set_value("参数研究").run()
    widget(app, "button", "开始优化").click().run()
    assert_healthy(app)
    widget(app, "selectbox", "行情来源").set_value("hithink").run()
    assert_healthy(app)
    assert any("请点击“开始优化”更新结果" in item.value for item in app.info)
    assert run.call_count == 1
    assert app_data.call_count == 4
    widget(app, "button", "开始优化").click().run()
    assert_healthy(app)
    exported = pd.read_csv(BytesIO(download.call_args.args[1]), dtype={"代码": str})
    assert exported["代码"].eq("510880").all()
    assert exported["行情来源"].eq("同花顺 Financial API").all()
    assert exported["价格口径"].eq("接口原始口径（无复权选项）").all()
    assert exported["数据开始"].notna().all() and exported["数据结束"].notna().all()
    assert "hithink" in download.call_args.kwargs["file_name"]


def test_changed_key_does_not_reuse_previous_credential_cache(app_data, monkeypatch):
    from src.hithink_api import HithinkClient
    monkeypatch.setattr(HithinkClient, "fetch_etf_snapshot", lambda self, symbol: {
        "symbol": symbol, "price": 1.25, "quote_time": None,
    })
    app = AppTest.from_file(APP, default_timeout=15).run()
    widget(app, "selectbox", "行情来源").set_value("hithink").run()
    before = app_data.call_count
    widget(app, "text_input", "API Key").set_value("mock-test-key-one").run()
    assert_healthy(app)
    assert app_data.call_count == before + 2
    widget(app, "text_input", "API Key").set_value("mock-test-key-two").run()
    assert_healthy(app)
    assert app_data.call_count == before + 4
    displayed = [item.value for item in list(app.markdown) + list(app.caption) + list(app.warning) + list(app.error)]
    assert not any("mock-test-key" in text for text in displayed)


def test_invalid_key_is_explained_without_crashing_dashboard(app_data):
    app = AppTest.from_file(APP, default_timeout=15).run()
    widget(app, "selectbox", "行情来源").set_value("hithink").run()
    widget(app, "text_input", "API Key").set_value("非有效密钥").run()
    assert_healthy(app)
    assert not any("非有效密钥" in item.value for item in app.warning)


def test_workspace_navigation_retains_chart_choices_without_refetch(app_data):
    import json

    app = AppTest.from_file(APP, default_timeout=15).run()
    widget(app, "radio", "选择 ETF").set_value("512890").run()
    widget(app, "button_group", "显示区间").set_value("近1月").run()
    widget(app, "radio", "图表类型").set_value("收盘线").run()
    assert_healthy(app)
    chart = json.loads(app.get("plotly_chart")[0].proto.spec)
    assert chart["data"][0]["type"] == "scatter"
    assert chart["data"][0]["name"] == "收盘价"
    for page in ["信号复盘", "持仓记录", "参数研究", "行情总览"]:
        widget(app, "button_group", "页面").set_value(page).run()
        assert_healthy(app)
    assert widget(app, "radio", "选择 ETF").value == "512890"
    assert widget(app, "button_group", "显示区间").value == "近1月"
    assert widget(app, "radio", "图表类型").value == "收盘线"
    assert app_data.call_count == 2


def test_portfolio_entry_isolated_and_independent_of_market_page(app_data, tmp_path):
    app = AppTest.from_file(APP, default_timeout=15).run()
    assert not any(item.label == "保存记录" for item in app.button)
    widget(app, "button_group", "页面").set_value("持仓记录").run()
    assert_healthy(app)
    assert any("从第一笔交易开始" in item.value for item in app.markdown)
    widget(app, "button", "保存记录").click().run()
    assert_healthy(app)
    records = load_records(tmp_path / "investment_records.csv")
    assert len(records) == 1
    assert widget(app, "button_group", "记录视图").value == "当前持仓"
    widget(app, "button_group", "记录视图").set_value("交易流水").run()
    assert_healthy(app)
    assert len(app.dataframe[0].value) == 1
    widget(app, "button_group", "记录视图").set_value("收益记录").run()
    assert_healthy(app)
    assert app_data.call_count == 2
