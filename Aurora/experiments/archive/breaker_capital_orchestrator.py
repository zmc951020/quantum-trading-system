#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
熔断资金双向编排器 (Breaker Capital Orchestrator)
==================================================
核心原则：「智慧 ✧ 勇气 ✧ 力量」的三重合奏
  - 智慧：识别关键支撑位，科学计算买卖时机
  - 勇气：在极端恐慌点敢于分批买入（巴菲特式逆向投资）
  - 力量：永远保留弹药储备，确保跌得越深买得越多

理论基石：
  1. 金字塔加仓 (Pyramid Buying) — 越跌越买，但控制节奏
  2. 均值回归 (Mean Reversion) — 恐慌后市场有回归倾向
  3. Kelly 准则 — 基于胜率/赔率的最优仓位
  4. 斐波那契回撤 — 科学支撑位判定
  5. 杠铃策略 (Barbell) — 90%安全垫 + 10%极端激进
  6. CME三级熔断 — 7%/13%/20% 阈值体系
  7. ATR波动率仓位法 — 波动越大仓位越小
  8. 恐惧贪婪指数 — 极端恐惧时买入信号

集成模块:
  - CircuitBreakerModel (experiments/circuit_breaker_model.py)
  - DownMarketStrategy (strategies/downtrend_optimized.py)
  - FinalMarketAdaptiveGrid (strategies/final_market_adaptive.py)
  - BreakerCapitalBridge (experiments/breaker_capital_bridge.py)
"""

import numpy as np
from typing import Dict, List, Tuple, Optional, Any, Union
from dataclasses import dataclass, field
from enum import Enum, auto
from collections import deque
import logging
import sys
import os

# 路径设置
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger("BreakerCapitalOrchestrator")

# =============================================================================
# 枚举与状态定义
# =============================================================================

class MarketPhase(Enum):
    """市场阶段分类 — 决定买卖策略的主导方向"""
    CALM = "平稳"                # 正常交易，标准仓位
    CORRECTION = "回调"          # 小幅下跌，持仓观望
    PANIC_SURGE = "恐慌上升"     # 加速下跌，开始分层卖出
    PANIC_PEAK = "恐慌峰值"      # 极端恐慌，准备逆向买入
    BOUNCE_EARLY = "初步反弹"     # 止跌回升，确认买入
    BOUNCE_CONFIRMED = "确认反弹" # 趋势反转，追加仓位
    RECOVERY = "恢复"            # 恢复上涨，逐步获利了结

class OrchestratorAction(Enum):
    """编排器动作"""
    HOLD = "持仓不动"
    TIERED_SELL = "分层卖出"
    PREPARE_BUY = "准备买入"
    PYRAMID_BUY = "金字塔买入"
    TRAILING_STOP = "追踪止损"
    TAKE_PROFIT = "获利了结"
    FULL_EXIT = "全面清仓"

class SignalStrength(Enum):
    """信号强度"""
    WEAK = 1       # 弱信号 — 小仓位试探
    MODERATE = 2   # 中等信号 — 标准仓位
    STRONG = 3      # 强信号 — 加大仓位
    EXTREME = 4     # 极端信号 — 重仓出击

# =============================================================================
# 数据类定义
# =============================================================================

@dataclass
class SellTierConfig:
    """分层卖出配置"""
    breaker_level: int          # 熔断等级 0-4
    sell_pct: float             # 卖出比例 (0.0 ~ 1.0)
    min_hold_pct: float         # 最低持有比例
    description: str            # 说明
    panic_protection: bool = True  # 是否启用恐慌保护（防止最低点全卖）

# 分层卖出表 — 核心理念：下跌熔断 ≠ 全卖
SELL_TIERS = [
    SellTierConfig(0, 0.00, 1.00, "无熔断 — 正常持仓"),
    SellTierConfig(1, 0.12, 0.88, "预警级 — 小幅减仓12%，观察市场"),
    SellTierConfig(2, 0.25, 0.75, "局部熔断 — 减仓25%，保留75%"),
    SellTierConfig(3, 0.45, 0.55, "全局熔断 — 减仓45%，保留55%以防反弹"),
    SellTierConfig(4, 0.60, 0.40, "全面熔断 — 减仓60%，保留40%弹药"),
]

@dataclass
class BuyTierConfig:
    """分层买入配置"""
    signal_strength: SignalStrength
    reserve_allocation: float    # 从储备金中动用的比例
    max_single_buy_pct: float   # 单次买入占当前持仓的上限
    description: str
    require_confirmation: bool  # 是否需要多重确认

# 分层买入表 — 核心理念：极端恐慌时敢于分批买入
BUY_TIERS = [
    BuyTierConfig(SignalStrength.WEAK,   0.10, 0.05, "弱反弹信号 — 试探性建仓10%", True),
    BuyTierConfig(SignalStrength.MODERATE, 0.25, 0.10, "中等反弹 — 标准加仓25%", True),
    BuyTierConfig(SignalStrength.STRONG,  0.40, 0.20, "强反转信号 — 积极加仓40%", True),
    BuyTierConfig(SignalStrength.EXTREME, 0.60, 0.35, "极端恐慌底部 — 重仓出击60%", False),
]

@dataclass
class CapitalReservePolicy:
    """资金储备策略"""
    market_phase: MarketPhase
    min_cash_reserve_pct: float    # 最低现金储备比例
    max_deploy_pct: float          # 最大可部署比例
    description: str

# 资金储备表 — 永远保留弹药
RESERVE_POLICIES = [
    CapitalReservePolicy(MarketPhase.CALM,          0.20, 0.80, "正常市场 — 保留20%现金"),
    CapitalReservePolicy(MarketPhase.CORRECTION,    0.30, 0.70, "回调阶段 — 保留30%现金"),
    CapitalReservePolicy(MarketPhase.PANIC_SURGE,   0.40, 0.60, "恐慌上升 — 保留40%等待更好机会"),
    CapitalReservePolicy(MarketPhase.PANIC_PEAK,    0.50, 0.60, "恐慌峰值 — 50%现金准备抄底"),
    CapitalReservePolicy(MarketPhase.BOUNCE_EARLY,  0.35, 0.65, "初步反弹 — 可部署65%"),
    CapitalReservePolicy(MarketPhase.BOUNCE_CONFIRMED, 0.25, 0.75, "确认反弹 — 可部署75%"),
    CapitalReservePolicy(MarketPhase.RECOVERY,      0.20, 0.80, "恢复期 — 正常仓位"),
]

@dataclass
class KeySupportLevel:
    """关键支撑位"""
    price: float
    level_type: str            # "fibonacci", "recent_low", "volume_profile", "moving_average"
    strength: float            # 0~1, 支撑强度
    distance_pct: float        # 距当前价格的距离百分比（负数=下方）
    description: str

@dataclass
class ReversalSignal:
    """反转信号"""
    detected: bool
    strength: SignalStrength
    confidence: float           # 0~1
    indicators: Dict[str, float]  # 各指标值
    confirmations: int          # 确认指标数量
    description: str

@dataclass
class OrchestratorDecision:
    """编排器决策"""
    timestamp: int
    action: OrchestratorAction
    current_phase: MarketPhase
    breaker_level: int
    black_swan_score: float
    sell_pct: float = 0.0          # 本次卖出比例
    buy_pct: float = 0.0           # 本次买入比例
    target_cash_reserve: float = 0.2
    reversal_signal: Optional[ReversalSignal] = None
    support_levels: List[KeySupportLevel] = field(default_factory=list)
    reasoning: str = ""
    metrics: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# 核心编排器
# =============================================================================

class BreakerCapitalOrchestrator:
    """
    熔断资金双向编排器
    
    功能:
      1. 分层卖出 — 根据熔断等级智能减仓，绝不恐慌全卖
      2. 支撑位探测 — Fibonacci + 量价轮廓 + 均线 + 历史低点
      3. 逆向买入 — 极端恐慌时捕捉反弹信号，金字塔加仓
      4. 资金储备 — 动态调整现金/持仓比例
      5. 反弹确认 — 多重指标协同确认反转有效性
    """
    
    def __init__(self,
                 initial_capital: float = 100000.0,
                 max_position_pct: float = 0.80,
                 min_cash_reserve: float = 0.15):
        """
        Args:
            initial_capital: 初始资金
            max_position_pct: 最大持仓比例
            min_cash_reserve: 最低现金储备（安全垫）
        """
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.cash = initial_capital
        self.position = 0.0               # 当前持仓市值
        self.position_cost = 0.0          # 持仓成本
        self.max_position_pct = max_position_pct
        self.min_cash_reserve = min_cash_reserve
        
        # 状态追踪
        self.current_phase = MarketPhase.CALM
        self.breaker_level = 0
        self.black_swan_score = 0.0
        self.peak_capital = initial_capital
        self.drawdown_history: List[float] = []
        
        # 价格与交易历史
        self.price_history: List[float] = []
        self.volume_history: List[float] = []
        self.decisions: List[OrchestratorDecision] = []
        
        # 支撑位缓存
        self.support_levels: List[KeySupportLevel] = []
        
        # 反弹追踪
        self.consecutive_down_bars = 0
        self.last_buy_price = 0.0
        self.pyramid_level = 0       # 金字塔当前层级
        self.max_pyramid_levels = 4
        
        # 技术指标参数
        self.rsi_period_short = 7
        self.rsi_period_mid = 14
        self.rsi_period_long = 28
        self.macd_fast = 12
        self.macd_slow = 26
        self.macd_signal = 9
        self.bollinger_period = 20
        self.bollinger_std = 2.0
        self.atr_period = 14
        
        # 斐波那契回撤位（标准）
        self.fib_levels = [0.236, 0.382, 0.5, 0.618, 0.786, 1.0]
        
        # 资金分配配置（与 constellation 对齐）
        self.constellation_levels = [
            {'threshold': 0.02, 'allocation': 0.10, 'max_position': 0.15},
            {'threshold': 0.04, 'allocation': 0.15, 'max_position': 0.35},
            {'threshold': 0.06, 'allocation': 0.20, 'max_position': 0.55},
            {'threshold': 0.08, 'allocation': 0.25, 'max_position': 0.75},
            {'threshold': 0.10, 'allocation': 0.30, 'max_position': 1.00},
        ]
        
        # 盈亏统计
        self.total_trades = 0
        self.winning_trades = 0
        self.total_profit = 0.0
        self.max_drawdown = 0.0

    # ═══════════════════════════════════════════════════════════════
    #  智 慧 — 技术指标计算与支撑位探测
    # ═══════════════════════════════════════════════════════════════

    def _calculate_rsi(self, prices: List[float], period: int) -> float:
        """计算 RSI 指标"""
        if len(prices) < period + 1:
            return 50.0
        recent = prices[-(period + 1):]
        gains = []
        losses = []
        for i in range(1, len(recent)):
            diff = recent[i] - recent[i - 1]
            if diff > 0:
                gains.append(diff)
                losses.append(0.0)
            else:
                gains.append(0.0)
                losses.append(abs(diff))
        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))

    def _calculate_macd(self, prices: List[float]) -> Tuple[float, float, float]:
        """计算 MACD 指标 — 返回 (MACD, Signal, Histogram)"""
        if len(prices) < self.macd_slow + 1:
            return 0.0, 0.0, 0.0
        
        prices_arr = np.array(prices)
        ema_fast = self._ema(prices_arr, self.macd_fast)
        ema_slow = self._ema(prices_arr, self.macd_slow)
        macd_line = ema_fast[-1] - ema_slow[-1]
        
        # 计算信号线（MACD 的 9 日 EMA）
        macd_full = ema_fast - ema_slow
        signal_line = self._ema(macd_full, self.macd_signal)[-1]
        
        histogram = macd_line - signal_line
        return macd_line, signal_line, histogram

    def _ema(self, data: np.ndarray, period: int) -> np.ndarray:
        """指数移动平均"""
        alpha = 2.0 / (period + 1)
        result = np.zeros_like(data)
        result[0] = data[0]
        for i in range(1, len(data)):
            result[i] = alpha * data[i] + (1 - alpha) * result[i - 1]
        return result

    def _calculate_bollinger(self, prices: List[float]) -> Tuple[float, float, float, float]:
        """计算布林带 — 返回 (middle, upper, lower, position)"""
        if len(prices) < self.bollinger_period:
            return prices[-1], prices[-1], prices[-1], 0.5
        recent = np.array(prices[-self.bollinger_period:])
        middle = np.mean(recent)
        std = np.std(recent)
        upper = middle + self.bollinger_std * std
        lower = middle - self.bollinger_std * std
        # position: 0=下轨, 0.5=中轨, 1=上轨
        if upper - lower > 0:
            position = (prices[-1] - lower) / (upper - lower)
        else:
            position = 0.5
        return middle, upper, lower, position

    def _calculate_atr(self, prices: List[float]) -> float:
        """简化 ATR（用价格波动近似）"""
        if len(prices) < self.atr_period:
            return 0.01
        returns = np.abs(np.diff(prices[-(self.atr_period + 1):]))
        return float(np.mean(returns)) / prices[-1] if prices[-1] > 0 else 0.01

    def _detect_macd_divergence(self, prices: List[float]) -> bool:
        """
        检测 MACD 底背离
        价格创新低但 MACD 柱状图缩小 → 底背离 → 反弹信号
        """
        if len(prices) < 30:
            return False
        # 最近 10 根 K 线的低点
        lookback = 10
        recent_prices = prices[-lookback:]
        price_low = min(recent_prices)
        price_low_idx = recent_prices.index(price_low)
        
        # 计算历史 MACD
        macd_hist_values = []
        for i in range(lookback, 1, -1):
            segment = prices[:-(i - 1)] if i > 1 else prices
            _, _, hist = self._calculate_macd(segment)
            macd_hist_values.append(hist)
        
        if len(macd_hist_values) < lookback:
            return False
        
        # 检查：价格低点更低，但 MACD 柱更高（底背离）
        earlier_low = min(prices[-(lookback * 2):-lookback]) if len(prices) >= lookback * 2 else price_low
        earlier_hist = min(macd_hist_values[:lookback]) if len(macd_hist_values) >= lookback else 0
        
        return price_low <= earlier_low * 0.99 and macd_hist_values[-1] > earlier_hist

    def _detect_reversal_signal(self) -> ReversalSignal:
        """
        综合反转信号检测 — 多重指标协同确认
        
        信号层级:
          - 极端超卖: RSI(7)<25 AND RSI(14)<30 AND RSI(28)<45
          - 布林带触及: 价格 < 下轨 × 1.02
          - MACD底背离: 价格新低但柱状线缩小
          - 成交量放大: 恐慌性放量后缩量 → 卖盘枯竭
          - 连续下跌反转: 连跌 ≥ 5 天后收阳
        """
        prices = self.price_history
        volumes = self.volume_history
        
        if len(prices) < 30:
            return ReversalSignal(
                detected=False, strength=SignalStrength.WEAK,
                confidence=0.0, indicators={}, confirmations=0,
                description="数据不足，无法判断反转信号"
            )
        
        # 1. 多周期 RSI 超卖
        rsi_7 = self._calculate_rsi(prices, self.rsi_period_short)
        rsi_14 = self._calculate_rsi(prices, self.rsi_period_mid)
        rsi_28 = self._calculate_rsi(prices, self.rsi_period_long)
        oversold_score = 0
        if rsi_7 < 25: oversold_score += 2
        elif rsi_7 < 30: oversold_score += 1
        if rsi_14 < 30: oversold_score += 2
        elif rsi_14 < 35: oversold_score += 1
        if rsi_28 < 40: oversold_score += 1
        extreme_oversold = oversold_score >= 4
        
        # 2. 布林带位置
        _, _, lower_bb, bb_pos = self._calculate_bollinger(prices)
        near_lower_band = bb_pos < 0.1 or prices[-1] < lower_bb * 1.02
        
        # 3. MACD 底背离
        macd_divergence = self._detect_macd_divergence(prices)
        _, _, histogram = self._calculate_macd(prices)
        histogram_turning = histogram < 0 and len(prices) >= 3 and \
            self._calculate_macd(prices[:-1])[2] < histogram
        
        # 4. 成交量分析
        volume_surge = False
        volume_drying = False
        if len(volumes) >= 20:
            avg_vol = np.mean(volumes[-20:])
            recent_vol = np.mean(volumes[-5:])
            if recent_vol > avg_vol * 1.5:
                volume_surge = True
            if recent_vol < avg_vol * 0.6 and prices[-1] < np.mean(prices[-20:]):
                volume_drying = True  # 卖盘枯竭信号
        
        # 5. 连续下跌反转
        consecutive_down = 0
        for i in range(min(10, len(prices) - 1), 0, -1):
            if prices[-i] < prices[-i - 1]:
                consecutive_down += 1
            else:
                break
        last_is_up = prices[-1] > prices[-2] if len(prices) >= 2 else False
        momentum_reversal = consecutive_down >= 3 and last_is_up and prices[-1] > prices[-2] * 1.002
        
        # 综合评分
        confirmations = sum([
            extreme_oversold,
            near_lower_band,
            macd_divergence or histogram_turning,
            volume_surge or volume_drying,
            momentum_reversal
        ])
        
        # 信号强度判定
        if confirmations >= 4:
            strength = SignalStrength.EXTREME
            description = "极端恐慌底部 — 多重超卖+底背离+放量止跌"
        elif confirmations >= 3:
            strength = SignalStrength.STRONG
            description = "强反转信号 — 多指标协同确认"
        elif confirmations >= 2:
            strength = SignalStrength.MODERATE
            description = "中等反弹信号 — 部分指标确认"
        elif confirmations >= 1:
            strength = SignalStrength.WEAK
            description = "弱反弹信号 — 谨慎试探"
        else:
            strength = SignalStrength.WEAK
            description = "无明显反转信号"
        
        return ReversalSignal(
            detected=confirmations >= 1,
            strength=strength,
            confidence=min(confirmations / 5.0, 1.0),
            indicators={
                "rsi_7": rsi_7, "rsi_14": rsi_14, "rsi_28": rsi_28,
                "bb_position": bb_pos, "macd_histogram": histogram,
                "oversold_score": oversold_score,
                "volume_surge": 1.0 if volume_surge else 0.0,
                "volume_drying": 1.0 if volume_drying else 0.0,
                "consecutive_down": consecutive_down,
            },
            confirmations=confirmations,
            description=description
        )

    def _detect_key_support_levels(self) -> List[KeySupportLevel]:
        """
        探测关键支撑位
        - Fibonacci 回撤位（基于近期高低点）
        - 近期低点（20日/50日/100日）
        - 布林带下轨
        - 成交量密集区低点
        """
        prices = self.price_history
        if len(prices) < 20:
            return []
        
        current_price = prices[-1]
        supports = []
        
        # 1. Fibonacci 回撤位
        lookback_fib = min(100, len(prices))
        recent_segment = prices[-lookback_fib:]
        high = max(recent_segment)
        low = min(recent_segment)
        diff = high - low
        
        if diff > 0:
            for fib in self.fib_levels:
                fib_price = high - diff * fib
                distance = (fib_price - current_price) / current_price
                if fib_price < current_price:  # 只关注下方支撑
                    # 关键 Fib 水平权重更高
                    if fib in [0.382, 0.5, 0.618]:
                        strength = 0.8
                    elif fib in [0.786, 1.0]:
                        strength = 1.0
                    else:
                        strength = 0.5
                    supports.append(KeySupportLevel(
                        price=fib_price,
                        level_type="fibonacci",
                        strength=strength,
                        distance_pct=distance,
                        description=f"斐波那契 {fib:.1%} 回撤位 @ {fib_price:.2f}"
                    ))
        
        # 2. 近期低点支撑
        for period, label, weight in [(20, "20日低点", 0.6), (50, "50日低点", 0.7), (100, "百日低点", 0.85)]:
            if len(prices) >= period:
                recent_low = min(prices[-period:])
                if recent_low < current_price:
                    distance = (recent_low - current_price) / current_price
                    supports.append(KeySupportLevel(
                        price=recent_low,
                        level_type="recent_low",
                        strength=weight,
                        distance_pct=distance,
                        description=f"{label} @ {recent_low:.2f}"
                    ))
        
        # 3. 布林带下轨
        _, _, lower_bb, _ = self._calculate_bollinger(prices)
        if lower_bb < current_price:
            distance = (lower_bb - current_price) / current_price
            supports.append(KeySupportLevel(
                price=lower_bb,
                level_type="bollinger",
                strength=0.7,
                distance_pct=distance,
                description=f"布林带下轨 @ {lower_bb:.2f}"
            ))
        
        # 4. 移动均线支撑
        for period, label, weight in [(20, "MA20", 0.5), (60, "MA60", 0.65), (120, "MA120", 0.8)]:
            if len(prices) >= period:
                ma = np.mean(prices[-period:])
                if ma < current_price:
                    distance = (ma - current_price) / current_price
                    supports.append(KeySupportLevel(
                        price=ma,
                        level_type="moving_average",
                        strength=weight,
                        distance_pct=distance,
                        description=f"{label} 支撑 @ {ma:.2f}"
                    ))
        
        # 按距当前价格由近到远排序
        supports.sort(key=lambda x: x.distance_pct, reverse=True)
        self.support_levels = supports
        return supports

    def _classify_market_phase(self, breaker_level: int, black_swan_score: float,
                                 reversal: ReversalSignal) -> MarketPhase:
        """
        市场阶段分类
        
        决策矩阵:
          breaker=0, score<0.15 → CALM
          breaker=1, score 0.15-0.30 → CORRECTION
          breaker>=2, score 0.30-0.50 → PANIC_SURGE
          breaker>=3, score>0.50, reversal=strong → PANIC_PEAK
          breaker从高变低, reversal=strong → BOUNCE_EARLY
          breaker=0, price>MA20 → BOUNCE_CONFIRMED/RECOVERY
        """
        if breaker_level == 0 and black_swan_score < 0.15:
            # 检查是否从恐慌中恢复
            if self.current_phase in [MarketPhase.BOUNCE_EARLY, MarketPhase.BOUNCE_CONFIRMED]:
                if len(self.price_history) >= 20:
                    current = self.price_history[-1]
                    ma20 = np.mean(self.price_history[-20:])
                    if current > ma20:
                        return MarketPhase.RECOVERY
                    else:
                        return MarketPhase.BOUNCE_CONFIRMED
            return MarketPhase.CALM
        
        if breaker_level == 1 and black_swan_score < 0.30:
            return MarketPhase.CORRECTION
        
        if breaker_level >= 2 and black_swan_score < 0.50:
            return MarketPhase.PANIC_SURGE
        
        if breaker_level >= 3 and black_swan_score >= 0.50:
            if reversal.strength in [SignalStrength.STRONG, SignalStrength.EXTREME]:
                return MarketPhase.PANIC_PEAK
            return MarketPhase.PANIC_SURGE
        
        # 从高峰回落 → 可能反弹
        if self.current_phase in [MarketPhase.PANIC_SURGE, MarketPhase.PANIC_PEAK]:
            if breaker_level <= 1 and reversal.detected:
                return MarketPhase.BOUNCE_EARLY
        
        return self.current_phase

    # ═══════════════════════════════════════════════════════════════
    #  勇 气 — 逆向买入与金字塔加仓
    # ═══════════════════════════════════════════════════════════════

    def _calculate_buy_amount(self, signal: ReversalSignal, phase: MarketPhase) -> float:
        """
        计算本次买入金额 — 金字塔加仓模型
        
        原理: 越跌越买，但每次买入量递增（金字塔底部更宽）
        层级1: 试探  — 动用储备10%
        层级2: 加仓  — 动用储备25%
        层级3: 重仓  — 动用储备40%
        层级4: 满仓  — 动用储备60%（需极端信号）
        """
        # 获取当前储备金
        reserve = self.cash
        total_value = self.capital + self.position * (self.price_history[-1] if self.price_history else 1.0)
        
        # 根据信号强度选择买入层级
        tier_map = {
            SignalStrength.WEAK: 0,
            SignalStrength.MODERATE: 1,
            SignalStrength.STRONG: 2,
            SignalStrength.EXTREME: 3,
        }
        tier_idx = tier_map.get(signal.strength, 0)
        
        # 限制金字塔层级（不超过已配置最大层级）
        tier_idx = min(tier_idx, self.max_pyramid_levels - 1)
        buy_config = BUY_TIERS[tier_idx]
        
        # 计算买入金额
        buy_amount = reserve * buy_config.reserve_allocation
        
        # 仓位上限约束
        max_position_value = total_value * self.max_position_pct
        current_position_value = self.position * (self.price_history[-1] if self.price_history else 1.0)
        max_buy = max(0, max_position_value - current_position_value)
        buy_amount = min(buy_amount, max_buy)
        
        # 储备金底线约束
        reserve_policy = next((p for p in RESERVE_POLICIES if p.market_phase == phase), RESERVE_POLICIES[0])
        min_cash = total_value * reserve_policy.min_cash_reserve_pct
        max_deploy = max(0, self.cash - min_cash)
        buy_amount = min(buy_amount, max_deploy)
        
        # 单次买入上限（占当前持仓比例）
        max_single = current_position_value * buy_config.max_single_buy_pct
        if current_position_value > 0:
            buy_amount = min(buy_amount, max_single)
        
        return max(0, buy_amount)

    def _execute_pyramid_buy(self, signal: ReversalSignal, phase: MarketPhase,
                               current_price: float) -> OrchestratorDecision:
        """执行金字塔买入"""
        buy_amount = self._calculate_buy_amount(signal, phase)
        
        if buy_amount <= 0:
            return OrchestratorDecision(
                timestamp=len(self.price_history),
                action=OrchestratorAction.PREPARE_BUY,
                current_phase=phase,
                breaker_level=self.breaker_level,
                black_swan_score=self.black_swan_score,
                reversal_signal=signal,
                support_levels=self.support_levels,
                reasoning=f"信号强度={signal.strength.name}, 但资金不满足买入条件",
                metrics={"buy_amount": 0, "available_cash": self.cash}
            )
        
        # 执行买入
        shares = buy_amount / current_price if current_price > 0 else 0
        total_cost = shares * current_price
        
        self.cash -= total_cost
        old_position = self.position
        self.position += shares
        
        # 更新成本（加权平均）
        if old_position > 0:
            self.position_cost = (self.position_cost * old_position + total_cost) / self.position
        else:
            self