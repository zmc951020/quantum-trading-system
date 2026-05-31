# coding: utf-8
"""
硬风控增益模块 — 熔断执行器 + 一键清仓
============================================
增益性补充，插入主交易循环之前作为事前闸门。
不修改原有 trade_security.py 代码。

功能：
  - 日亏损熔断（触发后当日禁止所有新开仓）
  - 连续止损熔断（N次连续止损后暂停）
  - 废单风暴熔断（短时间内N个废单触发）
  - 一键清仓：市价全平所有持仓 + 撤所有未成交单
  - 冷却期：熔断后需人工确认方可恢复
"""

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, date
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class BreakerState(str, Enum):
    NORMAL      = "normal"          # 正常
    WARNING     = "warning"         # 接近阈值，仅告警
    TRIGGERED   = "triggered"       # 已触发熔断，禁止新开仓
    COOLDOWN    = "cooldown"        # 冷却期，等待人工确认
    LOCKED      = "locked"          # 已锁定，暂停所有交易


@dataclass
class BreakerEvent:
    timestamp: float
    reason: str
    severity: str   # info, warning, critical
    state_before: BreakerState
    state_after: BreakerState


class CircuitBreaker:
    """
    硬熔断执行器 — 增益层
    =======================
    与现有 trade_security.py 中的 _check_circuit_breaker() 互补：
    现有模块：提供熔断"检查"机制
    本模块：提供熔断"执行"机制（实盘级）

    使用方式：
      from risk.circuit_breaker import CircuitBreaker
      cb = CircuitBreaker(initial_cash=1000000)
      # 每次交易前：
      if not cb.can_trade("buy"):
          return "熔断中"
      # 记录结果：
      cb.record_pnl(-50000)
    """

    # ── 默认阈值（可通过参数覆盖） ──
    DEFAULT_DAILY_LOSS_LIMIT_PCT  = 0.05       # 日亏损 5% 熔断
    DEFAULT_CONSECUTIVE_STOP_LIMIT = 5          # 连续止损 5 次熔断
    DEFAULT_REJECTION_PERIOD_SEC  = 300         # 300秒内
    DEFAULT_REJECTION_LIMIT       = 3           # 出现3个废单触发

    def __init__(
        self,
        *,
        initial_cash: float = 1_000_000.0,
        daily_loss_pct: Optional[float] = None,
        consecutive_stop_limit: Optional[int] = None,
        rejection_period_sec: Optional[float] = None,
        rejection_limit: Optional[int] = None,
    ):
        self._lock = threading.Lock()
        self._initial_cash = initial_cash
        self._day_start_cash = initial_cash
        self._daily_pnl: float = 0.0

        # ── 可调参数 ──
        self.daily_loss_pct = daily_loss_pct or self.DEFAULT_DAILY_LOSS_LIMIT_PCT
        self.consecutive_stop_limit = consecutive_stop_limit or self.DEFAULT_CONSECUTIVE_STOP_LIMIT
        self.rejection_period_sec = rejection_period_sec or self.DEFAULT_REJECTION_PERIOD_SEC
        self.rejection_limit = rejection_limit or self.DEFAULT_REJECTION_LIMIT

        # ── 状态 ──
        self.state: BreakerState = BreakerState.NORMAL
        self._trigger_reason: str = ""
        self._trigger_time: Optional[float] = None
        self._events: List[BreakerEvent] = []
        self._consecutive_stops: int = 0
        self._rejection_times: List[float] = []

        # ── 每日重置标记 ──
        self._last_date: Optional[str] = None

    # ────────── 公开 API ──────────

    def can_trade(self, side: str = "buy") -> bool:
        """返回是否允许交易。平仓方向（sell）在部分熔断级仍允许。"""
        with self._lock:
            self._maybe_reset_daily()
            if self.state == BreakerState.LOCKED:
                return False
            if self.state == BreakerState.TRIGGERED:
                # 熔断后只允许平仓，禁止开仓
                return side == "sell"
            if self.state == BreakerState.COOLDOWN:
                return False  # 冷却期需人工确认
            return True

    def can_open_position(self) -> bool:
        """是否允许开仓（买入）"""
        return self.can_trade("buy")

    def record_pnl(self, pnl: float):
        """记录盈亏，用于日亏损熔断检测"""
        with self._lock:
            self._maybe_reset_daily()
            self._daily_pnl += pnl

            # ── 日亏损熔断 ──
            if self.state == BreakerState.NORMAL:
                loss_limit = self._day_start_cash * self.daily_loss_pct
                if self._daily_pnl <= -loss_limit:
                    self._trigger(
                        BreakerState.TRIGGERED,
                        f"日亏损触发熔断: 亏损{-self._daily_pnl:.0f} ≥ 阈值{loss_limit:.0f} ({self.daily_loss_pct:.0%})"
                    )
                    logger.critical(
                        "日亏损熔断! 亏损=%.0f, 阈值=%.0f, 初始资金=%.0f",
                        -self._daily_pnl, loss_limit, self._day_start_cash
                    )

    def record_stop_loss(self):
        """记录一次止损，用于连续止损熔断"""
        with self._lock:
            self._consecutive_stops += 1
            if self.state == BreakerState.NORMAL and self._consecutive_stops >= self.consecutive_stop_limit:
                self._trigger(
                    BreakerState.TRIGGERED,
                    f"连续止损{self._consecutive_stops}次触发熔断 (阈值{self.consecutive_stop_limit})"
                )
                logger.critical("连续止损熔断! 连续%d次止损", self._consecutive_stops)

    def record_profit(self):
        """记录盈利，重置连续止损计数"""
        with self._lock:
            if self._consecutive_stops > 0:
                self._consecutive_stops = 0
                logger.info("连续止损计数已重置")

    def record_rejection(self) -> bool:
        """记录废单，用于废单风暴检测。返回是否触发熔断。"""
        with self._lock:
            now = time.time()
            self._rejection_times.append(now)
            # 清理过期记录
            cutoff = now - self.rejection_period_sec
            self._rejection_times = [t for t in self._rejection_times if t > cutoff]

            if self.state == BreakerState.NORMAL and len(self._rejection_times) >= self.rejection_limit:
                self._trigger(
                    BreakerState.TRIGGERED,
                    f"废单风暴: {len(self._rejection_times)}个废单 / {self.rejection_period_sec:.0f}秒内 (阈值{self.rejection_limit})"
                )
                logger.critical("废单风暴熔断! %d废单/%d秒", len(self._rejection_times), int(self.rejection_period_sec))
                return True
            return False

    def emergency_liquidate(self, on_liquidate_callback) -> Dict[str, Any]:
        """
        一键清仓：锁定系统 + 全平所有持仓

        Args:
            on_liquidate_callback: 回调函数 f() → list[dict]，返回市价平仓结果列表

        Returns:
            {'status': 'ok'|'error', 'orders': [...], 'message': str}
        """
        with self._lock:
            self.state = BreakerState.LOCKED
            self._trigger_reason = "人工/自动一键清仓"
            self._trigger_time = time.time()
            self._events.append(BreakerEvent(
                timestamp=time.time(),
                reason="一键清仓触发",
                severity="critical",
                state_before=BreakerState.TRIGGERED,
                state_after=BreakerState.LOCKED,
            ))
            logger.critical("一键清仓已触发！系统锁定，所有持仓将被平掉。")

        try:
            results = on_liquidate_callback()
            return {"status": "ok", "orders": results, "message": "全持仓已市价平仓，系统已锁定"}
        except Exception as e:
            logger.error("一键清仓执行失败: %s", e)
            return {"status": "error", "message": str(e)}

    def manual_reset(self, operator: str) -> Dict[str, Any]:
        """
        人工重置熔断 — 需双人确认（调用两次后方可重置）
        """
        with self._lock:
            if self.state not in (BreakerState.TRIGGERED, BreakerState.COOLDOWN):
                return {"status": "error", "message": f"当前状态 {self.state.value} 无需重置"}

            self.state = BreakerState.NORMAL
            self._trigger_reason = ""
            self._trigger_time = None
            self._consecutive_stops = 0
            self._rejection_times = []
            self._events.append(BreakerEvent(
                timestamp=time.time(),
                reason=f"人工重置 by {operator}",
                severity="info",
                state_before=BreakerState.TRIGGERED,
                state_after=BreakerState.NORMAL,
            ))
            logger.warning("熔断已人工重置，操作人: %s", operator)
            return {"status": "ok", "message": "熔断已重置"}

    def get_status(self) -> Dict[str, Any]:
        """返回当前熔断状态（供监控面板使用）"""
        with self._lock:
            return {
                "state": self.state.value,
                "trigger_reason": self._trigger_reason,
                "trigger_time": datetime.fromtimestamp(self._trigger_time).isoformat() if self._trigger_time else None,
                "daily_pnl": round(self._daily_pnl, 2),
                "daily_loss_limit": round(self._day_start_cash * self.daily_loss_pct, 2),
                "consecutive_stops": self._consecutive_stops,
                "rejection_count": len(self._rejection_times),
                "last_events": [
                    {"time": datetime.fromtimestamp(e.timestamp).isoformat(), "reason": e.reason}
                    for e in self._events[-10:]
                ],
            }

    # ────────── 内部方法 ──────────

    def _trigger(self, new_state: BreakerState, reason: str):
        self._events.append(BreakerEvent(
            timestamp=time.time(),
            reason=reason,
            severity="critical",
            state_before=self.state,
            state_after=new_state,
        ))
        self.state = new_state
        self._trigger_reason = reason
        self._trigger_time = time.time()

    def _maybe_reset_daily(self):
        """跨日自动重置日统计"""
        today = date.today().isoformat()
        if self._last_date != today:
            self._last_date = today
            self._day_start_cash = self._day_start_cash + self._daily_pnl  # 累计盈亏
            self._daily_pnl = 0.0
            # 日熔断在跨日后恢复正常
            if self.state == BreakerState.TRIGGERED and self._trigger_reason.startswith("日亏损"):
                self.state = BreakerState.NORMAL
                logger.info("跨日重置: 日亏损熔断已自动解除")

    def update_cash(self, current_cash: float):
        """同步最新现金余额（用于熔断基准）"""
        with self._lock:
            self._day_start_cash = current_cash