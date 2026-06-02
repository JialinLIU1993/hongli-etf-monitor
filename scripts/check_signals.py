#!/usr/bin/env python3
"""Check ETF Bollinger signals and notify via PushPlus."""
from __future__ import annotations

import argparse
import html
import json
import logging
import os
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib import error, request
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.data_loader import fetch_etf_data  # noqa: E402
from src.monitoring import (  # noqa: E402
    ETF_PROFILES,
    calculate_monitor_frame,
    summarize_monitor_status,
)


LOGGER = logging.getLogger("check_signals")
PUSHPLUS_URL = "https://www.pushplus.plus/send"
DEFAULT_STATE_FILE = ROOT / ".cache" / "check-signals" / "pushplus_sent.json"
PROXY_ENV_KEYS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
)


@dataclass(frozen=True)
class SignalAlert:
    symbol: str
    name: str
    role: str
    date: str
    action: str
    change: str
    signal: float
    target_position: float
    close: float
    ma: float
    lower_band: float
    upper_band: float
    hint: str
    window: int
    num_std: float

    @property
    def key(self) -> str:
        return (
            f"{self.symbol}:{self.date}:{self.action}:"
            f"{self.signal:.6f}:{self.target_position:.6f}"
        )


@dataclass(frozen=True)
class RealtimeQuote:
    symbol: str
    price: float
    quote_time: datetime | None


@dataclass(frozen=True)
class BandStatus:
    symbol: str
    name: str
    role: str
    band_date: str
    price: float
    price_source: str
    quote_time: datetime | None
    ma: float
    lower_band: float
    upper_band: float
    band_position: float
    position_label: str
    window: int
    num_std: float


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return int(value)


def parse_symbols(raw: str | None) -> list[str]:
    if not raw:
        return list(ETF_PROFILES.keys())
    symbols = [item.strip() for item in raw.split(",") if item.strip()]
    unknown = sorted(set(symbols) - set(ETF_PROFILES))
    if unknown:
        raise ValueError(f"Unknown ETF symbol(s): {', '.join(unknown)}")
    return symbols


@contextmanager
def without_proxy_env():
    old_values = {key: os.environ.get(key) for key in PROXY_ENV_KEYS}
    try:
        for key in PROXY_ENV_KEYS:
            os.environ.pop(key, None)
        yield
    finally:
        for key, value in old_values.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"sent": {}}

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        LOGGER.warning("State file is unreadable, starting fresh: %s", exc)
        return {"sent": {}}

    if not isinstance(data, dict):
        return {"sent": {}}
    if not isinstance(data.get("sent"), dict):
        data["sent"] = {}
    return data


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def prune_state(state: dict[str, Any], keep: int = 300) -> None:
    sent = state.setdefault("sent", {})
    if len(sent) <= keep:
        return

    sorted_items = sorted(
        sent.items(),
        key=lambda item: item[1].get("sent_at", "") if isinstance(item[1], dict) else "",
    )
    state["sent"] = dict(sorted_items[-keep:])


def to_date_string(value: Any) -> str:
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d")
    return str(value)


def parse_quote_float(value: Any) -> float | None:
    if value in (None, "", "-"):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def secid_for_symbol(symbol: str) -> str:
    market = "1" if symbol.startswith(("5", "6", "9")) else "0"
    return f"{market}.{symbol}"


def fetch_realtime_quotes_once(
    symbols: list[str],
    *,
    timezone: ZoneInfo,
    bypass_proxy: bool = False,
) -> dict[str, RealtimeQuote]:
    params = urlencode(
        {
            "fltt": "2",
            "invt": "2",
            "fields": "f12,f14,f2,f3,f4,f15,f16,f17,f18,f13,f124",
            "secids": ",".join(secid_for_symbol(symbol) for symbol in symbols),
        }
    )
    url = f"https://push2.eastmoney.com/api/qt/ulist.np/get?{params}"
    req = request.Request(url, headers={"User-Agent": "Mozilla/5.0"})

    if bypass_proxy:
        with without_proxy_env():
            raw = request.urlopen(req, timeout=env_int("QUOTE_TIMEOUT", 15)).read().decode("utf-8")
    else:
        raw = request.urlopen(req, timeout=env_int("QUOTE_TIMEOUT", 15)).read().decode("utf-8")

    data = json.loads(raw)
    rows = data.get("data", {}).get("diff") or []
    quotes: dict[str, RealtimeQuote] = {}

    for row in rows:
        symbol = str(row.get("f12", "")).strip()
        if symbol not in symbols:
            continue

        price = parse_quote_float(row.get("f2"))
        if price is None:
            continue

        quote_time = None
        timestamp = parse_quote_float(row.get("f124"))
        if timestamp is not None:
            quote_time = datetime.fromtimestamp(timestamp, timezone)

        quotes[symbol] = RealtimeQuote(symbol=symbol, price=price, quote_time=quote_time)

    return quotes


def fetch_realtime_quotes(symbols: list[str], *, timezone: ZoneInfo) -> dict[str, RealtimeQuote]:
    try:
        return fetch_realtime_quotes_once(symbols, timezone=timezone)
    except Exception as exc:
        LOGGER.warning("Realtime quote fetch failed, retrying without proxy: %s", exc)

    try:
        return fetch_realtime_quotes_once(symbols, timezone=timezone, bypass_proxy=True)
    except Exception as exc:
        LOGGER.warning("Realtime quote unavailable, will use latest daily close: %s", exc)
        return {}


def describe_band_position(value: float) -> str:
    if value < 0:
        return "下轨下方"
    if value > 1:
        return "上轨上方"
    if value < 0.25:
        return "下轨附近"
    if value < 0.5:
        return "中轨下方"
    if value < 0.75:
        return "中轨上方"
    return "上轨附近"


def build_alert(
    status: dict[str, Any],
    *,
    today: datetime,
    max_signal_age_days: int,
) -> SignalAlert | None:
    if not status.get("is_ready"):
        LOGGER.warning(
            "%s %s is not ready: %s",
            status.get("symbol"),
            status.get("name"),
            status.get("message"),
        )
        return None

    signal = float(status.get("signal") or 0.0)
    if abs(signal) < 1e-9:
        return None

    signal_date = pd.Timestamp(status["date"]).date()
    age_days = (today.date() - signal_date).days
    if max_signal_age_days >= 0 and age_days > max_signal_age_days:
        LOGGER.info(
            "%s %s signal is stale (%s, %s days old), skip notification.",
            status["symbol"],
            status["name"],
            signal_date.isoformat(),
            age_days,
        )
        return None

    action = "买入/加仓" if signal > 0 else "卖出/减仓"
    return SignalAlert(
        symbol=status["symbol"],
        name=status["name"],
        role=status["role"],
        date=signal_date.isoformat(),
        action=action,
        change=status["signal_change"],
        signal=signal,
        target_position=float(status["target_position"]),
        close=float(status["close"]),
        ma=float(status["ma"]),
        lower_band=float(status["lower_band"]),
        upper_band=float(status["upper_band"]),
        hint=str(status["hint"]),
        window=int(status["window"]),
        num_std=float(status["num_std"]),
    )


def summarize_symbol(symbol: str, *, start_date: str, force_update: bool) -> dict[str, Any]:
    profile = ETF_PROFILES[symbol]
    df = fetch_etf_data(
        symbol=symbol,
        start_date=start_date,
        adjust="qfq",
        force_update=force_update,
    )
    if df.empty:
        return {
            "symbol": symbol,
            "name": profile.name,
            "role": profile.role,
            "is_ready": False,
            "message": "行情数据为空",
        }

    frame = calculate_monitor_frame(
        df,
        window=profile.window,
        num_std=profile.num_std,
        first_batch_pct=profile.first_batch_pct,
    )
    return summarize_monitor_status(
        frame,
        symbol=symbol,
        name=profile.name,
        role=profile.role,
        window=profile.window,
        num_std=profile.num_std,
        first_batch_pct=profile.first_batch_pct,
    )


def build_band_status(status: dict[str, Any], quote: RealtimeQuote | None) -> BandStatus | None:
    if not status.get("is_ready"):
        LOGGER.warning(
            "%s %s is not ready: %s",
            status.get("symbol"),
            status.get("name"),
            status.get("message"),
        )
        return None

    price = quote.price if quote else float(status["close"])
    price_source = "实时价" if quote else "最新日线收盘价"
    lower = float(status["lower_band"])
    upper = float(status["upper_band"])
    band_range = upper - lower
    band_position = ((price - lower) / band_range) if band_range else 0.5

    return BandStatus(
        symbol=status["symbol"],
        name=status["name"],
        role=status["role"],
        band_date=to_date_string(status["date"]),
        price=price,
        price_source=price_source,
        quote_time=quote.quote_time if quote else None,
        ma=float(status["ma"]),
        lower_band=lower,
        upper_band=upper,
        band_position=band_position,
        position_label=describe_band_position(band_position),
        window=int(status["window"]),
        num_std=float(status["num_std"]),
    )


def render_content(alerts: list[SignalAlert], *, generated_at: datetime) -> str:
    blocks = [
        "<h2>红利双雄 ETF 信号提醒</h2>",
        f"<p>检查时间: {html.escape(generated_at.strftime('%Y-%m-%d %H:%M:%S %Z'))}</p>",
    ]

    for alert in alerts:
        blocks.append(
            "\n".join(
                [
                    f"<h3>{html.escape(alert.symbol)} {html.escape(alert.name)} "
                    f"({html.escape(alert.role)})</h3>",
                    "<ul>",
                    f"<li>信号: {html.escape(alert.action)} {html.escape(alert.change)}</li>",
                    f"<li>数据日期: {html.escape(alert.date)}</li>",
                    f"<li>最新价: {alert.close:.3f}</li>",
                    f"<li>目标仓位: {alert.target_position:.0%}</li>",
                    (
                        f"<li>布林带: 下轨 {alert.lower_band:.3f} / "
                        f"中轨 {alert.ma:.3f} / 上轨 {alert.upper_band:.3f}</li>"
                    ),
                    f"<li>参数: Window={alert.window}, Std={alert.num_std:g}</li>",
                    f"<li>提示: {html.escape(alert.hint)}</li>",
                    "</ul>",
                ]
            )
        )

    blocks.append("<p>策略信号仅供参考，投资需谨慎。</p>")
    return "\n".join(blocks)


def render_band_status_content(statuses: list[BandStatus], *, generated_at: datetime) -> str:
    blocks = [
        "<h2>红利双雄 ETF 布林带状态</h2>",
        f"<p>检查时间: {html.escape(generated_at.strftime('%Y-%m-%d %H:%M:%S %Z'))}</p>",
    ]

    for status in statuses:
        quote_suffix = ""
        if status.quote_time is not None:
            quote_suffix = f"，报价时间 {html.escape(status.quote_time.strftime('%Y-%m-%d %H:%M:%S %Z'))}"

        blocks.append(
            "\n".join(
                [
                    f"<h3>{html.escape(status.symbol)} {html.escape(status.name)} "
                    f"({html.escape(status.role)})</h3>",
                    "<ul>",
                    (
                        f"<li>价格: {status.price:.3f} "
                        f"({html.escape(status.price_source)}{quote_suffix})</li>"
                    ),
                    (
                        f"<li>布林带: 下轨 {status.lower_band:.3f} / "
                        f"中轨 {status.ma:.3f} / 上轨 {status.upper_band:.3f}</li>"
                    ),
                    (
                        f"<li>区间位置: {status.band_position:.0%} "
                        f"({html.escape(status.position_label)}，0%=下轨，50%=中轨，100%=上轨)</li>"
                    ),
                    f"<li>布林带数据日期: {html.escape(status.band_date)}</li>",
                    f"<li>参数: Window={status.window}, Std={status.num_std:g}</li>",
                    "</ul>",
                ]
            )
        )

    blocks.append("<p>策略信号仅供参考，投资需谨慎。</p>")
    return "\n".join(blocks)


def send_pushplus(title: str, content: str) -> dict[str, Any]:
    token = os.getenv("PUSHPLUS_TOKEN", "").strip()
    if not token:
        raise RuntimeError("PUSHPLUS_TOKEN is required when a signal needs notification.")

    payload: dict[str, Any] = {
        "token": token,
        "title": title,
        "content": content,
        "template": os.getenv("PUSHPLUS_TEMPLATE", "html").strip() or "html",
    }

    topic = os.getenv("PUSHPLUS_TOPIC", "").strip()
    to = os.getenv("PUSHPLUS_TO", "").strip()
    if topic and to:
        LOGGER.warning("Both PUSHPLUS_TOPIC and PUSHPLUS_TO are set; using PUSHPLUS_TOPIC.")
    if topic:
        payload["topic"] = topic
    elif to:
        payload["to"] = to

    channel = os.getenv("PUSHPLUS_CHANNEL", "").strip()
    if channel:
        payload["channel"] = channel

    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        PUSHPLUS_URL,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    timeout = env_int("PUSHPLUS_TIMEOUT", 15)

    try:
        with request.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"PushPlus HTTP {exc.code}: {details}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"PushPlus request failed: {exc}") from exc

    try:
        result = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"PushPlus returned non-JSON response: {raw}") from exc

    if result.get("code") != 200:
        raise RuntimeError(f"PushPlus rejected notification: {result}")

    return result


def run_status_mode(args: argparse.Namespace, *, now: datetime, symbols: list[str]) -> int:
    quotes = fetch_realtime_quotes(symbols, timezone=now.tzinfo or ZoneInfo("Asia/Shanghai"))
    if args.require_today_quote:
        missing_today_quotes = [
            symbol
            for symbol in symbols
            if quotes.get(symbol) is None
            or quotes[symbol].quote_time is None
            or quotes[symbol].quote_time.date() != now.date()
        ]
        if missing_today_quotes:
            LOGGER.info(
                "Realtime quotes are missing or not from today for %s, skip fixed status push.",
                ", ".join(missing_today_quotes),
            )
            return 0

    quote_dates = {
        quote.quote_time.date()
        for quote in quotes.values()
        if quote.quote_time is not None
    }
    if quote_dates and now.date() not in quote_dates:
        LOGGER.info(
            "Realtime quotes are not from today (%s), skip fixed status push.",
            ", ".join(sorted(date.isoformat() for date in quote_dates)),
        )
        return 0

    statuses: list[BandStatus] = []
    for symbol in symbols:
        status = summarize_symbol(symbol, start_date=args.start_date, force_update=args.force_update)
        band_status = build_band_status(status, quotes.get(symbol))
        if band_status is None:
            continue
        statuses.append(band_status)
        LOGGER.info(
            "%s %s | price=%.3f source=%s band_pos=%.0f%% lower=%.3f ma=%.3f upper=%.3f",
            band_status.symbol,
            band_status.name,
            band_status.price,
            band_status.price_source,
            band_status.band_position * 100,
            band_status.lower_band,
            band_status.ma,
            band_status.upper_band,
        )

    if not statuses:
        LOGGER.error("No ready ETF band statuses to push.")
        return 1

    title = "红利双雄 ETF 布林带状态"
    content = render_band_status_content(statuses, generated_at=now)
    if args.dry_run:
        LOGGER.info("Dry run enabled. Notification title: %s", title)
        print(content)
        return 0

    try:
        result = send_pushplus(title, content)
    except RuntimeError as exc:
        LOGGER.error("%s", exc)
        return 2

    LOGGER.info("PushPlus band status sent successfully: %s", result.get("data"))
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=("signals", "status"),
        default=os.getenv("CHECK_SIGNALS_MODE", "signals"),
        help="signals pushes only new trading signals; status always pushes current band status.",
    )
    parser.add_argument(
        "--state-file",
        type=Path,
        default=Path(os.getenv("SIGNAL_STATE_FILE", DEFAULT_STATE_FILE)),
        help="Path used to remember already-sent signal keys.",
    )
    parser.add_argument(
        "--start-date",
        default=os.getenv("SIGNAL_START_DATE", "20200102"),
        help="History start date passed to AkShare, format YYYYMMDD.",
    )
    parser.add_argument(
        "--symbols",
        default=os.getenv("SIGNAL_SYMBOLS", ",".join(ETF_PROFILES.keys())),
        help="Comma-separated ETF symbols to check.",
    )
    parser.add_argument(
        "--max-signal-age-days",
        type=int,
        default=env_int("SIGNAL_MAX_SIGNAL_AGE_DAYS", 2),
        help="Skip notifications when latest signal data is older than this many days. Use -1 to disable.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=env_bool("SIGNAL_DRY_RUN", False),
        help="Print notification content without calling PushPlus or marking state.",
    )
    parser.add_argument(
        "--force-update",
        action=argparse.BooleanOptionalAction,
        default=env_bool("SIGNAL_FORCE_UPDATE", True),
        help="Force AkShare refresh instead of using local cache.",
    )
    parser.add_argument(
        "--skip-weekends",
        action=argparse.BooleanOptionalAction,
        default=env_bool("SIGNAL_SKIP_WEEKENDS", True),
        help="Skip checks on Saturday and Sunday in the configured timezone.",
    )
    parser.add_argument(
        "--require-today-quote",
        action=argparse.BooleanOptionalAction,
        default=env_bool("STATUS_REQUIRE_TODAY_QUOTE", True),
        help="In status mode, skip unless all symbols have realtime quotes from today.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    args = parse_args(argv)

    os.chdir(ROOT)
    timezone = ZoneInfo(os.getenv("SIGNAL_TIMEZONE", "Asia/Shanghai"))
    now = datetime.now(timezone)

    if args.skip_weekends and now.weekday() >= 5:
        LOGGER.info("Today is weekend in %s, skip signal check.", timezone.key)
        save_state(args.state_file, load_state(args.state_file))
        return 0

    state = load_state(args.state_file)
    sent = state.setdefault("sent", {})
    symbols = parse_symbols(args.symbols)

    if args.mode == "status":
        return run_status_mode(args, now=now, symbols=symbols)

    alerts: list[SignalAlert] = []

    for symbol in symbols:
        status = summarize_symbol(symbol, start_date=args.start_date, force_update=args.force_update)
        if status.get("is_ready"):
            LOGGER.info(
                "%s %s | date=%s close=%.3f signal=%s target=%.0f%% state=%s",
                symbol,
                status["name"],
                to_date_string(status["date"]),
                status["close"],
                status["signal_change"],
                status["target_position"] * 100,
                status["state_label"],
            )

        alert = build_alert(status, today=now, max_signal_age_days=args.max_signal_age_days)
        if alert is None:
            continue

        if alert.key in sent:
            LOGGER.info("%s %s signal already notified, skip.", alert.symbol, alert.date)
            continue

        alerts.append(alert)

    if not alerts:
        LOGGER.info("No new buy/sell signals.")
        prune_state(state)
        save_state(args.state_file, state)
        return 0

    title = f"红利双雄 ETF 信号提醒 ({len(alerts)} 条)"
    content = render_content(alerts, generated_at=now)

    if args.dry_run:
        LOGGER.info("Dry run enabled. Notification title: %s", title)
        print(content)
        return 0

    try:
        result = send_pushplus(title, content)
    except RuntimeError as exc:
        LOGGER.error("%s", exc)
        save_state(args.state_file, state)
        return 2
    sent_at = now.isoformat()
    for alert in alerts:
        sent[alert.key] = {
            "sent_at": sent_at,
            "symbol": alert.symbol,
            "date": alert.date,
            "action": alert.action,
            "change": alert.change,
            "target_position": alert.target_position,
            "pushplus_message_id": result.get("data"),
        }

    prune_state(state)
    save_state(args.state_file, state)
    LOGGER.info("PushPlus notification sent successfully: %s", result.get("data"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
