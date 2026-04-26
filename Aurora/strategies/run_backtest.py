# -*- coding: utf-8 -*-
"""
非交互式回测脚本，用于测试进阶版机器学习自适应策略的收益率
"""

import pandas as pd
import numpy as np
from sklearn.ensemble import GradientBoostingClassifier
import ta
import sys

# ====================== 配置项 ======================
STOCK_CODE = "600036.SH"
LOOKBACK_WINDOW = 30
PREDICT_WINDOW = 3
STOP_LOSS_GLOBAL = 0.08
# ====================================================

# 全局模型
model = None
market_type_map = {0: "range", 1: "up", 2: "down", 3: "volatile"}

# 最优策略参数
STRATEGY_PARAMS = {
    "range": {"step": 0.015, "vol": 50},
    "up": {"step": 0.03, "vol": 100},
    "down": {"step": 0.02, "vol": 50},
    "volatile": {"step": 0.04, "vol": 50}
}

def extract_advanced_features(prices, volumes):
    """高级特征提取：包含技术指标"""
    df = pd.DataFrame()
    df['close'] = prices
    df['volume'] = volumes if volumes is not None else np.ones_like(prices)
    
    # 基础特征
    returns = np.diff(prices) / prices[:-1]
    volatility = np.std(returns)
    trend = (prices[-1] - prices[0]) / prices[0]
    range_pct = (max(prices) - min(prices)) / prices[0]
    
    # 技术指标
    rsi = ta.momentum.rsi(df['close'], window=14).iloc[-1]
    atr = ta.volatility.average_true_range(df['close'], df['close'], df['close'], window=14).iloc[-1]
    macd = ta.trend.macd(df['close']).iloc[-1]
    boll_width = (ta.volatility.bollinger_hband(df['close']) - ta.volatility.bollinger_lband(df['close'])).iloc[-1] / df['close'].iloc[-1]
    
    # 确保所有特征都是数值类型
    features = np.array([
        volatility, trend, range_pct, np.mean(returns),
        rsi, atr, macd, boll_width
    ])
    
    # 处理可能的NaN值
    features = np.nan_to_num(features, nan=0.0)
    
    return features.reshape(1, -1)

def train_market_model(historical_data):
    """训练市场类型分类模型"""
    global model
    X = []
    y = []
    
    # 标注历史数据
    for i in range(LOOKBACK_WINDOW, len(historical_data)-PREDICT_WINDOW):
        window = historical_data[i-LOOKBACK_WINDOW:i]
        prices = window['close'].values
        
        # 标注未来市场类型
        future = historical_data[i:i+PREDICT_WINDOW]
        f_prices = future['close'].values
        f_returns = np.diff(f_prices) / f_prices[:-1]
        f_vol = np.std(f_returns)
        f_trend = (f_prices[-1] - f_prices[0]) / f_prices[0]
        
        if f_vol > 0.03:
            label = 3  # volatile
        elif f_trend > 0.02:
            label = 1  # up
        elif f_trend < -0.02:
            label = 2  # down
        else:
            label = 0  # range
        
        features = extract_advanced_features(prices, window['volume'].values)[0]
        X.append(features)
        y.append(label)
    
    # 训练GBDT模型
    model = GradientBoostingClassifier(
        n_estimators=100, learning_rate=0.1, max_depth=3
    )
    model.fit(X, y)
    print("市场预判模型训练完成，准确率:", model.score(X, y))
    return model

def predict_market_type(prices, volumes):
    """预判未来市场类型"""
    if model is None:
        #  fallback 规则
        returns = np.diff(prices) / prices[:-1]
        vol = np.std(returns)
        trend = (prices[-1] - prices[0]) / prices[0]
        if vol > 0.03:
            return "volatile"
        elif trend > 0.02:
            return "up"
        elif trend < -0.02:
            return "down"
        else:
            return "range"
    
    features = extract_advanced_features(prices, volumes)
    pred = model.predict(features)[0]
    return market_type_map[pred]

def backtest_strategy(historical_data):
    """回测验证策略表现"""
    print("="*50)
    print("开始回测验证...")
    print("="*50)
    
    capital = 100000
    position = 0
    position_cost = 0
    base_price = 0
    trades = 0
    wins = 0
    
    # 训练模型
    train_market_model(historical_data)
    
    prices = []
    volumes = []
    
    for idx, row in historical_data.iterrows():
        current_price = row['close']
        current_vol = row['volume']
        
        prices.append(current_price)
        volumes.append(current_vol)
        
        if len(prices) < LOOKBACK_WINDOW:
            continue
        
        # 预判市场
        market_type = predict_market_type(prices, volumes)
        params = STRATEGY_PARAMS[market_type]
        step, vol_size = params['step'], params['vol']
        
        # 更新基准价
        if base_price == 0:
            base_price = current_price
        
        # 止盈止损
        if position > 0:
            loss_rate = (position_cost - current_price) / position_cost
            if loss_rate >= STOP_LOSS_GLOBAL:
                # 止损
                capital += position * current_price
                position = 0
                trades += 1
                base_price = current_price
                continue
        
        # 策略执行
        if position == 0 and current_price <= base_price * (1 - step):
            # 买入
            buy_vol = min(vol_size, int(capital / current_price / 100) * 100)
            if buy_vol > 0:
                position += buy_vol
                capital -= buy_vol * current_price
                position_cost = current_price
                base_price = current_price
                trades += 1
        
        elif position > 0 and current_price >= base_price * (1 + step):
            # 卖出
            sell_vol = min(vol_size, position)
            if sell_vol > 0:
                profit = (current_price - position_cost) * sell_vol
                if profit > 0:
                    wins += 1
                capital += sell_vol * current_price
                position -= sell_vol
                base_price = current_price
                trades += 1
    
    # 最终结算
    if position > 0:
        capital += position * current_price
    
    total_return = (capital - 100000) / 100000
    win_rate = wins / trades if trades > 0 else 0
    
    print("回测结果:")
    print("初始资金: 100000")
    print("最终资金: {:.2f}".format(capital))
    print("总收益率: {:.2f}%" .format(total_return*100))
    print("总交易次数: {}".format(trades))
    print("平均胜率: {:.2f}%" .format(win_rate*100))
    print("="*50)
    
    return total_return, trades, win_rate

def generate_simulated_data(days=200):
    """生成模拟市场数据"""
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

if __name__ == "__main__":
    print("进阶版机器学习自适应策略回测")
    print("生成模拟数据...")
    df = generate_simulated_data(days=200)
    backtest_strategy(df)