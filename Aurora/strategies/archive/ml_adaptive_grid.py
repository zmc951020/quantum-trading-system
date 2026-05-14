#!/usr/bin/env python3
"""
机器学习自适应网格交易策略
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Tuple, Optional
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler

class MLAdaptiveGridTrading:
    """
    机器学习自适应网格交易策略
    """
    
    def __init__(self, base_price: float, grid_spacing: float = 0.002, initial_balance: float = 100000):
        """
        初始化机器学习自适应网格交易策略
        
        Args:
            base_price: 基准价格
            grid_spacing: 网格间距
            initial_balance: 初始资金
        """
        self.base_price = base_price
        self.grid_spacing = grid_spacing
        self.initial_balance = initial_balance
        self.current_balance = initial_balance
        self.position = 0
        self.grid_levels = 30  # 网格层数
        self.grids = self._create_grids()
        self.price_history = []
        self.is_active = True
        self.last_grid_index = self.grid_levels  # 初始在中间网格
        self.last_price = base_price  # 上次价格
        self.entry_price = 0  # 入场价格
        self.consecutive_holds = 0  # 连续不交易次数
        self.min_grid_spacing = 0.001  # 最小网格间距
        self.max_grid_spacing = 0.01  # 最大网格间距
        
        # 交易统计
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        
        # 风险控制参数
        self.stop_loss_threshold = 0.02  # 2%止损（下跌市场中更严格）
        self.take_profit_threshold = 0.03  # 3%止盈（下跌市场中更保守）
        self.max_position_percentage = 0.5  # 最大持仓比例（下跌市场中降低）
        self.reserve_balance_percentage = 0.4  # 保留资金比例（下跌市场中增加）
        
        # 市场类型检测
        self.market_type = 'range_bound'
        self.last_market_type = 'range_bound'
        self.market_types = ['range_bound', 'trending_up', 'trending_down']
        
        # 网格调整计数器
        self.grid_adjustment_count = 0
        
        # 下跌市场特定参数
        self.downward_trend_count = 0  # 下跌趋势计数
        self.max_downward_trend_count = 10  # 最大下跌趋势计数
        self.downward_buy_reduction = 0.5  # 下跌市场买入金额减少比例
        
        # 历史最高价格
        self.highest_price = base_price
        
        # 下跌市场的买入策略
        self.downward_buy_levels = []  # 下跌买入点位
        self.downward_buy_amounts = []  # 对应买入金额
        self.downward_buy_executed = []  # 已执行的买入点位
        
        # 机器学习模型
        self.market_classifier = RandomForestClassifier(n_estimators=100, random_state=42)
        self.scaler = StandardScaler()
        self.model_trained = False
        self.model_data = []
        self.model_labels = []
        self.model_training_count = 0
        
        # 初始化下跌买入点位
        self._init_downward_buy_levels()
    
    def _init_downward_buy_levels(self):
        """
        初始化下跌买入点位
        """
        # 定义下跌买入点位（相对于基准价格的百分比）
        levels = [0.98, 0.95, 0.92, 0.90, 0.88, 0.85, 0.82, 0.80, 0.78, 0.75]
        for level in levels:
            price = self.base_price * level
            self.downward_buy_levels.append(price)
            # 价格越低，买入金额越大
            amount_ratio = (1 - level) * 15  # 价格越低，买入比例越高
            max_amount = self.initial_balance * 0.15  # 单次最大买入金额
            amount = min(max_amount, self.initial_balance * 0.05 * amount_ratio)
            self.downward_buy_amounts.append(amount)
            self.downward_buy_executed.append(False)
        
        # 按价格从高到低排序
        sorted_pairs = sorted(zip(self.downward_buy_levels, self.downward_buy_amounts, self.downward_buy_executed), reverse=True)
        self.downward_buy_levels, self.downward_buy_amounts, self.downward_buy_executed = zip(*sorted_pairs)
        self.downward_buy_levels = list(self.downward_buy_levels)
        self.downward_buy_amounts = list(self.downward_buy_amounts)
        self.downward_buy_executed = list(self.downward_buy_executed)
    
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
    
    def _extract_features(self, data: pd.Series) -> List[float]:
        """
        提取特征用于市场类型分类
        
        Args:
            data: 价格数据
            
        Returns:
            特征列表
        """
        if len(data) < 20:
            return [0] * 10  # 返回默认特征
        
        # 计算移动平均线
        ema10 = data.ewm(span=10).mean().iloc[-1]
        ema30 = data.ewm(span=30).mean().iloc[-1]
        ema60 = data.ewm(span=60).mean().iloc[-1]
        
        # 计算趋势强度
        trend_strength = (ema10 - ema60) / ema60
        
        # 计算价格范围
        recent_data = data.iloc[-20:]
        price_range = (recent_data.max() - recent_data.min()) / recent_data.mean()
        
        # 计算波动率
        volatility = recent_data.pct_change().std()
        
        # 计算MACD
        ema12 = data.ewm(span=12).mean().iloc[-1]
        ema26 = data.ewm(span=26).mean().iloc[-1]
        macd = ema12 - ema26
        
        # 计算RSI
        delta = data.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean().iloc[-1]
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean().iloc[-1]
        rs = gain / loss if loss != 0 else 0
        rsi = 100 - (100 / (1 + rs))
        
        # 计算价格变化率
        price_change_1d = (data.iloc[-1] - data.iloc[-2]) / data.iloc[-2]
        price_change_5d = (data.iloc[-1] - data.iloc[-6]) / data.iloc[-6]
        price_change_20d = (data.iloc[-1] - data.iloc[-21]) / data.iloc[-21]
        
        return [
            trend_strength,
            price_range,
            volatility,
            macd / data.iloc[-1],
            rsi,
            price_change_1d,
            price_change_5d,
            price_change_20d,
            ema10 / ema30,
            ema30 / ema60
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
    
    def _train_model(self):
        """
        训练机器学习模型
        """
        if len(self.model_data) < 50:
            return
        
        # 准备训练数据
        X = np.array(self.model_data)
        y = np.array([self.market_types.index(label) for label in self.model_labels])
        
        # 标准化特征
        X_scaled = self.scaler.fit_transform(X)
        
        # 训练模型
        self.market_classifier.fit(X_scaled, y)
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
        self.model_data.append(features)
        self.model_labels.append(true_label)
        
        # 定期训练模型
        if len(self.model_data) % 20 == 0:
            self._train_model()
        
        # 使用模型预测市场类型
        if self.model_trained:
            features_scaled = self.scaler.transform([features])
            prediction = self.market_classifier.predict(features_scaled)[0]
            predicted_type = self.market_types[prediction]
            return predicted_type
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
            data: 价格数据（用于市场类型检测）
            
        Returns:
            交易结果
        """
        # 记录价格历史
        self.price_history.append(current_price)
        
        # 更新历史最高价格
        if current_price > self.highest_price:
            self.highest_price = current_price
            # 价格创新高，重置下跌趋势计数和买入点位
            self.downward_trend_count = 0
            self.downward_buy_executed = [False] * len(self.downward_buy_executed)
        
        # 检测市场类型
        if data is not None:
            self.last_market_type = self.market_type
            self.market_type = self.detect_market_type(data)
            
            # 如果市场类型变化，调整网格和参数
            if self.last_market_type != self.market_type:
                if self.market_type == 'range_bound':
                    # 横盘市场，使用较小的网格间距
                    self.grid_spacing = 0.002
                    self.max_position_percentage = 0.75
                    self.reserve_balance_percentage = 0.25
                    self.stop_loss_threshold = 0.025
                    self.take_profit_threshold = 0.035
                elif self.market_type == 'trending_up':
                    # 上涨市场，使用中等的网格间距
                    self.grid_spacing = 0.003
                    self.max_position_percentage = 0.7
                    self.reserve_balance_percentage = 0.3
                    self.stop_loss_threshold = 0.025
                    self.take_profit_threshold = 0.035
                elif self.market_type == 'trending_down':
                    # 下跌市场，使用较大的网格间距
                    self.grid_spacing = 0.005
                    self.max_position_percentage = 0.5
                    self.reserve_balance_percentage = 0.4
                    self.stop_loss_threshold = 0.02
                    self.take_profit_threshold = 0.03
                self.grids = self._create_grids()
                self.grid_adjustment_count += 1
        
        # 动态调整网格间距
        if len(self.price_history) > 15:
            recent_prices = pd.Series(self.price_history[-15:])
            volatility = recent_prices.pct_change().std()
            if volatility > 0:
                optimal_spacing = max(self.min_grid_spacing, min(self.max_grid_spacing, volatility * 2))
                if abs(optimal_spacing - self.grid_spacing) > 0.0005:
                    self.grid_spacing = optimal_spacing
                    self.grids = self._create_grids()
                    self.grid_adjustment_count += 1
        
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
        
        # 计算价格变化
        price_change = (current_price - self.last_price) / self.last_price if self.last_price > 0 else 0
        
        # 下跌趋势计数
        if price_change < -0.005:
            self.downward_trend_count += 1
        else:
            # 价格上涨，重置下跌趋势计数
            self.downward_trend_count = 0
        
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
                self.last_grid_index = current_grid_index
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
        
        # 止盈检查：如果持仓盈利超过止盈阈值，自动止盈
        if self.position > 0 and self.entry_price > 0:
            profit_ratio = (current_price - self.entry_price) / self.entry_price
            if profit_ratio > self.take_profit_threshold:
                # 止盈卖出80%
                sell_quantity = self.position * 0.8
                if sell_quantity > 0.01:
                    revenue = sell_quantity * current_price
                    self.current_balance += revenue
                    self.position -= sell_quantity
                    self.last_grid_index = current_grid_index
                    self.last_price = current_price
                    self.total_trades += 1
                    self.winning_trades += 1
                    return {
                        "action": "sell",
                        "quantity": sell_quantity,
                        "price": current_price,
                        "balance": self.current_balance,
                        "position": self.position,
                        "reason": "take_profit"
                    }
        
        # 计算可用资金（保留reserve_balance_percentage作为接盘资金）
        available_balance = self.current_balance * (1 - self.reserve_balance_percentage)
        
        # 计算最大持仓限制
        max_position = (self.initial_balance * self.max_position_percentage) / current_price
        
        # 网格交易核心逻辑
        grid_change = current_grid_index - self.last_grid_index
        
        # 下跌市场的特殊处理
        if self.market_type == 'trending_down':
            # 下跌市场：减少买入频率，只在关键点位买入
            if grid_change < 0 and self.position < max_position:
                # 检查是否达到下跌买入点位
                for i, (buy_level, buy_amount, executed) in enumerate(zip(self.downward_buy_levels, self.downward_buy_amounts, self.downward_buy_executed)):
                    if current_price <= buy_level and not executed and available_balance > buy_amount:
                        # 达到买入点位
                        buy_quantity = buy_amount / current_price
                        if buy_quantity > 0.01:
                            self.position += buy_quantity
                            self.current_balance -= buy_amount
                            if self.entry_price == 0:
                                self.entry_price = current_price
                            self.last_grid_index = current_grid_index
                            self.last_price = current_price
                            # 标记为已执行
                            self.downward_buy_executed[i] = True
                            return {
                                "action": "buy",
                                "quantity": buy_quantity,
                                "price": current_price,
                                "balance": self.current_balance,
                                "position": self.position,
                                "reason": "downward_buy_level"
                            }
            elif grid_change > 0 and self.position > 0:
                # 下跌市场中的反弹，适当卖出
                sell_quantity = min(abs(grid_change) * 800 / current_price, self.position * 0.6)
                if sell_quantity > 0.01:
                    sell_amount = sell_quantity * current_price
                    self.position -= sell_quantity
                    self.current_balance += sell_amount
                    self.last_grid_index = current_grid_index
                    self.last_price = current_price
                    self.total_trades += 1
                    if current_price > self.entry_price:
                        self.winning_trades += 1
                    else:
                        self.losing_trades += 1
                    return {
                        "action": "sell",
                        "quantity": sell_quantity,
                        "price": current_price,
                        "balance": self.current_balance,
                        "position": self.position,
                        "reason": "downward_rally_sell"
                    }
        else:
            # 非下跌市场：正常网格交易
            if grid_change < 0 and self.position < max_position:
                # 价格下跌到更低网格 -> 买入（低买）
                buy_amount = min(abs(grid_change) * 1000, available_balance)
                if buy_amount > 50:
                    buy_quantity = buy_amount / current_price
                    if buy_quantity > 0.01:
                        self.position += buy_quantity
                        self.current_balance -= buy_amount
                        if self.entry_price == 0:
                            self.entry_price = current_price
                        self.last_grid_index = current_grid_index
                        self.last_price = current_price
                        return {
                            "action": "buy",
                            "quantity": buy_quantity,
                            "price": current_price,
                            "balance": self.current_balance,
                            "position": self.position
                        }
            elif grid_change > 0 and self.position > 0:
                # 价格上涨到更高网格 -> 卖出（高卖）
                sell_quantity = min(abs(grid_change) * 1000 / current_price, self.position)
                if sell_quantity > 0.01:
                    sell_amount = sell_quantity * current_price
                    self.position -= sell_quantity
                    self.current_balance += sell_amount
                    self.last_grid_index = current_grid_index
                    self.last_price = current_price
                    self.total_trades += 1
                    if current_price > self.entry_price:
                        self.winning_trades += 1
                    else:
                        self.losing_trades += 1
                    return {
                        "action": "sell",
                        "quantity": sell_quantity,
                        "price": current_price,
                        "balance": self.current_balance,
                        "position": self.position
                    }
        
        # 市场下跌时的资金接盘机制（仅在非明确下跌趋势时使用）
        if self.market_type != 'trending_down' and price_change < -0.015 and available_balance > 500:
            buy_amount = min(available_balance * 0.3, 3000)
            if buy_amount > 100:
                buy_quantity = buy_amount / current_price
                if buy_quantity > 0.01:
                    self.position += buy_quantity
                    self.current_balance -= buy_amount
                    if self.entry_price == 0:
                        self.entry_price = current_price
                    self.last_price = current_price
                    return {
                        "action": "buy",
                        "quantity": buy_quantity,
                        "price": current_price,
                        "balance": self.current_balance,
                        "position": self.position,
                        "reason": "market_drop_buy"
                    }
        
        # 市场上涨时的获利了结
        if price_change > 0.015 and self.position > 0:
            sell_quantity = min(self.position * 0.3, 1000 / current_price)
            if sell_quantity > 0.01:
                sell_amount = sell_quantity * current_price
                self.position -= sell_quantity
                self.current_balance += sell_amount
                self.last_price = current_price
                self.total_trades += 1
                if current_price > self.entry_price:
                    self.winning_trades += 1
                else:
                    self.losing_trades += 1
                return {
                    "action": "sell",
                    "quantity": sell_quantity,
                    "price": current_price,
                    "balance": self.current_balance,
                    "position": self.position,
                    "reason": "market_rise_sell"
                }
        
        # 横盘市场的高频交易策略
        if self.market_type == 'range_bound' and len(self.price_history) > 5:
            recent_prices = self.price_history[-5:]
            price_range = max(recent_prices) - min(recent_prices)
            price_mean = np.mean(recent_prices)
            
            # 如果价格在小范围内波动，执行高频交易
            if price_range / price_mean < 0.01 and available_balance > 200:
                if current_price < price_mean * 0.998:
                    # 价格低于均值，买入
                    buy_amount = min(available_balance * 0.2, 1000)
                    if buy_amount > 50:
                        buy_quantity = buy_amount / current_price
                        if buy_quantity > 0.01:
                            self.position += buy_quantity
                            self.current_balance -= buy_amount
                            if self.entry_price == 0:
                                self.entry_price = current_price
                            self.last_price = current_price
                            return {
                                "action": "buy",
                                "quantity": buy_quantity,
                                "price": current_price,
                                "balance": self.current_balance,
                                "position": self.position,
                                "reason": "range_bound_buy"
                            }
                elif current_price > price_mean * 1.002 and self.position > 0:
                    # 价格高于均值，卖出
                    sell_quantity = min(self.position * 0.2, 1000 / current_price)
                    if sell_quantity > 0.01:
                        sell_amount = sell_quantity * current_price
                        self.position -= sell_quantity
                        self.current_balance += sell_amount
                        self.last_price = current_price
                        self.total_trades += 1
                        if current_price > self.entry_price:
                            self.winning_trades += 1
                        else:
                            self.losing_trades += 1
                        return {
                            "action": "sell",
                            "quantity": sell_quantity,
                            "price": current_price,
                            "balance": self.current_balance,
                            "position": self.position,
                            "reason": "range_bound_sell"
                        }
        
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
        return {
            "initial_balance": self.initial_balance,
            "current_balance": self.current_balance,
            "return": (self.current_balance - self.initial_balance) / self.initial_balance * 100,
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": win_rate,
            "grid_adjustments": self.grid_adjustment_count,
            "final_position": self.position,
            "model_training_count": self.model_training_count,
            "model_trained": self.model_trained
        }
