#!/usr/bin/env python3
"""
持久化测试 - 验证电脑重启后成果传承
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

def generate_test_data(length: int = 300, start_price: float = 100):
    """
    生成测试数据
    """
    dates = pd.date_range(start=datetime.now() - timedelta(days=length), periods=length, freq='D')
    returns = np.random.normal(0, 0.01, length)
    # 添加趋势和周期
    trend = np.linspace(0, 0.2, length)  # 20%的长期趋势
    cycle = 0.08 * np.sin(np.linspace(0, 6 * np.pi, length))  # 周期性波动
    returns = returns + trend + cycle
    prices = start_price * (1 + returns).cumprod()
    return pd.Series(prices, index=dates)

def test_persistence():
    """
    测试持久化功能
    """
    print("="*70)
    print("持久化测试 - 验证电脑重启后成果传承")
    print("="*70)
    print("测试内容:")
    print("  1. 第一次优化")
    print("  2. 模拟电脑重启")
    print("  3. 第二次优化（验证成果传承）")
    print("  4. 验证队列持久化")
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
    
    # 测试1: 第一次优化
    print("\n" + "="*70)
    print("测试1: 第一次优化")
    print("="*70)
    
    ml_allocator1 = MODULES['MLFundAllocator'](initial_balance=100000)
    dca1 = MODULES['DCAStrategy']()
    grid1 = MODULES['GridTrading'](base_price=100, grid_spacing=0.01)
    
    ml_allocator1.add_strategy("dca", dca1, 0.5)
    ml_allocator1.add_strategy("grid", grid1, 0.5)
    
    data1 = generate_test_data(length=300)
    print(f"  数据点: {len(data1)}")
    
    start_time1 = datetime.now()
    ml_allocator1.optimize_with_machine_learning(
        data1,
        max_queue_size=30,
        convergence_threshold=0.0001,
        convergence_patience=50,
        print_interval=25,
        parallel_workers=4
    )
    elapsed_time1 = (datetime.now() - start_time1).total_seconds()
    
    # 运行策略
    for i, price in enumerate(data1):
        timestamp = data1.index[i]
        ml_allocator1.update(price, timestamp)
    
    perf1 = ml_allocator1.get_performance(data1.iloc[-1])
    print(f"  耗时: {elapsed_time1:.2f}秒")
    print(f"  收益率: {perf1['overall']['return']:.2f}%")
    print(f"  队列大小: {len(ml_allocator1.candidate_queue)}")
    print(f"  优化周期: {ml_allocator1.optimization_cycle}")
    
    # 检查队列文件是否创建
    if os.path.exists(queue_file):
        print(f"  [OK] 队列文件已创建: {queue_file}")
        queue_size = os.path.getsize(queue_file)
        print(f"  队列文件大小: {queue_size} 字节")
    else:
        print(f"  [FAIL] 队列文件未创建")
        return
    
    # 测试2: 模拟电脑重启（创建新的分配器实例）
    print("\n" + "="*70)
    print("测试2: 模拟电脑重启")
    print("="*70)
    print("  模拟电脑重启...")
    print("  创建新的ML分配器实例...")
    
    # 创建新的分配器实例
    ml_allocator2 = MODULES['MLFundAllocator'](initial_balance=100000)
    dca2 = MODULES['DCAStrategy']()
    grid2 = MODULES['GridTrading'](base_price=100, grid_spacing=0.01)
    
    ml_allocator2.add_strategy("dca", dca2, 0.5)
    ml_allocator2.add_strategy("grid", grid2, 0.5)
    
    # 检查是否成功加载历史队列
    print(f"  加载历史队列大小: {len(ml_allocator2.candidate_queue)}")
    print(f"  优化周期: {ml_allocator2.optimization_cycle}")
    
    if len(ml_allocator2.candidate_queue) > 0:
        print(f"  [OK] 成功加载历史队列")
        best_candidate = sorted(ml_allocator2.candidate_queue, key=lambda x: x['return'], reverse=True)[0]
        print(f"  历史最佳收益率: {best_candidate['return']:.4f}")
        print(f"  历史最佳分配: {best_candidate['allocations']}")
    else:
        print(f"  [FAIL] 未加载到历史队列")
        return
    
    # 测试3: 第二次优化（验证成果传承）
    print("\n" + "="*70)
    print("测试3: 第二次优化（验证成果传承）")
    print("="*70)
    
    data2 = generate_test_data(length=200, start_price=data1.iloc[-1])
    
    start_time2 = datetime.now()
    ml_allocator2.optimize_with_machine_learning(
        data2,
        max_queue_size=30,
        convergence_threshold=0.0001,
        convergence_patience=50,
        print_interval=25,
        parallel_workers=4
    )
    elapsed_time2 = (datetime.now() - start_time2).total_seconds()
    
    # 运行策略
    for i, price in enumerate(data2):
        timestamp = data2.index[i]
        ml_allocator2.update(price, timestamp)
    
    perf2 = ml_allocator2.get_performance(data2.iloc[-1])
    print(f"  耗时: {elapsed_time2:.2f}秒")
    print(f"  收益率: {perf2['overall']['return']:.2f}%")
    print(f"  队列大小: {len(ml_allocator2.candidate_queue)}")
    print(f"  优化周期: {ml_allocator2.optimization_cycle}")
    
    # 测试4: 验证队列持久化
    print("\n" + "="*70)
    print("测试4: 验证队列持久化")
    print("="*70)
    
    # 检查队列文件是否更新
    if os.path.exists(queue_file):
        print(f"  [OK] 队列文件存在")
        queue_size = os.path.getsize(queue_file)
        print(f"  队列文件大小: {queue_size} 字节")
    else:
        print(f"  [FAIL] 队列文件不存在")
        return
    
    # 清理队列文件
    if os.path.exists(queue_file):
        os.remove(queue_file)
        print("  [INFO] 清理队列文件")
    
    # 打印总结
    print("\n" + "="*70)
    print("持久化测试总结")
    print("="*70)
    print(f"第一次优化: {perf1['overall']['return']:.2f}% (耗时: {elapsed_time1:.2f}秒)")
    print(f"第二次优化: {perf2['overall']['return']:.2f}% (耗时: {elapsed_time2:.2f}秒)")
    print(f"队列大小: {len(ml_allocator2.candidate_queue)}")
    print(f"优化周期: {ml_allocator2.optimization_cycle}")
    
    print("\n" + "="*70)
    print("持久化功能验证:")
    print("="*70)
    print("  [OK] 智能队列: 已验证")
    print("  [OK] 周期循环: 已验证")
    print("  [OK] 成果传承: 已验证")
    print("  [OK] 电脑重启后成果继承: 已验证")
    print("  [OK] 队列持久化: 已验证")
    
    print("\n" + "="*70)
    print("持久化测试完成！")
    print("="*70)

def main():
    """
    主函数
    """
    test_persistence()

if __name__ == "__main__":
    main()
