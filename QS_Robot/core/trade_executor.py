#!/usr/bin/env python3
"""
交易执行器 — 信号→风控→下单→成交回报→持仓更新
==================================================
实盘交易链路的编排层，负责：
1. 接收策略信号，调用事前风控
2. 通过BrokerConnector下发订单
3. 处理成交回报，更新持仓
4. 事中风险监控
5. 事后对账

券商密钥未就绪时，自动降级为模拟执行。
"""
import logging
import threading
import time
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum

from .order_manager import OrderManager, Order, OrderStatus, OrderSide
from .broker_connector import SimulatedBroker
from .risk_control import RiskControlEngine

logger = logging.getLogger(__name__)


class ExecutorMode(Enum):
    LIVE = "live"          # 真实券商
    PAPER = "paper"        # 模拟盘
    SIMULATED = "simulated"  # 纯模拟（无券商）


@dataclass
class TradeSignal:
    """交易信号"""
    symbol: str
    strategy_name: str
    side: OrderSide
    price: float
    volume: int
    signal_confidence: float = 1.0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict = field(default_factory=dict)


@dataclass
class ExecutionResult:
    """执行结果"""
    success: bool
    order_id: Optional[str] = None
    filled_price: Optional[float] = None
    filled_volume: int = 0
    reject_reason: Optional[str] = None
    elapsed_ms: float = 0.0
    risk_score: float = 100.0


class TradeExecutor:
    """交易执行器 — 编排信号→风控→下单→成交→持仓的完整链路"""

    def __init__(self, mode: ExecutorMode = ExecutorMode.SIMULATED):
        self.mode = mode
        self.order_mgr = OrderManager()
        self.risk_engine = RiskControlEngine()
        self._lock = threading.RLock()

        # 券商连接
        self._broker: Optional[Any] = None
        self._broker_ready = False
        self._init_broker()

        # 持仓
        self._positions: Dict[str, Dict] = {}  # symbol -> position info
        self._cash: float = 100000.0
        self._total_invested: float = 0.0

        # 交易统计
        self._stats = {
            "total_signals": 0,
            "total_orders": 0,
            "total_filled": 0,
            "total_rejected": 0,
            "total_cancelled": 0,
            "daily_pnl": 0.0,
            "cumulative_pnl": 0.0,
            "started_at": datetime.now().isoformat(),
        }

        # 回调
        self._on_order_update: Optional[Callable] = None
        self._on_trade: Optional[Callable] = None
        self._on_error: Optional[Callable] = None

        # 禁用的熔断信号
        self._circuit_breaker = False
        self._breaker_reason = ""

        logger.info(f"[TradeExecutor] 初始化完成，模式={mode.value}")

    def _init_broker(self):
        """初始化券商连接"""
        try:
            self._broker = SimulatedBroker()
            self._broker_ready = True
            logger.info("[TradeExecutor] 券商连接就绪（模拟模式）")
        except Exception as e:
            logger.warning(f"[TradeExecutor] 券商初始化失败: {e}")
            self._broker_ready = False

    # ========== 信号处理 ==========

    def execute_signal(self, signal: TradeSignal) -> ExecutionResult:
        """执行交易信号 — 完整链路

        1. 事前风控检查
        2. 创建订单
        3. 提交订单
        4. 等待成交回报
        5. 更新持仓
        """
        t0 = time.time()

        with self._lock:
            self._stats["total_signals"] += 1

            # 熔断检查
            if self._circuit_breaker:
                return ExecutionResult(
                    success=False,
                    reject_reason=f"熔断中: {self._breaker_reason}",
                    elapsed_ms=(time.time() - t0) * 1000,
                )

            # 1. 事前风控
            risk_result = self.risk_engine.pre_trade_check({
                "symbol": signal.symbol,
                "strategy_name": signal.strategy_name,
                "price": signal.price,
                "volume": signal.volume,
                "side": signal.side.value,
                "max_order_amount": self._cash * 0.1,
                "max_volume": int(self._cash * 0.1 / max(signal.price, 0.01)),
            })

            if not risk_result["passed"]:
                self._stats["total_rejected"] += 1
                logger.warning(f"[TradeExecutor] 事前风控拒绝: {risk_result['reason']}")
                return ExecutionResult(
                    success=False,
                    reject_reason=risk_result["reason"],
                    risk_score=risk_result["risk_score"],
                    elapsed_ms=(time.time() - t0) * 1000,
                )

            # 2. 创建订单
            order = self.order_mgr.create_order(
                symbol=signal.symbol,
                side=signal.side,
                price=signal.price,
                volume=signal.volume,
                strategy_name=signal.strategy_name,
            )
            self._stats["total_orders"] += 1

            # 3. 提交订单
            if self._broker and self._broker_ready:
                try:
                    result = self._broker.place_order(
                        symbol=signal.symbol,
                        side=signal.side.value,
                        price=signal.price,
                        volume=signal.volume,
                    )
                    order.order_id = result.get("order_id", order.order_id)
                    order.status = OrderStatus.SUBMITTED
                except Exception as e:
                    logger.error(f"[TradeExecutor] 下单失败: {e}")
                    order.status = OrderStatus.REJECTED
                    order.error_msg = str(e)
                    self._stats["total_rejected"] += 1
                    return ExecutionResult(
                        success=False,
                        order_id=order.order_id,
                        reject_reason=str(e),
                        elapsed_ms=(time.time() - t0) * 1000,
                    )
            else:
                # 无券商，模拟成交
                order.status = OrderStatus.FILLED
                order.filled_price = signal.price
                order.filled_volume = signal.volume
                order.filled_at = datetime.now().isoformat()

            # 4. 处理成交
            if order.status == OrderStatus.FILLED:
                self._update_position(order)
                self._stats["total_filled"] += 1

                # 事中监控
                self._mid_trade_monitor()

            elapsed = (time.time() - t0) * 1000
            logger.info(
                f"[TradeExecutor] 信号执行完成: {signal.symbol} {signal.side.value} "
                f"{signal.volume}@{signal.price}, 状态={order.status.value}, 耗时={elapsed:.1f}ms"
            )

            return ExecutionResult(
                success=order.status == OrderStatus.FILLED,
                order_id=order.order_id,
                filled_price=order.filled_price,
                filled_volume=order.filled_volume,
                risk_score=risk_result["risk_score"],
                elapsed_ms=elapsed,
            )

    def _update_position(self, order: Order):
        """更新持仓"""
        symbol = order.symbol
        if symbol not in self._positions:
            self._positions[symbol] = {
                "symbol": symbol,
                "volume": 0,
                "avg_cost": 0.0,
                "current_price": 0.0,
                "market_value": 0.0,
                "unrealized_pnl": 0.0,
                "realized_pnl": 0.0,
            }

        pos = self._positions[symbol]
        fill_price = order.filled_price or order.price

        if order.side == OrderSide.BUY:
            total_cost = pos["avg_cost"] * pos["volume"] + fill_price * order.filled_volume
            pos["volume"] += order.filled_volume
            pos["avg_cost"] = total_cost / pos["volume"] if pos["volume"] > 0 else 0
            self._cash -= fill_price * order.filled_volume
        else:
            if pos["volume"] >= order.filled_volume:
                realized = (fill_price - pos["avg_cost"]) * order.filled_volume
                pos["realized_pnl"] += realized
                pos["volume"] -= order.filled_volume
                self._cash += fill_price * order.filled_volume
                if pos["volume"] == 0:
                    pos["avg_cost"] = 0.0

        pos["current_price"] = fill_price
        pos["market_value"] = pos["volume"] * fill_price
        pos["unrealized_pnl"] = (fill_price - pos["avg_cost"]) * pos["volume"] if pos["volume"] > 0 else 0

        self._total_invested = sum(p["market_value"] for p in self._positions.values())

    def _mid_trade_monitor(self):
        """事中风险监控"""
        total_capital = self._cash + self._total_invested
        unrealized_pnl = sum(p["unrealized_pnl"] for p in self._positions.values())

        max_drawdown = 0.0
        if total_capital > 0:
            for p in self._positions.values():
                if p["avg_cost"] > 0 and p["current_price"] < p["avg_cost"]:
                    dd = (p["avg_cost"] - p["current_price"]) * p["volume"] / total_capital
                    max_drawdown = max(max_drawdown, dd)

        result = self.risk_engine.real_time_risk_monitor({
            "unrealized_pnl": unrealized_pnl,
            "total_capital": total_capital,
            "current_drawdown": max_drawdown,
            "total_exposure": self._total_invested / total_capital if total_capital > 0 else 0,
            "market_circuit_breaker": self._circuit_breaker,
        })

        if not result["passed"]:
            for alert in result["alerts"]:
                logger.warning(f"[TradeExecutor] 事中风控告警: {alert}")
                if self._on_error:
                    self._on_error({"type": "risk_alert", "message": alert})

    # ========== 熔断控制 ==========

    def trip_circuit_breaker(self, reason: str):
        """触发熔断"""
        with self._lock:
            self._circuit_breaker = True
            self._breaker_reason = reason
            logger.error(f"[TradeExecutor] 熔断触发: {reason}")

    def reset_circuit_breaker(self):
        """重置熔断"""
        with self._lock:
            self._circuit_breaker = False
            self._breaker_reason = ""
            logger.info("[TradeExecutor] 熔断已重置")

    # ========== 日终对账 ==========

    def daily_reconciliation(self) -> Dict:
        """日终对账 — 事后风控"""
        trade_records = self.order_mgr.get_all_orders()
        result = self.risk_engine.post_trade_reconciliation([
            {
                "symbol": o.symbol,
                "side": o.side.value,
                "price": o.price,
                "volume": o.volume,
                "status": o.status.value,
                "timestamp": o.created_at,
            }
            for o in trade_records
        ])

        # 日终统计
        self._stats["daily_pnl"] = sum(p["realized_pnl"] + p["unrealized_pnl"] for p in self._positions.values())
        self._stats["cumulative_pnl"] += self._stats["daily_pnl"]

        logger.info(f"[TradeExecutor] 日终对账完成: 通过={result['passed']}, 问题={len(result['issues'])}")
        return result

    # ========== 查询接口 ==========

    def get_positions(self) -> Dict[str, Dict]:
        with self._lock:
            return dict(self._positions)

    def get_stats(self) -> Dict:
        with self._lock:
            return dict(self._stats)

    def get_cash(self) -> float:
        with self._lock:
            return self._cash

    def get_total_equity(self) -> float:
        with self._lock:
            return self._cash + self._total_invested

    def get_orders(self, status: Optional[OrderStatus] = None) -> List[Order]:
        return self.order_mgr.get_orders(status)

    def cancel_order(self, order_id: str) -> bool:
        with self._lock:
            order = self.order_mgr.get_order(order_id)
            if order and order.status in (OrderStatus.PENDING, OrderStatus.SUBMITTED):
                order.status = OrderStatus.CANCELLED
                self._stats["total_cancelled"] += 1
                return True
            return False

    def set_callbacks(self, on_order_update=None, on_trade=None, on_error=None):
        self._on_order_update = on_order_update
        self._on_trade = on_trade
        self._on_error = on_error


# 全局单例
_executor_instance: Optional[TradeExecutor] = None
_executor_lock = threading.Lock()


def get_trade_executor(mode: ExecutorMode = None) -> TradeExecutor:
    global _executor_instance
    with _executor_lock:
        if _executor_instance is None:
            _executor_instance = TradeExecutor(mode=mode or ExecutorMode.SIMULATED)
        return _executor_instance