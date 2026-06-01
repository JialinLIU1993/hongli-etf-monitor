
import sys
import os
import pandas as pd
import numpy as np

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from data_loader import fetch_etf_data

def calculate_bollinger_bands(df, window=40, num_std=2.1):
    df['ma'] = df['close'].rolling(window=window).mean()
    df['std'] = df['close'].rolling(window=window).std()
    df['upper_band'] = df['ma'] + (df['std'] * num_std)
    df['lower_band'] = df['ma'] - (df['std'] * num_std)
    return df

def main():
    print("Fetching latest data...")
    # Force update to ensure we have the absolute latest data
    df = fetch_etf_data(symbol="510880", adjust="qfq", force_update=True)
    
    if df.empty:
        print("Error: No data fetched.")
        return

    # Calculate indicators
    df = calculate_bollinger_bands(df, window=40, num_std=2.1)
    
    # Get the last row
    latest = df.iloc[-1]
    last_date = df.index[-1]
    
    print("\n" + "="*50)
    print(f"LATEST SIGNAL STATUS ({last_date.strftime('%Y-%m-%d')})")
    print("="*50)
    print(f"Latest Close Price: {latest['close']:.3f}")
    print(f"MA40 (Baseline):    {latest['ma']:.3f}")
    print("-" * 50)
    
    # Buy Points
    buy_threshold_1 = latest['lower_band']
    buy_threshold_2 = latest['lower_band'] * 0.98
    
    print(f"BUY SIGNAL (Lower Band): {buy_threshold_1:.3f}")
    print(f"  -> Buy 90% if Close < {buy_threshold_1:.3f}")
    print(f"  -> Current Distance: {(latest['close'] - buy_threshold_1) / buy_threshold_1:.2%}")
    
    print(f"ADD POSITION (Lower - 2%): {buy_threshold_2:.3f}")
    print(f"  -> Buy remaining 10% if Close < {buy_threshold_2:.3f}")
    
    print("-" * 50)
    
    # Sell Points
    sell_threshold_1 = latest['upper_band']
    sell_threshold_2 = latest['upper_band'] * 1.02
    
    print(f"SELL SIGNAL (Upper Band): {sell_threshold_1:.3f}")
    print(f"  -> Sell 10% if Close > {sell_threshold_1:.3f}")
    print(f"  -> Current Distance: {(latest['close'] - sell_threshold_1) / sell_threshold_1:.2%}")
    
    print(f"CLEAR POSITION (Upper + 2%): {sell_threshold_2:.3f}")
    print(f"  -> Sell remaining 90% if Close > {sell_threshold_2:.3f}")
    
    print("="*50)
    
    # Current State
    if latest['close'] < buy_threshold_2:
        print("CURRENT STATUS: STRONG BUY (Below -2% Threshold)")
    elif latest['close'] < buy_threshold_1:
        print("CURRENT STATUS: BUY (Below Lower Band)")
    elif latest['close'] > sell_threshold_2:
        print("CURRENT STATUS: STRONG SELL (Above +2% Threshold)")
    elif latest['close'] > sell_threshold_1:
        print("CURRENT STATUS: SELL (Above Upper Band)")
    else:
        print("CURRENT STATUS: HOLD / WAIT")
        
if __name__ == "__main__":
    main()
