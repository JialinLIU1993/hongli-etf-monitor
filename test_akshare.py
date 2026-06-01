import akshare as ak
import pandas as pd

try:
    # 尝试获取股息率数据 (中证红利 000922 或者直接红利 ETF 的跟踪指数)
    # 中证红利指数的历史 PE/PB/股息率
    # ak.stock_zh_index_value_csindex(symbol="000922")
    # 也可以看看上证红利 000015
    print("Fetching index value...")
    df_index = ak.stock_zh_index_value_csindex(symbol="000922")
    print(df_index.tail())
    
    # 尝试获取十年期国债收益率
    # ak.bond_zh_us_rate()
    print("Fetching Treasury rate...")
    df_bond = ak.bond_zh_us_rate()
    print(df_bond.tail())
    
except Exception as e:
    print(f"Error: {e}")
