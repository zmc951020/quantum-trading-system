#!/usr/bin/env python3
"""
简单测试脚本 - 直接运行量化交易系统
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
    print("Aurora Quantitative Trading System - Quick Test")
    print("=" * 60)
    
    # 生成测试数据
    print("\nGenerating test data...")
    data = generate_simple_test_data(length=100)
    print(f"   Data points: {len(data)}")
    print(f"   Price range: {data.min():.2f} - {data.max():.2f}")
    
    # 导入简化的策略
    try:
        from strategies.ml_range_grid import MLRangeGridTrading
        print("\nInitializing ML range grid strategy...")
        
        base_price = data.iloc[0]
        strategy = MLRangeGridTrading(base_price=base_price, initial_balance=100000)
        print("   Strategy initialized successfully!")
        
        # 运行策略
        print("\nRunning strategy backtest...")
        for i, price in enumerate(data):
            strategy.update_price(price, data.iloc[:i+1] if i >= 100 else None)
        
        # 获取性能
        performance = strategy.get_performance()
        print("\nStrategy Performance Results:")
        print(f"   Total Return: {performance['total_return'] * 100:.2f}%")
        print(f"   Sharpe Ratio: {performance['sharpe_ratio']:.2f}")
        print(f"   Win Rate: {performance['win_rate'] * 100:.2f}%")
        print(f"   Total Trades: {performance['total_trades']}")
        
        # 测试成功
        print("\nSystem running successfully!")
        print("=" * 60)
        print("\nExplanation:")
        print("   This is a quick test to prove the system can run locally")
        print("   No Docker required, saves lots of memory")
        print("   Full system can be run via main.py")
        print("\nUsage:")
        print("   1. Run backtest: python main.py backtest")
        print("   2. Start trading: python main.py start")
        print("   3. Train model: python main.py train")
        print("=" * 60)
        
        return True
        
    except Exception as e:
        logger.error(f"Strategy running failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    test_grid_trading()
