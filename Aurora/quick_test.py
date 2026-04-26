#!/usr/bin/env python3
"""
快速测试脚本 - 直接运行量化交易系统
"""
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import logging
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def generate_simple_test_data(length=100, start_price=100):
    """
    生成简单的测试数据
    """
    dates = pd.date_range(start=datetime.now() - timedelta(days=length), periods=length, freq='D')
    returns = np.random.normal(0, 0.015, length)
    prices = start_price * (1 + returns).cumprod()
    return pd.Series(prices, index=dates)

def test_grid_trading():
    """
    测试简单的网格交易策略
    """
    print("=" * 60)
    print("Aurora 量化交易系统 - 快速测试")
    print("=" * 60)
    
    # 生成测试数据
    print("\n📊 生成测试数据...")
    data = generate_simple_test_data(length=100)
    print(f"   数据点: {len(data)}")
    print(f"   价格范围: {data.min():.2f} - {data.max():.2f}")
    
    # 导入简化的策略
    try:
        from strategies.ml_range_grid import MLRangeGridTrading
        print("\n🚀 初始化机器学习横盘网格策略...")
        
        base_price = data.iloc[0]
        strategy = MLRangeGridTrading(base_price=base_price, initial_balance=100000)
        print("   策略初始化成功!")
        
        # 运行策略
        print("\n▶️  运行策略回测...")
        for i, price in enumerate(data):
            strategy.update_price(price, data.iloc[:i+1] if i >= 100 else None)
        
        # 获取性能
        performance = strategy.get_performance()
        print("\n📈 策略性能结果:")
        print(f"   总收益率: {performance['total_return'] * 100:.2f}%")
        print(f"   夏普比率: {performance['sharpe_ratio']:.2f}")
        print(f"   胜率: {performance['win_rate'] * 100:.2f}%")
        print(f"   交易次数: {performance['total_trades']}")
        
        # 测试成功
        print("\n✅ 系统运行成功!")
        print("=" * 60)
        print("\n💡 说明:")
        print("   这是一个快速测试，证明系统可以在本地运行")
        print("   不需要Docker，节省大量内存")
        print("   完整系统可以通过 main.py 运行")
        print("\n📝 使用方法:")
        print("   1. 运行回测: python main.py backtest")
        print("   2. 启动交易系统: python main.py start")
        print("   3. 训练模型: python main.py train")
        print("=" * 60)
        
        return True
        
    except Exception as e:
        logger.error(f"策略运行失败: {str(e)}")
        return False

if __name__ == "__main__":
    test_grid_trading()
