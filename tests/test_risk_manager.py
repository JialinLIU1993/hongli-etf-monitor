"""单元测试: RiskManager 风控模块"""
import pytest
import pandas as pd
import numpy as np
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.risk_manager import RiskManager


def _make_signals_df(closes, positions, ma=None):
    """构造带有 close, ma, position 列的 DataFrame（模拟 generate_signals 输出）。"""
    n = len(closes)
    dates = pd.bdate_range('2023-01-01', periods=n)
    if ma is None:
        ma = pd.Series(closes).rolling(20, min_periods=1).mean().values
    df = pd.DataFrame({
        'close': closes,
        'open': closes,
        'high': [c * 1.01 for c in closes],
        'low': [c * 0.99 for c in closes],
        'ma': ma,
        'position': positions,
        'signal': [0.0] * n,
        'volume': [1000000] * n,
    }, index=dates)
    return df


class TestRiskManagerInit:
    """初始化测试。"""

    def test_default_config(self):
        rm = RiskManager()
        assert rm.max_drawdown_enabled is True
        assert rm.trailing_stop_enabled is True
        assert rm.time_stop_enabled is False
        assert rm.cooldown_days == 5

    def test_custom_config(self):
        rm = RiskManager(max_drawdown_threshold=-0.05, cooldown_days=10)
        assert rm.max_drawdown_threshold == -0.05
        assert rm.cooldown_days == 10


class TestMaxDrawdownStop:
    """最大回撤止损测试。"""

    def test_triggers_on_large_drawdown(self):
        """权益大幅回撤时应清仓。"""
        # 先涨后暴跌 20%
        closes = [1.0] * 10 + [1.0 - 0.025 * i for i in range(1, 11)]
        positions = [1.0] * 20
        df = _make_signals_df(closes, positions)

        rm = RiskManager(
            max_drawdown_enabled=True, max_drawdown_threshold=-0.10,
            trailing_stop_enabled=False, time_stop_enabled=False, cooldown_days=0
        )
        result = rm.apply(df, initial_capital=100000)
        # 暴跌后应有仓位被强制清零
        assert result['position'].iloc[-1] == 0.0, "大幅回撤后应清仓"
        assert len(rm.triggers) > 0, "应记录触发事件"
        assert rm.triggers[0]['type'] == '最大回撤止损'

    def test_no_trigger_within_threshold(self):
        """小幅波动不应触发。"""
        closes = [1.0 + 0.001 * i for i in range(30)]
        positions = [1.0] * 30
        df = _make_signals_df(closes, positions)

        rm = RiskManager(
            max_drawdown_enabled=True, max_drawdown_threshold=-0.10,
            trailing_stop_enabled=False, time_stop_enabled=False
        )
        rm.apply(df, initial_capital=100000)
        assert len(rm.triggers) == 0, "小幅波动不应触发止损"

    def test_disabled(self):
        """禁用时不应触发。"""
        closes = [1.0] * 10 + [0.5] * 10
        positions = [1.0] * 20
        df = _make_signals_df(closes, positions)

        rm = RiskManager(
            max_drawdown_enabled=False,
            trailing_stop_enabled=False, time_stop_enabled=False
        )
        rm.apply(df, initial_capital=100000)
        dd_triggers = [t for t in rm.triggers if t['type'] == '最大回撤止损']
        assert len(dd_triggers) == 0


class TestTrailingStop:
    """移动止损测试。"""

    def test_triggers_on_price_drop_from_peak(self):
        """价格从高点回撤超过阈值应清仓。"""
        # 持仓期间先涨到 1.2，再跌到 1.0（回撤 ~16%）
        closes = [1.0] * 5 + [1.0 + 0.04 * i for i in range(1, 6)] + [1.2 - 0.04 * i for i in range(1, 6)]
        positions = [1.0] * len(closes)
        df = _make_signals_df(closes, positions)

        rm = RiskManager(
            max_drawdown_enabled=False,
            trailing_stop_enabled=True, trailing_stop_threshold=-0.08,
            time_stop_enabled=False, cooldown_days=0
        )
        result = rm.apply(df, initial_capital=100000)
        trail_triggers = [t for t in rm.triggers if t['type'] == '移动止损']
        assert len(trail_triggers) > 0, "价格大幅回撤应触发移动止损"


class TestTimeStop:
    """时间止损测试。"""

    def test_reduces_position_after_days(self):
        """持仓超天数且低于中轨时应减仓。"""
        n = 80
        closes = [1.0] * n
        # MA 设为高于 close，使得 holding_days 持续累加
        ma = [1.1] * n
        positions = [1.0] * n
        df = _make_signals_df(closes, positions, ma=ma)

        rm = RiskManager(
            max_drawdown_enabled=False, trailing_stop_enabled=False,
            time_stop_enabled=True, time_stop_days=60, time_stop_reduce_to=0.5,
            cooldown_days=0
        )
        result = rm.apply(df, initial_capital=100000)
        time_triggers = [t for t in rm.triggers if t['type'] == '时间止损']
        assert len(time_triggers) > 0, "持仓超天数且低于中轨应触发时间止损"
        # 减仓后仓位应为 0.5
        trigger_idx = df.index.get_loc(time_triggers[0]['date'])
        assert result['position'].iloc[trigger_idx] == pytest.approx(0.5)

    def test_no_trigger_above_ma(self):
        """价格在中轨上方时不应触发。"""
        n = 80
        closes = [1.5] * n  # 远高于 MA
        ma = [1.0] * n
        positions = [1.0] * n
        df = _make_signals_df(closes, positions, ma=ma)

        rm = RiskManager(
            max_drawdown_enabled=False, trailing_stop_enabled=False,
            time_stop_enabled=True, time_stop_days=60, time_stop_reduce_to=0.5
        )
        rm.apply(df, initial_capital=100000)
        assert len(rm.triggers) == 0, "价格高于中轨不应触发时间止损"


class TestCooldown:
    """冷却期测试。"""

    def test_cooldown_enforced(self):
        """止损触发后冷却期内仓位应为 0。"""
        # 构造暴跌触发止损的数据
        closes = [1.0] * 10 + [1.0 - 0.03 * i for i in range(1, 11)]
        positions = [1.0] * 20
        df = _make_signals_df(closes, positions)

        rm = RiskManager(
            max_drawdown_enabled=True, max_drawdown_threshold=-0.10,
            trailing_stop_enabled=False, time_stop_enabled=False,
            cooldown_days=3
        )
        result = rm.apply(df, initial_capital=100000)

        if rm.triggers:
            trigger_date = rm.triggers[0]['date']
            trigger_idx = df.index.get_loc(trigger_date)
            # 冷却期内（含触发当天）应为 0
            for offset in range(1, min(4, len(df) - trigger_idx)):
                assert result['position'].iloc[trigger_idx + offset] == 0.0, \
                    f"冷却期第 {offset} 天应为空仓"


class TestTriggerSummary:
    """触发摘要测试。"""

    def test_empty_summary(self):
        rm = RiskManager()
        summary = rm.get_trigger_summary()
        assert summary['total_count'] == 0
        assert summary['by_type'] == {}
        assert summary['last_trigger'] is None

    def test_summary_after_triggers(self):
        closes = [1.0] * 10 + [0.5] * 10
        positions = [1.0] * 20
        df = _make_signals_df(closes, positions)

        rm = RiskManager(
            max_drawdown_enabled=True, max_drawdown_threshold=-0.10,
            trailing_stop_enabled=False, time_stop_enabled=False, cooldown_days=0
        )
        rm.apply(df, initial_capital=100000)
        summary = rm.get_trigger_summary()
        assert summary['total_count'] > 0
        assert '最大回撤止损' in summary['by_type']
        assert summary['last_trigger'] is not None
        assert 'date' in summary['last_trigger']
        assert 'detail' in summary['last_trigger']
