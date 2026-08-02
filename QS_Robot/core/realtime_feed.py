#!/usr/bin/env python3
"""
实时行情推送 — 多源行情聚合与分钟级推送
===========================================
支持：
- akshare 实时行情（新浪/东方财富源）
- 腾讯行情 WebSocket
- 多标的并发订阅
- 行情缓存与去重
- 断线重连

券商密钥未就绪时，使用免费公开行情源。
"""
import logging
import threading
import time
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable, Any, Set
from dataclasses import dataclass, field
from collections import deque

logger = logging.getLogger(__name__)


@dataclass
class Quote:
    """实时行情数据"""
    symbol: str
    name: str = ""
    price: float = 0.0
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    pre_close: float = 0.0
    volume: float = 0.0
    amount: float = 0.0
    change_pct: float = 0.0
    bid1: float = 0.0
    bid1_vol: int = 0
    ask1: float = 0.0
    ask1_vol: int = 0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    source: str = ""


class RealtimeFeed:
    """实时行情聚合器"""

    def __init__(self, symbols: List[str] = None, interval_sec: float = 3.0):
        self._symbols: Set[str] = set(symbols or [])
        self._interval = max(interval_sec, 1.0)
        self._quotes: Dict[str, Quote] = {}
        self._history: Dict[str, deque] = {}  # symbol -> deque of (timestamp, price)
        self._lock = threading.RLock()
        self._running = False
        self._thread: Optional[threading.Thread] = None

        # 回调
        self._on_quote: Optional[Callable] = None
        self._on_error: Optional[Callable] = None

        # 统计
        self._stats = {
            "total_ticks": 0,
            "last_update": None,
            "errors": 0,
            "source": "unknown",
        }

        logger.info(f"[RealtimeFeed] 初始化, 订阅 {len(self._symbols)} 个标的")

    def subscribe(self, symbols: List[str]):
        with self._lock:
            self._symbols.update(symbols)
            logger.info(f"[RealtimeFeed] 新增订阅: {symbols}")

    def unsubscribe(self, symbols: List[str]):
        with self._lock:
            self._symbols.difference_update(symbols)

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="RealtimeFeed")
        self._thread.start()
        logger.info("[RealtimeFeed] 行情推送已启动")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("[RealtimeFeed] 行情推送已停止")

    def _run_loop(self):
        """主循环 — 定时拉取行情"""
        while self._running:
            try:
                self._fetch_quotes()
                self._stats["total_ticks"] += 1
                self._stats["last_update"] = datetime.now().isoformat()
            except Exception as e:
                self._stats["errors"] += 1
                logger.error(f"[RealtimeFeed] 行情拉取异常: {e}")
                if self._on_error:
                    self._on_error(str(e))

            time.sleep(self._interval)

    def _fetch_quotes(self):
        """拉取最新行情 — 多源fallback"""
        with self._lock:
            symbols = list(self._symbols)

        if not symbols:
            return

        quotes = self._fetch_from_akshare(symbols)
        if not quotes:
            quotes = self._fetch_from_tencent(symbols)

        if not quotes:
            logger.warning("[RealtimeFeed] 所有行情源不可用")
            return

        with self._lock:
            for q in quotes:
                old = self._quotes.get(q.symbol)
                self._quotes[q.symbol] = q

                # 维护历史价格
                if q.symbol not in self._history:
                    self._history[q.symbol] = deque(maxlen=500)
                self._history[q.symbol].append((q.timestamp, q.price))

                # 价格变动才回调
                if old is None or abs(old.price - q.price) > 0.001:
                    if self._on_quote:
                        try:
                            self._on_quote(q)
                        except Exception as e:
                            logger.error(f"[RealtimeFeed] 回调异常: {e}")

            self._stats["source"] = quotes[0].source if quotes else "unknown"

    def _fetch_from_akshare(self, symbols: List[str]) -> List[Quote]:
        """通过 akshare 获取实时行情（东方财富源）"""
        try:
            import akshare as ak

            # 批量获取实时行情
            df = ak.stock_zh_a_spot_em()
            if df is None or df.empty:
                return []

            quotes = []
            symbol_map = {s: s for s in symbols}

            for _, row in df.iterrows():
                code = str(row.get("代码", ""))
                if code not in symbol_map:
                    continue

                q = Quote(
                    symbol=code,
                    name=str(row.get("名称", "")),
                    price=float(row.get("最新价", 0) or 0),
                    open=float(row.get("今开", 0) or 0),
                    high=float(row.get("最高", 0) or 0),
                    low=float(row.get("最低", 0) or 0),
                    pre_close=float(row.get("昨收", 0) or 0),
                    volume=float(row.get("成交量", 0) or 0),
                    amount=float(row.get("成交额", 0) or 0),
                    change_pct=float(row.get("涨跌幅", 0) or 0),
                    source="akshare_em",
                )
                quotes.append(q)

            return quotes
        except ImportError:
            logger.debug("[RealtimeFeed] akshare 不可用")
            return []
        except Exception as e:
            logger.warning(f"[RealtimeFeed] akshare 拉取失败: {e}")
            return []

    def _fetch_from_tencent(self, symbols: List[str]) -> List[Quote]:
        """通过腾讯行情接口获取实时行情（无需API密钥）"""
        try:
            import requests

            # 转换代码格式 sh600000 / sz000001
            tencent_codes = []
            for s in symbols:
                code = s.replace(".SH", "").replace(".SZ", "").replace("sh", "").replace("sz", "")
                if s.startswith("6") or "SH" in s:
                    tencent_codes.append(f"sh{code}")
                else:
                    tencent_codes.append(f"sz{code}")

            if not tencent_codes:
                return []

            url = f"http://qt.gtimg.cn/q={','.join(tencent_codes)}"
            r = requests.get(url, timeout=5)
            r.encoding = "gbk"

            quotes = []
            for line in r.text.strip().split("\n"):
                if not line.startswith("v_"):
                    continue
                # 解析腾讯行情格式: v_sh600000="1~平安银行~000001~..."
                parts = line.split("~")
                if len(parts) < 10:
                    continue

                try:
                    # 提取原始代码
                    name_part = line.split('="')[1].split("~")
                    q = Quote(
                        symbol=name_part[2] if len(name_part) > 2 else "",
                        name=name_part[1] if len(name_part) > 1 else "",
                        price=float(parts[3]) if parts[3] else 0,
                        pre_close=float(parts[4]) if parts[4] else 0,
                        open=float(parts[5]) if parts[5] else 0,
                        volume=float(parts[6]) if parts[6] else 0,
                        change_pct=float(parts[32]) if len(parts) > 32 and parts[32] else 0,
                        high=float(parts[33]) if len(parts) > 33 and parts[33] else 0,
                        low=float(parts[34]) if len(parts) > 34 and parts[34] else 0,
                        source="tencent",
                    )
                    quotes.append(q)
                except (ValueError, IndexError):
                    continue

            return quotes
        except ImportError:
            return []
        except Exception as e:
            logger.warning(f"[RealtimeFeed] 腾讯行情拉取失败: {e}")
            return []

    # ========== 查询接口 ==========

    def get_quote(self, symbol: str) -> Optional[Quote]:
        with self._lock:
            return self._quotes.get(symbol)

    def get_all_quotes(self) -> Dict[str, Quote]:
        with self._lock:
            return dict(self._quotes)

    def get_price_history(self, symbol: str, n: int = 20) -> List[tuple]:
        with self._lock:
            if symbol in self._history:
                return list(self._history[symbol])[-n:]
            return []

    def get_stats(self) -> Dict:
        with self._lock:
            return dict(self._stats)

    def set_callbacks(self, on_quote=None, on_error=None):
        self._on_quote = on_quote
        self._on_error = on_error


# 全局单例
_feed_instance: Optional[RealtimeFeed] = None
_feed_lock = threading.Lock()


def get_realtime_feed(symbols: List[str] = None) -> RealtimeFeed:
    global _feed_instance
    with _feed_lock:
        if _feed_instance is None:
            _feed_instance = RealtimeFeed(symbols=symbols)
        elif symbols:
            _feed_instance.subscribe(symbols)
        return _feed_instance