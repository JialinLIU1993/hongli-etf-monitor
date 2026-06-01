"""
风控管理模块 - RiskManager

提供三种独立的止损机制：
1. 最大回撤止损：权益从高点回撤超过阈值时强制清仓
2. 移动止损：持仓浮亏超过阈值时强制清仓
3. 时间止损：持仓超过 N 天价格仍低于中轨时减仓
"""

import pandas as pd
import numpy as np


class RiskManager:
    def __init__(
        self,
        # 最大回撤止损
        max_drawdown_enabled=True,
        max_drawdown_threshold=-0.10,  # -10%
        # 移动止损（从持仓最高价回撤）
        trailing_stop_enabled=True,
        trailing_stop_threshold=-0.08,  # -8%
        # 时间止损
        time_stop_enabled=False,
        time_stop_days=60,
        time_stop_reduce_to=0.5,  # 减仓至 50%
        # 冷却期
        cooldown_days=5,
    ):
        self.max_drawdown_enabled = max_drawdown_enabled
        self.max_drawdown_threshold = max_drawdown_threshold

        self.trailing_stop_enabled = trailing_stop_enabled
        self.trailing_stop_threshold = trailing_stop_threshold

        self.time_stop_enabled = time_stop_enabled
        self.time_stop_days = time_stop_days
        self.time_stop_reduce_to = time_stop_reduce_to

        self.cooldown_days = cooldown_days

        # 触发记录（供前端展示）
        self.triggers = []

    def apply(self, df, initial_capital):
        """
        在策略信号生成后、收益计算前调用。
        遍历 df 的每一行，根据风控规则覆盖 position 列。

        Args:
            df: 包含 'close', 'ma', 'position' 列的 DataFrame（来自策略 generate_signals）
            initial_capital: 初始资金

        Returns:
            df: 修改后的 DataFrame（position 列可能被覆盖）
        """
        self.triggers = []

        positions = df['position'].values.copy()
        closes = df['close'].values
        mas = df['ma'].values if 'ma' in df.columns else np.full(len(df), np.nan)
        dates = df.index

        # 模拟权益曲线（简化版：仅用收盘价变化估算）
        equity = initial_capital
        peak_equity = initial_capital
        entry_price = 0.0       # 最近一次建仓的入场价
        holding_peak = 0.0      # 持仓期间最高价
        holding_days = 0        # 持仓天数（价格低于中轨的天数）
        cooldown_remaining = 0  # 冷却期剩余天数

        prev_position = 0.0
        prev_close = closes[0] if len(closes) > 0 else 0.0

        for i in range(len(df)):
            close = closes[i]
            ma = mas[i]
            original_position = positions[i]

            # --- 冷却期处理 ---
            if cooldown_remaining > 0:
                cooldown_remaining -= 1
                positions[i] = 0.0
                # 更新权益（空仓期间权益不变）
                if i > 0:
                    pass  # equity stays the same when flat
                prev_position = 0.0
                prev_close = close
                continue

            # --- 更新权益 ---
            if i > 0 and prev_position > 0:
                daily_return = (close - prev_close) / prev_close if prev_close > 0 else 0
                equity *= (1 + daily_return * prev_position)

            # --- 检查是否新建仓 ---
            if prev_position == 0 and original_position > 0:
                entry_price = close
                holding_peak = close
                holding_days = 0

            # --- 更新持仓追踪 ---
            if original_position > 0:
                holding_peak = max(holding_peak, close)
                if not np.isnan(ma) and close < ma:
                    holding_days += 1
                else:
                    holding_days = 0  # 重置：价格回到中轨以上

            # --- 风控检查 ---
            triggered = False
            trigger_type = ""

            # 1. 最大回撤止损
            if self.max_drawdown_enabled and original_position > 0:
                peak_equity = max(peak_equity, equity)
                current_drawdown = (equity - peak_equity) / peak_equity if peak_equity > 0 else 0
                if current_drawdown < self.max_drawdown_threshold:
                    triggered = True
                    trigger_type = "最大回撤止损"

            # 2. 移动止损（从持仓最高价回撤）
            if not triggered and self.trailing_stop_enabled and original_position > 0:
                if holding_peak > 0:
                    trailing_dd = (close - holding_peak) / holding_peak
                    if trailing_dd < self.trailing_stop_threshold:
                        triggered = True
                        trigger_type = "移动止损"

            # 3. 时间止损
            if not triggered and self.time_stop_enabled and original_position > 0:
                if holding_days >= self.time_stop_days:
                    # 时间止损不完全清仓，减仓至目标比例
                    if original_position > self.time_stop_reduce_to:
                        positions[i] = self.time_stop_reduce_to
                        self.triggers.append({
                            'date': dates[i],
                            'type': '时间止损',
                            'detail': f'持仓 {holding_days} 天低于中轨，减仓至 {self.time_stop_reduce_to:.0%}'
                        })
                        holding_days = 0  # 重置计时

            # --- 执行止损（回撤/移动止损 → 清仓） ---
            if triggered:
                positions[i] = 0.0
                cooldown_remaining = self.cooldown_days
                self.triggers.append({
                    'date': dates[i],
                    'type': trigger_type,
                    'detail': self._format_detail(trigger_type, equity, peak_equity, close, holding_peak)
                })
                # 重置追踪变量
                entry_price = 0.0
                holding_peak = 0.0
                holding_days = 0

            prev_position = positions[i]
            prev_close = close

        df['position'] = positions

        # 重新计算 signal 列（基于新的 position）
        df['signal'] = 0.0
        pos_diff = df['position'].diff()
        df.loc[pos_diff > 0, 'signal'] = 1.0
        df.loc[pos_diff < 0, 'signal'] = -1.0

        return df

    def _format_detail(self, trigger_type, equity, peak_equity, close, holding_peak):
        if trigger_type == "最大回撤止损":
            dd = (equity - peak_equity) / peak_equity * 100 if peak_equity > 0 else 0
            return f"权益回撤 {dd:.1f}%，触发清仓"
        elif trigger_type == "移动止损":
            dd = (close - holding_peak) / holding_peak * 100 if holding_peak > 0 else 0
            return f"价格从高点 ¥{holding_peak:.3f} 回撤 {dd:.1f}% 至 ¥{close:.3f}"
        return ""

    def get_trigger_summary(self):
        """返回风控触发的统计摘要"""
        if not self.triggers:
            return {
                'total_count': 0,
                'by_type': {},
                'last_trigger': None
            }

        by_type = {}
        for t in self.triggers:
            tp = t['type']
            by_type[tp] = by_type.get(tp, 0) + 1

        return {
            'total_count': len(self.triggers),
            'by_type': by_type,
            'last_trigger': self.triggers[-1]
        }
