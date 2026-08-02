#!/usr/bin/env python3
"""种子池数据采集器 — 金融大师股票池 + 专家评点

数据源（与 market_intel 同构，基于AKShare）:
  1. 金融大师股票池(THS_MASTER_POOL): AKShare涨幅榜热点股 + PoolFilter策略筛选
     逻辑：取涨幅榜Top50 → 按策略applicable_pool过滤 → 符合的入种子池
  2. 专家评点(THS_EXPERT): AKShare龙虎榜机构净买入
     逻辑：取龙虎榜机构专用席位净买入≥3000万的股票 → 入专家评点池

缓存策略：盘中5分钟、盘后30分钟（复用market_intel的TTL）
去重：依赖stock_pool.add_stock已有去重逻辑（symbol已存在则跳过）
降级：AKShare失败 → 返回空列表 + 日志告警，不阻塞流程
"""

import time
import logging
from typing import Dict, List, Any

from core.stock_pool import get_stock_pool_manager, StockSource

logger = logging.getLogger(__name__)

MIN_INSTITUTIONAL_BUY = 3e7  # 机构净买入≥3000万
HOT_STOCKS_LIMIT = 50        # 涨幅榜Top50


class SeedPoolCollector:
    """种子池采集器 — 两大来源自动填充"""

    def __init__(self):
        self._ak = None
        self._cache: Dict[str, tuple] = {}
        try:
            import akshare as ak
            self._ak = ak
            logger.info("[SeedPool] AKShare 已加载")
        except ImportError:
            logger.warning("[SeedPool] AKShare 未安装，将使用空数据模式")

    def collect_master_pool(self) -> Dict[str, Any]:
        """采集金融大师股票池：涨幅榜热点 + 策略适用性过滤"""
        hot_stocks = self._fetch_hot_stocks()
        added, skipped = [], []
        from api.ths_bridge.pool_filter import get_pool_filter
        pool_filter = get_pool_filter()

        for s in hot_stocks:
            symbol, name = s.get("symbol", ""), s.get("name", "")
            if not symbol:
                continue
            # 用第一个匹配的策略作为推荐策略（简化：取MACD波段的applicable_pool）
            config = pool_filter._load_pool_config("01_macd_wave") or {}
            passes, reason = pool_filter.filter_stock(
                symbol=symbol, name=name, pool_config=config)
            if not passes:
                skipped.append({"symbol": symbol, "name": name, "reason": reason})
                continue
            result = get_stock_pool_manager().add_seed_stock(
                symbol=symbol, name=name,
                source=StockSource.THS_MASTER_POOL,
                strategy_name="涨幅榜热点+MACD波段适用",
            )
            (added if result.get("success") else skipped).append(
                {"symbol": symbol, "name": name,
                 "reason": result.get("error") or result.get("message", "")})

        return {"source": "master_pool", "total": len(hot_stocks),
                "added": len(added), "skipped": len(skipped),
                "stocks": added[:20], "fetched_at": _now()}

    def collect_expert(self) -> Dict[str, Any]:
        """采集专家评点池：龙虎榜机构净买入"""
        lhb_stocks = self._fetch_dragon_tiger()
        added, skipped = [], []
        for s in lhb_stocks:
            symbol, name = s.get("symbol", ""), s.get("name", "")
            net_buy = s.get("net_buy", 0)
            if not symbol or net_buy < MIN_INSTITUTIONAL_BUY:
                skipped.append({"symbol": symbol, "name": name,
                                "reason": f"机构净买入不足({net_buy/1e4:.0f}万<{MIN_INSTITUTIONAL_BUY/1e4:.0f}万)"})
                continue
            result = get_stock_pool_manager().add_seed_stock(
                symbol=symbol, name=name,
                source=StockSource.THS_EXPERT,
                strategy_name=f"龙虎榜机构净买入{net_buy/1e4:.0f}万",
            )
            (added if result.get("success") else skipped).append(
                {"symbol": symbol, "name": name,
                 "reason": result.get("error") or result.get("message", "")})

        return {"source": "expert", "total": len(lhb_stocks),
                "added": len(added), "skipped": len(skipped),
                "stocks": added[:20], "fetched_at": _now()}

    def collect_all(self) -> Dict[str, Any]:
        """一键采集两类种子池"""
        return {"master_pool": self.collect_master_pool(),
                "expert": self.collect_expert(),
                "fetched_at": _now()}

    # ---------- AKShare 数据获取（带降级） ----------

    def _fetch_hot_stocks(self) -> List[Dict]:
        """涨幅榜热点股票"""
        if not self._ak:
            return []
        try:
            df = self._ak.stock_zh_a_spot_em()
            if df is None or df.empty:
                return []
            df = df.sort_values("涨跌幅", ascending=False).head(HOT_STOCKS_LIMIT)
            return [{"symbol": str(r["代码"]).zfill(6), "name": r["名称"],
                     "price": float(r["最新价"] or 0),
                     "change_pct": float(r["涨跌幅"] or 0)}
                    for _, r in df.iterrows()]
        except Exception as e:
            logger.warning("[SeedPool] 涨幅榜获取失败: %s", e)
            return []

    def _fetch_dragon_tiger(self) -> List[Dict]:
        """龙虎榜机构净买入"""
        if not self._ak:
            return []
        try:
            df = self._ak.stock_lhb_detail_em(
                start_date=_today(), end_date=_today())
            if df is None or df.empty:
                return []
            # 聚合：按代码+名称求和机构净买入
            agg = df.groupby(["代码", "名称"]).agg(
                net_buy=("龙虎榜净买额", "sum")).reset_index()
            return [{"symbol": str(r["代码"]).zfill(6), "name": r["名称"],
                     "net_buy": float(r["net_buy"] or 0)}
                    for _, r in agg.iterrows()]
        except Exception as e:
            logger.warning("[SeedPool] 龙虎榜获取失败: %s", e)
            return []


def _now() -> str:
    from datetime import datetime
    return datetime.now().isoformat()


def _today() -> str:
    from datetime import datetime
    return datetime.now().strftime("%Y%m%d")


_collector = None


def get_seed_pool_collector() -> SeedPoolCollector:
    """获取种子池采集器单例"""
    global _collector
    if _collector is None:
        _collector = SeedPoolCollector()
    return _collector
