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
    symbol = "512890"
    print(f"Fetching data for {symbol}...")
    df = fetch_etf_data(symbol, start_date="20200101")
    if df.empty:
        print("No data.")
        return

    # --- Strategy 1: Optimized Bollinger Bands (Window=50, Std=2.1) ---
    # We need to determine the best Batch Size. Let's do a quick check.
    print("\n[Optimization] Checking best Batch Size for Bollinger(50, 2.1)...")
    best_batch_pct = 0.9
    best_return = -999
    
    for pct in [0.5, 0.6, 0.7, 0.8, 0.9, 1.0]:
        strat = BollingerBandsStrategy(window=50, num_std=2.1, staged=True, first_batch_pct=pct)
        eng = BacktestEngine(strat, df.copy(), execution_type='close')
        res = eng.run()
        ret = res['cumulative_strategy_return'].iloc[-1] - 1
        if ret > best_return:
            best_return = ret
            best_batch_pct = pct
            
    print(f"Best Batch Size found: {best_batch_pct:.0%}")
    
    print(f"Running Optimized Bollinger Strategy (Window=50, Std=2.1, Batch={best_batch_pct:.0%})...")
    strat_boll = BollingerBandsStrategy(
        window=50, 
        num_std=2.1, 
        staged=True, 
        scale_threshold=0.02, 
        first_batch_pct=best_batch_pct
    )
    engine_boll = BacktestEngine(strat_boll, df.copy(), execution_type='close')
    res_boll = engine_boll.run()
    met_boll = engine_boll.calculate_metrics()
    stats_boll = calculate_advanced_metrics(res_boll, met_boll)

    # --- Strategy 2: MA40 Gradual (Reference) ---
    print("Running MA40 Gradual Strategy (Reference)...")
    strat_ma40 = MA40GradualStrategy(window=40, step=0.1)
    engine_ma40 = BacktestEngine(strat_ma40, df.copy(), execution_type='close')
    res_ma40 = engine_ma40.run()
    met_ma40 = engine_ma40.calculate_metrics()
    stats_ma40 = calculate_advanced_metrics(res_ma40, met_ma40)

    # --- Strategy 3: MA120 Trend (Reference) ---
    print("Running MA120 Gradual Strategy (Reference)...")
    strat_ma120 = MA40GradualStrategy(window=120, step=0.25)
    strat_ma120.name = "MA (120) Gradual +/-25%"
    engine_ma120 = BacktestEngine(strat_ma120, df.copy(), execution_type='close')
    res_ma120 = engine_ma120.run()
    met_ma120 = engine_ma120.calculate_metrics()
    stats_ma120 = calculate_advanced_metrics(res_ma120, met_ma120)

    # --- Benchmark: Buy & Hold ---
    bench_return = res_ma40['cumulative_market_return'].iloc[-1] - 1
    rolling_max = res_ma40['cumulative_market_return'].cummax()
    bench_dd = ((res_ma40['cumulative_market_return'] - rolling_max) / rolling_max).min()

    # --- Compare ---
    print("\n" + "="*105)
    print(f"COMPARISON FOR ETF {symbol} (2020-Now)")
    print("="*105)
    print(f"{'Metric':<25} | {'Opt. Bollinger':<18} | {'MA40 (10%)':<15} | {'MA120 (25%)':<15} | {'Buy & Hold':<12}")
    print("-" * 110)
    
    def fmt(val, is_pct=True):
        if is_pct: return f"{val:.2%}"
        return f"{val:.2f}"

    print(f"{'Total Return (ETF)':<25} | {fmt(stats_boll['Total Return (ETF)'])}     | {fmt(stats_ma40['Total Return (ETF)'])}     | {fmt(stats_ma120['Total Return (ETF)'])}     | {fmt(bench_return)}")
    print(f"{'Total Return (w/ Cash)':<25} | {fmt(stats_boll['Total Return (w/ Cash)'])}     | {fmt(stats_ma40['Total Return (w/ Cash)'])}     | {fmt(stats_ma120['Total Return (w/ Cash)'])}     | {fmt(bench_return)}")
    print(f"{'Annual Return':<25} | {fmt(stats_boll['Annual Return'])}     | {fmt(stats_ma40['Annual Return'])}     | {fmt(stats_ma120['Annual Return'])}     | -")
    print(f"{'Max Drawdown':<25} | {fmt(stats_boll['Max Drawdown'])}     | {fmt(stats_ma40['Max Drawdown'])}     | {fmt(stats_ma120['Max Drawdown'])}     | {fmt(bench_dd)}")
    print(f"{'Sharpe Ratio':<25} | {fmt(stats_boll['Sharpe Ratio'], False)}             | {fmt(stats_ma40['Sharpe Ratio'], False)}             | {fmt(stats_ma120['Sharpe Ratio'], False)}             | -")
    print(f"{'Avg Position':<25} | {fmt(stats_boll['Avg Position'])}     | {fmt(stats_ma40['Avg Position'])}     | {fmt(stats_ma120['Avg Position'])}     | 100.00%")
    print(f"{'Capital Efficiency':<25} | {fmt(stats_boll['Capital Efficiency'], False)}x            | {fmt(stats_ma40['Capital Efficiency'], False)}x            | {fmt(stats_ma120['Capital Efficiency'], False)}x            | 1.00x")
    print(f"{'Win Rate':<25} | {fmt(stats_boll['Win Rate'])}     | {fmt(stats_ma40['Win Rate'])}     | {fmt(stats_ma120['Win Rate'])}     | -")
    print(f"{'Transactions':<25} | {stats_boll['Transactions']:<18} | {stats_ma40['Transactions']:<15} | {stats_ma120['Transactions']:<15} | -")
    print("="*105)

if __name__ == "__main__":
    main()
