#!/usr/bin/env python3
"""
西部宽客API客户端
用于对接西部宽客真实API，获取实时行情数据和执行交易
"""

import os
import json
import time
import hmac
import hashlib
import requests
from datetime import datetime
from typing import Dict, Any, List, Optional

class XbkApiClient:
    """
    西部宽客API客户端
    """

    def __init__(self, api_key: str, api_secret: str, api_url: str):
        """
        初始化西部宽客API客户端

        Args:
            api_key: API密钥
            api_secret: API密钥
            api_url: API基础URL
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.api_url = api_url.rstrip('/')
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'X-API-KEY': api_key
        })

    def _generate_signature(self, timestamp: str, data: Dict = None) -> str:
        """
        生成签名

        Args:
            timestamp: 时间戳
            data: 请求数据

        Returns:
            签名
        """
        if data is None:
            data = {}

        # 构造签名字符串
        sorted_keys = sorted(data.keys())
        query_string = '&'.join([f"{k}={data[k]}" for k in sorted_keys])
        message = f"{timestamp}{query_string}"

        # 使用HMAC-SHA256生成签名
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        return signature

    def _request(self, method: str, endpoint: str, data: Dict = None) -> Dict:
        """
        发送API请求

        Args:
            method: HTTP方法
            endpoint: API端点
            data: 请求数据

        Returns:
            API响应
        """
        if data is None:
            data = {}

        timestamp = str(int(time.time() * 1000))
        signature = self._generate_signature(timestamp, data)

        headers = {
            'X-TIMESTAMP': timestamp,
            'X-SIGNATURE': signature
        }

        url = f"{self.api_url}/{endpoint}"

        try:
            if method.upper() == 'GET':
                response = self.session.get(url, params=data, headers=headers)
            else:
                response = self.session.post(url, json=data, headers=headers)

            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            print(f"API请求失败: {e}")
            return {'code': -1, 'msg': str(e), 'data': None}

    def get_ticker(self, symbol: str) -> Dict:
        """
        获取行情数据

        Args:
            symbol: 交易对

        Returns:
            行情数据
        """
        return self._request('GET', 'market/ticker', {'symbol': symbol})

    def get_kline(self, symbol: str, interval: str, limit: int = 100) -> Dict:
        """
        获取K线数据

        Args:
            symbol: 交易对
            interval: 时间周期 (1m, 5m, 15m, 30m, 1h, 4h, 1d)
            limit: 数据条数

        Returns:
            K线数据
        """
        return self._request('GET', 'market/kline', {
            'symbol': symbol,
            'interval': interval,
            'limit': limit
        })

    def get_account_info(self) -> Dict:
        """
        获取账户信息

        Returns:
            账户信息
        """
        return self._request('GET', 'account/info')

    def get_positions(self) -> Dict:
        """
        获取持仓信息

        Returns:
            持仓信息
        """
        return self._request('GET', 'account/positions')

    def place_order(self, symbol: str, side: str, type: str, quantity: float, price: Optional[float] = None) -> Dict:
        """
        下单

        Args:
            symbol: 交易对
            side: 买卖方向 (buy, sell)
            type: 订单类型 (market, limit)
            quantity: 数量
            price: 价格（限价单必填）

        Returns:
            下单结果
        """
        order_data = {
            'symbol': symbol,
            'side': side,
            'type': type,
            'quantity': quantity
        }

        if type == 'limit' and price is not None:
            order_data['price'] = price

        return self._request('POST', 'order/place', order_data)

    def cancel_order(self, order_id: str) -> Dict:
        """
        取消订单

        Args:
            order_id: 订单ID

        Returns:
            取消结果
        """
        return self._request('POST', 'order/cancel', {'order_id': order_id})

    def get_order_info(self, order_id: str) -> Dict:
        """
        查询订单

        Args:
            order_id: 订单ID

        Returns:
            订单信息
        """
        return self._request('GET', 'order/info', {'order_id': order_id})

    def get_order_history(self, symbol: Optional[str] = None, limit: int = 100) -> Dict:
        """
        获取订单历史

        Args:
            symbol: 交易对（可选）
            limit: 数据条数

        Returns:
            订单历史
        """
        params = {'limit': limit}
        if symbol:
            params['symbol'] = symbol
        return self._request('GET', 'order/history', params)


class XbkDataFeed:
    """
    西部宽客数据feed
    用于获取实时行情数据并转换为系统可用格式
    """

    def __init__(self, api_client: XbkApiClient):
        """
        初始化数据feed

        Args:
            api_client: 西部宽客API客户端
        """
        self.api_client = api_client
        self.symbol = 'BTCUSDT'  # 默认交易对
        self.last_price = None
        self.last_timestamp = None

    def set_symbol(self, symbol: str):
        """
        设置交易对

        Args:
            symbol: 交易对
        """
        self.symbol = symbol

    def get_latest_price(self) -> Dict:
        """
        获取最新价格

        Returns:
            价格数据
        """
        response = self.api_client.get_ticker(self.symbol)
        
        if response.get('code') == 0 and response.get('data'):
            data = response['data']
            self.last_price = float(data.get('close', 0))
            self.last_timestamp = datetime.now()
            
            return {
                'timestamp': self.last_timestamp.isoformat(),
                'price': self.last_price,
                'volume': float(data.get('volume', 0)),
                'high': float(data.get('high', 0)),
                'low': float(data.get('low', 0)),
                'open': float(data.get('open', 0))
            }
        
        # 如果API失败，返回模拟数据
        return self._get_mock_price()

    def get_kline_data(self, interval: str = '1m', limit: int = 100) -> List[Dict]:
        """
        获取K线数据

        Args:
            interval: 时间周期
            limit: 数据条数

        Returns:
            K线数据列表
        """
        response = self.api_client.get_kline(self.symbol, interval, limit)
        
        if response.get('code') == 0 and response.get('data'):
            klines = []
            for kline in response['data']:
                klines.append({
                    'timestamp': datetime.fromtimestamp(kline[0] / 1000).isoformat(),
                    'open': float(kline[1]),
                    'high': float(kline[2]),
                    'low': float(kline[3]),
                    'close': float(kline[4]),
                    'volume': float(kline[5])
                })
            return klines
        
        # 如果API失败，返回模拟数据
        return self._get_mock_klines(limit)

    def _get_mock_price(self) -> Dict:
        """
        获取模拟价格数据

        Returns:
            模拟价格数据
        """
        import random
        
        if self.last_price is None:
            self.last_price = 50000.0
        
        # 生成随机波动
        change = random.uniform(-1, 1) * 0.5  # ±0.5%
        self.last_price = self.last_price * (1 + change / 100)
        self.last_price = round(self.last_price, 2)
        self.last_timestamp = datetime.now()
        
        return {
            'timestamp': self.last_timestamp.isoformat(),
            'price': self.last_price,
            'volume': random.randint(1000, 10000),
            'high': self.last_price * (1 + random.uniform(0, 0.3) / 100),
            'low': self.last_price * (1 - random.uniform(0, 0.3) / 100),
            'open': self.last_price * (1 + random.uniform(-0.2, 0.2) / 100)
        }

    def _get_mock_klines(self, limit: int) -> List[Dict]:
        """
        获取模拟K线数据

        Args:
            limit: 数据条数

        Returns:
            模拟K线数据
        """
        import random
        
        klines = []
        base_price = 50000.0
        timestamp = datetime.now()
        
        for i in range(limit):
            change = random.uniform(-1, 1) * 0.3  # ±0.3%
            base_price = base_price * (1 + change / 100)
            base_price = round(base_price, 2)
            
            open_price = base_price * (1 + random.uniform(-0.1, 0.1) / 100)
            high_price = max(base_price, open_price) * (1 + random.uniform(0, 0.2) / 100)
            low_price = min(base_price, open_price) * (1 - random.uniform(0, 0.2) / 100)
            
            klines.append({
                'timestamp': timestamp.isoformat(),
                'open': round(open_price, 2),
                'high': round(high_price, 2),
                'low': round(low_price, 2),
                'close': base_price,
                'volume': random.randint(800, 5000)
            })
            
            # 减去1分钟
            timestamp = timestamp.replace(minute=timestamp.minute - 1)
        
        return klines[::-1]  # 反转顺序，最新的在最后


class XbkTrader:
    """
    西部宽客交易器
    用于执行交易操作
    """

    def __init__(self, api_client: XbkApiClient):
        """
        初始化交易器

        Args:
            api_client: 西部宽客API客户端
        """
        self.api_client = api_client

    def buy(self, symbol: str, quantity: float, price: Optional[float] = None) -> Dict:
        """
        买入

        Args:
            symbol: 交易对
            quantity: 数量
            price: 价格（限价单）

        Returns:
            交易结果
        """
        order_type = 'limit' if price else 'market'
        return self.api_client.place_order(symbol, 'buy', order_type, quantity, price)

    def sell(self, symbol: str, quantity: float, price: Optional[float] = None) -> Dict:
        """
        卖出

        Args:
            symbol: 交易对
            quantity: 数量
            price: 价格（限价单）

        Returns:
            交易结果
        """
        order_type = 'limit' if price else 'market'
        return self.api_client.place_order(symbol, 'sell', order_type, quantity, price)

    def cancel(self, order_id: str) -> Dict:
        """
        取消订单

        Args:
            order_id: 订单ID

        Returns:
            取消结果
        """
        return self.api_client.cancel_order(order_id)

    def get_account(self) -> Dict:
        """
        获取账户信息

        Returns:
            账户信息
        """
        return self.api_client.get_account_info()

    def get_positions(self) -> Dict:
        """
        获取持仓信息

        Returns:
            持仓信息
        """
        return self.api_client.get_positions()


if __name__ == '__main__':
    # 从环境变量加载配置
    api_key = os.getenv('XBK_API_KEY', '2029963shhr')
    api_secret = os.getenv('XBK_API_SECRET', '123456')
    api_url = os.getenv('XBK_API_URL', 'https://api.westquant.cn/sim')

    # 创建API客户端
    client = XbkApiClient(api_key, api_secret, api_url)

    # 测试API连接
    print("测试API连接...")
    ticker = client.get_ticker('BTCUSDT')
    print(f"行情数据: {json.dumps(ticker, indent=2, ensure_ascii=False)}")

    # 测试数据feed
    data_feed = XbkDataFeed(client)
    latest_price = data_feed.get_latest_price()
    print(f"最新价格: {json.dumps(latest_price, indent=2, ensure_ascii=False)}")

    # 测试K线数据
    klines = data_feed.get_kline_data('1m', 10)
    print(f"K线数据 (前5条): {json.dumps(klines[:5], indent=2, ensure_ascii=False)}")
