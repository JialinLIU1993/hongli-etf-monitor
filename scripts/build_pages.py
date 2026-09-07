"""Build public Pages assets from market data only; never read personal records."""
import argparse
from dataclasses import asdict
from datetime import datetime
import json
import logging
from pathlib import Path
import shutil
import sys
from zoneinfo import ZoneInfo

import pandas as pd
from plotly.offline import get_plotlyjs

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_sources import PRICE_BASIS_LABELS, PROVIDER_LABELS, resolve_provider
from src.monitoring import ETF_PROFILES, calculate_monitor_frame
from src.optimize import optimize_bollinger

COLUMNS = ['open', 'high', 'low', 'close', 'volume', 'ma', 'upper_band', 'lower_band', 'position', 'signal']


def make_payload(frames, provider='akshare'):
    assets = {}
    for symbol, profile in ETF_PROFILES.items():
        raw = frames[symbol].sort_index()
        if raw.empty:
            raise ValueError(f'{symbol}: no market data available')
        raw = raw.loc[raw.index.max() - pd.DateOffset(years=1):]
        frame = calculate_monitor_frame(raw, window=profile.window, num_std=profile.num_std,
                                        first_batch_pct=profile.first_batch_pct)
        public = frame[COLUMNS].copy()
        public.insert(0, 'date', frame.index.strftime('%Y-%m-%d'))
        grid = optimize_bollinger(raw, windows=sorted(set(range(10, 95, 10)) | {profile.window}),
                                  num_stds=[1.5, 1.8, 2.1, 2.4, 2.7, 3., 3.3],
                                  first_batch_pct=profile.first_batch_pct)
        assets[symbol] = dict(profile=asdict(profile), rows=json.loads(public.to_json(orient='records')),
                              optimization=json.loads(grid.to_json(orient='records')))
    return dict(schema=1, provider=provider, source=PROVIDER_LABELS[provider],
                price_basis=PRICE_BASIS_LABELS[provider], assets=assets,
                data_as_of=min(asset['rows'][-1]['date'] for asset in assets.values()))


def build(output, refresh=False, seed_path=None):
    seed = seed_path or ROOT / 'web' / 'market-seed.json'
    payload = json.loads(seed.read_text())
    if refresh:
        from src.data_loader import fetch_etf_data
        provider = resolve_provider()
        now = pd.Timestamp.now(tz='Asia/Shanghai')
        frames = {symbol: fetch_etf_data(symbol, start_date=(now - pd.DateOffset(years=1)).strftime('%Y%m%d'),
                                        end_date=now.strftime('%Y%m%d'), provider=provider, force_update=True)
                  for symbol in ETF_PROFILES}
        candidate = make_payload(frames, provider)
        if candidate['data_as_of'] >= payload['data_as_of']:
            payload = candidate
        elif candidate['provider'] != payload['provider']:
            raise ValueError('Configured source has insufficient current data')
    payload['built_at'] = datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(timespec='seconds')
    output.mkdir(parents=True, exist_ok=True)
    for name in ('index.html', 'app.css', 'app.js'):
        shutil.copyfile(ROOT / 'web' / name, output / name)
    (output / 'market.json').write_text(json.dumps(payload, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    (output / 'plotly.min.js').write_text(get_plotlyjs(), encoding='utf-8')
    (output / '.nojekyll').touch()
    print(f'Pages assets ready: {output}; market data through {payload["data_as_of"]}')


if __name__ == '__main__':
    logging.basicConfig(level=logging.WARNING)
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT / 'output' / 'pages')
    parser.add_argument('--refresh', action='store_true')
    parser.add_argument('--seed-from-cache', action='store_true')
    args = parser.parse_args()
    if args.seed_from_cache:
        frames = {s: pd.read_csv(ROOT / 'data' / f'{s}_qfq.csv', index_col='date', parse_dates=True) for s in ETF_PROFILES}
        (ROOT / 'web' / 'market-seed.json').write_text(json.dumps(make_payload(frames), ensure_ascii=False, allow_nan=False), encoding='utf-8')
    build(args.output, args.refresh)
