from data_loader import fetch_etf_data
import pandas as pd

# Load data (force unadjusted and adjusted comparison)
# Note: fetch_etf_data defaults to 'qfq'.
df_adj = fetch_etf_data("510880", start_date="20250101", end_date="20250110", adjust="qfq")
# We can't easily fetch unadjusted without modifying the loader or calling akshare directly, 
# but we can infer from the values.

print("Sample Data (First 5 days of 2025):")
print(df_adj[['open', 'close', 'high', 'low']].head())

print("\nSpecific Trade Example Verification:")
# Pick a random day T and T+1
t_date = df_adj.index[0]
t_plus_1_date = df_adj.index[1]

close_t = df_adj.loc[t_date, 'close']
open_t1 = df_adj.loc[t_plus_1_date, 'open']

print(f"Day T ({t_date.date()}): Close = {close_t:.3f}")
print(f"Day T+1 ({t_plus_1_date.date()}): Open = {open_t1:.3f}")

print("\n--- Execution Logic Confirmation ---")
print(f"1. Tail Execution (Close T): Buys at {close_t:.3f}")
print(f"2. Next Open Execution (Open T+1): Buys at {open_t1:.3f}")

gap = (open_t1 - close_t) / close_t
print(f"\nOvernight Gap (Profit/Loss difference): {gap:.2%}")
if gap > 0:
    print("Result: Next Day Open is HIGHER (Costlier). Tail Execution wins.")
else:
    print("Result: Next Day Open is LOWER (Cheaper). Next Open wins.")
