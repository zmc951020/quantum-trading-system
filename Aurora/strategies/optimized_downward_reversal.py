#!/usr/bin/env python3
"""
优化的下跌市场反转网格交易策略
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Tuple, Optional
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler

class OptimizedDownwardReversalGrid:
    """
    优化的下跌市场反转网格交易策略
    """
    
    def __init__(self, base_price: float, initial_balance: float = 100000):
        """
        初始化优化的下跌市场反转网格交易策略
        
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
        self.entry_price = 0  # 入场价格
        
        # 交易统计
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        
        # 风险控制参数
        self.stop_loss_threshold = 0.01  # 1%止损（更严格）
        self.take_profit_threshold = 0.025  # 2.5%止盈
        self.max_position_percentage = 0.3  # 最大持仓比例（更低）
        self.reserve_balance_percentage = 0.6  # 保留资金比例（更高）
        
        # 反转策略参数
        self.reversal_threshold = 0.015  # 反转阈值（1.5%）
        self.min_buy_amount = 500  # 最小买入金额
        self.max_buy_amount = 3000  # 最大买入金额
        self.buy_count = 0  # 买入次数
        self.max_buy_count = 5  # 最大买入次数
        
        # 历史最高价格
        self.highest_price = base_price
        self.last_buy_price = 0  # 上次买入价格
        self.profit_target = 0  # 盈利目标价格
        
        # 技术指标参数（分钟级）
        self.rsi_period = 14  # RSI周期
        self.macd_fast = 12  # MACD快速周期
        self.macd_slow = 26  # MACD慢速周期
        self.macd_signal = 9  # MACD信号周期
        self.bollinger_period = 20  # 布林带周期
        self.bollinger_std = 2  # 布林带标准差
        
        # 支撑位和压力位
        self.support_levels = []  # 支撑位
        self.resistance_levels = []  # 压力位
        self.pivot_points = []  # 枢轴点
        
        # 机器学习模型
        self.reversal_classifier = RandomForestClassifier(n_estimators=100, random_state=42)
        self.scaler = StandardScaler()
        self.model_trained = False
        self.model_data = []
        self.model_labels = []
        self.model_training_count = 0
        
        # 市场类型
        self.market_type = 'trending_down'
    
    def set_active(self, active: bool):
        """
        设置策略是否激活
        
        Args:
            active: 是否激活
        """
        self.is_active = active
    
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
    
    def _calculate_pivot_points(self, data: pd.Series) -> List[float]:
        """
        计算枢轴点
        
        Args:
            data: 价格数据
            
        Returns:
            枢轴点列表
        """
        if len(data) < 2:
            return [self.base_price]
        
        # 计算最近的最高价、最低价和收盘价
        high = data.max()
        low = data.min()
        close = data.iloc[-1]
        
        # 计算枢轴点
        pivot = (high + low + close) / 3
        r1 = 2 * pivot - low
        r2 = pivot + (high - low)
        r3 = high + 2 * (pivot - low)
        s1 = 2 * pivot - high
        s2 = pivot - (high - low)
        s3 = low - 2 * (high - pivot)
        
        return [r3, r2, r1, pivot, s1, s2, s3]
    
    def _detect_support_resistance(self, data: pd.Series) -> Tuple[List[float], List[float]]:
        """
        检测支撑位和压力位
        
        Args:
            data: 价格数据
            
        Returns:
            支撑位列表, 压力位列表
        """
        if len(data) < 20:
            return [data.min()], [data.max()]
        
        # 使用枢轴点作为支撑位和压力位
        pivot_points = self._calculate_pivot_points(data)
        
        # 支撑位：枢轴点下方的点
        support_levels = [p for p in pivot_points if p < data.iloc[-1]]
        
        # 压力位：枢轴点上方的点
        resistance_levels = [p for p in pivot_points if p > data.iloc[-1]]
        
        # 按价格排序
        support_levels.sort(reverse=True)  # 支撑位从高到低
        resistance_levels.sort()  # 压力位从低到高
        
        return support_levels, resistance_levels
    
    def _extract_features(self, data: pd.Series) -> List[float]:
        """
        提取特征用于反转信号检测
        
        Args:
            data: 价格数据
            
        Returns:
            特征列表
        """
        if len(data) < 20:
            return [0] * 20  # 返回默认特征
        
        # 计算RSI
        rsi = self._calculate_rsi(data)
        
        # 计算MACD
        macd, signal, histogram = self._calculate_macd(data)
        
        # 计算布林带
        upper_band, middle_band, lower_band = self._calculate_bollinger_bands(data)
        
        # 计算价格变化率
        price_change_1m = (data.iloc[-1] - data.iloc[-2]) / data.iloc[-2] if len(data) > 1 else 0
        price_change_5m = (data.iloc[-1] - data.iloc[-6]) / data.iloc[-6] if len(data) > 5 else 0
        price_change_15m = (data.iloc[-1] - data.iloc[-16]) / data.iloc[-16] if len(data) > 15 else 0
        price_change_30m = (data.iloc[-1] - data.iloc[-31]) / data.iloc[-31] if len(data) > 30 else 0
        
        # 计算波动率
        volatility = data.iloc[-20:].pct_change().std()
        
        # 计算价格范围
        price_range = (data.iloc[-20:].max() - data.iloc[-20:].min()) / data.iloc[-20:].mean()
        
        # 计算移动平均线
        ema10 = data.ewm(span=10).mean().iloc[-1]
        ema20 = data.ewm(span=20).mean().iloc[-1]
        ema50 = data.ewm(span=50).mean().iloc[-1]
        
        # 计算趋势强度
        trend_strength = (ema10 - ema50) / ema50
        
        # 计算价格动量
        momentum = data.iloc[-1] / data.iloc[-10] if len(data) > 9 else 1
        
        # 计算支撑位和压力位
        support_levels, resistance_levels = self._detect_support_resistance(data)
        nearest_support = support_levels[0] if support_levels else data.min()
        nearest_resistance = resistance_levels[0] if resistance_levels else data.max()
        support_distance = (data.iloc[-1] - nearest_support) / data.iloc[-1]
        resistance_distance = (nearest_resistance - data.iloc[-1]) / data.iloc[-1]
        
        # 计算布林带位置
        bollinger_position = (data.iloc[-1] - lower_band) / (upper_band - lower_band)
        
        return [
            rsi,
            macd / data.iloc[-1],
            signal / data.iloc[-1],
            histogram / data.iloc[-1],
            price_change_1m,
            price_change_5m,
            price_change_15m,
            price_change_30m,
            volatility,
            price_range,
            trend_strength,
            momentum,
            support_distance,
            resistance_distance,
            bollinger_position,
            ema10 / ema20,
            ema20 / ema50,
            data.iloc[-1] / upper_band,
            data.iloc[-1] / lower_band,
            len(support_levels)
        ]
    
    def _label_reversal(self, data: pd.Series) -> bool:
        """
        标记反转信号
        
        Args:
            data: 价格数据
            
        Returns:
            是否为反转信号
        """
        if len(data) < 30:
            return False
        
        # 计算RSI
        rsi = self._calculate_rsi(data)
        
        # 计算MACD
        macd, signal, histogram = self._calculate_macd(data)
        
        # 计算布林带
        upper_band, middle_band, lower_band = self._calculate_bollinger_bands(data)
        
        # 检测支撑位和压力位
        support_levels, resistance_levels = self._detect_support_resistance(data)
        
        # 计算价格变化
        price_change = (data.iloc[-1] - data.iloc[-2]) / data.iloc[-2] if len(data) > 1 else 0
        
        # 检测反转信号
        # 1. RSI低于40（超卖）
        # 2. MACD柱状图由负转正或 histogram > 0
        # 3. 价格触及布林带下轨或在支撑位附近
        # 4. 价格出现上涨趋势
        
        reversal = False
        
        # 超卖条件
        if rsi < 40:
            # MACD金叉或柱状图为正
            if (histogram > 0 and macd > signal) or histogram > 0:
                # 价格触及布林带下轨或在支撑位附近
                if data.iloc[-1] < lower_band * 1.01 or (support_levels and data.iloc[-1] > support_levels[0] * 0.99 and data.iloc[-1] < support_levels[0] * 1.01):
                    # 价格出现上涨趋势
                    if price_change > 0:
                        reversal = True
        
        # 额外的反转信号检测：价格在支撑位反弹
        if support_levels:
            nearest_support = support_levels[0]
            # 价格跌破支撑位后反弹
            if data.iloc[-1] < nearest_support * 0.99 and price_change > 0.01:
                reversal = True
        
        return reversal
    
    def _train_model(self):
        """
        训练机器学习模型
        """
        if len(self.model_data) < 100:
            return
        
        # 准备训练数据
        X = np.array(self.model_data)
        y = np.array(self.model_labels)
        
        # 标准化特征
        X_scaled = self.scaler.fit_transform(X)
        
        # 训练模型
        self.reversal_classifier.fit(X_scaled, y)
        self.model_trained = True
        self.model_training_count += 1
    
    def _detect_reversal(self, data: pd.Series) -> bool:
        """
        检测反转信号（使用机器学习）
        
        Args:
            data: 价格数据
            
        Returns:
            是否检测到反转信号
        """
        if len(data) < 30:
            return False
        
        # 提取特征
        features = self._extract_features(data)
        
        # 标记反转信号（用于训练）
        true_label = self._label_reversal(data)
        
        # 收集训练数据
        self.model_data.append(features)
        self.model_labels.append(true_label)
        
        # 定期训练模型
        if len(self.model_data) % 30 == 0:
            self._train_model()
        
        # 使用模型预测反转信号
        try:
            if self.model_trained:
                features_scaled = self.scaler.transform([features])
                prediction = self.reversal_classifier.predict(features_scaled)[0]
                return prediction
            else:
                return true_label
        except Exception:
            # 如果模型未训练或出现其他错误，返回真实标签
            return true_label
    
    def update_price(self, current_price: float, data: pd.Series = None) -> Dict[str, any]:
        """
        更新价格并执行交易
        
        Args:
            current_price: 当前价格
            data: 价格数据（用于市场类型检测）
            
        Returns:
            交易结果
        """
        # 记录价格历史
        self.price_history.append(current_price)
        
        # 更新历史最高价格
        if current_price > self.highest_price:
            self.highest_price = current_price
            # 价格创新高，重置买入次数
            self.buy_count = 0
            self.last_buy_price = 0
            self.profit_target = 0
        
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
                self.buy_count = 0  # 重置买入次数
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
                self.buy_count = 0  # 重置买入次数
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
        
        # 检测反转信号并买入
        if data is not None and len(data) > 30 and self.position < max_position and self.buy_count < self.max_buy_count:
            if self._detect_reversal(data):
                # 检测到反转信号，买入
                # 实现金字塔买入策略：价格越低，买入金额越大
                # 计算价格下跌百分比
                price_drop_percentage = (self.highest_price - current_price) / self.highest_price
                # 根据下跌百分比调整买入金额
                base_buy_amount = min(available_balance * 0.3, self.max_buy_amount)
                # 价格下跌越多，买入金额越大
                buy_amount = base_buy_amount * (1 + price_drop_percentage * 2)
                buy_amount = min(buy_amount, available_balance * 0.4, self.max_buy_amount)
                if buy_amount > self.min_buy_amount:
                    buy_quantity = buy_amount / current_price
                    if buy_quantity > 0.01:
                        self.position += buy_quantity
                        self.current_balance -= buy_amount
                        if self.entry_price == 0:
                            self.entry_price = current_price
                        self.last_buy_price = current_price
                        # 设置盈利目标价格（买入价格的2.5%以上）
                        self.profit_target = current_price * (1 + self.take_profit_threshold)
                        self.last_price = current_price
                        self.buy_count += 1
                        return {
                            "action": "buy",
                            "quantity": buy_quantity,
                            "price": current_price,
                            "balance": self.current_balance,
                            "position": self.position,
                            "reason": "reversal_buy"
                        }
        
        # 价格反弹卖出（非反转信号）
        if self.position > 0 and current_price > self.last_buy_price * 1.015:
            # 价格反弹1.5%以上，卖出全部
            revenue = self.position * current_price
            self.current_balance += revenue
            quantity = self.position
            self.position = 0
            self.entry_price = 0
            self.last_price = current_price
            self.total_trades += 1
            # 确保卖出价格高于买入价格
            if current_price > self.last_buy_price:
                self.winning_trades += 1
            else:
                self.losing_trades += 1
            self.buy_count = 0  # 重置买入次数
            return {
                "action": "sell",
                "quantity": quantity,
                "price": current_price,
                "balance": self.current_balance,
                "position": self.position,
                "reason": "bounce_sell"
            }
        
        # 价格跌破支撑位后的反弹买入
        if data is not None and len(data) > 20 and self.position < max_position:
            support_levels, _ = self._detect_support_resistance(data)
            if support_levels:
                nearest_support = support_levels[0]
                # 价格跌破支撑位后反弹
                if current_price < nearest_support * 0.995 and price_change > 0.01:
                    buy_amount = min(available_balance * 0.3, self.max_buy_amount * 0.8)
                    if buy_amount > self.min_buy_amount:
                        buy_quantity = buy_amount / current_price
                        if buy_quantity > 0.01:
                            self.position += buy_quantity
                            self.current_balance -= buy_amount
                            if self.entry_price == 0:
                                self.entry_price = current_price
                            self.last_buy_price = current_price
                            self.profit_target = current_price * (1 + self.take_profit_threshold)
                            self.last_price = current_price
                            self.buy_count += 1
                            return {
                                "action": "buy",
                                "quantity": buy_quantity,
                                "price": current_price,
                                "balance": self.current_balance,
                                "position": self.position,
                                "reason": "support_bounce_buy"
                            }
        
        # 价格突破压力位后的回调买入
        if data is not None and len(data) > 20 and self.position < max_position:
            _, resistance_levels = self._detect_support_resistance(data)
            if resistance_levels:
                nearest_resistance = resistance_levels[0]
                # 价格突破压力位后回调
                if current_price > nearest_resistance * 1.005 and price_change < -0.01:
                    buy_amount = min(available_balance * 0.3, self.max_buy_amount * 0.8)
                    if buy_amount > self.min_buy_amount:
                        buy_quantity = buy_amount / current_price
                        if buy_quantity > 0.01:
                            self.position += buy_quantity
                            self.current_balance -= buy_amount
                            if self.entry_price == 0:
                                self.entry_price = current_price
                            self.last_buy_price = current_price
                            self.profit_target = current_price * (1 + self.take_profit_threshold)
                            self.last_price = current_price
                            self.buy_count += 1
                            return {
                                "action": "buy",
                                "quantity": buy_quantity,
                                "price": current_price,
                                "balance": self.current_balance,
                                "position": self.position,
                                "reason": "resistance_callback_buy"
                            }
        
        # 额外的买入条件：下跌市场中的超跌反弹
        if self.market_type == 'trending_down' and data is not None and len(data) > 10 and self.position < max_position:
            # 计算最近的价格变化
            recent_prices = data.iloc[-10:]
            recent_change = (recent_prices.iloc[-1] - recent_prices.iloc[0]) / recent_prices.iloc[0]
            
            # 如果最近下跌超过5%，并且当前价格出现上涨
            if recent_change < -0.05 and price_change > 0.01:
                buy_amount = min(available_balance * 0.3, self.max_buy_amount)
                if buy_amount > self.min_buy_amount:
                    buy_quantity = buy_amount / current_price
                    if buy_quantity > 0.01:
                        self.position += buy_quantity
                        self.current_balance -= buy_amount
                        if self.entry_price == 0:
                            self.entry_price = current_price
                        self.last_buy_price = current_price
                        self.profit_target = current_price * (1 + self.take_profit_threshold)
                        self.last_price = current_price
                        self.buy_count += 1
                        return {
                            "action": "buy",
                            "quantity": buy_quantity,
                            "price": current_price,
                            "balance": self.current_balance,
                            "position": self.position,
                            "reason": "oversold_bounce_buy"
                        }
        
        # 额外的买入条件：价格创新低后的反弹
        if data is not None and len(data) > 5 and self.position < max_position:
            # 检查是否创近期新低
            recent_low = data.iloc[-5:].min()
            if current_price == recent_low and price_change > 0:
                buy_amount = min(available_balance * 0.3, self.max_buy_amount)
                if buy_amount > self.min_buy_amount:
                    buy_quantity = buy_amount / current_price
                    if buy_quantity > 0.01:
                        self.position += buy_quantity
                        self.current_balance -= buy_amount
                        if self.entry_price == 0:
                            self.entry_price = current_price
                        self.last_buy_price = current_price
                        self.profit_target = current_price * (1 + self.take_profit_threshold)
                        self.last_price = current_price
                        self.buy_count += 1
                        return {
                            "action": "buy",
                            "quantity": buy_quantity,
                            "price": current_price,
                            "balance": self.current_balance,
                            "position": self.position,
                            "reason": "new_low_bounce_buy"
                        }
        
        # 更新但不交易
        self.last_price = current_price
        return {"action": "hold", "balance": self.current_balance, "position": self.position}
    
    def get_performance(self) -> Dict[str, float]:
        """
        获取策略性能
        
        Returns:
            性能指标
        """
        win_rate = self.winning_trades / self.total_trades if self.total_trades > 0 else 0
        return {
            "initial_balance": self.initial_balance,
            "current_balance": self.current_balance,
            "return": (self.current_balance - self.initial_balance) / self.initial_balance * 100,
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": win_rate,
            "final_position": self.position,
            "model_training_count": self.model_training_count,
            "model_trained": self.model_trained
        }
