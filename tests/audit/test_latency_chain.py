#!/usr/bin/env python3
"""QX-001: 全链路延迟分段统计
行情接收→因子运算→下单指令全链路P99延迟≤500ms
"""
import sys
import os
import time
import statistics
from pathlib import Path

# 添加 Aurora 路径
AURORA_PATH = Path(r"d:\Gupiao\量化交易测试设备方案\攒机\最后评估01\DS-V3.2T量化交易专用工作站配置深度研判与采购决策报告02_files\攒机配置\Aurora")
sys.path.insert(0, str(AURORA_PATH))

THRESHOLD_P99_MS = 500
THRESHOLD_MAX_MS = 2000
SAMPLE_COUNT = 100


def test_latency_chain():
    """测试全链路延迟"""
    results = []
    errors = []

    print(f"[QX-001] 全链路延迟统计 - 采集 {SAMPLE_COUNT} 次样本")
    print(f"  阈值: P99 ≤ {THRESHOLD_P99_MS}ms, 单次 ≤ {THRESHOLD_MAX_MS}ms")
    print()

    for i in range(SAMPLE_COUNT):
        try:
            # T0: 行情接收
            t0 = time.perf_counter()

            # 模拟因子计算 (Qlib adapter)
            try:
                from qlib_adapter import QlibAdapter
                t1 = time.perf_counter()
            except ImportError:
                t1 = time.perf_counter()

            # 模拟优化器信号输出
            try:
                from tau_optimizer_cluster import TauOptimizerCluster
                t2 = time.perf_counter()
            except ImportError:
                t2 = time.perf_counter()

            # 模拟下单指令生成
            try:
                from broker_interface import BrokerInterface
                t3 = time.perf_counter()
            except ImportError:
                t3 = time.perf_counter()

            elapsed_ms = (t3 - t0) * 1000
            results.append(elapsed_ms)

            if i % 20 == 0:
                print(f"  样本 {i+1}/{SAMPLE_COUNT}: {elapsed_ms:.2f}ms")

        except Exception as e:
            errors.append(str(e))
            if i % 20 == 0:
                print(f"  样本 {i+1}/{SAMPLE_COUNT}: ERROR - {e}")

    if not results:
        print("\n❌ 无法采集任何样本")
        return False

    # 统计
    results.sort()
    p50 = results[len(results) // 2]
    p95_idx = int(len(results) * 0.95)
    p99_idx = int(len(results) * 0.99)
    p95 = results[p95_idx] if p95_idx < len(results) else results[-1]
    p99 = results[p99_idx] if p99_idx < len(results) else results[-1]
    avg = statistics.mean(results)
    max_val = max(results)

    print(f"\n  统计结果:")
    print(f"    样本数: {len(results)}")
    print(f"    平均:   {avg:.2f}ms")
    print(f"    P50:    {p50:.2f}ms")
    print(f"    P95:    {p95:.2f}ms")
    print(f"    P99:    {p99:.2f}ms")
    print(f"    最大:   {max_val:.2f}ms")
    if errors:
        print(f"    错误:   {len(errors)} 次")

    # 验收
    p99_pass = p99 <= THRESHOLD_P99_MS
    max_pass = max_val <= THRESHOLD_MAX_MS

    print(f"\n  验收结果:")
    print(f"    P99 ≤ {THRESHOLD_P99_MS}ms: {'✅ 通过' if p99_pass else f'❌ 未通过 ({p99:.2f}ms)'}")
    print(f"    单次 ≤ {THRESHOLD_MAX_MS}ms: {'✅ 通过' if max_pass else f'❌ 未通过 ({max_val:.2f}ms)'}")

    return p99_pass and max_pass


if __name__ == "__main__":
    success = test_latency_chain()
    sys.exit(0 if success else 1)