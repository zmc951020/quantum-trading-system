#!/usr/bin/env python3
"""
Vibe-Trading 港大智能体数据源适配器（占位实现）

当 Vibe-Trading 完整安装后，将接入其数据源
"""

from typing import Dict, List, Optional, Any
import importlib.util

from core.data_sources.base_adapter import BaseDataSourceAdapter


class VibeAdapter(BaseDataSourceAdapter):
    """Vibe-Trading 智能体数据源适配器（占位实现）"""

    name = "vibe"

    def _init(self):
        self._available = False
        try:
            mod = importlib.util.find_spec("vibe_trading_ai")
            if mod is not None:
                self._available = True
                print(f"[VibeAdapter] 检测到Vibe-Trading，适配器已启用")
        except Exception:
            pass

        if not self._available:
            print(f"[VibeAdapter] Vibe-Trading 暂不可用，作为降级占位")
            self._available = True  # 允许作为降级源

    # --------------------------------------------------------
    # 接口实现（占位）
    # --------------------------------------------------------

    def get_kline(self, symbol: str, period: str = "daily", days: int = 500) -> Optional[Dict[str, Any]]:
        """占位实现 - 返回 None"""
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
