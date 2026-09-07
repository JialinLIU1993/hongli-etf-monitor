"""Regression tests for reusable parameter searches."""

import numpy as np
import pandas as pd
import pytest

from src.backtest import BacktestEngine
from src.optimize import optimize_bollinger
from src.strategies import BollingerBandsStrategy


def _prices():
    rng = np.random.default_rng(8)
    prices = 100 * np.exp(rng.normal(0, 0.04, 120).cumsum())
    return pd.DataFrame({'close': prices}, index=pd.bdate_range('2024-01-01', periods=len(prices)))


def test_custom_grid_matches_direct_backtest_and_preserves_input():
    data = _prices()
    original = data.copy(deep=True)
    kwargs = dict(first_batch_pct=0.7, scale_threshold=0.03,
                  pyramid_levels=[0.01, 0.02], pyramid_sizes=[0.4, 0.6])
    results = optimize_bollinger(data, windows=[10, 20], num_stds=[1.5, 2.0], **kwargs)
    assert len(results) == 4
    for row in results.to_dict('records'):
        strategy = BollingerBandsStrategy(window=row['window'], num_std=row['num_std'], **kwargs)
        engine = BacktestEngine(strategy, data)
        engine.run()
        metrics = engine.calculate_metrics()
        for name in ['Total Return', 'Sharpe Ratio', 'Max Drawdown']:
            assert row[name] == pytest.approx(metrics[name])
    pd.testing.assert_frame_equal(data, original)


def test_search_does_not_build_fifo_records(monkeypatch):
    monkeypatch.setattr(BacktestEngine, '_build_trade_records', lambda self: pytest.fail('Unexpected trade statistics'))
    assert len(optimize_bollinger(_prices(), windows=[10], num_stds=[2.0])) == 1


def test_batch_grid_keeps_nine_original_ratios():
    result = optimize_bollinger(_prices(), mode='batch')
    np.testing.assert_allclose(result['first_batch_pct'], np.arange(0.1, 1.0, 0.1))
    assert (result['window'] == 40).all()
    assert (result['num_std'] == 2.1).all()


@pytest.mark.parametrize('mode', ['standard', 'batch'])
def test_empty_search_retains_result_columns(mode):
    result = optimize_bollinger(pd.DataFrame(), mode=mode)
    assert result.empty
    assert set(['window', 'num_std', 'Total Return', 'Sharpe Ratio', 'Max Drawdown']) <= set(result.columns)
    assert ('first_batch_pct' in result) == (mode == 'batch')


def test_unknown_search_mode_is_rejected():
    with pytest.raises(ValueError, match='mode'):
        optimize_bollinger(_prices(), mode='typo')
