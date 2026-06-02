#!/usr/bin/env python3
"""
韬定律策略优化器集群 - 回测缓存层验证
==========================================

目标: 验证回测缓存对优化效率的提升效果

测试场景:
- 模拟网格搜索优化: 1000组参数
- 场景A: 无缓存, 每次都完整计算
- 场景B: 有缓存, 重复参数直接复用

预期结果: 场景B的缓存命中率越高, 加速效果越明显
"""

import hashlib
import json
import time
import random
from dataclasses import dataclass, field
from typing import Dict, Optional, Any, Tuple
from datetime import datetime
from collections import OrderedDict
import threading


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
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class CacheEntry:
    """缓存条目"""
    result: BacktestResult
    hit_count: int = 0
    created_at: float = field(default_factory=time.time)


@dataclass
class CacheStats:
    """缓存统计"""
    total_requests: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    total_time_saved_ms: float = 0.0

    @property
    def hit_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.cache_hits / self.total_requests


# ============================================================
# 回测缓存层 (器件层核心)
# ============================================================

class BacktestCache:
    """
    回测结果缓存层 - τ定律"器件层"实现

    核心思想: 相同参数组合的回测结果应被缓存复用，
    而非每次都重新计算。

    缓存策略:
    - LRU淘汰 (最近最少使用)
    - 命中率阈值保护 (命中率 > 10% 保留)
    - 线程安全
    """

    def __init__(self, max_size: int = 10000, min_hit_rate: float = 0.1):
        """
        Args:
            max_size: 最大缓存条目数
            min_hit_rate: 最低命中率阈值, 低于此值的条目会被淘汰
        """
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = threading.RLock()
        self.max_size = max_size
        self.min_hit_rate = min_hit_rate
        self._stats = CacheStats()

    def make_cache_key(self, strategy_name: str, params: Dict[str, Any],
                       start_date: str = "2024-01-01",
                       end_date: str = "2024-12-31") -> str:
        """生成缓存键"""
        # 1. 参数标准化 (浮点数精度统一)
        normalized = {}
        for k, v in sorted(params.items()):
            if isinstance(v, float):
                normalized[k] = round(v, 6)
            else:
                normalized[k] = v

        # 2. 组合特征
        features = [
            strategy_name,
            start_date,
            end_date,
            json.dumps(normalized, sort_keys=True)
        ]
        content = "|".join(features)

        # 3. 计算哈希
        return hashlib.sha256(content.encode('utf-8')).hexdigest()[:32]

    def get(self, strategy_name: str, params: Dict[str, Any]) -> Optional[BacktestResult]:
        """获取缓存的回测结果"""
        key = self.make_cache_key(strategy_name, params)

        with self._lock:
            if key in self._cache:
                entry = self._cache[key]
                # 更新LRU顺序
                self._cache.move_to_end(key)
                # 增加命中计数
                entry.hit_count += 1
                self._stats.cache_hits += 1
                self._stats.total_requests += 1
                return entry.result

            self._stats.cache_misses += 1
            self._stats.total_requests += 1
            return None

    def put(self, strategy_name: str, params: Dict[str, Any],
            result: BacktestResult) -> None:
        """缓存回测结果"""
        key = self.make_cache_key(strategy_name, params)

        with self._lock:
            # 已存在则更新
            if key in self._cache:
                self._cache[key] = CacheEntry(result=result)
                self._cache.move_to_end(key)
                return

            # 淘汰低命中条目 (如果缓存满)
            if len(self._cache) >= self.max_size:
                self._evict_low_hit_rate()

            # 新增条目
            self._cache[key] = CacheEntry(result=result)
            self._cache.move_to_end(key)

    def _evict_low_hit_rate(self) -> None:
        """淘汰命中率低于阈值的旧条目"""
        to_remove = []
        for key, entry in self._cache.items():
            # 计算命中率 (基于当前缓存大小)
            if self._stats.total_requests > 0:
                hit_rate = entry.hit_count / max(1, self._stats.total_requests)
                if hit_rate < self.min_hit_rate:
                    to_remove.append(key)

        # 淘汰最旧的条目直到有空位
        if to_remove:
            for key in to_remove[:min(len(to_remove), len(self._cache) // 4)]:
                del self._cache[key]

        # 如果还不够空间, 淘汰最旧的25%
        while len(self._cache) >= self.max_size:
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]

    def get_stats(self) -> CacheStats:
        """返回缓存统计"""
        with self._lock:
            return CacheStats(
                total_requests=self._stats.total_requests,
                cache_hits=self._stats.cache_hits,
                cache_misses=self._stats.cache_misses,
                total_time_saved_ms=self._stats.total_time_saved_ms
            )

    def clear(self) -> None:
        """清空缓存"""
        with self._lock:
            self._cache.clear()
            self._stats = CacheStats()


# ============================================================
# 模拟回测引擎 (模拟Aurora API调用)
# ============================================================

class MockBacktestEngine:
    """
    模拟回测引擎 - 模拟真实Aurora回测API的响应时间

    真实回测耗时组成:
    - 数据加载: ~50ms
    - 指标计算: ~100-200ms
    - 信号生成: ~20-50ms
    - 结果评估: ~10-30ms
    总计: ~200-400ms
    """

    def __init__(self, use_cache: bool = True, cache: Optional[BacktestCache] = None):
        self.use_cache = use_cache
        self.cache = cache or BacktestCache()
        self.call_count = 0

    def run_backtest(self, strategy_name: str,
                     params: Dict[str, Any]) -> Tuple[BacktestResult, float]:
        """
        执行回测

        Returns:
            (回测结果, 本次计算耗时ms)
        """
        start_time = time.time()
        time.sleep(0.005)  # 基础耗时 5ms (模拟网络开销)

        # 检查缓存
        if self.use_cache:
            cached = self.cache.get(strategy_name, params)
            if cached:
                elapsed_ms = (time.time() - start_time) * 1000
                self.cache._stats.total_time_saved_ms += 200  # 估算节省的时间
                return cached, elapsed_ms

        # 模拟真实回测计算 (随机150-350ms)
        compute_time = random.uniform(0.15, 0.35)
        time.sleep(compute_time)
        self.call_count += 1

        # 生成模拟结果
        result = BacktestResult(
            strategy_name=strategy_name,
            params=params.copy(),
            total_return=random.uniform(-0.2, 0.5),
            sharpe_ratio=random.uniform(0.5, 2.5),
            max_drawdown=random.uniform(0.05, 0.25),
            win_rate=random.uniform(0.3, 0.7),
            total_trades=random.randint(10, 200)
        )

        # 存入缓存
        if self.use_cache:
            self.cache.put(strategy_name, params, result)

        elapsed_ms = (time.time() - start_time) * 1000
        return result, elapsed_ms


# ============================================================
# 验证测试
# ============================================================

def test_cache_effect():
    """测试缓存效果"""

    print("=" * 60)
    print("韬定律策略优化器集群 - 回测缓存层验证")
    print("=" * 60)

    # 测试参数
    param_space = {
        "short_period": list(range(5, 50, 5)),      # 9个值
        "long_period": list(range(20, 200, 10)),   # 18个值
        "threshold": [round(x * 0.001, 3) for x in range(10, 100, 5)],  # 18个值
        "stop_loss": [round(x * 0.01, 3) for x in range(1, 10, 1)]    # 9个值
    }

    # 生成测试参数组合
    test_params = []
    for short in param_space["short_period"]:
        for long in param_space["long_period"]:
            if long > short:
                for threshold in param_space["threshold"]:
                    for stop_loss in param_space["stop_loss"]:
                        test_params.append({
                            "short_period": short,
                            "long_period": long,
                            "threshold": threshold,
                            "stop_loss": stop_loss
                        })

    # 只取前1000组进行测试
    test_params = test_params[:1000]

    print(f"\n测试场景:")
    print(f"  - 参数组合数: {len(test_params)}")
    print(f"  - 预估无缓存耗时: {len(test_params) * 0.25:.1f}秒 (250ms/组)")
    print(f"  - 预估有缓存耗时: ~{len(test_params) * 0.35:.1f}秒 (含缓存开销)")

    # -------- 场景A: 无缓存 --------
    print(f"\n{'='*60}")
    print("场景A: 无缓存回测")
    print("="*60)

    cache_a = BacktestCache()
    engine_a = MockBacktestEngine(use_cache=False, cache=cache_a)

    start_a = time.time()
    results_a = []
    for params in test_params:
        result, elapsed = engine_a.run_backtest("双均线策略", params)
        results_a.append((result, elapsed))

    total_time_a = time.time() - start_a
    avg_time_a = total_time_a / len(test_params) * 1000

    print(f"  总耗时: {total_time_a:.2f}秒")
    print(f"  平均单次: {avg_time_a:.1f}ms")
    print(f"  实际调用回测次数: {engine_a.call_count}")

    # -------- 场景B: 有缓存 (第一次迭代) --------
    print(f"\n{'='*60}")
    print("场景B: 有缓存回测 (第一次迭代 - 缓存预热)")
    print("="*60)

    cache_b = BacktestCache()
    engine_b = MockBacktestEngine(use_cache=True, cache=cache_b)

    start_b1 = time.time()
    for params in test_params:
        result, elapsed = engine_b.run_backtest("双均线策略", params)
    total_time_b1 = time.time() - start_b1

    stats_b1 = cache_b.get_stats()
    print(f"  总耗时: {total_time_b1:.2f}秒")
    print(f"  缓存命中率: {stats_b1.hit_rate*100:.1f}%")
    print(f"  实际调用回测次数: {engine_b.call_count}")

    # -------- 场景B: 有缓存 (第二次迭代 - 测试命中) --------
    print(f"\n{'='*60}")
    print("场景B: 有缓存回测 (第二次迭代 - 测试缓存命中)")
    print("="*60)

    # 重置调用计数
    engine_b.call_count = 0
    cache_b._stats = CacheStats()  # 重置统计

    start_b2 = time.time()
    for params in test_params:
        result, elapsed = engine_b.run_backtest("双均线策略", params)
    total_time_b2 = time.time() - start_b2

    stats_b2 = cache_b.get_stats()
    avg_time_b2 = total_time_b2 / len(test_params) * 1000

    print(f"  总耗时: {total_time_b2:.2f}秒")
    print(f"  平均单次: {avg_time_b2:.1f}ms")
    print(f"  缓存命中率: {stats_b2.hit_rate*100:.1f}%")
    print(f"  实际调用回测次数: {engine_b.call_count}")

    # -------- 场景C: 有缓存 (重复参数测试 - 高重复率场景) --------
    print(f"\n{'='*60}")
    print("场景C: 有缓存回测 (重复参数场景 - 模拟多优化器重叠搜索)")
    print("="*60)

    # 模拟多优化器搜索, 30%的参数被重复搜索
    repeated_params = test_params.copy()
    for _ in range(int(len(test_params) * 0.3)):
        repeated_params.append(random.choice(test_params))
    random.shuffle(repeated_params)

    cache_c = BacktestCache()
    engine_c = MockBacktestEngine(use_cache=True, cache=cache_c)

    start_c = time.time()
    for params in repeated_params:
        result, elapsed = engine_c.run_backtest("双均线策略", params)
    total_time_c = time.time() - start_c

    stats_c = cache_c.get_stats()
    avg_time_c = total_time_c / len(repeated_params) * 1000

    print(f"  总参数组合数: {len(repeated_params)} (含30%重复)")
    print(f"  总耗时: {total_time_c:.2f}秒")
    print(f"  平均单次: {avg_time_c:.1f}ms")
    print(f"  缓存命中率: {stats_c.hit_rate*100:.1f}%")
    print(f"  实际调用回测次数: {engine_c.call_count}")
    print(f"  节省时间: {stats_c.total_time_saved_ms:.0f}ms")

    # -------- 结果对比 --------
    print(f"\n{'='*60}")
    print("结果对比")
    print("="*60)

    speedup_b2 = total_time_a / total_time_b2 if total_time_b2 > 0 else 0
    speedup_c = total_time_a / total_time_c if total_time_c > 0 else 0

    print(f"\n{'场景':<20} {'总耗时':<12} {'平均单次':<12} {'加速比':<10}")
    print("-" * 60)
    print(f"{'A: 无缓存':<20} {total_time_a:<12.2f} {avg_time_a:<12.1f} {'1.00x':<10}")
    print(f"{'B2: 有缓存(冷)':<20} {total_time_b1:<12.2f} {total_time_b1/len(test_params)*1000:<12.1f} {total_time_a/total_time_b1:<10.2f}x")
    print(f"{'B2: 有缓存(热)':<20} {total_time_b2:<12.2f} {avg_time_b2:<12.1f} {speedup_b2:<10.2f}x")
    print(f"{'C: 有缓存(重复)':<20} {total_time_c:<12.2f} {avg_time_c:<12.1f} {speedup_c:<10.2f}x")

    print(f"\n结论:")
    if stats_b2.hit_rate > 0.9:
        print(f"  ✅ 缓存层工作正常: 第二次迭代命中率 {stats_b2.hit_rate*100:.1f}%")
        print(f"  ✅ 加速效果: {speedup_b2:.2f}倍 (热缓存场景)")
    else:
        print(f"  ⚠️ 缓存命中率较低: {stats_b2.hit_rate*100:.1f}%")

    if speedup_c > 1.5:
        print(f"  ✅ 多优化器场景加速效果显著: {speedup_c:.2f}倍")
        print(f"     核心价值: 多优化器并行时, 搜索空间重叠部分可被缓存复用")
    else:
        print(f"  ⚠️ 重复参数场景加速效果一般: {speedup_c:.2f}倍")

    return {
        "speedup_cold": total_time_a / total_time_b1,
        "speedup_hot": speedup_b2,
        "speedup_repeated": speedup_c,
        "cache_hit_rate": stats_c.hit_rate
    }


def test_cache_key_normalization():
    """测试缓存键标准化"""
    print(f"\n{'='*60}")
    print("测试: 缓存键标准化")
    print("="*60)

    cache = BacktestCache()

    # 测试1: 浮点数精度
    params1 = {"period": 20.0, "threshold": 0.05}
    params2 = {"period": 20.0000000, "threshold": 0.050000}
    params3 = {"period": 20.000001, "threshold": 0.05}

    key1 = cache.make_cache_key("策略", params1)
    key2 = cache.make_cache_key("策略", params2)
    key3 = cache.make_cache_key("策略", params3)

    print(f"  参数1: {params1} -> key: {key1}")
    print(f"  参数2: {params2} -> key: {key2}")
    print(f"  参数3: {params3} -> key: {key3}")

    print(f"\n  key1 == key2: {key1 == key2} (预期: True, 相同值)")
    print(f"  key1 == key3: {key1 == key3} (预期: False, 不同值)")

    # 测试2: 键排序
    params4 = {"b": 2, "a": 1}
    params5 = {"a": 1, "b": 2}

    key4 = cache.make_cache_key("策略", params4)
    key5 = cache.make_cache_key("策略", params5)

    print(f"\n  参数顺序不同但值相同:")
    print(f"    {params4} -> key: {key4}")
    print(f"    {params5} -> key: {key5}")
    print(f"  key4 == key5: {key4 == key5} (预期: True)")


if __name__ == "__main__":
    test_cache_key_normalization()
    print("\n")
    results = test_cache_effect()
