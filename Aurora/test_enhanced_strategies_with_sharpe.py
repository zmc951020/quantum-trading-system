#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
增强策略回测测试 - 包含夏普比率、最大回撤、胜率等完整指标
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Any
import sys
import os

# 添加策略目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from strategies.newton_momentum_enhanced import NewtonMomentumEnhanced
from strategies.thermodynamic_entropy_enhanced import ThermodynamicEntropyEnhanced


class BacktestEngine:
    """增强策略回测引擎"""
    
    def __init__(self, initial_balance: float = 100000):
        self.initial_balance = initial_balance
        
    def generate_test_data(self, days: int = 300) -> pd.DataFrame:
        """生成测试数据"""
        np.random.seed(42)
        
        # 生成带趋势的价格序列
        t = np.linspace(0, days, days)
        
        # 多周期波动
        trend = 0.002 * t  # 长期趋势
        cycle1 = 0.05 * np.sin(2 * np.pi * t / 50)
        cycle2 = 0.02 * np.sin(2 * np.pi * t / 20)
        noise = np.random.normal(0, 0.01, days)
        
        # 合成收益率
        returns = trend + cycle1 + cycle2 + noise
        
        # 转换为价格（从100开始）
        prices = np.cumprod(1 + returns) * 100.0
        
        # 成交量
        volumes = 1000 + np.random.randint(-200, 200, days)
        
        # 创建DataFrame
        data = pd.DataFrame({
            'date': pd.date_range(start='2024-01-01', periods=days),
            'close': prices,
            'volume': volumes
        })
        
        return data
    
    def run_backtest(self, strategy_class, data: pd.DataFrame) -> Dict[str, Any]:
        """运行单策略回测"""
        initial_balance = self.initial_balance
        strategy = strategy_class(base_price=data['close'].iloc[0], initial_balance=initial_balance)
        
        equity_history = [initial_balance]
        trades = []
        positions = []
        
        # 运行回测
        for _, row in data.iterrows():
            result = strategy.update_price(row['close'], row['volume'])
            
            # 计算当前权益
            current_equity = strategy.current_balance + strategy.position * row['close']
            equity_history.append(current_equity)
            
            positions.append(strategy.position)
            
            if result['action'] in ['buy', 'sell']:
                trades.append({
                    'action': result['action'],
                    'price': result['price'],
                    'balance': result['balance']
                })
        
        # 计算性能指标
        equity_array = np.array(equity_history)
        returns = np.diff(equity_array) / equity_array[:-1]
        
        annual_return = ((equity_array[-1] / initial_balance) ** (252 / len(data)) - 1)
        volatility = np.std(returns) * np.sqrt(252)
        
        return {
            'final_balance': equity_array[-1],
            'total_return': (equity_array[-1] - initial_balance) / initial_balance,
            'annual_return': annual_return,
            'volatility': volatility,
            'sharpe_ratio': self._calculate_sharpe_ratio(returns),
            'max_drawdown': self._calculate_max_drawdown(equity_array),
            'win_rate': self._calculate_win_rate(trades),
            'trades': len(trades),
            'equity_history': equity_history,
            'positions': positions
        }
    
    def _calculate_sharpe_ratio(self, returns, risk_free_rate: float = 0.02) -> float:
        """计算夏普比率"""
        if len(returns) < 2:
            return 0.0
        
        annual_return = np.mean(returns) * 252
        annual_volatility = np.std(returns) * np.sqrt(252)
        
        if annual_volatility == 0:
            return 0.0
        
        return (annual_return - risk_free_rate) / annual_volatility
    
    def _calculate_max_drawdown(self, equity) -> float:
        """计算最大回撤"""
        if len(equity) < 2:
            return 0.0
        
        running_max = np.maximum.accumulate(equity)
        drawdown = (equity - running_max) / running_max
        return np.min(drawdown)
    
    def _calculate_win_rate(self, trades) -> float:
        """计算胜率"""
        if len(trades) == 0:
            return 0.0
        
        wins = 0
        last_buy_price = None
        for trade in trades:
            if trade['action'] == 'buy':
                last_buy_price = trade['price']
            elif trade['action'] == 'sell' and last_buy_price is not None:
                if trade['price'] > last_buy_price:
                    wins += 1
        
        trade_count = len(trades) // 2 if len(trades) >= 2 else 0
        return wins / trade_count if trade_count > 0 else 0.0
    
    def compare_strategies(self, strategies: Dict[str, Any], data: pd.DataFrame):
        """对比多个策略"""
        print("=" * 80)
        print("回测结果对比")
        print("=" * 80)
        
        results = {}
        
        for name, strategy_class in strategies.items():
            print(f"\n正在回测: {name}...")
            results[name] = self.run_backtest(strategy_class, data)
        
        print("\n" + "=" * 80)
        print("策略性能对比")
        print("=" * 80)
        
        # 打印表头
        print(f"{'策略名称':<35} {'年化收益':<12} {'夏普比率':<12} {'最大回撤':<12} {'胜率':<10} {'交易次数':<10}")
        print("-" * 80)
        
        for name, result in results.items():
            print(f"{name:<35} "
                  f"{result['annual_return'] * 100:>8.2f}% "
                  f"{result['sharpe_ratio']:>12.2f} "
                  f"{result['max_drawdown'] * 100:>8.2f}% "
                  f"{result['win_rate'] * 100:>8.2f}% "
                  f"{result['trades']:>10}")
        
        print(f"\n初始资金: {self.initial_balance}")
        print(f"回测天数: {len(data)}天")
        print("=" * 80)
        
        return results


def main():
    # 创建回测引擎
    engine = BacktestEngine(initial_balance=100000)
    
    # 生成测试数据
    data = engine.generate_test_data(days=300)
    
    # 定义要测试的策略
    strategies_to_test = {
        'NewtonMomentumEnhanced': NewtonMomentumEnhanced,
        'ThermodynamicEntropyEnhanced': ThermodynamicEntropyEnhanced
    }
    
    # 运行回测对比
    results = engine.compare_strategies(strategies_to_test, data)
    
    print("\n" + "=" * 80)
    print("回测详情")
    print("=" * 80)
    
    for name, result in results.items():
        print(f"\n--- {name} ---")
        print(f"初始资金: {engine.initial_balance}")
        print(f"最终资金: {result['final_balance']:.2f}")
        print(f"总收益: {result['total_return'] * 100:.2f}%")
        print(f"年化收益: {result['annual_return'] * 100:.2f}%")
        print(f"夏普比率: {result['sharpe_ratio']:.2f}")
        print(f"最大回撤: {result['max_drawdown'] * 100:.2f}%")
        print(f"胜率: {result['win_rate'] * 100:.2f}%")
        print(f"交易次数: {result['trades']}")
        print(f"波动率: {result['volatility'] * 100:.2f}%")


if __name__ == "__main__":
    main()
