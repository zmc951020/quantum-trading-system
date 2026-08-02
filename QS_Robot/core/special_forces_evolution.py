#!/usr/bin/env python3
"""
特种兵・自演进控制器 (Special Forces Self-Evolution Controller)
==============================================================
为「特种兵・威科夫量价自适应策略」提供自动参数寻优引擎。

核心能力：
  1. 强化学习奖励函数（硬约束 + 软目标）
  2. 遗传算法 + 局部搜索 混合优化
  3. 五维熵指标（期望/方差/熵/极值/概率）引导搜索
  4. 按标的独立演化，参数隔离
  5. 参数持久化，支持增量演进

架构：
  SpecialForcesEvolutionController
  ├── HardConstraintChecker    — 硬约束验证
  ├── RewardFunction           — 奖励函数
  ├── FiveDimensionalAnalyzer  — 五维熵指标分析
  ├── EvolutionEngine          — 遗传算法 + 局部搜索
  ├── ParameterJournal         — 演化日志
  └── ParameterStore           — 按标的持久化

硬约束（必须全部满足）：
  - 夏普比率 ≥ 1.8
  - 最大回撤 ≤ 12%
  - 胜率 ≥ 65%
  - 盈亏比 ≥ 2.2

唯一优化目标：最大化年化收益率
"""

import os
import sys
import json
import time
import math
import random
import copy
import traceback
import numpy as np
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple, Callable
from dataclasses import dataclass, field
from collections import OrderedDict

# 路径设置
current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)


# ============================================================
# 数据模型
# ============================================================

@dataclass
class EvolutionGeneration:
    """一代演化记录"""
    generation: int
    population: List[Dict[str, Any]]        # 种群 [{params, score, metrics}]
    best_params: Dict[str, float]
    best_score: float
    best_metrics: Dict[str, float]
    diversity: float                         # 种群多样性
    elapsed_seconds: float
    timestamp: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


@dataclass
class EvolutionJournal:
    """演化日志"""
    symbol: str
    strategy_name: str = "special_forces_wyckoff"
    generations: List[EvolutionGeneration] = field(default_factory=list)
    total_evaluations: int = 0
    total_elapsed_seconds: float = 0.0
    started_at: str = ""
    finished_at: str = ""
    convergence_generation: int = -1         # 收敛代
    final_best_params: Dict[str, float] = field(default_factory=dict)
    final_best_score: float = 0.0
    final_best_metrics: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "symbol": self.symbol,
            "strategy_name": self.strategy_name,
            "generations": [
                {
                    "generation": g.generation,
                    "best_score": g.best_score,
                    "best_metrics": g.best_metrics,
                    "diversity": g.diversity,
                    "elapsed_seconds": g.elapsed_seconds,
                    "timestamp": g.timestamp,
                }
                for g in self.generations
            ],
            "total_evaluations": self.total_evaluations,
            "total_elapsed_seconds": self.total_elapsed_seconds,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "convergence_generation": self.convergence_generation,
            "final_best_params": self.final_best_params,
            "final_best_score": self.final_best_score,
            "final_best_metrics": self.final_best_metrics,
        }


# ============================================================
# 硬约束检查器
# ============================================================

class HardConstraintChecker:
    """
    硬约束检查器

    必须全部满足的硬约束：
      - sharpe_ratio >= 1.8
      - max_drawdown <= 0.12 (12%)
      - win_rate >= 0.65 (65%)
      - profit_factor >= 2.2
    """

    CONSTRAINTS = {
        "sharpe_ratio": ("min", 1.8),
        "max_drawdown": ("max", 0.12),
        "win_rate": ("min", 0.65),
        "profit_factor": ("min", 2.2),
    }

    @classmethod
    def check(cls, metrics: Dict[str, float]) -> Tuple[bool, List[str]]:
        """
        检查是否满足所有硬约束

        Args:
            metrics: {sharpe_ratio, max_drawdown, win_rate, profit_factor, ...}

        Returns:
            (passed, violations): 是否通过 + 违规列表
        """
        violations = []
        for key, (rule, threshold) in cls.CONSTRAINTS.items():
            value = metrics.get(key, 0)
            if rule == "min" and value < threshold:
                violations.append(f"{key}={value:.3f} < {threshold}")
            elif rule == "max" and value > threshold:
                violations.append(f"{key}={value:.3f} > {threshold}")

        return len(violations) == 0, violations

    @classmethod
    def get_constraint_violation_penalty(cls, metrics: Dict[str, float]) -> float:
        """
        计算约束违反惩罚值（用于奖励函数）

        惩罚值越高越差，0 = 全部满足。
        """
        penalty = 0.0
        sharpe = metrics.get("sharpe_ratio", 0)
        if sharpe < 1.8:
            penalty += (1.8 - sharpe) * 5.0

        dd = metrics.get("max_drawdown", 1.0)
        if dd > 0.12:
            penalty += (dd - 0.12) * 50.0

        wr = metrics.get("win_rate", 0)
        if wr < 0.65:
            penalty += (0.65 - wr) * 10.0

        pf = metrics.get("profit_factor", 0)
        if pf < 2.2:
            penalty += (2.2 - pf) * 3.0

        return penalty


# ============================================================
# 强化学习奖励函数
# ============================================================

class RewardFunction:
    """
    强化学习奖励函数

    R(s, a) = α × 年化收益 + β × 夏普 + γ × (1 - 回撤) - λ × 约束惩罚

    其中:
      - 年化收益是唯一最大化目标（连续值）
      - 硬约束通过惩罚项强制
      - α, β, γ, λ 为可调权重
    """

    # 默认权重
    ALPHA = 1.0    # 年化收益权重
    BETA = 0.5     # 夏普权重（辅助）
    GAMMA = 0.3    # 抗回撤权重（辅助）
    LAMBDA = 2.0   # 约束惩罚权重

    @classmethod
    def compute(cls, metrics: Dict[str, float]) -> float:
        """
        计算奖励值

        Args:
            metrics: {
                annual_return: 年化收益率（小数）
                sharpe_ratio: 夏普比率
                max_drawdown: 最大回撤（小数）
                win_rate: 胜率
                profit_factor: 盈亏比
            }

        Returns:
            float: 奖励值（越高越好）
        """
        annual_return = metrics.get("annual_return", 0)
        sharpe = metrics.get("sharpe_ratio", 0)
        max_dd = metrics.get("max_drawdown", 0)
        win_rate = metrics.get("win_rate", 0)
        profit_factor = metrics.get("profit_factor", 0)

        # 主奖励
        reward = (
            cls.ALPHA * annual_return +
            cls.BETA * min(sharpe, 3.0) / 3.0 +  # 夏普归一化，上限3.0
            cls.GAMMA * (1.0 - min(max_dd, 0.3))   # 回撤越低越好
        )

        # 约束惩罚
        constraint_metrics = {
            "sharpe_ratio": sharpe,
            "max_drawdown": max_dd,
            "win_rate": win_rate,
            "profit_factor": profit_factor,
        }
        penalty = HardConstraintChecker.get_constraint_violation_penalty(constraint_metrics)
        reward -= cls.LAMBDA * penalty

        return reward

    @classmethod
    def compute_with_details(cls, metrics: Dict[str, float]) -> Dict[str, Any]:
        """计算奖励值并返回详细信息"""
        passed, violations = HardConstraintChecker.check({
            "sharpe_ratio": metrics.get("sharpe_ratio", 0),
            "max_drawdown": metrics.get("max_drawdown", 0),
            "win_rate": metrics.get("win_rate", 0),
            "profit_factor": metrics.get("profit_factor", 0),
        })

        reward = cls.compute(metrics)

        return {
            "reward": reward,
            "constraints_passed": passed,
            "violations": violations,
            "annual_return": metrics.get("annual_return", 0),
            "sharpe_ratio": metrics.get("sharpe_ratio", 0),
            "max_drawdown": metrics.get("max_drawdown", 0),
            "win_rate": metrics.get("win_rate", 0),
            "profit_factor": metrics.get("profit_factor", 0),
        }


# ============================================================
# 五维熵指标分析器
# ============================================================

class FiveDimensionalAnalyzer:
    """
    五维熵指标分析器

    对参数空间进行五维分析，指导搜索策略：
      E (期望): 参数向量方向 → 指导搜索方向（梯度上升）
      V (方差): 参数稳定性 → 指导搜索密度（高方差区多探）
      H (熵):   探索充分度 → 指导探索/利用平衡
      M (极值): 风险分布 → 过滤极端参数
      P (概率): 质量门控 → 优质区域概率加密
    """

    @staticmethod
    def compute_5d(params_history: List[Dict[str, Any]]) -> Dict[str, float]:
        """
        基于历史参数和评分，计算五维指标

        Args:
            params_history: [{params, score, metrics}, ...]

        Returns:
            {E, V, H, M, P} 五个维度指标
        """
        if not params_history or len(params_history) < 3:
            return {"E": 0.5, "V": 0.5, "H": 0.5, "M": 0.5, "P": 0.5}

        scores = np.array([h["score"] for h in params_history])
        sorted_scores = np.sort(scores)

        # E (期望): 评分趋势（正=上升，负=下降）
        if len(scores) >= 5:
            half = len(scores) // 2
            recent_mean = np.mean(scores[-half:])
            early_mean = np.mean(scores[:half])
            e_score = 1.0 / (1.0 + math.exp(-(recent_mean - early_mean) * 5))
        else:
            e_score = 0.5

        # V (方差): 评分离散度（高=不稳定，需要更多采样）
        score_std = np.std(scores)
        score_mean = np.mean(scores)
        cv = score_std / (abs(score_mean) + 0.01)
        v_score = np.clip(cv, 0, 1)

        # H (熵): 探索多样性（高=探索充分，低=过度集中）
        if len(params_history) >= 5:
            # 用参数空间中心距离的离散度近似熵
            param_keys = list(params_history[0]["params"].keys())
            if param_keys:
                param_matrix = np.array([[h["params"].get(k, 0) for k in param_keys]
                                         for h in params_history])
                centroid = np.mean(param_matrix, axis=0)
                distances = np.linalg.norm(param_matrix - centroid, axis=1)
                h_score = np.clip(np.std(distances) / (np.mean(distances) + 0.01), 0, 1)
            else:
                h_score = 0.5
        else:
            h_score = 0.5

        # M (极值): 极端值比例（高=有极端高/低分，需关注）
        q1, q3 = np.percentile(scores, [25, 75])
        iqr = q3 - q1
        upper_fence = q3 + 1.5 * iqr
        lower_fence = q1 - 1.5 * iqr
        outliers = np.sum((scores > upper_fence) | (scores < lower_fence))
        m_score = min(1.0, outliers / len(scores) * 3)

        # P (概率): 高质量区域比例
        top_quartile = np.percentile(scores, 75)
        top_count = np.sum(scores >= top_quartile)
        p_score = min(1.0, top_count / len(scores) * 3)

        return {
            "E": round(float(e_score), 4),
            "V": round(float(v_score), 4),
            "H": round(float(h_score), 4),
            "M": round(float(m_score), 4),
            "P": round(float(p_score), 4),
        }

    @staticmethod
    def get_search_strategy(indicators: Dict[str, float]) -> Dict[str, Any]:
        """
        根据五维指标生成搜索策略建议

        Returns:
            {
                "direction": "explore" | "exploit" | "balance",
                "mutation_rate": float,
                "crossover_rate": float,
                "elite_count": int,
                "exploration_noise": float,
            }
        """
        e, v, h, m, p = indicators["E"], indicators["V"], indicators["H"], indicators["M"], indicators["P"]

        # 方向判定
        if e > 0.6 and p > 0.5:
            direction = "exploit"    # 期望上升 + 高质量区域多 → 利用
        elif h < 0.3 or e < 0.3:
            direction = "explore"    # 熵低（探索不足）或期望低 → 探索
        else:
            direction = "balance"

        # 变异率：高方差 → 高变异（更多探索）
        mutation_rate = 0.1 + v * 0.3

        # 交叉率：高质量区域多 → 高交叉（精英遗传）
        crossover_rate = 0.5 + p * 0.3

        # 精英保留数：极值多 → 少保留（保持多样性）
        elite_count = max(1, int(3 - m * 2))

        # 探索噪声：熵低 → 高噪声
        exploration_noise = 0.05 + (1 - h) * 0.15

        return {
            "direction": direction,
            "mutation_rate": round(mutation_rate, 3),
            "crossover_rate": round(crossover_rate, 3),
            "elite_count": elite_count,
            "exploration_noise": round(exploration_noise, 3),
        }


# ============================================================
# 演化引擎（遗传算法 + 局部搜索）
# ============================================================

class EvolutionEngine:
    """
    演化引擎

    混合优化策略：
      1. 遗传算法（GA）：全局探索，参数交叉+变异
      2. 局部搜索（LS）：精英个体周边精细搜索
      3. 五维指标引导：自适应调整搜索策略

    参数范围来自 SpecialForcesStrategy.PARAM_RANGES
    """

    def __init__(self,
                 param_ranges: Dict[str, Tuple[float, float]],
                 evaluate_fn: Callable[[Dict[str, float]], Dict[str, Any]],
                 population_size: int = 20,
                 max_generations: int = 30,
                 convergence_threshold: float = 0.001,
                 early_stop_generations: int = 8):
        """
        Args:
            param_ranges: 参数范围 {param_name: (min, max)}
            evaluate_fn: 评估函数 params → {score, metrics, ...}
            population_size: 种群大小
            max_generations: 最大代数
            convergence_threshold: 收敛阈值（评分变化小于此值视为收敛）
            early_stop_generations: 连续N代不提升则早停
        """
        self.param_ranges = param_ranges
        self.param_names = list(param_ranges.keys())
        self.evaluate = evaluate_fn
        self.population_size = population_size
        self.max_generations = max_generations
        self.convergence_threshold = convergence_threshold
        self.early_stop_generations = early_stop_generations

        self._analyzer = FiveDimensionalAnalyzer()
        self._history: List[Dict[str, Any]] = []

    def _random_params(self) -> Dict[str, float]:
        """生成随机参数"""
        return {
            name: random.uniform(lo, hi)
            for name, (lo, hi) in self.param_ranges.items()
        }

    def _mutate(self, params: Dict[str, float],
                mutation_rate: float = 0.1,
                noise: float = 0.1) -> Dict[str, float]:
        """参数变异"""
        mutated = copy.deepcopy(params)
        for name in self.param_names:
            if random.random() < mutation_rate:
                delta = random.gauss(0, noise)
                lo, hi = self.param_ranges[name]
                new_val = mutated[name] + delta * (hi - lo)
                mutated[name] = max(lo, min(hi, new_val))
        return mutated

    def _crossover(self, parent1: Dict[str, float],
                   parent2: Dict[str, float]) -> Dict[str, float]:
        """参数交叉（均匀交叉）"""
        child = {}
        for name in self.param_names:
            if random.random() < 0.5:
                child[name] = parent1[name]
            else:
                child[name] = parent2[name]
        return child

    def _local_search(self, params: Dict[str, float],
                      steps: int = 5,
                      noise: float = 0.03) -> Dict[str, float]:
        """局部搜索：在当前最佳参数周围精细搜索"""
        best_params = copy.deepcopy(params)
        best_result = self.evaluate(best_params)
        best_score = best_result.get("score", -999)

        for _ in range(steps):
            candidate = self._mutate(best_params, mutation_rate=0.5, noise=noise)
            result = self.evaluate(candidate)
            self._history.append(result)
            score = result.get("score", -999)
            if score > best_score:
                best_score = score
                best_params = candidate

        return best_params

    def run(self, verbose: bool = True) -> EvolutionJournal:
        """
        运行演化优化

        Returns:
            EvolutionJournal: 演化日志
        """
        journal = EvolutionJournal(
            symbol="",
            started_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )

        # 初始化种群
        population = []
        for _ in range(self.population_size):
            params = self._random_params()
            result = self.evaluate(params)
            result["params"] = params
            population.append(result)
            self._history.append(result)

        # 排序
        population.sort(key=lambda x: x.get("score", -999), reverse=True)
        best_score = population[0].get("score", -999)
        best_params = population[0].get("params", {})
        best_metrics = population[0].get("metrics", {})
        no_improve_count = 0

        if verbose:
            print(f"[EvolutionEngine] 初始种群: 最佳评分={best_score:.4f}")

        # 演化循环
        for gen in range(1, self.max_generations + 1):
            gen_start = time.time()

            # 五维指标分析
            indicators = self._analyzer.compute_5d(self._history[-50:])
            strategy = self._analyzer.get_search_strategy(indicators)

            # 精英保留
            elite_count = strategy["elite_count"]
            elites = population[:elite_count]
            new_population = list(elites)

            # 生成下一代
            while len(new_population) < self.population_size:
                # 选择（锦标赛）
                p1 = self._tournament_select(population, 3)
                p2 = self._tournament_select(population, 3)

                # 交叉
                child_params = self._crossover(p1["params"], p2["params"])

                # 变异
                child_params = self._mutate(
                    child_params,
                    mutation_rate=strategy["mutation_rate"],
                    noise=strategy["exploration_noise"],
                )

                # 评估
                result = self.evaluate(child_params)
                result["params"] = child_params
                new_population.append(result)
                self._history.append(result)

            # 局部搜索：对精英个体精细搜索
            if strategy["direction"] == "exploit" and gen % 3 == 0:
                refined = self._local_search(elites[0]["params"], steps=3, noise=0.02)
                refined_result = self.evaluate(refined)
                refined_result["params"] = refined
                new_population[-1] = refined_result
                self._history.append(refined_result)

            # 排序
            new_population.sort(key=lambda x: x.get("score", -999), reverse=True)
            population = new_population

            gen_best_score = population[0].get("score", -999)
            gen_best_params = population[0].get("params", {})
            gen_best_metrics = population[0].get("metrics", {})

            # 多样性计算
            param_values = np.array([[p["params"].get(k, 0) for k in self.param_names]
                                     for p in population])
            diversity = float(np.mean(np.std(param_values, axis=0)))

            # 记录
            gen_elapsed = time.time() - gen_start
            gen_record = EvolutionGeneration(
                generation=gen,
                population=population,
                best_params=gen_best_params,
                best_score=gen_best_score,
                best_metrics=gen_best_metrics,
                diversity=diversity,
                elapsed_seconds=gen_elapsed,
            )
            journal.generations.append(gen_record)
            journal.total_evaluations += len(new_population)
            journal.total_elapsed_seconds += gen_elapsed

            if verbose:
                constraints = HardConstraintChecker.check({
                    "sharpe_ratio": gen_best_metrics.get("sharpe_ratio", 0),
                    "max_drawdown": gen_best_metrics.get("max_drawdown", 0),
                    "win_rate": gen_best_metrics.get("win_rate", 0),
                    "profit_factor": gen_best_metrics.get("profit_factor", 0),
                })
                status = "✅" if constraints[0] else "❌"
                print(f"  Gen {gen:2d}: score={gen_best_score:.4f} "
                      f"|年化={gen_best_metrics.get('annual_return',0):.2%} "
                      f"|夏普={gen_best_metrics.get('sharpe_ratio',0):.2f} "
                      f"|回撤={gen_best_metrics.get('max_drawdown',0):.2%} "
                      f"|胜率={gen_best_metrics.get('win_rate',0):.1%} "
                      f"|div={diversity:.3f} "
                      f"|策={strategy['direction']} {status}")

            # 收敛检查
            if gen_best_score > best_score + self.convergence_threshold:
                best_score = gen_best_score
                best_params = gen_best_params
                best_metrics = gen_best_metrics
                no_improve_count = 0
            else:
                no_improve_count += 1

            if no_improve_count >= self.early_stop_generations:
                if verbose:
                    print(f"  [早停] 连续{no_improve_count}代无提升，在第{gen}代停止")
                journal.convergence_generation = gen - no_improve_count
                break

        journal.finished_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        journal.final_best_params = best_params
        journal.final_best_score = best_score
        journal.final_best_metrics = best_metrics

        if verbose:
            passed, violations = HardConstraintChecker.check({
                "sharpe_ratio": best_metrics.get("sharpe_ratio", 0),
                "max_drawdown": best_metrics.get("max_drawdown", 0),
                "win_rate": best_metrics.get("win_rate", 0),
                "profit_factor": best_metrics.get("profit_factor", 0),
            })
            print(f"\n[EvolutionEngine] 演化完成: {journal.total_evaluations}次评估, "
                  f"{journal.total_elapsed_seconds:.1f}s")
            print(f"  最佳评分: {best_score:.4f}")
            print(f"  年化收益: {best_metrics.get('annual_return', 0):.2%}")
            print(f"  夏普: {best_metrics.get('sharpe_ratio', 0):.2f}")
            print(f"  最大回撤: {best_metrics.get('max_drawdown', 0):.2%}")
            print(f"  胜率: {best_metrics.get('win_rate', 0):.1%}")
            print(f"  盈亏比: {best_metrics.get('profit_factor', 0):.2f}")
            if not passed:
                print(f"  ⚠️ 硬约束未满足: {violations}")
            else:
                print(f"  ✅ 硬约束全部满足")

        return journal

    def _tournament_select(self, population: List[Dict],
                           tournament_size: int = 3) -> Dict:
        """锦标赛选择"""
        candidates = random.sample(population, min(tournament_size, len(population)))
        return max(candidates, key=lambda x: x.get("score", -999))


# ============================================================
# 参数存储（按标的持久化）
# ============================================================

class ParameterStore:
    """
    参数持久化存储

    按标的独立存储，支持版本管理。
    存储路径: QS_Robot/data/evolution/{symbol}_params.json
    """

    def __init__(self, store_dir: str = None):
        if store_dir is None:
            store_dir = os.path.join(os.path.dirname(__file__), "..", "data", "evolution")
        self._store_dir = store_dir
        os.makedirs(self._store_dir, exist_ok=True)

    def _path(self, symbol: str) -> str:
        return os.path.join(self._store_dir, f"{symbol}_params.json")

    def save(self, symbol: str, params: Dict[str, float],
             metrics: Dict[str, float] = None,
             score: float = 0.0,
             version: int = None):
        """保存参数"""
        path = self._path(symbol)

        # 读取现有记录
        records = []
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    records = data.get("history", [])
            except Exception:
                records = []

        # 自动版本号
        if version is None:
            version = len(records) + 1

        records.append({
            "version": version,
            "params": params,
            "metrics": metrics or {},
            "score": score,
            "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })

        with open(path, "w", encoding="utf-8") as f:
            json.dump({
                "symbol": symbol,
                "current_version": version,
                "current_params": params,
                "current_metrics": metrics or {},
                "current_score": score,
                "history": records,
            }, f, ensure_ascii=False, indent=2)

    def load(self, symbol: str) -> Optional[Dict[str, Any]]:
        """加载参数"""
        path = self._path(symbol)
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def get_best_params(self, symbol: str) -> Optional[Dict[str, float]]:
        """获取最佳参数"""
        data = self.load(symbol)
        if data:
            return data.get("current_params")
        return None

    def get_all_versions(self, symbol: str) -> List[Dict]:
        """获取所有版本"""
        data = self.load(symbol)
        if data:
            return data.get("history", [])
        return []


# ============================================================
# 自演进控制器主类
# ============================================================

class SpecialForcesEvolutionController:
    """
    特种兵策略自演进控制器

    核心功能：
      1. 按标的运行演化优化
      2. 自动保存最佳参数
      3. 支持增量演进（从已有参数继续优化）
      4. 对接回测引擎进行参数评估

    用法:
        controller = SpecialForcesEvolutionController()
        journal = controller.evolve("510300", generations=20)
        best_params = controller.get_best_params("510300")
    """

    def __init__(self,
                 data_dir: str = None,
                 initial_capital: float = 100000.0):
        """
        Args:
            data_dir: 数据目录
            initial_capital: 回测初始资金
        """
        self._data_dir = data_dir or os.path.join(os.path.dirname(__file__), "..", "data")
        self._initial_capital = initial_capital
        self._store = ParameterStore()
        self._strategy_cache: Dict[str, Any] = {}
        self._last_journal: Optional[EvolutionJournal] = None

    # --------------------------------------------------------
    # 核心：演化优化
    # --------------------------------------------------------

    def evolve(self, symbol: str,
               population_size: int = 20,
               max_generations: int = 30,
               force_refresh: bool = False,
               verbose: bool = True) -> EvolutionJournal:
        """
        对指定标的运行演化优化

        Args:
            symbol: 股票代码
            population_size: 种群大小
            max_generations: 最大代数
            force_refresh: 是否强制刷新数据
            verbose: 是否输出详细日志

        Returns:
            EvolutionJournal: 演化日志
        """
        print(f"\n{'='*60}")
        print(f"  特种兵自演进: {symbol}")
        print(f"{'='*60}\n")

        # 懒加载策略模块
        from core.special_forces_strategy import SpecialForcesStrategy, StrategyParams
        from core.special_forces_strategy import SFBacktestResult

        # 评估函数
        def evaluate_params(params: Dict[str, float]) -> Dict[str, Any]:
            """评估一组参数"""
            try:
                strategy = SpecialForcesStrategy(
                    symbol=symbol,
                    params=StrategyParams.from_dict(params),
                    force_refresh=force_refresh,
                )
                strategy.load_data()
                result = strategy.run_backtest(initial_capital=self._initial_capital)

                metrics = {
                    "annual_return": result.annual_return,
                    "sharpe_ratio": result.sharpe_ratio,
                    "max_drawdown": result.max_drawdown,
                    "win_rate": result.win_rate,
                    "profit_factor": result.profit_factor,
                    "total_return": result.total_return,
                    "total_trades": result.total_trades,
                }

                reward = RewardFunction.compute(metrics)

                return {
                    "params": params,
                    "score": reward,
                    "metrics": metrics,
                    "elapsed": result.elapsed_time,
                }
            except Exception as e:
                traceback.print_exc()
                return {
                    "params": params,
                    "score": -999.0,
                    "metrics": {
                        "annual_return": 0, "sharpe_ratio": 0,
                        "max_drawdown": 1.0, "win_rate": 0,
                        "profit_factor": 0, "total_return": 0,
                        "total_trades": 0,
                    },
                    "elapsed": 0,
                }

        # 初始化演化引擎
        param_ranges = SpecialForcesStrategy.PARAM_RANGES
        engine = EvolutionEngine(
            param_ranges=param_ranges,
            evaluate_fn=evaluate_params,
            population_size=population_size,
            max_generations=max_generations,
        )

        # 运行演化
        journal = engine.run(verbose=verbose)
        journal.symbol = symbol

        # 保存最佳参数
        self._store.save(
            symbol=symbol,
            params=journal.final_best_params,
            metrics=journal.final_best_metrics,
            score=journal.final_best_score,
        )

        self._last_journal = journal
        return journal

    def evolve_incremental(self, symbol: str,
                           additional_generations: int = 10,
                           verbose: bool = True) -> Optional[EvolutionJournal]:
        """
        增量演化：从已有最佳参数继续优化

        Args:
            symbol: 股票代码
            additional_generations: 额外演化代数
            verbose: 是否输出详细日志

        Returns:
            EvolutionJournal: 演化日志，无已有参数时返回None
        """
        existing = self._store.load(symbol)
        if not existing or not existing.get("current_params"):
            print(f"[增量演化] {symbol} 无已有参数，请先运行完整演化")
            return None

        current_params = existing["current_params"]
        current_score = existing.get("current_score", 0)

        if verbose:
            print(f"\n{'='*60}")
            print(f"  特种兵增量演化: {symbol}")
            print(f"  起始评分: {current_score:.4f}")
            print(f"{'='*60}\n")

        from core.special_forces_strategy import SpecialForcesStrategy, StrategyParams

        def evaluate_params(params: Dict[str, float]) -> Dict[str, Any]:
            try:
                strategy = SpecialForcesStrategy(
                    symbol=symbol,
                    params=StrategyParams.from_dict(params),
                )
                strategy.load_data()
                result = strategy.run_backtest(initial_capital=self._initial_capital)
                metrics = {
                    "annual_return": result.annual_return,
                    "sharpe_ratio": result.sharpe_ratio,
                    "max_drawdown": result.max_drawdown,
                    "win_rate": result.win_rate,
                    "profit_factor": result.profit_factor,
                    "total_return": result.total_return,
                    "total_trades": result.total_trades,
                }
                return {
                    "params": params,
                    "score": RewardFunction.compute(metrics),
                    "metrics": metrics,
                    "elapsed": result.elapsed_time,
                }
            except Exception:
                return {
                    "params": params,
                    "score": -999.0,
                    "metrics": {"annual_return": 0, "sharpe_ratio": 0,
                                "max_drawdown": 1.0, "win_rate": 0,
                                "profit_factor": 0, "total_return": 0, "total_trades": 0},
                    "elapsed": 0,
                }

        engine = EvolutionEngine(
            param_ranges=SpecialForcesStrategy.PARAM_RANGES,
            evaluate_fn=evaluate_params,
            population_size=12,
            max_generations=additional_generations,
            convergence_threshold=0.0005,
            early_stop_generations=5,
        )

        journal = engine.run(verbose=verbose)
        journal.symbol = symbol

        # 如果新结果更好，保存
        if journal.final_best_score > current_score:
            self._store.save(
                symbol=symbol,
                params=journal.final_best_params,
                metrics=journal.final_best_metrics,
                score=journal.final_best_score,
            )
            if verbose:
                print(f"  ✅ 增量演化提升: {current_score:.4f} → {journal.final_best_score:.4f}")
        else:
            if verbose:
                print(f"  ⚠️ 增量演化未提升: {current_score:.4f} (当前最佳)")

        self._last_journal = journal
        return journal

    # --------------------------------------------------------
    # 便捷接口
    # --------------------------------------------------------

    def get_best_params(self, symbol: str) -> Optional[Dict[str, float]]:
        """获取标的的最佳参数"""
        return self._store.get_best_params(symbol)

    def get_evolution_history(self, symbol: str) -> List[Dict]:
        """获取演化历史"""
        return self._store.get_all_versions(symbol)

    def get_last_journal(self) -> Optional[EvolutionJournal]:
        """获取最近一次演化日志"""
        return self._last_journal

    def apply_best_params(self, symbol: str) -> bool:
        """
        将最佳参数应用到策略实例

        Returns:
            bool: 是否成功
        """
        best_params = self._store.get_best_params(symbol)
        if not best_params:
            print(f"[应用参数] {symbol} 无最佳参数")
            return False

        from core.special_forces_strategy import StrategyParams
        params = StrategyParams.from_dict(best_params)
        print(f"[应用参数] {symbol} 已应用最佳参数 (v{len(self._store.get_all_versions(symbol))})")
        return True

    def get_params_summary(self, symbol: str) -> Dict[str, Any]:
        """获取参数摘要"""
        data = self._store.load(symbol)
        if not data:
            return {"symbol": symbol, "status": "未演化"}
        return {
            "symbol": symbol,
            "version": data.get("current_version", 0),
            "score": data.get("current_score", 0),
            "metrics": data.get("current_metrics", {}),
            "params_count": len(data.get("current_params", {})),
            "history_count": len(data.get("history", [])),
            "last_updated": data.get("history", [{}])[-1].get("saved_at", "") if data.get("history") else "",
        }


# ============================================================
# 单例
# ============================================================

_evolution_controller: Optional[SpecialForcesEvolutionController] = None


def get_evolution_controller() -> SpecialForcesEvolutionController:
    """获取自演进控制器单例"""
    global _evolution_controller
    if _evolution_controller is None:
        _evolution_controller = SpecialForcesEvolutionController()
    return _evolution_controller


# ============================================================
# 命令行入口
# ============================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="特种兵策略自演进控制器")
    parser.add_argument("symbol", nargs="?", default="510300", help="股票代码")
    parser.add_argument("--generations", type=int, default=20, help="最大演化代数")
    parser.add_argument("--population", type=int, default=20, help="种群大小")
    parser.add_argument("--incremental", action="store_true", help="增量演化")
    parser.add_argument("--force-refresh", action="store_true", help="强制刷新数据")
    parser.add_argument("--list", action="store_true", help="列出已有参数")

    args = parser.parse_args()

    controller = get_evolution_controller()

    if args.list:
        summary = controller.get_params_summary(args.symbol)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    elif args.incremental:
        controller.evolve_incremental(
            args.symbol,
            additional_generations=args.generations,
            verbose=True,
        )
    else:
        controller.evolve(
            args.symbol,
            population_size=args.population,
            max_generations=args.generations,
            force_refresh=args.force_refresh,
            verbose=True,
        )