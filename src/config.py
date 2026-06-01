"""
全局默认参数配置。
侧边栏 UI 的默认值、回测引擎参数等统一在此管理。
"""

# ── 数据 ──
DATA_DIR = 'data'
DEFAULT_SYMBOLS = ['510880', '512890']
DEFAULT_ADJUST = 'qfq'

# ── 日期 ──
DEFAULT_START_YEAR = 2020

# ── 组合 ──
DEFAULT_INITIAL_CAPITAL = 100_000
DEFAULT_WEIGHT_510880 = 0.7
DEFAULT_COMMISSION = 0.0003
DEFAULT_SLIPPAGE = 0.0002       # 单边滑点（万分之二）
DEFAULT_EXECUTION_TYPE = 'close'

# ── 无风险利率（年化） ──
RISK_FREE_RATE = 0.025           # 2.5%, 用于 Sharpe / Cash Enhanced

# ── 布林带策略默认参数 ──
BOLLINGER_510880 = {
    'window': 40,
    'num_std': 2.1,
    'first_batch_pct': 0.9,
}
BOLLINGER_512890 = {
    'window': 50,
    'num_std': 2.1,
    'first_batch_pct': 1.0,
}

# ── 风控 ──
RISK_CONTROL = {
    'max_drawdown_enabled': True,
    'max_drawdown_threshold': -0.10,
    'trailing_stop_enabled': True,
    'trailing_stop_threshold': -0.08,
    'time_stop_enabled': False,
    'time_stop_days': 60,
    'time_stop_reduce_to': 0.5,
    'cooldown_days': 5,
}

# ── 自适应策略 ──
ADAPTIVE = {
    'vol_short': 10,
    'vol_long': 60,
    'high_thresh': 1.3,
    'low_thresh': 0.7,
}

# ── 金字塔加仓 ──
PYRAMID = {
    'enabled': False,
    'levels': [0.01, 0.02, 0.03],   # 跌破下轨 1%/2%/3% 逐步加仓
    'sizes': [0.3, 0.3, 0.4],       # 各级仓位
}
