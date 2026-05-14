"""
OMS订单管理系统测试用例
"""
import pytest
from datetime import datetime
from oms.core import OrderManager, Order, OrderStatus


@pytest.fixture
def oms():
    """初始化OMS系统"""
    return OrderManager()


def test_create_order(oms):
    """测试创建订单"""
    order = oms.create_order(
        symbol="000001.SZ",
        side="BUY",
        quantity=100,
        price=10.5,
        broker_id="xibu"
    )
    
    assert order.order_id is not None
    assert order.status == OrderStatus.NEW
    assert order.symbol == "000001.SZ"
    assert order.side == "BUY"
    assert order.quantity == 100
    assert order.price == 10.5


def test_order_status_update(oms):
    """测试订单状态更新"""
    order = oms.create_order(
        symbol="000001.SZ",
        side="BUY",
        quantity=100,
        price=10.5,
        broker_id="xibu"
    )
    
    oms.update_order_status(order.order_id, OrderStatus.FILLED)
    updated_order = oms.get_order(order.order_id)
    
    assert updated_order.status == OrderStatus.FILLED


def test_get_active_orders(oms):
    """测试获取活跃订单"""
    oms.create_order(
        symbol="000001.SZ", side="BUY", quantity=100, price=10.5, broker_id="xibu"
    )
    oms.create_order(
        symbol="000002.SZ", side="SELL", quantity=200, price=20.5, broker_id="xibu"
    )
    
    active_orders = oms.get_active_orders()
    assert len(active_orders) == 2


def test_cancel_order(oms):
    """测试取消订单"""
    order = oms.create_order(
        symbol="000001.SZ",
        side="BUY",
        quantity=100,
        price=10.5,
        broker_id="xibu"
    )
    
    result = oms.cancel_order(order.order_id)
    assert result is True
    
    canceled_order = oms.get_order(order.order_id)
    assert canceled_order.status == OrderStatus.CANCELED