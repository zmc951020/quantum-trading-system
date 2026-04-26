#!/usr/bin/env python3
"""
西部宽客平台模拟对接模块
提供与西部宽客平台相同的API接口，但使用模拟数据
"""
import time
import random
import logging
from typing import Dict, Any, Optional
from datetime import datetime
from enum import Enum

from simulated_market import SimulatedMarket

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class OrderType(Enum):
    """订单类型"""
    MARKET = "market"  # 市价单
    LIMIT = "limit"    # 限价单
    STOP = "stop"      # 止损单

class OrderSide(Enum):
    """订单方向"""
    BUY = "buy"
    SELL = "sell"

class OrderStatus(Enum):
    """订单状态"""
    PENDING = "pending"      # 待成交
    PARTIAL = "partial"      # 部分成交
    FILLED = "filled"        # 完全成交
    CANCELLED = "cancelled"  # 已取消
    REJECTED = "rejected"    # 已拒绝

class XbkSimulatedTrader:
    """
    西部宽客模拟交易客户端
    使用模拟市场数据，提供与真实API相同的接口
    """
    
    def __init__(self, initial_balance: float = 100000.0):
        """
        初始化模拟交易客户端
        
        Args:
            initial_balance: 初始资金
        """
        self.connected = True
        self.token = "simulated_token_" + str(int(time.time()))
        
        # 账户信息
        self.balance = initial_balance
        self.available = initial_balance
        self.positions = {}  # 持仓: {symbol: quantity}
        self.orders = {}    # 订单: {order_id: order_data}
        
        # 市场
        self.market = SimulatedMarket(base_price=100.0)
        
        # 订单计数器
        self.order_counter = 1
        
        logger.info(f"西部宽客模拟交易客户端初始化完成，初始资金: {initial_balance}")
    
    def login(self, username: str, password: str) -> Dict[str, Any]:
        """
        模拟登录
        
        Args:
            username: 用户名
            password: 密码
            
        Returns:
            登录结果
        """
        logger.info(f"模拟登录: {username}")
        self.connected = True
        
        return {
            "code": 0,
            "message": "login_success",
            "data": {
                "token": self.token,
                "user_id": "simulated_user_123"
            }
        }
    
    def logout(self) -> Dict[str, Any]:
        """
        模拟登出
        
        Returns:
            登出结果
        """
        logger.info("模拟登出")
        self.connected = False
        
        return {
            "code": 0,
            "message": "logout_success"
        }
    
    def get_account_info(self) -> Dict[str, Any]:
        """
        获取模拟账户信息
        
        Returns:
            账户信息
        """
        if not self.connected:
            return {"code": -1, "message": "not_connected"}
        
        # 计算持仓市值
        position_value = 0.0
        for symbol, quantity in self.positions.items():
            ticker = self.get_ticker(symbol)
            if ticker.get("code") == 0:
                position_value += quantity * ticker["data"]["last_price"]
        
        return {
            "code": 0,
            "message": "success",
            "data": {
                "balance": self.balance,
                "available": self.available,
                "frozen": self.balance - self.available,
                "position_value": position_value,
                "total_value": self.available + position_value,
                "timestamp": int(time.time() * 1000)
            }
        }
    
    def get_positions(self) -> Dict[str, Any]:
        """
        获取模拟持仓
        
        Returns:
            持仓列表
        """
        if not self.connected:
            return {"code": -1, "message": "not_connected"}
        
        position_list = []
        for symbol, quantity in self.positions.items():
            ticker = self.get_ticker(symbol)
            if ticker.get("code") == 0:
                current_price = ticker["data"]["last_price"]
                position_list.append({
                    "symbol": symbol,
                    "quantity": quantity,
                    "average_price": current_price * 0.99,  # 模拟成本价
                    "current_price": current_price,
                    "value": quantity * current_price,
                    "unrealized_pnl": quantity * current_price * 0.005,
                    "timestamp": int(time.time() * 1000)
                })
        
        return {
            "code": 0,
            "message": "success",
            "data": position_list
        }
    
    def place_order(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        quantity: float,
        price: Optional[float] = None,
        stop_price: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        模拟下单
        
        Args:
            symbol: 交易对
            side: 买卖方向
            order_type: 订单类型
            quantity: 数量
            price: 价格（限价单）
            stop_price: 止损价格
            
        Returns:
            下单结果
        """
        if not self.connected:
            return {"code": -1, "message": "not_connected"}
        
        # 获取当前价格
        ticker = self.get_ticker(symbol)
        if ticker.get("code") != 0:
            return ticker
        
        current_price = ticker["data"]["last_price"]
        
        # 计算实际成交价格
        if order_type == OrderType.MARKET:
            execute_price = current_price
        else:
            execute_price = price if price is not None else current_price
        
        # 计算订单金额
        order_amount = quantity * execute_price
        
        # 检查资金是否足够
        if side == OrderSide.BUY and self.available < order_amount:
            return {
                "code": -2,
                "message": "insufficient_balance",
                "data": None
            }
        
        # 生成订单ID
        order_id = f"sim_order_{self.order_counter}"
        self.order_counter += 1
        
        # 模拟成交（95%成功率）
        success = random.random() < 0.95
        
        if success:
            # 更新账户
            if side == OrderSide.BUY:
                self.available -= order_amount
                if symbol not in self.positions:
                    self.positions[symbol] = 0.0
                self.positions[symbol] += quantity
            else:  # SELL
                if symbol not in self.positions or self.positions[symbol] < quantity:
                    return {
                        "code": -3,
                        "message": "insufficient_position",
                        "data": None
                    }
                
                self.available += order_amount
                self.positions[symbol] -= quantity
                if self.positions[symbol] <= 0.0001:
                    del self.positions[symbol]
            
            status = OrderStatus.FILLED
            logger.info(f"订单成交: {symbol} {side.value} {quantity} @ {execute_price:.4f}")
        else:
            status = OrderStatus.REJECTED
            logger.warning(f"订单被拒绝: {symbol} {side.value} {quantity}")
        
        # 创建订单记录
        order = {
            "order_id": order_id,
            "symbol": symbol,
            "side": side.value,
            "type": order_type.value,
            "quantity": quantity,
            "price": execute_price,
            "status": status.value,
            "timestamp": int(time.time() * 1000)
        }
        self.orders[order_id] = order
        
        return {
            "code": 0 if success else -4,
            "message": "order_placed" if success else "order_rejected",
            "data": order
        }
    
    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """
        模拟取消订单
        
        Args:
            order_id: 订单ID
            
        Returns:
            取消结果
        """
        if not self.connected:
            return {"code": -1, "message": "not_connected"}
        
        if order_id not in self.orders:
            return {"code": -5, "message": "order_not_found"}
        
        order = self.orders[order_id]
        if order["status"] in [OrderStatus.FILLED.value, OrderStatus.CANCELLED.value]:
            return {"code": -6, "message": "order_cannot_cancel"}
        
        order["status"] = OrderStatus.CANCELLED.value
        logger.info(f"订单取消: {order_id}")
        
        return {
            "code": 0,
            "message": "order_cancelled",
            "data": order
        }
    
    def get_order_info(self, order_id: str) -> Dict[str, Any]:
        """
        获取订单信息
        
        Args:
            order_id: 订单ID
            
        Returns:
            订单信息
        """
        if not self.connected:
            return {"code": -1, "message": "not_connected"}
        
        if order_id not in self.orders:
            return {"code": -5, "message": "order_not_found"}
        
        return {
            "code": 0,
            "message": "success",
            "data": self.orders[order_id]
        }
    
    def get_ticker(self, symbol: str) -> Dict[str, Any]:
        """
        获取模拟行情数据
        
        Args:
            symbol: 交易对
            
        Returns:
            行情数据
        """
        # 更新市场价格
        self.market.generate_price()
        
        # 获取行情
        ticker = self.market.get_ticker()
        ticker["data"]["symbol"] = symbol
        
        return ticker
    
    def get_kline(self, symbol: str, interval: str = "1h", limit: int = 100) -> Dict[str, Any]:
        """
        获取模拟K线数据
        
        Args:
            symbol: 交易对
            interval: K线周期
            limit: 数据条数
            
        Returns:
            K线数据
        """
        return self.market.get_kline(interval, limit)
    
    def advance_time(self, steps: int = 1):
        """
        推进模拟时间
        
        Args:
            steps: 时间步长
        """
        for _ in range(steps):
            self.market.generate_price()
        logger.debug(f"模拟时间推进 {steps} 步")


if __name__ == "__main__":
    # 测试模拟交易客户端
    print("=" * 60)
    print("西部宽客模拟交易客户端测试")
    print("=" * 60)
    
    # 创建客户端
    trader = XbkSimulatedTrader(initial_balance=100000.0)
    
    # 登录
    print("\n1. 登录...")
    login_result = trader.login("test_user", "test_password")
    print(f"   结果: {login_result['message']}")
    
    # 获取账户信息
    print("\n2. 获取账户信息...")
    account = trader.get_account_info()
    if account.get("code") == 0:
        data = account["data"]
        print(f"   余额: {data['balance']:.2f}")
        print(f"   可用: {data['available']:.2f}")
    
    # 获取行情
    print("\n3. 获取行情...")
    ticker = trader.get_ticker("BTCUSDT")
    if ticker.get("code") == 0:
        print(f"   BTC价格: {ticker['data']['last_price']:.4f}")
    
    # 下单买入
    print("\n4. 下单买入...")
    buy_result = trader.place_order(
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=0.1
    )
    print(f"   结果: {buy_result['message']}")
    
    # 检查持仓
    print("\n5. 查询持仓...")
    positions = trader.get_positions()
    if positions.get("code") == 0:
        print(f"   持仓数量: {len(positions['data'])}")
        for pos in positions['data']:
            print(f"     {pos['symbol']}: {pos['quantity']:.2f} @ {pos['current_price']:.2f}")
    
    # 下单卖出
    print("\n6. 下单卖出...")
    sell_result = trader.place_order(
        symbol="BTCUSDT",
        side=OrderSide.SELL,
        order_type=OrderType.MARKET,
        quantity=0.05
    )
    print(f"   结果: {sell_result['message']}")
    
    # 再次检查账户
    print("\n7. 再次检查账户...")
    account = trader.get_account_info()
    if account.get("code") == 0:
        data = account["data"]
        print(f"   总资产: {data['total_value']:.2f}")
    
    print("\n测试完成！")
