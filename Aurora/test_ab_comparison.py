!/usr/bin/env python3
"""
A/B 对比测试框架 — 验证优化策略是否超越现有策略
=================================================
核心逻辑：
  1. 在相同市场数据上同时运行基线策略和优化策略
  2. 记录完整的绩效指标（年化收益、夏普、最大回撤、胜率、盈亏比）
  3. 输出对比报告，判断优化策略是否显著超越基线

使用方式：
  python test_ab_comparison.py

输出：
  - 控制台打印对比报告
  - reports/ab_comparison_report.json 持久化结果
"""

import sys
import os
import json
import time
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, field, asdict
from enum import Enum
import logging
from copy import deepcopy

# 添加项目根目录
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 导入 MarketStateHub
from signals.market_state_hub import get_market_state_hub, MarketStateHub

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


# ==================== 绩效指标定义 ====================

@dataclass
class PerformanceMetrics:
    """绩效指标数据类"""
    total_return: float = 0.0          # 总收益率
    annual_return: float = 0.0         # 年化收益率
    sharpe_ratio: float = 0.0          # 夏普比率
    sortino_ratio: float = 0.0         # 索提诺比率
    calmar_ratio: float = 0.0          # 卡玛比率
    max_drawdown: float = 0.0          # 最大回撤
    win_rate: float = 0.0              # 胜率
    profit_loss_ratio: float = 0.0     # 盈亏比
    total_trades: int = 0              # 总交易次数
    avg_holding_period: float = 0.0    # 平均持仓周期
    volatility: float = 0.0            # 波动率
    final_balance: float = 0.0         # 最终余额
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ABTestResult:
    """A/B 测试结果"""
    baseline: PerformanceMetrics = field(default_factory=PerformanceMetrics)
    optimized: PerformanceMetrics = field(default_factory=PerformanceMetrics)
    improvement: Dict[str, float] = field(default_factory=dict)
    is_significant: bool = False
    test_name: str = ""
    timestamp: str = ""
    market_scenario: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "test_name": self.test_name,
            "timestamp": self.timestamp,
            "market_scenario": self.market_scenario,
            "baseline": self.baseline.to_dict(),
            "optimized": self.optimized.to_dict(),
            "improvement": self.improvement,
            "is_significant": self.is_significant
        }


# ==================== 市场场景生成器 ====================

class MarketScenario(Enum):
    """市场场景枚举"""
    RANGE_BOUND = "range_bound"      # 横盘市场
    TRENDING_UP = "trending_up"      # 上涨趋势
    TRENDING_DOWN = "trending_down"  # 下跌趋势
    VOLATILE = "volatile"            # 高波动市场
    MIXED = "mixed"                  # 混合市场


def generate_market_data(
    scenario: MarketScenario,
    length: int = 1000,
    base_price: float = 100.0,
    seed: int = 42
) -> pd.Series:
    """
    生成指定场景的市场数据
    
    Args:
        scenario: 市场场景
        length: 数据长度
        base_price: 基准价格
        seed: 随机种子
        
    Returns:
        价格序列
    """
    np.random.seed(seed)
    
    if scenario == MarketScenario.RANGE_BOUND:
        # 横盘：小幅随机波动
        returns = np.random.randn(length) * 0.003
        prices = base_price * np.exp(np.cumsum(returns))
        
    elif scenario == MarketScenario.TRENDING_UP:
        # 上涨：趋势 + 噪声
        trend = np.linspace(0, 0.3, length)
        returns = np.random.randn(length) * 0.004 + trend * 0.001
        prices = base_price * np.exp(np.cumsum(returns))
        
    elif scenario == MarketScenario.TRENDING_DOWN:
        # 下跌：趋势 + 噪声
        trend = np.linspace(0, -0.3, length)
        returns = np.random.randn(length) * 0.004 + trend * 0.001
        prices = base_price * np.exp(np.cumsum(returns))
        
    elif scenario == MarketScenario.VOLATILE:
        # 高波动：大幅随机波动
        returns = np.random.randn(length) * 0.02
        prices = base_price * np.exp(np.cumsum(returns))
        
    elif scenario == MarketScenario.MIXED:
        # 混合：横盘→上涨→下跌→横盘
        segments = [
            (0, 250, 0.002, 0.0),      # 横盘
            (250, 500, 0.004, 0.001),   # 上涨
            (500, 750, 0.004, -0.001),  # 下跌
            (750, 1000, 0.002, 0.0),    # 横盘
        ]
        returns = np.zeros(length)
        for start, end, vol, trend in segments:
            seg_len = end - start
            returns[start:end] = np.random.randn(seg_len) * vol + trend
        prices = base_price * np.exp(np.cumsum(returns))
    
    return pd.Series(prices, index=pd.date_range(
        start="2025-01-01", periods=length, freq="1min"
    ))


# ==================== 基线策略模拟器 ====================

class BaselineStrategySimulator:
    """
    基线策略模拟器
    
    模拟 final_market_adaptive.py 的核心交易逻辑：
    - 市场状态检测（_label_market_type）
    - 网格交易
    - 均值回归
    - 承接策略
    - 止损止盈
    """
    
    def __init__(self, initial_balance: float = 100000.0):
        self.initial_balance = initial_balance
        self.balance = initial_balance
        self.position = 0.0  # 持仓数量
        self.trade_history = []
        self.balance_history = [initial_balance]
        self.base_price = 100.0
        
        # 网格参数
        self.grid_levels = 5
        self.grid_spacing = 0.02
        self.min_buy_amount = 1000.0
        self.max_buy_amount = 5000.0
        
        # 风险参数
        self.stop_loss = 0.008
        self.take_profit = 0.025
        self.max_drawdown = 0.08
        
        # 市场状态
        self.market_type = 'range_bound'
        self.last_price = 100.0
        
        # 网格价格水平
        self.grid_prices = []
        self._init_grids()
    
    def _init_grids(self):
        """初始化网格价格"""
        self.grid_prices = []
        for i in range(-self.grid_levels, self.grid_levels + 1):
            price = self.base_price * (1 + self.grid_spacing) ** i
            self.grid_prices.append(price)
        self.grid_prices.sort()
    
    def _detect_market_type(self, data: pd.Series) -> str:
        """检测市场类型（与 final_market_adaptive 一致）"""
        if len(data) < 60:
            return 'range_bound'
        
        ema10 = data.ewm(span=10).mean()
        ema30 = data.ewm(span=30).mean()
        ema60 = data.ewm(span=60).mean()
        
        trend_10_60 = (ema10.iloc[-1] - ema60.iloc[-1]) / ema60.iloc[-1]
        trend_10_30 = (ema10.iloc[-1] - ema30.iloc[-1]) / ema30.iloc[-1]
        
        up_count = sum([
            trend_10_60 > 0.02, trend_10_30 > 0.02,
            ema10.iloc[-1] > ema10.iloc[-5],
            ema30.iloc[-1] > ema30.iloc[-10]
        ])
        
        down_count = sum([
            trend_10_60 < -0.02, trend_10_30 < -0.02,
            ema10.iloc[-1] < ema10.iloc[-5],
            ema30.iloc[-1] < ema30.iloc[-10]
        ])
        
        volatility = data.iloc[-20:].pct_change().std()
        price_range = (data.iloc[-20:].max() - data.iloc[-20:].min()) / data.iloc[-20:].mean()
        momentum_5d = (data.iloc[-1] - data.iloc[-5]) / data.iloc[-5] if len(data) > 5 else 0
        momentum_10d = (data.iloc[-1] - data.iloc[-10]) / data.iloc[-10] if len(data) > 10 else 0
        
        if up_count >= 3 and momentum_5d > 0 and momentum_10d > 0:
            return 'trending_up'
        if down_count >= 3 and momentum_5d < 0 and momentum_10d < 0:
            return 'trending_down'
        if price_range < 0.03 and abs(trend_10_60) < 0.01:
            return 'range_bound'
        if volatility > 0.015 and abs(trend_10_60) < 0.015:
            return 'volatile'
        if trend_10_60 < -0.015:
            return 'trending_down'
        elif trend_10_60 > 0.015:
            return 'trending_up'
        else:
            return 'range_bound'
    
    def update(self, price: float, data: pd.Series) -> Dict[str, Any]:
        """
        更新策略状态
        
        Args:
            price: 当前价格
            data: 完整价格序列
            
        Returns:
            交易动作字典
        """
        action = {"type": "hold", "price": price, "quantity": 0, "reason": ""}
        
        # 检测市场类型
        self.market_type = self._detect_market_type(data)
        
        # 计算持仓价值
        position_value = self.position * price
        total_value = self.balance + position_value
        
        # 止损检查
        if self.position > 0:
            unrealized_pnl = (price - self.last_price) / self.last_price
            if unrealized_pnl < -self.stop_loss:
                # 止损卖出
                sell_amount = self.position * price
                self.balance += sell_amount
                action = {"type": "sell", "price": price, "quantity": self.position, "reason": "stop_loss"}
                self.trade_history.append({"action": "sell", "price": price, "quantity": self.position, "reason": "stop_loss"})
                self.position = 0.0
        
        # 止盈检查
        if self.position > 0:
            unrealized_pnl = (price - self.last_price) / self.last_price
            if unrealized_pnl > self.take_profit:
                sell_amount = self.position * price
                self.balance += sell_amount
                action = {"type": "sell", "price": price, "quantity": self.position, "reason": "take_profit"}
                self.trade_history.append({"action": "sell", "price": price, "quantity": self.position, "reason": "take_profit"})
                self.position = 0.0
        
        # 网格交易
        if self.market_type == 'range_bound':
            for grid_price in self.grid_prices:
                if abs(price - grid_price) / grid_price < 0.001:
                    if price <= grid_price and self.balance > self.min_buy_amount:
                        # 买入
                        buy_amount = min(self.max_buy_amount, self.balance * 0.3)
                        quantity = buy_amount / price
                        self.position += quantity
                        self.balance -= buy_amount
                        action = {"type": "buy", "price": price, "quantity": quantity, "reason": "grid_buy"}
                        self.trade_history.append({"action": "buy", "price": price, "quantity": quantity, "reason": "grid_buy"})
                    elif price > grid_price and self.position > 0:
                        # 卖出
                        sell_quantity = self.position * 0.3
                        sell_amount = sell_quantity * price
                        self.position -= sell_quantity
                        self.balance += sell_amount
                        action = {"type": "sell", "price": price, "quantity": sell_quantity, "reason": "grid_sell"}
                        self.trade_history.append({"action": "sell", "price": price, "quantity": sell_quantity, "reason": "grid_sell"})
        
        # 趋势跟随
        elif self.market_type == 'trending_up' and self.balance > self.min_buy_amount:
            buy_amount = min(self.max_buy_amount * 0.5, self.balance * 0.2)
            quantity = buy_amount / price
            self.position += quantity
            self.balance -= buy_amount
            action = {"type": "buy", "price": price, "quantity": quantity, "reason": "trend_follow"}
            self.trade_history.append({"action": "buy", "price": price, "quantity": quantity, "reason": "trend_follow"})
        
        # 下跌承接
        elif self.market_type == 'trending_down' and self.balance > self.min_buy_amount:
            if price < self.base_price * 0.95:
                buy_amount = min(self.max_buy_amount * 0.3, self.balance * 0.15)
                quantity = buy_amount / price
                self.position += quantity
                self.balance -= buy_amount
                action = {"type": "buy", "price": price, "quantity": quantity, "reason": "downward_buy"}
                self.trade_history.append({"action": "buy", "price": price, "quantity": quantity, "reason": "downward_buy"})
        
        self.last_price = price
        self.balance_history.append(self.balance + self.position * price)
        
        return action


# ==================== 优化策略模拟器 ====================

class OptimizedStrategySimulator:
    """
    优化策略模拟器（v4 — 下跌反弹增强版）
    
    核心设计理念（基于用户反馈）：
    - 分钟级高频交易，不降低交易频率
    - 下跌重要支撑位敢于承接，抓住反弹机会
    - 提高资金利用率，不持有大量现金
    - 利用 MarketStateHub 的 RSI/布林带/波动率信息增强交易决策
    
    与基线的核心差异：
    1. 【下跌反弹增强】下跌趋势中，利用 RSI 超卖 + 布林带下轨双重确认，积极抄底
    2. 【支撑位承接】在关键支撑位（网格下沿、前期低点）加大买入力度
    3. 【资金利用率】保持较高仓位，减少现金闲置
    4. 【RSI 动态仓位】RSI 越低仓位越大，RSI 越高仓位越小
    5. 【波动率自适应】高波动时扩大网格捕捉更大波动，低波动时缩小网格
    """
    
    def __init__(self, initial_balance: float = 100000.0):
        self.initial_balance = initial_balance
        self.balance = initial_balance
        self.position = 0.0
        self.trade_history = []
        self.balance_history = [initial_balance]
        self.base_price = 100.0
        
        # 网格参数（与基线一致）
        self.grid_levels = 5
        self.grid_spacing = 0.02
        self.min_buy_amount = 1000.0
        self.max_buy_amount = 5000.0
        
        # 风险参数（与基线一致）
        self.stop_loss = 0.008
        self.take_profit = 0.025
        self.max_drawdown = 0.08
        
        # 市场状态（使用 MarketStateHub）
        self.hub = get_market_state_hub()
        self.hub.enabled = True
        self.market_type = 'range_bound'
        self.last_price = 100.0
        
        # 网格价格水平
        self.grid_prices = []
        self._init_grids()
        
        # 跟踪最近 N 笔交易的价格，用于计算支撑位
        self.recent_prices = []
        self.max_recent_prices = 50
    
    def _init_grids(self):
        """初始化网格价格"""
        self.grid_prices = []
        for i in range(-self.grid_levels, self.grid_levels + 1):
            price = self.base_price * (1 + self.grid_spacing) ** i
            self.grid_prices.append(price)
        self.grid_prices.sort()
    
    def _find_support_level(self, price: float) -> float:
        """
        寻找最近的关键支撑位
        
        使用最近价格的最低点作为支撑位参考
        """
        if len(self.recent_prices) < 10:
            return self.base_price * 0.95
        
        # 找到最近的最低点
        recent_lows = []
        window = 10
        for i in range(len(self.recent_prices) - window):
            segment = self.recent_prices[i:i+window]
            local_min = min(segment)
            if local_min == segment[0] or local_min == segment[-1]:
                recent_lows.append(local_min)
        
        if recent_lows:
            return min(recent_lows)
        return min(self.recent_prices[-20:])
    
    def update(self, price: float, data: pd.Series) -> Dict[str, Any]:
        """
        更新策略状态（v4 下跌反弹增强版）
        
        核心增益逻辑：
        
        1. 【下跌反弹增强】下跌趋势中：
           - RSI < 35（超卖）+ 布林带下轨附近 → 积极买入（抄底）
           - 价格接近支撑位 → 加大买入力度
           - 买入量是基线的 1.5-2 倍
        
        2. 【横盘网格增强】横盘市场中：
           - RSI < 40 时在网格下沿加大买入
           - RSI > 60 时在网格上沿加大卖出
           - 波动率自适应网格间距
        
        3. 【上涨趋势增强】上涨趋势中：
           - RSI < 55 时正常追涨
           - RSI > 70 时减仓（防止回调）
        
        4. 【动态止损】基于波动率调整止损幅度
        """
        action = {"type": "hold", "price": price, "quantity": 0, "reason": ""}
        
        # 记录价格
        self.recent_prices.append(price)
        if len(self.recent_prices) > self.max_recent_prices:
            self.recent_prices.pop(0)
        
        # 使用 MarketStateHub 获取市场状态
        self.market_type = self.hub.get_market_regime(data)
        state = self.hub.get_full_state()
        confidence = state['confidence']
        vol_structure = self.hub.get_volatility_structure(data)
        rsi = state.get('rsi', 50)
        price_position = state.get('price_position', 0.5)
        vol_regime = vol_structure['vol_regime']
        
        # 计算当前总资产
        total_value = self.balance + self.position * price
        
        # === 增益1：波动率自适应网格间距 ===
        if vol_regime == "high":
            effective_spacing = self.grid_spacing * 1.5
        elif vol_regime == "low":
            effective_spacing = self.grid_spacing * 0.8
        else:
            effective_spacing = self.grid_spacing
        
        # === 增益2：动态止损（基于波动率） ===
        if vol_regime == "high":
            effective_stop_loss = self.stop_loss * 1.5  # 高波动放宽止损
        elif vol_regime == "low":
            effective_stop_loss = self.stop_loss * 0.8  # 低波动收紧止损
        else:
            effective_stop_loss = self.stop_loss
        
        # 止损检查
        if self.position > 0:
            unrealized_pnl = (price - self.last_price) / self.last_price
            if unrealized_pnl < -effective_stop_loss:
                sell_amount = self.position * price
                self.balance += sell_amount
                action = {"type": "sell", "price": price, "quantity": self.position, "reason": "stop_loss_v4"}
                self.trade_history.append({"action": "sell", "price": price, "quantity": self.position, "reason": "stop_loss_v4"})
                self.position = 0.0
        
        # 止盈检查
        if self.position > 0:
            unrealized_pnl = (price - self.last_price) / self.last_price
            if unrealized_pnl > self.take_profit:
                sell_amount = self.position * price
                self.balance += sell_amount
                action = {"type": "sell", "price": price, "quantity": self.position, "reason": "take_profit"}
                self.trade_history.append({"action": "sell", "price": price, "quantity": self.position, "reason": "take_profit"})
                self.position = 0.0
        
        # === 核心增益3：下跌反弹增强 ===
        # 下跌趋势中，利用 RSI 超卖 + 布林带下轨双重确认抄底
        if self.market_type == 'trending_down' and self.balance > self.min_buy_amount:
            # 计算价格从高点的跌幅
            if len(self.recent_prices) > 20:
                recent_high = max(self.recent_prices[-20:])
                drop_pct = (recent_high - price) / recent_high
            else:
                drop_pct = (self.base_price - price) / self.base_price
            
            # 条件1：RSI 超卖（< 35）
            # 条件2：布林带下轨附近（price_position < 0.3）
            # 条件3：价格从高点下跌超过 3%
            is_oversold = rsi < 35
            is_at_lower_band = price_position < 0.3
            is_significant_drop = drop_pct > 0.03
            
            if is_oversold and is_at_lower_band and is_significant_drop:
                # 三重确认 → 积极抄底！
                # 买入量是基线的 2 倍
                buy_amount = min(
                    self.max_buy_amount * 2.0,  # 加倍买入
                    self.balance * 0.4           # 最多用 40% 资金
                )
                quantity = buy_amount / price
                self.position += quantity
                self.balance -= buy_amount
                action = {"type": "buy", "price": price, "quantity": quantity, "reason": "bounce_buy_strong"}
                self.trade_history.append({"action": "buy", "price": price, "quantity": quantity, "reason": "bounce_buy_strong"})
            elif is_oversold and is_significant_drop:
                # 双重确认 → 正常抄底
                buy_amount = min(
                    self.max_buy_amount * 1.2,
                    self.balance * 0.25
                )
                quantity = buy_amount / price
                self.position += quantity
                self.balance -= buy_amount
                action = {"type": "buy", "price": price, "quantity": quantity, "reason": "bounce_buy_normal"}
                self.trade_history.append({"action": "buy", "price": price, "quantity": quantity, "reason": "bounce_buy_normal"})
            elif price < self.base_price * 0.95:
                # 基线逻辑：价格低于 95% 时承接
                buy_amount = min(self.max_buy_amount * 0.5, self.balance * 0.15)
                quantity = buy_amount / price
                self.position += quantity
                self.balance -= buy_amount
                action = {"type": "buy", "price": price, "quantity": quantity, "reason": "downward_buy_v4"}
                self.trade_history.append({"action": "buy", "price": price, "quantity": quantity, "reason": "downward_buy_v4"})
        
        # === 核心增益4：横盘网格增强 ===
        elif self.market_type == 'range_bound':
            # 横盘市场中，只在 RSI 极端值时交易，减少无效网格触发
            # 基线策略的网格触发阈值是 0.001，这里使用更严格的 RSI 过滤
            if rsi < 35 and self.balance > self.min_buy_amount:
                # RSI 超卖 → 在网格下沿买入
                for grid_price in self.grid_prices[:self.grid_levels]:  # 只在下半部分网格
                    if abs(price - grid_price) / grid_price < effective_spacing * 0.3:
                        buy_amount = min(
                            self.max_buy_amount * 1.3,
                            self.balance * 0.25
                        )
                        quantity = buy_amount / price
                        self.position += quantity
                        self.balance -= buy_amount
                        action = {"type": "buy", "price": price, "quantity": quantity, "reason": "grid_buy_v4"}
                        self.trade_history.append({"action": "buy", "price": price, "quantity": quantity, "reason": "grid_buy_v4"})
                        break
            elif rsi > 65 and self.position > 0:
                # RSI 超买 → 在网格上沿卖出
                for grid_price in self.grid_prices[self.grid_levels:]: 
                        self.trade_history.append({"action": "buy", "price": price, "quantity": quantity, "reason": "grid_buy_v4"})
                    elif price > grid_price and self.position > 0:
                        # RSI 越高卖出越多
                        if rsi > 65:
                            sell_scale = 1.5  # 超买时加大卖出
                        elif rsi > 55:
                            sell_scale = 1.2  # 偏高时适度卖出
                        else:
                            sell_scale = 1.0  # 正常卖出
                        
                        sell_quantity = self.position * 0.3 * sell_scale
                        sell_amount = sell_quantity * price
                        self.position -= sell_quantity
                        self.balance += sell_amount
                        action = {"type": "sell", "price": price, "quantity": sell_quantity, "reason": "grid_sell_v4"}
                        self.trade_history.append({"action": "sell", "price": price, "quantity": sell_quantity, "reason": "grid_sell_v4"})
        
        # === 核心增益5：上涨趋势增强 ===
        elif self.market_type == 'trending_up' and self.balance > self.min_buy_amount:
            # RSI < 55 时追涨，RSI > 70 时减仓
            if rsi < 55:
                buy_amount = min(self.max_buy_amount * 0.6, self.balance * 0.25)
                quantity = buy_amount / price
                self.position += quantity
                self.balance -= buy_amount
                action = {"type": "buy", "price": price, "quantity": quantity, "reason": "trend_follow_v4"}
                self.trade_history.append({"action": "buy", "price": price, "quantity": quantity, "reason": "trend_follow_v4"})
            elif rsi > 70 and self.position > 0:
                # RSI 超买时减仓
                sell_quantity = self.position * 0.3
                sell_amount = sell_quantity * price
                self.position -= sell_quantity
                self.balance += sell_amount
                action = {"type": "sell", "price": price, "quantity": sell_quantity, "reason": "overbought_reduce"}
                self.trade_history.append({"action": "sell", "price": price, "quantity": sell_quantity, "reason": "overbought_reduce"})
        
        self.last_price = price
        self.balance_history.append(self.balance + self.position * price)
        
        return action


# ==================== 绩效计算 ====================

def calculate_metrics(
    balance_history: List[float],
    trade_history: List[Dict],
    initial_balance: float,
    risk_free_rate: float = 0.02
) -> PerformanceMetrics:
    """
    计算完整绩效指标
    
    Args:
        balance_history: 余额历史
        trade_history: 交易历史
        initial_balance: 初始余额
        risk_free_rate: 无风险利率
        
    Returns:
        绩效指标
    """
    metrics = PerformanceMetrics()
    metrics.final_balance = balance_history[-1]
    metrics.total_return = (balance_history[-1] - initial_balance) / initial_balance
    
    # 计算收益率序列
    balance_series = pd.Series(balance_history)
    returns = balance_series.pct_change().dropna()
    
    if len(returns) == 0:
        return metrics
    
    # 年化收益率
    n_periods = len(returns)
    metrics.annual_return = (1 + metrics.total_return) ** (252 * 390 / n_periods) - 1
    
    # 波动率
    metrics.volatility = returns.std() * np.sqrt(252 * 390)
    
    # 夏普比率
    excess_returns = returns - risk_free_rate / (252 * 390)
    if metrics.volatility > 0:
        metrics.sharpe_ratio = (metrics.annual_return - risk_free_rate) / metrics.volatility
    
    # 最大回撤
    cumulative = (1 + returns).cumprod()
    running_max = cumulative.expanding().max()
    drawdown = (cumulative - running_max) / running_max
    metrics.max_drawdown = abs(drawdown.min())
    
    # 索提诺比率
    downside_returns = returns[returns < 0]
    if len(downside_returns) > 0:
        downside_std = downside_returns.std() * np.sqrt(252 * 390)
        if downside_std > 0:
            metrics.sortino_ratio = (metrics.annual_return - risk_free_rate) / downside_std
    
    # 卡玛比率
    if metrics.max_drawdown > 0:
        metrics.calmar_ratio = metrics.annual_return / metrics.max_drawdown
    
    # 交易统计
    metrics.total_trades = len(trade_history)
    
    if metrics.total_trades > 0:
        # 胜率
        buy_trades = [t for t in trade_history if t['action'] == 'buy']
        sell_trades = [t for t in trade_history if t['action'] == 'sell']
        
        if len(sell_trades) > 0:
            wins = sum(1 for t in sell_trades if t['price'] > 0)  # 简化：卖出即盈利
            metrics.win_rate = wins / len(sell_trades)
        
        # 盈亏比
        profits = [t['price'] * t['quantity'] for t in sell_trades if t['price'] > 0]
        if profits:
            avg_profit = np.mean(profits)
            avg_loss = np.mean([t['price'] * t['quantity'] for t in buy_trades]) if buy_trades else 1
            metrics.profit_loss_ratio = avg_profit / avg_loss if avg_loss > 0 else 0
    
    return metrics


# ==================== A/B 测试执行器 ====================

def run_ab_test(
    data: pd.Series,
    initial_balance: float = 100000.0,
    warmup_periods: int = 60
) -> Tuple[PerformanceMetrics, PerformanceMetrics]:
    """
    运行 A/B 对比测试
    
    Args:
        data: 价格序列
        initial_balance: 初始余额
        warmup_periods: 预热周期（用于计算指标）
        
    Returns:
        (基线指标, 优化指标)
    """
    # 重置 MarketStateHub
    hub = get_market_state_hub()
    hub.reset()
    hub.enabled = True
    
    # 初始化策略
    baseline = BaselineStrategySimulator(initial_balance)
    optimized = OptimizedStrategySimulator(initial_balance)
    
    # 运行回测
    for i in range(len(data)):
        price = data.iloc[i]
        current_data = data.iloc[:i+1]
        
        if i < warmup_periods:
            continue
        
        baseline.update(price, current_data)
        optimized.update(price, current_data)
    
    # 计算绩效
    baseline_metrics = calculate_metrics(
        baseline.balance_history, baseline.trade_history, initial_balance
    )
    optimized_metrics = calculate_metrics(
        optimized.balance_history, optimized.trade_history, initial_balance
    )
    
    return baseline_metrics, optimized_metrics


def compute_improvement(
    baseline: PerformanceMetrics,
    optimized: PerformanceMetrics
) -> Dict[str, float]:
    """
    计算优化策略相对于基线的改进幅度
    
    Args:
        baseline: 基线指标
        optimized: 优化指标
        
    Returns:
        改进幅度字典（百分比）
    """
    improvement = {}
    
    # 需要正向改进的指标
    positive_metrics = [
        'total_return', 'annual_return', 'sharpe_ratio',
        'sortino_ratio', 'calmar_ratio', 'win_rate',
        'profit_loss_ratio', 'final_balance'
    ]
    
    # 需要负向改进的指标（越小越好）
    negative_metrics = ['max_drawdown', 'volatility']
    
    for metric in positive_metrics:
        base_val = getattr(baseline, metric, 0)
        opt_val = getattr(optimized, metric, 0)
        if abs(base_val) > 1e-10:
            improvement[metric] = (opt_val - base_val) / abs(base_val) * 100
        else:
            improvement[metric] = 0.0 if abs(opt_val) < 1e-10 else 100.0
    
    for metric in negative_metrics:
        base_val = getattr(baseline, metric, 0)
        opt_val = getattr(optimized, metric, 0)
        if abs(base_val) > 1e-10:
            improvement[metric] = (base_val - opt_val) / abs(base_val) * 100
        else:
            improvement[metric] = 0.0
    
    return improvement


def is_significant_improvement(
    improvement: Dict[str, float],
    threshold: float = 5.0
) -> bool:
    """
    判断优化是否显著
    
    核心指标（年化收益、夏普、最大回撤）中至少2个改进超过阈值
    
    Args:
        improvement: 改进幅度
        threshold: 显著阈值（百分比）
        
    Returns:
        是否显著
    """
    key_metrics = ['annual_return', 'sharpe_ratio', 'max_drawdown']
    significant_count = 0
    
    for metric in key_metrics:
        if metric in improvement and improvement[metric] > threshold:
            significant_count += 1
    
    return significant_count >= 2


# ==================== 报告生成 ====================

def print_comparison_report(result: ABTestResult):
    """打印对比报告"""
    print("\n" + "=" * 70)
    print(f"📊 A/B 对比测试报告")
    print(f"   测试名称: {result.test_name}")
    print(f"   市场场景: {result.market_scenario}")
    print(f"   时间戳: {result.timestamp}")
    print("=" * 70)
    
    print(f"\n{'指标':<20} {'基线':<15} {'优化':<15} {'改进':<15}")
    print("-" * 65)
    
    metrics_display = [
        ("总收益率", "total_return", "{:.2%}"),
        ("年化收益率", "annual_return", "{:.2%}"),
        ("夏普比率", "sharpe_ratio", "{:.2f}"),
        ("索提诺比率", "sortino_ratio", "{:.2f}"),
        ("卡玛比率", "calmar_ratio", "{:.2f}"),
        ("最大回撤", "max_drawdown", "{:.2%}"),
        ("胜率", "win_rate", "{:.2%}"),
        ("盈亏比", "profit_loss_ratio", "{:.2f}"),
        ("交易次数", "total_trades", "{:d}"),
        ("波动率", "volatility", "{:.2%}"),
        ("最终余额", "final_balance", "{:.2f}"),
    ]
    
    for name, attr, fmt in metrics_display:
        base_val = getattr(result.baseline, attr, 0)
        opt_val = getattr(result.optimized, attr, 0)
        imp = result.improvement.get(attr, 0)
        
        base_str = fmt.format(base_val)
        opt_str = fmt.format(opt_val)
        
        if imp > 0:
            imp_str = f"+{imp:.1f}% ✅"
        elif imp < 0:
            imp_str = f"{imp:.1f}% ❌"
        else:
            imp_str = "0.0%"
        
        print(f"{name:<20} {base_str:<15} {opt_str:<15} {imp_str:<15}")
    
    print("-" * 65)
    verdict = "✅ 优化策略显著超越基线" if result.is_significant else "⚠️ 优化策略未显著超越基线，继续实验"
    print(f"\n  判定: {verdict}")
    print("=" * 70)


def save_report(result: ABTestResult, filepath: str = "reports/ab_comparison_report.json"):
    """保存报告到文件"""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    
    # 加载已有报告
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            try:
                existing = json.load(f)
            except:
                existing = []
    else:
        existing = []
    
    existing.append(result.to_dict())
    
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)
    
    logger.info(f"报告已保存到 {filepath}")


# ==================== 主测试流程 ====================

def run_all_scenarios():
    """运行所有市场场景的 A/B 测试"""
    print("\n" + "=" * 70)
    print("🚀 Aurora 量化策略 A/B 对比测试")
    print("   验证 MarketStateHub 增益性优化效果")
    print("=" * 70)
    
    scenarios = [
        (MarketScenario.RANGE_BOUND, "横盘市场"),
        (MarketScenario.TRENDING_UP, "上涨趋势"),
        (MarketScenario.TRENDING_DOWN, "下跌趋势"),
        (MarketScenario.VOLATILE, "高波动市场"),
        (MarketScenario.MIXED, "混合市场"),
    ]
    
    all_results = []
    
    for scenario, name in scenarios:
        print(f"\n{'─' * 60}")
        print(f"📈 测试场景: {name}")
        print(f"{'─' * 60}")
        
        # 生成市场数据
        data = generate_market_data(scenario, length=1000, seed=42)
        
        # 运行 A/B 测试
        baseline_metrics, optimized_metrics = run_ab_test(data)
        
        # 计算改进
        improvement = compute_improvement(baseline_metrics, optimized_metrics)
        significant = is_significant_improvement(improvement)
        
        # 构建结果
        result = ABTestResult(
            baseline=baseline_metrics,
            optimized=optimized_metrics,
            improvement=improvement,
            is_significant=significant,
            test_name=f"MarketStateHub_{name}",
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            market_scenario=name
        )
        
        print_comparison_report(result)
        all_results.append(result)
    
    # 汇总
    print(f"\n{'=' * 70}")
    print("📋 汇总报告")
    print(f"{'=' * 70}")
    
    significant_count = sum(1 for r in all_results if r.is_significant)
    print(f"\n  总测试场景: {len(all_results)}")
    print(f"  显著超越: {significant_count}/{len(all_results)}")
    
    if significant_count == len(all_results):
        print(f"\n  ✅ 结论: MarketStateHub 在所有场景中均显著超越基线策略")
    elif significant_count >= len(all_results) * 0.6:
        print(f"\n  ⚠️ 结论: MarketStateHub 在多数场景中表现优于基线")
    else:
        print(f"\n  ❌ 结论: MarketStateHub 需要进一步优化")
    
    # 保存报告
    save_report(all_results[0])  # 保存第一个场景的详细报告
    
    return all_results


if __name__ == "__main__":
    results = run_all_scenarios()
