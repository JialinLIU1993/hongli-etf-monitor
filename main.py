from src.data_loader import fetch_etf_data
from src.strategies import BollingerBandsStrategy, RSIStrategy
from src.backtest import BacktestEngine
from src.visualization import plot_performance
import matplotlib.pyplot as plt
import os

def main():
    # 1. Fetch Data
    symbol = "510880"
    print(f"Fetching data for {symbol}...")
    # Fetch from 2020 to ensure enough data for windows
    df = fetch_etf_data(symbol, start_date="20200101")
    
    if df.empty:
        print("No data found. Exiting.")
        return

    # 2. Define Strategies
    strategies = [
        BollingerBandsStrategy(window=20, num_std=2),
        RSIStrategy(window=14, buy_threshold=30, sell_threshold=70, staged=True)
    ]
    
    # 3. Run Backtests
    for strategy in strategies:
        print(f"\nRunning Strategy: {strategy.name}")
        engine = BacktestEngine(strategy, df)
        engine.run()
        metrics = engine.calculate_metrics()
        
        print("-" * 30)
        print(f"Performance Metrics ({strategy.name}):")
        for k, v in metrics.items():
            print(f"{k}: {v}")
        print("-" * 30)
        
        # Plot using new visualization module
        safe_name = strategy.name.replace(" ", "_").replace("(", "").replace(")", "").replace("/", "_")
        plot_filename = f"analysis_{safe_name}.png"
        
        try:
            plot_performance(engine, save_path=plot_filename)
        except Exception as e:
            print(f"Error plotting {strategy.name}: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    main()
