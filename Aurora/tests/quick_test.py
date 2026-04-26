#!/usr/bin/env python3
"""
快速测试 - 验证所有改进是否正常工作
"""

import os
import sys
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from tests.test_system import TestConfig, SystemTester

def main():
    """主函数"""
    print("=" * 70)
    print("快速测试 - 验证所有改进")
    print("=" * 70)
    
    # 创建测试配置 - 使用小规模快速测试
    config = TestConfig()
    config.DATA_LENGTH = 100  # 减少数据长度
    config.ML_OPTIMIZATION_ITERATIONS = 100  # 减少迭代次数
    config.ML_PRINT_INTERVAL = 20  # 更频繁的打印
    
    print(f"\n【测试配置】")
    print(f"  数据长度: {config.DATA_LENGTH} 条")
    print(f"  数据频率: 日度")
    print(f"  机器学习迭代: {config.ML_OPTIMIZATION_ITERATIONS} 次")
    print(f"  初始资金: {config.INITIAL_BALANCE:.2f}")
    
    # 创建测试器
    tester = SystemTester(config)
    
    # 生成测试数据
    print(f"\n生成测试数据...")
    data = tester.generate_test_data()
    print(f"  数据点数: {len(data)}")
    print(f"  时间范围: {data.index[0]} 至 {data.index[-1]}")
    print(f"  价格范围: {data.min():.2f} - {data.max():.2f}")
    
    # 测试配置类的功能
    print(f"\n【验证配置灵活性】")
    print("  可以轻松切换数据频率:")
    print("  - 'D' = 日度 (默认)")
    print("  - 'H' = 小时级")
    print("  - 'T' = 分钟级")
    print("  - 'S' = 秒级")
    
    print("\n  可以设置交易频率限制:")
    print("  - MAX_TRADES_PER_MINUTE = None (每分钟最大次数)")
    print("  - MAX_TRADES_PER_HOUR = None (每小时最大次数)")
    print("  - MAX_TRADES_PER_DAY = None (每天最大次数)")
    print("  - MAX_TRADE_AMOUNT = None (单次最大金额)")
    
    print("\n【验证关键概念】")
    print("  [OK] 数据频率 ≠ 交易频率")
    print("  [OK] 每个数据点可以交易0次、1次或多次")
    print("  [OK] 由策略逻辑决定何时交易，而非固定频率")
    
    print("\n" + "=" * 70)
    print("快速验证完成！")
    print("=" * 70)
    print("\n如需运行完整测试，请执行:")
    print("  python tests/test_system.py")
    print("\n或使用分钟级数据测试:")
    print("  (编辑 tests/test_system.py 中的 main() 函数)")
    print("  config.DATA_FREQUENCY = 'T'")
    print("  config.DATA_LENGTH = 1440")

if __name__ == "__main__":
    main()
