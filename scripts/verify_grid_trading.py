
import sys
import os
import pandas as pd
import matplotlib.pyplot as plt

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from data_loader import fetch_etf_data
from strategies import BollingerBandsStrategy, BollingerWithGridStrategy
from backtest import BacktestEngine

def run_grid_comparison():
    # 1. Load Data
    df = fetch_etf_data(symbol="510880", adjust="qfq")
    
    # Filter data from 2020 onwards
    df = df[df.index >= '2020-01-01']
    
    print(f"Data range: {df.index.min()} to {df.index.max()}")
    
    # 2. Define Strategies
    
    # Strategy A: Baseline (Optimized Bollinger)
    strategy_base = BollingerBandsStrategy(
        window=40, 
        num_std=2.1, 
        staged=False, 
        min_position=0.0
    )
    strategy_base.name = "Baseline (Hold Full)"
    
    # Strategy B: Baseline + 1% Grid
    # Sell 10% for every 1% rise, Buy back if drops 1%.
    # Max 50% position used for grid (5 grids).
    strategy_grid = BollingerWithGridStrategy(
        window=40, num_std=2.1,
        grid_step=0.01, # 1%
        grid_qty=0.1,   # 10% per grid
        max_grids=5,    # Max 50% sold
        name="With 1% Grid (Max 50%)"
    )
    
    # 3. Run Backtests
    engine_base = BacktestEngine(strategy_base, df)
    res_base = engine_base.run()
    metrics_base = engine_base.calculate_metrics()
    
    engine_grid = BacktestEngine(strategy_grid, df)
    res_grid = engine_grid.run()
    metrics_grid = engine_grid.calculate_metrics()
    
    # 4. Print Results
    print("\n" + "="*65)
    print("GRID TRADING PERFORMANCE COMPARISON (2020-Present)")
    print("="*65)
    
    print(f"{'Metric':<20} | {'Baseline (Hold Full)':<20} | {'With 1% Grid':<20}")
    print("-" * 75)
    
    print(f"{'Total Return':<20} | {metrics_base['Total Return']:>19.2%} | {metrics_grid['Total Return']:>19.2%}")
    print(f"{'Annual Return':<20} | {metrics_base['Annualized Return']:>19.2%} | {metrics_grid['Annualized Return']:>19.2%}")
    print(f"{'Max Drawdown':<20} | {metrics_base['Max Drawdown']:>19.2%} | {metrics_grid['Max Drawdown']:>19.2%}")
    print(f"{'Win Rate':<20} | {metrics_base['Win Rate']:>19.2%} | {metrics_grid['Win Rate']:>19.2%}")
    print(f"{'Transactions':<20} | {metrics_base['Transaction Count']:>19} | {metrics_grid['Transaction Count']:>19}")

    print("\nAnalysis:")
    diff = metrics_grid['Total Return'] - metrics_base['Total Return']
    
    if diff > 0.05:
        print(f"- 1% Grid SIGNIFICANTLY improves return by {diff:.1%}.")
    elif diff > 0:
        print(f"- 1% Grid slightly improves return by {diff:.1%}.")
    else:
        print(f"- 1% Grid REDUCES return by {abs(diff):.1%}.")
        print("  Reason: In a strong uptrend, you sell early and price never drops 1% to let you buy back.")
        print("  You end up holding less position during the main rally.")

if __name__ == "__main__":
    run_grid_comparison()
