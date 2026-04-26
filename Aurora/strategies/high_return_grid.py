#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
高收益网格交易策略
目标：实现8%的收益率和2.0-3.0的夏普指数
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Any, Tuple
from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier
from sklearn.preprocessing import StandardScaler

class HighReturnGridTrading:
    """
    高收益网格交易策略
    目标：实现8%的收益率和2.0-3.0的夏普指数
    """
    
    def __init__(self, initial_balance: float = 100000.0, base_price: float = None):
        """
        初始化策略
        
        Args:
            initial_balance: 初始资金
            base_price: 基准价格
        """
        self.initial_balance = initial_balance
        self.balance = initial_balance
        self.position = 0.0
        self.base_price = base_price
        self.price_history = []
        self.last_price = base_price if base_price else 0
        self.last_buy_price = base_price if base_price else 0
        self.entry_price = 0
        
        # 高收益参数设置（分钟级高频交易）
        self.grid_spacing = 0.0002  # 减小网格间距，实现高频交易
        self.grid_levels = 20  # 网格层数
        self.take_profit_threshold = 0.001  # 减小止盈阈值，提高交易频率
        self.stop_loss_threshold = 0.0005  # 减小止损阈值
        self.max_position_percentage = 0.95  # 最大持仓比例
        self.reserve_balance_percentage = 0.05  # 保留资金比例
        
        # 交易参数
        self.fee_rate = 0.0003  # 交易手续费
        self.slippage = 0.0002  # 滑点
        
        # 性能指标
        self.total_trades = 0
        self.win_trades = 0
        self.lose_trades = 0
        self.total_profit = 0.0
        self.profit_history = []
        
        # 网格初始化
        self.grids = []
        self.last_grid_index = self.grid_levels  # 初始在中间网格
        if base_price:
            self.grids = self._create_grids()
        
        # 技术指标参数
        self.rsi_period = 14
        self.macd_fast = 12
        self.macd_slow = 26
        self.macd_signal = 9
        self.bollinger_period = 20
        self.bollinger_std = 2
        self.atr_period = 14  # ATR周期
        
        # 机器学习模型
        self.grid_spacing_optimizer = RandomForestRegressor(n_estimators=100, random_state=42)
        self.fund_allocation_optimizer = RandomForestRegressor(n_estimators=100, random_state=42)
        self.market_classifier = RandomForestClassifier(n_estimators=100, random_state=42)
        self.scaler = StandardScaler()
        self.model_trained = False
        
        # 训练数据
        self.grid_spacing_data = []
        self.grid_spacing_labels = []
        self.fund_allocation_data = []
        self.fund_allocation_labels = []
        self.market_data = []
        self.market_labels = []
        
        # 市场类型
        self.market_type = 'range_bound'
        self.market_types = ['range_bound', 'trending_up', 'trending_down']
        
        # 黄金分割参数
        self.golden_ratio = 0.618
        self.golden_points = [0.25, 0.5, 0.75]  # 更积极的卖出策略
        
        # 动态买入量参数（分钟级高频交易）
        self.min_buy_amount = 100  # 减小最小买入金额
        self.max_buy_amount = 1000  # 减小最大买入金额
        self.buy_amount_step = 100  # 减小买入金额步长
        
        # 优化参数
        self.optimization_period = 50
        self.optimization_count = 0
        
        # 协变因子最优化参数
        self.covariance_window = 20  # 协方差计算窗口
        self.best_params = {
            'grid_spacing': self.grid_spacing,
            'max_position_percentage': self.max_position_percentage,
            'reserve_balance_percentage': self.reserve_balance_percentage,
            'take_profit_threshold': self.take_profit_threshold
        }
        
        # 机器学习参数优化
        self.parameter_optimizer = RandomForestRegressor(n_estimators=200, random_state=42)
        self.parameter_data = []
        self.parameter_labels = []
        
        # 目标指标
        self.target_return = 0.18  # 目标年化收益率18%（8-28%）
        self.target_sharpe = 2.5  # 目标夏普比率2.5（2.0-3.0）
        self.target_sortino = 3.5  # 目标索提诺比率3.5（>3.0）
        
        # 横盘市场特定参数
        self.min_grid_spacing = 0.0005  # 最小网格间距
        self.max_grid_spacing = 0.003  # 最大网格间距
        self.min_reserve_percentage = 0.1  # 最小保留资金比例
        self.max_reserve_percentage = 0.3  # 最大保留资金比例
        
        # 性能跟踪
        self.grid_adjustment_count = 0
        self.model_training_count = 0
    
    def _create_grids(self) -> List[float]:
        """
        创建网格
        
        Returns:
            网格价格列表
        """
        grids = []
        # 创建上下各grid_levels层网格
        for i in range(-self.grid_levels, self.grid_levels + 1):
            grid_price = self.base_price * (1 + self.grid_spacing) ** i
            grids.append(grid_price)
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
            return 50
        
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
            return 0, 0, 0
        
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
            return data.iloc[-1] * 1.05, data.iloc[-1], data.iloc[-1] * 0.95
        
        ma = data.rolling(window=self.bollinger_period).mean().iloc[-1]
        std = data.rolling(window=self.bollinger_period).std().iloc[-1]
        if std == 0:
            std = 0.01
        upper = ma + (std * self.bollinger_std)
        lower = ma - (std * self.bollinger_std)
        
        return upper, ma, lower
    
    def _calculate_atr(self, data: pd.Series) -> float:
        """
        计算ATR指标
        
        Args:
            data: 价格数据
            
        Returns:
            ATR值
        """
        if len(data) < self.atr_period + 1:
            return 0.001  # 默认值
        
        high = data
        low = data
        close = data.shift(1)
        
        tr = pd.DataFrame()
        tr['h-l'] = high - low
        tr['h-pc'] = abs(high - close)
        tr['l-pc'] = abs(low - close)
        tr['tr'] = tr.max(axis=1)
        
        atr = tr['tr'].rolling(window=self.atr_period).mean().iloc[-1]
        return atr / data.iloc[-1]
    
    def _calculate_range_boundaries(self, data: pd.Series) -> Tuple[float, float]:
        """
        计算横盘区间的上下限
        
        Args:
            data: 价格数据
            
        Returns:
            区间下限, 区间上限
        """
        if len(data) < 20:
            current_price = data.iloc[-1]
            return current_price * 0.95, current_price * 1.05
        
        recent_prices = data.iloc[-20:]
        lower_bound = recent_prices.min()
        upper_bound = recent_prices.max()
        
        if upper_bound - lower_bound < 0.01 * data.iloc[-1]:
            mid_price = (lower_bound + upper_bound) / 2
            lower_bound = mid_price * 0.99
            upper_bound = mid_price * 1.01
        
        return lower_bound, upper_bound
    
    def _calculate_golden_points(self, lower_bound: float, upper_bound: float) -> List[float]:
        """
        计算黄金分割点
        
        Args:
            lower_bound: 区间下限
            upper_bound: 区间上限
            
        Returns:
            黄金分割点列表
        """
        range_width = upper_bound - lower_bound
        return [lower_bound + point * range_width for point in self.golden_points]
    
    def _calculate_returns(self, data: pd.Series) -> pd.Series:
        """
        计算收益率序列
        
        Args:
            data: 价格数据
            
        Returns:
            收益率序列
        """
        return data.pct_change().dropna()
    
    def _calculate_covariance(self, returns: pd.Series) -> np.ndarray:
        """
        计算协方差矩阵
        
        Args:
            returns: 收益率序列
            
        Returns:
            协方差矩阵
        """
        if len(returns) < self.covariance_window:
            return np.array([[0.0001]])
        
        # 计算滚动协方差
        cov_matrix = np.cov(returns.values, returns.values)
        return cov_matrix
    
    def _calculate_sharpe_ratio(self, returns: pd.Series, risk_free_rate: float = 0.0) -> float:
        """
        计算夏普比率
        
        Args:
            returns: 收益率序列
            risk_free_rate: 无风险利率
            
        Returns:
            夏普比率
        """
        if len(returns) < 2:
            return 0
        
        excess_returns = returns - risk_free_rate / 252  # 日无风险利率
        mean_excess_return = np.mean(excess_returns)
        std_excess_return = np.std(excess_returns)
        
        if std_excess_return == 0:
            return 0
        
        return mean_excess_return / std_excess_return * np.sqrt(252)  # 年化
    
    def _calculate_sortino_ratio(self, returns: pd.Series, risk_free_rate: float = 0.0) -> float:
        """
        计算索提诺比率
        
        Args:
            returns: 收益率序列
            risk_free_rate: 无风险利率
            
        Returns:
            索提诺比率
        """
        if len(returns) < 2:
            return 0
        
        excess_returns = returns - risk_free_rate / 252  # 日无风险利率
        mean_excess_return = np.mean(excess_returns)
        downside_returns = excess_returns[excess_returns < 0]
        
        if len(downside_returns) == 0:
            return 0
        
        downside_deviation = np.std(downside_returns)
        
        if downside_deviation == 0:
            return 0
        
        return mean_excess_return / downside_deviation * np.sqrt(252)  # 年化
    
    def _calculate_dynamic_buy_amount(self, current_price: float, lower_bound: float, upper_bound: float) -> float:
        """
        计算动态买入金额
        
        Args:
            current_price: 当前价格
            lower_bound: 区间下限
            upper_bound: 区间上限
            
        Returns:
            买入金额
        """
        price_position = (current_price - lower_bound) / (upper_bound - lower_bound)
        buy_amount_ratio = 1 - price_position
        buy_amount = self.min_buy_amount + buy_amount_ratio * (self.max_buy_amount - self.min_buy_amount)
        return max(self.min_buy_amount, min(self.max_buy_amount, buy_amount))
    
    def _calculate_optimal_grid_spacing(self, data: pd.Series) -> float:
        """
        计算最优网格间距
        
        Args:
            data: 价格数据
            
        Returns:
            最优网格间距
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
        optimal_spacing = max(self.min_grid_spacing, min(self.max_grid_spacing, volatility * 1.5))
        
        # 收集训练数据
        self.grid_spacing_data.append(features)
        self.grid_spacing_labels.append(optimal_spacing)
        
        # 定期训练模型
        if len(self.grid_spacing_data) % 30 == 0 and len(self.grid_spacing_data) >= 100:
            self._train_models()
        
        # 使用模型预测最优网格间距
        if self.model_trained:
            try:
                features_scaled = self.scaler.transform([features])
                predicted_spacing = self.grid_spacing_optimizer.predict(features_scaled)[0]
                # 确保预测值在合理范围内
                predicted_spacing = max(self.min_grid_spacing, min(self.max_grid_spacing, predicted_spacing))
                return predicted_spacing
            except Exception:
                return optimal_spacing
        else:
            return optimal_spacing
    
    def _calculate_optimal_fund_allocation(self, data: pd.Series) -> Tuple[float, float]:
        """
        计算最优资金分配
        
        Args:
            data: 价格数据
            
        Returns:
            (最大持仓比例, 保留资金比例)
        """
        if len(data) < 20:
            return self.max_position_percentage, self.reserve_balance_percentage
        
        # 提取特征
        features = self._extract_features(data)
        
        # 计算RSI
        rsi = self._calculate_rsi(data)
        
        # 计算波动率
        volatility = data.iloc[-20:].pct_change().std()
        
        # 基于RSI和波动率计算资金分配
        if rsi < 30:
            # 超卖，增加持仓比例
            max_position = min(0.9, self.max_position_percentage + 0.1)
            reserve_balance = max(self.min_reserve_percentage, self.reserve_balance_percentage - 0.1)
        elif rsi > 70:
            # 超买，减少持仓比例
            max_position = max(0.6, self.max_position_percentage - 0.1)
            reserve_balance = min(self.max_reserve_percentage, self.reserve_balance_percentage + 0.1)
        else:
            # 正常状态，保持默认比例
            max_position = self.max_position_percentage
            reserve_balance = self.reserve_balance_percentage
        
        # 高波动率时减少持仓比例
        if volatility > 0.02:
            max_position = max(0.6, max_position - 0.1)
            reserve_balance = min(self.max_reserve_percentage, reserve_balance + 0.1)
        
        # 收集训练数据
        self.fund_allocation_data.append(features)
        self.fund_allocation_labels.append(max_position)
        
        # 定期训练模型
        if len(self.fund_allocation_data) % 30 == 0 and len(self.fund_allocation_data) >= 100:
            self._train_models()
        
        # 使用模型预测最优资金分配
        if self.model_trained:
            try:
                features_scaled = self.scaler.transform([features])
                predicted_max_position = self.fund_allocation_optimizer.predict(features_scaled)[0]
                # 确保预测值在合理范围内
                predicted_max_position = max(0.5, min(0.9, predicted_max_position))
                predicted_reserve_balance = 1 - predicted_max_position * 0.8  # 保留资金比例与持仓比例相关
                predicted_reserve_balance = max(self.min_reserve_percentage, min(self.max_reserve_percentage, predicted_reserve_balance))
                return predicted_max_position, predicted_reserve_balance
            except Exception:
                return max_position, reserve_balance
        else:
            return max_position, reserve_balance
    
    def _extract_features(self, data: pd.Series) -> List[float]:
        """
        提取特征用于机器学习
        
        Args:
            data: 价格数据
            
        Returns:
            特征列表
        """
        if len(data) < 20:
            return [0] * 21
        
        # 计算RSI
        rsi = self._calculate_rsi(data)
        
        # 计算MACD
        macd, signal, histogram = self._calculate_macd(data)
        
        # 计算布林带
        upper_band, middle_band, lower_band = self._calculate_bollinger_bands(data)
        
        # 计算ATR
        atr = self._calculate_atr(data)
        
        # 计算价格变化率
        price_change_1d = (data.iloc[-1] - data.iloc[-2]) / data.iloc[-2] if len(data) > 1 else 0
        price_change_5d = (data.iloc[-1] - data.iloc[-6]) / data.iloc[-6] if len(data) > 5 else 0
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
        trend_strength = (ema10 - ema60) / ema60
        
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
        
        return [
            rsi,
            macd / data.iloc[-1],
            signal / data.iloc[-1],
            histogram / data.iloc[-1],
            price_change_1d,
            price_change_5d,
            price_change_20d,
            volatility,
            price_range,
            trend_strength,
            momentum,
            ema10 / ema30,
            ema30 / ema60,
            support_level,
            resistance_level,
            bollinger_width,
            bollinger_position,
            atr,  # 添加ATR指标
            data.iloc[-1] / data.iloc[-20],
            data.iloc[-10] / data.iloc[-20],
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
        
        ema10 = data.ewm(span=10).mean().iloc[-1]
        ema60 = data.ewm(span=60).mean().iloc[-1]
        trend_strength = (ema10 - ema60) / ema60
        
        recent_data = data.iloc[-20:]
        price_range = (recent_data.max() - recent_data.min()) / recent_data.mean()
        
        if trend_strength < -0.02:
            return 'trending_down'
        elif trend_strength > 0.02:
            return 'trending_up'
        elif price_range < 0.04:
            return 'range_bound'
        else:
            if abs(trend_strength) > 0.01:
                if trend_strength > 0:
                    return 'trending_up'
                else:
                    return 'trending_down'
            else:
                return 'range_bound'
    
    def detect_market_type(self, data: pd.Series) -> str:
        """
        检测市场类型
        
        Args:
            data: 价格数据
            
        Returns:
            市场类型
        """
        if len(data) < 20:
            return 'range_bound'
        
        features = self._extract_features(data)
        true_label = self._label_market_type(data)
        
        self.market_data.append(features)
        self.market_labels.append(true_label)
        
        if len(self.market_data) % 30 == 0 and len(self.market_data) >= 100:
            self._train_models()
        
        if self.model_trained:
            try:
                features_scaled = self.scaler.transform([features])
                prediction = self.market_classifier.predict(features_scaled)[0]
                return self.market_types[prediction]
            except Exception:
                return true_label
        else:
            return true_label
    
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
        
        # 训练网格间距优化模型
        if len(self.grid_spacing_data) >= 100:
            # 准备训练数据
            X = np.array(self.grid_spacing_data)
            y = np.array(self.grid_spacing_labels)
            
            # 标准化特征
            X_scaled = self.scaler.fit_transform(X)
            
            # 训练模型
            self.grid_spacing_optimizer.fit(X_scaled, y)
        
        # 训练资金分配优化模型
        if len(self.fund_allocation_data) >= 100:
            # 准备训练数据
            X = np.array(self.fund_allocation_data)
            y = np.array(self.fund_allocation_labels)
            
            # 标准化特征
            X_scaled = self.scaler.fit_transform(X)
            
            # 训练模型
            self.fund_allocation_optimizer.fit(X_scaled, y)
        
        if len(self.market_data) >= 100 or len(self.grid_spacing_data) >= 100 or len(self.fund_allocation_data) >= 100:
            self.model_trained = True
            self.model_training_count += 1
    
    def _train_parameter_optimizer(self):
        """
        训练参数优化模型
        """
        if len(self.parameter_data) >= 200:
            # 准备训练数据
            X = np.array(self.parameter_data)
            y = np.array(self.parameter_labels)
            
            # 标准化特征
            X_scaled = self.scaler.fit_transform(X)
            
            # 训练模型
            self.parameter_optimizer.fit(X_scaled, y)
            
            print(f"参数优化模型训练完成，训练数据量: {len(self.parameter_data)}")
    
    def update_price(self, current_price: float, data: pd.Series = None) -> Dict[str, Any]:
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
            
            # 协变因子最优化：定期更新参数
            self.optimization_count += 1
            if self.optimization_count % self.optimization_period == 0:
                # 找到最优参数组合
                optimal_params = self._find_optimal_parameters(data)
                
                # 如果参数优化模型已训练，使用模型预测参数
                if hasattr(self, 'parameter_optimizer') and len(self.parameter_data) >= 200:
                    try:
                        # 提取特征
                        features = self._extract_features(data)
                        returns = self._calculate_returns(data)
                        mean_return = returns.mean() if len(returns) > 0 else 0
                        std_return = returns.std() if len(returns) > 0 else 0
                        sharpe_ratio = self._calculate_sharpe_ratio(returns)
                        sortino_ratio = self._calculate_sortino_ratio(returns)
                        max_drawdown = (returns.cummax() - returns).max() if len(returns) > 0 else 0
                        
                        # 准备输入特征
                        input_features = features + [mean_return, std_return, sharpe_ratio, sortino_ratio, max_drawdown]
                        input_features_scaled = self.scaler.transform([input_features])
                        
                        # 预测参数
                        predicted_params = self.parameter_optimizer.predict(input_features_scaled)[0]
                        
                        # 验证预测参数
                        if len(predicted_params) == 4:
                            # 确保参数在合理范围内
                            predicted_grid_spacing = max(self.min_grid_spacing, min(self.max_grid_spacing, predicted_params[0]))
                            predicted_max_position = max(0.5, min(0.98, predicted_params[1]))
                            predicted_reserve_balance = max(0.05, min(0.3, predicted_params[2]))
                            predicted_take_profit = max(0.01, min(0.05, predicted_params[3]))
                            
                            # 结合预测参数和搜索参数
                            optimal_params = {
                                'grid_spacing': (optimal_params['grid_spacing'] + predicted_grid_spacing) / 2,
                                'max_position_percentage': (optimal_params['max_position_percentage'] + predicted_max_position) / 2,
                                'reserve_balance_percentage': (optimal_params['reserve_balance_percentage'] + predicted_reserve_balance) / 2,
                                'take_profit_threshold': (optimal_params['take_profit_threshold'] + predicted_take_profit) / 2
                            }
                    except Exception as e:
                        print(f"参数预测失败: {e}")
                
                # 更新参数
                self.grid_spacing = optimal_params['grid_spacing']
                self.max_position_percentage = optimal_params['max_position_percentage']
                self.reserve_balance_percentage = optimal_params['reserve_balance_percentage']
                self.take_profit_threshold = optimal_params['take_profit_threshold']
                # 重新创建网格
                self.grids = self._create_grids()
                self.best_params = optimal_params
            
            # 市场状态参数
            market_state_params = {
                'range_bound': {
                    'grid_spacing': 0.0015,
                    'max_position_percentage': 0.8,
                    'reserve_balance_percentage': 0.2,
                    'take_profit_threshold': 0.025
                },
                'trending_up': {
                    'grid_spacing': 0.003,
                    'max_position_percentage': 0.6,
                    'reserve_balance_percentage': 0.4,
                    'take_profit_threshold': 0.035
                },
                'trending_down': {
                    'grid_spacing': 0.002,
                    'max_position_percentage': 0.4,
                    'reserve_balance_percentage': 0.6,
                    'take_profit_threshold': 0.02
                }
            }
            
            # 根据市场状态调整参数
            if self.market_type in market_state_params:
                params = market_state_params[self.market_type]
                # 结合最优参数和市场状态参数
                self.grid_spacing = (self.grid_spacing + params['grid_spacing']) / 2
                self.max_position_percentage = (self.max_position_percentage + params['max_position_percentage']) / 2
                self.reserve_balance_percentage = (self.reserve_balance_percentage + params['reserve_balance_percentage']) / 2
                self.take_profit_threshold = (self.take_profit_threshold + params['take_profit_threshold']) / 2
                # 重新创建网格
                self.grids = self._create_grids()
            
            # 使用机器学习优化网格间距
            optimal_spacing = self._calculate_optimal_grid_spacing(data)
            if abs(optimal_spacing - self.grid_spacing) > 0.0001:
                self.grid_spacing = optimal_spacing
                self.grids = self._create_grids()
                self.grid_adjustment_count += 1
            
            # 使用机器学习优化资金分配
            optimal_max_position, optimal_reserve = self._calculate_optimal_fund_allocation(data)
            if abs(optimal_max_position - self.max_position_percentage) > 0.01:
                self.max_position_percentage = optimal_max_position
                self.reserve_balance_percentage = optimal_reserve
        
        # 初始化网格
        if not self.grids:
            self.base_price = current_price
            self.grids = self._create_grids()
        
        # 计算可用资金
        available_balance = self.balance * (1 - self.reserve_balance_percentage)
        max_position = (self.initial_balance * self.max_position_percentage) / current_price
        
        # 找到当前价格所在的网格区间
        current_grid_index = None
        for i in range(len(self.grids) - 1):
            if self.grids[i] <= current_price < self.grids[i + 1]:
                current_grid_index = i
                break
        
        if current_grid_index is None:
            self.base_price = current_price
            self.grids = self._create_grids()
            for i in range(len(self.grids) - 1):
                if self.grids[i] <= current_price < self.grids[i + 1]:
                    current_grid_index = i
                    break
            if current_grid_index is None:
                return {"action": "hold", "balance": self.balance, "position": self.position}
        
        # 计算横盘区间边界和黄金分割点
        price_series = pd.Series(self.price_history)
        lower_bound, upper_bound = self._calculate_range_boundaries(price_series)
        golden_points = self._calculate_golden_points(lower_bound, upper_bound)
        
        # 网格交易核心逻辑
        grid_change = current_grid_index - self.last_grid_index
        
        # 横盘市场的高频交易策略
        if grid_change < 0 and self.position < max_position:
            # 价格下跌到更低网格 -> 买入（低买）
            buy_amount = self._calculate_dynamic_buy_amount(current_price, lower_bound, upper_bound)
            buy_amount = min(buy_amount, available_balance * 0.15)
            if buy_amount > self.min_buy_amount:
                buy_quantity = buy_amount / current_price
                if buy_quantity > 0.01:
                    actual_buy_amount = buy_quantity * current_price * (1 + self.fee_rate + self.slippage)
                    actual_buy_amount = min(actual_buy_amount, available_balance)
                    buy_quantity = actual_buy_amount / (current_price * (1 + self.fee_rate + self.slippage))
                    if buy_quantity > 0.01:
                        self.position += buy_quantity
                        self.balance -= actual_buy_amount
                        if self.entry_price == 0:
                            self.entry_price = current_price
                        self.last_buy_price = current_price
                        self.last_grid_index = current_grid_index
                        self.last_price = current_price
                        self.total_trades += 1
                        return {
                            "action": "buy",
                            "quantity": buy_quantity,
                            "current_price": current_price,
                            "balance": self.balance,
                            "position": self.position,
                            "reason": "grid_buy"
                        }
        elif grid_change > 0 and self.position > 0:
            # 价格上涨到更高网格 -> 卖出（高卖）
            if self.market_type == 'range_bound':
                price_position = (current_price - lower_bound) / (upper_bound - lower_bound)
                
                if current_price > golden_points[0] and current_price <= golden_points[1]:
                    sell_quantity = self.position * 0.4
                elif current_price > golden_points[1] and current_price <= golden_points[2]:
                    sell_quantity = self.position * 0.6
                elif current_price > golden_points[2]:
                    sell_quantity = self.position
                else:
                    sell_quantity = self.position * 0.2
                
                if sell_quantity > 0.01:
                    if current_price > self.last_buy_price * 1.0005:
                        sell_value = sell_quantity * current_price * (1 - self.fee_rate - self.slippage)
                        self.balance += sell_value
                        self.position -= sell_quantity
                        self.last_grid_index = current_grid_index
                        self.last_price = current_price
                        self.total_trades += 1
                        self.win_trades += 1
                        profit = sell_value - sell_quantity * self.last_buy_price
                        self.total_profit += profit
                        self.profit_history.append(profit)
                        return {
                            "action": "sell",
                            "quantity": sell_quantity,
                            "current_price": current_price,
                            "balance": self.balance,
                            "position": self.position,
                            "reason": "grid_sell"
                        }
            else:
                sell_quantity = min(abs(grid_change) * 400 / current_price, self.position)
                if sell_quantity > 0.01:
                    if current_price > self.last_buy_price * 1.0005:
                        sell_value = sell_quantity * current_price * (1 - self.fee_rate - self.slippage)
                        self.balance += sell_value
                        self.position -= sell_quantity
                        self.last_grid_index = current_grid_index
                        self.last_price = current_price
                        self.total_trades += 1
                        self.win_trades += 1
                        profit = sell_value - sell_quantity * self.last_buy_price
                        self.total_profit += profit
                        self.profit_history.append(profit)
                        return {
                            "action": "sell",
                            "quantity": sell_quantity,
                            "current_price": current_price,
                            "balance": self.balance,
                            "position": self.position,
                            "reason": "grid_sell"
                        }
        
        # 横盘市场的额外交易策略：基于价格动量
        if len(self.price_history) > 5:
            recent_prices = self.price_history[-5:]
            price_range = max(recent_prices) - min(recent_prices)
            price_mean = np.mean(recent_prices)
            
            if price_range / price_mean < 0.01 and available_balance > 200:
                if current_price < price_mean * 0.998:
                    buy_amount = min(available_balance * 0.1, 500)
                    if buy_amount > 50:
                        buy_quantity = buy_amount / (current_price * (1 + self.fee_rate + self.slippage))
                        if buy_quantity > 0.01:
                            actual_buy_amount = buy_quantity * current_price * (1 + self.fee_rate + self.slippage)
                            actual_buy_amount = min(actual_buy_amount, available_balance)
                            buy_quantity = actual_buy_amount / (current_price * (1 + self.fee_rate + self.slippage))
                            if buy_quantity > 0.01:
                                self.position += buy_quantity
                                self.balance -= actual_buy_amount
                                if self.entry_price == 0:
                                    self.entry_price = current_price
                                self.last_buy_price = current_price
                                self.last_price = current_price
                                self.total_trades += 1
                                return {
                                    "action": "buy",
                                    "quantity": buy_quantity,
                                    "current_price": current_price,
                                    "balance": self.balance,
                                    "position": self.position,
                                    "reason": "mean_reversion_buy"
                                }
                elif current_price > price_mean * 1.002 and self.position > 0:
                    sell_quantity = min(self.position * 0.2, 500 / current_price)
                    if sell_quantity > 0.01:
                        sell_value = sell_quantity * current_price * (1 - self.fee_rate - self.slippage)
                        self.balance += sell_value
                        self.position -= sell_quantity
                        self.last_price = current_price
                        self.total_trades += 1
                        profit = sell_value - sell_quantity * self.last_buy_price
                        if profit > 0:
                            self.win_trades += 1
                        else:
                            self.lose_trades += 1
                        self.total_profit += profit
                        self.profit_history.append(profit)
                        return {
                            "action": "sell",
                            "quantity": sell_quantity,
                            "current_price": current_price,
                            "balance": self.balance,
                            "position": self.position,
                            "reason": "mean_reversion_sell"
                        }
        
        # 更新但不交易
        self.last_grid_index = current_grid_index
        self.last_price = current_price
        
        # 计算当前权益
        current_equity = self.balance + self.position * current_price
        
        # 计算收益率
        return_rate = (current_equity - self.initial_balance) / self.initial_balance
        
        # 计算胜率
        win_rate = self.win_trades / self.total_trades if self.total_trades > 0 else 0
        
        return {
            "action": "hold",
            "quantity": 0,
            "current_price": current_price,
            "balance": self.balance,
            "position": self.position,
            "current_equity": current_equity,
            "return_rate": return_rate,
            "total_trades": self.total_trades,
            "win_rate": win_rate,
            "total_profit": self.total_profit
        }
    
    def _find_optimal_parameters(self, data: pd.Series) -> Dict[str, float]:
        """
        找到最优参数组合
        
        Args:
            data: 价格数据
            
        Returns:
            最优参数组合
        """
        returns = self._calculate_returns(data)
        if len(returns) < self.covariance_window:
            return self.best_params
        
        # 计算协方差矩阵
        cov_matrix = self._calculate_covariance(returns)
        
        # 计算收益率统计指标
        mean_return = returns.mean()
        std_return = returns.std()
        sharpe_ratio = self._calculate_sharpe_ratio(returns)
        sortino_ratio = self._calculate_sortino_ratio(returns)
        max_drawdown = (returns.cummax() - returns).max()
        
        # 提取特征
        features = self._extract_features(data)
        
        # 定义参数搜索空间（更精细的参数）
        # 网格间距：更小的间距，增加交易频率
        grid_spacings = [0.0005, 0.0007, 0.0009, 0.001, 0.0012, 0.0014, 0.0016, 0.0018, 0.002]
        # 止盈阈值：更高的止盈，增加每笔收益
        take_profit_thresholds = [0.02, 0.025, 0.03, 0.035, 0.04, 0.045, 0.05]
        # 资金管理参数：更高的仓位，提高资金利用率
        max_position_percentages = [0.8, 0.85, 0.9, 0.92, 0.95, 0.98]
        # 保留资金：更少的保留，提高资金利用率
        reserve_balance_percentages = [0.05, 0.08, 0.1, 0.12, 0.15]
        
        best_score = -float('inf')
        best_params = self.best_params.copy()
        
        # 遍历参数组合
        for grid_spacing in grid_spacings:
            for max_position in max_position_percentages:
                for reserve_balance in reserve_balance_percentages:
                    for take_profit in take_profit_thresholds:
                        # 计算预期收益和风险
                        expected_return = take_profit - 0.001  # 减去交易成本
                        expected_risk = np.trace(cov_matrix)  # 协方差矩阵的迹作为风险指标
                        expected_sharpe = expected_return / expected_risk if expected_risk > 0 else 0
                        expected_sortino = expected_return / (expected_risk * 0.8) if expected_risk > 0 else 0  # 估算索提诺比率
                        expected_max_drawdown = expected_risk * 1.5  # 更保守的最大回撤估算
                        
                        # 计算与目标的差距
                        return_gap = abs(expected_return - self.target_return)
                        sharpe_gap = abs(expected_sharpe - self.target_sharpe)
                        sortino_gap = abs(expected_sortino - self.target_sortino)
                        
                        # 计算参数得分（以收益、夏普比率和索提诺比率为目标）
                        score = (
                            (1 - return_gap) * 0.4 +  # 收益权重40%
                            (1 - sharpe_gap) * 0.3 +  # 夏普比率权重30%
                            (1 - sortino_gap) * 0.3    # 索提诺比率权重30%
                        ) * (1 + expected_return * 200) * (1 + expected_sharpe * 15) * (1 + expected_sortino * 10)
                        
                        # 选择得分最高的参数组合
                        if score > best_score:
                            best_score = score
                            best_params = {
                                'grid_spacing': grid_spacing,
                                'max_position_percentage': max_position,
                                'reserve_balance_percentage': reserve_balance,
                                'take_profit_threshold': take_profit
                            }
        
        # 收集训练数据
        self.parameter_data.append(features + [mean_return, std_return, sharpe_ratio, sortino_ratio, max_drawdown])
        self.parameter_labels.append([
            best_params['grid_spacing'],
            best_params['max_position_percentage'],
            best_params['reserve_balance_percentage'],
            best_params['take_profit_threshold']
        ])
        
        # 定期训练参数优化模型
        if len(self.parameter_data) % 50 == 0 and len(self.parameter_data) >= 200:
            self._train_parameter_optimizer()
        
        return best_params
    
    def get_performance(self) -> Dict[str, Any]:
        """
        获取策略性能
        
        Returns:
            策略性能指标
        """
        current_price = self.last_price if self.last_price > 0 else 100
        current_equity = self.balance + self.position * current_price
        return_rate = (current_equity - self.initial_balance) / self.initial_balance
        win_rate = self.win_trades / self.total_trades if self.total_trades > 0 else 0
        avg_profit = np.mean(self.profit_history) if self.profit_history else 0
        total_profit = sum(self.profit_history) if self.profit_history else 0
        
        return {
            "initial_balance": self.initial_balance,
            "current_balance": current_equity,
            "return": return_rate,
            "total_trades": self.total_trades,
            "win_rate": win_rate,
            "total_profit": total_profit,
            "avg_profit_per_trade": avg_profit,
            "winning_trades": self.win_trades,
            "losing_trades": self.lose_trades,
            "grid_adjustments": self.grid_adjustment_count,
            "model_training_count": self.model_training_count,
            "model_trained": self.model_trained
        }
