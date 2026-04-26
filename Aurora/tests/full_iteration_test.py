#!/usr/bin/env python3
"""
完整测试迭代 - 验证智能队列优化
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

def generate_trending_data(length: int = 500, start_price: float = 100):
    """生成有趋势的测试数据"""
    dates = pd.date_range(start=datetime.now() - timedelta(days=length), periods=length, freq='D')
    # 创建上升趋势 + 随机波动
    trend = np.linspace(0, 0.3, length)  # 30%的上升趋势
    noise = np.random.normal(0, 0.01, length)
    returns = trend + noise
    prices = start_price * (1 + returns).cumprod()
    return pd.Series(prices, index=dates)

def generate_range_bound_data(length: int = 500, start_price: float = 100):
    """生成区间震荡的测试数据"""
    dates = pd.date_range(start=datetime.now() - timedelta(days=length), periods=length, freq='D')
    # 均值回归 + 随机波动
    prices = [start_price]
    for i in range(1, length):
        # 向均值回归
        mean_reversion = (start_price - prices[-1]) * 0.02
        noise = np.random.normal(0, 0.008)
        price = prices[-1] * (1 + mean_reversion + noise)
        prices.append(price)
    return pd.Series(prices, index=dates)

def run_single_test(test_name: str, data: pd.Series, config_override: dict = None):
    """运行单个测试"""
    print(f"\n{'='*70}")
    print(f"测试: {test_name}")
    print(f"{'='*70}")
    
    # 检查必要模块
    required_modules = ['MLFundAllocator', 'DCAStrategy', 'GridTrading']
    for mod in required_modules:
        if mod not in MODULES:
            print(f"\n[FAIL] 缺少必要模块: {mod}")
            return None
    
    print(f"\n数据: {len(data)} 条")
    print(f"价格范围: {data.min():.2f} - {data.max():.2f}")
    print(f"价格变化: {((data.iloc[-1] - data.iloc[0]) / data.iloc[0] * 100):.2f}%")
    
    # 创建ML资金分配器
    ml_allocator = MODULES['MLFundAllocator'](initial_balance=100000)
    
    # 添加策略
    dca = MODULES['DCAStrategy']()
    grid = MODULES['GridTrading'](base_price=data.iloc[0], grid_spacing=0.01)
    
    ml_allocator.add_strategy("dca", dca, 0.5)
    ml_allocator.add_strategy("grid", grid, 0.5)
    
    # 应用配置覆盖
    default_config = {
        'max_queue_size': 50,
        'convergence_threshold': 0.0001,
        'convergence_patience': 100,
        'print_interval': 50
    }
    if config_override:
        default_config.update(config_override)
    
    # 运行优化
    start_time = datetime.now()
    ml_allocator.optimize_with_machine_learning(data, **default_config)
    optimization_time = (datetime.now() - start_time).total_seconds()
    
    # 运行策略
    for i, price in enumerate(data):
        timestamp = data.index[i]
        ml_allocator.update(price, timestamp)
    
    # 获取性能
    perf = ml_allocator.get_performance(data.iloc[-1])
    
    result = {
        'test_name': test_name,
        'optimization_time': optimization_time,
        'iterations': ml_allocator.optimization_cycle,
        'queue_size': len(ml_allocator.candidate_queue),
        'final_return': perf['overall']['return'],
        'final_allocations': perf['overall']['current_allocations'],
        'candidate_queue': ml_allocator.candidate_queue.copy() if ml_allocator.candidate_queue else []
    }
    
    print(f"\n{'='*70}")
    print(f"测试结果: {test_name}")
    print(f"{'='*70}")
    print(f"优化耗时: {optimization_time:.2f}秒")
    print(f"队列大小: {len(ml_allocator.candidate_queue)}")
    print(f"最终收益率: {perf['overall']['return']:.2f}%")
    print(f"最终分配: {perf['overall']['current_allocations']}")
    
    return result

def main():
    """主函数"""
    print("="*70)
    print("完整测试迭代 - 智能队列优化")
    print("="*70)
    
    results = []
    
    # 测试1: 趋势市场
    print("\n" + "="*70)
    print("测试1/3: 趋势市场数据")
    print("="*70)
    data_trending = generate_trending_data(length=400)
    result1 = run_single_test("趋势市场", data_trending)
    if result1:
        results.append(result1)
    
    # 测试2: 区间震荡市场
    print("\n" + "="*70)
    print("测试2/3: 区间震荡市场数据")
    print("="*70)
    data_range = generate_range_bound_data(length=400)
    result2 = run_single_test("区间震荡市场", data_range)
    if result2:
        results.append(result2)
    
    # 测试3: 标准随机市场
    print("\n" + "="*70)
    print("测试3/3: 标准随机市场数据")
    print("="*70)
    dates = pd.date_range(start=datetime.now() - timedelta(days=400), periods=400, freq='D')
    returns = np.random.normal(0, 0.01, 400)
    prices = 100 * (1 + returns).cumprod()
    data_random = pd.Series(prices, index=dates)
    result3 = run_single_test("标准随机市场", data_random)
    if result3:
        results.append(result3)
    
    # 打印摘要
    print("\n" + "="*70)
    print("测试摘要")
    print("="*70)
    for r in results:
        print(f"\n{r['test_name']}:")
        print(f"  收益率: {r['final_return']:.2f}%")
        print(f"  优化耗时: {r['optimization_time']:.2f}秒")
        print(f"  队列大小: {r['queue_size']}")
    
    print("\n" + "="*70)
    print("完整测试迭代完成！")
    print("="*70)
    print("\n智能队列优化的核心价值:")
    print("  1. 不设固定迭代次数，自动收敛")
    print("  2. 维护优秀方案队列，按性能排序")
    print("  3. 支持跨周期持续优化")
    print("  4. 在历史优秀方案附近探索，效率更高")
    print("  5. 自适应不同市场环境（趋势、震荡、随机）")
    print("="*70)

if __name__ == "__main__":
    main()
