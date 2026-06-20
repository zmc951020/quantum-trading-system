#!/usr/bin/env python3
"""
数据源适配器基类

所有数据源适配器必须继承自此基类，实现统一接口。
"""

from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import random


class BaseDataSourceAdapter:
    """数据源适配器基类"""

    name = "base"

    def __init__(self):
        self._available = False
        self._init()

    def _init(self):
        """初始化适配器（子类重写）"""
        self._available = True

    def is_available(self) -> bool:
        """检查数据源是否可用"""
        return self._available

    # --------------------------------------------------------
    # 模拟数据生成（统一实现，子类可直接调用）
    # --------------------------------------------------------

    def _generate_mock_kline(self, symbol: str, days: int,
                             period: str = "daily") -> Dict[str, Any]:
        """生成模拟K线数据（当真实数据源不可用时降级使用）

        使用几何布朗运动模型生成价格序列，同一股票代码
        每次生成相同的模拟数据（通过固定随机种子保证一致性）。

        Args:
            symbol: 股票代码
            days: 天数
            period: 周期 ('daily'|'weekly'|'monthly'|'1min'等)

        Returns:
            标准K线格式字典
        """
        random.seed(hash(symbol) & 0xFFFFFFFF)

        n = min(days, 500)
        base_price = 10.0 + (hash(symbol) % 50) / 10.0

        dates = []
        opens = []
        highs = []
        lows = []
        closes = []
        volumes = []

        price = base_price
        end_date = datetime.now()

        for i in range(n):
            # 生成日期
            if period in ["daily", "weekly", "monthly"]:
                d = end_date - timedelta(days=n - i)
                dates.append(d.strftime("%Y-%m-%d"))
            else:
                d = end_date - timedelta(minutes=n - i)
                dates.append(d.strftime("%Y-%m-%d %H:%M:%S"))

            # 价格生成（几何布朗运动）
            change = random.uniform(-0.03, 0.03)
            open_p = price * (1 + random.uniform(-0.01, 0.01))
            close_p = price * (1 + change)
            high_p = max(open_p, close_p) * (1 + random.uniform(0, 0.01))
            low_p = min(open_p, close_p) * (1 - random.uniform(0, 0.01))
            vol = random.uniform(500000, 2000000) * (1 + abs(change) * 10)

            opens.append(round(open_p, 2))
            highs.append(round(high_p, 2))
            lows.append(round(low_p, 2))
            closes.append(round(close_p, 2))
            volumes.append(round(vol, 0))

            price = close_p

        return {
            "dates": dates,
            "opens": opens,
            "highs": highs,
            "lows": lows,
            "closes": closes,
            "volumes": volumes,
            "symbol": symbol,
            "count": n,
            "start_date": dates[0] if dates else "",
            "end_date": dates[-1] if dates else "",
            "_mock": True,
            "source": f"{self.name}-Mock",
        }

    def _generate_mock_financial(self, symbol: str) -> Dict[str, Any]:
        """生成模拟财务数据（当真实数据源不可用时降级使用）

        同一股票代码每次生成相同的模拟数据（通过固定随机种子保证一致性）。

        Args:
            symbol: 股票代码

        Returns:
            标准财务数据格式字典
        """
        random.seed(hash(symbol) & 0xFFFFFFFF)

        return {
            "symbol": symbol,
            "name": f"{symbol}(模拟)",
            "pe": round(8 + random.random() * 30, 2),
            "pb": round(0.5 + random.random() * 5, 2),
            "eps": round(random.random() * 3, 2),
            "roe": round(5 + random.random() * 20, 2),
            "revenue_growth": round(random.uniform(-10, 30), 2),
            "profit_growth": round(random.uniform(-20, 40), 2),
            "total_market_cap": round(100 + random.random() * 900, 2),
            "industry": random.choice(
                ["金融", "科技", "消费", "医药", "制造", "能源"]
            ),
            "_mock": True,
            "source": f"{self.name}-Mock",
        }

    # --------------------------------------------------------
    # 必须实现的接口
    # --------------------------------------------------------

    def get_kline(self, symbol: str, period: str = "daily", days: int = 500) -> Optional[Dict[str, Any]]:
        """获取K线数据

        返回标准K线格式字典，失败返回None
        """
        raise NotImplementedError("子类必须实现 get_kline()")

    def get_financial(self, symbol: str) -> Optional[Dict[str, Any]]:
        """获取财务数据

        返回标准财务数据格式字典，失败返回None
        """
        raise NotImplementedError("子类必须实现 get_financial()")

    # --------------------------------------------------------
    # 可选实现的接口
    # --------------------------------------------------------

    def get_realtime(self, symbol: str) -> Optional[Dict[str, Any]]:
        """获取实时行情数据"""
        return None

    def get_stock_list(self, market: str = "A股") -> List[Dict]:
        """获取股票列表"""
        return []

    def get_index_components(self, index_code: str) -> List[str]:
        """获取指数成分股代码列表"""
        return []
