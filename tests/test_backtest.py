"""单元测试: BacktestEngine 回测引擎"""
import pytest
import pandas as pd
import numpy as np
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.strategies import BollingerBandsStrategy
from src.backtest import BacktestEngine


def _make_df(n=200, seed=42):
    """构造模拟价格数据。"""
    np.random.seed(seed)
    dates = pd.bdate_range('2022-01-01', periods=n)
    prices = (1 + np.random.randn(n).cumsum() * 0.005 + 1)
    df = pd.DataFrame({
        'open': prices * (1 - np.random.rand(n) * 0.005),
        'high': prices * (1 + np.random.rand(n) * 0.01),
        'low': prices * (1 - np.random.rand(n) * 0.01),
        'close': prices,
        'volume': np.random.randint(500000, 2000000, n),
    }, index=dates)
    return df


class TestBacktestEngine:
    """回测引擎测试组。"""

    def setup_method(self):
        self.df = _make_df()
        self.strategy = BollingerBandsStrategy(window=20, num_std=2.0)
        self.engine = BacktestEngine(
            self.strategy, self.df.copy(),
            initial_capital=100000, commission=0.0003
        )

    def test_run_returns_dataframe(self):
        """run() 应返回 DataFrame。"""
        result = self.engine.run()
        assert isinstance(result, pd.DataFrame)
        assert len(result) == len(self.df)

    def test_result_columns(self):
        """结果 DataFrame 应包含必须的列。"""
        result = self.engine.run()
        required = ['market_return', 'strategy_return', 'strategy_net_return',
                     'cumulative_market_return', 'cumulative_strategy_return', 'equity']
        for col in required:
            assert col in result.columns, f"缺少列: {col}"

    def test_equity_positive(self):
        """权益曲线应始终 > 0（假设没有杠杆不会归零）。"""
        self.engine.run()
        assert (self.engine.results['equity'] > 0).all()

    def test_metrics_keys(self):
        """calculate_metrics 应返回完整的指标。"""
        self.engine.run()
        metrics = self.engine.calculate_metrics()
        required_keys = ['Total Return', 'Annualized Return', 'Max Drawdown',
                         'Sharpe Ratio', 'Transaction Count', 'Win Rate']
        for key in required_keys:
            assert key in metrics, f"缺少指标: {key}"

    def test_metrics_types(self):
        """指标值类型检查。"""
        self.engine.run()
        metrics = self.engine.calculate_metrics()
        assert isinstance(metrics['Total Return'], float)
        assert isinstance(metrics['Transaction Count'], int)
        assert 0.0 <= metrics['Win Rate'] <= 1.0

    def test_max_drawdown_negative(self):
        """最大回撤应 <= 0。"""
        self.engine.run()
        metrics = self.engine.calculate_metrics()
        assert metrics['Max Drawdown'] <= 0

    def test_trade_records_structure(self):
        """get_trade_records 应返回正确结构的记录。"""
        self.engine.run()
        records = self.engine.get_trade_records()
        assert isinstance(records, list)
        if records:
            r = records[0]
            assert 'date' in r
            assert 'direction' in r
            assert r['direction'] in ('买入', '卖出')
            assert 'price' in r
            assert 'position_change' in r

    def test_trade_records_buy_sell_pairs(self):
        """卖出记录应有 PnL 和持仓天数。"""
        self.engine.run()
        records = self.engine.get_trade_records()
        sells = [r for r in records if r['direction'] == '卖出']
        for s in sells:
            assert s['pnl'] is not None, "卖出记录应有 PnL"
            assert s['holding_days'] is not None, "卖出记录应有持仓天数"
            assert s['holding_days'] >= 0

    def test_commission_impact(self):
        """佣金应减少收益。"""
        engine_no_comm = BacktestEngine(
            BollingerBandsStrategy(window=20, num_std=2.0),
            self.df.copy(), initial_capital=100000, commission=0.0
        )
        engine_high_comm = BacktestEngine(
            BollingerBandsStrategy(window=20, num_std=2.0),
            self.df.copy(), initial_capital=100000, commission=0.01
        )
        engine_no_comm.run()
        engine_high_comm.run()
        m_no = engine_no_comm.calculate_metrics()
        m_hi = engine_high_comm.calculate_metrics()
        assert m_no['Total Return'] >= m_hi['Total Return'], "高佣金应降低收益"

    def test_execution_types(self):
        """不同交易时机均应正常运行。"""
        for exec_type in ['close', 'next_open']:
            engine = BacktestEngine(
                BollingerBandsStrategy(window=20, num_std=2.0),
                self.df.copy(), initial_capital=100000,
                execution_type=exec_type
            )
            result = engine.run()
            assert len(result) == len(self.df)


class _FixedPositions:
    """Prescribed decisions isolate accounting from indicator logic."""

    def __init__(self, positions):
        self.positions = positions

    def generate_signals(self, df):
        result = df.copy()
        result['position'] = self.positions
        result['signal'] = result['position'].diff().fillna(result['position'])
        return result


def _accounting_engine(positions, closes=None, opens=None, dates=None, **kwargs):
    closes = closes if closes is not None else [100.0] * len(positions)
    opens = opens if opens is not None else closes
    dates = dates if dates is not None else pd.bdate_range('2024-01-01', periods=len(positions))
    data = pd.DataFrame({'close': closes, 'open': opens}, index=dates)
    return BacktestEngine(_FixedPositions(positions), data, cash_annual_yield=0, **kwargs)


@pytest.mark.parametrize('execution_type,costs,count', [
    ('close', [0.005, 0.005, 0.005, 0.005, 0.01], 5),
    ('next_open', [0, 0.005, 0.005, 0.005, 0.005], 4),
    ('hybrid', [0.005, 0.005, 0, 0.005, 0.015], 5),
])
def test_commissions_follow_actual_execution_dates(execution_type, costs, count):
    engine = _accounting_engine([0.5, 1.0, 0.5, 0.0, 1.0], commission=0.01,
                                execution_type=execution_type)
    result = engine.run()
    np.testing.assert_allclose(result['cost'], costs)
    assert result['equity'].iloc[-1] == pytest.approx(100000 * np.prod(1 - np.array(costs)))
    assert engine.calculate_metrics()['Transaction Count'] == count
    assert len(engine.get_trade_records()) == count


def test_initial_purchase_fee_is_included_in_drawdown():
    engine = _accounting_engine([1.0], commission=0.01)
    engine.run()
    metrics = engine.calculate_metrics()
    assert metrics['Total Return'] == pytest.approx(-0.01)
    assert metrics['Max Drawdown'] == pytest.approx(-0.01)
    assert metrics['Transaction Count'] == 1
    assert metrics['Volatility'] == 0
    assert all(not np.isnan(value) for value in metrics.values())


def test_close_signal_does_not_profit_from_same_day_price_move():
    engine = _accounting_engine([0.0, 1.0, 1.0], closes=[100.0, 200.0, 300.0], commission=0)
    result = engine.run()
    np.testing.assert_allclose(result['strategy_return'], [0, 0, 0.5])
    assert result['cumulative_market_return'].iloc[0] == 1


def test_next_open_purchase_skips_gap_before_execution():
    engine = _accounting_engine([1.0, 1.0, 0.0], closes=[100.0, 132.0, 156.0],
                                opens=[100.0, 120.0, 130.0], commission=0,
                                execution_type='next_open')
    result = engine.run()
    np.testing.assert_allclose(result['strategy_return'], [0, 0.1, 156 / 132 - 1])
    assert engine.calculate_metrics()['Transaction Count'] == 1


def test_hybrid_exit_keeps_overnight_exposure_but_skips_intraday_move():
    engine = _accounting_engine([1.0, 0.0, 0.0], closes=[100.0, 110.0, 80.0],
                                opens=[100.0, 100.0, 100.0], commission=0,
                                execution_type='hybrid')
    result = engine.run()
    np.testing.assert_allclose(result['strategy_return'], [0, 0.1, 100 / 110 - 1])


def test_fifo_holding_period_uses_oldest_matched_execution_date():
    dates = pd.to_datetime(['2024-01-04', '2024-01-05', '2024-01-08', '2024-01-09'])
    engine = _accounting_engine([0.5, 1.0, 0.0, 0.0], dates=dates, execution_type='next_open')
    engine.run()
    sell = engine.get_trade_records()[-1]
    assert sell['date'] == dates[2]
    assert sell['execution_date'] == dates[3]
    assert sell['holding_days'] == 4  # Friday purchase to Tuesday sale.


def test_lightweight_metrics_match_full_report_without_fifo(monkeypatch):
    engine = _accounting_engine([0.0, 0.5, 1.0, 0.0], closes=[100, 90, 95, 105])
    engine.run()
    complete = engine.calculate_metrics()
    monkeypatch.setattr(engine, '_build_trade_records', lambda: pytest.fail('FIFO should be skipped'))
    lightweight = engine.calculate_metrics(include_trade_stats=False)
    for name, value in lightweight.items():
        assert value == pytest.approx(complete[name])


def test_empty_backtest_has_no_metrics_or_trades():
    engine = _accounting_engine([])
    assert engine.run().empty
    assert engine.calculate_metrics() == {}
    assert engine.get_trade_records() == []


@pytest.mark.parametrize('bad_prices', [[100, np.nan], [100, 0], [100, np.inf]])
def test_invalid_prices_fail_instead_of_creating_fabricated_returns(bad_prices):
    engine = _accounting_engine([0.0, 1.0], closes=bad_prices)
    with pytest.raises(ValueError, match='Prices'):
        engine.run()


def test_unknown_execution_mode_is_rejected():
    with pytest.raises(ValueError, match='execution_type'):
        _accounting_engine([0.0], execution_type='unknown')
