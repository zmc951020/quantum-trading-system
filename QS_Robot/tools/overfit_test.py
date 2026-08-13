"""策略过拟合扰动测试
对策略参数进行 ±5%/±10%/±20% 随机扰动，验证性能是否平滑衰减。
若小幅扰动导致性能剧烈恶化 → 过拟合风险高。

用法：
    python tools/overfit_test.py --mock
    python tools/overfit_test.py 000001 2024-01-01 2025-06-30
"""
import os
import sys
import math
import random
import logging
from datetime import datetime, timedelta
from typing import Any

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

logging.basicConfig(level=logging.WARNING, format="%(asctime)s [%(name)s] %(levelname)s - %(message)s")
logger = logging.getLogger("overfit_test")
# 抑制策略内部日志
logging.getLogger("ths").setLevel(logging.WARNING)

REPORTS_DIR = os.path.join(PROJECT_ROOT, "reports", "overfit")


def run_overfit_test(strategy, stock_code: str, start_date: str, end_date: str,
                     perturbation_levels: list[float] = None) -> dict:
    """对策略执行参数扰动测试，检测过拟合风险"""
    if perturbation_levels is None:
        perturbation_levels = [0.05, 0.10, 0.20]

    os.makedirs(REPORTS_DIR, exist_ok=True)
    name = getattr(strategy, "NAME", strategy.__class__.__name__)
    logger.info("=" * 50)
    logger.info("🔬 过拟合扰动测试: %s 股票=%s", name, stock_code)

    # 加载数据
    kline = _load_data(stock_code, start_date, end_date)
    if not kline or kline.get("error"):
        return {"error": kline.get("error", "数据加载失败")}

    bars = _to_bars(kline)
    logger.info("数据: %d条K线 %s~%s", len(bars), str(bars[0]["date"])[:10], str(bars[-1]["date"])[:10])

    param_space = strategy.get_param_space()
    default_params = {k: v[0] if isinstance(v, tuple) else v for k, v in param_space.items()}
    logger.info("默认参数: %s", default_params)

    # 基线性能
    baseline = _evaluate(strategy, bars, default_params)
    logger.info("基线: 收益=%.2f%% 回撤=%.2f%% 夏普=%.2f 交易=%d",
                baseline["total_return"] * 100, baseline["max_drawdown"] * 100, baseline["sharpe"], baseline["trades"])

    results = {"策略": name, "股票": stock_code, "区间": f"{start_date}~{end_date}",
               "默认参数": {k: round(v, 4) if isinstance(v, float) else v for k, v in default_params.items()},
               "基线": {k: round(v, 4) if isinstance(v, float) else v for k, v in baseline.items()},
               "扰动测试": {}, "过拟合评估": {}}

    for level in perturbation_levels:
        logger.info("─── 扰动级别: %.0f%% ───", level * 100)
        level_results = []
        for trial in range(10):
            perturbed = _perturb_params(default_params, param_space, level)
            perf = _evaluate(strategy, bars, perturbed)
            level_results.append(perf)
            logger.info("  试验%d: 收益=%.2f%% 回撤=%.2f%% 夏普=%.2f params=%s",
                        trial + 1, perf["total_return"] * 100, perf["max_drawdown"] * 100,
                        perf["sharpe"], {k: round(v, 2) for k, v in perturbed.items()})

        aggregated = _aggregate(level_results)
        results["扰动测试"][f"{int(level*100)}%"] = aggregated
        logger.info("  聚合: 收益均值=%.2f%%±%.2f%% 夏普均值=%.2f±%.2f",
                    aggregated["avg_return"] * 100, aggregated["std_return"] * 100,
                    aggregated["avg_sharpe"], aggregated["std_sharpe"])

    # 过拟合评估
    assessment = _assess_overfit(results)
    results["过拟合评估"] = assessment
    logger.info("=" * 50)
    logger.info("结论: %s (风险分=%.1f/10)", assessment["结论"], assessment["风险分"])
    logger.info("  %s", assessment["解释"])

    _save_report(results, strategy, stock_code)
    return results


def _perturb_params(default_params: dict, param_space: dict, level: float) -> dict:
    """在参数空间内随机扰动参数"""
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


def _evaluate(strategy, bars: list, params: dict) -> dict:
    """评估一组参数的性能"""
    buys = []
    sells = []
    for i in range(len(bars)):
        window = bars[:i + 1]
        try:
            signal = strategy.generate_signal(window, params)
        except Exception:
            continue
        if signal is None:
            continue
        if signal.get("action") == "buy":
            buys.append({"date": str(bars[i]["date"])[:10], "price": signal.get("price", bars[i]["close"])})
        elif signal.get("action") == "sell":
            sells.append({"date": str(bars[i]["date"])[:10], "price": signal.get("price", bars[i]["close"])})

    if not buys:
        return {"total_return": 0.0, "max_drawdown": 0.0, "sharpe": 0.0, "trades": 0}

    trades = _pair_trades(buys, sells, bars)
    if not trades:
        return {"total_return": 0.0, "max_drawdown": 0.0, "sharpe": 0.0, "trades": 0}

    returns = [t["ret"] for t in trades]
    total_return = sum(returns)
    equity = 1.0
    max_equity = 1.0
    max_dd = 0.0
    for r in returns:
        equity *= (1 + r)
        max_equity = max(max_equity, equity)
        max_dd = max(max_dd, (max_equity - equity) / max_equity)

    if len(returns) >= 2:
        mean_r = sum(returns) / len(returns)
        variance = sum((r - mean_r) ** 2 for r in returns) / (len(returns) - 1)
        std_r = math.sqrt(variance) if variance > 0 else 0
        sharpe = (mean_r / std_r * math.sqrt(252)) if std_r > 0 else 0
    else:
        sharpe = 0.0

    return {"total_return": total_return, "max_drawdown": max_dd, "sharpe": sharpe, "trades": len(trades)}


def _pair_trades(buys: list, sells: list, bars: list) -> list:
    trades = []
    prices = {str(b["date"])[:10]: b["close"] for b in bars}
    sorted_sells = sorted(sells, key=lambda s: s["date"])
    si = 0
    for buy in sorted(buys, key=lambda b: b["date"]):
        bd = str(buy["date"])[:10]
        bp = buy.get("price") or prices.get(bd, 0)
        if not bp:
            continue
        while si < len(sorted_sells):
            s = sorted_sells[si]
            sd = str(s["date"])[:10]
            if sd >= bd:
                sp = s.get("price") or prices.get(sd, bp)
                trades.append({"ret": (sp - bp) / bp})
                si += 1
                break
            si += 1
    return trades


def _aggregate(results: list) -> dict:
    returns = [r["total_return"] for r in results]
    sharpes = [r["sharpe"] for r in results]
    dds = [r["max_drawdown"] for r in results]
    n = len(results)
    return {
        "avg_return": sum(returns) / n,
        "std_return": math.sqrt(sum((r - sum(returns) / n) ** 2 for r in returns) / n) if n > 1 else 0,
        "avg_sharpe": sum(sharpes) / n,
        "std_sharpe": math.sqrt(sum((s - sum(sharpes) / n) ** 2 for s in sharpes) / n) if n > 1 else 0,
        "avg_drawdown": sum(dds) / n,
        "max_return": max(returns),
        "min_return": min(returns),
        "trials": n,
    }


def _assess_overfit(results: dict) -> dict:
    """评估过拟合风险等级"""
    baseline = results["基线"]
    if baseline["trades"] == 0:
        return {"风险分": 0, "结论": "无法评估", "解释": "基线无交易，跳过评估"}

    score = 0
    reasons = []
    base_return = baseline["total_return"]
    base_sharpe = baseline["sharpe"]

    for label, data in results["扰动测试"].items():
        level = float(label.replace("%", "")) / 100
        avg_ret = data["avg_return"]
        std_ret = data["std_return"]

        # 收益衰减
        ret_drop = (base_return - avg_ret) / abs(base_return) if base_return != 0 else 0
        if ret_drop > 0.5:
            score += 3
            reasons.append(f"{label}扰动收益衰减{ret_drop:.0%}，严重过拟合")
        elif ret_drop > 0.2:
            score += 1.5
            reasons.append(f"{label}扰动收益衰减{ret_drop:.0%}，轻度过拟合")

        # 波动率 (CV)
        if avg_ret != 0 and std_ret > 0:
            cv = abs(std_ret / avg_ret)
            if cv > 2.0:
                score += 2
                reasons.append(f"{label}扰动变异系数{cv:.1f}，参数敏感")

        # 夏普衰减
        if base_sharpe > 0 and data["avg_sharpe"] < base_sharpe * 0.5:
            score += 1
            reasons.append(f"{label}扰动夏普减半")

    score = min(score, 10)
    if score < 2:
        conclusion = "低风险，参数鲁棒性好"
    elif score < 5:
        conclusion = "中风险，存在参数敏感性"
    elif score < 7:
        conclusion = "高风险，明显过拟合趋势"
    else:
        conclusion = "极高风险，严重过拟合"

    return {"风险分": round(score, 1), "结论": conclusion, "解释": "; ".join(reasons) if reasons else "参数稳定，无过拟合迹象"}


def _load_data(stock_code: str, start_date: str, end_date: str) -> dict:
    from core.data_bus import get_data_bus
    bus = get_data_bus()
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    days_needed = (end_dt - start_dt).days + 60
    kline = bus.get_kline(stock_code, days=min(days_needed, 2000))
    if not kline or not kline.get("dates"):
        return {"error": "无法获取K线数据"}
    dates = kline["dates"]
    indices = [i for i, d in enumerate(dates) if start_date <= str(d)[:10] <= end_date]
    if not indices:
        return {"error": f"区间无数据"}
    lo, hi = indices[0], indices[-1] + 1
    return {
        "symbol": stock_code, "name": kline.get("name", ""),
        "dates": dates[lo:hi], "opens": kline["opens"][lo:hi],
        "highs": kline["highs"][lo:hi], "lows": kline["lows"][lo:hi],
        "closes": kline["closes"][lo:hi], "volumes": kline["volumes"][lo:hi],
        "count": hi - lo,
    }


def _to_bars(kline: dict) -> list[dict]:
    n = kline["count"]
    return [{"date": kline["dates"][i], "open": float(kline["opens"][i]),
             "high": float(kline["highs"][i]), "low": float(kline["lows"][i]),
             "close": float(kline["closes"][i]), "volume": float(kline["volumes"][i])}
            for i in range(n)]


def _save_report(report: dict, strategy, stock_code: str) -> None:
    import json
    sid = getattr(strategy, "ID", strategy.__class__.__name__)
    fn = f"{sid}_{stock_code}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    fp = os.path.join(REPORTS_DIR, fn)
    with open(fp, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    logger.info("📄 报告: %s", fp)


# ============================================================
# Mock 数据 + 快速测试
# ============================================================

def generate_mock_bars(days: int = 200) -> list[dict]:
    """生成含趋势的Mock数据，让MACD能产生买入信号"""
    random.seed(42)
    bars = []
    price = 10.0
    base = datetime(2024, 1, 2)
    for i in range(days):
        date = base + timedelta(days=i)
        if date.weekday() >= 5:
            continue
        # 前半段上升，后半段震荡
        if i < 80:
            trend = 0.003
        elif i < 120:
            trend = -0.002
        else:
            trend = 0.001
        change = random.gauss(trend, 0.015)
        open_p = price * (1 + random.gauss(0, 0.005))
        close_p = price * (1 + change)
        high_p = max(open_p, close_p) * (1 + abs(random.gauss(0, 0.01)))
        low_p = min(open_p, close_p) * (1 - abs(random.gauss(0, 0.01)))
        volume = random.uniform(500000, 2000000)
        bars.append({
            "date": date.strftime("%Y-%m-%d"), "open": round(open_p, 2),
            "high": round(high_p, 2), "low": round(low_p, 2),
            "close": round(close_p, 2), "volume": int(volume),
        })
        price = close_p
    return bars


if __name__ == "__main__":
    import importlib
    import json

    print("=" * 60)
    print("  策略过拟合扰动测试")
    print("=" * 60)

    use_mock = "--mock" in sys.argv

    mod = importlib.import_module("core.strategies.ths_strategies.14_strategies.01_macd_wave")
    strategy = mod.MACDWaveStrategy()

    if use_mock:
        print("\n📦 Mock 模式")
        bars = generate_mock_bars(200)
        logger.info("Mock: %d条K线", len(bars))
        param_space = strategy.get_param_space()
        default_params = {k: v[0] if isinstance(v, tuple) else v for k, v in param_space.items()}
        baseline = _evaluate(strategy, bars, default_params)
        print(f"基线: 收益={baseline['total_return']*100:.2f}% 夏普={baseline['sharpe']:.2f} 交易={baseline['trades']}")

        results = {"策略": strategy.NAME, "默认参数": default_params, "基线": baseline, "扰动测试": {}}
        for level in [0.05, 0.10, 0.20]:
            level_results = [_evaluate(strategy, bars, _perturb_params(default_params, param_space, level)) for _ in range(10)]
            results["扰动测试"][f"{int(level*100)}%"] = _aggregate(level_results)

        assessment = _assess_overfit(results)
        results["过拟合评估"] = assessment

        print(f"\n📊 扰动测试结果:")
        for label, data in results["扰动测试"].items():
            print(f"  {label}: 收益={data['avg_return']*100:.2f}%±{data['std_return']*100:.2f}% 夏普={data['avg_sharpe']:.2f}±{data['std_sharpe']:.2f}")
        print(f"\n🎯 过拟合评估: {assessment['结论']} (风险分={assessment['风险分']}/10)")
        print(f"   {assessment['解释']}")
    else:
        stock_code = sys.argv[1] if len(sys.argv) > 1 else "000001"
        start = sys.argv[2] if len(sys.argv) > 2 else "2024-01-01"
        end = sys.argv[3] if len(sys.argv) > 3 else "2025-06-30"
        result = run_overfit_test(strategy, stock_code, start, end)
        print(f"\n🎯 结论: {result['过拟合评估']['结论']}")
        print(f"   风险分: {result['过拟合评估']['风险分']}/10")
        print(f"   {result['过拟合评估']['解释']}")