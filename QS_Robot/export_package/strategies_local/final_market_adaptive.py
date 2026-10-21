#!/usr/bin/env python3
"""
最终市场自适应网格交易策略
强化学习优化版本 - 支持参数持久化
集成全局ML管理器和金融数据层
"""

import numpy as np
import pandas as pd
import pickle
import os
import sys
import json
from typing import List, Dict, Tuple, Optional
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.preprocessing import StandardScaler

try:
    from .final_market_classifier import MarketClassifier
    from .final_grid_executor import GridExecutor
except ImportError:
    from final_market_classifier import MarketClassifier
    from final_grid_executor import GridExecutor

# 导入全局ML管理器和数据提供者
try:
    # 添加Aurora根目录到路径
    aurora_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    if aurora_root not in sys.path:
        sys.path.insert(0, aurora_root)
    
    from ml import get_ml_manager, MLManager
    from data import get_data_provider, DataProvider
    GLOBAL_ML_AVAILABLE = True
    print("[INFO] 已成功连接全局ML管理器和数据提供者")
except ImportError as e:
    print(f"[WARN] 无法导入全局ML模块: {e}")
    GLOBAL_ML_AVAILABLE = False
    MLManager = None
    DataProvider = None
    get_ml_manager = lambda: None
    get_data_provider = lambda: None

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
        self.market_types = ['range_bound', 'trending_up', 'trending_down', 'volatile']
        
        # 连接全局ML管理器和数据提供者
        self.ml_manager = get_ml_manager()
        self.data_provider = get_data_provider()
        
        # 从全局ML管理器获取模型
        if self.ml_manager:
            self.regime_detector = self.ml_manager.get_model('regime_detector')
            self.trend_predictor = self.ml_manager.get_model('trend_predictor')
            self.market_state_analyzer = self.ml_manager.get_model('market_state_analyzer')
            self.market_classifier = self.ml_manager.get_model('market_classifier')
            self.grid_optimizer = self.ml_manager.get_model('grid_optimizer')
            self.fund_allocator = self.ml_manager.get_model('fund_allocator')
            print("[INFO] 已连接全局ML管理器: regime_detector, trend_predictor, market_state_analyzer")
        else:
            self.regime_detector = None
            self.trend_predictor = None
            self.market_state_analyzer = None
            self.market_classifier = None
            self.grid_optimizer = None
            self.fund_allocator = None
            print("[WARN] 未连接全局ML管理器，使用本地模型")
        
        # 网格交易参数（分钟级交易）
        self.grid_levels = 100  # 网格层数（增加层数以适应高频交易）
        self.grid_spacing = 0.0015  # 0.15% 网格间距（小于典型波动率）
        self.grids = self._create_grids()
        self.last_grid_index = self.grid_levels  # 初始在中间网格

        self.grid_exec = GridExecutor(base_price, initial_balance)
        
        # 风险控制参数
        self.stop_loss_threshold = 0.008  # 0.8%止损（缩小止损提高灵敏度）
        self.take_profit_threshold = 0.01  # 1%止盈（缩小止盈提高交易频率）
        self.max_position_percentage = 0.8  # 最大持仓比例（保留20%作为风险储备金）
        self.reserve_balance_percentage = 0.2  # 风险储备金比例（用于下跌承接）
        self.max_drawdown = 0.08  # 最大回撤限制
        
        # 下跌市场特定参数
        self.downward_trend_count = 0  # 下跌趋势计数
        self.max_downward_trend_count = 10  # 最大下跌趋势计数
        self.downward_buy_levels = []  # 下跌买入点位
        self.downward_buy_amounts = []  # 对应买入金额
        self.downward_buy_executed = []  # 已执行的买入点位
        
        # 反转策略参数（用于下跌市场）
        self.reversal_threshold = 0.015  # 反转阈值（1.5%）
        self.min_buy_amount = 200  # 最小买入金额
        self.max_buy_amount = 5000  # 最大买入金额（增加用于下跌承接）
        self.buy_amount_step = 300  # 买入金额步长
        self.buy_count = 0  # 买入次数
        self.max_buy_count = 8  # 最大买入次数（增加以支持金字塔建仓）
        
        # 下跌承接策略参数
        self.accumulation_fund = 0  # 风险储备金（专门用于下跌承接）
        self.accumulation_enabled = True  # 是否启用下跌承接
        self.last_accumulation_price = base_price  # 上次承接价格
        self.accumulation_level = 0  # 当前承接级别（0-5）
        
        # 金字塔建仓配置
        self.constellation_levels = [
            {'threshold': 0.02, 'allocation': 0.1, 'max_position': 0.15},   # 下跌2%，买入10%资金，仓位上限15%
            {'threshold': 0.04, 'allocation': 0.15, 'max_position': 0.35},  # 下跌4%，买入15%资金，仓位上限35%
            {'threshold': 0.06, 'allocation': 0.2, 'max_position': 0.55},   # 下跌6%，买入20%资金，仓位上限55%
            {'threshold': 0.08, 'allocation': 0.25, 'max_position': 0.75},  # 下跌8%，买入25%资金，仓位上限75%
            {'threshold': 0.10, 'allocation': 0.3, 'max_position': 1.0},    # 下跌10%，买入30%资金，仓位上限100%
        ]
        
        # 技术指标参数
        self.rsi_period = 14  # RSI周期
        self.macd_fast = 12  # MACD快速周期
        self.macd_slow = 26  # MACD慢速周期
        self.macd_signal = 9  # MACD信号周期
        self.bollinger_period = 20  # 布林带周期
        self.bollinger_std = 2  # 布林带标准差
        self.atr_period = 14  # ATR周期
        
        # 机器学习模型
        self.market_clf = MarketClassifier()
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
            'take_profit_threshold': 0.025,
            'stop_loss_threshold': 0.008,  # 止损阈值
            'max_drawdown': 0.08  # 最大回撤限制 8%
        }
        
        # 性能跟踪
        self.trade_history = []
        self.grid_adjustment_count = 0
        self.highest_balance = initial_balance
        
        # 账户历史记录（用于计算回撤等指标）
        self.balance_history = [initial_balance]
        
        # 市场类型稳定性机制
        self.market_type_history = []  # 历史市场类型记录
        self.market_type_stable_count = 0  # 连续稳定次数
        self.market_type_switch_count = 0  # 切换次数统计
        self.min_stable_periods = 10  # 最小稳定周期数才认为市场类型真正改变
        
        # 初始化下跌买入点位
        self._init_downward_buy_levels()
        
        # ==================== 强化学习参数 ====================
        self.rl_agent = RLTradingAgent()
        self.rl_enabled = True
        self.rl_training_mode = True
        
        # ==================== 参数持久化 ====================
        self.persist_dir = 'strategy_params'
        self.persist_file = os.path.join(self.persist_dir, 'optimized_params.pkl')
        self.persist_history_file = os.path.join(self.persist_dir, 'training_history.json')
        
        # 加载已优化的参数
        self._load_optimized_params()
        
        # 训练统计
        self.training_episodes = 0
        self.best_total_return = -np.inf
        self.improvement_count = 0
        
        # 探索率（用于强化学习）
        self.exploration_rate = 0.3
        self.min_exploration_rate = 0.05
        self.exploration_decay = 0.995
        
        # 学习率
        self.learning_rate = 0.1
        self.min_learning_rate = 0.01
        self.learning_decay = 0.99
        
        # 性能缓存
        self.last_evaluation_metrics = None
    
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
    
    def _calculate_rsi(self, data: pd.Series, period: int = None) -> float:
        """
        计算RSI指标
        
        Args:
            data: 价格数据
            period: RSI周期，默认为self.rsi_period(14)
            
        Returns:
            RSI值
        """
        if period is None:
            period = self.rsi_period
        
        if len(data) < period + 1:
            return 50  # 默认值
        
        delta = data.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean().iloc[-1]
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean().iloc[-1]
        
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
        
        high = data.rolling(window=2).max()
        low = data.rolling(window=2).min()
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
        
        variance = returns.var()
        cov_matrix = np.array([[variance]])
        return cov_matrix
    
    def _label_reversal(self, data: pd.Series, volume: pd.Series = None) -> bool:
        """
        标记反转信号（增强版：多指标协同判断）

        Args:
            data: 价格数据
            volume: 成交量数据（可选）。传入时使用真实量比判断放量；
                    未传入时不再用价格波动冒充成交量，改用价格K线确认。

        Returns:
            是否为反转信号
        """
        if len(data) < 30:
            return False
        
        # 计算多周期RSI
        rsi_7 = self._calculate_rsi(data, period=7)
        rsi_14 = self._calculate_rsi(data, period=14)
        rsi_28 = self._calculate_rsi(data, period=28)
        
        # 计算MACD
        macd, signal, histogram = self._calculate_macd(data)
        
        # 计算布林带
        upper_band, middle_band, lower_band = self._calculate_bollinger_bands(data)
        
        # 计算价格变化
        price_change = (data.iloc[-1] - data.iloc[-2]) / data.iloc[-2] if len(data) > 1 else 0
        price_change_5d = (data.iloc[-1] - data.iloc[-6]) / data.iloc[-6] if len(data) > 5 else 0
        
        # 检测反转信号 - 多重确认机制
        # 1. 极端超卖信号：RSI多周期协同
        extreme_oversold = rsi_7 < 25 and rsi_14 < 30 and rsi_28 < 45
        
        # 2. 成交量放大确认
        # TODO: 需要在调用处传入与 data 对齐的真实 volume 序列后，量比判断才生效。
        # 历史bug：原 volume_surge = abs(price_change) > 0.01 是用价格波动冒充成交量，
        # 已废弃。接入真实量时按"当前量 > 20日均量×1.5"判断；未接入时改用价格K线确认。
        if volume is not None and len(volume) >= 20:
            try:
                avg_vol_20 = float(volume.iloc[-21:-1].mean())
                cur_vol = float(volume.iloc[-1])
                volume_surge = bool(avg_vol_20 > 0 and cur_vol > avg_vol_20 * 1.5)
            except Exception:
                volume_surge = False
        else:
            # 无真实成交量：用价格确认替代（连续2根阳线且当前收涨），而非价格波动冒充量能
            volume_surge = False
            if len(data) >= 3:
                up_bars = sum(1 for i in range(-2, 0) if data.iloc[i] > data.iloc[i - 1])
                volume_surge = (up_bars >= 2) and (price_change > 0)
        
        # 3. MACD确认：柱状图由负转正
        macd_confirm = histogram > 0 and macd > signal
        
        # 4. 支撑位反弹：价格接近布林带下轨
        near_lower_band = data.iloc[-1] < lower_band * 1.02
        
        # 5. 连续下跌后反转检测
        consecutive_downs = 0
        if len(data) >= 10:
            for i in range(len(data)-10, len(data)-1):
                if data.iloc[i] < data.iloc[i-1]:
                    consecutive_downs += 1
        consecutive_reversal = consecutive_downs >= 5 and price_change > 0.002
        
        # 6. 价格动量确认
        momentum_confirm = price_change > 0.005
        
        # 综合判断：多个条件协同确认
        reversal = False
        
        # 强信号：极端超卖 + MACD确认 + 成交量放大
        if extreme_oversold and macd_confirm and volume_surge:
            reversal = True
        
        # 中信号：支撑位反弹 + RSI超卖 + 动量确认
        if near_lower_band and rsi_14 < 35 and momentum_confirm:
            reversal = True
        
        # 弱信号：连续下跌反转 + 成交量确认
        if consecutive_reversal and volume_surge and rsi_7 < 30:
            reversal = True
        
        # 额外确认：多周期RSI超卖
        oversold_count = sum(1 for rsi in [rsi_7, rsi_14, rsi_28] if rsi < 35)
        if oversold_count >= 2 and histogram > 0 and price_change > 0:
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
                        expected_return = take_profit - 0.001
                        expected_risk = std_return * np.sqrt(252)
                        expected_sharpe = expected_return / expected_risk if expected_risk > 0 else 0
                        expected_max_drawdown = expected_risk * 0.8
                        
                        return_gap = abs(expected_return - target_return) / target_return if target_return > 0 else abs(expected_return - target_return)
                        sharpe_gap = abs(expected_sharpe - target_sharpe) / target_sharpe if target_sharpe > 0 else abs(expected_sharpe - target_sharpe)
                        drawdown_gap = abs(expected_max_drawdown - target_max_drawdown) / target_max_drawdown if target_max_drawdown > 0 else abs(expected_max_drawdown - target_max_drawdown)
                        
                        weights = [0.3, 0.4, 0.3]
                        score = (1 - return_gap) * weights[0] + (1 - sharpe_gap) * weights[1] + (1 - drawdown_gap) * weights[2]
                        
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
        features = self.market_clf._extract_features(data)
        
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
            if len(self.grid_spacing_data) >= 100:
                X = np.array(self.grid_spacing_data)
                y = np.array(self.grid_spacing_labels)
                X_scaled = self.scaler.fit_transform(X)
                self.grid_spacing_optimizer.fit(X_scaled, y)
                self.model_trained = True
                self.model_training_count += 1
        
        # 使用模型预测最优网格间距
        if self.model_trained:
            try:
                features_scaled = self.scaler.transform([features])
                predicted_spacing = self.grid_spacing_optimizer.predict(features_scaled)[0]
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
        features = self.market_clf._extract_features(data)
        
        # 计算RSI
        rsi = self._calculate_rsi(data)
        
        # 计算波动率
        volatility = data.iloc[-20:].pct_change().std()
        
        # 基于RSI和波动率计算资金分配
        if rsi < 30:
            max_position = min(0.9, self.max_position_percentage + 0.1)
            reserve_balance = max(self.min_reserve_percentage, self.reserve_balance_percentage - 0.1)
        elif rsi > 70:
            max_position = max(0.6, self.max_position_percentage - 0.1)
            reserve_balance = min(self.max_reserve_percentage, self.reserve_balance_percentage + 0.1)
        else:
            max_position = self.max_position_percentage
            reserve_balance = self.reserve_balance_percentage
        
        if volatility > 0.02:
            max_position = max(0.6, max_position - 0.1)
            reserve_balance = min(self.max_reserve_percentage, reserve_balance + 0.1)
        
        # 收集训练数据
        self.fund_allocation_data.append(features)
        self.fund_allocation_labels.append(max_position)
        
        if len(self.fund_allocation_data) % 30 == 0 and len(self.fund_allocation_data) >= 100:
            X = np.array(self.fund_allocation_data)
            y = np.array(self.fund_allocation_labels)
            X_scaled = self.scaler.fit_transform(X)
            self.fund_allocation_optimizer.fit(X_scaled, y)
            self.model_trained = True
            self.model_training_count += 1
        
        if self.model_trained:
            try:
                features_scaled = self.scaler.transform([features])
                predicted_max_position = self.fund_allocation_optimizer.predict(features_scaled)[0]
                predicted_max_position = max(0.5, min(0.9, predicted_max_position))
                predicted_reserve_balance = 1 - predicted_max_position * 0.8
                predicted_reserve_balance = max(self.min_reserve_percentage, min(self.max_reserve_percentage, predicted_reserve_balance))
                return predicted_max_position, predicted_reserve_balance
            except Exception:
                return max_position, reserve_balance
        else:
            return max_position, reserve_balance

    def detect_market_type(self, data: pd.Series) -> str:
        """
        检测市场类型（委托给MarketClassifier）
        """
        if len(data) < 60:
            return 'range_bound'

        predicted_type = self.market_clf.detect_market_type(data)

        if self.regime_detector is not None and len(data) > 100:
            try:
                returns = data.pct_change().dropna()
                volumes = np.ones(len(returns))
                if len(returns) % 100 == 0:
                    self.regime_detector.fit(returns, volumes)
                hmm_state = self.regime_detector.predict(returns, volumes)
                if hmm_state is not None:
                    hmm_label = self.regime_detector.regime_labels.get(hmm_state, 'CHOPPY_HIGH_VOL')
                    if hmm_label == 'CRISIS_MODE':
                        predicted_type = 'trending_down'
                    elif hmm_label == 'CHOPPY_HIGH_VOL':
                        predicted_type = 'volatile'
            except Exception as e:
                # FIX C6-20261020: 静默失败改为可见日志（豆包闸门）
                print(f"[WARN] final_market_adaptive: HMM市场预测失败, 沿用默认: {e}")

        self.market_type_history.append(predicted_type)
        if len(self.market_type_history) > 20:
            self.market_type_history.pop(0)

        if self.market_type and predicted_type != self.market_type:
            self.market_type_stable_count = 0
            self.market_type_switch_count += 1
            recent_same = sum(1 for t in self.market_type_history[-self.min_stable_periods:] if t == predicted_type)
            if recent_same >= self.min_stable_periods // 2:
                market_names = {
                    'range_bound': '横盘市场', 'trending_up': '上涨市场',
                    'trending_down': '下跌市场', 'volatile': '波动市场'
                }
                print(f"[市场识别] 从 {market_names.get(self.market_type, self.market_type)} 切换到 {market_names.get(predicted_type, predicted_type)}")
                return predicted_type
            else:
                return self.market_type
        else:
            if predicted_type == self.market_type:
                self.market_type_stable_count += 1

        return self.market_type if self.market_type else predicted_type
    
    def _detect_reversal(self, data: pd.Series, volume: pd.Series = None) -> bool:
        """
        检测反转信号（使用机器学习）

        Args:
            data: 价格数据
            volume: 成交量数据（可选，传入后用于真实量比确认）

        Returns:
            是否检测到反转信号
        """
        if len(data) < 30:
            return False

        features = self.market_clf._extract_features(data)
        true_label = self._label_reversal(data, volume)
        
        self.reversal_data.append(features)
        self.reversal_labels.append(true_label)
        
        if len(self.reversal_data) % 30 == 0 and len(self.reversal_data) >= 100:
            X = np.array(self.reversal_data)
            y = np.array(self.reversal_labels)
            X_scaled = self.scaler.fit_transform(X)
            self.reversal_classifier.fit(X_scaled, y)
            self.model_trained = True
            self.model_training_count += 1
        
        try:
            if self.model_trained:
                features_scaled = self.scaler.transform([features])
                return self.reversal_classifier.predict(features_scaled)[0]
            else:
                return true_label
        except Exception:
            return true_label
    
    def set_active(self, active: bool):
        self.is_active = active
    
    def _detect_support_resistance(self, data: pd.Series) -> Dict[str, float]:
        if len(data) < 50:
            return {'support': 0, 'resistance': 0, 'fib_levels': []}
        recent_high = data.iloc[-50:].max()
        recent_low = data.iloc[-50:].min()
        range_size = recent_high - recent_low
        fib_levels = [
            recent_high - range_size * 0.236,
            recent_high - range_size * 0.382,
            recent_high - range_size * 0.5,
            recent_high - range_size * 0.618,
            recent_high - range_size * 0.786
        ]
        return {
            'support': recent_low,
            'resistance': recent_high,
            'fib_levels': fib_levels,
            'range_size': range_size
        }
    
    def _detect_wave_pattern(self, data: pd.Series) -> str:
        if len(data) < 20:
            return 'unknown'
        recent_data = data.iloc[-20:]
        peaks = []
        troughs = []
        for i in range(1, len(recent_data) - 1):
            if recent_data.iloc[i] > recent_data.iloc[i-1] and recent_data.iloc[i] > recent_data.iloc[i+1]:
                peaks.append(i)
            if recent_data.iloc[i] < recent_data.iloc[i-1] and recent_data.iloc[i] < recent_data.iloc[i+1]:
                troughs.append(i)
        if len(peaks) >= 3 and len(troughs) >= 2:
            if recent_data.iloc[-1] > recent_data.iloc[peaks[-2]]:
                return 'impulse'
            elif recent_data.iloc[-1] < recent_data.iloc[troughs[-1]]:
                return 'correction'
        return 'consolidation'
    
    def _check_trend_continuation(self, current_price: float, data: pd.Series) -> bool:
        if len(data) < 30:
            return False
        sma_short = data.rolling(window=5).mean().iloc[-1]
        sma_long = data.rolling(window=20).mean().iloc[-1]
        rsi = self._calculate_rsi(data)
        conditions = [
            sma_short > sma_long * 1.005,
            current_price > sma_short,
            rsi > 50 and rsi < 70
        ]
        return all(conditions)
    
    def update_price(self, current_price: float, data: pd.Series = None,
                     volume: pd.Series = None) -> Dict[str, any]:
        return self._update_price_impl(current_price, data, volume)

    def _update_price_impl(self, current_price: float, data: pd.Series = None,
                           volume: pd.Series = None) -> Dict[str, any]:
        # FIX 2026-10-21 审核：DataFrame→Series 适配（对齐 adaptive_range_grid 成熟模式）
        # 生产加载器传 DataFrame，本策略内部 RSI 等按 Series 假设，
        # 不转换会在生产逐 bar 调用时抛 ValueError 被降级捕获 → 策略从未真正运行。
        if data is not None and isinstance(data, pd.DataFrame):
            data = data['close'].copy()
        self.price_history.append(current_price)
        
        if data is not None:
            self.last_market_type = self.market_type
            self.market_type = self.detect_market_type(data)
            if self.market_type != self.last_market_type:
                market_names = {
                    'range_bound': '横盘市场',
                    'trending_up': '上涨市场',
                    'trending_down': '下跌市场',
                    'volatile': '波动市场'
                }
                print(f"[市场识别] 从 {market_names.get(self.last_market_type, self.last_market_type)} 切换到 {market_names.get(self.market_type, self.market_type)}")
            
            self.optimization_count += 1
            if self.optimization_count % self.optimization_period == 0:
                optimal_params = self._find_optimal_parameters(data)
                self.grid_spacing = optimal_params['grid_spacing']
                self.max_position_percentage = optimal_params['max_position_percentage']
                self.reserve_balance_percentage = optimal_params['reserve_balance_percentage']
                self.take_profit_threshold = optimal_params['take_profit_threshold']
                self.grids = self._create_grids()
                self.best_params = optimal_params
            
            if self.market_type in self.market_state_params:
                params = self.market_state_params[self.market_type]
                self.grid_spacing = (self.grid_spacing + params['grid_spacing']) / 2
                self.max_position_percentage = (self.max_position_percentage + params['max_position_percentage']) / 2
                self.reserve_balance_percentage = (self.reserve_balance_percentage + params['reserve_balance_percentage']) / 2
                self.take_profit_threshold = (self.take_profit_threshold + params['take_profit_threshold']) / 2
                self.grids = self._create_grids()
            
            if self.market_type == 'range_bound':
                optimal_spacing = self._calculate_optimal_grid_spacing(data)
                if abs(optimal_spacing - self.grid_spacing) > 0.0001:
                    self.grid_spacing = optimal_spacing
                    self.grids = self._create_grids()
                    self.grid_adjustment_count += 1
            
            optimal_max_position, optimal_reserve = self._calculate_optimal_fund_allocation(data)
            if abs(optimal_max_position - self.max_position_percentage) > 0.01:
                self.max_position_percentage = optimal_max_position
                self.reserve_balance_percentage = optimal_reserve
        
        price_change = (current_price - self.last_price) / self.last_price if self.last_price > 0 else 0
        current_total = self.current_balance + (self.position * current_price if self.position > 0 else 0)
        
        if current_total > self.highest_balance:
            self.highest_balance = current_total
        
        drawdown = (self.highest_balance - current_total) / self.highest_balance if self.highest_balance > 0 else 0
        if drawdown > self.max_drawdown:
            if self.position > 0:
                revenue = self.position * current_price
                self.current_balance += revenue
                quantity = self.position
                self.position = 0
                self.entry_price = 0
                self.last_price = current_price
                self.total_trades += 1
                self.losing_trades += 1
                self.buy_count = 0
                return {
                    "action": "sell",
                    "quantity": quantity,
                    "price": current_price,
                    "balance": self.current_balance,
                    "position": self.position,
                    "reason": "max_drawdown"
                }
        
        if self.position > 0 and self.entry_price > 0:
            loss_ratio = (current_price - self.entry_price) / self.entry_price
            if loss_ratio < -self.stop_loss_threshold:
                revenue = self.position * current_price
                self.current_balance += revenue
                quantity = self.position
                self.position = 0
                self.entry_price = 0
                self.last_price = current_price
                self.total_trades += 1
                self.losing_trades += 1
                self.buy_count = 0
                return {
                    "action": "sell",
                    "quantity": quantity,
                    "price": current_price,
                    "balance": self.current_balance,
                    "position": self.position,
                    "reason": "stop_loss"
                }
        
        if self.position > 0 and self.entry_price > 0:
            profit_ratio = (current_price - self.entry_price) / self.entry_price
            if profit_ratio > self.take_profit_threshold:
                revenue = self.position * current_price
                self.current_balance += revenue
                quantity = self.position
                self.position = 0
                self.entry_price = 0
                self.last_price = current_price
                self.total_trades += 1
                self.winning_trades += 1
                self.buy_count = 0
                return {
                    "action": "sell",
                    "quantity": quantity,
                    "price": current_price,
                    "balance": self.current_balance,
                    "position": self.position,
                    "reason": "take_profit"
                }
        
        available_balance = self.current_balance * (1 - self.reserve_balance_percentage)
        max_position = (available_balance * self.max_position_percentage) / current_price
        
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
                return {"action": "hold", "balance": self.current_balance, "position": self.position}
        
        grid_change = current_grid_index - self.last_grid_index
        
        if self.accumulation_fund == 0 and self.current_balance > 0:
            self.accumulation_fund = self.initial_balance * self.reserve_balance_percentage
        
        if self.market_type == 'trending_down':
            if data is not None:
                accumulation_result = self.grid_exec.pyramid_承接(data, self.current_balance, self.position)
                if accumulation_result is not None:
                    self.position += accumulation_result.get('quantity', 0) - self.position
                    self.current_balance -= accumulation_result.get('quantity', 0) * current_price
                    return accumulation_result
            
            if data is not None and len(data) > 30 and self.position < max_position and self.buy_count < self.max_buy_count:
                if self._detect_reversal(data, volume):
                    accumulation_level = self.grid_exec._calc_accumulation_level(current_price, data)
                    if accumulation_level == 0:
                        buy_pct = 0.15
                    elif accumulation_level == 1:
                        buy_pct = 0.20
                    elif accumulation_level == 2:
                        buy_pct = 0.25
                    elif accumulation_level == 3:
                        buy_pct = 0.30
                    else:
                        buy_pct = 0.35
                    buy_amount = min(available_balance * buy_pct, self.max_buy_amount)
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
                                "reason": f"reversal_buy_lvl{accumulation_level}"
                            }
            
            if self.position > 0 and current_price > self.entry_price * 1.015:
                revenue = self.position * current_price
                self.current_balance += revenue
                quantity = self.position
                # FIX T4-20261020: 赢/亏判定必须在 entry_price 复位之前（原代码复位后
                # current_price > 0 恒 True，导致所有 bounce_sell 误记为赢单）
                is_win = current_price > self.entry_price
                self.position = 0
                self.entry_price = 0
                self.last_price = current_price
                self.total_trades += 1
                if is_win:
                    self.winning_trades += 1
                else:
                    self.losing_trades += 1
                self.buy_count = 0
                return {
                    "action": "sell",
                    "quantity": quantity,
                    "price": current_price,
                    "balance": self.current_balance,
                    "position": self.position,
                    "reason": "bounce_sell"
                }
            
            if data is not None and len(data) > 10 and self.position < max_position:
                recent_prices = data.iloc[-10:]
                recent_change = (recent_prices.iloc[-1] - recent_prices.iloc[0]) / recent_prices.iloc[0]
                if recent_change < -0.03 and price_change > 0.005:
                    buy_amount = min(available_balance * 0.2, self.max_buy_amount)
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
            if self.market_type == 'trending_up':
                if data is not None and len(data) > 30:
                    support_resistance = self._detect_support_resistance(data)
                    wave_pattern = self._detect_wave_pattern(data)
                    trend_continues = self._check_trend_continuation(current_price, data)
                    
                    for fib_level in support_resistance['fib_levels']:
                        if abs(current_price - fib_level) / fib_level < 0.002 and self.position < max_position:
                            grid_result = self.grid_exec.execute_grid_buy(current_price, available_balance, self.position)
                            if grid_result:
                                self.position += grid_result['quantity']
                                self.current_balance -= grid_result['quantity'] * current_price
                                if self.entry_price == 0:
                                    self.entry_price = current_price
                                self.last_price = current_price
                                grid_result['reason'] = 'fibonacci_buy'
                                return grid_result
                    
                    if wave_pattern == 'correction' and trend_continues:
                        grid_result = self.grid_exec.execute_grid_buy(current_price, available_balance, self.position)
                        if grid_result:
                            self.position += grid_result['quantity']
                            self.current_balance -= grid_result['quantity'] * current_price
                            if self.entry_price == 0:
                                self.entry_price = current_price
                            self.last_price = current_price
                            grid_result['reason'] = 'wave_correction_buy'
                            return grid_result
                    
                    if trend_continues and current_price > support_resistance['resistance'] * 1.001:
                        grid_result = self.grid_exec.execute_grid_buy(current_price, available_balance, self.position)
                        if grid_result:
                            self.position += grid_result['quantity']
                            self.current_balance -= grid_result['quantity'] * current_price
                            if self.entry_price == 0:
                                self.entry_price = current_price
                            self.last_price = current_price
                            grid_result['reason'] = 'breakout_buy'
                            return grid_result
                
                if grid_change < 0 and self.position < max_position:
                    grid_result = self.grid_exec.execute_grid_buy(current_price, available_balance, self.position)
                    if grid_result:
                        self.position += grid_result['quantity']
                        self.current_balance -= grid_result['quantity'] * current_price
                        if self.entry_price == 0:
                            self.entry_price = current_price
                        self.last_price = current_price
                        grid_result['reason'] = 'uptrend_grid_buy'
                        return grid_result
                
                if grid_change > 0 and self.position > 0:
                    sell_quantity = self.position * 0.3
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
                            "reason": "uptrend_grid_sell"
                        }
            
            elif self.market_type == 'range_bound':
                price_series = pd.Series(self.price_history)
                lower_bound, upper_bound = self._calculate_range_boundaries(price_series)
                golden_points = self._calculate_golden_points(lower_bound, upper_bound)
                
                if grid_change < 0 and self.position < max_position:
                    buy_amount = self._calculate_dynamic_buy_amount(current_price, lower_bound, upper_bound)
                    buy_amount = min(buy_amount, available_balance * 0.15)
                    if buy_amount > self.min_buy_amount:
                        buy_quantity = buy_amount / current_price
                        if buy_quantity > 0.01:
                            actual_buy_amount = buy_quantity * current_price
                            actual_buy_amount = min(actual_buy_amount, available_balance)
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
                        sell_amount = sell_quantity * current_price
                        if current_price > self.last_buy_price * 1.0005:
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
                
                if len(self.price_history) > 5:
                    recent_prices = self.price_history[-5:]
                    price_range = max(recent_prices) - min(recent_prices)
                    price_mean = np.mean(recent_prices)
                    if price_range / price_mean < 0.01 and available_balance > 200:
                        if current_price < price_mean * 0.998:
                            grid_result = self.grid_exec.execute_grid_buy(current_price, available_balance, self.position)
                            if grid_result:
                                self.position += grid_result['quantity']
                                self.current_balance -= grid_result['quantity'] * current_price
                                if self.entry_price == 0:
                                    self.entry_price = current_price
                                self.last_buy_price = current_price
                                self.last_price = current_price
                                self.trade_history.append("mean_reversion_buy")
                                grid_result['reason'] = 'mean_reversion_buy'
                                return grid_result
                        elif current_price > price_mean * 1.002 and self.position > 0:
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
                pass
        
        self.balance_history.append(self.current_balance)
        if len(self.balance_history) > 10000:
            self.balance_history = self.balance_history[-10000:]
        
        if len(self.price_history) % 50 == 0 and len(self.price_history) > 0:
            self._rl_update_parameters()
        
        if len(self.price_history) % 100 == 0 and len(self.price_history) > 0:
            self._save_optimized_params()
    
    # ==================== 强化学习与参数优化方法 ====================
    
    def _load_optimized_params(self):
        if not os.path.exists(self.persist_dir):
            os.makedirs(self.persist_dir)
        if os.path.exists(self.persist_file):
            try:
                with open(self.persist_file, 'rb') as f:
                    saved_params = pickle.load(f)
                    if 'best_params' in saved_params:
                        self.best_params.update(saved_params['best_params'])
                    if 'market_state_params' in saved_params:
                        self.market_state_params.update(saved_params['market_state_params'])
                    if 'best_total_return' in saved_params:
                        self.best_total_return = saved_params['best_total_return']
                    if 'training_episodes' in saved_params:
                        self.training_episodes = saved_params['training_episodes']
                print(f"[OK] 加载已优化参数，历史最佳收益: {self.best_total_return:.2%}")
            except Exception as e:
                print(f"加载参数失败: {e}")
    
    def _save_optimized_params(self):
        if not os.path.exists(self.persist_dir):
            os.makedirs(self.persist_dir)
        params_to_save = {
            'best_params': self.best_params,
            'market_state_params': self.market_state_params,
            'best_total_return': self.best_total_return,
            'training_episodes': self.training_episodes,
            'exploration_rate': self.exploration_rate,
            'learning_rate': self.learning_rate,
            'save_time': pd.Timestamp.now().isoformat()
        }
        try:
            with open(self.persist_file, 'wb') as f:
                pickle.dump(params_to_save, f)
            print(f"[OK] 参数已保存到 {self.persist_file}")
            self._save_training_history()
        except Exception as e:
            print(f"保存参数失败: {e}")
    
    def _save_training_history(self):
        history = {
            'episode': self.training_episodes,
            'best_return': self.best_total_return,
            'params': self.best_params,
            'timestamp': pd.Timestamp.now().isoformat()
        }
        try:
            if os.path.exists(self.persist_history_file):
                with open(self.persist_history_file, 'r', encoding='utf-8') as f:
                    all_history = json.load(f)
            else:
                all_history = []
            all_history.append(history)
            if len(all_history) > 100:
                all_history = all_history[-100:]
            with open(self.persist_history_file, 'w', encoding='utf-8') as f:
                json.dump(all_history, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"保存训练历史失败: {e}")
    
    def _evaluate_strategy(self, data: pd.Series) -> Dict[str, float]:
        if len(data) < 50:
            return {'total_return': 0, 'sharpe_ratio': 0, 'max_drawdown': 0, 'win_rate': 0}
        returns = np.diff(self.balance_history) / self.balance_history[:-1]
        total_return = (self.current_balance - self.initial_balance) / self.initial_balance
        if len(returns) > 0:
            daily_returns = returns.reshape(-1, 390).sum(axis=1) if len(returns) >= 390 else returns
            volatility = daily_returns.std() * np.sqrt(252)
            sharpe_ratio = total_return / volatility if volatility > 0 else 0
        else:
            sharpe_ratio = 0
        peak = np.maximum.accumulate(self.balance_history)
        drawdown = (peak - self.balance_history) / peak
        max_drawdown = np.max(drawdown)
        win_rate = self.winning_trades / self.total_trades * 100 if self.total_trades > 0 else 0
        return {
            'total_return': total_return,
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown': max_drawdown,
            'win_rate': win_rate,
            'total_trades': self.total_trades
        }
    
    def _rl_update_parameters(self):
        if not self.rl_enabled:
            return
        metrics = self._evaluate_strategy(pd.Series(self.price_history))
        self.last_evaluation_metrics = metrics
        current_return = metrics['total_return']
        sharpe_ratio = metrics['sharpe_ratio']
        reward = current_return * 0.5 + sharpe_ratio * 0.3 - metrics['max_drawdown'] * 0.2
        if current_return > self.best_total_return + 0.001:
            self.best_total_return = current_return
            self.best_params = {
                'grid_spacing': self.grid_spacing,
                'max_position_percentage': self.max_position_percentage,
                'reserve_balance_percentage': self.reserve_balance_percentage,
                'take_profit_threshold': self.take_profit_threshold,
                'stop_loss_threshold': self.stop_loss_threshold
            }
            self.improvement_count += 1
            print(f"[INFO] 发现更优参数！收益: {current_return:.2%}, 夏普: {sharpe_ratio:.2f}")
            self._save_optimized_params()
        if self.rl_training_mode and np.random.random() < self.exploration_rate:
            self._explore_new_parameters()
        self.exploration_rate = max(self.min_exploration_rate, self.exploration_rate * self.exploration_decay)
        self.learning_rate = max(self.min_learning_rate, self.learning_rate * self.learning_decay)
        self.training_episodes += 1
    
    def _explore_new_parameters(self):
        params = self.best_params.copy()
        if 'stop_loss_threshold' not in params:
            params['stop_loss_threshold'] = 0.008
        if 'max_drawdown' not in params:
            params['max_drawdown'] = 0.08
        params['grid_spacing'] *= np.random.uniform(0.9, 1.1)
        params['max_position_percentage'] = np.clip(
            params['max_position_percentage'] * np.random.uniform(0.95, 1.05), 0.5, 0.95
        )
        params['reserve_balance_percentage'] = np.clip(
            params['reserve_balance_percentage'] * np.random.uniform(0.95, 1.05), 0.05, 0.4
        )
        params['take_profit_threshold'] *= np.random.uniform(0.8, 1.2)
        params['stop_loss_threshold'] *= np.random.uniform(0.8, 1.2)
        params['max_drawdown'] = np.clip(
            params['max_drawdown'] * np.random.uniform(0.9, 1.1), 0.05, 0.15
        )
        self.grid_spacing = params['grid_spacing']
        self.max_position_percentage = params['max_position_percentage']
        self.reserve_balance_percentage = params['reserve_balance_percentage']
        self.take_profit_threshold = params['take_profit_threshold']
        self.stop_loss_threshold = params['stop_loss_threshold']
        self.max_drawdown = params['max_drawdown']
        self.grids = self._create_grids()
        print(f"[EXP] 探索新参数 - 网格间距: {self.grid_spacing:.4f}, 仓位: {self.max_position_percentage:.2f}, 最大回撤: {self.max_drawdown:.2%}")
    
    def _apply_optimized_params(self):
        self.grid_spacing = self.best_params.get('grid_spacing', 0.004)
        self.max_position_percentage = self.best_params.get('max_position_percentage', 0.8)
        self.reserve_balance_percentage = self.best_params.get('reserve_balance_percentage', 0.2)
        self.take_profit_threshold = self.best_params.get('take_profit_threshold', 0.025)
        self.stop_loss_threshold = self.best_params.get('stop_loss_threshold', 0.008)
        self.max_drawdown = self.best_params.get('max_drawdown', 0.08)
        self.grids = self._create_grids()
        for market_type in self.market_state_params:
            if market_type in self.best_params:
                self.market_state_params[market_type].update(self.best_params[market_type])
        print(f"[OK] 已应用优化参数")
    
    def get_optimization_report(self) -> Dict:
        return {
            'training_episodes': self.training_episodes,
            'best_total_return': self.best_total_return,
            'improvement_count': self.improvement_count,
            'exploration_rate': self.exploration_rate,
            'learning_rate': self.learning_rate,
            'best_params': self.best_params,
            'last_metrics': self.last_evaluation_metrics,
            'total_trades': self.total_trades,
            'win_rate': self.winning_trades / self.total_trades * 100 if self.total_trades > 0 else 0
        }

# ==================== 强化学习代理类 ====================

class RLTradingAgent:
    def __init__(self):
        self.q_table = {}
        self.alpha = 0.1
        self.gamma = 0.99
        self.epsilon = 0.2
        self.state_bins = {
            'price_change': [-0.05, -0.02, -0.01, 0, 0.01, 0.02, 0.05],
            'rsi': [20, 30, 40, 50, 60, 70, 80],
            'volatility': [0.005, 0.01, 0.015, 0.02, 0.03],
            'market_type': ['range_bound', 'trending_up', 'trending_down']
        }
        self.actions = ['buy', 'sell', 'hold', 'increase_position', 'decrease_position']
    
    def _discretize_state(self, state: Dict) -> Tuple:
        discretized = []
        pc = state.get('price_change', 0)
        for i, bin_val in enumerate(self.state_bins['price_change']):
            if pc <= bin_val:
                discretized.append(f'pc_{i}')
                break
        else:
            discretized.append(f'pc_{len(self.state_bins["price_change"])}')
        rsi = state.get('rsi', 50)
        for i, bin_val in enumerate(self.state_bins['rsi']):
            if rsi <= bin_val:
                discretized.append(f'rsi_{i}')
                break
        else:
            discretized.append(f'rsi_{len(self.state_bins["rsi"])}')
        vol = state.get('volatility', 0.01)
        for i, bin_val in enumerate(self.state_bins['volatility']):
            if vol <= bin_val:
                discretized.append(f'vol_{i}')
                break
        else:
            discretized.append(f'vol_{len(self.state_bins["volatility"])}')
        mt = state.get('market_type', 'range_bound')
        discretized.append(f'mt_{mt}')
        return tuple(discretized)
    
    def get_action(self, state: Dict) -> str:
        discretized_state = self._discretize_state(state)
        if np.random.random() < self.epsilon:
            return np.random.choice(self.actions)
        if discretized_state not in self.q_table:
            self.q_table[discretized_state] = {action: 0 for action in self.actions}
        q_values = self.q_table[discretized_state]
        return max(q_values, key=q_values.get)
    
    def update_q_table(self, state: Dict, action: str, reward: float, next_state: Dict):
        state_key = self._discretize_state(state)
        next_state_key = self._discretize_state(next_state)
        if state_key not in self.q_table:
            self.q_table[state_key] = {a: 0 for a in self.actions}
        if next_state_key not in self.q_table:
            self.q_table[next_state_key] = {a: 0 for a in self.actions}
        old_q = self.q_table[state_key][action]
        max_next_q = max(self.q_table[next_state_key].values())
        new_q = old_q + self.alpha * (reward + self.gamma * max_next_q - old_q)
        self.q_table[state_key][action] = new_q
    
    def save_model(self, filepath: str):
        try:
            with open(filepath, 'wb') as f:
                pickle.dump({
                    'q_table': self.q_table,
                    'alpha': self.alpha,
                    'gamma': self.gamma,
                    'epsilon': self.epsilon
                }, f)
            print(f"[OK] RL模型已保存到 {filepath}")
        except Exception as e:
            print(f"保存RL模型失败: {e}")
    
    def load_model(self, filepath: str):
        if os.path.exists(filepath):
            try:
                with open(filepath, 'rb') as f:
                    data = pickle.load(f)
                    self.q_table = data.get('q_table', {})
                    self.alpha = data.get('alpha', 0.1)
                    self.gamma = data.get('gamma', 0.99)
                    self.epsilon = data.get('epsilon', 0.2)
                print(f"[OK] RL模型已加载，Q值表大小: {len(self.q_table)}")
            except Exception as e:
                print(f"加载RL模型失败: {e}")