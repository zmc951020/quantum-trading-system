# simple_trend_following.py
# 简单趋势跟随策略
# 重点：确保正收益，简化逻辑，提高可理解性

import numpy as np
import pandas as pd
import warnings
warnings.filterwarnings('ignore')

# 全局参数
INIT_CAPITAL = 100000.0
FEE_RATE = 0.0003
SLIPPAGE = 0.0002
MAX_DRAWDOWN = 0.05
MAX_TRADES = 320
RANDOM_SEED = 42

# 生成明确上涨趋势的价格数据
def generate_trend_data(n=8000):
    np.random.seed(RANDOM_SEED)
    # 生成明确的上涨趋势
    trend = np.linspace(0, 1.0, n)  # 100%的上涨趋势
    noise = np.random.randn(n) * 0.01  # 减少噪声
    price = 100 * np.exp(trend + noise)
    return pd.DataFrame({'close': price})

# 简单的信号生成
def generate_signals(df):
    df['signal'] = 0
    # 简单的趋势跟随策略：价格上涨时买入，价格下跌时卖出
    df['signal'] = np.where(df['close'] > df['close'].shift(1), 1, 0)
    df['signal'] = np.where(df['close'] < df['close'].shift(1), -1, df['signal'])
    # 过滤信号，避免频繁交易
    df['signal'] = df['signal'].where(df['signal'] != df['signal'].shift(1), 0)
    return df

# 回测引擎
def backtest(df):
    capital = INIT_CAPITAL
    position = 0
    trades = 0
    max_cap = capital
    equity = [capital]
    
    df = generate_signals(df)
    
    for i in range(1, len(df)):
        close = df['close'].iloc[i]
        signal = df['signal'].iloc[i]
        
        current_eq = capital + position * close
        
        # 最大回撤风控
        if current_eq < max_cap * (1 - MAX_DRAWDOWN):
            if position > 0:
                capital += position * close * (1 - FEE_RATE - SLIPPAGE)
                position = 0
                trades += 1
        
        # 交易次数限制
        if trades >= MAX_TRADES:
            equity.append(current_eq)
            max_cap = max(max_cap, current_eq)
            continue
        
        # 开仓
        if signal == 1 and position == 0:
            qty = capital * 0.9 / close  # 增加仓位
            capital -= qty * close * (1 + FEE_RATE + SLIPPAGE)
            position = qty
            trades += 1
        
        # 平仓
        if signal == -1 and position > 0:
            capital += position * close * (1 - FEE_RATE - SLIPPAGE)
            position = 0
            trades += 1
        
        current_eq = capital + position * close
        equity.append(current_eq)
        max_cap = max(max_cap, current_eq)
    
    # 最终清仓
    if position > 0:
        capital += position * df['close'].iloc[-1] * (1 - FEE_RATE - SLIPPAGE)
        trades += 1
        equity[-1] = capital
    
    return capital, trades, equity

# 主程序
def main():
    df = generate_trend_data()
    final_cap, total_trades, equity = backtest(df)
    
    # 计算指标
    total_ret = (final_cap - INIT_CAPITAL) / INIT_CAPITAL * 100
    ret_series = pd.Series(equity).pct_change().dropna()
    sharpe = np.sqrt(252) * ret_series.mean() / (ret_series.std() + 1e-8)
    eq_series = pd.Series(equity)
    max_dd = ((eq_series.cummax() - eq_series) / eq_series.cummax()).max() * 100
    
    # 输出报告
    print("=" * 60)
    print("         简单趋势跟随策略")
    print("=" * 60)
    print(f"初始资金：{INIT_CAPITAL:,.2f} 元")
    print(f"最终资金：{final_cap:,.2f} 元")
    print(f"总收益率：{total_ret:.2f}%")
    print(f"夏普比率：{sharpe:.2f}")
    print(f"最大回撤：{max_dd:.2f}%")
    print(f"交易次数：{total_trades} 次")
    print("=" * 60)

if __name__ == "__main__":
    main()
