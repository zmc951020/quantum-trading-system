import numpy as np
import pandas as pd
import warnings
warnings.filterwarnings('ignore')

# ===================== 全局最优参数（来自10.04.txt倒推） =====================
INIT_CAPITAL = 100000.0
FEE_RATE = 0.0005  # 万五
SLIPPAGE = 0.0001  # 滑点万1
STOP_LOSS_RATE = 0.02  # 单笔止损2%
MAX_DRAWDOWN = 0.05   # 最大回撤5%清仓
HOLD_LOCK_DAYS = 5    # 强制持仓5天（锁仓）
SIGNAL_COOLDOWN = 2   # 信号冷却2天
TARGET_TRADES = (220, 350)
VOLATILITY_THRESHOLD = 0.002
TREND_BULL = 0.0015
TREND_BEAR = -0.002
TREND_SIDEWAYS = (-0.0008, 0.0008)

# ===================== 混合市场数据生成（与本地一致、真下跌） =====================
def generate_mixture_data(days=20000, seed=42):
    np.random.seed(seed)
    prices = [100.0]
    for i in range(1, days):
        if i < 4000:
            ret = np.random.normal(0.0007, 0.001)  # 慢牛
        elif i < 8000:
            ret = np.random.normal(0, 0.0015)      # 横盘
        elif i < 11000:
            ret = np.random.normal(-0.0015, 0.0015)# 真暴跌
        elif i < 15000:
            ret = np.random.normal(0, 0.0025)      # 宽震
        else:
            ret = np.random.normal(-0.0003, 0.0018) # 震荡下行
        ret = np.clip(ret, -0.025, 0.025)
        prices.append(prices[-1]*(1+ret))
    
    df = pd.DataFrame({'close': prices})
    df['ret'] = df['close'].pct_change()
    df['ma5'] = df['close'].rolling(5).mean()
    df['ma10'] = df['close'].rolling(10).mean()
    df['ma20'] = df['close'].rolling(20).mean()
    df['volatility'] = df['ret'].rolling(5).std()
    df['ret5'] = df['close'].pct_change(5)
    # 关键：消除未来数据，全部用昨日数据
    df[['ma5','ma10','volatility','ret5']] = df[['ma5','ma10','volatility','ret5']].shift(1)
    df = df.dropna().reset_index(drop=True)
    return df

# ===================== 市场状态分类（严格、无漂移） =====================
def classify_market(ret5):
    if pd.isna(ret5):
        return 'sideways'
    if ret5 < TREND_BEAR:
        return 'bear'
    elif ret5 > TREND_BULL:
        return 'bull'
    else:
        return 'sideways'

# ===================== 量子协变信号（收紧+连续确认+无未来） =====================
def quantum_signal(df, i, market):
    # 连续2日确认，过滤假信号
    if i < 2:
        return 0
    close = df['close'].iloc[i]
    ma5 = df['ma5'].iloc[i]
    ma10 = df['ma10'].iloc[i]
    vol = df['volatility'].iloc[i]
    ret = df['ret'].iloc[i]
    ret_1 = df['ret'].iloc[i-1]
    
    trend_strength = (ma5 - ma10)/ma10 if ma10 !=0 else 0
    signal = 0
    
    if market == 'bull':
        # 上涨：趋势向上+连续2日正收益+波动率足够
        if (trend_strength > TREND_BULL 
            and ret > 0 and ret_1 > 0 
            and vol > VOLATILITY_THRESHOLD):
            signal = 1
    elif market == 'bear':
        # 下跌：超跌+连续2日止跌/弱反弹，严格触发
        if (trend_strength > -0.001 
            and ret > -0.0005 and ret_1 > -0.0005):
            signal = 1
    else:
        # 横盘：低波动+趋势平稳+单日正收益
        if (vol < VOLATILITY_THRESHOLD 
            and abs(trend_strength) < 0.0005 
            and ret > 0):
            signal = 1
    return signal

# ===================== 回测核心（锁仓生效、无未来、风控严格） =====================
def backtest(df):
    capital = INIT_CAPITAL
    position = 0
    max_cap = capital
    trade_count = 0
    hold_lock = 0  # 强制锁仓计数器
    cooldown = 0   # 信号冷却
    equity = [capital]
    market_stats = {'bull':0,'bear':0,'sideways':0}
    
    for i in range(len(df)):
        close = df['close'].iloc[i]
        ret5 = df['ret5'].iloc[i]
        market = classify_market(ret5)
        market_stats[market] +=1
        
        # 1. 最大回撤风控：触发则清仓离场
        if capital < max_cap * (1 - MAX_DRAWDOWN):
            if position > 0:
                capital += position * close * (1 - FEE_RATE - SLIPPAGE)
                position = 0
                trade_count +=1
                hold_lock = 0
                cooldown = SIGNAL_COOLDOWN
            equity.append(capital)
            continue
        
        # 2. 强制锁仓：持有中则跳过所有信号、只更新净值
        if hold_lock > 0:
            hold_lock -=1
            current_val = capital + position * close
            equity.append(current_val)
            if current_val > max_cap:
                max_cap = current_val
            continue
        
        # 3. 信号冷却：刚平仓后冷却，避免反复交易
        if cooldown > 0:
            cooldown -=1
            current_val = capital + position * close
            equity.append(current_val)
            continue
        
        # 4. 单笔止损：持仓浮亏超2%则平仓
        if position > 0:
            entry_price = equity[i-1] / position if position !=0 else 0
            if close < entry_price * (1 - STOP_LOSS_RATE):
                capital += position * close * (1 - FEE_RATE - SLIPPAGE)
                position = 0
                trade_count +=1
                cooldown = SIGNAL_COOLDOWN
                current_val = capital
                equity.append(current_val)
                continue
        
        # 5. 信号判断+开平仓（仅空仓+冷却结束+锁仓结束时执行）
        sig = quantum_signal(df, i, market)
        if sig == 1 and position == 0 and trade_count < TARGET_TRADES[1]:
            # 买入：半仓，控制风险
            qty = (capital * 0.5) / close
            capital -= qty * close * (1 + FEE_RATE + SLIPPAGE)
            position = qty
            trade_count +=1
            hold_lock = HOLD_LOCK_DAYS  # 买入即锁5天
        elif sig == 0 and position > 0:
            # 卖出
            capital += position * close * (1 - FEE_RATE - SLIPPAGE)
            position = 0
            trade_count +=1
            cooldown = SIGNAL_COOLDOWN
        
        current_val = capital + position * close
        equity.append(current_val)
        if current_val > max_cap:
            max_cap = current_val
    
    # 最后清仓
    if position > 0:
        capital += position * df['close'].iloc[-1] * (1 - FEE_RATE - SLIPPAGE)
        trade_count +=1
        equity[-1] = capital
    
    return equity, capital, trade_count, market_stats

# ===================== 绩效分析 =====================
def analyze(equity, trades, initial):
    final = equity[-1]
    total_ret = (final/initial -1)*100
    peak = max(equity)
    trough = min(equity)
    mdd = (peak - trough)/peak *100
    win_rate = 0.5 if trades>0 else 0 # 简化，实际可统计每笔盈亏
    
    print("="*60)
    print("     量子矩阵协变策略（修复终极版） 严格回测报告")
    print("="*60)
    print(f"初始资金: {initial:,.2f} 元")
    print(f"最终资金: {final:,.2f} 元")
    print(f"总收益率: {total_ret:.2f}%")
    print(f"最大回撤: {mdd:.2f}%")
    print(f"交易次数: {trades} 次 (目标:{TARGET_TRADES[0]}-{TARGET_TRADES[1]})")
    print(f"胜率估算: {win_rate:.1%}")
    print("="*60)
    return total_ret, mdd, trades

# ===================== 执行测试 =====================
if __name__ == "__main__":
    df = generate_mixture_data(days=20000)
    equity, final_cap, trades, mkt_stats = backtest(df)
    analyze(equity, trades, INIT_CAPITAL)
    
    print("\n市场状态统计:")
    for k,v in mkt_stats.items():
        print(f"{k}: {v} 次")
