"""14个同花顺策略批量审查 + 排行榜
一键运行：python tools/batch_review.py [股票代码] [起始日期] [结束日期]
默认：000001 2024-01-01 2025-06-30
"""
import os
import sys
import json
import math
import time
import random
import logging
import importlib
from datetime import datetime, timedelta
from typing import Any

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

logging.basicConfig(level=logging.WARNING, format="%(asctime)s [%(name)s] %(levelname)s - %(message)s")
logger = logging.getLogger("batch_review")
logging.getLogger("ths").setLevel(logging.WARNING)

REPORTS_DIR = os.path.join(PROJECT_ROOT, "reports", "batch")

STRATEGY_FILES = [
    "01_macd_wave", "02_weekly_breakout", "03_dragon_head",
    "04_dragon_list_follow", "05_ma_long_arrangement", "06_expma_double_cross",
    "07_macd_zero_second_cross", "08_dmi_adx_strong_trend", "09_boll_upper_breakout",
    "10_five_day_low_suck", "11_ten_day_wave", "12_twenty_day_lifeline",
    "13_sixty_day_bull_bear", "14_four_ma_resonance",
]

random.seed(42)


def main():
    os.makedirs(REPORTS_DIR, exist_ok=True)
    stock = sys.argv[1] if len(sys.argv) > 1 else "000001"
    start = sys.argv[2] if len(sys.argv) > 2 else "2024-01-01"
    end = sys.argv[3] if len(sys.argv) > 3 else "2025-06-30"

    print("=" * 70)
    print(f"  同花顺14策略批量审查: {stock} {start}~{end}")
    print("=" * 70)

    bars = _load_bars(stock, start, end)
    if not bars:
        print("❌ 数据加载失败")
        return
    print(f"K线数据: {len(bars)}条\n")

    results = []
    t0 = time.time()

    for i, module_name in enumerate(STRATEGY_FILES):
        strategy = _load_strategy(module_name)
        if not strategy:
            results.append({"策略": module_name, "状态": "加载失败"})
            continue

        name = getattr(strategy, "NAME", module_name)
        print(f"[{i+1:2d}/14] {name} ...", end=" ", flush=True)

        try:
            # 审查
            review = _run_review(strategy, bars)
            # 过拟合
            overfit = _run_overfit(strategy, bars)
            entry = {
                "排名": 0, "策略": name, "ID": module_name,
                "交易次数": review["交易次数"],
                "累计收益%": review["累计收益"],
                "最大回撤": review["最大回撤"],
                "夏普比率": review["夏普比率"],
                "胜率%": review["胜率"],
                "过拟合分": overfit["风险分"],
                "过拟合结论": overfit["结论"],
                "审查结论": review["结论"],
                "信号总数": review["信号总数"],
                "买入": review["买入"],
                "卖出": review["卖出"],
                "边界_涨停": review.get("边界_涨停", "N/A"),
                "边界_跌停": review.get("边界_跌停", "N/A"),
                "边界_波动": review.get("边界_波动", "N/A"),
            }
            results.append(entry)
            print(f"✅ 收益={review['累计收益']:.1f}% 夏普={review['夏普比率']:.2f} 交易={review['交易次数']} 过拟合={overfit['风险分']:.0f}")
        except Exception as e:
            print(f"❌ {e}")
            results.append({"策略": name, "ID": module_name, "状态": f"异常: {e}"})

    elapsed = time.time() - t0

    # 排序
    valid = [r for r in results if "夏普比率" in r]
    valid.sort(key=lambda r: r["夏普比率"], reverse=True)
    for rank, r in enumerate(valid, 1):
        r["排名"] = rank

    # 保存
    report = {
        "股票": stock, "区间": f"{start}~{end}",
        "审查时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "总耗时": f"{elapsed:.1f}s",
        "策略数": len(valid),
        "排行榜": valid,
    }
    fp = os.path.join(REPORTS_DIR, f"batch_{stock}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(fp, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)

    # 打印排行榜
    print(f"\n{'='*70}")
    print(f"  🏆 策略排行榜 (按夏普排序) - 耗时 {elapsed:.1f}s")
    print(f"{'='*70}")
    print(f"{'排名':<4} {'策略':<20} {'收益%':>8} {'回撤':>8} {'夏普':>7} {'交易':>5} {'胜率':>6} {'过拟合':>6} {'结论'}")
    print("-" * 70)
    for r in valid:
        ofit = f"{r['过拟合分']:.0f}"
        print(f"{r['排名']:<4} {r['策略']:<20} {r['累计收益%']:>7.1f}% {r['最大回撤']:>7.1f}% {r['夏普比率']:>7.2f} {r['交易次数']:>5} {r['胜率%']:>5.0f}% {ofit:>5}  {r['审查结论']}")

    print(f"\n📄 报告: {fp}")


def _load_bars(stock: str, start: str, end: str) -> list[dict] | None:
    from core.data_bus import get_data_bus
    bus = get_data_bus()
    start_dt = datetime.strptime(start, "%Y-%m-%d")
    end_dt = datetime.strptime(end, "%Y-%m-%d")
    days_needed = (end_dt - start_dt).days + 60
    kline = bus.get_kline(stock, days=min(days_needed, 2000))
    if not kline or not kline.get("dates"):
        return None
    dates = kline["dates"]
    indices = [i for i, d in enumerate(dates) if start <= str(d)[:10] <= end]
    if not indices or len(indices) < 120:
        # 数据不足时用全部可用数据
        indices = list(range(len(dates)))
    lo, hi = indices[0], indices[-1] + 1
    return [
        {"date": kline["dates"][i], "open": float(kline["opens"][i]),
         "high": float(kline["highs"][i]), "low": float(kline["lows"][i]),
         "close": float(kline["closes"][i]), "volume": float(kline["volumes"][i])}
        for i in range(lo, hi)
    ]


def _load_strategy(module_name: str):
    try:
        mod = importlib.import_module(f"core.strategies.ths_strategies.14_strategies.{module_name}")
        cls_name = _find_strategy_class(mod)
        if cls_name:
            return getattr(mod, cls_name)()
    except Exception as e:
        logger.warning("加载 %s 失败: %s", module_name, e)
    return None


def _find_strategy_class(mod) -> str | None:
    import inspect
    from core.strategies.ths_strategies.base import THSBaseStrategy
    for name, obj in inspect.getmembers(mod, inspect.isclass):
        if issubclass(obj, THSBaseStrategy) and obj is not THSBaseStrategy:
            return name
    return None


def _run_review(strategy, bars: list) -> dict:
    params = strategy.get_param_space() if hasattr(strategy, "get_param_space") else {}
    default_params = {k: v[0] if isinstance(v, tuple) else v for k, v in params.items()} if params else {}

    buys, sells = [], []
    for i in range(len(bars)):
        window = bars[:i + 1]
        try:
            sig = strategy.generate_signal(window, default_params)
        except Exception:
            continue
        if sig is None:
            continue
        entry = {"日期": str(bars[i]["date"])[:10], "价格": sig.get("price", bars[i]["close"])}
        if sig.get("action") == "buy":
            buys.append(entry)
        elif sig.get("action") == "sell":
            sells.append(entry)

    trades = _pair_trades(buys, sells, bars)
    metrics = _calc_metrics(trades)

    # 边界场景
    edge = _test_edge(strategy, bars, default_params)

    # 结论
    if metrics["交易次数"] == 0:
        conclusion = "无交易信号"
    elif metrics["夏普比率"] > 0 and metrics["最大回撤"] < 0.35:
        conclusion = "适配该标的"
    else:
        conclusion = "条件适配"

    return {
        "信号总数": len(buys) + len(sells),
        "买入": len(buys), "卖出": len(sells),
        "交易次数": metrics["交易次数"],
        "累计收益": metrics["累计收益"],
        "最大回撤": metrics["最大回撤"],
        "夏普比率": metrics["夏普比率"],
        "胜率": metrics["胜率"],
        "结论": conclusion,
        "边界_涨停": edge.get("涨停", "N/A"),
        "边界_跌停": edge.get("跌停", "N/A"),
        "边界_波动": edge.get("波动", "N/A"),
    }


def _pair_trades(buys: list, sells: list, bars: list) -> list:
    trades = []
    prices = {str(b["date"])[:10]: b["close"] for b in bars}
    sorted_sells = sorted(sells, key=lambda s: s["日期"])
    si = 0
    for buy in sorted(buys, key=lambda b: b["日期"]):
        bd = str(buy["日期"])[:10]
        bp = buy.get("价格") or prices.get(bd, 0)
        if not bp:
            continue
        while si < len(sorted_sells):
            s = sorted_sells[si]
            sd = str(s["日期"])[:10]
            if sd >= bd:
                sp = s.get("价格") or prices.get(sd, bp)
                trades.append({"ret": (sp - bp) / bp})
                si += 1
                break
            si += 1
    return trades


def _calc_metrics(trades: list) -> dict:
    if not trades:
        return {"累计收益": 0.0, "最大回撤": 0.0, "夏普比率": 0.0, "交易次数": 0, "胜率": 0.0}
    returns = [t["ret"] for t in trades]
    total = sum(returns)
    eq = 1.0
    peak = 1.0
    max_dd = 0.0
    for r in returns:
        eq *= (1 + r)
        peak = max(peak, eq)
        max_dd = max(max_dd, (peak - eq) / peak)
    if len(returns) >= 2:
        mean_r = total / len(returns)
        variance = sum((r - mean_r) ** 2 for r in returns) / (len(returns) - 1)
        std_r = math.sqrt(variance) if variance > 0 else 0
        sharpe = (mean_r / std_r * math.sqrt(252)) if std_r > 0 else 0
    else:
        sharpe = 0.0
    wins = sum(1 for r in returns if r > 0)
    return {
        "累计收益": round(total * 100, 2),
        "最大回撤": round(max_dd, 4),
        "夏普比率": round(sharpe, 2),
        "交易次数": len(trades),
        "胜率": round(wins / len(trades) * 100, 1),
    }


def _test_edge(strategy, bars: list, params: dict) -> dict:
    if len(bars) < 30:
        return {}
    last = bars[-1]
    result = {}

    # 涨停
    limit_up = dict(last)
    limit_up["open"] = limit_up["high"] = limit_up["low"] = limit_up["close"] = round(last["close"] * 1.10, 2)
    limit_up["volume"] = last["volume"] * 0.1
    try:
        sig = strategy.generate_signal(bars + [limit_up] * 3, params)
        result["涨停"] = sig.get("action", "无信号") if sig else "无信号"
    except Exception:
        result["涨停"] = "异常"

    # 跌停
    limit_down = dict(last)
    limit_down["open"] = limit_down["high"] = limit_down["low"] = limit_down["close"] = round(last["close"] * 0.90, 2)
    limit_down["volume"] = last["volume"] * 0.1
    try:
        sig = strategy.generate_signal(bars + [limit_down] * 3, params)
        result["跌停"] = sig.get("action", "无信号") if sig else "无信号"
    except Exception:
        result["跌停"] = "异常"

    # 大幅波动
    vb = list(bars)
    for pct in [1.05, 0.92, 1.08]:
        b = vb[-1].copy()
        b["close"] = round(b["close"] * pct, 2)
        b["high"] = round(b["close"] * 1.03, 2)
        b["low"] = round(b["close"] * 0.97, 2)
        vb.append(b)
    try:
        sig = strategy.generate_signal(vb, params)
        result["波动"] = sig.get("action", "无信号") if sig else "无信号"
    except Exception:
        result["波动"] = "异常"

    return result


def _run_overfit(strategy, bars: list) -> dict:
    param_space = strategy.get_param_space()
    default_params = {k: v[0] if isinstance(v, tuple) else v for k, v in param_space.items()}
    baseline = _evaluate(strategy, bars, default_params)

    if baseline["trades"] == 0:
        return {"风险分": 0, "结论": "无交易"}

    scores = []
    for level_name, level_val in [("5%", 0.05), ("10%", 0.10), ("20%", 0.20)]:
        level_rets = []
        for _ in range(5):
            perturbed = _perturb(default_params, param_space, level_val)
            perf = _evaluate(strategy, bars, perturbed)
            level_rets.append(perf["total_return"])
        avg = sum(level_rets) / len(level_rets)
        scores.append(avg)

    # 评估衰减
    base_ret = baseline["total_return"]
    risk = 0
    for level, avg in zip([0.05, 0.10, 0.20], scores):
        if base_ret != 0:
            drop = (base_ret - avg) / abs(base_ret)
            if drop > 0.5:
                risk += 3
            elif drop > 0.2:
                risk += 1.5

    risk = min(risk, 10)
    if risk < 2:
        conclusion = "鲁棒"
    elif risk < 5:
        conclusion = "敏感"
    elif risk < 7:
        conclusion = "过拟合"
    else:
        conclusion = "严重过拟合"

    return {"风险分": round(risk, 1), "结论": conclusion}


def _evaluate(strategy, bars: list, params: dict) -> dict:
    buys, sells = [], []
    for i in range(len(bars)):
        window = bars[:i + 1]
        try:
            sig = strategy.generate_signal(window, params)
        except Exception:
            continue
        if sig is None:
            continue
        if sig.get("action") == "buy":
            buys.append({"日期": str(bars[i]["date"])[:10], "价格": sig.get("price", bars[i]["close"])})
        elif sig.get("action") == "sell":
            sells.append({"日期": str(bars[i]["date"])[:10], "价格": sig.get("price", bars[i]["close"])})
    trades = _pair_trades(buys, sells, bars)
    if not trades:
        return {"total_return": 0.0, "trades": 0}
    returns = [t["ret"] for t in trades]
    return {"total_return": sum(returns), "trades": len(trades)}


def _perturb(default_params: dict, param_space: dict, level: float) -> dict:
    result = {}
    for key, val in default_params.items():
        if key not in param_space:
            result[key] = val
            continue
        low, high = param_space[key]
        delta = val * level * random.uniform(-1, 1)
        new_val = val + delta
        if isinstance(low, int) and isinstance(high, int):
            new_val = round(new_val)
        new_val = max(low, min(high, new_val))
        if isinstance(low, int):
            new_val = int(new_val)
        result[key] = new_val
    return result


if __name__ == "__main__":
    main()