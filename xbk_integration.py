#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
西部宽客系统集成模块
实现实盘数据技术分析和模型策略使用
"""

import os
import json
import logging
import requests
from datetime import datetime
from typing import Dict, List, Optional, Any
from enum import Enum

# 配置日志
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('XBKIntegration')

class XbkSystemState(Enum):
    """西部宽客系统状态"""
    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    ERROR = "ERROR"

class XbkIntegration:
    """西部宽客系统集成类"""
    
    def __init__(self):
        self.api_url = "http://localhost:8000"
        self.state = XbkSystemState.DISCONNECTED
        self.account_info = None
        self.positions = []
        self.market_data = {}
        self.strategies = []
    
    def connect(self) -> bool:
        """
        连接到西部宽客系统
        
        Returns:
            bool: 连接是否成功
        """
        try:
            logger.info("正在连接西部宽客系统...")
            self.state = XbkSystemState.CONNECTING
            
            # 测试连接
            response = requests.get(f"{self.api_url}/health", timeout=5)
            if response.status_code == 200:
                self.state = XbkSystemState.CONNECTED
                logger.info("西部宽客系统连接成功")
                return True
            else:
                self.state = XbkSystemState.ERROR
                logger.error(f"连接失败: {response.status_code}")
                return False
        except Exception as e:
            self.state = XbkSystemState.ERROR
            logger.error(f"连接异常: {str(e)}")
            return False
    
    def get_account_info(self) -> Optional[Dict]:
        """
        获取账户信息
        
        Returns:
            Dict: 账户信息
        """
        if self.state != XbkSystemState.CONNECTED:
            return None
        
        try:
            response = requests.get(f"{self.api_url}/xbk/account", timeout=10)
            if response.status_code == 200:
                self.account_info = response.json()
                return self.account_info
            return None
        except Exception as e:
            logger.error(f"获取账户信息失败: {str(e)}")
            return None
    
    def get_positions(self) -> List[Dict]:
        """
        获取持仓信息
        
        Returns:
            List[Dict]: 持仓列表
        """
        if self.state != XbkSystemState.CONNECTED:
            return []
        
        try:
            response = requests.get(f"{self.api_url}/xbk/positions", timeout=10)
            if response.status_code == 200:
                self.positions = response.json().get('data', [])
                return self.positions
            return []
        except Exception as e:
            logger.error(f"获取持仓信息失败: {str(e)}")
            return []
    
    def get_market_data(self, symbol: str) -> Optional[Dict]:
        """
        获取行情数据
        
        Args:
            symbol: 交易对符号
            
        Returns:
            Dict: 行情数据
        """
        if self.state != XbkSystemState.CONNECTED:
            return None
        
        try:
            response = requests.get(f"{self.api_url}/xbk/market", 
                                  params={"symbol": symbol}, 
                                  timeout=10)
            if response.status_code == 200:
                data = response.json()
                self.market_data[symbol] = data
                return data
            return None
        except Exception as e:
            logger.error(f"获取行情数据失败: {str(e)}")
            return None
    
    def get_kline_data(self, symbol: str, interval: str = "1h", limit: int = 100) -> Optional[List]:
        """
        获取K线数据
        
        Args:
            symbol: 交易对符号
            interval: K线周期
            limit: 数据条数
            
        Returns:
            List: K线数据
        """
        if self.state != XbkSystemState.CONNECTED:
            return None
        
        try:
            response = requests.get(f"{self.api_url}/xbk/kline", 
                                  params={"symbol": symbol, "interval": interval, "limit": limit}, 
                                  timeout=10)
            if response.status_code == 200:
                return response.json().get('data', [])
            return None
        except Exception as e:
            logger.error(f"获取K线数据失败: {str(e)}")
            return None
    
    def place_order(self, symbol: str, side: str, order_type: str, quantity: float, price: Optional[float] = None) -> Optional[Dict]:
        """
        下单
        
        Args:
            symbol: 交易对符号
            side: 订单方向 (buy/sell)
            order_type: 订单类型 (market/limit)
            quantity: 数量
            price: 价格（限价单必填）
            
        Returns:
            Dict: 下单结果
        """
        if self.state != XbkSystemState.CONNECTED:
            return None
        
        try:
            data = {
                "symbol": symbol,
                "side": side,
                "type": order_type,
                "quantity": quantity
            }
            if price:
                data["price"] = price
            
            response = requests.post(f"{self.api_url}/xbk/order", 
                                   json=data, 
                                   timeout=10)
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            logger.error(f"下单失败: {str(e)}")
            return None
    
    def cancel_order(self, order_id: str) -> Optional[Dict]:
        """
        取消订单
        
        Args:
            order_id: 订单ID
            
        Returns:
            Dict: 取消结果
        """
        if self.state != XbkSystemState.CONNECTED:
            return None
        
        try:
            response = requests.post(f"{self.api_url}/xbk/cancel", 
                                   json={"order_id": order_id}, 
                                   timeout=10)
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            logger.error(f"取消订单失败: {str(e)}")
            return None
    
    def get_strategies(self) -> List[Dict]:
        """
        获取可用策略
        
        Returns:
            List[Dict]: 策略列表
        """
        if self.state != XbkSystemState.CONNECTED:
            return []
        
        try:
            response = requests.get(f"{self.api_url}/xbk/strategies", timeout=10)
            if response.status_code == 200:
                self.strategies = response.json().get('data', [])
                return self.strategies
            return []
        except Exception as e:
            logger.error(f"获取策略列表失败: {str(e)}")
            return []
    
    def get_state(self) -> XbkSystemState:
        """
        获取系统状态
        
        Returns:
            XbkSystemState: 系统状态
        """
        return self.state
    
    def disconnect(self):
        """
        断开连接
        """
        self.state = XbkSystemState.DISCONNECTED
        self.account_info = None
        self.positions = []
        self.market_data = {}
        self.strategies = []
        logger.info("已断开西部宽客系统连接")

class XbkTechnicalAnalyzer:
    """技术分析模块"""
    
    def __init__(self, xbk_integration: XbkIntegration):
        self.xbk = xbk_integration
    
    def calculate_ma(self, data: List, period: int) -> List:
        """
        计算移动平均线
        
        Args:
            data: K线数据
            period: 周期
            
        Returns:
            List: 移动平均线数据
        """
        if len(data) < period:
            return []
        
        ma = []
        for i in range(period-1, len(data)):
            sum_close = sum(item[4] for item in data[i-period+1:i+1])
            ma_value = sum_close / period
            ma.append(ma_value)
        return ma
    
    def calculate_macd(self, data: List, fast_period: int = 12, slow_period: int = 26, signal_period: int = 9) -> Dict:
        """
        计算MACD
        
        Args:
            data: K线数据
            fast_period: 快速周期
            slow_period: 慢速周期
            signal_period: 信号周期
            
        Returns:
            Dict: MACD数据
        """
        if len(data) < slow_period:
            return {"macd": [], "signal": [], "histogram": []}
        
        # 计算EMA
        def ema(values, period):
            ema_values = []
            multiplier = 2 / (period + 1)
            ema_values.append(values[0])
            for i in range(1, len(values)):
                current_ema = values[i] * multiplier + ema_values[-1] * (1 - multiplier)
                ema_values.append(current_ema)
            return ema_values
        
        closes = [item[4] for item in data]
        ema_fast = ema(closes, fast_period)
        ema_slow = ema(closes, slow_period)
        
        macd = [fast - slow for fast, slow in zip(ema_fast, ema_slow)]
        signal = ema(macd, signal_period)
        histogram = [m - s for m, s in zip(macd, signal)]
        
        return {
            "macd": macd,
            "signal": signal,
            "histogram": histogram
        }
    
    def calculate_rsi(self, data: List, period: int = 14) -> List:
        """
        计算RSI
        
        Args:
            data: K线数据
            period: 周期
            
        Returns:
            List: RSI数据
        """
        if len(data) < period + 1:
            return []
        
        changes = []
        for i in range(1, len(data)):
            change = data[i][4] - data[i-1][4]
            changes.append(change)
        
        rsi = []
        gain = []
        loss = []
        
        for i in range(period):
            if changes[i] > 0:
                gain.append(changes[i])
                loss.append(0)
            else:
                gain.append(0)
                loss.append(abs(changes[i]))
        
        avg_gain = sum(gain) / period
        avg_loss = sum(loss) / period
        
        if avg_loss == 0:
            rsi_value = 100
        else:
            rs = avg_gain / avg_loss
            rsi_value = 100 - (100 / (1 + rs))
        rsi.append(rsi_value)
        
        for i in range(period, len(changes)):
            current_change = changes[i]
            if current_change > 0:
                current_gain = current_change
                current_loss = 0
            else:
                current_gain = 0
                current_loss = abs(current_change)
            
            avg_gain = (avg_gain * (period - 1) + current_gain) / period
            avg_loss = (avg_loss * (period - 1) + current_loss) / period
            
            if avg_loss == 0:
                rsi_value = 100
            else:
                rs = avg_gain / avg_loss
                rsi_value = 100 - (100 / (1 + rs))
            rsi.append(rsi_value)
        
        return rsi
    
    def analyze_symbol(self, symbol: str, interval: str = "1h") -> Dict:
        """
        分析单个交易对
        
        Args:
            symbol: 交易对符号
            interval: K线周期
            
        Returns:
            Dict: 分析结果
        """
        kline_data = self.xbk.get_kline_data(symbol, interval, 100)
        if not kline_data:
            return {"error": "获取数据失败"}
        
        # 计算技术指标
        ma5 = self.calculate_ma(kline_data, 5)
        ma10 = self.calculate_ma(kline_data, 10)
        ma20 = self.calculate_ma(kline_data, 20)
        macd = self.calculate_macd(kline_data)
        rsi = self.calculate_rsi(kline_data)
        
        # 生成交易信号
        signals = self.generate_signals(kline_data, ma5, ma10, ma20, macd, rsi)
        
        return {
            "symbol": symbol,
            "interval": interval,
            "ma": {
                "ma5": ma5,
                "ma10": ma10,
                "ma20": ma20
            },
            "macd": macd,
            "rsi": rsi,
            "signals": signals,
            "timestamp": datetime.now().isoformat()
        }
    
    def generate_signals(self, kline_data: List, ma5: List, ma10: List, ma20: List, macd: Dict, rsi: List) -> List:
        """
        生成交易信号
        
        Args:
            kline_data: K线数据
            ma5: 5日均线
            ma10: 10日均线
            ma20: 20日均线
            macd: MACD数据
            rsi: RSI数据
            
        Returns:
            List: 交易信号
        """
        signals = []
        
        # 金叉死叉信号
        if len(ma5) >= 2 and len(ma10) >= 2:
            if ma5[-1] > ma10[-1] and ma5[-2] <= ma10[-2]:
                signals.append({"type": "BUY", "reason": "MA5金叉MA10"})
            elif ma5[-1] < ma10[-1] and ma5[-2] >= ma10[-2]:
                signals.append({"type": "SELL", "reason": "MA5死叉MA10"})
        
        # MACD信号
        if len(macd["histogram"]) >= 2:
            if macd["histogram"][-1] > 0 and macd["histogram"][-2] <= 0:
                signals.append({"type": "BUY", "reason": "MACD金叉"})
            elif macd["histogram"][-1] < 0 and macd["histogram"][-2] >= 0:
                signals.append({"type": "SELL", "reason": "MACD死叉"})
        
        # RSI信号
        if rsi:
            if rsi[-1] < 30:
                signals.append({"type": "BUY", "reason": "RSI超卖"})
            elif rsi[-1] > 70:
                signals.append({"type": "SELL", "reason": "RSI超买"})
        
        return signals

# 全局实例
_xbk_integration = None
_technical_analyzer = None

def get_xbk_integration() -> XbkIntegration:
    """
    获取西部宽客集成实例
    
    Returns:
        XbkIntegration: 集成实例
    """
    global _xbk_integration
    if _xbk_integration is None:
        _xbk_integration = XbkIntegration()
    return _xbk_integration

def get_technical_analyzer() -> XbkTechnicalAnalyzer:
    """
    获取技术分析实例
    
    Returns:
        XbkTechnicalAnalyzer: 技术分析实例
    """
    global _technical_analyzer
    if _technical_analyzer is None:
        _technical_analyzer = XbkTechnicalAnalyzer(get_xbk_integration())
    return _technical_analyzer

if __name__ == "__main__":
    # 测试代码
    xbk = get_xbk_integration()
    analyzer = get_technical_analyzer()
    
    if xbk.connect():
        print("连接成功")
        
        # 获取账户信息
        account = xbk.get_account_info()
        print(f"账户信息: {account}")
        
        # 获取持仓
        positions = xbk.get_positions()
        print(f"持仓数量: {len(positions)}")
        
        # 分析BTCUSDT
        analysis = analyzer.analyze_symbol("BTCUSDT")
        print(f"分析结果: {analysis}")
        
        xbk.disconnect()
    else:
        print("连接失败")
