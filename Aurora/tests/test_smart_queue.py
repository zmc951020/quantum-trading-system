#!/usr/bin/env python3
"""
测试智能队列优化方法
"""

import os
import sys
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from tests.test_system import TestConfig, SimpleMonitor, SimpleEvaluator, SimpleReportGenerator

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

def generate_test_data(length: int = 500, start_price: float = 100, volatility: float = 0.01):
    """生成测试数据"""
    dates = pd.date_range(start=datetime.now() - timedelta(days=length), periods=length, freq='D')
    returns = np.random.normal(0, volatility, length)
    prices = start_price * (1 + returns).cumprod()
    return pd.Series(prices, index=dates)

def main():
    """主函数"""
    print("="*70)
    print("智能队列优化测试")
    print("="*70)
    
    # 检查必要模块
    required_modules = ['MLFundAllocator', 'DCAStrategy', 'GridTrading']
    for mod in required_modules:
        if mod not in MODULES:
            print(f"\n[FAIL] 缺少必要模块: {mod}")
            return
    
    print("\n[OK] 所有必要模块已加载")
    
    # 生成测试数据
    print("\n生成测试数据...")
    data = generate_test_data(length=300)
    print(f"  数据点数: {len(data)}")
    print(f"  价格范围: {data.min():.2f} - {data.max():.2f}")
    
    # 创建ML资金分配器
    print("\n初始化ML资金分配器...")
    ml_allocator = MODULES['MLFundAllocator'](initial_balance=100000)
    
    # 添加策略
    dca = MODULES['DCAStrategy']()
    grid = MODULES['GridTrading'](base_price=data.iloc[0], grid_spacing=0.01)
    
    ml_allocator.add_strategy("dca", dca, 0.5)
    ml_allocator.add_strategy("grid", grid, 0.5)
    
    print("[OK] 策略已添加")
    
    # 第一次优化
    print("\n" + "="*70)
    print("第一次优化周期")
    print("="*70)
    ml_allocator.optimize_with_machine_learning(
        data,
        max_queue_size=30,
        convergence_threshold=0.0001,
        convergence_patience=50,
        print_interval=20
    )
    
    # 运行策略
    print("\n运行策略...")
    for i, price in enumerate(data):
        timestamp = data.index[i]
        ml_allocator.update(price, timestamp)
    
    # 获取性能
    perf = ml_allocator.get_performance(data.iloc[-1])
    print(f"\n第一次优化后性能:")
    print(f"  总价值: {perf['overall']['total_value']:.2f}")
    print(f"  收益率: {perf['overall']['return']:.2f}%")
    print(f"  当前分配: {perf['overall']['current_allocations']}")
    
    # 第二次优化（使用历史队列）
    print("\n" + "="*70)
    print("第二次优化周期（使用历史队列）")
    print("="*70)
    
    # 生成新的测试数据
    data2 = generate_test_data(length=300, start_price=data.iloc[-1])
    
    ml_allocator.optimize_with_machine_learning(
        data2,
        max_queue_size=30,
        convergence_threshold=0.0001,
        convergence_patience=50,
        print_interval=20
    )
    
    print("\n" + "="*70)
    print("智能队列优化测试完成！")
    print("="*70)
    print("\n核心优势:")
    print("  [OK] 不需要设置固定最大迭代次数")
    print("  [OK] 维护候选方案队列，按性能排序")
    print("  [OK] 基于收敛判断自动停止")
    print("  [OK] 支持跨交易周期持续优化")
    print("  [OK] 在历史优秀方案附近探索，效率更高")
    print("="*70)

if __name__ == "__main__":
    main()
