#!/usr/bin/env python3
"""
市场自适应策略
自动切换不同市场类型的最佳策略
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Tuple, Optional
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.preprocessing import StandardScaler

# 导入其他策略
from strategies.adaptive_range_grid import AdaptiveRangeGridTrading
from strategies.adaptive_grid import AdaptiveGridTrading
from strategies.enhanced_grid import EnhancedGridTrading
from strategies.optimized_downward_reversal import OptimizedDownwardReversalGrid

class MarketAdaptiveStrategy:
    """
    市场自适应策略
    自动切换不同市场类型的最佳策略
    """
    
    def __init__(self, base_price: float, initial_balance: float = 100000):
        """
        初始化市场自适应策略
        
        Args:
            base_price: 基准价格
            initial_balance: 初始资金
        """
        self.base_price = base_price
        self.initial_balance = initial_balance
        self.current_balance = initial_balance
        self.position = 0
        self.price_history = []
        self.is_active = True
        self.last_price = base_price  # 上次价格
        
        # 交易统计
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        
        # 市场类型
        self.market_type = 'range_bound'
        self.last_market_type = 'range_bound'
        self.market_types = ['range_bound', 'trending_up', 'trending_down', 'volatile']
        
        # 技术指标参数
        self.rsi_period = 14  # RSI周期
        self.macd_fast = 12  # MACD快速周期
        self.macd_slow = 26  # MACD慢速周期
        self.macd_signal = 9  # MACD信号周期
        self.bollinger_period = 20  # 布林带周期
        self.bollinger_std = 2  # 布林带标准差
        
        # 机器学习模型
        self.market_classifier = RandomForestClassifier(n_estimators=200, random_state=42)
        self.strategy_selector = RandomForestClassifier(n_estimators=150, random_state=42)
        self.scaler = StandardScaler()
        self.model_trained = False
        
        # 训练数据
        self.market_data = []
        self.market_labels = []
        self.strategy_data = []
        self.strategy_labels = []
        self.model_training_count = 0
        
        # 性能跟踪
        self.trade_history = []
        self.profit_history = []
        self.market_switch_count = 0
        self.strategy_switch_count = 0
        
        # 策略实例
        self.range_strategy = AdaptiveRangeGridTrading(base_price, initial_balance)
        self.adaptive_strategy = AdaptiveGridTrading(base_price, initial_balance)
        self.enhanced_strategy = EnhancedGridTrading(base_price, initial_balance)
        self.downward_strategy = OptimizedDownwardReversalGrid(base_price, initial_balance)
        
        # 当前使用的策略
        self.current_strategy = self.range_strategy
        
        # 策略性能历史
        self.strategy_performance = {
            'range_bound': {'adaptive_range_grid': [], 'adaptive_grid': [], 'enhanced_grid': [], 'optimized_downward_reversal': []},
            'trending_up': {'adaptive_range_grid': [], 'adaptive_grid': [], 'enhanced_grid': [], 'optimized_downward_reversal': []},
            'trending_down': {'adaptive_range_grid': [], 'adaptive_grid': [], 'enhanced_grid': [], 'optimized_downward_reversal': []},
            'volatile': {'adaptive_range_grid': [], 'adaptive_grid': [], 'enhanced_grid': [], 'optimized_downward_reversal': []}
        }
    
    def _calculate_rsi(self, data: pd.Series) -> float:
        """
        计算RSI指标
        
        Args:
            data: 价格数据
            
        Returns:
            RSI值
        """
        if len(data) < self.rsi_period + 1:
            return 50  # 默认值
        
        delta = data.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=self.rsi_period).mean().iloc[-1]
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.rsi_period).mean().iloc[-1]
        
        if loss == 0:
            return 100
        
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    def _calculate_macd(self, data: pd.Series) -> Tuple[float, float, float]:
        """
        计算MACD指标
        
        Args:
            data: 价格数据
            
        Returns:
            MACD, 信号, 柱状图
        """
        if len(data) < self.macd_slow + self.macd_signal:
            return 0, 0, 0  # 默认值
        
        ema12 = data.ewm(span=self.macd_fast, adjust=False).mean()
        ema26 = data.ewm(span=self.macd_slow, adjust=False).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=self.macd_signal, adjust=False).mean()
        histogram = macd - signal
        
        return macd.iloc[-1], signal.iloc[-1], histogram.iloc[-1]
    
    def _calculate_bollinger_bands(self, data: pd.Series) -> Tuple[float, float, float]:
        """
        计算布林带
        
        Args:
            data: 价格数据
            
        Returns:
            上轨, 中轨, 下轨
        """
        if len(data) < self.bollinger_period:
            return data.iloc[-1] * 1.05, data.iloc[-1], data.iloc[-1] * 0.95  # 默认值
        
        ma = data.rolling(window=self.bollinger_period).mean().iloc[-1]
        std = data.rolling(window=self.bollinger_period).std().iloc[-1]
        if std == 0:
            std = 0.01  # 避免除零错误
        upper = ma + (std * self.bollinger_std)
        lower = ma - (std * self.bollinger_std)
        
        return upper, ma, lower
    
    def _extract_features(self, data: pd.Series) -> List[float]:
        """
        提取特征用于机器学习
        
        Args:
            data: 价格数据
            
        Returns:
            特征列表
        """
        if len(data) < 20:
            return [0] * 25  # 返回默认特征
        
        # 计算RSI
        rsi = self._calculate_rsi(data)
        
        # 计算MACD
        macd, signal, histogram = self._calculate_macd(data)
        
        # 计算布林带
        upper_band, middle_band, lower_band = self._calculate_bollinger_bands(data)
        
        # 计算价格变化率
        price_change_1d = (data.iloc[-1] - data.iloc[-2]) / data.iloc[-2] if len(data) > 1 else 0
        price_change_5d = (data.iloc[-1] - data.iloc[-6]) / data.iloc[-6] if len(data) > 5 else 0
        price_change_10d = (data.iloc[-1] - data.iloc[-11]) / data.iloc[-11] if len(data) > 10 else 0
        price_change_20d = (data.iloc[-1] - data.iloc[-21]) / data.iloc[-21] if len(data) > 20 else 0
        
        # 计算波动率
        volatility = data.iloc[-20:].pct_change().std()
        
        # 计算价格范围
        price_range = (data.iloc[-20:].max() - data.iloc[-20:].min()) / data.iloc[-20:].mean()
        
        # 计算移动平均线
        ema10 = data.ewm(span=10).mean().iloc[-1]
        ema30 = data.ewm(span=30).mean().iloc[-1]
        ema60 = data.ewm(span=60).mean().iloc[-1]
        
        # 计算趋势强度
        short_term_trend = (ema10 - ema30) / ema30
        medium_term_trend = (ema30 - ema60) / ema60
        
        # 计算价格动量
        momentum = data.iloc[-1] / data.iloc[-10] if len(data) > 9 else 1
        
        # 计算布林带宽度
        bollinger_width = (upper_band - lower_band) / middle_band
        
        # 计算价格在布林带中的位置
        bollinger_position = (data.iloc[-1] - lower_band) / (upper_band - lower_band) if upper_band > lower_band else 0.5
        
        # 计算支撑位和阻力位
        recent_low = data.iloc[-20:].min()
        recent_high = data.iloc[-20:].max()
        support_level = recent_low / data.iloc[-1]
        resistance_level = recent_high / data.iloc[-1]
        
        return [
            rsi,
            macd / data.iloc[-1],
            signal / data.iloc[-1],
            histogram / data.iloc[-1],
            price_change_1d,
            price_change_5d,
            price_change_10d,
            price_change_20d,
            volatility,
            price_range,
            short_term_trend,
            medium_term_trend,
            momentum,
            bollinger_width,
            bollinger_position,
            support_level,
            resistance_level,
            ema10 / ema30,
            ema30 / ema60,
            data.iloc[-1] / data.iloc[-20],
            data.iloc[-10] / data.iloc[-20],
            len(data) / 100,  # 数据长度归一化
            volatility * 100,  # 波动率放大
            price_range * 100,  # 价格范围放大
            rsi / 50  # RSI归一化
        ]
    
    def _label_market_type(self, data: pd.Series) -> str:
        """
        标记市场类型
        
        Args:
            data: 价格数据
            
        Returns:
            市场类型
        """
        if len(data) < 20:
            return 'range_bound'
        
        # 计算趋势强度
        ema10 = data.ewm(span=10).mean().iloc[-1]
        ema30 = data.ewm(span=30).mean().iloc[-1]
        ema60 = data.ewm(span=60).mean().iloc[-1]
        trend_strength = (ema10 - ema60) / ema60
        
        # 计算价格范围
        recent_data = data.iloc[-20:]
        price_range = (recent_data.max() - recent_data.min()) / recent_data.mean()
        
        # 计算波动率
        volatility = data.iloc[-20:].pct_change().std()
        
        # 确定市场类型
        if volatility > 0.02:
            return 'volatile'
        elif trend_strength < -0.02:
            return 'trending_down'
        elif trend_strength > 0.02:
            return 'trending_up'
        elif price_range < 0.04:
            return 'range_bound'
        elif price_range > 0.08:
            if trend_strength > 0:
                return 'trending_up'
            else:
                return 'trending_down'
        else:
            if abs(trend_strength) > 0.01:
                if trend_strength > 0:
                    return 'trending_up'
                else:
                    return 'trending_down'
            else:
                return 'range_bound'
    
    def _select_optimal_strategy(self, market_type: str, features: List[float]) -> str:
        """
        选择最优策略
        
        Args:
            market_type: 市场类型
            features: 特征列表
            
        Returns:
            策略名称
        """
        # 基于历史表现选择策略
        if market_type == 'range_bound':
            # 横盘市场优先选择 adaptive_range_grid
            return 'adaptive_range_grid'
        elif market_type == 'trending_up':
            # 上涨市场优先选择 adaptive_grid
            return 'adaptive_grid'
        elif market_type == 'trending_down':
            # 下跌市场优先选择 optimized_downward_reversal
            return 'optimized_downward_reversal'
        else:  # volatile
            # 波动市场优先选择 enhanced_grid
            return 'enhanced_grid'
    
    def _get_strategy_instance(self, strategy_name: str) -> any:
        """
        获取策略实例
        
        Args:
            strategy_name: 策略名称
            
        Returns:
            策略实例
        """
        if strategy_name == 'adaptive_range_grid':
            return self.range_strategy
        elif strategy_name == 'adaptive_grid':
            return self.adaptive_strategy
        elif strategy_name == 'enhanced_grid':
            return self.enhanced_strategy
        elif strategy_name == 'optimized_downward_reversal':
            return self.downward_strategy
        else:
            return self.adaptive_strategy
    
    def _train_models(self):
        """
        训练机器学习模型
        """
        # 训练市场类型分类模型
        if len(self.market_data) >= 100:
            # 准备训练数据
            X = np.array(self.market_data)
            y = np.array([self.market_types.index(label) for label in self.market_labels])
            
            # 标准化特征
            X_scaled = self.scaler.fit_transform(X)
            
            # 训练模型
            self.market_classifier.fit(X_scaled, y)
        
        # 训练策略选择模型
        if len(self.strategy_data) >= 100:
            # 准备训练数据
            X = np.array(self.strategy_data)
            y = np.array(self.strategy_labels)
            
            # 标准化特征
            X_scaled = self.scaler.fit_transform(X)
            
            # 训练模型
            self.strategy_selector.fit(X_scaled, y)
        
        if len(self.market_data) >= 100 or len(self.strategy_data) >= 100:
            self.model_trained = True
            self.model_training_count += 1
    
    def detect_market_type(self, data: pd.Series) -> str:
        """
        检测市场类型（使用机器学习）
        
        Args:
            data: 价格数据
            
        Returns:
            市场类型: 'range_bound', 'trending_up', 'trending_down', 'volatile'
        """
        if len(data) < 20:
            return 'range_bound'
        
        # 提取特征
        features = self._extract_features(data)
        
        # 标记市场类型（用于训练）
        true_label = self._label_market_type(data)
        
        # 收集训练数据
        self.market_data.append(features)
        self.market_labels.append(true_label)
        
        # 定期训练模型
        if len(self.market_data) % 30 == 0:
            self._train_models()
        
        # 使用模型预测市场类型
        if self.model_trained:
            try:
                features_scaled = self.scaler.transform([features])
                prediction = self.market_classifier.predict(features_scaled)[0]
                predicted_type = self.market_types[prediction]
                return predicted_type
            except Exception:
                return true_label
        else:
            return true_label
    
    def set_active(self, active: bool):
        """
        设置策略是否激活
        
        Args:
            active: 是否激活
        """
        self.is_active = active
        self.range_strategy.set_active(active)
        self.adaptive_strategy.set_active(active)
        self.enhanced_strategy.set_active(active)
        self.downward_strategy.set_active(active)
    
    def update_price(self, current_price: float, data: pd.Series = None) -> Dict[str, any]:
        """
        更新价格并执行交易
        
        Args:
            current_price: 当前价格
            data: 价格数据（用于市场类型检测和机器学习）
            
        Returns:
            交易结果
        """
        # 记录价格历史
        self.price_history.append(current_price)
        
        # 检测市场类型
        if data is not None:
            self.last_market_type = self.market_type
            self.market_type = self.detect_market_type(data)
            
            # 提取特征
            features = self._extract_features(data)
            
            # 选择最优策略
            selected_strategy = self._select_optimal_strategy(self.market_type, features)
            
            # 获取策略实例
            new_strategy = self._get_strategy_instance(selected_strategy)
            
            # 切换策略
            if self.current_strategy != new_strategy:
                self.current_strategy = new_strategy
                self.strategy_switch_count += 1
            
            # 记录策略切换
            if self.last_market_type != self.market_type:
                self.market_switch_count += 1
        
        # 执行当前策略的交易
        result = self.current_strategy.update_price(current_price, data)
        
        # 更新整体状态
        self.current_balance = self.current_strategy.current_balance
        self.position = self.current_strategy.position
        self.last_price = current_price
        
        # 记录交易结果
        if result['action'] != 'hold':
            self.total_trades += 1
            if result['action'] == 'sell' and 'reason' in result and result['reason'] != 'stop_loss':
                self.winning_trades += 1
            elif result['action'] == 'sell' and 'reason' in result and result['reason'] == 'stop_loss':
                self.losing_trades += 1
            self.trade_history.append(result['action'])
        
        return result
    
    def get_performance(self) -> Dict[str, float]:
        """
        获取策略性能
        
        Returns:
            性能指标
        """
        win_rate = self.winning_trades / self.total_trades if self.total_trades > 0 else 0
        
        # 获取当前策略的性能
        current_perf = self.current_strategy.get_performance()
        
        # 确定当前策略名称
        current_strategy_name = "adaptive_range_grid" if self.current_strategy == self.range_strategy else \
                               "adaptive_grid" if self.current_strategy == self.adaptive_strategy else \
                               "enhanced_grid" if self.current_strategy == self.enhanced_strategy else \
                               "optimized_downward_reversal"
        
        return {
            "initial_balance": self.initial_balance,
            "current_balance": self.current_balance,
            "return": (self.current_balance - self.initial_balance) / self.initial_balance * 100,
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": win_rate,
            "market_switch_count": self.market_switch_count,
            "strategy_switch_count": self.strategy_switch_count,
            "final_position": self.position,
            "model_training_count": self.model_training_count,
            "model_trained": self.model_trained,
            "current_strategy": current_strategy_name,
            "current_market_type": self.market_type
        }
