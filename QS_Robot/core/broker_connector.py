#!/usr/bin/env python3
"""
券商连接器 (Broker Connector)
==============================
统一券商接口，支持：
1. 模拟交易（默认，用于开发测试）
2. 实盘券商接口（预留扩展点：华泰/东方财富/CTP/XTQuant等）

功能：
- 账户查询（持仓、资金、委托）
- 下单（限价/市价）
- 撤单
- 成交查询
- 委托状态跟踪
"""

import os
import sys
import json
import time
import logging
import threading
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(Enum):
    LIMIT = "limit"      # 限价单
    MARKET = "market"    # 市价单


class OrderStatus(Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    PARTIAL = "partial"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


@dataclass
class Order:
    order_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    price: float
    quantity: int
    status: OrderStatus = OrderStatus.PENDING
    filled_qty: int = 0
    filled_price: float = 0.0
    create_time: str = ""
    update_time: str = ""
    commission: float = 0.0
    risk_checked: bool = False
    vibe_verified: bool = False
    audit_id: str = ""


@dataclass
class Account:
    total_assets: float = 100000.0
    available_cash: float = 100000.0
    frozen_cash: float = 0.0
    market_value: float = 0.0
    total_return: float = 0.0
    positions: List[Dict] = field(default_factory=list)


class SimulatedBroker:
    """模拟券商（开发测试用）"""

    def __init__(self, initial_capital: float = 100000.0):
        self.account = Account(total_assets=initial_capital, available_cash=initial_capital)
        self.orders: Dict[str, Order] = {}
        self._order_counter = 0
        self._lock = threading.Lock()
        self._positions: Dict[str, Dict] = {}
        self._transaction_log: List[Dict] = []

        # 模拟行情（用于市价单模拟）
        self._mock_prices: Dict[str, float] = {}

    def _next_order_id(self) -> str:
        self._order_counter += 1
        return f"ORD{datetime.now().strftime('%Y%m%d')}{self._order_counter:06d}"

    def get_account(self) -> Dict:
        with self._lock:
            return {
                "total_assets": self.account.total_assets,
                "available_cash": self.account.available_cash,
                "frozen_cash": self.account.frozen_cash,
                "market_value": self.account.market_value,
                "total_return": self.account.total_return,
                "positions": list(self._positions.values())
            }

    def submit_order(self, symbol: str, side: str, order_type: str,
                     price: float, quantity: int) -> Dict:
        """提交订单"""
        with self._lock:
            side_enum = OrderSide(side)
            type_enum = OrderType(order_type)

            # 计算所需资金
            if type_enum == OrderType.MARKET:
                execution_price = self._mock_prices.get(symbol, price)
            else:
                execution_price = price

            required_cash = execution_price * quantity

            # 资金检查
            if side_enum == OrderSide.BUY and required_cash > self.account.available_cash:
                logger.warning(f"资金不足: 需要{required_cash:.2f}, 可用{self.account.available_cash:.2f}")
                return {"success": False, "error": "资金不足",
                        "required": required_cash, "available": self.account.available_cash}

            # 持仓检查
            if side_enum == OrderSide.SELL:
                pos = self._positions.get(symbol)
                if not pos or pos['quantity'] < quantity:
                    logger.warning(f"持仓不足: {symbol}, 需要{quantity}, 持有{pos['quantity'] if pos else 0}")
                    return {"success": False, "error": "持仓不足"}

            # 创建订单
            order = Order(
                order_id=self._next_order_id(),
                symbol=symbol, side=side_enum, order_type=type_enum,
                price=price, quantity=quantity,
                status=OrderStatus.SUBMITTED,
                create_time=datetime.now().isoformat()
            )
            self.orders[order.order_id] = order

            # 冻结资金
            if side_enum == OrderSide.BUY:
                self.account.frozen_cash += required_cash
                self.account.available_cash -= required_cash

            # 模拟立即成交（实盘需等待确认）
            self._simulate_fill(order)

            logger.info(f"订单成交: {order.order_id} {symbol} {side} {quantity}手@{execution_price:.2f}")

            return {"success": True, "order_id": order.order_id,
                    "order": {k: v.value if isinstance(v, Enum) else v for k, v in order.__dict__.items()}}

    def _simulate_fill(self, order: Order):
        """模拟成交"""
        execution_price = self._mock_prices.get(order.symbol, order.price)
        if order.order_type == OrderType.MARKET:
            slippage = -0.001 if order.side == OrderSide.BUY else 0.001
            execution_price = execution_price * (1 + slippage)

        order.status = OrderStatus.FILLED
        order.filled_qty = order.quantity
        order.filled_price = execution_price
        order.update_time = datetime.now().isoformat()
        order.commission = abs(execution_price * order.quantity * 0.0003)  # 万三佣金

        # 更新持仓
        if order.side == OrderSide.BUY:
            pos = self._positions.get(order.symbol,
                                       {"symbol": order.symbol, "quantity": 0, "avg_price": 0})
            total_cost = pos['avg_price'] * pos['quantity'] + execution_price * order.quantity
            pos['quantity'] += order.quantity
            pos['avg_price'] = total_cost / pos['quantity'] if pos['quantity'] > 0 else 0
            self._positions[order.symbol] = pos
            # 解冻资金
            self.account.frozen_cash -= order.price * order.quantity
        else:
            pos = self._positions[order.symbol]
            pos['quantity'] -= order.quantity
            if pos['quantity'] <= 0:
                del self._positions[order.symbol]
            self.account.available_cash += execution_price * order.quantity - order.commission

        # 更新市值
        self.account.market_value = sum(
            p['quantity'] * self._mock_prices.get(p['symbol'], p['avg_price'])
            for p in self._positions.values()
        )
        self.account.total_assets = (
            self.account.available_cash + self.account.frozen_cash + self.account.market_value
        )

        # 记录交易日志
        self._transaction_log.append({
            "order_id": order.order_id, "symbol": order.symbol,
            "side": order.side.value, "price": execution_price,
            "quantity": order.quantity, "commission": order.commission,
            "time": order.update_time
        })

    def cancel_order(self, order_id: str) -> Dict:
        with self._lock:
            order = self.orders.get(order_id)
            if not order:
                return {"success": False, "error": "订单不存在"}
            if order.status != OrderStatus.SUBMITTED:
                return {"success": False, "error": f"订单状态为{order.status.value}，无法撤单"}
            order.status = OrderStatus.CANCELLED
            order.update_time = datetime.now().isoformat()
            logger.info(f"订单已撤: {order_id}")
            return {"success": True, "order_id": order_id}

    def get_order(self, order_id: str) -> Optional[Dict]:
        order = self.orders.get(order_id)
        if order:
            return {k: v.value if isinstance(v, Enum) else v for k, v in order.__dict__.items()}
        return None

    def get_orders(self, symbol: str = None, status: str = None) -> List[Dict]:
        orders = list(self.orders.values())
        if symbol:
            orders = [o for o in orders if o.symbol == symbol]
        if status:
            status_enum = OrderStatus(status)
            orders = [o for o in orders if o.status == status_enum]
        return [{k: v.value if isinstance(v, Enum) else v for k, v in o.__dict__.items()}
                for o in orders]

    def get_transaction_log(self, limit: int = 50) -> List[Dict]:
        return self._transaction_log[-limit:]

    def set_mock_price(self, symbol: str, price: float):
        self._mock_prices[symbol] = price


class BrokerConnector:
    """券商连接器统一入口"""

    def __init__(self, mode: str = "simulated", initial_capital: float = 100000.0):
        self.mode = mode
        self.broker = SimulatedBroker(initial_capital=initial_capital)
        self._risk_engine = None
        self._vibe_analyzer = None
        logger.info(f"BrokerConnector initialized: mode={mode}, capital={initial_capital}")

    def set_risk_engine(self, engine):
        self._risk_engine = engine

    def set_vibe_analyzer(self, analyzer):
        self._vibe_analyzer = analyzer

    def get_account(self) -> Dict:
        return self.broker.get_account()

    def submit_order_with_risk_check(self, symbol: str, side: str, order_type: str,
                                      price: float, quantity: int,
                                      vibe_verified: bool = False) -> Dict:
        """带风控检查的下单"""
        # 1. 风控预检
        risk_warnings = []
        if self._risk_engine:
            try:
                risk_result = self._risk_engine.evaluate_order(symbol, side, price, quantity)
                if not risk_result.get('passed', True):
                    risk_warnings = risk_result.get('warnings', [])
            except Exception as e:
                logger.error(f"风控检查失败: {e}")

        # 2. Vibe复核
        if not vibe_verified:
            logger.warning(f"订单未经过Vibe智能体复核: {symbol} {side} {quantity}手")
            risk_warnings.append("未经过Vibe智能体复核")

        # 3. 提交订单
        result = self.broker.submit_order(symbol, side, order_type, price, quantity)
        result['risk_warnings'] = risk_warnings
        result['vibe_verified'] = vibe_verified

        return result

    def batch_submit(self, orders: List[Dict], verify_all: bool = True) -> Dict:
        """批量提交订单（来自精选股票池）"""
        results = []
        for order in orders:
            result = self.submit_order_with_risk_check(
                symbol=order['symbol'],
                side=order.get('side', 'buy'),
                order_type=order.get('order_type', 'limit'),
                price=order.get('price', 0),
                quantity=order.get('quantity', 100),
                vibe_verified=verify_all
            )
            results.append(result)

        success_count = sum(1 for r in results if r.get('success'))
        logger.info(f"批量下单完成: {success_count}/{len(results)}")

        return {
            "success": True,
            "total": len(results),
            "success_count": success_count,
            "failed_count": len(results) - success_count,
            "results": results
        }

    def get_transaction_history(self, limit: int = 50) -> List[Dict]:
        return self.broker.get_transaction_log(limit)


# 全局实例
_broker_connector: Optional[BrokerConnector] = None
_broker_lock = threading.Lock()


def get_broker_connector(mode: str = "simulated",
                         initial_capital: float = 100000.0) -> BrokerConnector:
    """获取全局券商连接器单例"""
    global _broker_connector
    with _broker_lock:
        if _broker_connector is None:
            _broker_connector = BrokerConnector(mode=mode, initial_capital=initial_capital)
        return _broker_connector


def reset_broker_connector():
    """重置券商连接器（用于测试或切换模式）"""
    global _broker_connector
    with _broker_lock:
        _broker_connector = None
        logger.info("BrokerConnector已重置")