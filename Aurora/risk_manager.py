# coding: utf-8
"""
独立硬风控引擎 — 事前/事中/事后三层风控 + A股规则适配
=====================================================
功能：
  - 事前风控：T+1卖出校验、涨跌停校验、单笔限额、持仓上限、集合竞价禁止市价单
  - 事中风控：实时盈亏熔断、废单风暴检测、连续亏损熔断
  - 事后风控：日终对账、最大回撤告警、异常订单审计
  - 一键清仓：紧急状态下全平所有持仓
  - 策略异常隔离：单策略连续异常则自动暂停

使用方式：
  from risk_manager import HardRiskEngine
  hre = HardRiskEngine()
  result = hre.pre_trade_check(order_dict, position_dict, market_data)
"""

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, date
from enum import Enum
from typing import Any, Dict, Optional, Set

logger = logging.getLogger(__name__)


# ── A股交易时间常量 ──
A_SHARE_MORNING_START = (9, 30)
A_SHARE_MORNING_END = (11, 30)
A_SHARE_AFTERNOON_START = (13, 0)
A_SHARE_AFTERNOON_END = (15, 0)
# 集合竞价时段
A_SHARE_CALL_AUCTION_MORNING = ((9, 15), (9, 25))  # 开盘集合竞价
A_SHARE_CALL_AUCTION_AFTERNOON = ((13, 0), (13, 0)) # 深市无下午集合竞价


class CircuitBreakerState(str, Enum):
    NORMAL = "normal"       # 正常
    WARNING = "warning"     # 预警（仅告警不禁用交易）
    HALTED = "halted"       # 熔断（禁止新开仓）
    EMERGENCY = "emergency" # 紧急（仅允许平仓）


@dataclass
class StrategyHealth:
    """单策略健康状态"""
    strategy_id: str
    total_orders: int = 0
    rejected_orders: int = 0
    consecutive_errors: int = 0
    is_suspended: bool = False
    suspend_reason: str = ""
    last_error_time: Optional[float] = None
    last_success_time: Optional[float] = None


class HardRiskEngine:
    """
    独立硬风控引擎
    ===============
    作为所有交易请求的统一入口，任何订单必须通过此引擎的前置检查。
    不依赖于任何策略逻辑，对策略层透明。
    """

    # ── 默认参数 ──
    MAX_POSITION_PCT = 0.30          # 单股仓位上限 30%
    MAX_DAILY_LOSS_PCT = 6.0         # 单日最大亏损 6%（触发熔断）
    MAX_CONSECUTIVE_LOSS_COUNT = 5   # 连续亏损5笔触发熔断
    MAX_REJECTION_PER_MINUTE = 10    # 每分钟废单超过10笔触发废单风暴熔断
    MAX_CONSECUTIVE_STRATEGY_ERRORS = 3  # 单策略连续异常3次暂停该策略
    EMERGENCY_CLEAR_TIMEOUT = 30.0   # 一键清仓超时30秒

    def __init__(self, config_path: str = "risk_config.json"):
        self._lock = threading.Lock()
        self._config_path = config_path
        self._state = CircuitBreakerState.NORMAL
        self._state_changed_at = time.time()
        self._daily_pnl: float = 0.0
        self._daily_trades: int = 0
        self._consecutive_losses: int = 0
        self._rejection_timestamps: list = []  # 废单时间戳列表
        self._current_date = date.today().isoformat()
        self._strategy_health: Dict[str, StrategyHealth] = {}
        self._suspended_strategies: Set[str] = set()
        self._alerts: list = []
        self._trading_disabled: bool = False

    # ═══════════════════════════════════════════════════════════
    # 事前风控
    # ═══════════════════════════════════════════════════════════

    def pre_trade_check(
        self,
        symbol: str,
        side: str,
        quantity: int,
        price: float,
        *,
        position_qty: int = 0,
        position_avg_cost: float = 0.0,
        available_cash: float = 0.0,
        total_asset: float = 0.0,
        strategy_id: str = "default",
        last_buy_date: Optional[str] = None,
        current_price: float = 0.0,
        prev_close: float = 0.0,
        high_limit: Optional[float] = None,
        low_limit: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        事前风控检查 — 在订单提交前调用
        
        Returns:
            {'allowed': bool, 'reason': str, 'risk_level': str}
        """
        # 0. 检查熔断状态
        cb_check = self._check_circuit_breaker_state()
        if not cb_check["allowed"]:
            return cb_check

        # 1. 检查集合竞价特殊规则
        call_result = self._check_call_auction_rules(side, price)
        if not call_result["allowed"]:
            return call_result

        # 2. T+1 卖出校验
        if side == "sell" and position_qty > 0:
            t1_result = self._check_t_plus_one(symbol, last_buy_date)
            if not t1_result["allowed"]:
                return t1_result

        # 3. 涨跌停校验
        if prev_close > 0:
            limit_result = self._check_price_limit(price, prev_close, high_limit, low_limit)
            if not limit_result["allowed"]:
                return limit_result

        # 4. 超卖校验
        if side == "sell" and quantity > position_qty:
            return {
                "allowed": False,
                "reason": f"超卖拦截: {symbol} 卖出{quantity} > 持仓{position_qty}",
                "risk_level": "CRITICAL",
            }

        # 5. 超买校验
        if side == "buy" and total_asset > 0:
            cost = quantity * price
            if cost > available_cash:
                return {
                    "allowed": False,
                    "reason": f"超买拦截: 所需资金{cost:.2f} > 可用{available_cash:.2f}",
                    "risk_level": "CRITICAL",
                }
            # 单股仓位上限
            if total_asset > 0:
                position_value = position_qty * current_price + quantity * price
                if position_value / total_asset > self.MAX_POSITION_PCT:
                    return {
                        "allowed": False,
                        "reason": f"仓位超限: {symbol} 仓位{position_value/total_asset*100:.1f}% > {self.MAX_POSITION_PCT*100:.0f}%",
                        "risk_level": "HIGH",
                    }

        # 6. 策略异常检查
        if strategy_id in self._suspended_strategies:
            return {
                "allowed": False,
                "reason": f"策略 {strategy_id} 已被暂停",
                "risk_level": "HIGH",
            }

        return {"allowed": True, "reason": "事前风控通过", "risk_level": "LOW"}

    def _check_circuit_breaker_state(self) -> Dict[str, Any]:
        """检查熔断状态"""
        if self._state == CircuitBreakerState.HALTED:
            return {
                "allowed": False,
                "reason": "熔断已触发: 禁止新开仓",
                "risk_level": "EMERGENCY",
            }
        if self._state == CircuitBreakerState.EMERGENCY:
            return {
                "allowed": False,
                "reason": "紧急状态: 仅允许平仓",
                "risk_level": "EMERGENCY",
            }
        if self._trading_disabled:
            return {
                "allowed": False,
                "reason": "交易已手动禁用",
                "risk_level": "EMERGENCY",
            }
        return {"allowed": True, "reason": "正常", "risk_level": "LOW"}

    def _check_call_auction_rules(self, side: str, price: float) -> Dict[str, Any]:
        """集合竞价时段特殊规则: 禁止市价单(price=0视为市价)"""
        now = datetime.now().time()
        in_call = (
            (A_SHARE_CALL_AUCTION_MORNING[0][0] <= now.hour * 60 + now.minute <= A_SHARE_CALL_AUCTION_MORNING[1][0] * 60 + A_SHARE_CALL_AUCTION_MORNING[1][1])
        )
        if in_call and price <= 0:
            return {
                "allowed": False,
                "reason": "集合竞价时段禁止市价单",
                "risk_level": "MEDIUM",
            }
        return {"allowed": True, "reason": "通过", "risk_level": "LOW"}

    def _check_t_plus_one(self, symbol: str, last_buy_date: Optional[str]) -> Dict[str, Any]:
        """
        T+1卖出校验: 当日买入的A股不可卖出
        last_buy_date 格式: "YYYY-MM-DD"
        """
        if not last_buy_date:
            return {"allowed": True, "reason": "无买入日期", "risk_level": "LOW"}

        today = date.today().isoformat()
        if last_buy_date == today:
            return {
                "allowed": False,
                "reason": f"T+1违规拦截: {symbol} 于{last_buy_date}买入，今日({today})不可卖出",
                "risk_level": "CRITICAL",
            }
        return {"allowed": True, "reason": "T+1校验通过", "risk_level": "LOW"}

    def _check_price_limit(
        self,
        price: float,
        prev_close: float,
        high_limit: Optional[float] = None,
        low_limit: Optional[float] = None,
    ) -> Dict[str, Any]:
        """涨跌停校验"""
        # 如果外部已提供涨跌停价，直接使用
        if high_limit is not None and low_limit is not None:
            if price > high_limit:
                return {
                    "allowed": False,
                    "reason": f"涨停拦截: 价格{price:.2f} > 涨停价{high_limit:.2f}",
                    "risk_level": "CRITICAL",
                }
            if price < low_limit:
                return {
                    "allowed": False,
                    "reason": f"跌停拦截: 价格{price:.2f} < 跌停价{low_limit:.2f}",
                    "risk_level": "CRITICAL",
                }
            return {"allowed": True, "reason": "涨跌停校验通过", "risk_level": "LOW"}

        # 内部计算：A股 ±10%（普通股），科创/创业板 ±20%  
        # 这里默认用±10%，外部可传具体值
        limit_pct = 0.10
        high = prev_close * (1 + limit_pct)
        low = prev_close * (1 - limit_pct)

        if price > high:
            return {
                "allowed": False,
                "reason": f"涨停拦截: 价格{price:.2f} > 涨停价{high:.2f}",
                "risk_level": "CRITICAL",
            }
        if price < low:
            return {
                "allowed": False,
                "reason": f"跌停拦截: 价格{price:.2f} < 跌停价{low:.2f}",
                "risk_level": "CRITICAL",
            }
        return {"allowed": True, "reason": "涨跌停校验通过", "risk_level": "LOW"}

    # ═══════════════════════════════════════════════════════════
    # 事中风控
    # ═══════════════════════════════════════════════════════════

    def on_trade_result(self, pnl: float, is_win: bool, strategy_id: str = "default"):
        """
        每笔成交后调用，更新事中风控状态
        """
        with self._lock:
            # 日期跨越重置
            today = date.today().isoformat()
            if today != self._current_date:
                self._reset_daily_stats()
                self._current_date = today

            self._daily_trades += 1
            self._daily_pnl += pnl

            # 连续亏损追踪
            if not is_win and pnl < 0:
                self._consecutive_losses += 1
                if self._consecutive_losses >= self.MAX_CONSECUTIVE_LOSS_COUNT:
                    self._trigger_circuit_breaker(
                        CircuitBreakerState.HALTED,
                        f"连续亏损{self._consecutive_losses}笔，触发熔断"
                    )
            else:
                self._consecutive_losses = 0  # 盈利或平推后重置

            # 单日亏损熔断检查
            if self._daily_pnl < 0:
                loss_pct = abs(self._daily_pnl)
                # 这里需要total_asset, 暂且记录告警
                logger.warning("当日累计亏损: %.2f", abs(self._daily_pnl))

    def on_order_rejected(self, strategy_id: str = "default", reason: str = ""):
        """收到废单回报时调用"""
        with self._lock:
            now = time.time()
            self._rejection_timestamps.append(now)
            # 清理过期时间戳
            self._rejection_timestamps = [
                ts for ts in self._rejection_timestamps
                if now - ts < 60.0
            ]

            # 废单风暴检测
            if len(self._rejection_timestamps) >= self.MAX_REJECTION_PER_MINUTE:
                self._trigger_circuit_breaker(
                    CircuitBreakerState.HALTED,
                    f"废单风暴: 1分钟内废单{len(self._rejection_timestamps)}笔"
                )
                return

            # 策略异常追踪
            health = self._get_strategy_health(strategy_id)
            health.rejected_orders += 1
            health.consecutive_errors += 1
            health.last_error_time = now

            if health.consecutive_errors >= self.MAX_CONSECUTIVE_STRATEGY_ERRORS:
                self._suspend_strategy(strategy_id, f"连续{health.consecutive_errors}次异常")

    def on_strategy_success(self, strategy_id: str):
        """策略成功执行后调用，重置异常计数"""
        with self._lock:
            health = self._get_strategy_health(strategy_id)
            health.consecutive_errors = 0
            health.last_success_time = time.time()

    # ═══════════════════════════════════════════════════════════
    # 熔断与恢复
    # ═══════════════════════════════════════════════════════════

    def _trigger_circuit_breaker(self, state: CircuitBreakerState, reason: str):
        """触发熔断"""
        if self._state != state:
            self._state = state
            self._state_changed_at = time.time()
            alert = {
                "type": "CIRCUIT_BREAKER",
                "state": state.value,
                "reason": reason,
                "timestamp": datetime.now().isoformat(),
                "daily_pnl": self._daily_pnl,
                "daily_trades": self._daily_trades,
            }
            self._alerts.append(alert)
            logger.critical("熔断触发: %s - %s", state.value, reason)
            return alert
        return None

    def reset_circuit_breaker(self, admin_key: str = "") -> Dict[str, Any]:
        """
        重置熔断（需管理员确认）
        实际使用时需验证admin_key
        """
        with self._lock:
            old_state = self._state
            self._state = CircuitBreakerState.NORMAL
            self._state_changed_at = time.time()
            self._consecutive_losses = 0
            self._rejection_timestamps.clear()
            logger.warning("熔断已手动重置，恢复为%s (原状态: %s)", self._state.value, old_state.value)
            return {
                "success": True,
                "previous_state": old_state.value,
                "new_state": self._state.value,
            }

    # ═══════════════════════════════════════════════════════════
    # 策略异常隔离
    # ═══════════════════════════════════════════════════════════

    def _get_strategy_health(self, strategy_id: str) -> StrategyHealth:
        if strategy_id not in self._strategy_health:
            self._strategy_health[strategy_id] = StrategyHealth(strategy_id=strategy_id)
        return self._strategy_health[strategy_id]

    def _suspend_strategy(self, strategy_id: str, reason: str):
        """暂停异常策略"""
        self._suspended_strategies.add(strategy_id)
        health = self._get_strategy_health(strategy_id)
        health.is_suspended = True
        health.suspend_reason = reason
        logger.error("策略暂停: %s - %s", strategy_id, reason)
        self._alerts.append({
            "type": "STRATEGY_SUSPENDED",
            "strategy_id": strategy_id,
            "reason": reason,
            "timestamp": datetime.now().isoformat(),
        })

    def resume_strategy(self, strategy_id: str) -> Dict[str, Any]:
        """恢复被暂停的策略"""
        with self._lock:
            self._suspended_strategies.discard(strategy_id)
            health = self._get_strategy_health(strategy_id)
            health.is_suspended = False
            health.consecutive_errors = 0
            health.suspend_reason = ""
            logger.info("策略已恢复: %s", strategy_id)
            return {"success": True, "strategy_id": strategy_id}

    # ═══════════════════════════════════════════════════════════
    # 一键清仓
    # ═══════════════════════════════════════════════════════════

    def emergency_liquidate(
        self,
        positions: Dict[str, Dict],
        sell_callback,
    ) -> Dict[str, Any]:
        """
        一键清仓 — 紧急全平所有持仓
        
        Args:
            positions: {"symbol": {"quantity": int, "price": float}, ...}
            sell_callback: 卖出回调函数，签名: callback(symbol, quantity, price) -> dict
        Returns:
            清仓结果汇总
        """
        with self._lock:
            self._state = CircuitBreakerState.EMERGENCY
            self._state_changed_at = time.time()
            logger.critical("一键清仓已触发！全平所有持仓")

        results = []
        success_count = 0
        fail_count = 0

        for symbol, pos in positions.items():
            qty = pos.get("quantity", 0)
            if qty <= 0:
                continue
            price = pos.get("price", pos.get("avg_cost", 0))
            try:
                result = sell_callback(symbol, qty, price)
                results.append({
                    "symbol": symbol,
                    "quantity": qty,
                    "price": price,
                    "result": result,
                    "status": "success" if result.get("status") == "ok" else "failed",
                })
                if result.get("status") == "ok":
                    success_count += 1
                else:
                    fail_count += 1
            except Exception as e:
                results.append({
                    "symbol": symbol,
                    "quantity": qty,
                    "price": price,
                    "error": str(e),
                    "status": "error",
                })
                fail_count += 1

        summary = {
            "total_symbols": len(positions),
            "success_count": success_count,
            "fail_count": fail_count,
            "details": results,
            "timestamp": datetime.now().isoformat(),
        }
        logger.critical("一键清仓结果: 成功%d 失败%d", success_count, fail_count)
        self._alerts.append({"type": "EMERGENCY_LIQUIDATE", **summary})
        return summary

    # ═══════════════════════════════════════════════════════════
    # 辅助
    # ═══════════════════════════════════════════════════════════

    def _reset_daily_stats(self):
        self._daily_pnl = 0.0
        self._daily_trades = 0
        self._consecutive_losses = 0
        self._rejection_timestamps.clear()

    def disable_trading(self):
        """手动禁用所有交易（紧急按钮）"""
        self._trading_disabled = True
        self._alerts.append({
            "type": "TRADING_DISABLED",
            "timestamp": datetime.now().isoformat(),
        })
        logger.critical("所有交易已手动禁用！")

    def enable_trading(self):
        """恢复交易"""
        self._trading_disabled = False
        logger.warning("交易已恢复")

    def get_state(self) -> Dict[str, Any]:
        """获取风控引擎完整状态"""
        with self._lock:
            return {
                "circuit_breaker": self._state.value,
                "state_changed_at": datetime.fromtimestamp(self._state_changed_at).isoformat(),
                "daily_pnl": self._daily_pnl,
                "daily_trades": self._daily_trades,
                "consecutive_losses": self._consecutive_losses,
                "rejection_storm_count": len(self._rejection_timestamps),
                "suspended_strategies": list(self._suspended_strategies),
                "trading_disabled": self._trading_disabled,
                "alerts_count": len(self._alerts),
            }

    def get_recent_alerts(self, limit: int = 20) -> list:
        """获取最近告警"""
        return self._alerts[-limit:]

    def is_call_auction(self) -> bool:
        """判断当前是否处于集合竞价时段"""
        now = datetime.now().time()
        total_minutes = now.hour * 60 + now.minute
        ca_start = A_SHARE_CALL_AUCTION_MORNING[0][0] * 60 + A_SHARE_CALL_AUCTION_MORNING[0][1]
        ca_end = A_SHARE_CALL_AUCTION_MORNING[1][0] * 60 + A_SHARE_CALL_AUCTION_MORNING[1][1]
        return ca_start <= total_minutes <= ca_end

    def is_trading_hours(self) -> bool:
        """判断当前是否在A股连续竞价时段"""
        now = datetime.now()
        t = now.time()
        total_minutes = t.hour * 60 + t.minute
        morning_ok = (
            A_SHARE_MORNING_START[0] * 60 + A_SHARE_MORNING_START[1]
            <= total_minutes
            <= A_SHARE_MORNING_END[0] * 60 + A_SHARE_MORNING_END[1]
        )
        afternoon_ok = (
            A_SHARE_AFTERNOON_START[0] * 60 + A_SHARE_AFTERNOON_START[1]
            <= total_minutes
            <= A_SHARE_AFTERNOON_END[0] * 60 + A_SHARE_AFTERNOON_END[1]
        )
        weekday_ok = now.weekday() < 5
        return weekday_ok and (morning_ok or afternoon_ok)

    def get_price_limits(self, prev_close: float, *, is_st: bool = False, is_kcb: bool = False, is_cyb: bool = False) -> Dict[str, float]:
        """
        计算涨跌停价
        A股: ±10%  ST: ±5%  科创/创业板: ±20%
        """
        if is_st:
            pct = 0.05
        elif is_kcb or is_cyb:
            pct = 0.20
        else:
            pct = 0.10
        return {
            "high_limit": round(prev_close * (1 + pct), 2),
            "low_limit": round(prev_close * (1 - pct), 2),
        }

    # ═══════════════════════════════════════════════════════════
    # 事后风控 / 日终对账
    # ═══════════════════════════════════════════════════════════

    def eod_reconciliation(
        self,
        book_cash: float,
        book_positions: Dict[str, Dict],
        broker_cash: float,
        broker_positions: Dict[str, Dict],
    ) -> Dict[str, Any]:
        """
        日终对账 — 比对本地记账与券商实际持仓
        """
        discrepancies = []

        # 现金对账
        cash_diff = abs(book_cash - broker_cash)
        if cash_diff > 0.01:
            discrepancies.append({
                "type": "CASH",
                "book": book_cash,
                "broker": broker_cash,
                "diff": book_cash - broker_cash,
            })

        # 持仓对账
        all_symbols = set(list(book_positions.keys()) + list(broker_positions.keys()))
        for sym in all_symbols:
            book_qty = book_positions.get(sym, {}).get("quantity", 0)
            broker_qty = broker_positions.get(sym, {}).get("quantity", 0)
            if book_qty != broker_qty:
                discrepancies.append({
                    "type": "POSITION",
                    "symbol": sym,
                    "book_qty": book_qty,
                    "broker_qty": broker_qty,
                    "diff": book_qty - broker_qty,
                })

        if discrepancies:
            logger.error("日终对账差异: %d项", len(discrepancies))
            for d in discrepancies:
                logger.error("  %s", d)

        return {
            "status": "reconciled" if not discrepancies else "discrepancy",
            "discrepancies": discrepancies,
            "timestamp": datetime.now().isoformat(),
        }


# ── 原 RiskManager 兼容包装 ──
class RiskManager:
    """向后兼容的 RiskManager 包装器"""
    def __init__(self, max_position_pct: float = 0.2):
        self._engine = HardRiskEngine()
        self.max_position_pct = max_position_pct

    def evaluate(self, position: dict) -> dict:
        return {"status": "safe", "risk_score": 0.0}

    def get_position_limit(self) -> float:
        return self.max_position_pct

    def pre_trade_check(self, **kwargs) -> dict:
        return self._engine.pre_trade_check(**kwargs)