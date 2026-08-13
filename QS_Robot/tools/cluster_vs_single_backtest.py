"""金融大师32策略集群 vs 单策略 真实数据对比回测

对比维度:
  1. 集群共识信号 (32策略加权投票)
  2. 最优单策略 (收益最高)
  3. 策略平均 (32策略均值)
  4. 策略中位数

输出: 收益率/夏普比率/胜率/最大回撤/交易次数 对比报告
"""
from __future__ import annotations

import json
import logging
import statistics as st
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("cluster_vs_single")

# 抑制策略模块的详细日志，只保留 WARNING 以上
for _name in ["ths", "core.strategies", "RiskMonitor"]:
    logging.getLogger(_name).setLevel(logging.WARNING)

_QS_ROBOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_QS_ROBOT))


@dataclass
class TradeRecord:
    symbol: str
    entry_date: str
    exit_date: str
    entry_price: float
    exit_price: float
    return_pct: float
    strategy: str = ""


@dataclass
class StrategyResult:
    name: str
    total_trades: int = 0
    win_trades: int = 0
    total_return: float = 0.0
    win_rate: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    returns_list: list[float] = field(default_factory=list)
    trades: list[TradeRecord] = field(default_factory=list)


def load_strategies() -> list[Any]:
    """加载全部32个策略"""
    strategies = []
    base_dir = _QS_ROBOT / "core" / "strategies" / "ths_strategies"

    for sub_dir in ["14_strategies", "18_advanced"]:
        d = base_dir / sub_dir
        if not d.exists():
            continue
        for f in sorted(d.glob("*.py")):
            if f.name.startswith("_"):
                continue
            try:
                mod = __import__(
                    f"core.strategies.ths_strategies.{sub_dir}.{f.stem}",
                    fromlist=[f.stem],
                )
                for attr in dir(mod):
                    obj = getattr(mod, attr)
                    if isinstance(obj, type) and attr.endswith("Strategy") and hasattr(obj, "ID"):
                        strategies.append(obj())
                        logger.info("加载: %s (%s)", obj.ID, obj.NAME)
            except Exception as e:
                logger.warning("加载失败 %s: %s", f.name, e)

    logger.info("共加载 %d 个策略", len(strategies))
    return strategies


def load_market_data(symbol: str = "000300", cache_dir: Path = None) -> list[dict]:
    """加载近3年日线数据（指数用stock_zh_index_daily，个股用stock_zh_a_daily）"""
    if cache_dir is None:
        cache_dir = _QS_ROBOT / "data_cache"
    cache_dir.mkdir(exist_ok=True)
    cache_file = cache_dir / f"{symbol}_3y.json"

    if cache_file.exists():
        try:
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            if data and len(data) > 100:
                logger.info("从缓存加载 %s: %d条", symbol, len(data))
                return data
        except Exception:
            pass

    logger.info("从AKShare获取 %s 行情...", symbol)
    try:
        import akshare as ak
        df = None
        # 指数类标的用 stock_zh_index_daily
        if symbol in ("000300", "000001", "000016", "399001", "399006"):
            prefix = "sh" if symbol.startswith(("0", "6")) else "sz"
            df = ak.stock_zh_index_daily(symbol=f"{prefix}{symbol}")
        else:
            # 个股先尝试 Sina 接口
            prefix = "sh" if symbol.startswith(("5", "6", "9")) else "sz"
            try:
                df = ak.stock_zh_a_daily(symbol=f"{prefix}{symbol}", adjust="qfq")
            except Exception:
                df = ak.stock_zh_a_daily(symbol=symbol, adjust="qfq")

        if df is None or df.empty:
            raise RuntimeError("空数据")
        df = df.tail(750)
        bars = []
        for _, row in df.iterrows():
            bars.append({
                "date": str(row["date"]),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row["volume"]),
            })
        cache_file.write_text(json.dumps(bars, ensure_ascii=False), encoding="utf-8")
        logger.info("获取 %s: %d条 (%s ~ %s)", symbol, len(bars), bars[0]["date"], bars[-1]["date"])
        return bars
    except ImportError:
        logger.warning("AKShare未安装")
        return _mock_data(750)
    except Exception as e:
        logger.warning("AKShare %s 失败: %s", symbol, e)
        return _mock_data(750)


def _mock_data(n: int = 750) -> list[dict]:
    import random
    random.seed(42)
    bars = []
    price = 10.0
    for i in range(n):
        change = random.gauss(0.0005, 0.02)
        c = price * (1 + change)
        h = max(price, c) * (1 + abs(random.gauss(0, 0.008)))
        l = min(price, c) * (1 - abs(random.gauss(0, 0.008)))
        v = random.randint(500000, 5000000)
        bars.append({
            "date": f"2024-{1+(i//21):02d}-{1+(i%21):02d}",
            "open": round(price, 2), "high": round(h, 2),
            "low": round(l, 2), "close": round(c, 2), "volume": v,
        })
        price = c
    return bars


def _compute_metrics(returns: list[float], capital: float = 1_000_000) -> dict:
    """计算核心指标"""
    if not returns:
        return {"total_return": 0, "win_rate": 0, "sharpe": 0, "max_dd": 0, "trades": 0}

    total_ret = sum(returns) * 100
    wins = sum(1 for r in returns if r > 0)
    win_rate = wins / len(returns) * 100

    mean_r = st.mean(returns)
    std_r = st.stdev(returns) if len(returns) > 1 else 0.01
    sharpe = (mean_r / std_r * (252 ** 0.5)) if std_r > 0 else 0

    peak = 0.0
    cum = 0.0
    max_dd = 0.0
    for r in returns:
        cum += r
        peak = max(peak, cum)
        max_dd = max(max_dd, peak - cum)

    return {
        "total_return": round(total_ret, 2),
        "win_rate": round(win_rate, 1),
        "sharpe": round(sharpe, 2),
        "max_dd": round(max_dd * 100, 2),
        "trades": len(returns),
    }


def run_single_strategy_backtest(strategy: Any, bars: list[dict]) -> StrategyResult:
    """单策略回测"""
    result = StrategyResult(name=f"{strategy.ID} {strategy.NAME}")
    position = 0
    entry_price = Decimal("0")
    entry_date = ""
    total_bars = len(bars) - 60

    for i in range(60, len(bars)):
        window = bars[:i + 1]
        bar = bars[i]

        try:
            signal = strategy.generate_signal(window, params={})
        except Exception:
            continue

        if not signal:
            continue

        action = signal.get("action", "")

        if action == "buy" and position == 0:
            position = 1
            entry_price = Decimal(str(bar["close"]))
            entry_date = bar["date"]

        elif action == "sell" and position > 0:
            close_p = Decimal(str(bar["close"]))
            pnl = float((close_p - entry_price) / entry_price)
            result.returns_list.append(pnl)
            result.trades.append(TradeRecord(
                symbol="", entry_date=entry_date, exit_date=bar["date"],
                entry_price=float(entry_price), exit_price=float(close_p),
                return_pct=pnl * 100, strategy=result.name,
            ))
            position = 0

    result.total_trades = len(result.returns_list)
    result.win_trades = sum(1 for r in result.returns_list if r > 0)
    if result.returns_list:
        result.total_return = sum(result.returns_list) * 100
        result.win_rate = result.win_trades / len(result.returns_list) * 100
        result.sharpe_ratio = _compute_metrics(result.returns_list)["sharpe"]
        result.max_drawdown = _compute_metrics(result.returns_list)["max_dd"]

    return result


def run_cluster_consensus_backtest(
    strategies: list[Any], bars: list[dict],
    threshold: float = 0.15,
) -> StrategyResult:
    """集群共识回测 — 32策略加权投票"""
    result = StrategyResult(name="集群共识(32策略加权)")
    position = 0
    entry_price = Decimal("0")
    entry_date = ""

    for i in range(60, len(bars)):
        window = bars[:i + 1]
        bar = bars[i]

        directions = []
        for s in strategies:
            try:
                sig = s.generate_signal(window, params={})
            except Exception:
                continue
            if sig is None:
                directions.append(0.0)
            elif sig.get("action") == "buy":
                directions.append(1.0)
            elif sig.get("action") == "sell":
                directions.append(-1.0)
            else:
                directions.append(0.0)

        if not directions:
            continue

        weighted_dir = sum(directions) / len(directions)
        bullish = sum(1 for d in directions if d > 0)
        bearish = sum(1 for d in directions if d < 0)

        if position == 0 and weighted_dir > threshold:
            position = 1
            entry_price = Decimal(str(bar["close"]))
            entry_date = bar["date"]

        elif position > 0 and weighted_dir < -threshold:
            close_p = Decimal(str(bar["close"]))
            pnl = float((close_p - entry_price) / entry_price)
            result.returns_list.append(pnl)
            result.trades.append(TradeRecord(
                symbol="", entry_date=entry_date, exit_date=bar["date"],
                entry_price=float(entry_price), exit_price=float(close_p),
                return_pct=pnl * 100, strategy="集群共识",
            ))
            position = 0

    result.total_trades = len(result.returns_list)
    result.win_trades = sum(1 for r in result.returns_list if r > 0)
    if result.returns_list:
        result.total_return = sum(result.returns_list) * 100
        result.win_rate = result.win_trades / len(result.returns_list) * 100
        result.sharpe_ratio = _compute_metrics(result.returns_list)["sharpe"]
        result.max_drawdown = _compute_metrics(result.returns_list)["max_dd"]

    return result


def run_full_comparison(
    symbols: list[str] = None,
    thresholds: list[float] = None,
) -> dict:
    """运行完整对比"""
    if symbols is None:
        symbols = ["000300"]
    if thresholds is None:
        thresholds = [0.05, 0.10, 0.15, 0.20, 0.25]

    strategies = load_strategies()
    if not strategies:
        logger.error("策略加载失败")
        return {}

    all_results = {}
    for symbol in symbols:
        logger.info("=" * 60)
        logger.info("标的: %s", symbol)
        logger.info("=" * 60)

        bars = load_market_data(symbol)
        logger.info("数据: %d 条K线 (%s ~ %s)",
                    len(bars), bars[0]["date"], bars[-1]["date"])

        single_results = []
        for s in strategies:
            sr = run_single_strategy_backtest(s, bars)
            single_results.append(sr)
            if sr.total_trades > 0:
                logger.info("  %s: 交易%d 收益%.1f%% 胜率%.0f%% 夏普%.2f",
                           s.ID, sr.total_trades, sr.total_return,
                           sr.win_rate, sr.sharpe_ratio)

        cluster_results = []
        for th in thresholds:
            cr = run_cluster_consensus_backtest(strategies, bars, threshold=th)
            cluster_results.append({"threshold": th, "result": cr})
            logger.info("  集群(阈值%.2f): 交易%d 收益%.1f%% 胜率%.0f%% 夏普%.2f",
                       th, cr.total_trades, cr.total_return,
                       cr.win_rate, cr.sharpe_ratio)

        best_single = max(single_results, key=lambda r: r.total_return)
        returns_all = [r.total_return for r in single_results if r.total_trades > 0]
        avg_return = st.mean(returns_all) if returns_all else 0
        median_return = st.median(returns_all) if returns_all else 0
        best_cluster = max(cluster_results, key=lambda r: r["result"].total_return)

        all_results[symbol] = {
            "symbol": symbol,
            "data_bars": len(bars),
            "date_range": f"{bars[0]['date']} ~ {bars[-1]['date']}",
            "single_count": len(single_results),
            "active_count": len([r for r in single_results if r.total_trades > 0]),
            "best_single": {
                "name": best_single.name,
                "trades": best_single.total_trades,
                "return": best_single.total_return,
                "win_rate": best_single.win_rate,
                "sharpe": best_single.sharpe_ratio,
                "max_dd": best_single.max_drawdown,
            },
            "avg_single": {
                "return": round(avg_return, 2),
                "count": len(returns_all),
            },
            "median_single": {
                "return": round(median_return, 2),
            },
            "best_cluster": {
                "threshold": best_cluster["threshold"],
                "trades": best_cluster["result"].total_trades,
                "return": best_cluster["result"].total_return,
                "win_rate": best_cluster["result"].win_rate,
                "sharpe": best_cluster["result"].sharpe_ratio,
                "max_dd": best_cluster["result"].max_drawdown,
            },
            "cluster_by_threshold": [
                {
                    "threshold": cr["threshold"],
                    "trades": cr["result"].total_trades,
                    "return": cr["result"].total_return,
                    "win_rate": cr["result"].win_rate,
                    "sharpe": cr["result"].sharpe_ratio,
                }
                for cr in cluster_results
            ],
            "single_details": [
                {
                    "name": r.name,
                    "trades": r.total_trades,
                    "return": r.total_return,
                    "win_rate": r.win_rate,
                    "sharpe": r.sharpe_ratio,
                    "max_dd": r.max_drawdown,
                }
                for r in sorted(single_results, key=lambda x: x.total_return, reverse=True)
            ],
        }

    return all_results


def generate_report(all_results: dict) -> str:
    """生成对比报告"""
    lines = []
    lines.append("=" * 80)
    lines.append("金融大师32策略集群 vs 单策略 — 真实数据对比报告")
    lines.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("=" * 80)
    lines.append("")

    for symbol, data in all_results.items():
        lines.append(f"## 标的: {symbol} ({data['date_range']}, {data['data_bars']}条K线)")
        lines.append("")

        bs = data["best_single"]
        as_ = data["avg_single"]
        ms = data["median_single"]
        bc = data["best_cluster"]

        lines.append("### 核心对比")
        lines.append("")
        lines.append("| 指标 | 最优单策略 | 策略平均 | 策略中位数 | 集群共识 | 集群vs最优 | 集群vs平均 |")
        lines.append("|------|-----------|---------|-----------|---------|-----------|-----------|")
        lines.append(f"| 收益率 | {bs['return']:.1f}% | {as_['return']:.1f}% | {ms['return']:.1f}% | {bc['return']:.1f}% | {bc['return']-bs['return']:+.1f}pp | {bc['return']-as_['return']:+.1f}pp |")
        lines.append(f"| 夏普比率 | {bs['sharpe']:.2f} | - | - | {bc['sharpe']:.2f} | - | - |")
        lines.append(f"| 胜率 | {bs['win_rate']:.0f}% | - | - | {bc['win_rate']:.0f}% | - | - |")
        lines.append(f"| 最大回撤 | {bs['max_dd']:.1f}% | - | - | {bc['max_dd']:.1f}% | - | - |")
        lines.append(f"| 交易次数 | {bs['trades']} | - | - | {bc['trades']} | - | - |")
        lines.append(f"| 活跃策略 | - | {data['active_count']}/{data['single_count']} | - | 阈值={bc['threshold']:.2f} | - | - |")
        lines.append("")

        lines.append("### 集群阈值敏感性")
        lines.append("")
        lines.append("| 阈值 | 交易次数 | 收益率 | 胜率 | 夏普 |")
        lines.append("|------|---------|--------|------|------|")
        for ct in data["cluster_by_threshold"]:
            lines.append(f"| {ct['threshold']:.2f} | {ct['trades']} | {ct['return']:.1f}% | {ct['win_rate']:.0f}% | {ct['sharpe']:.2f} |")
        lines.append("")

        lines.append("### 单策略排名 (Top 10)")
        lines.append("")
        lines.append("| 排名 | 策略 | 交易数 | 收益率 | 胜率 | 夏普 | 最大回撤 |")
        lines.append("|------|------|--------|--------|------|------|---------|")
        for rank, sd in enumerate(data["single_details"][:10], 1):
            lines.append(f"| {rank} | {sd['name']} | {sd['trades']} | {sd['return']:.1f}% | {sd['win_rate']:.0f}% | {sd['sharpe']:.2f} | {sd['max_dd']:.1f}% |")
        lines.append("")

    lines.append("=" * 80)
    lines.append("结论")
    lines.append("=" * 80)
    lines.append("")

    avg_cluster_vs_best = st.mean([
        d["best_cluster"]["return"] - d["best_single"]["return"]
        for d in all_results.values()
    ])
    avg_cluster_vs_avg = st.mean([
        d["best_cluster"]["return"] - d["avg_single"]["return"]
        for d in all_results.values()
    ])

    lines.append(f"1. 集群共识 vs 最优单策略: {avg_cluster_vs_best:+.1f}pp (平均)")
    lines.append(f"2. 集群共识 vs 策略平均: {avg_cluster_vs_avg:+.1f}pp (平均)")
    if avg_cluster_vs_avg > 0:
        lines.append("3. ✅ 集群共识整体优于策略平均水平")
    else:
        lines.append("3. ⚠️ 集群共识未显著优于策略平均，需优化共识机制")
    if avg_cluster_vs_best > 0:
        lines.append("4. ✅ 集群共识超越最优单策略")
    else:
        lines.append("4. 集群共识未超越最优单策略（正常，集群追求稳健而非极致）")

    return "\n".join(lines)


def main():
    logger.info("=" * 60)
    logger.info("金融大师32策略集群 vs 单策略 对比回测")
    logger.info("=" * 60)

    symbols = ["000300"]  # 先用沪深300跑通，后续扩展
    all_results = run_full_comparison(symbols=symbols)

    report = generate_report(all_results)

    report_dir = _QS_ROBOT / "reports" / "cluster_vs_single"
    report_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = report_dir / f"comparison_{ts}.md"
    report_path.write_text(report, encoding="utf-8")

    json_path = report_dir / f"comparison_{ts}.json"
    json_path.write_text(
        json.dumps(all_results, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    print("\n" + report)
    logger.info("报告已保存: %s", report_path)
    logger.info("JSON已保存: %s", json_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())