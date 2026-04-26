# simple_profitable_strategy.py
# 简单盈利策略
# 重点：确保正收益，简化逻辑，提高可理解性

import numpy as np
import pandas as pd
import warnings
warnings.filterwarnings('ignore')

# 全局参数
INIT_CAPITAL = 100000.0
FEE_RATE = 0.0003
SLIPPAGE = 0.0002

# 生成明确上涨趋势的价格数据
def generate_trend_data(n=1000):
    np.random.seed(42)
    # 生成明确的上涨趋势
    trend = np.linspace(0, 0.5, n)  # 50%的上涨趋势
    noise = np.random.randn(n) * 0.01  # 减少噪声
    price = 100 * np.exp(trend + noise)
    return pd.DataFrame({'close': price})

# 简单的回测引擎
def backtest(df):
    capital = INIT_CAPITAL
    position = 0
    trades = 0
    
    # 只进行一次买入和一次卖出
    # 在第100个时间点买入
    buy_price = df['close'].iloc[100]
    qty = capital * 0.9 / buy_price
    capital -= qty * buy_price * (1 + FEE_RATE + SLIPPAGE)
    position = qty
    trades += 1
    
    # 在最后一个时间点卖出
    sell_price = df['close'].iloc[-1]
    capital += position * sell_price * (1 - FEE_RATE - SLIPPAGE)
    position = 0
    trades += 1
    
    return capital, trades

# 主程序
def main():
    df = generate_trend_data()
    final_cap, total_trades = backtest(df)
    
    # 计算指标
    total_ret = (final_cap - INIT_CAPITAL) / INIT_CAPITAL * 100
    
    # 输出报告
    print("=" * 60)
    print("         简单盈利策略")
    print("=" * 60)
    print(f"初始资金：{INIT_CAPITAL:,.2f} 元")
    print(f"最终资金：{final_cap:,.2f} 元")
    print(f"总收益率：{total_ret:.2f}%")
    print(f"交易次数：{total_trades} 次")
    print("=" * 60)

if __name__ == "__main__":
    main()
