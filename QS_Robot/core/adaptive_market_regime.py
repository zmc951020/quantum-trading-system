#!/usr/bin/env python3
"""
AMTS 策略自适应引擎 — Strategy Adaptation Engine
==================================================

基于韬策略引擎和熵韬收敛优化器集群的自适应策略调度层。

核心设计理念：
  不以固定规则映射市场状态→策略类别，而是使用：
  1. 多维市场状态向量（趋势强度、波动率、冲击强度、动量方向、广度）
  2. 优化器集群回测论证的策略性能画像（每种市场条件下各策略的收敛效益）
  3. 实时收敛追踪（各策略在当前市场条件下的信号质量、方向一致性、胜率）
  4. 动态策略切换（基于收敛指标实时调整策略权重，支持休眠/唤醒）

与 TauClusterEngine 的集成方式：
  - 增强 EntropyWeightScheduler._regime_strategy_map（基于回测论证）
  - 提供市场状态向量给 EntropyWeightScheduler._apply_regime_bias()
  - 实时监控各策略收敛状态，触发衰减/恢复/重优化
  - 熔断保护作为最后一道风控防线

依赖: numpy, TauClusterEngine, 熵韬收敛优化器集群
"""

from __future__ import annotations

import math
import time
import json
import os
import logging
import threading
import statistics
from collections import deque, defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple, Callable

import numpy as np

logger = logging.getLogger(__name__)


# ============================================================
# 1. 多维市场状态向量
# ============================================================

@dataclass
class MarketStateVector:
    """多维市场状态 — 替代简单的 S0/S1/S2 三态分类"""
    trend_strength: float       # 趋势强度 (STR) [0, 5]
    volatility: float           # 价格波动率 [0, 0.1]
    impact_intensity: float     # 冲击强度 (Hawkes λ) [0, 5]
    momentum_bias: float        # 动量方向 [-1, 1]，正=上涨，负=下跌
    volume_ratio: float         # 量比（当前量/均量）[0, 3]
    regime_label: str           # 简化标签: "trending"|"ranging"|"volatile"|"bearish"
    confidence: float           # 状态置信度 [0, 1]
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trend_strength": round(self.trend_strength, 4),
            "volatility": round(self.volatility, 6),
            "impact_intensity": round(self.impact_intensity, 4),
            "momentum_bias": round(self.momentum_bias, 4),
            "volume_ratio": round(self.volume_ratio, 4),
            "regime_label": self.regime_label,
            "confidence": round(self.confidence, 4),
        }

    def to_vector(self) -> np.ndarray:
        """转换为特征向量，用于相似度计算"""
        return np.array([
            self.trend_strength,
            self.volatility * 100,
            self.impact_intensity,
            self.momentum_bias,
            self.volume_ratio,
        ])


# ============================================================
# 2. 多维市场状态检测器
# ============================================================

class MultiDimensionalRegimeDetector:
    """多维市场状态检测器 — 替代简单的 3 状态分类

    输出 MarketStateVector（5 维连续特征 + 1 个离散标签），
    用于策略性能画像的相似度匹配。
    """

    def __init__(self,
                 window: int = 60,
                 str_trend_threshold: float = 1.5,
                 str_chaos_threshold: float = 0.5,
                 volatility_chaos_threshold: float = 0.04,
                 confirmation_cycles: int = 3):
        self.window = window
        self.str_trend_threshold = str_trend_threshold
        self.str_chaos_threshold = str_chaos_threshold
        self.volatility_chaos_threshold = volatility_chaos_threshold
        self.confirmation_cycles = confirmation_cycles

        self._price_history: deque = deque(maxlen=window)
        self._volume_history: deque = deque(maxlen=window)
        self._state_history: deque = deque(maxlen=20)
        self._state_candidate: Optional[str] = None
        self._state_counter: int = 0
        self._lock = threading.RLock()

    def feed(self, price: float, volume: float = 0):
        self._price_history.append(price)
        if volume > 0:
            self._volume_history.append(volume)

    def detect(self) -> MarketStateVector:
        with self._lock:
            prices = list(self._price_history)
            if len(prices) < 5:
                return MarketStateVector(
                    trend_strength=1.0, volatility=0.01, impact_intensity=0.5,
                    momentum_bias=0.0, volume_ratio=1.0,
                    regime_label="ranging", confidence=0.3,
                )

            n = len(prices)

            # 1. 趋势强度 STR（累积收益 / 去趋势波动率）
            total_return = math.log(prices[-1] / prices[0]) if prices[0] > 0 else 0
            x = np.arange(n)
            y = np.array(prices)
            slope, _ = np.polyfit(x, y, 1)
            detrended = y - (slope * x + np.mean(y) - slope * np.mean(x))
            price_vol = float(np.std(detrended))
            normalized_vol = price_vol / (prices[0] + 1e-8)
            str_val = abs(total_return) / (normalized_vol * math.sqrt(n) + 1e-8)
            trend_strength = max(0.1, min(5.0, str_val * 3.0))

            # 2. 波动率
            returns = [prices[i] / prices[i - 1] - 1 for i in range(1, n)]
            volatility = statistics.stdev(returns) if len(returns) >= 2 else 0.01

            # 3. 冲击强度（成交量变异 × 价格跳变）
            volumes = list(self._volume_history) if self._volume_history else [1000] * n
            avg_vol = statistics.mean(volumes)
            std_vol = statistics.stdev(volumes) if len(volumes) >= 2 else 1
            vol_cv = std_vol / (avg_vol + 1)
            price_jumps = [abs(returns[i]) for i in range(len(returns))]
            avg_jump = statistics.mean(price_jumps) if price_jumps else 0
            impact = vol_cv * 0.4 + avg_jump * 100 * 0.6
            impact_intensity = max(0.1, min(5.0, impact * 2.0))

            # 4. 动量方向
            momentum_bias = float(np.tanh(total_return * 5))

            # 5. 量比
            recent_vol = statistics.mean(volumes[-10:]) if len(volumes) >= 10 else avg_vol
            hist_vol = statistics.mean(volumes[:-10]) if len(volumes) >= 20 else avg_vol
            volume_ratio = min(3.0, max(0.1, recent_vol / (hist_vol + 1)))

            # 6. 离散标签（用于 TauClusterEngine 兼容）
            regime_label = self._classify_label(trend_strength, volatility, momentum_bias)

            # 7. 置信度
            confidence = self._calc_confidence(trend_strength, volatility, regime_label)

            return MarketStateVector(
                trend_strength=trend_strength,
                volatility=volatility,
                impact_intensity=impact_intensity,
                momentum_bias=momentum_bias,
                volume_ratio=volume_ratio,
                regime_label=regime_label,
                confidence=confidence,
            )

    def _classify_label(self, trend: float, vol: float, momentum: float) -> str:
        if vol > self.volatility_chaos_threshold:
            return "volatile"
        if momentum < -0.3:
            return "bearish"
        if trend > self.str_trend_threshold:
            return "trending"
        return "ranging"

    def _calc_confidence(self, trend: float, vol: float, label: str) -> float:
        if label == "trending":
            return min(1.0, max(0.4, (trend - self.str_trend_threshold) / 2.0))
        elif label == "volatile":
            return min(1.0, max(0.5, vol / self.volatility_chaos_threshold))
        elif label == "bearish":
            return min(1.0, max(0.4, abs(vol) * 20))
        else:
            center = 1.0
            return min(1.0, max(0.3, 1.0 - abs(trend - center) / 1.5))

    def reset(self):
        self._price_history.clear()
        self._volume_history.clear()
        self._state_history.clear()


# ============================================================
# 3. 策略性能画像（回测论证驱动）
# ============================================================

@dataclass
class StrategyPerformanceProfile:
    """单个策略在特定市场条件下的性能画像

    由优化器集群回测生成，每条记录对应一次回测结果。
    """
    strategy_name: str
    strategy_category: str      # Trend/Grid/RL/Value/MultiFactor/...
    market_vector: List[float]  # 5维市场状态向量
    sharpe: float
    max_drawdown: float
    win_rate: float
    total_return: float
    convergence_score: float    # 熵韬收敛评分（综合）
    backtest_date: str
    sample_count: int = 1       # 回测样本数（用于加权）


class StrategyProfileStore:
    """策略性能画像存储 — 持久化回测论证结果

    用于：
      1. 根据当前市场状态查找最匹配的策略
      2. 向 EntropyWeightScheduler 提供 regime_strategy_map
    """

    def __init__(self, storage_path: str = None):
        self._profiles: Dict[str, List[StrategyPerformanceProfile]] = defaultdict(list)
        self._storage_path = storage_path or os.path.join(
            os.path.dirname(__file__), "..", "data", "strategy_profiles.json"
        )
        self._lock = threading.RLock()
        self._load()

    def add_profile(self, profile: StrategyPerformanceProfile):
        with self._lock:
            self._profiles[profile.strategy_name].append(profile)
            self._save()

    def get_best_strategies(self, market_vector: MarketStateVector,
                            top_n: int = 5) -> List[Tuple[str, float]]:
        """根据当前市场状态，返回收敛评分最高的 N 个策略"""
        with self._lock:
            target = market_vector.to_vector()
            scored = []

            for name, profiles in self._profiles.items():
                if not profiles:
                    continue
                # 计算与目标市场状态的相似度 + 收敛评分
                best_score = 0.0
                for p in profiles:
                    src = np.array(p.market_vector)
                    similarity = 1.0 / (1.0 + float(np.linalg.norm(target - src)))
                    combined = p.convergence_score * 0.6 + similarity * 0.4
                    if combined > best_score:
                        best_score = combined
                scored.append((name, best_score))

            scored.sort(key=lambda x: -x[1])
            return scored[:top_n]

    def get_regime_priorities(self) -> Dict[str, List[str]]:
        """生成 regime → 优先策略列表（用于 EntropyWeightScheduler）

        按市场状态标签聚合各策略的收敛评分，排序输出。
        """
        with self._lock:
            # 按 regime_label 聚合
            regime_scores: Dict[str, Dict[str, float]] = defaultdict(dict)

            for name, profiles in self._profiles.items():
                for p in profiles:
                    # 根据 market_vector 推断 regime_label
                    vector = np.array(p.market_vector)
                    trend = vector[0]
                    vol = vector[1] / 100
                    momentum = vector[3]

                    if vol > 0.04:
                        label = "volatile"
                    elif momentum < -0.3:
                        label = "bearish"
                    elif trend > 1.5:
                        label = "trending"
                    else:
                        label = "ranging"

                    current = regime_scores[label].get(name, 0)
                    regime_scores[label][name] = max(current, p.convergence_score)

            # 排序输出
            result = {}
            for label, scores in regime_scores.items():
                sorted_names = [n for n, _ in sorted(scores.items(), key=lambda x: -x[1])]
                result[label] = sorted_names[:5]  # 每个 regime 最多 5 个优先策略

            return result

    def _save(self):
        try:
            os.makedirs(os.path.dirname(self._storage_path), exist_ok=True)
            data = {}
            for name, profiles in self._profiles.items():
                data[name] = [
                    {
                        "strategy_category": p.strategy_category,
                        "market_vector": p.market_vector,
                        "sharpe": p.sharpe,
                        "max_drawdown": p.max_drawdown,
                        "win_rate": p.win_rate,
                        "total_return": p.total_return,
                        "convergence_score": p.convergence_score,
                        "backtest_date": p.backtest_date,
                        "sample_count": p.sample_count,
                    }
                    for p in profiles
                ]
            with open(self._storage_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"[ProfileStore] 保存失败: {e}")

    def _load(self):
        try:
            if os.path.exists(self._storage_path):
                with open(self._storage_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for name, profiles in data.items():
                    for p in profiles:
                        self._profiles[name].append(StrategyPerformanceProfile(
                            strategy_name=name,
                            strategy_category=p.get("strategy_category", "Unknown"),
                            market_vector=p["market_vector"],
                            sharpe=p.get("sharpe", 0),
                            max_drawdown=p.get("max_drawdown", 0),
                            win_rate=p.get("win_rate", 0),
                            total_return=p.get("total_return", 0),
                            convergence_score=p.get("convergence_score", 0),
                            backtest_date=p.get("backtest_date", ""),
                            sample_count=p.get("sample_count", 1),
                        ))
                logger.info(f"[ProfileStore] 已加载 {sum(len(v) for v in self._profiles.values())} 条策略画像")
        except Exception as e:
            logger.warning(f"[ProfileStore] 加载失败: {e}")


# ============================================================
# 4. 实时收敛追踪器
# ============================================================

class ConvergenceTracker:
    """实时收敛追踪器 — 监控各策略在当前市场条件下的信号质量

    追踪维度：
      - 方向一致性（连续同向信号次数）
      - 置信度趋势（上升/下降）
      - 虚拟胜率（信号方向与实际价格走势的匹配度）
      - 收敛衰减检测（信号质量持续下降 → 触发重优化）
    """

    def __init__(self, window: int = 30, decay_threshold: int = 10):
        self.window = window
        self.decay_threshold = decay_threshold

        # 每策略追踪
        self._direction_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=window))
        self._confidence_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=window))
        self._virtual_pnl: Dict[str, List[float]] = defaultdict(list)
        self._decay_counters: Dict[str, int] = defaultdict(int)
        self._price_history: deque = deque(maxlen=window)

        self._lock = threading.RLock()

    def feed_price(self, price: float):
        self._price_history.append(price)

    def record_signal(self, strategy_name: str, direction: float, confidence: float):
        with self._lock:
            self._direction_history[strategy_name].append(direction)
            self._confidence_history[strategy_name].append(confidence)

            # 虚拟胜率：信号方向 vs 价格方向
            if len(self._price_history) >= 2:
                price_dir = 1 if self._price_history[-1] > self._price_history[-2] else -1
                signal_dir = 1 if direction > 0 else (-1 if direction < 0 else 0)
                if signal_dir != 0 and price_dir != 0:
                    self._virtual_pnl[strategy_name].append(1 if signal_dir == price_dir else 0)

            # 信号质量衰减检测
            if len(self._confidence_history[strategy_name]) >= 5:
                recent = list(self._confidence_history[strategy_name])[-5:]
                if statistics.mean(recent) < 0.3:
                    self._decay_counters[strategy_name] += 1
                else:
                    self._decay_counters[strategy_name] = 0

    def get_convergence_score(self, strategy_name: str) -> float:
        """获取策略的收敛评分 [0, 1]"""
        with self._lock:
            # 1. 方向一致性
            dirs = list(self._direction_history[strategy_name])
            if len(dirs) < 5:
                return 0.5

            dir_consistency = abs(sum(1 if d > 0 else (-1 if d < 0 else 0) for d in dirs[-10:])) / max(1, len(dirs[-10:]))

            # 2. 置信度均值
            confs = list(self._confidence_history[strategy_name])
            avg_conf = statistics.mean(confs[-10:]) if confs[-10:] else 0.5

            # 3. 虚拟胜率
            pnl = self._virtual_pnl.get(strategy_name, [])
            win_rate = statistics.mean(pnl[-20:]) if pnl[-20:] else 0.5

            return dir_consistency * 0.3 + avg_conf * 0.35 + win_rate * 0.35

    def is_decaying(self, strategy_name: str) -> bool:
        with self._lock:
            return self._decay_counters.get(strategy_name, 0) >= self.decay_threshold

    def get_decaying_strategies(self) -> List[str]:
        with self._lock:
            return [n for n, c in self._decay_counters.items() if c >= self.decay_threshold]

    def reset(self):
        with self._lock:
            self._direction_history.clear()
            self._confidence_history.clear()
            self._virtual_pnl.clear()
            self._decay_counters.clear()
            self._price_history.clear()


# ============================================================
# 5. 策略自适应引擎（主类）
# ============================================================

class StrategyAdaptationEngine:
    """策略自适应引擎 — 基于韬策略引擎和熵韬收敛优化器集群的自适应调度

    核心流程：
      1. 检测多维市场状态
      2. 查询策略性能画像 → 确定当前最优策略组合
      3. 更新 TauClusterEngine 的 EntropyWeightScheduler 权重偏置
      4. 实时追踪各策略收敛状态 → 衰减/恢复/触发重优化
      5. 熔断保护

    用法:
        engine = TauClusterEngine()
        adapter = StrategyAdaptationEngine(tau_engine=engine, optimizer=optimizer)
        adapter.feed(price, volume)

        # 在 TauClusterEngine.evaluate() 之前
        adapter.apply_adaptation()  # 更新权重偏置

        # 在 TauClusterEngine.evaluate() 之后
        decision = engine.get_last_decision()
        decision = adapter.adjust_decision(decision)
    """

    def __init__(self,
                 tau_engine: Any = None,
                 optimizer: Any = None,       # 熵韬收敛优化器集群
                 integration_bus: Any = None,  # 集成总线
                 window: int = 60):
        self.tau_engine = tau_engine
        self.optimizer = optimizer
        self.integration_bus = integration_bus

        # 子模块
        self.detector = MultiDimensionalRegimeDetector(window=window)
        self.profile_store = StrategyProfileStore()
        self.tracker = ConvergenceTracker(window=window // 2)

        # 状态
        self._current_state: Optional[MarketStateVector] = None
        self._circuit_breaker: bool = False
        self._circuit_breaker_reason: str = ""
        self._daily_drawdown: float = 0.0
        self._day_start_equity: float = 0.0
        self._lock = threading.RLock()

        # 回调
        self._on_regime_change: List[Callable] = []
        self._on_decay_detected: List[Callable] = []

    def feed(self, price: float, volume: float = 0):
        self.detector.feed(price, volume)
        self.tracker.feed_price(price)

    def detect(self) -> MarketStateVector:
        self._current_state = self.detector.detect()

        # 概念漂移检测（市场状态显著变化时触发回调）
        if hasattr(self, '_last_label') and self._last_label != self._current_state.regime_label:
            for cb in self._on_regime_change:
                try:
                    cb(self._current_state)
                except Exception:
                    pass
        self._last_label = self._current_state.regime_label

        return self._current_state

    def apply_adaptation(self):
        """在 TauClusterEngine.evaluate() 之前调用，更新策略权重偏置

        1. 从画像存储获取当前市场状态下的最优策略组合
        2. 注入到 EntropyWeightScheduler._regime_strategy_map
        3. 同时考虑实时收敛追踪结果
        """
        if self.tau_engine is None:
            return

        state = self._current_state or self.detect()
        scheduler = getattr(self.tau_engine, 'weight_scheduler', None)
        if scheduler is None:
            return

        # 1. 从画像存储获取优先策略
        profile_priorities = self.profile_store.get_regime_priorities()
        for regime, strategies in profile_priorities.items():
            scheduler.set_regime_priorities(regime, strategies)

        # 2. 叠加实时收敛追踪结果
        # 收敛评分高的策略额外提权，衰减策略降权
        decaying = self.tracker.get_decaying_strategies()
        for name in decaying:
            scheduler.set_regime_priorities(
                state.regime_label,
                [s for s in profile_priorities.get(state.regime_label, [])
                 if s != name]
            )
            logger.info(f"[Adaptation] 策略 {name} 收敛衰减，已从优先列表移除")

    def record_signal(self, strategy_name: str, direction: float, confidence: float):
        """记录策略信号（在 TauClusterEngine 输出信号后调用）"""
        self.tracker.record_signal(strategy_name, direction, confidence)

        # 衰减检测 → 触发回调
        if self.tracker.is_decaying(strategy_name):
            for cb in self._on_decay_detected:
                try:
                    cb(strategy_name)
                except Exception:
                    pass

    def adjust_decision(self, decision: Any) -> Any:
        """调整集群决策 — 叠加仓位管理和熔断保护"""
        state = self._current_state or self.detect()

        with self._lock:
            # 1. 仓位计算：基于市场状态
            if state.regime_label == "trending":
                base_position = 0.6 + state.confidence * 0.2
            elif state.regime_label == "ranging":
                base_position = 0.2 + state.confidence * 0.1
            elif state.regime_label == "volatile":
                base_position = 0.05 + state.confidence * 0.05
            elif state.regime_label == "bearish":
                base_position = 0.0 + state.confidence * 0.1
            else:
                base_position = 0.2

            decision.position_ratio *= base_position

            # 2. 混乱/熔断 → 强制降仓
            if state.regime_label == "volatile" and state.volatility > 0.05:
                decision.position_ratio = min(decision.position_ratio, 0.10)
                if hasattr(decision, 'direction'):
                    decision.direction *= 0.3

            if self._circuit_breaker:
                decision.position_ratio = 0
                if hasattr(decision, 'direction'):
                    decision.direction = 0

            # 3. 日回撤保护
            if self._daily_drawdown > 0.03:
                decision.position_ratio *= 0.5
            if self._daily_drawdown > 0.05:
                decision.position_ratio = 0

            return decision

    def trigger_circuit_breaker(self, reason: str = ""):
        self._circuit_breaker = True
        self._circuit_breaker_reason = reason
        logger.warning(f"[Adaptation] 熔断触发: {reason}")

    def release_circuit_breaker(self):
        self._circuit_breaker = False
        self._circuit_breaker_reason = ""
        logger.info("[Adaptation] 熔断释放")

    def update_pnl(self, current_equity: float):
        with self._lock:
            if self._day_start_equity == 0:
                self._day_start_equity = current_equity
            pnl = current_equity - self._day_start_equity
            if self._day_start_equity > 0:
                self._daily_drawdown = max(0, -pnl / self._day_start_equity)

    def reset_daily(self):
        self._day_start_equity = 0
        self._daily_drawdown = 0

    def on_regime_change(self, callback: Callable):
        self._on_regime_change.append(callback)

    def on_decay_detected(self, callback: Callable):
        self._on_decay_detected.append(callback)

    def get_health_report(self) -> Dict[str, Any]:
        state = self._current_state
        return {
            "market_state": state.to_dict() if state else {},
            "circuit_breaker": self._circuit_breaker,
            "daily_drawdown": round(self._daily_drawdown, 4),
            "convergence": {
                name: round(self.tracker.get_convergence_score(name), 4)
                for name in list(self.tracker._direction_history.keys())[:20]
            },
            "decaying": self.tracker.get_decaying_strategies(),
        }

    def reset(self):
        self.detector.reset()
        self.tracker.reset()
        self._current_state = None
        self._circuit_breaker = False


# ============================================================
# 6. 回测画像构建器（使用优化器集群）
# ============================================================

class BacktestProfileBuilder:
    """回测画像构建器 — 使用熵韬收敛优化器集群进行策略回测论证

    对每个策略，在不同市场条件下运行回测，生成 StrategyPerformanceProfile，
    存入 StrategyProfileStore，供自适应引擎查询。

    用法:
        builder = BacktestProfileBuilder(optimizer, integration_bus)
        builder.build_profiles(strategy_names=["策略A", "策略B"], stock_pool=[...])
    """

    def __init__(self,
                 optimizer: Any = None,
                 integration_bus: Any = None,
                 profile_store: StrategyProfileStore = None):
        self.optimizer = optimizer
        self.integration_bus = integration_bus
        self.profile_store = profile_store or StrategyProfileStore()

    def build_profiles(self,
                       strategy_names: List[str],
                       stock_pool: List[str] = None,
                       market_periods: int = 3) -> List[StrategyPerformanceProfile]:
        """为指定策略构建性能画像

        Args:
            strategy_names: 策略名称列表
            stock_pool: 股票池（用于回测）
            market_periods: 划分的市场时间段数（模拟不同市场状态）

        Returns:
            生成的性能画像列表
        """
        profiles = []

        for strategy_name in strategy_names:
            logger.info(f"[ProfileBuilder] 构建策略画像: {strategy_name}")

            try:
                if self.integration_bus:
                    # 使用集成总线的完整优化流程
                    result = self.integration_bus.auto_optimize_strategy(
                        strategy_name,
                        use_warm_start=True,
                    )
                    if result.get("success"):
                        profile = self._result_to_profile(strategy_name, result)
                        profiles.append(profile)
                        self.profile_store.add_profile(profile)
                else:
                    # 降级：使用默认画像
                    profile = self._create_default_profile(strategy_name)
                    profiles.append(profile)
                    self.profile_store.add_profile(profile)
            except Exception as e:
                logger.error(f"[ProfileBuilder] {strategy_name} 画像构建失败: {e}")

        logger.info(f"[ProfileBuilder] 完成 {len(profiles)} 个策略画像")
        return profiles

    def _result_to_profile(self, strategy_name: str,
                           result: Dict[str, Any]) -> StrategyPerformanceProfile:
        """将优化结果转换为性能画像"""
        best_score = result.get("best_score", 0)
        sharpe = result.get("sharpe", best_score * 0.5)
        drawdown = result.get("max_drawdown", 0.15)
        win_rate = result.get("win_rate", 0.5)
        total_return = result.get("total_return", 0.1)

        # 收敛评分：综合 sharpe、回撤、胜率
        convergence = (
            min(1.0, sharpe / 3.0) * 0.4 +
            (1.0 - min(1.0, drawdown)) * 0.3 +
            win_rate * 0.3
        )

        # 市场状态向量（从优化结果推断）
        market_env = result.get("market_env", {})
        market_vector = [
            market_env.get("trend_strength", 1.0),
            market_env.get("volatility", 0.02) * 100,
            market_env.get("impact", 0.5),
            market_env.get("momentum", 0.0),
            market_env.get("volume_ratio", 1.0),
        ]

        return StrategyPerformanceProfile(
            strategy_name=strategy_name,
            strategy_category=self._detect_category(strategy_name),
            market_vector=market_vector,
            sharpe=sharpe,
            max_drawdown=drawdown,
            win_rate=win_rate,
            total_return=total_return,
            convergence_score=convergence,
            backtest_date=time.strftime("%Y-%m-%d"),
        )

    def _create_default_profile(self, strategy_name: str) -> StrategyPerformanceProfile:
        """创建默认画像（无优化器时使用）"""
        return StrategyPerformanceProfile(
            strategy_name=strategy_name,
            strategy_category=self._detect_category(strategy_name),
            market_vector=[1.0, 2.0, 0.5, 0.0, 1.0],
            sharpe=1.0,
            max_drawdown=0.15,
            win_rate=0.5,
            total_return=0.1,
            convergence_score=0.5,
            backtest_date=time.strftime("%Y-%m-%d"),
        )

    def _detect_category(self, name: str) -> str:
        name_lower = name.lower()
        keywords = {
            "Trend": ["trend", "movingaverage", "ma", "均线", "趋势"],
            "Grid": ["grid", "网格"],
            "RL": ["rl", "ppo", "fourier", "傅里叶", "强化学习"],
            "Value": ["value", "huijin", "汇金", "价值"],
            "MultiFactor": ["multifactor", "resonance", "多因子", "共振"],
            "Gyro": ["gyro", "陀螺仪", "陀螺"],
            "Bernoulli": ["bernoulli", "coanda", "伯努利", "康达"],
            "Shepherd": ["shepherd", "rotation", "轮动", "标的"],
            "Defense": ["defense", "down", "防御", "下跌"],
            "特种兵": ["special_forces", "wyckoff", "威科夫"],
        }
        for cat, kws in keywords.items():
            if any(kw in name_lower for kw in kws):
                return cat
        return "Unknown"


# ============================================================
# 7. 全局单例
# ============================================================

_adaptation_engine: Optional[StrategyAdaptationEngine] = None
_singleton_lock = threading.Lock()


def get_adaptation_engine(
    tau_engine: Any = None,
    optimizer: Any = None,
    integration_bus: Any = None,
) -> StrategyAdaptationEngine:
    global _adaptation_engine
    if _adaptation_engine is None:
        with _singleton_lock:
            if _adaptation_engine is None:
                _adaptation_engine = StrategyAdaptationEngine(
                    tau_engine=tau_engine,
                    optimizer=optimizer,
                    integration_bus=integration_bus,
                )
    return _adaptation_engine


# ============================================================
# 8. 向后兼容：保留旧接口
# ============================================================

class AdaptiveMarketRegime:
    """向后兼容的旧接口包装"""

    def __init__(self, window: int = 60, **kwargs):
        self._detector = MultiDimensionalRegimeDetector(window=window)

    def feed(self, price: float, volume: float = 0):
        self._detector.feed(price, volume)

    def detect(self):
        state = self._detector.detect()
        # 返回兼容的 MarketRegime 对象
        from dataclasses import dataclass
        @dataclass
        class CompatRegime:
            state: str
            confidence: float
            str_ratio: float
            volatility: float
            hawkes_intensity: float
            suggested_position: float
            suggested_mode: str
            def to_dict(self):
                return {
                    "state": self.state, "confidence": self.confidence,
                    "str_ratio": self.str_ratio, "volatility": self.volatility,
                    "hawkes_intensity": self.hawkes_intensity,
                    "suggested_position": self.suggested_position,
                    "suggested_mode": self.suggested_mode,
                }

        mode_map = {"trending": "momentum", "ranging": "mean_reversion",
                    "volatile": "risk_off", "bearish": "risk_off"}
        pos_map = {"trending": 0.7, "ranging": 0.25, "volatile": 0.05, "bearish": 0.05}

        return CompatRegime(
            state=f"{state.regime_label}",
            confidence=state.confidence,
            str_ratio=state.trend_strength,
            volatility=state.volatility,
            hawkes_intensity=state.impact_intensity,
            suggested_position=pos_map.get(state.regime_label, 0.2),
            suggested_mode=mode_map.get(state.regime_label, "mean_reversion"),
        )

    def get_regime_weights_bias(self) -> Dict[str, float]:
        return {}

    def get_health_report(self) -> Dict[str, Any]:
        return {"note": "legacy wrapper"}

    def reset(self):
        self._detector.reset()

    def trigger_circuit_breaker(self, reason: str = ""):
        pass

    def release_circuit_breaker(self):
        pass


class AdaptiveRegimeBridge:
    """向后兼容的旧桥接器"""

    def __init__(self, tau_engine: Any = None, window: int = 60):
        self.regime_detector = AdaptiveMarketRegime(window=window)
        self.tau_engine = tau_engine
        self._daily_drawdown = 0.0
        self._lock = threading.RLock()

    def feed(self, price: float, volume: float = 0):
        self.regime_detector.feed(price, volume)

    def get_regime(self):
        return self.regime_detector.detect()

    def get_weights_bias(self) -> Dict[str, float]:
        return self.regime_detector.get_regime_weights_bias()

    def adjust_decision(self, decision: Any, regime: Any) -> Any:
        decision.position_ratio *= regime.suggested_position
        return decision

    def update_pnl(self, current_equity: float):
        pass

    def reset_daily(self):
        pass

    def get_health_report(self) -> Dict[str, Any]:
        return {}


def get_adaptive_regime(window: int = 60) -> AdaptiveMarketRegime:
    return AdaptiveMarketRegime(window=window)


def get_adaptive_bridge(tau_engine: Any = None) -> AdaptiveRegimeBridge:
    return AdaptiveRegimeBridge(tau_engine=tau_engine)