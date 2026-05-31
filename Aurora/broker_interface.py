#!/usr/bin/env python3
"""
Aurora量化交易系统 — 券商接口抽象层 (Broker Interface)

定义统一的券商接入规范，支持多券商无缝切换。
所有券商适配器必须实现此接口。

设计原则：
  - 接口与实现分离：技术分析、策略层只依赖此接口，不感知具体券商
  - 统一数据格式：所有券商返回标准化的行情/账户/订单数据结构
  - 动态切换：运行时可通过 BrokerManager 热切换券商
  - 模拟/真实统一：XbkSimulatedTrader 和真实券商使用相同接口

支持的券商类型：
  - 西部宽客 (XBK/西部证券)
  - 中泰证券 (ZhongTai)
  - 更多券商可通过实现此接口快速接入
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


# ═══════════════════════════════════════════════════════════════
# 枚举定义
# ═══════════════════════════════════════════════════════════════

class OrderSide(str, Enum):
    """订单方向"""
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    """订单类型"""
    MARKET = "market"      # 市价单
    LIMIT = "limit"        # 限价单
    STOP = "stop"          # 止损单
    STOP_LIMIT = "stop_limit"  # 止损限价单


class OrderStatus(str, Enum):
    """订单状态"""
    PENDING = "pending"        # 待提交
    SUBMITTED = "submitted"    # 已提交
    PARTIAL = "partial"        # 部分成交
    FILLED = "filled"          # 完全成交
    CANCELLED = "cancelled"    # 已取消
    REJECTED = "rejected"      # 已拒绝
    EXPIRED = "expired"        # 已过期


class BrokerType(str, Enum):
    """券商类型"""
    XBK = "xbk"               # 西部宽客
    ZHONGTAI = "zhongtai"     # 中泰证券
    SIMULATED = "simulated"   # 模拟券商


class ConnectionState(str, Enum):
    """连接状态"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


# ═══════════════════════════════════════════════════════════════
# 标准化数据结构
# ═══════════════════════════════════════════════════════════════

@dataclass
class TickerData:
    """标准化行情数据"""
    symbol: str
    timestamp: datetime
    last_price: float
    open_price: float = 0.0
    high_price: float = 0.0
    low_price: float = 0.0
    close_price: float = 0.0
    volume: float = 0.0
    turnover: float = 0.0        # 成交额
    bid_price: float = 0.0       # 买一价
    ask_price: float = 0.0       # 卖一价
    bid_volume: float = 0.0      # 买一量
    ask_volume: float = 0.0      # 卖一量
    change: float = 0.0          # 涨跌额
    change_pct: float = 0.0      # 涨跌幅(%)
    pre_close: float = 0.0       # 昨收
    raw: Dict[str, Any] = field(default_factory=dict)  # 原始数据

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp.isoformat(),
            "last_price": self.last_price,
            "open": self.open_price,
            "high": self.high_price,
            "low": self.low_price,
            "close": self.close_price,
            "volume": self.volume,
            "turnover": self.turnover,
            "bid": self.bid_price,
            "ask": self.ask_price,
            "change": self.change,
            "change_pct": self.change_pct,
            "pre_close": self.pre_close,
        }


@dataclass
class KlineData:
    """标准化K线数据"""
    symbol: str
    interval: str               # 1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w, 1M
    timestamp: datetime
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    volume: float
    turnover: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "interval": self.interval,
            "timestamp": self.timestamp.isoformat(),
            "open": self.open_price,
            "high": self.high_price,
            "low": self.low_price,
            "close": self.close_price,
            "volume": self.volume,
            "turnover": self.turnover,
        }


@dataclass
class AccountInfo:
    """标准化账户信息"""
    account_id: str
    broker_type: BrokerType
    total_asset: float = 0.0        # 总资产
    available_cash: float = 0.0     # 可用资金
    frozen_cash: float = 0.0        # 冻结资金
    market_value: float = 0.0       # 持仓市值
    total_profit: float = 0.0       # 累计盈亏
    today_profit: float = 0.0       # 当日盈亏
    today_profit_pct: float = 0.0   # 当日盈亏率

    def to_dict(self) -> Dict[str, Any]:
        return {
            "account_id": self.account_id,
            "broker_type": self.broker_type.value,
            "total_asset": self.total_asset,
            "available_cash": self.available_cash,
            "frozen_cash": self.frozen_cash,
            "market_value": self.market_value,
            "total_profit": self.total_profit,
            "today_profit": self.today_profit,
            "today_profit_pct": self.today_profit_pct,
        }


@dataclass
class PositionData:
    """标准化持仓数据"""
    symbol: str
    quantity: float                 # 持仓数量
    available_quantity: float = 0.0 # 可用数量
    average_cost: float = 0.0       # 成本价
    current_price: float = 0.0      # 当前价
    market_value: float = 0.0       # 市值
    unrealized_pnl: float = 0.0     # 浮动盈亏
    unrealized_pnl_pct: float = 0.0 # 浮动盈亏率
    today_quantity: float = 0.0     # 今日买入量

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "quantity": self.quantity,
            "available_quantity": self.available_quantity,
            "average_cost": self.average_cost,
            "current_price": self.current_price,
            "market_value": self.market_value,
            "unrealized_pnl": self.unrealized_pnl,
            "unrealized_pnl_pct": self.unrealized_pnl_pct,
        }


@dataclass
class OrderData:
    """标准化订单数据"""
    order_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    price: float = 0.0              # 委托价（市价单为0）
    filled_quantity: float = 0.0    # 已成交数量
    filled_price: float = 0.0       # 成交均价
    status: OrderStatus = OrderStatus.PENDING
    create_time: Optional[datetime] = None
    update_time: Optional[datetime] = None
    commission: float = 0.0         # 手续费
    remark: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "order_id": self.order_id,
            "symbol": self.symbol,
            "side": self.side.value,
            "order_type": self.order_type.value,
            "quantity": self.quantity,
            "price": self.price,
            "filled_quantity": self.filled_quantity,
            "filled_price": self.filled_price,
            "status": self.status.value,
            "create_time": self.create_time.isoformat() if self.create_time else None,
            "update_time": self.update_time.isoformat() if self.update_time else None,
            "commission": self.commission,
            "remark": self.remark,
        }


@dataclass
class BrokerResult:
    """券商操作统一返回"""
    success: bool
    message: str = ""
    data: Any = None
    error_code: int = 0

    @classmethod
    def ok(cls, data: Any = None, message: str = "success") -> BrokerResult:
        return cls(success=True, message=message, data=data)

    @classmethod
    def fail(cls, message: str, error_code: int = -1, data: Any = None) -> BrokerResult:
        return cls(success=False, message=message, error_code=error_code, data=data)


# ═══════════════════════════════════════════════════════════════
# 抽象券商接口
# ═══════════════════════════════════════════════════════════════

class BrokerInterface(ABC):
    """
    券商接口抽象基类

    所有券商适配器必须实现此接口。
    技术分析、策略、回测等上层模块仅依赖此接口，实现券商解耦。

    接口分为5大类：
      1. 连接管理：connect / disconnect / health_check
      2. 行情数据：get_ticker / get_kline / subscribe
      3. 账户管理：get_account / get_positions
      4. 订单管理：place_order / cancel_order / get_order / get_orders
      5. 信息查询：get_broker_info
    """

    # ── 连接管理 ────────────────────────────────────────

    @abstractmethod
    def connect(self) -> BrokerResult:
        """建立券商连接"""
        ...

    @abstractmethod
    def disconnect(self) -> BrokerResult:
        """断开券商连接"""
        ...

    @abstractmethod
    def health_check(self) -> BrokerResult:
        """
        健康检查

        Returns:
            BrokerResult，data中包含:
            - connected: bool
            - latency_ms: float
            - broker_type: str
            - server_time: datetime
        """
        ...

    @property
    @abstractmethod
    def connection_state(self) -> ConnectionState:
        """获取当前连接状态"""
        ...

    @property
    @abstractmethod
    def broker_type(self) -> BrokerType:
        """获取券商类型"""
        ...

    # ── 行情数据 ────────────────────────────────────────

    @abstractmethod
    def get_ticker(self, symbol: str) -> BrokerResult:
        """
        获取实时行情

        Args:
            symbol: 股票代码（如 '000001.SZ', '600519.SH', 'AAPL'）

        Returns:
            BrokerResult，data 为 TickerData
        """
        ...

    @abstractmethod
    def get_kline(
        self,
        symbol: str,
        interval: str = "1d",
        limit: int = 200,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> BrokerResult:
        """
        获取K线数据

        Args:
            symbol:    股票代码
            interval:  K线周期 (1m/5m/15m/30m/1h/4h/1d/1w/1M)
            limit:     数据条数
            start_date: 起始日期 (YYYY-MM-DD)
            end_date:   结束日期 (YYYY-MM-DD)

        Returns:
            BrokerResult，data 为 List[KlineData]
        """
        ...

    @abstractmethod
    def get_batch_tickers(self, symbols: List[str]) -> BrokerResult:
        """
        批量获取实时行情

        Args:
            symbols: 股票代码列表

        Returns:
            BrokerResult，data 为 List[TickerData]
        """
        ...

    # ── 账户管理 ────────────────────────────────────────

    @abstractmethod
    def get_account(self) -> BrokerResult:
        """
        获取账户信息

        Returns:
            BrokerResult，data 为 AccountInfo
        """
        ...

    @abstractmethod
    def get_positions(self) -> BrokerResult:
        """
        获取持仓列表

        Returns:
            BrokerResult，data 为 List[PositionData]
        """
        ...

    # ── 订单管理 ────────────────────────────────────────

    @abstractmethod
    def place_order(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        quantity: float,
        price: Optional[float] = None,
        stop_price: Optional[float] = None,
    ) -> BrokerResult:
        """
        下单

        Args:
            symbol:     股票代码
            side:       买卖方向
            order_type: 订单类型
            quantity:   委托数量（股）
            price:      委托价格（限价单必填）
            stop_price: 止损价（止损单必填）

        Returns:
            BrokerResult，data 为 OrderData
        """
        ...

    @abstractmethod
    def cancel_order(self, order_id: str) -> BrokerResult:
        """
        撤单

        Args:
            order_id: 订单ID

        Returns:
            BrokerResult，data 为 OrderData
        """
        ...

    @abstractmethod
    def get_order(self, order_id: str) -> BrokerResult:
        """
        查询单个订单

        Args:
            order_id: 订单ID

        Returns:
            BrokerResult，data 为 OrderData
        """
        ...

    @abstractmethod
    def get_orders(
        self,
        symbol: Optional[str] = None,
        status: Optional[OrderStatus] = None,
        limit: int = 100,
    ) -> BrokerResult:
        """
        查询订单列表

        Args:
            symbol: 股票代码（可选，不传则查全部）
            status: 订单状态筛选（可选）
            limit:  最大返回数量

        Returns:
            BrokerResult，data 为 List[OrderData]
        """
        ...

    # ── 信息查询 ────────────────────────────────────────

    @abstractmethod
    def get_broker_info(self) -> Dict[str, Any]:
        """
        获取券商能力信息

        Returns:
            {
                "name": "西部宽客",
                "broker_type": "xbk",
                "supports": ["stock", "etf", "futures"],
                "market": ["SH", "SZ", "HK"],
                "commission_rate": 0.00025,
                "min_commission": 5.0,
                "trading_hours": "09:30-15:00",
                "api_version": "v2",
            }
        """
        ...

    # ── 股票池支持 ────────────────────────────────────────

    def get_stock_list(self, market: str = "A") -> BrokerResult:
        """
        获取可交易股票列表（可选实现）

        Args:
            market: 市场类型 (A=沪深A股, HK=港股, US=美股)

        Returns:
            BrokerResult，data 为 List[dict]，每项含 symbol/name/market/sector
        """
        return BrokerResult.fail("当前券商不支持获取股票列表")


# ═══════════════════════════════════════════════════════════════
# 辅助工具
# ═══════════════════════════════════════════════════════════════

def normalize_symbol(symbol: str, target_format: str = "xbk") -> str:
    """
    标准化股票代码格式

    输入格式:
      - '000001.SZ' / '600519.SH' (标准格式)
      - '000001' / '600519'     (纯数字)
      - 'sz000001' / 'sh600519' (前缀格式)

    target_format:
      - 'xbk':      '000001.SZ'
      - 'zhongtai': '000001.SZ'
      - 'tushare':  '000001.SZ'

    Returns:
        标准化后的股票代码
    """
    symbol = symbol.strip().upper()

    # 已经是标准格式
    if "." in symbol:
        return symbol

    # sz000001 / sh600519 格式
    if symbol.lower().startswith("sz"):
        return f"{symbol[2:]}.SZ"
    if symbol.lower().startswith("sh"):
        return f"{symbol[2:]}.SH"

    # 纯数字格式，根据首位判断市场
    if symbol.isdigit():
        if len(symbol) == 6:
            if symbol.startswith(("6", "9")):
                return f"{symbol}.SH"
            elif symbol.startswith(("0", "3", "2")):
                return f"{symbol}.SZ"
            else:
                return f"{symbol}.SZ"  # 默认深市

    return symbol


def get_market_from_symbol(symbol: str) -> str:
    """从股票代码获取市场类型"""
    symbol = normalize_symbol(symbol)
    if symbol.endswith(".SH"):
        return "SH"
    elif symbol.endswith(".SZ"):
        return "SZ"
    elif symbol.endswith(".HK"):
        return "HK"
    else:
        return "UNKNOWN"