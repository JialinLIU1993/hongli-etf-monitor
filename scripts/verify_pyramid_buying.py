
import sys
import os
import pandas as pd
import numpy as np

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from data_loader import fetch_etf_data
from strategies import BollingerBandsStrategy
from backtest import BacktestEngine

def run_pyramid_comparison():
    # 1. Load Data
    df = fetch_etf_data(symbol="510880", adjust="qfq")
    df = df[df.index >= '2020-01-01']
    
    print(f"Data range: {df.index.min()} to {df.index.max()}")
    
    # Common Params
    WINDOW = 40
    NUM_STD = 2.1
    # Exit Strategy: Sell 100% (proven best)
    SELL_PCT = 1.0 
    
    # 2. Define Strategies
    
    # Strategy A: Inverted Pyramid (Aggressive Entry)
    # Buy 90% at Lower Band, Add 10% if drops further
    strat_inverted = BollingerBandsStrategy(
        window=WINDOW, num_std=NUM_STD, staged=True,
        first_batch_pct=0.9, # Heavy entry
        sell_batch_pct=SELL_PCT
    )
    strat_inverted.name = "Inverted Pyramid (Buy 90% first)"
    
    # Strategy B: Equal Split
    # Buy 50% at Lower Band, Add 50% if drops further
    strat_equal = BollingerBandsStrategy(
        window=WINDOW, num_std=NUM_STD, staged=True,
        first_batch_pct=0.5, # Equal entry
        sell_batch_pct=SELL_PCT
    )
    strat_equal.name = "Equal Split (Buy 50% first)"
    
    # Strategy C: Normal Pyramid (Conservative Entry)
    # Buy 10% at Lower Band, Add 90% if drops further
    strat_pyramid = BollingerBandsStrategy(
        window=WINDOW, num_std=NUM_STD, staged=True,
        first_batch_pct=0.1, # Light entry
        sell_batch_pct=SELL_PCT
    )
    strat_pyramid.name = "Normal Pyramid (Buy 10% first)"
    
    strategies = [strat_inverted, strat_equal, strat_pyramid]
    results = []
    
    print("\nRunning Backtests...")
    
    for strat in strategies:
        engine = BacktestEngine(strat, df)
        engine.run()
        metrics = engine.calculate_metrics()
        
        # Calculate Average Position during Holding Periods
        # Filter for days where position > 0
        positions = engine.results['position']
        avg_pos_when_holding = positions[positions > 0].mean()
        
        results.append({
            "Name": strat.name,
            "Total Return": metrics['Total Return'],
            "Annual Return": metrics['Annualized Return'],
            "Max Drawdown": metrics['Max Drawdown'],
            "Win Rate": metrics['Win Rate'],
            "Avg Pos (When Holding)": avg_pos_when_holding
        })
        
    # 3. Print Results
    print("\n" + "="*90)
    print("BUYING STRATEGY COMPARISON (Pyramid vs Inverted)")
    print("="*90)
    
    print(f"{'Strategy Name':<30} | {'Total Return':<12} | {'Ann. Return':<12} | {'Max DD':<10} | {'Avg Pos':<8}")
    print("-" * 90)
    
    # Sort by Total Return
    results.sort(key=lambda x: x['Total Return'], reverse=True)
    
    for res in results:
        print(f"{res['Name']:<30} | {res['Total Return']:>11.2%} | {res['Annual Return']:>11.2%} | {res['Max Drawdown']:>9.2%} | {res['Avg Pos (When Holding)']:>8.2%}")

    print("\nAnalysis:")
    best = results[0]
    worst = results[-1]
    
    print(f"Winner: {best['Name']} ({best['Total Return']:.2%})")
    print(f"Loser:  {worst['Name']} ({worst['Total Return']:.2%})")
    
    diff = best['Total Return'] - worst['Total Return']
    print(f"\nDifference: {diff:.2%}")
    print(f"Reason: Look at 'Avg Pos'. The loser only held {worst['Avg Pos (When Holding)']:.2%} on average during uptrends.")
    print("In a strong trend, the price rarely dips deep enough to fill the rest of the pyramid.")

if __name__ == "__main__":
    run_pyramid_comparison()
