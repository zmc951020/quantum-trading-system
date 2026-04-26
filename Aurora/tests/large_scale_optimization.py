#!/usr/bin/env python3
"""
大规模优化迭代测试 - 验证系统在更大规模下的性能
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

def generate_large_market_data(length: int = 1000, start_price: float = 100, volatility: float = 0.01):
    """
    生成大规模市场数据
    """
    dates = pd.date_range(start=datetime.now() - timedelta(days=length), periods=length, freq='D')
    returns = np.random.normal(0, volatility, length)
    # 添加一些趋势和周期
    trend = np.linspace(0, 0.2, length)  # 20%的长期趋势
    cycle = 0.08 * np.sin(np.linspace(0, 6 * np.pi, length))  # 周期性波动
    returns = returns + trend + cycle
    prices = start_price * (1 + returns).cumprod()
    return pd.Series(prices, index=dates)

def run_large_scale_optimization():
    """
    运行大规模优化迭代
    """
    print("="*70)
    print("大规模优化迭代测试")
    print("="*70)
    print("测试规模:")
    print("  1. 数据长度: 1000个数据点")
    print("  2. 并行工作线程: 8个")
    print("  3. 队列大小: 100个候选方案")
    print("  4. 收敛耐心: 200次")
    print("  5. 多周期测试: 3个周期")
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
    
    # 创建ML资金分配器
    print("\n初始化ML资金分配器...")
    ml_allocator = MODULES['MLFundAllocator'](initial_balance=100000)
    
    # 添加策略
    dca = MODULES['DCAStrategy']()
    grid = MODULES['GridTrading'](base_price=100, grid_spacing=0.01)
    
    ml_allocator.add_strategy("dca", dca, 0.5)
    ml_allocator.add_strategy("grid", grid, 0.5)
    
    print("[OK] 策略已添加")
    
    total_time = 0
    total_iterations = 0
    total_evaluations = 0
    best_returns = []
    
    # 运行3个优化周期
    for cycle in range(1, 4):
        print(f"\n" + "="*70)
        print(f"优化周期 {cycle}/3")
        print("="*70)
        
        # 生成大规模测试数据
        print("生成大规模测试数据...")
        data = generate_large_market_data(length=1000)
        print(f"  数据点: {len(data)}")
        print(f"  价格范围: {data.min():.2f} - {data.max():.2f}")
        print(f"  价格变化: {((data.iloc[-1] - data.iloc[0]) / data.iloc[0] * 100):.2f}%")
        
        # 运行优化
        print("\n运行大规模智能队列优化...")
        start_time = datetime.now()
        ml_allocator.optimize_with_machine_learning(
            data,
            max_queue_size=100,
            convergence_threshold=0.00005,
            convergence_patience=200,
            print_interval=100,
            parallel_workers=8
        )
        elapsed_time = (datetime.now() - start_time).total_seconds()
        total_time += elapsed_time
        
        # 计算总评估次数
        # 假设每次迭代评估8个方案
        cycle_iterations = ml_allocator.optimization_cycle
        if cycle > 1:
            cycle_iterations -= total_iterations
        total_iterations = ml_allocator.optimization_cycle
        cycle_evaluations = cycle_iterations * 8
        total_evaluations += cycle_evaluations
        
        # 运行策略
        print("\n运行策略...")
        for i, price in enumerate(data):
            timestamp = data.index[i]
            ml_allocator.update(price, timestamp)
        
        # 获取性能
        perf = ml_allocator.get_performance(data.iloc[-1])
        current_return = perf['overall']['return']
        best_returns.append(current_return)
        
        print(f"\n周期 {cycle} 结果:")
        print(f"  耗时: {elapsed_time:.2f}秒")
        print(f"  迭代次数: {cycle_iterations}")
        print(f"  评估方案数: {cycle_evaluations}")
        print(f"  队列大小: {len(ml_allocator.candidate_queue)}")
        print(f"  收益率: {current_return:.2f}%")
        print(f"  最终分配: {perf['overall']['current_allocations']}")
    
    # 清理队列文件
    if os.path.exists(queue_file):
        os.remove(queue_file)
        print("\n[INFO] 清理队列文件")
    
    # 打印总结
    print("\n" + "="*70)
    print("大规模优化迭代测试完成！")
    print("="*70)
    print(f"总耗时: {total_time:.2f}秒")
    print(f"总迭代次数: {total_iterations}")
    print(f"总评估方案数: {total_evaluations}")
    print(f"平均周期耗时: {total_time / 3:.2f}秒")
    print(f"最佳收益率: {max(best_returns):.2f}%")
    print(f"平均收益率: {sum(best_returns) / 3:.2f}%")
    
    print("\n" + "="*70)
    print("性能分析:")
    print("="*70)
    print(f"  数据规模: 1000个数据点/周期")
    print(f"  并行效率: 8线程")
    print(f"  队列管理: 100个候选方案")
    print(f"  收敛速度: 平均 {total_iterations / 3:.1f}次迭代/周期")
    print(f"  评估效率: {total_evaluations / total_time:.1f}方案/秒")
    
    print("\n" + "="*70)
    print("大规模优化迭代成功完成！")
    print("="*70)

def main():
    """
    主函数
    """
    run_large_scale_optimization()

if __name__ == "__main__":
    main()
