# -*- coding: utf-8 -*-
"""
测试最终优化策略的性能，分析各类型市场的收益率
"""

import pandas as pd
import numpy as np
import sys
import os

# 添加当前目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from final_optimized_strategy import FinalOptimizedStrategy

# 生成模拟数据
def generate_simulated_data(days=200):
    np.random.seed(42)
    dates = pd.date_range(start='2023-01-01', periods=days)
    
    # 生成基础价格走势
    base_trend = np.linspace(100, 120, days)  # 基础上涨趋势
    
    # 添加不同市场类型的波动
    volatility = np.zeros(days)
    
    # 横盘市场
    volatility[0:50] = 0.01
    
    # 上涨市场
    volatility[50:100] = 0.02
    base_trend[50:100] = np.linspace(105, 140, 50)
    
    # 下跌市场
    volatility[100:150] = 0.02
    base_trend[100:150] = np.linspace(140, 110, 50)
    
    # 波动市场
    volatility[150:200] = 0.04
    base_trend[150:200] = np.linspace(110, 130, 50)
    
    # 生成价格
    returns = np.random.normal(0, volatility, days)
    prices = base_trend * np.exp(np.cumsum(returns))
    
    # 生成成交量
    volumes = np.random.randint(1000000, 10000000, days)
    
    # 创建DataFrame
    df = pd.DataFrame({
        'close': prices,
        'volume': volumes
    }, index=dates)
    
    return df

# 测试策略
def test_strategy(strategy, data):
    """
    测试策略性能
    
    Args:
        strategy: 策略实例
        data: 价格数据
    
    Returns:
        测试结果
    """
    # 模拟交易
    market_type_stats = {
        'range_bound': {'balance': 100000, 'trades': 0, 'wins': 0},
        'trending_up': {'balance': 100000, 'trades': 0, 'wins': 0},
        'trending_down': {'balance': 100000, 'trades': 0, 'wins': 0},
        'volatile': {'balance': 100000, 'trades': 0, 'wins': 0}
    }
    
    # 记录每个市场类型的初始资金
    initial_balance = 100000
    
    # 模拟交易
    last_market_type = None
    for i in range(len(data)):
        current_price = data['close'].iloc[i]
        price_data = data['close'].iloc[max(0, i-30):i+1]
        
        # 记录交易前的状态
        prev_position = strategy.position
        prev_entry_price = strategy.entry_price
        
        # 更新价格并执行交易
        result = strategy.update_price(current_price, price_data)
        
        # 记录市场类型的表现
        market_type = strategy.market_type
        if market_type in market_type_stats:
            # 记录每个市场类型的交易次数
            if result['action'] in ['buy', 'sell']:
                market_type_stats[market_type]['trades'] += 1
                
                # 记录盈利交易
                if result['action'] == 'sell' and prev_position > 0:
                    # 计算是否为盈利交易
                    if current_price > prev_entry_price:
                        market_type_stats[market_type]['wins'] += 1
                        # 计算盈利金额
                        profit = (current_price - prev_entry_price) * prev_position
                        market_type_stats[market_type].setdefault('profit', 0)
                        market_type_stats[market_type]['profit'] += profit
                    else:
                        # 计算亏损金额
                        loss = (current_price - prev_entry_price) * prev_position
                        market_type_stats[market_type].setdefault('loss', 0)
                        market_type_stats[market_type]['loss'] += loss
    
    # 计算最终性能
    final_balance = strategy.current_balance
    total_return = (final_balance - initial_balance) / initial_balance
    total_trades = strategy.total_trades
    win_rate = strategy.winning_trades / total_trades if total_trades > 0 else 0
    
    # 计算各市场类型的收益率
    for market_type, stats in market_type_stats.items():
        # 计算卖出交易次数
        sell_trades = 0
        if 'wins' in stats:
            sell_trades += stats['wins']
        if 'loss' in stats:
            # 每次亏损交易算一次卖出
            sell_trades += 1
        
        if sell_trades > 0:
            # 计算胜率
            win_rate_type = stats.get('wins', 0) / sell_trades
            stats['win_rate'] = win_rate_type
            
            # 计算实际收益率
            total_profit = stats.get('profit', 0) + stats.get('loss', 0)
            # 假设每次交易的平均资金使用量为初始资金的10%
            avg_trade_amount = initial_balance * 0.1
            # 计算收益率
            if avg_trade_amount > 0:
                stats['actual_return'] = total_profit / avg_trade_amount
            else:
                stats['actual_return'] = 0
        else:
            stats['win_rate'] = 0
            stats['actual_return'] = 0
    
    return {
        'final_balance': final_balance,
        'total_return': total_return,
        'total_trades': total_trades,
        'win_rate': win_rate,
        'market_type_stats': market_type_stats,
        'final_position': strategy.position,
        'current_market_type': strategy.market_type
    }

if __name__ == "__main__":
    print("测试最终优化策略的性能")
    print("="*60)
    
    # 生成模拟数据
    print("生成模拟数据...")
    df = generate_simulated_data(days=200)
    print(f"生成了 {len(df)} 天的模拟数据")
    print(f"价格范围: {df.close.min():.2f} - {df.close.max():.2f}")
    print("="*60)
    
    # 初始化策略
    print("初始化最终优化策略...")
    base_price = df['close'].iloc[0]
    strategy = FinalOptimizedStrategy(base_price=base_price, initial_balance=100000)
    print("="*60)
    
    # 测试策略
    print("测试策略...")
    result = test_strategy(strategy, df)
    print("="*60)
    
    # 输出结果
    print("测试结果:")
    print(f"初始资金: 100000")
    print(f"最终资金: {result['final_balance']:.2f}")
    print(f"总收益率: {result['total_return']*100:.2f}%")
    print(f"总交易次数: {result['total_trades']}")
    print(f"胜率: {result['win_rate']*100:.2f}%")
    print(f"最终持仓: {result['final_position']:.2f}")
    print(f"当前市场类型: {result['current_market_type']}")
    print("="*60)
    
    # 输出各市场类型的表现
    print("各市场类型表现分析:")
    print(f"{'市场类型':<15} {'交易次数':>10} {'胜率':>8} {'实际收益率':>12}")
    print("-"*60)
    
    for market_type, stats in result['market_type_stats'].items():
        print(f"{market_type:<15} {stats['trades']:>10} {stats['win_rate']*100:>8.2f}% {stats['actual_return']*100:>12.2f}%")
    
    print("="*60)
    print("测试完成！")
