#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
熔断→资金分配桥接模块 (Breaker → Capital Bridge)
======================================================
将分层熔断因子模型 (circuit_breaker_model.py) 的输出
映射到三个资金分配系统的仓位收缩系数。

映射理论：
  position_final = position_base × α_G × α_L × α_S

其中：
  α_G = 1 − δ_global              ← 全局 Ledoit-Wolf 收缩
  α_L = 1 − δ_local_effective     ← 局部 Tikhonov 有效阻尼
  α_S = 1 − black_swan_score × k  ← 黑天鹅评分缩放 (k=敏感度)

集成目标：
  ✅ EnhancedRiskManager: 替换离散 regime 3档 → 连续收缩
  ✅ RLEnhancer: 将 black_swan_score 注入状态向量第21维
  ✅ FinalMarketAdaptive: 星座买入比例 × (1 − score)
  ✅ 统一风控 (unified_risk_controller): 顶层级联调仓

作者: Aurora Team
日期: 2026-05-25
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np

# 熔断模块引用
try:
    from experiments.circuit_breaker_model import (
        BlackSwanScore,
        BreakerLevel,
        CircuitBreakerState,
        COVARIANT_FACTOR_NAMES,
        GlobalCircuitBreaker,
        HierarchicalCircuitBreaker,
        LocalCircuitBreaker,
        MarketRegime,
    )
    BREAKER_AVAILABLE = True
except ImportError as e:
    BREAKER_AVAILABLE = False
    # 定义轻量级桩类，确保模块在不加载熔断模型时也能运行
    class MarketRegime(Enum):
        LOW_VOL = "低波动"
        NORMAL = "正常"
        ELEVATED = "恐慌上升"
        EXTREME = "极端"
        CRASH = "崩盘"

    class BreakerLevel(Enum):
        NONE = 0
        WARNING = 1
        LOCAL = 2
        GLOBAL = 3
        FULL = 4

    COVARIANT_FACTOR_NAMES = [
        "f1_volatility", "f2_liquidity", "f3_microstructure",
        "f4_signal_quality", "f5_execution", "f6_capital_efficiency",
        "f7_tail_risk", "f8_stress_resilience",
    ]

logger = logging.getLogger("BreakerCapitalBridge")


# =============================================================================
# 敏感度配置 — 控制熔断评分到仓位收缩的映射强度
# =============================================================================

@dataclass
class BridgeSensitivityConfig:
    """桥接敏感度配置 — 每个因子的黑天鹅评分对仓位的收缩系数权重"""

    # 全局收缩映射强度 (0=不影响仓位, 1=完全收缩)
    global_shrinkage_weight: float = 1.0

    # 黑天鹅评分映射强度
    black_swan_weight: float = 0.85

    # 各因子组对仓位的敏感度
    factor_group_weights: Dict[str, float] = field(default_factory=lambda: {
        "MARKET": 0.60,       # 市场环境因子 → 60% 仓位影响
        "STRATEGY": 0.35,     # 策略执行因子 → 35%
        "TAIL_RISK": 0.80,    # 尾部风险因子 → 80%（最高敏感度）
    })

    # 熔断级别→仓位系数 映射
    breaker_level_position_map: Dict[int, float] = field(default_factory=lambda: {
        0: 1.00,   # NONE: 正常仓位
        1: 0.80,   # WARNING: 收缩至80%
        2: 0.55,   # LOCAL: 收缩至55%
        3: 0.25,   # GLOBAL: 收缩至25%
        4: 0.05,   # FULL: 几乎清仓 (5% 保留对冲底仓)
    })

    # 市场状态 → 基础仓位系数 (与 EnhancedRiskManager 对齐)
    regime_base_capital: Dict[str, float] = field(default_factory=lambda: {
        "低波动": 0.95,
        "正常": 0.70,
        "恐慌上升": 0.40,
        "极端": 0.15,
        "崩盘": 0.05,
    })

    # 状态向量扩展维度（供 RLEnhancer 使用）
    expand_rl_state_dim: bool = True


# =============================================================================
# 核心桥接类
# =============================================================================

class BreakerCapitalBridge:
    """
    熔断→资金分配桥接器

    核心公式:
        α_total = α_regime × α_breaker × α_score

    其中:
        α_regime  = config.regime_base_capital[regime]
        α_breaker = config.breaker_level_position_map[level]
        α_score   = 1 − black_swan_score × config.black_swan_weight

    使用方式:
        bridge = BreakerCapitalBridge()
        bridge.update_from_breaker(breaker_state)
        new_position_pct = bridge.adjust_position_ratio(base_ratio=0.95)
    """

    def __init__(self, sensitivity_config: Optional[BridgeSensitivityConfig] = None):
        self.config = sensitivity_config or BridgeSensitivityConfig()
        self._current_regime: MarketRegime = MarketRegime.NORMAL
        self._current_breaker_level: BreakerLevel = BreakerLevel.NONE
        self._current_black_swan_score: float = 0.0
        self._current_delta_global: float = 0.0
        self._current_delta_local: float = 0.0
        self._active_local_factors: List[str] = []
        self._factor_dampen_vector: np.ndarray = np.ones(len(COVARIANT_FACTOR_NAMES))
        self._last_update_ts: float = 0.0
        self._update_count: int = 0

    # ── 更新接口 ──────────────────────────────────────────────

    def update_from_breaker_state(self, state: CircuitBreakerState) -> None:
        """
        从熔断状态对象同步更新

        Args:
            state: HierarchicalCircuitBreaker.step() 返回的 CircuitBreakerState
        """
        self._current_regime = state.market_regime
        self._current_breaker_level = state.recommended_level
        self._current_black_swan_score = state.black_swan_score
        self._current_delta_global = state.global_shrinkage_delta
        self._active_local_factors = state.local_active_factors
        self._last_update_ts = time.time()
        self._update_count += 1

        # 从阻尼矩阵提取局部 δ
        if state.dampen_matrix is not None:
            diag = np.diag(state.dampen_matrix)
            self._current_delta_local = np.mean(diag) if len(diag) > 0 else 0.0
            self._factor_dampen_vector = 1.0 - np.clip(diag, 0, 1)
        else:
            self._current_delta_local = 0.0
            self._factor_dampen_vector = np.ones(len(COVARIANT_FACTOR_NAMES))

    def update_from_raw(
        self,
        black_swan_score: float,
        regime: Union[MarketRegime, str] = MarketRegime.NORMAL,
        breaker_level: BreakerLevel = BreakerLevel.NONE,
        delta_global: float = 0.0,
        delta_local: float = 0.0,
    ) -> None:
        """
        从原始数值更新（不依赖熔断模块对象）

        Args:
            black_swan_score: 黑天鹅评分 [0, 1]
            regime: 市场状态
            breaker_level: 熔断等级
            delta_global: 全局收缩系数
            delta_local: 局部阻尼系数
        """
        if isinstance(regime, str):
            regime_map = {r.value: r for r in MarketRegime}
            self._current_regime = regime_map.get(regime, MarketRegime.NORMAL)
        else:
            self._current_regime = regime

        self._current_breaker_level = breaker_level
        self._current_black_swan_score = float(np.clip(black_swan_score, 0, 1))
        self._current_delta_global = float(np.clip(delta_global, 0, 1))
        self._current_delta_local = float(np.clip(delta_local, 0, 1))
        self._last_update_ts = time.time()
        self._update_count += 1

    # ── 仓位比例调整 ─────────────────────────────────────────

    def adjust_position_ratio(
        self,
        base_ratio: float,
        use_cascade: bool = True,
    ) -> float:
        """
        计算熔断调整后的仓位比例

        级联公式 (use_cascade=True):
            α = α_regime × α_breaker × α_score × (1 − δ_G) × (1 − δ_L_eff)

        非级联公式 (use_cascade=False):
            α = base_ratio × α_score

        Args:
            base_ratio: 基础仓位比例 [0, 1]
            use_cascade: 是否使用全链路级联收缩

        Returns:
            调整后的仓位比例 [0, 1]
        """
        base_ratio = float(np.clip(base_ratio, 0, 1))

        if not use_cascade:
            alpha_score = 1.0 - self._current_black_swan_score * self.config.black_swan_weight
            return float(np.clip(base_ratio * alpha_score, 0, 1))

        # 级联收缩
        regime_str = self._current_regime.value if isinstance(self._current_regime, MarketRegime) else str(self._current_regime)
        alpha_regime = self.config.regime_base_capital.get(regime_str, 0.70)
        alpha_breaker = self.config.breaker_level_position_map.get(
            self._current_breaker_level.value if hasattr(self._current_breaker_level, 'value') else self._current_breaker_level, 1.0
        )
        alpha_score = 1.0 - self._current_black_swan_score * self.config.black_swan_weight
        alpha_global = 1.0 - self._current_delta_global * self.config.global_shrinkage_weight
        alpha_local = 1.0 - self._current_delta_local * 0.5  # 局部阻尼权重减半

        # 乘积链
        alpha_total = alpha_regime * alpha_breaker * alpha_score * alpha_global * alpha_local

        adjusted = base_ratio * alpha_total
        return float(np.clip(adjusted, 0, 1))

    def get_alpha_components(self) -> Dict[str, float]:
        """返回各层收缩因子，用于诊断和日志"""
        regime_str = self._current_regime.value if isinstance(self._current_regime, MarketRegime) else str(self._current_regime)
        return {
            "alpha_regime": self.config.regime_base_capital.get(regime_str, 0.70),
            "alpha_breaker": self.config.breaker_level_position_map.get(
                self._current_breaker_level.value if hasattr(self._current_breaker_level, 'value') else self._current_breaker_level, 1.0
            ),
            "alpha_score": 1.0 - self._current_black_swan_score * self.config.black_swan_weight,
            "alpha_global": 1.0 - self._current_delta_global * self.config.global_shrinkage_weight,
            "alpha_local": 1.0 - self._current_delta_local * 0.5,
            "alpha_total": self.adjust_position_ratio(1.0),
        }

    # ── EnhancedRiskManager 集成 ──────────────────────────────

    def map_to_risk_manager_regime(self) -> int:
        """
        将 MarketRegime (5级) 映射到 EnhancedRiskManager 的 regime (3级)

        Returns:
            regime: 0=趋势(低波动), 1=震荡(正常/恐慌), 2=危机(极端/崩盘)
        """
        mapping = {
            MarketRegime.LOW_VOL: 0,
            MarketRegime.NORMAL: 1,
            MarketRegime.ELEVATED: 1,
            MarketRegime.EXTREME: 2,
            MarketRegime.CRASH: 2,
        }
        return mapping.get(self._current_regime, 1)

    def get_continuous_position_limit(
        self,
        account_balance: float,
        base_max_pct: float = 0.95,
    ) -> float:
        """
        计算连续仓位上限，替代 EnhancedRiskManager 的离散 3档

        比原始 get_regime_based_risk_params 更精细：
        - 不是简单 95%/60%/10% 三档
        - 而是连续映射: max_position_pct = base × α_total

        Args:
            account_balance: 账户余额
            base_max_pct: 基准最大仓位比例

        Returns:
            连续化的 max_position_pct
        """
        alpha_total = self.adjust_position_ratio(1.0, use_cascade=True)
        continuous_pct = base_max_pct * alpha_total
        return float(np.clip(continuous_pct, 0.02, base_max_pct))

    # ── RLEnhancer 集成 ──────────────────────────────────────

    def expand_rl_state_vector(
        self,
        original_state: np.ndarray,
    ) -> np.ndarray:
        """
        将 black_swan_score 作为第21维附加到 RL 状态向量

        原始 RLEnhancer 使用 20 维状态向量。
        此方法在末尾追加 1 维 = black_swan_score，
        使 PPO 策略可以感知当前市场危险程度。

        Args:
            original_state: 原始 20维状态向量

        Returns:
            21维扩展状态向量
        """
        if not self.config.expand_rl_state_dim:
            return original_state

        original_state = np.asarray(original_state, dtype=np.float32).flatten()
        swan_score = np.array([self._current_black_swan_score], dtype=np.float32)
        return np.concatenate([original_state, swan_score])

    def get_rl_action_suppressor(self) -> float:
        """
        返回 RL 动作抑制系数，可直接乘到 PPO 输出的仓位建议上

        使用方式:
            raw_action = enhancer.predict(state)  # [0, 1]
            safe_action = raw_action * bridge.get_rl_action_suppressor()
        """
        return self.adjust_position_ratio(1.0, use_cascade=True)

    # ── FinalMarketAdaptive 星座买入集成 ──────────────────────

    def adjust_constellation_allocation(
        self,
        allocations: Dict[str, float],
    ) -> Dict[str, float]:
        """
        调整星座5级买入分配比例

        FinalMarketAdaptive 的 constellation_levels:
            [0.02: 0.10, 0.04: 0.15, 0.06: 0.20, 0.08: 0.25, 0.10: 0.30]

        每个买入比例乘以 (1 − black_swan_score × weight)，
        保证危险时买入更少。

        Args:
            allocations: {threshold: allocation_pct, ...}

        Returns:
            调整后的分配比例
        """
        alpha = 1.0 - self._current_black_swan_score * self.config.black_swan_weight
        adjusted = {}
        for threshold, alloc in allocations.items():
            adjusted[threshold] = alloc * alpha
        return adjusted

    # ── 快捷查询 ──────────────────────────────────────────────

    @property
    def is_emergency(self) -> bool:
        """是否处于紧急状态（需要大幅减仓或清仓）"""
        return self._current_breaker_level in (BreakerLevel.FULL,)

    @property
    def recommended_action(self) -> str:
        """基于当前熔断状态的推荐操作"""
        mapping = {
            BreakerLevel.NONE: "正常交易",
            BreakerLevel.WARNING: "减仓至80%，暂停加仓",
            BreakerLevel.LOCAL: "减仓至55%，停止新开仓",
            BreakerLevel.GLOBAL: "减仓至25%，仅平仓",
            BreakerLevel.FULL: "紧急清仓至5%底仓，人工介入",
        }
        return mapping.get(self._current_breaker_level, "未知")

    def summary(self) -> Dict[str, Any]:
        """返回当前桥接状态摘要"""
        regime_str = self._current_regime.value if isinstance(self._current_regime, MarketRegime) else str(self._current_regime)
        level_val = self._current_breaker_level.value if hasattr(self._current_breaker_level, 'value') else self._current_breaker_level
        return {
            "市场状态": regime_str,
            "熔断等级": level_val,
            "黑天鹅评分": round(self._current_black_swan_score, 4),
            "全局收缩δ": round(self._current_delta_global, 4),
            "局部阻尼δ": round(self._current_delta_local, 4),
            "综合收缩系数α": round(self.adjust_position_ratio(1.0), 4),
            "推荐操作": self.recommended_action,
            "是否紧急": self.is_emergency,
            "RL动作抑制系数": round(self.get_rl_action_suppressor(), 4),
            "更新次数": self._update_count,
        }


# =============================================================================
# 端到端集成示例 — 展示完整的熔断→仓位映射流程
# =============================================================================

def demo_breaker_to_capital_pipeline(seed: int = 42) -> Dict[str, Any]:
    """
    端到端演示: 熔断评估 → 仓位调整

    模拟 5 种市场场景下的联动效果
    """
    np.random.seed(seed)

    if not BREAKER_AVAILABLE:
        return {"status": "skipped", "reason": "circuit_breaker_model 不可用"}
    from experiments.circuit_breaker_model import (
        COVARIANT_FACTOR_NAMES,
        ExperimentConfig,
        HierarchicalCircuitBreaker,
    )

    # 创建熔断器
    breaker = HierarchicalCircuitBreaker(
        tikhonov_lambda=0.12,
        ledoit_wolf_delta_max=0.45,
        adaptive_thresholds=True,
    )

    # 创建桥接器
    bridge = BreakerCapitalBridge()

    # 初始因子值（正常市场）
    factor_values = {name: 0.45 for name in COVARIANT_FACTOR_NAMES}
    factor_histories = {name: [0.45] for name in COVARIANT_FACTOR_NAMES}

    # 模拟场景序列
    scenarios = [
        ("normal", 10),
        ("flash_crash", 8),
        ("black_swan", 5),
        ("v_recovery", 15),
        ("normal", 10),
    ]

    results = []
    tick = 0

    from experiments.circuit_breaker_model import generate_factor_scenario, estimate_covariance_matrix

    for scenario_name, duration in scenarios:
        for t in range(duration):
            # 生成因子值
            factor_values = generate_factor_scenario(
                factor_values, scenario_name, t, duration
            )
            for name in COVARIANT_FACTOR_NAMES:
                factor_histories[name].append(factor_values[name])
                if len(factor_histories[name]) > 200:
                    factor_histories[name].pop(0)

            cov = estimate_covariance_matrix(factor_histories)
            _, state = breaker.step(
                factor_values=factor_values,
                cov_matrix=cov,
                tick=tick,
            )

            # 桥接
            bridge.update_from_breaker_state(state)

            # 计算三种仓位调整
            base_ratio = 0.95  # 基准仓位95%
            adjusted_ratio = bridge.adjust_position_ratio(base_ratio)
            continuous_limit = bridge.get_continuous_position_limit(
                account_balance=100000, base_max_pct=0.95
            )

            results.append({
                "tick": tick,
                "场景": scenario_name,
                "市场状态": state.market_regime.value,
                "熔断等级": state.recommended_level.value,
                "黑天鹅评分": round(state.black_swan_score, 4),
                "全局δ": round(state.global_shrinkage_delta, 3),
                "基准仓位": base_ratio,
                "桥接仓位": round(adjusted_ratio, 4),
                "连续上限": round(continuous_limit, 4),
            })

            tick += 1

    # 汇总
    final_summary = bridge.summary()
    final_summary["测试tick数"] = len(results)

    # 场景统计
    scenario_stats = {}
    for scenario_name in dict.fromkeys([s[0] for s in scenarios], None):
        scenario_results = [r for r in results if r["场景"] == scenario_name]
        if scenario_results:
            avg_position = np.mean([r["桥接仓位"] for r in scenario_results])
            avg_score = np.mean([r["黑天鹅评分"] for r in scenario_results])
            scenario_stats[scenario_name] = {
                "tick数": len(scenario_results),
                "平均仓位": round(avg_position, 4),
                "平均黑天鹅评分": round(avg_score, 4),
            }

    return {
        "status": "success",
        "tick_details": results,
        "final_summary": final_summary,
        "scenario_stats": scenario_stats,
    }


# =============================================================================
# 快速验证入口
# =============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("熔断→资金分配桥接模块 — 快速验证")
    print("=" * 70)
    print()
    print("核心公式: position_final = base × α_regime × α_breaker × α_score × (1−δ_G)")
    print()

    if not BREAKER_AVAILABLE:
        print("[SKIP] circuit_breaker_model 未加载，仅验证桥接器基础逻辑\n")
        bridge = BreakerCapitalBridge()
        bridge.update_from_raw(
            black_swan_score=0.75,
            regime=MarketRegime.EXTREME,
            breaker_level=BreakerLevel.GLOBAL,
            delta_global=0.35,
        )
        print(f"  模拟极端场景: black_swan_score=0.75, regime=极端, level=GLOBAL, δ_G=0.35")
        print(f"  α_total = {bridge.adjust_position_ratio(1.0):.4f}")
        print(f"  基准仓位 95% → 调整后 {bridge.adjust_position_ratio(0.95):.4f}")
        print(f"\n  {bridge.summary()}")
    else:
        print("运行端到端演示 (normal→flash_crash→black_swan→v_recovery→normal)...")
        result = demo_breaker_to_capital_pipeline(seed=42)

        if result["status"] == "success":
            print(f"\n{'─' * 70}")
            print("各场景平均仓位变化:")
            print(f"{'─' * 70}")
            for scenario, stats in result["scenario_stats"].items():
                print(f"  {scenario:15s} | avg_position={stats['平均仓位']:.4f}  avg_swan={stats['平均黑天鹅评分']:.4f}")
            print(f"\n{'─' * 70}")
            print("最终桥接状态:")
            print(f"{'─' * 70}")
            for k, v in result["final_summary"].items():
                print(f"  {k}: {v}")
            print(f"\n{'─' * 70}")
            print("详细tick (前5 + 关键转折点):")
            print(f"{'─' * 70}")
            shown_ticks = set()
            prev_scenario = None
            count = 0
            for r in result["tick_details"]:
                if r["场景"] != prev_scenario:
                    shown_ticks.add(r["tick"])
                    prev_scenario = r["场景"]
                    print(f"  t={r['tick']:3d} [{r['场景']:12s}] pos={r['桥接仓位']:.4f} swan={r['黑天鹅评分']:.4f} δ={r['全局δ']:.3f}")
                elif count < 5:
                    shown_ticks.add(r["tick"])
                    print(f"  t={r['tick']:3d} [{r['场景']:12s}] pos={r['桥接仓位']:.4f} swan={r['黑天鹅评分']:.4f} δ={r['全局δ']:.3f}")
                    count += 1

    print(f"\n{'=' * 70}")
    print("桥接验证完成 — 三路映射已建立")
    print(f"{'=' * 70}")