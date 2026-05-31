#!/usr/bin/env python3
"""
西部宽客（XBK）券商适配器

将现有 xbk_api_client.py / xbk_simulator.py 封装为统一的 BrokerInterface。
支持真实API模式和模拟模式。

使用方式:
    # 真实API模式
    adapter = XbkAdapter(api_key="xxx", api_secret="xxx")

    # 模拟模式（用于开发测试）
    adapter = XbkAdapter(simulated=True, initial_balance=1000000.0)
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
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


class XbkAdapter(BrokerInterface):
    """
    西部宽客适配器

    将 XbkApiClient/XbkTrader/XbkSimulatedTrader 统一包装为 BrokerInterface。
    """

    def __init__(
        self,
        api_key: str = "",
        api_secret: str = "",
        api_url: str = "https://api.westquant.cn",
        simulated: bool = False,
        initial_balance: float = 1000000.0,
    ):
        """
        初始化适配器

        Args:
            api_key:         API密钥（真实模式）
            api_secret:      API密钥（真实模式）
            api_url:         API地址（真实模式）
            simulated:       是否使用模拟模式
            initial_balance: 模拟模式初始资金
        """
        self._broker_type = BrokerType.XBK
        self._connection_state = ConnectionState.DISCONNECTED
        self._simulated = simulated
        self._client = None
        self._trader = None
        self._data_feed = None
        self._orders_cache: Dict[str, OrderData] = {}
        self._order_counter = 0

        if simulated:
            self._init_simulated(initial_balance)
        else:
            self._api_key = api_key
            self._api_secret = api_secret
            self._api_url = api_url

    def _init_simulated(self, initial_balance: float):
        """初始化模拟器"""
        from xbk_simulator import XbkSimulatedTrader as SimTrader

        self._sim_trader = SimTrader(initial_balance=initial_balance)
        logger.info(f"XBK适配器已初始化为模拟模式，初始资金: {initial_balance}")

    # ═══════════════════════════════════════════════════════════
    # 连接管理
    # ═══════════════════════════════════════════════════════════

    def connect(self) -> BrokerResult:
        self._connection_state = ConnectionState.CONNECTING

        if self._simulated:
            result = self._sim_trader.login("aurora_user", "aurora_pass")
            if result.get("code") == 0:
                self._connection_state = ConnectionState.CONNECTED
                return BrokerResult.ok({"token": result["data"].get("token")})
            else:
                self._connection_state = ConnectionState.ERROR
                return BrokerResult.fail(result.get("message", "登录失败"))

        # 真实API模式
        from xbk_api_client import XbkApiClient

        self._client = XbkApiClient(self._api_key, self._api_secret, self._api_url)
        # XbkApiClient 无显式连接检查，用获取账户信息测试
        try:
            resp = self._client.get_account_info()
            if resp.get("code") == 0:
                self._connection_state = ConnectionState.CONNECTED
                return BrokerResult.ok(resp.get("data"))
            else:
                self._connection_state = ConnectionState.ERROR
                return BrokerResult.fail(resp.get("msg", "连接失败"))
        except Exception as e:
            self._connection_state = ConnectionState.ERROR
            return BrokerResult.fail(f"连接异常: {e}")

    def disconnect(self) -> BrokerResult:
        if self._simulated:
            try:
                self._sim_trader.logout()
            except Exception:
                pass

        self._connection_state = ConnectionState.DISCONNECTED
        self._client = None
        return BrokerResult.ok(message="已断开")

    def health_check(self) -> BrokerResult:
        start = time.time()
        try:
            if self._simulated:
                connected = getattr(self._sim_trader, "connected", False)
                latency = (time.time() - start) * 1000
            else:
                if not self._client:
                    connected = False
                    latency = 0
                else:
                    resp = self._client.get_account_info()
                    connected = resp.get("code") == 0
                    latency = (time.time() - start) * 1000
        except Exception:
            connected = False
            latency = 0

        return BrokerResult.ok({
            "connected": connected,
            "latency_ms": round(latency, 2),
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

        if self._simulated:
            resp = self._sim_trader.get_ticker(symbol)
            if resp.get("code") != 0:
                return BrokerResult.fail(resp.get("message", "获取行情失败"))
            data = resp.get("data", {})
            return BrokerResult.ok(TickerData(
                symbol=symbol,
                timestamp=datetime.now(),
                last_price=float(data.get("last_price", 0)),
                open_price=float(data.get("open", 0)),
                high_price=float(data.get("high", 0)),
                low_price=float(data.get("low", 0)),
                close_price=float(data.get("close", 0)),
                volume=float(data.get("volume", 0)),
                raw=data,
            ))

        from xbk_api_client import XbkDataFeed
        if not self._data_feed:
            self._data_feed = XbkDataFeed(self._client)
            self._data_feed.set_symbol(symbol)

        result = self._data_feed.get_latest_price()
        return BrokerResult.ok(TickerData(
            symbol=symbol,
            timestamp=datetime.now(),
            last_price=float(result.get("price", 0)),
            open_price=float(result.get("open", 0)),
            high_price=float(result.get("high", 0)),
            low_price=float(result.get("low", 0)),
            volume=float(result.get("volume", 0)),
            raw=result,
        ))

    def get_kline(self, symbol: str, interval: str = "1d", limit: int = 200,
                  start_date: Optional[str] = None, end_date: Optional[str] = None) -> BrokerResult:
        symbol = normalize_symbol(symbol)
        # 映射到XBK的时间周期格式
        interval_map = {"1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
                         "1h": "1h", "4h": "4h", "1d": "1d", "1w": "1w", "1M": "1M"}
        xbk_interval = interval_map.get(interval, "1d")

        if self._simulated:
            resp = self._sim_trader.get_kline(symbol, xbk_interval, limit)
            if resp.get("code") != 0:
                return BrokerResult.fail(resp.get("message", "获取K线失败"))
            klines = resp.get("data", [])
        else:
            resp = self._client.get_kline(symbol, xbk_interval, limit)
            if resp.get("code") != 0:
                return BrokerResult.fail(resp.get("msg", "获取K线失败"))
            klines = resp.get("data", [])

        result = []
        for k in klines:
            ts = k.get("timestamp")
            if isinstance(ts, str):
                ts = datetime.fromisoformat(ts)
            elif isinstance(ts, (int, float)):
                ts = datetime.fromtimestamp(ts / 1000)
            else:
                ts = datetime.now()

            result.append(KlineData(
                symbol=symbol,
                interval=interval,
                timestamp=ts,
                open_price=float(k.get("open", 0)),
                high_price=float(k.get("high", 0)),
                low_price=float(k.get("low", 0)),
                close_price=float(k.get("close", 0)),
                volume=float(k.get("volume", 0)),
            ))

        return BrokerResult.ok(result)

    def get_batch_tickers(self, symbols: List[str]) -> BrokerResult:
        results = []
        for sym in symbols:
            r = self.get_ticker(sym)
            if r.success and r.data:
                results.append(r.data)
        return BrokerResult.ok(results)

    # ═══════════════════════════════════════════════════════════
    # 账户管理
    # ═══════════════════════════════════════════════════════════

    def get_account(self) -> BrokerResult:
        if self._simulated:
            resp = self._sim_trader.get_account_info()
            if resp.get("code") != 0:
                return BrokerResult.fail(resp.get("message", "获取账户失败"))
            d = resp.get("data", {})
            return BrokerResult.ok(AccountInfo(
                account_id="XBK_SIM_001",
                broker_type=BrokerType.SIMULATED,
                total_asset=float(d.get("total_value", 0)),
                available_cash=float(d.get("available", 0)),
                frozen_cash=float(d.get("frozen", 0)),
                market_value=float(d.get("position_value", 0)),
            ))

        resp = self._client.get_account_info()
        if resp.get("code") != 0:
            return BrokerResult.fail(resp.get("msg", "获取账户失败"))
        d = resp.get("data", {})
        return BrokerResult.ok(AccountInfo(
            account_id=d.get("account_id", "XBK_API"),
            broker_type=BrokerType.XBK,
            total_asset=float(d.get("total_asset", 0)),
            available_cash=float(d.get("available", 0)),
            frozen_cash=float(d.get("frozen", 0)),
        ))

    def get_positions(self) -> BrokerResult:
        if self._simulated:
            resp = self._sim_trader.get_positions()
            if resp.get("code") != 0:
                return BrokerResult.fail(resp.get("message", "获取持仓失败"))
            positions = []
            for p in resp.get("data", []):
                positions.append(PositionData(
                    symbol=p.get("symbol", ""),
                    quantity=float(p.get("quantity", 0)),
                    average_cost=float(p.get("average_price", 0)),
                    current_price=float(p.get("current_price", 0)),
                    market_value=float(p.get("value", 0)),
                    unrealized_pnl=float(p.get("unrealized_pnl", 0)),
                ))
            return BrokerResult.ok(positions)

        resp = self._client.get_positions()
        if resp.get("code") != 0:
            return BrokerResult.fail(resp.get("msg", "获取持仓失败"))
        positions = []
        for p in resp.get("data", []):
            positions.append(PositionData(
                symbol=p.get("symbol", ""),
                quantity=float(p.get("quantity", 0)),
                average_cost=float(p.get("avg_price", 0)),
                current_price=float(p.get("current_price", 0)),
                market_value=float(p.get("market_value", 0)),
                unrealized_pnl=float(p.get("unrealized_pnl", 0)),
            ))
        return BrokerResult.ok(positions)

    # ═══════════════════════════════════════════════════════════
    # 订单管理
    # ═══════════════════════════════════════════════════════════

    def place_order(self, symbol: str, side: OrderSide, order_type: OrderType,
                    quantity: float, price: Optional[float] = None,
                    stop_price: Optional[float] = None) -> BrokerResult:
        symbol = normalize_symbol(symbol)

        if self._simulated:
            from xbk_simulator import OrderSide as SimSide, OrderType as SimType
            sim_side = SimSide.BUY if side == OrderSide.BUY else SimSide.SELL
            sim_type_map = {OrderType.MARKET: SimType.MARKET, OrderType.LIMIT: SimType.LIMIT,
                            OrderType.STOP: SimType.STOP, OrderType.STOP_LIMIT: SimType.STOP}
            sim_type = sim_type_map.get(order_type, SimType.LIMIT)
            result = self._sim_trader.place_order(symbol, sim_side, sim_type, quantity, price, stop_price)
            if result.get("code") == 0:
                self._order_counter += 1
                data = result.get("data", {})
                order = OrderData(
                    order_id=data.get("order_id", f"XBK_{self._order_counter}"),
                    symbol=symbol, side=side, order_type=order_type,
                    quantity=quantity, price=data.get("price", price or 0),
                    status=OrderStatus.FILLED,
                    create_time=datetime.now(),
                )
                self._orders_cache[order.order_id] = order
                return BrokerResult.ok(order)
            return BrokerResult.fail(result.get("message", "下单失败"))

        # 真实API
        xbk_side = "buy" if side == OrderSide.BUY else "sell"
        xbk_type = "market" if order_type == OrderType.MARKET else "limit"
        result = self._client.place_order(symbol, xbk_side, xbk_type, quantity, price)
        if result.get("code") == 0:
            data = result.get("data", {})
            order = OrderData(
                order_id=data.get("order_id", ""),
                symbol=symbol, side=side, order_type=order_type,
                quantity=quantity, price=price or 0,
                status=OrderStatus.SUBMITTED,
                create_time=datetime.now(),
            )
            return BrokerResult.ok(order)
        return BrokerResult.fail(result.get("msg", "下单失败"))

    def cancel_order(self, order_id: str) -> BrokerResult:
        if self._simulated:
            result = self._sim_trader.cancel_order(order_id)
            if result.get("code") == 0:
                if order_id in self._orders_cache:
                    self._orders_cache[order_id].status = OrderStatus.CANCELLED
                    return BrokerResult.ok(self._orders_cache[order_id])
            return BrokerResult.fail(result.get("message", "撤单失败"))

        result = self._client.cancel_order(order_id)
        if result.get("code") == 0:
            return BrokerResult.ok(result.get("data"))
        return BrokerResult.fail(result.get("msg", "撤单失败"))

    def get_order(self, order_id: str) -> BrokerResult:
        if order_id in self._orders_cache:
            return BrokerResult.ok(self._orders_cache[order_id])

        if self._simulated:
            result = self._sim_trader.get_order_info(order_id)
            if result.get("code") == 0:
                data = result.get("data", {})
                return BrokerResult.ok(self._sim_order_to_standard(data))
            return BrokerResult.fail("订单不存在")

        result = self._client.get_order_info(order_id)
        if result.get("code") == 0:
            return BrokerResult.ok(result.get("data"))
        return BrokerResult.fail(result.get("msg", "查询失败"))

    def get_orders(self, symbol: Optional[str] = None,
                   status: Optional[OrderStatus] = None,
                   limit: int = 100) -> BrokerResult:
        if self._simulated:
            orders = list(self._orders_cache.values())
            if symbol:
                orders = [o for o in orders if o.symbol == symbol]
            if status:
                orders = [o for o in orders if o.status == status]
            return BrokerResult.ok(orders[:limit])

        result = self._client.get_order_history(symbol=symbol, limit=limit)
        if result.get("code") != 0:
            return BrokerResult.fail(result.get("msg", "查询失败"))
        return BrokerResult.ok(result.get("data", []))

    # ═══════════════════════════════════════════════════════════
    # 信息查询
    # ═══════════════════════════════════════════════════════════

    def get_broker_info(self) -> Dict[str, Any]:
        return {
            "name": "西部宽客",
            "broker_type": BrokerType.XBK.value if not self._simulated else BrokerType.SIMULATED.value,
            "supports": ["stock", "etf", "futures", "crypto"],
            "market": ["SH", "SZ", "HK"],
            "commission_rate": 0.00025,
            "min_commission": 5.0,
            "trading_hours": "09:30-11:30,13:00-15:00",
            "api_version": "v2",
            "simulated": self._simulated,
        }

    def get_stock_list(self, market: str = "A") -> BrokerResult:
        """从XBK获取可交易股票列表"""
        # XBK暂不支持股票列表接口，返回模拟列表
        sample_stocks = [
            {"symbol": "000001.SZ", "name": "平安银行", "market": "SZ", "sector": "银行"},
            {"symbol": "600519.SH", "name": "贵州茅台", "market": "SH", "sector": "白酒"},
            {"symbol": "000858.SZ", "name": "五粮液",   "market": "SZ", "sector": "白酒"},
            {"symbol": "300750.SZ", "name": "宁德时代", "market": "SZ", "sector": "新能源"},
            {"symbol": "601318.SH", "name": "中国平安", "market": "SH", "sector": "保险"},
            {"symbol": "000333.SZ", "name": "美的集团", "market": "SZ", "sector": "家电"},
        ]
        return BrokerResult.ok(sample_stocks)

    # ═══════════════════════════════════════════════════════════
    # 私有辅助方法
    # ═══════════════════════════════════════════════════════════

    def _sim_order_to_standard(self, data: dict) -> OrderData:
        """将模拟订单转为标准格式"""
        side_str = data.get("side", "buy")
        type_str = data.get("type", "market")
        status_str = data.get("status", "filled")

        side_map = {"buy": OrderSide.BUY, "sell": OrderSide.SELL}
        type_map = {"market": OrderType.MARKET, "limit": OrderType.LIMIT, "stop": OrderType.STOP}
        status_map = {
            "pending": OrderStatus.PENDING, "filled": OrderStatus.FILLED,
            "partial": OrderStatus.PARTIAL, "cancelled": OrderStatus.CANCELLED,
            "rejected": OrderStatus.REJECTED,
        }

        return OrderData(
            order_id=data.get("order_id", ""),
            symbol=data.get("symbol", ""),
            side=side_map.get(side_str, OrderSide.BUY),
            order_type=type_map.get(type_str, OrderType.MARKET),
            quantity=float(data.get("quantity", 0)),
            price=float(data.get("price", 0)),
            status=status_map.get(status_str, OrderStatus.PENDING),
            create_time=datetime.now(),
        )