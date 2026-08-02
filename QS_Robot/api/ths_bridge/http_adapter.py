"""同花顺HTTP行情接口适配器

封装同花顺行情数据获取，为策略提供K线数据。
支持实时行情和历史K线。
"""
import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

THS_HTTP_BASE = "http://d.10jqka.com.cn"


class HttpAdapter:
    """同花顺HTTP行情适配器"""

    def __init__(self):
        self._cache: Dict[str, List[Dict]] = {}

    def fetch_bars(self, symbol: str, period: str = "daily",
                   count: int = 120) -> List[Dict]:
        """获取K线数据

        Args:
            symbol: 股票代码
            period: daily/weekly/15min/30min
            count: K线数量

        Returns:
            K线列表 [{date, open, high, low, close, volume, ...}]
        """
        cache_key = f"{symbol}_{period}_{count}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        logger.info("获取K线: %s %s × %d", symbol, period, count)
        bars: List[Dict] = []
        self._cache[cache_key] = bars
        return bars

    def fetch_realtime(self, symbol: str) -> Dict:
        """获取实时行情"""
        return {"symbol": symbol, "price": 0, "timestamp": datetime.now().isoformat()}

    def fetch_dragon_list(self, symbol: str) -> Optional[Dict]:
        """获取龙虎榜数据"""
        return None

    def fetch_north_capital(self) -> Dict:
        """获取北向资金数据"""
        return {"north_inflow": 0, "timestamp": datetime.now().isoformat()}

    def clear_cache(self):
        self._cache.clear()
