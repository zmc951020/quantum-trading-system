#!/usr/bin/env python3
"""SW-001: 多因子并行运算基准测试
50标的全因子计算≤3s
"""
import sys
import os
import time
import statistics
from pathlib import Path

# 添加路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "QS_Robot"))
sys.path.insert(0, r"d:\Gupiao\量化交易测试设备方案\攒机\最后评估01\DS-V3.2T量化交易专用工作站配置深度研判与采购决策报告02_files\攒机配置\Aurora")

THRESHOLD_50_SYMBOLS_S = 3.0
THRESHOLD_SINGLE_FACTOR_MS = 500
REPEAT_COUNT = 10

# 测试股票池（沪深300成分股样本）
TEST_SYMBOLS = [
    "000001.SZ", "000002.SZ", "000063.SZ", "000333.SZ", "000651.SZ",
    "000725.SZ", "000858.SZ", "002415.SZ", "002594.SZ", "300750.SZ",
    "600000.SH", "600009.SH", "600016.SH", "600028.SH", "600030.SH",
    "600036.SH", "600048.SH", "600050.SH", "600104.SH", "600276.SH",
    "600309.SH", "600519.SH", "600585.SH", "600809.SH", "600887.SH",
    "600900.SH", "601012.SH", "601088.SH", "601166.SH", "601318.SH",
    "601328.SH", "601390.SH", "601398.SH", "601668.SH", "601857.SH",
    "601888.SH", "601899.SH", "601919.SH", "601985.SH", "601988.SH",
    "603259.SH", "603288.SH", "603501.SH", "603986.SH", "688981.SH",
    "000001.SZ", "000002.SZ", "000063.SZ", "000333.SZ", "000651.SZ",
][:50]


def generate_mock_kline(symbol: str, days: int = 250):
    """生成模拟K线数据（当真实数据不可用时）"""
    import random
    random.seed(hash(symbol) % 2**32)
    base_price = random.uniform(10, 200)
    data = []
    for i in range(days):
        change = random.gauss(0, 0.02)
        close = base_price * (1 + change)
        open_p = close * (1 + random.uniform(-0.01, 0.01))
        high = max(open_p, close) * (1 + abs(random.gauss(0, 0.005)))
        low = min(open_p, close) * (1 - abs(random.gauss(0, 0.005)))
        volume = random.uniform(1e6, 1e8)
        data.append({
            "open": open_p, "high": high, "low": low, "close": close,
            "volume": volume, "date": f"2026-{i//30+1:02d}-{i%30+1:02d}",
        })
        base_price = close
    return data


def compute_momentum_factor(data: list) -> float:
    """动量因子"""
    if len(data) < 20:
        return 0.0
    closes = [d["close"] for d in data]
    return (closes[-1] / closes[-20] - 1) * 100


def compute_volatility_factor(data: list) -> float:
    """波动率因子"""
    if len(data) < 20:
        return 0.0
    returns = []
    closes = [d["close"] for d in data[-21:]]
    for i in range(1, len(closes)):
        returns.append((closes[i] - closes[i-1]) / closes[i-1])
    return statistics.stdev(returns) * 100 if len(returns) > 1 else 0.0


def compute_volume_factor(data: list) -> float:
    """量能因子"""
    if len(data) < 5:
        return 0.0
    recent_vol = statistics.mean([d["volume"] for d in data[-5:]])
    all_vol = statistics.mean([d["volume"] for d in data[-20:]]) if len(data) >= 20 else recent_vol
    return recent_vol / all_vol if all_vol > 0 else 1.0


def compute_entropy_factor(data: list) -> float:
    """熵因子"""
    if len(data) < 20:
        return 0.0
    import math
    returns = []
    closes = [d["close"] for d in data[-21:]]
    for i in range(1, len(closes)):
        r = (closes[i] - closes[i-1]) / closes[i-1]
        returns.append(r)
    if not returns:
        return 0.0
    mean_r = statistics.mean(returns)
    variance = statistics.mean([(r - mean_r)**2 for r in returns])
    if variance <= 0:
        return 0.0
    return 0.5 * math.log(2 * math.pi * math.e * variance)


def compute_single_stock_factors(symbol: str, data: list) -> dict:
    """计算单只股票所有因子"""
    return {
        "symbol": symbol,
        "momentum": compute_momentum_factor(data),
        "volatility": compute_volatility_factor(data),
        "volume_ratio": compute_volume_factor(data),
        "entropy": compute_entropy_factor(data),
    }


def main():
    print("[SW-001] 多因子并行运算基准测试")
    print(f"  阈值: 50标的 ≤ {THRESHOLD_50_SYMBOLS_S}s")
    print()

    # 生成模拟数据
    print(f"  生成 {len(TEST_SYMBOLS)} 只股票模拟数据...")
    all_data = {}
    for symbol in TEST_SYMBOLS:
        all_data[symbol] = generate_mock_kline(symbol)
    print(f"  数据生成完成")

    # 串行测试（基准）
    print(f"\n  串行运算测试...")
    t0 = time.perf_counter()
    for symbol in TEST_SYMBOLS:
        compute_single_stock_factors(symbol, all_data[symbol])
    serial_time = time.perf_counter() - t0
    print(f"  串行耗时: {serial_time:.3f}s")

    # 并行测试
    print(f"\n  并行运算测试 ({REPEAT_COUNT} 次取平均)...")
    parallel_times = []
    for run in range(REPEAT_COUNT):
        t0 = time.perf_counter()
        # 使用线程池并行计算
        from concurrent.futures import ThreadPoolExecutor, as_completed
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = {
                executor.submit(compute_single_stock_factors, symbol, all_data[symbol]): symbol
                for symbol in TEST_SYMBOLS
            }
            results = []
            for future in as_completed(futures):
                results.append(future.result())
        elapsed = time.perf_counter() - t0
        parallel_times.append(elapsed)
        print(f"    运行 {run+1}/{REPEAT_COUNT}: {elapsed:.3f}s")

    avg_parallel = statistics.mean(parallel_times)
    speedup = serial_time / avg_parallel if avg_parallel > 0 else 0

    print(f"\n  统计结果:")
    print(f"    标的数:   {len(TEST_SYMBOLS)}")
    print(f"    串行耗时: {serial_time:.3f}s")
    print(f"    并行平均: {avg_parallel:.3f}s")
    print(f"    加速比:   {speedup:.1f}x")
    print(f"    并行范围: {min(parallel_times):.3f}s - {max(parallel_times):.3f}s")

    passed = avg_parallel <= THRESHOLD_50_SYMBOLS_S

    print(f"\n  验收结果:")
    print(f"    50标的 ≤ {THRESHOLD_50_SYMBOLS_S}s: {'✅ 通过' if passed else f'❌ 未通过 ({avg_parallel:.3f}s)'}")

    return passed


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)