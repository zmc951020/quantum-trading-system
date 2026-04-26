#!/usr/bin/env python3
"""
策略比较测试
"""

import os
import sys
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    from strategies.grid_trading import GridTrading
    from strategies.ml_grid_trading import MLGridTrading
    from strategies.optimized_grid import OptimizedGridTrading
    from strategies.enhanced_grid import EnhancedGridTrading
    from strategies.adaptive_grid import AdaptiveGridTrading
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

def test_strategy(strategy_name: str, strategy_class, market_type: str, initial_balance: float = 100000):
    """
    测试特定策略
    """
    # 生成市场数据
    data = generate_market_data(length=365, market_type=market_type, volatility=0.008)
    
    # 创建策略实例
    if strategy_name == 'ml_grid_trading':
        strategy = strategy_class(base_price=data.iloc[0], initial_balance=initial_balance)
    else:
        strategy = strategy_class(base_price=data.iloc[0], grid_spacing=0.002, initial_balance=initial_balance)
    
    # 运行交易
    for i, price in enumerate(data):
        # 每20个数据点提供一次市场数据用于检测
        if i >= 20:
            current_data = data.iloc[:i+1]
            if strategy_name == 'ml_grid_trading' or strategy_name == 'enhanced_grid' or strategy_name == 'adaptive_grid':
                strategy.update_price(price, current_data)
            else:
                strategy.update_price(price)
        else:
            strategy.update_price(price)
    
    # 获取性能
    perf = strategy.get_performance()
    
    return {
        'strategy': strategy_name,
        'market_type': market_type,
        'initial_balance': initial_balance,
        'final_balance': perf['current_balance'],
        'return_rate': perf['return'],
        'total_trades': perf.get('total_trades', 0),
        'win_rate': perf.get('win_rate', 0),
        'grid_adjustments': perf.get('grid_adjustments', 0)
    }

def main():
    """
    主函数
    """
    print("="*90)
    print("策略比较测试")
    print("="*90)
    print("比较不同网格交易策略在各种市场条件下的表现")
    print("="*90)
    
    # 测试策略
    strategies = {
        'grid_trading': GridTrading,
        'ml_grid_trading': MLGridTrading,
        'optimized_grid': OptimizedGridTrading,
        'enhanced_grid': EnhancedGridTrading,
        'adaptive_grid': AdaptiveGridTrading
    }
    
    # 测试市场类型
    market_types = ['range_bound', 'trending_up', 'trending_down', 'volatile']
    
    all_results = []
    
    # 测试不同策略和市场类型
    for strategy_name, strategy_class in strategies.items():
        print(f"\n测试 {strategy_name}...")
        for market_type in market_types:
            result = test_strategy(strategy_name, strategy_class, market_type)
            all_results.append(result)
            print(f"  {market_type}: 收益率={result['return_rate']:8.2f}% 交易次数={result['total_trades']:5d}")
    
    # 分析结果
    print("\n" + "="*90)
    print("策略表现分析")
    print("="*90)
    
    # 按市场类型分析
    for market_type in market_types:
        print(f"\n{market_type} 市场:")
        market_results = [r for r in all_results if r['market_type'] == market_type]
        market_results.sort(key=lambda x: x['return_rate'], reverse=True)
        for result in market_results:
            print(f"  {result['strategy']:16s} 收益率: {result['return_rate']:8.2f}% 交易次数: {result['total_trades']:5d} 胜率: {result['win_rate']:5.2%}")
    
    # 按策略分析
    print("\n" + "="*90)
    print("各策略综合表现")
    print("="*90)
    
    for strategy_name in strategies.keys():
        strategy_results = [r for r in all_results if r['strategy'] == strategy_name]
        avg_return = np.mean([r['return_rate'] for r in strategy_results])
        total_trades = sum([r['total_trades'] for r in strategy_results])
        avg_win_rate = np.mean([r['win_rate'] for r in strategy_results])
        
        # 计算各市场类型的表现
        range_bound_return = next((r['return_rate'] for r in strategy_results if r['market_type'] == 'range_bound'), 0)
        trending_up_return = next((r['return_rate'] for r in strategy_results if r['market_type'] == 'trending_up'), 0)
        trending_down_return = next((r['return_rate'] for r in strategy_results if r['market_type'] == 'trending_down'), 0)
        volatile_return = next((r['return_rate'] for r in strategy_results if r['market_type'] == 'volatile'), 0)
        
        print(f"\n{strategy_name}:")
        print(f"  平均收益率: {avg_return:8.2f}%")
        print(f"  总交易次数: {total_trades:5d}")
        print(f"  平均胜率: {avg_win_rate:5.2%}")
        print(f"  横盘市场: {range_bound_return:8.2f}%")
        print(f"  上涨市场: {trending_up_return:8.2f}%")
        print(f"  下跌市场: {trending_down_return:8.2f}%")
        print(f"  波动市场: {volatile_return:8.2f}%")
    
    # 整体最佳策略
    best_overall = max(all_results, key=lambda x: x['return_rate'])
    print(f"\n" + "="*90)
    print("整体最佳策略")
    print("="*90)
    print(f"  策略: {best_overall['strategy']}")
    print(f"  市场类型: {best_overall['market_type']}")
    print(f"  收益率: {best_overall['return_rate']:.2f}%")
    print(f"  交易次数: {best_overall['total_trades']}")
    print(f"  胜率: {best_overall['win_rate']:.2%}")
    
    # 下跌市场最佳策略
    down_market_results = [r for r in all_results if r['market_type'] == 'trending_down']
    best_down = max(down_market_results, key=lambda x: x['return_rate'])
    print(f"\n" + "="*90)
    print("下跌市场最佳策略")
    print("="*90)
    print(f"  策略: {best_down['strategy']}")
    print(f"  收益率: {best_down['return_rate']:.2f}%")
    print(f"  交易次数: {best_down['total_trades']}")
    print(f"  胜率: {best_down['win_rate']:.2%}")
    
    print("\n" + "="*90)
    print("策略比较测试完成！")
    print("="*90)

if __name__ == "__main__":
    main()
