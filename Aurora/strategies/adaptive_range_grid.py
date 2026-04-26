#!/usr/bin/env python3
"""
自适应横盘网格交易策略
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Tuple, Optional
from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier
from sklearn.preprocessing import StandardScaler

class AdaptiveRangeGridTrading:
    """
    自适应横盘网格交易策略
    专门针对横盘市场优化，使用机器学习和动态网格调整
    """
    
    def __init__(self, base_price: float, initial_balance: float = 100000):
        """
        初始化自适应横盘网格交易策略
        
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
        self.last_buy_price = base_price  # 上次买入价格
        self.last_sell_price = base_price  # 上次卖出价格
        self.entry_price = 0  # 入场价格
        self.consecutive_holds = 0  # 连续不交易次数
        
        # 网格交易参数
        self.grid_levels = 50  # 网格层数（增加层数以适应横盘市场）
        self.grid_spacing = 0.001  # 初始网格间距（横盘市场使用较小的网格间距）
        self.grids = self._create_grids()
        self.last_grid_index = self.grid_levels  # 初始在中间网格
        
        # 风险控制参数
        self.stop_loss_threshold = 0.015  # 1.5%止损
        self.take_profit_threshold = 0.02  # 2%止盈
        self.max_position_percentage = 0.85  # 最大持仓比例（横盘市场可以更高）
        self.reserve_balance_percentage = 0.15  # 保留资金比例（横盘市场可以更低）
        
        # 交易统计
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        
        # 市场类型
        self.market_type = 'range_bound'
        self.market_types = ['range_bound', 'trending_up', 'trending_down']
        
        # 技术指标参数
        self.rsi_period = 14  # RSI周期
        self.macd_fast = 12  # MACD快速周期
        self.macd_slow = 26  # MACD慢速周期
        self.macd_signal = 9  # MACD信号周期
        self.bollinger_period = 20  # 布林带周期
        self.bollinger_std = 2  # 布林带标准差
        self.keltner_period = 20  # 凯尔特纳通道周期
        self.keltner_multiplier = 2  # 凯尔特纳通道乘数
        
        # 机器学习模型
        self.price_predictor = RandomForestRegressor(n_estimators=100, random_state=42)
        self.grid_optimizer = RandomForestRegressor(n_estimators=100, random_state=42)
        self.market_classifier = RandomForestClassifier(n_estimators=100, random_state=42)
        self.scaler = StandardScaler()
        self.model_trained = False
        
        # 训练数据
        self.price_data = []
        self.price_labels = []
        self.grid_data = []
        self.grid_labels = []
        self.market_data = []
        self.market_labels = []
        self.model_training_count = 0
        
        # 性能跟踪
        self.trade_history = []
        self.profit_history = []
        self.grid_adjustment_count = 0
        
        # 横盘市场特定参数
        self.min_grid_spacing = 0.0005  # 最小网格间距
        self.max_grid_spacing = 0.002  # 最大网格间距
        self.min_reserve_percentage = 0.1  # 最小保留资金比例
        self.max_reserve_percentage = 0.2  # 最大保留资金比例
        
        # 高频交易参数
        self.min_trade_amount = 50  # 最小交易金额
        self.max_trade_amount = 2000  # 最大交易金额
        self.trade_frequency = 0  # 交易频率计数
        self.max_trade_frequency = 5  # 最大交易频率
        
        # 趋势识别参数
        self.short_term_period = 5  # 短期趋势周期
        self.medium_term_period = 15  # 中期趋势周期
        
    def _create_grids(self) -> List[float]:
        """
        创建网格价格水平
        
        Returns:
            网格价格列表
        """
        grids = []
        for i in range(-self.grid_levels, self.grid_levels + 1):
            price = self.base_price * (1 + self.grid_spacing) ** i
            grids.append(price)
        return sorted(grids)
    
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
    
    def _calculate_keltner_channels(self, data: pd.Series) -> Tuple[float, float, float]:
        """
        计算凯尔特纳通道
        
        Args:
            data: 价格数据
            
        Returns:
            上轨, 中轨, 下轨
        """
        if len(data) < self.keltner_period:
            return data.iloc[-1] * 1.05, data.iloc[-1], data.iloc[-1] * 0.95  # 默认值
        
        ma = data.rolling(window=self.keltner_period).mean().iloc[-1]
        atr = data.rolling(window=self.keltner_period).apply(lambda x: np.mean(np.abs(np.diff(x))), raw=True).iloc[-1]
        if atr == 0:
            atr = 0.01  # 避免除零错误
        upper = ma + (atr * self.keltner_multiplier)
        lower = ma - (atr * self.keltner_multiplier)
        
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
        
        # 计算凯尔特纳通道
        keltner_upper, keltner_middle, keltner_lower = self._calculate_keltner_channels(data)
        
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
        ema5 = data.ewm(span=5).mean().iloc[-1]
        ema10 = data.ewm(span=10).mean().iloc[-1]
        ema20 = data.ewm(span=20).mean().iloc[-1]
        ema50 = data.ewm(span=50).mean().iloc[-1]
        
        # 计算趋势强度
        short_term_trend = (ema5 - ema10) / ema10
        medium_term_trend = (ema10 - ema20) / ema20
        long_term_trend = (ema20 - ema50) / ema50
        
        # 计算价格动量
        momentum = data.iloc[-1] / data.iloc[-10] if len(data) > 9 else 1
        
        # 计算支撑位和阻力位
        recent_low = data.iloc[-20:].min()
        recent_high = data.iloc[-20:].max()
        support_level = recent_low / data.iloc[-1]
        resistance_level = recent_high / data.iloc[-1]
        
        # 计算布林带宽度
        bollinger_width = (upper_band - lower_band) / middle_band
        
        # 计算价格在布林带中的位置
        bollinger_position = (data.iloc[-1] - lower_band) / (upper_band - lower_band) if upper_band > lower_band else 0.5
        
        # 计算凯尔特纳通道宽度
        keltner_width = (keltner_upper - keltner_lower) / keltner_middle
        
        # 计算价格在凯尔特纳通道中的位置
        keltner_position = (data.iloc[-1] - keltner_lower) / (keltner_upper - keltner_lower) if keltner_upper > keltner_lower else 0.5
        
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
            long_term_trend,
            momentum,
            support_level,
            resistance_level,
            bollinger_width,
            bollinger_position,
            keltner_width,
            keltner_position,
            ema5 / ema10,
            ema10 / ema20,
            ema20 / ema50,
            data.iloc[-1] / data.iloc[-20],
            len(data) / 100  # 数据长度归一化
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
        
        # 确定市场类型
        if trend_strength < -0.02:
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
    
    def _predict_price_movement(self, data: pd.Series) -> float:
        """
        预测价格走势
        
        Args:
            data: 价格数据
            
        Returns:
            预测的价格变化率
        """
        if len(data) < 20:
            return 0
        
        # 提取特征
        features = self._extract_features(data)
        
        # 计算目标变量（未来5天的价格变化率）
        if len(data) >= 25:
            target = (data.iloc[-1] - data.iloc[-6]) / data.iloc[-6]
        else:
            target = 0
        
        # 收集训练数据
        self.price_data.append(features)
        self.price_labels.append(target)
        
        # 定期训练模型
        if len(self.price_data) % 30 == 0 and len(self.price_data) >= 100:
            self._train_models()
        
        # 使用模型预测价格走势
        if self.model_trained:
            try:
                features_scaled = self.scaler.transform([features])
                prediction = self.price_predictor.predict(features_scaled)[0]
                return prediction
            except Exception:
                return 0
        else:
            return target
    
    def _optimize_grid_spacing(self, data: pd.Series) -> float:
        """
        优化网格间距
        
        Args:
            data: 价格数据
            
        Returns:
            优化后的网格间距
        """
        if len(data) < 20:
            return self.grid_spacing
        
        # 提取特征
        features = self._extract_features(data)
        
        # 计算历史波动率
        volatility = data.iloc[-20:].pct_change().std()
        
        # 计算价格范围
        price_range = (data.iloc[-20:].max() - data.iloc[-20:].min()) / data.iloc[-20:].mean()
        
        # 基于波动率和价格范围计算网格间距
        optimal_spacing = max(self.min_grid_spacing, min(self.max_grid_spacing, volatility * 1.2))
        
        # 收集训练数据
        self.grid_data.append(features)
        self.grid_labels.append(optimal_spacing)
        
        # 定期训练模型
        if len(self.grid_data) % 30 == 0 and len(self.grid_data) >= 100:
            self._train_models()
        
        # 使用模型预测最优网格间距
        if self.model_trained:
            try:
                features_scaled = self.scaler.transform([features])
                predicted_spacing = self.grid_optimizer.predict(features_scaled)[0]
                # 确保预测值在合理范围内
                predicted_spacing = max(self.min_grid_spacing, min(self.max_grid_spacing, predicted_spacing))
                return predicted_spacing
            except Exception:
                return optimal_spacing
        else:
            return optimal_spacing
    
    def _train_models(self):
        """
        训练机器学习模型
        """
        # 训练价格预测模型
        if len(self.price_data) >= 100:
            # 准备训练数据
            X = np.array(self.price_data)
            y = np.array(self.price_labels)
            
            # 标准化特征
            X_scaled = self.scaler.fit_transform(X)
            
            # 训练模型
            self.price_predictor.fit(X_scaled, y)
        
        # 训练网格优化模型
        if len(self.grid_data) >= 100:
            # 准备训练数据
            X = np.array(self.grid_data)
            y = np.array(self.grid_labels)
            
            # 标准化特征
            X_scaled = self.scaler.fit_transform(X)
            
            # 训练模型
            self.grid_optimizer.fit(X_scaled, y)
        
        # 训练市场类型分类模型
        if len(self.market_data) >= 100:
            # 准备训练数据
            X = np.array(self.market_data)
            y = np.array([self.market_types.index(label) for label in self.market_labels])
            
            # 标准化特征
            X_scaled = self.scaler.fit_transform(X)
            
            # 训练模型
            self.market_classifier.fit(X_scaled, y)
        
        if len(self.price_data) >= 100 or len(self.grid_data) >= 100 or len(self.market_data) >= 100:
            self.model_trained = True
            self.model_training_count += 1
    
    def detect_market_type(self, data: pd.Series) -> str:
        """
        检测市场类型（使用机器学习）
        
        Args:
            data: 价格数据
            
        Returns:
            市场类型: 'range_bound', 'trending_up', 'trending_down'
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
            self.market_type = self.detect_market_type(data)
            
            # 只有在横盘市场才使用此策略
            if self.market_type != 'range_bound':
                return {"action": "hold", "balance": self.current_balance, "position": self.position}
            
            # 使用机器学习优化网格间距
            optimal_spacing = self._optimize_grid_spacing(data)
            if abs(optimal_spacing - self.grid_spacing) > 0.0001:
                self.grid_spacing = optimal_spacing
                self.grids = self._create_grids()
                self.grid_adjustment_count += 1
        
        # 计算价格变化
        price_change = (current_price - self.last_price) / self.last_price if self.last_price > 0 else 0
        
        # 止损检查：如果持仓亏损超过止损阈值，自动止损
        if self.position > 0 and self.entry_price > 0:
            loss_ratio = (current_price - self.entry_price) / self.entry_price
            if loss_ratio < -self.stop_loss_threshold:
                # 止损卖出
                revenue = self.position * current_price
                self.current_balance += revenue
                quantity = self.position
                self.position = 0
                self.entry_price = 0
                self.last_price = current_price
                self.total_trades += 1
                self.losing_trades += 1
                self.trade_history.append("stop_loss")
                self.profit_history.append(revenue - quantity * self.entry_price)
                return {
                    "action": "sell",
                    "quantity": quantity,
                    "price": current_price,
                    "balance": self.current_balance,
                    "position": self.position,
                    "reason": "stop_loss"
                }
        
        # 止盈检查：如果持仓盈利超过止盈阈值，自动止盈
        if self.position > 0 and self.entry_price > 0:
            profit_ratio = (current_price - self.entry_price) / self.entry_price
            if profit_ratio > self.take_profit_threshold:
                # 止盈卖出全部
                revenue = self.position * current_price
                self.current_balance += revenue
                quantity = self.position
                self.position = 0
                self.entry_price = 0
                self.last_price = current_price
                self.total_trades += 1
                self.winning_trades += 1
                self.trade_history.append("take_profit")
                self.profit_history.append(revenue - quantity * self.entry_price)
                return {
                    "action": "sell",
                    "quantity": quantity,
                    "price": current_price,
                    "balance": self.current_balance,
                    "position": self.position,
                    "reason": "take_profit"
                }
        
        # 计算可用资金（保留reserve_balance_percentage作为接盘资金）
        available_balance = self.current_balance * (1 - self.reserve_balance_percentage)
        
        # 计算最大持仓限制
        max_position = (self.initial_balance * self.max_position_percentage) / current_price
        
        # 找到当前价格所在的网格区间
        current_grid_index = None
        for i in range(len(self.grids) - 1):
            if self.grids[i] <= current_price < self.grids[i + 1]:
                current_grid_index = i
                break
        
        if current_grid_index is None:
            # 价格超出网格范围，重新计算网格
            self.base_price = current_price
            self.grids = self._create_grids()
            for i in range(len(self.grids) - 1):
                if self.grids[i] <= current_price < self.grids[i + 1]:
                    current_grid_index = i
                    break
            if current_grid_index is None:
                return {"action": "hold", "balance": self.current_balance, "position": self.position}
        
        # 网格交易核心逻辑
        grid_change = current_grid_index - self.last_grid_index
        
        # 预测价格走势
        price_prediction = 0
        if data is not None:
            price_prediction = self._predict_price_movement(data)
        
        # 横盘市场的高频交易策略
        if grid_change < 0 and self.position < max_position:
            # 价格下跌到更低网格 -> 买入（低买）
            # 计算买入金额：基于网格变化、可用资金和价格预测
            buy_amount = min(abs(grid_change) * 300, available_balance * 0.1, self.max_trade_amount * 0.8)
            if buy_amount > self.min_trade_amount:
                buy_quantity = buy_amount / current_price
                if buy_quantity > 0.01:
                    self.position += buy_quantity
                    self.current_balance -= buy_amount
                    if self.entry_price == 0:
                        self.entry_price = current_price
                    self.last_buy_price = current_price
                    self.last_grid_index = current_grid_index
                    self.last_price = current_price
                    self.trade_history.append("buy")
                    self.trade_frequency += 1
                    return {
                        "action": "buy",
                        "quantity": buy_quantity,
                        "price": current_price,
                        "balance": self.current_balance,
                        "position": self.position,
                        "reason": "grid_buy"
                    }
        elif grid_change > 0 and self.position > 0:
            # 价格上涨到更高网格 -> 卖出（高卖）
            # 计算卖出数量：基于网格变化和当前持仓
            sell_quantity = min(abs(grid_change) * 300 / current_price, self.position)
            if sell_quantity > 0.01:
                sell_amount = sell_quantity * current_price
                # 卖出条件：价格高于买入价格，确保覆盖交易成本
                if current_price > self.last_buy_price * 1.001:  # 确保有足够盈利覆盖交易成本
                    self.position -= sell_quantity
                    self.current_balance += sell_amount
                    self.last_sell_price = current_price
                    self.last_grid_index = current_grid_index
                    self.last_price = current_price
                    self.total_trades += 1
                    self.winning_trades += 1
                    profit = sell_amount - sell_quantity * self.last_buy_price
                    self.profit_history.append(profit)
                    self.trade_history.append("sell")
                    self.trade_frequency += 1
                    return {
                        "action": "sell",
                        "quantity": sell_quantity,
                        "price": current_price,
                        "balance": self.current_balance,
                        "position": self.position,
                        "reason": "grid_sell"
                    }
        
        # 横盘市场的额外交易策略：基于价格动量和预测
        if len(self.price_history) > 5 and data is not None:
            recent_prices = self.price_history[-5:]
            price_range = max(recent_prices) - min(recent_prices)
            price_mean = np.mean(recent_prices)
            
            # 计算短期趋势
            short_term_trend = (recent_prices[-1] - recent_prices[0]) / recent_prices[0]
            
            # 如果价格在小范围内波动，执行高频交易
            if price_range / price_mean < 0.01 and available_balance > self.min_trade_amount * 2:
                if current_price < price_mean * 0.998 and self.position < max_position:
                    # 价格低于均值，买入
                    buy_amount = min(available_balance * 0.1, self.max_trade_amount * 0.6)
                    if buy_amount > self.min_trade_amount:
                        buy_quantity = buy_amount / current_price
                        if buy_quantity > 0.01:
                            # 预测价格上涨时增加买入金额
                            if price_prediction > 0:
                                buy_amount = min(buy_amount * 1.1, available_balance * 0.15)
                                buy_quantity = buy_amount / current_price
                            
                            self.position += buy_quantity
                            self.current_balance -= buy_amount
                            if self.entry_price == 0:
                                self.entry_price = current_price
                            self.last_buy_price = current_price
                            self.last_price = current_price
                            self.trade_history.append("mean_reversion_buy")
                            self.trade_frequency += 1
                            return {
                                "action": "buy",
                                "quantity": buy_quantity,
                                "price": current_price,
                                "balance": self.current_balance,
                                "position": self.position,
                                "reason": "mean_reversion_buy"
                            }
                elif current_price > price_mean * 1.002 and self.position > 0:
                    # 价格高于均值，卖出
                    sell_quantity = min(self.position * 0.2, self.max_trade_amount * 0.6 / current_price)
                    if sell_quantity > 0.01:
                        # 预测价格下跌时增加卖出数量
                        if price_prediction < 0:
                            sell_quantity = min(sell_quantity * 1.1, self.position * 0.25)
                        
                        sell_amount = sell_quantity * current_price
                        # 确保卖出价格高于买入价格，覆盖交易成本
                        if current_price > self.last_buy_price * 1.001:
                            self.position -= sell_quantity
                            self.current_balance += sell_amount
                            self.last_sell_price = current_price
                            self.last_price = current_price
                            self.total_trades += 1
                            self.winning_trades += 1
                            profit = sell_amount - sell_quantity * self.last_buy_price
                            self.profit_history.append(profit)
                            self.trade_history.append("mean_reversion_sell")
                            self.trade_frequency += 1
                            return {
                                "action": "sell",
                                "quantity": sell_quantity,
                                "price": current_price,
                                "balance": self.current_balance,
                                "position": self.position,
                                "reason": "mean_reversion_sell"
                            }
        
        # 重置交易频率计数
        if self.trade_frequency >= self.max_trade_frequency:
            self.trade_frequency = 0
        
        # 更新但不交易
        self.consecutive_holds += 1
        self.last_grid_index = current_grid_index
        self.last_price = current_price
        return {"action": "hold", "balance": self.current_balance, "position": self.position}
    
    def get_performance(self) -> Dict[str, float]:
        """
        获取策略性能
        
        Returns:
            性能指标
        """
        win_rate = self.winning_trades / self.total_trades if self.total_trades > 0 else 0
        avg_profit = np.mean(self.profit_history) if self.profit_history else 0
        total_profit = sum(self.profit_history) if self.profit_history else 0
        
        return {
            "initial_balance": self.initial_balance,
            "current_balance": self.current_balance,
            "return": (self.current_balance - self.initial_balance) / self.initial_balance * 100,
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": win_rate,
            "avg_profit_per_trade": avg_profit,
            "total_profit": total_profit,
            "grid_adjustments": self.grid_adjustment_count,
            "final_position": self.position,
            "model_training_count": self.model_training_count,
            "model_trained": self.model_trained
        }
