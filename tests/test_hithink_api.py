"""Offline contract tests: no API key, live endpoint or user data is accessed."""

import http.client
import io
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from src import hithink_api
from src.hithink_api import HithinkAPIError, HithinkClient


_KEY = 'test-only-never-a-real-api-key'
_TZ = ZoneInfo('Asia/Shanghai')
_THSCODE = '510880.SH'


def _ms(value):
    return int(pd.Timestamp(value, tz='Asia/Shanghai').timestamp() * 1000)


def _envelope(data, code=0, message='success'):
    return {'code': code, 'message': message, 'request_id': 'test-request', 'data': data}


def _metadata(items=None):
    return _envelope({'timestamp': _ms('2026-01-01'), 'item': items if items is not None else [{
        'ticker': '510880', 'thscode': _THSCODE, 'asset_type': 'fund-etf', 'exchange': 'SH',
    }]})


def _bar(day='2026-01-05', **changes):
    result = {
        'date_ms': _ms(day), 'open_price': 1.1, 'high_price': 1.3,
        'low_price': 1.0, 'close_price': 1.2, 'volume': 10000, 'turnover': 12000,
    }
    result.update(changes)
    return result


def _history(items=None, **changes):
    data = {
        'timestamp': _ms('2026-01-05'), 'thscode': _THSCODE,
        'interval': '1d', 'adjust': None, 'item': items if items is not None else [_bar()],
    }
    data.update(changes)
    return _envelope(data)


def _snapshot(**changes):
    data = {'timestamp': _ms('2026-01-05 14:35:01'), 'item': [{
        'thscode': _THSCODE, 'ticker': '510880', 'last_price': 1.234,
    }]}
    data.update(changes)
    return _envelope(data)


class _Response(io.BytesIO):
    def __init__(self, payload, *, url='https://fuyao.aicubes.cn/api/test', status=200):
        raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode('utf-8')
        super().__init__(raw)
        self.url = url
        self.status = status

    def geturl(self):
        return self.url

    def getcode(self):
        return self.status


class _Opener:
    def __init__(self):
        self.replies = []
        self.calls = []

    def open(self, request, timeout):
        self.calls.append((request, timeout))
        assert self.replies, 'Unexpected request in an offline test'
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply if isinstance(reply, _Response) else _Response(reply)


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    opener = _Opener()
    monkeypatch.setattr(hithink_api.urllib.request, 'build_opener', lambda *_: opener)
    monkeypatch.setattr(hithink_api.time, 'sleep', Mock())
    return opener


def test_snapshot_resolves_exact_etf_and_caches_code(offline):
    offline.replies = [_metadata(), _snapshot(), _snapshot()]
    client = HithinkClient(_KEY, timeout=7)
    quote = client.fetch_etf_snapshot('510880')
    client.fetch_etf_snapshot('510880.SH')
    assert quote == {
        'symbol': '510880', 'price': 1.234,
        'quote_time': datetime(2026, 1, 5, 14, 35, 1, tzinfo=_TZ),
        'data_source': '同花顺 Financial API', 'price_basis': '接口原始口径',
    }
    assert len(offline.calls) == 3
    first, timeout = offline.calls[0]
    assert timeout == 7
    assert first.get_method() == 'GET'
    assert first.get_header('X-api-key') == _KEY
    assert _KEY not in first.full_url
    parts = urllib.parse.urlsplit(first.full_url)
    assert parts.path == '/api/meta/tickers/search'
    assert urllib.parse.parse_qs(parts.query) == {
        'q': ['510880'], 'asset_type': ['fund-etf'], 'limit': ['50'],
    }
    snapshot_parts = urllib.parse.urlsplit(offline.calls[1][0].full_url)
    assert snapshot_parts.path == '/api/fund/market/snapshot'
    assert urllib.parse.parse_qs(snapshot_parts.query) == {'thscode': [_THSCODE]}


def test_metadata_ignores_fuzzy_results_and_other_asset_types(offline):
    offline.replies = [_metadata([
        {'ticker': '510880', 'thscode': '510880.OF', 'asset_type': 'fund-otc'},
        {'ticker': '510881', 'thscode': '510881.SH', 'asset_type': 'fund-etf'},
        {'ticker': '510880', 'thscode': _THSCODE, 'asset_type': 'fund-etf'},
    ]), _snapshot()]
    assert HithinkClient(_KEY).fetch_etf_snapshot('510880')['price'] == 1.234


@pytest.mark.parametrize('items', [
    [],
    [{'ticker': '510881', 'thscode': '510881.SH', 'asset_type': 'fund-etf'}],
    [{'ticker': '510880', 'thscode': _THSCODE, 'asset_type': 'a-share'}],
    [
        {'ticker': '510880', 'thscode': _THSCODE, 'asset_type': 'fund-etf'},
        {'ticker': '510880', 'thscode': '510880.SZ', 'asset_type': 'fund-etf'},
    ],
])
def test_ambiguous_or_non_etf_symbols_never_reach_market_endpoint(offline, items):
    offline.replies = [_metadata(items)]
    with pytest.raises(HithinkAPIError, match='唯一确认'):
        HithinkClient(_KEY).fetch_etf_snapshot('510880')
    assert len(offline.calls) == 1


def test_explicit_suffix_must_match_resolved_code(offline):
    offline.replies = [_metadata()]
    with pytest.raises(HithinkAPIError, match='唯一确认'):
        HithinkClient(_KEY).fetch_etf_snapshot('510880.SZ')
    assert len(offline.calls) == 1


@pytest.mark.parametrize('symbol', ['', 'ABC', '510880,512890', '510880.SH?key=bad', 510880])
def test_invalid_symbol_does_not_make_request(offline, symbol):
    with pytest.raises(HithinkAPIError):
        HithinkClient(_KEY).fetch_etf_snapshot(symbol)
    assert not offline.calls


def test_history_normalizes_dates_without_changing_original_units(offline):
    offline.replies = [_metadata(), _history([
        _bar('2026-01-06', close_price=1.25),
        _bar('2026-01-04'),  # Server overfetch must not escape the requested range.
        _bar('2026-01-05', volume=None, turnover=None),
        _bar('2026-01-06', close_price=1.26),
        _bar('2026-01-07'),
    ])]
    frame = HithinkClient(_KEY).fetch_etf_history('510880', '20260105', '2026-01-06')
    assert frame.index.equals(pd.DatetimeIndex(['2026-01-05', '2026-01-06'], name='date'))
    assert list(frame.columns) == ['open', 'high', 'low', 'close', 'volume', 'amount']
    assert frame.loc['2026-01-06', 'close'] == 1.26
    assert pd.isna(frame.loc['2026-01-05', 'volume'])
    assert pd.isna(frame.loc['2026-01-05', 'amount'])
    assert frame.loc['2026-01-06', 'volume'] == 10000
    assert frame.loc['2026-01-06', 'amount'] == 12000
    assert frame.attrs == {
        'provider': 'hithink', 'price_basis': '接口原始口径', 'volume_unit': '接口原始单位',
    }
    request = urllib.parse.urlsplit(offline.calls[1][0].full_url)
    assert request.path == '/api/fund/market/historical'
    params = urllib.parse.parse_qs(request.query)
    assert params == {
        'thscode': [_THSCODE], 'interval': ['1d'],
        'start': [str(_ms('2026-01-05'))],
        'end': [str(_ms('2026-01-07') - 1)],
    }


def test_history_handles_leap_year_windows_without_gaps_or_overlap(offline):
    offline.replies = [
        _metadata(), _history([_bar('2020-02-29')]),
        _history([_bar('2025-02-28'), _bar('2025-03-01')]),
    ]
    frame = HithinkClient(_KEY).fetch_etf_history('510880', date(2020, 2, 29), date(2025, 3, 1))
    assert frame.index.strftime('%Y-%m-%d').tolist() == ['2020-02-29', '2025-02-28', '2025-03-01']
    windows = [urllib.parse.parse_qs(urllib.parse.urlsplit(call[0].full_url).query)
               for call in offline.calls[1:]]
    assert int(windows[0]['start'][0]) == _ms('2020-02-29')
    assert int(windows[0]['end'][0]) == _ms('2025-02-28') - 1
    assert int(windows[1]['start'][0]) == int(windows[0]['end'][0]) + 1
    assert int(windows[1]['end'][0]) == _ms('2025-03-02') - 1


def test_later_history_window_failure_never_returns_partial_data(offline):
    offline.replies = [
        _metadata(), _history([_bar('2020-01-02')]), _envelope(None, 2003, _KEY),
    ]
    with pytest.raises(HithinkAPIError, match='密钥'):
        HithinkClient(_KEY).fetch_etf_history('510880', '20200101', '20260101')
    assert len(offline.calls) == 3


def test_history_allows_omitted_adjust_and_empty_closed_market(offline):
    payload = _history([])
    del payload['data']['adjust']
    offline.replies = [_metadata(), payload]
    frame = HithinkClient(_KEY).fetch_etf_history('510880', '20260101', '20260101')
    assert frame.empty and frame.index.name == 'date'
    assert frame.attrs['price_basis'] == '接口原始口径'


@pytest.mark.parametrize('changes', [
    {'thscode': '512890.SH'}, {'interval': '1m'}, {'adjust': 'forward'}, {'item': None},
])
def test_history_rejects_wrong_identity_basis_or_shape(offline, changes):
    offline.replies = [_metadata(), _history(**changes)]
    with pytest.raises(HithinkAPIError, match='格式或行情数值'):
        HithinkClient(_KEY).fetch_etf_history('510880', '20260101', '20260110')


@pytest.mark.parametrize('changes', [
    {'date_ms': None}, {'date_ms': '2026-01-05'}, {'date_ms': True},
    {'open_price': None}, {'close_price': 0}, {'close_price': 2},
    {'high_price': float('inf')}, {'low_price': -1}, {'volume': -1},
    {'turnover': '12000'}, {'close_price': True}, {'volume': 10 ** 1000},
])
def test_invalid_history_values_are_not_fabricated_or_silently_removed(offline, changes):
    offline.replies = [_metadata(), _history([_bar(**changes)])]
    with pytest.raises(HithinkAPIError):
        HithinkClient(_KEY).fetch_etf_history('510880', '20260101', '20260110')


@pytest.mark.parametrize('start,end', [
    ('20260230', '20260301'), ('20260102', '20260101'), (None, '20260101'),
    (20260101, '20260102'), (pd.NaT, '20260102'), ('bad', '20260102'),
])
def test_invalid_history_dates_do_not_make_requests(offline, start, end):
    with pytest.raises(HithinkAPIError, match='日期'):
        HithinkClient(_KEY).fetch_etf_history('510880', start, end)
    assert not offline.calls


def test_datetime_input_uses_shanghai_calendar_day(offline):
    offline.replies = [_metadata(), _history()]
    utc_day = datetime(2026, 1, 4, 18, tzinfo=timezone.utc)
    frame = HithinkClient(_KEY).fetch_etf_history('510880', utc_day, utc_day + timedelta(hours=1))
    assert frame.index.tolist() == [pd.Timestamp('2026-01-05')]


def test_missing_snapshot_time_is_not_replaced_with_current_time(offline):
    offline.replies = [_metadata(), _snapshot(timestamp=None)]
    assert HithinkClient(_KEY).fetch_etf_snapshot('510880')['quote_time'] is None


@pytest.mark.parametrize('data', [
    {'timestamp': 'bad', 'item': [{'thscode': _THSCODE, 'ticker': '510880', 'last_price': 1}]},
    {'timestamp': None, 'item': [{'thscode': '512890.SH', 'ticker': '512890', 'last_price': 1}]},
    {'timestamp': None, 'item': [{'thscode': _THSCODE, 'ticker': '510880', 'last_price': None}]},
    {'timestamp': None, 'item': []},
])
def test_invalid_or_empty_snapshot_fails_safely(offline, data):
    offline.replies = [_metadata(), _envelope(data)]
    with pytest.raises(HithinkAPIError):
        HithinkClient(_KEY).fetch_etf_snapshot('510880')


@pytest.mark.parametrize('code', [1001, 1002, 1003, 1004, 2001, 2003, 3001, 3002, 3004, 9999])
def test_non_retryable_business_errors_do_not_leak_message(offline, code):
    offline.replies = [_envelope(None, code, f'upstream echoes {_KEY}')]
    with pytest.raises(HithinkAPIError) as caught:
        HithinkClient(_KEY).fetch_etf_snapshot('510880')
    assert len(offline.calls) == 1
    assert caught.value.code == code
    assert _KEY not in str(caught.value)
    assert 'upstream' not in repr(caught.value)
    assert not hithink_api.time.sleep.called


@pytest.mark.parametrize('code', [4001, 5001, 5002, 5003])
def test_transient_business_failures_retry_then_succeed(offline, code):
    offline.replies = [_envelope(None, code), _metadata(), _snapshot()]
    assert HithinkClient(_KEY).fetch_etf_snapshot('510880')['price'] == 1.234
    assert len(offline.calls) == 3
    hithink_api.time.sleep.assert_called_once_with(0.5)


@pytest.mark.parametrize('error', [
    urllib.error.URLError(_KEY), TimeoutError(_KEY), OSError(_KEY),
    http.client.IncompleteRead(b'test-only-never-a-real-api-key'),
])
def test_network_retries_are_bounded_and_errors_are_safe(offline, error):
    offline.replies = [error, error, error]
    with pytest.raises(HithinkAPIError) as caught:
        HithinkClient(_KEY, max_retries=2).fetch_etf_snapshot('510880')
    assert len(offline.calls) == 3
    assert hithink_api.time.sleep.call_count == 2
    assert _KEY not in str(caught.value)
    assert caught.value.__suppress_context__


@pytest.mark.parametrize('status,retry', [(401, False), (403, False), (404, False), (429, True), (503, True)])
def test_http_status_retry_policy(offline, status, retry):
    offline.replies = [urllib.error.HTTPError('https://fuyao.aicubes.cn', status, _KEY, {}, None)]
    if retry:
        offline.replies.extend([_metadata(), _snapshot()])
        assert HithinkClient(_KEY).fetch_etf_snapshot('510880')['price'] == 1.234
        assert len(offline.calls) == 3
    else:
        with pytest.raises(HithinkAPIError) as caught:
            HithinkClient(_KEY).fetch_etf_snapshot('510880')
        assert _KEY not in str(caught.value)
        assert len(offline.calls) == 1


def test_http_error_closes_a_real_response_body(offline):
    body = io.BytesIO(b'not printed in errors')
    offline.replies = [urllib.error.HTTPError(
        'https://fuyao.aicubes.cn', 403, _KEY, {}, body,
    )]
    with pytest.raises(HithinkAPIError, match='密钥'):
        HithinkClient(_KEY).fetch_etf_snapshot('510880')
    assert body.closed


def test_non_200_response_without_urllib_exception_is_closed(offline):
    response = _Response(b'not printed in errors', status=403)
    offline.replies = [response]
    with pytest.raises(HithinkAPIError, match='密钥'):
        HithinkClient(_KEY).fetch_etf_snapshot('510880')
    assert response.closed


def test_http_body_cleanup_failure_does_not_expose_original_error(offline):
    body = io.BytesIO(b'')
    error = urllib.error.HTTPError('https://fuyao.aicubes.cn', 403, _KEY, {}, body)
    error.close = Mock(side_effect=OSError(_KEY))
    offline.replies = [error]
    with pytest.raises(HithinkAPIError, match='密钥') as caught:
        HithinkClient(_KEY).fetch_etf_snapshot('510880')
    assert _KEY not in str(caught.value)
    error.close.assert_called_once()
    body.close()


@pytest.mark.parametrize('payload', [b'not JSON', b'\xff', [], {'data': {}},
                                     {'code': True, 'data': {}}, {'code': 0, 'data': None}])
def test_invalid_response_envelopes_do_not_retry(offline, payload):
    offline.replies = [payload]
    with pytest.raises(HithinkAPIError, match='格式或行情数值'):
        HithinkClient(_KEY).fetch_etf_snapshot('510880')
    assert len(offline.calls) == 1


def test_oversized_response_is_rejected(offline, monkeypatch):
    monkeypatch.setattr(hithink_api, '_MAX_RESPONSE_BYTES', 16)
    offline.replies = [_metadata()]
    with pytest.raises(HithinkAPIError, match='格式或行情数值'):
        HithinkClient(_KEY).fetch_etf_snapshot('510880')


@pytest.mark.parametrize('target', [
    'https://other.example/api', 'http://fuyao.aicubes.cn/api',
    'https://fuyao.aicubes.cn:444/api', 'https://fuyao.aicubes.cn.evil.example/api',
    'https://user:password@fuyao.aicubes.cn/api',
])
def test_redirects_cannot_forward_key_to_another_origin(target):
    request = urllib.request.Request('https://fuyao.aicubes.cn/api/test', headers={'X-api-key': _KEY})
    handler = hithink_api._OfficialRedirectHandler()
    with pytest.raises(HithinkAPIError, match='非官方地址') as caught:
        handler.redirect_request(request, None, 302, '', {}, target)
    assert _KEY not in str(caught.value)


def test_same_origin_https_redirect_is_allowed():
    request = urllib.request.Request('https://fuyao.aicubes.cn/api/test', headers={'X-api-key': _KEY})
    redirected = hithink_api._OfficialRedirectHandler().redirect_request(
        request, None, 302, '', {}, 'https://fuyao.aicubes.cn/api/test/',
    )
    assert redirected.get_header('X-api-key') == _KEY


def test_final_response_origin_is_checked_defensively(offline):
    offline.replies = [_Response(_metadata(), url='https://other.example/api')]
    with pytest.raises(HithinkAPIError, match='非官方地址'):
        HithinkClient(_KEY).fetch_etf_snapshot('510880')
    assert len(offline.calls) == 1


@pytest.mark.parametrize('kwargs', [
    {'api_key': ''}, {'api_key': None}, {'api_key': 'key\r\nHeader: bad'},
    {'api_key': '密钥'}, {'api_key': _KEY, 'timeout': 0},
    {'api_key': _KEY, 'timeout': float('inf')}, {'api_key': _KEY, 'timeout': 61},
    {'api_key': _KEY, 'max_retries': -1}, {'api_key': _KEY, 'max_retries': 4},
    {'api_key': _KEY, 'max_retries': True},
])
def test_invalid_client_configuration_is_safe(offline, kwargs):
    with pytest.raises(HithinkAPIError, match='配置无效') as caught:
        HithinkClient(**kwargs)
    assert _KEY not in str(caught.value)
    assert not offline.calls


def test_unknown_error_kind_cannot_display_untrusted_text():
    error = HithinkAPIError(f'upstream leaked {_KEY}', code=_KEY)
    assert _KEY not in str(error)
    assert error.code is None
