"""单只股票标准化审查流程
输入：策略实例 + 股票代码 + 回测时间区间
输出：个股审查报告（JSON）+ 风险标记 + 适配结论

用法：
    import importlib
    from tools.single_stock_review import single_stock_review
    mod = importlib.import_module("core.strategies.ths_strategies.14_strategies.01_macd_wave")
    strategy = mod.MACDWaveStrategy()
    report = single_stock_review(strategy, "000001", "2024-01-01", "2025-12-31")
"""
import os
import sys
import json
import math
import time
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from core.data_bus import get_data_bus
from core.data_validator import get_validator
from api.ths_bridge.pool_filter import is_st_stock, detect_market

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s - %(message)s")
logger = logging.getLogger("single_stock_review")

REPORTS_DIR = os.path.join(PROJECT_ROOT, "reports", "single_stock")


def single_stock_review(strategy, stock_code: str, start_date: str, end_date: str) -> dict:
    """个股标准化审查主流程"""
    os.makedirs(REPORTS_DIR, exist_ok=True)
    strategy_name = getattr(strategy, "NAME", strategy.__class__.__name__)
    logger.info("=" * 50)
    logger.info("🔍 开始审查: 策略=%s 股票=%s 区间=%s~%s", strategy_name, stock_code, start_date, end_date)

    report = {
        "策略": strategy_name,
        "股票代码": stock_code,
        "回测区间": f"{start_date} ~ {end_date}",
        "审查时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    # 步骤1：标的前置过滤
    logger.info("─── 步骤1/6: 标的前置过滤 ───")
    filter_result = _stock_filter(stock_code)
    report["标的过滤结果"] = filter_result
    logger.info("过滤结果: pass=%s checks=%d warnings=%d",
                filter_result["pass"], len(filter_result.get("checks", [])), len(filter_result.get("warnings", [])))
    if not filter_result["pass"]:
        logger.warning("❌ 过滤不通过: %s", [c["detail"] for c in filter_result.get("checks", []) if c["status"] == "FAIL"])
        report["结论"] = "不适配，过滤条件不通过"
        _save_report(report, strategy, stock_code)
        return report

    # 步骤2：校验K线数据完整性
    logger.info("─── 步骤2/6: K线数据加载与校验 ───")
    kline = _load_kline(stock_code, start_date, end_date)
    data_check = _validate_data(kline)
    report["数据校验"] = data_check
    logger.info("数据校验: valid=%s 条数=%d errors=%d warnings=%d",
                data_check["valid"], kline.get("count", 0),
                len(data_check.get("errors", [])), len(data_check.get("warnings", [])))
    if not data_check["valid"]:
        logger.warning("❌ 数据校验不通过: %s", data_check.get("errors", []))
        report["结论"] = "不适配，数据校验不通过"
        _save_report(report, strategy, stock_code)
        return report

    bars = _to_bars(kline)
    logger.info("K线转bars完成: %d条, 首日=%s 末日=%s",
                len(bars), str(bars[0]["date"])[:10] if bars else "N/A",
                str(bars[-1]["date"])[:10] if bars else "N/A")

    # 步骤3：逐K回放全部交易信号
    logger.info("─── 步骤3/6: 逐K回放交易信号 ───")
    signal_records = _backtest_step_by_step(strategy, bars)
    report["全部信号记录"] = signal_records
    logger.info("信号统计: 买入=%d 卖出=%d 异常=%d 无信号=%d天",
                len(signal_records.get("买入信号", [])),
                len(signal_records.get("卖出信号", [])),
                len(signal_records.get("异常", [])),
                signal_records.get("无信号天数", 0))

    # 步骤4：边界场景模拟
    logger.info("─── 步骤4/6: 边界场景模拟 ───")
    edge_result = _simulate_edge_scenario(strategy, bars)
    report["边界场景测试"] = edge_result
    for scenario, detail in edge_result.items():
        if "error" in detail:
            logger.warning("  %s: ❌ %s", scenario, detail["error"])
        else:
            sig = detail.get("信号", {})
            sig_str = f"action={sig.get('action')} price={sig.get('price')} reason={sig.get('reason')}" if sig else "无信号"
            logger.info("  %s: %s", scenario, sig_str)

    # 步骤5：计算单标的量化指标
    logger.info("─── 步骤5/6: 量化指标计算 ───")
    metrics = _calc_metrics(signal_records, bars)
    report["量化指标"] = metrics
    logger.info("指标: 累计收益=%.2f%% 回撤=%.4f 夏普=%.2f 交易=%d次 胜率=%.1f%%",
                metrics["累计收益"], metrics["最大回撤"], metrics["夏普比率"],
                metrics["交易次数"], metrics["胜率"])

    # 步骤6：漏洞检测
    logger.info("─── 步骤6/6: 漏洞检测 ───")
    bug_check = _detect_strategy_bug(signal_records, bars)
    report["漏洞检测"] = bug_check
    logger.info("漏洞检测: 严重=%d 警告=%d",
                len(bug_check.get("serious_bug", [])), len(bug_check.get("warnings", [])))

    # 最终适配结论
    if bug_check.get("serious_bug"):
        report["结论"] = "不适配，存在严重漏洞"
        logger.warning("❌ 结论: 不适配 (严重漏洞=%d)", len(bug_check["serious_bug"]))
    elif metrics["夏普比率"] > 0 and metrics["最大回撤"] < 0.35:
        report["结论"] = "适配该标的"
        logger.info("✅ 结论: 适配该标的")
    else:
        report["结论"] = "条件适配，性能表现一般"
        logger.info("⚠️ 结论: 条件适配 (夏普=%.2f 回撤=%.4f)", metrics["夏普比率"], metrics["最大回撤"])

    _save_report(report, strategy, stock_code)
    return report


# ============================================================
# 步骤1：标的前置过滤
# ============================================================

def _stock_filter(stock_code: str) -> dict:
    """ST/退市/停牌/流动性基础过滤"""
    result = {"pass": True, "checks": [], "warnings": []}
    logger.info("[过滤] 开始检查股票 %s", stock_code)

    # ST检查
    try:
        bus = get_data_bus()
        kline = bus.get_kline(stock_code, days=5)
        name = kline.get("name", "") if kline else ""
        if is_st_stock(name):
            logger.warning("[过滤] ST检查 FAIL: 股票名称含ST='%s'", name)
            result["pass"] = False
            result["checks"].append({"item": "ST检查", "status": "FAIL", "detail": f"股票名称含ST: {name}"})
            return result
        logger.info("[过滤] ST检查 PASS: name=%s", name or stock_code)
        result["checks"].append({"item": "ST检查", "status": "PASS", "detail": name or stock_code})
    except Exception as e:
        logger.warning("[过滤] ST检查异常: %s", e)
        result["warnings"].append(f"ST检查异常: {e}")

    # 市场识别
    market = detect_market(stock_code)
    if market == "unknown":
        logger.warning("[过滤] 市场识别 FAIL: 无法识别板块")
        result["pass"] = False
        result["checks"].append({"item": "市场识别", "status": "FAIL", "detail": "无法识别市场板块"})
        return result
    logger.info("[过滤] 市场识别 PASS: %s", market)
    result["checks"].append({"item": "市场识别", "status": "PASS", "detail": market})

    # 流动性检查
    try:
        bus = get_data_bus()
        kline = bus.get_kline(stock_code, days=60)
        if kline and kline.get("volumes") and kline.get("closes"):
            vols = [float(v) for v in kline["volumes"][-20:] if v]
            closes = [float(c) for c in kline["closes"][-20:] if c]
            if vols and closes:
                avg_amount = sum(v * c for v, c in zip(vols, closes)) / len(vols)
                if avg_amount < 1_000_000:
                    logger.warning("[过滤] 流动性 FAIL: 日均成交额=%.1f万 < 100万", avg_amount / 10000)
                    result["pass"] = False
                    result["checks"].append({
                        "item": "流动性检查", "status": "FAIL",
                        "detail": f"日均成交额{avg_amount/10000:.1f}万 < 100万"
                    })
                    return result
                logger.info("[过滤] 流动性 PASS: 日均成交额=%.1f万", avg_amount / 10000)
                result["checks"].append({
                    "item": "流动性检查", "status": "PASS",
                    "detail": f"日均成交额{avg_amount/10000:.1f}万"
                })
    except Exception as e:
        logger.warning("[过滤] 流动性检查异常: %s", e)
        result["warnings"].append(f"流动性检查异常: {e}")

    return result


# ============================================================
# 步骤2：K线数据加载与校验
# ============================================================

def _load_kline(stock_code: str, start_date: str, end_date: str) -> dict:
    """通过data_bus加载K线，按日期范围截取"""
    bus = get_data_bus()
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    days_needed = (end_dt - start_dt).days + 60

    logger.info("[K线] 请求 %s K线 days=%d", stock_code, min(days_needed, 2000))
    kline = bus.get_kline(stock_code, days=min(days_needed, 2000))
    if not kline or not kline.get("dates"):
        logger.error("[K线] 获取失败: 无数据返回")
        return {"error": "无法获取K线数据", "count": 0}

    logger.info("[K线] 获取到 %d 条 (源=%s)", len(kline["dates"]), kline.get("source", "unknown"))

    # 按日期范围截取
    dates = kline["dates"]
    indices = [i for i, d in enumerate(dates) if start_date <= str(d)[:10] <= end_date]
    if not indices:
        logger.error("[K线] 区间 %s~%s 无数据", start_date, end_date)
        return {"error": f"区间{start_date}~{end_date}无数据", "count": 0}

    lo, hi = indices[0], indices[-1] + 1
    logger.info("[K线] 截取后: %d 条 (%s ~ %s)", hi - lo, str(dates[lo])[:10], str(dates[hi - 1])[:10])
    return {
        "symbol": stock_code,
        "name": kline.get("name", ""),
        "dates": dates[lo:hi],
        "opens": kline["opens"][lo:hi],
        "highs": kline["highs"][lo:hi],
        "lows": kline["lows"][lo:hi],
        "closes": kline["closes"][lo:hi],
        "volumes": kline["volumes"][lo:hi],
        "count": hi - lo,
        "source": kline.get("source", "unknown"),
    }


def _validate_data(kline: dict) -> dict:
    """数据完整性校验"""
    if kline.get("error"):
        logger.error("[校验] K线错误: %s", kline["error"])
        return {"valid": False, "errors": [kline["error"]], "warnings": []}

    validator = get_validator()
    result = validator.validate_kline(kline)

    # NaN/Inf检查
    nan_fields = []
    for field in ["opens", "highs", "lows", "closes", "volumes"]:
        values = kline.get(field, [])
        for v in values:
            if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
                nan_fields.append(field)
                break
    if nan_fields:
        logger.warning("[校验] 发现NaN/Inf字段: %s", nan_fields)
        result.setdefault("errors", []).append(f"包含NaN/Inf字段: {nan_fields}")

    # 最小数据量
    count = kline.get("count", 0)
    if count < 30:
        logger.warning("[校验] 数据量不足: %d条 < 30条", count)
        result.setdefault("errors", []).append(f"数据量不足({count}条，至少30条)")
    else:
        logger.info("[校验] 数据量OK: %d条", count)

    return result


def _to_bars(kline: dict) -> list[dict]:
    """将data_bus格式转为策略所需的bars格式"""
    n = kline["count"]
    return [
        {
            "date": kline["dates"][i],
            "open": float(kline["opens"][i]),
            "high": float(kline["highs"][i]),
            "low": float(kline["lows"][i]),
            "close": float(kline["closes"][i]),
            "volume": float(kline["volumes"][i]),
        }
        for i in range(n)
    ]


# ============================================================
# 步骤3：逐K回放交易信号
# ============================================================

def _backtest_step_by_step(strategy, bars: list[dict]) -> dict:
    """逐K模拟，记录全部开平仓信号"""
    params = strategy.get_param_space() if hasattr(strategy, "get_param_space") else {}
    default_params = {k: v[0] if isinstance(v, tuple) else v for k, v in params.items()} if params else {}
    logger.info("[信号回放] 开始逐K遍历 %d 条K线, params=%s", len(bars), default_params)

    records = {"买入信号": [], "卖出信号": [], "信号总数": 0, "无信号天数": 0}
    prev_has_signal = False

    for i in range(len(bars)):
        window = bars[:i + 1]
        try:
            signal = strategy.generate_signal(window, default_params)
        except Exception as e:
            logger.error("[信号回放] 第%d天异常: %s", i + 1, e)
            records.setdefault("异常", []).append({"日期": str(bars[i]["date"])[:10], "异常": str(e)})
            continue

        if signal is None:
            records["无信号天数"] += 1
            prev_has_signal = False
            continue

        # 信号切换时打印
        if not prev_has_signal or records["信号总数"] == 0:
            logger.info("[信号回放] 第%d天 (%s) 首次触发信号: action=%s price=%.2f",
                        i + 1, str(bars[i]["date"])[:10],
                        signal.get("action"), signal.get("price", bars[i]["close"]))

        records["信号总数"] += 1
        prev_has_signal = True
        action = signal.get("action", "unknown")
        entry = {
            "日期": str(bars[i]["date"])[:10],
            "价格": round(signal.get("price", bars[i]["close"]), 2),
            "止损": signal.get("stop_loss"),
            "止盈": signal.get("take_profit"),
            "原因": signal.get("reason", ""),
        }
        if action == "buy":
            records["买入信号"].append(entry)
            logger.info("[信号回放] 📈 买入 %s price=%.2f stop=%.2f take=%.2f",
                        entry["日期"], entry["价格"], entry["止损"], entry["止盈"])
        elif action == "sell":
            records["卖出信号"].append(entry)
        else:
            records.setdefault("未知信号", []).append({**entry, "action": action})

    logger.info("[信号回放] 完成: 买入=%d 卖出=%d 未知=%d 无信号=%d天",
                len(records["买入信号"]), len(records["卖出信号"]),
                len(records.get("未知信号", [])), records["无信号天数"])
    return records


# ============================================================
# 步骤4：边界场景模拟
# ============================================================

def _simulate_edge_scenario(strategy, bars: list[dict]) -> dict:
    """模拟涨跌停、大幅波动场景下策略行为"""
    result = {"涨停场景": {}, "跌停场景": {}, "大幅波动场景": {}}

    if len(bars) < 30:
        logger.warning("[边界] 数据不足 %d条 < 30，跳过模拟", len(bars))
        result["error"] = "数据不足，无法模拟"
        return result

    params = strategy.get_param_space() if hasattr(strategy, "get_param_space") else {}
    default_params = {k: v[0] if isinstance(v, tuple) else v for k, v in params.items()} if params else {}
    last = bars[-1]
    last_close = last["close"]
    logger.info("[边界] 基准收盘价=%.2f 开始模拟3种场景", last_close)

    # ── 涨停场景 ──
    logger.info("[边界] 涨停场景: 构造连续3日涨停 (%.2f → %.2f)", last_close, round(last_close * 1.10, 2))
    limit_up = last.copy()
    limit_up["open"] = limit_up["high"] = limit_up["low"] = limit_up["close"] = round(last_close * 1.10, 2)
    limit_up["volume"] = last["volume"] * 0.1
    scenario_bars = bars + [dict(limit_up) for _ in range(3)]
    try:
        sig = strategy.generate_signal(scenario_bars, default_params)
        if sig:
            logger.info("[边界] 涨停场景 → 触发信号: action=%s price=%.2f reason=%s",
                        sig.get("action"), sig.get("price"), sig.get("reason", ""))
        else:
            logger.info("[边界] 涨停场景 → 无信号 (策略静默)")
        result["涨停场景"] = {"信号": _safe_signal(sig), "警告": "涨停板一字板，实盘无法买入"}
    except Exception as e:
        logger.error("[边界] 涨停场景异常: %s", e)
        result["涨停场景"] = {"异常": str(e)}

    # ── 跌停场景 ──
    logger.info("[边界] 跌停场景: 构造连续3日跌停 (%.2f → %.2f)", last_close, round(last_close * 0.90, 2))
    limit_down = last.copy()
    limit_down["open"] = limit_down["high"] = limit_down["low"] = limit_down["close"] = round(last_close * 0.90, 2)
    limit_down["volume"] = last["volume"] * 0.1
    scenario_bars = bars + [dict(limit_down) for _ in range(3)]
    try:
        sig = strategy.generate_signal(scenario_bars, default_params)
        if sig:
            logger.info("[边界] 跌停场景 → 触发信号: action=%s price=%.2f reason=%s",
                        sig.get("action"), sig.get("price"), sig.get("reason", ""))
        else:
            logger.info("[边界] 跌停场景 → 无信号")
        result["跌停场景"] = {"信号": _safe_signal(sig), "警告": "跌停板一字板，实盘无法卖出"}
    except Exception as e:
        logger.error("[边界] 跌停场景异常: %s", e)
        result["跌停场景"] = {"异常": str(e)}

    # ── 大幅波动场景 ──
    logger.info("[边界] 大幅波动场景: 连续3日涨5%/跌8%/涨8%")
    volatile_bars = list(bars)
    for pct in [1.05, 0.92, 1.08]:
        b = volatile_bars[-1].copy()
        b["close"] = round(b["close"] * pct, 2)
        b["high"] = round(b["close"] * 1.03, 2)
        b["low"] = round(b["close"] * 0.97, 2)
        volatile_bars.append(b)
        logger.info("[边界]   追加bar: close=%.2f high=%.2f low=%.2f", b["close"], b["high"], b["low"])
    try:
        sig = strategy.generate_signal(volatile_bars, default_params)
        if sig:
            logger.info("[边界] 大幅波动 → 触发信号: action=%s price=%.2f reason=%s",
                        sig.get("action"), sig.get("price"), sig.get("reason", ""))
        else:
            logger.info("[边界] 大幅波动 → 无信号 (策略在此波动中未触发)")
        result["大幅波动场景"] = {"信号": _safe_signal(sig), "波动": "连续3日涨跌5%/8%/8%"}
    except Exception as e:
        logger.error("[边界] 大幅波动场景异常: %s", e)
        result["大幅波动场景"] = {"异常": str(e)}

    return result


def _safe_signal(signal) -> dict | None:
    if signal is None:
        return None
    return {
        "action": signal.get("action"),
        "price": signal.get("price"),
        "reason": signal.get("reason", ""),
    }


# ============================================================
# 步骤5：量化指标计算
# ============================================================

def _calc_metrics(signal_records: dict, bars: list[dict]) -> dict:
    """从信号记录计算量化指标"""
    buys = signal_records.get("买入信号", [])
    sells = signal_records.get("卖出信号", [])

    empty_metrics = {"累计收益": 0, "最大回撤": 0, "夏普比率": 0, "最大连续亏损": 0, "交易次数": 0, "胜率": 0, "盈亏比": 0}
    if not buys and not sells:
        logger.info("[指标] 无信号，跳过计算")
        return empty_metrics

    trades = _pair_trades(buys, sells, bars)
    if not trades:
        logger.info("[指标] 无配对交易，跳过计算")
        return empty_metrics

    logger.info("[指标] 开始计算 %d 笔交易", len(trades))
    for t in trades:
        pnl = "✅" if t["收益率"] > 0 else "❌"
        logger.info("[指标]   %s %s→%s 买入%.2f 卖出%.2f 收益率=%.2f%%",
                    pnl, t["买入日期"], t["卖出日期"], t["买入价"], t["卖出价"], t["收益率"] * 100)

    returns = [t["收益率"] for t in trades]
    total_return = sum(returns)
    win_trades = [r for r in returns if r > 0]
    lose_trades = [r for r in returns if r <= 0]

    # 最大回撤
    equity = 1.0
    max_equity = 1.0
    max_dd = 0.0
    for r in returns:
        equity *= (1 + r)
        max_equity = max(max_equity, equity)
        dd = (max_equity - equity) / max_equity
        max_dd = max(max_dd, dd)

    # 夏普比率
    if len(returns) >= 2:
        mean_r = sum(returns) / len(returns)
        variance = sum((r - mean_r) ** 2 for r in returns) / (len(returns) - 1)
        std_r = math.sqrt(variance) if variance > 0 else 0
        sharpe = (mean_r / std_r * math.sqrt(252)) if std_r > 0 else 0
    else:
        sharpe = 0

    # 最大连续亏损
    max_consec_loss = 0
    current_streak = 0
    for r in returns:
        if r <= 0:
            current_streak += 1
            max_consec_loss = max(max_consec_loss, current_streak)
        else:
            current_streak = 0

    metrics = {
        "累计收益": round(total_return * 100, 2),
        "最大回撤": round(max_dd, 4),
        "夏普比率": round(sharpe, 2),
        "最大连续亏损": max_consec_loss,
        "交易次数": len(trades),
        "胜率": round(len(win_trades) / len(trades) * 100, 1) if trades else 0,
        "盈亏比": round(sum(win_trades) / abs(sum(lose_trades)), 2) if lose_trades and sum(lose_trades) != 0 else 0,
    }
    logger.info("[指标] 结果: 累计收益=%.2f%% 回撤=%.4f 夏普=%.2f 胜率=%.1f%% 盈亏比=%.2f",
                metrics["累计收益"], metrics["最大回撤"], metrics["夏普比率"], metrics["胜率"], metrics["盈亏比"])
    return metrics


def _pair_trades(buys: list, sells: list, bars: list) -> list:
    """配对买卖信号，每笔买入匹配其后第一个卖出，计算收益率"""
    trades = []
    prices = {str(b["date"])[:10]: b["close"] for b in bars}
    sorted_sells = sorted(sells, key=lambda s: s["日期"])
    sell_idx = 0

    logger.info("[配对] 买入=%d笔 卖出=%d笔 开始配对", len(buys), len(sells))
    for buy in sorted(buys, key=lambda b: b["日期"]):
        buy_date = str(buy["日期"])[:10]
        buy_price = buy.get("价格") or prices.get(buy_date, 0)
        if not buy_price:
            logger.warning("[配对] 买入 %s 无价格，跳过", buy_date)
            continue
        while sell_idx < len(sorted_sells):
            sell = sorted_sells[sell_idx]
            sell_date = str(sell["日期"])[:10]
            if sell_date >= buy_date:
                sell_price = sell.get("价格") or prices.get(sell_date, buy_price)
                ret = (sell_price - buy_price) / buy_price
                trades.append({
                    "买入日期": buy_date,
                    "卖出日期": sell_date,
                    "买入价": buy_price,
                    "卖出价": sell_price,
                    "收益率": round(ret, 4),
                })
                logger.info("[配对] %s 买入%.2f → %s 卖出%.2f 收益=%.2f%%",
                            buy_date, buy_price, sell_date, sell_price, ret * 100)
                sell_idx += 1
                break
            sell_idx += 1

    logger.info("[配对] 完成: %d笔配对交易", len(trades))
    return trades


# ============================================================
# 步骤6：漏洞检测
# ============================================================

def _detect_strategy_bug(signal_records: dict, bars: list[dict]) -> dict:
    """检测未来函数、信号冲突、NaN异常"""
    serious_bug = []
    warnings = []
    logger.info("[漏洞] 开始4项检测")

    # 1. NaN/Inf检测
    logger.info("[漏洞] 检测NaN/Inf...")
    nan_count = 0
    for bar in bars:
        for k in ["open", "high", "low", "close", "volume"]:
            v = bar.get(k)
            if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
                serious_bug.append({
                    "类型": "NaN异常",
                    "日期": str(bar["date"])[:10],
                    "字段": k,
                    "风险": "NaN/Inf值会导致策略逻辑失效",
                })
                nan_count += 1
    logger.info("[漏洞] NaN/Inf: %d处异常", nan_count)

    # 2. 信号冲突检测
    logger.info("[漏洞] 检测信号冲突...")
    buy_dates = {s["日期"] for s in signal_records.get("买入信号", [])}
    sell_dates = {s["日期"] for s in signal_records.get("卖出信号", [])}
    conflicts = buy_dates & sell_dates
    if conflicts:
        logger.warning("[漏洞] 信号冲突: %d个日期同时有买卖信号 %s", len(conflicts), sorted(conflicts))
        serious_bug.append({
            "类型": "信号冲突",
            "冲突日期": sorted(conflicts),
            "风险": "同一交易日同时出现买卖信号，逻辑冲突",
        })
    else:
        logger.info("[漏洞] 信号冲突: 无冲突")

    # 3. 价格异常检测
    logger.info("[漏洞] 检测价格异常(超出OHLC范围)...")
    price_anomalies = 0
    for sig_type in ["买入信号", "卖出信号"]:
        for sig in signal_records.get(sig_type, []):
            sig_date = str(sig["日期"])[:10]
            sig_price = sig.get("价格")
            for bar in bars:
                if str(bar["date"])[:10] == sig_date and sig_price:
                    if sig_price > bar["high"] * 1.001 or sig_price < bar["low"] * 0.999:
                        warnings.append({
                            "类型": "价格异常",
                            "日期": sig_date,
                            "信号价": sig_price,
                            "当日最高": bar["high"],
                            "当日最低": bar["low"],
                            "风险": "信号价格超出当日OHLC范围，可能使用未来数据",
                        })
                        price_anomalies += 1
                        logger.warning("[漏洞] 价格异常 %s: 信号价%.2f 超出[%.2f, %.2f]",
                                       sig_date, sig_price, bar["low"], bar["high"])
                    break
    logger.info("[漏洞] 价格异常: %d处", price_anomalies)

    # 4. 连续同向信号
    logger.info("[漏洞] 检测连续同向信号...")
    buy_seqs = signal_records.get("买入信号", [])
    if len(buy_seqs) >= 3:
        for i in range(len(buy_seqs) - 2):
            d1 = buy_seqs[i]["日期"]
            d2 = buy_seqs[i + 2]["日期"]
            if _days_between(d1, d2) <= 5:
                warnings.append({
                    "类型": "连续买入信号",
                    "区间": f"{d1} ~ {d2}",
                    "风险": "5日内连续3次买入信号，可能过度交易",
                })
                logger.warning("[漏洞] 连续买入: %s ~ %s", d1, d2)
                break
    logger.info("[漏洞] 检测完成: 严重=%d 警告=%d", len(serious_bug), len(warnings))

    return {"serious_bug": serious_bug, "warnings": warnings}


def _days_between(d1: str, d2: str) -> int:
    try:
        dt1 = datetime.strptime(str(d1)[:10], "%Y-%m-%d")
        dt2 = datetime.strptime(str(d2)[:10], "%Y-%m-%d")
        return abs((dt2 - dt1).days)
    except Exception:
        return 999


# ============================================================
# 报告输出
# ============================================================

def _save_report(report: dict, strategy, stock_code: str) -> None:
    """保存JSON报告"""
    strategy_id = getattr(strategy, "ID", strategy.__class__.__name__)
    filename = f"{strategy_id}_{stock_code}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    filepath = os.path.join(REPORTS_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    logger.info("📄 报告已保存: %s", filepath)


# ============================================================
# Mock 数据生成
# ============================================================

def generate_mock_bars(days: int = 200, start_price: float = 10.0) -> list[dict]:
    """生成模拟K线数据，包含涨跌停、大幅波动、金叉死叉等场景"""
    import random
    random.seed(42)
    bars = []
    price = start_price
    base_date = datetime(2024, 1, 2)

    for i in range(days):
        date = base_date + timedelta(days=i)
        if date.weekday() >= 5:  # 跳过周末
            continue

        # 正常波动 ±2%
        change = random.gauss(0.001, 0.02)
        open_p = price * (1 + random.gauss(0, 0.005))
        close_p = price * (1 + change)
        high_p = max(open_p, close_p) * (1 + abs(random.gauss(0, 0.01)))
        low_p = min(open_p, close_p) * (1 - abs(random.gauss(0, 0.01)))
        volume = random.uniform(500000, 2000000)

        # 在特定位置注入极端场景
        day_idx = len(bars) + 1

        if day_idx == 50:  # 连续3日涨停
            close_p = price * 1.10
            open_p = high_p = low_p = close_p
            volume *= 0.1
        elif day_idx == 51:
            close_p = price * 1.10
            open_p = high_p = low_p = close_p
            volume *= 0.1
        elif day_idx == 52:
            close_p = price * 1.10
            open_p = high_p = low_p = close_p
            volume *= 0.1

        if day_idx == 100:  # 连续3日跌停
            close_p = price * 0.90
            open_p = high_p = low_p = close_p
            volume *= 0.1
        elif day_idx == 101:
            close_p = price * 0.90
            open_p = high_p = low_p = close_p
            volume *= 0.1
        elif day_idx == 102:
            close_p = price * 0.90
            open_p = high_p = low_p = close_p
            volume *= 0.1

        if day_idx == 150:  # 大幅波动日
            close_p = price * 1.07
            high_p = price * 1.09
            low_p = price * 0.95
            volume *= 3

        bars.append({
            "date": date.strftime("%Y-%m-%d"),
            "open": round(open_p, 2),
            "high": round(high_p, 2),
            "low": round(low_p, 2),
            "close": round(close_p, 2),
            "volume": int(volume),
        })
        price = close_p

    return bars


# ============================================================
# 测试入口
# ============================================================

if __name__ == "__main__":
    import importlib

    print("=" * 60)
    print("  单只股票标准化审查 - 测试")
    print("=" * 60)

    # 模式选择
    use_mock = "--mock" in sys.argv
    stock_code = "000001"
    start_date = "2024-01-01"
    end_date = "2025-06-30"

    if use_mock:
        print("\n📦 使用 Mock 数据模式")
        stock_code = "MOCK01"
        start_date = "2024-01-02"
        end_date = "2024-12-31"

    # 加载策略
    mod = importlib.import_module("core.strategies.ths_strategies.14_strategies.01_macd_wave")
    MACDWaveStrategy = mod.MACDWaveStrategy
    strategy = MACDWaveStrategy()

    print(f"\n策略: {strategy.NAME}")
    print(f"股票: {stock_code}")
    print(f"区间: {start_date} ~ {end_date}")
    print(f"模式: {'Mock' if use_mock else '真实数据'}")
    print("-" * 60)

    if use_mock:
        # Mock 模式：跳过数据加载，直接构造 bars
        mock_bars = generate_mock_bars(200)
        logger.info("Mock数据: %d条K线, 首日=%s 末日=%s close=%.2f→%.2f",
                     len(mock_bars), mock_bars[0]["date"], mock_bars[-1]["date"],
                     mock_bars[0]["close"], mock_bars[-1]["close"])

        report = {
            "策略": strategy.NAME,
            "股票代码": stock_code,
            "回测区间": f"{start_date} ~ {end_date}",
            "审查时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "数据来源": "Mock模拟数据",
        }

        # 过滤
        filter_result = {"pass": True, "checks": [
            {"item": "ST检查", "status": "PASS", "detail": "MOCK01"},
            {"item": "市场识别", "status": "PASS", "detail": "main"},
            {"item": "流动性检查", "status": "PASS", "detail": "Mock数据跳过"},
        ], "warnings": []}
        report["标的过滤结果"] = filter_result

        # 数据校验
        report["数据校验"] = {"valid": True, "errors": [], "warnings": []}

        # 信号回放
        signal_records = _backtest_step_by_step(strategy, mock_bars)
        report["全部信号记录"] = signal_records

        # 边界场景
        edge_result = _simulate_edge_scenario(strategy, mock_bars)
        report["边界场景测试"] = edge_result

        # 量化指标
        metrics = _calc_metrics(signal_records, mock_bars)
        report["量化指标"] = metrics

        # 漏洞检测
        bug_check = _detect_strategy_bug(signal_records, mock_bars)
        report["漏洞检测"] = bug_check

        if bug_check.get("serious_bug"):
            report["结论"] = "不适配，存在严重漏洞"
        elif metrics["夏普比率"] > 0 and metrics["最大回撤"] < 0.35:
            report["结论"] = "适配该标的"
        else:
            report["结论"] = "条件适配，性能表现一般"

        _save_report(report, strategy, stock_code)

        print(f"\n{'='*60}")
        print(f"  审查完成")
        print(f"  结论: {report['结论']}")
        print(f"{'='*60}")

        print(f"\n📊 量化指标:")
        print(f"  累计收益: {metrics.get('累计收益', 0)}%")
        print(f"  最大回撤: {metrics.get('最大回撤', 0)}")
        print(f"  夏普比率: {metrics.get('夏普比率', 0)}")
        print(f"  交易次数: {metrics.get('交易次数', 0)}")
        print(f"  胜率: {metrics.get('胜率', 0)}%")

        print(f"\n🔬 边界场景:")
        for s, d in edge_result.items():
            if "error" in d:
                print(f"  {s}: ❌ {d['error']}")
            else:
                sig = d.get("信号", {})
                print(f"  {s}: {sig.get('action', '无信号') if sig else '无信号'}")

        if bug_check.get("serious_bug"):
            print(f"\n⚠️ 严重漏洞: {len(bug_check['serious_bug'])}个")
            for b in bug_check["serious_bug"]:
                print(f"  - [{b['类型']}] {b.get('风险', '')}")
        if bug_check.get("warnings"):
            print(f"\n⚡ 警告: {len(bug_check['warnings'])}个")
            for w in bug_check["warnings"]:
                print(f"  - [{w['类型']}] {w.get('风险', '')}")

    else:
        t0 = time.time()
        report = single_stock_review(strategy, stock_code, start_date, end_date)
        elapsed = time.time() - t0

        print(f"\n{'='*60}")
        print(f"  审查完成 (耗时 {elapsed:.1f}s)")
        print(f"  结论: {report['结论']}")
        print(f"{'='*60}")

        metrics = report.get("量化指标", {})
        print(f"\n📊 量化指标:")
        print(f"  累计收益: {metrics.get('累计收益', 'N/A')}%")
        print(f"  最大回撤: {metrics.get('最大回撤', 'N/A')}")
        print(f"  夏普比率: {metrics.get('夏普比率', 'N/A')}")
        print(f"  最大连续亏损: {metrics.get('最大连续亏损', 'N/A')}次")
        print(f"  交易次数: {metrics.get('交易次数', 'N/A')}")

        bug = report.get("漏洞检测", {})
        if bug.get("serious_bug"):
            print(f"\n⚠️ 严重漏洞: {len(bug['serious_bug'])}个")
            for b in bug["serious_bug"]:
                print(f"  - [{b['类型']}] {b.get('风险', '')}")
        if bug.get("warnings"):
            print(f"\n⚡ 警告: {len(bug['warnings'])}个")
            for w in bug["warnings"]:
                print(f"  - [{w['类型']}] {w.get('风险', '')}")

        edge = report.get("边界场景测试", {})
        print(f"\n🔬 边界场景测试:")
        for scenario, r in edge.items():
            if "error" in r:
                print(f"  {scenario}: ❌ {r['error']}")
            else:
                sig = r.get("信号", {})
                print(f"  {scenario}: {sig.get('action', '无信号') if sig else '无信号'}")