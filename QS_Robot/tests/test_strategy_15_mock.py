"""Strategy-15 低位首板潜伏策略 Mock 数据测试
覆盖8个边界场景：低位/高位/量比/涨幅/涨停/跌停/熊市/低价
"""
import sys, os, logging, json, math
from datetime import datetime, timedelta

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s - %(message)s")

import importlib
mod = importlib.import_module("core.strategies.ths_strategies.14_strategies.15_low_first_board")
LowFirstBoardStrategy = mod.LowFirstBoardStrategy


def make_bars(base_price, days, trend="down", vol_mult=1.0, seed=42):
    """生成模拟日线数据
    trend: 'down'(下跌到底部) / 'up'(上涨到高位) / 'flat'(震荡)
    """
    import random
    rng = random.Random(seed)
    bars = []
    start = datetime(2024, 1, 2)

    if trend == "down":
        high_price = base_price * 2.5
        low_price = base_price
        price_range = high_price - low_price
    elif trend == "up":
        high_price = base_price
        low_price = base_price * 0.4
    else:
        high_price = base_price * 1.2
        low_price = base_price * 0.8
        price_range = high_price - low_price

    for i in range(days):
        date = start + timedelta(days=i)
        if i == 0:
            price = high_price if trend == "down" else low_price
        else:
            if trend == "down":
                price_decay = (i / days) ** 0.7
                price = high_price - (high_price - low_price) * price_decay
            elif trend == "up":
                price_rise = (i / days) ** 0.7
                price = low_price + (high_price - low_price) * price_rise
            else:
                price = base_price + rng.uniform(-0.1, 0.1) * base_price

        noise = rng.gauss(0, price * 0.015)
        close = price + noise
        open_p = close * (1 + rng.uniform(-0.01, 0.01))
        high_p = max(open_p, close) * (1 + abs(rng.gauss(0, 0.005)))
        low_p = min(open_p, close) * (1 - abs(rng.gauss(0, 0.005)))
        base_vol = 5_000_000 + rng.randint(0, 10_000_000)
        volume = base_vol * vol_mult

        bars.append({
            "date": date.strftime("%Y-%m-%d"),
            "open": round(open_p, 2),
            "high": round(high_p, 2),
            "low": round(low_p, 2),
            "close": round(close, 2),
            "volume": round(volume, 0),
        })
    return bars


def tweak_last_bar(bars, **overrides):
    """修改最后一根bar的属性，用于构造特定场景"""
    last = bars[-1].copy()
    for k, v in overrides.items():
        last[k] = v
    return bars[:-1] + [last]


def tweak_last_n_volume(bars, n, vol_mult):
    """修改最后n根bar的成交量"""
    result = bars[:-n]
    for i in range(n):
        b = bars[-(n - i)].copy()
        b["volume"] = round(b["volume"] * vol_mult, 0)
        result.append(b)
    return result


def run_scenario(name, bars, params, expect_buy):
    """运行单个场景并验证"""
    strategy = LowFirstBoardStrategy()
    sig = strategy.generate_signal(bars, params)
    actual = sig is not None and sig.get("action") == "buy"
    status = "✅" if actual == expect_buy else "❌"
    print(f"\n{'='*70}")
    print(f"  {status} 场景: {name}")
    print(f"  {'='*70}")
    print(f"  预期: {'BUY' if expect_buy else 'NO BUY'} | 实际: {'BUY' if actual else 'NO BUY'}")
    if sig and actual:
        print(f"  信号: 价格={sig['price']:.2f} 止损={sig['stop_loss']:.2f} "
              f"止盈={sig['take_profit']:.2f} 评分={sig['composite_score']}")
    return actual == expect_buy


def main():
    print("=" * 70)
    print("  Strategy-15 低位首板潜伏策略 — Mock 边界场景测试")
    print("=" * 70)

    results = []
    base_price = 10.0

    # ─── 场景A：标准低位+热启动 → 应触发BUY ───
    bars = make_bars(base_price, 200, trend="down")
    # 前19天正常量，最后一天巨量（确保量比>3）
    last = bars[-1].copy()
    last["open"] = round(base_price * 1.00, 2)
    last["close"] = round(base_price * 1.05, 2)
    last["high"] = round(base_price * 1.06, 2)
    last["low"] = round(base_price * 0.99, 2)
    # 计算MA20并设置量比>3.5
    ma20_vol = sum(b["volume"] for b in bars[-20:-1]) / 19
    last["volume"] = round(ma20_vol * 3.5, 0)
    bars = bars[:-1] + [last]
    results.append(run_scenario(
        "A: 标准低位+放量涨5%", bars,
        {"index_change": 0.005, "sector_change": 0.02, "regime_label": "shake"},
        expect_buy=True))

    # ─── 场景B：高位非低位 → 应过滤 ───
    bars = make_bars(base_price, 200, trend="up")
    bars = tweak_last_n_volume(bars, 5, 3.0)
    last = bars[-1].copy()
    last["open"] = round(base_price * 2.3, 2)
    last["close"] = round(base_price * 2.4, 2)
    last["high"] = round(base_price * 2.42, 2)
    last["low"] = round(base_price * 2.28, 2)
    bars = bars[:-1] + [last]
    results.append(run_scenario(
        "B: 高位上涨（非低位）", bars,
        {"index_change": 0.005, "sector_change": 0.02, "regime_label": "shake"},
        expect_buy=False))

    # ─── 场景C：量比不满足 → 应过滤 ───
    bars = make_bars(base_price, 200, trend="down")
    # 不放大成交量
    last = bars[-1].copy()
    last["open"] = round(base_price * 1.00, 2)
    last["close"] = round(base_price * 1.05, 2)
    last["high"] = round(base_price * 1.06, 2)
    last["low"] = round(base_price * 0.99, 2)
    bars = bars[:-1] + [last]
    results.append(run_scenario(
        "C: 低位但无量（量比<3）", bars,
        {"index_change": 0.005, "sector_change": 0.02, "regime_label": "shake"},
        expect_buy=False))

    # ─── 场景D：涨幅不满足 → 应过滤 ───
    bars = make_bars(base_price, 200, trend="down")
    bars = tweak_last_n_volume(bars, 5, 3.0)
    last = bars[-1].copy()
    last["open"] = round(base_price * 1.00, 2)
    last["close"] = round(base_price * 1.01, 2)  # 只涨1%
    last["high"] = round(base_price * 1.02, 2)
    last["low"] = round(base_price * 0.99, 2)
    bars = bars[:-1] + [last]
    results.append(run_scenario(
        "D: 低位放量但涨幅仅1%（<2%）", bars,
        {"index_change": 0.005, "sector_change": 0.02, "regime_label": "shake"},
        expect_buy=False))

    # ─── 场景E：已涨停 → 应过滤 ───
    bars = make_bars(base_price, 200, trend="down")
    bars = tweak_last_n_volume(bars, 5, 3.0)
    prev_close = bars[-2]["close"]
    limit_up = round(prev_close * 1.10, 2)
    last = bars[-1].copy()
    last["open"] = round(limit_up * 0.97, 2)
    last["close"] = limit_up
    last["high"] = limit_up
    last["low"] = round(limit_up * 0.97, 2)
    bars = bars[:-1] + [last]
    results.append(run_scenario(
        "E: 低位放量但已涨停", bars,
        {"index_change": 0.005, "sector_change": 0.02, "regime_label": "shake"},
        expect_buy=False))

    # ─── 场景F：已跌停 → 应过滤 ───
    bars = make_bars(base_price, 200, trend="down")
    bars = tweak_last_n_volume(bars, 5, 3.0)
    prev_close = bars[-2]["close"]
    limit_down = round(prev_close * 0.90, 2)
    last = bars[-1].copy()
    last["open"] = round(limit_down * 1.03, 2)
    last["close"] = limit_down
    last["high"] = round(limit_down * 1.03, 2)
    last["low"] = limit_down
    bars = bars[:-1] + [last]
    results.append(run_scenario(
        "F: 低位放量但已跌停", bars,
        {"index_change": 0.005, "sector_change": 0.02, "regime_label": "shake"},
        expect_buy=False))

    # ─── 场景G：熊市环境 → 应过滤 ───
    bars = make_bars(base_price, 200, trend="down")
    last = bars[-1].copy()
    last["open"] = round(base_price * 1.00, 2)
    last["close"] = round(base_price * 1.05, 2)
    last["high"] = round(base_price * 1.06, 2)
    last["low"] = round(base_price * 0.99, 2)
    ma20_vol = sum(b["volume"] for b in bars[-20:-1]) / 19
    last["volume"] = round(ma20_vol * 3.5, 0)
    bars = bars[:-1] + [last]
    results.append(run_scenario(
        "G: 低位+放量+涨5% 但熊市", bars,
        {"index_change": -0.03, "sector_change": -0.02, "regime_label": "bear"},
        expect_buy=False))

    # ─── 场景H：价格过低 → 应过滤 ───
    low_bars = make_bars(3.5, 200, trend="down")
    low_bars = tweak_last_n_volume(low_bars, 5, 3.0)
    last = low_bars[-1].copy()
    last["open"] = 3.50
    last["close"] = 3.68  # 涨5%
    last["high"] = 3.72
    last["low"] = 3.48
    low_bars = low_bars[:-1] + [last]
    results.append(run_scenario(
        "H: 低价股（<4元）", low_bars,
        {"index_change": 0.005, "sector_change": 0.02, "regime_label": "shake"},
        expect_buy=False))

    # ─── 场景I：涨幅超8% → 应过滤 ───
    bars = make_bars(base_price, 200, trend="down")
    last = bars[-1].copy()
    last["open"] = round(base_price * 1.00, 2)
    last["close"] = round(base_price * 1.09, 2)  # 涨9%
    last["high"] = round(base_price * 1.10, 2)
    last["low"] = round(base_price * 0.99, 2)
    ma20_vol = sum(b["volume"] for b in bars[-20:-1]) / 19
    last["volume"] = round(ma20_vol * 3.5, 0)
    bars = bars[:-1] + [last]
    results.append(run_scenario(
        "I: 低位放量但涨幅9%（>8%）", bars,
        {"index_change": 0.005, "sector_change": 0.02, "regime_label": "shake"},
        expect_buy=False))

    # ─── 场景J：沪深300大跌 → 应过滤 ───
    bars = make_bars(base_price, 200, trend="down")
    last = bars[-1].copy()
    last["open"] = round(base_price * 1.00, 2)
    last["close"] = round(base_price * 1.05, 2)
    last["high"] = round(base_price * 1.06, 2)
    last["low"] = round(base_price * 0.99, 2)
    ma20_vol = sum(b["volume"] for b in bars[-20:-1]) / 19
    last["volume"] = round(ma20_vol * 3.5, 0)
    bars = bars[:-1] + [last]
    results.append(run_scenario(
        "J: 低位+放量+涨5% 但沪深300跌2%", bars,
        {"index_change": -0.02, "sector_change": 0.02, "regime_label": "shake"},
        expect_buy=False))

    # ─── 场景K：涨幅3%边界（刚好满足） → 应触发BUY ───
    bars = make_bars(base_price, 200, trend="down")
    last = bars[-1].copy()
    last["open"] = round(base_price * 1.00, 2)
    last["close"] = round(base_price * 1.031, 2)  # 涨3.1%
    last["high"] = round(base_price * 1.04, 2)
    last["low"] = round(base_price * 0.99, 2)
    ma20_vol = sum(b["volume"] for b in bars[-20:-1]) / 19
    last["volume"] = round(ma20_vol * 3.5, 0)
    bars = bars[:-1] + [last]
    results.append(run_scenario(
        "K: 涨幅3.1%（>2%阈值通过）", bars,
        {"index_change": 0.005, "sector_change": 0.02, "regime_label": "shake"},
        expect_buy=True))

    # ─── 总结 ───
    passed = sum(results)
    total = len(results)
    print(f"\n{'='*70}")
    print(f"  测试结果: {passed}/{total} 通过")
    if passed == total:
        print(f"  ✅ 全部通过！")
    else:
        failed = [f"{chr(65+i)}" for i, r in enumerate(results) if not r]
        print(f"  ❌ 失败场景: {', '.join(failed)}")
    print(f"{'='*70}")
    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)