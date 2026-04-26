#!/usr/bin/env python3
"""
自适应横盘网格交易策略测试
"""

import os
import sys
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    from strategies.adaptive_range_grid import AdaptiveRangeGridTrading
    from strategies.final_market_adaptive import FinalMarketAdaptiveGrid
    from strategies.enhanced_grid import EnhancedGridTrading
    from strategies.adaptive_grid import AdaptiveGridTrading
except ImportError as e:
    print(f"错误: {str(e)}")
    sys.exit(1)

def generate_range_bound_data(length: int, start_price: float = 100, volatility: float = 0.008):
    """
    生成横盘市场数据
    """
    dates = pd.date_range(start=datetime.now() - timedelta(days=length), periods=length, freq='D')
    
    # 生成横盘震荡市场数据
    # 添加更多的小周期波动，适合网格交易
    trend = np.linspace(0, 0.02, length)  # 轻微上涨趋势
    cycle1 = 0.02 * np.sin(np.linspace(0, 30 * np.pi, length))  # 主要周期
    cycle2 = 0.01 * np.sin(np.linspace(0, 60 * np.pi, length))  # 次要周期
    random_noise = np.random.normal(0, volatility, length)
    returns = trend + cycle1 + cycle2 + random_noise
    prices = start_price * (1 + returns).cumprod()
    
    # 确保价格在合理范围内波动
    prices = np.clip(prices, start_price * 0.95, start_price * 1.05)
    
    return pd.Series(prices, index=dates)

def test_strategy(strategy_name: str, strategy_class, data, initial_balance: float = 100000):
    """
    测试特定策略
    """
    # 创建策略实例
    if strategy_name in ['adaptive_range_grid', 'final_market_adaptive']:
        strategy = strategy_class(base_price=data.iloc[0], initial_balance=initial_balance)
    else:
        strategy = strategy_class(base_price=data.iloc[0], grid_spacing=0.002, initial_balance=initial_balance)
    
    # 运行交易
    for i, price in enumerate(data):
        # 每20个数据点提供一次市场数据用于检测
        if i >= 20:
            current_data = data.iloc[:i+1]
            if strategy_name in ['adaptive_range_grid', 'final_market_adaptive', 'enhanced_grid', 'adaptive_grid']:
                strategy.update_price(price, current_data)
            else:
                strategy.update_price(price)
        else:
            strategy.update_price(price)
    
    # 获取性能
    perf = strategy.get_performance()
    
    return {
        'strategy': strategy_name,
        'initial_balance': initial_balance,
        'final_balance': perf['current_balance'],
        'return_rate': perf['return'],
        'total_trades': perf.get('total_trades', 0),
        'win_rate': perf.get('win_rate', 0),
        'avg_profit_per_trade': perf.get('avg_profit_per_trade', 0),
        'grid_adjustments': perf.get('grid_adjustments', 0),
        'model_trained': perf.get('model_trained', False)
    }

def main():
    """
    主函数
    """
    print("="*100)
    print("自适应横盘网格交易策略测试")
    print("="*100)
    print("专门测试横盘市场中的网格交易策略表现")
    print("="*100)
    
    # 生成横盘市场数据
    data = generate_range_bound_data(length=365, volatility=0.008)
    print(f"生成的横盘市场数据: 起始价格={data.iloc[0]:.2f}, 结束价格={data.iloc[-1]:.2f}, 价格范围={data.min():.2f} - {data.max():.2f}")
    
    # 测试策略
    strategies = {
        'adaptive_range_grid': AdaptiveRangeGridTrading,
        'final_market_adaptive': FinalMarketAdaptiveGrid,
        'enhanced_grid': EnhancedGridTrading,
        'adaptive_grid': AdaptiveGridTrading
    }
    
    results = []
    
    # 测试不同策略
    for strategy_name, strategy_class in strategies.items():
        print(f"\n测试 {strategy_name}...")
        try:
            result = test_strategy(strategy_name, strategy_class, data)
            results.append(result)
            print(f"  收益率: {result['return_rate']:8.2f}%")
            print(f"  交易次数: {result['total_trades']:5d}")
            print(f"  胜率: {result['win_rate']:5.2%}")
            print(f"  平均每笔利润: {result['avg_profit_per_trade']:8.2f}")
            if 'grid_adjustments' in result:
                print(f"  网格调整次数: {result['grid_adjustments']:3d}")
            if 'model_trained' in result:
                print(f"  模型训练状态: {'已训练' if result['model_trained'] else '未训练'}")
        except Exception as e:
            print(f"  错误 - {str(e)}")
    
    # 分析结果
    print("\n" + "="*100)
    print("横盘市场策略表现分析")
    print("="*100)
    
    # 按收益率排序
    results.sort(key=lambda x: x['return_rate'], reverse=True)
    
    for i, result in enumerate(results):
        print(f"\n{i+1}. {result['strategy']}:")
        print(f"  收益率: {result['return_rate']:8.2f}%")
        print(f"  交易次数: {result['total_trades']:5d}")
        print(f"  胜率: {result['win_rate']:5.2%}")
        print(f"  平均每笔利润: {result['avg_profit_per_trade']:8.2f}")
        if 'grid_adjustments' in result:
            print(f"  网格调整次数: {result['grid_adjustments']:3d}")
        if 'model_trained' in result:
            print(f"  模型训练状态: {'已训练' if result['model_trained'] else '未训练'}")
    
    # 最佳策略
    if results:
        best_strategy = results[0]
        print(f"\n" + "="*100)
        print("最佳横盘市场策略")
        print("="*100)
        print(f"  策略: {best_strategy['strategy']}")
        print(f"  收益率: {best_strategy['return_rate']:.2f}%")
        print(f"  交易次数: {best_strategy['total_trades']}")
        print(f"  胜率: {best_strategy['win_rate']:.2%}")
        print(f"  平均每笔利润: {best_strategy['avg_profit_per_trade']:.2f}")
    
    print("\n" + "="*100)
    print("横盘市场策略测试完成！")
    print("="*100)

if __name__ == "__main__":
    main()
