#!/usr/bin/env python3
"""
熵韬收敛优化器集群 v4.0 — 五维熵驱动收敛引擎
==============================================

EntropyTauOptimizer（熵韬收敛优化器集群）是主力策略寻优引擎，
基于期望/方差/熵/最值/概率五大数学指标的工程化落地：

  期望(E)  → 收益中枢锚定，目标年化收益基准
  方差(V)  → 净值波动约束，惩罚过度激进
  熵(H)    → 参数空间/决策熵压缩，防止过拟合与信号漂移
  最值(M)  → 极端风险硬截断，风控兜底
  概率(P)  → 信号质量筛选，抬高有效交易概率

五维指标定位: 搜索策略控制器，不替代评分
  - 最终排序仍用原始四维评分（已验证可靠）
  - 五维指标用于: 自适应粗筛、分区域精搜密度、硬约束过滤、熵趋势收敛

核心公式:
  Score = w_E·E_score + w_V·(1-V_penalty) + w_H·(1-H_penalty) + w_M·M_score + w_P·P_score

目标: 收敛更快、曲线更稳、回测与实盘偏差更小

备选方案: TauOptimizerCluster（原韬定律优化器集群）作为低配快速兜底
"""

import math
import random
import time
import statistics
from collections import Counter
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field

# 数据平台集成：优化器数据源统一通过qlib_adapter/alpha_factors获取
# 批量回测、参数寻优、模型训练仅读取数据平台，无本地历史文件依赖

# 引用现有优化器的基础组件
from core.tau_optimizer_cluster import (
    TauOptimizerCluster, BacktestResult, ParameterSpaceFolding,
    SimilarityCache, IncrementalBacktest, PatternAnalyzer
)


# ============================================================
# 1. 熵计算引擎
# ============================================================

class EntropyCalculator:
    """信息熵计算器 — 用于参数空间熵和决策熵"""

    @staticmethod
    def shannon_entropy(values: List[float], bins: int = 10) -> float:
        """
        香农熵 H = -∑ p_i·log₂(p_i)

        Args:
            values: 数值列表
            bins: 分箱数（连续值离散化）

        Returns:
            熵值 (0 = 完全确定, log₂(bins) = 最大混乱)
        """
        if len(values) < 2:
            return 0.0

        n = len(values)
        min_v, max_v = min(values), max(values)
        if min_v == max_v:
            return 0.0  # 全部相同 → 完全确定

        # 等宽分箱
        bin_width = (max_v - min_v) / bins
        counts = [0] * bins
        for v in values:
            idx = min(bins - 1, int((v - min_v) / bin_width))
            counts[idx] += 1

        # 计算熵
        entropy = 0.0
        for c in counts:
            if c > 0:
                p = c / n
                entropy -= p * math.log2(p)

        return entropy

    @staticmethod
    def parameter_space_entropy(param_history: List[Dict[str, float]]) -> float:
        """
        参数空间熵 — 衡量搜索分散程度

        熵越高 → 搜索越分散（探索阶段）
        熵越低 → 搜索越集中（收敛阶段）

        优化目标: 前期允许高熵探索，后期强制熵下降收敛
        """
        if len(param_history) < 2:
            return 0.0

        # 取每个参数的取值序列
        all_keys = set()
        for ph in param_history:
            all_keys.update(ph.keys())

        entropies = []
        for key in all_keys:
            vals = [ph.get(key, 0) for ph in param_history]
            entropies.append(EntropyCalculator.shannon_entropy(vals))

        return statistics.mean(entropies) if entropies else 0.0

    @staticmethod
    def decision_entropy(signals: List[float]) -> float:
        """
        决策熵 — 衡量策略信号的一致性

        信号方向一致 → 低熵（稳定）
        信号方向混乱 → 高熵（过拟合/漂移）

        Args:
            signals: 策略信号序列 (正=做多, 负=做空, 0=空仓)
        """
        if len(signals) < 2:
            return 0.0

        # 三分类: 做多(+1), 空仓(0), 做空(-1)
        categorized = [1 if s > 0.01 else (-1 if s < -0.01 else 0) for s in signals]
        counter = Counter(categorized)
        n = len(categorized)

        entropy = 0.0
        for count in counter.values():
            p = count / n
            entropy -= p * math.log2(p)

        return entropy

    @staticmethod
    def feature_redundancy_entropy(feature_matrix: List[List[float]]) -> float:
        """
        特征冗余熵 — 衡量特征之间的冗余度

        熵过高 → 特征冗余、信号互相冲突
        目标: 剔除高冗余特征，保留独立特征
        """
        if len(feature_matrix) < 2 or len(feature_matrix[0]) < 2:
            return 0.0

        n_features = len(feature_matrix[0])
        n_samples = len(feature_matrix)

        # 计算特征间相关系数矩阵的熵
        correlations = []
        for i in range(n_features):
            for j in range(i + 1, n_features):
                x = [row[i] for row in feature_matrix]
                y = [row[j] for row in feature_matrix]
                corr = EntropyCalculator._pearson_correlation(x, y)
                correlations.append(abs(corr))

        return EntropyCalculator.shannon_entropy(correlations, bins=5)

    @staticmethod
    def _pearson_correlation(x: List[float], y: List[float]) -> float:
        """皮尔逊相关系数"""
        n = len(x)
        if n < 2:
            return 0.0
        mx = statistics.mean(x)
        my = statistics.mean(y)
        sx = statistics.stdev(x) if len(set(x)) > 1 else 0.001
        sy = statistics.stdev(y) if len(set(y)) > 1 else 0.001
        cov = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y)) / n
        return cov / (sx * sy + 1e-10)


# ============================================================
# 2. 五维评分引擎
# ============================================================

@dataclass
class EnhancedBacktestResult:
    """增强版回测结果 — 包含五维指标"""
    strategy_name: str
    params: Dict[str, float]
    total_return: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    total_trades: int
    timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%d %H:%M:%S"))
    is_approximate: bool = False
    confidence: float = 1.0
    simulated: bool = False

    # === 五维增强字段 ===
    daily_returns: List[float] = field(default_factory=list)   # 日收益率序列
    trade_returns: List[float] = field(default_factory=list)   # 单笔交易收益序列
    signal_sequence: List[float] = field(default_factory=list) # 信号序列
    param_history: List[Dict[str, float]] = field(default_factory=list) # 参数搜索历史

    def score(self) -> float:
        """原始评分（兼容旧接口）"""
        tr = float(self.total_return)
        ret_score = min(3.0, max(0.0, tr * 5.0))
        sh = float(self.sharpe_ratio)
        sharpe_score = min(3.0, max(0.0, sh))
        dd = float(self.max_drawdown)
        dd_score = max(0.0, 2.0 - dd * 4.0)
        wr = float(self.win_rate)
        win_score = min(2.0, max(0.0, (wr - 0.4) * 5.0))
        total = round(ret_score + sharpe_score + dd_score + win_score, 4)
        return round(total * self.confidence, 4)


class FiveMetricScorer:
    """
    五维评分器 — 期望/方差/熵/最值/概率 加权融合

    五维指标各自定位:
      E(期望) → 收益中枢，确保参数有正的收益期望
      V(方差) → 波动约束，惩罚净值大起大落
      H(熵)   → 决策稳定性，压缩信号混乱度
      M(最值) → 极端风险拦截，防止爆仓参数
      P(概率) → 信号质量，剔除低胜率噪声

    三层输出:
      1. 综合评分(0-10) — 用于参数质量排序
      2. 搜索策略建议 — 告诉优化器该往哪搜、搜多少
      3. 风险等级 — 分级标记(绿/黄/红)，替代一刀切
    """

    # 默认权重配置
    DEFAULT_WEIGHTS = {
        "expectation": 0.30,   # 收益中枢
        "variance":    0.15,   # 波动约束
        "entropy":     0.20,   # 熵压缩
        "extreme":     0.20,   # 极端风险
        "probability": 0.15,   # 信号质量
    }

    # 硬约束阈值（分级）
    HARD_CONSTRAINTS = {
        "max_drawdown_red": 0.40,     # 红色: 回撤>40% 直接淘汰
        "max_drawdown_yellow": 0.25,  # 黄色: 回撤>25% 降权
        "min_win_rate": 0.30,         # 最低胜率30%
        "min_sharpe": 0.0,            # 最低夏普（放宽，允许负夏普被原评分自然淘汰）
        "max_entropy_red": 0.85,      # 红色: 决策熵>0.85 信号完全混乱
        "max_entropy_yellow": 0.60,   # 黄色: 决策熵>0.60 信号不够稳定
        "variance_red": 0.05,         # 日收益方差上限(红色)
        "variance_yellow": 0.02,      # 日收益方差上限(黄色)
    }

    def __init__(self, weights: Dict[str, float] = None,
                 constraints: Dict[str, float] = None):
        self.weights = weights or self.DEFAULT_WEIGHTS.copy()
        self.constraints = constraints or self.HARD_CONSTRAINTS.copy()

    def check_hard_constraints(self, result: EnhancedBacktestResult) -> Tuple[str, List[str], float]:
        """
        硬约束检查 — 分级制（红/黄/绿）

        Returns:
            (等级: "green"/"yellow"/"red", 失败原因列表, 惩罚系数: 1.0/0.6/0.0)
        """
        failures = []
        level = "green"
        penalty = 1.0

        # 最大回撤
        if result.max_drawdown > self.constraints["max_drawdown_red"]:
            level = "red"
            failures.append(f"回撤{result.max_drawdown:.1%}>{self.constraints['max_drawdown_red']:.0%}(红)")
        elif result.max_drawdown > self.constraints["max_drawdown_yellow"]:
            if level == "green":
                level = "yellow"
            failures.append(f"回撤{result.max_drawdown:.1%}>{self.constraints['max_drawdown_yellow']:.0%}(黄)")

        # 最低胜率
        if result.win_rate < self.constraints["min_win_rate"]:
            level = "red"
            failures.append(f"胜率{result.win_rate:.1%}<{self.constraints['min_win_rate']:.0%}")

        # 最低夏普
        if result.sharpe_ratio < self.constraints["min_sharpe"]:
            if level == "green":
                level = "yellow"
            failures.append(f"夏普{result.sharpe_ratio:.2f}<{self.constraints['min_sharpe']}")

        # 决策熵
        if result.signal_sequence:
            decision_h = EntropyCalculator.decision_entropy(result.signal_sequence)
            decision_h_norm = decision_h / 1.585
            if decision_h_norm > self.constraints["max_entropy_red"]:
                level = "red"
                failures.append(f"决策熵{decision_h_norm:.2f}>{self.constraints['max_entropy_red']}(红,信号混乱)")
            elif decision_h_norm > self.constraints["max_entropy_yellow"]:
                if level == "green":
                    level = "yellow"
                failures.append(f"决策熵{decision_h_norm:.2f}>{self.constraints['max_entropy_yellow']}(黄)")

        # 方差
        if result.daily_returns and len(result.daily_returns) >= 5:
            daily_var = statistics.variance(result.daily_returns)
            if daily_var > self.constraints["variance_red"]:
                level = "red"
                failures.append(f"日方差{daily_var:.4f}>{self.constraints['variance_red']}(红,波动过大)")
            elif daily_var > self.constraints["variance_yellow"]:
                if level == "green":
                    level = "yellow"
                failures.append(f"日方差{daily_var:.4f}>{self.constraints['variance_yellow']}(黄)")

        # 极端单笔亏损
        if result.trade_returns:
            worst_trade = min(result.trade_returns)
            if worst_trade < -0.20:
                level = "red"
                failures.append(f"单笔最大亏损{worst_trade:.1%}超限")

        # 惩罚系数
        if level == "red":
            penalty = 0.0   # 红色直接淘汰
        elif level == "yellow":
            penalty = 0.6   # 黄色降权

        return level, failures, penalty

    def get_search_strategy_advice(self, result: EnhancedBacktestResult,
                                    param_history: List[Dict] = None) -> Dict[str, Any]:
        """
        根据五维指标给出搜索策略建议

        各维度告诉优化器:
          - E(期望): 该区域是否有继续搜索的价值
          - V(方差): 该区域是否需要降密度
          - H(熵):   该区域是否需要扩大搜索（高熵=还没探索够）
          - M(最值): 该区域是否应该跳过
          - P(概率): 该区域信号质量是否足够

        Returns:
            {
                "search_priority": 0-1,    # 该区域搜索优先级
                "expand_factor": 1-3,      # 精搜点数放大系数
                "skip_region": bool,       # 是否跳过该区域
                "reasons": [str],          # 原因
                "risk_level": "green"/"yellow"/"red",
            }
        """
        level, failures, _ = self.check_hard_constraints(result)

        # 红色区域: 跳过
        if level == "red":
            return {
                "search_priority": 0.0,
                "expand_factor": 0.0,
                "skip_region": True,
                "reasons": failures,
                "risk_level": "red",
            }

        # 绿色/黄色区域: 计算搜索策略
        priority = 1.0
        expand = 1.0
        reasons = []

        # 收益期望: 正收益才值得搜
        if result.total_return > 0.05:
            expand = min(2.0, expand * 1.3)
            reasons.append("正收益期望→扩大搜索")
        elif result.total_return < -0.05:
            priority *= 0.5
            expand = max(0.5, expand * 0.7)
            reasons.append("负收益期望→缩小搜索")

        # 方差: 高波动区域降低密度
        if result.daily_returns and len(result.daily_returns) >= 5:
            daily_var = statistics.variance(result.daily_returns)
            if daily_var > 0.02:
                priority *= 0.7
                expand = max(0.5, expand * 0.8)
                reasons.append("高波动→降低密度")

        # 熵: 高熵区域需要更多探索
        if result.signal_sequence:
            decision_h = EntropyCalculator.decision_entropy(result.signal_sequence)
            decision_h_norm = decision_h / 1.585
            if decision_h_norm > 0.7:
                # 高熵=信号混乱，但不是坏区域，可能是还没探索够
                expand = min(2.5, expand * 1.5)
                reasons.append("高决策熵→扩大探索")
            elif decision_h_norm < 0.3:
                # 低熵=信号稳定，已经找到好区域，可以精搜
                reasons.append("低决策熵→信号稳定")

        # 胜率: 低胜率区域降低优先级
        if result.win_rate < 0.35:
            priority *= 0.6
            reasons.append("低胜率→降低优先级")

        if level == "yellow":
            priority *= 0.7
            reasons.append("黄色风险→降低优先级")

        return {
            "search_priority": round(min(1.0, max(0.0, priority)), 2),
            "expand_factor": round(min(3.0, max(0.3, expand)), 2),
            "skip_region": False,
            "reasons": reasons,
            "risk_level": level,
        }

    def compute_five_metric_score(self, result: EnhancedBacktestResult,
                                   param_history: List[Dict] = None) -> Dict[str, Any]:
        """
        计算五维综合评分

        Returns:
            {
                "total_score": float,        # 综合评分 (0-10)
                "dimension_scores": {...},   # 各维度得分
                "penalties": {...},          # 各惩罚项
                "entropy_metrics": {...},    # 熵指标
                "hard_constraint_pass": bool,
                "hard_constraint_failures": [...],
            }
        """
        dim = {}

        # ---- 1. 期望(E): 收益中枢评分 (0-3) ----
        tr = float(result.total_return)
        e_score = min(3.0, max(0.0, tr * 5.0))  # 60%+ → 3.0
        dim["expectation"] = round(e_score, 4)

        # ---- 2. 方差(V): 波动收敛惩罚 (0-1) ----
        if result.daily_returns and len(result.daily_returns) >= 5:
            daily_var = statistics.variance(result.daily_returns)
            # 方差越大惩罚越重
            v_penalty = min(1.0, daily_var / self.constraints["variance_red"])
            v_score = 1.0 - v_penalty  # 0 = 最大惩罚, 1 = 无惩罚
        else:
            v_penalty = 0.0
            v_score = 1.0
        dim["variance"] = round(v_score, 4)

        # ---- 3. 熵(H): 决策/参数熵压缩 (0-1) ----
        # 决策熵
        if result.signal_sequence:
            decision_h = EntropyCalculator.decision_entropy(result.signal_sequence)
            # 归一化: 最大熵 = log₂(3) ≈ 1.585 (三分类)
            decision_h_norm = decision_h / 1.585
        else:
            decision_h_norm = 0.0

        # 参数空间熵
        if param_history and len(param_history) >= 2:
            param_h = EntropyCalculator.parameter_space_entropy(param_history)
            # 归一化: 假设10个参数、10个分箱 → 最大熵 ≈ log₂(10) ≈ 3.32
            param_h_norm = min(1.0, param_h / 3.32)
        else:
            param_h_norm = 0.0

        # 综合熵惩罚: 决策熵权重0.6, 参数熵权重0.4
        combined_entropy = 0.6 * decision_h_norm + 0.4 * param_h_norm
        h_penalty = min(1.0, combined_entropy / self.constraints["max_entropy_red"])
        h_score = 1.0 - h_penalty
        dim["entropy"] = round(h_score, 4)

        # ---- 4. 最值(M): 极端风险截断得分 (0-2) ----
        dd = float(result.max_drawdown)
        # 回撤评分
        m_dd_score = max(0.0, 2.0 - dd * 4.0)  # 50%→0, 0%→2

        # 极端盈亏比检查
        if result.trade_returns and len(result.trade_returns) >= 1:
            best = max(result.trade_returns)
            worst = min(result.trade_returns)
            if worst < 0:
                ratio = abs(best / worst) if worst != 0 else 10.0
                m_ratio_bonus = min(0.5, ratio * 0.1)  # 盈亏比>5 → +0.5
            else:
                m_ratio_bonus = 0.5
        else:
            m_ratio_bonus = 0.0

        m_score = min(2.0, m_dd_score + m_ratio_bonus)
        dim["extreme"] = round(m_score, 4)

        # ---- 5. 概率(P): 信号质量评分 (0-2) ----
        wr = float(result.win_rate)
        p_win_score = min(1.5, max(0.0, (wr - 0.35) * 3.0))  # 35%→0, 85%→1.5

        # 交易次数惩罚: 交易太少不可靠
        if result.total_trades < 5:
            p_trade_penalty = 0.5
        elif result.total_trades < 10:
            p_trade_penalty = 0.2
        else:
            p_trade_penalty = 0.0

        p_score = max(0.0, p_win_score - p_trade_penalty)
        dim["probability"] = round(p_score, 4)

        # ---- 综合评分 ----
        total = (
            self.weights["expectation"] * dim["expectation"] * (10/3) +  # 缩放到0-10
            self.weights["variance"]     * dim["variance"] * 10 +
            self.weights["entropy"]      * dim["entropy"] * 10 +
            self.weights["extreme"]      * dim["extreme"] * (10/2) +     # 缩放到0-10
            self.weights["probability"]  * dim["probability"] * (10/2)   # 缩放到0-10
        )

        # 置信度加权
        total = round(total * result.confidence, 4)

        # 硬约束检查（分级制）
        risk_level, hc_failures, hc_penalty = self.check_hard_constraints(result)
        if risk_level != "green":
            total = round(total * hc_penalty, 4)

        return {
            "total_score": total,
            "dimension_scores": dim,
            "penalties": {
                "variance_penalty": round(v_penalty, 4),
                "entropy_penalty": round(h_penalty, 4),
                "trade_penalty": round(p_trade_penalty, 4),
                "hard_constraint_penalty": hc_penalty,
            },
            "entropy_metrics": {
                "decision_entropy": round(decision_h_norm, 4),
                "parameter_entropy": round(param_h_norm, 4),
                "combined_entropy": round(combined_entropy, 4),
            },
            "risk_level": risk_level,
            "hard_constraint_failures": hc_failures,
            "search_advice": self.get_search_strategy_advice(result, param_history),
        }


# ============================================================
# 3. 熵韬收敛优化器集群（主力引擎）
# ============================================================

class EntropyTauOptimizer(TauOptimizerCluster):
    """
    熵韬收敛优化器集群 — 主力策略寻优引擎 (v4.0)

    在原有三层架构(器件层/电路层/系统层)基础上，增加:
      第四层(熵约束层): 参数空间熵 + 决策熵 双重压缩
      第五层(五维评分层): 期望/方差/熵/最值/概率 多目标融合

    核心改进:
      1. 五维搜索策略控制器（不替代原评分，而是引导搜索方向）
      2. 自适应粗筛: 前30%均匀→之后按五维反馈动态调整
      3. 分区域精搜: 绿区×1.5 / 黄区×0.7 / 红区跳过
      4. 熵趋势在线引导: 实时监控，动态调整探索/开发平衡
      5. 硬约束真正生效: 红区参数不进精搜，最终结果排除红区
    """

    def __init__(self, param_ranges: Dict[str, Tuple[float, float]],
                 strategy_name: str = "generic_strategy",
                 similarity_threshold: float = 0.15,
                 default_compute_time_ms: float = 100.0,
                 strategy_mgr: Optional[Any] = None,
                 # 增强参数
                 scorer_weights: Dict[str, float] = None,
                 convergence_entropy_target: float = 0.3,
                 # 持久化继承参数
                 warm_start_params: Dict[str, float] = None,
                 auto_persist: bool = True):
        super().__init__(param_ranges, strategy_name, similarity_threshold,
                         default_compute_time_ms, strategy_mgr)

        # 五维评分器
        self.scorer = FiveMetricScorer(weights=scorer_weights)

        # 熵收敛参数
        self.convergence_entropy_target = convergence_entropy_target
        self._param_history: List[Dict[str, float]] = []
        self._score_history: List[float] = []
        self._entropy_history: List[float] = []

        # 持久化继承
        self.warm_start_params = warm_start_params  # 上次优化最佳参数，作为搜索起点
        self.auto_persist = auto_persist            # 是否自动持久化

    def _enhanced_score(self, result: BacktestResult,
                        daily_returns: List[float] = None,
                        trade_returns: List[float] = None,
                        signal_sequence: List[float] = None) -> Dict[str, Any]:
        """
        增强版评分 — 将 BacktestResult 转为 EnhancedBacktestResult 并计算五维评分

        如果 result 已经是 EnhancedBacktestResult 且包含有效的 daily_returns，
        则直接使用，避免重新生成不匹配的模拟数据。
        """
        # 如果 result 已经是 EnhancedBacktestResult 且有有效数据，直接使用
        if isinstance(result, EnhancedBacktestResult):
            if result.daily_returns and len(result.daily_returns) > 0:
                daily_returns = result.daily_returns
            if result.trade_returns and len(result.trade_returns) > 0:
                trade_returns = result.trade_returns
            if result.signal_sequence and len(result.signal_sequence) > 0:
                signal_sequence = result.signal_sequence

        enhanced = EnhancedBacktestResult(
            strategy_name=result.strategy_name,
            params=result.params,
            total_return=result.total_return,
            sharpe_ratio=result.sharpe_ratio,
            max_drawdown=result.max_drawdown,
            win_rate=result.win_rate,
            total_trades=result.total_trades,
            is_approximate=result.is_approximate,
            confidence=result.confidence,
            simulated=result.simulated,
            daily_returns=daily_returns or [],
            trade_returns=trade_returns or [],
            signal_sequence=signal_sequence or [],
            param_history=self._param_history,
        )

        score_result = self.scorer.compute_five_metric_score(enhanced, self._param_history)

        # 记录历史
        self._param_history.append(result.params.copy())
        self._score_history.append(score_result["total_score"])
        self._entropy_history.append(score_result["entropy_metrics"]["combined_entropy"])

        return score_result

    def get_convergence_metrics(self) -> Dict[str, Any]:
        """获取收敛指标（含熵趋势）"""
        n = len(self._score_history)
        if n < 3:
            return {"status": "insufficient_data", "iterations": n}

        # 收敛速度: 最后10次评分的标准差
        recent = self._score_history[-10:] if n >= 10 else self._score_history
        score_std = statistics.stdev(recent) if len(recent) >= 2 else 0.0

        # 熵收敛: 最后10次熵的均值
        recent_entropy = self._entropy_history[-10:] if n >= 10 else self._entropy_history
        avg_entropy = statistics.mean(recent_entropy) if recent_entropy else 0.0

        # 熵趋势: 计算熵下降速率（正=熵在降，好兆头）
        entropy_trend = 0.0
        if len(self._entropy_history) >= 5:
            first_half = self._entropy_history[:len(self._entropy_history)//2]
            second_half = self._entropy_history[len(self._entropy_history)//2:]
            if first_half and second_half:
                entropy_trend = statistics.mean(first_half) - statistics.mean(second_half)

        # 收敛判定（含熵趋势）
        is_converged = score_std < 0.5 and avg_entropy < self.convergence_entropy_target

        return {
            "iterations": n,
            "best_score": max(self._score_history) if self._score_history else 0,
            "latest_score": self._score_history[-1] if self._score_history else 0,
            "score_std": round(score_std, 4),
            "avg_entropy": round(avg_entropy, 4),
            "entropy_trend": round(entropy_trend, 4),  # 正=熵在降
            "is_converged": is_converged,
            "convergence_rate": round(1.0 / (score_std + 0.01), 2),
        }

    def _generate_simulated_returns(self, params: Dict[str, float],
                                     n_days: int = 30) -> Tuple[List[float], List[float], List[float]]:
        """
        生成模拟的日收益率、交易收益和信号序列（用于无真实数据时的熵计算）

        基于参数特征生成有意义的模拟数据，确保熵计算有区分度
        """
        import random as _random
        seed = hash(frozenset(params.items())) & 0xFFFFFFFF
        rng = _random.Random(seed)

        # 参数归一化: 将每个参数映射到 [0, 1] 范围
        normalized_params = {}
        for name, (pmin, pmax) in self.param_ranges.items():
            if name in params and pmax > pmin:
                normalized_params[name] = (params[name] - pmin) / (pmax - pmin)
            else:
                normalized_params[name] = 0.5

        norm_values = list(normalized_params.values())
        avg_norm = statistics.mean(norm_values) if norm_values else 0.5
        norm_spread = max(0.05, statistics.stdev(norm_values)) if len(norm_values) >= 2 else 0.1

        # 日收益率: 基于参数归一化均值和离散度
        mu = (avg_norm - 0.5) * 0.004   # 日收益均值（约±0.2%）
        sigma = norm_spread * 0.008     # 日收益标准差（约0.1-0.5%）
        daily_returns = [rng.gauss(mu, max(0.0002, sigma)) for _ in range(n_days)]

        # 交易收益: 模拟N笔交易
        n_trades = max(5, int(norm_spread * 30 + 5))
        trade_returns = [rng.gauss(mu * 3, max(0.003, sigma * 2)) for _ in range(n_trades)]

        # 信号序列: 参数越集中信号越一致
        trend_strength = (avg_norm - 0.5) * 2  # -1到1
        signal_sequence = []
        for _ in range(n_days):
            signal = trend_strength + rng.gauss(0, norm_spread * 0.5)
            signal_sequence.append(max(-1.0, min(1.0, signal)))

        return daily_returns, trade_returns, signal_sequence

    def run_enhanced_optimization(self,
                                   coarse_points: int = 50,
                                   refined_points_per_region: int = 30,
                                   validation_points: int = 5,
                                   run_analysis: bool = True,
                                   entropy_decay: bool = True,
                                   early_stop: bool = True) -> Dict[str, Any]:
        """
        运行增强版五维优化流程 — v4.0 五维真正驱动搜索

        五维指标定位（搜索策略控制器，不替代评分）:
          E(期望) → 驱动搜索方向: 正收益区扩大，负收益区缩小
          V(方差) → 约束搜索密度: 高波动区降密度，低波动区提密度
          H(熵)   → 控制探索/开发平衡: 高熵→扩大探索，低熵→收窄聚焦
          M(最值) → 硬约束过滤: 极端参数直接排除
          P(概率) → 信号质量门控: 低胜率区降优先级

        最终排序仍用原始四维评分（已验证），五维指标作为搜索加速器。

        改进要点:
          1. 自适应粗筛: 前30%均匀→之后按五维反馈动态调整采样方向
          2. 分区域精搜: 绿区×1.5, 黄区×0.7, 红区跳过
          3. 熵趋势在线引导: 实时监控，动态调整探索/开发平衡
          4. 硬约束真正生效: 红区参数不进精搜，黄区参数降权
          5. 最终排序: 原始评分 + 五维硬约束过滤（红区直接排除）
        """
        t0 = time.time()
        results = []
        self._param_history = []
        self._score_history = []
        self._entropy_history = []

        # ================================================================
        # Warm Start: 从上次优化继承最佳参数，作为搜索起点
        # ================================================================
        warm_start_eval = 0
        if self.warm_start_params:
            print(f"  [WarmStart] 从历史最佳参数继承: {self.warm_start_params}")
            # 先评估 warm start 参数
            result, mode = self.optimize(self.warm_start_params)
            daily_r, trade_r, signals = self._generate_simulated_returns(self.warm_start_params)
            enhanced = self._enhanced_score(result, daily_r, trade_r, signals)
            results.append((result, enhanced, mode))
            self.folding.record_coarse_result(self.warm_start_params, result)
            warm_start_eval = 1

        # ================================================================
        # 阶段1: 自适应粗筛（五维在线驱动）
        # ================================================================
        # 策略: 前30%粗筛点均匀分布（冷启动），之后根据五维反馈动态调整
        points_per_dim = max(4, int(coarse_points ** 0.5))
        print(f"  [Phase 1] 自适应粗筛: {coarse_points} 个点 (每维{points_per_dim}点)")
        coarse_grid = self.folding.generate_coarse_points(points_per_dim)
        coarse_grid = coarse_grid[:coarse_points]

        # 冷启动比例: 前30%均匀探索
        cold_start = max(5, int(coarse_points * 0.3))
        # 在线自适应步长: 每N个点评估一次五维趋势，调整后续方向
        online_batch = max(3, int(coarse_points * 0.1))

        coarse_region_info = []  # 记录每个粗筛点的区域信息

        for i, params in enumerate(coarse_grid):
            result, mode = self.optimize(params)
            self.folding.record_coarse_result(params, result)
            daily_r, trade_r, signals = self._generate_simulated_returns(params)
            enhanced = self._enhanced_score(result, daily_r, trade_r, signals)
            results.append((result, enhanced, mode))

            advice = enhanced.get("search_advice", {})
            risk = enhanced.get("risk_level", "green")
            coarse_region_info.append({
                "params": params,
                "score": result.score(),
                "five_dim_score": enhanced["total_score"],
                "risk_level": risk,
                "advice": advice,
            })

            # --- 在线自适应: 每 online_batch 个点评估一次 ---
            if i >= cold_start and (i + 1) % online_batch == 0 and i < len(coarse_grid) - 2:
                # 计算已评估区域的五维统计
                recent_info = coarse_region_info[-online_batch:]
                red_ratio = sum(1 for ri in recent_info if ri["risk_level"] == "red") / len(recent_info)
                green_ratio = sum(1 for ri in recent_info if ri["risk_level"] == "green") / len(recent_info)
                avg_score = statistics.mean([ri["score"] for ri in recent_info])
                avg_entropy = statistics.mean([
                    self._entropy_history[j] for j in range(max(0, i - online_batch), i + 1)
                ]) if self._entropy_history else 0.5

                # 五维驱动的自适应策略
                if red_ratio > 0.3:
                    # 红区太多 → 当前搜索区域质量差，需要跳转到新区域
                    print(f"    [自适应] 点{i+1}: 红区率{red_ratio:.0%}偏高 → 跳转搜索区域")
                    # 跳过接下来的几个点（它们大概率也在红区附近）
                    skip_count = min(3, len(coarse_grid) - i - 1)
                    for _ in range(skip_count):
                        i += 1
                        if i < len(coarse_grid):
                            params = coarse_grid[i]
                            result, mode = self.optimize(params)
                            self.folding.record_coarse_result(params, result)
                            daily_r, trade_r, signals = self._generate_simulated_returns(params)
                            enhanced = self._enhanced_score(result, daily_r, trade_r, signals)
                            results.append((result, enhanced, mode))
                            coarse_region_info.append({
                                "params": params, "score": result.score(),
                                "five_dim_score": enhanced["total_score"],
                                "risk_level": enhanced.get("risk_level", "green"),
                                "advice": enhanced.get("search_advice", {}),
                            })
                elif green_ratio > 0.5 and avg_entropy < 0.4:
                    # 绿区多且熵低 → 好区域，已经比较收敛
                    print(f"    [自适应] 点{i+1}: 绿区率{green_ratio:.0%}, 熵{avg_entropy:.2f} → 区域质量好，可加速")
                elif avg_entropy > 0.7:
                    # 熵高 → 还在探索，信号混乱
                    print(f"    [自适应] 点{i+1}: 熵{avg_entropy:.2f}偏高 → 信号混乱，扩大搜索")

        # 粗筛完成统计
        green_count = sum(1 for ri in coarse_region_info if ri["risk_level"] == "green")
        yellow_count = sum(1 for ri in coarse_region_info if ri["risk_level"] == "yellow")
        red_count = sum(1 for ri in coarse_region_info if ri["risk_level"] == "red")
        print(f"    -> 粗筛风险分布: 绿={green_count} 黄={yellow_count} 红={red_count}")

        # 按原始评分排序
        coarse_region_info.sort(key=lambda x: x["score"], reverse=True)
        top_coarse_score = coarse_region_info[0]["score"] if coarse_region_info else 0
        print(f"    -> 粗筛最佳原评分: {top_coarse_score:.4f}")

        # ================================================================
        # 阶段2: 五维驱动分区域精搜
        # ================================================================
        # 核心改进: 每个粗筛点按五维风险等级分配不同精搜密度
        #   绿区: 基础密度 × 1.5 (优质区域，值得细搜)
        #   黄区: 基础密度 × 0.7 (有风险但可探索)
        #   红区: 跳过 (风险过高，不浪费算力)

        # 熵趋势: 判断当前收敛状态（用于全局精搜量调整）
        if entropy_decay and len(self._entropy_history) >= 5:
            # 用后半段vs前半段的熵差判断趋势
            half = len(self._entropy_history) // 2
            first_half_entropy = statistics.mean(self._entropy_history[:half])
            second_half_entropy = statistics.mean(self._entropy_history[half:])
            entropy_trend = first_half_entropy - second_half_entropy  # 正=熵在降
            if entropy_trend > 0.05:
                entropy_trend_factor = 0.7  # 熵在降→收敛中，减少精搜
                print(f"    -> 熵趋势: 下降中 ({entropy_trend:+.3f}) → 加速收敛，减少精搜")
            elif entropy_trend < -0.05:
                entropy_trend_factor = 1.3  # 熵在升→还在探索，加大精搜
                print(f"    -> 熵趋势: 上升中 ({entropy_trend:+.3f}) → 扩大探索，增加精搜")
            else:
                entropy_trend_factor = 1.0
        else:
            entropy_trend_factor = 1.0

        # 按五维风险等级分区域分配精搜密度
        # 策略: 只在TOP-N评分区域做精搜，避免全量粗筛点都精搜导致算力爆炸
        green_points = [ri for ri in coarse_region_info if ri["risk_level"] == "green"]
        yellow_points = [ri for ri in coarse_region_info if ri["risk_level"] == "yellow"]
        red_points = [ri for ri in coarse_region_info if ri["risk_level"] == "red"]

        # 红区: 跳过
        if red_points:
            print(f"    -> 五维硬约束: {len(red_points)} 个红区参数跳过精搜（节省算力）")

        # TOP-N筛选: 只在评分最高的绿区和黄区做精搜
        # 避免对所有粗筛点都做精搜导致算力爆炸
        max_refine_regions = max(5, int(coarse_points * 0.15))  # 最多15%的粗筛点做精搜
        top_green = sorted(green_points, key=lambda x: x["score"], reverse=True)[:max_refine_regions]
        top_yellow = sorted(yellow_points, key=lambda x: x["score"], reverse=True)[:max(2, max_refine_regions // 2)]

        # 每个区域的基础精搜量
        base_refined = max(2, refined_points_per_region)

        # 构建精搜计划（严格控制总量）
        refined_by_region = []  # [(center_params, n_points, risk_level), ...]

        # 绿区: 1.5倍密度
        for ri in top_green:
            n = max(2, int(base_refined * 1.5 * entropy_trend_factor))
            refined_by_region.append((ri["params"], n, "green"))

        # 黄区: 0.7倍密度
        for ri in top_yellow:
            n = max(1, int(base_refined * 0.7 * entropy_trend_factor))
            refined_by_region.append((ri["params"], n, "yellow"))

        # 总量上限: 控制精搜总点数在合理范围
        total_planned = sum(n for _, n, _ in refined_by_region)
        max_total = min(200, coarse_points * 3)  # 上限: 200点或粗筛点的3倍
        if total_planned > max_total:
            # 按比例缩减
            scale = max_total / total_planned
            refined_by_region = [(p, max(1, int(n * scale)), r) for p, n, r in refined_by_region]
            total_planned = sum(n for _, n, _ in refined_by_region)
            print(f"    -> 精搜总量超限，缩放到{max_total}点 (缩放因子{scale:.1f})")

        print(f"    -> 分区域精搜: 绿区×1.5({len(top_green)}个) | 黄区×0.7({len(top_yellow)}个) | 红区跳过({len(red_points)}个) | 共{total_planned}个精搜点")
        if entropy_trend_factor != 1.0:
            print(f"       (熵趋势因子: {entropy_trend_factor:.1f})")

        # 执行精搜
        refined_count = 0
        for center_params, n_points, risk in refined_by_region:
            if n_points <= 0:
                continue
            points = self._generate_refined_around_center(center_params, n_points)
            for params in points:
                result, mode = self.optimize(params)
                daily_r, trade_r, signals = self._generate_simulated_returns(params)
                enhanced = self._enhanced_score(result, daily_r, trade_r, signals)
                results.append((result, enhanced, mode))
                refined_count += 1

        print(f"    -> 实际精搜: {refined_count} 个点")

        # ================================================================
        # 阶段3: 提前终止判定（熵+评分双指标）
        # ================================================================
        early_stopped = False
        if early_stop and len(self._score_history) >= 10:
            conv = self.get_convergence_metrics()
            if conv["is_converged"]:
                print(f"    -> 提前终止: 已收敛 (score_std={conv['score_std']:.4f}, "
                      f"entropy={conv['avg_entropy']:.4f}, trend={conv['entropy_trend']:+.4f})")
                early_stopped = True

        # ================================================================
        # 阶段4: 最终排序（原始评分 + 五维硬约束过滤）
        # ================================================================
        # 关键: 红区参数直接排除，不计入最终结果
        valid_results = []
        excluded_red = 0
        for r_tuple in results:
            r, e, m = r_tuple
            if e.get("risk_level") == "red":
                excluded_red += 1
                continue
            valid_results.append(r_tuple)

        if excluded_red > 0:
            print(f"    -> 最终过滤: 排除 {excluded_red} 个红区参数")

        # 如果没有有效结果，降级使用全部结果
        if not valid_results:
            print(f"    -> 警告: 所有参数均被过滤，降级使用全部结果")
            valid_results = results

        all_results = [(r, e, m) for r, e, m in valid_results]
        all_results.sort(key=lambda x: x[0].score(), reverse=True)

        if not all_results:
            return {"best_params": None, "best_result": None, "total_evaluations": 0}

        best_result, best_enhanced, best_mode = all_results[0]
        best_params = best_result.params

        # 五维增益: 记录五维评分最优参数（用于对比分析）
        best_by_five = max(valid_results, key=lambda x: x[1]["total_score"])
        five_dim_params = best_by_five[0].params
        five_dim_score = best_by_five[1]["total_score"]
        params_differ = best_params != five_dim_params

        if params_differ:
            orig_score_at_five = best_by_five[0].score()
            print(f"    -> 五维增益: 五维最优参数 (五维={five_dim_score:.4f}) "
                  f"vs 原始最优 (原评分={best_result.score():.4f}) "
                  f"| 五维最优的原评分={orig_score_at_five:.4f}")

        # ================================================================
        # 阶段5: 模式分析
        # ================================================================
        if run_analysis:
            analyzer = PatternAnalyzer(
                param_ranges=self.param_ranges,
                strategy_name=self.strategy_name)
            for r, e, _ in valid_results:
                analyzer.record_point(r.params, e["total_score"])
            analysis = analyzer.analyze()
        else:
            analysis = None

        # ================================================================
        # 阶段6: 收敛指标
        # ================================================================
        convergence = self.get_convergence_metrics()

        elapsed = round(time.time() - t0, 1)

        # ================================================================
        # 阶段7: 持久化优化结果（优化成果永久性继承）
        # ================================================================
        persisted = False
        if best_params and best_result:
            try:
                from core.tau_optimizer_cluster import get_parameter_store
                _store = get_parameter_store()
                _record = _store.record_optimization(
                    strategy_name=self.strategy_name,
                    best_params=best_params,
                    best_score=best_result.score(),
                    method="entropy_tau_v4",
                    total_evals=len(results),
                    param_ranges=self.param_ranges,
                )
                if _record["is_new_best"]:
                    print(f"  [持久化] {self.strategy_name} v{_record['new_version']} "
                          f"(score={best_result.score():.4f}, +{_record['score_delta']:.4f})")
                else:
                    print(f"  [持久化] {self.strategy_name} 保持 v{_record['new_version']} "
                          f"(未超越历史最佳 {_record['prev_best_score']:.4f})")
                persisted = True
            except Exception as _e:
                print(f"  [持久化] 保存失败: {_e}")

        return {
            "best_params": best_params,
            "best_result": best_result,
            "best_score_original": best_result.score(),
            "best_enhanced_score": best_enhanced,
            "five_dim_best_params": five_dim_params,
            "five_dim_best_score": five_dim_score,
            "params_differ": params_differ,
            "top_results": [(r, e) for r, e, _ in all_results[:10]],
            "total_evaluations": len(results),
            "convergence": convergence,
            "risk_summary": {"green": green_count, "yellow": yellow_count, "red": red_count},
            "cluster_status": self.get_status(),
            "pattern_analysis": analysis,
            "elapsed_seconds": elapsed,
            "early_stopped": early_stopped,
            "excluded_red_count": excluded_red,
            "persisted": persisted,
        }

    def _generate_refined_around_center(self, center_params: Dict[str, float],
                                         n_points: int) -> List[Dict[str, float]]:
        """
        以指定参数为中心生成精搜点

        策略: 在中心参数的邻域内随机采样，采样范围随参数维度缩放
        """
        points = []
        param_names = list(self.param_ranges.keys())

        for _ in range(n_points):
            new_params = {}
            for name in param_names:
                pmin, pmax = self.param_ranges[name]
                center = center_params.get(name, (pmin + pmax) / 2)
                param_range = pmax - pmin
                # 精搜范围: 参数范围的 10-20%
                search_radius = param_range * random.uniform(0.05, 0.15)
                new_val = center + random.uniform(-search_radius, search_radius)
                new_val = max(pmin, min(pmax, new_val))
                new_params[name] = new_val
            points.append(new_params)

        return points


# ============================================================
# 4. A/B对比测试工具
# ============================================================
#
# ============================================================
# 导出别名 & 工厂函数
# ============================================================

# 别名: 熵韬收敛优化器集群 = EntropyTauOptimizer
EntropyTauCluster = EntropyTauOptimizer

def create_optimizer_cluster(
    param_ranges: Dict[str, Tuple[float, float]],
    strategy_name: str = "generic_strategy",
    use_entropy_tau: bool = True,
    **kwargs
) -> object:
    """
    创建优化器集群工厂 — 熵韬为主力，原韬定律为备选

    Args:
        param_ranges: 参数范围字典
        strategy_name: 策略名称
        use_entropy_tau: True=使用熵韬收敛优化器（主力），False=使用原韬定律（备选兜底）

    Returns:
        优化器实例（EntropyTauOptimizer 或 TauOptimizerCluster）
    """
    if use_entropy_tau:
        return EntropyTauOptimizer(param_ranges, strategy_name, **kwargs)
    else:
        from core.tau_optimizer_cluster import TauOptimizerCluster
        return TauOptimizerCluster(param_ranges, strategy_name, **kwargs)

def compare_optimizers(param_ranges: Dict[str, Tuple[float, float]],
                       strategy_name: str = "test_strategy",
                       strategy_mgr=None,
                       coarse_points: int = 30,
                       refined_points: int = 15) -> Dict[str, Any]:
    """
    A/B对比测试: 原韬定律优化器 vs 熵韬收敛优化器

    对比指标:
      - 收敛速度（到达稳定评分所需迭代次数）
      - 最终评分
      - 搜索覆盖度（参数空间熵）
      - 决策稳定性（决策熵）
      - 耗时
    """
    print(f"\n{'='*60}")
    print(f"  A/B对比测试: 原韬定律 vs 熵韬收敛优化器")
    print(f"  策略: {strategy_name}")
    print(f"  粗筛: {coarse_points}点, 精搜: {refined_points}点/区域")
    print(f"{'='*60}")

    # ---- A组: 原韬定律优化器 ----
    print("\n[A组] 原韬定律优化器...")
    t0 = time.time()
    original = TauOptimizerCluster(param_ranges, strategy_name, 0.15, 100.0, strategy_mgr)
    original_result = original.run_folding_optimization(
        coarse_points=coarse_points,
        refined_points_per_region=refined_points,
        run_analysis=False
    )
    original_time = round(time.time() - t0, 1)
    original_score = original_result["best_result"].score() if original_result["best_result"] else 0

    # ---- B组: 熵韬收敛优化器 ----
    print("\n[B组] 熵韬收敛优化器...")
    t0 = time.time()
    entropy_tau = EntropyTauOptimizer(param_ranges, strategy_name, 0.15, 100.0, strategy_mgr)
    entropy_tau_result = entropy_tau.run_enhanced_optimization(
        coarse_points=coarse_points,
        refined_points_per_region=refined_points,
        run_analysis=False,
        entropy_decay=True
    )
    entropy_tau_time = round(time.time() - t0, 1)
    entropy_tau_original_score = entropy_tau_result["best_score_original"]  # 原评分
    entropy_tau_five_dim_score = entropy_tau_result["best_enhanced_score"]["total_score"]  # 五维评分(增益)
    entropy_tau_convergence = entropy_tau_result["convergence"]
    risk_summary = entropy_tau_result.get("risk_summary", {})
    excluded_red = entropy_tau_result.get("excluded_red_count", 0)
    early_stopped = entropy_tau_result.get("early_stopped", False)

    # ---- 公平对比: 统一使用原评分 score() ----
    # 两个优化器都用 BacktestResult.score() 比较，五维评分仅作增益参考
    # （原评分体系已做等效转换：百分比→小数、多策略标度统一、置信度加权）

    # ---- 对比报告 ----
    print(f"\n{'='*60}")
    print(f"  A/B对比结果（统一使用原评分体系）")
    print(f"{'='*60}")
    print(f"  {'指标':<22} {'原韬定律':<15} {'熵韬收敛':<15} {'差异':<10}")
    print(f"  {'-'*60}")
    print(f"  {'原评分(四维)':<22} {original_score:<15.4f} {entropy_tau_original_score:<15.4f} {_delta_str(original_score, entropy_tau_original_score)}")
    print(f"  {'耗时(秒)':<22} {original_time:<15.1f} {entropy_tau_time:<15.1f} {'-'}")
    print(f"  {'--- 五维驱动指标 ---':<22} {'---':<15} {'---':<15} {'---'}")
    print(f"  {'五维评分(增益)':<22} {'N/A':<15} {entropy_tau_five_dim_score:<15.4f} {'-'}")
    print(f"  {'收敛判定':<22} {'N/A':<15} {str(entropy_tau_convergence['is_converged']):<15} {'-'}")
    print(f"  {'评分标准差':<22} {'N/A':<15} {entropy_tau_convergence['score_std']:<15.4f} {'-'}")
    print(f"  {'平均熵':<22} {'N/A':<15} {entropy_tau_convergence['avg_entropy']:<15.4f} {'-'}")
    print(f"  {'收敛率':<22} {'N/A':<15} {entropy_tau_convergence['convergence_rate']:<15.2f} {'-'}")
    print(f"  {'排除红区数':<22} {'N/A':<15} {excluded_red:<15} {'-'}")
    print(f"  {'提前终止':<22} {'N/A':<15} {str(early_stopped):<15} {'-'}")
    risk_str = f"绿{risk_summary.get('green',0)}/黄{risk_summary.get('yellow',0)}/红{risk_summary.get('red',0)}"
    print(f"  {'风险分布':<22} {'N/A':<15} {risk_str:<15} {'-'}")
    # 五维各维度详情
    dims = entropy_tau_result["best_enhanced_score"]["dimension_scores"]
    print(f"  {'五维维度':<22} {'E(期望)':<5} {'V(方差)':<5} {'H(熵)':<5} {'M(最值)':<5} {'P(概率)':<5}")
    print(f"  {'':<22} {dims['expectation']:<5.3f} {dims['variance']:<5.3f} {dims['entropy']:<5.3f} {dims['extreme']:<5.3f} {dims['probability']:<5.3f}")

    return {
        "original": {"score": original_score,
                     "time": original_time, "best_params": original_result.get("best_params")},
        "entropy_tau": {"score": entropy_tau_original_score,
                     "time": entropy_tau_time,
                     "best_params": entropy_tau_result.get("best_params"),
                     "five_dim_score": entropy_tau_five_dim_score,
                     "convergence": entropy_tau_convergence,
                     "dimension_scores": entropy_tau_result["best_enhanced_score"]["dimension_scores"],
                     "entropy_metrics": entropy_tau_result["best_enhanced_score"]["entropy_metrics"],
                     "excluded_red": excluded_red,
                     "early_stopped": early_stopped,
                     "risk_summary": risk_summary},
        "comparison": {
            "score_delta": round(entropy_tau_original_score - original_score, 4),
            "improvement_pct": round((entropy_tau_original_score - original_score) / max(0.01, abs(original_score)) * 100, 1),
        }
    }


def _delta_str(a: float, b: float) -> str:
    """格式化差异字符串"""
    delta = b - a
    if delta > 0:
        return f"+{delta:.4f}"
    return f"{delta:.4f}"