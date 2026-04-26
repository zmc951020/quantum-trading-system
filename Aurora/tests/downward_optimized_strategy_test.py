#!/usr/bin/env python3
"""
下跌市场优化策略测试
"""

import numpy as np
import pandas as pd
import sys
import os

# 添加父目录到路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strategies.downward_optimized_strategy import DownwardOptimizedStrategy

def generate_market_data(market_type, days=200):
    """
    生成模拟市场数据
    
    Args:
        market_type: 市场类型 ('range_bound', 'trending_up', 'trending_down', 'volatile')
        days: 数据天数
        
    Returns:
        价格数据
    """
    np.random.seed(42)
    dates = pd.date_range(start='2023-01-01', periods=days)
    
    # 生成基础价格
    base_price = 100.0
    prices = [base_price]
    
    for i in range(1, days):
        if market_type == 'range_bound':
            # 横盘市场：小幅波动
            change = np.random.normal(0, 0.01)
        elif market_type == 'trending_up':
            # 上涨市场：持续上涨
            change = np.random.normal(0.005, 0.01)
        elif market_type == 'trending_down':
            # 下跌市场：持续下跌
            change = np.random.normal(-0.005, 0.01)
        else:  # volatile
            # 波动市场：大幅波动
            change = np.random.normal(0, 0.03)
        
        new_price = prices[-1] * (1 + change)
        prices.append(new_price)
    
    return pd.DataFrame({
        'close': prices
    }, index=dates)

def test_strategy(strategy, data, market_name):
    """
    测试策略
    
    Args:
        strategy: 策略实例
        data: 价格数据
        market_name: 市场名称
        
    Returns:
        策略性能
    """
    print(f"\n{'='*80}")
    print(f"测试 {market_name} 市场")
    print(f"{'='*80}")
    
    buy_count = 0
    sell_count = 0
    
    for i, (index, row) in enumerate(data.iterrows()):
        current_price = row['close']
        # 传递足够的历史数据
        if i >= 20:
            window_data = data.iloc[:i+1]['close']
            result = strategy.update_price(current_price, window_data)
        else:
            result = strategy.update_price(current_price)
        
        if result['action'] == 'buy':
            buy_count += 1
            print(f"  买入: {result['quantity']:.2f} @ {result['price']:.2f} 余额: {result['balance']:.2f} (原因: {result.get('reason', 'normal')})")
        elif result['action'] == 'sell':
            sell_count += 1
            reason = result.get('reason', 'normal')
            print(f"  卖出: {result['quantity']:.2f} @ {result['price']:.2f} 余额: {result['balance']:.2f} (原因: {reason})")
    
    performance = strategy.get_performance()
    
    print(f"\n结果:")
    print(f"  总交易: {buy_count + sell_count}")
    print(f"  买入: {buy_count}")
    print(f"  卖出: {sell_count}")
    print(f"  初始资金: {performance['initial_balance']:.2f}")
    print(f"  当前资金: {performance['current_balance']:.2f}")
    print(f"  收益率: {performance['return']:.2f}%")
    print(f"  总交易次数: {performance['total_trades']}")
    print(f"  盈利交易: {performance['winning_trades']}")
    print(f"  亏损交易: {performance['losing_trades']}")
    print(f"  胜率: {performance['win_rate']*100:.2f}%")
    print(f"  市场切换次数: {performance['market_switch_count']}")
    print(f"  模型训练状态: {'已训练' if performance['model_trained'] else '未训练'}")
    print(f"  当前市场类型: {performance['current_market_type']}")
    
    return performance

def main():
    """
    主测试函数
    """
    print("="*100)
    print("下跌市场优化策略测试")
    print("="*100)
    print("测试专门针对下跌市场的优化策略")
    print("="*100)
    
    # 测试不同市场类型
    market_types = ['trending_down', 'range_bound', 'trending_up', 'volatile']
    results = {}
    
    for market_type in market_types:
        # 生成市场数据
        data = generate_market_data(market_type)
        print(f"\n{'='*80}")
        print(f"生成的{market_type}市场数据: 起始价格={data['close'].iloc[0]:.2f}, 结束价格={data['close'].iloc[-1]:.2f}, 价格范围={data['close'].min():.2f} - {data['close'].max():.2f}")
        
        # 测试下跌市场优化策略
        strategy = DownwardOptimizedStrategy(base_price=data['close'].iloc[0])
        results[market_type] = test_strategy(strategy, data, f"downward_optimized")
    
    # 分析结果
    print("\n" + "="*100)
    print("各市场类型策略表现分析")
    print("="*100)
    
    for market_type in market_types:
        print(f"\n{market_type} 市场:")
        perf = results[market_type]
        print(f"  收益率: {perf['return']:8.2f}%")
        print(f"  交易次数: {perf['total_trades']:8}")
        print(f"  胜率: {perf['win_rate']*100:8.2f}%")
        print(f"  市场切换次数: {perf['market_switch_count']:8}")
    
    # 计算综合表现
    total_return = 0
    total_trades = 0
    total_win_rate = 0
    
    for market_type in market_types:
        perf = results[market_type]
        total_return += perf['return']
        total_trades += perf['total_trades']
        total_win_rate += perf['win_rate']
    
    avg_return = total_return / len(market_types)
    avg_win_rate = total_win_rate / len(market_types) * 100
    
    print("\n" + "="*100)
    print("综合表现分析")
    print("="*100)
    print(f"平均收益率: {avg_return:.2f}%")
    print(f"总交易次数: {total_trades}")
    print(f"平均胜率: {avg_win_rate:.2f}%")
    
    print("\n" + "="*100)
    print("下跌市场优化策略测试完成！")
    print("="*100)

if __name__ == "__main__":
    main()
