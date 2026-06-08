#!/usr/bin/env python3
"""
统一数据获取器（Unified Data Fetcher）

核心职责：
  1. 统一接口：对上层屏蔽不同数据源的差异
  2. 多源融合：AKShare + 备选数据源自动fallback
  3. 智能缓存：本地文件缓存 + TTL机制，避免重复请求
  4. 数据标准化：统一返回格式（OHLCV + 财务指标）
  5. 批量获取：支持多股票批量查询

支持的数据：
  - 股票K线（日/周/月/分钟）
  - 财务指标（PE、PB、EPS、ROE等）
  - 行业分类、概念板块
  - 指数成分股
"""

import os
import json
import time
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

# ============================================================
# 数据源类型
# ============================================================

class DataSourceType:
    AKSHARE = "akshare"
    BACKUP = "backup"

# ============================================================
# 数据获取器
# ============================================================

class UnifiedDataFetcher:
    def __init__(self, cache_dir: str = "data/market_cache", cache_ttl_days: int = 1):
        self._cache_dir = os.path.join(os.path.dirname(__file__), "..", cache_dir)
        self._cache_ttl = cache_ttl_days * 24 * 60 * 60  # 秒
        self._akshare = None
        self._init_akshare()
        os.makedirs(self._cache_dir, exist_ok=True)

    def _init_akshare(self):
        """延迟初始化 AKShare"""
        try:
            import akshare as ak
            self._akshare = ak
            print("[DataFetcher] AKShare 已加载")
        except ImportError:
            print("[DataFetcher] AKShare 未安装，使用模拟数据")

    def _get_cache_key(self, symbol: str, period: str, days: int, data_type: str) -> str:
        """生成缓存键"""
        key_str = f"{symbol}_{period}_{days}_{data_type}"
        return hashlib.md5(key_str.encode()).hexdigest()[:12]

    def _read_cache(self, symbol: str, period: str, days: int, data_type: str):
        """从缓存读取数据（兼容 dict/list）"""
        key = self._get_cache_key(symbol, period, days, data_type)
        path = os.path.join(self._cache_dir, f"{key}.json")
        
        if not os.path.exists(path):
            return None
        
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # 检查TTL
            created_at = data.get("_cache_created_at", 0) if isinstance(data, dict) else 0
            if time.time() - created_at > self._cache_ttl:
                return None
            
            # 如果是 list-wrapper 包装，返回原始数据
            if isinstance(data, dict) and "_cache_type" in data and "data" in data:
                return data["data"]
            return data
        except Exception:
            return None

    def _write_cache(self, symbol: str, period: str, days: int, data_type: str, data):
        """写入缓存（兼容 dict / list / 任意可JSON序列化结构，含 datetime/date）"""
        key = self._get_cache_key(symbol, period, days, data_type)
        path = os.path.join(self._cache_dir, f"{key}.json")

        if isinstance(data, dict):
            payload = dict(data)
            payload["_cache_created_at"] = time.time()
        else:
            # list / 其他类型：包装在一个 wrapper dict 中
            payload = {
                "_cache_created_at": time.time(),
                "_cache_type": type(data).__name__,
                "data": data,
            }
        import datetime as _dt

        def _default(obj):
            if isinstance(obj, (_dt.datetime, _dt.date)):
                return obj.isoformat()
            if hasattr(obj, "__float__"):
                return float(obj)
            raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")

        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False, default=_default)
        except Exception as e:
            print(f"[DataFetcher] 缓存写入失败: {e}")

    # ---------- 股票K线数据 ----------

    def get_kline(self, symbol: str, period: str = "daily", days: int = 500, 
                  adjust: str = "qfq") -> Optional[Dict]:
        """获取股票K线数据
        
        Args:
            symbol: 股票代码（6位数字，如 '000001'）
            period: 'daily' | 'weekly' | 'monthly' | '60min' | '30min' | '15min' | '5min' | '1min'
            days: 获取天数（实际会多取30天留余量）
            adjust: 复权类型 'qfq'(前复权) | 'hfq'(后复权) | None(不复权)
        
        Returns:
            dict: {dates, opens, highs, lows, closes, volumes, symbol, period, count, start_date, end_date}
        """
        # 先查缓存
        cache = self._read_cache(symbol, period, days, "kline")
        if cache:
            return cache
        
        # 获取数据
        data = None
        if self._akshare:
            data = self._fetch_kline_akshare(symbol, period, days, adjust)
        
        # fallback到模拟数据
        if data is None:
            data = self._generate_mock_kline(symbol, days)
        
        # 写入缓存
        if data:
            self._write_cache(symbol, period, days, "kline", data)
        
        return data

    def _fetch_kline_akshare(self, symbol: str, period: str, days: int, adjust: str) -> Optional[Dict]:
        """通过 AKShare 获取 K线"""
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days * 2 + 30)  # 多取30天
            
            start_str = start_date.strftime("%Y%m%d")
            end_str = end_date.strftime("%Y%m%d")
            
            period_map = {
                "daily": "daily",
                "weekly": "weekly",
                "monthly": "monthly",
                "60min": "60",
                "30min": "30",
                "15min": "15",
                "5min": "5",
                "1min": "1"
            }
            
            ak_period = period_map.get(period, "daily")
            
            if period in ["daily", "weekly", "monthly"]:
                df = self._akshare.stock_zh_a_hist(
                    symbol=symbol,
                    period=ak_period,
                    start_date=start_str,
                    end_date=end_str,
                    adjust=adjust
                )
            else:
                df = self._akshare.stock_zh_a_minute(
                    symbol=symbol,
                    period=ak_period,
                    start_date=start_str,
                    end_date=end_str,
                    adjust=adjust
                )
            
            return self._normalize_kline(df)
        except Exception as e:
            print(f"[DataFetcher] AKShare获取K线失败 {symbol}: {e}")
            return None

    def _normalize_kline(self, df) -> Dict:
        """标准化 K线数据格式"""
        if df is None or df.empty:
            return None
        
        # 中文列名映射
        col_map = {
            "日期": "dates",
            "时间": "dates",
            "date": "dates",
            "开盘": "opens",
            "Open": "opens",
            "open": "opens",
            "收盘": "closes",
            "Close": "closes",
            "close": "closes",
            "最高": "highs",
            "High": "highs",
            "high": "highs",
            "最低": "lows",
            "Low": "lows",
            "low": "lows",
            "成交量": "volumes",
            "Volume": "volumes",
            "volume": "volumes"
        }
        
        result = {"dates": [], "opens": [], "highs": [], "lows": [], "closes": [], "volumes": []}
        
        for col_name, target_key in col_map.items():
            if col_name in df.columns:
                result[target_key] = df[col_name].tolist()
        
        # 确保长度一致
        min_len = min(len(v) for v in result.values())
        for k in result:
            result[k] = result[k][:min_len]
        
        if len(result["dates"]) > 0:
            result.update({
                "count": len(result["dates"]),
                "start_date": result["dates"][0],
                "end_date": result["dates"][-1]
            })
        
        return result

    def _generate_mock_kline(self, symbol: str, days: int) -> Dict:
        """生成模拟K线数据（备用）"""
        import random
        dates = []
        opens = []
        highs = []
        lows = []
        closes = []
        volumes = []
        
        price = 10.0 + random.uniform(-2, 2)
        today = datetime.now()
        
        for i in range(days):
            date_str = (today - timedelta(days=days - i - 1)).strftime("%Y-%m-%d")
            dates.append(date_str)
            
            open_p = price + random.uniform(-0.2, 0.2)
            close_p = open_p + random.uniform(-0.3, 0.3)
            high_p = max(open_p, close_p) + random.uniform(0, 0.15)
            low_p = min(open_p, close_p) - random.uniform(0, 0.15)
            
            opens.append(round(open_p, 2))
            closes.append(round(close_p, 2))
            highs.append(round(high_p, 2))
            lows.append(round(low_p, 2))
            volumes.append(random.randint(10000, 50000))
            
            price = close_p
        
        return {
            "dates": dates,
            "opens": opens,
            "highs": highs,
            "lows": lows,
            "closes": closes,
            "volumes": volumes,
            "symbol": symbol,
            "count": days,
            "start_date": dates[0],
            "end_date": dates[-1],
            "_mock": True
        }

    # ---------- 财务指标 ----------

    def get_financials(self, symbol: str) -> Optional[Dict]:
        """获取股票财务指标"""
        cache = self._read_cache(symbol, "financial", 0, "financials")
        if cache:
            return cache
        
        data = None
        if self._akshare:
            data = self._fetch_financials_akshare(symbol)
        
        if data is None:
            data = self._generate_mock_financials(symbol)
        
        if data:
            self._write_cache(symbol, "financial", 0, "financials", data)
        
        return data

    def _fetch_financials_akshare(self, symbol: str) -> Optional[Dict]:
        """通过 AKShare 获取财务数据"""
        try:
            # 获取股票基本信息
            df = self._akshare.stock_zh_a_basic(symbol=symbol)
            if df.empty:
                return None
            
            result = {
                "pe": float(df.get("pe", [0])[0]) if not df.empty else 0,
                "pb": float(df.get("pb", [0])[0]) if not df.empty else 0,
                "market_cap": float(df.get("total_mv", [0])[0]) / 10000 if not df.empty else 0,  # 亿
                "industry": str(df.get("industry", [""])[0]) if not df.empty else "",
                "list_date": str(df.get("list_date", [""])[0]) if not df.empty else ""
            }
            return result
        except Exception as e:
            print(f"[DataFetcher] 获取财务数据失败 {symbol}: {e}")
            return None

    def _generate_mock_financials(self, symbol: str) -> Dict:
        """生成模拟财务数据"""
        import random
        return {
            "pe": round(8 + random.uniform(-3, 12), 2),
            "pb": round(1 + random.uniform(-0.5, 3), 2),
            "market_cap": round(50 + random.uniform(-30, 950), 2),  # 亿
            "industry": random.choice(["金融", "科技", "消费", "医药", "制造"]),
            "eps": round(0.2 + random.uniform(-0.1, 1.5), 2),
            "roe": round(5 + random.uniform(-3, 15), 2),
            "_mock": True
        }

    # ---------- 股票列表 ----------

    def get_stock_list(self, market: str = "zh_a") -> List[Dict]:
        """获取股票列表（含丰富 spot 字段：价格、涨跌幅、成交量、成交额、换手率、振幅、PE、PB）

        Returns:
            List[Dict]: 每只股票包含 symbol/name/price/change_pct/volume/amount/turnover/amplitude/pe/pb
        """
        cache = self._read_cache(market, "list", 0, "stock_list")
        if cache:
            return cache

        data = []
        if self._akshare:
            try:
                if market == "zh_a":
                    df = self._akshare.stock_zh_a_spot_em()
                    # AKShare spot 常见列：代码,名称,最新价,涨跌幅,涨跌额,成交量,成交额,振幅,最高,最低,今开,昨收,量比,换手率,市盈率-动态,市净率 ...
                    col_map = {
                        "symbol": "代码",
                        "name": "名称",
                        "price": "最新价",
                        "change_pct": "涨跌幅",
                        "change_amount": "涨跌额",
                        "volume": "成交量",
                        "amount": "成交额",
                        "amplitude": "振幅",
                        "high": "最高",
                        "low": "最低",
                        "open": "今开",
                        "preclose": "昨收",
                        "volume_ratio": "量比",
                        "turnover": "换手率",
                        "pe": "市盈率-动态",
                        "pb": "市净率",
                    }
                    for _, row in df.iterrows():
                        item = {}
                        for k, col in col_map.items():
                            val = row.get(col)
                            if val is None:
                                # 兼容不同版本的字段命名
                                alt = None
                                if col == "市盈率-动态":
                                    alt = row.get("动态市盈率") or row.get("市盈率")
                                elif col == "市净率":
                                    alt = row.get("市净率")
                                if alt is not None:
                                    val = alt
                            try:
                                if k in ("symbol", "name"):
                                    item[k] = str(val) if val is not None else ""
                                else:
                                    fv = float(val) if val not in (None, "", "-") else 0.0
                                    item[k] = fv
                            except (TypeError, ValueError):
                                item[k] = "" if k in ("symbol", "name") else 0.0
                        data.append(item)
            except Exception as e:
                print(f"[DataFetcher] 获取股票列表失败: {e}")

        if not data:
            data = self._generate_mock_stock_list(50)

        self._write_cache(market, "list", 0, "stock_list", data)
        return data

    def _generate_mock_stock_list(self, count: int) -> List[Dict]:
        """生成模拟股票列表（字段结构与真实数据对齐）"""
        import random

        random.seed(42)
        names = ["平安银行", "贵州茅台", "五粮液", "招商银行", "中国平安",
                 "比亚迪", "宁德时代", "隆基绿能", "药明康德", "迈瑞医疗",
                 "美的集团", "格力电器", "海尔智家", "京东方A", "海康威视"]

        result = []
        for i in range(count):
            symbol = f"{random.randint(0, 6)}{random.randint(0, 9)}{random.randint(0, 9)}{random.randint(0, 9)}{random.randint(0, 9)}{random.randint(0, 9)}"
            name = names[i % len(names)] + ("" if i < len(names) else str(i))
            price = round(5 + random.uniform(-2, 95), 2)
            change_pct = round(random.uniform(-8, 8), 2)
            volume = random.randint(100_000, 50_000_000)
            amount = round(volume * price * random.uniform(0.8, 1.2), 0)
            turnover = round(random.uniform(0.1, 8.0), 2)
            amplitude = round(abs(change_pct) + random.uniform(0.5, 3.0), 2)
            pe = round(random.uniform(5, 60), 2)
            pb = round(random.uniform(0.5, 8.0), 2)
            result.append({
                "symbol": symbol,
                "name": name,
                "price": price,
                "change_pct": change_pct,
                "change_amount": round(price * change_pct / 100, 2),
                "volume": volume,
                "amount": amount,
                "amplitude": amplitude,
                "high": round(price * (1 + amplitude / 200), 2),
                "low": round(price * (1 - amplitude / 200), 2),
                "open": round(price * (1 - change_pct / 200), 2),
                "preclose": round(price / (1 + change_pct / 100), 2),
                "volume_ratio": round(random.uniform(0.3, 3.5), 2),
                "turnover": turnover,
                "pe": pe,
                "pb": pb,
            })
        return result

    # ---------- 批量获取 ----------

    def batch_get_kline(self, symbols: List[str], period: str = "daily", days: int = 500) -> Dict[str, Optional[Dict]]:
        """批量获取多只股票K线"""
        results = {}
        for symbol in symbols:
            results[symbol] = self.get_kline(symbol, period, days)
        return results

    def batch_get_financials(self, symbols: List[str]) -> Dict[str, Optional[Dict]]:
        """批量获取多只股票财务数据"""
        results = {}
        for symbol in symbols:
            results[symbol] = self.get_financials(symbol)
        return results

# ============================================================
# 全局单例
# ============================================================

_data_fetcher = None

def get_data_fetcher() -> UnifiedDataFetcher:
    global _data_fetcher
    if _data_fetcher is None:
        _data_fetcher = UnifiedDataFetcher()
    return _data_fetcher

# ============================================================
# 示例
# ============================================================

if __name__ == "__main__":
    df = get_data_fetcher()
    
    # 获取单只股票K线
    kline = df.get_kline("000001", "daily", 100)
    print(f"K线数据: {kline.get('count', 0)} 条")
    
    # 获取财务数据
    financials = df.get_financials("000001")
    print(f"财务数据: {financials}")
    
    # 获取股票列表
    stocks = df.get_stock_list()
    print(f"股票列表: {len(stocks)} 只")