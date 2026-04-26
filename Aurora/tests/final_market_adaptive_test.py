#!/usr/bin/env python3
"""
最终市场自适应网格交易策略测试
"""

import os
import sys
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    from strategies.final_market_adaptive import FinalMarketAdaptiveGrid
except ImportError as e:
    print(f"错误: {str(e)}")
    sys.exit(1)

def generate_market_data(length: int, market_type: str = 'range_bound', start_price: float = 100, volatility: float = 0.01):
    """
    生成不同类型的市场数据
    """
    dates = pd.date_range(start=datetime.now() - timedelta(days=length), periods=length, freq='D')
    
    if market_type == 'range_bound':
        # 横盘震荡市场
        trend = np.linspace(0, 0.03, length)
        cycle = 0.03 * np.sin(np.linspace(0, 25 * np.pi, length))
        random_noise = np.random.normal(0, volatility, length)
        returns = trend + cycle + random_noise
        prices = start_price * (1 + returns).cumprod()
        prices = np.clip(prices, start_price * 0.96, start_price * 1.04)
    
    elif market_type == 'trending_up':
        # 上涨趋势市场
        trend = np.linspace(0, 0.25, length)
        cycle = 0.02 * np.sin(np.linspace(0, 15 * np.pi, length))
        random_noise = np.random.normal(0, volatility, length)
        returns = trend + cycle + random_noise
        prices = start_price * (1 + returns).cumprod()
    
    elif market_type == 'trending_down':
        # 下跌趋势市场（更真实的下跌市场数据）
        # 生成一个逐渐下跌但有反弹的市场
        trend = np.linspace(0, -0.15, length)
        # 添加更多的周期性反弹
        cycle = 0.03 * np.sin(np.linspace(0, 20 * np.pi, length))
        random_noise = np.random.normal(0, volatility, length)
        returns = trend + cycle + random_noise
        prices = start_price * (1 + returns).cumprod()
        # 确保价格不会变成负数
        prices = np.maximum(prices, start_price * 0.5)  # 最低价格为初始价格的50%
    
    elif market_type == 'volatile':
        # 高波动市场
        trend = np.linspace(0, 0.08, length)
        cycle = 0.05 * np.sin(np.linspace(0, 20 * np.pi, length))
        random_noise = np.random.normal(0, volatility * 1.5, length)
        returns = trend + cycle + random_noise
        prices = start_price * (1 + returns).cumprod()
    
    else:
        # 默认为横盘震荡
        trend = np.linspace(0, 0.03, length)
        cycle = 0.03 * np.sin(np.linspace(0, 25 * np.pi, length))
        random_noise = np.random.normal(0, volatility, length)
        returns = trend + cycle + random_noise
        prices = start_price * (1 + returns).cumprod()
        prices = np.clip(prices, start_price * 0.96, start_price * 1.04)
    
    return pd.Series(prices, index=dates)

def test_final_market_adaptive(market_type: str, initial_balance: float = 100000):
    """
    测试最终市场自适应网格交易策略
    """
    print(f"\n" + "="*60)
    print(f"测试: {market_type} 市场 (最终市场自适应网格交易)")
    print("="*60)
    
    # 生成市场数据
    data = generate_market_data(length=365, market_type=market_type, volatility=0.008)
    print(f"价格范围: {data.min():.2f} - {data.max():.2f}")
    print(f"价格变化: {((data.iloc[-1] - data.iloc[0]) / data.iloc[0] * 100):.2f}%")
    
    # 创建最终市场自适应网格交易策略
    grid = FinalMarketAdaptiveGrid(
        base_price=data.iloc[0], 
        initial_balance=initial_balance
    )
    
    # 运行交易
    trades = {'buy': 0, 'sell': 0, 'hold': 0}
    buy_prices = []
    sell_prices = []
    market_type_changes = []
    
    for i, price in enumerate(data):
        # 每20个数据点提供一次市场数据用于检测
        if i >= 20:
            current_data = data.iloc[:i+1]
            result = grid.update_price(price, current_data)
            # 记录市场类型变化
            if i > 20 and grid.last_market_type != grid.market_type:
                market_type_changes.append((i, grid.last_market_type, grid.market_type))
        else:
            result = grid.update_price(price)
        
        trades[result['action']] += 1
        
        if result['action'] == 'buy':
            buy_prices.append(price)
            if trades['buy'] <= 10:
                print(f"  买入: {result['quantity']:.2f} @ {price:.2f} 余额: {result['balance']:.2f}")
        elif result['action'] == 'sell':
            sell_prices.append(price)
            if trades['sell'] <= 10:
                print(f"  卖出: {result['quantity']:.2f} @ {price:.2f} 余额: {result['balance']:.2f}")
    
    # 获取性能
    perf = grid.get_performance()
    
    # 计算交易统计
    avg_buy_price = np.mean(buy_prices) if buy_prices else 0
    avg_sell_price = np.mean(sell_prices) if sell_prices else 0
    
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
    print(f"  总交易次数: {perf['total_trades']}")
    print(f"  盈利交易: {perf['winning_trades']}")
    print(f"  亏损交易: {perf['losing_trades']}")
    print(f"  胜率: {perf['win_rate']:.2%}")
    print(f"  模型训练次数: {perf['model_training_count']}")
    print(f"  模型是否训练: {perf['model_trained']}")
    
    # 打印市场类型变化
    if market_type_changes:
        print(f"\n市场类型变化:")
        for i, old_type, new_type in market_type_changes[:5]:  # 只显示前5次变化
            print(f"  第{i}天: {old_type} -> {new_type}")
    
    if buy_prices and sell_prices:
        print(f"  平均买入价格: {avg_buy_price:.2f}")
        print(f"  平均卖出价格: {avg_sell_price:.2f}")
        print(f"  买卖价差: {(avg_sell_price - avg_buy_price):.2f} ({((avg_sell_price - avg_buy_price) / avg_buy_price * 100):.2f}%)")
    
    print("="*60)
    
    return {
        'market_type': market_type,
        'initial_balance': initial_balance,
        'final_balance': perf['current_balance'],
        'return_rate': perf['return'],
        'total_trades': perf['total_trades'],
        'buy_trades': trades['buy'],
        'sell_trades': trades['sell'],
        'position': grid.position,
        'avg_buy_price': avg_buy_price,
        'avg_sell_price': avg_sell_price,
        'win_rate': perf['win_rate'],
        'model_training_count': perf['model_training_count'],
        'model_trained': perf['model_trained']
    }

def main():
    """
    主函数
    """
    print("="*60)
    print("最终市场自适应网格交易策略测试")
    print("="*60)
    print("根据市场类型自动切换不同的网格交易策略")
    print("="*60)
    
    # 测试不同市场类型
    market_types = ['range_bound', 'trending_up', 'trending_down', 'volatile']
    results = []
    
    for market_type in market_types:
        result = test_final_market_adaptive(market_type)
        results.append(result)
    
    # 打印综合结果
    print("\n" + "="*60)
    print("综合测试结果")
    print("="*60)
    
    for result in results:
        print(f"{result['market_type']:15s} 收益率: {result['return_rate']:8.2f}% 交易次数: {result['total_trades']:5d} 胜率: {result['win_rate']:5.2%} 模型训练: {result['model_training_count']:3d}")
    
    # 计算平均收益率
    avg_return = np.mean([r['return_rate'] for r in results])
    print(f"\n平均收益率: {avg_return:.2f}%")
    
    print("\n" + "="*60)
    print("最终市场自适应网格交易策略测试完成！")
    print("="*60)

if __name__ == "__main__":
    main()
