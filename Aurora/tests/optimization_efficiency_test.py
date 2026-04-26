#!/usr/bin/env python3
"""
优化效率测试 - 验证系统在不同规模下的性能
"""

import os
import sys
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# 尝试导入模块
MODULES = {}
try:
    from strategies.grid_trading import GridTrading
    MODULES['GridTrading'] = GridTrading
except ImportError as e:
    print(f"警告: 导入网格化交易策略失败: {str(e)}")

try:
    from strategies.fund_allocation import DCAStrategy, MLFundAllocator
    MODULES['DCAStrategy'] = DCAStrategy
    MODULES['MLFundAllocator'] = MLFundAllocator
except ImportError as e:
    print(f"警告: 导入资金配置策略失败: {str(e)}")

def generate_market_data(length: int, start_price: float = 100, volatility: float = 0.01):
    """
    生成市场数据
    """
    dates = pd.date_range(start=datetime.now() - timedelta(days=length), periods=length, freq='D')
    returns = np.random.normal(0, volatility, length)
    # 添加一些趋势
    trend = np.linspace(0, 0.15, length)  # 15%的长期趋势
    returns = returns + trend
    prices = start_price * (1 + returns).cumprod()
    return pd.Series(prices, index=dates)

def test_optimization_efficiency(data_length: int, parallel_workers: int, description: str):
    """
    测试优化效率
    """
    print(f"\n" + "="*70)
    print(f"测试: {description}")
    print(f"数据长度: {data_length}, 并行线程: {parallel_workers}")
    print("="*70)
    
    # 创建ML资金分配器
    ml_allocator = MODULES['MLFundAllocator'](initial_balance=100000)
    
    # 添加策略
    dca = MODULES['DCAStrategy']()
    grid = MODULES['GridTrading'](base_price=100, grid_spacing=0.01)
    
    ml_allocator.add_strategy("dca", dca, 0.5)
    ml_allocator.add_strategy("grid", grid, 0.5)
    
    # 生成测试数据
    data = generate_market_data(length=data_length)
    print(f"  数据点: {len(data)}")
    print(f"  价格范围: {data.min():.2f} - {data.max():.2f}")
    
    # 运行优化
    start_time = datetime.now()
    ml_allocator.optimize_with_machine_learning(
        data,
        max_queue_size=50,
        convergence_threshold=0.0001,
        convergence_patience=100,
        print_interval=50,
        parallel_workers=parallel_workers
    )
    elapsed_time = (datetime.now() - start_time).total_seconds()
    
    # 运行策略
    for i, price in enumerate(data):
        timestamp = data.index[i]
        ml_allocator.update(price, timestamp)
    
    # 获取性能
    perf = ml_allocator.get_performance(data.iloc[-1])
    
    # 计算效率指标
    total_evaluations = ml_allocator.optimization_cycle * parallel_workers
    evaluations_per_second = total_evaluations / elapsed_time
    
    result = {
        'description': description,
        'data_length': data_length,
        'parallel_workers': parallel_workers,
        'elapsed_time': elapsed_time,
        'iterations': ml_allocator.optimization_cycle,
        'evaluations': total_evaluations,
        'evaluations_per_second': evaluations_per_second,
        'return_rate': perf['overall']['return'],
        'final_allocation': perf['overall']['current_allocations']
    }
    
    print(f"  耗时: {elapsed_time:.2f}秒")
    print(f"  迭代次数: {result['iterations']}")
    print(f"  评估方案数: {result['evaluations']}")
    print(f"  效率: {result['evaluations_per_second']:.1f}方案/秒")
    print(f"  收益率: {result['return_rate']:.2f}%")
    print(f"  最终分配: {result['final_allocation']}")
    
    return result

def run_efficiency_tests():
    """
    运行效率测试
    """
    print("="*70)
    print("优化效率测试")
    print("="*70)
    print("测试不同规模下的优化性能")
    print("="*70)
    
    # 检查必要模块
    required_modules = ['MLFundAllocator', 'DCAStrategy', 'GridTrading']
    for mod in required_modules:
        if mod not in MODULES:
            print(f"\n[FAIL] 缺少必要模块: {mod}")
            return
    
    # 清理旧的队列文件
    queue_file = "candidate_queue.pkl"
    if os.path.exists(queue_file):
        os.remove(queue_file)
        print("[INFO] 清理旧的队列文件")
    
    results = []
    
    # 测试1: 小数据规模
    results.append(test_optimization_efficiency(
        data_length=200,
        parallel_workers=4,
        description="小数据规模 (200点)"
    ))
    
    # 测试2: 中等数据规模
    results.append(test_optimization_efficiency(
        data_length=500,
        parallel_workers=4,
        description="中等数据规模 (500点)"
    ))
    
    # 测试3: 大数据规模
    results.append(test_optimization_efficiency(
        data_length=1000,
        parallel_workers=8,
        description="大数据规模 (1000点)"
    ))
    
    # 测试4: 并行效率测试
    results.append(test_optimization_efficiency(
        data_length=500,
        parallel_workers=8,
        description="并行效率测试 (8线程)"
    ))
    
    # 清理队列文件
    if os.path.exists(queue_file):
        os.remove(queue_file)
        print("\n[INFO] 清理队列文件")
    
    # 打印总结
    print("\n" + "="*70)
    print("优化效率测试总结")
    print("="*70)
    
    for i, result in enumerate(results, 1):
        print(f"\n测试 {i}: {result['description']}")
        print(f"  数据长度: {result['data_length']}")
        print(f"  并行线程: {result['parallel_workers']}")
        print(f"  耗时: {result['elapsed_time']:.2f}秒")
        print(f"  效率: {result['evaluations_per_second']:.1f}方案/秒")
        print(f"  收益率: {result['return_rate']:.2f}%")
    
    # 计算平均性能
    avg_time = sum(r['elapsed_time'] for r in results) / len(results)
    avg_efficiency = sum(r['evaluations_per_second'] for r in results) / len(results)
    avg_return = sum(r['return_rate'] for r in results) / len(results)
    
    print("\n" + "="*70)
    print("平均性能")
    print("="*70)
    print(f"  平均耗时: {avg_time:.2f}秒")
    print(f"  平均效率: {avg_efficiency:.1f}方案/秒")
    print(f"  平均收益率: {avg_return:.2f}%")
    
    print("\n" + "="*70)
    print("优化效率测试完成！")
    print("="*70)

def main():
    """
    主函数
    """
    run_efficiency_tests()

if __name__ == "__main__":
    main()
