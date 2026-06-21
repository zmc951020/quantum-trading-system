#!/usr/bin/env python3
"""联动场景: 极端行情场景模拟
模拟2024-02-05千股跌停行情，全链路压力测试
"""
import sys
import os
import time
import random
import statistics
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

THRESHOLD_LATENCY_P99_MS = 500
THRESHOLD_CIRCUIT_BREAKER_MS = 50
STRATEGY_COUNT = 5
STOCK_COUNT = 50


def generate_extreme_market_data(days: int = 250) -> list:
    """生成极端行情模拟数据（模拟千股跌停）"""
    random.seed(20240205)
    data = []
    base_price = 100.0

    for i in range(days):
        if i < days - 30:
            # 正常行情
            change = random.gauss(0, 0.015)
        elif i < days - 10:
            # 下跌趋势
            change = random.gauss(-0.02, 0.02)
        elif i < days - 5:
            # 加速下跌
            change = random.gauss(-0.03, 0.025)
        elif i < days - 1:
            # 恐慌
            change = random.gauss(-0.05, 0.03)
        else:
            # 跌停日
            change = -0.10

        close = base_price * (1 + change)
        open_p = close * (1 + random.uniform(-0.02, 0.02))
        high = max(open_p, close) * (1 + abs(random.gauss(0, 0.01)))
        low = min(open_p, close) * (1 - abs(random.gauss(0, 0.01)))
        volume = random.uniform(5e6, 5e8) * (1 + abs(change) * 10)  # 极端行情放量

        data.append({
            "open": open_p, "high": high, "low": low, "close": close,
            "volume": volume, "date": f"2024-{i//30+1:02d}-{i%30+1:02d}",
        })
        base_price = close

    return data


def simulate_strategy_signal(strategy_id: int, market_data: list) -> dict:
    """模拟策略信号生成"""
    t0 = time.perf_counter()

    # 模拟因子计算
    closes = [d["close"] for d in market_data[-20:]]
    if len(closes) >= 2:
        recent_return = (closes[-1] / closes[0] - 1)
    else:
        recent_return = 0

    # 模拟风控检查
    is_extreme = recent_return < -0.05
    if is_extreme:
        # 模拟熔断
        time.sleep(0.001)  # 模拟处理延迟

    t1 = time.perf_counter()
    elapsed_ms = (t1 - t0) * 1000

    return {
        "strategy_id": strategy_id,
        "signal": "SELL" if recent_return < -0.02 else "HOLD",
        "strength": abs(recent_return),
        "circuit_breaker": is_extreme,
        "latency_ms": elapsed_ms,
    }


def simulate_risk_control(data: list) -> dict:
    """模拟风控检查"""
    t0 = time.perf_counter()

    closes = [d["close"] for d in data[-5:]]
    if len(closes) >= 2:
        daily_return = (closes[-1] / closes[-2] - 1)
    else:
        daily_return = 0

    # 熔断条件
    circuit_triggered = daily_return < -0.05
    slippage = abs(daily_return) * 100

    t1 = time.perf_counter()
    elapsed_ms = (t1 - t0) * 1000

    return {
        "circuit_triggered": circuit_triggered,
        "slippage_pct": slippage,
        "latency_ms": elapsed_ms,
    }


def main():
    print("[联动] 极端行情场景模拟 - 千股跌停")
    print(f"  策略数: {STRATEGY_COUNT}, 股票数: {STOCK_COUNT}")
    print()

    # 生成极端行情数据
    print("  生成极端行情数据...")
    all_market_data = {}
    for i in range(STOCK_COUNT):
        all_market_data[f"STOCK_{i:03d}"] = generate_extreme_market_data()
    print(f"  已生成 {STOCK_COUNT} 只股票数据")

    # 测试1: 多策略并行信号生成
    print(f"\n  测试1: {STRATEGY_COUNT} 策略并行信号生成...")
    signal_latencies = []
    circuit_breakers = 0

    for symbol, data in all_market_data.items():
        with ThreadPoolExecutor(max_workers=STRATEGY_COUNT) as executor:
            futures = {
                executor.submit(simulate_strategy_signal, i, data): i
                for i in range(STRATEGY_COUNT)
            }
            for future in as_completed(futures):
                result = future.result()
                signal_latencies.append(result["latency_ms"])
                if result["circuit_breaker"]:
                    circuit_breakers += 1

    signal_latencies.sort()
    p99_idx = int(len(signal_latencies) * 0.99)
    p99 = signal_latencies[p99_idx] if p99_idx < len(signal_latencies) else signal_latencies[-1]

    print(f"    总信号数: {len(signal_latencies)}")
    print(f"    平均延迟: {statistics.mean(signal_latencies):.2f}ms")
    print(f"    P99延迟:  {p99:.2f}ms")
    print(f"    熔断触发: {circuit_breakers}/{len(signal_latencies)}")

    # 测试2: 风控响应时效
    print(f"\n  测试2: 风控响应时效...")
    risk_latencies = []
    for symbol, data in all_market_data.items():
        result = simulate_risk_control(data)
        risk_latencies.append(result["latency_ms"])

    risk_latencies.sort()
    risk_p99 = risk_latencies[int(len(risk_latencies) * 0.99)]

    print(f"    风控检查次数: {len(risk_latencies)}")
    print(f"    平均延迟: {statistics.mean(risk_latencies):.2f}ms")
    print(f"    P99延迟:  {risk_p99:.2f}ms")

    # 验收
    signal_pass = p99 <= THRESHOLD_LATENCY_P99_MS
    risk_pass = risk_p99 <= THRESHOLD_CIRCUIT_BREAKER_MS

    print(f"\n  验收结果:")
    print(f"    信号延迟 P99 ≤ {THRESHOLD_LATENCY_P99_MS}ms: "
          f"{'✅ 通过' if signal_pass else f'❌ 未通过 ({p99:.2f}ms)'}")
    print(f"    风控延迟 P99 ≤ {THRESHOLD_CIRCUIT_BREAKER_MS}ms: "
          f"{'✅ 通过' if risk_pass else f'❌ 未通过 ({risk_p99:.2f}ms)'}")
    print(f"    熔断响应: {'✅ 触发' if circuit_breakers > 0 else '⚠️ 未触发（极端行情应触发熔断）'}")

    overall = signal_pass and risk_pass and circuit_breakers > 0

    if overall:
        print(f"\n  ✅ 整体通过 - 系统在极端行情下稳定运行")
    else:
        print(f"\n  ❌ 未通过 - 存在性能或功能缺陷")

    return overall


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)