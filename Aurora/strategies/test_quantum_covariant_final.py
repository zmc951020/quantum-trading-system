#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试最终完美版量子矩阵协变策略
"""

import numpy as np
import sys
import os

# 添加父目录到路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strategies.quantum_covariant_final import QuantumCovariantTradingSystem


def generate_simulation_data(days=10):
    """
    生成模拟数据
    
    Args:
        days: 数据天数
        
    Returns:
        模拟数据
    """
    total_minutes = days * 24 * 60 / 5  # 5分钟数据
    total_minutes = int(total_minutes)
    prices = np.zeros(total_minutes)
    prices[0] = 100.0

    # 生成混合行情：上涨 + 横盘 + 下跌
    for i in range(1, total_minutes):
        if i < total_minutes * 0.35:
            prices[i] = prices[i-1] * np.random.uniform(0.9992, 1.0018)
        elif i < total_minutes * 0.7:
            prices[i] = prices[i-1] * np.random.uniform(0.9988, 1.0012)
        else:
            prices[i] = prices[i-1] * np.random.uniform(0.9985, 1.0005)

    return prices


def test_strategy(strategy, data):
    """
    测试策略
    
    Args:
        strategy: 策略实例
        data: 测试数据
        
    Returns:
        测试结果
    """
    for i in range(20, len(data)):
        strategy.step(data[:i+1], now=i*60)
    
    final = strategy._equity(data[-1])
    ret_pct = (final - strategy.initial_capital) / strategy.initial_capital * 100
    win_rate = strategy.win_trades / (strategy.trade_count + 1e-8) * 100
    max_dd = (max(strategy.equity_curve) - min(strategy.equity_curve)) / max(strategy.equity_curve)
    
    return {
        "initial_capital": strategy.initial_capital,
        "final_capital": final,
        "total_return": ret_pct,
        "trade_count": strategy.trade_count,
        "win_rate": win_rate,
        "max_drawdown": max_dd * 100,
        "market_trades": strategy.market_trades
    }


def main():
    """
    主函数
    """
    print("测试最终完美版量子矩阵协变策略")
    print("="*80)
    
    # 生成模拟数据（分钟级）
    print("生成模拟数据...")
    data = generate_simulation_data(days=10)
    print(f"生成了 {len(data)} 分钟的模拟数据")
    print(f"价格范围: {data.min():.2f} - {data.max():.2f}")
    print("="*80)
    
    # 初始化策略
    print("初始化最终完美版量子矩阵协变策略...")
    strategy = QuantumCovariantTradingSystem()
    print("="*80)
    
    # 测试策略
    print("测试策略...")
    performance = test_strategy(strategy, data)
    print("="*80)
    
    # 输出测试结果
    print("测试结果:")
    print(f"初始资金: {performance['initial_capital']:.2f}")
    print(f"最终资金: {performance['final_capital']:.2f}")
    print(f"总收益率: {performance['total_return']:.2f}%")
    print(f"总交易次数: {performance['trade_count']}")
    print(f"胜率: {performance['win_rate']:.2f}%")
    print(f"最大回撤: {performance['max_drawdown']:.2f}%")
    print("="*80)
    
    # 输出各市场类型交易次数
    print("各市场类型交易次数:")
    for market_type, count in performance['market_trades'].items():
        print(f"{market_type}: {count} 次")
    
    print("="*80)
    print("测试完成！")


if __name__ == "__main__":
    main()
