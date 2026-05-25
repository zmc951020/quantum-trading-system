#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
伯努利-康达量化策略 (Bernoulli-Coanda Strategy, BCQ)
基于流体力学原理的自适应量化交易策略
包含自优化演进功能
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
from enum import Enum
import warnings
warnings.filterwarnings('ignore')

try:
    import talib as ta
except ImportError:
    ta = None
    print("警告: talib未安装，使用简化指标计算")

try:
    from strategy_monitor import (
        get_strategy_monitor,
        StrategyEventType,
        record_strategy_event
    )
    STRATEGY_MONITOR_AVAILABLE = True
except ImportError:
    STRATEGY_MONITOR_AVAILABLE = False


class MarketRegime(Enum):
    """市场状态枚举"""
    STRONG_TREND = "strong_trend"      # 强趋势市场
    WEAK_TREND = "weak_trend"          # 弱趋势市场
    RANGE_HIGH_LIQ = "range_high_liq"  # 震荡高流动性市场
    RANGE_LOW_LIQ = "range_low_liq"    # 震荡低流动性市场
    UNKNOWN = "unknown"                # 未知状态


class PositionSide(Enum):
    """持仓方向"""
    LONG = 1
    SHORT = -1
    FLAT = 0


@dataclass
class BernoulliCoandaParameters:
    """策略参数配置"""
    # 伯努利模块参数
    short_velocity_window: int = 5
    long_velocity_window: int = 20
    pressure_threshold: float = 0.5
    
    # 康达模块参数
    curve_type: str = "kalman"  # kalman, ema, hull
    curve_window: int = 20
    adhere_threshold: float = 0.02
    
    # 自适应参数
    auto_adapt_enabled: bool = True
    adaptation_rate: float = 0.1
    
    # 风控参数
    max_position_pct: float = 0.95
    max_drawdown_pct: float = 0.15
    stop_loss_atr_multiplier: float = 2.0
    take_profit_risk_reward: float = 2.0
    max_holding_days: int = 30
    
    # 机器学习参数
    use_ml_features: bool = True
    ml_update_frequency: int = 100  # 每100个bar更新一次


class AdaptiveParameter:
    """自适应参数类"""
    def __init__(self, initial_value: float, min_val: float, max_val: float, 
                 learning_rate: float = 0.1):
        self.value = initial_value
        self.min_val = min_val
        self.max_val = max_val
        self.learning_rate = learning_rate
        self.history = [initial_value]
        self.performance_scores = []
    
    def update(self, performance_signal: float, direction: float = 1.0):
        """根据表现信号更新参数值"""
        delta = self.learning_rate * performance_signal * direction
        new_value = self.value + delta
        self.value = np.clip(new_value, self.min_val, self.max_val)
        self.history.append(self.value)
        self.performance_scores.append(performance_signal)
        return self.value
    
    def get_value(self) -> float:
        return self.value
    
    def get_history(self) -> List[float]:
        return self.history


class BernoulliCoandaFeatures:
    """伯努利-康达特征计算器"""
    
    def __init__(self, params: BernoulliCoandaParameters):
        self.params = params
        self.scalers = {}
        self.feature_history = {}
    
    def calculate_velocity(self, df: pd.DataFrame) -> pd.DataFrame:
        """计算流速指标（伯努利原理）"""
        df = df.copy()
        
        # 价格变动率
        df['price_pct_change'] = df['Close'].pct_change()
        
        # 带符号的流速 = 成交量 * 价格变动率（方向敏感）
        df['signed_velocity'] = df['Volume'] * df['price_pct_change']
        
        # 绝对流速 = 成交量 * |价格变动率|
        df['abs_velocity'] = df['Volume'] * df['price_pct_change'].abs()
        
        # 短期和长期流速
        df['vel_short'] = df['abs_velocity'].rolling(self.params.short_velocity_window).mean()
        df['vel_long'] = df['abs_velocity'].rolling(self.params.long_velocity_window).mean()
        
        # 计算压强差
        df['pressure_gap'] = df['vel_short'] - df['vel_long']
        
        # 使用扩展窗口标准化（避免未来信息泄露）
        df['pressure_strength'] = df['pressure_gap'] / (
            df['pressure_gap'].expanding().std() + 1e-8
        )
        
        # 伯努利信号
        df['bernoulli_signal'] = np.sign(df['pressure_gap'])
        
        # 压强方向置信度
        df['pressure_confidence'] = np.tanh(df['pressure_strength'].abs())
        
        return df
    
    def calculate_coanda(self, df: pd.DataFrame) -> pd.DataFrame:
        """计算康达曲面附着特征"""
        df = df.copy()
        
        # 计算多种曲面
        df['curve_ema'] = df['Close'].ewm(span=self.params.curve_window).mean()
        
        # 卡尔曼滤波曲面（更平滑）
        df['curve_kalman'] = self._calculate_kalman_curve(df['Close'])
        
        # 选择主曲面
        if self.params.curve_type == "kalman":
            df['curve'] = df['curve_kalman']
        else:
            df['curve'] = df['curve_ema']
        
        # 计算到曲面的距离
        df['dist_to_curve'] = (df['Close'] - df['curve']) / df['curve']
        
        # 动态附着阈值（基于历史距离的标准差）
        rolling_dist_std = df['dist_to_curve'].rolling(50).std()
        df['adhere_threshold'] = rolling_dist_std * 1.5
        df['adherent'] = (df['dist_to_curve'].abs() < df['adhere_threshold']).astype(int)
        
        # 计算曲面斜率（方向）
        df['curve_slope'] = df['curve'].diff()
        
        # 价格方向
        df['price_direction'] = np.sign(df['Close'].diff())
        
        # 康达角度一致性
        df['coanda_angle'] = (df['price_direction'] == np.sign(df['curve_slope'])).astype(int)
        
        # 计算ADX趋势强度
        if ta is not None:
            df['adx'] = ta.ADX(df['High'], df['Low'], df['Close'], timeperiod=14)
        else:
            df['adx'] = self._simplified_adx(df)
        
        # 连续附着天数
        df['adherent_streak'] = df['adherent'].groupby(
            (df['adherent'].diff() != 0).cumsum()
        ).cumsum()
        
        # 康达强度 = 连续附着天数 * ADX归一化
        df['coanda_raw'] = df['adherent_streak'] * (df['adx'] / 100)
        df['coanda_strength'] = df['coanda_raw'].clip(0, 1)
        
        return df
    
    def _calculate_kalman_curve(self, prices: pd.Series) -> pd.Series:
        """简单的卡尔曼滤波实现"""
        n = len(prices)
        smoothed = np.zeros(n)
        smoothed[0] = prices.iloc[0]
        
        # 简单的卡尔曼滤波参数
        process_variance = 1e-5
        measurement_variance = 0.1
        
        estimate = prices.iloc[0]
        error_covariance = 1.0
        
        for i in range(1, n):
            # 预测
            predicted_estimate = estimate
            predicted_error_covariance = error_covariance + process_variance
            
            # 更新
            kalman_gain = predicted_error_covariance / (predicted_error_covariance + measurement_variance)
            estimate = predicted_estimate + kalman_gain * (prices.iloc[i] - predicted_estimate)
            error_covariance = (1 - kalman_gain) * predicted_error_covariance
            
            smoothed[i] = estimate
        
        return pd.Series(smoothed, index=prices.index)
    
    def _simplified_adx(self, df: pd.DataFrame) -> pd.Series:
        """简化的ADX计算"""
        n = 14
        tr = pd.DataFrame()
        tr['h-l'] = df['High'] - df['Low']
        tr['h-pc'] = abs(df['High'] - df['Close'].shift())
        tr['l-pc'] = abs(df['Low'] - df['Close'].shift())
        tr['tr'] = tr.max(axis=1)
        atr = tr['tr'].rolling(n).mean()
        
        # 简化版本，返回标准化的TR
        return (atr / atr.rolling(100).mean() * 25).clip(0, 100)
    
    def classify_market_regime(self, df: pd.DataFrame, idx: int = -1) -> MarketRegime:
        """分类市场状态"""
        if idx == -1:
            idx = len(df) - 1
        
        adx = df['adx'].iloc[idx] if 'adx' in df.columns else 25
        vol = df['Close'].pct_change().rolling(20).std().iloc[idx]
        liq = df['Volume'].iloc[idx] / (df['Volume'].rolling(100).mean().iloc[idx] + 1e-8)
        
        if pd.isna(adx) or pd.isna(vol) or pd.isna(liq):
            return MarketRegime.UNKNOWN
        
        if adx > 30 and vol > 0.01:
            return MarketRegime.STRONG_TREND
        elif adx > 30 and vol <= 0.01:
            return MarketRegime.WEAK_TREND
        elif adx <= 30 and liq > 1.2:
            return MarketRegime.RANGE_HIGH_LIQ
        else:
            return MarketRegime.RANGE_LOW_LIQ
    
    def fit_transform(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, List[str]]:
        """计算所有特征"""
        df = df.copy()
        
        # 计算伯努利特征
        df = self.calculate_velocity(df)
        
        # 计算康达特征
        df = self.calculate_coanda(df)
        
        # 清理NaN
        feature_cols = [
            'bernoulli_signal', 'pressure_strength', 'pressure_confidence',
            'coanda_strength', 'coanda_angle', 'dist_to_curve', 'adx'
        ]
        
        for col in feature_cols:
            if col in df.columns:
                df[col] = df[col].fillna(0)
        
        return df, feature_cols


class StrategyOptimizer:
    """策略自优化器"""
    
    def __init__(self, params: BernoulliCoandaParameters):
        self.base_params = params
        self.adaptive_params = self._init_adaptive_params()
        self.performance_history = []
        self.param_performance = {}
        self.regime_best_params = {}
    
    def _init_adaptive_params(self) -> Dict[str, AdaptiveParameter]:
        """初始化自适应参数"""
        return {
            'pressure_threshold': AdaptiveParameter(
                initial_value=self.base_params.pressure_threshold,
                min_val=0.2,
                max_val=1.0,
                learning_rate=0.05
            ),
            'adhere_threshold': AdaptiveParameter(
                initial_value=self.base_params.adhere_threshold,
                min_val=0.005,
                max_val=0.05,
                learning_rate=0.05
            ),
            'stop_loss_atr_multiplier': AdaptiveParameter(
                initial_value=self.base_params.stop_loss_atr_multiplier,
                min_val=1.0,
                max_val=4.0,
                learning_rate=0.03
            )
        }
    
    def record_trade_result(self, trade_result: Dict[str, Any]):
        """记录交易结果用于优化"""
        self.performance_history.append(trade_result)
        
        # 保存当前参数状态
        param_state = {
            name: param.get_value() 
            for name, param in self.adaptive_params.items()
        }
        param_state['profit'] = trade_result.get('profit_pct', 0)
        
        regime = trade_result.get('market_regime', MarketRegime.UNKNOWN.value)
        if regime not in self.param_performance:
            self.param_performance[regime] = []
        self.param_performance[regime].append(param_state)
        
        if len(self.performance_history) % 50 == 0:
            self._learn_best_params()
    
    def _learn_best_params(self):
        """学习不同市场状态下的最优参数"""
        for regime, results in self.param_performance.items():
            if len(results) < 10:
                continue
            
            # 找出盈利最高的参数组合
            sorted_results = sorted(results, key=lambda x: x['profit'], reverse=True)
            top_20 = sorted_results[:max(5, len(results) // 5)]
            
            # 计算平均最优参数
            best_params = {}
            for param_name in self.adaptive_params.keys():
                values = [r[param_name] for r in top_20 if param_name in r]
                if values:
                    best_params[param_name] = np.mean(values)
            
            if best_params:
                self.regime_best_params[regime] = best_params
    
    def adapt_for_regime(self, regime: MarketRegime) -> Dict[str, float]:
        """为特定市场状态自适应调整参数"""
        if regime.value in self.regime_best_params:
            best_params = self.regime_best_params[regime.value]
            for param_name, target_value in best_params.items():
                if param_name in self.adaptive_params:
                    # 平滑地向目标值调整
                    current = self.adaptive_params[param_name].get_value()
                    new_value = current + 0.1 * (target_value - current)
                    self.adaptive_params[param_name].value = new_value
        
        # 返回当前参数值
        return {name: param.get_value() 
                for name, param in self.adaptive_params.items()}
    
    def update_from_recent_performance(self, win_rate: float, avg_profit: float):
        """根据近期表现更新参数"""
        performance_score = win_rate * avg_profit * 10
        
        # 根据表现调整参数敏感度
        for param in self.adaptive_params.values():
            # 如果表现好，保持参数稳定
            # 如果表现差，增加探索范围
            if performance_score < 0:
                param.learning_rate = min(0.2, param.learning_rate * 1.1)
            else:
                param.learning_rate = max(0.02, param.learning_rate * 0.9)


class RiskManager:
    """风险管理器"""
    
    def __init__(self, params: BernoulliCoandaParameters):
        self.params = params
        self.highest_equity = 0
        self.current_drawdown = 0
        self.trade_history = []
        self.daily_returns = []
    
    def update_equity(self, current_equity: float):
        """更新权益和回撤计算"""
        if current_equity > self.highest_equity:
            self.highest_equity = current_equity
        
        if self.highest_equity > 0:
            self.current_drawdown = (self.highest_equity - current_equity) / self.highest_equity
    
    def is_in_drawdown_limit(self) -> bool:
        """检查是否超过最大回撤限制"""
        return self.current_drawdown >= self.params.max_drawdown_pct
    
    def calculate_position_size(self, 
                               equity: float,
                               entry_price: float,
                               atr: float,
                               target_risk_pct: float = 0.02) -> float:
        """基于风险的仓位计算"""
        if atr <= 0 or entry_price <= 0:
            return 0
        
        # 2倍ATR止损
        stop_distance = self.params.stop_loss_atr_multiplier * atr
        
        # 仓位 = (风险比例 * 资本) / (止损距离 * 价格)
        position_value = (equity * target_risk_pct) / (stop_distance / entry_price)
        
        # 限制最大仓位
        max_position_value = equity * self.params.max_position_pct
        position_value = min(position_value, max_position_value)
        
        return position_value
    
    def check_stop_loss(self, 
                       current_price: float, 
                       entry_price: float, 
                       atr: float, 
                       side: PositionSide) -> bool:
        """检查止损条件"""
        stop_distance = self.params.stop_loss_atr_multiplier * atr
        
        if side == PositionSide.LONG:
            return current_price <= entry_price - stop_distance
        else:
            return current_price >= entry_price + stop_distance
    
    def check_take_profit(self,
                         current_price: float,
                         entry_price: float,
                         atr: float,
                         side: PositionSide) -> bool:
        """检查止盈条件"""
        stop_distance = self.params.stop_loss_atr_multiplier * atr
        target_distance = stop_distance * self.params.take_profit_risk_reward
        
        if side == PositionSide.LONG:
            return current_price >= entry_price + target_distance
        else:
            return current_price <= entry_price - target_distance


class Position:
    """持仓管理类"""
    
    def __init__(self, 
                 side: PositionSide, 
                 entry_price: float, 
                 size: float, 
                 entry_time: pd.Timestamp):
        self.side = side
        self.entry_price = entry_price
        self.size = size
        self.entry_time = entry_time
        self.highest_price = entry_price
        self.lowest_price = entry_price
        self.holding_days = 0
    
    def update(self, current_price: float, current_time: pd.Timestamp):
        """更新持仓状态"""
        if current_price > self.highest_price:
            self.highest_price = current_price
        if current_price < self.lowest_price:
            self.lowest_price = current_price
        
        self.holding_days = (current_time - self.entry_time).days
    
    def calculate_unrealized_pnl(self, current_price: float) -> float:
        """计算未实现盈亏"""
        if self.side == PositionSide.LONG:
            return (current_price - self.entry_price) / self.entry_price
        else:
            return (self.entry_price - current_price) / self.entry_price


class bernoulli_coanda_strategy:
    """伯努利-康达量化策略主类"""
    
    def __init__(self, 
                 name: str = "BernoulliCoanda",
                 params: Optional[BernoulliCoandaParameters] = None):
        self.name = name
        self.params = params or BernoulliCoandaParameters()
        
        # 核心组件
        self.feature_calc = BernoulliCoandaFeatures(self.params)
        self.optimizer = StrategyOptimizer(self.params)
        self.risk_manager = RiskManager(self.params)
        
        # 状态管理
        self.current_position: Optional[Position] = None
        self.equity_history = []
        self.trades = []
        
        # 数据缓存
        self.data: Optional[pd.DataFrame] = None
        self.current_idx = 0
        
        # 监控集成
        self.monitor_available = STRATEGY_MONITOR_AVAILABLE
        if self.monitor_available:
            self.strategy_monitor = get_strategy_monitor()
    
    def initialize(self, initial_capital: float = 100000):
        """初始化策略"""
        self.risk_manager.highest_equity = initial_capital
        self.equity_history = [initial_capital]
        self.current_position = None
        self.trades = []
        self.current_idx = 0
        
        if self.monitor_available:
            record_strategy_event(
                StrategyEventType.STRATEGY_ACTIVATE,
                strategy_id=self.name,
                environment="paper"
            )
    
    def load_data(self, data: pd.DataFrame):
        """加载数据"""
        required_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
        for col in required_cols:
            if col not in data.columns:
                raise ValueError(f"缺少必要列: {col}")
        
        self.data = data.copy()
        self.data, _ = self.feature_calc.fit_transform(self.data)
        self.current_idx = 0
    
    def _get_current_state(self) -> Dict[str, Any]:
        """获取当前市场状态"""
        idx = self.current_idx
        df = self.data
        
        state = {
            'bernoulli_signal': df['bernoulli_signal'].iloc[idx],
            'pressure_strength': df['pressure_strength'].iloc[idx],
            'pressure_confidence': df['pressure_confidence'].iloc[idx],
            'coanda_strength': df['coanda_strength'].iloc[idx],
            'coanda_angle': df['coanda_angle'].iloc[idx],
            'adx': df['adx'].iloc[idx] if 'adx' in df.columns else 25,
            'close': df['Close'].iloc[idx],
            'volume': df['Volume'].iloc[idx],
        }
        
        if ta is not None:
            state['atr'] = ta.ATR(df['High'], df['Low'], df['Close'], timeperiod=14).iloc[idx]
        else:
            # 简化ATR计算
            high_low = df['High'] - df['Low']
            state['atr'] = high_low.rolling(14).mean().iloc[idx]
        
        # 市场状态
        state['regime'] = self.feature_calc.classify_market_regime(df, idx)
        
        return state
    
    def _generate_signal(self, state: Dict[str, Any]) -> Tuple[Optional[PositionSide], float]:
        """生成交易信号"""
        signal = None
        confidence = 0.0
        
        bernoulli_sig = state['bernoulli_signal']
        pressure_strength = state['pressure_strength']
        pressure_confidence = state['pressure_confidence']
        coanda_strength = state['coanda_strength']
        coanda_angle = state['coanda_angle']
        
        # 获取自适应参数
        adapted_params = self.optimizer.adapt_for_regime(state['regime'])
        pressure_threshold = adapted_params.get('pressure_threshold', self.params.pressure_threshold)
        
        # 多头信号条件
        if (bernoulli_sig == 1 and 
            pressure_strength > pressure_threshold and 
            coanda_angle == 1 and 
            coanda_strength > 0.5):
            signal = PositionSide.LONG
            confidence = min(1.0, (pressure_confidence + coanda_strength) / 2)
        
        # 空头信号条件
        elif (bernoulli_sig == -1 and 
              pressure_strength < -pressure_threshold and 
              coanda_angle == 1 and 
              coanda_strength > 0.5):
            signal = PositionSide.SHORT
            confidence = min(1.0, (pressure_confidence + coanda_strength) / 2)
        
        return signal, confidence
    
    def _execute_long(self, state: Dict[str, Any], confidence: float):
        """执行多头开仓"""
        if self.current_position is not None:
            return
        
        equity = self.equity_history[-1]
        entry_price = state['close']
        atr = state['atr']
        
        # 基于风险的仓位计算
        target_risk = 0.02 * confidence  # 置信度调整风险
        position_size = self.risk_manager.calculate_position_size(
            equity, entry_price, atr, target_risk
        )
        
        if position_size > 0:
            self.current_position = Position(
                side=PositionSide.LONG,
                entry_price=entry_price,
                size=position_size,
                entry_time=self.data.index[self.current_idx]
            )
            
            if self.monitor_available:
                record_strategy_event(
                    StrategyEventType.USER_ACTION,
                    strategy_id=self.name,
                    metadata={"action": "LONG_ENTER", "price": entry_price, "size": position_size}
                )
    
    def _execute_short(self, state: Dict[str, Any], confidence: float):
        """执行空头开仓"""
        if self.current_position is not None:
            return
        
        equity = self.equity_history[-1]
        entry_price = state['close']
        atr = state['atr']
        
        target_risk = 0.02 * confidence
        position_size = self.risk_manager.calculate_position_size(
            equity, entry_price, atr, target_risk
        )
        
        if position_size > 0:
            self.current_position = Position(
                side=PositionSide.SHORT,
                entry_price=entry_price,
                size=position_size,
                entry_time=self.data.index[self.current_idx]
            )
            
            if self.monitor_available:
                record_strategy_event(
                    StrategyEventType.USER_ACTION,
                    strategy_id=self.name,
                    metadata={"action": "SHORT_ENTER", "price": entry_price, "size": position_size}
                )
    
    def _close_position(self, state: Dict[str, Any], reason: str = "unknown"):
        """平仓"""
        if self.current_position is None:
            return
        
        exit_price = state['close']
        pnl_pct = self.current_position.calculate_unrealized_pnl(exit_price)
        
        # 记录交易
        trade = {
            'entry_time': self.current_position.entry_time,
            'exit_time': self.data.index[self.current_idx],
            'side': self.current_position.side.value,
            'entry_price': self.current_position.entry_price,
            'exit_price': exit_price,
            'profit_pct': pnl_pct,
            'holding_days': self.current_position.holding_days,
            'reason': reason,
            'market_regime': state['regime'].value
        }
        self.trades.append(trade)
        
        # 更新权益
        equity = self.equity_history[-1]
        new_equity = equity * (1 + pnl_pct * self.current_position.size / equity)
        self.equity_history.append(new_equity)
        self.risk_manager.update_equity(new_equity)
        
        # 优化器学习
        self.optimizer.record_trade_result(trade)
        
        if self.monitor_available:
            record_strategy_event(
                StrategyEventType.USER_ACTION,
                strategy_id=self.name,
                metadata={"action": "CLOSE", "profit_pct": pnl_pct, "reason": reason}
            )
        
        # 清空持仓
        self.current_position = None
    
    def step(self) -> bool:
        """执行一个时间步"""
        if self.data is None or self.current_idx >= len(self.data):
            return False
        
        state = self._get_current_state()
        
        # 检查回撤限制
        if self.risk_manager.is_in_drawdown_limit():
            if self.current_position is not None:
                self._close_position(state, reason="drawdown_limit")
            self.current_idx += 1
            return True
        
        # 处理现有持仓
        if self.current_position is not None:
            current_price = state['close']
            atr = state['atr']
            
            # 更新持仓
            self.current_position.update(
                current_price,
                self.data.index[self.current_idx]
            )
            
            # 检查止损
            if self.risk_manager.check_stop_loss(
                current_price, 
                self.current_position.entry_price, 
                atr, 
                self.current_position.side
            ):
                self._close_position(state, reason="stop_loss")
            
            # 检查止盈
            elif self.risk_manager.check_take_profit(
                current_price,
                self.current_position.entry_price,
                atr,
                self.current_position.side
            ):
                self._close_position(state, reason="take_profit")
            
            # 检查最大持仓天数
            elif self.current_position.holding_days >= self.params.max_holding_days:
                self._close_position(state, reason="max_holding_days")
            
            # 检查信号是否反转
            else:
                signal, _ = self._generate_signal(state)
                if (signal == PositionSide.SHORT and 
                    self.current_position.side == PositionSide.LONG):
                    self._close_position(state, reason="signal_reversal")
                elif (signal == PositionSide.LONG and 
                      self.current_position.side == PositionSide.SHORT):
                    self._close_position(state, reason="signal_reversal")
        
        # 如果没有持仓，寻找新机会
        else:
            signal, confidence = self._generate_signal(state)
            
            if signal == PositionSide.LONG:
                self._execute_long(state, confidence)
            elif signal == PositionSide.SHORT:
                self._execute_short(state, confidence)
        
        # 更新权益（如果有持仓）
        if self.current_position is not None:
            unrealized_pnl = self.current_position.calculate_unrealized_pnl(state['close'])
            equity = self.equity_history[-1]
            if len(self.equity_history) <= self.current_idx + 1:
                self.equity_history.append(equity)
        
        self.current_idx += 1
        return True
    
    def run_backtest(self, 
                     data: pd.DataFrame, 
                     initial_capital: float = 100000) -> Dict[str, Any]:
        """运行回测"""
        self.load_data(data)
        self.initialize(initial_capital)
        
        # 逐时间步运行
        while self.step():
            pass
        
        # 计算最终结果
        result = self._calculate_backtest_results(initial_capital)
        
        return result
    
    def _calculate_backtest_results(self, initial_capital: float) -> Dict[str, Any]:
        """计算回测结果指标"""
        if len(self.equity_history) < 2:
            return {}
        
        final_equity = self.equity_history[-1]
        returns = pd.Series(self.equity_history).pct_change().dropna()
        
        # 计算指标
        total_return_pct = (final_equity - initial_capital) / initial_capital * 100
        
        if len(returns) > 0:
            annual_return = returns.mean() * 252 * 100
            annual_volatility = returns.std() * np.sqrt(252)
            sharpe_ratio = (annual_return / 100) / (annual_volatility + 1e-8) if annual_volatility > 0 else 0
        else:
            annual_return = 0
            annual_volatility = 0
            sharpe_ratio = 0
        
        # 计算最大回撤
        equity_series = pd.Series(self.equity_history)
        running_max = equity_series.expanding().max()
        drawdowns = (equity_series - running_max) / running_max
        max_drawdown = drawdowns.min() * 100
        
        # 交易统计
        if self.trades:
            trade_df = pd.DataFrame(self.trades)
            winning_trades = trade_df[trade_df['profit_pct'] > 0]
            losing_trades = trade_df[trade_df['profit_pct'] <= 0]
            
            win_rate = len(winning_trades) / len(trade_df) * 100 if len(trade_df) > 0 else 0
            
            avg_win = winning_trades['profit_pct'].mean() if len(winning_trades) > 0 else 0
            avg_loss = losing_trades['profit_pct'].mean() if len(losing_trades) > 0 else 0
            
            profit_factor = abs(winning_trades['profit_pct'].sum() / losing_trades['profit_pct'].sum()) if len(losing_trades) > 0 and losing_trades['profit_pct'].sum() != 0 else float('inf')
        else:
            win_rate = 0
            avg_win = 0
            avg_loss = 0
            profit_factor = 0
        
        result = {
            'strategy_name': self.name,
            'initial_capital': initial_capital,
            'final_equity': final_equity,
            'total_return_pct': total_return_pct,
            'annual_return_pct': annual_return,
            'annual_volatility_pct': annual_volatility * 100,
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown_pct': max_drawdown,
            'total_trades': len(self.trades),
            'win_rate_pct': win_rate,
            'avg_win_pct': avg_win * 100,
            'avg_loss_pct': avg_loss * 100,
            'profit_factor': profit_factor,
            'equity_curve': self.equity_history.copy(),
            'trades': self.trades.copy(),
            'final_params': {
                name: param.get_value()
                for name, param in self.optimizer.adaptive_params.items()
            }
        }
        
        return result


# 便捷函数
def create_bernoulli_coanda_strategy(name: str = "BCQ_V1", 
                                     auto_adapt: bool = True) -> bernoulli_coanda_strategy:
    """创建伯努利-康达策略实例"""
    params = BernoulliCoandaParameters()
    params.auto_adapt_enabled = auto_adapt
    return bernoulli_coanda_strategy(name=name, params=params)


if __name__ == "__main__":
    print("伯努利-康达量化策略模块加载成功！")
    print("使用 create_bernoulli_coanda_strategy() 创建策略实例")
