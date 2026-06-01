"""
自适应布林带策略 — 根据市场波动率状态动态调整参数

核心思路:
  1. 用短期/长期 ATR 比值检测波动率状态（高波/中波/低波）
  2. 根据波动率状态自动调整布林带 window 和 num_std
  3. 保留原 BollingerBandsStrategy 的全部交易逻辑（分批/全仓/止损）
"""
import pandas as pd
import numpy as np
from src.strategies import BollingerBandsStrategy


# ----- 波动率状态参数映射 -----
# 高波动 → 拉宽布林带（避免频繁触发）
# 低波动 → 收窄布林带（捕捉小幅波动机会）
REGIME_PARAMS = {
    'high': {'window_mult': 1.25, 'std_mult': 1.20, 'label': '🔴 高波动'},
    'mid':  {'window_mult': 1.00, 'std_mult': 1.00, 'label': '🟡 中波动'},
    'low':  {'window_mult': 0.80, 'std_mult': 0.85, 'label': '🟢 低波动'},
}


def detect_volatility_regime(df, short_window=10, long_window=60,
                              high_threshold=1.3, low_threshold=0.7):
    """
    检测每日的波动率状态。

    使用 ATR（Average True Range）的短/长期比值:
      - ratio > high_threshold → 高波动
      - ratio < low_threshold  → 低波动
      - 其他                   → 中波动

    返回:
        pd.Series: 索引与 df 一致，值为 'high' / 'mid' / 'low'
    """
    high = df['high']
    low = df['low']
    prev_close = df['close'].shift(1)

    # True Range
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)

    atr_short = tr.rolling(short_window, min_periods=1).mean()
    atr_long = tr.rolling(long_window, min_periods=1).mean()

    ratio = atr_short / atr_long.replace(0, np.nan)
    ratio = ratio.fillna(1.0)

    regime = pd.Series('mid', index=df.index)
    regime[ratio > high_threshold] = 'high'
    regime[ratio < low_threshold] = 'low'

    return regime


class AdaptiveBollingerStrategy(BollingerBandsStrategy):
    """
    自适应布林带策略。

    继承 BollingerBandsStrategy，在 generate_signals 前
    根据波动率状态动态调整 window 和 num_std。
    """

    def __init__(self, base_window=40, base_std=2.1,
                 staged=True, first_batch_pct=0.9,
                 vol_short=10, vol_long=60,
                 high_thresh=1.3, low_thresh=0.7,
                 **kwargs):
        super().__init__(
            window=base_window, num_std=base_std,
            staged=staged, first_batch_pct=first_batch_pct,
            **kwargs
        )
        self.name = f"Adaptive Bollinger ({base_window}, {base_std})"
        self.base_window = base_window
        self.base_std = base_std
        self.vol_short = vol_short
        self.vol_long = vol_long
        self.high_thresh = high_thresh
        self.low_thresh = low_thresh

        # 记录状态供前端展示
        self.regime_series = None
        self.param_log = []

    def generate_signals(self, df):
        """
        按区间切换参数并生成信号。

        1. 检测波动率状态
        2. 将数据按连续相同状态分段
        3. 每段用对应参数跑布林带策略
        4. 拼接结果
        """
        regime = detect_volatility_regime(
            df, self.vol_short, self.vol_long,
            self.high_thresh, self.low_thresh
        )
        self.regime_series = regime

        # 分段处理：找到 regime 切换的断点
        regime_groups = (regime != regime.shift()).cumsum()
        segments = []
        self.param_log = []
        carry_position = 0.0  # 上一段最后仓位

        for group_id, group_df in df.groupby(regime_groups, sort=False):
            current_regime = regime.loc[group_df.index[0]]
            params = REGIME_PARAMS[current_regime]

            # 动态调整参数
            adj_window = max(5, int(self.base_window * params['window_mult']))
            adj_std = self.base_std * params['std_mult']

            # 记录参数变化
            self.param_log.append({
                'start': group_df.index[0],
                'end': group_df.index[-1],
                'regime': current_regime,
                'label': params['label'],
                'window': adj_window,
                'num_std': round(adj_std, 2),
                'days': len(group_df),
            })

            # 用调整后的参数跑策略
            # 需要足够的回看数据 → 从 df 中取更长的切片
            lookback = adj_window * 2
            start_idx = max(0, df.index.get_loc(group_df.index[0]) - lookback)
            extended_df = df.iloc[start_idx:df.index.get_loc(group_df.index[-1]) + 1].copy()

            # 临时修改参数
            self.window = adj_window
            self.num_std = adj_std

            result = super().generate_signals(extended_df)

            # 只取当前 segment 对应的行
            segment_result = result.loc[group_df.index]
            segments.append(segment_result)

        # 恢复原始参数
        self.window = self.base_window
        self.num_std = self.base_std

        # 拼接所有段
        combined = pd.concat(segments)
        combined = combined.loc[df.index]  # 确保顺序

        return combined

    def get_regime_summary(self):
        """返回波动率状态统计摘要。"""
        if not self.param_log:
            return {}
        total_days = sum(p['days'] for p in self.param_log)
        by_regime = {}
        for p in self.param_log:
            r = p['regime']
            if r not in by_regime:
                by_regime[r] = {'days': 0, 'segments': 0}
            by_regime[r]['days'] += p['days']
            by_regime[r]['segments'] += 1

        return {
            'total_days': total_days,
            'by_regime': {
                r: {
                    'label': REGIME_PARAMS[r]['label'],
                    'days': v['days'],
                    'pct': v['days'] / total_days,
                    'segments': v['segments'],
                }
                for r, v in by_regime.items()
            },
            'current_regime': self.param_log[-1] if self.param_log else None,
        }
