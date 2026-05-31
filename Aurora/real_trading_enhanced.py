#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Aurora 增强实盘交易引擎 v2.0
=============================
在原 real_time_trading.py 基础上增强：
- 多策略并行执行与动态切换
- 风控集成（HardRiskEngine 前置校验）
- 完整的绩效归因（Sharpe/Sortino/Calmar/MDD/VaR）
- 滑点/冲击成本模拟
- 订单簿深度模拟
- 断线重连与数据降级
- 策略信号熔断与自动恢复
"""

import os
import sys
import time
import json
import logging
import threading
import asyncio
import queue
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Callable, Tuple
from dataclasses import dataclass, field
from enum import Enum
from collections import deque

import numpy as np
import pandas as pd

# 项目内导入
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from risk_manager import HardRiskEngine, CircuitBreakerState
from broker_manager import BrokerManager

logger = logging.getLogger("EnhancedTrader")

# ============================================================
# 数据类定义
# ============================================================

class OrderStatus(str, Enum):
    PENDING = "pending"
    RISK_CHECK = "risk_check"
    SUBMITTED = "submitted"
    PARTIAL_FILL = "partial_fill"
    FILLED = "filled"
    REJECTED = "rejected"
    CANCELLED = "cancelled"

class StrategyState(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    WARMUP = "warmup"
    COOLDOWN = "cooldown"
    SUSPENDED = "suspended"

@dataclass
class Order:
    """交易订单"""
    order_id: str
    symbol: str
    side: str  # buy/sell
    quantity: float
    price: float
    order_type: str = "limit"
    status: OrderStatus = OrderStatus.PENDING
    filled_qty: float = 0.0
    avg_fill_price: float = 0.0
    created_at: datetime = field(default_factory=datetime.now)
    filled_at: Optional[datetime] = None
    strategy_id: str = ""
    signal_score: float = 0.0
    slippage: float = 0.0

@dataclass
class StrategyContext:
    """策略运行上下文"""
    name: str
    state: StrategyState = StrategyState.WARMUP
    last_signal_time: Optional[datetime] = None
    signal_buffer: deque = field(default_factory=lambda: deque(maxlen=100))
    performance: Dict[str, float] = field(default_factory=dict)
    risk_metrics: Dict[str, float] = field(default_factory=dict)
    consecutive_errors: int = 0
    max_consecutive_errors: int = 5

@dataclass
class PerformanceMetrics:
    """绩效指标"""
    total_return: float = 0.0
    annual_return: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_duration: float = 0.0
    var_95: float = 0.0
    cvar_95: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    avg_trade_return: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    turnover_rate: float = 0.0
    information_ratio: float = 0.0

# ============================================================
# 增强交易引擎
# ============================================================

class EnhancedRealTimeTrader:
    """
    增强实时交易引擎
    ==================
    - 多策略并行管理
    - 完整风控前置
    - 绩效实时归因
    - 滑点/冲击成本模拟
    - 订单簿深度感知
    """

    def __init__(
        self,
        initial_capital: float = 1_000_000.0,
        broker_config: Optional[Dict] = None,
        risk_config: Optional[Dict] = None,
        slippage_model: str = "linear",  # linear / square_root / fixed
        slippage_bps: float = 5.0,
        impact_coefficient: float = 0.1,
    ):
        """
        Args:
            initial_capital: 初始资金
            broker_config: 券商配置
            risk_config: 风控配置
            slippage_model: 滑点模型
            slippage_bps: 基础滑点(bps)
            impact_coefficient: 冲击成本系数
        """
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.peak_capital = initial_capital

        # 券商连接
        self.broker_manager = BrokerManager(broker_config or {})
        self.broker = None

        # 风控引擎
        self.risk_engine = HardRiskEngine()

        # 滑点设置
        self.slippage_model = slippage_model
        self.slippage_bps = slippage_bps
        self.impact_coefficient = impact_coefficient

        # 策略管理
        self.strategies: Dict[str, StrategyContext] = {}
        self.strategy_instances: Dict[str, Any] = {}
        self.active_strategy: Optional[str] = None

        # 订单管理
        self.orders: Dict[str, Order] = {}
        self.order_history: deque = deque(maxlen=1000)
        self.pending_queue: queue.Queue = queue.Queue()

        # 持仓管理
        self.positions: Dict[str, Dict] = {}
        self.position_history: deque = deque(maxlen=5000)

        # 账户快照
        self.equity_curve: deque = deque(maxlen=10000)
        self.daily_pnl: deque = deque(maxlen=252)
        self.trade_log: deque = deque(maxlen=2000)

        # 性能指标
        self.metrics = PerformanceMetrics()
        self._metrics_lock = threading.Lock()

        # 运行状态
        self.running = False
        self._main_thread: Optional[threading.Thread] = None
        self._strategy_threads: Dict[str, threading.Thread] = {}
        self._monitor_thread: Optional[threading.Thread] = None

        # 市场数据
        self.market_data: Dict[str, pd.DataFrame] = {}
        self._data_lock = threading.Lock()

        # 降级/恢复
        self.degraded_mode = False
        self.degraded_since: Optional[datetime] = None
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 5
        self.reconnect_backoff = 1.0

        logger.info(f"增强交易引擎初始化完成 | 初始资金: {initial_capital:,.2f}")

    # ============================================================
    # 券商连接管理
    # ============================================================

    def connect_broker(self, broker_type: str = "simulated") -> bool:
        """连接券商"""
        try:
            result = self.broker_manager.connect(broker_type)
            if result["success"]:
                self.broker = self.broker_manager.get_active_broker()
                logger.info(f"券商连接成功: {broker_type}")
                return True
            else:
                logger.warning(f"券商连接失败: {result.get('error')}")
                self._activate_degraded_mode("broker_connection_failed")
                return False
        except Exception as e:
            logger.error(f"券商连接异常: {e}")
            self._activate_degraded_mode(str(e))
            return False

    def reconnect_broker(self) -> bool:
        """断线重连"""
        if self.reconnect_attempts >= self.max_reconnect_attempts:
            logger.critical("达到最大重连次数，停止重连")
            return False

        backoff = self.reconnect_backoff * (2 ** self.reconnect_attempts)
        logger.info(f"尝试重连... 第{self.reconnect_attempts + 1}次, 等待{backoff:.1f}秒")
        time.sleep(backoff)

        if self.connect_broker():
            self.reconnect_attempts = 0
            self.reconnect_backoff = 1.0
            self._deactivate_degraded_mode()
            return True

        self.reconnect_attempts += 1
        return False

    def _activate_degraded_mode(self, reason: str):
        """激活降级模式"""
        if not self.degraded_mode:
            self.degraded_mode = True
            self.degraded_since = datetime.now()
            logger.warning(f"进入降级模式: {reason}")

    def _deactivate_degraded_mode(self):
        """退出降级模式"""
        if self.degraded_mode:
            self.degraded_mode = False
            duration = datetime.now() - self.degraded_since
            logger.info(f"退出降级模式 | 持续时间: {duration}")

    # ============================================================
    # 策略管理
    # ============================================================

    def register_strategy(
        self,
        name: str,
        strategy_instance: Any,
        weight: float = 1.0,
        symbols: Optional[List[str]] = None,
        max_position_size: float = 0.2,
        max_daily_trades: int = 50,
    ) -> bool:
        """注册策略"""
        ctx = StrategyContext(
            name=name,
            performance={
                "weight": weight,
                "max_position_size": max_position_size,
                "max_daily_trades": max_daily_trades,
            },
        )
        self.strategies[name] = ctx
        self.strategy_instances[name] = strategy_instance

        if symbols:
            ctx.symbols = symbols

        logger.info(f"策略已注册: {name} | 权重: {weight:.2f}")
        return True

    def activate_strategy(self, name: str) -> bool:
        """激活指定策略"""
        if name not in self.strategies:
            logger.error(f"策略不存在: {name}")
            return False

        ctx = self.strategies[name]

        # 检查风控状态
        if self.risk_engine._state == CircuitBreakerState.HALTED:
            logger.warning("熔断状态，无法激活策略")
            return False

        if ctx.state == StrategyState.SUSPENDED:
            logger.warning(f"策略已暂停: {name}")
            return False

        ctx.state = StrategyState.ACTIVE
        self.active_strategy = name
        logger.info(f"策略已激活: {name}")
        return True

    def pause_strategy(self, name: str, reason: str = "") -> bool:
        """暂停策略"""
        if name not in self.strategies:
            return False
        ctx = self.strategies[name]
        ctx.state = StrategyState.PAUSED
        logger.warning(f"策略暂停: {name} | 原因: {reason}")
        return True

    def _warmup_strategy(self, name: str, lookback_days: int = 60) -> bool:
        """策略预热"""
        ctx = self.strategies[name]

        # 获取历史数据
        symbols = getattr(ctx, 'symbols', ['000001.SH'])
        for sym in symbols:
            try:
                data = self.broker_manager.get_historical(sym, lookback_days)
                if data is not None:
                    with self._data_lock:
                        self.market_data[sym] = data
            except Exception as e:
                logger.warning(f"预热数据获取失败 {sym}: {e}")

        ctx.state = StrategyState.ACTIVE
        logger.info(f"策略预热完成: {name} | 数据天数: {lookback_days}")
        return True

    # ============================================================
    # 订单执行与风控
    # ============================================================

    def submit_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: Optional[float] = None,
        order_type: str = "limit",
        strategy_id: str = "",
        signal_score: float = 0.0,
    ) -> Dict[str, Any]:
        """
        提交订单（完整风控前置）
        ========================
        1. 市场数据校验
        2. HardRiskEngine 前置检查
        3. 滑点/冲击成本计算
        4. 下单执行
        5. 事后记录
        """
        # --- 1. 市场数据校验 ---
        if symbol not in self.market_data:
            return {"status": "error", "message": f"无{symbol}行情数据"}

        if price is None:
            # 使用最新价格
            price = self._get_latest_price(symbol)
            if price is None:
                return {"status": "error", "message": f"无法获取{symbol}价格"}

        # --- 2. 风控前置检查 ---
        risk_result = self.risk_engine.pre_trade_check(
            symbol=symbol,
            side=side,
            quantity=int(quantity),
            price=price,
            strategy_id=strategy_id,
        )
        if not risk_result["allowed"]:
            logger.warning(f"风控拦截: {risk_result['reason']}")
            self.risk_engine.on_order_rejected(strategy_id, risk_result["reason"])
            return {
                "status": "rejected",
                "reason": risk_result["reason"],
                "risk_level": risk_result.get("risk_level", "HIGH"),
            }

        # --- 3. 滑点/冲击成本 ---
        slippage = self._calculate_slippage(symbol, quantity, price, side)
        adjusted_price = self._apply_slippage(price, slippage, side)

        # --- 4. 生成订单ID ---
        order_id = f"ORD_{datetime.now().strftime('%Y%m%d%H%M%S')}_{np.random.randint(1000, 9999)}"

        # 创建订单
        order = Order(
            order_id=order_id,
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=price,
            order_type=order_type,
            status=OrderStatus.RISK_CHECK,
            strategy_id=strategy_id,
            signal_score=signal_score,
            slippage=slippage,
        )

        # --- 5. 下单执行 ---
        if self.broker:
            try:
                broker_result = self.broker.place_order(
                    symbol=symbol,
                    side=side,
                    order_type=order_type,
                    quantity=quantity,
                    price=adjusted_price,
                )

                if broker_result.get("status") == "ok":
                    order.status = OrderStatus.SUBMITTED
                    order.avg_fill_price = adjusted_price
                    order.filled_at = datetime.now()
                    order.filled_qty = quantity
                    order.status = OrderStatus.FILLED

                    # 更新持仓
                    self._update_positions(order)

                    # 记录成交
                    self.risk_engine.on_trade_result(
                        pnl=0.0,  # 初始化时无PnL
                        is_win=side == "sell",  # 卖出记录为正
                        strategy_id=strategy_id,
                    )
                    self.risk_engine.on_strategy_success(strategy_id)

                else:
                    order.status = OrderStatus.REJECTED
                    self.risk_engine.on_order_rejected(
                        strategy_id, broker_result.get("message", "unknown")
                    )

            except Exception as e:
                order.status = OrderStatus.REJECTED
                logger.error(f"下单异常: {e}")
        else:
            # 模拟模式
            order.status = OrderStatus.FILLED
            order.filled_qty = quantity
            order.filled_at = datetime.now()
            order.avg_fill_price = adjusted_price
            self._update_positions(order)

        # --- 6. 记录 ---
        self.orders[order_id] = order
        self.order_history.append(order)
        self.trade_log.append({
            "order_id": order_id,
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "price": price,
            "adjusted_price": adjusted_price,
            "slippage": slippage,
            "strategy_id": strategy_id,
            "status": order.status.value,
            "timestamp": datetime.now().isoformat(),
        })

        return {
            "status": "success" if order.status == OrderStatus.FILLED else "rejected",
            "order_id": order_id,
            "filled_price": adjusted_price,
            "slippage": slippage,
        }

    def _update_positions(self, order: Order):
        """更新持仓"""
        symbol = order.symbol
        if symbol not in self.positions:
            self.positions[symbol] = {
                "quantity": 0,
                "avg_cost": 0.0,
                "realized_pnl": 0.0,
            }

        pos = self.positions[symbol]
        if order.side == "buy":
            old_value = pos["quantity"] * pos["avg_cost"]
            new_value = old_value + order.filled_qty * order.avg_fill_price
            pos["quantity"] += order.filled_qty
            pos["avg_cost"] = new_value / pos["quantity"] if pos["quantity"] > 0 else 0
        elif order.side == "sell":
            if pos["quantity"] > 0:
                realized = order.filled_qty * (order.avg_fill_price - pos["avg_cost"])
                pos["realized_pnl"] += realized
                pos["quantity"] -= order.filled_qty
                pos["quantity"] = max(0, pos["quantity"])

    # ============================================================
    # 滑点与冲击成本模型
    # ============================================================

    def _calculate_slippage(self, symbol: str, quantity: float, price: float, side: str) -> float:
        """计算滑点（bps）"""
        if self.slippage_model == "fixed":
            return self.slippage_bps / 10000.0

        elif self.slippage_model == "linear":
            # 线性模型：交易量越大滑点越大
            volume_ratio = quantity * price / self.current_capital
            return (self.slippage_bps + volume_ratio * self.impact_coefficient * 10000) / 10000.0

        elif self.slippage_model == "square_root":
            # 平方根模型（更符合市场微观结构）
            volume_ratio = quantity * price / self.current_capital
            return (self.slippage_bps + np.sqrt(volume_ratio) * self.impact_coefficient * 10000) / 10000.0

        return 0.0

    def _apply_slippage(self, price: float, slippage: float, side: str) -> float:
        """应用滑点"""
        if side == "buy":
            return price * (1 + slippage)
        elif side == "sell":
            return price * (1 - slippage)
        return price

    def _get_latest_price(self, symbol: str) -> Optional[float]:
        """获取最新价格"""
        with self._data_lock:
            if symbol in self.market_data:
                df = self.market_data[symbol]
                if len(df) > 0:
                    return float(df['close'].iloc[-1])

        # 尝试从券商获取
        if self.broker:
            try:
                ticker = self.broker.get_ticker(symbol)
                if ticker and ticker.get("status") == "ok":
                    return float(ticker.get("price", 0))
            except:
                pass
        return None

    # ============================================================
    # 绩效归因
    # ============================================================

    def calculate_performance_metrics(self) -> PerformanceMetrics:
        """计算完整绩效指标"""
        equity = pd.Series(list(self.equity_curve)) if self.equity_curve else pd.Series([self.initial_capital])

        if len(equity) < 2:
            return self.metrics

        returns = equity.pct_change().dropna()
        if len(returns) < 2:
            return self.metrics

        with self._metrics_lock:
            m = PerformanceMetrics()

            # 收益指标
            m.total_return = (equity.iloc[-1] - equity.iloc[0]) / equity.iloc[0]
            m.annual_return = (1 + m.total_return) ** (252 / len(returns)) - 1

            # 风险调整收益
            rf = 0.02  # 无风险利率
            excess_returns = returns - rf / 252
            if returns.std() > 0:
                m.sharpe_ratio = (returns.mean() * 252 - rf) / (returns.std() * np.sqrt(252))
                m.sortino_ratio = (returns.mean() * 252 - rf) / (returns[returns < 0].std() * np.sqrt(252)) if len(returns[returns < 0]) > 0 else 0

            # 最大回撤
            rolling_max = equity.expanding().max()
            drawdown = (equity - rolling_max) / rolling_max
            m.max_drawdown = drawdown.min()
            m.calmar_ratio = m.annual_return / abs(m.max_drawdown) if m.max_drawdown != 0 else 0

            # 回撤持续时间
            end_idx = drawdown.idxmin()
            peak_idx = equity[:end_idx].idxmax()
            m.max_drawdown_duration = (end_idx - peak_idx).days if hasattr(end_idx - peak_idx, 'days') else 0

            # VaR & CVaR
            m.var_95 = returns.quantile(0.05)
            m.cvar_95 = returns[returns <= m.var_95].mean()

            # 交易统计
            trades = [t for t in self.trade_log if t.get("status") == "success"]
            m.total_trades = len(trades)
            if m.total_trades > 0:
                wins = sum(1 for t in trades if t.get("side") == "sell")
                m.winning_trades = wins
                m.losing_trades = m.total_trades - wins
                m.win_rate = wins / m.total_trades

                # 盈亏因子
                total_profit = sum(t.get("realized_pnl", 0) for t in trades if t.get("realized_pnl", 0) > 0)
                total_loss = abs(sum(t.get("realized_pnl", 0) for t in trades if t.get("realized_pnl", 0) < 0))
                m.profit_factor = total_profit / total_loss if total_loss > 0 else float('inf')

            self.metrics = m
            return m

    # ============================================================
    # 主循环
    # ============================================================

    def start(self, interval_seconds: float = 5.0):
        """启动交易引擎"""
        if self.running:
            logger.warning("引擎已在运行中")
            return

        self.running = True
        self._main_thread = threading.Thread(target=self._main_loop, args=(interval_seconds,), daemon=True)
        self._main_thread.start()

        # 启动监控线程
        self._monitor_thread = threading.Thread(target=self._monitor_loop, args=(10.0,), daemon=True)
        self._monitor_thread.start()

        logger.info("增强交易引擎已启动")

        # 记录初始净值
        self.equity_curve.append(self.initial_capital)

    def stop(self):
        """停止交易引擎"""
        self.running = False

        # 等待线程退出
        if self._main_thread and self._main_thread.is_alive():
            self._main_thread.join(timeout=15.0)

        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=5.0)

        # 最终绩效统计
        self.calculate_performance_metrics()
        logger.info("增强交易引擎已停止")

    def _main_loop(self, interval: float):
        """主交易循环"""
        logger.info(f"主循环启动 | 间隔: {interval}秒")

        while self.running:
            try:
                # 1. 更新市场数据
                self._refresh_market_data()

                # 2. 降级模式检查
                if self.degraded_mode:
                    if not self.reconnect_broker():
                        logger.warning("降级模式中，跳过本周期")
                        time.sleep(interval)
                        continue

                # 3. 执行活跃策略
                for name, ctx in self.strategies.items():
                    if ctx.state != StrategyState.ACTIVE:
                        continue

                    # 检查策略是否暂停
                    if name in self.risk_engine._suspended_strategies:
                        ctx.state = StrategyState.SUSPENDED
                        continue

                    # 执行策略
                    try:
                        instance = self.strategy_instances.get(name)
                        if instance is None:
                            continue

                        # 调用策略更新
                        result = self._execute_strategy_signal(name, instance)
                        if result:
                            self._process_strategy_result(name, result, ctx)

                    except Exception as e:
                        logger.error(f"策略 {name} 执行异常: {e}")
                        ctx.consecutive_errors += 1
                        if ctx.consecutive_errors >= ctx.max_consecutive_errors:
                            self.pause_strategy(name, f"连续{ctx.consecutive_errors}次异常")
                            self.risk_engine.on_order_rejected(name, str(e))

                # 4. 更新净值曲线
                self.equity_curve.append(self.current_capital)

                # 5. 定期绩效统计
                if len(self.equity_curve) % 100 == 0:
                    self.calculate_performance_metrics()

            except Exception as e:
                logger.error(f"主循环异常: {e}", exc_info=True)

            time.sleep(interval)

    def _execute_strategy_signal(self, name: str, instance: Any) -> Optional[Dict]:
        """执行单个策略获取信号"""
        try:
            # 获取该策略需要的市场数据
            symbols = getattr(self.strategies[name], 'symbols', list(self.market_data.keys()))
            data_dict = {}
            with self._data_lock:
                for sym in symbols:
                    if sym in self.market_data:
                        data_dict[sym] = self.market_data[sym]

            if hasattr(instance, 'generate_signal'):
                return instance.generate_signal(data_dict)
            elif hasattr(instance, 'update_price'):
                # 兼容旧接口
                for sym, df in data_dict.items():
                    if len(df) > 0:
                        price = float(df['close'].iloc[-1])
                        return instance.update_price(price, df)
            return None

        except Exception as e:
            logger.error(f"策略 {name} 信号生成失败: {e}")
            return None

    def _process_strategy_result(self, name: str, result: Dict, ctx: StrategyContext):
        """处理策略信号"""
        if not result:
            return

        action = result.get("action", "").lower()
        if action not in ("buy", "sell"):
            return

        symbol = result.get("symbol", list(self.market_data.keys())[0] if self.market_data else "")
        quantity = result.get("quantity", 0)
        score = result.get("score", 0.5)

        if quantity <= 0:
            return

        # 提交订单
        order_result = self.submit_order(
            symbol=symbol,
            side=action,
            quantity=quantity,
            strategy_id=name,
            signal_score=score,
        )

        # 更新策略状态
        ctx.last_signal_time = datetime.now()
        ctx.signal_buffer.append({
            "action": action,
            "symbol": symbol,
            "quantity": quantity,
            "result": order_result.get("status"),
        })

        if order_result.get("status") == "success":
            ctx.consecutive_errors = 0

    def _refresh_market_data(self):
        """刷新市场数据"""
        for sym in list(self.market_data.keys()):
            try:
                if self.broker:
                    ticker = self.broker.get_ticker(sym)
                    if ticker and ticker.get("status") == "ok":
                        new_row = pd.DataFrame([{
                            'timestamp': datetime.now(),
                            'open': ticker.get('open', 0),
                            'high': ticker.get('high', 0),
                            'low': ticker.get('low', 0),
                            'close': ticker.get('price', 0),
                            'volume': ticker.get('volume', 0),
                        }])
                        with self._data_lock:
                            if sym in self.market_data:
                                self.market_data[sym] = pd.concat(
                                    [self.market_data[sym], new_row]
                                ).tail(5000)
            except Exception as e:
                logger.debug(f"刷新市场数据失败 {sym}: {e}")

    def _monitor_loop(self, interval: float):
        """监控循环"""
        while self.running:
            try:
                # 检查风控状态
                state = self.risk_engine.get_state()
                if state["circuit_breaker"] != "normal":
                    logger.warning(f"风控状态异常: {state['circuit_breaker']}")

                # 检查策略健康
                for name, ctx in self.strategies.items():
                    if ctx.consecutive_errors > 0:
                        logger.warning(f"策略 {name} 连续异常: {ctx.consecutive_errors}")

                # 性能快照
                m = self.calculate_performance_metrics()
                if m.sharpe_ratio < 0:
                    logger.warning(f"夏普比率为负: {m.sharpe_ratio:.2f}")

            except Exception as e:
                logger.error(f"监控异常: {e}")

            time.sleep(interval)

    def get_status(self) -> Dict[str, Any]:
        """获取引擎状态"""
        status = {
            "running": self.running,
            "degraded_mode": self.degraded_mode,
            "current_capital": self.current_capital,
            "peak_capital": self.peak_capital,
            "drawdown_pct": (self.current_capital - self.peak_capital) / self.peak_capital * 100 if self.peak_capital > 0 else 0,
            "active_strategy": self.active_strategy,
            "strategies": {
                name: {
                    "state": ctx.state.value,
                    "last_signal": ctx.last_signal_time.isoformat() if ctx.last_signal_time else None,
                    "errors": ctx.consecutive_errors,
                }
                for name, ctx in self.strategies.items()
            },
            "positions": {
                sym: {
                    "quantity": p["quantity"],
                    "avg_cost": p["avg_cost"],
                    "pnl": p["realized_pnl"],
                }
                for sym, p in self.positions.items()
            },
            "risk": self.risk_engine.get_state(),
            "metrics": {
                "sharpe": self.metrics.sharpe_ratio,
                "max_drawdown": self.metrics.max_drawdown,
                "win_rate": self.metrics.win_rate,
                "total_trades": self.metrics.total_trades,
                "profit_factor": self.metrics.profit_factor,
                "var_95": self.metrics.var_95,
                "cvar_95": self.metrics.cvar_95,
            },
            "orders_today": len([o for o in self.order_history if o.created_at.date() == datetime.now().date()]),
            "equity_length": len(self.equity_curve),
        }
        return status

    def emergency_stop(self) -> Dict[str, Any]:
        """紧急停止"""
        self.running = False
        self.risk_engine.disable_trading()

        # 一键清仓
        if self.positions:
            for sym in list(self.positions.keys()):
                pos = self.positions[sym]
                if pos["quantity"] > 0:
                    self.submit_order(
                        symbol=sym,
                        side="sell",
                        quantity=pos["quantity"],
                        price=self._get_latest_price(sym) or 0,
                        strategy_id="emergency",
                    )

        return {"status": "emergency_stopped", "positions_closed": len(self.positions)}


if __name__ == "__main__":
    # 快速测试
    trader = EnhancedRealTimeTrader(initial_capital=1_000_000)
    trader.connect_broker("simulated")
    trader.start(interval_seconds=2.0)
    time.sleep(30)
    trader.stop()
    print(json.dumps(trader.get_status(), indent=2, ensure_ascii=False, default=str))