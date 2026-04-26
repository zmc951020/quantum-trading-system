#!/usr/bin/env python3
"""
高级机器学习策略测试
"""

import os
import sys
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    from strategies.advanced_ml_strategy import AdvancedMLStrategy
    from strategies.adaptive_range_grid import AdaptiveRangeGridTrading
    from strategies.adaptive_grid import AdaptiveGridTrading
except ImportError as e:
    print(f"错误: {str(e)}")
    sys.exit(1)

def generate_market_data(length: int, market_type: str, start_price: float = 100):
    """
    生成不同类型的市场数据
    """
    dates = pd.date_range(start=datetime.now() - timedelta(days=length), periods=length, freq='D')
    
    if market_type == 'range_bound':
        # 横盘市场
        trend = np.linspace(0, 0.02, length)  # 轻微上涨趋势
        cycle1 = 0.02 * np.sin(np.linspace(0, 30 * np.pi, length))  # 主要周期
        cycle2 = 0.01 * np.sin(np.linspace(0, 60 * np.pi, length))  # 次要周期
        random_noise = np.random.normal(0, 0.008, length)
        returns = trend + cycle1 + cycle2 + random_noise
        prices = start_price * (1 + returns).cumprod()
        prices = np.clip(prices, start_price * 0.95, start_price * 1.05)
    
    elif market_type == 'trending_up':
        # 上涨市场
        trend = np.linspace(0, 0.8, length)  # 明显上涨趋势
        random_noise = np.random.normal(0, 0.01, length)
        returns = 0.002 + random_noise  # 每天平均上涨0.2%
        prices = start_price * (1 + returns).cumprod()
    
    elif market_type == 'trending_down':
        # 下跌市场
        trend = np.linspace(0, -0.4, length)  # 明显下跌趋势
        random_noise = np.random.normal(0, 0.01, length)
        returns = -0.0015 + random_noise  # 每天平均下跌0.15%
        prices = start_price * (1 + returns).cumprod()
    
    elif market_type == 'volatile':
        # 波动市场
        trend = np.linspace(0, 0.2, length)  # 轻微上涨趋势
        cycle = 0.03 * np.sin(np.linspace(0, 10 * np.pi, length))  # 较大周期波动
        random_noise = np.random.normal(0, 0.015, length)  # 较大噪声
        returns = trend + cycle + random_noise
        prices = start_price * (1 + returns).cumprod()
    
    else:
        # 默认横盘市场
        trend = np.linspace(0, 0.02, length)
        cycle = 0.02 * np.sin(np.linspace(0, 30 * np.pi, length))
        random_noise = np.random.normal(0, 0.008, length)
        returns = trend + cycle + random_noise
        prices = start_price * (1 + returns).cumprod()
        prices = np.clip(prices, start_price * 0.95, start_price * 1.05)
    
    return pd.Series(prices, index=dates)

def test_strategy(strategy_name: str, strategy_class, data, market_type, initial_balance: float = 100000):
    """
    测试特定策略
    """
    # 创建策略实例
    strategy = strategy_class(base_price=data.iloc[0], initial_balance=initial_balance)
    
    # 运行交易
    for i, price in enumerate(data):
        # 每20个数据点提供一次市场数据用于检测
        if i >= 20:
            current_data = data.iloc[:i+1]
            strategy.update_price(price, current_data)
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
        'market_switch_count': perf.get('market_switch_count', 0),
        'model_trained': perf.get('model_trained', False),
        'current_strategy': perf.get('current_strategy', 'unknown'),
        'current_market_type': perf.get('current_market_type', 'unknown')
    }

def main():
    """
    主函数
    """
    print("="*100)
    print("高级机器学习策略测试")
    print("="*100)
    print("测试自动切换不同市场类型的最佳策略")
    print("="*100)
    
    # 测试不同市场类型
    market_types = ['range_bound', 'trending_up', 'trending_down', 'volatile']
    strategies = {
        'advanced_ml_strategy': AdvancedMLStrategy,
        'adaptive_range_grid': AdaptiveRangeGridTrading,
        'adaptive_grid': AdaptiveGridTrading
    }
    
    all_results = []
    
    # 测试不同市场类型
    for market_type in market_types:
        print(f"\n测试 {market_type} 市场...")
        
        # 生成市场数据
        data = generate_market_data(length=365, market_type=market_type)
        print(f"  生成的{market_type}市场数据: 起始价格={data.iloc[0]:.2f}, 结束价格={data.iloc[-1]:.2f}, 价格范围={data.min():.2f} - {data.max():.2f}")
        
        # 测试不同策略
        for strategy_name, strategy_class in strategies.items():
            print(f"  测试 {strategy_name}...")
            try:
                result = test_strategy(strategy_name, strategy_class, data, market_type)
                all_results.append(result)
                print(f"    收益率: {result['return_rate']:8.2f}%")
                print(f"    交易次数: {result['total_trades']:5d}")
                print(f"    胜率: {result['win_rate']:5.2%}")
                if 'market_switch_count' in result:
                    print(f"    市场切换次数: {result['market_switch_count']:3d}")
                if 'model_trained' in result:
                    print(f"    模型训练状态: {'已训练' if result['model_trained'] else '未训练'}")
                if 'current_strategy' in result:
                    print(f"    当前策略: {result['current_strategy']}")
                if 'current_market_type' in result:
                    print(f"    当前市场类型: {result['current_market_type']}")
            except Exception as e:
                print(f"    错误 - {str(e)}")
    
    # 分析结果
    print("\n" + "="*100)
    print("各市场类型策略表现分析")
    print("="*100)
    
    for market_type in market_types:
        print(f"\n{market_type} 市场:")
        market_results = [r for r in all_results if r['market_type'] == market_type]
        market_results.sort(key=lambda x: x['return_rate'], reverse=True)
        
        for i, result in enumerate(market_results):
            print(f"  {i+1}. {result['strategy']}: {result['return_rate']:.2f}%")
    
    # 计算综合表现
    print("\n" + "="*100)
    print("综合表现分析")
    print("="*100)
    
    strategy_results = {}
    for strategy_name in strategies.keys():
        strategy_data = [r for r in all_results if r['strategy'] == strategy_name]
        avg_return = np.mean([r['return_rate'] for r in strategy_data])
        total_trades = sum([r['total_trades'] for r in strategy_data])
        win_rate = np.mean([r['win_rate'] for r in strategy_data])
        
        strategy_results[strategy_name] = {
            'avg_return': avg_return,
            'total_trades': total_trades,
            'avg_win_rate': win_rate
        }
    
    # 按平均收益率排序
    sorted_strategies = sorted(strategy_results.items(), key=lambda x: x[1]['avg_return'], reverse=True)
    
    for i, (strategy_name, stats) in enumerate(sorted_strategies):
        print(f"\n{i+1}. {strategy_name}:")
        print(f"  平均收益率: {stats['avg_return']:.2f}%")
        print(f"  总交易次数: {stats['total_trades']}")
        print(f"  平均胜率: {stats['avg_win_rate']:.2%}")
    
    # 最佳策略
    if sorted_strategies:
        best_strategy, best_stats = sorted_strategies[0]
        print(f"\n" + "="*100)
        print("最佳综合策略")
        print("="*100)
        print(f"  策略: {best_strategy}")
        print(f"  平均收益率: {best_stats['avg_return']:.2f}%")
        print(f"  总交易次数: {best_stats['total_trades']}")
        print(f"  平均胜率: {best_stats['avg_win_rate']:.2%}")
    
    print("\n" + "="*100)
    print("高级机器学习策略测试完成！")
    print("="*100)

if __name__ == "__main__":
    main()
