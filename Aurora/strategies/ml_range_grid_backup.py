#!/usr/bin/env python3
"""
机器学习横盘网格交易策略备份
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Tuple, Optional
from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier
from sklearn.preprocessing import StandardScaler

class MLRangeGridTrading:
    """
    机器学习横盘网格交易策略
    专门针对横盘市场优化，使用机器学习自动优化网格步长和资金分配
    """
    
    def __init__(self, base_price: float, initial_balance: float = 100000):
        """
        初始化机器学习横盘网格交易策略
        
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
        self.entry_price = 0  # 入场价格
        self.consecutive_holds = 0  # 连续不交易次数
        
        # 网格交易参数（3分钟交易间隔）
        self.grid_levels = 40  # 网格层数
        self.grid_spacing = 0.0040  # 0.0400% 网格间距（基准参数）
        self.grids = self._create_grids()
        self.last_grid_index = self.grid_levels  # 初始在中间网格
        
        # 风险控制参数
        self.stop_loss_threshold = 0.005  # 止损阈值
        self.take_profit_threshold = 0.025  # 止盈阈值
        self.max_position_percentage = 0.8  # 最大持仓比例
        self.reserve_balance_percentage = 0.2  # 保留资金比例
        self.max_drawdown = 0.05  # 最大回撤限制
        
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
        self.atr_period = 14  # ATR周期
        self.ma_periods = [10, 30, 60, 120]  # 移动平均线周期
        
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
        self.model_training_count = 0
        
        # 性能跟踪
        self.trade_history = []
        self.profit_history = []
        self.grid_adjustment_count = 0
        self.highest_balance = initial_balance
        self.max_drawdown = 0
        self.drawdown_history = []
        self.sharpe_ratio = 0
        self.sortino_ratio = 0
        
        # 机器学习参数优化
        self.parameter_optimizer = RandomForestRegressor(n_estimators=200, random_state=42)
        self.parameter_data = []
        self.parameter_labels = []
        
        # 目标指标
        self.target_return = 0.18  # 目标年化收益率18%（8-28%）
        self.target_sharpe = 2.5  # 目标夏普比率2.5（2.0-3.0）
        self.target_sortino = 3.5  # 目标索提诺比率3.5（>3.0）
        
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
        
        # 动态买入量参数（分钟级高频交易）
        self.min_buy_amount = 100  # 减小最小买入金额
        self.max_buy_amount = 1000  # 减小最大买入金额
        self.buy_amount_step = 100  # 减小买入金额步长
        
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
    
    def _calculate_ma(self, data: pd.Series, period: int) -> float:
        """
        计算移动平均线
        
        Args:
            data: 价格数据
            period: 周期
            
        Returns:
            移动平均线值
        """
        if len(data) < period:
            return data.iloc[-1] if len(data) > 0 else 0
        return data.rolling(window=period).mean().iloc[-1]
    
    def _calculate_kdj(self, data: pd.Series, n=9, m1=3, m2=3) -> Tuple[float, float, float]:
        """
        计算KDJ指标
        
        Args:
            data: 价格数据
            n: 周期
            m1: 快线平滑周期
            m2: 慢线平滑周期
            
        Returns:
            K, D, J值
        """
        if len(data) < n:
            return 50, 50, 50
        
        low = data.rolling(window=n).min()
        high = data.rolling(window=n).max()
        rsv = (data - low) / (high - low) * 100
        
        k = rsv.ewm(alpha=1/m1, adjust=False).mean()
        d = k.ewm(alpha=1/m2, adjust=False).mean()
        j = 3 * k - 2 * d
        
        return k.iloc[-1], d.iloc[-1], j.iloc[-1]
    
    def _calculate_mfi(self, data: pd.Series, volume: pd.Series, period=14) -> float:
        """
        计算MFI指标
        
        Args:
            data: 价格数据
            volume: 成交量数据
            period: 周期
            
        Returns:
            MFI值
        """
        if len(data) < period or len(volume) < period:
            return 50
        
        typical_price = (data + data + data) / 3  # 简化计算，实际应该是(high+low+close)/3
        money_flow = typical_price * volume
        
        positive_flow = money_flow.where(typical_price > typical_price.shift(1), 0)
        negative_flow = money_flow.where(typical_price < typical_price.shift(1), 0)
        
        positive_sum = positive_flow.rolling(window=period).sum()
        negative_sum = negative_flow.rolling(window=period).sum()
        
        if negative_sum.iloc[-1] == 0:
            return 100
        
        mfi = 100 - (100 / (1 + positive_sum.iloc[-1] / negative_sum.iloc[-1]))
        return mfi
    
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
    
    def _extract_features(self, data: pd.Series) -> List[float]:
        """
        提取特征用于机器学习
        
        Args:
            data: 价格数据
            
        Returns:
            特征列表
        """
        if len(data) < 20:
            return [0] * 33  # 返回默认特征（增加了KDJ、移动平均线等特征）
        
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
        
        # 计算KDJ指标
        k, d, j = self._calculate_kdj(data)
        
        # 计算移动平均线
        ma_values = []
        for period in self.ma_periods:
            ma_value = self._calculate_ma(data, period)
            ma_values.append(ma_value / data.iloc[-1] if data.iloc[-1] > 0 else 0)
        
        # 计算移动平均线斜率
        ma_slopes = []
        for i, period in enumerate(self.ma_periods):
            if len(data) > period + 10:
                ma_current = self._calculate_ma(data.iloc[-period:], period)
                ma_past = self._calculate_ma(data.iloc[-period-10:-10], period)
                slope = (ma_current - ma_past) / ma_past if ma_past > 0 else 0
                ma_slopes.append(slope)
            else:
                ma_slopes.append(0)
        
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
            k,  # 添加KDJ指标
            d,
            j,
            ma_values[0],  # 10日均线
            ma_values[1],  # 30日均线
            ma_values[2],  # 60日均线
            ma_values[3],  # 120日均线
            ma_slopes[0],  # 10日均线斜率
            ma_slopes[1],  # 30日均线斜率
            ma_slopes[2],  # 60日均线斜率
            ma_slopes[3],  # 120日均线斜率
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
        
        # 计算横盘区间边界和黄金分割点
        price_series = pd.Series(self.price_history)
        lower_bound, upper_bound = self._calculate_range_boundaries(price_series)
        golden_points = self._calculate_golden_points(lower_bound, upper_bound)
        
        # 网格交易核心逻辑
        grid_change = current_grid_index - self.last_grid_index
        
        # 横盘市场的高频交易策略
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
            if self.market_type == 'range_bound':
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
            else:
                # 非横盘市场：按照传统网格策略卖出
                # 计算卖出数量：基于网格变化和当前持仓
                sell_quantity = min(abs(grid_change) * 400 / current_price, self.position)
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
                        # 卖出条件：价格高于买入价格
                        if current_price > self.last_buy_price * 1.0005:  # 确保有微小盈利
                            self.position -= sell_quantity
                            self.current_balance += sell_amount
                            self.last_price = current_price
                            self.total_trades += 1
                            self.winning_trades += 1
                            self.profit_history.append(sell_amount - sell_quantity * self.last_buy_price)
                            self.trade_history.append("mean_reversion_sell")
                            return {
                                "action": "sell",
                                "quantity": sell_quantity,
                                "price": current_price,
                                "balance": self.current_balance,
                                "position": self.position,
                                "reason": "mean_reversion_sell"
                            }
        
        # 横盘市场的额外交易策略：基于布林带
        if self.market_type == 'range_bound' and len(self.price_history) > self.bollinger_period:
            price_series = pd.Series(self.price_history)
            upper_band, middle_band, lower_band = self._calculate_bollinger_bands(price_series)
            
            # 价格接近下轨，买入
            if current_price < lower_band * 1.001 and available_balance > 200:
                buy_amount = min(available_balance * 0.15, 800)
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
                            self.trade_history.append("bollinger_buy")
                            return {
                                "action": "buy",
                                "quantity": buy_quantity,
                                "price": current_price,
                                "balance": self.current_balance,
                                "position": self.position,
                                "reason": "bollinger_buy"
                            }
            # 价格接近上轨，卖出
            elif current_price > upper_band * 0.999 and self.position > 0:
                sell_quantity = min(self.position * 0.3, 800 / current_price)
                if sell_quantity > 0.01:
                    sell_amount = sell_quantity * current_price
                    # 卖出条件：价格高于买入价格
                    if current_price > self.last_buy_price * 1.0005:  # 确保有微小盈利
                        self.position -= sell_quantity
                        self.current_balance += sell_amount
                        self.last_price = current_price
                        self.total_trades += 1
                        self.winning_trades += 1
                        self.profit_history.append(sell_amount - sell_quantity * self.last_buy_price)
                        self.trade_history.append("bollinger_sell")
                        return {
                            "action": "sell",
                            "quantity": sell_quantity,
                            "price": current_price,
                            "balance": self.current_balance,
                            "position": self.position,
                            "reason": "bollinger_sell"
                        }
        
        # 更新最后价格
        self.last_price = current_price
        
        return {"action": "hold", "balance": self.current_balance, "position": self.position}
    
    def get_performance(self) -> Dict[str, float]:
        """
        获取策略性能指标
        
        Returns:
            性能指标字典
        """
        # 计算总收益率
        total_return = (self.current_balance - self.initial_balance) / self.initial_balance
        
        # 计算胜率
        win_rate = self.winning_trades / self.total_trades if self.total_trades > 0 else 0
        
        # 计算平均每笔交易收益率
        avg_trade_return = sum(self.profit_history) / self.initial_balance / self.total_trades if self.total_trades > 0 else 0
        
        # 计算最大回撤
        if self.trade_history:
            balance_history = [self.initial_balance]
            current_balance = self.initial_balance
            for i, trade in enumerate(self.trade_history):
                if trade in ["buy"]:
                    current_balance -= self.profit_history[i] if i < len(self.profit_history) else 0
                elif trade in ["sell", "take_profit", "stop_loss", "mean_reversion_sell", "bollinger_sell"]:
                    current_balance += self.profit_history[i] if i < len(self.profit_history) else 0
                balance_history.append(current_balance)
            
            # 计算最大回撤
            peak = balance_history[0]
            max_drawdown = 0
            for balance in balance_history[1:]:
                if balance > peak:
                    peak = balance
                drawdown = (peak - balance) / peak
                if drawdown > max_drawdown:
                    max_drawdown = drawdown
            self.max_drawdown = max_drawdown
        
        # 计算夏普比率和索提诺比率
        if len(self.profit_history) > 1:
            # 假设风险-free利率为0
            returns = pd.Series(self.profit_history) / self.initial_balance
            self.sharpe_ratio = self._calculate_sharpe_ratio(returns)
            self.sortino_ratio = self._calculate_sortino_ratio(returns)
        
        return {
            "total_return": total_return,
            "win_rate": win_rate,
            "total_trades": self.total_trades,
            "avg_trade_return": avg_trade_return,
            "max_drawdown": self.max_drawdown,
            "sharpe_ratio": self.sharpe_ratio,
            "sortino_ratio": self.sortino_ratio,
            "final_balance": self.current_balance,
            "grid_adjustment_count": self.grid_adjustment_count,
            "model_training_count": self.model_training_count
        }
