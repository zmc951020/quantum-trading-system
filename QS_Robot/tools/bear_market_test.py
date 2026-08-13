"""熊市策略适配器
方案A: 反转多头条件 → 做空信号
方案B: 股指期货对冲（IF/IC）
"""
import os
import sys
import json
import math
import time
import logging
import importlib
from datetime import datetime
from collections import defaultdict

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

logging.basicConfig(level=logging.WARNING)
logging.getLogger("ths").setLevel(logging.WARNING)
logger = logging.getLogger("bear_adapter")

REPORTS_DIR = os.path.join(PROJECT_ROOT, "reports", "bear_market")

# 策略周期映射
PERIOD_MAP = {
    "02_weekly_breakout": "weekly", "14_four_ma_resonance": "weekly",
    "12_twenty_day_lifeline": "weekly", "13_sixty_day_bull_bear": "weekly",
    "10_five_day_low_suck": "daily", "11_ten_day_wave": "daily",
    "01_macd_wave": "daily", "05_ma_long_arrangement": "daily",
    "06_expma_double_cross": "daily", "07_macd_zero_second_cross": "daily",
    "08_dmi_adx_strong_trend": "daily", "09_boll_upper_breakout": "daily",
    "03_dragon_head": "special", "04_dragon_list_follow": "special",
}


def resample_daily_to_weekly(bars):
    weeks = defaultdict(list)
    for b in bars:
        d = str(b["date"])[:10]
        dt = datetime.strptime(d, "%Y-%m-%d")
        iso = dt.isocalendar()
        weeks[(iso[0], iso[1])].append(b)
    result = []
    for (y, w), wb in sorted(weeks.items()):
        if len(wb) < 2:
            continue
        result.append({"date": wb[-1]["date"], "open": wb[0]["open"],
                       "high": max(b["high"] for b in wb),
                       "low": min(b["low"] for b in wb),
                       "close": wb[-1]["close"],
                       "volume": sum(b["volume"] for b in wb)})
    return result


def classify_regime(bars, period=60):
    closes = [b["close"] for b in bars]
    if len(closes) < period:
        return {"labels": ["unknown"] * len(bars), "stats": {}}
    labels = ["unknown"] * period
    for i in range(period, len(bars)):
        ma = sum(closes[i - period:i + 1]) / (period + 1)
        ma_prev = sum(closes[i - period - 1:i]) / (period + 1)
        slope = (ma - ma_prev) / ma_prev if ma_prev > 0 else 0
        if closes[i] > ma and slope > 0.002:
            labels.append("bull")
        elif closes[i] < ma and slope < -0.002:
            labels.append("bear")
        else:
            labels.append("ranging")
    return {"labels": labels, "stats": {
        "bull": labels.count("bull"), "bear": labels.count("bear"),
        "ranging": labels.count("ranging"), "total": len(labels) - period}}


def load_bars(stock, start, end):
    from core.data_bus import get_data_bus
    bus = get_data_bus()
    start_dt = datetime.strptime(start, "%Y-%m-%d")
    end_dt = datetime.strptime(end, "%Y-%m-%d")
    days_needed = (end_dt - start_dt).days + 120
    kline = bus.get_kline(stock, days=min(days_needed, 2000))
    if not kline or not kline.get("dates"):
        return None
    dates = kline["dates"]
    indices = [i for i, d in enumerate(dates) if start <= str(d)[:10] <= end]
    if not indices or len(indices) < 120:
        indices = list(range(len(dates)))
    lo, hi = indices[0], indices[-1] + 1
    return [{"date": kline["dates"][i], "open": float(kline["opens"][i]),
             "high": float(kline["highs"][i]), "low": float(kline["lows"][i]),
             "close": float(kline["closes"][i]), "volume": float(kline["volumes"][i])}
            for i in range(lo, hi)]


def load_strategy(module_name):
    try:
        import inspect
        from core.strategies.ths_strategies.base import THSBaseStrategy
        mod = importlib.import_module(f"core.strategies.ths_strategies.14_strategies.{module_name}")
        for name, obj in inspect.getmembers(mod, inspect.isclass):
            if (issubclass(obj, THSBaseStrategy) and obj is not THSBaseStrategy
                    and obj.__module__ == mod.__name__):
                return obj()
    except Exception as e:
        logger.warning("加载 %s 失败: %s", module_name, e)
    return None


def run_normal_long(strategy, bars, regime, params):
    """原始多头策略（基线）"""
    buys, sells = [], []
    labels = regime["labels"]
    for i in range(60, len(bars)):
        try:
            sig = strategy.generate_signal(bars[:i + 1], params)
        except Exception:
            continue
        if sig is None:
            continue
        if sig.get("action") == "buy":
            buys.append({"idx": i, "price": bars[i]["close"], "regime": labels[i]})
        elif sig.get("action") == "sell":
            sells.append({"idx": i, "price": bars[i]["close"]})
    return trades_from_buys(buys, sells, bars, "多头")


def run_reverse_short(strategy, bars, regime, params):
    """方案A：反转策略 — 熊市中条件满足→做空，多头条件满足→平空"""
    shorts, covers = [], []
    labels = regime["labels"]
    in_short = False

    for i in range(60, len(bars)):
        if labels[i] not in ("bear", "bull", "ranging"):
            continue
        try:
            # 先获取条件（通过调用generate_signal + 读取_last_entry_conditions）
            sig = strategy.generate_signal(bars[:i + 1], params)
        except Exception:
            continue

        conditions = getattr(strategy, "_last_entry_conditions", {})
        if not conditions:
            if sig is None:
                continue
            if sig.get("action") == "sell":
                if in_short:
                    covers.append({"idx": i, "price": bars[i]["close"]})
                    in_short = False
            continue

        total = len(conditions)
        passed = sum(1 for v in conditions.values() if v)
        score = passed / total if total > 0 else 0

        if labels[i] == "bear":
            if not in_short and score >= 0.6:
                shorts.append({"idx": i, "price": bars[i]["close"], "regime": "bear"})
                in_short = True
        elif in_short:
            if score >= 0.6 or labels[i] == "bull":
                covers.append({"idx": i, "price": bars[i]["close"]})
                in_short = False

    if in_short:
        covers.append({"idx": len(bars) - 1, "price": bars[-1]["close"]})
    return trades_from_shorts(shorts, covers, bars, "反转做空")


def run_hedge_short(strategy, bars, regime, params, index_bars=None):
    """方案B：股指对冲 — 熊市用IF对冲"""
    buys, sells = [], []
    hedges = []
    labels = regime["labels"]
    hedging = False
    hedge_ratio = 0

    for i in range(60, len(bars)):
        try:
            sig = strategy.generate_signal(bars[:i + 1], params)
        except Exception:
            continue

        # 多头信号
        if sig and sig.get("action") == "buy":
            buys.append({"idx": i, "price": bars[i]["close"], "regime": labels[i]})
        elif sig and sig.get("action") == "sell":
            sells.append({"idx": i, "price": bars[i]["close"]})

        # 熊市对冲
        if labels[i] == "bear" and not hedging:
            hedge_ratio = calc_beta(bars, index_bars, i) if index_bars else 0.5
            hedging = True
            hedges.append({"idx": i, "action": "open", "ratio": hedge_ratio})
        elif labels[i] != "bear" and hedging:
            hedging = False
            hedges.append({"idx": i, "action": "close", "ratio": hedge_ratio})

    long_trades = trades_from_buys(buys, sells, bars, "多头")
    hedge_pl = calc_hedge_pl(hedges, bars, index_bars)
    return merge_hedge(long_trades, hedge_pl, hedges)


def calc_beta(stock_bars, index_bars, idx):
    if not index_bars or idx < 60:
        return 0.5
    n = min(60, idx)
    stock_ret = [(stock_bars[idx - n + j]["close"] / stock_bars[idx - n + j - 1]["close"] - 1)
                 for j in range(1, n)]
    idx_ret = [(index_bars[idx - n + j]["close"] / index_bars[idx - n + j - 1]["close"] - 1)
               for j in range(1, n)]
    if len(stock_ret) < 2:
        return 0.5
    cov = sum((s - sum(stock_ret) / len(stock_ret)) * (i - sum(idx_ret) / len(idx_ret))
              for s, i in zip(stock_ret, idx_ret)) / (len(stock_ret) - 1)
    var = sum((i - sum(idx_ret) / len(idx_ret)) ** 2 for i in idx_ret) / (len(idx_ret) - 1)
    return round(cov / var, 2) if var > 0 else 0.5


def calc_hedge_pl(hedges, stock_bars, index_bars):
    if not hedges or not index_bars:
        return 0.0
    total = 0.0
    for h in hedges:
        price = stock_bars[h["idx"]]["close"]
        if h["action"] == "open":
            total -= price * h["ratio"] * 0.10
        else:
            total += price * h["ratio"] * 0.10
    return total


def merge_hedge(long_trades, hedge_pl, hedges):
    result = dict(long_trades)
    result["对冲盈亏"] = round(hedge_pl, 2)
    result["对冲次数"] = len(hedges)
    result["净收益"] = round(result["total_return"] + hedge_pl, 2)
    return result


def trades_from_buys(buys, sells, bars, label):
    if not buys:
        return {"total_return": 0.0, "sharpe": 0.0, "max_drawdown": 0.0,
                "交易次数": 0, "win_rate": 0.0, "type": label}
    pairs = []
    si = 0
    for b in sorted(buys, key=lambda x: x["idx"]):
        while si < len(sells):
            if sells[si]["idx"] >= b["idx"]:
                pairs.append({"ret": (sells[si]["price"] - b["price"]) / b["price"]})
                si += 1
                break
            si += 1
    return calc_metrics(pairs, label)


def trades_from_shorts(shorts, covers, bars, label):
    if not shorts:
        return {"total_return": 0.0, "sharpe": 0.0, "max_drawdown": 0.0,
                "交易次数": 0, "win_rate": 0.0, "type": label}
    pairs = []
    ci = 0
    for s in sorted(shorts, key=lambda x: x["idx"]):
        while ci < len(covers):
            if covers[ci]["idx"] >= s["idx"]:
                pairs.append({"ret": (s["price"] - covers[ci]["price"]) / s["price"]})
                ci += 1
                break
            ci += 1
    return calc_metrics(pairs, label)


def calc_metrics(pairs, label):
    if not pairs:
        return {"total_return": 0.0, "sharpe": 0.0, "max_drawdown": 0.0,
                "交易次数": 0, "win_rate": 0.0, "type": label}
    returns = [p["ret"] for p in pairs]
    total = round(sum(returns) * 100, 2)
    eq = 1.0
    peak = 1.0
    max_dd = 0.0
    for r in returns:
        eq *= (1 + r)
        peak = max(peak, eq)
        max_dd = max(max_dd, (peak - eq) / peak)
    if len(returns) >= 2:
        mean_r = sum(returns) / len(returns)
        variance = sum((r - mean_r) ** 2 for r in returns) / (len(returns) - 1)
        std_r = math.sqrt(variance) if variance > 0 else 0
        sharpe = round(mean_r / std_r * math.sqrt(52), 2) if std_r > 0 else 0.0
    else:
        sharpe = 0.0
    wins = sum(1 for r in returns if r > 0)
    return {"total_return": total, "sharpe": sharpe, "max_drawdown": round(max_dd, 4),
            "交易次数": len(pairs), "win_rate": round(wins / len(pairs) * 100, 1), "type": label}


def run_bear_market_test(stock="000001", start="2024-01-01", end="2025-06-30"):
    os.makedirs(REPORTS_DIR, exist_ok=True)
    bars = load_bars(stock, start, end)
    if not bars:
        return {"error": "数据加载失败"}
    weekly_bars = resample_daily_to_weekly(bars)
    regime = classify_regime(bars)
    weekly_regime = classify_regime(weekly_bars)

    # 加载IF指数数据用于对冲
    index_bars = load_bars("000300", start, end)

    print(f"{'='*90}")
    print(f"  熊市策略测试: {stock} | 日线{regime['stats']} | 周线{weekly_regime['stats']}")
    print(f"{'='*90}")

    results = []
    t0 = time.time()

    for module_name, period in PERIOD_MAP.items():
        if period == "special":
            continue
        strategy = load_strategy(module_name)
        if not strategy:
            continue
        name = getattr(strategy, "NAME", module_name)
        b = weekly_bars if period == "weekly" else bars
        r = weekly_regime if period == "weekly" else regime
        params = strategy.get_param_space() if hasattr(strategy, "get_param_space") else {}
        dp = {k: v[0] if isinstance(v, tuple) else v for k, v in params.items()} if params else {}

        strat2 = load_strategy(module_name)
        strat3 = load_strategy(module_name)

        try:
            long_m = run_normal_long(strategy, b, r, dp)
            short_m = run_reverse_short(strat2, b, r, dp)
            hedge_m = run_hedge_short(strat3, b, r, dp, index_bars)
        except Exception as e:
            print(f"  [{period:6s}] {name} ❌ {e}")
            continue

        print(f"  [{period:6s}] {name} | 多头={long_m['交易次数']}笔/{long_m['total_return']:.1f}% "
              f"| 做空={short_m['交易次数']}笔/{short_m['total_return']:.1f}% "
              f"| 对冲={hedge_m.get('交易次数',0)}笔/{hedge_m.get('净收益',0):.1f}%")

        results.append({"策略": name, "周期": period,
                        "多头收益": long_m["total_return"], "多头夏普": long_m["sharpe"],
                        "多头交易": long_m["交易次数"],
                        "做空收益": short_m["total_return"], "做空夏普": short_m["sharpe"],
                        "做空交易": short_m["交易次数"],
                        "对冲收益": hedge_m.get("净收益", 0),
                        "对冲次数": hedge_m.get("对冲次数", 0)})

    elapsed = time.time() - t0

    valid = [r for r in results if r["做空交易"] > 0 or r["对冲次数"] > 0]

    print(f"\n{'='*100}")
    print(f"  🏆 熊市三种方案对比")
    print(f"{'='*100}")
    print(f"{'策略':<20} {'周期':>6} {'多头':>7} {'夏普':>7} {'做空':>7} {'夏普':>7} {'对冲':>7} {'做空笔':>7} {'对冲笔':>7}")
    print("-" * 100)
    for r in sorted(valid, key=lambda x: x["做空收益"], reverse=True):
        print(f"{r['策略']:<20} {r['周期']:>6} {r['多头收益']:>6.1f}% {r['多头夏普']:>7.2f} "
              f"{r['做空收益']:>6.1f}% {r['做空夏普']:>7.2f} {r['对冲收益']:>6.1f}% "
              f"{r['做空交易']:>7} {r['对冲次数']:>7}")

    # 汇总
    long_total = sum(r["多头收益"] for r in valid)
    short_total = sum(r["做空收益"] for r in valid)
    hedge_total = sum(r["对冲收益"] for r in valid)
    short_trades = sum(r["做空交易"] for r in valid)
    hedge_trades = sum(r["对冲次数"] for r in valid)

    print(f"\n  汇总: 多头={long_total:.1f}% | 做空={short_total:.1f}% ({short_trades}笔) | 对冲={hedge_total:.1f}% ({hedge_trades}次)")
    print(f"  熊市天数: {regime['stats']['bear']}/{regime['stats']['total']}")

    report = {"标的": stock, "区间": f"{start}-{end}", "时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
              "耗时": f"{elapsed:.1f}s", "市场状态": regime["stats"], "结果": valid}
    fp = os.path.join(REPORTS_DIR, f"bear_{stock}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(fp, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n📄 报告: {fp}")
    return report


if __name__ == "__main__":
    import sys
    stock = sys.argv[1] if len(sys.argv) > 1 else "000001"
    start = sys.argv[2] if len(sys.argv) > 2 else "2024-01-01"
    end = sys.argv[3] if len(sys.argv) > 3 else "2025-06-30"
    run_bear_market_test(stock, start, end)