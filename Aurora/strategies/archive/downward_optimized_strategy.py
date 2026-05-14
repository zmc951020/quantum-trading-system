#!/usr/bin/env python3
"""
下跌市场优化策略
专门针对下跌市场的优化策略
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Tuple, Optional
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler

class DownwardOptimizedStrategy:
    """
    下跌市场优化策略
    专门针对下跌市场的优化策略
    """
    
    def __init__(self, base_price: float, initial_balance: float = 100000):
        """
        初始化下跌市场优化策略
        
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
        
        # 市场类型
        self.market_type = 'trending_down'
        self.last_market_type = 'trending_down'
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
        self.reversal_classifier = RandomForestClassifier(n_estimators=200, random_state=42)
        self.scaler = StandardScaler()
        self.model_trained = False
        
        # 训练数据
        self.market_data = []
        self.market_labels = []
        self.reversal_data = []
        self.reversal_labels = []
        self.model_training_count = 0
        
        # 性能跟踪
        self.trade_history = []
        self.profit_history = []
        self.market_switch_count = 0
        
        # 资金管理参数
        self.max_position_percentage = 0.8  # 最大持仓比例
        self.reserve_balance_percentage = 0.2  # 保留资金比例
        self.min_trade_amount = 1000  # 最小交易金额
        self.max_trade_amount = 15000  # 最大交易金额
        self.position_size = 0.15  # 单次交易仓位比例
        
        # 交易参数
        self.take_profit_threshold = 0.015  # 止盈阈值，下跌市场小盈利就出
        self.stop_loss_threshold = 0.01  # 止损阈值，下跌市场严格止损
        self.min_profit_threshold = 0.003  # 最小盈利阈值
        
        # 下跌市场特定参数
        self.downward_trend_count = 0  # 下跌趋势计数
        self.max_downward_trend_count = 5  # 最大下跌趋势计数
        self.downward_buy_levels = []  # 下跌买入点位
        self.downward_buy_amounts = []  # 对应买入金额
        self.downward_buy_executed = []  # 已执行的买入点位
        
        # 反转策略参数
        self.reversal_threshold = 0.01  # 反转阈值
        self.buy_count = 0  # 买入次数
        self.max_buy_count = 3  # 最大买入次数
        
        # 初始化下跌买入点位
        self._init_downward_buy_levels()
    
    def _init_downward_buy_levels(self):
        """
        初始化下跌买入点位
        """
        # 定义下跌买入点位（相对于基准价格的百分比）
        levels = [0.97, 0.94, 0.91, 0.88, 0.85, 0.82, 0.79, 0.76, 0.73, 0.70]
        for level in levels:
            price = self.base_price * level
            self.downward_buy_levels.append(price)
            # 价格越低，买入金额越大
            amount_ratio = (1 - level) * 20  # 价格越低，买入比例越高
            max_amount = self.initial_balance * 0.2  # 单次最大买入金额
            amount = min(max_amount, self.initial_balance * 0.05 * amount_ratio)
            self.downward_buy_amounts.append(amount)
            self.downward_buy_executed.append(False)
        
        # 按价格从高到低排序
        sorted_pairs = sorted(zip(self.downward_buy_levels, self.downward_buy_amounts, self.downward_buy_executed), reverse=True)
        self.downward_buy_levels, self.downward_buy_amounts, self.downward_buy_executed = zip(*sorted_pairs)
        self.downward_buy_levels = list(self.downward_buy_levels)
        self.downward_buy_amounts = list(self.downward_buy_amounts)
        self.downward_buy_executed = list(self.downward_buy_executed)
    
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
            return 'trending_down'
        
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
        if volatility > 0.025:
            return 'volatile'
        elif trend_strength < -0.01:
            return 'trending_down'
        elif trend_strength > 0.01:
            return 'trending_up'
        elif price_range < 0.03:
            return 'range_bound'
        elif price_range > 0.07:
            if trend_strength > 0:
                return 'trending_up'
            else:
                return 'trending_down'
        else:
            if abs(trend_strength) > 0.005:
                if trend_strength > 0:
                    return 'trending_up'
                else:
                    return 'trending_down'
            else:
                return 'range_bound'
    
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
        
        # 计算价格变化
        price_change = (data.iloc[-1] - data.iloc[-2]) / data.iloc[-2] if len(data) > 1 else 0
        
        # 检测反转信号
        # 1. RSI低于35（超卖）
        # 2. MACD柱状图由负转正或 histogram > 0
        # 3. 价格触及布林带下轨或在支撑位附近
        # 4. 价格出现上涨趋势
        
        reversal = False
        
        # 超卖条件
        if rsi < 35:
            # MACD金叉或柱状图为正
            if (histogram > 0 and macd > signal) or histogram > 0:
                # 价格触及布林带下轨
                if data.iloc[-1] < lower_band * 1.01:
                    # 价格出现上涨趋势
                    if price_change > 0:
                        reversal = True
        
        return reversal
    
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
        
        # 训练反转信号检测模型
        if len(self.reversal_data) >= 100:
            # 准备训练数据
            X = np.array(self.reversal_data)
            y = np.array(self.reversal_labels)
            
            # 标准化特征
            X_scaled = self.scaler.fit_transform(X)
            
            # 训练模型
            self.reversal_classifier.fit(X_scaled, y)
        
        if len(self.market_data) >= 100 or len(self.reversal_data) >= 100:
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
            return 'trending_down'
        
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
        self.reversal_data.append(features)
        self.reversal_labels.append(true_label)
        
        # 定期训练模型
        if len(self.reversal_data) % 30 == 0:
            self._train_models()
        
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
    
    def set_active(self, active: bool):
        """
        设置策略是否激活
        
        Args:
            active: 是否激活
        """
        self.is_active = active
    
    def _calculate_position_size(self, current_price: float, amount: float = None) -> float:
        """
        计算仓位大小
        
        Args:
            current_price: 当前价格
            amount: 交易金额
            
        Returns:
            仓位大小
        """
        # 计算可用资金
        available_balance = self.current_balance * (1 - self.reserve_balance_percentage)
        
        # 计算最大持仓限制
        max_position = (self.initial_balance * self.max_position_percentage) / current_price
        
        # 计算本次交易的仓位大小
        if amount:
            position_size = amount / current_price
        else:
            position_size = min(
                available_balance * self.position_size / current_price,
                max_position - abs(self.position)
            )
        
        return max(position_size, 0.01)  # 确保最小仓位
    
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
            
            # 记录市场切换
            if self.last_market_type != self.market_type:
                self.market_switch_count += 1
        
        # 止损检查
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
        
        # 止盈检查
        if self.position > 0 and self.entry_price > 0:
            profit_ratio = (current_price - self.entry_price) / self.entry_price
            if profit_ratio > self.take_profit_threshold:
                # 止盈卖出
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
        
        # 下跌市场：使用反转策略
        if self.market_type == 'trending_down' and data is not None and len(data) > 30:
            # 检测反转信号并买入
            if self.position == 0 and self.buy_count < self.max_buy_count:
                if self._detect_reversal(data):
                    # 检测到反转信号，买入
                    position_size = self._calculate_position_size(current_price)
                    if position_size > 0.01:
                        buy_amount = position_size * current_price
                        if buy_amount >= self.min_trade_amount:
                            self.position = position_size
                            self.current_balance -= buy_amount
                            self.entry_price = current_price
                            self.last_price = current_price
                            self.buy_count += 1
                            self.total_trades += 1
                            return {
                                "action": "buy",
                                "quantity": position_size,
                                "price": current_price,
                                "balance": self.current_balance,
                                "position": self.position,
                                "reason": "reversal_buy"
                            }
            
            # 价格反弹卖出
            if self.position > 0 and current_price > self.entry_price * 1.008:
                # 价格反弹0.8%以上，卖出
                revenue = self.position * current_price
                self.current_balance += revenue
                quantity = self.position
                self.position = 0
                self.entry_price = 0
                self.last_price = current_price
                self.total_trades += 1
                if current_price > self.entry_price:
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
            
            # 额外的买入条件：下跌市场中的超跌反弹
            if self.position == 0 and self.buy_count < self.max_buy_count:
                # 计算最近的价格变化
                recent_prices = data.iloc[-10:]
                recent_change = (recent_prices.iloc[-1] - recent_prices.iloc[0]) / recent_prices.iloc[0]
                
                # 如果最近下跌超过4%，并且当前价格出现上涨
                if recent_change < -0.04 and (current_price - self.last_price) / self.last_price > 0.005:
                    position_size = self._calculate_position_size(current_price)
                    if position_size > 0.01:
                        buy_amount = position_size * current_price
                        if buy_amount >= self.min_trade_amount:
                            self.position = position_size
                            self.current_balance -= buy_amount
                            self.entry_price = current_price
                            self.last_price = current_price
                            self.buy_count += 1
                            self.total_trades += 1
                            return {
                                "action": "buy",
                                "quantity": position_size,
                                "price": current_price,
                                "balance": self.current_balance,
                                "position": self.position,
                                "reason": "oversold_bounce_buy"
                            }
        
        # 下跌买入点位检查
        for i, (buy_level, buy_amount, executed) in enumerate(zip(self.downward_buy_levels, self.downward_buy_amounts, self.downward_buy_executed)):
            if not executed and current_price <= buy_level:
                # 达到买入点位，执行买入
                position_size = self._calculate_position_size(current_price, buy_amount)
                if position_size > 0.01:
                    self.position = position_size
                    self.current_balance -= buy_amount
                    self.entry_price = current_price
                    self.last_price = current_price
                    self.downward_buy_executed[i] = True
                    self.total_trades += 1
                    return {
                        "action": "buy",
                        "quantity": position_size,
                        "price": current_price,
                        "balance": self.current_balance,
                        "position": self.position,
                        "reason": "downward_buy"
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
            "market_switch_count": self.market_switch_count,
            "final_position": self.position,
            "model_training_count": self.model_training_count,
            "model_trained": self.model_trained,
            "current_market_type": self.market_type
        }
