"""Validated ETF daily prices with incremental, failure-safe local caching."""

import logging
import os
import re
import tempfile
from collections import OrderedDict
from contextlib import contextmanager
from datetime import datetime
from time import monotonic

import akshare as ak
import numpy as np
import pandas as pd

from .data_sources import default_adjust, get_hithink_api_key, resolve_provider

logger = logging.getLogger(__name__)

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DATA_DIR = os.path.join(ROOT_DIR, 'data')
SEED_DATA_DIR = os.path.join(ROOT_DIR, 'data', 'seed')
_PROXY_ENV_KEYS = (
    'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY',
    'http_proxy', 'https_proxy', 'all_proxy',
)
# A successful request may end on a holiday or start before the fund was listed.
# Remember its checked range briefly instead of equating coverage with row dates.
_REQUEST_TTL_SECONDS = 300
_RECENT_REQUESTS = OrderedDict()
_COLUMN_MAP = {
    "日期": "date", "开盘": "open", "收盘": "close", "最高": "high",
    "最低": "low", "成交量": "volume", "成交额": "amount",
    "振幅": "amplitude", "涨跌幅": "pct_change", "涨跌额": "change_amount",
    "换手率": "turnover",
}
_PRICE_COLUMNS = ['open', 'close', 'high', 'low']


def ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def _write_cache(file_path, df):
    """Replace a complete CSV atomically; a failed write leaves the old file intact."""
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode='w', dir=os.path.dirname(file_path), suffix='.tmp',
            encoding='utf-8', delete=False,
        ) as handle:
            temp_path = handle.name
            df.to_csv(handle)
        os.replace(temp_path, file_path)
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)


def _seed_cache_if_available(file_path, symbol, adjust):
    if os.path.exists(file_path):
        return
    seed_path = os.path.join(SEED_DATA_DIR, f"{symbol}_{adjust}.csv")
    if os.path.exists(seed_path):
        try:
            seeded = _normalize(pd.read_csv(seed_path, index_col=0))
            if not seeded.empty:
                _write_cache(file_path, seeded)
                logger.info("使用 seed 数据初始化 %s 缓存", symbol)
        except (OSError, ValueError, TypeError) as error:
            logger.warning("无法初始化 seed 缓存: %s", error)


def _is_proxy_error(error):
    return 'proxy' in f"{type(error).__name__}: {error}".lower()


def _is_retryable_network_error(error):
    text = f"{type(error).__name__}: {error}".lower()
    return any(phrase in text for phrase in (
        'remote disconnected', 'connection aborted', 'connection reset',
        'max retries exceeded', 'timed out', 'timeout', 'ssl',
    ))


@contextmanager
def _without_proxy_env():
    """Restore the process proxy configuration even when the retry fails."""
    old_values = {key: os.environ.get(key) for key in _PROXY_ENV_KEYS}
    try:
        for key in _PROXY_ENV_KEYS:
            os.environ.pop(key, None)
        yield
    finally:
        for key, value in old_values.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _normalize(df, *, allow_missing_volume=False):
    """Return independent, chronological daily OHLC data with valid numeric prices."""
    if not isinstance(df, pd.DataFrame):
        raise ValueError('行情接口未返回表格数据')
    if df.empty:
        return pd.DataFrame(columns=_PRICE_COLUMNS, index=pd.DatetimeIndex([], name='date'))
    df = df.rename(columns=_COLUMN_MAP).copy()
    if 'date' in df.columns:
        dates = df.pop('date')
    elif isinstance(df.index, pd.DatetimeIndex) or df.index.name == 'date':
        dates = df.index
    else:
        raise ValueError('行情数据缺少日期列')
    df.index = pd.DatetimeIndex(pd.to_datetime(dates, errors='coerce', format='mixed'), name='date')
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)
    df.index = df.index.normalize()
    if not set(_PRICE_COLUMNS).issubset(df.columns):
        raise ValueError('行情数据缺少必要的开盘、收盘、最高或最低价格列')
    for column in set(_COLUMN_MAP.values()) & set(df.columns):
        df[column] = pd.to_numeric(df[column], errors='coerce').replace([np.inf, -np.inf], np.nan)
    valid = (
        df.index.notna()
        & df[_PRICE_COLUMNS].notna().all(axis=1)
        & df[_PRICE_COLUMNS].gt(0).all(axis=1)
        & df['high'].ge(df[['open', 'close', 'low']].max(axis=1))
        & df['low'].le(df[['open', 'close']].min(axis=1))
    )
    if 'volume' in df.columns:
        valid_volume = df['volume'].ge(0)
        if allow_missing_volume:
            valid_volume |= df['volume'].isna()
        valid &= valid_volume
    if not valid.all():
        logger.warning('过滤 %s 条日期或价格无效的行情', int((~valid).sum()))
        df.attrs['warning'] = '已过滤日期或价格无效的行情，请核对数据完整性。'
    df = df.loc[valid]
    if df.empty:
        raise ValueError('行情数据没有有效的日期和价格')
    return df.loc[~df.index.duplicated(keep='last')].sort_index()


def _fetch_from_api(symbol, start_date, end_date, adjust):
    logger.info("API 拉取 %s %s → %s (adjust=%s)", symbol, start_date, end_date, adjust)
    kwargs = dict(symbol=symbol, period='daily', start_date=start_date,
                  end_date=end_date, adjust=adjust)
    try:
        df = ak.fund_etf_hist_em(**kwargs)
    except Exception as error:
        if not (_is_proxy_error(error) or _is_retryable_network_error(error)):
            raise
        logger.warning('API 拉取遇到网络错误，临时绕过代理重试: %s', error)
        with _without_proxy_env():
            df = ak.fund_etf_hist_em(**kwargs)
    return _normalize(df).loc[pd.Timestamp(start_date):pd.Timestamp(end_date)]


def _cache_signature(file_path):
    try:
        stat = os.stat(file_path)
        return stat.st_mtime_ns, stat.st_size
    except OSError:
        return None


def _recently_checked(file_path, start, end):
    previous = _RECENT_REQUESTS.get(file_path)
    if previous is None:
        return False
    checked_start, checked_end, when, signature, _ = previous
    return (
        signature is not None and signature == _cache_signature(file_path)
        and monotonic() - when < _REQUEST_TTL_SECONDS
        and checked_start <= start and checked_end >= end
    )


def _remember_request(file_path, start, end, warning=None):
    _RECENT_REQUESTS[file_path] = (start, end, monotonic(), _cache_signature(file_path), warning)
    _RECENT_REQUESTS.move_to_end(file_path)
    while len(_RECENT_REQUESTS) > 256:
        _RECENT_REQUESTS.popitem(last=False)


def _history_repriced(cached, fresh, today):
    overlap = cached.index.intersection(fresh.index)
    overlap = overlap[overlap < today]
    return bool(len(overlap) and not np.isclose(
        cached.loc[overlap, _PRICE_COLUMNS].to_numpy(dtype=float),
        fresh.loc[overlap, _PRICE_COLUMNS].to_numpy(dtype=float),
        rtol=1e-8, atol=1e-8,
    ).all())


def _result(df, start, end, source, warning=None, *, provider='akshare', adjust='qfq'):
    result = df.loc[start:end].copy()
    result.attrs['data_source'] = source
    result.attrs['provider'] = provider
    if provider == 'hithink':
        result.attrs['price_basis'] = '接口原始口径（无复权选项）'
        result.attrs['volume_unit'] = '接口原始单位'
    else:
        result.attrs['price_basis'] = {'qfq': '前复权', 'hfq': '后复权', '': '不复权'}[adjust]
        result.attrs['volume_unit'] = '手'
    if warning:
        result.attrs['warning'] = warning
    return result


def fetch_etf_data(symbol='510880', start_date='20200101', end_date=None,
                   adjust=None, force_update=False, *, provider=None, api_key=None):
    """Fetch daily ETF prices, preserving valid history when refreshes fail.

    Results are always clipped to the requested dates. ``attrs['data_source']``
    identifies API/cache data; ``attrs['provider']`` and ``attrs['price_basis']``
    identify the source and its price convention. ``attrs['warning']`` describes
    degraded results. Sources use separate caches and are never combined.
    Successful holiday/listing-boundary checks expire after five minutes.
    """
    provider = resolve_provider(provider)
    adjust = default_adjust(provider) if adjust is None else adjust
    symbol = str(symbol).strip()
    if not re.fullmatch(r'\d{6}', symbol):
        raise ValueError('ETF 代码必须是六位数字')
    if adjust not in ('', 'qfq', 'hfq'):
        raise ValueError('复权方式必须为 qfq、hfq 或空字符串')
    if provider == 'hithink' and adjust:
        raise ValueError('同花顺 Financial API 仅提供接口原始口径，不支持指定前复权或后复权')
    req_start = pd.Timestamp(start_date)
    req_end = pd.Timestamp(datetime.now().strftime('%Y%m%d') if end_date is None else end_date)
    if (pd.isna(req_start) or pd.isna(req_end) or req_start.tz is not None
            or req_end.tz is not None or req_start > req_end):
        raise ValueError('请提供有效且起始日期不晚于结束日期的日期范围')
    req_start, req_end = req_start.normalize(), req_end.normalize()
    today = pd.Timestamp(datetime.now().date())
    cache_name = f'{symbol}_{adjust}.csv' if provider == 'akshare' else f'{symbol}_hithink_original.csv'
    file_path = os.path.join(DATA_DIR, cache_name)
    try:
        ensure_data_dir()
        if provider == 'akshare':
            _seed_cache_if_available(file_path, symbol, adjust)
    except OSError as error:
        logger.warning('本地缓存目录不可用，将继续获取行情: %s', error)

    cached = pd.DataFrame(index=pd.DatetimeIndex([], name='date'))
    if os.path.exists(file_path):
        try:
            cached = _normalize(pd.read_csv(file_path, index_col=0),
                                allow_missing_volume=provider == 'hithink')
        except (OSError, ValueError, TypeError) as error:
            logger.warning('忽略不可用行情缓存 %s: %s', file_path, error)

    def result(df, source, warning=None):
        return _result(df, req_start, req_end, source, warning,
                       provider=provider, adjust=adjust)

    hithink_key = get_hithink_api_key(api_key) if provider == 'hithink' else None
    if provider == 'hithink' and not hithink_key:
        warning = ('尚未配置同花顺 Financial API Key，当前仅显示同花顺历史缓存；请检查数据日期。'
                   if not cached.empty else '尚未配置同花顺 Financial API Key，无法获取该来源的行情。')
        logger.warning(warning)
        return result(cached, 'cache', warning)

    cache_start, cache_end = cached.index.min(), cached.index.max()
    if not force_update and not cached.empty:
        historical_hit = cache_start <= req_start and cache_end >= req_end and req_end < today
        if historical_hit:
            return result(cached, 'cache')
        if _recently_checked(file_path, req_start, req_end):
            return result(cached, 'cache', _RECENT_REQUESTS[file_path][4])

    def fetch(start, end):
        if provider == 'akshare':
            return _fetch_from_api(symbol, start, end, adjust)
        from .hithink_api import HithinkClient
        fetched = HithinkClient(hithink_key).fetch_etf_history(symbol, start, end)
        return _normalize(fetched, allow_missing_volume=True).loc[pd.Timestamp(start):pd.Timestamp(end)]

    # Preserve both ends when expanding history or forcing a smaller date range.
    full_start = min(req_start, cache_start) if not cached.empty else req_start
    full_end = max(req_end, cache_end) if not cached.empty else req_end
    incremental = not force_update and not cached.empty and cache_start <= req_start
    # Include the last cached day to refresh today's unfinished candle and detect
    # historical price changes caused by a new adjustment factor.
    fetch_start = cache_end if incremental else full_start
    try:
        fresh = fetch(fetch_start.strftime('%Y%m%d'), full_end.strftime('%Y%m%d'))
        if (incremental and adjust and not fresh.empty
                and _history_repriced(cached, fresh, today)):
            fresh = fetch(full_start.strftime('%Y%m%d'), full_end.strftime('%Y%m%d'))
        if fresh.empty:
            warning = '行情接口未返回新数据，当前显示已有缓存。'
            if not cached.empty:
                _remember_request(file_path, req_start, req_end, warning)
            return result(cached, 'cache', warning)
        if (adjust and not cached.empty and _history_repriced(cached, fresh, today)
                and not cached.index.difference(fresh.index).empty):
            raise ValueError('复权价格发生变化，但接口未返回完整历史，无法安全合并')
        merged = pd.concat([cached, fresh]) if not cached.empty else fresh
        merged = merged.loc[~merged.index.duplicated(keep='last')].sort_index()
        warning = fresh.attrs.get('warning') or cached.attrs.get('warning')
        try:
            _write_cache(file_path, merged)
        except OSError as error:
            logger.warning('行情已更新，但缓存保存失败: %s', error)
            warning = '行情已更新，但本地缓存保存失败。'
        else:
            _remember_request(file_path, full_start, full_end, warning)
        return result(merged, 'api', warning)
    except Exception as error:
        warning = '行情更新失败，当前显示已有缓存；请检查数据日期。'
        if provider == 'hithink':
            # Unexpected transport exceptions can contain authentication headers.
            # Only the client adapter's explicitly sanitized error is user-facing.
            from .hithink_api import HithinkAPIError
            if isinstance(error, HithinkAPIError):
                warning = f'{error} 当前显示同花顺已有缓存，请检查数据日期。'
            logger.warning('同花顺行情更新失败，使用同来源缓存（%s）', type(error).__name__)
        else:
            logger.warning('行情更新失败，使用已有缓存: %s', error)
        return result(cached, 'cache', warning)


if __name__ == '__main__':
    df = fetch_etf_data()
    print(df.head())
    print(df.tail())
