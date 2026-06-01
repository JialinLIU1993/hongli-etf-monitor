from .data_loader import fetch_etf_data
from .strategies import BollingerBandsStrategy
from .backtest import BacktestEngine
import pandas as pd
import numpy as np
import itertools

def optimize_bollinger(df, mode='standard'):
    """
    Run Bollinger Bands optimization.
    mode: 
        'standard' - Grid search Window (10-90) x StdDev (1.5-3.5)
        'batch'    - Grid search First Batch Pct (0.1-0.9) with fixed Window=40, Std=2.1
    """
    results = []

    if mode == 'standard':
        # Parameter ranges
        windows = range(10, 95, 5) # 10 to 90
        num_stds = np.arange(1.5, 3.6, 0.1) # 1.5 to 3.5
        
        # Use fixed reasonable defaults for others
        FIXED_STAGED = True
        FIXED_THRESHOLD = 0.02
        FIXED_PCT = 1.0 # Standard usually implies All-in or simple staged. 
                        # To keep heatmap comparable to current "Best", let's use PCT=1.0 (All-in) 
                        # OR use the PCT=0.9 found. 
                        # Let's use PCT=1.0 (All-in) as that was the baseline for the heatmap originally.
        
        total_combinations = len(windows) * len(num_stds)
        print(f"Starting Standard Grid Search on {total_combinations} combinations (Window x Std)...")
        
        for window in windows:
            for num_std in num_stds:
                strategy = BollingerBandsStrategy(
                    window=window, 
                    num_std=num_std, 
                    staged=FIXED_STAGED, 
                    scale_threshold=FIXED_THRESHOLD,
                    first_batch_pct=FIXED_PCT
                )
                engine = BacktestEngine(strategy, df.copy(), initial_capital=100000, commission=0.0003)
                engine.run()
                metrics = engine.calculate_metrics()
                
                results.append({
                    'window': window,
                    'num_std': round(num_std, 1),
                    'Total Return': metrics.get('Total Return', 0),
                    'Sharpe Ratio': metrics.get('Sharpe Ratio', 0),
                    'Max Drawdown': metrics.get('Max Drawdown', 0)
                })

    elif mode == 'batch':
        # Fixed Parameters (from previous optimization)
        FIXED_WINDOW = 40
        FIXED_STD = 2.1
        FIXED_THRESHOLD = 0.02
        
        # Optimize First Batch Percentage
        first_batch_pcts = np.arange(0.1, 1.0, 0.1) # 10% to 90%
        
        print(f"Starting Batch Size Optimization (Window={FIXED_WINDOW}, Std={FIXED_STD})...")
        
        for pct in first_batch_pcts:
            strategy = BollingerBandsStrategy(
                window=FIXED_WINDOW, 
                num_std=FIXED_STD, 
                staged=True, 
                scale_threshold=FIXED_THRESHOLD,
                first_batch_pct=pct
            )
            engine = BacktestEngine(strategy, df.copy(), initial_capital=100000, commission=0.0003)
            engine.run()
            metrics = engine.calculate_metrics()
            
            results.append({
                'window': FIXED_WINDOW,
                'num_std': FIXED_STD,
                'first_batch_pct': round(pct, 1),
                'Total Return': metrics.get('Total Return', 0),
                'Sharpe Ratio': metrics.get('Sharpe Ratio', 0),
                'Max Drawdown': metrics.get('Max Drawdown', 0)
            })
            
    results_df = pd.DataFrame(results)
    return results_df

def main():
    symbol = "510880"
    print(f"Fetching data for {symbol}...")
    df = fetch_etf_data(symbol, start_date="20200101")
    
    if df.empty:
        print("No data found.")
        return

    results_df = optimize_bollinger(df)
    
    # Sort by Total Return
    top_10 = results_df.sort_values(by='Total Return', ascending=False)
    
    print("\n" + "="*50)
    print("OPTIMIZATION RESULTS (Batch Size Ratio)")
    print("="*50)
    print(top_10.to_string(index=False))
    
    # Best Param
    best = top_10.iloc[0]
    print("\n" + "="*50)
    print(f"🏆 BEST BATCH DISTRIBUTION:")
    print(f"First Batch: {best['first_batch_pct']:.0%}")
    print(f"Second Batch: {1 - best['first_batch_pct']:.0%}")
    print(f"Total Return: {best['Total Return']:.2%}")
    print("="*50)

if __name__ == "__main__":
    main()
