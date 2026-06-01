from strategies import BollingerBandsStrategy
from backtest import BacktestEngine
from data_loader import fetch_etf_data
import pandas as pd
import numpy as np

def calculate_metrics_with_cash(results, metrics, risk_free_rate_annual=0.025):
    # Calculate Cash-Enhanced Return
    risk_free_rate_daily = (1 + risk_free_rate_annual) ** (1/252) - 1
    results['cash_return'] = (1 - results['position'].shift(1).fillna(0)) * risk_free_rate_daily
    results['strategy_total_daily'] = results['strategy_net_return'].fillna(0) + results['cash_return']
    results['cumulative_strategy_total'] = (1 + results['strategy_total_daily']).cumprod()
    
    total_return_with_cash = results['cumulative_strategy_total'].iloc[-1] - 1
    avg_position = results['position'].mean()
    
    return {
        "Total Return (ETF)": metrics.get('Total Return', 0),
        "Total Return (w/ Cash)": total_return_with_cash,
        "Annual Return (w/ Cash)": (1 + total_return_with_cash) ** (252/len(results)) - 1,
        "Max Drawdown": metrics.get('Max Drawdown', 0),
        "Sharpe Ratio": metrics.get('Sharpe Ratio', 0),
        "Avg Position": avg_position,
        "Capital Efficiency": metrics.get('Total Return', 0) / avg_position if avg_position > 0 else 0,
        "Win Rate": metrics.get('Win Rate', 0),
        "Transactions": metrics.get('Transaction Count', 0)
    }

def main():
    etfs = [
        {"symbol": "510880", "name": "红利 ETF", "window": 40, "std": 2.1, "batch": 0.9},
        {"symbol": "512890", "name": "红利低波", "window": 50, "std": 2.1, "batch": 1.0}
    ]
    
    print(f"{'ETF Name':<15} | {'Symbol':<8} | {'Params (Win, Std, Batch)':<25} | {'Return (Cash)':<15} | {'Max DD':<10} | {'Win Rate':<10} | {'Eff.':<8} | {'Tx Count':<8}")
    print("-" * 115)
    
    for etf in etfs:
        df = fetch_etf_data(etf['symbol'], start_date="20200101")
        if df.empty: continue
            
        strat = BollingerBandsStrategy(
            window=etf['window'], 
            num_std=etf['std'], 
            staged=True, 
            first_batch_pct=etf['batch']
        )
        engine = BacktestEngine(strat, df.copy(), execution_type='close')
        res = engine.run()
        met = engine.calculate_metrics()
        stats = calculate_metrics_with_cash(res, met)
        
        params_str = f"{etf['window']}, {etf['std']}, {etf['batch']:.0%}"
        print(f"{etf['name']:<15} | {etf['symbol']:<8} | {params_str:<25} | {stats['Total Return (w/ Cash)']:<15.2%} | {stats['Max Drawdown']:<10.2%} | {stats['Win Rate']:<10.2%} | {stats['Capital Efficiency']:<8.2f} | {stats['Transactions']:<8}")

if __name__ == "__main__":
    main()
