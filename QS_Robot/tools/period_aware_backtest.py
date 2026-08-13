"""周期适配回测工具
将日线数据聚合为周线/分钟线，匹配策略原生周期，加入场景识别层。
"""
import os
import sys
import json
import math
import time
import logging
import importlib
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Callable

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

logging.basicConfig(level=logging.WARNING)
logging.getLogger("ths").setLevel(logging.WARNING)
logger = logging.getLogger("period_adapter")

REPORTS_DIR = os.path.join(PROJECT_ROOT, "reports", "period_aware")

# 评分模式阈值：入场条件满足率 >= 该值即触发买入
SCORE_THRESHOLD = 0.6  # 60%条件满足即入场（40%信号太杂，60%更精准）

# 策略→原生周期映射
# 策略→目标场景映射（基于原策略设计意图）
# bull: 主升浪趋势, bear: 下跌趋势, ranging: 震荡筑底
STRATEGY_REGIME_MAP = {
    "01_macd_wave": ["bull", "ranging"],          # MACD顺势：趋势+震荡
    "02_weekly_breakout": ["bull"],                # 周线突破：仅主升浪
    "03_dragon_head": ["bull"],                    # 抓龙头：涨停板环境
    "04_dragon_list_follow": ["bull", "ranging"],  # 龙虎榜跟庄：牛市+筑底
    "05_ma_long_arrangement": ["bull"],            # 多头排列：仅均线多头
    "06_expma_double_cross": ["bull", "ranging"],  # EXPMA双金叉：趋势+筑底
    "07_macd_zero_second_cross": ["bull", "ranging"],
    "08_dmi_adx_strong_trend": ["bull"],           # ADX强趋势：仅强趋势
    "09_boll_upper_breakout": ["bull"],            # BOLL突破：仅主升浪
    "10_five_day_low_suck": ["ranging"],           # 5日低吸：震荡市回踩
    "11_ten_day_wave": ["bull", "ranging"],        # 10日波段：趋势+震荡
    "12_twenty_day_lifeline": ["bull", "ranging"],
    "13_sixty_day_bull_bear": ["bull", "ranging"],
    "14_four_ma_resonance": ["bull"],              # 四线共振：仅牛市
}

STRATEGY_PERIOD_MAP = {
    "02_weekly_breakout": "weekly",       # 周线突破 → 周线
    "14_four_ma_resonance": "weekly",     # 四线共振 → 周线（MA60太大）
    "12_twenty_day_lifeline": "weekly",   # 20日生命线 → 可周线
    "13_sixty_day_bull_bear": "weekly",   # 60日牛熊 → 周线
    "10_five_day_low_suck": "daily",      # 5日线超短 → 日线（已正确）
    "11_ten_day_wave": "daily",           # 10日线波段 → 日线
    "01_macd_wave": "daily",
    "05_ma_long_arrangement": "daily",
    "06_expma_double_cross": "daily",
    "07_macd_zero_second_cross": "daily",
    "08_dmi_adx_strong_trend": "daily",
    "09_boll_upper_breakout": "daily",
    "03_dragon_head": "special",          # 需要涨停板数据
    "04_dragon_list_follow": "special",   # 需要龙虎榜数据
}


def resample_daily_to_weekly(daily_bars: list[dict]) -> list[dict]:
    """日线→周线聚合"""
    if not daily_bars:
        return []
    weeks = defaultdict(list)
    for b in daily_bars:
        d = b["date"]
        if isinstance(d, str):
            d = datetime.strptime(d[:10], "%Y-%m-%d")
        iso = d.isocalendar()
        week_key = (iso[0], iso[1])
        weeks[week_key].append(b)

    weekly = []
    for (year, wk), bars in sorted(weeks.items()):
        if len(bars) < 2:
            continue
        weekly.append({
            "date": bars[-1]["date"],
            "open": bars[0]["open"],
            "high": max(b["high"] for b in bars),
            "low": min(b["low"] for b in bars),
            "close": bars[-1]["close"],
            "volume": sum(b["volume"] for b in bars),
        })
    return weekly


def classify_regime(bars: list[dict], period: int = 60) -> dict:
    """市场状态分类：bull / bear / ranging
    返回每根bar对应的状态标签 + 整体统计
    """
    if len(bars) < period:
        return {"labels": ["unknown"] * len(bars), "stats": {"bull": 0, "bear": 0, "ranging": 0}}

    closes = [b["close"] for b in bars]
    labels = ["unknown"] * period  # 前period根无法判断

    for i in range(period, len(bars)):
        window = closes[i - period:i + 1]
        ma = sum(window) / len(window)
        ma_prev = sum(closes[i - period - 1:i]) / len(window) if i > period else ma
        price = closes[i]
        slope = (ma - ma_prev) / ma_prev if ma_prev > 0 else 0

        if price > ma and slope > 0.002:
            labels.append("bull")
        elif price < ma and slope < -0.002:
            labels.append("bear")
        else:
            labels.append("ranging")

    stats = {"bull": labels.count("bull"), "bear": labels.count("bear"),
             "ranging": labels.count("ranging"), "total": len(labels) - period}
    return {"labels": labels, "stats": stats}


def run_period_aware_batch(stock: str = "510050",
                           start: str = "2024-01-01",
                           end: str = "2025-06-30") -> dict:
    """按策略原生周期执行批量回测"""
    os.makedirs(REPORTS_DIR, exist_ok=True)

    from core.data_bus import get_data_bus
    bus = get_data_bus()
    start_dt = datetime.strptime(start, "%Y-%m-%d")
    end_dt = datetime.strptime(end, "%Y-%m-%d")
    days_needed = (end_dt - start_dt).days + 120
    kline = bus.get_kline(stock, days=min(days_needed, 2000))
    if not kline or not kline.get("dates"):
        return {"error": "数据加载失败"}

    dates = kline["dates"]
    indices = [i for i, d in enumerate(dates) if start <= str(d)[:10] <= end]
    if not indices or len(indices) < 120:
        indices = list(range(len(dates)))
    lo, hi = indices[0], indices[-1] + 1

    daily_bars = [
        {"date": kline["dates"][i], "open": float(kline["opens"][i]),
         "high": float(kline["highs"][i]), "low": float(kline["lows"][i]),
         "close": float(kline["closes"][i]), "volume": float(kline["volumes"][i])}
        for i in range(lo, hi)
    ]

    weekly_bars = resample_daily_to_weekly(daily_bars)
    daily_regime = classify_regime(daily_bars)
    weekly_regime = classify_regime(weekly_bars)

    print("=" * 70)
    print(f"  周期适配回测: {stock} | 日线{daily_regime['stats']} | 周线{weekly_regime['stats']}")
    print("=" * 70)

    results = []
    t0 = time.time()

    for module_name, native_period in STRATEGY_PERIOD_MAP.items():
        if native_period == "special":
            results.append({"策略": module_name, "周期": "special", "状态": "跳过(需特殊数据)"})
            continue

        strategy = _load_strategy(module_name)
        if not strategy:
            results.append({"策略": module_name, "周期": native_period, "状态": "加载失败"})
            continue

        name = getattr(strategy, "NAME", module_name)
        bars = weekly_bars if native_period == "weekly" else daily_bars
        regime = weekly_regime if native_period == "weekly" else daily_regime

        print(f"  [{native_period:6s}] {name} ({len(bars)}条) ...", end=" ", flush=True)

        try:
            # 原始AND模式
            perf_and = _evaluate(strategy, bars, regime, scoring=False)
            # 加载新实例（避免状态污染），跑评分模式
            strat2 = _load_strategy(module_name)
            perf_score = _evaluate(strat2, bars, regime, scoring=True) if strat2 else perf_and

            entry = {
                "策略": name, "ID": module_name,
                "原生周期": native_period,
                "数据量": len(bars),
                "AND交易": perf_and["trades"],
                "AND收益%": perf_and["total_return"],
                "AND夏普": perf_and["sharpe"],
                "评分交易": perf_score["trades"],
                "评分收益%": perf_score["total_return"],
                "评分夏普": perf_score["sharpe"],
                "评分信号": perf_score.get("scored", 0),
                "牛市信号": perf_score["bull_signals"],
                "熊市信号": perf_score["bear_signals"],
                "震荡信号": perf_score["ranging_signals"],
                "结论": perf_score["conclusion"],
            }
            results.append(entry)
            delta = perf_score["trades"] - perf_and["trades"]
            print(f"✅ AND={perf_and['trades']}笔/{perf_and['total_return']:.1f}% → "
                  f"评分={perf_score['trades']}笔/{perf_score['total_return']:.1f}% "
                  f"(+{delta}笔 评分信号={perf_score.get('scored',0)})")
        except Exception as e:
            print(f"❌ {e}")
            results.append({"策略": name, "周期": native_period, "状态": f"异常: {e}"})

    elapsed = time.time() - t0

    valid = [r for r in results if "AND收益%" in r]
    valid.sort(key=lambda r: r["评分夏普"], reverse=True)

    report = {
        "标的": stock, "区间": f"{start}~{end}",
        "时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "耗时": f"{elapsed:.1f}s",
        "日线统计": daily_regime["stats"],
        "周线统计": weekly_regime["stats"],
        "日线K线": len(daily_bars),
        "周线K线": len(weekly_bars),
        "结果": valid,
    }
    fp = os.path.join(REPORTS_DIR, f"period_aware_{stock}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(fp, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)

    print(f"\n{'='*90}")
    print(f"  🏆 AND vs 评分制 对比 (阈值≥{int(SCORE_THRESHOLD*100)}%条件满足)")
    print(f"{'='*90}")
    print(f"{'策略':<20} {'周期':>6} {'AND':>5} {'AND%':>7} {'评分':>6} {'评分%':>7} {'夏普':>7} {'评分信号':>8} {'结论'}")
    print("-" * 90)
    for r in valid:
        print(f"{r['策略']:<20} {r['原生周期']:>6} {r['AND交易']:>5} {r['AND收益%']:>6.1f}% "
              f"{r['评分交易']:>6} {r['评分收益%']:>6.1f}% {r['评分夏普']:>7.2f} "
              f"{r['评分信号']:>8}  {r['结论']}")

    and_total = sum(r["AND交易"] for r in valid)
    score_total = sum(r["评分交易"] for r in valid)
    print(f"\n  汇总: AND={and_total}笔 | 评分={score_total}笔 | +{score_total-and_total}笔\n")

    print(f"\n📄 报告: {fp}")
    return report


def _load_strategy(module_name: str):
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


def _evaluate(strategy, bars: list, regime: dict, scoring: bool = False) -> dict:
    """评估策略表现
    scoring=True: 使用评分制（≥40%条件满足即入场）
    scoring=False: 使用原始AND逻辑
    """
    params = strategy.get_param_space() if hasattr(strategy, "get_param_space") else {}
    default_params = {k: v[0] if isinstance(v, tuple) else v for k, v in params.items()} if params else {}

    sid = getattr(strategy, "ID", "")
    allowed_regimes = STRATEGY_REGIME_MAP.get(sid, ["bull", "ranging"])

    buys, sells = [], []
    labels = regime.get("labels", [])
    bull_sigs = bear_sigs = ranging_sigs = 0
    scored_sigs = 0
    skipped_by_regime = 0

    for i in range(len(bars)):
        if i < 60:
            continue
        window = bars[:i + 1]
        label = labels[i] if i < len(labels) else "unknown"

        if label not in allowed_regimes and label != "unknown":
            skipped_by_regime += 1
            continue

        try:
            sig = strategy.generate_signal(window, default_params)
        except Exception:
            continue

        # 评分模式：原始信号为None时，检查条件满足率
        if sig is None and scoring:
            conditions = getattr(strategy, "_last_entry_conditions", {})
            if conditions:
                total = len(conditions)
                passed = sum(1 for v in conditions.values() if v)
                score = passed / total if total > 0 else 0
                if score >= SCORE_THRESHOLD:
                    sig = {"action": "buy", "price": bars[i]["close"],
                           "stop_loss": bars[i]["close"] * 0.95,
                           "take_profit": bars[i]["close"] * 1.10,
                           "reason": f"scored({passed}/{total})"}
                    scored_sigs += 1

        if sig is None:
            continue
        entry = {"日期": str(bars[i]["date"])[:10], "价格": sig.get("price", bars[i]["close"])}
        if sig.get("action") == "buy":
            buys.append(entry)
            if label == "bull":
                bull_sigs += 1
            elif label == "bear":
                bear_sigs += 1
            else:
                ranging_sigs += 1
        elif sig.get("action") == "sell":
            sells.append(entry)

    trades = _pair_trades(buys, sells, bars)
    metrics = _calc_metrics(trades)

    if metrics["交易次数"] == 0:
        conclusion = "无信号"
    elif metrics["sharpe"] > 0 and metrics["max_drawdown"] < 0.35:
        conclusion = "适配"
    else:
        conclusion = "条件适配"

    metrics["trades"] = metrics["交易次数"]
    metrics["bull_signals"] = bull_sigs
    metrics["bear_signals"] = bear_sigs
    metrics["ranging_signals"] = ranging_sigs
    metrics["scored"] = scored_sigs
    metrics["skipped"] = skipped_by_regime
    metrics["allowed_regimes"] = ",".join(allowed_regimes)
    metrics["conclusion"] = conclusion
    return metrics


def _pair_trades(buys, sells, bars):
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


def _calc_metrics(trades):
    if not trades:
        return {"total_return": 0.0, "max_drawdown": 0.0, "sharpe": 0.0, "交易次数": 0, "win_rate": 0.0}
    returns = [t["ret"] for t in trades]
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
    return {
        "total_return": total,
        "max_drawdown": round(max_dd, 4),
        "sharpe": sharpe,
        "交易次数": len(trades),
        "win_rate": round(wins / len(trades) * 100, 1),
    }


if __name__ == "__main__":
    stock = sys.argv[1] if len(sys.argv) > 1 else "510050"
    start = sys.argv[2] if len(sys.argv) > 2 else "2024-01-01"
    end = sys.argv[3] if len(sys.argv) > 3 else "2025-06-30"
    run_period_aware_batch(stock, start, end)