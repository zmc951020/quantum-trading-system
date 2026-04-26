#!/usr/bin/env python3
"""
模拟市场数据生成器
生成实时市场数据用于策略测试
"""
import time
import random
import math
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Any, List, Tuple
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SimulatedMarket:
    """
    模拟市场类
    生成真实的市场数据用于策略测试
    """
    
    def __init__(self, base_price: float = 100.0, volatility: float = 0.005):
        """
        初始化模拟市场
        
        Args:
            base_price: 基准价格
            volatility: 价格波动幅度
        """
        self.base_price = base_price
        self.current_price = base_price
        self.last_price = base_price
        self.volatility = volatility
        self.price_history = [base_price]
        self.time_history = [datetime.now()]
        
        # 市场状态
        self.trend = random.choice([-1, 0, 1])  # -1=下跌, 0=横盘, 1=上涨
        self.trend_strength = 0.001
        self.mean_reversion = 0.0001
        self.jump_probability = 0.01  # 跳空概率
        
        logger.info(f"模拟市场初始化完成，基准价格: {base_price}")
    
    def generate_price(self) -> float:
        """
        生成下一个价格
        
        Returns:
            新价格
        """
        # 保存上一个价格
        self.last_price = self.current_price
        
        # 生成随机波动
        random_change = random.normalvariate(0, self.volatility)
        
        # 趋势项
        trend_change = self.trend * self.trend_strength
        
        # 均值回归项
        mean_reversion_change = self.mean_reversion * (self.base_price - self.current_price)
        
        # 跳空项
        jump_change = 0.0
        if random.random() < self.jump_probability:
            jump_change = random.choice([-1, 1]) * random.uniform(0.01, 0.05)
        
        # 计算总变化
        total_change = random_change + trend_change + mean_reversion_change + jump_change
        
        # 更新价格
        self.current_price = self.current_price * (1 + total_change)
        
        # 确保价格为正
        if self.current_price < 0.01:
            self.current_price = 0.01
        
        # 记录价格
        self.price_history.append(self.current_price)
        self.time_history.append(datetime.now())
        
        # 定期更新趋势
        if len(self.price_history) % 100 == 0:
            self._update_trend()
        
        return self.current_price
    
    def _update_trend(self):
        """
        随机更新市场趋势
        """
        # 有一定概率改变趋势
        if random.random() < 0.3:
            self.trend = random.choice([-1, 0, 1])
            self.trend_strength = random.uniform(0.0005, 0.002)
            logger.info(f"市场趋势更新: {'上涨' if self.trend > 0 else '下跌' if self.trend < 0 else '横盘'}")
    
    def get_ticker(self) -> Dict[str, Any]:
        """
        获取行情数据（模拟西部宽客API格式）
        
        Returns:
            行情数据字典
        """
        return {
            "code": 0,
            "message": "success",
            "data": {
                "symbol": "BTCUSDT",
                "last_price": self.current_price,
                "open_price": self.last_price,
                "high_price": max(self.price_history[-20:]) if len(self.price_history) >= 20 else self.current_price,
                "low_price": min(self.price_history[-20:]) if len(self.price_history) >= 20 else self.current_price,
                "volume": random.uniform(1000, 10000),
                "timestamp": int(time.time() * 1000)
            }
        }
    
    def get_kline(self, interval: str = "1m", limit: int = 100) -> Dict[str, Any]:
        """
        获取K线数据（模拟西部宽客API格式）
        
        Args:
            interval: K线周期
            limit: 数据条数
            
        Returns:
            K线数据字典
        """
        klines = []
        
        # 生成K线数据
        if len(self.price_history) < limit:
            # 如果历史数据不够，生成额外数据
            for i in range(limit - len(self.price_history) + 1):
                price = self.base_price * (1 + random.normalvariate(0, self.volatility))
                self.price_history.insert(0, price)
                self.time_history.insert(0, self.time_history[0] - timedelta(minutes=1))
        
        # 截取最近的K线
        start_idx = max(0, len(self.price_history) - limit)
        for i in range(start_idx, len(self.price_history)):
            kline = {
                "timestamp": int(self.time_history[i].timestamp() * 1000),
                "open": self.price_history[i-1] if i > 0 else self.price_history[i],
                "high": self.price_history[i],
                "low": self.price_history[i],
                "close": self.price_history[i],
                "volume": random.uniform(100, 1000)
            }
            klines.append(kline)
        
        return {
            "code": 0,
            "message": "success",
            "data": klines[-limit:]
        }
    
    def get_price_history(self) -> List[float]:
        """
        获取价格历史
        
        Returns:
            价格历史列表
        """
        return self.price_history
    
    def reset(self, base_price: float = None):
        """
        重置市场
        
        Args:
            base_price: 新的基准价格
        """
        if base_price is not None:
            self.base_price = base_price
        
        self.current_price = self.base_price
        self.last_price = self.base_price
        self.price_history = [self.base_price]
        self.time_history = [datetime.now()]
        self.trend = random.choice([-1, 0, 1])
        logger.info(f"模拟市场已重置，新基准价格: {self.base_price}")


if __name__ == "__main__":
    # 测试模拟市场
    market = SimulatedMarket(base_price=100.0)
    
    print("=" * 60)
    print("模拟市场测试")
    print("=" * 60)
    
    # 生成一些价格数据
    print("\n生成价格数据...")
    for i in range(10):
        price = market.generate_price()
        print(f"  时间 {i+1}: 价格 = {price:.4f}")
        time.sleep(0.1)
    
    # 获取行情
    print("\n获取行情数据...")
    ticker = market.get_ticker()
    print(f"  最新价格: {ticker['data']['last_price']:.4f}")
    print(f"  最高价: {ticker['data']['high_price']:.4f}")
    print(f"  最低价: {ticker['data']['low_price']:.4f}")
    
    # 获取K线
    print("\n获取K线数据...")
    klines = market.get_kline(limit=10)
    print(f"  K线数量: {len(klines['data'])}")
    if klines['data']:
        last_kline = klines['data'][-1]
        print(f"  最新K线: 开={last_kline['open']:.4f}, 收={last_kline['close']:.4f}")
    
    print("\n测试完成！")
