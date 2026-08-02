#!/usr/bin/env python3
"""种子池量化验证器 — 32策略扫描 → 升级流转

流转逻辑:
  1. 从 stock_pool 取所有种子池股票(THS_MASTER_POOL/THS_EXPERT)
  2. 对每只股票调用 SignalCollector.scan() 用32策略生成信号
  3. 命中买入信号的股票 → promote_seed_to_iwencai() 升级为实盘池
  4. 未命中 → 留在种子池继续等待验证

触发方式:
  - 手动触发: POST /market_intel/api/seed_pool/validate
  - 定时触发: 由外部调度器调用 validate_seed_pool()

依赖:
  - bars_map 由调用方提供（实盘由行情模块提供，回测由历史数据提供）
  - SignalCollector 已加载32策略
"""

import logging
from typing import Dict, List, Any

from core.stock_pool import get_stock_pool_manager, StockSource
from api.ths_bridge.signal_collector import SignalCollector

logger = logging.getLogger(__name__)


class SeedPoolValidator:
    """种子池量化验证器 — 种子池→实盘池的自动流转"""

    def __init__(self):
        self._pool = get_stock_pool_manager()
        self._collector = SignalCollector()

    def get_seed_stocks(self) -> List[Dict]:
        """获取所有待验证的种子池股票"""
        stocks = []
        for symbol, record in self._pool._pools.items():
            if record.source in StockSource.seed_sources():
                stocks.append({
                    "symbol": symbol,
                    "name": record.name,
                    "source": record.source.value,
                    "strategy": record.strategy_name,
                })
        return stocks

    def validate_seed_pool(self, bars_map: Dict[str, List[dict]],
                          stock_names: Dict[str, str] = None) -> Dict[str, Any]:
        """对种子池股票执行32策略量化验证

        Args:
            bars_map: {symbol: bars_list} K线数据
            stock_names: {symbol: name} 股票名称（ST过滤用）

        Returns:
            {
                "total_seeds": 待验证种子数,
                "validated": 命中信号数,
                "promoted": 升级成功数,
                "failed": 升级失败数,
                "details": 每只股票的验证结果
            }
        """
        seeds = self.get_seed_stocks()
        # 只验证有K线数据的种子
        validable = [s for s in seeds if s["symbol"] in bars_map]

        if not validable:
            return {"total_seeds": len(seeds), "validated": 0,
                    "promoted": 0, "failed": 0, "details": [],
                    "message": "无K线数据的种子池股票，请先提供bars_map"}

        # 筛选bars_map只保留种子池股票
        seed_bars = {sym: bars_map[sym] for sym in [s["symbol"] for s in validable]}
        signals = self._collector.scan(seed_bars, stock_names=stock_names)

        # 按symbol聚合命中信号
        signals_by_symbol = {}
        for sig in signals:
            sym = sig["symbol"]
            if sym not in signals_by_symbol:
                signals_by_symbol[sym] = []
            signals_by_symbol[sym].append(sig)

        # 升级命中的种子
        details = []
        promoted, failed = 0, 0
        for seed in validable:
            sym = seed["symbol"]
            hits = signals_by_symbol.get(sym, [])
            if not hits:
                details.append({"symbol": sym, "name": seed["name"],
                                "source": seed["source"],
                                "passed": False, "reason": "未命中买入信号"})
                continue

            # 取第一个命中信号作为升级策略
            hit = hits[0]
            result = self._pool.promote_seed_to_iwencai(
                symbol=sym,
                strategy_name=hit["strategy_name"],
                validation_result={
                    "signal": hit["signal"],
                    "risk_level": hit["risk_level"],
                    "strategy_count": len(hits),
                })

            if result.get("success"):
                promoted += 1
                details.append({"symbol": sym, "name": seed["name"],
                                "source": seed["source"], "passed": True,
                                "strategy": hit["strategy_name"],
                                "hit_count": len(hits)})
            else:
                failed += 1
                details.append({"symbol": sym, "name": seed["name"],
                                "source": seed["source"], "passed": False,
                                "reason": result.get("error", "升级失败")})

        logger.info("[SeedValidator] 验证完成: 种子%d → 命中%d → 升级%d",
                    len(validable), len(signals_by_symbol), promoted)
        return {"total_seeds": len(seeds), "validated": len(signals_by_symbol),
                "promoted": promoted, "failed": failed, "details": details}


_validator = None


def get_seed_pool_validator() -> SeedPoolValidator:
    """获取种子池验证器单例"""
    global _validator
    if _validator is None:
        _validator = SeedPoolValidator()
    return _validator
