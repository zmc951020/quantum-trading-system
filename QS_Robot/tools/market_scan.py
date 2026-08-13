"""全市场扫描器：ALL-AND逻辑 + 排列优选
原策略设计：5000+股票海选 → 交集条件筛选 → 0-10只通过
周期：日线
"""
import os, sys, json, math, time, logging, importlib, inspect
from datetime import datetime
from collections import defaultdict

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
logging.basicConfig(level=logging.WARNING)
logging.getLogger("ths").setLevel(logging.WARNING)

REPORTS_DIR = os.path.join(PROJECT_ROOT, "reports", "market_scan")


def load_cached_stocks(min_bars=200):
    """从本地缓存加载所有股票数据"""
    cache_dir = os.path.join(PROJECT_ROOT, "data", "bus_cache")
    if not os.path.exists(cache_dir):
        return {}
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
    """将缓存数据转为bar列表"""
    n = len(data["dates"])
    return [{"date": data["dates"][i], "open": float(data["opens"][i]),
             "high": float(data["highs"][i]), "low": float(data["lows"][i]),
             "close": float(data["closes"][i]), "volume": float(data["volumes"][i])}
            for i in range(n)]


def load_strategies():
    """加载所有策略"""
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


def scan_all(bars, strategies, strategy_instances):
    """全市场扫描：ALL-AND逻辑
    对每根bar，逐个策略检查：所有条件同时满足 → 信号
    返回: {策略名: [(日期, 价格, 条件数), ...]}
    """
    results = defaultdict(list)
    for i in range(60, len(bars)):
        for mod_name, strategy in strategies:
            try:
                sig = strategy.generate_signal(bars[:i + 1], {})
                if sig is not None and sig.get("action") == "buy":
                    conds = getattr(strategy, "_last_entry_conditions", {})
                    cond_count = len(conds)
                    passed = sum(1 for v in conds.values() if v)
                    results[mod_name].append({
                        "date": str(bars[i]["date"])[:10],
                        "price": round(bars[i]["close"], 2),
                        "conditions": cond_count,
                        "passed": passed,
                    })
            except Exception:
                pass
    return results


def run_full_scan(max_stocks=0):
    """主流程：加载缓存 → 逐股扫描 → 排序输出
    max_stocks: 0=全部, >0=限制数量
    """
    t0 = time.time()
    print("加载缓存数据...", flush=True)
    stocks = load_cached_stocks(min_bars=200)
    print(f"  可用股票: {len(stocks)} 只", flush=True)
    
    if max_stocks > 0:
        stocks = dict(list(stocks.items())[:max_stocks])
        print(f"  限制扫描: {max_stocks} 只", flush=True)

    print("加载策略...", flush=True)
    strategy_list = load_strategies()
    print(f"  策略: {len(strategy_list)} 个", flush=True)

    # 统计
    all_results = []
    total_signals = 0
    stocks_with_signal = 0

    for idx, (code, data) in enumerate(stocks.items()):
        bars = build_bars(data)
        # 每个股票用独立策略实例
        fresh_strats = [(n, s.__class__()) for n, s in strategy_list]
        results = scan_all(bars, fresh_strats, None)

        if idx % 20 == 0:
            elapsed = time.time() - t0
            print(f"  [{idx+1}/{len(stocks)}] {code} | {elapsed:.0f}s", flush=True)

        stock_signals = []
        for mod_name, signals in results.items():
            if signals:
                name = getattr(
                    {n: s for n, s in strategy_list}.get(mod_name, None),
                    "NAME", mod_name)
                stock_signals.append({
                    "策略": name, "信号数": len(signals),
                    "日期范围": f"{signals[0]['date']} ~ {signals[-1]['date']}",
                })
                total_signals += len(signals)

        if stock_signals:
            stocks_with_signal += 1
            # 按信号数排序
            stock_signals.sort(key=lambda x: x["信号数"], reverse=True)
            all_results.append({
                "代码": code, "信号": stock_signals,
                "总信号": sum(s["信号数"] for s in stock_signals),
                "策略数": len(stock_signals),
                "K线": len(bars),
            })

    elapsed = time.time() - t0

    # 按总信号数排序
    all_results.sort(key=lambda x: x["总信号"], reverse=True)

    print(f"\n{'='*90}")
    print(f"  全市场扫描结果（ALL-AND逻辑，{len(stocks)}只股票）")
    print(f"{'='*90}")
    print(f"{'排名':<4} {'代码':<8} {'总信号':>5} {'策略数':>5} {'K线':>5} {'TOP策略':<30}")
    print("-" * 70)

    for rank, r in enumerate(all_results[:30], 1):
        top_strat = r["信号"][0]["策略"] if r["信号"] else ""
        print(f"{rank:<4} {r['代码']:<8} {r['总信号']:>5} {r['策略数']:>5} {r['K线']:>5} {top_strat:<30}")

    print(f"\n  总计: {stocks_with_signal}/{len(stocks)}只股票产生信号, {total_signals}个信号")
    print(f"  耗时: {elapsed:.1f}s")

    # 策略汇总
    strat_summary = defaultdict(lambda: {"信号": 0, "股票": set()})
    for r in all_results:
        for s in r["信号"]:
            strat_summary[s["策略"]]["信号"] += s["信号数"]
            strat_summary[s["策略"]]["股票"].add(r["代码"])

    print(f"\n{'─'*60}")
    print(f"  策略维度汇总")
    print(f"{'─'*60}")
    print(f"{'策略':<20} {'信号':>5} {'股票':>5} {'日均':>6}")
    print("-" * 40)
    for name, d in sorted(strat_summary.items(), key=lambda x: x[1]["信号"], reverse=True):
        avg = round(d["信号"] / len(stocks), 1)
        print(f"{name:<20} {d['信号']:>5} {len(d['股票']):>5} {avg:>6.1f}")

    # 保存报告
    os.makedirs(REPORTS_DIR, exist_ok=True)
    report = {
        "时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "股票数": len(stocks),
        "有信号股票": stocks_with_signal,
        "总信号": total_signals,
        "耗时": f"{elapsed:.1f}s",
        "排名": all_results[:50],
        "策略汇总": {k: {"信号": v["信号"], "股票": len(v["股票"])}
                     for k, v in strat_summary.items()},
    }
    fp = os.path.join(REPORTS_DIR, f"scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(fp, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n📄 报告: {fp}")

    return report


if __name__ == "__main__":
    import sys
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    run_full_scan(max_stocks=limit)