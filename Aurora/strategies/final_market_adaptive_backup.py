#!/usr/bin/env python3
"""
最终市场自适应网格交易策略
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Tuple, Optional
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.preprocessing import StandardScaler

class FinalMarketAdaptiveGrid:
    """
    最终市场自适应网格交易策略
    """
    
    def __init__(self, base_price: float, initial_balance: float = 100000):
        """
        初始化最终市场自适应网格交易策略
        
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
        self.last_buy_price = base_price  # 上次买入价格
        
        # 交易统计
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        self.profit_history = []
        
        # 市场类型
        self.market_type = 'range_bound'
        self.last_market_type = 'range_bound'
        self.market_types = ['range_bound', 'trending_up', 'trending_down']
        
        # 网格交易参数（3分钟交易间隔）
        self.grid_levels = 40  # 网格层数（增加层数以适应横盘市场）
        self.grid_spacing = 0.0040  # 0.0400% 网格间距（基准参数）
        self.grids = self._create_grids()
        self.last_grid_index = self.grid_levels  # 初始在中间网格
        
        # 风险控制参数
        self.stop_loss_threshold = 0.02  # 2%止损
        self.take_profit_threshold = 0.025  # 2.5%止盈
        self.max_position_percentage = 0.8  # 最大持仓比例（横盘市场可以更高）
        self.reserve_balance_percentage = 0.2  # 保留资金比例（横盘市场可以更低）
        self.max_drawdown = 0.1  # 最大回撤限制
        
        # 下跌市场特定参数
        self.downward_trend_count = 0  # 下跌趋势计数
        self.max_downward_trend_count = 10  # 最大下跌趋势计数
        self.downward_buy_levels = []  # 下跌买入点位
        self.downward_buy_amounts = []  # 对应买入金额
        self.downward_buy_executed = []  # 已执行的买入点位
        
        # 反转策略参数（用于下跌市场）
        self.reversal_threshold = 0.015  # 反转阈值（1.5%）
        self.min_buy_amount = 200  # 最小买入金额（增加）
        self.max_buy_amount = 2000  # 最大买入金额（增加）
        self.buy_amount_step = 200  # 买入金额步长（增加）
        self.buy_count = 0  # 买入次数
        self.max_buy_count = 5  # 最大买入次数
        
        # 技术指标参数
        self.rsi_period = 14  # RSI周期
        self.macd_fast = 12  # MACD快速周期
        self.macd_slow = 26  # MACD慢速周期
        self.macd_signal = 9  # MACD信号周期
        self.bollinger_period = 20  # 布林带周期
        self.bollinger_std = 2  # 布林带标准差
        self.atr_period = 14  # ATR周期
        
        # 机器学习模型
        self.market_classifier = RandomForestClassifier(n_estimators=100, random_state=42)
        self.reversal_classifier = RandomForestClassifier(n_estimators=100, random_state=42)
        self.grid_spacing_optimizer = RandomForestRegressor(n_estimators=100, random_state=42)
        self.fund_allocation_optimizer = RandomForestRegressor(n_estimators=100, random_state=42)
        self.scaler = StandardScaler()
        self.model_trained = False
        self.model_data = []
        self.model_labels = []
        self.reversal_data = []
        self.reversal_labels = []
        self.grid_spacing_data = []
        self.grid_spacing_labels = []
        self.fund_allocation_data = []
        self.fund_allocation_labels = []
        self.model_training_count = 0
        
        # 横盘市场特定参数
        self.min_grid_spacing = 0.003  # 最小网格间距
        self.max_grid_spacing = 0.005  # 最大网格间距
        self.min_reserve_percentage = 0.1  # 最小保留资金比例
        self.max_reserve_percentage = 0.3  # 最大保留资金比例
        
        # 市场状态参数
        self.market_state_params = {
            'range_bound': {
                'grid_spacing': 0.0040,  # 0.0400% 网格间距（基准参数）
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
        
        # 黄金分割参数
        self.golden_ratio = 0.618
        self.golden_points = [0.25, 0.5, 0.75]  # 四分之一、二分之一、四分之三（更积极的卖出策略）
        
        # 协变因子最优化参数
        self.covariance_window = 20  # 协方差计算窗口
        self.optimization_period = 50  # 优化周期
        self.optimization_count = 0  # 优化计数
        self.best_params = {
            'grid_spacing': 0.0040,  # 0.0400% 网格间距（基准参数）
            'max_position_percentage': 0.8,
            'reserve_balance_percentage': 0.2,
            'take_profit_threshold': 0.025
        }
        
        # 性能跟踪
        self.trade_history = []
        self.grid_adjustment_count = 0
        self.highest_balance = initial_balance
        
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
        
        # 使用最近20天的价格计算区间
        recent_prices = data.iloc[-20:]
        lower_bound = recent_prices.min()
        upper_bound = recent_prices.max()
        
        # 确保区间有一定宽度
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
    
    def _calculate_dynamic_buy_amount(self, current_price: float, lower_bound: float, upper_bound: float) -> float:
        """
        计算动态买入金额（价格越低，买入金额越大）
        
        Args:
            current_price: 当前价格
            lower_bound: 区间下限
            upper_bound: 区间上限
            
        Returns:
            买入金额
        """
        # 计算价格在区间中的位置（0-1）
        price_position = (current_price - lower_bound) / (upper_bound - lower_bound)
        # 价格越低，买入金额越大
        buy_amount_ratio = 1 - price_position
        # 计算买入金额
        buy_amount = self.min_buy_amount + buy_amount_ratio * (self.max_buy_amount - self.min_buy_amount)
        # 确保买入金额在合理范围内
        return max(self.min_buy_amount, min(self.max_buy_amount, buy_amount))
    
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
    
    def _extract_features(self, data: pd.Series) -> List[float]:
        """
        提取特征用于市场类型分类和反转信号检测
        
        Args:
            data: 价格数据
            
        Returns:
            特征列表
        """
        if len(data) < 20:
            return [0] * 21  # 返回默认特征
        
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
        # 1. RSI低于40（超卖）
        # 2. MACD柱状图由负转正或 histogram > 0
        # 3. 价格触及布林带下轨或在支撑位附近
        # 4. 价格出现上涨趋势
        
        reversal = False
        
        # 超卖条件
        if rsi < 40:
            # MACD金叉或柱状图为正
            if (histogram > 0 and macd > signal) or histogram > 0:
                # 价格触及布林带下轨
                if data.iloc[-1] < lower_band * 1.01:
                    # 价格出现上涨趋势
                    if price_change > 0:
                        reversal = True
        
        return reversal
    
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
        sharpe_ratio = mean_return / std_return if std_return > 0 else 0
        max_drawdown = (returns.cummax() - returns).max()
        
        # 定义目标收益和风险
        target_return = 0.08  # 目标年化收益率 = 8%
        target_sharpe = 2.5  # 目标夏普比率 = 2.0-3.0
        target_max_drawdown = 0.10  # 目标最大回撤 ≤10%
        
        # 定义参数搜索空间（更激进的参数）
        # 网格间距：更小的间距，增加交易频率
        grid_spacings = [0.0005, 0.0008, 0.001, 0.0012, 0.0015, 0.0018, 0.002]
        # 止盈阈值：更高的止盈，增加每笔收益
        take_profit_thresholds = [0.02, 0.025, 0.03, 0.035, 0.04, 0.045, 0.05]
        # 资金管理参数：更高的仓位，提高资金利用率
        max_position_percentages = [0.8, 0.85, 0.9, 0.95, 0.98]
        # 保留资金：更少的保留，提高资金利用率
        reserve_balance_percentages = [0.05, 0.1, 0.15]
        
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
                        expected_max_drawdown = expected_risk * 1.5  # 更保守的最大回撤估算
                        
                        # 计算与目标的差距
                        return_gap = abs(expected_return - target_return)
                        sharpe_gap = abs(expected_sharpe - target_sharpe)
                        drawdown_gap = abs(expected_max_drawdown - target_max_drawdown)
                        
                        # 计算参数得分（更注重收益率和夏普比率）
                        score = (1 - return_gap) * (1 - sharpe_gap) * (1 - drawdown_gap) * (1 + expected_return * 200) * (1 + expected_sharpe * 20)
                        
                        # 选择得分最高的参数组合
                        if score > best_score:
                            best_score = score
                            best_params = {
                                'grid_spacing': grid_spacing,
                                'max_position_percentage': max_position,
                                'reserve_balance_percentage': reserve_balance,
                                'take_profit_threshold': take_profit
                            }
        
        return best_params
    
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
    
    def _train_models(self):
        """
        训练机器学习模型
        """
        # 训练市场类型分类模型
        if len(self.model_data) >= 100:
            # 准备训练数据
            X = np.array(self.model_data)
            y = np.array([self.market_types.index(label) for label in self.model_labels])
            
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
        
        if len(self.model_data) >= 100 or len(self.reversal_data) >= 100 or len(self.grid_spacing_data) >= 100 or len(self.fund_allocation_data) >= 100:
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
        if len(self.model_data) % 30 == 0:
            self._train_models()
        
        # 使用模型预测市场类型
        if self.model_trained:
            features_scaled = self.scaler.transform([features])
            prediction = self.market_classifier.predict(features_scaled)[0]
            predicted_type = self.market_types[prediction]
            return predicted_type
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
        
        # 检测市场类型
        if data is not None:
            self.last_market_type = self.market_type
            self.market_type = self.detect_market_type(data)
            
            # 协变因子最优化：定期更新参数
            self.optimization_count += 1
            if self.optimization_count % self.optimization_period == 0:
                # 找到最优参数组合
                optimal_params = self._find_optimal_parameters(data)
                # 更新参数
                self.grid_spacing = optimal_params['grid_spacing']
                self.max_position_percentage = optimal_params['max_position_percentage']
                self.reserve_balance_percentage = optimal_params['reserve_balance_percentage']
                self.take_profit_threshold = optimal_params['take_profit_threshold']
                # 重新创建网格
                self.grids = self._create_grids()
                self.best_params = optimal_params
            
            # 根据市场状态调整参数
            if self.market_type in self.market_state_params:
                params = self.market_state_params[self.market_type]
                # 结合最优参数和市场状态参数
                self.grid_spacing = (self.grid_spacing + params['grid_spacing']) / 2
                self.max_position_percentage = (self.max_position_percentage + params['max_position_percentage']) / 2
                self.reserve_balance_percentage = (self.reserve_balance_percentage + params['reserve_balance_percentage']) / 2
                self.take_profit_threshold = (self.take_profit_threshold + params['take_profit_threshold']) / 2
                # 重新创建网格
                self.grids = self._create_grids()
            
            # 使用机器学习优化网格间距
            if self.market_type == 'range_bound':
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
            # 检测反转信号并买入
            if data is not None and len(data) > 30 and self.position < max_position and self.buy_count < self.max_buy_count:
                if self._detect_reversal(data):
                    # 检测到反转信号，买入
                    buy_amount = min(available_balance * 0.4, self.max_buy_amount)
                    if buy_amount > self.min_buy_amount:
                        buy_quantity = buy_amount / current_price
                        if buy_quantity > 0.01:
                            self.position += buy_quantity
                            self.current_balance -= buy_amount
                            if self.entry_price == 0:
                                self.entry_price = current_price
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
            if self.position > 0 and current_price > self.entry_price * 1.015:
                # 价格反弹1.5%以上，卖出全部
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
            if data is not None and len(data) > 10 and self.position < max_position:
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
        else:
            # 非下跌市场：使用正常网格交易
            if self.market_type == 'range_bound':
                # 横盘市场：使用MLRangeGridTrading策略的高频交易策略
                # 计算横盘区间边界和黄金分割点
                price_series = pd.Series(self.price_history)
                lower_bound, upper_bound = self._calculate_range_boundaries(price_series)
                golden_points = self._calculate_golden_points(lower_bound, upper_bound)
                
                if grid_change < 0 and self.position < max_position:
                    # 价格下跌到更低网格 -> 买入（低买）
                    # 计算动态买入金额：价格越低，买入金额越大
                    buy_amount = self._calculate_dynamic_buy_amount(current_price, lower_bound, upper_bound)
                    # 限制买入金额不超过可用资金的15%
                    buy_amount = min(buy_amount, available_balance * 0.15)
                    if buy_amount > self.min_buy_amount:
                        buy_quantity = buy_amount / current_price
                        if buy_quantity > 0.01:
                            # 计算实际买入金额
                            actual_buy_amount = buy_quantity * current_price
                            # 确保实际买入金额不超过可用资金
                            actual_buy_amount = min(actual_buy_amount, available_balance)
                            # 重新计算买入数量
                            buy_quantity = actual_buy_amount / current_price
                            if buy_quantity > 0.01:
                                self.position += buy_quantity
                                self.current_balance -= actual_buy_amount
                                if self.entry_price == 0:
                                    self.entry_price = current_price
                                self.last_buy_price = current_price
                                self.last_grid_index = current_grid_index
                                self.last_price = current_price
                                self.trade_history.append("buy")
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
                    # 横盘市场：基于黄金分割点的卖出策略
                    # 计算当前价格在区间中的位置
                    price_position = (current_price - lower_bound) / (upper_bound - lower_bound)
                    
                    # 基于黄金分割点的卖出策略（更积极）
                    if current_price > golden_points[0] and current_price <= golden_points[1]:
                        # 四分之一处：中量卖出（40%）
                        sell_quantity = self.position * 0.4
                    elif current_price > golden_points[1] and current_price <= golden_points[2]:
                        # 二分之一处：大量卖出（60%）
                        sell_quantity = self.position * 0.6
                    elif current_price > golden_points[2]:
                        # 四分之三处：全部卖出（100%）
                        sell_quantity = self.position
                    else:
                        # 价格较低：少量卖出（20%）
                        sell_quantity = self.position * 0.2
                    
                    if sell_quantity > 0.01:
                        sell_amount = sell_quantity * current_price
                        # 卖出条件：价格高于买入价格
                        if current_price > self.last_buy_price * 1.0005:  # 确保有微小盈利
                            self.position -= sell_quantity
                            self.current_balance += sell_amount
                            self.last_grid_index = current_grid_index
                            self.last_price = current_price
                            self.total_trades += 1
                            self.winning_trades += 1
                            self.profit_history.append(sell_amount - sell_quantity * self.last_buy_price)
                            self.trade_history.append("sell")
                            return {
                                "action": "sell",
                                "quantity": sell_quantity,
                                "price": current_price,
                                "balance": self.current_balance,
                                "position": self.position,
                                "reason": "grid_sell"
                            }
                
                # 横盘市场的额外交易策略：基于价格动量
                if len(self.price_history) > 5:
                    recent_prices = self.price_history[-5:]
                    price_range = max(recent_prices) - min(recent_prices)
                    price_mean = np.mean(recent_prices)
                    
                    # 如果价格在小范围内波动，执行高频交易
                    if price_range / price_mean < 0.01 and available_balance > 200:
                        if current_price < price_mean * 0.998:
                            # 价格低于均值，买入
                            buy_amount = min(available_balance * 0.1, 500)
                            if buy_amount > 50:
                                buy_quantity = buy_amount / current_price
                                if buy_quantity > 0.01:
                                    # 计算实际买入金额
                                    actual_buy_amount = buy_quantity * current_price
                                    # 确保实际买入金额不超过可用资金
                                    actual_buy_amount = min(actual_buy_amount, available_balance)
                                    # 重新计算买入数量
                                    buy_quantity = actual_buy_amount / current_price
                                    if buy_quantity > 0.01:
                                        self.position += buy_quantity
                                        self.current_balance -= actual_buy_amount
                                        if self.entry_price == 0:
                                            self.entry_price = current_price
                                        self.last_buy_price = current_price
                                        self.last_price = current_price
                                        self.trade_history.append("mean_reversion_buy")
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
                            sell_quantity = min(self.position * 0.2, 500 / current_price)
                            if sell_quantity > 0.01:
                                sell_amount = sell_quantity * current_price
                                self.position -= sell_quantity
                                self.current_balance += sell_amount
                                self.last_price = current_price
                                self.total_trades += 1
                                if current_price > self.entry_price:
                                    self.winning_trades += 1
                                    self.profit_history.append(sell_amount - sell_quantity * self.entry_price)
                                else:
                                    self.losing_trades += 1
                                    self.profit_history.append(sell_amount - sell_quantity * self.entry_price)
                                self.trade_history.append("mean_reversion_sell")
                                return {
                                    "action": "sell",
                                    "quantity": sell_quantity,
                                    "price": current_price,
                                    "balance": self.current_balance,
                                    "position": self.position,
                                    "reason": "mean_reversion_sell"
                                }
            else:
                # 上涨市场：使用正常网格交易
