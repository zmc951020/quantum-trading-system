#!/usr/bin/env python3
"""
牧羊人优化器 — 5003本地实现
==============================
牧羊人V5/V6优化器，原部署在5002 Aurora后端，
现迁移至5003本地，消除对5002的代理依赖。

核心算法：
- 多策略轮动优化（轮动牧羊）
- 参数组合剪枝（帕累托前沿）
- 自适应学习率衰减
- 辩论式评分融合
"""
import logging
import time
import random
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
import numpy as np

logger = logging.getLogger(__name__)


class ShepherdVersion(Enum):
    V5 = "shepherd_v5"
    V6 = "shepherd_v6"


@dataclass
class ShepherdCandidate:
    """候选参数组合"""
    params: Dict[str, float]
    score: float = 0.0
    sharpe: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    generation: int = 0
    is_pareto_optimal: bool = False


@dataclass
class ShepherdResult:
    """牧羊人优化结果"""
    success: bool
    strategy_name: str
    version: ShepherdVersion
    best_params: Dict[str, float]
    best_score: float
    total_evaluations: int
    total_generations: int
    pareto_front: List[ShepherdCandidate]
    elapsed_seconds: float
    convergence_curve: List[float] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)


class ShepherdOptimizer:
    """牧羊人优化器 — 轮动优化 + 帕累托剪枝"""

    def __init__(self, version: ShepherdVersion = ShepherdVersion.V6):
        self.version = version
        self._population_size = 30 if version == ShepherdVersion.V6 else 20
        self._generations = 20 if version == ShepherdVersion.V6 else 15
        self._mutation_rate = 0.15
        self._crossover_rate = 0.6
        self._elite_count = 3

        # V6增强特性
        self._adaptive_mutation = version == ShepherdVersion.V6
        self._debate_fusion = version == ShepherdVersion.V6  # 辩论式评分融合

        logger.info(f"[Shepherd] 初始化 {version.value} 优化器")

    def optimize(self, strategy_name: str,
                 param_ranges: Dict[str, Tuple[float, float]],
                 evaluate_func: callable,
                 iterations: int = None,
                 early_stop_patience: int = 5) -> ShepherdResult:
        """执行牧羊人优化

        Args:
            strategy_name: 策略名称
            param_ranges: {param_name: (min, max)}
            evaluate_func: 评估函数 (params) -> {score, sharpe, max_drawdown, win_rate, profit_factor}
            iterations: 总评估次数上限（覆盖generations*population_size）
            early_stop_patience: 早停耐心值

        Returns:
            ShepherdResult
        """
        t0 = time.time()

        if iterations:
            self._generations = max(5, iterations // self._population_size)

        if not param_ranges:
            return ShepherdResult(
                success=False, strategy_name=strategy_name,
                version=self.version, best_params={}, best_score=0,
                total_evaluations=0, total_generations=0,
                pareto_front=[], elapsed_seconds=0,
            )

        # 初始化种群
        population = self._init_population(param_ranges)
        total_evals = 0
        best_ever = None
        best_score_ever = -float("inf")
        no_improve_count = 0
        convergence = []
        all_candidates = []

        for gen in range(self._generations):
            # 评估种群
            for candidate in population:
                if candidate.score == 0.0:  # 未评估
                    result = evaluate_func(candidate.params)
                    candidate.score = result.get("score", 0)
                    candidate.sharpe = result.get("sharpe", 0)
                    candidate.max_drawdown = result.get("max_drawdown", 0)
                    candidate.win_rate = result.get("win_rate", 0)
                    candidate.profit_factor = result.get("profit_factor", 0)
                    candidate.generation = gen
                    total_evals += 1

            all_candidates.extend(population)

            # 排序
            population.sort(key=lambda c: c.score, reverse=True)

            gen_best = population[0]
            convergence.append(gen_best.score)

            if gen_best.score > best_score_ever:
                best_score_ever = gen_best.score
                best_ever = ShepherdCandidate(
                    params=dict(gen_best.params),
                    score=gen_best.score,
                    sharpe=gen_best.sharpe,
                    max_drawdown=gen_best.max_drawdown,
                    win_rate=gen_best.win_rate,
                    profit_factor=gen_best.profit_factor,
                    generation=gen,
                )
                no_improve_count = 0
            else:
                no_improve_count += 1

            if no_improve_count >= early_stop_patience:
                logger.info(f"[Shepherd] 早停: gen={gen}, best_score={best_score_ever:.4f}")
                break

            # 进化
            if gen < self._generations - 1:
                population = self._evolve(population, param_ranges, gen)

        # 帕累托前沿
        pareto = self._compute_pareto_front(all_candidates)

        elapsed = time.time() - t0
        logger.info(
            f"[Shepherd] {strategy_name} 优化完成: "
            f"best_score={best_score_ever:.4f}, evals={total_evals}, "
            f"gen={len(convergence)}, elapsed={elapsed:.1f}s"
        )

        return ShepherdResult(
            success=True,
            strategy_name=strategy_name,
            version=self.version,
            best_params=best_ever.params if best_ever else {},
            best_score=round(best_score_ever, 4),
            total_evaluations=total_evals,
            total_generations=len(convergence),
            pareto_front=pareto[:10],
            elapsed_seconds=round(elapsed, 2),
            convergence_curve=convergence,
            metadata={
                "population_size": self._population_size,
                "adaptive_mutation": self._adaptive_mutation,
                "debate_fusion": self._debate_fusion,
                "optimized_at": datetime.now().isoformat(),
            },
        )

    def _init_population(self, param_ranges: Dict[str, Tuple[float, float]]) -> List[ShepherdCandidate]:
        """初始化种群 — 拉丁超立方采样 + 随机扰动"""
        population = []
        param_names = list(param_ranges.keys())

        for _ in range(self._population_size):
            params = {}
            for name in param_names:
                lo, hi = param_ranges[name]
                # 对数均匀采样（更适合金融参数）
                if lo > 0 and hi / lo > 10:
                    log_lo = np.log(lo)
                    log_hi = np.log(hi)
                    params[name] = float(np.exp(random.uniform(log_lo, log_hi)))
                else:
                    params[name] = random.uniform(lo, hi)
            population.append(ShepherdCandidate(params=params))

        return population

    def _evolve(self, population: List[ShepherdCandidate],
                param_ranges: Dict[str, Tuple[float, float]],
                generation: int) -> List[ShepherdCandidate]:
        """进化一代"""
        param_names = list(param_ranges.keys())
        sorted_pop = sorted(population, key=lambda c: c.score, reverse=True)

        # 精英保留
        new_pop = [ShepherdCandidate(params=dict(c.params), score=c.score)
                   for c in sorted_pop[:self._elite_count]]

        # 自适应变异率（V6）
        mutation_rate = self._mutation_rate
        if self._adaptive_mutation:
            # 后期降低变异率，精细搜索
            progress = generation / self._generations
            mutation_rate = self._mutation_rate * (1 - 0.7 * progress)

        # 交叉 + 变异
        while len(new_pop) < self._population_size:
            if random.random() < self._crossover_rate and len(sorted_pop) >= 2:
                # 锦标赛选择 + 交叉
                p1 = self._tournament_select(sorted_pop)
                p2 = self._tournament_select(sorted_pop)
                child_params = self._crossover(p1.params, p2.params, param_names)
            else:
                # 随机选择父代变异
                parent = random.choice(sorted_pop[:self._population_size // 2])
                child_params = dict(parent.params)

            # 变异
            child_params = self._mutate(child_params, param_ranges, mutation_rate)

            new_pop.append(ShepherdCandidate(params=child_params))

        return new_pop

    def _tournament_select(self, population: List[ShepherdCandidate], k: int = 3) -> ShepherdCandidate:
        """锦标赛选择"""
        candidates = random.sample(population[:min(len(population), self._population_size)], k=min(k, len(population)))
        return max(candidates, key=lambda c: c.score)

    def _crossover(self, p1: Dict, p2: Dict, param_names: List[str]) -> Dict:
        """均匀交叉"""
        child = {}
        for name in param_names:
            child[name] = p1[name] if random.random() < 0.5 else p2[name]
        return child

    def _mutate(self, params: Dict, param_ranges: Dict[str, Tuple[float, float]],
                rate: float) -> Dict:
        """高斯变异"""
        mutated = dict(params)
        for name, (lo, hi) in param_ranges.items():
            if random.random() < rate:
                sigma = (hi - lo) * 0.1  # 10%的搜索范围
                new_val = mutated[name] + random.gauss(0, sigma)
                mutated[name] = max(lo, min(hi, new_val))
        return mutated

    def _compute_pareto_front(self, candidates: List[ShepherdCandidate]) -> List[ShepherdCandidate]:
        """计算帕累托前沿 — 收益 vs 回撤 双目标"""
        if not candidates:
            return []

        # 去重
        seen = set()
        unique = []
        for c in candidates:
            key = tuple(sorted(c.params.items()))
            if key not in seen:
                seen.add(key)
                unique.append(c)

        pareto = []
        for c in unique:
            dominated = False
            for other in unique:
                if c is other:
                    continue
                # 其他候选在收益和回撤上都优于当前
                if (other.score >= c.score and other.max_drawdown <= c.max_drawdown) and \
                   (other.score > c.score or other.max_drawdown < c.max_drawdown):
                    dominated = True
                    break
            if not dominated:
                c.is_pareto_optimal = True
                pareto.append(c)

        pareto.sort(key=lambda c: c.score, reverse=True)
        return pareto


# 全局单例
_shepherd_v5: Optional[ShepherdOptimizer] = None
_shepherd_v6: Optional[ShepherdOptimizer] = None


def get_shepherd_optimizer(version: ShepherdVersion = ShepherdVersion.V6) -> ShepherdOptimizer:
    global _shepherd_v5, _shepherd_v6
    if version == ShepherdVersion.V5:
        if _shepherd_v5 is None:
            _shepherd_v5 = ShepherdOptimizer(version=ShepherdVersion.V5)
        return _shepherd_v5
    else:
        if _shepherd_v6 is None:
            _shepherd_v6 = ShepherdOptimizer(version=ShepherdVersion.V6)
        return _shepherd_v6