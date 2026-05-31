#!/usr/bin/env python3
"""
中泰证券适配器

预留中泰证券 API 接入框架，实现 BrokerInterface。
实际 API 接入时，替换 _real_* 方法中的桩数据即可。

目前提供：
  - 完整的接口实现（桩数据 + 模拟模式）
  - 待接入真实中泰证券 API 时的规范替换点
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from broker_interface import (
    AccountInfo,
    BrokerInterface,
    BrokerResult,
    BrokerType,
    ConnectionState,
    KlineData,
    OrderData,
    OrderSide,
    OrderStatus,
    OrderType,
    PositionData,
    TickerData,
    normalize_symbol,
)

logger = logging.getLogger(__name__)


class ZhongTaiAdapter(BrokerInterface):
    """
    中泰证券适配器

    实现 BrokerInterface，预留真实 API 接入点。
    当前为模拟模式，接入真实 API 时只需替换 _real_* 方法。
    """

    # ── 中泰特有配置 ────────────────────────────────────

    # 交易时间
    MORNING_OPEN = "09:30"
    MORNING_CLOSE = "11:30"
    AFTERNOON_OPEN = "13:00"
    AFTERNOON_CLOSE = "15:00"

    # 佣金费率（中泰标准）
    _COMMISSION_RATE = 0.00025  # 万2.5
    _MIN_COMMISSION = 5.0       # 最低5元
    _STAMP_TAX_RATE = 0.001     # 印花税（卖出时）

    def __init__(self, account_id: str = "ZT_DEFAULT", simulated: bool = True,
                 initial_balance: float = 1000000.0, **kwargs):
        """
        初始化中泰适配器

        Args:
            account_id:      账户ID
            simulated:       是否模拟模式
            initial_balance: 模拟初始资金
            **kwargs:        预留扩展（如真实API的app_key/app_secret）
        """
        self._broker_type = BrokerType.ZHONGTAI
        self._connection_state = ConnectionState.DISCONNECTED
        self._simulated = simulated
        self._account_id = account_id
        self._initial_balance = initial_balance
        self._balance = initial_balance
        self._available = initial_balance
        self._positions: Dict[str, PositionData] = {}
        self._orders: Dict[str, OrderData] = {}
        self._order_counter = 0

        # 预留真实API凭证
        self._app_key = kwargs.get("app_key", "")
        self._app_secret = kwargs.get("app_secret", "")
        self._api_url = kwargs.get("api_url", "")

        logger.info(f"中泰证券适配器初始化完成 (simulated={simulated})")

    # ═══════════════════════════════════════════════════════════
    # 连接管理
    # ═══════════════════════════════════════════════════════════

    def connect(self) -> BrokerResult:
        self._connection_state = ConnectionState.CONNECTING

        if self._simulated:
            self._connection_state = ConnectionState.CONNECTED
            return BrokerResult.ok({"account_id": self._account_id, "simulated": True})

        # TODO: 真实中泰API接入点
        try:
            # result = ZhongTaiApiClient(self._app_key, self._app_secret).connect()
            # if result.success:
            #     self._connection_state = ConnectionState.CONNECTED
            #     return BrokerResult.ok(result.data)
            self._connection_state = ConnectionState.ERROR
            return BrokerResult.fail("中泰证券真实API尚未接入，请使用模拟模式")
        except Exception as e:
            self._connection_state = ConnectionState.ERROR
            return BrokerResult.fail(f"连接异常: {e}")

    def disconnect(self) -> BrokerResult:
        self._connection_state = ConnectionState.DISCONNECTED
        return BrokerResult.ok(message="已断开")

    def health_check(self) -> BrokerResult:
        return BrokerResult.ok({
            "connected": self._connection_state == ConnectionState.CONNECTED,
            "latency_ms": 0,
            "broker_type": self._broker_type.value,
            "simulated": self._simulated,
            "server_time": datetime.now().isoformat(),
        })

    @property
    def connection_state(self) -> ConnectionState:
        return self._connection_state

    @property
    def broker_type(self) -> BrokerType:
        return self._broker_type

    # ═══════════════════════════════════════════════════════════
    # 行情数据
    # ═══════════════════════════════════════════════════════════

    def get_ticker(self, symbol: str) -> BrokerResult:
        symbol = normalize_symbol(symbol)
        # 模拟行情
        import random
        seed = sum(ord(c) for c in symbol) + datetime.now().day
        random.seed(seed)
        base_price = 50.0 + (hash(symbol) % 200)
        price = base_price * (1 + random.uniform(-0.02, 0.02))
        change = price - base_price

        return BrokerResult.ok(TickerData(
            symbol=symbol,
            timestamp=datetime.now(),
            last_price=round(price, 2),
            open_price=round(base_price * 0.995, 2),
            high_price=round(price * 1.008, 2),
            low_price=round(price * 0.992, 2),
            volume=random.randint(1000000, 50000000),
            turnover=random.randint(5000000, 200000000),
            change=round(change, 2),
            change_pct=round(change / base_price * 100, 2),
            pre_close=round(base_price, 2),
        ))

    def get_kline(self, symbol: str, interval: str = "1d", limit: int = 200,
                  start_date: Optional[str] = None, end_date: Optional[str] = None) -> BrokerResult:
        symbol = normalize_symbol(symbol)

        import random
        seed = sum(ord(c) for c in symbol)
        random.seed(seed)

        base_price = 50.0 + (hash(symbol) % 200)
        now = datetime.now()
        klines = []

        for i in range(limit):
            day = now - timedelta(days=limit - i)
            change_pct = random.uniform(-0.03, 0.03)
            open_p = base_price * (1 + random.uniform(-0.01, 0.01))
            close_p = open_p * (1 + change_pct)
            high_p = max(open_p, close_p) * (1 + random.uniform(0, 0.015))
            low_p = min(open_p, close_p) * (1 - random.uniform(0, 0.015))

            klines.append(KlineData(
                symbol=symbol,
                interval=interval,
                timestamp=day,
                open_price=round(open_p, 2),
                high_price=round(high_p, 2),
                low_price=round(low_p, 2),
                close_price=round(close_p, 2),
                volume=random.randint(5000000, 30000000),
            ))
            base_price = close_p

        return BrokerResult.ok(klines)

    def get_batch_tickers(self, symbols: List[str]) -> BrokerResult:
        return BrokerResult.ok([self.get_ticker(s).data for s in symbols if self.get_ticker(s).success])

    # ═══════════════════════════════════════════════════════════
    # 账户管理
    # ═══════════════════════════════════════════════════════════

    def get_account(self) -> BrokerResult:
        if not self._simulated:
            return self._real_get_account()

        mv = sum(p.market_value for p in self._positions.values())
        return BrokerResult.ok(AccountInfo(
            account_id=self._account_id,
            broker_type=BrokerType.SIMULATED,
            total_asset=self._available + mv,
            available_cash=self._available,
            frozen_cash=self._initial_balance - self._available - mv,
            market_value=mv,
        ))

    def _real_get_account(self) -> BrokerResult:
        """TODO: 真实中泰API — 获取账户信息"""
        return BrokerResult.fail("真实API尚未接入")

    def get_positions(self) -> BrokerResult:
        if not self._simulated:
            return self._real_get_positions()
        return BrokerResult.ok(list(self._positions.values()))

    def _real_get_positions(self) -> BrokerResult:
        """TODO: 真实中泰API — 获取持仓"""
        return BrokerResult.fail("真实API尚未接入")

    # ═══════════════════════════════════════════════════════════
    # 订单管理
    # ═══════════════════════════════════════════════════════════

    def place_order(self, symbol: str, side: OrderSide, order_type: OrderType,
                    quantity: float, price: Optional[float] = None,
                    stop_price: Optional[float] = None) -> BrokerResult:
        symbol = normalize_symbol(symbol)

        if not self._simulated:
            return self._real_place_order(symbol, side, order_type, quantity, price, stop_price)

        # 模拟下单
        tk = self.get_ticker(symbol)
        if not tk.success:
            return BrokerResult.fail("获取行情失败")

        current_price = tk.data.last_price
        exec_price = price if order_type in (OrderType.LIMIT, OrderType.STOP_LIMIT) else current_price
        amount = quantity * exec_price

        if side == OrderSide.BUY:
            if self._available < amount:
                return BrokerResult.fail("可用资金不足")
            commission = max(amount * self._COMMISSION_RATE, self._MIN_COMMISSION)
            self._available -= (amount + commission)
            if symbol in self._positions:
                old = self._positions[symbol]
                total_qty = old.quantity + quantity
                avg_cost = (old.average_cost * old.quantity + exec_price * quantity) / total_qty
                self._positions[symbol] = PositionData(
                    symbol=symbol, quantity=total_qty,
                    average_cost=avg_cost, current_price=current_price,
                    market_value=total_qty * current_price,
                    unrealized_pnl=total_qty * (current_price - avg_cost),
                )
            else:
                self._positions[symbol] = PositionData(
                    symbol=symbol, quantity=quantity,
                    average_cost=exec_price, current_price=current_price,
                    market_value=quantity * current_price,
                    unrealized_pnl=quantity * (current_price - exec_price),
                )
        else:
            if symbol not in self._positions or self._positions[symbol].quantity < quantity:
                return BrokerResult.fail("持仓不足")
            commission = max(amount * (self._COMMISSION_RATE + self._STAMP_TAX_RATE), self._MIN_COMMISSION)
            self._available += (amount - commission)
            old = self._positions[symbol]
            remaining = old.quantity - quantity
            if remaining <= 0:
                del self._positions[symbol]
            else:
                self._positions[symbol] = PositionData(
                    symbol=symbol, quantity=remaining,
                    average_cost=old.average_cost, current_price=current_price,
                    market_value=remaining * current_price,
                    unrealized_pnl=remaining * (current_price - old.average_cost),
                )

        self._order_counter += 1
        order_id = f"ZT_{datetime.now().strftime('%Y%m%d%H%M%S')}_{self._order_counter:04d}"
        order = OrderData(
            order_id=order_id, symbol=symbol, side=side, order_type=order_type,
            quantity=quantity, price=exec_price,
            filled_quantity=quantity, filled_price=exec_price,
            status=OrderStatus.FILLED, commission=commission,
            create_time=datetime.now(), update_time=datetime.now(),
        )
        self._orders[order_id] = order
        return BrokerResult.ok(order)

    def _real_place_order(self, symbol, side, order_type, quantity, price, stop_price):
        """TODO: 真实中泰API — 下单"""
        return BrokerResult.fail("真实API尚未接入")

    def cancel_order(self, order_id: str) -> BrokerResult:
        if not self._simulated:
            return self._real_cancel_order(order_id)
        if order_id in self._orders:
            self._orders[order_id].status = OrderStatus.CANCELLED
            return BrokerResult.ok(self._orders[order_id])
        return BrokerResult.fail("订单不存在")

    def _real_cancel_order(self, order_id):
        return BrokerResult.fail("真实API尚未接入")

    def get_order(self, order_id: str) -> BrokerResult:
        if not self._simulated:
            return self._real_get_order(order_id)
        if order_id in self._orders:
            return BrokerResult.ok(self._orders[order_id])
        return BrokerResult.fail("订单不存在")

    def _real_get_order(self, order_id):
        return BrokerResult.fail("真实API尚未接入")

    def get_orders(self, symbol: Optional[str] = None,
                   status: Optional[OrderStatus] = None,
                   limit: int = 100) -> BrokerResult:
        if not self._simulated:
            return self._real_get_orders(symbol, status, limit)
        orders = list(self._orders.values())
        if symbol:
            orders = [o for o in orders if o.symbol == symbol]
        if status:
            orders = [o for o in orders if o.status == status]
        return BrokerResult.ok(sorted(orders, key=lambda o: o.create_time or datetime.min, reverse=True)[:limit])

    def _real_get_orders(self, symbol, status, limit):
        return BrokerResult.fail("真实API尚未接入")

    # ═══════════════════════════════════════════════════════════
    # 信息查询
    # ═══════════════════════════════════════════════════════════

    def get_broker_info(self) -> Dict[str, Any]:
        return {
            "name": "中泰证券",
            "broker_type": BrokerType.ZHONGTAI.value,
            "supports": ["stock", "etf", "fund", "bond"],
            "market": ["SH", "SZ", "HK"],
            "commission_rate": 0.00025,
            "min_commission": 5.0,
            "stamp_tax_rate": 0.001,
            "trading_hours": "09:30-11:30,13:00-15:00",
            "simulated": self._simulated,
            "real_api_ready": not self._simulated and bool(self._app_key),
        }

    def get_stock_list(self, market: str = "A") -> BrokerResult:
        """获取中泰可交易股票列表"""
        sample = [
            {"symbol": "600519.SH", "name": "贵州茅台", "market": "SH", "sector": "白酒"},
            {"symbol": "000858.SZ", "name": "五粮液",   "market": "SZ", "sector": "白酒"},
            {"symbol": "300750.SZ", "name": "宁德时代", "market": "SZ", "sector": "新能源"},
            {"symbol": "002415.SZ", "name": "海康威视", "market": "SZ", "sector": "安防"},
            {"symbol": "600036.SH", "name": "招商银行", "market": "SH", "sector": "银行"},
            {"symbol": "603259.SH", "name": "药明康德", "market": "SH", "sector": "医药"},
            {"symbol": "000725.SZ", "name": "京东方A",  "market": "SZ", "sector": "面板"},
            {"symbol": "002475.SZ", "name": "立讯精密", "market": "SZ", "sector": "消费电子"},
        ]
        return BrokerResult.ok(sample)