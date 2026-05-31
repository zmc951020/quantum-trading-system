#!/usr/bin/env python3
"""
Aurora量化交易系统 — 券商管理器 & 股票池 & 技术分析桥接

核心编排层，负责：
  1. BrokerManager — 多券商动态注册/切换/健康监控
  2. StockPool     — 股票池管理（候选/精选/黑名单）
  3. AnalysisBridge — 技术分析与券商间的无缝桥接

技术分析 → AnalysisBridge → BrokerManager → BrokerInterface → 券商API

使用方式：
    from broker_manager import BrokerManager, StockPool, AnalysisBridge

    # 初始化管理器
    mgr = BrokerManager()

    # 注册券商
    mgr.register("xbk", XbkAdapter(simulated=True))
    mgr.register("zhongtai", ZhongTaiAdapter(simulated=True))

    # 切换到指定券商
    mgr.switch_to("xbk")

    # 创建股票池
    pool = StockPool(mgr)
    pool.add_candidates(["000001.SZ", "600519.SH"])

    # 技术分析桥接
    bridge = AnalysisBridge(mgr, pool)
    signals = bridge.scan_and_rank(top_n=10)
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from broker_interface import (
    BrokerInterface,
    BrokerResult,
    BrokerType,
    ConnectionState,
    KlineData,
    TickerData,
    normalize_symbol,
    get_market_from_symbol,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# BrokerManager — 多券商注册与动态切换
# ═══════════════════════════════════════════════════════════════

class BrokerManager:
    """
    券商管理器

    功能：
      - 注册/注销多个券商适配器
      - 运行时动态切换券商
      - 切换事件回调通知
      - 券商健康状态监控
      - 透明代理：对上层表现为单一券商接口
    """

    def __init__(self):
        self._brokers: Dict[str, BrokerInterface] = {}
        self._active_key: Optional[str] = None
        self._active: Optional[BrokerInterface] = None
        self._switch_listeners: List[Callable] = []
        self._health_status: Dict[str, dict] = {}

    # ── 注册管理 ────────────────────────────────────────

    def register(self, key: str, broker: BrokerInterface) -> None:
        """
        注册券商适配器

        Args:
            key:     券商标识（如 'xbk', 'zhongtai', 'simulated'）
            broker:  实现了 BrokerInterface 的券商适配器
        """
        if not isinstance(broker, BrokerInterface):
            raise TypeError(f"券商适配器必须实现 BrokerInterface，收到: {type(broker)}")
        self._brokers[key] = broker
        logger.info(f"券商已注册: {key} ({broker.broker_type.value})")

        # 如果是第一个注册的，自动设为活跃
        if self._active is None:
            self.switch_to(key)

    def unregister(self, key: str) -> None:
        """注销券商"""
        if key in self._brokers:
            if self._active_key == key:
                self._active = None
                self._active_key = None
            del self._brokers[key]
            logger.info(f"券商已注销: {key}")

    @property
    def brokers(self) -> Dict[str, BrokerInterface]:
        """获取所有已注册券商"""
        return dict(self._brokers)

    @property
    def active_broker(self) -> Optional[BrokerInterface]:
        """获取当前活跃券商"""
        return self._active

    @property
    def active_key(self) -> Optional[str]:
        """获取当前活跃券商标识"""
        return self._active_key

    # ── 切换管理 ────────────────────────────────────────

    def switch_to(self, key: str) -> BrokerResult:
        """
        切换到指定券商

        Args:
            key: 券商标识

        Returns:
            BrokerResult
        """
        if key not in self._brokers:
            return BrokerResult.fail(f"券商未注册: {key}。可用: {list(self._brokers.keys())}")

        old_key = self._active_key
        old_broker = self._active

        new_broker = self._brokers[key]

        # 断开旧连接
        if old_broker and old_broker.connection_state == ConnectionState.CONNECTED:
            old_broker.disconnect()

        # 连接新券商
        result = new_broker.connect()
        if not result.success:
            logger.error(f"券商 {key} 连接失败: {result.message}")
            return result

        self._active_key = key
        self._active = new_broker
        logger.info(f"券商已切换: {old_key or '(无)'} → {key} ({new_broker.broker_type.value})")

        # 通知监听器
        for listener in self._switch_listeners:
            try:
                listener(old_key, key, old_broker, new_broker)
            except Exception as e:
                logger.warning(f"切换监听器异常: {e}")

        return BrokerResult.ok({
            "from": old_key,
            "to": key,
            "broker_type": new_broker.broker_type.value,
            "broker_info": new_broker.get_broker_info(),
        })

    def add_switch_listener(self, listener: Callable) -> None:
        """
        添加切换事件监听器

        Args:
            listener: 回调函数 f(from_key, to_key, old_broker, new_broker)
        """
        self._switch_listeners.append(listener)

    def remove_switch_listener(self, listener: Callable) -> None:
        """移除切换事件监听器"""
        if listener in self._switch_listeners:
            self._switch_listeners.remove(listener)

    # ── 健康检查 ────────────────────────────────────────

    def check_all_health(self) -> Dict[str, dict]:
        """检查所有已注册券商的健康状态"""
        for key, broker in self._brokers.items():
            try:
                result = broker.health_check()
                self._health_status[key] = {
                    "healthy": result.success,
                    "data": result.data if result.success else {"error": result.message},
                    "checked_at": datetime.now().isoformat(),
                }
            except Exception as e:
                self._health_status[key] = {
                    "healthy": False,
                    "error": str(e),
                    "checked_at": datetime.now().isoformat(),
                }
        return dict(self._health_status)

    # ── 代理方法（透明转发给活跃券商） ──────────────────

    def _ensure_active(self) -> BrokerInterface:
        """确保有活跃券商，否则抛出异常"""
        if self._active is None:
            raise RuntimeError("没有活跃券商。请先 register() 并 switch_to()。")
        if self._active.connection_state != ConnectionState.CONNECTED:
            self._active.connect()
        return self._active

    def get_ticker(self, symbol: str) -> BrokerResult:
        return self._ensure_active().get_ticker(symbol)

    def get_kline(self, symbol: str, interval: str = "1d", limit: int = 200,
                  start_date: Optional[str] = None, end_date: Optional[str] = None) -> BrokerResult:
        return self._ensure_active().get_kline(symbol, interval, limit, start_date, end_date)

    def get_batch_tickers(self, symbols: List[str]) -> BrokerResult:
        return self._ensure_active().get_batch_tickers(symbols)

    def get_account(self) -> BrokerResult:
        return self._ensure_active().get_account()

    def get_positions(self) -> BrokerResult:
        return self._ensure_active().get_positions()

    def place_order(self, *args, **kwargs) -> BrokerResult:
        return self._ensure_active().place_order(*args, **kwargs)

    def cancel_order(self, order_id: str) -> BrokerResult:
        return self._ensure_active().cancel_order(order_id)

    def get_order(self, order_id: str) -> BrokerResult:
        return self._ensure_active().get_order(order_id)

    def get_orders(self, *args, **kwargs) -> BrokerResult:
        return self._ensure_active().get_orders(*args, **kwargs)

    def get_broker_info(self) -> Dict[str, Any]:
        return self._ensure_active().get_broker_info()


# ═══════════════════════════════════════════════════════════════
# StockPool — 股票池管理
# ═══════════════════════════════════════════════════════════════

@dataclass
class StockInfo:
    """股票元信息"""
    symbol: str
    name: str = ""
    market: str = ""          # SH / SZ / HK
    sector: str = ""          # 行业板块
    market_cap: float = 0.0   # 总市值（亿元）
    pe_ratio: float = 0.0     # 市盈率
    pb_ratio: float = 0.0     # 市净率
    volume_ratio: float = 0.0 # 量比
    tags: List[str] = field(default_factory=list)  # 自定义标签

    def __hash__(self):
        return hash(self.symbol)

    def __eq__(self, other):
        if isinstance(other, StockInfo):
            return self.symbol == other.symbol
        return False


class StockPool:
    """
    股票池管理器

    三级股票池：
      - candidates（候选池）：所有值得关注的股票
      - selected  （精选池）：经过筛选的优质股票
      - blacklist （黑名单）：绝对不能交易的股票

    使用方式：
        pool = StockPool(broker_manager)
        pool.add_candidates(["000001.SZ", "600519.SH"])
        pool.promote_to_selected("000001.SZ")
        pool.blacklist_add("000002.SZ")
    """

    def __init__(self, broker_manager: BrokerManager, max_workers: int = 10):
        self._broker = broker_manager
        self._candidates: Dict[str, StockInfo] = {}
        self._selected: Dict[str, StockInfo] = {}
        self._blacklist: set = set()
        self._max_workers = max_workers

    # ── 候选池操作 ──────────────────────────────────────

    @property
    def candidates(self) -> List[StockInfo]:
        return list(self._candidates.values())

    def add_candidates(self, symbols: List[str]) -> int:
        """批量添加候选股票"""
        added = 0
        for sym in symbols:
            sym = normalize_symbol(sym)
            if sym in self._blacklist:
                continue
            if sym not in self._candidates:
                self._candidates[sym] = StockInfo(
                    symbol=sym,
                    market=get_market_from_symbol(sym),
                )
                added += 1
        logger.info(f"候选池新增 {added} 只股票，总计 {len(self._candidates)} 只")
        return added

    def remove_from_candidates(self, symbols: List[str]) -> int:
        """从候选池移除"""
        removed = 0
        for sym in symbols:
            sym = normalize_symbol(sym)
            if sym in self._candidates:
                del self._candidates[sym]
                removed += 1
        return removed

    def clear_candidates(self) -> None:
        """清空候选池"""
        self._candidates.clear()
        logger.info("候选池已清空")

    # ── 精选池操作 ──────────────────────────────────────

    @property
    def selected(self) -> List[StockInfo]:
        return list(self._selected.values())

    def promote_to_selected(self, symbol: str) -> bool:
        """将候选池中的股票提升到精选池"""
        sym = normalize_symbol(symbol)
        if sym in self._blacklist:
            logger.warning(f"股票 {sym} 在黑名单中，无法提升")
            return False
        if sym in self._candidates:
            self._selected[sym] = self._candidates[sym]
            return True
        logger.warning(f"股票 {sym} 不在候选池中")
        return False

    def batch_promote(self, symbols: List[str]) -> int:
        """批量提升到精选池"""
        promoted = 0
        for s in symbols:
            if self.promote_to_selected(s):
                promoted += 1
        return promoted

    def demote_from_selected(self, symbol: str) -> bool:
        """从精选池降级回收选池"""
        sym = normalize_symbol(symbol)
        if sym in self._selected:
            self._candidates[sym] = self._selected.pop(sym)
            return True
        return False

    def clear_selected(self) -> None:
        """清空精选池"""
        self._selected.clear()
        logger.info("精选池已清空")

    # ── 黑名单操作 ──────────────────────────────────────

    @property
    def blacklist(self) -> List[str]:
        return list(self._blacklist)

    def blacklist_add(self, symbols: List[str]) -> int:
        """添加黑名单"""
        added = 0
        for sym in symbols:
            sym = normalize_symbol(sym)
            if sym not in self._blacklist:
                self._blacklist.add(sym)
                # 从候选和精选中移除
                self._candidates.pop(sym, None)
                self._selected.pop(sym, None)
                added += 1
        return added

    def blacklist_remove(self, symbols: List[str]) -> int:
        """移除黑名单"""
        removed = 0
        for sym in symbols:
            sym = normalize_symbol(sym)
            if sym in self._blacklist:
                self._blacklist.remove(sym)
                removed += 1
        return removed

    def is_blacklisted(self, symbol: str) -> bool:
        """检查是否在黑名单"""
        return normalize_symbol(symbol) in self._blacklist

    # ── 查询与过滤 ──────────────────────────────────────

    def find(self, symbol: str) -> Optional[StockInfo]:
        """查找股票"""
        sym = normalize_symbol(symbol)
        return self._selected.get(sym) or self._candidates.get(sym)

    def get_all_symbols(self) -> List[str]:
        """获取所有标的代码（候选+精选，排除黑名单）"""
        symbols = list(self._candidates.keys()) + list(self._selected.keys())
        return sorted(set(symbols))

    def filter_by_sector(self, sector: str, pool: str = "all") -> List[StockInfo]:
        """按板块过滤"""
        if pool == "selected":
            source = list(self._selected.values())
        elif pool == "candidates":
            source = list(self._candidates.values())
        else:
            source = list(self._candidates.values()) + list(self._selected.values())
        return [s for s in source if s.sector == sector]

    # ── 批量行情获取 ────────────────────────────────────

    def fetch_all_tickers(self, pool: str = "selected") -> List[TickerData]:
        """
        获取股票池中所有股票的实时行情

        Args:
            pool: 'selected' / 'candidates' / 'all'
        """
        if pool == "selected":
            symbols = list(self._selected.keys())
        elif pool == "candidates":
            symbols = list(self._candidates.keys())
        else:
            symbols = list(set(self._candidates.keys()) | set(self._selected.keys()))

        if not symbols:
            return []

        result = self._broker.get_batch_tickers(symbols)
        return result.data if result.success else []

    # ── 统计 ────────────────────────────────────────────

    def stats(self) -> Dict[str, Any]:
        return {
            "candidates_count": len(self._candidates),
            "selected_count": len(self._selected),
            "blacklist_count": len(self._blacklist),
            "total_available": len(self._candidates) + len(self._selected),
            "sectors": self._get_sector_distribution(),
        }

    def _get_sector_distribution(self) -> Dict[str, int]:
        dist: Dict[str, int] = {}
        for s in list(self._candidates.values()) + list(self._selected.values()):
            if s.sector:
                dist[s.sector] = dist.get(s.sector, 0) + 1
        return dist


# ═══════════════════════════════════════════════════════════════
# AnalysisBridge — 技术分析与券商间的无缝桥接
# ═══════════════════════════════════════════════════════════════

@dataclass
class AnalysisSignal:
    """技术分析信号"""
    symbol: str
    name: str = ""
    score: float = 0.0            # 综合评分 (0~100)
    trend: str = "neutral"        # bullish / bearish / neutral
    indicators: Dict[str, Any] = field(default_factory=dict)
    # 具体信号
    macd_signal: str = ""         # golden_cross / death_cross / divergence
    rsi_value: float = 50.0
    ma_arrangement: str = ""      # bullish_aligned / bearish_aligned / messy
    volume_signal: str = ""       # volume_surge / volume_shrink / normal
    support_level: float = 0.0
    resistance_level: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "name": self.name,
            "score": self.score,
            "trend": self.trend,
            "macd_signal": self.macd_signal,
            "rsi_value": self.rsi_value,
            "ma_arrangement": self.ma_arrangement,
            "volume_signal": self.volume_signal,
            "support": self.support_level,
            "resistance": self.resistance_level,
        }


class AnalysisBridge:
    """
    技术分析与券商间的桥接层

    职责：
      1. 从券商获取 K 线数据 → 喂给 technical_analyzer
      2. 对股票池批量扫描 → 生成技术信号
      3. 综合评分 → 排序 → 返回交易推荐
      4. 按信号触发条件 → 通过券商执行交易

    使用方式：
        bridge = AnalysisBridge(broker_manager, stock_pool)
        top_picks = bridge.scan_and_rank(top_n=10)
    """

    # ── 评分权重 ────────────────────────────────────────

    WEIGHT_TREND = 25       # 趋势指标权重
    WEIGHT_MOMENTUM = 25    # 动量指标权重
    WEIGHT_VOLUME = 20      # 成交量权重
    WEIGHT_VOLATILITY = 15  # 波动率权重
    WEIGHT_PATTERN = 15     # 形态识别权重

    def __init__(self, broker_manager: BrokerManager, stock_pool: StockPool,
                 max_workers: int = 8):
        self._broker = broker_manager
        self._pool = stock_pool
        self._max_workers = max_workers
        self._analyzer = None  # 延迟加载 technical_analyzer

        # 信号缓存
        self._last_signals: List[AnalysisSignal] = []
        self._last_scan_time: Optional[datetime] = None

        logger.info("AnalysisBridge 初始化完成")

    @property
    def _ta(self):
        """延迟加载技术分析器"""
        if self._analyzer is None:
            try:
                from technical_analyzer import TechnicalAnalyzer
                self._analyzer = TechnicalAnalyzer()
            except ImportError:
                logger.error("无法加载 technical_analyzer，使用内置简易分析")
                self._analyzer = _SimpleAnalyzer()
        return self._analyzer

    # ── 核心扫描 ────────────────────────────────────────

    def scan_and_rank(self, pool: str = "selected", top_n: int = 10,
                      min_score: float = 50.0) -> List[AnalysisSignal]:
        """
        扫描股票池，生成技术评分并排序

        Args:
            pool:      'selected' / 'candidates' / 'all'
            top_n:     返回前N只
            min_score: 最低评分阈值

        Returns:
            评分最高的信号列表
        """
        symbols = self._pool.get_all_symbols() if pool == "all" else \
                  [s.symbol for s in (self._pool.selected if pool == "selected" else self._pool.candidates)]

        if not symbols:
            logger.warning("股票池为空")
            return []

        logger.info(f"开始扫描 {len(symbols)} 只股票的技术指标...")
        self._last_scan_time = datetime.now()
        signals: List[AnalysisSignal] = []

        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            futures = {executor.submit(self._analyze_single, sym): sym for sym in symbols}
            for future in as_completed(futures):
                try:
                    signal = future.result()
                    if signal and signal.score >= min_score:
                        signals.append(signal)
                except Exception as e:
                    logger.warning(f"分析 {futures[future]} 失败: {e}")

        # 按评分排序
        signals.sort(key=lambda s: s.score, reverse=True)
        self._last_signals = signals[:top_n]
        logger.info(f"扫描完成，最高评分: {signals[0].score if signals else 0:.1f}，"
                    f"符合阈值 {min_score} 的共 {len(signals)} 只")

        return signals[:top_n]

    def _analyze_single(self, symbol: str) -> Optional[AnalysisSignal]:
        """
        对单只股票执行技术分析

        流程：
          1. 从券商获取K线数据
          2. 计算技术指标
          3. 综合评分
          4. 返回信号
        """
        # 获取K线数据
        result = self._broker.get_kline(symbol, interval="1d", limit=200)
        if not result.success or not result.data:
            return None

        klines: List[KlineData] = result.data
        if len(klines) < 30:
            return None

        try:
            # 提取价格序列
            closes = [k.close_price for k in klines]
            highs = [k.high_price for k in klines]
            lows = [k.low_price for k in klines]
            volumes = [k.volume for k in klines]

            # 调用技术分析器
            indicators = self._ta.analyze(closes, highs, lows, volumes)

            # 综合评分
            score, details = self._compute_score(indicators, closes, volumes)

            # 构建信号
            signal = AnalysisSignal(
                symbol=symbol,
                name=self._pool.find(symbol).name if self._pool.find(symbol) else "",
                score=score,
                trend=details.get("trend", "neutral"),
                indicators=indicators,
                macd_signal=details.get("macd_signal", ""),
                rsi_value=details.get("rsi", 50.0),
                ma_arrangement=details.get("ma_arrangement", ""),
                volume_signal=details.get("volume_signal", ""),
                support_level=details.get("support", min(lows[-20:])),
                resistance_level=details.get("resistance", max(highs[-20:])),
            )
            return signal

        except Exception as e:
            logger.debug(f"分析 {symbol} 异常: {e}")
            return None

    def _compute_score(self, indicators: Dict[str, Any],
                       closes: List[float], volumes: List[float]) -> tuple:
        """
        综合评分引擎

        从5个维度打分（每个0~100），加权汇总
        """
        details = {}
        score = 0.0

        # 1. 趋势维度（25分）
        trend_score, trend_detail = self._score_trend(indicators, closes)
        score += trend_score * self.WEIGHT_TREND / 100

        # 2. 动量维度（25分）
        mom_score, mom_detail = self._score_momentum(indicators, closes)
        score += mom_score * self.WEIGHT_MOMENTUM / 100

        # 3. 成交量维度（20分）
        vol_score, vol_detail = self._score_volume(volumes)
        score += vol_score * self.WEIGHT_VOLUME / 100

        # 4. 波动率维度（15分）
        vlt_score = self._score_volatility(closes)
        score += vlt_score * self.WEIGHT_VOLATILITY / 100

        # 5. 形态维度（15分）
        pat_score = self._score_pattern(closes)
        score += pat_score * self.WEIGHT_PATTERN / 100

        # 汇总趋势方向
        details.update(trend_detail)
        details.update(mom_detail)
        details.update(vol_detail)
        details["trend"] = self._determine_trend(indicators, closes)

        return round(score, 1), details

    def _score_trend(self, indicators: dict, closes: list) -> tuple:
        """趋势评分：均线排列 + MACD"""
        score = 50
        details = {"ma_arrangement": "messy", "macd_signal": "neutral"}

        # 均线排列
        ma5 = self._sma(closes[-5:]) if len(closes) >= 5 else closes[-1]
        ma10 = self._sma(closes[-10:]) if len(closes) >= 10 else closes[-1]
        ma20 = self._sma(closes[-20:]) if len(closes) >= 20 else closes[-1]
        ma60 = self._sma(closes[-60:]) if len(closes) >= 60 else closes[-1]

        if ma5 > ma10 > ma20 > ma60:
            score = 85
            details["ma_arrangement"] = "bullish_aligned"
        elif ma5 > ma10 > ma20:
            score = 70
            details["ma_arrangement"] = "short_bullish"
        elif ma5 < ma10 < ma20 < ma60:
            score = 15
            details["ma_arrangement"] = "bearish_aligned"
        elif ma5 < ma10 < ma20:
            score = 30
            details["ma_arrangement"] = "short_bearish"

        # MACD
        macd_val = indicators.get("macd", [])
        if isinstance(macd_val, list) and len(macd_val) >= 2:
            if macd_val[-2] < 0 and macd_val[-1] >= 0:
                score += 15
                details["macd_signal"] = "golden_cross"
            elif macd_val[-2] > 0 and macd_val[-1] <= 0:
                score -= 15
                details["macd_signal"] = "death_cross"

        return min(max(score, 0), 100), details

    def _score_momentum(self, indicators: dict, closes: list) -> tuple:
        """动量评分：RSI + 价格变动"""
        score = 50
        details = {"rsi": 50.0}

        rsi = indicators.get("rsi", 50.0)
        if isinstance(rsi, list):
            rsi = rsi[-1] if rsi else 50.0
        details["rsi"] = float(rsi)

        if 40 <= rsi <= 60:
            score = 60  # 中性区
        elif 30 <= rsi < 40:
            score = 75  # 超卖回弹
        elif 20 <= rsi < 30:
            score = 85  # 深度超卖
        elif 60 < rsi <= 70:
            score = 40  # 超买区
        elif rsi > 70:
            score = 20  # 严重超买
        elif rsi < 20:
            score = 90  # 极限超卖

        # 近期动量
        if len(closes) >= 5:
            mom5 = (closes[-1] / closes[-5] - 1) * 100
            if 1 < mom5 < 5:
                score += 10
            elif mom5 > 10:
                score -= 10

        return min(max(score, 0), 100), details

    def _score_volume(self, volumes: list) -> tuple:
        """成交量评分"""
        score = 50
        details = {"volume_signal": "normal"}
        if len(volumes) < 20:
            return score, details

        avg_vol = sum(volumes[-20:]) / 20
        recent_vol = sum(volumes[-5:]) / 5

        ratio = recent_vol / avg_vol if avg_vol > 0 else 1.0
        if ratio > 2.0:
            score = 80
            details["volume_signal"] = "volume_surge"
        elif ratio > 1.5:
            score = 65
            details["volume_signal"] = "volume_increase"
        elif ratio < 0.5:
            score = 30
            details["volume_signal"] = "volume_shrink"

        return score, details

    def _score_volatility(self, closes: list) -> float:
        """波动率评分：适中波动最好"""
        if len(closes) < 20:
            return 50
        returns = [(closes[i] / closes[i-1] - 1) for i in range(1, len(closes))]
        avg_return = sum(returns) / len(returns)
        variance = sum((r - avg_return)**2 for r in returns) / len(returns)
        std = variance ** 0.5

        # 日波动 1~3% 最佳
        if 0.01 <= std <= 0.03:
            return 80
        elif std < 0.01:
            return 50
        elif std <= 0.05:
            return 60
        else:
            return 30

    def _score_pattern(self, closes: list) -> float:
        """形态评分：检测简单形态"""
        if len(closes) < 10:
            return 50
        score = 50

        # 近期高点突破
        if closes[-1] > max(closes[-20:-1]):
            score += 15

        # 连续阳线
        recent_changes = [closes[i] > closes[i-1] for i in range(max(0, len(closes)-3), len(closes))]
        if sum(recent_changes) >= 3:
            score += 10

        # 低点抬升
        if len(closes) >= 10 and min(closes[-5:]) > min(closes[-10:-5]):
            score += 10

        return min(score, 100)

    def _determine_trend(self, indicators: dict, closes: list) -> str:
        """判断总体趋势方向"""
        if len(closes) < 20:
            return "neutral"
        ma10 = self._sma(closes[-10:])
        ma20 = self._sma(closes[-20:])
        if closes[-1] > ma10 > ma20:
            return "bullish"
        elif closes[-1] < ma10 < ma20:
            return "bearish"
        return "neutral"

    @staticmethod
    def _sma(data: list) -> float:
        """简单移动平均"""
        return sum(data) / len(data) if data else 0.0

    # ── 快捷操作 ────────────────────────────────────────

    def get_top_picks(self, n: int = 5) -> List[AnalysisSignal]:
        """获取最近一次评分最高的N只股票"""
        if not self._last_signals:
            self.scan_and_rank(top_n=n)
        return self._last_signals[:n]

    def get_bullish_signals(self) -> List[AnalysisSignal]:
        """获取所有看涨信号"""
        self.scan_and_rank()
        return [s for s in self._last_signals if s.trend == "bullish"]

    @property
    def last_scan_time(self) -> Optional[datetime]:
        return self._last_scan_time

    # ── 交易执行桥接 ────────────────────────────────────

    def execute_signal(self, signal: AnalysisSignal, position_pct: float = 0.1) -> BrokerResult:
        """
        根据技术信号执行交易

        Args:
            signal:       技术分析信号
            position_pct: 仓位比例（占可用资金）

        Returns:
            BrokerResult
        """
        from broker_interface import OrderSide, OrderType

        account = self._broker.get_account()
        if not account.success:
            return BrokerResult.fail("无法获取账户信息")

        available = account.data.available_cash
        if signal.trend == "bullish" and signal.score >= 60:
            # 买入
            ticker = self._broker.get_ticker(signal.symbol)
            if not ticker.success:
                return BrokerResult.fail(f"获取 {signal.symbol} 行情失败")
            price = ticker.data.last_price
            quantity = int(available * position_pct / price / 100) * 100  # A股整手
            if quantity < 100:
                return BrokerResult.fail("资金不足以买入1手")
            return self._broker.place_order(
                symbol=signal.symbol,
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                quantity=quantity,
                price=price,
            )
        elif signal.trend == "bearish" and signal.score <= 40:
            # 卖出
            positions = self._broker.get_positions()
            if not positions.success:
                return BrokerResult.fail("无法获取持仓")
            for pos in positions.data:
                if pos.symbol == signal.symbol:
                    return self._broker.place_order(
                        symbol=signal.symbol,
                        side=OrderSide.SELL,
                        order_type=OrderType.MARKET,
                        quantity=pos.available_quantity,
                    )
            return BrokerResult.fail(f"未持有 {signal.symbol}")

        return BrokerResult.fail("信号不足以触发交易")


# ═══════════════════════════════════════════════════════════════
# 内置简易分析器（当 technical_analyzer 不可用时）
# ═══════════════════════════════════════════════════════════════

class _SimpleAnalyzer:
    """
    内置简易技术分析器

    当 technical_analyzer.py 不可用时的回退方案。
    提供基本指标计算：SMA、RSI、MACD。
    """

    def analyze(self, closes: list, highs: list, lows: list, volumes: list) -> Dict[str, Any]:
        return {
            "rsi": self._calc_rsi(closes, 14),
            "macd": self._calc_macd(closes),
            "sma_5": self._sma(closes, 5),
            "sma_10": self._sma(closes, 10),
            "sma_20": self._sma(closes, 20),
            "sma_60": self._sma(closes, 60),
        }

    def _calc_rsi(self, closes: list, period: int = 14) -> list:
        """计算 RSI 序列"""
        if len(closes) < period + 1:
            return [50.0] * len(closes)
        gains, losses = [], []
        for i in range(1, len(closes)):
            diff = closes[i] - closes[i-1]
            gains.append(max(diff, 0))
            losses.append(max(-diff, 0))
        rsi = [50.0] * period
        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period
        for i in range(period, len(gains)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period
            if avg_loss == 0:
                rsi.append(100.0)
            else:
                rs = avg_gain / avg_loss
                rsi.append(100.0 - 100.0 / (1.0 + rs))
        return rsi

    def _calc_macd(self, closes: list, fast: int = 12, slow: int = 26, signal: int = 9) -> list:
        """计算 MACD（返回 DIF-DEA 柱状线）"""
        if len(closes) < slow + signal:
            return [0.0] * len(closes)
        ema_fast = self._ema(closes, fast)
        ema_slow = self._ema(closes, slow)
        dif = [ema_fast[i] - ema_slow[i] for i in range(len(closes))]
        dea = self._ema(dif, signal)
        macd = [(dif[i] - dea[i]) * 2 for i in range(len(closes))]
        return macd

    @staticmethod
    def _sma(data: list, period: int = 5) -> float:
        if not data:
            return 0.0
        n = min(len(data), period)
        return sum(data[-n:]) / n

    @staticmethod
    def _ema(data: list, period: int) -> list:
        if len(data) < 2:
            return data[:]
        k = 2.0 / (period + 1)
        ema = [data[0]]
        for i in range(1, len(data)):
            ema.append(data[i] * k + ema[-1] * (1 - k))
        return ema
