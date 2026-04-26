#!/usr/bin/env python3
"""
趋势预测和波段识别模块
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, classification_report
from typing import Dict, List, Tuple, Optional

class TrendPredictor:
    """
    趋势预测器
    """
    
    def __init__(self):
        """
        初始化趋势预测器
        """
        self.model = RandomForestClassifier(n_estimators=100, random_state=42)
        self.scaler = StandardScaler()
        self.is_trained = False
    
    def extract_features(self, data: pd.Series, lookback: int = 30) -> pd.DataFrame:
        """
        提取特征
        
        Args:
            data: 价格数据
            lookback: 回溯期
            
        Returns:
            特征DataFrame
        """
        df = pd.DataFrame(data, columns=['price'])
        
        # 基本特征
        df['return'] = df['price'].pct_change()
        df['log_return'] = np.log(df['price'] / df['price'].shift(1))
        
        # 移动平均线
        for window in [5, 10, 20, 50]:
            df[f'MA{window}'] = df['price'].rolling(window=window).mean()
            df[f'MA{window}_diff'] = df[f'MA{window}'].diff() / df[f'MA{window}'].shift(1)
        
        # 均线交叉
        df['MA5_20_crossover'] = (df['MA5'] - df['MA20']) / df['MA20']
        df['MA10_50_crossover'] = (df['MA10'] - df['MA50']) / df['MA50']
        
        # 波动率
        for window in [10, 20, 30]:
            df[f'volatility_{window}'] = df['return'].rolling(window=window).std()
        
        # RSI
        delta = df['price'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))
        
        # 布林带
        df['BB_middle'] = df['price'].rolling(window=20).mean()
        df['BB_std'] = df['price'].rolling(window=20).std()
        df['BB_upper'] = df['BB_middle'] + 2 * df['BB_std']
        df['BB_lower'] = df['BB_middle'] - 2 * df['BB_std']
        df['BB_position'] = (df['price'] - df['BB_lower']) / (df['BB_upper'] - df['BB_lower'])
        
        # 动量
        for window in [10, 20, 50]:
            df[f'momentum_{window}'] = df['price'] - df['price'].shift(window)
            df[f'momentum_{window}_norm'] = df[f'momentum_{window}'] / df['price'].shift(window)
        
        # MACD
        exp1 = df['price'].ewm(span=12, adjust=False).mean()
        exp2 = df['price'].ewm(span=26, adjust=False).mean()
        df['MACD'] = exp1 - exp2
        df['MACD_signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
        df['MACD_hist'] = df['MACD'] - df['MACD_signal']
        
        # 移除NaN值
        df = df.dropna()
        
        return df
    
    def create_labels(self, data: pd.Series, future_window: int = 5, threshold: float = 0.01) -> pd.Series:
        """
        创建标签
        
        Args:
            data: 价格数据
            future_window: 未来窗口
            threshold: 阈值
            
        Returns:
            标签Series
        """
        # 计算未来收益率
        future_returns = data.pct_change(future_window).shift(-future_window)
        
        # 创建标签：1=上涨，0=横盘，-1=下跌
        labels = pd.Series(0, index=data.index)
        labels[future_returns > threshold] = 1
        labels[future_returns < -threshold] = -1
        
        return labels
    
    def train(self, data: pd.Series, future_window: int = 5, threshold: float = 0.01):
        """
        训练模型
        
        Args:
            data: 价格数据
            future_window: 未来窗口
            threshold: 阈值
        """
        # 提取特征
        features = self.extract_features(data)
        
        # 创建标签
        labels = self.create_labels(data, future_window, threshold)
        
        # 对齐特征和标签
        common_index = features.index.intersection(labels.index)
        X = features.loc[common_index].drop('price', axis=1)
        y = labels.loc[common_index]
        
        if len(X) < 100:
            print("数据不足，无法训练模型")
            return
        
        # 划分训练集和测试集
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
        
        # 标准化
        self.scaler.fit(X_train)
        X_train_scaled = self.scaler.transform(X_train)
        X_test_scaled = self.scaler.transform(X_test)
        
        # 训练模型
        self.model.fit(X_train_scaled, y_train)
        
        # 评估模型
        y_pred = self.model.predict(X_test_scaled)
        accuracy = accuracy_score(y_test, y_pred)
        print(f"模型训练完成，准确率: {accuracy:.4f}")
        print(classification_report(y_test, y_pred))
        
        self.is_trained = True
    
    def predict_trend(self, data: pd.Series) -> int:
        """
        预测趋势
        
        Args:
            data: 价格数据
            
        Returns:
            趋势预测：1=上涨，0=横盘，-1=下跌
        """
        if not self.is_trained:
            return 0
        
        # 提取特征
        features = self.extract_features(data)
        if features.empty:
            return 0
        
        # 获取最新特征
        latest_features = features.drop('price', axis=1).iloc[-1:]
        
        # 标准化
        features_scaled = self.scaler.transform(latest_features)
        
        # 预测
        prediction = self.model.predict(features_scaled)[0]
        
        return prediction
    
    def predict_bands(self, data: pd.Series, num_bands: int = 5) -> Dict[str, float]:
        """
        预测最优交易波段
        
        Args:
            data: 价格数据
            num_bands: 波段数量
            
        Returns:
            波段字典
        """
        current_price = data.iloc[-1]
        
        # 计算波动率
        returns = data.pct_change().dropna()
        if len(returns) > 20:
            volatility = returns.iloc[-20:].std()
        else:
            volatility = 0.01
        
        # 预测上涨和下跌波段
        bands = {}
        
        # 上涨波段
        for i in range(1, num_bands + 1):
            bands[f'up_band_{i}'] = current_price * (1 + volatility * i * 0.5)
        
        # 下跌波段
        for i in range(1, num_bands + 1):
            bands[f'down_band_{i}'] = current_price * (1 - volatility * i * 0.5)
        
        return bands

class AdaptiveTradingStrategy:
    """
    自适应交易策略 - 优化用于分钟级交易
    """
    
    def __init__(self, initial_balance: float = 100000):
        """
        初始化自适应交易策略
        
        Args:
            initial_balance: 初始资金
        """
        self.initial_balance = initial_balance
        self.current_balance = initial_balance
        self.position = 0
        self.trend_predictor = TrendPredictor()
        self.current_strategy = 'grid'  # 默认使用网格交易
        self.last_switch_time = None
        self.price_history = []
        self.last_trade_time = None
        self.min_trade_interval = pd.Timedelta(minutes=1)  # 最小交易间隔
    
    def train_models(self, data: pd.Series):
        """
        训练模型
        
        Args:
            data: 价格数据
        """
        self.trend_predictor.train(data)
    
    def detect_market_type(self, data: pd.Series) -> str:
        """
        检测市场类型
        
        Args:
            data: 价格数据
            
        Returns:
            市场类型: 'trending_up', 'trending_down', 'range_bound'
        """
        # 计算关键指标
        returns = data.pct_change().dropna()
        
        if len(returns) < 20:
            return 'range_bound'
        
        # 计算动量
        momentum = (data.iloc[-1] - data.iloc[-20]) / data.iloc[-20]
        
        # 计算波动率
        volatility = returns.iloc[-20:].std()
        
        # 计算趋势强度
        ema20 = data.ewm(span=20, adjust=False).mean()
        ema50 = data.ewm(span=50, adjust=False).mean()
        trend_strength = (ema20.iloc[-1] - ema50.iloc[-1]) / ema50.iloc[-1]
        
        # 计算价格范围
        price_range = (data.iloc[-20:].max() - data.iloc[-20:].min()) / data.iloc[-20:].mean()
        
        # 确定市场类型
        if abs(trend_strength) > 0.02:
            if trend_strength > 0:
                return 'trending_up'
            else:
                return 'trending_down'
        elif price_range < 0.03:
            # 窄幅横盘，适合网格交易
            return 'range_bound'
        elif price_range > 0.08:
            # 宽幅波动，适合趋势交易
            if momentum > 0:
                return 'trending_up'
            else:
                return 'trending_down'
        else:
            # 中等波动，根据趋势强度判断
            if abs(trend_strength) > 0.01:
                if trend_strength > 0:
                    return 'trending_up'
                else:
                    return 'trending_down'
            else:
                return 'range_bound'
    
    def update_price(self, current_price: float, data: pd.Series, timestamp: Optional[pd.Timestamp] = None) -> Dict[str, any]:
        """
        更新价格并执行交易
        
        Args:
            current_price: 当前价格
            data: 历史价格数据
            timestamp: 当前时间戳
            
        Returns:
            交易结果
        """
        # 记录价格历史
        self.price_history.append(current_price)
        
        # 限制价格历史长度
        if len(self.price_history) > 100:
            self.price_history = self.price_history[-100:]
        
        # 检查交易间隔
        if self.last_trade_time and timestamp:
            if timestamp - self.last_trade_time < self.min_trade_interval:
                return {"action": "hold", "balance": self.current_balance, "position": self.position}
        
        # 检测市场类型
        market_type = self.detect_market_type(data)
        
        # 预测趋势
        trend = self.trend_predictor.predict_trend(data)
        
        # 预测波段
        bands = self.trend_predictor.predict_bands(data)
        
        # 策略切换逻辑
        if market_type == 'trending_up' and self.current_strategy != 'trend':
            # 上涨趋势，切换到趋势交易
            # 先平仓所有网格交易仓位
            if self.position != 0:
                # 平仓
                revenue = self.position * current_price
                self.current_balance += revenue
                self.position = 0
                print("平仓网格交易仓位，准备切换到趋势交易")
            
            self.current_strategy = 'trend'
            self.last_switch_time = timestamp or pd.Timestamp.now()
            print("切换到趋势交易策略")
        elif market_type == 'trending_down' and self.current_strategy != 'grid':
            # 下跌趋势，切换到网格交易
            # 先平仓所有趋势交易仓位
            if self.position != 0:
                # 平仓
                revenue = self.position * current_price
                self.current_balance += revenue
                self.position = 0
                print("平仓趋势交易仓位，准备切换到网格交易")
            
            self.current_strategy = 'grid'
            self.last_switch_time = timestamp or pd.Timestamp.now()
            print("切换到网格交易策略")
        elif market_type == 'range_bound' and self.current_strategy != 'grid':
            # 横盘市场，使用网格交易
            # 先平仓所有趋势交易仓位
            if self.position != 0:
                # 平仓
                revenue = self.position * current_price
                self.current_balance += revenue
                self.position = 0
                print("平仓趋势交易仓位，准备切换到网格交易")
            
            self.current_strategy = 'grid'
            self.last_switch_time = timestamp or pd.Timestamp.now()
            print("切换到网格交易策略")
        
        # 根据当前策略执行交易
        if self.current_strategy == 'trend':
            result = self._execute_trend_trade(current_price, bands)
        else:
            result = self._execute_grid_trade(current_price, bands)
        
        # 更新最后交易时间
        if result['action'] != 'hold':
            self.last_trade_time = timestamp or pd.Timestamp.now()
        
        return result
    
    def _execute_trend_trade(self, current_price: float, bands: Dict[str, float]) -> Dict[str, any]:
        """
        执行趋势交易
        
        Args:
            current_price: 当前价格
            bands: 预测波段
            
        Returns:
            交易结果
        """
        # 趋势交易逻辑 - 优化用于分钟级交易
        action = "hold"
        quantity = 0
        
        # 买入逻辑：价格回调到均线附近时买入
        if self.position == 0:
            # 计算短期均线
            if len(self.price_history) >= 20:
                ma20 = sum(self.price_history[-20:]) / 20
                # 价格接近均线时买入
                if abs(current_price - ma20) / ma20 < 0.005:
                    # 买入 - 限制资金使用
                    quantity = self.current_balance * 0.3 / current_price  # 仅使用30%资金
                    if quantity > 0:
                        self.position = quantity
                        self.current_balance -= quantity * current_price
                        action = "buy"
        
        # 卖出逻辑：价格达到上涨波段或出现反转信号
        elif self.position > 0:
            # 计算短期均线
            if len(self.price_history) >= 10:
                ma10 = sum(self.price_history[-10:]) / 10
                ma5 = sum(self.price_history[-5:]) / 5
                
                # 价格达到上涨波段
                if current_price > bands['up_band_2']:
                    # 卖出获利
                    revenue = self.position * current_price
                    self.current_balance += revenue
                    quantity = self.position
                    self.position = 0
                    action = "sell"
                # 价格跌破短期均线，出现反转信号
                elif current_price < ma10 and ma5 < ma10:
                    # 卖出止损
                    revenue = self.position * current_price
                    self.current_balance += revenue
                    quantity = self.position
                    self.position = 0
                    action = "sell"
        
        return {
            "action": action,
            "quantity": quantity,
            "price": current_price,
            "balance": self.current_balance,
            "position": self.position,
            "strategy": "trend",
            "bands": bands
        }
    
    def _execute_grid_trade(self, current_price: float, bands: Dict[str, float]) -> Dict[str, any]:
        """
        执行网格交易
        
        Args:
            current_price: 当前价格
            bands: 预测波段
            
        Returns:
            交易结果
        """
        # 网格交易逻辑 - 优化用于分钟级交易
        action = "hold"
        quantity = 0
        
        # 确定当前价格所在的网格区间
        grid_levels = sorted([bands[f'down_band_{i}'] for i in range(1, 4)] + 
                           [bands[f'up_band_{i}'] for i in range(1, 4)])
        
        current_level = None
        for i, level in enumerate(grid_levels):
            if current_price <= level:
                current_level = i
                break
        if current_level is None:
            current_level = len(grid_levels)
        
        # 计算目标仓位 - 更保守的仓位管理
        target_position = (current_level - 3) * 5  # 每个网格5个单位
        position_change = target_position - self.position
        
        # 执行交易
        if position_change > 0:
            # 买入
            cost = position_change * current_price
            if cost <= self.current_balance * 0.2:  # 仅使用20%资金
                self.position = target_position
                self.current_balance -= cost
                action = "buy"
                quantity = position_change
        elif position_change < 0:
            # 卖出
            quantity = abs(position_change)
            revenue = quantity * current_price
            self.position = target_position
            self.current_balance += revenue
            action = "sell"
        
        return {
            "action": action,
            "quantity": quantity,
            "price": current_price,
            "balance": self.current_balance,
            "position": self.position,
            "strategy": "grid",
            "bands": bands
        }
    
    def get_performance(self, current_price: float) -> Dict[str, float]:
        """
        获取策略性能
        
        Args:
            current_price: 当前价格
            
        Returns:
            性能指标
        """
        total_value = self.current_balance + self.position * current_price
        return {
            "initial_balance": self.initial_balance,
            "current_balance": self.current_balance,
            "position": self.position,
            "total_value": total_value,
            "pnl": total_value - self.initial_balance,
            "return": (total_value / self.initial_balance - 1) * 100,
            "current_strategy": self.current_strategy
        }
