"""Notification regressions. All market and notification endpoints are mocked."""
from datetime import datetime, timedelta
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo
import json

import pandas as pd
import pytest

from scripts import check_signals as checker


NOW = datetime(2026, 9, 7, 15, 30, tzinfo=ZoneInfo('Asia/Shanghai'))
FETCH_REALTIME_QUOTES = checker.fetch_realtime_quotes
SUMMARIZE_SYMBOL = checker.summarize_symbol


def ready_status(**changes):
    status = {
        'symbol': '510880', 'name': '红利ETF', 'role': '核心',
        'is_ready': True, 'date': pd.Timestamp('2026-09-07'),
        'signal': 0.5, 'target_position': 0.5, 'close': 1.0, 'ma': 1.0,
        'lower_band': 0.9, 'upper_band': 1.1, 'signal_change': '+50%',
        'hint': '示例', 'state_label': '持仓', 'window': 40, 'num_std': 2.1,
    }
    status.update(changes)
    return status


@pytest.fixture(autouse=True)
def offline_runtime(monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW if tz else NOW.replace(tzinfo=None)

    monkeypatch.setattr(checker, 'datetime', Clock)
    monkeypatch.setattr(checker.os, 'chdir', lambda path: None)
    monkeypatch.setattr(checker.request, 'urlopen', MagicMock(side_effect=AssertionError('Unexpected network call')))
    monkeypatch.setattr(checker, 'send_pushplus', MagicMock(return_value={'code': 200, 'data': 'mock-message'}))
    monkeypatch.setattr(checker, 'summarize_symbol', MagicMock(return_value=ready_status()))
    monkeypatch.setattr(checker, 'fetch_realtime_quotes', MagicMock(return_value={}))
    monkeypatch.setattr(checker, 'HithinkClient', MagicMock(side_effect=AssertionError('Unexpected API client')))
    for key in (
        'SIGNAL_SYMBOLS', 'SIGNAL_DRY_RUN', 'SIGNAL_TIMEZONE', 'CHECK_SIGNALS_MODE',
        'ETF_DATA_PROVIDER', 'HITHINK_FINANCE_API_KEY',
    ):
        monkeypatch.delenv(key, raising=False)


def run_args(path, *extra):
    return ['--state-file', str(path), '--symbols', '510880', '--no-skip-weekends', *extra]


@pytest.mark.parametrize('signal', [0.0, 0.5])
def test_dry_run_never_creates_state(tmp_path, signal):
    path = tmp_path / 'new-directory' / 'state.json'
    checker.summarize_symbol.return_value = ready_status(signal=signal)
    assert checker.main(run_args(path, '--dry-run')) == 0
    assert not path.exists()
    assert not path.parent.exists()
    checker.send_pushplus.assert_not_called()


def test_dry_run_preserves_existing_state_byte_for_byte(tmp_path):
    path = tmp_path / 'state.json'
    original = '{"sent": {"existing": {"sent_at": "2026-01-01"}}}\n'
    path.write_text(original)
    checker.summarize_symbol.return_value = ready_status(signal=0.0)
    assert checker.main(run_args(path, '--dry-run')) == 0
    assert path.read_text() == original
    checker.send_pushplus.assert_not_called()


def test_weekend_dry_run_does_not_create_state(tmp_path, monkeypatch):
    class Weekend(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 9, 6, tzinfo=ZoneInfo('Asia/Shanghai'))

    monkeypatch.setattr(checker, 'datetime', Weekend)
    path = tmp_path / 'state.json'
    assert checker.main(['--state-file', str(path), '--dry-run', '--skip-weekends']) == 0
    assert not path.exists()
    checker.summarize_symbol.assert_not_called()
    checker.send_pushplus.assert_not_called()


@pytest.mark.parametrize('status', [
    {'is_ready': False, 'message': '行情数据为空'},
    ready_status(date=pd.Timestamp('2026-09-08')),
    ready_status(signal=float('nan')),
    ready_status(close=float('inf')),
])
def test_all_unusable_data_returns_failure_without_state_or_notification(tmp_path, status):
    path = tmp_path / 'state.json'
    checker.summarize_symbol.return_value = status
    assert checker.main(run_args(path)) == 1
    assert not path.exists()
    checker.send_pushplus.assert_not_called()


def test_duplicate_symbols_only_evaluated_and_notified_once(tmp_path):
    path = tmp_path / 'state.json'
    assert checker.main(run_args(path, '--symbols', '510880, 510880,510880')) == 0
    checker.summarize_symbol.assert_called_once()
    checker.send_pushplus.assert_called_once()
    assert '(1 条)' in checker.send_pushplus.call_args.args[0]
    state = json.loads(path.read_text())
    assert len(state['sent']) == 1


def test_successful_notification_is_deduplicated_on_next_run(tmp_path):
    path = tmp_path / 'state.json'
    assert checker.main(run_args(path)) == 0
    assert checker.main(run_args(path)) == 0
    checker.send_pushplus.assert_called_once()
    assert len(json.loads(path.read_text())['sent']) == 1


def test_failed_notification_is_not_marked_sent(tmp_path):
    path = tmp_path / 'state.json'
    checker.send_pushplus.side_effect = RuntimeError('mock delivery failure')
    assert checker.main(run_args(path)) == 2
    assert json.loads(path.read_text())['sent'] == {}


@pytest.mark.parametrize('changes', [
    {'date': '2026-09-08'}, {'date': 'NaT'}, {'date': 'invalid'},
    {'signal': float('inf')}, {'signal': float('nan')},
    {'target_position': float('inf')}, {'target_position': 1.5},
    {'close': 0}, {'close': float('inf')}, {'ma': float('nan')},
    {'lower_band': 1.2}, {'upper_band': float('inf')},
])
def test_corrupt_or_future_signal_does_not_create_alert(changes):
    assert checker.build_alert(ready_status(**changes), today=NOW, max_signal_age_days=-1) is None


def test_stale_signal_rule_still_applies():
    status = ready_status(date=pd.Timestamp('2026-09-03'))
    assert checker.build_alert(status, today=NOW, max_signal_age_days=2) is None
    assert checker.build_alert(status, today=NOW, max_signal_age_days=-1) is not None


@pytest.mark.parametrize('value', [float('inf'), float('-inf'), float('nan'), 'inf', 'NaN', -1, 0, None, '-'])
def test_nonfinite_and_nonpositive_quote_prices_are_rejected(value):
    assert checker.parse_quote_float(value) is None


def test_valid_quote_price_is_parsed():
    assert checker.parse_quote_float('1.23') == 1.23


@pytest.mark.parametrize('quote', [
    checker.RealtimeQuote('510880', float('inf'), NOW),
    checker.RealtimeQuote('512890', 1.01, NOW),
    checker.RealtimeQuote('510880', 1.01, NOW + timedelta(days=1)),
])
def test_invalid_realtime_quote_falls_back_to_valid_close(quote):
    band = checker.build_band_status(ready_status(), quote, today=NOW)
    assert band.price == 1.0
    assert band.price_source == '最新日线收盘价'


def test_status_mode_all_unready_returns_failure(tmp_path):
    checker.summarize_symbol.return_value = {'is_ready': False}
    assert checker.main(run_args(tmp_path / 'state.json', '--mode', 'status', '--no-require-today-quote')) == 1
    checker.send_pushplus.assert_not_called()


@pytest.mark.parametrize('payload', [
    {'data': None}, {'data': {'diff': []}},
    {'data': {'diff': [{'f12': '510880', 'f2': 'inf'}]}},
    {'data': {'diff': [None, 'bad-row']}},
])
def test_empty_or_corrupt_quote_response_is_safe(monkeypatch, payload):
    response = MagicMock()
    response.read.return_value = json.dumps(payload).encode()
    monkeypatch.setattr(checker.request, 'urlopen', MagicMock(return_value=response))
    assert checker.fetch_realtime_quotes_once(['510880'], timezone=NOW.tzinfo) == {}


def test_bad_quote_timestamp_does_not_discard_valid_price(monkeypatch):
    response = MagicMock()
    response.read.return_value = json.dumps({'data': {'diff': [
        {'f12': '510880', 'f2': '1.23', 'f124': 1e300},
    ]}}).encode()
    monkeypatch.setattr(checker.request, 'urlopen', MagicMock(return_value=response))
    quotes = checker.fetch_realtime_quotes_once(['510880'], timezone=NOW.tzinfo)
    assert quotes['510880'].price == 1.23
    assert quotes['510880'].quote_time is None


def test_symbol_order_is_preserved_and_empty_selection_rejected():
    assert checker.parse_symbols('512890,510880,512890') == ['512890', '510880']
    with pytest.raises(ValueError):
        checker.parse_symbols(' , , ')


@pytest.mark.parametrize('mode', ['signals', 'status'])
def test_hithink_missing_key_fails_safely_before_any_fetch(tmp_path, caplog, mode):
    path = tmp_path / 'state.json'
    assert checker.main(run_args(path, '--provider', 'hithink', '--mode', mode, '--dry-run')) == 1
    assert 'HITHINK_FINANCE_API_KEY' in caplog.text
    assert not path.exists()
    checker.summarize_symbol.assert_not_called()
    checker.fetch_realtime_quotes.assert_not_called()
    checker.HithinkClient.assert_not_called()
    checker.send_pushplus.assert_not_called()


@pytest.mark.parametrize('mode', ['signals', 'status'])
def test_hithink_env_routes_both_modes_without_sending(tmp_path, monkeypatch, capsys, mode):
    monkeypatch.setenv('ETF_DATA_PROVIDER', 'hithink')
    monkeypatch.setenv('HITHINK_FINANCE_API_KEY', 'test-only-secret')
    checker.summarize_symbol.return_value = ready_status(provider='hithink')
    path = tmp_path / 'state.json'
    assert checker.main(run_args(
        path, '--mode', mode, '--dry-run', '--no-require-today-quote',
    )) == 0
    assert checker.summarize_symbol.call_args.kwargs['provider'] == 'hithink'
    if mode == 'status':
        assert checker.fetch_realtime_quotes.call_args.kwargs['provider'] == 'hithink'
    content = capsys.readouterr().out
    assert '同花顺 Financial API' in content
    assert '接口原始口径' in content
    assert 'test-only-secret' not in content
    assert not path.exists()
    checker.send_pushplus.assert_not_called()


def test_cli_provider_overrides_environment(tmp_path, monkeypatch):
    monkeypatch.setenv('ETF_DATA_PROVIDER', 'hithink')
    assert checker.main(run_args(tmp_path / 'state.json', '--provider', 'akshare', '--dry-run')) == 0
    assert checker.summarize_symbol.call_args.kwargs['provider'] == 'akshare'


def test_invalid_provider_environment_is_safe(tmp_path, monkeypatch):
    monkeypatch.setenv('ETF_DATA_PROVIDER', 'unsupported')
    assert checker.main(run_args(tmp_path / 'state.json', '--dry-run')) == 1
    checker.summarize_symbol.assert_not_called()
    checker.send_pushplus.assert_not_called()


def test_hithink_realtime_failure_keeps_successful_quotes_without_switching_provider(monkeypatch, caplog):
    client = MagicMock()
    client.fetch_etf_snapshot.side_effect = [
        {'symbol': '510880', 'price': 1.23, 'quote_time': '2026-09-07 14:30:00'},
        RuntimeError('Authorization: Bearer test-only-secret'),
    ]
    monkeypatch.setattr(checker, 'HithinkClient', MagicMock(return_value=client))
    eastmoney = MagicMock(side_effect=AssertionError('Must not switch provider'))
    monkeypatch.setattr(checker, 'fetch_realtime_quotes_once', eastmoney)
    quotes = FETCH_REALTIME_QUOTES(
        ['510880', '512890'], timezone=NOW.tzinfo, provider='hithink', api_key='test-only-secret',
    )
    assert list(quotes) == ['510880']
    assert quotes['510880'].price == 1.23
    assert quotes['510880'].provider == 'hithink'
    assert quotes['510880'].quote_time == NOW.replace(hour=14)
    assert client.fetch_etf_snapshot.call_count == 2
    assert 'test-only-secret' not in caplog.text
    eastmoney.assert_not_called()


@pytest.mark.parametrize('snapshot', [
    None, {'symbol': '512890', 'price': 1.2},
    {'symbol': '510880', 'price': float('inf')},
    {'symbol': '510880', 'price': 0},
])
def test_hithink_invalid_snapshot_is_ignored(monkeypatch, snapshot):
    client = MagicMock()
    client.fetch_etf_snapshot.return_value = snapshot
    monkeypatch.setattr(checker, 'HithinkClient', MagicMock(return_value=client))
    assert FETCH_REALTIME_QUOTES(
        ['510880'], timezone=NOW.tzinfo, provider='hithink', api_key='test-only-secret',
    ) == {}


def test_hithink_invalid_timestamp_keeps_price_but_cannot_claim_today(monkeypatch):
    client = MagicMock()
    client.fetch_etf_snapshot.return_value = {
        'symbol': '510880', 'price': 1.2, 'quote_time': 'invalid',
    }
    monkeypatch.setattr(checker, 'HithinkClient', MagicMock(return_value=client))
    quotes = FETCH_REALTIME_QUOTES(
        ['510880'], timezone=NOW.tzinfo, provider='hithink', api_key='test-only-secret',
    )
    assert quotes['510880'].price == 1.2
    assert quotes['510880'].quote_time is None


def test_hithink_daily_load_uses_provider_default_price_basis(monkeypatch):
    daily = MagicMock(return_value=pd.DataFrame({'close': [1.0]}))
    monkeypatch.setattr(checker, 'fetch_etf_data', daily)
    monkeypatch.setattr(checker, 'calculate_monitor_frame', MagicMock(return_value=pd.DataFrame()))
    monkeypatch.setattr(checker, 'summarize_monitor_status', MagicMock(return_value=ready_status()))
    status = SUMMARIZE_SYMBOL(
        '510880', start_date='20250901', force_update=False, provider='hithink', api_key='test-only-secret',
    )
    assert daily.call_args.kwargs['provider'] == 'hithink'
    assert daily.call_args.kwargs.get('adjust') is None
    assert status['provider'] == 'hithink'
    assert '接口原始口径' in status['price_basis']


def test_hithink_daily_exception_is_redacted_and_unready(monkeypatch, caplog):
    monkeypatch.setattr(checker, 'fetch_etf_data', MagicMock(side_effect=RuntimeError('test-only-secret')))
    status = SUMMARIZE_SYMBOL('510880', start_date='20250901', force_update=False, provider='hithink')
    assert not status['is_ready']
    assert status['provider'] == 'hithink'
    assert 'test-only-secret' not in caplog.text
    assert 'test-only-secret' not in str(status)


def test_realtime_from_another_provider_falls_back_to_own_daily_close():
    quote = checker.RealtimeQuote('510880', 1.23, NOW, provider='akshare')
    band = checker.build_band_status(ready_status(provider='hithink'), quote, today=NOW)
    assert band.price == 1.0
    assert band.price_source == '最新日线收盘价'
    assert band.provider == 'hithink'
    assert '接口原始口径' in band.price_basis


def test_hithink_quote_and_daily_bands_render_source_and_basis():
    quote = checker.RealtimeQuote('510880', 1.03, NOW, provider='hithink')
    band = checker.build_band_status(ready_status(provider='hithink'), quote, today=NOW)
    assert band.price == 1.03
    assert band.price_source == '实时价'
    content = checker.render_band_status_content([band], generated_at=NOW)
    assert '同花顺 Financial API' in content
    assert '接口原始口径' in content


def test_signal_deduplication_is_separate_for_each_provider():
    akshare_alert = checker.build_alert(ready_status(), today=NOW, max_signal_age_days=2)
    hithink_alert = checker.build_alert(ready_status(provider='hithink'), today=NOW, max_signal_age_days=2)
    assert akshare_alert.key.startswith('510880:')
    assert hithink_alert.key == f'hithink:{akshare_alert.key}'


@pytest.mark.parametrize('quote_time', [None, NOW - timedelta(days=1)])
def test_hithink_status_requires_today_quote_even_in_dry_run(tmp_path, monkeypatch, quote_time):
    monkeypatch.setenv('HITHINK_FINANCE_API_KEY', 'test-only-secret')
    checker.fetch_realtime_quotes.return_value = {
        '510880': checker.RealtimeQuote('510880', 1.03, quote_time, provider='hithink'),
    }
    path = tmp_path / 'state.json'
    assert checker.main(run_args(
        path, '--provider', 'hithink', '--mode', 'status', '--dry-run', '--require-today-quote',
    )) == 0
    assert not path.exists()
    checker.summarize_symbol.assert_not_called()
    checker.send_pushplus.assert_not_called()
