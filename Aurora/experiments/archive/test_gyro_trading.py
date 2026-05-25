#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
陀螺恒稳进动矩阵策略 - 交易效果测试
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from strategies.gyro_minute_strategy import GyroMinuteStrategy
from strategies.gyro_precession_strategy import GyroCompleteStrategy

def generate_minute_data(days=30):
    """生成分钟级测试数据"""
    n_minutes = days * 1440
    dates = pd.date_range(start='2024-01-01', periods=n_minutes, freq='T')
    
    np.random.seed(42)
    prices = np.zeros(n_minutes)
    prices[0] = 100.0
    
    for i in range(1, n_minutes):
        hour_of_day = (i % 1440) / 1440
        
        if i < n_minutes * 0.25:
            dr = np.random.normal(0.0002, 0.0012)
        elif i < n_minutes * 0.5:
            dr = np.random.normal(-0.00015, 0.0015)
        elif i < n_minutes * 0.75:
            dr = np.random.normal(0.0001, 0.0010)
        else:
            dr = np.random.normal(0.00025, 0.0014)
        
        prices[i] = prices[i-1] * (1 + dr)
    
    data = pd.DataFrame({
        'Open': prices * (1 + np.random.randn(n_minutes) * 0.0003),
        'High': prices + np.random.rand(n_minutes) * 0.15,
        'Low': prices - np.random.rand(n_minutes) * 0.15,
        'Close': prices,
        'Volume': np.random.randint(10000, 500000, n_minutes)
    }, index=dates)
    
    return data

def test_strategy():
    print("="*90)
    print("陀螺恒稳进动矩阵策略 - 交易效果测试")
    print("="*90)
    
    # 生成测试数据
    print("\n1. 生成分钟级测试数据...")
    data = generate_minute_data(days=30)
    print(f"   数据规模: {len(data)}分钟 ({len(data)/1440:.1f}天)")
    
    # 创建策略
    print("\n2. 初始化分钟级策略...")
    strategy = GyroMinuteStrategy()
    
    # 运行回测
    print("\n3. 运行回测...")
    result = strategy.run_backtest(data, initial_capital=100000)
    
    # 输出结果
    print("\n" + "="*90)
    print("📊 交易效果测试结果")
    print("="*90)
    
    print("\n--- 核心指标 ---")
    print(f"综合评分: {result['final_score']:.2f} ({result['grade']})")
    print(f"总收益率: {result['total_return_pct']:.2f}%")
    print(f"夏普比率: {result['sharpe_ratio']:.2f}")
    print(f"最大回撤: {result['max_drawdown_pct']:.2f}%")
    print(f"交易次数: {result['total_trades']}")
    print(f"平均持仓时长: {np.mean(strategy.holding_periods):.0f}分钟" if strategy.holding_periods else "平均持仓时长: N/A")
    print(f"日均交易: {result['total_trades']/(len(data)/1440):.2f}次")
    
    print("\n--- 盈亏统计 ---")
    all_returns = np.array([t['return'] for t in strategy.trade_history]) if strategy.trade_history else np.array([0])
    winning_trades = len(all_returns[all_returns > 0])
    losing_trades = len(all_returns[all_returns < 0])
    win_rate = winning_trades / len(all_returns) * 100 if len(all_returns) > 0 else 0
    avg_win = np.mean(all_returns[all_returns > 0]) * 100 if winning_trades > 0 else 0
    avg_loss = np.mean(all_returns[all_returns < 0]) * 100 if losing_trades > 0 else 0
    
    print(f"盈利交易: {winning_trades}次")
    print(f"亏损交易: {losing_trades}次")
    print(f"胜率: {win_rate:.1f}%")
    print(f"平均盈利: {avg_win:.2f}%")
    print(f"平均亏损: {avg_loss:.2f}%")
    print(f"盈亏比: {abs(avg_win/avg_loss):.2f}" if avg_loss != 0 else "盈亏比: N/A")
    
    print("\n--- 指标评分详情 ---")
    print("-"*60)
    sorted_metrics = sorted(result['metric_scores'].items(), key=lambda x: x[1], reverse=True)
    for k, v in sorted_metrics:
        status = "✅" if v >= 8 else "⚠️" if v >= 6 else "❌"
        print(f"{status} {k:<25} : {v:.1f}")
    
    # 生成收益曲线
    print("\n4. 生成收益曲线...")
    equity_curve = result['equity_curve']
    if len(equity_curve) > 0:
        plt.figure(figsize=(12, 6))
        plt.plot(equity_curve)
        plt.title('陀螺策略净值曲线')
        plt.xlabel('时间(分钟)')
        plt.ylabel('净值')
        plt.grid(True)
        plt.savefig('gyro_equity_curve.png')
        print("   收益曲线已保存: gyro_equity_curve.png")
    
    print("\n" + "="*90)
    print("测试完成！")
    print("="*90)
    
    return result

if __name__ == "__main__":
    result = test_strategy()
