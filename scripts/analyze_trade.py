from data_loader import fetch_etf_data
from strategies import BollingerBandsStrategy
import pandas as pd

# Load data
df = fetch_etf_data("510880", start_date="20250101", end_date="20251231")

# Run Strategy with Optimized Params
# Window=40, Std=2.1 (from previous best results)
# Assuming 'All-in' mode as that's the default high-performer
strategy = BollingerBandsStrategy(window=40, num_std=2.1, staged=False)
results = strategy.generate_signals(df)

# Filter for the period in question
mask = (results.index >= "2025-09-01") & (results.index <= "2025-11-30")
period_data = results.loc[mask]

print(f"{'Date':<12} | {'Close':<8} | {'Upper':<8} | {'Lower':<8} | {'Signal':<6} | {'Dist to Upper'}")
print("-" * 70)

max_close = 0
max_close_date = None

for date, row in period_data.iterrows():
    date_str = date.strftime("%Y-%m-%d")
    close = row['close']
    upper = row['upper_band']
    lower = row['lower_band']
    signal = row['signal']
    dist = upper - close
    
    if close > max_close:
        max_close = close
        max_close_date = date_str
    
    # Only print significant days (Buy/Sell or Near Misses)
    # Near miss = within 1% of upper band
    is_near = (upper - close) / close < 0.01
    
    if signal != 0 or is_near or date_str in ["2025-09-01", "2025-11-30"] or close == max_close:
        print(f"{date_str:<12} | {close:<8.3f} | {upper:<8.3f} | {lower:<8.3f} | {signal:<6.1f} | {dist:<.3f}")

print("-" * 70)
print(f"Max Price in Period: {max_close} on {max_close_date}")
