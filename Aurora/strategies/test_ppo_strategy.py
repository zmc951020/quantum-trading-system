#!/usr/bin/env python3
"""
测试DeepSeek优化后的PPO强化学习策略
"""

import sys
import os

# 添加策略目录到路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import pandas as pd
import datetime
from final_market_adaptive_rl_optimized_clean import FinalMarketAdaptiveGrid

def generate_minute_data(days=30, market_type='range_bound'):
    """
    生成分钟级测试数据
    """
    minutes_per_day = 390  # 6.5小时交易时间
    total_minutes = days * minutes_per_day
    
    # 时间索引
    start_time = datetime.datetime.now() - datetime.timedelta(days=days)
    timestamps = pd.date_range(start=start_time, periods=total_minutes, freq='T')
    
    # 生成价格数据
    np.random.seed(42)
    
    if market_type == 'range_bound':
        # 横盘市场：小幅波动
        base_price = 100
        returns = np.random.normal(0, 0.001, total_minutes)
        prices = base_price * np.cumprod(1 + returns)
    elif market_type == 'trending_up':
        # 上涨市场：趋势向上
        base_price = 100
        trend = np.linspace(0, 0.1, total_minutes)
        noise = np.random.normal(0, 0.0015, total_minutes)
        prices = base_price * np.cumprod(1 + trend/total_minutes + noise)
    elif market_type == 'trending_down':
        # 下跌市场：趋势向下
        base_price = 100
        trend = np.linspace(0, -0.1, total_minutes)
        noise = np.random.normal(0, 0.0015, total_minutes)
        prices = base_price * np.cumprod(1 + trend/total_minutes + noise)
    elif market_type == 'volatile':
        # 波动市场：高波动
        base_price = 100
        volatility = np.abs(np.random.normal(0.002, 0.001, total_minutes))
        directions = np.random.choice([-1, 1], total_minutes)
        returns = directions * volatility
        prices = base_price * np.cumprod(1 + returns)
    
    return pd.Series(prices, index=timestamps)

def test_strategy():
    """
    测试优化后的策略
    """
    print("=" * 80)
    print("DeepSeek PPO优化策略测试")
    print("=" * 80)
    
    market_types = ['range_bound', 'trending_up', 'trending_down', 'volatile']
    results = []
    
    for market_type in market_types:
        print(f"\n📊 测试市场类型: {market_type}")
        print("-" * 60)
        
        # 生成分钟级数据（30天）
        price_data = generate_minute_data(days=30, market_type=market_type)
        
        # 创建策略实例
        strategy = FinalMarketAdaptiveGrid(
            base_price=price_data.iloc[0],
            initial_balance=100000,
            enable_rl=True  # 启用强化学习
        )
        
        # 运行策略
        total_trades = 0
        for i, (timestamp, price) in enumerate(price_data.items()):
            action = strategy.update_price(price)
            if action in ['buy', 'sell']:
                total_trades += 1
        
        # 获取结果
        final_balance = strategy.current_balance
        total_return = (final_balance - strategy.initial_balance) / strategy.initial_balance
        
        # 计算夏普比率（简化计算）
        daily_returns = np.diff(strategy.balance_history) / strategy.balance_history[:-1]
        daily_returns = daily_returns.reshape(-1, 390).sum(axis=1) if len(daily_returns) >= 390 else daily_returns
        sharpe_ratio = np.mean(daily_returns) / np.std(daily_returns) * np.sqrt(252) if np.std(daily_returns) > 0 else 0
        
        # 计算最大回撤
        peak = np.maximum.accumulate(strategy.balance_history)
        drawdown = (peak - strategy.balance_history) / peak
        max_drawdown = np.max(drawdown)
        
        results.append({
            '市场类型': market_type,
            '最终余额': final_balance,
            '收益率': total_return,
            '夏普比率': sharpe_ratio,
            '最大回撤': max_drawdown,
            '交易次数': total_trades,
            '日均交易': total_trades / 30
        })
        
        print(f"最终余额: {final_balance:,.2f}")
        print(f"收益率: {total_return:.2%}")
        print(f"夏普比率: {sharpe_ratio:.2f}")
        print(f"最大回撤: {max_drawdown:.2%}")
        print(f"交易次数: {total_trades}")
        print(f"日均交易: {total_trades/30:.1f}")
    
    # 输出汇总表格
    print("\n" + "=" * 80)
    print("📈 测试结果汇总")
    print("=" * 80)
    
    df = pd.DataFrame(results)
    print(df.to_string(formatters={
        '最终余额': '{:,.0f}'.format,
        '收益率': '{:.2%}'.format,
        '夏普比率': '{:.2f}'.format,
        '最大回撤': '{:.2%}'.format,
        '日均交易': '{:.1f}'.format
    }))
    
    # 保存结果
    output_file = 'ppo_strategy_test_results.csv'
    df.to_csv(output_file, index=False, encoding='utf-8-sig')
    print(f"\n✓ 测试结果已保存到 {output_file}")

if __name__ == "__main__":
    test_strategy()