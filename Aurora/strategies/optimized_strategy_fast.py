#!/usr/bin/env python3
"""
优化后的交易策略 - 快速测试版
基于DeepSeek的建议，针对横盘、波动、下跌市场优化
"""
import random
import numpy as np
import pandas as pd

class MarketTypeDetector:
    """市场类型检测器"""
    
    def __init__(self):
        self.price_history = []
    
    def detect(self, price):
        self.price_history.append(price)
        if len(self.price_history) < 20:
            return 'unknown'
        
        recent = np.array(self.price_history[-20:])
        returns = np.diff(recent) / recent[:-1]
        
        volatility = np.std(returns)
        trend = (recent[-1] - recent[0]) / recent[0]
        
        if abs(trend) < 0.01 and volatility < 0.015:
            return 'sideways'  # 横盘
        elif trend < -0.01:
            return 'downtrend'  # 下跌
        elif volatility > 0.02:
            return 'volatile'  # 波动
        else:
            return 'uptrend'  # 上涨

class OptimizedTradingAgent:
    """优化后的交易代理"""
    
    def __init__(self, initial_capital=100000):
        self.capital = initial_capital
        self.initial_capital = initial_capital
        self.position = 0
        self.position_value = 0
        self.entry_price = 0
        
        self.price_history = []
        self.market_detector = MarketTypeDetector()
        
        # 市场自适应参数
        self.market_params = {
            'sideways': {
                'position_size': 0.05,  # 极小仓位
                'stop_loss': 0.015,
                'take_profit': 0.02,
                'max_trades': 2
            },
            'downtrend': {
                'position_size': 0.03,  # 极小仓位
                'stop_loss': 0.01,
                'take_profit': 0.015,
                'max_trades': 1
            },
            'volatile': {
                'position_size': 0.08,
                'stop_loss': 0.03,
                'take_profit': 0.04,
                'max_trades': 3
            },
            'uptrend': {
                'position_size': 0.15,
                'stop_loss': 0.03,
                'take_profit': 0.05,
                'max_trades': 5
            },
            'unknown': {
                'position_size': 0.1,
                'stop_loss': 0.02,
                'take_profit': 0.03,
                'max_trades': 3
            }
        }
        
        self.trade_count = 0
        self.winning_trades = 0
        self.total_trades = 0
        
        self.current_market = 'unknown'
    
    def update(self, price):
        self.price_history.append(price)
        self.position_value = self.position * price
        
        # 检测市场类型
        self.current_market = self.market_detector.detect(price)
        params = self.market_params[self.current_market]
        
        # 交易决策
        action = self._make_decision(price, params)
        
        # 执行交易
        if action == 'buy':
            self._execute_buy(price, params)
        elif action == 'sell':
            self._execute_sell(price)
        
        return action
    
    def _make_decision(self, price, params):
        if self.current_market in ['sideways', 'downtrend']:
            # 横盘和下跌市场：严格控制，只做超跌反弹
            if len(self.price_history) >= 10:
                recent_low = min(self.price_history[-10:])
                price_drop = (price - recent_low) / recent_low
                
                # 超跌反弹信号
                if price_drop < -0.02 and self.position == 0:
                    return 'buy'
                
                # 持有多头，触及止损或止盈
                if self.position > 0:
                    pnl = (price - self.entry_price) / self.entry_price
                    if pnl <= -params['stop_loss'] or pnl >= params['take_profit']:
                        return 'sell'
        
        elif self.current_market == 'volatile':
            # 波动市场：高抛低吸
            if len(self.price_history) >= 5:
                ma5 = np.mean(self.price_history[-5:])
                
                if price < ma5 * 0.98 and self.position == 0:
                    return 'buy'
                if price > ma5 * 1.02 and self.position > 0:
                    return 'sell'
        
        elif self.current_market == 'uptrend':
            # 上涨市场：持有或加仓
            if len(self.price_history) >= 5:
                ma5 = np.mean(self.price_history[-5:])
                
                if price > ma5 and self.position == 0:
                    return 'buy'
                if self.position > 0:
                    pnl = (price - self.entry_price) / self.entry_price
                    if pnl >= params['take_profit']:
                        return 'sell'
        
        return 'hold'
    
    def _execute_buy(self, price, params):
        if self.trade_count >= params['max_trades']:
            return
        
        max_invest = self.capital * params['position_size']
        shares = int(max_invest / price)
        
        if shares > 0:
            cost = shares * price
            fee = cost * 0.0001
            
            self.capital -= (cost + fee)
            self.position += shares
            self.entry_price = price
            self.trade_count += 1
            self.total_trades += 1
    
    def _execute_sell(self, price):
        if self.position > 0:
            proceeds = self.position * price
            fee = proceeds * 0.0001
            profit = proceeds - fee - self.position * self.entry_price
            
            self.capital += (proceeds - fee)
            
            if profit > 0:
                self.winning_trades += 1
            
            self.position = 0
            self.position_value = 0
            self.position_value = 0
            self.trade_count = 0
            self.total_trades += 1
    
    def get_performance(self):
        total_value = self.capital + self.position_value
        total_return = (total_value - self.initial_capital) / self.initial_capital
        win_rate = self.winning_trades / self.total_trades if self.total_trades > 0 else 0
        
        return {
            'total_value': total_value,
            'total_return': total_return,
            'total_trades': self.total_trades,
            'win_rate': win_rate,
            'market': self.current_market
        }

def test_optimized_strategy():
    """测试优化后的策略"""
    print("=" * 60)
    print("优化后的交易策略 - 快速测试")
    print("=" * 60)
    
    test_days = 10
    minutes_per_day = 390
    base_price = 100
    
    # 测试不同市场类型
    market_types = {
        '横盘': {'mean': 0, 'std': 0.001},
        '上涨': {'mean': 0.0008, 'std': 0.001},
        '下跌': {'mean': -0.0008, 'std': 0.001},
        '波动': {'mean': 0, 'std': 0.002}
    }
    
    results = []
    
    for name, params in market_types.items():
        print(f"\n测试市场: {name}")
        
        agent = OptimizedTradingAgent(initial_capital=100000)
        
        # 生成数据
        np.random.seed(42)
        returns = np.random.normal(params['mean'], params['std'], test_days * minutes_per_day)
        prices = base_price * np.cumprod(1 + returns)
        
        # 运行策略
        for price in prices:
            agent.update(price)
        
        # 获取结果
        perf = agent.get_performance()
        results.append({
            '市场': name,
            '最终价值': perf['total_value'],
            '收益率': perf['total_return'],
            '交易次数': perf['total_trades'],
            '胜率': perf['win_rate']
        })
        
        print(f"  最终价值: {perf['total_value']:,.0f}")
        print(f"  收益率: {perf['total_return']:.2%}")
        print(f"  交易次数: {perf['total_trades']}")
        print(f"  胜率: {perf['win_rate']:.2%}")
    
    # 输出汇总
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    df = pd.DataFrame(results)
    print(df.to_string(formatters={
        '最终价值': '{:,.0f}'.format,
        '收益率': '{:.2%}'.format,
        '胜率': '{:.2%}'.format
    }))

if __name__ == "__main__":
    test_optimized_strategy()