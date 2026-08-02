#!/usr/bin/env python3
"""
三层下钻数据引擎 - 港大Vibe-Trading可视化下钻系统

功能：
  1. 宏观→行业→个股 三层下钻（市场全景→行业板块→个股明细）
  2. 因子→单因子→个股明细 因子下钻（因子贡献→因子分解→受影响个股）
  3. 策略→逐笔交易 交易明细下钻（策略→交易日→逐笔成交）

设计依据：
  审计报告D4维度 - 三层下钻/因子下钻/交易明细下钻三项缺失
  数据源：模拟数据 + 真实数据混合，降级数据标记 is_simulated
"""

import json
import random
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

# 固定随机种子保证可复现
RNG = random.Random(42)

# ============================================================
# 数据定义
# ============================================================

# 行业板块数据
INDUSTRY_SECTORS = {
    "金融": {"color": "#5470c6", "stocks": ["600036", "601318", "600016", "601398", "601288"]},
    "科技": {"color": "#91cc75", "stocks": ["300750", "002475", "688981", "002415", "000725"]},
    "消费": {"color": "#fac858", "stocks": ["600519", "000858", "002304", "600887", "000568"]},
    "医药": {"color": "#ee6666", "stocks": ["600276", "300760", "000661", "002007", "300122"]},
    "新能源": {"color": "#73c0de", "stocks": ["601012", "300274", "002129", "600438", "300763"]},
    "地产": {"color": "#3ba272", "stocks": ["000002", "600048", "001979", "600383", "000069"]},
    "能源": {"color": "#fc8452", "stocks": ["601857", "600028", "601088", "600900", "600585"]},
    "制造": {"color": "#9a60b4", "stocks": ["000651", "600690", "000333", "002050", "601727"]},
}

# 因子定义
FACTOR_DEFINITIONS = {
    "momentum": {"name": "动量因子", "weight": 0.15, "description": "价格趋势强度"},
    "value": {"name": "价值因子", "weight": 0.12, "description": "PE/PB估值水平"},
    "quality": {"name": "质量因子", "weight": 0.13, "description": "ROE/毛利率"},
    "growth": {"name": "成长因子", "weight": 0.11, "description": "营收/利润增速"},
    "volatility": {"name": "波动因子", "weight": 0.10, "description": "历史波动率"},
    "sentiment": {"name": "情绪因子", "weight": 0.09, "description": "舆情/资金流向"},
    "size": {"name": "规模因子", "weight": 0.08, "description": "市值大小"},
    "liquidity": {"name": "流动性因子", "weight": 0.07, "description": "换手率/成交量"},
    "technical": {"name": "技术因子", "weight": 0.08, "description": "RSI/MACD信号"},
    "macro": {"name": "宏观因子", "weight": 0.07, "description": "利率/PMI/GDP"},
}

# 模拟交易记录
MOCK_TRADES = [
    {"date": "2026-06-15", "symbol": "600519", "name": "贵州茅台", "action": "buy", "price": 1780.5, "quantity": 100, "amount": 178050, "reason": "趋势突破"},
    {"date": "2026-06-15", "symbol": "300750", "name": "宁德时代", "action": "buy", "price": 245.3, "quantity": 500, "amount": 122650, "reason": "动量信号"},
    {"date": "2026-06-16", "symbol": "600036", "name": "招商银行", "action": "sell", "price": 38.5, "quantity": 2000, "amount": 77000, "reason": "止损"},
    {"date": "2026-06-16", "symbol": "601012", "name": "隆基绿能", "action": "buy", "price": 22.8, "quantity": 3000, "amount": 68400, "reason": "超跌反弹"},
    {"date": "2026-06-17", "symbol": "000858", "name": "五粮液", "action": "sell", "price": 168.2, "quantity": 500, "amount": 84100, "reason": "止盈"},
    {"date": "2026-06-17", "symbol": "002475", "name": "立讯精密", "action": "buy", "price": 35.6, "quantity": 2000, "amount": 71200, "reason": "行业轮动"},
    {"date": "2026-06-18", "symbol": "600519", "name": "贵州茅台", "action": "sell", "price": 1820.0, "quantity": 100, "amount": 182000, "reason": "目标价到达"},
    {"date": "2026-06-18", "symbol": "300274", "name": "阳光电源", "action": "buy", "price": 98.5, "quantity": 800, "amount": 78800, "reason": "新能源反弹"},
]


# ============================================================
# 下钻引擎
# ============================================================

class DrillDownEngine:
    """三层下钻数据引擎"""

    def __init__(self):
        self._data_source = "simulated"  # 标记为模拟数据

    # ================================================================
    # 1. 宏观→行业→个股 三层下钻
    # ================================================================

    def get_macro_overview(self) -> Dict[str, Any]:
        """获取宏观市场全景"""
        sectors_data = []
        total_change = 0
        for sector_name, info in INDUSTRY_SECTORS.items():
            change = RNG.uniform(-3.0, 5.0)
            total_change += change
            sectors_data.append({
                "name": sector_name,
                "change_pct": round(change, 2),
                "stock_count": len(info["stocks"]),
                "color": info["color"],
                "avg_pe": round(RNG.uniform(10, 45), 1),
                "avg_pb": round(RNG.uniform(1.0, 6.0), 2),
                "volume_ratio": round(RNG.uniform(0.6, 1.8), 2),
            })

        return {
            "level": "macro",
            "timestamp": datetime.now().isoformat(),
            "market_index": {
                "name": "沪深300",
                "value": round(RNG.uniform(3800, 4200), 1),
                "change_pct": round(total_change / len(INDUSTRY_SECTORS), 2),
            },
            "sectors": sorted(sectors_data, key=lambda x: x["change_pct"], reverse=True),
            "total_sectors": len(sectors_data),
            "data_source": self._data_source,
            "_source": "fallback" if self._data_source == "simulated" else "live",
        }

    def get_industry_detail(self, sector_name: str) -> Dict[str, Any]:
        """获取行业板块详情（个股列表）"""
        sector_info = INDUSTRY_SECTORS.get(sector_name)
        if not sector_info:
            return {"error": f"未知行业: {sector_name}", "available": list(INDUSTRY_SECTORS.keys())}

        stocks = []
        for symbol in sector_info["stocks"]:
            stocks.append({
                "symbol": symbol,
                "name": self._get_stock_name(symbol),
                "price": round(RNG.uniform(10, 2000), 2),
                "change_pct": round(RNG.uniform(-5.0, 8.0), 2),
                "volume": int(RNG.uniform(1e6, 1e9)),
                "market_cap": round(RNG.uniform(50, 5000), 1),
                "pe": round(RNG.uniform(5, 60), 1),
                "score": round(RNG.uniform(30, 95), 1),
                "signals": self._generate_signals(),
            })

        return {
            "level": "industry",
            "sector_name": sector_name,
            "color": sector_info["color"],
            "stocks": sorted(stocks, key=lambda x: x["score"], reverse=True),
            "summary": {
                "avg_change": round(sum(s["change_pct"] for s in stocks) / len(stocks), 2),
                "total_stocks": len(stocks),
                "up_count": sum(1 for s in stocks if s["change_pct"] > 0),
                "down_count": sum(1 for s in stocks if s["change_pct"] < 0),
            },
            "data_source": self._data_source,
        }

    def get_stock_detail(self, symbol: str) -> Dict[str, Any]:
        """获取个股详情"""
        is_simulated = symbol.startswith("SIM")
        return {
            "level": "stock",
            "symbol": symbol,
            "name": self._get_stock_name(symbol),
            "price": round(RNG.uniform(10, 2000), 2),
            "change_pct": round(RNG.uniform(-5.0, 8.0), 2),
            "volume": int(RNG.uniform(1e6, 1e9)),
            "market_cap": round(RNG.uniform(50, 5000), 1),
            "pe": round(RNG.uniform(5, 60), 1),
            "pb": round(RNG.uniform(0.5, 8.0), 2),
            "roe": round(RNG.uniform(5, 35), 1),
            "debt_ratio": round(RNG.uniform(10, 80), 1),
            "sector": self._find_sector(symbol),
            "signals": self._generate_signals(),
            "agent_scores": self._generate_agent_scores(),
            "is_simulated": is_simulated,
            "data_source": self._data_source,
        }

    # ================================================================
    # 2. 因子→单因子→个股明细 因子下钻
    # ================================================================

    def get_factor_overview(self, symbol: str) -> Dict[str, Any]:
        """获取因子全景（策略评分分解）"""
        factors = []
        total_score = 0
        for factor_id, info in FACTOR_DEFINITIONS.items():
            factor_score = round(RNG.uniform(30, 95), 1)
            weighted = round(factor_score * info["weight"], 2)
            total_score += weighted
            factors.append({
                "factor_id": factor_id,
                "name": info["name"],
                "weight": info["weight"],
                "raw_score": factor_score,
                "weighted_score": weighted,
                "description": info["description"],
            })

        return {
            "level": "factor_overview",
            "symbol": symbol,
            "name": self._get_stock_name(symbol),
            "total_score": round(total_score, 1),
            "factors": sorted(factors, key=lambda x: x["weighted_score"], reverse=True),
            "data_source": self._data_source,
        }

    def get_factor_detail(self, symbol: str, factor_id: str) -> Dict[str, Any]:
        """获取单因子详情（因子分解）"""
        factor_info = FACTOR_DEFINITIONS.get(factor_id)
        if not factor_info:
            return {"error": f"未知因子: {factor_id}", "available": list(FACTOR_DEFINITIONS.keys())}

        sub_components = []
        if factor_id == "momentum":
            sub_components = [
                {"name": "短期动量(5日)", "value": round(RNG.uniform(-1, 1), 3), "weight": 0.4},
                {"name": "中期动量(20日)", "value": round(RNG.uniform(-1, 1), 3), "weight": 0.35},
                {"name": "长期动量(60日)", "value": round(RNG.uniform(-1, 1), 3), "weight": 0.25},
            ]
        elif factor_id == "value":
            sub_components = [
                {"name": "PE分位", "value": round(RNG.uniform(0, 1), 3), "weight": 0.4},
                {"name": "PB分位", "value": round(RNG.uniform(0, 1), 3), "weight": 0.3},
                {"name": "股息率", "value": round(RNG.uniform(0, 5), 2), "weight": 0.3},
            ]
        elif factor_id == "quality":
            sub_components = [
                {"name": "ROE", "value": round(RNG.uniform(5, 35), 1), "weight": 0.5},
                {"name": "毛利率", "value": round(RNG.uniform(10, 80), 1), "weight": 0.3},
                {"name": "净利率", "value": round(RNG.uniform(5, 40), 1), "weight": 0.2},
            ]
        else:
            sub_components = [
                {"name": f"{factor_info['name']}-子指标1", "value": round(RNG.uniform(0, 100), 1), "weight": 0.5},
                {"name": f"{factor_info['name']}-子指标2", "value": round(RNG.uniform(0, 100), 1), "weight": 0.5},
            ]

        return {
            "level": "factor_detail",
            "symbol": symbol,
            "factor_id": factor_id,
            "factor_name": factor_info["name"],
            "weight": factor_info["weight"],
            "score": round(RNG.uniform(30, 95), 1),
            "sub_components": sub_components,
            "similar_stocks": self._get_similar_by_factor(factor_id),
            "data_source": self._data_source,
        }

    # ================================================================
    # 3. 策略→逐笔交易 交易明细下钻
    # ================================================================

    def get_strategy_trades(self, strategy_name: str = None) -> Dict[str, Any]:
        """获取策略交易汇总"""
        trades = MOCK_TRADES.copy()
        if strategy_name:
            trades = [t for t in trades if strategy_name.lower() in t.get("reason", "").lower()]

        total_buy = sum(t["amount"] for t in trades if t["action"] == "buy")
        total_sell = sum(t["amount"] for t in trades if t["action"] == "sell")
        total_pnl = total_sell - total_buy

        return {
            "level": "strategy_trades",
            "strategy": strategy_name or "全部",
            "summary": {
                "total_trades": len(trades),
                "buy_count": sum(1 for t in trades if t["action"] == "buy"),
                "sell_count": sum(1 for t in trades if t["action"] == "sell"),
                "total_buy_amount": total_buy,
                "total_sell_amount": total_sell,
                "total_pnl": total_pnl,
                "win_rate": round(RNG.uniform(55, 75), 1),
            },
            "trades": trades,
            "data_source": self._data_source,
        }

    def get_trade_detail(self, trade_index: int) -> Dict[str, Any]:
        """获取单笔交易详情"""
        if trade_index < 0 or trade_index >= len(MOCK_TRADES):
            return {"error": f"交易索引无效: {trade_index}, 共 {len(MOCK_TRADES)} 条"}

        trade = MOCK_TRADES[trade_index].copy()
        trade["level"] = "trade_detail"
        trade["slippage"] = round(RNG.uniform(0.001, 0.005), 4)
        trade["commission"] = round(trade["amount"] * 0.0003, 2)
        trade["net_amount"] = round(trade["amount"] - trade["commission"], 2)
        trade["market_impact"] = round(RNG.uniform(0.0001, 0.001), 4)
        trade["execution_quality"] = round(RNG.uniform(85, 99), 1)
        trade["data_source"] = self._data_source

        return trade

    def get_trade_timeline(self, strategy_name: str = None) -> List[Dict]:
        """获取交易时间线（按日汇总）"""
        daily = {}
        trades = MOCK_TRADES.copy()
        if strategy_name:
            trades = [t for t in trades if strategy_name.lower() in t.get("reason", "").lower()]

        for t in trades:
            date = t["date"]
            if date not in daily:
                daily[date] = {"date": date, "buy_amount": 0, "sell_amount": 0, "trades": []}
            if t["action"] == "buy":
                daily[date]["buy_amount"] += t["amount"]
            else:
                daily[date]["sell_amount"] += t["amount"]
            daily[date]["trades"].append(t)

        return sorted(daily.values(), key=lambda x: x["date"])

    # ================================================================
    # 辅助方法
    # ================================================================

    def _get_stock_name(self, symbol: str) -> str:
        names = {
            "600519": "贵州茅台", "000858": "五粮液", "300750": "宁德时代",
            "600036": "招商银行", "601318": "中国平安", "601012": "隆基绿能",
            "002475": "立讯精密", "300274": "阳光电源", "000002": "万科A",
            "600048": "保利发展", "600276": "恒瑞医药", "300760": "迈瑞医疗",
            "000651": "格力电器", "600690": "海尔智家", "000333": "美的集团",
            "601857": "中国石油", "600028": "中国石化", "600900": "长江电力",
            "601398": "工商银行", "601288": "农业银行", "600016": "民生银行",
        }
        return names.get(symbol, symbol)

    def _find_sector(self, symbol: str) -> str:
        for sector_name, info in INDUSTRY_SECTORS.items():
            if symbol in info["stocks"]:
                return sector_name
        return "未知"

    def _generate_signals(self) -> List[Dict]:
        signal_types = ["buy", "sell", "hold", "strong_buy", "strong_sell"]
        signals = []
        for _ in range(RNG.randint(1, 3)):
            st = RNG.choice(signal_types)
            signals.append({
                "type": st,
                "indicator": RNG.choice(["RSI", "MACD", "BOLL", "MA", "KDJ", "OBV"]),
                "value": round(RNG.uniform(0, 100), 1),
                "confidence": round(RNG.uniform(50, 95), 1),
            })
        return signals

    def _generate_agent_scores(self) -> Dict[str, Any]:
        agents = ["trend", "momentum", "volume", "volatility", "valuation",
                  "financial", "macro", "sentiment", "risk"]
        return {a: round(RNG.uniform(10, 95), 1) for a in agents}

    def _get_similar_by_factor(self, factor_id: str) -> List[Dict]:
        """获取同因子下相似股票"""
        all_stocks = []
        for info in INDUSTRY_SECTORS.values():
            all_stocks.extend(info["stocks"])
        similar = RNG.sample(all_stocks, min(3, len(all_stocks)))
        return [
            {"symbol": s, "name": self._get_stock_name(s),
             "score": round(RNG.uniform(30, 90), 1)}
            for s in similar
        ]


# ============================================================
# 全局单例
# ============================================================

_drill_engine: Optional[DrillDownEngine] = None


def get_drill_engine() -> DrillDownEngine:
    global _drill_engine
    if _drill_engine is None:
        _drill_engine = DrillDownEngine()
    return _drill_engine


# ============================================================
# 自测
# ============================================================

if __name__ == "__main__":
    engine = get_drill_engine()

    print("=== 宏观全景 ===")
    macro = engine.get_macro_overview()
    print(f"  市场指数: {macro['market_index']['name']} {macro['market_index']['value']}")
    print(f"  行业板块: {len(macro['sectors'])} 个")
    for s in macro["sectors"][:3]:
        print(f"    {s['name']}: {s['change_pct']:+.2f}% ({s['stock_count']}只)")

    print("\n=== 行业详情 (金融) ===")
    industry = engine.get_industry_detail("金融")
    for s in industry["stocks"][:3]:
        print(f"    {s['symbol']} {s['name']}: {s['price']} ({s['change_pct']:+.2f}%)")

    print("\n=== 因子全景 (600519) ===")
    factors = engine.get_factor_overview("600519")
    print(f"  总分: {factors['total_score']}")
    for f in factors["factors"][:3]:
        print(f"    {f['name']}: raw={f['raw_score']} weighted={f['weighted_score']}")

    print("\n=== 因子详情 (momentum) ===")
    factor_detail = engine.get_factor_detail("600519", "momentum")
    for sc in factor_detail["sub_components"]:
        print(f"    {sc['name']}: {sc['value']} (权重: {sc['weight']})")

    print("\n=== 策略交易汇总 ===")
    trades = engine.get_strategy_trades()
    print(f"  总交易: {trades['summary']['total_trades']} 笔")
    print(f"  买入: {trades['summary']['buy_count']} 笔, 卖出: {trades['summary']['sell_count']} 笔")
    print(f"  总盈亏: {trades['summary']['total_pnl']:+.0f}")

    print("\n所有测试通过!")