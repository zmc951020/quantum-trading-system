#!/usr/bin/env python3
"""
统一数据总线 (Unified Data Bus)

架构设计：
  上层应用(技术分析/策略优化/Vibe智能体)
            │
            ▼
  统一数据总线 (DataBus)  ← 缓存管理器
            │
            ▼
  数据源适配层 (Adapters)
    ├── AKShareAdapter (东方财富/新浪)
    ├── AStockDataAdapter (a-Stock-data 聚合数据源)
    ├── VibeAdapter (港大Vibe智能体数据源)
    └── BrokerAdapter (券商实时数据，预留)

核心特性：
  1. 统一入口：所有应用通过 get_kline/get_financials 获取数据
  2. 源优先级：按配置自动选择最优数据源
  3. 智能缓存：内存缓存 + 文件缓存 + TTL
  4. 数据校验：格式检查 + 完整性检查 + 去重
  5. 优雅降级：高优先级源失败时自动切换到低优先级
"""

import os
import json
import time
import threading
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple

from core.data_cache import get_cache_manager
from core.data_validator import get_validator

# ============================================================
# 数据类型定义
# ============================================================

class DataPeriod:
    """数据周期"""
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    MIN_1 = "1min"
    MIN_5 = "5min"
    MIN_15 = "15min"
    MIN_30 = "30min"
    MIN_60 = "60min"

    @classmethod
    def all_periods(cls) -> List[str]:
        return [cls.DAILY, cls.WEEKLY, cls.MONTHLY,
                cls.MIN_1, cls.MIN_5, cls.MIN_15, cls.MIN_30, cls.MIN_60]

# ============================================================
# 统一数据格式定义
# ============================================================

def create_kline_format(symbol: str, name: str = "", market: str = "A股",
                        period: str = "daily",
                        dates: List[str] = None, opens: List[float] = None,
                        highs: List[float] = None, lows: List[float] = None,
                        closes: List[float] = None, volumes: List[float] = None,
                        source: str = "") -> Dict[str, Any]:
    """创建标准K线格式数据"""
    return {
        "symbol": symbol,
        "name": name,
        "market": market,
        "period": period,
        "dates": dates or [],
        "opens": opens or [],
        "highs": highs or [],
        "lows": lows or [],
        "closes": closes or [],
        "volumes": volumes or [],
        "source": source,
        "count": len(dates) if dates else 0,
        "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

def create_financial_format(symbol: str, name: str = "",
                           pe: float = None, pb: float = None,
                           eps: float = None, roe: float = None,
                           revenue_growth: float = None, profit_growth: float = None,
                           total_market_cap: float = None, industry: str = "",
                           source: str = "") -> Dict[str, Any]:
    """创建标准财务数据格式"""
    return {
        "symbol": symbol,
        "name": name,
        "pe": pe,
        "pb": pb,
        "eps": eps,
        "roe": roe,
        "revenue_growth": revenue_growth,
        "profit_growth": profit_growth,
        "total_market_cap": total_market_cap,
        "industry": industry,
        "source": source,
        "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

# ============================================================
# 数据源优先级配置
# ============================================================

DEFAULT_PRIORITY = {
    "kline": ["akshare", "tushare", "vibe", "astock"],
    "financial": ["akshare", "tushare", "astock", "vibe"],
    "realtime": ["akshare", "tushare"]
}

DEFAULT_CACHE_TTL = {
    "kline": 3600,       # 1小时
    "financial": 86400,   # 1天
    "realtime": 5         # 5秒
}

# ============================================================
# 数据总线核心
# ============================================================

class UnifiedDataBus:
    """统一数据总线 - 所有应用的唯一数据入口"""

    def __init__(self, priority_config: Dict[str, List[str]] = None,
                 cache_ttl_config: Dict[str, int] = None):
        self._priority = priority_config or DEFAULT_PRIORITY
        self._cache_ttl = cache_ttl_config or DEFAULT_CACHE_TTL
        self._cache = get_cache_manager()
        self._validator = get_validator()
        self._adapters = {}
        self._lock = threading.Lock()
        self._init_adapters()

    # --------------------------------------------------------
    # 适配器管理
    # --------------------------------------------------------

    def _init_adapters(self):
        """初始化所有可用的数据源适配器"""
        try:
            from core.data_sources.akshare_adapter import AKShareAdapter
            self._adapters["akshare"] = AKShareAdapter()
            print(f"[DataBus] AKShare适配器已加载")
        except Exception as e:
            print(f"[DataBus] AKShare适配器加载失败: {e}")

        try:
            from core.data_sources.tushare_adapter import TushareAdapter
            self._adapters["tushare"] = TushareAdapter()
            print(f"[DataBus] Tushare适配器已加载")
        except Exception as e:
            print(f"[DataBus] Tushare适配器未加载: {e}")

        try:
            from core.data_sources.astock_adapter import AStockDataAdapter
            self._adapters["astock"] = AStockDataAdapter()
            print(f"[DataBus] AStockData适配器已加载")
        except Exception as e:
            print(f"[DataBus] AStockData适配器未加载: {e}")

        try:
            from core.data_sources.vibe_adapter import VibeAdapter
            self._adapters["vibe"] = VibeAdapter()
            print(f"[DataBus] Vibe适配器已加载")
        except Exception as e:
            print(f"[DataBus] Vibe适配器未加载: {e}")

        print(f"[DataBus] 可用数据源: {list(self._adapters.keys())}")

    def register_adapter(self, name: str, adapter: Any) -> bool:
        """注册新的数据源适配器"""
        with self._lock:
            self._adapters[name] = adapter
            print(f"[DataBus] 已注册适配器: {name}")
            return True

    def list_adapters(self) -> List[str]:
        """列出所有可用的适配器"""
        return list(self._adapters.keys())

    def is_adapter_available(self, name: str) -> bool:
        """检查适配器是否可用"""
        return name in self._adapters and self._adapters[name].is_available()

    # --------------------------------------------------------
    # 缓存操作快捷方法
    # --------------------------------------------------------

    def _get_cache(self, data_type: str, symbol: str, period: str = "", **kwargs) -> Optional[Dict]:
        """从缓存获取数据"""
        params = {"symbol": symbol, "period": period, **kwargs}
        return self._cache.get(data_type, params)

    def _set_cache(self, data_type: str, symbol: str, period: str = "",
                   **kwargs) -> bool:
        """设置缓存"""
        return self._cache.set(data_type, data_type, self._cache_ttl.get(data_type, 3600))

    # --------------------------------------------------------
    # K线数据获取
    # --------------------------------------------------------

    def get_kline(self, symbol: str, period: str = "daily", days: int = 500,
                  prefer_source: str = None, use_cache: bool = True) -> Optional[Dict[str, Any]]:
        """获取K线数据（统一入口）

        Args:
            symbol: 股票代码，如 "000001"
            period: 数据周期，DataPeriod枚举值
            days: 获取的天数
            prefer_source: 首选数据源名称（覆盖默认优先级）
            use_cache: 是否使用缓存

        Returns:
            标准K线格式数据字典，失败返回None
        """
        # 1. 检查缓存
        if use_cache:
            cached = self._get_cache("kline", symbol, period, days=days)
            if cached:
                print(f"[DataBus] {symbol} K线命中缓存")
                return cached

        # 2. 确定数据源优先级
        sources = [prefer_source] if prefer_source and prefer_source in self._adapters else []
        for src in self._priority.get("kline", []):
            if src not in sources and src in self._adapters:
                sources.append(src)

        if not sources:
            print(f"[DataBus] 错误: 没有可用的数据源")
            return None

        # 3. 按优先级尝试获取数据
        last_error = None
        for source_name in sources:
            try:
                adapter = self._adapters.get(source_name)
                if not adapter or not adapter.is_available():
                    print(f"[DataBus] {source_name} 不可用，跳过")
                    continue

                print(f"[DataBus] 尝试从 {source_name} 获取 {symbol} K线...")
                result = adapter.get_kline(symbol, period, days)

                if result and result.get("count", 0) > 0:
                    # 4. 数据校验
                    validation = self._validator.validate_kline(result)
                    if not validation["valid"]:
                        print(f"[DataBus] {source_name} 数据校验失败: {validation['errors']}")
                        continue

                    # 5. 存入缓存
                    ttl = self._cache_ttl.get("kline", 3600)
                    self._cache.set("kline", {"symbol": symbol, "period": period, "days": days},
                                    result, ttl=ttl)

                    print(f"[DataBus] {symbol} K线获取成功 (源: {source_name}, {result['count']}条)")
                    return result

            except Exception as e:
                last_error = e
                print(f"[DataBus] {source_name} 获取失败: {e}")
                continue

        print(f"[DataBus] {symbol} K线获取失败，所有源尝试完毕")
        if last_error:
            print(f"[DataBus] 最后错误: {last_error}")
        return None

    # --------------------------------------------------------
    # 财务数据获取
    # --------------------------------------------------------

    def get_financial(self, symbol: str, prefer_source: str = None,
                     use_cache: bool = True) -> Optional[Dict[str, Any]]:
        """获取财务数据"""
        if use_cache:
            cached = self._get_cache("financial", symbol)
            if cached:
                print(f"[DataBus] {symbol} 财务数据命中缓存")
                return cached

        sources = [prefer_source] if prefer_source and prefer_source in self._adapters else []
        for src in self._priority.get("financial", []):
            if src not in sources and src in self._adapters:
                sources.append(src)

        if not sources:
            return None

        for source_name in sources:
            try:
                adapter = self._adapters.get(source_name)
                if not adapter or not adapter.is_available():
                    continue

                print(f"[DataBus] 尝试从 {source_name} 获取 {symbol} 财务数据...")
                result = adapter.get_financial(symbol)

                if result:
                    ttl = self._cache_ttl.get("financial", 86400)
                    self._cache.set("financial", {"symbol": symbol}, result, ttl=ttl)

                    print(f"[DataBus] {symbol} 财务数据获取成功 (源: {source_name})")
                    return result

            except Exception as e:
                print(f"[DataBus] {source_name} 获取财务数据失败: {e}")
                continue

        return None

    # --------------------------------------------------------
    # 实时数据获取
    # --------------------------------------------------------

    def get_realtime(self, symbol: str, prefer_source: str = None) -> Optional[Dict[str, Any]]:
        """获取实时行情数据"""
        sources = [prefer_source] if prefer_source and prefer_source in self._adapters else []
        for src in self._priority.get("realtime", []):
            if src not in sources and src in self._adapters:
                sources.append(src)

        if not sources:
            return None

        for source_name in sources:
            try:
                adapter = self._adapters.get(source_name)
                if not adapter or not adapter.is_available():
                    continue

                result = adapter.get_realtime(symbol)
                if result:
                    return result

            except Exception as e:
                continue

        return None

    # --------------------------------------------------------
    # 股票列表
    # --------------------------------------------------------

    def get_stock_list(self, market: str = "A股") -> List[Dict]:
        """获取股票列表"""
        for source_name in self._priority.get("kline", []):
            adapter = self._adapters.get(source_name)
            if adapter and adapter.is_available():
                try:
                    result = adapter.get_stock_list(market)
                    if result:
                        return result
                except Exception as e:
                    continue
        return []

    # --------------------------------------------------------
    # 状态监控
    # --------------------------------------------------------

    def get_status(self) -> Dict[str, Any]:
        """获取总线状态"""
        status = {
            "adapters": {},
            "cache_hits": self._cache.get_hit_count(),
            "cache_misses": self._cache.get_miss_count()
        }
        for name, adapter in self._adapters.items():
            status["adapters"][name] = {
                "available": adapter.is_available()
            }
        return status

# ============================================================
# 单例模式
# ============================================================

_global_bus: Optional[UnifiedDataBus] = None
_global_lock = threading.Lock()

def get_data_bus() -> UnifiedDataBus:
    """获取数据总线单例"""
    global _global_bus
    if _global_bus is None:
        with _global_lock:
            if _global_bus is None:
                _global_bus = UnifiedDataBus()
    return _global_bus
