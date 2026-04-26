# -*- coding: utf-8 -*-
"""
测试金融级自适应深度学习混合策略
"""

import pandas as pd
import numpy as np
import sys
import os

# 添加策略目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strategies.financial_adaptive_strategy import FinancialAdaptiveStrategy

def generate_large_market_data(days=100, time_frame=5):
    """生成大规模混合市场数据
    
    Args:
        days: 天数
        time_frame: 时间周期（分钟）
        
    Returns:
        包含OHLCV数据的DataFrame
    """
    np.random.seed(42)
    # 生成分钟级数据
    minutes_per_day = 24 * 60 // time_frame
    total_minutes = days * minutes_per_day
    dates = pd.date_range(start='2023-01-01', periods=total_minutes, freq=f'{time_frame}min')
    
    # 基础价格
    base_price = 100.0
    prices = []
    
    # 市场阶段划分
    phases = [
        {"type": "NARROW_RANGE", "days": 25, "volatility": 0.2, "trend": 0},
        {"type": "STRONG_UP", "days": 25, "volatility": 0.15, "trend": 0.3},
        {"type": "STRONG_DOWN", "days": 25, "volatility": 0.15, "trend": -0.25},
        {"type": "PANIC", "days": 10, "volatility": 0.4, "trend": 0},
        {"type": "LOW_VOLATILITY", "days": 15, "volatility": 0.1, "trend": 0}
    ]
    
    current_price = base_price
    for phase in phases:
        phase_minutes = phase["days"] * minutes_per_day
        for i in range(phase_minutes):
            if phase["type"] in ["NARROW_RANGE", "LOW_VOLATILITY"]:
                # 横盘市场
                noise = np.random.normal(0, phase["volatility"])
                current_price += noise
            elif phase["type"] == "STRONG_UP":
                # 上涨市场
                trend = phase["trend"] / phase_minutes
                noise = np.random.normal(0, phase["volatility"])
                current_price *= (1 + trend)
                current_price += noise
            elif phase["type"] == "STRONG_DOWN":
                # 下跌市场
                trend = phase["trend"] / phase_minutes
                noise = np.random.normal(0, phase["volatility"])
                current_price *= (1 + trend)
                current_price += noise
            elif phase["type"] == "PANIC":
                # 高波动市场
                noise = np.random.normal(0, phase["volatility"])
                current_price += noise
            
            # 确保价格为正
            current_price = max(0.01, current_price)
            prices.append(current_price)
    
    # 生成成交量
    volumes = np.random.randint(1000000, 10000000, total_minutes)
    
    # 创建DataFrame
    df = pd.DataFrame({
        'open': prices,
        'high': [p * (1 + np.random.uniform(0, 0.002)) for p in prices],
        'low': [p * (1 - np.random.uniform(0, 0.002)) for p in prices],
        'close': prices,
        'volume': volumes
    }, index=dates)
    
    return df

def evaluate_strategy(strategy, df, initial_capital=100000):
    """评估策略表现
    
    Args:
        strategy: 策略对象
        df: 包含OHLCV数据的DataFrame
        initial_capital: 初始资金
        
    Returns:
        策略表现指标字典
    """
    capital = initial_capital
    position = 0
    position_cost = 0
    trades = 0
    wins = 0
    losses = 0
    equity_curve = []
    market_states = []
    
    print("开始测试...")
    print(f"数据总量: {len(df)} 根K线")
    print(f"测试周期: {len(df) // (24 * 60 // 5)} 天")
    
    for i in range(100, len(df)):
        # 每1000根K线打印一次进度
        if i % 1000 == 0:
            progress = (i / len(df)) * 100
            print(f"测试进度: {progress:.1f}%")
        
        window = df.iloc[i-100:i+1]
        market_type, current_capital = strategy.run(window)
        current_price = window.close.iloc[-1]
        
        # 记录市场状态
        market_states.append(market_type)
        
        # 记录资金曲线
        total_equity = current_capital + (strategy.pos * current_price if strategy.pos != 0 else 0)
        equity_curve.append(total_equity)
    
    # 计算指标
    final_capital = equity_curve[-1] if equity_curve else initial_capital
    total_return = (final_capital - initial_capital) / initial_capital
    win_rate = strategy.wins / (strategy.wins + strategy.losses) if (strategy.wins + strategy.losses) > 0 else 0
    
    # 计算夏普比率
    returns = np.diff(equity_curve) / equity_curve[:-1] if len(equity_curve) > 1 else []
    sharpe_ratio = np.mean(returns) / np.std(returns) * np.sqrt(252 * 24 * 60 / 5) if len(returns) > 0 and np.std(returns) > 0 else 0
    
    # 计算最大回撤
    peak = equity_curve[0] if equity_curve else initial_capital
    max_drawdown = 0
    for equity in equity_curve:
        if equity > peak:
            peak = equity
        drawdown = (peak - equity) / peak
        if drawdown > max_drawdown:
            max_drawdown = drawdown
    
    # 统计市场状态分布
    market_distribution = {}
    for state in market_states:
        if state not in market_distribution:
            market_distribution[state] = 0
        market_distribution[state] += 1
    
    return {
        'total_return': total_return,
        'win_rate': win_rate,
        'sharpe_ratio': sharpe_ratio,
        'max_drawdown': max_drawdown,
        'trades': strategy.trade_count,
        'final_capital': final_capital,
        'market_distribution': market_distribution
    }

def run_large_scale_test():
    """运行大规模测试"""
    print("测试金融级自适应深度学习混合策略")
    print("="*60)
    
    # 生成大规模混合市场数据
    print("生成大规模混合市场数据...")
    df = generate_large_market_data(days=100, time_frame=5)
    print(f"生成了 {len(df)} 根 5分钟K线数据")
    print(f"价格范围: {df.close.min():.2f} - {df.close.max():.2f}")
    print("="*60)
    
    # 初始化策略
    strategy = FinancialAdaptiveStrategy()
    
    # 评估策略
    print("评估策略表现...")
    result = evaluate_strategy(strategy, df)
    
    # 输出结果
    print("="*60)
    print("大规模测试结果:")
    print(f"策略名称: {strategy.name}")
    print(f"初始资金: 100000")
    print(f"最终资金: {result['final_capital']:.2f}")
    print(f"总收益率: {result['total_return']*100:.2f}%")
    print(f"总交易次数: {result['trades']}")
    print(f"胜率: {result['win_rate']*100:.2f}%")
    print(f"夏普比率: {result['sharpe_ratio']:.2f}")
    print(f"最大回撤: {result['max_drawdown']*100:.2f}%")
    print("\n市场状态分布:")
    for state, count in result['market_distribution'].items():
        print(f"{state}: {count}次 ({count/len(result['market_distribution'])*100:.1f}%)")
    print("="*60)
    print("测试完成！")

if __name__ == "__main__":
    run_large_scale_test()
