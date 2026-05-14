# =========================================
# Aurora OMS - 顶级金融级订单管理系统
# =========================================

from enum import Enum
from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field
from uuid import uuid4


class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"
    TWAP = "twap"
    VWAP = "vwap"
    ICEBERG = "iceberg"


class OrderStatus(Enum):
    PENDING = "pending"
    NEW = "new"
    PARTIAL = "partial"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"


class Order(BaseModel):
    """顶级金融级订单模型"""
    order_id: str = Field(default_factory=lambda: str(uuid4()))
    account_id: str
    strategy_id: Optional[str] = None
    symbol: str
    exchange: Optional[str] = None
    side: OrderSide
    order_type: OrderType
    quantity: float
    price: Optional[float] = None
    stop_price: Optional[float] = None
    status: OrderStatus = OrderStatus.PENDING
    filled_quantity: float = 0.0
    avg_price: Optional[float] = None
    fees: float = 0.0
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    filled_at: Optional[datetime] = None
    exchange_order_id: Optional[str] = None
    notes: Optional[str] = None
    
    class Config:
        use_enum_values = True


class Fill(BaseModel):
    """顶级金融级成交记录模型"""
    fill_id: str = Field(default_factory=lambda: str(uuid4()))
    order_id: str
    symbol: str
    side: OrderSide
    quantity: float
    price: float
    fees: float
    exchange_fill_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    
    class Config:
        use_enum_values = True


class OrderManager:
    """顶级订单管理器 - 金融级标准"""
    
    def __init__(self):
        self.orders: Dict[str, Order] = {}
        self.fills: Dict[str, Fill] = {}
        self.fills_by_order: Dict[str, List[Fill]] = {}
    
    def create_order(self, order: Order) -> Order:
        """创建订单"""
        self.orders[order.order_id] = order
        if order.order_id not in self.fills_by_order:
            self.fills_by_order[order.order_id] = []
        return order
    
    def get_order(self, order_id: str) -> Optional[Order]:
        """获取订单"""
        return self.orders.get(order_id)
    
    def cancel_order(self, order_id: str) -> bool:
        """取消订单"""
        order = self.orders.get(order_id)
        if order and order.status not in [OrderStatus.FILLED, OrderStatus.CANCELLED]:
            order.status = OrderStatus.CANCELLED
            order.updated_at = datetime.now()
            return True
        return False
    
    def add_fill(self, fill: Fill) -> Fill:
        """添加成交记录"""
        self.fills[fill.fill_id] = fill
        self.fills_by_order[fill.order_id].append(fill)
        
        order = self.orders.get(fill.order_id)
        if order:
            self._update_order_from_fill(order, fill)
        
        return fill
    
    def _update_order_from_fill(self, order: Order, fill: Fill) -> None:
        """从成交记录更新订单状态"""
        order.filled_quantity += fill.quantity
        order.fees += fill.fees
        
        # 更新平均价格
        total_filled_prev = order.filled_quantity - fill.quantity
        if total_filled_prev == 0:
            order.avg_price = fill.price
        else:
            price_total = order.avg_price * total_filled_prev + fill.price * fill.quantity
            order.avg_price = price_total / order.filled_quantity
        
        # 更新状态
        if abs(order.filled_quantity - order.quantity) < 1e-9:
            order.status = OrderStatus.FILLED
            order.filled_at = fill.created_at
        else:
            order.status = OrderStatus.PARTIAL
        
        order.updated_at = datetime.now()
    
    def get_positions(self, account_id: str) -> Dict[str, float]:
        """获取账户持仓"""
        positions: Dict[str, float] = {}
        for fill in self.fills.values():
            order = self.orders.get(fill.order_id)
            if order and order.account_id == account_id:
                if fill.side == OrderSide.BUY:
                    positions[fill.symbol] = positions.get(fill.symbol, 0) + fill.quantity
                else:
                    positions[fill.symbol] = positions.get(fill.symbol, 0) - fill.quantity
        return positions
    
    def get_order_history(self, account_id: str, limit: int = 100) -> List[Order]:
        """获取账户订单历史"""
        return sorted(
            [o for o in self.orders.values() if o.account_id == account_id],
            key=lambda o: o.created_at,
            reverse=True
        )[:limit]
