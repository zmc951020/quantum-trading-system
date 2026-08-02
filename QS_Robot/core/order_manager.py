#!/usr/bin/env python3
"""
订单管理器 — 订单状态机与生命周期管理
========================================
管理订单从创建到终态的完整生命周期：
  PENDING → SUBMITTED → PARTIAL_FILLED → FILLED
                     ↘ REJECTED
                     ↘ CANCELLED

支持：
- 订单创建/查询/撤销
- 批量订单处理
- 订单持久化（SQLite）
- 订单事件回调
"""
import logging
import sqlite3
import threading
import time
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class OrderStatus(Enum):
    PENDING = "pending"            # 待提交
    SUBMITTED = "submitted"        # 已提交
    PARTIAL_FILLED = "partial"     # 部分成交
    FILLED = "filled"              # 全部成交
    REJECTED = "rejected"          # 被拒绝
    CANCELLED = "cancelled"        # 已撤销
    EXPIRED = "expired"            # 已过期


class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(Enum):
    LIMIT = "limit"      # 限价单
    MARKET = "market"    # 市价单
    STOP = "stop"        # 止损单
    STOP_LIMIT = "stop_limit"  # 止损限价单


@dataclass
class Order:
    """订单数据结构"""
    order_id: str = field(default_factory=lambda: f"ORD-{uuid.uuid4().hex[:8].upper()}")
    symbol: str = ""
    side: OrderSide = OrderSide.BUY
    order_type: OrderType = OrderType.LIMIT
    price: float = 0.0
    volume: int = 0
    strategy_name: str = ""
    status: OrderStatus = OrderStatus.PENDING

    # 成交信息
    filled_price: Optional[float] = None
    filled_volume: int = 0
    filled_amount: float = 0.0
    avg_fill_price: float = 0.0

    # 时间戳
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    submitted_at: Optional[str] = None
    filled_at: Optional[str] = None
    cancelled_at: Optional[str] = None
    expired_at: Optional[str] = None

    # 元数据
    error_msg: Optional[str] = None
    broker_order_id: Optional[str] = None
    tags: Dict[str, str] = field(default_factory=dict)
    version: int = 1

    # 不可逆状态
    _TERMINAL_STATUSES = {OrderStatus.FILLED, OrderStatus.REJECTED, OrderStatus.CANCELLED, OrderStatus.EXPIRED}

    def is_terminal(self) -> bool:
        return self.status in self._TERMINAL_STATUSES

    def is_active(self) -> bool:
        return self.status in {OrderStatus.PENDING, OrderStatus.SUBMITTED, OrderStatus.PARTIAL_FILLED}

    def to_dict(self) -> Dict:
        return {
            "order_id": self.order_id,
            "symbol": self.symbol,
            "side": self.side.value,
            "order_type": self.order_type.value,
            "price": self.price,
            "volume": self.volume,
            "strategy_name": self.strategy_name,
            "status": self.status.value,
            "filled_price": self.filled_price,
            "filled_volume": self.filled_volume,
            "filled_amount": round(self.filled_amount, 2),
            "avg_fill_price": round(self.avg_fill_price, 4),
            "created_at": self.created_at,
            "submitted_at": self.submitted_at,
            "filled_at": self.filled_at,
            "cancelled_at": self.cancelled_at,
            "error_msg": self.error_msg,
            "broker_order_id": self.broker_order_id,
        }


class OrderManager:
    """订单管理器 — 订单生命周期管理 + 持久化"""

    DB_PATH = "data/orders.db"

    def __init__(self):
        self._orders: Dict[str, Order] = {}
        self._lock = threading.RLock()
        self._callbacks: List[Callable] = []

        # 初始化数据库
        self._init_db()
        self._load_orders()

        logger.info("[OrderManager] 初始化完成")

    def _init_db(self):
        """初始化SQLite数据库"""
        try:
            import os
            os.makedirs("data", exist_ok=True)
            conn = sqlite3.connect(self.DB_PATH)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    order_id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    order_type TEXT DEFAULT 'limit',
                    price REAL NOT NULL,
                    volume INTEGER NOT NULL,
                    strategy_name TEXT DEFAULT '',
                    status TEXT DEFAULT 'pending',
                    filled_price REAL,
                    filled_volume INTEGER DEFAULT 0,
                    filled_amount REAL DEFAULT 0,
                    avg_fill_price REAL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    submitted_at TEXT,
                    filled_at TEXT,
                    cancelled_at TEXT,
                    error_msg TEXT,
                    broker_order_id TEXT,
                    version INTEGER DEFAULT 1
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_orders_symbol ON orders(symbol)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_orders_created ON orders(created_at)
            """)
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"[OrderManager] 数据库初始化失败: {e}")

    def _load_orders(self):
        """从数据库加载活跃订单"""
        try:
            conn = sqlite3.connect(self.DB_PATH)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM orders WHERE status NOT IN ('filled', 'rejected', 'cancelled', 'expired')"
            ).fetchall()
            conn.close()

            for row in rows:
                order = Order(
                    order_id=row["order_id"],
                    symbol=row["symbol"],
                    side=OrderSide(row["side"]),
                    order_type=OrderType(row.get("order_type", "limit")),
                    price=row["price"],
                    volume=row["volume"],
                    strategy_name=row["strategy_name"] or "",
                    status=OrderStatus(row["status"]),
                    filled_price=row["filled_price"],
                    filled_volume=row["filled_volume"] or 0,
                    filled_amount=row["filled_amount"] or 0,
                    avg_fill_price=row["avg_fill_price"] or 0,
                    created_at=row["created_at"],
                    submitted_at=row["submitted_at"],
                    filled_at=row["filled_at"],
                    cancelled_at=row["cancelled_at"],
                    error_msg=row["error_msg"],
                    broker_order_id=row["broker_order_id"],
                )
                self._orders[order.order_id] = order

            logger.info(f"[OrderManager] 从数据库恢复 {len(self._orders)} 个活跃订单")
        except Exception as e:
            logger.warning(f"[OrderManager] 订单加载失败: {e}")

    def _save_order(self, order: Order):
        """持久化订单到数据库"""
        try:
            conn = sqlite3.connect(self.DB_PATH)
            conn.execute("""
                INSERT OR REPLACE INTO orders
                (order_id, symbol, side, order_type, price, volume, strategy_name,
                 status, filled_price, filled_volume, filled_amount, avg_fill_price,
                 created_at, submitted_at, filled_at, cancelled_at, error_msg,
                 broker_order_id, version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                order.order_id, order.symbol, order.side.value, order.order_type.value,
                order.price, order.volume, order.strategy_name,
                order.status.value, order.filled_price, order.filled_volume,
                order.filled_amount, order.avg_fill_price,
                order.created_at, order.submitted_at, order.filled_at,
                order.cancelled_at, order.error_msg, order.broker_order_id,
                order.version,
            ))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"[OrderManager] 订单保存失败: {e}")

    # ========== 订单操作 ==========

    def create_order(self, symbol: str, side: OrderSide, price: float,
                     volume: int, strategy_name: str = "",
                     order_type: OrderType = OrderType.LIMIT) -> Order:
        """创建新订单"""
        with self._lock:
            order = Order(
                symbol=symbol,
                side=side,
                order_type=order_type,
                price=price,
                volume=volume,
                strategy_name=strategy_name,
            )
            self._orders[order.order_id] = order
            self._save_order(order)
            logger.info(f"[OrderManager] 订单创建: {order.order_id} {symbol} {side.value} {volume}@{price}")
            self._notify(order)
            return order

    def update_status(self, order_id: str, status: OrderStatus,
                      filled_price: float = None, filled_volume: int = None,
                      error_msg: str = None, broker_order_id: str = None):
        """更新订单状态"""
        with self._lock:
            order = self._orders.get(order_id)
            if not order:
                logger.warning(f"[OrderManager] 订单不存在: {order_id}")
                return

            if order.is_terminal():
                logger.warning(f"[OrderManager] 订单已是终态: {order_id} {order.status.value}")
                return

            order.status = status
            order.version += 1

            if filled_price is not None:
                order.filled_price = filled_price
            if filled_volume is not None:
                order.filled_volume = filled_volume
                order.filled_amount = filled_price * filled_volume if filled_price else 0
            if error_msg is not None:
                order.error_msg = error_msg
            if broker_order_id is not None:
                order.broker_order_id = broker_order_id

            now = datetime.now().isoformat()
            if status == OrderStatus.SUBMITTED:
                order.submitted_at = now
            elif status == OrderStatus.FILLED:
                order.filled_at = now
                if order.filled_volume > 0:
                    order.avg_fill_price = order.filled_amount / order.filled_volume
            elif status == OrderStatus.CANCELLED:
                order.cancelled_at = now

            self._save_order(order)
            logger.info(f"[OrderManager] 订单状态更新: {order_id} -> {status.value}")
            self._notify(order)

    def get_order(self, order_id: str) -> Optional[Order]:
        with self._lock:
            return self._orders.get(order_id)

    def get_orders(self, status: Optional[OrderStatus] = None,
                   symbol: Optional[str] = None,
                   strategy_name: Optional[str] = None) -> List[Order]:
        """查询订单"""
        with self._lock:
            orders = list(self._orders.values())
            if status:
                orders = [o for o in orders if o.status == status]
            if symbol:
                orders = [o for o in orders if o.symbol == symbol]
            if strategy_name:
                orders = [o for o in orders if o.strategy_name == strategy_name]
            return sorted(orders, key=lambda o: o.created_at, reverse=True)

    def get_all_orders(self) -> List[Order]:
        with self._lock:
            return list(self._orders.values())

    def cancel_order(self, order_id: str) -> bool:
        """撤销订单"""
        with self._lock:
            order = self._orders.get(order_id)
            if not order:
                return False
            if not order.is_active():
                return False
            self.update_status(order_id, OrderStatus.CANCELLED)
            return True

    def cancel_all_active(self, strategy_name: str = None) -> int:
        """撤销所有活跃订单"""
        count = 0
        with self._lock:
            for order in list(self._orders.values()):
                if order.is_active():
                    if strategy_name and order.strategy_name != strategy_name:
                        continue
                    self.update_status(order.order_id, OrderStatus.CANCELLED)
                    count += 1
        return count

    # ========== 统计 ==========

    def get_stats(self, symbol: str = None, days: int = 1) -> Dict:
        """获取订单统计"""
        with self._lock:
            orders = self.get_orders(symbol=symbol)

            total = len(orders)
            filled = sum(1 for o in orders if o.status == OrderStatus.FILLED)
            rejected = sum(1 for o in orders if o.status == OrderStatus.REJECTED)
            cancelled = sum(1 for o in orders if o.status == OrderStatus.CANCELLED)
            pending = sum(1 for o in orders if o.is_active())

            buy_volume = sum(o.filled_volume for o in orders if o.side == OrderSide.BUY and o.status == OrderStatus.FILLED)
            sell_volume = sum(o.filled_volume for o in orders if o.side == OrderSide.SELL and o.status == OrderStatus.FILLED)
            buy_amount = sum(o.filled_amount for o in orders if o.side == OrderSide.BUY and o.status == OrderStatus.FILLED)
            sell_amount = sum(o.filled_amount for o in orders if o.side == OrderSide.SELL and o.status == OrderStatus.FILLED)

            return {
                "total": total,
                "filled": filled,
                "rejected": rejected,
                "cancelled": cancelled,
                "pending": pending,
                "buy_volume": buy_volume,
                "sell_volume": sell_volume,
                "buy_amount": round(buy_amount, 2),
                "sell_amount": round(sell_amount, 2),
                "fill_rate": round(filled / total, 4) if total > 0 else 0,
            }

    # ========== 回调 ==========

    def on_update(self, callback: Callable):
        """注册订单更新回调"""
        self._callbacks.append(callback)

    def _notify(self, order: Order):
        for cb in self._callbacks:
            try:
                cb(order)
            except Exception as e:
                logger.error(f"[OrderManager] 回调异常: {e}")


# 全局单例
_order_mgr_instance: Optional[OrderManager] = None
_order_mgr_lock = threading.Lock()


def get_order_manager() -> OrderManager:
    global _order_mgr_instance
    with _order_mgr_lock:
        if _order_mgr_instance is None:
            _order_mgr_instance = OrderManager()
        return _order_mgr_instance