#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自演进优化引擎 - 历史最佳策略的记忆与进化
"""

import json
import os
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, field


@dataclass
class StrategyDNA:
    """策略 DNA - 进化遗传信息"""
    strategy_id: str
    params: Dict[str, Any]
    fitness: float
    sharpe: float
    max_drawdown: float
    win_rate: float
    total_return: float
    generation: int
    created_at: str
    parent_ids: List[str] = field(default_factory=list)
    market_regime: str = 'unknown'
    adaptability_score: float = 0.0


class AutoEvolutionEngine:
    """
    自演进优化引擎
    ===============
    功能：
    1. 策略基因库 - 历史最佳策略存储与检索
    2. 进化算法 - 从历史最优策略中衍生新策略
    3. 市场环境自适应 - 根据当前市场匹配最佳历史策略
    4. 分阶段优化 - 探索 → 开发 → 精炼
    5. 策略多样性保护 - 防止过度集中
    """

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.population: List[StrategyDNA] = []
        self.elite_archive: List[StrategyDNA] = []
        self.evolution_history: List[Dict] = []
        self.market_regimes: Dict[str, List[str]] = {}
        self.generation_count = 0
        self.population_size = config.get('population_size', 50)
        self.elite_size = config.get('elite_size', 10)
        self.mutation_rate = config.get('mutation_rate', 0.2)
        self.crossover_rate = config.get('crossover_rate', 0.7)
        self.memory_dir = config.get('memory_dir', './ml/memory/')
        os.makedirs(self.memory_dir, exist_ok=True)
        self._load_memories()

    def _load_memories(self):
        """加载持久化记忆"""
        memory_files = [
            'ml_institutional_memory.json',
            'ml_permanent_memory.json',
            'ml_covariance_opt.json',
            'positive_profitable_strategy_ml_memory.json'
        ]
        for fname in memory_files:
            path = os.path.join(self.memory_dir, fname)
            if not os.path.exists(path):
                path = os.path.join('.', fname)
            if os.path.exists(path):
                try:
                    with open(path) as f:
                        data = json.load(f)
                        if isinstance(data, dict):
                            self.evolution_history.append({'source': fname, 'data': data, 'loaded_at': datetime.now().isoformat()})
                except Exception:
                    pass

    def add_to_population(self, strategy: StrategyDNA):
        """将策略加入进化种群"""
        strategy.generation = self.generation_count
        self.population.append(strategy)

    def evaluate_population(self) -> Dict[str, Any]:
        """评估当前种群"""
        if not self.population:
            return {'status': 'empty', 'population_size': 0}

        sharpes = [s.sharpe for s in self.population if s.sharpe is not None]
        returns = [s.total_return for s in self.population if s.total_return is not None]
        win_rates = [s.win_rate for s in self.population if s.win_rate is not None]

        return {
            'population_size': len(self.population),
            'best_sharpe': max(sharpes) if sharpes else 0,
            'avg_sharpe': np.mean(sharpes) if sharpes else 0,
            'best_return': max(returns) if returns else 0,
            'avg_win_rate': np.mean(win_rates) if win_rates else 0,
            'generation': self.generation_count,
            'unique_strategies': len(set(s.strategy_id for s in self.population)),
            'archived_elites': len(self.elite_archive)
        }

    def select_elite(self) -> List[StrategyDNA]:
        """精英选择 - 保留最优策略到精英档案"""
        if not self.population:
            return []

        sorted_pop = sorted(self.population, key=lambda s: s.fitness, reverse=True)
        elites = sorted_pop[:self.elite_size]

        for elite in elites:
            if elite not in self.elite_archive:
                self.elite_archive.append(elite)

        # 精英档案裁剪
        if len(self.elite_archive) > 200:
            self.elite_archive = sorted(self.elite_archive, key=lambda s: s.fitness, reverse=True)[:200]

        return elites

    def crossover(self, parent1: StrategyDNA, parent2: StrategyDNA) -> StrategyDNA:
        """交叉操作 - 从两个父代生成子代"""
        child_params = {}
        all_keys = set(parent1.params.keys()) | set(parent2.params.keys())

        for key in all_keys:
            if np.random.random() < self.crossover_rate:
                # 交叉：取两个父代的加权平均
                v1 = parent1.params.get(key, 0)
                v2 = parent2.params.get(key, 0)
                if isinstance(v1, (int, float)) and isinstance(v2, (int, float)):
                    alpha = np.random.random()
                    child_params[key] = alpha * v1 + (1 - alpha) * v2
                else:
                    child_params[key] = v1 if np.random.random() < 0.5 else v2
            else:
                child_params[key] = parent1.params.get(key, parent2.params.get(key))

        child = StrategyDNA(
            strategy_id=f"evo_{self.generation_count}_{int(np.random.random() * 10000)}",
            params=child_params,
            fitness=0.0, sharpe=0.0, max_drawdown=0.0, win_rate=0.0,
            total_return=0.0, generation=self.generation_count + 1,
            created_at=datetime.now().isoformat(),
            parent_ids=[parent1.strategy_id, parent2.strategy_id],
            market_regime=parent1.market_regime if np.random.random() < 0.7 else parent2.market_regime
        )
        return child

    def mutate(self, strategy: StrategyDNA) -> StrategyDNA:
        """变异操作"""
        for key in strategy.params:
            if np.random.random() < self.mutation_rate:
                v = strategy.params[key]
                if isinstance(v, (int, float)):
                    noise = np.random.normal(0, abs(v) * 0.1 + 0.01)
                    strategy.params[key] = v + noise
        strategy.strategy_id = f"mut_{self.generation_count}_{int(np.random.random() * 10000)}"
        strategy.generation += 1
        return strategy

    def evolve_generation(self, n_offspring: int = 20) -> List[StrategyDNA]:
        """进化一代"""
        if len(self.population) < 2:
            return []

        elites = self.select_elite()
        if len(elites) < 2:
            return []

        offspring = []
        # 交叉生成
        for _ in range(n_offspring * 2 // 3):
            p1, p2 = np.random.choice(elites, 2, replace=False)
            child = self.crossover(p1, p2)
            offspring.append(child)

        # 变异生成
        for _ in range(n_offspring // 3):
            parent = np.random.choice(self.population)
            child = self.mutate(parent)
            offspring.append(child)

        self.generation_count += 1
        self.evolution_history.append({
            'generation': self.generation_count,
            'n_offspring': len(offspring),
            'elite_count': len(elites),
            'timestamp': datetime.now().isoformat(),
            'stats': self.evaluate_population()
        })

        return offspring

    def match_market_regime(self, current_features: Dict[str, float]) -> Optional[StrategyDNA]:
        """
        市场环境自适应 - 根据当前市场特征匹配最佳历史策略
        """
        if not self.elite_archive:
            return None

        # 根据特征计算与当前市场的相似度
        best_match = None
        best_score = -float('inf')

        regime_map = {
            'bull': ['trending', 'uptrend', '牛市'],
            'bear': ['downtrend', '熊市'],
            'volatile': ['high_volatility', '波动'],
            'sideways': ['range', '震荡', '盘整']
        }

        # 简易市场环境判断
        volatility = current_features.get('volatility', 0.02)
        trend = current_features.get('trend_strength', 0)

        if trend > 0.3 and volatility < 0.03:
            current_regime = 'bull'
        elif trend < -0.3 and volatility < 0.03:
            current_regime = 'bear'
        elif volatility > 0.05:
            current_regime = 'volatile'
        else:
            current_regime = 'sideways'

        # 匹配
        for elite in self.elite_archive:
            score = elite.fitness
            # 同市场环境加分
            if any(kw in elite.market_regime.lower() for kw in regime_map.get(current_regime, [])):
                score *= 1.3
            if score > best_score:
                best_score = score
                best_match = elite

        return best_match

    def get_top_strategies(self, n: int = 5, metric: str = 'sharpe') -> List[StrategyDNA]:
        """获取历史最优策略"""
        all_strategies = self.population + self.elite_archive
        sorted_strategies = sorted(all_strategies, key=lambda s: getattr(s, metric, 0), reverse=True)
        return sorted_strategies[:n]

    def suggest_params(self, base_params: Dict[str, Any],
                       current_features: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
        """建议优化后的参数"""
        # 尝试匹配市场环境
        if current_features:
            matched = self.match_market_regime(current_features)
            if matched and matched.fitness > 0.3:
                # 融合历史最佳策略和当前参数
                suggested = base_params.copy()
                for key in matched.params:
                    if key in suggested:
                        alpha = 0.3  # 融合比例
                        suggested[key] = alpha * matched.params[key] + (1 - alpha) * suggested[key]
                return suggested

        # 回退到精英平均
        top = self.get_top_strategies(3)
        if top:
            suggested = base_params.copy()
            for key in base_params:
                values = [s.params.get(key, base_params[key]) for s in top]
                if all(isinstance(v, (int, float)) for v in values):
                    suggested[key] = np.mean(values)
            return suggested

        return base_params

    def save_state(self):
        """持久化进化状态"""
        state = {
            'generation_count': self.generation_count,
            'population_size': len(self.population),
            'elite_archive_size': len(self.elite_archive),
            'elite_archive': [{
                'strategy_id': s.strategy_id,
                'fitness': s.fitness,
                'sharpe': s.sharpe,
                'total_return': s.total_return,
                'market_regime': s.market_regime,
                'created_at': s.created_at
            } for s in self.elite_archive[:50]],
            'evolution_stats': self.evaluate_population(),
            'saved_at': datetime.now().isoformat()
        }
        path = os.path.join(self.memory_dir, 'evolution_state.json')
        with open(path, 'w') as f:
            json.dump(state, f, indent=2, default=str)

    def load_state(self) -> bool:
        """加载进化状态"""
        path = os.path.join(self.memory_dir, 'evolution_state.json')
        if not os.path.exists(path):
            return False
        with open(path) as f:
            state = json.load(f)
        self.generation_count = state.get('generation_count', 0)
        for item in state.get('elite_archive', []):
            dna = StrategyDNA(
                strategy_id=item['strategy_id'],
                params={}, fitness=item.get('fitness', 0),
                sharpe=item.get('sharpe', 0), max_drawdown=0,
                win_rate=0, total_return=item.get('total_return', 0),
                generation=self.generation_count,
                created_at=item.get('created_at', datetime.now().isoformat()),
                market_regime=item.get('market_regime', 'unknown')
            )
            self.elite_archive.append(dna)
        return True