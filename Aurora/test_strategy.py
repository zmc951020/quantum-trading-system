#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import pandas as pd

print("="*80)
print("伯努利-康达策略测试")
print("="*80)

try:
    from strategies.bernoulli_coanda_strategy import (
        bernoulli_coanda_strategy,
        BernoulliCoandaParameters
    )
    print("✅ 策略导入成功")
except Exception as e:
    print(f"❌ 策略导入失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print()

# 创建测试数据
print("1. 创建测试数据...")
np.random.seed(42)
n_days = 300
dates = pd.date_range(start='2022-01-01', periods=n_days, freq='D')
prices = 100 + np.cumsum(np.random.randn(n_days) * 2)

data = pd.DataFrame({
    'Open': prices * 0.995,
    'High': prices * 1.01,
    'Low': prices * 0.99,
    'Close': prices,
    'Volume': np.random.randint(100000, 1000000, n_days)
}, index=dates)
print("✅ 测试数据创建完成")
print(f"   起始价格: {prices[0]:.2f}")
print(f"   结束价格: {prices[-1]:.2f}")

print()

# 创建策略
print("2. 创建策略实例...")
params = BernoulliCoandaParameters(
    short_velocity_window=5,
    long_velocity_window=20,
    pressure_threshold=0.5,
    curve_type='ema',
    max_holding_days=30
)
strategy = bernoulli_coanda_strategy(name="BCQ_Test", params=params)
print("✅ 策略创建完成")

print()

# 运行回测
print("3. 运行回测...")
initial_capital = 100000
result = strategy.run_backtest(data, initial_capital)
print("✅ 回测完成")

print()

# 显示结果
print("4. 回测结果:")
print("-"*80)
print(f"初始资金:  ${initial_capital:,.2f}")
print(f"最终资金:  ${result.get('final_equity', 0):,.2f}")
print(f"总收益率:  {result.get('total_return_pct', 0):+.2f}%")
print(f"夏普比率:  {result.get('sharpe_ratio', 0):.2f}")
print(f"最大回撤:  {result.get('max_drawdown_pct', 0):.2f}%")
print(f"交易次数:  {result.get('total_trades', 0)}")
print(f"胜率:      {result.get('win_rate_pct', 0):.1f}%")
print(f"盈亏比:    {result.get('profit_factor', 0):.2f}")
print("-"*80)

print()
print("="*80)
print("✅ 测试完成！")
print("="*80)

