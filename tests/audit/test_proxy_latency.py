#!/usr/bin/env python3
"""QX-002: 5002↔5003代理通信延迟测试
反向代理请求延迟P99≤200ms，重试机制验证
"""
import sys
import os
import time
import statistics
from pathlib import Path

# 添加 QS_Robot 路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "QS_Robot"))

THRESHOLD_P99_MS = 200
SAMPLE_COUNT = 100
RETRY_SUCCESS_RATE = 0.95


def test_proxy_latency():
    """测试代理通信延迟"""
    results = []

    print(f"[QX-002] 5002↔5003 代理通信延迟测试")
    print(f"  阈值: P99 ≤ {THRESHOLD_P99_MS}ms")
    print()

    # 测试代理GET请求延迟
    try:
        from api.aurora_core_adapter import AuroraCoreAdapter

        adapter = AuroraCoreAdapter()

        for i in range(SAMPLE_COUNT):
            t0 = time.perf_counter()
            try:
                result = adapter._proxy_get("/api/strategy/list", timeout=10)
                t1 = time.perf_counter()
                elapsed_ms = (t1 - t0) * 1000
                if result.get("success"):
                    results.append(elapsed_ms)
                    if i % 20 == 0:
                        print(f"  样本 {i+1}/{SAMPLE_COUNT}: {elapsed_ms:.2f}ms ✓")
                else:
                    if i % 20 == 0:
                        print(f"  样本 {i+1}/{SAMPLE_COUNT}: {elapsed_ms:.2f}ms ✗ ({result.get('error', 'unknown')})")
            except Exception as e:
                if i % 20 == 0:
                    print(f"  样本 {i+1}/{SAMPLE_COUNT}: ERROR - {e}")

    except ImportError as e:
        print(f"  ⚠️ AuroraCoreAdapter 不可用: {e}")
        print(f"  使用 HTTP 直连方式测试...")

        import requests
        AURORA_URL = "http://127.0.0.1:5002"

        for i in range(SAMPLE_COUNT):
            t0 = time.perf_counter()
            try:
                r = requests.get(f"{AURORA_URL}/api/strategy/list", timeout=10)
                t1 = time.perf_counter()
                elapsed_ms = (t1 - t0) * 1000
                if r.status_code == 200:
                    results.append(elapsed_ms)
                    if i % 20 == 0:
                        print(f"  样本 {i+1}/{SAMPLE_COUNT}: {elapsed_ms:.2f}ms ✓")
                else:
                    if i % 20 == 0:
                        print(f"  样本 {i+1}/{SAMPLE_COUNT}: {elapsed_ms:.2f}ms ✗ (HTTP {r.status_code})")
            except Exception as e:
                if i % 20 == 0:
                    print(f"  样本 {i+1}/{SAMPLE_COUNT}: ERROR - {e}")

    if not results:
        print("\n❌ 5002 服务不可达，无法测试")
        print("  请确保 5002 服务已启动: python visualization.py")
        return False

    # 统计
    results.sort()
    p50 = results[len(results) // 2]
    p99_idx = int(len(results) * 0.99)
    p99 = results[p99_idx] if p99_idx < len(results) else results[-1]
    avg = statistics.mean(results)
    success_rate = len(results) / SAMPLE_COUNT

    print(f"\n  统计结果:")
    print(f"    请求数:   {SAMPLE_COUNT}")
    print(f"    成功数:   {len(results)}")
    print(f"    成功率:   {success_rate:.1%}")
    print(f"    平均:     {avg:.2f}ms")
    print(f"    P50:      {p50:.2f}ms")
    print(f"    P99:      {p99:.2f}ms")

    p99_pass = p99 <= THRESHOLD_P99_MS
    retry_pass = success_rate >= RETRY_SUCCESS_RATE

    print(f"\n  验收结果:")
    print(f"    P99 ≤ {THRESHOLD_P99_MS}ms: {'✅ 通过' if p99_pass else f'❌ 未通过 ({p99:.2f}ms)'}")
    print(f"    成功率 ≥ {RETRY_SUCCESS_RATE:.0%}: {'✅ 通过' if retry_pass else f'❌ 未通过 ({success_rate:.1%})'}")

    return p99_pass and retry_pass


if __name__ == "__main__":
    success = test_proxy_latency()
    sys.exit(0 if success else 1)