#!/usr/bin/env python3
"""
同花顺金融大师 - 市场情报采集器

对应金融大师"投教中心"的实时市场情报面板，5大维度：
  1. 每日热点股票 (涨幅榜/跌幅榜/成交额榜)
  2. 大盘动态 (上证/深证/创业板/科创50/北证50)
  3. 资金动向 (北向资金净流入 + 行业主力资金)
  4. 板块轮动 (行业板块涨跌幅)
  5. 市场情绪 (涨跌家数比/涨停跌停数)

数据源：AKShare（东方财富/新浪）
缓存策略：盘中5分钟、盘后30分钟，避免高频请求
"""

import time
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

# 盘中刷新5分钟，盘后刷新30分钟
INTRADAY_TTL = 300
AFTER_HOURS_TTL = 1800


def _is_trading_hours(now: datetime = None) -> bool:
    """判断当前是否为A股交易时段"""
    now = now or datetime.now()
    if now.weekday() >= 5:
        return False
    hour_min = now.hour * 100 + now.minute
    return 915 <= hour_min <= 1130 or 1300 <= hour_min <= 1500


def _cache_ttl() -> int:
    """获取当前缓存TTL（秒）"""
    return INTRADAY_TTL if _is_trading_hours() else AFTER_HOURS_TTL


class MarketIntelCollector:
    """市场情报采集器 — 5大维度统一采集入口"""

    def __init__(self):
        self._ak = None
        self._cache: Dict[str, tuple] = {}
        try:
            import akshare as ak
            self._ak = ak
            logger.info("[MarketIntel] AKShare 已加载")
        except ImportError:
            logger.warning("[MarketIntel] AKShare 未安装，使用模拟数据")

    def _cached(self, key: str, fetcher) -> Any:
        """带TTL的缓存获取"""
        now = time.time()
        if key in self._cache:
            data, ts = self._cache[key]
            if now - ts < _cache_ttl():
                return data
        try:
            data = fetcher()
            self._cache[key] = (data, now)
            return data
        except Exception as e:
            logger.error("[MarketIntel] 获取 %s 失败: %s", key, e)
            return self._fallback(key)

    # ============================================================
    # 1. 每日热点股票
    # ============================================================

    def fetch_hot_stocks(self, limit: int = 20) -> Dict[str, Any]:
        """获取每日热点股票（涨幅榜/跌幅榜/成交额榜）"""
        return self._cached("hot_stocks", lambda: self._fetch_hot_impl(limit))

    def _fetch_hot_impl(self, limit: int) -> Dict[str, Any]:
        if not self._ak:
            return self._mock_hot(limit)
        try:
            df = self._ak.stock_zh_a_spot_em()
            if df is None or len(df) == 0:
                return self._mock_hot(limit)
            df = df[df['涨跌幅'].notna()]
            gainers = df.nlargest(limit, '涨跌幅')
            losers = df.nsmallest(limit, '涨跌幅')
            vol_top = df.nlargest(limit, '成交额')
            return {
                "gainers": self._format_spot(gainers),
                "losers": self._format_spot(losers),
                "volume_top": self._format_spot(vol_top),
                "updated_at": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.warning("[MarketIntel] 热点股获取失败: %s", e)
            return self._mock_hot(limit)

    @staticmethod
    def _format_spot(df) -> List[Dict]:
        """格式化Spot DataFrame为字典列表"""
        cols_map = {
            '代码': 'symbol', '名称': 'name', '最新价': 'price',
            '涨跌幅': 'change_pct', '涨跌额': 'change',
            '成交量': 'volume', '成交额': 'amount', '换手率': 'turnover',
        }
        result = []
        for _, row in df.iterrows():
            item = {}
            for cn, en in cols_map.items():
                if cn in row:
                    val = row[cn]
                    try:
                        if en in ('symbol', 'name'):
                            item[en] = str(val)
                        else:
                            item[en] = float(val) if val == val else 0.0  # NaN检查
                    except (ValueError, TypeError):
                        item[en] = str(val) if en in ('symbol', 'name') else 0.0
            if item.get('symbol'):
                result.append(item)
        return result

    @staticmethod
    def _mock_hot(limit: int) -> Dict[str, Any]:
        """模拟热点数据"""
        return {
            "gainers": [
                {"symbol": f"60000{i}", "name": f"涨幅股{i}", "price": 10 + i,
                 "change_pct": 9.87 - i * 0.3, "change": 1.0 - i * 0.05}
                for i in range(limit)
            ],
            "losers": [
                {"symbol": f"00000{i}", "name": f"跌幅股{i}", "price": 20 - i,
                 "change_pct": -5.43 + i * 0.2, "change": -1.0 + i * 0.05}
                for i in range(limit)
            ],
            "volume_top": [
                {"symbol": f"30000{i}", "name": f"成交股{i}", "price": 15 + i,
                 "amount": 1.5e9 - i * 5e7}
                for i in range(limit)
            ],
            "updated_at": datetime.now().isoformat(),
            "mock": True,
        }

    # ============================================================
    # 2. 大盘动态
    # ============================================================

    def fetch_market_overview(self) -> Dict[str, Any]:
        """获取大盘指数动态"""
        return self._cached("market_overview", self._fetch_market_impl)

    def _fetch_market_impl(self) -> Dict[str, Any]:
        if not self._ak:
            return self._mock_market()
        indices_cfg = [
            ("上证指数", "sh000001"),
            ("深证成指", "sz399001"),
            ("创业板指", "sz399006"),
            ("科创50", "sh000688"),
            ("北证50", "bj899050"),
        ]
        result = []
        for name, code in indices_cfg:
            try:
                df = self._ak.stock_zh_index_daily_em(symbol=code)
                if df is not None and len(df) >= 2:
                    last = df.iloc[-1]
                    prev = df.iloc[-2]
                    close = float(last['close'])
                    prev_close = float(prev['close'])
                    result.append({
                        "name": name,
                        "code": code[2:] if len(code) > 2 else code,
                        "value": close,
                        "change": round(close - prev_close, 2),
                        "change_pct": round((close - prev_close) / prev_close * 100, 2),
                    })
            except Exception as e:
                logger.debug("[MarketIntel] %s 获取失败: %s", name, e)
        if not result:
            return self._mock_market()
        return {"indices": result, "updated_at": datetime.now().isoformat()}

    @staticmethod
    def _mock_market() -> Dict[str, Any]:
        return {
            "indices": [
                {"name": "上证指数", "code": "000001", "value": 3289.45,
                 "change": 25.36, "change_pct": 0.78},
                {"name": "深证成指", "code": "399001", "value": 10456.78,
                 "change": -12.45, "change_pct": -0.12},
                {"name": "创业板指", "code": "399006", "value": 2156.34,
                 "change": 18.90, "change_pct": 0.88},
                {"name": "科创50", "code": "000688", "value": 875.43,
                 "change": -3.21, "change_pct": -0.37},
                {"name": "北证50", "code": "899050", "value": 1098.76,
                 "change": 15.67, "change_pct": 1.45},
            ],
            "updated_at": datetime.now().isoformat(),
            "mock": True,
        }

    # ============================================================
    # 3. 资金动向
    # ============================================================

    def fetch_capital_flow(self) -> Dict[str, Any]:
        """获取资金动向（北向资金 + 行业主力资金）"""
        return self._cached("capital_flow", self._fetch_capital_impl)

    def _fetch_capital_impl(self) -> Dict[str, Any]:
        if not self._ak:
            return self._mock_capital()
        try:
            north = self._fetch_north_flow()
            sectors = self._fetch_sector_capital()
            return {
                "north_bound": north,
                "sector_flow": sectors,
                "updated_at": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.warning("[MarketIntel] 资金动向获取失败: %s", e)
            return self._mock_capital()

    def _fetch_north_flow(self) -> Dict[str, Any]:
        """北向资金净流入"""
        try:
            df = self._ak.stock_hsgt_north_net_flow_in_em(symbol="北向资金")
            if df is not None and len(df) > 0:
                last = df.iloc[-1]
                value = float(last['当日成交净买额']) if '当日成交净买额' in last else 0.0
                date = str(last['交易日']) if '交易日' in last else datetime.now().strftime("%Y-%m-%d")
                return {"net_buy": value, "date": date, "unit": "元"}
        except Exception as e:
            logger.debug("[MarketIntel] 北向资金失败: %s", e)
        return {"net_buy": 0.0, "date": datetime.now().strftime("%Y-%m-%d"), "unit": "元"}

    def _fetch_sector_capital(self, limit: int = 10) -> List[Dict]:
        """行业板块主力资金流向Top"""
        try:
            df = self._ak.stock_sector_fund_flow_rank(indicator="今日", sector_type="行业资金流")
            if df is None or len(df) == 0:
                return []
            df = df.head(limit)
            result = []
            for _, row in df.iterrows():
                result.append({
                    "name": str(row.get('名称', '')),
                    "change_pct": float(row.get('今日涨跌幅', 0) or 0),
                    "net_flow": float(row.get('今日主力净流入-净额', 0) or 0),
                })
            return result
        except Exception as e:
            logger.debug("[MarketIntel] 行业资金流失败: %s", e)
            return []

    @staticmethod
    def _mock_capital() -> Dict[str, Any]:
        return {
            "north_bound": {"net_buy": 56.78e8, "date": datetime.now().strftime("%Y-%m-%d"), "unit": "元"},
            "sector_flow": [
                {"name": "电子", "change_pct": 2.34, "net_flow": 12.5e8},
                {"name": "医药生物", "change_pct": 1.23, "net_flow": 8.9e8},
                {"name": "计算机", "change_pct": -0.45, "net_flow": -3.2e8},
            ],
            "updated_at": datetime.now().isoformat(),
            "mock": True,
        }

    # ============================================================
    # 4. 板块轮动
    # ============================================================

    def fetch_sector_rotation(self) -> Dict[str, Any]:
        """获取行业板块涨跌幅（轮动看板）"""
        return self._cached("sector_rotation", self._fetch_sector_impl)

    def _fetch_sector_impl(self) -> Dict[str, Any]:
        if not self._ak:
            return self._mock_sector()
        try:
            df = self._ak.stock_board_industry_name_em()
            if df is None or len(df) == 0:
                return self._mock_sector()
            df = df.sort_values('涨跌幅', ascending=False)
            sectors = []
            for _, row in df.iterrows():
                sectors.append({
                    "name": str(row.get('板块名称', '')),
                    "code": str(row.get('板块代码', '')),
                    "change_pct": float(row.get('涨跌幅', 0) or 0),
                    "leader": str(row.get('领涨股票', '')),
                })
            return {
                "sectors": sectors,
                "top_gainers": sectors[:10],
                "top_losers": list(reversed(sectors[-10:])),
                "updated_at": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.warning("[MarketIntel] 板块轮动失败: %s", e)
            return self._mock_sector()

    @staticmethod
    def _mock_sector() -> Dict[str, Any]:
        mock_sectors = [
            {"name": "半导体", "change_pct": 3.45, "leader": "中芯国际"},
            {"name": "光伏设备", "change_pct": 2.87, "leader": "隆基绿能"},
            {"name": "医药商业", "change_pct": 1.92, "leader": "国药一致"},
            {"name": "酿酒行业", "change_pct": -1.34, "leader": "贵州茅台"},
            {"name": "房地产", "change_pct": -2.10, "leader": "万科A"},
        ]
        return {
            "sectors": mock_sectors,
            "top_gainers": mock_sectors[:3],
            "top_losers": list(reversed(mock_sectors[-3:])),
            "updated_at": datetime.now().isoformat(),
            "mock": True,
        }

    # ============================================================
    # 5. 市场情绪
    # ============================================================

    def fetch_market_emotion(self) -> Dict[str, Any]:
        """获取市场情绪指标（涨跌家数比/涨停跌停数）"""
        return self._cached("market_emotion", self._fetch_emotion_impl)

    def _fetch_emotion_impl(self) -> Dict[str, Any]:
        if not self._ak:
            return self._mock_emotion()
        try:
            df = self._ak.stock_zh_a_spot_em()
            if df is None or len(df) == 0:
                return self._mock_emotion()
            df = df[df['涨跌幅'].notna()]
            up = len(df[df['涨跌幅'] > 0])
            down = len(df[df['涨跌幅'] < 0])
            flat = len(df[df['涨跌幅'] == 0])
            limit_up = len(df[df['涨跌幅'] >= 9.9])
            limit_down = len(df[df['涨跌幅'] <= -9.9])
            total = len(df)
            return {
                "up_count": up, "down_count": down, "flat_count": flat,
                "limit_up": limit_up, "limit_down": limit_down, "total": total,
                "up_ratio": round(up / total * 100, 2) if total else 0.0,
                "emotion_score": round((up - down) / total * 100, 2) if total else 0.0,
                "updated_at": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.warning("[MarketIntel] 情绪获取失败: %s", e)
            return self._mock_emotion()

    @staticmethod
    def _mock_emotion() -> Dict[str, Any]:
        return {
            "up_count": 2856, "down_count": 1872, "flat_count": 156,
            "limit_up": 48, "limit_down": 12, "total": 4884,
            "up_ratio": 58.48, "emotion_score": 20.14,
            "updated_at": datetime.now().isoformat(),
            "mock": True,
        }

    # ============================================================
    # 统一入口：一键采集全部情报
    # ============================================================

    def fetch_all(self) -> Dict[str, Any]:
        """一键采集5大维度市场情报"""
        return {
            "hot_stocks": self.fetch_hot_stocks(),
            "market_overview": self.fetch_market_overview(),
            "capital_flow": self.fetch_capital_flow(),
            "sector_rotation": self.fetch_sector_rotation(),
            "market_emotion": self.fetch_market_emotion(),
            "fetched_at": datetime.now().isoformat(),
        }

    def _fallback(self, key: str) -> Any:
        mock_map = {
            "hot_stocks": lambda: self._mock_hot(20),
            "market_overview": self._mock_market,
            "capital_flow": self._mock_capital,
            "sector_rotation": self._mock_sector,
            "market_emotion": self._mock_emotion,
        }
        return mock_map.get(key, lambda: {})()


_collector: Optional[MarketIntelCollector] = None


def get_market_intel_collector() -> MarketIntelCollector:
    """获取市场情报采集器单例"""
    global _collector
    if _collector is None:
        _collector = MarketIntelCollector()
    return _collector
