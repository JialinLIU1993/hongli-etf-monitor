import numpy as np
import logging
from collections import deque
try:
    from src.config import RISK_FREE_RATE
except ImportError:
    # Fallback for script execution
    import sys
    import os
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    from src.config import RISK_FREE_RATE

logger = logging.getLogger(__name__)

class BacktestEngine:
    def __init__(self, strategy, data, initial_capital=100000, commission=0.0003,
                 slippage=0.0, execution_type='close', risk_manager=None, cash_annual_yield=None):
        """
        Args:
            slippage: 单边滑点比例（如 0.0002 = 万分之二）
            execution_type: 'close' | 'next_open' | 'hybrid'
            risk_manager: Optional RiskManager instance
            cash_annual_yield: 年化闲钱收益率，默认为 RISK_FREE_RATE
        """
        if execution_type not in {'close', 'next_open', 'hybrid'}:
            raise ValueError("execution_type must be 'close', 'next_open', or 'hybrid'")
        if not np.isfinite(initial_capital) or initial_capital <= 0:
            raise ValueError('initial_capital must be positive and finite')
        if not all(np.isfinite(value) and value >= 0 for value in (commission, slippage)) or commission + slippage >= 1:
            raise ValueError('commission and slippage must be non-negative and total less than 1')
        self.strategy = strategy
        self.data = data
        self.initial_capital = initial_capital
        self.commission = commission
        self.slippage = slippage
        self.execution_type = execution_type
        self.risk_manager = risk_manager
        self.cash_annual_yield = cash_annual_yield if cash_annual_yield is not None else RISK_FREE_RATE
        if not np.isfinite(self.cash_annual_yield) or self.cash_annual_yield <= -1:
            raise ValueError('cash_annual_yield must be finite and greater than -1')
        self.results = None
        logger.info(f"BacktestEngine: capital={initial_capital}, comm={commission}, slip={slippage}, exec={execution_type}, cash_yield={self.cash_annual_yield}")

    @staticmethod
    def _position_changes(position):
        changes = position.diff().fillna(position)
        return changes.where(changes.abs() > 1e-9, 0.0)

    def run(self):
        # Clear a previous run before validating new data.
        self.results = None
        required = ['close'] if self.execution_type == 'close' else ['close', 'open']
        missing = set(required) - set(self.data.columns)
        if missing:
            raise ValueError(f"Missing price columns: {', '.join(sorted(missing))}")
        if not self.data.index.is_monotonic_increasing or not self.data.index.is_unique:
            raise ValueError('Price data must have a unique, increasing index')
        prices = self.data[required].to_numpy(dtype=float)
        if not np.isfinite(prices).all() or (prices <= 0).any():
            raise ValueError('Prices must be positive and finite')

        df = self.strategy.generate_signals(self.data)
        if self.risk_manager is not None:
            df = self.risk_manager.apply(df, self.initial_capital)
        position = df['position']
        if not np.isfinite(position.to_numpy(dtype=float)).all() or not position.between(0, 1).all():
            raise ValueError('Strategy positions must be finite and within [0, 1]')

        changes = self._position_changes(position)
        daily_cash_return = (1 + self.cash_annual_yield) ** (1 / 252) - 1
        df['market_return'] = df['close'].pct_change(fill_method=None).fillna(0.0)
        if self.execution_type == 'close':
            # A close signal changes exposure only for the following price interval.
            held = position.shift(1).fillna(0.0)
            df['strategy_return'] = held * df['market_return'] + (1.0 - held) * daily_cash_return
            traded = changes.abs()
        else:
            overnight_return = (df['open'] / df['close'].shift(1) - 1).fillna(0.0)
            intraday_return = df['close'] / df['open'] - 1
            intraday_position = position.shift(1).fillna(0.0)
            overnight_position = position.shift(2).fillna(0.0)
            if self.execution_type == 'hybrid':
                overnight_position = np.maximum(intraday_position, overnight_position)
                # Buys execute at the signal day's close; sells at the next open.
                traded = changes.clip(lower=0) + (-changes.clip(upper=0)).shift(1).fillna(0.0)
            else:
                traded = changes.abs().shift(1).fillna(0.0)
            df['strategy_return'] = (
                (1 + overnight_return * overnight_position + (1.0 - overnight_position) * daily_cash_return * 0.5)
                * (1 + intraday_return * intraday_position + (1.0 - intraday_position) * daily_cash_return * 0.5)
                - 1
            )

        # The first observation has no prior holding period, but a close purchase
        # can still incur a fee. Do not erase that fee with a NaN return.
        if not df.empty:
            df.iloc[0, df.columns.get_loc('strategy_return')] = 0.0
        df['cost'] = traded * (self.commission + self.slippage)
        df['strategy_net_return'] = df['strategy_return'] - df['cost']
        df['cumulative_market_return'] = (1 + df['market_return']).cumprod()
        df['cumulative_strategy_return'] = (1 + df['strategy_net_return']).cumprod()
        df['equity'] = self.initial_capital * df['cumulative_strategy_return']
        self.results = df
        return df

    def calculate_metrics(self, include_trade_stats=True):
        """Calculate performance, optionally skipping FIFO trade detail for searches."""
        if self.results is None or self.results.empty:
            return {}
        
        df = self.results
        total_return = df['cumulative_strategy_return'].iloc[-1] - 1
        days = len(df)
        annual_return = (1 + total_return) ** (252/days) - 1
        
        # Max Drawdown
        rolling_max = df['equity'].cummax().clip(lower=self.initial_capital)
        drawdown = (df['equity'] - rolling_max) / rolling_max
        max_drawdown = drawdown.min()
        
        # Sharpe Ratio (使用统一无风险利率)
        daily_returns = df['strategy_net_return'].fillna(0)
        rf_daily = (1 + RISK_FREE_RATE) ** (1/252) - 1
        excess_returns = daily_returns - rf_daily
        sharpe_ratio = np.sqrt(252) * excess_returns.mean() / excess_returns.std() if excess_returns.std() > 0 else 0.0
        
        if not include_trade_stats:
            return {
                "Total Return": float(total_return),
                "Annualized Return": float(annual_return),
                "Max Drawdown": float(max_drawdown),
                "Sharpe Ratio": float(sharpe_ratio),
            }

        # One FIFO pass supplies both trade metrics and detailed records.
        trade_records, realized_pnl = self._build_trade_records()
        transaction_count = len(trade_records)

        win_count = sum(1 for pnl in realized_pnl if pnl > 0)
        loss_count = sum(1 for pnl in realized_pnl if pnl <= 0)
        total_trades = len(realized_pnl)
        win_rate = win_count / total_trades if total_trades > 0 else 0.0

        # --- 新增指标 ---

        # 年化波动率
        volatility = daily_returns.std() * np.sqrt(252) if len(daily_returns) > 1 else 0.0

        # Sortino Ratio (仅用下行波动率)
        downside = daily_returns[daily_returns < 0]
        downside_std = downside.std() if len(downside) > 0 else 0.0
        sortino_ratio = np.sqrt(252) * daily_returns.mean() / downside_std if downside_std > 0 else 0.0

        # Calmar Ratio (年化收益 / |最大回撤|)
        calmar_ratio = annual_return / abs(max_drawdown) if max_drawdown != 0 else 0.0

        # Profit Factor (盈利总和 / 亏损总和)
        gross_wins = sum(p for p in realized_pnl if p > 0)
        gross_losses = abs(sum(p for p in realized_pnl if p <= 0))
        profit_factor = gross_wins / gross_losses if gross_losses > 0 else float('inf') if gross_wins > 0 else 0.0

        # 平均盈利 / 平均亏损
        avg_win = gross_wins / win_count if win_count > 0 else 0.0
        avg_loss = gross_losses / loss_count if loss_count > 0 else 0.0

        # 最大连续盈亏次数
        max_consec_wins = 0
        max_consec_losses = 0
        cur_wins = 0
        cur_losses = 0
        for pnl in realized_pnl:
            if pnl > 0:
                cur_wins += 1
                cur_losses = 0
                max_consec_wins = max(max_consec_wins, cur_wins)
            else:
                cur_losses += 1
                cur_wins = 0
                max_consec_losses = max(max_consec_losses, cur_losses)

        # 平均持仓天数（从交易记录计算）
        sell_records = [r for r in trade_records if r['direction'] == '卖出' and r.get('holding_days') is not None]
        avg_holding_days = np.mean([r['holding_days'] for r in sell_records]) if sell_records else 0.0

        return {
            "Total Return": total_return,
            "Annualized Return": annual_return,
            "Volatility": volatility,
            "Max Drawdown": max_drawdown,
            "Sharpe Ratio": sharpe_ratio,
            "Sortino Ratio": sortino_ratio,
            "Calmar Ratio": calmar_ratio,
            "Transaction Count": int(transaction_count),
            "Win Rate": win_rate,
            "Profit Factor": profit_factor,
            "Avg Win": avg_win,
            "Avg Loss": avg_loss,
            "Max Consecutive Wins": max_consec_wins,
            "Max Consecutive Losses": max_consec_losses,
            "Avg Holding Days": avg_holding_days,
        }

    def _executed_trades(self):
        """Yield only executable changes, with both signal and execution dates."""
        df = self.results
        changes = self._position_changes(df['position']).to_numpy()
        closes = df['close'].to_numpy()
        opens = df['open'].to_numpy() if self.execution_type != 'close' else None
        positions = df['position'].to_numpy()
        for i in np.flatnonzero(changes):
            change = changes[i]
            next_open = self.execution_type == 'next_open' or (self.execution_type == 'hybrid' and change < 0)
            execution_i = i + 1 if next_open else i
            if execution_i >= len(df):
                continue
            price = opens[execution_i] if next_open else closes[i]
            yield df.index[i], df.index[execution_i], price, change, positions[i]

    def _build_trade_records(self):
        if self.results is None or self.results.empty:
            return [], []
        records = []
        realized_pnl = []
        fifo_queue = deque()  # Effective entry price, position quantity, execution date.
        for signal_date, execution_date, price, change, position_after in self._executed_trades():
            quantity = abs(change)
            record = {
                'date': signal_date,
                'execution_date': execution_date,
                'direction': '买入' if change > 0 else '卖出',
                'price': price,
                'position_change': f"{change:+.0%}",
                'position_after': f"{position_after:.0%}",
                'pnl': None,
                'holding_days': None,
            }
            if change > 0:
                fifo_queue.append((price * (1 + self.commission + self.slippage), quantity, execution_date))
            else:
                effective_exit = price * (1 - self.commission - self.slippage)
                remaining = quantity
                total_pnl = total_weight = 0.0
                earliest_entry = None
                while remaining > 1e-9 and fifo_queue:
                    entry_price, entry_quantity, entry_date = fifo_queue[0]
                    matched = min(remaining, entry_quantity)
                    pnl = (effective_exit - entry_price) / entry_price
                    realized_pnl.append(pnl)
                    total_pnl += pnl * matched
                    total_weight += matched
                    if earliest_entry is None:
                        earliest_entry = entry_date
                    remaining -= matched
                    if entry_quantity - matched <= 1e-9:
                        fifo_queue.popleft()
                    else:
                        fifo_queue[0] = (entry_price, entry_quantity - matched, entry_date)
                record['pnl'] = total_pnl / total_weight if total_weight else 0.0
                record['holding_days'] = (execution_date - earliest_entry).days if earliest_entry is not None else 0
            records.append(record)
        return records, realized_pnl

    def get_trade_records(self):
        """Return executed trades; date is the signal date, execution_date the fill date.

        Sell holding days run from the oldest matched FIFO entry's actual fill.
        """
        return self._build_trade_records()[0]

    def plot_results(self):
        import matplotlib.pyplot as plt

        if self.results is None:
            print("Run backtest first.")
            return
            
        plt.figure(figsize=(12, 8))
        plt.plot(self.results.index, self.results['cumulative_market_return'], label='Benchmark (Buy & Hold)', alpha=0.5)
        plt.plot(self.results.index, self.results['cumulative_strategy_return'], label='Strategy', linewidth=2)
        
        # Include fractional staged purchases and sales in the plot markers.
        
        buys = self.results[self._position_changes(self.results['position']) > 0]
        sells = self.results[self._position_changes(self.results['position']) < 0]
        
        plt.scatter(buys.index, self.results.loc[buys.index, 'cumulative_strategy_return'], 
                    marker='^', color='green', label='Buy', s=100)
        plt.scatter(sells.index, self.results.loc[sells.index, 'cumulative_strategy_return'], 
                    marker='v', color='red', label='Sell', s=100)
        
        plt.title(f"Backtest Result: {self.strategy.name}")
        plt.xlabel("Date")
        plt.ylabel("Cumulative Return")
        plt.legend()
        plt.grid(True)
        plt.show()
