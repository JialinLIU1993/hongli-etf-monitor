from data_loader import fetch_etf_data
from strategies import BollingerBandsStrategy
import pandas as pd
import numpy as np

# Load data
df = fetch_etf_data("510880", start_date="20200101")

# Run Strategy (Standard Best Params)
strategy = BollingerBandsStrategy(window=40, num_std=2.1, staged=False)
results = strategy.generate_signals(df)

# Identify Signal Days (Day T)
# Buy: Signal 1 (0 -> 1)
# Sell: Signal -1 (1 -> 0)
# Note: In generate_signals, 'signal' is the diff of position.
# signal=1 means Buy at Close T.
# signal=-1 means Sell at Close T.

buy_dates = results[results['signal'] == 1].index
sell_dates = results[results['signal'] == -1].index

print(f"Total Buy Signals: {len(buy_dates)}")
print(f"Total Sell Signals: {len(sell_dates)}")

# Calculate Gaps for Buys
# Gap = (Open[T+1] - Close[T]) / Close[T]
buy_gaps = []
print("\n--- Buy Signal Gaps (Next Open vs Signal Close) ---")
print(f"{'Date':<12} | {'Close(T)':<8} | {'Open(T+1)':<9} | {'Gap %':<8}")
for t in buy_dates:
    loc = results.index.get_loc(t)
    if loc + 1 < len(results):
        t_next = results.index[loc+1]
        close_t = results.loc[t, 'close']
        open_t1 = results.loc[t_next, 'open']
        gap = (open_t1 - close_t) / close_t
        buy_gaps.append(gap)
        # Print first few
        if len(buy_gaps) <= 5:
            print(f"{t.strftime('%Y-%m-%d'):<12} | {close_t:<8.3f} | {open_t1:<9.3f} | {gap:<8.2%}")

avg_buy_gap = np.mean(buy_gaps) if buy_gaps else 0
print(f"AVERAGE BUY GAP: {avg_buy_gap:.4%}")
if avg_buy_gap < 0:
    print("=> RESULT: Gap Down. Next Open is CHEAPER (Better Entry).")
else:
    print("=> RESULT: Gap Up. Next Open is MORE EXPENSIVE (Worse Entry).")


# Calculate Gaps for Sells
sell_gaps = []
print("\n--- Sell Signal Gaps (Next Open vs Signal Close) ---")
print(f"{'Date':<12} | {'Close(T)':<8} | {'Open(T+1)':<9} | {'Gap %':<8}")
for t in sell_dates:
    loc = results.index.get_loc(t)
    if loc + 1 < len(results):
        t_next = results.index[loc+1]
        close_t = results.loc[t, 'close']
        open_t1 = results.loc[t_next, 'open']
        gap = (open_t1 - close_t) / close_t
        sell_gaps.append(gap)
        if len(sell_gaps) <= 5:
            print(f"{t.strftime('%Y-%m-%d'):<12} | {close_t:<8.3f} | {open_t1:<9.3f} | {gap:<8.2%}")

avg_sell_gap = np.mean(sell_gaps) if sell_gaps else 0
print(f"AVERAGE SELL GAP: {avg_sell_gap:.4%}")
if avg_sell_gap > 0:
    print("=> RESULT: Gap Up. Next Open is HIGHER (Better Exit).")
else:
    print("=> RESULT: Gap Down. Next Open is LOWER (Worse Exit).")

print("\n" + "="*50)
print("FINAL CONCLUSION:")
net_benefit = 0
if avg_buy_gap < 0: net_benefit += -avg_buy_gap # Saved money
else: net_benefit -= avg_buy_gap # Lost money

if avg_sell_gap > 0: net_benefit += avg_sell_gap # Made more
else: net_benefit -= -avg_sell_gap # Made less

print(f"Net Advantage of Next Day Trading: {net_benefit:.4%}")
if net_benefit > 0:
    print("Next Day Trading wins statistically.")
else:
    print("Same Day (Tail) Trading wins statistically.")
