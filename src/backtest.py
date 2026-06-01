import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
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
            execution_type: 'close' | 'next_open'
            risk_manager: Optional RiskManager instance
            cash_annual_yield: 年化闲钱收益率，默认为 RISK_FREE_RATE
        """
        self.strategy = strategy
        self.data = data
        self.initial_capital = initial_capital
        self.commission = commission
        self.slippage = slippage
        self.execution_type = execution_type
        self.risk_manager = risk_manager
        self.cash_annual_yield = cash_annual_yield if cash_annual_yield is not None else RISK_FREE_RATE
        self.results = None
        logger.info(f"BacktestEngine: capital={initial_capital}, comm={commission}, slip={slippage}, exec={execution_type}, cash_yield={self.cash_annual_yield}")

    def run(self):
        # Generate signals
        df = self.strategy.generate_signals(self.data)
        
        # Apply risk management (override positions if stop-loss triggered)
        if self.risk_manager is not None:
            df = self.risk_manager.apply(df, self.initial_capital)
        
        # Calculate returns
        daily_cash_return = (1 + self.cash_annual_yield) ** (1 / 252) - 1
        
        if self.execution_type == 'close':
            # Standard Close-to-Close Return
            df['market_return'] = df['close'].pct_change()
            # Position at T Close affects return at T+1
            # Effectively simulating: Buy at T Close, Hold for T+1
            strategy_pos = df['position'].shift(1).fillna(0)
            cash_pos = np.maximum(0.0, 1.0 - strategy_pos)
            df['strategy_return'] = strategy_pos * df['market_return'] + cash_pos * daily_cash_return
            
            # Commission paid on day T (when position changes)
            trades = df['position'].diff().abs()
            df['cost'] = trades * (self.commission + self.slippage)
            
        elif self.execution_type == 'next_open':
            # Trade at Next Open
            pct_open_close = (df['close'] - df['open']) / df['open']
            pct_close_close = df['close'].pct_change()
            
            ret_overnight = (df['open'] / df['close'].shift(1)) - 1
            ret_intraday = (df['close'] / df['open']) - 1
            
            pos_prev = df['position'].shift(2).fillna(0) # Position held overnight
            pos_curr = df['position'].shift(1).fillna(0) # Position held intraday
            
            cash_prev = np.maximum(0.0, 1.0 - pos_prev)
            cash_curr = np.maximum(0.0, 1.0 - pos_curr)
            
            df['strategy_return'] = (1 + ret_overnight * pos_prev + cash_prev * daily_cash_return * 0.5) * (1 + ret_intraday * pos_curr + cash_curr * daily_cash_return * 0.5) - 1
            
            trades = df['position'].shift(1).diff().abs()
            df['cost'] = trades * (self.commission + self.slippage)
            df['market_return'] = df['close'].pct_change()

        elif self.execution_type == 'hybrid':
            # Buy at Close T (Tail), Sell at Open T+1 (Next Open)
            # Buy Logic (0 -> 1):
            #   Signal T says Buy. Position T=1.
            #   We enter at Close T.
            #   We hold T->T+1 overnight.
            #   We hold T+1 intraday.
            
            # Sell Logic (1 -> 0):
            #   Signal T says Sell. Position T=0.
            #   We exit at Open T+1.
            #   We hold T->T+1 overnight.
            #   We DO NOT hold T+1 intraday.
            
            # Constructing Return for Day T+1:
            # ret_overnight = (Open[T+1] / Close[T]) - 1
            # ret_intraday = (Close[T+1] / Open[T+1]) - 1
            
            # Position Overnight (T->T+1):
            #   Depends on Position T.
            #   If Buy (0->1 at T): Pos T=1. We hold overnight.
            #   If Sell (1->0 at T): Pos T=0? NO.
            #   Wait. If we sell at Open T+1, it means we HELD overnight.
            #   So for "Hybrid Sell", we treat Signal T (Sell) as "Exit at Next Open".
            #   This means we are effectively holding position T=1 overnight, then 0 intraday.
            #   But Position column says 0 at T.
            #   So we need to check: Did we just sell?
            #   If Position[T]==0 and Position[T-1]==1 (Sell Signal at T):
            #     Overnight Pos = 1.
            #     Intraday Pos = 0.
            
            # General Logic:
            #   Overnight Pos = Position[T-1] (Previous state) OR Position[T] (New state)?
            #   If Buy (0->1): We buy at Close T. So Overnight we hold 1. (Pos T)
            #   If Sell (1->0): We sell at Open T+1. So Overnight we hold 1. (Pos T-1)
            #   If Hold (1->1): Overnight 1. (Pos T)
            #   If Flat (0->0): Overnight 0. (Pos T)
            
            # So Overnight Pos = max(Pos[T], Pos[T-1]) ?
            #   0->1: max(1,0)=1. Correct.
            #   1->0: max(0,1)=1. Correct.
            #   1->1: 1. Correct.
            #   0->0: 0. Correct.
            
            # Intraday Pos (Day T+1):
            #   If Buy (0->1 at T): Intraday T+1 we hold 1. (Pos T)
            #   If Sell (1->0 at T): Intraday T+1 we hold 0. (Pos T)
            #   So Intraday Pos = Pos[T].
            
            # Mapping to T+1 row index:
            #   We need values from T (shift 1).
            #   pos_overnight = max(position.shift(1), position.shift(2))
            #   pos_intraday = position.shift(1)
            
            ret_overnight = (df['open'] / df['close'].shift(1)) - 1
            ret_intraday = (df['close'] / df['open']) - 1
            
            pos_t = df['position'].shift(1).fillna(0)
            pos_t_minus_1 = df['position'].shift(2).fillna(0)
            
            # Overnight position logic for Hybrid
            # We hold overnight if we BOUGHT at Close T, OR if we haven't SOLD yet (until Open T+1).
            # If we sold at Close T (Standard): Overnight is 0.
            # If we sell at Open T+1 (Hybrid): Overnight is 1.
            # So yes, max(current, prev) covers it.
            # Wait, Staged position? (0.5 etc).
            # If 1.0 -> 0.5 (Sell half):
            #   Overnight: We hold 1.0 (Full) until Open.
            #   Intraday: We hold 0.5.
            #   max(1.0, 0.5) = 1.0. Correct.
            # If 0.5 -> 1.0 (Buy half):
            #   Overnight: We hold 1.0 (Full) starting Close T.
            #   Intraday: We hold 1.0.
            #   max(0.5, 1.0) = 1.0. Correct.
            
            pos_overnight = np.maximum(pos_t, pos_t_minus_1)
            pos_intraday = pos_t
            
            cash_overnight = np.maximum(0.0, 1.0 - pos_overnight)
            cash_intraday = np.maximum(0.0, 1.0 - pos_intraday)
            
            df['strategy_return'] = (1 + ret_overnight * pos_overnight + cash_overnight * daily_cash_return * 0.5) * (1 + ret_intraday * pos_intraday + cash_intraday * daily_cash_return * 0.5) - 1
            
            # Commission
            # Buy Trades: Close T.
            # Sell Trades: Open T+1.
            # We just sum them up on Day T+1 (or T)?
            # Simplified: Charge commission on the day the PnL is realized or signal generated.
            # Let's charge on Day T+1 for simplicity of vectorization.
            trades = df['position'].shift(1).diff().abs()
            df['cost'] = trades * (self.commission + self.slippage)
            df['market_return'] = df['close'].pct_change()

        # Net strategy return
        df['strategy_net_return'] = df['strategy_return'] - df['cost']
        
        # Cumulative returns
        df['cumulative_market_return'] = (1 + df['market_return']).cumprod()
        df['cumulative_strategy_return'] = (1 + df['strategy_net_return'].fillna(0)).cumprod()
        
        # Equity curve
        df['equity'] = self.initial_capital * df['cumulative_strategy_return']
        
        self.results = df
        return df

    def calculate_metrics(self):
        if self.results is None:
            return {}
        
        df = self.results
        total_return = df['cumulative_strategy_return'].iloc[-1] - 1
        days = len(df)
        annual_return = (1 + total_return) ** (252/days) - 1
        
        # Max Drawdown
        rolling_max = df['equity'].cummax()
        drawdown = (df['equity'] - rolling_max) / rolling_max
        max_drawdown = drawdown.min()
        
        # Sharpe Ratio (使用统一无风险利率)
        daily_returns = df['strategy_net_return'].fillna(0)
        rf_daily = (1 + RISK_FREE_RATE) ** (1/252) - 1
        excess_returns = daily_returns - rf_daily
        sharpe_ratio = np.sqrt(252) * excess_returns.mean() / excess_returns.std() if excess_returns.std() > 0 else 0.0
        
        # Transaction Count
        # Count non-zero changes in position
        transaction_count = df['position'].diff().abs().gt(0).sum()
        
        # Win Rate Calculation
        # Use robust Price-based FIFO stack for PnL calculation
        
        realized_pnl = []
        fifo_queue = deque()  # Stores (price, quantity) — O(1) popleft
        
        # Iterate through the DataFrame to simulate trades
        # We need trade execution prices based on execution_type
        
        # Determine execution prices for each day
        # 'close': Exec price = Close
        # 'next_open': Exec price = Open (shifted -1? No, next day open)
        # 'hybrid': Buy at Close, Sell at Next Open
        
        # Simpler approach:
        # Loop through signals.
        # If Signal > 0 (Buy): Add to FIFO. Price depends on execution_type.
        # If Signal < 0 (Sell): Pop from FIFO. Price depends on execution_type.
        
        # We need to map signals to prices.
        # Signal T -> Trade T (Close) or Trade T+1 (Open)
        
        # Let's align signals to trade dates and prices.
        # signals = df['position'].diff()
        # signal[i] != 0 means trade decision made at end of day i.
        
        # For 'close'/'hybrid' Buy: Trade at Close[i]
        # For 'next_open' Buy: Trade at Open[i+1]
        
        # For 'close' Sell: Trade at Close[i]
        # For 'next_open'/'hybrid' Sell: Trade at Open[i+1]
        
        for i in range(len(df)):
            sig = df['position'].iloc[i] - (df['position'].iloc[i-1] if i > 0 else 0)
            
            if sig == 0:
                continue
                
            # Determine Trade Price
            trade_price = 0.0
            is_buy = sig > 0
            qty = abs(sig)
            
            # Index boundary check for Next Open
            if i + 1 >= len(df):
                # Cannot execute Next Open trade if at end of data
                if self.execution_type in ['next_open', 'hybrid'] and (self.execution_type == 'next_open' or not is_buy):
                    continue
                else:
                    # Close execution is possible
                    trade_price = df['close'].iloc[i]
            else:
                if self.execution_type == 'close':
                    trade_price = df['close'].iloc[i]
                elif self.execution_type == 'next_open':
                    trade_price = df['open'].iloc[i+1]
                elif self.execution_type == 'hybrid':
                    if is_buy:
                        trade_price = df['close'].iloc[i]
                    else:
                        trade_price = df['open'].iloc[i+1]
            
            # Execute Trade Logic
            if is_buy:
                # Buy: Add to FIFO
                # Add commission to cost basis? Or handle separately.
                # PnL = (Exit - Entry) / Entry. Commission reduces PnL.
                # Effective Entry = Price * (1 + Comm)
                eff_price = trade_price * (1 + self.commission + self.slippage)
                fifo_queue.append((eff_price, qty))
                
            else:
                # Sell: Pop from FIFO
                # Effective Exit = Price * (1 - Comm)
                eff_price = trade_price * (1 - self.commission - self.slippage)
                
                qty_to_sell = qty
                
                while qty_to_sell > 0 and fifo_queue:
                    entry_price, entry_qty = fifo_queue[0]
                    
                    matched_qty = min(qty_to_sell, entry_qty)
                    
                    # Calculate PnL for this chunk
                    pnl = (eff_price - entry_price) / entry_price
                    realized_pnl.append(pnl)
                    
                    # Update state
                    qty_to_sell -= matched_qty
                    
                    if matched_qty == entry_qty:
                        fifo_queue.popleft()  # O(1)
                    else:
                        fifo_queue[0] = (entry_price, entry_qty - matched_qty)

        win_count = sum(1 for pnl in realized_pnl if pnl > 0)
        loss_count = sum(1 for pnl in realized_pnl if pnl <= 0)
        total_trades = len(realized_pnl)
        win_rate = win_count / total_trades if total_trades > 0 else 0.0

        # --- 新增指标 ---

        # 年化波动率
        volatility = daily_returns.std() * np.sqrt(252)

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
        trade_records = self.get_trade_records()
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

    def get_trade_records(self):
        """
        提取每一笔交易的详细记录。
        返回 list[dict]，每条记录包含：
          - date: 信号日期
          - direction: '买入' 或 '卖出'
          - price: 成交价
          - position_change: 仓位变化 (+/-)
          - position_after: 交易后仓位
          - pnl: 已实现收益率（仅卖出时有值）
          - holding_days: 本笔持仓天数（仅卖出时有值）
        """
        if self.results is None:
            return []

        df = self.results
        records = []
        fifo_queue = deque()  # Stores (entry_price, qty, entry_date)

        for i in range(len(df)):
            sig = df['position'].iloc[i] - (df['position'].iloc[i-1] if i > 0 else 0)

            if abs(sig) < 1e-9:
                continue

            is_buy = sig > 0
            qty = abs(sig)
            signal_date = df.index[i]

            # Determine Trade Price (same logic as calculate_metrics)
            trade_price = 0.0
            if i + 1 >= len(df):
                if self.execution_type in ['next_open', 'hybrid'] and (self.execution_type == 'next_open' or not is_buy):
                    continue
                else:
                    trade_price = df['close'].iloc[i]
            else:
                if self.execution_type == 'close':
                    trade_price = df['close'].iloc[i]
                elif self.execution_type == 'next_open':
                    trade_price = df['open'].iloc[i+1]
                elif self.execution_type == 'hybrid':
                    trade_price = df['close'].iloc[i] if is_buy else df['open'].iloc[i+1]

            if is_buy:
                eff_price = trade_price * (1 + self.commission + self.slippage)
                fifo_queue.append((eff_price, qty, signal_date))
                records.append({
                    'date': signal_date,
                    'direction': '买入',
                    'price': trade_price,
                    'position_change': f"+{qty:.0%}",
                    'position_after': f"{df['position'].iloc[i]:.0%}",
                    'pnl': None,
                    'holding_days': None,
                })
            else:
                eff_price = trade_price * (1 - self.commission - self.slippage)
                qty_to_sell = qty
                total_pnl = 0.0
                total_weight = 0.0
                earliest_entry = signal_date

                while qty_to_sell > 1e-9 and fifo_queue:
                    entry_price, entry_qty, entry_date = fifo_queue[0]
                    matched_qty = min(qty_to_sell, entry_qty)

                    pnl = (eff_price - entry_price) / entry_price
                    total_pnl += pnl * matched_qty
                    total_weight += matched_qty
                    earliest_entry = entry_date

                    qty_to_sell -= matched_qty
                    if abs(matched_qty - entry_qty) < 1e-9:
                        fifo_queue.popleft()
                    else:
                        fifo_queue[0] = (entry_price, entry_qty - matched_qty, entry_date)

                avg_pnl = total_pnl / total_weight if total_weight > 0 else 0
                hold_days = (signal_date - earliest_entry).days

                records.append({
                    'date': signal_date,
                    'direction': '卖出',
                    'price': trade_price,
                    'position_change': f"-{qty:.0%}",
                    'position_after': f"{df['position'].iloc[i]:.0%}",
                    'pnl': avg_pnl,
                    'holding_days': hold_days,
                })

        return records

    def plot_results(self):
        if self.results is None:
            print("Run backtest first.")
            return
            
        plt.figure(figsize=(12, 8))
        plt.plot(self.results.index, self.results['cumulative_market_return'], label='Benchmark (Buy & Hold)', alpha=0.5)
        plt.plot(self.results.index, self.results['cumulative_strategy_return'], label='Strategy', linewidth=2)
        
        # Plot buy/sell markers
        # Buy: signal == 1 (meaning position increased)
        # Sell: signal == -1
        # Signals are stored in 'signal' column from generate_signals (diff of position)
        
        buys = self.results[self.results['signal'] == 1]
        sells = self.results[self.results['signal'] == -1]
        
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
