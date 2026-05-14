# -*- coding: utf-8 -*-
"""
非交互式测试脚本，用于测试所有策略的性能
"""

import pandas as pd
import numpy as np
import sys
import os

# 添加当前目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from market_adaptive_strategies import (
    UpMarketStrategy,
    DownMarketStrategy,
    SidewayMarketStrategy,
    HighVolMarketStrategy,
    MixedMarketStrategy,
    MinuteMixedMarketStrategy,
    MLMarketClassifier,
    evaluate_strategy
)

# 生成模拟数据
def generate_simulated_data(days=200):
    np.random.seed(42)
    dates = pd.date_range(start='2023-01-01', periods=days)
    
    # 生成基础价格走势
    base_trend = np.linspace(100, 120, days)  # 基础上涨趋势
    
    # 添加不同市场类型的波动
    volatility = np.zeros(days)
    
    # 横盘市场
    volatility[0:50] = 0.01
    
    # 上涨市场
    volatility[50:100] = 0.02
    base_trend[50:100] = np.linspace(105, 140, 50)
    
    # 下跌市场
    volatility[100:150] = 0.02
    base_trend[100:150] = np.linspace(140, 110, 50)
    
    # 波动市场
    volatility[150:200] = 0.04
    base_trend[150:200] = np.linspace(110, 130, 50)
    
    # 生成价格
    returns = np.random.normal(0, volatility, days)
    prices = base_trend * np.exp(np.cumsum(returns))
    
    # 生成成交量
    volumes = np.random.randint(1000000, 10000000, days)
    
    # 创建DataFrame
    df = pd.DataFrame({
        'open': prices,
        'high': prices * (1 + np.random.uniform(0, 0.02, days)),
        'low': prices * (1 - np.random.uniform(0, 0.02, days)),
        'close': prices,
        'volume': volumes
    }, index=dates)
    
    return df

if __name__ == "__main__":
    print("测试所有策略的性能")
    print("="*60)
    
    # 生成模拟数据
    print("生成模拟数据...")
    df = generate_simulated_data(days=200)
    print(f"生成了 {len(df)} 天的模拟数据")
    print(f"价格范围: {df.close.min():.2f} - {df.close.max():.2f}")
    print("="*60)
    
    # 训练机器学习模型
    print("训练机器学习模型...")
    ml_classifier = MLMarketClassifier()
    ml_classifier.train(df)
    print("="*60)
    
    # 测试所有策略
    strategies = [
        ("上涨市场策略", UpMarketStrategy()),
        ("下跌市场策略", DownMarketStrategy()),
        ("横盘市场策略", SidewayMarketStrategy()),
        ("高波动市场策略", HighVolMarketStrategy()),
        ("混合市场策略", MixedMarketStrategy(market_classifier=ml_classifier)),
        ("5分钟混合市场策略", MinuteMixedMarketStrategy(market_classifier=ml_classifier, time_frame=5))
    ]
    
    results = []
    
    for name, strategy in strategies:
        print(f"测试 {name}...")
        result = evaluate_strategy(strategy, df)
        results.append((name, result))
        print(f"总收益率: {result['total_return']*100:.2f}%")
        print(f"胜率: {result['win_rate']*100:.2f}%")
        print(f"夏普比率: {result['sharpe_ratio']:.2f}")
        print(f"最大回撤: {result['max_drawdown']*100:.2f}%")
        print(f"总交易次数: {result['trades']}")
        print(f"最终资金: {result['final_capital']:.2f}")
        print("="*60)
    
    # 输出总结
    print("策略性能总结")
    print("="*60)
    print(f"{'策略名称':<20} {'总收益率':>10} {'胜率':>8} {'夏普比率':>10} {'最大回撤':>10} {'交易次数':>10}")
    print("-"*60)
    
    for name, result in results:
        print(f"{name:<20} {result['total_return']*100:>10.2f}% {result['win_rate']*100:>8.2f}% {result['sharpe_ratio']:>10.2f} {result['max_drawdown']*100:>10.2f}% {result['trades']:>10}")
    
    print("="*60)
    print("测试完成！")
