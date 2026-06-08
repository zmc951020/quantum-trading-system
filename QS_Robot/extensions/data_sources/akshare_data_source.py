#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AKShare 行情数据源 - 获取真实A股/指数/美股等历史K线，支持本地缓存。

本模块基于开源项目 AKShare 提供行情数据拉取能力，符合项目内 BaseDataSource
标准接口（connect / disconnect / is_connected / get_data / send_command），并实现
K 线数据的本地缓存，以减少重复请求并提高离线可用性。
"""

import os
import sys
import json
import time
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any


_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_CURRENT_DIR))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from .base_data_source import BaseDataSource


class AKShareDataSource(BaseDataSource):
    """基于 AKShare 的行情数据源适配器。

    对外提供统一的 connect / disconnect / is_connected / get_data /
    send_command 接口，内部负责 AKShare 的延迟导入、接口调用、列名归一化
    以及 JSON 本地缓存。
    """

    name = "akshare_data_source"
    description = "AKShare 行情数据源 - 支持 A股 / 美股 / 港股 K线数据"

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.cache_enabled = self.config.get("cache_enabled", True)
        self.cache_ttl_days = int(self.config.get("cache_ttl_days", 1))
        self._ak = None
        self._connected = False

        self.cache_dir = os.path.join(_PROJECT_ROOT, "data", "market_cache")
        if self.cache_enabled:
            os.makedirs(self.cache_dir, exist_ok=True)

    # -------------------- 连接管理 --------------------
    def connect(self) -> bool:
        try:
            import akshare as ak  # type: ignore
            self._ak = ak
        except Exception as exc:
            print("[AKShareDataSource] 警告: 无法导入 akshare 模块 - {}".format(exc))
            return False

        try:
            _ = self._ak.stock_zh_a_spot_em()
            self._connected = True
        except Exception as exc:
            print("[AKShareDataSource] 警告: 连通性验证失败（网络稍后会恢复）- {}".format(exc))
            self._connected = True

        return True

    def disconnect(self) -> None:
        self._connected = False
        self._ak = None

    def is_connected(self) -> bool:
        return self._connected and self._ak is not None

    # -------------------- 高层接口 --------------------
    def get_data(self, query: Dict[str, Any]) -> Any:
        if not query or not isinstance(query, dict):
            return {"status": "error", "message": "query 参数必须为 dict"}

        data_type = (query.get("type") or query.get("data_type") or "").lower()

        if data_type in ("kline", "ohlcv", "history"):
            symbol = query.get("symbol")
            period = query.get("period", "daily")
            days = int(query.get("days", 500))
            market = query.get("market", "auto")
            if not symbol:
                return {"status": "error", "message": "缺少 symbol 参数"}
            result = self.get_stock_kline(symbol, period=period, days=days, market=market)
            if result is None:
                return {"status": "error", "message": "获取 K 线数据失败"}
            return {"status": "ok", "data": result}

        return {
            "status": "unsupported",
            "message": "暂不支持的 type: {}".format(data_type),
            "available_types": ["kline", "ohlcv", "history"],
        }

    def send_command(self, command: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return {
            "status": "ok",
            "command": command,
            "params": params or {},
            "message": "AKShareDataSource 不执行命令，仅提供行情查询",
        }

    # -------------------- 主方法：K 线拉取 --------------------
    def get_stock_kline(
        self,
        symbol: str,
        period: str = "daily",
        days: int = 500,
        market: str = "auto",
    ) -> Optional[Dict[str, Any]]:
        try:
            if self.cache_enabled:
                cached = self._read_cache(symbol, period, days)
                if cached is not None:
                    return cached

            if not self._connected or self._ak is None:
                ok = self.connect()
                if not ok or self._ak is None:
                    print("[AKShareDataSource] 警告: AKShare 未连接，无法获取数据")
                    return None

            if market == "auto":
                market = self._detect_market(symbol)

            df = None
            if market == "zh_a":
                df = self._fetch_zh_a(symbol, period, days)
            elif market == "us":
                df = self._fetch_us(symbol, period, days)
            elif market == "hk":
                df = self._fetch_hk(symbol, period, days)
            else:
                print("[AKShareDataSource] 警告: 未知 market={}".format(market))
                return None

            if df is None or getattr(df, "empty", True):
                print("[AKShareDataSource] 警告: symbol={} 返回空数据".format(symbol))
                return None

            normalized = self._normalize_kline(df, market)
            normalized["symbol"] = symbol
            normalized["period"] = period
            normalized["market"] = market
            normalized["fetched_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            if self.cache_enabled:
                self._write_cache(symbol, period, days, normalized)

            return normalized
        except Exception as exc:
            print("[AKShareDataSource] 警告: get_stock_kline 异常 - {}".format(exc))
            return None

    # -------------------- 不同市场的底层抓取 --------------------
    def _fetch_zh_a(self, symbol: str, period: str, days: int):
        period_map = {"daily": "daily", "weekly": "weekly", "monthly": "monthly"}
        ak_period = period_map.get(period, "daily")

        today = datetime.now()
        start_date = today - timedelta(days=days * 2 + 30)
        start_str = start_date.strftime("%Y%m%d")
        end_str = today.strftime("%Y%m%d")

        try:
            df = self._ak.stock_zh_a_hist(
                symbol=symbol,
                period=ak_period,
                start_date=start_str,
                end_date=end_str,
                adjust="qfq",
            )
            return df
        except Exception as exc:
            print("[AKShareDataSource] _fetch_zh_a 失败: {}".format(exc))
            return None

    def _fetch_us(self, symbol: str, period: str, days: int):
        today = datetime.now()
        start_date = today - timedelta(days=days * 2 + 30)
        start_str = start_date.strftime("%Y%m%d")
        end_str = today.strftime("%Y%m%d")

        try:
            df = self._ak.stock_us_hist(
                symbol=symbol,
                period=period,
                start_date=start_str,
                end_date=end_str,
                adjust="qfq",
            )
            return df
        except Exception as exc:
            print("[AKShareDataSource] _fetch_us 失败: {}".format(exc))
            return None

    def _fetch_hk(self, symbol: str, period: str, days: int):
        today = datetime.now()
        start_date = today - timedelta(days=days * 2 + 30)
        start_str = start_date.strftime("%Y%m%d")
        end_str = today.strftime("%Y%m%d")

        try:
            df = self._ak.stock_hk_hist(
                symbol=symbol,
                period=period,
                start_date=start_str,
                end_date=end_str,
                adjust="qfq",
            )
            return df
        except Exception as exc:
            print("[AKShareDataSource] _fetch_hk 失败: {}".format(exc))
            return None

    # -------------------- 列名归一化 --------------------
    def _normalize_kline(self, df: Any, market: str) -> Dict[str, Any]:
        candidates_date = ["日期", "时间", "date", "Date"]
        candidates_open = ["开盘", "Open", "open"]
        candidates_close = ["收盘", "Close", "close"]
        candidates_high = ["最高", "High", "high"]
        candidates_low = ["最低", "Low", "low"]
        candidates_volume = ["成交量", "Volume", "volume"]

        def _find_col(cols, candidates):
            for name in candidates:
                for col in cols:
                    if str(col).strip() == name:
                        return col
            return None

        columns = list(df.columns)
        col_date = _find_col(columns, candidates_date)
        col_open = _find_col(columns, candidates_open)
        col_close = _find_col(columns, candidates_close)
        col_high = _find_col(columns, candidates_high)
        col_low = _find_col(columns, candidates_low)
        col_volume = _find_col(columns, candidates_volume)

        missing = [
            n
            for n, c in zip(
                ["date", "open", "close", "high", "low", "volume"],
                [col_date, col_open, col_close, col_high, col_low, col_volume],
            )
            if c is None
        ]
        if missing:
            print(
                "[AKShareDataSource] _normalize_kline 缺失列: {}; 实际列: {}".format(
                    missing, columns
                )
            )

        def _to_float_list(series) -> List[float]:
            if series is None:
                return []
            try:
                return [float(v) for v in series.tolist()]
            except Exception:
                values = []
                for v in series.tolist():
                    try:
                        values.append(float(v))
                    except Exception:
                        values.append(0.0)
                return values

        dates: List[str] = []
        if col_date is not None:
            for v in df[col_date].tolist():
                if isinstance(v, datetime):
                    dates.append(v.strftime("%Y-%m-%d"))
                else:
                    s = str(v).strip()
                    if " " in s:
                        s = s.split(" ", 1)[0]
                    dates.append(s)

        opens = _to_float_list(df[col_open] if col_open is not None else None)
        closes = _to_float_list(df[col_close] if col_close is not None else None)
        highs = _to_float_list(df[col_high] if col_high is not None else None)
        lows = _to_float_list(df[col_low] if col_low is not None else None)
        volumes = _to_float_list(df[col_volume] if col_volume is not None else None)

        count = len(dates)
        start_date = dates[0] if dates else ""
        end_date = dates[-1] if dates else ""

        return {
            "dates": dates,
            "opens": opens,
            "closes": closes,
            "highs": highs,
            "lows": lows,
            "volumes": volumes,
            "count": count,
            "start_date": start_date,
            "end_date": end_date,
        }

    # -------------------- 市场识别 --------------------
    @staticmethod
    def _detect_market(symbol: str) -> str:
        s = (symbol or "").strip()
        if not s:
            return "zh_a"

        if s.isdigit() and len(s) == 6:
            return "zh_a"

        if ".hk" in s.lower():
            return "hk"

        if any(c.isalpha() for c in s):
            return "us"

        return "zh_a"

    # -------------------- 缓存管理 --------------------
    def _cache_path(self, symbol: str, period: str, days: int) -> str:
        key = "{}_{}_{}".format(symbol, period, days)
        file_tag = hashlib.md5(key.encode("utf-8")).hexdigest()[:10]
        filename = "akshare_{}_{}.json".format(symbol.replace("/", "_"), file_tag)
        return os.path.join(self.cache_dir, filename)

    def _read_cache(self, symbol: str, period: str, days: int) -> Optional[Dict[str, Any]]:
        path = self._cache_path(symbol, period, days)
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except Exception as exc:
            print("[AKShareDataSource] 读取缓存失败: {}".format(exc))
            return None

        fetched_at = payload.get("fetched_at")
        if fetched_at:
            try:
                t = datetime.strptime(fetched_at, "%Y-%m-%d %H:%M:%S")
                if (datetime.now() - t).total_seconds() > self.cache_ttl_days * 86400:
                    return None
            except Exception:
                pass

        return payload.get("data")

    def _write_cache(self, symbol: str, period: str, days: int, data: Dict[str, Any]) -> None:
        path = self._cache_path(symbol, period, days)
        payload = {
            "symbol": symbol,
            "period": period,
            "days": days,
            "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "data": data,
        }
        try:
            os.makedirs(self.cache_dir, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        except Exception as exc:
            print("[AKShareDataSource] 写入缓存失败: {}".format(exc))
