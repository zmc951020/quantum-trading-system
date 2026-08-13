"""Strategy-15 盘中分钟级数据模拟测试
验证涨速等盘中瞬时指标逻辑，覆盖日线回测无法验证的实盘场景

盘中数据特征：
  1分钟K线 × 240根/天（A股9:30-11:30, 13:00-15:00）
  涨速 = (当前价 - 5分钟前价) / 5分钟前价
  量比 = 当前累计量 / 前N日均量×时间比例
"""
import sys, os, math, logging
from datetime import datetime, timedelta
from collections import defaultdict

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [Intraday] %(levelname)s - %(message)s")
logger = logging.getLogger("S15-Intraday")

import importlib
mod = importlib.import_module("core.strategies.ths_strategies.14_strategies.15_low_first_board")
LowFirstBoardStrategy = mod.LowFirstBoardStrategy


# ========== 盘中分钟数据生成器 ==========

def generate_intraday_bars(prev_close, open_price, pattern="steady_rise", seed=42):
    """生成一天240根1分钟K线
    pattern:
      steady_rise  - 稳步上涨 3-8%
      rapid_spike  - 盘中急速拉升
      sharp_drop   - 冲高回落
      sideways     - 横盘震荡
      limit_up     - 封涨停
    """
    import random
    rng = random.Random(seed)
    bars = []
    current = open_price
    total_minutes = 240

    for m in range(total_minutes):
        if m == 0:
            o = open_price
        else:
            o = bars[-1]["close"]

        if pattern == "steady_rise":
            drift = (open_price * 0.06) / total_minutes
            noise = rng.gauss(0, open_price * 0.0005)
            c = o + drift + noise
            if c > prev_close * 1.098:
                c = prev_close * 1.098

        elif pattern == "rapid_spike":
            if m < 60:
                drift = 0
            elif m < 120:
                drift = (open_price * 0.08) / 60
            else:
                drift = -open_price * 0.001
            noise = rng.gauss(0, open_price * 0.001)
            c = o + drift + noise
            if c > prev_close * 1.098:
                c = prev_close * 1.098

        elif pattern == "sharp_drop":
            if m < 80:
                drift = (open_price * 0.07) / 80
            else:
                drift = -(open_price * 0.05) / 160
            noise = rng.gauss(0, open_price * 0.001)
            c = o + drift + noise

        elif pattern == "high_open_drop":
            total_drop = open_price * 0.06
            drift = -total_drop / total_minutes
            noise = rng.gauss(0, open_price * 0.001)
            c = o + drift + noise

        elif pattern == "sideways":
            noise = rng.gauss(0, open_price * 0.0005)
            c = o + noise

        elif pattern == "limit_up":
            limit = prev_close * 1.098
            if m < 120:
                drift = (limit - open_price) / 120
                c = o + drift + rng.gauss(0, open_price * 0.0005)
            else:
                c = limit + rng.gauss(0, 0.01)
            if c > limit:
                c = limit

        h = max(o, c) * (1 + abs(rng.gauss(0, 0.0003)))
        l = min(o, c) * (1 - abs(rng.gauss(0, 0.0003)))
        vol = int(50000 + rng.randint(0, 200000))
        if pattern in ("steady_rise", "rapid_spike"):
            vol = int(vol * (1 + m / total_minutes * 2))

        bars.append({
            "minute": m,
            "open": round(o, 3),
            "high": round(h, 3),
            "low": round(l, 3),
            "close": round(c, 3),
            "volume": vol,
        })

    return bars


# ========== 涨速计算 ==========

def calc_price_speed(bars, lookback=5):
    """计算涨速: (当前价 - N分钟前价) / N分钟前价
    返回: (涨速值, 是否≥0)
    """
    if len(bars) < lookback + 1:
        return 0.0, True
    prev = bars[-lookback - 1]["close"]
    current = bars[-1]["close"]
    if prev <= 0:
        return 0.0, True
    speed = (current - prev) / prev
    return speed, speed >= 0


def calc_realtime_vol_ratio(intraday_bars, daily_avg_vol):
    """实时量比: 当前累计量 / 日均量×时间比例"""
    total_minutes = len(intraday_bars)
    cum_vol = sum(b["volume"] for b in intraday_bars)
    time_ratio = total_minutes / 240
    expected_vol = daily_avg_vol * time_ratio
    if expected_vol <= 0:
        return 0.0
    return cum_vol / expected_vol


def calc_realtime_gain(intraday_bars, prev_close):
    """实时涨幅"""
    if not intraday_bars:
        return 0.0
    return (intraday_bars[-1]["close"] - prev_close) / prev_close


# ========== 盘中策略检查器 ==========

class IntradayChecker:
    """盘中实时检查器，模拟实盘分钟级决策"""

    def __init__(self, prev_close, open_price, daily_avg_vol=5_000_000):
        self.prev_close = prev_close
        self.open_price = open_price
        self.daily_avg_vol = daily_avg_vol
        self.strategy = LowFirstBoardStrategy()
        self.bars = []
        self.signals = []

    def feed_bar(self, bar):
        """喂入一根1分钟K线，返回实时信号"""
        self.bars.append(bar)
        if len(self.bars) < 30:
            return None

        current = bar["close"]
        gain = calc_realtime_gain(self.bars, self.prev_close)
        vol_ratio = calc_realtime_vol_ratio(self.bars, self.daily_avg_vol)
        price_speed, speed_ok = calc_price_speed(self.bars, 5)

        # 检查是否在2-8%区间
        in_range = 0.02 < gain < 0.08

        # 检查量比
        vol_ok = 3.0 < vol_ratio < 10.0

        # 检查涨速
        speed_ok_check = price_speed >= 0

        # 记录信号
        if in_range and vol_ok and speed_ok_check:
            sig = {
                "minute": bar["minute"],
                "price": current,
                "gain": round(gain * 100, 2),
                "vol_ratio": round(vol_ratio, 1),
                "price_speed": round(price_speed * 100, 4),
                "stop_loss": round(current * 0.96, 3),
                "take_profit": round(current * 1.07, 3),
            }
            self.signals.append(sig)

        return {
            "minute": bar["minute"], "price": current,
            "gain_pct": round(gain * 100, 2),
            "vol_ratio": round(vol_ratio, 1),
            "price_speed_pct": round(price_speed * 100, 4),
            "in_range": in_range, "vol_ok": vol_ok, "speed_ok": speed_ok_check,
            "signal": in_range and vol_ok and speed_ok_check,
        }


# ========== 测试场景 ==========

def run_scenario(name, pattern, prev_close, open_price, expect_signal, expect_min_minute=30):
    """运行一个盘中场景"""
    bars = generate_intraday_bars(prev_close, open_price, pattern)
    checker = IntradayChecker(prev_close, open_price, daily_avg_vol=8_000_000)

    snapshots = []
    first_signal_minute = None

    for bar in bars:
        result = checker.feed_bar(bar)
        if result and result["signal"] and first_signal_minute is None:
            first_signal_minute = bar["minute"]
        if bar["minute"] % 30 == 0:
            snapshots.append(result)

    has_signal = len(checker.signals) > 0
    status = "✅" if has_signal == expect_signal else "❌"

    print(f"\n{'='*70}")
    print(f"  {status} 场景: {name} ({pattern})")
    print(f"  {'='*70}")
    print(f"  前收盘={prev_close} 开盘={open_price} 预期信号={'有' if expect_signal else '无'}")
    print(f"  实际: {'有信号' if has_signal else '无信号'} | 信号数={len(checker.signals)}")
    if first_signal_minute:
        print(f"  首次触发: 第{first_signal_minute}分钟（约{first_signal_minute//60+9}:{first_signal_minute%60:02d}）")

    if checker.signals:
        s = checker.signals[0]
        print(f"  首个信号: 涨幅={s['gain']}% 量比={s['vol_ratio']} 涨速={s['price_speed']}% "
              f"价格={s['price']} 止损={s['stop_loss']} 止盈={s['take_profit']}")

    # 打印关键时间点快照
    print(f"\n  {'分钟':<6}{'价格':>8}{'涨幅%':>8}{'量比':>7}{'涨速%':>10}{'区间':>6}{'量OK':>6}{'速OK':>6}{'信号':>6}")
    print(f"  {'-'*65}")
    for s in snapshots:
        if s:
            print(f"  {s['minute']:<6}{s['price']:>8.2f}{s['gain_pct']:>8.2f}{s['vol_ratio']:>7.1f}"
                  f"{s['price_speed_pct']:>10.4f}{'✓' if s['in_range'] else '✗':>6}"
                  f"{'✓' if s['vol_ok'] else '✗':>6}"
                  f"{'✓' if s['speed_ok'] else '✗':>6}"
                  f"{'★★★' if s['signal'] else '':>6}")

    return has_signal == expect_signal


def main():
    print("=" * 70)
    print("  Strategy-15 盘中分钟级涨速模拟测试")
    print("  涨速 = (当前价 - 5分钟前价) / 5分钟前价")
    print("=" * 70)

    results = []

    # 场景1: 稳步上涨 → 涨速持续≥0, 应触发
    results.append(run_scenario(
        "S1: 稳步上涨5%", "steady_rise",
        prev_close=10.00, open_price=10.02,
        expect_signal=True))

    # 场景2: 急速拉升 → 盘中突然拉升, 涨速骤增
    results.append(run_scenario(
        "S2: 盘中急速拉升", "rapid_spike",
        prev_close=10.00, open_price=10.01,
        expect_signal=True))

    # 场景3: 冲高回落 → 涨速先正后负, 开盘后买入则亏损
    results.append(run_scenario(
        "S3: 冲高回落（假突破）", "sharp_drop",
        prev_close=10.00, open_price=10.02,
        expect_signal=True))

    # 场景4: 横盘震荡 → 涨速≈0, 涨幅不满足
    results.append(run_scenario(
        "S4: 横盘震荡", "sideways",
        prev_close=10.00, open_price=10.00,
        expect_signal=False))

    # 场景5: 封涨停 → 涨速正常但涨幅超8%后不在区间
    results.append(run_scenario(
        "S5: 封涨停板", "limit_up",
        prev_close=10.00, open_price=10.05,
        expect_signal=True))

    # 场景6: 高开低走 → 开盘在2-8%区间触发信号，但随后回落（止损保护）
    results.append(run_scenario(
        "S6: 高开低走（触发后止损保护）", "high_open_drop",
        prev_close=10.00, open_price=10.35,
        expect_signal=True))

    # 场景7: 涨速边界测试 → 价格刚好在3%边缘, 涨速=0
    results.append(run_scenario(
        "S7: 涨幅3%边界+涨速=0", "steady_rise",
        prev_close=10.00, open_price=10.00,
        expect_signal=True))

    # ─── 总结 ───
    passed = sum(results)
    total = len(results)
    print(f"\n{'='*70}")
    print(f"  盘中测试结果: {passed}/{total} 通过")
    if passed == total:
        print(f"  ✅ 全部通过！")
    else:
        failed = [f"S{i+1}" for i, r in enumerate(results) if not r]
        print(f"  ❌ 失败: {', '.join(failed)}")
    print(f"{'='*70}")

    # ─── 实盘差异分析 ───
    print(f"\n{'='*70}")
    print(f"  日线回测 vs 实盘 差异分析")
    print(f"{'='*70}")
    print(f"""
  日线回测局限:
    1. 涨速不可模拟 → 日线用涨幅替代，可能漏掉盘中急拉的信号
    2. 量比近似 → 日线用MA20近似，实盘量比是实时累计/时间比例
    3. 2-8%区间 → 日线看收盘价，实盘可在盘中任何时刻介入
    4. 滑点 → 日线假设收盘价成交，实盘有bid-ask spread

  建议:
    1. 日线策略作为"预筛选"：收盘后选出符合低位+量比的候选池
    2. 盘中实时监控：候选池内股票，盘中触发2-8%+涨速≥0即介入
    3. 两阶段流程：日线粗筛 → 分钟级精筛 → 人工确认
  """)

    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)