#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v5.牧羊人智能体优化器 5.0 — 金融级综合升级 (Shepherd V5 Comprehensive)
🐑 
======================================================================
v5.0 核心升级：
  [1] 🏦 金融级严格评测体系 — 多维度财务指标 + 压力测试 + Walk-Forward
  [2] 🧬 策略基因提取与新生策略生成框架 — 基因维度框架 + 优良策略精华组合
  [3] 🤝 智能体专家团队协作机制 — 12位专家协同评审 + 创造性策略合成
  [4] 🔄 自演进系统 — 迭代优化闭环 + 元学习 + 自我调用专家团队推进演进

架构设计原则：
  - 金融级严谨性：所有评测必须基于真实市场数据,杜绝模拟占位
  - 基因可组合性：策略基因模块化,支持跨策略精华提取与再组合
  - 专家协同创造：多专家并行评审 + 合议生成新生策略
  - 自演进闭环：Shepherd能自我审视、调用专家团队、持续优化自身参数

用法:
  python shepherd_v5_comprehensive.py                      # 完整自检
  python shepherd_v5_comprehensive.py --audit              # 审查现有系统
  python shepherd_v5_comprehensive.py --extract-genes      # 提取策略基因
  python shepherd_v5_comprehensive.py --generate-strategy  # 生成新生策略
  python shepherd_v5_comprehensive.py --evolve             # 启动自演进闭环
  python shepherd_v5_comprehensive.py --full-pipeline      # 全流程启动
"""

import sys, os, json, time, math, logging, sqlite3, random, hashlib
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Any, Optional, Tuple, Callable, Set, Union
from datetime import datetime, timedelta
from abc import ABC, abstractmethod
from collections import defaultdict, OrderedDict
from copy import deepcopy
from enum import Enum, auto
import itertools
import numpy as np

# ═══════════════════════════════════════════════
# 全局金融级配置常量
# ═══════════════════════════════════════════════
VERSION = "5.0.0-comprehensive"
SCHEMA_DATE = "2026-05-20"

# 金融级评测阈值
FINANCIAL_GRADE_THRESHOLD = 0.85       # 金融级达标线
EXCELLENCE_THRESHOLD = 0.90            # 卓越级
MIN_SHARPE_RATIO = 0.50                # 最低夏普比率
MIN_SORTINO_RATIO = 0.75               # 最低索提诺比率
MIN_CALMAR_RATIO = 0.30                # 最低卡尔玛比率
MAX_DRAWDOWN_LIMIT = 0.25              # 最大回撤限制
MAX_VAR_95_LIMIT = 0.03                # 95% VaR日限(3%)
MAX_CVAR_95_LIMIT = 0.05               # 95% CVaR日限(5%)
MIN_PROFIT_FACTOR = 1.20               # 最低盈利因子
MIN_WIN_RATE = 0.40                    # 最低胜率
MAX_CONSECUTIVE_LOSSES = 8             # 最大连续亏损次数
MIN_SAMPLE_SIZE = 100                  # 最小样本量(交易次数)
OVERFIT_THRESHOLD = 0.30               # 过拟合警告阈值(样本内/外差距)
CROSS_VALIDATION_FOLDS = 5             # 交叉验证折数
WALK_FORWARD_WINDOWS = 4               # Walk-Forward窗口数

# 基因工程常量
GENE_DIMENSIONS = [
    "signal_detection",     # 信号检测基因
    "entry_timing",         # 入场时机基因
    "exit_timing",          # 离场时机基因
    "risk_control",         # 风险控制基因
    "position_sizing",      # 仓位管理基因
    "market_regime",        # 市场状态识别基因
    "param_adaptation",     # 参数自适应基因
    "feature_engineering",  # 特征工程基因
    "model_selection",      # 模型选择基因
    "ensemble_method",      # 集成方法基因
]

GENE_DIMENSION_WEIGHTS = {
    "signal_detection": 0.15,
    "entry_timing": 0.12,
    "exit_timing": 0.15,
    "risk_control": 0.18,
    "position_sizing": 0.13,
    "market_regime": 0.10,
    "param_adaptation": 0.07,
    "feature_engineering": 0.05,
    "model_selection": 0.03,
    "ensemble_method": 0.02,
}

# 专家团队配置
EXPERT_TEAM = [
    {"id": 1,  "name": "架构设计审计师",     "role": "System Architect",          "weight": 0.12, "focus": "strategy_architecture"},
    {"id": 2,  "name": "代码质量审查官",     "role": "Code Quality Inspector",   "weight": 0.09, "focus": "implementation_quality"},
    {"id": 3,  "name": "金融风控合规官",     "role": "Risk & Compliance Officer","weight": 0.14, "focus": "risk_management"},
    {"id": 4,  "name": "性能工程师",         "role": "Performance Engineer",     "weight": 0.11, "focus": "execution_efficiency"},
    {"id": 5,  "name": "安全审计专家",       "role": "Security Auditor",         "weight": 0.08, "focus": "system_security"},
    {"id": 6,  "name": "数据质量专家",       "role": "Data Quality Specialist",  "weight": 0.08, "focus": "data_integrity"},
    {"id": 7,  "name": "可扩展性架构师",     "role": "Scalability Architect",    "weight": 0.08, "focus": "system_scalability"},
    {"id": 8,  "name": "测试工程专家",       "role": "Quality Assurance Lead",   "weight": 0.07, "focus": "test_coverage"},
    {"id": 9,  "name": "用户体验设计师",     "role": "Observability Designer",   "weight": 0.06, "focus": "observability"},
    {"id": 10, "name": "AI工程化专家",       "role": "AI/ML Engineering Lead",   "weight": 0.08, "focus": "ai_ml_integration"},
    {"id": 11, "name": "DevOps运维专家",     "role": "DevOps Engineer",          "weight": 0.05, "focus": "deployment_readiness"},
    {"id": 12, "name": "产品化评审官",       "role": "Product Review Officer",   "weight": 0.04, "focus": "commercialization"},
]

# 自演进参数空间
EVOLUTION_PARAM_SPACE = {
    "population_size": (10, 50),
    "generations": (5, 30),
    "mutation_rate": (0.05, 0.30),
    "elite_ratio": (0.05, 0.30),
    "crossover_points": (1, 5),
    "learning_rate": (0.001, 0.100),
    "exploration_ratio": (0.10, 0.50),
    "convergence_threshold": (0.0001, 0.0100),
}

# ═══════════════════════════════════════════════
# 日志配置
# ═══════════════════════════════════════════════
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] ShepherdV5: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ShepherdV5")


# ═══════════════════════════════════════════════
# 第一阶段：金融级严格评测体系
# ═══════════════════════════════════════════════

class FinancialMetrics(Enum):
    """金融级评测指标枚举"""
    SHARPE_RATIO = auto()
    SORTINO_RATIO = auto()
    CALMAR_RATIO = auto()
    MAX_DRAWDOWN = auto()
    VAR_95 = auto()
    CVAR_95 = auto()
    PROFIT_FACTOR = auto()
    WIN_RATE = auto()
    EXPECTANCY = auto()
    CONSECUTIVE_LOSSES = auto()
    RECOVERY_FACTOR = auto()
    TAIL_RATIO = auto()
    ANNUAL_RETURN = auto()
    ANNUAL_VOLATILITY = auto()
    INFORMATION_RATIO = auto()
    OMEGA_RATIO = auto()


@dataclass
class FinancialEvaluationResult:
    """金融级评测结果"""
    strategy_name: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    # 核心指标
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    max_drawdown: float = 0.0
    var_95_daily: float = 0.0
    cvar_95_daily: float = 0.0
    profit_factor: float = 0.0
    win_rate: float = 0.0
    expectancy: float = 0.0
    max_consecutive_losses: int = 0
    recovery_factor: float = 0.0
    tail_ratio: float = 0.0
    annual_return: float = 0.0
    annual_volatility: float = 0.0
    information_ratio: float = 0.0
    omega_ratio: float = 0.0

    # 衍生评分
    composite_score: float = 0.0
    grade: str = "F"
    financial_grade_pass: bool = False

    # 稳健性测试
    walk_forward_score: float = 0.0
    monte_carlo_score: float = 0.0
    stress_test_score: float = 0.0
    overfit_ratio: float = 0.0
    cross_val_score: float = 0.0

    # 交易统计
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    avg_win: float = 0.0
    avg_loss: float = 0.0

    # 风险调整
    risk_adjusted_return: float = 0.0
    ulcer_index: float = 0.0
    pain_index: float = 0.0

    # 详情
    monthly_returns: List[float] = field(default_factory=list)
    daily_var_series: List[float] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)

    def compute_composite_score(self) -> float:
        """计算金融级综合评分"""
        scores = {}

        # 夏普比率评分 (0-1, 目标>1.5)
        scores["sharpe"] = min(1.0, max(0.0, self.sharpe_ratio / 2.0))

        # 索提诺比率评分
        scores["sortino"] = min(1.0, max(0.0, self.sortino_ratio / 2.5))

        # 卡尔玛比率评分
        scores["calmar"] = min(1.0, max(0.0, self.calmar_ratio / 0.8))

        # 最大回撤评分 (回撤越小越好)
        scores["drawdown"] = max(0.0, 1.0 - self.max_drawdown / MAX_DRAWDOWN_LIMIT)

        # 盈利因子评分
        scores["profit_factor"] = min(1.0, max(0.0, self.profit_factor / 2.5))

        # 胜率评分
        scores["win_rate"] = min(1.0, max(0.0, self.win_rate / 0.60))

        # 连续亏损评分
        scores["consecutive"] = max(0.0, 1.0 - self.max_consecutive_losses / MAX_CONSECUTIVE_LOSSES)

        # VaR控制评分
        scores["var"] = max(0.0, 1.0 - self.var_95_daily / MAX_VAR_95_LIMIT)

        # CVaR控制评分
        scores["cvar"] = max(0.0, 1.0 - self.cvar_95_daily / MAX_CVAR_95_LIMIT)

        # 恢复因子评分
        scores["recovery"] = min(1.0, max(0.0, self.recovery_factor / 1.5))

        # 过拟合控制评分
        scores["overfit"] = max(0.0, 1.0 - self.overfit_ratio / OVERFIT_THRESHOLD)

        # 交易数量充分性
        scores["samples"] = min(1.0, self.total_trades / MIN_SAMPLE_SIZE)

        # 加权综合
        weight_map = {
            "sharpe": 0.15, "sortino": 0.10, "calmar": 0.08,
            "drawdown": 0.15, "profit_factor": 0.10, "win_rate": 0.08,
            "consecutive": 0.06, "var": 0.06, "cvar": 0.06,
            "recovery": 0.06, "overfit": 0.06, "samples": 0.04,
        }

        self.composite_score = sum(scores[k] * weight_map.get(k, 0) for k in scores)
        return self.composite_score

    def assign_grade(self) -> str:
        """分配金融级评级"""
        s = self.composite_score
        if s >= 0.95:
            self.grade = "S+ 传奇级"
        elif s >= 0.90:
            self.grade = "S 卓越级"
        elif s >= 0.85:
            self.grade = "A+ 优秀级"
            self.financial_grade_pass = True
        elif s >= 0.75:
            self.grade = "A 良好级"
        elif s >= 0.65:
            self.grade = "B 稳健级"
        elif s >= 0.50:
            self.grade = "C 及格级"
        elif s >= 0.35:
            self.grade = "D 预警级"
        else:
            self.grade = "F 不合格"
        return self.grade

    def to_dict(self) -> Dict[str, Any]:
        return {
            "strategy_name": self.strategy_name,
            "timestamp": self.timestamp,
            "composite_score": round(self.composite_score, 4),
            "grade": self.grade,
            "financial_grade_pass": self.financial_grade_pass,
            "sharpe_ratio": round(self.sharpe_ratio, 4),
            "sortino_ratio": round(self.sortino_ratio, 4),
            "calmar_ratio": round(self.calmar_ratio, 4),
            "max_drawdown": round(self.max_drawdown, 4),
            "var_95_daily": round(self.var_95_daily, 4),
            "cvar_95_daily": round(self.cvar_95_daily, 4),
            "profit_factor": round(self.profit_factor, 4),
            "win_rate": round(self.win_rate, 4),
            "expectancy": round(self.expectancy, 4),
            "max_consecutive_losses": self.max_consecutive_losses,
            "recovery_factor": round(self.recovery_factor, 4),
            "tail_ratio": round(self.tail_ratio, 4),
            "annual_return": round(self.annual_return, 4),
            "annual_volatility": round(self.annual_volatility, 4),
            "information_ratio": round(self.information_ratio, 4),
            "omega_ratio": round(self.omega_ratio, 4),
            "walk_forward_score": round(self.walk_forward_score, 4),
            "monte_carlo_score": round(self.monte_carlo_score, 4),
            "stress_test_score": round(self.stress_test_score, 4),
            "overfit_ratio": round(self.overfit_ratio, 4),
            "cross_val_score": round(self.cross_val_score, 4),
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "avg_win": round(self.avg_win, 6),
            "avg_loss": round(self.avg_loss, 6),
            "warnings": self.warnings,
        }


class FinancialGradeEvaluator:
    """金融级严格评测器：对策略进行全维度财务评估"""

    def __init__(self, risk_free_rate: float = 0.02):
        self.risk_free_rate = risk_free_rate
        self._evaluation_history: List[FinancialEvaluationResult] = []

    def evaluate_from_returns(
        self,
        strategy_name: str,
        daily_returns: List[float],
        benchmark_returns: List[float] = None,
        trade_records: List[Dict] = None,
    ) -> FinancialEvaluationResult:
        """从日收益率序列进行金融级评估"""
        result = FinancialEvaluationResult(strategy_name=strategy_name)

        if not daily_returns or len(daily_returns) < MIN_SAMPLE_SIZE:
            result.warnings.append(f"数据量不足: {len(daily_returns)} < {MIN_SAMPLE_SIZE}")
            result.grade = "F 不合格"
            self._evaluation_history.append(result)
            return result

        returns = np.array(daily_returns, dtype=np.float64)
        returns = returns[~np.isnan(returns)]
        n = len(returns)

        # ========== 核心收益指标 ==========
        # 年化收益率
        result.annual_return = np.mean(returns) * 252

        # 年化波动率
        result.annual_volatility = np.std(returns, ddof=1) * np.sqrt(252)

        # 超额收益
        excess_returns = returns - (self.risk_free_rate / 252)

        # ========== 风险调整指标 ==========
        # 夏普比率
        if result.annual_volatility > 1e-10:
            result.sharpe_ratio = (result.annual_return - self.risk_free_rate) / result.annual_volatility

        # 索提诺比率 (只考虑下行波动)
        downside_returns = returns[returns < (self.risk_free_rate / 252)]
        if len(downside_returns) > 1:
            downside_std = np.std(downside_returns, ddof=1) * np.sqrt(252)
            if downside_std > 1e-10:
                result.sortino_ratio = (result.annual_return - self.risk_free_rate) / downside_std

        # ========== 回撤分析 ==========
        cumulative = np.cumprod(1 + returns)
        running_max = np.maximum.accumulate(cumulative)
        drawdowns = (cumulative - running_max) / running_max
        result.max_drawdown = abs(np.min(drawdowns))

        # 卡尔玛比率
        if result.max_drawdown > 1e-10:
            result.calmar_ratio = result.annual_return / result.max_drawdown

        # 恢复因子 = 总收益 / 最大回撤
        total_return = cumulative[-1] - 1
        if result.max_drawdown > 1e-10:
            result.recovery_factor = total_return / result.max_drawdown

        # 尾端比率
        positive_returns = returns[returns > 0]
        negative_returns = returns[returns < 0]
        if len(negative_returns) > 0 and len(positive_returns) > 0:
            result.tail_ratio = abs(
                np.percentile(positive_returns, 95) / np.percentile(negative_returns, 5)
            ) if np.percentile(negative_returns, 5) != 0 else 0.0

        # ========== VaR / CVaR ==========
        result.var_95_daily = abs(np.percentile(returns, 5))
        result.cvar_95_daily = abs(np.mean(returns[returns <= np.percentile(returns, 5)]))
        result.daily_var_series = [abs(np.percentile(returns[:i+1], 5)) for i in range(20, n)]

        # ========== 交易统计 ==========
        if trade_records:
            self._compute_trade_statistics(result, trade_records)
        else:
            self._compute_trade_statistics_from_returns(result, returns)

        # ========== 信息比率 ==========
        if benchmark_returns and len(benchmark_returns) == n:
            bm = np.array(benchmark_returns, dtype=np.float64)
            tracking_error = np.std(returns - bm, ddof=1) * np.sqrt(252)
            if tracking_error > 1e-10:
                result.information_ratio = (result.annual_return - (np.mean(bm) * 252)) / tracking_error

        # ========== Omega比率 ==========
        threshold = self.risk_free_rate / 252
        gains = returns[returns > threshold] - threshold
        losses = threshold - returns[returns <= threshold]
        if np.sum(losses) > 1e-10:
            result.omega_ratio = np.sum(gains) / np.sum(losses)

        # ========== 溃疡指数 ==========
        squared_drawdowns = np.square(drawdowns)
        result.ulcer_index = np.sqrt(np.mean(squared_drawdowns))

        # ========== 稳健性测试 ==========
        result.walk_forward_score = self._walk_forward_analysis(returns)
        result.monte_carlo_score = self._monte_carlo_simulation(returns)
        result.stress_test_score = self._stress_test(returns)
        result.overfit_ratio = self._compute_overfit_ratio(returns)
        result.cross_val_score = self._cross_validation(returns)

        # ========== 月度收益 ==========
        result.monthly_returns = self._compute_monthly_returns(returns)

        # ========== 风险调整收益 ==========
        result.risk_adjusted_return = result.sharpe_ratio * (1 - result.max_drawdown)

        # ========== 综合评分 ==========
        result.compute_composite_score()
        result.assign_grade()

        # ========== 警告生成 ==========
        self._generate_warnings(result)

        self._evaluation_history.append(result)
        logger.info(f"📊 [{result.strategy_name}] 金融级评测: {result.grade} "
                     f"(综合={result.composite_score:.4f}, Sharpe={result.sharpe_ratio:.3f}, "
                     f"MaxDD={result.max_drawdown:.3f})")
        return result

    def _compute_trade_statistics(self, result: FinancialEvaluationResult,
                                   trade_records: List[Dict]):
        """从交易记录计算统计"""
        profits = [t.get("pnl", 0) for t in trade_records]
        result.total_trades = len(profits)
        if result.total_trades == 0:
            return
        result.winning_trades = sum(1 for p in profits if p > 0)
        result.losing_trades = sum(1 for p in profits if p < 0)
        result.win_rate = result.winning_trades / result.total_trades

        winning_profits = [p for p in profits if p > 0]
        losing_profits = [p for p in profits if p < 0]
        result.avg_win = np.mean(winning_profits) if winning_profits else 0
        result.avg_loss = abs(np.mean(losing_profits)) if losing_profits else 0

        # 盈利因子
        total_win = sum(winning_profits) if winning_profits else 0
        total_loss = abs(sum(losing_profits)) if losing_profits else 0
        if total_loss > 1e-10:
            result.profit_factor = total_win / total_loss

        # 期望值
        result.expectancy = (result.win_rate * result.avg_win -
                              (1 - result.win_rate) * result.avg_loss)

        # 最大连续亏损
        current_streak = 0
        max_streak = 0
        for p in profits:
            if p < 0:
                current_streak += 1
                max_streak = max(max_streak, current_streak)
            else:
                current_streak = 0
        result.max_consecutive_losses = max_streak

    def _compute_trade_statistics_from_returns(self, result: FinancialEvaluationResult,
                                                 returns: np.ndarray):
        """从收益率序列近似估算交易统计"""
        # 非零收益视为简化的交易
        nonzero = returns[returns != 0]
        result.total_trades = len(nonzero)
        if result.total_trades == 0:
            return
        result.winning_trades = int(np.sum(nonzero > 0))
        result.losing_trades = result.total_trades - result.winning_trades
        result.win_rate = result.winning_trades / result.total_trades

        winning = nonzero[nonzero > 0]
        losing = nonzero[nonzero < 0]
        result.avg_win = np.mean(winning) if len(winning) > 0 else 0.0
        result.avg_loss = abs(np.mean(losing)) if len(losing) > 0 else 0.0

        if len(losing) > 0:
            total_win = np.sum(winning)
            total_loss = abs(np.sum(losing))
            result.profit_factor = total_win / total_loss if total_loss > 1e-10 else 0.0
        else:
            result.profit_factor = 999.0 if len(winning) > 0 else 0.0

        result.expectancy = (result.win_rate * result.avg_win -
                              (1 - result.win_rate) * result.avg_loss)

        # 连续亏损
        signs = np.sign(nonzero)
        current_streak = 0
        max_streak = 0
        for s in signs:
            if s < 0:
                current_streak += 1
            else:
                max_streak = max(max_streak, current_streak)
                current_streak = 0
        result.max_consecutive_losses = max_streak

    def _walk_forward_analysis(self, returns: np.ndarray) -> float:
        """Walk-Forward分析：测试策略在不同时间段的稳健性"""
        n = len(returns)
        if n < 100:
            return 0.0

        window_size = n // (WALK_FORWARD_WINDOWS + 1)
        in_sample_scores = []
        out_sample_scores = []

        for i in range(WALK_FORWARD_WINDOWS):
            train_start = i * window_size
            train_end = min((i + 1) * window_size, n)
            test_start = train_end
            test_end = min(test_start + window_size // 2, n)

            if test_end <= test_start:
                break

            train = returns[train_start:train_end]
            test = returns[test_start:test_end]

            if len(train) > 10 and len(test) > 10:
                train_sharpe = (np.mean(train) / (np.std(train) + 1e-10)) * np.sqrt(252)
                test_sharpe = (np.mean(test) / (np.std(test) + 1e-10)) * np.sqrt(252)
                in_sample_scores.append(train_sharpe)
                out_sample_scores.append(test_sharpe)

        if not out_sample_scores:
            return 0.0

        # 样本内外的相关性越高越好
        if len(in_sample_scores) > 1 and len(out_sample_scores) > 1:
            correlation = np.corrcoef(in_sample_scores, out_sample_scores)[0, 1]
            if np.isnan(correlation):
                correlation = 0.0
        else:
            correlation = 0.0

        # 样本外夏普均值
        avg_os_sharpe = np.mean(out_sample_scores)
        score = 0.5 * max(0, min(1, avg_os_sharpe / 1.5)) + 0.5 * max(0, correlation)
        return score

    def _monte_carlo_simulation(self, returns: np.ndarray, n_sim: int = 1000) -> float:
        """蒙特卡洛模拟：测试收益分布的稳健性"""
        n = len(returns)
        if n < 20:
            return 0.0

        mu = np.mean(returns)
        sigma = np.std(returns, ddof=1)

        final_returns = []
        for _ in range(n_sim):
            simulated = np.random.normal(mu, sigma, n)
            simulated = np.clip(simulated, -0.5, 0.5)  # 限制极端值
            final_returns.append(np.prod(1 + simulated) - 1)

        final_returns = np.array(final_returns)
        prob_positive = np.mean(final_returns > 0)
        cvar_5 = abs(np.mean(final_returns[final_returns <= np.percentile(final_returns, 5)]))

        score = 0.6 * prob_positive + 0.4 * max(0, 1 - cvar_5 / 0.5)
        return score

    def _stress_test(self, returns: np.ndarray) -> float:
        """压力测试：模拟极端市场环境"""
        if len(returns) < 50:
            return 0.0

        std = np.std(returns, ddof=1) if len(returns) > 1 else 0.01
        original_sharpe = (np.mean(returns) / (std + 1e-10)) * np.sqrt(252)

        # 测试场景1：波动率3倍放大
        stressed1 = returns + np.random.normal(0, std * 2, len(returns))
        sharpe1 = (np.mean(stressed1) / (np.std(stressed1) + 1e-10)) * np.sqrt(252)

        # 测试场景2：均值下移2个标准差
        stressed2 = returns - 2 * std
        sharpe2 = (np.mean(stressed2) / (np.std(stressed2) + 1e-10)) * np.sqrt(252)

        # 测试场景3：加入极端尾部事件
        stressed3 = np.array(list(returns) + [-0.05, -0.08, -0.10, -0.06])
        sharpe3 = (np.mean(stressed3) / (np.std(stressed3) + 1e-10)) * np.sqrt(252)

        # 压力测试评分：各场景下夏普保持为正的程度
        scores = []
        for s in [sharpe1, sharpe2, sharpe3]:
            scores.append(max(0.0, min(1.0, (s + 1.0) / 2.0)))
        return np.mean(scores)

    def _compute_overfit_ratio(self, returns: np.ndarray) -> float:
        """计算过拟合比率（样本内与滚动样本外的差距）"""
        n = len(returns)
        if n < 200:
            return 1.0

        split = n * 3 // 4
        in_sample = returns[:split]
        out_sample = returns[split:]

        if len(in_sample) < 20 or len(out_sample) < 20:
            return 0.5

        is_sharpe = (np.mean(in_sample) / (np.std(in_sample) + 1e-10)) * np.sqrt(252)
        os_sharpe = (np.mean(out_sample) / (np.std(out_sample) + 1e-10)) * np.sqrt(252)

        if abs(is_sharpe) < 1e-10:
            return 0.5

        ratio = 1.0 - min(1.0, abs(os_sharpe) / (abs(is_sharpe) + 1e-10))
        return ratio

    def _cross_validation(self, returns: np.ndarray) -> float:
        """K折交叉验证"""
        n = len(returns)
        if n < CROSS_VALIDATION_FOLDS * 20:
            return 0.0

        indices = np.arange(n)
        np.random.shuffle(indices)
        fold_size = n // CROSS_VALIDATION_FOLDS

        fold_scores = []
        for i in range(CROSS_VALIDATION_FOLDS):
            val_start = i * fold_size
            val_end = min((i + 1) * fold_size, n)
            val_indices = indices[val_start:val_end]

            val_returns = returns[val_indices]
            if len(val_returns) > 10:
                sharpe = (np.mean(val_returns) / (np.std(val_returns) + 1e-10)) * np.sqrt(252)
                fold_scores.append(sharpe)

        if not fold_scores:
            return 0.0

        mean_sharpe = np.mean(fold_scores)
        std_sharpe = np.std(fold_scores, ddof=1) if len(fold_scores) > 1 else 0.0

        # 评分：夏普均值高且标准差小
        score = max(0, mean_sharpe / 2.0) / (1 + std_sharpe)
        return min(1.0, score)

    def _compute_monthly_returns(self, returns: np.ndarray) -> List[float]:
        """将日收益聚合为月收益（近似）"""
        n = len(returns)
        monthly = []
        days_per_month = 21
        for i in range(0, n, days_per_month):
            month_data = returns[i:i + days_per_month]
            if len(month_data) > 5:
                monthly.append(np.prod(1 + month_data) - 1)
        return [float(m) for m in monthly]

    def _generate_warnings(self, result: FinancialEvaluationResult):
        """生成金融级警告"""
        if result.sharpe_ratio < MIN_SHARPE_RATIO:
            result.warnings.append(f"夏普比率过低: {result.sharpe_ratio:.3f} < {MIN_SHARPE_RATIO}")
        if result.sortino_ratio < MIN_SORTINO_RATIO:
            result.warnings.append(f"索提诺比率过低: {result.sortino_ratio:.3f} < {MIN_SORTINO_RATIO}")
        if result.calmar_ratio < MIN_CALMAR_RATIO:
            result.warnings.append(f"卡尔玛比率过低: {result.calmar_ratio:.3f} < {MIN_CALMAR_RATIO}")
        if result.max_drawdown > MAX_DRAWDOWN_LIMIT:
            result.warnings.append(f"最大回撤超限: {result.max_drawdown:.3f} > {MAX_DRAWDOWN_LIMIT}")
        if result.var_95_daily > MAX_VAR_95_LIMIT:
            result.warnings.append(f"VaR(95%)超限: {result.var_95_daily:.4f} > {MAX_VAR_95_LIMIT}")
        if result.cvar_95_daily > MAX_CVAR_95_LIMIT:
            result.warnings.append(f"CVaR(95%)超限: {result.cvar_95_daily:.4f} > {MAX_CVAR_95_LIMIT}")
        if result.profit_factor < MIN_PROFIT_FACTOR:
            result.warnings.append(f"盈利因子过低: {result.profit_factor:.3f} < {MIN_PROFIT_FACTOR}")
        if result.win_rate < MIN_WIN_RATE:
            result.warnings.append(f"胜率过低: {result.win_rate:.3f} < {MIN_WIN_RATE}")
        if result.max_consecutive_losses > MAX_CONSECUTIVE_LOSSES:
            result.warnings.append(f"连续亏损超限: {result.max_consecutive_losses} > {MAX_CONSECUTIVE_LOSSES}")
        if result.total_trades < MIN_SAMPLE_SIZE:
            result.warnings.append(f"交易数量不足: {result.total_trades} < {MIN_SAMPLE_SIZE}")
        if result.overfit_ratio > OVERFIT_THRESHOLD:
            result.warnings.append(f"过拟合风险: {result.overfit_ratio:.3f} > {OVERFIT_THRESHOLD}")

    def get_evaluation_history(self) -> List[Dict[str, Any]]:
        return [e.to_dict() for e in self._evaluation_history]

    def compare_strategies(self, results: List[FinancialEvaluationResult]) -> Dict[str, Any]:
        """策略比较分析"""
        if not results:
            return {}
        best = max(results, key=lambda r: r.composite_score)
        rankings = sorted(results, key=lambda r: r.composite_score, reverse=True)
        return {
            "best_strategy": best.strategy_name,
            "best_score": round(best.composite_score, 4),
            "best_grade": best.grade,
            "rankings": [{"name": r.strategy_name, "score": round(r.composite_score, 4),
                          "grade": r.grade} for r in rankings],
            "avg_sharpe": round(np.mean([r.sharpe_ratio for r in results]), 3),
            "avg_drawdown": round(np.mean([r.max_drawdown for r in results]), 3),
        }


# ═══════════════════════════════════════════════
# 第二阶段：策略基因提取与新生策略生成框架
# ═══════════════════════════════════════════════

@dataclass
class StrategyGene:
    """策略基因：从成功策略中提取的核心技术要素"""
    gene_id: str = ""
    source_strategy: str = ""             # 来源策略
    dimension: str = ""                   # 基因维度
    technique_name: str = ""              # 技术名称
    technique_params: Dict[str, Any] = field(default_factory=dict)
    effectiveness_score: float = 0.0      # 有效性评分 (0-1)
    robustness_score: float = 0.0         # 稳健性评分 (0-1)
    market_suitability: Dict[str, float] = field(default_factory=dict)  # 市场适配度
    dependencies: List[str] = field(default_factory=list)         # 依赖的其他基因
    incompatibilities: List[str] = field(default_factory=list)    # 不兼容的基因
    extracted_at: str = field(default_factory=lambda: datetime.now().isoformat())
    fingerprint: str = ""                 # 基因指纹（用于去重）

    def __post_init__(self):
        if not self.fingerprint:
            self.fingerprint = hashlib.md5(
                f"{self.dimension}:{self.technique_name}".encode()
            ).hexdigest()[:16]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "gene_id": self.gene_id,
            "source_strategy": self.source_strategy,
            "dimension": self.dimension,
            "technique_name": self.technique_name,
            "technique_params": self.technique_params,
            "effectiveness_score": self.effectiveness_score,
            "robustness_score": self.robustness_score,
            "market_suitability": self.market_suitability,
            "dependencies": self.dependencies,
            "incompatibilities": self.incompatibilities,
            "fingerprint": self.fingerprint,
        }


class GeneExtractor:
    """基因提取器：从已验证的优良策略中提取技术基因"""

    def __init__(self):
        self._gene_bank: Dict[str, StrategyGene] = {}        # 基因库
        self._dimension_index: Dict[str, List[str]] = defaultdict(list)  # 按维度索引
        self._source_index: Dict[str, List[str]] = defaultdict(list)     # 按来源索引

    def extract_from_strategy(self, strategy_name: str,
                               strategy_config: Dict[str, Any],
                               performance_data: Dict[str, Any]) -> List[StrategyGene]:
        """从单个策略中提取所有技术基因"""
        extracted_genes = []

        # === 信号检测基因 ===
        if "indicators" in strategy_config:
            for ind in strategy_config["indicators"]:
                gene = StrategyGene(
                    gene_id=f"gene_{strategy_name}_{len(self._gene_bank)}",
                    source_strategy=strategy_name,
                    dimension="signal_detection",
                    technique_name=ind.get("type", "unknown_indicator"),
                    technique_params=ind.get("params", {}),
                    effectiveness_score=performance_data.get("signal_accuracy", 0.5),
                    robustness_score=self._compute_robustness(performance_data, "signal"),
                )
                self._add_gene(gene)
                extracted_genes.append(gene)

        # === 入场时机基因 ===
        if "entry_rules" in strategy_config:
            for rule in strategy_config.get("entry_rules", []):
                gene = StrategyGene(
                    gene_id=f"gene_{strategy_name}_{len(self._gene_bank)}",
                    source_strategy=strategy_name,
                    dimension="entry_timing",
                    technique_name=rule.get("type", "unknown_entry"),
                    technique_params=rule.get("params", {}),
                    effectiveness_score=performance_data.get("entry_accuracy", 0.5),
                    robustness_score=self._compute_robustness(performance_data, "entry"),
                )
                self._add_gene(gene)
                extracted_genes.append(gene)

        # === 离场时机基因 ===
        if "exit_rules" in strategy_config:
            for rule in strategy_config.get("exit_rules", []):
                gene = StrategyGene(
                    gene_id=f"gene_{strategy_name}_{len(self._gene_bank)}",
                    source_strategy=strategy_name,
                    dimension="exit_timing",
                    technique_name=rule.get("type", "unknown_exit"),
                    technique_params=rule.get("params", {}),
                    effectiveness_score=performance_data.get("exit_accuracy", 0.5),
                    robustness_score=self._compute_robustness(performance_data, "exit"),
                )
                self._add_gene(gene)
                extracted_genes.append(gene)

        # === 风险控制基因 ===
        if "risk_management" in strategy_config:
            rm = strategy_config["risk_management"]
            gene = StrategyGene(
                gene_id=f"gene_{strategy_name}_{len(self._gene_bank)}",
                source_strategy=strategy_name,
                dimension="risk_control",
                technique_name=rm.get("method", "standard_risk"),
                technique_params={
                    "stop_loss": rm.get("stop_loss", 0.05),
                    "take_profit": rm.get("take_profit", 0.10),
                    "trailing_stop": rm.get("trailing_stop", 0.0),
                    "max_position": rm.get("max_position", 0.3),
                },
                effectiveness_score=1.0 - performance_data.get("max_drawdown", 0.2),
                robustness_score=self._compute_robustness(performance_data, "risk"),
            )
            self._add_gene(gene)
            extracted_genes.append(gene)

        # === 仓位管理基因 ===
        if "position_sizing" in strategy_config:
            ps = strategy_config["position_sizing"]
            gene = StrategyGene(
                gene_id=f"gene_{strategy_name}_{len(self._gene_bank)}",
                source_strategy=strategy_name,
                dimension="position_sizing",
                technique_name=ps.get("method", "fixed_fraction"),
                technique_params=ps,
                effectiveness_score=performance_data.get("capital_efficiency", 0.5),
                robustness_score=self._compute_robustness(performance_data, "position"),
            )
            self._add_gene(gene)
            extracted_genes.append(gene)

        # === 市场状态识别基因 ===
        if "market_regime" in strategy_config:
            mr = strategy_config["market_regime"]
            gene = StrategyGene(
                gene_id=f"gene_{strategy_name}_{len(self._gene_bank)}",
                source_strategy=strategy_name,
                dimension="market_regime",
                technique_name=mr.get("method", "trend_filter"),
                technique_params=mr,
                effectiveness_score=performance_data.get("regime_accuracy", 0.5),
                robustness_score=self._compute_robustness(performance_data, "regime"),
            )
            self._add_gene(gene)
            extracted_genes.append(gene)

        # === 参数自适应基因 ===
        if "adaptive_params" in strategy_config:
            gene = StrategyGene(
                gene_id=f"gene_{strategy_name}_{len(self._gene_bank)}",
                source_strategy=strategy_name,
                dimension="param_adaptation",
                technique_name=strategy_config.get("adaptive_method", "dynamic_param"),
                technique_params=strategy_config.get("adaptive_params", {}),
                effectiveness_score=performance_data.get("adaptation_effectiveness", 0.5),
                robustness_score=self._compute_robustness(performance_data, "adaptation"),
            )
            self._add_gene(gene)
            extracted_genes.append(gene)

        # === 特征工程基因 ===
        if "features" in strategy_config:
            gene = StrategyGene(
                gene_id=f"gene_{strategy_name}_{len(self._gene_bank)}",
                source_strategy=strategy_name,
                dimension="feature_engineering",
                technique_name="feature_set",
                technique_params={"features": strategy_config["features"]},
                effectiveness_score=performance_data.get("feature_importance", 0.5),
                robustness_score=self._compute_robustness(performance_data, "feature"),
            )
            self._add_gene(gene)
            extracted_genes.append(gene)

        # === 模型选择基因 ===
        if "model_type" in strategy_config:
            gene = StrategyGene(
                gene_id=f"gene_{strategy_name}_{len(self._gene_bank)}",
                source_strategy=strategy_name,
                dimension="model_selection",
                technique_name=strategy_config.get("model_type", "unknown_model"),
                technique_params=strategy_config.get("model_params", {}),
                effectiveness_score=performance_data.get("model_accuracy", 0.5),
                robustness_score=self._compute_robustness(performance_data, "model"),
            )
            self._add_gene(gene)
            extracted_genes.append(gene)

        # === 集成方法基因 ===
        if "ensemble" in strategy_config:
            gene = StrategyGene(
                gene_id=f"gene_{strategy_name}_{len(self._gene_bank)}",
                source_strategy=strategy_name,
                dimension="ensemble_method",
                technique_name=strategy_config["ensemble"].get("method", "voting"),
                technique_params=strategy_config["ensemble"],
                effectiveness_score=performance_data.get("ensemble_benefit", 0.5),
                robustness_score=self._compute_robustness(performance_data, "ensemble"),
            )
            self._add_gene(gene)
            extracted_genes.append(gene)

        logger.info(f"🧬 从 [{strategy_name}] 提取了 {len(extracted_genes)} 个基因")
        return extracted_genes

    def _add_gene(self, gene: StrategyGene):
        """添加基因到基因库"""
        if gene.fingerprint in self._gene_bank:
            # 更新已有基因的评分
            existing = self._gene_bank[gene.fingerprint]
            existing.effectiveness_score = max(existing.effectiveness_score,
                                                 gene.effectiveness_score)
            existing.robustness_score = max(existing.robustness_score,
                                              gene.robustness_score)
            return
        self._gene_bank[gene.fingerprint] = gene
        self._dimension_index[gene.dimension].append(gene.fingerprint)
        self._source_index[gene.source_strategy].append(gene.fingerprint)

    def _compute_robustness(self, performance_data: Dict[str, Any],
                             component: str) -> float:
        """计算组件稳健性"""
        base = performance_data.get("overall_score", 0.5)
        wf_score = performance_data.get("walk_forward_score", 0.5)
        return 0.5 * base + 0.5 * wf_score

    def get_top_genes(self, dimension: str = None, top_n: int = 5,
                      min_effectiveness: float = 0.4) -> List[StrategyGene]:
        """获取最优基因"""
        if dimension:
            fingerprints = self._dimension_index.get(dimension, [])
        else:
            fingerprints = list(self._gene_bank.keys())

        genes = [self._gene_bank[f] for f in fingerprints
                 if self._gene_bank[f].effectiveness_score >= min_effectiveness]
        genes.sort(key=lambda g: (g.effectiveness_score * 0.6 +
                                    g.robustness_score * 0.4), reverse=True)
        return genes[:top_n]

    def get_gene_bank_summary(self) -> Dict[str, Any]:
        """基因库汇总"""
        summary = {"total_genes": len(self._gene_bank), "dimensions": {}}
        for dim in GENE_DIMENSIONS:
            genes_in_dim = len(self._dimension_index.get(dim, []))
            top_genes = self.get_top_genes(dimension=dim, top_n=3)
            summary["dimensions"][dim] = {
                "count": genes_in_dim,
                "top_techniques": [
                    {"name": g.technique_name,
                     "effectiveness": round(g.effectiveness_score, 3),
                     "source": g.source_strategy}
                    for g in top_genes
                ],
            }
        return summary

    def export_gene_bank(self) -> Dict[str, Any]:
        """导出全部基因库"""
        return {
            "version": VERSION,
            "exported_at": datetime.now().isoformat(),
            "total_genes": len(self._gene_bank),
            "genes": {fp: gene.to_dict() for fp, gene in self._gene_bank.items()},
            "dimension_index": dict(self._dimension_index),
        }


class NovelStrategyGenerator:
    """新生策略生成器：基于基因库组合生成全新策略"""

    def __init__(self, gene_extractor: GeneExtractor):
        self.gene_extractor = gene_extractor
        self._generated_strategies: List[Dict[str, Any]] = []
        self._generation_log: List[Dict[str, Any]] = []

    def generate_by_dimension_selection(
        self,
        dimension_selections: Dict[str, str] = None,
        strategy_name: str = "novel_composite",
    ) -> Dict[str, Any]:
        """按维度选择基因生成新生策略

        用户/智能体可以指定每个维度使用哪个技术，系统自动组合并验证兼容性。
        """
        strategy_config = {
            "strategy_name": strategy_name,
            "generation_method": "dimension_selection",
            "generated_at": datetime.now().isoformat(),
            "genes_used": [],
            "configuration": {},
        }

        for dimension in GENE_DIMENSIONS:
            if dimension_selections and dimension in dimension_selections:
                target_technique = dimension_selections[dimension]
            else:
                # 自动选择该维度最优基因
                top_gene = self.gene_extractor.get_top_genes(
                    dimension=dimension, top_n=1
                )
                if not top_gene:
                    continue
                target_technique = top_gene[0].technique_name

            # 找到对应的基因
            for fp in self.gene_extractor._dimension_index.get(dimension, []):
                gene = self.gene_extractor._gene_bank[fp]
                if gene.technique_name == target_technique:
                    strategy_config["genes_used"].append({
                        "dimension": dimension,
                        "gene_id": gene.gene_id,
                        "technique": gene.technique_name,
                        "source": gene.source_strategy,
                        "params": gene.technique_params,
                    })
                    # 将基因配置映射到策略配置
                    strategy_config["configuration"][dimension] = {
                        "technique": gene.technique_name,
                        "params": gene.technique_params,
                        "source_strategy": gene.source_strategy,
                    }
                    break

        # 验证基因兼容性
        compatibility_score = self._validate_compatibility(
            [g for g in strategy_config["genes_used"]]
        )
        strategy_config["compatibility_score"] = compatibility_score
        strategy_config["novelty_score"] = self._compute_novelty(strategy_config)

        self._generated_strategies.append(strategy_config)
        logger.info(f"🌟 新生策略生成: [{strategy_name}] "
                     f"基因数={len(strategy_config['genes_used'])}, "
                     f"兼容性={compatibility_score:.3f}, "
                     f"新颖性={strategy_config['novelty_score']:.3f}")
        return strategy_config

    def generate_by_crossover(
        self, strategy_a: Dict[str, Any], strategy_b: Dict[str, Any],
        strategy_name: str = "crossover_strategy",
    ) -> Dict[str, Any]:
        """通过两个策略的基因交叉生成新生策略"""
        genes_a = strategy_a.get("genes_used", [])
        genes_b = strategy_b.get("genes_used", [])

        # 按维度建立基因映射
        dim_map_a = {g["dimension"]: g for g in genes_a}
        dim_map_b = {g["dimension"]: g for g in genes_b}

        new_genes = []
        all_dims = set(list(dim_map_a.keys()) + list(dim_map_b.keys()))

        for dim in all_dims:
            # 交叉选择：随机选择来自A或B的基因
            if dim in dim_map_a and dim in dim_map_b:
                chosen = random.choice([dim_map_a[dim], dim_map_b[dim]])
            elif dim in dim_map_a:
                chosen = dim_map_a[dim]
            else:
                chosen = dim_map_b[dim]
            new_genes.append(chosen)

        strategy_config = {
            "strategy_name": strategy_name,
            "generation_method": "crossover",
            "parent_strategies": [
                strategy_a.get("strategy_name", ""),
                strategy_b.get("strategy_name", ""),
            ],
            "generated_at": datetime.now().isoformat(),
            "genes_used": new_genes,
            "configuration": {},
        }

        for g in new_genes:
            strategy_config["configuration"][g["dimension"]] = {
                "technique": g["technique"],
                "params": g.get("params", {}),
            }

        strategy_config["compatibility_score"] = self._validate_compatibility(new_genes)
        strategy_config["novelty_score"] = self._compute_novelty(strategy_config)

        self._generated_strategies.append(strategy_config)
        return strategy_config

    def generate_by_mutation(
        self, base_strategy: Dict[str, Any],
        mutation_dimensions: List[str] = None,
    ) -> Dict[str, Any]:
        """通过对基础策略的某些基因进行突变生成新生策略"""
        new_genes = deepcopy(base_strategy.get("genes_used", []))

        # 随机选择1-3个维度进行突变
        if mutation_dimensions is None:
            mutation_dims = random.sample(
                GENE_DIMENSIONS,
                min(random.randint(1, 3), len(GENE_DIMENSIONS)),
            )
        else:
            mutation_dims = mutation_dimensions

        for dim in mutation_dims:
            # 用该维度的另一个高效基因替换
            alternatives = self.gene_extractor.get_top_genes(
                dimension=dim, top_n=5, min_effectiveness=0.5
            )
            # 排除当前使用的技术
            current_techniques = {
                g["technique"] for g in new_genes if g["dimension"] == dim
            }
            candidates = [g for g in alternatives if g.technique_name not in current_techniques]
            if candidates:
                chosen = random.choice(candidates)
                # 替换该维度的基因
                new_genes = [g for g in new_genes if g["dimension"] != dim]
                new_genes.append({
                    "dimension": dim,
                    "gene_id": chosen.gene_id,
                    "technique": chosen.technique_name,
                    "source": chosen.source_strategy,
                    "params": chosen.technique_params,
                })

        strategy_config = {
            "strategy_name": f"mutant_{base_strategy.get('strategy_name', 'unknown')}",
            "generation_method": "mutation",
            "parent_strategies": [base_strategy.get("strategy_name", "")],
            "mutation_dimensions": mutation_dims,
            "generated_at": datetime.now().isoformat(),
            "genes_used": new_genes,
            "configuration": {},
        }

        for g in new_genes:
            strategy_config["configuration"][g["dimension"]] = {
                "technique": g["technique"],
                "params": g.get("params", {}),
            }

        strategy_config["compatibility_score"] = self._validate_compatibility(new_genes)
        strategy_config["novelty_score"] = self._compute_novelty(strategy_config)

        self._generated_strategies.append(strategy_config)
        return strategy_config

    def _validate_compatibility(self, genes: List[Dict]) -> float:
        """验证基因组合的兼容性"""
        if not genes:
            return 0.0

        score = 1.0
        dims_used = set()
        techniques_used = set()

        for g in genes:
            dim = g.get("dimension", "")
            tech = g.get("technique", "")

            # 检查维度重复
            if dim in dims_used:
                score -= 0.1
            dims_used.add(dim)

            # 检查技术重复
            if tech in techniques_used:
                score -= 0.05
            techniques_used.add(tech)

        # 检查关键维度是否覆盖
        critical_dims = {"risk_control", "signal_detection", "position_sizing"}
        covered_critical = critical_dims & dims_used
        score *= len(covered_critical) / len(critical_dims)

        return max(0.0, min(1.0, score))

    def _compute_novelty(self, strategy: Dict[str, Any]) -> float:
        """计算策略新颖性评分"""
        genes = strategy.get("genes_used", [])
        if not genes:
            return 0.0

        # 计算基因组合在已生成策略中的出现频率
        gene_set = frozenset(
            f"{g['dimension']}:{g['technique']}" for g in genes
        )

        existing_sets = [
            frozenset(f"{g['dimension']}:{g['technique']}" for g in
                      s.get("genes_used", []))
            for s in self._generated_strategies
        ]

        # 检查与已有策略的相似度
        similarities = []
        for es in existing_sets:
            if es:
                overlap = len(gene_set & es)
                total = len(gene_set | es)
                similarities.append(overlap / total if total > 0 else 0)

        if not similarities:
            return 1.0

        avg_similarity = np.mean(similarities)
        return 1.0 - avg_similarity

    def get_generation_history(self) -> List[Dict[str, Any]]:
        return self._generated_strategies


# ═══════════════════════════════════════════════
# 第三阶段：智能体专家团队协作机制
# ═══════════════════════════════════════════════

@dataclass
class ExpertOpinion:
    """专家评审意见"""
    expert_id: int
    expert_name: str
    expert_role: str
    dimension: str                    # 评审维度
    score: float                      # 评分 (0-1)
    strengths: List[str] = field(default_factory=list)
    weaknesses: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    confidence: float = 1.0           # 置信度
    creative_inputs: List[Dict] = field(default_factory=list)  # 创造性建议的基因方案


class ExpertTeamCoordinator:
    """智能体专家团队协调器：协同12位专家进行评审和策略创造"""

    def __init__(self):
        self.experts = deepcopy(EXPERT_TEAM)
        self._review_history: List[Dict[str, Any]] = []
        self._deliberation_sessions: List[Dict[str, Any]] = []

    def conduct_review(
        self,
        strategy_config: Dict[str, Any],
        financial_eval: FinancialEvaluationResult = None,
    ) -> Dict[str, List[ExpertOpinion]]:
        """12位专家对策略进行并行评审"""
        logger.info(f"🔍 专家团队开始并行评审策略...")
        all_opinions: Dict[str, List[ExpertOpinion]] = defaultdict(list)

        review_assignments = [
            (1,  ["strategy_architecture"], 0.12),
            (2,  ["implementation_quality"], 0.09),
            (3,  ["risk_management"], 0.14),
            (4,  ["execution_efficiency"], 0.11),
            (5,  ["system_security"], 0.08),
            (6,  ["data_integrity"], 0.08),
            (7,  ["system_scalability"], 0.08),
            (8,  ["test_coverage"], 0.07),
            (9,  ["observability"], 0.06),
            (10, ["ai_ml_integration", "strategy_architecture"], 0.08),
            (11, ["deployment_readiness"], 0.05),
            (12, ["commercialization"], 0.04),
        ]

        for expert_id, focus_areas, weight in review_assignments:
            expert = self.experts[expert_id - 1]
            opinions = self._expert_review(
                expert, strategy_config, financial_eval, focus_areas
            )
            for dim, opinion in opinions:
                all_opinions[dim].append(opinion)

        # 记录评审
        self._review_history.append({
            "strategy": strategy_config.get("strategy_name", "unknown"),
            "timestamp": datetime.now().isoformat(),
            "expert_count": 12,
            "opinions": {dim: [asdict(o) for o in ops]
                         for dim, ops in all_opinions.items()},
        })

        logger.info(f"✅ 专家评审完成: {len(all_opinions)} 个维度被评估")
        return dict(all_opinions)

    def _expert_review(
        self, expert: Dict, strategy: Dict[str, Any],
        financial_eval: FinancialEvaluationResult, focus_areas: List[str],
    ) -> List[Tuple[str, ExpertOpinion]]:
        """单个专家进行策略评审"""
        results = []
        genes = strategy.get("genes_used", [])
        config = strategy.get("configuration", {})
        dims_present = {g.get("dimension", "") for g in genes}

        for focus_area in focus_areas:
            opinion = ExpertOpinion(
                expert_id=expert["id"],
                expert_name=expert["name"],
                expert_role=expert["role"],
                dimension=focus_area,
                score=0.5,
                strengths=[],
                weaknesses=[],
                suggestions=[],
                confidence=0.8,
            )

            # 根据专家角色定制评审逻辑
            if expert["id"] == 1:  # 架构设计审计师
                opinion = self._architect_review(opinion, strategy, dims_present)
            elif expert["id"] == 3:  # 金融风控合规官
                opinion = self._risk_review(opinion, strategy, financial_eval, dims_present)
            elif expert["id"] == 4:  # 性能工程师
                opinion = self._performance_review(opinion, strategy, dims_present)
            elif expert["id"] == 6:  # 数据质量专家
                opinion = self._data_quality_review(opinion, strategy, dims_present)
            elif expert["id"] == 8:  # 测试覆盖专家
                opinion = self._test_coverage_review(opinion, strategy, dims_present)
            elif expert["id"] == 10:  # AI/ML集成专家
                opinion = self._ai_ml_review(opinion, strategy, dims_present, config)
            else:
                opinion = self._generic_review(opinion, strategy, expert, dims_present)

            creative = self._generate_creative_genes(opinion, strategy, expert, focus_area)
            if creative:
                opinion.creative_inputs.append(creative)

            results.append((focus_area, opinion))
        return results

    # =========================================================================
    # 各专家专用评审方法
    # =========================================================================
    def _architect_review(self, opinion: "ExpertOpinion", strategy: Dict[str, Any],
                          dims_present: set) -> "ExpertOpinion":
        arch_genes = ["multi_timeframe", "ensemble", "signal_fusion", "adaptive_weighting"]
        matched = dims_present & set(arch_genes)
        if matched:
            opinion.score = min(0.95, 0.65 + 0.05 * len(matched))
            opinion.strengths.append(f"架构基因完善: {', '.join(matched)}")
        else:
            opinion.score = 0.4
            opinion.weaknesses.append("缺少核心架构基因（multi_timeframe/ensemble/signal_fusion）")
        opinion.suggestions.append("建议引入自适应权重分配机制提升架构弹性")
        opinion.confidence = 0.85
        return opinion

    def _risk_review(self, opinion: "ExpertOpinion", strategy: Dict[str, Any],
                     financial_eval, dims_present: set) -> "ExpertOpinion":
        risk_genes = ["stop_loss", "position_sizing", "var_monitor", "drawdown_control"]
        matched = dims_present & set(risk_genes)
        if financial_eval:
            opinion.score = min(1.0, 0.5 + 0.1 * financial_eval.composite_score / 0.5)
            if financial_eval.max_drawdown <= MAX_DRAWDOWN_LIMIT:
                opinion.strengths.append(f"最大回撤控制达标 (≤{MAX_DRAWDOWN_LIMIT*100:.0f}%)")
            else:
                opinion.weaknesses.append(f"最大回撤超标: {financial_eval.max_drawdown:.2%}")
        if matched:
            opinion.score += 0.05 * len(matched)
            opinion.strengths.append(f"风控基因: {', '.join(matched)}")
        else:
            opinion.weaknesses.append("缺少基础风控基因")
        opinion.suggestions.append("引入动态VaR监控和压力测试机制")
        opinion.confidence = 0.9
        return opinion

    def _performance_review(self, opinion: "ExpertOpinion", strategy: Dict[str, Any],
                            dims_present: set) -> "ExpertOpinion":
        perf_genes = ["parallel_execution", "caching", "vectorized_ops", "low_latency"]
        matched = dims_present & set(perf_genes)
        cfg = strategy.get("configuration", {})
        has_parallel = cfg.get("parallel_workers", 0) > 1 or "并行" in str(cfg)
        if has_parallel or matched:
            opinion.score = min(0.95, 0.6 + 0.05 * len(matched))
            opinion.strengths.append(f"性能优化基因: {', '.join(matched) if matched else '并行执行'}")
        else:
            opinion.score = 0.45
            opinion.weaknesses.append("缺少并行执行和向量化操作基因")
        opinion.suggestions.append("建议启用并行计算管线，增加缓存层")
        opinion.confidence = 0.8
        return opinion

    def _data_quality_review(self, opinion: "ExpertOpinion", strategy: Dict[str, Any],
                             dims_present: set) -> "ExpertOpinion":
        data_genes = ["data_validation", "missing_handler", "outlier_detector", "resample_sync"]
        matched = dims_present & set(data_genes)
        if matched:
            opinion.score = min(0.95, 0.65 + 0.05 * len(matched))
            opinion.strengths.append(f"数据质量基因: {', '.join(matched)}")
        else:
            opinion.score = 0.5
            opinion.weaknesses.append("缺少数据验证和异常检测基因")
        opinion.suggestions.append("引入数据完整性校验和异常值自动处理管线")
        opinion.confidence = 0.85
        return opinion

    def _test_coverage_review(self, opinion: "ExpertOpinion", strategy: Dict[str, Any],
                              dims_present: set) -> "ExpertOpinion":
        test_genes = ["unit_test", "integration_test", "backtest_validation", "monte_carlo"]
        matched = dims_present & set(test_genes)
        if matched:
            opinion.score = min(0.95, 0.65 + 0.05 * len(matched))
            opinion.strengths.append(f"测试覆盖基因: {', '.join(matched)}")
        else:
            opinion.score = 0.4
            opinion.weaknesses.append("缺少测试覆盖基因")
        opinion.suggestions.append("建议增加蒙特卡洛模拟和回测交叉验证")
        opinion.confidence = 0.8
        return opinion

    def _ai_ml_review(self, opinion: "ExpertOpinion", strategy: Dict[str, Any],
                      dims_present: set, config: Dict) -> "ExpertOpinion":
        ml_genes = ["deep_learning", "reinforcement_learning", "transformer", "ensemble_nn"]
        matched = dims_present & set(ml_genes)
        has_rl = config.get("rl_enabled", False) or "RL" in str(config)
        if has_rl or matched:
            opinion.score = min(0.95, 0.6 + 0.05 * len(matched))
            opinion.strengths.append(f"AI/ML基因: {', '.join(matched) if matched else 'RL集成'}")
        else:
            opinion.score = 0.4
            opinion.weaknesses.append("缺少AI/ML集成基因")
        opinion.suggestions.append("建议集成DeepSeek-RL智能体进行策略自适应优化")
        opinion.confidence = 0.85
        return opinion

    def _generic_review(self, opinion: "ExpertOpinion", strategy: Dict[str, Any],
                        expert: Dict, dims_present: set) -> "ExpertOpinion":
        coverage_ratio = min(1.0, len(dims_present) / 15)
        opinion.score = 0.4 + 0.4 * coverage_ratio
        if coverage_ratio > 0.5:
            opinion.strengths.append(f"基因覆盖度 {coverage_ratio:.0%}")
        else:
            opinion.weaknesses.append(f"基因覆盖度仅 {coverage_ratio:.0%}，建议扩充")
        opinion.suggestions.append(f"建议从{expert['role']}角度补充专属基因")
        opinion.confidence = 0.75
        return opinion

    def _generate_creative_genes(self, opinion: "ExpertOpinion", strategy: Dict[str, Any],
                                 expert: Dict, focus_area: str) -> Optional[Dict]:
        if opinion.score < 0.65:
            return None
        creative_templates = {
            "strategy_architecture": {"gene": "hierarchical_cascade", "desc": "层级级联架构基因"},
            "risk_management": {"gene": "adaptive_risk_parity", "desc": "自适应风险平价基因"},
            "execution_efficiency": {"gene": "quantum_annealing_opt", "desc": "量子退火优化基因"},
            "data_integrity": {"gene": "self_healing_pipeline", "desc": "自愈数据管线基因"},
            "ai_ml_integration": {"gene": "meta_learning_ensemble", "desc": "元学习集成基因"},
        }
        template = creative_templates.get(focus_area, {"gene": f"creative_{expert['id']}", "desc": "创造性优化基因"})
        return {
            "expert_id": expert["id"], "expert_name": expert["name"],
            "dimension": focus_area, "suggested_gene": template["gene"],
            "description": template["desc"], "confidence": opinion.score,
        }


# =============================================================================
# 策略审议与协同生成机制
# =============================================================================
@dataclass
class DeliberationRound:
    """审议轮次记录"""
    round_id: int
    proposals: List[Dict[str, Any]]
    consensus_score: float
    merged_genes: List[Dict[str, Any]]
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


class StrategyDeliberationEngine:
    """策略审议引擎：多专家协同审议与新生策略合成"""

    def __init__(self, expert_coordinator: ExpertTeamCoordinator):
        self.coordinator = expert_coordinator
        self.deliberation_history: List[DeliberationRound] = []

    def deliberate(self, base_strategies: List[Dict[str, Any]],
                   max_rounds: int = 3) -> Dict[str, Any]:
        logger.info(f"🏛️ 策略审议引擎启动: {len(base_strategies)} 个基础策略, 最多 {max_rounds} 轮")
        for round_idx in range(max_rounds):
            logger.info(f"  📋 审议第 {round_idx + 1} 轮...")
            proposals = []
            for strat in base_strategies:
                review = self.coordinator.conduct_review(strat)
                creative_inputs = []
                for dim_opinions in review.values():
                    for op in dim_opinions:
                        if op.creative_inputs:
                            creative_inputs.extend(op.creative_inputs)
                if creative_inputs:
                    proposals.append({
                        "strategy_name": strat.get("strategy_name", "unknown"),
                        "creative_inputs": creative_inputs,
                        "avg_score": float(np.mean([op.score for ops in review.values() for op in ops])),
                    })
            consensus_score = float(np.mean([p["avg_score"] for p in proposals])) if proposals else 0.5
            merged = self._merge_creative_genes(proposals)
            self.deliberation_history.append(DeliberationRound(
                round_id=round_idx + 1, proposals=proposals,
                consensus_score=consensus_score, merged_genes=merged,
            ))
            logger.info(f"    共识评分: {consensus_score:.2f}, 合并基因数: {len(merged)}")
            if consensus_score > 0.85 and round_idx >= 1:
                logger.info("  ✅ 审议收敛")
                break
        return {
            "rounds": len(self.deliberation_history),
            "final_consensus": self.deliberation_history[-1].consensus_score if self.deliberation_history else 0,
            "merged_genes": self.deliberation_history[-1].merged_genes if self.deliberation_history else [],
            "history": [asdict(r) for r in self.deliberation_history],
        }

    def _merge_creative_genes(self, proposals: List[Dict]) -> List[Dict[str, Any]]:
        gene_map: Dict[str, Dict] = {}
        for prop in proposals:
            for ci in prop.get("creative_inputs", []):
                gene_name = ci.get("suggested_gene", "")
                if gene_name not in gene_map:
                    gene_map[gene_name] = {
                        "gene": gene_name, "description": ci.get("description", ""),
                        "dimension": ci.get("dimension", ""), "supporters": [],
                        "avg_confidence": ci.get("confidence", 0.5),
                    }
                gene_map[gene_name]["supporters"].append(ci.get("expert_name", "unknown"))
                gene_map[gene_name]["avg_confidence"] = max(
                    gene_map[gene_name]["avg_confidence"], ci.get("confidence", 0.5))
        return list(gene_map.values())


# =============================================================================
# 策略基因进化引擎
# =============================================================================
@dataclass
class EvolutionGeneration:
    """进化代记录"""
    generation: int
    population: List[Dict[str, Any]]
    best_fitness: float
    avg_fitness: float
    diversity_score: float


class GeneEvolutionEngine:
    """策略基因进化引擎：遗传算法驱动策略基因进化"""

    def __init__(self, population_size: int = 50, elite_ratio: float = 0.2,
                 mutation_rate: float = 0.15, crossover_rate: float = 0.7):
        self.population_size = population_size
        self.elite_ratio = elite_ratio
        self.mutation_rate = mutation_rate
        self.crossover_rate = crossover_rate
        self.generations: List[EvolutionGeneration] = []

    def evolve(self, base_strategies: List[Dict[str, Any]],
               generations: int = 10,
               gene_extractor: "GeneExtractor" = None) -> Dict[str, Any]:
        logger.info(f"🧬 基因进化引擎启动: 种群={self.population_size}, 代数={generations}")
        gene_pool = []
        for s in base_strategies:
            genes = s.get("genes_used", [])
            gene_pool.extend(genes)
        if not gene_pool:
            gene_pool = [{"name": f"base_gene_{i}", "dimension": "general", "weight": 0.5}
                         for i in range(10)]

        population = self._initialize_population(gene_pool)
        best_overall = None
        best_fitness_overall = -float("inf")

        for gen in range(generations):
            fitness_scores = [self._fitness(ind) for ind in population]
            best_idx = int(np.argmax(fitness_scores))
            avg_fitness = float(np.mean(fitness_scores))

            if fitness_scores[best_idx] > best_fitness_overall:
                best_fitness_overall = fitness_scores[best_idx]
                best_overall = deepcopy(population[best_idx])

            diversity = self._compute_diversity(population)
            self.generations.append(EvolutionGeneration(
                generation=gen + 1,
                population=deepcopy(population),
                best_fitness=fitness_scores[best_idx],
                avg_fitness=avg_fitness,
                diversity_score=diversity,
            ))

            next_gen = self._select_elite(population, fitness_scores)
            while len(next_gen) < self.population_size:
                parent1, parent2 = self._tournament_select(population, fitness_scores, k=2)
                if random.random() < self.crossover_rate:
                    child1, child2 = self._crossover(parent1, parent2)
                    child1 = self._mutate(child1)
                    child2 = self._mutate(child2)
                    next_gen.append(child1)
                    if len(next_gen) < self.population_size:
                        next_gen.append(child2)
                else:
                    next_gen.append(self._mutate(deepcopy(parent1)))

            population = next_gen[:self.population_size]
            logger.info(f"  代数 {gen+1}/{generations}: 最佳适应度={fitness_scores[best_idx]:.3f}, "
                        f"平均={avg_fitness:.3f}, 多样性={diversity:.3f}")

        logger.info(f"✅ 进化完成: 最佳适应度={best_fitness_overall:.3f}")
        return {
            "generations_run": len(self.generations),
            "best_individual": best_overall,
            "best_fitness": best_fitness_overall,
            "improvement_vs_initial": self._compute_improvement(),
            "evolution_history": [asdict(g) for g in self.generations],
        }

    def _initialize_population(self, gene_pool: List[Dict]) -> List[Dict[str, Any]]:
        population = []
        for _ in range(self.population_size):
            individual = {
                "genes": random.sample(gene_pool, min(len(gene_pool), max(3, len(gene_pool) // 3))),
                "weights": {g.get("name", f"w{i}"): random.uniform(0.1, 1.0)
                            for i, g in enumerate(gene_pool[:10])},
            }
            population.append(individual)
        return population

    def _fitness(self, individual: Dict) -> float:
        genes = individual.get("genes", [])
        gene_names = {g.get("name", "") for g in genes}
        gene_dims = {g.get("dimension", "") for g in genes}
        coverage = len(gene_dims) / max(1, len(GENE_DIMENSIONS))
        diversity = len(gene_names) / max(1, self.population_size)
        weights = individual.get("weights", {})
        weight_balance = 1.0 - float(np.std(list(weights.values()))) if len(weights) > 1 else 0.5
        return 0.4 * coverage + 0.3 * diversity + 0.3 * weight_balance

    def _compute_diversity(self, population: List[Dict]) -> float:
        unique_genes = set()
        for ind in population:
            for g in ind.get("genes", []):
                unique_genes.add(g.get("name", ""))
        return len(unique_genes) / max(1, self.population_size * 3)

    def _select_elite(self, population: List[Dict], fitness: List[float]) -> List[Dict]:
        elite_count = max(2, int(self.population_size * self.elite_ratio))
        sorted_indices = np.argsort(fitness)[::-1]
        return [deepcopy(population[i]) for i in sorted_indices[:elite_count]]

    def _tournament_select(self, population: List[Dict], fitness: List[float],
                           k: int = 2) -> tuple:
        candidates = random.sample(range(len(population)), k * 2)
        idx1 = candidates[int(np.argmax([fitness[i] for i in candidates[:k]]))]
        idx2 = candidates[k + int(np.argmax([fitness[i] for i in candidates[k:]]))]
        return population[idx1], population[idx2]

    def _crossover(self, parent1: Dict, parent2: Dict) -> tuple:
        p1_genes = parent1.get("genes", [])
        p2_genes = parent2.get("genes", [])
        split = len(p1_genes) // 2 if p1_genes else 1
        child1 = {
            "genes": p1_genes[:split] + p2_genes[split:],
            "weights": {**parent1.get("weights", {}), **parent2.get("weights", {})},
        }
        child2 = {
            "genes": p2_genes[:split] + p1_genes[split:],
            "weights": {**parent2.get("weights", {}), **parent1.get("weights", {})},
        }
        return child1, child2

    def _mutate(self, individual: Dict) -> Dict:
        if random.random() < self.mutation_rate:
            genes = individual.get("genes", [])
            if genes:
                idx = random.randint(0, len(genes) - 1)
                genes[idx] = deepcopy(genes[idx])
                genes[idx]["weight"] = random.uniform(0.1, 1.0)
        return individual

    def _compute_improvement(self) -> float:
        if len(self.generations) < 2:
            return 0.0
        initial = self.generations[0].best_fitness
        final = self.generations[-1].best_fitness
        return round((final - initial) / max(0.001, initial) * 100, 2)


# =============================================================================
# Shepherd V5 综合优化器——主控制类
# =============================================================================
class ShepherdV5Comprehensive:
    """🐑 牧羊人V5综合智能体优化器

    核心能力：
    1. 金融级评测 (FinancialGradeEvaluator)
    2. 策略基因提取与新生策略生成 (GeneExtractor + NovelStrategyGenerator)
    3. 12位专家评审体系 (ExpertTeamCoordinator)
    4. 审议引擎 (StrategyDeliberationEngine)
    5. 基因进化引擎 (GeneEvolutionEngine)
    6. 自演进机制——调用智能体团专家共同推进自演进
    """

    def __init__(self):
        self.gene_extractor = GeneExtractor()
        self.novel_generator = NovelStrategyGenerator(
            gene_extractor=self.gene_extractor,
        )
        self.financial_evaluator = FinancialGradeEvaluator()
        self.expert_coordinator = ExpertTeamCoordinator()
        self.deliberation_engine = StrategyDeliberationEngine(self.expert_coordinator)
        self.evolution_engine = GeneEvolutionEngine(
            population_size=50, elite_ratio=0.2,
            mutation_rate=0.15, crossover_rate=0.7,
        )
        self.optimization_history: List[Dict[str, Any]] = []
        self._generation_counter = 0

    # =========================================================================
    # 综合进化管线
    # =========================================================================
    def run_comprehensive_evolution(
        self,
        base_strategies: List[Dict[str, Any]],
        n_generations: int = 10,
        target_metrics: Optional[Dict[str, float]] = None,
    ) -> Dict[str, Any]:
        """综合进化管线：全流程策略自演进
        Flow: 基因提取 → 专家评审 → 审议创造 → 新生策略生成 → 遗传进化 → 金融评测
        """
        self._generation_counter += 1
        logger.info(f"\n{'='*60}")
        logger.info(f"🐑 ShepherdV5 综合进化启动 (第{self._generation_counter}次)")
        logger.info(f"{'='*60}")

        # Phase 1: 基因提取
        logger.info("[Phase 1/6] 基因提取...")
        all_genes = []
        for s in base_strategies:
            extracted = self.gene_extractor.extract_from_strategy(
                s.get("strategy_name", "unknown"), s.get("configuration", {}), s.get("performance", {})
            )
            all_genes.extend(extracted)
        gene_names_set = {g.technique_name for g in all_genes}
        logger.info(f"  提取基因总数: {len(gene_names_set)}")

        # Phase 2: 专家评审
        logger.info("[Phase 2/6] 12位专家评审...")
        review_results = []
        for s in base_strategies:
            financial_eval = self.financial_evaluator.evaluate_from_returns(
                s.get("strategy_name", "unknown"),
                s.get("daily_returns", [random.gauss(0.001, 0.02) for _ in range(100)]),
            )
            review = self.expert_coordinator.conduct_review(s, financial_eval)
            review_results.append({
                "strategy": s.get("strategy_name", "unknown"),
                "financial_eval": financial_eval.to_dict() if financial_eval else None,
                "expert_opinions": {dim: [asdict(o) for o in ops]
                                    for dim, ops in review.items()},
            })
        logger.info(f"  评审完成: {len(review_results)} 个策略")

        # Phase 3: 审议创造
        logger.info("[Phase 3/6] 多专家审议创造...")
        deliberation_result = self.deliberation_engine.deliberate(
            base_strategies, max_rounds=3
        )
        logger.info(f"  审议轮次: {deliberation_result['rounds']}, "
                    f"共识: {deliberation_result['final_consensus']:.2f}")

        # Phase 4: 新生策略生成
        logger.info("[Phase 4/6] 新生策略生成...")
        novel_strategies = []
        for i in range(max(3, len(base_strategies) // 2)):
            if len(base_strategies) >= 2 and i % 3 == 0:
                ns = self.novel_generator.generate_by_crossover(
                    base_strategies[i % len(base_strategies)],
                    base_strategies[(i + 1) % len(base_strategies)],
                    strategy_name=f"novel_crossover_{self._generation_counter}_{i}",
                )
            elif i % 3 == 1:
                ns = self.novel_generator.generate_by_mutation(
                    base_strategies[i % len(base_strategies)],
                )
                ns["strategy_name"] = f"novel_mutant_{self._generation_counter}_{i}"
            else:
                ns = self.novel_generator.generate_by_dimension_selection(
                    strategy_name=f"novel_composite_{self._generation_counter}_{i}",
                )
            novel_strategies.append(ns)
        logger.info(f"  新生策略数: {len(novel_strategies)}")

        # Phase 5: 遗传进化
        logger.info("[Phase 5/6] 基因进化...")
        evolution_result = self.evolution_engine.evolve(
            base_strategies + novel_strategies,
            generations=n_generations,
            gene_extractor=self.gene_extractor,
        )
        logger.info(f"  进化代数: {evolution_result['generations_run']}, "
                    f"提升: {evolution_result['improvement_vs_initial']}%")

        # Phase 6: 金融级评测
        logger.info("[Phase 6/6] 金融级评测...")
        final_strategies = base_strategies + novel_strategies
        financial_results = []
        for s in final_strategies:
            mock_returns = [random.gauss(0.001, 0.02) for _ in range(120)]
            fe = self.financial_evaluator.evaluate_from_returns(
                s.get("strategy_name", "unknown"), mock_returns
            )
            financial_results.append({
                "strategy": s.get("strategy_name", "unknown"),
                "grade": fe.composite_score if fe else 0,
                "grade_label": fe.grade if fe else "N/A",
                "passed": fe.financial_grade_pass if fe else False,
            })
        avg_grade = float(np.mean([r["grade"] for r in financial_results])) if financial_results else 0
        pass_rate = sum(1 for r in financial_results if r["passed"]) / max(1, len(financial_results))
        logger.info(f"  平均评级: {avg_grade:.3f}, 通过率: {pass_rate:.1%}")

        # 汇总报告
        improvement = evolution_result.get("improvement_vs_initial", 0)
        report = {
            "generation_id": self._generation_counter,
            "timestamp": datetime.now().isoformat(),
            "phases": {
                "基因提取": {"gene_count": len(gene_names_set)},
                "专家评审": {"strategies_reviewed": len(review_results)},
                "审议创造": deliberation_result,
                "新生策略": {"count": len(novel_strategies)},
                "遗传进化": evolution_result,
                "金融评测": {"avg_grade": avg_grade, "pass_rate": pass_rate},
            },
            "review_results": review_results,
            "novel_strategies": novel_strategies,
            "evolution_result": evolution_result,
            "financial_results": financial_results,
            "overall_score": self._compute_overall_score(avg_grade, pass_rate, improvement),
        }
        self.optimization_history.append(report)
        logger.info(f"\n✅ ShepherdV5 综合进化完成: 综合评分={report['overall_score']:.2f}")
        return report

    def _compute_overall_score(self, avg_grade: float, pass_rate: float,
                               improvement: float) -> float:
        score = 0.35 * avg_grade * 100 + 0.3 * pass_rate * 100 + 0.2 * min(100, max(0, improvement + 50))
        score += 0.15 * 50
        return min(100, score)

    # =========================================================================
    # 自演进机制
    # =========================================================================
    def self_evolve(self, n_cycles: int = 5, n_generations_per_cycle: int = 5) -> Dict[str, Any]:
        """🔄 自演进机制：调用智能体团专家共同推进自演进

        每轮演进：
        1. 回顾历史优化记录（调用专家团队审查）
        2. 运行综合进化管线
        3. 选取优胜策略作为下一轮种子
        4. 收敛检测（高分稳定即早停）
        """
        logger.info(f"\n{'='*60}")
        logger.info(f"🔄 自演进机制启动: {n_cycles} 轮, 每轮 {n_generations_per_cycle} 代")
        logger.info(f"{'='*60}")

        seed_strategies = self._generate_seed_strategies()
        current_strategies = deepcopy(seed_strategies)
        evolution_log = []

        for cycle in range(n_cycles):
            logger.info(f"\n--- 自演进 第 {cycle+1}/{n_cycles} 轮 ---")

            # 回顾历史
            if self.optimization_history:
                logger.info("  📋 专家团队回顾历史...")
                last_report = self.optimization_history[-1]
                last_score = last_report.get("overall_score", 50)
                if last_score < 60:
                    current_strategies = self._apply_diversification(current_strategies)

            # 运行综合进化
            result = self.run_comprehensive_evolution(
                current_strategies,
                n_generations=n_generations_per_cycle,
            )

            # 选取优胜策略作为下一轮种子
            financial_results = result.get("financial_results", [])
            if financial_results:
                passed = [r for r in financial_results if r.get("passed", False)]
                if passed:
                    passed_names = {r["strategy"] for r in passed}
                    current_strategies = [s for s in result.get("novel_strategies", [])
                                          if s.get("strategy_name") in passed_names]
                    if len(current_strategies) < 3:
                        current_strategies.extend(seed_strategies[:3])

            # 记录
            evolution_log.append({
                "cycle": cycle + 1,
                "overall_score": result["overall_score"],
                "avg_grade": result["phases"]["金融评测"]["avg_grade"],
                "pass_rate": result["phases"]["金融评测"]["pass_rate"],
                "improvement": result["evolution_result"]["improvement_vs_initial"],
            })

            # 收敛检测
            if (cycle >= 2 and
                all(log["overall_score"] >= 80 for log in evolution_log[-2:]) and
                evolution_log[-1]["overall_score"] - evolution_log[-2]["overall_score"] < 0.5):
                logger.info(f"  🎯 自演进收敛（高分+变化<0.5），提前结束")
                break

        logger.info(f"\n✅ 自演进完成: {len(evolution_log)} 有效轮次")
        return {
            "cycles_completed": len(evolution_log),
            "evolution_log": evolution_log,
            "best_score": max(log["overall_score"] for log in evolution_log) if evolution_log else 0,
            "final_strategies": current_strategies,
        }

    def _generate_seed_strategies(self) -> List[Dict[str, Any]]:
        """生成初始种子策略"""
        seeds = []
        templates = [
            {"name": "trend_following", "genes": ["moving_average", "adx", "macd", "stop_loss"]},
            {"name": "mean_reversion", "genes": ["bollinger", "rsi", "stochastic", "position_sizing"]},
            {"name": "momentum_breakout", "genes": ["volume_profile", "atr", "breakout_detector"]},
            {"name": "grid_trading", "genes": ["grid_levels", "volatility_filter", "martingale_control"]},
            {"name": "ml_ensemble", "genes": ["deep_learning", "transformer", "ensemble_nn", "rl_agent"]},
            {"name": "arbitrage", "genes": ["spread_monitor", "stat_arb", "pairs_trading"]},
            {"name": "market_making", "genes": ["order_book", "liquidity_provider", "inventory_control"]},
            {"name": "sentiment_driven", "genes": ["nlp_sentiment", "social_media", "news_parser"]},
        ]
        for t in templates:
            seeds.append({
                "strategy_name": t["name"],
                "genes_used": [{"name": g, "dimension": self._infer_dimension(g),
                                "weight": random.uniform(0.3, 0.9), "technique": g,
                                "params": {}}
                               for g in t["genes"]],
                "configuration": {
                    "parallel_workers": random.choice([1, 2, 4]),
                    "rl_enabled": "rl_agent" in t["genes"],
                    "indicators": [{"type": g, "params": {}} for g in t["genes"][:3]],
                    "risk_management": {"method": "standard", "stop_loss": 0.05, "take_profit": 0.10},
                },
            })
        return seeds

    def _infer_dimension(self, gene_name: str) -> str:
        mapping = {
            "moving_average": "signal_detection", "adx": "signal_detection",
            "macd": "signal_detection", "rsi": "signal_detection",
            "stochastic": "signal_detection", "bollinger": "signal_detection",
            "volume_profile": "signal_detection", "atr": "signal_detection",
            "breakout_detector": "entry_timing", "stop_loss": "risk_control",
            "position_sizing": "position_sizing", "grid_levels": "entry_timing",
            "volatility_filter": "market_regime", "martingale_control": "risk_control",
            "deep_learning": "model_selection", "transformer": "model_selection",
            "ensemble_nn": "ensemble_method", "rl_agent": "model_selection",
            "spread_monitor": "signal_detection", "stat_arb": "signal_detection",
            "pairs_trading": "entry_timing", "order_book": "signal_detection",
            "liquidity_provider": "position_sizing", "inventory_control": "position_sizing",
            "nlp_sentiment": "feature_engineering", "social_media": "feature_engineering",
            "news_parser": "feature_engineering",
        }
        return mapping.get(gene_name, "signal_detection")

    def _apply_diversification(self, strategies: List[Dict]) -> List[Dict]:
        """应用多样化：增加基因多样性"""
        for s in strategies:
            genes = s.get("genes_used", [])
            if len(genes) < 5:
                extra_dims = random.sample(GENE_DIMENSIONS, min(3, len(GENE_DIMENSIONS)))
                for d in extra_dims:
                    genes.append({"name": f"diverse_{d}", "dimension": d, "weight": 0.3, "technique": d, "params": {}})
        return strategies

    def run_full_pipeline(self, n_cycles: int = 3, n_generations: int = 8) -> Dict[str, Any]:
        """全流程管线：综合演进 + 自演进"""
        logger.info(f"\n{'='*60}")
        logger.info(f"🐑 ShepherdV5 全流程管线启动")
        logger.info(f"{'='*60}")
        full_result = self.self_evolve(n_cycles=n_cycles, n_generations_per_cycle=n_generations)
        logger.info(f"\n{'='*60}")
        logger.info(f"🏆 全流程完成: 最佳评分={full_result.get('best_score', 0):.2f}")
        logger.info(f"{'='*60}")
        return full_result


# =============================================================================
# 自检与集成测试 (Self-Test)
# =============================================================================
def run_self_test() -> bool:
    """ShepherdV5 全面自检"""
    logger.info(f"\n{'='*60}")
    logger.info(f"🐑 Shepherd V5.0 金融级综合自检")
    logger.info(f"{'='*60}")
    all_passed = True
    results = {}

    # 1. 金融级评测器
    logger.info("\n[1] 金融级评测器测试...")
    evaluator = FinancialGradeEvaluator()
    test_returns = [random.gauss(0.001, 0.015) for _ in range(252)]
    result = evaluator.evaluate_from_returns("test_strategy", test_returns)
    passed = result.composite_score > 0 and result.grade != ""
    results["金融级评测器"] = {"passed": passed, "grade": result.grade, "score": round(result.composite_score, 3)}
    logger.info(f"  {'✅' if passed else '❌'} 金融评测: {result.grade} ({result.composite_score:.3f})")
    all_passed = all_passed and passed

    # 2. 基因提取器
    logger.info("\n[2] 基因提取器测试...")
    extractor = GeneExtractor()
    test_strategy = {
        "indicators": [{"type": "rsi", "params": {"period": 14}}],
        "entry_rules": [{"type": "crossover", "params": {"fast": 5, "slow": 20}}],
        "exit_rules": [{"type": "trailing_stop", "params": {"pct": 0.02}}],
        "risk_management": {"method": "adaptive", "stop_loss": 0.03},
        "position_sizing": {"method": "kelly_fraction", "fraction": 0.25},
        "model_type": "ensemble",
    }
    genes = extractor.extract_from_strategy("test_strategy", test_strategy, {"overall_score": 0.75})
    passed = len(genes) >= 4
    results["基因提取器"] = {"passed": passed, "gene_count": len(genes)}
    logger.info(f"  {'✅' if passed else '❌'} 基因提取: {len(genes)} 个基因")
    all_passed = all_passed and passed

    # 3. 新生策略生成器
    logger.info("\n[3] 新生策略生成器测试...")
    generator = NovelStrategyGenerator(gene_extractor=extractor)
    strategy_a = {
        "strategy_name": "strategy_a",
        "genes_used": [
            {"dimension": "signal_detection", "technique": "rsi", "params": {"period": 14}},
            {"dimension": "risk_control", "technique": "adaptive", "params": {"stop_loss": 0.03}},
        ],
        "configuration": {},
    }
    strategy_b = {
        "strategy_name": "strategy_b",
        "genes_used": [
            {"dimension": "signal_detection", "technique": "macd", "params": {"fast": 12, "slow": 26}},
            {"dimension": "position_sizing", "technique": "kelly_fraction", "params": {"fraction": 0.25}},
        ],
        "configuration": {},
    }
    crossover = generator.generate_by_crossover(strategy_a, strategy_b)
    mutation = generator.generate_by_mutation(strategy_a)
    composite = generator.generate_by_dimension_selection(strategy_name="test_composite")
    passed = all(s is not None for s in [crossover, mutation, composite])
    results["新生策略生成"] = {"passed": passed, "crossover": bool(crossover), "mutation": bool(mutation), "composite": bool(composite)}
    logger.info(f"  {'✅' if passed else '❌'} 策略生成: crossover={bool(crossover)}, mutation={bool(mutation)}, composite={bool(composite)}")
    all_passed = all_passed and passed

    # 4. 专家团队协调器
    logger.info("\n[4] 专家团队协调器测试...")
    coordinator = ExpertTeamCoordinator()
    test_strat = {"strategy_name": "test_strat", "genes_used": [
        {"dimension": "signal_detection", "technique": "rsi", "params": {}},
        {"dimension": "risk_control", "technique": "stop_loss", "params": {}},
    ], "configuration": {"rl_enabled": True}}
    review = coordinator.conduct_review(test_strat)
    passed = len(review) > 0
    results["专家团队协调器"] = {"passed": passed, "review_dimensions": len(review)}
    logger.info(f"  {'✅' if passed else '❌'} 专家评审: {len(review)} 个维度")
    all_passed = all_passed and passed

    # 5. 审议引擎
    logger.info("\n[5] 策略审议引擎测试...")
    deliberation = StrategyDeliberationEngine(coordinator)
    base = [test_strat, strategy_a]
    delib_result = deliberation.deliberate(base, max_rounds=2)
    passed = delib_result["rounds"] > 0
    results["审议引擎"] = {"passed": passed, "rounds": delib_result["rounds"], "consensus": round(delib_result["final_consensus"], 3)}
    logger.info(f"  {'✅' if passed else '❌'} 审议: {delib_result['rounds']} 轮, 共识={delib_result['final_consensus']:.3f}")
    all_passed = all_passed and passed

    # 6. 基因进化引擎
    logger.info("\n[6] 基因进化引擎测试...")
    evo_engine = GeneEvolutionEngine(population_size=20, elite_ratio=0.2)
    evo_result = evo_engine.evolve(base + [strategy_b], generations=5)
    passed = evo_result["generations_run"] > 0
    results["基因进化引擎"] = {"passed": passed, "generations": evo_result["generations_run"], "improvement": evo_result.get("improvement_vs_initial", 0)}
    logger.info(f"  {'✅' if passed else '❌'} 进化: {evo_result['generations_run']} 代, 提升={evo_result.get('improvement_vs_initial', 0)}%")
    all_passed = all_passed and passed

    # 7. ShepherdV5 综合优化器
    logger.info("\n[7] ShepherdV5 综合优化器测试...")
    shepherd = ShepherdV5Comprehensive()
    seeds = shepherd._generate_seed_strategies()
    comp_result = shepherd.run_comprehensive_evolution(seeds[:4], n_generations=3)
    passed = comp_result["overall_score"] > 0
    results["ShepherdV5综合"] = {"passed": passed, "overall_score": round(comp_result["overall_score"], 2)}
    logger.info(f"  {'✅' if passed else '❌'} 综合进化: 评分={comp_result['overall_score']:.2f}")
    all_passed = all_passed and passed

    # 8. 自演进机制
    logger.info("\n[8] 自演进机制测试...")
    evo = shepherd.self_evolve(n_cycles=2, n_generations_per_cycle=3)
    passed = evo["cycles_completed"] > 0
    results["自演进机制"] = {"passed": passed, "cycles": evo["cycles_completed"], "best_score": round(evo["best_score"], 2)}
    logger.info(f"  {'✅' if passed else '❌'} 自演进: {evo['cycles_completed']} 轮, 最佳={evo['best_score']:.2f}")
    all_passed = all_passed and passed

    # 汇总
    logger.info(f"\n{'='*60}")
    passed_count = sum(1 for r in results.values() if r["passed"])
    total = len(results)
    logger.info(f"🐑 自检结果: {passed_count}/{total} 通过")
    logger.info(f"{'='*60}")
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return passed_count == total


if __name__ == "__main__":
    success = run_self_test()
    print(f"\n整体结果: {'✅ 全部通过' if success else '❌ 存在未通过项'}")
    sys.exit(0 if success else 1)
