#!/usr/bin/env python3
"""
资金优化策略
改进资金管理，提高资金周转使用率
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Tuple, Optional
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler

class FundOptimizedStrategy:
    """
    资金优化策略
    改进资金管理，提高资金周转使用率
    """
    
    def __init__(self, base_price: float, initial_balance: float = 100000):
        """
        初始化资金优化策略
        
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
        self.scaler = StandardScaler()
        self.model_trained = False
        
        # 训练数据
        self.market_data = []
        self.market_labels = []
        self.model_training_count = 0
        
        # 性能跟踪
        self.trade_history = []
        self.profit_history = []
        self.market_switch_count = 0
        
        # 资金管理参数
        self.max_position_percentage = 0.9  # 最大持仓比例，提高资金使用率
        self.reserve_balance_percentage = 0.1  # 保留资金比例
        self.min_trade_amount = 500  # 最小交易金额
        self.max_trade_amount = 10000  # 最大交易金额，提高单笔交易规模
        self.position_size = 0.1  # 单次交易仓位比例
        
        # 交易参数
        self.take_profit_threshold = 0.02  # 止盈阈值
        self.stop_loss_threshold = 0.015  # 止损阈值
        self.min_profit_threshold = 0.005  # 最小盈利阈值
        
        # 网格参数
        self.grid_levels = 50  # 网格层数
        self.grid_spacing = 0.005  # 网格间距
        self.grids = self._create_grids()
        self.last_grid_index = self.grid_levels  # 初始在中间网格
    
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
        if volatility > 0.025:
            return 'volatile'
        elif trend_strength < -0.015:
            return 'trending_down'
        elif trend_strength > 0.015:
            return 'trending_up'
        elif price_range < 0.03:
            return 'range_bound'
        elif price_range > 0.07:
            if trend_strength > 0:
                return 'trending_up'
            else:
                return 'trending_down'
        else:
            if abs(trend_strength) > 0.008:
                if trend_strength > 0:
                    return 'trending_up'
                else:
                    return 'trending_down'
            else:
                return 'range_bound'
    
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
        
        if len(self.market_data) >= 100:
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
    
    def _calculate_position_size(self, current_price: float) -> float:
        """
        计算仓位大小
        
        Args:
            current_price: 当前价格
            
        Returns:
            仓位大小
        """
        # 计算可用资金
        available_balance = self.current_balance * (1 - self.reserve_balance_percentage)
        
        # 计算最大持仓限制
        max_position = (self.initial_balance * self.max_position_percentage) / current_price
        
        # 计算本次交易的仓位大小
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
                return {
                    "action": "sell",
                    "quantity": quantity,
                    "price": current_price,
                    "balance": self.current_balance,
                    "position": self.position,
                    "reason": "take_profit"
                }
        
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
        
        # 根据市场类型执行不同的交易策略
        if self.market_type == 'trending_down':
            # 下跌市场：使用反转策略
            if data is not None and len(data) > 30 and self.position == 0:
                # 计算RSI
                rsi = self._calculate_rsi(data)
                
                # 计算MACD
                macd, signal, histogram = self._calculate_macd(data)
                
                # 计算布林带
                upper_band, middle_band, lower_band = self._calculate_bollinger_bands(data)
                
                # 检测反转信号
                if rsi < 35 and histogram > 0 and current_price < lower_band * 1.01:
                    # 检测到反转信号，买入
                    position_size = self._calculate_position_size(current_price)
                    if position_size > 0.01:
                        buy_amount = position_size * current_price
                        if buy_amount >= self.min_trade_amount:
                            self.position = position_size
                            self.current_balance -= buy_amount
                            self.entry_price = current_price
                            self.last_price = current_price
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
            if self.position > 0 and current_price > self.entry_price * 1.01:
                # 价格反弹1%以上，卖出
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
                return {
                    "action": "sell",
                    "quantity": quantity,
                    "price": current_price,
                    "balance": self.current_balance,
                    "position": self.position,
                    "reason": "bounce_sell"
                }
        else:
            # 非下跌市场：使用正常网格交易
            if grid_change < 0 and self.position == 0:
                # 价格下跌到更低网格 -> 买入（低买）
                position_size = self._calculate_position_size(current_price)
                if position_size > 0.01:
                    buy_amount = position_size * current_price
                    if buy_amount >= self.min_trade_amount:
                        self.position = position_size
                        self.current_balance -= buy_amount
                        self.entry_price = current_price
                        self.last_grid_index = current_grid_index
                        self.last_price = current_price
                        self.total_trades += 1
                        return {
                            "action": "buy",
                            "quantity": position_size,
                            "price": current_price,
                            "balance": self.current_balance,
                            "position": self.position,
                            "reason": "grid_buy"
                        }
            elif grid_change > 0 and self.position > 0:
                # 价格上涨到更高网格 -> 卖出（高卖）
                revenue = self.position * current_price
                self.current_balance += revenue
                quantity = self.position
                self.position = 0
                self.entry_price = 0
                self.last_grid_index = current_grid_index
                self.last_price = current_price
                self.total_trades += 1
                if current_price > self.entry_price:
                    self.winning_trades += 1
                else:
                    self.losing_trades += 1
                return {
                    "action": "sell",
                    "quantity": quantity,
                    "price": current_price,
                    "balance": self.current_balance,
                    "position": self.position,
                    "reason": "grid_sell"
                }
        
        # 更新但不交易
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
