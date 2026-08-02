#!/usr/bin/env python3
"""
多周期数据对齐管道 (Multi-Timeframe Data Pipeline)
==================================================
为「特种兵・威科夫量价自适应策略」提供四级周期数据：
  周线 → 日线 → 60分钟 → 15分钟

核心能力：
  1. 统一拉取四个周期的K线数据
  2. 时间戳对齐：将分钟级数据映射到所属的日线和周线
  3. 数据缓存：避免重复API请求
  4. 递推式特征注入：上级周期特征作为下级周期的上下文

数据格式：遵循 data_bus.create_kline_format 标准
"""

import os
import sys
import json
import time
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field

import numpy as np

# 路径设置
current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)


# ============================================================
# 数据模型
# ============================================================

@dataclass
class AlignedData:
    """
    四级周期对齐后的数据结构

    索引 i 对应 15分钟K线的第 i 根bar。
    每个 bar 同时携带其所属的日线、周线特征。
    60分钟特征也按15分钟对齐（每4根15分钟bar对应1根60分钟bar）。
    """
    symbol: str
    # 15分钟数据（主力信号层，对齐基准）
    m15_dates: List[str] = field(default_factory=list)
    m15_opens: List[float] = field(default_factory=list)
    m15_highs: List[float] = field(default_factory=list)
    m15_lows: List[float] = field(default_factory=list)
    m15_closes: List[float] = field(default_factory=list)
    m15_volumes: List[float] = field(default_factory=list)
    # 映射索引：m15_index → 所属日线bar索引
    m15_to_daily: List[int] = field(default_factory=list)
    # 映射索引：m15_index → 所属周线bar索引
    m15_to_weekly: List[int] = field(default_factory=list)
    # 映射索引：m15_index → 所属60分钟bar索引
    m15_to_h60: List[int] = field(default_factory=list)
    # 日线数据
    daily_dates: List[str] = field(default_factory=list)
    daily_opens: List[float] = field(default_factory=list)
    daily_highs: List[float] = field(default_factory=list)
    daily_lows: List[float] = field(default_factory=list)
    daily_closes: List[float] = field(default_factory=list)
    daily_volumes: List[float] = field(default_factory=list)
    # 60分钟数据
    h60_dates: List[str] = field(default_factory=list)
    h60_opens: List[float] = field(default_factory=list)
    h60_highs: List[float] = field(default_factory=list)
    h60_lows: List[float] = field(default_factory=list)
    h60_closes: List[float] = field(default_factory=list)
    h60_volumes: List[float] = field(default_factory=list)
    # 周线数据
    weekly_dates: List[str] = field(default_factory=list)
    weekly_opens: List[float] = field(default_factory=list)
    weekly_highs: List[float] = field(default_factory=list)
    weekly_lows: List[float] = field(default_factory=list)
    weekly_closes: List[float] = field(default_factory=list)
    weekly_volumes: List[float] = field(default_factory=list)
    # 元数据
    count: int = 0
    fetch_time: str = ""

    def __repr__(self) -> str:
        return (f"AlignedData(symbol={self.symbol}, m15_bars={self.count}, "
                f"daily_bars={len(self.daily_dates)}, "
                f"h60_bars={len(self.h60_dates)}, "
                f"weekly_bars={len(self.weekly_dates)})")


# ============================================================
# 多周期数据管道
# ============================================================

class MultiTimeframePipeline:
    """
    多周期数据对齐管道

    四级周期：
      周线 → 定趋势、定阶段
      日线 → 定结构、定信号
      60分钟 → 定执行、定止损
      15分钟 → 定精准入场、过滤假突破

    对齐策略：
      以15分钟为基准，每根15分钟bar向上查找所属的60分钟、日线、周线bar。
    """

    # 周期配置
    PERIODS = {
        "weekly": {"period": "weekly", "lookback_days": 730, "label": "周线"},
        "daily": {"period": "daily", "lookback_days": 500, "label": "日线"},
        "60min": {"period": "60min", "lookback_days": 120, "label": "60分钟"},
        "15min": {"period": "15min", "lookback_days": 60, "label": "15分钟"},
    }

    def __init__(self, cache_dir: str = None):
        """
        Args:
            cache_dir: 缓存目录，默认 QS_Robot/data/mtf_cache/
        """
        if cache_dir is None:
            cache_dir = os.path.join(os.path.dirname(__file__), "..", "data", "mtf_cache")
        self._cache_dir = cache_dir
        os.makedirs(self._cache_dir, exist_ok=True)
        self._adapter = None

    def _get_adapter(self):
        """延迟初始化数据适配器"""
        if self._adapter is None:
            from core.data_sources.akshare_adapter import AKShareAdapter
            self._adapter = AKShareAdapter()
        return self._adapter

    # --------------------------------------------------------
    # 数据获取
    # --------------------------------------------------------

    def fetch_aligned(self, symbol: str, force_refresh: bool = False) -> AlignedData:
        """
        获取四级周期对齐数据

        Args:
            symbol: 股票代码（如 '510300', '600519'）
            force_refresh: 是否强制刷新缓存

        Returns:
            AlignedData: 对齐后的四级周期数据
        """
        # 尝试读缓存
        if not force_refresh:
            cached = self._read_cache(symbol)
            if cached is not None:
                return cached

        print(f"[MTF-Pipeline] 拉取 {symbol} 四级周期数据...")

        adapter = self._get_adapter()

        # 并行拉取四个周期（实际是顺序的，但可以后续优化为并行）
        weekly_data = self._fetch_or_mock(adapter, symbol, "weekly", 730)
        daily_data = self._fetch_or_mock(adapter, symbol, "daily", 500)
        h60_data = self._fetch_or_mock(adapter, symbol, "60min", 120)
        m15_data = self._fetch_or_mock(adapter, symbol, "15min", 60)

        # 对齐
        aligned = self._align(symbol, m15_data, h60_data, daily_data, weekly_data)

        # 写缓存
        self._write_cache(symbol, aligned)

        print(f"[MTF-Pipeline] {symbol} 数据就绪: {aligned}")
        return aligned

    def _fetch_or_mock(self, adapter, symbol: str, period: str, days: int) -> Dict:
        """拉取数据，失败时降级为管道自有的模拟数据"""
        result = adapter.get_kline(symbol, period, days)
        # 如果数据源是mock（AKShare不可用），使用管道自己的模拟数据以保证日期格式一致
        if result is None or result.get("count", 0) == 0 or result.get("source", "").startswith("akshare-Mock"):
            print(f"[MTF-Pipeline] {period} 使用管道模拟数据")
            result = self._generate_mock(symbol, period, days)
        return result

    def _generate_mock(self, symbol: str, period: str, days: int) -> Dict:
        """生成模拟K线数据（用于测试和降级）

        关键：所有周期的模拟数据使用相同的日期范围，确保时间对齐。
        """
        from core.data_bus import create_kline_format

        np.random.seed(hash(symbol + period) % 2**31)

        base_price = 4.0
        now = datetime.now()

        if period == "weekly":
            n = max(30, days // 7)
            freq = timedelta(weeks=1)
        elif period == "daily":
            n = max(100, days)
            freq = timedelta(days=1)
        elif period == "60min":
            # 60分钟：覆盖最近60天，每天4根
            n = max(100, days * 4)
            freq = timedelta(hours=1)
        else:  # 15min
            # 15分钟：覆盖最近60天，每天16根
            n = max(200, days * 16)
            freq = timedelta(minutes=15)

        dates = []
        opens, highs, lows, closes, volumes = [], [], [], [], []
        price = base_price

        for i in range(n):
            if period == "weekly":
                d = now - timedelta(weeks=n - i)
            elif period == "daily":
                d = now - timedelta(days=n - i)
            elif period == "60min":
                d = now - timedelta(hours=n - i)
            else:
                d = now - timedelta(minutes=(n - i) * 15)

            dates.append(d.strftime("%Y-%m-%d %H:%M:%S"))

            ret = np.random.normal(0.0002, 0.015)
            price = price * (1 + ret)
            o = price * (1 + np.random.normal(0, 0.003))
            c = price
            h = max(o, c) * (1 + abs(np.random.normal(0, 0.005)))
            l = min(o, c) * (1 - abs(np.random.normal(0, 0.005)))
            v = abs(np.random.normal(1e7, 3e6))

            opens.append(round(o, 3))
            highs.append(round(h, 3))
            lows.append(round(l, 3))
            closes.append(round(c, 3))
            volumes.append(round(v, 0))

        return create_kline_format(
            symbol=symbol, period=period,
            dates=dates, opens=opens, highs=highs,
            lows=lows, closes=closes, volumes=volumes,
            source="mock"
        )

    # --------------------------------------------------------
    # 时间对齐核心
    # --------------------------------------------------------

    def _align(self, symbol: str, m15: Dict, h60: Dict,
               daily: Dict, weekly: Dict) -> AlignedData:
        """
        四级周期对齐

        策略：
          1. 以15分钟为基准线
          2. 每根15分钟bar，找到其所属的60分钟、日线、周线bar
          3. 时间匹配规则：15分钟bar的时间戳 在上级周期bar的时间范围内
        """
        result = AlignedData(symbol=symbol)
        result.fetch_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 填充15分钟数据
        result.m15_dates = m15.get("dates", [])
        result.m15_opens = m15.get("opens", [])
        result.m15_highs = m15.get("highs", [])
        result.m15_lows = m15.get("lows", [])
        result.m15_closes = m15.get("closes", [])
        result.m15_volumes = m15.get("volumes", [])
        result.count = len(result.m15_dates)

        # 填充日线数据
        result.daily_dates = daily.get("dates", [])
        result.daily_opens = daily.get("opens", [])
        result.daily_highs = daily.get("highs", [])
        result.daily_lows = daily.get("lows", [])
        result.daily_closes = daily.get("closes", [])
        result.daily_volumes = daily.get("volumes", [])

        # 填充60分钟数据
        result.h60_dates = h60.get("dates", [])
        result.h60_opens = h60.get("opens", [])
        result.h60_highs = h60.get("highs", [])
        result.h60_lows = h60.get("lows", [])
        result.h60_closes = h60.get("closes", [])
        result.h60_volumes = h60.get("volumes", [])

        # 填充周线数据
        result.weekly_dates = weekly.get("dates", [])
        result.weekly_opens = weekly.get("opens", [])
        result.weekly_highs = weekly.get("highs", [])
        result.weekly_lows = weekly.get("lows", [])
        result.weekly_closes = weekly.get("closes", [])
        result.weekly_volumes = weekly.get("volumes", [])

        # 构建映射索引
        result.m15_to_daily = self._build_time_mapping(
            result.m15_dates, result.daily_dates, "daily")
        result.m15_to_weekly = self._build_time_mapping(
            result.m15_dates, result.weekly_dates, "weekly")
        result.m15_to_h60 = self._build_time_mapping(
            result.m15_dates, result.h60_dates, "60min")

        return result

    def _build_time_mapping(self, child_dates: List[str],
                            parent_dates: List[str],
                            parent_period: str) -> List[int]:
        """
        构建子周期→父周期的索引映射

        规则：
          - 日线：15分钟bar的日期与日线bar的日期相同
          - 周线：15分钟bar所在周与周线bar所在周相同
          - 60分钟：15分钟bar的小时（向下取整到整点）匹配60分钟bar

        Returns:
            List[int]: child_dates[i] 对应的 parent_dates 索引
        """
        if not child_dates or not parent_dates:
            return [-1] * len(child_dates)

        mapping = []
        parent_dts = [self._parse_datetime(d) for d in parent_dates]

        for child_date in child_dates:
            child_dt = self._parse_datetime(child_date)
            if child_dt is None:
                mapping.append(-1)
                continue

            best_idx = -1

            if parent_period == "daily":
                # 同一天
                child_day = child_dt.date()
                for i, pdt in enumerate(parent_dts):
                    if pdt and pdt.date() == child_day:
                        best_idx = i
                        break

            elif parent_period == "weekly":
                # 同一周（ISO周）
                child_week = child_dt.isocalendar()[1]
                child_year = child_dt.isocalendar()[0]
                for i, pdt in enumerate(parent_dts):
                    if pdt and pdt.isocalendar()[1] == child_week and \
                       pdt.isocalendar()[0] == child_year:
                        best_idx = i
                        break

            elif parent_period == "60min":
                # 同一小时（向下取整）
                child_hour = child_dt.replace(minute=0, second=0, microsecond=0)
                for i, pdt in enumerate(parent_dts):
                    if pdt:
                        parent_hour = pdt.replace(minute=0, second=0, microsecond=0)
                        if child_hour == parent_hour:
                            best_idx = i
                            break

            mapping.append(best_idx)

        return mapping

    def _parse_datetime(self, date_str: str) -> Optional[datetime]:
        """解析多种日期时间格式"""
        if not date_str:
            return None
        formats = [
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d",
            "%Y%m%d",
            "%Y/%m/%d",
        ]
        for fmt in formats:
            try:
                return datetime.strptime(str(date_str).strip(), fmt)
            except ValueError:
                continue
        return None

    # --------------------------------------------------------
    # 便捷数据访问
    # --------------------------------------------------------

    def get_daily_context(self, aligned: AlignedData, m15_idx: int) -> Dict[str, float]:
        """
        获取指定15分钟bar所属的日线上下文

        返回该日线bar的OHLCV + 当日已走过的15分钟统计
        """
        daily_idx = aligned.m15_to_daily[m15_idx] if m15_idx < len(aligned.m15_to_daily) else -1
        if daily_idx < 0 or daily_idx >= len(aligned.daily_closes):
            return {}

        # 当日已走过的15分钟bar统计
        same_day_m15 = [i for i, di in enumerate(aligned.m15_to_daily)
                        if di == daily_idx and i <= m15_idx]

        intraday_high = max(aligned.m15_highs[i] for i in same_day_m15) if same_day_m15 else 0
        intraday_low = min(aligned.m15_lows[i] for i in same_day_m15) if same_day_m15 else 0
        intraday_vol = sum(aligned.m15_volumes[i] for i in same_day_m15) if same_day_m15 else 0

        return {
            "daily_open": aligned.daily_opens[daily_idx],
            "daily_high": aligned.daily_highs[daily_idx],
            "daily_low": aligned.daily_lows[daily_idx],
            "daily_close": aligned.daily_closes[daily_idx],
            "daily_volume": aligned.daily_volumes[daily_idx],
            "intraday_high": intraday_high,
            "intraday_low": intraday_low,
            "intraday_volume": intraday_vol,
            "intraday_bar_count": len(same_day_m15),
            "is_first_bar": (same_day_m15[0] == m15_idx if same_day_m15 else False),
        }

    def get_weekly_context(self, aligned: AlignedData, m15_idx: int) -> Dict[str, float]:
        """获取指定15分钟bar所属的周线上下文"""
        weekly_idx = aligned.m15_to_weekly[m15_idx] if m15_idx < len(aligned.m15_to_weekly) else -1
        if weekly_idx < 0 or weekly_idx >= len(aligned.weekly_closes):
            return {}
        return {
            "weekly_open": aligned.weekly_opens[weekly_idx],
            "weekly_high": aligned.weekly_highs[weekly_idx],
            "weekly_low": aligned.weekly_lows[weekly_idx],
            "weekly_close": aligned.weekly_closes[weekly_idx],
            "weekly_volume": aligned.weekly_volumes[weekly_idx],
        }

    def get_h60_context(self, aligned: AlignedData, m15_idx: int) -> Dict[str, float]:
        """获取指定15分钟bar所属的60分钟上下文"""
        h60_idx = aligned.m15_to_h60[m15_idx] if m15_idx < len(aligned.m15_to_h60) else -1
        if h60_idx < 0 or h60_idx >= len(aligned.h60_closes):
            return {}
        return {
            "h60_open": aligned.h60_opens[h60_idx],
            "h60_high": aligned.h60_highs[h60_idx],
            "h60_low": aligned.h60_lows[h60_idx],
            "h60_close": aligned.h60_closes[h60_idx],
            "h60_volume": aligned.h60_volumes[h60_idx],
        }

    # --------------------------------------------------------
    # 缓存管理
    # --------------------------------------------------------

    def _cache_path(self, symbol: str) -> str:
        key = hashlib.md5(f"mtf_{symbol}".encode()).hexdigest()[:12]
        return os.path.join(self._cache_dir, f"{key}.json")

    def _read_cache(self, symbol: str) -> Optional[AlignedData]:
        path = self._cache_path(symbol)
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            # 检查缓存时效（日线数据24小时有效，分钟线数据4小时有效）
            cached_time = raw.get("fetch_time", "")
            if cached_time:
                try:
                    ct = datetime.strptime(cached_time, "%Y-%m-%d %H:%M:%S")
                    if (datetime.now() - ct).total_seconds() > 4 * 3600:
                        return None  # 过期
                except ValueError:
                    pass
            return self._dict_to_aligned(raw)
        except Exception as e:
            print(f"[MTF-Pipeline] 缓存读取失败: {e}")
            return None

    def _write_cache(self, symbol: str, aligned: AlignedData):
        path = self._cache_path(symbol)
        try:
            raw = self._aligned_to_dict(aligned)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(raw, f, ensure_ascii=False)
        except Exception as e:
            print(f"[MTF-Pipeline] 缓存写入失败: {e}")

    def _aligned_to_dict(self, a: AlignedData) -> Dict:
        return {
            "symbol": a.symbol,
            "m15_dates": a.m15_dates, "m15_opens": a.m15_opens,
            "m15_highs": a.m15_highs, "m15_lows": a.m15_lows,
            "m15_closes": a.m15_closes, "m15_volumes": a.m15_volumes,
            "m15_to_daily": a.m15_to_daily, "m15_to_weekly": a.m15_to_weekly,
            "m15_to_h60": a.m15_to_h60,
            "daily_dates": a.daily_dates, "daily_opens": a.daily_opens,
            "daily_highs": a.daily_highs, "daily_lows": a.daily_lows,
            "daily_closes": a.daily_closes, "daily_volumes": a.daily_volumes,
            "h60_dates": a.h60_dates, "h60_opens": a.h60_opens,
            "h60_highs": a.h60_highs, "h60_lows": a.h60_lows,
            "h60_closes": a.h60_closes, "h60_volumes": a.h60_volumes,
            "weekly_dates": a.weekly_dates, "weekly_opens": a.weekly_opens,
            "weekly_highs": a.weekly_highs, "weekly_lows": a.weekly_lows,
            "weekly_closes": a.weekly_closes, "weekly_volumes": a.weekly_volumes,
            "count": a.count, "fetch_time": a.fetch_time,
        }

    def _dict_to_aligned(self, d: Dict) -> AlignedData:
        return AlignedData(
            symbol=d.get("symbol", ""),
            m15_dates=d.get("m15_dates", []), m15_opens=d.get("m15_opens", []),
            m15_highs=d.get("m15_highs", []), m15_lows=d.get("m15_lows", []),
            m15_closes=d.get("m15_closes", []), m15_volumes=d.get("m15_volumes", []),
            m15_to_daily=d.get("m15_to_daily", []), m15_to_weekly=d.get("m15_to_weekly", []),
            m15_to_h60=d.get("m15_to_h60", []),
            daily_dates=d.get("daily_dates", []), daily_opens=d.get("daily_opens", []),
            daily_highs=d.get("daily_highs", []), daily_lows=d.get("daily_lows", []),
            daily_closes=d.get("daily_closes", []), daily_volumes=d.get("daily_volumes", []),
            h60_dates=d.get("h60_dates", []), h60_opens=d.get("h60_opens", []),
            h60_highs=d.get("h60_highs", []), h60_lows=d.get("h60_lows", []),
            h60_closes=d.get("h60_closes", []), h60_volumes=d.get("h60_volumes", []),
            weekly_dates=d.get("weekly_dates", []), weekly_opens=d.get("weekly_opens", []),
            weekly_highs=d.get("weekly_highs", []), weekly_lows=d.get("weekly_lows", []),
            weekly_closes=d.get("weekly_closes", []), weekly_volumes=d.get("weekly_volumes", []),
            count=d.get("count", 0), fetch_time=d.get("fetch_time", ""),
        )


# ============================================================
# 单例
# ============================================================

_pipeline_instance: Optional[MultiTimeframePipeline] = None


def get_mtf_pipeline() -> MultiTimeframePipeline:
    global _pipeline_instance
    if _pipeline_instance is None:
        _pipeline_instance = MultiTimeframePipeline()
    return _pipeline_instance