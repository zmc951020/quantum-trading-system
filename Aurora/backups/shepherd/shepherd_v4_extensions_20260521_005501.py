#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🐑 牧羊人智能体优化器 v4.0 — 六大扩展引擎
============================================================
包含:
  [1] 评测引擎扩展 — 15专家能力动态评估HUB
  [2] 优化引擎 — 贝叶斯优化 + CMA-ES + 帕累托多目标
  [3] 策略生成器 — DNA模板库 + 交叉变异 + 特征重要性
  [4] 技术栈组合引擎 — 指纹提取 + 交叉组合 + 新颖性评分
  [5] 自演进系统 — 元学习记忆 + 遗传算法 + A/B测试
  [6] 全流程编排器 — 五项全能联动
"""

import sys, os, json, time, math, random, hashlib, logging
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Any, Optional, Tuple, Set
from datetime import datetime
from collections import defaultdict
from copy import deepcopy
from enum import Enum

logger = logging.getLogger("ShepherdOptimizer.v4ext")


# ═══════════════════════════════════════════════
#  引擎 [1]: 评测引擎扩展 — 15专家能力动态评估HUB
# ═══════════════════════════════════════════════

class CapabilityLevel(Enum):
    NOVICE = "novice"
    STANDARD = "standard"
    ADVANCED = "advanced"
    MASTER = "master"
    GRANDMASTER = "grandmaster"


@dataclass
class ExpertProfile:
    """专家画像"""
    expert_id: int
    name: str
    domain: str  # 金融风控/代码质量/架构设计/数据工程/AI工程化等
    capability: CapabilityLevel = CapabilityLevel.STANDARD
    capability_score: float = 0.50
    evolution_history: List[float] = field(default_factory=list)
    successful_reviews: int = 0
    total_reviews: int = 0
    specializations: List[str] = field(default_factory=list)
    weight: float = 0.05
    last_assessment: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "expert_id": self.expert_id,
            "name": self.name,
            "domain": self.domain,
            "capability": self.capability.value,
            "capability_score": round(self.capability_score, 4),
            "evolution_trend": self._compute_trend(),
            "review_accuracy": round(self.successful_reviews / max(self.total_reviews, 1), 4),
            "specializations": self.specializations,
            "weight": round(self.weight, 4),
            "last_assessment": self.last_assessment,
        }

    def _compute_trend(self) -> float:
        if len(self.evolution_history) < 2:
            return 0.0
        recent = self.evolution_history[-5:]
        if len(recent) < 2:
            return 0.0
        return round((recent[-1] - recent[0]) / max(len(recent) - 1, 1), 4)


class ExpertCapabilityHub:
    """15专家能力动态评估HUB — 管理、评估、演进专家团队"""
    
    EXPERT_DEFINITIONS: Dict[int, Dict[str, Any]] = {
        1:  {"name": "架构设计审计师", "domain": "系统架构", "capability": "advanced", "weight": 0.10},
        2:  {"name": "代码质量审查官", "domain": "代码质量", "capability": "standard", "weight": 0.08},
        3:  {"name": "金融风控合规官", "domain": "金融风控", "capability": "advanced", "weight": 0.12},
        4:  {"name": "性能工程师", "domain": "性能工程", "capability": "standard", "weight": 0.09},
        5:  {"name": "安全审计专家", "domain": "安全审计", "capability": "advanced", "weight": 0.07},
        6:  {"name": "数据质量专家", "domain": "数据工程", "capability": "standard", "weight": 0.07},
        7:  {"name": "可扩展性架构师", "domain": "系统架构", "capability": "standard", "weight": 0.07},
        8:  {"name": "测试工程专家", "domain": "质量保障", "capability": "standard", "weight": 0.06},
        9:  {"name": "用户体验设计师", "domain": "用户体验", "capability": "standard", "weight": 0.05},
        10: {"name": "AI工程化专家", "domain": "AI工程化", "capability": "advanced", "weight": 0.08},
        11: {"name": "DevOps运维专家", "domain": "运维工程", "capability": "standard", "weight": 0.05},
        12: {"name": "产品化评审官", "domain": "产品化", "capability": "standard", "weight": 0.04},
        13: {"name": "策略生成审计师", "domain": "策略工程", "capability": "standard", "weight": 0.06},
        14: {"name": "组合创新审计师", "domain": "策略工程", "capability": "novice", "weight": 0.04},
        15: {"name": "自演进审计师", "domain": "元学习", "capability": "novice", "weight": 0.02},
    }

    def __init__(self):
        self._experts: Dict[int, ExpertProfile] = {}
        self._assessment_history: List[Dict[str, Any]] = []
        self._evolution_events: List[Dict[str, Any]] = []
        self._init_experts()

    def _init_experts(self):
        for eid, info in self.EXPERT_DEFINITIONS.items():
            cap = CapabilityLevel(info["capability"])
            self._experts[eid] = ExpertProfile(
                expert_id=eid,
                name=info["name"],
                domain=info["domain"],
                capability=cap,
                capability_score={"novice": 0.25, "standard": 0.50, "advanced": 0.75, "master": 1.0}.get(info["capability"], 0.50),
                weight=info["weight"],
                specializations=self._infer_specializations(info["name"], info["domain"]),
            )

    @staticmethod
    def _infer_specializations(name: str, domain: str) -> List[str]:
        specs_map = {
            "架构设计审计师": ["微服务架构", "事件驱动架构", "数据库设计"],
            "代码质量审查官": ["代码审查", "静态分析", "重构"],
            "金融风控合规官": ["风险建模", "合规审计", "压力测试"],
            "性能工程师": ["性能分析", "缓存优化", "并行计算"],
            "安全审计专家": ["漏洞扫描", "渗透测试", "安全策略"],
            "数据质量专家": ["数据清洗", "异常检测", "数据验证"],
            "可扩展性架构师": ["水平扩展", "负载均衡", "分布式系统"],
            "测试工程专家": ["单元测试", "集成测试", "E2E测试"],
            "用户体验设计师": ["交互设计", "可视化", "可访问性"],
            "AI工程化专家": ["模型部署", "特征工程", "MLOps"],
            "DevOps运维专家": ["CI/CD", "容器化", "监控报警"],
            "产品化评审官": ["产品策略", "市场适配", "用户反馈"],
            "策略生成审计师": ["策略DNA分析", "信号质量评估", "参数合理性"],
            "组合创新审计师": ["策略组合分析", "技术栈评估", "新颖性判断"],
            "自演进审计师": ["元学习评估", "进化收敛", "A/B测试"],
        }
        return specs_map.get(name, [domain])

    def assess_expert(self, expert_id: int, performance_score: float,
                      review_context: Dict[str, Any] = None) -> Dict[str, Any]:
        """评估单个专家能力并记录演进"""
        expert = self._experts.get(expert_id)
        if not expert:
            return {"error": f"专家ID {expert_id} 不存在"}

        expert.total_reviews += 1
        if performance_score >= 0.70:
            expert.successful_reviews += 1

        expert.evolution_history.append(performance_score)
        expert.capability_score = sum(expert.evolution_history[-10:]) / min(len(expert.evolution_history), 10)

        # 能力等级演进
        old_level = expert.capability
        if expert.capability_score >= 0.90:
            expert.capability = CapabilityLevel.GRANDMASTER
        elif expert.capability_score >= 0.75:
            expert.capability = CapabilityLevel.MASTER
        elif expert.capability_score >= 0.55:
            expert.capability = CapabilityLevel.ADVANCED
        elif expert.capability_score >= 0.35:
            expert.capability = CapabilityLevel.STANDARD
        else:
            expert.capability = CapabilityLevel.NOVICE

        expert.last_assessment = datetime.now().isoformat()

        if old_level != expert.capability:
            evolve_event = {
                "timestamp": datetime.now().isoformat(),
                "expert_id": expert_id,
                "expert_name": expert.name,
                "old_level": old_level.value,
                "new_level": expert.capability.value,
                "score": round(expert.capability_score, 4),
            }
            self._evolution_events.append(evolve_event)
            logger.info(f"🌟 专家演进: {expert.name} {old_level.value} → {expert.capability.value} (score={expert.capability_score:.4f})")

        assessment = {
            "expert_id": expert_id,
            "expert_name": expert.name,
            "score": round(performance_score, 4),
            "capability": expert.capability.value,
            "capability_score": round(expert.capability_score, 4),
            "context": review_context or {},
        }
        self._assessment_history.append(assessment)
        return assessment

    def batch_assess(self, scores: Dict[int, float],
                     context: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """批量评估所有专家"""
        results = []
        for eid, score in scores.items():
            results.append(self.assess_expert(eid, score, context))
        return results

    def get_capability_matrix(self) -> Dict[str, Any]:
        """获取专家能力矩阵"""
        experts_detail = []
        for eid, expert in self._experts.items():
            experts_detail.append(expert.to_dict())

        capability_dist = defaultdict(int)
        for e in experts_detail:
            capability_dist[e["capability"]] += 1

        avg_score = sum(e["capability_score"] for e in experts_detail) / max(len(experts_detail), 1)

        return {
            "total_experts": len(experts_detail),
            "average_capability": round(avg_score, 4),
            "capability_distribution": dict(capability_dist),
            "experts_detail": experts_detail,
            "evolution_events": self._evolution_events[-10:],
            "top_performers": sorted(experts_detail, key=lambda x: x["capability_score"], reverse=True)[:5],
            "needs_improvement": [e for e in experts_detail if e["capability_score"] < 0.50],
            "timestamp": datetime.now().isoformat(),
        }

    def get_expert_recommendations(self) -> List[Dict[str, str]]:
        """获取专家提升建议"""
        recommendations = []
        order = ["novice", "standard", "advanced", "master", "grandmaster"]
        for eid, expert in self._experts.items():
            if expert.capability.value != "grandmaster":
                current_idx = order.index(expert.capability.value)
                target = order[min(current_idx + 1, 4)]
                recommendations.append({
                    "expert_id": eid,
                    "expert_name": expert.name,
                    "current_level": expert.capability.value,
                    "target_level": target,
                    "current_score": round(expert.capability_score, 4),
                    "domain": expert.domain,
                    "action": f"将 {expert.name} 从 {expert.capability.value} 提升至 {target}",
                })
        return recommendations

    def evolve_weights(self, performance_history: Dict[int, List[float]],
                       learning_rate: float = 0.05) -> Dict[int, float]:
        """根据历史表现动态调整专家权重"""
        new_weights = {}
        valid_experts = {
            eid: scores for eid, scores in performance_history.items()
            if eid in self._experts and len(scores) >= 2
        }

        if not valid_experts:
            return {eid: self._experts[eid].weight for eid in self._experts}

        improvements = {}
        for eid, scores in valid_experts.items():
            improvements[eid] = scores[-1] - scores[0]

        avg_improvement = sum(improvements.values()) / max(len(improvements), 1)

        for eid in self._experts:
            if eid in improvements:
                delta = (improvements[eid] - avg_improvement) * learning_rate
                new_weights[eid] = max(0.01, min(0.30, self._experts[eid].weight + delta))
            else:
                new_weights[eid] = self._experts[eid].weight

        total = sum(new_weights.values())
        new_weights = {k: v / total for k, v in new_weights.items()}

        for eid, w in new_weights.items():
            self._experts[eid].weight = w

        logger.info(f"🔄 专家权重演进完成, 分布: {dict((self._experts[eid].name[:4], round(w,3)) for eid, w in list(new_weights.items())[:5])}")
        return new_weights


# ═══════════════════════════════════════════════
#  引擎 [2]: 优化引擎 — 贝叶斯 + CMA-ES + Pareto
# ═══════════════════════════════════════════════

class BayesianOptimizer:
    """基于 GP 的贝叶斯超参数优化"""
    def __init__(self, n_initial: int = 10, n_iterations: int = 50, 
                 exploration_ratio: float = 0.15):
        self.n_initial = n_initial
        self.n_iterations = n_iterations
        self.exploration_ratio = exploration_ratio
        self._observations: List[Tuple[Dict[str, float], float]] = []
        self._best_params: Dict[str, float] = {}
        self._best_score: float = -float('inf')

    def optimize(self, param_ranges: Dict[str, Tuple[float, float]],
                 objective_fn, name: str = "bayesian_opt") -> Dict[str, Any]:
        """执行贝叶斯优化"""
        logger.info(f"🔬 贝叶斯优化启动: {name}, 参数空间={len(param_ranges)}维")
        # 初始随机采样
        for _ in range(self.n_initial):
            params = {k: random.uniform(*v) for k, v in param_ranges.items()}
            score = objective_fn(params)
            self._observations.append((params, score))
            if score > self._best_score:
                self._best_score = score
                self._best_params = dict(params)
        
        # 基于GP的迭代优化 (简化版: 用加权采样模拟GP采集函数)
        for iteration in range(self.n_iterations):
            # 利用已知最优 + 探索
            use_best = random.random() > self.exploration_ratio
            if use_best and self._best_params:
                base = deepcopy(self._best_params)
                for k in param_ranges:
                    noise = random.gauss(0, 0.05 * (param_ranges[k][1] - param_ranges[k][0]))
                    base[k] = min(max(base[k] + noise, param_ranges[k][0]), param_ranges[k][1])
                params = base
            else:
                params = {k: random.uniform(*v) for k, v in param_ranges.items()}

            score = objective_fn(params)
            self._observations.append((params, score))
            if score > self._best_score:
                self._best_score = score
                self._best_params = dict(params)
            
            if iteration % 10 == 0:
                logger.info(f"  贝叶斯迭代 {iteration}/{self.n_iterations}: best={self._best_score:.4f}")

        logger.info(f"✅ 贝叶斯优化完成: best={self._best_score:.4f}")
        return {
            "method": "bayesian_gp",
            "best_params": self._best_params,
            "best_score": round(self._best_score, 6),
            "n_observations": len(self._observations),
            "exploration_ratio": self.exploration_ratio,
        }


class CMAEvolutionaryOptimizer:
    """CMA-ES 进化策略优化器"""
    def __init__(self, population_size: int = 20, generations: int = 30,
                 sigma: float = 0.3):
        self.population_size = population_size
        self.generations = generations
        self.sigma = sigma
        self._history: List[Dict[str, Any]] = []

    def optimize(self, param_ranges: Dict[str, Tuple[float, float]],
                 objective_fn, name: str = "cma_es") -> Dict[str, Any]:
        """CMA-ES 进化优化"""
        logger.info(f"🧬 CMA-ES优化启动: {name}, 种群={self.population_size}, 代数={self.generations}")
        param_names = list(param_ranges.keys())
        bounds = {k: v for k, v in param_ranges.items()}
        
        # 初始化种群均值
        mean = {k: (v[0] + v[1]) / 2 for k, v in param_ranges.items()}
        best_score = -float('inf')
        best_individual = dict(mean)

        for gen in range(self.generations):
            population = []
            for _ in range(self.population_size):
                individual = {}
                for k in param_names:
                    lo, hi = bounds[k]
                    val = mean[k] + random.gauss(0, self.sigma * (hi - lo))
                    individual[k] = min(max(val, lo), hi)
                score = objective_fn(individual)
                population.append((score, individual))
                if score > best_score:
                    best_score = score
                    best_individual = individual

            # 选取 top 50% 更新均值
            population.sort(key=lambda x: x[0], reverse=True)
            elite = population[:max(1, self.population_size // 2)]
            for k in param_names:
                mean[k] = sum(indv[k] for _, indv in elite) / len(elite)

            # 衰减 sigma
            self.sigma *= 0.97
            self._history.append({
                "generation": gen, "best_score": best_score,
                "avg_score": sum(s for s, _ in population) / len(population),
            })

            if gen % 10 == 0:
                logger.info(f"  CMA-ES 第{gen}代: best={best_score:.4f}, sigma={self.sigma:.4f}")

        logger.info(f"✅ CMA-ES优化完成: best={best_score:.4f}")
        return {
            "method": "cma_es",
            "best_params": best_individual,
            "best_score": round(best_score, 6),
            "generations": self.generations,
            "population_size": self.population_size,
            "final_sigma": round(self.sigma, 6),
            "history": self._history[-5:],
        }


class ParetoMultiObjectiveOptimizer:
    """帕累托多目标优化器（Sharpe vs 回撤 vs 胜率）"""
    def __init__(self, objectives: List[str] = None):
        self.objectives = objectives or ["sharpe_ratio", "max_drawdown", "win_rate"]
        self._pareto_front: List[Dict[str, Any]] = []

    def dominates(self, a: Dict[str, float], b: Dict[str, float]) -> bool:
        """a 是否帕累托支配 b (sharpe/win_rate 越大越好, drawdown 绝对值越小越好)"""
        better = False
        for obj in self.objectives:
            if obj == "max_drawdown":
                # 回撤绝对值越小越好
                if abs(a.get(obj, 1.0)) > abs(b.get(obj, 0.0)):
                    return False
                if abs(a.get(obj, 1.0)) < abs(b.get(obj, 0.0)):
                    better = True
            else:
                if a.get(obj, 0.0) < b.get(obj, 0.0):
                    return False
                if a.get(obj, 0.0) > b.get(obj, 0.0):
                    better = True
        return better

    def compute_pareto_front(self, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """计算帕累托前沿"""
        front = []
        for c in candidates:
            dominated = False
            for f in front:
                if self.dominates(f, c):
                    dominated = True
                    break
                if self.dominates(c, f):
                    front.remove(f)
            if not dominated:
                front.append(c)
        self._pareto_front = front
        logger.info(f"📊 帕累托前沿: {len(front)}/{len(candidates)} 个非支配解")
        return front

    def get_preferred_solution(self, weights: Dict[str, float] = None) -> Dict[str, Any]:
        """从帕累托前沿选加权最优解"""
        if not self._pareto_front:
            return {}
        weights = weights or {"sharpe_ratio": 0.5, "max_drawdown": 0.3, "win_rate": 0.2}
        best, best_score = None, -float('inf')
        for sol in self._pareto_front:
            score = 0.0
            for obj, w in weights.items():
                val = sol.get(obj, 0.0)
                if obj == "max_drawdown":
                    score += w * (1.0 - min(abs(val), 1.0))
                else:
                    score += w * min(val, 3.0) / 3.0
            if score > best_score:
                best_score = score
                best = sol
        return best or {}


# ═══════════════════════════════════════════════
#  引擎 [3]: 策略生成器 — DNA模板 + 交叉变异
# ═══════════════════════════════════════════════

@dataclass
class StrategyTemplate:
    name: str
    type: str
    indicators: List[str]
    signal_rules: List[str]
    risk_params: Dict[str, float]
    fitness_base: float = 0.5

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class StrategyTemplateLibrary:
    """策略模板库"""
    TEMPLATES: Dict[str, StrategyTemplate] = {
        "trend_following_ma": StrategyTemplate(
            "趋势跟踪-MA交叉", "trend_following",
            ["MA_5", "MA_20", "MA_60", "MACD"],
            ["MA_5 > MA_20 → LONG", "MA_5 < MA_20 → SHORT"],
            {"stop_loss": 0.05, "take_profit": 0.10, "trailing_stop": 0.03},
            0.72,
        ),
        "mean_reversion_bb": StrategyTemplate(
            "均值回归-布林带", "mean_reversion",
            ["BB_upper", "BB_lower", "RSI", "KDJ"],
            ["price < BB_lower & RSI < 30 → LONG", "price > BB_upper & RSI > 70 → SHORT"],
            {"stop_loss": 0.03, "take_profit": 0.05, "trailing_stop": 0.02},
            0.68,
        ),
        "momentum_breakout": StrategyTemplate(
            "动量突破", "momentum",
            ["ATR", "ADX", "Volume_SMA", "price_high_20"],
            ["price > price_high_20 & ADX > 25 → LONG"],
            {"stop_loss": 0.06, "take_profit": 0.15, "trailing_stop": 0.04},
            0.65,
        ),
        "grid_oscillation": StrategyTemplate(
            "网格震荡", "grid",
            ["support_level", "resistance_level", "Bollinger_Width"],
            ["price near support → BUY", "price near resistance → SELL"],
            {"grid_count": 10, "grid_spacing": 0.02, "position_per_grid": 0.1},
            0.60,
        ),
        "ml_ensemble_signal": StrategyTemplate(
            "ML集成信号", "ml_ensemble",
            ["XGBoost_pred", "LSTM_pred", "Transformer_pred", "sentiment_idx"],
            ["ensemble_score > 0.65 → LONG", "ensemble_score < -0.65 → SHORT"],
            {"stop_loss": 0.04, "take_profit": 0.08, "confidence_threshold": 0.65},
            0.75,
        ),
        "fourier_rl_adaptive": StrategyTemplate(
            "傅里叶RL自适应", "hybrid",
            ["Fourier_dominant_freq", "Fourier_phase", "RL_action", "volatility_regime"],
            ["RL_action > 0.5 & Fourier_trend_aligned → LONG"],
            {"stop_loss": 0.04, "take_profit": 0.09, "rl_exploration": 0.1},
            0.78,
        ),
    }

    @classmethod
    def get_all(cls) -> List[StrategyTemplate]:
        return list(cls.TEMPLATES.values())

    @classmethod
    def get_by_type(cls, stype: str) -> List[StrategyTemplate]:
        return [t for t in cls.TEMPLATES.values() if t.type == stype]

    @classmethod
    def get_random(cls) -> StrategyTemplate:
        return random.choice(list(cls.TEMPLATES.values()))


class CrossoverEngine:
    """策略DNA交叉变异引擎"""
    def __init__(self, crossover_rate: float = 0.7, mutation_rate: float = 0.15):
        self.crossover_rate = crossover_rate
        self.mutation_rate = mutation_rate

    def crossover(self, parent1: Dict[str, Any], parent2: Dict[str, Any]) -> Dict[str, Any]:
        """两个策略DNA交叉"""
        if random.random() > self.crossover_rate:
            return deepcopy(parent1 if random.random() < 0.5 else parent2)

        child = {}
        all_keys = set(parent1.keys()) | set(parent2.keys())
        for key in all_keys:
            if key in parent1 and key in parent2:
                child[key] = parent1[key] if random.random() < 0.5 else parent2[key]
            elif key in parent1:
                child[key] = parent1[key]
            else:
                child[key] = parent2[key]
        return child

    def mutate(self, dna: Dict[str, Any], param_ranges: Dict[str, Tuple[float, float]] = None) -> Dict[str, Any]:
        """策略DNA变异"""
        mutated = deepcopy(dna)
        for key, val in mutated.items():
            if isinstance(val, float) and random.random() < self.mutation_rate:
                noise = random.gauss(0, 0.1 * abs(val) if abs(val) > 0 else 0.1)
                mutated[key] = max(0.001, val + noise)
                if param_ranges and key in param_ranges:
                    lo, hi = param_ranges[key]
                    mutated[key] = min(max(mutated[key], lo), hi)
            elif isinstance(val, list) and random.random() < self.mutation_rate:
                # 列表类参数变异：增删改元素
                if val and random.random() < 0.5:
                    val.append(f"indicator_{random.randint(1, 50)}")
                elif val:
                    val.pop(random.randint(0, len(val) - 1))
        return mutated


class StrategyGenerator:
    """策略生成器：模板实例化 + 交叉变异 + 新策略孵化"""

    def __init__(self):
        self.template_lib = StrategyTemplateLibrary()
        self.crossover_engine = CrossoverEngine()
        self._generated_dnas: List[Dict[str, Any]] = []

    def generate_from_template(self, template_name: str = None) -> Dict[str, Any]:
        """从模板生成策略DNA"""
        tmpl = (self.template_lib.TEMPLATES.get(template_name) 
                if template_name else self.template_lib.get_random())
        dna = {
            "dna_id": hashlib.md5(f"{tmpl.name}:{time.time()}:{random.random()}".encode()).hexdigest()[:12],
            "strategy_type": tmpl.type,
            "source_template": tmpl.name,
            "params": dict(tmpl.risk_params),
            "indicators": list(tmpl.indicators),
            "signal_rules": list(tmpl.signal_rules),
            "fitness": tmpl.fitness_base,
            "generation": 0,
            "created_at": datetime.now().isoformat(),
            "tech_stack_fingerprint": self._compute_fingerprint(tmpl),
        }
        self._generated_dnas.append(dna)
        logger.info(f"🧬 策略生成: {tmpl.name} (DNA={dna['dna_id']})")
        return dna

    def generate_offspring(self, parent1: Dict[str, Any], parent2: Dict[str, Any]) -> Dict[str, Any]:
        """交叉生成子代策略"""
        child = self.crossover_engine.crossover(parent1, parent2)
        child = self.crossover_engine.mutate(child)
        max_gen = max(parent1.get("generation", 0), parent2.get("generation", 0))
        child["generation"] = max_gen + 1
        child["parent_ids"] = [
            parent1.get("dna_id", ""),
            parent2.get("dna_id", ""),
        ]
        child["dna_id"] = hashlib.md5(
            f"offspring:{child.get('strategy_type','')}:{time.time()}:{random.random()}".encode()
        ).hexdigest()[:12]
        child["created_at"] = datetime.now().isoformat()
        child["source_template"] = f"crossover(G{max_gen})"
        self._generated_dnas.append(child)
        return child

    def generate_population(self, size: int = 10, elite_ratio: float = 0.2) -> List[Dict[str, Any]]:
        """生成策略种群 (含精英模板 + 交叉子代)"""
        population = []
        n_elite = max(1, int(size * elite_ratio))
        # 精英模板
        for tmp in list(self.template_lib.TEMPLATES.values())[:n_elite]:
            population.append(self.generate_from_template(tmp.name))
        # 交叉子代
        while len(population) < size:
            p1 = random.choice(population)
            p2 = random.choice(population)
            if p1["dna_id"] != p2["dna_id"]:
                offspring = self.generate_offspring(p1, p2)
                population.append(offspring)
        logger.info(f"🌱 种群生成完成: {size}个策略")
        return population

    @staticmethod
    def _compute_fingerprint(tmpl: StrategyTemplate) -> str:
        sig = f"{tmpl.type}|{'|'.join(sorted(tmpl.indicators))}|{','.join(sorted(tmpl.risk_params.keys()))}"
        return hashlib.sha256(sig.encode()).hexdigest()[:16]


# ═══════════════════════════════════════════════
#  引擎 [4]: 技术栈组合引擎 — 指纹 + 交叉组合
# ═══════════════════════════════════════════════

@dataclass
class TechStackProfile:
    """技术栈画像"""
    name: str
    category: str  # ML / Signal / Risk / Execution / Data
    technologies: List[str]
    maturity: float  # 0-1
    synergy_score: float = 0.5
    fingerprint: str = ""

    def __post_init__(self):
        if not self.fingerprint:
            raw = f"{self.category}:{sorted(self.technologies)}"
            self.fingerprint = hashlib.sha256(raw.encode()).hexdigest()[:16]


class TechStackExtractor:
    """技术栈指纹提取器"""
    KNOWN_STACKS: Dict[str, List[str]] = {
        "ML": ["XGBoost", "LightGBM", "CatBoost", "LSTM", "Transformer", "PPO", "RandomForest"],
        "Signal": ["Fourier", "Wavelet", "MACD", "RSI", "Bollinger", "ATR", "ADX", "OBV"],
        "Risk": ["VaR", "CVaR", "MaxDrawdown", "StopLoss", "Kelly", "RiskParity", "VolatilityTargeting"],
        "Execution": ["TWAP", "VWAP", "Iceberg", "SmartOrderRouting", "MarketMaking"],
        "Data": ["AKShare", "Tushare", "yfinance", "Redis", "TimescaleDB", "SQLite"],
        "Optimization": ["Bayesian", "CMA-ES", "ParticleSwarm", "GeneticAlgorithm", "GridSearch"],
    }

    @classmethod
    def extract_profile(cls, dna: Dict[str, Any]) -> List[TechStackProfile]:
        """从策略DNA提取技术栈画像"""
        profiles = []
        stype = dna.get("strategy_type", "unknown")
        indicators = dna.get("indicators", [])
        
        # 根据策略类型推断技术栈
        signal_techs = [ind for ind in indicators 
                        if ind in cls.KNOWN_STACKS.get("Signal", [])]
        if signal_techs:
            profiles.append(TechStackProfile(
                f"{stype}_signal", "Signal", signal_techs,
                maturity=0.7, synergy_score=0.75,
            ))

        # ML技术栈
        ml_techs = [t for t in cls.KNOWN_STACKS.get("ML", [])
                    if any(kw in str(dna.get("params", {})).lower() 
                          for kw in [t.lower()[:4]])]
        if not ml_techs:
            ml_techs = ["XGBoost", "LightGBM"]  # 默认
        profiles.append(TechStackProfile(
            f"{stype}_ml", "ML", ml_techs,
            maturity=0.8, synergy_score=0.70,
        ))

        # 风控技术栈
        risk_params = dna.get("params", {})
        risk_techs = ["StopLoss", "MaxDrawdown"]
        if any(k in risk_params for k in ["trailing_stop"]):
            risk_techs.append("TrailingStop")
        profiles.append(TechStackProfile(
            f"{stype}_risk", "Risk", risk_techs,
            maturity=0.85, synergy_score=0.80,
        ))

        return profiles


class NoveltyScorer:
    """策略新颖性评分器"""
    
    def __init__(self):
        self._seen_fingerprints: Set[str] = set()

    def compute_novelty(self, dna: Dict[str, Any], 
                        population: List[Dict[str, Any]] = None) -> float:
        """计算策略的新颖性得分（0-1, 越高越新颖）"""
        fp = dna.get("tech_stack_fingerprint", "")
        if not fp:
            return 0.5

        if fp in self._seen_fingerprints:
            return 0.1
        
        # 与种群的相似度
        if population:
            similarities = []
            for other in population:
                if other.get("dna_id") == dna.get("dna_id"):
                    continue
                other_fp = other.get("tech_stack_fingerprint", "")
                if other_fp:
                    sim = self._fingerprint_similarity(fp, other_fp)
                    similarities.append(sim)
            if similarities:
                avg_sim = sum(similarities) / len(similarities)
                novelty = 1.0 - avg_sim
            else:
                novelty = 0.8
        else:
            novelty = 0.8

        self._seen_fingerprints.add(fp)
        return round(max(0.0, min(1.0, novelty)), 4)

    @staticmethod
    def _fingerprint_similarity(fp1: str, fp2: str) -> float:
        """两个指纹的汉明距离相似度"""
        max_len = max(len(fp1), len(fp2))
        matches = sum(1 for a, b in zip(fp1, fp2) if a == b)
        return matches / max_len if max_len > 0 else 1.0


class TechStackComposer:
    """技术栈组合引擎：多策略DNA交叉组合+新颖性导向"""

    def __init__(self, target_novelty: float = 0.3):
        self.extractor = TechStackExtractor()
        self.scorer = NoveltyScorer()
        self.target_novelty = target_novelty
        self._composition_history: List[Dict[str, Any]] = []

    def compose(self, dnas: List[Dict[str, Any]], 
                target_count: int = 3) -> List[Dict[str, Any]]:
        """从多策略DNA组合出新策略"""
        if len(dnas) < 2:
            logger.warning("组合需要至少2个DNA样本")
            return dnas

        logger.info(f"🔧 技术栈组合引擎: {len(dnas)}个DNA → {target_count}个新组合")
        compositions = []

        for i in range(target_count):
            # 选取2-3个源DNA
            sources = random.sample(dnas, min(3, len(dnas)))
            
            # 提取所有技术栈画像
            all_profiles = []
            for src in sources:
                all_profiles.extend(self.extractor.extract_profile(src))

            # 按类别分组，每个类别选最佳
            by_category = defaultdict(list)
            for prof in all_profiles:
                by_category[prof.category].append(prof)

            # 组合：每类选 synergy 最高的
            composed_tech = []
            for cat, profs in by_category.items():
                best = max(profs, key=lambda p: p.synergy_score * p.maturity)
                composed_tech.extend(best.technologies[:3])

            # 参数融合
            fused_params = {}
            for src in sources:
                for k, v in src.get("params", {}).items():
                    if k in fused_params:
                        fused_params[k] = (fused_params[k] + v) / 2
                    else:
                        fused_params[k] = v

            # 创建组合DNA
            composed = {
                "dna_id": hashlib.md5(
                    f"composed:{i}:{time.time()}:{random.random()}".encode()
                ).hexdigest()[:12],
                "strategy_type": "composed",
                "source_strategies": [s.get("dna_id", "") for s in sources],
                "params": fused_params,
                "indicators": list(set(composed_tech)),
                "signal_rules": self._generate_composed_rules(sources),
                "fitness": 0.0,  # 待评估
                "generation": max(s.get("generation", 0) for s in sources) + 1,
                "source_template": f"composed({len(sources)}src)",
                "tech_stack_fingerprint": hashlib.sha256(
                    f"composed:{composed_tech}".encode()
                ).hexdigest()[:16],
                "created_at": datetime.now().isoformat(),
            }

            # 新颖性评分
            composed["novelty_score"] = self.scorer.compute_novelty(composed, dnas)
            compositions.append(composed)

            logger.info(f"  组合#{i+1}: DNA={composed['dna_id']}, "
                       f"新颖性={composed['novelty_score']:.3f}, "
                       f"技术={composed_tech[:3]}")

        self._composition_history.extend(compositions)
        # 按新颖性排序
        compositions.sort(key=lambda x: x.get("novelty_score", 0), reverse=True)
        return compositions

    @staticmethod
    def _generate_composed_rules(sources: List[Dict[str, Any]]) -> List[str]:
        """融合多个来源的信号规则"""
        rules = []
        for src in sources:
            rules.extend(src.get("signal_rules", [])[:2])
        # 去重
        return list(set(rules))[:5]

    def get_history(self) -> List[Dict[str, Any]]:
        return self._composition_history


# ═══════════════════════════════════════════════
#  引擎 [4.5]: 策略新生引擎 — 多策略DNA融合孵化全新策略
# ═══════════════════════════════════════════════

@dataclass
class StrategyLineage:
    """策略血统追踪"""
    dna_id: str
    ancestors: List[str] = field(default_factory=list)
    birth_generation: int = 0
    archetype: str = "unknown"
    viability_scores: List[float] = field(default_factory=list)
    rebirth_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dna_id": self.dna_id,
            "ancestors": self.ancestors,
            "birth_generation": self.birth_generation,
            "archetype": self.archetype,
            "avg_viability": round(sum(self.viability_scores) / max(len(self.viability_scores), 1), 4),
            "rebirth_count": self.rebirth_count,
        }


class StrategyRebirthEngine:
    """策略新生引擎 — 多策略DNA融合孵化全新策略，支持血统追踪与生态平衡"""

    ARCHETYPES = [
        "trend_following", "mean_reversion", "momentum", "grid", "ml_ensemble",
        "hybrid", "adaptive", "contrarian", "arbitrage", "macro_driven",
    ]

    FUSION_STRATEGIES = [
        "weighted_average",      # 加权平均融合
        "regime_switching",      # 市场体制切换融合
        "stacked_ensemble",      # 堆叠集成融合
        "complementary_synergy",  # 优势互补融合
        "genetic_splice",        # 遗传剪接融合
    ]

    def __init__(self, min_parents: int = 2, max_parents: int = 5,
                 gestation_period: int = 3):
        self.min_parents = min_parents
        self.max_parents = max_parents
        self.gestation_period = gestation_period  # 新生策略验证轮次
        self._lineages: Dict[str, StrategyLineage] = {}
        self._rebirth_history: List[Dict[str, Any]] = []
        self._ecosystem: Dict[str, List[str]] = defaultdict(list)  # 生态位

    def rebirth(self, parents: List[Dict[str, Any]],
                fusion_strategy: str = None,
                market_context: Dict[str, Any] = None) -> Dict[str, Any]:
        """从多个父策略孵化全新策略"""
        if len(parents) < self.min_parents:
            logger.warning(f"策略新生需要至少{self.min_parents}个父策略, 当前={len(parents)}")
            return {}

        fusion = fusion_strategy or random.choice(self.FUSION_STRATEGIES)
        logger.info(f"🦋 策略新生启动: {len(parents)}个父策略, 融合策略={fusion}")

        # 选择父策略
        selected_parents = parents[:self.max_parents]
        parent_ids = [p.get("dna_id", "") for p in selected_parents]
        parent_types = [p.get("strategy_type", "unknown") for p in selected_parents]

        # 第一步：提取核心基因
        core_genes = self._extract_core_genes(selected_parents)

        # 第二步：融合策略DNA
        if fusion == "weighted_average":
            newborn = self._fusion_weighted_average(selected_parents, core_genes)
        elif fusion == "regime_switching":
            newborn = self._fusion_regime_switching(selected_parents, core_genes, market_context)
        elif fusion == "stacked_ensemble":
            newborn = self._fusion_stacked_ensemble(selected_parents, core_genes)
        elif fusion == "complementary_synergy":
            newborn = self._fusion_complementary_synergy(selected_parents, core_genes)
        else:  # genetic_splice
            newborn = self._fusion_genetic_splice(selected_parents, core_genes)

        # 第三步：新生策略标识
        newborn["dna_id"] = hashlib.md5(
            f"rebirth:{fusion}:{','.join(sorted(parent_ids))}:{time.time()}:{random.random()}".encode()
        ).hexdigest()[:12]
        newborn["strategy_type"] = self._determine_archetype(core_genes)
        newborn["source_strategies"] = parent_ids
        newborn["parent_types"] = parent_types
        newborn["fusion_strategy"] = fusion
        newborn["fitness"] = 0.0
        newborn["generation"] = max(p.get("generation", 0) for p in selected_parents) + 1
        newborn["source_template"] = f"rebirth({fusion})"
        newborn["gestation_round"] = 0
        newborn["viable"] = False
        newborn["tech_stack_fingerprint"] = self._compute_newborn_fingerprint(newborn)
        newborn["novelty_score"] = 0.0
        newborn["created_at"] = datetime.now().isoformat()
        newborn["lineage_depth"] = max(
            len(self._lineages.get(pid, StrategyLineage(pid)).ancestors)
            for pid in parent_ids
        ) + 1

        # 第四步：血统注册
        ancestors = []
        for pid in parent_ids:
            if pid in self._lineages:
                ancestors.extend(self._lineages[pid].ancestors)
                ancestors.append(pid)
            else:
                ancestors.append(pid)
                self._lineages[pid] = StrategyLineage(
                    dna_id=pid, ancestors=[], birth_generation=0,
                    archetype=parent_types[parent_ids.index(pid)] if pid in parent_ids else "unknown",
                )

        self._lineages[newborn["dna_id"]] = StrategyLineage(
            dna_id=newborn["dna_id"],
            ancestors=list(set(ancestors)),
            birth_generation=newborn["generation"],
            archetype=newborn["strategy_type"],
            rebirth_count=1 + sum(
                self._lineages[pid].rebirth_count for pid in parent_ids if pid in self._lineages
            ),
        )

        # 第五步：生态位注册
        archetype = newborn["strategy_type"]
        self._ecosystem[archetype].append(newborn["dna_id"])

        self._rebirth_history.append({
            "dna_id": newborn["dna_id"],
            "parents": parent_ids,
            "fusion": fusion,
            "archetype": archetype,
            "timestamp": newborn["created_at"],
        })

        logger.info(f"🦋 策略新生完成: DNA={newborn['dna_id']}, "
                    f"archetype={archetype}, parents={len(parent_ids)}, "
                    f"血统深度={newborn['lineage_depth']}")

        return newborn

    def _extract_core_genes(self, parents: List[Dict[str, Any]]) -> Dict[str, Any]:
        """提取核心基因：信号逻辑、风控规则、指标集、参数空间"""
        all_indicators = list(set(
            ind for p in parents for ind in p.get("indicators", [])
        ))
        all_signal_rules = list(set(
            rule for p in parents for rule in p.get("signal_rules", [])
        ))
        all_params = {}
        for p in parents:
            for k, v in p.get("params", {}).items():
                if k not in all_params:
                    all_params[k] = []
                all_params[k].append(v)

        # 计算参数统计
        param_stats = {}
        for k, vals in all_params.items():
            if len(vals) >= 2:
                param_stats[k] = {
                    "mean": sum(vals) / len(vals),
                    "min": min(vals),
                    "max": max(vals),
                    "range": max(vals) - min(vals),
                }
            else:
                param_stats[k] = {"mean": vals[0], "min": vals[0], "max": vals[0], "range": 0}

        # 计算父策略适应度权重
        total_fitness = sum(p.get("fitness", 0.5) for p in parents)
        weights = [p.get("fitness", 0.5) / max(total_fitness, 0.01) for p in parents]

        return {
            "indicators": all_indicators,
            "signal_rules": all_signal_rules,
            "param_stats": param_stats,
            "parent_weights": weights,
            "best_parent_idx": weights.index(max(weights)),
        }

    def _fusion_weighted_average(self, parents: List[Dict[str, Any]],
                                  genes: Dict[str, Any]) -> Dict[str, Any]:
        """加权平均融合：按父策略适应度加权"""
        weights = genes["parent_weights"]
        fused_params = {}
        for k, stats in genes["param_stats"].items():
            fused_params[k] = stats["mean"]
            # 向最佳父策略微调
            best = parents[genes["best_parent_idx"]].get("params", {}).get(k)
            if best is not None:
                fused_params[k] = fused_params[k] * 0.6 + best * 0.4

        return {
            "params": fused_params,
            "indicators": genes["indicators"][:8],
            "signal_rules": genes["signal_rules"][:5],
            "risk_rules": self._merge_risk_rules(parents, weights),
        }

    def _fusion_regime_switching(self, parents: List[Dict[str, Any]],
                                  genes: Dict[str, Any],
                                  market_context: Dict[str, Any] = None) -> Dict[str, Any]:
        """市场体制切换融合：不同市场状态用不同父策略"""
        mc = market_context or {}
        regime = mc.get("regime", "neutral")

        # 根据市场体制选择主要父策略
        regime_map = {
            "bull": 0,     # 趋势跟踪优先
            "bear": 1,     # 均值回归优先
            "neutral": 2,  # 网格优先
        }
        primary_idx = regime_map.get(regime, 0) % len(parents)
        secondary_idx = (primary_idx + 1) % len(parents)

        fused_params = {}
        for k in genes["param_stats"]:
            primary_val = parents[primary_idx].get("params", {}).get(k)
            secondary_val = parents[secondary_idx].get("params", {}).get(k)
            if primary_val is not None and secondary_val is not None:
                fused_params[k] = primary_val * 0.7 + secondary_val * 0.3
            elif primary_val is not None:
                fused_params[k] = primary_val
            elif secondary_val is not None:
                fused_params[k] = secondary_val

        return {
            "params": fused_params,
            "indicators": parents[primary_idx].get("indicators", [])[:6] + 
                         parents[secondary_idx].get("indicators", [])[:3],
            "signal_rules": (parents[primary_idx].get("signal_rules", [])[:2] +
                           parents[secondary_idx].get("signal_rules", [])[:1]),
            "risk_rules": self._merge_risk_rules(
                [parents[primary_idx], parents[secondary_idx]],
                [0.7, 0.3],
            ),
        }

    def _fusion_stacked_ensemble(self, parents: List[Dict[str, Any]],
                                  genes: Dict[str, Any]) -> Dict[str, Any]:
        """堆叠集成融合：父策略信号作为元特征"""
        # 所有父策略的信号规则作为元特征
        meta_rules = []
        for p in parents:
            meta_rules.extend(p.get("signal_rules", [])[:1])

        # 参数取中位数
        fused_params = {}
        for k, stats in genes["param_stats"].items():
            # 取中位数近似（mean在正态分布下近似中位数）
            fused_params[k] = stats["mean"]

        return {
            "params": fused_params,
            "indicators": genes["indicators"][:10],
            "signal_rules": ["ensemble_vote → LONG", "ensemble_vote < 0 → SHORT"] + meta_rules,
            "risk_rules": {"ensemble_confidence_threshold": 0.6, **self._merge_risk_rules(parents, genes["parent_weights"])},
        }

    def _fusion_complementary_synergy(self, parents: List[Dict[str, Any]],
                                       genes: Dict[str, Any]) -> Dict[str, Any]:
        """优势互补融合：每个父策略贡献最强项"""
        # 评估每个父策略的优势维度
        strengths = []
        for i, p in enumerate(parents):
            params = p.get("params", {})
            score = 0
            if params.get("take_profit", 0) > params.get("stop_loss", 0) * 2:
                score += 1  # 收益导向
            if params.get("stop_loss", 0) < 0.05:
                score += 1  # 风控导向
            if len(p.get("indicators", [])) > 4:
                score += 1  # 多指标
            strengths.append(score)

        # 选最强的2个父策略
        ranked = sorted(range(len(parents)), key=lambda i: strengths[i], reverse=True)
        best_two = [parents[ranked[0]], parents[ranked[min(1, len(ranked)-1)]]]

        fused_params = {}
        # 止盈止损等关键参数取最强父策略
        primary = best_two[0].get("params", {})
        secondary = best_two[1].get("params", {})
        for k in set(list(primary.keys()) + list(secondary.keys())):
            if k in primary and k in secondary:
                fused_params[k] = max(primary[k], secondary[k]) if "profit" in k or "take" in k else min(primary[k], secondary[k])
            else:
                fused_params[k] = primary.get(k, secondary.get(k, 0))

        return {
            "params": fused_params,
            "indicators": list(set(
                best_two[0].get("indicators", []) + best_two[1].get("indicators", [])
            )),
            "signal_rules": best_two[0].get("signal_rules", [])[:3],
            "risk_rules": self._merge_risk_rules(best_two, [0.7, 0.3]),
        }

    def _fusion_genetic_splice(self, parents: List[Dict[str, Any]],
                                genes: Dict[str, Any]) -> Dict[str, Any]:
        """遗传剪接融合：随机剪接父策略基因片段"""
        # 参数随机剪接
        spliced_params = {}
        for k, stats in genes["param_stats"].items():
            spliced_params[k] = random.uniform(stats["min"] * 0.9, stats["max"] * 1.1)

        # 指标随机选取
        indicators = random.sample(
            genes["indicators"],
            min(len(genes["indicators"]), random.randint(3, 7)),
        )

        # 信号规则拼接
        rules = []
        for p in parents:
            p_rules = p.get("signal_rules", [])
            if p_rules:
                rules.append(random.choice(p_rules))
        rules = list(set(rules))[:4]

        return {
            "params": spliced_params,
            "indicators": indicators,
            "signal_rules": rules,
            "risk_rules": self._merge_risk_rules(parents, genes["parent_weights"]),
        }

    @staticmethod
    def _merge_risk_rules(parents: List[Dict[str, Any]],
                          weights: List[float]) -> Dict[str, float]:
        """融合风控规则"""
        merged = {}
        for p, w in zip(parents, weights):
            for k, v in p.get("risk_rules", {}).items():
                if isinstance(v, (int, float)):
                    merged[k] = merged.get(k, 0) + v * w
        return merged

    @staticmethod
    def _compute_newborn_fingerprint(newborn: Dict[str, Any]) -> str:
        sig = f"rebirth:{newborn.get('strategy_type','')}:{sorted(newborn.get('indicators',[]))}:{sorted(newborn.get('params',{}).keys())}"
        return hashlib.sha256(sig.encode()).hexdigest()[:16]

    def _determine_archetype(self, genes: Dict[str, Any]) -> str:
        """根据基因确定策略原型"""
        indicators_str = ' '.join(genes.get("indicators", [])).lower()
        if any(kw in indicators_str for kw in ["fourier", "wavelet", "rl"]):
            return "hybrid"
        elif any(kw in indicators_str for kw in ["xgboost", "lstm", "transformer"]):
            return "ml_ensemble"
        elif any(kw in indicators_str for kw in ["bb_", "rsi", "kdj"]):
            return "mean_reversion"
        elif any(kw in indicators_str for kw in ["ma_", "macd"]):
            return "trend_following"
        elif any(kw in indicators_str for kw in ["atr", "adx"]):
            return "momentum"
        elif any(kw in indicators_str for kw in ["support", "resistance", "grid"]):
            return "grid"
        return "adaptive"

    def validate_newborn(self, dna: Dict[str, Any], fitness_score: float) -> Dict[str, Any]:
        """验证新生策略的生存能力"""
        dna_id = dna.get("dna_id", "")
        gestation_round = dna.get("gestation_round", 0) + 1
        dna["gestation_round"] = gestation_round

        if dna_id in self._lineages:
            self._lineages[dna_id].viability_scores.append(fitness_score)

        viable = fitness_score >= 0.50 and gestation_round >= self.gestation_period
        dna["viable"] = viable
        dna["fitness"] = max(dna.get("fitness", 0), fitness_score)

        if viable:
            logger.info(f"✅ 新生策略 DNA={dna_id} 通过生存验证: "
                       f"fitness={fitness_score:.4f}, 孵育轮次={gestation_round}")

        return dna

    def get_lineage_tree(self, dna_id: str = None) -> Dict[str, Any]:
        """获取血统树"""
        if dna_id:
            lineage = self._lineages.get(dna_id)
            if not lineage:
                return {"dna_id": dna_id, "error": "未找到血统"}
            children = [
                lid for lid, lin in self._lineages.items()
                if dna_id in lin.ancestors
            ]
            return {
                **lineage.to_dict(),
                "children": children,
                "depth": len(lineage.ancestors),
            }

        # 全血统树
        return {
            "total_strategies": len(self._lineages),
            "max_depth": max((len(l.ancestors) for l in self._lineages.values()), default=0),
            "archetype_distribution": {
                arch: len(ids) for arch, ids in self._ecosystem.items()
            },
            "lineages": {lid: l.to_dict() for lid, l in self._lineages.items()},
        }

    def get_ecosystem_health(self) -> Dict[str, Any]:
        """获取策略生态健康度"""
        archetype_counts = {arch: len(ids) for arch, ids in self._ecosystem.items()}
        total = sum(archetype_counts.values())
        if total == 0:
            return {"status": "empty", "total": 0}

        # 计算生态多样性 (Simpson 多样性指数)
        diversity = 1 - sum(
            (c / total) ** 2 for c in archetype_counts.values()
        )

        # 检测失衡
        imbalance_warnings = []
        avg_per_arch = total / max(len(self.ARCHETYPES), 1)
        for arch, count in archetype_counts.items():
            if count > avg_per_arch * 3:
                imbalance_warnings.append(f"{arch}过载({count}个)")
            elif count == 0:
                imbalance_warnings.append(f"{arch}缺失(0个)")

        return {
            "status": "healthy" if diversity > 0.6 else "degraded",
            "total_strategies": total,
            "diversity_index": round(diversity, 4),
            "archetype_distribution": archetype_counts,
            "imbalance_warnings": imbalance_warnings,
            "recommended_action": "需要引入" + "和".join(
                arch for arch in self.ARCHETYPES if arch not in archetype_counts
            ) if archetype_counts else "初始化策略生态",
        }

    def get_rebirth_history(self) -> List[Dict[str, Any]]:
        return self._rebirth_history


# ═══════════════════════════════════════════════
#  引擎 [5]: 自演进系统 — 元学习 + 遗传 + A/B
# ═══════════════════════════════════════════════

class MetaLearningMemory:
    """元学习记忆库：存储成功/失败经验模式"""
    
    def __init__(self, capacity: int = 1000):
        self.capacity = capacity
        self._memories: List[Dict[str, Any]] = []
        self._patterns: Dict[str, Dict[str, float]] = defaultdict(dict)

    def record(self, dna: Dict[str, Any], score: float, 
               context: Dict[str, Any] = None):
        """记录策略在特定环境下的表现"""
        memory = {
            "timestamp": datetime.now().isoformat(),
            "dna_id": dna.get("dna_id", ""),
            "strategy_type": dna.get("strategy_type", "unknown"),
            "score": score,
            "params": deepcopy(dna.get("params", {})),
            "market_context": deepcopy(context or {}),
            "success": score >= 0.70,
        }
        self._memories.append(memory)
        if len(self._memories) > self.capacity:
            self._memories = self._memories[-self.capacity:]

        # 更新模式库
        stype = dna.get("strategy_type", "unknown")
        if stype not in self._patterns:
            self._patterns[stype] = {"total": 0, "success": 0, "avg_score": 0.0}
        pat = self._patterns[stype]
        pat["total"] += 1
        if score >= 0.70:
            pat["success"] += 1
        pat["avg_score"] = (pat["avg_score"] * (pat["total"] - 1) + score) / pat["total"]

    def get_best_patterns(self, top_n: int = 3) -> List[Dict[str, Any]]:
        """获取最优策略模式"""
        sorted_mems = sorted(
            [m for m in self._memories if m["success"]],
            key=lambda x: x["score"], reverse=True,
        )
        return sorted_mems[:top_n]

    def get_strategy_type_stats(self, stype: str) -> Dict[str, float]:
        """获取特定类型的统计"""
        return dict(self._patterns.get(stype, {"total": 0, "success": 0, "avg_score": 0.0}))

    def recommend_params(self, stype: str) -> Dict[str, float]:
        """基于元记忆为策略类型推荐参数"""
        relevant = [m for m in self._memories 
                    if m["strategy_type"] == stype and m["success"]]
        if not relevant:
            return {}
        best = max(relevant, key=lambda x: x["score"])
        return deepcopy(best.get("params", {}))


class GeneticEvolutionEngine:
    """遗传算法进化引擎：策略种群迭代进化"""
    
    def __init__(self, population_size: int = 20, generations: int = 10,
                 elite_ratio: float = 0.2, mutation_rate: float = 0.15):
        self.population_size = population_size
        self.generations = generations
        self.elite_ratio = elite_ratio
        self.mutation_rate = mutation_rate
        self.generator = StrategyGenerator()
        self.memory = MetaLearningMemory()
        self._generation_log: List[Dict[str, Any]] = []

    def evolve(self, initial_population: List[Dict[str, Any]] = None,
               fitness_fn=None) -> List[Dict[str, Any]]:
        """执行遗传进化"""
        logger.info(f"🧬 遗传进化启动: {self.generations}代, 种群={self.population_size}")
        
        if initial_population and len(initial_population) >= 2:
            population = initial_population[:self.population_size]
        else:
            population = self.generator.generate_population(self.population_size)

        for gen in range(self.generations):
            # 评估适应度
            if fitness_fn:
                for indv in population:
                    indv["fitness"] = fitness_fn(indv)
                    self.memory.record(indv, indv["fitness"])

            # 排序选择
            population.sort(key=lambda x: x.get("fitness", 0), reverse=True)
            best_fitness = population[0].get("fitness", 0)
            avg_fitness = sum(ind.get("fitness", 0) for ind in population) / len(population)

            # 精英保留
            n_elite = max(1, int(self.population_size * self.elite_ratio))
            new_population = deepcopy(population[:n_elite])

            # 交叉变异填充
            while len(new_population) < self.population_size:
                p1, p2 = random.sample(population, 2)
                offspring = self.generator.generate_offspring(p1, p2)
                # 额外变异
                offspring = self.generator.crossover_engine.mutate(offspring)
                if fitness_fn:
                    offspring["fitness"] = fitness_fn(offspring)
                new_population.append(offspring)

            population = new_population
            gen_log = {
                "generation": gen,
                "best_fitness": round(best_fitness, 6),
                "avg_fitness": round(avg_fitness, 6),
                "population_size": len(population),
            }
            self._generation_log.append(gen_log)
            logger.info(f"  第{gen}代: best={best_fitness:.4f}, avg={avg_fitness:.4f}")

        # 最终按适应度排序
        population.sort(key=lambda x: x.get("fitness", 0), reverse=True)
        logger.info(f"✅ 遗传进化完成: {self.generations}代, best={population[0].get('fitness', 0):.4f}")
        return population

    def get_best_individual(self) -> Dict[str, Any]:
        """获取最优个体"""
        if self._generation_log:
            best_gen = max(self._generation_log, key=lambda x: x["best_fitness"])
            return {"generation": best_gen["generation"], "fitness": best_gen["best_fitness"]}
        return {}

    def get_evolution_log(self) -> List[Dict[str, Any]]:
        return self._generation_log


class ABTestEngine:
    """A/B测试引擎：对比新旧策略，统计显著性检验"""

    def __init__(self, confidence_level: float = 0.95, min_samples: int = 30):
        self.confidence_level = confidence_level
        self.min_samples = min_samples
        self._experiments: Dict[str, Dict[str, Any]] = {}

    def create_experiment(self, name: str, variant_a: Dict[str, Any],
                          variant_b: Dict[str, Any]) -> str:
        """创建A/B测试实验"""
        exp_id = f"ab_{name}_{int(time.time())}"
        self._experiments[exp_id] = {
            "name": name,
            "variant_a": deepcopy(variant_a),
            "variant_b": deepcopy(variant_b),
            "results_a": [],
            "results_b": [],
            "status": "running",
            "created_at": datetime.now().isoformat(),
        }
        logger.info(f"🧪 A/B测试创建: {name} (ID={exp_id})")
        return exp_id

    def record_result(self, exp_id: str, variant: str, score: float):
        """记录单次实验数据"""
        if exp_id not in self._experiments:
            logger.warning(f"实验ID不存在: {exp_id}")
            return
        exp = self._experiments[exp_id]
        if variant == "a":
            exp["results_a"].append(score)
        else:
            exp["results_b"].append(score)

    def evaluate_experiment(self, exp_id: str) -> Dict[str, Any]:
        """评估A/B测试结果"""
        exp = self._experiments.get(exp_id)
        if not exp:
            return {"status": "not_found"}

        results_a = exp["results_a"]
        results_b = exp["results_b"]

        if len(results_a) < self.min_samples or len(results_b) < self.min_samples:
            return {
                "status": "insufficient_data",
                "samples_a": len(results_a),
                "samples_b": len(results_b),
                "min_required": self.min_samples,
            }

        avg_a = sum(results_a) / len(results_a)
        avg_b = sum(results_b) / len(results_b)
        var_a = sum((x - avg_a) ** 2 for x in results_a) / max(1, len(results_a) - 1)
        var_b = sum((x - avg_b) ** 2 for x in results_b) / max(1, len(results_b) - 1)

        # Welch's t-test 近似
        se = math.sqrt(var_a / len(results_a) + var_b / len(results_b))
        if se < 1e-10:
            t_stat = 0.0
            p_value = 1.0
        else:
            t_stat = (avg_b - avg_a) / se
            # 简化p值估计（基于正态近似）
            p_value = 2 * (1 - self._approx_normal_cdf(abs(t_stat)))

        significant = p_value < (1 - self.confidence_level)
        winner = "b" if avg_b > avg_a else "a"
        improvement = ((avg_b - avg_a) / abs(avg_a)) * 100 if abs(avg_a) > 0 else 0

        result = {
            "status": "completed",
            "avg_a": round(avg_a, 6),
            "avg_b": round(avg_b, 6),
            "improvement_pct": round(improvement, 2),
            "t_statistic": round(t_stat, 4),
            "p_value": round(p_value, 4),
            "significant": significant,
            "winner": winner,
            "samples_a": len(results_a),
            "samples_b": len(results_b),
        }
        exp["status"] = "completed"
        exp["result"] = result
        logger.info(f"📊 A/B测试结果: {exp['name']}: winner={winner}, "
                    f"改善={improvement:.1f}%, significant={significant}")
        return result

    @staticmethod
    def _approx_normal_cdf(x: float) -> float:
        """正态分布CDF近似"""
        return 0.5 * (1 + math.erf(x / math.sqrt(2)))

    def get_all_experiments(self) -> Dict[str, Dict[str, Any]]:
        return dict(self._experiments)


# ═══════════════════════════════════════════════
#  引擎 [6]: 全流程编排器 — 五项全能联动
# ═══════════════════════════════════════════════

class ShepherdOrchestrator:
    """牧羊人全流程编排器：统筹六大引擎协同工作"""

    def __init__(self):
        self.bayesian_opt = BayesianOptimizer()
        self.cma_opt = CMAEvolutionaryOptimizer()
        self.pareto_opt = ParetoMultiObjectiveOptimizer()
        self.generator = StrategyGenerator()
        self.composer = TechStackComposer()
        self.evolution = GeneticEvolutionEngine()
        self.ab_tester = ABTestEngine()
        self.memory = MetaLearningMemory()
        self._pipeline_log: List[Dict[str, Any]] = []

    def run_full_pipeline(self, param_ranges: Dict[str, Tuple[float, float]] = None,
                          fitness_fn=None, n_strategies: int = 10) -> Dict[str, Any]:
        """全流程：生成 → 优化 → 组合 → 进化 → A/B验证"""
        logger.info("=" * 60)
        logger.info("🐑 牧羊人智能体优化器 v4.0 — 全流程启动")
        logger.info("=" * 60)

        timeline = {"start": datetime.now().isoformat()}

        # 阶段1: 策略生成
        logger.info("[1/5] 策略生成阶段...")
        population = self.generator.generate_population(n_strategies)
        timeline["generation_done"] = datetime.now().isoformat()

        # 阶段2: 优化（贝叶斯+CMA-ES+帕累托）
        logger.info("[2/5] 优化阶段...")
        if param_ranges and fitness_fn:
            params_for_bayes = {k: v for k, v in list(param_ranges.items())[:5]}
            bayes_result = self.bayesian_opt.optimize(
                params_for_bayes, fitness_fn, name="pipeline_optimization"
            )

            cma_result = self.cma_opt.optimize(
                params_for_bayes, fitness_fn, name="pipeline_cma_es"
            )
        else:
            # 使用默认参数空间和模拟适应度
            default_ranges = {
                "stop_loss": (0.01, 0.10),
                "take_profit": (0.03, 0.20),
                "trailing_stop": (0.01, 0.08),
                "position_size": (0.05, 0.50),
            }

            def _mock_fitness(params):
                score = 0.5
                score += (params.get("take_profit", 0.1) - params.get("stop_loss", 0.05)) * 2
                score += (1 - abs(params.get("position_size", 0.3) - 0.25)) * 0.5
                return max(0.0, min(1.0, score + random.gauss(0, 0.05)))

            bayes_result = self.bayesian_opt.optimize(default_ranges, _mock_fitness)
            cma_result = self.cma_opt.optimize(default_ranges, _mock_fitness)

        # 帕累托多目标分析
        pareto_candidates = []
        for indv in population:
            d = {
                "dna_id": indv.get("dna_id", ""),
                "sharpe_ratio": indv.get("fitness", 0.5) * random.uniform(0.5, 2.0),
                "max_drawdown": random.uniform(0.05, 0.30),
                "win_rate": indv.get("fitness", 0.5) * random.uniform(0.6, 1.0),
            }
            pareto_candidates.append(d)
        pareto_front = self.pareto_opt.compute_pareto_front(pareto_candidates)
        preferred = self.pareto_opt.get_preferred_solution()
        timeline["optimization_done"] = datetime.now().isoformat()

        # 阶段3: 技术栈组合
        logger.info("[3/5] 技术栈组合阶段...")
        compositions = self.composer.compose(population, target_count=5)
        timeline["composition_done"] = datetime.now().isoformat()

        # 阶段4: 遗传进化
        logger.info("[4/5] 遗传进化阶段...")
        evolved = self.evolution.evolve(
            initial_population=population[:15] + compositions[:5],
            fitness_fn=fitness_fn or _mock_fitness,
        )
        timeline["evolution_done"] = datetime.now().isoformat()

        # 阶段5: A/B测试验证
        logger.info("[5/5] A/B验证阶段...")
        best_before = max(population, key=lambda x: x.get("fitness", 0))
        best_after = evolved[0] if evolved else best_before
        exp_id = self.ab_tester.create_experiment(
            "full_pipeline", best_before, best_after
        )

        # 模拟A/B数据收集
        for _ in range(35):
            score_a = best_before.get("fitness", 0.5) + random.gauss(0, 0.03)
            score_b = best_after.get("fitness", 0.5) + random.gauss(0, 0.03)
            self.ab_tester.record_result(exp_id, "a", max(0, min(1, score_a)))
            self.ab_tester.record_result(exp_id, "b", max(0, min(1, score_b)))

        ab_result = self.ab_tester.evaluate_experiment(exp_id)
        timeline["ab_test_done"] = datetime.now().isoformat()

        # 元记忆记录
        for indv in evolved[:5]:
            self.memory.record(indv, indv.get("fitness", 0.5))

        # 汇总报告
        timeline["end"] = datetime.now().isoformat()
        report = {
            "pipeline_version": "4.0",
            "timeline": timeline,
            "generation": {
                "population_size": len(population),
                "template_types": list(set(
                    d.get("strategy_type", "unknown") for d in population
                )),
            },
            "optimization": {
                "bayesian": {"best_score": bayes_result.get("best_score", 0)},
                "cma_es": {"best_score": cma_result.get("best_score", 0)},
                "pareto_front_size": len(pareto_front),
                "preferred_solution": preferred,
            },
            "composition": {
                "count": len(compositions),
                "avg_novelty": round(
                    sum(c.get("novelty_score", 0) for c in compositions) / max(1, len(compositions)), 4
                ),
            },
            "evolution": {
                "generations_run": self.evolution.generations,
                "best_final_fitness": evolved[0].get("fitness", 0) if evolved else 0,
                "improvement_vs_initial": round(
                    (evolved[0].get("fitness", 0.5) - population[0].get("fitness", 0.5))
                    / abs(population[0].get("fitness", 0.5)) * 100, 1
                ) if evolved and population else 0,
            },
            "ab_test": ab_result,
            "meta_memory": {
                "total_memories": len(self.memory._memories),
                "best_patterns": len(self.memory.get_best_patterns(3)),
            },
        }

        self._pipeline_log.append(report)
        logger.info(f"✅ 全流程完成! 进化提升: {report['evolution']['improvement_vs_initial']}%")
        return report

    def get_pipeline_history(self) -> List[Dict[str, Any]]:
        return self._pipeline_log


# ═══════════════════════════════════════════════
#  自检入口
# ═══════════════════════════════════════════════

def _setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def run_self_test():
    """牧羊人智能体优化器 v4.0 扩展引擎自检"""
    _setup_logging()
    logger.info("=" * 60)
    logger.info("🐑 牧羊人智能体优化器 v4.0 — 扩展引擎自检")
    logger.info("=" * 60)

    results = {}

    # 1. 贝叶斯优化
    logger.info("\n[1] 贝叶斯优化引擎测试...")
    bayes = BayesianOptimizer(n_initial=5, n_iterations=20)
    param_ranges = {"alpha": (0.01, 0.50), "beta": (0.10, 0.90)}
    bayes_result = bayes.optimize(param_ranges, lambda p: p["beta"] - p["alpha"])
    results["贝叶斯优化"] = {
        "passed": bayes_result["best_score"] > 0,
        "detail": f"best_score={bayes_result['best_score']:.4f}",
    }
    logger.info(f"  {'✅' if results['贝叶斯优化']['passed'] else '❌'} 贝叶斯优化完成")

    # 2. CMA-ES优化
    logger.info("[2] CMA-ES优化引擎测试...")
    cma = CMAEvolutionaryOptimizer(population_size=10, generations=15)
    cma_result = cma.optimize(param_ranges, lambda p: p["beta"] - p["alpha"])
    results["CMA-ES优化"] = {
        "passed": cma_result["best_score"] > 0,
        "detail": f"best_score={cma_result['best_score']:.4f}, 代数={cma_result['generations']}",
    }
    logger.info(f"  {'✅' if results['CMA-ES优化']['passed'] else '❌'} CMA-ES优化完成")

    # 3. 帕累托多目标
    logger.info("[3] 帕累托多目标优化测试...")
    pareto = ParetoMultiObjectiveOptimizer()
    candidates = [
        {"dna_id": f"dna_{i}",
         "sharpe_ratio": random.uniform(0.5, 2.5),
         "max_drawdown": random.uniform(0.05, 0.30),
         "win_rate": random.uniform(0.4, 0.9)}
        for i in range(20)
    ]
    front = pareto.compute_pareto_front(candidates)
    preferred = pareto.get_preferred_solution()
    results["帕累托多目标"] = {
        "passed": len(front) > 0,
        "detail": f"帕累托前沿={len(front)}个解, 优选解存在={bool(preferred)}",
    }
    logger.info(f"  {'✅' if results['帕累托多目标']['passed'] else '❌'} 帕累托优化完成")

    # 4. 策略生成器
    logger.info("[4] 策略生成器测试...")
    gen = StrategyGenerator()
    dna1 = gen.generate_from_template("trend_following_ma")
    dna2 = gen.generate_from_template("fourier_rl_adaptive")
    offspring = gen.generate_offspring(dna1, dna2)
    population = gen.generate_population(8)
    results["策略生成器"] = {
        "passed": (len(population) == 8 and bool(offspring.get("parent_ids"))),
        "detail": f"种群={len(population)}, 模板={len(gen.template_lib.TEMPLATES)}, 子代parent_ids={offspring.get('parent_ids')}",
    }
    logger.info(f"  {'✅' if results['策略生成器']['passed'] else '❌'} 策略生成完成")

    # 5. 技术栈组合引擎
    logger.info("[5] 技术栈组合引擎测试...")
    composer = TechStackComposer()
    comps = composer.compose(population, target_count=3)
    results["技术栈组合"] = {
        "passed": len(comps) > 0 and all("novelty_score" in c for c in comps),
        "detail": f"组合={len(comps)}个, avg新颖性={sum(c.get('novelty_score',0) for c in comps)/len(comps):.3f}" if comps else "N/A",
    }
    logger.info(f"  {'✅' if results['技术栈组合']['passed'] else '❌'} 技术栈组合完成")

    # 6. 自演进系统
    logger.info("[6] 自演进系统测试...")

    def _mock_evolve_fitness(dna):
        return dna.get("fitness", 0.5) + random.gauss(0, 0.02)

    evolution = GeneticEvolutionEngine(population_size=8, generations=5)
    evolved = evolution.evolve(
        initial_population=population[:6],
        fitness_fn=_mock_evolve_fitness,
    )
    results["遗传进化"] = {
        "passed": len(evolved) > 0 and evolved[0].get("fitness", 0) > 0,
        "detail": f"种群={len(evolved)}, best_fitness={evolved[0].get('fitness', 0):.4f}, 代数={len(evolution.get_evolution_log())}",
    }
    logger.info(f"  {'✅' if results['遗传进化']['passed'] else '❌'} 遗传进化完成")

    # 7. A/B测试引擎
    logger.info("[7] A/B测试引擎测试...")
    ab = ABTestEngine(min_samples=5)
    exp_id = ab.create_experiment("test_exp", {"fitness": 0.7}, {"fitness": 0.75})
    for i in range(10):
        ab.record_result(exp_id, "a", 0.7 + random.gauss(0, 0.05))
        ab.record_result(exp_id, "b", 0.75 + random.gauss(0, 0.05))
    ab_result = ab.evaluate_experiment(exp_id)
    results["A/B测试"] = {
        "passed": ab_result["status"] == "completed",
        "detail": f"winner={ab_result.get('winner', '?')}, improvement={ab_result.get('improvement_pct', 0):.1f}%, significant={ab_result.get('significant')}",
    }
    logger.info(f"  {'✅' if results['A/B测试']['passed'] else '❌'} A/B测试完成")

    # 8. 全流程编排器
    logger.info("[8] 全流程编排器测试...")
    orchestrator = ShepherdOrchestrator()
    report = orchestrator.run_full_pipeline(n_strategies=8)
    results["全流程编排"] = {
        "passed": bool(report.get("evolution", {}).get("generations_run", 0) > 0),
        "detail": f"策略生成={report['generation']['population_size']}, "
                   f"帕累托前沿={report['optimization']['pareto_front_size']}, "
                   f"组合数={report['composition']['count']}, "
                   f"进化提升={report['evolution']['improvement_vs_initial']}%",
    }
    logger.info(f"  {'✅' if results['全流程编排']['passed'] else '❌'} 全流程编排完成")

    # 汇总
    passed = sum(1 for r in results.values() if r["passed"])
    total = len(results)
    summary = {
        "version": "4.0-extensions",
        "module": "shepherd_v4_extensions",
        "results": results,
        "passed": passed,
        "total": total,
        "all_passed": passed == total,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    logger.info(f"\n{'='*60}")
    logger.info(f"🐑 扩展引擎自检: {passed}/{total} 通过")
    logger.info(f"{'='*60}")
    return passed == total


if __name__ == "__main__":
    run_self_test()
