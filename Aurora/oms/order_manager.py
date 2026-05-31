# coding: utf-8
"""
订单管理增益模块 — 幂等下单 + 状态机 + 废单处置
==================================================
增益性补充，插入现有 TradeExecutionEngine 与券商接口之间，
不修改原有 trade_security.py 代码。

功能：
  - 幂等键机制（防止网络超时重复下单）
  - 订单状态机（PENDING→SUBMITTED→FILLED/CANCELLED/REJECTED）
  - 废单检测与告警（不自动重发）
  - 部分成交感知

使用方式：
  from oms.order_manager import OrderManager
  oms = OrderManager()
  result = oms.place_order(order_dict, idempotency_key)
"""

import hashlib
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class OrderStatus(str, Enum):
    """A股订单状态机"""
    PENDING         = "pending"          # 待发送
    SUBMITTED       = "submitted"        # 已提交券商
    PARTIAL_FILLED  = "partial_filled"   # 部分成交
    FILLED          = "filled"           # 全部成交
    CANCELLED       = "cancelled"        # 已撤单
    REJECTED        = "rejected"         # 券商拒绝（废单）
    EXPIRED         = "expired"          # 过期未成交


# ── 终态集合 ──
_TERMINAL_STATES = {OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED, OrderStatus.EXPIRED}


@dataclass
class Order:
    """订单数据对象"""
    order_id: str
    idempotency_key: str
    symbol: str
    side: str                 # buy / sell
    quantity: int
    price: Optional[float] = None
    order_type: str = "limit" # limit / market

    status: OrderStatus = OrderStatus.PENDING
    filled_qty: int = 0
    avg_fill_price: float = 0.0
    reject_reason: str = ""

    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    submitted_at: Optional[float] = None

    # 审计用
    strategy_id: str = ""
    signal_source: str = ""

    def is_terminal(self) -> bool:
        return self.status in _TERMINAL_STATES


class OrderManager:
    """
    订单管理器 — 增益层
    ====================
    插入 TradeExecutionEngine._perform_exchange_trade() 之前。
    不修改原有 trade_security.py 任何代码。
    """

    _MAX_IDEMPOTENT_CACHE = 10000     # 幂等键最大缓存数量
    _MAX_HISTORY = 5000               # 订单历史最大保留

    def __init__(self):
        self._lock = threading.Lock()
        self._orders: Dict[str, Order] = {}                            # order_id → Order
        self._idempotency_map: Dict[str, str] = {}                     # idempotency_key → order_id
        self._rejected_count: int = 0
        self._daily_rejections: Dict[str, int] = {}                    # "YYYY-MM-DD" → count

    def place_order(
        self,
        order_req: Dict[str, Any],
        idempotency_key: str,
        *,
        strategy_id: str = "",
        signal_source: str = ""
    ) -> Dict[str, Any]:
        """
        下单 — 含幂等检查

        Args:
            order_req:  {'symbol', 'side', 'quantity', 'price'(可选), 'order_type'(可选)}
            idempotency_key: 幂等键（建议格式：STRATEGY_SYMBOL_TIMESTAMP）
            strategy_id: 策略标识
            signal_source: 信号来源

        Returns:
            {'status': 'ok'|'duplicate', 'order_id': str}
        """
        with self._lock:
            # ── 幂等检查 ──
            if idempotency_key in self._idempotency_map:
                existing_id = self._idempotency_map[idempotency_key]
                existing = self._orders.get(existing_id)
                if existing and not existing.is_terminal():
                    logger.warning(
                        "幂等拦截: 重复订单 idempotency_key=%s, 已有订单=%s, 状态=%s",
                        idempotency_key[:32], existing_id, existing.status.value
                    )
                    return {"status": "duplicate", "order_id": existing_id, "existing_status": existing.status.value}
                # 如果终态，允许重新下单
                logger.info("幂等键 %s 对应订单 %s 已终态，允许新单", idempotency_key[:32], existing_id)

            # ── 生成订单 ──
            order_id = f"ORD_{uuid.uuid4().hex[:16]}"
            order = Order(
                order_id=order_id,
                idempotency_key=idempotency_key,
                symbol=order_req.get("symbol", ""),
                side=order_req.get("side", "buy"),
                quantity=order_req.get("quantity", 0),
                price=order_req.get("price"),
                order_type=order_req.get("order_type", "limit"),
                strategy_id=strategy_id,
                signal_source=signal_source,
            )

            self._orders[order_id] = order
            self._idempotency_map[idempotency_key] = order_id

            # ── 缓存清理 ──
            if len(self._idempotency_map) > self._MAX_IDEMPOTENT_CACHE:
                # 按时间保留最近 5000 个
                sorted_keys = sorted(
                    self._idempotency_map.keys(),
                    key=lambda k: self._orders[self._idempotency_map[k]].created_at,
                    reverse=True
                )
                for old_key in sorted_keys[self._MAX_IDEMPOTENT_CACHE:]:
                    self._idempotency_map.pop(old_key, None)

            if len(self._orders) > self._MAX_HISTORY:
                sorted_orders = sorted(
                    self._orders.values(),
                    key=lambda o: o.created_at,
                    reverse=True
                )
                for old_order in sorted_orders[self._MAX_HISTORY:]:
                    self._orders.pop(old_order.order_id, None)

            logger.info(
                "订单已创建: order_id=%s, symbol=%s, side=%s, qty=%d, idempotency=%s...",
                order_id, order.symbol, order.side, order.quantity, idempotency_key[:32]
            )
            return {"status": "ok", "order_id": order_id, "order": order}

    def mark_submitted(self, order_id: str):
        """标记订单已提交到券商"""
        with self._lock:
            order = self._orders.get(order_id)
            if order:
                order.status = OrderStatus.SUBMITTED
                order.submitted_at = time.time()
                order.updated_at = time.time()

    def on_execution_report(self, report: Dict[str, Any]):
        """
        接收成交回报 / 废单回报

        report 格式:
          {
            'order_id': str,
            'status': 'filled'|'partial_filled'|'rejected'|'cancelled',
            'filled_qty': int,
            'avg_price': float,
            'reject_reason': str (可选),
            'trade_time': str (可选),
          }
        """
        order_id = report.get("order_id", "")
        with self._lock:
            order = self._orders.get(order_id)
            if not order:
                logger.warning("收到未知订单回报: %s", order_id)
                return

            new_status = OrderStatus(report.get("status", order.status.value))
            order.status = new_status
            order.filled_qty = report.get("filled_qty", order.filled_qty)
            order.avg_fill_price = report.get("avg_price", order.avg_fill_price)
            order.updated_at = time.time()

            # ── 废单处置 ──
            if new_status == OrderStatus.REJECTED:
                order.reject_reason = report.get("reject_reason", "券商拒绝")
                self._rejected_count += 1
                today = datetime.now().strftime("%Y-%m-%d")
                self._daily_rejections[today] = self._daily_rejections.get(today, 0) + 1
                logger.error(
                    "废单告警: order_id=%s, symbol=%s, side=%s, reason=%s",
                    order_id, order.symbol, order.side, order.reject_reason
                )
                # 不自动重发 — 由上层策略决定

            elif new_status in (OrderStatus.FILLED, OrderStatus.PARTIAL_FILLED):
                logger.info(
                    "成交回报: order_id=%s, filled=%d/%d, avg_price=%.2f",
                    order_id, order.filled_qty, order.quantity, order.avg_fill_price
                )

    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """撤单"""
        with self._lock:
            order = self._orders.get(order_id)
            if not order:
                return {"status": "error", "msg": "订单不存在"}
            if order.is_terminal():
                return {"status": "error", "msg": f"订单已处于终态 {order.status.value}，无法撤单"}
            order.status = OrderStatus.CANCELLED
            order.updated_at = time.time()
            logger.info("订单已撤单: order_id=%s", order_id)
            return {"status": "ok", "order_id": order_id}

    def get_order(self, order_id: str) -> Optional[Order]:
        """查询订单"""
        return self._orders.get(order_id)

    def get_active_orders(self) -> list:
        """获取所有活跃（非终态）订单"""
        with self._lock:
            return [o for o in self._orders.values() if not o.is_terminal()]

    def get_daily_rejection_count(self) -> int:
        """今日废单数量"""
        today = datetime.now().strftime("%Y-%m-%d")
        return self._daily_rejections.get(today, 0)

    def get_stats(self) -> Dict[str, Any]:
        """订单管理统计"""
        with self._lock:
            total = len(self._orders)
            active = len([o for o in self._orders.values() if not o.is_terminal()])
            terminal = total - active
            return {
                "total_orders": total,
                "active_orders": active,
                "terminal_orders": terminal,
                "total_rejected": self._rejected_count,
                "daily_rejections": self.get_daily_rejection_count(),
            }