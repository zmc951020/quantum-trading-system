# -*- coding: utf-8 -*-
"""
市场自适应策略模型集合
包含四种市场类型的策略模型和混合模型
"""

import pandas as pd
import numpy as np
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
import ta

# 尝试导入tensorflow，如果失败则设置标志
try:
    import tensorflow as tf
    from tensorflow.keras.models import Sequential
    from tensorflow.keras.layers import LSTM, Dense, Dropout
    tensorflow_available = True
except ImportError:
    tensorflow_available = False
    print("警告：未安装tensorflow，深度学习市场分类器将不可用")

# ====================== 基础函数 ======================

def calculate_indicators(df):
    """计算技术指标"""
    # 趋势指标
    df['ema8'] = ta.trend.ema_indicator(df.close, window=8)
    df['ema20'] = ta.trend.ema_indicator(df.close, window=20)
    df['ema60'] = ta.trend.ema_indicator(df.close, window=60)
    df['slope'] = df.ema20 - df.ema60
    
    # 波动率指标
    df['atr'] = ta.volatility.average_true_range(df.high, df.low, df.close, window=14)
    df['atr_mean'] = df.atr.rolling(60).mean()
    df['atr_ratio'] = df.atr / df.atr_mean
    
    # 趋势强度指标
    df['adx'] = ta.trend.adx(df.high, df.low, df.close, window=14)
    
    # 震荡指标
    df['rsi'] = ta.momentum.rsi(df.close, window=14)
    # 计算布林带
    df['bollinger_middle'] = df['close'].rolling(window=20).mean()
    df['bollinger_std'] = df['close'].rolling(window=20).std()
    df['bollinger_upper'] = df['bollinger_middle'] + 2 * df['bollinger_std']
    df['bollinger_lower'] = df['bollinger_middle'] - 2 * df['bollinger_std']
    df['bollinger_width'] = (df.bollinger_upper - df.bollinger_lower) / df.close
    
    # 动量指标
    df['roc'] = ta.momentum.roc(df.close, window=10)
    
    # 收益率和波动率
    df['return'] = df.close.pct_change()
    df['volatility'] = df['return'].rolling(20).std() * np.sqrt(252)
    
    # 最大回撤
    df['cum_return'] = (1 + df['return']).cumprod()
    df['cum_max'] = df['cum_return'].cummax()
    df['drawdown'] = (df['cum_return'] - df['cum_max']) / df['cum_max']
    
    return df

# ====================== 市场类型判断 ======================

def get_market_state(df):
    """基于技术指标判断市场状态"""
    df = calculate_indicators(df)
    last = df.iloc[-1]
    
    # 高波动优先判断
    if last.atr_ratio > 1.5:
        return 'high_vol'
    
    # 趋势判断
    if last.adx >= 25:
        if last.slope > 0:
            return 'up'
        else:
            return 'down'
    
    # 横盘
    return 'sideway'

# ====================== 机器学习市场类型判断 ======================

class MLMarketClassifier:
    """机器学习市场类型分类器"""
    def __init__(self):
        self.model = GradientBoostingClassifier(n_estimators=100, learning_rate=0.1, max_depth=3)
        self.scaler = StandardScaler()
        self.trained = False
    
    def extract_features(self, df):
        """提取特征"""
        df = calculate_indicators(df)
        features = []
        for i in range(60, len(df)):
            window = df.iloc[i-60:i]
            feature = [
                window['adx'].iloc[-1],
                window['slope'].iloc[-1],
                window['atr_ratio'].iloc[-1],
                window['bollinger_width'].iloc[-1],
                window['rsi'].iloc[-1],
                window['roc'].iloc[-1],
                window['volatility'].iloc[-1],
                window['drawdown'].iloc[-1]
            ]
            features.append(feature)
        return np.array(features)
    
    def label_market_state(self, df):
        """标注市场状态"""
        labels = []
        for i in range(60, len(df)):
            state = get_market_state(df.iloc[i-60:i+1])
            label_map = {'up': 0, 'down': 1, 'sideway': 2, 'high_vol': 3}
            labels.append(label_map[state])
        return np.array(labels)
    
    def train(self, df):
        """训练模型"""
        X = self.extract_features(df)
        y = self.label_market_state(df)
        
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
        X_train = self.scaler.fit_transform(X_train)
        X_test = self.scaler.transform(X_test)
        
        self.model.fit(X_train, y_train)
        accuracy = self.model.score(X_test, y_test)
        print(f"机器学习模型训练完成，准确率: {accuracy:.2f}")
        self.trained = True
    
    def predict(self, df):
        """预测市场状态"""
        if not self.trained:
            return get_market_state(df)
        
        features = self.extract_features(df)
        if len(features) == 0:
            return get_market_state(df)
        
        features = self.scaler.transform(features)
        prediction = self.model.predict(features)[-1]
        label_map = {0: 'up', 1: 'down', 2: 'sideway', 3: 'high_vol'}
        return label_map[prediction]

# ====================== 深度学习市场类型判断 ======================

if tensorflow_available:
    class DLMarketClassifier:
        """深度学习市场类型分类器"""
        def __init__(self):
            self.model = None
            self.scaler = StandardScaler()
            self.trained = False
        
        def build_model(self, input_shape):
            """构建LSTM模型"""
            model = Sequential()
            model.add(LSTM(64, return_sequences=True, input_shape=input_shape))
            model.add(Dropout(0.2))
            model.add(LSTM(32, return_sequences=False))
            model.add(Dropout(0.2))
            model.add(Dense(4, activation='softmax'))
            model.compile(optimizer='adam', loss='sparse_categorical_crossentropy', metrics=['accuracy'])
            return model
        
        def prepare_data(self, df, window_size=60):
            """准备LSTM数据"""
            df = calculate_indicators(df)
            features = []
            labels = []
            
            for i in range(window_size, len(df)):
                window = df.iloc[i-window_size:i]
                feature = window[['adx', 'slope', 'atr_ratio', 'bollinger_width', 'rsi', 'roc', 'volatility', 'drawdown']].values
                features.append(feature)
                
                state = get_market_state(df.iloc[i-window_size:i+1])
                label_map = {'up': 0, 'down': 1, 'sideway': 2, 'high_vol': 3}
                labels.append(label_map[state])
            
            X = np.array(features)
            y = np.array(labels)
            return X, y
        
        def train(self, df):
            """训练模型"""
            X, y = self.prepare_data(df)
            X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
            
            # 标准化
            n_samples, n_time, n_features = X_train.shape
            X_train_reshaped = X_train.reshape(-1, n_features)
            self.scaler.fit(X_train_reshaped)
            X_train = self.scaler.transform(X_train_reshaped).reshape(n_samples, n_time, n_features)
            
            n_samples_test = X_test.shape[0]
            X_test_reshaped = X_test.reshape(-1, n_features)
            X_test = self.scaler.transform(X_test_reshaped).reshape(n_samples_test, n_time, n_features)
            
            # 构建和训练模型
            self.model = self.build_model((X_train.shape[1], X_train.shape[2]))
            self.model.fit(X_train, y_train, epochs=50, batch_size=32, validation_data=(X_test, y_test))
            
            # 评估
            loss, accuracy = self.model.evaluate(X_test, y_test)
            print(f"深度学习模型训练完成，准确率: {accuracy:.2f}")
            self.trained = True
        
        def predict(self, df):
            """预测市场状态"""
            if not self.trained:
                return get_market_state(df)
            
            X, _ = self.prepare_data(df)
            if len(X) == 0:
                return get_market_state(df)
            
            # 标准化
            n_samples, n_time, n_features = X.shape
            X_reshaped = X.reshape(-1, n_features)
            X_scaled = self.scaler.transform(X_reshaped).reshape(n_samples, n_time, n_features)
            
            prediction = np.argmax(self.model.predict(X_scaled)[-1])
            label_map = {0: 'up', 1: 'down', 2: 'sideway', 3: 'high_vol'}
            return label_map[prediction]
else:
    # 如果tensorflow不可用，定义一个简单的DLMarketClassifier类
    class DLMarketClassifier:
        """深度学习市场类型分类器（tensorflow不可用）"""
        def __init__(self):
            self.trained = False
        
        def train(self, df):
            print("警告：tensorflow不可用，无法训练深度学习模型")
        
        def predict(self, df):
            return get_market_state(df)

# ====================== 策略模型 ======================

class UpMarketStrategy:
    """上涨市场策略"""
    def __init__(self):
        self.name = "上涨市场策略"
    
    def get_signal(self, df):
        """获取交易信号"""
        df = calculate_indicators(df)
        last = df.iloc[-1]
        
        # 趋势跟踪信号
        if last.ema8 > last.ema20 and last.adx > 25:
            return "buy"
        elif last.ema8 < last.ema20 and last.adx > 25:
            return "sell"
        else:
            return "hold"
    
    def get_grid_step(self, price, atr, atr_mean, adx, mdd):
        """获取网格步长"""
        k_base = 0.018
        step = price * k_base * (atr / atr_mean) * (1 + 0.003 * adx) / (1 + 5 * mdd)
        return max(0.001, step)
    
    def get_position_size(self, win_rate, profit_loss_ratio):
        """获取仓位大小"""
        if profit_loss_ratio <= 0:
            return 0.0
        kelly = (win_rate * (profit_loss_ratio + 1) - 1) / profit_loss_ratio
        return float(max(0.0, min(kelly * 1.0, 1.0)))

class DownMarketStrategy:
    """下跌市场策略"""
    def __init__(self):
        self.name = "下跌市场策略"
    
    def get_signal(self, df):
        """获取交易信号"""
        df = calculate_indicators(df)
        last = df.iloc[-1]
        
        # 防御策略
        if last.ema8 < last.ema20 and last.adx > 25:
            return "sell"
        elif last.rsi < 30 and last.roc < -5:
            return "buy"  # 超卖反弹
        else:
            return "hold"
    
    def get_grid_step(self, price, atr, atr_mean, adx, mdd):
        """获取网格步长"""
        k_base = 0.025
        step = price * k_base * (atr / atr_mean) * (1 + 0.003 * adx) / (1 + 5 * mdd)
        return max(0.001, step)
    
    def get_position_size(self, win_rate, profit_loss_ratio):
        """获取仓位大小"""
        if profit_loss_ratio <= 0:
            return 0.0
        kelly = (win_rate * (profit_loss_ratio + 1) - 1) / profit_loss_ratio
        return float(max(0.0, min(kelly * 0.2, 0.2)))

class SidewayMarketStrategy:
    """横盘市场策略"""
    def __init__(self):
        self.name = "横盘市场策略"
    
    def get_signal(self, df):
        """获取交易信号"""
        df = calculate_indicators(df)
        last = df.iloc[-1]
        
        # 均值回归信号
        if last.close > last.bollinger_upper:
            return "sell"
        elif last.close < last.bollinger_lower:
            return "buy"
        elif last.rsi > 70:
            return "sell"
        elif last.rsi < 30:
            return "buy"
        else:
            return "hold"
    
    def get_grid_step(self, price, atr, atr_mean, adx, mdd):
        """获取网格步长"""
        k_base = 0.012
        step = price * k_base * (atr / atr_mean) * (1 + 0.003 * adx) / (1 + 5 * mdd)
        return max(0.001, step)
    
    def get_position_size(self, win_rate, profit_loss_ratio):
        """获取仓位大小"""
        if profit_loss_ratio <= 0:
            return 0.0
        kelly = (win_rate * (profit_loss_ratio + 1) - 1) / profit_loss_ratio
        return float(max(0.0, min(kelly * 0.5, 0.5)))

class HighVolMarketStrategy:
    """高波动市场策略"""
    def __init__(self):
        self.name = "高波动市场策略"
    
    def get_signal(self, df):
        """获取交易信号"""
        df = calculate_indicators(df)
        last = df.iloc[-1]
        
        # 高波动策略
        if last.ema8 > last.ema20:
            return "buy"
        elif last.ema8 < last.ema20:
            return "sell"
        else:
            return "hold"
    
    def get_grid_step(self, price, atr, atr_mean, adx, mdd):
        """获取网格步长"""
        k_base = 0.03
        step = price * k_base * (atr / atr_mean) * (1 + 0.003 * adx) / (1 + 5 * mdd)
        return max(0.001, step)
    
    def get_position_size(self, win_rate, profit_loss_ratio):
        """获取仓位大小"""
        if profit_loss_ratio <= 0:
            return 0.0
        kelly = (win_rate * (profit_loss_ratio + 1) - 1) / profit_loss_ratio
        return float(max(0.0, min(kelly * 0.3, 0.4)))

class MixedMarketStrategy:
    """混合市场策略"""
    def __init__(self, market_classifier=None):
        self.name = "混合市场策略"
        self.market_classifier = market_classifier
        self.strategies = {
            'up': UpMarketStrategy(),
            'down': DownMarketStrategy(),
            'sideway': SidewayMarketStrategy(),
            'high_vol': HighVolMarketStrategy()
        }
    
    def get_market_state(self, df):
        """获取市场状态"""
        if self.market_classifier:
            return self.market_classifier.predict(df)
        else:
            return get_market_state(df)
    
    def get_signal(self, df):
        """获取交易信号"""
        state = self.get_market_state(df)
        strategy = self.strategies[state]
        return strategy.get_signal(df)
    
    def get_grid_step(self, df):
        """获取网格步长"""
        state = self.get_market_state(df)
        strategy = self.strategies[state]
        
        df = calculate_indicators(df)
        last = df.iloc[-1]
        return strategy.get_grid_step(last.close, last.atr, last.atr_mean, last.adx, abs(last.drawdown))
    
    def get_position_size(self, df, win_rate=0.55, profit_loss_ratio=1.8):
        """获取仓位大小"""
        state = self.get_market_state(df)
        strategy = self.strategies[state]
        return strategy.get_position_size(win_rate, profit_loss_ratio)

# ====================== 分钟级交易策略 ======================

class MinuteMixedMarketStrategy:
    """分钟级混合市场策略"""
    def __init__(self, market_classifier=None, time_frame=5):
        self.name = f"{time_frame}分钟混合市场策略"
        self.time_frame = time_frame
        self.market_classifier = market_classifier
        self.strategies = {
            'up': UpMarketStrategy(),
            'down': DownMarketStrategy(),
            'sideway': SidewayMarketStrategy(),
            'high_vol': HighVolMarketStrategy()
        }
    
    def get_market_state(self, df):
        """获取分钟级市场状态"""
        if self.market_classifier:
            return self.market_classifier.predict(df)
        else:
            return self._get_minute_market_state(df)
    
    def _get_minute_market_state(self, df):
        """基于分钟级数据判断市场状态"""
        # 计算分钟级指标
        df['ema8'] = ta.EMA(df.close, timeperiod=8)
        df['ema20'] = ta.EMA(df.close, timeperiod=20)
        df['adx'] = ta.ADX(df.high, df.low, df.close, timeperiod=9)
        df['atr'] = ta.ATR(df.high, df.low, df.close, timeperiod=7)
        df['atr_mean'] = df['atr'].rolling(30).mean()
        df['atr_ratio'] = df['atr'] / df['atr_mean']
        
        last = df.iloc[-1]
        
        # 高波动优先判断
        if last.atr_ratio > 1.4:
            return 'high_vol'
        
        # 趋势判断
        if last.adx >= 22:
            if last.ema8 > last.ema20:
                return 'up'
            else:
                return 'down'
        
        # 横盘
        return 'sideway'
    
    def get_signal(self, df):
        """获取交易信号"""
        state = self.get_market_state(df)
        strategy = self.strategies[state]
        return strategy.get_signal(df)
    
    def get_grid_step(self, df):
        """获取分钟级网格步长"""
        state = self.get_market_state(df)
        
        df = calculate_indicators(df)
        last = df.iloc[-1]
        
        # 分钟级基础步长系数
        base_coef = {
            'up': 0.0028,     # 0.28%
            'down': 0.0040,   # 0.4%
            'sideway': 0.0016, # 0.16%
            'high_vol': 0.0050  # 0.5%
        }[state]
        
        vol_mult = last.atr / last.atr_mean if last.atr_mean > 0 else 1.0
        step = last.close * base_coef * vol_mult
        return max(0.001, step)
    
    def get_position_size(self, df, win_rate=0.55, profit_loss_ratio=1.8):
        """获取分钟级仓位大小"""
        state = self.get_market_state(df)
        
        # 基础凯利
        if profit_loss_ratio <= 0:
            return 0.0
        kelly = (win_rate * profit_loss_ratio - (1 - win_rate)) / profit_loss_ratio
        
        # 行情乘数
        state_mult = {
            'up': 1.0,
            'down': 0.2,
            'sideway': 0.6,
            'high_vol': 0.4
        }[state]
        
        # 最终仓位（上限60%）
        position = max(0.0, min(kelly * state_mult, 0.6))
        return float(position)

# ====================== 策略评估 ======================

def evaluate_strategy(strategy, df, initial_capital=100000):
    """评估策略表现"""
    capital = initial_capital
    position = 0
    position_cost = 0
    trades = 0
    wins = 0
    equity_curve = []
    
    for i in range(60, len(df)):
        window = df.iloc[i-60:i+1]
        signal = strategy.get_signal(window)
        current_price = window.close.iloc[-1]
        
        # 计算仓位大小
        try:
            pos_size = strategy.get_position_size(window, win_rate=0.55, profit_loss_ratio=1.8)
        except TypeError:
            # 对于不接受win_rate和profit_loss_ratio参数的策略
            pos_size = strategy.get_position_size(win_rate=0.55, profit_loss_ratio=1.8)
        max_position = int(capital * pos_size / current_price)
        
        # 执行交易
        if signal == "buy" and position == 0:
            # 买入
            position = max_position
            capital -= position * current_price
            position_cost = current_price
            trades += 1
        elif signal == "sell" and position > 0:
            # 卖出
            profit = (current_price - position_cost) * position
            if profit > 0:
                wins += 1
            capital += position * current_price
            position = 0
            trades += 1
        
        # 记录资金曲线
        total_equity = capital + (position * current_price if position > 0 else 0)
        equity_curve.append(total_equity)
    
    # 计算指标
    final_capital = equity_curve[-1] if equity_curve else initial_capital
    total_return = (final_capital - initial_capital) / initial_capital
    win_rate = wins / trades if trades > 0 else 0
    
    # 计算夏普比率
    returns = np.diff(equity_curve) / equity_curve[:-1]
    sharpe_ratio = np.mean(returns) / np.std(returns) * np.sqrt(252) if len(returns) > 0 else 0
    
    # 计算最大回撤
    peak = equity_curve[0]
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

# ====================== 主函数 ======================

if __name__ == "__main__":
    print("市场自适应策略模型集合")
    print("1. 上涨市场策略")
    print("2. 下跌市场策略")
    print("3. 横盘市场策略")
    print("4. 高波动市场策略")
    print("5. 混合市场策略")
    print("6. 分钟级混合市场策略")
    
    choice = input("请选择策略类型 (1-6): ")
    
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
            'open': prices,
            'high': prices * (1 + np.random.uniform(0, 0.02, days)),
            'low': prices * (1 - np.random.uniform(0, 0.02, days)),
            'close': prices,
            'volume': volumes
        }, index=dates)
        
        return df
    
    df = generate_simulated_data(days=200)
    
    if choice == "1":
        strategy = UpMarketStrategy()
    elif choice == "2":
        strategy = DownMarketStrategy()
    elif choice == "3":
        strategy = SidewayMarketStrategy()
    elif choice == "4":
        strategy = HighVolMarketStrategy()
    elif choice == "5":
        # 训练机器学习模型
        ml_classifier = MLMarketClassifier()
        ml_classifier.train(df)
        strategy = MixedMarketStrategy(market_classifier=ml_classifier)
    elif choice == "6":
        # 训练机器学习模型
        ml_classifier = MLMarketClassifier()
        ml_classifier.train(df)
        strategy = MinuteMixedMarketStrategy(market_classifier=ml_classifier, time_frame=5)
    else:
        print("无效选择")
        exit()
    
    # 评估策略
    results = evaluate_strategy(strategy, df)
    
    print(f"\n策略评估结果:")
    print(f"策略名称: {strategy.name}")
    print(f"总收益率: {results['total_return']*100:.2f}%")
    print(f"胜率: {results['win_rate']*100:.2f}%")
    print(f"夏普比率: {results['sharpe_ratio']:.2f}")
    print(f"最大回撤: {results['max_drawdown']*100:.2f}%")
    print(f"总交易次数: {results['trades']}")
    print(f"最终资金: {results['final_capital']:.2f}")
