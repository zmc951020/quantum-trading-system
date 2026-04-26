#!/usr/bin/env python3
"""
网格交易收益测试
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

def generate_market_data(length: int, market_type: str = 'range_bound', start_price: float = 100):
    """
    生成不同类型的市场数据
    
    Args:
        length: 数据长度
        market_type: 市场类型: 'range_bound', 'trending_up', 'trending_down', 'volatile'
        start_price: 起始价格
        
    Returns:
        价格数据
    """
    dates = pd.date_range(start=datetime.now() - timedelta(days=length), periods=length, freq='D')
    
    if market_type == 'range_bound':
        # 横盘震荡市场
        trend = np.linspace(0, 0.05, length)  # 5%的长期趋势
        cycle = 0.04 * np.sin(np.linspace(0, 20 * np.pi, length))  # 周期性波动
        random_noise = np.random.normal(0, 0.01, length)
        returns = trend + cycle + random_noise
        prices = start_price * (1 + returns).cumprod()
        prices = np.clip(prices, start_price * 0.95, start_price * 1.05)  # 限制在±5%范围内
    
    elif market_type == 'trending_up':
        # 上涨趋势市场
        trend = np.linspace(0, 0.3, length)  # 30%的趋势
        random_noise = np.random.normal(0, 0.01, length)
        returns = trend + random_noise
        prices = start_price * (1 + returns).cumprod()
    
    elif market_type == 'trending_down':
        # 下跌趋势市场
        trend = np.linspace(0, -0.2, length)  # -20%的趋势
        random_noise = np.random.normal(0, 0.01, length)
        returns = trend + random_noise
        prices = start_price * (1 + returns).cumprod()
    
    elif market_type == 'volatile':
        # 高波动市场
        trend = np.linspace(0, 0.1, length)  # 10%的长期趋势
        cycle = 0.06 * np.sin(np.linspace(0, 30 * np.pi, length))  # 大周期波动
        random_noise = np.random.normal(0, 0.015, length)  # 更大的随机波动
        returns = trend + cycle + random_noise
        prices = start_price * (1 + returns).cumprod()
    
    else:
        # 默认为横盘震荡
        trend = np.linspace(0, 0.05, length)
        cycle = 0.04 * np.sin(np.linspace(0, 20 * np.pi, length))
        random_noise = np.random.normal(0, 0.01, length)
        returns = trend + cycle + random_noise
        prices = start_price * (1 + returns).cumprod()
        prices = np.clip(prices, start_price * 0.95, start_price * 1.05)
    
    return pd.Series(prices, index=dates)

def test_grid_trading(market_type: str, initial_balance: float = 100000):
    """
    测试网格交易在不同市场环境下的表现
    
    Args:
        market_type: 市场类型
        initial_balance: 初始资金
        
    Returns:
        测试结果
    """
    print(f"\n" + "="*60)
    print(f"测试: {market_type} 市场")
    print("="*60)
    
    # 生成市场数据
    data = generate_market_data(length=365, market_type=market_type)
    print(f"价格范围: {data.min():.2f} - {data.max():.2f}")
    print(f"价格变化: {((data.iloc[-1] - data.iloc[0]) / data.iloc[0] * 100):.2f}%")
    
    # 创建网格交易策略
    grid = GridTrading(
        base_price=data.iloc[0], 
        grid_spacing=0.005,  # 0.5%网格间距
        initial_balance=initial_balance
    )
    
    # 运行交易
    trades = {'buy': 0, 'sell': 0, 'hold': 0}
    buy_prices = []
    sell_prices = []
    
    for i, price in enumerate(data):
        # 每20个数据点提供一次市场数据用于检测
        if i >= 20:
            current_data = data.iloc[:i+1]
            result = grid.update_price(price, current_data)
        else:
            result = grid.update_price(price)
        
        trades[result['action']] += 1
        
        if result['action'] == 'buy':
            buy_prices.append(price)
            if trades['buy'] <= 3:
                print(f"  买入: {result['quantity']:.2f} @ {price:.2f} 余额: {result['balance']:.2f}")
        elif result['action'] == 'sell':
            sell_prices.append(price)
            if trades['sell'] <= 3:
                print(f"  卖出: {result['quantity']:.2f} @ {price:.2f} 余额: {result['balance']:.2f}")
    
    # 获取性能
    perf = grid.get_performance()
    
    # 计算交易统计
    avg_buy_price = np.mean(buy_prices) if buy_prices else 0
    avg_sell_price = np.mean(sell_prices) if sell_prices else 0
    win_rate = len([p for p in sell_prices if p > avg_buy_price]) / len(sell_prices) if sell_prices else 0
    
    # 打印结果
    print(f"\n结果:")
    print(f"  总交易: {trades['buy'] + trades['sell']}")
    print(f"  买入: {trades['buy']}")
    print(f"  卖出: {trades['sell']}")
    print(f"  持仓: {trades['hold']}")
    print(f"  初始资金: {perf['initial_balance']:.2f}")
    print(f"  当前资金: {perf['current_balance']:.2f}")
    print(f"  最终仓位: {grid.position:.2f}")
    print(f"  收益率: {perf['return']:.2f}%")
    
    if buy_prices and sell_prices:
        print(f"  平均买入价格: {avg_buy_price:.2f}")
        print(f"  平均卖出价格: {avg_sell_price:.2f}")
        print(f"  胜率: {win_rate:.2%}")
    
    print("="*60)
    
    return {
        'market_type': market_type,
        'initial_balance': initial_balance,
        'final_balance': perf['current_balance'],
        'return_rate': perf['return'],
        'total_trades': trades['buy'] + trades['sell'],
        'buy_trades': trades['buy'],
        'sell_trades': trades['sell'],
        'position': grid.position,
        'avg_buy_price': avg_buy_price,
        'avg_sell_price': avg_sell_price,
        'win_rate': win_rate
    }

def main():
    """
    主函数
    """
    print("="*60)
    print("网格交易收益测试")
    print("="*60)
    print("测试不同市场环境下的网格交易表现")
    print("="*60)
    
    # 测试不同市场类型
    market_types = ['range_bound', 'trending_up', 'trending_down', 'volatile']
    results = []
    
    for market_type in market_types:
        result = test_grid_trading(market_type)
        results.append(result)
    
    # 打印综合结果
    print("\n" + "="*60)
    print("综合测试结果")
    print("="*60)
    
    for result in results:
        print(f"{result['market_type']:15s} 收益率: {result['return_rate']:8.2f}% 交易次数: {result['total_trades']:5d} 胜率: {result['win_rate']:5.2%}")
    
    # 计算平均收益率
    avg_return = np.mean([r['return_rate'] for r in results])
    print(f"\n平均收益率: {avg_return:.2f}%")
    
    print("\n" + "="*60)
    print("网格交易收益测试完成！")
    print("="*60)

if __name__ == "__main__":
    main()
