#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修复 shepherd_v5_comprehensive.py 截断
补全 ExpertTeamCoordinator 类的剩余方法 + ShepherdV5Comprehensive 主类 + 自检
"""
import re

TARGET = "shepherd_v5_comprehensive.py"

with open(TARGET, "r", encoding="utf-8") as f:
    lines = f.readlines()

# 找到需要替换的截断位置（第1337行）
# 原行: '                opinion = self._data_quality_review\n'
# 需要补全这一行及之后所有内容
# 策略：删除从1337行末尾开始的所有不完整内容，补全完整方法与类

# 保留前1336行完整内容
original_content = "".join(lines)
# 截断点后的内容标记（第1337行开始不完整）
cut_marker_line = "                opinion = self._data_quality_review\n"

if cut_marker_line not in original_content:
    print("未找到截断标记行，退出。")
    exit(1)

# 需要替换的片段：从截断行到文件末尾
old_tail_start = 1336  # 0-based: 前1336行保留（即第1-1336行）
old_tail = "".join(lines[old_tail_start:])

# 新内容（完整补全）
new_tail = '''                opinion = self._data_quality_review(opinion, strategy, dims_present)
            elif expert["id"] == 8:  # 测试覆盖专家
                opinion = self._test_coverage_review(opinion, strategy, dims_present)
            elif expert["id"] == 10:  # AI/ML集成专家
                opinion = self._ai_ml_review(opinion, strategy, dims_present, config)
            else:
                opinion = self._generic_review(opinion, strategy, expert, dims_present)

            # 记录创造性基因建议
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
        """架构设计审计师评审"""
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
        """金融风控合规官评审"""
        risk_genes = ["stop_loss", "position_sizing", "var_monitor", "drawdown_control"]
        matched = dims_present & set(risk_genes)
        if financial_eval:
            opinion.score = min(1.0, 0.5 + 0.1 * financial_eval.overall_grade / 20)
            if financial_eval.max_drawdown_ok:
                opinion.strengths.append(f"最大回撤控制达标 (≤{financial_eval.max_drawdown_limit*100}%)")
            else:
                opinion.weaknesses.append(f"最大回撤超标")
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
        """性能工程师评审"""
        perf_genes = ["parallel_execution", "caching", "vectorized_ops", "low_latency"]
        matched = dims_present & set(perf_genes)
        config = strategy.get("configuration", {})
        has_parallel = config.get("parallel_workers", 0) > 1 or "并行" in str(config)
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
        """数据质量专家评审"""
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
        """测试覆盖专家评审"""
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
        """AI/ML集成专家评审"""
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
        """通用评审（适用未专属定制的专家）"""
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
        """专家基于评审生成创造性基因方案"""
        # 只有高评分专家才产生创造性输入
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
            "expert_id": expert["id"],
            "expert_name": expert["name"],
            "dimension": focus_area,
            "suggested_gene": template["gene"],
            "description": template["desc"],
            "confidence": opinion.score,
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
        """多轮审议，生成优化策略"""
        logger.info(f"🏛️ 策略审议引擎启动: {len(base_strategies)} 个基础策略, 最多 {max_rounds} 轮")
        all_genes: List[Dict[str, Any]] = []
        for s in base_strategies:
            genes = s.get("genes_used", [])
            all_genes.extend(genes)

        for round_idx in range(max_rounds):
            logger.info(f"  📋 审议第 {round_idx + 1} 轮...")
            proposals = []
            for strat in base_strategies:
                review = self.coordinator.conduct_review(strat)
                # 收集所有创造性建议
                creative_inputs = []
                for dim_opinions in review.values():
                    for op in dim_opinions:
                        if op.creative_inputs:
                            creative_inputs.extend(op.creative_inputs)
                if creative_inputs:
                    proposals.append({
                        "strategy_name": strat.get("strategy_name", "unknown"),
                        "creative_inputs": creative_inputs,
                        "avg_score": np.mean([op.score for ops in review.values() for op in ops]),
                    })

            # 共识评分
            if proposals:
                consensus_score = np.mean([p["avg_score"] for p in proposals])
            else:
                consensus_score = 0.5

            # 合并基因
            merged = self._merge_creative_genes(proposals)
            self.deliberation_history.append(DeliberationRound(
                round_id=round_idx + 1,
                proposals=proposals,
                consensus_score=consensus_score,
                merged_genes=merged,
            ))
            logger.info(f"    共识评分: {consensus_score:.2f}, 合并基因数: {len(merged)}")

            # 收敛判断
            if consensus_score > 0.85 and round_idx >= 1:
                logger.info(f"  ✅ 审议收敛 (共识>{0.85})")
                break

        return {
            "rounds": len(self.deliberation_history),
            "final_consensus": self.deliberation_history[-1].consensus_score if self.deliberation_history else 0,
            "merged_genes": self.deliberation_history[-1].merged_genes if self.deliberation_history else [],
            "history": [asdict(r) for r in self.deliberation_history],
        }

    def _merge_creative_genes(self, proposals: List[Dict]) -> List[Dict[str, Any]]:
        """合并多专家创造性基因建议"""
        gene_map: Dict[str, Dict] = {}
        for prop in proposals:
            for ci in prop.get("creative_inputs", []):
                gene_name = ci.get("suggested_gene", "")
                if gene_name not in gene_map:
                    gene_map[gene_name] = {
                        "gene": gene_name,
                        "description": ci.get("description", ""),
                        "dimension": ci.get("dimension", ""),
                        "supporters": [],
                        "avg_confidence": ci.get("confidence", 0.5),
                    }
                gene_map[gene_name]["supporters"].append(ci.get("expert_name", "unknown"))
                gene_map[gene_name]["avg_confidence"] = max(
                    gene_map[gene_name]["avg_confidence"],
                    ci.get("confidence", 0.5),
                )
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
        """执行基因进化"""
        logger.info(f"🧬 基因进化引擎启动: 种群={self.population_size}, 代数={generations}")
        # 提取初始基因池
        gene_pool = []
        for s in base_strategies:
            genes = s.get("genes_used", [])
            gene_pool.extend(genes)
        if not gene_pool:
            gene_pool = [{"name": f"base_gene_{i}", "dimension": "general", "weight": 0.5}
                         for i in range(10)]

        # 初始化种群
        population = self._initialize_population(gene_pool)
        best_overall = None
        best_fitness_overall = -float("inf")

        for gen in range(generations):
            # 评估适应度
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

            # 选择、交叉、变异
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
                "weights": {g["name"]: random.uniform(0.1, 1.0) for g in gene_pool[:10]},
            }
            population.append(individual)
        return population

    def _fitness(self, individual: Dict) -> float:
        """多目标适应度函数"""
        genes = individual.get("genes", [])
        # 基因覆盖度
        coverage = len({g.get("dimension", "") for g in genes}) / max(1, len(genes))
        # 基因多样性
        diversity = len(genes) / max(1, self.population_size)
        # 权重平衡度
        weights = individual.get("weights", {})
        weight_balance = 1.0 - np.std(list(weights.values())) if weights else 0.5
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
        idx1 = candidates[np.argmax([fitness[i] for i in candidates[:k]])]
        idx2 = candidates[k + np.argmax([fitness[i] for i in candidates[k:]])]
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
                if hasattr(genes[idx], "copy"):
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
# Shepherd V5 综合优化器——全面增强版
# =============================================================================
class ShepherdV5Comprehensive:
    """牧羊人V5综合智能体优化器
    整合：
    - 12位专家评审体系（金融级审查）
    - 策略基因提取与新生策略生成
    - 审议引擎（多专家协同创造）
    - 基因进化引擎（遗传算法驱动自演进）
    - 金融级评测标准框架
    - 自演进机制（调用智能体团专家共同推进）
    """

    def __init__(self):
        self.gene_extractor = GeneExtractor()
        self.novel_generator = NovelStrategyGenerator(
            gene_extractor=self.gene_extractor,
            use_deep_learning=True,
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
        """⛓️ 综合进化管线：全流程策略自演进
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
            extracted = self.gene_extractor.extract_genes(s)
            all_genes.extend(extracted)
        logger.info(f"  提取基因总数: {len(set(g.get('name','') for g in all_genes))}")

        # Phase 2: 专家评审
        logger.info("[Phase 2/6] 12位专家评审...")
        review_results = []
        for s in base_strategies:
            financial_eval = self.financial_evaluator.evaluate(s)
            review = self.expert_coordinator.conduct_review(s, financial_eval)
            review_results.append({
                "strategy": s.get("strategy_name", "unknown"),
                "financial_eval": asdict(financial_eval) if financial_eval else None,
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
        novel_strategies = self.novel_generator.generate(
            base_strategies, n_strategies=max(5, len(base_strategies) * 2)
        )
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
            fe = self.financial_evaluator.evaluate(s)
            financial_results.append({
                "strategy": s.get("strategy_name", "unknown"),
                "grade": fe.overall_grade if fe else 0,
                "grade_label": fe.grade_label if fe else "N/A",
                "passed": fe.passed if fe else False,
            })
        avg_grade = np.mean([r["grade"] for r in financial_results]) if financial_results else 0
        pass_rate = sum(1 for r in financial_results if r["passed"]) / max(1, len(financial_results))
        logger.info(f"  平均评级: {avg_grade:.1f}, 通过率: {pass_rate:.0%}")

        # 汇总报告
        report = {
            "generation_id": self._generation_counter,
            "timestamp": datetime.now().isoformat(),
            "phases": {
                "基因提取": {"gene_count": len(set(g.get('name','') for g in all_genes))},
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
            "overall_score": self._compute_overall_score(avg_grade, pass_rate,
                                                         evolution_result["improvement_vs_initial"]),
        }
        self.optimization_history.append(report)
        logger.info(f"\n✅ ShepherdV5 综合进化完成: 综合评分={report['overall_score']:.2f}")
        return report

    def _compute_overall_score(self, avg_grade: float, pass_rate: float,
                               improvement: float) -> float:
        """金融级综合评分 (0-100)"""
        score = 0.35 * avg_grade + 0.3 * pass_rate * 100 + 0.2 * min(100, max(0, improvement + 50))
        score += 0.15 * 50  # 基础分
        return min(100, score)

    # =========================================================================
    # 自演进机制
    # =========================================================================
    def self_evolve(self, n_cycles: int = 5, n_generations_per_cycle: int = 5) -> Dict[str, Any]:
        """🔄 自演进机制：调用智能体团专家共同推进自演进
        每轮演进都会：
        1. 回顾历史优化记录
        2. 调用专家评审当前策略热度
        3. 驱动审议引擎生成新基因方案
        4. 运行进化引擎
        5. 金融评测
        6. 记录并反馈
        """
        logger.info(f"\n{'='*60}")
        logger.info(f"🔄 自演进机制启动: {n_cycles} 轮, 每轮 {n_generations_per_cycle} 代")
        logger.info(f"{'='*60}")

        # 初始策略种子
        seed_strategies = self._generate_seed_strategies()
        current_strategies = deepcopy(seed_strategies)
        evolution_log = []

        for cycle in range(n_cycles):
            logger.info(f"\n--- 自演进 第 {cycle+1}/{n_cycles} 轮 ---")

            # 调用专家团队回顾和改进
            logger.info("  📋 专家团队回顾历史...")
            historical_insights = self._analyze_history()
            meta_suggestions = self._expert_meta_review(historical_insights)

            # 根据元建议调整策略
            if meta_suggestions:
                current_strategies = self._apply_meta_suggestions(
                    current_strategies, meta_suggestions
                )

            # 运行综合进化
            result = self.run_comprehensive_evolution(
                current_strategies,
                n_generations=n_generations_per_cycle,
            )

            # 选取优胜策略作为下一轮种子
            financial_results = result.get("financial_results", [])
            if financial_results:
                passed = [r for r in financial_results if r["passed"]]
                if passed:
                    passed_names = {r["strategy"] for r in passed}
                    current_strategies = [s for s in result.get("novel_strategies", [])
                                          if s.get("strategy_name") in passed_names]
                    if len(current_strategies) < 3:
                        current_strategies.extend(seed_strategies[:3])

            evolution_log.append({
                "cycle": cycle + 1,
                "overall_score": result["overall_score"],
                "avg_grade": result["phases"]["金融评测"]["avg_grade"],
                "pass_rate": result["phases"]["金融评测"]["pass_rate"],
                "improvement": result["evolution_result"]["improvement_vs_initial"],
            })

            # 早停检查
            if (cycle >= 2 and
                all(log["overall_score"] >= 85 for log in evolution_log[-2:]) and
                evolution_log[-1]["overall_score"] - evolution_log[-2]["overall_score"] < 0.5):
                logger.info(f"  🎯 自演进收敛 (连续高分+变化<0.5)，提前终止")
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
                                "weight": random.uniform(0.3, 0.9)}
                               for g in t["genes"]],
                "configuration": {
                    "parallel_workers": random.choice([1, 2, 4]),
                    "rl_enabled": "rl_agent" in t["