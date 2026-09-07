"""Source selection and credentials shared by the app and command-line jobs."""
from __future__ import annotations

import os

PROVIDER_LABELS = {"akshare": "AkShare", "hithink": "同花顺 Financial API"}
PRICE_BASIS_LABELS = {"akshare": "前复权", "hithink": "接口原始口径（无复权选项）"}


def resolve_provider(provider: str | None = None) -> str:
    value = (provider if provider is not None else os.getenv("ETF_DATA_PROVIDER", "akshare")).strip().lower()
    value = value or "akshare"
    if value not in PROVIDER_LABELS:
        raise ValueError("行情来源必须为 akshare 或 hithink。")
    return value


def get_hithink_api_key(api_key: str | None = None) -> str:
    """Read a supplied or environment key without writing it to disk."""
    return (api_key if api_key is not None else os.getenv("HITHINK_FINANCE_API_KEY", "")).strip()


def default_adjust(provider: str) -> str:
    """The ETF Financial API contract has no adjustable-price option."""
    return "qfq" if resolve_provider(provider) == "akshare" else ""
