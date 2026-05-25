#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试陀螺恒稳进动矩阵策略
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import pandas as pd

from strategies.gyro_precession_strategy import GyroCompleteStrategy

print("="*90)
print("测试陀螺恒稳进动矩阵·自适应演进交易策略（金融级专业版）")
print("="*90)

# 生成测试数据
np.random.seed(42)
n_days = 1000
dates = pd.date_range(start='2020-01-01', periods=n_days, freq='D')

prices = np.zeros(n_days)
prices[0] = 100.0
for i in range(1, n_days):
    if i < 200:
        dr = np.random.normal(0.002, 0.012)  # 牛市
    elif i < 400:
        dr = np.random.normal(-0.0015, 0.018)  # 熊市
    elif i < 600:
        dr = np.random.normal(0.0005, 0.010)  # 震荡
    elif i < 800:
        dr = np.random.normal(0.0018, 0.014)  # 上涨
    else:
        dr = np.random.normal(0.0012, 0.016)  # 稳定
    prices[i] = prices[i-1] * (1 + dr)

test_data = pd.DataFrame({
    'Open': prices * (1 + np.random.randn(n_days) * 0.003),
    'High': np.maximum(prices, prices * (1 + np.random.randn(n_days) * 0.003)) * (1 + np.random.rand(n_days) * 0.005),
    'Low': np.minimum(prices, prices * (1 + np.random.randn(n_days) * 0.003)) * (1 - np.random.rand(n_days) * 0.005),
    'Close': prices,
    'Volume': np.random.randint(2000000, 15000000, n_days)
}, index=dates)

print(f"\n测试数据: {n_days}天, 包含多种市场状态")

# 创建并运行策略
strategy = GyroCompleteStrategy()
result = strategy.run_backtest(test_data, 100000)

print("\n" + "="*90)
print("📊 回测结果")
print("="*90)
print(f"综合评分: {result['final_score']:.2f} ({result['grade']})")
print(f"总收益率: {result['total_return_pct']:.2f}%")
print(f"夏普比率: {result['sharpe_ratio']:.2f}")
print(f"最大回撤: {result['max_drawdown_pct']:.2f}%")
print(f"交易次数: {result['total_trades']}")

print("\n🏆 各指标得分:")
sorted_metrics = sorted(result['metric_scores'].items(), key=lambda x: x[1], reverse=True)
for k, v in sorted_metrics:
    status = "✅" if v >= 8 else "⚠️" if v >= 6 else "❌"
    print(f"{status} {k:<25}: {v:.1f}")

print("\n" + "="*90)
print("测试完成！")
print("="*90)
