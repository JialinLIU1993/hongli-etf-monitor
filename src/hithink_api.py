"""Small REST client for HiThink's ETF market API, without an SDK dependency.

ETF daily prices have the API's original price basis; this endpoint has no
forward-adjustment parameter. Keep these prices separate from adjusted caches.
Contract: https://github.com/HiThink-Tech/Financial-API/blob/main/docs/api/endpoints-fund.md
"""

import calendar
import http.client
import json
import math
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, time as daytime, timedelta, timezone
from numbers import Real
from zoneinfo import ZoneInfo

import pandas as pd


_BASE_URL = 'https://fuyao.aicubes.cn'
_SHANGHAI = ZoneInfo('Asia/Shanghai')
_MAX_RESPONSE_BYTES = 8 * 1024 * 1024
_COLUMNS = ['open', 'high', 'low', 'close', 'volume', 'amount']
_ATTRS = {
    'provider': 'hithink',
    'price_basis': '接口原始口径',
    'volume_unit': '接口原始单位',
}
_ERROR_MESSAGES = {
    'configuration': '同花顺 API 配置无效，请检查密钥、超时和重试设置。',
    'symbol': '无法唯一确认该 ETF 代码，请检查基金代码及资产类型。',
    'date': '同花顺行情查询日期无效，请检查起止日期。',
    'parameter': '同花顺 API 查询参数无效，请检查代码和日期范围。',
    'authentication': '同花顺 API 密钥无效或权限不足，请检查密钥配置。',
    'unavailable': '同花顺 API 暂无该 ETF 的可用行情。',
    'unsupported': '同花顺 API 暂不支持该标的的行情能力。',
    'rate_limit': '同花顺 API 请求过于频繁，请稍后重试。',
    'network': '无法连接同花顺 API，请检查网络后重试。',
    'service': '同花顺 API 服务暂时不可用，请稍后重试。',
    'response': '同花顺 API 返回的数据格式或行情数值无效。',
    'redirect': '同花顺 API 返回了非官方地址跳转，已停止请求。',
}


class HithinkAPIError(Exception):
    """Public errors contain fixed messages, never upstream text or credentials."""

    def __init__(self, kind='service', *, code=None):
        self.kind = kind if kind in _ERROR_MESSAGES else 'service'
        self.code = code if type(code) is int else None
        super().__init__(_ERROR_MESSAGES[self.kind])


def _is_official_origin(url):
    try:
        parts = urllib.parse.urlsplit(url)
        return (
            parts.scheme == 'https'
            and parts.hostname == 'fuyao.aicubes.cn'
            and parts.port in (None, 443)
            and parts.username is None
            and parts.password is None
        )
    except (TypeError, ValueError):
        return False


class _OfficialRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _is_official_origin(newurl):
            raise HithinkAPIError('redirect') from None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _symbol_parts(symbol):
    if not isinstance(symbol, str):
        raise HithinkAPIError('symbol')
    normalized = symbol.strip().upper()
    if not re.fullmatch(r'[0-9]{6}(?:\.(?:SH|SZ|BJ))?', normalized):
        raise HithinkAPIError('symbol')
    return normalized[:6], normalized if '.' in normalized else None


def _day(value):
    try:
        if isinstance(value, str):
            if re.fullmatch(r'[0-9]{8}', value):
                return datetime.strptime(value, '%Y%m%d').date()
            if re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', value):
                return datetime.strptime(value, '%Y-%m-%d').date()
        elif isinstance(value, datetime) and not pd.isna(value):
            if value.tzinfo is not None:
                value = value.astimezone(_SHANGHAI)
            return value.date()
        elif isinstance(value, date) and not pd.isna(value):
            return value
    except (OverflowError, TypeError, ValueError):
        pass
    raise HithinkAPIError('date') from None


def _number(value, *, nullable=False, positive=False):
    if value is None and nullable:
        return float('nan')
    if isinstance(value, bool) or not isinstance(value, Real):
        raise HithinkAPIError('response')
    try:
        number = float(value)
    except (OverflowError, TypeError, ValueError):
        raise HithinkAPIError('response') from None
    if not math.isfinite(number) or (number <= 0 if positive else number < 0):
        raise HithinkAPIError('response')
    return number


def _datetime_ms(value):
    if isinstance(value, bool) or not isinstance(value, Real):
        raise HithinkAPIError('response')
    try:
        number = float(value)
        if not math.isfinite(number) or number != int(number):
            raise ValueError
        return datetime.fromtimestamp(number / 1000, tz=timezone.utc).astimezone(_SHANGHAI)
    except (OSError, OverflowError, TypeError, ValueError):
        raise HithinkAPIError('response') from None


def _items(data):
    result = data.get('item')
    if not isinstance(result, list) or any(not isinstance(item, dict) for item in result):
        raise HithinkAPIError('response')
    return result


def _api_error(code):
    if code in (2001, 2003) or 2000 <= code < 3000:
        return HithinkAPIError('authentication', code=code)
    if 1000 <= code < 2000:
        return HithinkAPIError('parameter', code=code)
    if code == 3001:
        return HithinkAPIError('symbol', code=code)
    if code == 3002:
        return HithinkAPIError('unavailable', code=code)
    if code == 3004:
        return HithinkAPIError('unsupported', code=code)
    if code == 4001:
        return HithinkAPIError('rate_limit', code=code)
    return HithinkAPIError('service', code=code)


class HithinkClient:
    """Authenticated, bounded read-only access to the official ETF endpoints."""

    def __init__(self, api_key: str, timeout=15.0, max_retries=2):
        if (
            not isinstance(api_key, str)
            or not api_key.strip()
            or any(ord(char) < 32 or ord(char) > 126 for char in api_key)
            or isinstance(timeout, bool)
            or not isinstance(timeout, Real)
            or not math.isfinite(float(timeout))
            or not 0 < timeout <= 60
            or type(max_retries) is not int
            or not 0 <= max_retries <= 3
        ):
            raise HithinkAPIError('configuration')
        self._api_key = api_key.strip()
        self.timeout = float(timeout)
        self.max_retries = max_retries
        self._opener = urllib.request.build_opener(_OfficialRedirectHandler())
        self._symbols = {}

    def _get(self, path, params):
        request = urllib.request.Request(
            f'{_BASE_URL}{path}?{urllib.parse.urlencode(params)}',
            headers={'X-api-key': self._api_key, 'Accept': 'application/json'},
            method='GET',
        )
        for attempt in range(self.max_retries + 1):
            try:
                with self._opener.open(request, timeout=self.timeout) as response:
                    if not _is_official_origin(response.geturl()):
                        raise HithinkAPIError('redirect')
                    status = response.getcode()
                    if status != 200:
                        raise urllib.error.HTTPError(request.full_url, status, '', {}, None)
                    raw = response.read(_MAX_RESPONSE_BYTES + 1)
                if len(raw) > _MAX_RESPONSE_BYTES:
                    raise HithinkAPIError('response')
                try:
                    payload = json.loads(raw)
                except (UnicodeError, ValueError, TypeError, RecursionError):
                    raise HithinkAPIError('response') from None
                if not isinstance(payload, dict) or type(payload.get('code')) is not int:
                    raise HithinkAPIError('response')
                code = payload['code']
                if code != 0:
                    error = _api_error(code)
                    retryable = code == 4001 or 5000 <= code < 6000
                else:
                    if not isinstance(payload.get('data'), dict):
                        raise HithinkAPIError('response')
                    return payload['data']
            except urllib.error.HTTPError as error_response:
                status = error_response.code
                error = HithinkAPIError(
                    'authentication' if status in (401, 403) else
                    'rate_limit' if status == 429 else 'service'
                )
                retryable = status == 429 or 500 <= status < 600
                # Python 3.10 leaves the file-wrapper base uninitialized when
                # HTTPError has no body. Calling its close() then raises KeyError.
                if error_response.fp is not None:
                    try:
                        error_response.close()
                    except (OSError, http.client.HTTPException):
                        # Cleanup must not replace the safe, actionable API error.
                        pass
            except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException):
                error = HithinkAPIError('network')
                retryable = True
            if not retryable or attempt >= self.max_retries:
                raise error from None
            time.sleep(min(0.5 * (2 ** attempt), 2.0))
        raise HithinkAPIError('service')  # Defensive: the loop always returns or raises.

    def _resolve(self, symbol):
        ticker, requested_code = _symbol_parts(symbol)
        if ticker not in self._symbols:
            data = self._get('/api/meta/tickers/search', {
                'q': ticker, 'asset_type': 'fund-etf', 'limit': 50,
            })
            matches = set()
            for item in _items(data):
                if item.get('ticker') != ticker or item.get('asset_type') != 'fund-etf':
                    continue
                thscode = item.get('thscode')
                if not isinstance(thscode, str) or not re.fullmatch(
                    rf'{ticker}\.(?:SH|SZ|BJ)', thscode
                ):
                    raise HithinkAPIError('response')
                if item.get('exchange', thscode[-2:]) != thscode[-2:]:
                    raise HithinkAPIError('response')
                matches.add(thscode)
            if len(matches) != 1:
                raise HithinkAPIError('symbol')
            self._symbols[ticker] = matches.pop()
        thscode = self._symbols[ticker]
        if requested_code is not None and requested_code != thscode:
            raise HithinkAPIError('symbol')
        return ticker, thscode

    def fetch_etf_history(self, symbol, start_date, end_date):
        """Fetch complete inclusive date windows, keeping the original price basis."""
        start, end = _day(start_date), _day(end_date)
        if end < start:
            raise HithinkAPIError('date')
        _, thscode = self._resolve(symbol)
        records = []
        window_start = start
        while window_start <= end:
            # The final millisecond remains strictly below the five-year boundary.
            if end.year - window_start.year < 5:
                window_end = end
            else:
                year = window_start.year + 5
                anniversary = date(year, window_start.month, min(
                    window_start.day, calendar.monthrange(year, window_start.month)[1],
                ))
                window_end = min(end, anniversary - timedelta(days=1))
            start_ms = int(datetime.combine(window_start, daytime.min, _SHANGHAI).timestamp() * 1000)
            end_ms = int(datetime.combine(window_end, daytime(23, 59, 59), _SHANGHAI).timestamp() * 1000) + 999
            data = self._get('/api/fund/market/historical', {
                'thscode': thscode, 'interval': '1d', 'start': start_ms, 'end': end_ms,
            })
            if (
                data.get('thscode') != thscode
                or data.get('interval') != '1d'
                or data.get('adjust') is not None
            ):
                raise HithinkAPIError('response')
            for item in _items(data):
                required = {'date_ms', 'open_price', 'high_price', 'low_price',
                            'close_price', 'volume', 'turnover'}
                if not required.issubset(item):
                    raise HithinkAPIError('response')
                bar_date = _datetime_ms(item['date_ms']).date()
                values = [_number(item[f'{name}_price'], positive=True)
                          for name in ('open', 'high', 'low', 'close')]
                open_price, high, low, close = values
                if high < max(open_price, close, low) or low > min(open_price, close):
                    raise HithinkAPIError('response')
                values += [_number(item['volume'], nullable=True),
                           _number(item['turnover'], nullable=True)]
                if window_start <= bar_date <= window_end:
                    records.append((bar_date, *values))
            if window_end == end:
                break
            window_start = window_end + timedelta(days=1)
        if records:
            frame = pd.DataFrame.from_records(records, columns=['date', *_COLUMNS]).set_index('date')
            try:
                frame.index = pd.DatetimeIndex(frame.index, name='date')
            except (OverflowError, ValueError, TypeError):
                raise HithinkAPIError('response') from None
            frame = frame.loc[~frame.index.duplicated(keep='last')].sort_index()
        else:
            frame = pd.DataFrame(columns=_COLUMNS, index=pd.DatetimeIndex([], name='date'), dtype=float)
        frame.attrs.update(_ATTRS)
        return frame

    def fetch_etf_snapshot(self, symbol):
        """Return the actual quote timestamp; a missing upstream time stays None."""
        ticker, thscode = self._resolve(symbol)
        data = self._get('/api/fund/market/snapshot', {'thscode': thscode})
        items = _items(data)
        if not items:
            raise HithinkAPIError('unavailable')
        if len(items) != 1 or items[0].get('thscode') != thscode or items[0].get('ticker') != ticker:
            raise HithinkAPIError('response')
        return {
            'symbol': ticker,
            'price': _number(items[0].get('last_price'), positive=True),
            'quote_time': _datetime_ms(data['timestamp']) if data.get('timestamp') is not None else None,
            'data_source': '同花顺 Financial API',
            'price_basis': _ATTRS['price_basis'],
        }
