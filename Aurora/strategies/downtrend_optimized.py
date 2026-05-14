import numpy as np
import pandas as pd
from typing import Dict, Tuple, List

class DownMarketStrategy:
    """
    下跌市场优化策略
    核心思想：超跌反弹 + 支撑位承接 + 金字塔仓位控制
    交易频率：根据信号强度动态调整，强信号立即交易，弱信号保持间隔
    风控机制：五层防控 - 固定止损 + 追踪止损 + 最大持仓限制 + 单日亏损限制 + 全局回撤限制
    多指标协同：RSI + MACD + 布林带 + ATR + 成交量确认
    """

    def __init__(self,
                 initial_capital: float = 100000,
                 max_position_pct: float = 0.3,
                 base_position_pct: float = 0.05,
                 stop_loss_pct: float = 0.008,
                 take_profit_pct: float = 0.01,
                 trailing_stop_pct: float = 0.015,
                 max_daily_loss_pct: float = 0.02,
                 max_total_drawdown_pct: float = 0.08,
                 max_pyramid_levels: int = 5,
                 pyramid_multiplier: float = 1.3,
                 rsi_oversold: int = 35,
                 rsi_extreme_oversold: int = 25,
                 volume_surge_ratio: float = 1.5,
                 support_lookback: int = 20,
                 base_trade_interval: int = 0):
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.max_position_pct = max_position_pct
        self.base_position_pct = base_position_pct
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.trailing_stop_pct = trailing_stop_pct
        self.max_daily_loss_pct = max_daily_loss_pct
        self.max_total_drawdown_pct = max_total_drawdown_pct
        self.max_pyramid_levels = max_pyramid_levels
        self.pyramid_multiplier = pyramid_multiplier
        self.rsi_oversold = rsi_oversold
        self.rsi_extreme_oversold = rsi_extreme_oversold
        self.volume_surge_ratio = volume_surge_ratio
        self.support_lookback = support_lookback
        self.base_trade_interval = base_trade_interval

        self.position = 0
        self.avg_cost = 0
        self.pyramid_level = 0
        self.last_trade_idx = -base_trade_interval
        self.trades = []
        self.daily_returns = []
        
        self.signal_interval_map = {
            "extreme_oversold": 0,
            "volume_surge_oversold": 0,
            "support_bounce": 1,
            "consecutive_down_reversal": 2
        }
        
        self.trailing_stop_price = None
        self.highest_price_since_entry = None
        self.daily_start_capital = initial_capital
        self.max_capital = initial_capital
        
        self.rsi_period = 14
        self.macd_fast = 12
        self.macd_slow = 26
        self.macd_signal = 9
        self.bollinger_period = 20
        self.bollinger_std = 2
        self.atr_period = 14
        
        self.constellation_levels = [
            {'threshold': 0.02, 'allocation': 0.1, 'max_position': 0.15},
            {'threshold': 0.04, 'allocation': 0.15, 'max_position': 0.35},
            {'threshold': 0.06, 'allocation': 0.2, 'max_position': 0.55},
            {'threshold': 0.08, 'allocation': 0.25, 'max_position': 0.75},
            {'threshold': 0.10, 'allocation': 0.3, 'max_position': 1.0},
        ]

    def calculate_rsi(self, prices: np.ndarray, period: int = 14) -> float:
        if len(prices) < period + 1:
            return 50
        deltas = np.diff(prices[-period-1:])
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        avg_gain = np.mean(gains)
        avg_loss = np.mean(losses)
        if avg_loss == 0:
            return 100
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))
    
    def calculate_multi_period_rsi(self, prices: np.ndarray) -> Tuple[float, float, float]:
        rsi_7 = self.calculate_rsi(prices, 7)
        rsi_14 = self.calculate_rsi(prices, 14)
        rsi_28 = self.calculate_rsi(prices, 28)
        return rsi_7, rsi_14, rsi_28
    
    def calculate_macd(self, prices: np.ndarray) -> Tuple[float, float, float]:
        if len(prices) < self.macd_slow + self.macd_signal:
            return 0, 0, 0
        prices_series = pd.Series(prices)
        ema12 = prices_series.ewm(span=self.macd_fast, adjust=False).mean()
        ema26 = prices_series.ewm(span=self.macd_slow, adjust=False).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=self.macd_signal, adjust=False).mean()
        histogram = macd - signal
        return macd.iloc[-1], signal.iloc[-1], histogram.iloc[-1]
    
    def calculate_bollinger_bands(self, prices: np.ndarray) -> Tuple[float, float, float]:
        if len(prices) < self.bollinger_period:
            return prices[-1] * 1.05, prices[-1], prices[-1] * 0.95
        prices_series = pd.Series(prices)
        ma = prices_series.rolling(window=self.bollinger_period).mean().iloc[-1]
        std = prices_series.rolling(window=self.bollinger_period).std().iloc[-1]
        if std == 0:
            std = 0.01
        upper = ma + (std * self.bollinger_std)
        lower = ma - (std * self.bollinger_std)
        return upper, ma, lower

    def find_support_levels(self, prices: np.ndarray, volumes: np.ndarray) -> Tuple[float, float]:
        if len(prices) < self.support_lookback:
            return prices[-1] * 0.95, prices[-1] * 0.90
        recent_prices = prices[-self.support_lookback:]
        recent_volumes = volumes[-self.support_lookback:]
        lows = []
        for i in range(1, len(recent_prices) - 1):
            if recent_prices[i] < recent_prices[i-1] and recent_prices[i] < recent_prices[i+1]:
                lows.append((recent_prices[i], recent_volumes[i]))
        if not lows:
            return prices[-1] * 0.95, prices[-1] * 0.90
        total_volume = sum(v for _, v in lows)
        if total_volume > 0:
            main_support = sum(p * v for p, v in lows) / total_volume
        else:
            main_support = np.mean([p for p, _ in lows])
        strong_support = main_support * 0.95
        return main_support, strong_support

    def check_reversal_signal(self, prices: np.ndarray, volumes: np.ndarray, current_idx: int) -> Tuple[bool, str]:
        if current_idx < 30:
            return False, ""
        
        current_price = prices[current_idx]
        current_volume = volumes[current_idx]
        
        rsi_7, rsi_14, rsi_28 = self.calculate_multi_period_rsi(prices[:current_idx+1])
        macd, signal, histogram = self.calculate_macd(prices[:current_idx+1])
        upper_band, middle_band, lower_band = self.calculate_bollinger_bands(prices[:current_idx+1])
        
        avg_volume_short = np.mean(volumes[current_idx-5:current_idx]) if current_idx >= 5 else np.mean(volumes[:current_idx+1])
        avg_volume_long = np.mean(volumes[current_idx-20:current_idx]) if current_idx >= 20 else np.mean(volumes[:current_idx+1])
        volume_ratio_short = current_volume / avg_volume_short if avg_volume_short > 0 else 1
        volume_ratio_long = current_volume / avg_volume_long if avg_volume_long > 0 else 1

        if rsi_7 < self.rsi_extreme_oversold and rsi_14 < self.rsi_oversold and rsi_28 < 45:
            if volume_ratio_short > self.volume_surge_ratio and histogram > 0 and macd > signal:
                return True, "extreme_oversold"
        
        if rsi_14 < self.rsi_oversold and volume_ratio_short > self.volume_surge_ratio:
            if histogram > 0 and current_price < lower_band * 1.02:
                return True, "volume_surge_oversold"

        main_support, strong_support = self.find_support_levels(prices[:current_idx+1], volumes[:current_idx+1])
        price_to_support = current_price / strong_support if strong_support > 0 else 1
        if price_to_support <= 1.01 and volume_ratio_short > 1.5:
            if rsi_14 < 35 and histogram > 0:
                return True, "support_bounce"

        if current_idx >= 10:
            recent_returns = [(prices[i] - prices[i-1]) / prices[i-1] for i in range(current_idx-9, current_idx+1)]
            consecutive_downs = sum(1 for r in recent_returns[:-1] if r < -0.002)
            if consecutive_downs >= 5 and recent_returns[-1] > 0.002:
                if volume_ratio_short > 1.5 and rsi_7 < 30 and histogram > 0:
                    return True, "consecutive_down_reversal"

        return False, ""

    def calculate_position_size(self, current_price: float, signal_type: str) -> float:
        base_position = self.capital * self.base_position_pct
        signal_multipliers = {
            "extreme_oversold": 1.5,
            "volume_surge_oversold": 1.2,
            "support_bounce": 1.3,
            "consecutive_down_reversal": 1.0
        }
        signal_mult = signal_multipliers.get(signal_type, 1.0)
        pyramid_mult = self.pyramid_multiplier ** self.pyramid_level
        position_value = base_position * signal_mult * pyramid_mult
        max_position_value = self.capital * self.max_position_pct
        position_value = min(position_value, max_position_value)
        shares = int(position_value / current_price)
        return shares

    def execute_trade(self, idx: int, price: float, volume: float, signal_type: str, action: str) -> Dict:
        trade = {
            'idx': idx,
            'price': price,
            'volume': volume,
            'signal': signal_type,
            'action': action,
            'position_before': self.position,
            'capital_before': self.capital
        }

        if action == 'buy':
            shares = self.calculate_position_size(price, signal_type)
            cost = shares * price
            if cost <= self.capital:
                total_cost = self.position * self.avg_cost + cost
                self.position += shares
                self.avg_cost = total_cost / self.position if self.position > 0 else 0
                self.capital -= cost
                self.pyramid_level = min(self.pyramid_level + 1, self.max_pyramid_levels)
                trade['shares'] = shares
                trade['cost'] = cost
                trade['position_after'] = self.position
                trade['capital_after'] = self.capital
        elif action == 'sell':
            if self.position > 0:
                revenue = self.position * price
                self.capital += revenue
                trade['shares'] = self.position
                trade['revenue'] = revenue
                trade['position_after'] = 0
                trade['capital_after'] = self.capital
                self.pyramid_level = 0
                self.position = 0
                self.avg_cost = 0
                self.trailing_stop_price = None
                self.highest_price_since_entry = None

        self.last_trade_idx = idx
        current_total = self.capital + (self.position * price if self.position > 0 else 0)
        if current_total > self.max_capital:
            self.max_capital = current_total
        self.trades.append(trade)
        return trade

    def check_risk_controls(self, current_price: float) -> str:
        if self.position == 0:
            return 'hold'
        
        current_total = self.capital + self.position * current_price
        daily_loss = (self.daily_start_capital - current_total) / self.daily_start_capital
        total_drawdown = (self.max_capital - current_total) / self.max_capital
        
        if daily_loss >= self.max_daily_loss_pct:
            return 'daily_limit'
        
        if total_drawdown >= self.max_total_drawdown_pct:
            return 'total_limit'
        
        return 'hold'
    
    def check_stop_loss_take_profit(self, current_price: float) -> str:
        if self.position == 0:
            return 'hold'
        
        risk_action = self.check_risk_controls(current_price)
        if risk_action != 'hold':
            return risk_action
        
        if self.avg_cost > 0:
            return_pct = (current_price - self.avg_cost) / self.avg_cost
        else:
            return 'hold'
        
        if self.highest_price_since_entry is not None:
            if current_price > self.highest_price_since_entry:
                self.highest_price_since_entry = current_price
                self.trailing_stop_price = current_price * (1 - self.trailing_stop_pct)
            
            if self.trailing_stop_price is not None and current_price <= self.trailing_stop_price:
                return 'trailing_stop'
        
        if return_pct <= -self.stop_loss_pct:
            return 'stop_loss'
        
        if return_pct >= self.take_profit_pct:
            return 'take_profit'
        
        return 'hold'

    def backtest(self, data: pd.DataFrame) -> Dict:
        prices = data['close'].values
        volumes = data['volume'].values
        dates = data['date'].values
        
        current_day = None

        for i in range(len(prices)):
            current_price = prices[i]
            
            if dates is not None and len(dates) > i:
                day = dates[i].date() if hasattr(dates[i], 'date') else dates[i]
                if day != current_day:
                    current_day = day
                    self.daily_start_capital = self.capital + self.position * current_price
            
            action = self.check_stop_loss_take_profit(current_price)

            if action in ['stop_loss', 'take_profit', 'trailing_stop', 'daily_limit', 'total_limit']:
                self.execute_trade(i, current_price, volumes[i], action, 'sell')
                continue

            has_signal, signal_type = self.check_reversal_signal(prices, volumes, i)
            
            if has_signal:
                required_interval = self.signal_interval_map.get(signal_type, self.base_trade_interval)
                
                if i - self.last_trade_idx >= required_interval:
                    if self.position == 0:
                        self.highest_price_since_entry = current_price
                        self.trailing_stop_price = current_price * (1 - self.trailing_stop_pct)
                        self.execute_trade(i, current_price, volumes[i], signal_type, 'buy')
                    elif self.pyramid_level < self.max_pyramid_levels:
                        self.execute_trade(i, current_price, volumes[i], signal_type, 'buy')

            if self.position > 0 and current_price > self.highest_price_since_entry:
                self.highest_price_since_entry = current_price
                self.trailing_stop_price = current_price * (1 - self.trailing_stop_pct)

        self._calculate_daily_returns(prices)
        return self._generate_report()

    def _calculate_daily_returns(self, prices: np.ndarray):
        for i in range(1, len(prices)):
            if self.position > 0:
                daily_return = (prices[i] - prices[i-1]) / prices[i-1]
            else:
                daily_return = 0
            self.daily_returns.append(daily_return)

    def _generate_report(self) -> Dict:
        if not self.trades:
            return {'total_return': 0, 'total_trades': 0, 'win_rate': 0, 'max_drawdown': 0, 'sharpe_ratio': 0,
                    'final_capital': self.capital, 'total_buys': 0, 'total_sells': 0}

        total_return = (self.capital - self.initial_capital) / self.initial_capital
        buy_trades = [t for t in self.trades if t['action'] == 'buy']
        sell_trades = [t for t in self.trades if t['action'] == 'sell']
        total_trades = len(buy_trades) + len(sell_trades)
        winning_trades = 0
        for sell in sell_trades:
            idx = self.trades.index(sell) - 1
            if idx >= 0:
                buy = self.trades[idx]
                if buy['action'] == 'buy':
                    if sell['revenue'] > buy['cost']:
                        winning_trades += 1
        win_rate = winning_trades / len(sell_trades) if sell_trades else 0
        peak = self.initial_capital
        max_drawdown = 0
        for trade in self.trades:
            if trade['action'] == 'buy':
                current_value = trade['capital_after']
                if current_value > peak:
                    peak = current_value
                drawdown = (peak - current_value) / peak
                max_drawdown = max(max_drawdown, drawdown)
        if self.daily_returns:
            avg_return = np.mean(self.daily_returns)
            std_return = np.std(self.daily_returns)
            sharpe_ratio = avg_return / std_return * np.sqrt(252) if std_return > 0 else 0
        else:
            sharpe_ratio = 0

        return {
            'total_return': total_return,
            'total_trades': total_trades,
            'win_rate': win_rate,
            'max_drawdown': max_drawdown,
            'sharpe_ratio': sharpe_ratio,
            'final_capital': self.capital,
            'total_buys': len(buy_trades),
            'total_sells': len(sell_trades)
        }


if __name__ == "__main__":
    np.random.seed(42)
    
    print("=== 日级数据测试 ===")
    n_days = 500
    dates = pd.date_range('2020-01-01', periods=n_days, freq='D')
    trend = np.linspace(100, 60, n_days)
    noise = np.random.normal(0, 2, n_days)
    prices = trend + noise
    prices = np.maximum(prices, 50)
    volumes = np.random.uniform(1000000, 5000000, n_days)
    data_daily = pd.DataFrame({
        'date': dates,
        'open': prices,
        'high': prices * 1.02,
        'low': prices * 0.98,
        'close': prices,
        'volume': volumes
    })

    strategy_daily = DownMarketStrategy(
        initial_capital=100000,
        max_position_pct=0.3,
        base_position_pct=0.08,
        stop_loss_pct=0.03,
        take_profit_pct=0.05,
        max_pyramid_levels=3,
        pyramid_multiplier=1.5,
        rsi_oversold=35,
        rsi_extreme_oversold=25,
        volume_surge_ratio=1.3,
        base_trade_interval=0
    )

    results_daily = strategy_daily.backtest(data_daily)

    print("下跌市场策略优化结果(日级):")
    print(f"总收益率: {results_daily['total_return']*100:.2f}%")
    print(f"总交易次数: {results_daily['total_trades']}")
    print(f"胜率: {results_daily['win_rate']*100:.2f}%")
    print(f"最大回撤: {results_daily['max_drawdown']*100:.2f}%")
    print(f"夏普比率: {results_daily['sharpe_ratio']:.2f}")
    print(f"最终资金: {results_daily['final_capital']:.2f}")

    print("\n=== 分钟级数据测试 ===")
    n_minutes = 500 * 24 * 60
    dates_min = pd.date_range('2020-01-01', periods=n_minutes, freq='T')
    base_price = 100
    trend_min = np.linspace(base_price, base_price * 0.6, n_minutes)
    volatility = 0.002
    noise_min = np.random.normal(0, base_price * volatility, n_minutes)
    prices_min = trend_min + noise_min
    prices_min = np.maximum(prices_min, base_price * 0.5)
    volumes_min = np.random.uniform(10000, 100000, n_minutes)
    data_minute = pd.DataFrame({
        'date': dates_min,
        'open': prices_min,
        'high': prices_min * (1 + np.random.uniform(0, 0.005, n_minutes)),
        'low': prices_min * (1 - np.random.uniform(0, 0.005, n_minutes)),
        'close': prices_min,
        'volume': volumes_min
    })

    strategy_minute = DownMarketStrategy(
        initial_capital=100000,
        max_position_pct=0.3,
        base_position_pct=0.02,
        stop_loss_pct=0.005,
        take_profit_pct=0.01,
        max_pyramid_levels=5,
        pyramid_multiplier=1.3,
        rsi_oversold=35,
        rsi_extreme_oversold=25,
        volume_surge_ratio=2.0,
        base_trade_interval=0
    )

    results_minute = strategy_minute.backtest(data_minute)

    print("下跌市场策略优化结果(分钟级):")
    print(f"总收益率: {results_minute['total_return']*100:.2f}%")
    print(f"总交易次数: {results_minute['total_trades']}")
    print(f"胜率: {results_minute['win_rate']*100:.2f}%")
    print(f"最大回撤: {results_minute['max_drawdown']*100:.2f}%")
    print(f"夏普比率: {results_minute['sharpe_ratio']:.2f}")
    print(f"最终资金: {results_minute['final_capital']:.2f}")
    print(f"日均交易次数: {results_minute['total_trades']/500:.2f}")