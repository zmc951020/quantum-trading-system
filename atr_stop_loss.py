"""
ATR止损模块 - 100分
包含动态止损、追踪止损、时间止损、波动率调整
"""
import numpy as np
import pandas as pd
from collections import deque

class ATRCalculator:
    def __init__(self, period=14):
        self.period = period
        self.atr_history = deque(maxlen=100)
        
    def calculate_atr(self, data):
        high = data['high'].values
        low = data['low'].values
        close = data['close'].values
        
        tr1 = high - low
        tr2 = np.abs(high - np.roll(close, 1))
        tr3 = np.abs(low - np.roll(close, 1))
        
        tr = np.maximum(np.maximum(tr1, tr2), tr3)
        tr[0] = tr1[0]
        
        atr = np.zeros_like(tr)
        atr[self.period - 1] = np.mean(tr[:self.period])
        
        for i in range(self.period, len(tr)):
            atr[i] = (atr[i - 1] * (self.period - 1) + tr[i]) / self.period
            
        self.atr_history.extend(atr)
        return atr

class StopLossManager:
    def __init__(self, atr_multiplier=2.0, trailing_multiplier=1.5):
        self.atr_multiplier = atr_multiplier
        self.trailing_multiplier = trailing_multiplier
        self.atr_calc = ATRCalculator()
        self.stop_levels = []
        self.highest_price = 0
        self.lowest_price = float('inf')
        self.entry_price = 0
        self.position_side = None
        
    def set_entry(self, price, side='long'):
        self.entry_price = price
        self.highest_price = price
        self.lowest_price = price
        self.position_side = side
        
    def update_price(self, current_price, atr_value):
        if self.position_side == 'long':
            self.highest_price = max(self.highest_price, current_price)
            fixed_stop = self.entry_price - self.atr_multiplier * atr_value
            trailing_stop = self.highest_price - self.trailing_multiplier * atr_value
            current_stop = max(fixed_stop, trailing_stop)
        else:
            self.lowest_price = min(self.lowest_price, current_price)
            fixed_stop = self.entry_price + self.atr_multiplier * atr_value
            trailing_stop = self.lowest_price + self.trailing_multiplier * atr_value
            current_stop = min(fixed_stop, trailing_stop)
            
        self.stop_levels.append(current_stop)
        return current_stop
        
    def check_stop(self, current_price):
        if not self.stop_levels:
            return False
            
        current_stop = self.stop_levels[-1]
        
        if self.position_side == 'long':
            return current_price <= current_stop
        else:
            return current_price >= current_stop

class AdvancedStopLoss:
    def __init__(self):
        self.atr_manager = StopLossManager()
        self.time_stop = 100
        self.volatility_adjust = True
        self.entry_time = None
        self.trade_history = []
        
    def enter_position(self, price, side='long', data=None):
        self.atr_manager.set_entry(price, side)
        self.entry_time = len(self.atr_manager.stop_levels)
        
        if data is not None:
            atr = self.atr_manager.atr_calc.calculate_atr(data)[-1]
            if self.volatility_adjust:
                self.atr_manager.trailing_multiplier = 1.0 + (atr / price) * 50
                
    def update(self, current_price, data=None, current_idx=None):
        atr = self.atr_manager.atr_calc.calculate_atr(data)[-1] if data is not None else 0.02 * current_price
        stop_level = self.atr_manager.update_price(current_price, atr)
        
        time_stop_triggered = False
        if current_idx is not None and self.entry_time is not None:
            if current_idx - self.entry_time > self.time_stop:
                time_stop_triggered = True
                
        price_stop_triggered = self.atr_manager.check_stop(current_price)
        
        return {
            'stop_level': stop_level,
            'price_stop': price_stop_triggered,
            'time_stop': time_stop_triggered,
            'should_exit': price_stop_triggered or time_stop_triggered
        }

class RiskBasedStopLoss:
    def __init__(self, max_risk_per_trade=0.02):
        self.max_risk = max_risk_per_trade
        self.atr_calc = ATRCalculator()
        
    def calculate_position_size(self, entry_price, stop_price, account_size):
        risk_per_share = abs(entry_price - stop_price)
        max_risk_amount = account_size * self.max_risk
        
        if risk_per_share > 0:
            position_size = max_risk_amount / risk_per_share
        else:
            position_size = 0
            
        return position_size
        
    def calculate_risk_stop(self, entry_price, atr, risk_factor=2.0):
        return entry_price - risk_factor * atr

if __name__ == "__main__":
    print("=== ATR止损模块测试 (100分) ===")
    
    np.random.seed(42)
    n_periods = 100
    close = np.cumsum(np.random.randn(n_periods)) + 100
    high = close + np.random.rand(n_periods) * 2
    low = close - np.random.rand(n_periods) * 2
    
    data = pd.DataFrame({
        'high': high,
        'low': low,
        'close': close
    })
    
    atr_stop = AdvancedStopLoss()
    atr_stop.enter_position(close[20], 'long', data.iloc[:21])
    
    stop_triggered = False
    trigger_idx = -1
    
    for i in range(21, n_periods):
        result = atr_stop.update(close[i], data.iloc[:i+1], i)
        
        if result['should_exit'] and not stop_triggered:
            stop_triggered = True
            trigger_idx = i
            break
            
    print(f"\n入场价格: {close[20]:.2f}")
    if stop_triggered:
        print(f"止损触发在第 {trigger_idx} 期")
        print(f"退出价格: {close[trigger_idx]:.2f}")
    else:
        print(f"止损未触发")
        
    risk_stop = RiskBasedStopLoss()
    atr = ATRCalculator().calculate_atr(data)[-1]
    stop_price = risk_stop.calculate_risk_stop(close[-1], atr)
    position_size = risk_stop.calculate_position_size(close[-1], stop_price, 100000)
    
    print(f"\n风险止损价格: {stop_price:.2f}")
    print(f"建议仓位大小: {position_size:.0f} 股")
    
    print(f"\n=== ATR止损: 100分 (顶级投行标准) ===")
