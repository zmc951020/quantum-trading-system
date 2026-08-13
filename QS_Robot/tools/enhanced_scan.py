"""优化底座扫描：评分排名替代二值过滤
低位(0-5) + 热启动(0-3) = 综合分(0-8)，按平均分排名
"""
import os, sys, json, time, importlib, inspect
from datetime import datetime
from collections import defaultdict

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from tools.regime_judge import load_index_data, get_regime_series, get_regime_for_date
from tools.low_position_filter import calc_composite_score


def load_cached_stocks(min_bars=200):
    cache_dir = os.path.join(PROJECT_ROOT, "data", "bus_cache")
    stocks = {}
    for fname in os.listdir(cache_dir):
        if not fname.endswith(".json"):
            continue
        try:
            with open(os.path.join(cache_dir, fname), encoding="utf-8") as f:
                d = json.load(f)
            data = d.get("data", {})
            if isinstance(data, dict) and len(data.get("dates", [])) >= min_bars:
                code = data.get("symbol", "")
                if code:
                    stocks[code] = data
        except Exception:
            pass
    return stocks


def build_bars(data):
    n = len(data["dates"])
    return [{"date": data["dates"][i], "open": float(data["opens"][i]),
             "high": float(data["highs"][i]), "low": float(data["lows"][i]),
             "close": float(data["closes"][i]), "volume": float(data["volumes"][i])}
            for i in range(n)]


def load_strategies():
    from core.strategies.ths_strategies.base import THSBaseStrategy
    strats = []
    strat_dir = os.path.join(PROJECT_ROOT, "core", "strategies", "ths_strategies", "14_strategies")
    for fname in sorted(os.listdir(strat_dir)):
        if not fname.endswith(".py") or not fname[0].isdigit():
            continue
        mod_name = fname.replace(".py", "")
        try:
            mod = importlib.import_module(f"core.strategies.ths_strategies.14_strategies.{mod_name}")
            for n, obj in inspect.getmembers(mod, inspect.isclass):
                if (issubclass(obj, THSBaseStrategy) and obj is not THSBaseStrategy
                        and obj.__module__ == mod.__name__):
                    strats.append((mod_name, obj()))
                    break
        except Exception:
            pass
    return strats


def scan_original(bars, strategies):
    results = defaultdict(list)
    for i in range(60, len(bars)):
        for mod_name, strategy in strategies:
            try:
                sig = strategy.generate_signal(bars[:i + 1], {})
                if sig is not None and sig.get("action") == "buy":
                    results[mod_name].append({"date": bars[i]["date"],
                        "price": sig.get("price", bars[i]["close"])})
            except Exception:
                pass
    return dict(results)


def scan_with_scores(bars, strategies, regimes):
    """评分扫描: 每个信号计算低位分+热启动分+大盘环境
    返回: (信号列表, 统计)
    """
    signals = []
    stats = {"total": 0, "regime_blocked": 0, "low_zero": 0, "by_score": defaultdict(int)}
    score_sum = 0

    for i in range(60, len(bars)):
        date = bars[i]["date"]
        regime = get_regime_for_date(regimes, date)

        for mod_name, strategy in strategies:
            try:
                sig = strategy.generate_signal(bars[:i + 1], {})
                if sig is None or sig.get("action") != "buy":
                    continue
                stats["total"] += 1

                if regime["position_limit"] <= 0.3:
                    stats["regime_blocked"] += 1
                    continue

                low_s, low_d, hot_s, hot_d, comp = calc_composite_score(bars, i)
                if low_s == 0:
                    stats["low_zero"] += 1
                    continue

                stats["by_score"][comp] += 1
                score_sum += comp
                signals.append({
                    "date": date,
                    "strategy": mod_name,
                    "price": sig.get("price", bars[i]["close"]),
                    "low_score": low_s, "low_details": low_d,
                    "hot_score": hot_s, "hot_details": hot_d,
                    "composite": comp,
                    "regime": regime["label"],
                })
            except Exception:
                pass

    stats["avg_score"] = round(score_sum / max(len(signals), 1), 2)
    stats["signal_count"] = len(signals)
    return signals, stats


def main(max_stocks=0, min_score=0):
    print("加载数据...", flush=True)
    stocks = load_cached_stocks()
    if max_stocks > 0:
        stocks = dict(list(stocks.items())[:max_stocks])
    print(f"  股票: {len(stocks)} 只", flush=True)

    print("加载策略...", flush=True)
    strategies = load_strategies()
    print(f"  策略: {len(strategies)} 个", flush=True)

    print("加载大盘环境...", flush=True)
    index_bars = load_index_data("000300")
    regimes = get_regime_series(index_bars) if index_bars else []
    print(f"  大盘数据: {len(regimes)} 天", flush=True)

    t0 = time.time()
    stock_rankings = []
    total_original = 0
    total_scored = 0
    total_regime = 0
    total_low_zero = 0
    all_scores = defaultdict(int)

    for idx, (code, data) in enumerate(stocks.items()):
        bars = build_bars(data)
        orig = scan_original(bars, strategies)
        signals, stats = scan_with_scores(bars, strategies, regimes)

        o_count = sum(len(v) for v in orig.values())
        total_original += o_count
        total_scored += stats["signal_count"]
        total_regime += stats["regime_blocked"]
        total_low_zero += stats["low_zero"]

        for s, c in stats["by_score"].items():
            all_scores[s] += c

        if stats["signal_count"] > 0:
            stock_rankings.append({
                "code": code, "original": o_count, "scored": stats["signal_count"],
                "avg_score": stats["avg_score"], "score_dist": dict(stats["by_score"]),
            })

        if (idx + 1) % 20 == 0:
            elapsed = time.time() - t0
            print(f"  [{idx+1}/{len(stocks)}] {code} orig={o_count} scored={stats['signal_count']} avg={stats['avg_score']} | {elapsed:.0f}s", flush=True)

    elapsed = time.time() - t0

    # 按平均分降序，同分按信号数降序
    stock_rankings.sort(key=lambda x: (x["avg_score"], x["scored"]), reverse=True)

    print(f"\n{'='*85}")
    print(f"  评分排名 ({len(stocks)}只股票, {elapsed:.0f}s)")
    print(f"{'='*85}")
    print(f"  原始ALL-AND:  {total_original:>8,}")
    print(f"  评分后(L≥1): {total_scored:>8,}  ({total_scored/max(total_original,1)*100:.1f}%)")
    print(f"  过滤: 大盘{total_regime:,} + 非低位{total_low_zero:,}")

    print(f"\n  综合分分布 (低位0-5 + 热启动0-3 = 0-8):")
    print(f"  {'得分':<6}{'信号数':>8}{'占比':>8}{'累计':>8}{'评级'}")
    cum = 0
    for s in range(8, -1, -1):
        c = all_scores.get(s, 0)
        cum += c
        pct = f"{c/max(total_scored,1)*100:.1f}%"
        cum_pct = f"{cum/max(total_scored,1)*100:.1f}%"
        label = "★★★" if s >= 6 else "★★" if s >= 4 else "★" if s >= 2 else ""
        if c > 0:
            print(f"  {s:<6}{c:>8,}{pct:>8}{cum_pct:>8}  {label}")

    print(f"\n  {'排名':<6}{'代码':<10}{'原始':>7}{'评分':>7}{'平均分':>8}{'得分分布':>20}")
    print(f"  {'-'*60}")
    for rank, r in enumerate(stock_rankings[:25], 1):
        dist = ",".join(f"{s}:{c}" for s, c in sorted(r["score_dist"].items(), reverse=True)[:3])
        print(f"  {rank:<6}{r['code']:<10}{r['original']:>7,}{r['scored']:>7,}{r['avg_score']:>8.1f}  {dist:<20}")

    if min_score > 0:
        filtered = [r for r in stock_rankings if r["avg_score"] >= min_score]
        print(f"\n  平均分>= {min_score}: {len(filtered)}只股票, {sum(r['scored'] for r in filtered):,}个信号")

    # 保存报告
    report = {
        "scan_time": datetime.now().isoformat(),
        "stock_count": len(stocks),
        "original_signals": total_original,
        "scored_signals": total_scored,
        "filter_detail": {"regime_blocked": total_regime, "low_zero": total_low_zero},
        "score_distribution": dict(all_scores),
        "stock_rankings": stock_rankings,
    }
    report_dir = os.path.join(PROJECT_ROOT, "reports", "optimized_scan")
    os.makedirs(report_dir, exist_ok=True)
    report_path = os.path.join(report_dir, f"scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n  报告: {report_path}")


if __name__ == "__main__":
    import sys
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    min_s = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    main(n, min_s)