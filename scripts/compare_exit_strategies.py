
import sys
import os
import pandas as pd
import matplotlib.pyplot as plt

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from data_loader import fetch_etf_data
from strategies import BollingerBandsStrategy
from backtest import BacktestEngine

def run_exit_comparison():
    # 1. Load Data
    df = fetch_etf_data(symbol="510880", adjust="qfq")
    
    # Filter data from 2020 onwards
    df = df[df.index >= '2020-01-01']
    
    print(f"Data range: {df.index.min()} to {df.index.max()}")
    
    # 2. Define Strategies
    
    # Common params
    WINDOW = 40
    NUM_STD = 2.1
    BUY_PCT = 0.9 # Buy 90% at lower band
    
    # Strategy A: Sell 10% at Upper Band (Keep 90%) - DOCUMENTED
    strategy_keep90 = BollingerBandsStrategy(
        window=WINDOW, num_std=NUM_STD, staged=True,
        first_batch_pct=BUY_PCT, 
        sell_batch_pct=0.1, # Sell 10%
    )
    strategy_keep90.name = "Sell 10% (Keep 90%)"
    
    # Strategy B: Sell 50% at Upper Band (Keep 50%) - BALANCED
    strategy_keep50 = BollingerBandsStrategy(
        window=WINDOW, num_std=NUM_STD, staged=True,
        first_batch_pct=BUY_PCT, 
        sell_batch_pct=0.5, # Sell 50%
    )
    strategy_keep50.name = "Sell 50% (Keep 50%)"
    
    # Strategy C: Sell 90% at Upper Band (Keep 10%) - AGGRESSIVE
    strategy_keep10 = BollingerBandsStrategy(
        window=WINDOW, num_std=NUM_STD, staged=True,
        first_batch_pct=BUY_PCT, 
        sell_batch_pct=0.9, # Sell 90%
    )
    strategy_keep10.name = "Sell 90% (Keep 10%)"
    
    # Strategy D: Sell 100% at Upper Band (All Out) - SIMPLE
    strategy_all_out = BollingerBandsStrategy(
        window=WINDOW, num_std=NUM_STD, staged=False, # All-in mode for exit
    )
    strategy_all_out.name = "Sell 100% (All Out)"
    # Note: strategy_all_out uses All-in logic (Buy 100%, Sell 100%)
    
    strategies = [strategy_keep90, strategy_keep50, strategy_keep10, strategy_all_out]
    results = []
    
    print("\nRunning Backtests...")
    
    for strat in strategies:
        engine = BacktestEngine(strat, df)
        engine.run()
        metrics = engine.calculate_metrics()
        results.append({
            "Name": strat.name,
            "Total Return": metrics['Total Return'],
            "Annual Return": metrics['Annualized Return'],
            "Max Drawdown": metrics['Max Drawdown'],
            "Win Rate": metrics['Win Rate'],
            "Tx Count": metrics['Transaction Count']
        })
        
    # 3. Print Results
    print("\n" + "="*80)
    print("EXIT STRATEGY COMPARISON (When hitting Upper Band)")
    print("="*80)
    
    print(f"{'Strategy Name':<25} | {'Total Return':<12} | {'Ann. Return':<12} | {'Max DD':<10} | {'Tx Count':<8}")
    print("-" * 80)
    
    # Sort by Total Return descending
    results.sort(key=lambda x: x['Total Return'], reverse=True)
    
    for res in results:
        print(f"{res['Name']:<25} | {res['Total Return']:>11.2%} | {res['Annual Return']:>11.2%} | {res['Max Drawdown']:>9.2%} | {res['Tx Count']:>8}")

    print("\nAnalysis:")
    best = results[0]
    print(f"The BEST strategy is: {best['Name']} with {best['Total Return']:.2%} return.")
    
    if "Sell 10%" in best['Name']:
        print("- This confirms that 'Selling a little (10%)' to lock in small profit but keeping 90% for the trend is best.")
    elif "Sell 90%" in best['Name']:
        print("- This suggests 'Selling most (90%)' to take profit early is better.")
    elif "Sell 100%" in best['Name']:
        print("- Simple All-In/All-Out is best. Staged exit might be over-optimizing.")

if __name__ == "__main__":
    run_exit_comparison()
