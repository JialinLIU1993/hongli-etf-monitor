from strategies import MA40GradualStrategy
from backtest import BacktestEngine
from data_loader import fetch_etf_data
import pandas as pd

def main():
    # 1. Load Data
    # Using the default 510880 ETF
    df = fetch_etf_data(start_date="20200101")
    
    if df.empty:
        print("No data found.")
        return

    # 2. Initialize Strategy
    strategy = MA40GradualStrategy(window=40, step=0.1)
    
    # 3. Run Backtest
    # Using 'close' execution (trade at close of same day) as implied by "Daily Buy/Sell"
    # Usually "If price < MA, buy" implies checking during the day or at close.
    # If we check at close and buy at close, it's 'close' execution.
    engine = BacktestEngine(strategy, df, execution_type='close')
    results = engine.run()
    
    # 4. Calculate Metrics
    metrics = engine.calculate_metrics()
    
    # 5. Output Results
    print("\n" + "="*30)
    print(f"Backtest Results: {strategy.name}")
    print("="*30)
    
    # Calculate Benchmark Return
    benchmark_return = results['cumulative_market_return'].iloc[-1] - 1
    
    # Calculate Additional Analysis Metrics
    avg_position = results['position'].mean()
    total_cost_drag = results['cost'].sum()

    # Calculate Cash-Enhanced Return (Assuming 2.5% annual risk-free rate on idle cash)
    risk_free_rate_annual = 0.025
    risk_free_rate_daily = (1 + risk_free_rate_annual) ** (1/252) - 1
    
    # Idle cash ratio each day = 1 - position
    # Cash return = idle_ratio * risk_free_rate_daily
    results['cash_return'] = (1 - results['position'].shift(1).fillna(0)) * risk_free_rate_daily
    
    # Total strategy return with cash
    # (1 + strat_net_ret + cash_ret) - 1
    # Compound it
    results['strategy_total_daily'] = results['strategy_net_return'].fillna(0) + results['cash_return']
    results['cumulative_strategy_total'] = (1 + results['strategy_total_daily']).cumprod()
    
    total_return_with_cash = results['cumulative_strategy_total'].iloc[-1] - 1
    annual_return_with_cash = (1 + total_return_with_cash) ** (252/len(results)) - 1
    
    # Benchmark Max Drawdown
    rolling_max_bench = results['cumulative_market_return'].cummax()
    drawdown_bench = (results['cumulative_market_return'] - rolling_max_bench) / rolling_max_bench
    max_drawdown_bench = drawdown_bench.min()

    print(f"Benchmark Return: {benchmark_return:.2%}")
    print(f"Benchmark Max Drawdown: {max_drawdown_bench:.2%}")
    print("-" * 30)
    print(f"Strategy Total Return (ETF Only): {metrics.get('Total Return', 0):.2%}")
    print(f"Strategy Total Return (w/ 2.5% Cash): {total_return_with_cash:.2%}")
    print(f"Strategy Max Drawdown: {metrics.get('Max Drawdown', 0):.2%}")
    print("-" * 30)
    print(f"Average Position Exposure: {avg_position:.2%}")
    print(f"Total Transaction Cost Drag: {total_cost_drag:.2%}")
    print(f"Capital Efficiency (Ret/Exp): {metrics.get('Total Return', 0)/avg_position:.2f}x vs Benchmark 1.00x")
    print(f"Annual Return: {metrics.get('Annualized Return', 0):.2%}")
    print(f"Max Drawdown: {metrics.get('Max Drawdown', 0):.2%}")
    print(f"Sharpe Ratio: {metrics.get('Sharpe Ratio', 0):.2f}")
    print(f"Transactions: {metrics.get('Transaction Count', 0)}")
    print(f"Win Rate: {metrics.get('Win Rate', 0):.2%}")
    
    # Optional: Save results to CSV for inspection
    results.to_csv("ma40_backtest_results.csv")
    print("\nDetailed results saved to ma40_backtest_results.csv")

if __name__ == "__main__":
    main()
