#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试高周转强化版量子矩阵协变策略
"""

import numpy as np
import pandas as pd
import sys
import os

# 添加父目录到路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strategies.quantum_covariant_high_turnover import QuantumCovariantTradingSystem


def generate_simulation_data(days=10, freq="5min"):
    """
    生成模拟数据
    
    Args:
        days: 数据天数
        freq: 数据频率
        
    Returns:
        模拟数据
    """
    minutes_per_day = 24 * 60 / int(freq.split('min')[0])
    total_minutes = int(days * minutes_per_day)
    dates = pd.date_range("2024-01-01", periods=total_minutes, freq=freq)
    base = 100.0
    price_series = np.zeros(total_minutes)
    price_series[0] = base

    # 生成混合行情：上涨 + 横盘 + 下跌
    for i in range(1, total_minutes):
        if i < total_minutes * 0.3:
            price_series[i] = price_series[i-1] * np.random.uniform(0.999, 1.002)
        elif i < total_minutes * 0.7:
            price_series[i] = price_series[i-1] * np.random.uniform(0.9985, 1.0015)
        else:
            price_series[i] = price_series[i-1] * np.random.uniform(0.998, 1.001)

    df = pd.DataFrame({
        "datetime": dates,
        "open": price_series,
        "high": price_series * np.random.uniform(1.0, 1.005, total_minutes),
        "low": price_series * np.random.uniform(0.995, 1.0, total_minutes),
        "close": price_series,
        "volume": np.random.randint(500, 50000, total_minutes)
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
    for i in range(20, len(data)):
        strategy.update_price(data.close.iloc[i], data.iloc[:i])
    
    performance = strategy.get_performance()
    
    return performance


def main():
    """
    主函数
    """
    print("测试高周转强化版量子矩阵协变策略")
    print("="*80)
    
    # 生成模拟数据（分钟级）
    print("生成模拟数据...")
    data = generate_simulation_data(days=10, freq="5min")
    print(f"生成了 {len(data)} 分钟的模拟数据")
    print(f"价格范围: {data.close.min():.2f} - {data.close.max():.2f}")
    print("="*80)
    
    # 初始化策略
    print("初始化高周转强化版量子矩阵协变策略...")
    strategy = QuantumCovariantTradingSystem(initial_balance=100000)
    print("="*80)
    
    # 测试策略
    print("测试策略...")
    performance = test_strategy(strategy, data)
    print("="*80)
    
    # 输出测试结果
    print("测试结果:")
    print(f"初始资金: {performance['initial_balance']:.2f}")
    print(f"最终资金: {performance['final_balance']:.2f}")
    print(f"总收益率: {performance['total_return']:.2f}%")
    print(f"总交易次数: {performance['trade_count']}")
    print(f"胜率: {performance['win_rate']:.2f}%")
    print(f"最大回撤: {performance['max_drawdown']:.2f}%")
    print("="*80)
    
    # 输出各市场类型表现
    print("各市场类型表现分析:")
    print("市场类型                  交易次数       胜率          收益率")
    print("------------------------------------------------------------")
    
    for market_type, analysis in performance['market_type_analysis'].items():
        win_rate = (analysis["wins"] / analysis["trades"] * 100) if analysis["trades"] > 0 else 0
        return_rate = (analysis["return"] / performance['initial_balance'] * 100) if analysis["trades"] > 0 else 0
        print(f"{market_type:<24} {analysis['trades']:<10} {win_rate:<10.2f}% {return_rate:<10.2f}%")
    
    # 输出市场状态统计
    print("\n市场状态统计:")
    for regime, count in performance['regime_stats'].items():
        print(f"{regime}: {count} 次")
    
    print("="*80)
    print("测试完成！")


if __name__ == "__main__":
    main()
