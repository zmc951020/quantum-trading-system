#!/usr/bin/env python3
"""
MarketStateHub — 统一市场状态感知层
=====================================
增益性优化模块，不修改现有策略代码，通过依赖注入提供增强的市场状态感知能力。

设计目标：
  1. 消除多个策略各自独立检测市场状态的重复计算
  2. 提供更丰富的市场特征（波动率结构、相关性矩阵、状态置信度）
  3. 支持 HMM、傅里叶、技术指标等多维度融合
  4. 单例模式，全局唯一实例，默认关闭

使用方式：
  hub = MarketStateHub()
  hub.enabled = True  # 启用
  regime = hub.get_market_regime(data)  # 获取市场状态

回滚方式：
  hub.enabled = False  # 各策略回退到自有检测逻辑
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional, Any
from enum import Enum
from dataclasses import dataclass, field
import logging
from collections import deque
import warnings

logger = logging.getLogger(__name__)


class MarketRegime(Enum):
    """市场状态枚举"""
    RANGE_BOUND = "range_bound"
    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    VOLATILE = "volatile"
    UNKNOWN = "unknown"


@dataclass
class MarketState:
    """市场状态数据类"""
    regime: MarketRegime = MarketRegime.UNKNOWN
    confidence: float = 0.0
    volatility: float = 0.0
    trend_strength: float = 0.0
    momentum: float = 0.0
    rsi: float = 50.0
    atr: float = 0.0
    bollinger_width: float = 0.0
    price_position: float = 0.5  # 价格在布林带中的位置 [0,1]
    
    # 多维度状态
    hmm_regime: Optional[str] = None
    fourier_regime: Optional[str] = None
    technical_regime: Optional[str] = None
    
    # 状态转换概率
    transition_probs: Dict[str, float] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "regime": self.regime.value,
            "confidence": self.confidence,
            "volatility": self.volatility,
            "trend_strength": self.trend_strength,
            "momentum": self.momentum,
            "rsi": self.rsi,
            "atr": self.atr,
            "bollinger_width": self.bollinger_width,
            "price_position": self.price_position,
            "hmm_regime": self.hmm_regime,
            "fourier_regime": self.fourier_regime,
            "technical_regime": self.technical_regime,
        }


class MarketStateHub:
    """
    统一市场状态感知中心
    
    单例模式，聚合 HMM、傅里叶、技术指标等多维度市场状态判断，
    提供统一的市场状态查询接口。
    
    Features:
        - 多维度市场状态融合（HMM + 傅里叶 + 技术指标）
        - 置信度评估
        - 状态转换概率矩阵
        - 波动率结构分析
        - 降级策略：Hub 不可用时回退到本地检测
    """
    
    _instance = None
    _initialized = False
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if MarketStateHub._initialized:
            return
        
        self.enabled = False  # 默认关闭，通过配置启用
        self._price_buffer = deque(maxlen=500)  # 价格缓冲区
        self._state_history = deque(maxlen=100)  # 状态历史
        self._current_state = MarketState()
        self._last_regime = MarketRegime.UNKNOWN
        self._stable_count = 0
        self._min_stable_periods = 3
        
        # HMM 状态检测器（轻量版）
        self._hmm_available = False
        self._hmm_model = None
        self._init_hmm()
        
        # 技术指标缓存
        self._indicator_cache = {}
        
        # 性能统计
        self._call_count = 0
        self._cache_hit_count = 0
        
        MarketStateHub._initialized = True
        logger.info("[MarketStateHub] 初始化完成，默认关闭状态")
    
    def _init_hmm(self):
        """尝试初始化 HMM 模型"""
        try:
            from hmmlearn import hmm
            self._hmm_model = hmm.GaussianHMM(
                n_components=3,  # 上涨/横盘/下跌
                covariance_type="full",
                n_iter=100,
                random_state=42
            )
            self._hmm_available = True
            logger.info("[MarketStateHub] HMM 模型初始化成功")
        except ImportError:
            self._hmm_available = False
            logger.warning("[MarketStateHub] hmmlearn 未安装，HMM 检测不可用")
    
    # ==================== 公开接口 ====================
    
    def get_market_regime(self, data: pd.Series) -> str:
        """
        获取当前市场状态
        
        Args:
            data: 价格序列
            
        Returns:
            市场状态字符串: 'range_bound', 'trending_up', 'trending_down', 'volatile'
        """
        if not self.enabled or len(data) < 20:
            return 'range_bound'
        
        self._call_count += 1
        self._price_buffer.append(data.iloc[-1])
        
        # 更新市场状态
        state = self._compute_market_state(data)
        self._current_state = state
        self._state_history.append(state)
        
        # 稳定性检查
        regime = state.regime
        if regime == self._last_regime:
            self._stable_count += 1
        else:
            self._stable_count = 0
        
        self._last_regime = regime
        
        # 只有连续稳定超过阈值才切换
        if self._stable_count >= self._min_stable_periods:
            return regime.value
        else:
            return self._last_regime.value if self._last_regime != MarketRegime.UNKNOWN else 'range_bound'
    
    def get_volatility_structure(self, data: pd.Series) -> Dict[str, float]:
        """
        获取波动率结构
        
        Args:
            data: 价格序列
            
        Returns:
            波动率结构字典
        """
        if not self.enabled or len(data) < 20:
            return {
                "short_term_vol": 0.0,
                "medium_term_vol": 0.0,
                "long_term_vol": 0.0,
                "vol_ratio": 1.0,
                "vol_regime": "low"
            }
        
        returns = data.pct_change().dropna()
        
        short_vol = returns.tail(5).std() if len(returns) >= 5 else 0.0
        medium_vol = returns.tail(20).std() if len(returns) >= 20 else 0.0
        long_vol = returns.tail(60).std() if len(returns) >= 60 else 0.0
        
        vol_ratio = short_vol / medium_vol if medium_vol > 0 else 1.0
        
        # 波动率状态判断
        if medium_vol < 0.005:
            vol_regime = "low"
        elif medium_vol < 0.015:
            vol_regime = "normal"
        else:
            vol_regime = "high"
        
        return {
            "short_term_vol": short_vol,
            "medium_term_vol": medium_vol,
            "long_term_vol": long_vol,
            "vol_ratio": vol_ratio,
            "vol_regime": vol_regime
        }
    
    def get_signal_confidence(self) -> float:
        """
        获取当前信号置信度
        
        Returns:
            置信度 [0, 1]
        """
        return self._current_state.confidence
    
    def get_full_state(self) -> Dict[str, Any]:
        """
        获取完整市场状态
        
        Returns:
            完整状态字典
        """
        return self._current_state.to_dict()
    
    def get_regime_transition_probs(self) -> Dict[str, float]:
        """
        获取状态转换概率
        
        Returns:
            状态转换概率字典
        """
        return self._current_state.transition_probs
    
    def reset(self):
        """重置状态（用于回测切换）"""
        self._price_buffer.clear()
        self._state_history.clear()
        self._current_state = MarketState()
        self._last_regime = MarketRegime.UNKNOWN
        self._stable_count = 0
        self._call_count = 0
        self._cache_hit_count = 0
        logger.info("[MarketStateHub] 状态已重置")
    
    # ==================== 内部计算方法 ====================
    
    def _compute_market_state(self, data: pd.Series) -> MarketState:
        """
        计算综合市场状态
        
        融合 HMM、傅里叶、技术指标三个维度的判断
        """
        state = MarketState()
        
        # 1. 技术指标维度
        technical_regime = self._detect_technical_regime(data)
        state.technical_regime = technical_regime.value
        state.rsi = self._calculate_rsi(data)
        state.atr = self._calculate_atr(data)
        
        # 2. HMM 维度（如果可用）
        if self._hmm_available and len(data) >= 60:
            hmm_regime = self._detect_hmm_regime(data)
            state.hmm_regime = hmm_regime.value
        
        # 3. 傅里叶维度
        fourier_regime = self._detect_fourier_regime(data)
        state.fourier_regime = fourier_regime.value
        
        # 4. 计算基础指标
        state.volatility = self._calculate_volatility(data)
        state.trend_strength = self._calculate_trend_strength(data)
        state.momentum = self._calculate_momentum(data)
        state.bollinger_width = self._calculate_bollinger_width(data)
        state.price_position = self._calculate_price_position(data)
        
        # 5. 融合判断（加权投票）
        state.regime, state.confidence = self._fuse_regimes(
            technical_regime, hmm_regime if self._hmm_available else None,
            fourier_regime, data
        )
        
        # 6. 计算状态转换概率
        state.transition_probs = self._compute_transition_probs()
        
        return state
    
    def _detect_technical_regime(self, data: pd.Series) -> MarketRegime:
        """
        基于技术指标的市场状态检测
        
        使用多周期 EMA、RSI、布林带、ADX 综合判断
        """
        if len(data) < 60:
            return MarketRegime.RANGE_BOUND
        
        # 多周期 EMA
        ema10 = data.ewm(span=10).mean()
        ema30 = data.ewm(span=30).mean()
        ema60 = data.ewm(span=60).mean()
        
        trend_10_60 = (ema10.iloc[-1] - ema60.iloc[-1]) / ema60.iloc[-1]
        trend_10_30 = (ema10.iloc[-1] - ema30.iloc[-1]) / ema30.iloc[-1]
        
        # 趋势计数（降低阈值，提高灵敏度）
        up_count = sum([
            trend_10_60 > 0.005,
            trend_10_30 > 0.003,
            ema10.iloc[-1] > ema10.iloc[-5],
            ema30.iloc[-1] > ema30.iloc[-10]
        ])
        
        down_count = sum([
            trend_10_60 < -0.005,
            trend_10_30 < -0.003,
            ema10.iloc[-1] < ema10.iloc[-5],
            ema30.iloc[-1] < ema30.iloc[-10]
        ])
        
        # 波动率
        volatility = data.iloc[-20:].pct_change().std()
        price_range = (data.iloc[-20:].max() - data.iloc[-20:].min()) / data.iloc[-20:].mean()
        
        # 动量
        momentum_5d = (data.iloc[-1] - data.iloc[-5]) / data.iloc[-5] if len(data) > 5 else 0
        momentum_10d = (data.iloc[-1] - data.iloc[-10]) / data.iloc[-10] if len(data) > 10 else 0
        
        # 综合判断
        # 先检查横盘（弱趋势 + 小价格范围）
        if abs(trend_10_60) < 0.005 and price_range < 0.04:
            return MarketRegime.RANGE_BOUND
        
        # 再检查趋势
        if up_count >= 2 and momentum_5d > 0 and momentum_10d > 0:
            return MarketRegime.TRENDING_UP
        
        if down_count >= 2 and momentum_5d < 0 and momentum_10d < 0:
            return MarketRegime.TRENDING_DOWN
        
        if price_range < 0.03 and abs(trend_10_60) < 0.01:
            return MarketRegime.RANGE_BOUND
        
        if volatility > 0.015 and abs(trend_10_60) < 0.015:
            return MarketRegime.VOLATILE
        
        if trend_10_60 < -0.008:
            return MarketRegime.TRENDING_DOWN
        elif trend_10_60 > 0.008:
            return MarketRegime.TRENDING_UP
        else:
            return MarketRegime.RANGE_BOUND
    
    def _detect_hmm_regime(self, data: pd.Series) -> MarketRegime:
        """
        基于 HMM 的市场状态检测
        
        使用收益率序列训练 HMM，识别隐含市场状态
        """
        if not self._hmm_available or len(data) < 60:
            return MarketRegime.UNKNOWN
        
        try:
            returns = data.pct_change().dropna().values.reshape(-1, 1)
            returns = returns[-100:]  # 使用最近100个数据点
            
            if len(returns) < 30:
                return MarketRegime.UNKNOWN
            
            self._hmm_model.fit(returns)
            hidden_states = self._hmm_model.predict(returns)
            
            # 统计各状态的出现频率和均值
            current_state = hidden_states[-1]
            state_means = []
            for i in range(self._hmm_model.n_components):
                mask = hidden_states == i
                if mask.sum() > 0:
                    state_means.append(returns[mask].mean())
                else:
                    state_means.append(0.0)
            
            # 根据均值判断状态
            max_mean_idx = np.argmax(state_means)
            min_mean_idx = np.argmin(state_means)
            
            if current_state == max_mean_idx and state_means[max_mean_idx] > 0.001:
                return MarketRegime.TRENDING_UP
            elif current_state == min_mean_idx and state_means[min_mean_idx] < -0.001:
                return MarketRegime.TRENDING_DOWN
            else:
                return MarketRegime.RANGE_BOUND
                
        except Exception as e:
            logger.warning(f"[MarketStateHub] HMM 检测失败: {e}")
            return MarketRegime.UNKNOWN
    
    def _detect_fourier_regime(self, data: pd.Series) -> MarketRegime:
        """
        基于傅里叶频谱分析的市场状态检测
        
        通过频谱能量分布判断市场状态
        """
        if len(data) < 60:
            return MarketRegime.UNKNOWN
        
        try:
            # 去趋势
            detrended = data.iloc[-128:] - data.iloc[-128:].mean()
            
            # FFT
            fft_vals = np.fft.fft(detrended.values)
            fft_mag = np.abs(fft_vals[:len(fft_vals)//2])
            
            # 频谱能量分布
            total_energy = np.sum(fft_mag)
            if total_energy == 0:
                return MarketRegime.RANGE_BOUND
            
            # 低频能量（趋势成分）
            low_freq_energy = np.sum(fft_mag[:len(fft_mag)//4])
            # 高频能量（噪声成分）
            high_freq_energy = np.sum(fft_mag[len(fft_mag)//2:])
            
            low_ratio = low_freq_energy / total_energy
            high_ratio = high_freq_energy / total_energy
            
            # 判断
            if low_ratio > 0.6:
                # 低频主导 → 趋势市场
                # 判断方向
                trend = (data.iloc[-1] - data.iloc[-20]) / data.iloc[-20] if len(data) > 20 else 0
                if trend > 0.02:
                    return MarketRegime.TRENDING_UP
                elif trend < -0.02:
                    return MarketRegime.TRENDING_DOWN
                else:
                    return MarketRegime.RANGE_BOUND
            elif high_ratio > 0.4:
                return MarketRegime.VOLATILE
            else:
                return MarketRegime.RANGE_BOUND
                
        except Exception as e:
            logger.warning(f"[MarketStateHub] 傅里叶检测失败: {e}")
            return MarketRegime.UNKNOWN
    
    def _fuse_regimes(
        self,
        technical: MarketRegime,
        hmm: Optional[MarketRegime],
        fourier: MarketRegime,
        data: pd.Series
    ) -> Tuple[MarketRegime, float]:
        """
        融合多个维度的市场状态判断
        
        改进的加权投票机制：
        1. 各维度权重归一化，确保总权重 = 1.0
        2. 置信度 = 最高票数 / 总有效票数，反映多维度一致性
        3. 各维度分歧时置信度自然降低，不会出现虚假高置信度
        4. 使用 RSI 和布林带位置作为辅助验证
        """
        votes = {}
        total_weight = 0.0
        
        # 技术指标权重 0.5
        votes[technical] = votes.get(technical, 0) + 0.5
        total_weight += 0.5
        
        # HMM 权重 0.3（如果可用）
        if hmm is not None and hmm != MarketRegime.UNKNOWN:
            votes[hmm] = votes.get(hmm, 0) + 0.3
            total_weight += 0.3
        
        # 傅里叶权重 0.2
        if fourier != MarketRegime.UNKNOWN:
            votes[fourier] = votes.get(fourier, 0) + 0.2
            total_weight += 0.2
        
        if not votes or total_weight == 0:
            return MarketRegime.RANGE_BOUND, 0.0
        
        # 选择得票最高的状态
        winner = max(votes, key=votes.get)
        
        # === 改进的置信度计算 ===
        # 基础置信度 = 最高票数 / 总权重
        base_confidence = votes[winner] / total_weight
        
        # 维度一致性惩罚：各维度分歧越大，置信度越低
        unique_votes = len(set(votes.keys()))
        if unique_votes >= 3:
            # 三个维度都不同 → 高度分歧，大幅降低置信度
            consistency_penalty = 0.5
        elif unique_votes == 2:
            # 两个维度一致，一个分歧 → 中等置信度
            consistency_penalty = 0.8
        else:
            # 所有维度一致 → 高置信度
            consistency_penalty = 1.0
        
        # 使用 RSI 验证趋势判断
        rsi = self._calculate_rsi(data)
        rsi_penalty = 1.0
        if winner == MarketRegime.TRENDING_UP and (rsi > 75 or rsi < 40):
            # 判断上涨但 RSI 显示超买或非超卖 → 降低置信度
            rsi_penalty = 0.6
        elif winner == MarketRegime.TRENDING_DOWN and (rsi < 25 or rsi > 60):
            # 判断下跌但 RSI 显示超卖或非超买 → 降低置信度
            rsi_penalty = 0.6
        
        # 最终置信度
        confidence = base_confidence * consistency_penalty * rsi_penalty
        
        # 置信度下限：即使高度一致，也保留一定的不确定性
        confidence = max(0.15, min(confidence, 0.95))
        
        return winner, confidence
    
    def _compute_transition_probs(self) -> Dict[str, float]:
        """
        计算状态转换概率
        
        基于历史状态序列统计
        """
        if len(self._state_history) < 20:
            return {}
        
        regimes = [s.regime.value for s in self._state_history]
        current = regimes[-1]
        
        # 统计从当前状态到各状态的转换频率
        transitions = {}
        for i in range(len(regimes) - 1):
            if regimes[i] == current:
                next_regime = regimes[i + 1]
                transitions[next_regime] = transitions.get(next_regime, 0) + 1
        
        total = sum(transitions.values())
        if total == 0:
            return {}
        
        return {k: v / total for k, v in transitions.items()}
    
    # ==================== 技术指标计算 ====================
    
    def _calculate_rsi(self, data: pd.Series, period: int = 14) -> float:
        """计算 RSI"""
        if len(data) < period + 1:
            return 50.0
        
        delta = data.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean().iloc[-1]
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean().iloc[-1]
        
        if loss == 0:
            return 100.0
        
        rs = gain / loss
        return 100.0 - (100.0 / (1.0 + rs))
    
    def _calculate_atr(self, data: pd.Series, period: int = 14) -> float:
        """计算 ATR"""
        if len(data) < period + 1:
            return 0.001
        
        high = data.rolling(window=2).max()
        low = data.rolling(window=2).min()
        close = data.shift(1)
        
        tr = pd.DataFrame()
        tr['h-l'] = high - low
        tr['h-pc'] = abs(high - close)
        tr['l-pc'] = abs(low - close)
        tr['tr'] = tr.max(axis=1)
        
        atr = tr['tr'].rolling(window=period).mean().iloc[-1]
        return atr / data.iloc[-1] if data.iloc[-1] > 0 else 0.001
    
    def _calculate_volatility(self, data: pd.Series, window: int = 20) -> float:
        """计算波动率"""
        if len(data) < window:
            return 0.0
        return data.iloc[-window:].pct_change().std()
    
    def _calculate_trend_strength(self, data: pd.Series) -> float:
        """计算趋势强度"""
        if len(data) < 60:
            return 0.0
        
        ema10 = data.ewm(span=10).mean().iloc[-1]
        ema60 = data.ewm(span=60).mean().iloc[-1]
        return (ema10 - ema60) / ema60 if ema60 > 0 else 0.0
    
    def _calculate_momentum(self, data: pd.Series, period: int = 10) -> float:
        """计算动量"""
        if len(data) < period:
            return 0.0
        return (data.iloc[-1] - data.iloc[-period]) / data.iloc[-period]
    
    def _calculate_bollinger_width(self, data: pd.Series, period: int = 20) -> float:
        """计算布林带宽度"""
        if len(data) < period:
            return 0.0
        
        ma = data.rolling(window=period).mean().iloc[-1]
        std = data.rolling(window=period).std().iloc[-1]
        
        if ma == 0 or std == 0:
            return 0.0
        
        return (2 * std) / ma
    
    def _calculate_price_position(self, data: pd.Series, period: int = 20) -> float:
        """计算价格在布林带中的位置 [0, 1]"""
        if len(data) < period:
            return 0.5
        
        ma = data.rolling(window=period).mean().iloc[-1]
        std = data.rolling(window=period).std().iloc[-1]
        
        if std == 0:
            return 0.5
        
        upper = ma + 2 * std
        lower = ma - 2 * std
        
        if upper == lower:
            return 0.5
        
        return (data.iloc[-1] - lower) / (upper - lower)
    
    # ==================== 统计接口 ====================
    
    def get_stats(self) -> Dict[str, Any]:
        """获取性能统计"""
        return {
            "enabled": self.enabled,
            "call_count": self._call_count,
            "cache_hit_count": self._cache_hit_count,
            "buffer_size": len(self._price_buffer),
            "state_history_size": len(self._state_history),
            "hmm_available": self._hmm_available,
            "current_regime": self._current_state.regime.value,
            "current_confidence": self._current_state.confidence,
            "stable_count": self._stable_count
        }


# ==================== 全局单例访问 ====================

_hub_instance = None


def get_market_state_hub() -> MarketStateHub:
    """
    获取 MarketStateHub 全局单例
    
    Returns:
        MarketStateHub 实例
    """
    global _hub_instance
    if _hub_instance is None:
        _hub_instance = MarketStateHub()
    return _hub_instance


# ==================== 快速测试 ====================

if __name__ == "__main__":
    # 生成测试数据
    np.random.seed(42)
    
    # 横盘数据
    range_data = pd.Series(100 + np.random.randn(200) * 0.5)
    
    # 上涨数据
    up_data = pd.Series(100 + np.linspace(0, 10, 200) + np.random.randn(200) * 0.5)
    
    # 下跌数据
    down_data = pd.Series(100 - np.linspace(0, 10, 200) + np.random.randn(200) * 0.5)
    
    hub = get_market_state_hub()
    hub.enabled = True
    
    print("=" * 60)
    print("MarketStateHub 快速测试")
    print("=" * 60)
    
    for name, data in [("横盘", range_data), ("上涨", up_data), ("下跌", down_data)]:
        regime = hub.get_market_regime(data)
        state = hub.get_full_state()
        print(f"\n{name}市场:")
        print(f"  状态: {regime}")
        print(f"  置信度: {state['confidence']:.2%}")
        print(f"  波动率: {state['volatility']:.4%}")
        print(f"  趋势强度: {state['trend_strength']:.4%}")
        print(f"  RSI: {state['rsi']:.1f}")
        print(f"  技术指标: {state['technical_regime']}")
        print(f"  傅里叶: {state['fourier_regime']}")
        if state['hmm_regime']:
            print(f"  HMM: {state['hmm_regime']}")
    
    print(f"\n统计信息: {hub.get_stats()}")
    print("\n✅ MarketStateHub 测试完成")
