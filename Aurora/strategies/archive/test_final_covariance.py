#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试最终协变策略
"""

import numpy as np
import pandas as pd
import sys
import os

# 添加父目录到路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strategies.final_covariance_strategy import FinalCovarianceStrategy


def generate_simulation_data(days=200, freq="5min", volatility=0.001, trend_strength=0.0001):
    """
    生成模拟数据
    
    Args:
        days: 数据天数
        freq: 数据频率
        volatility: 日波动率
        trend_strength: 趋势强度
        
    Returns:
        模拟数据
    """
    minutes_per_day = 24 * 60 / int(freq.split('min')[0])
    total_minutes = int(days * minutes_per_day)
    dates = pd.date_range("2024-01-01", periods=total_minutes, freq=freq)
    price = 100.0
    prices = []
    
    for i in range(len(dates)):
        # 添加趋势和随机波动
        price *= (1 + trend_strength + np.random.normal(0, volatility))
        prices.append(price)
    
    df = pd.DataFrame({
        "datetime": dates,
        "open": prices,
        "high": [p * (1 + np.random.uniform(0, 0.005)) for p in prices],
        "low": [p * (1 - np.random.uniform(0, 0.005)) for p in prices],
        "close": prices,
        "volume": [np.random.randint(500, 50000) for _ in prices]
    })
    
    return df


def test_strategy(strategy, data):
    """
    测试策略
    
    Args:
        strategy: 策略实例
        data: 测试数据
        
    Returns:
        测试结果
    """
    for i in range(120, len(data)):
        strategy.update_price(data.close.iloc[i], data.iloc[:i])
    
    performance = strategy.get_performance()
    
    return performance


def main():
    """
    主函数
    """
    print("测试最终协变策略")
    print("="*60)
    
    # 生成模拟数据（分钟级）
    print("生成模拟数据...")
    data = generate_simulation_data(days=10, freq="5min", volatility=0.001, trend_strength=0.0001)
    print(f"生成了 {len(data)} 分钟的模拟数据")
    print(f"价格范围: {data.close.min():.2f} - {data.close.max():.2f}")
    print("="*60)
    
    # 初始化策略
    print("初始化最终协变策略...")
    strategy = FinalCovarianceStrategy(initial_balance=100000)
    print("="*60)
    
    # 测试策略
    print("测试策略...")
    performance = test_strategy(strategy, data)
    print("="*60)
    
    # 输出测试结果
    print("测试结果:")
    print(f"初始资金: {performance['initial_balance']:.2f}")
    print(f"最终资金: {performance['final_balance']:.2f}")
    print(f"总收益率: {performance['total_return']:.2f}%")
    print(f"总交易次数: {performance['trade_count']}")
    print(f"胜率: {performance['win_rate']:.2f}%")
    print(f"最大回撤: {performance['max_drawdown']:.2f}%")
    print("="*60)
    
    # 输出各市场类型表现
    print("各市场类型表现分析:")
    print("市场类型                  交易次数       胜率          收益率")
    print("------------------------------------------------------------")
    
    for market_type, analysis in performance['market_type_analysis'].items():
        win_rate = (analysis["wins"] / analysis["trades"] * 100) if analysis["trades"] > 0 else 0
        return_rate = (analysis["return"] / performance['initial_balance'] * 100) if analysis["trades"] > 0 else 0
        print(f"{market_type:<24} {analysis['trades']:<10} {win_rate:<10.2f}% {return_rate:<10.2f}%")
    
    print("="*60)
    print("测试完成！")


if __name__ == "__main__":
    main()
