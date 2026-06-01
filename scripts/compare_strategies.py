from strategies import MA40GradualStrategy, BollingerBandsStrategy
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

    # 1. MA40 Gradual Strategy
    print("\nRunning MA40 Gradual Strategy...")
    strat_ma40 = MA40GradualStrategy(window=40, step=0.1)
    engine_ma40 = BacktestEngine(strat_ma40, df.copy(), execution_type='close')
    res_ma40 = engine_ma40.run()
    met_ma40 = engine_ma40.calculate_metrics()
    stats_ma40 = calculate_advanced_metrics(res_ma40, met_ma40)

    # 1.5. MA120 Gradual Strategy (New)
    print("Running MA120 Gradual Strategy (Step 25%)...")
    strat_ma120 = MA40GradualStrategy(window=120, step=0.25) # Reusing class, it accepts params
    strat_ma120.name = "MA (120) Gradual +/-25%" # Update name manually for clarity if needed
    engine_ma120 = BacktestEngine(strat_ma120, df.copy(), execution_type='close')
    res_ma120 = engine_ma120.run()
    met_ma120 = engine_ma120.calculate_metrics()
    stats_ma120 = calculate_advanced_metrics(res_ma120, met_ma120)

    # 2. Optimized Bollinger Bands Strategy
    # Parameters from batch_optimization_results.csv (Best Return)
    # window=40, num_std=2.1, scale_threshold=0.02, first_batch_pct=0.9
    print("Running Optimized Bollinger Strategy...")
    strat_boll = BollingerBandsStrategy(
        window=40, 
        num_std=2.1, 
        staged=True, 
        scale_threshold=0.02, 
        first_batch_pct=0.9
    )
    engine_boll = BacktestEngine(strat_boll, df.copy(), execution_type='close')
    res_boll = engine_boll.run()
    met_boll = engine_boll.calculate_metrics()
    stats_boll = calculate_advanced_metrics(res_boll, met_boll)

    # 3. Benchmark (Buy & Hold)
    bench_return = res_ma40['cumulative_market_return'].iloc[-1] - 1
    rolling_max = res_ma40['cumulative_market_return'].cummax()
    bench_dd = ((res_ma40['cumulative_market_return'] - rolling_max) / rolling_max).min()

    # 4. Compare
    print("\n" + "="*105)
    print(f"{'Metric':<25} | {'MA40 (10%)':<15} | {'MA120 (25%)':<15} | {'Opt. Bollinger':<18} | {'Buy & Hold':<12}")
    print("-" * 110)
    
    def fmt(val, is_pct=True):
        if is_pct: return f"{val:.2%}"
        return f"{val:.2f}"

    print(f"{'Total Return (ETF)':<25} | {fmt(stats_ma40['Total Return (ETF)'])}     | {fmt(stats_ma120['Total Return (ETF)'])}     | {fmt(stats_boll['Total Return (ETF)'])}     | {fmt(bench_return)}")
    print(f"{'Total Return (w/ Cash)':<25} | {fmt(stats_ma40['Total Return (w/ Cash)'])}     | {fmt(stats_ma120['Total Return (w/ Cash)'])}     | {fmt(stats_boll['Total Return (w/ Cash)'])}     | {fmt(bench_return)}")
    print(f"{'Annual Return':<25} | {fmt(stats_ma40['Annual Return'])}     | {fmt(stats_ma120['Annual Return'])}     | {fmt(stats_boll['Annual Return'])}     | -")
    print(f"{'Max Drawdown':<25} | {fmt(stats_ma40['Max Drawdown'])}     | {fmt(stats_ma120['Max Drawdown'])}     | {fmt(stats_boll['Max Drawdown'])}     | {fmt(bench_dd)}")
    print(f"{'Sharpe Ratio':<25} | {fmt(stats_ma40['Sharpe Ratio'], False)}             | {fmt(stats_ma120['Sharpe Ratio'], False)}             | {fmt(stats_boll['Sharpe Ratio'], False)}             | -")
    print(f"{'Avg Position':<25} | {fmt(stats_ma40['Avg Position'])}     | {fmt(stats_ma120['Avg Position'])}     | {fmt(stats_boll['Avg Position'])}     | 100.00%")
    print(f"{'Capital Efficiency':<25} | {fmt(stats_ma40['Capital Efficiency'], False)}x            | {fmt(stats_ma120['Capital Efficiency'], False)}x            | {fmt(stats_boll['Capital Efficiency'], False)}x            | 1.00x")
    print(f"{'Win Rate':<25} | {fmt(stats_ma40['Win Rate'])}     | {fmt(stats_ma120['Win Rate'])}     | {fmt(stats_boll['Win Rate'])}     | -")
    print(f"{'Transactions':<25} | {stats_ma40['Transactions']:<15} | {stats_ma120['Transactions']:<15} | {stats_boll['Transactions']:<18} | -")
    print("="*105)

if __name__ == "__main__":
    main()
