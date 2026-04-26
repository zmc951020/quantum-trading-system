#!/usr/bin/env python3
"""
收益率计算测试 - 分析异常高收益率的原因
"""

import os
import sys
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# 尝试导入模块
try:
    from strategies.grid_trading import GridTrading
except ImportError as e:
    print(f"警告: 导入网格化交易策略失败: {str(e)}")

try:
    from strategies.fund_allocation import DCAStrategy, MLFundAllocator
except ImportError as e:
    print(f"警告: 导入资金配置策略失败: {str(e)}")

def generate_test_data(length: int = 300, start_price: float = 100):
    """
    生成测试数据
    """
    dates = pd.date_range(start=datetime.now() - timedelta(days=length), periods=length, freq='D')
    returns = np.random.normal(0, 0.01, length)
    # 添加趋势
    trend = np.linspace(0, 0.2, length)  # 20%的长期趋势
    returns = returns + trend
    prices = start_price * (1 + returns).cumprod()
    return pd.Series(prices, index=dates)

def test_grid_trading_returns():
    """
    测试网格交易的收益率计算
    """
    print("="*70)
    print("网格交易收益率测试")
    print("="*70)
    
    # 创建网格交易策略
    grid = GridTrading(base_price=100, grid_spacing=0.01, initial_balance=100000)
    
    # 生成测试数据
    data = generate_test_data(length=300)
    print(f"  数据点: {len(data)}")
    print(f"  价格范围: {data.min():.2f} - {data.max():.2f}")
    print(f"  价格变化: {((data.iloc[-1] - data.iloc[0]) / data.iloc[0] * 100):.2f}%")
    
    # 模拟交易
    trade_count = 0
    for i, price in enumerate(data):
        current_data = data.iloc[:i+1]
        result = grid.update_price(price, current_data)
        if result['action'] != 'hold':
            trade_count += 1
            if trade_count <= 10:
                print(f"  交易 {trade_count}: {result['action']} {result['quantity']:.2f} @ {result['price']:.2f}, 余额: {result['balance']:.2f}")
    
    # 查看最终状态
    perf = grid.get_performance()
    print(f"\n  总交易次数: {trade_count}")
    print(f"  初始资金: {perf['initial_balance']:.2f}")
    print(f"  当前资金: {perf['current_balance']:.2f}")
    print(f"  收益率: {perf['return']:.2f}%")
    print(f"  最终仓位: {grid.position}")
    
    # 分析仓位变化
    print(f"\n  网格数量: {len(grid.grids)}")
    print(f"  网格级别: {grid.grid_levels}")
    print(f"  基准价格: {grid.base_price}")
    print(f"  网格间距: {grid.grid_spacing}")
    
    # 检查价格是否超出网格范围
    max_price = data.max()
    min_price = data.min()
    grid_max = max(grid.grids)
    grid_min = min(grid.grids)
    print(f"\n  价格范围: {min_price:.2f} - {max_price:.2f}")
    print(f"  网格范围: {grid_min:.2f} - {grid_max:.2f}")
    
    if max_price > grid_max:
        print(f"  [WARNING] 价格超出网格上限 {max_price - grid_max:.2f}")
    if min_price < grid_min:
        print(f"  [WARNING] 价格超出网格下限 {grid_min - min_price:.2f}")
    
    return perf['return']

def test_ml_allocator_returns():
    """
    测试ML资金分配器的收益率计算
    """
    print("\n" + "="*70)
    print("ML资金分配器收益率测试")
    print("="*70)
    
    # 创建ML资金分配器
    ml_allocator = MLFundAllocator(initial_balance=100000)
    dca = DCAStrategy()
    grid = GridTrading(base_price=100, grid_spacing=0.01)
    
    ml_allocator.add_strategy("dca", dca, 0.5)
    ml_allocator.add_strategy("grid", grid, 0.5)
    
    # 生成测试数据
    data = generate_test_data(length=300)
    
    # 运行优化
    print("  运行优化...")
    ml_allocator.optimize_with_machine_learning(
        data,
        max_queue_size=30,
        convergence_threshold=0.0001,
        convergence_patience=50,
        print_interval=25,
        parallel_workers=4
    )
    
    # 运行策略
    trade_count = 0
    for i, price in enumerate(data):
        timestamp = data.index[i]
        results = ml_allocator.update(price, timestamp)
        for name, result in results.items():
            if result['action'] != 'hold':
                trade_count += 1
                if trade_count <= 5:
                    print(f"  交易 {trade_count}: {name} {result['action']} {result.get('quantity', 0):.2f} @ {price:.2f}")
    
    # 获取性能
    perf = ml_allocator.get_performance(data.iloc[-1])
    print(f"\n  总交易次数: {trade_count}")
    print(f"  初始资金: {perf['overall']['initial_balance']:.2f}")
    print(f"  当前资金: {perf['overall']['current_balance']:.2f}")
    print(f"  总价值: {perf['overall']['total_value']:.2f}")
    print(f"  收益率: {perf['overall']['return']:.2f}%")
    print(f"  最终分配: {perf['overall']['current_allocations']}")
    
    # 检查各个策略的性能
    for name, p in perf.items():
        if name != 'overall':
            print(f"\n  {name} 策略:")
            print(f"    初始资金: {p.get('initial_balance', 0):.2f}")
            print(f"    当前资金: {p.get('current_balance', 0):.2f}")
            print(f"    收益率: {p.get('return', 0):.2f}%")
    
    return perf['overall']['return']

def main():
    """
    主函数
    """
    grid_return = test_grid_trading_returns()
    ml_return = test_ml_allocator_returns()
    
    print("\n" + "="*70)
    print("收益率分析总结")
    print("="*70)
    print(f"网格交易策略收益率: {grid_return:.2f}%")
    print(f"ML资金分配器收益率: {ml_return:.2f}%")
    
    if abs(ml_return) > 1000:
        print("\n[WARNING] 收益率异常高，可能存在计算问题")
        print("可能的原因:")
        print("  1. 网格交易策略的仓位计算问题")
        print("  2. 价格超出网格范围")
        print("  3. 收益率计算方法问题")
    
    print("\n" + "="*70)
    print("收益率测试完成！")
    print("="*70)

if __name__ == "__main__":
    main()
