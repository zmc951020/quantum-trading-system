#!/usr/bin/env python3
"""
简单测试脚本
"""

import numpy as np
import sys

sys.path.insert(0, '.')

print("正在导入策略...")
try:
    from newton_momentum_enhanced import NewtonMomentumEnhanced
    print("✓ NewtonMomentumEnhanced 导入成功")
except Exception as e:
    print(f"✗ NewtonMomentumEnhanced 导入失败: {e}")

try:
    from thermodynamic_entropy_enhanced import ThermodynamicEntropyEnhanced
    print("✓ ThermodynamicEntropyEnhanced 导入成功")
except Exception as e:
    print(f"✗ ThermodynamicEntropyEnhanced 导入失败: {e}")

print("\n测试牛顿动量策略...")
try:
    strategy = NewtonMomentumEnhanced(base_price=100.0, initial_balance=100000)
    print("✓ 策略初始化成功")
    
    # 测试基本方法
    result = strategy.update_price(100.5, 1000)
    print(f"✓ update_price 调用成功: action={result['action']}")
    
    perf = strategy.get_performance()
    print(f"✓ get_performance 调用成功: trades={perf['total_trades']}")
    
    physics = strategy.get_physics_summary()
    print(f"✓ get_physics_summary 调用成功: {physics}")
    
except Exception as e:
    print(f"✗ 测试失败: {e}")

print("\n测试完成!")
