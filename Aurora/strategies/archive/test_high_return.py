#!/usr/bin/env python3
"""
测试HighReturnGridTrading策略
"""

import numpy as np
import pandas as pd
import sys
import os

# 添加父目录到路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 导入HighReturnGridTrading策略
from high_return_grid import HighReturnGridTrading

def generate_range_bound_data(n=1000):
    """
    生成横盘市场数据
    """
    np.random.seed(42)
    price = [100.0]
    for i in range(1, n):
        # 生成横盘市场数据
        ret = np.random.normal(0, 0.001)
        price.append(price[-1] * (1 + ret))
    return pd.DataFrame({'close': price})

def test_high_return_strategy():
    """
    测试HighReturnGridTrading策略
    """
    # 生成测试数据
    data = generate_range_bound_data()
    
    # 初始化策略
    strategy = HighReturnGridTrading(initial_balance=100000.0, base_price=data['close'].iloc[0])
    
    # 模拟交易
    for i in range(len(data)):
        current_price = data['close'].iloc[i]
        result = strategy.update_price(current_price)
        
        # 打印每100个价格点的状态
        if (i + 1) % 100 == 0:
            current_equity = result.get('current_equity', strategy.balance + strategy.position * current_price)
            return_rate = (current_equity - strategy.initial_balance) / strategy.initial_balance
            print(f"Step {i+1}: Price={current_price:.2f}, Balance={result['balance']:.2f}, Position={result['position']:.2f}, Equity={current_equity:.2f}, Return={return_rate*100:.2f}%")
    
    # 获取最终性能
    performance = strategy.get_performance()
    print("\n最终性能:")
    print(f"初始资金: {performance['initial_balance']:.2f}")
    print(f"当前资金: {performance['current_balance']:.2f}")
    print(f"收益率: {performance['return']*100:.2f}%")
    print(f"交易次数: {performance['total_trades']}")
    print(f"胜率: {performance['win_rate']*100:.2f}%")
    print(f"总盈利: {performance['total_profit']:.2f}")

if __name__ == "__main__":
    test_high_return_strategy()
