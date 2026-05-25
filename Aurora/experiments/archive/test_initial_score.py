#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试伯努利-康达策略的初始评分
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import pandas as pd

def log(msg):
    print(msg)
    sys.stdout.flush()

log("="*90)
log("测试伯努利-康达策略初始评分")
log("="*90)

# 导入策略和评估器
from strategies.bernoulli_coanda_strategy import (
    bernoulli_coanda_strategy,
    BernoulliCoandaParameters
)
from enhanced_evaluator import EnhancedFinancialEvaluator

# 生成测试数据
np.random.seed(42)
n_days = 500
dates = pd.date_range(start='2020-01-01', periods=n_days, freq='D')

prices = np.zeros(n_days)
prices[0] = 100.0
for i in range(1, n_days):
    if i < 150:
        dr = np.random.normal(0.002, 0.015)
    elif i < 300:
        dr = np.random.normal(-0.0015, 0.02)
    elif i < 420:
        dr = np.random.normal(0.0008, 0.012)
    else:
        dr = np.random.normal(0.0015, 0.016)
    prices[i] = prices[i-1] * (1 + dr)

data = pd.DataFrame({
    'Open': prices*(1+np.random.randn(n_days)*0.003),
    'High': np.maximum(prices, prices*(1+np.random.randn(n_days)*0.003))*(1+np.random.rand(n_days)*0.005),
    'Low': np.minimum(prices, prices*(1+np.random.randn(n_days)*0.003))*(1-np.random.rand(n_days)*0.005),
    'Close': prices,
    'Volume': np.random.randint(2000000, 15000000, n_days)
}, index=dates)

log("\n1. 测试默认参数评分")

# 1. 使用默认参数
log("\n   1.1 默认参数:")
default_params = BernoulliCoandaParameters()
strategy = bernoulli_coanda_strategy(name="Default", params=default_params)
result = strategy.run_backtest(data, 100000)

evaluator = EnhancedFinancialEvaluator()
total_score, metric_scores, details = evaluator.evaluate(result)
grade = evaluator.get_grade(total_score)

log(f"       综合评分: {total_score:.2f} ({grade})")
log(f"       总收益率: {result.get('total_return_pct', 0):.2f}%")
log(f"       夏普比率: {result.get('sharpe_ratio', 0):.2f}")
log(f"       最大回撤: {result.get('max_drawdown_pct', 0):.2f}%")
log(f"       胜率: {result.get('win_rate_pct', 0):.1f}%")
log(f"       盈亏比: {result.get('profit_factor', 0):.2f}")
log(f"       交易次数: {result.get('total_trades', 0)}")

log("\n   1.2 默认参数各指标得分:")
for k, v in sorted(metric_scores.items(), key=lambda x: x[1], reverse=True):
    log(f"       {k:<25}: {v:.1f}")

log("\n2. 测试优化后参数评分")

# 2. 使用优化后的参数
log("\n   2.1 优化后参数:")
optimized_params = BernoulliCoandaParameters(
    short_velocity_window=4,
    long_velocity_window=18,
    pressure_threshold=2.48,
    curve_window=15,
    adhere_threshold=0.02,
    stop_loss_atr_multiplier=2.0,
    take_profit_risk_reward=3.07,
    max_holding_days=32
)
strategy2 = bernoulli_coanda_strategy(name="Optimized", params=optimized_params)
result2 = strategy2.run_backtest(data, 100000)

total_score2, metric_scores2, details2 = evaluator.evaluate(result2)
grade2 = evaluator.get_grade(total_score2)

log(f"       综合评分: {total_score2:.2f} ({grade2})")
log(f"       总收益率: {result2.get('total_return_pct', 0):.2f}%")
log(f"       夏普比率: {result2.get('sharpe_ratio', 0):.2f}")
log(f"       最大回撤: {result2.get('max_drawdown_pct', 0):.2f}%")
log(f"       胜率: {result2.get('win_rate_pct', 0):.1f}%")
log(f"       盈亏比: {result2.get('profit_factor', 0):.2f}")
log(f"       交易次数: {result2.get('total_trades', 0)}")

log("\n   2.2 优化后各指标得分:")
for k, v in sorted(metric_scores2.items(), key=lambda x: x[1], reverse=True):
    log(f"       {k:<25}: {v:.1f}")

log("\n3. 对比分析")
log("="*90)
log(f"   初始评分: {total_score:.2f}")
log(f"   优化后评分: {total_score2:.2f}")
log(f"   提升: {total_score2 - total_score:+.2f}")
log(f"   提升百分比: {(total_score2 - total_score) / total_score * 100:+.1f}%")
log("="*90)
