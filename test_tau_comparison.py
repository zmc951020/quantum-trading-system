#!/usr/bin/env python3
"""Tau Optimizer Cluster - Comparison Test"""

import sys
import time
import random

sys.path.insert(0, r'd:\Gupiao\升级vscode\QS_Robot\core')

from tau_optimizer_cluster import TauOptimizerCluster
from tau_optimizer_cluster import BacktestResult


PARAM_RANGES = {
    'short_period': (5, 100),
    'long_period': (20, 300),
    'threshold': (0.005, 0.1),
    'stop_loss': (0.01, 0.15),
}


def run_no_cache(params_list):
    start = time.time()
    results = []
    for params in params_list:
        compute_time = random.uniform(0.15, 0.35)
        time.sleep(compute_time)
        r = BacktestResult(
            strategy_name="strategy", params=params,
            total_return=random.uniform(-0.2, 0.5),
            sharpe_ratio=random.uniform(0.3, 2.5),
            max_drawdown=random.uniform(0.05, 0.25),
            win_rate=random.uniform(0.3, 0.7),
            total_trades=random.randint(10, 200),
        )
        results.append(r)
    total_time = time.time() - start
    return results, total_time


def run_exact_cache(params_list):
    start = time.time()
    cache = {}
    results = []
    for params in params_list:
        key = str(sorted(params.items()))
        if key in cache:
            results.append(cache[key])
        else:
            compute_time = random.uniform(0.15, 0.35)
            time.sleep(compute_time)
            r = BacktestResult(
                strategy_name="strategy", params=params,
                total_return=random.uniform(-0.2, 0.5),
                sharpe_ratio=random.uniform(0.3, 2.5),
                max_drawdown=random.uniform(0.05, 0.25),
                win_rate=random.uniform(0.3, 0.7),
                total_trades=random.randint(10, 200),
            )
            cache[key] = r
            results.append(r)
    total_time = time.time() - start
    return results, total_time


def generate_optimizer_params(count, initial=None):
    current = initial or {
        'short_period': 20.0, 'long_period': 60.0,
        'threshold': 0.05, 'stop_loss': 0.05,
    }
    params_list = []
    for _ in range(count):
        if random.random() < 0.1:
            current = {
                'short_period': random.uniform(5, 100),
                'long_period': random.uniform(20, 300),
                'threshold': random.uniform(0.005, 0.1),
                'stop_loss': random.uniform(0.01, 0.15),
            }
        else:
            current = {
                'short_period': max(5, current['short_period'] + random.gauss(0, 2)),
                'long_period': max(20, current['long_period'] + random.gauss(0, 5)),
                'threshold': max(0.005, current['threshold'] + random.gauss(0, 0.005)),
                'stop_loss': max(0.01, current['stop_loss'] + random.gauss(0, 0.005)),
            }
        params_list.append({k: round(v, 4) for k, v in current.items()})
    return params_list


def main():
    print("=" * 70)
    print("Tau Optimizer Cluster - Comparison Test")
    print("=" * 70)
    print()

    params_100 = generate_optimizer_params(100)

    print("[Plan A] No cache (baseline)")
    print("=" * 70)
    results_a, time_a = run_no_cache(params_100)
    print(f"  Total time: {time_a:.2f}s")
    print(f"  Avg per eval: {time_a / len(params_100) * 1000:.1f}ms")

    print("\n[Plan B] Exact-match cache (original design)")
    print("=" * 70)
    results_b, time_b = run_exact_cache(params_100)
    print(f"  Total time: {time_b:.2f}s")
    print(f"  Avg per eval: {time_b / len(params_100) * 1000:.1f}ms")

    print("\n[Plan C] Tau Optimizer Cluster (new: similarity+buckets+incremental)")
    print("=" * 70)
    cluster = TauOptimizerCluster(PARAM_RANGES, strategy_name="strategy")
    start = time.time()
    results_c = []
    for params in params_100:
        result, mode = cluster.optimize(params)
        results_c.append(result)
    time_c = time.time() - start
    status = cluster.get_status()

    print(f"  Total time: {time_c:.2f}s")
    print(f"  Avg per eval: {time_c / len(params_100) * 1000:.1f}ms")
    print(f"  Cache hit rate: {status['cache']['hit_rate']*100:.1f}%")
    print(f"  Exact: {status['cache']['exact_hits']}, Bucket: {status['cache']['bucket_hits']}, Neighbor: {status['cache']['neighbor_hits']}")
    print(f"  Full computes: {status['cache']['full_computes']}/{len(params_100)} (reduction: {status['cache']['compute_reduction']*100:.1f}%)")

    print()
    print("=" * 70)
    print("Comparison")
    print("=" * 70)
    print(f"{'Plan':<25} {'Time(s)':<12} {'Speedup':<10} {'Computes':<12} {'HitRate':<10}")
    print("-" * 70)
    print(f"{'A: No cache':<25} {time_a:<12.2f} {'1.00x':<10} {len(params_100):<12} {'0%':<10}")
    print(f"{'B: Exact cache':<25} {time_b:<12.2f} {time_a/time_b:<10.2f}x {len(params_100):<12} {'~0%':<10}")
    print(f"{'C: Tau Cluster':<25} {time_c:<12.2f} {time_a/time_c:<10.2f}x {status['cache']['full_computes']:<12} {status['cache']['hit_rate']*100:<10.1f}%")

    print()
    print("=" * 70)
    print("Test 2: Space Folding optimization (3-phase workflow)")
    print("=" * 70)
    print()

    cluster2 = TauOptimizerCluster(PARAM_RANGES, strategy_name="strategy")
    start = time.time()
    result = cluster2.run_folding_optimization(
        coarse_points=50, refined_points_per_region=30, validation_points=5
    )
    time_fold = time.time() - start

    print(f"\n  Total time: {time_fold:.2f}s")
    print(f"  Total evals: {result['total_evaluations']}")
    print(f"  Best params: {result['best_params']}")
    print(f"  Best score: {result['best_result'].score():.3f}")
    print(f"  Best return: {result['best_result'].total_return:.3f}, sharpe: {result['best_result'].sharpe_ratio:.2f}")
    print(f"  Cache hit rate: {result['cluster_status']['cache']['hit_rate']*100:.1f}%")
    print(f"  Time saved: {result['cluster_status']['cache']['time_saved_ms']:.0f}ms")
    print()
    print("  Top-5 results:")
    for i, (params, r) in enumerate(result['top_results'][:5], 1):
        print(f"    {i}. score={r.score():.3f}, return={r.total_return:.3f}, sharpe={r.sharpe_ratio:.2f}")


if __name__ == '__main__':
    main()
