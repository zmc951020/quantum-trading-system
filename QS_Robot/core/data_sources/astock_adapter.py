#!/usr/bin/env python3
"""
a-Stock-data 聚合数据源适配器（占位实现）

当 a-Stock-data 包可用时，将接入其聚合数据源
"""

from typing import Dict, List, Optional, Any

from core.data_sources.base_adapter import BaseDataSourceAdapter


class AStockDataAdapter(BaseDataSourceAdapter):
    """a-Stock-data 聚合数据源适配器（占位实现）"""

    name = "astock"

    def _init(self):
        self._available = False
        try:
            # 尝试检测 a-stock-data 包（实际上可能叫其他名字）
            import importlib
            mod = importlib.util.find_spec("a_stock_data")
            if mod is not None:
                self._available = True
                print(f"[AStockDataAdapter] 检测到a-Stock-data，适配器已启用")
        except Exception:
            pass

        if not self._available:
            print(f"[AStockDataAdapter] a-Stock-data 暂不可用，作为降级占位")
            # 保持可用状态，但实际降级返回None
            self._available = True  # 允许作为降级的兜底数据源

    # --------------------------------------------------------
    # 接口实现（占位，返回None，由总线自动降级到其他源）
    # --------------------------------------------------------

    def get_kline(self, symbol: str, period: str = "daily", days: int = 500) -> Optional[Dict[str, Any]]:
        """占位实现 - 返回 None，由数据总线自动降级到其他源"""
        return None

    def get_financial(self, symbol: str) -> Optional[Dict[str, Any]]:
        """占位实现 - 返回 None"""
        return None

    def get_realtime(self, symbol: str) -> Optional[Dict[str, Any]]:
        """占位实现 - 返回 None"""
        return None

    def get_stock_list(self, market: str = "A股") -> List[Dict]:
        """占位实现 - 返回空列表"""
        return []
