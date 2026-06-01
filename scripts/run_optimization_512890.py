from optimize import optimize_bollinger
from data_loader import fetch_etf_data
import seaborn as sns
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np

def main():
    symbol = "512890"
    print(f"Fetching data for {symbol}...")
    df = fetch_etf_data(symbol, start_date="20200101")
    
    if df.empty:
        print("No data found.")
        return

    # Run optimization
    print("Running optimization (this may take a while)...")
    results_df = optimize_bollinger(df, mode='standard')
    
    # Save raw results
    results_df.to_csv(f"optimization_results_{symbol}.csv", index=False)
    
    # Pivot for heatmap
    # Pivot: Index=Window, Columns=NumStd, Values=Total Return
    heatmap_data = results_df.pivot(index="window", columns="num_std", values="Total Return")
    
    # Plot
    plt.figure(figsize=(14, 10))
    sns.heatmap(heatmap_data, annot=False, cmap="RdYlGn", center=0, cbar_kws={'label': 'Total Return'})
    plt.title(f"Bollinger Bands Strategy Optimization for {symbol}\n(Total Return)", fontsize=16)
    plt.xlabel("Number of Std Devs", fontsize=12)
    plt.ylabel("Window Size (MA Period)", fontsize=12)
    
    # Invert Y axis so small windows are at the bottom (optional, but standard usually has small at top. 
    # Let's keep default pandas pivot order: Window 10 at top, 90 at bottom? 
    # Pandas sorts index ascending. Seaborn heatmap plots index 0 at top. 
    # So Window 10 is at top. 
    # Let's invert y axis to have 10 at bottom if we want "graph" style, but matrix style is usually top-down.
    # I'll keep default but maybe make it clearer.
    plt.gca().invert_yaxis() # Put small windows at bottom, large at top.
    
    # Save plot
    output_file = f"heatmap_{symbol}_return.png"
    plt.savefig(output_file)
    print(f"Heatmap saved to {output_file}")
    
    # Find best
    best = results_df.sort_values(by='Total Return', ascending=False).iloc[0]
    print("\n" + "="*50)
    print(f"🏆 BEST PARAMETERS FOR {symbol}:")
    print(f"Window: {best['window']}")
    print(f"Std Dev: {best['num_std']}")
    print(f"Total Return: {best['Total Return']:.2%}")
    print("="*50)

if __name__ == "__main__":
    main()
