"""
西部宽客交易平台API接口模块
西部宽客量化交易平台对接

使用方法：
1. 安装依赖：pip install requests websocket-client pandas numpy
2. 配置账号：在使用时请输入账号密码（不要硬编码）
3. 自定义接口：根据西部宽客实际API文档实现具体方法

API文档请参考：https://api.xbk.com/docs
"""

import os
import json
import time
import hashlib
import hmac
import base64
import logging
import requests
from typing import Dict, Any, Optional, List
from datetime import datetime
from enum import Enum

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

class XbkAPIConfig:
    """西部宽客API配置"""
    def __init__(self):
        self.api_key = os.getenv("XBK_API_KEY", "")
        self.api_secret = os.getenv("XBK_API_SECRET", "")
        self.api_url = os.getenv("XBK_API_URL", "https://api.xbk.com")
        self.ws_url = os.getenv("XBK_WS_URL", "wss://ws.xbk.com")
        self.timeout = 30
        self.retry_count = 3

class XbkTrader:
    """西部宽客交易客户端"""

    def __init__(self, config: Optional[XbkAPIConfig] = None):
        """
        初始化交易客户端

        Args:
            config: API配置，如果为None则从环境变量加载
        """
        self.config = config or XbkAPIConfig()
        self.session = None
        self.token = None
        self.connected = False

    def login(self, username: str, password: str) -> Dict[str, Any]:
        """
        用户登录

        Args:
            username: 用户名
            password: 密码

        Returns:
            登录结果字典
        """
        try:
            logger.info(f"正在登录西部宽客平台，用户名：{username}")

            # 实现真实登录逻辑
            url = f"{self.config.api_url}/v1/auth/login"
            data = {
                "username": username,
                "password": self._encrypt_password(password)
            }
            response = self._request("POST", url, data)
            
            if response.get("code") == 0:
                self.token = response["data"]["token"]
                self.connected = True
                logger.info("登录成功")
                return response
            else:
                logger.error(f"登录失败：{response.get('message', '未知错误')}")
                return response

        except Exception as e:
            logger.error(f"登录失败：{str(e)}")
            return {
                "code": -1,
                "message": f"登录失败：{str(e)}",
                "data": None
            }

    def logout(self) -> Dict[str, Any]:
        """
        用户登出

        Returns:
            登出结果字典
        """
        try:
            logger.info("正在登出")
            self.token = None
            self.connected = False
            return {
                "code": 0,
                "message": "登出成功"
            }
        except Exception as e:
            logger.error(f"登出失败：{str(e)}")
            return {
                "code": -1,
                "message": f"登出失败：{str(e)}"
            }

    def get_account_info(self) -> Dict[str, Any]:
        """
        获取账户信息

        Returns:
            账户信息字典
        """
        if not self.connected:
            return {"code": -1, "message": "未登录"}

        try:
            logger.info("获取账户信息")
            url = f"{self.config.api_url}/v1/account/info"
            response = self._request("GET", url)
            
            if response.get("code") == 0:
                logger.info("获取账户信息成功")
                return response
            else:
                logger.error(f"获取账户信息失败：{response.get('message', '未知错误')}")
                return response
        except Exception as e:
            logger.error(f"获取账户信息失败：{str(e)}")
            return {"code": -1, "message": str(e)}

    def get_positions(self) -> Dict[str, Any]:
        """
        获取持仓信息

        Returns:
            持仓信息列表
        """
        if not self.connected:
            return {"code": -1, "message": "未登录"}

        try:
            logger.info("获取持仓信息")
            url = f"{self.config.api_url}/v1/account/positions"
            response = self._request("GET", url)
            
            if response.get("code") == 0:
                logger.info("获取持仓信息成功")
                return response
            else:
                logger.error(f"获取持仓信息失败：{response.get('message', '未知错误')}")
                return response
        except Exception as e:
            logger.error(f"获取持仓信息失败：{str(e)}")
            return {"code": -1, "message": str(e)}

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
        下单

        Args:
            symbol: 交易对符号，如 "BTCUSDT"
            side: 订单方向（买入/卖出）
            order_type: 订单类型（市价/限价/止损）
            quantity: 数量
            price: 价格（限价单必填）
            stop_price: 止损价格（止损单必填）

        Returns:
            下单结果字典
        """
        if not self.connected:
            return {"code": -1, "message": "未登录"}

        try:
            logger.info(f"下单：{symbol} {side.value} {order_type.value} {quantity}@{price or '市价'}")

            url = f"{self.config.api_url}/v1/order/place"
            data = {
                "symbol": symbol,
                "side": side.value,
                "type": order_type.value,
                "quantity": quantity
            }
            
            if price:
                data["price"] = price
            if stop_price:
                data["stop_price"] = stop_price
            
            response = self._request("POST", url, data)
            
            if response.get("code") == 0:
                logger.info("下单成功")
                return response
            else:
                logger.error(f"下单失败：{response.get('message', '未知错误')}")
                return response

        except Exception as e:
            logger.error(f"下单失败：{str(e)}")
            return {"code": -1, "message": f"下单失败：{str(e)}"}

    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """
        取消订单

        Args:
            order_id: 订单ID

        Returns:
            取消结果字典
        """
        if not self.connected:
            return {"code": -1, "message": "未登录"}

        try:
            logger.info(f"取消订单：{order_id}")

            url = f"{self.config.api_url}/v1/order/cancel"
            data = {
                "order_id": order_id
            }
            response = self._request("POST", url, data)
            
            if response.get("code") == 0:
                logger.info("取消订单成功")
                return response
            else:
                logger.error(f"取消订单失败：{response.get('message', '未知错误')}")
                return response

        except Exception as e:
            logger.error(f"取消订单失败：{str(e)}")
            return {"code": -1, "message": f"取消订单失败：{str(e)}"}

    def get_order_info(self, order_id: str) -> Dict[str, Any]:
        """
        查询订单信息

        Args:
            order_id: 订单ID

        Returns:
            订单信息字典
        """
        if not self.connected:
            return {"code": -1, "message": "未登录"}

        try:
            logger.info(f"查询订单：{order_id}")

            url = f"{self.config.api_url}/v1/order/info"
            data = {
                "order_id": order_id
            }
            response = self._request("GET", url, data)
            
            if response.get("code") == 0:
                logger.info("查询订单成功")
                return response
            else:
                logger.error(f"查询订单失败：{response.get('message', '未知错误')}")
                return response

        except Exception as e:
            logger.error(f"查询订单失败：{str(e)}")
            return {"code": -1, "message": str(e)}

    def get_ticker(self, symbol: str) -> Dict[str, Any]:
        """
        获取行情数据

        Args:
            symbol: 交易对符号

        Returns:
            行情数据字典
        """
        try:
            logger.info(f"获取行情：{symbol}")

            url = f"{self.config.api_url}/v1/market/ticker"
            data = {
                "symbol": symbol
            }
            response = self._request("GET", url, data)
            
            if response.get("code") == 0:
                logger.info("获取行情成功")
                return response
            else:
                logger.error(f"获取行情失败：{response.get('message', '未知错误')}")
                return response

        except Exception as e:
            logger.error(f"获取行情失败：{str(e)}")
            return {"code": -1, "message": str(e)}

    def get_kline(self, symbol: str, interval: str = "1h", limit: int = 100) -> Dict[str, Any]:
        """
        获取K线数据

        Args:
            symbol: 交易对符号
            interval: K线周期（1m, 5m, 15m, 1h, 4h, 1d）
            limit: 数据条数

        Returns:
            K线数据列表
        """
        try:
            logger.info(f"获取K线：{symbol} {interval} {limit}")

            url = f"{self.config.api_url}/v1/market/kline"
            data = {
                "symbol": symbol,
                "interval": interval,
                "limit": limit
            }
            response = self._request("GET", url, data)
            
            if response.get("code") == 0:
                logger.info("获取K线成功")
                return response
            else:
                logger.error(f"获取K线失败：{response.get('message', '未知错误')}")
                return response

        except Exception as e:
            logger.error(f"获取K线失败：{str(e)}")
            return {"code": -1, "message": str(e)}

    def _encrypt_password(self, password: str) -> str:
        """密码加密（根据实际API要求实现）"""
        # 使用SHA256加密密码，根据西部宽客API要求
        return hashlib.sha256(password.encode()).hexdigest()

    def _request(self, method: str, url: str, data: Dict = None) -> Dict:
        """
        发送HTTP请求

        Args:
            method: 请求方法（GET/POST/PUT/DELETE）
            url: 请求URL
            data: 请求数据

        Returns:
            响应数据字典
        """
        try:
            headers = {}
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"
            headers["Content-Type"] = "application/json"
            headers["X-Request-Time"] = str(int(time.time() * 1000))
            
            if method == "GET":
                response = requests.get(url, headers=headers, params=data, timeout=self.config.timeout)
            elif method == "POST":
                response = requests.post(url, json=data, headers=headers, timeout=self.config.timeout)
            elif method == "PUT":
                response = requests.put(url, json=data, headers=headers, timeout=self.config.timeout)
            elif method == "DELETE":
                response = requests.delete(url, headers=headers, timeout=self.config.timeout)
            else:
                raise ValueError(f"不支持的请求方法: {method}")
            
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"HTTP请求失败: {str(e)}")
            return {"code": -1, "message": f"请求失败: {str(e)}"}
        except Exception as e:
            logger.error(f"请求处理失败: {str(e)}")
            return {"code": -1, "message": f"处理失败: {str(e)}"}

class XbkTraderFactory:
    """交易客户端工厂"""

    @staticmethod
    def create_trader(config: Optional[XbkAPIConfig] = None) -> XbkTrader:
        """创建交易客户端"""
        return XbkTrader(config)

# 全局单例
_trader_instance = None

def get_trader() -> XbkTrader:
    """获取全局交易客户端实例"""
    global _trader_instance
    if _trader_instance is None:
        _trader_instance = XbkTrader()
    return _trader_instance

if __name__ == "__main__":
    # 测试代码
    trader = XbkTrader()

    # 登录（使用时请替换为实际账号密码）
    # login_result = trader.login("your_username", "your_password")
    # print(login_result)

    # 获取账户信息
    account_info = trader.get_account_info()
    print(f"账户信息：{account_info}")

    # 获取持仓
    positions = trader.get_positions()
    print(f"持仓信息：{positions}")

    # 获取行情
    ticker = trader.get_ticker("BTCUSDT")
    print(f"行情数据：{ticker}")
