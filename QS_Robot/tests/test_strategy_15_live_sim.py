"""策略15 实盘模拟连续运行测试

模拟实盘环境下的连续运行，验证：
  1. 闪崩检测：多标的同时监控，闪崩事件自动触发止损
  2. 跌停检测：模拟跌停板行情，验证强制离场
  3. 持仓追踪：入场→止损/止盈→出场完整链路
  4. 风控告警：结构化告警输出 + 日志
  5. 连续运行：多日连续模拟，无内存泄漏/状态污染

运行方式：
  python tests/test_strategy_15_live_sim.py                    # 默认20标的×60分钟
  python tests/test_strategy_15_live_sim.py --stocks 10 --duration 30
  python tests/test_strategy_15_live_sim.py --scenario stress  # 仅压力场景
"""
import sys
import os
import random
import logging
import json
import time
import argparse
from datetime import datetime, timedelta
from collections import defaultdict

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("LiveSim")

import importlib
_mod = importlib.import_module(
    "core.strategies.ths_strategies.14_strategies.15_low_first_board"
)
LowFirstBoardStrategy = _mod.LowFirstBoardStrategy
PositionManager = _mod.PositionManager

from tools.risk_monitor import RiskMonitor

# ========== 模拟股票池 ==========

STOCK_POOL = [
    ("000001", 12.50, 8_000_000),  # (代码, 昨收, 日均量)
    ("000002", 18.30, 12_000_000),
    ("000858", 145.00, 6_000_000),
    ("600519", 1680.00, 2_000_000),
    ("600036", 38.50, 15_000_000),
    ("601318", 52.00, 10_000_000),
    ("000725", 5.80, 30_000_000),
    ("002415", 35.20, 8_000_000),
    ("300750", 220.00, 5_000_000),
    ("600030", 22.00, 20_000_000),
    ("601398", 5.50, 50_000_000),
    ("000333", 65.00, 7_000_000),
    ("601166", 18.00, 12_000_000),
    ("600900", 24.00, 8_000_000),
    ("000651", 42.00, 6_000_000),
    ("002594", 280.00, 3_000_000),
    ("601899", 8.50, 25_000_000),
    ("600585", 28.00, 9_000_000),
    ("000568", 200.00, 4_000_000),
    ("002475", 38.00, 7_000_000),
]

# ========== 行情场景 ==========

SCENARIOS = {
    "normal": {"drift": 0.0002, "noise": 0.002, "vol_mult": 1.0, "weight": 0.70},
    "bullish": {"drift": 0.001, "noise": 0.003, "vol_mult": 1.5, "weight": 0.10},
    "bearish": {"drift": -0.0008, "noise": 0.003, "vol_mult": 1.3, "weight": 0.08},
    "flash_crash": {"drift": -0.015, "noise": 0.005, "vol_mult": 3.0, "weight": 0.05},
    "limit_down": {"drift": -0.02, "noise": 0.003, "vol_mult": 2.0, "weight": 0.04},
    "volatile": {"drift": 0.0, "noise": 0.008, "vol_mult": 2.0, "weight": 0.03},
}


def pick_scenario(rng: random.Random) -> str:
    """按权重随机选择场景"""
    weights = [SCENARIOS[s]["weight"] for s in SCENARIOS]
    return rng.choices(list(SCENARIOS.keys()), weights=weights, k=1)[0]


def generate_bar(prev_close: float, prev_price: float, scenario: str,
                 rng: random.Random, minute: int, daily_avg_vol: float) -> dict:
    """生成一根1分钟K线"""
    cfg = SCENARIOS[scenario]

    if scenario == "flash_crash" and minute < 5:
        drift = 0.0
    elif scenario == "flash_crash":
        drift = cfg["drift"] * prev_close
    elif scenario == "limit_down":
        limit_down_price = prev_close * 0.902
        drift = max(cfg["drift"] * prev_close, (limit_down_price - prev_price) * 0.3)
    else:
        drift = cfg["drift"] * prev_close

    noise = rng.gauss(0, cfg["noise"] * prev_close)
    close = prev_price + drift + noise

    if close <= 0.01:
        close = 0.01
    if scenario == "limit_down":
        close = max(close, prev_close * 0.901)

    high = max(prev_price, close) * (1 + abs(rng.gauss(0, 0.0005)))
    low = min(prev_price, close) * (1 - abs(rng.gauss(0, 0.0005)))

    base_vol = daily_avg_vol / 240
    volume = int(base_vol * cfg["vol_mult"] * rng.uniform(0.5, 2.0))

    if scenario == "flash_crash":
        volume = int(volume * 3.0)

    return {
        "minute": minute,
        "open": round(prev_price, 3),
        "high": round(high, 3),
        "low": round(low, 3),
        "close": round(close, 3),
        "volume": volume,
        "prev_close": prev_close,
    }


# ========== 模拟交易引擎 ==========

class SimulatedTradingEngine:
    """模拟实盘交易引擎：管理多标的、多策略、风控监控"""

    def __init__(self, stocks: list[tuple], seed: int = 42):
        self.rng = random.Random(seed)
        self.stocks = {s[0]: {"prev_close": s[1], "daily_avg_vol": s[2]} for s in stocks}
        self.strategy = LowFirstBoardStrategy()
        self.pm = PositionManager(stop_loss_pct=0.04, take_profit_pct=0.07,
                                  time_stop_minute=235, slippage=0.001)
        self.standalone_rm = RiskMonitor()  # 独立风控实例（用于对比验证）

        self.trade_history: list[dict] = []
        self.alert_history: list[dict] = []
        self.current_day = 0
        self.total_minutes = 0

        # 初始化独立风控的昨收和均量
        for symbol, info in self.stocks.items():
            self.standalone_rm.set_prev_close(symbol, info["prev_close"])
            self.standalone_rm.set_daily_avg_vol(symbol, info["daily_avg_vol"])

    def reset_day(self, day: int):
        """新交易日重置"""
        self.current_day = day
        self.strategy.reset_risk_monitor()
        self.pm = PositionManager(stop_loss_pct=0.04, take_profit_pct=0.07)
        self.standalone_rm = RiskMonitor()
        for symbol, info in self.stocks.items():
            self.standalone_rm.set_prev_close(symbol, info["prev_close"])
            self.standalone_rm.set_daily_avg_vol(symbol, info["daily_avg_vol"])

    def run_minute(self, minute: int, scenario: str) -> dict:
        """运行一个交易分钟，返回本分钟事件摘要"""
        self.total_minutes += 1
        events = {"minute": minute, "alerts": [], "trades": []}

        for symbol, info in self.stocks.items():
            prev_close = info["prev_close"]
            daily_avg_vol = info["daily_avg_vol"]

            # 当前价格（模拟连续行情）
            prev_price = self._get_last_price(symbol, prev_close)
            bar = generate_bar(prev_close, prev_price, scenario, self.rng,
                             minute, daily_avg_vol)
            bar["symbol"] = symbol
            self._price_cache[symbol] = bar["close"]

            # 1. 喂入独立风控（对比基准）
            self.standalone_rm.feed(symbol, {
                "price": bar["close"],
                "volume": bar["volume"],
                "time": f"D{self.current_day} {minute // 60:02d}:{minute % 60:02d}",
            })

            # 2. 喂入策略内嵌风控
            self.strategy.set_symbol(symbol)
            strategy_alerts = self.strategy.feed_risk_monitor(bar)
            for a in strategy_alerts:
                events["alerts"].append({"source": "strategy_rm", **a})

            # 3. 检查入场
            if not self.pm.has_position() and not self.pm.traded_today:
                if self._should_enter(bar, minute, scenario):
                    self.pm.enter(bar["close"], minute, date=f"D{self.current_day}")
                    self.strategy.risk_monitor.open_position(
                        symbol, bar["close"],
                        stop_loss_pct=-0.04, take_profit_pct=0.07,
                    )
                    self.standalone_rm.open_position(
                        symbol, bar["close"],
                        stop_loss_pct=-0.04, take_profit_pct=0.07,
                    )
                    events["trades"].append({
                        "action": "ENTRY", "symbol": symbol,
                        "price": bar["close"], "minute": minute,
                    })

            # 4. 检查出场
            if self.pm.has_position():
                exit_sig = self.pm.check_exit(bar)
                if exit_sig:
                    self.standalone_rm.close_position(symbol)
                    events["trades"].append({
                        "action": exit_sig["reason"], "symbol": symbol,
                        "price": exit_sig["price"], "pnl_pct": exit_sig["pnl_pct"],
                        "minute": minute,
                    })

        # 收集独立风控告警
        standalone_alerts = self.standalone_rm.get_alerts(clear=True)
        for a in standalone_alerts:
            events["alerts"].append({"source": "standalone_rm", **a})

        return events

    _price_cache: dict[str, float] = {}

    def _get_last_price(self, symbol: str, prev_close: float) -> float:
        return self._price_cache.get(symbol, prev_close * 1.005)

    def _should_enter(self, bar: dict, minute: int, scenario: str) -> bool:
        """简化入场条件：涨幅2-5% + 随机概率"""
        if minute < 10 or minute > 200:
            return False
        if scenario in ("flash_crash", "limit_down"):
            return False
        gain = (bar["close"] - bar["prev_close"]) / bar["prev_close"]
        if not (0.02 < gain < 0.05):
            return False
        return self.rng.random() < 0.08  # 8%概率入场

    def get_summary(self) -> dict:
        """获取运行摘要"""
        pm_summary = self.pm.get_summary()
        strategy_risk = self.strategy.get_risk_summary()
        standalone_risk = self.standalone_rm.get_summary()

        return {
            "days": self.current_day + 1,
            "total_minutes": self.total_minutes,
            "position_manager": pm_summary,
            "strategy_risk_monitor": strategy_risk,
            "standalone_risk_monitor": standalone_risk,
            "total_trades": len(self.trade_history),
            "total_alerts": len(self.alert_history),
        }


# ========== 测试场景 ==========

def run_live_simulation(stocks: list[tuple], total_minutes: int = 240,
                        seed: int = 42, verbose: bool = True) -> dict:
    """运行实盘模拟"""
    engine = SimulatedTradingEngine(stocks, seed=seed)
    rng = random.Random(seed + 1)

    flash_crash_detected = 0
    limit_down_detected = 0
    stop_loss_triggered = 0
    take_profit_triggered = 0

    day = 0
    minute_in_day = 0

    logger.info("=" * 60)
    logger.info("🚀 实盘模拟启动 | %d标的 × %d分钟", len(stocks), total_minutes)
    logger.info("=" * 60)

    for total_min in range(total_minutes):
        if minute_in_day >= 240:
            day += 1
            minute_in_day = 0
            engine.reset_day(day)
            logger.info("--- 新交易日 D%d ---", day)

        scenario = pick_scenario(rng)
        events = engine.run_minute(minute_in_day, scenario)
        minute_in_day += 1

        for alert in events["alerts"]:
            engine.alert_history.append(alert)
            if alert["category"] == "flash_crash":
                flash_crash_detected += 1
            elif alert["category"] == "limit_down":
                limit_down_detected += 1

        for trade in events["trades"]:
            engine.trade_history.append(trade)
            if trade.get("action") == "STOP_LOSS" or trade.get("reason") == "stop_loss":
                stop_loss_triggered += 1
            elif trade.get("action") == "TAKE_PROFIT" or trade.get("reason") == "take_profit":
                take_profit_triggered += 1

        # 每60分钟输出状态
        if verbose and total_min % 60 == 0 and total_min > 0:
            summary = engine.get_summary()
            logger.info("[%3dmin] 交易=%d 止损=%d 止盈=%d 闪崩告警=%d 跌停告警=%d",
                       total_min, summary["position_manager"]["trades"],
                       summary["position_manager"]["stop_losses"],
                       summary["position_manager"]["take_profits"],
                       flash_crash_detected, limit_down_detected)

    # 最终摘要
    summary = engine.get_summary()
    logger.info("=" * 60)
    logger.info("🏁 模拟完成 | %d天 %d分钟", summary["days"], summary["total_minutes"])
    logger.info("  交易: 入场%d 止损%d 止盈%d 时间止损%d 跌停出场%d",
               summary["position_manager"]["trades"],
               summary["position_manager"]["stop_losses"],
               summary["position_manager"]["take_profits"],
               summary["position_manager"]["time_stops"],
               summary["position_manager"]["limit_down_exits"])
    logger.info("  风控告警: 闪崩%d 跌停%d 总告警%d",
               flash_crash_detected, limit_down_detected,
               summary["total_alerts"])
    logger.info("  策略风控: %d告警 %d持仓",
               summary["strategy_risk_monitor"]["total_alerts"],
               summary["strategy_risk_monitor"]["active_positions"])
    logger.info("=" * 60)

    return {
        "summary": summary,
        "flash_crash_detected": flash_crash_detected,
        "limit_down_detected": limit_down_detected,
        "stop_loss_triggered": stop_loss_triggered,
        "take_profit_triggered": take_profit_triggered,
        "trades": engine.trade_history[-20:],
        "alerts": engine.alert_history[-20:],
    }


# ========== 专项压力测试 ==========

def run_stress_test():
    """闪崩+跌停专项压力测试"""
    logger.info("\n" + "=" * 60)
    logger.info("⚡ 专项压力测试：闪崩 + 跌停")
    logger.info("=" * 60)

    results = {}

    # 测试1: 单标的闪崩场景
    logger.info("\n--- 测试1: 单标的闪崩 ---")
    rm = RiskMonitor()
    rm.set_prev_close("TEST01", 10.00)
    rm.set_daily_avg_vol("TEST01", 5_000_000)

    prices = [10.02, 10.05, 10.08, 10.10, 10.12, 9.50]  # 最后一下闪崩
    for i, p in enumerate(prices):
        rm.feed("TEST01", {"price": p, "volume": 1_000_000, "time": f"09:3{i}"})

    alerts = rm.get_alerts()
    flash_crash_alerts = [a for a in alerts if a["category"] == "flash_crash"]
    results["flash_crash_single"] = {
        "passed": len(flash_crash_alerts) >= 1,
        "alerts": flash_crash_alerts,
    }
    logger.info("  闪崩告警: %d个 → %s",
               len(flash_crash_alerts),
               "✅ PASS" if results["flash_crash_single"]["passed"] else "❌ FAIL")

    # 测试2: 持仓闪崩自动止损
    logger.info("\n--- 测试2: 持仓闪崩止损 ---")
    rm2 = RiskMonitor()
    rm2.set_prev_close("TEST02", 10.00)
    rm2.open_position("TEST02", 10.10, stop_loss_pct=-0.04, take_profit_pct=0.07)

    prices2 = [10.08, 10.05, 9.95, 9.65, 9.60]  # 跌破止损线
    for i, p in enumerate(prices2):
        rm2.feed("TEST02", {"price": p, "volume": 500_000, "time": f"09:4{i}"})

    alerts2 = rm2.get_alerts()
    stop_loss_alerts = [a for a in alerts2 if a["category"] == "stop_loss"]
    flash_crash_alerts2 = [a for a in alerts2 if a["category"] == "flash_crash"]
    results["position_flash_crash"] = {
        "passed": len(stop_loss_alerts) >= 1 or len(flash_crash_alerts2) >= 1,
        "stop_loss": len(stop_loss_alerts),
        "flash_crash": len(flash_crash_alerts2),
    }
    logger.info("  止损告警: %d 闪崩告警: %d → %s",
               len(stop_loss_alerts), len(flash_crash_alerts2),
               "✅ PASS" if results["position_flash_crash"]["passed"] else "❌ FAIL")

    # 测试3: 跌停检测
    logger.info("\n--- 测试3: 跌停检测 ---")
    rm3 = RiskMonitor()
    rm3.set_prev_close("TEST03", 10.00)
    rm3.set_daily_avg_vol("TEST03", 5_000_000)

    prices3 = [9.80, 9.50, 9.30, 9.10, 9.02]  # 逐步逼近跌停
    for i, p in enumerate(prices3):
        rm3.feed("TEST03", {"price": p, "volume": 2_000_000, "time": f"09:3{i}"})

    alerts3 = rm3.get_alerts()
    limit_down_alerts = [a for a in alerts3 if a["category"] == "limit_down"]
    results["limit_down"] = {
        "passed": len(limit_down_alerts) >= 1,
        "alerts": limit_down_alerts,
    }
    logger.info("  跌停告警: %d个 → %s",
               len(limit_down_alerts),
               "✅ PASS" if results["limit_down"]["passed"] else "❌ FAIL")

    # 测试4: 持仓跌停强制离场
    logger.info("\n--- 测试4: 持仓跌停强制离场 ---")
    rm4 = RiskMonitor()
    rm4.set_prev_close("TEST04", 10.00)
    rm4.open_position("TEST04", 9.80, stop_loss_pct=-0.04, take_profit_pct=0.07)

    prices4 = [9.60, 9.30, 9.10, 9.02, 9.01]  # 跌停板
    for i, p in enumerate(prices4):
        rm4.feed("TEST04", {"price": p, "volume": 3_000_000, "time": f"09:4{i}"})

    alerts4 = rm4.get_alerts()
    limit_down4 = [a for a in alerts4 if a["category"] == "limit_down"]
    stop_loss4 = [a for a in alerts4 if a["category"] == "stop_loss"]
    results["position_limit_down"] = {
        "passed": len(limit_down4) >= 1 or len(stop_loss4) >= 1,
        "limit_down": len(limit_down4),
        "stop_loss": len(stop_loss4),
    }
    logger.info("  跌停告警: %d 止损告警: %d → %s",
               len(limit_down4), len(stop_loss4),
               "✅ PASS" if results["position_limit_down"]["passed"] else "❌ FAIL")

    # 测试5: 多标的混合场景
    logger.info("\n--- 测试5: 多标的混合场景 ---")
    rm5 = RiskMonitor()
    symbols = [("MIX01", 10.00, 5_000_000), ("MIX02", 20.00, 3_000_000),
               ("MIX03", 50.00, 2_000_000)]
    for sym, prev, avg_vol in symbols:
        rm5.set_prev_close(sym, prev)
        rm5.set_daily_avg_vol(sym, avg_vol)

    # 喂入混合行情
    for i in range(20):
        for sym, prev, _ in symbols:
            if sym == "MIX01" and i > 10:
                p = prev * (1 - i * 0.008)
            elif sym == "MIX02" and i > 15:
                p = prev * 0.91
            else:
                p = prev * (1 + random.gauss(0, 0.003))
            rm5.feed(sym, {"price": round(p, 3), "volume": 500_000,
                          "time": f"09:{30+i:02d}"})

    summary5 = rm5.get_summary()
    results["multi_symbol"] = {
        "passed": summary5["monitored_symbols"] == 3,
        "summary": summary5,
    }
    logger.info("  监控标的: %d 告警: %d(critical=%d) → %s",
               summary5["monitored_symbols"], summary5["total_alerts"],
               summary5["critical"],
               "✅ PASS" if results["multi_symbol"]["passed"] else "❌ FAIL")

    # 测试6: 连续运行内存/状态泄漏检查
    logger.info("\n--- 测试6: 连续运行状态检查 ---")
    rm6 = RiskMonitor()
    rm6.set_prev_close("LEAK01", 10.00)
    for i in range(500):
        p = 10.00 + random.gauss(0, 0.05)
        rm6.feed("LEAK01", {"price": round(p, 3), "volume": 100_000,
                           "time": f"09:{i % 60:02d}"})

    history_len = len(rm6.price_history.get("LEAK01", []))
    results["no_leak"] = {
        "passed": history_len <= 120,  # 不应超过120条
        "history_len": history_len,
    }
    logger.info("  历史长度: %d (上限120) → %s",
               history_len,
               "✅ PASS" if results["no_leak"]["passed"] else "❌ FAIL")

    # 汇总
    total = len(results)
    passed = sum(1 for r in results.values() if r["passed"])
    logger.info("\n" + "=" * 60)
    logger.info("📊 压力测试结果: %d/%d 通过", passed, total)
    for name, r in results.items():
        status = "✅" if r["passed"] else "❌"
        logger.info("  %s %s", status, name)
    logger.info("=" * 60)

    return {"total": total, "passed": passed, "results": results}


# ========== 主入口 ==========

def main():
    parser = argparse.ArgumentParser(description="策略15 实盘模拟连续运行测试")
    parser.add_argument("--stocks", type=int, default=20,
                       help="模拟标的数量 (默认20)")
    parser.add_argument("--duration", type=int, default=240,
                       help="模拟运行分钟数 (默认240=1个交易日)")
    parser.add_argument("--seed", type=int, default=42,
                       help="随机种子 (默认42)")
    parser.add_argument("--scenario", type=str, default="all",
                       choices=["all", "stress", "normal"],
                       help="测试场景 (默认all)")
    parser.add_argument("--output", type=str, default="",
                       help="结果输出JSON文件路径")
    parser.add_argument("--quiet", action="store_true",
                       help="安静模式，减少日志输出")
    args = parser.parse_args()

    if args.quiet:
        logging.getLogger().setLevel(logging.WARNING)

    start_time = time.time()
    all_passed = True

    if args.scenario in ("all", "stress"):
        stress_result = run_stress_test()
        all_passed = all_passed and (stress_result["passed"] == stress_result["total"])

    if args.scenario in ("all", "normal"):
        stocks = STOCK_POOL[:args.stocks]
        live_result = run_live_simulation(
            stocks, total_minutes=args.duration,
            seed=args.seed, verbose=not args.quiet,
        )
        # 验证关键指标
        summary = live_result["summary"]
        pm = summary["position_manager"]
        if pm["trades"] > 0:
            if pm["stop_losses"] > 0:
                logger.info("✅ 止损保护有效（%d次触发）", pm["stop_losses"])
            if pm["take_profits"] > 0:
                logger.info("✅ 止盈机制有效（%d次触发）", pm["take_profits"])

        if live_result["flash_crash_detected"] > 0:
            logger.info("✅ 闪崩检测有效（%d次告警）", live_result["flash_crash_detected"])
        if live_result["limit_down_detected"] > 0:
            logger.info("✅ 跌停检测有效（%d次告警）", live_result["limit_down_detected"])

    elapsed = time.time() - start_time
    logger.info("\n⏱️ 总耗时: %.1f秒", elapsed)

    if args.output:
        output_data = {
            "timestamp": datetime.now().isoformat(),
            "config": {"stocks": args.stocks, "duration": args.duration,
                      "seed": args.seed, "scenario": args.scenario},
            "elapsed_seconds": round(elapsed, 1),
        }
        if args.scenario in ("all", "stress"):
            output_data["stress_test"] = {
                k: v for k, v in stress_result["results"].items()
            }
        if args.scenario in ("all", "normal"):
            output_data["live_simulation"] = live_result["summary"]
        os.makedirs(os.path.join(PROJECT_ROOT, "reports", "live_sim"), exist_ok=True)
        path = args.output or os.path.join(
            PROJECT_ROOT, "reports", "live_sim",
            f"live_sim_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        with open(path, "w", encoding="utf-8") as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)
        logger.info("📄 报告已保存: %s", path)

    if all_passed:
        logger.info("\n✅ 全部测试通过")
    else:
        logger.warning("\n⚠️ 部分测试未通过，请检查详细日志")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())