"""Cached market context shared by the independent workspace pages."""
from hashlib import sha256
import pandas as pd
import streamlit as st
from src import data_loader
from src.data_sources import PRICE_BASIS_LABELS
from src.hithink_api import HithinkClient, HithinkAPIError
from src.monitoring import ETF_PROFILES, calculate_monitor_frame, summarize_data_status, summarize_monitor_status

@st.cache_data(show_spinner=False, ttl=300, max_entries=32)
def load_data(symbol, start, end, provider, credential_id, _api_key=None, _force=False):
    """Partition the cache by source and credential fingerprint, never the raw key."""
    start_str = start.strftime("%Y%m%d") if hasattr(start, "strftime") else start
    end_str = end.strftime("%Y%m%d") if hasattr(end, "strftime") else end
    return data_loader.fetch_etf_data(symbol, start_date=start_str, end_date=end_str,
                          provider=provider, api_key=_api_key, force_update=_force)


@st.cache_data(show_spinner=False, ttl=30, max_entries=16)
def load_quotes(symbols, credential_id, _api_key):
    try:
        client = HithinkClient(_api_key)
    except HithinkAPIError as exc:
        return {}, [str(exc)]
    quotes, warnings = {}, []
    for symbol in symbols:
        try:
            quotes[symbol] = client.fetch_etf_snapshot(symbol)
        except HithinkAPIError as exc:
            warnings.append(f"{symbol} 快照暂不可用：{exc}")
    return quotes, warnings


cached_monitor_frame = st.cache_data(show_spinner=False, max_entries=32)(calculate_monitor_frame)


def build_context(cfg):
    provider = cfg["provider"]
    credential_id = sha256(cfg["api_key"].encode()).hexdigest() if cfg["api_key"] else ""
    warnings = []
    symbols = list(ETF_PROFILES)
    if cfg["force_update"]:
        load_data.clear()
        load_quotes.clear()

    raw_data = {}
    for symbol in symbols:
        raw_data[symbol] = load_data(symbol, cfg["start_date"], cfg["end_date"], provider,
                                     credential_id, _api_key=cfg["api_key"], _force=cfg["force_update"])
        if raw_data[symbol].attrs.get("warning"):
            warnings.append(f"{symbol}：{raw_data[symbol].attrs['warning']}")
        if raw_data[symbol].empty:
            warnings.append(f"{symbol} 当前区间暂无可用行情，可调整日期或刷新后重试。")

    quotes = {}
    if (provider == "hithink" and cfg["api_key"] and any(not df.empty for df in raw_data.values())
            and cfg["end_date"] == pd.Timestamp.now(tz="Asia/Shanghai").date()):
        quotes, quote_warnings = load_quotes(tuple(symbols), credential_id, _api_key=cfg["api_key"])
        for warning in quote_warnings:
            warnings.append(warning)

    frames = {}
    statuses = {}
    data_status = {}

    for idx, symbol in enumerate(symbols, start=1):
        profile = ETF_PROFILES[symbol]
        window = cfg[f"w{idx}"]
        num_std = cfg[f"std{idx}"]
        first_batch_pct = cfg[f"batch{idx}"]
        frame = cached_monitor_frame(
            raw_data[symbol],
            window=window,
            num_std=num_std,
            first_batch_pct=first_batch_pct,
            scale_threshold=cfg["scale_threshold"],
            pyramid_levels=cfg["pyramid_levels"],
            pyramid_sizes=cfg["pyramid_sizes"],
        ) if not raw_data[symbol].empty else pd.DataFrame()
        # Streamlit hashes the table values, so annotate the chosen source after
        # retrieving a calculation that may also be valid for identical price data.
        frame.attrs.update(provider=provider, price_basis=PRICE_BASIS_LABELS[provider])
        frames[symbol] = frame
        data_status[symbol] = summarize_data_status(raw_data[symbol], symbol)
        statuses[symbol] = summarize_monitor_status(
            frame,
            symbol=symbol,
            name=profile.name,
            role=profile.role,
            window=window,
            num_std=num_std,
            first_batch_pct=first_batch_pct,
        )


    ctx = {
        "profiles": ETF_PROFILES,
        "provider": provider,
        "price_basis": PRICE_BASIS_LABELS[provider],
        "quotes": quotes,
        "raw_data": raw_data,
        "frames": frames,
        "statuses": statuses,
        "data_status": data_status,
        "start_date": cfg["start_date"],
        "end_date": cfg["end_date"],
        "w1": cfg["w1"],
        "std1": cfg["std1"],
        "batch1": cfg["batch1"],
        "w2": cfg["w2"],
        "std2": cfg["std2"],
        "batch2": cfg["batch2"],
        "scale_threshold": cfg["scale_threshold"],
        "pyramid_levels": cfg["pyramid_levels"],
        "pyramid_sizes": cfg["pyramid_sizes"],
    }

    return ctx, warnings
