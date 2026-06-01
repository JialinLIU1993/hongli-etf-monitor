"""
红利双雄布林带下轨监控脚本
在交易日 10:00 和 14:00 运行，检查现价是否触及或跌破布林带下轨。
"""
import akshare as ak
import pandas as pd
import numpy as np
import logging
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# ETF 配置
ETFS = {
    "510880": {"name": "红利 ETF", "window": 40, "num_std": 2.1},
    "512890": {"name": "红利低波", "window": 50, "num_std": 2.1},
}

LOOKBACK_DAYS = 120


def fetch_recent_data(symbol: str) -> pd.DataFrame:
    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=LOOKBACK_DAYS)).strftime("%Y%m%d")
    df = ak.fund_etf_hist_em(
        symbol=symbol, period="daily",
        start_date=start_date, end_date=end_date, adjust="qfq"
    )
    col_map = {"日期": "date", "开盘": "open", "收盘": "close",
               "最高": "high", "最低": "low", "成交量": "volume"}
    df.rename(columns=col_map, inplace=True)
    df["date"] = pd.to_datetime(df["date"])
    df.set_index("date", inplace=True)
    df.sort_index(inplace=True)
    return df


def calc_lower_band(df: pd.DataFrame, window: int, num_std: float) -> float:
    ma = df["close"].rolling(window=window).mean().iloc[-1]
    std = df["close"].rolling(window=window).std().iloc[-1]
    return ma - std * num_std


def is_trading_day() -> bool:
    today = datetime.now().weekday()
    return today < 5


def check_alerts() -> list[str]:
    alerts = []
    for symbol, cfg in ETFS.items():
        try:
            df = fetch_recent_data(symbol)
        except Exception as e:
            logger.error(f"获取 {symbol} 数据失败: {e}")
            alerts.append(f"⚠️ {symbol} {cfg['name']}: 数据获取失败 ({e})")
            continue

        if df.empty:
            alerts.append(f"⚠️ {symbol} {cfg['name']}: 无数据")
            continue

        latest_close = df["close"].iloc[-1]
        latest_date = df.index[-1].strftime("%Y-%m-%d")
        lower_band = calc_lower_band(df, cfg["window"], cfg["num_std"])

        logger.info(
            f"{symbol} {cfg['name']} | 最新日期: {latest_date} | "
            f"现价: {latest_close:.3f} | 下轨: {lower_band:.3f} | "
            f"偏离: {(latest_close - lower_band) / lower_band * 100:.2f}%"
        )

        if latest_close <= lower_band:
            deviation = (lower_band - latest_close) / lower_band * 100
            alerts.append(
                f"🔔 {symbol} {cfg['name']} 触发买入信号！\n"
                f"   现价: {latest_close:.3f}\n"
                f"   布林带下轨: {lower_band:.3f}\n"
                f"   低于下轨: {deviation:.2f}%\n"
                f"   数据日期: {latest_date}"
            )

    return alerts


def main():
    if not is_trading_day():
        print("今日非交易日，跳过监控。")
        return

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"\n{'='*50}")
    print(f"红利双雄布林带监控 | {now_str}")
    print(f"{'='*50}\n")

    alerts = check_alerts()

    if alerts:
        print("\n--- 监控结果 ---\n")
        for a in alerts:
            print(a)
            print()
    else:
        print("\n✅ 所有标的现价均在布林带下轨之上，无需操作。\n")


if __name__ == "__main__":
    main()
