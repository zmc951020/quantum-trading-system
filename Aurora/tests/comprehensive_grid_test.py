#!/usr/bin/env python3
"""
综合网格交易策略测试
"""

import os
import sys
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    from strategies.enhanced_grid import EnhancedGridTrading
except ImportError as e:
    print(f"错误: {str(e)}")
    sys.exit(1)

def generate_market_data(length: int, market_type: str = 'range_bound', start_price: float = 100, volatility: float = 0.01):
    """
    生成不同类型的市场数据
    """
    dates = pd.date_range(start=datetime.now() - timedelta(days=length), periods=length, freq='D')
    
    if market_type == 'range_bound':
        # 横盘震荡市场
        trend = np.linspace(0, 0.03, length)
        cycle = 0.03 * np.sin(np.linspace(0, 25 * np.pi, length))
        random_noise = np.random.normal(0, volatility, length)
        returns = trend + cycle + random_noise
        prices = start_price * (1 + returns).cumprod()
        prices = np.clip(prices, start_price * 0.96, start_price * 1.04)
    
    elif market_type == 'trending_up':
        # 上涨趋势市场
        trend = np.linspace(0, 0.25, length)
        cycle = 0.02 * np.sin(np.linspace(0, 15 * np.pi, length))
        random_noise = np.random.normal(0, volatility, length)
        returns = trend + cycle + random_noise
        prices = start_price * (1 + returns).cumprod()
    
    elif market_type == 'trending_down':
        # 下跌趋势市场
        trend = np.linspace(0, -0.15, length)
        cycle = 0.02 * np.sin(np.linspace(0, 15 * np.pi, length))
        random_noise = np.random.normal(0, volatility, length)
        returns = trend + cycle + random_noise
        prices = start_price * (1 + returns).cumprod()
    
    elif market_type == 'volatile':
        # 高波动市场
        trend = np.linspace(0, 0.08, length)
        cycle = 0.05 * np.sin(np.linspace(0, 20 * np.pi, length))
        random_noise = np.random.normal(0, volatility * 1.5, length)
        returns = trend + cycle + random_noise
        prices = start_price * (1 + returns).cumprod()
    
    else:
        # 默认为横盘震荡
        trend = np.linspace(0, 0.03, length)
        cycle = 0.03 * np.sin(np.linspace(0, 25 * np.pi, length))
        random_noise = np.random.normal(0, volatility, length)
        returns = trend + cycle + random_noise
        prices = start_price * (1 + returns).cumprod()
        prices = np.clip(prices, start_price * 0.96, start_price * 1.04)
    
    return pd.Series(prices, index=dates)

def test_strategy(market_type: str, grid_spacing: float, initial_balance: float = 100000):
    """
    测试特定参数的网格交易策略
    """
    # 生成市场数据
    data = generate_market_data(length=365, market_type=market_type, volatility=0.008)
    
    # 创建增强版网格交易策略
    grid = EnhancedGridTrading(
        base_price=data.iloc[0], 
        grid_spacing=grid_spacing,
        initial_balance=initial_balance
    )
    
    # 运行交易
    for i, price in enumerate(data):
        # 每20个数据点提供一次市场数据用于检测
        if i >= 20:
            current_data = data.iloc[:i+1]
            grid.update_price(price, current_data)
        else:
            grid.update_price(price)
    
    # 获取性能
    perf = grid.get_performance()
    
    return {
        'market_type': market_type,
        'grid_spacing': grid_spacing,
        'initial_balance': initial_balance,
        'final_balance': perf['current_balance'],
        'return_rate': perf['return'],
        'total_trades': perf['total_trades'],
        'win_rate': perf['win_rate'],
        'grid_adjustments': perf['grid_adjustments']
    }

def main():
    """
    主函数
    """
    print("="*80)
    print("综合网格交易策略测试")
    print("="*80)
    print("测试不同参数下的网格交易策略表现")
    print("="*80)
    
    # 测试参数
    market_types = ['range_bound', 'trending_up', 'trending_down', 'volatile']
    grid_spacings = [0.001, 0.002, 0.003, 0.004, 0.005]
    initial_balances = [50000, 100000, 200000]
    
    all_results = []
    
    # 测试不同参数组合
    for market_type in market_types:
        print(f"\n测试 {market_type} 市场...")
        for grid_spacing in grid_spacings:
            for initial_balance in initial_balances:
                result = test_strategy(market_type, grid_spacing, initial_balance)
                all_results.append(result)
                print(f"  网格间距: {grid_spacing:.3f}, 初始资金: {initial_balance:6d}, 收益率: {result['return_rate']:8.2f}%")
    
    # 分析结果
    print("\n" + "="*80)
    print("测试结果分析")
    print("="*80)
    
    # 按市场类型分析
    for market_type in market_types:
        market_results = [r for r in all_results if r['market_type'] == market_type]
        avg_return = np.mean([r['return_rate'] for r in market_results])
        best_result = max(market_results, key=lambda x: x['return_rate'])
        print(f"\n{market_type} 市场:")
        print(f"  平均收益率: {avg_return:.2f}%")
        print(f"  最佳参数: 网格间距={best_result['grid_spacing']:.3f}, 初始资金={best_result['initial_balance']:6d}")
        print(f"  最佳收益率: {best_result['return_rate']:.2f}%")
    
    # 按网格间距分析
    for grid_spacing in grid_spacings:
        spacing_results = [r for r in all_results if r['grid_spacing'] == grid_spacing]
        avg_return = np.mean([r['return_rate'] for r in spacing_results])
        print(f"\n网格间距 {grid_spacing:.3f}:")
        print(f"  平均收益率: {avg_return:.2f}%")
    
    # 按初始资金分析
    for initial_balance in initial_balances:
        balance_results = [r for r in all_results if r['initial_balance'] == initial_balance]
        avg_return = np.mean([r['return_rate'] for r in balance_results])
        print(f"\n初始资金 {initial_balance:6d}:")
        print(f"  平均收益率: {avg_return:.2f}%")
    
    # 整体最佳结果
    overall_best = max(all_results, key=lambda x: x['return_rate'])
    print(f"\n" + "="*80)
    print("整体最佳结果")
    print("="*80)
    print(f"  市场类型: {overall_best['market_type']}")
    print(f"  网格间距: {overall_best['grid_spacing']:.3f}")
    print(f"  初始资金: {overall_best['initial_balance']:6d}")
    print(f"  收益率: {overall_best['return_rate']:.2f}%")
    print(f"  交易次数: {overall_best['total_trades']}")
    print(f"  胜率: {overall_best['win_rate']:.2%}")
    print(f"  网格调整次数: {overall_best['grid_adjustments']}")
    
    # 整体平均结果
    avg_overall_return = np.mean([r['return_rate'] for r in all_results])
    print(f"\n整体平均收益率: {avg_overall_return:.2f}%")
    
    print("\n" + "="*80)
    print("综合测试完成！")
    print("="*80)

if __name__ == "__main__":
    main()
