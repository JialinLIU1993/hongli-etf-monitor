import matplotlib.pyplot as plt
import pandas as pd
import numpy as np

def plot_performance(engine, save_path=None):
    """
    Plots the performance of the strategy including:
    1. Price chart with indicators and buy/sell signals
    2. Equity curve (Strategy vs Benchmark)
    3. Drawdown curve
    """
    results = engine.results
    strategy_name = engine.strategy.name
    
    # Setup the figure with 3 subplots sharing x-axis
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(14, 12), sharex=True, gridspec_kw={'height_ratios': [3, 2, 1]})
    plt.subplots_adjust(hspace=0.05)
    
    # --- Subplot 1: Price & Indicators ---
    ax1.plot(results.index, results['close'], label='Price', color='black', alpha=0.6, linewidth=1)
    
    # Dynamic Indicator Plotting
    if 'short_mavg' in results.columns and 'long_mavg' in results.columns:
        ax1.plot(results.index, results['short_mavg'], label='Short MA', color='orange', alpha=0.8, linewidth=1)
        ax1.plot(results.index, results['long_mavg'], label='Long MA', color='blue', alpha=0.8, linewidth=1)
    
    if 'upper_band' in results.columns and 'lower_band' in results.columns:
        ax1.plot(results.index, results['upper_band'], label='Upper Band', color='green', alpha=0.5, linestyle='--')
        ax1.plot(results.index, results['lower_band'], label='Lower Band', color='green', alpha=0.5, linestyle='--')
        ax1.fill_between(results.index, results['upper_band'], results['lower_band'], color='green', alpha=0.1)
        if 'ma' in results.columns:
             ax1.plot(results.index, results['ma'], label='MA', color='green', alpha=0.6, linewidth=1)

    # Plot Signals
    # Buy Signals
    buys = results[results['signal'] > 0]
    ax1.scatter(buys.index, results.loc[buys.index, 'close'], marker='^', color='green', label='Buy Signal', s=100, zorder=5)
    
    # Sell Signals
    sells = results[results['signal'] < 0]
    ax1.scatter(sells.index, results.loc[sells.index, 'close'], marker='v', color='red', label='Sell Signal', s=100, zorder=5)
    
    ax1.set_title(f'{strategy_name} - Analysis', fontsize=14, fontweight='bold')
    ax1.set_ylabel('Price')
    ax1.legend(loc='upper left')
    ax1.grid(True, alpha=0.3)

    # --- Subplot 2: Equity Curve ---
    ax2.plot(results.index, results['cumulative_market_return'] * 100, label='Benchmark (Buy & Hold)', color='gray', alpha=0.7)
    ax2.plot(results.index, results['cumulative_strategy_return'] * 100, label='Strategy', color='blue', linewidth=2)
    
    # Fill area under strategy
    ax2.fill_between(results.index, results['cumulative_strategy_return'] * 100, 100, where=(results['cumulative_strategy_return'] >= 1), color='blue', alpha=0.1)
    ax2.fill_between(results.index, results['cumulative_strategy_return'] * 100, 100, where=(results['cumulative_strategy_return'] < 1), color='red', alpha=0.1)
    
    ax2.set_ylabel('Return (%)')
    ax2.legend(loc='upper left')
    ax2.grid(True, alpha=0.3)
    
    # --- Subplot 3: Drawdown ---
    # Calculate drawdown if not present (though engine calculates metrics, it might not store daily drawdown series in df)
    # Re-calculate for plotting
    rolling_max = results['equity'].cummax().clip(lower=engine.initial_capital)
    drawdown = (results['equity'] - rolling_max) / rolling_max
    
    ax3.fill_between(results.index, drawdown * 100, 0, color='red', alpha=0.3)
    ax3.plot(results.index, drawdown * 100, color='red', linewidth=1)
    ax3.set_ylabel('Drawdown (%)')
    ax3.set_xlabel('Date')
    ax3.grid(True, alpha=0.3)
    
    # Format x-axis date
    fig.autofmt_xdate()
    
    if save_path:
        plt.savefig(save_path, bbox_inches='tight')
        print(f"Enhanced plot saved to {save_path}")
    else:
        plt.show()
        
    plt.close()
