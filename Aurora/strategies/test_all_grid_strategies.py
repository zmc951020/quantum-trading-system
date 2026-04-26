#!/usr/bin/env python3
"""
测试所有网格化交易策略
重点关注横盘市场的表现
"""

import numpy as np
import pandas as pd
import sys
import os

# 添加父目录到路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 导入所有网格化交易策略
from grid_trading import GridTrading, MLGridTrading
from enhanced_grid import EnhancedGridTrading
from adaptive_grid import AdaptiveGridTrading
from optimized_grid import OptimizedGridTrading
from adaptive_range_grid import AdaptiveRangeGridTrading
from reversal_grid import ReversalGridTrading
from downward_grid import DownwardGridTrading
from ml_grid_trading import MLGridTrading
from ml_range_grid import MLRangeGridTrading
from ml_adaptive_grid import MLAdaptiveGridTrading
from final_adaptive_grid import FinalAdaptiveGridTrading
from minute_adaptive_grid_v3 import MinuteAdaptiveGridStrategyV3
from ml_reversal_grid import MLReversalGridTrading
from high_return_grid import HighReturnGridTrading
from final_market_adaptive import FinalMarketAdaptiveGrid

def generate_range_bound_data(n=1000):
    """
    生成横盘市场数据
    """
    np.random.seed(42)
    price = [100.0]
    for i in range(1, n):
        # 生成横盘市场数据
        ret = np.random.normal(0, 0.001)
        price.append(price[-1] * (1 + ret))
    return pd.DataFrame({'close': price})

def test_strategy(strategy_class, name, data):
    """
    测试单个策略
    """
    base_price = data['close'].iloc[0]
    if name == 'HighReturnGridTrading':
        strategy = strategy_class(initial_balance=100000.0, base_price=base_price)
    else:
        strategy = strategy_class(base_price)
    
    for i in range(len(data)):
        current_price = data['close'].iloc[i]
        # 调用策略的update_price方法
        if name == 'MLRangeGridTrading' or name == 'FinalMarketAdaptiveGrid':
            # 特殊处理，需要传递data参数
            result = strategy.update_price(current_price, data['close'])
        else:
            result = strategy.update_price(current_price)
    
    # 获取策略性能
    if hasattr(strategy, 'get_performance'):
        performance = strategy.get_performance()
        return {
            'name': name,
            'initial_balance': performance.get('initial_balance', 100000),
            'final_balance': performance.get('current_balance', 100000),
            'return': performance.get('return', 0),
            'total_trades': performance.get('total_trades', 0),
            'win_rate': performance.get('win_rate', 0) * 100,
            'total_profit': performance.get('total_profit', 0)
        }
    else:
        # 对于没有get_performance方法的策略，使用默认值
        return {
            'name': name,
            'initial_balance': 100000,
            'final_balance': 100000,
            'return': 0,
            'total_trades': 0,
            'win_rate': 0,
            'total_profit': 0
        }

def main():
    """
    测试所有网格化交易策略
    """
    # 生成横盘市场数据
    data = generate_range_bound_data()
    
    # 定义要测试的策略
    strategies = [
        (GridTrading, 'GridTrading'),
        (MLGridTrading, 'MLGridTrading'),
        (EnhancedGridTrading, 'EnhancedGridTrading'),
        (AdaptiveGridTrading, 'AdaptiveGridTrading'),
        (OptimizedGridTrading, 'OptimizedGridTrading'),
        (AdaptiveRangeGridTrading, 'AdaptiveRangeGridTrading'),
        (ReversalGridTrading, 'ReversalGridTrading'),
        (DownwardGridTrading, 'DownwardGridTrading'),
        (MLRangeGridTrading, 'MLRangeGridTrading'),
        (MLAdaptiveGridTrading, 'MLAdaptiveGridTrading'),
        (FinalAdaptiveGridTrading, 'FinalAdaptiveGridTrading'),
        (MinuteAdaptiveGridStrategyV3, 'MinuteAdaptiveGridStrategyV3'),
        (MLReversalGridTrading, 'MLReversalGridTrading'),
        (HighReturnGridTrading, 'HighReturnGridTrading'),
        (FinalMarketAdaptiveGrid, 'FinalMarketAdaptiveGrid')
    ]
    
    # 测试所有策略
    results = []
    for strategy_class, name in strategies:
        try:
            result = test_strategy(strategy_class, name, data)
            results.append(result)
            print(f"测试完成: {name}")
        except Exception as e:
            print(f"测试失败: {name}, 错误: {e}")
            # 添加失败的策略结果
            results.append({
                'name': name,
                'initial_balance': 100000,
                'final_balance': 100000,
                'return': 0,
                'total_trades': 0,
                'win_rate': 0,
                'total_profit': 0
            })
    
    # 整理结果
    df = pd.DataFrame(results)
    
    # 按收益率排序
    df = df.sort_values(by='return', ascending=False)
    
    # 打印结果
    print("\n" + "=" * 80)
    print("所有网格化交易策略横盘市场测试结果")
    print("=" * 80)
    print(df.to_string(index=False))
    print("=" * 80)
    
    # 打印最佳策略
    if not df.empty:
        best_strategy = df.iloc[0]
        print(f"\n最佳横盘市场策略: {best_strategy['name']}")
        print(f"收益率: {best_strategy['return']*100:.2f}%")
        print(f"交易次数: {best_strategy['total_trades']}")
        print(f"胜率: {best_strategy['win_rate']:.2f}%")
        print(f"总盈利: {best_strategy['total_profit']:.2f}元")

if __name__ == "__main__":
    main()
