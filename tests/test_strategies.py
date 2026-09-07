"""单元测试: BollingerBandsStrategy 信号生成"""
import pytest
import pandas as pd
import numpy as np
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.strategies import BollingerBandsStrategy


def _make_df(prices, volumes=None):
    """构造测试用 DataFrame。"""
    n = len(prices)
    dates = pd.bdate_range('2023-01-01', periods=n)
    df = pd.DataFrame({
        'open': prices,
        'high': [p * 1.01 for p in prices],
        'low': [p * 0.99 for p in prices],
        'close': prices,
        'volume': volumes or [1000000] * n,
    }, index=dates)
    return df


class TestBollingerBandsStrategy:
    """布林带策略测试组。"""

    def test_output_columns(self):
        """generate_signals 应输出必须的列。"""
        prices = [1.0 + 0.01 * i for i in range(60)]
        df = _make_df(prices)
        strat = BollingerBandsStrategy(window=20, num_std=2.0)
        result = strat.generate_signals(df)
        for col in ['ma', 'upper_band', 'lower_band', 'signal', 'position']:
            assert col in result.columns, f"缺少列: {col}"

    def test_position_range(self):
        """仓位应在 [0, 1] 范围内。"""
        np.random.seed(42)
        prices = (1 + np.random.randn(100).cumsum() * 0.01 + 1).tolist()
        df = _make_df(prices)
        strat = BollingerBandsStrategy(window=20, num_std=2.0)
        result = strat.generate_signals(df)
        assert result['position'].min() >= 0.0
        assert result['position'].max() <= 1.0

    def test_buy_signal_below_lower_band(self):
        """价格跌破下轨时应产生买入信号（仓位 > 0）。"""
        # 构造先稳定后急跌的价格序列
        prices = [1.0] * 40 + [1.0 - 0.02 * i for i in range(1, 21)]
        df = _make_df(prices)
        strat = BollingerBandsStrategy(window=20, num_std=2.0, staged=False)
        result = strat.generate_signals(df)
        # 后段应有非零仓位
        tail_positions = result['position'].iloc[-10:]
        assert tail_positions.max() > 0, "价格跌破下轨后应建仓"

    def test_sell_signal_above_upper_band(self):
        """价格突破上轨时应产生卖出信号。"""
        # 先跌破建仓，再急涨至上轨
        prices = [1.0] * 30 + [0.8] * 10 + [0.8 + 0.05 * i for i in range(1, 21)]
        df = _make_df(prices)
        strat = BollingerBandsStrategy(window=20, num_std=2.0, staged=False)
        result = strat.generate_signals(df)
        # 在急涨后段，仓位应有减到 0 的情况
        tail_positions = result['position'].iloc[-5:]
        assert tail_positions.min() == 0.0, "价格突破上轨后应清仓"

    def test_staged_vs_allin(self):
        """分批和全仓模式应产生不同的仓位序列。"""
        np.random.seed(99)
        prices = (1 + np.random.randn(120).cumsum() * 0.008 + 1).tolist()
        df = _make_df(prices)

        strat_staged = BollingerBandsStrategy(window=20, num_std=2.0, staged=True, first_batch_pct=0.5)
        result_staged = strat_staged.generate_signals(df)

        strat_allin = BollingerBandsStrategy(window=20, num_std=2.0, staged=False)
        result_allin = strat_allin.generate_signals(df)

        # 两种模式应至少产生一些不同的仓位值
        diff_count = (result_staged['position'] != result_allin['position']).sum()
        # 如果有交易发生，仓位序列不应完全一致
        if result_staged['position'].sum() > 0 and result_allin['position'].sum() > 0:
            assert diff_count > 0, "分批和全仓模式应产生不同仓位"

    def test_empty_df(self):
        """空 DataFrame 不应崩溃。"""
        df = pd.DataFrame(columns=['open', 'high', 'low', 'close', 'volume'])
        strat = BollingerBandsStrategy(window=20, num_std=2.0)
        result = strat.generate_signals(df)
        assert len(result) == 0

    def test_short_df(self):
        """数据不足 window 长度时不应崩溃。"""
        prices = [1.0] * 5
        df = _make_df(prices)
        strat = BollingerBandsStrategy(window=20, num_std=2.0)
        result = strat.generate_signals(df)
        assert result['position'].sum() == 0, "数据不足时不应有仓位"


def test_reversal_respects_minimum_position_at_start_and_after_sell():
    df = _make_df([100.0] * 8 + [80.0, 100.0, 120.0, 100.0])
    strategy = BollingerBandsStrategy(window=5, num_std=1, staged=False,
                                      confirm_reversal=True, min_position=0.2)
    result = strategy.generate_signals(df)
    assert result['position'].iloc[0] == pytest.approx(0.2)
    assert result['signal'].iloc[0] == pytest.approx(0.2)
    assert result['position'].iloc[9] == pytest.approx(1.0)
    assert result['position'].iloc[11] == pytest.approx(0.2)
    assert result['signal'].notna().all()


@pytest.mark.parametrize('kwargs', [
    {},
    {'staged': False},
    {'staged': False, 'confirm_reversal': True},
    {'pyramid_levels': [0.01, 0.03], 'pyramid_sizes': [0.4, 0.6]},
])
def test_bollinger_signals_do_not_change_when_future_prices_are_added(kwargs):
    rng = np.random.default_rng(12)
    df = _make_df((100 * np.exp(rng.normal(0, 0.035, 150).cumsum())).tolist())
    original = df.copy(deep=True)
    strategy = BollingerBandsStrategy(window=10, num_std=1.5, **kwargs)
    prefix = strategy.generate_signals(df.iloc[:100])
    full = strategy.generate_signals(df)
    pd.testing.assert_frame_equal(prefix, full.iloc[:100])
    pd.testing.assert_frame_equal(df, original)
