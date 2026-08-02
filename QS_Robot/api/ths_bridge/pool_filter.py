#!/usr/bin/env python3
"""股票池过滤器 - 按策略 applicable_pool 配置筛选股票

每个策略在 JSON 元数据中声明了 applicable_pool：
  markets: 适用市场板块 (main/creative/tech/bj)
  exclude_st: 排除ST股
  exclude_new: 排除新股（上市<60日）
  min_market_cap: 最小市值（亿元）
  min_volume: 最小日均成交额（万元）

本模块负责：
1. 按股票代码识别市场板块
2. 按 applicable_pool 配置过滤股票
3. 给 SignalCollector 提供按策略筛选的股票池入口
"""

import re
import logging
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


def detect_market(symbol: str) -> str:
    """根据股票代码识别市场板块

    Args:
        symbol: 股票代码（6位数字）

    Returns:
        市场标识：main(主板) / creative(创业板) / tech(科创板) / bj(北交所) / unknown
    """
    sym = str(symbol).strip().zfill(6)
    if not re.match(r'^\d{6}$', sym):
        return "unknown"
    # 沪市主板：600/601/603/605
    if sym.startswith(('600', '601', '603', '605')):
        return "main"
    # 深市主板：000/001
    if sym.startswith(('000', '001')):
        return "main"
    # 创业板：300/301
    if sym.startswith(('300', '301')):
        return "creative"
    # 科创板：688/689
    if sym.startswith(('688', '689')):
        return "tech"
    # 北交所：8开头（430/830/870/920）
    if sym.startswith(('430', '830', '870', '920', '871', '872', '873', '874',
                        '875', '876', '877', '878', '879', '880', '881', '882',
                        '883', '889')):
        return "bj"
    return "unknown"


def is_st_stock(name: str) -> bool:
    """判断是否ST股"""
    if not name:
        return False
    return 'ST' in name.upper() or '*ST' in name or 'ST*' in name


class PoolFilter:
    """股票池过滤器 - 按 applicable_pool 配置筛选"""

    def __init__(self):
        self._cache_market = {}  # symbol -> market 缓存

    def filter_stock(self, symbol: str, name: str,
                     pool_config: Dict[str, Any],
                     market_cap: float = 0.0,
                     avg_volume: float = 0.0,
                     list_days: int = 999) -> tuple:
        """过滤单只股票是否符合策略的 applicable_pool 配置

        Args:
            symbol: 股票代码
            name: 股票名称（用于ST判断）
            pool_config: applicable_pool 配置
            market_cap: 市值（亿元）
            avg_volume: 日均成交额（万元）
            list_days: 上市天数

        Returns:
            (passes: bool, reason: str)
        """
        if not pool_config:
            return True, "无过滤配置"

        # 1. 市场板块匹配
        markets = pool_config.get("markets", [])
        if markets:
            market = self._cache_market.get(symbol)
            if market is None:
                market = detect_market(symbol)
                self._cache_market[symbol] = market
            if market not in markets:
                return False, f"市场不匹配({market}不在{markets})"

        # 2. ST股过滤
        if pool_config.get("exclude_st", False) and is_st_stock(name):
            return False, "ST股已排除"

        # 3. 新股过滤
        if pool_config.get("exclude_new", False) and list_days < 60:
            return False, f"新股未满60日({list_days}日)"

        # 4. 市值过滤
        min_cap = pool_config.get("min_market_cap", 0)
        if min_cap and market_cap < min_cap:
            return False, f"市值不足({market_cap:.1f}<{min_cap}亿)"

        # 5. 成交额过滤
        min_vol = pool_config.get("min_volume", 0)
        if min_vol and avg_volume < min_vol:
            return False, f"成交额不足({avg_volume:.0f}<{min_vol}万)"

        return True, "通过"

    def filter_universe(self, universe: List[Dict],
                        pool_config: Dict[str, Any]) -> List[Dict]:
        """批量过滤股票池，返回符合配置的股票

        Args:
            universe: 候选股票列表，每项含 symbol/name/market_cap/avg_volume/list_days
            pool_config: applicable_pool 配置

        Returns:
            过滤后的股票列表
        """
        result = []
        for stock in universe:
            symbol = stock.get("symbol", "")
            name = stock.get("name", "")
            passes, reason = self.filter_stock(
                symbol=symbol, name=name,
                pool_config=pool_config,
                market_cap=stock.get("market_cap", 0),
                avg_volume=stock.get("avg_volume", 0),
                list_days=stock.get("list_days", 999),
            )
            if passes:
                result.append(stock)
            else:
                logger.debug("[PoolFilter] %s(%s) 过滤: %s", symbol, name, reason)
        return result

    def get_strategy_pool(self, strategy_id: str,
                          universe: List[Dict] = None) -> List[Dict]:
        """按策略ID获取其适用股票池

        Args:
            strategy_id: 策略ID（如 "01_macd_wave"）
            universe: 全市场股票列表

        Returns:
            策略适用的股票列表
        """
        from pathlib import Path
        # 加载策略的 applicable_pool 配置
        pool_config = self._load_pool_config(strategy_id)
        if not pool_config:
            logger.warning("[PoolFilter] 策略 %s 无 applicable_pool 配置，返回全市场", strategy_id)
            return universe or []
        return self.filter_universe(universe or [], pool_config)

    @staticmethod
    def _load_pool_config(strategy_id: str) -> Optional[Dict]:
        """从JSON元数据加载策略的 applicable_pool 配置

        优先按文件实际存在位置判断属于14策略还是18战法，回退到双JSON查找
        """
        from pathlib import Path
        import json
        # __file__ = QS_Robot/api/ths_bridge/pool_filter.py
        # root   = QS_Robot/
        root = Path(__file__).resolve().parent.parent.parent
        base_14 = root / "core" / "strategies" / "ths_strategies" / "14_strategies"
        base_18 = root / "core" / "strategies" / "ths_strategies" / "18_advanced"
        json_14 = root / "data" / "ths_academy" / "14_strategies.json"
        json_18 = root / "data" / "ths_academy" / "18_advanced.json"

        # 按.py文件位置确定JSON归属
        candidate_jsons = []
        if (base_14 / f"{strategy_id}.py").exists():
            candidate_jsons.append(json_14)
        if (base_18 / f"{strategy_id}.py").exists():
            candidate_jsons.append(json_18)
        # 兜底：两个JSON都查
        if not candidate_jsons:
            candidate_jsons = [json_14, json_18]

        for json_file in candidate_jsons:
            if not json_file.exists():
                continue
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
                for s in data.get("strategies", []):
                    if s.get("id") == strategy_id:
                        return s.get("applicable_pool")
            except Exception as e:
                logger.error("[PoolFilter] 加载 %s 失败: %s", json_file, e)
        return None


_filter: Optional[PoolFilter] = None


def get_pool_filter() -> PoolFilter:
    """获取股票池过滤器单例"""
    global _filter
    if _filter is None:
        _filter = PoolFilter()
    return _filter
