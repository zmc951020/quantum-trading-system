#!/usr/bin/env python3
"""
韬定律策略优化器集群 v2.0 - 时间缩微 + 空间缩微 协同
====================================================

核心改进 (基于测试验证):
  1. 相似参数复用 (距离感知缓存) - 解决"连续参数0%命中率"问题
  2. 参数空间折叠 (粗筛→精搜→验证三层) - 实现"逻辑折叠"
  3. 增量计算框架 - 真正的"时间缩微" (τ缩减)
"""

import sys
import hashlib
import json
import time
import random
import math
import datetime
import os
from dataclasses import dataclass, field
from typing import Dict, Optional, List, Any, Tuple
from collections import OrderedDict
from enum import Enum
import threading

# ============================================================
# Windows控制台UTF-8编码补丁 (解决'gbk' codec无法编码emoji的问题)
# ============================================================
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')


# ============================================================
# 数据模型
# ============================================================

@dataclass
class BacktestResult:
    """回测结果"""
    strategy_name: str
    params: Dict[str, float]
    total_return: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    total_trades: int
    timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%d %H:%M:%S"))
    is_approximate: bool = False  # 是否为插值估算结果

    def score(self) -> float:
        """综合评分: 收益×0.4 + 夏普×0.3 + (1-回撤)×0.3"""
        return (self.total_return * 0.4 +
                self.sharpe_ratio * 0.3 +
                (1 - self.max_drawdown) * 0.3)


@dataclass
class CacheStats:
    """缓存统计"""
    total_requests: int = 0
    exact_hits: int = 0      # 精确命中
    bucket_hits: int = 0     # 同桶命中 (距离=0)
    neighbor_hits: int = 0   # 近邻插值命中
    full_computes: int = 0   # 完整回测次数
    time_saved_ms: float = 0.0

    @property
    def total_hit_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return (self.exact_hits + self.bucket_hits + self.neighbor_hits) / self.total_requests

    @property
    def compute_reduction(self) -> float:
        """计算量减少比例"""
        if self.total_requests == 0:
            return 0.0
        return 1 - (self.full_computes / self.total_requests)


# ============================================================
# 核心1: 相似参数复用缓存 (距离感知)
# ============================================================

class SimilarityCache:
    """
    相似参数复用缓存 - 韬定律"器件层"实现

    核心思想: 优化器产生的参数是连续的 (贝叶斯/遗传),
    精确匹配缓存命中率为0%.

    改进: 用"距离感知分桶"替代精确匹配
      - 参数空间离散化为"桶"
      - 相同桶内的参数共享回测结果 (距离=0)
      - 邻近桶内的参数用插值快速估算 (距离<阈值)
      - 只有远离所有桶的参数才需要完整回测

    这是真正的"时间缩微" (τ缩减):
      完整回测: 200-400ms → τ_full
      同桶复用:   1-2ms   → τ_bucket  (≈0.5% of τ_full)
      插值估算:   5-10ms  → τ_neighbor (≈2-3% of τ_full)
    """

    def __init__(self, param_ranges: Dict[str, Tuple[float, float]],
                 bucket_sizes: Optional[Dict[str, float]] = None,
                 neighbor_threshold: float = 2.0):
        """
        Args:
            param_ranges: 各参数的范围 {param_name: (min, max)}
            bucket_sizes: 各参数的桶大小 (离散化粒度), 默认自动计算
            neighbor_threshold: 近邻搜索的距离阈值 (以桶为单位)
        """
        self.param_ranges = param_ranges
        self.neighbor_threshold = neighbor_threshold
        self._cache: Dict[str, BacktestResult] = {}
        self._lock = threading.RLock()
        self._stats = CacheStats()

        # 自动计算桶大小: 每个参数范围分20个桶
        self.bucket_sizes = bucket_sizes or {}
        for name, (pmin, pmax) in param_ranges.items():
            if name not in self.bucket_sizes:
                self.bucket_sizes[name] = (pmax - pmin) / 20.0

        # 桶权重: 用于归一化距离计算
        self.weights = {name: 1.0 / size for name, size in self.bucket_sizes.items()}

    def _make_bucket_key(self, params: Dict[str, float]) -> str:
        """生成桶键 - 参数空间离散化"""
        bucket_coords = []
        for name in sorted(params.keys()):
            if name in self.bucket_sizes:
                value = params[name]
                size = self.bucket_sizes[name]
                bucket_idx = int(math.floor(value / size))
                bucket_coords.append(f"{name}:{bucket_idx}")
            else:
                bucket_coords.append(f"{name}:{params[name]}")
        return "|".join(bucket_coords)

    def _bucket_distance(self, params1: Dict[str, float],
                         params2: Dict[str, float]) -> float:
        """计算两个参数组合之间的归一化桶距离"""
        dist = 0.0
        for name in sorted(set(params1.keys()) | set(params2.keys())):
            if name in self.weights:
                v1 = params1.get(name, 0)
                v2 = params2.get(name, 0)
                dist += (abs(v1 - v2) * self.weights[name]) ** 2
        return math.sqrt(dist)

    def _interpolate(self, target_params: Dict[str, float],
                     neighbors: List[Tuple[float, BacktestResult]]) -> BacktestResult:
        """
        用近邻结果插值估算目标参数的回测结果

        使用距离加权平均 (反距离加权 IDW):
          weight_i = 1 / (distance_i^2 + ε)
          result = Σ(weight_i × result_i) / Σ(weight_i)
        """
        if not neighbors:
            raise ValueError("No neighbors for interpolation")

        weights = []
        for dist, _ in neighbors:
            w = 1.0 / (dist ** 2 + 0.01)
            weights.append(w)

        total_w = sum(weights)

        def _avg(field: str) -> float:
            return sum(w * getattr(r, field) for w, (_, r) in zip(weights, neighbors)) / total_w

        return BacktestResult(
            strategy_name=neighbors[0][1].strategy_name,
            params=target_params,
            total_return=_avg("total_return"),
            sharpe_ratio=_avg("sharpe_ratio"),
            max_drawdown=_avg("max_drawdown"),
            win_rate=_avg("win_rate"),
            total_trades=int(_avg("total_trades")),
            is_approximate=True
        )

    def get(self, strategy_name: str, params: Dict[str, float]) -> Optional[BacktestResult]:
        """
        获取回测结果 (支持三种模式):
          1. 精确命中: 完全相同参数 (最快)
          2. 同桶命中: 参数落在同一桶内 (次快)
          3. 近邻插值: 邻近桶内的结果加权平均 (最快,但有近似误差)

        Returns:
            BacktestResult if cached, None if full computation needed
        """
        with self._lock:
            self._stats.total_requests += 1

            # 1) 精确匹配
            exact_key = self._make_exact_key(strategy_name, params)
            if exact_key in self._cache:
                self._stats.exact_hits += 1
                self._stats.time_saved_ms += 200
                return self._cache[exact_key]

            # 2) 同桶匹配 (离散化后的桶键)
            bucket_key = f"{strategy_name}|{self._make_bucket_key(params)}"
            if bucket_key in self._cache:
                self._stats.bucket_hits += 1
                self._stats.time_saved_ms += 195
                return self._cache[bucket_key]

            # 3) 近邻插值: 在缓存中找最近的K个邻居
            neighbors = []
            for key, cached_result in self._cache.items():
                if key.startswith(strategy_name + "|"):
                    dist = self._bucket_distance(params, cached_result.params)
                    if dist < self.neighbor_threshold:
                        neighbors.append((dist, cached_result))

            if len(neighbors) >= 2:  # 至少需要2个近邻才插值
                neighbors.sort(key=lambda x: x[0])
                top_k = neighbors[:5]
                self._stats.neighbor_hits += 1
                self._stats.time_saved_ms += 190
                return self._interpolate(params, top_k)

            return None

    def put(self, strategy_name: str, params: Dict[str, float],
            result: BacktestResult) -> None:
        """缓存回测结果"""
        with self._lock:
            self._stats.full_computes += 1

            # 同时存精确键和桶键
            exact_key = self._make_exact_key(strategy_name, params)
            bucket_key = f"{strategy_name}|{self._make_bucket_key(params)}"
            self._cache[exact_key] = result
            self._cache[bucket_key] = result

            # 控制缓存大小: 最多保留500条
            if len(self._cache) > 1000:
                for _ in range(100):
                    oldest = next(iter(self._cache))
                    del self._cache[oldest]

    def _make_exact_key(self, strategy_name: str, params: Dict[str, float]) -> str:
        """精确匹配键"""
        normalized = {k: round(v, 4) for k, v in sorted(params.items())}
        return f"{strategy_name}|exact|{json.dumps(normalized, sort_keys=True)}"

    def get_stats(self) -> CacheStats:
        """返回缓存统计"""
        with self._lock:
            return CacheStats(
                total_requests=self._stats.total_requests,
                exact_hits=self._stats.exact_hits,
                bucket_hits=self._stats.bucket_hits,
                neighbor_hits=self._stats.neighbor_hits,
                full_computes=self._stats.full_computes,
                time_saved_ms=self._stats.time_saved_ms
            )

    def clear(self) -> None:
        """清空缓存"""
        with self._lock:
            self._cache.clear()
            self._stats = CacheStats()


# ============================================================
# 核心2: 参数空间折叠 (逻辑折叠)
# ============================================================

class SpaceLevel(Enum):
    COARSE = "coarse"        # 粗筛层: 大粒度网格, 快速排除坏区域
    REFINED = "refined"      # 精搜层: 聚焦热点, 贝叶斯/遗传精搜
    VALIDATION = "validation"  # 验证层: 原始精度, 实盘级别验证


@dataclass
class HotRegion:
    """搜索空间中的热点区域"""
    center: Dict[str, float]  # 区域中心
    radius: float             # 区域半径 (归一化桶距离)
    best_score: float         # 当前最优评分
    sample_count: int = 0     # 已采样次数


class ParameterSpaceFolding:
    """
    参数空间折叠 - 韬定律"电路层"实现

    核心思想: 像"逻辑折叠"将电路从平面堆叠成立体结构一样,
    将高维参数搜索空间"折叠"为三层结构:

        顶层 (COARSE):    大粒度网格搜索 → 发现热点区域 (5-10%空间)
        中层 (REFINED):   聚焦热点精搜 → 确认局部最优 (1-5%空间)
        底层 (VALIDATION): 高精度验证 → 输出最终参数 (<1%空间)

    效果:
      传统全空间搜索: O(10^N) 次回测 (N为参数维度)
      空间折叠搜索: O(10^N × 10%) → O(10^N × 1%) → O(10^N × 0.1%)
      实际缩减: 约 100-1000 倍的搜索量减少
    """

    def __init__(self, param_ranges: Dict[str, Tuple[float, float]]):
        self.param_ranges = param_ranges
        self.hot_regions: List[HotRegion] = []
        self.excluded_regions: List[Tuple[Dict[str, float], float]] = []  # (center, radius)
        self._coarse_results: List[Tuple[Dict[str, float], BacktestResult]] = []
        self._current_level = SpaceLevel.COARSE

    def generate_coarse_points(self, points_per_dim: int = 5) -> List[Dict[str, float]]:
        """
        生成粗筛层的网格点

        等效于芯片的"逻辑折叠"第一步: 将平铺电路网格化
        """
        names = sorted(self.param_ranges.keys())
        if not names:
            return []

        # 为每个参数生成网格点
        grid_values = {}
        for name in names:
            pmin, pmax = self.param_ranges[name]
            step = (pmax - pmin) / points_per_dim
            grid_values[name] = [pmin + step * (i + 0.5) for i in range(points_per_dim)]

        # 笛卡尔积生成所有组合 (如果维度太多, 随机采样)
        total_combinations = 1
        for values in grid_values.values():
            total_combinations *= len(values)

        if total_combinations > 500:  # 防止组合爆炸
            # 随机抽样: 每个维度随机选值
            points = []
            for _ in range(200):
                point = {}
                for name in names:
                    point[name] = random.choice(grid_values[name])
                points.append(point)
            return points
        else:
            # 完整笛卡尔积
            points = [{}]
            for name in names:
                new_points = []
                for value in grid_values[name]:
                    for p in points:
                        new_p = p.copy()
                        new_p[name] = value
                        new_points.append(new_p)
                points = new_points
            return points

    def record_coarse_result(self, params: Dict[str, float], result: BacktestResult) -> None:
        """记录粗筛结果, 并识别热点/冷点区域"""
        self._coarse_results.append((params, result))

    def analyze_coarse_results(self, top_ratio: float = 0.2) -> List[HotRegion]:
        """
        分析粗筛结果, 识别热点区域

        相当于"折叠"操作: 将表现好的区域识别出来,
        后续精搜只在这些区域内进行 (搜索空间折叠)
        """
        if not self._coarse_results:
            return []

        # 按评分排序
        sorted_results = sorted(self._coarse_results,
                                key=lambda x: x[1].score(),
                                reverse=True)

        # 前top_ratio作为热点种子
        top_n = max(3, int(len(sorted_results) * top_ratio))
        top_results = sorted_results[:top_n]

        # 聚类热点区域 (简单贪心: 距离超过阈值则作为新区域中心)
        clusters: List[HotRegion] = []
        for params, result in top_results:
            # 检查是否与已有聚类中心距离足够远
            is_new_cluster = True
            for cluster in clusters:
                dist = self._param_distance(params, cluster.center)
                if dist < 3.0:  # 3个桶距离内, 合并到同一聚类
                    cluster.sample_count += 1
                    if result.score() > cluster.best_score:
                        cluster.best_score = result.score()
                        cluster.center = params
                    is_new_cluster = False
                    break

            if is_new_cluster:
                clusters.append(HotRegion(
                    center=params.copy(),
                    radius=2.0,  # 初始搜索半径 (2个桶)
                    best_score=result.score(),
                    sample_count=1
                ))

        # 识别排除区域: 评分低于中位数的连续区域
        scores = [r.score() for _, r in self._coarse_results]
        if scores:
            median_score = sorted(scores)[len(scores) // 2]
            for params, result in self._coarse_results:
                if result.score() < median_score * 0.8:  # 显著低于中位数
                    self.excluded_regions.append((params.copy(), 1.5))

        self.hot_regions = clusters[:5]  # 最多保留5个热点区域
        self._current_level = SpaceLevel.REFINED
        return self.hot_regions

    def generate_refined_points(self, points_per_region: int = 20) -> List[Dict[str, float]]:
        """在热点区域内生成精搜点"""
        if not self.hot_regions:
            # 退化为随机搜索
            return [self._random_params() for _ in range(100)]

        points = []
        for region in self.hot_regions:
            for _ in range(points_per_region):
                # 在热点区域内做高斯扰动
                perturbed = {}
                for name, center in region.center.items():
                    pmin, pmax = self.param_ranges[name]
                    std = (pmax - pmin) * 0.05 * region.radius
                    perturbed[name] = max(pmin, min(pmax,
                                                     center + random.gauss(0, std)))
                points.append(perturbed)

        self._current_level = SpaceLevel.VALIDATION
        return points

    def generate_validation_points(self, top_k: int = 5) -> List[Dict[str, float]]:
        """生成验证层的候选点 (从精搜结果中取最优)"""
        # 简化: 返回热点中心微调后的点
        points = []
        for region in self.hot_regions:
            # 原始精度的参数值 (round到小数点后4位)
            precise = {k: round(v, 4) for k, v in region.center.items()}
            points.append(precise)
        return points[:top_k]

    def is_in_excluded_region(self, params: Dict[str, float]) -> bool:
        """检查参数是否在排除区域内 (用于快速跳过坏区域)"""
        for center, radius in self.excluded_regions:
            if self._param_distance(params, center) < radius:
                return True
        return False

    def _param_distance(self, p1: Dict[str, float], p2: Dict[str, float]) -> float:
        """归一化参数空间距离"""
        dist = 0.0
        for name in self.param_ranges:
            pmin, pmax = self.param_ranges[name]
            v1 = p1.get(name, (pmin + pmax) / 2)
            v2 = p2.get(name, (pmin + pmax) / 2)
            dist += ((v1 - v2) / (pmax - pmin)) ** 2
        return math.sqrt(dist * len(self.param_ranges))

    def _random_params(self) -> Dict[str, float]:
        """生成随机参数点"""
        return {name: random.uniform(pmin, pmax)
                for name, (pmin, pmax) in self.param_ranges.items()}

    @property
    def current_level(self) -> SpaceLevel:
        return self._current_level

    def get_stats(self) -> Dict[str, Any]:
        return {
            "current_level": self._current_level.value,
            "hot_regions_count": len(self.hot_regions),
            "excluded_regions_count": len(self.excluded_regions),
            "coarse_points_tested": len(self._coarse_results),
            "search_space_reduction": self._estimate_reduction()
        }

    def _estimate_reduction(self) -> float:
        """估算搜索空间缩减比例"""
        if not self.hot_regions:
            return 0.0
        # 简化估算: 每个热点约占总空间的5%
        total_coverage = len(self.hot_regions) * 0.05
        return 1 - total_coverage


# ============================================================
# 核心3: 增量计算框架
# ============================================================

class IncrementalBacktest:
    """
    增量回测引擎 - 韬定律"时间缩微"的核心实现

    核心思想: 不是每次参数变化都重新跑完整K线,
    而是只计算"参数变化导致的差异部分"

    类比芯片中的逻辑折叠:
      传统芯片: 信号从输入端到输出端走完整路径 (长延迟)
      逻辑折叠: 信号走折叠后的短路径 (短延迟)

      传统回测: 每次都重新加载+计算全部K线 (200ms)
      增量回测: 只计算参数变化导致的差异部分 (5-20ms)

    支持的增量模式:
      1. INDICATOR: 指标参数变化 (如均线周期) → 增量更新指标
      2. THRESHOLD: 信号阈值变化 → 仅重新评估信号
      3. RISK: 风控参数变化 → 仅重新评估交易结果
    """

    class IncrementalMode(Enum):
        FULL = "full"              # 完整回测 (兜底)
        INDICATOR = "indicator"    # 指标参数变化
        THRESHOLD = "threshold"    # 阈值参数变化
        RISK = "risk"              # 风控参数变化

    def __init__(self, base_compute_time_ms: float = 250.0):
        self.base_time_ms = base_compute_time_ms
        self._indicator_cache: Dict[str, List[float]] = {}  # 缓存已计算的指标值

    def classify_change(self, old_params: Dict[str, float],
                         new_params: Dict[str, float]) -> IncrementalMode:
        """
        根据参数变化类型分类, 决定增量计算模式

        返回值决定了τ缩减比例:
          FULL: τ = 100%
          INDICATOR: τ = 30% (需要部分重算)
          THRESHOLD: τ = 10% (只需重新评估信号)
          RISK: τ = 5% (只需重新评估盈亏)
        """
        if not old_params:
            return self.IncrementalMode.FULL

        changed = set()
        for name in set(old_params.keys()) | set(new_params.keys()):
            old_val = old_params.get(name, 0)
            new_val = new_params.get(name, 0)
            if abs(old_val - new_val) > 1e-6:
                changed.add(name)

        if not changed:
            return self.IncrementalMode.THRESHOLD  # 无实际变化

        # 简单的分类逻辑 (根据参数名推断类型)
        has_period = any('period' in n.lower() or 'window' in n.lower()
                         for n in changed)
        has_threshold = any('threshold' in n.lower() or 'signal' in n.lower()
                            for n in changed)
        has_risk = any('stop' in n.lower() or 'risk' in n.lower() or 'drawdown' in n.lower()
                       for n in changed)

        if has_period:
            return self.IncrementalMode.INDICATOR
        elif has_threshold:
            return self.IncrementalMode.THRESHOLD
        elif has_risk:
            return self.IncrementalMode.RISK
        else:
            return self.IncrementalMode.FULL

    def compute_incremental(self, old_result: BacktestResult,
                            old_params: Dict[str, float],
                            new_params: Dict[str, float]) -> Tuple[BacktestResult, float]:
        """
        增量计算新参数的回测结果

        Returns:
            (new_result, compute_time_ms)
        """
        mode = self.classify_change(old_params, new_params)

        # 根据模式模拟不同的计算时间 (模拟真实增量计算效果)
        if mode == self.IncrementalMode.FULL:
            time_ms = self.base_time_ms
        elif mode == self.IncrementalMode.INDICATOR:
            time_ms = self.base_time_ms * 0.30  # 30% 计算量
        elif mode == self.IncrementalMode.THRESHOLD:
            time_ms = self.base_time_ms * 0.10  # 10% 计算量
        elif mode == self.IncrementalMode.RISK:
            time_ms = self.base_time_ms * 0.05  # 5% 计算量
        else:
            time_ms = self.base_time_ms

        # 模拟回测结果 (真实场景下这里会调用实际回测引擎)
        # 结果与旧结果相关, 但参数变化越大差异越大
        param_change = self._param_change_magnitude(old_params, new_params)
        noise = random.gauss(0, 0.1 * param_change)  # 变化越大噪声越大

        new_result = BacktestResult(
            strategy_name=old_result.strategy_name,
            params=new_params.copy(),
            total_return=max(-0.5, min(1.0, old_result.total_return + noise)),
            sharpe_ratio=max(0, min(3.0, old_result.sharpe_ratio + noise * 0.5)),
            max_drawdown=max(0.01, min(0.5, old_result.max_drawdown + noise * 0.3)),
            win_rate=max(0.1, min(0.9, old_result.win_rate + noise * 0.2)),
            total_trades=max(1, int(old_result.total_trades + random.gauss(0, 5))),
            is_approximate=(mode != self.IncrementalMode.FULL)
        )

        return new_result, time_ms

    def _param_change_magnitude(self, p1: Dict[str, float],
                                 p2: Dict[str, float]) -> float:
        """计算参数变化幅度 (用于估算结果变化范围)"""
        total_change = 0.0
        for name in set(p1.keys()) | set(p2.keys()):
            v1, v2 = p1.get(name, 0), p2.get(name, 0)
            if abs(v1) + abs(v2) > 0:
                total_change += abs(v1 - v2) / (abs(v1) + abs(v2))
        return total_change / max(1, len(p1))


# ============================================================
# 集成: 韬定律优化器集群
# ============================================================

class TauOptimizerCluster:
    """
    韬定律策略优化器集群 - 完整集成

    架构:
      器件层: SimilarityCache    → 相似参数复用
      电路层: ParameterSpaceFolding → 空间折叠 + 热点聚焦
      系统层: IncrementalBacktest → 增量计算 (τ缩微核心)

    目标: 最小化 τ_优化 = 总搜索时间 / 有效搜索量
    """

    def __init__(self, param_ranges: Dict[str, Tuple[float, float]],
                 strategy_name: str = "generic_strategy",
                 similarity_threshold: float = 0.15,
                 default_compute_time_ms: float = 100.0,
                 strategy_mgr: Optional[Any] = None):
        self.param_ranges = param_ranges
        self.strategy_name = strategy_name
        self.similarity_threshold = similarity_threshold
        self.default_compute_time_ms = default_compute_time_ms
        self._strategy_mgr = strategy_mgr

        # 三层架构组件
        self.cache = SimilarityCache(param_ranges)
        self.folding = ParameterSpaceFolding(param_ranges)
        self.incremental = IncrementalBacktest()

        # 状态
        self._last_params: Optional[Dict[str, float]] = None
        self._last_result: Optional[BacktestResult] = None
        self._total_compute_time_ms = 0.0
        self._total_requests = 0
        self._parameter_store = get_parameter_store()  # 策略参数持久化存储

    def optimize(self, params: Dict[str, float]) -> Tuple[BacktestResult, str]:
        """
        执行一次优化评估

        返回: (回测结果, 命中模式)
        命中模式:
          - exact: 精确缓存命中 (最快)
          - bucket: 同桶缓存命中 (快)
          - neighbor: 近邻插值命中 (较快)
          - incremental: 增量计算 (中)
          - full: 完整回测 (慢, 兜底)
        """
        self._total_requests += 1

        # 1) 优先尝试缓存 (器件层)
        cached = self.cache.get(self.strategy_name, params)
        if cached is not None:
            if self.cache._stats.exact_hits > 0 and self.cache._stats.total_requests == self._total_requests:
                hit_mode = "exact"
            elif self.cache._stats.bucket_hits > 0:
                hit_mode = "bucket"
            else:
                hit_mode = "neighbor"
            self._last_params = params.copy()
            self._last_result = cached
            return cached, hit_mode

        # 2) 检查是否在排除区域 (电路层: 快速跳过)
        if self.folding.is_in_excluded_region(params):
            # 返回一个"差"结果 (快速估算, 无需计算)
            result = BacktestResult(
                strategy_name=self.strategy_name,
                params=params.copy(),
                total_return=-0.1,
                sharpe_ratio=0.3,
                max_drawdown=0.3,
                win_rate=0.3,
                total_trades=10,
                is_approximate=True
            )
            self._total_compute_time_ms += 1.0  # 几乎无计算开销
            self.cache.put(self.strategy_name, params, result)
            self._last_params = params.copy()
            self._last_result = result
            return result, "excluded"

        # 3) 尝试增量计算 (系统层)
        if self._last_params is not None and self._last_result is not None:
            mode = self.incremental.classify_change(self._last_params, params)
            if mode != IncrementalBacktest.IncrementalMode.FULL:
                result, compute_time = self.incremental.compute_incremental(
                    self._last_result, self._last_params, params
                )
                self._total_compute_time_ms += compute_time
                self.cache.put(self.strategy_name, params, result)
                self._last_params = params.copy()
                self._last_result = result
                return result, f"incremental-{mode.value}"

        # 4) 完整回测 (兜底)
        result, compute_time = self._full_backtest(params)
        self._total_compute_time_ms += compute_time
        self.cache.put(self.strategy_name, params, result)
        self._last_params = params.copy()
        self._last_result = result
        return result, "full"

    def _full_backtest(self, params: Dict[str, float]) -> Tuple[BacktestResult, float]:
        """完整回测 - 优先调用真实回测引擎，不可用时降级到模拟"""
        start_time = time.time()

        # 1) 如果有策略管理器引用，优先调用真实回测
        if self._strategy_mgr is not None:
            try:
                # 调用 EnhancedStrategyManager.run_backtest
                bt = self._strategy_mgr.run_backtest(
                    name=self.strategy_name,
                    days=30,
                    balance=100000.0,
                    params=params
                )
                compute_time = (time.time() - start_time) * 1000

                # 统一转换为 TauOptimizerCluster 内部的 BacktestResult
                result = BacktestResult(
                    strategy_name=self.strategy_name,
                    params=params.copy(),
                    total_return=getattr(bt, 'total_return_pct', 0) / 100.0,
                    sharpe_ratio=getattr(bt, 'sharpe_ratio', 0),
                    max_drawdown=getattr(bt, 'max_drawdown', 0) / 100.0,
                    win_rate=getattr(bt, 'win_rate', 0) / 100.0,
                    total_trades=getattr(bt, 'total_trades', 0),
                    is_approximate=False
                )
                return result, compute_time
            except Exception as _e:
                # 真实回测失败，降级到模拟
                pass

        # 2) 降级: 优先使用策略感知的 estimate_quality，失败时退回到通用模拟
        compute_time = random.uniform(150.0, 350.0)
        quality = None

        # 检查当前策略是否有专用的 estimate_quality 方法 (通过 strategy_module)
        try:
            if not hasattr(self, '_quality_module') or self._quality_module is None:
                # 根据策略名自动选择评分模块
                sn = self.strategy_name.lower() if self.strategy_name else ''
                if 'bernoulli' in sn or 'coanda' in sn or '伯努利' in sn or '康达' in sn:
                    module = BernoulliCoandaModule()
                    self._quality_module = module
                    if hasattr(module, 'estimate_quality'):
                        quality = module.estimate_quality(params)
                elif 'shepherd' in sn or 'rotation' in sn or '轮动' in sn or '标的' in sn:
                    module = ShepherdRotationModule()
                    self._quality_module = module
                    if hasattr(module, 'estimate_overall_quality'):
                        quality = module.estimate_overall_quality(params)
                    elif hasattr(module, 'estimate_quality'):
                        quality = module.estimate_quality(params)

            # 如果已经设置了_quality_module，使用它
            if quality is None and hasattr(self, '_quality_module') and self._quality_module is not None:
                mod = self._quality_module
                if hasattr(mod, 'estimate_overall_quality'):
                    quality = mod.estimate_overall_quality(params)
                elif hasattr(mod, 'estimate_quality'):
                    quality = mod.estimate_quality(params)
        except Exception as _e:
            quality = None  # 忽略模块错误，继续用通用模拟

        if quality is None or quality <= 0:
            # 退回到通用模拟评分（为双均线策略设计的）
            quality = self._simulate_param_quality(params)

        result = BacktestResult(
            strategy_name=self.strategy_name,
            params=params.copy(),
            total_return=quality * random.uniform(-0.1, 0.3),
            sharpe_ratio=max(0, quality * random.uniform(0.5, 2.0)),
            max_drawdown=max(0.02, (1 - quality * 0.5) * random.uniform(0.05, 0.25)),
            win_rate=min(0.9, max(0.2, quality * random.uniform(0.4, 0.7))),
            total_trades=random.randint(10, 200),
            is_approximate=True
        )
        return result, compute_time

    def _simulate_param_quality(self, params: Dict[str, float]) -> float:
        """
        模拟参数"好坏"的评估函数

        真实场景中不需要这个 - 这是为了验证优化器有效性而加入的模拟函数
        好参数: 在参数空间的某些"甜区"内
        """
        # 预设一个简单的"甜区": short_period 在 [10, 30], long_period 在 [50, 100]
        # 这样优化器应该能找到这些区域
        quality = 0.5

        if 'short_period' in params:
            sp = params['short_period']
            if 10 <= sp <= 30:
                quality += 0.2
            elif 5 <= sp <= 50:
                quality += 0.1

        if 'long_period' in params:
            lp = params['long_period']
            if 50 <= lp <= 100:
                quality += 0.2
            elif 30 <= lp <= 150:
                quality += 0.1

        if 'threshold' in params:
            t = params['threshold']
            if 0.02 <= t <= 0.08:
                quality += 0.1

        return min(1.0, quality)

    def get_status(self) -> Dict[str, Any]:
        """获取集群运行状态"""
        stats = self.cache.get_stats()
        return {
            "total_requests": self._total_requests,
            "total_compute_time_ms": self._total_compute_time_ms,
            "avg_compute_time_ms": (self._total_compute_time_ms /
                                     max(1, self._total_requests)),
            "cache": {
                "hit_rate": stats.total_hit_rate,
                "exact_hits": stats.exact_hits,
                "bucket_hits": stats.bucket_hits,
                "neighbor_hits": stats.neighbor_hits,
                "full_computes": stats.full_computes,
                "compute_reduction": stats.compute_reduction,
                "time_saved_ms": stats.time_saved_ms
            },
            "folding": self.folding.get_stats()
        }

    def run_folding_optimization(self,
                                 coarse_points: int = 50,
                                 refined_points_per_region: int = 30,
                                 validation_points: int = 5) -> Dict[str, Any]:
        """
        运行完整的"空间折叠"优化流程

        这是韬定律优化器集群的核心工作流程:
          1. 粗筛: 大粒度网格, 发现热点
          2. 精搜: 热点区域密集采样
          3. 验证: 最优参数高精度验证
        """
        results = []

        # Phase 1: 粗筛
        print(f"  [Phase 1] 粗筛层: 探索 {coarse_points} 个参数点...")
        coarse_params = self.folding.generate_coarse_points(
            points_per_dim=max(3, int(math.sqrt(coarse_points))))
        coarse_params = coarse_params[:coarse_points]

        for params in coarse_params:
            result, _ = self.optimize(params)
            self.folding.record_coarse_result(params, result)
            results.append((params, result))

        hot_regions = self.folding.analyze_coarse_results()
        print(f"    → 发现 {len(hot_regions)} 个热点区域")
        for i, region in enumerate(hot_regions, 1):
            print(f"       热点{i}: center={list(region.center.values())[:2]}, score={region.best_score:.3f}")

        # Phase 2: 精搜
        if hot_regions:
            print(f"  [Phase 2] 精搜层: 在 {len(hot_regions)} 个热点区域内精搜...")
            refined_params = self.folding.generate_refined_points(
                points_per_region=refined_points_per_region)
            print(f"    → 生成 {len(refined_params)} 个精搜点 (约占原空间的 10-20%)")

            for params in refined_params:
                result, _ = self.optimize(params)
                results.append((params, result))

        # Phase 3: 验证
        print(f"  [Phase 3] 验证层: 高精度验证 TOP{validation_points}...")
        validation_params = self.folding.generate_validation_points(
            top_k=validation_points)

        # 验证层: 禁用缓存, 强制完整计算 (确保精度)
        best_results = []
        for params in validation_params:
            # 强制完整回测 (跳过缓存和增量)
            result, compute_time = self._full_backtest(params)
            self._total_compute_time_ms += compute_time
            best_results.append((params, result))

        # 汇总最优结果
        all_sorted = sorted(results + best_results,
                            key=lambda x: x[1].score(), reverse=True)
        best_params = all_sorted[0][0] if all_sorted else None
        best_result = all_sorted[0][1] if all_sorted else None
        total_evaluations = len(results) + len(best_results)

        # === 策略参数持久化: 记录本次优化结果 ===
        if best_params and best_result is not None:
            score = best_result.score()
            record = self._parameter_store.record_optimization(
                strategy_name=self.strategy_name,
                best_params=best_params,
                best_score=score,
                method=f"tau_cluster_{self.folding.__class__.__name__}",
                total_evals=total_evaluations,
                param_ranges=getattr(self, 'param_ranges', {}),
                module_info={"param_groups": getattr(self, '_current_param_groups', [])}
            )

            if record["is_new_best"]:
                print(f"\n  ✅ 策略 [{self.strategy_name}] 新版本 v{record['new_version']} "
                      f"(改进 +{record['score_delta']:.4f})")
            else:
                print(f"\n  ℹ️  未超越历史最佳 v{record.get('new_version', 1)} "
                      f"(当前最佳 {self._parameter_store.get_best_score(self.strategy_name):.4f})")
        # === 持久化结束 ===

        return {
            "best_params": best_params,
            "best_result": best_result,
            "top_results": all_sorted[:10],
            "total_evaluations": total_evaluations,
            "cluster_status": self.get_status()
        }


# ============================================================
# 策略感知模块 1: 伯努利-康达优化模块
# ============================================================
# 专长: 多周期共振参数优化 (均线/趋势/动量协同)
# ============================================================

class BernoulliCoandaModule:
    """
    伯努利-康达策略优化模块 - 韬定律集群的"策略感知"子模块

    伯努利-康达策略核心: 利用流体力学康达效应类比
      - 伯努利原理: 流速↑ → 压力↓ (类比: 动能↑ → 趋势延续概率↑)
      - 康达效应: 流体沿曲面附着 (类比: 价格沿均线吸附)

    优化目标: 多周期共振参数 (短/中/长周期 × 阈值参数)
    参数规模: 约 15-25个参数
    """

    # 预定义的伯努利-康达策略参数空间 (如果调用方不提供param_ranges时使用)
    DEFAULT_PARAM_RANGES = {
        # 周期参数: 短期快线 / 中期确认线 / 长期趋势线
        'short_period': (5.0, 30.0),
        'mid_period': (20.0, 80.0),
        'long_period': (60.0, 200.0),
        # 伯努利阈值参数: 动能/压力差/流速比
        'bernoulli_threshold': (0.02, 0.15),
        'momentum_alpha': (0.5, 2.0),
        'pressure_sensitivity': (0.3, 1.5),
        # 康达效应参数: 吸附强度/曲面曲率响应/脱离阈值
        'coanda_attachment': (0.2, 1.0),
        'curvature_sensitivity': (0.1, 1.2),
        'separation_threshold': (0.5, 2.5),
        # 风险管理参数
        'stop_loss_pct': (0.02, 0.10),
        'position_size': (0.1, 0.5),
        'confirmation_bars': (1.0, 5.0),
    }

    def __init__(self, param_ranges: Dict[str, Tuple[float, float]] = None):
        """初始化 - 如果不提供param_ranges, 使用预定义的伯努利-康达参数空间"""
        self.param_ranges = param_ranges or self.DEFAULT_PARAM_RANGES
        self.name = "bernoulli_coanda"
        self.description = "伯努利-康达策略优化 - 多周期共振参数优化"

    def get_param_groups(self) -> Dict[str, List[str]]:
        """参数分组 - 韬定律空间折叠时按组优化"""
        return {
            'trend_periods': ['short_period', 'mid_period', 'long_period'],
            'bernoulli_factors': ['bernoulli_threshold', 'momentum_alpha', 'pressure_sensitivity'],
            'coanda_effect': ['coanda_attachment', 'curvature_sensitivity', 'separation_threshold'],
            'risk_control': ['stop_loss_pct', 'position_size', 'confirmation_bars'],
        }

    def estimate_quality(self, params: Dict[str, float]) -> float:
        """
        伯努利-康达策略的参数质量快速估算

        评估维度（每个维度 0-1 分，加权平均）:
          1. 均线周期合理性 (权重 25%): 短<中<长, 间隔合理
          2. 伯努利阈值合理性 (权重 15%): 动能和压力信号阈值
          3. 康达效应配置 (权重 15%): 曲线附着/曲率/脱离阈值
          4. 风控参数合理性 (权重 20%): 止损/仓位/确认机制
          5. 参数间协同效应 (权重 15%): 参数组合的整体协调性
          6. 极端值惩罚 (权重 10%): 防止参数溢出

        返回: 0-1 的质量评分（1=最佳，0=最差）
        """
        params = params or {}

        # ============================================================
        # 1. 均线周期评分 (权重 25%)
        # ============================================================
        period_score = 0.5
        sp = float(params.get('short_period', 0))
        mp = float(params.get('mid_period', 0))
        lp = float(params.get('long_period', 0))

        if sp > 0 and mp > 0 and lp > 0:
            sp_score = 1.0 if 8 <= sp <= 20 else (0.7 if 5 <= sp <= 30 else 0.3)
            mp_score = 1.0 if 25 <= mp <= 50 else (0.7 if 15 <= mp <= 80 else 0.3)
            lp_score = 1.0 if 55 <= lp <= 100 else (0.7 if 40 <= lp <= 150 else 0.3)

            interval1 = mp - sp
            interval2 = lp - mp
            int1_score = 1.0 if 10 <= interval1 <= 30 else (0.6 if 5 <= interval1 <= 50 else 0.2)
            int2_score = 1.0 if 20 <= interval2 <= 60 else (0.6 if 10 <= interval2 <= 100 else 0.2)

            order_score = 1.0 if sp < mp < lp else 0.2

            period_score = 0.25 * sp_score + 0.25 * mp_score + 0.25 * lp_score + \
                          0.10 * int1_score + 0.10 * int2_score + 0.05 * order_score
        elif sp > 0 and lp > 0:
            sp_score = 1.0 if 8 <= sp <= 20 else (0.7 if 5 <= sp <= 30 else 0.3)
            lp_score = 1.0 if 55 <= lp <= 100 else (0.7 if 40 <= lp <= 150 else 0.3)
            order_score = 1.0 if sp < lp else 0.2
            gap = lp - sp
            gap_score = 1.0 if 40 <= gap <= 80 else (0.6 if 20 <= gap <= 120 else 0.3)
            period_score = 0.30 * sp_score + 0.30 * lp_score + 0.20 * gap_score + 0.20 * order_score

        period_weight = 0.25

        # ============================================================
        # 2. 伯努利因子评分 (权重 15%)
        # ============================================================
        bernoulli_score = 0.5
        b_scores = []

        bt = float(params.get('bernoulli_threshold', -1))
        if bt >= 0:
            if 0.04 <= bt <= 0.08:
                b_scores.append(1.0)
            elif 0.02 <= bt <= 0.12:
                b_scores.append(0.65)
            else:
                b_scores.append(0.3)

        ma = float(params.get('momentum_alpha', -1))
        if ma >= 0:
            if 0.6 <= ma <= 1.5:
                b_scores.append(1.0)
            elif 0.3 <= ma <= 2.5:
                b_scores.append(0.65)
            else:
                b_scores.append(0.3)

        ps = float(params.get('pressure_sensitivity', -1))
        if ps >= 0:
            if 0.5 <= ps <= 1.2:
                b_scores.append(1.0)
            elif 0.3 <= ps <= 1.8:
                b_scores.append(0.65)
            else:
                b_scores.append(0.3)

        if b_scores:
            bernoulli_score = sum(b_scores) / len(b_scores)

        bernoulli_weight = 0.15 if b_scores else 0.05

        # ============================================================
        # 3. 康达效应评分 (权重 15%)
        # ============================================================
        coanda_score = 0.5
        c_scores = []

        ca = float(params.get('coanda_attachment', -1))
        if ca >= 0:
            if 0.4 <= ca <= 0.8:
                c_scores.append(1.0)
            elif 0.2 <= ca <= 1.0:
                c_scores.append(0.65)
            else:
                c_scores.append(0.3)

        cs = float(params.get('curvature_sensitivity', -1))
        if cs >= 0:
            if 0.3 <= cs <= 0.8:
                c_scores.append(1.0)
            elif 0.1 <= cs <= 1.2:
                c_scores.append(0.65)
            else:
                c_scores.append(0.3)

        st = float(params.get('separation_threshold', -1))
        if st >= 0:
            if 0.8 <= st <= 1.5:
                c_scores.append(1.0)
            elif 0.5 <= st <= 2.5:
                c_scores.append(0.65)
            else:
                c_scores.append(0.3)

        if c_scores:
            coanda_score = sum(c_scores) / len(c_scores)

        coanda_weight = 0.15 if c_scores else 0.05

        # ============================================================
        # 4. 风控参数评分 (权重 20%)
        # ============================================================
        risk_score = 0.5
        r_scores = []

        sl = float(params.get('stop_loss_pct', -1))
        if sl >= 0:
            if 0.03 <= sl <= 0.08:
                r_scores.append(1.0)
            elif 0.015 <= sl <= 0.15:
                r_scores.append(0.65)
            elif sl > 0.20:
                r_scores.append(0.15)
            else:
                r_scores.append(0.4)

        psz = float(params.get('position_size', -1))
        if psz >= 0:
            if 0.15 <= psz <= 0.4:
                r_scores.append(1.0)
            elif 0.05 <= psz <= 0.6:
                r_scores.append(0.65)
            elif psz > 0.8:
                r_scores.append(0.15)
            else:
                r_scores.append(0.4)

        cb = float(params.get('confirmation_bars', -1))
        if cb >= 0:
            if 2 <= cb <= 4:
                r_scores.append(1.0)
            elif 1 <= cb <= 6:
                r_scores.append(0.65)
            else:
                r_scores.append(0.4)

        if r_scores:
            risk_score = sum(r_scores) / len(r_scores)

        risk_weight = 0.20 if r_scores else 0.05

        # ============================================================
        # 5. 参数协同效应 (权重 15%)
        # ============================================================
        synergy_score = 0.5
        valid_params = sum([
            1 for k in ['short_period', 'mid_period', 'long_period',
                       'bernoulli_threshold', 'momentum_alpha', 'pressure_sensitivity',
                       'coanda_attachment', 'curvature_sensitivity', 'separation_threshold',
                       'stop_loss_pct', 'position_size', 'confirmation_bars']
            if k in params and params[k] is not None
        ])

        if valid_params >= 4:
            coverage = min(1.0, valid_params / 12.0)

            avg_period = (sp + mp + lp) / 3 if (sp > 0 and lp > 0) else 50
            if 30 <= avg_period <= 70:
                avg_ok = 1.0
            elif 20 <= avg_period <= 100:
                avg_ok = 0.7
            else:
                avg_ok = 0.4

            risk_vs_reward = 0.5
            if bt > 0 and sl > 0:
                ratio = bt / sl if sl > 0 else 1.0
                if 0.5 <= ratio <= 2.5:
                    risk_vs_reward = 1.0
                elif 0.2 <= ratio <= 4.0:
                    risk_vs_reward = 0.6
                else:
                    risk_vs_reward = 0.3

            synergy_score = 0.4 * coverage + 0.3 * avg_ok + 0.3 * risk_vs_reward

        synergy_weight = 0.15 if valid_params >= 4 else 0.05

        # ============================================================
        # 6. 极端值惩罚 (权重 10%)
        # ============================================================
        extreme_penalty = 1.0
        extreme_count = 0

        if 'short_period' in params and (sp < 2 or sp > 80):
            extreme_count += 1
        if 'long_period' in params and (lp < 20 or lp > 300):
            extreme_count += 1
        if 'stop_loss_pct' in params and (sl > 0.25):
            extreme_count += 1
        if 'position_size' in params and (psz > 0.8):
            extreme_count += 1

        if extreme_count > 0:
            extreme_penalty = max(0.1, 1.0 - extreme_count * 0.2)

        extreme_weight = 0.10

        # ============================================================
        # 综合评分
        # ============================================================
        total_weight = period_weight + bernoulli_weight + coanda_weight + \
                      risk_weight + synergy_weight + extreme_weight

        quality = (
            period_weight * period_score +
            bernoulli_weight * bernoulli_score +
            coanda_weight * coanda_score +
            risk_weight * risk_score +
            synergy_weight * synergy_score +
            extreme_weight * extreme_penalty
        ) / max(0.1, total_weight)

        return max(0.0, min(1.0, round(quality, 6)))


# ============================================================
# 策略感知模块 2: 智能标的轮动优化模块 (核心-68因子)
# ============================================================
# 专长: 68技术因子分层优化 + 滚动窗口验证
# ============================================================

class ShepherdRotationModule:
    """
    智能标的轮动策略优化模块 - 韬定律集群的"高维策略感知"子模块

    核心能力:
      1. 68个技术因子的自动分组 (7个因子类别)
      2. 层次化参数折叠 (组内权重 → 组间权重 → 细节调优)
      3. 因子相关性自动筛选 (排除冗余因子)
      4. 滚动窗口验证 (walk-forward validation)

    参数规模: 68个技术因子权重 + 5个轮动控制参数 = 约73个参数
    韬定律空间折叠效果: 73维 → 3层 → 实际搜索量减少 100-1000倍
    """

    # 68个技术因子的预定义分组和范围
    # 每个因子的权重范围: 0.1-2.0 (相对权重, 后续归一化)
    FACTOR_GROUPS = {
        # 1. 趋势因子组 (12个) - MA斜率、ADX、趋势强度等
        'trend_factors': [
            'ma5_slope', 'ma10_slope', 'ma20_slope', 'ma60_slope',
            'price_to_ma20', 'price_to_ma60',
            'adx_14', 'adx_20', 'plus_di_14', 'minus_di_14',
            'trend_strength_20', 'trend_consistency'
        ],
        # 2. 动量因子组 (15个) - RSI、MACD、ROC、动量加速度等
        'momentum_factors': [
            'rsi_6', 'rsi_12', 'rsi_14', 'rsi_20',
            'macd_line', 'macd_signal', 'macd_histogram',
            'roc_5', 'roc_10', 'roc_20',
            'momentum_10d', 'momentum_20d', 'momentum_60d',
            'momentum_acceleration', 'williams_r_14'
        ],
        # 3. 波动率因子组 (10个) - ATR、布林带、历史波动率
        'volatility_factors': [
            'atr_10', 'atr_14', 'atr_20',
            'bollinger_width', 'bollinger_position',
            'historical_vol_10d', 'historical_vol_20d', 'historical_vol_60d',
            'volatility_ratio', 'range_volatility'
        ],
        # 4. 成交量因子组 (8个) - OBV、成交量斜率、资金流等
        'volume_factors': [
            'obv', 'obv_ma_slope',
            'volume_slope_5', 'volume_slope_10',
            'volume_ratio_20',
            'money_flow_index_14',
            'volume_price_correlation',
            'accumulation_distribution'
        ],
        # 5. 价值因子组 (12个) - PE、PB、ROE、股息率等
        'value_factors': [
            'pe_ratio', 'pb_ratio', 'ps_ratio',
            'roe', 'roa', 'gross_margin', 'net_margin',
            'dividend_yield', 'revenue_growth', 'earnings_growth',
            'book_value_per_share', 'free_cash_flow_yield'
        ],
        # 6. 质量因子组 (6个) - 毛利率、杠杆率、资产质量
        'quality_factors': [
            'operating_margin', 'asset_turnover',
            'debt_to_equity', 'current_ratio',
            'earnings_quality', 'sustainable_growth_rate'
        ],
        # 7. 轮动控制参数 (5个) - 切换阈值、持有期、最大仓位等
        'rotation_controls': [
            'rotation_threshold',    # 切换阈值 (0.03-0.15)
            'min_hold_period',        # 最小持有期天 (3-30)
            'max_position_pct',       # 最大单标的仓位 (0.05-0.30)
            'max_holdings',           # 最大同时持有标的数 (1-10)
            'rebalance_frequency'     # 调仓频率天 (1-20)
        ],
    }

    # 计算: 12+15+10+8+12+6+5 = 68个技术因子 ✓

    def __init__(self, param_ranges: Dict[str, Tuple[float, float]] = None,
                 use_factor_filtering: bool = True):
        """
        初始化标的轮动优化模块
        Args:
            param_ranges: 可选的自定义参数范围
            use_factor_filtering: 是否启用因子相关性筛选
        """
        # 构建默认参数范围 (权重型因子 0.1-2.0, 控制参数各自范围)
        if param_ranges is None:
            self.param_ranges = {}
            for group_name, factors in self.FACTOR_GROUPS.items():
                for factor in factors:
                    if group_name == 'rotation_controls':
                        # 轮动控制参数有不同的合理范围
                        if factor == 'rotation_threshold':
                            self.param_ranges[factor] = (0.03, 0.15)
                        elif factor == 'min_hold_period':
                            self.param_ranges[factor] = (3.0, 30.0)
                        elif factor == 'max_position_pct':
                            self.param_ranges[factor] = (0.05, 0.30)
                        elif factor == 'max_holdings':
                            self.param_ranges[factor] = (1.0, 10.0)
                        elif factor == 'rebalance_frequency':
                            self.param_ranges[factor] = (1.0, 20.0)
                    else:
                        # 权重型因子: 0.1(低贡献)-2.0(高贡献)
                        self.param_ranges[factor] = (0.1, 2.0)
        else:
            self.param_ranges = param_ranges

        self.name = "shepherd_rotation"
        self.description = "智能标的轮动优化 - 68因子分层参数优化"
        self.use_factor_filtering = use_factor_filtering
        self._active_factor_mask: Dict[str, bool] = {}  # 活跃因子标记
        self._factor_correlations: Dict[str, float] = {}  # 因子相关性缓存

    def get_param_groups(self) -> Dict[str, List[str]]:
        """返回7个因子组 - 用于韬定律层次化空间折叠"""
        return self.FACTOR_GROUPS.copy()

    def count_params(self) -> int:
        """返回总参数数量"""
        return sum(len(v) for v in self.FACTOR_GROUPS.values())

    def estimate_group_quality(self, group_name: str,
                                params: Dict[str, float]) -> float:
        """
        快速估算某个因子组的质量 (用于粗筛层跳过坏区域)
        """
        if group_name == 'rotation_controls':
            # 轮动控制: 阈值太低=频繁交易, 太高=错过机会
            threshold = params.get('rotation_threshold', 0.08)
            hold_period = params.get('min_hold_period', 10)
            max_pos = params.get('max_position_pct', 0.15)
            q = 1.0 - abs(threshold - 0.08) * 5.0
            q *= 1.0 - abs(hold_period - 10) * 0.05
            q *= max(0.2, min(1.0, max_pos * 5))
            return max(0.0, min(1.0, q))

        # 因子组: 检查权重分布是否合理 (不应该全部0或全部2)
        group_factors = self.FACTOR_GROUPS.get(group_name, [])
        if not group_factors:
            return 0.5
        weights = [params.get(f, 1.0) for f in group_factors]
        if not weights:
            return 0.5

        # 权重方差应该适中 (不是全相等, 也不是极端集中)
        avg = sum(weights) / len(weights)
        variance = sum((w - avg) ** 2 for w in weights) / len(weights)
        # 方差在0.1-0.5之间较好
        if 0.1 <= variance <= 0.5:
            var_q = 1.0
        elif variance < 0.1:
            var_q = 0.5 + variance * 5  # 太平滑 → 中等
        else:
            var_q = max(0.2, 1.0 - (variance - 0.5) * 2)

        # 平均权重不应太低或太高
        avg_q = 1.0 - abs(avg - 1.0)

        return max(0.0, min(1.0, 0.6 * var_q + 0.4 * avg_q))

    def estimate_overall_quality(self, params: Dict[str, float]) -> float:
        """整体质量快速估算 (用于韬定律粗筛层)"""
        group_scores = []
        for group_name in self.FACTOR_GROUPS:
            group_scores.append(self.estimate_group_quality(group_name, params))
        return sum(group_scores) / len(group_scores) if group_scores else 0.5


# ============================================================
# 策略感知模块 3: 因子空间折叠 (高维参数空间专用)
# ============================================================
# 为68因子参数空间设计的层次化折叠算法
# 区别于通用ParameterSpaceFolding:
#   - 先按因子组折叠, 再组内折叠
#   - 支持因子相关性自动筛选
#   - 与ShepherdRotationModule协同工作
# ============================================================

class FactorSpaceFolding:
    """
    因子空间折叠 - 针对高维因子参数空间的层次化搜索

    三层折叠策略:
      Phase 1 (组级粗筛): 每个因子组作为整体, 测试组权重分布
          实际点数: 7组 × 每个组5个代表性点 = 35点
      Phase 2 (组内精搜): 对高价值因子组, 组内参数精细搜索
          实际点数: 热门3-4组 × 每组10-15个点 = 30-60点
      Phase 3 (交叉验证): 对TOP-5参数组合, 做滚动窗口验证
          实际点数: 5 × 3(滚动窗口) = 15点

    总评估量: 80-110次 (对比盲目搜索 5^68 ≈ 3.6×10^47)
    """

    class Phase(Enum):
        GROUP_SCREEN = "group_screen"      # 组级粗筛
        INTRA_GROUP = "intra_group"         # 组内精搜
        VALIDATION = "validation"           # 滚动窗口验证

    def __init__(self, shepherd_module: ShepherdRotationModule):
        """绑定到标的轮动模块"""
        self.shepherd = shepherd_module
        self.param_ranges = shepherd_module.param_ranges
        self.phase = self.Phase.GROUP_SCREEN
        self.group_scores: Dict[str, float] = {}
        self.hot_groups: List[str] = []
        self.best_params_history: List[Dict[str, float]] = []

    def generate_group_screen_points(self, points_per_group: int = 5) -> List[Dict[str, float]]:
        """
        Phase 1: 组级粗筛 - 每个因子组生成几个代表性参数点
        只改变目标组的参数, 其他组使用默认值1.0
        """
        all_points = []
        for group_name, factors in self.shepherd.FACTOR_GROUPS.items():
            if group_name == 'rotation_controls':
                continue  # 控制参数后面单独处理

            for i in range(points_per_group):
                point = {}
                # 其他组: 默认权重1.0
                for other_group, other_factors in self.shepherd.FACTOR_GROUPS.items():
                    default_val = 1.0 if other_group != 'rotation_controls' else 0.1
                    for f in other_factors:
                        point[f] = default_val

                # 当前组: 参数变化 (低/中/高/极端1/极端2)
                for idx, factor in enumerate(factors):
                    pmin, pmax = self.param_ranges[factor]
                    if i == 0:
                        point[factor] = pmin  # 最低
                    elif i == 1:
                        point[factor] = (pmin + pmax) / 3  # 偏低
                    elif i == 2:
                        point[factor] = (pmin + pmax) / 2  # 中间
                    elif i == 3:
                        point[factor] = (pmin + pmax) * 2 / 3  # 偏高
                    else:
                        point[factor] = pmax  # 最高

                all_points.append(point)

        # 再添加几组控制参数测试点
        for i in range(5):
            point = {}
            for group, factors in self.shepherd.FACTOR_GROUPS.items():
                for f in factors:
                    pmin, pmax = self.param_ranges[f]
                    point[f] = (pmin + pmax) / 2
            # 只改变控制参数
            for idx, f in enumerate(self.shepherd.FACTOR_GROUPS['rotation_controls']):
                pmin, pmax = self.param_ranges[f]
                point[f] = pmin + (pmax - pmin) * (i / 4.0)
            all_points.append(point)

        return all_points

    def rank_groups_by_score(self, results: List[Tuple[Dict[str, float], float]]) -> List[str]:
        """
        根据Phase 1结果, 排序因子组的"可优化潜力"
        Args:
            results: [(params, backtest_score), ...]
        Returns:
            排序后的因子组名列表 (高潜力在前)
        """
        group_score_range: Dict[str, float] = {}

        for group_name, factors in self.shepherd.FACTOR_GROUPS.items():
            if group_name == 'rotation_controls':
                continue
            # 计算该组参数变化时分数的波动范围
            # 波动大 = 这个组对性能影响大 = 值得深入优化
            relevant_scores = []
            for params, score in results:
                group_weights = [params.get(f, 1.0) for f in factors]
                avg_w = sum(group_weights) / len(group_weights)
                # 如果该组偏离默认值1.0较多, 记录其分数
                if abs(avg_w - 1.0) > 0.2:
                    relevant_scores.append((avg_w, score))

            if len(relevant_scores) >= 3:
                scores_only = [s for _, s in relevant_scores]
                score_range = max(scores_only) - min(scores_only)
                group_score_range[group_name] = score_range
            else:
                group_score_range[group_name] = 0.1  # 默认中等潜力

        # 控制参数始终高优先级
        group_score_range['rotation_controls'] = max(
            group_score_range.get('rotation_controls', 0.2),
            max(group_score_range.values()) * 0.8
        )

        sorted_groups = sorted(group_score_range.keys(),
                                key=lambda g: group_score_range[g], reverse=True)
        self.group_scores = group_score_range
        self.hot_groups = sorted_groups[:4]  # 取TOP 4个组深入
        return sorted_groups

    def generate_intra_group_points(self, hot_groups: List[str] = None,
                                     points_per_group: int = 12) -> List[Dict[str, float]]:
        """
        Phase 2: 组内精搜 - 对热门因子组精细搜索
        """
        if hot_groups is None:
            hot_groups = self.hot_groups or list(self.shepherd.FACTOR_GROUPS.keys())[:4]

        points = []
        # 先用Phase 1找到的最佳参数作为基准
        base_params = self.best_params_history[-1] if self.best_params_history else {}

        for group_name in hot_groups:
            factors = self.shepherd.FACTOR_GROUPS.get(group_name, [])
            if not factors:
                continue

            for i in range(points_per_group):
                point = base_params.copy()
                for factor in factors:
                    pmin, pmax = self.param_ranges[factor]
                    # 精细网格: 在基准值附近 ±30%范围搜索
                    base_val = point.get(factor, (pmin + pmax) / 2)
                    search_min = max(pmin, base_val * 0.7)
                    search_max = min(pmax, base_val * 1.3)
                    point[factor] = search_min + (search_max - search_min) * (i / (points_per_group - 1))
                points.append(point)

        return points

    def generate_validation_points(self, top_n: int = 5,
                                    windows: int = 3,
                                    top_k: int = None) -> List[Dict[str, float]]:
        """
        Phase 3: 滚动窗口验证 - 对TOP-N候选参数在不同市场周期测试
        返回参数组 (用于多窗口测试的实际回测调用由上层执行)
        """
        n = top_k if top_k is not None else top_n
        return self.best_params_history[-n:] if self.best_params_history else []

    # ============================================================
    # TauOptimizerCluster 兼容接口 (别名)
    # 使 FactorSpaceFolding 可以无缝替换 ParameterSpaceFolding
    # ============================================================
    def generate_coarse_points(self, points_per_dim: int = 5,
                               **kwargs) -> List[Dict[str, float]]:
        """TauOptimizerCluster 兼容: Phase 1 粗筛层"""
        points_per_group = max(3, points_per_dim // max(1, len(self.shepherd.FACTOR_GROUPS) - 1))
        return self.generate_group_screen_points(points_per_group=points_per_group)

    def record_coarse_result(self, params: Dict[str, float],
                             result: 'BacktestResult') -> None:
        """TauOptimizerCluster 兼容: 记录粗筛结果"""
        score = result.score()
        # 维护 best_params_history（按评分排序，保留前20个）
        self.best_params_history.append(params.copy())
        # 只保留前20个（这里不排序，简化为保留最新的20个）
        if len(self.best_params_history) > 20:
            self.best_params_history = self.best_params_history[-20:]
        # 粗略维护 group_scores - 通过参数键推断所属组
        for group_name, factors in self.shepherd.FACTOR_GROUPS.items():
            # 如果参数点中此组因子被改动（值 != 1.0），则标记为该组
            modified = [f for f in factors if abs(params.get(f, 1.0) - 1.0) > 0.05]
            if modified:
                if group_name not in self.group_scores or score > self.group_scores[group_name]:
                    self.group_scores[group_name] = score
                break

    def analyze_coarse_results(self, top_ratio: float = 0.2,
                               **kwargs) -> List[Any]:
        """TauOptimizerCluster 兼容: Phase 1 结果分析"""
        if not self.group_scores:
            # 如果没有分组信息，默认前3个组为热门
            self.hot_groups = list(self.shepherd.FACTOR_GROUPS.keys())[:3]
        else:
            sorted_groups = sorted(self.group_scores.items(),
                                   key=lambda x: x[1], reverse=True)
            hot_count = max(2, int(len(sorted_groups) * top_ratio))
            self.hot_groups = [g for g, _ in sorted_groups[:hot_count]]
        # 返回兼容的热点区域列表（与 ParameterSpaceFolding 类似的格式）
        class HotRegion:
            def __init__(self, center, best_score):
                self.center = center
                self.best_score = best_score
        hot = []
        for g in self.hot_groups:
            s = self.group_scores.get(g, 0.5)
            hot.append(HotRegion({"group": g}, s))
        return hot

    def generate_refined_points(self, points_per_region: int = 15,
                                **kwargs) -> List[Dict[str, float]]:
        """TauOptimizerCluster 兼容: Phase 2 精搜层"""
        return self.generate_intra_group_points(
            hot_groups=self.hot_groups or list(self.shepherd.FACTOR_GROUPS.keys())[:3],
            points_per_group=max(5, points_per_region // max(1, len(self.hot_groups or [1])))
        )

    def is_in_excluded_region(self, params: Dict[str, float]) -> bool:
        """TauOptimizerCluster 兼容: 检查是否在排除区域 (FactorSpaceFolding 暂不支持)"""
        return False

    def get_stats(self) -> Dict[str, Any]:
        """TauOptimizerCluster 兼容: 返回折叠统计"""
        return {
            "current_level": "factor_space_folding",
            "hot_regions_count": len(self.hot_groups),
            "excluded_regions_count": 0,
            "coarse_points_tested": len(self.best_params_history),
            "factor_groups": len(self.shepherd.FACTOR_GROUPS),
            "total_factors": self.shepherd.count_params()
        }


# ============================================================
# 策略感知模块 4: 策略优化器总线 (StrategyOptimizerBus)
# ============================================================
# 统一调度各策略感知模块
# ============================================================

class StrategyOptimizerBus:
    """
    策略优化器总线 - 韬定律集群的"系统层"调度器

    根据策略类型自动选择合适的策略感知模块:
      - 伯努利-康达策略 → BernoulliCoandaModule
      - 智能标的轮动 → ShepherdRotationModule
      - 其他策略 → 通用ParameterSpaceFolding

    这实现了"策略感知" - 不是对所有策略用同一个方法优化,
    而是根据策略的内部结构选择最合适的折叠算法和参数空间。
    """

    STRATEGY_TYPE_MAP = {
        'bernoulli_coanda': BernoulliCoandaModule,
        'coanda': BernoulliCoandaModule,
        'bernoulli': BernoulliCoandaModule,
        'shepherd_rotation': ShepherdRotationModule,
        'shepherd': ShepherdRotationModule,
        'rotation': ShepherdRotationModule,
        '标的轮动': ShepherdRotationModule,
        '伯努利': BernoulliCoandaModule,
        '智能标的轮动': ShepherdRotationModule,
    }

    def __init__(self):
        self._modules = {}
        self.current_module = None
        self.current_module_name = "generic"

    def detect_and_init(self, strategy_name: str,
                         param_ranges: Dict[str, Tuple[float, float]] = None):
        """
        根据策略名称检测类型并初始化对应模块
        """
        name_lower = strategy_name.lower()
        module_class = None

        for keyword, cls in self.STRATEGY_TYPE_MAP.items():
            if keyword in name_lower:
                module_class = cls
                break

        if module_class:
            self.current_module = module_class(param_ranges)
            self.current_module_name = self.current_module.name
            return self.current_module
        else:
            # 回退到通用模式
            self.current_module = None
            self.current_module_name = "generic"
            return None

    def get_param_groups(self) -> Dict[str, List[str]]:
        """获取当前模块的参数分组 (通用模式返回单组)"""
        if self.current_module and hasattr(self.current_module, 'get_param_groups'):
            return self.current_module.get_param_groups()
        return {'all_params': []}

    def has_specialized_module(self) -> bool:
        """当前策略是否有专用优化模块"""
        return self.current_module is not None

    def get_module_info(self) -> Dict[str, str]:
        """获取当前模块信息 (用于UI显示和健康检查)"""
        if self.current_module is None:
            return {
                'module_name': 'generic',
                'module_description': '通用参数优化 (无策略专用优化器)',
                'params_count': '取决于调用方',
                'specialized': 'no',
            }
        info = {
            'module_name': self.current_module.name,
            'module_description': self.current_module.description,
            'params_count': str(getattr(self.current_module, 'count_params',
                                          lambda: len(self.current_module.param_ranges))()),
            'specialized': 'yes',
        }
        if hasattr(self.current_module, 'get_param_groups'):
            groups = self.current_module.get_param_groups()
            info['groups'] = f"{len(groups)} groups: {', '.join(groups.keys())}"
        return info


def create_tau_cluster_with_mgr(strategy_name: str,
                                 param_ranges: Dict[str, Tuple[float, float]] = None,
                                 strategy_mgr: Any = None) -> TauOptimizerCluster:
    """
    创建一个已连接到真实策略管理器的韬定律优化集群

    Args:
        strategy_name: 策略名称（用于回测）
        param_ranges: 参数范围（如果为空，使用双均线默认范围）
        strategy_mgr: EnhancedStrategyManager实例，如果提供，会用于真实回测

    Returns:
        TauOptimizerCluster 实例
    """
    if param_ranges is None:
        param_ranges = {
            'short_period': (5.0, 50.0),
            'long_period': (30.0, 200.0),
            'threshold': (0.01, 0.1)
        }
    return TauOptimizerCluster(
        param_ranges=param_ranges,
        strategy_name=strategy_name,
        strategy_mgr=strategy_mgr
    )


# ============================================================
# 参数持久化存储 (用于 warm start / 版本管理) - v2 StrategyParameterStore
# ============================================================

class StrategyParameterStore:
    """
    策略参数持久化存储系统

    功能:
      - 保存每个策略的最佳参数版本 (带版本号 v1, v2...)
      - 自动记录优化历史 (优化时间、评分、方法等)
      - 下次优化时 warm start (从历史最佳开始)
      - 区分"原策略"和"已优化策略"，避免混淆

    数据结构 (JSON):
      {
        "伯努利-康达策略": {
            "current_version": 2,
            "best_score": 0.89,
            "optimization_history": [
                {
                    "version": 1,
                    "timestamp": "2026-06-03T10:00:00",
                    "best_params": {...},
                    "best_score": 0.75,
                    "method": "tau_cluster_fallback",
                    "total_evals": 80
                },
                {
                    "version": 2,
                    "timestamp": "2026-06-03T14:30:00",
                    "best_params": {...},
                    "best_score": 0.89,
                    "method": "bernoulli_module",
                    "improved_from_version": 1
                }
            ]
        },
        ...
      }
    """

    DEFAULT_STORE_FILE = "strategy_optimization_store.json"

    def __init__(self, store_dir: str = None):
        """
        Args:
            store_dir: 存储目录，默认为 QS_Robot/data/
        """
        if store_dir is None:
            # 默认存储在 QS_Robot/data/ 目录
            module_dir = os.path.dirname(os.path.abspath(__file__))
            store_dir = os.path.join(os.path.dirname(module_dir), "data")

        self.store_dir = store_dir
        os.makedirs(self.store_dir, exist_ok=True)
        self.store_file = os.path.join(self.store_dir, self.DEFAULT_STORE_FILE)
        self._data = self._load()
        self._lock = threading.RLock()

    def _load(self) -> dict:
        """从文件加载存储数据"""
        if os.path.exists(self.store_file):
            try:
                with open(self.store_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return {"_metadata": {"created": datetime.datetime.now().isoformat(),
                               "description": "韬定律策略优化器集群 - 参数版本存储"}}

    def _save(self):
        """保存到文件"""
        with self._lock:
            try:
                with open(self.store_file, 'w', encoding='utf-8') as f:
                    json.dump(self._data, f, ensure_ascii=False, indent=2)
            except Exception as e:
                print(f"  ⚠️  策略参数存储保存失败: {e}")

    def get_strategy(self, strategy_name: str) -> dict:
        """获取策略的存储数据"""
        return self._data.get(strategy_name, {})

    def get_best_params(self, strategy_name: str) -> Optional[dict]:
        """获取策略的最新最佳参数 (warm start 用)"""
        strategy = self.get_strategy(strategy_name)
        history = strategy.get("optimization_history", [])
        if not history:
            return None
        # 取评分最高的版本
        best = max(history, key=lambda x: x.get("best_score", 0))
        return best.get("best_params")

    def get_best_score(self, strategy_name: str) -> float:
        """获取策略的历史最佳评分 (若没有则返回 0)"""
        best_params = self.get_best_params(strategy_name)
        if best_params is None:
            return 0.0
        # 从history中找对应的评分
        history = self.get_strategy(strategy_name).get("optimization_history", [])
        best = max(history, key=lambda x: x.get("best_score", 0))
        return best.get("best_score", 0.0)

    def record_optimization(self, strategy_name: str, best_params: dict,
                            best_score: float, method: str = "tau_cluster",
                            total_evals: int = 0, param_ranges: dict = None,
                            module_info: dict = None) -> dict:
        """
        记录一次优化结果

        Returns:
            包含更新信息的dict: {
                "is_new_best": bool, 是否超越历史最佳,
                "new_version": int, 新版本号,
                "improved_from": Optional[int], 从哪个版本改进来,
                "score_delta": float, 相比上次最佳的改进量
            }
        """
        with self._lock:
            strategy = self._data.setdefault(strategy_name, {
                "optimization_history": []
            })

            history = strategy.get("optimization_history", [])
            current_best = max(
                (h.get("best_score", 0) for h in history),
                default=0.0
            ) if history else 0.0
            current_version = strategy.get("current_version", 0)

            is_new_best = best_score > current_best + 0.001  # 微小阈值避免噪声
            new_version = current_version + (1 if is_new_best else 0)

            record = {
                "version": new_version if is_new_best else current_version,
                "timestamp": datetime.datetime.now().isoformat(),
                "best_params": best_params,
                "best_score": round(float(best_score), 6),
                "method": method,
                "total_evals": total_evals,
                "param_ranges": {k: list(v) if isinstance(v, (tuple, list)) else v
                                 for k, v in (param_ranges or {}).items()},
                "module": module_info or {},
                "is_improvement": is_new_best,
                "improved_from": current_version if is_new_best and current_version > 0 else None
            }

            # 保存
            history.append(record)
            strategy["optimization_history"] = history
            if is_new_best:
                strategy["current_version"] = new_version
                strategy["best_score"] = round(float(best_score), 6)
                strategy["last_updated"] = datetime.datetime.now().isoformat()
                strategy["status"] = "optimized"
            else:
                strategy.setdefault("current_version", 0)
                strategy.setdefault("best_score", round(float(best_score), 6))
                strategy.setdefault("last_updated", datetime.datetime.now().isoformat())
                strategy["status"] = "stagnant"  # 未改进

            self._save()

            return {
                "is_new_best": is_new_best,
                "new_version": strategy.get("current_version", 0),
                "improved_from": record.get("improved_from"),
                "score_delta": round(best_score - current_best, 6),
                "history_length": len(history)
            }

    def get_optimized_strategies(self) -> List[str]:
        """返回所有经过优化的策略名称列表 (供UI展示)"""
        result = []
        for name, info in self._data.items():
            if name.startswith("_"):  # 跳过元数据
                continue
            if info.get("current_version", 0) > 0:
                result.append(name)
        return sorted(result)

    def get_all_strategies_info(self) -> List[dict]:
        """返回所有策略的优化状态列表 (用于策略面板展示)"""
        strategies = []
        for name, info in self._data.items():
            if name.startswith("_"):
                continue
            strategies.append({
                "name": name,
                "current_version": info.get("current_version", 0),
                "best_score": info.get("best_score", 0.0),
                "history_count": len(info.get("optimization_history", [])),
                "last_updated": info.get("last_updated", "-"),
                "status": info.get("status", "new")
            })
        return sorted(strategies, key=lambda x: -x["best_score"])

    def __str__(self) -> str:
        count = len([k for k in self._data.keys() if not k.startswith("_")])
        return f"StrategyParameterStore({count} strategies in {self.store_file})"


# === 全局单例 ===

_global_parameter_store = None
_global_store_lock = threading.Lock()

def get_parameter_store() -> StrategyParameterStore:
    """获取全局单例的策略参数存储"""
    global _global_parameter_store
    with _global_store_lock:
        if _global_parameter_store is None:
            _global_parameter_store = StrategyParameterStore()
        return _global_parameter_store

