#!/usr/bin/env python3
"""
数据源适配器基类

所有数据源适配器必须继承自此基类，实现统一接口。
"""

from typing import Dict, List, Optional, Any


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
