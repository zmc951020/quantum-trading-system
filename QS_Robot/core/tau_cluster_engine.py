#!/usr/bin/env python3
"""
韬策略集群引擎 v2.0 — Tau Cluster Engine
==========================================

基于华为韬定律（τ-Law）的量化策略集群引擎：
  - 多策略协同：14个核心策略并行输出信号
  - 信号共振：多策略交叉验证，熵过滤，冲突仲裁
  - 动态权重：基于五维评分(E/V/H/M/P)的实时权重分配
  - 集群优化：集群级参数搜索，全局收益收敛
  - 持久化继承：优化成果永久保存，版本管理，自动恢复
  - 模块集成：与优化器、健康检查、实盘交易全链路打通

架构映射（韬定律 → 量化集群）：
  时间常数 τ → 策略信号生成→决策→下单全链路时延压缩
  逻辑折叠 3D → 多策略分层集群（信号层→共振层→权重层→优化层→执行层）
  全栈协同   → 全域统一约束方差、信息熵，实现整体收益收敛

依赖: tau_optimizer_cluster, tau_enhanced_optimizer, integration_bus
"""

from __future__ import annotations

import os
import json
import math
import random
import statistics
import time
import logging
import threading
import datetime
from collections import deque, defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple, Callable

logger = logging.getLogger(__name__)


# ============================================================
# 1. 统一信号数据模型
# ============================================================

@dataclass
class ClusterSignal:
    """统一策略信号 — 所有策略通过适配器输出此格式

    方向约定:
      +1.0 = 强烈看多
       0.0 = 中性/观望
      -1.0 = 强烈看空
    """
    strategy_name: str                          # 策略名称
    direction: float                            # 方向 [-1.0, +1.0]
    confidence: float                           # 置信度 [0.0, 1.0]
    strength: float                             # 信号强度 [0.0, 1.0]

    # 五维指标（由策略提供或估算）
    expectation: float = 0.0                    # 收益期望
    variance: float = 0.0                       # 方差
    entropy: float = 0.0                        # 决策熵
    extreme_risk: float = 0.0                   # 极端风险暴露
    win_probability: float = 0.5                # 胜率估计

    # 元数据
    timestamp: float = field(default_factory=time.time)
    market_regime: str = "unknown"              # 市场状态: trending/ranging/volatile
    extra: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_bullish(self) -> bool:
        return self.direction > 0.1

    @property
    def is_bearish(self) -> bool:
        return self.direction < -0.1

    @property
    def is_neutral(self) -> bool:
        return -0.1 <= self.direction <= 0.1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "strategy": self.strategy_name,
            "direction": round(self.direction, 4),
            "confidence": round(self.confidence, 4),
            "strength": round(self.strength, 4),
            "expectation": round(self.expectation, 4),
            "variance": round(self.variance, 4),
            "entropy": round(self.entropy, 4),
            "extreme_risk": round(self.extreme_risk, 4),
            "win_probability": round(self.win_probability, 4),
            "market_regime": self.market_regime,
            "is_bullish": self.is_bullish,
            "is_bearish": self.is_bearish,
        }


@dataclass
class ClusterDecision:
    """集群统一决策 — 韬策略引擎的最终输出"""
    direction: float                            # 综合方向 [-1.0, +1.0]
    confidence: float                           # 综合置信度
    position_ratio: float                       # 建议仓位比例 [0.0, 1.0]
    stop_loss: float = 0.0                      # 止损价
    take_profit: float = 0.0                    # 止盈价

    # 集群统计
    total_signals: int = 0                      # 参与策略数
    bullish_count: int = 0                      # 看多策略数
    bearish_count: int = 0                      # 看空策略数
    neutral_count: int = 0                      # 中性策略数
    resonance_count: int = 0                    # 共振策略数（≥2组同向）
    consensus_ratio: float = 0.0                # 共识比例

    # 五维集群指标
    cluster_expectation: float = 0.0
    cluster_variance: float = 0.0
    cluster_entropy: float = 0.0
    cluster_risk: float = 0.0
    cluster_win_prob: float = 0.0

    # 权重信息
    active_strategies: List[str] = field(default_factory=list)
    strategy_weights: Dict[str, float] = field(default_factory=dict)
    suppressed_strategies: List[str] = field(default_factory=list)

    # 元数据
    timestamp: float = field(default_factory=time.time)
    market_regime: str = "unknown"

    # 动作判定阈值（可被优化器搜索）
    action_threshold: float = 0.2

    @property
    def action(self) -> str:
        """交易动作

        使用可配置的 action_threshold 判定：
          direction > +threshold → BUY
          direction < -threshold → SELL
          否则 → HOLD

        threshold 越高 → 越保守（需要更强共识才交易）
        threshold 越低 → 越敏感（微弱共识即可交易）
        """
        if self.direction > self.action_threshold:
            return "BUY"
        elif self.direction < -self.action_threshold:
            return "SELL"
        else:
            return "HOLD"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action,
            "direction": round(self.direction, 4),
            "confidence": round(self.confidence, 4),
            "position_ratio": round(self.position_ratio, 4),
            "stop_loss": round(self.stop_loss, 4),
            "take_profit": round(self.take_profit, 4),
            "total_signals": self.total_signals,
            "bullish": self.bullish_count,
            "bearish": self.bearish_count,
            "neutral": self.neutral_count,
            "resonance": self.resonance_count,
            "consensus": round(self.consensus_ratio, 4),
            "cluster_expectation": round(self.cluster_expectation, 4),
            "cluster_variance": round(self.cluster_variance, 4),
            "cluster_entropy": round(self.cluster_entropy, 4),
            "cluster_risk": round(self.cluster_risk, 4),
            "cluster_win_prob": round(self.cluster_win_prob, 4),
            "active_strategies": self.active_strategies,
            "suppressed": self.suppressed_strategies,
            "weights": {k: round(v, 4) for k, v in self.strategy_weights.items()},
            "market_regime": self.market_regime,
        }


# ============================================================
# 2. 熵计算工具
# ============================================================

class EntropyTools:
    """轻量熵计算（避免与 tau_enhanced_optimizer 循环依赖）"""

    @staticmethod
    def shannon_entropy(values: List[float], bins: int = 10) -> float:
        """香农熵"""
        if len(values) < 2:
            return 0.0
        n = len(values)
        min_v, max_v = min(values), max(values)
        if min_v == max_v:
            return 0.0
        bin_width = (max_v - min_v) / bins
        counts = [0] * bins
        for v in values:
            idx = min(bins - 1, int((v - min_v) / bin_width))
            counts[idx] += 1
        entropy = 0.0
        for c in counts:
            if c > 0:
                p = c / n
                entropy -= p * math.log2(p)
        return entropy

    @staticmethod
    def decision_entropy(signals: List[float]) -> float:
        """决策熵 — 信号方向的一致程度"""
        if len(signals) < 2:
            return 0.0
        binary = [1 if s > 0 else (0 if s == 0 else -1) for s in signals]
        return EntropyTools.shannon_entropy(binary, bins=3)

    @staticmethod
    def signal_entropy(directions: List[float]) -> float:
        """信号方向熵 — 多策略信号分歧度"""
        if len(directions) < 2:
            return 0.0
        return EntropyTools.shannon_entropy(directions, bins=10)


# ============================================================
# 3. 策略信号适配器
# ============================================================

class StrategySignalAdapter:
    """策略信号适配器 — 将各类策略输出统一为 ClusterSignal

    每种策略的输出格式不同，适配器负责转换为统一的 ClusterSignal。
    支持两种模式：
      1. 函数模式：传入一个 callable，直接调用获取信号
      2. 策略实例模式：包装策略实例，调用其 update_price/get_signal 方法
    """

    def __init__(self, name: str, strategy_type: str = "generic",
                 signal_func: Callable = None, strategy_instance: Any = None):
        self.name = name
        self.strategy_type = strategy_type
        self.signal_func = signal_func
        self.strategy_instance = strategy_instance

        # 信号历史（用于计算五维指标）
        self._signal_history: deque = deque(maxlen=100)
        self._return_history: deque = deque(maxlen=100)
        self._direction_history: deque = deque(maxlen=50)

        # 性能追踪
        self.total_calls: int = 0
        self.success_calls: int = 0
        self.last_signal: Optional[ClusterSignal] = None

    def get_signal(self, market_data: Dict[str, Any] = None,
                   current_price: float = None) -> Optional[ClusterSignal]:
        """获取策略信号并转换为统一格式"""
        self.total_calls += 1

        try:
            # 模式1: 函数模式
            if self.signal_func:
                raw = self.signal_func(market_data, current_price)
                signal = self._parse_signal(raw)
            # 模式2: 策略实例模式
            elif self.strategy_instance:
                signal = self._get_signal_from_instance(market_data, current_price)
            else:
                logger.warning(f"[{self.name}] 无信号源配置")
                return None

            if signal is None:
                return None

            signal.strategy_name = self.name
            self._update_history(signal)
            self.success_calls += 1
            self.last_signal = signal
            return signal

        except Exception as e:
            logger.error(f"[{self.name}] 获取信号失败: {e}")
            return None

    def _parse_signal(self, raw: Any) -> Optional[ClusterSignal]:
        """解析原始信号为 ClusterSignal"""
        if raw is None:
            return None
        if isinstance(raw, ClusterSignal):
            return raw
        if isinstance(raw, dict):
            return ClusterSignal(
                strategy_name=self.name,
                direction=float(raw.get("direction", raw.get("signal", 0))),
                confidence=float(raw.get("confidence", 0.5)),
                strength=float(raw.get("strength", raw.get("intensity", 0.5))),
                expectation=float(raw.get("expectation", raw.get("expected_return", 0))),
                variance=float(raw.get("variance", 0)),
                entropy=float(raw.get("entropy", 0)),
                extreme_risk=float(raw.get("extreme_risk", raw.get("max_drawdown", 0))),
                win_probability=float(raw.get("win_probability", raw.get("win_rate", 0.5))),
                extra=raw.get("extra", {}),
            )
        if isinstance(raw, (int, float)):
            return ClusterSignal(
                strategy_name=self.name,
                direction=float(raw),
                confidence=abs(float(raw)),
            )
        return None

    def _get_signal_from_instance(self, market_data: Dict = None,
                                   current_price: float = None) -> Optional[ClusterSignal]:
        """从策略实例获取信号"""
        inst = self.strategy_instance
        if inst is None:
            return None

        # 尝试调用 update_price
        if hasattr(inst, 'update_price') and current_price is not None:
            result = inst.update_price(current_price, market_data)
            if isinstance(result, dict):
                return self._parse_signal(result)

        # 尝试调用 get_signal（传递 market_data 和 current_price）
        if hasattr(inst, 'get_signal'):
            try:
                return self._parse_signal(inst.get_signal(market_data, current_price))
            except TypeError:
                # 策略不支持参数，回退到无参调用
                return self._parse_signal(inst.get_signal())

        # 尝试直接读取属性
        direction = 0.0
        confidence = 0.5
        if hasattr(inst, 'position'):
            pos = inst.position
            direction = min(1.0, max(-1.0, pos / 1000.0)) if pos else 0.0
        if hasattr(inst, 'current_regime'):
            confidence = 0.6

        return ClusterSignal(
            strategy_name=self.name,
            direction=direction,
            confidence=confidence,
            strength=abs(direction),
        )

    def _update_history(self, signal: ClusterSignal):
        """更新信号历史"""
        self._signal_history.append(signal)
        self._direction_history.append(signal.direction)

    def get_five_metrics(self) -> Dict[str, float]:
        """从信号历史计算五维指标"""
        if not self._signal_history:
            return {"E": 0, "V": 0, "H": 0, "M": 0, "P": 0.5}

        signals = list(self._signal_history)
        directions = [s.direction for s in signals]

        return {
            "E": sum(s.expectation for s in signals[-20:]) / min(20, len(signals)),
            "V": statistics.variance(directions) if len(directions) >= 5 else 0,
            "H": EntropyTools.signal_entropy(directions),
            "M": max(abs(s.extreme_risk) for s in signals),
            "P": sum(s.win_probability for s in signals) / len(signals),
        }

    def get_success_rate(self) -> float:
        """信号获取成功率"""
        if self.total_calls == 0:
            return 1.0
        return self.success_calls / self.total_calls


# ============================================================
# 4. 信号共振验证器
# ============================================================

class SignalResonanceValidator:
    """信号共振验证器 — 韬定律交叉验证核心

    规则：
      1. 单策略信号需 ≥2 组策略共振才纳入候选
      2. 方向冲突时按置信度加权投票
      3. 高熵信号（分歧大）降低整体置信度
      4. 信号质量过滤：剔除低置信度噪声
    """

    def __init__(self,
                 min_resonance: int = 2,          # 最少共振策略数
                 min_confidence: float = 0.3,      # 最低置信度阈值
                 max_entropy: float = 0.85,        # 最大信号熵
                 consensus_threshold: float = 0.5,  # 共识阈值
                 ):
        self.min_resonance = min_resonance
        self.min_confidence = min_confidence
        self.max_entropy = max_entropy
        self.consensus_threshold = consensus_threshold

    def validate(self, signals: List[ClusterSignal]) -> Tuple[List[ClusterSignal], Dict[str, Any]]:
        """验证信号共振

        Returns:
            (validated_signals, resonance_report)
        """
        if not signals:
            return [], {"error": "无信号输入", "passed": False}

        # 1. 置信度过滤
        filtered = [s for s in signals if s.confidence >= self.min_confidence]
        noise_count = len(signals) - len(filtered)

        if len(filtered) < self.min_resonance:
            return filtered, {
                "passed": False,
                "reason": f"有效信号不足({len(filtered)}<{self.min_resonance})",
                "total": len(signals),
                "filtered": len(filtered),
                "noise": noise_count,
            }

        # 2. 方向分类
        bullish = [s for s in filtered if s.is_bullish]
        bearish = [s for s in filtered if s.is_bearish]
        neutral = [s for s in filtered if s.is_neutral]

        # 3. 加权投票
        bull_weight = sum(s.confidence * s.strength for s in bullish)
        bear_weight = sum(s.confidence * s.strength for s in bearish)

        total_weight = bull_weight + bear_weight
        if total_weight > 0:
            consensus = (bull_weight - bear_weight) / total_weight
        else:
            consensus = 0.0

        # 4. 共振检查
        dominant = bullish if bull_weight >= bear_weight else bearish
        has_resonance = len(dominant) >= self.min_resonance

        # 5. 信号熵（归一化到 [0,1]，与 max_entropy 可比）
        directions = [s.direction for s in filtered]
        raw_signal_entropy = EntropyTools.signal_entropy(directions)
        # 归一化：log2(10) ≈ 3.32 为最大熵
        signal_entropy = raw_signal_entropy / 3.32
        entropy_ok = signal_entropy <= self.max_entropy

        # 6. 综合判定
        passed = has_resonance and entropy_ok and abs(consensus) >= self.consensus_threshold

        report = {
            "passed": passed,
            "total": len(signals),
            "filtered": len(filtered),
            "noise": noise_count,
            "bullish": len(bullish),
            "bearish": len(bearish),
            "neutral": len(neutral),
            "bull_weight": round(bull_weight, 4),
            "bear_weight": round(bear_weight, 4),
            "consensus": round(consensus, 4),
            "has_resonance": has_resonance,
            "resonance_count": len(dominant) if has_resonance else 0,
            "signal_entropy": round(signal_entropy, 4),
            "entropy_ok": entropy_ok,
            "dominant_direction": "bullish" if bull_weight >= bear_weight else "bearish",
        }

        if not passed:
            reasons = []
            if not has_resonance:
                reasons.append(f"共振不足({len(dominant)}<{self.min_resonance})")
            if not entropy_ok:
                reasons.append(f"信号熵过高({signal_entropy:.3f}>{self.max_entropy})")
            if abs(consensus) < self.consensus_threshold:
                reasons.append(f"共识不足({abs(consensus):.3f}<{self.consensus_threshold})")
            report["reasons"] = reasons

        return filtered, report


# ============================================================
# 5. 动态权重调度器
# ============================================================

class EntropyWeightScheduler:
    """熵韬动态权重调度器

    基于五维评分(E/V/H/M/P)实时评估每个子策略，动态调整权重：
      - 高收益、低方差、低熵策略 → 提权
      - 高方差、高熵、低胜率策略 → 降权 → 休眠
      - 市场状态变化时自动切换策略优先级

    权重衰减机制：
      - 连续 N 次信号质量差 → 权重衰减
      - 休眠策略定期唤醒检测 → 恢复权重
    """

    def __init__(self,
                 base_weights: Dict[str, float] = None,
                 decay_rate: float = 0.3,           # 权重衰减率
                 recovery_threshold: float = 0.6,    # 恢复阈值
                 max_dormant_rounds: int = 10,       # 最大休眠轮次
                 ):
        self.base_weights = base_weights or {}
        self.decay_rate = decay_rate
        self.recovery_threshold = recovery_threshold
        self.max_dormant_rounds = max_dormant_rounds

        # 动态权重
        self._current_weights: Dict[str, float] = {}
        self._dormant_counters: Dict[str, int] = defaultdict(int)
        self._score_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=20))

        # 市场状态 → 策略优先级映射
        self._regime_strategy_map: Dict[str, List[str]] = {
            "trending": [],    # 趋势市优先策略
            "ranging": [],     # 震荡市优先策略
            "volatile": [],    # 高波动优先策略
            "bearish": [],     # 下跌市优先策略
        }

        self._lock = threading.RLock()

    def set_regime_priorities(self, regime: str, strategy_names: List[str]):
        """设置市场状态下的策略优先级"""
        self._regime_strategy_map[regime] = strategy_names

    def update_weights(self, signals: List[ClusterSignal],
                       market_regime: str = "unknown") -> Dict[str, float]:
        """根据最新信号更新权重

        Args:
            signals: 当前各策略信号
            market_regime: 当前市场状态

        Returns:
            {strategy_name: weight}
        """
        with self._lock:
            # 初始化权重
            if not self._current_weights:
                self._init_weights(signals)

            # 记录各策略评分
            for s in signals:
                score = self._calc_strategy_score(s)
                self._score_history[s.strategy_name].append(score)

            # 更新每个策略的权重
            new_weights = {}
            for s in signals:
                name = s.strategy_name
                current = self._current_weights.get(name, 1.0 / max(1, len(signals)))
                score = self._calc_strategy_score(s)

                # 质量评分
                if score >= self.recovery_threshold:
                    # 表现好 → 恢复/提升权重
                    self._dormant_counters[name] = 0
                    new_w = min(1.0, current * (1.0 + self.decay_rate * score))
                else:
                    # 表现差 → 衰减
                    self._dormant_counters[name] += 1
                    if self._dormant_counters[name] > self.max_dormant_rounds:
                        new_w = 0.0  # 休眠
                    else:
                        new_w = max(0.01, current * (1.0 - self.decay_rate))

                new_weights[name] = new_w

            # 归一化
            total = sum(new_weights.values())
            if total > 0:
                new_weights = {k: v / total for k, v in new_weights.items()}

            # 市场状态调整
            new_weights = self._apply_regime_bias(new_weights, market_regime)

            self._current_weights = new_weights
            return dict(new_weights)

    def _init_weights(self, signals: List[ClusterSignal]):
        """初始化权重（等权或使用预设）"""
        if self.base_weights:
            self._current_weights = dict(self.base_weights)
        else:
            n = len(signals)
            self._current_weights = {s.strategy_name: 1.0 / n for s in signals}

    def _calc_strategy_score(self, signal: ClusterSignal) -> float:
        """计算单个策略的质量评分（0-1）"""
        return (
            signal.confidence * 0.3 +
            signal.strength * 0.2 +
            (1.0 - min(1.0, signal.entropy)) * 0.2 +
            (1.0 - min(1.0, signal.variance * 10)) * 0.15 +
            signal.win_probability * 0.15
        )

    def _apply_regime_bias(self, weights: Dict[str, float],
                            market_regime: str) -> Dict[str, float]:
        """根据市场状态偏置权重"""
        priority_strategies = self._regime_strategy_map.get(market_regime, [])
        if not priority_strategies:
            return weights

        # 对优先策略提权 20%
        result = dict(weights)
        for name in priority_strategies:
            if name in result:
                result[name] = min(1.0, result[name] * 1.2)

        # 重新归一化
        total = sum(result.values())
        if total > 0:
            result = {k: v / total for k, v in result.items()}

        return result

    def get_dormant_strategies(self) -> List[str]:
        """获取休眠策略列表"""
        with self._lock:
            return [name for name, c in self._dormant_counters.items()
                    if c > self.max_dormant_rounds]

    def get_current_weights(self) -> Dict[str, float]:
        with self._lock:
            return dict(self._current_weights)

    def restore_weights(self, weights: Dict[str, float]):
        """从持久化存储恢复权重（用于继承优化成果）"""
        with self._lock:
            self._current_weights = dict(weights)
            # 重置休眠计数器
            self._dormant_counters = defaultdict(int)
            logger.info(f"[EntropyWeight] 权重已恢复: {len(weights)}个策略")

    def reset_weights(self):
        """重置权重到初始状态"""
        with self._lock:
            self._current_weights = {}
            self._dormant_counters = defaultdict(int)
            self._score_history = defaultdict(lambda: deque(maxlen=20))
            logger.info("[EntropyWeight] 权重已重置")


# ============================================================
# 6. 市场状态识别器
# ============================================================

class MarketRegimeDetector:
    """市场状态识别器 — 判断当前处于趋势/震荡/高波动/下跌市"""

    def __init__(self, lookback: int = 20):
        self.lookback = lookback
        self._price_history: deque = deque(maxlen=lookback * 2)

    def feed(self, price: float):
        """喂入价格数据"""
        self._price_history.append(price)

    def detect(self) -> str:
        """识别当前市场状态"""
        if len(self._price_history) < self.lookback:
            return "unknown"

        prices = list(self._price_history)[-self.lookback:]

        # 计算收益率统计
        returns = [prices[i] / prices[i - 1] - 1 for i in range(1, len(prices))]
        if not returns:
            return "unknown"

        mean_ret = statistics.mean(returns)
        std_ret = statistics.stdev(returns) if len(returns) >= 2 else 0

        # 判断逻辑
        # 先判断下跌（避免被趋势判断覆盖）
        if mean_ret < -0.003:     # 日均下跌 > 0.3%
            return "bearish"
        elif std_ret > 0.03:          # 日波动 > 3%
            return "volatile"
        elif abs(mean_ret) / max(std_ret, 0.0001) > 1.2:  # 趋势明显
            return "trending"
        else:
            return "ranging"

    def reset(self):
        """重置价格历史"""
        self._price_history.clear()


# ============================================================
# 7. 韬策略集群引擎主类
# ============================================================

class TauClusterEngine:
    """韬策略集群引擎 — 主控制器

    用法:
        engine = TauClusterEngine()
        engine.register_strategy("bernoulli", adapter)
        engine.register_strategy("fourier", adapter)
        ...
        decision = engine.evaluate(market_data, current_price)
    """

    def __init__(self,
                 min_resonance: int = 2,
                 consensus_threshold: float = 0.4,
                 action_threshold: float = 0.2,
                 config: Dict[str, Any] = None):
        """
        Args:
            min_resonance: 最少共振策略数
            consensus_threshold: 共识阈值
            action_threshold: 交易动作判定阈值（方向绝对值 > 此值才产生 BUY/SELL）
            config: 额外配置
        """
        self.config = config or {}

        # 引擎参数（暴露为实例属性，供持久化和优化器使用）
        self.min_resonance = min_resonance
        self.consensus_threshold = consensus_threshold
        self.action_threshold = action_threshold

        # 分股票阈值配置（不同股票可有不同最优阈值）
        self.per_stock_thresholds: Dict[str, float] = {}  # {stock_code: threshold}

        # 核心组件子模块
        self.validator = SignalResonanceValidator(
            min_resonance=min_resonance,
            consensus_threshold=consensus_threshold,
        )
        self.weight_scheduler = EntropyWeightScheduler(
            recovery_threshold=0.4,          # 降低恢复阈值，适配模拟/真实策略评分范围
            max_dormant_rounds=30,           # 延长休眠容忍轮次
        )
        self.regime_detector = MarketRegimeDetector()

        # 策略适配器注册表
        self._adapters: Dict[str, StrategySignalAdapter] = {}
        self._lock = threading.RLock()

        # 决策历史
        self._decision_history: deque = deque(maxlen=200)
        self._performance_history: deque = deque(maxlen=500)

        # 统计
        self.total_evaluations: int = 0
        self.total_decisions: int = 0

    # ---- 策略注册 ----

    def register_strategy(self, name: str, adapter: StrategySignalAdapter):
        """注册策略适配器"""
        with self._lock:
            self._adapters[name] = adapter
            logger.info(f"[TauCluster] 注册策略: {name} (type={adapter.strategy_type})")

    def register_strategy_func(self, name: str, strategy_type: str,
                                signal_func: Callable):
        """通过函数注册策略（便捷方法）"""
        adapter = StrategySignalAdapter(name, strategy_type, signal_func=signal_func)
        self.register_strategy(name, adapter)
        return adapter

    def unregister_strategy(self, name: str):
        """移除策略"""
        with self._lock:
            self._adapters.pop(name, None)

    def get_registered_strategies(self) -> List[str]:
        with self._lock:
            return list(self._adapters.keys())

    # ---- 核心评估 ----

    def evaluate(self, market_data: Dict[str, Any] = None,
                 current_price: float = None) -> ClusterDecision:
        """执行集群评估，输出统一交易决策

        Args:
            market_data: 市场数据字典（可包含 stock_code 用于分股票阈值）
            current_price: 当前价格

        Returns:
            ClusterDecision: 集群统一决策
        """
        self.total_evaluations += 1
        t_start = time.time()

        # 提取股票代码（用于分股票阈值）
        stock_code = None
        if market_data:
            stock_code = market_data.get("stock_code") or market_data.get("code")

        # 更新市场状态
        if current_price:
            self.regime_detector.feed(current_price)
        market_regime = self.regime_detector.detect()

        # 1. 收集所有策略信号
        signals: List[ClusterSignal] = []
        with self._lock:
            for name, adapter in self._adapters.items():
                signal = adapter.get_signal(market_data, current_price)
                if signal:
                    signal.market_regime = market_regime
                    signals.append(signal)

        # 2. 信号共振验证
        validated_signals, resonance_report = self.validator.validate(signals)

        # 3. 动态权重更新
        weights = self.weight_scheduler.update_weights(validated_signals, market_regime)

        # 4. 计算集群统一信号
        decision = self._compute_cluster_decision(
            validated_signals, weights, resonance_report, market_regime,
            stock_code=stock_code
        )

        # 5. 计算风控参数
        if current_price:
            self._apply_risk_params(decision, current_price, validated_signals)

        self._decision_history.append(decision)
        self.total_decisions += 1

        elapsed = (time.time() - t_start) * 1000
        logger.debug(f"[TauCluster] 评估完成: action={decision.action}, "
                     f"confidence={decision.confidence:.2f}, "
                     f"resonance={decision.resonance_count}, "
                     f"elapsed={elapsed:.1f}ms")

        return decision

    def _compute_cluster_decision(self, signals: List[ClusterSignal],
                                   weights: Dict[str, float],
                                   resonance: Dict[str, Any],
                                   market_regime: str,
                                   stock_code: str = None) -> ClusterDecision:
        """计算集群统一决策

        Args:
            stock_code: 股票代码，用于分股票阈值配置
        """
        if not signals:
            return ClusterDecision(
                direction=0, confidence=0, position_ratio=0,
                stop_loss=0, take_profit=0, market_regime=market_regime,
            )

        # 加权方向
        weighted_direction = 0.0
        total_weight = 0.0
        for s in signals:
            w = weights.get(s.strategy_name, 1.0 / len(signals))
            weighted_direction += s.direction * s.confidence * w
            total_weight += w

        direction = weighted_direction / max(total_weight, 0.001)
        direction = max(-1.0, min(1.0, direction))

        # 综合置信度（共识 * 熵降噪）
        normalized_entropy = resonance.get("signal_entropy", 0.5)  # 已归一化到[0,1]
        confidence = resonance.get("consensus", 0.5) * (1.0 - normalized_entropy)

        # 仓位比例
        position_ratio = abs(direction) * confidence
        position_ratio = max(0.0, min(1.0, position_ratio))

        # 五维集群指标
        cluster_metrics = self._compute_cluster_metrics(signals, weights)

        # 统计
        bullish = [s for s in signals if s.is_bullish]
        bearish = [s for s in signals if s.is_bearish]
        neutral = [s for s in signals if s.is_neutral]

        dormant = self.weight_scheduler.get_dormant_strategies()

        # 分股票阈值：优先使用该股票的专属阈值，否则使用全局默认
        threshold = self.action_threshold
        if stock_code and stock_code in self.per_stock_thresholds:
            threshold = self.per_stock_thresholds[stock_code]

        return ClusterDecision(
            direction=direction,
            confidence=confidence,
            position_ratio=position_ratio,
            stop_loss=0.0,
            take_profit=0.0,
            action_threshold=threshold,
            total_signals=len(signals),
            bullish_count=len(bullish),
            bearish_count=len(bearish),
            neutral_count=len(neutral),
            resonance_count=resonance.get("resonance_count", 0),
            consensus_ratio=resonance.get("consensus", 0),
            cluster_expectation=cluster_metrics.get("E", 0),
            cluster_variance=cluster_metrics.get("V", 0),
            cluster_entropy=cluster_metrics.get("H", 0),
            cluster_risk=cluster_metrics.get("M", 0),
            cluster_win_prob=cluster_metrics.get("P", 0),
            active_strategies=[s.strategy_name for s in signals],
            strategy_weights=weights,
            suppressed_strategies=dormant,
            market_regime=market_regime,
        )

    def _compute_cluster_metrics(self, signals: List[ClusterSignal],
                                  weights: Dict[str, float]) -> Dict[str, float]:
        """计算集群五维指标"""
        if not signals:
            return {"E": 0, "V": 0, "H": 0, "M": 0, "P": 0}

        directions = [s.direction for s in signals]
        confidences = [s.confidence for s in signals]

        raw_entropy = EntropyTools.signal_entropy(directions)

        return {
            "E": statistics.mean(directions),
            "V": statistics.variance(directions) if len(directions) >= 2 else 0,
            "H": raw_entropy / 3.32,  # 归一化到 [0,1]
            "M": max(abs(s.extreme_risk) for s in signals),
            "P": statistics.mean(confidences),
        }

    def _apply_risk_params(self, decision: ClusterDecision, current_price: float,
                            signals: List[ClusterSignal]):
        """计算止损止盈"""
        decision.stop_loss = current_price * 0.95
        decision.take_profit = current_price * 1.10

        # 如果集群熵高（分歧大），收紧止损
        if decision.cluster_entropy > 0.7:
            decision.stop_loss = current_price * 0.97
            decision.position_ratio *= 0.5

        # 如果极端风险高，降低仓位
        if decision.cluster_risk > 0.3:
            decision.position_ratio *= 0.5

    # ---- 查询接口 ----

    def get_last_decision(self) -> Optional[ClusterDecision]:
        """获取最近一次决策"""
        if self._decision_history:
            return self._decision_history[-1]
        return None

    def set_stock_threshold(self, stock_code: str, threshold: float):
        """设置某只股票的专属动作阈值

        不同股票波动特性不同，最优阈值可能不同：
        - 高波动股票（创业板）→ 更高阈值（0.3-0.4）
        - 低波动股票（银行股）→ 更低阈值（0.1-0.15）

        Args:
            stock_code: 股票代码（如 '000001', '300750'）
            threshold: 动作阈值 [0.05, 0.50]
        """
        self.per_stock_thresholds[stock_code] = max(0.05, min(0.50, threshold))
        logger.info(f"[TauCluster] {stock_code} 专属阈值 = {self.per_stock_thresholds[stock_code]}")

    def get_stock_threshold(self, stock_code: str) -> float:
        """获取某只股票的专属阈值（无配置则返回全局默认）"""
        return self.per_stock_thresholds.get(stock_code, self.action_threshold)

    def clear_stock_thresholds(self):
        """清除所有分股票阈值配置"""
        self.per_stock_thresholds.clear()

    def get_decision_history(self, n: int = 20) -> List[ClusterDecision]:
        return list(self._decision_history)[-n:]

    def get_cluster_health(self) -> Dict[str, Any]:
        """集群健康报告"""
        with self._lock:
            adapter_count = len(self._adapters)
            active_count = sum(1 for a in self._adapters.values()
                              if a.last_signal is not None)
            dormant = self.weight_scheduler.get_dormant_strategies()

            return {
                "total_strategies": adapter_count,
                "active_strategies": active_count,
                "dormant_strategies": len(dormant),
                "dormant_list": dormant,
                "total_evaluations": self.total_evaluations,
                "total_decisions": self.total_decisions,
                "current_weights": self.weight_scheduler.get_current_weights(),
                "market_regime": self.regime_detector.detect(),
                "last_decision": self.get_last_decision().to_dict() if self.get_last_decision() else None,
            }

    def get_strategy_performance(self, strategy_name: str) -> Dict[str, Any]:
        """获取单个策略的绩效"""
        adapter = self._adapters.get(strategy_name)
        if not adapter:
            return {"error": f"策略 {strategy_name} 未注册"}

        return {
            "name": strategy_name,
            "type": adapter.strategy_type,
            "success_rate": adapter.get_success_rate(),
            "five_metrics": adapter.get_five_metrics(),
            "total_calls": adapter.total_calls,
            "last_signal": adapter.last_signal.to_dict() if adapter.last_signal else None,
        }

    # ================================================================
    # 9. 优化成果永久性继承 (持久化 + 版本管理 + 自动恢复)
    # ================================================================

    # 集群引擎专用存储文件名
    CLUSTER_STORE_FILE = "tau_cluster_engine_store.json"

    def _get_store_path(self) -> str:
        """获取持久化存储路径"""
        module_dir = os.path.dirname(os.path.abspath(__file__))
        store_dir = os.path.join(os.path.dirname(module_dir), "data")
        os.makedirs(store_dir, exist_ok=True)
        return os.path.join(store_dir, self.CLUSTER_STORE_FILE)

    def save_state(self, optimizer_name: str = "grid_search",
                   score: float = None, metadata: Dict = None) -> Dict[str, Any]:
        """
        持久化当前集群引擎的完整状态（优化成果永久继承）

        保存内容：
          - 引擎参数（min_resonance, consensus_threshold）
          - 策略权重（当前动态权重）
          - 策略类型映射（name → type）
          - 权重衰减历史
          - 优化元数据（方法、评分、时间戳）
          - 版本号（自动递增）

        Args:
            optimizer_name: 优化器名称（用于记录优化来源）
            score: 当前综合评分
            metadata: 额外元数据

        Returns:
            {success, version, file_path, is_new_best}
        """
        store_path = self._get_store_path()

        # 加载已有数据
        existing = {}
        if os.path.exists(store_path):
            try:
                with open(store_path, 'r', encoding='utf-8') as f:
                    existing = json.load(f)
            except Exception:
                pass

        # 计算当前版本号
        history = existing.get("optimization_history", [])
        latest_version = max((h.get("version", 0) for h in history), default=0)
        new_version = latest_version + 1

        # 检查是否超越历史最佳
        past_best_score = existing.get("best_score", -float("inf"))
        is_new_best = score is not None and score > past_best_score

        with self._lock:
            # 当前状态快照
            state = {
                "version": new_version,
                "timestamp": datetime.datetime.now().isoformat(),
                "optimizer": optimizer_name,
                "score": score,
                "engine_params": {
                    "min_resonance": self.min_resonance,
                    "consensus_threshold": self.consensus_threshold,
                    "action_threshold": self.action_threshold,
                },
                "per_stock_thresholds": dict(self.per_stock_thresholds),
                "strategy_weights": self.weight_scheduler.get_current_weights(),
                "strategy_types": {
                    name: adapter.strategy_type
                    for name, adapter in self._adapters.items()
                },
                "dormant_strategies": self.weight_scheduler.get_dormant_strategies(),
                "strategy_performance": {
                    name: self.get_strategy_performance(name)
                    for name in self._adapters
                },
                "market_regime": self.regime_detector.detect(),
                "total_evaluations": self.total_evaluations,
                "total_decisions": self.total_decisions,
                "metadata": metadata or {},
            }

            # 更新存储
            history.append(state)

            # 只保留最近50个版本（避免文件过大）
            if len(history) > 50:
                history = history[-50:]

            store_data = {
                "_meta": {
                    "store_name": "韬策略集群引擎 - 优化成果持久化存储",
                    "created": existing.get("_meta", {}).get("created",
                        datetime.datetime.now().isoformat()),
                    "last_updated": datetime.datetime.now().isoformat(),
                    "total_versions": len(history),
                },
                "best_score": max(score or 0, past_best_score),
                "best_version": new_version if is_new_best else existing.get("best_version"),
                "optimization_history": history,
            }

            if is_new_best:
                store_data["best_version"] = new_version

            try:
                with open(store_path, 'w', encoding='utf-8') as f:
                    json.dump(store_data, f, ensure_ascii=False, indent=2)
                logger.info(f"[TauCluster] 状态已持久化: v{new_version}, "
                           f"score={score}, is_new_best={is_new_best}")
            except Exception as e:
                logger.error(f"[TauCluster] 持久化失败: {e}")
                return {"success": False, "error": str(e)}

        return {
            "success": True,
            "version": new_version,
            "file_path": store_path,
            "is_new_best": is_new_best,
            "score_delta": (score - past_best_score) if score is not None and past_best_score != -float("inf") else None,
        }

    def load_state(self, version: int = None) -> Dict[str, Any]:
        """
        从持久化存储恢复集群引擎状态

        Args:
            version: 指定恢复的版本号（None = 恢复最佳版本）

        Returns:
            {success, version, restored_params, strategy_count}
        """
        store_path = self._get_store_path()
        if not os.path.exists(store_path):
            return {"success": False, "error": "存储文件不存在，无历史优化记录"}

        try:
            with open(store_path, 'r', encoding='utf-8') as f:
                store_data = json.load(f)
        except Exception as e:
            return {"success": False, "error": f"读取存储文件失败: {e}"}

        history = store_data.get("optimization_history", [])
        if not history:
            return {"success": False, "error": "存储中无优化历史"}

        # 选择版本
        if version is not None:
            target = next((h for h in history if h.get("version") == version), None)
            if target is None:
                return {"success": False, "error": f"版本 v{version} 不存在"}
        else:
            # 恢复最佳版本
            best_version = store_data.get("best_version")
            if best_version:
                target = next((h for h in history if h.get("version") == best_version), None)
            if target is None:
                target = history[-1]  # 回退到最新版本

        with self._lock:
            ep = target.get("engine_params", {})
            if ep:
                self.min_resonance = ep.get("min_resonance", self.min_resonance)
                self.consensus_threshold = ep.get("consensus_threshold", self.consensus_threshold)
                self.action_threshold = ep.get("action_threshold", self.action_threshold)
                # 同步到子模块
                self.validator.min_resonance = self.min_resonance
                self.validator.consensus_threshold = self.consensus_threshold

            # 恢复分股票阈值
            pst = target.get("per_stock_thresholds", {})
            if pst:
                self.per_stock_thresholds = dict(pst)

            # 恢复策略权重
            weights = target.get("strategy_weights", {})
            if weights:
                self.weight_scheduler.restore_weights(weights)

            logger.info(f"[TauCluster] 状态已恢复: v{target.get('version')}, "
                       f"score={target.get('score')}, "
                       f"params={ep}")

        return {
            "success": True,
            "version": target.get("version"),
            "restored_params": ep,
            "strategy_count": len(target.get("strategy_weights", {})),
            "score": target.get("score"),
            "timestamp": target.get("timestamp"),
        }

    def get_optimization_history(self) -> List[Dict[str, Any]]:
        """获取优化历史摘要"""
        store_path = self._get_store_path()
        if not os.path.exists(store_path):
            return []

        try:
            with open(store_path, 'r', encoding='utf-8') as f:
                store_data = json.load(f)
        except Exception:
            return []

        history = store_data.get("optimization_history", [])
        return [{
            "version": h.get("version"),
            "timestamp": h.get("timestamp"),
            "optimizer": h.get("optimizer"),
            "score": h.get("score"),
            "params": h.get("engine_params"),
            "strategy_count": len(h.get("strategy_weights", {})),
        } for h in history]

    def reset_state(self, keep_strategies: bool = True) -> Dict[str, Any]:
        """
        重置引擎状态到初始值（保留策略注册）

        Args:
            keep_strategies: 是否保留已注册的策略
        """
        with self._lock:
            self.min_resonance = 2  # 类默认值
            self.consensus_threshold = 0.4
            self.action_threshold = 0.2
            self.validator.min_resonance = self.min_resonance
            self.validator.consensus_threshold = self.consensus_threshold
            self.weight_scheduler.reset_weights()
            self.regime_detector.reset()
            self.total_evaluations = 0
            self.total_decisions = 0
            self._decision_history.clear()

            if not keep_strategies:
                self._adapters.clear()

        logger.info("[TauCluster] 引擎状态已重置")
        return {"success": True, "message": "引擎状态已重置到初始值"}

    # ================================================================
    # 10. 策略类型归档 (可视化模块可见)
    # ================================================================

    # 核心交易策略类型定义（供可视化模块引用）
    STRATEGY_TYPE_ARCHIVE = {
        "gyro": {
            "name": "陀螺仪策略",
            "category": "物理模型",
            "icon": "gyroscope",
            "optimizer": "GyroModule",
            "description": "基于陀螺仪原理的趋势跟踪策略",
        },
        "bernoulli": {
            "name": "伯努利-康达策略",
            "category": "物理模型",
            "icon": "fluid",
            "optimizer": "BernoulliCoandaModule",
            "description": "基于流体力学原理的自适应策略",
        },
        "fourier": {
            "name": "傅里叶+RL策略",
            "category": "ML模型",
            "icon": "wave",
            "optimizer": "FourierRLStrategyModule",
            "description": "傅里叶特征提取+强化学习决策",
        },
        "shepherd": {
            "name": "智能标的轮动策略",
            "category": "轮动模型",
            "icon": "rotation",
            "optimizer": "ShepherdRotationModule",
            "description": "68因子分层优化标的轮动",
        },
        "grid": {
            "name": "网格交易策略",
            "category": "传统策略",
            "icon": "grid",
            "optimizer": "TauOptimizerCluster",
            "description": "价格区间网格交易",
        },
        "trend": {
            "name": "趋势跟踪策略",
            "category": "传统策略",
            "icon": "trending_up",
            "optimizer": "TauOptimizerCluster",
            "description": "均线/趋势跟踪",
        },
        "ml": {
            "name": "机器学习策略",
            "category": "ML模型",
            "icon": "brain",
            "optimizer": "TauOptimizerCluster",
            "description": "自适应ML交易策略",
        },
        "rl": {
            "name": "强化学习策略",
            "category": "ML模型",
            "icon": "robot",
            "optimizer": "FourierRLStrategyModule",
            "description": "PPO/RL智能体交易",
        },
        "value": {
            "name": "价值轮动策略",
            "category": "轮动模型",
            "icon": "diamond",
            "optimizer": "TauOptimizerCluster",
            "description": "基于价值的标的轮动",
        },
        "multifactor": {
            "name": "多因子共振策略",
            "category": "传统策略",
            "icon": "filter",
            "optimizer": "TauOptimizerCluster",
            "description": "多因子信号共振",
        },
        "fund": {
            "name": "定投/资金管理策略",
            "category": "传统策略",
            "icon": "wallet",
            "optimizer": "TauOptimizerCluster",
            "description": "定投及资金管理",
        },
        "defense": {
            "name": "下跌防御策略",
            "category": "风控策略",
            "icon": "shield",
            "optimizer": "TauOptimizerCluster",
            "description": "下跌市场防御",
        },
        "ensemble": {
            "name": "综合融合策略",
            "category": "ML模型",
            "icon": "layers",
            "optimizer": "TauOptimizerCluster",
            "description": "多策略综合融合",
        },
        "physics": {
            "name": "物理模型策略",
            "category": "物理模型",
            "icon": "science",
            "optimizer": "TauOptimizerCluster",
            "description": "基于物理学原理的量化策略",
        },
        "noise": {
            "name": "噪声/无效策略",
            "category": "待分类",
            "icon": "warning",
            "optimizer": None,
            "description": "噪声或未分类策略（待分析）",
        },
        "generic": {
            "name": "通用策略",
            "category": "待分类",
            "icon": "question_mark",
            "optimizer": "TauOptimizerCluster",
            "description": "通用/未分类策略",
        },
    }

    @classmethod
    def get_strategy_type_archive(cls) -> Dict[str, Dict[str, str]]:
        """获取完整的策略类型归档（供可视化模块使用）"""
        return dict(cls.STRATEGY_TYPE_ARCHIVE)

    def get_registered_strategy_archive(self) -> List[Dict[str, Any]]:
        """
        获取当前已注册策略的归档信息（供可视化模块列表显示）

        Returns:
            [{name, type, category, icon, optimizer, weight, performance, ...}]
        """
        archive = self.get_strategy_type_archive()
        result = []

        with self._lock:
            for name, adapter in self._adapters.items():
                type_info = archive.get(adapter.strategy_type, archive["generic"])
                weights = self.weight_scheduler.get_current_weights()
                perf = self.get_strategy_performance(name)

                result.append({
                    "name": name,
                    "type": adapter.strategy_type,
                    "type_display": type_info["name"],
                    "category": type_info["category"],
                    "icon": type_info["icon"],
                    "optimizer": type_info["optimizer"],
                    "description": type_info["description"],
                    "weight": weights.get(name, 0),
                    "success_rate": perf.get("success_rate", 0),
                    "five_metrics": perf.get("five_metrics", {}),
                    "total_calls": adapter.total_calls,
                    "is_dormant": name in self.weight_scheduler.get_dormant_strategies(),
                })

        return result

    def get_type_summary(self) -> Dict[str, Any]:
        """
        获取策略类型汇总（供可视化模块仪表盘）

        Returns:
            {total_strategies, type_distribution, category_distribution, ...}
        """
        archive = self.get_strategy_type_archive()
        type_dist = defaultdict(int)
        category_dist = defaultdict(int)
        total_weight = 0.0

        with self._lock:
            weights = self.weight_scheduler.get_current_weights()
            for name, adapter in self._adapters.items():
                st = adapter.strategy_type
                type_dist[st] += 1
                cat = archive.get(st, {}).get("category", "待分类")
                category_dist[cat] += 1
                total_weight += weights.get(name, 0)

        return {
            "total_strategies": len(self._adapters),
            "total_weight": round(total_weight, 4),
            "type_distribution": dict(type_dist),
            "category_distribution": dict(category_dist),
            "active_types": list(type_dist.keys()),
            "version": "2.0",
        }

    # ================================================================
    # 11. 集成总线接口 (优化器 ← → 集群引擎 ← → 健康检查 ← → 实盘交易)
    # ================================================================

    def to_optimizer_params(self) -> Dict[str, Tuple[float, float]]:
        """
        导出可被优化器搜索的参数空间

        供 EntropyTauOptimizer / TauOptimizerCluster 调用，
        实现「优化器 → 集群引擎」的参数优化回路

        Returns:
            {param_name: (min, max)} 参数范围
        """
        return {
            "min_resonance": (1.0, 5.0),
            "consensus_threshold": (0.05, 0.60),
            "action_threshold": (0.05, 0.50),    # 动作判定阈值：0.05=极敏感, 0.50=极保守
        }

    def apply_optimizer_result(self, best_params: Dict[str, float],
                                score: float = None) -> Dict[str, Any]:
        """
        应用优化器的搜索结果（优化器 → 集群引擎）

        Args:
            best_params: 优化器找到的最佳参数
            score: 优化评分

        Returns:
            {success, applied_params, previous_params}
        """
        with self._lock:
            previous = {
                "min_resonance": self.min_resonance,
                "consensus_threshold": self.consensus_threshold,
                "action_threshold": self.action_threshold,
            }

            if "min_resonance" in best_params:
                self.min_resonance = int(best_params["min_resonance"])
                self.validator.min_resonance = self.min_resonance
            if "consensus_threshold" in best_params:
                self.consensus_threshold = float(best_params["consensus_threshold"])
                self.validator.consensus_threshold = self.consensus_threshold
            if "action_threshold" in best_params:
                self.action_threshold = float(best_params["action_threshold"])

            logger.info(f"[TauCluster] 优化器参数已应用: {previous} → {best_params}")

        # 自动持久化
        save_result = self.save_state(
            optimizer_name="entropy_tau_optimizer",
            score=score,
            metadata={"previous_params": previous, "applied_params": best_params},
        )

        return {
            "success": True,
            "applied_params": {
                "min_resonance": self.min_resonance,
                "consensus_threshold": self.consensus_threshold,
                "action_threshold": self.action_threshold,
            },
            "previous_params": previous,
            "persisted": save_result,
        }

    def to_trade_signal(self) -> Optional[Dict[str, Any]]:
        """
        将最近一次集群决策转换为实盘交易信号（集群引擎 → 实盘交易）

        供 TradeExecutor.execute_signal() 消费

        Returns:
            TradeSignal 格式的字典，或 None（无有效决策）
        """
        decision = self.get_last_decision()
        if not decision or decision.action == "HOLD":
            return None

        return {
            "signal_id": f"tau_{int(time.time() * 1000)}",
            "timestamp": datetime.datetime.now().isoformat(),
            "action": decision.action,  # BUY / SELL / HOLD
            "direction": decision.direction,
            "confidence": decision.confidence,
            "position_ratio": decision.position_ratio,
            "stop_loss": decision.stop_loss,
            "take_profit": decision.take_profit,
            "source": "tau_cluster_engine",
            "source_version": "2.0",
            "resonance_count": decision.resonance_count,
            "total_signals": decision.total_signals,
            "bullish_count": decision.bullish_count,
            "bearish_count": decision.bearish_count,
            "market_regime": decision.market_regime,
            "five_metrics": {
                "E": decision.cluster_expectation,
                "V": decision.cluster_variance,
                "H": decision.cluster_entropy,
                "M": decision.cluster_risk,
                "P": decision.cluster_win_prob,
            },
            "active_strategies": decision.active_strategies,
            "suppressed_strategies": decision.suppressed_strategies,
        }

    def get_health_for_checker(self) -> Dict[str, Any]:
        """
        输出符合 SystemHealthChecker 格式的健康报告
        （集群引擎 → 系统健康检查）

        Returns:
            {
                status: "healthy" / "warning" / "critical",
                checks: [{name, status, message, ...}],
                metrics: {...},
                timestamp: "...",
            }
        """
        health = self.get_cluster_health()

        checks = []
        warnings = 0
        criticals = 0

        # 检查1：策略数量
        strategy_count = health["total_strategies"]
        if strategy_count >= 10:
            checks.append({"name": "策略数量", "status": "pass",
                          "message": f"{strategy_count}个策略已注册"})
        elif strategy_count >= 5:
            checks.append({"name": "策略数量", "status": "warn",
                          "message": f"仅{strategy_count}个策略，建议≥10个"})
            warnings += 1
        else:
            checks.append({"name": "策略数量", "status": "fail",
                          "message": f"仅{strategy_count}个策略，严重不足"})
            criticals += 1

        # 检查2：活跃策略
        active_count = health["active_strategies"]
        active_ratio = active_count / max(strategy_count, 1)
        if active_ratio >= 0.5:
            checks.append({"name": "活跃策略比例", "status": "pass",
                          "message": f"{active_count}/{strategy_count} ({active_ratio:.0%})"})
        elif active_ratio >= 0.3:
            checks.append({"name": "活跃策略比例", "status": "warn",
                          "message": f"仅{active_ratio:.0%}策略活跃"})
            warnings += 1
        else:
            checks.append({"name": "活跃策略比例", "status": "fail",
                          "message": f"大量策略休眠 ({active_ratio:.0%})"})
            criticals += 1

        # 检查3：休眠策略
        dormant_count = health["dormant_strategies"]
        dormant_ratio = dormant_count / max(strategy_count, 1)
        if dormant_count <= 3:
            checks.append({"name": "休眠策略数", "status": "pass",
                          "message": f"{dormant_count}个休眠"})
        elif dormant_ratio < 0.5:
            checks.append({"name": "休眠策略数", "status": "warn",
                          "message": f"{dormant_count}个休眠，偏高"})
            warnings += 1
        elif dormant_ratio < 0.8:
            checks.append({"name": "休眠策略数", "status": "warn",
                          "message": f"{dormant_count}个休眠({dormant_ratio:.0%})，需关注"})
            warnings += 1
        else:
            checks.append({"name": "休眠策略数", "status": "fail",
                          "message": f"{dormant_count}个休眠({dormant_ratio:.0%})，权重调度异常"})
            criticals += 1

        # 检查4：最近决策
        last_decision = health.get("last_decision")
        if last_decision:
            conf = last_decision.get("confidence", 0)
            if conf >= 0.5:
                checks.append({"name": "最近决策置信度", "status": "pass",
                              "message": f"置信度 {conf:.2f}"})
            else:
                checks.append({"name": "最近决策置信度", "status": "warn",
                              "message": f"置信度偏低 {conf:.2f}"})
                warnings += 1
        else:
            checks.append({"name": "最近决策", "status": "warn",
                          "message": "尚无决策记录"})
            warnings += 1

        # 检查5：评估/决策比
        evals = health["total_evaluations"]
        decisions = health["total_decisions"]
        if evals > 0:
            checks.append({"name": "评估引擎", "status": "pass",
                          "message": f"评估{evals}次, 决策{decisions}次"})
        else:
            checks.append({"name": "评估引擎", "status": "warn",
                          "message": "尚未运行评估"})
            warnings += 1

        # 综合状态
        if criticals > 0:
            overall = "critical"
        elif warnings > 2:
            overall = "warning"
        elif warnings > 0:
            overall = "warning"
        else:
            overall = "healthy"

        return {
            "status": overall,
            "module": "tau_cluster_engine",
            "version": "2.0",
            "checks": checks,
            "warnings": warnings,
            "criticals": criticals,
            "metrics": {
                "total_strategies": strategy_count,
                "active_strategies": active_count,
                "dormant_strategies": dormant_count,
                "total_evaluations": evals,
                "total_decisions": decisions,
                "market_regime": health["market_regime"],
            },
            "timestamp": datetime.datetime.now().isoformat(),
        }


# ================================================================
    # 12. 集群引擎作为优化目标（对接 EntropyTauOptimizer 五维搜索引擎）
    # ================================================================

    def evaluate_params(self, params: Dict[str, float],
                         rounds: int = 200, seed: int = 42) -> Any:
        """评估一组集群引擎参数，返回 EnhancedBacktestResult

        将集群引擎作为 EntropyTauOptimizer 的优化目标，
        使集群融合参数享受五维驱动搜索（E/V/H/M/P）。

        Args:
            params: 集群引擎参数 {min_resonance, consensus_threshold, action_threshold}
            rounds: 模拟评估轮数
            seed: 随机种子

        Returns:
            EnhancedBacktestResult: 包含 daily_returns/trade_returns/signal_sequence
        """
        from core.tau_enhanced_optimizer import EnhancedBacktestResult

        # 保存当前状态
        saved_state = {
            "min_resonance": self.min_resonance,
            "consensus_threshold": self.consensus_threshold,
            "action_threshold": self.action_threshold,
        }

        # 应用待评估参数
        self.apply_optimizer_result(params)

        # 模拟评估
        rnd = random.Random(seed)
        correct = wrong = hold = 0
        daily_returns = []
        trade_returns = []
        signal_sequence = []

        for i in range(rounds):
            true_signal = math.sin(i * 0.08) * 0.8
            if true_signal > 0.15:
                true_dir = 1
            elif true_signal < -0.15:
                true_dir = -1
            else:
                true_dir = 0

            price = 100.0 + true_signal * 3.0
            cd = self.evaluate({"price": price, "_true_signal": true_signal}, price)
            ca = 1 if cd.action == "BUY" else (-1 if cd.action == "SELL" else 0)
            signal_sequence.append(cd.direction)

            if ca == 0:
                hold += 1
                daily_returns.append(0.0)
            elif ca == true_dir and true_dir != 0:
                correct += 1
                ret = abs(true_signal) * 0.5
                daily_returns.append(ret)
                trade_returns.append(ret)
            elif ca != 0 and true_dir != 0:
                wrong += 1
                ret = -abs(true_signal) * 0.3
                daily_returns.append(ret)
                trade_returns.append(ret)
            else:
                wrong += 1
                daily_returns.append(-0.02)
                trade_returns.append(-0.02)

        total_trades = correct + wrong
        accuracy = correct / max(1, total_trades)

        if len(daily_returns) >= 2:
            daily_std = statistics.stdev(daily_returns)
            if daily_std > 0:
                sharpe = (statistics.mean(daily_returns) / daily_std) * math.sqrt(252)
            else:
                sharpe = 0.0
        else:
            sharpe = 0.0

        total_return = sum(daily_returns)
        max_dd = self._calc_max_drawdown(daily_returns)

        # 恢复原状态
        with self._lock:
            self.min_resonance = saved_state["min_resonance"]
            self.consensus_threshold = saved_state["consensus_threshold"]
            self.action_threshold = saved_state["action_threshold"]
            self.validator.min_resonance = self.min_resonance
            self.validator.consensus_threshold = self.consensus_threshold

        return EnhancedBacktestResult(
            strategy_name="tau_cluster_engine",
            params=params.copy(),
            total_return=total_return,
            sharpe_ratio=sharpe,
            max_drawdown=max_dd,
            win_rate=accuracy,
            total_trades=total_trades,
            daily_returns=daily_returns,
            trade_returns=trade_returns,
            signal_sequence=signal_sequence,
            confidence=1.0,
        )

    @staticmethod
    def _calc_max_drawdown(returns: List[float]) -> float:
        """从收益率序列计算最大回撤"""
        if not returns:
            return 0.0
        peak = returns[0]
        max_dd = 0.0
        cum = 0.0
        for r in returns:
            cum += r
            if cum > peak:
                peak = cum
            dd = (peak - cum) / max(abs(peak), 0.001)
            if dd > max_dd:
                max_dd = dd
        return max_dd


# ============================================================
# 8. ClusterEngineOptimizer — 熵韬收敛优化器 × 集群引擎
# ============================================================

class ClusterEngineOptimizer:
    """集群引擎专用优化器 — 将 TauClusterEngine 作为 EntropyTauOptimizer 的优化目标

    继承 EntropyTauOptimizer 的全部五维搜索能力：
      - 自适应粗筛（冷启动 + 在线反馈）
      - 分区域精搜（绿区×1.5, 黄区×0.7, 红区跳过）
      - 熵趋势收敛（实时监控，动态调整探索/开发平衡）
      - 硬约束过滤（极端参数直接排除）
      - Warm Start 继承 + 自动持久化

    与单个策略优化的区别：
      - 优化目标是集群融合参数（min_resonance, consensus_threshold, action_threshold）
      - 评估函数是集群引擎的模拟交易（而非单个策略回测）
      - 五维指标（E/V/H/M/P）从集群引擎的模拟交易中提取
    """

    def __init__(self, cluster_engine: TauClusterEngine,
                 rounds: int = 200, seed: int = 42,
                 warm_start: bool = True,
                 auto_persist: bool = True):
        """
        Args:
            cluster_engine: 已注册策略的 TauClusterEngine 实例
            rounds: 每轮评估的模拟交易轮数
            seed: 随机种子
            warm_start: 是否从历史最佳参数继承
            auto_persist: 是否自动持久化优化结果
        """
        self._cluster_engine = cluster_engine
        self._rounds = rounds
        self._seed = seed

        # 获取参数空间
        param_space = cluster_engine.to_optimizer_params()

        # 获取 Warm Start 参数（从历史最佳继承）
        warm_start_params = None
        if warm_start:
            try:
                history = cluster_engine.get_optimization_history()
                if history:
                    best = max(history, key=lambda h: h.get("score", -float("inf")))
                    warm_start_params = best.get("params", {})
                    if warm_start_params:
                        print(f"[ClusterEngineOptimizer] Warm Start: 继承历史最佳参数 "
                              f"v{best.get('version')}, score={best.get('score')}")
            except Exception:
                pass

        # 创建底层 EntropyTauOptimizer
        from core.tau_enhanced_optimizer import EntropyTauOptimizer
        self._optimizer = EntropyTauOptimizer(
            param_ranges=param_space,
            strategy_name="tau_cluster_engine",
            warm_start_params=warm_start_params,
            auto_persist=auto_persist,
        )

        # 替换 optimize 方法：将集群引擎评估包装为优化器可调用的格式
        self._optimizer.optimize = self._cluster_optimize

    def _cluster_optimize(self, params: Dict[str, float]) -> Tuple[Any, str]:
        """集群引擎参数评估 → 兼容 EntropyTauOptimizer.optimize() 接口"""
        result = self._cluster_engine.evaluate_params(params, self._rounds, self._seed)
        return result, "full"

    def run(self, coarse_points: int = 50,
            refined_points_per_region: int = 30,
            entropy_decay: bool = True,
            early_stop: bool = True) -> Dict[str, Any]:
        """运行五维驱动优化

        Args:
            coarse_points: 粗筛点数
            refined_points_per_region: 每区域精搜点数
            entropy_decay: 是否启用熵趋势收敛
            early_stop: 是否启用早停

        Returns:
            {success, best_params, best_score, optimization_result, ...}
        """
        print(f"\n{'='*60}")
        print(f"  ClusterEngineOptimizer: 五维驱动集群引擎参数优化")
        print(f"  参数空间: {self._cluster_engine.to_optimizer_params()}")
        print(f"  模拟轮数: {self._rounds}, 粗筛: {coarse_points}, 精搜: {refined_points_per_region}")
        print(f"{'='*60}")

        t0 = time.time()

        opt_result = self._optimizer.run_enhanced_optimization(
            coarse_points=coarse_points,
            refined_points_per_region=refined_points_per_region,
            entropy_decay=entropy_decay,
            early_stop=early_stop,
        )

        elapsed = time.time() - t0

        if opt_result.get("best_params") is not None:
            best_params = opt_result["best_params"]
            best_score = opt_result.get("best_score_original", 0)

            # 应用最佳参数到集群引擎
            self._cluster_engine.apply_optimizer_result(best_params, score=best_score)

            print(f"\n  ✅ 优化完成: {elapsed:.1f}s")
            print(f"  最佳参数: {best_params}")
            print(f"  最佳评分: {best_score:.4f}")
            print(f"  总评估: {opt_result.get('total_evaluations', '?')} 次")
            print(f"  五维评分: {opt_result.get('best_enhanced_score', {}).get('total_score', 'N/A')}")

            return {
                "success": True,
                "optimizer": "ClusterEngineOptimizer (EntropyTau × ClusterEngine)",
                "best_params": best_params,
                "best_score": round(best_score, 4),
                "total_evals": opt_result.get("total_evaluations", 0),
                "convergence": opt_result.get("convergence", {}),
                "elapsed_seconds": round(elapsed, 2),
                "optimization_result": opt_result,
            }
        else:
            return {
                "success": False,
                "error": opt_result.get("error", "优化失败"),
                "optimization_result": opt_result,
            }

    def get_convergence_metrics(self) -> Dict[str, Any]:
        """获取优化收敛指标"""
        return self._optimizer.get_convergence_metrics()


# ============================================================
# 9. 工厂函数
# ============================================================

# 全局单例
_cluster_engine: Optional[TauClusterEngine] = None


def get_cluster_engine(**kwargs) -> TauClusterEngine:
    """获取韬策略集群引擎单例"""
    global _cluster_engine
    if _cluster_engine is None:
        _cluster_engine = TauClusterEngine(**kwargs)
    return _cluster_engine


def create_cluster_engine(strategies: Dict[str, Any] = None, **kwargs) -> TauClusterEngine:
    """创建并初始化韬策略集群引擎

    Args:
        strategies: {name: strategy_instance} 策略实例字典
        **kwargs: 传递给 TauClusterEngine 的参数

    Returns:
        TauClusterEngine 实例
    """
    engine = TauClusterEngine(**kwargs)

    if strategies:
        for name, inst in strategies.items():
            strategy_type = "generic"
            # 自动识别策略类型
            name_lower = name.lower()
            if any(k in name_lower for k in ['gyro', '陀螺']):
                strategy_type = "gyro"
            elif any(k in name_lower for k in ['bernoulli', 'coanda', '伯努利']):
                strategy_type = "bernoulli"
            elif any(k in name_lower for k in ['fourier', '傅里叶']):
                strategy_type = "fourier"
            elif any(k in name_lower for k in ['shepherd', 'rotation', '轮动']):
                strategy_type = "shepherd"
            elif any(k in name_lower for k in ['grid', '网格']):
                strategy_type = "grid"
            elif any(k in name_lower for k in ['moving', '均线', 'trend', '趋势']):
                strategy_type = "trend"
            elif any(k in name_lower for k in ['ml', 'adaptive', 'ppo']):
                strategy_type = "ml"
            elif any(k in name_lower for k in ['rl', 'reinforce']):
                strategy_type = "rl"
            elif any(k in name_lower for k in ['fractal', 'chaos', '分形']):
                strategy_type = "physics"
            elif any(k in name_lower for k in ['fluid', '流体']):
                strategy_type = "physics"
            elif any(k in name_lower for k in ['quantum', '量子']):
                strategy_type = "physics"
            elif any(k in name_lower for k in ['value', '价值', 'huijin']):
                strategy_type = "value"
            elif any(k in name_lower for k in ['multifactor', 'resonance', '共振', '因子']):
                strategy_type = "multifactor"
            elif any(k in name_lower for k in ['dca', '定投', 'fund']):
                strategy_type = "fund"
            elif any(k in name_lower for k in ['down', 'defense', '防御', '下跌']):
                strategy_type = "defense"
            elif any(k in name_lower for k in ['ensemble', 'optimized', '综合', '融合']):
                strategy_type = "ensemble"

            adapter = StrategySignalAdapter(
                name=name,
                strategy_type=strategy_type,
                strategy_instance=inst,
            )
            engine.register_strategy(name, adapter)

    return engine