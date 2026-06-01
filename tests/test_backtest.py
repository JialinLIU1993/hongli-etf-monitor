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
