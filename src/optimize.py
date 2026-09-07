"""Bollinger parameter searches using the same backtest model as reports."""

import numpy as np
import pandas as pd

from .backtest import BacktestEngine
from .strategies import BollingerBandsStrategy


def optimize_bollinger(df, mode='standard', *, windows=None, num_stds=None,
                       first_batch_pct=1.0, scale_threshold=0.02,
                       pyramid_levels=None, pyramid_sizes=None):
    """Search Window × StdDev, or batch sizes with fixed Window=40 / Std=2.1.

    Custom grids and staged settings allow the UI to evaluate its current data
    and configuration. Search results omit expensive per-trade FIFO statistics.
    """
    if mode not in {'standard', 'batch'}:
        raise ValueError("mode must be 'standard' or 'batch'")
    columns = ['window', 'num_std']
    if mode == 'batch':
        columns.append('first_batch_pct')
    columns += ['Total Return', 'Sharpe Ratio', 'Max Drawdown']
    if df.empty:
        return pd.DataFrame(columns=columns)

    if mode == 'standard':
        windows = tuple(range(10, 95, 5) if windows is None else windows)
        num_stds = tuple(np.arange(1.5, 3.6, 0.1) if num_stds is None else num_stds)
        combinations = ((window, num_std, first_batch_pct)
                        for window in windows for num_std in num_stds)
    else:
        combinations = ((40, 2.1, pct) for pct in np.arange(0.1, 1.0, 0.1))

    results = []
    for window, num_std, pct in combinations:
        strategy = BollingerBandsStrategy(
            window=window,
            num_std=num_std,
            staged=True,
            scale_threshold=scale_threshold,
            first_batch_pct=pct,
            pyramid_levels=pyramid_levels,
            pyramid_sizes=pyramid_sizes,
        )
        # Signal generation already copies its input; an extra full-frame copy
        # for each grid point is unnecessary.
        engine = BacktestEngine(strategy, df, initial_capital=100000, commission=0.0003)
        engine.run()
        metrics = engine.calculate_metrics(include_trade_stats=False)
        result = {
            'window': window,
            'num_std': round(num_std, 1),
            'Total Return': metrics['Total Return'],
            'Sharpe Ratio': metrics['Sharpe Ratio'],
            'Max Drawdown': metrics['Max Drawdown'],
        }
        if mode == 'batch':
            result['first_batch_pct'] = round(pct, 1)
        results.append(result)
    return pd.DataFrame(results, columns=columns)


def main():
    from .data_loader import fetch_etf_data

    symbol = '510880'
    print(f'Fetching data for {symbol}...')
    df = fetch_etf_data(symbol, start_date='20200101')
    if df.empty:
        print('No data found.')
        return

    # This report displays batch percentages, so explicitly run the batch mode.
    results = optimize_bollinger(df, mode='batch').sort_values('Total Return', ascending=False)
    print('\nOPTIMIZATION RESULTS (Batch Size Ratio)')
    print(results.to_string(index=False))
    best = results.iloc[0]
    print(f"\nBest first batch: {best['first_batch_pct']:.0%}")
    print(f"Second batch: {1 - best['first_batch_pct']:.0%}")
    print(f"Total Return: {best['Total Return']:.2%}")


if __name__ == '__main__':
    main()
