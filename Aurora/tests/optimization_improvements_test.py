#!/usr/bin/env python3
"""
优化改进测试 - 验证队列持久化、多策略支持、并行优化
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

def generate_market_data(length: int = 300, start_price: float = 100, volatility: float = 0.01):
    """
    生成市场数据
    """
    dates = pd.date_range(start=datetime.now() - timedelta(days=length), periods=length, freq='D')
    returns = np.random.normal(0, volatility, length)
    prices = start_price * (1 + returns).cumprod()
    return pd.Series(prices, index=dates)

def test_queue_persistence():
    """
    测试队列持久化
    """
    print("\n" + "="*70)
    print("测试1: 队列持久化")
    print("="*70)
    
    # 检查必要模块
    required_modules = ['MLFundAllocator', 'DCAStrategy', 'GridTrading']
    for mod in required_modules:
        if mod not in MODULES:
            print(f"\n[FAIL] 缺少必要模块: {mod}")
            return False
    
    # 清理旧的队列文件
    queue_file = "candidate_queue.pkl"
    if os.path.exists(queue_file):
        os.remove(queue_file)
        print("[INFO] 清理旧的队列文件")
    
    # 第一次运行
    print("\n第一次运行...")
    ml_allocator1 = MODULES['MLFundAllocator'](initial_balance=100000)
    
    # 添加策略
    dca = MODULES['DCAStrategy']()
    grid = MODULES['GridTrading'](base_price=100, grid_spacing=0.01)
    
    ml_allocator1.add_strategy("dca", dca, 0.5)
    ml_allocator1.add_strategy("grid", grid, 0.5)
    
    # 生成测试数据
    data = generate_market_data(length=200)
    
    # 运行优化
    ml_allocator1.optimize_with_machine_learning(
        data,
        max_queue_size=20,
        convergence_threshold=0.0001,
        convergence_patience=50,
        print_interval=20,
        parallel_workers=4
    )
    
    first_queue_size = len(ml_allocator1.candidate_queue)
    print(f"\n第一次运行后队列大小: {first_queue_size}")
    
    # 第二次运行（应该加载历史队列）
    print("\n第二次运行（加载历史队列）...")
    ml_allocator2 = MODULES['MLFundAllocator'](initial_balance=100000)
    
    # 添加相同的策略
    dca2 = MODULES['DCAStrategy']()
    grid2 = MODULES['GridTrading'](base_price=100, grid_spacing=0.01)
    
    ml_allocator2.add_strategy("dca", dca2, 0.5)
    ml_allocator2.add_strategy("grid", grid2, 0.5)
    
    # 运行优化
    ml_allocator2.optimize_with_machine_learning(
        data,
        max_queue_size=20,
        convergence_threshold=0.0001,
        convergence_patience=50,
        print_interval=20,
        parallel_workers=4
    )
    
    second_queue_size = len(ml_allocator2.candidate_queue)
    print(f"\n第二次运行后队列大小: {second_queue_size}")
    
    if second_queue_size >= first_queue_size:
        print("\n[OK] 队列持久化测试通过！")
        return True
    else:
        print("\n[FAIL] 队列持久化测试失败！")
        return False

def test_multi_strategy_support():
    """
    测试多策略支持
    """
    print("\n" + "="*70)
    print("测试2: 多策略支持")
    print("="*70)
    
    # 检查必要模块
    required_modules = ['MLFundAllocator', 'DCAStrategy']
    for mod in required_modules:
        if mod not in MODULES:
            print(f"\n[FAIL] 缺少必要模块: {mod}")
            return False
    
    # 创建ML资金分配器
    ml_allocator = MODULES['MLFundAllocator'](initial_balance=100000)
    
    # 添加多个策略
    dca = MODULES['DCAStrategy']()
    
    # 尝试添加多个策略（这里我们用同一个策略作为示例）
    ml_allocator.add_strategy("dca1", dca, 1/3)
    
    # 生成测试数据
    data = generate_market_data(length=100)
    
    # 测试二策略情况
    print("\n测试二策略情况...")
    dca2 = MODULES['DCAStrategy']()
    ml_allocator.add_strategy("dca2", dca2, 1/3)
    
    candidate = ml_allocator._generate_candidate()
    print(f"二策略候选方案: {candidate}")
    print(f"分配总和: {sum(candidate.values()):.4f}")
    
    # 测试多策略情况
    print("\n测试多策略情况...")
    dca3 = MODULES['DCAStrategy']()
    ml_allocator.add_strategy("dca3", dca3, 1/3)
    
    candidate = ml_allocator._generate_candidate()
    print(f"多策略候选方案: {candidate}")
    print(f"分配总和: {sum(candidate.values()):.4f}")
    
    if len(candidate) == 3 and abs(sum(candidate.values()) - 1.0) < 0.001:
        print("\n[OK] 多策略支持测试通过！")
        return True
    else:
        print("\n[FAIL] 多策略支持测试失败！")
        return False

def test_parallel_optimization():
    """
    测试并行优化
    """
    print("\n" + "="*70)
    print("测试3: 并行优化")
    print("="*70)
    
    # 检查必要模块
    required_modules = ['MLFundAllocator', 'DCAStrategy', 'GridTrading']
    for mod in required_modules:
        if mod not in MODULES:
            print(f"\n[FAIL] 缺少必要模块: {mod}")
            return False
    
    # 创建ML资金分配器
    ml_allocator = MODULES['MLFundAllocator'](initial_balance=100000)
    
    # 添加策略
    dca = MODULES['DCAStrategy']()
    grid = MODULES['GridTrading'](base_price=100, grid_spacing=0.01)
    
    ml_allocator.add_strategy("dca", dca, 0.5)
    ml_allocator.add_strategy("grid", grid, 0.5)
    
    # 生成测试数据
    data = generate_market_data(length=150)
    
    # 运行并行优化
    print("\n运行并行优化...")
    start_time = datetime.now()
    ml_allocator.optimize_with_machine_learning(
        data,
        max_queue_size=20,
        convergence_threshold=0.0001,
        convergence_patience=30,
        print_interval=10,
        parallel_workers=4
    )
    elapsed_time = (datetime.now() - start_time).total_seconds()
    
    print(f"\n并行优化耗时: {elapsed_time:.2f}秒")
    print(f"队列大小: {len(ml_allocator.candidate_queue)}")
    
    if len(ml_allocator.candidate_queue) > 0:
        print("\n[OK] 并行优化测试通过！")
        return True
    else:
        print("\n[FAIL] 并行优化测试失败！")
        return False

def main():
    """
    主函数
    """
    print("="*70)
    print("优化改进测试")
    print("="*70)
    print("测试内容:")
    print("  1. 队列持久化")
    print("  2. 多策略支持")
    print("  3. 并行优化")
    print("="*70)
    
    results = []
    
    # 测试队列持久化
    results.append(test_queue_persistence())
    
    # 测试多策略支持
    results.append(test_multi_strategy_support())
    
    # 测试并行优化
    results.append(test_parallel_optimization())
    
    # 清理队列文件
    queue_file = "candidate_queue.pkl"
    if os.path.exists(queue_file):
        os.remove(queue_file)
        print("\n[INFO] 清理队列文件")
    
    # 打印总结
    print("\n" + "="*70)
    print("测试总结")
    print("="*70)
    print(f"队列持久化: {'通过' if results[0] else '失败'}")
    print(f"多策略支持: {'通过' if results[1] else '失败'}")
    print(f"并行优化: {'通过' if results[2] else '失败'}")
    
    if all(results):
        print("\n[OK] 所有优化改进测试通过！")
    else:
        print("\n[FAIL] 部分测试失败！")
    
    print("="*70)

if __name__ == "__main__":
    main()
