
import sys
import os
import pandas as pd
import matplotlib.pyplot as plt

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from data_loader import fetch_etf_data
from strategies import BollingerBandsStrategy, BollingerWithInnerBandStrategy
from backtest import BacktestEngine

def run_micro_swing_comparison():
    # 1. Load Data
    df = fetch_etf_data(symbol="510880", adjust="qfq")
    
    # Filter data from 2020 onwards
    df = df[df.index >= '2020-01-01']
    
    print(f"Data range: {df.index.min()} to {df.index.max()}")
    
    # 2. Define Strategies
    
    # Strategy A: Baseline (Optimized Bollinger)
    # Buy 100% at Lower, Sell 100% at Upper. No movement in between.
    strategy_base = BollingerBandsStrategy(
        window=40, 
        num_std=2.1, 
        staged=False, # All-in for simpler comparison base
        min_position=0.0
    )
    strategy_base.name = "Baseline (Hold Full)"
    
    # Strategy B: Baseline + Micro Swing
    # Buy 100% at Lower.
    # While holding, if price hits Inner Upper (20, 1.5), sell 30%.
    # If price dips back to Inner Lower (20, 1.5), buy back that 30%.
    strategy_micro = BollingerWithInnerBandStrategy(
        main_window=40, main_std=2.1,
        inner_window=20, inner_std=1.5,
        inner_ratio=0.3,
        name="With Micro Swing (30%)"
    )
    
    # 3. Run Backtests
    engine_base = BacktestEngine(strategy_base, df)
    res_base = engine_base.run()
    metrics_base = engine_base.calculate_metrics()
    
    engine_micro = BacktestEngine(strategy_micro, df)
    res_micro = engine_micro.run()
    metrics_micro = engine_micro.calculate_metrics()
    
    # 4. Print Results
    print("\n" + "="*60)
    print("MICRO SWING PERFORMANCE COMPARISON (2020-Present)")
    print("="*60)
    
    print(f"{'Metric':<20} | {'Baseline (Hold Full)':<20} | {'With Micro Swing':<20}")
    print("-" * 70)
    
    print(f"{'Total Return':<20} | {metrics_base['Total Return']:>19.2%} | {metrics_micro['Total Return']:>19.2%}")
    print(f"{'Annual Return':<20} | {metrics_base['Annualized Return']:>19.2%} | {metrics_micro['Annualized Return']:>19.2%}")
    print(f"{'Max Drawdown':<20} | {metrics_base['Max Drawdown']:>19.2%} | {metrics_micro['Max Drawdown']:>19.2%}")
    print(f"{'Win Rate':<20} | {metrics_base['Win Rate']:>19.2%} | {metrics_micro['Win Rate']:>19.2%}")
    print(f"{'Transactions':<20} | {metrics_base['Transaction Count']:>19} | {metrics_micro['Transaction Count']:>19}")

    print("\nAnalysis:")
    diff = metrics_micro['Total Return'] - metrics_base['Total Return']
    if diff > 0.05:
        print(f"- Micro Swing SIGNIFICANTLY improves return by {diff:.1%}.")
    elif diff > 0:
        print(f"- Micro Swing slightly improves return by {diff:.1%}.")
    else:
        print(f"- Micro Swing REDUCES return by {abs(diff):.1%}. It might be over-trading or selling too early.")

    if metrics_micro['Transaction Count'] > metrics_base['Transaction Count'] * 2:
        print(f"- Note: Transaction count increased significantly ({metrics_micro['Transaction Count']} vs {metrics_base['Transaction Count']}).")
        print("  Ensure commission costs are acceptable.")

if __name__ == "__main__":
    run_micro_swing_comparison()
