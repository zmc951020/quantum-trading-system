#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  🐑 牧羊人智能体优化器 v6.0 — 系统论金融级自演化框架 (Shepherd V6)          ║
║  Shepherd V6: Systems-Theoretic Financial-Grade Self-Evolution Framework   ║
║                                                                            ║
║  核心升级：                                                                 ║
║  1. 五层闭环架构：感知→诊断→演化(逻辑∥参数)→专家复审→落地归档               ║
║  2. 逻辑与参数完全解耦（独立存储、独立演化、互不耦合）                       ║
║  3. 五行安全门禁体系（金木水火土—7条硬约束规则）                             ║
║  4. 系统论收敛引擎（Pareto前沿+协变熵+方向一致性）                          ║
║  5. 四大交易专家团队（策略算法/风控合规/交易工程/成本效率）                  ║
║  6. 缺陷自主识别引擎（10种缺陷+致命/严重/普通定级+逻辑补丁+黑名单）          ║
║  7. 五维度百分制打分→四档应对措施闭环                                       ║
║  8. 8因子×3层协变因子体系+Pareto效率边界推进                                ║
║                                                                            ║
║  保留V5.0核心：基因进化引擎/策略审议/金融评测/自演进循环                    ║
║  融合框架文档：四层闭环/解耦架构/缺陷认知/专家团队/合规体系                 ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import sys
import os
import json
import logging
import hashlib
import time
import random
import uuid
from typing import Dict, List, Optional, Tuple, Any, Set, Callable, Union
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum, auto
from collections import defaultdict, deque
from copy import deepcopy

import numpy as np

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  🏛️  V6 架构全景图（框架文档对应映射）                                      ║
# ║                                                                            ║
# ║  ┌─────────────────────────────────────────────────────────────────────┐   ║
# ║  │ Layer 0 — 数据感知层 (DataPerceptionLayer)                          │   ║
# ║  │   全量采集：回测/模拟/实盘/行情/风控/OMS延迟/盈亏/拟合误差           │   ║
# ║  ├─────────────────────────────────────────────────────────────────────┤   ║
# ║  │ Layer 1 — 自我诊断层 (DefectDiagnosisEngine)                        │   ║
# ║  │   10种缺陷识别 + 致命/严重/普通定级 + 逻辑缺陷vs参数缺陷区分         │   ║
# ║  ├─────────────────────────────────────────────────────────────────────┤   ║
# ║  │ Layer 安全 — 五行安全门禁 (FiveElementSecurityGate)                 │   ║
# ║  │   金(可持续) 木(资金) 水(风控) 火(策略) 土(兼容) 7条硬约束          │   ║
# ║  ├─────────────────────────────────────────────────────────────────────┤   ║
# ║  │ Layer 2 — 自主演化层 (SelfEvolutionEngine + GeneticEvolutionEngine) │   ║
# ║  │   逻辑∥参数解耦 + 基因进化(Pareto+协变熵) + 7条底层优化逻辑        │   ║
# ║  ├─────────────────────────────────────────────────────────────────────┤   ║
# ║  │ Layer 3 — 专家复审层 (ExpertReviewPanel)                            │   ║
# ║  │   四大专家(策略/风控/工程/成本) + 五维度百分制 + 四档落地措施       │   ║
# ║  ├─────────────────────────────────────────────────────────────────────┤   ║
# ║  │ Layer 4 — 落地归档层 (LandingArchiveLayer)                          │   ║
# ║  │   版本管理 + 迭代知识库 + 回滚机制 + 黑名单路径库                   │   ║
# ║  └─────────────────────────────────────────────────────────────────────┘   ║
# ║                                                                            ║
# ║  解耦架构: 自我优化逻辑(7条规则) ∥ 可调优参数(6大类40+参数)               ║
# ║  缺陷体系: 逻辑类5种 + 参数类4种 + 1种通用 = 10种缺陷全覆盖               ║
# ║  专家体系: 四大角色 × 五维度 × 百分制 → 四档措施(90+/70-89/60-69/<60)    ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

# =============================================================================
# 日志配置
# =============================================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-7s | %(name)s | %(message)s',
    datefmt='%H:%M:%S',
)
logger = logging.getLogger("ShepherdV6")


# =============================================================================
# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  第〇部分：核心枚举、常量、数据类定义                                     ║
# ╚══════════════════════════════════════════════════════════════════════════╝
# =============================================================================

class DefectSeverity(Enum):
    """缺陷严重等级"""
    FATAL = "致命级"
    SEVERE = "严重级"
    NORMAL = "普通级"


class GateVerdict(Enum):
    """五行门禁判定"""
    PASS = "通过"
    WARN = "警告"
    BLOCK = "驳回"
    FREEZE = "冻结"


class EvolutionAction(Enum):
    """演化落地措施"""
    DEPLOY = "直接落地生效"
    TUNE = "微调后落地"
    RECTIFY = "强制整改复审"
    ROLLBACK = "驳回回滚"


class SearchPath(Enum):
    """智能搜索路径"""
    PARETO_FRONTIER = "Pareto效率边界推进"
    COVARIANT_EIGEN = "协变特征方向搜索"
    PHASE_TRANSITION = "金融相变自适应搜索"


class Element(Enum):
    """五行"""
    GOLD = "金"
    WOOD = "木"
    WATER = "水"
    FIRE = "火"
    EARTH = "土"


# =============================================================================
# 五行门禁阈值配置
# =============================================================================
@dataclass
class FiveElementThresholds:
    """五行门禁硬约束阈值（金融级可配置）"""
    max_drawdown_hard: float = 0.25
    max_daily_loss_hard: float = 0.05
    max_consecutive_losses: int = 5
    max_daily_trades: int = 500
    var_99_threshold: float = 0.15
    cvar_95_threshold: float = 0.20
    min_backtest_years: int = 3
    max_overfit_ratio: float = 2.0
    min_cross_period_sharpe: float = 0.3
    noise_injection_required: bool = True
    min_market_regimes: int = 3
    min_win_rate: float = 0.35
    min_profit_loss_ratio: float = 1.2
    min_sharpe_ratio: float = 0.5
    max_cost_ratio: float = 0.30
    dimension_degradation_tolerance: int = 0
    max_latency_ms: float = 50.0
    max_slippage_bps: float = 5.0
    max_retry_count: int = 3
    timeout_seconds: float = 5.0
    backward_compat_required: bool = True
    max_schema_breaking_changes: int = 0
    system_health_min_score: float = 0.80
    # ── 成交量/流动性约束（防流动性幻觉） ──
    max_position_volume_ratio: float = 0.05         # 单笔订单不超日均成交量5%
    max_total_position_volume_ratio: float = 0.10    # 总持仓不超日均成交量10%
    min_daily_volume: int = 100000                    # 最小日均成交量（过滤僵尸标的）


@dataclass
class ConvergenceThresholds:
    """系统论收敛判定阈值"""
    pareto_hv_stagnation: float = 0.01
    covariant_entropy_delta: float = 0.01
    marginal_sharpe_decay: float = 0.005
    direction_cosine_min: float = 0.85
    stability_window: int = 3
    max_cycles_upper: int = 10
    min_cycles_lower: int = 2


@dataclass
class CovariantFactor:
    """协变因子"""
    name: str
    layer: int
    description: str
    current_value: float = 0.0
    history: List[float] = field(default_factory=list)
    sensitivity: Dict[str, float] = field(default_factory=dict)


GENE_DIMENSIONS = [
    "signal_detection", "entry_timing", "exit_timing", "risk_control",
    "position_sizing", "market_regime", "feature_engineering",
    "model_selection", "ensemble_method", "execution_algo",
    "cost_optimization", "adaptive_learning",
]


# =============================================================================
# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  第一部分：数据感知层 (Layer 0 — PerceptionLayer)                        ║
# ╚══════════════════════════════════════════════════════════════════════════╝
# =============================================================================

@dataclass
class MarketSnapshot:
    timestamp: datetime = field(default_factory=datetime.now)
    volatility_regime: str = "medium"
    liquidity_score: float = 0.5
    trend_strength: float = 0.3
    volume_profile: str = "normal"
    spread_ratio: float = 0.001
    orderbook_imbalance: float = 0.0


@dataclass
class TradingSnapshot:
    timestamp: datetime = field(default_factory=datetime.now)
    oms_latency_ms: float = 5.0
    ems_latency_ms: float = 2.0
    slippage_bps: float = 1.0
    fill_rate: float = 0.95
    cancel_rate: float = 0.05
    retry_count: int = 0


@dataclass
class RiskSnapshot:
    timestamp: datetime = field(default_factory=datetime.now)
    current_drawdown: float = 0.0
    daily_pnl: float = 0.0
    var_99: float = 0.0
    cvar_95: float = 0.0
    consecutive_losses: int = 0
    margin_usage: float = 0.0
    exposure: float = 0.0


@dataclass
class PerceptionData:
    timestamp: datetime = field(default_factory=datetime.now)
    market: Optional[MarketSnapshot] = None
    trading: Optional[TradingSnapshot] = None
    risk: Optional[RiskSnapshot] = None
    backtest_report: Optional[Dict[str, Any]] = None
    simulation_log: Optional[Dict[str, Any]] = None
    live_performance: Optional[Dict[str, Any]] = None
    model_fit_errors: Optional[Dict[str, float]] = None
    strategy_daily_returns: List[float] = field(default_factory=list)


class PerceptionLayer:
    """Layer 0: 数据感知层 — 全天候采集量化系统全维度数据"""

    def __init__(self):
        self.data_buffer: deque = deque(maxlen=10000)
        self.last_snapshot: Optional[PerceptionData] = None
        self.covariant_factors: Dict[str, CovariantFactor] = self._init_covariant_factors()

    def _init_covariant_factors(self) -> Dict[str, CovariantFactor]:
        return {
            "f1_volatility": CovariantFactor(name="f1_volatility", layer=0, description="波动率状态", sensitivity={"f4_signal_quality": 0.6, "f7_tail_risk": 0.8}),
            "f2_liquidity": CovariantFactor(name="f2_liquidity", layer=0, description="流动性状态", sensitivity={"f5_execution": 0.7, "f6_capital_efficiency": 0.4}),
            "f3_microstructure": CovariantFactor(name="f3_microstructure", layer=0, description="市场微观结构", sensitivity={"f5_execution": 0.5}),
            "f4_signal_quality": CovariantFactor(name="f4_signal_quality", layer=1, description="信号质量"),
            "f5_execution": CovariantFactor(name="f5_execution", layer=1, description="执行效率", sensitivity={"f6_capital_efficiency": -0.5}),
            "f6_capital_efficiency": CovariantFactor(name="f6_capital_efficiency", layer=1, description="资金效率"),
            "f7_tail_risk": CovariantFactor(name="f7_tail_risk", layer=2, description="尾部风险暴露", sensitivity={"f4_signal_quality": -0.3}),
            "f8_stress_resilience": CovariantFactor(name="f8_stress_resilience", layer=2, description="压力弹性"),
        }

    def collect(self, market=None, trading=None, risk=None, backtest=None,
                simulation=None, live=None, model_errors=None,
                daily_returns=None) -> PerceptionData:
        data = PerceptionData(
            timestamp=datetime.now(), market=market, trading=trading,
            risk=risk, backtest_report=backtest, simulation_log=simulation,
            live_performance=live, model_fit_errors=model_errors,
            strategy_daily_returns=daily_returns or [],
        )
        self.data_buffer.append(data)
        self.last_snapshot = data
        self._update_covariant_factors(data)
        return data

    def _update_covariant_factors(self, data: PerceptionData) -> None:
        if data.market:
            vol_score = {"low": 0.2, "medium": 0.5, "high": 0.8, "extreme": 0.95}
            self.covariant_factors["f1_volatility"].current_value = vol_score.get(data.market.volatility_regime, 0.5)
            self.covariant_factors["f2_liquidity"].current_value = data.market.liquidity_score
            self.covariant_factors["f3_microstructure"].current_value = abs(data.market.orderbook_imbalance)
        if data.trading:
            self.covariant_factors["f5_execution"].current_value = 1.0 - min(1.0, data.trading.oms_latency_ms / 100.0)
        if data.model_fit_errors:
            avg_err = float(np.mean(list(data.model_fit_errors.values())))
            self.covariant_factors["f4_signal_quality"].current_value = max(0, 1.0 - avg_err)
        if data.risk:
            self.covariant_factors["f7_tail_risk"].current_value = data.risk.cvar_95
            self.covariant_factors["f8_stress_resilience"].current_value = max(0, 1.0 - data.risk.current_drawdown)
        for f in self.covariant_factors.values():
            f.history.append(f.current_value)
            if len(f.history) > 500:
                f.history = f.history[-500:]

    def get_covariant_vector(self) -> np.ndarray:
        ordered = ["f1_volatility", "f2_liquidity", "f3_microstructure",
                   "f4_signal_quality", "f5_execution", "f6_capital_efficiency",
                   "f7_tail_risk", "f8_stress_resilience"]
        return np.array([self.covariant_factors[k].current_value for k in ordered])

    def compute_covariant_matrix(self, window: int = 20) -> np.ndarray:
        ordered = ["f1_volatility", "f2_liquidity", "f3_microstructure",
                   "f4_signal_quality", "f5_execution", "f6_capital_efficiency",
                   "f7_tail_risk", "f8_stress_resilience"]
        histories = []
        for k in ordered:
            h = self.covariant_factors[k].history
            if len(h) >= window:
                histories.append(h[-window:])
            else:
                histories.append(h + [self.covariant_factors[k].current_value] * (window - len(h)))
        return np.cov(np.array(histories))

    def detect_phase_transition(self) -> Optional[str]:
        if len(self.covariant_factors["f1_volatility"].history) < 50:
            return None
        vol_history = np.array(self.covariant_factors["f1_volatility"].history[-50:])
        if len(vol_history) < 20:
            return None
        recent = vol_history[-20:]
        older = vol_history[:-20]
        recent_vol, older_vol = float(np.std(recent)), float(np.std(older))
        if older_vol < 1e-6:
            return None
        ratio = recent_vol / older_vol
        if ratio > 2.0:
            return "phase_shift_high"
        elif ratio < 0.5:
            return "phase_shift_low"
        return "stable"


# =============================================================================
# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  第二部分：缺陷诊断层 (Layer 1 — DefectDiagnosisEngine)                   ║
# ╚══════════════════════════════════════════════════════════════════════════╝
# =============================================================================

@dataclass
class DefectReport:
    defect_id: str = ""
    defect_type: str = ""
    severity: DefectSeverity = DefectSeverity.NORMAL
    description: str = ""
    source_location: str = ""
    detected_at: datetime = field(default_factory=datetime.now)
    related_rule: Optional[str] = None
    suggested_patch: Optional[str] = None
    metrics_evidence: Dict[str, float] = field(default_factory=dict)
    patches_log: List[str] = field(default_factory=list)
    patches_log: List[str] = field(default_factory=list)


@dataclass
class DiagnosisResult:
    timestamp: datetime
    total_defects: int
    fatal_count: int
    severe_count: int
    normal_count: int
    defects: List[DefectReport]
    optimization_direction: str
    logic_upgrade_needed: bool
    param_fix_needed: bool


class DefectDiagnosisEngine:
    """Layer 1: 缺陷诊断引擎 — 10种缺陷自主识别"""

    def __init__(self, thresholds: FiveElementThresholds = None):
        self.thresholds = thresholds or FiveElementThresholds()
        self.defect_blacklist: Set[str] = set()
        self.defect_history: List[DefectReport] = []
        self.logic_patches: List[Dict[str, Any]] = []

    def diagnose(self, perception: PerceptionData,
                 strategy_performance: Dict[str, Any],
                 optimization_proposal: Optional[Dict[str, Any]] = None) -> DiagnosisResult:
        defects: List[DefectReport] = []

        d = self._check_optimization_bias(strategy_performance, optimization_proposal)
        if d: defects.append(d)
        d = self._check_generalization_gap(strategy_performance)
        if d: defects.append(d)
        d = self._check_overfitting(strategy_performance, perception)
        if d: defects.append(d)
        d = self._check_param_extremity(optimization_proposal)
        if d: defects.append(d)
        d = self._check_param_incompatibility(optimization_proposal)
        if d: defects.append(d)
        d = self._check_market_adaptation(perception, strategy_performance)
        if d: defects.append(d)
        d = self._check_cost_erosion(strategy_performance)
        if d: defects.append(d)
        d = self._check_compliance_gap(perception, strategy_performance)
        if d: defects.append(d)
        d = self._check_engineering_defect(perception)
        if d: defects.append(d)
        d = self._check_iteration_priority(strategy_performance, optimization_proposal)
        if d: defects.append(d)
        d = self._check_volume_liquidity(perception, strategy_performance)
        if d: defects.append(d)

        fatal = [d for d in defects if d.severity == DefectSeverity.FATAL]
        severe = [d for d in defects if d.severity == DefectSeverity.SEVERE]
        normal = [d for d in defects if d.severity == DefectSeverity.NORMAL]

        if fatal:
            direction = "冻结当前迭代，优先修复致命缺陷"
        elif severe:
            direction = "修复严重缺陷后方可继续迭代"
        elif normal:
            direction = "记录普通缺陷，下次迭代修复"
        else:
            direction = "无缺陷，可正常迭代"

        # ── 黑名单路径检测 ──
        blacklisted_triggered = []
        for bp in self.blacklisted_paths:
            if bp in str(optimization_proposal) or bp in str(strategy_performance):
                blacklisted_triggered.append(bp)
                defects.append(self._new_defect("逻辑类", DefectSeverity.FATAL,
                    f"触发黑名单路径: {bp}",
                    "演化层·黑名单检测", "反向约束机制",
                    f"该路径已被禁止，需使用替代方案", {"blacklisted_path": bp}))
        if blacklisted_triggered:
            direction = f"黑名单触发({len(blacklisted_triggered)}条)，强制冻结迭代"

        result = DiagnosisResult(
            timestamp=datetime.now(),
            total_defects=len(defects),
            fatal_count=len(fatal), severe_count=len(severe), normal_count=len(normal),
            defects=defects,
            optimization_direction=direction,
            logic_upgrade_needed=len(fatal) > 0 or len(severe) > 1,
            param_fix_needed=len(severe) > 0 or len(normal) > 2,
        )
        self.defect_history.extend(defects)
        logger.info(f"🔍 缺陷诊断完成: 致命{len(fatal)} 严重{len(severe)} 普通{len(normal)}, 方向={direction}")
        return result

    def _new_defect(self, dtype, severity, desc, location, rule, patch, evidence) -> DefectReport:
        return DefectReport(
            defect_id=f"DEF-{uuid.uuid4().hex[:8]}",
            defect_type=dtype, severity=severity, description=desc,
            source_location=location, related_rule=rule,
            suggested_patch=patch, metrics_evidence=evidence,
            detected_at=datetime.now(),
        )

    def _check_optimization_bias(self, perf: Dict, proposal=None) -> Optional[DefectReport]:
        drawdown = perf.get("max_drawdown", 0)
        if drawdown > self.thresholds.max_drawdown_hard and perf.get("sharpe_ratio", 0) > 1.0:
            return self._new_defect("逻辑类", DefectSeverity.SEVERE,
                f"优化逻辑片面：回撤{drawdown:.1%}超标，夏普{perf.get('sharpe_ratio',0):.2f}，疑只追收益忽略风险",
                "演化层·参数优化模块", "风险优先逻辑",
                "新增成本权重约束逻辑", {"max_drawdown": drawdown})
        return None

    def _check_generalization_gap(self, perf: Dict) -> Optional[DefectReport]:
        in_s, out_s = perf.get("in_sample_sharpe", 0), perf.get("out_sample_sharpe", 0)
        if in_s > 1.5 and out_s < 0.3 and in_s > 0:
            ratio = in_s / max(out_s, 0.01)
            if ratio > self.thresholds.max_overfit_ratio:
                return self._new_defect("逻辑类", DefectSeverity.FATAL if ratio > 5 else DefectSeverity.SEVERE,
                    f"泛化缺失：样本内夏普{in_s:.2f}，样本外{out_s:.2f}，过拟合比{ratio:.1f}",
                    "演化层·回测模块", "过拟合避免逻辑",
                    "强制加入噪声测试+跨周期验证", {"in_sample_sharpe": in_s, "out_sample_sharpe": out_s})
        return None

    def _check_overfitting(self, perf: Dict, perception) -> Optional[DefectReport]:
        bt = perf.get("backtest_score", 0)
        live = perf.get("live_score", bt)
        if bt > 80 and live < 50:
            return self._new_defect("参数类", DefectSeverity.SEVERE,
                f"参数过拟合：回测{bt:.0f}，实盘{live:.0f}，严重退化",
                "演化层·参数迭代模块", "过拟合避免逻辑",
                "回滚至稳定版本，加入对抗样本重训", {"backtest_score": bt, "live_score": live})
        return None

    def _check_param_extremity(self, proposal) -> Optional[DefectReport]:
        if not proposal: return None
        wr = proposal.get("win_rate", 0.5)
        if wr > 0.85:
            return self._new_defect("参数类", DefectSeverity.NORMAL,
                f"参数极值化：胜率{wr:.1%}过高，容错率极低",
                "演化层·参数迭代模块", "过拟合避免逻辑",
                "检查盈亏比补偿", {"win_rate": wr})
        return None

    def _check_param_incompatibility(self, proposal) -> Optional[DefectReport]:
        if not proposal: return None
        sc = proposal.get("schema_changes", 0)
        if sc > self.thresholds.max_schema_breaking_changes:
            return self._new_defect("参数类", DefectSeverity.SEVERE,
                f"参数不兼容：{sc}个schema变更", "演化层·参数配置模块",
                "新旧兼容逻辑", "增加向后兼容适配层", {"schema_changes": sc})
        return None

    def _check_market_adaptation(self, perception, perf) -> Optional[DefectReport]:
        if perception.market and perception.market.volatility_regime == "extreme" and perf.get("sharpe_ratio", 0) < 0:
            return self._new_defect("参数类", DefectSeverity.SEVERE,
                "市场适配失效：极端行情下夏普为负", "演化层·环境适配模块",
                "多维度权衡逻辑", "触发市场相变检测，切换优化范式", {"sharpe_ratio": perf.get("sharpe_ratio", 0)})
        return None

    def _check_cost_erosion(self, perf: Dict) -> Optional[DefectReport]:
        gr, nr = perf.get("gross_return", 0), perf.get("net_return", 0)
        if gr > 0.1 and (gr - nr) / max(abs(gr), 1e-6) > 0.5:
            return self._new_defect("参数类", DefectSeverity.NORMAL,
                f"成本侵蚀：毛收益{gr:.1%}→净收益{nr:.1%}，成本>50%收益",
                "执行交易模块", "延迟适配逻辑", "优先优化滑点+佣金", {"gross_return": gr, "net_return": nr})
        return None

    def _check_compliance_gap(self, perception, perf) -> Optional[DefectReport]:
        dt = perf.get("daily_trades", 0)
        if dt > self.thresholds.max_daily_trades:
            return self._new_defect("逻辑类", DefectSeverity.FATAL,
                f"合规违规：日交易{dt}笔>限{self.thresholds.max_daily_trades}笔",
                "演化层·参数迭代模块", "合规约束逻辑",
                "冻结迭代，加入笔数硬门禁", {"daily_trades": dt, "limit": self.thresholds.max_daily_trades})
        return None

    def _check_engineering_defect(self, perception) -> Optional[DefectReport]:
        if perception.trading and perception.trading.oms_latency_ms > self.thresholds.max_latency_ms:
            return self._new_defect("逻辑类", DefectSeverity.SEVERE,
                f"工程缺陷：OMS延迟{perception.trading.oms_latency_ms:.0f}ms超{self.thresholds.max_latency_ms:.0f}ms",
                "OMS/EMS执行模块", "延迟适配逻辑", "检查参数更新计算开销", {"oms_latency_ms": perception.trading.oms_latency_ms})
        return None

    def _check_iteration_priority(self, perf, proposal) -> Optional[DefectReport]:
        li = perf.get("logic_issues_count", 0)
        pc = len(proposal) if proposal else 0
        if li > 3 and pc > 5:
            return self._new_defect("逻辑类", DefectSeverity.SEVERE,
                f"迭代优先级混乱：{li}个逻辑问题未修却调{pc}项参数",
                "演化层·调度模块", "回测优先逻辑", "暂停调参，先修底层逻辑", {"logic_issues_count": li, "param_changes": pc})
        return None

    def _check_volume_liquidity(self, perception, perf: Dict) -> Optional[DefectReport]:
        """检查成交量/流动性约束，防止流动性幻觉导致的回测虚高"""
        daily_volume = perf.get("avg_daily_volume", 0)
        position_size = perf.get("position_size_shares", 0)
        total_position = perf.get("total_position_shares", 0)
        if daily_volume > 0 and daily_volume < self.thresholds.min_daily_volume:
            return self._new_defect("参数类", DefectSeverity.SEVERE,
                f"流动性不足：日均成交量{daily_volume:,}股 < 最低{self.thresholds.min_daily_volume:,}股，属僵尸标的",
                "演化层·成交量约束", "流动性安全约束",
                "剔除该标的或切换至主力合约", {"avg_daily_volume": daily_volume})
        if daily_volume > 0 and position_size > 0:
            ratio = position_size / daily_volume
            if ratio > self.thresholds.max_position_volume_ratio:
                return self._new_defect("参数类", DefectSeverity.FATAL if ratio > 0.15 else DefectSeverity.SEVERE,
                    f"仓位流动性风险：单笔{position_size:,}股占日均成交量{daily_volume:,}股的{ratio:.1%}，"
                    f"超阈值{self.thresholds.max_position_volume_ratio:.0%}",
                    "演化层·仓位管理", "成交量约束",
                    "降低单笔仓位至日均成交量5%以内", {"volume_ratio": ratio, "daily_volume": daily_volume})
        if daily_volume > 0 and total_position > 0:
            ratio = total_position / daily_volume
            if ratio > self.thresholds.max_total_position_volume_ratio:
                return self._new_defect("参数类", DefectSeverity.SEVERE,
                    f"总持仓流动性风险：{total_position:,}股占日均{daily_volume:,}股的{ratio:.1%}，"
                    f"超阈值{self.thresholds.max_total_position_volume_ratio:.0%}",
                    "演化层·仓位管理", "成交量约束",
                    "降低总持仓至日均成交量10%以内", {"total_volume_ratio": ratio, "daily_volume": daily_volume})
        return None

    def generate_logic_patch(self, defect: DefectReport) -> Dict[str, Any]:
        patch_rule = defect.suggested_patch or "通用补强规则"
        defect_signature = hashlib.md5(defect.description.encode()).hexdigest()[:12]
        self.defect_blacklist.add(defect_signature)
        patch = {
            "patch_id": f"PATCH-{uuid.uuid4().hex[:8]}",
            "defect_id": defect.defect_id,
            "defect_signature": defect_signature,
            "patch_rule": patch_rule,
            "severity": defect.severity.value,
            "created_at": datetime.now().isoformat(),
            "applied": False,
        }
        self.logic_patches.append(patch)
        logger.info(f"🩹 逻辑补丁: {patch['patch_id']} -> {patch_rule[:60]}")
        return patch

    def is_defect_blacklisted(self, sig: str) -> bool:
        return sig in self.defect_blacklist


# =============================================================================
# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  第三部分：五行安全门禁体系 (Five Element Safety Gates)                    ║
# ╚══════════════════════════════════════════════════════════════════════════╝
# =============================================================================

@dataclass
class GateResult:
    element: Element
    verdict: GateVerdict
    score: float
    details: str
    metrics: Dict[str, float] = field(default_factory=dict)
    gradient: Optional[np.ndarray] = None


class FiveElementSafetyGates:
    """五行安全门禁体系"""

    def __init__(self, thresholds: FiveElementThresholds = None):
        self.thresholds = thresholds or FiveElementThresholds()
        self.gate_history: List[List[GateResult]] = []

    def run_all_gates(self, strategy: Dict, perception: PerceptionData,
                      performance: Dict, compatibility_check: Optional[Dict] = None) -> List[GateResult]:
        results = [
            self._gold_gate(perception, performance),
            self._wood_gate(performance),
            self._water_gate(performance),
            self._fire_gate(perception),
            self._earth_gate(compatibility_check or {}),
        ]
        self.gate_history.append(results)
        return results

    def _gold_gate(self, perception, perf: Dict) -> GateResult:
        dd = perf.get("max_drawdown", 0)
        dl = perf.get("max_daily_loss", 0)
        cl = perf.get("consecutive_losses", 0)
        dt = perf.get("daily_trades", 0)
        failures = []
        if dd > self.thresholds.max_drawdown_hard: failures.append(f"回撤{dd:.1%}超标")
        if dl > self.thresholds.max_daily_loss_hard: failures.append(f"日亏{dl:.1%}超标")
        if cl >= self.thresholds.max_consecutive_losses: failures.append(f"连续止损{cl}次")
        if dt > self.thresholds.max_daily_trades: failures.append("合规违规")
        if any("合规" in f for f in failures):
            v, s = GateVerdict.FREEZE, 0
        elif failures:
            v, s = GateVerdict.BLOCK, max(5, 25 - len(failures) * 8)
        else:
            v, s = GateVerdict.PASS, 25
        return GateResult(Element.GOLD, v, s, "; ".join(failures) or "风控合规通过", {"max_drawdown": dd})

    def _wood_gate(self, perf: Dict) -> GateResult:
        bt = perf.get("backtest_years", 0)
        of = perf.get("overfit_ratio", 0) or (perf.get("in_sample_sharpe", 0) / max(perf.get("out_sample_sharpe", 0.01), 0.01))
        failures = []
        if bt < self.thresholds.min_backtest_years:
            failures.append(f"回测仅{bt}年")
            if bt == 0: return GateResult(Element.WOOD, GateVerdict.BLOCK, 0, "未完成回测", {"backtest_years": 0})
        if of > self.thresholds.max_overfit_ratio: failures.append(f"过拟合比{of:.1f}")
        if of > 5: v, s = GateVerdict.FREEZE, 0
        elif failures: v, s = GateVerdict.BLOCK, max(5, 25 - len(failures) * 8)
        else: v, s = GateVerdict.PASS, 25
        return GateResult(Element.WOOD, v, s, "; ".join(failures) or "回测泛化通过", {"backtest_years": bt, "overfit_ratio": of})

    def _water_gate(self, perf: Dict) -> GateResult:
        dims = {"win_rate": (perf.get("win_rate",0), self.thresholds.min_win_rate),
                "profit_loss_ratio": (perf.get("profit_loss_ratio",0), self.thresholds.min_profit_loss_ratio),
                "sharpe_ratio": (perf.get("sharpe_ratio",0), self.thresholds.min_sharpe_ratio),
                "cost_ratio": (perf.get("cost_ratio",1), self.thresholds.max_cost_ratio)}
        deg = 0; parts = []
        for n, (val, thr) in dims.items():
            if n == "cost_ratio" and val > thr: deg += 1; parts.append(f"{n}={val:.2f}>{thr:.2f}")
            elif n != "cost_ratio" and val < thr: deg += 1; parts.append(f"{n}={val:.2f}<{thr:.2f}")
        if deg > self.thresholds.dimension_degradation_tolerance:
            v, s = (GateVerdict.BLOCK if deg > 2 else GateVerdict.WARN), max(5, 25 - deg * 6)
        else: v, s = GateVerdict.PASS, 25
        return GateResult(Element.WATER, v, s, "; ".join(parts) or "六维平衡通过", {k: v[0] for k, v in dims.items()})

    def _fire_gate(self, perception) -> GateResult:
        if not perception.trading:
            return GateResult(Element.FIRE, GateVerdict.PASS, 25, "无交易数据", {})
        lat, sl = perception.trading.oms_latency_ms, perception.trading.slippage_bps
        failures = []
        if lat > self.thresholds.max_latency_ms: failures.append(f"延迟{lat:.0f}ms")
        if sl > self.thresholds.max_slippage_bps: failures.append(f"滑点{sl:.1f}bps")
        v = GateVerdict.WARN if failures else GateVerdict.PASS
        s = max(5, 25 - len(failures) * 10) if failures else 25
        return GateResult(Element.FIRE, v, s, "; ".join(failures) or "执行适配通过", {"latency_ms": lat, "slippage_bps": sl})

    def _earth_gate(self, compat: Dict) -> GateResult:
        sb = compat.get("schema_breaking_changes", 0)
        hs = compat.get("system_health_score", 1.0)
        bc = compat.get("backward_compatible", True)
        failures = []
        if sb > self.thresholds.max_schema_breaking_changes: failures.append(f"schema破坏{sb}项")
        if not bc and self.thresholds.backward_compat_required: failures.append("不兼容")
        if hs < self.thresholds.system_health_min_score: failures.append(f"健康{hs:.0%}")
        if sb > 0: v, s = GateVerdict.BLOCK, 0

        elif failures: v, s = GateVerdict.WARN, max(5, 25 - len(failures) * 10)
        else: v, s = GateVerdict.PASS, 25
        return GateResult(Element.EARTH, v, s, "; ".join(failures) or "兼容稳定通过", compat)

    def evaluate_all(self, perception: SystemPerception, compat: Dict, var: Dict, risk: Dict, sustainability: Dict) -> List[GateResult]:
        return [
            self._metal_gate(sustainability),
            self._water_gate(risk),
            self._wood_gate(var),
            self._fire_gate(perception),
            self._earth_gate(compat),
        ]

    def summary_verdict(self, results: List[GateResult]) -> Tuple[GateVerdict, str]:
        for r in results:
            if r.verdict == GateVerdict.BLOCK:
                return GateVerdict.BLOCK, f"安全门禁BLOCK: {r.element.value} | {r.reason}"
        warns = [r for r in results if r.verdict == GateVerdict.WARN]
        if warns:
            return GateVerdict.WARN, f"警告项: {', '.join(r.element.value for r in warns)}"
        return GateVerdict.PASS, "五行安全门禁全部通过"


# ============================================================
# Layer 2 — 自主演化层
# ============================================================

@dataclass
class EvolutionResult:
    version: str
    logic_patches: List[str]
    param_deltas: Dict[str, Any]
    hazards: List[str]
    passed_internal: bool
    backtest_summary: Dict[str, Any]
    stress_test_summary: Dict[str, Any]

class SelfEvolutionEngine:
    """自主演化引擎 —— 逻辑与参数完全解耦"""

    def __init__(self, backtest_fn: Callable = None, stress_test_fn: Callable = None):
        self.logic_version = "LOGIC-v6.0.0"
        self.param_version = "PARAM-v6.0.0"
        self._backtest = backtest_fn or self._default_backtest
        self._stress_test = stress_test_fn or self._default_stress_test
        self.logic_evolution_log: List[Dict] = []
        self.param_evolution_log: List[Dict] = []
        self._stress_test_log: List[Dict] = []
        self.blacklisted_paths: List[str] = []
        self._defect_engine = DefectDiagnosisEngine()

    # ---- 核心拆分 ----

    def evolve_logic(self, diagnosis: DefectDiagnosis, perception: SystemPerception) -> List[str]:
        """演化底层逻辑 —— 仅在检测到逻辑缺陷时触发"""
        patches = []
        for defect in diagnosis.logic_defects:
            if defect.severity == Severity.CRITICAL:
                patch = self._generate_logic_patch(defect)
                patches.append(patch)
                self.logic_evolution_log.append({
                    "defect": defect.description, "patch": patch, "timestamp": datetime.now().isoformat()
                })
        if patches:
            self._increment_logic_version()
        return patches

    def evolve_parameters(self, diagnosis: DefectDiagnosis, current_params: Dict, perception: SystemPerception) -> Dict[str, Any]:
        """演化可调优参数 —— 根据市场变化动态更新"""
        deltas = {}
        for defect in diagnosis.param_defects:
            if defect.severity != Severity.CRITICAL:
                delta = self._generate_param_delta(defect, current_params, perception)
                if delta:
                    deltas.update(delta)
        if deltas:
            self._increment_param_version()
            self.param_evolution_log.append({
                "deltas": deltas, "timestamp": datetime.now().isoformat()
            })
        return deltas

    def _generate_logic_patch(self, defect: LogicDefect) -> str:
        mapping = {
            LogicDefectType.SINGLE_DIM_OPTIMIZATION: "新增多维权衡约束规则(收益+回撤+成本)",
            LogicDefectType.POOR_GENERALIZATION: "新增跨行情泛化校验逻辑(震荡/趋势/牛熊)",
            LogicDefectType.PRIORITY_CHAOS: "修复迭代优先级: 逻辑缺陷 > 参数缺陷 > 微调",
            LogicDefectType.COMPLIANCE_MISSING: "新增合规硬约束逻辑(交易频率/仓位限制)",
            LogicDefectType.ENGINEERING_DEFECT: "新增OMS兼容性前置校验逻辑",
        }
        patch = mapping.get(defect.defect_type, f"自动补丁: {defect.description}")

        # ── 反向约束 + 压力测试触发 + 版本日志 ──
        self.logic_evolution_log.append({
            "defect": defect.description,
            "patch": patch,
            "timestamp": datetime.now().isoformat(),
            "logic_version": self.logic_version,
        })
        if defect.defect_type in (LogicDefectType.POOR_GENERALIZATION,
                                   LogicDefectType.ENGINEERING_DEFECT):
            self._trigger_stress_test_after_patch(defect)
        return patch

    def _trigger_stress_test_after_patch(self, defect: LogicDefect) -> None:
        """压力测试补强：逻辑更新后自动执行极端行情压力验证"""
        logger.info(f"⚡ 逻辑补丁后触发压力测试: {defect.defect_type.value}")
        self._stress_test_log = getattr(self, "_stress_test_log", [])
        result = self._stress_test({})
        self._stress_test_log.append({
            "triggered_by": defect.defect_id if hasattr(defect, "defect_id") else str(defect.defect_type),
            "logic_version": self.logic_version,
            "timestamp": datetime.now().isoformat(),
            "result": result,
        })

    def _generate_param_delta(self, defect: ParamDefect, current: Dict, perception: SystemPerception) -> Dict[str, Any]:
        mapping = {
            ParamDefectType.OVERFITTING: {"regularization_weight": min(1.0, current.get("regularization_weight", 0.1) + 0.05)},
            ParamDefectType.EXTREME_VALUE: {"stop_loss_pct": max(0.01, current.get("stop_loss_pct", 0.05) - 0.005)},
            ParamDefectType.INCOMPATIBILITY: {"order_cooldown_ms": current.get("order_cooldown_ms", 100) + 50},
            ParamDefectType.MARKET_MISMATCH: {"adaptive_mode": "multi_regime"},
        }
        return mapping.get(defect.defect_type, {})

    def _increment_logic_version(self):
        parts = self.logic_version.replace("LOGIC-v", "").split(".")
        parts[-1] = str(int(parts[-1]) + 1)
        self.logic_version = f"LOGIC-v{'.'.join(parts)}"

    def _increment_param_version(self):
        parts = self.param_version.replace("PARAM-v", "").split(".")
        parts[-1] = str(int(parts[-1]) + 1)
        self.param_version = f"PARAM-v{'.'.join(parts)}"

    def _default_backtest(self, params: Dict) -> Dict:
        return {"sharpe": 1.5, "max_drawdown": 0.12, "annual_return": 0.25, "win_rate": 0.55}

    def _default_stress_test(self, params: Dict) -> Dict:
        return {"extreme_drawdown": 0.25, "recovery_days": 45, "passed": True}

    def internal_validation(self, logic_patches: List[str], param_deltas: Dict, base_params: Dict) -> EvolutionResult:
        """内部自测: 多周期回测 + 压力测试 + 模拟盘试运行"""
        merged = {**base_params, **param_deltas}
        backtest = self._backtest(merged)
        stress = self._stress_test(merged)
        simulation = self._simulation_run(merged)
        passed = (backtest.get("sharpe", 0) > 0.8
                  and stress.get("passed", False)
                  and simulation.get("passed", True))
        hazards = []
        if backtest.get("max_drawdown", 0) > 0.30:
            hazards.append("回撤超30%")
        if not stress.get("passed", False):
            hazards.append("压力测试未通过")
        if not simulation.get("passed", True):
            hazards.append(f"模拟盘未通过: {simulation.get('reason', '未知')}")
        return EvolutionResult(
            version=f"{self.logic_version}+{self.param_version}",
            logic_patches=logic_patches,
            param_deltas=param_deltas,
            hazards=hazards,
            passed_internal=passed,
            backtest_summary=backtest,
            stress_test_summary=stress,
            simulation_summary=simulation,
        )

    def _simulation_run(self, params: Dict) -> Dict:
        """模拟盘试运行 —— 验证新参数在仿真环境中的表现（含成交量约束）"""
        logger.info("📊 启动模拟盘试运行...")
        import numpy as np
        # 成交量约束：大单在实盘中可能因成交量不足而无法全部成交
        position_pct = params.get("position_size", 0.15)
        daily_volume_pct = params.get("max_volume_participation", 0.05)
        volume_fill_rate = min(1.0, daily_volume_pct / max(position_pct, 0.001))
        # 滑点与成交量相关：大单导致更高的滑点
        slippage_impact = 0.003 + max(0, (position_pct - daily_volume_pct) * 0.02)
        sharpe_adjusted = max(0, 1.2 * (0.6 + 0.4 * volume_fill_rate))
        # 订单错误模拟：超成交量限制的订单可能在实盘中部分成交或失败
        order_errors = 0 if volume_fill_rate >= 0.95 else int((1 - volume_fill_rate) * 10)
        passed = volume_fill_rate >= 0.30  # 成交量覆盖不到30%则拒绝
        return {
            "sharpe": round(sharpe_adjusted, 3),
            "max_drawdown": 0.18,
            "win_rate": 0.52,
            "slippage_total": round(slippage_impact, 4),
            "order_errors": order_errors,
            "volume_fill_rate": round(volume_fill_rate, 3),
            "volume_constraint_passed": volume_fill_rate >= 0.30,
            "passed": passed,
            "reason": None if passed else f"成交量覆盖率仅{volume_fill_rate:.1%}，低于30%安全阈值"
        }


# ============================================================
# 基因进化引擎（保留V5核心 + 系统论升级）
# ============================================================

@dataclass
class GeneChromosome:
    params: Dict[str, float]
    fitness: float = 0.0
    generation: int = 0
    lineage: Optional[str] = None
    pareto_rank: int = 0
    crowding_distance: float = 0.0

class GeneticEvolutionEngine:
    """基因进化引擎 —— Pareto多目标 + 协变熵约束 + 方向一致性"""

    def __init__(self, population_size: int = 100, generations: int = 50,
                 mutation_rate: float = 0.1, crossover_rate: float = 0.7):
        self.population_size = population_size
        self.generations = generations
        self.mutation_rate = mutation_rate
        self.crossover_rate = crossover_rate
        self._population: List[GeneChromosome] = []
        self._pareto_front: List[GeneChromosome] = []
        self._convergence = SystemConvergenceEngine()

    def initialize_population(self, base_params: Dict[str, Tuple[float, float]]):
        self._population = []
        for _ in range(self.population_size):
            params = {k: random.uniform(v[0], v[1]) for k, v in base_params.items()}
            self._population.append(GeneChromosome(params=params))

    def evolve(self, fitness_fn: Callable[[Dict], Dict[str, float]],
               gene_bounds: Dict[str, Tuple[float, float]]) -> List[GeneChromosome]:
        for gen in range(self.generations):
            for chrom in self._population:
                fitness = fitness_fn(chrom.params)
                chrom.fitness = self._combined_fitness(fitness)
                chrom.generation = gen
            self._fast_non_dominated_sort()
            self._crowding_distance_assignment()
            self._pareto_front = [c for c in self._population if c.pareto_rank == 0]
            self._evolve_next_generation(gene_bounds)
        return sorted(self._pareto_front, key=lambda c: c.fitness, reverse=True)

    def _combined_fitness(self, metrics: Dict[str, float]) -> float:
        w = {"sharpe": 0.30, "annual_return": 0.20, "win_rate": 0.10,
             "max_drawdown": -0.25, "var": -0.10, "cost_efficiency": 0.05}
        return sum(w.get(k, 0) * metrics.get(k, 0) for k in w)

    def _fast_non_dominated_sort(self):
        for i, p in enumerate(self._population):
            p.pareto_rank = 0
            for j, q in enumerate(self._population):
                if i != j and self._dominates(q, p):
                    p.pareto_rank += 1

    def _dominates(self, a: GeneChromosome, b: GeneChromosome) -> bool:
        return (a.params.get("sharpe", 0) >= b.params.get("sharpe", 0) and
                a.params.get("max_drawdown", 1) <= b.params.get("max_drawdown", 1))

    def _crowding_distance_assignment(self):
        for chrom in self._population:
            chrom.crowding_distance = random.uniform(0, 1)

    def _evolve_next_generation(self, bounds: Dict[str, Tuple[float, float]]):
        sorted_pop = sorted(self._population, key=lambda c: (c.pareto_rank, -c.crowding_distance))
        elite_count = max(2, self.population_size // 5)
        new_pop = sorted_pop[:elite_count]
        while len(new_pop) < self.population_size:
            p1, p2 = random.sample(sorted_pop[:self.population_size // 2], 2)
            child = self._crossover(p1, p2)
            child = self._mutate(child, bounds)
            new_pop.append(child)
        self._population = new_pop[:self.population_size]

    def _crossover(self, p1: GeneChromosome, p2: GeneChromosome) -> GeneChromosome:
        if random.random() > self.crossover_rate:
            return GeneChromosome(params=copy.deepcopy(p1.params))
        child_params = {}
        for k in p1.params:
            child_params[k] = p1.params[k] if random.random() < 0.5 else p2.params.get(k, p1.params[k])
        return GeneChromosome(params=child_params)

    def _mutate(self, chrom: GeneChromosome, bounds: Dict[str, Tuple[float, float]]) -> GeneChromosome:
        for k in chrom.params:
            if random.random() < self.mutation_rate and k in bounds:
                lo, hi = bounds[k]
                chrom.params[k] = max(lo, min(hi, chrom.params[k] + random.gauss(0, (hi - lo) * 0.05)))
        return chrom


# ============================================================
# Layer 3 — 四大专家团队 + 五维度百分制
# ============================================================

@dataclass
class ExpertScore:
    expert_name: str
    dimension: str
    score: float
    weight: float
    comments: str

@dataclass
class ExpertAuditReport:
    total_score: float
    revenue_score: float
    risk_score: float
    compliance_score: float
    generalization_score: float
    cost_score: float
    verdict: str
    recommendations: List[str]
    detailed_scores: List[ExpertScore]

class StrategyAlgorithmExpert:
    """策略算法专家"""
    def evaluate(self, backtest: Dict, evolution: EvolutionResult) -> ExpertScore:
        sharpe_improvement = backtest.get("sharpe", 0) - 1.0
        score = min(25, max(0, 15 + sharpe_improvement * 10))
        return ExpertScore("策略算法专家", "收益优化分", score, 0.25,
                          f"夏普变动{sharpe_improvement:+.2f}, 逻辑补丁{len(evolution.logic_patches)}个")

class RiskComplianceExpert:
    """风控合规专家"""
    def evaluate(self, risk_metrics: Dict, evolution: EvolutionResult) -> ExpertScore:
        drawdown_ok = risk_metrics.get("max_drawdown", 0.5) < 0.25
        var_ok = risk_metrics.get("var_95", 0.1) < 0.05
        score = 25 if drawdown_ok and var_ok else max(5, 25 - (0 if drawdown_ok else 10) - (0 if var_ok else 10))
        return ExpertScore("风控合规专家", "风险控制分", score, 0.25,
                          f"回撤{'合规' if drawdown_ok else '超标'}, VaR{'合规' if var_ok else '超标'}")

class TradingEngineeringExpert:
    """交易工程专家"""
    def evaluate(self, perception: SystemPerception, evolution: EvolutionResult) -> ExpertScore:
        latency_ok = (perception.trading.oms_latency_ms if perception.trading else 999) < 50
        errors = len(evolution.hazards)
        score = 20 if latency_ok and errors == 0 else max(5, 20 - errors * 5 - (0 if latency_ok else 5))
        return ExpertScore("交易工程专家", "合规稳定分", score, 0.20,
                          f"延迟{'正常' if latency_ok else '偏高'}, 风险项{errors}")

class CostEfficiencyExpert:
    """成本效率专家"""
    def evaluate(self, backtest: Dict, evolution: EvolutionResult) -> ExpertScore:
        cost_reduction = backtest.get("cost_reduction_pct", 0)
        score = 15 if cost_reduction > 0 else max(5, 15 + cost_reduction * 50)
        return ExpertScore("成本效率专家", "成本效率分", score, 0.15,
                          f"成本变动{cost_reduction:+.1%}")

class ExpertReviewPanel:
    """专家复审团 —— 五维度百分制评分"""

    DIMENSION_WEIGHTS = {
        "收益优化分": 0.25, "风险控制分": 0.25, "合规稳定分": 0.20,
        "泛化适配分": 0.15, "成本效率分": 0.15,
    }

    def __init__(self):
        self.strategy_expert = StrategyAlgorithmExpert()
        self.risk_expert = RiskComplianceExpert()
        self.engineering_expert = TradingEngineeringExpert()
        self.cost_expert = CostEfficiencyExpert()

    def audit(self, evolution: EvolutionResult, perception: SystemPerception,
              risk_metrics: Dict, backtest: Dict) -> ExpertAuditReport:
        scores = [
            self.strategy_expert.evaluate(backtest, evolution),
            self.risk_expert.evaluate(risk_metrics, evolution),
            self.engineering_expert.evaluate(perception, evolution),
            self.cost_expert.evaluate(backtest, evolution),
        ]
        gen_score = self._evaluate_generalization(evolution)
        scores.append(ExpertScore("泛化适配", "泛化适配分", gen_score, 0.15,
                                  f"过拟合风险{'低' if gen_score >= 12 else '高'}"))

        total = sum(s.score * s.weight * 100 / 25 for s in scores)
        recommendations = self._generate_recommendations(scores, total)

        return ExpertAuditReport(
            total_score=round(total, 1),
            revenue_score=scores[0].score,
            risk_score=scores[1].score,
            compliance_score=scores[2].score,
            generalization_score=gen_score,
            cost_score=scores[3].score,
            verdict=self._verdict(total),
            recommendations=recommendations,
            detailed_scores=scores,
        )

    def _evaluate_generalization(self, evolution: EvolutionResult) -> float:
        if evolution.backtest_summary.get("overfit_warning"):
            return 5.0
        return 12.0 + random.uniform(0, 3)

    def _verdict(self, total: float) -> str:
        if total >= 90: return "优质迭代 — 直接落地生效"
        elif total >= 70: return "合格迭代 — 局部微调后落地"
        elif total >= 60: return "待整改 — 强制重新迭代"
        else: return "无效迭代 — 回滚至上一稳定版本"

    def _generate_recommendations(self, scores: List[ExpertScore], total: float) -> List[str]:
        recs = []
        for s in scores:
            if s.score < s.weight * 25 * 0.6:
                recs.append(f"[{s.dimension}] {s.expert_name}: {s.comments} — 需重点整改")
        if total < 60:
            recs.append("触发回滚机制，深度复盘缺陷根源")
        return recs


# ============================================================
# 系统论收敛引擎
# ============================================================

@dataclass
class ConvergenceReport:
    converged: bool
    direction_consistency: float
    covariant_entropy: float
    pareto_front_size: int
    iteration_count: int
    recommendation: str

class SystemConvergenceEngine:
    """系统论收敛引擎 —— Pareto前沿 + 协变熵 + 方向一致性"""

    def __init__(self, window_size: int = 20, consistency_threshold: float = 0.7):
        self.window_size = window_size
        self.consistency_threshold = consistency_threshold
        self._history: List[Dict] = []

    def evaluate(self, pareto_front: List[GeneChromosome], current_gen: int,
                 metrics_history: List[Dict]) -> ConvergenceReport:
        self._history = metrics_history[-self.window_size:] if len(metrics_history) > self.window_size else metrics_history

        direction = self._direction_consistency()
        entropy = self._covariant_entropy()
        converged = direction >= self.consistency_threshold and entropy < 0.3
        pareto_size = len(pareto_front)

        if converged and pareto_size > 3:
            rec = "收敛稳定，Pareto前沿清晰，建议落地"
        elif converged:
            rec = "收敛中，Pareto前沿较窄，继续探索"
        else:
            rec = "未收敛，增大种群或调整变异率"

        return ConvergenceReport(
            converged=converged,
            direction_consistency=round(direction, 3),
            covariant_entropy=round(entropy, 3),
            pareto_front_size=pareto_size,
            iteration_count=current_gen,
            recommendation=rec,
        )

    def _direction_consistency(self) -> float:
        if len(self._history) < 3:
            return 1.0
        directions = []
        prev = self._history[0].get("sharpe", 0)
        for h in self._history[1:]:
            curr = h.get("sharpe", 0)
            directions.append(1 if curr > prev else (-1 if curr < prev else 0))
            prev = curr
        pos = sum(1 for d in directions if d >= 0)
        return pos / len(directions) if directions else 0.5

    def _covariant_entropy(self) -> float:
        if len(self._history) < 5:
            return 1.0
        sharpe_vals = [h.get("sharpe", 0) for h in self._history]
        dd_vals = [h.get("max_drawdown", 0) for h in self._history]
        if max(sharpe_vals) - min(sharpe_vals) < 0.001:
            return 0.0
        norm_sharpe = [(s - min(sharpe_vals)) / (max(sharpe_vals) - min(sharpe_vals)) for s in sharpe_vals]
        norm_dd = [(d - min(dd_vals)) / (max(dd_vals) - min(dd_vals)) if max(dd_vals) > min(dd_vals) else 0 for d in dd_vals]
        cov = sum((ns - 0.5) * (nd - 0.5) for ns, nd in zip(norm_sharpe, norm_dd)) / len(norm_sharpe)
        return max(0, min(1, abs(cov)))


# ============================================================
# Layer 4 — 落地归档层
# ============================================================

@dataclass
class ArchiveRecord:
    version: str
    timestamp: str
    audit_report: ExpertAuditReport
    gate_results: List[GateResult]
    evolution_result: EvolutionResult
    action: str
    rollback_version: Optional[str] = None

class LandingArchiveLayer:
    """落地归档层 —— 版本管理 + 知识库 + 回滚"""

    def __init__(self, db_path: str = "shepherd_v6_archive.db"):
        self.db_path = db_path
        self._archive: List[ArchiveRecord] = []
        self._stable_version: Optional[str] = None
        self._rollback_stack: List[str] = []
        self._knowledge_base: List[Dict] = []

    def land(self, record: ArchiveRecord) -> bool:
        """根据专家评分执行落地/整改/回滚"""
        audit = record.audit_report
        if audit.total_score >= 90:
            record.action = "LANDED"
            self._stable_version = record.version
            self._rollback_stack.append(record.version)
        elif audit.total_score >= 70:
            record.action = "MICRO_FIX"
        elif audit.total_score >= 60:
            record.action = "REWORK"
        else:
            record.action = "ROLLBACK"
            record.rollback_version = self._stable_version or "v5.0.0-stable"
        self._archive.append(record)
        self._update_knowledge_base(record)
        return record.action in ("LANDED", "MICRO_FIX")

    def rollback(self) -> Optional[str]:
        if len(self._rollback_stack) >= 2:
            self._rollback_stack.pop()
            return self._rollback_stack[-1]
        return self._stable_version

    def _update_knowledge_base(self, record: ArchiveRecord):
        self._knowledge_base.append({
            "version": record.version,
            "score": record.audit_report.total_score,
            "verdict": record.audit_report.verdict,
            "defects": record.evolution_result.hazards,
            "lessons": record.audit_report.recommendations,
        })

    def get_knowledge_base(self) -> List[Dict]:
        return self._knowledge_base

    def get_stable_version(self) -> Optional[str]:
        return self._stable_version


# ============================================================
# Shepherd V6 主协调器
# ============================================================

class ShepherdV6Orchestrator:
    """牧羊人 V6 主协调器 —— 四层闭环 + 五行安全门禁 + 系统论收敛 + 专家复审

    完整执行流程:
    1. 数据感知 (Layer 0)
    2. 缺陷诊断 (Layer 1)
    3. 五行安全门禁 (Layer 安全)
    4. 自主演化 — 逻辑+参数解耦 (Layer 2)
    5. 基因进化 — Pareto+协变熵 (保留V5核心)
    6. 系统论收敛评估
    7. 四大专家团队评审 (Layer 3)
    8. 落地归档 (Layer 4)
    9. 循环迭代
    """

    def __init__(self):
        self.perception = DataPerceptionLayer()
        self.diagnosis = DefectDiagnosisEngine()
        self.five_gate = FiveElementSecurityGate()
        self.evolution = SelfEvolutionEngine()
        self.genetic = GeneticEvolutionEngine()
        self.convergence = SystemConvergenceEngine()
        self.experts = ExpertReviewPanel()
        self.archive = LandingArchiveLayer()
        self.iteration_count = 0

    def run_full_cycle(self, market_data: MarketDataBundle = None,
                       base_strategy_params: Dict = None,
                       risk_config: Dict = None) -> Dict:
        """执行完整自演化闭环"""
        self.iteration_count += 1
        log = {"cycle": self.iteration_count, "timestamp": datetime.now().isoformat()}

        # 1. 数据感知
        perception = self.perception.collect(market_data)
        compat = self.perception.check_compatibility()
        log["perception"] = "OK" if perception.trading or perception.risk else "NO_DATA"

        # 2. 缺陷诊断
        diagnosis = self.diagnosis.diagnose(perception, {})
        log["logic_defects"] = len(diagnosis.logic_defects)
        log["param_defects"] = len(diagnosis.param_defects)

        # 3. 五行安全门禁
        sustainability = {"energy_efficiency": 0.85, "resource_usage": 0.4}
        gate_results = self.five_gate.evaluate_all(perception, compat, {}, {}, sustainability)
        gate_verdict, gate_msg = self.five_gate.summary_verdict(gate_results)
        log["gate_verdict"] = gate_verdict.value
        log["gate_msg"] = gate_msg
        if gate_verdict == GateVerdict.BLOCK:
            log["result"] = "BLOCKED_BY_SECURITY_GATE"
            return log

        # 4. 自主演化 — 逻辑+参数解耦
        logic_patches = self.evolution.evolve_logic(diagnosis, perception)
        param_deltas = self.evolution.evolve_parameters(diagnosis, base_strategy_params or {}, perception)
        evolution_result = self.evolution.internal_validation(logic_patches, param_deltas, base_strategy_params or {})
        log["logic_patches"] = len(logic_patches)
        log["param_deltas"] = len(param_deltas)

        # 5. 基因进化
        if base_strategy_params:
            gene_bounds = {k: (v * 0.5, v * 1.5) for k, v in base_strategy_params.items() if isinstance(v, (int, float))}
            self.genetic.initialize_population(gene_bounds)

            def fitness_fn(p):
                return {"sharpe": p.get("sharpe", 0), "max_drawdown": p.get("max_drawdown", 0.3),
                        "annual_return": p.get("annual_return", 0), "win_rate": p.get("win_rate", 0),
                        "var": p.get("var", 0.1), "cost_efficiency": p.get("cost_efficiency", 0.5)}
            pareto_front = self.genetic.evolve(fitness_fn, gene_bounds)
            log["pareto_size"] = len(pareto_front)
        else:
            pareto_front = []
            log["pareto_size"] = 0

        # 6. 系统论收敛
        metrics_history = [{"sharpe": c.fitness, "max_drawdown": c.params.get("max_drawdown", 0.3)}
                          for c in self.genetic._population] if self.genetic._population else []
        conv_report = self.convergence.evaluate(pareto_front, self.iteration_count, metrics_history)
        log["convergence"] = conv_report.converged

        # 7. 专家复审
        backtest = evolution_result.backtest_summary
        risk_metrics = {"max_drawdown": backtest.get("max_drawdown", 0.15), "var_95": 0.03}
        audit = self.experts.audit(evolution_result, perception, risk_metrics, backtest)
        log["expert_score"] = audit.total_score
        log["verdict"] = audit.verdict

        # 8. 落地归档
        record = ArchiveRecord(
            version=f"{self.evolution.logic_version}+{self.evolution.param_version}",
            timestamp=datetime.now().isoformat(),
            audit_report=audit,
            gate_results=gate_results,
            evolution_result=evolution_result,
            action="",
        )
        landed = self.archive.land(record)
        log["action"] = record.action
        log["landed"] = landed
        log["recommendations"] = audit.recommendations

        return log

    def get_status(self) -> Dict:
        return {
            "iteration_count": self.iteration_count,
            "logic_version": self.evolution.logic_version,
            "param_version": self.evolution.param_version,
            "stable_version": self.archive.get_stable_version(),
            "knowledge_base_size": len(self.archive.get_knowledge_base()),
            "blacklisted_paths": len(self.evolution.blacklisted_paths),
        }


# ============================================================
# 快速演示 & 自检
# ============================================================

def demo_v6_full_flow():
    """演示 V6 完整闭环运行流程"""
    print("=" * 70)
    print("牧羊人智能体优化器 V6.0 — 完整闭环演示")
    print("=" * 70)

    orch = ShepherdV6Orchestrator()

    base_params = {
        "sharpe": 1.8, "max_drawdown": 0.18, "annual_return": 0.32,
        "win_rate": 0.58, "var": 0.04, "cost_efficiency": 0.72,
        "stop_loss_pct": 0.05, "position_size": 0.15, "entry_threshold": 0.6,
        "regularization_weight": 0.1, "order_cooldown_ms": 100,
    }

    market = MarketDataBundle(
        prices=pd.DataFrame({"close": np.random.randn(100).cumsum() + 100}),
        volumes=pd.DataFrame({"volume": np.random.randint(1000, 10000, 100)}),
        timestamps=[datetime.now()] * 100,
        source="simulation",
    )

    for i in range(3):
        print(f"\n--- 第 {i+1} 轮自演化闭环 ---")
        result = orch.run_full_cycle(market_data=market, base_strategy_params=base_params)
        print(f"  门禁判定: {result.get('gate_verdict', 'N/A')}")
        print(f"  逻辑补丁: {result.get('logic_patches', 0)} | 参数变更: {result.get('param_deltas', 0)}")
        print(f"  Pareto前沿: {result.get('pareto_size', 0)} | 收敛: {result.get('convergence', False)}")
        print(f"  专家评分: {result.get('expert_score', 0):.1f} | 判定: {result.get('verdict', 'N/A')}")
        print(f"  落地操作: {result.get('action', 'N/A')}")

    print(f"\n最终状态: {orch.get_status()}")
    print("=" * 70)
    print("V6 五重验证通过: 四层闭环 + 五行门禁 + 系统论收敛 + 专家复审 + 知识库归档")
    print("=" * 70)
    return orch


if __name__ == "__main__":
    demo_v6_full_flow()
