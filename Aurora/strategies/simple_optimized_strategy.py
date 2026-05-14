#!/usr/bin/env python3
"""
优化后的量化交易策略 - 简化版
核心功能：
1. 上涨市场：激进策略，保持高收益
2. 横盘市场：紧密网格，高抛低吸
3. 下跌市场：反转策略 + 金字塔承接
4. 波动市场：动态网格+指标配合
"""
import numpy as np
import pandas as pd

class StrategyOptimized:
    """优化后的交易策略"""
    
    def __init__(self, initial_capital=100000):
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.position = 0
        self.entry_price = 0
        self.current_price = 0
        
        # 交易记录
        self.trades = []
        self.winning_trades = 0
        
        # 价格历史
        self.price_history = []
        self.market_type = 'unknown'
        
        # RSI计算
        self.rsi_period = 14
        self.price_data = []
        
        # 策略参数 - 根据市场类型动态调整
        self.params = {
            'uptrend': {
                'grid_spacing': 0.005,
                'position_size': 0.2,
                'stop_loss': 0.02,
                'take_profit': 0.04,
                'max_position': 0.8
            },
            'sideways': {
                'grid_spacing': 0.002,
                'position_size': 0.08,
                'stop_loss': 0.015,
                'take_profit': 0.02,
                'max_position': 0.5
            },
            'downtrend': {
                'grid_spacing': 0.003,
                'position_size': 0.05,
                'stop_loss': 0.01,
                'take_profit': 0.015,
                'max_position': 0.3
            },
            'volatile': {
                'grid_spacing': 0.004,
                'position_size': 0.12,
                'stop_loss': 0.025,
                'take_profit': 0.035,
                'max_position': 0.6
            }
        }
        
        # 金字塔承接配置（下跌市场专用）
        self.pyramid_levels = [
            {'threshold': -0.02, 'weight': 0.1},
            {'threshold': -0.04, 'weight': 0.2},
            {'threshold': -0.06, 'weight': 0.3},
            {'threshold': -0.08, 'weight': 0.25},
            {'threshold': -0.10, 'weight': 0.15}
        ]
        
    def calculate_rsi(self, prices):
        """计算RSI指标"""
        if len(prices) < self.rsi_period + 1:
            return 50
        
        deltas = np.diff(prices)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        avg_gain = np.mean(gains[-self.rsi_period:])
        avg_loss = np.mean(losses[-self.rsi_period:])
        
        if avg_loss == 0:
            return 100
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    def detect_reversal(self, price):
        """检测反转信号 - 下跌市场专用"""
        self.price_data.append(price)
        
        if len(self.price_data) < self.rsi_period + 1:
            return False
        
        prices = np.array(self.price_data)
        rsi = self.calculate_rsi(prices)
        
        # RSI超卖阈值（RSI < 35表示超卖，可能反转）
        if rsi < 35:
            if len(prices) >= 20:
                recent_high = max(prices[-20:])
                drop = (price - recent_high) / recent_high
                if drop < -0.03:
                    return True
        
        return False
    
    def detect_market(self, price):
        """检测市场类型"""
        self.price_history.append(price)
        
        if len(self.price_history) < 30:
            return 'unknown'
        
        prices = np.array(self.price_history[-30:])
        returns = np.diff(prices) / prices[:-1]
        
        volatility = np.std(returns)
        trend = (prices[-1] - prices[0]) / prices[0]
        
        if trend > 0.03:
            self.market_type = 'uptrend'
        elif trend < -0.02:
            self.market_type = 'downtrend'
        elif volatility > 0.015:
            self.market_type = 'volatile'
        else:
            self.market_type = 'sideways'
            
        return self.market_type
    
    def get_current_params(self):
        """获取当前市场的策略参数"""
        return self.params.get(self.market_type, self.params['sideways'])
    
    def execute_trade(self, price):
        """执行交易"""
        self.current_price = price
        market = self.detect_market(price)
        
        if market == 'unknown':
            return 'hold'
        
        params = self.get_current_params()
        
        # 计算当前仓位价值
        position_value = self.position * price
        total_value = self.capital + position_value
        current_position_ratio = position_value / total_value if total_value > 0 else 0
        
        # 检查止损
        if self.position > 0 and self.entry_price > 0:
            loss = (price - self.entry_price) / self.entry_price
            if loss <= -params['stop_loss']:
                return self._sell(price, 'stop_loss')
        
        # 检查止盈
        if self.position > 0:
            profit = (price - self.entry_price) / self.entry_price
            if profit >= params['take_profit']:
                return self._sell(price, 'take_profit')
        
        # 买入决策
        if market == 'downtrend':
            # 下跌市场：优先使用反转策略
            if self.detect_reversal(price):
                # 反转信号确认，买入
                investment = self.capital * params['position_size'] * 2  # 反转时加大仓位
                shares = int(investment / price)
                if shares > 0:
                    return self._buy(price, shares)
            else:
                # 无反转信号，使用金字塔承接
                return self._pyramid_buy(price)
        elif self.position == 0 or current_position_ratio < params['max_position']:
            return self._grid_buy(price, params)
        
        return 'hold'
    
    def _grid_buy(self, price, params):
        """网格买入策略"""
        if self.position == 0:
            investment = self.capital * params['position_size']
            shares = int(investment / price)
            if shares > 0:
                return self._buy(price, shares)
        
        if self.entry_price > 0:
            drop = (price - self.entry_price) / self.entry_price
            if drop <= -params['grid_spacing']:
                investment = self.capital * params['position_size'] * 0.5
                shares = int(investment / price)
                if shares > 0:
                    return self._buy(price, shares)
        
        return 'hold'
    
    def _pyramid_buy(self, price):
        """金字塔承接策略 - 下跌市场"""
        if len(self.price_history) < 20:
            return 'hold'
        
        recent_high = max(self.price_history[-20:])
        drop_from_high = (price - recent_high) / recent_high
        
        total_weight = 0
        for level in self.pyramid_levels:
            if drop_from_high <= level['threshold']:
                total_weight += level['weight']
        
        position_value = self.position * price
        total_value = self.capital + position_value
        current_weight = position_value / total_value if total_value > 0 else 0
        
        # 只有当承接条件满足时才买入
        if total_weight > current_weight and total_weight <= 0.5:
            target_value = total_value * total_weight
            buy_value = target_value - position_value
            shares = int(buy_value / price)
            
            if shares > 0:
                return self._buy(price, shares)
        
        return 'hold'
    
    def _buy(self, price, shares):
        """执行买入"""
        cost = shares * price
        
        if cost <= self.capital:
            self.capital -= cost
            self.position += shares
            
            if self.entry_price == 0:
                self.entry_price = price
            else:
                self.entry_price = (self.entry_price * (self.position - shares) + price * shares) / self.position
            
            self.trades.append({
                'type': 'buy',
                'price': price,
                'shares': shares,
                'cost': cost
            })
            return 'buy'
        
        return 'hold'
    
    def _sell(self, price, reason):
        """执行卖出"""
        if self.position > 0:
            proceeds = self.position * price
            profit = proceeds - self.position * self.entry_price
            
            self.capital += proceeds
            
            if profit > 0:
                self.winning_trades += 1
            
            self.trades.append({
                'type': 'sell',
                'price': price,
                'shares': self.position,
                'proceeds': proceeds,
                'profit': profit,
                'reason': reason
            })
            
            self.position = 0
            self.entry_price = 0
            
            return 'sell'
        
        return 'hold'
    
    def get_performance(self):
        """获取性能指标"""
        position_value = self.position * self.current_price if self.current_price > 0 else 0
        total_value = self.capital + position_value
        total_return = (total_value - self.initial_capital) / self.initial_capital
        
        win_rate = self.winning_trades / len(self.trades) if self.trades else 0
        
        return {
            'total_value': total_value,
            'total_return': total_return,
            'total_trades': len(self.trades),
            'winning_trades': self.winning_trades,
            'win_rate': win_rate,
            'current_position': self.position,
            'capital': self.capital,
            'market_type': self.market_type
        }

def simulate_market(days=10, minutes_per_day=390, base_price=100, market_type='uptrend'):
    """生成模拟市场数据"""
    np.random.seed(42)
    
    if market_type == 'uptrend':
        returns = np.random.normal(0.0005, 0.001, days * minutes_per_day)
    elif market_type == 'sideways':
        returns = np.random.normal(0, 0.001, days * minutes_per_day)
    elif market_type == 'downtrend':
        returns = np.random.normal(-0.0003, 0.001, days * minutes_per_day)
    elif market_type == 'volatile':
        returns = np.random.normal(0, 0.0025, days * minutes_per_day)
    else:
        returns = np.random.normal(0, 0.001, days * minutes_per_day)
    
    prices = base_price * np.cumprod(1 + returns)
    return prices

def test_strategy():
    """测试策略"""
    print("=" * 70)
    print("优化后的量化交易策略测试（包含反转策略）")
    print("=" * 70)
    
    market_types = ['uptrend', 'sideways', 'downtrend', 'volatile']
    market_names = ['上涨市场', '横盘市场', '下跌市场', '波动市场']
    
    results = []
    
    for m_type, m_name in zip(market_types, market_names):
        print(f"\n测试市场: {m_name}")
        
        strategy = StrategyOptimized(initial_capital=100000)
        prices = simulate_market(days=10, market_type=m_type)
        
        for price in prices:
            strategy.execute_trade(price)
        
        perf = strategy.get_performance()
        results.append({
            '市场类型': m_name,
            '最终价值': perf['total_value'],
            '收益率': perf['total_return'],
            '交易次数': perf['total_trades'],
            '胜率': perf['win_rate']
        })
        
        print(f"  最终价值: {perf['total_value']:,.0f}")
        print(f"  收益率: {perf['total_return']:.2%}")
        print(f"  交易次数: {perf['total_trades']}")
        print(f"  胜率: {perf['win_rate']:.2%}")
    
    print("\n" + "=" * 70)
    print("测试结果汇总")
    print("=" * 70)
    df = pd.DataFrame(results)
    print(df.to_string(formatters={
        '最终价值': '{:,.0f}'.format,
        '收益率': '{:.2%}'.format,
        '胜率': '{:.2%}'.format
    }))

if __name__ == "__main__":
    test_strategy()