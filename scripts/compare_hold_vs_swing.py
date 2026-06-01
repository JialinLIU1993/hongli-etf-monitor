
import sys
import os
import pandas as pd
import matplotlib.pyplot as plt

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from data_loader import fetch_etf_data
from strategies import BollingerBandsStrategy
from backtest import BacktestEngine

def run_comparison():
    # 1. Load Data
    # loader = DataLoader('data/510880_qfq.csv')
    # df = loader.load()
    df = fetch_etf_data(symbol="510880", adjust="qfq")
    
    # Filter data from 2020 onwards to match documentation period
    df = df[df.index >= '2020-01-01']
    
    print(f"Data range: {df.index.min()} to {df.index.max()}")
    
    # 2. Define Strategies
    # Parameters based on documentation: Window=40, Std=2.1
    # Using first_batch_pct=0.5 for balanced staging as code doesn't support asymmetric well yet
    
    # Strategy A: Pure Swing (No minimum position, full band trading)
    # Corresponds to "Optimized Bollinger Strategy" in docs (roughly)
    strategy_swing = BollingerBandsStrategy(
        window=40, 
        num_std=2.1, 
        staged=True, 
        min_position=0.0,
        first_batch_pct=0.5
    )
    strategy_swing.name = "Pure Swing (0% Base)"
    
    # Strategy B: Base + Swing (Hold 50%, Swing 50%)
    # This simulates "Trading within a range while holding"
    strategy_hybrid = BollingerBandsStrategy(
        window=40, 
        num_std=2.1, 
        staged=True, 
        min_position=0.5,
        first_batch_pct=0.5
    )
    strategy_hybrid.name = "Base + Swing (50% Base)"
    
    # 3. Run Backtests
    engine_swing = BacktestEngine(strategy_swing, df)
    res_swing = engine_swing.run()
    metrics_swing = engine_swing.calculate_metrics()
    
    engine_hybrid = BacktestEngine(strategy_hybrid, df)
    res_hybrid = engine_hybrid.run()
    metrics_hybrid = engine_hybrid.calculate_metrics()
    
    # Benchmark (Buy & Hold) is in res_swing['cumulative_market_return']
    total_return_bench = res_swing['cumulative_market_return'].iloc[-1] - 1
    annual_return_bench = (1 + total_return_bench) ** (252/len(res_swing)) - 1
    max_dd_bench = ((res_swing['close'] - res_swing['close'].cummax()) / res_swing['close'].cummax()).min()
    
    # 4. Print Results
    print("\n" + "="*50)
    print("STRATEGY PERFORMANCE COMPARISON (2020-Present)")
    print("="*50)
    
    print(f"{'Metric':<20} | {'Buy & Hold':<15} | {'Base + Swing (50%)':<20} | {'Pure Swing (0%)':<15}")
    print("-" * 80)
    
    print(f"{'Total Return':<20} | {total_return_bench:>14.2%} | {metrics_hybrid['Total Return']:>19.2%} | {metrics_swing['Total Return']:>14.2%}")
    print(f"{'Annual Return':<20} | {annual_return_bench:>14.2%} | {metrics_hybrid['Annualized Return']:>19.2%} | {metrics_swing['Annualized Return']:>14.2%}")
    print(f"{'Max Drawdown':<20} | {max_dd_bench:>14.2%} | {metrics_hybrid['Max Drawdown']:>19.2%} | {metrics_swing['Max Drawdown']:>14.2%}")
    print(f"{'Win Rate':<20} | {'N/A':>15} | {metrics_hybrid['Win Rate']:>19.2%} | {metrics_swing['Win Rate']:>14.2%}")
    print(f"{'Transactions':<20} | {'1':>15} | {metrics_hybrid['Transaction Count']:>19} | {metrics_swing['Transaction Count']:>14}")

    print("\nAnalysis:")
    if metrics_hybrid['Total Return'] > total_return_bench:
        print("- Holding a base position while swinging (Base + Swing) OUTPERFORMS simple Buy & Hold.")
    else:
        print("- Holding a base position while swinging (Base + Swing) UNDERPERFORMS simple Buy & Hold.")
        
    if metrics_swing['Total Return'] > metrics_hybrid['Total Return']:
        print("- However, Pure Swing (0% Base) performs BEST, suggesting that avoiding drawdowns during downturns is crucial.")
    else:
        print("- Base + Swing performs better than Pure Swing.")

if __name__ == "__main__":
    run_comparison()
