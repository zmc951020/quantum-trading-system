# -*- coding: utf-8 -*-
"""
测试分钟级自适应网格混合策略 - 终极优化版
"""

import pandas as pd
import numpy as np
import sys
import os

# 添加策略目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strategies.minute_adaptive_grid_v3 import MinuteAdaptiveGridStrategyV3

def generate_market_data(market_type="all", days=30, time_frame=5):
    """生成不同市场类型的模拟数据
    
    Args:
        market_type: 市场类型 (all/up/down/sideway/volatility)
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
    
    if market_type == "up":
        # 上涨市场
        for i in range(total_minutes):
            # 整体上涨趋势，波动较小
            trend = base_price * (1 + i / total_minutes * 0.3)  # 30%上涨
            noise = np.random.normal(0, 0.1)
            prices.append(trend + noise)
    elif market_type == "down":
        # 下跌市场
        for i in range(total_minutes):
            # 整体下跌趋势，波动较小
            trend = base_price * (1 - i / total_minutes * 0.3)  # 30%下跌
            noise = np.random.normal(0, 0.1)
            prices.append(trend + noise)
    elif market_type == "sideway":
        # 横盘市场
        for i in range(total_minutes):
            # 横盘震荡，波动较小
            noise = np.random.normal(0, 0.2)
            prices.append(base_price + noise)
    elif market_type == "volatility":
        # 高波动市场
        for i in range(total_minutes):
            # 高波动，无明显趋势
            noise = np.random.normal(0, 0.5)
            prices.append(base_price + noise)
    else:  # all
        # 混合市场
        segment_size = total_minutes // 4
        for i in range(total_minutes):
            if i < segment_size:
                # 横盘市场
                noise = np.random.normal(0, 0.2)
                prices.append(base_price + noise)
            elif i < 2 * segment_size:
                # 上涨市场
                trend = base_price * (1 + (i - segment_size) / segment_size * 0.2)
                noise = np.random.normal(0, 0.15)
                prices.append(trend + noise)
            elif i < 3 * segment_size:
                # 下跌市场
                trend = base_price * (1 + 0.2 - (i - 2 * segment_size) / segment_size * 0.25)
                noise = np.random.normal(0, 0.15)
                prices.append(trend + noise)
            else:
                # 高波动市场
                noise = np.random.normal(0, 0.4)
                prices.append(base_price * 0.95 + noise)
    
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
    equity_curve = []
    
    for i in range(60, len(df)):
        window = df.iloc[i-60:i+1]
        signal = strategy.get_signal(window, position, capital)
        current_price = window.close.iloc[-1]
        
        # 计算目标仓位
        target_pos = strategy.get_position_size(capital, current_price)
        
        # 执行交易
        if signal == 1 and position < target_pos:
            # 买入/平空
            buy_vol = target_pos - position
            if buy_vol > 0:
                capital -= buy_vol * current_price
                position += buy_vol
                position_cost = current_price
                trades += 1
        elif signal == -1 and position > target_pos:
            # 卖出/做空
            sell_vol = position - target_pos
            if sell_vol > 0:
                profit = (current_price - position_cost) * sell_vol
                if profit > 0:
                    wins += 1
                capital += sell_vol * current_price
                position -= sell_vol
                trades += 1
        
        # 记录资金曲线
        total_equity = capital + (position * current_price if position != 0 else 0)
        equity_curve.append(total_equity)
    
    # 计算指标
    final_capital = equity_curve[-1] if equity_curve else initial_capital
    total_return = (final_capital - initial_capital) / initial_capital
    win_rate = wins / trades if trades > 0 else 0
    
    # 计算夏普比率
    returns = np.diff(equity_curve) / equity_curve[:-1] if len(equity_curve) > 1 else []
    sharpe_ratio = np.mean(returns) / np.std(returns) * np.sqrt(252 * 24 * 60 / 5) if len(returns) > 0 else 0
    
    # 计算最大回撤
    peak = equity_curve[0] if equity_curve else initial_capital
    max_drawdown = 0
    for equity in equity_curve:
        if equity > peak:
            peak = equity
        drawdown = (peak - equity) / peak
        if drawdown > max_drawdown:
            max_drawdown = drawdown
    
    return {
        'total_return': total_return,
        'win_rate': win_rate,
        'sharpe_ratio': sharpe_ratio,
        'max_drawdown': max_drawdown,
        'trades': trades,
        'final_capital': final_capital
    }

def test_all_markets():
    """测试策略在所有市场类型中的表现"""
    print("测试分钟级自适应网格混合策略 - 终极优化版")
    print("="*60)
    
    # 测试不同市场类型
    market_types = ["all", "up", "down", "sideway", "volatility"]
    results = []
    
    for market_type in market_types:
        print(f"测试 {market_type} 市场...")
        
        # 生成市场数据
        df = generate_market_data(market_type=market_type, days=20, time_frame=5)
        print(f"生成了 {len(df)} 根 5分钟K线数据")
        print(f"价格范围: {df.close.min():.2f} - {df.close.max():.2f}")
        
        # 初始化策略
        strategy = MinuteAdaptiveGridStrategyV3(time_frame=5)
        
        # 评估策略
        result = evaluate_strategy(strategy, df)
        results.append((market_type, result))
        
        print(f"总收益率: {result['total_return']*100:.2f}%")
        print(f"胜率: {result['win_rate']*100:.2f}%")
        print(f"夏普比率: {result['sharpe_ratio']:.2f}")
        print(f"最大回撤: {result['max_drawdown']*100:.2f}%")
        print(f"总交易次数: {result['trades']}")
        print(f"最终资金: {result['final_capital']:.2f}")
        print("="*60)
    
    # 输出总结
    print("策略性能总结")
    print("="*60)
    print(f"{'市场类型':<12} {'总收益率':>10} {'胜率':>8} {'夏普比率':>10} {'最大回撤':>10} {'交易次数':>10}")
    print("-"*60)
    
    for market_type, result in results:
        print(f"{market_type:<12} {result['total_return']*100:>10.2f}% {result['win_rate']*100:>8.2f}% {result['sharpe_ratio']:>10.2f} {result['max_drawdown']*100:>10.2f}% {result['trades']:>10}")
    
    print("="*60)
    print("测试完成！")

if __name__ == "__main__":
    test_all_markets()
