from strategies import BollingerBandsStrategy
from backtest import BacktestEngine
from data_loader import fetch_etf_data
import pandas as pd
import numpy as np

def calculate_advanced_metrics(results, metrics, risk_free_rate_annual=0.025):
    # Calculate Cash-Enhanced Return
    risk_free_rate_daily = (1 + risk_free_rate_annual) ** (1/252) - 1
    
    # Idle cash ratio each day = 1 - position
    # Cash return = idle_ratio * risk_free_rate_daily
    results['cash_return'] = (1 - results['position'].shift(1).fillna(0)) * risk_free_rate_daily
    
    # Total strategy return with cash
    results['strategy_total_daily'] = results['strategy_net_return'].fillna(0) + results['cash_return']
    results['cumulative_strategy_total'] = (1 + results['strategy_total_daily']).cumprod()
    
    total_return_with_cash = results['cumulative_strategy_total'].iloc[-1] - 1
    
    avg_position = results['position'].mean()
    
    return {
        "Total Return (ETF)": metrics.get('Total Return', 0),
        "Total Return (w/ Cash)": total_return_with_cash,
        "Annual Return": metrics.get('Annualized Return', 0),
        "Max Drawdown": metrics.get('Max Drawdown', 0),
        "Sharpe Ratio": metrics.get('Sharpe Ratio', 0),
        "Avg Position": avg_position,
        "Capital Efficiency": metrics.get('Total Return', 0) / avg_position if avg_position > 0 else 0,
        "Win Rate": metrics.get('Win Rate', 0),
        "Transactions": metrics.get('Transaction Count', 0)
    }

def main():
    print("Fetching data...")
    df = fetch_etf_data(start_date="20200101")
    if df.empty:
        print("No data.")
        return

    # Benchmark (Buy & Hold)
    bench_ret_series = df['close'].pct_change()
    bench_cum_ret = (1 + bench_ret_series).cumprod()
    bench_return = bench_cum_ret.iloc[-1] - 1
    rolling_max = bench_cum_ret.cummax()
    bench_dd = ((bench_cum_ret - rolling_max) / rolling_max).min()

    # Optimized Bollinger Params
    WINDOW = 40
    NUM_STD = 2.1
    SCALE_THRESHOLD = 0.02
    FIRST_BATCH_PCT = 0.9

    min_positions = [0.0, 0.2, 0.4, 0.5, 0.6, 0.8]
    
    print("\n" + "="*120)
    print(f"{'Strategy (Min Pos)':<20} | {'Total Ret (ETF)':<15} | {'Total Ret (Cash)':<15} | {'Max DD':<10} | {'Sharpe':<8} | {'Avg Pos':<10} | {'Efficiency':<10} | {'Win Rate':<10}")
    print("-" * 120)
    
    # Print Benchmark first
    print(f"{'Buy & Hold (100%)':<20} | {bench_return:.2%}          | {bench_return:.2%} (N/A)   | {bench_dd:.2%}    | {'-':<8} | 100.00%    | 1.00x      | -")

    for min_pos in min_positions:
        strat = BollingerBandsStrategy(
            window=WINDOW, 
            num_std=NUM_STD, 
            staged=True, 
            scale_threshold=SCALE_THRESHOLD, 
            first_batch_pct=FIRST_BATCH_PCT,
            min_position=min_pos
        )
        engine = BacktestEngine(strat, df.copy(), execution_type='close')
        res = engine.run()
        met = engine.calculate_metrics()
        stats = calculate_advanced_metrics(res, met)
        
        name = f"Bollinger (Min {min_pos:.0%})"
        
        print(f"{name:<20} | {stats['Total Return (ETF)']:.2%}          | {stats['Total Return (w/ Cash)']:.2%}          | {stats['Max Drawdown']:.2%}    | {stats['Sharpe Ratio']:.2f}     | {stats['Avg Position']:.2%}     | {stats['Capital Efficiency']:.2f}x      | {stats['Win Rate']:.2%}")
        
    print("="*120)

if __name__ == "__main__":
    main()
