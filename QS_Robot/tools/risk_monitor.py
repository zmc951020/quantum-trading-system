"""实盘风控监控模块：闪崩/跌停/异常波动实时检测

监控维度：
  1. 闪崩检测：N分钟内跌幅超过阈值（默认5分钟跌超-5%）
  2. 跌停检测：价格触及跌停板（A股±10%）
  3. 异常波动：价格振幅超过阈值（默认>15%）
  4. 止损追踪：对已持仓标的实时监控止损/止盈线
  5. 流动性枯竭：成交量骤降（默认<20日均量×0.3）

输出：结构化告警JSON + 日志 + 可选Webhook推送

使用方式：
    monitor = RiskMonitor()
    monitor.feed("000001", {"price": 10.50, "volume": 500000, "time": "09:35"})
    monitor.feed("000001", {"price": 9.50, "volume": 2000000, "time": "09:40"})
    alerts = monitor.get_alerts()
"""
import logging
from datetime import datetime
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("RiskMonitor")

# ========== 配置 ==========

FLASH_CRASH_WINDOW = 5         # 闪崩检测窗口（分钟）
FLASH_CRASH_THRESHOLD = -0.05  # 闪崩阈值（-5%）
SURGE_THRESHOLD = 0.05         # 急涨阈值（+5%）
AMPLITUDE_THRESHOLD = 0.15     # 异常振幅阈值（15%）
AMPLITUDE_MIN_POINTS = 30      # 振幅检测最小数据点数
VOLUME_DROP_RATIO = 0.3        # 量缩阈值（<30%均量）
LIMIT_UP_RATIO = 0.098         # 涨停比例（9.8%）
LIMIT_DOWN_RATIO = -0.098      # 跌停比例（-9.8%）
POSITION_STOP_LOSS = -0.04     # 持仓止损线
POSITION_TAKE_PROFIT = 0.07    # 持仓止盈线
ALERT_COOLDOWN_SEC = 60        # 同标的同类别告警冷却时间（秒）


@dataclass
class PricePoint:
    price: float
    volume: float
    time: str


@dataclass
class Alert:
    level: str          # critical / warning / info
    category: str       # flash_crash / limit_down / amplitude / stop_loss / take_profit / volume_drop
    symbol: str
    detail: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


class RiskMonitor:
    """实盘风控监控器"""

    def __init__(self):
        self.price_history: dict[str, list[PricePoint]] = defaultdict(list)
        self.daily_avg_vol: dict[str, float] = {}
        self.alerts: list[Alert] = []
        self.positions: dict[str, dict] = {}  # symbol -> {entry_price, stop_loss, take_profit}
        self.prev_close: dict[str, float] = {}
        self._last_alert_time: dict[tuple[str, str], float] = {}  # (symbol, category) -> timestamp

    # ========== 数据输入 ==========

    def set_prev_close(self, symbol: str, price: float):
        if price <= 0:
            logger.warning("[RM] 昨收价无效 %s: %.2f，已忽略", symbol, price)
            return
        self.prev_close[symbol] = price

    def set_daily_avg_vol(self, symbol: str, avg_vol: float):
        if avg_vol <= 0:
            logger.warning("[RM] 均量无效 %s: %.0f，已忽略", symbol, avg_vol)
            return
        self.daily_avg_vol[symbol] = avg_vol

    def open_position(self, symbol: str, entry_price: float,
                      stop_loss_pct: float = POSITION_STOP_LOSS,
                      take_profit_pct: float = POSITION_TAKE_PROFIT):
        if entry_price <= 0:
            logger.warning("[RM] 入场价无效 %s: %.3f", symbol, entry_price)
            return
        if symbol in self.positions:
            logger.warning("[RM] 重复开仓 %s（旧持仓将被覆盖）", symbol)
        # 归一化stop_loss_pct：用户可能传正数-0.04或负数
        sl_pct = stop_loss_pct if stop_loss_pct < 0 else -stop_loss_pct
        tp_pct = take_profit_pct if take_profit_pct > 0 else -take_profit_pct
        self.positions[symbol] = {
            "entry_price": entry_price,
            "stop_loss": round(entry_price * (1 + sl_pct), 3),
            "take_profit": round(entry_price * (1 + tp_pct), 3),
        }
        logger.info("[RM] 开仓 %s @ %.3f SL=%.3f TP=%.3f",
                    symbol, entry_price,
                    self.positions[symbol]["stop_loss"],
                    self.positions[symbol]["take_profit"])

    def close_position(self, symbol: str):
        if symbol in self.positions:
            del self.positions[symbol]
            logger.info("[RM] 平仓 %s", symbol)

    def feed(self, symbol: str, data: dict):
        """喂入一笔实时行情"""
        try:
            price = float(data["price"])
        except (KeyError, ValueError, TypeError) as e:
            logger.warning("[RM] 行情数据无效 %s: %s", symbol, e)
            return
        if price <= 0:
            logger.warning("[RM] 价格无效 %s: %.2f", symbol, price)
            return

        volume = float(data.get("volume", 0))
        tick_time = data.get("time", datetime.now().strftime("%H:%M:%S"))

        self.price_history[symbol].append(PricePoint(price, volume, tick_time))
        if len(self.price_history[symbol]) > 120:
            self.price_history[symbol] = self.price_history[symbol][-120:]

        self._check_flash_crash(symbol)
        self._check_limit(symbol)
        self._check_amplitude(symbol)
        self._check_volume_drop(symbol, volume)
        self._check_position(symbol, price)

    # ========== 告警去重 ==========

    def _should_alert(self, symbol: str, category: str) -> bool:
        """检查是否应发送告警（冷却时间内不重复）"""
        key = (symbol, category)
        now = datetime.now().timestamp()
        last = self._last_alert_time.get(key, 0)
        if now - last < ALERT_COOLDOWN_SEC:
            return False
        self._last_alert_time[key] = now
        return True

    # ========== 检测逻辑 ==========

    def _check_flash_crash(self, symbol: str):
        """闪崩/急涨检测：N分钟内价格变化超过阈值"""
        history = self.price_history[symbol]
        if len(history) < FLASH_CRASH_WINDOW + 1:
            return

        recent = history[-FLASH_CRASH_WINDOW - 1:]
        start_price = recent[0].price
        current = recent[-1].price
        if start_price <= 0:
            return
        change = (current - start_price) / start_price

        if change <= FLASH_CRASH_THRESHOLD and self._should_alert(symbol, "flash_crash"):
            self.alerts.append(Alert(
                level="critical", category="flash_crash", symbol=symbol,
                detail=f"闪崩! {FLASH_CRASH_WINDOW}分钟内 {start_price:.2f}→{current:.2f} ({change*100:.1f}%)"
            ))
            logger.warning("[RM] ⚡闪崩 %s: %.2f→%.2f (%.1f%%) %d分钟",
                         symbol, start_price, current, change * 100, FLASH_CRASH_WINDOW)

        elif change >= SURGE_THRESHOLD and self._should_alert(symbol, "surge"):
            self.alerts.append(Alert(
                level="info", category="surge", symbol=symbol,
                detail=f"急涨 {FLASH_CRASH_WINDOW}分钟内 {start_price:.2f}→{current:.2f} (+{change*100:.1f}%)"
            ))

    def _check_limit(self, symbol: str):
        """涨跌停检测"""
        if symbol not in self.prev_close:
            return
        history = self.price_history[symbol]
        if not history:
            return

        prev = self.prev_close[symbol]
        current = history[-1].price
        if prev <= 0:
            return
        change = (current - prev) / prev

        if change <= LIMIT_DOWN_RATIO and self._should_alert(symbol, "limit_down"):
            self.alerts.append(Alert(
                level="critical", category="limit_down", symbol=symbol,
                detail=f"跌停! 昨收{prev:.2f} → {current:.2f} ({change*100:.1f}%)"
            ))
            logger.warning("[RM] 📉跌停 %s: %.2f (%.1f%%)", symbol, current, change * 100)

        elif change >= LIMIT_UP_RATIO and self._should_alert(symbol, "limit_up"):
            self.alerts.append(Alert(
                level="info", category="limit_up", symbol=symbol,
                detail=f"涨停 {prev:.2f} → {current:.2f} (+{change*100:.1f}%)"
            ))

    def _check_amplitude(self, symbol: str):
        """异常振幅检测（需足够数据点）"""
        history = self.price_history[symbol]
        if len(history) < AMPLITUDE_MIN_POINTS:
            return

        recent = history[-AMPLITUDE_MIN_POINTS:]
        prices = [p.price for p in recent]
        high = max(prices)
        low = min(prices)
        if high <= 0:
            return
        amplitude = (high - low) / high

        if amplitude > AMPLITUDE_THRESHOLD and self._should_alert(symbol, "amplitude"):
            self.alerts.append(Alert(
                level="warning", category="amplitude", symbol=symbol,
                detail=f"异常振幅 {amplitude*100:.1f}% (H={high:.2f} L={low:.2f})"
            ))
            logger.warning("[RM] 📊异常振幅 %s: %.1f%% H=%.2f L=%.2f",
                         symbol, amplitude * 100, high, low)

    def _check_volume_drop(self, symbol: str, volume: float):
        """流动性枯竭检测"""
        if symbol not in self.daily_avg_vol or self.daily_avg_vol[symbol] <= 0:
            return

        ratio = volume / self.daily_avg_vol[symbol]
        if ratio < VOLUME_DROP_RATIO and self._should_alert(symbol, "volume_drop"):
            self.alerts.append(Alert(
                level="warning", category="volume_drop", symbol=symbol,
                detail=f"量缩 {ratio*100:.0f}%均量 (当前{volume:.0f} vs 均量{self.daily_avg_vol[symbol]:.0f})"
            ))

    def _check_position(self, symbol: str, price: float):
        """持仓止损/止盈追踪（触发后自动平仓，防止重复告警）"""
        if symbol not in self.positions:
            return

        pos = self.positions[symbol]
        entry = pos["entry_price"]

        if price <= pos["stop_loss"]:
            pnl = (price - entry) / entry
            if self._should_alert(symbol, "stop_loss"):
                self.alerts.append(Alert(
                    level="critical", category="stop_loss", symbol=symbol,
                    detail=f"止损触发! 入场{entry:.3f} → {price:.3f} ({pnl*100:.1f}%)"
                ))
                logger.warning("[RM] 🔴持仓止损 %s: %.3f→%.3f (%.1f%%)",
                             symbol, entry, price, pnl * 100)
            self.close_position(symbol)

        elif price >= pos["take_profit"]:
            pnl = (price - entry) / entry
            if self._should_alert(symbol, "take_profit"):
                self.alerts.append(Alert(
                    level="info", category="take_profit", symbol=symbol,
                    detail=f"止盈触发! 入场{entry:.3f} → {price:.3f} (+{pnl*100:.1f}%)"
                ))
                logger.info("[RM] 🟢持仓止盈 %s: %.3f→%.3f (+%.1f%%)",
                           symbol, entry, price, pnl * 100)
            self.close_position(symbol)

    # ========== 结果输出 ==========

    def get_alerts(self, clear: bool = False) -> list[dict]:
        """获取告警列表"""
        result = [{"level": a.level, "category": a.category,
                   "symbol": a.symbol, "detail": a.detail,
                   "timestamp": a.timestamp} for a in self.alerts]
        if clear:
            self.alerts.clear()
        return result

    def get_position_risk(self) -> list[dict]:
        """获取持仓风险状态"""
        result = []
        for symbol, pos in self.positions.items():
            history = self.price_history.get(symbol, [])
            if not history:
                continue
            current = history[-1].price
            entry = pos["entry_price"]
            pnl = (current - entry) / entry
            distance_to_sl = (current - pos["stop_loss"]) / current
            result.append({
                "symbol": symbol, "entry_price": entry,
                "current_price": current, "pnl_pct": round(pnl * 100, 2),
                "stop_loss": pos["stop_loss"],
                "take_profit": pos["take_profit"],
                "distance_to_sl_pct": round(distance_to_sl * 100, 2),
                "risk_level": "critical" if pnl <= -0.03 else
                              "warning" if pnl <= -0.02 else "normal",
            })
        return result

    def get_summary(self) -> dict:
        """获取监控摘要"""
        alerts = self.get_alerts()
        critical = [a for a in alerts if a["level"] == "critical"]
        warnings = [a for a in alerts if a["level"] == "warning"]
        return {
            "monitored_symbols": len(self.price_history),
            "active_positions": len(self.positions),
            "total_alerts": len(alerts),
            "critical": len(critical),
            "warnings": len(warnings),
            "position_risk": self.get_position_risk(),
            "latest_alerts": alerts[-5:] if alerts else [],
        }


# ========== 自测 ==========

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s - %(message)s")

    monitor = RiskMonitor()
    monitor.set_prev_close("000001", 10.00)
    monitor.set_daily_avg_vol("000001", 5_000_000)

    # 场景1: 正常波动
    for i, p in enumerate([10.02, 10.05, 10.03, 10.08, 10.06]):
        monitor.feed("000001", {"price": p, "volume": 200000, "time": f"09:3{i}"})

    # 场景2: 闪崩
    monitor.feed("000001", {"price": 10.10, "volume": 500000, "time": "09:35"})
    monitor.feed("000001", {"price": 9.50, "volume": 3000000, "time": "09:40"})

    # 场景3: 持仓止损
    monitor.open_position("000001", 10.10)
    monitor.feed("000001", {"price": 9.65, "volume": 2000000, "time": "09:45"})

    # 场景4: 跌停
    monitor.set_prev_close("000002", 10.00)
    monitor.feed("000002", {"price": 9.01, "volume": 1000000, "time": "09:35"})

    print("\n=== 监控摘要 ===")
    import json
    print(json.dumps(monitor.get_summary(), ensure_ascii=False, indent=2))

    print("\n=== 完整告警 ===")
    for a in monitor.get_alerts():
        print(f"  [{a['level']:8s}] {a['category']:15s} {a['symbol']}: {a['detail']}")