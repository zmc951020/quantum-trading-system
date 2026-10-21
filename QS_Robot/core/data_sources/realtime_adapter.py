#!/usr/bin/env python3
"""
免费实时行情数据源适配器 (Tencent / Eastmoney)

- 主源: 腾讯行情 qt.gtimg.cn（批量、无鉴权、盘中实时、国内直连稳定）
- 备源: 东方财富 push2 实时快照（单只，字段需 /100）

统一返回格式:
  {
    "symbol": "600519", "name": "贵州茅台",
    "price": 1309.69, "change_pct": -1.67,
    "open": ..., "high": ..., "low": ..., "prev_close": ...,
    "volume": ..., "amount": ...,
    "time": "2026-10-21 15:00:00", "source": "tencent"
  }
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from core.data_sources.base_adapter import BaseDataSourceAdapter

TENCENT_URL = "https://qt.gtimg.cn/q={codes}"
EASTMONEY_URL = "https://push2.eastmoney.com/api/qt/stock/get"


def to_tencent_code(symbol: str) -> str:
    """6位代码 -> 腾讯市场前缀 (sh/sz)"""
    if symbol.startswith(("6", "9")):
        return "sh" + symbol
    return "sz" + symbol


def to_em_secid(symbol: str) -> str:
    """6位代码 -> 东财 secid (1=沪 0=深)"""
    if symbol.startswith(("6", "9")):
        return "1." + symbol
    return "0." + symbol


class RealtimeAdapter(BaseDataSourceAdapter):
    """腾讯/东财 免费实时行情适配器"""

    name = "realtime"

    def _init(self):
        try:
            import requests  # noqa: F401
            self._available = True
        except ImportError:
            self._available = False

    # --------------------------------------------------------
    # 单只实时
    # --------------------------------------------------------

    def get_realtime(self, symbol: str) -> Optional[Dict[str, Any]]:
        """获取单只股票实时行情（腾讯主源，失败降级东财）"""
        if not symbol:
            return None
        result = self._fetch_tencent([symbol])
        if result:
            return result[symbol]
        return self._fetch_eastmoney(symbol)

    # --------------------------------------------------------
    # 批量实时
    # --------------------------------------------------------

    def get_realtime_batch(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        """批量获取实时行情（腾讯一次请求，最多约50只/次）"""
        if not symbols:
            return {}
        result = self._fetch_tencent(symbols)
        # 单只失败时用东财补齐
        for sym in symbols:
            if sym not in result:
                single = self._fetch_eastmoney(sym)
                if single:
                    result[sym] = single
        return result

    # --------------------------------------------------------
    # 腾讯
    # --------------------------------------------------------

    def _fetch_tencent(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        """腾讯行情: qt.gtimg.cn/q=sh600519,sz000001  (GBK, ~分隔)"""
        import requests
        codes = ",".join(to_tencent_code(s) for s in symbols)
        try:
            r = requests.get(TENCENT_URL.format(codes=codes),
                             headers={"User-Agent": "Mozilla/5.0"},
                             timeout=10)
            r.encoding = "gbk"
        except Exception:
            return {}
        out: Dict[str, Dict[str, Any]] = {}
        for line in r.text.strip().split(";"):
            line = line.strip()
            if not line or "~" not in line:
                continue
            parts = line.split("~")
            if len(parts) < 40:
                continue
            try:
                sym = parts[2]
                out[sym] = {
                    "symbol": sym,
                    "name": parts[1],
                    "price": float(parts[3]) if parts[3] else 0.0,
                    "prev_close": float(parts[4]) if parts[4] else 0.0,
                    "open": float(parts[5]) if parts[5] else 0.0,
                    "volume": int(float(parts[6])) if parts[6] else 0,
                    "high": float(parts[33]) if parts[33] else 0.0,
                    "low": float(parts[34]) if parts[34] else 0.0,
                    "change_pct": float(parts[32]) if parts[32] else 0.0,
                    "amount": float(parts[37]) if parts[37] else 0.0,
                    "time": parts[30] if len(parts) > 30 else "",
                    "source": "tencent",
                }
            except (ValueError, IndexError):
                continue
        return out

    # --------------------------------------------------------
    # 东财（备源，字段 /100）
    # --------------------------------------------------------

    def _fetch_eastmoney(self, symbol: str) -> Optional[Dict[str, Any]]:
        """东财 push2 实时快照 (f43..f170 均放大100倍)"""
        import requests
        params = {
            "secid": to_em_secid(symbol),
            "fields": "f43,f44,f45,f46,f47,f48,f57,f58,f60,f86,f170",
        }
        try:
            r = requests.get(EASTMONEY_URL, params=params,
                             headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
            d = r.json().get("data") or {}
        except Exception:
            return None
        if not d:
            return None
        def div100(v):
            try:
                return float(v) / 100.0
            except (TypeError, ValueError):
                return 0.0
        return {
            "symbol": symbol,
            "name": str(d.get("f58") or ""),
            "price": div100(d.get("f43")),
            "prev_close": div100(d.get("f60")),
            "open": div100(d.get("f46")),
            "high": div100(d.get("f44")),
            "low": div100(d.get("f45")),
            "change_pct": div100(d.get("f170")),
            "volume": int(float(d.get("f47") or 0)),
            "amount": float(d.get("f48") or 0),
            "time": str(d.get("f86") or ""),
            "source": "eastmoney",
        }
