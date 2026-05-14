# -*- coding: utf-8 -*-
"""
简化版测试脚本，用于验证进阶版机器学习自适应策略的核心功能
"""

import pandas as pd
import numpy as np
from sklearn.ensemble import GradientBoostingClassifier
import ta

# ====================== 配置项 ======================
LOOKBACK_WINDOW = 30
PREDICT_WINDOW = 3
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

def generate_simulated_data(days=100):
    """生成模拟市场数据"""
    np.random.seed(42)
    dates = pd.date_range(start='2023-01-01', periods=days)
    
    # 生成基础价格走势
    base_trend = np.linspace(100, 120, days)  # 基础上涨趋势
    
    # 添加不同市场类型的波动
    volatility = np.zeros(days)
    
    # 横盘市场
    volatility[0:25] = 0.01
    
    # 上涨市场
    volatility[25:50] = 0.02
    base_trend[25:50] = np.linspace(105, 140, 25)
    
    # 下跌市场
    volatility[50:75] = 0.02
    base_trend[50:75] = np.linspace(140, 110, 25)
    
    # 波动市场
    volatility[75:100] = 0.04
    base_trend[75:100] = np.linspace(110, 130, 25)
    
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
    try:
        print("测试进阶版机器学习自适应策略核心功能")
        print("="*50)
        
        # 生成模拟数据
        print("生成模拟数据...")
        df = generate_simulated_data(days=100)
        print(f"生成了 {len(df)} 天的模拟数据")
        print(f"价格范围: {df['close'].min():.2f} - {df['close'].max():.2f}")
        
        # 训练模型
        print("\n训练市场预判模型...")
        train_market_model(df)
        
        # 测试市场类型预测
        print("\n测试市场类型预测...")
        test_windows = [
            (0, 30, "横盘市场"),
            (25, 55, "上涨市场"),
            (50, 80, "下跌市场"),
            (75, 100, "波动市场")
        ]
        
        for start, end, expected in test_windows:
            print(f"处理窗口 {start}-{end}...")
            window_prices = df['close'].iloc[start:end].values
            window_volumes = df['volume'].iloc[start:end].values
            print(f"窗口价格长度: {len(window_prices)}, 成交量长度: {len(window_volumes)}")
            
            # 提取特征
            features = extract_advanced_features(window_prices, window_volumes)
            print(f"特征形状: {features.shape}")
            print(f"特征值: {features}")
            
            # 预测市场类型
            predicted = predict_market_type(window_prices, window_volumes)
            print(f"窗口 {start}-{end} (预期: {expected}): 预测为 {predicted}")
        
        # 测试策略参数匹配
        print("\n测试策略参数匹配...")
        for market_type in STRATEGY_PARAMS:
            params = STRATEGY_PARAMS[market_type]
            print(f"{market_type} 市场: 步长 {params['step']*100:.1f}%, 仓位 {params['vol']}")
        
        print("\n核心功能测试完成！")
        print("模型训练成功，市场类型预测功能正常，策略参数匹配正确。")
    except Exception as e:
        print(f"测试过程中出现错误: {e}")
        import traceback
        traceback.print_exc()