#!/usr/bin/env python3
"""
简单网格交易测试
"""

import os
import sys
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    from strategies.grid_trading import GridTrading
except ImportError as e:
    print(f"错误: {str(e)}")
    sys.exit(1)

def test_simple_grid():
    """简单网格交易测试"""
    print("="*60)
    print("简单网格交易测试")
    print("="*60)
    
    # 生成横盘震荡数据
    dates = pd.date_range(start=datetime.now() - timedelta(days=365), periods=365, freq='D')
    start_price = 100
    prices = []
    current_price = start_price
    
    for i in range(365):
        # 模拟横盘震荡
        change = np.random.normal(0, 0.5)  # 每天±0.5元波动
        current_price += change
        current_price = max(95, min(105, current_price))  # 限制在95-105之间
        prices.append(current_price)
    
    data = pd.Series(prices, index=dates)
    
    print(f"价格范围: {data.min():.2f} - {data.max():.2f}")
    print(f"价格变化: {((data.iloc[-1] - data.iloc[0]) / data.iloc[0] * 100):.2f}%")
    
    # 创建网格交易
    grid = GridTrading(base_price=100, grid_spacing=0.005)
    print(f"\n网格参数:")
    print(f"  网格间距: {grid.grid_spacing}")
    print(f"  网格层数: {grid.grid_levels}")
    print(f"  网格数量: {len(grid.grids)}")
    print(f"  网格价格: {grid.grids[:5]}...{grid.grids[-5:]}")
    
    # 运行交易
    trades = {'buy': 0, 'sell': 0, 'hold': 0}
    
    for i, price in enumerate(data):
        result = grid.update_price(price)
        trades[result['action']] += 1
        
        if result['action'] != 'hold' and trades[result['action']] <= 5:
            print(f"  {result['action']:4s} {result.get('quantity', 0):8.2f} @ {price:8.2f} 余额: {result['balance']:.2f}")
    
    # 结果
    perf = grid.get_performance()
    
    print(f"\n结果:")
    print(f"  总交易: {trades['buy'] + trades['sell']}")
    print(f"  买入: {trades['buy']}")
    print(f"  卖出: {trades['sell']}")
    print(f"  持仓: {trades['hold']}")
    print(f"  初始资金: {perf['initial_balance']:.2f}")
    print(f"  当前资金: {perf['current_balance']:.2f}")
    print(f"  最终仓位: {grid.position}")
    print(f"  收益率: {perf['return']:.2f}%")
    print("="*60)

if __name__ == "__main__":
    test_simple_grid()
