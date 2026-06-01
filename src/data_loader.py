import akshare as ak
import pandas as pd
import os
import logging
from contextlib import contextmanager
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

DATA_DIR = 'data'
_PROXY_ENV_KEYS = (
    'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY',
    'http_proxy', 'https_proxy', 'all_proxy',
)

# AkShare 列名映射
_COLUMN_MAP = {
    "日期": "date",
    "开盘": "open",
    "收盘": "close",
    "最高": "high",
    "最低": "low",
    "成交量": "volume",
    "成交额": "amount",
    "振幅": "amplitude",
    "涨跌幅": "pct_change",
    "涨跌额": "change_amount",
    "换手率": "turnover"
}




def ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def _is_proxy_error(error):
    """判断 AkShare 底层请求是否卡在代理上。"""
    text = f"{type(error).__name__}: {error}".lower()
    return "proxy" in text


@contextmanager
def _without_proxy_env():
    """临时绕过本机代理，避免代理失效时误回退到旧缓存。"""
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


def _normalize(df):
    """统一列名 & 索引格式。"""
    df.rename(columns=_COLUMN_MAP, inplace=True)
    if 'date' in df.columns:
        df['date'] = pd.to_datetime(df['date'])
        df.set_index('date', inplace=True)
    df.sort_index(inplace=True)
    return df


def _fetch_from_api(symbol, start_date, end_date, adjust):
    """调用 AkShare 获取 ETF 日线数据。"""
    logger.info(f"API 拉取 {symbol}  {start_date} → {end_date}  (adjust={adjust})")
    try:
        df = ak.fund_etf_hist_em(
            symbol=symbol, period="daily",
            start_date=start_date, end_date=end_date, adjust=adjust
        )
    except Exception as e:
        if not _is_proxy_error(e):
            raise
        logger.warning(f"API 拉取遇到代理错误，临时绕过代理重试: {e}")
        with _without_proxy_env():
            df = ak.fund_etf_hist_em(
                symbol=symbol, period="daily",
                start_date=start_date, end_date=end_date, adjust=adjust
            )
    return _normalize(df)


def fetch_etf_data(symbol="510880", start_date="20200101", end_date=None,
                   adjust="qfq", force_update=False):
    """
    获取 ETF 历史行情数据（支持增量更新）。

    工作流程:
      1. 本地有缓存 → 判断能否增量更新
         a. 缓存覆盖区间完全满足请求 → 直接裁剪返回
         b. 请求 start_date 在缓存内 → 仅拉取 (last_cached_date+1 ~ end_date) 的增量
         c. 请求 start_date 早于缓存 → 全量刷新
      2. 本地无缓存 / force_update → 全量拉取并保存
    """
    ensure_data_dir()
    file_path = os.path.join(DATA_DIR, f"{symbol}_{adjust}.csv")

    if end_date is None:
        end_date = datetime.now().strftime("%Y%m%d")

    req_start = pd.Timestamp(start_date)
    req_end = pd.Timestamp(end_date)

    # ---------- 尝试从缓存加载 ----------
    if os.path.exists(file_path) and not force_update:
        cached = pd.read_csv(file_path, index_col=0, parse_dates=True)
        cached.sort_index(inplace=True)

        cache_start = cached.index.min()
        cache_end = cached.index.max()

        # 情况 A: 缓存已完全覆盖请求范围
        if cache_start <= req_start and cache_end >= req_end:
            logger.info(f"缓存命中 {symbol}  ({cache_start.date()} ~ {cache_end.date()})")
            return cached.loc[req_start:req_end]

        # 情况 B: 请求起始在缓存内，仅需拉取增量
        if cache_start <= req_start and cache_end < req_end:
            delta_start = (cache_end + timedelta(days=1)).strftime("%Y%m%d")
            try:
                delta = _fetch_from_api(symbol, delta_start, end_date, adjust)
                if not delta.empty:
                    merged = pd.concat([cached, delta])
                    merged = merged[~merged.index.duplicated(keep='last')]
                    merged.sort_index(inplace=True)
                    merged.to_csv(file_path)
                    logger.info(f"增量更新 {symbol}  +{len(delta)} 条 → 共 {len(merged)} 条")
                    return merged.loc[req_start:req_end]
                else:
                    logger.info(f"无新数据 {symbol}（API 返回空），使用缓存")
                    return cached.loc[req_start:req_end]
            except Exception as e:
                logger.warning(f"增量更新失败: {e}，使用缓存")
                return cached.loc[req_start:req_end]

        # 情况 C: 请求 start 早于缓存 → 需要全量刷新
        logger.info(f"缓存不覆盖请求起始 ({req_start.date()} < {cache_start.date()})，全量刷新")

    # ---------- 全量拉取 ----------
    try:
        df = _fetch_from_api(symbol, start_date, end_date, adjust)
        df.to_csv(file_path)
        logger.info(f"全量保存 {symbol}  {len(df)} 条 → {file_path}")
        return df
    except Exception as e:
        logger.error(f"数据获取失败: {e}")
        if os.path.exists(file_path):
            logger.warning(f"由于网络问题，降级使用本地缓存: {file_path}")
            cached = pd.read_csv(file_path, index_col=0, parse_dates=True)
            cached.sort_index(inplace=True)
            # Try to return as much as requested, even if partial
            return cached.loc[req_start:req_end]
        return pd.DataFrame()




if __name__ == "__main__":
    df = fetch_etf_data()
    print(df.head())
    print(df.tail())
