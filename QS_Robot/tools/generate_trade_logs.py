"""6策略详细交易日志生成器

对每只股票逐bar扫描，记录每次入场条件的完整市场状态。
输出到 logs/trade_signal_audit.log，方便排查触发率低的原因。
"""
import sys
import os
import logging
import random
from pathlib import Path
from collections import defaultdict
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.strategies.ths_strategies.base import THSBaseStrategy
from core.strategies.ths_strategies._indicators import sma, ema, dmi

# 6个目标策略
TARGET_IDS = [
    "01_macd_wave", "03_dragon_head", "05_ma_long_arrangement",
    "06_expma_double_cross", "07_macd_zero_second_cross", "08_volume_ladder",
]


def fetch_real_kline(symbol: str, days: int = 200) -> list[dict] | None:
    try:
        from core.data_fetcher import get_data_fetcher
        fetcher = get_data_fetcher()
        data = fetcher.get_kline(symbol, period="daily", days=days)
        if not data or data.get("count", 0) < 60:
            return None
        closes = data.get("closes", [])
        opens = data.get("opens", [])
        highs = data.get("highs", [])
        lows = data.get("lows", [])
        vols = data.get("volumes", [])
        dates = data.get("dates", [])
        n = min(len(closes), len(opens), len(highs), len(lows), len(vols))
        return [{
            "date": str(dates[i]) if i < len(dates) else f"D{i}",
            "open": float(opens[i]), "close": float(closes[i]),
            "high": float(highs[i]), "low": float(lows[i]),
            "volume": float(vols[i]),
        } for i in range(n)]
    except Exception as e:
        print(f"  [WARN] {symbol}: {e}")
        return None


def inject_external(bars: list[dict], symbol: str) -> list[dict]:
    rng = random.Random(hash(symbol) + 42)
    for bar in bars:
        bar["north_inflow"] = rng.uniform(5, 80) if rng.random() < 0.35 else rng.uniform(-20, 8)
        bar["sector_concentrated"] = rng.random() < 0.40
        bar["dragon_list"] = {"quant_net_buy": rng.uniform(100, 5000) if rng.random() < 0.25 else 0}
        bar["profit_growth"] = rng.uniform(-30, 80) if rng.random() < 0.60 else rng.uniform(-50, -5)
        bar["market_cap"] = rng.uniform(20, 80) if rng.random() < 0.70 else rng.uniform(5, 200)
        bar["circulating_cap"] = bar["market_cap"] * rng.uniform(0.6, 0.95)
        bar["is_st"] = rng.random() < 0.05
        bar["main_inflow"] = rng.uniform(100, 10000) if rng.random() < 0.40 else rng.uniform(-5000, 0)
        bar["sector"] = {
            "limit_up_count": rng.randint(1, 8) if rng.random() < 0.50 else 0,
            "pct_change": rng.uniform(-2, 4),
        }
        bar["sandwich"] = rng.random() < 0.35
        bar["big_support"] = rng.random() < 0.35
        bar["ddy_red"] = rng.random() < 0.35
        bar["independent"] = rng.random() < 0.35
        bar["all_matched"] = rng.random() < 0.50
    return bars


def compute_market_state(bars: list[dict], idx: int) -> dict:
    """计算指定bar位置的完整市场状态"""
    window = bars[:idx + 1]
    closes = [b["close"] for b in window]
    highs = [b["high"] for b in window]
    lows = [b["low"] for b in window]
    vols = [b["volume"] for b in window]
    last = window[-1]

    state = {
        "date": str(last.get("date", "")),
        "close": round(last["close"], 2),
        "open": round(last["open"], 2),
        "high": round(last["high"], 2),
        "low": round(last["low"], 2),
        "volume": int(last["volume"]),
        "body_pct": round((last["close"] - last["open"]) / last["open"] * 100, 2),
    }

    if len(closes) >= 5:
        state["ma5"] = round(sma(closes, 5), 2)
    if len(closes) >= 10:
        state["ma10"] = round(sma(closes, 10), 2)
    if len(closes) >= 20:
        state["ma20"] = round(sma(closes, 20), 2)
        state["vol_ma20"] = round(sma(vols, 20), 1)
    if len(closes) >= 60:
        state["ma60"] = round(sma(closes, 60), 2)

    if len(closes) >= 26:
        exp7 = ema(closes, 7)
        exp21 = ema(closes, 21)
        state["exp7"] = round(exp7[-1], 2)
        state["exp21"] = round(exp21[-1], 2)
        if len(exp7) >= 2:
            state["exp7_prev"] = round(exp7[-2], 2)
            state["exp21_prev"] = round(exp21[-2], 2)

    if len(highs) >= 14:
        _, _, adx_val = dmi(highs, lows, closes, 14)
        state["adx"] = round(adx_val, 1)

    if len(closes) >= 26:
        dif = ema(closes, 12)
        dea = ema(dif, 9)
        state["dif"] = round(dif[-1], 4)
        state["dea"] = round(dea[-1], 4)
        if len(dif) >= 2:
            state["macd_hist"] = round(2 * (dif[-1] - dea[-1]), 4)
            state["macd_hist_prev"] = round(2 * (dif[-2] - dea[-2]), 4)

    state["north_inflow"] = round(last.get("north_inflow", 0), 1)
    state["main_inflow"] = round(last.get("main_inflow", 0), 1)

    return state


def scan_strategy(strategy, bars: list[dict]) -> list[dict]:
    """逐bar扫描策略，收集每次调用的详细结果"""
    events = []
    for i in range(25, len(bars)):
        window = bars[:i + 1]
        try:
            signal = strategy.generate_signal(window, {})
        except Exception as e:
            continue
        if signal:
            state = compute_market_state(bars, i)
            state["signal"] = signal
            events.append(state)
    return events


def main():
    logging.getLogger("ths").setLevel(logging.WARNING)

    # 加载策略
    import importlib
    base = Path(r"d:\Gupiao\升级vscode\QS_Robot\core\strategies\ths_strategies")
    strategies = {}
    for subdir, prefix in [("14_strategies", "14_strategies"), ("18_advanced", "18_advanced")]:
        d = base / subdir
        for f in sorted(d.glob("*.py")):
            if f.name.startswith("_"):
                continue
            mod = importlib.import_module(f"core.strategies.ths_strategies.{prefix}.{f.stem}")
            for name in dir(mod):
                cls = getattr(mod, name)
                if (isinstance(cls, type) and issubclass(cls, THSBaseStrategy)
                        and cls is not THSBaseStrategy and cls.ID in TARGET_IDS):
                    strategies[cls.ID] = cls()

    print(f"已加载 {len(strategies)} 个目标策略")

    # 股票池
    stocks = [
        "000001", "000333", "000858", "002594", "300750",
        "600519", "600036", "600276", "601318", "002415",
    ]

    # 日志文件
    log_dir = Path(r"d:\Gupiao\升级vscode\QS_Robot\logs")
    log_dir.mkdir(exist_ok=True)
    log_path = log_dir / "trade_signal_audit.log"
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    with open(log_path, "w", encoding="utf-8") as f:
        f.write(f"# 6策略交易信号审计日志 | 生成时间: {ts}\n")
        f.write(f"# 策略: {', '.join(TARGET_IDS)}\n")
        f.write(f"# 股票: {', '.join(stocks)}\n")
        f.write("=" * 100 + "\n\n")

        total_buy = defaultdict(int)
        total_sell = defaultdict(int)
        total_bars = 0

        for symbol in stocks:
            bars = fetch_real_kline(symbol, days=200)
            if not bars:
                print(f"  ❌ {symbol} 跳过")
                continue
            bars = inject_external(bars, symbol)
            total_bars += len(bars)
            print(f"  ✅ {symbol} ({len(bars)} 条)")

            f.write(f"## {symbol} | {len(bars)} bars\n")
            f.write(f"  日期范围: {bars[0]['date']} ~ {bars[-1]['date']}\n\n")

            for sid, s in strategies.items():
                events = scan_strategy(s, bars)
                buys = [e for e in events if e["signal"]["action"] == "buy"]
                sells = [e for e in events if e["signal"]["action"] == "sell"]
                total_buy[sid] += len(buys)
                total_sell[sid] += len(sells)

                f.write(f"### {s.NAME} ({sid})\n")
                f.write(f"  总bar数: {len(bars)}, 买入: {len(buys)}, 卖出: {len(sells)}\n")

                if buys:
                    f.write(f"\n  **买入信号 ({len(buys)} 次):**\n")
                    for e in buys[:5]:  # 最多展示5次
                        sg = e["signal"]
                        f.write(f"  - [{e['date']}] 价格={sg['price']:.2f} "
                                f"止损={sg['stop_loss']:.2f} 止盈={sg['take_profit']:.2f}\n")
                        f.write(f"    MA5={e.get('ma5','N/A')} MA10={e.get('ma10','N/A')} "
                                f"MA20={e.get('ma20','N/A')} ADX={e.get('adx','N/A')}\n")
                        f.write(f"    量={e['volume']} 量比={e.get('vol_ma20',0) and round(e['volume']/e['vol_ma20'],1) if e.get('vol_ma20') else 'N/A'}\n")
                        f.write(f"    实体={e['body_pct']}% MACD柱={e.get('macd_hist','N/A')}\n")

                if sells:
                    f.write(f"\n  **卖出信号 ({len(sells)} 次):**\n")
                    for e in sells[:3]:
                        sg = e["signal"]
                        f.write(f"  - [{e['date']}] 价格={sg['price']:.2f} 原因={sg.get('reason','?')}\n")

                if not buys and not sells:
                    f.write(f"  (无信号)\n")
                f.write("\n")

        # 汇总
        f.write("=" * 100 + "\n")
        f.write("## 汇总\n\n")
        f.write(f"| 策略 | 总bar | 买入 | 卖出 | 买入频率 |\n")
        f.write(f"|------|------:|-----:|-----:|------:|\n")
        for sid in TARGET_IDS:
            if sid in strategies:
                n_bars = total_bars // len(strategies)
                freq = f"{total_buy[sid]/n_bars*100:.1f}%" if n_bars > 0 else "0%"
                f.write(f"| {sid} | {n_bars} | {total_buy[sid]} | {total_sell[sid]} | {freq} |\n")

    print(f"\n日志已写入: {log_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())