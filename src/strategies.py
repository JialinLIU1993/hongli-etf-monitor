import pandas as pd
import numpy as np

class BaseStrategy:
    def __init__(self, name="Base Strategy"):
        self.name = name

    def generate_signals(self, df):
        """
        Input: DataFrame with 'close' column
        Output: DataFrame with 'signal' column (1: Buy, -1: Sell, 0: No action)
                and 'position' column (1: Long, 0: Empty)
        """
        raise NotImplementedError

class BollingerBandsStrategy(BaseStrategy):
    def __init__(self, window=20, num_std=2, staged=True, scale_threshold=0.02, 
                 first_batch_pct=0.5, sell_batch_pct=None, 
                 confirm_reversal=False, min_position=0.0,
                 pyramid_levels=None, pyramid_sizes=None):
        """
        first_batch_pct: Buying first batch percentage (e.g. 0.9 for 90%)
        sell_batch_pct: Selling first batch percentage. Defaults to first_batch_pct.
        pyramid_levels: list of % thresholds below lower band for pyramid entries, e.g. [0.01, 0.02, 0.03]
        pyramid_sizes: list of position sizes per level, e.g. [0.3, 0.3, 0.4]. Must sum to <= 1.0.
        """
        suffix = " (Staged)" if staged else " (All-in)"
        if confirm_reversal:
            suffix += " [Reversal]"
        if min_position > 0:
            suffix += f" [Min {min_position:.0%}]"
        if pyramid_levels:
            suffix += f" [Pyramid {len(pyramid_levels)}L]"
            
        super().__init__(f"Bollinger Bands ({window}, {num_std}, {scale_threshold:.1%}, {first_batch_pct:.0%}){suffix}")
        self.window = window
        self.num_std = num_std
        self.staged = staged
        self.scale_threshold = scale_threshold
        self.first_batch_pct = first_batch_pct
        self.sell_batch_pct = sell_batch_pct if sell_batch_pct is not None else first_batch_pct
        self.confirm_reversal = confirm_reversal
        self.min_position = min_position
        self.pyramid_levels = pyramid_levels or []
        self.pyramid_sizes = pyramid_sizes or []

    def generate_signals(self, df):
        signals = df.copy()
        rolling = df['close'].rolling(window=self.window)
        signals['ma'] = rolling.mean()
        signals['std'] = rolling.std()
        signals['upper_band'] = signals['ma'] + signals['std'] * self.num_std
        signals['lower_band'] = signals['ma'] - signals['std'] * self.num_std

        if self.confirm_reversal and not self.staged:
            # An all-in reversal enters/exits after crossing back inside the bands.
            buy = (df['close'].shift(1) < signals['lower_band'].shift(1)) & (df['close'] > signals['lower_band'])
            sell = (df['close'].shift(1) > signals['upper_band'].shift(1)) & (df['close'] < signals['upper_band'])
            targets = pd.Series(np.nan, index=signals.index, dtype=float)
            targets.loc[buy] = 1.0
            targets.loc[sell] = self.min_position
            signals['position'] = targets.ffill().fillna(self.min_position)
        else:
            current_position = self.min_position
            positions = np.empty(len(signals), dtype=float)
            # Iterate numeric arrays; iterrows creates a Series for every trading day.
            values = zip(signals['close'].to_numpy(), signals['lower_band'].to_numpy(),
                         signals['upper_band'].to_numpy())
            for i, (close, lower, upper) in enumerate(values):
                if self.staged:
                    # Keep existing staged behavior, including pyramid priority.
                    if self.pyramid_levels and close < lower:
                        depth = (lower - close) / lower
                        cumulative = self.min_position + sum(
                            size for level, size in zip(self.pyramid_levels, self.pyramid_sizes)
                            if depth >= level
                        )
                        current_position = max(current_position, min(cumulative, 1.0))
                    elif close < lower * (1 - self.scale_threshold):
                        current_position = 1.0
                    elif close < lower:
                        current_position = max(current_position, self.first_batch_pct, self.min_position)
                    elif close > upper * (1 + self.scale_threshold):
                        current_position = self.min_position
                    elif close > upper:
                        current_position = min(current_position, max(1.0 - self.sell_batch_pct, self.min_position))
                elif close < lower:
                    current_position = 1.0
                elif close > upper:
                    current_position = self.min_position
                positions[i] = max(current_position, self.min_position)
            signals['position'] = positions

        # The account starts in cash, so an initial minimum position is a buy.
        signals['signal'] = signals['position'].diff().fillna(signals['position'])
        return signals

class RSIStrategy(BaseStrategy):
    def __init__(self, window=14, buy_threshold=30, sell_threshold=70, staged=True):
        suffix = " (Staged)" if staged else " (All-in)"
        super().__init__(f"RSI ({window}, {buy_threshold}/{sell_threshold}){suffix}")
        self.window = window
        self.buy_threshold = buy_threshold
        self.sell_threshold = sell_threshold
        self.staged = staged

    def calculate_rsi(self, data):
        delta = data.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=self.window).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.window).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    def generate_signals(self, df):
        signals = df.copy()
        signals['rsi'] = self.calculate_rsi(df['close'])
        
        signals['signal'] = 0.0
        signals['position'] = 0.0
        
        current_position = 0.0
        position_list = []
        
        for row in signals.itertuples(index=False):
            if self.staged:
                # Staged Buying (Pyramiding)
                if row.rsi < (self.buy_threshold - 5): # e.g. < 25
                    current_position = 1.0 # 100%
                elif row.rsi < self.buy_threshold: # e.g. < 30
                    current_position = max(current_position, 0.6) # At least 60%
                elif row.rsi < (self.buy_threshold + 5): # e.g. < 35
                    current_position = max(current_position, 0.3) # At least 30%
                
                # Staged Selling
                elif row.rsi > (self.sell_threshold + 5): # e.g. > 75
                    current_position = 0.0 # Clear
                elif row.rsi > self.sell_threshold: # e.g. > 70
                    current_position = min(current_position, 0.3) # Max 30%
                elif row.rsi > (self.sell_threshold - 5): # e.g. > 65
                    current_position = min(current_position, 0.6) # Max 60%
            else:
                # All-in/All-out Logic
                if row.rsi < self.buy_threshold:
                    current_position = 1.0 # Buy All
                elif row.rsi > self.sell_threshold:
                    current_position = 0.0 # Sell All
                
            position_list.append(current_position)
            
        signals['position'] = position_list
        signals['signal'] = signals['position'].diff().fillna(signals['position'])
        return signals

class BollingerWithInnerBandStrategy(BaseStrategy):
    """
    Main Logic: Bollinger Bands (e.g., 40, 2.1)
    Inner Logic: Tighter Bollinger Bands (e.g., 20, 1.5) or similar indicator for micro-swings.
    
    When Main Position is FULL (1.0), we allow selling a portion (inner_ratio) if Inner Upper Band is hit,
    and buying it back if Inner Lower Band is hit.
    """
    def __init__(self, 
                 main_window=40, main_std=2.1, 
                 inner_window=20, inner_std=1.5, 
                 inner_ratio=0.3,
                 name="Bollinger Main + Inner Swing"):
        super().__init__(name)
        self.main_window = main_window
        self.main_std = main_std
        self.inner_window = inner_window
        self.inner_std = inner_std
        self.inner_ratio = inner_ratio

    def generate_signals(self, df):
        signals = df.copy()
        
        # Calculate Main Bands
        signals['ma_main'] = df['close'].rolling(window=self.main_window).mean()
        signals['std_main'] = df['close'].rolling(window=self.main_window).std()
        signals['upper_main'] = signals['ma_main'] + (signals['std_main'] * self.main_std)
        signals['lower_main'] = signals['ma_main'] - (signals['std_main'] * self.main_std)
        
        # Calculate Inner Bands
        signals['ma_inner'] = df['close'].rolling(window=self.inner_window).mean()
        signals['std_inner'] = df['close'].rolling(window=self.inner_window).std()
        signals['upper_inner'] = signals['ma_inner'] + (signals['std_inner'] * self.inner_std)
        signals['lower_inner'] = signals['ma_inner'] - (signals['std_inner'] * self.inner_std)
        
        signals['position'] = 0.0
        current_position = 0.0
        position_list = []
        
        # State tracking
        # 'EMPTY': No position
        # 'FULL': Main position held (1.0)
        # 'PARTIAL': Main position held but reduced by inner swing (1.0 - inner_ratio)
        state = 'EMPTY' 
        
        for row in signals.itertuples(index=False):
            if pd.isna(row.upper_main) or pd.isna(row.upper_inner):
                position_list.append(current_position)
                continue
            
            # 1. Main Logic Triggers (Priority)
            
            # Main Buy Signal: Close < Lower Main
            if row.close < row.lower_main:
                current_position = 1.0
                state = 'FULL'
            
            # Main Sell Signal: Close > Upper Main
            elif row.close > row.upper_main:
                current_position = 0.0
                state = 'EMPTY'
            
            # 2. Inner Swing Logic (Only if holding Main Position)
            elif state == 'FULL':
                # We are holding full position. Look for opportunity to sell high (Inner Swing).
                if row.close > row.upper_inner:
                    # Sell inner_ratio
                    current_position = 1.0 - self.inner_ratio
                    state = 'PARTIAL'
            
            elif state == 'PARTIAL':
                # We sold some. Look to buy back low.
                if row.close < row.lower_inner:
                    # Buy back
                    current_position = 1.0
                    state = 'FULL'
            
            # Ensure precision
            current_position = round(current_position, 2)
            position_list.append(current_position)
            
        signals['position'] = position_list
        signals['signal'] = signals['position'].diff().fillna(signals['position'])
        
        return signals

class BollingerWithGridStrategy(BaseStrategy):
    """
    Main Logic: Bollinger Bands (40, 2.1) for Entry/Exit.
    Grid Logic: When holding, sell 'grid_qty' if price rises 'grid_step' (1%).
                Buy back if price falls 'grid_step' (1%) from last action.
    """
    def __init__(self, 
                 window=40, num_std=2.1, 
                 grid_step=0.01, grid_qty=0.1, max_grids=5,
                 name="Bollinger + Grid"):
        super().__init__(name)
        self.window = window
        self.num_std = num_std
        self.grid_step = grid_step
        self.grid_qty = grid_qty
        self.max_grids = max_grids

    def generate_signals(self, df):
        signals = df.copy()
        signals['ma'] = df['close'].rolling(window=self.window).mean()
        signals['std'] = df['close'].rolling(window=self.window).std()
        signals['upper_band'] = signals['ma'] + (signals['std'] * self.num_std)
        signals['lower_band'] = signals['ma'] - (signals['std'] * self.num_std)
        
        signals['position'] = 0.0
        current_position = 0.0
        position_list = []
        
        # Grid State
        last_grid_price = 0.0
        grids_sold = 0
        holding_main = False
        
        for row in signals.itertuples(index=False):
            if pd.isna(row.upper_band):
                position_list.append(current_position)
                continue
                
            # Main Strategy
            if row.close < row.lower_band:
                # Buy Signal (Entry)
                current_position = 1.0
                holding_main = True
                last_grid_price = row.close
                grids_sold = 0
            
            elif row.close > row.upper_band:
                # Sell Signal (Exit)
                current_position = 0.0
                holding_main = False
                last_grid_price = 0.0
                grids_sold = 0
                
            # Grid Logic (Only if holding)
            elif holding_main:
                # Check for Grid Sell (Price Rises)
                # If price > last * (1 + step)
                if row.close > last_grid_price * (1 + self.grid_step):
                    if grids_sold < self.max_grids:
                        # Sell one grid unit
                        current_position -= self.grid_qty
                        grids_sold += 1
                        last_grid_price = row.close # Update reference price
                
                # Check for Grid Buy Back (Price Falls)
                # If price < last * (1 - step)
                elif row.close < last_grid_price * (1 - self.grid_step):
                    if grids_sold > 0:
                        # Buy back one grid unit
                        current_position += self.grid_qty
                        grids_sold -= 1
                        last_grid_price = row.close # Update reference price
            
            # Ensure bounds and precision
            current_position = max(0.0, min(1.0, current_position))
            current_position = round(current_position, 2)
            position_list.append(current_position)
            
        signals['position'] = position_list
        signals['signal'] = signals['position'].diff().fillna(signals['position'])
        
        return signals

class MA40GradualStrategy(BaseStrategy):
    def __init__(self, window=40, step=0.1):
        super().__init__(f"MA ({window}) Gradual +/-{step:.0%}")
        self.window = window
        self.step = step

    def generate_signals(self, df):
        signals = df.copy()
        signals['ma'] = df['close'].rolling(window=self.window).mean()
        
        signals['signal'] = 0.0
        signals['position'] = 0.0
        
        current_position = 0.0
        position_list = []
        
        for row in signals.itertuples(index=False):
            if pd.isna(row.ma):
                position_list.append(current_position)
                continue

            if row.close < row.ma:
                # Buy 10%
                current_position = min(current_position + self.step, 1.0)
            elif row.close > row.ma:
                # Sell 10%
                current_position = max(current_position - self.step, 0.0)
            
            # Ensure floating point precision doesn't cause issues
            current_position = round(current_position, 2)
            
            position_list.append(current_position)
            
        signals['position'] = position_list
        signals['signal'] = signals['position'].diff().fillna(signals['position'])
        return signals

class DualMAStrategy(BaseStrategy):
    """双均线趋势跟随策略"""
    def __init__(self, short_window=10, long_window=60):
        super().__init__(f"Dual MA ({short_window}, {long_window})")
        self.short_window = short_window
        self.long_window = long_window

    def generate_signals(self, df):
        signals = df.copy()
        signals['ma_short'] = df['close'].rolling(window=self.short_window).mean()
        signals['ma_long'] = df['close'].rolling(window=self.long_window).mean()
        
        # 产生信号：短线上穿长线买入，下穿卖出
        signals['position'] = np.where(signals['ma_short'] > signals['ma_long'], 1.0, 0.0)
        # 填充NaN
        signals['position'] = pd.Series(signals['position'], index=signals.index).fillna(0.0)
        
        signals['signal'] = signals['position'].diff().fillna(signals['position'])
        return signals

class CombinedStrategy(BaseStrategy):
    """
    组合策略：
    可以将震荡策略（布林带）与趋势策略（双均线）按权重组合
    主策略用于提供 UI 显示需要的均线、上下轨等绘图数据（UI 兼容）
    """
    def __init__(self, main_strategy, main_weight, sub_strategy, sub_weight, name=None):
        name = name or f"Combined({main_weight*100:.0f}% {main_strategy.name} + {sub_weight*100:.0f}% {sub_strategy.name})"
        super().__init__(name)
        self.main_strategy = main_strategy
        self.main_weight = main_weight
        self.sub_strategy = sub_strategy
        self.sub_weight = sub_weight

    def __getattr__(self, name):
        """代理属性访问到主策略（为了兼容 UI，如 get_regime_summary 等方法）"""
        return getattr(self.main_strategy, name)

    def generate_signals(self, df):
        # 分别生成信号
        sig_main = self.main_strategy.generate_signals(df)
        sig_sub = self.sub_strategy.generate_signals(df)
        
        # 以主策略 DataFrame 为基底（包含布林带上下轨等所有图表列）
        signals = sig_main.copy()
        
        # 计算组合仓位
        pos_main = sig_main['position'].fillna(0.0)
        pos_sub = sig_sub['position'].fillna(0.0)
        
        signals['position'] = (pos_main * self.main_weight + pos_sub * self.sub_weight)
        
        # 重新计算最终合并信号（仓位变化）
        signals['signal'] = signals['position'].diff().fillna(signals['position'])
        
        # 附加副策略的调试字段（可选，这里加上前缀防止冲突）
        signals['sub_position'] = pos_sub
        
        return signals

class DividendPremiumStrategy(BaseStrategy):
    """
    股息率溢价基本面策略：
    当 股息率 - 十年期国债收益率 > buy_threshold 时买入满仓
    当 股息率 - 十年期国债收益率 < sell_threshold 时卖出空仓
    """
    def __init__(self, buy_threshold=0.02, sell_threshold=0.005):
        super().__init__(f"Dividend Premium ({buy_threshold*100:.1f}%, {sell_threshold*100:.1f}%)")
        self.buy_threshold = buy_threshold
        self.sell_threshold = sell_threshold

    def generate_signals(self, df):
        signals = df.copy()
        
        # 确保数据中包含基本面字段
        if 'dividend_premium' not in signals.columns:
            # 如果没有提供基本面数据，默认空仓
            signals['position'] = 0.0
            signals['signal'] = 0.0
            return signals
            
        signals['position'] = 0.0
        current_position = 0.0
        position_list = []
        
        for row in signals.itertuples(index=False):
            if pd.isna(row.dividend_premium):
                position_list.append(current_position)
                continue
                
            if row.dividend_premium > self.buy_threshold:
                current_position = 1.0
            elif row.dividend_premium < self.sell_threshold:
                current_position = 0.0
                
            position_list.append(current_position)
            
        signals['position'] = position_list
        signals['signal'] = signals['position'].diff().fillna(signals['position'])
        
        return signals

